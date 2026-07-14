from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk
from typing import Any, Callable, Iterable

import customtkinter as ctk

from rust_companion_plus.services.item_catalog import RustItemCatalog
from rust_companion_plus.ui.common import (
    ACCENT,
    DANGER,
    MUTED,
    SUCCESS,
    run_in_worker,
    safe_int,
)


BLUEPRINT_MODES = (
    "Any offer",
    "No blueprints",
    "Sells blueprint",
    "Buys blueprint",
)
SORT_MODES = (
    "Item A-Z",
    "Shop A-Z",
    "Grid",
    "Lowest cost",
    "Highest stock",
)


@dataclass(frozen=True, slots=True)
class ShopFilters:
    buy_query: str = ""
    sell_query: str = ""
    location_query: str = ""
    in_stock_only: bool = False
    blueprint_mode: str = "Any offer"
    min_stock: int = 0
    max_cost: int = 0
    sort_mode: str = "Item A-Z"


@dataclass(frozen=True, slots=True)
class ShopOrderRow:
    shop: str
    grid: str
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
        return f"{self.shop}|{self.grid}|{self.x:.1f}|{self.y:.1f}"

    @property
    def item_display(self) -> str:
        suffix = "  • BP" if self.item_is_blueprint else ""
        return f"{self.item_name}{suffix}"

    @property
    def currency_display(self) -> str:
        suffix = "  • BP" if self.currency_is_blueprint else ""
        return f"{self.currency_name}{suffix}"

    @property
    def coordinates(self) -> str:
        return f"{self.x:.0f}, {self.y:.0f}"

    @property
    def offer_type(self) -> str:
        flags: list[str] = []
        if self.item_is_blueprint:
            flags.append("Sells BP")
        if self.currency_is_blueprint:
            flags.append("Buys BP")
        return " + ".join(flags) or "Standard"

    @property
    def trade_sentence(self) -> str:
        return (
            f"{self.shop} at {self.grid} sells "
            f"{self.quantity} × {self.item_name} for "
            f"{self.cost} × {self.currency_name}. "
            f"Stock: {self.stock}."
        )

    def values(self) -> tuple[Any, ...]:
        return (
            self.shop,
            self.grid,
            self.coordinates,
            self.item_display,
            self.quantity,
            self.currency_display,
            self.cost,
            self.stock,
            self.offer_type,
        )


def rust_grid_reference(
    x: Any,
    y: Any,
    map_size: Any,
) -> str:
    try:
        numeric_x = float(x)
        numeric_y = float(y)
        numeric_size = int(float(map_size))
    except (TypeError, ValueError):
        return "—"
    if numeric_size <= 0:
        return "—"

    try:
        from rustplus import convert_coordinates

        column, row = convert_coordinates(
            (numeric_x, numeric_y),
            numeric_size,
        )
    except Exception:
        return "—"
    return f"{column}{row}"


def collect_shop_rows(
    markers: Iterable[dict[str, Any]],
    *,
    map_size: int,
    label: Callable[[Any], str],
    search_text: Callable[[Any], str],
    filters: ShopFilters,
    grid_label: Callable[[Any, Any, Any], str] = rust_grid_reference,
) -> list[ShopOrderRow]:
    buy_query = filters.buy_query.strip().casefold()
    sell_query = filters.sell_query.strip().casefold()
    location_query = filters.location_query.strip().casefold()
    rows: list[ShopOrderRow] = []

    for marker in markers:
        if _as_int(marker.get("type")) != 3:
            continue

        shop = str(marker.get("name") or "Vending Machine").strip()
        x = _as_float(marker.get("x"))
        y = _as_float(marker.get("y"))
        grid = grid_label(x, y, map_size)

        location_text = (
            f"{shop} {grid} {x:.0f} {y:.0f}"
        ).casefold()
        if location_query and location_query not in location_text:
            continue

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
                    grid=grid,
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


def _grid_sort_key(grid: str) -> tuple[str, int]:
    letters = "".join(
        character
        for character in grid
        if character.isalpha()
    )
    digits = "".join(
        character
        for character in grid
        if character.isdigit()
    )
    return letters, int(digits or 0)


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
    elif mode == "Grid":
        key = lambda row: (
            _grid_sort_key(row.grid),
            row.shop.casefold(),
            row.item_name.casefold(),
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


class _MetricTile(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        title: str,
        *,
        value: str = "—",
        detail: str = "",
    ) -> None:
        super().__init__(
            master,
            corner_radius=12,
            border_width=1,
            border_color=("#d1d5db", "#334155"),
        )
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self,
            text=title.upper(),
            text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(11, 1),
        )
        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        )
        self.value_label.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
        )
        self.detail_label = ctk.CTkLabel(
            self,
            text=detail,
            text_color=MUTED,
            font=ctk.CTkFont(size=10),
            anchor="w",
        )
        self.detail_label.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 11),
        )

    def set(self, value: str, detail: str = "") -> None:
        self.value_label.configure(text=value)
        self.detail_label.configure(text=detail)


class ShopsTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.catalog = RustItemCatalog()
        self._last_signature: tuple[tuple[Any, ...], ...] | None = None
        self._catalog_loading = False
        self._visible_rows: list[ShopOrderRow] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._build_header()
        self._build_metrics()
        self._build_search_card()
        self._build_filter_bar()
        self._build_results_table()
        self.after(100, self._load_catalog)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Marketplace",
            font=ctk.CTkFont(size=30, weight="bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkLabel(
            header,
            text=(
                "Search every live vending offer by what you want "
                "to buy, what you want to trade, or where the shop is."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(2, 0),
        )

        live_badge = ctk.CTkLabel(
            header,
            text="  ● LIVE · 3 SEC  ",
            text_color=SUCCESS,
            fg_color=("#dcfce7", "#052e16"),
            corner_radius=999,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        live_badge.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=(10, 8),
        )
        ctk.CTkButton(
            header,
            text="Refresh item names",
            width=155,
            height=36,
            command=self.refresh_catalog,
        ).grid(
            row=0,
            column=2,
            rowspan=2,
        )

    def _build_metrics(self) -> None:
        metrics = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        metrics.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        for column in range(4):
            metrics.grid_columnconfigure(column, weight=1)

        self.offers_metric = _MetricTile(
            metrics,
            "Matching offers",
            detail="current filters",
        )
        self.shops_metric = _MetricTile(
            metrics,
            "Shops",
            detail="unique locations",
        )
        self.stock_metric = _MetricTile(
            metrics,
            "In stock",
            detail="available offers",
        )
        self.map_metric = _MetricTile(
            metrics,
            "Map",
            detail="grid conversion",
        )

        for column, tile in enumerate(
            (
                self.offers_metric,
                self.shops_metric,
                self.stock_metric,
                self.map_metric,
            )
        ):
            tile.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(
                    0 if column == 0 else 5,
                    0 if column == 3 else 5,
                ),
            )

    def _build_search_card(self) -> None:
        card = ctk.CTkFrame(
            self,
            corner_radius=14,
            border_width=1,
            border_color=("#d1d5db", "#334155"),
        )
        card.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        for column in range(3):
            card.grid_columnconfigure(column, weight=1)

        labels = (
            "I WANT TO BUY",
            "I WANT TO TRADE / SELL",
            "SHOP OR LOCATION",
        )
        placeholders = (
            "Item name, shortname, or ID",
            "Payment item name, shortname, or ID",
            "Shop name, grid (H12), or coordinates",
        )

        entries: list[ctk.CTkEntry] = []
        for column, (label, placeholder) in enumerate(
            zip(labels, placeholders)
        ):
            ctk.CTkLabel(
                card,
                text=label,
                text_color=MUTED,
                font=ctk.CTkFont(size=10, weight="bold"),
                anchor="w",
            ).grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(14, 14),
                pady=(12, 4),
            )
            entry = ctk.CTkEntry(
                card,
                placeholder_text=placeholder,
                height=38,
            )
            entry.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(14, 14),
                pady=(0, 14),
            )
            entry.bind(
                "<KeyRelease>",
                lambda _event: self.refresh(),
            )
            entries.append(entry)

        (
            self.buy_query,
            self.sell_query,
            self.location_query,
        ) = entries

    def _build_filter_bar(self) -> None:
        filters = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        filters.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        for column in range(7):
            filters.grid_columnconfigure(
                column,
                weight=1 if column in {2, 3, 4, 5} else 0,
            )

        self.in_stock = ctk.CTkCheckBox(
            filters,
            text="In stock only",
            command=self.refresh,
        )
        self.in_stock.grid(
            row=0,
            column=0,
            padx=(4, 12),
        )

        self.blueprint_mode = ctk.CTkOptionMenu(
            filters,
            values=list(BLUEPRINT_MODES),
            width=150,
            command=lambda _value: self.refresh(),
        )
        self.blueprint_mode.set("Any offer")
        self.blueprint_mode.grid(
            row=0,
            column=1,
            padx=(0, 8),
        )

        self.min_stock = ctk.CTkEntry(
            filters,
            placeholder_text="Minimum stock",
            height=36,
        )
        self.min_stock.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=4,
        )
        self.max_cost = ctk.CTkEntry(
            filters,
            placeholder_text="Maximum cost",
            height=36,
        )
        self.max_cost.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=4,
        )
        for entry in (self.min_stock, self.max_cost):
            entry.bind(
                "<KeyRelease>",
                lambda _event: self.refresh(),
            )

        self.sort_mode = ctk.CTkOptionMenu(
            filters,
            values=list(SORT_MODES),
            command=lambda _value: self.refresh(),
        )
        self.sort_mode.set("Item A-Z")
        self.sort_mode.grid(
            row=0,
            column=4,
            sticky="ew",
            padx=4,
        )

        ctk.CTkButton(
            filters,
            text="Clear",
            width=80,
            fg_color="transparent",
            border_width=1,
            border_color=("#9ca3af", "#475569"),
            hover_color=("#e5e7eb", "#1e293b"),
            command=self.clear_filters,
        ).grid(
            row=0,
            column=5,
            padx=(8, 4),
        )

        self.copy_button = ctk.CTkButton(
            filters,
            text="Copy selected location",
            width=170,
            state="disabled",
            command=self.copy_selected_location,
        )
        self.copy_button.grid(
            row=0,
            column=6,
            padx=(4, 0),
        )

    def _configure_tree_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "RustShop.Treeview",
            background="#0f172a",
            fieldbackground="#0f172a",
            foreground="#e5e7eb",
            borderwidth=0,
            relief="flat",
            rowheight=34,
            font=("Segoe UI", 10),
        )
        style.configure(
            "RustShop.Treeview.Heading",
            background="#1e293b",
            foreground="#f8fafc",
            borderwidth=0,
            relief="flat",
            padding=(8, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "RustShop.Treeview",
            background=[("selected", "#92400e")],
            foreground=[("selected", "#ffffff")],
        )
        style.map(
            "RustShop.Treeview.Heading",
            background=[("active", "#334155")],
        )

    def _build_results_table(self) -> None:
        card = ctk.CTkFrame(
            self,
            corner_radius=14,
            border_width=1,
            border_color=("#d1d5db", "#334155"),
        )
        card.grid(
            row=4,
            column=0,
            sticky="nsew",
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        table_header = ctk.CTkFrame(
            card,
            fg_color="transparent",
        )
        table_header.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(12, 8),
        )
        table_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            table_header,
            text="Live vending offers",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.table_note = ctk.CTkLabel(
            table_header,
            text="Waiting for Rust+ marketplace data…",
            text_color=MUTED,
            anchor="e",
        )
        self.table_note.grid(row=0, column=1, sticky="e")

        self._configure_tree_style()
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
        )
        self.tree = ttk.Treeview(
            card,
            columns=columns,
            show="headings",
            style="RustShop.Treeview",
            selectmode="browse",
        )
        settings = (
            ("shop", "Shop", 215, "w"),
            ("grid", "Grid", 72, "center"),
            ("coordinates", "Coordinates", 105, "center"),
            ("sells", "Shop sells", 225, "w"),
            ("quantity", "Qty", 58, "center"),
            ("wants", "Shop wants", 225, "w"),
            ("cost", "Cost", 65, "center"),
            ("stock", "Stock", 70, "center"),
            ("type", "Offer", 100, "center"),
        )
        for column, heading, width, anchor in settings:
            self.tree.heading(column, text=heading)
            self.tree.column(
                column,
                width=width,
                minwidth=52,
                anchor=anchor,
                stretch=column in {"shop", "sells", "wants"},
            )

        self.tree.tag_configure(
            "even",
            background="#0f172a",
            foreground="#e5e7eb",
        )
        self.tree.tag_configure(
            "odd",
            background="#111c2f",
            foreground="#e5e7eb",
        )
        self.tree.tag_configure(
            "out",
            background="#111827",
            foreground="#64748b",
        )
        self.tree.tag_configure(
            "blueprint",
            background="#172033",
            foreground="#fbbf24",
        )

        self.tree.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(12, 0),
        )
        self.tree.bind(
            "<<TreeviewSelect>>",
            self._selection_changed,
        )
        self.tree.bind(
            "<Double-1>",
            lambda _event: self.copy_selected_location(),
        )

        vertical = ttk.Scrollbar(
            card,
            orient="vertical",
            command=self.tree.yview,
        )
        vertical.grid(
            row=1,
            column=1,
            sticky="ns",
            padx=(0, 12),
        )
        horizontal = ttk.Scrollbar(
            card,
            orient="horizontal",
            command=self.tree.xview,
        )
        horizontal.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=(12, 0),
        )
        self.tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )

        detail = ctk.CTkFrame(
            card,
            fg_color=("#f3f4f6", "#111827"),
            corner_radius=10,
        )
        detail.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=12,
            pady=12,
        )
        detail.grid_columnconfigure(0, weight=1)

        self.selection_title = ctk.CTkLabel(
            detail,
            text="Select an offer to see its trade and location.",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self.selection_title.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(9, 1),
        )
        self.selection_detail = ctk.CTkLabel(
            detail,
            text="Double-click a row to copy its grid and coordinates.",
            text_color=MUTED,
            anchor="w",
        )
        self.selection_detail.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=12,
            pady=(0, 9),
        )

        self.status = ctk.CTkLabel(
            self,
            text="Connect to load vending markers.",
            anchor="w",
            text_color=MUTED,
        )
        self.status.grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

    def _map_size(self) -> int:
        snapshot = self.context.snapshot
        if snapshot is None:
            return 0
        server = snapshot.server or {}
        return max(
            0,
            _as_int(
                server.get("map_size")
                or server.get("size")
                or 0
            ),
        )

    def current_filters(self) -> ShopFilters:
        return ShopFilters(
            buy_query=self.buy_query.get(),
            sell_query=self.sell_query.get(),
            location_query=self.location_query.get(),
            in_stock_only=bool(self.in_stock.get()),
            blueprint_mode=self.blueprint_mode.get(),
            min_stock=max(
                0,
                safe_int(self.min_stock.get()),
            ),
            max_cost=max(
                0,
                safe_int(self.max_cost.get()),
            ),
            sort_mode=self.sort_mode.get(),
        )

    def refresh(self) -> None:
        snapshot = self.context.snapshot
        if snapshot is None:
            self.status.configure(
                text="Connect to load vending markers."
            )
            self.table_note.configure(
                text="Rust+ connection required"
            )
            return

        map_size = self._map_size()
        rows = collect_shop_rows(
            snapshot.markers,
            map_size=map_size,
            label=self.catalog.label,
            search_text=self.catalog.search_text,
            filters=self.current_filters(),
        )
        signature = tuple(row.values() for row in rows)
        selected_index = self._selected_index()

        if signature != self._last_signature:
            y_position = (
                self.tree.yview()[0]
                if self.tree.get_children()
                else 0.0
            )
            self.tree.delete(*self.tree.get_children())

            for index, row in enumerate(rows):
                if row.stock <= 0:
                    tag = "out"
                elif (
                    row.item_is_blueprint
                    or row.currency_is_blueprint
                ):
                    tag = "blueprint"
                else:
                    tag = "even" if index % 2 == 0 else "odd"
                self.tree.insert(
                    "",
                    "end",
                    values=row.values(),
                    tags=(tag,),
                )

            self.tree.yview_moveto(y_position)
            self._last_signature = signature
            self._visible_rows = rows
            if selected_index is not None and selected_index < len(rows):
                item = self.tree.get_children()[selected_index]
                self.tree.selection_set(item)
                self.tree.focus(item)
            else:
                self._clear_selection_detail()

        shop_count = len({row.shop_key for row in rows})
        in_stock_count = sum(row.stock > 0 for row in rows)
        refreshed = datetime.now().strftime("%H:%M:%S")

        self.offers_metric.set(
            str(len(rows)),
            "current filters",
        )
        self.shops_metric.set(
            str(shop_count),
            "unique locations",
        )
        self.stock_metric.set(
            str(in_stock_count),
            "available now",
        )
        self.map_metric.set(
            f"{map_size or '—'}",
            "world size / grids",
        )
        self.table_note.configure(
            text=f"Updated {refreshed}"
        )
        self.status.configure(
            text=(
                f"{len(rows)} offer(s) from {shop_count} shop(s) · "
                f"{self.catalog.description()} · "
                f"Rust+ refreshed {refreshed}"
            )
        )

    def _selected_index(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        item = selection[0]
        try:
            return self.tree.index(item)
        except Exception:
            return None

    def _selected_row(self) -> ShopOrderRow | None:
        index = self._selected_index()
        if index is None or index >= len(self._visible_rows):
            return None
        return self._visible_rows[index]

    def _selection_changed(self, _event: Any = None) -> None:
        row = self._selected_row()
        if row is None:
            self._clear_selection_detail()
            return

        self.selection_title.configure(
            text=f"{row.grid}  •  {row.shop}"
        )
        self.selection_detail.configure(
            text=(
                f"{row.quantity} × {row.item_name}  →  "
                f"{row.cost} × {row.currency_name}  •  "
                f"Coordinates {row.coordinates}  •  "
                f"Stock {row.stock}"
            )
        )
        self.copy_button.configure(state="normal")

    def _clear_selection_detail(self) -> None:
        self.selection_title.configure(
            text="Select an offer to see its trade and location."
        )
        self.selection_detail.configure(
            text="Double-click a row to copy its grid and coordinates."
        )
        self.copy_button.configure(state="disabled")

    def copy_selected_location(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        value = (
            f"{row.grid} — {row.shop} "
            f"(X {row.x:.0f}, Y {row.y:.0f})"
        )
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()
        self.selection_detail.configure(
            text=f"Copied: {value}"
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
        self.sort_mode.set("Item A-Z")
        self.refresh()

    def _load_catalog(self, *, force: bool = False) -> None:
        if self._catalog_loading:
            return
        self._catalog_loading = True
        self.status.configure(
            text="Loading Rust item names…"
        )

        work = (
            self.catalog.refresh
            if force
            else self.catalog.load
        )

        def success(_count: int) -> None:
            self._catalog_loading = False
            self._last_signature = None
            self.refresh()

        def error(exc: Exception) -> None:
            self._catalog_loading = False
            self.catalog.last_error = str(exc)
            self._last_signature = None
            self.refresh()

        run_in_worker(
            self,
            work,
            success,
            error,
        )

    def refresh_catalog(self) -> None:
        self._load_catalog(force=True)

    def on_context_updated(self) -> None:
        self.refresh()
