use std::io;
use std::path::PathBuf;

/// 返回 DawnChat 的跨平台日志目录。
///
/// 与 Python 层 `config.py::_get_user_logs_dir()` 对齐：
/// - macOS: ~/Library/Logs/DawnChat
/// - Windows: %LOCALAPPDATA%\DawnChat\Logs
/// - Linux: ~/.local/share/DawnChat/logs
pub fn user_logs_dir() -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        return dirs::home_dir()
            .unwrap_or_else(std::env::temp_dir)
            .join("Library")
            .join("Logs")
            .join("DawnChat");
    }

    #[cfg(target_os = "windows")]
    {
        if let Some(localappdata) = std::env::var_os("LOCALAPPDATA") {
            return PathBuf::from(localappdata).join("DawnChat").join("Logs");
        }

        return dirs::home_dir()
            .unwrap_or_else(std::env::temp_dir)
            .join("AppData")
            .join("Local")
            .join("DawnChat")
            .join("Logs");
    }

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        return dirs::home_dir()
            .unwrap_or_else(std::env::temp_dir)
            .join(".local")
            .join("share")
            .join("DawnChat")
            .join("logs");
    }
}

pub fn ensure_user_logs_dir() -> io::Result<PathBuf> {
    let dir = user_logs_dir();
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

pub fn rust_log_path() -> io::Result<PathBuf> {
    Ok(ensure_user_logs_dir()?.join("DawnChat_Rust.log"))
}

pub fn python_log_path() -> io::Result<PathBuf> {
    Ok(ensure_user_logs_dir()?.join("DawnChat_Python.log"))
}

pub fn crash_log_path() -> io::Result<PathBuf> {
    Ok(ensure_user_logs_dir()?.join("DawnChat_crash.log"))
}
