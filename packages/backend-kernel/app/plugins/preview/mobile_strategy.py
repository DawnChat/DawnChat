from __future__ import annotations

from .web_strategy import WebPreviewStrategy


class MobilePreviewStrategy(WebPreviewStrategy):
    @property
    def app_type(self) -> str:
        return "mobile"
