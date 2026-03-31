use std::process::ExitStatus;
use std::time::{Duration, Instant};
use tracing::{error, info, warn};

/// Python 进程监控器
///
/// 负责监控 Python 后端进程的健康状态，并在崩溃时自动重启。
/// 采用指数退避策略，防止无限重启循环。
pub struct ProcessSupervisor {
    /// 重启次数（在冷却期内）
    restart_count: u32,
    /// 上次启动时间
    last_start: Instant,
    /// 最大重启次数（冷却期内）
    max_restarts: u32,
    /// 冷却期（稳定运行超过此时间则重置计数）
    cooldown_period: Duration,
    /// 基础重启延迟
    base_delay: Duration,
    /// 进程检查间隔
    pub check_interval: Duration,
}

impl ProcessSupervisor {
    pub fn new() -> Self {
        Self {
            restart_count: 0,
            last_start: Instant::now(),
            max_restarts: 5,
            cooldown_period: Duration::from_secs(60),
            base_delay: Duration::from_secs(2),
            check_interval: Duration::from_secs(5),
        }
    }

    /// 判断是否应该重启，并返回重启前的延迟时间
    ///
    /// 返回 None 表示不应重启（正常退出或重启次数过多）
    pub fn should_restart(&mut self, exit_status: Option<ExitStatus>) -> Option<Duration> {
        if let Some(status) = exit_status {
            if status.success() {
                info!("Python 进程正常退出 (code 0)，不重启");
                return None;
            }

            #[cfg(unix)]
            {
                use std::os::unix::process::ExitStatusExt;
                if let Some(signal) = status.signal() {
                    if signal == 15 || signal == 2 {
                        info!("Python 进程被信号 {} 终止，不重启", signal);
                        return None;
                    }
                }
            }
        }

        if self.last_start.elapsed() > self.cooldown_period {
            info!(
                "Python 进程稳定运行超过 {:?}，重置重启计数",
                self.cooldown_period
            );
            self.restart_count = 0;
        }

        if self.restart_count >= self.max_restarts {
            error!(
                "❌ Python 进程重启次数过多 ({}/{}), 放弃重启",
                self.restart_count, self.max_restarts
            );
            return None;
        }

        let delay = self.base_delay * 2_u32.pow(self.restart_count);
        self.restart_count += 1;

        warn!(
            "⚠️ Python 进程意外退出，将在 {:?} 后尝试重启 (第 {}/{} 次)",
            delay, self.restart_count, self.max_restarts
        );

        Some(delay)
    }

    /// 记录进程启动
    pub fn on_process_started(&mut self) {
        self.last_start = Instant::now();
    }
}
