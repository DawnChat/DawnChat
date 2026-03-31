from __future__ import annotations

from .base import PreviewStrategy
from .desktop_strategy import DesktopPreviewStrategy
from .mobile_strategy import MobilePreviewStrategy
from .web_strategy import WebPreviewStrategy


class PreviewStrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, PreviewStrategy] = {
            "desktop": DesktopPreviewStrategy(),
            "web": WebPreviewStrategy(),
            "mobile": MobilePreviewStrategy(),
        }

    def get(self, app_type: str) -> PreviewStrategy:
        normalized = str(app_type or "desktop").strip().lower() or "desktop"
        return self._strategies.get(normalized, self._strategies["desktop"])
