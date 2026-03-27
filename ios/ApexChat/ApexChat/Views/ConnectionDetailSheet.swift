import SwiftUI

struct ConnectionDetailSheet: View {
    let statusText: String
    let isConnected: Bool
    let modelDisplayName: String
    let modelDescription: String
    let serverURL: String
    let openSettings: () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                detailRow(
                    title: "Status",
                    value: statusText,
                    tint: isConnected ? .green : .red
                )

                detailRow(
                    title: "Model",
                    value: modelDescription == "Unknown"
                        ? modelDisplayName
                        : "\(modelDisplayName) (\(modelDescription))"
                )

                detailRow(
                    title: "Server URL",
                    value: serverURL
                )

                Button {
                    openSettings()
                } label: {
                    Text("Open Settings")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                }
                .buttonStyle(.borderedProminent)

                Spacer()
            }
            .padding(20)
            .navigationTitle("Connection")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func detailRow(
        title: String,
        value: String,
        tint: Color? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                if let tint {
                    Circle()
                        .fill(tint)
                        .frame(width: 8, height: 8)
                }

                Text(value)
                    .font(.body)
                    .textSelection(.enabled)
            }
        }
    }
}
