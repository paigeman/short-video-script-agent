import json
import unittest
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx

from src.agent.runner import AgentRunner
from src.llm.responses import ResponsesClient, _retry_after
from src.llm.types import Message, ModelCallError, ModelRequest
from src.tools.registry import ToolRegistry
from tests.test_responses_client import response_body, text_item
from tests.test_runtime_capabilities import FakeControl


class ModelResilienceTests(unittest.TestCase):
    def make_client(self, handler):
        client = ResponsesClient(
            "test-model",
            "unit-test-placeholder",
            timeout_seconds=5,
            base_url="https://model.example.invalid/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        return client

    def test_error_classification_distinguishes_quota_from_rate_limits(self):
        cases = [
            (401, None, None, False),
            (400, None, None, False),
            (429, "rate_limit_exceeded", "rate_limit_error", True),
            (503, "server_is_overloaded", None, True),
            (408, None, None, True),
            (409, None, None, True),
            (501, None, None, False),
            (429, "insufficient_quota", None, False),
            (429, "project_spend_limit_exceeded", "insufficient_quota", False),
            (429, "organization_usage_limit_exceeded", None, False),
            (429, "unknown_quota", "insufficient_quota", False),
            (503, {"malformed": "error code"}, None, False),
        ]
        for status, code, kind, expected in cases:
            with self.subTest(status=status, code=code):

                def handle(request, status=status, code=code, kind=kind):
                    return httpx.Response(
                        status,
                        json={
                            "error": {
                                "code": code,
                                "type": kind,
                                "message": "synthetic-private-error",
                            }
                        },
                        headers={"retry-after": "2"},
                    )

                client = self.make_client(handle)
                with self.assertRaises(ModelCallError) as caught:
                    client.send(ModelRequest([Message("user", "test")]))
                self.assertEqual(caught.exception.retryable, expected)
                self.assertEqual(caught.exception.retry_after, 2)
                self.assertNotIn("synthetic-private-error", str(caught.exception))

    def test_server_no_retry_header_is_honored(self):
        client = self.make_client(
            lambda req: httpx.Response(
                503, json={"error": {}}, headers={"x-should-retry": "false"}
            )
        )
        with self.assertRaises(ModelCallError) as caught:
            client.send(ModelRequest([Message("user", "test")]))
        self.assertFalse(caught.exception.retryable)

    def test_retry_after_supports_numeric_date_and_milliseconds(self):
        cases = [
            ({"retry-after": "3"}, 3),
            ({"retry-after-ms": "1500"}, 1.5),
            ({"retry-after": "nan"}, None),
            ({"retry-after": "nonsense"}, None),
            ({"retry-after": "-2"}, 0),
            ({"retry-after-ms": "bad", "retry-after": "2"}, 2),
        ]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                self.assertEqual(_retry_after(httpx.Headers(headers)), expected)
        date = format_datetime(datetime.now(UTC) + timedelta(seconds=60), usegmt=True)
        delay = _retry_after(httpx.Headers({"retry-after": date}))
        self.assertGreater(delay, 58)
        self.assertLessEqual(delay, 60)

    def test_request_timeout_never_extends_client_timeout(self):
        observed = []

        def handle(request):
            observed.append(request.extensions["timeout"])
            return httpx.Response(200, json=response_body([text_item()]))

        client = self.make_client(handle)
        for timeout in (1, 30):
            client.send(
                ModelRequest([Message("user", "test")], timeout_seconds=timeout)
            )
        self.assertTrue(all(value == 1 for value in observed[0].values()))
        self.assertTrue(all(value == 5 for value in observed[1].values()))
        for timeout in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                client.send(
                    ModelRequest([Message("user", "test")], timeout_seconds=timeout)
                )

    def test_malformed_success_payloads_become_safe_protocol_errors(self):
        cases = [
            {},
            {"output": None},
            response_body([{"type": "function_call"}]),
            response_body([{"type": "message", "content": None}]),
            response_body(
                [{"type": "message", "content": [{"type": "output_text", "text": 4}]}]
            ),
            response_body(
                [], usage={"input_tokens": -1, "output_tokens": 2, "total_tokens": 1}
            ),
            response_body([{"type": "unknown_item"}]),
        ]
        for body in cases:
            with self.subTest(body=body):
                client = self.make_client(
                    lambda request, body=body: httpx.Response(200, json=body)
                )
                result = AgentRunner(client, ToolRegistry([])).run(
                    ModelRequest([Message("user", "test")])
                )
                self.assertEqual(result.status, "model_error")
                self.assertIn(
                    result.reason, {"invalid_response", "unsupported_output_item"}
                )
                self.assertEqual(result.model_requests, 1)

    def test_non_json_success_payload_is_a_protocol_error(self):
        client = self.make_client(
            lambda request: httpx.Response(200, text="synthetic-private-error")
        )
        with self.assertRaises(ModelCallError) as caught:
            client.send(ModelRequest([Message("user", "test")]))
        self.assertEqual(caught.exception.code, "invalid_response")
        self.assertNotIn("synthetic-private-error", str(caught.exception))

    def test_real_sdk_retry_and_pause_resume_keep_matching_call_results(self):
        requests = []

        def handle(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 1:
                return httpx.Response(
                    503,
                    json={"error": {"code": "server_is_overloaded"}},
                    headers={"retry-after": "1"},
                )
            if len(requests) == 2:
                return httpx.Response(
                    200,
                    json=response_body(
                        [
                            {
                                "type": "function_call",
                                "id": "fc-test",
                                "call_id": "q1",
                                "name": "ask_user",
                                "arguments": '{"question":"Which value?"}',
                                "status": "completed",
                            }
                        ]
                    ),
                )
            return httpx.Response(200, json=response_body([text_item('{"value":3}')]))

        runner = AgentRunner(self.make_client(handle), ToolRegistry([]))
        control = FakeControl()
        paused = runner.run(
            ModelRequest([Message("user", "test")]),
            output_schema={"type": "object", "required": ["value"]},
            control=control,
        )
        self.assertEqual(paused.status, "needs_input")
        final = runner.resume(paused.checkpoint, "Three", control=control)
        self.assertEqual(
            (final.status, final.data, final.model_requests),
            ("completed", {"value": 3}, 3),
        )
        self.assertEqual(control.waits, [1])
        self.assertEqual(requests[0]["input"], requests[1]["input"])
        answer = requests[2]["input"][-1]
        self.assertEqual(
            (answer["type"], answer["call_id"]), ("function_call_output", "q1")
        )
        self.assertEqual(json.loads(answer["output"]), {"answer": "Three"})
        self.assertEqual(final.model, "test-model")
