import Foundation
import Security

class TLSDelegate: NSObject, URLSessionDelegate {
    private let certificateManager: CertificateManager

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

        switch method {
        case NSURLAuthenticationMethodClientCertificate:
            // Present client certificate
            guard let identity = certificateManager.loadIdentity() else {
                completionHandler(.cancelAuthenticationChallenge, nil)
                return
            }
            let credential = URLCredential(
                identity: identity,
                certificates: nil,
                persistence: .forSession
            )
            completionHandler(.useCredential, credential)

        case NSURLAuthenticationMethodServerTrust:
            // Validate server certificate against our local CA
            guard let serverTrust = challenge.protectionSpace.serverTrust else {
                completionHandler(.cancelAuthenticationChallenge, nil)
                return
            }

            // If we have a CA cert, pin to it exclusively
            if let caCert = certificateManager.loadCACertificate() {
                SecTrustSetAnchorCertificates(serverTrust, [caCert] as CFArray)
                SecTrustSetAnchorCertificatesOnly(serverTrust, true)
            }

            var error: CFError?
            let trusted = SecTrustEvaluateWithError(serverTrust, &error)

            if trusted {
                let credential = URLCredential(trust: serverTrust)
                completionHandler(.useCredential, credential)
            } else {
                print("TLS: Server trust evaluation failed: \(error?.localizedDescription ?? "unknown")")
                completionHandler(.cancelAuthenticationChallenge, nil)
            }

        default:
            completionHandler(.performDefaultHandling, nil)
        }
    }
}
