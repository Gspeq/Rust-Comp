from __future__ import annotations

import math

import customtkinter as ctk

from rust_companion_plus.models import ElectricalSetup, SetupComponent
from rust_companion_plus.services.electrical import analyze_setup, parse_component_text
from rust_companion_plus.ui.common import MUTED
from rust_companion_plus.ui.tabs.electrical import ElectricalTab as AdvancedElectricalTab


EXAMPLES = {
    "Starter base": "1 large solar panel, 1 small battery, 3 ceiling lights, 2 door controllers",
    "Turret defense": "2 wind turbines, 2 large batteries, 8 auto turrets, 8 electrical branches",
    "Industrial base": "4 large solar panels, 1 wind turbine, 2 large batteries, 6 industrial conveyors, 2 electric furnaces, 4 ceiling lights",
}


class ElectricalTab(ctk.CTkFrame):
    """A beginner-first planner backed by the existing advanced circuit canvas."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Electrical Planner",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.grid(row=1, column=0, sticky="nsew")
        self.tabs.add("Simple Planner")
        self.tabs.add("Advanced Circuit")

        self._build_simple(self.tabs.tab("Simple Planner"))
        self.advanced = AdvancedElectricalTab(
            self.tabs.tab("Advanced Circuit"),
            context,
        )
        self.advanced.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_simple(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            parent,
            text=(
                "Describe what you want to power. The planner recognizes common Rust electrical "
                "parts, calculates load, generation, batteries, runtime, and tells you what to fix."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=1100,
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        self.goal = ctk.CTkTextbox(parent, height=110, corner_radius=8)
        self.goal.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        self.goal.insert(
            "1.0",
            "6 auto turrets, 4 ceiling lights, 6 door controllers, 2 large solar panels, 1 wind turbine, and 1 large battery",
        )

        examples = ctk.CTkFrame(parent, fg_color="transparent")
        examples.grid(row=2, column=0, sticky="ew", padx=14, pady=6)
        for column, (name, text) in enumerate(EXAMPLES.items()):
            examples.grid_columnconfigure(column, weight=1)
            ctk.CTkButton(
                examples,
                text=name,
                fg_color="transparent",
                border_width=1,
                command=lambda value=text: self._set_goal(value),
            ).grid(row=0, column=column, sticky="ew", padx=4)

        assumptions = ctk.CTkFrame(parent, fg_color="transparent")
        assumptions.grid(row=3, column=0, sticky="ew", padx=14, pady=6)
        assumptions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.solar = ctk.CTkEntry(assumptions, placeholder_text="Solar average %")
        self.wind = ctk.CTkEntry(assumptions, placeholder_text="Wind average %")
        self.charge = ctk.CTkEntry(assumptions, placeholder_text="Battery charge %")
        self.solar.insert(0, "35")
        self.wind.insert(0, "55")
        self.charge.insert(0, "100")
        for column, entry in enumerate((self.solar, self.wind, self.charge)):
            entry.grid(row=0, column=column, sticky="ew", padx=4)
        ctk.CTkButton(
            assumptions,
            text="Analyze this setup",
            command=self.analyze_simple,
        ).grid(row=0, column=3, sticky="ew", padx=4)

        self.summary = ctk.CTkLabel(
            parent,
            text="Enter a setup and select Analyze.",
            text_color=MUTED,
            anchor="w",
            justify="left",
        )
        self.summary.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 6))

        self.result = ctk.CTkTextbox(parent, corner_radius=8, wrap="word")
        self.result.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.analyze_simple()

    def _set_goal(self, value: str) -> None:
        self.goal.delete("1.0", "end")
        self.goal.insert("1.0", value)
        self.analyze_simple()

    @staticmethod
    def _fraction(entry: ctk.CTkEntry, default: float) -> float:
        try:
            value = float(entry.get().strip()) / 100.0
        except (TypeError, ValueError):
            value = default
        return min(1.0, max(0.0, value))

    @staticmethod
    def _runtime(minutes: float) -> str:
        if math.isinf(minutes):
            return "indefinite"
        if minutes < 60:
            return f"{minutes:.0f} minutes"
        return f"{minutes / 60.0:.1f} hours"

    def analyze_simple(self) -> None:
        text = self.goal.get("1.0", "end").strip()
        parsed = parse_component_text(text)
        setup = ElectricalSetup(
            name="Quick Plan",
            components=[
                SetupComponent(name, quantity, "Planned", "Main")
                for name, quantity in sorted(parsed.components.items())
            ],
            assumptions={
                "solar_utilization": self._fraction(self.solar, 0.35),
                "wind_utilization": self._fraction(self.wind, 0.55),
                "battery_charge_fraction": self._fraction(self.charge, 1.0),
            },
        )
        analysis = analyze_setup(setup)

        recognized = sum(parsed.components.values())
        self.summary.configure(
            text=(
                f"Recognized {recognized} component(s) across {len(parsed.components)} type(s). "
                "Use Advanced Circuit for exact branches, switches, paths, and redundancy."
            )
        )

        lines = [
            "QUICK ELECTRICAL ANSWER",
            "",
            f"Active load: {analysis.load_rw:.0f} rW",
            f"Peak generation: {analysis.peak_generation_rw:.0f} rW",
            f"Estimated usable average: {analysis.usable_generation_rw:.0f} rW",
            f"Battery storage: {analysis.battery_capacity_rwm:,.0f} rWm",
            f"Battery output limit: {analysis.battery_output_limit_rw:.0f} rW",
            f"Runtime with no generation: {self._runtime(analysis.no_generation_runtime_minutes)}",
            f"Estimated runtime with average generation: {self._runtime(analysis.estimated_runtime_minutes)}",
            f"Peak headroom: {analysis.peak_headroom_rw:+.0f} rW",
            "",
            "RECOGNIZED PARTS",
        ]
        if parsed.components:
            lines.extend(
                f"- {quantity} × {name}"
                for name, quantity in sorted(parsed.components.items())
            )
        else:
            lines.append("- None")

        if parsed.unmatched:
            lines.extend(("", "NOT RECOGNIZED"))
            lines.extend(f"- {value}" for value in parsed.unmatched)

        lines.extend(("", "RECOMMENDATIONS"))
        lines.extend(
            f"{index}. {recommendation}"
            for index, recommendation in enumerate(
                analysis.recommendations or ["[Info] No obvious aggregate power issue."],
                start=1,
            )
        )
        lines.extend(
            (
                "",
                "ADVANCED MODE",
                "Open Advanced Circuit to draw actual wiring paths, inspect each component, "
                "detect loops and disconnected loads, calculate branch topology, save layouts, "
                "and receive path-specific fixes.",
            )
        )
        self.result.delete("1.0", "end")
        self.result.insert("1.0", "\n".join(lines))

    def on_context_updated(self) -> None:
        callback = getattr(self.advanced, "on_context_updated", None)
        if callable(callback):
            callback()
