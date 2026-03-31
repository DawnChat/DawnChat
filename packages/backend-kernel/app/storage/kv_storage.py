"""
KV 存储实现 (基于 SQLite)

用于存储应用配置、用户偏好等简单键值对数据。
替代原有的 TinyDB 实现，提供更好的并发支持和数据持久性。
"""

import asyncio
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, Optional

from ..utils.logger import get_logger
from .base import BaseKVStorage

logger = get_logger(__name__)


class SQLiteKVStorage(BaseKVStorage):
    """
    基于 SQLite 的 KV 存储实现
    
    特点：
    - 使用 SQLite 存储键值对
    - 支持并发读写 (WAL模式)
    - 数据持久性更强
    - 替代不可靠的 JSON 文件存储
    """
    
    def __init__(self, storage_path: Path):
        """
        初始化 SQLite KV 存储
        
        Args:
            storage_path: 存储文件路径（推荐以 .db 或 .sqlite 结尾）
        """
        super().__init__(storage_path)
        self._lock = threading.Lock()
        logger.info(f"Initializing SQLiteKVStorage at: {self.storage_path.absolute()}")
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        # logger.debug(f"Connecting to DB: {self.storage_path}")
        conn = sqlite3.connect(str(self.storage_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        try:
            with self._lock:
                with self._get_conn() as conn:
                    # 启用 WAL 模式以提高并发性能
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    
                    # 创建 KV 表
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS kv_store (
                            key TEXT PRIMARY KEY,
                            value TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
            logger.info(f"SQLite KV 存储已初始化: {self.storage_path}")
        except Exception as e:
            logger.error(f"SQLite 初始化失败: {e}", exc_info=True)
            raise

    async def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """获取值"""
        def _sync_get():
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,))
                    row = cursor.fetchone()
                    if row:
                        try:
                            return json.loads(row['value'])
                        except json.JSONDecodeError:
                            logger.warning(f"数据解析失败 [{key}], 返回默认值")
                            return default
                    return default
            except Exception as e:
                logger.error(f"读取失败 [{key}]: {e}")
                return default
        
        return await asyncio.to_thread(_sync_get)

    async def set(self, key: str, value: Any) -> None:
        """设置值"""
        def _sync_set():
            try:
                json_val = json.dumps(value, ensure_ascii=False)
                with self._lock:
                    with self._get_conn() as conn:
                        conn.execute("""
                            INSERT OR REPLACE INTO kv_store (key, value, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                        """, (key, json_val))
                        conn.commit()
                logger.debug(f"KV Set: {key} (len={len(json_val)})")
            except Exception as e:
                logger.error(f"写入失败 [{key}]: {e}")
                raise

        await asyncio.to_thread(_sync_set)

    async def delete(self, key: str) -> bool:
        """删除值"""
        def _sync_delete():
            try:
                with self._lock:
                    with self._get_conn() as conn:
                        cursor = conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
                        conn.commit()
                        success = cursor.rowcount > 0
                        if success:
                            logger.debug(f"KV Delete: {key}")
                        return success
            except Exception as e:
                logger.error(f"删除失败 [{key}]: {e}")
                return False

        return await asyncio.to_thread(_sync_delete)

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        def _sync_exists():
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute("SELECT 1 FROM kv_store WHERE key = ?", (key,))
                    return cursor.fetchone() is not None
            except Exception as e:
                logger.error(f"检查存在失败 [{key}]: {e}")
                return False

        return await asyncio.to_thread(_sync_exists)

    async def clear(self) -> None:
        """清空所有数据"""
        def _sync_clear():
            try:
                with self._lock:
                    with self._get_conn() as conn:
                        conn.execute("DELETE FROM kv_store")
                        conn.commit()
            except Exception as e:
                logger.error(f"清空数据失败: {e}")

        await asyncio.to_thread(_sync_clear)

    async def get_all(self) -> Dict[str, Any]:
        """获取所有键值对"""
        def _sync_get_all():
            try:
                result = {}
                with self._get_conn() as conn:
                    cursor = conn.execute("SELECT key, value FROM kv_store")
                    for row in cursor:
                        try:
                            result[row['key']] = json.loads(row['value'])
                        except json.JSONDecodeError:
                            continue
                return result
            except Exception as e:
                logger.error(f"获取所有数据失败: {e}")
                return {}

        return await asyncio.to_thread(_sync_get_all)

    async def get_many(self, keys: list[str]) -> Dict[str, Any]:
        """批量获取值"""
        def _sync_get_many():
            try:
                result = {}
                if not keys:
                    return result
                    
                with self._get_conn() as conn:
                    # SQLite limits variables, so we process in chunks
                    chunk_size = 900
                    for i in range(0, len(keys), chunk_size):
                        chunk = keys[i:i + chunk_size]
                        placeholders = ','.join(['?'] * len(chunk))
                        cursor = conn.execute(
                            f"SELECT key, value FROM kv_store WHERE key IN ({placeholders})",
                            chunk
                        )
                        for row in cursor:
                            try:
                                result[row['key']] = json.loads(row['value'])
                            except json.JSONDecodeError:
                                continue
                return result
            except Exception as e:
                logger.error(f"批量获取失败: {e}")
                return {}

        return await asyncio.to_thread(_sync_get_many)

    async def set_many(self, items: Dict[str, Any]) -> None:
        """批量设置"""
        def _sync_set_many():
            try:
                with self._lock:
                    with self._get_conn() as conn:
                        data = []
                        for k, v in items.items():
                            json_val = json.dumps(v, ensure_ascii=False)
                            data.append((k, json_val))
                        
                        conn.executemany("""
                            INSERT OR REPLACE INTO kv_store (key, value, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                        """, data)
                        conn.commit()
            except Exception as e:
                logger.error(f"批量写入失败: {e}")
                raise

        await asyncio.to_thread(_sync_set_many)

    async def keys(self, prefix: Optional[str] = None) -> list[str]:
        """获取所有键"""
        def _sync_keys():
            try:
                with self._get_conn() as conn:
                    if prefix:
                        cursor = conn.execute("SELECT key FROM kv_store WHERE key LIKE ?", (f"{prefix}%",))
                    else:
                        cursor = conn.execute("SELECT key FROM kv_store")
                    keys = [row['key'] for row in cursor]
                    # logger.debug(f"KV Keys: found {len(keys)} keys")
                    return keys
            except Exception as e:
                logger.error(f"获取所有键失败: {e}")
                return []
        return await asyncio.to_thread(_sync_keys)

    async def get_by_prefix(self, prefix: str) -> Dict[str, Any]:
        """获取指定前缀的所有键值对"""
        def _sync_get_by_prefix():
            try:
                result = {}
                with self._get_conn() as conn:
                    cursor = conn.execute("SELECT key, value FROM kv_store WHERE key LIKE ?", (f"{prefix}%",))
                    for row in cursor:
                        try:
                            result[row['key']] = json.loads(row['value'])
                        except json.JSONDecodeError:
                            continue
                return result
            except Exception as e:
                logger.error(f"获取前缀数据失败 [{prefix}]: {e}")
                return {}
        return await asyncio.to_thread(_sync_get_by_prefix)

    def close(self) -> None:
        """关闭数据库连接"""
        try:
            # 执行 WAL checkpoint 以确保数据持久化
            with self._get_conn() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.info(f"SQLiteKVStorage closed: {self.storage_path}")
        except Exception as e:
            logger.error(f"Failed to close SQLiteKVStorage: {e}")

# 保持向下兼容的别名，虽然实现已经改变
TinyDBKVStorage = SQLiteKVStorage
