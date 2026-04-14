import Foundation

/// Defaults when `BuiltinPlugins/builtin-manifest.json` is missing; after running
/// `scripts/mobile/build-builtin-mobile-assistant.sh`, the manifest is authoritative.
enum BuiltinMobileAssistant {
    static let pluginId = "com.dawnchat.mobile-ai-assistant"
    static let displayName = "Mobile AI Assistant"
    static let entry = "index.html"
    static let assetRoot = "builtin_mobile_assistant"
    static let fallbackBundledVersion = "1.0.0"
}
