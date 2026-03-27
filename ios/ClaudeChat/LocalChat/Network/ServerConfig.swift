import Foundation

/// Single source of truth for the server URL.
/// Both APIClient and ConnectionManager read from here.
enum ServerConfig {
    static let defaultBaseURL = "https://10.8.0.2:8300"
    private static let userDefaultsKey = "server_url"

    static var currentBaseURL: String {
        normalizedBaseURL(UserDefaults.standard.string(forKey: userDefaultsKey) ?? defaultBaseURL)
    }

    static func setBaseURL(_ value: String) {
        UserDefaults.standard.set(normalizedBaseURL(value), forKey: userDefaultsKey)
    }

    private static func normalizedBaseURL(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return defaultBaseURL }
        return trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
    }
}
