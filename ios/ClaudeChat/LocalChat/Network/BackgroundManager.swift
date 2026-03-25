import BackgroundTasks
import Foundation

enum BackgroundManager {
    static let keepAliveTaskIdentifier = "com.openclaw.localchat.keepalive"

    private static var connectionManager: ConnectionManager?

    static func configure(connectionManager: ConnectionManager) {
        self.connectionManager = connectionManager
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
            task.setTaskCompleted(success: true)
        }
    }
}
