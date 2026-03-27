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
        ModelOption(id: "grok-4-fast", displayName: "Grok 4 Fast"),
        ModelOption(id: "grok-4", displayName: "Grok 4"),
    ]

    var chats: [Chat] = []
    var profiles: [AgentProfile] = []

    var persistentChatId: String? {
        didSet {
            UserDefaults.standard.set(persistentChatId, forKey: Self.persistentChatIdKey)
        }
    }
    var currentChat: Chat?
    var messages: [Message] = []
    var alerts: [Alert] = []
    var unackedAlertCount: Int { alerts.filter { !$0.acked }.count }
    var toastAlert: Alert?  // Latest alert for toast overlay (any screen)
    var localModels: [LocalModel] = []
    var allModels: [ModelOption] {
        var models = Self.supportedModels
        for lm in localModels {
            models.append(ModelOption(id: lm.id, displayName: "\(lm.displayName) (\(lm.sizeGb)GB)"))
        }
        return models
    }
    var connectionProfiles: [ConnectionProfile] = ConnectionProfile.loadAll()
    var activeProfileId: String? = ConnectionProfile.activeProfileId
    var isLoadingMessages: Bool = false
    var isEnsuringPersistentChat: Bool = false
    var error: String?
    var scenePhase: ScenePhase = .active
    var streamMessageHandler: ((ServerMessage) -> Void)?
    var usageData: UsageResponse?
    var contextData: ContextData?
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
        Self.friendlyModelName(currentChat?.model ?? connectionManager.serverModel ?? selectedModel)
    }

    var modelDescription: String {
        currentChat?.model ?? connectionManager.serverModel ?? selectedModel
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
                // Don't send global set_model — each chat has its own model in the DB
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
            self.chats = chats
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

    func switchProfile(_ profile: ConnectionProfile) {
        activeProfileId = profile.id
        ConnectionProfile.activeProfileId = profile.id
        disconnect()
        updateServerURL(profile.serverURL)
        connect()
        Task { await ensurePersistentChat() }
    }

    func saveProfiles() {
        ConnectionProfile.saveAll(connectionProfiles)
    }

    func updateSelectedModel(_ model: String) {
        guard allModels.contains(where: { $0.id == model }) else { return }
        // Only update the current chat's model — not the global default
        guard let chatId = persistentChatId else { return }
        if connectionManager.isConnected {
            connectionManager.send(.setChatModel(chatId: chatId, model: model))
        }
        if let idx = chats.firstIndex(where: { $0.id == chatId }) {
            chats[idx].model = model
        }
        currentChat?.model = model
    }

    // MARK: - Channels

    func loadChats() async {
        do {
            chats = try await apiClient.fetchChats().sorted()
        } catch {
            // Silent fail
        }
    }

    func createChannel(name: String, model: String) async {
        do {
            let chatId = try await apiClient.createChat(model: model)
            await loadChats()
            if let chat = chats.first(where: { $0.id == chatId }) {
                switchToChat(chat)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createChannelWithProfile(_ profileId: String) async {
        do {
            let chatId = try await apiClient.createChat(profileId: profileId)
            await loadChats()
            if let chat = chats.first(where: { $0.id == chatId }) {
                switchToChat(chat)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadProfiles() async {
        do {
            profiles = try await apiClient.fetchProfiles()
        } catch {
            // Profiles are supplementary — silent fail
        }
    }

    func updateChatProfile(_ chatId: String, profileId: String) async {
        do {
            try await apiClient.updateChatProfile(chatId: chatId, profileId: profileId)
            await loadChats()
            if let updated = chats.first(where: { $0.id == chatId }) {
                if currentChat?.id == chatId {
                    currentChat = updated
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func renameChannel(_ chatId: String, to newTitle: String) async {
        do {
            try await apiClient.renameChat(chatId: chatId, title: newTitle)
            // Server broadcasts chat_updated via WS — but update local state immediately
            if let idx = chats.firstIndex(where: { $0.id == chatId }) {
                chats[idx].title = newTitle
            }
            if currentChat?.id == chatId {
                currentChat?.title = newTitle
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteChannel(_ chatId: String) async {
        do {
            try await apiClient.deleteChat(chatId: chatId)
            chats.removeAll { $0.id == chatId }
            if currentChat?.id == chatId {
                if let first = chats.first {
                    switchToChat(first)
                } else {
                    currentChat = nil
                    persistentChatId = nil
                    messages = []
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createAlertsChannel(category: String? = nil) async {
        do {
            _ = try await apiClient.createChat(type: "alerts", category: category)
            await loadChats()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func switchToChat(_ chat: Chat) {
        persistentChatId = chat.id
        currentChat = chat
        messages = []
        connectionManager.send(.attach(chatId: chat.id))
        Task { await loadMessages(chat.id) }
        if chat.type == "alerts" {
            Task { await loadAlerts() }
        }
    }

    // MARK: - Usage

    func startUsagePolling() {
        usagePollingTask?.cancel()
        usagePollingTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.fetchUsage()
                try? await Task.sleep(for: .seconds(300))
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

    func fetchContext() async {
        guard let chatId = persistentChatId else { return }
        do {
            contextData = try await apiClient.fetchContext(chatId: chatId)
        } catch {
            contextData = nil
        }
    }

    func refreshCurrentView() async {
        if !connectionManager.isConnected {
            connectionManager.connect()
        }

        await loadChats()
        await loadProfiles()

        if persistentChatId == nil {
            await ensurePersistentChat()
        } else {
            await refreshPersistentChat()
        }

        if let chatId = persistentChatId {
            connectionManager.send(.attach(chatId: chatId))
            await loadMessages(chatId)
            await fetchContext()
        }

        await loadAlerts()
        await fetchUsage()
    }

    static func alertCategory(for source: String) -> String {
        switch source {
        case "plan_h", "plan_c", "plan_h_backstop", "plan_m", "plan_alpha", "regime":
            return "trading"
        case "guardrail", "watchdog", "system":
            return "system"
        case "test":
            return "test"
        default:
            return "other"
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
        if lowercased.contains("grok") { return "Grok" }
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
        let now = DateParsing.iso8601.string(from: Date())
        return Chat(
            id: id,
            title: "New Chat",
            model: nil,
            type: nil,
            category: nil,
            claudeSessionId: nil,
            createdAt: now,
            updatedAt: now,
            profileId: nil,
            profileName: nil,
            profileAvatar: nil
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
        case .chatUpdated(let chatId, let title, let model):
            guard currentChat?.id == chatId else { break }
            guard var updatedChat = currentChat else { break }
            updatedChat.title = title
            if let model { updatedChat.model = model }
            self.currentChat = updatedChat
            if let idx = chats.firstIndex(where: { $0.id == chatId }) {
                chats[idx].title = title
                if let model { chats[idx].model = model }
            }
        case .chatDeleted(let chatId):
            chats.removeAll { $0.id == chatId }
            if currentChat?.id == chatId {
                if let first = chats.first {
                    switchToChat(first)
                } else {
                    currentChat = nil
                    persistentChatId = nil
                    messages = []
                }
            }
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
        case .userMessageAdded(let chatId, let content):
            guard persistentChatId == chatId else { break }
            let userMsg = Message(
                id: UUID().uuidString,
                role: "user",
                content: content,
                toolEvents: "",
                thinking: "",
                costUsd: 0,
                tokensIn: 0,
                tokensOut: 0,
                createdAt: DateParsing.iso8601.string(from: Date())
            )
            messages.append(userMsg)
        case .result(let costUsd, let tokensIn, let tokensOut, _, let contextTokensIn, let contextWindow):
            if scenePhase == .background {
                enqueueCompletionNotification(
                    body: notificationBody(
                        costUsd: costUsd,
                        tokensIn: tokensIn,
                        tokensOut: tokensOut
                    )
                )
            }
            if let ctxIn = contextTokensIn, let ctxWindow = contextWindow {
                contextData = ContextData(tokensIn: ctxIn, contextWindow: ctxWindow)
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
        case .alert(let id, let source, let severity, let title, let body, let createdAt, let metadata):
            let alert = Alert(id: id, source: source, severity: severity, title: title, body: body, acked: false, createdAt: createdAt, metadata: metadata)
            // Only insert if it matches the current channel's category filter
            // Empty string = catch-all (show everything), nil = not an alerts channel (show everything)
            if let channelCategory = currentChat?.category, !channelCategory.isEmpty {
                let sourceCategory = Self.alertCategory(for: source)
                if sourceCategory != channelCategory {
                    // Still notify even if not displayed
                    if scenePhase == .background || scenePhase == .inactive {
                        enqueueAlertNotification(alert)
                    }
                    break
                }
            }
            alerts.insert(alert, at: 0)
            // Only show toast if NOT already viewing an alerts channel
            if currentChat?.type != "alerts" {
                withAnimation(.easeInOut(duration: 0.3)) {
                    toastAlert = alert
                }
            }
            if scenePhase == .background || scenePhase == .inactive {
                enqueueAlertNotification(alert)
            }
        case .alertAcked(let alertId):
            if let idx = alerts.firstIndex(where: { $0.id == alertId }) {
                alerts[idx].acked = true
            }
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

    func loadAlerts() async {
        do {
            let category = currentChat?.type == "alerts" ? currentChat?.category : nil
            alerts = try await apiClient.fetchAlerts(category: category)
        } catch {
            // Alerts are supplementary — silent fail
        }
    }

    func loadLocalModels() async {
        do {
            localModels = try await apiClient.fetchLocalModels()
        } catch {
            // Local models are optional — silent fail
        }
    }

    func ackAlert(_ alertId: String) async {
        do {
            try await apiClient.ackAlert(alertId: alertId)
            if let idx = alerts.firstIndex(where: { $0.id == alertId }) {
                alerts[idx].acked = true
            }
        } catch {
            self.error = "Failed to ack alert: \(error.localizedDescription)"
        }
    }

    func allowAlert(_ alertId: String) async {
        do {
            try await apiClient.allowAlert(alertId: alertId)
            if let idx = alerts.firstIndex(where: { $0.id == alertId }) {
                alerts[idx].acked = true
            }
        } catch {
            self.error = "Failed to allow: \(error.localizedDescription)"
        }
    }

    func deleteAlert(_ alertId: String) async {
        do {
            try await apiClient.deleteAlert(alertId: alertId)
            alerts.removeAll { $0.id == alertId }
        } catch {
            self.error = "Failed to delete alert: \(error.localizedDescription)"
        }
    }

    func deleteAllAlerts() async {
        do {
            try await apiClient.deleteAllAlerts()
            alerts.removeAll()
        } catch {
            self.error = "Failed to clear alerts: \(error.localizedDescription)"
        }
    }

    private func enqueueAlertNotification(_ alert: Alert) {
        let content = UNMutableNotificationContent()
        content.title = "[\(alert.severity.uppercased())] \(alert.source)"
        content.body = alert.title
        content.sound = alert.severity == "critical" ? .defaultCritical : .default
        content.categoryIdentifier = "ALERT"
        content.userInfo = ["alert_id": alert.id]
        content.interruptionLevel = alert.severity == "critical" ? .critical : .timeSensitive
        let request = UNNotificationRequest(
            identifier: "alert-\(alert.id)",
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
