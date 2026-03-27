import Foundation
import Network
import Observation
import OSLog

@Observable
final class ConnectionManager {
    var isConnected: Bool = false
    var connectionError: String?
    var serverModel: String?
    var onMessage: ((ServerMessage) -> Void)?
    var onConnected: (() -> Void)?

    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession!
    private var pingTimer: Timer?
    private var pongTimer: Timer?
    private var reconnectAttempts: Int = 0
    private let maxReconnectDelay: TimeInterval = 15
    private let logger = Logger(subsystem: "com.apex.apexchat", category: "WebSocket")
    private var intentionalDisconnect = false
    private var wantsConnection = false
    private let delegate: TLSDelegate
    private let pathMonitor = NWPathMonitor()
    private var connectionGeneration: UInt64 = 0
    private var pathMonitorDebounceWork: DispatchWorkItem?

    var baseURL: String {
        ServerConfig.currentBaseURL
    }

    init(certificateManager: CertificateManager) {
        delegate = TLSDelegate(certificateManager: certificateManager)
        let config = URLSessionConfiguration.default
        session = URLSession(configuration: config, delegate: delegate, delegateQueue: nil)
        pathMonitor.pathUpdateHandler = { [weak self] path in
            guard let self else { return }
            guard path.status == .satisfied else { return }
            guard self.wantsConnection, !self.isConnected, self.webSocketTask == nil else { return }
            self.pathMonitorDebounceWork?.cancel()
            let work = DispatchWorkItem { [weak self] in
                guard let self, self.wantsConnection, !self.isConnected, self.webSocketTask == nil else { return }
                self.connect()
            }
            self.pathMonitorDebounceWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: work)
        }
        pathMonitor.start(queue: .main)
    }

    deinit {
        pathMonitor.cancel()
    }

    // MARK: - Connect / Disconnect

    func connect() {
        guard webSocketTask == nil else { return }

        wantsConnection = true
        intentionalDisconnect = false
        connectionError = nil

        connectionGeneration &+= 1
        let gen = connectionGeneration

        let wsURL = baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")

        guard let url = URL(string: wsURL + "/ws") else {
            connectionError = "Invalid WebSocket URL"
            return
        }

        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        receiveLoop(generation: gen)
        startPingTimer()
        startPongTimer()
        send(.ping)
    }

    func disconnect() {
        wantsConnection = false
        intentionalDisconnect = true
        stopTimers()
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        isConnected = false
    }

    func ensureConnected() {
        wantsConnection = true
        guard !isConnected, webSocketTask == nil else { return }
        connect()
    }

    func sendBackgroundPing() {
        ensureConnected()
        send(.ping)
    }

    // MARK: - Send

    func send(_ message: ClientMessage) {
        guard let data = try? JSONEncoder().encode(message),
              let string = String(data: data, encoding: .utf8) else { return }
        let currentTask = webSocketTask
        webSocketTask?.send(.string(string)) { [weak self] error in
            if let error {
                self?.logger.error("WS send error: \(error.localizedDescription, privacy: .public)")
                self?.handleDisconnect(for: currentTask)
            }
        }
    }

    // MARK: - Receive Loop

    private func receiveLoop(generation: UInt64) {
        let currentTask = webSocketTask
        webSocketTask?.receive { [weak self] result in
            guard let self else { return }
            guard generation == self.connectionGeneration else {
                return
            }
            switch result {
            case .success(.string(let text)):
                self.handleText(text)
                self.receiveLoop(generation: generation)
            case .success(.data(let data)):
                if let text = String(data: data, encoding: .utf8) {
                    self.handleText(text)
                }
                self.receiveLoop(generation: generation)
            case .failure(let error):
                self.logger.error("WS receive error: \(error.localizedDescription, privacy: .public)")
                self.handleDisconnect(for: currentTask)
            default:
                self.receiveLoop(generation: generation)
            }
        }
    }

    private func handleText(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            if !self.isConnected {
                self.isConnected = true
                self.reconnectAttempts = 0
                self.connectionError = nil
                self.onConnected?()
            }

            let message = self.parseServerMessage(type: type, json: json)
            if case .system(_, let model) = message, let model {
                self.serverModel = model
            }
            self.onMessage?(message)
        }
    }

    // MARK: - Parse Server Messages

    private func parseServerMessage(type: String, json: [String: Any]) -> ServerMessage {
        switch type {
        case "pong":
            resetPongTimer()
            return .pong
        case "stream_start":
            return .streamStart(chatId: json["chat_id"] as? String ?? "")
        case "text":
            return .text(text: json["text"] as? String ?? "")
        case "thinking":
            return .thinking(text: json["text"] as? String ?? "")
        case "tool_use":
            return .toolUse(
                id: json["id"] as? String ?? "",
                name: json["name"] as? String ?? "",
                input: json["input"] ?? [:]
            )
        case "tool_result":
            return .toolResult(
                toolUseId: json["tool_use_id"] as? String ?? "",
                content: json["content"] as? String ?? "",
                isError: json["is_error"] as? Bool ?? false
            )
        case "result":
            return .result(
                costUsd: json["cost_usd"] as? Double ?? 0,
                tokensIn: json["tokens_in"] as? Int ?? 0,
                tokensOut: json["tokens_out"] as? Int ?? 0,
                sessionId: json["session_id"] as? String,
                contextTokensIn: json["context_tokens_in"] as? Int,
                contextWindow: json["context_window"] as? Int
            )
        case "stream_end":
            return .streamEnd(chatId: json["chat_id"] as? String ?? "")
        case "stream_reattached":
            return .streamReattached(chatId: json["chat_id"] as? String ?? "")
        case "attach_ok":
            return .attachOk(chatId: json["chat_id"] as? String ?? "")
        case "stream_complete_reload":
            return .streamCompleteReload(chatId: json["chat_id"] as? String ?? "")
        case "user_message_added":
            return .userMessageAdded(
                chatId: json["chat_id"] as? String ?? "",
                content: json["content"] as? String ?? ""
            )
        case "chat_updated":
            return .chatUpdated(
                chatId: json["chat_id"] as? String ?? "",
                title: json["title"] as? String ?? "",
                model: json["model"] as? String
            )
        case "chat_deleted":
            return .chatDeleted(chatId: json["chat_id"] as? String ?? "")
        case "error":
            return .error(message: json["message"] as? String ?? "Unknown error")
        case "system":
            return .system(
                subtype: json["subtype"] as? String ?? "",
                model: json["model"] as? String
            )
        case "alert":
            return .alert(
                id: json["id"] as? String ?? "",
                source: json["source"] as? String ?? "",
                severity: json["severity"] as? String ?? "info",
                title: json["title"] as? String ?? "",
                body: json["body"] as? String ?? "",
                createdAt: json["created_at"] as? String ?? "",
                metadata: json["metadata"] as? [String: String]
            )
        case "alert_acked":
            return .alertAcked(alertId: json["alert_id"] as? String ?? "")
        default:
            return .error(message: "Unknown message type: \(type)")
        }
    }

    // MARK: - Ping / Pong

    private func startPingTimer() {
        stopTimers()
        pingTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            self?.send(.ping)
            self?.startPongTimer()
        }
    }

    private func startPongTimer() {
        pongTimer?.invalidate()
        let currentTask = webSocketTask
        pongTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: false) { [weak self] _ in
            self?.logger.warning("WS: Pong timeout — forcing reconnect")
            self?.handleDisconnect(for: currentTask)
        }
    }

    private func resetPongTimer() {
        pongTimer?.invalidate()
        pongTimer = nil
    }

    private func stopTimers() {
        pingTimer?.invalidate()
        pingTimer = nil
        pongTimer?.invalidate()
        pongTimer = nil
    }

    // MARK: - Reconnect

    private func handleDisconnect(for task: URLSessionWebSocketTask?) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            guard task === self.webSocketTask else { return }
            let wasConnected = self.isConnected || self.webSocketTask != nil
            self.isConnected = false
            self.stopTimers()
            self.webSocketTask?.cancel(with: .abnormalClosure, reason: nil)
            self.webSocketTask = nil
            if self.wantsConnection && !self.intentionalDisconnect && wasConnected {
                self.scheduleReconnect()
            }
        }
    }

    private func scheduleReconnect() {
        let delay = min(pow(2.0, Double(reconnectAttempts)), maxReconnectDelay)
        reconnectAttempts += 1
        connectionError = "Reconnecting in \(Int(delay))s..."
        logger.info("WS: Scheduling reconnect in \(delay, privacy: .public)s (attempt \(self.reconnectAttempts, privacy: .public))")

        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self, self.wantsConnection, !self.intentionalDisconnect else { return }
            self.connect()
        }
    }

}

// MARK: - Message Types

enum ServerMessage {
    case pong
    case streamStart(chatId: String)
    case text(text: String)
    case thinking(text: String)
    case toolUse(id: String, name: String, input: Any)
    case toolResult(toolUseId: String, content: String, isError: Bool)
    case result(costUsd: Double, tokensIn: Int, tokensOut: Int, sessionId: String?, contextTokensIn: Int?, contextWindow: Int?)
    case streamEnd(chatId: String)
    case streamReattached(chatId: String)
    case attachOk(chatId: String)
    case streamCompleteReload(chatId: String)
    case userMessageAdded(chatId: String, content: String)
    case chatUpdated(chatId: String, title: String, model: String?)
    case chatDeleted(chatId: String)
    case error(message: String)
    case system(subtype: String, model: String?)
    case alert(id: String, source: String, severity: String, title: String, body: String, createdAt: String, metadata: [String: String]?)
    case alertAcked(alertId: String)
}

enum ClientMessage: Encodable {
    case ping
    case attach(chatId: String)
    case send(chatId: String, prompt: String, attachments: [[String: String]]? = nil)
    case setModel(model: String)
    case setChatModel(chatId: String, model: String)
    case stop(chatId: String)

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .ping:
            try container.encode("ping", forKey: .action)
        case .attach(let chatId):
            try container.encode("attach", forKey: .action)
            try container.encode(chatId, forKey: .chatId)
        case .send(let chatId, let prompt, let attachments):
            try container.encode("send", forKey: .action)
            try container.encode(chatId, forKey: .chatId)
            try container.encode(prompt, forKey: .prompt)
            if let attachments {
                try container.encode(attachments, forKey: .attachments)
            }
        case .setModel(let model):
            try container.encode("set_model", forKey: .action)
            try container.encode(model, forKey: .model)
        case .setChatModel(let chatId, let model):
            try container.encode("set_chat_model", forKey: .action)
            try container.encode(chatId, forKey: .chatId)
            try container.encode(model, forKey: .model)
        case .stop(let chatId):
            try container.encode("stop", forKey: .action)
            try container.encode(chatId, forKey: .chatId)
        }
    }

    enum CodingKeys: String, CodingKey {
        case action
        case chatId = "chat_id"
        case prompt
        case attachments
        case model
    }
}
