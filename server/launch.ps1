# Apex Server — Windows PowerShell launcher
# Usage: powershell -ExecutionPolicy Bypass -File server\launch.ps1

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$APEX_ROOT = Split-Path -Parent $SCRIPT_DIR

# Load .env (check standard locations)
$envCandidates = @(
    "$env:USERPROFILE\.apex\.env",
    "$env:USERPROFILE\.config\apex\.env",
    "$APEX_ROOT\.env"
)
if ($env:APEX_ENV_FILE -and (Test-Path $env:APEX_ENV_FILE)) {
    $envCandidates = @($env:APEX_ENV_FILE) + $envCandidates
}
foreach ($candidate in $envCandidates) {
    if (Test-Path $candidate) {
        Get-Content $candidate | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
                $parts = $line -split "=", 2
                $key = $parts[0].Trim()
                $val = $parts[1].Trim()
                [Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
        Write-Host "Loaded env from: $candidate"
    }
}

# SSL cert defaults
$SSL_DIR = "$APEX_ROOT\state\ssl"
if (-not $env:APEX_SSL_CERT) { $env:APEX_SSL_CERT = "$SSL_DIR\apex.crt" }
if (-not $env:APEX_SSL_KEY)  { $env:APEX_SSL_KEY  = "$SSL_DIR\apex.key" }
if (-not $env:APEX_SSL_CA)   { $env:APEX_SSL_CA   = "$SSL_DIR\ca.crt" }
$env:APEX_ROOT = $APEX_ROOT

# First-run check
if (-not (Test-Path $env:APEX_SSL_CA)) {
    Write-Host "SSL certificates not found. Run setup first:"
    Write-Host "  python $APEX_ROOT\setup.py"
    exit 1
}

Write-Host "=== Apex Server ==="
Write-Host "  Root:  $APEX_ROOT"
Write-Host "  Port:  $($env:APEX_PORT ?? '8300')"
Write-Host "  Model: $($env:APEX_MODEL ?? 'claude-sonnet-4-6')"
Write-Host "==================="

Set-Location $APEX_ROOT

# Use venv Python if available
$PYTHON = "$APEX_ROOT\.venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON)) { $PYTHON = "python" }

& $PYTHON "$SCRIPT_DIR\apex.py"
