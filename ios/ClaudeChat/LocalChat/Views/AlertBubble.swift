import SwiftUI

struct AlertBubble: View {
    let alert: Alert
    var onAck: (() -> Void)?
    var onAllow: (() -> Void)?
    var onTap: (() -> Void)? = nil

    // MARK: - Severity

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

    // MARK: - Source mapping

    private var sourceLabel: String {
        switch alert.source {
        case "plan_h": return "Plan H"
        case "plan_c": return "Plan C"
        case "plan_h_backstop": return "Backstop"
        case "regime": return "Regime"
        case "guardrail": return "Guardrail"
        case "test": return "Test"
        default: return alert.source
        }
    }

    private var sourceIcon: String {
        switch alert.source {
        case "plan_h": return "chart.xyaxis.line"
        case "plan_c": return "chart.bar.xaxis"
        case "plan_h_backstop": return "shield.fill"
        case "regime": return "gauge.medium"
        case "guardrail": return "lock.shield.fill"
        case "test": return "testtube.2"
        default: return severityIcon
        }
    }

    private var isGuardrail: Bool { alert.source == "guardrail" }

    // MARK: - Timestamp

    private static let iso8601Frac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let iso8601: ISO8601DateFormatter = ISO8601DateFormatter()

    private static let absoluteFmt: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM d, HH:mm"
        return f
    }()

    private var relativeTimestamp: String {
        guard let date = Self.iso8601Frac.date(from: alert.createdAt)
                ?? Self.iso8601.date(from: alert.createdAt) else { return "" }
        let seconds = Date().timeIntervalSince(date)
        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(Int(seconds / 60))m ago" }
        if seconds < 86400 { return "\(Int(seconds / 3600))h ago" }
        return Self.absoluteFmt.string(from: date)
    }

    // MARK: - Body

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: severityIcon)
                .foregroundStyle(severityColor)
                .font(.title3)
            VStack(alignment: .leading, spacing: 4) {
                // Row 1: source + timestamp + actions
                HStack(spacing: 6) {
                    Image(systemName: sourceIcon)
                        .font(.caption2)
                        .foregroundStyle(severityColor)
                    Text(sourceLabel.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(severityColor)
                    Spacer()
                    Text(relativeTimestamp)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if alert.acked {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption2)
                            .foregroundStyle(.green)
                    }
                    if !alert.acked {
                        if isGuardrail {
                            Button("Allow") { onAllow?() }
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(.green)
                                .clipShape(Capsule())
                        }
                        Button("Ack") { onAck?() }
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(severityColor)
                            .clipShape(Capsule())
                    }
                }
                // Row 2: title
                Text(alert.title)
                    .font(.subheadline.weight(.semibold))
                // Row 3: body
                if !alert.body.isEmpty {
                    Text(alert.body)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                // Row 4: metadata chips
                if let metadata = alert.metadata, !metadata.isEmpty {
                    metadataChips(metadata)
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
        .contentShape(RoundedRectangle(cornerRadius: 12))
        .onTapGesture {
            onTap?()
        }
    }

    // MARK: - Metadata

    @ViewBuilder
    private func metadataChips(_ metadata: [String: String]) -> some View {
        let pairs = metadata.sorted { $0.key < $1.key }
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 6)], alignment: .leading, spacing: 4) {
            ForEach(pairs, id: \.key) { key, value in
                HStack(spacing: 3) {
                    Text(key.capitalized)
                        .font(.system(.caption2))
                        .foregroundStyle(.tertiary)
                    Text(value)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color(.tertiarySystemFill))
                .clipShape(Capsule())
            }
        }
    }
}
