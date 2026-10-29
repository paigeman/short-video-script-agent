"""Minimal live configuration adapted from AI-demo, without model profiles."""

import argparse
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self
from urllib.parse import urlsplit

from src.llm.types import REASONING_EFFORTS

DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_MAX_RUN_SECONDS = 180.0


class ConfigurationError(ValueError):
    """Identify the invalid setting without including its potentially secret value."""

    def __init__(self, field_name: str):
        self.field_name = field_name
        super().__init__(f"Missing or invalid {field_name}")


def _number(env: Mapping[str, str], name: str, default, convert):
    if name not in env:
        return default
    try:
        return convert(env[name])
    except (TypeError, ValueError, OverflowError):
        raise ConfigurationError(name) from None


@dataclass(frozen=True)
class ModelConfig:
    model: str
    api_key: str = field(repr=False)
    base_url: str | None = field(default=None, repr=False)
    timeout_seconds: float = 30.0
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    reasoning_effort: str | None = None
    max_run_seconds: float = DEFAULT_MAX_RUN_SECONDS

    def __post_init__(self):
        for name, value in (("MODEL", self.model), ("API_KEY", self.api_key)):
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(name)
        for name, value in (
            ("MODEL_TIMEOUT_SECONDS", self.timeout_seconds),
            ("MAX_RUN_SECONDS", self.max_run_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ConfigurationError(name)
        if type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise ConfigurationError("MAX_OUTPUT_TOKENS")
        if self.reasoning_effort is not None and (
            not isinstance(self.reasoning_effort, str)
            or self.reasoning_effort not in REASONING_EFFORTS
        ):
            raise ConfigurationError("REASONING_EFFORT")
        if self.base_url is not None:
            try:
                if not isinstance(self.base_url, str) or any(
                    char.isspace() for char in self.base_url
                ):
                    raise ValueError
                url = urlsplit(self.base_url)
                if (
                    url.scheme not in {"http", "https"}
                    or not url.hostname
                    or url.username is not None
                    or url.password is not None
                    or url.query
                    or url.fragment
                    or url.port == 0
                ):
                    raise ValueError
            except (TypeError, ValueError):
                raise ConfigurationError("BASE_URL") from None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        env = os.environ if env is None else env
        effort = env.get("REASONING_EFFORT")
        return cls(
            model=env.get("MODEL", "").strip(),
            api_key=env.get("API_KEY", "").strip(),
            base_url=env.get("BASE_URL", "").strip() or None,
            timeout_seconds=_number(env, "MODEL_TIMEOUT_SECONDS", 30.0, float),
            max_output_tokens=_number(
                env, "MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, int
            ),
            reasoning_effort=effort.strip() if effort is not None else None,
            max_run_seconds=_number(
                env, "MAX_RUN_SECONDS", DEFAULT_MAX_RUN_SECONDS, float
            ),
        )

    def public_settings(self) -> dict:
        """An explicit allowlist: never serialize this dataclass with asdict()."""
        return {
            "api": "responses",
            "model": self.model,
            "endpoint": "custom" if self.base_url else "sdk_default",
            "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
            "max_run_seconds": self.max_run_seconds,
        }


def main() -> int:
    argparse.ArgumentParser(
        description="Validate live settings without a model call"
    ).parse_args()
    try:
        settings = ModelConfig.from_env().public_settings()
    except ConfigurationError as exc:
        print(json.dumps({"status": "configuration_error", "field": exc.field_name}))
        return 2
    print(json.dumps({"status": "configuration_valid", "model_settings": settings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
