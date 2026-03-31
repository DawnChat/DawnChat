from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from app.agentv3.runtime.events import RunEvent


@dataclass(slots=True)
class StepResult:
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    events: List[RunEvent] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None


class Executor(Protocol):
    async def execute(self, step_input: Dict[str, Any]) -> StepResult:
        ...

