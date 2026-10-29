"""Minimal provider-independent contracts extracted from AI-demo."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from src.tools.definition import ToolDefinition
from src.tools.protocol import ToolCallRequest, ToolCallResult


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ProviderItem:
    """Opaque continuation data; never included in exported execution traces."""

    provider: str
    payload: dict[str, object] = field(repr=False)


type ModelInputItem = Message | ToolCallRequest | ToolCallResult | ProviderItem


@dataclass
class ModelRequest:
    input: list[ModelInputItem]
    tools: list[ToolDefinition] = field(default_factory=list)
    max_output_tokens: int = 2048


@dataclass
class ModelResponse:
    text: str = ""
    reason: str = "completed"
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    continuation: list[ProviderItem] = field(default_factory=list, repr=False)
    usage: dict[str, int] | None = None


class ModelCallError(RuntimeError):
    """Sanitized provider failure that the runner can report safely."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ModelClient(Protocol):
    def send(self, request: ModelRequest) -> ModelResponse: ...
