from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from rust_companion_plus.services.deal_notifications import (
    LOOT_PRESETS,
    MINIMUM_RATING_OPTIONS,
    NOTIFICATION_SETTINGS_KEY,
    DealAlert,
    clear_deal_alert_history,
    normalize_notification_settings,
    save_notification_settings,
)
from rust_companion_plus.ui.common import MUTED, safe_int


class MarketplaceNotificationSettingsPanel(ctk.CTkFrame):
    """Persistent marketplace alert presets and advanced item targeting."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        settings = normalize_notification_settings(
            context.store.get(NOTIFICATION_SETTINGS_KEY, {})
        )
        self.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.enabled = ctk.BooleanVar(value=settings["enabled"])
        self.sound = ctk.BooleanVar(value=settings["sound"])
        self.windows = ctk.BooleanVar(
            value=settings["windows_notifications"]
        )
        self.in_app = ctk.BooleanVar(
            value=settings["in_app_notifications"]
        )
        self.include_blueprints = ctk.BooleanVar(
            value=settings["include_blueprints"]
        )
        self.specific_any = ctk.BooleanVar(
            value=settings["specific_item_any_listing"]
        )
        self.minimum = ctk.StringVar(
            value=settings["minimum_rating"]
        )
        self.preset = ctk.StringVar(value=settings["loot_preset"])
        self.seconds = ctk.StringVar(
            value=str(settings["popup_seconds"])
        )
        self.repeat = ctk.StringVar(
            value=str(settings["repeat_hours"])
        )
        self.maximum_alerts = ctk.StringVar(
            value=str(settings["max_alerts"])
        )
        self.minimum_stock = ctk.StringVar(
            value=str(settings["minimum_stock"])
        )
        self.maximum_cost = ctk.StringVar(
            value=str(settings["maximum_cost"])
        )

        ctk.CTkSwitch(
            self,
            text="Enable alerts",
            variable=self.enabled,
        ).grid(row=0, column=0, sticky="w", padx=4, pady=5)
        ctk.CTkSwitch(
            self,
            text="Windows / fullscreen",
            variable=self.windows,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=5)
        ctk.CTkSwitch(
            self,
            text="In-app popup",
            variable=self.in_app,
        ).grid(row=0, column=2, sticky="w", padx=4, pady=5)
        ctk.CTkSwitch(
            self,
            text="Sound",
            variable=self.sound,
        ).grid(row=0, column=3, sticky="w", padx=4, pady=5)

        self._labeled_option(
            1,
            0,
            "Loot preset",
            list(LOOT_PRESETS),
            self.preset,
        )
        self._labeled_option(
            1,
            1,
            "Minimum deal rating",
            list(MINIMUM_RATING_OPTIONS),
            self.minimum,
        )
        self._labeled_option(
            1,
            2,
            "Popup seconds",
            ["5", "10", "15", "30", "60"],
            self.seconds,
        )
        self._labeled_option(
            1,
            3,
            "Repeat suppression (hours)",
            ["1", "6", "24", "72", "168", "720"],
            self.repeat,
        )

        ctk.CTkLabel(
            self,
            text="Specific items (comma-separated names or IDs)",
            text_color=MUTED,
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=4)
        self.specific_items = ctk.CTkEntry(
            self,
            placeholder_text=(
                "e.g. timed explosive charge, rocket, assault rifle"
            ),
        )
        self.specific_items.insert(
            0,
            ", ".join(settings["specific_items"]),
        )
        self.specific_items.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=4,
            pady=(2, 6),
        )
        ctk.CTkSwitch(
            self,
            text="Notify for any listing of watched items",
            variable=self.specific_any,
        ).grid(row=3, column=2, sticky="w", padx=4, pady=(2, 6))
        ctk.CTkSwitch(
            self,
            text="Include blueprint listings",
            variable=self.include_blueprints,
        ).grid(row=3, column=3, sticky="w", padx=4, pady=(2, 6))

        self._labeled_entry(
            4,
            0,
            "Minimum stock",
            self.minimum_stock,
        )
        self._labeled_entry(
            4,
            1,
            "Maximum total cost (0 = unlimited)",
            self.maximum_cost,
        )
        self._labeled_option(
            4,
            2,
            "Maximum alerts per scan",
            ["1", "3", "5", "10"],
            self.maximum_alerts,
        )

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(
            row=6,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(8, 2),
        )
        buttons.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(
            buttons,
            text="Save notification settings",
            command=self.save,
        ).grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkButton(
            buttons,
            text="Test notification",
            command=self.test,
            fg_color="transparent",
            border_width=1,
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(
            buttons,
            text="Clear alert history",
            command=self.clear_history,
            fg_color="transparent",
            border_width=1,
        ).grid(row=0, column=2, sticky="ew", padx=4)

        self.status = ctk.CTkLabel(
            self,
            text=(
                "Relative price alone does not create a steal. Automatic "
                "deal alerts require a worthwhile mid/high-tier progression item; "
                "explicit watched-item alerts can still notify for any listing."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        )
        self.status.grid(
            row=7,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=4,
            pady=(5, 0),
        )

    def _labeled_option(
        self,
        row: int,
        column: int,
        label: str,
        values: list[str],
        variable: ctk.StringVar,
    ) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=column, sticky="ew", padx=4, pady=5)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=label,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=10, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 2))
        ctk.CTkOptionMenu(
            frame,
            values=values,
            variable=variable,
        ).grid(row=1, column=0, sticky="ew")

    def _labeled_entry(
        self,
        row: int,
        column: int,
        label: str,
        variable: ctk.StringVar,
    ) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=column, sticky="ew", padx=4, pady=5)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=label,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=10, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 2))
        ctk.CTkEntry(
            frame,
            textvariable=variable,
        ).grid(row=1, column=0, sticky="ew")

    def values(self) -> dict:
        return {
            "enabled": bool(self.enabled.get()),
            "minimum_rating": self.minimum.get(),
            "loot_preset": self.preset.get(),
            "specific_items": self.specific_items.get(),
            "specific_item_any_listing": bool(self.specific_any.get()),
            "include_blueprints": bool(self.include_blueprints.get()),
            "minimum_stock": safe_int(self.minimum_stock.get(), 1),
            "maximum_cost": safe_int(self.maximum_cost.get(), 0),
            "sound": bool(self.sound.get()),
            "popup_seconds": safe_int(self.seconds.get(), 15),
            "repeat_hours": safe_int(self.repeat.get(), 72),
            "max_alerts": safe_int(self.maximum_alerts.get(), 3),
            "windows_notifications": bool(self.windows.get()),
            "in_app_notifications": bool(self.in_app.get()),
        }

    def save(self, *, show_confirmation: bool = True) -> dict:
        settings = save_notification_settings(
            self.context.store,
            self.values(),
        )
        self.status.configure(
            text=(
                f"Saved {settings['loot_preset']} · "
                f"{settings['minimum_rating']} · "
                f"{len(settings['specific_items'])} watched item(s)."
            )
        )
        if show_confirmation:
            messagebox.showinfo(
                "Marketplace notifications",
                "Notification settings were saved.",
            )
        return settings

    def test(self) -> None:
        self.save(show_confirmation=False)
        app = getattr(self.context, "app", None)
        publish = getattr(app, "publish_deal_alerts", None)
        if not callable(publish):
            messagebox.showerror(
                "Marketplace notifications",
                "The notification center is unavailable.",
            )
            return
        publish(
            [
                DealAlert(
                    fingerprint="dashboard-test",
                    severity=2,
                    title="Test marketplace notification",
                    message=(
                        "Fullscreen Windows and in-app notification paths "
                        "are using the settings currently shown here."
                    ),
                    label="TEST",
                    score=100,
                    grid="A1",
                    shop="Test Vending Machine",
                    item_name="Test Item",
                )
            ],
            force=True,
        )

    def clear_history(self) -> None:
        clear_deal_alert_history(self.context.store)
        self.status.configure(
            text=(
                "Alert history cleared. Current qualifying listings can "
                "notify again on the next marketplace scan."
            )
        )
        messagebox.showinfo(
            "Marketplace notifications",
            "Saved marketplace alert history was cleared.",
        )
