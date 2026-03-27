import Foundation

struct AgentProfile: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let slug: String
    let avatar: String
    let roleDescription: String
    let backend: String
    let model: String
    let isDefault: Bool

    enum CodingKeys: String, CodingKey {
        case id, name, slug, avatar, backend, model
        case roleDescription = "role_description"
        case isDefault = "is_default"
    }

    /// Display-friendly model name
    var modelDisplayName: String {
        if model.isEmpty { return "Default" }
        let parts = model.split(separator: ":")
        return parts.last.map(String.init) ?? model
    }
}

struct ProfilesResponse: Decodable {
    let profiles: [AgentProfile]
}
