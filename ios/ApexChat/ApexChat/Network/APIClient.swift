import Foundation
import Observation
import UniformTypeIdentifiers

@Observable
final class APIClient {
    private let delegate: TLSDelegate

    var baseURL: String {
        get { ServerConfig.currentBaseURL }
        set { ServerConfig.setBaseURL(newValue) }
    }

    private let session: URLSession

    init(certificateManager: CertificateManager) {
        delegate = TLSDelegate(certificateManager: certificateManager)
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForResource = 60
        config.timeoutIntervalForRequest = 30
        session = URLSession(configuration: config, delegate: delegate, delegateQueue: nil)
    }

    // MARK: - REST Endpoints

    func fetchChats() async throws -> [Chat] {
        let data = try await request("GET", path: "/api/chats")
        return try JSONDecoder().decode([Chat].self, from: data)
    }

    func createChat(model: String? = nil, type: String? = nil, category: String? = nil, profileId: String? = nil) async throws -> String {
        var body: Data? = nil
        if model != nil || type != nil || category != nil || profileId != nil {
            var dict: [String: String] = [:]
            if let model { dict["model"] = model }
            if let type { dict["type"] = type }
            if let category { dict["category"] = category }
            if let profileId, !profileId.isEmpty { dict["profile_id"] = profileId }
            body = try JSONSerialization.data(withJSONObject: dict)
        }
        let data = try await request("POST", path: "/api/chats", body: body)
        return try JSONDecoder().decode(CreateChatResponse.self, from: data).id
    }

    func createGroup(title: String, members: [[String: String]]) async throws -> String {
        let dict: [String: Any] = ["type": "group", "title": title, "members": members]
        let body = try JSONSerialization.data(withJSONObject: dict)
        let data = try await request("POST", path: "/api/chats", body: body)
        return try JSONDecoder().decode(CreateChatResponse.self, from: data).id
    }

    func fetchFeatures() async throws -> [String: Bool] {
        let data = try await request("GET", path: "/api/features")
        return try JSONDecoder().decode([String: Bool].self, from: data)
    }

    func fetchProfiles() async throws -> [AgentProfile] {
        let data = try await request("GET", path: "/api/profiles")
        return try JSONDecoder().decode(ProfilesResponse.self, from: data).profiles
    }

    func updateChatProfile(chatId: String, profileId: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["profile_id": profileId])
        _ = try await request("PATCH", path: "/api/chats/\(chatId)", body: body)
    }

    func fetchMessages(chatId: String, days: Int = 3) async throws -> [Message] {
        let data = try await request("GET", path: "/api/chats/\(chatId)/messages?days=\(days)")
        return try JSONDecoder().decode([Message].self, from: data)
    }

    func renameChat(chatId: String, title: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["title": title])
        _ = try await request("PATCH", path: "/api/chats/\(chatId)", body: body)
    }

    func deleteChat(chatId: String) async throws {
        _ = try await request("DELETE", path: "/api/chats/\(chatId)")
    }

    func healthCheck(baseURLOverride: String? = nil) async throws -> Bool {
        let data = try await request("GET", path: "/health", baseURLOverride: baseURLOverride)
        return try JSONDecoder().decode(HealthResponse.self, from: data).ok
    }

    func fetchUsage() async throws -> UsageResponse {
        let data = try await request("GET", path: "/api/usage")
        return try JSONDecoder().decode(UsageResponse.self, from: data)
    }

    func fetchContext(chatId: String) async throws -> ContextData {
        let data = try await request("GET", path: "/api/chats/\(chatId)/context")
        return try JSONDecoder().decode(ContextData.self, from: data)
    }

    func uploadFile(data: Data, filename: String) async throws -> UploadResponse {
        let boundary = "Boundary-\(UUID().uuidString)"
        let body = makeMultipartBody(data: data, filename: filename, boundary: boundary)
        let response = try await request(
            "POST",
            path: "/api/upload",
            body: body,
            headers: ["Content-Type": "multipart/form-data; boundary=\(boundary)"]
        )
        return try JSONDecoder().decode(UploadResponse.self, from: response)
    }

    func fetchAlerts(since: String? = nil, unackedOnly: Bool = false, category: String? = nil) async throws -> [Alert] {
        var path = "/api/alerts?"
        if let since = since {
            path += "since=\(since.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? since)&"
        }
        if unackedOnly {
            path += "unacked=true&"
        }
        if let category = category {
            path += "category=\(category)&"
        }
        let data = try await request("GET", path: path)
        return try JSONDecoder().decode([Alert].self, from: data)
    }

    func fetchAlertsLongPoll(since: String? = nil, timeout: Int = 20) async throws -> [Alert] {
        var path = "/api/alerts/wait?timeout=\(timeout)&"
        if let since = since {
            path += "since=\(since.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? since)&"
        }
        let data = try await request("GET", path: path, timeout: Double(timeout + 10))
        return try JSONDecoder().decode([Alert].self, from: data)
    }

    func ackAlert(alertId: String) async throws {
        _ = try await request("POST", path: "/api/alerts/\(alertId)/ack")
    }

    func allowAlert(alertId: String) async throws {
        _ = try await request("POST", path: "/api/alerts/\(alertId)/allow")
    }

    func deleteAlert(alertId: String) async throws {
        _ = try await request("DELETE", path: "/api/alerts/\(alertId)")
    }

    func deleteAllAlerts() async throws {
        _ = try await request("DELETE", path: "/api/alerts")
    }

    func fetchLocalModels() async throws -> [LocalModel] {
        let data = try await request("GET", path: "/api/models/local")
        return try JSONDecoder().decode([LocalModel].self, from: data)
    }

    // MARK: - Private

    private func request(
        _ method: String,
        path: String,
        body: Data? = nil,
        headers: [String: String] = [:],
        baseURLOverride: String? = nil,
        timeout: TimeInterval? = nil
    ) async throws -> Data {
        let raw = (baseURLOverride ?? baseURL).trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedBaseURL = raw.hasSuffix("/") ? String(raw.dropLast()) : raw

        guard let url = URL(string: resolvedBaseURL + path) else {
            throw APIError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.httpBody = body
        if let timeout { req.timeoutInterval = timeout }
        if body != nil && headers["Content-Type"] == nil {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        for (field, value) in headers {
            req.setValue(value, forHTTPHeaderField: field)
        }

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

    private func makeMultipartBody(data: Data, filename: String, boundary: String) -> Data {
        let safeFilename = URL(fileURLWithPath: filename).lastPathComponent
        let mimeType = mimeType(for: safeFilename)
        var body = Data()

        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(safeFilename)\"\r\n")
        body.append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n")
        return body
    }

    private func mimeType(for filename: String) -> String {
        let ext = URL(fileURLWithPath: filename).pathExtension
        if ext.isEmpty {
            return "application/octet-stream"
        }
        return UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
    }
}

struct UploadResponse: Decodable {
    let id: String
    let name: String
    let type: String
    let ext: String
    let size: Int
}

private struct CreateChatResponse: Decodable {
    let id: String
}

private struct HealthResponse: Decodable {
    let ok: Bool
}

// MARK: - Local Models

struct LocalModel: Identifiable, Decodable {
    let id: String
    let displayName: String
    let sizeGb: Double
    let local: Bool

    enum CodingKeys: String, CodingKey {
        case id, local
        case displayName = "displayName"
        case sizeGb = "sizeGb"
    }
}

// MARK: - Usage

struct UsageResponse: Decodable {
    let plan: String?
    let session: UsageBucket
    let weekly: UsageBucket
    let models: [String: UsageBucket]?

    struct UsageBucket: Decodable {
        let utilization: Int
        let resetsAt: String
        let resetsIn: String

        enum CodingKeys: String, CodingKey {
            case utilization
            case resetsAt = "resets_at"
            case resetsIn = "resets_in"
        }
    }
}

// MARK: - Context

struct ContextData: Decodable, Equatable {
    let tokensIn: Int
    let contextWindow: Int

    enum CodingKeys: String, CodingKey {
        case tokensIn = "tokens_in"
        case contextWindow = "context_window"
    }
}

private extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}
