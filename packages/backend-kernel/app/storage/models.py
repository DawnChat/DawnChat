"""
数据模型定义

定义应用中使用的数据模型。
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class TableModel(SQLModel):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)


class User(TableModel, table=True):
    """
    用户模型
    
    用于存储用户基本信息。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: Optional[str] = Field(default=None, index=True)
    full_name: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "full_name": "John Doe"
            }
        }


class APIKey(TableModel, table=True):
    """
    API 密钥模型
    
    用于存储 API 密钥元数据（实际密钥存储在 keyring 中）。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)  # 密钥名称（如 "OpenAI", "Anthropic"）
    provider: str  # 提供商（如 "openai", "anthropic"）
    username: str  # keyring 中的 username（用于检索实际密钥）
    description: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "OpenAI Production Key",
                "provider": "openai",
                "username": "openai_api_key_prod",
                "description": "主要的 OpenAI API 密钥"
            }
        }


class UserPreference(TableModel, table=True):
    """
    用户偏好设置模型
    
    用于存储用户个性化设置。
    """
    __table_args__ = (UniqueConstraint("user_id", "preference_key", name="uq_user_preference_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    preference_key: str = Field(index=True)
    preference_value: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "preference_key": "theme",
                "preference_value": "dark"
            }
        }


class UserAuth(TableModel, table=True):
    """
    用户认证信息模型
    
    用于存储 Supabase 用户认证信息和 session 数据。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    supabase_user_id: str = Field(index=True)  # Supabase 用户 ID
    access_token: str  # 访问令牌
    refresh_token: str  # 刷新令牌
    expires_at: datetime  # token 过期时间
    user_email: Optional[str] = None  # 用户邮箱
    user_metadata: Optional[str] = None  # 用户元数据（JSON 字符串）
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "supabase_user_id": "123e4567-e89b-12d3-a456-426614174000",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "def50200abcd...",
                "expires_at": "2024-01-01T12:00:00Z",
                "user_email": "user@example.com",
                "user_metadata": '{"name": "John Doe", "avatar_url": "https://..."}'
            }
        }
