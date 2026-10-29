"""Synchronous Responses API adapter adapted from AI-demo's OpenAIClient."""

import math
import os
from copy import deepcopy
from typing import Self

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from src.llm.types import (
    Message,
    ModelCallError,
    ModelInputItem,
    ModelRequest,
    ModelResponse,
    ProviderItem,
)
from src.tools.protocol import ToolCallRequest, ToolCallResult


def to_responses_item(item: ModelInputItem) -> dict[str, object]:
    match item:
        case Message(role=role, content=content):
            return {"role": role, "content": content}
        case ToolCallRequest(call_id=call_id, name=name, arguments=arguments):
            return {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
        case ToolCallResult(call_id=call_id, output=output):
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
            }
        case ProviderItem(provider="responses", payload=payload):
            return deepcopy(payload)
        case _:
            raise TypeError(f"Unsupported input item: {type(item).__name__}")


class ResponsesClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        http_client: httpx.Client | None = None,
    ):
        if not model.strip() or not api_key.strip():
            raise ValueError("Model and API key must be configured")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
            http_client=http_client,
        )

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            model=os.environ.get("MODEL", ""),
            api_key=os.environ.get("API_KEY", ""),
            base_url=os.environ.get("BASE_URL") or None,
            timeout_seconds=float(os.environ.get("MODEL_TIMEOUT_SECONDS", "30")),
        )

    def send(self, request: ModelRequest) -> ModelResponse:
        options = {
            "model": self.model,
            "input": [to_responses_item(item) for item in request.input],
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if request.tools:
            options["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": deepcopy(tool.parameter_schema),
                    # The executor validates arbitrary local JSON Schemas itself.
                    "strict": False,
                }
                for tool in request.tools
            ]
        try:
            response = self._client.responses.create(**options)
        except APITimeoutError:
            raise ModelCallError("model_timeout") from None
        except APIConnectionError:
            raise ModelCallError("connection_failed") from None
        except APIStatusError as exc:
            raise ModelCallError(f"http_{exc.status_code}") from None

        calls = [
            ToolCallRequest(item.call_id, item.name, item.arguments)
            for item in response.output
            if item.type == "function_call"
        ]
        if any(
            not isinstance(call.call_id, str)
            or not call.call_id
            or not isinstance(call.name, str)
            or not call.name
            or not isinstance(call.arguments, str)
            for call in calls
        ):
            raise ModelCallError("invalid_response")
        reason = {
            "completed": "completed",
            "incomplete": "model_incomplete",
            "failed": "model_failed",
            "cancelled": "model_cancelled",
        }.get(response.status, "unexpected_response_status")
        if any(
            part.type == "refusal"
            for item in response.output
            if item.type == "message"
            for part in item.content
        ):
            reason = "model_refused"
        return ModelResponse(
            text=response.output_text,
            reason=reason,
            tool_calls=calls,
            continuation=[
                ProviderItem(
                    "responses", item.model_dump(mode="json", exclude_none=True)
                )
                for item in response.output
            ],
            usage=(
                {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                if response.usage is not None
                else None
            ),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
