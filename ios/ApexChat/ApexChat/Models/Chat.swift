import Foundation

struct Chat: Identifiable, Codable, Comparable {
    let id: String
    var title: String
    var model: String?
    var type: String?           // "chat", "thread", "group", or "alerts"
    var category: String?       // alert filter: "trading", "system", nil = all
    let claudeSessionId: String?
    let createdAt: String
    let updatedAt: String
    var profileId: String?
    var profileName: String?
    var profileAvatar: String?
    var memberCount: Int?
    var primaryProfileName: String?
    var primaryProfileAvatar: String?

    var isGroup: Bool { type == "group" }

    enum CodingKeys: String, CodingKey {
        case id, title, model, type, category
        case claudeSessionId = "claude_session_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case profileId = "profile_id"
        case profileName = "profile_name"
        case profileAvatar = "profile_avatar"
        case memberCount = "member_count"
        case primaryProfileName = "primary_profile_name"
        case primaryProfileAvatar = "primary_profile_avatar"
    }

    static func < (lhs: Chat, rhs: Chat) -> Bool {
        lhs.updatedAt > rhs.updatedAt  // Most recent first
    }
}
