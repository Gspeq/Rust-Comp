from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from rust_companion_plus.services import exact_map_intelligence
from rust_companion_plus.services import server_profiles
from rust_companion_plus.services.exact_map_intelligence import (
    ExactMapIntelligenceResult,
)
from rust_companion_plus.services.server_profiles import (
    ParsedMapResult,
)


class ExactMonumentHotfixRepairTests(unittest.TestCase):
    def test_parsed_map_result_is_one_frozen_dataclass(
        self,
    ) -> None:
        self.assertTrue(
            dataclasses.is_dataclass(ParsedMapResult)
        )
        self.assertTrue(
            ParsedMapResult.__dataclass_params__.frozen
        )
        self.assertEqual(
            [
                "source_dir",
                "raw_map_path",
                "map_url",
                "created",
                "exact_parser_status",
                "monument_count",
                "exact_error",
            ],
            [
                field.name
                for field in dataclasses.fields(
                    ParsedMapResult
                )
            ],
        )

    def test_exact_map_service_exports_real_result_type(
        self,
    ) -> None:
        self.assertTrue(
            dataclasses.is_dataclass(
                ExactMapIntelligenceResult
            )
        )
        self.assertTrue(
            ExactMapIntelligenceResult
            .__dataclass_params__
            .frozen
        )
        self.assertTrue(
            callable(
                exact_map_intelligence
                .export_exact_map_intelligence
            )
        )

    def test_source_has_no_duplicate_profile_decorator(
        self,
    ) -> None:
        source = Path(
            server_profiles.__file__
        ).read_text(encoding="utf-8")
        duplicated = (
            "@dataclass(frozen=True, slots=True)\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class ParsedMapResult:"
        )
        self.assertNotIn(duplicated, source)


if __name__ == "__main__":
    unittest.main()
