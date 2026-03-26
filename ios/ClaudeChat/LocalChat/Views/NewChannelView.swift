import SwiftUI

struct NewChannelView: View {
    @Bindable var appState: AppState
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Claude") {
                    ForEach(AppState.supportedModels.filter { $0.id.hasPrefix("claude-") }) { model in
                        Button {
                            createAndDismiss(model: model.id)
                        } label: {
                            Text(model.displayName)
                                .foregroundStyle(.primary)
                        }
                    }
                }

                Section("Grok") {
                    ForEach(AppState.supportedModels.filter { $0.id.hasPrefix("grok-") }) { model in
                        Button {
                            createAndDismiss(model: model.id)
                        } label: {
                            Text(model.displayName)
                                .foregroundStyle(.primary)
                        }
                    }
                }

                if !appState.localModels.isEmpty {
                    Section("Local (Ollama)") {
                        ForEach(appState.localModels) { model in
                            Button {
                                createAndDismiss(model: model.id)
                            } label: {
                                HStack {
                                    Text(model.displayName)
                                        .foregroundStyle(.primary)
                                    Spacer()
                                    Text("\(model.sizeGb, specifier: "%.0f")GB")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }

                Section("Special") {
                    Button {
                        Task {
                            await appState.createAlertsChannel()
                            dismiss()
                        }
                    } label: {
                        HStack {
                            Image(systemName: "bell.fill")
                                .foregroundStyle(.orange)
                            Text("Alerts Channel")
                                .foregroundStyle(.primary)
                        }
                    }
                }
            }
            .navigationTitle("New Channel")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func createAndDismiss(model: String) {
        Task {
            await appState.createChannel(name: "New Chat", model: model)
            dismiss()
        }
    }
}
