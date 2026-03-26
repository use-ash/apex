import SwiftUI

struct ContentView: View {
    @Bindable var appState: AppState

    @State private var isShowingConnectionDetails: Bool = false
    @State private var isShowingSettings: Bool = false
    @State private var isShowingSearch: Bool = false
    @State private var searchText: String = ""
    @State private var openSettingsAfterConnectionSheet: Bool = false

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                VStack(spacing: 0) {
                    if let usage = appState.usageData {
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
                        isShowingSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }

                ToolbarItem(placement: .principal) {
                    Button {
                        isShowingConnectionDetails = true
                    } label: {
                        HStack(spacing: 6) {
                            connectionPill
                            if appState.unackedAlertCount > 0 {
                                Text("\(appState.unackedAlertCount)")
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(.red)
                                    .clipShape(Capsule())
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }

                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        withAnimation {
                            isShowingSearch.toggle()
                            if !isShowingSearch {
                                searchText = ""
                            }
                        }
                    } label: {
                        Image(systemName: isShowingSearch ? "xmark.circle.fill" : "magnifyingglass")
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
        .onAppear {
            appState.startUsagePolling()
        }
        .onDisappear {
            appState.stopUsagePolling()
        }
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
