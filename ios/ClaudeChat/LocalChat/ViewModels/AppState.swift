import Foundation
import Observation
import SwiftUI
import UserNotifications

@MainActor
@Observable
final class AppState {
    private static let persistentChatIdKey = "persistent_chat_id"
    private static let selectedModelKey = "selected_model"
    static let supportedModels: [ModelOption] = [
        ModelOption(id: "claude-opus-4-6", displayName: "Opus 4.6"),
        ModelOption(id: "claude-sonnet-4-6", displayName: "Sonnet 4.6"),
        ModelOption(id: "claude-haiku-4-5-20251001", displayName: "Haiku 4.5"),
    ]

    var persistentChatId: String? {
        didSet {
            UserDefaults.standard.set(persistentChatId, forKey: Self.persistentChatIdKey)
        }
    }
    var currentChat: Chat?
    var messages: [Message] = []
    var isLoadingMessages: Bool = false
    var isEnsuringPersistentChat: Bool = false
    var error: String?
    var scenePhase: ScenePhase = .active
    var streamMessageHandler: ((ServerMessage) -> Void)?
    var usageData: UsageResponse?
    private var usagePollingTask: Task<Void, Never>?
    var selectedModel: String {
        didSet {
            UserDefaults.standard.set(selectedModel, forKey: Self.selectedModelKey)
        }
    }

    let certificateManager: CertificateManager
    let apiClient: APIClient
    let connectionManager: ConnectionManager

    private var streamingResponsePreview: String = ""

    var isConfigured: Bool {
        !(UserDefaults.standard.string(forKey: "server_url")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .isEmpty ?? true)
    }

    var serverURL: String {
        apiClient.baseURL
    }

    var connectionStatusText: String {
        if connectionManager.isConnected {
            return "Connected"
        }
        if let connectionError = connectionManager.connectionError,
           !connectionError.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return connectionError
        }
        return "Disconnected"
    }

    var modelDisplayName: String {
        Self.friendlyModelName(connectionManager.serverModel ?? selectedModel)
    }

    var modelDescription: String {
        connectionManager.serverModel ?? selectedModel
    }

    init() {
        let certManager = CertificateManager()
        self.persistentChatId = UserDefaults.standard.string(forKey: Self.persistentChatIdKey)
        self.selectedModel = UserDefaults.standard.string(forKey: Self.selectedModelKey) ?? Self.supportedModels[0].id
        self.certificateManager = certManager
        self.apiClient = APIClient(certificateManager: certManager)
        self.connectionManager = ConnectionManager(certificateManager: certManager)

        connectionManager.onMessage = { [weak self] message in
            Task { @MainActor in
                self?.handleServerMessage(message)
                self?.streamMessageHandler?(message)
            }
        }
        connectionManager.onConnected = { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.connectionManager.send(.setModel(model: self.selectedModel))
                guard let chatId = self.persistentChatId else { return }
                self.connectionManager.send(.attach(chatId: chatId))
            }
        }
    }

    // MARK: - Chat Lifecycle

    func ensurePersistentChat() async {
        guard isConfigured else { return }
        guard !isEnsuringPersistentChat else { return }

        isEnsuringPersistentChat = true
        defer { isEnsuringPersistentChat = false }

        do {
            let chats = try await apiClient.fetchChats().sorted()
            let resolvedChat = try await resolvePersistentChat(from: chats)

            persistentChatId = resolvedChat.id
            currentChat = resolvedChat
            error = nil

            if connectionManager.isConnected {
                connectionManager.send(.attach(chatId: resolvedChat.id))
            }
            await loadMessages(resolvedChat.id)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refreshPersistentChat() async {
        guard let chatId = persistentChatId else { return }

        do {
            let chats = try await apiClient.fetchChats().sorted()
            if let matchingChat = chats.first(where: { $0.id == chatId }) {
                currentChat = matchingChat
            } else if let mostRecentChat = chats.first {
                persistentChatId = mostRecentChat.id
                currentChat = mostRecentChat
            } else {
                currentChat = nil
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadMessages(_ chatId: String? = nil) async {
        guard let chatId = chatId ?? persistentChatId else { return }

        isLoadingMessages = true
        defer { isLoadingMessages = false }

        do {
            messages = try await apiClient.fetchMessages(chatId: chatId)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Connection

    func connect() {
        connectionManager.connect()
    }

    func disconnect() {
        connectionManager.disconnect()
    }

    func updateServerURL(_ value: String) {
        apiClient.baseURL = value
    }

    func updateSelectedModel(_ model: String) {
        guard Self.supportedModels.contains(where: { $0.id == model }) else { return }
        selectedModel = model
        connectionManager.serverModel = model
        if connectionManager.isConnected {
            connectionManager.send(.setModel(model: model))
        }
    }

    // MARK: - Usage

    func startUsagePolling() {
        usagePollingTask?.cancel()
        usagePollingTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.fetchUsage()
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    func stopUsagePolling() {
        usagePollingTask?.cancel()
        usagePollingTask = nil
    }

    func fetchUsage() async {
        do {
            usageData = try await apiClient.fetchUsage()
        } catch {
            // Silently fail — banner just won't show
        }
    }

    static func friendlyModelName(_ model: String?) -> String {
        guard let model, !model.isEmpty else { return "Model" }
        if let option = supportedModels.first(where: { $0.id == model }) {
            return option.displayName
        }
        let lowercased = model.lowercased()
        if lowercased.contains("opus") { return "Opus" }
        if lowercased.contains("sonnet") { return "Sonnet" }
        if lowercased.contains("haiku") { return "Haiku" }
        return model
    }

    // MARK: - Private

    private func resolvePersistentChat(from chats: [Chat]) async throws -> Chat {
        if let persistentChatId,
           let matchingChat = chats.first(where: { $0.id == persistentChatId }) {
            return matchingChat
        }

        if let mostRecentChat = chats.first {
            return mostRecentChat
        }

        let createdChatId = try await apiClient.createChat()
        let refreshedChats = try await apiClient.fetchChats().sorted()
        if let createdChat = refreshedChats.first(where: { $0.id == createdChatId }) {
            return createdChat
        }

        return fallbackChat(id: createdChatId)
    }

    private func fallbackChat(id: String) -> Chat {
        let now = ISO8601DateFormatter().string(from: Date())
        return Chat(
            id: id,
            title: "New Chat",
            claudeSessionId: nil,
            createdAt: now,
            updatedAt: now
        )
    }

    private func handleServerMessage(_ message: ServerMessage) {
        switch message {
        case .pong:
            break
        case .streamStart:
            streamingResponsePreview = ""
        case .text(let text):
            streamingResponsePreview += text
        case .chatUpdated(let chatId, let title):
            guard currentChat?.id == chatId else { break }
            guard var currentChat = currentChat else { break }
            currentChat.title = title
            self.currentChat = currentChat
        case .attachOk(let chatId):
            guard persistentChatId == chatId else { break }
            Task { await loadMessages(chatId) }
        case .streamCompleteReload(let chatId):
            streamingResponsePreview = ""
            guard persistentChatId == chatId else { break }
            Task {
                await loadMessages(chatId)
                await refreshPersistentChat()
            }
        case .result(let costUsd, let tokensIn, let tokensOut, _):
            if scenePhase == .background {
                enqueueCompletionNotification(
                    body: notificationBody(
                        costUsd: costUsd,
                        tokensIn: tokensIn,
                        tokensOut: tokensOut
                    )
                )
            }
            streamingResponsePreview = ""
            Task { await fetchUsage() }
        case .streamEnd:
            streamingResponsePreview = ""
        case .error(let msg):
            streamingResponsePreview = ""
            error = msg
        case .system(_, _):
            break
        default:
            break
        }
    }

    private func notificationBody(costUsd: Double, tokensIn: Int, tokensOut: Int) -> String {
        let preview = streamingResponsePreview
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if !preview.isEmpty {
            return String(preview.prefix(100))
        }

        return String(
            format: "Response complete. In: %d, Out: %d, Cost: $%.4f",
            tokensIn,
            tokensOut,
            costUsd
        )
    }

    private func enqueueCompletionNotification(body: String) {
        let content = UNMutableNotificationContent()
        content.title = "Claude"
        content.body = body
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }
}

struct ModelOption: Identifiable, Hashable {
    let id: String
    let displayName: String
}
