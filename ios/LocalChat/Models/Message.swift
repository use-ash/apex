import Foundation

struct Message: Identifiable, Codable {
    let id: String
    let role: String
    let content: String
    let toolEvents: String
    let thinking: String
    let costUsd: Double
    let tokensIn: Int
    let tokensOut: Int
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, role, content, thinking
        case toolEvents = "tool_events"
        case costUsd = "cost_usd"
        case tokensIn = "tokens_in"
        case tokensOut = "tokens_out"
        case createdAt = "created_at"
    }

    var isUser: Bool { role == "user" }
    var isAssistant: Bool { role == "assistant" }
}
