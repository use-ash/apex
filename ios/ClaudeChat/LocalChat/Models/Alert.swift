import Foundation

struct Alert: Identifiable, Codable {
    let id: String
    let source: String
    let severity: String
    let title: String
    let body: String
    var acked: Bool
    let createdAt: String
    let metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case id, source, severity, title, body, acked, metadata
        case createdAt = "created_at"
    }
}
