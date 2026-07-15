from __future__ import annotations

import ast
import unittest
from pathlib import Path


ELECTRICAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "rust_companion_plus"
    / "ui"
    / "tabs"
    / "electrical.py"
)


def is_ctk_button_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "CTkButton"
        and isinstance(func.value, ast.Name)
        and func.value.id == "ctk"
    )


class CustomTkinterButtonContractTests(unittest.TestCase):
    def test_ctk_buttons_never_receive_unsupported_justify_keyword(self) -> None:
        source = ELECTRICAL_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(ELECTRICAL_PATH))

        offenders: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not is_ctk_button_call(node):
                continue
            offenders.extend(
                keyword.lineno
                for keyword in node.keywords
                if keyword.arg == "justify"
            )

        self.assertEqual(
            offenders,
            [],
            "CTkButton does not support justify; use anchor for button text alignment.",
        )

    def test_palette_button_keeps_left_anchor(self) -> None:
        source = ELECTRICAL_PATH.read_text(encoding="utf-8")
        self.assertIn('button = ctk.CTkButton(', source)
        self.assertIn('anchor="w"', source)


if __name__ == "__main__":
    unittest.main()
