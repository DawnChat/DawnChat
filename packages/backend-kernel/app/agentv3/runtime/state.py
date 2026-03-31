from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

FinishReason = Literal["completed", "interrupted", "error", "cancelled"]


@dataclass(slots=True)
class RunState:
    session_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[FinishReason] = None

