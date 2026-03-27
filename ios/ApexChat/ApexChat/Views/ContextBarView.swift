import SwiftUI

struct ContextBarView: View, Equatable {
    let context: ContextData

    static func == (lhs: ContextBarView, rhs: ContextBarView) -> Bool {
        lhs.context == rhs.context
    }

    private var pct: Double {
        guard context.contextWindow > 0 else { return 0 }
        return min(Double(context.tokensIn) / Double(context.contextWindow) * 100, 100)
    }

    var body: some View {
        HStack(spacing: 6) {
            Spacer()

            Text("\(formatTokens(context.tokensIn)) / \(formatTokens(context.contextWindow)) (\(Int(pct))%)")
                .font(.system(size: 10, weight: .semibold).monospacedDigit())
                .foregroundStyle(pct >= 80 ? .red : pct >= 50 ? .orange : .secondary)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.primary.opacity(0.08))

                    Capsule()
                        .fill(barColor)
                        .frame(width: geo.size.width * CGFloat(pct) / 100)
                }
            }
            .frame(width: 50, height: 3)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 3)
    }

    private var barColor: Color {
        if pct >= 80 { return .red }
        if pct >= 50 { return .orange }
        return .green
    }

    private func formatTokens(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }
}