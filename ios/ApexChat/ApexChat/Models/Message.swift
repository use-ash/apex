import Foundation

struct Message: Identifiable, Codable, Equatable {
    let id: String
    let role: String
    let content: String
    let toolEvents: String
    let thinking: String
    let costUsd: Double
    let tokensIn: Int
    let tokensOut: Int
    let createdAt: String
    var speakerId: String? = nil
    var speakerName: String? = nil
    var speakerAvatar: String? = nil
    var visibility: String? = nil
    var groupTurnId: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, role, content, thinking, visibility
        case toolEvents = "tool_events"
        case costUsd = "cost_usd"
        case tokensIn = "tokens_in"
        case tokensOut = "tokens_out"
        case createdAt = "created_at"
        case speakerId = "speaker_id"
        case speakerName = "speaker_name"
        case speakerAvatar = "speaker_avatar"
        case groupTurnId = "group_turn_id"
    }

    var isUser: Bool { role == "user" }
    var isAssistant: Bool { role == "assistant" }
    var hasSpeaker: Bool { speakerName != nil && !(speakerName?.isEmpty ?? true) }
    var searchableText: String {
        [content, thinking, toolEvents]
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
    }
}
