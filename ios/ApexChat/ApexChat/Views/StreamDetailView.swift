import SwiftUI

protocol StreamDetailToolEventRepresentable {
    var streamDetailID: String { get }
    var streamDetailName: String { get }
    var streamDetailInput: String { get }
    var streamDetailResult: String? { get }
    var streamDetailIsError: Bool { get }
    var streamDetailIsComplete: Bool { get }
}

extension ToolEventDisplayItem: StreamDetailToolEventRepresentable {
    var streamDetailID: String { id }
    var streamDetailName: String { name }
    var streamDetailInput: String { fullInput }
    var streamDetailResult: String? { result }
    var streamDetailIsError: Bool { isError }
    var streamDetailIsComplete: Bool { isComplete }
}

struct StreamDetailView<ToolEvent: StreamDetailToolEventRepresentable>: View {
    let thinking: String
    let toolEvents: [ToolEvent]
    let isStreaming: Bool

    @Environment(\.dismiss) private var dismiss
    @State private var isNearBottom: Bool = true

    private let bottomAnchorID = "stream-detail-bottom"
    private let topAnchorID = "stream-detail-top"

    private var displayEvents: [DisplayToolEvent] {
        toolEvents.map {
            DisplayToolEvent(
                id: $0.streamDetailID,
                name: $0.streamDetailName,
                input: $0.streamDetailInput,
                result: $0.streamDetailResult,
                isError: $0.streamDetailIsError,
                isComplete: $0.streamDetailIsComplete
            )
        }
    }

    private var activitySignature: Int {
        thinking.count + toolEvents.count * 1000 + (toolEvents.last?.streamDetailIsComplete == true ? 1 : 0)
    }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Color.clear
                            .frame(height: 1)
                            .id(topAnchorID)

                        if !thinking.isEmpty {
                            thinkingSection
                        }

                        if !displayEvents.isEmpty {
                            toolEventsSection
                        }

                        if thinking.isEmpty && displayEvents.isEmpty {
                            emptyState
                        }

                        // Bottom anchor — track visibility to know if user scrolled up
                        GeometryReader { geo in
                            Color.clear
                                .preference(
                                    key: BottomVisiblePreferenceKey.self,
                                    value: geo.frame(in: .named("detailScroll")).maxY
                                )
                        }
                        .frame(height: 1)
                        .id(bottomAnchorID)
                    }
                    .padding(16)
                }
                .coordinateSpace(name: "detailScroll")
                .onPreferenceChange(BottomVisiblePreferenceKey.self) { maxY in
                    // If bottom anchor is within 150pt of the visible area, user is "near bottom"
                    isNearBottom = maxY < 900
                }
                
                .background(Color(.systemGroupedBackground))
                .navigationTitle(isStreaming ? "Live Details" : "Response Details")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "xmark")
                        }
                    }
                    // Show "Jump to bottom" button when scrolled up during streaming
                    if isStreaming && !isNearBottom {
                        ToolbarItem(placement: .bottomBar) {
                            Button {
                                scrollToBottom(proxy, animated: true)
                            } label: {
                                Label("Jump to latest", systemImage: "arrow.down.circle.fill")
                                    .font(.caption.weight(.semibold))
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                        }
                    }
                }
                .onAppear {
                    if isStreaming {
                        scrollToBottom(proxy, animated: false)
                    }
                }
                .onChange(of: activitySignature) { _, _ in
                    guard isStreaming, isNearBottom else { return }
                    scrollToBottom(proxy, animated: true)
                }
            }
        }
    }

    private var thinkingSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Text("🧠")
                    .font(.title3)
                Text("Thinking")
                    .font(.headline)
                if isStreaming {
                    ProgressView()
                        .controlSize(.small)
                }
            }

            Text(thinking)
                .font(.system(.subheadline, design: .monospaced))
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var toolEventsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Text("🔧")
                    .font(.title3)
                Text("Tools")
                    .font(.headline)
                Text("(\(displayEvents.filter(\.isComplete).count)/\(displayEvents.count))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 12) {
                ForEach(displayEvents) { event in
                    StreamDetailToolCard(event: event)
                }
            }
        }
    }

    private var emptyState: some View {
        ContentUnavailableView(
            isStreaming ? "Waiting for activity" : "No details available",
            systemImage: "ellipsis.bubble",
            description: Text(isStreaming ? "Thinking and tool activity will appear here as it streams." : "This message has no thinking or tool activity.")
        )
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy, animated: Bool) {
        let action = {
            proxy.scrollTo(bottomAnchorID, anchor: .bottom)
        }
        if animated {
            withAnimation(.easeOut(duration: 0.2)) {
                action()
            }
        } else {
            action()
        }
    }
}

private struct DisplayToolEvent: Identifiable, Equatable {
    let id: String
    let name: String
    let input: String
    let result: String?
    let isError: Bool
    let isComplete: Bool

    var resultText: String {
        result?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}

private struct StreamDetailToolCard: View {
    let event: DisplayToolEvent
    let cachedSmartInput: String

    init(event: DisplayToolEvent) {
        self.event = event
        self.cachedSmartInput = Self.parseSmartInput(event)
    }

    private var toolEmoji: String {
        switch event.name.lowercased() {
        case "bash", "run", "command": return "💻"
        case "read", "read_file": return "📖"
        case "write", "edit", "write_file": return "✏️"
        case "glob", "list_files": return "📁"
        case "grep", "search", "search_files": return "🔍"
        case "agent": return "🤖"
        case "webfetch": return "🌐"
        case "websearch": return "🔎"
        case "skill": return "⚡"
        default: return "🔧"
        }
    }

    private static func parseSmartInput(_ event: DisplayToolEvent) -> String {
        let raw = event.input
        if raw.isEmpty { return "" }

        if raw.hasPrefix("{") {
            if let data = raw.data(using: .utf8),
               let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let name = event.name.lowercased()
                if name.contains("bash") || name.contains("command"),
                   let cmd = dict["command"] as? String {
                    return cmd
                }
                if name.contains("read") || name.contains("write") || name.contains("edit"),
                   let path = dict["file_path"] as? String ?? dict["path"] as? String {
                    return path
                }
                if name.contains("grep") || name.contains("search"),
                   let pattern = dict["pattern"] as? String {
                    let path = dict["path"] as? String
                    return path != nil ? "\"\(pattern)\" in \(path!)" : "\"\(pattern)\""
                }
                if name.contains("glob"),
                   let pattern = dict["pattern"] as? String {
                    return pattern
                }
                if let desc = dict["description"] as? String {
                    return desc
                }
            }
        }
        return raw
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header row
            HStack(alignment: .center, spacing: 10) {
                Text(toolEmoji)
                    .font(.title2)

                VStack(alignment: .leading, spacing: 2) {
                    Text(humanReadableToolName(event.name))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                    statusBadge
                }

                Spacer(minLength: 8)

                statusIcon
            }

            // Smart input summary
            if !cachedSmartInput.isEmpty {
                Text(cachedSmartInput)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.primary.opacity(0.8))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color(.systemBackground).opacity(0.6))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .textSelection(.enabled)
            }

            // Result
            if event.isComplete {
                if !event.resultText.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(event.isError ? "❌ Error" : "✅ Result")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(event.isError ? .red : .green)
                        Text(event.resultText)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.primary.opacity(0.8))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                            .background(Color(.systemBackground).opacity(0.6))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .textSelection(.enabled)
                    }
                }
            } else {
                HStack(spacing: 6) {
                    ProgressView()
                        .controlSize(.mini)
                    Text("Waiting for result...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private var statusBadge: some View {
        if !event.isComplete {
            Text("⏳ Running")
                .font(.caption2.weight(.medium))
                .foregroundStyle(.orange)
        } else if event.isError {
            Text("❌ Failed")
                .font(.caption2.weight(.medium))
                .foregroundStyle(.red)
        } else {
            Text("✅ Done")
                .font(.caption2.weight(.medium))
                .foregroundStyle(.green)
        }
    }

    @ViewBuilder
    private var statusIcon: some View {
        if !event.isComplete {
            ProgressView()
                .controlSize(.small)
        } else {
            Image(systemName: event.isError ? "xmark.circle.fill" : "checkmark.circle.fill")
                .font(.title3)
                .foregroundStyle(event.isError ? .red : .green)
        }
    }
}

private struct BottomVisiblePreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

