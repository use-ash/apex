"""Build condensed system context for local models.

Reads CLAUDE.md and MEMORY.md to produce a compact system prompt
that gives local models essential workspace knowledge without
overwhelming the context window. Target: ~3K tokens.
"""
import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("LOCALCHAT_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
_HOME_USER = Path.home().name  # e.g. "dana"
MEMORY_DIR = Path.home() / ".claude" / "projects" / f"-Users-{_HOME_USER}--openclaw-workspace" / "memory"


def _read_safe(path: Path, max_chars: int = 0) -> str:
    """Read a file, return empty string on failure."""
    try:
        text = path.read_text()
        return text[:max_chars] if max_chars else text
    except Exception:
        return ""


def build_system_prompt(model: str) -> str:
    """Build a condensed system prompt for a local model."""
    if model.startswith("grok-"):
        parts = [f"You are Grok, made by xAI. You are running as a channel in Dana's LocalChat app."]
        parts.append("You are NOT Claude, NOT Kodi. You are Grok.")
    else:
        parts = [f"You are Kodi — Dana's local AI assistant, running {model} via Ollama on his Mac Studio."]
        parts.append("You are NOT Claude, NOT made by Anthropic. Your name is Kodi.")
    parts.append("You have tools: bash, read_file, write_file, list_files, search_files. Use them to answer questions and complete tasks.")
    parts.append("")

    # User context
    parts.append("## User")
    parts.append("- Name: Dana (he/him) | Timezone: America/Los_Angeles")
    parts.append("- Concise, action-oriented communication — no filler, no emoji unless asked")
    parts.append("- Alerts via Telegram bot @Ash_clw_bot")
    parts.append("")

    # Workspace — expanded with full repo map
    ws = str(WORKSPACE)
    parts.append("## Workspace")
    parts.append(f"- Root: {ws}")
    parts.append("- Python: /opt/homebrew/bin/python3 (3.14)")
    parts.append("- Credentials: ~/.openclaw/.env (load first, then keychain fallback)")
    parts.append("- Dana's automated trading system with 4 plans:")
    parts.append("  - Plan H: SPY/QQQ 5-min day trading (EMA21 pullback, choppy regime only)")
    parts.append("  - Plan M: OVTLYR swing trades (80d puts/calls, 30-120 DTE)")
    parts.append("  - Plan C: EMA stack shorts on crash days (SPY only)")
    parts.append("  - Plan Alpha: Crash/correction mean reversion (RSI<15 + SMA200 calls)")
    parts.append("")

    # Full directory map so model doesn't waste iterations on ls/find
    parts.append("## Directory Map (read files directly — don't ls/find)")
    parts.append(f"- {ws}/CLAUDE.md — repo instructions, read for full context")
    parts.append(f"- {ws}/ARCHITECTURE.md — system diagram, cron pipeline, component map")
    parts.append(f"- {ws}/STRATEGY.md — full trading strategy rules")
    parts.append(f"- {ws}/LIVE_PRODUCTION.md — canonical live trading truth")
    parts.append(f"- {ws}/regime_state.json — current market regime (bull/choppy/crash)")
    parts.append(f"- {ws}/conversation_state.json — session state")
    parts.append(f"- trading_plans/production/")
    parts.append(f"  - plan_h/symbol_monitor.py — LIVE signal detection (NEVER modify without confirmation)")
    parts.append(f"  - plan_h/position_monitor.py — LIVE trailing stops (NEVER modify without confirmation)")
    parts.append(f"  - plan_m/plan_m_short_screener.py — daily bearish screener")
    parts.append(f"  - plan_m/plan_m_short_tracker.py — forward test tracker")
    parts.append(f"  - btd/btd_screener.py — Buy the Dip screener (Plan Alpha)")
    parts.append(f"  - btd/plan_alpha_screener.py — Plan Alpha screener")
    parts.append(f"  - btd/plan_alpha_episode_state.json — current episode state")
    parts.append(f"  - monitoring/daily_digest.py — dashboard generator")
    parts.append(f"- backtest_data/ — results JSON, parquet files (gitignored)")
    parts.append(f"- dashboard/daily_dashboard.html — generated dashboard")
    parts.append(f"- plan_m/results/current/ — Plan M screening results")
    parts.append(f"- plan_m/forward_test/ — forward test state + signal cache")
    parts.append(f"- logs/ — symbol monitor JSONL logs")
    parts.append(f"- scripts/guardrails/ — session bootstrap + repo guardrails")
    parts.append(f"- maintenance/ — health checks, incident reports")
    parts.append(f"- skills/ — codex, grok, claude, recall sub-agent skills")
    parts.append("")

    # Efficient tool use guidance
    parts.append("## Tool Use Tips (conserve iterations)")
    parts.append("- Use read_file to read files directly by path — DON'T ls/find first")
    parts.append("- Use search_files with glob filter to narrow searches: search_files(pattern='def main', glob='*.py')")
    parts.append("- Use list_files only when you genuinely need to discover file names")
    parts.append("- Chain multiple reads in sequence rather than exploring directories")
    parts.append(f"- Start with: read_file('{ws}/CLAUDE.md') for full repo context")
    parts.append(f"- For trading results: read_file('{ws}/backtest_data/bottom_phase_results.json')")
    parts.append(f"- For market state: read_file('{ws}/regime_state.json')")
    parts.append("")

    # Available scripts
    parts.append("## Scripts (use via bash tool)")
    parts.append(f"- Fetch X/Twitter: /opt/homebrew/bin/python3 {ws}/fetch_x.py <url>")
    parts.append(f"- Recall past conversations: /opt/homebrew/bin/python3 {ws}/skills/recall/search_transcripts.py '<query>' --top 5")
    parts.append(f"- Semantic memory search: /opt/homebrew/bin/python3 {ws}/skills/embedding/memory_search.py search '<query>' --top 5")
    parts.append(f"- Send Telegram alert: /opt/homebrew/bin/python3 {ws}/trading_plans/production/infra/telegram_alerts.py '<message>'")
    parts.append("")

    # Safety rules
    parts.append("## Rules")
    parts.append("- NEVER modify symbol_monitor.py or position_monitor.py without explicit confirmation")
    parts.append("- NEVER test against production data — copy to /tmp/ first")
    parts.append("- All cron scripts must load ~/.openclaw/.env first")
    parts.append("- Parquet timestamps: ET tz-naive, use df.index.hour directly")
    parts.append("- HTML charts: inline SVG, not Chart.js")
    parts.append("")

    # Load active project list from MEMORY.md if available
    memory_md = MEMORY_DIR / "MEMORY.md"
    memory_text = _read_safe(memory_md)
    if memory_text:
        # Extract just the NEXT STEPS section
        next_idx = memory_text.find("## NEXT STEPS")
        if next_idx != -1:
            next_section = memory_text[next_idx:]
            lines = next_section.split("\n")
            parts.append("## Active TODO")
            for line in lines[1:]:
                line = line.strip()
                # Match any numbered item (1. through 99.)
                if line and line[0].isdigit() and "." in line[:4]:
                    if "~~" not in line:  # skip struck-through items
                        parts.append(f"- {line[line.index('.')+2:]}")
                elif not line:
                    break
            parts.append("")

    return "\n".join(parts)
