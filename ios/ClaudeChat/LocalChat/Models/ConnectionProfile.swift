import Foundation

struct ConnectionProfile: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var serverURL: String

    init(id: String = UUID().uuidString, name: String, serverURL: String) {
        self.id = id
        self.name = name
        self.serverURL = serverURL
    }

    static let defaultProfiles: [ConnectionProfile] = [
        ConnectionProfile(id: "vpn", name: "VPN", serverURL: "https://10.8.0.2:8300"),
        ConnectionProfile(id: "wifi", name: "WiFi", serverURL: "https://192.168.86.214:8300"),
    ]

    // MARK: - Persistence

    private static let storageKey = "connection_profiles"
    private static let activeProfileKey = "active_profile_id"

    static func loadAll() -> [ConnectionProfile] {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let profiles = try? JSONDecoder().decode([ConnectionProfile].self, from: data),
              !profiles.isEmpty else {
            return defaultProfiles
        }
        return profiles
    }

    static func saveAll(_ profiles: [ConnectionProfile]) {
        if let data = try? JSONEncoder().encode(profiles) {
            UserDefaults.standard.set(data, forKey: storageKey)
        }
    }

    static var activeProfileId: String? {
        get { UserDefaults.standard.string(forKey: activeProfileKey) }
        set { UserDefaults.standard.set(newValue, forKey: activeProfileKey) }
    }
}
