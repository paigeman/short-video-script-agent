from dataclasses import dataclass

from src.tools.errors import ToolLoopStoppedError, ToolLoopStopReason


@dataclass(frozen=True)
class ToolLoopLimits:
    max_tool_rounds: int = 3
    max_model_requests: int = 4
    max_tool_executions: int = 8

    def __post_init__(self):
        for name in ("max_tool_rounds", "max_model_requests", "max_tool_executions"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass
class ToolExecutionBudget:
    max_tool_executions: int
    used_tool_executions: int = 0

    def consume(self):
        if self.used_tool_executions >= self.max_tool_executions:
            raise ToolLoopStoppedError(ToolLoopStopReason.MAX_TOOL_EXECUTIONS_REACHED)
        self.used_tool_executions += 1
