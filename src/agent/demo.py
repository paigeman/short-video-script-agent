"""Offline runtime demonstration; this does not generate video scripts."""

import argparse
import json

from src.agent.control import RuntimePolicy
from src.agent.runner import AgentRunner
from src.llm.types import Message, ModelCallError, ModelRequest, ModelResponse
from src.tools.definition import RegisteredTool, ToolDefinition
from src.tools.limits import ToolLoopLimits
from src.tools.protocol import ToolCallRequest, ToolCallResult
from src.tools.registry import ToolRegistry


class DemoModel:
    """A deterministic test double that observes actual tool results."""

    def __init__(self, keep_calling: bool = False):
        self.keep_calling = keep_calling

    def send(self, request: ModelRequest) -> ModelResponse:
        results = [item for item in request.input if isinstance(item, ToolCallResult)]
        if results and not self.keep_calling:
            observed = json.loads(results[-1].output)
            if "error" not in observed:
                return ModelResponse(text="Offline runtime demonstration completed.")
        action = "Read the demo value."
        if results:
            action = (
                "Continue calling to exercise the configured limit."
                if self.keep_calling
                else "Retry the failed demo tool."
            )
        return ModelResponse(
            text=action,
            tool_calls=[
                ToolCallRequest(f"demo-{len(results) + 1}", "echo", '{"value":"ready"}')
            ],
        )


class CapabilitiesModel:
    """Exercise generic runtime facilities using only synthetic values."""

    model = "offline-capabilities-model"

    def __init__(self):
        self.failed_once = False

    def send(self, request: ModelRequest) -> ModelResponse:
        results = [item for item in request.input if isinstance(item, ToolCallResult)]
        if not results:
            return ModelResponse(
                tool_calls=[
                    ToolCallRequest(
                        "question-1",
                        "ask_user",
                        '{"question":"Which synthetic integer should I use?"}',
                    )
                ]
            )
        observed = json.loads(results[-1].output)
        if "answer" in observed:
            return ModelResponse(
                tool_calls=[
                    ToolCallRequest(
                        "echo-1", "echo", json.dumps({"value": int(observed["answer"])})
                    )
                ]
            )
        repair_requested = any(
            isinstance(item, Message) and "failed JSON validation" in item.content
            for item in request.input
        )
        if not repair_requested:
            return ModelResponse(text=json.dumps({"value": str(observed["value"])}))
        if not self.failed_once:
            self.failed_once = True
            raise ModelCallError("connection_failed", retryable=True)
        return ModelResponse(text=json.dumps(observed))


def run_capabilities_demo() -> dict[str, object]:
    schema = {
        "type": "object",
        "required": ["value"],
        "additionalProperties": False,
        "properties": {"value": {"type": "integer"}},
    }
    registry = ToolRegistry(
        [
            RegisteredTool(
                ToolDefinition("echo", "Echo a synthetic integer.", schema),
                lambda arguments: {"value": arguments["value"]},
            )
        ]
    )
    runner = AgentRunner(
        CapabilitiesModel(),
        registry,
        ToolLoopLimits(max_model_requests=6),
        policy=RuntimePolicy(retry_base_seconds=0),
    )
    paused = runner.run(
        ModelRequest([Message("user", "Verify generic runtime capabilities.")]),
        output_schema=schema,
    )
    final = runner.resume(paused.checkpoint, "7")
    return {
        "mode": "offline_demo",
        "scenario": "capabilities",
        "answer_source": "synthetic demo answer, not a human response",
        "paused": paused.to_dict(),
        "final": final.to_dict(),
    }


def run_demo(scenario: str) -> dict[str, object]:
    if scenario == "capabilities":
        return run_capabilities_demo()
    if scenario not in {"normal", "tool-failure", "limit"}:
        raise ValueError("Unknown demo scenario")
    attempts = 0

    def echo(arguments):
        nonlocal attempts
        attempts += 1
        if scenario == "tool-failure" and attempts == 1:
            raise RuntimeError("Simulated demo failure")
        return {"value": arguments["value"]}

    registry = ToolRegistry(
        [
            RegisteredTool(
                ToolDefinition(
                    "echo",
                    "Return a synthetic value for runtime verification.",
                    {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                ),
                echo,
            )
        ]
    )
    runner = AgentRunner(
        DemoModel(keep_calling=scenario == "limit"),
        registry,
        ToolLoopLimits(max_tool_rounds=2, max_model_requests=4, max_tool_executions=4),
    )
    result = runner.run(ModelRequest([Message("user", "Verify the demo tool loop.")]))
    return {"mode": "offline_demo", "scenario": scenario, **result.to_dict()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=["normal", "tool-failure", "limit", "capabilities"],
        default="normal",
    )
    args = parser.parse_args()
    print(json.dumps(run_demo(args.scenario), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
