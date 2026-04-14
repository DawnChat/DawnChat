import Capacitor
import Foundation

/// POST dawn-tts with Supabase session; writes MP3 to caches and returns path. Token stays native.
@objc(DawnTtsPlugin)
public class DawnTtsPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "DawnTtsPlugin"
    public let jsName = "DawnTts"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "synthesizeToFile", returnType: CAPPluginReturnPromise),
    ]

    @objc func synthesizeToFile(_ call: CAPPluginCall) {
        guard let text = call.getString("text")?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            call.reject("Field text is required", "text_required")
            return
        }

        Task {
            do {
                let token = try await MobileAuthRepository.shared.dawnTtsAccessToken()
                let bundleUrl = (Bundle.main.object(forInfoDictionaryKey: "DawnChatSupabaseURL") as? String)?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let anon = (Bundle.main.object(forInfoDictionaryKey: "DawnChatSupabaseAnonKey") as? String)?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let base = bundleUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                if base.isEmpty || anon.isEmpty {
                    await MainActor.run {
                        call.reject("Supabase URL or anon key is not configured", "supabase_config_missing")
                    }
                    return
                }
                guard let url = URL(string: base + "/functions/v1/dawn-tts") else {
                    await MainActor.run { call.reject("Invalid Supabase URL", "invalid_url") }
                    return
                }

                var body: [String: Any] = ["text": text]
                if let v = call.getString("voice")?.trimmingCharacters(in: .whitespacesAndNewlines), !v.isEmpty {
                    body["voice"] = v
                }
                if let r = call.getString("rate")?.trimmingCharacters(in: .whitespacesAndNewlines), !r.isEmpty {
                    body["rate"] = r
                }
                if let v = call.getString("volume")?.trimmingCharacters(in: .whitespacesAndNewlines), !v.isEmpty {
                    body["volume"] = v
                }
                if let p = call.getString("pitch")?.trimmingCharacters(in: .whitespacesAndNewlines), !p.isEmpty {
                    body["pitch"] = p
                }
                let jsonData = try JSONSerialization.data(withJSONObject: body)

                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                req.setValue(anon, forHTTPHeaderField: "apikey")
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.setValue("audio/mpeg", forHTTPHeaderField: "Accept")
                req.httpBody = jsonData
                req.timeoutInterval = 90

                let (data, response) = try await URLSession.shared.data(for: req)
                guard let http = response as? HTTPURLResponse else {
                    await MainActor.run { call.reject("Invalid response", "dawn_tts_request_failed") }
                    return
                }
                if !(200 ... 299).contains(http.statusCode) {
                    let (code, message) = Self.parseErrorPayload(data: data, status: http.statusCode)
                    await MainActor.run { call.reject(message, code) }
                    return
                }
                let ct = http.value(forHTTPHeaderField: "Content-Type")?.lowercased() ?? ""
                if ct.contains("application/json") {
                    await MainActor.run {
                        call.reject("Unexpected JSON response; ensure Accept is audio/mpeg", "unexpected_json")
                    }
                    return
                }

                let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)
                guard let cacheRoot = caches.first else {
                    await MainActor.run { call.reject("No cache directory", "cache_unavailable") }
                    return
                }
                let dir = cacheRoot.appendingPathComponent("dawn-tts", isDirectory: true)
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                let out = dir.appendingPathComponent(UUID().uuidString + ".mp3")
                try data.write(to: out)
                await MainActor.run { call.resolve(["path": out.path]) }
            } catch {
                let ns = error as NSError
                if ns.domain == "DawnTts", let dawnCode = ns.userInfo["dawnCode"] as? String {
                    await MainActor.run { call.reject(ns.localizedDescription, dawnCode) }
                } else {
                    await MainActor.run {
                        call.reject(error.localizedDescription, "dawn_tts_request_failed", error)
                    }
                }
            }
        }
    }

    private static func parseErrorPayload(data: Data, status: Int) -> (String, String) {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return ("dawn_tts_http_\(status)", HTTPURLResponse.localizedString(forStatusCode: status))
        }
        let code = (obj["code"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let message = (obj["message"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let c = (code?.isEmpty == false) ? code! : "dawn_tts_http_\(status)"
        let m = (message?.isEmpty == false) ? message! : HTTPURLResponse.localizedString(forStatusCode: status)
        return (c, m)
    }
}
