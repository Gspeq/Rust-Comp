from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from rust_companion_plus.ui.common import SectionCard


class ShopsTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text="Vending Machine Search", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        filters = ctk.CTkFrame(self)
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        filters.grid_columnconfigure(0, weight=1)
        self.query = ctk.CTkEntry(filters, placeholder_text="Search marker name, item ID or currency ID")
        self.query.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.query.bind("<KeyRelease>", lambda _event: self.refresh())
        self.in_stock = ctk.CTkCheckBox(filters, text="In stock only", command=self.refresh)
        self.in_stock.grid(row=0, column=1, padx=10)

        frame = ctk.CTkFrame(self)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        columns = ("shop", "position", "item", "quantity", "currency", "cost", "stock")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, width in [
            ("shop", 210), ("position", 140), ("item", 110), ("quantity", 80),
            ("currency", 110), ("cost", 80), ("stock", 80)
        ]:
            self.tree.heading(column, text=column.title())
            self.tree.column(column, width=width, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=10)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.status = ctk.CTkLabel(self, text="Connect to load vending markers.", anchor="w")
        self.status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        snapshot = self.context.snapshot
        if snapshot is None:
            self.status.configure(text="Connect to load vending markers.")
            return
        query = self.query.get().strip().lower()
        count = 0
        for marker in snapshot.markers:
            if int(marker.get("type", 0) or 0) != 3:
                continue
            shop = str(marker.get("name") or "Vending Machine")
            position = f"x={float(marker.get('x', 0)):.0f}, y={float(marker.get('y', 0)):.0f}"
            orders = marker.get("sell_orders", []) or [{}]
            for order in orders:
                stock = int(order.get("amount_in_stock", 0) or 0)
                if self.in_stock.get() and stock <= 0:
                    continue
                haystack = " ".join(
                    [
                        shop.lower(),
                        str(order.get("item_id", "")),
                        str(order.get("currency_id", "")),
                    ]
                )
                if query and query not in haystack:
                    continue
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        shop,
                        position,
                        order.get("item_id", "—"),
                        order.get("quantity", "—"),
                        order.get("currency_id", "—"),
                        order.get("cost_per_item", "—"),
                        stock,
                    ),
                )
                count += 1
        self.status.configure(text=f"{count} matching sell order(s). Item names require an item-definition catalog.")

    def on_context_updated(self) -> None:
        self.refresh()
