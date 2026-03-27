import BackgroundTasks
import Foundation
import OSLog
import UserNotifications

/// Manages background alert polling via BGAppRefreshTask + long-poll endpoint.
///
/// Flow:
/// 1. App goes to background → schedules BGAppRefreshTask (25s earliest)
/// 2. iOS wakes the app → we hit GET /api/alerts/wait?since=<last>&timeout=20
/// 3. Server blocks up to 20s, returns immediately on new alert
/// 4. We fire local notifications for each new alert
/// 5. Re-schedule the task for immediate re-poll
enum BackgroundManager {
    static let keepAliveTaskIdentifier = "com.openclaw.localchat.keepalive"
    private static let logger = Logger(subsystem: "com.openclaw.localchat", category: "Background")

    private static var connectionManager: ConnectionManager?
    private static var apiClient: APIClient?

    static func configure(connectionManager: ConnectionManager, apiClient: APIClient) {
        self.connectionManager = connectionManager
        self.apiClient = apiClient
    }

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: keepAliveTaskIdentifier, using: nil) { task in
            guard let refreshTask = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            handleKeepAlive(task: refreshTask)
        }
    }

    static func scheduleKeepAlive() {
        let request = BGAppRefreshTaskRequest(identifier: keepAliveTaskIdentifier)
        // Ask iOS to run again ASAP (iOS may delay, but with background fetch enabled it's better)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 5)

        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: keepAliveTaskIdentifier)

        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            logger.error("BGTask submit error: \(error.localizedDescription, privacy: .public)")
        }
    }

    static func handleKeepAlive(task: BGAppRefreshTask) {
        // Immediately schedule next run so we keep polling
        scheduleKeepAlive()

        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }

        // Ping WS to keep connection alive
        DispatchQueue.main.async {
            connectionManager?.sendBackgroundPing()
        }

        // Long-poll for new alerts
        Task {
            guard let client = apiClient else {
                task.setTaskCompleted(success: true)
                return
            }
            do {
                let lastTimestamp = UserDefaults.standard.string(forKey: "lastAlertTimestamp")
                let since = (lastTimestamp?.isEmpty ?? true) ? nil : lastTimestamp

                // Hit the long-poll endpoint — server blocks up to 20s if no new alerts
                let alerts = try await client.fetchAlertsLongPoll(since: since, timeout: 20)

                for alert in alerts {
                    let content = UNMutableNotificationContent()
                    content.title = "[\(alert.severity.uppercased())] \(alert.source)"
                    content.body = alert.title
                    content.sound = alert.severity == "critical" ? .defaultCritical : .default
                    content.categoryIdentifier = "ALERT"
                    content.userInfo = ["alert_id": alert.id]
                    content.interruptionLevel = alert.severity == "critical" ? .critical : .timeSensitive

                    let request = UNNotificationRequest(
                        identifier: "alert-\(alert.id)",
                        content: content,
                        trigger: nil
                    )
                    try? await UNUserNotificationCenter.current().add(request)
                }

                if let newest = alerts.first {
                    UserDefaults.standard.set(newest.createdAt, forKey: "lastAlertTimestamp")
                }
            } catch {
                // Silent fail — will retry on next BGTask
            }
            task.setTaskCompleted(success: true)
        }
    }
}
