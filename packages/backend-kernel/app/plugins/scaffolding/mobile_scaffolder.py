from __future__ import annotations

from .web_scaffolder import WebTemplateScaffolder


class MobileTemplateScaffolder(WebTemplateScaffolder):
    @property
    def app_type(self) -> str:
        return "mobile"
