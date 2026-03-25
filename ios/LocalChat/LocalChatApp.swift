import SwiftUI

@main
struct LocalChatApp: App {
    @State private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            if appState.isConfigured {
                ContentView(appState: appState)
            } else {
                OnboardingView(appState: appState)
            }
        }
    }
}
