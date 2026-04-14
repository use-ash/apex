#!/opt/homebrew/bin/python3
"""Canonical Store — unified read layer across all memory/context sources.

Merges memories from Apex SQLite, guidance.json, .subconscious/memory files,
and chatmine extractions into a single scored interface. Backend adapters
translate the canonical output into their native injection format.

Phase 1: Read-only. Does not modify any source. Existing injection paths
continue to work alongside this layer.
"""

import datetime
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Memory:
    text: str
    type: str               # invariant, correction, decision, context, task, pending
    confidence: float        # 0.0-1.0 unified
    source: str              # apex_db, guidance, chatmine, claude_memory, memory_file
    source_id: str = ""      # original ID for traceability
    created_at: str = ""
    ttl_days: int = 7
    # Invariant-specific
    context_when: str = ""
    enforce: str = ""
    avoid: str = ""

    def display_text(self) -> str:
        """Human-readable rendering for injection."""
        if self.type == "invariant" and self.context_when:
            return (f"When {self.context_when}: "
                    f"enforce {self.enforce}; avoid {self.avoid}")
        return self.text

    def char_len(self) -> int:
        """Total chars consumed when injected."""
        if self.type == "invariant":
            return len(self.context_when) + len(self.enforce) + len(self.avoid)
        return len(self.text)


@dataclass
class Skill:
    name: str
    description: str
    invocation: str          # backend-specific invocation string
    content: str = ""
    backend_native: bool = False
    source_path: str = ""


@dataclass
class ToolsPolicy:
    allowed: list = field(default_factory=list)
    denied: list = field(default_factory=list)
    permission_level: int = 2


@dataclass
class WorkspaceContext:
    project_md: str = ""
    memory_md: str = ""
    git_branch: str = ""
    git_recent: list = field(default_factory=list)
    skills_catalog: str = ""


@dataclass
class SessionState:
    session_id: str = ""
    prompt_count: int = 0
    context_fill_pct: float = 0.0
    phase: str = "explore"   # explore, consolidate, preserve, critical
    started_at: str = ""


@dataclass
class ContextEnvelope:
    """Full context payload for a single prompt, backend-agnostic."""
    backend: str = ""        # apex, codex, claude_code
    persona: str = ""
    memories: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    tools_policy: ToolsPolicy = field(default_factory=ToolsPolicy)
    workspace: WorkspaceContext = field(default_factory=WorkspaceContext)
    guidance: list = field(default_factory=list)
    session: SessionState = field(default_factory=SessionState)

    def total_chars(self) -> int:
        """Estimated total injection size."""
        total = len(self.persona)
        total += sum(m.char_len() for m in self.memories)
        total += sum(len(s.content) for s in self.skills)
        total += len(self.workspace.project_md)
        total += len(self.workspace.memory_md)
        total += sum(m.char_len() for m in self.guidance)
        return total


# ---------------------------------------------------------------------------
# Similarity (reuse digest.py's word-overlap approach)
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


# ---------------------------------------------------------------------------
# Canonical Store
# ---------------------------------------------------------------------------

class CanonicalStore:
    """Unified read layer across all memory/context sources."""

    def __init__(self):
        self._workspace = Path(config.WORKSPACE)
        self._state_dir = Path(config.STATE_DIR)

    # -- Memories ----------------------------------------------------------

    def get_memories(self,
                     types: list[str] = None,
                     min_confidence: float = 0.3,
                     max_items: int = 50,
                     deduplicate: bool = True) -> list[Memory]:
        """Merge memories from all sources, deduplicate, return scored list.

        Sources (in priority order):
          1. guidance.json (invariants, corrections, decisions, pending)
          2. chatmine extractions (bridged into guidance, also raw)
          3. .subconscious/memory/*.md files
        """
        all_memories = []

        # Source 1: guidance.json
        all_memories.extend(self._load_guidance_memories())

        # Source 2: chatmine claude extractions (unbridged)
        all_memories.extend(self._load_chatmine_memories())

        # Source 3: memory files
        all_memories.extend(self._load_memory_files())

        # Filter by type
        if types:
            all_memories = [m for m in all_memories if m.type in types]

        # Filter by confidence
        all_memories = [m for m in all_memories
                        if m.confidence >= min_confidence]

        # Filter by TTL
        now = datetime.datetime.now(datetime.timezone.utc)
        valid = []
        for m in all_memories:
            if m.created_at:
                try:
                    dt = datetime.datetime.fromisoformat(m.created_at)
                    age = (now - dt).days
                    if age > m.ttl_days:
                        continue
                except ValueError:
                    pass
            valid.append(m)
        all_memories = valid

        # Deduplicate by text similarity
        if deduplicate:
            all_memories = self._dedup_memories(all_memories)

        # Sort by confidence descending
        all_memories.sort(key=lambda m: m.confidence, reverse=True)

        return all_memories[:max_items]

    def get_guidance(self, min_confidence: float = 0.3) -> list[Memory]:
        """Convenience: get just invariants and corrections."""
        return self.get_memories(
            types=["invariant", "correction"],
            min_confidence=min_confidence,
        )

    # -- Workspace context -------------------------------------------------

    def get_workspace_context(self) -> WorkspaceContext:
        """Project context shared across all backends."""
        ctx = WorkspaceContext()

        # CLAUDE.md or APEX.md
        for name in ("CLAUDE.md", "APEX.md"):
            p = self._workspace / name
            if p.exists():
                content = p.read_text()
                ctx.project_md = content[:8192]  # 8K cap
                break

        # MEMORY.md
        mem_md = self._workspace / "memory" / "MEMORY.md"
        if mem_md.exists():
            ctx.memory_md = mem_md.read_text()[:4096]

        # Git state
        try:
            import subprocess
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._workspace)
            )
            ctx.git_branch = result.stdout.strip()

            result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._workspace)
            )
            ctx.git_recent = result.stdout.strip().split("\n")
        except Exception:
            pass

        return ctx

    # -- Skills ------------------------------------------------------------

    def get_skills(self, backend: str = "all") -> list[Skill]:
        """List available skills across all backends.

        Returns skills with backend-appropriate invocation hints.
        """
        skills = []

        # Shared workspace skills
        skills_dir = self._workspace / "skills"
        if skills_dir.exists():
            for md in skills_dir.rglob("*.md"):
                if md.name.startswith("."):
                    continue
                content = md.read_text()
                desc = ""
                # Extract description from frontmatter
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end > 0:
                        for line in content[3:end].split("\n"):
                            if line.strip().startswith("description:"):
                                desc = line.split(":", 1)[1].strip().strip('"\'')
                                break

                skills.append(Skill(
                    name=md.stem,
                    description=desc or md.stem,
                    invocation=self._skill_invocation(md.stem, backend),
                    content=content[:2048],
                    source_path=str(md),
                ))

        # Claude Code commands
        if backend in ("claude_code", "all"):
            cmd_dir = self._workspace / ".claude" / "commands"
            if cmd_dir.exists():
                for md in cmd_dir.glob("*.md"):
                    content = md.read_text()
                    skills.append(Skill(
                        name=md.stem,
                        description=content[:100].replace("\n", " ").strip(),
                        invocation=f"/{md.stem}",
                        content=content[:2048],
                        backend_native=True,
                        source_path=str(md),
                    ))

        return skills

    def _skill_invocation(self, name: str, backend: str) -> str:
        """Map skill name to backend-specific invocation."""
        if backend == "claude_code":
            return f"/{name}"
        elif backend == "codex":
            return f"@{name}"
        elif backend == "apex":
            return f"/skill {name}"
        return name

    # -- Tools policy ------------------------------------------------------

    def get_tools_policy(self, backend: str,
                         permission_level: int = 2) -> ToolsPolicy:
        """Resolve tool access for a backend."""
        policy = ToolsPolicy(permission_level=permission_level)

        if backend == "claude_code":
            # Read from settings.json and settings.local.json
            for path in [
                Path.home() / ".claude" / "settings.json",
                self._workspace / ".claude" / "settings.local.json",
            ]:
                if path.exists():
                    try:
                        d = json.loads(path.read_text())
                        perms = d.get("permissions", {})
                        policy.allowed.extend(perms.get("allow", []))
                        policy.denied.extend(perms.get("deny", []))
                    except (json.JSONDecodeError, OSError):
                        pass

        # Other backends: read from their respective configs
        # (Phase 2: wire in Apex tool_access.py, Codex hooks)

        return policy

    # -- Session state -----------------------------------------------------

    def get_session_state(self, session_id: str) -> SessionState:
        """Current session metadata."""
        ss = SessionState(session_id=session_id)
        session = state.get_session(session_id)
        if session:
            ss.prompt_count = session.get("prompt_count", 0)
            ss.started_at = session.get("started_at", "")
        return ss

    # -- Build envelope ----------------------------------------------------

    def build_envelope(self, backend: str,
                       session_id: str = "",
                       persona: str = "",
                       query: str = "") -> ContextEnvelope:
        """Build a complete ContextEnvelope for a backend."""
        return ContextEnvelope(
            backend=backend,
            persona=persona,
            memories=self.get_memories(),
            skills=self.get_skills(backend),
            tools_policy=self.get_tools_policy(backend),
            workspace=self.get_workspace_context(),
            guidance=self.get_guidance(),
            session=self.get_session_state(session_id),
        )

    # -- Private: source loaders -------------------------------------------

    def _load_guidance_memories(self) -> list[Memory]:
        """Load from guidance.json."""
        guidance = state.read_guidance()
        memories = []
        for item in guidance.get("items", []):
            itype = item.get("type", "context")
            if itype == "invariant":
                memories.append(Memory(
                    text=item.get("text", ""),
                    type="invariant",
                    confidence=item.get("confidence", 0.85),
                    source="guidance",
                    source_id=f"guidance:{item.get('created_at', '')}",
                    created_at=item.get("created_at", ""),
                    ttl_days=item.get("ttl_days", 30),
                    context_when=item.get("context", ""),
                    enforce=item.get("enforce", ""),
                    avoid=item.get("avoid", ""),
                ))
            else:
                memories.append(Memory(
                    text=item.get("text", ""),
                    type=itype,
                    confidence=item.get("confidence", 0.5),
                    source="guidance",
                    source_id=f"guidance:{item.get('created_at', '')}",
                    created_at=item.get("created_at", ""),
                    ttl_days=item.get("ttl_days", 7),
                ))
        return memories

    def _load_chatmine_memories(self) -> list[Memory]:
        """Load from chatmine/claude/ day files (most recent sessions only)."""
        chatmine_dir = self._state_dir / "chatmine" / "claude"
        if not chatmine_dir.exists():
            return []

        memories = []
        today = datetime.date.today().isoformat()

        # Only load from sessions modified in last 7 days
        cutoff = datetime.datetime.now() - datetime.timedelta(days=7)

        for session_dir in chatmine_dir.iterdir():
            if not session_dir.is_dir():
                continue
            if session_dir.stat().st_mtime < cutoff.timestamp():
                continue

            # Only read today's file (others should already be bridged)
            day_file = session_dir / f"{today}.json"
            if not day_file.exists():
                continue

            try:
                data = json.loads(day_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            sid = session_dir.name[:12]

            for lesson in data.get("lessons", []):
                memories.append(Memory(
                    text=str(lesson),
                    type="correction",
                    confidence=0.4,
                    source="chatmine",
                    source_id=f"chatmine:{sid}:{today}",
                    created_at=datetime.datetime.now(
                        datetime.timezone.utc).isoformat(),
                    ttl_days=7,
                ))

            for decision in data.get("decisions", []):
                memories.append(Memory(
                    text=str(decision),
                    type="decision",
                    confidence=0.4,
                    source="chatmine",
                    source_id=f"chatmine:{sid}:{today}",
                    created_at=datetime.datetime.now(
                        datetime.timezone.utc).isoformat(),
                    ttl_days=7,
                ))

        return memories

    def _load_memory_files(self) -> list[Memory]:
        """Load from .subconscious/memory/*.md files."""
        mem_dir = self._state_dir / "memory"
        if not mem_dir.exists():
            return []

        memories = []
        for md in mem_dir.glob("*.md"):
            content = md.read_text().strip()
            if not content or len(content) < 10:
                continue

            # Parse frontmatter if present
            name = md.stem
            mtype = "context"
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    for line in content[3:end].split("\n"):
                        line = line.strip()
                        if line.startswith("type:"):
                            mtype = line.split(":", 1)[1].strip()

            mtime = datetime.datetime.fromtimestamp(
                md.stat().st_mtime, tz=datetime.timezone.utc
            ).isoformat()

            memories.append(Memory(
                text=content[:2000],
                type=mtype,
                confidence=0.6,
                source="memory_file",
                source_id=f"file:{name}",
                created_at=mtime,
                ttl_days=30,
            ))

        return memories

    def _dedup_memories(self, memories: list[Memory],
                        threshold: float = 0.7) -> list[Memory]:
        """Remove near-duplicate memories by text similarity.

        Higher-confidence items are kept when duplicates are found.
        """
        # Sort by confidence desc so we keep the best version
        sorted_mems = sorted(memories, key=lambda m: m.confidence, reverse=True)
        unique = []
        for mem in sorted_mems:
            display = mem.display_text()
            is_dup = False
            for existing in unique:
                if _similarity(display, existing.display_text()) > threshold:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(mem)
        return unique


# ---------------------------------------------------------------------------
# CLI — test/debug interface
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Canonical Store — unified memory reader")
    parser.add_argument("--memories", action="store_true", help="List all memories")
    parser.add_argument("--guidance", action="store_true", help="List guidance items")
    parser.add_argument("--skills", type=str, default="", help="List skills for backend (apex/codex/claude_code)")
    parser.add_argument("--workspace", action="store_true", help="Show workspace context")
    parser.add_argument("--envelope", type=str, default="", help="Build full envelope for backend")
    parser.add_argument("--stats", action="store_true", help="Show source statistics")
    args = parser.parse_args()

    store = CanonicalStore()

    if args.stats:
        mems = store.get_memories(deduplicate=False, min_confidence=0.0)
        by_source = {}
        by_type = {}
        for m in mems:
            by_source[m.source] = by_source.get(m.source, 0) + 1
            by_type[m.type] = by_type.get(m.type, 0) + 1

        deduped = store.get_memories(min_confidence=0.0)
        print(f"Total memories (raw): {len(mems)}")
        print(f"Total memories (deduped): {len(deduped)}")
        print(f"\nBy source:")
        for src, count in sorted(by_source.items()):
            print(f"  {src}: {count}")
        print(f"\nBy type:")
        for t, count in sorted(by_type.items()):
            print(f"  {t}: {count}")

    elif args.memories:
        for m in store.get_memories():
            print(f"  [{m.type}] ({m.source}, {m.confidence:.2f}) "
                  f"{m.display_text()[:100]}")

    elif args.guidance:
        for m in store.get_guidance():
            print(f"  [{m.type}] ({m.confidence:.2f}) "
                  f"{m.display_text()[:120]}")

    elif args.skills:
        for s in store.get_skills(args.skills):
            native = " [native]" if s.backend_native else ""
            print(f"  {s.name}: {s.invocation}{native} — {s.description[:60]}")

    elif args.workspace:
        ws = store.get_workspace_context()
        print(f"Branch: {ws.git_branch}")
        print(f"Project MD: {len(ws.project_md)} chars")
        print(f"Memory MD: {len(ws.memory_md)} chars")
        if ws.git_recent:
            print(f"Recent commits:")
            for c in ws.git_recent[:3]:
                print(f"  {c}")

    elif args.envelope:
        env = store.build_envelope(args.envelope)
        print(f"Backend: {env.backend}")
        print(f"Memories: {len(env.memories)}")
        print(f"Guidance: {len(env.guidance)}")
        print(f"Skills: {len(env.skills)}")
        print(f"Total chars: {env.total_chars()}")

    else:
        # Default: stats
        store_instance = CanonicalStore()
        mems = store_instance.get_memories(min_confidence=0.0)
        print(f"{len(mems)} memories across all sources")
        print("Run with --stats, --memories, --guidance, --skills BACKEND, --workspace, or --envelope BACKEND")
