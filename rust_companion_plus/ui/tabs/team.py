from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk


class TeamTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Team", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        columns = ("name", "online", "alive", "x", "y", "steam_id")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column in columns:
            self.tree.heading(column, text=column.replace("_", " ").title())
            self.tree.column(column, anchor="center", width=150)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.status = ctk.CTkLabel(self, text="Connect to load team data.", anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", pady=(8, 0))

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        snapshot = self.context.snapshot
        if snapshot is None:
            return
        for member in snapshot.team:
            self.tree.insert(
                "",
                "end",
                values=(
                    member.get("name", "Unknown"),
                    "Online" if member.get("is_online") else "Offline",
                    "Alive" if member.get("is_alive") else "Dead",
                    f"{float(member.get('x', 0)):.0f}",
                    f"{float(member.get('y', 0)):.0f}",
                    member.get("steam_id", ""),
                ),
            )
        online = sum(bool(member.get("is_online")) for member in snapshot.team)
        self.status.configure(text=f"{online}/{len(snapshot.team)} team member(s) online.")

    def on_context_updated(self) -> None:
        self.refresh()
