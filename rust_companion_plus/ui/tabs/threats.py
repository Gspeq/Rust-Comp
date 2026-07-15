
from __future__ import annotations

from collections import Counter
from tkinter import messagebox, ttk
from typing import Any

import customtkinter as ctk

from rust_companion_plus.models import ThreatEntry
from rust_companion_plus.ui.common import MUTED


class ThreatsTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self,
            text="Threats, Events & Death History",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            self,
            text=(
                "Rust+ automatically records team deaths, your last ten "
                "death positions, and dangerous world events. Add attacker "
                "or weapon details manually when you know them."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=1080,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        form = ctk.CTkFrame(self)
        form.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.attacker = ctk.CTkEntry(
            form,
            placeholder_text="Attacker / threat",
        )
        self.victim = ctk.CTkEntry(
            form,
            placeholder_text="Victim / subject",
        )
        self.weapon = ctk.CTkEntry(
            form,
            placeholder_text="Weapon / detail",
        )
        self.grid_ref = ctk.CTkEntry(
            form,
            placeholder_text="Grid",
        )
        for index, widget in enumerate(
            [
                self.attacker,
                self.victim,
                self.weapon,
                self.grid_ref,
            ]
        ):
            widget.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=5,
                pady=8,
            )

        ctk.CTkButton(
            form,
            text="Add manual threat/death",
            command=self.add_entry,
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=5,
            pady=(0, 8),
        )
        ctk.CTkButton(
            form,
            text="Delete selected",
            command=self.delete_selected,
        ).grid(
            row=1,
            column=2,
            sticky="ew",
            padx=5,
            pady=(0, 8),
        )
        ctk.CTkButton(
            form,
            text="Clear my death history",
            command=self.clear_death_history,
            fg_color="transparent",
            border_width=1,
        ).grid(
            row=1,
            column=3,
            sticky="ew",
            padx=5,
            pady=(0, 8),
        )

        pane = ctk.CTkFrame(self)
        pane.grid(row=3, column=0, sticky="nsew")
        pane.grid_columnconfigure(0, weight=3)
        pane.grid_columnconfigure(1, weight=2)
        pane.grid_rowconfigure(0, weight=1)

        columns = (
            "time",
            "type",
            "details",
            "grid",
            "source",
        )
        self.tree = ttk.Treeview(
            pane,
            columns=columns,
            show="headings",
        )
        widths = {
            "time": 165,
            "type": 100,
            "details": 390,
            "grid": 80,
            "source": 130,
        }
        for column in columns:
            self.tree.heading(
                column,
                text=column.title(),
            )
            self.tree.column(
                column,
                width=widths[column],
                anchor=(
                    "w"
                    if column in {"details", "source"}
                    else "center"
                ),
            )
        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=10,
            pady=10,
        )

        side = ctk.CTkTabview(pane, width=390)
        side.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(0, 10),
            pady=10,
        )
        side.add("Summary")
        side.add("My last 10 deaths")

        self.summary = ctk.CTkTextbox(
            side.tab("Summary"),
        )
        self.summary.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )

        self.deaths = ctk.CTkTextbox(
            side.tab("My last 10 deaths"),
        )
        self.deaths.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )

        self.refresh()

    def entries(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.context.store.get(
                "threats",
                [],
            )
            if isinstance(row, dict)
        ]

    def death_history(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.context.store.get(
                "death_history",
                [],
            )
            if isinstance(row, dict)
        ][-10:]

    @staticmethod
    def _event_type(row: dict[str, Any]) -> str:
        value = str(row.get("event_type") or "").strip()
        if value:
            return value.replace("_", " ").title()
        return "Manual"

    @staticmethod
    def _details(row: dict[str, Any]) -> str:
        event_type = str(
            row.get("event_type") or "manual"
        ).casefold()
        attacker = str(
            row.get("attacker") or ""
        ).strip()
        victim = str(row.get("victim") or "").strip()
        weapon = str(row.get("weapon") or "").strip()
        note = str(row.get("note") or "").strip()

        if event_type == "world_event":
            return note or attacker
        if attacker and victim:
            detail = f"{attacker} → {victim}"
        else:
            detail = attacker or victim or note or "Threat event"
        if weapon:
            detail += f" · {weapon}"
        if note and note not in detail:
            detail += f" · {note}"
        return detail

    def add_entry(self) -> None:
        attacker = self.attacker.get().strip()
        victim = self.victim.get().strip()
        if not attacker and not victim:
            messagebox.showerror(
                "Missing fields",
                "Enter an attacker/threat or victim/subject.",
            )
            return

        entry = ThreatEntry(
            attacker or "Unknown",
            victim or "Unknown",
            self.weapon.get().strip(),
            self.grid_ref.get().strip(),
        ).to_dict()
        entry.update(
            {
                "event_type": "manual",
                "source": "manual",
                "automatic": False,
            }
        )
        rows = self.entries()
        rows.append(entry)
        self.context.store.set("threats", rows)

        for widget in (
            self.attacker,
            self.victim,
            self.weapon,
            self.grid_ref,
        ):
            widget.delete(0, "end")
        self.refresh()

    def delete_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return

        indexes: list[int] = []
        for item in selected:
            try:
                indexes.append(int(str(item).split("-", 1)[1]))
            except (IndexError, ValueError):
                continue

        rows = self.entries()
        for index in sorted(indexes, reverse=True):
            if 0 <= index < len(rows):
                rows.pop(index)
        self.context.store.set("threats", rows)
        self.refresh()

    def clear_death_history(self) -> None:
        if not self.death_history():
            return
        confirmed = messagebox.askyesno(
            "Clear death history?",
            "Remove the saved last-ten-deaths list for this server profile?",
        )
        if not confirmed:
            return
        self.context.store.set("death_history", [])
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = self.entries()

        indexed_rows = list(enumerate(rows))
        indexed_rows.sort(
            key=lambda pair: str(
                pair[1].get("occurred_at") or ""
            ),
            reverse=True,
        )
        for original_index, row in indexed_rows:
            self.tree.insert(
                "",
                "end",
                iid=f"row-{original_index}",
                values=(
                    str(row.get("occurred_at") or "")[:19],
                    self._event_type(row),
                    self._details(row),
                    row.get("grid", ""),
                    row.get("source", "manual"),
                ),
            )

        known_attackers = [
            str(row.get("attacker") or "").strip()
            for row in rows
            if str(row.get("event_type") or "").casefold()
            not in {"world_event"}
            and str(row.get("attacker") or "").strip().casefold()
            not in {"", "unknown", "rust+ event"}
        ]
        counts = Counter(known_attackers)
        automatic_deaths = sum(
            1
            for row in rows
            if row.get("event_type") == "death"
            and row.get("automatic")
        )
        world_events = sum(
            1
            for row in rows
            if row.get("event_type") == "world_event"
        )

        lines = [
            "AUTOMATIC INTELLIGENCE",
            "",
            f"Team/self deaths detected: {automatic_deaths}",
            f"Dangerous world events: {world_events}",
            f"Saved personal deaths: {len(self.death_history())}/10",
            "",
            "KNOWN REPEAT OFFENDERS",
            "",
        ]
        if counts:
            lines.extend(
                f"{name}: {count} event(s)"
                for name, count in counts.most_common()
            )
        else:
            lines.append(
                "No named attacker has been entered yet."
            )
        lines.extend(
            [
                "",
                "Rust+ cannot expose the killer or weapon. "
                "Automatic rows keep those fields unknown until "
                "you add the information manually.",
            ]
        )
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))

        death_lines = []
        history = list(reversed(self.death_history()))
        for index, row in enumerate(history, start=1):
            death_lines.extend(
                [
                    f"{index}. {str(row.get('occurred_at') or '')[:19]}",
                    (
                        f"   Grid {row.get('grid') or '?'} · "
                        f"x={float(row.get('x', 0) or 0):.0f}, "
                        f"y={float(row.get('y', 0) or 0):.0f}"
                    ),
                    (
                        "   Last Rust+ position before the "
                        "alive→dead update."
                    ),
                    "",
                ]
            )
        if not death_lines:
            death_lines = [
                "No personal death has been observed in the live "
                "Rust+ team feed for this server profile yet."
            ]
        self.deaths.delete("1.0", "end")
        self.deaths.insert("1.0", "\n".join(death_lines))

    def on_context_updated(self) -> None:
        self.refresh()
