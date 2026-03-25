import Foundation
import Observation

@MainActor
@Observable
final class AppState {
    var chats: [Chat] = []
    var selectedChatId: String?
    var messages: [Message] = []
    var isLoadingChats: Bool = false
    var isLoadingMessages: Bool = false
    var error: String?
    var streamMessageHandler: ((ServerMessage) -> Void)?

    let certificateManager: CertificateManager
    let apiClient: APIClient
    let connectionManager: ConnectionManager

    var isConfigured: Bool {
        certificateManager.hasIdentity &&
        !(UserDefaults.standard.string(forKey: "server_url")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .isEmpty ?? true)
    }

    var selectedChat: Chat? {
        chats.first { $0.id == selectedChatId }
    }

    init() {
        let certManager = CertificateManager()
        self.certificateManager = certManager
        self.apiClient = APIClient(certificateManager: certManager)
        self.connectionManager = ConnectionManager(certificateManager: certManager)

        // Wire up server message handler
        connectionManager.onMessage = { [weak self] message in
            Task { @MainActor in
                self?.handleServerMessage(message)
                self?.streamMessageHandler?(message)
            }
        }
        connectionManager.onConnected = { [weak self] in
            Task { @MainActor in
                guard let self, let chatId = self.selectedChatId else { return }
                self.connectionManager.send(.attach(chatId: chatId))
            }
        }
    }

    // MARK: - Chat Operations

    func loadChats() async {
        isLoadingChats = true
        defer { isLoadingChats = false }
        do {
            chats = try await apiClient.fetchChats().sorted()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func selectChat(_ chatId: String) async {
        selectedChatId = chatId
        connectionManager.send(.attach(chatId: chatId))
        await loadMessages(chatId)
    }

    func loadMessages(_ chatId: String) async {
        isLoadingMessages = true
        defer { isLoadingMessages = false }
        do {
            messages = try await apiClient.fetchMessages(chatId: chatId)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createChat() async {
        do {
            let id = try await apiClient.createChat()
            await loadChats()
            await selectChat(id)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteChat(_ chatId: String) async {
        error = "Deleting chats is not supported by the current LocalChat server."
    }

    // MARK: - Connection

    func connect() {
        connectionManager.connect()
    }

    func disconnect() {
        connectionManager.disconnect()
    }

    // MARK: - Server Message Handling

    private func handleServerMessage(_ message: ServerMessage) {
        switch message {
        case .pong:
            break
        case .chatUpdated(let chatId, let title):
            if let index = chats.firstIndex(where: { $0.id == chatId }) {
                chats[index].title = title
            }
        case .attachOk(let chatId):
            guard selectedChatId == chatId else { break }
            Task { await loadMessages(chatId) }
        case .streamCompleteReload(let chatId):
            guard selectedChatId == chatId else { break }
            Task {
                await loadMessages(chatId)
                await loadChats()
            }
        case .error(let msg):
            error = msg
        case .system(_, _):
            break
        default:
            // streaming messages handled by ChatView's overlay handler
            break
        }
    }
}
