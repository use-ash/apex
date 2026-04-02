# Group Channels — Multi-Agent Collaboration

Groups are where Apex becomes something you can't get anywhere else. Instead of talking to one AI at a time, you put multiple agents in one room and let them work together.

**What makes this different from just having multiple chat windows?** In a group, agents can see each other's messages. They respond to @mentions, build on each other's work, and hand off tasks — all in one conversation thread that you can follow.

---

## Create Your First Group

1. Click **+ New Channel** in the sidebar.
2. Click **New Group** (instead of selecting a single persona).
3. Give it a name — something that describes the purpose: "Product Team", "Code Review", "Research Lab".
4. Add members — select 2 or more personas from the list. Each agent brings its own model and expertise.
5. Click **Create**.

The group appears in your sidebar with a member count badge.

---

## Talking to Agents in a Group

### @mention a specific agent

Type `@` in the message field to see the agent roster. Select an agent to direct your message to them.

```
@Architect review this database schema for scalability issues
```

Only Architect responds. Other agents see the exchange but stay quiet unless mentioned.

### Talk to the room

Send a message without an @mention. The group's primary agent (the first one listed) responds by default.

> **Coming soon:** `@all` broadcasts to every agent in the group simultaneously.

### Agent-to-agent handoffs

Agents can @mention each other. When Architect finishes a design spec, it can hand off to Developer:

```
Architect: Here's the schema. @Developer — implement this with the migration.
Developer: On it. I'll create the migration file and the model class...
```

This is the collaboration pattern that makes groups powerful. You set the direction, agents coordinate the work.

---

## Group Ideas

### Product Team
| Member | Model | Role in group |
|--------|-------|---------------|
| Architect | Claude Opus 4.6 | Technical lead, makes architecture decisions |
| Developer | Claude Sonnet 4.6 | Implements what Architect designs |
| Designer | Claude Sonnet 4.6 | Reviews UX, pushes back on poor user experience |

**Use for:** Feature planning, code review, design critique. Give the team a feature request and watch them break it down, debate trade-offs, and produce a spec.

### Research Lab
| Member | Model | Role in group |
|--------|-------|---------------|
| Researcher | Grok 4 | Web search, current events, source finding |
| Analyst | Claude Opus 4.6 | Deep analysis, synthesis, statistical reasoning |
| Writer | Claude Sonnet 4.6 | Drafts the final report in clean prose |

**Use for:** Market research, competitive analysis, literature review. Researcher finds the raw info, Analyst synthesizes it, Writer produces the deliverable.

### Code Review Board
| Member | Model | Role in group |
|--------|-------|---------------|
| Architect | Claude Opus 4.6 | Architecture-level review |
| Codex | GPT-5.4 | Implementation-level review, catches bugs |
| DevOps | Claude Sonnet 4.6 | Deployment, CI/CD, security review |

**Use for:** PR reviews, security audits, deployment planning. Paste a diff and get three perspectives.

### Operations Room
| Member | Model | Role in group |
|--------|-------|---------------|
| Architect | Claude Opus 4.6 | Technical decisions, system design |
| Codex | GPT-5.4 | Background builds and code generation |
| Operations | Claude Sonnet 4.6 | Planning, tracking, coordination |
| Designer | Claude Sonnet 4.6 | UX review and user-facing design |

**Use for:** Running your whole project. This is the "War Room" — set tasks, coordinate agents, track progress.

---

## Tips for Effective Groups

### Keep groups focused
A "Product Team" group works better than a "Everything" group. When agents know the context of the room, their responses are more relevant.

### Use the right models for the right roles
Put the expensive model (Opus) on the agent that needs deep reasoning. Put a fast model (Sonnet) on agents that do implementation work. Put a local model on the utility agent that does quick lookups.

### Let agents hand off to each other
The most powerful pattern is: you give a directive, and agents orchestrate the rest. "Build a REST API for user management" → Architect designs it → Developer implements it → you review.

### One primary, many specialists
Every group has a primary agent (the first member). This agent responds to bare messages (no @mention). Make the primary your project lead — the one who understands context and delegates.

---

## Group Settings

Click the ⚙️ gear icon next to the group name to access:

- **Rename** the group
- **Add/remove members**
- **Change the primary agent** (who responds to bare messages)
- **View conversation history**

---

## Next Steps

- **[Build Your AI Team](PERSONAS.md)** — Create custom personas before adding them to groups.
- **[Getting Started](GETTING_STARTED.md)** — Full setup guide if you haven't installed Apex yet.
