import Foundation

struct Chat: Identifiable, Codable, Comparable {
    let id: String
    var title: String
    let claudeSessionId: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, title
        case claudeSessionId = "claude_session_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    static func < (lhs: Chat, rhs: Chat) -> Bool {
        lhs.updatedAt > rhs.updatedAt  // Most recent first
    }
}
