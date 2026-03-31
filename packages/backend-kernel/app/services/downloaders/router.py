"""
Route download requests to concrete downloader implementations by URL host.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.services.downloaders.base import Downloader
from app.services.downloaders.github_downloader import GitHubDownloader
from app.services.downloaders.http_downloader import HttpDownloader


class DownloadRouter:
    def __init__(self) -> None:
        self._github = GitHubDownloader()
        self._http = HttpDownloader()

    def route(self, url: str) -> Downloader:
        host = (urlparse(url).hostname or "").lower()
        if self._is_github_host(host):
            return self._github
        return self._http

    @staticmethod
    def _is_github_host(host: str) -> bool:
        if not host:
            return False
        github_hosts = {
            "github.com",
            "raw.githubusercontent.com",
            "objects.githubusercontent.com",
            "githubusercontent.com",
            "github-releases.githubusercontent.com",
        }
        if host in github_hosts:
            return True
        return host.endswith(".github.com") or host.endswith(".githubusercontent.com")


_download_router: DownloadRouter | None = None


def get_download_router() -> DownloadRouter:
    global _download_router
    if _download_router is None:
        _download_router = DownloadRouter()
    return _download_router
