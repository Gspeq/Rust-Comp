# Rust Companion+

**Developed by Taylor Marshall**

Rust Companion+ is a desktop information and planning companion for the PC version of Rust. This final-gate update makes the launcher the single entry point for both source and EXE runs.

## Final launch behavior

`Run_Rust_Companion_Plus_Source.bat`, `launcher.py`, `main.py`, and the compiled EXE all follow the same sequence:

1. Load global BattleMetrics and RustMaps keys from the persistent AppData vault.
2. Wait until `RustClient.exe` is actually running.
3. Reject connection lines from older Rust sessions.
4. Wait until the current Rust session joins a server.
5. Identify the exact game endpoint.
6. Try to discover the Rust+ companion port from:
   - the current Rust log,
   - the exact BattleMetrics server record,
   - Source A2S server rules,
   - a fresh Rust+ pairing notification or imported pairing payload.
7. Load the exact saved profile for `game IP:game port`.
8. Ask only for server-specific values that are still missing.
9. Validate the Rust+ WebSocket using the detected host, companion port, Steam ID, and player token.
10. Open the main GUI only after validation succeeds.

The player token and Rust+ port are never reused across unrelated game-server profiles. The Steam ID is treated as account-wide.

## Persistent data

Source runs and the compiled EXE use the same application-data directory. It stores:

- BattleMetrics and RustMaps keys
- Per-server Rust+ profiles
- Global Steam identity
- Optional FCM pairing-receiver configuration
- Detection diagnostics and bootstrap snapshot
- Notes, planners, timelines, and other application saves

Run either of these to print or open the exact save location:

```powershell
.\RustCompanionPlus.exe --data-dir
.\RustCompanionPlus.exe --open-data-folder
```

The save file deliberately remains outside the EXE so upgrades do not erase it.

## Run from source

Double-click:

```text
Run_Rust_Companion_Plus_Source.bat
```

The script creates `.venv`, installs required packages, and starts the gated launcher.

## Pairing when the server does not publish its Rust+ port

The launcher offers four choices when a server profile is incomplete:

- **A** — listen for a fresh Rust+ pairing notification using a saved/imported `rustplus.py.config.json`
- **P** — paste a pairing JSON notification or provide its JSON file path
- **R** — retry current-log, BattleMetrics, and A2S discovery
- **M** — enter only the missing values manually

A pairing payload is expected to contain fields equivalent to:

```json
{
  "ip": "server IP",
  "port": 28082,
  "playerId": 76561190000000000,
  "playerToken": 123456789
}
```

The launcher validates the completed profile before opening the GUI.

## Build the single Windows EXE

Run:

```text
Build_Rust_Companion_Plus.bat
```

The build script:

1. Creates/reuses `.venv`.
2. Installs the app dependencies and PyInstaller.
3. Compiles the Python source.
4. Runs all tests.
5. Bundles the launcher, GUI, services, libraries, and package data into one console-enabled EXE.
6. Writes a SHA-256 checksum.

Output:

```text
release\RustCompanionPlus.exe
release\RustCompanionPlus.exe.sha256
release\README-FIRST-RUN.txt
```

## Important limitation

A Rust client cannot always discover `app.port` from the normal game connection alone. The launcher checks every legitimate published source it has, but when a server hides the port, the authoritative automatic method is a Rust+ pairing notification. It does not scan or guess arbitrary ports.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Feature hubs and automatic retention

- Saved server profiles are removed after 30 days without a live update and can be removed individually or all at once.
- Map Intelligence includes bounded zoom, icon visibility controls, and map-derived starter-base recommendations with reasons and cautions.
- Marketplace defaults to Best value, highlights strong and weak offers, and keeps advanced filters under an Advanced tab.
- Smart Devices is a standalone Rust+ hub with saved entities, batch reads, batch controls, favorites, zones, and protection/capacity details.
- Electrical opens with a simple natural-language planner while preserving the full visual circuit analyzer under Advanced Circuit.
- Utilities is intentionally limited to recycler calculations; map routing and smart devices live in their dedicated hubs.

## Marketplace alerts and simplified navigation

<!-- MARKETPLACE_ALERTS_061 -->

The Utilities page is temporarily hidden. Marketplace rows use neutral styling
and plain-text ratings calculated from normalized unit price, comparable live
offers, rolling server-specific history, stock, peer rank, confidence, and
robust outlier detection. While the application is open, new STEAL, CAN'T MISS,
and possible listing-error offers produce a non-modal alert with an Open Shops
action. Notification behavior is configured from the Dashboard and shared by
source and packaged EXE launches. Repeated unchanged listings are suppressed
for the configured interval.

## Contextual guide, compact marketplace, and fullscreen alerts

<!-- CONTEXT_GUIDE_COMPACT_SHOPS_070 -->

The small `? Guide` button remains visible on every application tab and opens
the section for the page currently being viewed. The in-app catalog and
`docs/FEATURE_GUIDE.md` are generated from the same source and must be updated
whenever a tab or feature changes.

Marketplace blueprint offers are always visible and marked with a `BP:` prefix;
the separate Blueprint mode filter has been removed. The results table omits
redundant coordinate/type columns and uses compact responsive columns so normal
listings fit without horizontal scrolling.

Marketplace alerts use both the existing non-modal in-app card and a native
Windows notification-area message. The Windows path is intended to remain
visible while Rust is fullscreen and to place the alert in Windows Notification
Center, subject to the user's Windows notification and Do Not Disturb settings.
