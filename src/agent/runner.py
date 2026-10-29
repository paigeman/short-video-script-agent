"""Run model/tool turns with explicit limits and portable execution evidence."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace

from src.llm.types import Message, ModelCallError, ModelClient, ModelRequest
from src.tools.errors import ToolLoopStoppedError, ToolLoopStopReason
from src.tools.executor import ToolExecutor
from src.tools.limits import ToolExecutionBudget, ToolLoopLimits
from src.tools.registry import ToolRegistry


@dataclass
class RunResult:
    status: str
    reason: str
    text: str = ""
    model_requests: int = 0
    tool_rounds: int = 0
    tool_executions: int = 0
    trace: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AgentRunner:
    def __init__(
        self,
        client: ModelClient,
        registry: ToolRegistry,
        limits: ToolLoopLimits | None = None,
    ):
        self.client = client
        self.registry = registry
        self.executor = ToolExecutor(registry)
        self.limits = limits if limits is not None else ToolLoopLimits()

    def run(self, request: ModelRequest) -> RunResult:
        if not request.input:
            raise ValueError("A run requires at least one input item")
        if type(request.max_output_tokens) is not int or request.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")
        current = replace(
            deepcopy(request), tools=deepcopy(self.registry.get_tool_list())
        )
        budget = ToolExecutionBudget(self.limits.max_tool_executions)
        result = RunResult(status="incomplete", reason="running")
        seen_call_ids: set[str] = set()

        def finish(status: str, reason: str, text: str = "") -> RunResult:
            result.status, result.reason, result.text = status, reason, text
            result.tool_executions = budget.used_tool_executions
            result.trace.append({"event": "stop", "status": status, "reason": reason})
            return result

        while True:
            if result.model_requests >= self.limits.max_model_requests:
                return finish(
                    "incomplete", ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED
                )
            result.model_requests += 1
            try:
                response = self.client.send(deepcopy(current))
            except ModelCallError as exc:
                result.trace.append(
                    {
                        "event": "model_error",
                        "request": result.model_requests,
                        "code": exc.code,
                    }
                )
                return finish("model_error", exc.code)

            result.trace.append(
                {
                    "event": "model",
                    "request": result.model_requests,
                    "reason": response.reason,
                    "summary": response.text[:1000],
                    "calls": [asdict(call) for call in response.tool_calls],
                    "usage": deepcopy(response.usage),
                }
            )
            if response.reason != "completed":
                return finish("incomplete", response.reason, response.text)
            if not response.tool_calls:
                if not response.text.strip():
                    return finish("incomplete", "empty_response")
                return finish("completed", "model_finished", response.text)

            call_ids = [call.call_id for call in response.tool_calls]
            if (
                any(not call_id for call_id in call_ids)
                or len(set(call_ids)) != len(call_ids)
                or seen_call_ids.intersection(call_ids)
            ):
                return finish("model_error", "invalid_call_ids")
            if result.tool_rounds >= self.limits.max_tool_rounds:
                return finish("incomplete", ToolLoopStopReason.MAX_TOOL_ROUNDS_REACHED)
            # Do not execute tools when there is no budget to send their results back.
            if result.model_requests >= self.limits.max_model_requests:
                return finish(
                    "incomplete", ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED
                )

            seen_call_ids.update(call_ids)
            result.tool_rounds += 1
            if response.continuation:
                current.input.extend(deepcopy(response.continuation))
            else:
                if response.text:
                    current.input.append(Message("assistant", response.text))
                current.input.extend(deepcopy(response.tool_calls))
            for call in response.tool_calls:
                try:
                    output = self.executor.execute_call(call, budget)
                except ToolLoopStoppedError as exc:
                    return finish("incomplete", exc.reason)
                current.input.append(output)
                result.trace.append(
                    {
                        "event": "tool",
                        "round": result.tool_rounds,
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "output_summary": output.output[:1000],
                    }
                )
