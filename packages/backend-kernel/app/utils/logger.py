"""
DawnChat - 日志系统
提供分级日志、日志轮转、隐私过滤等功能
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys
from typing import Optional

from app.config import Config


class PrivacyFilter(logging.Filter):
    """过滤日志中的敏感信息"""
    
    PATTERNS = [
        (r'password["\s:=]+[\w\d]+', 'password=***'),
        (r'token["\s:=]+[\w\d\-_]+', 'token=***'),
        (r'api_key["\s:=]+[\w\d\-_]+', 'api_key=***'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***'),
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        # 过滤消息内容
        message = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
        
        # 更新记录
        record.msg = message
        record.args = ()
        
        return True


def setup_logger(
    name: str,
    log_file: Optional[Path] = None,
    level: int = Config.LOG_LEVEL,
    enable_privacy_filter: bool = True
) -> logging.Logger:
    """
    设置并返回一个配置好的 logger
    
    Args:
        name: Logger 名称
        log_file: 日志文件路径（可选）
        level: 日志级别
        enable_privacy_filter: 是否启用隐私过滤
        
    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 创建格式化器
    formatter = logging.Formatter(Config.LOG_FORMAT)
    
    # 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件 Handler（如果指定）
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 添加隐私过滤器
    if enable_privacy_filter:
        privacy_filter = PrivacyFilter()
        for handler in logger.handlers:
            handler.addFilter(privacy_filter)
    
    # 防止日志传播到根 logger
    logger.propagate = False
    
    return logger


# 创建全局 logger 实例
app_logger = setup_logger(
    "dawnchat",
    log_file=Config.LOGS_DIR / "app.log"
)

api_logger = setup_logger(
    "dawnchat.api",
    log_file=Config.LOGS_DIR / "api.log"
)


def get_logger(name: str) -> logging.Logger:
    """
    获取或创建一个 logger
    
    Args:
        name: Logger 名称
        
    Returns:
        Logger 实例
    """
    return setup_logger(f"dawnchat.{name}")

