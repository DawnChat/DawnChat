"""
GitHub-backed downloader adapter.
"""

from __future__ import annotations

from app.services.downloaders.base import BaseDownloader, DownloadProgress, DownloadRequest
from app.services.github_download import get_github_download_manager


class GitHubDownloader(BaseDownloader):
    async def start(self, request: DownloadRequest) -> str:
        manager = get_github_download_manager()
        result = await manager.start_download(
            url=request.url,
            save_path=request.save_path,
            task_id=request.task_id,
            use_mirror=request.use_mirror,
            resume=request.resume,
        )
        task_id = str(result.get("task_id") or request.task_id or "")
        if not task_id:
            raise RuntimeError("github_downloader_missing_task_id")
        return task_id

    def get_progress(self, task_id: str) -> DownloadProgress:
        manager = get_github_download_manager()
        raw = manager.get_progress(task_id)
        return DownloadProgress(
            task_id=task_id,
            status=str(raw.get("status") or "not_found"),
            progress=float(raw.get("progress") or 0.0),
            downloaded_bytes=int(raw.get("downloaded_bytes") or 0),
            total_bytes=int(raw.get("total_bytes") or 0),
            speed=str(raw.get("speed") or ""),
            error_message=raw.get("error_message"),
        )

    async def cancel(self, task_id: str) -> bool:
        manager = get_github_download_manager()
        result = await manager.request_cancel(task_id)
        return str(result.get("status")) == "cancelled"
