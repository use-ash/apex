import Foundation
import OSLog
import UIKit

// MARK: - Secure Clipboard

extension UIPasteboard {
    /// Copy a string and auto-clear after `timeout` seconds unless the user has
    /// copied something else in the meantime (checked via `changeCount`).
    func secureCopy(_ string: String, clearAfter timeout: TimeInterval = 30) {
        self.string = string
        let snapshot = self.changeCount
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
            if self.changeCount == snapshot {
                self.string = ""
            }
        }
    }
}

// MARK: - Shared Logger

extension Logger {
    /// Create a logger with the app's bundle subsystem.
    static func app(_ category: String) -> Logger {
        Logger(subsystem: "com.apex.apexchat", category: category)
    }
}

// MARK: - ISO 8601 Date Parsing

enum DateParsing {
    static let iso8601Frac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static let iso8601: ISO8601DateFormatter = ISO8601DateFormatter()

    /// Parse an ISO 8601 string, trying fractional seconds first.
    static func parseISO8601(_ string: String) -> Date? {
        iso8601Frac.date(from: string) ?? iso8601.date(from: string)
    }

    /// Relative time string: "just now", "5m ago", "2h ago", or absolute.
    static func relativeTimeAgo(_ isoString: String) -> String {
        guard let date = parseISO8601(isoString) else { return "" }
        let secs = Date().timeIntervalSince(date)
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(Int(secs / 60))m ago" }
        if secs < 86400 { return "\(Int(secs / 3600))h ago" }
        return DateFormatter.localizedString(from: date, dateStyle: .short, timeStyle: .short)
    }
}
