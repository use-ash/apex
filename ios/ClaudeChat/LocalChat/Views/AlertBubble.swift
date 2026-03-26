import SwiftUI

struct AlertBubble: View {
    let alert: Alert
    var onAck: (() -> Void)?

    private var severityColor: Color {
        switch alert.severity {
        case "critical": return .red
        case "warning": return .orange
        default: return .blue
        }
    }

    private var severityIcon: String {
        switch alert.severity {
        case "critical": return "exclamationmark.triangle.fill"
        case "warning": return "exclamationmark.circle.fill"
        default: return "info.circle.fill"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: severityIcon)
                .foregroundStyle(severityColor)
                .font(.title3)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(alert.source.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(severityColor)
                    Spacer()
                    if !alert.acked {
                        Button("Ack") { onAck?() }
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(severityColor)
                            .clipShape(Capsule())
                    }
                }
                Text(alert.title)
                    .font(.subheadline.weight(.semibold))
                if !alert.body.isEmpty {
                    Text(alert.body)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(severityColor.opacity(alert.acked ? 0.05 : 0.12))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(severityColor.opacity(0.3), lineWidth: 1)
        )
        .opacity(alert.acked ? 0.6 : 1.0)
        .padding(.horizontal, 12)
    }
}
