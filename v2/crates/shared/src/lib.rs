use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TeamRole {
    Owner,
    Admin,
    Coordinator,
    Member,
    Viewer,
}

impl TeamRole {
    pub fn can_control_devices(&self) -> bool {
        matches!(self, Self::Owner | Self::Admin | Self::Coordinator)
    }

    pub fn can_manage_members(&self) -> bool {
        matches!(self, Self::Owner | Self::Admin)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserProfile {
    pub id: Uuid,
    pub steam_id: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TeamSummary {
    pub id: Uuid,
    pub name: String,
    pub owner_id: Uuid,
    pub member_count: i64,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Objective {
    pub id: Uuid,
    pub team_id: Uuid,
    pub title: String,
    pub description: String,
    pub grid: Option<String>,
    pub status: ObjectiveStatus,
    pub priority: i32,
    pub created_by: Uuid,
    pub assigned_to: Option<Uuid>,
    pub expires_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveStatus {
    Open,
    Claimed,
    InProgress,
    Completed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TacticalMarker {
    pub id: Uuid,
    pub team_id: Uuid,
    pub kind: String,
    pub label: String,
    pub x_fraction: f64,
    pub y_fraction: f64,
    pub radius_meters: Option<f64>,
    pub created_by: Uuid,
    pub expires_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShoppingRequest {
    pub id: Uuid,
    pub team_id: Uuid,
    pub item_name: String,
    pub quantity: i32,
    pub priority: i32,
    pub requested_by: Uuid,
    pub claimed_by: Option<Uuid>,
    pub completed_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TeamEvent {
    pub id: Uuid,
    pub team_id: Uuid,
    pub actor_id: Option<Uuid>,
    pub event_type: String,
    pub payload: Value,
    pub occurred_at: DateTime<Utc>,
}

impl TeamEvent {
    pub fn new(
        team_id: Uuid,
        actor_id: Option<Uuid>,
        event_type: impl Into<String>,
        payload: Value,
    ) -> Self {
        Self {
            id: Uuid::new_v4(),
            team_id,
            actor_id,
            event_type: event_type.into(),
            payload,
            occurred_at: Utc::now(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderDescriptor {
    pub id: String,
    pub display_name: String,
    pub category: String,
    pub free_to_use: bool,
    pub requires_account: bool,
    pub required_environment: Vec<String>,
    pub capabilities: Vec<String>,
    pub privacy_note: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn device_control_is_role_restricted() {
        assert!(TeamRole::Owner.can_control_devices());
        assert!(TeamRole::Coordinator.can_control_devices());
        assert!(!TeamRole::Viewer.can_control_devices());
    }

    #[test]
    fn team_events_round_trip_as_json() {
        let event = TeamEvent::new(
            Uuid::new_v4(),
            None,
            "objective.created",
            serde_json::json!({"title": "Cargo"}),
        );
        let encoded = serde_json::to_string(&event).unwrap();
        let decoded: TeamEvent = serde_json::from_str(&encoded).unwrap();
        assert_eq!(event.id, decoded.id);
        assert_eq!(decoded.event_type, "objective.created");
    }
}
