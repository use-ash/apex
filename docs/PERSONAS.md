# Build Your AI Team

Apex ships with system personas and starter templates. Each has a name, a role, a model, and a system prompt that shapes how it thinks and responds. You can use them as-is, customize them, or build your own from scratch.

**Think of personas like hiring.** You wouldn't ask a designer to review your database schema, and you wouldn't ask a DevOps engineer to write marketing copy. Personas let you give each AI a specialty and a voice.

---

## System Personas

These are built into the server and refreshed on every startup.

### Apex Assistant — General Purpose
**Model:** Claude Sonnet 4.6 · **Avatar:** ✨ · **Default**

The go-to for everyday work. Questions, research, writing, analysis. Clear and direct, matches your register — casual for quick questions, thorough for complex ones.

**Good for:** Quick Q&A, research, writing, brainstorming, analysis.

### Guide — Platform Expert
**Model:** Claude Haiku 4.5 · **Avatar:** 🧭

Knows Apex inside and out. Setup help, configuration questions, how features work. Runs on Haiku for fast, lightweight answers about the platform itself.

**Good for:** Setup help, feature questions, troubleshooting, configuration.

### CodeExpert — Technical Specialist
**Model:** Claude Sonnet 4.6 · **Avatar:** 💻

A senior engineer. Writes production-quality code, debugs methodically, designs systems. Shows full implementations — no pseudocode stubs. Reports bugs with exact file, line, and root cause.

**Good for:** Code review, debugging, architecture, implementation, system design.

## Starter Templates

These are created on first launch from `server/persona_templates.json`. You can edit, delete, or clone them.

### Architect — Technical Lead
**Avatar:** 🏗️

Thinks in systems — how components connect, where the failure modes are, what the right abstraction is.

### Developer — Software Engineer
**Avatar:** 💻

Implementation-focused. Give it a spec and it builds. Day-to-day coding work.

### Designer — UI/UX Specialist
**Avatar:** 🎨

Interfaces, layouts, visual systems, accessibility, user experience.

### Planner — Project Manager
**Avatar:** 📊

Milestones, tracking, coordination, task breakdowns, sprint planning.

### Writer — Content Specialist
**Avatar:** ✍️

Documentation, blog posts, emails, technical writing. Understands tone, audience, and structure.

### Assistant — Versatile Helper
**Avatar:** 🤖

General-purpose template for everyday tasks, research, and brainstorming.

!!! tip "Mix models and providers"
    Any persona can use any model — Claude, GPT, Grok, or a local model via Ollama/MLX. Assign each persona the model that fits its job best.

---

## Customizing a Persona

Every persona is fully editable. Change the model, name, avatar, role, or system prompt.

### From the UI

1. Click **+ New Channel** in the sidebar.
2. Hover over any persona card — a gear icon appears.
3. Click the gear to open the profile editor.
4. Change whatever you want — model, name, avatar, role, or system prompt.
5. Click **Save**.

Changes apply to all future channels using that persona.

### From the Admin Dashboard

Go to **Apex Dashboard > Personas & Models**. Each persona has an edit card.

### From the API

```bash
# List all personas
curl -k https://localhost:8300/api/profiles

# Update a persona's model
curl -k -X PUT https://localhost:8300/api/profiles/architect \
  -H 'Content-Type: application/json' \
  -d '{"model": "claude-opus-4-6"}'

# Create a new persona
curl -k -X POST https://localhost:8300/api/profiles \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Researcher",
    "slug": "researcher",
    "avatar": "🔬",
    "role_description": "Research specialist",
    "model": "grok-4",
    "system_prompt": "You are a research specialist. You search the web, synthesize findings, and cite sources."
  }'
```

> **Note:** With mTLS enabled, add `--cert state/ssl/client.crt --key state/ssl/client.key` to curl commands.

---

## Creating Your Own

The defaults are a starting point. Some ideas:

| Persona | Model | Why |
|---------|-------|-----|
| **Data Analyst** | Claude Opus 4.6 | Deep reasoning for statistical analysis, SQL, visualization. |
| **DevOps** | Claude Sonnet 4.6 | CI/CD, infrastructure, Docker, deployment, monitoring. |
| **Researcher** | Grok 4 | Web search, real-time news, competitive analysis. |
| **Tutor** | Claude Sonnet 4.6 | Patient explanations, Socratic questioning, learning support. |
| **Local Draft** | Ollama (local) | Free brainstorming. Draft locally, hand off to a cloud model for polish. |

### Model Selection Guide

| If you need... | Use |
|----------------|-----|
| Deep reasoning, complex analysis, long documents | Claude Opus 4.6 |
| Fast, capable general-purpose work | Claude Sonnet 4.6 |
| Web search, real-time information, X/Twitter | Grok 4 |
| Code generation with OpenAI's latest | GPT-5.4 (Codex CLI) |
| Free inference, no API costs, works offline | Any Ollama model |
| Apple Silicon optimized local inference | MLX model |
