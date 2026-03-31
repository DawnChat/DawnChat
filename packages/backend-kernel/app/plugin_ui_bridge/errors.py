from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class PluginUIBridgeError(Exception):
    code: str
    message: str
    details: Dict[str, Any] | None = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "error_code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload

