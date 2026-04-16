"""
安全存储实现

用于存储敏感信息（API Keys、Token、密码等）。

默认使用 DATA_DIR 下 Fernet 本地加密文件；可通过环境变量 DAWNCHAT_API_KEY_SECURE_BACKEND=keychain
切换为系统 keyring（macOS Keychain 等）。keyring 不可用时回退到本地 Fernet。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger
from .base import BaseSecureStorage
from .local_secrets_crypto import (
    LocalSecretEnvelopeError,
    LocalSecretMasterKeyError,
    LocalSecretsCrypto,
    secure_storage_key_to_filename,
)

logger = get_logger(__name__)

class KeyringSecureStorage(BaseSecureStorage):
    """
    基于 keyring 的安全存储实现
    
    特点：
    - 使用系统密钥管理器（macOS Keychain, Windows Credential Locker, Linux Secret Service）
    - 操作系统级加密，安全可靠
    - 适合存储 API Keys、Token、密码等敏感信息
    
    注意：
    - 在某些环境下（如 PBS 打包）可能不可用
    """
    
    def __init__(self, namespace: str = "DawnChat"):
        super().__init__(namespace)
        import keyring
        self._keyring = keyring
        logger.info(f"Keyring 安全存储已初始化: namespace={namespace}")
    
    async def get(self, key: str) -> Optional[str]:
        """获取敏感数据"""
        def _sync_get():
            try:
                value = self._keyring.get_password(self.namespace, key)
                if value:
                    logger.debug(f"成功获取敏感数据: {key}")
                return value
            except Exception as e:
                logger.error(f"获取敏感数据失败 [{key}]: {e}")
                return None
        
        try:
            return await asyncio.to_thread(_sync_get)
        except Exception as e:
            logger.error(f"获取敏感数据异常 [{key}]: {e}", exc_info=True)
            return None
    
    async def set(self, key: str, value: str) -> None:
        """设置敏感数据"""
        def _sync_set():
            try:
                self._keyring.set_password(self.namespace, key, value)
                logger.info(f"敏感数据已设置: {key}")
            except Exception as e:
                logger.error(f"设置敏感数据失败 [{key}]: {e}")
                raise
        
        try:
            await asyncio.to_thread(_sync_set)
        except Exception as e:
            logger.error(f"设置敏感数据异常 [{key}]: {e}", exc_info=True)
            raise
    
    async def delete(self, key: str) -> bool:
        """删除敏感数据"""
        def _sync_delete():
            try:
                self._keyring.delete_password(self.namespace, key)
                logger.info(f"敏感数据已删除: {key}")
                return True
            except Exception as e:
                logger.warning(f"删除敏感数据失败 [{key}]: {e}")
                return False
        
        try:
            return await asyncio.to_thread(_sync_delete)
        except Exception as e:
            logger.error(f"删除敏感数据异常 [{key}]: {e}", exc_info=True)
            return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        value = await self.get(key)
        return value is not None


class MemorySecureStorage(BaseSecureStorage):
    """
    基于内存的安全存储实现（用于测试或不可用 keyring 的环境）
    
    警告：
    - 仅用于开发/测试环境
    - 数据不持久化，重启后丢失
    """
    
    def __init__(self, namespace: str = "DawnChat"):
        super().__init__(namespace)
        self._storage: dict[str, str] = {}
        logger.warning("⚠️ 使用内存存储（不安全），仅用于测试！")
    
    async def get(self, key: str) -> Optional[str]:
        return self._storage.get(key)
    
    async def set(self, key: str, value: str) -> None:
        self._storage[key] = value
        logger.debug(f"内存数据已设置: {key}")
    
    async def delete(self, key: str) -> bool:
        if key in self._storage:
            del self._storage[key]
            logger.debug(f"内存数据已删除: {key}")
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        return key in self._storage
    
    def clear(self) -> None:
        self._storage.clear()
        logger.warning("所有内存数据已清空")


class LocalEncryptedSecureStorage(BaseSecureStorage):
    """
    使用 Fernet 将敏感数据加密写入 DATA_DIR/secrets/api_keys/。

    主密钥：DATA_DIR/secrets/fernet_master.key（0600，首次写入时生成）。
    """

    def __init__(self, namespace: str = "DawnChat"):
        from ..config import Config

        super().__init__(namespace)
        Config.ensure_directories()
        self._secrets_dir = Config.DATA_DIR / "secrets"
        self._master_path = self._secrets_dir / "fernet_master.key"
        self._api_keys_dir = self._secrets_dir / "api_keys"
        self._crypto = LocalSecretsCrypto(self._master_path)
        logger.info(
            "本地 Fernet 安全存储已初始化: namespace=%s, keys_dir=%s",
            namespace,
            self._api_keys_dir,
        )

    def _path_for_key(self, key: str) -> Path:
        return self._api_keys_dir / secure_storage_key_to_filename(key)

    def _read_sync(self, path: Path) -> Optional[str]:
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            return self._crypto.decrypt_string(raw)
        except LocalSecretMasterKeyError:
            logger.error("主密钥无效，无法解密敏感数据，请检查: %s", self._master_path)
            return None
        except LocalSecretEnvelopeError as e:
            logger.error("解密本地密文失败 [%s]: %s", path.name, e)
            return None
        except OSError as e:
            logger.error("读取本地密文失败 [%s]: %s", path.name, e)
            return None

    def _write_sync(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    def _delete_sync(self, path: Path) -> bool:
        try:
            if path.is_file():
                path.unlink()
                return True
        except OSError as e:
            logger.warning("删除本地密文失败 [%s]: %s", path.name, e)
        return False

    async def get(self, key: str) -> Optional[str]:
        path = self._path_for_key(key)

        def _run() -> Optional[str]:
            return self._read_sync(path)

        try:
            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.error(f"获取敏感数据异常 [{key}]: {e}", exc_info=True)
            return None

    async def set(self, key: str, value: str) -> None:
        path = self._path_for_key(key)

        def _run() -> None:
            payload = self._crypto.encrypt_string(value)
            self._write_sync(path, payload)
            logger.info("敏感数据已设置(本地加密): %s", key)

        try:
            await asyncio.to_thread(_run)
        except LocalSecretMasterKeyError:
            logger.error("主密钥无效，无法写入敏感数据: %s", self._master_path)
            raise
        except Exception as e:
            logger.error(f"设置敏感数据异常 [{key}]: {e}", exc_info=True)
            raise

    async def delete(self, key: str) -> bool:
        path = self._path_for_key(key)

        def _run() -> bool:
            ok = self._delete_sync(path)
            if ok:
                logger.info("敏感数据已删除(本地加密): %s", key)
            return ok

        try:
            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.error(f"删除敏感数据异常 [{key}]: {e}", exc_info=True)
            return False

    async def exists(self, key: str) -> bool:
        path = self._path_for_key(key)
        return await asyncio.to_thread(lambda: path.is_file())


def create_secure_storage(namespace: str = "DawnChat") -> BaseSecureStorage:
    """
    创建安全存储实例。

    环境变量 DAWNCHAT_API_KEY_SECURE_BACKEND：
    - local_fernet（默认）：DATA_DIR/secrets 下 Fernet 加密文件
    - keychain：Python keyring；初始化失败时回退到 local_fernet
    """
    raw = os.environ.get("DAWNCHAT_API_KEY_SECURE_BACKEND", "local_fernet").strip().lower()
    backend = raw or "local_fernet"
    if backend not in ("local_fernet", "fernet", "keychain"):
        logger.warning("未知的 DAWNCHAT_API_KEY_SECURE_BACKEND=%r，使用 local_fernet", raw)
        backend = "local_fernet"

    if backend == "keychain":
        try:
            storage: BaseSecureStorage = KeyringSecureStorage(namespace=namespace)
            logger.info("使用 Keyring 安全存储 (DAWNCHAT_API_KEY_SECURE_BACKEND=keychain)")
            return storage
        except Exception as e:
            logger.warning("Keyring 不可用，回退到本地 Fernet: %s", e)

    storage = LocalEncryptedSecureStorage(namespace=namespace)
    logger.info("使用本地 Fernet 安全存储 (DAWNCHAT_API_KEY_SECURE_BACKEND=%r)", raw or "local_fernet")
    return storage
