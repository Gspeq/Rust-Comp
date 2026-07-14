from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk
from typing import Any, Callable, Iterable

import customtkinter as ctk

from rust_companion_plus.services.item_catalog import RustItemCatalog
from rust_companion_plus.ui.common import MUTED, run_in_worker, safe_int


BLUEPRINT_MODES = (
    "Any offer",
    "No blueprints",
    "Sells blueprint",
    "Buys blueprint",
)
SORT_MODES = (
    "Item A-Z",
    "Shop A-Z",
    "Lowest cost",
    "Highest stock",
    "X position",
    "Y position",
)


@dataclass(frozen=True, slots=True)
class ShopFilters:
    buy_query: str = ""
    sell_query: str = ""
    shop_query: str = ""
    in_stock_only: bool = False
    blueprint_mode: str = "Any offer"
    min_stock: int = 0
    max_cost: int = 0
    sort_mode: str = "Item A-Z"


@dataclass(frozen=True, slots=True)
class ShopOrderRow:
    shop: str
    x: float
    y: float
    item_id: int
    item_name: str
    quantity: int
    currency_id: int
    currency_name: str
    cost: int
    stock: int
    item_is_blueprint: bool
    currency_is_blueprint: bool

    @property
    def shop_key(self) -> str:
        return f"{self.shop}|{self.x:.1f}|{self.y:.1f}"

    @property
    def item_display(self) -> str:
        suffix = " BP" if self.item_is_blueprint else ""
        return f"{self.item_name}{suffix} [{self.item_id}]"

    @property
    def currency_display(self) -> str:
        suffix = " BP" if self.currency_is_blueprint else ""
        return f"{self.currency_name}{suffix} [{self.currency_id}]"

    @property
    def flags(self) -> str:
        flags: list[str] = []
        if self.item_is_blueprint:
            flags.append("Sells BP")
        if self.currency_is_blueprint:
            flags.append("Buys BP")
        return ", ".join(flags) or "Regular"

    def values(self) -> tuple[Any, ...]:
        return (
            self.shop,
            f"{self.x:.0f}",
            f"{self.y:.0f}",
            self.item_display,
            self.quantity,
            self.currency_display,
            self.cost,
            self.stock,
            self.flags,
        )


def collect_shop_rows(
    markers: Iterable[dict[str, Any]],
    *,
    label: Callable[[Any], str],
    search_text: Callable[[Any], str],
    filters: ShopFilters,
) -> list[ShopOrderRow]:
    buy_query = filters.buy_query.strip().casefold()
    sell_query = filters.sell_query.strip().casefold()
    shop_query = filters.shop_query.strip().casefold()
    rows: list[ShopOrderRow] = []

    for marker in markers:
        if _as_int(marker.get("type")) != 3:
            continue

        shop = str(marker.get("name") or "Vending Machine").strip()
        if shop_query and shop_query not in shop.casefold():
            continue

        x = _as_float(marker.get("x"))
        y = _as_float(marker.get("y"))
        orders = marker.get("sell_orders") or []
        if not isinstance(orders, list):
            continue

        for order in orders:
            if not isinstance(order, dict):
                continue
            item_id = _as_int(order.get("item_id"))
            currency_id = _as_int(order.get("currency_id"))
            quantity = max(0, _as_int(order.get("quantity")))
            cost = max(0, _as_int(order.get("cost_per_item")))
            stock = max(0, _as_int(order.get("amount_in_stock")))
            item_bp = bool(order.get("item_is_blueprint"))
            currency_bp = bool(order.get("currency_is_blueprint"))

            if filters.in_stock_only and stock <= 0:
                continue
            if filters.min_stock > 0 and stock < filters.min_stock:
                continue
            if filters.max_cost > 0 and cost > filters.max_cost:
                continue
            if not _blueprint_matches(
                filters.blueprint_mode,
                item_bp,
                currency_bp,
            ):
                continue
            if buy_query and buy_query not in search_text(item_id):
                continue
            if sell_query and sell_query not in search_text(currency_id):
                continue

            rows.append(
                ShopOrderRow(
                    shop=shop,
                    x=x,
                    y=y,
                    item_id=item_id,
                    item_name=label(item_id),
                    quantity=quantity,
                    currency_id=currency_id,
                    currency_name=label(currency_id),
                    cost=cost,
                    stock=stock,
                    item_is_blueprint=item_bp,
                    currency_is_blueprint=currency_bp,
                )
            )

    return _sort_rows(rows, filters.sort_mode)


def _blueprint_matches(
    mode: str,
    item_is_blueprint: bool,
    currency_is_blueprint: bool,
) -> bool:
    if mode == "No blueprints":
        return not item_is_blueprint and not currency_is_blueprint
    if mode == "Sells blueprint":
        return item_is_blueprint
    if mode == "Buys blueprint":
        return currency_is_blueprint
    return True


def _sort_rows(
    rows: list[ShopOrderRow],
    mode: str,
) -> list[ShopOrderRow]:
    if mode == "Shop A-Z":
        key = lambda row: (
            row.shop.casefold(),
            row.item_name.casefold(),
            row.cost,
        )
    elif mode == "Lowest cost":
        key = lambda row: (
            row.cost,
            row.item_name.casefold(),
            row.shop.casefold(),
        )
    elif mode == "Highest stock":
        key = lambda row: (
            -row.stock,
            row.item_name.casefold(),
            row.shop.casefold(),
        )
    elif mode == "X position":
        key = lambda row: (row.x, row.y, row.shop.casefold())
    elif mode == "Y position":
        key = lambda row: (row.y, row.x, row.shop.casefold())
    else:
        key = lambda row: (
            row.item_name.casefold(),
            row.cost,
            row.shop.casefold(),
        )
    return sorted(rows, key=key)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class ShopsTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.catalog = RustItemCatalog()
        self._last_signature: tuple[tuple[Any, ...], ...] | None = None
        self._catalog_loading = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Vending Machine Search",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Live Rust+ shop offers refresh every 3 seconds.",
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="Refresh item names",
            width=150,
            command=self.refresh_catalog,
        ).grid(row=0, column=1, rowspan=2, padx=(10, 0))

        filters = ctk.CTkFrame(self)
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for column in range(6):
            filters.grid_columnconfigure(column, weight=1)

        self.buy_query = ctk.CTkEntry(
            filters,
            placeholder_text="I want to buy: item name or ID",
        )
        self.buy_query.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(10, 5),
            pady=(10, 5),
        )
        self.sell_query = ctk.CTkEntry(
            filters,
            placeholder_text="I want to sell: item/currency name or ID",
        )
        self.sell_query.grid(
            row=0,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=5,
            pady=(10, 5),
        )
        self.shop_query = ctk.CTkEntry(
            filters,
            placeholder_text="Shop name",
        )
        self.shop_query.grid(
            row=0,
            column=4,
            columnspan=2,
            sticky="ew",
            padx=(5, 10),
            pady=(10, 5),
        )

        for entry in (
            self.buy_query,
            self.sell_query,
            self.shop_query,
        ):
            entry.bind("<KeyRelease>", lambda _event: self.refresh())

        self.in_stock = ctk.CTkCheckBox(
            filters,
            text="In stock only",
            command=self.refresh,
        )
        self.in_stock.grid(
            row=1,
            column=0,
            sticky="w",
            padx=10,
            pady=(5, 10),
        )

        self.blueprint_mode = ctk.CTkOptionMenu(
            filters,
            values=list(BLUEPRINT_MODES),
            command=lambda _value: self.refresh(),
        )
        self.blueprint_mode.set("Any offer")
        self.blueprint_mode.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=5,
            pady=(5, 10),
        )

        self.min_stock = ctk.CTkEntry(
            filters,
            placeholder_text="Minimum stock",
        )
        self.min_stock.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=5,
            pady=(5, 10),
        )
        self.max_cost = ctk.CTkEntry(
            filters,
            placeholder_text="Maximum cost",
        )
        self.max_cost.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=5,
            pady=(5, 10),
        )
        for entry in (self.min_stock, self.max_cost):
            entry.bind("<KeyRelease>", lambda _event: self.refresh())

        self.sort_mode = ctk.CTkOptionMenu(
            filters,
            values=list(SORT_MODES),
            command=lambda _value: self.refresh(),
        )
        self.sort_mode.set("Item A-Z")
        self.sort_mode.grid(
            row=1,
            column=4,
            sticky="ew",
            padx=5,
            pady=(5, 10),
        )
        ctk.CTkButton(
            filters,
            text="Clear filters",
            command=self.clear_filters,
        ).grid(
            row=1,
            column=5,
            sticky="ew",
            padx=(5, 10),
            pady=(5, 10),
        )

        frame = ctk.CTkFrame(self)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        columns = (
            "shop",
            "x",
            "y",
            "sells",
            "quantity",
            "wants",
            "cost",
            "stock",
            "type",
        )
        self.tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
        )
        column_settings = (
            ("shop", "Shop", 220),
            ("x", "X", 70),
            ("y", "Y", 70),
            ("sells", "Shop sells", 235),
            ("quantity", "Qty", 60),
            ("wants", "Shop wants", 235),
            ("cost", "Cost", 70),
            ("stock", "Stock", 75),
            ("type", "Offer type", 115),
        )
        for column, heading, width in column_settings:
            self.tree.heading(column, text=heading)
            anchor = "w" if column in {"shop", "sells", "wants"} else "center"
            self.tree.column(
                column,
                width=width,
                minwidth=55,
                anchor=anchor,
            )
        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(10, 0),
            pady=(10, 0),
        )

        vertical = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.tree.yview,
        )
        vertical.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(0, 10),
            pady=(10, 0),
        )
        horizontal = ttk.Scrollbar(
            frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        horizontal.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 10),
        )
        self.tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )

        self.status = ctk.CTkLabel(
            self,
            text="Connect to load vending markers.",
            anchor="w",
        )
        self.status.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        self.after(100, self._load_catalog)

    def current_filters(self) -> ShopFilters:
        return ShopFilters(
            buy_query=self.buy_query.get(),
            sell_query=self.sell_query.get(),
            shop_query=self.shop_query.get(),
            in_stock_only=bool(self.in_stock.get()),
            blueprint_mode=self.blueprint_mode.get(),
            min_stock=max(0, safe_int(self.min_stock.get())),
            max_cost=max(0, safe_int(self.max_cost.get())),
            sort_mode=self.sort_mode.get(),
        )

    def refresh(self) -> None:
        snapshot = self.context.snapshot
        if snapshot is None:
            self.status.configure(
                text="Connect to load vending markers."
            )
            return

        rows = collect_shop_rows(
            snapshot.markers,
            label=self.catalog.label,
            search_text=self.catalog.search_text,
            filters=self.current_filters(),
        )
        signature = tuple(row.values() for row in rows)

        if signature != self._last_signature:
            y_position = self.tree.yview()[0] if self.tree.get_children() else 0.0
            selected_values = {
                tuple(self.tree.item(item, "values"))
                for item in self.tree.selection()
            }
            self.tree.delete(*self.tree.get_children())
            reselections: list[str] = []
            for row in rows:
                item = self.tree.insert("", "end", values=row.values())
                if tuple(str(value) for value in row.values()) in selected_values:
                    reselections.append(item)
            if reselections:
                self.tree.selection_set(reselections)
            self.tree.yview_moveto(y_position)
            self._last_signature = signature

        shop_count = len({row.shop_key for row in rows})
        refreshed = datetime.now().strftime("%H:%M:%S")
        self.status.configure(
            text=(
                f"{len(rows)} matching offer(s) from {shop_count} shop(s) · "
                f"{self.catalog.description()} · updated {refreshed}"
            )
        )

    def clear_filters(self) -> None:
        for entry in (
            self.buy_query,
            self.sell_query,
            self.shop_query,
            self.min_stock,
            self.max_cost,
        ):
            entry.delete(0, "end")
        self.in_stock.deselect()
        self.blueprint_mode.set("Any offer")
        self.sort_mode.set("Item A-Z")
        self.refresh()

    def _load_catalog(self, *, force: bool = False) -> None:
        if self._catalog_loading:
            return
        self._catalog_loading = True
        self.status.configure(text="Loading Rust item names…")

        work = self.catalog.refresh if force else self.catalog.load

        def success(_count: int) -> None:
            self._catalog_loading = False
            self._last_signature = None
            self.refresh()

        def error(exc: Exception) -> None:
            self._catalog_loading = False
            self.catalog.last_error = str(exc)
            self._last_signature = None
            self.refresh()

        run_in_worker(self, work, success, error)

    def refresh_catalog(self) -> None:
        self._load_catalog(force=True)

    def on_context_updated(self) -> None:
        self.refresh()
