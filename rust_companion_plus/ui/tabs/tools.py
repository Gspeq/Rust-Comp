
from __future__ import annotations

import customtkinter as ctk

from rust_companion_plus.catalog import RECYCLE_CATALOG
from rust_companion_plus.services.tools import (
    calculate_recycle,
    calculate_upkeep_hours,
)
from rust_companion_plus.ui.common import (
    MUTED,
    run_in_worker,
    safe_float,
    safe_int,
)


class ToolsTab(ctk.CTkFrame):
    """Keep only utilities that provide direct in-game value."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Useful Utilities",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            self,
            text=(
                "The speculative building, farming, clone, and loot planners "
                "were removed. This page keeps upkeep, recycle returns, and "
                "live Rust+ smart-device controls."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=2, column=0, sticky="nsew")
        for name in (
            "TC Upkeep",
            "Recycle",
            "Smart Devices",
        ):
            tabs.add(name)

        self._upkeep(tabs.tab("TC Upkeep"))
        self._recycle(tabs.tab("Recycle"))
        self._devices(tabs.tab("Smart Devices"))

    def _upkeep(self, parent) -> None:
        parent.grid_columnconfigure((0, 1, 2), weight=1)
        resources = [
            "Wood",
            "Stone",
            "Metal Fragments",
            "High Quality Metal",
        ]
        self.upkeep_inventory = {}
        self.upkeep_rate = {}

        for row, resource in enumerate(resources):
            ctk.CTkLabel(
                parent,
                text=resource,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=10,
                pady=6,
            )
            inventory = ctk.CTkEntry(
                parent,
                placeholder_text="Currently in TC",
            )
            inventory.grid(
                row=row,
                column=1,
                sticky="ew",
                padx=5,
                pady=6,
            )
            rate = ctk.CTkEntry(
                parent,
                placeholder_text="Hourly upkeep",
            )
            rate.grid(
                row=row,
                column=2,
                sticky="ew",
                padx=5,
                pady=6,
            )
            self.upkeep_inventory[resource] = inventory
            self.upkeep_rate[resource] = rate

        ctk.CTkButton(
            parent,
            text="Calculate time remaining",
            command=self.calculate_upkeep,
        ).grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=10,
            pady=10,
        )
        self.upkeep_result = ctk.CTkTextbox(
            parent,
            height=260,
        )
        self.upkeep_result.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="nsew",
            padx=10,
            pady=10,
        )

    def calculate_upkeep(self) -> None:
        inventory = {
            name: safe_float(widget.get())
            for name, widget in self.upkeep_inventory.items()
        }
        rates = {
            name: safe_float(widget.get())
            for name, widget in self.upkeep_rate.items()
        }
        total, details = calculate_upkeep_hours(
            inventory,
            rates,
        )
        lines = []
        if total == float("inf"):
            lines.append(
                "Enter at least one non-zero hourly upkeep rate."
            )
        else:
            lines.append(
                f"Limiting resource: {total:.1f} hours "
                f"({total / 24:.2f} days)"
            )
        lines.extend(
            f"{resource}: {hours:.1f} hours"
            for resource, hours in details.items()
        )
        self.upkeep_result.delete("1.0", "end")
        self.upkeep_result.insert(
            "1.0",
            "\n".join(lines),
        )

    def _recycle(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self.recycle_item = ctk.CTkOptionMenu(
            parent,
            values=sorted(RECYCLE_CATALOG),
        )
        self.recycle_item.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=10,
            pady=10,
        )
        self.recycle_qty = ctk.CTkEntry(
            parent,
            placeholder_text="Quantity",
        )
        self.recycle_qty.insert(0, "1")
        self.recycle_qty.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=10,
            pady=10,
        )
        ctk.CTkButton(
            parent,
            text="Calculate recycle returns",
            command=self.calculate_recycle,
        ).grid(
            row=2,
            column=0,
            sticky="ew",
            padx=10,
            pady=10,
        )
        self.recycle_result = ctk.CTkTextbox(
            parent,
            height=300,
        )
        self.recycle_result.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=10,
            pady=10,
        )

    def calculate_recycle(self) -> None:
        returns = calculate_recycle(
            self.recycle_item.get(),
            safe_int(self.recycle_qty.get(), 1),
        )
        self.recycle_result.delete("1.0", "end")
        self.recycle_result.insert(
            "1.0",
            "\n".join(
                f"{name}: {amount:g}"
                for name, amount in returns.items()
            )
            or "No configured recycle return.",
        )

    def _devices(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            parent,
            text=(
                "Control a paired Rust+ smart entity by its entity ID."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=10,
            pady=(10, 4),
        )
        self.device_id = ctk.CTkEntry(
            parent,
            placeholder_text="Paired entity ID",
        )
        self.device_id.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=10,
            pady=10,
        )
        buttons = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        buttons.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=10,
        )
        buttons.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(
            buttons,
            text="Read status",
            command=self.read_device,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=4,
        )
        ctk.CTkButton(
            buttons,
            text="Turn ON",
            command=lambda: self.set_device(True),
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=4,
        )
        ctk.CTkButton(
            buttons,
            text="Turn OFF",
            command=lambda: self.set_device(False),
        ).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=4,
        )
        self.device_status = ctk.CTkTextbox(
            parent,
            height=300,
        )
        self.device_status.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=10,
            pady=10,
        )

    def read_device(self) -> None:
        entity_id = safe_int(self.device_id.get())
        if entity_id <= 0:
            self._show_device(
                {"error": "Enter a valid paired entity ID."}
            )
            return
        run_in_worker(
            self,
            lambda: self.context.rust.get_entity(
                self.context.credentials,
                entity_id,
            ),
            self._show_device,
            lambda exc: self._show_device(
                {"error": str(exc)}
            ),
        )

    def set_device(self, value: bool) -> None:
        entity_id = safe_int(self.device_id.get())
        if entity_id <= 0:
            self._show_device(
                {"error": "Enter a valid paired entity ID."}
            )
            return

        def success(_result) -> None:
            self.read_device()

        run_in_worker(
            self,
            lambda: self.context.rust.set_entity_value(
                self.context.credentials,
                entity_id,
                value,
            ),
            success,
            lambda exc: self._show_device(
                {"error": str(exc)}
            ),
        )

    def _show_device(self, result) -> None:
        self.device_status.delete("1.0", "end")
        if isinstance(result, dict):
            self.device_status.insert(
                "1.0",
                "\n".join(
                    f"{key}: {value}"
                    for key, value in result.items()
                ),
            )
        else:
            self.device_status.insert(
                "1.0",
                str(result),
            )
