"""
Downloader abstractions for package/model asset fetching.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol

TERMINAL_DOWNLOAD_STATUSES = {"completed", "failed", "cancelled", "not_found"}


@dataclass
class DownloadRequest:
    url: str
    save_path: Path
    task_id: Optional[str] = None
    use_mirror: Optional[bool] = None
    resume: bool = True


@dataclass
class DownloadProgress:
    task_id: str
    status: str
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: str = ""
    error_message: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_DOWNLOAD_STATUSES


class Downloader(Protocol):
    async def start(self, request: DownloadRequest) -> str:
        ...

    def get_progress(self, task_id: str) -> DownloadProgress:
        ...

    async def cancel(self, task_id: str) -> bool:
        ...

    async def wait(
        self,
        task_id: str,
        *,
        timeout_s: Optional[float] = None,
        poll_interval_s: float = 0.5,
        on_progress: Optional[Callable[[DownloadProgress], Awaitable[None] | None]] = None,
    ) -> DownloadProgress:
        ...


class BaseDownloader:
    def get_progress(self, task_id: str) -> DownloadProgress:
        raise NotImplementedError

    async def wait(
        self,
        task_id: str,
        *,
        timeout_s: Optional[float] = None,
        poll_interval_s: float = 0.5,
        on_progress: Optional[Callable[[DownloadProgress], Awaitable[None] | None]] = None,
    ) -> DownloadProgress:
        started = asyncio.get_running_loop().time()
        while True:
            progress = self.get_progress(task_id)
            if on_progress:
                callback_result = on_progress(progress)
                if asyncio.iscoroutine(callback_result):
                    await callback_result

            if progress.is_terminal:
                return progress

            if timeout_s is not None:
                elapsed = asyncio.get_running_loop().time() - started
                if elapsed >= timeout_s:
                    return DownloadProgress(
                        task_id=task_id,
                        status="failed",
                        progress=progress.progress,
                        downloaded_bytes=progress.downloaded_bytes,
                        total_bytes=progress.total_bytes,
                        speed=progress.speed,
                        error_message="download_wait_timeout",
                    )

            await asyncio.sleep(max(poll_interval_s, 0.2))
