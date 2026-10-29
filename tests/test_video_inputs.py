import unittest
from copy import deepcopy

from jsonschema.exceptions import ValidationError

from src.video.catalog import Catalog
from src.video.schemas import validate_brief
from src.video.service import run_script
from tests.video_fixtures import brief, catalog


class VideoInputTests(unittest.TestCase):
    def test_normalization_does_not_change_caller_input(self):
        value = brief(topic="  介绍字幕  ")
        original = deepcopy(value)
        parsed, missing, errors = validate_brief(value)
        self.assertEqual(parsed["topic"], "介绍字幕")
        self.assertEqual((missing, errors), ([], []))
        self.assertEqual(value, original)

    def test_each_missing_required_field_requests_input_without_model(self):
        class NeverCalled:
            def send(self, request):
                raise AssertionError("Model should not be called")

        for name in (
            "topic",
            "audience",
            "platform",
            "duration_seconds",
            "style",
            "product_id",
        ):
            for replacement in (None, "", "   "):
                with self.subTest(name=name, replacement=replacement):
                    value = brief(**{name: replacement})
                    report = run_script(value, client=NeverCalled(), mode="offline")
                    self.assertEqual(report["status"], "needs_input")
                    self.assertIn(name, report["missing_fields"])
                    self.assertIsNone(report["script"])

    def test_invalid_inputs_are_not_silently_coerced(self):
        for value in (
            [],
            None,
            brief(duration_seconds=True),
            brief(duration_seconds=0),
            brief(duration_seconds=301),
            brief(duration_seconds="30"),
            brief(duration_seconds=1.5),
            brief(product_id="../P01"),
            brief(extra="unknown"),
            brief(style=["简洁"]),
        ):
            with self.subTest(value=value):
                report = run_script(value, mode="offline")
                self.assertEqual(report["status"], "invalid_input")
                self.assertIsNone(report["runtime"])

    def test_fault_injection_is_offline_only(self):
        report = run_script(brief(simulate_tool_failure=True), mode="live")
        self.assertEqual(report["status"], "invalid_input")
        self.assertEqual(report["issues"][0]["code"], "offline_only")

    def test_catalog_rejects_invalid_and_ambiguous_data(self):
        loaded = catalog()
        base = {"synthetic": True, "materials": loaded.materials}
        for materials, policy in (
            ({**base, "materials": loaded.materials * 2}, loaded.policy),
            ({**base, "synthetic": False}, loaded.policy),
            (
                base,
                {
                    **loaded.policy,
                    "timing": {**loaded.policy["timing"], "speech_units_per_second": 0},
                },
            ),
            (
                base,
                {
                    **loaded.policy,
                    "timing": {
                        **loaded.policy["timing"],
                        "speech_units_per_second": float("nan"),
                    },
                },
            ),
        ):
            with (
                self.subTest(materials=materials),
                self.assertRaises((ValueError, ValidationError)),
            ):
                Catalog(materials, policy)
