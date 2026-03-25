import Foundation
import Observation

@Observable
final class APIClient {
    private let defaultBaseURL = "https://10.8.0.2:8300"
    private let delegate: TLSDelegate

    var baseURL: String {
        get { normalizedBaseURL(UserDefaults.standard.string(forKey: "server_url") ?? defaultBaseURL) }
        set { UserDefaults.standard.set(normalizedBaseURL(newValue), forKey: "server_url") }
    }

    private let session: URLSession

    init(certificateManager: CertificateManager) {
        delegate = TLSDelegate(certificateManager: certificateManager)
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForResource = 30
        config.timeoutIntervalForRequest = 15
        session = URLSession(configuration: config, delegate: delegate, delegateQueue: nil)
    }

    // MARK: - REST Endpoints

    func fetchChats() async throws -> [Chat] {
        let data = try await request("GET", path: "/api/chats")
        return try JSONDecoder().decode([Chat].self, from: data)
    }

    func createChat() async throws -> String {
        let data = try await request("POST", path: "/api/chats")
        return try JSONDecoder().decode(CreateChatResponse.self, from: data).id
    }

    func fetchMessages(chatId: String) async throws -> [Message] {
        let data = try await request("GET", path: "/api/chats/\(chatId)/messages")
        return try JSONDecoder().decode([Message].self, from: data)
    }

    func deleteChat(chatId: String) async throws {
        throw APIError.unsupportedEndpoint("DELETE /api/chats/{id}")
    }

    func healthCheck(baseURLOverride: String? = nil) async throws -> Bool {
        let data = try await request("GET", path: "/health", baseURLOverride: baseURLOverride)
        return try JSONDecoder().decode(HealthResponse.self, from: data).ok
    }

    // MARK: - Private

    private func request(
        _ method: String,
        path: String,
        body: Data? = nil,
        baseURLOverride: String? = nil
    ) async throws -> Data {
        let resolvedBaseURL = normalizedBaseURL(baseURLOverride ?? baseURL)

        guard let url = URL(string: resolvedBaseURL + path) else {
            throw APIError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body

        let (data, response) = try await session.data(for: req)

        guard let http = response as? HTTPURLResponse else {
            throw APIError.noConnection
        }

        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.serverError(http.statusCode, body)
        }

        return data
    }

    // MARK: - Errors

    enum APIError: LocalizedError {
        case serverError(Int, String)
        case noConnection
        case invalidURL
        case decodingFailed
        case unsupportedEndpoint(String)

        var errorDescription: String? {
            switch self {
            case .serverError(let code, let msg): return "Server error \(code): \(msg)"
            case .noConnection: return "No connection to server"
            case .invalidURL: return "Invalid server URL"
            case .decodingFailed: return "Failed to decode response"
            case .unsupportedEndpoint(let endpoint): return "Server does not support \(endpoint)"
            }
        }
    }

    private func normalizedBaseURL(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return defaultBaseURL }
        return trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
    }
}

private struct CreateChatResponse: Decodable {
    let id: String
}

private struct HealthResponse: Decodable {
    let ok: Bool
}
