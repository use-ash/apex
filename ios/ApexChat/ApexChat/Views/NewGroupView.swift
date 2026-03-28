import SwiftUI

struct NewGroupView: View {
    @Bindable var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var groupTitle = ""
    @State private var selectedMembers: [String: String] = [:]  // profile_id -> routing_mode

    var body: some View {
        NavigationStack {
            List {
                Section("Group Name") {
                    TextField("e.g. Build Room", text: $groupTitle)
                }

                Section {
                    if appState.profiles.isEmpty {
                        Text("No agent profiles available")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(appState.profiles) { profile in
                            Button {
                                toggleMember(profile.id)
                            } label: {
                                HStack(spacing: 12) {
                                    Text(profile.avatar.isEmpty ? "\u{1F4AC}" : profile.avatar)
                                        .font(.title2)
                                        .frame(width: 36, alignment: .center)

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(profile.name)
                                            .font(.body.weight(.semibold))
                                            .foregroundStyle(.primary)
                                        if !profile.roleDescription.isEmpty {
                                            Text(profile.roleDescription)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .lineLimit(1)
                                        }
                                    }

                                    Spacer()

                                    if let mode = selectedMembers[profile.id] {
                                        if mode == "primary" {
                                            Image(systemName: "crown.fill")
                                                .foregroundStyle(.yellow)
                                        } else {
                                            Image(systemName: "checkmark.circle.fill")
                                                .foregroundStyle(.blue)
                                        }
                                    }
                                }
                            }
                        }
                    }
                } header: {
                    Text("Members")
                } footer: {
                    Text("Tap to add/remove. Tap again to set as primary (crown).")
                        .font(.caption2)
                }
            }
            .navigationTitle("New Group")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Create") {
                        createGroup()
                    }
                    .disabled(selectedMembers.isEmpty)
                    .fontWeight(.semibold)
                }
            }
            .task {
                await appState.loadProfiles()
            }
        }
    }

    private func toggleMember(_ profileId: String) {
        if let current = selectedMembers[profileId] {
            if current == "mentioned" {
                // Promote to primary, demote others
                for key in selectedMembers.keys {
                    if selectedMembers[key] == "primary" {
                        selectedMembers[key] = "mentioned"
                    }
                }
                selectedMembers[profileId] = "primary"
            } else {
                // Remove
                selectedMembers.removeValue(forKey: profileId)
            }
        } else {
            selectedMembers[profileId] = "mentioned"
        }
    }

    private func createGroup() {
        var members = selectedMembers.map { ["profile_id": $0.key, "routing_mode": $0.value] }
        // Ensure at least one primary
        if !members.contains(where: { $0["routing_mode"] == "primary" }), !members.isEmpty {
            members[0]["routing_mode"] = "primary"
        }
        let title = groupTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        Task {
            await appState.createGroup(
                title: title.isEmpty ? "New Group" : title,
                members: members
            )
            dismiss()
        }
    }
}
