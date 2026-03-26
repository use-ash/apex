import Foundation

enum TimelineItem: Identifiable {
    case message(Message)
    case alert(Alert)

    var id: String {
        switch self {
        case .message(let m): return "msg-\(m.id)"
        case .alert(let a): return "alert-\(a.id)"
        }
    }

    var createdAt: String {
        switch self {
        case .message(let m): return m.createdAt
        case .alert(let a): return a.createdAt
        }
    }
}
