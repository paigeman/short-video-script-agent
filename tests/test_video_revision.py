import json
import unittest
from copy import deepcopy

from scripts.live_acceptance import assess, scenario
from src.llm.types import ModelResponse
from src.tools.executor import ToolExecutor
from src.tools.protocol import ToolCallRequest
from src.video.catalog import Catalog
from src.video.checks import VISUALS, estimate_duration
from src.video.offline import OfflineModel
from src.video.schemas import SCENE_SCHEMA, validate_brief
from src.video.service import run_script
from src.video.tools import VideoTools, draft_id
from tests.helpers import ScriptedModel
from tests.video_fixtures import brief, catalog, draft


class ExistingDraftTests(unittest.TestCase):
    def test_initial_draft_is_validated_without_mutating_input(self):
        request = brief(initial_draft=draft())
        original = deepcopy(request)
        self.assertEqual(validate_brief(request)[1:], ([], []))
        self.assertEqual(request, original)
        for bad in (
            "not a draft",
            {"title": "missing scenes"},
            {**draft(), "passed": True},
        ):
            with self.subTest(bad=bad):
                self.assertTrue(validate_brief(brief(initial_draft=bad))[2])

    def test_existing_draft_is_measured_then_revised_without_relaxing_limit(self):
        request, materials, policy, _ = scenario("duration-repair")
        original = deepcopy(request)
        loaded = Catalog(materials, policy)
        # Explicit offline unit fixture, not a live acceptance record.
        report = run_script(
            request, catalog=loaded, client=OfflineModel(request, policy)
        )
        self.assertEqual(report["status"], "completed")
        self.assertEqual(request, original)
        self.assertEqual(report["input"]["duration_seconds"], 10)
        estimates = [
            r for r in report["tool_records"] if r["tool"] == "estimate_duration"
        ]
        self.assertEqual(estimates[0]["arguments"]["script"], original["initial_draft"])
        self.assertFalse(estimates[0]["result"]["passed"])
        self.assertTrue(estimates[-1]["result"]["passed"])
        self.assertEqual(assess("duration-repair", report, request, loaded), [])
        estimates[0]["result"]["estimated_total_seconds"] = 99
        self.assertTrue(assess("duration-repair", report, request, loaded))

    def test_initial_draft_is_not_a_prevalidated_deliverable(self):
        initial = draft()
        response = ModelResponse(
            text=json.dumps({"status": "completed", "draft_id": draft_id(initial)})
        )
        report = run_script(
            brief(initial_draft=initial), client=ScriptedModel([response])
        )
        self.assertEqual(report["reason"], "final_checks_failed")
        self.assertIsNone(report["script"])

    def test_first_pass_success_cannot_count_as_duration_repair(self):
        request, materials, policy, _ = scenario("duration-repair")
        loaded = Catalog(materials, policy)
        without_initial = {k: v for k, v in request.items() if k != "initial_draft"}
        report = run_script(
            without_initial,
            catalog=loaded,
            client=OfflineModel(without_initial, policy),
        )
        self.assertTrue(assess("duration-repair", report, request, loaded))


class StoryboardTests(unittest.TestCase):
    def test_tutorial_accepts_detail_demonstration_but_requires_actual_demo(self):
        request, materials, policy, _ = scenario("style-tutorial")
        loaded = Catalog(materials, policy)

        class TutorialDouble(OfflineModel):
            demo_visual = "screen_demo"

            def draft(self, **kwargs):
                value = super().draft(**kwargs)
                first, second = value["scenes"]
                first.update(visual="step_card", hold_seconds=0)
                second.update(visual=self.demo_visual, hold_seconds=0)
                value["scenes"].append(dict(first, id="recap", visual="recap_card"))
                return value

        for visual in ("screen_demo", "screen_closeup", "title_card"):
            with self.subTest(visual=visual):
                client = TutorialDouble(request, policy)
                client.demo_visual = visual
                report = run_script(request, catalog=loaded, client=client)
                self.assertEqual(report["status"], "completed")
                self.assertEqual(
                    bool(assess("style-tutorial", report, request, loaded)),
                    visual == "title_card",
                )

    def test_teaser_assessment_rejects_repetitive_but_grounded_copy(self):
        request, materials, policy, _ = scenario("style-teaser")
        loaded = Catalog(materials, policy)

        class TeaserDouble(OfflineModel):
            repeat = False

            def draft(self, **kwargs):
                value = super().draft(**kwargs)
                for scene in value["scenes"]:
                    scene.update(visual="screen_closeup", hold_seconds=0)
                if self.repeat:
                    value["scenes"].append(dict(value["scenes"][0], id="repeat"))
                return value

        for repeat in (False, True):
            with self.subTest(repeat=repeat):
                client = TeaserDouble(request, policy)
                client.repeat = repeat
                report = run_script(request, catalog=loaded, client=client)
                self.assertEqual(report["status"], "completed")
                self.assertEqual(
                    bool(assess("style-teaser", report, request, loaded)), repeat
                )

    def test_timeline_matches_rounded_transition_total(self):
        value = draft()
        value["scenes"] = [dict(value["scenes"][0], id=f"S{i}") for i in range(4)]
        timing = {**catalog().policy["timing"], "transition_seconds": 0.15}
        report = estimate_duration(value, 30, timing)
        self.assertEqual(report["scenes"][0]["start_seconds"], 0)
        self.assertEqual(
            report["scenes"][-1]["end_seconds"], report["estimated_total_seconds"]
        )
        gaps = []
        for index, scene in enumerate(report["scenes"]):
            self.assertAlmostEqual(
                scene["end_seconds"] - scene["start_seconds"],
                scene["estimated_seconds"],
            )
            if index:
                gap = (
                    scene["start_seconds"] - report["scenes"][index - 1]["end_seconds"]
                )
                self.assertGreaterEqual(gap, 0)
                gaps.append(gap)
        self.assertAlmostEqual(sum(gaps), report["transition_seconds"])

    def test_visual_choices_preserve_facts_and_checked_timeline(self):
        self.assertEqual(
            set(SCENE_SCHEMA["properties"]["visual"]["enum"]), set(VISUALS)
        )
        for visual in VISUALS:
            with self.subTest(visual=visual):
                tools = VideoTools(brief(), catalog())
                tools.search({"query": "P01"})
                value = draft()
                value["scenes"][0]["visual"] = visual
                result = ToolExecutor(tools.registry()).execute_call(
                    ToolCallRequest(
                        "e1",
                        "estimate_duration",
                        json.dumps({"script": value, "reason": "test"}),
                    )
                )
                key = json.loads(result.output)["draft_id"]
                tools.check({"draft_id": key})
                delivered, issues = tools.finalize(key)
                self.assertEqual(issues, [])
                self.assertEqual(delivered["scenes"][0]["visual_kind"], visual)
                self.assertEqual(
                    delivered["scenes"][0]["end_seconds"],
                    delivered["estimated_total_seconds"],
                )
                value["scenes"][0]["narration"] = "guaranteed improvement 80%"
                bad_key = tools.estimate({"script": value})["draft_id"]
                self.assertFalse(tools.check({"draft_id": bad_key})["passed"])
                self.assertIsNone(tools.finalize(bad_key)[0])

    def test_assessor_rejects_modified_visual_or_timeline(self):
        request, materials, policy, _ = scenario("normal")
        loaded = Catalog(materials, policy)
        report = run_script(
            request, catalog=loaded, client=OfflineModel(request, policy)
        )
        for field, value in (
            ("visual_kind", "recap_card"),
            ("start_seconds", 100),
            ("end_seconds", 200),
        ):
            with self.subTest(field=field):
                changed = deepcopy(report)
                changed["script"]["scenes"][0][field] = value
                self.assertTrue(assess("normal", changed, request, loaded))
