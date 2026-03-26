import SwiftUI

struct ContentView: View {
    @Bindable var appState: AppState

    @State private var isShowingConnectionDetails: Bool = false
    @State private var isShowingSettings: Bool = false
    @State private var isShowingSearch: Bool = false
    @State private var isShowingChannels: Bool = false
    @State private var channelDragOffset: CGFloat = 0
    @State private var searchText: String = ""
    @State private var openSettingsAfterConnectionSheet: Bool = false
    @State private var showUsageBanner: Bool = false
    @State private var usageHideTask: Task<Void, Never>?
    @State private var toastDismissTask: Task<Void, Never>?
    @State private var selectedToastAlert: Alert?
    @State private var isShowingBellSheet: Bool = false
    @State private var bellSelectedAlert: Alert?
    @State private var preBellChatId: String?

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                VStack(spacing: 0) {
                    if showUsageBanner, let usage = appState.usageData {
                        UsageBannerView(usage: usage)
                            .transition(.move(edge: .top).combined(with: .opacity))
                    }
                    chatContent
                }

                if isShowingSearch {
                    SearchOverlay(
                        searchText: $searchText,
                        isPresented: $isShowingSearch,
                        matchCount: matchedMessageCount
                    )
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .zIndex(1)
                }
            }
            .animation(.spring(response: 0.24, dampingFraction: 0.88), value: isShowingSearch)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        withAnimation(.easeOut(duration: 0.25)) {
                            isShowingChannels = true
                        }
                    } label: {
                        Image(systemName: "line.3.horizontal")
                    }
                }

                ToolbarItem(placement: .principal) {
                    Button {
                        if appState.usageData != nil {
                            flashUsageBanner()
                        } else {
                            isShowingConnectionDetails = true
                        }
                    } label: {
                        connectionPill
                    }
                    .buttonStyle(.plain)
                }

                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await appState.loadAlerts() }
                        isShowingBellSheet = true
                    } label: {
                        ZStack(alignment: .topTrailing) {
                            Image(systemName: "bell.fill")
                                .font(.body)
                            if appState.unackedAlertCount > 0 {
                                Text("\(appState.unackedAlertCount)")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(.white)
                                    .frame(minWidth: 16, minHeight: 16)
                                    .background(.red)
                                    .clipShape(Circle())
                                    .offset(x: 8, y: -8)
                            }
                        }
                        .frame(width: 32, height: 32)
                    }
                }
            }
        }
        .sheet(
            isPresented: $isShowingConnectionDetails,
            onDismiss: handleConnectionSheetDismiss
        ) {
            ConnectionDetailSheet(
                statusText: appState.connectionStatusText,
                isConnected: appState.connectionManager.isConnected,
                modelDisplayName: appState.modelDisplayName,
                modelDescription: appState.modelDescription,
                serverURL: appState.serverURL
            ) {
                openSettingsAfterConnectionSheet = true
                isShowingConnectionDetails = false
            }
            .presentationDetents([.medium])
        }
        .sheet(isPresented: $isShowingSettings) {
            SettingsView(appState: appState)
        }
        .sheet(isPresented: $isShowingBellSheet) {
            bellAlertListSheet
        }
        .sheet(item: $bellSelectedAlert) { alert in
            AlertDetailView(alert: alert, appState: appState)
                .onDisappear {
                    // Return to the chat we were on before tapping the alert
                    if let prevId = preBellChatId,
                       let prevChat = appState.chats.first(where: { $0.id == prevId }) {
                        appState.switchToChat(prevChat)
                        preBellChatId = nil
                    }
                }
        }
        .overlay {
            if isShowingChannels || channelDragOffset > 0 {
                channelDrawer
            }
        }
        .overlay(alignment: .top) {
            if let alert = appState.toastAlert, !isShowingChannels, !isShowingSettings, !isShowingConnectionDetails {
                AlertBubble(
                    alert: alert,
                    onAck: {
                        Task { await appState.ackAlert(alert.id) }
                        withAnimation { appState.toastAlert = nil }
                    },
                    onAllow: {
                        Task { await appState.allowAlert(alert.id) }
                        withAnimation { appState.toastAlert = nil }
                    },
                    onTap: {
                        selectedToastAlert = alert
                        withAnimation { appState.toastAlert = nil }
                    }
                )
                .transition(.move(edge: .top).combined(with: .opacity))
                .padding(.top, 8)
                .zIndex(100)
                .onAppear {
                    toastDismissTask?.cancel()
                    toastDismissTask = Task {
                        try? await Task.sleep(for: .seconds(8))
                        guard !Task.isCancelled else { return }
                        withAnimation(.easeOut(duration: 0.3)) {
                            appState.toastAlert = nil
                        }
                    }
                }
                .gesture(
                    DragGesture(minimumDistance: 10)
                        .onEnded { value in
                            if value.translation.height < -20 {
                                withAnimation { appState.toastAlert = nil }
                            }
                        }
                )
            }
        }
        .sheet(item: $selectedToastAlert) { alert in
            AlertDetailView(alert: alert, appState: appState)
        }
        .simultaneousGesture(
            DragGesture(coordinateSpace: .global)
                .onChanged { value in
                    if value.startLocation.x < 50 && value.translation.width > 0 {
                        channelDragOffset = value.translation.width
                    }
                }
                .onEnded { value in
                    if value.startLocation.x < 50 && value.translation.width > 60 {
                        withAnimation(.easeOut(duration: 0.25)) {
                            isShowingChannels = true
                            channelDragOffset = 0
                        }
                    } else {
                        withAnimation(.easeOut(duration: 0.2)) {
                            channelDragOffset = 0
                        }
                    }
                }
        )
        .onAppear {
            appState.startUsagePolling()
            flashUsageBanner()
        }
        .onDisappear {
            appState.stopUsagePolling()
        }
    }

    private func flashUsageBanner() {
        usageHideTask?.cancel()
        withAnimation { showUsageBanner = true }
        usageHideTask = Task {
            try? await Task.sleep(for: .seconds(5))
            guard !Task.isCancelled else { return }
            withAnimation(.easeOut(duration: 0.3)) { showUsageBanner = false }
        }
    }

    // MARK: - Bell Alert List Sheet

    private var bellAlertListSheet: some View {
        NavigationStack {
            List {
                if appState.alerts.isEmpty {
                    ContentUnavailableView("No Alerts", systemImage: "bell.slash", description: Text("Alerts will appear here when they arrive."))
                } else {
                    ForEach(appState.alerts) { alert in
                        Button {
                            isShowingBellSheet = false
                            // Save current chat so we can return after detail closes
                            preBellChatId = appState.persistentChatId
                            // Navigate to the matching alerts channel
                            let sourceCategory = AppState.alertCategory(for: alert.source)
                            if let channel = appState.chats.first(where: {
                                $0.type == "alerts" && $0.category == sourceCategory
                            }) ?? appState.chats.first(where: {
                                $0.type == "alerts" && ($0.category == nil || $0.category?.isEmpty == true)
                            }) {
                                appState.switchToChat(channel)
                            }
                            // Open alert detail after a brief delay for navigation
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                bellSelectedAlert = alert
                            }
                        } label: {
                            HStack(alignment: .top, spacing: 10) {
                                Image(systemName: alert.severity == "critical" ? "exclamationmark.triangle.fill" : alert.severity == "warning" ? "exclamationmark.circle.fill" : "info.circle.fill")
                                    .foregroundStyle(alert.severity == "critical" ? .red : alert.severity == "warning" ? .orange : .blue)
                                    .font(.body)
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack {
                                        Text(alert.source.uppercased())
                                            .font(.caption2.weight(.bold))
                                            .foregroundStyle(alert.severity == "critical" ? .red : alert.severity == "warning" ? .orange : .blue)
                                        Spacer()
                                        Text(bellTimeAgo(alert.createdAt))
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                        if alert.acked {
                                            Image(systemName: "checkmark.circle.fill")
                                                .font(.caption2)
                                                .foregroundStyle(.green)
                                        }
                                    }
                                    Text(alert.title)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.primary)
                                    if !alert.body.isEmpty {
                                        Text(alert.body)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(2)
                                    }
                                }
                            }
                            .opacity(alert.acked ? 0.5 : 1.0)
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Alerts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { isShowingBellSheet = false }
                }
            }
        }
    }

    private func bellTimeAgo(_ iso: String) -> String {
        let fmtFrac = ISO8601DateFormatter()
        fmtFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fmtPlain = ISO8601DateFormatter()
        guard let date = fmtFrac.date(from: iso) ?? fmtPlain.date(from: iso) else { return "" }
        let secs = Date().timeIntervalSince(date)
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(Int(secs / 60))m ago" }
        if secs < 86400 { return "\(Int(secs / 3600))h ago" }
        return DateFormatter.localizedString(from: date, dateStyle: .short, timeStyle: .short)
    }

    // MARK: - Chat

    @ViewBuilder
    private var chatContent: some View {
        if let chatId = appState.persistentChatId {
            ChatView(
                chatId: chatId,
                appState: appState,
                highlightedMessageIDs: highlightedMessageIDs
            )
        } else if appState.isEnsuringPersistentChat {
            ProgressView("Preparing chat...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = appState.error {
            ContentUnavailableView(
                "Unable to Load Chat",
                systemImage: "exclamationmark.triangle",
                description: Text(error)
            )
        } else {
            ProgressView("Preparing chat...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Channel Drawer

    private let drawerWidth: CGFloat = 300

    private var channelDrawer: some View {
        let openOffset: CGFloat = 0
        let closedOffset: CGFloat = -drawerWidth
        let currentOffset: CGFloat = isShowingChannels
            ? openOffset
            : closedOffset + min(channelDragOffset, drawerWidth)

        return ZStack(alignment: .leading) {
            // Scrim
            Color.black.opacity(scrimOpacity)
                .ignoresSafeArea()
                .onTapGesture {
                    withAnimation(.easeOut(duration: 0.25)) {
                        isShowingChannels = false
                    }
                }

            // Drawer panel
            ChannelListView(appState: appState, onSelect: {
                withAnimation(.easeOut(duration: 0.25)) {
                    isShowingChannels = false
                }
            }, onShowSearch: {
                withAnimation {
                    isShowingSearch = true
                }
            }, onShowSettings: {
                isShowingSettings = true
            })
            .frame(width: drawerWidth)
            .background(.ultraThickMaterial)
            .offset(x: currentOffset)
            .gesture(
                DragGesture()
                    .onEnded { value in
                        if value.translation.width < -60 {
                            withAnimation(.easeOut(duration: 0.25)) {
                                isShowingChannels = false
                            }
                        }
                    }
            )
        }
    }

    private var scrimOpacity: Double {
        if isShowingChannels { return 0.4 }
        return Double(min(channelDragOffset / drawerWidth, 1.0)) * 0.4
    }

    // MARK: - Toolbar

    private var connectionPill: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(appState.connectionManager.isConnected ? .green : .red)
                .frame(width: 8, height: 8)

            Text(appState.modelDisplayName)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(1)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(.thinMaterial)
        .clipShape(Capsule())
        .overlay {
            Capsule()
                .strokeBorder(Color.primary.opacity(0.08), lineWidth: 1)
        }
    }

    // MARK: - Search

    private var matchedMessageCount: Int {
        highlightedMessageIDs.count
    }

    private var highlightedMessageIDs: Set<String> {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return [] }

        return Set(
            appState.messages
                .filter { $0.searchableText.localizedCaseInsensitiveContains(query) }
                .map(\.id)
        )
    }

    private func handleConnectionSheetDismiss() {
        guard openSettingsAfterConnectionSheet else { return }
        openSettingsAfterConnectionSheet = false
        isShowingSettings = true
    }
}
