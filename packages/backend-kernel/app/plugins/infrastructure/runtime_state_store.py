from __future__ import annotations

import asyncio


class PluginRuntimeStateStore:
    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._allocated_ports: set[int] = set()
        self._runtime_log_sessions: dict[str, str] = {}

    def set_process(self, plugin_id: str, process: asyncio.subprocess.Process) -> None:
        self._processes[plugin_id] = process

    def get_process(self, plugin_id: str) -> asyncio.subprocess.Process | None:
        return self._processes.get(plugin_id)

    def pop_process(self, plugin_id: str) -> asyncio.subprocess.Process | None:
        return self._processes.pop(plugin_id, None)

    def reserve_port(self, port: int) -> bool:
        if port in self._allocated_ports:
            return False
        self._allocated_ports.add(port)
        return True

    def release_port(self, port: int) -> None:
        self._allocated_ports.discard(port)

    def set_runtime_log_session(self, plugin_id: str, session_id: str) -> None:
        self._runtime_log_sessions[plugin_id] = session_id

    def pop_runtime_log_session(self, plugin_id: str) -> str | None:
        return self._runtime_log_sessions.pop(plugin_id, None)
