"""
Network Configuration Service
Manages proxy settings and resource-access policies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from app.storage import storage_manager
from app.utils.logger import get_logger

logger = get_logger("network_service")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _move_to_front(items: List[str], candidate: Optional[str]) -> List[str]:
    if not candidate or candidate not in items:
        return items
    return [candidate] + [item for item in items if item != candidate]


class NetworkService:
    """
    Service for managing network configurations (Proxy and mirrors).
    """

    PROXY_CONFIG_KEY = "system:network:proxy"
    RESOURCE_ACCESS_CONFIG_KEY = "system:network:resource_access"
    RESOURCE_PROBE_STATUS_KEY = "system:network:probe_status"
    RESOURCE_LAST_SUCCESS_KEY = "system:network:resource_access:last_success"

    DEFAULT_MODES: Dict[str, Any] = {
        "global_mode": "auto",  # auto | direct_only | mirror_only | prefer_direct | prefer_mirror
        "providers": {
            "huggingface": {
                "mode": "auto",
                "mirror_url": "https://hf-mirror.com",
                "direct_url": "https://huggingface.co",
            },
            "github": {
                "mode": "auto",
                "mirror_prefix": "https://ghproxy.com/",
            },
            "playwright": {
                "mode": "auto",
                "mirror_host": "https://npmmirror.com/mirrors/playwright",
                "direct_host": "",
            },
            "pypi": {
                "mode": "auto",
                "mirror_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
                "direct_url": "https://pypi.org/simple",
            },
        },
        "auto_probe": {
            "enabled": True,
            "timeout_ms": 2500,
        },
    }

    VALID_MODES = {"auto", "direct_only", "mirror_only", "prefer_direct", "prefer_mirror"}

    @classmethod
    async def initialize(cls):
        """Initialize network settings from storage"""
        try:
            proxy_config = await storage_manager.get_config(cls.PROXY_CONFIG_KEY)
            if proxy_config:
                cls.apply_proxy_settings(proxy_config)
            else:
                cls.apply_default_proxy_settings()
        except Exception as e:
            logger.error(f"Failed to initialize network proxy settings: {e}")
            cls.apply_default_proxy_settings()

        try:
            config = await cls.get_resource_access_settings()
            cls.apply_resource_access_env(config)
        except Exception as e:
            logger.warning(f"Failed to initialize resource access env: {e}")

    @classmethod
    def _normalize_proxy_url(cls, proxy_url: str) -> str:
        """
        Normalize proxy URL: ensure it uses http:// protocol.
        
        Proxy servers (Clash, V2Ray, etc.) use HTTP protocol to receive requests,
        even when proxying HTTPS traffic. Using https:// for proxy URL will cause
        SSL handshake failures because the client tries to establish TLS with the
        proxy server itself.
        """
        if not proxy_url:
            return proxy_url
        
        proxy_url = proxy_url.strip()
        
        # Fix common mistake: https:// should be http://
        if proxy_url.startswith("https://"):
            corrected = "http://" + proxy_url[8:]
            logger.warning(f"Corrected proxy URL protocol: {proxy_url} -> {corrected}")
            return corrected
        
        # Add http:// prefix if missing
        if not proxy_url.startswith("http://") and not proxy_url.startswith("socks"):
            corrected = "http://" + proxy_url
            logger.info(f"Added http:// prefix to proxy URL: {proxy_url} -> {corrected}")
            return corrected
        
        return proxy_url
    
    @classmethod
    def apply_proxy_settings(cls, config: Dict[str, Union[str, bool]]):
        """Apply proxy settings to environment variables"""
        
        # Clear existing proxy env vars first to ensure clean state
        for key in [
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
            "no_proxy",
            "NO_PROXY",
        ]:
            if key in os.environ:
                del os.environ[key]
                
        if config.get("enabled", False):
            http_proxy = cls._normalize_proxy_url(str(config.get("http_proxy", "")))
            https_proxy = cls._normalize_proxy_url(str(config.get("https_proxy", "")))
            no_proxy = str(config.get("no_proxy", "localhost,127.0.0.1"))
            
            if http_proxy:
                os.environ["http_proxy"] = http_proxy
                os.environ["HTTP_PROXY"] = http_proxy
            
            if https_proxy:
                os.environ["https_proxy"] = https_proxy
                os.environ["HTTPS_PROXY"] = https_proxy

            # Keep ALL_PROXY aligned so libraries that prefer it (including httpx)
            # follow the same user-configured proxy endpoint.
            all_proxy = https_proxy or http_proxy
            if all_proxy:
                os.environ["all_proxy"] = all_proxy
                os.environ["ALL_PROXY"] = all_proxy
                
            if no_proxy:
                # Ensure localhost is always in no_proxy
                if "localhost" not in no_proxy:
                    no_proxy += ",localhost"
                if "127.0.0.1" not in no_proxy:
                    no_proxy += ",127.0.0.1"
                    
                os.environ["no_proxy"] = no_proxy
                os.environ["NO_PROXY"] = no_proxy
                
            logger.info(f"Applied proxy settings: HTTP={http_proxy}, HTTPS={https_proxy}, NO_PROXY={no_proxy}")
        else:
            cls.apply_default_proxy_settings()
            logger.info("Proxy settings disabled, applied defaults")

    @classmethod
    def apply_default_proxy_settings(cls):
        """Apply default proxy settings (ensure localhost bypass)"""
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
            if key in os.environ:
                del os.environ[key]
        # Even when proxy is disabled, we should ensure NO_PROXY is set for localhost
        # to avoid issues with VPNs or system-wide proxies
        defaults = "localhost,127.0.0.1"
        os.environ["no_proxy"] = defaults
        os.environ["NO_PROXY"] = defaults

    @classmethod
    async def get_proxy_settings(cls) -> Dict[str, Union[str, bool]]:
        """Get current proxy settings"""
        return await storage_manager.get_config(cls.PROXY_CONFIG_KEY) or {
            "enabled": False,
            "http_proxy": "",
            "https_proxy": "",
            "no_proxy": "localhost,127.0.0.1"
        }

    @classmethod
    async def save_proxy_settings(cls, config: Dict[str, Union[str, bool]]):
        """Save and apply proxy settings"""
        await storage_manager.set_config(cls.PROXY_CONFIG_KEY, config)
        cls.apply_proxy_settings(config)

    # -----------------------------
    # Resource access policy
    # -----------------------------

    @classmethod
    def _normalize_mode(cls, value: Optional[str], fallback: str = "auto") -> str:
        mode = (value or fallback).strip().lower()
        return mode if mode in cls.VALID_MODES else fallback

    @classmethod
    def _default_resource_access_config(cls) -> Dict[str, Any]:
        default = {
            "global_mode": cls.DEFAULT_MODES["global_mode"],
            "providers": {
                "huggingface": dict(cls.DEFAULT_MODES["providers"]["huggingface"]),
                "github": dict(cls.DEFAULT_MODES["providers"]["github"]),
                "playwright": dict(cls.DEFAULT_MODES["providers"]["playwright"]),
                "pypi": dict(cls.DEFAULT_MODES["providers"]["pypi"]),
            },
            "auto_probe": dict(cls.DEFAULT_MODES["auto_probe"]),
            "updated_at": _now_iso(),
        }
        return default

    @classmethod
    def _normalize_resource_access_config(cls, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = cls._default_resource_access_config()
        if not isinstance(config, dict):
            return merged

        merged["global_mode"] = cls._normalize_mode(config.get("global_mode"), merged["global_mode"])

        providers = config.get("providers")
        if isinstance(providers, dict):
            for provider in ("huggingface", "github", "playwright", "pypi"):
                if provider not in providers or not isinstance(providers[provider], dict):
                    continue
                target = merged["providers"][provider]
                source = providers[provider]
                target["mode"] = cls._normalize_mode(source.get("mode"), target.get("mode", "auto"))
                for key in ("mirror_url", "direct_url", "mirror_prefix", "mirror_host", "direct_host"):
                    if key in source and isinstance(source[key], str):
                        target[key] = source[key].strip()

        auto_probe = config.get("auto_probe")
        if isinstance(auto_probe, dict):
            enabled = auto_probe.get("enabled")
            timeout_ms = auto_probe.get("timeout_ms")
            if isinstance(enabled, bool):
                merged["auto_probe"]["enabled"] = enabled
            if isinstance(timeout_ms, int) and 200 <= timeout_ms <= 10000:
                merged["auto_probe"]["timeout_ms"] = timeout_ms

        updated_at = config.get("updated_at")
        merged["updated_at"] = updated_at if isinstance(updated_at, str) and updated_at else _now_iso()
        return merged

    @classmethod
    async def get_resource_access_settings(cls) -> Dict[str, Any]:
        raw = await storage_manager.get_config(cls.RESOURCE_ACCESS_CONFIG_KEY)
        config = cls._normalize_resource_access_config(raw)
        # Self-heal malformed/legacy data in storage.
        if raw != config:
            await storage_manager.set_config(cls.RESOURCE_ACCESS_CONFIG_KEY, config)
        return config

    @classmethod
    async def save_resource_access_settings(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        normalized = cls._normalize_resource_access_config(config)
        normalized["updated_at"] = _now_iso()
        await storage_manager.set_config(cls.RESOURCE_ACCESS_CONFIG_KEY, normalized)
        cls.apply_resource_access_env(normalized)
        return normalized

    @classmethod
    def _resolve_mode_for_provider(cls, config: Dict[str, Any], provider: str) -> str:
        provider_cfg = config.get("providers", {}).get(provider, {})
        provider_mode = provider_cfg.get("mode")
        if provider_mode:
            return cls._normalize_mode(provider_mode, "auto")
        return cls._normalize_mode(config.get("global_mode"), "auto")

    @classmethod
    async def _get_last_success_cache(cls) -> Dict[str, Any]:
        cache = await storage_manager.get_config(cls.RESOURCE_LAST_SUCCESS_KEY)
        if isinstance(cache, dict):
            return cache
        return {}

    @classmethod
    async def _set_last_success_cache(cls, cache: Dict[str, Any]):
        await storage_manager.set_config(cls.RESOURCE_LAST_SUCCESS_KEY, cache)

    @classmethod
    async def record_provider_success(cls, provider: str, candidate: str):
        cache = await cls._get_last_success_cache()
        cache[provider] = {
            "candidate": candidate,
            "updated_at": _now_iso(),
        }
        await cls._set_last_success_cache(cache)

    @classmethod
    def _apply_mode_order(cls, mode: str, direct: str, mirror: str) -> List[str]:
        if mode == "direct_only":
            return [direct]
        if mode == "mirror_only":
            return [mirror]
        if mode == "prefer_mirror":
            return [mirror, direct]
        # auto / prefer_direct
        return [direct, mirror]

    @classmethod
    async def resolve_hf_endpoint_candidates(
        cls,
        explicit_use_mirror: Optional[bool] = None,
    ) -> List[str]:
        cfg = await cls.get_resource_access_settings()
        provider_cfg = cfg["providers"]["huggingface"]
        direct = provider_cfg.get("direct_url") or "https://huggingface.co"
        mirror = provider_cfg.get("mirror_url") or "https://hf-mirror.com"

        if explicit_use_mirror is True:
            candidates = [mirror, direct]
        elif explicit_use_mirror is False:
            candidates = [direct, mirror]
        else:
            mode = cls._resolve_mode_for_provider(cfg, "huggingface")
            candidates = cls._apply_mode_order(mode, direct, mirror)

        probe = await cls.get_probe_status()
        recommended = (
            probe.get("providers", {})
            .get("huggingface", {})
            .get("recommended")
        )
        if explicit_use_mirror is None:
            candidates = _move_to_front(candidates, recommended)

            cache = await cls._get_last_success_cache()
            sticky = cache.get("huggingface", {}).get("candidate")
            candidates = _move_to_front(candidates, sticky)

        return _dedupe_keep_order(candidates)

    @classmethod
    async def resolve_github_url_candidates(
        cls,
        url: str,
        explicit_use_mirror: Optional[bool] = None,
    ) -> List[str]:
        cfg = await cls.get_resource_access_settings()
        provider_cfg = cfg["providers"]["github"]
        mirror_prefix = provider_cfg.get("mirror_prefix") or "https://ghproxy.com/"
        mirror_url = f"{mirror_prefix}{url}"

        if explicit_use_mirror is True:
            candidates = [mirror_url, url]
        elif explicit_use_mirror is False:
            candidates = [url, mirror_url]
        else:
            mode = cls._resolve_mode_for_provider(cfg, "github")
            mode_candidates = cls._apply_mode_order(mode, "direct", "mirror")
            candidates = [mirror_url if c == "mirror" else url for c in mode_candidates]

        probe = await cls.get_probe_status()
        rec = probe.get("providers", {}).get("github", {}).get("recommended")
        if explicit_use_mirror is None and rec in {"direct", "mirror"}:
            preferred = mirror_url if rec == "mirror" else url
            candidates = _move_to_front(candidates, preferred)

        if explicit_use_mirror is None:
            cache = await cls._get_last_success_cache()
            sticky = cache.get("github", {}).get("candidate")
            candidates = _move_to_front(candidates, sticky)

        return _dedupe_keep_order(candidates)

    @classmethod
    async def resolve_playwright_hosts(
        cls,
        explicit_use_mirror: Optional[bool] = None,
    ) -> List[str]:
        cfg = await cls.get_resource_access_settings()
        provider_cfg = cfg["providers"]["playwright"]
        mirror = provider_cfg.get("mirror_host") or "https://npmmirror.com/mirrors/playwright"
        direct = provider_cfg.get("direct_host") or ""

        if explicit_use_mirror is True:
            candidates = [mirror, direct]
        elif explicit_use_mirror is False:
            candidates = [direct, mirror]
        else:
            mode = cls._resolve_mode_for_provider(cfg, "playwright")
            if mode == "mirror_only":
                candidates = [mirror]
            elif mode == "direct_only":
                candidates = [direct]
            elif mode == "prefer_mirror":
                candidates = [mirror, direct]
            else:
                candidates = [direct, mirror]

        # Probe recommendation and sticky cache only applies when explicit not set.
        if explicit_use_mirror is None:
            probe = await cls.get_probe_status()
            rec = probe.get("providers", {}).get("playwright", {}).get("recommended")
            if rec in {"direct", "mirror"}:
                preferred = mirror if rec == "mirror" else direct
                candidates = _move_to_front(candidates, preferred)

            cache = await cls._get_last_success_cache()
            sticky = cache.get("playwright", {}).get("candidate")
            candidates = _move_to_front(candidates, sticky)

        return _dedupe_keep_order([c for c in candidates if isinstance(c, str)])

    @classmethod
    async def resolve_pypi_index_candidates(
        cls,
        explicit_use_mirror: Optional[bool] = None,
    ) -> List[str]:
        cfg = await cls.get_resource_access_settings()
        provider_cfg = cfg["providers"]["pypi"]
        direct = provider_cfg.get("direct_url") or "https://pypi.org/simple"
        mirror = provider_cfg.get("mirror_url") or "https://pypi.tuna.tsinghua.edu.cn/simple"

        if explicit_use_mirror is True:
            candidates = [mirror, direct]
        elif explicit_use_mirror is False:
            candidates = [direct, mirror]
        else:
            mode = cls._resolve_mode_for_provider(cfg, "pypi")
            candidates = cls._apply_mode_order(mode, direct, mirror)

            probe = await cls.get_probe_status()
            recommended = probe.get("providers", {}).get("pypi", {}).get("recommended")
            candidates = _move_to_front(candidates, recommended)

            cache = await cls._get_last_success_cache()
            sticky = cache.get("pypi", {}).get("candidate")
            candidates = _move_to_front(candidates, sticky)

        return _dedupe_keep_order(candidates)

    @classmethod
    def apply_resource_access_env(cls, config: Dict[str, Any]):
        """
        Apply process-level env values.
        This is best-effort and avoids hardcoding mirror globally for all users.
        """
        provider_cfg = config.get("providers", {}).get("huggingface", {})
        mode = cls._resolve_mode_for_provider(config, "huggingface")
        direct = provider_cfg.get("direct_url") or "https://huggingface.co"
        mirror = provider_cfg.get("mirror_url") or "https://hf-mirror.com"
        hf_endpoint = mirror if mode in {"mirror_only", "prefer_mirror"} else direct
        os.environ["HF_ENDPOINT"] = hf_endpoint
        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
        logger.info(f"Applied resource env: HF_ENDPOINT={hf_endpoint}")

    @classmethod
    async def get_probe_status(cls) -> Dict[str, Any]:
        data = await storage_manager.get_config(cls.RESOURCE_PROBE_STATUS_KEY)
        if isinstance(data, dict):
            return data
        return {"providers": {}, "updated_at": None}

    @classmethod
    async def _probe_url(
        cls,
        url: str,
        timeout_ms: int,
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        try:
            import time

            import aiohttp

            started = time.perf_counter()
            timeout = aiohttp.ClientTimeout(total=max(timeout_ms / 1000.0, 0.2))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    _ = resp.status
            elapsed = int((time.perf_counter() - started) * 1000)
            return True, elapsed, None
        except Exception as e:
            return False, None, str(e)

    @classmethod
    async def probe_resource_access(cls) -> Dict[str, Any]:
        cfg = await cls.get_resource_access_settings()
        timeout_ms = int(cfg.get("auto_probe", {}).get("timeout_ms", 2500))

        hf_direct = cfg["providers"]["huggingface"].get("direct_url") or "https://huggingface.co"
        hf_mirror = cfg["providers"]["huggingface"].get("mirror_url") or "https://hf-mirror.com"
        gh_direct = "https://github.com"
        gh_mirror = (cfg["providers"]["github"].get("mirror_prefix") or "https://ghproxy.com/").rstrip("/") + "/https://github.com"
        pw_direct = "https://playwright.azureedge.net"
        pw_mirror = cfg["providers"]["playwright"].get("mirror_host") or "https://npmmirror.com/mirrors/playwright"
        pypi_direct = cfg["providers"]["pypi"].get("direct_url") or "https://pypi.org/simple"
        pypi_mirror = cfg["providers"]["pypi"].get("mirror_url") or "https://pypi.tuna.tsinghua.edu.cn/simple"

        probe_targets: Dict[str, Dict[str, str]] = {
            "huggingface": {"direct": hf_direct, "mirror": hf_mirror},
            "github": {"direct": gh_direct, "mirror": gh_mirror},
            "playwright": {"direct": pw_direct, "mirror": pw_mirror},
            "pypi": {"direct": pypi_direct, "mirror": pypi_mirror},
        }

        result: Dict[str, Any] = {"providers": {}, "updated_at": _now_iso()}
        for provider, targets in probe_targets.items():
            provider_result: Dict[str, Any] = {}
            direct_ok, direct_ms, direct_err = await cls._probe_url(targets["direct"], timeout_ms)
            mirror_ok, mirror_ms, mirror_err = await cls._probe_url(targets["mirror"], timeout_ms)
            provider_result["direct"] = {"ok": direct_ok, "latency_ms": direct_ms, "error": direct_err}
            provider_result["mirror"] = {"ok": mirror_ok, "latency_ms": mirror_ms, "error": mirror_err}

            recommended = "direct"
            if mirror_ok and not direct_ok:
                recommended = "mirror"
            elif mirror_ok and direct_ok:
                if (mirror_ms or 10**9) + 150 < (direct_ms or 10**9):
                    recommended = "mirror"
            elif not direct_ok and not mirror_ok:
                recommended = "direct"
            provider_result["recommended"] = recommended
            result["providers"][provider] = provider_result

        await storage_manager.set_config(cls.RESOURCE_PROBE_STATUS_KEY, result)
        return result
