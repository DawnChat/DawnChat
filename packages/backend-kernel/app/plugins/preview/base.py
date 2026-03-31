from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from watchdog.observers.api import BaseObserver

if TYPE_CHECKING:
    from app.plugins.preview_manager import PluginPreviewManager


@dataclass
class PreviewSession:
    plugin_id: str
    app_type: str
    plugin_path: Path
    backend_kind: str = "python"
    frontend_port: Optional[int] = None
    backend_port: Optional[int] = None
    entry_path: Optional[Path] = None
    python_exe: Optional[Path] = None
    python_sidecar_entry_path: Optional[Path] = None
    python_sidecar_exe: Optional[Path] = None
    watcher_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    watcher: Optional[BaseObserver] = None
    watcher_task: Optional[asyncio.Task[None]] = None
    python_process: Optional[asyncio.subprocess.Process] = None
    python_sidecar_process: Optional[asyncio.subprocess.Process] = None
    bun_process: Optional[asyncio.subprocess.Process] = None
    python_sidecar_port: Optional[int] = None
    python_sidecar_state: str = "stopped"
    python_sidecar_error_message: Optional[str] = None
    log_session_id: str = ""
    log_tasks: list[asyncio.Task[None]] = field(default_factory=list)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    frontend_mode: str = "dev"  # dev | dist
    deps_ready: bool = True
    install_status: str = "idle"  # idle | running | success | failed
    install_error_message: Optional[str] = None
    install_task: Optional[asyncio.Task[None]] = None


class PreviewStrategy(ABC):
    @property
    @abstractmethod
    def app_type(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def create_session(self, manager: PluginPreviewManager, plugin) -> PreviewSession:
        raise NotImplementedError

    @abstractmethod
    async def start(self, manager: PluginPreviewManager, plugin, session: PreviewSession) -> None:
        raise NotImplementedError

    def build_url(self, bind_host: str, session: PreviewSession) -> Optional[str]:
        preview_port = session.frontend_port or session.backend_port
        if not preview_port:
            return None
        return f"http://{bind_host}:{preview_port}/"
