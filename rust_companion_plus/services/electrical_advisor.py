from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any


CRITICAL_LOAD_NAMES = {
    "Auto Turret",
    "SAM Site",
    "HBHF Sensor",
    "Seismic Sensor",
    "Smart Alarm",
    "Door Controller",
}
DEFENSE_NAMES = {
    "Auto Turret",
    "SAM Site",
    "Search Light",
    "Siren Light",
    "Smart Alarm",
    "HBHF Sensor",
    "Seismic Sensor",
}
ROUTING_NAMES = {
    "Electrical Branch",
    "Splitter",
    "Root Combiner",
    "Blocker",
    "OR Switch",
    "AND Switch",
    "XOR Switch",
    "Memory Cell",
    "Timer",
    "Smart Switch",
}


def _active_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in nodes
        if str(row.get("state", "Planned")).casefold()
        in {"placed", "planned"}
    ]


def _quantity(node: dict[str, Any]) -> int:
    try:
        return max(1, int(node.get("quantity", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _component(node: dict[str, Any]) -> str:
    return str(node.get("component") or "")


def strategic_recommendations(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
) -> list[str]:
    """Add endgame reliability, isolation, and maintainability suggestions."""
    active = _active_nodes(nodes)
    if not active:
        return []

    counts = Counter()
    zones: dict[str, Counter[str]] = defaultdict(Counter)
    node_by_id: dict[str, dict[str, Any]] = {}
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)

    for node in active:
        name = _component(node)
        quantity = _quantity(node)
        counts[name] += quantity
        zones[str(node.get("zone") or "Main")][name] += quantity
        node_id = str(node.get("id") or "")
        if node_id:
            node_by_id[node_id] = node

    for edge in connections:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in node_by_id and target in node_by_id and source != target:
            outgoing[source].append(target)
            incoming[target].append(source)

    suggestions: list[str] = []
    generators = sum(
        quantity
        for name, quantity in counts.items()
        if str(catalog.get(name, {}).get("category", "")).casefold()
        == "generation"
    )
    batteries = sum(
        quantity
        for name, quantity in counts.items()
        if str(catalog.get(name, {}).get("category", "")).casefold()
        == "storage"
    )
    critical_count = sum(counts[name] for name in CRITICAL_LOAD_NAMES)
    defense_count = sum(counts[name] for name in DEFENSE_NAMES)

    if critical_count and batteries == 0:
        suggestions.append(
            "[Fix] Critical defense/control loads have no battery storage. "
            "Add protected storage so night, weather, or generator loss does not "
            "drop the circuit immediately."
        )
    elif critical_count >= 4 and batteries == 1:
        suggestions.append(
            "[Optimize] Several critical loads depend on one battery bank. "
            "Split defense into at least two independently protected buses so one "
            "destroyed battery or branch cannot disable everything."
        )

    if generators == 1 and critical_count >= 4:
        suggestions.append(
            "[Optimize] This defense-heavy circuit has one generation source. "
            "Add a second source type or a separately routed backup to reduce a "
            "single-point failure."
        )

    if counts["Auto Turret"] >= 2 and counts["Electrical Branch"] == 0:
        suggestions.append(
            "[Fix] Multiple Auto Turrets are present without Electrical Branches. "
            "Give each turret or turret group a fixed allocation and avoid equal "
            "splitters when downstream demand differs."
        )

    if defense_count and counts["Smart Switch"] == 0:
        suggestions.append(
            "[Optimize] Add Smart Switch isolation ahead of logical defense zones. "
            "That enables safe maintenance, remote raid/offline scenes, and power "
            "shedding without disabling unrelated circuits."
        )

    if counts["Auto Turret"] and counts["Smart Alarm"] == 0:
        suggestions.append(
            "[Optimize] Turrets are present without a Smart Alarm. Route Has Target, "
            "Low Ammo, or No Ammo outputs through alarm logic so the Smart Devices "
            "panel can provide meaningful defense events."
        )

    if counts["Storage Monitor"] == 0 and (
        counts["Auto Turret"] >= 2
        or counts["Industrial Conveyor"] >= 2
    ):
        suggestions.append(
            "[Info] Consider Storage Monitors on turret-ammo reserves and critical "
            "industrial input/output boxes so low-capacity rules can warn before "
            "production or defense stops."
        )

    if counts["Splitter"] >= 3 and counts["Electrical Branch"] == 0:
        suggestions.append(
            "[Swap] The circuit relies heavily on Splitters. Use Electrical Branches "
            "for priority loads so optional lighting or industry cannot starve defense."
        )

    if counts["Timer"] == 0 and counts["Industrial Conveyor"] >= 2:
        suggestions.append(
            "[Info] A Timer can run conveyors, pumps, or furnace support in bounded "
            "cycles instead of leaving every production load active continuously."
        )

    # Detect critical loads that share the exact same immediate parent.
    critical_ids = {
        node_id
        for node_id, node in node_by_id.items()
        if _component(node) in CRITICAL_LOAD_NAMES
    }
    parent_groups: dict[str, list[str]] = defaultdict(list)
    for node_id in critical_ids:
        for parent in incoming[node_id]:
            parent_groups[parent].append(node_id)
    for parent, children in parent_groups.items():
        if len(children) >= 4:
            parent_name = _component(node_by_id[parent])
            suggestions.append(
                "[Optimize] "
                f"{len(children)} critical loads share one immediate {parent_name} "
                "output. Divide them across protected branches or buses so one broken "
                "wire/component does not remove the whole layer."
            )
            break

    # Check whether critical zones have any upstream switch/branch.
    for zone_name, zone_counts in zones.items():
        zone_critical = sum(
            zone_counts[name]
            for name in CRITICAL_LOAD_NAMES
        )
        if zone_critical >= 2 and not (
            zone_counts["Smart Switch"]
            or zone_counts["Electrical Branch"]
        ):
            suggestions.append(
                "[Optimize] "
                f"Zone {zone_name} contains {zone_critical} critical devices but no "
                "local Smart Switch or Electrical Branch. Add a named isolation point "
                "for maintenance and scene control."
            )
            break

    # Long path depth often means hidden power loss and fragile routing.
    roots = [
        node_id
        for node_id in node_by_id
        if not incoming[node_id]
    ]
    depth: dict[str, int] = {node_id: 0 for node_id in roots}
    queue: deque[str] = deque(roots)
    while queue:
        current = queue.popleft()
        for target in outgoing[current]:
            next_depth = depth[current] + 1
            if next_depth > depth.get(target, -1):
                depth[target] = next_depth
                queue.append(target)
    deepest = max(depth.values(), default=0)
    if deepest >= 8:
        suggestions.append(
            "[Info] The longest modeled power path crosses "
            f"{deepest} components. Review each routing component's own draw and "
            "consider shorter buses for critical loads."
        )

    return suggestions
