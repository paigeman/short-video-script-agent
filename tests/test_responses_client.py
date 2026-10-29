import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import httpx

from src.agent.runner import AgentRunner
from src.llm.responses import ResponsesClient, to_responses_item
from src.llm.types import Message, ModelCallError, ModelRequest, ProviderItem
from src.tools.protocol import ToolCallRequest, ToolCallResult
from tests.helpers import echo_registry


def response_body(output, status="completed", usage=None):
    return {
        "id": "resp-test",
        "object": "response",
        "created_at": 0,
        "model": "test-model",
        "status": status,
        "output": output,
        "usage": usage,
        "parallel_tool_calls": True,
        "tools": [],
        "tool_choice": "auto",
    }


def text_item(text="Done"):
    return {
        "id": "msg-test",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


class ResponsesClientTests(unittest.TestCase):
    def make_client(self, handler):
        transport_client = httpx.Client(transport=httpx.MockTransport(handler))
        client = ResponsesClient(
            model="test-model",
            api_key="unit-test-placeholder",
            base_url="https://model.example.invalid/v1",
            http_client=transport_client,
            timeout_seconds=2,
        )
        self.addCleanup(client.close)
        return client

    def test_real_sdk_loop_preserves_output_order_and_matching_results(self):
        requests = []
        original_output = [
            {
                "type": "reasoning",
                "id": "rs-test",
                "summary": [],
                "encrypted_content": "opaque-test-context",
            },
            text_item("Read both values."),
            {
                "type": "function_call",
                "id": "fc-1",
                "call_id": "c1",
                "name": "echo",
                "arguments": '{"value":1}',
                "status": "completed",
            },
            {
                "type": "function_call",
                "id": "fc-2",
                "call_id": "c2",
                "name": "echo",
                "arguments": '{"value":2}',
                "status": "completed",
            },
        ]

        def handle(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 1:
                return httpx.Response(200, json=response_body(original_output))
            return httpx.Response(
                200,
                json=response_body(
                    [text_item("Verified both values.")],
                    usage={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
                ),
            )

        client = self.make_client(handle)
        calls = []
        result = AgentRunner(client, echo_registry(calls)).run(
            ModelRequest([Message("user", "Read values")], max_output_tokens=128)
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, [{"value": 1}, {"value": 2}])
        self.assertEqual(requests[1]["input"][1:5], original_output)
        results = requests[1]["input"][5:]
        self.assertEqual([item["call_id"] for item in results], ["c1", "c2"])
        self.assertTrue(all(item["type"] == "function_call_output" for item in results))
        self.assertEqual(requests[0]["max_output_tokens"], 128)
        self.assertFalse(requests[0]["store"])
        self.assertIn("reasoning.encrypted_content", requests[0]["include"])
        self.assertFalse(requests[0]["tools"][0]["strict"])
        self.assertEqual(requests[0]["tools"][0]["parameters"]["required"], ["value"])
        model_events = [event for event in result.trace if event["event"] == "model"]
        self.assertIsNone(model_events[0]["usage"])
        self.assertEqual(model_events[1]["usage"]["total_tokens"], 13)
        self.assertNotIn("opaque-test-context", json.dumps(result.to_dict()))

    def test_transport_errors_are_sanitized_and_not_retried(self):
        for status in (401, 429, 503):
            with self.subTest(status=status):
                attempts = []

                def handle(request, attempts=attempts, status=status):
                    attempts.append(request)
                    return httpx.Response(
                        status,
                        json={
                            "error": {
                                "message": "synthetic-sensitive-response",
                                "type": "test_error",
                            }
                        },
                    )

                client = self.make_client(handle)
                with self.assertRaises(ModelCallError) as caught:
                    client.send(ModelRequest([Message("user", "test")]))
                self.assertEqual(caught.exception.code, f"http_{status}")
                self.assertNotIn("synthetic-sensitive-response", str(caught.exception))
                self.assertEqual(len(attempts), 1)

    def test_timeouts_and_connection_failures(self):
        for error, code in [
            (httpx.ReadTimeout, "model_timeout"),
            (httpx.ConnectError, "connection_failed"),
        ]:
            with self.subTest(code=code):

                def handle(request, error=error):
                    raise error("synthetic transport error", request=request)

                client = self.make_client(handle)
                with self.assertRaises(ModelCallError) as caught:
                    client.send(ModelRequest([Message("user", "test")]))
                self.assertEqual(caught.exception.code, code)

    def test_noncompleted_responses_keep_their_status(self):
        for status in ("incomplete", "failed", "cancelled", "queued"):
            with self.subTest(status=status):
                client = self.make_client(
                    lambda request, status=status: httpx.Response(
                        200, json=response_body([], status=status)
                    )
                )
                response = client.send(ModelRequest([Message("user", "test")]))
                self.assertNotEqual(response.reason, "completed")
                self.assertIsNone(response.usage)

    def test_refusal_is_not_a_successful_answer(self):
        item = text_item()
        item["content"] = [{"type": "refusal", "refusal": "Cannot fulfill request"}]
        client = self.make_client(
            lambda request: httpx.Response(200, json=response_body([item]))
        )
        self.assertEqual(
            client.send(ModelRequest([Message("user", "test")])).reason, "model_refused"
        )

    def test_mapping_preserves_input_and_checks_provider(self):
        payload = {"type": "reasoning", "summary": []}
        original = deepcopy(payload)
        mapped = to_responses_item(ProviderItem("responses", payload))
        mapped["summary"].append({"text": "changed"})
        self.assertEqual(payload, original)
        self.assertEqual(
            to_responses_item(ToolCallRequest("c1", "echo", "{}"))["type"],
            "function_call",
        )
        self.assertEqual(to_responses_item(ToolCallResult("c1", "{}"))["call_id"], "c1")
        with self.assertRaises(TypeError):
            to_responses_item(ProviderItem("another-provider", {}))

    def test_invalid_configuration_and_close(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ResponsesClient(
                    "test-model", "unit-test-placeholder", timeout_seconds=value
                )
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            ResponsesClient.from_env()
        client = self.make_client(
            lambda request: httpx.Response(200, json=response_body([text_item()]))
        )
        with client:
            self.assertFalse(client._client.is_closed())
        self.assertTrue(client._client.is_closed())
