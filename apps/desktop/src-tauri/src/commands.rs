use std::fs::OpenOptions;
use std::io::Write;

use tauri::{Theme, Window};
use tracing::info;

#[tauri::command]
pub fn get_backend_url() -> String {
    crate::get_backend_url()
}

#[tauri::command]
pub fn consume_pending_auth_callback() -> Option<String> {
    crate::deep_link::consume_pending_auth_callback()
}

#[tauri::command]
pub fn set_native_theme(window: Window, theme: &str) -> Result<(), String> {
    let tauri_theme = match theme {
        "light" => Some(Theme::Light),
        "dark" => Some(Theme::Dark),
        _ => None,
    };

    info!("🎨 设置原生窗口主题: {:?}", tauri_theme);
    window.set_theme(tauri_theme).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn append_frontend_log(line: String) -> Result<(), String> {
    let path = crate::app_paths::frontend_log_path().map_err(|e| e.to_string())?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|e| e.to_string())?;

    file.write_all(line.as_bytes()).map_err(|e| e.to_string())?;
    file.write_all(b"\n").map_err(|e| e.to_string())
}
