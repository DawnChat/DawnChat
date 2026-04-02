use std::fs::File;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use tracing::{error, info};

/// 启动 Python 后端进程
///
/// 返回启动的子进程，如果启动失败则返回 None
pub fn spawn_python_backend(
    python_path: &PathBuf,
    main_script: &PathBuf,
    sidecar_dir: &PathBuf,
    log_path: &PathBuf,
    api_host: &str,
    api_port: u16,
) -> Option<Child> {
    let python_stdout = match File::create(log_path) {
        Ok(f) => f,
        Err(e) => {
            error!("❌ 无法创建 Python 日志文件: {}", e);
            return None;
        }
    };

    let python_stderr = match python_stdout.try_clone() {
        Ok(f) => f,
        Err(e) => {
            error!("❌ 无法克隆日志文件句柄: {}", e);
            return None;
        }
    };

    let python_home = sidecar_dir.join("python");
    let app_dir = sidecar_dir.join("app");

    #[cfg(target_os = "windows")]
    let site_packages = python_home.join("Lib").join("site-packages");

    #[cfg(not(target_os = "windows"))]
    let site_packages = python_home
        .join("lib")
        .join("python3.11")
        .join("site-packages");

    #[cfg(target_os = "windows")]
    let pythonpath_separator = ";";

    #[cfg(not(target_os = "windows"))]
    let pythonpath_separator = ":";

    let pythonpath = format!(
        "{}{}{}{}{}",
        sidecar_dir.display(),
        pythonpath_separator,
        app_dir.display(),
        pythonpath_separator,
        site_packages.display()
    );

    let mut command = Command::new(python_path);
    let forced_logs_dir = log_path
        .parent()
        .map(|path| path.to_string_lossy().to_string())
        .unwrap_or_else(|| sidecar_dir.display().to_string());
    let dawnchat_run_mode = if cfg!(debug_assertions) {
        "development"
    } else {
        "release"
    };

    command
        .arg(main_script)
        .env("PYTHONHOME", &python_home)
        .env("PYTHONPATH", &pythonpath)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("DAWNCHAT_RUN_MODE", dawnchat_run_mode)
        .env("DAWNCHAT_PARENT_PID", std::process::id().to_string())
        .env("DAWNCHAT_API_HOST", api_host)
        .env("DAWNCHAT_API_PORT", api_port.to_string())
        .env_remove("DAWNCHAT_LOGS_DIR")
        .env("DAWNCHAT_LOGS_DIR", forced_logs_dir)
        .env("PORT", api_port.to_string())
        .current_dir(sidecar_dir)
        .stdout(Stdio::from(python_stdout))
        .stderr(Stdio::from(python_stderr));

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            command.pre_exec(|| {
                if libc::setpgid(0, 0) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }

    match command.spawn() {
        Ok(child) => {
            info!("✅ Python 后端已启动, PID: {:?}", child.id());
            Some(child)
        }
        Err(e) => {
            error!("❌ Python 后端启动失败: {}", e);
            None
        }
    }
}

pub fn find_available_port() -> Option<u16> {
    TcpListener::bind("127.0.0.1:0")
        .ok()
        .and_then(|listener| listener.local_addr().ok().map(|addr| addr.port()))
}
