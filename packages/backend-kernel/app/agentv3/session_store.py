from __future__ import annotations

import asyncio
from typing import Any, Dict, List


class AgentV3SessionStore:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.messages: Dict[str, List[Dict[str, Any]]] = {}
        self.pending_permissions: Dict[str, Dict[str, Any]] = {}
