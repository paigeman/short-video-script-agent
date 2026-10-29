import unittest
from copy import deepcopy

from scripts.live_acceptance import assess, scenario
from src.video.catalog import Catalog
from src.video.offline import OfflineModel
from src.video.service import run_script
from tests.helpers import ScriptedModel
from tests.video_fixtures import brief, catalog


class LiveFailureInjectionTests(unittest.TestCase):
    def test_live_model_receives_real_tool_failure_and_can_retry(self):
        loaded = catalog()
        client = OfflineModel(brief(), loaded.policy, "tool-failure")
        report = run_script(
            brief(),
            client=client,
            catalog=loaded,
            evaluation_failures={"search_materials": 1},
        )
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["tool_records"][0]["status"], "error")
        self.assertEqual(report["tool_records"][1]["status"], "returned")
        self.assertEqual(
            report["evaluation"],
            {
                "injected_tool_failures": {"search_materials": 1},
                "scope": "local_tools_only",
            },
        )

    def test_live_persistent_fault_does_not_become_a_success(self):
        loaded = catalog()
        report = run_script(
            brief(),
            client=OfflineModel(brief(), loaded.policy, "persistent-failure"),
            catalog=loaded,
            evaluation_failures={"search_materials": 100},
        )
        self.assertEqual(
            (report["status"], report["reason"]), ("incomplete", "tool_failure")
        )
        self.assertTrue(all(r["status"] == "error" for r in report["tool_records"]))
        self.assertIsNone(report["script"])

    def test_fault_plan_is_validated_before_calling_the_model(self):
        for plan in (
            {"unknown": 1},
            {"search_materials": True},
            {"search_materials": 0},
            {"search_materials": 101},
            [],
        ):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                run_script(brief(), client=ScriptedModel([]), evaluation_failures=plan)
        with self.assertRaises(ValueError):
            run_script(
                brief(), mode="offline", evaluation_failures={"search_materials": 1}
            )

    def test_user_input_cannot_enable_live_fault_injection(self):
        report = run_script(
            {**brief(), "evaluation_failures": {"search_materials": 1}},
            client=ScriptedModel([]),
        )
        self.assertEqual(report["status"], "invalid_input")
        self.assertIsNone(report["runtime"])


class AcceptanceAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.request, materials, policy, _ = scenario("normal")
        self.catalog = Catalog(materials, policy)
        # Offline-only unit fixtures exercise the assessor, never published as live evidence.
        self.report = run_script(
            self.request,
            client=OfflineModel(self.request, policy),
            catalog=self.catalog,
        )

    def test_checked_output_passes_assessment(self):
        self.assertEqual(assess("normal", self.report, self.request, self.catalog), [])

    def test_delivery_tampering_and_missing_receipts_fail_assessment(self):
        def tamper_scene(report):
            report["script"]["scenes"][0]["narration"] = "unsupported claim 80%"

        def tamper_duration(report):
            report["script"]["estimated_total_seconds"] = 0

        def remove_receipt(report):
            report["tool_records"] = [
                r for r in report["tool_records"] if r["tool"] != "check_rules"
            ]

        for mutate in (tamper_scene, tamper_duration, remove_receipt):
            with self.subTest(mutate=mutate.__name__):
                report = deepcopy(self.report)
                mutate(report)
                self.assertTrue(assess("normal", report, self.request, self.catalog))

    def test_offline_evidence_cannot_pass_live_assessment(self):
        self.report["mode"] = "offline"
        self.assertTrue(assess("normal", self.report, self.request, self.catalog))

    def test_changed_materials_cannot_reuse_old_script(self):
        request, materials, policy, _ = scenario("changed-materials")
        self.assertTrue(
            assess(
                "changed-materials", self.report, request, Catalog(materials, policy)
            )
        )

    def test_unfinished_report_cannot_smuggle_script(self):
        self.report.update(status="needs_input", question="Need evidence")
        self.assertTrue(
            assess("unsupported-claim", self.report, self.request, self.catalog)
        )
