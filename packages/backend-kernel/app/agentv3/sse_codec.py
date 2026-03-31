from __future__ import annotations

import json
from typing import Any, Dict, Optional


def encode_sse_event(payload: Dict[str, Any], *, retry_ms: Optional[int] = None) -> str:
    event_id = payload.get("eventID")
    lines: list[str] = []
    if retry_ms is not None and int(retry_ms) > 0:
        lines.append(f"retry: {int(retry_ms)}")
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"
