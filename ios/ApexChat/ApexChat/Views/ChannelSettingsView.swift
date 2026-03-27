import SwiftUI

struct ChannelSettingsView: View {
    @Environment(\.dismiss) private var dismiss

    @Bindable var appState: AppState
    let chatId: String

    @State private var selectedProfileId: String
    @State private var selectedModelId: String
    @State private var isUpdatingProfile: Bool = false
    @State private var isShowingConnectionDetails: Bool = false
    @State private var isShowingSettings: Bool = false
    @State private var openSettingsAfterConnectionSheet: Bool = false

    init(appState: AppState, chatId: String) {
        self.appState = appState
        self.chatId = chatId
        _selectedProfileId = State(initialValue: appState.currentChat?.profileId ?? "")
        _selectedModelId = State(initialValue: appState.currentChat?.model ?? appState.selectedModel)
    }

    var body: some View {
        NavigationStack {
            Form {
                if isEditableChat {
                    personaSection
                    modelSection
                    connectionSection
                } else {
                    Section {
                        Text("Channel settings are only available for regular chat channels.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Channel Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
        .task {
            if appState.profiles.isEmpty {
                await appState.loadProfiles()
            }
            if appState.localModels.isEmpty {
                await appState.loadLocalModels()
            }
            syncSelectionsFromChat()
        }
        .onChange(of: selectedProfileId) { oldValue, newValue in
            guard oldValue != newValue else { return }
            handleProfileSelectionChange(newValue)
        }
        .onChange(of: selectedModelId) { oldValue, newValue in
            guard oldValue != newValue else { return }
            handleModelSelectionChange(newValue)
        }
        .sheet(
            isPresented: $isShowingConnectionDetails,
            onDismiss: handleConnectionSheetDismiss
        ) {
            ConnectionDetailSheet(
                statusText: appState.connectionStatusText,
                isConnected: appState.connectionManager.isConnected,
                modelDisplayName: appState.modelDisplayName,
                modelDescription: appState.modelDescription,
                serverURL: appState.serverURL
            ) {
                openSettingsAfterConnectionSheet = true
                isShowingConnectionDetails = false
            }
            .presentationDetents([.medium])
        }
        .sheet(isPresented: $isShowingSettings) {
            SettingsView(appState: appState)
        }
    }

    private var currentChat: Chat? {
        if let current = appState.currentChat, current.id == chatId {
            return current
        }
        return appState.chats.first(where: { $0.id == chatId })
    }

    private var isEditableChat: Bool {
        let type = currentChat?.type ?? "chat"
        return type == "chat"
    }

    private var selectedProfile: AgentProfile? {
        let trimmedId = selectedProfileId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedId.isEmpty else { return nil }
        return appState.profiles.first(where: { $0.id == trimmedId })
    }

    private var isModelLocked: Bool {
        guard let selectedProfile else { return false }
        return !selectedProfile.model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var activeModelId: String {
        currentChat?.model ?? selectedModelId
    }

    private var personaSection: some View {
        Section("Persona") {
            Picker("Persona", selection: $selectedProfileId) {
                ProfileOptionLabel.noProfile
                    .tag("")

                ForEach(appState.profiles) { profile in
                    ProfileOptionLabel(profile: profile)
                        .tag(profile.id)
                }
            }
            .disabled(isUpdatingProfile)

            if isUpdatingProfile {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("Updating persona...")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            } else if let selectedProfile {
                Text(selectedProfile.roleDescription)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                Text("No persona attached.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var modelSection: some View {
        Section("Model") {
            if isModelLocked, let selectedProfile {
                HStack(spacing: 12) {
                    Image(systemName: "lock.fill")
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(AppState.friendlyModelName(selectedProfile.model))
                            .foregroundStyle(.primary)
                        Text("Locked by profile")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
            } else {
                Picker("Model", selection: $selectedModelId) {
                    ForEach(appState.allModels) { model in
                        Text(model.displayName)
                            .tag(model.id)
                    }
                }
                .disabled(isUpdatingProfile || appState.allModels.isEmpty)

                if selectedProfile != nil {
                    Text("This profile does not lock the model.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Changes apply to this channel only.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var connectionSection: some View {
        Section {
            Button {
                isShowingConnectionDetails = true
            } label: {
                Label("Connection Details", systemImage: "info.circle")
            }
        }
    }

    private func syncSelectionsFromChat() {
        selectedProfileId = currentChat?.profileId ?? ""
        selectedModelId = currentChat?.model ?? appState.selectedModel
    }

    private func handleProfileSelectionChange(_ newValue: String) {
        let normalizedCurrent = (currentChat?.profileId ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedSelection = newValue.trimmingCharacters(in: .whitespacesAndNewlines)

        guard normalizedCurrent != normalizedSelection else { return }
        guard !isUpdatingProfile else { return }

        isUpdatingProfile = true

        Task {
            await appState.updateChatProfile(chatId, profileId: normalizedSelection)
            await MainActor.run {
                isUpdatingProfile = false
                syncSelectionsFromChat()
                if (currentChat?.profileId ?? "") == normalizedSelection {
                    dismissAfterSelection()
                }
            }
        }
    }

    private func handleModelSelectionChange(_ newValue: String) {
        guard !isModelLocked else {
            syncSelectionsFromChat()
            return
        }

        let normalizedSelection = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
        let currentModel = activeModelId.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !normalizedSelection.isEmpty else { return }
        guard normalizedSelection != currentModel else { return }

        appState.updateSelectedModel(normalizedSelection)
        syncSelectionsFromChat()
        dismissAfterSelection()
    }

    private func dismissAfterSelection() {
        Task {
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            dismiss()
        }
    }

    private func handleConnectionSheetDismiss() {
        guard openSettingsAfterConnectionSheet else { return }
        openSettingsAfterConnectionSheet = false
        isShowingSettings = true
    }
}

private struct ProfileOptionLabel: View {
    let profile: AgentProfile?

    init(profile: AgentProfile) {
        self.profile = profile
    }

    private init(profile: AgentProfile?) {
        self.profile = profile
    }

    static var noProfile: some View {
        ProfileOptionLabel(profile: nil)
    }

    var body: some View {
        HStack(spacing: 10) {
            if let profile, !profile.avatar.isEmpty {
                Text(profile.avatar)
                    .font(.body)
                    .frame(width: 24, alignment: .center)
            } else {
                Image(systemName: "bubble.left")
                    .foregroundStyle(.secondary)
                    .frame(width: 24, alignment: .center)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(profile?.name ?? "No Profile")
                    .foregroundStyle(.primary)
                Text(profile?.roleDescription ?? "Use a custom model for this channel.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
    }
}
