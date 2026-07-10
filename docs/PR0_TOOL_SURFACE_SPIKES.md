# PR0 — Unified Tool Surface Spikes (2026-07-09)

Raw artifacts: `/tmp/apex-pr0-spike/` (local machine; not committed).

## 1. Grok temp `GROK_HOME` + resume + OIDC

**Setup**
- `GROK_HOME=/tmp/apex-pr0-spike/home`
- **Symlink:** `auth.json` → `~/.grok/auth.json`, `sessions/` → `~/.grok/sessions`
- **Symlink all other top-level entries** except `config.toml` (copied + MCP merge)
- Observed real home top-level: `auth.json`, `sessions/`, `config.toml`, `active_sessions.json`, `active_sessions.lock`, `agent_id`, `bin/`, `bundled/`, `completions/`, `docs/`, `downloads/`, `logs/`, `managed_config.lock`, `models_cache.json`, `README.md`, `skills/`, `upload_queue/`, `vendor/`

**Results**
| Check | Result |
|-------|--------|
| OIDC / no login prompt | Pass (no login/auth prompt; turn completed) |
| MCP list under temp home | Pass — `grok mcp list` shows filesystem from merged config |
| `grok mcp doctor filesystem` | Healthy — 14 tools, handshake OK |
| Multi-turn `-r <sessionId>` | Pass — turn1 `SPIKEOK`, turn2 recalled `SPIKEOK`, same `sessionId` |

**Locked algorithm for PR2:** copy+merge `config.toml`; symlink `auth.json` + `sessions/` + other top-level except config; never invent minimal config; never delete real home.

## 2. Grok project MCP ignore flag

| Source | Loaded? | Disable flag? |
|--------|---------|---------------|
| User `GROK_HOME/config.toml` | Yes | N/A (Apex owns temp config) |
| Project `.grok/config.toml` | **Yes** (`project_rogue` scope=project) | **No** global ignore flag found |
| Project `.mcp.json` | **Yes** (`rogue_mcpjson`) | Loaded unless Claude import marker (docs); **no CLI flag** to force-off |
| Cursor/Claude compat | Docs: `[compat.cursor] mcps=false` / `GROK_CURSOR_MCPS_ENABLED=0` (and Claude twin) | Yes for **compat only** |

**Conclusion:** Residual project MCP risk accepted. P1 must **log** if `.grok/config.toml` or `.mcp.json` exists under workspace. Prefer temp cwd without project MCP when possible; cannot fully suppress project MCP via env in current CLI.

## 3. Grok filesystem MCP wire names + `--deny`

**Raw tools** (stdio list_tools) → wire form `filesystem__<name>` (docs + model `search_tool` agree):

| Category | Wire names |
|----------|------------|
| Read | `filesystem__read_file`, `filesystem__read_text_file`, `filesystem__read_media_file`, `filesystem__read_multiple_files`, `filesystem__list_directory`, `filesystem__list_directory_with_sizes`, `filesystem__directory_tree`, `filesystem__search_files`, `filesystem__get_file_info`, `filesystem__list_allowed_directories` |
| **Write (L1 deny)** | `filesystem__write_file`, `filesystem__edit_file`, `filesystem__create_directory`, `filesystem__move_file` |

**Working deny argv (verified):**
```
--deny "MCPTool(filesystem__write_file)"
--deny "MCPTool(filesystem__edit_file)"
--deny "MCPTool(filesystem__create_directory)"
--deny "MCPTool(filesystem__move_file)"
```
Model attempted write → blocked by permission policy → replied `DENY_WORKED`; file absent.

## 4. Codex `-c` multi-server inject + resume

**Working inject shape (nested keys; table form flaky):**
```bash
codex exec -c 'mcp_servers.fs_spike.command="npx"' \
  -c 'mcp_servers.fs_spike.args=["-y","@modelcontextprotocol/server-filesystem","/tmp/apex-pr0-ws"]' \
  -c 'mcp_servers.echo_spike.command="/bin/echo"' \
  -c 'mcp_servers.echo_spike.args=["hi"]' \
  -c 'mcp_servers.echo_spike.env={FOO="bar"}' ...
```

**Wire names:** `mcp__<server>.<tool>` e.g. `mcp__fs_spike.write_file` (not `server__tool`).

**Resume:** `codex exec resume <session_id> [PROMPT]` keeps conversation on real `CODEX_HOME` (`~/.codex/sessions/...`). Re-pass same `-c mcp_servers.*` on resume for MCP attachment. Verified `RESUME_OK` / `RESUME_MCP_OK`.

**Home policy:** Prefer **real `CODEX_HOME` + `-c` overlays**. Do not move sessions.

## 5. Codex write fine-deny

| Approach | Result |
|----------|--------|
| `tools.disabled_tools=[...]` | **Invalid** under `--strict-config` (`unknown configuration field`) |
| `mcp_servers.<name>.tools.disabled_tools` | Wrong type (expects `auto`/`prompt`/`approve`) |
| **`mcp_servers.<name>.enabled_tools=[...]`** | **Works** — allowlist only listed tools; `write_file` not present when omitted |
| **`mcp_servers.<name>.disabled_tools=[...]`** | Accepted by strict-config (denylist shape available) |

**L1 policy for PR3:** attach filesystem with  
`enabled_tools=["read_file","read_text_file","read_media_file","read_multiple_files","list_directory","list_directory_with_sizes","directory_tree","search_files","get_file_info","list_allowed_directories"]`  
(or omit server if allowlist fails for a server).

## 6. Codex API-key auth path

| Path | Status |
|------|--------|
| `CODEX_HOME` (default `~/.codex`) | **Live** — `auth.json`, sessions, config |
| `CODEX_CONFIG_DIR` | **Not in binary** — dead |
| `~/.codex-api` | **Empty dir** — Apex still sets `CODEX_CONFIG_DIR` for o3/o4-mini; **ineffective** |
| Auth materials | ChatGPT login → `~/.codex/auth.json`; API key via `OPENAI_API_KEY` / `CODEX_API_KEY` env or `codex login --with-api-key` (stdin) stored in `auth.json` |

**PR3 action:** stop relying on `CODEX_CONFIG_DIR=~/.codex-api`; keep real `CODEX_HOME` + env key if needed.

## Summary for projectors

| Backend | Isolation | Auth/session | L1 write control |
|---------|-----------|--------------|------------------|
| `xai` (Grok) | Temp `GROK_HOME`, symlink sessions+auth, merge config | OIDC via linked `auth.json` | `--deny MCPTool(filesystem__write_file)` (+ edit/create/move) |
| `codex` | Real `CODEX_HOME` + nested `-c mcp_servers.*` | `~/.codex/auth.json` / env keys | `mcp_servers.<name>.enabled_tools` read-only allowlist |
