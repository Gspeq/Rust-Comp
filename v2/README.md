# Rust Companion+ 2.0

This directory is the additive Rust/Tauri migration. The production Python/CustomTkinter application remains available while v2 is proven.

## Included foundation

- Rust Axum HTTP/WebSocket service.
- SQLite development and PostgreSQL production schema.
- Friends, blocking, teams, roles, devices, sessions, presence, objectives, tactical markers, shared notes, shopping, smart bindings, alert rules, acknowledgements, integrations and append-only events.
- Tauri 2 desktop shell and React/TypeScript operations UI.
- Python Rust+ sidecar that reuses the existing tested pairing/client implementation without uploading player tokens.
- Provider catalog and clients for Steam, Discord, BattleMetrics, RustMaps, GitHub Releases, ntfy, Telegram and Matrix; configuration contracts for GeoLite2, Sentry, OpenTelemetry, Web Push, Turnstile and Twitch.

## Security boundaries

Rust+ player tokens remain local. Steam/Discord/bot/API secrets are backend-only. The example environment file contains no real credentials. Shared events contain sanitized data only.

## Development

1. Copy `.env.example` to `.env` and configure only providers you use.
2. Optionally run `docker compose up -d postgres`.
3. Run `cargo run -p rust-companion-v2-server` from this directory.
4. Run `npm install` and `npm run tauri dev` under `apps/desktop`, or use the root V2 development launcher.

## Migration rule

No v2 module may delete or bypass the existing Python test suite until equivalent behavior has automated Rust/TypeScript tests and a documented data migration.


## Windows development launcher

Run `v2\\Run_Rust_Companion_Plus_V2_Dev.bat` from the repository. The launcher intentionally lives under `v2/` so the legacy root launcher allowlist remains unchanged.
