import SwiftUI

struct ChatView: View {
    let chatId: String
    @Bindable var appState: AppState

    @State private var inputText: String = ""
    @State private var isStreaming: Bool = false
    @State private var streamingText: String = ""
    @State private var streamingThinking: String = ""

    var body: some View {
        VStack(spacing: 0) {
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(appState.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }

                        if isStreaming {
                            streamingBubble
                                .id("streaming")
                        }
                    }
                    .padding(.vertical, 8)
                }
                .onChange(of: appState.messages.count) {
                    scrollToBottom(proxy: proxy)
                }
                .onChange(of: streamingText) {
                    scrollToBottom(proxy: proxy)
                }
                .onChange(of: streamingThinking) {
                    scrollToBottom(proxy: proxy)
                }
                .onAppear {
                    scrollToBottom(proxy: proxy)
                }
            }

            // Compose bar
            composeBar
        }
        .navigationTitle(chatTitle)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: chatId) {
            if appState.selectedChatId != chatId {
                await appState.selectChat(chatId)
            }
        }
        .onAppear {
            appState.streamMessageHandler = handleStreamMessage
        }
        .onDisappear {
            appState.streamMessageHandler = nil
        }
    }

    // MARK: - Chat Title

    private var chatTitle: String {
        appState.selectedChat?.title ?? "Chat"
    }

    // MARK: - Streaming Bubble

    private var streamingBubble: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                if !streamingThinking.isEmpty {
                    DisclosureGroup {
                        Text(streamingThinking)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    } label: {
                        Label("Thinking...", systemImage: "brain")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.tertiary.opacity(0.3))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }

                if streamingText.isEmpty && streamingThinking.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if !streamingText.isEmpty {
                    Text(streamingText)
                        .font(.subheadline)
                        .foregroundStyle(.primary)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color(.systemGray5))
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .frame(maxWidth: UIScreen.main.bounds.width * 0.75, alignment: .leading)

            Spacer(minLength: 60)
        }
        .padding(.horizontal, 12)
    }

    // MARK: - Compose Bar

    private var composeBar: some View {
        HStack(spacing: 8) {
            TextField("Message", text: $inputText, axis: .vertical)
                .lineLimit(1...5)
                .textFieldStyle(.plain)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .submitLabel(.send)
                .onSubmit { sendMessage() }

            if isStreaming {
                Button {
                    appState.connectionManager.send(.stop(chatId: chatId))
                } label: {
                    Image(systemName: "stop.fill")
                        .foregroundStyle(.white)
                        .frame(width: 32, height: 32)
                        .background(.red)
                        .clipShape(Circle())
                }
            } else {
                Button(action: sendMessage) {
                    Image(systemName: "arrow.up")
                        .foregroundStyle(.white)
                        .frame(width: 32, height: 32)
                        .background(canSendMessage ? Color.blue : Color.gray)
                        .clipShape(Circle())
                }
                .disabled(!canSendMessage)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.regularMaterial)
        .overlay(alignment: .top) { Divider() }
    }

    // MARK: - Send

    private func sendMessage() {
        let prompt = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return }
        guard appState.connectionManager.isConnected else {
            appState.error = "Connect to the server before sending a message."
            return
        }

        // Optimistic local insert
        let userMessage = Message(
            id: UUID().uuidString,
            role: "user",
            content: prompt,
            toolEvents: "[]",
            thinking: "",
            costUsd: 0,
            tokensIn: 0,
            tokensOut: 0,
            createdAt: ISO8601DateFormatter().string(from: Date())
        )
        appState.messages.append(userMessage)

        inputText = ""
        isStreaming = true
        streamingText = ""
        streamingThinking = ""

        appState.connectionManager.send(.send(chatId: chatId, prompt: prompt))
    }

    private var canSendMessage: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        appState.connectionManager.isConnected
    }

    // MARK: - Scroll

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if isStreaming {
            withAnimation(.easeOut(duration: 0.2)) {
                proxy.scrollTo("streaming", anchor: .bottom)
            }
        } else if let lastId = appState.messages.last?.id {
            withAnimation(.easeOut(duration: 0.2)) {
                proxy.scrollTo(lastId, anchor: .bottom)
            }
        }
    }

    // MARK: - Message Handler

    private func handleStreamMessage(_ message: ServerMessage) {
        switch message {
        case .streamStart(let streamChatId):
            guard streamChatId == chatId else { break }
            isStreaming = true
            streamingText = ""
            streamingThinking = ""
        case .text(let text):
            streamingText += text
        case .thinking(let text):
            streamingThinking += text
        case .result:
            isStreaming = false
            streamingText = ""
            streamingThinking = ""
            Task {
                await appState.loadMessages(chatId)
                await appState.loadChats()
            }
        case .streamEnd(let streamChatId):
            guard streamChatId == chatId else { break }
            if !isStreaming { break }
            isStreaming = false
            streamingText = ""
            streamingThinking = ""
        case .error(let msg):
            isStreaming = false
            streamingText = ""
            streamingThinking = ""
            appState.error = msg
            Task {
                await appState.loadMessages(chatId)
            }
        default:
            break
        }
    }
}
