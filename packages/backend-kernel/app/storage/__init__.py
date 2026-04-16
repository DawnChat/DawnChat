"""
存储模块

提供统一的数据存储接口，支持：
- KV 存储（配置）
- 安全存储（API Keys、密码）
- 数据库存储（结构化数据）

使用示例：

```python
from app.storage import storage_manager

# 配置存储
await storage_manager.set_config("theme", "dark")
theme = await storage_manager.get_config("theme")

# API 密钥存储
await storage_manager.set_api_key("openai", "sk-...")
api_key = await storage_manager.get_api_key("openai")

# 用户管理
user = await storage_manager.create_user("john", "john@example.com")
```
"""

from .db_storage import SQLModelDBStorage
from .kv_storage import SQLiteKVStorage, TinyDBKVStorage
from .manager import StorageManager, storage_manager
from .models import APIKey, User, UserPreference
from .secure_storage import (
    KeyringSecureStorage,
    LocalEncryptedSecureStorage,
    MemorySecureStorage,
    create_secure_storage,
)

__all__ = [
    # 管理器
    "StorageManager",
    "storage_manager",
    
    # 存储实现
    "SQLiteKVStorage",
    "TinyDBKVStorage",
    "KeyringSecureStorage",
    "LocalEncryptedSecureStorage",
    "MemorySecureStorage",
    "create_secure_storage",
    "SQLModelDBStorage",
    
    # 数据模型
    "User",
    "APIKey",
    "UserPreference",
]

