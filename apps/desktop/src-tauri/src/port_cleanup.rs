use std::process::Command;
use tracing::{debug, info, warn};

/// 清理占用指定端口的进程
pub fn cleanup_port(port: u16) -> bool {
    debug!("🔍 检查端口 {} 是否被占用...", port);

    #[cfg(target_os = "macos")]
    {
        let output = Command::new("lsof")
            .args(&["-ti", &format!(":{}", port)])
            .output();

        if let Ok(output) = output {
            let pids = String::from_utf8_lossy(&output.stdout);
            let pids: Vec<&str> = pids.trim().split('\n').filter(|s| !s.is_empty()).collect();

            if !pids.is_empty() {
                warn!("⚠️  端口 {} 被以下进程占用: {:?}", port, pids);

                for pid in pids {
                    info!("🔪 尝试终止进程 PID: {}", pid);
                    let _ = Command::new("kill").arg(pid).output();

                    let start_wait = std::time::Instant::now();
                    let mut killed = false;

                    while start_wait.elapsed().as_millis() < 2000 {
                        let check = Command::new("ps").args(&["-p", pid]).output();

                        if let Ok(check) = check {
                            if !check.status.success() || check.stdout.is_empty() {
                                info!("✅ 进程 {} 已终止", pid);
                                killed = true;
                                break;
                            }
                        }
                        std::thread::sleep(std::time::Duration::from_millis(100));
                    }

                    if !killed {
                        warn!("⚠️  进程 {} 仍在运行，使用 SIGKILL 强制终止", pid);
                        let _ = Command::new("kill").args(&["-9", pid]).output();
                        std::thread::sleep(std::time::Duration::from_millis(200));
                    }
                }

                let start_check = std::time::Instant::now();
                while start_check.elapsed().as_millis() < 2000 {
                    let check_output = Command::new("lsof")
                        .args(&["-ti", &format!(":{}", port)])
                        .output();

                    if let Ok(output) = check_output {
                        if output.stdout.is_empty() {
                            info!("✅ 端口 {} 清理完成", port);
                            return true;
                        }
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                }

                warn!("⚠️  端口 {} 可能仍未释放", port);
                return true;
            } else {
                debug!("✅ 端口 {} 未被占用", port);
                return false;
            }
        }
    }

    #[cfg(target_os = "linux")]
    {
        let output = Command::new("lsof")
            .args(&["-ti", &format!(":{}", port)])
            .output();

        if let Ok(output) = output {
            let pids = String::from_utf8_lossy(&output.stdout);
            let pids: Vec<&str> = pids.trim().split('\n').filter(|s| !s.is_empty()).collect();

            if !pids.is_empty() {
                warn!("⚠️  端口 {} 被占用，终止进程: {:?}", port, pids);
                for pid in pids {
                    let _ = Command::new("kill").arg("-9").arg(pid).output();
                }
                std::thread::sleep(std::time::Duration::from_millis(500));
                return true;
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        let output = Command::new("netstat").args(&["-ano"]).output();

        if let Ok(output) = output {
            let output_str = String::from_utf8_lossy(&output.stdout);
            for line in output_str.lines() {
                if line.contains(&format!(":{}", port)) && line.contains("LISTENING") {
                    if let Some(pid) = line.split_whitespace().last() {
                        warn!("⚠️  端口 {} 被进程 {} 占用，尝试终止", port, pid);
                        let _ = Command::new("taskkill").args(&["/F", "/PID", pid]).output();
                        std::thread::sleep(std::time::Duration::from_millis(500));
                        return true;
                    }
                }
            }
        }
    }

    false
}
