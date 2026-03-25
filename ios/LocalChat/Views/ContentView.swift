import SwiftUI

struct ContentView: View {
    @Bindable var appState: AppState
    @State private var path: [String] = []

    var body: some View {
        NavigationStack(path: $path) {
            List {
                ForEach(appState.chats) { chat in
                    Button {
                        path.append(chat.id)
                    } label: {
                        chatRow(chat)
                    }
                }
            }
            .navigationTitle("LocalChat")
            .navigationDestination(for: String.self) { chatId in
                ChatView(chatId: chatId, appState: appState)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await appState.createChat() }
                    } label: {
                        Image(systemName: "plus")
                    }
                }

                ToolbarItem(placement: .topBarLeading) {
                    connectionIndicator
                }
            }
            .refreshable {
                await appState.loadChats()
            }
            .overlay {
                if appState.chats.isEmpty && !appState.isLoadingChats {
                    ContentUnavailableView {
                        Label("No Chats", systemImage: "bubble.left.and.bubble.right")
                    } description: {
                        Text("Tap + to start a conversation")
                    }
                }
            }
        }
        .task {
            appState.connect()
            await appState.loadChats()
        }
        .onChange(of: appState.selectedChatId) {
            guard let selectedChatId = appState.selectedChatId else { return }
            path = [selectedChatId]
        }
    }

    // MARK: - Chat Row

    private func chatRow(_ chat: Chat) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(chat.title)
                .font(.headline)
                .lineLimit(1)

            Text(formattedDate(chat.updatedAt))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    // MARK: - Connection Indicator

    private var connectionIndicator: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(appState.connectionManager.isConnected ? .green : .red)
                .frame(width: 8, height: 8)

            if let model = appState.connectionManager.serverModel {
                Text(modelDisplayName(model))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Helpers

    private func formattedDate(_ isoString: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        guard let date = formatter.date(from: isoString) else {
            // Try without fractional seconds
            formatter.formatOptions = [.withInternetDateTime]
            guard let date = formatter.date(from: isoString) else { return isoString }
            return RelativeDateTimeFormatter().localizedString(for: date, relativeTo: Date())
        }

        return RelativeDateTimeFormatter().localizedString(for: date, relativeTo: Date())
    }

    private func modelDisplayName(_ model: String) -> String {
        if model.contains("opus") { return "Opus" }
        if model.contains("sonnet") { return "Sonnet" }
        if model.contains("haiku") { return "Haiku" }
        return model
    }
}
