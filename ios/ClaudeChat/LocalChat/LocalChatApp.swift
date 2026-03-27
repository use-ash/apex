import BackgroundTasks
import OSLog
import SwiftUI
import UserNotifications

@main
struct LocalChatApp: App {
    @AppStorage("did_request_notification_permission") private var didRequestNotificationPermission = false
    @Environment(\.scenePhase) private var scenePhase
    @State private var appState = AppState()

    init() {
        BackgroundManager.register()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.isConfigured {
                    ContentView(appState: appState)
                } else {
                    OnboardingView(appState: appState)
                }
            }
            .task(id: appState.isConfigured) {
                guard appState.isConfigured else {
                    appState.disconnect()
                    return
                }

                appState.connect()
                await appState.ensurePersistentChat()
            }
            .task {
                BackgroundManager.configure(connectionManager: appState.connectionManager, apiClient: appState.apiClient)
                await requestNotificationAuthorizationIfNeeded()
                registerNotificationCategories()
            }
            .onChange(of: scenePhase) { _, newPhase in
                appState.scenePhase = newPhase

                guard appState.isConfigured else { return }

                switch newPhase {
                case .active:
                    appState.connectionManager.ensureConnected()
                    if let chatId = appState.persistentChatId {
                        appState.connectionManager.send(.attach(chatId: chatId))
                    }
                    Task { await appState.loadAlerts() }
                    Task { await appState.loadLocalModels() }
                    Task { await appState.loadChats() }
                case .background:
                    BackgroundManager.scheduleKeepAlive()
                case .inactive:
                    break
                @unknown default:
                    break
                }
            }
        }
    }

    private func requestNotificationAuthorizationIfNeeded() async {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        if settings.authorizationStatus == .notDetermined {
            do {
                try await center.requestAuthorization(options: [.alert, .sound, .badge])
            } catch {
                Logger(subsystem: "com.openclaw.localchat", category: "App").error("Notification auth error: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    private func registerNotificationCategories() {
        let ackAction = UNNotificationAction(
            identifier: "ACK_ALERT",
            title: "Acknowledge",
            options: []
        )
        let alertCategory = UNNotificationCategory(
            identifier: "ALERT",
            actions: [ackAction],
            intentIdentifiers: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([alertCategory])
    }
}
