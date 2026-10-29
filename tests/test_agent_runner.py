import json
import unittest
from copy import deepcopy

from src.agent.runner import AgentRunner
from src.llm.types import (
    Message,
    ModelCallError,
    ModelRequest,
    ModelResponse,
    ProviderItem,
)
from src.tools.limits import ToolLoopLimits
from src.tools.protocol import ToolCallRequest, ToolCallResult
from tests.helpers import ScriptedModel, echo_registry


def call_response(call_id="c1", arguments='{"value":1}', name="echo"):
    return ModelResponse(tool_calls=[ToolCallRequest(call_id, name, arguments)])


class AgentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.registry = echo_registry(self.calls)
        self.request = ModelRequest([Message("user", "Use a tool when needed.")])

    def test_model_result_is_observed_and_changes_the_next_action(self):
        test = self

        class ObservingModel:
            def send(self, request):
                results = [
                    item for item in request.input if isinstance(item, ToolCallResult)
                ]
                if not results:
                    return call_response(arguments='{"value":"wrong"}')
                observed = json.loads(results[-1].output)
                if "error" in observed:
                    test.assertEqual(observed["error"]["category"], "invalid_arguments")
                    return call_response("c2", '{"value":2}')
                return ModelResponse(text=f"Observed {observed['value']}")

        result = AgentRunner(ObservingModel(), self.registry).run(self.request)
        self.assertEqual((result.status, result.text), ("completed", "Observed 2"))
        self.assertEqual(self.calls, [{"value": 2}])
        self.assertEqual(
            (result.model_requests, result.tool_rounds, result.tool_executions),
            (3, 2, 1),
        )
        self.assertEqual(
            [event["event"] for event in result.trace],
            ["model", "tool", "model", "tool", "model", "stop"],
        )

    def test_batch_calls_precede_all_results_without_mutating_the_input(self):
        first = call_response()
        first.tool_calls.append(ToolCallRequest("c2", "echo", '{"value":2}'))
        model = ScriptedModel([first, ModelResponse(text="Done")])
        original = deepcopy(self.request)
        result = AgentRunner(model, self.registry).run(self.request)
        followup = model.requests[1].input
        self.assertEqual(
            [type(item) for item in followup],
            [Message, ToolCallRequest, ToolCallRequest, ToolCallResult, ToolCallResult],
        )
        self.assertEqual(
            [item.call_id for item in followup[1:]], ["c1", "c2", "c1", "c2"]
        )
        self.assertEqual(self.request, original)
        self.assertEqual(result.tool_executions, 2)

    def test_round_and_request_caps_stop_before_extra_execution(self):
        cases = [
            (ToolLoopLimits(max_tool_rounds=1), "max_tool_rounds_reached", 1, 2),
            (ToolLoopLimits(max_model_requests=1), "max_model_requests_reached", 0, 1),
        ]
        for limits, reason, executions, requests in cases:
            with self.subTest(reason=reason):
                calls = []
                model = ScriptedModel([call_response(), call_response("c2")])
                result = AgentRunner(model, echo_registry(calls), limits).run(
                    self.request
                )
                self.assertEqual((result.status, result.reason), ("incomplete", reason))
                self.assertEqual(len(calls), executions)
                self.assertEqual(len(model.requests), requests)

    def test_execution_cap_preserves_partial_batch_results(self):
        response = call_response()
        response.tool_calls.append(ToolCallRequest("c2", "echo", '{"value":2}'))
        model = ScriptedModel([response])
        result = AgentRunner(
            model, self.registry, ToolLoopLimits(max_tool_executions=1)
        ).run(self.request)
        self.assertEqual(result.reason, "max_tool_executions_reached")
        self.assertEqual(self.calls, [{"value": 1}])
        self.assertEqual(result.tool_executions, 1)
        self.assertEqual(
            len([event for event in result.trace if event["event"] == "tool"]), 1
        )

    def test_incomplete_response_does_not_execute_pending_calls(self):
        response = call_response()
        response.reason = "model_incomplete"
        response.text = "Partial"
        result = AgentRunner(ScriptedModel([response]), self.registry).run(self.request)
        self.assertEqual(
            (result.status, result.reason, result.text),
            ("incomplete", "model_incomplete", "Partial"),
        )
        self.assertEqual(self.calls, [])

    def test_error_results_are_returned_to_the_model(self):
        model = ScriptedModel(
            [call_response(name="unknown"), ModelResponse(text="Cannot use this tool")]
        )
        result = AgentRunner(model, self.registry).run(self.request)
        tool_result = model.requests[1].input[-1]
        self.assertEqual(
            json.loads(tool_result.output)["error"]["category"], "unknown_tool"
        )
        self.assertEqual(result.tool_executions, 0)
        self.assertEqual(self.calls, [])

    def test_provider_context_is_forwarded_but_not_exported_in_trace(self):
        response = call_response()
        response.continuation = [
            ProviderItem(
                "responses",
                {"type": "reasoning", "encrypted_content": "opaque-test-data"},
            )
        ]
        model = ScriptedModel([response, ModelResponse(text="Done")])
        result = AgentRunner(model, self.registry).run(self.request)
        self.assertEqual(model.requests[1].input[1], response.continuation[0])
        self.assertNotIn("opaque-test-data", json.dumps(result.to_dict()))

    def test_duplicate_ids_are_rejected_before_execution(self):
        response = call_response()
        response.tool_calls.append(ToolCallRequest("c1", "echo", '{"value":2}'))
        result = AgentRunner(ScriptedModel([response]), self.registry).run(self.request)
        self.assertEqual(result.reason, "invalid_call_ids")
        self.assertEqual(self.calls, [])

    def test_repeated_ids_do_not_reexecute_a_tool(self):
        result = AgentRunner(
            ScriptedModel([call_response(), call_response()]), self.registry
        ).run(self.request)
        self.assertEqual(result.reason, "invalid_call_ids")
        self.assertEqual(len(self.calls), 1)

    def test_empty_answers_are_not_reported_as_complete(self):
        result = AgentRunner(
            ScriptedModel([ModelResponse(text=" ")]), self.registry
        ).run(self.request)
        self.assertEqual(
            (result.status, result.reason), ("incomplete", "empty_response")
        )

    def test_transport_failure_has_an_explicit_state(self):
        class FailedModel:
            def send(self, request):
                raise ModelCallError("model_timeout")

        result = AgentRunner(FailedModel(), self.registry).run(self.request)
        self.assertEqual(
            (result.status, result.reason), ("model_error", "model_timeout")
        )
        self.assertEqual(result.model_requests, 1)
        self.assertEqual(self.calls, [])

    def test_limits_reset_between_runs(self):
        model = ScriptedModel(
            [
                call_response(),
                ModelResponse(text="Done"),
                call_response(),
                ModelResponse(text="Done"),
            ]
        )
        runner = AgentRunner(
            model, self.registry, ToolLoopLimits(max_tool_executions=1)
        )
        for _ in range(2):
            self.assertEqual(runner.run(self.request).tool_executions, 1)
        self.assertEqual(len(self.calls), 2)

    def test_invalid_limits_and_requests_are_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ToolLoopLimits(max_model_requests=value)
        runner = AgentRunner(ScriptedModel([]), self.registry)
        with self.assertRaises(ValueError):
            runner.run(ModelRequest([]))
        with self.assertRaises(ValueError):
            runner.run(ModelRequest([Message("user", "test")], max_output_tokens=True))
