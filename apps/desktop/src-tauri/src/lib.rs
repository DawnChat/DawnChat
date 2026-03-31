use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Instant;
use tauri::Emitter;
use tauri::Manager;
use tracing::{error, info, warn};

pub mod app_paths;
mod backend_launcher;
mod commands;
mod deep_link;
mod heartbeat;
mod logger;
mod process_supervisor;
use process_supervisor::ProcessSupervisor;

// 全局进程管理器（当前仅管理 Python 后端一个进程）
static PROCESS_MANAGER: OnceLock<Arc<Mutex<Option<Child>>>> = OnceLock::new();

// 全局应用关闭标志
static APP_SHUTTING_DOWN: AtomicBool = AtomicBool::new(false);

static BACKEND_URL: OnceLock<String> = OnceLock::new();

/// 获取进程管理器实例
fn get_process_manager() -> Arc<Mutex<Option<Child>>> {
    PROCESS_MANAGER
        .get_or_init(|| Arc::new(Mutex::new(None)))
        .clone()
}

fn set_backend_url(url: String) {
    let _ = BACKEND_URL.set(url);
}

pub fn get_backend_url() -> String {
    BACKEND_URL
        .get()
        .cloned()
        .unwrap_or_else(|| "http://127.0.0.1:8000".to_string())
}

/// 强制终止进程（包括子进程）
fn force_kill_process(pid: u32) {
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    {
        // Unix: 终止整个进程组（负 PID）
        let _ = Command::new("kill")
            .args(&["-TERM", &format!("-{}", pid)])
            .output();

        // 等待一点时间让进程优雅退出
        std::thread::sleep(std::time::Duration::from_millis(500));

        // 如果还在运行，强制杀死
        let _ = Command::new("kill")
            .args(&["-KILL", &format!("-{}", pid)])
            .output();
    }

    #[cfg(target_os = "windows")]
    {
        // Windows: 使用 taskkill
        let _ = Command::new("taskkill")
            .args(&["/F", "/T", "/PID", &pid.to_string()])
            .output();
    }
}

/// 等待子进程退出（带超时）
fn wait_for_child_with_timeout(
    child: &mut Child,
    timeout: std::time::Duration,
) -> std::io::Result<Option<std::process::ExitStatus>> {
    use std::thread;
    use std::time::Instant;

    let start = Instant::now();

    loop {
        match child.try_wait() {
            Ok(Some(status)) => return Ok(Some(status)),
            Ok(None) => {
                if start.elapsed() >= timeout {
                    return Ok(None);
                }
                thread::sleep(std::time::Duration::from_millis(100));
            }
            Err(e) => return Err(e),
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 初始化全局日志系统（必须在最开始）
    if let Err(e) = logger::init_logger() {
        eprintln!("❌ 日志系统初始化失败: {}", e);
    }

    // 记录系统信息
    logger::log_system_info();

    if let Err(e) = tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            commands::get_backend_url,
            commands::consume_pending_auth_callback,
            commands::set_native_theme
        ])
        .setup(|app| {
            info!("🚀 DawnChat 应用启动");

            // 启动心跳机制，解决 macOS 下窗口最小化后 WebSocket 连接断开的问题
            heartbeat::start_heartbeat(app.handle().clone());

            info!("============================================");

            deep_link::setup(&app.handle().clone());

            // 启动 Python 后端 sidecar (PBS 方案)
            info!("📦 开始启动 Python 后端 sidecar (PBS)...");

            // 获取 sidecar 路径
            let resource_path = match app.path().resource_dir() {
                Ok(path) => {
                    info!("✅ 资源目录: {:?}", path);
                    path
                }
                Err(e) => {
                    error!("❌ 获取资源目录失败: {}", e);
                    let _ = app.emit("backend-start-failed", format!("获取资源目录失败: {}", e));
                    return Ok(());
                }
            };

            let sidecar_dir = resource_path.join("sidecars/dawnchat-backend");

            // PBS 方案：使用嵌入式 Python 执行 main.py
            #[cfg(target_os = "windows")]
            let python_path = sidecar_dir.join("python").join("python.exe");

            #[cfg(not(target_os = "windows"))]
            let python_path = sidecar_dir.join("python").join("bin").join("python3.11");

            let main_script = sidecar_dir.join("app").join("main.py");

            info!("📂 Sidecar 目录: {:?}", sidecar_dir);
            info!("🐍 Python 路径: {:?}", python_path);
            info!("📜 入口脚本: {:?}", main_script);

            // 检查目录是否存在
            if !sidecar_dir.exists() {
                error!("❌ Sidecar 目录不存在!");
                let _ = app.emit(
                    "backend-start-failed",
                    format!("Sidecar 目录不存在: {:?}", sidecar_dir),
                );
                info!("尝试列出资源目录内容:");
                if let Ok(entries) = std::fs::read_dir(&resource_path) {
                    for entry in entries.flatten() {
                        info!("  - {:?}", entry.path());
                    }
                }
                return Ok(());
            }

            // 检查 Python 是否存在
            if !python_path.exists() {
                error!("❌ Python 解释器不存在: {:?}", python_path);
                let _ = app.emit(
                    "backend-start-failed",
                    format!("Python 解释器不存在: {:?}", python_path),
                );
                info!("尝试列出 sidecar 目录内容:");
                if let Ok(entries) = std::fs::read_dir(&sidecar_dir) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        info!("  - {:?}", path);
                    }
                }
                return Ok(());
            }

            // 检查入口脚本是否存在
            if !main_script.exists() {
                error!("❌ 入口脚本不存在: {:?}", main_script);
                let _ = app.emit(
                    "backend-start-failed",
                    format!("入口脚本不存在: {:?}", main_script),
                );
                return Ok(());
            }

            // 检查文件权限 (Unix)
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(metadata) = std::fs::metadata(&python_path) {
                    let mode = metadata.permissions().mode();
                    info!("📋 Python 权限: {:o}", mode);

                    if mode & 0o111 == 0 {
                        warn!("⚠️  警告: Python 不可执行，尝试添加执行权限...");
                        let _ = std::fs::set_permissions(
                            &python_path,
                            std::fs::Permissions::from_mode(0o755),
                        );
                    }
                }
            }

            let backend_port = backend_launcher::find_available_port().unwrap_or(8000);
            let backend_host = "127.0.0.1".to_string();
            let backend_url = format!("http://{}:{}", backend_host, backend_port);
            set_backend_url(backend_url.clone());
            let _ = app.emit("backend-url-updated", backend_url.clone());

            // 克隆路径用于后台线程
            let python_path_clone = python_path.clone();
            let main_script_clone = main_script.clone();
            let sidecar_dir_clone = sidecar_dir.clone();
            let python_log_path = app_paths::python_log_path().unwrap_or_else(|e| {
                warn!(
                    "⚠️  无法创建用户日志目录，将回退到临时目录记录 Python 日志: {}",
                    e
                );
                std::env::temp_dir().join("DawnChat_Python.log")
            });
            let backend_host_clone = backend_host.clone();
            let backend_url_clone = backend_url.clone();

            // 获取 app_handle 用于发送事件
            let app_handle_for_supervisor = app.handle().clone();

            info!("🚀 在后台线程启动服务...");
            info!("⚡ 应用界面将立即响应，服务在后台初始化");
            info!("📝 Python 日志文件: {:?}", python_log_path);

            // 在后台线程执行 Python 进程监控
            // 这个线程会持续运行，监控 Python 进程状态，并在崩溃时自动重启
            std::thread::spawn(move || {
                let start_time = Instant::now();
                info!("⏱️  [0ms] 后台线程启动 - ProcessSupervisor 模式");

                // 创建进程监控器
                let mut supervisor = ProcessSupervisor::new();

                // 进程监控主循环
                loop {
                    // 检查应用是否正在关闭
                    if APP_SHUTTING_DOWN.load(Ordering::SeqCst) {
                        info!("🛑 应用正在关闭，停止进程监控");
                        break;
                    }

                    // 启动 Python 后端
                    info!(
                        "⏱️  [{:?}] 启动 Python 后端进程...",
                        start_time.elapsed().as_millis()
                    );

                    let child = backend_launcher::spawn_python_backend(
                        &python_path_clone,
                        &main_script_clone,
                        &sidecar_dir_clone,
                        &python_log_path,
                        &backend_host_clone,
                        backend_port,
                    );

                    match child {
                        Some(process) => {
                            info!("🆔 Python 进程 PID: {}", process.id());
                            supervisor.on_process_started();

                            info!("🌐 后端监听: {}", backend_url_clone);
                            info!("📊 总启动时间: {:?}", start_time.elapsed());

                            // 将进程添加到管理器
                            {
                                if let Ok(mut manager) = get_process_manager().lock() {
                                    *manager = Some(process);
                                    info!("✅ Python 进程已注册到管理器");
                                }
                            }

                            // 进程监控循环
                            loop {
                                std::thread::sleep(supervisor.check_interval);

                                // 检查应用是否正在关闭
                                if APP_SHUTTING_DOWN.load(Ordering::SeqCst) {
                                    info!("🛑 应用正在关闭，停止进程监控");
                                    return;
                                }

                                // 检查进程状态
                                let exit_status = {
                                    if let Ok(mut manager) = get_process_manager().lock() {
                                        if let Some(child) = manager.as_mut() {
                                            match child.try_wait() {
                                                Ok(Some(status)) => {
                                                    // 进程已退出
                                                    *manager = None;
                                                    Some(Some(status))
                                                }
                                                Ok(None) => {
                                                    // 进程仍在运行
                                                    None
                                                }
                                                Err(e) => {
                                                    error!("❌ 检查进程状态失败: {}", e);
                                                    None
                                                }
                                            }
                                        } else {
                                            // 进程不在管理器中（可能已被关闭）
                                            Some(None)
                                        }
                                    } else {
                                        None
                                    }
                                };

                                // 如果进程退出了，决定是否重启
                                if let Some(status) = exit_status {
                                    if let Some(delay) = supervisor.should_restart(status) {
                                        // 通知前端后端已崩溃
                                        let _ =
                                            app_handle_for_supervisor.emit("backend-crashed", ());

                                        // 等待延迟后重启
                                        info!("⏳ 等待 {:?} 后重启...", delay);
                                        std::thread::sleep(delay);

                                        // 跳出内层循环，重新启动进程
                                        break;
                                    } else {
                                        // 不需要重启
                                        info!("📭 Python 进程监控结束");
                                        return;
                                    }
                                }
                            }

                            // 通知前端后端正在重启
                            let _ = app_handle_for_supervisor.emit("backend-restarting", ());
                            info!("🔄 正在重启 Python 后端...");
                        }
                        None => {
                            // 启动失败
                            if let Some(delay) = supervisor.should_restart(None) {
                                warn!("⚠️ Python 启动失败，将在 {:?} 后重试", delay);
                                std::thread::sleep(delay);
                            } else {
                                error!("❌ Python 启动失败次数过多，放弃重试");
                                let _ = app_handle_for_supervisor.emit(
                                    "backend-start-failed",
                                    "Python 启动失败次数过多，放弃重试".to_string(),
                                );
                                break;
                            }
                        }
                    }
                }

                info!("📭 ProcessSupervisor 线程退出");
            });

            info!("============================================");
            info!("🎯 启动流程完成");
            info!("============================================");

            Ok(())
        })
        .on_window_event(move |_window, event| {
            use tauri::WindowEvent;
            match event {
                WindowEvent::Destroyed => {
                    info!("🪟 窗口销毁事件触发");

                    // 设置应用关闭标志，通知 ProcessSupervisor 停止重启
                    APP_SHUTTING_DOWN.store(true, Ordering::SeqCst);

                    // 获取进程管理器并终止 Python 子进程
                    if let Ok(mut manager) = get_process_manager().lock() {
                        if let Some(mut child) = manager.take() {
                            let name = "python_backend";
                            info!("🛑 正在终止进程: {}", name);
                            let pid = child.id();

                            // 尝试温和终止
                            #[cfg(any(target_os = "macos", target_os = "linux"))]
                            {
                                let _ = Command::new("kill")
                                    .args(&["-TERM", &format!("-{}", pid)])
                                    .output();
                            }
                            #[cfg(target_os = "windows")]
                            {
                                let _ = child.kill();
                            }

                            // 等待进程退出（最多3秒）
                            match wait_for_child_with_timeout(
                                &mut child,
                                std::time::Duration::from_secs(3),
                            ) {
                                Ok(Some(status)) => {
                                    info!("✅ 进程 {} 已退出，状态: {:?}", name, status);
                                }
                                Ok(None) => {
                                    warn!("⚠️  进程 {} 在超时后仍在运行，强制杀死", name);
                                    force_kill_process(pid);
                                }
                                Err(e) => {
                                    error!("❌ 等待进程 {} 退出时出错: {}，强制杀死", name, e);
                                    force_kill_process(pid);
                                }
                            }
                        }
                    }
                }
                _ => {}
            }
        })
        .run(tauri::generate_context!())
    {
        panic!("Error while running Tauri application: {:?}", e)
    }
}
