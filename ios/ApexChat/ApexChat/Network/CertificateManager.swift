import Foundation
import Observation
import Security

@Observable
final class CertificateManager {
    private static let identityLabel = "com.apex.apexchat.client"
    private static let caLabel = "com.apex.apexchat.ca"

    // Migration: check old keychain labels
    private static let legacyIdentityLabel = "com.openclaw.localchat.client"
    private static let legacyCaLabel = "com.openclaw.localchat.ca"

    var hasIdentity: Bool = false
    var importError: String?

    init() {
        Self.migrateKeychainLabels()
        hasIdentity = loadIdentity() != nil
    }

    static func migrateKeychainLabels() {
        // Check if identity exists under old label
        let oldIdentityQuery: [String: Any] = [
            kSecClass as String: kSecClassIdentity,
            kSecAttrLabel as String: legacyIdentityLabel,
            kSecReturnRef as String: true
        ]
        var result: CFTypeRef?
        if SecItemCopyMatching(oldIdentityQuery as CFDictionary, &result) == errSecSuccess {
            // Update label to new value
            let updateQuery: [String: Any] = [
                kSecClass as String: kSecClassIdentity,
                kSecAttrLabel as String: legacyIdentityLabel
            ]
            let updateAttrs: [String: Any] = [
                kSecAttrLabel as String: identityLabel
            ]
            SecItemUpdate(updateQuery as CFDictionary, updateAttrs as CFDictionary)
        }
        // Same for CA cert
        let oldCaQuery: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecAttrLabel as String: legacyCaLabel,
            kSecReturnRef as String: true
        ]
        if SecItemCopyMatching(oldCaQuery as CFDictionary, &result) == errSecSuccess {
            let updateQuery: [String: Any] = [
                kSecClass as String: kSecClassCertificate,
                kSecAttrLabel as String: legacyCaLabel
            ]
            let updateAttrs: [String: Any] = [
                kSecAttrLabel as String: caLabel
            ]
            SecItemUpdate(updateQuery as CFDictionary, updateAttrs as CFDictionary)
        }
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

        // Extract the identity first. The system trust store should validate the
        // server certificate, so a bundled CA in the P12 is optional.
        guard let identity = firstItem[kSecImportItemIdentity as String] else {
            let msg = "No identity in P12 item"
            importError = msg
            throw CertError.noIdentity(msg)
        }

        let chain = firstItem[kSecImportItemCertChain as String] as? [SecCertificate]
        let caCertificate = (chain?.count ?? 0) > 1 ? chain?.last : nil

        // Store identity in keychain.
        let addIdentityQuery: [String: Any] = [
            kSecClass as String: kSecClassIdentity,
            kSecValueRef as String: identity,
            kSecAttrLabel as String: Self.identityLabel,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]
        let addStatus = SecItemAdd(addIdentityQuery as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            let msg = "Failed to store identity: \(addStatus)"
            importError = msg
            throw CertError.keychainError(msg)
        }

        if let caCertificate {
            let addCAQuery: [String: Any] = [
                kSecClass as String: kSecClassCertificate,
                kSecValueRef as String: caCertificate,
                kSecAttrLabel as String: Self.caLabel,
                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
            ]
            let caStatus = SecItemAdd(addCAQuery as CFDictionary, nil)
            guard caStatus == errSecSuccess else {
                deleteAll()
                let msg = "Failed to store CA certificate: \(caStatus)"
                importError = msg
                throw CertError.keychainError(msg)
            }
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
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess else { return nil }
        return (item as! SecIdentity)
    }

    func loadCACertificate() -> SecCertificate? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecAttrLabel as String: Self.caLabel,
            kSecReturnRef as String: true,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess else { return nil }
        return (item as! SecCertificate)
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
