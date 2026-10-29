import json
import unittest
from copy import deepcopy

from src.tools.executor import ToolExecutor
from src.tools.protocol import ToolCallRequest
from src.video.catalog import Catalog
from src.video.checks import check_rules, estimate_duration, units
from src.video.tools import VideoTools, draft_id
from tests.video_fixtures import brief, catalog, draft


class VideoToolTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog()
        self.tools = VideoTools(brief(), self.catalog)
        self.tools.search({"query": "字幕"})
        self.script = draft()

    def test_search_handles_rewrites_and_stays_within_product(self):
        materials = deepcopy(self.catalog.materials)
        materials.append({**materials[0], "id": "OTHER", "product_id": "P02"})
        loaded = Catalog(
            {"synthetic": True, "materials": materials}, self.catalog.policy
        )
        self.assertEqual(loaded.search("P01", "nothing matches"), [])
        for query in ("字幕草稿生成", "手动修改", "P01", "M01"):
            with self.subTest(query=query):
                results = loaded.search("P01", query)
                self.assertEqual([item["source_id"] for item in results], ["M01"])
        self.assertEqual(loaded.search("P404", "字幕"), [])

    def test_search_size_limit_only_marks_delivered_facts_as_retrieved(self):
        materials = [
            {
                "id": f"M{i}",
                "product_id": "P01",
                "title": "长资料",
                "source": "合成资料",
                "facts": [f"第{n}条" + "字" * 450 for n in range(20)],
            }
            for i in range(5)
        ]
        loaded = Catalog(
            {"synthetic": True, "materials": materials}, self.catalog.policy
        )
        tools = VideoTools(brief(), loaded)
        output = tools.search({"query": "P01"})
        returned = {
            fact["fact_id"] for item in output["materials"] for fact in item["facts"]
        }
        self.assertTrue(output["truncated"])
        self.assertEqual(tools.retrieved, returned)
        self.assertLess(len(returned), len(loaded.facts))
        self.assertLess(len(json.dumps(output, ensure_ascii=False).encode()), 17_000)

    def test_timing_uses_narration_subtitles_hold_and_transitions(self):
        self.script["scenes"][0].update(
            narration="一二三四五六七八", subtitle="", hold_seconds=1
        )
        first = estimate_duration(self.script, 2, self.catalog.policy["timing"])
        self.assertEqual(first["estimated_total_seconds"], 2)
        self.assertTrue(first["passed"])
        second = deepcopy(self.script["scenes"][0])
        second.update(id="S2", narration="", subtitle="一" * 30, hold_seconds=0)
        self.script["scenes"].append(second)
        report = estimate_duration(self.script, 7, self.catalog.policy["timing"])
        self.assertEqual(report["estimated_total_seconds"], 7.4)
        self.assertFalse(report["passed"])
        self.assertEqual(report["over_by_seconds"], 0.4)
        self.assertEqual(units("AI 字幕 12"), 5)

    def test_timing_rounds_up_and_does_not_trust_declared_total(self):
        self.script["scenes"][0].update(narration="一。", subtitle="", hold_seconds=0)
        report = estimate_duration(self.script, 1, self.catalog.policy["timing"])
        self.assertEqual(report["estimated_total_seconds"], 0.4)
        self.script["estimated_total_seconds"] = 0
        executor = ToolExecutor(self.tools.registry())
        output = executor.execute_call(
            ToolCallRequest(
                "c1",
                "estimate_duration",
                json.dumps({"script": self.script, "reason": "test"}),
            )
        )
        self.assertEqual(
            json.loads(output.output)["error"]["category"], "invalid_arguments"
        )

    def test_valid_copy_has_exact_source_and_fact_mapping(self):
        self.script["scenes"][0]["narration"] = "先看这里\uff0c支持生成字幕草稿。"
        result = check_rules(self.script, self.catalog, "P01", self.tools.retrieved)
        self.assertTrue(result["passed"])
        self.assertEqual(result["citations"][0]["source_id"], "M01")

    def test_unsupported_claims_are_rejected_in_every_copy_field(self):
        for field in ("title", "narration", "subtitle"):
            with self.subTest(field=field):
                value = draft()
                target = value if field == "title" else value["scenes"][0]
                target[field] += "\uff0c效率提升80%\uff0c保证有效"
                result = check_rules(value, self.catalog, "P01", self.tools.retrieved)
                codes = {issue["code"] for issue in result["issues"]}
                self.assertTrue(
                    {"unverified_copy", "unsupported_number", "prohibited_claim"}
                    <= codes
                )

    def test_citations_cannot_be_forged_unused_or_cross_product(self):
        for fact_ids, retrieved, product, code in (
            (["missing"], self.tools.retrieved, "P01", "unknown_fact"),
            (["M01:F1"], set(), "P01", "unretrieved_fact"),
            (["M01:F1"], self.tools.retrieved, "P02", "wrong_product"),
            (["M01:F2"], self.tools.retrieved, "P01", "unused_citation"),
            ([], self.tools.retrieved, "P01", "missing_evidence"),
        ):
            with self.subTest(code=code):
                self.script["scenes"][0]["fact_ids"] = fact_ids
                result = check_rules(self.script, self.catalog, product, retrieved)
                self.assertFalse(result["passed"])
                self.assertIn(code, [issue["code"] for issue in result["issues"]])

    def test_quantified_copy_requires_the_exact_cited_fact(self):
        for original, changed in (
            ("支持8种字幕样式", "支持9种字幕样式"),
            ("字幕示例长0.8秒", "字幕示例长08秒"),
            ("支持100种字幕样式", "支持1000种字幕样式"),
        ):
            with self.subTest(original=original):
                materials = deepcopy(self.catalog.materials)
                materials[0]["facts"] = [original]
                loaded = Catalog(
                    {"synthetic": True, "materials": materials}, self.catalog.policy
                )
                value = draft()
                value["scenes"][0].update(narration=original, subtitle=original)
                self.assertTrue(check_rules(value, loaded, "P01", {"M01:F1"})["passed"])
                value["scenes"][0]["narration"] = changed
                self.assertFalse(
                    check_rules(value, loaded, "P01", {"M01:F1"})["passed"]
                )

    def test_duplicate_scene_ids_empty_copy_and_empty_title_fail(self):
        self.script["scenes"].append(deepcopy(self.script["scenes"][0]))
        self.script["scenes"][1].update(narration="", subtitle="")
        self.script["title"] = "!!!"
        codes = {
            issue["code"]
            for issue in check_rules(
                self.script, self.catalog, "P01", self.tools.retrieved
            )["issues"]
        }
        self.assertTrue(
            {"duplicate_scene_id", "empty_scene_copy", "empty_title"} <= codes
        )

    def test_final_gate_requires_both_checks_for_exact_draft(self):
        report = self.tools.estimate({"script": self.script})
        key = report["draft_id"]
        self.assertIsNone(self.tools.finalize(key)[0])
        self.tools.check({"draft_id": key})
        delivered, issues = self.tools.finalize(key)
        self.assertEqual(issues, [])
        self.assertEqual(
            delivered["estimated_total_seconds"], report["estimated_total_seconds"]
        )
        changed = deepcopy(self.script)
        changed["scenes"][0]["hold_seconds"] = 100
        other = self.tools.estimate({"script": changed})["draft_id"]
        self.assertNotEqual(key, other)
        self.assertIsNone(self.tools.finalize(other)[0])
        self.tools.check({"draft_id": other})
        self.assertIn(
            "duration_exceeded",
            [issue["code"] for issue in self.tools.finalize(other)[1]],
        )
        self.tools.drafts[key]["title"] = "一起看看"
        self.assertEqual(self.tools.finalize(key)[1][0]["code"], "draft_changed")

    def test_failed_rule_receipt_cannot_be_reused_after_retrieval(self):
        tools = VideoTools(brief(), self.catalog)
        key = tools.estimate({"script": self.script})["draft_id"]
        self.assertFalse(tools.check({"draft_id": key})["passed"])
        tools.search({"query": "P01"})
        self.assertIsNone(tools.finalize(key)[0])
        self.assertTrue(tools.check({"draft_id": key})["passed"])
        self.assertIsNotNone(tools.finalize(key)[0])

    def test_draft_hash_is_order_independent_and_storage_copies_input(self):
        reversed_keys = dict(reversed(list(self.script.items())))
        self.assertEqual(draft_id(self.script), draft_id(reversed_keys))
        key = self.tools.estimate({"script": self.script})["draft_id"]
        self.script["title"] = "modified"
        self.assertEqual(self.tools.drafts[key]["title"], "功能小演示")
