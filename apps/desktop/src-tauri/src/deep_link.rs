use std::sync::{Mutex, OnceLock};
use tauri::{AppHandle, Emitter};
use tauri_plugin_deep_link::DeepLinkExt;
use tracing::{error, info};
use url::Url;

const DEEP_LINK_SCHEME: &str = "dawnchat";
const AUTH_CALLBACK_HOST: &str = "auth";
const AUTH_CALLBACK_PATH: &str = "/callback";
const AUTH_ALLOWED_QUERY_KEYS: [&str; 6] = [
    "ticket",
    "state",
    "error",
    "error_code",
    "error_description",
    "next",
];

static PENDING_AUTH_CALLBACK: OnceLock<Mutex<Option<String>>> = OnceLock::new();

fn get_pending_auth_callback() -> &'static Mutex<Option<String>> {
    PENDING_AUTH_CALLBACK.get_or_init(|| Mutex::new(None))
}

fn set_pending_auth_callback(url: String) {
    if let Ok(mut pending) = get_pending_auth_callback().lock() {
        *pending = Some(url);
    }
}

pub fn consume_pending_auth_callback() -> Option<String> {
    get_pending_auth_callback()
        .lock()
        .ok()
        .and_then(|mut pending| pending.take())
}

fn is_supported_route_host(host: &str) -> bool {
    matches!(host, "apps" | "pipeline" | "workbench")
}

fn normalize_auth_callback_url(raw_url: &str) -> Option<String> {
    let mut parsed = Url::parse(raw_url).ok()?;
    if parsed.scheme() != DEEP_LINK_SCHEME {
        return None;
    }
    if parsed.host_str()? != AUTH_CALLBACK_HOST || parsed.path() != AUTH_CALLBACK_PATH {
        return None;
    }

    let filtered: Vec<(String, String)> = parsed
        .query_pairs()
        .filter(|(key, _)| AUTH_ALLOWED_QUERY_KEYS.contains(&key.as_ref()))
        .map(|(key, value)| (key.into_owned(), value.into_owned()))
        .collect();

    parsed.set_fragment(None);
    parsed.set_query(None);
    {
        let mut pairs = parsed.query_pairs_mut();
        for (key, value) in filtered {
            pairs.append_pair(&key, &value);
        }
    }

    Some(parsed.to_string())
}

fn normalize_route_deep_link(raw_url: &str) -> Option<String> {
    let mut parsed = Url::parse(raw_url).ok()?;
    if parsed.scheme() != DEEP_LINK_SCHEME {
        return None;
    }
    let host = parsed.host_str()?;
    if !is_supported_route_host(host) {
        return None;
    }

    parsed.set_fragment(None);
    Some(parsed.to_string())
}

pub fn setup(app_handle: &AppHandle) {
    #[cfg(any(
        target_os = "macos",
        target_os = "linux",
        all(debug_assertions, target_os = "windows")
    ))]
    {
        let handle = app_handle.clone();
        let emitter_handle = handle.clone();

        if let Err(e) = handle.deep_link().register("dawnchat") {
            error!("❌ 注册 Deep Link 协议失败: {}", e);
        } else {
            info!("✅ Deep Link 协议已注册: dawnchat://");
        }

        handle.deep_link().on_open_url(move |event| {
            let urls = event.urls();
            let mut route_urls: Vec<String> = Vec::new();

            for raw_url in urls.iter().map(|u| u.to_string()) {
                info!("🔗 [Rust] 捕获 Deep Link: {}", raw_url);

                if let Some(auth_url) = normalize_auth_callback_url(&raw_url) {
                    info!("✅ 已识别认证回调 Deep Link");
                    set_pending_auth_callback(auth_url.clone());
                    if let Err(e) = emitter_handle.emit("deep-link-auth-callback", auth_url.clone())
                    {
                        error!("❌ 发送 deep-link-auth-callback 失败: {}", e);
                    }
                    continue;
                }

                if let Some(route_url) = normalize_route_deep_link(&raw_url) {
                    route_urls.push(route_url);
                    continue;
                }

                info!("ℹ️ 已忽略不受支持的 Deep Link");
            }

            if !route_urls.is_empty() {
                if let Err(e) = emitter_handle.emit("deep-link-route", route_urls.clone()) {
                    error!("❌ 发送 deep-link-route 失败: {}", e);
                }
                // 兼容旧前端监听器，后续可移除。
                if let Err(e) = emitter_handle.emit("deep-link-event", route_urls) {
                    error!("❌ 发送兼容事件 deep-link-event 失败: {}", e);
                }
            }
        });
    }

    info!("✅ Deep Link 插件已初始化");
}
