from __future__ import annotations

import argparse
import inspect
import math
from pathlib import Path
import wave

from app.config import Config


def _init_by_signature(factory, kwargs):
    try:
        return factory(**kwargs)
    except TypeError:
        pass
    try:
        signature = inspect.signature(factory)
        filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
        return factory(**filtered)
    except (TypeError, ValueError):
        optional_keys = ("tts_rule_fsts", "rule_fsts", "lexicon", "dict_dir", "data_dir")
        for key in optional_keys:
            if key not in kwargs:
                continue
            candidate = {k: v for k, v in kwargs.items() if k != key}
            try:
                return factory(**candidate)
            except TypeError:
                continue
        raise


def _resolve_model_dir(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError(f"model_dir not found: {path}")
    return path


def _to_int16(samples):
    pcm = []
    nan_count = 0
    inf_count = 0
    for value in samples:
        fv = float(value)
        if not math.isfinite(fv):
            if math.isnan(fv):
                nan_count += 1
            else:
                inf_count += 1
            fv = 0.0
        if -1.5 <= fv <= 1.5:
            iv = int(round(max(-1.0, min(1.0, fv)) * 32767))
        else:
            iv = int(round(fv))
        if iv < -32768:
            iv = -32768
        elif iv > 32767:
            iv = 32767
        pcm.append(iv)
    return pcm, nan_count, inf_count


def _write_wav(path: Path, sample_rate: int, pcm):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for value in pcm:
            frames.extend(int(value).to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--model-dir", default=str(Config.TTS_MODEL_DIR))
    parser.add_argument("--sid", type=int, default=Config.TTS_DEFAULT_EN_SID)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", default="tmp/tts-direct-smoke.wav")
    parser.add_argument("--disable-lexicon", action="store_true")
    parser.add_argument("--disable-dict-dir", action="store_true")
    args = parser.parse_args()

    import sherpa_onnx

    model_dir = _resolve_model_dir(args.model_dir)
    model_path = model_dir / "model.int8.onnx"
    if not model_path.is_file():
        model_path = model_dir / "model.onnx"
    if not model_path.is_file():
        raise RuntimeError(f"model not found in {model_dir}")
    voices_path = model_dir / "voices.bin"
    tokens_path = model_dir / "tokens.txt"
    data_dir = model_dir / "espeak-ng-data"
    dict_dir = model_dir / "dict"
    lexicons = [model_dir / "lexicon-us-en.txt", model_dir / "lexicon-gb-en.txt", model_dir / "lexicon-zh.txt"]
    lexicon_arg = ",".join(str(item) for item in lexicons if item.is_file())
    rule_fsts = ",".join(str(item) for item in [model_dir / "date-zh.fst", model_dir / "number-zh.fst"] if item.is_file())

    kokoro_kwargs = {
        "model": str(model_path),
        "voices": str(voices_path),
        "tokens": str(tokens_path),
        "data_dir": str(data_dir),
    }
    if lexicon_arg and not args.disable_lexicon:
        kokoro_kwargs["lexicon"] = lexicon_arg
    if dict_dir.is_dir() and not args.disable_dict_dir:
        kokoro_kwargs["dict_dir"] = str(dict_dir)
    kokoro_config = _init_by_signature(sherpa_onnx.OfflineTtsKokoroModelConfig, kokoro_kwargs)
    model_config = _init_by_signature(sherpa_onnx.OfflineTtsModelConfig, {"kokoro": kokoro_config})
    tts_cfg_kwargs = {"model": model_config}
    if rule_fsts:
        tts_cfg_kwargs["rule_fsts"] = rule_fsts
        tts_cfg_kwargs["tts_rule_fsts"] = rule_fsts
    tts_config = _init_by_signature(sherpa_onnx.OfflineTtsConfig, tts_cfg_kwargs)
    if hasattr(tts_config, "validate") and callable(tts_config.validate) and not tts_config.validate():
        raise RuntimeError("invalid sherpa_onnx tts config")

    tts = sherpa_onnx.OfflineTts(tts_config)
    generation_config = sherpa_onnx.GenerationConfig()
    generation_config.sid = args.sid
    generation_config.speed = args.speed
    generation_config.silence_scale = 0.2
    audio = tts.generate(args.text, generation_config)
    samples = getattr(audio, "samples", None)
    if samples is None:
        raise RuntimeError("audio.samples is missing")
    sample_rate = int(getattr(audio, "sample_rate", 0) or 24000)
    pcm, nan_count, inf_count = _to_int16(samples)
    if not pcm:
        raise RuntimeError("generated audio is empty")
    output = Path(args.output).expanduser().resolve()
    _write_wav(output, sample_rate, pcm)
    print(f"output={output}")
    print(f"sample_rate={sample_rate} samples={len(pcm)} nan={nan_count} inf={inf_count}")
    print(f"min={min(pcm)} max={max(pcm)}")


if __name__ == "__main__":
    main()
