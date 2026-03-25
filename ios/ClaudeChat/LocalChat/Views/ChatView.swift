import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct ChatView: View {
    private static let imageExtensions = ["jpg", "jpeg", "png", "gif", "webp"]
    private static let textExtensions = ["txt", "py", "json", "csv", "md", "yaml", "yml", "toml", "cfg", "ini", "log", "html", "css", "js", "ts", "sh"]
    private static let maxImageSize = 10 * 1024 * 1024
    private static let maxTextSize = 1 * 1024 * 1024

    let chatId: String
    @Bindable var appState: AppState
    var highlightedMessageIDs: Set<String> = []

    @State private var inputText: String = ""
    @State private var isStreaming: Bool = false
    @State private var streamingText: String = ""
    @State private var streamingThinking: String = ""
    @State private var streamingToolEvents: [StreamingToolEvent] = []
    @State private var streamingTimeoutToken: UUID?
    @State private var pendingAttachments: [PendingAttachment] = []
    @State private var selectedPhotoItems: [PhotosPickerItem] = []
    @State private var isShowingPhotoPicker: Bool = false
    @State private var isShowingFileImporter: Bool = false
    @State private var isUploadingAttachments: Bool = false
    @State private var reactions: [String: String] = [:]
    @State private var replyingToMessage: Message?
    @FocusState private var isInputFocused: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(appState.messages) { message in
                        MessageBubble(
                            message: message,
                            isHighlighted: highlightedMessageIDs.contains(message.id),
                            reaction: reactions[message.id],
                            onReact: { emoji in
                                updateReaction(emoji, for: message)
                            },
                            onReply: {
                                setReplyTarget(message)
                            }
                        )
                        .id(message.id)
                    }

                    if isStreaming {
                        streamingBubble
                            .id("streaming")
                    }
                }
                .padding(.vertical, 8)
            }
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom) {
                composeBar
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
            .onChange(of: streamingToolEvents) {
                scrollToBottom(proxy: proxy)
            }
            .onChange(of: isInputFocused) { _, focused in
                if focused {
                    scrollToBottom(proxy: proxy)
                }
            }
            .onAppear {
                scrollToBottom(proxy: proxy)
            }
        }
        .photosPicker(
            isPresented: $isShowingPhotoPicker,
            selection: $selectedPhotoItems,
            maxSelectionCount: nil,
            matching: .images,
            preferredItemEncoding: .current
        )
        .fileImporter(
            isPresented: $isShowingFileImporter,
            allowedContentTypes: [.data],
            allowsMultipleSelection: true,
            onCompletion: handleImportedFiles
        )
        .onChange(of: selectedPhotoItems) { _, newItems in
            guard !newItems.isEmpty else { return }
            Task {
                await importPhotoItems(newItems)
                await MainActor.run {
                    selectedPhotoItems = []
                }
            }
        }
        .onAppear {
            appState.streamMessageHandler = handleStreamMessage
        }
        .onDisappear {
            appState.streamMessageHandler = nil
        }
    }

    // MARK: - Streaming Bubble

    private var streamingBubble: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                if !streamingThinking.isEmpty {
                    ThinkingDisclosureView(text: streamingThinking, showsActivity: isStreaming)
                }

                if !streamingToolEvents.isEmpty {
                    ToolEventListView(
                        events: streamingToolEvents.map {
                            ToolEventDisplayItem(
                                id: $0.id,
                                name: $0.name,
                                input: $0.input,
                                result: $0.result,
                                isError: $0.isError,
                                isComplete: $0.isComplete
                            )
                        }
                    )
                }

                if streamingText.isEmpty && streamingThinking.isEmpty && streamingToolEvents.isEmpty {
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
        VStack(spacing: 8) {
            if let replyingToMessage {
                replyPreview(for: replyingToMessage)
            }

            if !pendingAttachments.isEmpty {
                attachmentPreview
            }

            HStack(spacing: 8) {
                Menu {
                    Button {
                        isShowingPhotoPicker = true
                    } label: {
                        Label("Photo Library", systemImage: "photo.on.rectangle")
                    }

                    Button {
                        isShowingFileImporter = true
                    } label: {
                        Label("Choose File", systemImage: "doc")
                    }
                } label: {
                    Image(systemName: "plus")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(.primary)
                        .frame(width: 34, height: 34)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(Circle())
                }
                .disabled(isStreaming || isUploadingAttachments)

                TextField("Message", text: $inputText, axis: .vertical)
                    .focused($isInputFocused)
                    .lineLimit(1...5)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .submitLabel(.send)
                    .onSubmit {
                        Task {
                            await sendMessage()
                        }
                    }

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
                } else if isUploadingAttachments {
                    ProgressView()
                        .frame(width: 32, height: 32)
                        .background(Color.gray.opacity(0.2))
                        .clipShape(Circle())
                } else {
                    Button {
                        Task {
                            await sendMessage()
                        }
                    } label: {
                        Image(systemName: "arrow.up")
                            .foregroundStyle(.white)
                            .frame(width: 32, height: 32)
                            .background(canSendMessage ? Color.blue : Color.gray)
                            .clipShape(Circle())
                    }
                    .disabled(!canSendMessage)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 8)
        .background(.regularMaterial)
        .overlay(alignment: .top) { Divider() }
    }

    private func replyPreview(for message: Message) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "arrowshape.turn.up.left.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.blue)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 2) {
                Text("Replying to \(message.isUser ? "you" : "assistant")")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(replyPreviewText(for: message))
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
            }

            Spacer(minLength: 8)

            Button {
                replyingToMessage = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color(.tertiarySystemFill))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 18))
    }

    private var attachmentPreview: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(pendingAttachments) { attachment in
                    attachmentChip(for: attachment)
                }
            }
            .padding(.horizontal, 12)
        }
    }

    private func attachmentChip(for attachment: PendingAttachment) -> some View {
        HStack(spacing: 8) {
            previewContent(for: attachment)

            Text(attachment.filename)
                .font(.footnote)
                .lineLimit(1)

            Button {
                removeAttachment(attachment)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color(.secondarySystemBackground))
        .clipShape(Capsule())
    }

    @ViewBuilder
    private func previewContent(for attachment: PendingAttachment) -> some View {
        switch attachment.kind {
        case .image:
            if let image = UIImage(data: attachment.data) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 28, height: 28)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            } else {
                Image(systemName: "photo")
                    .foregroundStyle(.secondary)
            }
        case .text:
            Image(systemName: "doc.text")
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Send

    @MainActor
    private func sendMessage() async {
        let prompt = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !isUploadingAttachments else { return }
        guard !prompt.isEmpty || !pendingAttachments.isEmpty || replyingToMessage != nil else { return }
        guard appState.connectionManager.isConnected else {
            appState.error = "Connect to the server before sending a message."
            return
        }

        isUploadingAttachments = true
        isInputFocused = false

        let attachmentsToUpload = pendingAttachments
        let replyTarget = replyingToMessage
        let composedPrompt = outgoingPrompt(basePrompt: prompt, replyTo: replyTarget)

        do {
            let uploadedAttachments = try await uploadPendingAttachments(attachmentsToUpload)
            let userMessage = Message(
                id: UUID().uuidString,
                role: "user",
                content: localUserMessageContent(prompt: composedPrompt, attachments: attachmentsToUpload),
                toolEvents: "[]",
                thinking: "",
                costUsd: 0,
                tokensIn: 0,
                tokensOut: 0,
                createdAt: ISO8601DateFormatter().string(from: Date())
            )

            inputText = ""
            pendingAttachments = []
            replyingToMessage = nil
            appState.messages.append(userMessage)

            isStreaming = true
            streamingText = ""
            streamingThinking = ""
            streamingToolEvents = []
            armStreamingTimeout()

            appState.connectionManager.send(
                .send(chatId: chatId, prompt: composedPrompt, attachments: uploadedAttachments.isEmpty ? nil : uploadedAttachments)
            )
        } catch {
            appState.error = error.localizedDescription
        }

        isUploadingAttachments = false
    }

    private var canSendMessage: Bool {
        (!inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !pendingAttachments.isEmpty || replyingToMessage != nil) &&
        appState.connectionManager.isConnected &&
        !isUploadingAttachments
    }

    private func localUserMessageContent(prompt: String, attachments: [PendingAttachment]) -> String {
        let summary = attachments.isEmpty
            ? ""
            : "Attachments: \(attachments.map(\.filename).joined(separator: ", "))"
        let combined = [prompt, summary]
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
        return combined.isEmpty ? "(attachment)" : combined
    }

    private func outgoingPrompt(basePrompt: String, replyTo: Message?) -> String {
        guard let replyTo else { return basePrompt }

        let quote = quotedReplyText(for: replyTo)
        return [quote, basePrompt]
            .filter { !$0.isEmpty }
            .joined(separator: "\n\n")
    }

    private func quotedReplyText(for message: Message) -> String {
        let trimmed = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
        let excerpt = String(trimmed.prefix(200))
        let normalized = excerpt.replacingOccurrences(of: "\r\n", with: "\n")
        return normalized
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { "> \($0)" }
            .joined(separator: "\n")
    }

    private func replyPreviewText(for message: Message) -> String {
        let collapsed = message.content
            .replacingOccurrences(of: "\r\n", with: "\n")
            .split(whereSeparator: \.isNewline)
            .joined(separator: " ")
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let excerpt = String(collapsed.prefix(50))
        return collapsed.count > 50 ? "\(excerpt)..." : excerpt
    }

    private func uploadPendingAttachments(_ attachments: [PendingAttachment]) async throws -> [[String: String]] {
        var uploaded: [[String: String]] = []
        for attachment in attachments {
            let response = try await appState.apiClient.uploadFile(
                data: attachment.data,
                filename: attachment.filename
            )
            uploaded.append([
                "id": response.id,
                "type": response.type,
                "name": response.name,
            ])
        }
        return uploaded
    }

    // MARK: - Attachment Import

    private func handleImportedFiles(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard !urls.isEmpty else { return }
            Task {
                for url in urls {
                    do {
                        let attachment = try loadAttachment(from: url)
                        await MainActor.run {
                            pendingAttachments.append(attachment)
                        }
                    } catch {
                        await MainActor.run {
                            appState.error = error.localizedDescription
                        }
                    }
                }
            }
        case .failure(let error):
            appState.error = error.localizedDescription
        }
    }

    private func importPhotoItems(_ items: [PhotosPickerItem]) async {
        for (index, item) in items.enumerated() {
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    continue
                }
                let attachment = try makeAttachment(
                    data: data,
                    filename: generatedPhotoFilename(for: item, index: index)
                )
                await MainActor.run {
                    pendingAttachments.append(attachment)
                }
            } catch {
                await MainActor.run {
                    appState.error = error.localizedDescription
                }
            }
        }
    }

    private func loadAttachment(from url: URL) throws -> PendingAttachment {
        let accessing = url.startAccessingSecurityScopedResource()
        defer {
            if accessing {
                url.stopAccessingSecurityScopedResource()
            }
        }
        let data = try Data(contentsOf: url)
        return try makeAttachment(data: data, filename: url.lastPathComponent)
    }

    private func generatedPhotoFilename(for item: PhotosPickerItem, index: Int) -> String {
        let ext = item.supportedContentTypes
            .first(where: { $0.conforms(to: .image) })?
            .preferredFilenameExtension ?? "jpg"
        return "photo-\(ProcessInfo.processInfo.globallyUniqueString)-\(index).\(ext)"
    }

    private func makeAttachment(data: Data, filename: String) throws -> PendingAttachment {
        let cleanFilename = filename.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedFilename = cleanFilename.isEmpty ? "attachment" : cleanFilename
        let ext = URL(fileURLWithPath: resolvedFilename).pathExtension.lowercased()

        guard !ext.isEmpty else {
            throw AttachmentValidationError.missingExtension
        }

        if Self.imageExtensions.contains(ext) {
            guard data.count <= Self.maxImageSize else {
                throw AttachmentValidationError.fileTooLarge(
                    limit: Self.maxImageSize,
                    kind: "image"
                )
            }
            return PendingAttachment(filename: resolvedFilename, data: data, kind: .image)
        }

        if Self.textExtensions.contains(ext) {
            guard data.count <= Self.maxTextSize else {
                throw AttachmentValidationError.fileTooLarge(
                    limit: Self.maxTextSize,
                    kind: "file"
                )
            }
            return PendingAttachment(filename: resolvedFilename, data: data, kind: .text)
        }

        throw AttachmentValidationError.unsupportedExtension(ext)
    }

    private func removeAttachment(_ attachment: PendingAttachment) {
        pendingAttachments.removeAll { $0.id == attachment.id }
    }

    private func updateReaction(_ emoji: String?, for message: Message) {
        guard let emoji else {
            reactions.removeValue(forKey: message.id)
            return
        }

        if reactions[message.id] == emoji {
            reactions.removeValue(forKey: message.id)
        } else {
            reactions[message.id] = emoji
        }
    }

    private func setReplyTarget(_ message: Message) {
        replyingToMessage = message
        isInputFocused = true
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

    private func armStreamingTimeout() {
        let token = UUID()
        streamingTimeoutToken = token

        Task {
            try? await Task.sleep(for: .seconds(120))
            await MainActor.run {
                guard streamingTimeoutToken == token, isStreaming else { return }
                resetStreamingState()
            }
        }
    }

    private func resetStreamingState() {
        streamingTimeoutToken = nil
        isStreaming = false
        streamingText = ""
        streamingThinking = ""
        streamingToolEvents = []
    }

    // MARK: - Message Handler

    private func handleStreamMessage(_ message: ServerMessage) {
        switch message {
        case .streamStart(let streamChatId):
            guard streamChatId == chatId else { break }
            isStreaming = true
            streamingText = ""
            streamingThinking = ""
            streamingToolEvents = []
        case .text(let text):
            streamingText += text
        case .thinking(let text):
            streamingThinking += text
        case .toolUse(let id, let name, let input):
            streamingToolEvents.append(
                StreamingToolEvent(
                    id: id,
                    name: name,
                    input: compactToolInputDescription(name: name, input: input),
                    result: nil,
                    isError: false,
                    isComplete: false
                )
            )
        case .toolResult(let toolUseId, let content, let isError):
            guard let index = streamingToolEvents.firstIndex(where: { $0.id == toolUseId }) else { break }
            streamingToolEvents[index].result = content
            streamingToolEvents[index].isError = isError
            streamingToolEvents[index].isComplete = true
        case .result:
            resetStreamingState()
            Task {
                await appState.loadMessages(chatId)
                await appState.refreshPersistentChat()
            }
        case .streamEnd(let streamChatId):
            guard streamChatId == chatId else { break }
            resetStreamingState()
        case .attachOk(let streamChatId):
            guard streamChatId == chatId else { break }
            resetStreamingState()
        case .streamCompleteReload(let streamChatId):
            guard streamChatId == chatId else { break }
            resetStreamingState()
            Task {
                await appState.loadMessages(chatId)
                await appState.refreshPersistentChat()
            }
        case .error(let msg):
            resetStreamingState()
            appState.error = msg
            Task {
                await appState.loadMessages(chatId)
            }
        default:
            break
        }
    }
}

private struct StreamingToolEvent: Identifiable, Equatable {
    let id: String
    let name: String
    let input: String
    var result: String?
    var isError: Bool
    var isComplete: Bool
}

private struct PendingAttachment: Identifiable {
    enum Kind {
        case image
        case text
    }

    let id = UUID()
    let filename: String
    let data: Data
    let kind: Kind
}

private enum AttachmentValidationError: LocalizedError {
    case missingExtension
    case unsupportedExtension(String)
    case fileTooLarge(limit: Int, kind: String)

    var errorDescription: String? {
        switch self {
        case .missingExtension:
            return "Attachments need a file extension."
        case .unsupportedExtension(let ext):
            return "Unsupported attachment type: .\(ext)"
        case .fileTooLarge(let limit, let kind):
            return "\(kind.capitalized) exceeds the \(ByteCountFormatter.string(fromByteCount: Int64(limit), countStyle: .file)) limit."
        }
    }
}
