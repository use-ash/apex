import Foundation
import Observation
import Security

@Observable
final class CertificateManager {
    private static let identityLabel = "com.openclaw.localchat.client"
    private static let caLabel = "com.openclaw.localchat.ca"

    var hasIdentity: Bool = false
    var importError: String?

    init() {
        hasIdentity = loadIdentity() != nil
    }

    // MARK: - Import

    func importP12(data: Data, password: String) throws {
        // Remove any existing items first
        deleteAll()

        let options: [String: Any] = [kSecImportExportPassphrase as String: password]
        var items: CFArray?
        let status = SecPKCS12Import(data as CFData, options as CFDictionary, &items)

        guard status == errSecSuccess else {
            let msg = "P12 import failed: \(status)"
            importError = msg
            throw CertError.importFailed(msg)
        }

        guard let itemArray = items as? [[String: Any]],
              let firstItem = itemArray.first else {
            let msg = "No identities found in P12"
            importError = msg
            throw CertError.noIdentity(msg)
        }

        // Extract identity and CA from the imported chain before storing either item.
        guard let identity = firstItem[kSecImportItemIdentity as String] else {
            let msg = "No identity in P12 item"
            importError = msg
            throw CertError.noIdentity(msg)
        }

        guard let chain = firstItem[kSecImportItemCertChain as String] as? [SecCertificate],
              let caCertificate = chain.last,
              chain.count > 1 else {
            let msg = "P12 is missing the CA certificate needed for server pinning"
            importError = msg
            throw CertError.missingCA(msg)
        }

        // Store identity in keychain.
        let addIdentityQuery: [String: Any] = [
            kSecClass as String: kSecClassIdentity,
            kSecValueRef as String: identity,
            kSecAttrLabel as String: Self.identityLabel,
        ]
        let addStatus = SecItemAdd(addIdentityQuery as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            let msg = "Failed to store identity: \(addStatus)"
            importError = msg
            throw CertError.keychainError(msg)
        }

        let addCAQuery: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecValueRef as String: caCertificate,
            kSecAttrLabel as String: Self.caLabel,
        ]
        let caStatus = SecItemAdd(addCAQuery as CFDictionary, nil)
        guard caStatus == errSecSuccess else {
            deleteAll()
            let msg = "Failed to store CA certificate: \(caStatus)"
            importError = msg
            throw CertError.keychainError(msg)
        }

        hasIdentity = true
        importError = nil
    }

    // MARK: - Load

    func loadIdentity() -> SecIdentity? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassIdentity,
            kSecAttrLabel as String: Self.identityLabel,
            kSecReturnRef as String: true,
        ]
        var identity: SecIdentity?
        let status = withUnsafeMutablePointer(to: &identity) { pointer in
            pointer.withMemoryRebound(to: CFTypeRef?.self, capacity: 1) { reboundPointer in
                SecItemCopyMatching(query as CFDictionary, reboundPointer)
            }
        }
        guard status == errSecSuccess else { return nil }
        return identity
    }

    func loadCACertificate() -> SecCertificate? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecAttrLabel as String: Self.caLabel,
            kSecReturnRef as String: true,
        ]
        var certificate: SecCertificate?
        let status = withUnsafeMutablePointer(to: &certificate) { pointer in
            pointer.withMemoryRebound(to: CFTypeRef?.self, capacity: 1) { reboundPointer in
                SecItemCopyMatching(query as CFDictionary, reboundPointer)
            }
        }
        guard status == errSecSuccess else { return nil }
        return certificate
    }

    // MARK: - Delete

    func deleteAll() {
        let identityQuery: [String: Any] = [
            kSecClass as String: kSecClassIdentity,
            kSecAttrLabel as String: Self.identityLabel,
        ]
        SecItemDelete(identityQuery as CFDictionary)

        let caQuery: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecAttrLabel as String: Self.caLabel,
        ]
        SecItemDelete(caQuery as CFDictionary)

        hasIdentity = false
    }

    // MARK: - Errors

    enum CertError: LocalizedError {
        case importFailed(String)
        case noIdentity(String)
        case missingCA(String)
        case keychainError(String)

        var errorDescription: String? {
            switch self {
            case .importFailed(let msg), .noIdentity(let msg), .missingCA(let msg), .keychainError(let msg):
                return msg
            }
        }
    }
}
