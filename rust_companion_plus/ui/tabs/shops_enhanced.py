from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

import customtkinter as ctk

from rust_companion_plus.services.shop_value import (
    ScoredShopRow,
    score_shop_rows,
    sort_scored_rows,
)
from rust_companion_plus.ui.common import MUTED, run_in_worker
from rust_companion_plus.ui.tabs.shops import (
    BLUEPRINT_MODES,
    ShopFilters,
    ShopsTab as BaseShopsTab,
    collect_shop_rows,
)


VALUE_SORT_MODES = (
    "Best value",
    "Item A-Z",
    "Shop A-Z",
    "Grid",
    "Lowest cost",
    "Highest stock",
)
VALUE_HISTORY_KEY = "shop_value_history"


class ShopsTab(BaseShopsTab):
    """Simplified marketplace with background value scoring and advanced filters."""

    def __init__(self, master, context):
        self._score_busy = False
        self._score_generation = 0
        self._raw_signature: tuple[tuple[Any, ...], ...] | None = None
        self._scored_rows: list[ScoredShopRow] = []
        self._pending_refresh = False
        self._last_requested_sort = "Best value"
        super().__init__(master, context)

    def _build_filter_bar(self) -> None:
        tabs = ctk.CTkTabview(self, corner_radius=10, height=90)
        tabs.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        tabs.add("Simple")
        tabs.add("Advanced")
        self.filter_tabs = tabs

        simple = tabs.tab("Simple")
        simple.grid_columnconfigure(1, weight=1)
        self.in_stock = ctk.CTkCheckBox(
            simple,
            text="In stock only",
            command=self.refresh,
        )
        self.in_stock.grid(row=0, column=0, padx=(12, 10), pady=10)

        self.sort_mode = ctk.CTkOptionMenu(
            simple,
            values=list(VALUE_SORT_MODES),
            command=lambda _value: self.refresh(),
        )
        self.sort_mode.set("Best value")
        self.sort_mode.grid(row=0, column=1, sticky="ew", padx=5, pady=10)

        ctk.CTkButton(
            simple,
            text="Clear searches",
            width=120,
            fg_color="transparent",
            border_width=1,
            command=self.clear_filters,
        ).grid(row=0, column=2, padx=5, pady=10)

        self.copy_button = ctk.CTkButton(
            simple,
            text="Copy selected location",
            width=170,
            state="disabled",
            command=self.copy_selected_location,
        )
        self.copy_button.grid(row=0, column=3, padx=(5, 12), pady=10)

        advanced = tabs.tab("Advanced")
        advanced.grid_columnconfigure((1, 2), weight=1)
        ctk.CTkLabel(
            advanced,
            text="Blueprint mode",
            text_color=MUTED,
        ).grid(row=0, column=0, padx=(12, 6), pady=10)
        self.blueprint_mode = ctk.CTkOptionMenu(
            advanced,
            values=list(BLUEPRINT_MODES),
            width=160,
            command=lambda _value: self.refresh(),
        )
        self.blueprint_mode.set("Any offer")
        self.blueprint_mode.grid(row=0, column=1, sticky="ew", padx=5, pady=10)

        self.min_stock = ctk.CTkEntry(
            advanced,
            placeholder_text="Minimum stock",
            height=36,
        )
        self.max_cost = ctk.CTkEntry(
            advanced,
            placeholder_text="Maximum total cost",
            height=36,
        )
        self.min_stock.grid(row=0, column=2, sticky="ew", padx=5, pady=10)
        self.max_cost.grid(row=0, column=3, sticky="ew", padx=(5, 12), pady=10)
        for entry in (self.min_stock, self.max_cost):
            entry.bind("<KeyRelease>", lambda _event: self.refresh())

    def _build_results_table(self) -> None:
        super()._build_results_table()
        columns = (
            "shop",
            "grid",
            "coordinates",
            "sells",
            "quantity",
            "wants",
            "cost",
            "stock",
            "type",
            "value",
            "deal",
        )
        self.tree.configure(columns=columns)
        self.tree.heading("value", text="Value")
        self.tree.heading("deal", text="Deal")
        self.tree.column("value", width=64, minwidth=58, anchor="center", stretch=False)
        self.tree.column("deal", width=108, minwidth=92, anchor="center", stretch=False)
        self.tree.tag_configure(
            "cant_miss",
            background="#14532d",
            foreground="#ffffff",
        )
        self.tree.tag_configure(
            "steal",
            background="#166534",
            foreground="#dcfce7",
        )
        self.tree.tag_configure(
            "good_value",
            background="#164e63",
            foreground="#cffafe",
        )
        self.tree.tag_configure(
            "overpriced",
            background="#7f1d1d",
            foreground="#fee2e2",
        )
        self.table_note.configure(
            text="Best value compares identical item/currency trades"
        )

    def clear_filters(self) -> None:
        for entry in (
            self.buy_query,
            self.sell_query,
            self.location_query,
            self.min_stock,
            self.max_cost,
        ):
            entry.delete(0, "end")
        self.in_stock.deselect()
        self.blueprint_mode.set("Any offer")
        self.sort_mode.set("Best value")
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.context.snapshot
        if snapshot is None:
            self.status.configure(text="Connect to load vending markers.")
            self.table_note.configure(text="Rust+ connection required")
            return

        filters = self.current_filters()
        scoring_filters: ShopFilters = (
            replace(filters, sort_mode="Item A-Z")
            if filters.sort_mode == "Best value"
            else filters
        )
        map_size = self._map_size()
        rows = collect_shop_rows(
            snapshot.markers,
            map_size=map_size,
            label=self.catalog.label,
            search_text=self.catalog.search_text,
            filters=scoring_filters,
        )
        raw_signature = tuple(row.values() for row in rows)

        if (
            raw_signature == self._raw_signature
            and self._scored_rows
            and not self._score_busy
        ):
            self._scored_rows = sort_scored_rows(
                self._scored_rows,
                filters.sort_mode,
            )
            self._render_scored_rows(map_size)
            return

        if self._score_busy:
            self._pending_refresh = True
            return

        self._score_busy = True
        self._pending_refresh = False
        self._score_generation += 1
        generation = self._score_generation
        history = self.context.store.get(VALUE_HISTORY_KEY, {}) or {}
        self.table_note.configure(text="Scoring comparable live offers…")

        def work():
            scored, updated_history = score_shop_rows(rows, history)
            return (
                sort_scored_rows(scored, filters.sort_mode),
                updated_history,
                raw_signature,
                map_size,
            )

        def success(payload) -> None:
            if generation != self._score_generation:
                return
            self._score_busy = False
            scored, updated_history, signature, effective_map_size = payload
            self.context.store.set(VALUE_HISTORY_KEY, updated_history)
            self._scored_rows = list(scored)
            self._raw_signature = signature
            self._last_requested_sort = filters.sort_mode
            self._render_scored_rows(effective_map_size)
            if self._pending_refresh:
                self.after(1, self.refresh)

        def error(exc: Exception) -> None:
            self._score_busy = False
            self.table_note.configure(text=f"Value scoring failed: {exc}")
            self.status.configure(text="Marketplace data loaded, but value scoring failed.")

        run_in_worker(self, work, success, error)

    def _render_scored_rows(self, map_size: int) -> None:
        selected = self._selected_row()
        selected_key = (
            (selected.shop_key, selected.item_id, selected.currency_id, selected.cost)
            if selected is not None
            else None
        )
        y_position = self.tree.yview()[0] if self.tree.get_children() else 0.0
        self.tree.delete(*self.tree.get_children())
        self._visible_rows = [item.row for item in self._scored_rows]

        selected_item = None
        for index, item in enumerate(self._scored_rows):
            row = item.row
            label = item.deal.label
            if label == "CAN'T MISS":
                tag = "cant_miss"
            elif label == "STEAL":
                tag = "steal"
            elif label == "GOOD VALUE":
                tag = "good_value"
            elif label == "OVERPRICED":
                tag = "overpriced"
            elif row.stock <= 0:
                tag = "out"
            elif row.item_is_blueprint or row.currency_is_blueprint:
                tag = "blueprint"
            else:
                tag = "even" if index % 2 == 0 else "odd"

            tree_item = self.tree.insert(
                "",
                "end",
                values=row.values() + (item.deal.score, label),
                tags=(tag,),
            )
            identity = (row.shop_key, row.item_id, row.currency_id, row.cost)
            if identity == selected_key:
                selected_item = tree_item

        self.tree.yview_moveto(y_position)
        if selected_item is not None:
            self.tree.selection_set(selected_item)
            self.tree.focus(selected_item)
        else:
            self._clear_selection_detail()

        rows = self._visible_rows
        shop_count = len({row.shop_key for row in rows})
        in_stock_count = sum(row.stock > 0 for row in rows)
        steal_count = sum(
            item.deal.label in {"STEAL", "CAN'T MISS"}
            for item in self._scored_rows
        )
        refreshed = datetime.now().strftime("%H:%M:%S")
        self.offers_metric.set(str(len(rows)), "current searches")
        self.shops_metric.set(str(shop_count), "unique locations")
        self.stock_metric.set(str(in_stock_count), f"{steal_count} highlighted deal(s)")
        self.map_metric.set(f"{map_size or '—'}", "world size / grids")
        self.table_note.configure(text=f"Value scores updated {refreshed}")
        self.status.configure(
            text=(
                f"{len(rows)} offer(s) · {shop_count} shop(s) · "
                "value compares unit cost only within identical item, payment, and blueprint markets"
            )
        )

    def _selected_scored(self) -> ScoredShopRow | None:
        index = self._selected_index()
        if index is None or index >= len(self._scored_rows):
            return None
        return self._scored_rows[index]

    def _selection_changed(self, _event: Any = None) -> None:
        super()._selection_changed(_event)
        item = self._selected_scored()
        if item is None:
            return
        deal = item.deal
        direction = (
            f"{abs(deal.discount_percent)}% below market"
            if deal.discount_percent > 0
            else f"{abs(deal.discount_percent)}% above market"
            if deal.discount_percent < 0
            else "at market"
        )
        row = item.row
        self.selection_detail.configure(
            text=(
                f"{row.quantity} × {row.item_name} for {row.cost} × {row.currency_name} · "
                f"{deal.label} {deal.score}/100 · {direction} · "
                f"benchmark {deal.benchmark:g} per unit · confidence {deal.confidence}"
            )
        )
