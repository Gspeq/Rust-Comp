from __future__ import annotations

from collections import Counter
from tkinter import messagebox, ttk

import customtkinter as ctk

from rust_companion_plus.models import ThreatEntry


class ThreatsTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text="Threats & Nemesis Log", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        form = ctk.CTkFrame(self)
        form.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.attacker = ctk.CTkEntry(form, placeholder_text="Attacker")
        self.victim = ctk.CTkEntry(form, placeholder_text="Team victim")
        self.weapon = ctk.CTkEntry(form, placeholder_text="Weapon")
        self.grid_ref = ctk.CTkEntry(form, placeholder_text="Grid")
        for index, widget in enumerate([self.attacker, self.victim, self.weapon, self.grid_ref]):
            widget.grid(row=0, column=index, sticky="ew", padx=5, pady=8)
        ctk.CTkButton(form, text="Add death", command=self.add_entry).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 8)
        )
        ctk.CTkButton(form, text="Delete selected", command=self.delete_selected).grid(
            row=1, column=2, columnspan=2, sticky="ew", padx=5, pady=(0, 8)
        )

        pane = ctk.CTkFrame(self)
        pane.grid(row=2, column=0, sticky="nsew")
        pane.grid_columnconfigure(0, weight=3)
        pane.grid_columnconfigure(1, weight=1)
        pane.grid_rowconfigure(0, weight=1)
        columns = ("time", "attacker", "victim", "weapon", "grid")
        self.tree = ttk.Treeview(pane, columns=columns, show="headings")
        for column in columns:
            self.tree.heading(column, text=column.title())
            self.tree.column(column, width=150, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.nemesis = ctk.CTkTextbox(pane, width=260)
        self.nemesis.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        self.refresh()

    def entries(self) -> list[dict]:
        return list(self.context.store.get("threats", []))

    def add_entry(self) -> None:
        if not self.attacker.get().strip() or not self.victim.get().strip():
            messagebox.showerror("Missing fields", "Attacker and victim are required.")
            return
        entry = ThreatEntry(
            self.attacker.get().strip(),
            self.victim.get().strip(),
            self.weapon.get().strip(),
            self.grid_ref.get().strip(),
        )
        rows = self.entries()
        rows.append(entry.to_dict())
        self.context.store.set("threats", rows)
        self.attacker.delete(0, "end")
        self.victim.delete(0, "end")
        self.weapon.delete(0, "end")
        self.grid_ref.delete(0, "end")
        self.refresh()

    def delete_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        indexes = sorted((self.tree.index(item) for item in selected), reverse=True)
        rows = self.entries()
        for index in indexes:
            if 0 <= index < len(rows):
                rows.pop(index)
        self.context.store.set("threats", rows)
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = self.entries()
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row.get("occurred_at", ""),
                    row.get("attacker", ""),
                    row.get("victim", ""),
                    row.get("weapon", ""),
                    row.get("grid", ""),
                ),
            )
        counts = Counter(row.get("attacker", "Unknown") for row in rows)
        lines = ["REPEAT OFFENDERS", ""]
        lines.extend(f"{name}: {count} kill(s)" for name, count in counts.most_common())
        self.nemesis.delete("1.0", "end")
        self.nemesis.insert("1.0", "\n".join(lines))
