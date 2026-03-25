import Foundation
import SwiftUI
import UIKit

struct MessageBubble: View {
    private static let reactionOptions = ["👍", "❤️", "😂", "😮", "😢", "🔥"]
    private static let iso8601FormatterWithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private static let iso8601Formatter = ISO8601DateFormatter()
    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        formatter.dateStyle = .none
        return formatter
    }()

    let message: Message
    var isHighlighted: Bool = false
    var reaction: String?
    var fontScale: CGFloat = 1.0
    var onReact: ((String?) -> Void)?
    var onReply: (() -> Void)?

    @State private var dragOffset: CGFloat = 0

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
            .offset(x: dragOffset)
            .gesture(
                DragGesture(minimumDistance: 20)
                    .onChanged { value in
                        if value.translation.width < 0 {
                            dragOffset = max(value.translation.width, -80)
                        }
                    }
                    .onEnded { _ in
                        withAnimation(.spring(response: 0.3)) {
                            dragOffset = 0
                        }
                    }
            )
            .overlay(alignment: .trailing) {
                if dragOffset < -10, let timestamp = formattedTime(message.createdAt) {
                    Text(timestamp)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .offset(x: 90 + dragOffset)
                        .allowsHitTesting(false)
                }
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
        .contentShape(RoundedRectangle(cornerRadius: 18))
        .frame(maxWidth: 300, alignment: message.isUser ? .trailing : .leading)
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

    private func formattedTime(_ createdAt: String) -> String? {
        let date = Self.iso8601FormatterWithFractionalSeconds.date(from: createdAt)
            ?? Self.iso8601Formatter.date(from: createdAt)
        guard let date else { return nil }
        return Self.timeFormatter.string(from: date)
    }

    @ViewBuilder
    private var messageText: some View {
        let baseFont = UIFont.preferredFont(forTextStyle: .subheadline)
        let scaledFont = baseFont.withSize(baseFont.pointSize * fontScale)
        if message.isAssistant {
            SelectableTextView(content: message.content, uiFont: scaledFont, textColor: UIColor.label)
        } else {
            SelectableTextView(content: message.content, uiFont: scaledFont, textColor: .white)
        }
    }
}

/// UITextView wrapper — gives native iOS partial text selection with drag handles.
/// SwiftUI Text + .textSelection(.enabled) only allows full-text copy and conflicts
/// with .contextMenu, so we drop to UIKit for the message body.
struct SelectableTextView: UIViewRepresentable {
    let content: String
    let uiFont: UIFont
    let textColor: UIColor

    func makeUIView(context: Context) -> UITextView {
        let tv = UITextView()
        tv.isEditable = false
        tv.isScrollEnabled = false
        tv.backgroundColor = .clear
        tv.textContainerInset = .zero
        tv.textContainer.lineFragmentPadding = 0
        tv.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        tv.adjustsFontForContentSizeCategory = true
        tv.isSelectable = true
        tv.dataDetectorTypes = []
        // Disable the scroll view's pan gesture — scrolling is off anyway,
        // and this pan eats horizontal swipes meant for the parent DragGesture.
        // Text selection uses long-press + drag (separate gesture), unaffected.
        tv.panGestureRecognizer.isEnabled = false
        return tv
    }

    func updateUIView(_ tv: UITextView, context: Context) {
        let styled = styledAttributedString()
        if tv.attributedText.string != styled.string {
            tv.attributedText = styled
        } else if tv.font != uiFont || tv.textColor != textColor {
            tv.attributedText = styled
        }
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        let width = proposal.width ?? 280
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    private func styledAttributedString() -> NSAttributedString {
        if let md = try? NSMutableAttributedString(
            markdown: content,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            let fullRange = NSRange(location: 0, length: md.length)
            md.enumerateAttribute(.inlinePresentationIntent, in: fullRange, options: []) { value, range, _ in
                guard let raw = (value as? NSNumber)?.intValue else { return }
                let intent = InlinePresentationIntent(rawValue: UInt(raw))
                var traits: UIFontDescriptor.SymbolicTraits = []
                if intent.contains(.stronglyEmphasized) { traits.insert(.traitBold) }
                if intent.contains(.emphasized) { traits.insert(.traitItalic) }
                if intent.contains(.code) {
                    let mono = UIFont.monospacedSystemFont(ofSize: uiFont.pointSize, weight: .regular)
                    md.addAttribute(.font, value: mono, range: range)
                    return
                }
                if !traits.isEmpty, let desc = uiFont.fontDescriptor.withSymbolicTraits(traits) {
                    md.addAttribute(.font, value: UIFont(descriptor: desc, size: uiFont.pointSize), range: range)
                } else {
                    md.addAttribute(.font, value: uiFont, range: range)
                }
            }
            md.enumerateAttribute(.font, in: fullRange, options: []) { value, range, _ in
                if value == nil {
                    md.addAttribute(.font, value: uiFont, range: range)
                }
            }
            md.addAttribute(.foregroundColor, value: textColor, range: fullRange)
            return md
        }
        return NSAttributedString(string: content, attributes: [
            .font: uiFont,
            .foregroundColor: textColor,
        ])
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
            ScrollView {
                Text(text)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(maxHeight: 200)
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "brain")
                if showsActivity {
                    ThinkingActivityLabel()
                } else {
                    Text("Thinking")
                }
            }
            .font(.caption)
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
        let description = stringValue(dict["description"])

        switch normalizedName {
        case "read", "edit", "write":
            if let filePath {
                let short = shortPath(filePath)
                return truncated(short, to: maxLength)
            }
        case "grep", "search":
            if let pattern, let filePath {
                return truncated("\"\(pattern)\" in \(shortPath(filePath))", to: maxLength)
            }
            if let pattern {
                return truncated("\"\(pattern)\"", to: maxLength)
            }
        case "bash", "run", "command":
            if let description {
                return truncated(description, to: maxLength)
            }
            if let command {
                return truncated(command, to: maxLength)
            }
        case "glob":
            if let pattern {
                return truncated(pattern, to: maxLength)
            }
        case "agent":
            if let description {
                return truncated(description, to: maxLength)
            }
            if let prompt = stringValue(dict["prompt"]) {
                return truncated(prompt, to: maxLength)
            }
        case "skill":
            if let skill = stringValue(dict["skill"]) {
                let args = stringValue(dict["args"])
                return truncated(args != nil ? "\(skill) \(args!)" : skill, to: maxLength)
            }
        case "webfetch":
            if let url = stringValue(dict["url"]) {
                return truncated(url, to: maxLength)
            }
        case "websearch":
            if let query = stringValue(dict["query"]) {
                return truncated("\"\(query)\"", to: maxLength)
            }
        default:
            break
        }

        if let filePath {
            return truncated(shortPath(filePath), to: maxLength)
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
        return "Searching code"
    case "edit":
        return "Editing file"
    case "write":
        return "Writing file"
    case "bash", "run", "command":
        return "Running command"
    case "glob":
        return "Finding files"
    case "ls":
        return "Listing files"
    case "webfetch":
        return "Fetching URL"
    case "websearch":
        return "Web search"
    case "agent":
        return "Sub-agent"
    case "skill":
        return "Running skill"
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
    case "edit":
        return "square.and.pencil"
    case "write":
        return "doc.badge.plus"
    case "bash", "run", "command":
        return "terminal"
    case "glob", "ls":
        return "folder"
    case "webfetch":
        return "globe"
    case "websearch":
        return "globe.badge.chevron.backward"
    case "agent":
        return "person.2"
    case "skill":
        return "bolt.fill"
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

    let lines = event.resultText.components(separatedBy: .newlines)
    let nonEmptyLines = lines.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    let lineCount = max(lines.count, 1)
    switch event.name.lowercased() {
    case "read":
        return "\(lineCount) \(lineCount == 1 ? "line" : "lines")"
    case "grep", "search":
        let matchCount = nonEmptyLines.count
        return "\(matchCount) \(matchCount == 1 ? "match" : "matches")"
    case "glob":
        let fileCount = nonEmptyLines.count
        return "\(fileCount) \(fileCount == 1 ? "file" : "files")"
    case "bash", "run", "command":
        if lineCount <= 3 {
            return truncated(event.resultText.replacingOccurrences(of: "\n", with: " "), to: 60)
        }
        return "\(lineCount) lines of output"
    case "agent":
        return "Completed"
    default:
        if lineCount > 1 {
            return "\(lineCount) \(lineCount == 1 ? "line" : "lines")"
        }
        return truncated(event.resultText.replacingOccurrences(of: "\n", with: " "), to: 60)
    }
}

private func shortPath(_ path: String) -> String {
    let components = path.split(separator: "/")
    if components.count <= 2 { return path }
    return components.suffix(2).joined(separator: "/")
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
