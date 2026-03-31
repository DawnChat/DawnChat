from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Any


@dataclass(frozen=True)
class TemplateScaffoldRequest:
    template_id: str
    app_type: str
    plugin_id: str
    app_name: str
    app_description: str
    owner_email: str
    owner_user_id: str
    template_source: Path
    target_dir: Path
    template_version: str = ""


@dataclass(frozen=True)
class TemplateScaffoldResult:
    plugin_id: str
    app_type: str
    target_dir: Path


class TemplateScaffolder(ABC):
    text_extensions = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".vue", ".toml", ".mjs"}

    @property
    @abstractmethod
    def app_type(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def scaffold(self, request: TemplateScaffoldRequest) -> TemplateScaffoldResult:
        raise NotImplementedError

    @staticmethod
    def copy_template_tree(source_dir: Path, target_dir: Path) -> None:
        shutil.copytree(
            source_dir,
            target_dir,
            ignore=shutil.ignore_patterns(
                "node_modules",
                ".dawnchat-preview",
                "__pycache__",
                "*.pyc",
            ),
        )

    @staticmethod
    def load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def normalize_package_name(plugin_id: str) -> str:
        return plugin_id.replace(".", "-")

    def replace_plugin_id_references(self, target_dir: Path, old_plugin_id: str, new_plugin_id: str) -> None:
        for file_path in target_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.text_extensions:
                continue
            try:
                raw = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            if old_plugin_id in raw:
                file_path.write_text(raw.replace(old_plugin_id, new_plugin_id), encoding="utf-8")

    @staticmethod
    def rewrite_pyproject(
        pyproject_path: Path,
        *,
        package_name: str,
        description: str,
        version: str = "0.1.0",
    ) -> None:
        pyproject_text = pyproject_path.read_text(encoding="utf-8")
        pyproject_text = re.sub(
            r'(?m)^name\s*=\s*".*?"\s*$',
            f'name = "{package_name}"',
            pyproject_text,
        )
        pyproject_text = re.sub(
            r'(?m)^description\s*=\s*".*?"\s*$',
            f'description = "{description}"',
            pyproject_text,
        )
        pyproject_text = re.sub(
            r'(?m)^version\s*=\s*".*?"\s*$',
            f'version = "{version}"',
            pyproject_text,
        )
        pyproject_path.write_text(pyproject_text, encoding="utf-8")
