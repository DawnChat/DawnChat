from __future__ import annotations

from ..env_manager import UVEnvManager
from .base import TemplateScaffolder
from .desktop_scaffolder import DesktopTemplateScaffolder
from .mobile_scaffolder import MobileTemplateScaffolder
from .web_scaffolder import WebTemplateScaffolder


class TemplateScaffolderRegistry:
    def __init__(self, env_manager: UVEnvManager) -> None:
        self._scaffolders: dict[str, TemplateScaffolder] = {
            "desktop": DesktopTemplateScaffolder(),
            "web": WebTemplateScaffolder(),
            "mobile": MobileTemplateScaffolder(),
        }

    def get(self, app_type: str) -> TemplateScaffolder:
        normalized = str(app_type or "desktop").strip().lower() or "desktop"
        scaffolder = self._scaffolders.get(normalized)
        if scaffolder is None:
            raise ValueError(f"Unsupported app type: {app_type}")
        return scaffolder
