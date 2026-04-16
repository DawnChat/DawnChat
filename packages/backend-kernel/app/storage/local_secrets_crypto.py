"""
本地对称加密（Fernet）工具

用于在 DATA_DIR 下加密敏感字符串；主密钥与密文同机存储，不防逆向与本地恶意进程。
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

_ENVELOPE_VERSION = 1
_ALG_FERNET = "fernet"


class LocalSecretMasterKeyError(Exception):
    """主密钥文件缺失、损坏或无法解析。"""


class LocalSecretEnvelopeError(Exception):
    """密文封装格式或算法版本不支持。"""


def _fernet_from_master_key_material(raw: bytes) -> Fernet:
    try:
        return Fernet(raw)
    except (ValueError, TypeError) as e:
        raise LocalSecretMasterKeyError("invalid Fernet master key material") from e


def load_or_create_fernet(master_key_path: Path) -> Fernet:
    """
    读取主密钥文件；不存在则生成并写入（权限 0600，尽力而为）。
    """
    master_key_path.parent.mkdir(parents=True, exist_ok=True)
    if master_key_path.is_file():
        text = master_key_path.read_text(encoding="utf-8").strip()
        if not text:
            raise LocalSecretMasterKeyError("fernet master key file is empty")
        raw = text.encode("ascii")
        return _fernet_from_master_key_material(raw)

    key = Fernet.generate_key()
    master_key_path.write_bytes(key + b"\n")
    try:
        master_key_path.chmod(0o600)
    except OSError:
        pass
    return Fernet(key)


def encrypt_to_envelope_dict(fernet: Fernet, plaintext: str) -> dict[str, Any]:
    token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return {"v": _ENVELOPE_VERSION, "alg": _ALG_FERNET, "payload": token}


def decrypt_from_envelope_dict(fernet: Fernet, envelope: dict[str, Any]) -> str:
    if envelope.get("v") != _ENVELOPE_VERSION:
        raise LocalSecretEnvelopeError(f"unsupported envelope v={envelope.get('v')!r}")
    if envelope.get("alg") != _ALG_FERNET:
        raise LocalSecretEnvelopeError(f"unsupported alg={envelope.get('alg')!r}")
    payload = envelope.get("payload")
    if not isinstance(payload, str) or not payload:
        raise LocalSecretEnvelopeError("missing payload")
    try:
        return fernet.decrypt(payload.encode("ascii")).decode("utf-8").strip()
    except InvalidToken as e:
        raise LocalSecretEnvelopeError("fernet decrypt failed") from e


def envelope_dict_to_json(envelope: dict[str, Any]) -> str:
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def envelope_json_to_dict(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LocalSecretEnvelopeError("invalid envelope json") from e
    if not isinstance(data, dict):
        raise LocalSecretEnvelopeError("envelope must be a json object")
    return data


def secure_storage_key_to_filename(key: str) -> str:
    """将安全存储键映射为文件名（仅字母数字与少量符号）。"""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", key.strip() or "key")
    return f"{safe}.json"


class LocalSecretsCrypto:
    """按主密钥路径惰性加载 Fernet，提供加解密。"""

    def __init__(self, master_key_path: Path):
        self._master_key_path = master_key_path
        self._fernet: Optional[Fernet] = None

    def fernet(self) -> Fernet:
        if self._fernet is None:
            self._fernet = load_or_create_fernet(self._master_key_path)
        return self._fernet

    def encrypt_string(self, plaintext: str) -> str:
        env = encrypt_to_envelope_dict(self.fernet(), plaintext)
        return envelope_dict_to_json(env)

    def decrypt_string(self, ciphertext: str) -> str:
        envelope = envelope_json_to_dict(ciphertext)
        return decrypt_from_envelope_dict(self.fernet(), envelope)
