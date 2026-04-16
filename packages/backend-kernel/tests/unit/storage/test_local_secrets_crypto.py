import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.storage.local_secrets_crypto import (
    LocalSecretEnvelopeError,
    LocalSecretMasterKeyError,
    LocalSecretsCrypto,
    decrypt_from_envelope_dict,
    encrypt_to_envelope_dict,
    envelope_dict_to_json,
    envelope_json_to_dict,
    load_or_create_fernet,
    secure_storage_key_to_filename,
)


def test_load_or_create_fernet_generates_and_reuses(tmp_path: Path) -> None:
    master = tmp_path / "fernet_master.key"
    f1 = load_or_create_fernet(master)
    assert master.is_file()
    f2 = load_or_create_fernet(master)
    env = encrypt_to_envelope_dict(f1, "sk-secret-value")
    assert env["v"] == 1
    assert env["alg"] == "fernet"
    assert decrypt_from_envelope_dict(f2, env) == "sk-secret-value"


def test_load_or_create_fernet_rejects_empty_file(tmp_path: Path) -> None:
    master = tmp_path / "fernet_master.key"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_text("   \n", encoding="utf-8")
    with pytest.raises(LocalSecretMasterKeyError):
        load_or_create_fernet(master)


def test_load_or_create_fernet_rejects_invalid_key_material(tmp_path: Path) -> None:
    master = tmp_path / "fernet_master.key"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_text("not-a-fernet-key", encoding="utf-8")
    with pytest.raises(LocalSecretMasterKeyError):
        load_or_create_fernet(master)


def test_decrypt_envelope_wrong_version() -> None:
    f = Fernet(Fernet.generate_key())
    with pytest.raises(LocalSecretEnvelopeError):
        decrypt_from_envelope_dict(f, {"v": 99, "alg": "fernet", "payload": "x"})


def test_decrypt_envelope_invalid_json() -> None:
    f = Fernet(Fernet.generate_key())
    with pytest.raises(LocalSecretEnvelopeError):
        envelope_json_to_dict("not json")


def test_decrypt_envelope_tampered_payload(tmp_path: Path) -> None:
    master = tmp_path / "k"
    fer = load_or_create_fernet(master)
    env = encrypt_to_envelope_dict(fer, "hello")
    env["payload"] = env["payload"][:-4] + "xxxx"
    with pytest.raises(LocalSecretEnvelopeError):
        decrypt_from_envelope_dict(fer, env)


def test_local_secrets_crypto_roundtrip(tmp_path: Path) -> None:
    master = tmp_path / "fernet_master.key"
    crypto = LocalSecretsCrypto(master)
    blob = crypto.encrypt_string(" api \n")
    assert crypto.decrypt_string(blob) == "api"


def test_secure_storage_key_to_filename() -> None:
    assert secure_storage_key_to_filename("openai_api_key") == "openai_api_key.json"
    escaped = secure_storage_key_to_filename("a/../b")
    assert "/" not in escaped
    assert escaped.endswith(".json")


@pytest.mark.asyncio
async def test_local_encrypted_secure_storage_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.config import Config
    from app.storage.secure_storage import LocalEncryptedSecureStorage

    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    store = LocalEncryptedSecureStorage(namespace="DawnChat")
    await store.set("openai_api_key", "sk-test-key-at-least-ten-chars")
    assert await store.get("openai_api_key") == "sk-test-key-at-least-ten-chars"
    assert await store.exists("openai_api_key") is True
    assert await store.delete("openai_api_key") is True
    assert await store.get("openai_api_key") is None
    assert await store.exists("openai_api_key") is False


@pytest.mark.asyncio
async def test_create_secure_storage_default_is_local_fernet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import Config
    from app.storage import secure_storage as ss

    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("DAWNCHAT_API_KEY_SECURE_BACKEND", "local_fernet")
    s = ss.create_secure_storage()
    assert type(s).__name__ == "LocalEncryptedSecureStorage"


@pytest.mark.asyncio
async def test_create_secure_storage_keychain_falls_back_when_keyring_init_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import Config
    from app.storage import secure_storage as ss

    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("DAWNCHAT_API_KEY_SECURE_BACKEND", "keychain")

    class _BrokenKeyring:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("keyring unavailable in test")

    monkeypatch.setattr(ss, "KeyringSecureStorage", _BrokenKeyring)
    s = ss.create_secure_storage()
    assert type(s).__name__ == "LocalEncryptedSecureStorage"


def test_envelope_json_roundtrip() -> None:
    f = Fernet(Fernet.generate_key())
    env = encrypt_to_envelope_dict(f, "x" * 20)
    raw = envelope_dict_to_json(env)
    parsed = envelope_json_to_dict(raw)
    assert decrypt_from_envelope_dict(f, parsed) == "x" * 20
    assert isinstance(json.loads(raw), dict)
