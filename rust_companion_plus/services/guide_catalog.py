from __future__ import annotations

from dataclasses import dataclass


GUIDE_VERSION = "0.8.0"
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
            "The Dashboard combines server status, Rust+ pairing, the complete "
            "feature guide, marketplace notification presets, intelligence, and "
            "the live event timeline."
        ),
        useful_when=(
            "Use it first after launch, when changing servers, configuring alerts, "
            "or learning what another page can do."
        ),
        features=(
            GuideFeature(
                "Feature Guide",
                "The Dashboard-only Guide button opens this maintained catalog for every tab and major feature.",
                "Useful when setting up a system for the first time or checking limitations before relying on it.",
            ),
            GuideFeature(
                "Server metrics",
                "Shows server name, population, detected endpoint, and the latest refresh time.",
                "Useful for confirming that the intended live or saved server is active.",
            ),
            GuideFeature(
                "Rust+ pairing",
                "Stores the companion host, app port, Steam ID, and player token for the active server profile.",
                "Useful after pairing or when repairing an incomplete server-specific profile.",
            ),
            GuideFeature(
                "Marketplace notification presets",
                "Filters alerts by All, Basic, Mid tier, High tier, Endgame, or custom watched items, plus rating, stock, cost, blueprint, sound, repeat, Windows, and in-app settings.",
                "Useful for matching alerts to your current wipe progression and avoiding irrelevant notifications.",
            ),
            GuideFeature(
                "Server intelligence and timeline",
                "Explains endpoint evidence and records Rust+, population, team, smart-device, and world-event changes.",
                "Useful for troubleshooting and reviewing what changed while another page was open.",
            ),
        ),
    ),
    "Map": GuideSection(
        name="Map",
        summary=(
            "Map Intelligence combines live or cached maps, interactive zoom and pan, "
            "server-marker visibility, multiple quick overlays, and starter-base analysis."
        ),
        useful_when=(
            "Use it for route planning, build-location comparison, resource access, and inspecting a specific area."
        ),
        features=(
            GuideFeature(
                "Zoom and pan",
                "Use Fit through 8x zoom, +/- controls, the mouse wheel, drag-to-pan, and double-click recentering.",
                "Useful when a full-map view is too small to inspect terrain or a specific grid.",
            ),
            GuideFeature(
                "Marker toggle",
                "Shows or hides Rust+ server icons without deleting marker data.",
                "Useful when vending, event, or team icons obscure terrain.",
            ),
            GuideFeature(
                "Quick overlay toggles",
                "Allows several commonly useful resource, road, water, and monument layers to be enabled together while retaining the detailed layer selector.",
                "Useful for comparing competing location factors in one map view.",
            ),
            GuideFeature(
                "Starter spot recommendation",
                "Scores candidate areas using resources, roads, terrain, water, monuments, events, shops, and map-edge risk, then zooms to the strongest estimate.",
                "Useful at wipe start or after relocating; it is not a player-safety guarantee.",
            ),
        ),
    ),
    "Team": GuideSection(
        name="Team",
        summary=(
            "Team Intelligence turns Rust+ team states and positions into a readable operational view and stores the local player's latest death positions."
        ),
        useful_when=(
            "Use it for teammate coordination, isolation checks, and returning toward a recent death location."
        ),
        features=(
            GuideFeature(
                "Team status and isolation",
                "Shows online/alive state, last position, distances, and separated teammates.",
                "Useful before roaming or deciding who needs support.",
            ),
            GuideFeature(
                "Latest deaths",
                "Detects the local player's Rust+ alive-to-dead transition on a one-second snapshot cadence and stores the last known pre-death coordinates.",
                "Useful for recovery routes; the position remains approximate because Rust+ reports snapshots rather than an exact death packet.",
            ),
            GuideFeature(
                "Monument context",
                "Associates team positions with named monuments when exact parsed map metadata is available.",
                "Useful when a teammate reports only a position or vague landmark.",
            ),
        ),
    ),
    "Shops": GuideSection(
        name="Shops",
        summary=(
            "The marketplace searches Rust+ vending offers, marks blueprints, rates equivalent trades in text, sends configurable alerts, and shows the selected shop's exact grid cell."
        ),
        useful_when=(
            "Use it when buying or selling, watching progression-specific loot, or checking whether a price is unusually strong."
        ),
        features=(
            GuideFeature(
                "Compact listings and BP marking",
                "Important columns fit without sideways scrolling, and blueprint items are visibly prefixed with BP.",
                "Useful for avoiding blueprint/item confusion while scanning many offers.",
            ),
            GuideFeature(
                "Best Value",
                "Compares normalized unit cost only within identical item, payment, and blueprint markets using live peers, rolling history, stock, rank, confidence, and robust outlier detection.",
                "Useful for finding strong deals without comparing unrelated trades.",
            ),
            GuideFeature(
                "Fixed grid map",
                "Selecting an offer shows only that shop's grid section at a fixed zoom with one shop marker and no unrelated icons.",
                "Useful for recognizing the immediate terrain around the destination without a cluttered full map.",
            ),
            GuideFeature(
                "Loot and item alerts",
                "Dashboard settings can filter by progression preset, specific item names or IDs, any-listing watches, minimum stock, maximum cost, blueprints, deal rating, and delivery path.",
                "Useful while Rust is fullscreen or while waiting for a rare item to appear.",
            ),
        ),
    ),
    "Electrical": GuideSection(
        name="Electrical",
        summary=(
            "Electrical opens directly into the complete visual circuit designer. The former basic planner has been removed and its power-balance information remains integrated into the canvas metrics and recommendations."
        ),
        useful_when=(
            "Use it before building, while diagnosing a circuit, or when hardening an endgame defense and automation network."
        ),
        features=(
            GuideFeature(
                "Visual circuit designer",
                "Drag or click equipment, wire outputs to inputs, arrange nodes, edit quantity/state/zone, and save the complete circuit.",
                "Useful whenever topology matters instead of only component totals.",
            ),
            GuideFeature(
                "Integrated power model",
                "Shows load, peak and average generation, battery storage/output, no-generation runtime, and charging headroom directly above the canvas.",
                "Useful for determining whether a circuit works through night, weather, or generator loss.",
            ),
            GuideFeature(
                "Strategic suggestions",
                "Adds topology fixes plus redundancy, branch priority, turret isolation, Smart Alarm, Storage Monitor, production timer, zone isolation, and single-point-failure advice.",
                "Useful for turning a merely powered circuit into a maintainable and raid-resistant system.",
            ),
        ),
    ),
    "Smart Devices": GuideSection(
        name="Smart Devices",
        summary=(
            "Smart Base Control turns paired Rust+ entities into named devices, logical systems, verified scenes, local rules, and an activity log."
        ),
        useful_when=(
            "Use it to operate defense zones, lights, lockdown circuits, industry, alarms, and storage monitors from one console."
        ),
        features=(
            GuideFeature(
                "Devices",
                "Stores entity ID, name, zone, role, logical system, favorite state, and the latest Rust+ status fields; supports batch refresh and ON/OFF.",
                "Useful for replacing raw entity IDs with an organized base-control inventory.",
            ),
            GuideFeature(
                "Systems",
                "Groups selected devices into a named zone or purpose such as North Defense, Core Lights, or Furnace Bank, then refreshes or controls the whole group.",
                "Useful for maintenance and logical control without selecting individual entities every time.",
            ),
            GuideFeature(
                "Scenes",
                "Stores multi-device ON/OFF states such as Raid Mode, Offline Mode, Quiet Mode, Industry Mode, or Emergency Lockdown, with preview, confirmation, and post-run verification.",
                "Useful for changing many circuits safely with one action.",
            ),
            GuideFeature(
                "Rules and activity",
                "Evaluates value transitions, capacity thresholds, status changes, and entity errors after refresh; rules can notify or run a scene when explicitly armed and respect cooldowns.",
                "Useful for low-ammo/storage warnings and controlled local automation. Rules only run while the app and Rust+ connection are active.",
            ),
        ),
    ),
    "Saved Servers": GuideSection(
        name="Saved Servers",
        summary=(
            "Saved Servers manages offline server archives, pairing metadata, cached maps, and server-specific workspace data."
        ),
        useful_when=(
            "Use it to reopen cached data with Rust closed or remove profiles for servers you no longer play."
        ),
        features=(
            GuideFeature(
                "Open saved profile",
                "Loads cached server, team, map, shop, timeline, electrical, and smart-control workspace data.",
                "Useful during a Rust+ outage or with Rust closed.",
            ),
            GuideFeature(
                "Delete and retention",
                "Removes one or all saved profiles and automatically purges profiles with no live update for 30 days.",
                "Useful for keeping credentials and cached assets limited to current servers.",
            ),
        ),
    ),
    "Notes": GuideSection(
        name="Notes",
        summary=(
            "Notes stores server-aware plans, reminders, routes, tasks, and observations that Rust+ cannot provide."
        ),
        useful_when=(
            "Use it for build tasks, raid plans, teammate reminders, shopping lists, or manual intelligence."
        ),
        features=(
            GuideFeature(
                "Persistent notes",
                "Keeps written information in local application data and the active server workspace.",
                "Useful for details needed across multiple sessions.",
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
            "This file is generated from the same catalog opened by the "
            "Dashboard Feature Guide button. Update the catalog whenever a tab "
            "or feature changes, then regenerate this document."
        ),
    ]
    for section in GUIDE_SECTIONS.values():
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
