import Foundation
import OSLog
import Security

final class TLSDelegate: NSObject, URLSessionDelegate {
    private let certificateManager: CertificateManager
    private let logger = Logger(subsystem: "com.apex.apexchat", category: "TLS")

    init(certificateManager: CertificateManager) {
        self.certificateManager = certificateManager
        super.init()
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        let method = challenge.protectionSpace.authenticationMethod
        logger.info("TLS challenge: \(method, privacy: .public) host=\(challenge.protectionSpace.host, privacy: .public)")

        switch method {
        case NSURLAuthenticationMethodClientCertificate:
            // Let iOS present the system-installed client cert from the profile
            completionHandler(.performDefaultHandling, nil)

        case NSURLAuthenticationMethodServerTrust:
            guard let serverTrust = challenge.protectionSpace.serverTrust else {
                completionHandler(.cancelAuthenticationChallenge, nil)
                return
            }

            // We MUST do custom trust evaluation because the server uses a
            // self-signed CA that iOS won't trust via .performDefaultHandling
            // even with the profile installed (app sandbox limitation).
            if let caCert = certificateManager.loadCACertificate() {
                // Pin to our CA only
                SecTrustSetAnchorCertificates(serverTrust, [caCert] as CFArray)
                SecTrustSetAnchorCertificatesOnly(serverTrust, true)
                logger.info("Using app-keychain CA for trust evaluation")
            } else {
                // No CA in app keychain — allow system CAs too
                logger.warning("No CA cert in app keychain, falling back to system trust")
            }

            var error: CFError?
            if SecTrustEvaluateWithError(serverTrust, &error) {
                logger.info("Server trust: PASSED")
                completionHandler(.useCredential, URLCredential(trust: serverTrust))
            } else {
                logger.error("Server trust: FAILED — \(error?.localizedDescription ?? "unknown", privacy: .public)")
                completionHandler(.cancelAuthenticationChallenge, nil)
            }

        default:
            completionHandler(.performDefaultHandling, nil)
        }
    }
}
