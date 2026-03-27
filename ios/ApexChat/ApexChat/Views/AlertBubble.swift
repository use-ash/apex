import SwiftUI

struct AlertBubble: View {
    let alert: Alert
    var onAck: (() -> Void)?
    var onAllow: (() -> Void)?
    var onTap: (() -> Void)? = nil

    @State private var buttonTapped = false

    // Severity + source helpers are now on Alert model

    private var relativeTimestamp: String {
        DateParsing.relativeTimeAgo(alert.createdAt)
    }

    // MARK: - Body

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: alert.severityIcon)
                .foregroundStyle(alert.severityColor)
                .font(.title3)
            VStack(alignment: .leading, spacing: 4) {
                // Row 1: source + timestamp + actions
                HStack(spacing: 6) {
                    Image(systemName: alert.sourceIcon)
                        .font(.caption2)
                        .foregroundStyle(alert.severityColor)
                    Text(alert.sourceLabel.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(alert.severityColor)
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
                        if alert.isGuardrail {
                            Button(action: { buttonTapped = true; onAllow?() }) {
                                Text("Allow")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(.green)
                                    .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)
                        }
                        Button(action: { buttonTapped = true; onAck?() }) {
                            Text("Ack")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(alert.severityColor)
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
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
        .background {
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.systemBackground))
            RoundedRectangle(cornerRadius: 12)
                .fill(alert.severityColor.opacity(alert.acked ? 0.05 : 0.12))
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(alert.severityColor.opacity(0.3), lineWidth: 1)
        )
        .opacity(alert.acked ? 0.6 : 1.0)
        .padding(.horizontal, 12)
        .contentShape(RoundedRectangle(cornerRadius: 12))
        .onTapGesture {
            if buttonTapped {
                buttonTapped = false
            } else {
                onTap?()
            }
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
