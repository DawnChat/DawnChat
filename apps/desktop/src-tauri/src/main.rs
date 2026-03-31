// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use chrono::Local;
use std::fs::File;
use std::io::Write;
use std::panic;

fn main() {
    panic::set_hook(Box::new(|panic_info| {
        let log_path = app_lib::app_paths::crash_log_path()
            .unwrap_or_else(|_| std::env::temp_dir().join("DawnChat_crash.log"));

        if let Ok(mut file) = File::create(&log_path) {
            let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S");

            let payload = if let Some(s) = panic_info.payload().downcast_ref::<&str>() {
                s.to_string()
            } else if let Some(s) = panic_info.payload().downcast_ref::<String>() {
                s.clone()
            } else {
                "Payload not available as a string".to_string()
            };

            let location = panic_info
                .location()
                .map_or("No location".to_string(), |l| {
                    format!("{}:{}:{}", l.file(), l.line(), l.column())
                });

            let log_message = format!(
                "[{}] App crashed!\nLocation: {}\nPayload: {}\n\n---\nPanic Info:\n{:?}\n---",
                timestamp, location, payload, panic_info
            );

            let _ = file.write_all(log_message.as_bytes());
        }
    }));

    app_lib::run();
}
