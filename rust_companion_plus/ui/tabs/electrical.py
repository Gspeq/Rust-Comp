from __future__ import annotations

import math
from copy import deepcopy
from tkinter import messagebox, ttk

import customtkinter as ctk

from rust_companion_plus.catalog import electrical_catalog
from rust_companion_plus.models import ElectricalSetup, SetupComponent, utc_now_iso
from rust_companion_plus.services.electrical import (
    analyze_setup,
    compare_setups,
    merge_parsed_components,
    parse_component_text,
)
from rust_companion_plus.ui.common import MetricCard, SectionCard, safe_float, safe_int


class ElectricalTab(ctk.CTkFrame):
    STATES = ["Placed", "Planned", "Inventory"]
    ZONES = ["Main", "Defense", "Living", "Farm", "Industrial", "External"]

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.catalog = electrical_catalog()
        self.setup = ElectricalSetup()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="Electrical Analyzer", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        self.name_entry = ctk.CTkEntry(header, width=220, placeholder_text="Setup name")
        self.name_entry.insert(0, self.setup.name)
        self.name_entry.grid(row=0, column=1, padx=5)
        ctk.CTkButton(header, text="New", width=80, command=self.new_setup).grid(row=0, column=2, padx=5)
        ctk.CTkButton(header, text="Save version", width=110, command=self.save_version).grid(row=0, column=3, padx=5)

        self.main_tabs = ctk.CTkTabview(self)
        self.main_tabs.grid(row=1, column=0, sticky="nsew")
        self.main_tabs.add("Planner")
        self.main_tabs.add("Versions & Compare")
        self._build_planner(self.main_tabs.tab("Planner"))
        self._build_versions(self.main_tabs.tab("Versions & Compare"))
        self.recalculate()

    def _build_planner(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=2)
        parent.grid_columnconfigure(1, weight=3)
        parent.grid_rowconfigure(1, weight=1)

        goal_card = SectionCard(
            parent,
            "Goal and inventory text",
            "Examples: “Power 6 auto turrets, 4 lights, 2 doors and a large battery.” "
            "Inventory text is added as non-active inventory.",
        )
        goal_card.grid(row=0, column=0, sticky="nsew", padx=(6, 4), pady=6)
        text_area = ctk.CTkFrame(goal_card, fg_color="transparent")
        text_area.grid(row=goal_card.content_row, column=0, sticky="ew", padx=12, pady=(0, 12))
        text_area.grid_columnconfigure((0, 1), weight=1)
        self.goal_text = ctk.CTkTextbox(text_area, height=100)
        self.goal_text.grid(row=0, column=0, sticky="ew", padx=4)
        self.goal_text.insert("1.0", "Power 6 auto turrets, 4 lights, 2 doors, and a large battery backup")
        self.inventory_text = ctk.CTkTextbox(text_area, height=100)
        self.inventory_text.grid(row=0, column=1, sticky="ew", padx=4)
        self.inventory_text.insert("1.0", "2 solar panels\n1 root combiner")
        ctk.CTkButton(text_area, text="Apply goal as planned", command=self.apply_goal).grid(
            row=1, column=0, sticky="ew", padx=4, pady=6
        )
        ctk.CTkButton(text_area, text="Add inventory", command=self.apply_inventory).grid(
            row=1, column=1, sticky="ew", padx=4, pady=6
        )

        metrics_frame = ctk.CTkFrame(parent, fg_color="transparent")
        metrics_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 6), pady=6)
        metrics_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.metric_cards = {}
        for index, (key, title) in enumerate([
            ("load", "Active load"),
            ("generation", "Peak generation"),
            ("average", "Estimated average"),
            ("battery", "Battery capacity"),
            ("runtime", "No-generation runtime"),
            ("headroom", "Peak headroom"),
        ]):
            card = MetricCard(metrics_frame, title)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=4, pady=4)
            self.metric_cards[key] = card

        builder = SectionCard(
            parent,
            "Manual component builder",
            "Placed and Planned rows are included in calculations. Inventory rows are used for shopping awareness only.",
        )
        builder.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        builder.grid_rowconfigure(builder.content_row + 1, weight=1)
        controls = ctk.CTkFrame(builder, fg_color="transparent")
        controls.grid(row=builder.content_row, column=0, sticky="ew", padx=12, pady=6)
        controls.grid_columnconfigure(0, weight=3)
        controls.grid_columnconfigure(3, weight=2)
        self.component_menu = ctk.CTkOptionMenu(controls, values=sorted(self.catalog))
        self.component_menu.grid(row=0, column=0, sticky="ew", padx=3)
        self.quantity_entry = ctk.CTkEntry(controls, width=80, placeholder_text="Qty")
        self.quantity_entry.insert(0, "1")
        self.quantity_entry.grid(row=0, column=1, padx=3)
        self.state_menu = ctk.CTkOptionMenu(controls, values=self.STATES)
        self.state_menu.set("Planned")
        self.state_menu.grid(row=0, column=2, padx=3)
        self.zone_menu = ctk.CTkOptionMenu(controls, values=self.ZONES)
        self.zone_menu.grid(row=0, column=3, sticky="ew", padx=3)
        ctk.CTkButton(controls, text="Add", width=70, command=self.add_manual).grid(row=0, column=4, padx=3)
        ctk.CTkButton(controls, text="Remove selected", width=120, command=self.remove_selected).grid(row=0, column=5, padx=3)

        table_frame = ctk.CTkFrame(builder, fg_color="transparent")
        table_frame.grid(row=builder.content_row + 1, column=0, sticky="nsew", padx=12, pady=6)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        columns = ("component", "quantity", "state", "zone", "unit", "total")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=11)
        for column, width in [
            ("component", 250), ("quantity", 80), ("state", 90),
            ("zone", 100), ("unit", 90), ("total", 100)
        ]:
            self.tree.heading(column, text=column.title())
            self.tree.column(column, width=width, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        assumptions = ctk.CTkFrame(builder, fg_color="transparent")
        assumptions.grid(row=builder.content_row + 2, column=0, sticky="ew", padx=12, pady=6)
        assumptions.grid_columnconfigure((1, 3, 5), weight=1)
        ctk.CTkLabel(assumptions, text="Solar avg %").grid(row=0, column=0, padx=3)
        self.solar = ctk.CTkEntry(assumptions)
        self.solar.insert(0, "35")
        self.solar.grid(row=0, column=1, sticky="ew", padx=3)
        ctk.CTkLabel(assumptions, text="Wind avg %").grid(row=0, column=2, padx=3)
        self.wind = ctk.CTkEntry(assumptions)
        self.wind.insert(0, "55")
        self.wind.grid(row=0, column=3, sticky="ew", padx=3)
        ctk.CTkLabel(assumptions, text="Battery charge %").grid(row=0, column=4, padx=3)
        self.charge = ctk.CTkEntry(assumptions)
        self.charge.insert(0, "100")
        self.charge.grid(row=0, column=5, sticky="ew", padx=3)
        ctk.CTkButton(assumptions, text="Recalculate", command=self.recalculate).grid(row=0, column=6, padx=5)

        tips = SectionCard(builder, "Optimization report")
        tips.grid(row=builder.content_row + 3, column=0, sticky="ew", padx=12, pady=(4, 12))
        self.tips_box = ctk.CTkTextbox(tips, height=145)
        self.tips_box.grid(row=tips.content_row, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _build_versions(self, parent) -> None:
        parent.grid_columnconfigure((0, 1), weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self.left_version = ctk.CTkOptionMenu(parent, values=["No saved versions"])
        self.left_version.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.right_version = ctk.CTkOptionMenu(parent, values=["Current working setup"])
        self.right_version.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(parent, text="Compare", command=self.compare_versions).grid(
            row=0, column=2, padx=8, pady=8
        )
        self.compare_box = ctk.CTkTextbox(parent)
        self.compare_box.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        self.refresh_version_menus()

    def setup_rows(self) -> list[dict]:
        return list(self.context.store.get("electrical_setups", []))

    def _version_label(self, setup: ElectricalSetup) -> str:
        return f"{setup.name} · v{setup.version} · {setup.updated_at}"

    def refresh_version_menus(self) -> None:
        setups = [ElectricalSetup.from_dict(row) for row in self.setup_rows()]
        labels = [self._version_label(setup) for setup in setups] or ["No saved versions"]
        self.left_version.configure(values=labels)
        self.right_version.configure(values=labels + ["Current working setup"])
        self.left_version.set(labels[-1])
        self.right_version.set("Current working setup")

    def new_setup(self) -> None:
        self.setup = ElectricalSetup(name="New Setup")
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, self.setup.name)
        self.goal_text.delete("1.0", "end")
        self.refresh_table()
        self.recalculate()

    def apply_goal(self) -> None:
        text = self.goal_text.get("1.0", "end").strip()
        result = parse_component_text(text)
        self.setup.goal_text = text
        self.setup.components = merge_parsed_components(
            self.setup.components, result.components, "Planned", "Main"
        )
        self.refresh_table()
        self.recalculate()
        if result.unmatched:
            messagebox.showwarning(
                "Partially parsed",
                "These fragments were not recognized:\n\n" + "\n".join(result.unmatched),
            )

    def apply_inventory(self) -> None:
        result = parse_component_text(self.inventory_text.get("1.0", "end"))
        self.setup.components = merge_parsed_components(
            self.setup.components, result.components, "Inventory", "Storage"
        )
        self.refresh_table()
        self.recalculate()
        if result.unmatched:
            messagebox.showwarning("Partially parsed", "\n".join(result.unmatched))

    def add_manual(self) -> None:
        quantity = max(1, safe_int(self.quantity_entry.get(), 1))
        self.setup.components.append(
            SetupComponent(
                self.component_menu.get(),
                quantity,
                self.state_menu.get(),
                self.zone_menu.get(),
            )
        )
        self.refresh_table()
        self.recalculate()

    def remove_selected(self) -> None:
        indexes = sorted((self.tree.index(item) for item in self.tree.selection()), reverse=True)
        for index in indexes:
            if 0 <= index < len(self.setup.components):
                self.setup.components.pop(index)
        self.refresh_table()
        self.recalculate()

    def refresh_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for item in self.setup.components:
            row = self.catalog.get(item.component, {})
            category = row.get("category")
            unit_value = row.get("power_draw", 0)
            unit_text = f"{unit_value} rW"
            total_text = f"{unit_value * item.quantity} rW"
            if category == "generation":
                unit_value = row.get("max_output", 0)
                unit_text = f"{unit_value} rW peak"
                total_text = f"{unit_value * item.quantity} rW"
            elif category == "storage":
                unit_value = row.get("capacity_rwm", 0)
                unit_text = f"{unit_value} rWm"
                total_text = f"{unit_value * item.quantity} rWm"
            self.tree.insert(
                "",
                "end",
                values=(item.component, item.quantity, item.state, item.zone, unit_text, total_text),
            )

    def sync_assumptions(self) -> None:
        self.setup.name = self.name_entry.get().strip() or "Unnamed Setup"
        self.setup.assumptions = {
            "solar_utilization": max(0.0, min(1.0, safe_float(self.solar.get(), 35) / 100)),
            "wind_utilization": max(0.0, min(1.0, safe_float(self.wind.get(), 55) / 100)),
            "battery_charge_fraction": max(0.0, min(1.0, safe_float(self.charge.get(), 100) / 100)),
        }

    @staticmethod
    def format_runtime(minutes: float) -> str:
        if math.isinf(minutes):
            return "Indefinite"
        return f"{minutes / 60:.1f} h"

    def recalculate(self) -> None:
        self.sync_assumptions()
        analysis = analyze_setup(self.setup)
        self.metric_cards["load"].set(f"{analysis.load_rw:.0f} rW", "Placed + planned")
        self.metric_cards["generation"].set(
            f"{analysis.peak_generation_rw:.0f} rW",
            f"{analysis.utilization_percent:.0f}% peak utilization",
        )
        self.metric_cards["average"].set(
            f"{analysis.estimated_generation_rw:.0f} rW", "Assumption-based"
        )
        self.metric_cards["battery"].set(
            f"{analysis.battery_capacity_rwm:.0f} rWm",
            f"{analysis.battery_output_limit_rw:.0f} rW output limit",
        )
        self.metric_cards["runtime"].set(
            self.format_runtime(analysis.no_generation_runtime_minutes),
            "At selected charge %",
        )
        self.metric_cards["headroom"].set(
            f"{analysis.peak_headroom_rw:+.0f} rW",
            f"Charging target ≈ {analysis.required_peak_for_charging_rw:.0f} rW",
        )
        self.tips_box.delete("1.0", "end")
        self.tips_box.insert(
            "1.0",
            "\n".join(f"• {tip}" for tip in analysis.recommendations),
        )

    def save_version(self) -> None:
        self.sync_assumptions()
        rows = self.setup_rows()
        family_versions = [
            ElectricalSetup.from_dict(row).version
            for row in rows
            if ElectricalSetup.from_dict(row).name == self.setup.name
        ]
        saved = deepcopy(self.setup)
        saved.version = max(family_versions, default=0) + 1
        saved.setup_id = ElectricalSetup().setup_id
        saved.created_at = utc_now_iso()
        saved.updated_at = utc_now_iso()
        rows.append(saved.to_dict())
        self.context.store.set("electrical_setups", rows)
        self.setup.version = saved.version
        self.refresh_version_menus()
        messagebox.showinfo("Saved", f"Saved {saved.name} version {saved.version}.")

    def _setup_by_label(self, label: str) -> ElectricalSetup | None:
        for row in self.setup_rows():
            setup = ElectricalSetup.from_dict(row)
            if self._version_label(setup) == label:
                return setup
        return None

    def compare_versions(self) -> None:
        left = self._setup_by_label(self.left_version.get())
        if left is None:
            self.compare_box.delete("1.0", "end")
            self.compare_box.insert("1.0", "Save at least one setup version first.")
            return
        right = (
            self.setup
            if self.right_version.get() == "Current working setup"
            else self._setup_by_label(self.right_version.get())
        )
        if right is None:
            return
        self.compare_box.delete("1.0", "end")
        self.compare_box.insert("1.0", "\n".join(compare_setups(left, right)))
