from __future__ import annotations

import ast
import unittest
from pathlib import Path

from PIL import Image

from rust_companion_plus.ui.tabs.shops import (
    ShopOrderRow,
    matching_shop_rows,
    render_shop_minimap,
    shop_map_fraction,
)


SHOPS_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "rust_companion_plus"
    / "ui"
    / "tabs"
    / "shops.py"
)


def row(
    shop: str,
    grid: str,
    x: float,
    y: float,
    *,
    item_id: int = 100,
    item_name: str = "Assault Rifle",
    cost: int = 500,
    stock: int = 3,
    blueprint: bool = False,
) -> ShopOrderRow:
    return ShopOrderRow(
        shop=shop,
        grid=grid,
        x=x,
        y=y,
        item_id=item_id,
        item_name=item_name,
        quantity=1,
        currency_id=200,
        currency_name="Scrap",
        cost=cost,
        stock=stock,
        item_is_blueprint=blueprint,
        currency_is_blueprint=False,
    )


class ShopMinimapCoordinateTests(unittest.TestCase):
    def test_positive_rustplus_coordinates_map_to_top_left_pixels(self) -> None:
        self.assertEqual((0.0, 1.0), shop_map_fraction(0, 0, 4000))
        self.assertEqual((1.0, 0.0), shop_map_fraction(4000, 4000, 4000))
        self.assertEqual((0.25, 0.25), shop_map_fraction(1000, 3000, 4000))

    def test_negative_centered_coordinate_fallback(self) -> None:
        self.assertEqual((0.0, 1.0), shop_map_fraction(-2000, -2000, 4000))
        self.assertEqual((0.25, 0.25), shop_map_fraction(-1000, 1000, 4000))

    def test_invalid_map_size_returns_none(self) -> None:
        self.assertIsNone(shop_map_fraction(100, 100, 0))


class ShopMinimapMatchingTests(unittest.TestCase):
    def test_selected_item_matches_one_best_offer_per_shop(self) -> None:
        selected = row("Alpha", "G6", 1000, 3000, cost=500)
        cheaper_same_shop = row("Alpha", "G6", 1000, 3000, cost=450)
        other_shop = row("Bravo", "T20", 3000, 1000, cost=550)
        wrong_item = row(
            "Charlie",
            "M12",
            2000,
            2000,
            item_id=300,
            item_name="Sulfur",
        )
        blueprint = row(
            "Delta",
            "A1",
            100,
            3900,
            blueprint=True,
        )

        matches = matching_shop_rows(
            [cheaper_same_shop, other_shop, wrong_item, blueprint],
            selected,
        )

        self.assertEqual(["Alpha", "Bravo"], [item.shop for item in matches])
        self.assertIs(selected, matches[0])

    def test_selected_shop_is_orange_and_other_match_is_green(self) -> None:
        selected = row("Alpha", "G6", 1000, 3000)
        other = row("Bravo", "T20", 3000, 1000)
        base = Image.new("RGBA", (400, 400), (0, 0, 0, 255))

        result = render_shop_minimap(
            base,
            [selected, other],
            selected,
            4000,
            output_size=(200, 200),
        )

        self.assertEqual((200, 200), result.size)
        selected_region = {
            result.getpixel((x, y))[:3]
            for x in range(43, 57)
            for y in range(43, 57)
        }
        other_region = {
            result.getpixel((x, y))[:3]
            for x in range(143, 157)
            for y in range(143, 157)
        }
        self.assertIn((245, 158, 11), selected_region)
        self.assertIn((34, 197, 94), other_region)

    def test_missing_base_map_still_renders_coordinate_grid(self) -> None:
        selected = row("Alpha", "G6", 1000, 3000)
        result = render_shop_minimap(
            None,
            [selected],
            selected,
            4000,
            output_size=(180, 180),
        )
        self.assertEqual((180, 180), result.size)


class ShopMinimapSourceContractTests(unittest.TestCase):
    def test_selection_event_renders_minimap(self) -> None:
        source = SHOPS_SOURCE.read_text(encoding="utf-8")
        self.assertIn('"<<TreeviewSelect>>"', source)
        self.assertIn("self._render_selected_minimap(row)", source)
        self.assertIn("self.minimap_label", source)
        self.assertIn("matching_shop_rows", source)

    def test_no_unsupported_ctkbutton_justify(self) -> None:
        source = SHOPS_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(SHOPS_SOURCE))
        offenders: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_button = (
                isinstance(func, ast.Attribute)
                and func.attr == "CTkButton"
                and isinstance(func.value, ast.Name)
                and func.value.id == "ctk"
            )
            if not is_button:
                continue
            offenders.extend(
                keyword.lineno
                for keyword in node.keywords
                if keyword.arg == "justify"
            )
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
