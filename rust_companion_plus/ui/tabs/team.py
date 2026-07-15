from __future__ import annotations

from typing import Any

import customtkinter as ctk

from rust_companion_plus.services.team_intelligence import (
    build_team_intelligence,
)
from rust_companion_plus.ui.common import ACCENT, MUTED


class TeamTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(
            master,
            fg_color="transparent",
        )
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self.stat_values: dict[str, ctk.CTkLabel] = {}

        header = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Team Intelligence",
            font=ctk.CTkFont(
                size=28,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkLabel(
            header,
            text=(
                "Live Rust+ positions, distance, team spread, "
                "map grid, monument proximity, and recent deaths."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(3, 0),
        )

        self.updated_label = ctk.CTkLabel(
            header,
            text="Waiting for team data",
            text_color=MUTED,
            anchor="e",
        )
        self.updated_label.grid(
            row=0,
            column=1,
            rowspan=2,
            sticky="e",
        )

        stats = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        stats.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        for column in range(4):
            stats.grid_columnconfigure(
                column,
                weight=1,
                uniform="team_stats",
            )

        self._stat_card(
            stats,
            0,
            "ONLINE",
            "online",
        )
        self._stat_card(
            stats,
            1,
            "ALIVE",
            "alive",
        )
        self._stat_card(
            stats,
            2,
            "NEAREST TEAMMATE",
            "nearest",
        )
        self._stat_card(
            stats,
            3,
            "TEAM SPREAD",
            "spread",
        )

        note = ctk.CTkLabel(
            self,
            text=(
                "Monument proximity is approximate and uses visible "
                "monument markers from the last analyzed map."
            ),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=11),
        )
        note.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )

        body = ctk.CTkFrame(
            self,
            corner_radius=12,
        )
        body.grid(
            row=3,
            column=0,
            sticky="nsew",
        )
        body.grid_columnconfigure(
            0,
            weight=5,
        )
        body.grid_columnconfigure(
            1,
            weight=2,
        )
        body.grid_rowconfigure(
            0,
            weight=1,
        )

        self.member_list = ctk.CTkScrollableFrame(
            body,
            label_text="Live team positions",
            corner_radius=10,
        )
        self.member_list.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=12,
            pady=12,
        )
        self.member_list.grid_columnconfigure(
            0,
            weight=1,
        )

        self.side_tabs = ctk.CTkTabview(
            body,
            width=390,
        )
        self.side_tabs.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(0, 12),
            pady=12,
        )
        self.side_tabs.add("Live insights")
        self.side_tabs.add("My last 10 deaths")

        self.insights = ctk.CTkTextbox(
            self.side_tabs.tab("Live insights"),
            corner_radius=8,
        )
        self.insights.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )

        self.deaths = ctk.CTkTextbox(
            self.side_tabs.tab("My last 10 deaths"),
            corner_radius=8,
        )
        self.deaths.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )

        self.refresh()

    def _stat_card(
        self,
        parent,
        column: int,
        title: str,
        key: str,
    ) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=10,
            border_width=1,
            border_color=("#d8dee9", "#263244"),
        )
        card.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(
                0 if column == 0 else 6,
                0 if column == 3 else 6,
            ),
        )
        ctk.CTkLabel(
            card,
            text=title,
            text_color=MUTED,
            font=ctk.CTkFont(
                size=10,
                weight="bold",
            ),
            anchor="w",
        ).pack(
            fill="x",
            padx=14,
            pady=(11, 2),
        )
        value = ctk.CTkLabel(
            card,
            text="—",
            font=ctk.CTkFont(
                size=20,
                weight="bold",
            ),
            anchor="w",
        )
        value.pack(
            fill="x",
            padx=14,
            pady=(0, 12),
        )
        self.stat_values[key] = value

    def _member_card(
        self,
        row_index: int,
        member: dict[str, Any],
    ) -> None:
        is_self = bool(member.get("is_self"))
        online = bool(member.get("is_online"))
        alive = bool(member.get("is_alive"))

        if not online:
            status = "Offline"
            status_color = ("#64748b", "#94a3b8")
        elif not alive:
            status = "Dead"
            status_color = ("#991b1b", "#f87171")
        else:
            status = "Online · Alive"
            status_color = ("#166534", "#4ade80")

        card = ctk.CTkFrame(
            self.member_list,
            corner_radius=10,
            border_width=(
                2 if is_self else 1
            ),
            border_color=(
                ACCENT
                if is_self
                else ("#d8dee9", "#263244")
            ),
        )
        card.grid(
            row=row_index,
            column=0,
            sticky="ew",
            padx=4,
            pady=5,
        )
        card.grid_columnconfigure(0, weight=1)

        name = str(member.get("name") or "Unknown")
        if is_self:
            name += "  ·  YOU"

        ctk.CTkLabel(
            card,
            text=name,
            font=ctk.CTkFont(
                size=16,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=14,
            pady=(11, 2),
        )
        ctk.CTkLabel(
            card,
            text=status,
            text_color=status_color,
            font=ctk.CTkFont(
                size=11,
                weight="bold",
            ),
            anchor="e",
        ).grid(
            row=0,
            column=1,
            sticky="e",
            padx=14,
            pady=(11, 2),
        )

        grid = str(member.get("grid") or "?")
        x = float(member.get("x") or 0)
        y = float(member.get("y") or 0)
        ctk.CTkLabel(
            card,
            text=(
                f"Grid {grid}   ·   "
                f"x {x:.0f}, y {y:.0f}"
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=14,
            pady=(2, 11),
        )

        distance = member.get("distance_m")
        if is_self:
            distance_text = "Current player"
        elif distance is None:
            distance_text = "Distance unavailable"
        else:
            distance_text = (
                f"{float(distance):,.0f} m from you"
            )

        monument_distance = member.get(
            "monument_distance_m"
        )
        if monument_distance is None:
            monument_text = (
                "Analyze the map to enable monument proximity"
            )
        elif bool(member.get("near_monument")):
            monument_text = (
                "Near a monument marker · "
                f"~{float(monument_distance):,.0f} m"
            )
        else:
            monument_text = (
                "Nearest monument marker · "
                f"~{float(monument_distance):,.0f} m"
            )

        ctk.CTkLabel(
            card,
            text=(
                f"{distance_text}\n{monument_text}"
            ),
            justify="right",
            anchor="e",
            text_color=(
                ("#0369a1", "#7dd3fc")
                if bool(member.get("near_monument"))
                else MUTED
            ),
            font=ctk.CTkFont(size=11),
        ).grid(
            row=1,
            column=1,
            sticky="e",
            padx=14,
            pady=(2, 11),
        )

    def _death_rows(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.context.store.get(
                "death_history",
                [],
            )
            if isinstance(row, dict)
        ][-10:]

    def refresh(self) -> None:
        for widget in self.member_list.winfo_children():
            widget.destroy()

        rows, summary = build_team_intelligence(
            self.context.snapshot,
            steam_id=self.context.credentials.steam_id,
            profile_record=self.context.profile_record,
        )

        if not rows:
            empty = ctk.CTkLabel(
                self.member_list,
                text=(
                    "No Rust+ team data is available yet.\n"
                    "Join a team and keep the live profile connected."
                ),
                text_color=MUTED,
                justify="center",
            )
            empty.grid(
                row=0,
                column=0,
                sticky="ew",
                padx=20,
                pady=50,
            )

        for index, member in enumerate(rows):
            self._member_card(index, member)

        total = int(summary.get("total") or 0)
        online = int(summary.get("online") or 0)
        alive = int(summary.get("alive") or 0)
        nearest_name = str(
            summary.get("nearest_teammate") or ""
        )
        nearest_distance = summary.get(
            "nearest_distance_m"
        )
        spread = float(
            summary.get("spread_m") or 0
        )

        self.stat_values["online"].configure(
            text=f"{online} / {total}"
        )
        self.stat_values["alive"].configure(
            text=f"{alive} / {total}"
        )
        self.stat_values["nearest"].configure(
            text=(
                f"{nearest_name}\n"
                f"{float(nearest_distance):,.0f} m"
                if nearest_name
                and nearest_distance is not None
                else "—"
            )
        )
        self.stat_values["spread"].configure(
            text=(
                f"{spread:,.0f} m"
                if total > 1
                else "—"
            )
        )

        self.updated_label.configure(
            text=(
                "Live Rust+"
                if self.context.rustplus_live
                else "Cached team snapshot"
            )
        )

        cluster = (
            "Tight group"
            if spread <= 200
            else "Moderately spread"
            if spread <= 600
            else "Widely split"
        )
        near_count = int(
            summary.get("near_monument_count") or 0
        )
        monument_count = int(
            summary.get("monument_markers") or 0
        )
        lines = [
            "TEAM POSITION SUMMARY",
            "",
            f"Your grid: {summary.get('self_grid') or '?'}",
            f"Team center: {summary.get('center_grid') or '?'}",
            f"Formation: {cluster}",
            f"Live spread: {spread:,.0f} m",
            "",
            "MONUMENT AWARENESS",
            "",
        ]
        if monument_count:
            lines.extend(
                [
                    (
                        f"{monument_count} approximate monument "
                        "markers were detected on the analyzed map."
                    ),
                    (
                        f"{near_count} team member(s) are within "
                        "about 250 m of a detected marker."
                    ),
                ]
            )
        else:
            lines.append(
                "Load and analyze the current map to enable "
                "monument proximity."
            )

        self.insights.delete("1.0", "end")
        self.insights.insert(
            "1.0",
            "\n".join(lines),
        )

        death_lines = [
            "LAST KNOWN POSITION BEFORE DEATH",
            "",
            (
                "Rust+ reports the alive→dead transition and the "
                "last position from the prior refresh. It does not "
                "report the killer or weapon."
            ),
            "",
        ]
        deaths = self._death_rows()
        if not deaths:
            death_lines.append(
                "No personal deaths have been recorded."
            )
        else:
            for index, row in enumerate(
                reversed(deaths),
                start=1,
            ):
                death_lines.extend(
                    [
                        (
                            f"{index}. "
                            f"{str(row.get('occurred_at') or '')[:19]}"
                        ),
                        (
                            f"   Grid {row.get('grid') or '?'} · "
                            f"x {float(row.get('x') or 0):.0f}, "
                            f"y {float(row.get('y') or 0):.0f}"
                        ),
                        "",
                    ]
                )

        self.deaths.delete("1.0", "end")
        self.deaths.insert(
            "1.0",
            "\n".join(death_lines),
        )

    def on_context_updated(self) -> None:
        self.refresh()
