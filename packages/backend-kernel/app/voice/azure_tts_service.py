from __future__ import annotations

import asyncio
from dataclasses import dataclass
import random
import re
import time
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.storage import storage_manager
from app.utils.logger import get_logger


_AZURE_TTS_PROVIDER = "azure_tts"
_AZURE_REGION_CONFIG_KEY = "tts.azure.region"
_AZURE_VOICE_CONFIG_KEY = "tts.azure.voice"
_AZURE_DEFAULT_ZH_VOICE_CONFIG_KEY = "tts.azure.default_voice_zh"
_AZURE_DEFAULT_EN_VOICE_CONFIG_KEY = "tts.azure.default_voice_en"
_DEFAULT_AZURE_VOICE = "zh-CN-XiaoxiaoNeural"
_DEFAULT_AZURE_ZH_VOICE = "zh-CN-XiaoxiaoNeural"
_DEFAULT_AZURE_EN_VOICE = "en-US-JennyNeural"
_DEFAULT_VALIDATE_TEXT = "DawnChat Azure TTS validation."
logger = get_logger("azure_tts_service")


@dataclass(slots=True)
class AzureTtsResolvedConfig:
    api_key: str
    region: str
    voice: str
    default_voice_zh: str
    default_voice_en: str


class AzureTtsService:
    _REGION_PATTERN = re.compile(r"^[a-z0-9-]{2,32}$")
    _VOICE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,80}$")

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        retry_base_delay_seconds: float = 0.3,
        retry_max_delay_seconds: float = 2.0,
        request_timeout_seconds: float = 12.0,
        connect_timeout_seconds: float = 4.0,
        max_keepalive_connections: int = 10,
        max_connections: int = 20,
        keepalive_expiry_seconds: float = 30.0,
    ) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._retry_base_delay_seconds = max(0.01, float(retry_base_delay_seconds))
        self._retry_max_delay_seconds = max(self._retry_base_delay_seconds, float(retry_max_delay_seconds))
        self._timeout = httpx.Timeout(timeout=float(request_timeout_seconds), connect=float(connect_timeout_seconds))
        self._limits = httpx.Limits(
            max_keepalive_connections=max(1, int(max_keepalive_connections)),
            max_connections=max(1, int(max_connections)),
            keepalive_expiry=max(1.0, float(keepalive_expiry_seconds)),
        )
        self._http_client: httpx.AsyncClient | None = None
        self._http_client_lock = asyncio.Lock()

    async def get_status(self) -> dict[str, Any]:
        api_key = await storage_manager.get_api_key(_AZURE_TTS_PROVIDER)
        region = str(await storage_manager.get_app_config(_AZURE_REGION_CONFIG_KEY, "") or "").strip()
        voice = str(await storage_manager.get_app_config(_AZURE_VOICE_CONFIG_KEY, _DEFAULT_AZURE_VOICE) or "").strip()
        default_voice_zh = str(
            await storage_manager.get_app_config(_AZURE_DEFAULT_ZH_VOICE_CONFIG_KEY, _DEFAULT_AZURE_ZH_VOICE) or ""
        ).strip() or _DEFAULT_AZURE_ZH_VOICE
        default_voice_en = str(
            await storage_manager.get_app_config(_AZURE_DEFAULT_EN_VOICE_CONFIG_KEY, _DEFAULT_AZURE_EN_VOICE) or ""
        ).strip() or _DEFAULT_AZURE_EN_VOICE
        return {
            "configured": bool(api_key and region),
            "api_key_configured": bool(api_key),
            "region": region,
            "voice": voice or _DEFAULT_AZURE_VOICE,
            "default_voice_zh": default_voice_zh,
            "default_voice_en": default_voice_en,
        }

    async def validate_config(
        self,
        *,
        api_key: str = "",
        region: str = "",
        voice: str = "",
        default_voice_zh: str = "",
        default_voice_en: str = "",
        test_text: str = "",
    ) -> dict[str, Any]:
        config = await self._resolve_config(
            api_key=api_key,
            region=region,
            voice=voice,
            default_voice_zh=default_voice_zh,
            default_voice_en=default_voice_en,
            text=test_text,
            allow_stored_key=True,
        )
        text = str(test_text or "").strip()
        zh_text = text or "你好，DawnChat。"
        en_text = text or _DEFAULT_VALIDATE_TEXT
        wav_bytes_zh = await self._synthesize_once(config=config, text=zh_text, force_voice=config.default_voice_zh)
        wav_bytes_en = await self._synthesize_once(config=config, text=en_text, force_voice=config.default_voice_en)
        if not wav_bytes_zh or not wav_bytes_en:
            raise ValueError("azure_tts_empty_audio")
        return {
            "ok": True,
            "region": config.region,
            "voice": config.voice,
            "default_voice_zh": config.default_voice_zh,
            "default_voice_en": config.default_voice_en,
            "audio_bytes_zh": len(wav_bytes_zh),
            "audio_bytes_en": len(wav_bytes_en),
        }

    async def save_config(
        self,
        *,
        api_key: str = "",
        region: str = "",
        voice: str = "",
        default_voice_zh: str = "",
        default_voice_en: str = "",
    ) -> dict[str, Any]:
        config = await self._resolve_config(
            api_key=api_key,
            region=region,
            voice=voice,
            default_voice_zh=default_voice_zh,
            default_voice_en=default_voice_en,
            text="",
            allow_stored_key=True,
        )
        current_api_key = await storage_manager.get_api_key(_AZURE_TTS_PROVIDER)
        if str(api_key or "").strip():
            await storage_manager.set_api_key(_AZURE_TTS_PROVIDER, config.api_key)
        elif not current_api_key:
            raise ValueError("azure_tts_api_key_required")
        await storage_manager.set_app_config(_AZURE_REGION_CONFIG_KEY, config.region)
        await storage_manager.set_app_config(_AZURE_VOICE_CONFIG_KEY, config.voice)
        await storage_manager.set_app_config(_AZURE_DEFAULT_ZH_VOICE_CONFIG_KEY, config.default_voice_zh)
        await storage_manager.set_app_config(_AZURE_DEFAULT_EN_VOICE_CONFIG_KEY, config.default_voice_en)
        return {
            "ok": True,
            "region": config.region,
            "voice": config.voice,
            "default_voice_zh": config.default_voice_zh,
            "default_voice_en": config.default_voice_en,
        }

    def iter_synthesize(self, *, text: str, voice: str = "", sid: int | None = None) -> list[Any]:
        raise RuntimeError("azure_iter_synthesize_should_not_run_sync")

    async def synthesize_segment(self, *, text: str, voice: str = "", sid: int | None = None) -> tuple[bytes, int]:
        del sid  # Azure voice uses voice name instead of sid.
        config = await self._resolve_config(
            api_key="",
            region="",
            voice=voice,
            default_voice_zh="",
            default_voice_en="",
            text=text,
            allow_stored_key=True,
        )
        wav_bytes = await self._synthesize_once(config=config, text=text)
        return wav_bytes, 24000

    async def _resolve_config(
        self,
        *,
        api_key: str,
        region: str,
        voice: str,
        default_voice_zh: str,
        default_voice_en: str,
        text: str,
        allow_stored_key: bool,
    ) -> AzureTtsResolvedConfig:
        normalized_region = str(region or "").strip().lower()
        if not normalized_region:
            normalized_region = str(await storage_manager.get_app_config(_AZURE_REGION_CONFIG_KEY, "") or "").strip().lower()
        if not normalized_region:
            raise ValueError("azure_tts_region_required")
        if not self._REGION_PATTERN.match(normalized_region):
            raise ValueError("azure_tts_region_invalid")

        normalized_default_voice_zh = await self._normalize_default_voice(
            raw_voice=default_voice_zh,
            storage_key=_AZURE_DEFAULT_ZH_VOICE_CONFIG_KEY,
            fallback_voice=_DEFAULT_AZURE_ZH_VOICE,
            expected_prefix="zh-",
        )
        normalized_default_voice_en = await self._normalize_default_voice(
            raw_voice=default_voice_en,
            storage_key=_AZURE_DEFAULT_EN_VOICE_CONFIG_KEY,
            fallback_voice=_DEFAULT_AZURE_EN_VOICE,
            expected_prefix="en-",
        )
        normalized_voice = await self._resolve_voice(
            voice=voice,
            text=text,
            default_voice_zh=normalized_default_voice_zh,
            default_voice_en=normalized_default_voice_en,
        )
        if not self._VOICE_PATTERN.match(normalized_voice):
            raise ValueError("azure_tts_voice_invalid")

        normalized_api_key = str(api_key or "").strip()
        if not normalized_api_key and allow_stored_key:
            normalized_api_key = str(await storage_manager.get_api_key(_AZURE_TTS_PROVIDER) or "").strip()
        if not normalized_api_key:
            raise ValueError("azure_tts_api_key_required")
        return AzureTtsResolvedConfig(
            api_key=normalized_api_key,
            region=normalized_region,
            voice=normalized_voice,
            default_voice_zh=normalized_default_voice_zh,
            default_voice_en=normalized_default_voice_en,
        )

    async def _resolve_voice(self, *, voice: str, text: str, default_voice_zh: str, default_voice_en: str) -> str:
        explicit_voice = str(voice or "").strip()
        if explicit_voice:
            return explicit_voice
        return default_voice_zh if self._contains_zh(text) else default_voice_en

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
            raise ValueError("azure_tts_voice_invalid")
        if not candidate.startswith(expected_prefix):
            raise ValueError("azure_tts_voice_locale_mismatch")
        return candidate

    async def _synthesize_once(self, *, config: AzureTtsResolvedConfig, text: str, force_voice: str = "") -> bytes:
        payload = str(text or "").strip()
        if not payload:
            raise ValueError("tts text is required")
        endpoint = f"https://{config.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        target_voice = str(force_voice or "").strip() or config.voice
        ssml_text = self._build_ssml(text=payload, voice=target_voice)
        for attempt in range(1, self._max_attempts + 1):
            started_at = time.monotonic()
            logger.info(
                "azure_tts_request_start attempt=%s text_len=%s region=%s voice=%s",
                attempt,
                len(payload),
                config.region,
                target_voice,
            )
            error_code = ""
            captured_error: Exception | None = None
            try:
                client = await self._get_http_client()
                response = await client.post(
                    endpoint,
                    headers={
                        "Ocp-Apim-Subscription-Key": config.api_key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                        "User-Agent": "DawnChat",
                    },
                    content=ssml_text.encode("utf-8"),
                )
                if response.status_code >= 400:
                    self._raise_http_error(response.status_code)
                output = bytes(response.content or b"")
                logger.info(
                    "azure_tts_request_done attempt=%s latency_ms=%s bytes=%s",
                    attempt,
                    int((time.monotonic() - started_at) * 1000),
                    len(output),
                )
                return output
            except httpx.TimeoutException as err:
                error_code = "azure_tts_timeout"
                captured_error = err
            except httpx.RequestError as err:
                error_code = "azure_tts_network_error"
                captured_error = err
                await self._recreate_http_client(reason=error_code)
            except ValueError as err:
                error_code = str(err).strip()
                captured_error = err

            normalized_code = error_code or "azure_tts_unknown_error"
            if not self._is_retryable_error_code(normalized_code):
                logger.warning("azure_tts_non_retryable_error attempt=%s error_code=%s", attempt, normalized_code)
                raise ValueError(normalized_code) from captured_error
            if attempt >= self._max_attempts:
                logger.warning(
                    "azure_tts_retry_exhausted attempts=%s last_error_code=%s",
                    attempt,
                    normalized_code,
                )
                raise ValueError(normalized_code) from captured_error
            sleep_seconds = self._compute_retry_sleep_seconds(attempt)
            logger.warning(
                "azure_tts_retry_scheduled attempt=%s error_code=%s sleep_ms=%s",
                attempt,
                normalized_code,
                int(round(sleep_seconds * 1000)),
            )
            await asyncio.sleep(sleep_seconds)
        raise ValueError("azure_tts_unknown_error")

    async def aclose(self) -> None:
        async with self._http_client_lock:
            client = self._http_client
            self._http_client = None
        if client is not None and not client.is_closed:
            await client.aclose()

    async def _get_http_client(self) -> httpx.AsyncClient:
        async with self._http_client_lock:
            if self._http_client is None or self._http_client.is_closed:
                self._http_client = self._create_http_client()
                logger.info(
                    "azure_tts_client_created timeout=%s connect_timeout=%s max_keepalive=%s max_connections=%s keepalive_expiry=%s",
                    self._timeout.read,
                    self._timeout.connect,
                    self._limits.max_keepalive_connections,
                    self._limits.max_connections,
                    self._limits.keepalive_expiry,
                )
            return self._http_client

    async def _recreate_http_client(self, *, reason: str) -> None:
        async with self._http_client_lock:
            old_client = self._http_client
            self._http_client = self._create_http_client()
        if old_client is not None and not old_client.is_closed:
            await old_client.aclose()
        logger.warning("azure_tts_client_recreated reason=%s", reason)

    def _create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, limits=self._limits)

    def _compute_retry_sleep_seconds(self, attempt: int) -> float:
        exponential = self._retry_base_delay_seconds * (2 ** max(0, attempt - 1))
        jitter = random.uniform(0.0, self._retry_base_delay_seconds * 0.25)
        return min(self._retry_max_delay_seconds, exponential + jitter)

    @staticmethod
    def _is_retryable_error_code(error_code: str) -> bool:
        code = str(error_code or "").strip().lower()
        if code in {"azure_tts_timeout", "azure_tts_network_error", "azure_tts_rate_limited", "azure_tts_http_5xx"}:
            return True
        return False

    @staticmethod
    def _build_ssml(*, text: str, voice: str) -> str:
        safe_text = escape(text)
        safe_voice = escape(voice)
        voice_lang = AzureTtsService._voice_to_locale(voice)
        return (
            f'<speak version="1.0" xml:lang="{voice_lang}">'
            f'<voice xml:lang="{voice_lang}" name="{safe_voice}">{safe_text}</voice>'
            "</speak>"
        )

    @staticmethod
    def _raise_http_error(status_code: int) -> None:
        if status_code in {401, 403}:
            raise ValueError("azure_tts_auth_failed")
        if status_code == 404:
            raise ValueError("azure_tts_region_or_voice_not_found")
        if status_code == 429:
            raise ValueError("azure_tts_rate_limited")
        if 500 <= status_code <= 599:
            raise ValueError("azure_tts_http_5xx")
        raise ValueError(f"azure_tts_http_{status_code}")

    @staticmethod
    def _contains_zh(text: str) -> bool:
        payload = str(text or "")
        return bool(re.search(r"[\u4e00-\u9fff]", payload))

    @staticmethod
    def _voice_to_locale(voice: str) -> str:
        payload = str(voice or "").strip()
        if len(payload) >= 5 and payload[2] == "-":
            return payload[:5]
        return "zh-CN"


_azure_tts_service: AzureTtsService | None = None


def get_azure_tts_service() -> AzureTtsService:
    global _azure_tts_service
    if _azure_tts_service is None:
        _azure_tts_service = AzureTtsService()
    return _azure_tts_service
