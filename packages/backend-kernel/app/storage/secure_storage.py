"""
安全存储实现

用于存储敏感信息（API Keys、Token、密码等）。
优先使用系统 keyring，当不可用时自动降级到内存存储。
"""

import asyncio
from typing import Optional

from ..utils.logger import get_logger
from .base import BaseSecureStorage

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


def create_secure_storage(namespace: str = "DawnChat") -> BaseSecureStorage:
    """
    创建安全存储实例（自动选择最佳实现）
    
    优先级：
    1. Keyring（系统密钥管理器）
    2. Memory（仅开发/降级兜底）
    
    Args:
        namespace: 命名空间
        
    Returns:
        安全存储实例
    """
    # 优先尝试使用 keyring
    try:
        import keyring
        # 测试 keyring 是否可用
        keyring.get_password("_dawnchat_test_", "_test_")
        storage: BaseSecureStorage = KeyringSecureStorage(namespace=namespace)
        logger.info("使用 Keyring 安全存储")
        return storage
    except Exception as e:
        logger.warning(f"Keyring 不可用: {e}")
    
    # 最后降级到内存存储
    logger.error("所有安全存储都不可用，使用内存存储（不推荐）")
    return MemorySecureStorage(namespace=namespace)
