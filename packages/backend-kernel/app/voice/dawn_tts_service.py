from __future__ import annotations

import re
from typing import Any

from app.config import Config
from app.services.dawn_tts_edge_client import synthesize_to_mp3
from app.services.supabase_session_store import get_supabase_session_store
from app.services.web_publish_service import WebPublishService
from app.storage import storage_manager
from app.utils.logger import get_logger

_DAWN_DEFAULT_ZH_VOICE_CONFIG_KEY = "tts.dawn.default_voice_zh"
_DAWN_DEFAULT_EN_VOICE_CONFIG_KEY = "tts.dawn.default_voice_en"
_DEFAULT_DAWN_ZH_VOICE = "zh-CN-XiaoxiaoNeural"
_DEFAULT_DAWN_EN_VOICE = "en-US-JennyNeural"

logger = get_logger("dawn_tts_service")


class DawnTtsService:
    _VOICE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,80}$")

    async def get_provider_status(self) -> dict[str, Any]:
        default_voice_zh = str(
            await storage_manager.get_app_config(_DAWN_DEFAULT_ZH_VOICE_CONFIG_KEY, _DEFAULT_DAWN_ZH_VOICE) or ""
        ).strip() or _DEFAULT_DAWN_ZH_VOICE
        default_voice_en = str(
            await storage_manager.get_app_config(_DAWN_DEFAULT_EN_VOICE_CONFIG_KEY, _DEFAULT_DAWN_EN_VOICE) or ""
        ).strip() or _DEFAULT_DAWN_EN_VOICE

        supabase_url = str(getattr(Config, "SUPABASE_URL", "") or "").strip()
        if not supabase_url:
            return {
                "available": False,
                "reason": "supabase_url_missing",
                "default_voice_zh": default_voice_zh,
                "default_voice_en": default_voice_en,
            }
        try:
            key = WebPublishService._resolve_supabase_apikey()
        except Exception as err:
            logger.warning("dawn_tts apikey resolve failed: %s", err)
            key = ""
        if not str(key or "").strip():
            return {
                "available": False,
                "reason": "supabase_apikey_missing",
                "default_voice_zh": default_voice_zh,
                "default_voice_en": default_voice_en,
            }

        token = await get_supabase_session_store().get_usable_access_token()
        if not token:
            return {
                "available": False,
                "reason": "not_logged_in",
                "default_voice_zh": default_voice_zh,
                "default_voice_en": default_voice_en,
            }

        return {
            "available": True,
            "reason": "",
            "default_voice_zh": default_voice_zh,
            "default_voice_en": default_voice_en,
        }

    async def validate_voice_config(
        self,
        *,
        default_voice_zh: str = "",
        default_voice_en: str = "",
    ) -> dict[str, Any]:
        zh = await self._normalize_default_voice(
            raw_voice=default_voice_zh,
            storage_key=_DAWN_DEFAULT_ZH_VOICE_CONFIG_KEY,
            fallback_voice=_DEFAULT_DAWN_ZH_VOICE,
            expected_prefix="zh-",
        )
        en = await self._normalize_default_voice(
            raw_voice=default_voice_en,
            storage_key=_DAWN_DEFAULT_EN_VOICE_CONFIG_KEY,
            fallback_voice=_DEFAULT_DAWN_EN_VOICE,
            expected_prefix="en-",
        )
        return {"ok": True, "default_voice_zh": zh, "default_voice_en": en}

    async def save_voice_config(
        self,
        *,
        default_voice_zh: str = "",
        default_voice_en: str = "",
    ) -> dict[str, Any]:
        validated = await self.validate_voice_config(
            default_voice_zh=default_voice_zh,
            default_voice_en=default_voice_en,
        )
        zh = str(validated.get("default_voice_zh") or _DEFAULT_DAWN_ZH_VOICE)
        en = str(validated.get("default_voice_en") or _DEFAULT_DAWN_EN_VOICE)
        await storage_manager.set_app_config(_DAWN_DEFAULT_ZH_VOICE_CONFIG_KEY, zh)
        await storage_manager.set_app_config(_DAWN_DEFAULT_EN_VOICE_CONFIG_KEY, en)
        return {"ok": True, "default_voice_zh": zh, "default_voice_en": en}

    async def resolve_voice(self, *, explicit_voice: str, text: str) -> str:
        voice = str(explicit_voice or "").strip()
        if voice:
            if not self._VOICE_PATTERN.match(voice):
                raise ValueError("dawn_tts_voice_invalid")
            return voice
        default_zh = await self._normalize_default_voice(
            raw_voice="",
            storage_key=_DAWN_DEFAULT_ZH_VOICE_CONFIG_KEY,
            fallback_voice=_DEFAULT_DAWN_ZH_VOICE,
            expected_prefix="zh-",
        )
        default_en = await self._normalize_default_voice(
            raw_voice="",
            storage_key=_DAWN_DEFAULT_EN_VOICE_CONFIG_KEY,
            fallback_voice=_DEFAULT_DAWN_EN_VOICE,
            expected_prefix="en-",
        )
        return default_zh if self._contains_zh(text) else default_en

    async def synthesize_segment_mp3(self, *, text: str, voice: str, sid: int | None = None) -> bytes:
        del sid
        token = await get_supabase_session_store().get_usable_access_token()
        if not token:
            raise ValueError("dawn_tts_not_logged_in")
        resolved = await self.resolve_voice(explicit_voice=voice, text=text)
        return await synthesize_to_mp3(access_token=token, text=text, voice=resolved)

    async def _normalize_default_voice(
        self,
        *,
        raw_voice: str,
        storage_key: str,
        fallback_voice: str,
        expected_prefix: str,
    ) -> str:
        candidate = str(raw_voice or "").strip()
        if not candidate:
            candidate = str(await storage_manager.get_app_config(storage_key, fallback_voice) or "").strip()
        if not candidate:
            candidate = fallback_voice
        if not self._VOICE_PATTERN.match(candidate):
            raise ValueError("dawn_tts_voice_invalid")
        if not candidate.startswith(expected_prefix):
            raise ValueError("dawn_tts_voice_locale_mismatch")
        return candidate

    @staticmethod
    def _contains_zh(text: str) -> bool:
        payload = str(text or "")
        return bool(re.search(r"[\u4e00-\u9fff]", payload))


_dawn_tts_service: DawnTtsService | None = None


def get_dawn_tts_service() -> DawnTtsService:
    global _dawn_tts_service
    if _dawn_tts_service is None:
        _dawn_tts_service = DawnTtsService()
    return _dawn_tts_service
