from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Dict, Optional


@dataclass(slots=True)
class RunEvent:
    type: str
    session_id: str
    message_id: Optional[str] = None
    engine: str = "agentv3"
    ts: int = field(default_factory=lambda: int(time() * 1000))
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "sessionID": self.session_id,
            "messageID": self.message_id,
            "engine": self.engine,
            "ts": self.ts,
            "properties": self.properties,
        }

