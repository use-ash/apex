# Channel Settings Dropdown — Implementation Spec

## Overview

Replace the current topbar profile chip with a **channel settings dropdown** that slides down from the topbar when tapped. This is where persona, model, and channel-specific settings live — NOT in the global settings panel.

**Separation of concerns:**
- **Global settings** (hamburger menu → Settings): server config, credentials, TLS, workspace
- **Channel settings** (topbar dropdown): persona, model, behavior toggles for THIS channel

## UX Design

### Trigger
The topbar currently shows: `[avatar] [persona name]` or `💬 No Profile`

When tapped, a dropdown sheet slides down from the topbar (not a modal, not a full-screen sheet — a compact panel anchored to the topbar).

### Dropdown Contents

```
┌─────────────────────────────────────┐
│  Channel Settings                   │
├─────────────────────────────────────┤
│                                     │
│  Persona                            │
│  ┌─────────────────────────────┐    │
│  │ 🏗️ Architect            ▼  │    │
│  └─────────────────────────────┘    │
│  CTO — plans, designs, reviews      │
│                                     │
│  Model                              │
│  ┌─────────────────────────────┐    │
│  │ claude-opus-4-6     🔒     │    │
│  └─────────────────────────────┘    │
│  Locked by profile                  │
│                                     │
│  ─────────────────────────────────  │
│                                     │
│  ☐ Whisper (auto-recall memories)   │
│  ☐ Extended thinking                │
│                                     │
└─────────────────────────────────────┘
```

### Persona Selector
- Dropdown/picker showing all profiles from `GET /api/profiles`
- Each option shows: avatar + name + role_description
- Selecting a profile: `PATCH /api/chats/{id}` with `profile_id`
- "No Profile" option at the top clears the profile
- Changing persona triggers session reset (server handles this in the P0 fix)

### Model Selector
- When a persona is set: **locked** — shows the profile's model with a 🔒 icon and "Locked by profile" label. Cannot be changed.
- When no persona: **editable** — standard model dropdown (cloud models + local models)
- Changing model: same WebSocket `set_model` action as current settings

### Toggle Options (future, can be empty for v1)
- Whisper injection on/off (per-channel override)
- Extended thinking on/off
- These are nice-to-haves, not required for v1

### Dismiss
- Tap outside the dropdown to close
- Tap the topbar trigger again to close
- Any selection auto-closes after a brief delay

## Webapp Implementation

### Changes to apex.py (embedded HTML/JS)

1. **Replace the current `showProfileDropdown()` function** with a richer `showChannelSettings()` that renders the full panel

2. **CSS**: Dropdown panel anchored to topbar, slides down with a subtle animation. Semi-transparent backdrop. Compact — doesn't take over the screen.

3. **JS**:
   - `showChannelSettings(event)` — fetches profiles, builds panel, attaches to topbar
   - Persona picker: select element or clickable list
   - Model picker: select element, disabled when profile is set
   - `changeChatProfile(profileId)` — existing function, already works
   - `changeChatModel(model)` — existing function via WebSocket

4. **Remove the separate model selector from global settings** for the current chat (it's now in the channel dropdown). The global settings model selector should only set the DEFAULT model for new chats.

## iOS Implementation

### Changes to iOS app

1. **Chat header tap target**: Tapping the persona/model indicator in the navigation bar opens a `.sheet` or `.popover` with channel settings

2. **ChannelSettingsView.swift** (new view):
   ```swift
   struct ChannelSettingsView: View {
       @Bindable var appState: AppState
       let chatId: String

       var body: some View {
           Form {
               Section("Persona") {
                   // Profile picker — list of profiles with avatars
                   // "No Profile" option
               }
               Section("Model") {
                   // If profile set: show locked model
                   // If no profile: model picker
               }
           }
       }
   }
   ```

3. **ContentView.swift**: Add tap gesture on the title/profile indicator that presents `ChannelSettingsView` as a popover or compact sheet

4. **AppState changes**: `updateChatProfile()` and model switching already exist — just need to be accessible from the new view

## Task Breakdown for Codex

This is a bounded task with clear scope:

**Chunk 1: Webapp dropdown** (~3-4 file sections in apex.py)
- Replace `showProfileDropdown()` with `showChannelSettings()`
- Add CSS for the settings panel
- Wire persona picker + locked model display
- Test: topbar click opens panel, selecting persona changes it, model shows locked

**Chunk 2: iOS ChannelSettingsView** (~2 new/modified Swift files)
- Create `ChannelSettingsView.swift`
- Wire tap gesture in `ContentView.swift`
- Test: tap header opens settings, persona picker works, model locked when profile set

Each chunk should be one Codex turn. Verify after each.
