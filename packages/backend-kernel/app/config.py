"""
DawnChat - 配置管理模块
统一管理应用配置、路径、日志级别等
"""

import json
import logging
import os
from pathlib import Path
import platform
import sys
from typing import Optional

from app.config_domains import AgentSettings, PluginSettings, RuntimeSettings

# ============ 环境变量配置 ============
# (已移除) 代理配置现在由 NetworkService 统一管理



# ============ 路径工具函数（模块级，避免 PyInstaller 问题）============

def _get_user_data_dir() -> Path:
    r"""
    获取用户数据目录（跨平台）
    遵循各平台的最佳实践：
    - macOS: ~/Library/Application Support/DawnChat/
    - Windows: %APPDATA%\DawnChat\ (C:\Users\Username\AppData\Roaming\DawnChat)
    - Linux: ~/.local/share/DawnChat/
    """
    system = platform.system()
    
    if system == "Darwin":  # macOS
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        # 优先使用 APPDATA，如果不存在则使用 LOCALAPPDATA
        appdata = os.getenv("APPDATA")
        if appdata:
            base = Path(appdata)
        else:
            localappdata = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            base = Path(localappdata)
    else:  # Linux and others
        # 遵循 XDG Base Directory 规范
        xdg_data_home = os.getenv("XDG_DATA_HOME")
        if xdg_data_home:
            base = Path(xdg_data_home)
        else:
            base = Path.home() / ".local" / "share"
    
    return base / "DawnChat"


def _get_user_logs_dir() -> Path:
    r"""
    获取用户日志目录（跨平台）
    - macOS: ~/Library/Logs/DawnChat/
    - Windows: %LOCALAPPDATA%\DawnChat\Logs\
    - Linux: ~/.local/share/DawnChat/logs/
    """
    system = platform.system()
    
    if system == "Darwin":  # macOS
        return Path.home() / "Library" / "Logs" / "DawnChat"
    elif system == "Windows":
        localappdata = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(localappdata) / "DawnChat" / "Logs"
    else:  # Linux
        # Linux 通常将日志放在数据目录下
        return _get_user_data_dir() / "logs"

def _is_running_tests() -> bool:
    if os.getenv("DAWNCHAT_TESTING") == "1":
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    if "pytest" in sys.modules:
        return True
    argv0 = sys.argv[0] if sys.argv else ""
    return "pytest" in argv0


# ============ 配置类 ============

class Config:
    """应用全局配置"""
    
    # ============ 应用基础配置 ============
    APP_NAME = "DawnChat"
    VERSION = "1.0.0"
    
    # ============ 功能开关 ============
    # 是否启用 Agent v2 (新架构)
    ENABLE_AGENT_V2 = os.getenv("ENABLE_AGENT_V2", "true").lower() == "true"
    AGENT_RUNTIME = os.getenv("AGENT_RUNTIME", "v3").lower()
    
    # ============ E2E 测试模式 ============
    # 启用测试模式时，后端自动注入 ScenarioExecutor 替代真实 CAO 执行器
    # 用法: DAWNCHAT_TEST_MODE=true ./dev.sh
    TEST_MODE = os.getenv("DAWNCHAT_TEST_MODE", "false").lower() == "true"
    
    # ============ 服务器配置 ============
    API_HOST = os.getenv("DAWNCHAT_API_HOST", "127.0.0.1")
    API_PORT = int(os.getenv("DAWNCHAT_API_PORT", "8000"))
    
    # ============ 路径配置 ============
    # PBS 打包标记（由 build.sh 在打包前后切换）
    IS_PBS_APP = False  # BUILD_SCRIPT_TOGGLE_PBS_FLAG
    
    # 获取项目根目录（应用可执行文件所在目录）
    if IS_PBS_APP:
        # 打包后：sidecar 的根目录（可执行位于 sidecar/python/bin/python3.11）
        # 例: /Applications/DawnChat.app/Contents/Resources/sidecars/dawnchat-backend/python/bin/python3.11
        # 需要回退到 .../sidecars/dawnchat-backend 作为 BACKEND_ROOT
        BACKEND_ROOT = Path(sys.executable).parent.parent.parent
        PROJECT_ROOT = BACKEND_ROOT
        ASSETS_DIR = BACKEND_ROOT / "app" / "assets"
        SIDECAR_DIR = BACKEND_ROOT  # 打包后 sidecar = backend_root
    else:
        # 开发环境：src-backend 的父目录
        BACKEND_ROOT = Path(__file__).parent.parent
        PROJECT_ROOT = BACKEND_ROOT.parent
        ASSETS_DIR = BACKEND_ROOT / "app" / "assets"
        dev_runtime_root = str(os.getenv("DAWNCHAT_DEV_RUNTIME_ROOT", "")).strip()
        if dev_runtime_root:
            SIDECAR_DIR = Path(dev_runtime_root).expanduser()
        else:
            SIDECAR_DIR = BACKEND_ROOT.parent.parent / "apps" / "desktop" / "src-tauri" / "sidecars" / "dawnchat-backend"
    
    # ============ 第三方工具路径 ============
    # 预置二进制资源路径（在 sidecar 目录中）
    LLAMACPP_RESOURCES_DIR = SIDECAR_DIR / "llamacpp"
    
    # Python 解释器路径 (PBS 环境下会自动调整)
    PYTHON_EXECUTABLE = sys.executable
    
    _default_data_dir = _get_user_data_dir()
    if _is_running_tests():
        _default_data_dir = Path(os.getenv("DAWNCHAT_TEST_DATA_DIR", str(PROJECT_ROOT / ".dawnchat-test-data")))

    # ⭐ 用户数据存储路径（在用户目录，不会因应用更新而丢失）
    DATA_DIR = Path(os.getenv("DAWNCHAT_DATA_DIR", str(_default_data_dir))).expanduser()

    _default_logs_dir = _get_user_logs_dir()
    if _is_running_tests():
        _default_logs_dir = DATA_DIR / "logs"

    LOGS_DIR = Path(os.getenv("DAWNCHAT_LOGS_DIR", str(_default_logs_dir))).expanduser()
    MODELS_DIR = DATA_DIR / "models"
    PLUGIN_DIR = DATA_DIR / "plugins"
    WORKBENCH_PROJECTS_DIR = DATA_DIR / "Project"
    CRAWL_DIR = DATA_DIR / "crawl"
    FFMPEG_DIR = DATA_DIR / "ffmpeg"
    
    # TTS 声音文件目录（统一存放所有 TTS 声音文件）
    VOICES_DIR = DATA_DIR / "assets" / "voices"
    TTS_MODEL_DIR = Path(
        os.getenv(
            "DAWNCHAT_TTS_MODEL_DIR",
            str(SIDECAR_DIR / "tts-models" / "kokoro-multi-lang-v1_1"),
        )
    ).expanduser()
    TTS_DEFAULT_EN_SID = int(os.getenv("DAWNCHAT_TTS_DEFAULT_EN_SID", "1"))
    TTS_DEFAULT_ZH_SID = int(os.getenv("DAWNCHAT_TTS_DEFAULT_ZH_SID", "6"))
    TTS_SAMPLE_RATE = int(os.getenv("DAWNCHAT_TTS_SAMPLE_RATE", "24000"))
    TTS_PRIMARY_LANG = os.getenv("DAWNCHAT_TTS_PRIMARY_LANG", "zh").strip().lower()
    if TTS_PRIMARY_LANG not in {"zh", "en"}:
        TTS_PRIMARY_LANG = "zh"
    TTS_ENGINE_IDLE_TTL_SECONDS = int(os.getenv("DAWNCHAT_TTS_ENGINE_IDLE_TTL_SECONDS", "300"))
    TTS_ENGINE_MAX_CACHED = max(1, int(os.getenv("DAWNCHAT_TTS_ENGINE_MAX_CACHED", "2")))
    
    # ============ Pipeline 系统配置 ============
    # Pipeline 数据库路径
    PIPELINE_DB_PATH = DATA_DIR / "pipeline.db"
    
    # Pipeline 产物存储路径
    PIPELINE_ARTIFACTS_DIR = DATA_DIR / "pipeline" / "artifacts"
    
    # Workspace 基础路径
    PIPELINE_WORKSPACES_DIR = DATA_DIR / "pipeline" / "workspaces"
    
    # Pipeline 引擎选择: "legacy" 使用自研状态机, "restate" 使用 Restate 编排引擎
    PIPELINE_ENGINE = os.getenv("DAWNCHAT_PIPELINE_ENGINE", "legacy")  # "legacy" | "restate"
    
    # Restate Server 配置
    RESTATE_INGRESS_PORT = int(os.getenv("RESTATE_INGRESS_PORT", "8080"))
    RESTATE_ADMIN_PORT = int(os.getenv("RESTATE_ADMIN_PORT", "9070"))
    RESTATE_DATA_DIR = DATA_DIR / "restate"
    RESTATE_AUTO_START = os.getenv("RESTATE_AUTO_START", "true").lower() == "true"
    
    # ============ Worker Pool 配置 ============
    # 角色配置: "manager" | "worker" | "both"
    # - manager: 仅作为 Manager，广播服务并调度任务
    # - worker: 仅作为 Worker，发现 Manager 并接收任务
    # - both: 同时作为 Manager 和 Worker（单机默认模式）
    WORKER_ROLE = os.getenv("DAWNCHAT_ROLE", "both")
    
    # Worker ID（默认使用主机名 + 随机后缀）
    WORKER_ID = os.getenv("DAWNCHAT_WORKER_ID", "")
    
    # 心跳配置
    WORKER_HEARTBEAT_INTERVAL = int(os.getenv("DAWNCHAT_HEARTBEAT_INTERVAL", "10"))  # 秒
    WORKER_HEARTBEAT_TIMEOUT = int(os.getenv("DAWNCHAT_HEARTBEAT_TIMEOUT", "30"))  # 连续丢失视为离线
    WORKER_HEARTBEAT_MAX_MISSED = 3  # 最大允许丢失的心跳次数
    
    # mDNS 服务发现配置
    MDNS_SERVICE_TYPE = "_dawnchat-manager._tcp.local."
    MDNS_BROADCAST_ENABLED = os.getenv("DAWNCHAT_MDNS_ENABLED", "true").lower() == "true"
    MDNS_DISCOVERY_TIMEOUT = float(os.getenv("DAWNCHAT_MDNS_TIMEOUT", "5.0"))  # 秒
    
    # Manager URL（手动指定时使用，优先于 mDNS）
    MANAGER_URL = os.getenv("DAWNCHAT_MANAGER_URL", "")
    
    # Worker 数据目录
    WORKER_DATA_DIR = DATA_DIR / "worker"
    WORKER_CONFIG_FILE = DATA_DIR / "worker.yaml"
    
    # Worker API 配置（接收远程任务时使用的端口）
    WORKER_API_PORT = int(os.getenv("DAWNCHAT_WORKER_PORT", "8001"))
    
    # ============ ASR 相关路径配置 ============
    # Whisper 模型目录（用户数据目录）
    WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
    
    # ============ Plugin 系统配置 ============
    # 插件市场索引（plugins.json）
    PLUGIN_MARKET_INDEX_URL = os.getenv(
        "DAWNCHAT_PLUGIN_MARKET_INDEX_URL",
        "https://plugins.dawnchat.com/plugins.json",
    )
    _plugin_market_fallback_raw = os.getenv(
        "DAWNCHAT_PLUGIN_MARKET_INDEX_FALLBACK_URLS",
        "https://github.com/chaxiu/dawnchat-plugins/releases/latest/download/plugins.json",
    )
    PLUGIN_MARKET_INDEX_FALLBACK_URLS = [
        item.strip() for item in _plugin_market_fallback_raw.split(",") if item.strip()
    ]

    # 官方插件源码目录（仅开发模式调试使用，生产不依赖该目录）
    OFFICIAL_PLUGINS_DIR = Path(
        os.getenv(
            "DAWNCHAT_OFFICIAL_PLUGINS_DIR",
            str(PROJECT_ROOT / "dawnchat-plugins" / "official-plugins"),
        )
    )

    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kgijmcqlakksjhxssxbb.supabase.co")
    
    # uv 二进制目录（在 sidecar 目录中）
    UV_BINARY_DIR = SIDECAR_DIR / "uv-binary"
    BUN_BINARY_DIR = SIDECAR_DIR / "bun-bin"
    OPENCODE_BINARY_DIR = SIDECAR_DIR / "opencode-bin"
    OPENCODE_RULES_BUNDLE_DIR = SIDECAR_DIR / "opencode-rules-default"
    OPENCODE_DATA_DIR = DATA_DIR / "opencode"
    OPENCODE_LOGS_DIR = LOGS_DIR / "opencode"
    CLAUDE_DATA_DIR = DATA_DIR / "claude"
    CLAUDE_LOGS_DIR = LOGS_DIR / "claude"
    OPENCODE_HOST = os.getenv("DAWNCHAT_OPENCODE_HOST", "127.0.0.1")
    OPENCODE_PORT = int(os.getenv("DAWNCHAT_OPENCODE_PORT", "4096"))
    OPENCODE_START_TIMEOUT = float(os.getenv("DAWNCHAT_OPENCODE_START_TIMEOUT", "20"))
    OPENCODE_HEALTH_CHECK_INTERVAL = float(os.getenv("DAWNCHAT_OPENCODE_HEALTH_CHECK_INTERVAL", "5"))
    OPENCODE_MAX_RESTARTS = int(os.getenv("DAWNCHAT_OPENCODE_MAX_RESTARTS", "5"))
    MCP_PROXY_TIMEOUT_CONNECT_SECONDS = float(os.getenv("DAWNCHAT_MCP_PROXY_TIMEOUT_CONNECT_SECONDS", "3"))
    MCP_PROXY_TIMEOUT_READ_SECONDS = float(os.getenv("DAWNCHAT_MCP_PROXY_TIMEOUT_READ_SECONDS", "12"))
    OPENCODE_SEARCH_TIMEOUT_READ_SECONDS = float(os.getenv("OPENCODE_SEARCH_TIMEOUT_READ_SECONDS", "60"))
    OPENCODE_UI_BRIDGE_MCP_TIMEOUT_READ_SECONDS = float(
        os.getenv("DAWNCHAT_OPENCODE_UI_BRIDGE_MCP_TIMEOUT_READ_SECONDS", "310")
    )
    MCP_PROXY_TIMEOUT_WRITE_SECONDS = float(os.getenv("DAWNCHAT_MCP_PROXY_TIMEOUT_WRITE_SECONDS", "8"))
    MCP_PROXY_TIMEOUT_POOL_SECONDS = float(os.getenv("DAWNCHAT_MCP_PROXY_TIMEOUT_POOL_SECONDS", "3"))
    DDGS_TIMEOUT_SECONDS = int(os.getenv("DAWNCHAT_DDGS_TIMEOUT_SECONDS", "8"))
    DDGS_CACHE_ENABLED = os.getenv("DAWNCHAT_DDGS_CACHE_ENABLED", "true").lower() == "true"
    DDGS_CACHE_MAX_ENTRIES = int(os.getenv("DAWNCHAT_DDGS_CACHE_MAX_ENTRIES", "200"))
    DDGS_SEARCH_CACHE_TTL_SECONDS = int(os.getenv("DAWNCHAT_DDGS_SEARCH_CACHE_TTL_SECONDS", "300"))
    DDGS_EXTRACT_CACHE_TTL_SECONDS = int(os.getenv("DAWNCHAT_DDGS_EXTRACT_CACHE_TTL_SECONDS", "600"))
    DDGS_SEARCH_DEFAULT_MAX_RESULTS = int(os.getenv("DAWNCHAT_DDGS_SEARCH_DEFAULT_MAX_RESULTS", "5"))
    DDGS_SEARCH_MAX_RESULTS_LIMIT = int(os.getenv("DAWNCHAT_DDGS_SEARCH_MAX_RESULTS_LIMIT", "10"))
    DDGS_IMAGE_FALLBACK_REGION = os.getenv("DAWNCHAT_DDGS_IMAGE_FALLBACK_REGION", "wt-wt")
    DDGS_IMAGE_FALLBACK_SAFESEARCH = os.getenv("DAWNCHAT_DDGS_IMAGE_FALLBACK_SAFESEARCH", "moderate")
    # Unsplash image search (Edge Function); kernel does not refresh Supabase tokens (frontend-only refresh).
    IMAGE_SEARCH_FUNCTION_NAME = os.getenv("DAWNCHAT_IMAGE_SEARCH_FUNCTION_NAME", "image-search").strip() or "image-search"
    IMAGE_SEARCH_EDGE_TIMEOUT_SECONDS = float(os.getenv("DAWNCHAT_IMAGE_SEARCH_EDGE_TIMEOUT_SECONDS", "25"))
    SUPABASE_ACCESS_SKEW_SECONDS = float(os.getenv("DAWNCHAT_SUPABASE_ACCESS_SKEW_SECONDS", "90"))
    PLUGIN_UI_BRIDGE_TIMEOUT_SECONDS = float(os.getenv("DAWNCHAT_PLUGIN_UI_BRIDGE_TIMEOUT_SECONDS", "15"))
    PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_SECONDS = float(
        os.getenv("DAWNCHAT_PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_SECONDS", "130")
    )
    PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_BUFFER_SECONDS = float(
        os.getenv("DAWNCHAT_PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_BUFFER_SECONDS", "5")
    )
    OPENCODE_INCLUDE_WORKSPACE_RULES = (
        os.getenv("DAWNCHAT_OPENCODE_INCLUDE_WORKSPACE_RULES", "false").lower() == "true"
    )
    CLAUDE_ENABLED = os.getenv("DAWNCHAT_CLAUDE_ENABLED", "false").lower() == "true"
    CLAUDE_HOST = os.getenv("DAWNCHAT_CLAUDE_HOST", "127.0.0.1")
    CLAUDE_PORT = int(os.getenv("DAWNCHAT_CLAUDE_PORT", "4097"))
    CLAUDE_START_TIMEOUT = float(os.getenv("DAWNCHAT_CLAUDE_START_TIMEOUT", "20"))
    CLAUDE_HEALTH_CHECK_INTERVAL = float(os.getenv("DAWNCHAT_CLAUDE_HEALTH_CHECK_INTERVAL", "5"))
    CLAUDE_MAX_RESTARTS = int(os.getenv("DAWNCHAT_CLAUDE_MAX_RESTARTS", "5"))
    CLAUDE_HEALTH_ENDPOINT = os.getenv("DAWNCHAT_CLAUDE_HEALTH_ENDPOINT", "")
    CLAUDE_HEALTH_STRICT = os.getenv("DAWNCHAT_CLAUDE_HEALTH_STRICT", "false").lower() == "true"
    CLAUDE_START_ARGS = os.getenv("DAWNCHAT_CLAUDE_START_ARGS", "").strip()
    
    # 插件目录分层
    PLUGIN_ROOT_DIR = DATA_DIR / "plugins"
    PLUGIN_SOURCES_DIR = PLUGIN_ROOT_DIR / "sources"
    PLUGIN_DATA_DIR = PLUGIN_ROOT_DIR / "data"
    PLUGIN_MODELS_DIR = PLUGIN_ROOT_DIR / "models"
    PLUGIN_DOWNLOAD_DIR = PLUGIN_ROOT_DIR / "downloads"
    PLUGIN_TEMPLATE_CACHE_DIR = PLUGIN_DOWNLOAD_DIR / "templates"
    PLUGIN_USER_UPLOADS_DIR_NAME = str(
        os.getenv("DAWNCHAT_PLUGIN_USER_UPLOADS_DIR_NAME", "user-uploads")
    ).strip() or "user-uploads"
    PLUGIN_USER_UPLOAD_MAX_BYTES = int(
        os.getenv("DAWNCHAT_PLUGIN_USER_UPLOAD_MAX_BYTES", str(500 * 1024 * 1024))
    )
    PLUGIN_METADATA_FILE = PLUGIN_ROOT_DIR / "plugin_metadata.json"
    PLUGIN_OPENCODE_RULES_DIR = PLUGIN_ROOT_DIR / "opencode-shared"
    PLUGIN_OPENCODE_RULES_VERSIONS_DIR = PLUGIN_OPENCODE_RULES_DIR / "versions"
    PLUGIN_OPENCODE_RULES_CURRENT_LINK = PLUGIN_OPENCODE_RULES_DIR / "current"
    PLUGIN_OPENCODE_RULES_STATE = PLUGIN_OPENCODE_RULES_DIR / "state.json"
    PLUGIN_OPENCODE_RULES_CACHE_DIR = PLUGIN_DOWNLOAD_DIR / "opencode-rules"
    ASSISTANT_SDK_DIRNAME = "assistant-sdk"
    ASSISTANT_SDK_PACKAGE_DIRS = {
        "@dawnchat/assistant-app-sdk": "assistant-app-sdk",
        "@dawnchat/assistant-chat-ui": "assistant-chat-ui",
        "@dawnchat/assistant-core": "assistant-core",
        "@dawnchat/host-orchestration-sdk": "host-orchestration-sdk",
    }
    ASSISTANT_SDK_BUNDLE_DIR = SIDECAR_DIR / "dawnchat-plugins" / ASSISTANT_SDK_DIRNAME

    # 向后兼容：历史代码把插件源码目录命名为 PLUGIN_DIR
    PLUGIN_DIR = PLUGIN_SOURCES_DIR

    # Plugin venv 目录（用户数据目录）
    PLUGINS_VENV_DIR = PLUGIN_ROOT_DIR / "venvs"
    
    # uv 全局缓存目录
    UV_CACHE_DIR = DATA_DIR / "cache" / "uv"
    
    # Plugin 端口范围（用于 Gradio 服务）
    PLUGIN_PORT_RANGE = (7861, 7899)
    PLUGIN_PREVIEW_ENABLED = os.getenv("DAWNCHAT_PLUGIN_PREVIEW_ENABLED", "true").lower() == "true"
    PLUGIN_PREVIEW_BIND_HOST = os.getenv("DAWNCHAT_PLUGIN_PREVIEW_BIND_HOST", "127.0.0.1")
    _preview_range_raw = os.getenv("DAWNCHAT_PLUGIN_PREVIEW_PORT_RANGE", "17961-18060")
    try:
        _preview_min, _preview_max = [int(part.strip()) for part in _preview_range_raw.split("-", 1)]
        PLUGIN_PREVIEW_PORT_RANGE = (
            min(_preview_min, _preview_max),
            max(_preview_min, _preview_max),
        )
    except Exception:
        PLUGIN_PREVIEW_PORT_RANGE = (17961, 18060)
    PLUGIN_PREVIEW_WATCH_DEBOUNCE_MS = int(os.getenv("DAWNCHAT_PLUGIN_PREVIEW_WATCH_DEBOUNCE_MS", "600"))

    # AI Base venv（用于重型插件共享依赖，避免重复下载）
    PLUGIN_AI_BASE_ENABLED = os.getenv("DAWNCHAT_PLUGIN_AI_BASE_ENABLED", "true").lower() == "true"
    PLUGIN_AI_BASE_VENV_ID = os.getenv("DAWNCHAT_PLUGIN_AI_BASE_VENV_ID", "_ai_base")
    _plugin_ai_base_reqs_raw = os.getenv(
        "DAWNCHAT_PLUGIN_AI_BASE_REQUIREMENTS",
        ",".join(
            [
                "torch>=2.0.0,<3.0.0",
                "torchaudio>=2.0.0,<3.0.0",
                "torchvision>=0.15.0,<1.0.0",
                "transformers>=4.45.0,<6.0.0",
                "tokenizers>=0.13.3,<1.0.0",
                "datasets>=3.5.0,<4.0.0",
                "accelerate>=1.6.0,<2.0.0",
                "safetensors>=0.4.2,<1.0.0",
                "sentencepiece>=0.2.0,<1.0.0",
            ]
        ),
    )
    PLUGIN_AI_BASE_REQUIREMENTS = [
        item.strip() for item in _plugin_ai_base_reqs_raw.split(",") if item.strip()
    ]
    
    @staticmethod
    def get_uv_binary() -> Optional[Path]:
        """
        获取当前平台的 uv 可执行文件路径
        
        Returns:
            uv 二进制路径，如果不存在则返回 None
        """
        system = platform.system()
        arch = platform.machine()
        
        # 映射平台到目录名
        if system == "Darwin":
            if arch == "arm64":
                uv_name = "uv"
            else:
                uv_name = "uv"
        elif system == "Windows":
            uv_name = "uv.exe"
        else:  # Linux
            uv_name = "uv"
        
        # 打包后的路径（在 sidecar/uv-binary/ 下）
        uv_path = Config.UV_BINARY_DIR / uv_name
        
        if uv_path.exists():
            return uv_path
        
        # 开发环境：在 uv-binary/<platform>/ 下
        if system == "Darwin":
            if arch == "arm64":
                platform_dir = "uv-aarch64-apple-darwin"
            else:
                platform_dir = "uv-x86_64-apple-darwin"
        elif system == "Windows":
            if arch == "ARM64":
                platform_dir = "uv-aarch64-pc-windows-msvc"
            else:
                platform_dir = "uv-x86_64-pc-windows-msvc"
        else:  # Linux
            if arch == "aarch64":
                platform_dir = "uv-aarch64-unknown-linux-gnu"
            else:
                platform_dir = "uv-x86_64-unknown-linux-gnu"
        
        dev_path = Config.UV_BINARY_DIR / platform_dir / uv_name
        if dev_path.exists():
            return dev_path
        
        return None
    
    @staticmethod
    def get_pbs_python() -> Optional[Path]:
        """
        获取 Host PBS Python 可执行文件路径
        
        PBS (Python Build Standalone) Python 用于创建 Plugin venv，
        使 Plugin 可以继承 Host 的 site-packages。
        
        Returns:
            PBS Python 路径，如果不存在则返回 None
        """
        system = platform.system()
        
        if Config.IS_PBS_APP:
            # 打包后：PBS Python 在 sidecar/python/bin/python3.11
            if system == "Windows":
                python_path = Config.BACKEND_ROOT / "python" / "python.exe"
            else:
                python_path = Config.BACKEND_ROOT / "python" / "bin" / "python3.11"
            
            if python_path.exists():
                return python_path
        
        # 开发环境：返回当前 Python
        return Path(sys.executable)

    @staticmethod
    def get_bun_binary() -> Optional[Path]:
        raw = str(os.getenv("DAWNCHAT_BUN_BIN", "")).strip()
        if raw:
            custom = Path(raw).expanduser()
            if custom.exists():
                return custom

        system = platform.system()
        arch = platform.machine().lower()
        bun_name = "bun.exe" if system == "Windows" else "bun"

        packed = Config.BUN_BINARY_DIR / bun_name
        if packed.exists():
            return packed

        dev_root = Config.PROJECT_ROOT / "binary" / "bun-bin"
        if system == "Darwin":
            folder = "bun-darwin-aarch64" if arch == "arm64" else "bun-darwin-x64"
        elif system == "Windows":
            folder = "bun-windows-x64"
        else:
            folder = "bun-linux-aarch64" if arch in {"aarch64", "arm64"} else "bun-linux-x64"
        candidate = dev_root / folder / bun_name
        if candidate.exists():
            return candidate
        return None

    @staticmethod
    def get_runtime_distribution_mode() -> str:
        raw = str(os.getenv("DAWNCHAT_RUNTIME_DISTRIBUTION", "")).strip().lower()
        if raw in {"dev", "debug", "release"}:
            return raw
        return "release" if Config.IS_PBS_APP else "dev"

    @classmethod
    def get_assistant_sdk_bundle_dir(cls) -> Path:
        raw = str(os.getenv("DAWNCHAT_ASSISTANT_SDK_BUNDLE_DIR", "")).strip()
        if raw:
            return Path(raw).expanduser()
        return cls.ASSISTANT_SDK_BUNDLE_DIR

    @classmethod
    def get_assistant_sdk_package_dirs(
        cls,
        *,
        allow_dev_fallback: bool = False,
    ) -> dict[str, Path]:
        bundle_root = cls.get_assistant_sdk_bundle_dir()
        resolved = {
            package_name: bundle_root / package_dir
            for package_name, package_dir in cls.ASSISTANT_SDK_PACKAGE_DIRS.items()
        }
        if all(path.exists() for path in resolved.values()):
            return resolved
        if allow_dev_fallback:
            dev_root = cls.PROJECT_ROOT / "dawnchat-plugins" / cls.ASSISTANT_SDK_DIRNAME
            fallback = {
                package_name: dev_root / package_dir
                for package_name, package_dir in cls.ASSISTANT_SDK_PACKAGE_DIRS.items()
            }
            if all(path.exists() for path in fallback.values()):
                return fallback
        return resolved

    @staticmethod
    def _collect_package_export_targets(value: object) -> list[str]:
        targets: list[str] = []
        if isinstance(value, str):
            targets.append(value)
        elif isinstance(value, dict):
            for nested in value.values():
                targets.extend(Config._collect_package_export_targets(nested))
        elif isinstance(value, list):
            for nested in value:
                targets.extend(Config._collect_package_export_targets(nested))
        return targets

    @classmethod
    def get_assistant_sdk_required_files(cls, package_dir: Path) -> list[Path]:
        package_json_path = package_dir / "package.json"
        if not package_json_path.exists():
            return [package_json_path]
        try:
            payload = json.loads(package_json_path.read_text(encoding="utf-8"))
        except Exception:
            return [package_json_path]

        relative_targets: set[str] = set()
        for key in ("main", "types"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("./"):
                relative_targets.add(value)

        exports_value = payload.get("exports")
        for target in cls._collect_package_export_targets(exports_value):
            if isinstance(target, str) and target.startswith("./"):
                relative_targets.add(target)

        required = [package_json_path]
        required.extend(package_dir / target[2:] for target in sorted(relative_targets))
        return required

    @classmethod
    def get_assistant_sdk_missing_files(cls, package_dir: Path) -> list[Path]:
        return [path for path in cls.get_assistant_sdk_required_files(package_dir) if not path.exists()]

    @classmethod
    def is_assistant_sdk_package_ready(cls, package_dir: Path) -> bool:
        return not cls.get_assistant_sdk_missing_files(package_dir)

    @staticmethod
    def get_opencode_binary() -> Optional[Path]:
        raw = str(os.getenv("DAWNCHAT_OPENCODE_BIN", "")).strip()
        if raw:
            custom = Path(raw).expanduser()
            if custom.exists():
                return custom

        system = platform.system()
        arch = platform.machine().lower()
        binary_name = "opencode.exe" if system == "Windows" else "opencode"

        packed = Config.OPENCODE_BINARY_DIR / binary_name
        if packed.exists():
            return packed

        dev_root = Config.PROJECT_ROOT / "binary" / "opencode-bin"
        if system == "Darwin":
            folder = "opencode-darwin-arm64" if arch == "arm64" else "opencode-darwin-x64"
        elif system == "Windows":
            folder = "opencode-windows-x64"
        else:
            folder = "opencode-linux-arm64" if arch in {"aarch64", "arm64"} else "opencode-linux-x64"

        candidate = dev_root / folder / binary_name
        if candidate.exists():
            return candidate
        return None

    @staticmethod
    def get_bundled_opencode_rules_dir() -> Optional[Path]:
        raw = str(os.getenv("DAWNCHAT_OPENCODE_RULES_DIR", "")).strip()
        if raw:
            custom = Path(raw).expanduser()
            if custom.exists() and custom.is_dir():
                return custom

        packed = Config.OPENCODE_RULES_BUNDLE_DIR
        if packed.exists() and packed.is_dir():
            return packed

        dev_candidate = Config.PROJECT_ROOT / "dawnchat-plugins" / ".opencode"
        if dev_candidate.exists() and dev_candidate.is_dir():
            return dev_candidate
        return None
    
    # ============ ADB 配置 ============
    # ADB 资源目录（内置 ADB 二进制文件，在 sidecar 目录中）
    ADB_RESOURCES_DIR = SIDECAR_DIR / "android-adb"
    
    # ADB 可执行文件路径（可由用户指定，None 则自动检测）
    ADB_EXECUTABLE: Optional[Path] = None
    
    # ADB 命令超时配置
    ADB_COMMAND_TIMEOUT = 30.0  # 秒
    ADB_RETRY_COUNT = 3
    ADB_RETRY_DELAY = 1.0  # 秒
    
    # ADB 截图配置
    ADB_SCREENSHOT_DIR = DATA_DIR / "adb" / "screenshots"
    ADB_SCREENSHOT_QUALITY = 80  # JPEG 质量 (1-100)
    ADB_SCREENSHOT_MAX_AGE_DAYS = 7  # 截图保留天数
    
    # ADB 日志配置
    ADB_LOG_DIR = DATA_DIR / "adb" / "logs"
    ADB_LOG_MAX_AGE_DAYS = 30  # 日志保留天数
    
    # ============ Llama-Server 配置 ============
    # 二进制部署路径（用户数据目录）
    BIN_DIR = DATA_DIR / "bin"
    
    @staticmethod
    def get_llama_server_executable() -> Path:
        """获取 llama-server 可执行文件路径"""
        system = platform.system()
        if system == "Windows":
            return Config.BIN_DIR / "llama-server.exe"
        else:
            return Config.BIN_DIR / "llama-server"
    
    # llama-server 服务配置
    LLAMA_SERVER_HOST = "127.0.0.1"
    LLAMA_SERVER_PORT = 8080  # 默认端口
    
    @classmethod
    def get_llama_server_api_base(cls) -> str:
        """获取 llama-server API 基础 URL"""
        return f"http://{cls.LLAMA_SERVER_HOST}:{cls.LLAMA_SERVER_PORT}/v1"
    
    # HuggingFace 缓存目录
    HF_CACHE_DIR = DATA_DIR / "cache" / "huggingface"
    
    # NLTK 数据目录
    NLTK_DATA_DIR = DATA_DIR / "nltk_data"
    
    # ============ 进程管理配置 ============
    # 健康检查配置
    HEALTH_CHECK_TIMEOUT = 5  # 秒
    HEALTH_CHECK_INTERVAL = 10  # 秒
    HEALTH_CHECK_MAX_RETRIES = 5  # 模型初始化需要时间
    
    # 启动重试配置
    STARTUP_RETRY_DELAY = 5  # 秒
    STARTUP_MAX_RETRIES = 3
    
    # 崩溃检测配置
    CRASH_DETECTION_WINDOW = 300  # 5分钟内
    CRASH_MAX_COUNT = 3  # 最多重启3次
    
    # 优雅关闭配置
    SHUTDOWN_TIMEOUT = 5  # SIGTERM 后等待时间
    
    # ============ LLM 日志截断配置 ============
    # 通过环境变量 LLM_LOG_TRUNCATE_LIMIT 控制截断长度，<=0 表示不截断
    LLM_LOG_TRUNCATE_LIMIT = int(os.getenv("LLM_LOG_TRUNCATE_LIMIT", "0") or "800")
    
    # ============ Llama-Server 进程配置 ============
    LLAMA_SERVER_HEALTH_CHECK_RETRIES = 10  # 模型加载需要时间
    LLAMA_SERVER_LOADING_TIMEOUT = 120  # 模型加载超时（秒）
    LLAMA_SERVER_IDLE_TIMEOUT = 600  # 空闲自动卸载时间（秒，10分钟）
    
    # llama-server 启动参数默认值
    LLAMA_SERVER_DEFAULT_CONTEXT = 262144  # 默认上下文窗口
    LLAMA_SERVER_DEFAULT_GPU_LAYERS = -1  # -1 表示全部使用 GPU

    # ============ MLX Server 配置 ============
    MLX_PROVIDER_MODE = os.getenv("MLX_PROVIDER_MODE", "http").lower()
    MLX_LM_SERVER_HOST = "127.0.0.1"
    MLX_LM_SERVER_PORT = int(os.getenv("MLX_LM_SERVER_PORT", "8081"))
    MLX_VLM_SERVER_HOST = "127.0.0.1"
    MLX_VLM_SERVER_PORT = int(os.getenv("MLX_VLM_SERVER_PORT", "8082"))
    
    # ============ AI 模型配置 ============
    DEFAULT_MODEL = "default"  # 默认使用的小模型
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 65535
    AGENTV3_DEFAULT_AGENT = os.getenv("DAWNCHAT_AGENTV3_DEFAULT_AGENT", "build")
    AGENTV3_PERMISSION_DEFAULT_ACTION = os.getenv("DAWNCHAT_AGENTV3_PERMISSION_DEFAULT_ACTION", "allow").lower()
    AGENTV3_PROJECT_CONFIG_RELATIVE_PATH = os.getenv(
        "DAWNCHAT_AGENTV3_PROJECT_CONFIG_RELATIVE_PATH", ".dawnchat/agentv3.json"
    )
    AGENTV3_GLOBAL_CONFIG_PATH = os.getenv(
        "DAWNCHAT_AGENTV3_GLOBAL_CONFIG_PATH",
        str(DATA_DIR / "agentv3" / "config.json"),
    )
    AGENTV3_MAX_STEPS = int(os.getenv("DAWNCHAT_AGENTV3_MAX_STEPS", "60"))
    AGENTV3_CONTEXT_LENGTH = int(os.getenv("DAWNCHAT_AGENTV3_CONTEXT_LENGTH", "262144"))
    AGENTV3_TOOL_REPEAT_FAIL_THRESHOLD = int(os.getenv("DAWNCHAT_AGENTV3_TOOL_REPEAT_FAIL_THRESHOLD", "3"))
    AGENTV3_TOOL_CONSEC_FAIL_THRESHOLD = int(os.getenv("DAWNCHAT_AGENTV3_TOOL_CONSEC_FAIL_THRESHOLD", "2"))
    AGENTV3_ENABLE_TOOL_LOOP_GUARD = os.getenv("DAWNCHAT_AGENTV3_ENABLE_TOOL_LOOP_GUARD", "true").lower() == "true"
    AGENTV3_ENABLE_STEP_RETRY_ON_RETRYABLE = (
        os.getenv("DAWNCHAT_AGENTV3_ENABLE_STEP_RETRY_ON_RETRYABLE", "true").lower() == "true"
    )
    AGENTV3_STEP_RETRY_LIMIT = int(os.getenv("DAWNCHAT_AGENTV3_STEP_RETRY_LIMIT", "1"))
    
    # ============ AI Token 预算配置 ============
    # 按任务类型分类的 max_tokens 配置，解决响应被截断问题
    # 
    # 设计原则：
    # 1. 需要返回结构化 JSON 的任务给足空间（防止截断）
    # 2. 多模态任务预留更多空间（图片描述往往较长）
    # 3. 直接回复任务可以较小（纯文本，边生成边返回）
    #
    class TokenBudget:
        """不同任务类型的 token 预算配置"""
        
        # 意图分析：需要返回完整 JSON，包含 reasoning 字段
        INTENT_ANALYSIS = 4096
        
        # 计划创建：返回多步骤的 TodoList JSON
        PLAN_CREATION = 8192
        
        # 直接回复：纯文本回复，支持长回复
        DIRECT_RESPONSE = 8192
        
        # 多模态观测：图片分析，返回界面元素 JSON
        VISION_OBSERVE = 8192
        
        # 动作决策：根据观测结果决定执行动作
        ACTION_DECISION = 4096
        
        # 验证判断：对比前后状态
        VALIDATION = 4096
        
        # ReAct 推理：每步推理和工具调用
        REACT_STEP = 4096
        
        # 最终整合：整合多步骤结果
        FINALIZE = 8192
        
        # 截断自动重试时的增量倍数
        RETRY_MULTIPLIER = 2
        
        # 最大 token 限制（防止无限增长）
        MAX_LIMIT = 65535
    
    # ============ 日志配置 ============
    _env_log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    LOG_LEVEL = getattr(logging, _env_log_level, logging.DEBUG)
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # ============ 安全配置 ============
    # API 访问令牌（实际应用中应该动态生成）
    API_TOKEN: Optional[str] = None

    # ============ 分域配置（Typed settings） ============
    RUNTIME = RuntimeSettings(
        api_host=API_HOST,
        api_port=API_PORT,
        test_mode=TEST_MODE,
        data_dir=DATA_DIR,
        logs_dir=LOGS_DIR,
    )
    PLUGIN = PluginSettings(
        root_dir=PLUGIN_ROOT_DIR,
        sources_dir=PLUGIN_SOURCES_DIR,
        data_dir=PLUGIN_DATA_DIR,
        models_dir=PLUGIN_MODELS_DIR,
        download_dir=PLUGIN_DOWNLOAD_DIR,
        preview_enabled=PLUGIN_PREVIEW_ENABLED,
        preview_bind_host=PLUGIN_PREVIEW_BIND_HOST,
        preview_port_range=PLUGIN_PREVIEW_PORT_RANGE,
    )
    AGENT = AgentSettings(
        runtime=AGENT_RUNTIME,
        default_agent=AGENTV3_DEFAULT_AGENT,
        max_steps=AGENTV3_MAX_STEPS,
        context_length=AGENTV3_CONTEXT_LENGTH,
    )
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        directories = [
            cls.DATA_DIR,
            cls.LOGS_DIR,
            cls.MODELS_DIR,
            cls.WORKBENCH_PROJECTS_DIR,
            cls.BIN_DIR,
            cls.HF_CACHE_DIR,
            cls.VOICES_DIR,
            cls.TTS_MODEL_DIR,
            cls.WHISPER_MODELS_DIR,
            cls.ADB_RESOURCES_DIR,
            cls.ADB_SCREENSHOT_DIR,
            cls.ADB_LOG_DIR,
            cls.PLUGIN_ROOT_DIR,
            cls.PLUGIN_SOURCES_DIR,
            cls.PLUGIN_DATA_DIR,
            cls.PLUGIN_MODELS_DIR,
            cls.PLUGIN_DOWNLOAD_DIR,
            cls.PLUGIN_OPENCODE_RULES_DIR,
            cls.PLUGIN_OPENCODE_RULES_VERSIONS_DIR,
            cls.PLUGIN_OPENCODE_RULES_CACHE_DIR,
            cls.PLUGINS_VENV_DIR,
            cls.UV_CACHE_DIR,
            cls.OPENCODE_DATA_DIR,
            cls.OPENCODE_LOGS_DIR,
            cls.CLAUDE_DATA_DIR,
            cls.CLAUDE_LOGS_DIR,
            cls.PIPELINE_ARTIFACTS_DIR,
            cls.PIPELINE_WORKSPACES_DIR,
            cls.WORKER_DATA_DIR,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_project_root(cls) -> Path:
        """获取项目根目录"""
        return cls.PROJECT_ROOT
    
# 在模块加载时确保目录存在
Config.ensure_directories()
