"""
存储抽象基类

定义了存储系统的统一接口，方便将来更换实现。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar('T')


class BaseStorage(ABC, Generic[T]):
    """存储基类 - 定义统一接口"""
    
    def __init__(self, storage_path: Path):
        """
        初始化存储
        
        Args:
            storage_path: 存储路径（必须在系统用户目录下）
        """
        self.storage_path = storage_path
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self) -> None:
        """确保存储目录存在"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    async def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """
        获取数据
        
        Args:
            key: 键
            default: 默认值
            
        Returns:
            值或默认值
        """
        pass
    
    @abstractmethod
    async def set(self, key: str, value: T) -> None:
        """
        设置数据
        
        Args:
            key: 键
            value: 值
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        删除数据
        
        Args:
            key: 键
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """清空所有数据"""
        pass


class BaseKVStorage(BaseStorage[Any]):
    """KV 存储基类 - 用于配置等简单键值对"""
    
    @abstractmethod
    async def get_all(self) -> Dict[str, Any]:
        """获取所有键值对"""
        pass
    
    @abstractmethod
    async def set_many(self, items: Dict[str, Any]) -> None:
        """批量设置"""
        pass
    
    @abstractmethod
    async def keys(self) -> List[str]:
        """获取所有键"""
        pass


class BaseSecureStorage(ABC):
    """安全存储基类 - 用于敏感信息（API Key、Token、密码等）"""
    
    def __init__(self, namespace: str):
        """
        初始化安全存储
        
        Args:
            namespace: 命名空间（用于隔离不同应用的数据）
        """
        self.namespace = namespace
    
    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """
        获取敏感数据
        
        Args:
            key: 数据键（如 'openai_api_key', 'user_token'）
            
        Returns:
            敏感数据或 None
        """
        pass
    
    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        """
        设置敏感数据
        
        Args:
            key: 数据键
            value: 敏感数据（API Key、Token、密码等）
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        删除敏感数据
        
        Args:
            key: 数据键
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 数据键
            
        Returns:
            是否存在
        """
        pass


class BaseDBStorage(ABC, Generic[T]):
    """数据库存储基类 - 用于结构化数据"""
    
    def __init__(self, db_path: Path):
        """
        初始化数据库存储
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self) -> None:
        """确保存储目录存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    async def create(self, item: T) -> T:
        """创建记录"""
        pass
    
    @abstractmethod
    async def get_by_id(self, item_id: int) -> Optional[T]:
        """根据 ID 获取记录"""
        pass
    
    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """获取所有记录（分页）"""
        pass
    
    @abstractmethod
    async def update(self, item_id: int, item: T) -> Optional[T]:
        """更新记录"""
        pass
    
    @abstractmethod
    async def delete(self, item_id: int) -> bool:
        """删除记录"""
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """统计记录数"""
        pass

