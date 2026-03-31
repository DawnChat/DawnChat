"""
数据库存储实现 (基于 SQLModel + SQLite)

用于存储结构化数据（用户信息、历史记录等）。
"""

import asyncio
from pathlib import Path
from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select

from ..utils.logger import get_logger
from .base import BaseDBStorage

logger = get_logger(__name__)

T = TypeVar('T', bound=SQLModel)


class SQLModelDBStorage(BaseDBStorage[T], Generic[T]):
    """
    基于 SQLModel 的数据库存储实现
    
    特点：
    - 使用 SQLite 数据库
    - 类型安全的 ORM 操作
    - 在 async 场景通过 asyncio.to_thread 封装同步会话
    - Pydantic 数据验证
    """
    
    def __init__(self, db_path: Path, model_class: Type[T], *, ensure_schema: bool = True):
        """
        初始化 SQLModel 数据库存储
        
        Args:
            db_path: 数据库文件路径（如 dawnchat.db）
            model_class: SQLModel 模型类
            ensure_schema: 是否在初始化时自动执行 schema 创建
        """
        super().__init__(db_path)
        self.model_class = model_class
        
        # 创建同步引擎（用于初始化和同步操作）
        self._sync_engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,  # 生产环境关闭 SQL 日志
            connect_args={"check_same_thread": False}
        )
        
        if ensure_schema:
            self._create_tables()
        
        logger.info(f"SQLModel 数据库已初始化: {db_path}, 模型={model_class.__name__}")
    
    def _create_tables(self) -> None:
        """创建数据库表"""
        try:
            SQLModel.metadata.create_all(self._sync_engine)
            logger.debug(f"数据库表已创建: {self.model_class.__name__}")
        except Exception as e:
            logger.error(f"创建数据库表失败: {e}", exc_info=True)
            raise
    
    async def create(self, item: T) -> T:
        """
        创建记录
        
        Args:
            item: 要创建的记录
            
        Returns:
            创建后的记录（包含 ID）
        """
        def _sync_create():
            with Session(self._sync_engine) as session:
                session.add(item)
                session.commit()
                session.refresh(item)
                return item
        
        try:
            result = await asyncio.to_thread(_sync_create)
            logger.debug(f"记录已创建: {self.model_class.__name__} ID={getattr(result, 'id', None)}")
            return result
        except Exception as e:
            logger.error(f"创建记录失败: {e}", exc_info=True)
            raise
    
    async def get_by_id(self, item_id: int) -> Optional[T]:
        """
        根据 ID 获取记录
        
        Args:
            item_id: 记录 ID
            
        Returns:
            记录或 None
        """
        def _sync_get():
            with Session(self._sync_engine) as session:
                statement = select(self.model_class).where(getattr(self.model_class, "id") == item_id)
                result = session.exec(statement).first()
                return result
        
        try:
            return await asyncio.to_thread(_sync_get)
        except Exception as e:
            logger.error(f"获取记录失败 [ID={item_id}]: {e}", exc_info=True)
            return None
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        获取所有记录（分页）
        
        Args:
            skip: 跳过记录数
            limit: 限制返回数量
            
        Returns:
            记录列表
        """
        def _sync_get_all():
            with Session(self._sync_engine) as session:
                statement = select(self.model_class).offset(skip).limit(limit)
                results = session.exec(statement).all()
                return list(results)
        
        try:
            return await asyncio.to_thread(_sync_get_all)
        except Exception as e:
            logger.error(f"获取所有记录失败: {e}", exc_info=True)
            return []
    
    async def update(self, item_id: int, item: T) -> Optional[T]:
        """
        更新记录
        
        Args:
            item_id: 记录 ID
            item: 更新后的数据
            
        Returns:
            更新后的记录或 None
        """
        def _sync_update():
            with Session(self._sync_engine) as session:
                # 获取现有记录
                statement = select(self.model_class).where(getattr(self.model_class, "id") == item_id)
                db_item = session.exec(statement).first()
                
                if not db_item:
                    return None
                
                # 更新字段
                if hasattr(item, "model_dump"):
                    item_data = item.model_dump(exclude_unset=True)
                else:
                    item_data = item.dict(exclude_unset=True)
                for key, value in item_data.items():
                    setattr(db_item, key, value)
                
                session.add(db_item)
                session.commit()
                session.refresh(db_item)
                return db_item
        
        try:
            result = await asyncio.to_thread(_sync_update)
            if result:
                logger.debug(f"记录已更新: {self.model_class.__name__} ID={item_id}")
            return result
        except Exception as e:
            logger.error(f"更新记录失败 [ID={item_id}]: {e}", exc_info=True)
            return None
    
    async def delete(self, item_id: int) -> bool:
        """
        删除记录
        
        Args:
            item_id: 记录 ID
            
        Returns:
            是否删除成功
        """
        def _sync_delete():
            with Session(self._sync_engine) as session:
                statement = select(self.model_class).where(getattr(self.model_class, "id") == item_id)
                item = session.exec(statement).first()
                
                if not item:
                    return False
                
                session.delete(item)
                session.commit()
                return True
        
        try:
            result = await asyncio.to_thread(_sync_delete)
            if result:
                logger.info(f"记录已删除: {self.model_class.__name__} ID={item_id}")
            return result
        except Exception as e:
            logger.error(f"删除记录失败 [ID={item_id}]: {e}", exc_info=True)
            return False
    
    async def count(self) -> int:
        """
        统计记录数
        
        Returns:
            记录总数
        """
        def _sync_count():
            with Session(self._sync_engine) as session:
                statement = select(func.count()).select_from(self.model_class)
                return int(session.exec(statement).one())
        
        try:
            return await asyncio.to_thread(_sync_count)
        except Exception as e:
            logger.error(f"统计记录失败: {e}", exc_info=True)
            return 0
    
    def close(self) -> None:
        """关闭数据库连接"""
        try:
            self._sync_engine.dispose()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}", exc_info=True)
    
    def __del__(self):
        """析构函数 - 确保资源释放"""
        self.close()
