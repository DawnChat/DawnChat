import Foundation
import Network
import Security
import Supabase

struct PendingAuthState: Codable {
    let state: String
    let deviceId: String
    let createdAt: Int64
    let nextPath: String?
}

/// UI-facing snapshot from Supabase Auth `User`; avoids binding views to SDK types.
struct UserProfileSnapshot: Sendable {
    let id: String
    let email: String?
    let phone: String?
    let displayName: String?
    let avatarUrl: String?
    let createdAtIso: String?
    let lastSignInAtIso: String?
}

private func metadataString(from meta: [String: AnyJSON], keys: String...) -> String? {
    for key in keys {
        guard let value = meta[key] else { continue }
        if case let .string(s) = value {
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { return t }
        }
    }
    return nil
}

private let profileDateFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
}()

private func mapSupabaseUserToProfile(_ u: User) -> UserProfileSnapshot {
    let meta = u.userMetadata
    let created = profileDateFormatter.string(from: u.createdAt)
    let lastIn: String? = u.lastSignInAt.map { profileDateFormatter.string(from: $0) }
    return UserProfileSnapshot(
        id: u.id.uuidString,
        email: u.email?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
        phone: u.phone?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
        displayName: metadataString(from: meta, keys: "full_name", "name", "display_name", "nickname"),
        avatarUrl: metadataString(from: meta, keys: "avatar_url", "picture", "avatar"),
        createdAtIso: created,
        lastSignInAtIso: lastIn
    )
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

/// Reachability for optional server-side session validation (offline: trust SDK session).
private final class DawnChatReachability {
    static let shared = DawnChatReachability()
    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "com.dawnchat.reachability")
    private(set) var isConnected = false
    private init() {
        monitor.pathUpdateHandler = { [weak self] path in
            self?.isConnected = path.status == .satisfied
        }
        monitor.start(queue: queue)
    }
}

@MainActor
final class MobileAuthRepository {
    static let shared = MobileAuthRepository()

    private let defaults = UserDefaults.standard
    private let pendingKey = "dawnchat_mobile_auth_pending_json"
    private let deviceKey = "dawnchat_device_install_id"

    private var supabaseClient: SupabaseClient?

    private init() {}

    var redirectURI: String {
        (Bundle.main.object(forInfoDictionaryKey: "DawnChatMobileAuthRedirectURI") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            ?? "com.dawnchat.app://auth/callback"
    }

    var bridgeBaseURL: String {
        (Bundle.main.object(forInfoDictionaryKey: "DawnChatAuthBridgeBaseURL") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            ?? "https://dawnchat.com/desktop-auth/bridge"
    }

    var supabaseURL: String {
        (Bundle.main.object(forInfoDictionaryKey: "DawnChatSupabaseURL") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    var supabaseAnonKey: String {
        (Bundle.main.object(forInfoDictionaryKey: "DawnChatSupabaseAnonKey") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    var isConfigReady: Bool {
        !supabaseURL.isEmpty && !supabaseAnonKey.isEmpty
    }

    /// Creates the Supabase client, migrates legacy Keychain tokens once, then starts auto-refresh.
    func bootstrapSupabaseIfNeeded() async {
        _ = DawnChatReachability.shared
        guard supabaseClient == nil else { return }
        guard isConfigReady, let url = URL(string: supabaseURL) else { return }
        supabaseClient = SupabaseClient(supabaseURL: url, supabaseKey: supabaseAnonKey)
        await importLegacyKeychainIfNeeded()
    }

    func startSupabaseAutoRefresh() async {
        await supabaseClient?.auth.startAutoRefresh()
    }

    func stopSupabaseAutoRefresh() async {
        await supabaseClient?.auth.stopAutoRefresh()
    }

    private func importLegacyKeychainIfNeeded() async {
        guard let client = supabaseClient else { return }
        if (try? await client.auth.session) != nil {
            Self.clearLegacyKeychainTokens()
            return
        }
        guard let access = KeychainHelper.load(key: KeychainKeys.access)?.trimmingCharacters(in: .whitespacesAndNewlines),
              let refresh = KeychainHelper.load(key: KeychainKeys.refresh)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !access.isEmpty, !refresh.isEmpty else { return }
        do {
            try await client.auth.setSession(accessToken: access, refreshToken: refresh)
            Self.clearLegacyKeychainTokens()
        } catch {
        }
    }

    func getOrCreateDeviceId() -> String {
        if let existing = defaults.string(forKey: deviceKey), !existing.isEmpty {
            return existing
        }
        let id = UUID().uuidString
        defaults.set(id, forKey: deviceKey)
        return id
    }

    func isLoggedIn() -> Bool {
        supabaseClient?.auth.currentSession != nil
    }

    /// Maps current Supabase Auth user to a stable snapshot for Mine / profile screens.
    func loadProfileForUi() async -> UserProfileSnapshot? {
        guard let client = supabaseClient, isConfigReady else { return nil }
        do {
            let session = try await client.auth.session
            return mapSupabaseUserToProfile(session.user)
        } catch {
            do {
                let u = try await client.auth.user()
                return mapSupabaseUserToProfile(u)
            } catch {
                return nil
            }
        }
    }

    /// Bearer token for Supabase Edge Functions (e.g. dawn-tts). Caller must not expose to WebView.
    func dawnTtsAccessToken() async throws -> String {
        guard let client = supabaseClient, isConfigReady else {
            throw NSError(
                domain: "DawnTts",
                code: -1,
                userInfo: [
                    "dawnCode": "supabase_config_missing",
                    NSLocalizedDescriptionKey: "Supabase URL or anon key is not configured",
                ]
            )
        }
        let session = try await client.auth.session
        let token = session.accessToken.trimmingCharacters(in: .whitespacesAndNewlines)
        if token.isEmpty {
            throw NSError(
                domain: "DawnTts",
                code: -2,
                userInfo: [
                    "dawnCode": "not_authenticated",
                    NSLocalizedDescriptionKey: "Not signed in or session has no access token",
                ]
            )
        }
        return token
    }

    /// After storage restore, optionally validates with Auth server when online.
    func awaitSessionVerifiedForLaunch() async -> Bool {
        guard let client = supabaseClient, isConfigReady else { return false }
        do {
            _ = try await client.auth.session
        } catch {
            return false
        }
        if !DawnChatReachability.shared.isConnected {
            return true
        }
        do {
            _ = try await client.auth.user()
            return true
        } catch {
            try? await client.auth.signOut()
            Self.clearLegacyKeychainTokens()
            return false
        }
    }

    func clearSession() async {
        if let client = supabaseClient {
            try? await client.auth.signOut()
        }
        Self.clearLegacyKeychainTokens()
    }

    private static func clearLegacyKeychainTokens() {
        KeychainHelper.delete(key: KeychainKeys.access)
        KeychainHelper.delete(key: KeychainKeys.refresh)
        KeychainHelper.delete(key: KeychainKeys.expiresAt)
    }

    func writePending(_ pending: PendingAuthState) {
        if let data = try? JSONEncoder().encode(pending) {
            defaults.set(String(data: data, encoding: .utf8), forKey: pendingKey)
        }
    }

    func readPending() -> PendingAuthState? {
        guard let raw = defaults.string(forKey: pendingKey),
              let data = raw.data(using: .utf8),
              let p = try? JSONDecoder().decode(PendingAuthState.self, from: data) else { return nil }
        return p
    }

    func clearPending() {
        defaults.removeObject(forKey: pendingKey)
    }

    func pendingValid() -> PendingAuthState? {
        guard let p = readPending() else { return nil }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        if now - p.createdAt > DesktopAuthBridgeConstants.pendingTtlMs {
            clearPending()
            return nil
        }
        return p
    }

    func prepareBridgeLogin(nextPath: String = DesktopAuthBridgeConstants.defaultNext) throws -> URL {
        let state = MobileAuthBridge.generateState()
        let deviceId = getOrCreateDeviceId()
        writePending(PendingAuthState(state: state, deviceId: deviceId, createdAt: Int64(Date().timeIntervalSince1970 * 1000), nextPath: nextPath))
        return try MobileAuthBridge.buildBridgeURL(
            baseURL: bridgeBaseURL,
            state: state,
            deviceId: deviceId,
            redirectUri: redirectURI,
            nextPath: nextPath,
            provider: nil
        )
    }

    func matchesRedirect(_ url: URL) -> Bool {
        MobileAuthBridge.matchesRedirect(url, expectedRedirect: redirectURI)
    }

    func completeAuth(fromCallback url: URL) async throws {
        guard matchesRedirect(url) else {
            throw NSError(domain: "MobileAuth", code: 10, userInfo: [NSLocalizedDescriptionKey: "not_auth_callback"])
        }
        let parsed = MobileAuthBridge.parseCallback(url)
        if let err = parsed.error, !err.isEmpty {
            clearPending()
            throw NSError(domain: "MobileAuth", code: 11, userInfo: [NSLocalizedDescriptionKey: err])
        }
        guard let ticket = parsed.ticket?.trimmingCharacters(in: .whitespacesAndNewlines), !ticket.isEmpty,
              let state = parsed.state?.trimmingCharacters(in: .whitespacesAndNewlines), !state.isEmpty else {
            throw NSError(domain: "MobileAuth", code: 12, userInfo: [NSLocalizedDescriptionKey: "登录回调缺少 ticket 或 state"])
        }
        try await exchangeTicket(ticket: ticket, state: state)
    }

    private func exchangeTicket(ticket: String, state: String) async throws {
        guard let pending = pendingValid() else {
            throw NSError(domain: "MobileAuth", code: 13, userInfo: [NSLocalizedDescriptionKey: "登录状态已失效，请重新发起登录"])
        }
        if pending.state != state {
            clearPending()
            throw NSError(domain: "MobileAuth", code: 14, userInfo: [NSLocalizedDescriptionKey: "登录状态校验失败，请重新登录"])
        }
        guard isConfigReady else {
            throw NSError(domain: "MobileAuth", code: 15, userInfo: [NSLocalizedDescriptionKey: "请在 Info.plist 填写 DawnChatSupabaseURL 与 DawnChatSupabaseAnonKey"])
        }
        guard let client = supabaseClient else {
            throw NSError(domain: "MobileAuth", code: 19, userInfo: [NSLocalizedDescriptionKey: "Supabase 客户端未初始化"])
        }
        let urlStr = supabaseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/functions/v1/exchange-desktop-ticket"
        guard let reqUrl = URL(string: urlStr) else { throw NSError(domain: "MobileAuth", code: 16) }
        var req = URLRequest(url: reqUrl)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(supabaseAnonKey, forHTTPHeaderField: "apikey")
        let body: [String: Any] = [
            "desktop_ticket": ticket,
            "state": state,
            "device_id": pending.deviceId,
            "protocol_version": DesktopAuthBridgeConstants.protocolVersion,
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw NSError(domain: "MobileAuth", code: 17) }
        guard (200 ... 299).contains(http.statusCode) else {
            let text = String(data: data, encoding: .utf8) ?? ""
            let msg = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["message"] as? String ?? text
            throw NSError(domain: "MobileAuth", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: msg.isEmpty ? "ticket 兑换失败" : msg])
        }
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let access = (json?["access_token"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let refresh = (json?["refresh_token"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if access.isEmpty || refresh.isEmpty {
            throw NSError(domain: "MobileAuth", code: 18, userInfo: [NSLocalizedDescriptionKey: "ticket 兑换结果缺少会话 token"])
        }
        try await client.auth.setSession(accessToken: access, refreshToken: refresh)
        Self.clearLegacyKeychainTokens()
        clearPending()
    }
}

private enum KeychainKeys {
    static let access = "dawnchat.supabase.access"
    static let refresh = "dawnchat.supabase.refresh"
    static let expiresAt = "dawnchat.supabase.expires_at"
}

private enum KeychainHelper {
    private static let service = "com.dawnchat.app.mobileauth"

    static func load(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &out)
        guard status == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }

    static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
