import Foundation
import Observation
import UniformTypeIdentifiers

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
        config.timeoutIntervalForResource = 60
        config.timeoutIntervalForRequest = 30
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

    func fetchMessages(chatId: String, days: Int = 3) async throws -> [Message] {
        let data = try await request("GET", path: "/api/chats/\(chatId)/messages?days=\(days)")
        return try JSONDecoder().decode([Message].self, from: data)
    }

    func deleteChat(chatId: String) async throws {
        throw APIError.unsupportedEndpoint("DELETE /api/chats/{id}")
    }

    func healthCheck(baseURLOverride: String? = nil) async throws -> Bool {
        let data = try await request("GET", path: "/health", baseURLOverride: baseURLOverride)
        return try JSONDecoder().decode(HealthResponse.self, from: data).ok
    }

    func fetchUsage() async throws -> UsageResponse {
        let data = try await request("GET", path: "/api/usage")
        return try JSONDecoder().decode(UsageResponse.self, from: data)
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

    // MARK: - Private

    private func request(
        _ method: String,
        path: String,
        body: Data? = nil,
        headers: [String: String] = [:],
        baseURLOverride: String? = nil
    ) async throws -> Data {
        let resolvedBaseURL = normalizedBaseURL(baseURLOverride ?? baseURL)

        guard let url = URL(string: resolvedBaseURL + path) else {
            throw APIError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.httpBody = body
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

    private func normalizedBaseURL(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return defaultBaseURL }
        return trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
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

private extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}
