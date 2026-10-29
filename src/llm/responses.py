"""Synchronous Responses API adapter adapted from AI-demo's OpenAIClient."""

import math
import os
from copy import deepcopy
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Self

import httpx
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)

from src.llm.types import (
    Message,
    ModelCallError,
    ModelInputItem,
    ModelRequest,
    ModelResponse,
    ProviderItem,
)
from src.tools.protocol import ToolCallRequest, ToolCallResult


def _retry_after(headers: httpx.Headers) -> float | None:
    value = headers.get("retry-after-ms")
    if value is not None:
        try:
            delay = float(value) / 1000
            if math.isfinite(delay) and delay >= 0:
                return delay
        except ValueError:
            pass
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            delay = (date - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0, delay) if math.isfinite(delay) else None


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
        self.timeout_seconds = timeout_seconds
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
        if request.timeout_seconds is not None:
            timeout = request.timeout_seconds
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or timeout <= 0
            ):
                raise ValueError("timeout_seconds must be finite and positive")
            options["timeout"] = min(self.timeout_seconds, timeout)
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
            raise ModelCallError("model_timeout", retryable=True) from None
        except APIConnectionError:
            raise ModelCallError("connection_failed", retryable=True) from None
        except APIStatusError as exc:
            permanent_codes = {
                "insufficient_quota",
                "billing_hard_limit_reached",
                "organization_spend_limit_exceeded",
                "project_spend_limit_exceeded",
                "organization_usage_limit_exceeded",
                "billing_not_active",
            }
            retryable = (
                exc.status_code in {408, 409, 429, 500, 502, 503, 504}
                and (exc.code is None or isinstance(exc.code, str))
                and exc.code not in permanent_codes
                and exc.type != "insufficient_quota"
                and exc.response.headers.get("x-should-retry", "").lower() != "false"
            )
            raise ModelCallError(
                f"http_{exc.status_code}",
                retryable=retryable,
                retry_after=_retry_after(exc.response.headers),
            ) from None
        except (APIResponseValidationError, ValueError):
            raise ModelCallError("invalid_response") from None

        try:
            return self._decode(response)
        except (AttributeError, TypeError, ValueError, KeyError):
            raise ModelCallError("invalid_response") from None

    @staticmethod
    def _decode(response) -> ModelResponse:
        if not isinstance(response.output, list):
            raise ModelCallError("invalid_response")
        if any(
            item.type not in {"message", "reasoning", "function_call"}
            for item in response.output
        ):
            raise ModelCallError("unsupported_output_item")
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
        if response.usage is not None and any(
            type(getattr(response.usage, key)) is not int
            or getattr(response.usage, key) < 0
            for key in ("input_tokens", "output_tokens", "total_tokens")
        ):
            raise ModelCallError("invalid_response")
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
