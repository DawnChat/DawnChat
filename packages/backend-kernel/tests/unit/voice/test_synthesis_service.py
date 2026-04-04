from decimal import Decimal
from io import BytesIO
from pathlib import Path
import wave

import pytest

from app.voice.synthesis_service import TextPreprocessor, TtsSynthesisService


class _GeneratedAudio:
    def __init__(self) -> None:
        self.samples = [0.0, 0.1, -0.1, 0.0]
        self.sample_rate = 24000


class _EngineStub:
    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.last_sid = None

    def generate(self, *args, **kwargs):
        sid = kwargs.get("sid")
        if sid is None and len(args) > 1:
            sid = args[1]
        self.last_sid = sid
        return _GeneratedAudio()


def _build_service(monkeypatch: pytest.MonkeyPatch) -> tuple[TtsSynthesisService, dict[str, _EngineStub]]:
    service = TtsSynthesisService(model_dir=Path("/tmp/kokoro-test-model"))
    engines: dict[str, _EngineStub] = {}

    def _fake_create_engine(*, lang: str):
        engine = engines.get(lang)
        if engine is not None:
            return engine
        engine = _EngineStub(lang=lang)
        engines[lang] = engine
        return engine

    monkeypatch.setattr(service, "_create_engine", _fake_create_engine)
    return service, engines


def test_synthesize_uses_default_english_sid(monkeypatch: pytest.MonkeyPatch) -> None:
    service, engines = _build_service(monkeypatch)
    segments = service.synthesize("hello world")
    assert segments
    assert engines["en"].last_sid == 1


def test_synthesize_uses_default_chinese_sid(monkeypatch: pytest.MonkeyPatch) -> None:
    service, engines = _build_service(monkeypatch)
    segments = service.synthesize("你好，世界")
    assert segments
    assert engines["zh"].last_sid == 6


def test_synthesize_explicit_sid_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    service, engines = _build_service(monkeypatch)
    segments = service.synthesize("hello", sid=8)
    assert segments
    assert engines["en"].last_sid == 8


def test_synthesize_generates_valid_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _build_service(monkeypatch)
    segment = service.synthesize("hello")[0]
    buffer = BytesIO(segment.wav_bytes)
    with wave.open(buffer, "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1


def test_iter_synthesize_streams_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _build_service(monkeypatch)
    segments = list(service.iter_synthesize("第一句。第二句。"))
    assert len(segments) == 2
    assert segments[0].seq == 1
    assert segments[1].seq == 2


def test_split_sentences_handles_mixed_language_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _build_service(monkeypatch)
    text = "你好，DawnChat! Please review this change. 然后继续下一步。Final check?"
    segments = service.split_sentences(text)
    assert segments == [
        "你好，DawnChat!",
        "Please review this change.",
        "然后继续下一步。",
        "Final check?",
    ]


def test_split_sentences_chunks_long_text_with_soft_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _build_service(monkeypatch)
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    segments = service.split_sentences(text, max_chars=20)
    assert segments == [
        "alpha beta gamma",
        "delta epsilon zeta",
        "eta theta iota kappa",
        "lambda",
    ]


def test_resolve_model_path_prefers_fp32_model(tmp_path: Path) -> None:
    (tmp_path / "model.int8.onnx").write_bytes(b"int8")
    (tmp_path / "model.onnx").write_bytes(b"fp32")
    service = TtsSynthesisService(model_dir=tmp_path)
    assert service._resolve_model_path() == tmp_path / "model.onnx"


def test_resolve_model_path_rejects_int8_only_model(tmp_path: Path) -> None:
    (tmp_path / "model.int8.onnx").write_bytes(b"int8")
    service = TtsSynthesisService(model_dir=tmp_path)
    with pytest.raises(RuntimeError, match="model.onnx"):
        service._resolve_model_path()


def test_extract_samples_supports_decimal_like_float_values() -> None:
    service = TtsSynthesisService(model_dir=Path("/tmp/kokoro-test-model"))
    generated = type("Generated", (), {"samples": [Decimal("0.5"), Decimal("-0.5"), Decimal("0.0")]})()
    samples = service._extract_samples(generated)
    assert samples[0] > 10000
    assert samples[1] < -10000
    assert samples[2] == 0


def test_extract_samples_replaces_non_finite_values() -> None:
    service = TtsSynthesisService(model_dir=Path("/tmp/kokoro-test-model"))
    generated = type("Generated", (), {"samples": [0.25, float("nan"), float("inf"), float("-inf")]})()
    samples = service._extract_samples(generated)
    assert samples[0] > 0
    assert samples[1:] == [0, 0, 0]


def test_extract_samples_raises_when_all_non_finite() -> None:
    service = TtsSynthesisService(model_dir=Path("/tmp/kokoro-test-model"))
    generated = type("Generated", (), {"samples": [float("nan"), float("inf"), float("-inf")]})()
    with pytest.raises(RuntimeError, match="non-finite samples only"):
        service._extract_samples(generated)


def test_normalize_tts_text_replaces_symbol_tokens() -> None:
    service = TtsSynthesisService(model_dir=Path("/tmp/kokoro-test-model"))
    normalized = service._normalize_tts_text("Hello ❓ world ❗")
    assert normalized == "Hello ? world !"


def test_split_sentences_normalizes_special_punctuation(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _build_service(monkeypatch)
    segments = service.split_sentences("Hello❓ Next step❗")
    assert segments == ["Hello?", "Next step!"]


def test_text_preprocessor_normalizes_fullwidth_and_control_chars() -> None:
    preprocessor = TextPreprocessor()
    normalized = preprocessor.normalize("ＡＢＣ\t１２３\u0007❕")
    assert normalized == "ABC 123 !"


def test_english_text_with_number_routes_to_en_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    service, engines = _build_service(monkeypatch)
    service.synthesize("Version 2.1 released in 2026")
    assert "en" in engines
    assert "zh" not in engines


def test_chinese_text_with_number_routes_to_zh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    service, engines = _build_service(monkeypatch)
    service.synthesize("今天是2026年3月")
    assert "zh" in engines
    assert "en" not in engines


def test_idle_ttl_recycles_zh_and_en_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _build_service(monkeypatch)
    service._engine_idle_ttl_seconds = 5
    fake_now = [100.0]
    monkeypatch.setattr("app.voice.synthesis_service.time.monotonic", lambda: fake_now[0])
    service.synthesize("Version 2.1 released in 2026")
    service.synthesize("今天是2026年3月")
    assert set(service._engines.keys()) == {"en", "zh"}

    fake_now[0] = 107.0
    service.synthesize("Hello again")
    assert "zh" not in service._engines
    assert "en" in service._engines

    fake_now[0] = 114.0
    service.synthesize("你好")
    assert "en" not in service._engines
    assert "zh" in service._engines


def test_engine_init_failure_is_isolated_by_language(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TtsSynthesisService(model_dir=Path("/tmp/kokoro-test-model"))

    def _fake_create_engine(*, lang: str):
        if lang == "en":
            raise RuntimeError("en init failed")
        return _EngineStub(lang=lang)

    monkeypatch.setattr(service, "_create_engine", _fake_create_engine)

    with pytest.raises(RuntimeError, match="en"):
        service.synthesize("Version 2.1 released in 2026")

    segments = service.synthesize("今天是2026年3月")
    assert segments
