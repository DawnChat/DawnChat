"""
Generic HTTP downloader implementation.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict
import uuid

import httpx

from app.services.downloaders.base import BaseDownloader, DownloadProgress, DownloadRequest


class HttpDownloader(BaseDownloader):
    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._progress: Dict[str, DownloadProgress] = {}

    async def start(self, request: DownloadRequest) -> str:
        task_id = request.task_id or f"http_{uuid.uuid4().hex[:12]}"
        if task_id in self._tasks and not self._tasks[task_id].done():
            return task_id

        request.save_path.parent.mkdir(parents=True, exist_ok=True)
        self._progress[task_id] = DownloadProgress(task_id=task_id, status="downloading", progress=0.0)
        cancel_event = asyncio.Event()
        self._cancel_events[task_id] = cancel_event
        self._tasks[task_id] = asyncio.create_task(self._download(task_id, request, cancel_event))
        return task_id

    def get_progress(self, task_id: str) -> DownloadProgress:
        return self._progress.get(task_id, DownloadProgress(task_id=task_id, status="not_found"))

    async def cancel(self, task_id: str) -> bool:
        event = self._cancel_events.get(task_id)
        if event is None:
            return False
        event.set()
        task = self._tasks.get(task_id)
        if task and not task.done():
            await asyncio.wait({task}, timeout=2.0)
        return True

    async def _download(self, task_id: str, request: DownloadRequest, cancel_event: asyncio.Event) -> None:
        url = request.url
        save_path = request.save_path
        downloaded = 0
        headers: Dict[str, str] = {}
        mode = "wb"

        if request.resume and save_path.exists():
            downloaded = save_path.stat().st_size
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"
                mode = "ab"

        last_time = time.time()
        last_bytes = downloaded

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    # Resume safety:
                    # if server ignores Range and returns 200, restart from scratch (wb),
                    # otherwise appending would corrupt file contents.
                    if downloaded > 0 and resp.status_code != 206:
                        downloaded = 0
                        mode = "wb"
                    if downloaded > 0 and resp.status_code == 206:
                        range_start = self._resolve_content_range_start(resp.headers)
                        if range_start is None or range_start != save_path.stat().st_size:
                            raise RuntimeError("invalid_content_range_for_resume")
                    total_bytes = self._resolve_total_bytes(resp.headers, downloaded)
                    self._progress[task_id] = DownloadProgress(
                        task_id=task_id,
                        status="downloading",
                        progress=(downloaded / total_bytes * 100) if total_bytes else 0.0,
                        downloaded_bytes=downloaded,
                        total_bytes=total_bytes,
                    )

                    with save_path.open(mode) as f:
                        async for chunk in resp.aiter_bytes():
                            if cancel_event.is_set():
                                self._progress[task_id] = DownloadProgress(
                                    task_id=task_id,
                                    status="cancelled",
                                    progress=self._progress[task_id].progress,
                                    downloaded_bytes=downloaded,
                                    total_bytes=total_bytes,
                                )
                                return

                            if not chunk:
                                continue

                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            elapsed = max(now - last_time, 0.001)
                            if elapsed >= 0.5:
                                speed_bps = (downloaded - last_bytes) / elapsed
                                speed = _format_speed(speed_bps)
                                progress = (downloaded / total_bytes * 100) if total_bytes else 0.0
                                self._progress[task_id] = DownloadProgress(
                                    task_id=task_id,
                                    status="downloading",
                                    progress=progress,
                                    downloaded_bytes=downloaded,
                                    total_bytes=total_bytes,
                                    speed=speed,
                                )
                                last_time = now
                                last_bytes = downloaded

            final_total = self._progress[task_id].total_bytes or downloaded
            self._progress[task_id] = DownloadProgress(
                task_id=task_id,
                status="completed",
                progress=100.0,
                downloaded_bytes=downloaded,
                total_bytes=final_total,
            )
        except Exception as e:
            snapshot = self._progress.get(task_id) or DownloadProgress(task_id=task_id, status="failed")
            self._progress[task_id] = DownloadProgress(
                task_id=task_id,
                status="failed",
                progress=snapshot.progress,
                downloaded_bytes=snapshot.downloaded_bytes,
                total_bytes=snapshot.total_bytes,
                speed=snapshot.speed,
                error_message=str(e),
            )
        finally:
            self._tasks.pop(task_id, None)
            self._cancel_events.pop(task_id, None)

    @staticmethod
    def _resolve_total_bytes(headers: httpx.Headers, downloaded: int) -> int:
        content_range = headers.get("Content-Range")
        if content_range and "/" in content_range:
            tail = content_range.split("/")[-1].strip()
            if tail.isdigit():
                return int(tail)
        content_length = headers.get("Content-Length")
        if content_length and content_length.isdigit():
            return downloaded + int(content_length)
        return 0

    @staticmethod
    def _resolve_content_range_start(headers: httpx.Headers) -> int | None:
        content_range = headers.get("Content-Range")
        if not content_range:
            return None
        # Example: "bytes 123-456/789"
        try:
            unit_and_range = content_range.split(" ", 1)
            if len(unit_and_range) != 2:
                return None
            range_part = unit_and_range[1].split("/", 1)[0]
            start_part = range_part.split("-", 1)[0].strip()
            if not start_part.isdigit():
                return None
            return int(start_part)
        except Exception:
            return None


def _format_speed(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return ""
    if bytes_per_second >= 1024 * 1024:
        return f"{bytes_per_second / 1024 / 1024:.1f} MB/s"
    if bytes_per_second >= 1024:
        return f"{bytes_per_second / 1024:.1f} KB/s"
    return f"{bytes_per_second:.0f} B/s"
