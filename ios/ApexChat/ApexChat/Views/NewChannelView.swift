import SwiftUI

struct NewChannelView: View {
    @Bindable var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var selectedProfile: AgentProfile?
    @State private var isLoadingProfiles = true
    @State private var groupsEnabled = false
    @State private var showingNewGroup = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button {
                        Task {
                            await appState.createThread()
                            dismiss()
                        }
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "bolt.fill")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                                .frame(width: 36, alignment: .center)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Quick Thread")
                                    .font(.body.weight(.semibold))
                                    .foregroundStyle(.primary)
                                Text("Lightweight one-off interaction")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                if groupsEnabled {
                    Section {
                        Button {
                            showingNewGroup = true
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "person.3.fill")
                                    .font(.title2)
                                    .foregroundStyle(.purple)
                                    .frame(width: 36, alignment: .center)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("New Group")
                                        .font(.body.weight(.semibold))
                                        .foregroundStyle(.primary)
                                    Text("Multi-agent collaboration")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }

                if !appState.profiles.isEmpty {
                    Section("Agent Profiles") {
                        ForEach(appState.profiles) { profile in
                            Button {
                                createWithProfile(profile)
                            } label: {
                                HStack(spacing: 12) {
                                    Text(profile.avatar.isEmpty ? "\u{1F4AC}" : profile.avatar)
                                        .font(.title2)
                                        .frame(width: 36, alignment: .center)

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(profile.name)
                                            .font(.body.weight(.semibold))
                                            .foregroundStyle(.primary)
                                        if !profile.roleDescription.isEmpty {
                                            Text(profile.roleDescription)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .lineLimit(2)
                                        }
                                    }

                                    Spacer()

                                    if !profile.model.isEmpty {
                                        Text(profile.modelDisplayName)
                                            .font(.caption2)
                                            .foregroundStyle(.blue)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(.blue.opacity(0.1))
                                            .clipShape(Capsule())
                                    }
                                }
                            }
                        }
                    }
                }

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

                Section("Alerts") {
                    alertChannelButton(label: "All Alerts", icon: "bell.fill", category: nil)
                    alertChannelButton(label: "Trading Alerts", icon: "chart.xyaxis.line", category: "trading")
                    alertChannelButton(label: "System Alerts", icon: "lock.shield.fill", category: "system")
                }
            }
            .navigationTitle("New Channel")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .task {
                await appState.loadProfiles()
                isLoadingProfiles = false
                if let features = try? await appState.apiClient.fetchFeatures() {
                    groupsEnabled = features["groups_enabled"] ?? false
                }
            }
            .sheet(isPresented: $showingNewGroup) {
                NewGroupView(appState: appState)
            }
        }
    }

    private func createWithProfile(_ profile: AgentProfile) {
        Task {
            await appState.createChannelWithProfile(profile.id)
            dismiss()
        }
    }

    private func createAndDismiss(model: String) {
        Task {
            await appState.createChannel(name: "New Channel", model: model)
            dismiss()
        }
    }

    private func alertChannelButton(label: String, icon: String, category: String?) -> some View {
        Button {
            Task {
                await appState.createAlertsChannel(category: category)
                dismiss()
            }
        } label: {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(.orange)
                Text(label)
                    .foregroundStyle(.primary)
            }
        }
    }
}
