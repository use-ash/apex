import SwiftUI
import UIKit

struct AlertDetailView: View {
    let alert: Alert
    @Bindable var appState: AppState

    @Environment(\.dismiss) private var dismiss

    private var displayAlert: Alert {
        appState.alerts.first(where: { $0.id == alert.id }) ?? alert
    }

    // displayAlert.severityColor, displayAlert.sourceLabel, displayAlert.isGuardrail now on Alert model

    private var severityEmoji: String {
        switch displayAlert.severity {
        case "critical": return "🔴"
        case "warning": return "🟡"
        default: return "🔵"
        }
    }

    private var relativeTimestamp: String {
        guard let date = DateParsing.parseISO8601(displayAlert.createdAt) else {
            return displayAlert.createdAt
        }
        return Self.relativeDateTimeFormatter.localizedString(for: date, relativeTo: Date())
    }

    private var sortedMetadata: [(key: String, value: String)] {
        (displayAlert.metadata ?? [:]).sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    headerCard
                    titleCard
                    bodyCard
                    if !sortedMetadata.isEmpty {
                        metadataCard
                    }
                }
                .padding(16)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("🚨 Alert")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .accessibilityLabel("Close alert details")
                }
            }
            .safeAreaInset(edge: .bottom) {
                actionBar
            }
        }
    }

    private var headerCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Text(severityEmoji)
                    .font(.system(size: 34))
                    .frame(width: 52, height: 52)
                    .background(displayAlert.severityColor.opacity(0.16))
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                VStack(alignment: .leading, spacing: 8) {
                    Text(displayAlert.sourceLabel.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(displayAlert.severityColor)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(displayAlert.severityColor.opacity(0.12))
                        .clipShape(Capsule())

                    HStack(spacing: 6) {
                        Text("🕒")
                        Text(relativeTimestamp)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if displayAlert.acked {
                        HStack(spacing: 6) {
                            Text("✅")
                            Text("Acknowledged")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.green)
                        }
                    }
                }

                Spacer(minLength: 0)
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var titleCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("📌 Title")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)

            Text(displayAlert.title)
                .font(.headline.weight(.semibold))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var bodyCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("📝 Details")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)

            Text(displayAlert.body.isEmpty ? "No body text." : displayAlert.body)
                .font(.system(.body, design: .monospaced))
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var metadataCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("🏷️ Metadata")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 12) {
                ForEach(sortedMetadata, id: \.key) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.key.capitalized)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Text(item.value)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.primary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                    }

                    if item.key != sortedMetadata.last?.key {
                        Divider()
                    }
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var actionBar: some View {
        VStack(spacing: 0) {
            Divider()

            HStack(spacing: 10) {
                Button {
                    Task { await appState.ackAlert(displayAlert.id) }
                } label: {
                    Text("✅ Acknowledge")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(displayAlert.severityColor)
                .disabled(displayAlert.acked)

                if displayAlert.isGuardrail {
                    Button {
                        Task { await appState.allowAlert(displayAlert.id) }
                    } label: {
                        Text("🟢 Allow")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.green)
                    .disabled(displayAlert.acked)
                }

                Button {
                    UIPasteboard.general.secureCopy(displayAlert.body)
                } label: {
                    Text("📋 Copy")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 16)
            .background(Color(.systemGroupedBackground))
        }
    }

    private static let relativeDateTimeFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter
    }()
}
