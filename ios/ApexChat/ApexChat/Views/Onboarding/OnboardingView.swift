import SwiftUI
import UniformTypeIdentifiers

struct OnboardingView: View {
    @Bindable var appState: AppState

    @State private var step: Int = 1
    @State private var password: String = ""
    @State private var serverURL: String = "https://10.8.0.2:8300"
    @State private var certImported: Bool = false
    @State private var certError: String?
    @State private var healthOK: Bool = false
    @State private var healthError: String?
    @State private var isTestingConnection: Bool = false
    @State private var showFilePicker: Bool = false
    @State private var selectedFileData: Data?
    @State private var selectedFileName: String?

    init(appState: AppState) {
        self.appState = appState
        let hasIdentity = appState.certificateManager.hasIdentity
        _step = State(initialValue: hasIdentity ? 2 : 1)
        _serverURL = State(initialValue: appState.apiClient.baseURL)
        _certImported = State(initialValue: hasIdentity)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Step indicator
                HStack {
                    stepDot(1)
                    Rectangle()
                        .fill(step >= 2 ? Color.blue : Color(.systemGray4))
                        .frame(height: 2)
                    stepDot(2)
                }
                .padding(.horizontal, 60)
                .padding(.top, 20)

                ScrollView {
                    VStack(spacing: 24) {
                        if step == 1 {
                            certImportStep
                        } else {
                            serverSetupStep
                        }
                    }
                    .padding(24)
                }
            }
            .navigationTitle("Setup")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Step 1: Certificate Import

    private var certImportStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Import Certificate")
                .font(.title2.bold())

            Text("Import your client certificate (.p12 file) to connect securely to your ApexChat server.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            // File selection
            Button {
                showFilePicker = true
            } label: {
                HStack {
                    Image(systemName: "doc.badge.plus")
                    Text(selectedFileName ?? "Select .p12 File")
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .fileImporter(
                isPresented: $showFilePicker,
                allowedContentTypes: [UTType(filenameExtension: "p12") ?? .data],
                allowsMultipleSelection: false
            ) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    let accessing = url.startAccessingSecurityScopedResource()
                    defer { if accessing { url.stopAccessingSecurityScopedResource() } }
                    do {
                        selectedFileData = try Data(contentsOf: url)
                        selectedFileName = url.lastPathComponent
                        certError = nil
                    } catch {
                        certError = "Failed to read file: \(error.localizedDescription)"
                    }
                case .failure(let error):
                    certError = error.localizedDescription
                }
            }

            // Password field
            SecureField("Certificate Password", text: $password)
                .textContentType(.password)
                .padding()
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))

            // Import button
            Button {
                importCertificate()
            } label: {
                Text("Import Certificate")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(selectedFileData != nil ? Color.blue : Color.gray)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .disabled(selectedFileData == nil)

            // Status
            if certImported {
                Label("Certificate imported successfully", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.subheadline)
            }

            if let error = certError {
                Label(error, systemImage: "xmark.circle.fill")
                    .foregroundStyle(.red)
                    .font(.subheadline)
            }

            // Next step
            if certImported {
                Button {
                    withAnimation { step = 2 }
                } label: {
                    Text("Next: Server Setup")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .padding(.top, 8)
            }
        }
    }

    // MARK: - Step 2: Server Setup

    private var serverSetupStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Server Connection")
                .font(.title2.bold())

            Text("Enter your ApexChat server address. Make sure you're connected to your VPN.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            // URL field
            TextField("Server URL", text: $serverURL)
                .keyboardType(.URL)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .padding()
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .onChange(of: serverURL) {
                    healthOK = false
                    healthError = nil
                }

            // Test button
            Button {
                testConnection()
            } label: {
                HStack {
                    if isTestingConnection {
                        ProgressView()
                            .tint(.white)
                    }
                    Text(isTestingConnection ? "Testing..." : "Test Connection")
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.blue)
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .disabled(isTestingConnection)

            // Status
            if healthOK {
                Label("Connected successfully", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.subheadline)
            }

            if let error = healthError {
                Label(error, systemImage: "xmark.circle.fill")
                    .foregroundStyle(.red)
                    .font(.subheadline)
            }

            // Start button
            if healthOK {
                Button {
                    appState.apiClient.baseURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
                } label: {
                    Text("Start Chatting")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .padding(.top, 8)
            }

            // Back button
            Button {
                withAnimation { step = 1 }
            } label: {
                Text("Back to Certificate")
                    .font(.subheadline)
                    .foregroundStyle(.blue)
            }
            .padding(.top, 4)
        }
    }

    // MARK: - Step Dot

    private func stepDot(_ number: Int) -> some View {
        ZStack {
            Circle()
                .fill(step >= number ? Color.blue : Color(.systemGray4))
                .frame(width: 32, height: 32)

            Text("\(number)")
                .font(.subheadline.bold())
                .foregroundStyle(step >= number ? .white : .secondary)
        }
    }

    // MARK: - Actions

    private func importCertificate() {
        guard let data = selectedFileData else { return }
        do {
            try appState.certificateManager.importP12(data: data, password: password)
            certImported = true
            certError = nil
        } catch {
            certError = error.localizedDescription
            certImported = false
        }
    }

    private func testConnection() {
        let candidateURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard isValidServerURL(candidateURL) else {
            healthOK = false
            healthError = "Enter a valid http:// or https:// server URL."
            return
        }

        isTestingConnection = true
        healthOK = false
        healthError = nil

        Task {
            do {
                let ok = try await appState.apiClient.healthCheck(baseURLOverride: candidateURL)
                await MainActor.run {
                    healthOK = ok
                    if !ok {
                        healthError = "Server returned unhealthy status"
                    }
                }
            } catch {
                await MainActor.run {
                    healthError = error.localizedDescription
                }
            }
            await MainActor.run {
                isTestingConnection = false
            }
        }
    }

    private func isValidServerURL(_ value: String) -> Bool {
        guard let url = URL(string: value),
              let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              url.host != nil else {
            return false
        }
        return true
    }
}
