"""
存储管理器

统一管理所有存储实例，提供便捷的访问接口。
"""

from pathlib import Path
import sqlite3
from typing import Optional

from sqlmodel import SQLModel, create_engine

from ..config import Config
from ..utils.logger import get_logger
from .db_storage import SQLModelDBStorage
from .kv_storage import SQLiteKVStorage
from .models import APIKey, User, UserPreference
from .secure_storage import create_secure_storage

logger = get_logger(__name__)


class StorageManager:
    """
    存储管理器
    
    统一管理和访问所有存储实例。
    """
    
    _instance: Optional['StorageManager'] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化存储管理器"""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # 确保存储目录存在
        Config.ensure_directories()
        
        # 初始化各类存储
        self._init_kv_storage()
        self._init_secure_storage()
        self._init_db_storage()
        
        logger.info("存储管理器已初始化")
    
    def _init_kv_storage(self) -> None:
        """初始化 KV 存储"""
        config_path = Config.DATA_DIR / "config" / "app_config.db"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_storage = SQLiteKVStorage(config_path)
        
        # 通用 KV 存储 (用于工作流定义等)
        kv_path = Config.DATA_DIR / "storage" / "kv.db"
        kv_path.parent.mkdir(parents=True, exist_ok=True)
        self.kv_storage = SQLiteKVStorage(kv_path)
        
        logger.debug(f"KV 存储已初始化: {config_path}, {kv_path}")
    
    def _init_secure_storage(self) -> None:
        """初始化安全存储（自动选择最佳实现）"""
        self.secure_storage = create_secure_storage(namespace="DawnChat")
        logger.debug("安全存储已初始化")
    
    def _init_db_storage(self) -> None:
        """初始化数据库存储"""
        db_path = Config.DATA_DIR / "database" / "dawnchat.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 集中负责 schema 初始化，避免在每个 storage 初始化时重复 create_all
        self._init_db_schema(db_path)
        self._migrate_user_preference_unique_index(db_path)

        # 初始化各个模型的存储
        self.user_storage = SQLModelDBStorage(db_path, User, ensure_schema=False)
        self.apikey_storage = SQLModelDBStorage(db_path, APIKey, ensure_schema=False)
        self.preference_storage = SQLModelDBStorage(db_path, UserPreference, ensure_schema=False)
        
        logger.debug(f"数据库存储已初始化: {db_path}")

    def _init_db_schema(self, db_path: Path) -> None:
        """初始化 SQLModel schema（仅执行一次）"""
        engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        try:
            SQLModel.metadata.create_all(engine)
        finally:
            engine.dispose()

    def _migrate_user_preference_unique_index(self, db_path: Path) -> None:
        """
        为 userpreference 添加复合唯一索引。

        兼容已有数据库：先清理重复数据（保留最大 id），再创建唯一索引。
        """
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    """
                    DELETE FROM userpreference
                    WHERE id NOT IN (
                        SELECT MAX(id) FROM userpreference GROUP BY user_id, preference_key
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_preference_key
                    ON userpreference(user_id, preference_key)
                    """
                )
                conn.commit()
        except sqlite3.OperationalError as e:
            # 表不存在时无需中断启动（首次运行由 create_all 创建）
            logger.debug(f"跳过 userpreference 唯一索引迁移: {e}")
        except Exception as e:
            logger.warning(f"userpreference 唯一索引迁移失败: {e}", exc_info=True)
    
    # ==================== 便捷方法 ====================
    
    # --- 配置存储 ---
    
    async def get_config(self, key: str, default=None):
        """获取配置"""
        value = await self.config_storage.get(key, default)
        logger.info(f"获取配置: {key}")
        return value
    
    async def set_config(self, key: str, value) -> None:
        """设置配置"""
        logger.info(f"设置配置: {key}")
        await self.config_storage.set(key, value)
    
    async def get_all_configs(self) -> dict:
        """获取所有配置"""
        return await self.config_storage.get_all()
    
    # --- 应用配置存储（别名，用于兼容 cloud_models_routes）---
    
    async def get_app_config(self, key: str, default=None):
        """获取应用配置"""
        return await self.config_storage.get(key, default)
    
    async def set_app_config(self, key: str, value) -> None:
        """设置应用配置"""
        if value is None:
            # 删除配置
            await self.config_storage.delete(key)
        else:
            await self.config_storage.set(key, value)
    
    # --- 安全存储 ---
    
    async def get_api_key(self, provider: str) -> Optional[str]:
        """
        获取 API 密钥
        
        Args:
            provider: 提供商名称（如 "openai", "anthropic"）
            
        Returns:
            API 密钥或 None
        """
        return await self.secure_storage.get(f"{provider}_api_key")
    
    async def set_api_key(self, provider: str, api_key: str) -> None:
        """
        设置 API 密钥
        
        Args:
            provider: 提供商名称
            api_key: API 密钥
        """
        await self.secure_storage.set(f"{provider}_api_key", api_key)
        logger.info(f"API 密钥已设置: {provider}")
    
    async def delete_api_key(self, provider: str) -> bool:
        """
        删除 API 密钥
        
        Args:
            provider: 提供商名称
            
        Returns:
            是否删除成功
        """
        result = await self.secure_storage.delete(f"{provider}_api_key")
        if result:
            logger.info(f"API 密钥已删除: {provider}")
        return result
    
    # --- 用户管理 ---
    
    async def create_user(self, username: str, email: Optional[str] = None, 
                         full_name: Optional[str] = None) -> User:
        """创建用户"""
        user = User(username=username, email=email, full_name=full_name)
        return await self.user_storage.create(user)
    
    async def get_user(self, user_id: int) -> Optional[User]:
        """获取用户"""
        return await self.user_storage.get_by_id(user_id)
    
    async def get_all_users(self) -> list[User]:
        """获取所有用户"""
        return await self.user_storage.get_all()
    
    # ==================== 资源清理 ====================
    
    def close(self) -> None:
        """关闭所有存储连接"""
        try:
            if hasattr(self, "config_storage"):
                self.config_storage.close()
            if hasattr(self, "kv_storage"):
                self.kv_storage.close()
            if hasattr(self, "user_storage"):
                self.user_storage.close()
            if hasattr(self, "apikey_storage"):
                self.apikey_storage.close()
            if hasattr(self, "preference_storage"):
                self.preference_storage.close()
            logger.info("所有存储连接已关闭")
        except Exception as e:
            logger.error(f"关闭存储连接失败: {e}", exc_info=True)
    
    def __del__(self):
        """析构函数"""
        self.close()


# 全局存储管理器实例
storage_manager = StorageManager()
