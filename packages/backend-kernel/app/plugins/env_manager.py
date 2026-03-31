"""
DawnChat Plugin System - Environment Manager

Manages isolated Python environments for plugins using uv.
"""

import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import sys
from typing import Any, Optional

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("uv_env_manager")


class UVEnvManager:
    """
    Manages plugin virtual environments using uv.
    
    Features:
    - Creates venvs with --system-site-packages to inherit Host PBS dependencies
    - Installs plugin-specific dependencies not available in Host
    - Uses shared uv cache for efficient package reuse
    """
    
    def __init__(self):
        self._uv_binary: Optional[Path] = None
        self._pbs_python: Optional[Path] = None
        self._venvs_dir: Optional[Path] = None
        self._cache_dir: Optional[Path] = None
        self._initialized = False
        self._local_sdk_path: Optional[Path] = None

    def _resolve_local_sdk_path(self) -> Optional[Path]:
        if self._local_sdk_path is not None:
            return self._local_sdk_path
        candidates = [
            Config.PROJECT_ROOT / "sdk",
            Config.PROJECT_ROOT.parent / "dawnchat-plugins" / "sdk",
        ]
        for candidate in candidates:
            if candidate.exists():
                self._local_sdk_path = candidate
                return candidate
        self._local_sdk_path = None
        return None
    
    async def initialize(self) -> bool:
        """
        Initialize the environment manager.
        
        Returns:
            True if initialization succeeded
        """
        if self._initialized:
            return True
        
        try:
            # Get uv binary path
            self._uv_binary = Config.get_uv_binary()
            if not self._uv_binary or not self._uv_binary.exists():
                logger.error(f"uv binary not found at: {self._uv_binary}")
                return False
            
            # Get PBS Python path
            self._pbs_python = Config.get_pbs_python()
            if not self._pbs_python or not self._pbs_python.exists():
                # In development, fall back to system Python
                self._pbs_python = Path(sys.executable)
                logger.warning(f"PBS Python not found, using system Python: {self._pbs_python}")
            
            # Setup directories
            self._venvs_dir = Config.PLUGINS_VENV_DIR
            self._venvs_dir.mkdir(parents=True, exist_ok=True)
            
            self._cache_dir = Config.UV_CACHE_DIR
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            
            self._initialized = True
            logger.info(f"UVEnvManager initialized: uv={self._uv_binary}, python={self._pbs_python}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize UVEnvManager: {e}")
            return False
    
    def get_venv_path(self, plugin_id: str) -> Path:
        """Get the venv path for a plugin."""
        # Sanitize plugin_id for filesystem
        if self._venvs_dir is None:
            raise RuntimeError("UVEnvManager not initialized")
        safe_id = plugin_id.replace(".", "_").replace("/", "_")
        return self._venvs_dir / safe_id
    
    def get_venv_python(self, plugin_id: str) -> Path:
        """Get the Python executable path for a plugin's venv."""
        venv_path = self.get_venv_path(plugin_id)
        
        if platform.system() == "Windows":
            return venv_path / "Scripts" / "python.exe"
        else:
            return venv_path / "bin" / "python"
    
    def _venv_uses_system_site_packages(self, venv_path: Path) -> Optional[bool]:
        cfg_path = venv_path / "pyvenv.cfg"
        if not cfg_path.exists():
            return None
        try:
            for raw_line in cfg_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip().lower()
                if line.startswith("include-system-site-packages"):
                    value = line.split("=", 1)[-1].strip()
                    if value in {"true", "1", "yes"}:
                        return True
                    if value in {"false", "0", "no"}:
                        return False
            return None
        except Exception:
            return None

    def _ai_base_state_path(self) -> Path:
        return self.get_venv_path(Config.PLUGIN_AI_BASE_VENV_ID) / ".ai_base_state.json"

    def _compute_ai_base_fingerprint(self, requirements: list[str], python_executable: Path) -> str:
        payload = {
            "requirements": sorted(requirements),
            "python_executable": str(python_executable.resolve()),
            "uv_binary": str(self._uv_binary.resolve()) if self._uv_binary else "",
            "is_pbs_app": bool(Config.IS_PBS_APP),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _load_ai_base_state(self) -> Optional[dict[str, Any]]:
        state_path = self._ai_base_state_path()
        if not state_path.exists():
            return None
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _save_ai_base_state(self, fingerprint: str) -> None:
        state_path = self._ai_base_state_path()
        payload = {
            "fingerprint": fingerprint,
            "saved_at": int(asyncio.get_event_loop().time()),
        }
        try:
            state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save ai base state: %s", e)

    async def ensure_ai_base_venv(self, force: bool = False) -> Optional[Path]:
        if not Config.PLUGIN_AI_BASE_ENABLED:
            return None
        if not self._initialized:
            if not await self.initialize():
                return None
        if self._pbs_python is None:
            logger.error("UVEnvManager not initialized")
            return None

        requirements = list(Config.PLUGIN_AI_BASE_REQUIREMENTS or [])
        if not requirements:
            logger.info("ai_base_skipped_empty_requirements")
            return None

        ai_base_id = Config.PLUGIN_AI_BASE_VENV_ID
        ai_base_python = self.get_venv_python(ai_base_id)
        expected_fingerprint = self._compute_ai_base_fingerprint(requirements, self._pbs_python)
        current_state = self._load_ai_base_state()

        if (
            not force
            and ai_base_python.exists()
            and isinstance(current_state, dict)
            and str(current_state.get("fingerprint") or "") == expected_fingerprint
        ):
            logger.info("ai_base_reused id=%s", ai_base_id)
            return self.get_venv_path(ai_base_id)

        venv_path = await self.create_venv(
            ai_base_id,
            force=force or (current_state is not None),
            system_site_packages=False,
            python_executable=self._pbs_python,
        )
        if not venv_path:
            logger.error("ai_base_create_failed id=%s", ai_base_id)
            return None

        ok = await self.install_dependencies(ai_base_id, requirements, upgrade=True)
        if not ok:
            logger.error("ai_base_install_failed id=%s", ai_base_id)
            return None

        self._save_ai_base_state(expected_fingerprint)
        logger.info("ai_base_created id=%s requirements=%s", ai_base_id, len(requirements))
        return venv_path

    async def create_venv(
        self,
        plugin_id: str,
        force: bool = False,
        system_site_packages: bool = True,
        python_executable: Optional[Path] = None,
        trigger_mode: str = "unknown",
    ) -> Optional[Path]:
        """
        Create a virtual environment for a plugin.
        
        The venv inherits Host PBS site-packages via --system-site-packages.
        
        Args:
            plugin_id: The plugin identifier
            force: If True, recreate even if venv exists
        
        Returns:
            Path to the venv, or None if creation failed
        """
        if not self._initialized:
            if not await self.initialize():
                return None
        
        if self._uv_binary is None or self._pbs_python is None:
            logger.error("UVEnvManager not initialized")
            return None
        
        venv_path = self.get_venv_path(plugin_id)
        
        recreate_reason: Optional[str] = None

        # Check if venv already exists
        if venv_path.exists() and not force:
            current = self._venv_uses_system_site_packages(venv_path)
            if current is not None and current != system_site_packages:
                force = True
                recreate_reason = "system_site_packages_mismatch"
            else:
                logger.debug(f"Venv already exists for {plugin_id}: {venv_path}")
                return venv_path

        if venv_path.exists() and force:
            import shutil
            shutil.rmtree(venv_path)
            logger.info(
                "Removed existing venv for %s (trigger_mode=%s recreate_reason=%s requested_system_site_packages=%s)",
                plugin_id,
                trigger_mode,
                recreate_reason or "force",
                system_site_packages,
            )

        if venv_path.exists():
            logger.debug(f"Venv already exists for {plugin_id}: {venv_path}")
            return venv_path
            logger.debug(f"Venv already exists for {plugin_id}: {venv_path}")
            return venv_path
        
        # Remove existing venv if force=True
        try:
            # Create venv with system site-packages
            # This allows plugins to use Host PBS dependencies
            base_python = python_executable or self._pbs_python
            cmd = [
                str(self._uv_binary),
                "venv",
                "--python", str(base_python),
            ]
            if system_site_packages:
                cmd.append("--system-site-packages")
            cmd.append(
                str(venv_path),
            )
            
            env = self._get_uv_env()
            
            logger.info(
                "Creating venv for %s (trigger_mode=%s requested_system_site_packages=%s): %s",
                plugin_id,
                trigger_mode,
                system_site_packages,
                " ".join(cmd),
            )
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Failed to create venv for {plugin_id}: {stderr.decode()}")
                return None
            
            logger.info(f"Created venv for {plugin_id}: {venv_path}")
            return venv_path
            
        except Exception as e:
            logger.error(f"Exception creating venv for {plugin_id}: {e}")
            return None
    
    async def install_dependencies(
        self,
        plugin_id: str,
        requirements: list[str],
        *,
        upgrade: bool = False,
        force_reinstall: bool = False,
    ) -> bool:
        """
        Install dependencies for a plugin.
        
        uv will automatically:
        1. Check system site-packages (Host PBS) for existing packages
        2. Skip installation if version requirements are met
        3. Install missing packages from cache or network
        
        Args:
            plugin_id: The plugin identifier
            requirements: List of requirement strings (e.g., ["gradio>=4.0.0"])
        
        Returns:
            True if installation succeeded
        """
        if not self._initialized:
            if not await self.initialize():
                return False
        
        if self._uv_binary is None:
            logger.error("UVEnvManager not initialized")
            return False
        
        if not requirements:
            logger.debug(f"No dependencies to install for {plugin_id}")
            return True
        
        venv_path = self.get_venv_path(plugin_id)
        if not venv_path.exists():
            logger.error(f"Venv does not exist for {plugin_id}")
            return False
        
        venv_python = self.get_venv_python(plugin_id)
        
        try:
            # Use uv pip install with the venv's Python
            cmd = [
                str(self._uv_binary),
                "pip",
                "install",
                "--python", str(venv_python),
            ]
            if upgrade:
                cmd.append("--upgrade")
            if force_reinstall:
                cmd.append("--force-reinstall")
            
            # Inject local SDK path if available (Dev environment)
            if not Config.IS_PBS_APP:
                sdk_path = self._resolve_local_sdk_path()
                if sdk_path:
                    logger.info(f"Using local SDK for {plugin_id}: {sdk_path}")
                    cmd.extend(["-e", str(sdk_path)])
            
            cmd.extend(requirements)
            logger.info(f"Installing dependencies for {plugin_id}: {requirements}")
            logger.debug(f"uv cmd for {plugin_id}: {' '.join(cmd)}")

            ok = await self._run_uv_install_with_fallback(plugin_id, cmd)
            if not ok:
                return False

            logger.info(f"Dependencies installed for {plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Exception installing dependencies for {plugin_id}: {e}")
            return False
    
    async def install_from_pyproject(
        self,
        plugin_id: str,
        pyproject_path: Path,
    ) -> bool:
        """
        Install dependencies from a pyproject.toml file.
        
        Args:
            plugin_id: The plugin identifier
            pyproject_path: Path to the plugin's pyproject.toml
        
        Returns:
            True if installation succeeded
        """
        if not pyproject_path.exists():
            logger.warning(f"pyproject.toml not found for {plugin_id}: {pyproject_path}")
            return True  # No dependencies to install

        if self._uv_binary is None:
            logger.error("UVEnvManager not initialized")
            return False
        
        venv_python = self.get_venv_python(plugin_id)
        plugin_dir = pyproject_path.parent
        force_reinstall = self._deps_cache_force_reinstall()
        fingerprint = self._compute_deps_fingerprint(plugin_id, pyproject_path, venv_python)
        if force_reinstall:
            logger.info("deps_install_forced for %s", plugin_id)
        elif fingerprint and self._deps_cache_hit(plugin_id, fingerprint):
            logger.info("deps_install_skipped_cached for %s", plugin_id)
            return True
        else:
            logger.info("deps_install_required for %s", plugin_id)
        
        try:
            # Use uv pip install with the plugin directory
            # This will read pyproject.toml and install dependencies
            cmd = [
                str(self._uv_binary),
                "pip",
                "install",
                "--python", str(venv_python),
            ]
            
            # Inject local SDK path if available (Dev environment)
            if not Config.IS_PBS_APP:
                sdk_path = self._resolve_local_sdk_path()
                if sdk_path:
                    logger.info(f"Using local SDK for {plugin_id}: {sdk_path}")
                    cmd.extend(["-e", str(sdk_path)])
            
            cmd.extend(["-e", str(plugin_dir)])
            logger.info(f"Installing from pyproject.toml for {plugin_id}")

            ok, stderr_text = await self._run_uv_process(plugin_id, cmd, self._get_uv_env())
            if not ok:
                # Try installing just dependencies without editable install
                logger.warning(f"Editable install failed, trying sync: {stderr_text[:1200]}")
                ok = await self._install_deps_from_toml(plugin_id, pyproject_path)
                if not ok:
                    return False
            if fingerprint:
                self._save_deps_state(plugin_id, pyproject_path, fingerprint)
            logger.info(f"Installed from pyproject.toml for {plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Exception installing from pyproject.toml for {plugin_id}: {e}")
            return False
    
    async def _install_deps_from_toml(
        self,
        plugin_id: str,
        pyproject_path: Path,
    ) -> bool:
        try:
            deps = self._read_dependencies_from_pyproject(pyproject_path)
            if deps:
                ok = await self.install_dependencies(plugin_id, deps)
                if not ok:
                    return False
            return True
        except Exception as e:
            logger.error(f"Failed to parse pyproject.toml: {e}")
            return False

    def _read_dependencies_from_pyproject(self, pyproject_path: Path) -> list[str]:
        if not pyproject_path.exists():
            return []
        toml_loader = None
        try:
            toml_loader = importlib.import_module("tomllib")
        except ModuleNotFoundError:
            try:
                toml_loader = importlib.import_module("tomli")
            except ModuleNotFoundError:
                toml_loader = None
        deps: list[str] = []
        if toml_loader is not None:
            with open(pyproject_path, "rb") as f:
                data = toml_loader.load(f)
            deps = data.get("project", {}).get("dependencies", []) or []
            return deps if isinstance(deps, list) else []
        in_project = False
        in_deps = False
        buf: list[str] = []
        with open(pyproject_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_project = line == "[project]"
                    in_deps = False
                    continue
                if not in_project:
                    continue
                if not in_deps:
                    if line.startswith("dependencies") and "[" in line:
                        in_deps = True
                        after = line.split("[", 1)[1]
                        buf.append(after)
                        if "]" in after:
                            break
                    continue
                buf.append(line)
                if "]" in line:
                    break
        joined = "\n".join(buf)
        joined = joined.split("]", 1)[0]
        deps = re.findall(r"""["']([^"']+)["']""", joined)
        return deps

    def _parse_requirement(self, raw: str) -> tuple[Optional[str], Optional[str], bool]:
        base = raw.split(";", 1)[0].strip()
        if not base:
            return None, None, False
        match = re.match(r"^[A-Za-z0-9_.-]+", base)
        if not match:
            return None, None, False
        name = match.group(0).lower()
        rest = base[len(name):].strip()
        if rest.startswith("["):
            close = rest.find("]")
            if close != -1:
                rest = rest[close + 1 :].strip()
        has_spec = any(op in rest for op in ("==", ">=", "<=", "!=", ">", "<", "~="))
        return name, rest if rest else None, has_spec

    def _deps_cache_force_reinstall(self) -> bool:
        raw = str(os.getenv("DAWNCHAT_PLUGIN_FORCE_REINSTALL", "")).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _deps_state_path(self, plugin_id: str) -> Path:
        return self.get_venv_path(plugin_id) / ".deps_install_state.json"

    def _compute_deps_fingerprint(self, plugin_id: str, pyproject_path: Path, venv_python: Path) -> Optional[str]:
        try:
            pyproject_sha = hashlib.sha256(pyproject_path.read_bytes()).hexdigest()
        except Exception as e:
            logger.warning("Failed to hash pyproject for %s: %s", plugin_id, e)
            return None

        sdk_path = None
        if not Config.IS_PBS_APP:
            local_sdk = self._resolve_local_sdk_path()
            if local_sdk:
                sdk_path = str(local_sdk.resolve())

        payload = {
            "plugin_id": plugin_id,
            "pyproject_path": str(pyproject_path.resolve()),
            "pyproject_sha256": pyproject_sha,
            "venv_python": str(venv_python.resolve()),
            "uv_binary": str(self._uv_binary.resolve()) if self._uv_binary else "",
            "is_pbs_app": bool(Config.IS_PBS_APP),
            "local_sdk_path": sdk_path,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _load_deps_state(self, plugin_id: str) -> Optional[dict[str, Any]]:
        state_path = self._deps_state_path(plugin_id)
        if not state_path.exists():
            return None
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _save_deps_state(self, plugin_id: str, pyproject_path: Path, fingerprint: str) -> None:
        state_path = self._deps_state_path(plugin_id)
        payload = {
            "fingerprint": fingerprint,
            "plugin_id": plugin_id,
            "pyproject_path": str(pyproject_path.resolve()),
            "saved_at": int(asyncio.get_event_loop().time()),
        }
        try:
            state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save deps state for %s: %s", plugin_id, e)

    def _deps_cache_hit(self, plugin_id: str, fingerprint: str) -> bool:
        state = self._load_deps_state(plugin_id)
        if not state:
            return False
        return str(state.get("fingerprint") or "") == fingerprint

    @staticmethod
    def _has_explicit_index(cmd: list[str]) -> bool:
        for i, arg in enumerate(cmd):
            if arg in {"--index-url", "-i", "--extra-index-url"}:
                return True
            if arg.startswith("--index-url=") or arg.startswith("--extra-index-url="):
                return True
            if arg == "--" and i + 1 < len(cmd):
                break
        return False

    async def _run_uv_process(self, plugin_id: str, cmd: list[str], env: dict[str, str]) -> tuple[bool, str]:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        stdout_text = stdout.decode(errors="replace") if stdout else ""
        stderr_text = stderr.decode(errors="replace") if stderr else ""

        if process.returncode == 0:
            return True, stderr_text

        logger.error(
            "Failed to install dependencies for %s (code=%s)\nstdout:\n%s\nstderr:\n%s",
            plugin_id,
            process.returncode,
            stdout_text[:8000],
            stderr_text[:8000],
        )
        return False, stderr_text

    async def _run_uv_install_with_fallback(self, plugin_id: str, cmd: list[str]) -> bool:
        base_env = self._get_uv_env()
        if "--offline" in cmd:
            ok, _ = await self._run_uv_process(plugin_id, cmd, base_env)
            return ok

        if self._has_explicit_index(cmd) or base_env.get("UV_INDEX_URL"):
            ok, _ = await self._run_uv_process(plugin_id, cmd, base_env)
            return ok

        try:
            from app.services.network_service import NetworkService

            candidates = await NetworkService.resolve_pypi_index_candidates()
        except Exception as e:
            logger.warning("Failed to resolve PyPI candidates, fallback to direct install: %s", e)
            candidates = []

        if not candidates:
            ok, _ = await self._run_uv_process(plugin_id, cmd, base_env)
            return ok

        for index_url in candidates:
            attempt_env = dict(base_env)
            attempt_env["UV_INDEX_URL"] = index_url
            logger.info("Trying PyPI index for %s: %s", plugin_id, index_url)
            ok, _ = await self._run_uv_process(plugin_id, cmd, attempt_env)
            if ok:
                try:
                    from app.services.network_service import NetworkService

                    await NetworkService.record_provider_success("pypi", index_url)
                except Exception:
                    pass
                return True

        return False
    
    async def delete_venv(self, plugin_id: str) -> bool:
        """Delete a plugin's virtual environment."""
        venv_path = self.get_venv_path(plugin_id)
        
        if not venv_path.exists():
            return True
        
        try:
            import shutil
            shutil.rmtree(venv_path)
            logger.info(f"Deleted venv for {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete venv for {plugin_id}: {e}")
            return False
    
    def _get_uv_env(self) -> dict[str, str]:
        """Get environment variables for uv commands."""
        env = os.environ.copy()
        
        # Set uv cache directory
        if self._cache_dir:
            env["UV_CACHE_DIR"] = str(self._cache_dir)
        
        # Disable uv's Python discovery to use our specified Python
        env["UV_PYTHON_PREFERENCE"] = "only-system"

        pypi_mirror = env.get("PYPI_MIRROR")
        if pypi_mirror and not env.get("UV_INDEX_URL"):
            env["UV_INDEX_URL"] = pypi_mirror
        
        return env


# Singleton instance
_env_manager: Optional[UVEnvManager] = None


def get_env_manager() -> UVEnvManager:
    """Get the global UVEnvManager instance."""
    global _env_manager
    if _env_manager is None:
        _env_manager = UVEnvManager()
    return _env_manager
