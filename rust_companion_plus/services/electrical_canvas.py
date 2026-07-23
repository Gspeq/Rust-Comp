from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable


ELECTRICAL_ZOOM_LEVELS = (0.50, 0.67, 0.80, 1.00, 1.25, 1.50, 2.00)

ASSUMPTION_HELP_TEXT = """Solar average %
The long-run share of each panel's rated peak output used for planning. It accounts for night, sun angle, shadows, and imperfect placement. It is not the panel's current output.

Wind average %
The long-run share of a turbine's 150 rW peak used by the planner. Height and terrain change real output, so a conservative value avoids overestimating your base.

Battery charge %
The share of incoming generation assumed to become stored energy after charging losses. It affects charge time and usable average generation, not the battery's maximum output.

Planner formulas
Usable average = average generation × battery charge efficiency.
No-generation runtime = stored rW-minutes ÷ active load.
Peak margin = raw peak generation − the peak input needed for load and charging."""


def clamp_zoom(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 1.0
    return min(
        ELECTRICAL_ZOOM_LEVELS,
        key=lambda candidate: abs(candidate - numeric),
    )


def zoom_label(value: Any) -> str:
    return f"{round(clamp_zoom(value) * 100):d}%"


def _node_map(nodes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("id")): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }


def _rect(
    node: dict[str, Any],
    node_width: float,
    node_height: float,
    clearance: float,
) -> tuple[float, float, float, float]:
    x = float(node.get("x", 0))
    y = float(node.get("y", 0))
    return (
        x - clearance,
        y - clearance,
        x + node_width + clearance,
        y + node_height + clearance,
    )


def _segment_hits_rect(
    a: tuple[float, float],
    b: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x1, y1, x2, y2 = rect
    ax, ay = a
    bx, by = b
    if abs(ax - bx) < 1e-9:
        x = ax
        low, high = sorted((ay, by))
        return x1 < x < x2 and max(low, y1) < min(high, y2)
    if abs(ay - by) < 1e-9:
        y = ay
        low, high = sorted((ax, bx))
        return y1 < y < y2 and max(low, x1) < min(high, x2)
    return True


def _route_is_clear(
    points: list[tuple[float, float]],
    obstacles: list[tuple[float, float, float, float]],
) -> bool:
    for start, end in zip(points, points[1:]):
        for obstacle in obstacles:
            if _segment_hits_rect(start, end, obstacle):
                return False
    return True


def _simplify(points: list[tuple[float, float]]) -> tuple[float, ...]:
    compact: list[tuple[float, float]] = []
    for point in points:
        if compact and point == compact[-1]:
            continue
        compact.append(point)

    changed = True
    while changed and len(compact) >= 3:
        changed = False
        reduced = [compact[0]]
        for index in range(1, len(compact) - 1):
            previous = reduced[-1]
            current = compact[index]
            following = compact[index + 1]
            if (
                abs(previous[0] - current[0]) < 1e-9
                and abs(current[0] - following[0]) < 1e-9
            ) or (
                abs(previous[1] - current[1]) < 1e-9
                and abs(current[1] - following[1]) < 1e-9
            ):
                changed = True
                continue
            reduced.append(current)
        reduced.append(compact[-1])
        compact = reduced

    flattened: list[float] = []
    for x, y in compact:
        flattened.extend((round(x, 3), round(y, 3)))
    return tuple(flattened)


def orthogonal_connection_points(
    nodes: Iterable[dict[str, Any]],
    connection: dict[str, Any],
    *,
    node_width: float = 166,
    node_height: float = 68,
    lane_index: int = 0,
    clearance: float = 18,
) -> tuple[float, ...] | None:
    """Return a deterministic right-angle route that avoids other nodes."""
    node_by_id = _node_map(nodes)
    source_id = str(connection.get("source", ""))
    target_id = str(connection.get("target", ""))
    source = node_by_id.get(source_id)
    target = node_by_id.get(target_id)
    if source is None or target is None or source_id == target_id:
        return None

    sx = float(source.get("x", 0)) + node_width
    sy = float(source.get("y", 0)) + node_height / 2
    tx = float(target.get("x", 0))
    ty = float(target.get("y", 0)) + node_height / 2
    stub = max(24.0, clearance + 6.0)
    lane_shift = ((int(lane_index) % 9) - 4) * 9.0

    obstacles = [
        _rect(node, node_width, node_height, clearance)
        for node_id, node in node_by_id.items()
        if node_id not in {source_id, target_id}
    ]

    candidates: list[list[tuple[float, float]]] = []
    if tx >= sx + stub * 2:
        midpoint = (sx + tx) / 2 + lane_shift
        offsets = (0, 32, -32, 64, -64, 96, -96, 128, -128)
        for offset in offsets:
            mx = min(tx - stub, max(sx + stub, midpoint + offset))
            candidates.append(
                [
                    (sx, sy),
                    (sx + stub, sy),
                    (mx, sy),
                    (mx, ty),
                    (tx - stub, ty),
                    (tx, ty),
                ]
            )

    all_nodes = list(node_by_id.values())
    upper = min(
        [float(node.get("y", 0)) for node in all_nodes] + [sy, ty]
    )
    lower = max(
        [
            float(node.get("y", 0)) + node_height
            for node in all_nodes
        ]
        + [sy, ty]
    )
    detour_spacing = 24.0 + abs(lane_shift)
    top_y = upper - clearance - 42.0 - detour_spacing
    bottom_y = lower + clearance + 42.0 + detour_spacing

    detours = (
        (bottom_y, top_y)
        if tx < sx
        else (top_y, bottom_y)
    )
    for detour_y in detours:
        candidates.append(
            [
                (sx, sy),
                (sx + stub, sy),
                (sx + stub, detour_y),
                (tx - stub, detour_y),
                (tx - stub, ty),
                (tx, ty),
            ]
        )

    for points in candidates:
        if _route_is_clear(points, obstacles):
            return _simplify(points)
    return _simplify(candidates[-1])


def graph_layout_positions(
    nodes: Iterable[dict[str, Any]],
    connections: Iterable[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    *,
    canvas_width: float = 2600,
    canvas_height: float = 1600,
    node_width: float = 166,
    node_height: float = 68,
) -> dict[str, tuple[float, float]]:
    """Lay out a circuit by actual signal depth, with stable cycle fallbacks."""
    node_by_id = _node_map(nodes)
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)

    for connection in connections:
        source = str(connection.get("source", ""))
        target = str(connection.get("target", ""))
        if source in node_by_id and target in node_by_id and source != target:
            outgoing[source].add(target)
            incoming[target].add(source)

    indegree = {
        node_id: len(incoming[node_id])
        for node_id in node_by_id
    }
    queue = deque(
        sorted(
            (node_id for node_id, degree in indegree.items() if degree == 0),
            key=lambda node_id: str(
                node_by_id[node_id].get("component", "")
            ).casefold(),
        )
    )
    depth = {node_id: 0 for node_id in queue}
    processed: set[str] = set()

    while queue:
        current = queue.popleft()
        processed.add(current)
        for target in sorted(outgoing[current]):
            depth[target] = max(
                depth.get(target, 0),
                depth.get(current, 0) + 1,
            )
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    special_rank = {
        "root combiner": 1,
        "large rechargeable battery": 2,
        "medium rechargeable battery": 2,
        "small rechargeable battery": 2,
        "electrical branch": 3,
        "splitter": 3,
        "blocker": 3,
        "smart switch": 4,
        "timer": 4,
    }
    category_rank = {
        "generation": 0,
        "storage": 1,
        "control": 2,
        "logic": 2,
        "utility": 2,
        "load": 4,
    }
    for node_id, node in node_by_id.items():
        if node_id in processed:
            continue
        component = str(node.get("component", "")).casefold()
        category = str(
            catalog.get(str(node.get("component", "")), {}).get(
                "category",
                "utility",
            )
        ).casefold()
        depth[node_id] = special_rank.get(
            component,
            category_rank.get(category, 2),
        )

    columns: dict[int, list[str]] = defaultdict(list)
    for node_id in node_by_id:
        columns[int(depth.get(node_id, 0))].append(node_id)

    result: dict[str, tuple[float, float]] = {}
    x_spacing = max(230.0, node_width + 84.0)
    y_spacing = max(96.0, node_height + 34.0)
    for display_column, logical_depth in enumerate(sorted(columns)):
        ordered = sorted(
            columns[logical_depth],
            key=lambda node_id: (
                str(node_by_id[node_id].get("zone", "")).casefold(),
                str(node_by_id[node_id].get("component", "")).casefold(),
                node_id,
            ),
        )
        for row_index, node_id in enumerate(ordered):
            x = 70.0 + display_column * x_spacing
            y = 65.0 + row_index * y_spacing
            result[node_id] = (
                min(max(8.0, x), canvas_width - node_width - 8.0),
                min(max(8.0, y), canvas_height - node_height - 8.0),
            )
    return result
