"""Public run evidence and a single-use, in-memory continuation handle."""

from copy import deepcopy
from dataclasses import dataclass, field, fields
from threading import Lock
from uuid import uuid4


class RunCheckpoint:
    """Owned by one runner; deliberately not serializable or included in traces."""

    def __init__(self, owner: object, state: object):
        self._owner = owner
        self._state = state
        self._consumed = False
        self._lock = Lock()

    def consume(self, owner: object) -> object:
        with self._lock:
            if owner is not self._owner or self._consumed:
                raise ValueError("Checkpoint is foreign or already consumed")
            self._consumed = True
            return self._state


@dataclass
class RunResult:
    status: str
    reason: str
    text: str = ""
    model_requests: int = 0
    tool_rounds: int = 0
    tool_executions: int = 0
    trace: list[dict[str, object]] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: str(uuid4()))
    data: object = None
    question: str | None = None
    model_retries: int = 0
    output_repairs: int = 0
    elapsed_seconds: float = 0.0
    usage: dict[str, int] | None = None
    usage_complete: bool = True
    model: str | None = None
    limits: dict[str, object] = field(default_factory=dict)
    checkpoint: RunCheckpoint | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        return {
            item.name: deepcopy(getattr(self, item.name))
            for item in fields(self)
            if item.name != "checkpoint"
        }
