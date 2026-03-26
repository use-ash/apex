import BackgroundTasks
import Foundation
import UserNotifications

enum BackgroundManager {
    static let keepAliveTaskIdentifier = "com.openclaw.localchat.keepalive"

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
        request.earliestBeginDate = Date(timeIntervalSinceNow: 25)

        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: keepAliveTaskIdentifier)

        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("BGTask submit error: \(error)")
        }
    }

    static func handleKeepAlive(task: BGAppRefreshTask) {
        scheduleKeepAlive()

        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }

        DispatchQueue.main.async {
            connectionManager?.sendBackgroundPing()
        }

        // Poll for new alerts
        Task {
            guard let client = apiClient else {
                task.setTaskCompleted(success: true)
                return
            }
            do {
                let lastTimestamp = UserDefaults.standard.string(forKey: "lastAlertTimestamp")
                let since = (lastTimestamp?.isEmpty ?? true) ? nil : lastTimestamp
                let alerts = try await client.fetchAlerts(since: since, unackedOnly: true)
                for alert in alerts {
                    let content = UNMutableNotificationContent()
                    content.title = "[\(alert.severity.uppercased())] \(alert.source)"
                    content.body = alert.title
                    content.sound = alert.severity == "critical" ? .defaultCritical : .default
                    content.categoryIdentifier = "ALERT"
                    content.userInfo = ["alert_id": alert.id]
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
                // Silent fail -- supplementary
            }
            task.setTaskCompleted(success: true)
        }
    }
}
