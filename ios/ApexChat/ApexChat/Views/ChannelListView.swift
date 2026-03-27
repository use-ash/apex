import SwiftUI

struct ChannelListView: View {
    @Bindable var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var isCreatingChannel = false
    @State private var renamingChatId: String?
    @State private var renameText = ""
    @State private var pendingDeleteId: String?

    /// Optional callback for drawer mode; when nil, falls back to sheet dismiss.
    var onSelect: (() -> Void)?
    var onShowSearch: (() -> Void)?
    var onShowSettings: (() -> Void)?

    private func close() {
        if let onSelect { onSelect() } else { dismiss() }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(appState.chats) { chat in
                    if renamingChatId == chat.id {
                        HStack {
                            TextField("Chat name", text: $renameText)
                                .textFieldStyle(.roundedBorder)
                                .onSubmit { commitRename(chat) }
                            Button("Save") { commitRename(chat) }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.small)
                            Button("Cancel") { renamingChatId = nil }
                                .controlSize(.small)
                        }
                    } else {
                        Button {
                            appState.switchToChat(chat)
                            close()
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(chat.title)
                                        .foregroundStyle(.primary)
                                    if chat.type == "alerts" {
                                        HStack(spacing: 4) {
                                            Image(systemName: "bell.fill")
                                                .font(.caption2)
                                            Text(alertChannelSubtitle(chat))
                                        }
                                        .font(.caption)
                                        .foregroundStyle(.orange)
                                    } else if let model = chat.model {
                                        Text(AppState.friendlyModelName(model))
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                if appState.persistentChatId == chat.id {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(.blue)
                                }
                            }
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) {
                                pendingDeleteId = chat.id
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                            Button {
                                renameText = chat.title
                                renamingChatId = chat.id
                            } label: {
                                Label("Rename", systemImage: "pencil")
                            }
                            .tint(.blue)
                        }
                    }
                }
            }
            .navigationTitle("Channels")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { close() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isCreatingChannel = true
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                HStack(spacing: 0) {
                    Button {
                        close()
                        onShowSearch?()
                    } label: {
                        VStack(spacing: 4) {
                            Image(systemName: "magnifyingglass")
                            Text("Search")
                                .font(.caption2)
                        }
                        .frame(maxWidth: .infinity)
                    }

                    Button {
                        close()
                        onShowSettings?()
                    } label: {
                        VStack(spacing: 4) {
                            Image(systemName: "gearshape")
                            Text("Settings")
                                .font(.caption2)
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
                .foregroundStyle(.secondary)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial)
                .overlay(alignment: .top) { Divider() }
            }
            .sheet(isPresented: $isCreatingChannel) {
                NewChannelView(appState: appState)
            }
        }
        .onChange(of: pendingDeleteId) {
            guard let id = pendingDeleteId else { return }
            pendingDeleteId = nil
            Task { await appState.deleteChannel(id) }
        }
    }

    private func alertChannelSubtitle(_ chat: Chat) -> String {
        switch chat.category {
        case "trading": return "Trading"
        case "system": return "System"
        case "test": return "Test"
        default: return "All"
        }
    }

    private func commitRename(_ chat: Chat) {
        let newTitle = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !newTitle.isEmpty, newTitle != chat.title else {
            renamingChatId = nil
            return
        }
        renamingChatId = nil
        Task { await appState.renameChannel(chat.id, to: newTitle) }
    }
}
