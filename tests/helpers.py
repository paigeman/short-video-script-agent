from copy import deepcopy

from src.llm.types import ModelRequest, ModelResponse
from src.tools.definition import RegisteredTool, ToolDefinition
from src.tools.registry import ToolRegistry


class ScriptedModel:
    def __init__(self, responses: list[ModelResponse]):
        self.responses = responses
        self.requests: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(deepcopy(request))
        return self.responses[len(self.requests) - 1]


def echo_registry(calls: list, handler=None) -> ToolRegistry:
    def echo(arguments):
        calls.append(dict(arguments))
        return {"value": arguments["value"]}

    return ToolRegistry(
        [
            RegisteredTool(
                ToolDefinition(
                    "echo",
                    "Return the provided value.",
                    {
                        "type": "object",
                        "properties": {"value": {"type": "integer"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                ),
                handler or echo,
            )
        ]
    )
