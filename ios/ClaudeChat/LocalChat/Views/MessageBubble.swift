import Foundation
import SwiftUI
import UIKit

struct MessageBubble: View {
    private static let reactionOptions = ["👍", "❤️", "😂", "😮", "😢", "🔥"]

    let message: Message
    var isHighlighted: Bool = false
    var reaction: String?
    var onReact: ((String?) -> Void)?
    var onReply: (() -> Void)?

    private var parsedToolEvents: [ToolEventDisplayItem] {
        parseSavedToolEventItems(from: message.toolEvents)
    }

    var body: some View {
        VStack(alignment: message.isUser ? .trailing : .leading, spacing: 8) {
            HStack {
                if message.isUser { Spacer(minLength: 60) }

                bubbleContent

                if message.isAssistant { Spacer(minLength: 60) }
            }

            if let reaction, !reaction.isEmpty {
                Text(reaction)
                    .font(.caption)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.thinMaterial)
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 12)
        .frame(maxWidth: .infinity, alignment: message.isUser ? .trailing : .leading)
    }

    private var bubbleContent: some View {
        ZoomableContent {
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
                messageText

                if !message.thinking.isEmpty {
                    ThinkingDisclosureView(text: message.thinking)
                }

                if !parsedToolEvents.isEmpty {
                    ToolEventListView(events: parsedToolEvents)
                }

                if message.costUsd > 0 {
                    Text("$\(message.costUsd, specifier: "%.4f") · \(message.tokensIn + message.tokensOut)t")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(message.isUser ? Color.blue : Color(.systemGray5))
            .background {
                if isHighlighted {
                    RoundedRectangle(cornerRadius: 22)
                        .fill(Color.yellow.opacity(0.35))
                        .padding(-4)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .frame(maxWidth: UIScreen.main.bounds.width * 0.75, alignment: message.isUser ? .trailing : .leading)
        }
        .contextMenu {
            ForEach(Self.reactionOptions, id: \.self) { emoji in
                Button(emoji) {
                    onReact?(emoji)
                }
            }

            if onReply != nil {
                Button {
                    onReply?()
                } label: {
                    Label("Reply", systemImage: "arrowshape.turn.up.left")
                }
            }

            Button {
                UIPasteboard.general.string = message.content
            } label: {
                Label("Copy", systemImage: "doc.on.doc")
            }
        }
    }

    @ViewBuilder
    private var messageText: some View {
        if message.isAssistant {
            MarkdownMessageText(
                content: message.content,
                font: .subheadline,
                foregroundColor: .primary,
                textAlignment: .leading,
                frameAlignment: .leading
            )
        } else {
            MarkdownMessageText(
                content: message.content,
                font: .subheadline,
                foregroundColor: .white,
                textAlignment: .trailing,
                frameAlignment: .trailing
            )
        }
    }
}

private struct ZoomableContent<Content: View>: View {
    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0

    let content: () -> Content

    var body: some View {
        content()
            .scaleEffect(scale)
            .gesture(
                MagnifyGesture()
                    .onChanged { value in
                        scale = lastScale * value.magnification
                    }
                    .onEnded { value in
                        let finalScale = lastScale * value.magnification
                        lastScale = max(1.0, min(finalScale, 3.0))
                        scale = lastScale
                        if lastScale < 1.05 {
                            withAnimation {
                                scale = 1.0
                                lastScale = 1.0
                            }
                        }
                    }
            )
            .onTapGesture(count: 2) {
                withAnimation(.spring(response: 0.3)) {
                    scale = scale > 1.05 ? 1.0 : 2.0
                    lastScale = scale
                }
            }
            }
    }
}

struct ToolEventDisplayItem: Identifiable, Equatable {
    let id: String
    let name: String
    let input: String
    var result: String?
    var isError: Bool
    var isComplete: Bool

    var resultText: String {
        result?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}

private struct MarkdownMessageText: View {
    let content: String
    let font: Font
    let foregroundColor: Color
    let textAlignment: TextAlignment
    let frameAlignment: Alignment

    var body: some View {
        Group {
            if let attributed = try? AttributedString(markdown: content, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
                Text(attributed)
            } else {
                Text(content)
            }
        }
        .font(font)
        .foregroundStyle(foregroundColor)
        .multilineTextAlignment(textAlignment)
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: frameAlignment)
    }
}

struct ThinkingDisclosureView: View {
    let text: String
    var showsActivity: Bool = false

    var body: some View {
        DisclosureGroup {
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "brain")
                if showsActivity {
                    ThinkingActivityLabel()
                } else {
                    Text("Thinking")
                }
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(8)
        .background(.tertiary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

struct ToolEventListView: View {
    let events: [ToolEventDisplayItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(events) { event in
                ToolEventRow(event: event)
            }
        }
    }
}

private struct ThinkingActivityLabel: View {
    var body: some View {
        TimelineView(.periodic(from: .now, by: 0.45)) { context in
            let dotCount = Int(context.date.timeIntervalSinceReferenceDate * 2).quotientAndRemainder(dividingBy: 4).remainder
            HStack(spacing: 0) {
                Text("Thinking")
                Text(String(repeating: ".", count: dotCount))
                    .monospacedDigit()
            }
        }
    }
}

private struct ToolEventRow: View {
    let event: ToolEventDisplayItem

    var body: some View {
        Group {
            if event.isComplete, !event.resultText.isEmpty {
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 8) {
                        if !event.input.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Input")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                Text(event.input)
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .textSelection(.enabled)
                            }
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text(event.isError ? "Error" : "Result")
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.secondary)
                            ToolResultContentView(text: event.resultText)
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    ToolEventHeader(event: event)
                }
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    ToolEventHeader(event: event)
                    if !event.input.isEmpty {
                        Text(event.input)
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .padding(8)
        .background(Color(.secondarySystemBackground).opacity(0.9))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct ToolEventHeader: View {
    let event: ToolEventDisplayItem

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: toolIconName(for: event.name))
                .font(.caption.weight(.semibold))
                .foregroundStyle(event.isError ? .red : .secondary)
                .frame(width: 16, alignment: .center)

            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(humanReadableToolName(event.name))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                    if !event.input.isEmpty {
                        Text(event.input)
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .textSelection(.enabled)
                    }
                }

                Text(toolResultSummary(for: event))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            statusView
        }
    }

    @ViewBuilder
    private var statusView: some View {
        if !event.isComplete {
            ProgressView()
                .controlSize(.mini)
        } else {
            Image(systemName: event.isError ? "xmark.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(event.isError ? .red : .green)
                .font(.caption)
        }
    }
}

private struct ToolResultContentView: View {
    let text: String

    @State private var showsFullContent = false

    private let previewLimit = 500

    private var needsTruncation: Bool {
        text.count > previewLimit
    }

    private var displayedText: String {
        if needsTruncation, !showsFullContent {
            return String(text.prefix(previewLimit)) + "..."
        }
        return text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(displayedText)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)

            if needsTruncation {
                Button(showsFullContent ? "Show less" : "Show more") {
                    showsFullContent.toggle()
                }
                .buttonStyle(.plain)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.blue)
            }
        }
    }
}

func parseSavedToolEventItems(from jsonString: String) -> [ToolEventDisplayItem] {
    guard !jsonString.isEmpty, jsonString != "[]",
          let data = jsonString.data(using: .utf8),
          let objects = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
        return []
    }

    var itemsByID: [String: ToolEventDisplayItem] = [:]
    var orderedIDs: [String] = []

    func remember(_ item: ToolEventDisplayItem) {
        if !orderedIDs.contains(item.id) {
            orderedIDs.append(item.id)
        }
        itemsByID[item.id] = item
    }

    for object in objects {
        if let type = object["type"] as? String {
            switch type {
            case "tool_use":
                let id = object["id"] as? String ?? UUID().uuidString
                let item = ToolEventDisplayItem(
                    id: id,
                    name: object["name"] as? String ?? "Tool",
                    input: compactToolInputDescription(name: object["name"] as? String, input: object["input"] ?? [:]),
                    result: nil,
                    isError: false,
                    isComplete: false
                )
                remember(item)

            case "tool_result":
                let toolUseID = object["tool_use_id"] as? String ?? UUID().uuidString
                var item = itemsByID[toolUseID] ?? ToolEventDisplayItem(
                    id: toolUseID,
                    name: "Tool",
                    input: "",
                    result: nil,
                    isError: false,
                    isComplete: false
                )
                item.result = stringifiedToolValue(object["content"])
                item.isError = object["is_error"] as? Bool ?? false
                item.isComplete = true
                remember(item)

            default:
                continue
            }
            continue
        }

        let id = object["id"] as? String ?? UUID().uuidString
        var item = ToolEventDisplayItem(
            id: id,
            name: object["name"] as? String ?? "Tool",
            input: compactToolInputDescription(name: object["name"] as? String, input: object["input"] ?? [:]),
            result: nil,
            isError: false,
            isComplete: false
        )

        if let result = object["result"] as? [String: Any] {
            item.result = stringifiedToolValue(result["content"])
            item.isError = result["is_error"] as? Bool ?? false
            item.isComplete = true
        }

        remember(item)
    }

    return orderedIDs.compactMap { itemsByID[$0] }
}

func compactToolInputDescription(name: String? = nil, input: Any, maxLength: Int = 120) -> String {
    let normalizedName = name?.lowercased() ?? ""

    if let dict = input as? [String: Any] {
        let filePath = stringValue(dict["file_path"] ?? dict["path"])
        let pattern = stringValue(dict["pattern"] ?? dict["query"] ?? dict["search"])
        let command = stringValue(dict["command"] ?? dict["cmd"])

        switch normalizedName {
        case "read", "edit", "write":
            if let filePath {
                return truncated("\"\(filePath)\"", to: maxLength)
            }
        case "grep", "search":
            if let pattern, let filePath {
                return truncated("\"\(pattern)\" in \"\(filePath)\"", to: maxLength)
            }
            if let pattern {
                return truncated("\"\(pattern)\"", to: maxLength)
            }
        case "bash", "run", "command":
            if let command {
                return truncated(command, to: maxLength)
            }
        default:
            break
        }

        if let filePath {
            return truncated("\"\(filePath)\"", to: maxLength)
        }
        if let pattern {
            return truncated("\"\(pattern)\"", to: maxLength)
        }
        if let command {
            return truncated(command, to: maxLength)
        }
        return truncated(jsonString(from: dict), to: maxLength)
    }

    if let array = input as? [Any] {
        return truncated(jsonString(from: array), to: maxLength)
    }

    return truncated(stringifiedToolValue(input), to: maxLength)
}

func humanReadableToolName(_ name: String) -> String {
    switch name.lowercased() {
    case "read":
        return "Reading file"
    case "grep", "search":
        return "Searching"
    case "edit", "write":
        return "Editing file"
    case "bash", "run", "command":
        return "Running command"
    case "glob":
        return "Finding files"
    case "ls":
        return "Listing files"
    default:
        return name.isEmpty ? "Tool" : name
    }
}

func toolIconName(for name: String) -> String {
    switch name.lowercased() {
    case "read":
        return "doc.text.magnifyingglass"
    case "grep", "search":
        return "magnifyingglass"
    case "edit", "write":
        return "square.and.pencil"
    case "bash", "run", "command":
        return "terminal"
    case "glob", "ls":
        return "folder"
    default:
        return "wrench.and.screwdriver"
    }
}

func toolResultSummary(for event: ToolEventDisplayItem) -> String {
    if !event.isComplete {
        return "In progress"
    }

    if event.isError {
        return event.resultText.isEmpty ? "Tool failed" : "Error returned"
    }

    guard !event.resultText.isEmpty else {
        return "Completed"
    }

    let lineCount = max(event.resultText.components(separatedBy: .newlines).count, 1)
    switch event.name.lowercased() {
    case "read":
        return "\(lineCount) \(lineCount == 1 ? "line" : "lines")"
    case "grep", "search":
        let matchCount = event.resultText
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .count
        return "\(matchCount) \(matchCount == 1 ? "match" : "matches")"
    default:
        if lineCount > 1 {
            return "\(lineCount) \(lineCount == 1 ? "line" : "lines")"
        }
        return truncated(event.resultText.replacingOccurrences(of: "\n", with: " "), to: 60)
    }
}

func truncated(_ value: String, to limit: Int) -> String {
    guard limit > 3, value.count > limit else { return value }
    return String(value.prefix(limit - 3)) + "..."
}

func stringifiedToolValue(_ value: Any?) -> String {
    guard let value else { return "" }
    if let string = value as? String {
        return string
    }
    return jsonString(from: value)
}

private func stringValue(_ value: Any?) -> String? {
    guard let value else { return nil }
    if let string = value as? String {
        return string
    }
    if let number = value as? NSNumber {
        return number.stringValue
    }
    return nil
}

private func jsonString(from value: Any) -> String {
    guard JSONSerialization.isValidJSONObject(value),
          let data = try? JSONSerialization.data(withJSONObject: value, options: []),
          let string = String(data: data, encoding: .utf8) else {
        return String(describing: value)
    }
    return string
}
