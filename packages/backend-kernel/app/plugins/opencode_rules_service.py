"""
Shared OpenCode rules sync service.

Downloads and manages versioned shared rules referenced by plugins.json.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any, Optional
from zipfile import ZipFile

from app.config import Config
from app.services.downloaders import DownloadRequest, get_download_router
from app.utils.logger import get_logger

from .market_service import get_plugin_market_service

logger = get_logger("opencode_rules_service")

RULES_META_KEY = "shared_opencode_rules"


class OpenCodeRulesService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def _load_state(self) -> dict[str, Any]:
        path = Config.PLUGIN_OPENCODE_RULES_STATE
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            logger.warning("Failed to load OpenCode rules state: %s", exc)
            return {}

    def _save_state(self, payload: dict[str, Any]) -> None:
        try:
            Config.PLUGIN_OPENCODE_RULES_STATE.parent.mkdir(parents=True, exist_ok=True)
            Config.PLUGIN_OPENCODE_RULES_STATE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist OpenCode rules state: %s", exc)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _resolve_current_dir(self, state: Optional[dict[str, Any]] = None) -> Optional[Path]:
        current_link = Config.PLUGIN_OPENCODE_RULES_CURRENT_LINK
        try:
            if current_link.exists():
                resolved = current_link.resolve()
                if resolved.exists() and resolved.is_dir():
                    return resolved
        except Exception:
            pass
        local_state = state or self._load_state()
        current_version = str(local_state.get("current_version") or "").strip()
        if not current_version:
            return None
        version_dir = Config.PLUGIN_OPENCODE_RULES_VERSIONS_DIR / current_version
        if version_dir.exists() and version_dir.is_dir():
            return version_dir
        return None

    def _switch_current_version(self, version: str) -> Path:
        target_dir = Config.PLUGIN_OPENCODE_RULES_VERSIONS_DIR / version
        if not target_dir.exists() or not target_dir.is_dir():
            raise FileNotFoundError(f"OpenCode shared rules version missing: {target_dir}")

        current_link = Config.PLUGIN_OPENCODE_RULES_CURRENT_LINK
        try:
            if current_link.exists() or current_link.is_symlink():
                if current_link.is_symlink() or current_link.is_file():
                    current_link.unlink(missing_ok=True)
                else:
                    shutil.rmtree(current_link)
            # Prefer symlink for atomic switch.
            current_link.symlink_to(target_dir, target_is_directory=True)
        except Exception:
            # Fallback for systems where symlink is unavailable.
            if current_link.exists():
                shutil.rmtree(current_link)
            shutil.copytree(target_dir, current_link)

        state = self._load_state()
        versions = state.get("versions")
        if not isinstance(versions, list):
            versions = []
        if version not in versions:
            versions.append(version)
        state.update(
            {
                "current_version": version,
                "versions": sorted(set(str(item) for item in versions if str(item).strip())),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save_state(state)
        return target_dir

    async def _download_rules_package(self, version: str, package_url: str) -> Path:
        out_name = f"opencode-rules-{version}.zip"
        out_path = Config.PLUGIN_OPENCODE_RULES_CACHE_DIR / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        task_id = f"opencode_rules_{version.replace('.', '_')}"
        downloader = get_download_router().route(package_url)
        await downloader.start(
            DownloadRequest(
                url=package_url,
                save_path=out_path,
                task_id=task_id,
                use_mirror=None,
                resume=True,
            )
        )
        progress = await downloader.wait(task_id, timeout_s=600, poll_interval_s=0.5)
        if progress.status != "completed":
            reason = progress.error_message or progress.status
            raise RuntimeError(f"Download shared OpenCode rules failed: {reason}")
        return out_path

    def _extract_to_version_dir(self, package_path: Path, version: str) -> Path:
        target_dir = Config.PLUGIN_OPENCODE_RULES_VERSIONS_DIR / version
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=f"dawnchat-opencode-rules-{version}-") as tmp:
            tmp_root = Path(tmp)
            with ZipFile(package_path, "r") as zf:
                zf.extractall(tmp_root)
            shutil.copytree(tmp_root, target_dir)
        return target_dir

    @staticmethod
    def _read_manifest_version(rules_dir: Path) -> Optional[str]:
        manifest_path = rules_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            version = str(payload.get("version") or "").strip()
            return version or None
        except Exception:
            return None

    def _seed_from_bundled_rules_if_missing(self) -> Optional[dict[str, Any]]:
        current_dir = self._resolve_current_dir()
        if current_dir:
            return None

        bundled_dir = Config.get_bundled_opencode_rules_dir()
        if not bundled_dir:
            return None

        version = self._read_manifest_version(bundled_dir)
        if not version:
            logger.warning("Bundled OpenCode rules missing manifest version: %s", bundled_dir)
            return None

        target_dir = Config.PLUGIN_OPENCODE_RULES_VERSIONS_DIR / version
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled_dir, target_dir)
        switched = self._switch_current_version(version)
        logger.info("OpenCode rules seeded from bundled copy version=%s source=%s", version, bundled_dir)
        return {
            "enabled": True,
            "updated": True,
            "version": version,
            "source": "bundled",
            "current_dir": str(switched),
        }

    async def ensure_rules_ready(self, force_refresh: bool = False) -> dict[str, Any]:
        async with self._lock:
            seeded = self._seed_from_bundled_rules_if_missing()
            try:
                market_data = await get_plugin_market_service().fetch_index(force=force_refresh)
            except Exception as exc:
                # Network failure should not break startup if local/bundled rules are available.
                logger.warning("OpenCode rules market fetch failed, fallback to local rules: %s", exc)
                current_dir = self._resolve_current_dir()
                if current_dir:
                    state = self._load_state()
                    return {
                        "enabled": True,
                        "updated": bool(seeded),
                        "version": str(state.get("current_version") or ""),
                        "source": "local-fallback",
                        "reason": "market_fetch_failed",
                        "current_dir": str(current_dir),
                    }
                raise
            meta = market_data.get(RULES_META_KEY)
            if not isinstance(meta, dict):
                current_dir = self._resolve_current_dir()
                return {
                    "enabled": bool(current_dir),
                    "reason": "no_shared_rules_meta",
                    "current_version": self._load_state().get("current_version"),
                    "source": "bundled" if seeded else "none",
                    "current_dir": str(current_dir) if current_dir else None,
                }

            version = str(meta.get("version") or "").strip()
            package = meta.get("package") if isinstance(meta.get("package"), dict) else {}
            package_url = str((package or {}).get("url") or "").strip()
            package_sha256 = str((package or {}).get("sha256") or "").strip().lower()
            if not version or not package_url:
                raise RuntimeError("Invalid shared_opencode_rules metadata: version/url missing")

            state = self._load_state()
            current_version = str(state.get("current_version") or "").strip()
            version_dir = Config.PLUGIN_OPENCODE_RULES_VERSIONS_DIR / version
            if current_version == version and version_dir.exists():
                current_dir = self._resolve_current_dir(state)
                return {
                    "enabled": True,
                    "updated": False,
                    "version": version,
                    "current_dir": str(current_dir) if current_dir else str(version_dir),
                }

            package_path = await self._download_rules_package(version, package_url)
            actual_sha256 = self._sha256_file(package_path).lower()
            if package_sha256 and actual_sha256 != package_sha256:
                raise RuntimeError(
                    f"Shared rules checksum mismatch: expected={package_sha256} actual={actual_sha256}"
                )
            self._extract_to_version_dir(package_path, version)
            current_dir = self._switch_current_version(version)
            logger.info("OpenCode shared rules switched to version=%s", version)
            return {
                "enabled": True,
                "updated": True,
                "version": version,
                "source": "remote",
                "current_dir": str(current_dir),
            }

    async def ensure_ready(self, force_refresh: bool = False) -> dict[str, Any]:
        return await self.ensure_rules_ready(force_refresh=force_refresh)

    def get_current_dir(self) -> Optional[str]:
        current_dir = self._resolve_current_dir()
        if not current_dir:
            return None
        return str(current_dir)

    def get_status(self) -> dict[str, Any]:
        state = self._load_state()
        current_dir = self._resolve_current_dir(state)
        return {
            "enabled": bool(current_dir),
            "current_version": state.get("current_version"),
            "versions": state.get("versions", []),
            "updated_at": state.get("updated_at"),
            "current_dir": str(current_dir) if current_dir else None,
        }

    def rollback(self, version: str) -> dict[str, Any]:
        with_version = str(version or "").strip()
        if not with_version:
            raise ValueError("version is required")
        target = self._switch_current_version(with_version)
        logger.info("OpenCode shared rules rollback to version=%s", with_version)
        return {
            "enabled": True,
            "current_version": with_version,
            "current_dir": str(target),
        }


_opencode_rules_service: Optional[OpenCodeRulesService] = None


def get_opencode_rules_service() -> OpenCodeRulesService:
    global _opencode_rules_service
    if _opencode_rules_service is None:
        _opencode_rules_service = OpenCodeRulesService()
    return _opencode_rules_service

