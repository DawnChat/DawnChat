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

        package_json = TemplateScaffolder.load_json(source_dir / "package.json")
        sanitized_package_json = TemplateScaffolder._sanitize_dist_package_json(
            package_json,
            target_dir=target_dir,
        )
        TemplateScaffolder.write_json(target_dir / "package.json", sanitized_package_json)
        readme_path = source_dir / "README.md"
        if readme_path.exists():
            shutil.copy2(readme_path, target_dir / "README.md")
        dist_dir = source_dir / "dist"
        if dist_dir.exists():
            shutil.copytree(dist_dir, target_dir / "dist")
        else:
            for path in Config.get_assistant_sdk_required_files(source_dir):
                if path.name == "package.json" or not path.is_file():
                    continue
                rel = path.relative_to(source_dir)
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)

    @staticmethod
    def _format_file_dependency_target(target_dir: Path, *, relative_to: Path | None = None) -> str:
        if relative_to is not None:
            relative_path = Path(os.path.relpath(target_dir, relative_to))
            return f"file:{relative_path.as_posix()}"
        return f"file:{target_dir.resolve().as_posix()}"

    @classmethod
    def _iter_assistant_sdk_dependency_sections(cls) -> tuple[str, ...]:
        return ("dependencies", "peerDependencies", "optionalDependencies", "devDependencies")

    @classmethod
    def _collect_internal_assistant_sdk_dependencies(cls, package_json: dict[str, Any]) -> set[str]:
        internal_dependencies: set[str] = set()
        for section in cls._iter_assistant_sdk_dependency_sections():
            deps = package_json.get(section)
            if not isinstance(deps, dict):
                continue
            for package_name in deps:
                if package_name in Config.ASSISTANT_SDK_PACKAGE_DIRS:
                    internal_dependencies.add(package_name)
        return internal_dependencies

    @classmethod
    def _collect_internal_frontend_sdk_dependencies(cls, package_json: dict[str, Any]) -> set[str]:
        internal_dependencies: set[str] = set()
        for section in cls._iter_assistant_sdk_dependency_sections():
            deps = package_json.get(section)
            if not isinstance(deps, dict):
                continue
            for package_name in deps:
                if (
                    package_name in Config.ASSISTANT_SDK_PACKAGE_DIRS
                    or package_name in Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS
                ):
                    internal_dependencies.add(package_name)
        return internal_dependencies

    @classmethod
    def _sanitize_dist_package_json(
        cls,
        package_json: dict[str, Any],
        *,
        target_dir: Path,
    ) -> dict[str, Any]:
        sanitized = json.loads(json.dumps(package_json))
        sanitized.pop("scripts", None)
        sanitized.pop("devDependencies", None)

        runtime_dependencies = sanitized.get("dependencies")
        if not isinstance(runtime_dependencies, dict):
            runtime_dependencies = {}
        sanitized["dependencies"] = runtime_dependencies

        for section in cls._iter_assistant_sdk_dependency_sections():
            deps = package_json.get(section)
            if not isinstance(deps, dict):
                continue
            for package_name in cls._collect_internal_assistant_sdk_dependencies({section: deps}):
                package_dirname = Config.ASSISTANT_SDK_PACKAGE_DIRS[package_name]
                runtime_dependencies[package_name] = cls._format_file_dependency_target(
                    target_dir.parent / package_dirname,
                    relative_to=target_dir,
                )

        for section in ("peerDependencies", "optionalDependencies"):
            deps = sanitized.get(section)
            if not isinstance(deps, dict):
                continue
            for package_name in list(deps):
                if (
                    package_name in Config.ASSISTANT_SDK_PACKAGE_DIRS
                    or package_name in Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS
                ):
                    deps.pop(package_name, None)
            if not deps:
                sanitized.pop(section, None)

        cls._validate_sanitized_dist_package_json(sanitized)
        return sanitized

    @classmethod
    def _validate_sanitized_dist_package_json(cls, package_json: dict[str, Any]) -> None:
        for section in ("dependencies", "peerDependencies", "optionalDependencies"):
            deps = package_json.get(section)
            if not isinstance(deps, dict):
                continue
            for package_name, version in deps.items():
                normalized = str(version or "").strip()
                if normalized == "workspace:*":
                    raise RuntimeError(
                        f"Assistant SDK dist package still contains workspace dependency: {package_name}"
                    )
                if normalized.startswith("file:") and (
                    package_name not in Config.ASSISTANT_SDK_PACKAGE_DIRS
                    and package_name not in Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS
                ):
                    raise RuntimeError(
                        f"Assistant SDK dist package contains unsupported local dependency: {package_name} -> {normalized}"
                    )

    @classmethod
    def _collect_transitive_assistant_sdk_packages(
        cls,
        root_packages: set[str],
        *,
        sdk_mapping: dict[str, Path],
    ) -> set[str]:
        collected = set(root_packages)
        pending = list(root_packages)
        while pending:
            package_name = pending.pop()
            package_dir = sdk_mapping.get(package_name)
            if package_dir is None:
                continue
            package_json_path = package_dir / "package.json"
            if not package_json_path.exists():
                continue
            internal_dependencies = cls._collect_internal_frontend_sdk_dependencies(
                cls.load_json(package_json_path)
            )
            for dependency_name in internal_dependencies:
                if dependency_name not in collected:
                    collected.add(dependency_name)
                    pending.append(dependency_name)
        return collected

    @classmethod
    def _expected_monorepo_frontend_package_dir(cls, package_name: str) -> Path | None:
        if package_name in Config.ASSISTANT_SDK_PACKAGE_DIRS:
            dirname = Config.ASSISTANT_SDK_PACKAGE_DIRS[package_name]
            return (
                Config.PROJECT_ROOT / "dawnchat-plugins" / Config.ASSISTANT_SDK_DIRNAME / dirname
            ).resolve()
        if package_name in Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS:
            dirname = Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS[package_name]
            return (
                Config.PROJECT_ROOT
                / "dawnchat-plugins"
                / Config.CAPACITOR_PLUGINS_SDK_DIRNAME
                / dirname
            ).resolve()
        return None

    @classmethod
    def _is_source_frontend_sdk_dependency(
        cls,
        version: str,
        *,
        package_name: str,
        package_json_path: Path,
    ) -> bool:
        expected = cls._expected_monorepo_frontend_package_dir(package_name)
        if expected is None:
            return False
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
        return target_path == expected

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
                if cls._is_source_frontend_sdk_dependency(
                    version,
                    package_name=package_name,
                    package_json_path=package_json_path,
                ):
                    matched[package_name] = section
            for package_name in Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS:
                version = str(deps.get(package_name) or "").strip()
                if cls._is_source_frontend_sdk_dependency(
                    version,
                    package_name=package_name,
                    package_json_path=package_json_path,
                ):
                    matched[package_name] = section
        if not matched:
            return False

        runtime_mode = Config.get_runtime_distribution_mode()
        allow_dev = runtime_mode == "dev"
        assistant_mapping = Config.get_assistant_sdk_package_dirs(allow_dev_fallback=allow_dev)
        capacitor_mapping = Config.get_capacitor_plugins_sdk_package_dirs(
            allow_dev_fallback=allow_dev,
        )
        sdk_mapping: dict[str, Path] = {**assistant_mapping, **capacitor_mapping}

        missing: list[str] = []
        for package_name in matched:
            path = sdk_mapping.get(package_name)
            if path is None:
                missing.append(f"{package_name} -> <unmapped>")
                continue
            if Config.get_assistant_sdk_missing_files(path):
                missing.append(f"{package_name} -> {path}")
        if missing:
            raise RuntimeError(
                "Assistant/Capacitor SDK dist-ready bundle missing for scaffold rewrite: "
                + ", ".join(missing)
            )

        relative_base = package_json_path.parent
        if runtime_mode == "release":
            packages_to_vendor = cls._collect_transitive_assistant_sdk_packages(
                set(matched),
                sdk_mapping=sdk_mapping,
            )
            for package_name in sorted(packages_to_vendor):
                if package_name in Config.ASSISTANT_SDK_PACKAGE_DIRS:
                    vendor_dir = (
                        plugin_root / "vendor" / Config.ASSISTANT_SDK_DIRNAME
                    ) / Config.ASSISTANT_SDK_PACKAGE_DIRS[package_name]
                elif package_name in Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS:
                    vendor_dir = (
                        plugin_root / "vendor" / Config.CAPACITOR_PLUGINS_SDK_DIRNAME
                    ) / Config.CAPACITOR_PLUGINS_SDK_PACKAGE_DIRS[package_name]
                else:
                    continue
                cls._copy_dist_ready_package(sdk_mapping[package_name], vendor_dir)
                deps_section = matched.get(package_name)
                if deps_section is not None:
                    deps = package_json.get(deps_section)
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
    def _is_monorepo_assistant_vite_script(val: str) -> bool:
        v = val.strip()
        if "assistant-workspace" not in v:
            return False
        if "official-plugins" in v:
            return True
        if "bun run template:" in v:
            return True
        return False

    @classmethod
    def rewrite_monorepo_assistant_vite_scripts(cls, package_json_path: Path) -> bool:
        """官方 assistant 模板在仓库内用 assistant-workspace 为 cwd 调 Vite；拷贝到用户插件后需改回在 web-src 内直接执行。"""
        if not package_json_path.exists():
            return False
        package_json = cls.load_json(package_json_path)
        scripts = package_json.get("scripts")
        if not isinstance(scripts, dict):
            return False
        changed = False
        for key in ("dev", "build", "preview"):
            raw = scripts.get(key)
            if not isinstance(raw, str):
                continue
            val = raw.strip()
            if not cls._is_monorepo_assistant_vite_script(val):
                continue
            if key == "dev":
                scripts[key] = "bun x vite --configLoader runner"
                changed = True
            elif key == "preview":
                scripts[key] = "bun x vite preview --configLoader runner"
                changed = True
            elif key == "build":
                is_mobile = val.startswith("vue-tsc -b &&") or "template:mobile:build" in val
                if is_mobile:
                    scripts[key] = "vue-tsc -b && bun x vite build --configLoader runner"
                else:
                    scripts[key] = "bun x vite build --configLoader runner"
                changed = True
        if changed:
            cls.write_json(package_json_path, package_json)
        return changed

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
