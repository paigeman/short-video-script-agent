"""Bounded model/tool execution, structured completion, and clarification resumes."""

import json
import math
import random
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace

from jsonschema import Draft202012Validator

from src.agent.control import RunControl, RuntimePolicy
from src.agent.state import RunCheckpoint, RunResult
from src.llm.types import (
    Message,
    ModelCallError,
    ModelClient,
    ModelRequest,
    ModelResponse,
)
from src.tools.definition import ToolDefinition
from src.tools.errors import ToolLoopStoppedError, ToolLoopStopReason
from src.tools.executor import ToolExecutor
from src.tools.limits import ToolExecutionBudget, ToolLoopLimits
from src.tools.protocol import ToolCallRequest, ToolCallResult
from src.tools.registry import ToolRegistry
from src.validation import StructuredOutputError, validate_json

ASK_USER = ToolDefinition(
    "ask_user",
    "Ask the user for missing information and pause until they answer.",
    {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2000,
                "pattern": r"\S",
            }
        },
        "required": ["question"],
        "additionalProperties": False,
    },
)


def _size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


@dataclass
class _State:
    request: ModelRequest
    result: RunResult
    budget: ToolExecutionBudget
    schema: dict[str, object] | None = None
    seen: set[str] = field(default_factory=set)
    pending: deque[ToolCallRequest] = field(default_factory=deque)
    awaiting: ToolCallRequest | None = None


class AgentRunner:
    def __init__(
        self,
        client: ModelClient,
        registry: ToolRegistry,
        limits: ToolLoopLimits | None = None,
        *,
        policy: RuntimePolicy | None = None,
        allow_clarification: bool = True,
    ):
        self.client = client
        self.registry = registry
        self.executor = ToolExecutor(registry)
        self.limits = limits if limits is not None else ToolLoopLimits()
        self.policy = policy if policy is not None else RuntimePolicy()
        self.allow_clarification = allow_clarification
        if allow_clarification and any(
            tool.name == ASK_USER.name for tool in registry.get_tool_list()
        ):
            raise ValueError("ask_user is reserved when clarification is enabled")

    def run(
        self,
        request: ModelRequest,
        *,
        output_schema: dict[str, object] | None = None,
        control: RunControl | None = None,
    ) -> RunResult:
        if not request.input:
            raise ValueError("A run requires at least one input item")
        if type(request.max_output_tokens) is not int or request.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")
        timeout = request.timeout_seconds
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        current = replace(
            deepcopy(request), tools=deepcopy(self.registry.get_tool_list())
        )
        if self.allow_clarification:
            current.tools.append(deepcopy(ASK_USER))
        schema = deepcopy(output_schema)
        if schema is not None:
            Draft202012Validator.check_schema(schema)
            current.input.insert(
                0,
                Message(
                    "system",
                    "Return the final answer as JSON matching this schema. "
                    "Tool calls may precede the final answer. Schema: "
                    + json.dumps(schema, ensure_ascii=False, allow_nan=False),
                ),
            )
        result = RunResult(
            status="incomplete",
            reason="running",
            model=getattr(self.client, "model", None),
            limits={**asdict(self.limits), **asdict(self.policy)},
        )
        state = _State(
            current,
            result,
            ToolExecutionBudget(self.limits.max_tool_executions),
            schema,
        )
        return self._drive(state, control if control is not None else RunControl())

    def resume(
        self,
        checkpoint: RunCheckpoint,
        answer: str,
        *,
        control: RunControl | None = None,
    ) -> RunResult:
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("A nonempty user answer is required")
        output = json.dumps({"answer": answer}, ensure_ascii=False)
        if len(output.encode("utf-8")) > self.policy.max_tool_output_bytes:
            raise ValueError("User answer exceeds the tool output byte limit")
        state = checkpoint.consume(self)
        call = state.awaiting
        state.awaiting = None
        state.result.question = None
        state.request.input.append(ToolCallResult(call.call_id, output))
        state.result.trace.append(
            {
                "event": "user_input",
                "call_id": call.call_id,
                "answer_chars": len(answer),
            }
        )
        return self._drive(state, control if control is not None else RunControl())

    @staticmethod
    def _append_response(state: _State, response: ModelResponse) -> None:
        if response.continuation:
            state.request.input.extend(deepcopy(response.continuation))
        else:
            if response.text:
                state.request.input.append(Message("assistant", response.text))
            state.request.input.extend(deepcopy(response.tool_calls))

    @staticmethod
    def _observe_usage(result: RunResult, usage: dict[str, int] | None) -> None:
        if usage is None:
            result.usage_complete = False
            return
        if result.usage is None:
            result.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for key in result.usage:
            result.usage[key] += usage[key]

    @staticmethod
    def _tool_error(
        call: ToolCallRequest, category: str, message: str
    ) -> ToolCallResult:
        return ToolCallResult(
            call.call_id,
            json.dumps({"error": {"category": category, "message": message}}),
        )

    def _drive(self, state: _State, control: RunControl) -> RunResult:
        result = state.result
        started = control.clock()
        prior_elapsed = result.elapsed_seconds

        def remaining() -> float:
            return (
                self.policy.max_run_seconds
                - prior_elapsed
                - (control.clock() - started)
            )

        def stop(status: str, reason: str, text: str = "") -> RunResult:
            result.status, result.reason, result.text = status, reason, text
            result.tool_executions = state.budget.used_tool_executions
            result.elapsed_seconds = prior_elapsed + max(0, control.clock() - started)
            result.trace.append({"event": "stop", "status": status, "reason": reason})
            snapshot = deepcopy(result)
            if status == "needs_input":
                snapshot.checkpoint = RunCheckpoint(self, state)
            return snapshot

        def guard() -> RunResult | None:
            if control.is_cancelled():
                return stop("cancelled", "cancelled")
            if remaining() <= 0:
                return stop("incomplete", "run_timeout")
            if _size(asdict(state.request)) > self.policy.max_context_bytes:
                return stop("incomplete", "max_context_bytes_reached")
            return None

        while True:
            if (stopped := guard()) is not None:
                return stopped
            while state.pending:
                if (stopped := guard()) is not None:
                    return stopped
                call = state.pending.popleft()
                tool_started = control.clock()
                if self.allow_clarification and call.name == ASK_USER.name:
                    try:
                        args = validate_json(call.arguments, ASK_USER.parameter_schema)
                    except StructuredOutputError:
                        output = self._tool_error(
                            call, "invalid_arguments", "Provide one nonempty question."
                        )
                    else:
                        state.awaiting = call
                        result.question = args["question"]
                        result.trace.append(
                            {
                                "event": "clarification",
                                "call_id": call.call_id,
                                "question": result.question,
                            }
                        )
                        return stop("needs_input", "user_input_required")
                else:
                    try:
                        output = self.executor.execute_call(call, state.budget)
                    except ToolLoopStoppedError as exc:
                        return stop("incomplete", exc.reason)
                output_bytes = len(output.output.encode("utf-8"))
                if output_bytes > self.policy.max_tool_output_bytes:
                    output = self._tool_error(
                        call,
                        "output_too_large",
                        "Tool output exceeds the configured byte limit.",
                    )
                state.request.input.append(output)
                result.trace.append(
                    {
                        "event": "tool",
                        "round": result.tool_rounds,
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments[:1000],
                        "arguments_truncated": len(call.arguments) > 1000,
                        "output_summary": output.output[:1000],
                        "output_summary_truncated": len(output.output) > 1000,
                        "output_bytes": output_bytes,
                        "elapsed_seconds": max(0, control.clock() - tool_started),
                    }
                )
            if (stopped := guard()) is not None:
                return stopped
            if result.model_requests >= self.limits.max_model_requests:
                return stop("incomplete", ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED)
            outbound = deepcopy(state.request)
            if control.is_cancelled():
                return stop("cancelled", "cancelled")
            time_left = remaining()
            if time_left <= 0:
                return stop("incomplete", "run_timeout")
            model_started = control.clock()
            timeout = min(state.request.timeout_seconds or time_left, time_left)
            result.model_requests += 1
            try:
                response = self.client.send(replace(outbound, timeout_seconds=timeout))
            except ModelCallError as exc:
                result.usage_complete = False
                result.trace.append(
                    {
                        "event": "model_error",
                        "request": result.model_requests,
                        "code": exc.code,
                        "elapsed_seconds": max(0, control.clock() - model_started),
                    }
                )
                if (stopped := guard()) is not None:
                    return stopped
                if (
                    not exc.retryable
                    or result.model_retries >= self.policy.max_model_retries
                ):
                    return stop("model_error", exc.code)
                if result.model_requests >= self.limits.max_model_requests:
                    return stop(
                        "incomplete", ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED
                    )
                delay = self.policy.retry_base_seconds * (
                    2 ** min(result.model_retries, 10)
                )
                delay = min(delay, self.policy.max_retry_delay_seconds)
                delay *= random.uniform(0.75, 1.0)
                if exc.retry_after is not None:
                    delay = max(delay, exc.retry_after)
                if delay >= remaining() or delay > self.policy.max_retry_delay_seconds:
                    return stop("incomplete", "retry_delay_exceeds_budget")
                result.model_retries += 1
                result.trace.append({"event": "model_retry", "delay_seconds": delay})
                control.wait(delay)
                continue

            self._observe_usage(result, response.usage)
            result.trace.append(
                {
                    "event": "model",
                    "request": result.model_requests,
                    "reason": response.reason,
                    "summary": response.text[:1000],
                    "summary_truncated": len(response.text) > 1000,
                    "calls": [
                        {
                            **asdict(call),
                            "arguments": call.arguments[:1000],
                            "arguments_truncated": len(call.arguments) > 1000,
                        }
                        for call in response.tool_calls
                    ],
                    "usage": deepcopy(response.usage),
                    "elapsed_seconds": max(0, control.clock() - model_started),
                }
            )
            if (stopped := guard()) is not None:
                return stopped
            if response.reason != "completed":
                return stop("incomplete", response.reason, response.text)
            if not response.tool_calls:
                if state.schema is not None:
                    try:
                        data = validate_json(response.text, state.schema)
                    except StructuredOutputError as exc:
                        result.trace.append(
                            {
                                "event": "output_validation_error",
                                "category": exc.category,
                                "field_path": exc.field_path,
                            }
                        )
                        if result.output_repairs >= self.policy.max_output_repairs:
                            return stop("incomplete", "invalid_output", response.text)
                        self._append_response(state, response)
                        state.request.input.append(
                            Message(
                                "system",
                                "The final answer failed JSON validation: "
                                f"{exc.category} at {exc.field_path}. Correct it using the supplied schema.",
                            )
                        )
                        result.output_repairs += 1
                        continue
                    if (stopped := guard()) is not None:
                        return stopped
                    result.data = data
                elif not response.text.strip():
                    return stop("incomplete", "empty_response")
                return stop("completed", "model_finished", response.text)

            call_ids = [call.call_id for call in response.tool_calls]
            if (
                any(not call_id for call_id in call_ids)
                or len(set(call_ids)) != len(call_ids)
                or state.seen.intersection(call_ids)
            ):
                return stop("model_error", "invalid_call_ids")
            if result.tool_rounds >= self.limits.max_tool_rounds:
                return stop("incomplete", ToolLoopStopReason.MAX_TOOL_ROUNDS_REACHED)
            if result.model_requests >= self.limits.max_model_requests:
                return stop("incomplete", ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED)
            state.seen.update(call_ids)
            result.tool_rounds += 1
            self._append_response(state, response)
            state.pending.extend(deepcopy(response.tool_calls))
