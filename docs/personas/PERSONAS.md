# Apex Agent Personas

Apex ships with system personas and starter templates. Users can create custom personas through the dashboard or by editing persona files.

---

## System Personas

These are built into the server and refreshed on every startup. They cannot be deleted.

| Persona | Role | Model | Default? |
|---------|------|-------|----------|
| Apex Assistant | General-purpose assistant — questions, research, writing, analysis | Claude Sonnet | Yes |
| Guide | Apex platform expert — setup help, configuration, how things work | Claude Haiku | No |
| CodeExpert | Technical specialist — code, debugging, architecture, engineering | Claude Sonnet | No |

## Starter Templates

These are seeded on first run from `server/persona_templates.json`. Users can edit or delete them freely.

| Persona | Role | File |
|---------|------|------|
| [Architect](architect.md) | CTO — product design, system architecture, technical decisions | `architect.md` |
| [Assistant](assistant.md) | Versatile helper — everyday tasks, research, brainstorming | `assistant.md` |
| [Designer](designer.md) | UI/UX specialist — interfaces, layouts, visual systems | `designer.md` |
| [Developer](developer.md) | Software engineer — implementation, testing, code review | `developer.md` |
| [Planner](planner.md) | Project manager — milestones, tracking, coordination | `planner.md` |
| [Writer](writer.md) | Content specialist — docs, copy, communication | `writer.md` |

## Creating Custom Personas

### From the Dashboard

Open **Apex Dashboard > Personas > + New Persona**. Fill in name, avatar, model, and system prompt.

### From a Markdown File

Drop a `.md` file in `docs/personas/` with YAML frontmatter:

```yaml
---
name: My Persona
slug: my-persona
role: What it does
model: claude-sonnet-4-6
backend: claude
avatar: "🎯"
---

# My Persona

## System Prompt
...
```

---

## Conventions

### Handoff Format
```
## Handoff: [Source Persona] → [Target Persona]
**Context:** [1-2 sentences]
**What's needed:** [specific ask]
**References:** [file paths]
```

### Conflict Resolution
If two personas give conflicting advice in a group:
1. Both present their case to the user
2. The user decides
3. Decision logged in the channel
