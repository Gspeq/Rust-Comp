# Rust Companion+

A legitimate, desktop-first information and planning companion for the PC version of Rust.

## What is implemented

- Modern dark CustomTkinter interface
- Automatic current-server detection on Windows using:
  - Rust process command-line and network information when available
  - Rust `Player.log` connection records
  - Steam server-history fallback
  - Saved Rust+ profiles as a final fallback
- Automatic refresh pipeline that switches server data, IP, map, wipe information, shops, events, and team data when possible
- BattleMetrics integration:
  - Public server matching and status
  - Population, queue, rank, country, endpoint, map seed/size, description, and wipe metadata
  - Optional authenticated current-player data when the supplied token has permission
- RustMaps v4 integration:
  - Map lookup by live seed and world size
  - Optional procedural-map generation
  - Automatic map/thumbnail metadata and monument/terrain statistics
  - Cached map images
  - Optional `.map` download where the account/map permits it
- Automatic map parser pipeline:
  - Detects a compatible `MapParser.exe`
  - Downloads and parses the newly detected server map when RustMaps permits download
  - Reloads resource points/masks and heatmap overlays automatically
  - Keeps manual import and RustPlusDesk cache detection as fallbacks
- Rust+ credentials and per-server profile selection
- Server overview, team list, events, map retrieval, vending marker search
- Strong electrical planner:
  - Free-text goal parsing
  - Structured placed/planned/inventory component list
  - Peak and estimated average generation
  - Load, battery capacity, output-limit and runtime calculations
  - Practical rule-based optimization suggestions
  - Saved version snapshots and comparison
- Manual threat/death log with repeat-offender counts
- TC upkeep timer
- Building cost calculator
- Recycle calculator with an editable starter catalog
- Farm power/water calculator
- Plant genetics ranking and three-parent crossover heuristic
- Loot value tracker
- Smart-device entity status/control
- Persistent notes

## How automatic server sync works

1. The app looks for a running Rust client and recent connection information.
2. It tests the strongest endpoint candidates against BattleMetrics and selects the best exact Rust-server match.
3. It switches to a saved Rust+ pairing profile for that server when one exists.
4. Rust+ refreshes team, map markers, vending machines, events, and smart-device access.
5. BattleMetrics enriches the snapshot with public population, rank, endpoint, wipe, and map details.
6. When seed and size are known, RustMaps retrieves the matching generated map and terrain/monument metadata.
7. If RustMaps permits `.map` download and `MapParser.exe` is available, the app downloads, parses, caches, and reloads the resource heatmaps.

Automatic detection cannot manufacture a Rust+ player token. Pair each server once and save its profile; afterward the app can select that profile automatically. BattleMetrics and RustMaps can still update when no matching Rust+ token exists.

## Map parser and heatmap accuracy

A map parser reads the Rust `.map` world file and exports structured prefab/location data. Rust Companion+ imports recognized ore, junk-pile, and animal prefab positions into heatmap masks.

These layers represent procedural spawn definitions or parsed map content—not guaranteed live ore nodes. Players can harvest nodes, servers can alter spawn rules, and plugins can change the world. The app therefore labels and treats them as planning heatmaps rather than a live radar.

Exact automatic parsing requires all of the following:

- RustMaps API access
- A map/account for which `canDownload` is true
- A compatible `MapParser.exe`

Without those, the app still displays the live Rust+ map or RustMaps image and supports imported parser folders/manual heatmap notes.

## Install and run

Python 3.11 or 3.12 is recommended.

```powershell
cd Rust_Companion_Plus
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

To run the planning, BattleMetrics, RustMaps, and detection tools without live Rust+ support:

```powershell
pip install -r requirements-core.txt
python main.py
```

## API setup

### BattleMetrics

Public server metadata generally works without a token. Add a BattleMetrics bearer token only when you need an authenticated endpoint, such as permitted current-player data. The app does not bypass BattleMetrics permissions.

### RustMaps

Create/copy an API key from the RustMaps dashboard and paste it into the Overview tab. The integration uses the v4 map status/generation endpoints and respects API errors, rate limits, subscription limits, and `canDownload`.

### Rust+

The Python Rust+ wrapper expects:

- Server IP
- Companion port
- Steam ID
- Player token

Rust+ tokens are server-specific. Save a profile for each paired server. The app masks tokens in the GUI but currently stores credentials and API keys in its local JSON application-data folder. Use this only on your own Windows account; an OS keyring backend is still recommended before distributing the app broadly.

Rust+ data access varies by server and pairing state. Features the companion protocol does not expose directly—such as arbitrary enemy tracking, exact decay state, or unrestricted inventory access—remain manual planners or require a server plugin you control.

## Electrical assumptions

- Power is represented in Rust Watts (`rW`).
- Battery capacity is represented in Rust Watt-minutes (`rWm`).
- Runtime with no generation is `capacity / load`.
- The live-generation runtime is an estimate using editable solar and wind utilization assumptions.
- Battery charging is modeled at 80% efficiency for planning suggestions.
- Branching/wiring behavior is simplified into component power draw. The app is a planner, not a circuit simulator.

Edit `rust_companion_plus/data/electrical_components.json` to add or update components without changing GUI code.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Good next expansions

1. Store tokens/API keys in Windows Credential Manager or another OS keyring.
2. Add a long-lived async Rust+ socket and push notifications.
3. Add map pan/zoom, clickable monument/shop navigation, and persisted polygons.
4. Add BattleMetrics historical population/wipe charts where the API/account permits them.
5. Import current item definitions automatically into vending and recycle tools.
6. Add a node-and-wire circuit canvas and validate branch/splitter topology.
7. Package with PyInstaller and sign Windows builds.
