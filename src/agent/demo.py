"""Offline runtime demonstration; this does not generate video scripts."""

import argparse
import json

from src.agent.runner import AgentRunner
from src.llm.types import Message, ModelRequest, ModelResponse
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


def run_demo(scenario: str) -> dict[str, object]:
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
        "--scenario", choices=["normal", "tool-failure", "limit"], default="normal"
    )
    args = parser.parse_args()
    print(json.dumps(run_demo(args.scenario), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
