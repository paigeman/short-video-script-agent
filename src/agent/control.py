"""Resource policies and cooperative cancellation, independent of any business task."""

import math
import time
from dataclasses import dataclass, field
from threading import Event


@dataclass(frozen=True)
class RuntimePolicy:
    max_model_retries: int = 2
    max_output_repairs: int = 1
    max_context_bytes: int = 128_000
    max_tool_output_bytes: int = 32_000
    max_run_seconds: float = 120.0
    retry_base_seconds: float = 0.5
    max_retry_delay_seconds: float = 30.0

    def __post_init__(self):
        for name in ("max_model_retries", "max_output_repairs"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in ("max_context_bytes", "max_tool_output_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in (
            "max_run_seconds",
            "retry_base_seconds",
            "max_retry_delay_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or (name != "retry_base_seconds" and value == 0)
            ):
                raise ValueError(f"Invalid {name}")


@dataclass
class RunControl:
    """Cancellation is checked between synchronous operations and during retry waits."""

    cancellation: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self.cancellation.set()

    def is_cancelled(self) -> bool:
        return self.cancellation.is_set()

    def clock(self) -> float:
        return time.monotonic()

    def wait(self, seconds: float) -> None:
        self.cancellation.wait(seconds)
