import json
import unittest
from copy import deepcopy

import httpx

from src.config import ModelConfig
from src.llm.responses import ResponsesClient
from src.llm.types import Message, ModelRequest, ModelResponse
from src.tools.limits import ToolLoopLimits
from src.tools.protocol import ToolCallRequest, ToolCallResult
from src.video.catalog import Catalog
from src.video.offline import OfflineModel
from src.video.service import run_script
from src.video.tools import draft_id
from tests.helpers import ScriptedModel
from tests.test_responses_client import response_body, text_item
from tests.video_fixtures import brief, catalog, draft


class VideoServiceTests(unittest.TestCase):
    def test_normal_generation_has_authoritative_per_scene_checks(self):
        report = run_script(brief(), mode="offline")
        self.assertEqual(
            (report["status"], report["reason"]), ("completed", "validated_script")
        )
        script = report["script"]
        self.assertEqual(script["sources"][0]["id"], "M01")
        duration = script["checks"]["duration"]
        self.assertAlmostEqual(
            sum(scene["estimated_seconds"] for scene in script["scenes"])
            + duration["transition_seconds"],
            script["estimated_total_seconds"],
        )
        self.assertLessEqual(script["estimated_total_seconds"], 30)
        self.assertEqual(
            [record["tool"] for record in report["tool_records"]],
            ["search_materials", "estimate_duration", "check_rules"],
        )
        self.assertTrue(all(record["reason"] for record in report["tool_records"]))
        self.assertEqual(report["trace"][-1]["event"], "business_final_gate")

    def test_duration_failure_changes_draft_and_rechecks(self):
        report = run_script(
            brief(duration_seconds=10),
            mode="offline",
            offline_scenario="duration-repair",
        )
        estimates = [
            r["result"]
            for r in report["tool_records"]
            if r["tool"] == "estimate_duration"
        ]
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(estimates), 2)
        self.assertFalse(estimates[0]["passed"])
        self.assertTrue(estimates[1]["passed"])
        self.assertNotEqual(estimates[0]["draft_id"], estimates[1]["draft_id"])
        self.assertEqual(report["script"]["draft_id"], estimates[1]["draft_id"])
        self.assertEqual(report["input"]["duration_seconds"], 10)

    def test_brand_failure_is_repaired_and_checked_again(self):
        report = run_script(brief(), mode="offline", offline_scenario="rules-repair")
        checks = [
            r["result"] for r in report["tool_records"] if r["tool"] == "check_rules"
        ]
        self.assertEqual(report["status"], "completed")
        self.assertEqual([check["passed"] for check in checks], [False, True])
        self.assertNotIn("80%", json.dumps(report["script"], ensure_ascii=False))
        self.assertIn(
            "unsupported_number", [issue["code"] for issue in checks[0]["issues"]]
        )

    def test_unrepairable_duration_is_never_success(self):
        report = run_script(
            brief(duration_seconds=1), mode="offline", offline_scenario="unrepairable"
        )
        self.assertEqual(
            (report["status"], report["reason"]),
            ("incomplete", "cannot_meet_constraints"),
        )
        self.assertIsNone(report["script"])
        self.assertTrue(
            all(not item["duration_check"]["passed"] for item in report["drafts"])
        )

    def test_no_materials_rewrites_then_requests_input(self):
        report = run_script(brief(product_id="P404"), mode="offline")
        queries = [r["arguments"]["query"] for r in report["tool_records"]]
        self.assertEqual(queries, [brief()["topic"], "P404"])
        self.assertEqual(report["status"], "needs_input")
        self.assertIsNone(report["script"])
        self.assertEqual(report["drafts"], [])
        self.assertTrue(report["question"])

    def test_user_answer_does_not_become_an_unverified_product_fact(self):
        questions = []

        def answer(question):
            questions.append(question)
            return "产品保证提升80%"

        report = run_script(
            brief(product_id="P404"), mode="offline", answer_provider=answer
        )
        self.assertEqual(len(questions), 1)
        self.assertEqual(report["status"], "incomplete")
        self.assertIsNone(report["script"])
        self.assertEqual(report["runtime"]["model_requests"], 4)
        self.assertEqual(report["runtime"]["tool_rounds"], 3)
        self.assertIn("user_input", [event["event"] for event in report["trace"]])

    def test_single_tool_failure_is_observed_and_recovered(self):
        report = run_script(brief(simulate_tool_failure=True), mode="offline")
        self.assertEqual(report["status"], "completed")
        records = report["tool_records"]
        self.assertEqual(records[0]["status"], "error")
        self.assertEqual(records[1]["tool"], "search_materials")
        self.assertEqual(records[1]["status"], "returned")
        self.assertEqual(report["runtime"]["tool_executions"], 4)

    def test_persistent_tool_failure_stops_with_preserved_error_records(self):
        report = run_script(
            brief(), mode="offline", offline_scenario="persistent-failure"
        )
        self.assertEqual(
            (report["status"], report["reason"]), ("incomplete", "tool_failure")
        )
        self.assertEqual(
            [r["status"] for r in report["tool_records"]], ["error", "error"]
        )
        self.assertIsNone(report["script"])

    def test_step_limit_is_explicit_and_preserves_observations(self):
        report = run_script(
            brief(),
            mode="offline",
            offline_scenario="limit",
            limits=ToolLoopLimits(max_tool_rounds=2),
        )
        self.assertEqual(report["reason"], "max_tool_rounds_reached")
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(report["tool_records"]), 2)

    def test_changed_material_changes_generated_copy_and_citations(self):
        loaded = catalog()
        materials = deepcopy(loaded.materials)
        materials[0]["facts"] = ["支持导出纯文本字幕"]
        changed = Catalog({"synthetic": True, "materials": materials}, loaded.policy)
        report = run_script(brief(), mode="offline", catalog=changed)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(
            report["script"]["scenes"][0]["narration"], materials[0]["facts"][0]
        )
        self.assertEqual(
            report["script"]["sources"][0]["facts"][0]["text"], materials[0]["facts"][0]
        )

    def test_model_cannot_skip_checks_or_deliver_an_unchecked_revision(self):
        value = draft()
        key = draft_id(value)
        forged = ModelResponse(
            text=json.dumps({"status": "completed", "draft_id": key})
        )
        for responses in (
            [forged],
            [
                ModelResponse(
                    tool_calls=[
                        ToolCallRequest(
                            "e1",
                            "estimate_duration",
                            json.dumps({"script": value, "reason": "estimate"}),
                        )
                    ]
                ),
                forged,
            ],
        ):
            with self.subTest(responses=responses):
                report = run_script(
                    brief(), client=ScriptedModel(responses), mode="offline"
                )
                self.assertEqual(report["runtime"]["status"], "completed")
                self.assertEqual(
                    (report["status"], report["reason"]),
                    ("incomplete", "final_checks_failed"),
                )
                self.assertEqual(report["issues"][0]["code"], "missing_checks")
                self.assertIsNone(report["script"])

    def test_configured_sdk_business_path_uses_actual_function_results(self):
        loaded = catalog()
        offline = OfflineModel(
            brief(duration_seconds=10), loaded.policy, "duration-repair"
        )
        requests = []

        def handle(request):
            body = json.loads(request.content)
            requests.append(body)
            inputs = []
            for item in body["input"]:
                if item.get("type") == "function_call_output":
                    inputs.append(ToolCallResult(item["call_id"], item["output"]))
                elif isinstance(item.get("content"), str):
                    inputs.append(Message(item["role"], item["content"]))
            response = offline.send(ModelRequest(inputs))
            output = [text_item(response.text)] if response.text else []
            output.extend(
                {
                    "type": "function_call",
                    "id": f"fc-{call.call_id}",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "status": "completed",
                }
                for call in response.tool_calls
            )
            return httpx.Response(200, json=response_body(output))

        config = ModelConfig(
            model="test-model",
            api_key="unit-test-placeholder",
            base_url="https://model.example.invalid/v1",
            max_output_tokens=8192,
            reasoning_effort="high",
            max_run_seconds=300,
        )
        with ResponsesClient.from_config(
            config,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        ) as client:
            report = run_script(
                brief(duration_seconds=10),
                client=client,
                config=config,
                catalog=loaded,
                mode="live",
            )
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(requests), 5)
        self.assertTrue(
            all(item["reasoning"] == {"effort": "high"} for item in requests)
        )
        self.assertTrue(all(item["max_output_tokens"] == 8192 for item in requests))
        self.assertTrue(
            all(
                item["text"] == {"format": {"type": "json_object"}} for item in requests
            )
        )
        self.assertEqual(
            report["model_settings"],
            {
                **config.public_settings(),
                "output_format": "json_object",
            },
        )
        self.assertTrue(
            {"search_materials", "estimate_duration", "check_rules"}
            <= {tool["name"] for tool in requests[0]["tools"]}
        )
        self.assertLess(report["script"]["estimated_total_seconds"], 10)
