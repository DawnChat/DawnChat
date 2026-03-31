"""
AI 代码执行沙箱模块

提供与 App 运行时隔离的 Python 执行环境，用于：
- 执行 AI 生成的代码
- 动态安装用户请求的依赖
- 安全地运行不受信任的脚本

主要组件:
- AIExecutionEnv: AI 执行环境管理器
- CodeSecurityChecker: 代码安全检查器
"""

from .env_manager import AIExecutionEnv, get_ai_env
from .security import CodeSecurityChecker, SecurityCheckResult, security_checker

__all__ = [
    "AIExecutionEnv",
    "get_ai_env",
    "CodeSecurityChecker",
    "SecurityCheckResult",
    "security_checker",
]
