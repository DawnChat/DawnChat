"""
AI 代码执行安全策略

提供代码安全检查功能，防止执行恶意代码。

检查内容:
1. 禁止危险的模块导入（os.system, subprocess 等）
2. 禁止危险的函数调用（exec, eval, compile 等）
3. 检测危险的字符串模式（rm -rf, sudo 等）
4. 限制文件访问路径

使用示例:
    from app.ai_sandbox.security import security_checker

    code = '''
    import subprocess
    subprocess.run(["rm", "-rf", "/"])
    '''

    result = security_checker.check(code)
    if not result.is_safe:
        print("代码不安全:", result.blocked_patterns)
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import List, Optional, Set

from app.config import Config


@dataclass
class SecurityCheckResult:
    """安全检查结果"""

    is_safe: bool
    warnings: List[str] = field(default_factory=list)
    blocked_patterns: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.is_safe:
            return "✅ 代码安全检查通过"
        else:
            return f"❌ 代码安全检查失败: {', '.join(self.blocked_patterns)}"


class CodeSecurityChecker:
    """
    代码安全检查器

    实现多层次的代码安全检查：
    1. AST 分析：检查导入和函数调用
    2. 正则匹配：检查危险模式
    3. 路径检查：限制文件访问范围
    """

    # 完全禁止的导入模块
    BLOCKED_IMPORTS: Set[str] = {
        # 系统命令执行
        "subprocess",
        "os.system",
        "os.popen",
        "commands",
        # 低级系统接口
        "ctypes",
        "ctypes.util",
        # 网络（根据需要可以放开）
        # "socket",
        # "urllib",
        # 文件操作（限制）
        "shutil.rmtree",
        "shutil.move",
        # 代码执行
        "__builtins__",
        "builtins",
        "importlib",
    }

    # 禁止的函数调用
    BLOCKED_FUNCTIONS: Set[str] = {
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
    }

    # 禁止的函数调用模式（正则）
    BLOCKED_PATTERNS: List[str] = [
        r"os\.system\s*\(",
        r"os\.popen\s*\(",
        r"subprocess\.\w+\s*\(",
        r"shutil\.rmtree\s*\(",
        r"shutil\.move\s*\(",
        r"__import__\s*\(",
        r"exec\s*\(",
        r"eval\s*\(",
        r"compile\s*\(",
        r"open\s*\([^)]*['\"][/~]",  # 禁止访问绝对路径
        r"Path\s*\([^)]*['\"][/~]",  # pathlib 绝对路径
    ]

    # 危险字符串
    DANGEROUS_STRINGS: List[str] = [
        "rm -rf",
        "rm -r",
        "sudo ",
        "; rm ",
        "| rm ",
        "&& rm ",
        "chmod 777",
        "chmod +x",
        "/etc/passwd",
        "/etc/shadow",
        "~/.ssh",
        "~/.gnupg",
    ]

    def __init__(
        self,
        allowed_paths: Optional[List[Path]] = None,
        extra_blocked_imports: Optional[Set[str]] = None,
        strict_mode: bool = False,
    ):
        """
        初始化安全检查器

        Args:
            allowed_paths: 允许访问的目录列表
            extra_blocked_imports: 额外禁止的导入
            strict_mode: 严格模式（禁止更多操作）
        """
        self.allowed_paths = allowed_paths or [
            Config.DATA_DIR,
            Path("/tmp") / "dawnchat",
        ]

        self.blocked_imports = self.BLOCKED_IMPORTS.copy()
        if extra_blocked_imports:
            self.blocked_imports.update(extra_blocked_imports)

        self.strict_mode = strict_mode

        if strict_mode:
            # 严格模式下禁止更多操作
            self.blocked_imports.update(
                {
                    "socket",
                    "urllib",
                    "http",
                    "ftplib",
                    "smtplib",
                }
            )

    def check(self, code: str) -> SecurityCheckResult:
        """
        检查代码安全性

        Args:
            code: Python 代码字符串

        Returns:
            SecurityCheckResult
        """
        warnings: List[str] = []
        blocked: List[str] = []

        # 1. AST 分析 - 检查导入和函数调用
        try:
            tree = ast.parse(code)
            ast_issues = self._check_ast(tree)
            blocked.extend(ast_issues)
        except SyntaxError as e:
            warnings.append(f"代码存在语法错误（行 {e.lineno}），无法进行完整安全检查")

        # 2. 正则模式匹配
        pattern_issues = self._check_patterns(code)
        blocked.extend(pattern_issues)

        # 3. 危险字符串检查
        string_issues = self._check_dangerous_strings(code)
        blocked.extend(string_issues)

        # 4. 路径检查（检查代码中的字符串路径）
        path_issues = self._check_paths(code)
        blocked.extend(path_issues)

        return SecurityCheckResult(is_safe=len(blocked) == 0, warnings=warnings, blocked_patterns=blocked)

    def _check_ast(self, tree: ast.AST) -> List[str]:
        """通过 AST 检查导入和函数调用"""
        issues = []

        for node in ast.walk(tree):
            # 检查 import 语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.blocked_imports:
                        issues.append(f"禁止导入: {alias.name}")

            # 检查 from ... import 语句
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # 检查模块本身
                    if node.module in self.blocked_imports:
                        issues.append(f"禁止导入: {node.module}")

                    # 检查 from module import name
                    for alias in node.names:
                        full_name = f"{node.module}.{alias.name}"
                        if full_name in self.blocked_imports:
                            issues.append(f"禁止导入: {full_name}")

            # 检查函数调用
            elif isinstance(node, ast.Call):
                func_name = self._get_func_name(node.func)
                if func_name in self.BLOCKED_FUNCTIONS:
                    issues.append(f"禁止调用: {func_name}")

        return issues

    def _get_func_name(self, node: ast.expr) -> str:
        """从 AST 节点获取函数名"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parent = self._get_func_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    def _check_patterns(self, code: str) -> List[str]:
        """正则模式匹配检查"""
        issues = []

        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, code):
                # 提取匹配的内容用于报告
                match = re.search(pattern, code)
                if match:
                    issues.append(f"检测到禁止的模式: {match.group()[:50]}...")

        return issues

    def _check_dangerous_strings(self, code: str) -> List[str]:
        """检查危险字符串"""
        issues = []

        code_lower = code.lower()
        for dangerous in self.DANGEROUS_STRINGS:
            if dangerous.lower() in code_lower:
                issues.append(f"检测到危险字符串: {dangerous}")

        return issues

    def _check_paths(self, code: str) -> List[str]:
        """检查路径访问"""
        issues = []

        # 提取代码中的字符串
        string_pattern = r'["\']([^"\']+)["\']'
        strings = re.findall(string_pattern, code)

        for s in strings:
            # 检查是否是路径
            if s.startswith("/") or s.startswith("~"):
                # 检查是否在允许的路径中
                path = Path(s).expanduser()
                is_allowed = any(self._is_path_under(path, allowed) for allowed in self.allowed_paths)
                if not is_allowed:
                    issues.append(f"禁止访问路径: {s}")

        return issues

    def _is_path_under(self, path: Path, parent: Path) -> bool:
        """检查路径是否在父目录下"""
        try:
            path = path.resolve()
            parent = parent.resolve()
            return str(path).startswith(str(parent))
        except Exception:
            return False

    def sanitize_code(self, code: str) -> str:
        """
        尝试清理代码中的危险内容

        注意：这只是一个辅助功能，不能替代安全检查

        Args:
            code: 原始代码

        Returns:
            清理后的代码
        """
        sanitized = code

        # 移除危险的导入
        for module in self.blocked_imports:
            # import module
            sanitized = re.sub(
                rf"^\s*import\s+{re.escape(module)}\s*$", f"# BLOCKED: import {module}", sanitized, flags=re.MULTILINE
            )
            # from module import ...
            sanitized = re.sub(
                rf"^\s*from\s+{re.escape(module)}\s+import\s+.*$",
                f"# BLOCKED: from {module} import ...",
                sanitized,
                flags=re.MULTILINE,
            )

        return sanitized


# 全局默认检查器
security_checker = CodeSecurityChecker()


def check_code_safety(code: str) -> SecurityCheckResult:
    """
    便捷函数：检查代码安全性

    Args:
        code: Python 代码

    Returns:
        SecurityCheckResult
    """
    return security_checker.check(code)
