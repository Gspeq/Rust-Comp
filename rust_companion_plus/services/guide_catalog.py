from __future__ import annotations

from dataclasses import dataclass


GUIDE_VERSION = "0.7.0"
GUIDE_LAST_UPDATED = "2026-07-22"


@dataclass(frozen=True, slots=True)
class GuideFeature:
    name: str
    description: str
    useful_when: str


@dataclass(frozen=True, slots=True)
class GuideSection:
    name: str
    summary: str
    useful_when: str
    features: tuple[GuideFeature, ...]


GUIDE_SECTIONS: dict[str, GuideSection] = {
    "Overview": GuideSection(
        name="Overview",
        summary=(
            "The Dashboard combines connection status, Rust+ pairing, server "
            "intelligence, marketplace notification settings, and the live event timeline."
        ),
        useful_when=(
            "Use it first when opening the app, changing servers, checking whether "
            "Rust+ is live, or changing marketplace alert behavior."
        ),
        features=(
            GuideFeature(
                "Server metrics",
                "Shows server name, population, detected game endpoint, and last update.",
                "Useful for confirming that the app is reading the intended server.",
            ),
            GuideFeature(
                "Rust+ pairing",
                "Stores the companion host, app port, Steam ID, and player token for the active server.",
                "Useful after pairing a server or when repairing an incomplete profile.",
            ),
            GuideFeature(
                "Connect and refresh",
                "Requests a fresh Rust+ snapshot using the currently saved pairing profile.",
                "Useful when cached information is visible but live data has not connected.",
            ),
            GuideFeature(
                "Re-detect server",
                "Rechecks the running Rust process, logs, sockets, and public server metadata.",
                "Useful after joining a different server or when the detected endpoint looks wrong.",
            ),
            GuideFeature(
                "Marketplace notifications",
                "Controls alert level, sound, popup duration, repeat suppression, and alerts per scan.",
                "Useful when tuning how often STEAL, CAN'T MISS, and possible listing-error alerts appear.",
            ),
            GuideFeature(
                "Server intelligence",
                "Explains why the endpoint was selected and shows accepted, rejected, and public evidence.",
                "Useful for troubleshooting server detection or Rust+ endpoint differences.",
            ),
            GuideFeature(
                "Live timeline",
                "Records population, team, event, detection, and Rust+ changes.",
                "Useful for reviewing what changed while using other tabs.",
            ),
        ),
    ),
    "Map": GuideSection(
        name="Map",
        summary=(
            "Map Intelligence combines the server map, Rust+ markers, optional resource "
            "analysis, zoom controls, and starter-base recommendations."
        ),
        useful_when=(
            "Use it while planning routes, deciding where to build, locating shops or "
            "events, and comparing resource access against player traffic."
        ),
        features=(
            GuideFeature(
                "Live and cached map",
                "Uses the current Rust+ map when available and saved map assets when offline.",
                "Useful for planning with Rust closed or during a temporary Rust+ outage.",
            ),
            GuideFeature(
                "Zoom and recenter",
                "Supports fit and fixed zoom levels, mouse-wheel zoom, and click-to-center.",
                "Useful when inspecting a specific grid or shop location.",
            ),
            GuideFeature(
                "Server icon visibility",
                "Shows or hides Rust+ map markers without removing the underlying data.",
                "Useful when markers obscure terrain or resource overlays.",
            ),
            GuideFeature(
                "Resource overlays",
                "Displays parsed or estimated resource and terrain layers when available.",
                "Useful for comparing stone, metal, sulfur, roads, water, and biome access.",
            ),
            GuideFeature(
                "Starter spot recommendation",
                "Scores candidate areas using resources, roads, terrain, water, monuments, events, shops, and edge risk.",
                "Useful at wipe start or after relocating; it is a planning estimate, not a safety guarantee.",
            ),
        ),
    ),
    "Team": GuideSection(
        name="Team",
        summary=(
            "Team Intelligence turns Rust+ team positions and status changes into a "
            "readable operational view."
        ),
        useful_when=(
            "Use it to check who is online or alive, find isolated teammates, review "
            "recent deaths, and understand nearby map context."
        ),
        features=(
            GuideFeature(
                "Team status",
                "Shows online, alive, position, and last-known state for Rust+ team members.",
                "Useful before roaming or coordinating a return to base.",
            ),
            GuideFeature(
                "Distance and isolation",
                "Compares teammate positions and identifies members far from the group.",
                "Useful for finding separated teammates or deciding who needs support.",
            ),
            GuideFeature(
                "Monument context",
                "Associates team positions with nearby named monuments when exact map data exists.",
                "Useful when teammates report only their map position.",
            ),
            GuideFeature(
                "My last deaths",
                "Stores recent automatic Rust+ alive-to-dead transitions for the local player.",
                "Useful for returning to an approximate death area.",
            ),
        ),
    ),
    "Shops": GuideSection(
        name="Shops",
        summary=(
            "The marketplace searches Rust+ vending listings, compares equivalent trades, "
            "rates deals in plain text, and maps matching shop locations."
        ),
        useful_when=(
            "Use it when buying or selling items, checking whether a price is unusual, or "
            "finding the closest shop offering a specific trade."
        ),
        features=(
            GuideFeature(
                "Buy, payment, and location searches",
                "Filters the item being sold, the requested payment item, and shop/grid text.",
                "Useful for narrowing a large marketplace without hiding important columns.",
            ),
            GuideFeature(
                "BP marking",
                "Blueprint listings stay visible and are prefixed with BP in the sold or payment item field.",
                "Useful for avoiding confusion between a blueprint and the crafted item.",
            ),
            GuideFeature(
                "Best value",
                "Ranks equivalent trades using unit price, live peers, rolling history, stock, rank, confidence, and robust outlier detection.",
                "Useful for finding strong offers without comparing unrelated currencies or blueprint states.",
            ),
            GuideFeature(
                "Deal ratings",
                "Labels listings as possible error, can't miss, steal, good value, fair, overpriced, unpriced, or out of stock.",
                "Useful for understanding the recommendation without relying on row color.",
            ),
            GuideFeature(
                "Advanced limits",
                "Optionally limits results by minimum stock or maximum total cost.",
                "Useful after the basic searches already identify the desired market.",
            ),
            GuideFeature(
                "Shop minimap",
                "Shows the selected shop and other matching locations on a focused map.",
                "Useful for choosing between several comparable offers.",
            ),
            GuideFeature(
                "Marketplace alerts",
                "Sends new high-value or possible listing-error notices in-app and through Windows notifications.",
                "Useful while Rust is fullscreen or while viewing another app tab.",
            ),
        ),
    ),
    "Electrical": GuideSection(
        name="Electrical",
        summary=(
            "Electrical Planner offers a fast natural-language power estimate and a complete "
            "advanced circuit workspace."
        ),
        useful_when=(
            "Use it before building a circuit, when diagnosing insufficient power, or when "
            "planning batteries and generation for a base."
        ),
        features=(
            GuideFeature(
                "Simple Planner",
                "Parses common Rust electrical components from a written description and estimates load, generation, storage, and runtime.",
                "Useful for quick plans without drawing every wire.",
            ),
            GuideFeature(
                "Recommendations",
                "Highlights generation shortages, battery limits, excess capacity, and likely substitutions.",
                "Useful for correcting a plan before spending resources.",
            ),
            GuideFeature(
                "Advanced Circuit",
                "Preserves the visual circuit editor, wiring paths, branch analysis, loop detection, disconnected-load checks, and saved layouts.",
                "Useful when exact topology matters or the simple estimate is not enough.",
            ),
        ),
    ),
    "Smart Devices": GuideSection(
        name="Smart Devices",
        summary=(
            "The Smart Devices hub stores paired Rust+ entity IDs and performs grouped "
            "status and control operations."
        ),
        useful_when=(
            "Use it to monitor or control supported switches, alarms, storage monitors, and "
            "other Rust+ entities from one place."
        ),
        features=(
            GuideFeature(
                "Saved devices",
                "Stores entity ID, name, zone, and favorite status separately for each server.",
                "Useful for turning numeric entity IDs into a readable device list.",
            ),
            GuideFeature(
                "Status reads",
                "Reads selected or all devices in one Rust+ socket session.",
                "Useful for checking state, capacity, protection, expiration, and API errors.",
            ),
            GuideFeature(
                "Batch control",
                "Turns selected controllable entities on or off together.",
                "Useful for grouped lights, defenses, doors, or alarm systems when the Rust+ API supports control.",
            ),
            GuideFeature(
                "Favorites and zones",
                "Sorts important devices first and groups them by room or purpose.",
                "Useful in bases with many paired devices.",
            ),
        ),
    ),
    "Saved Servers": GuideSection(
        name="Saved Servers",
        summary=(
            "Saved Servers manages offline server archives, pairing metadata, cached maps, "
            "and per-server workspace data."
        ),
        useful_when=(
            "Use it to reopen a server with Rust closed, remove an obsolete profile, or "
            "inspect what the app has saved."
        ),
        features=(
            GuideFeature(
                "Open saved profile",
                "Loads cached server, team, map, shop, timeline, and workspace data.",
                "Useful when Rust is closed or live Rust+ is temporarily unavailable.",
            ),
            GuideFeature(
                "Remove one or all",
                "Deletes selected profile metadata and associated cached assets.",
                "Useful after leaving a server or clearing old data.",
            ),
            GuideFeature(
                "Automatic retention",
                "Removes profiles with no live update for 30 days.",
                "Useful for keeping the archive from accumulating abandoned servers.",
            ),
        ),
    ),
    "Notes": GuideSection(
        name="Notes",
        summary=(
            "Notes provides a server-aware place to record plans, reminders, codes, routes, "
            "and other information that Rust+ does not supply."
        ),
        useful_when=(
            "Use it for raid plans, build tasks, teammate reminders, shopping lists, or "
            "anything that should remain with the companion workspace."
        ),
        features=(
            GuideFeature(
                "Persistent notes",
                "Stores written information in the app's local data.",
                "Useful for information you need across multiple play sessions.",
            ),
            GuideFeature(
                "Manual context",
                "Complements automated Rust+ information with details only the player knows.",
                "Useful for plans, agreements, and observations that cannot be detected automatically.",
            ),
        ),
    ),
}


def render_section(name: str) -> str:
    section = GUIDE_SECTIONS.get(name) or GUIDE_SECTIONS["Overview"]
    lines = [
        section.name,
        "=" * len(section.name),
        "",
        section.summary,
        "",
        "WHEN THIS TAB IS USEFUL",
        section.useful_when,
        "",
        "FEATURES",
    ]
    for feature in section.features:
        lines.extend(
            (
                "",
                feature.name,
                "-" * len(feature.name),
                feature.description,
                f"When useful: {feature.useful_when}",
            )
        )
    return "\n".join(lines)


def render_guide_markdown() -> str:
    lines = [
        "# Rust Companion+ Feature Guide",
        "",
        f"Guide version: {GUIDE_VERSION}",
        f"Last updated: {GUIDE_LAST_UPDATED}",
        "",
        (
            "This file is generated from the same guide catalog used by the "
            "in-application Guide button. Update the catalog whenever a tab or "
            "feature changes, then regenerate this document."
        ),
    ]
    for name in GUIDE_SECTIONS:
        section = GUIDE_SECTIONS[name]
        lines.extend(
            (
                "",
                f"## {section.name}",
                "",
                section.summary,
                "",
                f"**When useful:** {section.useful_when}",
                "",
            )
        )
        for feature in section.features:
            lines.extend(
                (
                    f"### {feature.name}",
                    "",
                    feature.description,
                    "",
                    f"**When useful:** {feature.useful_when}",
                    "",
                )
            )
    return "\n".join(lines).rstrip() + "\n"
