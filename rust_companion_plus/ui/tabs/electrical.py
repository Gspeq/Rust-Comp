from __future__ import annotations

import math
import tkinter as tk
from collections import defaultdict, deque
from tkinter import messagebox
from typing import Any
from uuid import uuid4

import customtkinter as ctk

from rust_companion_plus.catalog import electrical_catalog
from rust_companion_plus.models import ElectricalSetup, SetupComponent
from rust_companion_plus.services.electrical import analyze_setup
from rust_companion_plus.ui.common import ACCENT, DANGER, MUTED


CANVAS_STATE_KEY = "electrical_canvas_state_v2"
CANVAS_WIDTH = 2600
CANVAS_HEIGHT = 1600
NODE_WIDTH = 166
NODE_HEIGHT = 68
CONNECTOR_RADIUS = 5
GRID_SIZE = 32
NODE_INPUT_X = 0
NODE_OUTPUT_X = NODE_WIDTH
DEFAULT_ASSUMPTIONS = {
    "solar_utilization": 0.35,
    "wind_utilization": 0.55,
    "battery_charge_fraction": 1.0,
}

CATEGORY_ORDER = {
    "generation": 0,
    "storage": 1,
    "control": 2,
    "logic": 2,
    "utility": 2,
    "load": 3,
}

CATEGORY_LABELS = {
    "generation": "GENERATION",
    "storage": "STORAGE",
    "control": "CONTROL / ROUTING",
    "logic": "CONTROL / ROUTING",
    "utility": "CONTROL / ROUTING",
    "load": "LOADS",
}

CATEGORY_COLORS = {
    "generation": "#14532d",
    "storage": "#1e3a8a",
    "control": "#4c1d95",
    "logic": "#4c1d95",
    "utility": "#374151",
    "load": "#7c2d12",
}



def _node_category(node: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> str:
    row = catalog.get(str(node.get("component", "")), {})
    return str(row.get("category", "utility") or "utility").lower()



def setup_from_canvas(
    name: str,
    nodes: list[dict[str, Any]],
    assumptions: dict[str, float] | None = None,
) -> ElectricalSetup:
    """Build the existing analyzer model from visual-canvas nodes."""
    setup = ElectricalSetup(name=name or "Main Base")
    setup.assumptions = dict(DEFAULT_ASSUMPTIONS)
    setup.assumptions.update(assumptions or {})
    setup.components = [
        SetupComponent(
            component=str(node.get("component", "")),
            quantity=max(1, int(node.get("quantity", 1) or 1)),
            state=str(node.get("state", "Planned") or "Planned"),
            zone=str(node.get("zone", "Main") or "Main"),
            note=str(node.get("note", "") or ""),
        )
        for node in nodes
        if str(node.get("component", ""))
    ]
    return setup



def circuit_recommendations(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
) -> list[str]:
    """Return topology and part-choice recommendations for the visual circuit."""
    if not nodes:
        return ["[Info] Drag electrical equipment from the palette onto the circuit canvas."]

    active_nodes = [
        node
        for node in nodes
        if str(node.get("state", "Planned")).casefold() in {"placed", "planned"}
    ]
    node_by_id = {
        str(node.get("id")): node
        for node in active_nodes
        if node.get("id")
    }
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    valid_connections: list[tuple[str, str]] = []

    for connection in connections:
        source = str(connection.get("source", ""))
        target = str(connection.get("target", ""))
        if source in node_by_id and target in node_by_id and source != target:
            outgoing[source].append(target)
            incoming[target].append(source)
            valid_connections.append((source, target))

    def name(node_id: str) -> str:
        return str(node_by_id[node_id].get("component", "Component"))

    def demand(node_id: str) -> float:
        node = node_by_id[node_id]
        row = catalog.get(name(node_id), {})
        return (
            float(row.get("power_draw", 0) or 0)
            * max(1, int(node.get("quantity", 1) or 1))
        )

    source_ids = {
        node_id
        for node_id, node in node_by_id.items()
        if _node_category(node, catalog) in {"generation", "storage"}
    }
    generation_ids = {
        node_id
        for node_id, node in node_by_id.items()
        if _node_category(node, catalog) == "generation"
    }
    load_ids = {
        node_id
        for node_id, node in node_by_id.items()
        if _node_category(node, catalog) == "load"
    }
    root_ids = {
        node_id for node_id in node_by_id if name(node_id) == "Root Combiner"
    }

    recommendations: list[str] = []

    if not valid_connections and len(node_by_id) > 1:
        recommendations.append(
            "[Fix] No power paths are wired. Click an orange output, then a blue input."
        )

    unconnected_loads = [
        name(node_id)
        for node_id in sorted(load_ids)
        if not incoming[node_id]
    ]
    if unconnected_loads:
        preview = ", ".join(unconnected_loads[:4])
        suffix = "" if len(unconnected_loads) <= 4 else f" and {len(unconnected_loads) - 4} more"
        recommendations.append(f"[Fix] Connect power into: {preview}{suffix}.")

    idle_sources = [
        name(node_id)
        for node_id in sorted(source_ids)
        if not outgoing[node_id]
    ]
    if idle_sources:
        preview = ", ".join(idle_sources[:4])
        suffix = "" if len(idle_sources) <= 4 else f" and {len(idle_sources) - 4} more"
        recommendations.append(f"[Fix] These power sources have no output path: {preview}{suffix}.")

    reachable: set[str] = set()
    queue: deque[str] = deque(source_ids)
    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        queue.extend(outgoing[current])

    unreachable_loads = [
        name(node_id)
        for node_id in sorted(load_ids)
        if node_id not in reachable
    ]
    if source_ids and unreachable_loads:
        preview = ", ".join(unreachable_loads[:4])
        suffix = "" if len(unreachable_loads) <= 4 else f" and {len(unreachable_loads) - 4} more"
        recommendations.append(f"[Fix] No complete source-to-load path reaches: {preview}{suffix}.")

    # Rust devices generally accept one power input. Root combiners are the
    # intentional two-input exception in this simplified canvas.
    for node_id, sources in incoming.items():
        allowed_inputs = 2 if name(node_id) == "Root Combiner" else 1
        if len(sources) > allowed_inputs:
            recommendations.append(
                f"[Fix] {name(node_id)} has {len(sources)} incoming paths; "
                f"use a Root Combiner or separate buses instead of stacking inputs."
            )
            break

    for node_id, targets in outgoing.items():
        component = name(node_id)
        allowed_outputs = 3 if component == "Splitter" else 2 if component == "Electrical Branch" else 1
        if len(targets) > allowed_outputs:
            recommendations.append(
                f"[Fix] {component} fans into {len(targets)} paths but this part supports "
                f"{allowed_outputs}. Add another routing component."
            )
            break
        if len(targets) > 1 and component not in {"Splitter", "Electrical Branch"}:
            recommendations.append(
                f"[Fix] {component} directly feeds {len(targets)} paths. "
                "Insert a Splitter for equal feeds or an Electrical Branch for fixed priority."
            )
            break

    # Root combiners should only receive root-capable sources.
    for root_id in root_ids:
        bad_inputs = [
            name(source_id)
            for source_id in incoming[root_id]
            if _node_category(node_by_id[source_id], catalog)
            not in {"generation", "storage"}
        ]
        if bad_inputs:
            recommendations.append(
                f"[Fix] Root Combiner input should come from generators or batteries, not "
                f"{', '.join(bad_inputs[:3])}."
            )
            break
        if len(incoming[root_id]) > 2:
            recommendations.append(
                "[Fix] A Root Combiner accepts two inputs. Chain additional combiners for larger arrays."
            )
            break

    if len(generation_ids) > 1 and not any(len(incoming[root_id]) >= 2 for root_id in root_ids):
        recommendations.append(
            "[Optimize] Multiple generators are present. Combine root outputs through chained "
            "Root Combiners before the battery bus."
        )

    # A splitter divides evenly among connected outputs. Uneven direct loads
    # are better served by a configured branch.
    for node_id in node_by_id:
        component = name(node_id)
        targets = outgoing[node_id]
        target_demands = [demand(target) for target in targets if demand(target) > 0]
        if component == "Splitter":
            if len(targets) == 1:
                recommendations.append(
                    "[Swap] This Splitter uses only one output; remove it unless it is reserved for expansion."
                )
                break
            if len(target_demands) >= 2:
                smallest = min(target_demands)
                largest = max(target_demands)
                if smallest > 0 and largest > smallest * 1.35:
                    values = ", ".join(f"{value:.0f} rW" for value in target_demands[:3])
                    recommendations.append(
                        f"[Swap] Splitter outputs divide evenly, but its direct loads are {values}. "
                        "Use an Electrical Branch for unequal allocations."
                    )
                    break
        elif component == "Electrical Branch":
            if len(target_demands) == 2:
                smallest = min(target_demands)
                largest = max(target_demands)
                if largest - smallest <= max(1.0, largest * 0.15):
                    recommendations.append(
                        "[Swap] This Electrical Branch feeds nearly equal direct loads. "
                        "A Splitter is cleaner when both paths should receive equal power."
                    )
                    break

    for source, target in valid_connections:
        source_category = _node_category(node_by_id[source], catalog)
        target_category = _node_category(node_by_id[target], catalog)
        if target_category == "generation":
            recommendations.append(
                f"[Fix] Check the wire into {name(target)}; generation equipment starts a path "
                "rather than receiving normal power."
            )
            break
        if source_category == "load" and outgoing[source]:
            recommendations.append(
                f"[Fix] {name(source)} is a load, not a distribution source. Route power through "
                "a branch, splitter, switch, or battery bus."
            )
            break

    visiting: set[str] = set()
    visited: set[str] = set()

    def has_cycle(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in outgoing[node_id]:
            if has_cycle(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(has_cycle(node_id) for node_id in node_by_id):
        recommendations.append(
            "[Fix] The wiring contains a loop. Rust electrical paths should flow in one direction."
        )

    return recommendations


class CompactMetricCard(ctk.CTkFrame):
    """Dense metric card that keeps the circuit workspace visible."""

    def __init__(self, master, title: str):
        super().__init__(master, corner_radius=9, height=58)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=title,
            text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=(7, 0))

        self.value_label = ctk.CTkLabel(
            self,
            text="—",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="e",
        )
        self.value_label.grid(row=0, column=1, sticky="ew", padx=(4, 10), pady=(5, 0))

        self.detail_label = ctk.CTkLabel(
            self,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(size=9),
            anchor="w",
        )
        self.detail_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=10,
            pady=(0, 6),
        )

    def set(self, value: str, detail: str = "") -> None:
        self.value_label.configure(text=value)
        self.detail_label.configure(text=detail)


class ElectricalTab(ctk.CTkFrame):
    STATES = ["Placed", "Planned", "Inventory"]
    ZONES = ["Main", "Defense", "Living", "Farm", "Industrial", "External"]

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.catalog = electrical_catalog()

        self.nodes: list[dict[str, Any]] = []
        self.connections: list[dict[str, Any]] = []
        self.node_items: dict[str, dict[str, int]] = {}
        self.connection_items: dict[str, int] = {}
        self.selected_node_id: str | None = None
        self.selected_connection_id: str | None = None
        self.pending_source_id: str | None = None
        self.drag_node_id: str | None = None
        self.drag_offset = (0.0, 0.0)
        self.palette_drag: dict[str, Any] | None = None
        self._autosave_job: str | None = None
        self.assumptions = dict(DEFAULT_ASSUMPTIONS)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_metrics()
        self._build_workspace()
        self._build_recommendations()
        self._load_state()
        self._redraw_all()
        self.recalculate()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkFrame(header, fg_color="transparent")
        title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title,
            text="Electrical Circuit Designer",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title,
            text="Compact visual planner · drag equipment, then wire orange outputs to blue inputs.",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.name_entry = ctk.CTkEntry(header, width=180, height=30, placeholder_text="Circuit name")
        self.name_entry.grid(row=0, column=1, rowspan=2, padx=(8, 5))
        self.name_entry.bind("<KeyRelease>", lambda _event: self._schedule_autosave())

        ctk.CTkButton(header, text="New", width=72, height=30, command=self.new_circuit).grid(
            row=0, column=2, rowspan=2, padx=4
        )
        ctk.CTkButton(header, text="Arrange", width=78, height=30, command=self.auto_layout).grid(
            row=0, column=3, rowspan=2, padx=4
        )
        ctk.CTkButton(header, text="Clear wires", width=86, height=30, command=self.clear_wires).grid(
            row=0, column=4, rowspan=2, padx=4
        )
        ctk.CTkButton(
            header,
            text="Delete",
            width=72,
            height=30,
            command=self.delete_selected,
            fg_color=DANGER,
            hover_color="#b91c1c",
        ).grid(row=0, column=5, rowspan=2, padx=4)
        ctk.CTkButton(header, text="Save", width=64, height=30, command=self.save_circuit).grid(
            row=0, column=6, rowspan=2, padx=(4, 0)
        )

    def _build_metrics(self) -> None:
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        metrics.grid_columnconfigure(tuple(range(6)), weight=1)
        self.metric_cards: dict[str, CompactMetricCard] = {}
        definitions = [
            ("load", "Active load"),
            ("generation", "Peak generation"),
            ("average", "Usable average"),
            ("battery", "Battery storage"),
            ("runtime", "No-gen runtime"),
            ("headroom", "Usable peak margin"),
        ]
        for column, (key, title) in enumerate(definitions):
            card = CompactMetricCard(metrics, title)
            card.grid(row=0, column=column, sticky="nsew", padx=3)
            self.metric_cards[key] = card

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, corner_radius=12)
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, minsize=205)
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_columnconfigure(2, minsize=250)

        self._build_palette(workspace)
        self._build_canvas(workspace)
        self._build_inspector(workspace)

    def _build_palette(self, parent) -> None:
        palette = ctk.CTkFrame(parent, corner_radius=10)
        palette.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        palette.grid_columnconfigure(0, weight=1)
        palette.grid_rowconfigure(3, weight=1)

        heading = ctk.CTkFrame(palette, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=9, pady=(8, 4))
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            heading,
            text="Equipment",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            heading,
            text="drag or click to add",
            text_color=MUTED,
            font=ctk.CTkFont(size=9),
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        self.palette_search = ctk.CTkEntry(
            palette,
            height=28,
            placeholder_text="Search equipment…",
        )
        self.palette_search.grid(row=1, column=0, sticky="ew", padx=9, pady=(0, 5))
        self.palette_search.bind("<KeyRelease>", lambda _event: self._refresh_palette())

        self.palette_filter = ctk.CTkOptionMenu(
            palette,
            height=28,
            values=["All", "Generation", "Storage", "Routing", "Loads"],
            command=lambda _value: self._refresh_palette(),
        )
        self.palette_filter.set("All")
        self.palette_filter.grid(row=2, column=0, sticky="ew", padx=9, pady=(0, 5))

        self.palette_scroll = ctk.CTkScrollableFrame(palette, fg_color="transparent")
        self.palette_scroll.grid(row=3, column=0, sticky="nsew", padx=3, pady=(0, 5))
        self.palette_scroll.grid_columnconfigure(0, weight=1)
        self._refresh_palette()

    def _build_canvas(self, parent) -> None:
        shell = ctk.CTkFrame(parent, corner_radius=10)
        shell.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        shell.grid_rowconfigure(1, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(shell, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(5, 3))
        toolbar.grid_columnconfigure(0, weight=1)
        self.wire_status = ctk.CTkLabel(
            toolbar,
            text="Wire: orange output → blue input · middle-drag pans · Delete removes selection.",
            text_color=MUTED,
            font=ctk.CTkFont(size=10),
            anchor="w",
        )
        self.wire_status.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            toolbar,
            text="Cancel wire",
            width=78,
            height=27,
            fg_color="transparent",
            border_width=1,
            command=self.cancel_wire,
        ).grid(row=0, column=1, padx=(8, 0))

        canvas_frame = ctk.CTkFrame(shell, fg_color="#09111f", corner_radius=8)
        canvas_frame.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=(0, 6))
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#09111f",
            highlightthickness=0,
            scrollregion=(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT),
            cursor="arrow",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.vscroll = ctk.CTkScrollbar(canvas_frame, orientation="vertical", command=self.canvas.yview)
        self.vscroll.grid(row=0, column=1, sticky="ns")
        self.hscroll = ctk.CTkScrollbar(shell, orientation="horizontal", command=self.canvas.xview)
        self.hscroll.grid(row=2, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        self.canvas.configure(yscrollcommand=self.vscroll.set, xscrollcommand=self.hscroll.set)

        self.canvas.bind("<Button-1>", self._canvas_blank_click)
        self.canvas.bind("<Delete>", lambda _event: self.delete_selected())
        self.canvas.bind("<BackSpace>", lambda _event: self.delete_selected())
        self.canvas.bind("<ButtonPress-2>", self._pan_start)
        self.canvas.bind("<B2-Motion>", self._pan_move)
        self.canvas.bind("<MouseWheel>", self._canvas_wheel)

        for x in range(0, CANVAS_WIDTH, GRID_SIZE):
            self.canvas.create_line(x, 0, x, CANVAS_HEIGHT, fill="#102038", width=1, tags=("grid",))
        for y in range(0, CANVAS_HEIGHT, GRID_SIZE):
            self.canvas.create_line(0, y, CANVAS_WIDTH, y, fill="#102038", width=1, tags=("grid",))
        self.canvas.tag_lower("grid")

    def _build_inspector(self, parent) -> None:
        inspector = ctk.CTkFrame(parent, corner_radius=10)
        inspector.grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)
        inspector.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            inspector,
            text="Selected equipment",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 1))
        self.inspector_title = ctk.CTkLabel(
            inspector,
            text="Nothing selected",
            text_color=MUTED,
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=225,
        )
        self.inspector_title.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        editor = ctk.CTkFrame(inspector, fg_color="transparent")
        editor.grid(row=2, column=0, sticky="ew", padx=8)
        editor.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(editor, text="Qty", text_color=MUTED, font=ctk.CTkFont(size=10)).grid(
            row=0, column=0, sticky="w", padx=2, pady=2
        )
        self.quantity_entry = ctk.CTkEntry(editor, height=27)
        self.quantity_entry.grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        ctk.CTkLabel(editor, text="State", text_color=MUTED, font=ctk.CTkFont(size=10)).grid(
            row=1, column=0, sticky="w", padx=2, pady=2
        )
        self.state_menu = ctk.CTkOptionMenu(editor, values=self.STATES, height=27)
        self.state_menu.grid(row=1, column=1, sticky="ew", padx=2, pady=2)

        ctk.CTkLabel(editor, text="Zone", text_color=MUTED, font=ctk.CTkFont(size=10)).grid(
            row=2, column=0, sticky="w", padx=2, pady=2
        )
        self.zone_menu = ctk.CTkOptionMenu(editor, values=self.ZONES, height=27)
        self.zone_menu.grid(row=2, column=1, sticky="ew", padx=2, pady=2)

        ctk.CTkButton(
            editor,
            text="Apply",
            height=27,
            command=self.apply_inspector_changes,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 2))

        ctk.CTkLabel(
            inspector,
            text="Verified electrical values",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(7, 2))
        self.spec_box = ctk.CTkTextbox(inspector, height=104, font=ctk.CTkFont(size=10))
        self.spec_box.grid(row=4, column=0, sticky="ew", padx=10)

        ctk.CTkLabel(
            inspector,
            text="Connected paths",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=5, column=0, sticky="ew", padx=10, pady=(7, 2))
        self.path_box = ctk.CTkTextbox(inspector, height=72, font=ctk.CTkFont(size=10))
        self.path_box.grid(row=6, column=0, sticky="ew", padx=10)

        assumptions = ctk.CTkFrame(inspector, fg_color="transparent")
        assumptions.grid(row=7, column=0, sticky="ew", padx=8, pady=(7, 3))
        assumptions.grid_columnconfigure(1, weight=1)

        labels = (
            ("Solar avg %", "solar_entry"),
            ("Wind avg %", "wind_entry"),
            ("Battery charge %", "charge_entry"),
        )
        for row_index, (label, attribute) in enumerate(labels):
            ctk.CTkLabel(
                assumptions,
                text=label,
                text_color=MUTED,
                font=ctk.CTkFont(size=9),
            ).grid(row=row_index, column=0, sticky="w", padx=2, pady=1)
            entry = ctk.CTkEntry(assumptions, height=25)
            entry.grid(row=row_index, column=1, sticky="ew", padx=2, pady=1)
            setattr(self, attribute, entry)

        ctk.CTkButton(
            assumptions,
            text="Apply assumptions",
            height=26,
            command=self.apply_assumptions,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 1))

        self.math_model_label = ctk.CTkLabel(
            inspector,
            text="Battery-bus model: generation × charge efficiency − live load",
            text_color=MUTED,
            font=ctk.CTkFont(size=9),
            anchor="w",
            justify="left",
            wraplength=225,
        )
        self.math_model_label.grid(row=8, column=0, sticky="ew", padx=10, pady=(4, 8))

        self._set_textbox(self.spec_box, "Select a component to see its verified electrical values.")
        self._set_textbox(self.path_box, "Select a component to see incoming and outgoing paths.")

    def _build_recommendations(self) -> None:
        panel = ctk.CTkFrame(self, corner_radius=10)
        panel.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        panel.grid_columnconfigure(0, weight=1)

        heading = ctk.CTkFrame(panel, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=11, pady=(7, 2))
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            heading,
            text="Suggested changes",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.recommendation_status = ctk.CTkLabel(
            heading,
            text="0 checks",
            text_color=MUTED,
            font=ctk.CTkFont(size=9, weight="bold"),
            anchor="e",
        )
        self.recommendation_status.grid(row=0, column=1, sticky="e")

        self.recommendation_box = ctk.CTkTextbox(
            panel,
            height=104,
            font=ctk.CTkFont(size=10),
        )
        self.recommendation_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

    def _refresh_palette(self) -> None:
        for child in self.palette_scroll.winfo_children():
            child.destroy()

        query = self.palette_search.get().strip().casefold() if hasattr(self, "palette_search") else ""
        selected_filter = self.palette_filter.get() if hasattr(self, "palette_filter") else "All"
        filter_categories = {
            "Generation": {"generation"},
            "Storage": {"storage"},
            "Routing": {"control", "logic", "utility"},
            "Loads": {"load"},
        }
        allowed = filter_categories.get(selected_filter)

        rows = []
        for name, row in self.catalog.items():
            category = str(row.get("category", "utility")).lower()
            if allowed is not None and category not in allowed:
                continue
            searchable = " ".join(
                [name, category, " ".join(str(alias) for alias in row.get("aliases", []))]
            ).casefold()
            if query and query not in searchable:
                continue
            rows.append((name, row))

        rows.sort(
            key=lambda item: (
                CATEGORY_ORDER.get(str(item[1].get("category", "utility")).lower(), 9),
                item[0].casefold(),
            )
        )

        current_label = None
        grid_row = 0
        for name, row in rows:
            category = str(row.get("category", "utility")).lower()
            label = CATEGORY_LABELS.get(category, category.upper())
            if label != current_label:
                ctk.CTkLabel(
                    self.palette_scroll,
                    text=label,
                    text_color=MUTED,
                    font=ctk.CTkFont(size=9, weight="bold"),
                    anchor="w",
                ).grid(row=grid_row, column=0, sticky="ew", padx=6, pady=(5, 1))
                grid_row += 1
                current_label = label

            button = ctk.CTkButton(
                self.palette_scroll,
                text=name,
                anchor="w",
                height=30,
                font=ctk.CTkFont(size=10),
                fg_color="#172033",
                hover_color="#24324a",
            )
            button.grid(row=grid_row, column=0, sticky="ew", padx=3, pady=1)
            button.bind("<ButtonPress-1>", lambda event, component=name: self._palette_press(event, component))
            button.bind("<ButtonRelease-1>", lambda event, component=name: self._palette_release(event, component))
            grid_row += 1

        if not rows:
            ctk.CTkLabel(
                self.palette_scroll,
                text="No matching equipment.",
                text_color=MUTED,
                font=ctk.CTkFont(size=10),
            ).grid(row=0, column=0, sticky="ew", padx=7, pady=10)

    @staticmethod
    def _component_brief(row: dict[str, Any]) -> str:
        category = str(row.get("category", "utility")).lower()
        if category == "generation":
            return f"{float(row.get('max_output', 0)):.0f} rW peak"
        if category == "storage":
            return (
                f"{float(row.get('capacity_rwm', 0)):.0f} rWm · "
                f"{float(row.get('output_limit', 0)):.0f} rW output"
            )
        draw = float(row.get("power_draw", 0))
        return f"{draw:.0f} rW draw" if draw else "Routing / control"

    def _palette_press(self, event, component: str) -> None:
        self.palette_drag = {
            "component": component,
            "root_x": event.x_root,
            "root_y": event.y_root,
        }

    def _palette_release(self, event, component: str) -> None:
        drag = self.palette_drag or {}
        self.palette_drag = None
        dx = abs(event.x_root - int(drag.get("root_x", event.x_root)))
        dy = abs(event.y_root - int(drag.get("root_y", event.y_root)))

        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        right = left + self.canvas.winfo_width()
        bottom = top + self.canvas.winfo_height()

        if left <= event.x_root <= right and top <= event.y_root <= bottom:
            x = self.canvas.canvasx(event.x_root - left)
            y = self.canvas.canvasy(event.y_root - top)
            self.add_node(component, x, y)
        elif dx < 6 and dy < 6:
            x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
            y = self.canvas.canvasy(self.canvas.winfo_height() / 2)
            self.add_node(component, x, y)

    def add_node(self, component: str, x: float, y: float) -> None:
        node = {
            "id": str(uuid4()),
            "component": component,
            "quantity": 1,
            "state": "Planned",
            "zone": "Main",
            "note": "",
            "x": max(20.0, min(float(x) - NODE_WIDTH / 2, CANVAS_WIDTH - NODE_WIDTH - 20)),
            "y": max(20.0, min(float(y) - NODE_HEIGHT / 2, CANVAS_HEIGHT - NODE_HEIGHT - 20)),
        }
        self.nodes.append(node)
        self._draw_node(node)
        self.select_node(str(node["id"]))
        self.recalculate()
        self._schedule_autosave()

    def _draw_node(self, node: dict[str, Any]) -> None:
        node_id = str(node["id"])
        x = float(node.get("x", 50))
        y = float(node.get("y", 50))
        row = self.catalog.get(str(node.get("component", "")), {})
        category = str(row.get("category", "utility")).lower()
        fill = CATEGORY_COLORS.get(category, "#374151")
        r = CONNECTOR_RADIUS

        body = self.canvas.create_rectangle(
            x,
            y,
            x + NODE_WIDTH,
            y + NODE_HEIGHT,
            fill=fill,
            outline="#64748b",
            width=2,
            tags=("node", f"node:{node_id}", f"node-body:{node_id}"),
        )
        title = self.canvas.create_text(
            x + 9,
            y + 8,
            text=str(node.get("component", "Component")),
            fill="#f8fafc",
            font=("Segoe UI", 9, "bold"),
            anchor="nw",
            width=NODE_WIDTH - 18,
            tags=("node", f"node:{node_id}", f"node-body:{node_id}"),
        )
        detail = self.canvas.create_text(
            x + 9,
            y + 32,
            text=self._node_detail(node),
            fill="#cbd5e1",
            font=("Segoe UI", 8),
            anchor="nw",
            width=NODE_WIDTH - 18,
            tags=("node", f"node:{node_id}", f"node-body:{node_id}"),
        )
        input_dot = self.canvas.create_oval(
            x - r,
            y + NODE_HEIGHT / 2 - r,
            x + r,
            y + NODE_HEIGHT / 2 + r,
            fill="#38bdf8",
            outline="#e0f2fe",
            width=1,
            tags=("connector", "input", f"input:{node_id}"),
        )
        output_dot = self.canvas.create_oval(
            x + NODE_WIDTH - r,
            y + NODE_HEIGHT / 2 - r,
            x + NODE_WIDTH + r,
            y + NODE_HEIGHT / 2 + r,
            fill="#f59e0b",
            outline="#fffbeb",
            width=1,
            tags=("connector", "output", f"output:{node_id}"),
        )
        self.node_items[node_id] = {
            "body": body,
            "title": title,
            "detail": detail,
            "input": input_dot,
            "output": output_dot,
        }

        for item in (body, title, detail):
            self.canvas.tag_bind(item, "<ButtonPress-1>", lambda event, nid=node_id: self._node_press(event, nid))
            self.canvas.tag_bind(item, "<B1-Motion>", lambda event, nid=node_id: self._node_drag(event, nid))
            self.canvas.tag_bind(item, "<ButtonRelease-1>", lambda event, nid=node_id: self._node_release(event, nid))
        self.canvas.tag_bind(input_dot, "<Button-1>", lambda event, nid=node_id: self._input_clicked(event, nid))
        self.canvas.tag_bind(output_dot, "<Button-1>", lambda event, nid=node_id: self._output_clicked(event, nid))

    def _node_detail(self, node: dict[str, Any]) -> str:
        row = self.catalog.get(str(node.get("component", "")), {})
        brief = self._component_brief(row)
        quantity = max(1, int(node.get("quantity", 1) or 1))
        return f"x{quantity} · {brief}\n{node.get('state', 'Planned')} / {node.get('zone', 'Main')}"

    def _node_press(self, event, node_id: str) -> None:
        self.canvas.focus_set()
        self.select_node(node_id)
        node = self._node(node_id)
        if node is None:
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        self.drag_node_id = node_id
        self.drag_offset = (x - float(node.get("x", 0)), y - float(node.get("y", 0)))

    def _node_drag(self, event, node_id: str) -> None:
        if self.drag_node_id != node_id:
            return
        node = self._node(node_id)
        if node is None:
            return
        x = self.canvas.canvasx(event.x) - self.drag_offset[0]
        y = self.canvas.canvasy(event.y) - self.drag_offset[1]
        node["x"] = max(8.0, min(x, CANVAS_WIDTH - NODE_WIDTH - 8))
        node["y"] = max(8.0, min(y, CANVAS_HEIGHT - NODE_HEIGHT - 8))
        self._position_node(node_id)
        self._update_connections_for_node(node_id)

    def _node_release(self, _event, node_id: str) -> None:
        if self.drag_node_id == node_id:
            self.drag_node_id = None
            self._schedule_autosave()

    def _position_node(self, node_id: str) -> None:
        node = self._node(node_id)
        items = self.node_items.get(node_id)
        if node is None or items is None:
            return
        x = float(node.get("x", 0))
        y = float(node.get("y", 0))
        r = CONNECTOR_RADIUS
        self.canvas.coords(items["body"], x, y, x + NODE_WIDTH, y + NODE_HEIGHT)
        self.canvas.coords(items["title"], x + 9, y + 8)
        self.canvas.coords(items["detail"], x + 9, y + 32)
        self.canvas.coords(
            items["input"],
            x - r,
            y + NODE_HEIGHT / 2 - r,
            x + r,
            y + NODE_HEIGHT / 2 + r,
        )
        self.canvas.coords(
            items["output"],
            x + NODE_WIDTH - r,
            y + NODE_HEIGHT / 2 - r,
            x + NODE_WIDTH + r,
            y + NODE_HEIGHT / 2 + r,
        )

    def _output_clicked(self, event, node_id: str) -> None:
        self.canvas.focus_set()
        self.pending_source_id = node_id
        self.select_node(node_id)
        component = self._node(node_id).get("component", "component") if self._node(node_id) else "component"
        self.wire_status.configure(
            text=f"Wiring from {component}: click the blue input dot on the destination component.",
            text_color=("#92400e", "#fbbf24"),
        )

    def _input_clicked(self, event, node_id: str) -> None:
        self.canvas.focus_set()
        if self.pending_source_id is None:
            self.select_node(node_id)
            self.wire_status.configure(
                text="Choose an orange output dot first, then this blue input dot.",
                text_color=MUTED,
            )
            return
        source = self.pending_source_id
        self.pending_source_id = None
        if source == node_id:
            self.wire_status.configure(text="A component cannot be wired to itself.", text_color=("#991b1b", "#f87171"))
            return
        if any(connection.get("source") == source and connection.get("target") == node_id for connection in self.connections):
            self.wire_status.configure(text="That power path already exists.", text_color=MUTED)
            return
        connection = {"id": str(uuid4()), "source": source, "target": node_id}
        self.connections.append(connection)
        self._draw_connection(connection)
        self.select_connection(str(connection["id"]))
        self.wire_status.configure(
            text="Path created. Click another output dot to continue wiring.",
            text_color=("#166534", "#4ade80"),
        )
        self.recalculate()
        self._schedule_autosave()

    def cancel_wire(self) -> None:
        self.pending_source_id = None
        self.wire_status.configure(
            text="Wire mode: click a node's right output dot, then another node's left input dot.",
            text_color=MUTED,
        )

    def _draw_connection(self, connection: dict[str, Any]) -> None:
        connection_id = str(connection["id"])
        coords = self._connection_coords(connection)
        if coords is None:
            return
        line = self.canvas.create_line(
            *coords,
            fill="#f59e0b",
            width=3,
            smooth=True,
            splinesteps=20,
            arrow=tk.LAST,
            arrowshape=(10, 12, 5),
            tags=("wire", f"wire:{connection_id}"),
        )
        self.connection_items[connection_id] = line
        if self.canvas.find_withtag("node"):
            self.canvas.tag_lower(line, "node")
        self.canvas.tag_raise(line, "grid")
        self.canvas.tag_bind(line, "<Button-1>", lambda event, cid=connection_id: self._wire_clicked(event, cid))

    def _connection_coords(self, connection: dict[str, Any]) -> tuple[float, ...] | None:
        source = self._node(str(connection.get("source", "")))
        target = self._node(str(connection.get("target", "")))
        if source is None or target is None:
            return None
        sx = float(source.get("x", 0)) + NODE_OUTPUT_X
        sy = float(source.get("y", 0)) + NODE_HEIGHT / 2
        tx = float(target.get("x", 0)) + NODE_INPUT_X
        ty = float(target.get("y", 0)) + NODE_HEIGHT / 2
        bend = max(55.0, abs(tx - sx) * 0.45)
        if tx >= sx:
            return (sx, sy, sx + bend, sy, tx - bend, ty, tx, ty)
        detour = max(sy, ty) + 90
        return (sx, sy, sx + 55, sy, sx + 55, detour, tx - 55, detour, tx - 55, ty, tx, ty)

    def _wire_clicked(self, _event, connection_id: str) -> None:
        self.canvas.focus_set()
        self.select_connection(connection_id)

    def _update_connections_for_node(self, node_id: str) -> None:
        for connection in self.connections:
            if connection.get("source") != node_id and connection.get("target") != node_id:
                continue
            connection_id = str(connection.get("id"))
            item = self.connection_items.get(connection_id)
            coords = self._connection_coords(connection)
            if item is not None and coords is not None:
                self.canvas.coords(item, *coords)

    def select_node(self, node_id: str) -> None:
        self.selected_node_id = node_id
        self.selected_connection_id = None
        self._refresh_selection_style()
        self._refresh_inspector()

    def select_connection(self, connection_id: str) -> None:
        self.selected_node_id = None
        self.selected_connection_id = connection_id
        self._refresh_selection_style()
        connection = self._connection(connection_id)
        if connection is not None:
            source = self._node(str(connection.get("source", "")))
            target = self._node(str(connection.get("target", "")))
            source_name = source.get("component", "Source") if source else "Source"
            target_name = target.get("component", "Target") if target else "Target"
            self.inspector_title.configure(text=f"Selected path\n{source_name} → {target_name}", text_color=("#92400e", "#fbbf24"))
            self._set_textbox(self.spec_box, "This is a visual power path. Delete it with Delete selected or the keyboard Delete key.")
            self._set_textbox(self.path_box, f"OUTPUT\n{source_name}\n\nINPUT\n{target_name}")

    def _refresh_selection_style(self) -> None:
        for node_id, items in self.node_items.items():
            selected = node_id == self.selected_node_id
            self.canvas.itemconfigure(items["body"], outline=ACCENT if selected else "#64748b", width=4 if selected else 2)
        for connection_id, item in self.connection_items.items():
            selected = connection_id == self.selected_connection_id
            self.canvas.itemconfigure(item, fill="#fde047" if selected else "#f59e0b", width=5 if selected else 3)

    def _canvas_blank_click(self, event) -> None:
        current = self.canvas.find_withtag("current")
        if current:
            tags = self.canvas.gettags(current[0])
            if any(tag.startswith(("node:", "wire:", "input:", "output:")) for tag in tags):
                return
        self.canvas.focus_set()
        self.selected_node_id = None
        self.selected_connection_id = None
        self._refresh_selection_style()
        self._refresh_inspector()

    def _pan_start(self, event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _pan_move(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _canvas_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _refresh_inspector(self) -> None:
        node = self._node(self.selected_node_id) if self.selected_node_id else None
        if node is None:
            self.inspector_title.configure(text="Nothing selected", text_color=MUTED)
            self._replace_entry(self.quantity_entry, "1")
            self.state_menu.set("Planned")
            self.zone_menu.set("Main")
            self._set_textbox(self.spec_box, "Select a component to see its verified electrical values.")
            self._set_textbox(self.path_box, "Select a component to see incoming and outgoing paths.")
            return

        component = str(node.get("component", "Component"))
        row = self.catalog.get(component, {})
        category = str(row.get("category", "utility")).replace("_", " ").title()
        self.inspector_title.configure(text=f"{component}\n{category}", text_color="#f8fafc")
        self._replace_entry(self.quantity_entry, str(max(1, int(node.get("quantity", 1) or 1))))
        self.state_menu.set(str(node.get("state", "Planned")))
        self.zone_menu.set(str(node.get("zone", "Main")))

        specs = [
            f"Category: {category}",
            f"Power draw: {float(row.get('power_draw', 0)):.0f} rW each",
            f"Maximum output: {float(row.get('max_output', 0)):.0f} rW each",
            f"Battery capacity: {float(row.get('capacity_rwm', 0)):.0f} rWm each",
            f"Output limit: {float(row.get('output_limit', 0)):.0f} rW each",
            f"Charge efficiency: {float(row.get('charge_efficiency', 1.0)) * 100:.0f}%",
            f"Quantity total: x{max(1, int(node.get('quantity', 1) or 1))}",
        ]
        self._set_textbox(self.spec_box, "\n".join(specs))

        incoming_names = []
        outgoing_names = []
        node_id = str(node.get("id"))
        for connection in self.connections:
            if connection.get("target") == node_id:
                source = self._node(str(connection.get("source", "")))
                if source:
                    incoming_names.append(str(source.get("component", "Source")))
            if connection.get("source") == node_id:
                target = self._node(str(connection.get("target", "")))
                if target:
                    outgoing_names.append(str(target.get("component", "Target")))
        path_text = "INPUTS\n" + ("\n".join(f"← {name}" for name in incoming_names) if incoming_names else "None")
        path_text += "\n\nOUTPUTS\n" + ("\n".join(f"→ {name}" for name in outgoing_names) if outgoing_names else "None")
        self._set_textbox(self.path_box, path_text)

    def apply_inspector_changes(self) -> None:
        node = self._node(self.selected_node_id) if self.selected_node_id else None
        if node is None:
            return
        try:
            quantity = max(1, int(self.quantity_entry.get().strip() or "1"))
        except ValueError:
            quantity = 1
        node["quantity"] = quantity
        node["state"] = self.state_menu.get()
        node["zone"] = self.zone_menu.get()
        items = self.node_items.get(str(node["id"]))
        if items:
            self.canvas.itemconfigure(items["detail"], text=self._node_detail(node))
        self._refresh_inspector()
        self.recalculate()
        self._schedule_autosave()

    def apply_assumptions(self) -> None:
        self.assumptions = {
            "solar_utilization": self._percent(self.solar_entry.get(), 35),
            "wind_utilization": self._percent(self.wind_entry.get(), 55),
            "battery_charge_fraction": self._percent(self.charge_entry.get(), 100),
        }
        self._sync_assumption_entries()
        self.recalculate()
        self._schedule_autosave()

    @staticmethod
    def _percent(value: str, default: float) -> float:
        try:
            number = float(value.strip())
        except (ValueError, AttributeError):
            number = default
        return max(0.0, min(1.0, number / 100.0))

    def delete_selected(self) -> None:
        if self.selected_connection_id:
            connection_id = self.selected_connection_id
            self.connections = [row for row in self.connections if str(row.get("id")) != connection_id]
            item = self.connection_items.pop(connection_id, None)
            if item is not None:
                self.canvas.delete(item)
            self.selected_connection_id = None
        elif self.selected_node_id:
            node_id = self.selected_node_id
            self.nodes = [node for node in self.nodes if str(node.get("id")) != node_id]
            items = self.node_items.pop(node_id, {})
            for item in items.values():
                self.canvas.delete(item)
            removed_connection_ids = {
                str(connection.get("id"))
                for connection in self.connections
                if connection.get("source") == node_id or connection.get("target") == node_id
            }
            self.connections = [
                connection
                for connection in self.connections
                if str(connection.get("id")) not in removed_connection_ids
            ]
            for connection_id in removed_connection_ids:
                item = self.connection_items.pop(connection_id, None)
                if item is not None:
                    self.canvas.delete(item)
            self.selected_node_id = None
            if self.pending_source_id == node_id:
                self.cancel_wire()
        else:
            return
        self._refresh_selection_style()
        self._refresh_inspector()
        self.recalculate()
        self._schedule_autosave()

    def clear_wires(self) -> None:
        if not self.connections:
            return
        if not messagebox.askyesno("Clear wires", "Remove every visual power path from this circuit?"):
            return
        for item in self.connection_items.values():
            self.canvas.delete(item)
        self.connections.clear()
        self.connection_items.clear()
        self.selected_connection_id = None
        self.cancel_wire()
        self.recalculate()
        self._schedule_autosave()

    def new_circuit(self) -> None:
        if self.nodes and not messagebox.askyesno("New circuit", "Clear the current circuit and start over?"):
            return
        self.nodes.clear()
        self.connections.clear()
        self.selected_node_id = None
        self.selected_connection_id = None
        self.pending_source_id = None
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, "Main Base")
        self.assumptions = dict(DEFAULT_ASSUMPTIONS)
        self._sync_assumption_entries()
        self._redraw_all()
        self.recalculate()
        self.save_circuit(show_message=False)

    def auto_layout(self) -> None:
        if not self.nodes:
            return
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for node in sorted(self.nodes, key=lambda row: str(row.get("component", "")).casefold()):
            category = _node_category(node, self.catalog)
            grouped[CATEGORY_ORDER.get(category, 2)].append(node)

        columns = sorted(grouped)
        for display_column, category_column in enumerate(columns):
            for row_index, node in enumerate(grouped[category_column]):
                node["x"] = 70 + display_column * 240
                node["y"] = 65 + row_index * 92
        self._redraw_all()
        self.recalculate()
        self._schedule_autosave()

    def recalculate(self) -> None:
        setup = setup_from_canvas(
            self.name_entry.get().strip() or "Main Base",
            self.nodes,
            self.assumptions,
        )
        analysis = analyze_setup(setup)

        active_count = sum(
            max(1, int(node.get("quantity", 1) or 1))
            for node in self.nodes
            if str(node.get("state", "Planned")).casefold() in {"placed", "planned"}
        )
        usable_average = float(
            getattr(analysis, "usable_generation_rw", analysis.estimated_generation_rw)
        )
        battery_efficiency = float(
            getattr(analysis, "battery_charge_efficiency", 1.0)
        )
        estimated_runtime = float(
            getattr(
                analysis,
                "estimated_runtime_minutes",
                analysis.no_generation_runtime_minutes,
            )
        )

        self.metric_cards["load"].set(
            f"{analysis.load_rw:.0f} rW",
            f"{active_count} active item{'s' if active_count != 1 else ''}",
        )
        self.metric_cards["generation"].set(
            f"{analysis.peak_generation_rw:.0f} rW",
            f"{analysis.utilization_percent:.0f}% usable peak use",
        )
        self.metric_cards["average"].set(
            f"{usable_average:.0f} rW",
            (
                f"after {battery_efficiency * 100:.0f}% battery input efficiency"
                if analysis.battery_capacity_rwm > 0
                else "direct average generation"
            ),
        )
        self.metric_cards["battery"].set(
            f"{analysis.battery_capacity_rwm:.0f} rWm",
            f"{analysis.battery_output_limit_rw:.0f} rW combined output",
        )
        runtime_detail = (
            f"with average input: {self._format_runtime(estimated_runtime)}"
            if not math.isinf(estimated_runtime)
            else "average input sustains the load"
        )
        self.metric_cards["runtime"].set(
            self._format_runtime(analysis.no_generation_runtime_minutes),
            runtime_detail,
        )
        self.metric_cards["headroom"].set(
            f"{analysis.peak_headroom_rw:+.0f} rW",
            f"raw input target {analysis.required_peak_for_charging_rw:.0f} rW",
        )

        self.math_model_label.configure(
            text=(
                "Battery-bus model: "
                f"{analysis.estimated_generation_rw:.0f} rW raw average × "
                f"{battery_efficiency * 100:.0f}% − {analysis.load_rw:.0f} rW load"
            )
        )

        suggestions = list(analysis.recommendations)
        suggestions.extend(
            circuit_recommendations(
                self.nodes,
                self.connections,
                self.catalog,
            )
        )
        unique: list[str] = []
        seen: set[str] = set()
        for suggestion in suggestions:
            normalized = suggestion.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)

        priority = {
            "[Fix]": 0,
            "[Swap]": 1,
            "[Optimize]": 2,
            "[Info]": 3,
        }
        unique.sort(
            key=lambda suggestion: next(
                (
                    rank
                    for prefix, rank in priority.items()
                    if suggestion.startswith(prefix)
                ),
                4,
            )
        )
        if not unique:
            unique = ["[Info] The circuit has no obvious power-balance or wiring-path issue."]

        self.recommendation_status.configure(
            text=f"{len(unique)} recommendation{'s' if len(unique) != 1 else ''}"
        )
        self._set_textbox(
            self.recommendation_box,
            "\n".join(
                f"{index}. {suggestion}"
                for index, suggestion in enumerate(unique, start=1)
            ),
        )
        if self.selected_node_id:
            self._refresh_inspector()

    @staticmethod
    def _format_runtime(minutes: float) -> str:
        if math.isinf(minutes):
            return "Indefinite"
        if minutes < 60:
            return f"{minutes:.0f} min"
        return f"{minutes / 60:.1f} h"

    def _redraw_all(self) -> None:
        self.canvas.delete("node")
        self.canvas.delete("connector")
        self.canvas.delete("wire")
        self.node_items.clear()
        self.connection_items.clear()
        for connection in self.connections:
            self._draw_connection(connection)
        for node in self.nodes:
            self._draw_node(node)
        for connection in self.connections:
            connection_id = str(connection.get("id"))
            item = self.connection_items.get(connection_id)
            if item is not None:
                self.canvas.tag_lower(item, "node")
                self.canvas.tag_raise(item, "grid")
        self._refresh_selection_style()
        self._refresh_inspector()

    def _node(self, node_id: str | None) -> dict[str, Any] | None:
        if not node_id:
            return None
        return next((node for node in self.nodes if str(node.get("id")) == node_id), None)

    def _connection(self, connection_id: str | None) -> dict[str, Any] | None:
        if not connection_id:
            return None
        return next(
            (connection for connection in self.connections if str(connection.get("id")) == connection_id),
            None,
        )

    def _load_state(self) -> None:
        state = self.context.store.get(CANVAS_STATE_KEY, {})
        if isinstance(state, dict) and isinstance(state.get("nodes"), list):
            self.nodes = [dict(node) for node in state.get("nodes", []) if isinstance(node, dict)]
            self.connections = [
                dict(connection)
                for connection in state.get("connections", [])
                if isinstance(connection, dict)
            ]
            self.assumptions = dict(DEFAULT_ASSUMPTIONS)
            if isinstance(state.get("assumptions"), dict):
                self.assumptions.update(state["assumptions"])
            name = str(state.get("name", "Main Base") or "Main Base")
        else:
            name = "Main Base"
            self._migrate_legacy_setup()

        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, name)
        self._sync_assumption_entries()
        self._normalize_state()

    def _migrate_legacy_setup(self) -> None:
        rows = self.context.store.get("electrical_setups", [])
        if not isinstance(rows, list) or not rows:
            return
        try:
            setup = ElectricalSetup.from_dict(rows[-1])
        except Exception:
            return
        self.assumptions.update(setup.assumptions)
        for index, item in enumerate(setup.components):
            self.nodes.append(
                {
                    "id": str(uuid4()),
                    "component": item.component,
                    "quantity": max(1, item.quantity),
                    "state": item.state,
                    "zone": item.zone,
                    "note": item.note,
                    "x": 70 + (index % 5) * 225,
                    "y": 65 + (index // 5) * 92,
                }
            )

    def _normalize_state(self) -> None:
        valid_ids: set[str] = set()
        normalized_nodes: list[dict[str, Any]] = []
        for index, node in enumerate(self.nodes):
            node = dict(node)
            node_id = str(node.get("id") or uuid4())
            if node_id in valid_ids:
                node_id = str(uuid4())
            node["id"] = node_id
            node["component"] = str(node.get("component", ""))
            if node["component"] not in self.catalog:
                continue
            node["quantity"] = max(1, int(node.get("quantity", 1) or 1))
            node["state"] = str(node.get("state", "Planned") or "Planned")
            node["zone"] = str(node.get("zone", "Main") or "Main")
            node["x"] = float(node.get("x", 70 + (index % 5) * 225))
            node["y"] = float(node.get("y", 65 + (index // 5) * 92))
            valid_ids.add(node_id)
            normalized_nodes.append(node)
        self.nodes = normalized_nodes

        normalized_connections: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for connection in self.connections:
            source = str(connection.get("source", ""))
            target = str(connection.get("target", ""))
            pair = (source, target)
            if source not in valid_ids or target not in valid_ids or source == target or pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            normalized_connections.append(
                {
                    "id": str(connection.get("id") or uuid4()),
                    "source": source,
                    "target": target,
                }
            )
        self.connections = normalized_connections

    def save_circuit(self, show_message: bool = True) -> None:
        state = {
            "name": self.name_entry.get().strip() or "Main Base",
            "nodes": [dict(node) for node in self.nodes],
            "connections": [dict(connection) for connection in self.connections],
            "assumptions": dict(self.assumptions),
        }
        self.context.store.set(CANVAS_STATE_KEY, state)
        if show_message:
            messagebox.showinfo("Circuit saved", "The visual electrical circuit was saved.")

    def _schedule_autosave(self) -> None:
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except Exception:
                pass
        self._autosave_job = self.after(500, self._autosave)

    def _autosave(self) -> None:
        self._autosave_job = None
        self.save_circuit(show_message=False)

    def _sync_assumption_entries(self) -> None:
        self._replace_entry(self.solar_entry, f"{self.assumptions.get('solar_utilization', 0.35) * 100:.0f}")
        self._replace_entry(self.wind_entry, f"{self.assumptions.get('wind_utilization', 0.55) * 100:.0f}")
        self._replace_entry(self.charge_entry, f"{self.assumptions.get('battery_charge_fraction', 1.0) * 100:.0f}")

    @staticmethod
    def _replace_entry(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    @staticmethod
    def _set_textbox(box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def on_context_updated(self) -> None:
        # Electrical designs are local and do not depend on live Rust+ refreshes.
        return
