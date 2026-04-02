# Build Your AI Team

Apex ships with six ready-to-use AI personas. Each has a name, a role, a model, and a system prompt that shapes how it thinks and responds. You can use them as-is, customize them, or build your own from scratch.

**Think of personas like hiring.** You wouldn't ask a designer to review your database schema, and you wouldn't ask a DevOps engineer to write marketing copy. Personas let you give each AI a specialty and a voice.

---

## The Default Team

These are created automatically on first launch. Each one is tuned for a different kind of work — and a different model. The right model for the job means better results and lower costs.

### Architect — Technical Lead
**Model:** Claude Opus 4.6 · **Avatar:** 🏗️

The senior engineer in the room. Architect thinks in systems — how components connect, where the failure modes are, what the right abstraction is. Runs on Opus for deep reasoning on complex architectural decisions.

**Good for:** System design, code review, technical specifications, debugging complex issues, making trade-off decisions.

### Developer — Software Engineer
**Model:** Claude Sonnet 4.6 · **Avatar:** 💻

Writes code. Developer is more implementation-focused than Architect — give it a spec and it builds. Sonnet is fast and capable for day-to-day coding work.

**Good for:** Writing code, refactoring, unit tests, implementing features, fixing bugs.

### Codex — Background Coder
**Model:** GPT-5.4 (OpenAI) · **Avatar:** 🧬

Runs tasks in the background using OpenAI's Codex CLI. Hand off long-running refactors, migrations, or boilerplate generation while you keep working. Different model, different strengths.

**Good for:** Background tasks, large refactors, parallel code generation, migrations, boilerplate.

### Researcher — Web Intelligence
**Model:** Grok 4 (xAI) · **Avatar:** 🔍

Searches the web and X/Twitter in real time. Grok's native search means no tool-calling overhead — it just knows what's happening right now. Use it for market research, competitive analysis, or any question that needs live data.

**Good for:** Web research, real-time news, competitive analysis, market data, trend monitoring.

### Writer — Content Specialist
**Model:** Claude Sonnet 4.6 · **Avatar:** ✍️

Writes human-quality prose. Documentation, blog posts, emails, technical writing. Writer understands tone, audience, and structure.

**Good for:** Documentation, emails, blog posts, READMEs, editing, research summaries.

### Assistant — Local Utility
**Model:** Ollama (Qwen 3.5) · **Avatar:** 🤖

Free and fast. Runs entirely on your machine with no API calls and no internet. Use Assistant for quick questions, brainstorming, and anything where speed matters more than depth.

**Good for:** Quick Q&A, brainstorming, drafts, calculations, anything where you don't want to burn API credits.

!!! tip "Every model in one team"
    The default team uses four different providers: Claude (Anthropic), GPT (OpenAI), Grok (xAI), and a local model (Ollama). Each persona plays to its model's strengths. You can reassign any persona to any model — this is just the recommended starting point.

---

## Customizing a Persona

Every persona is fully editable. Change the model, name, avatar, role, or system prompt to match your workflow.

### From the UI

1. Click **+ New Channel** in the sidebar.
2. You'll see persona cards. Hover over any card — a ⚙️ gear icon appears.
3. Click the gear to open the profile editor.
4. Change whatever you want — model, name, avatar, role description, or system prompt.
5. Click **Save**.

Changes apply to all future channels using that persona.

### From the Admin Dashboard

Go to `/admin` → **Personas & Models**. Each persona has an edit card where you can change the model assignment, system prompt, and metadata.

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

> **Note:** If you're using mTLS, add `--cert state/ssl/client.crt --key state/ssl/client.key` to your curl commands.

---

## Creating Your Own Personas

The default team is a starting point. Here are some ideas for custom personas:

| Persona | Model | Why |
|---------|-------|-----|
| **Data Analyst** | Claude Opus 4.6 | Deep reasoning for statistical analysis, SQL, data visualization. |
| **DevOps** | Claude Sonnet 4.6 | CI/CD, infrastructure, Docker, deployment scripts, monitoring. |
| **Designer** | Claude Sonnet 4.6 | UX review, wireframes, design critique, accessibility audits. |
| **Planner** | GPT-5.4 (Codex) | Task breakdowns, sprint planning, prioritization, timelines. |
| **Tutor** | Claude Sonnet 4.6 | Patient explanations, Socratic questioning, learning support. |
| **Local Draft** | Ollama (Qwen 3.5) | Free brainstorming. Draft ideas locally, then hand off to a cloud model for polish. |

### Model Selection Guide

| If you need... | Use |
|----------------|-----|
| Deep reasoning, complex analysis, long documents | Claude Opus 4.6 |
| Fast, capable general-purpose work | Claude Sonnet 4.6 |
| Web search, real-time information, X/Twitter | Grok 4 |
| Code generation with OpenAI's latest | GPT-5.4 (Codex) |
| Free inference, no API costs, works offline | Any Ollama model |
| Apple Silicon optimized local inference | MLX model |

### Mix Models for Cost Efficiency

The default team already does this — expensive models where reasoning matters, fast models for daily work, free models for quick tasks:

```
Architect   →  Claude Opus 4.6      (deep reasoning)
Developer   →  Claude Sonnet 4.6    (fast coding)
Codex       →  GPT-5.4              (background tasks)
Researcher  →  Grok 4               (web search)
Writer      →  Claude Sonnet 4.6    (prose quality)
Assistant   →  Ollama Qwen 3.5      (free, offline)
```

This way you're only paying for intelligence where it matters.

---

## How Personas Work Under the Hood

When you create a channel with a persona:
1. The channel inherits the persona's model and system prompt.
2. The persona's system prompt is prepended to every message.
3. Memory injection (APEX.md, MEMORY.md, whisper) still applies on top.
4. The model selector is locked to the persona's model — to change models, edit the persona.

### Persona Templates

Default personas are defined in `server/persona_templates.json`. The server seeds them on startup using `INSERT OR IGNORE` — existing profiles are never overwritten.

To add new default personas, add entries to the JSON and restart the server. To disable auto-seeding, set `"seed_default_profiles": false` in `config.json`.

---

## Next Steps

- **[Set Up a Group Chat](GROUPS.md)** — Put multiple personas in one room and let them collaborate.
- **[Getting Started](GETTING_STARTED.md)** — Full setup guide if you haven't installed Apex yet.
