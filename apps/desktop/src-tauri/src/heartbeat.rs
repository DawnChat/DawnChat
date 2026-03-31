use tauri::{AppHandle, Emitter};
use tracing::info;

pub fn start_heartbeat(app_handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(25));
        loop {
            interval.tick().await;
            let _ = app_handle.emit("heartbeat", "keep-alive");
        }
    });
    info!("💓 Heartbeat mechanism started (25s interval)");
}
