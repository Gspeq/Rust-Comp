# Rust Companion+ Feature Guide

Guide version: 0.7.0
Last updated: 2026-07-22

This file is generated from the same guide catalog used by the in-application Guide button. Update the catalog whenever a tab or feature changes, then regenerate this document.

## Overview

The Dashboard combines connection status, Rust+ pairing, server intelligence, marketplace notification settings, and the live event timeline.

**When useful:** Use it first when opening the app, changing servers, checking whether Rust+ is live, or changing marketplace alert behavior.

### Server metrics

Shows server name, population, detected game endpoint, and last update.

**When useful:** Useful for confirming that the app is reading the intended server.

### Rust+ pairing

Stores the companion host, app port, Steam ID, and player token for the active server.

**When useful:** Useful after pairing a server or when repairing an incomplete profile.

### Connect and refresh

Requests a fresh Rust+ snapshot using the currently saved pairing profile.

**When useful:** Useful when cached information is visible but live data has not connected.

### Re-detect server

Rechecks the running Rust process, logs, sockets, and public server metadata.

**When useful:** Useful after joining a different server or when the detected endpoint looks wrong.

### Marketplace notifications

Controls alert level, sound, popup duration, repeat suppression, and alerts per scan.

**When useful:** Useful when tuning how often STEAL, CAN'T MISS, and possible listing-error alerts appear.

### Server intelligence

Explains why the endpoint was selected and shows accepted, rejected, and public evidence.

**When useful:** Useful for troubleshooting server detection or Rust+ endpoint differences.

### Live timeline

Records population, team, event, detection, and Rust+ changes.

**When useful:** Useful for reviewing what changed while using other tabs.


## Map

Map Intelligence combines the server map, Rust+ markers, optional resource analysis, zoom controls, and starter-base recommendations.

**When useful:** Use it while planning routes, deciding where to build, locating shops or events, and comparing resource access against player traffic.

### Live and cached map

Uses the current Rust+ map when available and saved map assets when offline.

**When useful:** Useful for planning with Rust closed or during a temporary Rust+ outage.

### Zoom and recenter

Supports fit and fixed zoom levels, mouse-wheel zoom, and click-to-center.

**When useful:** Useful when inspecting a specific grid or shop location.

### Server icon visibility

Shows or hides Rust+ map markers without removing the underlying data.

**When useful:** Useful when markers obscure terrain or resource overlays.

### Resource overlays

Displays parsed or estimated resource and terrain layers when available.

**When useful:** Useful for comparing stone, metal, sulfur, roads, water, and biome access.

### Starter spot recommendation

Scores candidate areas using resources, roads, terrain, water, monuments, events, shops, and edge risk.

**When useful:** Useful at wipe start or after relocating; it is a planning estimate, not a safety guarantee.


## Team

Team Intelligence turns Rust+ team positions and status changes into a readable operational view.

**When useful:** Use it to check who is online or alive, find isolated teammates, review recent deaths, and understand nearby map context.

### Team status

Shows online, alive, position, and last-known state for Rust+ team members.

**When useful:** Useful before roaming or coordinating a return to base.

### Distance and isolation

Compares teammate positions and identifies members far from the group.

**When useful:** Useful for finding separated teammates or deciding who needs support.

### Monument context

Associates team positions with nearby named monuments when exact map data exists.

**When useful:** Useful when teammates report only their map position.

### My last deaths

Stores recent automatic Rust+ alive-to-dead transitions for the local player.

**When useful:** Useful for returning to an approximate death area.


## Shops

The marketplace searches Rust+ vending listings, compares equivalent trades, rates deals in plain text, and maps matching shop locations.

**When useful:** Use it when buying or selling items, checking whether a price is unusual, or finding the closest shop offering a specific trade.

### Buy, payment, and location searches

Filters the item being sold, the requested payment item, and shop/grid text.

**When useful:** Useful for narrowing a large marketplace without hiding important columns.

### BP marking

Blueprint listings stay visible and are prefixed with BP in the sold or payment item field.

**When useful:** Useful for avoiding confusion between a blueprint and the crafted item.

### Best value

Ranks equivalent trades using unit price, live peers, rolling history, stock, rank, confidence, and robust outlier detection.

**When useful:** Useful for finding strong offers without comparing unrelated currencies or blueprint states.

### Deal ratings

Labels listings as possible error, can't miss, steal, good value, fair, overpriced, unpriced, or out of stock.

**When useful:** Useful for understanding the recommendation without relying on row color.

### Advanced limits

Optionally limits results by minimum stock or maximum total cost.

**When useful:** Useful after the basic searches already identify the desired market.

### Shop minimap

Shows the selected shop and other matching locations on a focused map.

**When useful:** Useful for choosing between several comparable offers.

### Marketplace alerts

Sends new high-value or possible listing-error notices in-app and through Windows notifications.

**When useful:** Useful while Rust is fullscreen or while viewing another app tab.


## Electrical

Electrical Planner offers a fast natural-language power estimate and a complete advanced circuit workspace.

**When useful:** Use it before building a circuit, when diagnosing insufficient power, or when planning batteries and generation for a base.

### Simple Planner

Parses common Rust electrical components from a written description and estimates load, generation, storage, and runtime.

**When useful:** Useful for quick plans without drawing every wire.

### Recommendations

Highlights generation shortages, battery limits, excess capacity, and likely substitutions.

**When useful:** Useful for correcting a plan before spending resources.

### Advanced Circuit

Preserves the visual circuit editor, wiring paths, branch analysis, loop detection, disconnected-load checks, and saved layouts.

**When useful:** Useful when exact topology matters or the simple estimate is not enough.


## Smart Devices

The Smart Devices hub stores paired Rust+ entity IDs and performs grouped status and control operations.

**When useful:** Use it to monitor or control supported switches, alarms, storage monitors, and other Rust+ entities from one place.

### Saved devices

Stores entity ID, name, zone, and favorite status separately for each server.

**When useful:** Useful for turning numeric entity IDs into a readable device list.

### Status reads

Reads selected or all devices in one Rust+ socket session.

**When useful:** Useful for checking state, capacity, protection, expiration, and API errors.

### Batch control

Turns selected controllable entities on or off together.

**When useful:** Useful for grouped lights, defenses, doors, or alarm systems when the Rust+ API supports control.

### Favorites and zones

Sorts important devices first and groups them by room or purpose.

**When useful:** Useful in bases with many paired devices.


## Saved Servers

Saved Servers manages offline server archives, pairing metadata, cached maps, and per-server workspace data.

**When useful:** Use it to reopen a server with Rust closed, remove an obsolete profile, or inspect what the app has saved.

### Open saved profile

Loads cached server, team, map, shop, timeline, and workspace data.

**When useful:** Useful when Rust is closed or live Rust+ is temporarily unavailable.

### Remove one or all

Deletes selected profile metadata and associated cached assets.

**When useful:** Useful after leaving a server or clearing old data.

### Automatic retention

Removes profiles with no live update for 30 days.

**When useful:** Useful for keeping the archive from accumulating abandoned servers.


## Notes

Notes provides a server-aware place to record plans, reminders, codes, routes, and other information that Rust+ does not supply.

**When useful:** Use it for raid plans, build tasks, teammate reminders, shopping lists, or anything that should remain with the companion workspace.

### Persistent notes

Stores written information in the app's local data.

**When useful:** Useful for information you need across multiple play sessions.

### Manual context

Complements automated Rust+ information with details only the player knows.

**When useful:** Useful for plans, agreements, and observations that cannot be detected automatically.
