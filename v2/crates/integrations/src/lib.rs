use anyhow::{anyhow, Context, Result};
use reqwest::Client;
use rust_companion_v2_shared::ProviderDescriptor;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use url::Url;

#[derive(Clone)]
pub struct IntegrationClients {
    http: Client,
}

impl Default for IntegrationClients {
    fn default() -> Self {
        Self {
            http: Client::builder()
                .user_agent("RustCompanionPlus/2.0")
                .build()
                .expect("HTTP client"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NotificationMessage {
    pub title: String,
    pub body: String,
    pub priority: i32,
    pub action_url: Option<String>,
}

impl IntegrationClients {
    pub async fn send_discord_webhook(
        &self,
        webhook_url: &str,
        message: &NotificationMessage,
    ) -> Result<()> {
        validate_https_secret_url(webhook_url, "discord.com")?;
        self.http
            .post(webhook_url)
            .json(&json!({
                "username": "Rust Companion+",
                "content": format!("**{}**\n{}", message.title, message.body),
                "allowed_mentions": { "parse": [] }
            }))
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn publish_ntfy(
        &self,
        base_url: &str,
        topic: &str,
        message: &NotificationMessage,
    ) -> Result<()> {
        let mut url = Url::parse(base_url).context("invalid ntfy base URL")?;
        if url.scheme() != "https"
            && url.host_str() != Some("127.0.0.1")
            && url.host_str() != Some("localhost")
        {
            return Err(anyhow!("ntfy must use HTTPS unless it is local"));
        }
        url.path_segments_mut()
            .map_err(|_| anyhow!("invalid ntfy URL"))?
            .push(topic);
        self.http
            .post(url)
            .header("Title", &message.title)
            .header("Priority", message.priority.clamp(1, 5).to_string())
            .body(message.body.clone())
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn send_telegram(
        &self,
        token: &str,
        chat_id: &str,
        message: &NotificationMessage,
    ) -> Result<()> {
        let url = format!("https://api.telegram.org/bot{token}/sendMessage");
        self.http
            .post(url)
            .json(&json!({
                "chat_id": chat_id,
                "text": format!("{}\n{}", message.title, message.body),
                "disable_web_page_preview": true
            }))
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn send_matrix(
        &self,
        homeserver: &str,
        token: &str,
        room_id: &str,
        transaction_id: &str,
        message: &NotificationMessage,
    ) -> Result<()> {
        let base = Url::parse(homeserver).context("invalid Matrix homeserver")?;
        if base.scheme() != "https" {
            return Err(anyhow!("Matrix homeserver must use HTTPS"));
        }
        let encoded_room: String =
            url::form_urlencoded::byte_serialize(room_id.as_bytes()).collect();
        let encoded_tx: String =
            url::form_urlencoded::byte_serialize(transaction_id.as_bytes()).collect();
        let endpoint = base.join(&format!(
            "/_matrix/client/v3/rooms/{encoded_room}/send/m.room.message/{encoded_tx}"
        ))?;
        self.http
            .put(endpoint)
            .bearer_auth(token)
            .json(&json!({
                "msgtype": "m.text",
                "body": format!("{}\n{}", message.title, message.body)
            }))
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn steam_player_summaries(
        &self,
        api_key: &str,
        steam_ids: &[String],
    ) -> Result<Value> {
        let response = self
            .http
            .get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/")
            .query(&[("key", api_key), ("steamids", &steam_ids.join(","))])
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        Ok(response)
    }

    pub async fn battlemetrics_server(
        &self,
        server_id: &str,
        bearer_token: Option<&str>,
    ) -> Result<Value> {
        let url = format!("https://api.battlemetrics.com/servers/{server_id}");
        let mut request = self.http.get(url);
        if let Some(token) = bearer_token.filter(|value| !value.is_empty()) {
            request = request.bearer_auth(token);
        }
        Ok(request.send().await?.error_for_status()?.json().await?)
    }

    pub async fn latest_github_release(&self, repository: &str) -> Result<Value> {
        let url = format!("https://api.github.com/repos/{repository}/releases/latest");
        Ok(self
            .http
            .get(url)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?)
    }

    pub async fn rustmaps_status(&self, map_id: &str, api_key: Option<&str>) -> Result<Value> {
        let url = format!("https://api.rustmaps.com/v4/maps/{map_id}");
        let mut request = self.http.get(url);
        if let Some(key) = api_key.filter(|value| !value.is_empty()) {
            request = request.header("X-API-Key", key);
        }
        Ok(request.send().await?.error_for_status()?.json().await?)
    }
}

pub fn steam_openid_login_url(return_to: &str, realm: &str) -> Result<String> {
    let mut url = Url::parse("https://steamcommunity.com/openid/login")?;
    url.query_pairs_mut()
        .append_pair("openid.ns", "http://specs.openid.net/auth/2.0")
        .append_pair("openid.mode", "checkid_setup")
        .append_pair("openid.return_to", return_to)
        .append_pair("openid.realm", realm)
        .append_pair(
            "openid.identity",
            "http://specs.openid.net/auth/2.0/identifier_select",
        )
        .append_pair(
            "openid.claimed_id",
            "http://specs.openid.net/auth/2.0/identifier_select",
        );
    Ok(url.to_string())
}

pub fn steam_id_from_claimed_id(claimed_id: &str) -> Option<String> {
    let value = claimed_id.trim_end_matches('/').rsplit('/').next()?;
    (value.len() == 17 && value.chars().all(|character| character.is_ascii_digit()))
        .then(|| value.to_owned())
}

pub fn provider_catalog() -> Vec<ProviderDescriptor> {
    vec![
        provider(
            "rustplus",
            "Rust+ local bridge",
            "game",
            true,
            false,
            &[],
            &["team", "chat", "map", "markers", "smart_devices", "cameras"],
            "Pairing tokens remain on the player device.",
        ),
        provider(
            "steam_openid",
            "Steam OpenID",
            "identity",
            true,
            true,
            &[],
            &["login", "steam_id"],
            "Authentication is completed on Steam's website.",
        ),
        provider(
            "steam_web_api",
            "Steam Web API",
            "identity",
            true,
            true,
            &["STEAM_WEB_API_KEY"],
            &["avatars", "profiles", "ownership"],
            "Protected keys belong only on the backend.",
        ),
        provider(
            "discord",
            "Discord OAuth, bot and webhooks",
            "notifications",
            true,
            true,
            &["DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET"],
            &["alerts", "commands", "acknowledgements", "role_linking"],
            "Bot and OAuth tokens are server-side secrets.",
        ),
        provider(
            "battlemetrics",
            "BattleMetrics",
            "server_intelligence",
            true,
            false,
            &[],
            &["server_status", "population", "wipe_metadata"],
            "Public data only unless the user configures a token.",
        ),
        provider(
            "rustmaps",
            "RustMaps",
            "maps",
            true,
            true,
            &["RUSTMAPS_API_KEY"],
            &["map_images", "monuments", "seed_metadata"],
            "Map assets are cached per server.",
        ),
        provider(
            "github_releases",
            "GitHub Releases",
            "updates",
            true,
            false,
            &[],
            &["update_checks", "release_notes"],
            "Only public release metadata is requested.",
        ),
        provider(
            "ntfy",
            "ntfy",
            "notifications",
            true,
            false,
            &[],
            &["push", "self_hosted_push"],
            "Self-hosting is recommended for sensitive alerts.",
        ),
        provider(
            "telegram",
            "Telegram Bot API",
            "notifications",
            true,
            true,
            &["TELEGRAM_BOT_TOKEN"],
            &["alerts", "commands"],
            "Bot tokens are server-side secrets.",
        ),
        provider(
            "matrix",
            "Matrix Client-Server API",
            "notifications",
            true,
            true,
            &["MATRIX_HOMESERVER", "MATRIX_ACCESS_TOKEN"],
            &["rooms", "alerts", "federated_chat"],
            "Access tokens are encrypted at rest.",
        ),
        provider(
            "maxmind_geolite2",
            "MaxMind GeoLite2",
            "geolocation",
            true,
            true,
            &["MAXMIND_DATABASE_PATH"],
            &["approximate_server_region"],
            "Results are approximate and never treated as an exact address.",
        ),
        provider(
            "sentry",
            "Sentry",
            "observability",
            true,
            true,
            &["SENTRY_DSN"],
            &["crash_reporting", "performance"],
            "Opt-in only; Steam IDs, chat, and tokens are scrubbed.",
        ),
        provider(
            "opentelemetry",
            "OpenTelemetry",
            "observability",
            true,
            false,
            &[],
            &["traces", "metrics", "logs"],
            "Can export to a self-hosted collector.",
        ),
        provider(
            "web_push",
            "Web Push",
            "notifications",
            true,
            false,
            &["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"],
            &["browser_push"],
            "Subscriptions can be revoked by the user.",
        ),
        provider(
            "cloudflare_turnstile",
            "Cloudflare Turnstile",
            "abuse_prevention",
            true,
            true,
            &["TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"],
            &["signup_protection"],
            "Used only on public web authentication flows.",
        ),
        provider(
            "twitch",
            "Twitch Helix",
            "presence",
            true,
            true,
            &["TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"],
            &["stream_status", "team_stream_links"],
            "Only explicitly linked Twitch accounts are queried.",
        ),
    ]
}

fn provider(
    id: &str,
    display_name: &str,
    category: &str,
    free_to_use: bool,
    requires_account: bool,
    required_environment: &[&str],
    capabilities: &[&str],
    privacy_note: &str,
) -> ProviderDescriptor {
    ProviderDescriptor {
        id: id.to_owned(),
        display_name: display_name.to_owned(),
        category: category.to_owned(),
        free_to_use,
        requires_account,
        required_environment: required_environment
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        capabilities: capabilities
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        privacy_note: privacy_note.to_owned(),
    }
}

fn validate_https_secret_url(value: &str, expected_suffix: &str) -> Result<()> {
    let url = Url::parse(value).context("invalid URL")?;
    if url.scheme() != "https" {
        return Err(anyhow!("secret-bearing integration URL must use HTTPS"));
    }
    let host = url.host_str().unwrap_or_default();
    if host != expected_suffix && !host.ends_with(&format!(".{expected_suffix}")) {
        return Err(anyhow!("unexpected integration host"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn steam_claimed_id_is_strict() {
        assert_eq!(
            steam_id_from_claimed_id("https://steamcommunity.com/openid/id/76561199121283118"),
            Some("76561199121283118".into())
        );
        assert_eq!(
            steam_id_from_claimed_id("https://example.com/not-steam"),
            None
        );
    }

    #[test]
    fn catalog_contains_required_foundation_integrations() {
        let ids: Vec<_> = provider_catalog().into_iter().map(|item| item.id).collect();
        for required in [
            "rustplus",
            "steam_openid",
            "discord",
            "battlemetrics",
            "ntfy",
            "matrix",
            "opentelemetry",
        ] {
            assert!(ids.contains(&required.to_owned()), "missing {required}");
        }
    }
}
