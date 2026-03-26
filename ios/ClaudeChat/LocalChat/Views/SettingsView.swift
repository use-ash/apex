import SwiftUI
import UniformTypeIdentifiers

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss

    @Bindable var appState: AppState

    @State private var serverURL: String
    @State private var serverStatusMessage: String?
    @State private var certStatusMessage: String?
    @State private var certErrorMessage: String?
    @State private var selectedFileData: Data?
    @State private var selectedFileName: String?
    @State private var certificatePassword: String = ""
    @State private var selectedModel: String
    @State private var isShowingFilePicker: Bool = false
    @State private var isApplyingServerURL: Bool = false
    @AppStorage("chatFontScale") private var fontScale: Double = 1.0

    init(appState: AppState) {
        self.appState = appState
        _serverURL = State(initialValue: appState.serverURL)
        _selectedModel = State(initialValue: appState.selectedModel)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    ForEach(appState.connectionProfiles) { profile in
                        Button {
                            appState.switchProfile(profile)
                            serverURL = profile.serverURL
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(profile.name)
                                        .foregroundStyle(.primary)
                                    Text(profile.serverURL)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if appState.activeProfileId == profile.id {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.green)
                                }
                            }
                        }
                    }
                }

                Section("Custom URL") {
                    TextField("https://10.8.0.2:8300", text: $serverURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button {
                        applyServerURL()
                    } label: {
                        HStack {
                            if isApplyingServerURL {
                                ProgressView()
                            }
                            Text(isApplyingServerURL ? "Applying..." : "Save and Reconnect")
                        }
                    }
                    .disabled(isApplyingServerURL || serverURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    if let serverStatusMessage {
                        Text(serverStatusMessage)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Certificate") {
                    HStack {
                        Text("Status")
                        Spacer()
                        Text(appState.certificateManager.hasIdentity ? "Installed" : "Not Installed")
                            .foregroundStyle(appState.certificateManager.hasIdentity ? .green : .secondary)
                    }

                    Button(selectedFileName ?? "Select .p12 File") {
                        isShowingFilePicker = true
                    }
                    .fileImporter(
                        isPresented: $isShowingFilePicker,
                        allowedContentTypes: [UTType(filenameExtension: "p12") ?? .data],
                        allowsMultipleSelection: false,
                        onCompletion: handleFileSelection
                    )

                    SecureField("Certificate Password", text: $certificatePassword)
                        .textContentType(.password)

                    Button(appState.certificateManager.hasIdentity ? "Reimport Certificate" : "Import Certificate") {
                        importCertificate()
                    }
                    .disabled(selectedFileData == nil)

                    if appState.certificateManager.hasIdentity {
                        Button("Delete Certificate", role: .destructive) {
                            deleteCertificate()
                        }
                    }

                    if let certStatusMessage {
                        Text(certStatusMessage)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    if let certErrorMessage {
                        Text(certErrorMessage)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }

                Section("Model") {
                    Picker("Selected Model", selection: $selectedModel) {
                        ForEach(AppState.supportedModels) { model in
                            Text(model.displayName).tag(model.id)
                        }
                        if !appState.localModels.isEmpty {
                            Section("Local (Ollama)") {
                                ForEach(appState.localModels) { model in
                                    Text("\(model.displayName) (\(model.sizeGb, specifier: "%.0f")GB)")
                                        .tag(model.id)
                                }
                            }
                        }
                    }
                    .onChange(of: selectedModel) { _, newValue in
                        appState.updateSelectedModel(newValue)
                    }

                    LabeledContent("Active") {
                        Text(appState.modelDisplayName)
                    }

                    if appState.localModels.isEmpty {
                        Button("Refresh Local Models") {
                            Task { await appState.loadLocalModels() }
                        }
                    }

                    Text(appState.connectionManager.isConnected
                        ? "Changes apply immediately to the connected server."
                        : "Changes will be sent when the app reconnects.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Text Size") {
                    HStack {
                        Text("Font Scale")
                        Spacer()
                        Text("\(Int(fontScale * 100))%")
                            .foregroundStyle(.secondary)
                    }

                    Slider(value: $fontScale, in: 0.7...2.0, step: 0.1)

                    if fontScale != 1.0 {
                        Button("Reset to Default") {
                            fontScale = 1.0
                        }
                    }
                }

                Section("About") {
                    Text("LocalChat for iOS connects directly to your LocalChat server over HTTPS and WebSocket, and streams responses into a single persistent conversation.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }

    private func applyServerURL() {
        let trimmedURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedURL.isEmpty else { return }

        isApplyingServerURL = true
        serverStatusMessage = nil

        appState.updateServerURL(trimmedURL)

        Task {
            appState.disconnect()
            appState.connect()
            await appState.ensurePersistentChat()

            await MainActor.run {
                serverStatusMessage = "Saved. Reconnected to \(appState.serverURL)."
                isApplyingServerURL = false
            }
        }
    }

    private func importCertificate() {
        guard let selectedFileData else { return }

        do {
            try appState.certificateManager.importP12(data: selectedFileData, password: certificatePassword)
            certStatusMessage = "Certificate imported."
            certErrorMessage = nil
            certificatePassword = ""
        } catch {
            certErrorMessage = error.localizedDescription
            certStatusMessage = nil
        }
    }

    private func deleteCertificate() {
        appState.certificateManager.deleteAll()
        certStatusMessage = "Certificate removed."
        certErrorMessage = nil
        selectedFileData = nil
        selectedFileName = nil
        certificatePassword = ""
    }

    private func handleFileSelection(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            let accessing = url.startAccessingSecurityScopedResource()
            defer {
                if accessing {
                    url.stopAccessingSecurityScopedResource()
                }
            }

            do {
                selectedFileData = try Data(contentsOf: url)
                selectedFileName = url.lastPathComponent
                certErrorMessage = nil
            } catch {
                certErrorMessage = "Failed to read file: \(error.localizedDescription)"
            }
        case .failure(let error):
            certErrorMessage = error.localizedDescription
        }
    }
}
