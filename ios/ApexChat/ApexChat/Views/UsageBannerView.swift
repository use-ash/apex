import SwiftUI

struct UsageBannerView: View {
    let usage: UsageResponse

    var body: some View {
        HStack(spacing: 8) {
            Text("Claude")
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(.secondary.opacity(0.5))
                .textCase(.uppercase)
                .rotationEffect(.degrees(-90))
                .fixedSize()
                .frame(width: 10)

            usageBar(
                label: "Session",
                pct: usage.session.utilization,
                resetLabel: usage.session.resetsIn
            )

            usageBar(
                label: "Weekly",
                pct: usage.weekly.utilization,
                resetLabel: usage.weekly.resetsIn
            )
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
    }

    private func usageBar(label: String, pct: Int, resetLabel: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(pct)%")
                    .font(.caption2.weight(.bold).monospacedDigit())
                    .foregroundStyle(barColor(pct))
                Text("(\(resetLabel))")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.primary.opacity(0.08))
                        .frame(height: 4)

                    Capsule()
                        .fill(barColor(pct))
                        .frame(width: geo.size.width * CGFloat(min(pct, 100)) / 100, height: 4)
                }
            }
            .frame(height: 4)
        }
    }

    private func barColor(_ pct: Int) -> Color {
        if pct >= 90 { return .red }
        if pct >= 70 { return .orange }
        return .green
    }
}
