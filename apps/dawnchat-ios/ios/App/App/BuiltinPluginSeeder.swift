import Foundation

private struct BundledManifest: Codable {
    let pluginId: String
    let version: String
    let name: String
    let entry: String

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        pluginId = try c.decode(String.self, forKey: .pluginId)
        version = try c.decode(String.self, forKey: .version)
        name = try c.decode(String.self, forKey: .name)
        entry = try c.decodeIfPresent(String.self, forKey: .entry) ?? BuiltinMobileAssistant.entry
    }

    init(pluginId: String, version: String, name: String, entry: String) {
        self.pluginId = pluginId
        self.version = version
        self.name = name
        self.entry = entry
    }

    private enum CodingKeys: String, CodingKey {
        case pluginId, version, name, entry
    }
}

enum BuiltinPluginSeeder {
    static func embeddedCatalogVersion() -> String {
        readBundledManifest()?.version ?? BuiltinMobileAssistant.fallbackBundledVersion
    }

    static func seedIfNeeded() async {
        await Task.detached(priority: .utility) {
            seedIfNeededSync()
        }.value
    }

    private static func readBundledManifest() -> BundledManifest? {
        guard
            let url = Bundle.main.url(
                forResource: "builtin-manifest",
                withExtension: "json",
                subdirectory: "BuiltinPlugins"
            ),
            let data = try? Data(contentsOf: url),
            let decoded = try? JSONDecoder().decode(BundledManifest.self, from: data)
        else {
            return nil
        }
        return decoded
    }

    private static func seedIfNeededSync() {
        let storage = PluginStorageService.shared
        let fileManager = FileManager.default
        let manifest = readBundledManifest() ?? BundledManifest(
            pluginId: BuiltinMobileAssistant.pluginId,
            version: BuiltinMobileAssistant.fallbackBundledVersion,
            name: BuiltinMobileAssistant.displayName,
            entry: BuiltinMobileAssistant.entry
        )

        guard
            let bundleSrc = Bundle.main.url(
                forResource: manifest.version,
                withExtension: nil,
                subdirectory: "BuiltinPlugins/builtin_mobile_assistant"
            )
        else {
            return
        }

        let paths: (pluginDir: URL, tempZip: URL, tempExtract: URL, finalVersionDir: URL)
        do {
            paths = try storage.prepareInstallPaths(pluginId: manifest.pluginId, version: manifest.version)
        } catch {
            return
        }

        let entryURL = paths.finalVersionDir.appendingPathComponent(manifest.entry)
        if !fileManager.fileExists(atPath: entryURL.path) {
            if fileManager.fileExists(atPath: paths.finalVersionDir.path) {
                try? fileManager.removeItem(at: paths.finalVersionDir)
            }
            do {
                try fileManager.copyItem(at: bundleSrc, to: paths.finalVersionDir)
            } catch {
                return
            }
        }

        guard fileManager.fileExists(atPath: entryURL.path) else { return }

        let existing = storage.readPluginMetadata(pluginId: manifest.pluginId)
        let lastLineage = HostBuiltinAssistantPrefs.lastLineageVersion

        if existing == nil {
            let meta = PluginMetadata(
                pluginId: manifest.pluginId,
                name: manifest.name,
                currentVersion: manifest.version,
                entry: manifest.entry,
                updatedAt: Date(),
                lastInstallStatus: "success"
            )
            try? storage.writePluginMetadata(meta)
            HostBuiltinAssistantPrefs.lastLineageVersion = manifest.version
            return
        }

        if !HostBuiltinAssistantPrefs.isLineageExternal,
           let lastLineage,
           existing?.pluginId == manifest.pluginId,
           existing?.currentVersion == lastLineage,
           lastLineage != manifest.version {
            let meta = PluginMetadata(
                pluginId: manifest.pluginId,
                name: manifest.name,
                currentVersion: manifest.version,
                entry: manifest.entry,
                updatedAt: Date(),
                lastInstallStatus: "success"
            )
            try? storage.writePluginMetadata(meta)
            HostBuiltinAssistantPrefs.lastLineageVersion = manifest.version
            return
        }

        if let existing, existing.pluginId == manifest.pluginId, existing.currentVersion == manifest.version {
            var m = existing
            m.name = manifest.name
            m.entry = manifest.entry
            m.updatedAt = Date()
            try? storage.writePluginMetadata(m)
        }
    }
}
