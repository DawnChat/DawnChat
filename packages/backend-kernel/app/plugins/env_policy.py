"""
Plugin environment policy resolver.

Centralizes env decision for install/runtime/preview:
- runtime.isolated controls hard isolation
- AI base reuse is auto-detected from plugin dependencies
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

from app.config import Config
from app.utils.logger import get_logger

from .env_manager import UVEnvManager

logger = get_logger("plugin_env_policy")


@dataclass(frozen=True)
class EnvDecision:
    python_executable: Optional[Path]
    system_site_packages: bool
    use_ai_base: bool
    reason: str


def _parse_requirement(raw: str) -> tuple[Optional[str], Optional[str]]:
    base = raw.split(";", 1)[0].strip()
    if not base:
        return None, None

    try:
        from packaging.requirements import Requirement

        req = Requirement(base)
        spec = str(req.specifier).strip() or None
        return req.name.lower(), spec
    except Exception:
        match = re.match(r"^[A-Za-z0-9_.-]+", base)
        if not match:
            return None, None
        name = match.group(0).lower()
        rest = base[len(name) :].strip()
        if rest.startswith("["):
            close = rest.find("]")
            if close != -1:
                rest = rest[close + 1 :].strip()
        return name, rest or None


def _exact_versions(spec: Optional[str]) -> set[str]:
    if not spec:
        return set()
    try:
        from packaging.specifiers import SpecifierSet

        parsed = SpecifierSet(spec)
        out: set[str] = set()
        for item in parsed:
            if item.operator == "==":
                out.add(item.version)
        return out
    except Exception:
        return set()


def _requirements_compatible(plugin_spec: Optional[str], ai_spec: Optional[str]) -> bool:
    if not plugin_spec or not ai_spec:
        return True
    try:
        from packaging.specifiers import SpecifierSet

        plugin_set = SpecifierSet(plugin_spec)
        ai_set = SpecifierSet(ai_spec)
    except Exception:
        return True

    # Fast-path exact pins to avoid obvious conflicts.
    plugin_exact = _exact_versions(plugin_spec)
    ai_exact = _exact_versions(ai_spec)
    if plugin_exact and any(v not in ai_set for v in plugin_exact):
        return False
    if ai_exact and any(v not in plugin_set for v in ai_exact):
        return False
    return True


def _build_ai_base_requirements() -> dict[str, Optional[str]]:
    out: dict[str, Optional[str]] = {}
    for raw in Config.PLUGIN_AI_BASE_REQUIREMENTS:
        name, spec = _parse_requirement(raw)
        if not name:
            continue
        out[name] = spec
    return out


async def resolve_plugin_env(
    env_manager: UVEnvManager,
    *,
    plugin_id: str,
    plugin_path: Path,
    isolated: bool,
    trigger_mode: str,
) -> EnvDecision:
    if isolated:
        decision = EnvDecision(
            python_executable=None,
            system_site_packages=False,
            use_ai_base=False,
            reason="isolated_enabled",
        )
        logger.info(
            "env_policy plugin_id=%s trigger_mode=%s isolated=%s use_ai_base=%s reason=%s",
            plugin_id,
            trigger_mode,
            True,
            decision.use_ai_base,
            decision.reason,
        )
        return decision

    pyproject_path = plugin_path / "pyproject.toml"
    deps = env_manager._read_dependencies_from_pyproject(pyproject_path)
    if not deps:
        decision = EnvDecision(
            python_executable=None,
            system_site_packages=False,
            use_ai_base=False,
            reason="no_dependencies",
        )
        logger.info(
            "env_policy plugin_id=%s trigger_mode=%s isolated=%s use_ai_base=%s reason=%s",
            plugin_id,
            trigger_mode,
            False,
            decision.use_ai_base,
            decision.reason,
        )
        return decision

    ai_base_reqs = _build_ai_base_requirements()
    matched_names: set[str] = set()
    for dep in deps:
        name, spec = _parse_requirement(dep)
        if not name:
            continue
        ai_spec = ai_base_reqs.get(name)
        if ai_spec is None:
            continue
        if _requirements_compatible(spec, ai_spec):
            matched_names.add(name)

    if not matched_names:
        decision = EnvDecision(
            python_executable=None,
            system_site_packages=False,
            use_ai_base=False,
            reason="no_ai_base_match",
        )
        logger.info(
            "env_policy plugin_id=%s trigger_mode=%s isolated=%s use_ai_base=%s reason=%s",
            plugin_id,
            trigger_mode,
            False,
            decision.use_ai_base,
            decision.reason,
        )
        return decision

    ai_base_venv = await env_manager.ensure_ai_base_venv()
    if not ai_base_venv:
        decision = EnvDecision(
            python_executable=None,
            system_site_packages=False,
            use_ai_base=False,
            reason="ai_base_unavailable",
        )
        logger.warning(
            "env_policy plugin_id=%s trigger_mode=%s isolated=%s use_ai_base=%s reason=%s",
            plugin_id,
            trigger_mode,
            False,
            decision.use_ai_base,
            decision.reason,
        )
        return decision

    ai_python = env_manager.get_venv_python(Config.PLUGIN_AI_BASE_VENV_ID)
    decision = EnvDecision(
        python_executable=ai_python,
        system_site_packages=True,
        use_ai_base=True,
        reason=f"matched_ai_deps:{','.join(sorted(matched_names))}",
    )
    logger.info(
        "env_policy plugin_id=%s trigger_mode=%s isolated=%s use_ai_base=%s reason=%s",
        plugin_id,
        trigger_mode,
        False,
        decision.use_ai_base,
        decision.reason,
    )
    return decision
