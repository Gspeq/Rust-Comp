from __future__ import annotations

import math

import customtkinter as ctk

from rust_companion_plus.catalog import RECYCLE_CATALOG
from rust_companion_plus.services.team_intelligence import (
    build_team_intelligence,
    compass_bearing,
    grid_for_world,
    world_size_for,
)
from rust_companion_plus.services.tools import (
    calculate_recycle,
)
from rust_companion_plus.ui.common import (
    MUTED,
    run_in_worker,
    safe_float,
    safe_int,
)


class ToolsTab(ctk.CTkFrame):
    """Utilities that add information the game does not already show."""

    def __init__(self, master, context):
        super().__init__(
            master,
            fg_color="transparent",
        )
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Utilities",
            font=ctk.CTkFont(
                size=28,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 4),
        )
        ctk.CTkLabel(
            self,
            text=(
                "Grid conversion, point-to-point distance, recycle "
                "returns, and live Rust+ smart-device controls."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )

        tabs = ctk.CTkTabview(
            self,
            corner_radius=10,
        )
        tabs.grid(
            row=2,
            column=0,
            sticky="nsew",
        )
        for name in (
            "Grid & Distance",
            "Recycle",
            "Smart Devices",
        ):
            tabs.add(name)

        self._coordinates(
            tabs.tab("Grid & Distance")
        )
        self._recycle(
            tabs.tab("Recycle")
        )
        self._devices(
            tabs.tab("Smart Devices")
        )

    def _coordinates(self, parent) -> None:
        parent.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="coordinate_columns",
        )
        parent.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            parent,
            text="Point A",
            font=ctk.CTkFont(
                size=17,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(14, 7),
            pady=(14, 4),
        )
        ctk.CTkLabel(
            parent,
            text="Point B",
            font=ctk.CTkFont(
                size=17,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(7, 14),
            pady=(14, 4),
        )

        left = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        left.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(14, 7),
        )
        left.grid_columnconfigure((0, 1), weight=1)
        self.ax = ctk.CTkEntry(
            left,
            placeholder_text="A world X",
        )
        self.ay = ctk.CTkEntry(
            left,
            placeholder_text="A world Y",
        )
        self.ax.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        self.ay.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )

        right = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        right.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(7, 14),
        )
        right.grid_columnconfigure((0, 1), weight=1)
        self.bx = ctk.CTkEntry(
            right,
            placeholder_text="B world X",
        )
        self.by = ctk.CTkEntry(
            right,
            placeholder_text="B world Y",
        )
        self.bx.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        self.by.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )

        buttons = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        buttons.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=12,
        )
        buttons.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
        )
        ctk.CTkButton(
            buttons,
            text="Use my live position",
            command=self.use_my_position,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        ctk.CTkButton(
            buttons,
            text="Use nearest teammate",
            command=self.use_nearest_teammate,
            fg_color="transparent",
            border_width=1,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=4,
        )
        ctk.CTkButton(
            buttons,
            text="Calculate route",
            command=self.calculate_route,
        ).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(4, 0),
        )

        self.coordinate_status = ctk.CTkLabel(
            parent,
            text=(
                "World size is read from the active Rust+ map."
            ),
            text_color=MUTED,
            anchor="w",
        )
        self.coordinate_status.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(0, 6),
        )

        self.coordinate_result = ctk.CTkTextbox(
            parent,
            corner_radius=8,
        )
        self.coordinate_result.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=14,
            pady=(0, 14),
        )
        self.coordinate_result.insert(
            "1.0",
            (
                "Enter two world positions, or use the live "
                "team-position buttons."
            ),
        )

    def _team_rows(self):
        return build_team_intelligence(
            self.context.snapshot,
            steam_id=self.context.credentials.steam_id,
            profile_record=self.context.profile_record,
        )[0]

    @staticmethod
    def _set_entry(
        entry: ctk.CTkEntry,
        value: float,
    ) -> None:
        entry.delete(0, "end")
        entry.insert(0, f"{value:.0f}")

    def use_my_position(self) -> None:
        member = next(
            (
                row
                for row in self._team_rows()
                if row.get("is_self")
            ),
            None,
        )
        if member is None:
            self.coordinate_status.configure(
                text=(
                    "Your current Rust+ team position "
                    "is unavailable."
                )
            )
            return
        self._set_entry(
            self.ax,
            float(member["x"]),
        )
        self._set_entry(
            self.ay,
            float(member["y"]),
        )
        self.coordinate_status.configure(
            text=(
                f"Point A set to your live position "
                f"at grid {member.get('grid') or '?'}."
            )
        )

    def use_nearest_teammate(self) -> None:
        teammates = [
            row
            for row in self._team_rows()
            if not row.get("is_self")
            and row.get("distance_m") is not None
        ]
        nearest = min(
            teammates,
            key=lambda row: float(
                row["distance_m"]
            ),
            default=None,
        )
        if nearest is None:
            self.coordinate_status.configure(
                text=(
                    "No teammate with a usable live position "
                    "is available."
                )
            )
            return
        self._set_entry(
            self.bx,
            float(nearest["x"]),
        )
        self._set_entry(
            self.by,
            float(nearest["y"]),
        )
        self.coordinate_status.configure(
            text=(
                f"Point B set to {nearest['name']} "
                f"at grid {nearest.get('grid') or '?'}."
            )
        )

    def calculate_route(self) -> None:
        ax = safe_float(self.ax.get())
        ay = safe_float(self.ay.get())
        bx = safe_float(self.bx.get())
        by = safe_float(self.by.get())
        world_size = world_size_for(
            self.context.snapshot,
            self.context.profile_record,
        )
        if world_size <= 0:
            self.coordinate_status.configure(
                text=(
                    "Load a current or saved analyzed map "
                    "before converting coordinates to grids."
                )
            )
            return

        distance = math.hypot(
            bx - ax,
            by - ay,
        )
        bearing, direction = compass_bearing(
            ax,
            ay,
            bx,
            by,
        )
        grid_a = grid_for_world(
            ax,
            ay,
            world_size,
        )
        grid_b = grid_for_world(
            bx,
            by,
            world_size,
        )

        lines = [
            "ROUTE",
            "",
            (
                f"Point A: grid {grid_a} · "
                f"x {ax:.0f}, y {ay:.0f}"
            ),
            (
                f"Point B: grid {grid_b} · "
                f"x {bx:.0f}, y {by:.0f}"
            ),
            "",
            f"Straight-line distance: {distance:,.0f} m",
            f"Bearing: {bearing:.0f}° {direction}",
            (
                f"Map coverage: "
                f"{distance / world_size * 100:.1f}% "
                "of one map width"
            ),
        ]
        self.coordinate_result.delete(
            "1.0",
            "end",
        )
        self.coordinate_result.insert(
            "1.0",
            "\n".join(lines),
        )
        self.coordinate_status.configure(
            text=f"Route calculated for a {world_size} map."
        )

    def _recycle(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            parent,
            text=(
                "Quickly calculate configured recycler returns."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 8),
        )

        self.recycle_item = ctk.CTkOptionMenu(
            parent,
            values=sorted(RECYCLE_CATALOG),
        )
        self.recycle_item.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=6,
        )

        self.recycle_qty = ctk.CTkEntry(
            parent,
            placeholder_text="Quantity",
        )
        self.recycle_qty.insert(0, "1")
        self.recycle_qty.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=14,
            pady=6,
        )

        ctk.CTkButton(
            parent,
            text="Calculate recycle returns",
            command=self.calculate_recycle,
        ).grid(
            row=3,
            column=0,
            sticky="ew",
            padx=14,
            pady=8,
        )

        self.recycle_result = ctk.CTkTextbox(
            parent,
            corner_radius=8,
        )
        self.recycle_result.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(0, 14),
        )

    def calculate_recycle(self) -> None:
        returns = calculate_recycle(
            self.recycle_item.get(),
            safe_int(
                self.recycle_qty.get(),
                1,
            ),
        )
        self.recycle_result.delete(
            "1.0",
            "end",
        )
        self.recycle_result.insert(
            "1.0",
            (
                "\n".join(
                    f"{name}: {amount:g}"
                    for name, amount in returns.items()
                )
                or "No configured recycle return."
            ),
        )

    def _devices(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            parent,
            text=(
                "Read or control a paired Rust+ smart entity "
                "by its entity ID."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 6),
        )

        self.device_id = ctk.CTkEntry(
            parent,
            placeholder_text="Paired entity ID",
        )
        self.device_id.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=8,
        )

        buttons = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        buttons.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=14,
            pady=6,
        )
        buttons.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
        )
        ctk.CTkButton(
            buttons,
            text="Read status",
            command=self.read_device,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
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
            fg_color="transparent",
            border_width=1,
        ).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(4, 0),
        )

        self.device_status = ctk.CTkTextbox(
            parent,
            corner_radius=8,
        )
        self.device_status.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(6, 14),
        )

    def read_device(self) -> None:
        entity_id = safe_int(
            self.device_id.get()
        )
        if entity_id <= 0:
            self._show_device(
                {
                    "error": (
                        "Enter a valid paired entity ID."
                    )
                }
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
        entity_id = safe_int(
            self.device_id.get()
        )
        if entity_id <= 0:
            self._show_device(
                {
                    "error": (
                        "Enter a valid paired entity ID."
                    )
                }
            )
            return
        run_in_worker(
            self,
            lambda: self.context.rust.set_entity_value(
                self.context.credentials,
                entity_id,
                value,
            ),
            lambda _result: self._show_device(
                {
                    "result": (
                        "ON" if value else "OFF"
                    )
                }
            ),
            lambda exc: self._show_device(
                {"error": str(exc)}
            ),
        )

    def _show_device(self, result) -> None:
        self.device_status.delete(
            "1.0",
            "end",
        )
        self.device_status.insert(
            "1.0",
            "\n".join(
                f"{key}: {value}"
                for key, value in result.items()
            ),
        )
