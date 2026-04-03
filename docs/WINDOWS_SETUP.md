# Apex on Windows — Setup Guide & Lessons Learned

## Overview

Apex runs on Windows Server 2022 and Windows 10/11. The core server is cross-platform Python/FastAPI. This document covers the full setup process, platform-specific gotchas, and workarounds discovered during the first Windows deployment (April 2026).

---

## Prerequisites

| Software | Version | Notes |
|----------|---------|-------|
| Python | 3.12+ | Install with "Add to PATH" checked. Use the official installer from python.org. |
| Git | 2.40+ | git-for-windows. Needed to clone the repo. |
| Node.js | 18+ | Only needed if using Claude CLI (Codex backend). |

**NOT needed on Windows:**
- OpenSSL CLI — cert generation uses Python's `cryptography` library directly
- Chocolatey — direct installers are more reliable in automated setups
- WSL — everything runs native

---

## Installation

### 1. Clone the repo

```powershell
git clone https://github.com/use-ash/apex.git C:\apex
cd C:\apex
```

### 2. Create Python virtual environment

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Windows gotcha:** The venv Python path is `.venv\Scripts\python.exe`, not `.venv/bin/python3` (Unix). The setup wizard handles this automatically.

### 3. Generate TLS certificates

Apex requires mTLS (mutual TLS) — both server and client need certificates. Use the included Windows cert generator:

```powershell
.venv\Scripts\python.exe scripts\gen_certs_win.py <YOUR_IP_ADDRESS>
```

Replace `<YOUR_IP_ADDRESS>` with the machine's external IP (or `127.0.0.1` for local-only). This generates:

| File | Purpose |
|------|---------|
| `state\ssl\ca.crt` | Certificate Authority — trust this on clients |
| `state\ssl\ca.key` | CA private key — keep secure |
| `state\ssl\apex.crt` | Server certificate (includes IP SANs) |
| `state\ssl\apex.key` | Server private key |
| `state\ssl\client.p12` | Client certificate bundle — install on connecting devices |

The `.p12` password is `apex` (change in production).

**Why not OpenSSL CLI?** OpenSSL is not installed by default on Windows. The `gen_certs_win.py` script uses Python's `cryptography` library (already installed via requirements.txt) to generate all certs — no external tools needed.

### 4. Create configuration

Create `.env` file at `%USERPROFILE%\.apex\.env`:

```
APEX_HOST=0.0.0.0
APEX_PORT=8300
APEX_MODEL=grok-4-fast
XAI_API_KEY=your-xai-api-key
APEX_LOG_LEVEL=info
```

**Model choices without macOS Keychain:**
- Claude models require an OAuth token stored in macOS Keychain — **not available on Windows**
- Use Grok (`grok-4-fast`, `grok-4`) with an xAI API key, or
- Use local models via Ollama (`gemma4:latest`, `qwen3.5:35b-a3b`, etc.)
- Set `ANTHROPIC_API_KEY` in `.env` if you have a Claude API key (bypasses Keychain)

### 5. Open Windows Firewall

```powershell
New-NetFirewallRule -DisplayName "Apex Server" -Direction Inbound -Protocol TCP -LocalPort 8300 -Action Allow
```

### 6. Start the server

**Option A — PowerShell launcher (recommended):**
```powershell
powershell -ExecutionPolicy Bypass -File server\launch.ps1
```

**Option B — Direct:**
```powershell
$env:APEX_SSL_CERT = "C:\apex\state\ssl\apex.crt"
$env:APEX_SSL_KEY = "C:\apex\state\ssl\apex.key"
$env:APEX_SSL_CA = "C:\apex\state\ssl\ca.crt"
$env:APEX_HOST = "0.0.0.0"
$env:APEX_PORT = "8300"
$env:APEX_ROOT = "C:\apex"
.venv\Scripts\python.exe server\apex.py
```

### 7. Install client certificate

To connect from another machine (or browser on the same machine):

1. Copy `state\ssl\client.p12` to the client machine
2. **macOS:** Double-click → Keychain imports it. Also import `ca.crt` and trust it.
3. **Windows:** Double-click → Certificate Import Wizard. Install to "Personal" store.
4. **iOS:** AirDrop or email the `.p12` file. Install via Settings → Profile.
5. Navigate to `https://<server-ip>:8300`

---

## Platform-Specific Differences

### File Permissions (chmod)

Unix `chmod 0o600` has no equivalent on Windows. Apex uses `safe_chmod()` from `server/compat.py` which:
- On Unix: calls `os.chmod(path, mode)` normally
- On Windows: sets read/write flags via `stat.S_IWRITE | stat.S_IREAD`

This is transparent — no user action needed.

### Credential Storage

| Platform | Primary | Fallback |
|----------|---------|----------|
| macOS | Keychain (`security` CLI) | `.env` file |
| Windows | `.env` file | `.env` file |
| Linux | `.env` file | `.env` file |

macOS Keychain integration is skipped automatically on Windows. All credentials go in `.env`.

### Path Separators

`APEX_WORKSPACE` supports colon-separated multiple paths on Unix (e.g., `/path1:/path2`). On Windows, colons appear in drive letters (`C:\...`), so **use only a single workspace path** on Windows. Multi-workspace support on Windows is a known limitation.

### Python Virtual Environment

| Platform | Venv Python path |
|----------|-----------------|
| macOS/Linux | `.venv/bin/python3` |
| Windows | `.venv\Scripts\python.exe` |

The setup wizard (`setup.py`) and `launch.ps1` handle this automatically.

### Network Interface Detection

The setup wizard auto-detects local IPs for certificate SANs:
- macOS: parses `ifconfig`
- Linux: parses `ip addr`
- Windows: parses `ipconfig`

All three paths are implemented in `setup/bootstrap.py`.

---

## GCP Deployment Notes

### VM Setup

```bash
# Create Windows Server 2022 VM
gcloud compute instances create apex-windows \
  --project=PROJECT_ID \
  --zone=us-east1-b \
  --machine-type=e2-standard-2 \
  --image-family=windows-2022 \
  --image-project=windows-cloud \
  --boot-disk-size=50GB

# Open firewall
gcloud compute firewall-rules create allow-apex \
  --project=PROJECT_ID \
  --rules=tcp:8300 \
  --source-ranges=YOUR_IP/32 \
  --target-tags=apex-server

# Set password for RDP
gcloud compute reset-windows-password apex-windows \
  --project=PROJECT_ID \
  --zone=us-east1-b \
  --user=admin
```

### Lessons Learned from GCP Deployment

1. **SSH is not enabled by default on Windows VMs.** Use RDP or set `enable-windows-ssh=TRUE` in instance metadata, then install OpenSSH Server via `Add-WindowsCapability`.

2. **Startup scripts run as SYSTEM.** The `%USERPROFILE%` for SYSTEM is `C:\Windows\system32\config\systemprofile`, not `C:\Users\dana`. Create `.env` in both locations or set env vars explicitly.

3. **PowerShell treats stderr as errors.** Git, pip, and Python all write progress to stderr. PowerShell flags these as errors in logs even though they're not. Use `2>&1 | Out-Null` to suppress, or `$ErrorActionPreference = "Continue"` to prevent script termination.

4. **Chocolatey is unreliable in startup scripts.** The install sometimes leaves partial state that blocks re-runs. Use direct `.exe` installers from python.org instead.

5. **PATH not refreshed after installs.** After installing Python/Git via silent installers, the PATH update only applies to new processes. Explicitly add paths:
   ```powershell
   $env:Path = "C:\Python312;C:\Python312\Scripts;C:\Program Files\Git\cmd;$env:Path"
   ```

6. **PowerShell string interpolation breaks Python code.** Never embed Python code in PowerShell strings — curly braces `{}` and dollar signs `$` get interpreted. Write Python scripts to files and execute them.

7. **Unicode encoding.** Windows console defaults to cp1252, not UTF-8. Set `$env:PYTHONIOENCODING = "utf-8"` before running Python, or Python's print() will crash on emoji/special characters.

8. **`cryptography` pkcs12 import.** Use `from cryptography.hazmat.primitives.serialization import pkcs12` — not `serialization.pkcs12` (AttributeError on some versions).

9. **Zone capacity.** GCP zones can run out of capacity for specific machine types. If `ZONE_RESOURCE_POOL_EXHAUSTED`, try a different zone.

10. **Git safe.directory.** When running as SYSTEM, git requires `git config --global --add safe.directory C:/apex` to allow operations in directories owned by other users.

---

## Automated Deployment Script

For headless Windows deployment (GCP startup script, CI/CD, etc.), see the PowerShell bootstrap template at `server/launch.ps1`. Key steps:

1. Install Python 3.12 (silent, add to PATH)
2. Install Git (silent)
3. Clone repo
4. Create venv + install deps
5. Write `.env` with API keys
6. Generate certs via `scripts/gen_certs_win.py`
7. Open firewall port
8. Start server

---

## Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| No macOS Keychain | Claude OAuth doesn't work | Use `ANTHROPIC_API_KEY` in `.env` or use Grok/local models |
| Multi-workspace paths | Colon separator conflicts with drive letters | Use single workspace only |
| No launchd/systemd | Server doesn't auto-start on boot | Use Task Scheduler or run in terminal |
| No caffeinate | Machine may sleep | Disable sleep in Power Settings |
| File permission model | Unix chmod has no exact equivalent | `safe_chmod()` handles gracefully |

---

## Verified Working

- [x] Server starts on Windows Server 2022
- [x] mTLS certificate generation (pure Python)
- [x] Client certificate authentication
- [x] Grok model chat (xAI API)
- [x] Welcome bot (Guide persona)
- [x] Admin dashboard
- [x] WebSocket streaming
- [x] SQLite database
- [x] Setup wizard UI

*Last tested: April 2, 2026 — Windows Server 2022 on GCP (e2-standard-2)*
