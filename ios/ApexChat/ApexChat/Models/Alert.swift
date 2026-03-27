import Foundation
import SwiftUI

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

// MARK: - Shared Display Helpers

extension Alert {
    var severityColor: Color {
        switch severity {
        case "critical": return .red
        case "warning": return .orange
        default: return .blue
        }
    }

    var severityIcon: String {
        switch severity {
        case "critical": return "exclamationmark.triangle.fill"
        case "warning": return "exclamationmark.circle.fill"
        default: return "info.circle.fill"
        }
    }

    var sourceLabel: String {
        switch source {
        case "plan_h": return "Plan H"
        case "plan_c": return "Plan C"
        case "plan_h_backstop": return "Backstop"
        case "plan_m": return "Plan M"
        case "plan_alpha": return "Plan Alpha"
        case "regime": return "Regime"
        case "guardrail": return "Guardrail"
        case "watchdog": return "Watchdog"
        case "system": return "System"
        case "test": return "Test"
        default: return source.replacingOccurrences(of: "_", with: " ")
        }
    }

    var sourceIcon: String {
        switch source {
        case "plan_h": return "chart.xyaxis.line"
        case "plan_c": return "chart.bar.xaxis"
        case "plan_h_backstop": return "shield.fill"
        case "plan_m": return "chart.line.uptrend.xyaxis"
        case "plan_alpha": return "bolt.fill"
        case "regime": return "gauge.medium"
        case "guardrail": return "lock.shield.fill"
        case "watchdog": return "eye.fill"
        case "system": return "gearshape.fill"
        case "test": return "testtube.2"
        default: return severityIcon
        }
    }

    var isGuardrail: Bool { source.lowercased() == "guardrail" }
}
