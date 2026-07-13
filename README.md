# Rust Companion+

A legitimate, desktop-first information and planning companion for the PC version of Rust.

## What is implemented

- Modern dark CustomTkinter interface
- Rust+ credentials and server snapshot adapter
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

## Project structure

```text
Rust_Companion_Plus/
├─ main.py
├─ requirements.txt
├─ requirements-core.txt
├─ run_windows.bat
├─ rust_companion_plus/
│  ├─ app.py
│  ├─ catalog.py
│  ├─ config.py
│  ├─ models.py
│  ├─ storage.py
│  ├─ data/
│  │  └─ electrical_components.json
│  ├─ services/
│  │  ├─ electrical.py
│  │  ├─ rustplus_client.py
│  │  └─ tools.py
│  └─ ui/
│     ├─ common.py
│     └─ tabs/
│        ├─ dashboard.py
│        ├─ electrical.py
│        ├─ map_tab.py
│        ├─ shops.py
│        ├─ team.py
│        ├─ threats.py
│        ├─ tools.py
│        └─ notes.py
└─ tests/
   └─ test_electrical.py
```

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

To run the planning tools without live Rust+ support:

```powershell
pip install -r requirements-core.txt
python main.py
```

## Rust+ pairing details

The Python Rust+ wrapper expects:

- Server IP
- Companion port
- Steam ID
- Player token

The app never prints the token, but this foundation stores saved credentials in its local JSON application-data folder. For a distributed release, replace that storage with Windows Credential Manager, macOS Keychain, or another OS secret store.

Rust+ data access varies by server and pairing state. This app treats Rust+ as an optional adapter. Features that the companion protocol does not expose directly—such as ore-node heatmaps, arbitrary enemy tracking, exact decay state, or unrestricted inventory access—remain manual planners or require a server plugin you control.

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

1. Add an OS keyring credential backend.
2. Add a dedicated async event loop and long-lived Rust+ socket.
3. Add map pan/zoom and persisted polygon overlays.
4. Import item definitions automatically into the vending and recycle tools.
5. Add a node-and-wire circuit canvas and validate branch/splitter topology.
6. Package with PyInstaller.
