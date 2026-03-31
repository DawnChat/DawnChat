"""
Playwright browser installer with smart fallback strategy.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Callable, Optional

from app.services.network_service import NetworkService
from app.utils.logger import app_logger as logger


class PlaywrightInstaller:
    """Install Playwright Chromium with provider-aware fallback hosts."""

    @classmethod
    async def install_chromium(
        cls,
        startup_start: float,
        elapsed_ms: Optional[Callable[[], int]] = None,
    ) -> bool:
        """
        Install Chromium for Playwright using host candidates.

        Returns:
            True if installed successfully, False otherwise.
        """
        if elapsed_ms is None:
            def _default_elapsed_ms() -> int:
                return int((time.time() - startup_start) * 1000)
            elapsed_ms = _default_elapsed_ms

        host_candidates = await NetworkService.resolve_playwright_hosts()
        install_ok = False

        for host in host_candidates:
            install_env = os.environ.copy()
            if host:
                install_env["PLAYWRIGHT_DOWNLOAD_HOST"] = host
            else:
                install_env.pop("PLAYWRIGHT_DOWNLOAD_HOST", None)

            logger.info(f"⏱️  [{elapsed_ms()}ms] 🔁 尝试 Playwright 下载源: {host or 'official'}")
            try:
                await asyncio.to_thread(
                    cls._run_playwright_install,
                    install_env,
                )
                await NetworkService.record_provider_success("playwright", host)
                install_ok = True
                logger.info(f"⏱️  [{elapsed_ms()}ms] ✅ Playwright 浏览器在线下载完成 (源: {host or 'official'})")
                break
            except Exception as install_error:
                logger.warning(
                    f"⏱️  [{elapsed_ms()}ms] ⚠️ Playwright 下载源失败: {host or 'official'} - {install_error}"
                )

        if not install_ok:
            logger.error(f"⏱️  [{elapsed_ms()}ms] ❌ Playwright 浏览器在线下载失败: all_playwright_hosts_failed")
        return install_ok

    @staticmethod
    def _run_playwright_install(install_env: dict[str, str]) -> None:
        import subprocess

        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            env=install_env,
        )
