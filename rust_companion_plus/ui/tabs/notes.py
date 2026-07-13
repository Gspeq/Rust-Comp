from __future__ import annotations

import customtkinter as ctk


class NotesTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="Base Notes & Plans", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Save notes", command=self.save).grid(row=0, column=1)

        self.text = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=14))
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.insert("1.0", str(context.store.get("notes", "")))
        self.status = ctk.CTkLabel(self, text="", anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", pady=(6, 0))

    def save(self) -> None:
        self.context.store.set("notes", self.text.get("1.0", "end").rstrip())
        self.status.configure(text="Saved locally.")
        self.after(1800, lambda: self.status.configure(text=""))
