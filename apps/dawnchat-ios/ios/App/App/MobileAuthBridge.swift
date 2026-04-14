import Foundation

enum DesktopAuthBridgeConstants {
    static let protocolVersion = "1"
    /// Same as @dawnchat/auth-bridge DESKTOP_AUTH_CLIENT
    static let client = "desktop"
    static let defaultBridgePath = "/desktop-auth/bridge"
    static let pendingTtlMs: Int64 = 10 * 60 * 1000
    static let defaultNext = "/app/workbench"
}

enum MobileAuthBridge {

    static func generateState() -> String {
        "dc_" + UUID().uuidString.replacingOccurrences(of: "-", with: "")
    }

    static func normalizeNextPath(_ value: String?) -> String {
        let v = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !v.hasPrefix("/") || v.hasPrefix("//") { return DesktopAuthBridgeConstants.defaultNext }
        let ns = v as NSString
        let range = NSRange(location: 0, length: ns.length)
        guard let re = try? NSRegularExpression(pattern: "^/(app|fullscreen)(/|$)") else {
            return DesktopAuthBridgeConstants.defaultNext
        }
        if re.firstMatch(in: v, options: [], range: range) != nil {
            return v
        }
        return DesktopAuthBridgeConstants.defaultNext
    }

    static func buildBridgeURL(
        baseURL: String,
        state: String,
        deviceId: String,
        redirectUri: String,
        nextPath: String,
        provider: String? = nil
    ) throws -> URL {
        var trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var components = URLComponents(string: trimmed) else {
            throw NSError(domain: "MobileAuth", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid bridge base URL"])
        }
        if components.path.isEmpty || components.path == "/" {
            components.path = DesktopAuthBridgeConstants.defaultBridgePath
        }
        var items: [URLQueryItem] = [
            URLQueryItem(name: "client", value: DesktopAuthBridgeConstants.client),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "device_id", value: deviceId),
            URLQueryItem(name: "redirect_uri", value: redirectUri),
            URLQueryItem(name: "next", value: normalizeNextPath(nextPath)),
            URLQueryItem(name: "protocol_version", value: DesktopAuthBridgeConstants.protocolVersion),
        ]
        if let p = provider, p == "google" || p == "github" {
            items.append(URLQueryItem(name: "provider", value: p))
        }
        components.queryItems = items
        guard let url = components.url else {
            throw NSError(domain: "MobileAuth", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to build bridge URL"])
        }
        return url
    }

    static func parseCallback(_ url: URL) -> (ticket: String?, state: String?, error: String?) {
        let comp = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let items = comp?.queryItems ?? []
        func val(_ name: String) -> String? {
            items.first { $0.name == name }?.value
        }
        let err = val("error_description") ?? val("error")
        return (val("ticket"), val("state"), err)
    }

    static func matchesRedirect(_ url: URL, expectedRedirect: String) -> Bool {
        guard let expected = URL(string: expectedRedirect), let expComp = URLComponents(url: expected, resolvingAgainstBaseURL: false) else {
            return false
        }
        guard let gotComp = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return false }
        guard gotComp.scheme?.lowercased() == expComp.scheme?.lowercased() else { return false }
        guard gotComp.host?.lowercased() == expComp.host?.lowercased() else { return false }
        let ep = expComp.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let gp = gotComp.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return ep == gp
    }
}
