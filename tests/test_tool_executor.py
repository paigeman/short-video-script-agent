import json
import unittest

from src.tools.definition import (
    RegisteredTool,
    ToolArguments,
    ToolDefinition,
    ToolOutput,
)
from src.tools.errors import (
    InvalidToolArgumentsError,
    ToolExecutionErrorCategory,
    ToolLoopStoppedError,
    ToolLoopStopReason,
)
from src.tools.executor import ToolExecutor
from src.tools.limits import ToolExecutionBudget
from src.tools.protocol import ToolCallRequest, ToolCallResult
from src.tools.registry import ToolRegistry


class RecordingHandler:
    def __init__(
        self,
        output: ToolOutput | None = None,
        error: Exception | None = None,
    ):
        self.output = output if output is not None else {"status": "ok"}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(self, arguments: ToolArguments) -> ToolOutput:
        self.calls.append(dict(arguments))
        if self.error is not None:
            raise self.error
        return self.output


def make_executor(handler: RecordingHandler) -> ToolExecutor:
    tool = RegisteredTool(
        definition=ToolDefinition(
            name="example_tool",
            description="Execute an example tool for tests.",
            parameter_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["value"],
                "properties": {
                    "value": {"type": "integer"},
                },
            },
        ),
        handler=handler,
    )
    return ToolExecutor(ToolRegistry([tool]))


class ToolExecutorTests(unittest.TestCase):
    def test_nonserializable_outputs_become_tool_errors(self):
        for output in ({"value": {1}}, {"value": float("nan")}, [1]):
            with self.subTest(output=output):
                handler = RecordingHandler(output=output)
                executor = make_executor(handler)
                result = executor.execute_call(
                    ToolCallRequest("call-1", "example_tool", '{"value":1}')
                )
                self.assertEqual(
                    json.loads(result.output)["error"]["category"], "execution_failed"
                )
                self.assertEqual(len(handler.calls), 1)

    def test_duplicate_keys_and_nonfinite_arguments_are_rejected(self):
        for arguments in (
            '{"value":1,"value":2}',
            '{"value":NaN}',
            '{"value":Infinity}',
            '{"value":1e999}',
        ):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()
                executor = make_executor(handler)
                result = executor.execute_call(
                    ToolCallRequest("call-1", "example_tool", arguments)
                )
                self.assertEqual(
                    json.loads(result.output)["error"]["category"], "invalid_arguments"
                )
                self.assertEqual(handler.calls, [])

    def test_valid_arguments_execute_handler_once_and_return_output(self):
        expected_output = {"doubled": 42}
        handler = RecordingHandler(output=expected_output)
        executor = make_executor(handler)

        result = executor.execute("example_tool", {"value": 21})

        self.assertEqual(result.output, expected_output)
        self.assertIsNone(result.error)
        self.assertEqual(handler.calls, [{"value": 21}])

    def test_invalid_arguments_are_rejected_before_handler_execution(self):
        invalid_arguments = {
            "missing required field": {},
            "wrong field type": {"value": "21"},
            "additional field": {"value": 21, "unexpected": True},
        }

        for name, arguments in invalid_arguments.items():
            with self.subTest(name=name):
                handler = RecordingHandler()
                executor = make_executor(handler)

                result = executor.execute("example_tool", arguments)

                self.assertIsNone(result.output)
                self.assertIsNotNone(result.error)
                self.assertEqual(
                    result.error.category,
                    ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                )
                self.assertEqual(handler.calls, [])

    def test_unknown_tool_is_rejected_without_executing_registered_handler(self):
        handler = RecordingHandler()
        executor = make_executor(handler)

        result = executor.execute("missing_tool", {"value": 21})

        self.assertIsNone(result.output)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error.category,
            ToolExecutionErrorCategory.UNKNOWN_TOOL,
        )
        self.assertEqual(handler.calls, [])

    def test_unexpected_handler_error_returns_safe_execution_failure(self):
        sensitive_detail = "internal path: /private/service/config.json"
        handler = RecordingHandler(error=RuntimeError(sensitive_detail))
        executor = make_executor(handler)

        result = executor.execute("example_tool", {"value": 21})

        self.assertIsNone(result.output)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error.category,
            ToolExecutionErrorCategory.EXECUTION_FAILED,
        )
        self.assertNotIn(sensitive_detail, result.error.message)
        self.assertEqual(handler.calls, [{"value": 21}])


class ToolCallExecutionTests(unittest.TestCase):
    def decode_result(self, result: ToolCallResult) -> dict[str, object]:
        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.call_id, "call-1")
        self.assertIsInstance(result.output, str)
        return json.loads(result.output)

    def test_shared_budget_stops_next_call_before_handler_execution(self):
        handler = RecordingHandler(output={"status": "ok"})
        executor = make_executor(handler)
        budget = ToolExecutionBudget(max_tool_executions=1)

        result = executor.execute_call(
            ToolCallRequest("call-1", "example_tool", '{"value":21}'),
            budget=budget,
        )

        self.assertEqual(self.decode_result(result), {"status": "ok"})
        self.assertEqual(budget.used_tool_executions, 1)
        with self.assertRaises(ToolLoopStoppedError) as caught:
            executor.execute_call(
                ToolCallRequest("call-2", "example_tool", '{"value":42}'),
                budget=budget,
            )

        self.assertEqual(
            caught.exception.reason,
            ToolLoopStopReason.MAX_TOOL_EXECUTIONS_REACHED,
        )
        self.assertEqual(handler.calls, [{"value": 21}])
        self.assertEqual(budget.used_tool_executions, 1)

    def test_rejected_calls_leave_budget_available_for_valid_call(self):
        cases = (
            ("missing_tool", '{"value":21}', ToolExecutionErrorCategory.UNKNOWN_TOOL),
            ("example_tool", "{", ToolExecutionErrorCategory.INVALID_ARGUMENTS),
            ("example_tool", "[]", ToolExecutionErrorCategory.INVALID_ARGUMENTS),
            ("example_tool", "{}", ToolExecutionErrorCategory.INVALID_ARGUMENTS),
            (
                "example_tool",
                '{"value":"21"}',
                ToolExecutionErrorCategory.INVALID_ARGUMENTS,
            ),
            (
                "example_tool",
                '{"value":21,"extra":true}',
                ToolExecutionErrorCategory.INVALID_ARGUMENTS,
            ),
        )
        for name, arguments, category in cases:
            with self.subTest(name=name, arguments=arguments):
                handler = RecordingHandler()
                executor = make_executor(handler)
                budget = ToolExecutionBudget(max_tool_executions=1)

                result = executor.execute_call(
                    ToolCallRequest("call-1", name, arguments), budget=budget
                )

                self.assertEqual(
                    self.decode_result(result)["error"]["category"], category
                )
                self.assertEqual(handler.calls, [])
                self.assertEqual(budget.used_tool_executions, 0)

                valid_result = executor.execute_call(
                    ToolCallRequest("call-1", "example_tool", '{"value":21}'),
                    budget=budget,
                )

                self.assertEqual(self.decode_result(valid_result), {"status": "ok"})
                self.assertEqual(handler.calls, [{"value": 21}])
                self.assertEqual(budget.used_tool_executions, 1)

    def test_handler_errors_consume_budget_and_stop_next_call(self):
        cases = (
            (
                InvalidToolArgumentsError("Rejected value"),
                ToolExecutionErrorCategory.INVALID_ARGUMENTS,
            ),
            (
                RuntimeError("handler failure"),
                ToolExecutionErrorCategory.EXECUTION_FAILED,
            ),
        )
        for error, category in cases:
            with self.subTest(error=type(error).__name__):
                handler = RecordingHandler(error=error)
                executor = make_executor(handler)
                budget = ToolExecutionBudget(max_tool_executions=1)

                with self.assertLogs("src.tools.executor", level="INFO"):
                    result = executor.execute_call(
                        ToolCallRequest("call-1", "example_tool", '{"value":21}'),
                        budget=budget,
                    )

                self.assertEqual(
                    self.decode_result(result)["error"]["category"], category
                )
                self.assertEqual(budget.used_tool_executions, 1)
                with self.assertRaises(ToolLoopStoppedError) as caught:
                    executor.execute_call(
                        ToolCallRequest("call-2", "example_tool", '{"value":42}'),
                        budget=budget,
                    )

                self.assertEqual(
                    caught.exception.reason,
                    ToolLoopStopReason.MAX_TOOL_EXECUTIONS_REACHED,
                )
                self.assertEqual(handler.calls, [{"value": 21}])
                self.assertEqual(budget.used_tool_executions, 1)

    def test_valid_call_returns_original_output_and_executes_once(self):
        for output in ({"doubled": 42, "text": "测试"}, {}):
            with self.subTest(output=output):
                handler = RecordingHandler(output=output)
                executor = make_executor(handler)
                call = ToolCallRequest("call-1", "example_tool", '{"value":21}')

                result = executor.execute_call(call)

                self.assertEqual(self.decode_result(result), output)
                self.assertEqual(handler.calls, [{"value": 21}])
                self.assertEqual(
                    call,
                    ToolCallRequest("call-1", "example_tool", '{"value":21}'),
                )

    def test_invalid_json_returns_error_without_executing_handler(self):
        for arguments in ("", "{", '{"value":', "not JSON"):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()

                result = make_executor(handler).execute_call(
                    ToolCallRequest("call-1", "example_tool", arguments)
                )

                self.assertEqual(
                    self.decode_result(result),
                    {
                        "error": {
                            "category": "invalid_arguments",
                            "message": "Tool arguments must be valid JSON.",
                        }
                    },
                )
                self.assertEqual(handler.calls, [])

    def test_non_object_json_returns_error_without_executing_handler(self):
        for arguments in ("[]", "[1]", "null", "true", "21", "1.5", '"text"'):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()

                result = make_executor(handler).execute_call(
                    ToolCallRequest("call-1", "example_tool", arguments)
                )

                self.assertEqual(
                    self.decode_result(result),
                    {
                        "error": {
                            "category": "invalid_arguments",
                            "message": "Tool arguments must be a JSON object.",
                        }
                    },
                )
                self.assertEqual(handler.calls, [])

    def test_schema_errors_are_preserved_without_executing_handler(self):
        for arguments in ({}, {"value": "21"}, {"value": 21, "extra": True}):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()
                executor = make_executor(handler)
                expected_error = executor.execute("example_tool", arguments).error

                result = executor.execute_call(
                    ToolCallRequest("call-1", "example_tool", json.dumps(arguments))
                )

                self.assertEqual(
                    self.decode_result(result),
                    {
                        "error": {
                            "category": "invalid_arguments",
                            "message": expected_error.message,
                        }
                    },
                )
                self.assertEqual(handler.calls, [])

    def test_unknown_tool_returns_error_without_executing_handler(self):
        handler = RecordingHandler()

        result = make_executor(handler).execute_call(
            ToolCallRequest("call-1", "missing_tool", '{"value":21}')
        )

        self.assertEqual(
            self.decode_result(result),
            {
                "error": {
                    "category": "unknown_tool",
                    "message": "Tool 'missing_tool' not found in registry",
                }
            },
        )
        self.assertEqual(handler.calls, [])

    def test_handler_parameter_rejection_returns_invalid_arguments(self):
        handler = RecordingHandler(error=InvalidToolArgumentsError("Rejected value"))

        result = make_executor(handler).execute_call(
            ToolCallRequest("call-1", "example_tool", '{"value":21}')
        )

        self.assertEqual(
            self.decode_result(result),
            {
                "error": {
                    "category": "invalid_arguments",
                    "message": "Invalid arguments for tool 'example_tool': Rejected value",
                }
            },
        )
        self.assertEqual(handler.calls, [{"value": 21}])

    def test_handler_failure_returns_execution_error_without_internal_detail(self):
        internal_detail = "internal failure sentinel"
        handler = RecordingHandler(error=RuntimeError(internal_detail))
        executor = make_executor(handler)

        with self.assertLogs("src.tools.executor", level="ERROR") as logs:
            result = executor.execute_call(
                ToolCallRequest("call-1", "example_tool", '{"value":21}')
            )

        self.assertEqual(
            self.decode_result(result),
            {
                "error": {
                    "category": "execution_failed",
                    "message": "Execution of tool 'example_tool' failed.",
                }
            },
        )
        self.assertNotIn(internal_detail, result.output)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("example_tool", logs.records[0].getMessage())
        self.assertIn("failed", logs.records[0].getMessage())
        self.assertNotIn(internal_detail, "\n".join(logs.output))
        self.assertIsNone(logs.records[0].exc_info)
        self.assertEqual(handler.calls, [{"value": 21}])


if __name__ == "__main__":
    unittest.main()
