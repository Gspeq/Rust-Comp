from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

import customtkinter as ctk
from tkinter import ttk

from rust_companion_plus.services.deal_notifications import (
    DEAL_ALERT_SEEN_KEY,
    NOTIFICATION_SETTINGS_KEY,
    collect_deal_alerts,
    normalize_notification_settings,
)
from rust_companion_plus.services.shop_value import (
    ScoredShopRow,
    score_shop_rows,
    sort_scored_rows,
)
from rust_companion_plus.ui.common import (
    MUTED,
    run_in_worker,
)
from rust_companion_plus.ui.tabs.shops import (
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
COMPACT_COLUMNS = (
    "shop",
    "grid",
    "sells",
    "quantity",
    "wants",
    "cost",
    "stock",
    "deal",
)
COMPACT_COLUMN_WIDTHS = {
    "shop": 150,
    "grid": 54,
    "sells": 170,
    "quantity": 54,
    "wants": 150,
    "cost": 58,
    "stock": 58,
    "deal": 155,
}



class ShopsTab(BaseShopsTab):
    # Plain-text deal ratings with background scoring and alerts.

    def __init__(self, master, context):
        self._score_busy = False
        self._score_generation = 0
        self._raw_signature: (
            tuple[tuple[Any, ...], ...]
            | None
        ) = None
        self._scored_rows: list[
            ScoredShopRow
        ] = []
        self._pending_refresh = False
        self._last_requested_sort = (
            "Best value"
        )
        super().__init__(master, context)

    def _build_filter_bar(self) -> None:
        tabs = ctk.CTkTabview(
            self,
            corner_radius=10,
            height=90,
        )
        tabs.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        tabs.add("Simple")
        tabs.add("Advanced")
        self.filter_tabs = tabs

        simple = tabs.tab("Simple")
        simple.grid_columnconfigure(
            1,
            weight=1,
        )
        self.in_stock = ctk.CTkCheckBox(
            simple,
            text="In stock only",
            command=self.refresh,
        )
        self.in_stock.grid(
            row=0,
            column=0,
            padx=(12, 10),
            pady=10,
        )

        self.sort_mode = ctk.CTkOptionMenu(
            simple,
            values=list(VALUE_SORT_MODES),
            command=lambda _value: (
                self.refresh()
            ),
        )
        self.sort_mode.set("Best value")
        self.sort_mode.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=5,
            pady=10,
        )

        ctk.CTkButton(
            simple,
            text="Clear searches",
            width=120,
            fg_color="transparent",
            border_width=1,
            command=self.clear_filters,
        ).grid(
            row=0,
            column=2,
            padx=5,
            pady=10,
        )

        self.copy_button = ctk.CTkButton(
            simple,
            text="Copy selected location",
            width=170,
            state="disabled",
            command=self.copy_selected_location,
        )
        self.copy_button.grid(
            row=0,
            column=3,
            padx=(5, 12),
            pady=10,
        )

        # Blueprint offers remain visible and are marked with a clear BP prefix.
        # A hidden StringVar keeps the base filter contract on "Any offer"
        # without exposing a separate BP filter control to the user.
        self.blueprint_mode = ctk.StringVar(value="Any offer")

        advanced = tabs.tab("Advanced")
        advanced.grid_columnconfigure((0, 1), weight=1)
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
        self.min_stock.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(12, 5),
            pady=10,
        )
        self.max_cost.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(5, 12),
            pady=10,
        )
        for entry in (self.min_stock, self.max_cost):
            entry.bind(
                "<KeyRelease>",
                lambda _event: self.refresh(),
            )

    def _build_results_table(self) -> None:
        super()._build_results_table()
        self.tree.configure(columns=COMPACT_COLUMNS)
        headings = {
            "shop": "Shop",
            "grid": "Grid",
            "sells": "Sells",
            "quantity": "Qty",
            "wants": "Wants",
            "cost": "Cost",
            "stock": "Stock",
            "deal": "Deal rating",
        }
        for name, heading in headings.items():
            self.tree.heading(name, text=heading)
            self.tree.column(
                name,
                width=COMPACT_COLUMN_WIDTHS[name],
                minwidth=max(42, COMPACT_COLUMN_WIDTHS[name] // 2),
                anchor="w" if name in {"shop", "sells", "wants", "deal"} else "center",
                stretch=name in {"shop", "sells", "wants", "deal"},
            )
        self._hide_horizontal_scrollbars(self)
        self.table_note.configure(
            text=(
                "BP listings are marked directly. Best value uses unit price, "
                "live peers, history, stock, rank, confidence, and outlier detection."
            )
        )

    def _hide_horizontal_scrollbars(self, widget: Any) -> None:
        for child in widget.winfo_children():
            if isinstance(child, ttk.Scrollbar):
                try:
                    if str(child.cget("orient")) == "horizontal":
                        child.grid_remove()
                        continue
                except Exception:
                    pass
            self._hide_horizontal_scrollbars(child)

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
        self.blueprint_mode.set(
            "Any offer"
        )
        self.sort_mode.set("Best value")
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.context.snapshot
        if snapshot is None:
            self.status.configure(
                text=(
                    "Connect to load "
                    "vending markers."
                )
            )
            self.table_note.configure(
                text="Rust+ connection required"
            )
            return

        filters = self.current_filters()
        scoring_filters: ShopFilters = (
            replace(
                filters,
                sort_mode="Item A-Z",
            )
            if filters.sort_mode
            == "Best value"
            else filters
        )
        map_size = self._map_size()
        rows = collect_shop_rows(
            snapshot.markers,
            map_size=map_size,
            label=self.catalog.label,
            search_text=(
                self.catalog.search_text
            ),
            filters=scoring_filters,
        )
        raw_signature = tuple(
            row.values()
            for row in rows
        )

        if (
            raw_signature
            == self._raw_signature
            and self._scored_rows
            and not self._score_busy
        ):
            self._scored_rows = (
                sort_scored_rows(
                    self._scored_rows,
                    filters.sort_mode,
                )
            )
            self._render_scored_rows(
                map_size
            )
            return

        if self._score_busy:
            self._pending_refresh = True
            return

        self._score_busy = True
        self._pending_refresh = False
        self._score_generation += 1
        generation = (
            self._score_generation
        )
        history = self.context.store.get(
            VALUE_HISTORY_KEY,
            {},
        ) or {}
        self.table_note.configure(
            text=(
                "Analyzing comparable "
                "live offers..."
            )
        )

        def work():
            scored, updated_history = (
                score_shop_rows(
                    rows,
                    history,
                )
            )
            return (
                sort_scored_rows(
                    scored,
                    filters.sort_mode,
                ),
                updated_history,
                raw_signature,
                map_size,
            )

        def success(payload) -> None:
            if (
                generation
                != self._score_generation
            ):
                return
            self._score_busy = False
            (
                scored,
                updated_history,
                signature,
                effective_map_size,
            ) = payload
            self.context.store.set(
                VALUE_HISTORY_KEY,
                updated_history,
            )
            self._scored_rows = list(
                scored
            )
            self._raw_signature = signature
            self._last_requested_sort = (
                filters.sort_mode
            )
            self._render_scored_rows(
                effective_map_size
            )
            self._publish_new_deal_alerts()
            if self._pending_refresh:
                self.after(
                    1,
                    self.refresh,
                )

        def error(exc: Exception) -> None:
            self._score_busy = False
            self.table_note.configure(
                text=(
                    "Value scoring failed: "
                    f"{exc}"
                )
            )
            self.status.configure(
                text=(
                    "Marketplace data loaded, "
                    "but deal analysis failed."
                )
            )

        run_in_worker(
            self,
            work,
            success,
            error,
        )

    def _profile_key(self) -> str:
        selected = (
            self.context.detection.get(
                "selected"
            )
            or {}
        )
        return str(
            self.context.active_profile_key
            or selected.get("endpoint")
            or self.context.credentials.host
            or "unknown-server"
        )

    def _publish_new_deal_alerts(
        self,
    ) -> None:
        seen = self.context.store.get(
            DEAL_ALERT_SEEN_KEY,
            {},
        ) or {}
        settings = normalize_notification_settings(
            self.context.store.get(
                NOTIFICATION_SETTINGS_KEY,
                {},
            )
        )
        alerts, updated = (
            collect_deal_alerts(
                self._scored_rows,
                seen,
                profile_key=(
                    self._profile_key()
                ),
                settings=settings,
            )
        )
        self.context.store.set(
            DEAL_ALERT_SEEN_KEY,
            updated,
        )
        app = getattr(
            self.context,
            "app",
            None,
        )
        publish = getattr(
            app,
            "publish_deal_alerts",
            None,
        )
        if alerts and callable(publish):
            publish(alerts)

    def _render_scored_rows(
        self,
        map_size: int,
    ) -> None:
        selected = self._selected_row()
        selected_key = (
            (
                selected.shop_key,
                selected.item_id,
                selected.currency_id,
                selected.cost,
            )
            if selected is not None
            else None
        )
        y_position = (
            self.tree.yview()[0]
            if self.tree.get_children()
            else 0.0
        )
        self.tree.delete(
            *self.tree.get_children()
        )
        self._visible_rows = [
            item.row
            for item in self._scored_rows
        ]

        selected_item = None
        for index, item in enumerate(
            self._scored_rows
        ):
            row = item.row
            # Ratings are text-only. Rows use neutral
            # striping instead of green/red deal colors.
            tag = (
                "even"
                if index % 2 == 0
                else "odd"
            )
            tree_item = self.tree.insert(
                "",
                "end",
                values=(
                    row.shop,
                    row.grid,
                    (
                        f"BP: {row.item_name}"
                        if row.item_is_blueprint
                        else row.item_name
                    ),
                    row.quantity,
                    (
                        f"BP: {row.currency_name}"
                        if row.currency_is_blueprint
                        else row.currency_name
                    ),
                    row.cost,
                    row.stock,
                    item.deal.label,
                ),
                tags=(tag,),
            )
            identity = (
                row.shop_key,
                row.item_id,
                row.currency_id,
                row.cost,
            )
            if identity == selected_key:
                selected_item = tree_item

        self.tree.yview_moveto(
            y_position
        )
        if selected_item is not None:
            self.tree.selection_set(
                selected_item
            )
            self.tree.focus(
                selected_item
            )
        else:
            self._clear_selection_detail()

        rows = self._visible_rows
        shop_count = len(
            {
                row.shop_key
                for row in rows
            }
        )
        in_stock_count = sum(
            row.stock > 0
            for row in rows
        )
        alert_count = sum(
            bool(item.deal.alert_level)
            for item in self._scored_rows
        )
        refreshed = (
            datetime.now().strftime(
                "%H:%M:%S"
            )
        )
        self.offers_metric.set(
            str(len(rows)),
            "current searches",
        )
        self.shops_metric.set(
            str(shop_count),
            "unique locations",
        )
        self.stock_metric.set(
            str(in_stock_count),
            (
                f"{alert_count} "
                "alert-worthy listing(s)"
            ),
        )
        self.map_metric.set(
            f"{map_size or '—'}",
            "world size / grids",
        )
        self.table_note.configure(
            text=(
                "Deal ratings updated "
                f"{refreshed}"
            )
        )
        self.status.configure(
            text=(
                f"{len(rows)} offer(s) · "
                f"{shop_count} shop(s) · "
                "ratings compare only identical "
                "item and payment markets; BP status is compared separately"
            )
        )

    def _selected_scored(
        self,
    ) -> ScoredShopRow | None:
        index = self._selected_index()
        if (
            index is None
            or index
            >= len(self._scored_rows)
        ):
            return None
        return self._scored_rows[index]

    def _selection_changed(
        self,
        _event: Any = None,
    ) -> None:
        super()._selection_changed(
            _event
        )
        item = self._selected_scored()
        if item is None:
            return
        row = item.row
        deal = item.deal
        self.selection_detail.configure(
            text=(
                f"{row.quantity} × "
                f"{'BP: ' if row.item_is_blueprint else ''}{row.item_name} for "
                f"{row.cost} × "
                f"{'BP: ' if row.currency_is_blueprint else ''}{row.currency_name} · "
                f"{deal.label} · "
                f"{deal.reason}"
            )
        )
