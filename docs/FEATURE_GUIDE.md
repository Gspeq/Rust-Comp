# Rust Companion+ Feature Guide

Guide version: 0.8.2
Last updated: 2026-07-22

This file is generated from the same catalog opened by the Dashboard Feature Guide button. Update the catalog whenever a tab or feature changes, then regenerate this document.

## Overview

The Dashboard combines server status, Rust+ pairing, the complete feature guide, marketplace notification presets, intelligence, and the live event timeline.

**When useful:** Use it first after launch, when changing servers, configuring alerts, or learning what another page can do.

### Feature Guide

The Dashboard-only Guide button opens this maintained catalog for every tab and major feature.

**When useful:** Useful when setting up a system for the first time or checking limitations before relying on it.

### Server metrics

Shows server name, population, detected endpoint, and the latest refresh time.

**When useful:** Useful for confirming that the intended live or saved server is active.

### Rust+ pairing

Stores the companion host, app port, Steam ID, and player token for the active server profile.

**When useful:** Useful after pairing or when repairing an incomplete server-specific profile.

### Marketplace notification presets

Filters alerts by All, Basic, Mid tier, High tier, Endgame, or custom watched items, plus rating, stock, cost, blueprint, sound, repeat, Windows, and in-app settings.

**When useful:** Useful for matching alerts to your current wipe progression and avoiding irrelevant notifications.

### Server intelligence and timeline

Explains endpoint evidence and records Rust+, population, team, smart-device, and world-event changes.

**When useful:** Useful for troubleshooting and reviewing what changed while another page was open.


## Map

Map Intelligence combines separate clean and icon-rendered Rust+ maps, cached interactive zoom and pan, multiple quick overlays, and mainland-aware starter analysis.

**When useful:** Use it for route planning, build-location comparison, resource access, and inspecting a specific area.

### Zoom and pan

Uses a cached overlay composite, direct display-size resizing, throttled wheel/pan frames, Fit through 8x zoom, and a high-quality idle redraw.

**When useful:** Useful when a full-map view is too small to inspect terrain or a specific grid.

### Marker toggle

Switches between separately requested clean and icon-rendered Rust+ maps, so shops, events, team positions, and other API icons actually disappear when disabled.

**When useful:** Useful when vending, event, or team icons obscure terrain.

### Quick overlay toggles

Allows several commonly useful resource, road, water, and monument layers to be enabled together while retaining the detailed layer selector.

**When useful:** Useful for comparing competing location factors in one map view.

### Starter spot recommendation

Rejects water-locked cells and small isolated landmasses, prefers mainland access and escape routes, then scores resources, roads, terrain, monuments, events, and map-edge risk.

**When useful:** Useful at wipe start or after relocating; it is not a player-safety guarantee.


## Team

Team Intelligence turns Rust+ team states and positions into a readable operational view and stores the local player's latest death positions.

**When useful:** Use it for teammate coordination, isolation checks, and returning toward a recent death location.

### Team status and isolation

Shows online/alive state, last position, distances, and separated teammates.

**When useful:** Useful before roaming or deciding who needs support.

### Latest deaths

Uses a lightweight one-second team-only poll for alive-to-dead transitions while full server and vending snapshots refresh every five seconds.

**When useful:** Useful for recovery routes; the position remains approximate because Rust+ reports snapshots rather than an exact death packet.

### Monument context

Associates team positions with named monuments when exact parsed map metadata is available.

**When useful:** Useful when a teammate reports only a position or vague landmark.


## Shops

The marketplace searches Rust+ vending offers, marks blueprints, uses calibrated progression-aware deal ratings, sends low-noise alerts, and shows a clean 2×2 area around the selected shop.

**When useful:** Use it when buying or selling, watching progression-specific loot, or checking whether a price is unusually strong.

### Compact listings and BP marking

Important columns fit without sideways scrolling, and blueprint items are visibly prefixed with BP.

**When useful:** Useful for avoiding blueprint/item confusion while scanning many offers.

### Best Value

Compares unique-shop prices and rolling history within identical markets, then adjusts for volatility, exact item tier, payment burden, blueprint burden, stock, and evidence confidence.

**When useful:** Useful for finding strong deals without comparing unrelated trades.

### 2×2 shop-area map

Selecting an offer shows an aligned 2×2 grid neighborhood with the shop at its true position, one marker, and no unrelated server icons.

**When useful:** Useful for recognizing the immediate terrain around the destination without a cluttered full map.

### Loot and item alerts

Dashboard settings filter progression presets and watched items. Ordinary STEAL/CAN'T MISS alerts require an actionable mid/high-tier item; watched-item any-listing alerts remain explicit overrides.

**When useful:** Useful while Rust is fullscreen or while waiting for a rare item to appear.


## Electrical

Electrical opens directly into the complete visual circuit designer. The former basic planner has been removed and its power-balance information remains integrated into the canvas metrics and recommendations.

**When useful:** Use it before building, while diagnosing a circuit, or when hardening an endgame defense and automation network.

### Visual circuit designer

Drag or click equipment, zoom from 50% to 200%, wire clean orthogonal paths, graph-arrange by real power flow, edit quantity/state/zone, and save the complete circuit.

**When useful:** Useful whenever topology matters instead of only component totals.

### Integrated power model

Shows load, peak and average generation, battery storage/output, no-generation runtime, and charging headroom. The clickable assumptions help explains solar average, wind average, battery charge efficiency, and the formulas.

**When useful:** Useful for determining whether a circuit works through night, weather, or generator loss.

### Strategic suggestions

Adds topology fixes plus redundancy, branch priority, turret isolation, Smart Alarm, Storage Monitor, production timer, zone isolation, and single-point-failure advice.

**When useful:** Useful for turning a merely powered circuit into a maintainable and raid-resistant system.


## Smart Devices

Smart Base Control turns paired Rust+ entities into named devices, logical systems, verified scenes, local rules, and an activity log.

**When useful:** Use it to operate defense zones, lights, lockdown circuits, industry, alarms, and storage monitors from one console.

### Devices

Stores entity ID, name, zone, role, logical system, favorite state, and the latest Rust+ status fields; supports batch refresh and ON/OFF.

**When useful:** Useful for replacing raw entity IDs with an organized base-control inventory.

### Systems

Groups selected devices into a named zone or purpose such as North Defense, Core Lights, or Furnace Bank, then refreshes or controls the whole group.

**When useful:** Useful for maintenance and logical control without selecting individual entities every time.

### Scenes

Stores multi-device ON/OFF states such as Raid Mode, Offline Mode, Quiet Mode, Industry Mode, or Emergency Lockdown, with preview, confirmation, and post-run verification.

**When useful:** Useful for changing many circuits safely with one action.

### Rules and activity

Evaluates value transitions, capacity thresholds, status changes, and entity errors after refresh; rules can notify or run a scene when explicitly armed and respect cooldowns.

**When useful:** Useful for low-ammo/storage warnings and controlled local automation. Rules only run while the app and Rust+ connection are active.


## Saved Servers

Saved Servers manages offline server archives, pairing metadata, cached maps, and server-specific workspace data.

**When useful:** Use it to reopen cached data with Rust closed or remove profiles for servers you no longer play.

### Open saved profile

Loads cached server, team, map, shop, timeline, electrical, and smart-control workspace data.

**When useful:** Useful during a Rust+ outage or with Rust closed.

### Delete and retention

Removes one or all saved profiles and automatically purges profiles with no live update for 30 days.

**When useful:** Useful for keeping credentials and cached assets limited to current servers.


## Notes

Notes stores server-aware plans, reminders, routes, tasks, and observations that Rust+ cannot provide.

**When useful:** Use it for build tasks, raid plans, teammate reminders, shopping lists, or manual intelligence.

### Persistent notes

Keeps written information in local application data and the active server workspace.

**When useful:** Useful for details needed across multiple sessions.
