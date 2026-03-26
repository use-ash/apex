import SwiftUI

struct ChannelListView: View {
    @Bindable var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var isCreatingChannel = false

    var body: some View {
        NavigationStack {
            List {
                ForEach(appState.chats) { chat in
                    Button {
                        appState.switchToChat(chat)
                        dismiss()
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(chat.title)
                                    .foregroundStyle(.primary)
                                if chat.type == "alerts" {
                                    Text("Alerts")
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
                }
            }
            .navigationTitle("Channels")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isCreatingChannel = true
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $isCreatingChannel) {
                NewChannelView(appState: appState)
            }
        }
    }
}
