from __future__ import annotations

import customtkinter as ctk

from rust_companion_plus.catalog import RECYCLE_CATALOG
from rust_companion_plus.services.tools import calculate_recycle
from rust_companion_plus.ui.common import MUTED, safe_int


UTILITY_SECTION = "Recycle"


class ToolsTab(ctk.CTkFrame):
    """Small utilities that are not already covered by the map or device hubs."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Utilities",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(
            self,
            text=(
                "A focused recycler calculator. Map coordinates belong in Map, "
                "and paired entities now live in Smart Devices."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            card,
            text="Recycler return calculator",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        ctk.CTkLabel(
            card,
            text="Choose a component and quantity to estimate configured returns.",
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.recycle_item = ctk.CTkOptionMenu(
            card,
            values=sorted(RECYCLE_CATALOG),
        )
        self.recycle_item.grid(row=2, column=0, sticky="ew", padx=16, pady=6)

        self.recycle_qty = ctk.CTkEntry(card, placeholder_text="Quantity")
        self.recycle_qty.insert(0, "1")
        self.recycle_qty.grid(row=3, column=0, sticky="ew", padx=16, pady=6)

        ctk.CTkButton(
            card,
            text="Calculate recycle returns",
            command=self.calculate_recycle,
        ).grid(row=4, column=0, sticky="ew", padx=16, pady=8)

        self.recycle_result = ctk.CTkTextbox(card, corner_radius=8)
        self.recycle_result.grid(
            row=5,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(0, 16),
        )
        self.calculate_recycle()

    def calculate_recycle(self) -> None:
        returns = calculate_recycle(
            self.recycle_item.get(),
            max(1, safe_int(self.recycle_qty.get(), 1)),
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

    def on_context_updated(self) -> None:
        return
