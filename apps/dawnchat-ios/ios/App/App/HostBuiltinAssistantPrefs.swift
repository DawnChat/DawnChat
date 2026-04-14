import Foundation

/// Tracks built-in assistant lineage vs QR-installed versions (see `BuiltinPluginSeeder`).
enum HostBuiltinAssistantPrefs {
    private static let builtinSuiteName = "host_builtin_assistant"
    private static let keyLastLineage = "last_lineage_version"
    private static let keyAutoOpenedEmbedded = "auto_opened_embedded_version"
    private static let keyAutoOpenEnabled = "auto_open_mobile_assistant"

    static let externalLineage = "__external__"

    private static var builtin: UserDefaults {
        UserDefaults(suiteName: builtinSuiteName) ?? .standard
    }

    static var lastLineageVersion: String? {
        get { builtin.string(forKey: keyLastLineage) }
        set {
            if let v = newValue {
                builtin.set(v, forKey: keyLastLineage)
            } else {
                builtin.removeObject(forKey: keyLastLineage)
            }
        }
    }

    /// Call after a bundle (QR) install for the official assistant id so we do not overwrite user-picked versions.
    static func markExternalInstall(pluginId: String) {
        if pluginId == BuiltinMobileAssistant.pluginId {
            lastLineageVersion = externalLineage
        }
    }

    static var isLineageExternal: Bool {
        lastLineageVersion == externalLineage
    }

    static var isAutoOpenEnabled: Bool {
        if UserDefaults.standard.object(forKey: keyAutoOpenEnabled) == nil {
            return true
        }
        return UserDefaults.standard.bool(forKey: keyAutoOpenEnabled)
    }

    static func setAutoOpenEnabled(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: keyAutoOpenEnabled)
    }

    static var autoOpenedEmbeddedVersion: String? {
        get { builtin.string(forKey: keyAutoOpenedEmbedded) }
        set {
            if let v = newValue {
                builtin.set(v, forKey: keyAutoOpenedEmbedded)
            } else {
                builtin.removeObject(forKey: keyAutoOpenedEmbedded)
            }
        }
    }
}
