import SwiftUI

struct SearchOverlay: View {
    @Binding var searchText: String
    @Binding var isPresented: Bool
    let matchCount: Int

    @FocusState private var isSearchFocused: Bool

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)

                TextField("Search messages", text: $searchText)
                    .focused($isSearchFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()

                if !searchText.isEmpty {
                    Text("\(matchCount)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.yellow.opacity(0.5))
                        .clipShape(Capsule())
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 16))

            Button {
                searchText = ""
                isPresented = false
            } label: {
                Image(systemName: "xmark")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)
                    .frame(width: 36, height: 36)
                    .background(.regularMaterial)
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
        }
        .shadow(color: .black.opacity(0.08), radius: 12, y: 4)
        .onAppear {
            isSearchFocused = true
        }
    }
}
