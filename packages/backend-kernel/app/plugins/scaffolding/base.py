from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from app.config import Config


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
    def _copy_filtered_tree(source_dir: Path, target_dir: Path) -> None:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(
            source_dir,
            target_dir,
            ignore=shutil.ignore_patterns(
                "node_modules",
                ".dawnchat-preview",
                "__pycache__",
                "*.pyc",
                ".pytest_cache",
            ),
        )

    @staticmethod
    def _copy_dist_ready_package(source_dir: Path, target_dir: Path) -> None:
        missing = Config.get_assistant_sdk_missing_files(source_dir)
        if missing:
            formatted = ", ".join(str(path) for path in missing)
            raise RuntimeError(f"Assistant SDK dist package is incomplete: {formatted}")

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(source_dir / "package.json", target_dir / "package.json")
        readme_path = source_dir / "README.md"
        if readme_path.exists():
            shutil.copy2(readme_path, target_dir / "README.md")
        dist_dir = source_dir / "dist"
        if dist_dir.exists():
            shutil.copytree(dist_dir, target_dir / "dist")

    @staticmethod
    def _format_file_dependency_target(target_dir: Path, *, relative_to: Path | None = None) -> str:
        if relative_to is not None:
            relative_path = Path(os.path.relpath(target_dir, relative_to))
            return f"file:{relative_path.as_posix()}"
        return f"file:{target_dir.resolve().as_posix()}"

    @classmethod
    def _is_source_assistant_sdk_dependency(
        cls,
        version: str,
        *,
        package_name: str,
        package_json_path: Path,
    ) -> bool:
        normalized = str(version or "").strip()
        if normalized == "workspace:*":
            return True
        if not normalized.startswith("file:"):
            return False
        raw_target = normalized[5:].strip()
        if not raw_target:
            return False
        target_path = Path(raw_target)
        if not target_path.is_absolute():
            target_path = (package_json_path.parent / target_path).resolve()
        package_dirname = Config.ASSISTANT_SDK_PACKAGE_DIRS.get(package_name)
        if not package_dirname:
            return False
        assistant_sdk_root = (Config.PROJECT_ROOT / "dawnchat-plugins" / Config.ASSISTANT_SDK_DIRNAME).resolve()
        expected_target = (assistant_sdk_root / package_dirname).resolve()
        return target_path == expected_target

    @classmethod
    def rewrite_frontend_sdk_dependencies(
        cls,
        package_json_path: Path,
        *,
        plugin_root: Path,
    ) -> bool:
        if not package_json_path.exists():
            return False

        package_json = cls.load_json(package_json_path)
        matched: dict[str, str] = {}
        for section in ("dependencies", "devDependencies"):
            deps = package_json.get(section)
            if not isinstance(deps, dict):
                continue
            for package_name in Config.ASSISTANT_SDK_PACKAGE_DIRS:
                version = str(deps.get(package_name) or "").strip()
                if cls._is_source_assistant_sdk_dependency(
                    version,
                    package_name=package_name,
                    package_json_path=package_json_path,
                ):
                    matched[package_name] = section
        if not matched:
            return False

        runtime_mode = Config.get_runtime_distribution_mode()
        sdk_mapping = Config.get_assistant_sdk_package_dirs(
            allow_dev_fallback=runtime_mode == "dev",
        )
        missing = [
            f"{package_name} -> {sdk_mapping[package_name]}"
            for package_name in matched
            if Config.get_assistant_sdk_missing_files(sdk_mapping[package_name])
        ]
        if missing:
            raise RuntimeError(
                "Assistant SDK dist-ready bundle missing for scaffold rewrite: "
                + ", ".join(missing)
            )

        relative_base = package_json_path.parent
        if runtime_mode == "release":
            vendor_root = plugin_root / "vendor" / Config.ASSISTANT_SDK_DIRNAME
            for package_name, package_dirname in Config.ASSISTANT_SDK_PACKAGE_DIRS.items():
                if package_name not in matched:
                    continue
                vendor_dir = vendor_root / package_dirname
                cls._copy_dist_ready_package(sdk_mapping[package_name], vendor_dir)
                section = matched[package_name]
                deps = package_json.get(section)
                if isinstance(deps, dict):
                    deps[package_name] = cls._format_file_dependency_target(
                        vendor_dir,
                        relative_to=relative_base,
                    )
        else:
            for package_name, section in matched.items():
                deps = package_json.get(section)
                if isinstance(deps, dict):
                    deps[package_name] = cls._format_file_dependency_target(
                        sdk_mapping[package_name],
                    )

        cls.write_json(package_json_path, package_json)
        return True

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
