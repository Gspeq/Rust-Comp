from __future__ import annotations

from collections import defaultdict
from tkinter import messagebox

import customtkinter as ctk

from rust_companion_plus.catalog import BUILDING_COSTS, RECYCLE_CATALOG
from rust_companion_plus.services.electrical import suggested_three_parent_crosses
from rust_companion_plus.services.tools import (
    calculate_building_cost,
    calculate_recycle,
    calculate_upkeep_hours,
    rank_plants,
)
from rust_companion_plus.ui.common import SectionCard, run_in_worker, safe_float, safe_int


class ToolsTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Planning Tools", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        tabs = ctk.CTkTabview(self)
        tabs.grid(row=1, column=0, sticky="nsew")
        for name in ["TC Upkeep", "Recycle", "Building", "Farming", "Plants", "Loot", "Devices"]:
            tabs.add(name)
        self._upkeep(tabs.tab("TC Upkeep"))
        self._recycle(tabs.tab("Recycle"))
        self._building(tabs.tab("Building"))
        self._farming(tabs.tab("Farming"))
        self._plants(tabs.tab("Plants"))
        self._loot(tabs.tab("Loot"))
        self._devices(tabs.tab("Devices"))

    def _upkeep(self, parent) -> None:
        parent.grid_columnconfigure((0, 1), weight=1)
        resources = ["Wood", "Stone", "Metal Fragments", "High Quality Metal"]
        self.upkeep_inventory = {}
        self.upkeep_rate = {}
        for row, resource in enumerate(resources):
            ctk.CTkLabel(parent, text=resource).grid(row=row, column=0, sticky="w", padx=10, pady=6)
            inv = ctk.CTkEntry(parent, placeholder_text="In TC")
            inv.grid(row=row, column=1, sticky="ew", padx=5, pady=6)
            rate = ctk.CTkEntry(parent, placeholder_text="Used per hour")
            rate.grid(row=row, column=2, sticky="ew", padx=5, pady=6)
            self.upkeep_inventory[resource] = inv
            self.upkeep_rate[resource] = rate
        ctk.CTkButton(parent, text="Calculate time remaining", command=self.calculate_upkeep).grid(
            row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=10
        )
        self.upkeep_result = ctk.CTkTextbox(parent, height=220)
        self.upkeep_result.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=10, pady=10)

    def calculate_upkeep(self) -> None:
        inventory = {name: safe_float(widget.get()) for name, widget in self.upkeep_inventory.items()}
        rates = {name: safe_float(widget.get()) for name, widget in self.upkeep_rate.items()}
        total, details = calculate_upkeep_hours(inventory, rates)
        lines = []
        if total == float("inf"):
            lines.append("Enter at least one non-zero hourly upkeep rate.")
        else:
            lines.append(f"Base-wide limiting resource: {total:.1f} hours ({total/24:.2f} days)")
        lines.extend(f"{resource}: {hours:.1f} hours" for resource, hours in details.items())
        self.upkeep_result.delete("1.0", "end")
        self.upkeep_result.insert("1.0", "\n".join(lines))

    def _recycle(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self.recycle_item = ctk.CTkOptionMenu(parent, values=sorted(RECYCLE_CATALOG))
        self.recycle_item.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.recycle_qty = ctk.CTkEntry(parent, placeholder_text="Quantity")
        self.recycle_qty.insert(0, "1")
        self.recycle_qty.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkButton(parent, text="Calculate returns", command=self.calculate_recycle).grid(
            row=2, column=0, sticky="ew", padx=10, pady=10
        )
        self.recycle_result = ctk.CTkTextbox(parent, height=260)
        self.recycle_result.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)

    def calculate_recycle(self) -> None:
        returns = calculate_recycle(self.recycle_item.get(), safe_int(self.recycle_qty.get(), 1))
        self.recycle_result.delete("1.0", "end")
        self.recycle_result.insert(
            "1.0",
            "\n".join(f"{name}: {amount:g}" for name, amount in returns.items())
            + "\n\nStarter values are intentionally isolated in catalog.py for easy updating.",
        )

    def _building(self, parent) -> None:
        parent.grid_columnconfigure((0, 1), weight=1)
        self.build_counts = {}
        for row, grade in enumerate(BUILDING_COSTS):
            ctk.CTkLabel(parent, text=f"{grade} building blocks").grid(row=row, column=0, sticky="w", padx=10, pady=7)
            entry = ctk.CTkEntry(parent, placeholder_text="0")
            entry.grid(row=row, column=1, sticky="ew", padx=10, pady=7)
            self.build_counts[grade] = entry
        ctk.CTkButton(parent, text="Estimate build resources", command=self.calculate_build).grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=10
        )
        self.build_result = ctk.CTkTextbox(parent, height=230)
        self.build_result.grid(row=7, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)

    def calculate_build(self) -> None:
        counts = {grade: safe_int(entry.get()) for grade, entry in self.build_counts.items()}
        result = calculate_building_cost(counts)
        self.build_result.delete("1.0", "end")
        self.build_result.insert("1.0", "\n".join(f"{name}: {amount:,}" for name, amount in result.items()) or "No blocks entered.")

    def _farming(self, parent) -> None:
        parent.grid_columnconfigure((0, 1), weight=1)
        labels = [
            ("planters", "Large planters"),
            ("lights", "Ceiling lights"),
            ("sprinklers", "Sprinklers"),
            ("pumps", "Water pumps"),
            ("purifiers", "Powered purifiers"),
        ]
        self.farm_entries = {}
        for row, (key, label) in enumerate(labels):
            ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=7)
            entry = ctk.CTkEntry(parent, placeholder_text="0")
            entry.grid(row=row, column=1, sticky="ew", padx=10, pady=7)
            self.farm_entries[key] = entry
        ctk.CTkButton(parent, text="Plan farm", command=self.calculate_farm).grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=10
        )
        self.farm_result = ctk.CTkTextbox(parent, height=220)
        self.farm_result.grid(row=7, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)

    def calculate_farm(self) -> None:
        values = {key: safe_int(entry.get()) for key, entry in self.farm_entries.items()}
        power = values["lights"] * 2 + values["pumps"] * 5 + values["purifiers"] * 5
        planter_water = values["planters"] * 9_000
        lines = [
            f"Estimated electrical load: {power} rW",
            f"Full large-planter water capacity: {planter_water:,} ml",
            f"Sprinklers per planter: {values['sprinklers'] / max(values['planters'], 1):.2f}",
            "",
            "Use this as a capacity planner. Actual watering cadence depends on crop count, stage and server settings.",
        ]
        self.farm_result.delete("1.0", "end")
        self.farm_result.insert("1.0", "\n".join(lines))

    def _plants(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            parent,
            text="Enter one six-gene clone per line using G, Y, H, W and X.",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        self.plant_input = ctk.CTkTextbox(parent, height=210)
        self.plant_input.grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        self.plant_input.insert("1.0", "GGGYYY\nGGHYYY\nGYYHYG\nXXGYYY")
        ctk.CTkButton(parent, text="Rank clones and suggest crosses", command=self.calculate_plants).grid(
            row=2, column=0, sticky="ew", padx=10, pady=8
        )
        self.plant_result = ctk.CTkTextbox(parent, height=320)
        self.plant_result.grid(row=3, column=0, sticky="nsew", padx=10, pady=8)

    def calculate_plants(self) -> None:
        plants = self.plant_input.get("1.0", "end").splitlines()
        try:
            ranking = rank_plants(plants)
        except ValueError as exc:
            messagebox.showerror("Invalid genes", str(exc))
            return
        crosses = suggested_three_parent_crosses(plants)
        lines = ["CLONE RANKING"]
        lines.extend(f"{genes}  score {score:+d}" for genes, score in ranking)
        lines.extend(["", "THREE-PARENT HEURISTIC"])
        lines.extend(
            f"{a} + {b} + {c}  →  {child}  score {score:+d}"
            for a, b, c, child, score in crosses
        )
        lines.extend(["", "Crosses are a planning heuristic; confirm the actual cross in-game."])
        self.plant_result.delete("1.0", "end")
        self.plant_result.insert("1.0", "\n".join(lines))

    def _loot(self, parent) -> None:
        parent.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(parent, text="Item").grid(row=0, column=0)
        ctk.CTkLabel(parent, text="Quantity").grid(row=0, column=1)
        ctk.CTkLabel(parent, text="Scrap value each").grid(row=0, column=2)
        self.loot_rows = []
        for row in range(1, 9):
            item = ctk.CTkEntry(parent, placeholder_text=f"Item {row}")
            qty = ctk.CTkEntry(parent, placeholder_text="0")
            value = ctk.CTkEntry(parent, placeholder_text="0")
            item.grid(row=row, column=0, sticky="ew", padx=5, pady=5)
            qty.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
            value.grid(row=row, column=2, sticky="ew", padx=5, pady=5)
            self.loot_rows.append((item, qty, value))
        ctk.CTkButton(parent, text="Calculate scrap-equivalent value", command=self.calculate_loot).grid(
            row=10, column=0, columnspan=3, sticky="ew", padx=5, pady=10
        )
        self.loot_result = ctk.CTkLabel(parent, text="Total: 0 scrap", font=ctk.CTkFont(size=22, weight="bold"))
        self.loot_result.grid(row=11, column=0, columnspan=3, pady=10)

    def calculate_loot(self) -> None:
        total = 0.0
        details = []
        prices = {}
        for item, qty, value in self.loot_rows:
            name = item.get().strip()
            quantity = safe_float(qty.get())
            unit = safe_float(value.get())
            if name and quantity > 0:
                subtotal = quantity * unit
                total += subtotal
                details.append(f"{name}: {subtotal:g}")
                prices[name] = unit
        self.context.store.set("loot_prices", prices)
        self.loot_result.configure(text=f"Total: {total:g} scrap-equivalent\n" + " · ".join(details))

    def _devices(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self.device_id = ctk.CTkEntry(parent, placeholder_text="Paired entity ID")
        self.device_id.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        buttons = ctk.CTkFrame(parent, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=10)
        buttons.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(buttons, text="Read status", command=self.read_device).grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkButton(buttons, text="Turn ON", command=lambda: self.set_device(True)).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(buttons, text="Turn OFF", command=lambda: self.set_device(False)).grid(row=0, column=2, sticky="ew", padx=4)
        self.device_status = ctk.CTkTextbox(parent, height=260)
        self.device_status.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)

    def read_device(self) -> None:
        entity_id = safe_int(self.device_id.get())
        run_in_worker(
            self,
            lambda: self.context.rust.get_entity(self.context.credentials, entity_id),
            lambda result: self._show_device(result),
        )

    def _show_device(self, result) -> None:
        self.device_status.delete("1.0", "end")
        self.device_status.insert("1.0", "\n".join(f"{key}: {value}" for key, value in result.items()))

    def set_device(self, value: bool) -> None:
        entity_id = safe_int(self.device_id.get())
        run_in_worker(
            self,
            lambda: self.context.rust.set_entity_value(self.context.credentials, entity_id, value),
            lambda _result: self._show_device({"entity_id": entity_id, "value": value, "updated": True}),
        )
