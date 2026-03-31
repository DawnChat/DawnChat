/// DawnChat Rust 层日志系统
///
/// 使用 tracing + tracing-subscriber + tracing-appender 实现专业的日志管理
/// 日志输出到用户日志目录（与 Python 层对齐）
use std::sync::OnceLock;
use tracing_appender::rolling::{RollingFileAppender, Rotation};
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

static LOG_GUARD: OnceLock<tracing_appender::non_blocking::WorkerGuard> = OnceLock::new();

/// 初始化全局日志系统
///
/// 特性：
/// - 日志输出到桌面的 DawnChat_Rust.log 文件
/// - 每天轮换日志文件（保留历史日志）
/// - 同时输出到控制台（开发模式）
/// - 结构化日志格式（包含时间戳、级别、模块、行号）
/// - 支持环境变量配置日志级别（RUST_LOG）
pub fn init_logger() -> Result<(), Box<dyn std::error::Error>> {
    let logs_dir = crate::app_paths::ensure_user_logs_dir()?;

    // 创建滚动文件 appender - 每天轮换
    // 日志文件: DawnChat_Rust.log, DawnChat_Rust.log.2025-11-20, ...
    let file_appender = RollingFileAppender::new(Rotation::DAILY, &logs_dir, "DawnChat_Rust.log");

    // 创建非阻塞写入器（提升性能）
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

    // 文件日志层 - 格式化输出
    let file_layer = fmt::layer()
        .with_writer(non_blocking)
        .with_ansi(false) // 文件中不使用颜色代码
        .with_target(true) // 包含模块路径
        .with_thread_ids(false) // 不显示线程ID（简洁）
        .with_thread_names(false)
        .with_file(true) // 包含文件名
        .with_line_number(true) // 包含行号
        .with_level(true) // 包含日志级别
        .compact(); // 使用紧凑格式

    // 环境过滤器 - 支持 RUST_LOG 环境变量
    // Debug 模式: 默认为 DEBUG
    // Release 模式: 默认为 ERROR
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| {
        #[cfg(debug_assertions)]
        let default_level = "debug";

        #[cfg(not(debug_assertions))]
        let default_level = "error";

        EnvFilter::new(default_level)
            // DawnChat 自身模块
            .add_directive(format!("app_lib={}", default_level).parse().unwrap())
    });

    // 根据是否为调试模式决定是否输出到控制台
    #[cfg(debug_assertions)]
    {
        // 开发模式：同时输出到文件和控制台
        let console_layer = fmt::layer()
            .with_target(true)
            .with_file(true)
            .with_line_number(true)
            .with_level(true)
            .pretty(); // 使用美化格式（带颜色）

        tracing_subscriber::registry()
            .with(env_filter)
            .with(file_layer)
            .with(console_layer)
            .try_init()?;

        tracing::info!("🚀 DawnChat 日志系统已初始化 (Debug Mode)");
    }

    #[cfg(not(debug_assertions))]
    {
        // 生产模式：仅输出到文件
        tracing_subscriber::registry()
            .with(env_filter)
            .with(file_layer)
            .try_init()?;

        tracing::info!("🚀 DawnChat 日志系统已初始化 (Release Mode)");
    }

    tracing::info!("📝 日志文件位置: {}/DawnChat_Rust.log", logs_dir.display());

    // 需要保持 guard 存活，否则日志会丢失。
    // OnceLock 保证只初始化一次，避免内存泄漏方案。
    let _ = LOG_GUARD.set(guard);

    Ok(())
}

/// 记录系统信息（用于调试）
pub fn log_system_info() {
    tracing::info!("============================================================");
    tracing::info!("🖥️  系统信息");
    tracing::info!("============================================================");

    #[cfg(target_os = "macos")]
    tracing::info!("操作系统: macOS");

    #[cfg(target_os = "linux")]
    tracing::info!("操作系统: Linux");

    #[cfg(target_os = "windows")]
    tracing::info!("操作系统: Windows");

    #[cfg(target_arch = "aarch64")]
    tracing::info!("架构: ARM64 (aarch64)");

    #[cfg(target_arch = "x86_64")]
    tracing::info!("架构: x86_64");

    #[cfg(debug_assertions)]
    tracing::info!("构建模式: Debug");

    #[cfg(not(debug_assertions))]
    tracing::info!("构建模式: Release");

    tracing::info!("============================================================");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_logger_initialization() {
        // 测试日志系统初始化
        // 注意：实际应用中只能初始化一次
        if let Err(e) = init_logger() {
            eprintln!("日志初始化失败: {}", e);
        }

        tracing::info!("测试日志 - INFO");
        tracing::warn!("测试日志 - WARN");
        tracing::error!("测试日志 - ERROR");
        tracing::debug!("测试日志 - DEBUG");
    }
}
