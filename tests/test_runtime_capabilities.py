import json
import unittest
from copy import deepcopy

from jsonschema.exceptions import SchemaError

from src.agent.control import RunControl, RuntimePolicy
from src.agent.runner import AgentRunner
from src.llm.types import (
    Message,
    ModelCallError,
    ModelRequest,
    ModelResponse,
    ProviderItem,
)
from src.tools.definition import RegisteredTool, ToolDefinition
from src.tools.limits import ToolLoopLimits
from src.tools.protocol import ToolCallRequest, ToolCallResult
from src.tools.registry import ToolRegistry
from tests.helpers import ScriptedModel, echo_registry


def call(name="echo", call_id="c1", arguments='{"value":1}'):
    return ToolCallRequest(call_id, name, arguments)


def question(call_id="q1"):
    return call("ask_user", call_id, '{"question":"Which value should I use?"}')


class FakeControl(RunControl):
    def __init__(self):
        super().__init__()
        self.now = 0.0
        self.waits = []

    def clock(self):
        return self.now

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class SequenceModel(ScriptedModel):
    def send(self, request):
        response = super().send(request)
        if isinstance(response, Exception):
            raise response
        return response


class RuntimeCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.request = ModelRequest([Message("user", "Run the synthetic task")])
        self.schema = {
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"type": "integer"}},
        }
        self.calls = []
        self.registry = echo_registry(self.calls)
        self.control = FakeControl()

    def runner(self, responses, **kwargs):
        self.model = SequenceModel(responses)
        return AgentRunner(self.model, self.registry, **kwargs)

    def test_structured_repairs_preserve_context_and_validate_before_completion(self):
        opaque = ProviderItem(
            "responses", {"type": "reasoning", "encrypted_content": "opaque"}
        )
        runner = self.runner(
            [
                ModelResponse(text="not JSON", continuation=[opaque]),
                ModelResponse(text='{"value":"wrong"}'),
                ModelResponse(text='{"value":2}'),
            ],
            policy=RuntimePolicy(max_output_repairs=2),
        )
        original = deepcopy(self.request)
        result = runner.run(self.request, output_schema=self.schema)
        self.assertEqual(
            (result.status, result.data, result.output_repairs),
            ("completed", {"value": 2}, 2),
        )
        self.assertIn(opaque, self.model.requests[1].input)
        self.assertEqual(self.request, original)
        self.assertEqual(result.model_requests, 3)
        self.assertEqual(
            [
                e["category"]
                for e in result.trace
                if e["event"] == "output_validation_error"
            ],
            ["parse_error", "schema_validation_error"],
        )
        self.assertNotIn("opaque", json.dumps(result.to_dict()))

    def test_invalid_output_stops_after_repair_budget(self):
        runner = self.runner(
            [ModelResponse(text="bad"), ModelResponse(text="still bad")]
        )
        result = runner.run(self.request, output_schema=self.schema)
        self.assertEqual(
            (result.status, result.reason), ("incomplete", "invalid_output")
        )
        self.assertEqual(result.model_requests, 2)
        self.assertIsNone(result.data)

    def test_repairs_share_the_model_request_budget(self):
        runner = self.runner(
            [ModelResponse(text="bad")], limits=ToolLoopLimits(max_model_requests=1)
        )
        result = runner.run(self.request, output_schema=self.schema)
        self.assertEqual(result.reason, "max_model_requests_reached")
        self.assertEqual(len(self.model.requests), 1)

    def test_refusal_never_triggers_output_repair(self):
        result = self.runner([ModelResponse(reason="model_refused")]).run(
            self.request, output_schema=self.schema
        )
        self.assertEqual(result.reason, "model_refused")
        self.assertEqual(result.output_repairs, 0)

    def test_bad_schema_fails_before_calling_model(self):
        runner = self.runner([])
        with self.assertRaises(SchemaError):
            runner.run(self.request, output_schema={"type": "invalid"})
        self.assertEqual(self.model.requests, [])

    def test_clarification_resumes_the_same_batch_without_repeating_tools(self):
        runner = self.runner(
            [
                ModelResponse(tool_calls=[call(), question(), call(call_id="c2")]),
                ModelResponse(text='{"value":3}'),
            ]
        )
        paused = runner.run(self.request, output_schema=self.schema)
        self.assertEqual((paused.status, paused.tool_executions), ("needs_input", 1))
        self.assertEqual(len(self.model.requests), 1)
        self.assertIsNotNone(paused.checkpoint)
        self.assertNotIn("checkpoint", paused.to_dict())
        result = runner.resume(paused.checkpoint, "Use three")
        self.assertEqual(
            (result.status, result.tool_executions, result.model_requests),
            ("completed", 2, 2),
        )
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result.run_id, paused.run_id)
        self.assertEqual(paused.status, "needs_input")
        results = [
            i for i in self.model.requests[1].input if isinstance(i, ToolCallResult)
        ]
        self.assertEqual([i.call_id for i in results], ["c1", "q1", "c2"])
        self.assertEqual(json.loads(results[1].output), {"answer": "Use three"})
        with self.assertRaises(ValueError):
            runner.resume(paused.checkpoint, "Again")

    def test_multiple_questions_pause_and_resume_in_order(self):
        runner = self.runner(
            [
                ModelResponse(tool_calls=[question(), question("q2")]),
                ModelResponse(text="Done"),
            ]
        )
        first = runner.run(self.request)
        second = runner.resume(first.checkpoint, "First answer")
        self.assertEqual((second.status, second.model_requests), ("needs_input", 1))
        final = runner.resume(second.checkpoint, "Second answer")
        self.assertEqual(final.status, "completed")
        self.assertEqual(final.tool_rounds, 1)
        self.assertEqual(final.tool_executions, 0)

    def test_resume_preserves_execution_budget(self):
        runner = self.runner(
            [ModelResponse(tool_calls=[call(), question(), call(call_id="c2")])],
            limits=ToolLoopLimits(max_tool_executions=1),
        )
        paused = runner.run(self.request)
        result = runner.resume(paused.checkpoint, "Continue")
        self.assertEqual(result.reason, "max_tool_executions_reached")
        self.assertEqual(len(self.calls), 1)

    def test_foreign_and_invalid_answers_do_not_consume_checkpoint(self):
        runner = self.runner(
            [ModelResponse(tool_calls=[question()]), ModelResponse(text="Done")]
        )
        paused = runner.run(self.request)
        foreign = AgentRunner(SequenceModel([]), self.registry)
        for operation in (
            lambda: foreign.resume(paused.checkpoint, "Answer"),
            lambda: runner.resume(paused.checkpoint, " "),
            lambda: runner.resume(paused.checkpoint, "x" * 32_000),
        ):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(runner.resume(paused.checkpoint, "Answer").status, "completed")

    def test_invalid_question_is_returned_as_tool_error(self):
        for arguments in ("{}", '{"question":" "}', '{"question":"x","extra":1}'):
            with self.subTest(arguments=arguments):
                runner = self.runner(
                    [
                        ModelResponse(
                            tool_calls=[call("ask_user", arguments=arguments)]
                        ),
                        ModelResponse(text="Done"),
                    ]
                )
                result = runner.run(self.request)
                self.assertEqual(result.status, "completed")
                self.assertEqual(
                    json.loads(self.model.requests[1].input[-1].output)["error"][
                        "category"
                    ],
                    "invalid_arguments",
                )

    def test_clarification_can_be_disabled_and_name_is_reserved(self):
        definition = ToolDefinition("ask_user", "test", {"type": "object"})
        registry = ToolRegistry([RegisteredTool(definition, lambda args: {})])
        with self.assertRaises(ValueError):
            AgentRunner(SequenceModel([]), registry)
        runner = self.runner([ModelResponse(text="Done")], allow_clarification=False)
        runner.run(self.request)
        self.assertNotIn("ask_user", [t.name for t in self.model.requests[0].tools])

    def test_waiting_for_user_does_not_consume_active_time_budget(self):
        control = self.control

        class TimedModel:
            count = 0

            def send(self, request):
                control.now += 1
                self.count += 1
                return (
                    ModelResponse(tool_calls=[question()])
                    if self.count == 1
                    else ModelResponse(text="Done")
                )

        runner = AgentRunner(
            TimedModel(), self.registry, policy=RuntimePolicy(max_run_seconds=3)
        )
        paused = runner.run(self.request, control=control)
        control.now += 1000
        result = runner.resume(paused.checkpoint, "Answer", control=control)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.elapsed_seconds, 2)

    def test_cancellation_before_model_request(self):
        self.control.cancel()
        result = self.runner([]).run(self.request, control=self.control)
        self.assertEqual((result.status, result.model_requests), ("cancelled", 0))

    def test_late_model_response_is_not_accepted_after_deadline(self):
        control = self.control

        class SlowModel:
            def send(self, request):
                self.timeout = request.timeout_seconds
                control.now += 3
                return ModelResponse(text="Too late")

        model = SlowModel()
        result = AgentRunner(
            model, self.registry, policy=RuntimePolicy(max_run_seconds=2)
        ).run(self.request, control=control)
        self.assertEqual(result.reason, "run_timeout")
        self.assertEqual(model.timeout, 2)
        self.assertEqual(result.elapsed_seconds, 3)

    def test_cancellation_and_deadline_between_tools_prevent_next_execution(self):
        for reason in ("cancelled", "run_timeout"):
            with self.subTest(reason=reason):
                control = FakeControl()
                executed = []

                def handler(args, executed=executed, reason=reason, control=control):
                    executed.append(args)
                    if reason == "cancelled":
                        control.cancel()
                    else:
                        control.now += 3
                    return {"value": 1}

                runner = AgentRunner(
                    SequenceModel(
                        [ModelResponse(tool_calls=[call(), call(call_id="c2")])]
                    ),
                    echo_registry([], handler),
                    policy=RuntimePolicy(max_run_seconds=2),
                )
                result = runner.run(self.request, control=control)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.tool_executions, 1)
                self.assertEqual(len(executed), 1)
                self.assertEqual(
                    len([e for e in result.trace if e["event"] == "tool"]), 1
                )

    def test_cancelled_model_response_does_not_execute_tools(self):
        control = self.control

        class CancelModel:
            def send(self, request):
                control.cancel()
                return ModelResponse(tool_calls=[call()])

        result = AgentRunner(CancelModel(), self.registry).run(
            self.request, control=control
        )
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(self.calls, [])

    def test_transient_retry_does_not_repeat_executed_tools(self):
        runner = self.runner(
            [
                ModelResponse(tool_calls=[call()]),
                ModelCallError("http_503", retryable=True, retry_after=1),
                ModelResponse(text="Done"),
            ]
        )
        result = runner.run(self.request, control=self.control)
        self.assertEqual(
            (result.status, result.model_retries, result.model_requests),
            ("completed", 1, 3),
        )
        self.assertEqual(self.control.waits, [1])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.model.requests[1].input, self.model.requests[2].input)
        self.assertFalse(result.usage_complete)

    def test_retry_and_request_limits_are_independent(self):
        for limits, policy, requests, reason in (
            (ToolLoopLimits(), RuntimePolicy(max_model_retries=1), 2, "http_503"),
            (
                ToolLoopLimits(max_model_requests=1),
                RuntimePolicy(),
                1,
                "max_model_requests_reached",
            ),
        ):
            with self.subTest(reason=reason):
                runner = self.runner(
                    [ModelCallError("http_503", retryable=True)] * 4,
                    limits=limits,
                    policy=policy,
                )
                result = runner.run(self.request, control=self.control)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.model_requests, requests)

    def test_permanent_errors_never_retry(self):
        result = self.runner([ModelCallError("http_401")]).run(
            self.request, control=self.control
        )
        self.assertEqual(result.status, "model_error")
        self.assertEqual(result.model_requests, 1)
        self.assertEqual(self.control.waits, [])

    def test_server_retry_delay_is_not_shortened_to_fit_budget(self):
        for delay in (121, 31):
            with self.subTest(delay=delay):
                result = self.runner(
                    [ModelCallError("http_429", retryable=True, retry_after=delay)]
                ).run(self.request, control=self.control)
                self.assertEqual(result.reason, "retry_delay_exceeds_budget")
                self.assertEqual(self.control.waits, [])

    def test_cancellation_during_retry_wait(self):
        class CancelWait(FakeControl):
            def wait(self, seconds):
                self.cancel()

        result = self.runner([ModelCallError("http_503", retryable=True)]).run(
            self.request, control=CancelWait()
        )
        self.assertEqual((result.status, result.model_requests), ("cancelled", 1))

    def test_initial_context_limit_stops_before_model_request(self):
        result = self.runner([], policy=RuntimePolicy(max_context_bytes=10)).run(
            self.request
        )
        self.assertEqual(
            (result.reason, result.model_requests), ("max_context_bytes_reached", 0)
        )

    def test_context_limit_keeps_protocol_items_intact_and_stops_before_tools(self):
        response = ModelResponse(
            tool_calls=[call()],
            continuation=[ProviderItem("responses", {"payload": "x" * 3000})],
        )
        result = self.runner(
            [response], policy=RuntimePolicy(max_context_bytes=2000)
        ).run(self.request)
        self.assertEqual(result.reason, "max_context_bytes_reached")
        self.assertEqual(self.calls, [])

    def test_oversized_tool_output_is_explicit_error_not_silent_truncation(self):
        model = SequenceModel(
            [ModelResponse(tool_calls=[call()]), ModelResponse(text="Done")]
        )
        runner = AgentRunner(
            model,
            echo_registry([], lambda args: {"value": "界" * 1000}),
            policy=RuntimePolicy(max_tool_output_bytes=200),
        )
        result = runner.run(self.request)
        output = json.loads(model.requests[1].input[-1].output)
        self.assertEqual(output["error"]["category"], "output_too_large")
        self.assertEqual(result.tool_executions, 1)
        self.assertGreater(
            next(e for e in result.trace if e["event"] == "tool")["output_bytes"], 200
        )

    def test_usage_accumulates_and_missing_usage_remains_explicit(self):
        usage = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}
        for first in (usage, None):
            with self.subTest(first=first):
                result = self.runner(
                    [
                        ModelResponse(tool_calls=[call()], usage=first),
                        ModelResponse(text="Done", usage=usage),
                    ]
                ).run(self.request)
                self.assertEqual(result.usage["total_tokens"], 14 if first else 7)
                self.assertEqual(result.usage_complete, first is not None)
        self.assertIsNone(
            self.runner([ModelResponse(text="Done")]).run(self.request).usage
        )

    def test_invalid_policy_values_are_rejected(self):
        for kwargs in (
            {"max_model_retries": -1},
            {"max_output_repairs": True},
            {"max_context_bytes": 0},
            {"max_run_seconds": float("inf")},
            {"retry_base_seconds": -1},
            {"max_retry_delay_seconds": 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RuntimePolicy(**kwargs)
