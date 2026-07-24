use std::{env, net::SocketAddr, sync::Arc};

use anyhow::Result;
use axum::{
    extract::{Path, State, WebSocketUpgrade},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use dashmap::DashMap;
use futures_util::{SinkExt, StreamExt};
use rust_companion_v2_integrations::{provider_catalog, steam_openid_login_url};
use rust_companion_v2_shared::{ObjectiveStatus, TeamEvent};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::{any::AnyPoolOptions, AnyPool, Row};
use tokio::sync::broadcast;
use tower_http::{cors::CorsLayer, trace::TraceLayer};
use uuid::Uuid;

#[derive(Clone)]
struct AppState {
    database: AnyPool,
    rooms: Arc<DashMap<Uuid, broadcast::Sender<TeamEvent>>>,
}

impl AppState {
    async fn connect(database_url: &str) -> Result<Self> {
        sqlx::any::install_default_drivers();
        let max_connections = if database_url.contains(":memory:") {
            1
        } else {
            8
        };
        let database = AnyPoolOptions::new()
            .max_connections(max_connections)
            .connect(database_url)
            .await?;
        apply_schema(&database).await?;
        Ok(Self {
            database,
            rooms: Arc::new(DashMap::new()),
        })
    }

    fn room(&self, team_id: Uuid) -> broadcast::Sender<TeamEvent> {
        self.rooms
            .entry(team_id)
            .or_insert_with(|| broadcast::channel(256).0)
            .clone()
    }

    fn publish(&self, event: TeamEvent) {
        let _ = self.room(event.team_id).send(event);
    }
}

#[derive(Debug, Deserialize)]
struct CreateTeam {
    name: String,
    owner_id: Uuid,
}

#[derive(Debug, Deserialize)]
struct FriendRequest {
    requester_id: Uuid,
    addressee_id: Uuid,
}

#[derive(Debug, Deserialize)]
struct CreateObjective {
    title: String,
    description: Option<String>,
    grid: Option<String>,
    priority: Option<i32>,
    created_by: Uuid,
    assigned_to: Option<Uuid>,
}

#[derive(Debug, Deserialize)]
struct CreateMarker {
    kind: String,
    label: String,
    x_fraction: f64,
    y_fraction: f64,
    radius_meters: Option<f64>,
    created_by: Uuid,
}

#[derive(Debug, Deserialize)]
struct CreateShoppingRequest {
    item_name: String,
    quantity: i32,
    priority: Option<i32>,
    requested_by: Uuid,
}

#[derive(Debug, Deserialize)]
struct SteamLoginQuery {
    return_to: String,
    realm: String,
}

#[derive(Debug, Serialize)]
struct CreatedId {
    id: Uuid,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();
    let database_url = env::var("DATABASE_URL")
        .unwrap_or_else(|_| "sqlite://rust_companion_v2.db?mode=rwc".to_owned());
    let bind = env::var("RUST_COMPANION_V2_BIND").unwrap_or_else(|_| "127.0.0.1:43117".to_owned());
    let state = AppState::connect(&database_url).await?;
    let address: SocketAddr = bind.parse()?;
    tracing::info!(%address, "Rust Companion+ v2 server listening");
    let listener = tokio::net::TcpListener::bind(address).await?;
    axum::serve(listener, app(state)).await?;
    Ok(())
}

fn app(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/api/v1/integrations", get(integrations))
        .route("/api/v1/auth/steam/login", post(steam_login))
        .route("/api/v1/friends/request", post(friend_request))
        .route("/api/v1/teams", post(create_team))
        .route(
            "/api/v1/teams/{team_id}/objectives",
            get(list_objectives).post(create_objective),
        )
        .route(
            "/api/v1/teams/{team_id}/markers",
            get(list_markers).post(create_marker),
        )
        .route(
            "/api/v1/teams/{team_id}/shopping",
            get(list_shopping).post(create_shopping),
        )
        .route("/ws/teams/{team_id}", get(team_socket))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

async fn health() -> Json<Value> {
    Json(
        json!({"status": "ok", "service": "rust-companion-v2", "version": env!("CARGO_PKG_VERSION")}),
    )
}

async fn integrations() -> Json<Value> {
    Json(json!({"providers": provider_catalog()}))
}

async fn steam_login(Json(query): Json<SteamLoginQuery>) -> Result<Json<Value>, ApiError> {
    let url =
        steam_openid_login_url(&query.return_to, &query.realm).map_err(ApiError::bad_request)?;
    Ok(Json(json!({"authorization_url": url})))
}

async fn friend_request(
    State(state): State<AppState>,
    Json(request): Json<FriendRequest>,
) -> Result<(StatusCode, Json<CreatedId>), ApiError> {
    if request.requester_id == request.addressee_id {
        return Err(ApiError::bad_request(
            "cannot send a friend request to yourself",
        ));
    }
    let id = Uuid::new_v4();
    sqlx::query("INSERT INTO friendships (id, requester_id, addressee_id, status, created_at, updated_at) VALUES ($1, $2, $3, 'pending', $4, $5)")
        .bind(id.to_string())
        .bind(request.requester_id.to_string())
        .bind(request.addressee_id.to_string())
        .bind(Utc::now().to_rfc3339())
        .bind(Utc::now().to_rfc3339())
        .execute(&state.database)
        .await
        .map_err(ApiError::database)?;
    Ok((StatusCode::CREATED, Json(CreatedId { id })))
}

async fn create_team(
    State(state): State<AppState>,
    Json(request): Json<CreateTeam>,
) -> Result<(StatusCode, Json<CreatedId>), ApiError> {
    let id = Uuid::new_v4();
    let now = Utc::now().to_rfc3339();
    sqlx::query("INSERT INTO teams (id, name, owner_id, created_at, updated_at) VALUES ($1, $2, $3, $4, $5)")
        .bind(id.to_string()).bind(request.name).bind(request.owner_id.to_string()).bind(&now).bind(&now)
        .execute(&state.database).await.map_err(ApiError::database)?;
    sqlx::query("INSERT INTO team_memberships (team_id, user_id, role, joined_at) VALUES ($1, $2, 'owner', $3)")
        .bind(id.to_string()).bind(request.owner_id.to_string()).bind(&now)
        .execute(&state.database).await.map_err(ApiError::database)?;
    Ok((StatusCode::CREATED, Json(CreatedId { id })))
}

async fn create_objective(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
    Json(request): Json<CreateObjective>,
) -> Result<(StatusCode, Json<CreatedId>), ApiError> {
    let id = Uuid::new_v4();
    sqlx::query("INSERT INTO objectives (id, team_id, title, description, grid, status, priority, created_by, assigned_to, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, 'open', $6, $7, $8, $9, $10)")
        .bind(id.to_string()).bind(team_id.to_string()).bind(&request.title).bind(request.description.unwrap_or_default()).bind(request.grid)
        .bind(request.priority.unwrap_or(1).clamp(0, 5)).bind(request.created_by.to_string()).bind(request.assigned_to.map(|value| value.to_string()))
        .bind(Utc::now().to_rfc3339()).bind(Utc::now().to_rfc3339())
        .execute(&state.database).await.map_err(ApiError::database)?;
    state.publish(TeamEvent::new(
        team_id,
        Some(request.created_by),
        "objective.created",
        json!({"id": id, "title": request.title}),
    ));
    Ok((StatusCode::CREATED, Json(CreatedId { id })))
}

async fn list_objectives(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
) -> Result<Json<Value>, ApiError> {
    let rows = sqlx::query("SELECT id, title, description, grid, status, CAST(priority AS BIGINT) AS priority, created_by, assigned_to, created_at FROM objectives WHERE team_id = $1 ORDER BY priority DESC, created_at DESC")
        .bind(team_id.to_string()).fetch_all(&state.database).await.map_err(ApiError::database)?;
    let values: Vec<Value> = rows.into_iter().map(|row| json!({
        "id": row.get::<String, _>("id"), "title": row.get::<String, _>("title"), "description": row.get::<String, _>("description"),
        "grid": row.try_get::<String, _>("grid").ok(), "status": row.get::<String, _>("status"), "priority": row.get::<i64, _>("priority"),
        "created_by": row.get::<String, _>("created_by"), "assigned_to": row.try_get::<String, _>("assigned_to").ok(), "created_at": row.get::<String, _>("created_at")
    })).collect();
    Ok(Json(json!({"objectives": values})))
}

async fn create_marker(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
    Json(request): Json<CreateMarker>,
) -> Result<(StatusCode, Json<CreatedId>), ApiError> {
    if !(0.0..=1.0).contains(&request.x_fraction) || !(0.0..=1.0).contains(&request.y_fraction) {
        return Err(ApiError::bad_request(
            "marker fractions must be between 0 and 1",
        ));
    }
    let id = Uuid::new_v4();
    sqlx::query("INSERT INTO tactical_markers (id, team_id, kind, label, x_fraction, y_fraction, radius_meters, created_by, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)")
        .bind(id.to_string()).bind(team_id.to_string()).bind(&request.kind).bind(&request.label).bind(request.x_fraction).bind(request.y_fraction)
        .bind(request.radius_meters).bind(request.created_by.to_string()).bind(Utc::now().to_rfc3339())
        .execute(&state.database).await.map_err(ApiError::database)?;
    state.publish(TeamEvent::new(
        team_id,
        Some(request.created_by),
        "marker.created",
        json!({"id": id, "kind": request.kind, "label": request.label}),
    ));
    Ok((StatusCode::CREATED, Json(CreatedId { id })))
}

async fn list_markers(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
) -> Result<Json<Value>, ApiError> {
    let rows = sqlx::query("SELECT id, kind, label, x_fraction, y_fraction, radius_meters, created_by, created_at FROM tactical_markers WHERE team_id = $1 ORDER BY created_at DESC")
        .bind(team_id.to_string()).fetch_all(&state.database).await.map_err(ApiError::database)?;
    let values: Vec<Value> = rows.into_iter().map(|row| json!({
        "id": row.get::<String, _>("id"), "kind": row.get::<String, _>("kind"), "label": row.get::<String, _>("label"),
        "x_fraction": row.get::<f64, _>("x_fraction"), "y_fraction": row.get::<f64, _>("y_fraction"),
        "radius_meters": row.try_get::<f64, _>("radius_meters").ok(), "created_by": row.get::<String, _>("created_by"), "created_at": row.get::<String, _>("created_at")
    })).collect();
    Ok(Json(json!({"markers": values})))
}

async fn create_shopping(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
    Json(request): Json<CreateShoppingRequest>,
) -> Result<(StatusCode, Json<CreatedId>), ApiError> {
    let id = Uuid::new_v4();
    sqlx::query("INSERT INTO shopping_requests (id, team_id, item_name, quantity, priority, requested_by, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)")
        .bind(id.to_string()).bind(team_id.to_string()).bind(&request.item_name).bind(request.quantity.max(1)).bind(request.priority.unwrap_or(1).clamp(0, 5))
        .bind(request.requested_by.to_string()).bind(Utc::now().to_rfc3339()).bind(Utc::now().to_rfc3339())
        .execute(&state.database).await.map_err(ApiError::database)?;
    state.publish(TeamEvent::new(
        team_id,
        Some(request.requested_by),
        "shopping.created",
        json!({"id": id, "item_name": request.item_name}),
    ));
    Ok((StatusCode::CREATED, Json(CreatedId { id })))
}

async fn list_shopping(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
) -> Result<Json<Value>, ApiError> {
    let rows = sqlx::query("SELECT id, item_name, CAST(quantity AS BIGINT) AS quantity, CAST(priority AS BIGINT) AS priority, requested_by, claimed_by, completed_at, created_at FROM shopping_requests WHERE team_id = $1 ORDER BY completed_at IS NOT NULL, priority DESC, created_at DESC")
        .bind(team_id.to_string()).fetch_all(&state.database).await.map_err(ApiError::database)?;
    let values: Vec<Value> = rows.into_iter().map(|row| json!({
        "id": row.get::<String, _>("id"), "item_name": row.get::<String, _>("item_name"), "quantity": row.get::<i64, _>("quantity"),
        "priority": row.get::<i64, _>("priority"), "requested_by": row.get::<String, _>("requested_by"),
        "claimed_by": row.try_get::<String, _>("claimed_by").ok(), "completed_at": row.try_get::<String, _>("completed_at").ok(), "created_at": row.get::<String, _>("created_at")
    })).collect();
    Ok(Json(json!({"shopping": values})))
}

async fn team_socket(
    Path(team_id): Path<Uuid>,
    State(state): State<AppState>,
    upgrade: WebSocketUpgrade,
) -> impl IntoResponse {
    upgrade.on_upgrade(move |socket| async move {
        let (mut sender, mut receiver) = socket.split();
        let mut events = state.room(team_id).subscribe();
        loop {
            tokio::select! {
                event = events.recv() => match event {
                    Ok(event) => {
                        if let Ok(text) = serde_json::to_string(&event) {
                            if sender.send(axum::extract::ws::Message::Text(text.into())).await.is_err() { break; }
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(_) => break,
                },
                incoming = receiver.next() => match incoming {
                    Some(Ok(axum::extract::ws::Message::Close(_))) | None => break,
                    Some(Err(_)) => break,
                    _ => {}
                }
            }
        }
    })
}

async fn apply_schema(pool: &AnyPool) -> Result<()> {
    let schema = include_str!("../../../migrations/0001_initial.sql");
    for statement in schema
        .split(';')
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        sqlx::query(statement).execute(pool).await?;
    }
    Ok(())
}

struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(error: impl std::fmt::Display) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: error.to_string(),
        }
    }

    fn database(error: sqlx::Error) -> Self {
        tracing::error!(%error, "database operation failed");
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: "database operation failed".to_owned(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        (self.status, Json(json!({"error": self.message}))).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn schema_creates_friend_and_team_tables() {
        let state = AppState::connect("sqlite::memory:").await.unwrap();
        let tables = sqlx::query("SELECT name FROM sqlite_master WHERE type='table'")
            .fetch_all(&state.database)
            .await
            .unwrap();
        let names: Vec<String> = tables.into_iter().map(|row| row.get("name")).collect();
        assert!(names.contains(&"friendships".to_owned()));
        assert!(names.contains(&"team_memberships".to_owned()));
        assert!(names.contains(&"event_log".to_owned()));
    }

    #[test]
    fn objective_status_contract_is_serializable() {
        assert_eq!(
            serde_json::to_string(&ObjectiveStatus::InProgress).unwrap(),
            "\"in_progress\""
        );
    }
}
