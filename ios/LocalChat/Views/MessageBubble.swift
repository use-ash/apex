import SwiftUI

struct MessageBubble: View {
    let message: Message

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }

            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
                // Main content
                markdownContent
                    .font(.subheadline)
                    .foregroundStyle(message.isUser ? .white : .primary)

                // Thinking disclosure
                if !message.thinking.isEmpty {
                    DisclosureGroup {
                        Text(message.thinking)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    } label: {
                        Label("Thinking", systemImage: "brain")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.tertiary.opacity(0.3))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }

                // Tool events
                if !message.toolEvents.isEmpty, message.toolEvents != "[]" {
                    toolEventsView
                }

                // Cost badge
                if message.costUsd > 0 {
                    Text("$\(message.costUsd, specifier: "%.4f") · \(message.tokensIn + message.tokensOut)t")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(message.isUser ? Color.blue : Color(.systemGray5))
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .frame(maxWidth: UIScreen.main.bounds.width * 0.75, alignment: message.isUser ? .trailing : .leading)

            if message.isAssistant { Spacer(minLength: 60) }
        }
        .padding(.horizontal, 12)
    }

    // MARK: - Markdown

    private var markdownContent: some View {
        Group {
            if let attributed = try? AttributedString(markdown: message.content, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
                Text(attributed)
            } else {
                Text(message.content)
            }
        }
    }

    // MARK: - Tool Events

    private var toolEventsView: some View {
        Group {
            if let data = message.toolEvents.data(using: .utf8),
               let events = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(events.enumerated()), id: \.offset) { entry in
                            let event = entry.element
                            HStack(alignment: .top, spacing: 4) {
                                let result = event["result"] as? [String: Any]
                                let isError = result?["is_error"] as? Bool ?? false
                                Image(systemName: isError ? "xmark.circle.fill" : "checkmark.circle.fill")
                                    .foregroundStyle(isError ? .red : .green)
                                    .font(.caption2)

                                let name = event["name"] as? String ?? "tool"
                                let content = result?["content"] as? String ?? ""
                                Text("\(name): \(content.prefix(300))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                } label: {
                    Label("\(events.count) tool call\(events.count == 1 ? "" : "s")", systemImage: "wrench")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .background(.tertiary.opacity(0.3))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
        }
    }
}
