from __future__ import annotations

from dataclasses import dataclass
import io
import math
from pathlib import Path
import re
import threading
import time
from typing import Any, Iterator, List, Literal
import unicodedata
import wave

from app.config import Config


class TextPreprocessor:
    def __init__(self) -> None:
        self._replacements = {
            "❓": "?",
            "❔": "?",
            "❕": "!",
            "❗": "!",
        }

    def normalize(self, text: str, *, empty_fallback: str = " ", use_nfkc: bool = True) -> str:
        payload = str(text or "")
        if use_nfkc:
            payload = unicodedata.normalize("NFKC", payload)
        if not payload:
            return empty_fallback
        replaced = payload
        for src, target in self._replacements.items():
            replaced = replaced.replace(src, target)
        chars: List[str] = []
        for ch in replaced:
            if ch in {"\n", "\r", "\t"}:
                chars.append(" ")
                continue
            category = unicodedata.category(ch)
            if category in {"Cc", "Cs"}:
                chars.append(" ")
                continue
            if category == "So":
                chars.append(" ")
                continue
            if ch.isprintable():
                chars.append(ch)
        normalized = re.sub(r"\s+", " ", "".join(chars)).strip()
        return normalized or empty_fallback


@dataclass(slots=True)
class TtsSegment:
    seq: int
    text: str
    wav_bytes: bytes
    sample_rate: int
    duration_ms: int


@dataclass(slots=True)
class _EngineEntry:
    engine: Any | None
    initialized: bool
    init_error: str
    last_used_at: float
    with_zh_rules: bool


class TtsSynthesisService:
    _ZH_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")

    def __init__(
        self,
        model_dir: Path | None = None,
        sample_rate: int | None = None,
        default_en_sid: int | None = None,
        default_zh_sid: int | None = None,
    ) -> None:
        self._model_dir = Path(model_dir or Config.TTS_MODEL_DIR).expanduser()
        self._sample_rate = int(sample_rate or Config.TTS_SAMPLE_RATE)
        self._default_en_sid = int(default_en_sid if default_en_sid is not None else Config.TTS_DEFAULT_EN_SID)
        self._default_zh_sid = int(default_zh_sid if default_zh_sid is not None else Config.TTS_DEFAULT_ZH_SID)
        primary_lang = str(getattr(Config, "TTS_PRIMARY_LANG", "zh") or "zh").strip().lower()
        self._primary_lang: Literal["zh", "en"] = "en" if primary_lang == "en" else "zh"
        self._engine_idle_ttl_seconds = max(0, int(getattr(Config, "TTS_ENGINE_IDLE_TTL_SECONDS", 300)))
        self._engine_max_cached = max(1, int(getattr(Config, "TTS_ENGINE_MAX_CACHED", 2)))
        self._text_preprocessor = TextPreprocessor()
        self._engines: dict[str, _EngineEntry] = {}
        self._engine_lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def model_descriptor(self) -> dict:
        cached_languages = sorted(lang for lang, entry in self._engines.items() if entry.engine is not None)
        first_error = ""
        for entry in self._engines.values():
            if entry.init_error:
                first_error = entry.init_error
                break
        
        model_exists = (self._model_dir / "model.onnx").is_file()

        return {
            "engine": "sherpa-onnx-kokoro",
            "model_dir": str(self._model_dir),
            "sample_rate": self._sample_rate,
            "ready": model_exists and not bool(first_error),
            "error": first_error,
            "primary_lang": self._primary_lang,
            "cached_languages": cached_languages,
            "engine_idle_ttl_seconds": self._engine_idle_ttl_seconds,
        }

    def split_sentences(self, text: str, max_chars: int = 120) -> List[str]:
        normalized = self._text_preprocessor.normalize(text, empty_fallback="", use_nfkc=False)
        if not normalized:
            return []
        paragraphs = re.split(r"\n+", normalized)
        sentences: List[str] = []
        for paragraph in paragraphs:
            part = paragraph.strip()
            if not part:
                continue
            for sentence in self._split_paragraph(part):
                sentences.extend(self._chunk_sentence(sentence, max_chars=max_chars))
        return sentences

    def _split_paragraph(self, text: str) -> List[str]:
        boundaries = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=(?:[\"'“”‘’(\[]\s*)?[A-Z\u4e00-\u9fff])")
        chunks = boundaries.split(text)
        return [item.strip() for item in chunks if item and item.strip()]

    def _chunk_sentence(self, text: str, max_chars: int) -> List[str]:
        payload = text.strip()
        if not payload:
            return []
        if len(payload) <= max_chars:
            return [payload]
        chunks: List[str] = []
        rest = payload
        while len(rest) > max_chars:
            window = rest[: max_chars + 1]
            split_at = self._best_split_index(window, max_chars=max_chars)
            head = rest[:split_at].strip()
            if head:
                chunks.append(head)
            rest = rest[split_at:].strip()
            if not rest:
                break
        if rest:
            chunks.append(rest)
        return chunks

    def _best_split_index(self, text: str, max_chars: int) -> int:
        cut_points = [
            text.rfind("，"),
            text.rfind(","),
            text.rfind("、"),
            text.rfind("；"),
            text.rfind(";"),
            text.rfind(" "),
        ]
        preferred = max(cut_points)
        if preferred >= max(8, max_chars // 3):
            return preferred + 1
        return max_chars

    def synthesize(self, text: str, voice: str = "", sid: int | None = None) -> List[TtsSegment]:
        return list(self.iter_synthesize(text=text, voice=voice, sid=sid))

    def iter_synthesize(self, text: str, voice: str = "", sid: int | None = None) -> Iterator[TtsSegment]:
        sentences = self.split_sentences(text=text)
        if not sentences:
            return
        resolved_lang = self._resolve_lang(text=text)
        resolved_sid = self._resolve_sid(text=text, voice=voice, sid=sid)
        for index, item in enumerate(sentences, start=1):
            yield self._synthesize_segment(seq=index, text=item, sid=resolved_sid, lang=resolved_lang)

    def _synthesize_segment(self, seq: int, text: str, sid: int, lang: Literal["zh", "en"]) -> TtsSegment:
        normalized_text = self._normalize_tts_text(text)
        pcm_samples, sample_rate = self._generate_pcm_samples(text=normalized_text, sid=sid, lang=lang)
        wav_bytes = self._to_wav_bytes(samples=pcm_samples, sample_rate=sample_rate)
        duration_ms = max(1, int(round(len(pcm_samples) * 1000 / sample_rate)))
        return TtsSegment(
            seq=seq,
            text=normalized_text,
            wav_bytes=wav_bytes,
            sample_rate=sample_rate,
            duration_ms=duration_ms,
        )

    def _generate_pcm_samples(self, text: str, sid: int, lang: Literal["zh", "en"]) -> tuple[List[int], int]:
        engine = self._get_engine(lang=lang)
        generated = None
        try:
            generated = engine.generate(text=text, sid=sid)
        except TypeError:
            generated = engine.generate(text, sid=sid)
        if generated is None:
            raise RuntimeError("sherpa-onnx returned empty audio")
        samples = self._extract_samples(generated)
        sample_rate = int(getattr(generated, "sample_rate", 0) or getattr(engine, "sample_rate", 0) or self._sample_rate)
        if sample_rate <= 0:
            sample_rate = self._sample_rate
        self._sample_rate = sample_rate
        return samples, sample_rate

    def _extract_samples(self, generated: Any) -> List[int]:
        raw_samples = getattr(generated, "samples", None)
        if raw_samples is None:
            raw_samples = getattr(generated, "audio", None)
        if raw_samples is None:
            raise RuntimeError("sherpa-onnx generated audio has no samples field")
        pcm: List[int] = []
        non_finite_count = 0
        for value in raw_samples:
            float_value: float | None = None
            if not isinstance(value, (int, bool)):
                try:
                    float_value = float(value)
                except (TypeError, ValueError):
                    float_value = None
            if float_value is not None:
                if not math.isfinite(float_value):
                    non_finite_count += 1
                    int_value = 0
                    pcm.append(int_value)
                    continue
                if -1.5 <= float_value <= 1.5:
                    int_value = int(round(max(-1.0, min(1.0, float_value)) * 32767))
                else:
                    int_value = int(round(float_value))
            else:
                int_value = int(value)
            if int_value < -32768:
                int_value = -32768
            elif int_value > 32767:
                int_value = 32767
            pcm.append(int_value)
        if not pcm:
            raise RuntimeError("sherpa-onnx generated empty samples")
        if non_finite_count == len(pcm):
            raise RuntimeError("sherpa-onnx generated non-finite samples only; model may be incompatible")
        return pcm

    def _normalize_tts_text(self, text: str) -> str:
        return self._text_preprocessor.normalize(text)

    def _to_wav_bytes(self, samples: List[int], sample_rate: int) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            frames = bytearray()
            for value in samples:
                frames.extend(int(value).to_bytes(2, byteorder="little", signed=True))
            wav_file.writeframes(bytes(frames))
        return buffer.getvalue()

    def _resolve_sid(self, text: str, voice: str, sid: int | None) -> int:
        if sid is not None:
            candidate = int(sid)
            if candidate < 0:
                raise ValueError("sid must be >= 0")
            return candidate
        voice_text = str(voice or "").strip()
        if voice_text.isdigit():
            return int(voice_text)
        if self._resolve_lang(text=text) == "zh":
            return self._default_zh_sid
        return self._default_en_sid

    def _resolve_lang(self, text: str) -> Literal["zh", "en"]:
        if self._ZH_CHAR_PATTERN.search(text):
            return "zh"
        return "en"

    def _get_engine(self, *, lang: Literal["zh", "en"]) -> Any:
        now = time.monotonic()
        self._recycle_idle_engines(now=now, protect_lang=lang)
        with self._engine_lock:
            entry = self._engines.get(lang)
            if entry is None:
                entry = _EngineEntry(
                    engine=None,
                    initialized=False,
                    init_error="",
                    last_used_at=now,
                    with_zh_rules=lang == "zh",
                )
                self._engines[lang] = entry
            if entry.engine is not None:
                entry.last_used_at = now
                return entry.engine
            if entry.initialized and entry.engine is None:
                raise RuntimeError(entry.init_error or f"sherpa-onnx {lang} engine is unavailable")
            entry.initialized = True
            entry.last_used_at = now
            try:
                entry.engine = self._create_engine(lang=lang)
                entry.init_error = ""
                self._enforce_cache_limit_locked(protect_lang=lang)
                return entry.engine
            except Exception as err:
                entry.init_error = str(err)
                raise RuntimeError(f"sherpa-onnx kokoro init failed ({lang}): {err}") from err

    def _recycle_idle_engines(self, *, now: float, protect_lang: str | None = None) -> None:
        if self._engine_idle_ttl_seconds <= 0:
            return
        with self._engine_lock:
            stale_keys: List[str] = []
            for lang, entry in self._engines.items():
                if protect_lang and lang == protect_lang:
                    continue
                idle_seconds = now - entry.last_used_at
                if idle_seconds > self._engine_idle_ttl_seconds:
                    stale_keys.append(lang)
            for lang in stale_keys:
                self._engines.pop(lang, None)

    def _enforce_cache_limit_locked(self, *, protect_lang: str) -> None:
        cached_keys = [lang for lang, entry in self._engines.items() if entry.engine is not None]
        while len(cached_keys) > self._engine_max_cached:
            evictable = [
                (lang, self._engines[lang].last_used_at)
                for lang in cached_keys
                if lang != protect_lang
            ]
            if not evictable:
                break
            evict_lang = sorted(evictable, key=lambda item: item[1])[0][0]
            self._engines.pop(evict_lang, None)
            cached_keys = [lang for lang, entry in self._engines.items() if entry.engine is not None]

    def _create_engine(self, *, lang: Literal["zh", "en"]) -> Any:
        try:
            import sherpa_onnx
        except Exception as err:
            raise RuntimeError(f"missing sherpa-onnx dependency: {err}") from err

        model_path = self._resolve_model_path()
        voices_path = self._must_exist("voices.bin")
        tokens_path = self._must_exist("tokens.txt")
        data_dir = self._must_exist_dir("espeak-ng-data")
        dict_dir = self._model_dir / "dict"
        lexicon_paths = [self._model_dir / "lexicon-us-en.txt", self._model_dir / "lexicon-gb-en.txt", self._model_dir / "lexicon-zh.txt"]
        lexicon_arg = ",".join(str(item) for item in lexicon_paths if item.is_file())
        rule_fsts = ""
        if lang == "zh":
            rule_fst_candidates = [self._model_dir / "phone-zh.fst", self._model_dir / "date-zh.fst", self._model_dir / "number-zh.fst"]
            rule_fsts = ",".join(str(item) for item in rule_fst_candidates if item.is_file())

        kokoro_kwargs: dict[str, Any] = {
            "model": str(model_path),
            "voices": str(voices_path),
            "tokens": str(tokens_path),
            "data_dir": str(data_dir),
        }
        if lexicon_arg:
            kokoro_kwargs["lexicon"] = lexicon_arg
        if dict_dir.is_dir():
            kokoro_kwargs["dict_dir"] = str(dict_dir)

        try:
            kokoro_config = sherpa_onnx.OfflineTtsKokoroModelConfig(**kokoro_kwargs)
        except TypeError:
            fallback_kwargs = dict(kokoro_kwargs)
            fallback_kwargs.pop("dict_dir", None)
            fallback_kwargs.pop("lexicon", None)
            kokoro_config = sherpa_onnx.OfflineTtsKokoroModelConfig(**fallback_kwargs)

        try:
            model_config = sherpa_onnx.OfflineTtsModelConfig(kokoro=kokoro_config, num_threads=1, provider="cpu")
        except TypeError:
            model_config = sherpa_onnx.OfflineTtsModelConfig(kokoro=kokoro_config)

        tts_config_kwargs: dict[str, Any] = {"model": model_config}
        if rule_fsts:
            tts_config_kwargs["rule_fsts"] = rule_fsts
        try:
            tts_config = sherpa_onnx.OfflineTtsConfig(**tts_config_kwargs)
        except TypeError:
            tts_config_kwargs.pop("rule_fsts", None)
            tts_config = sherpa_onnx.OfflineTtsConfig(**tts_config_kwargs)

        validate = getattr(tts_config, "validate", None)
        if callable(validate) and not bool(validate()):
            raise RuntimeError("invalid sherpa-onnx tts config")

        return sherpa_onnx.OfflineTts(tts_config)

    def _resolve_model_path(self) -> Path:
        model_path = self._model_dir / "model.onnx"
        if model_path.is_file():
            return model_path
        raise RuntimeError(f"kokoro model.onnx not found in {self._model_dir}")

    def _must_exist(self, filename: str) -> Path:
        path = self._model_dir / filename
        if path.is_file():
            return path
        raise RuntimeError(f"kokoro file not found: {path}")

    def _must_exist_dir(self, dirname: str) -> Path:
        path = self._model_dir / dirname
        if path.is_dir():
            return path
        raise RuntimeError(f"kokoro dir not found: {path}")


_tts_synthesis_service: TtsSynthesisService | None = None


def get_tts_synthesis_service() -> TtsSynthesisService:
    global _tts_synthesis_service
    if _tts_synthesis_service is None:
        _tts_synthesis_service = TtsSynthesisService()
    return _tts_synthesis_service
