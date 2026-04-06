#!/usr/bin/env bash
# Apex Installer — cross-platform bootstrap script.
#
# Finds Python 3.10+, creates a venv, installs dependencies,
# and launches the interactive setup wizard.
#
# Usage:
#   ./install.sh              Full interactive wizard
#   ./install.sh --fast       Quick setup (certs + launch)
#   ./install.sh --help       Show all options
#
# On macOS, double-click "Install Apex.command" instead.

set -euo pipefail

# ---------------------------------------------------------------------------
# Self-locate
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
SETUP_PY="$SCRIPT_DIR/setup.py"

# ---------------------------------------------------------------------------
# Terminal polish
# ---------------------------------------------------------------------------

# Set window title
printf '\033]0;Apex Setup\007'

# Colors (respect NO_COLOR)
if [ -z "${NO_COLOR:-}" ] && [ -t 1 ]; then
    BOLD='\033[1m'
    CYAN='\033[1;36m'
    GREEN='\033[1;32m'
    YELLOW='\033[1;33m'
    RED='\033[1;31m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    BOLD='' CYAN='' GREEN='' YELLOW='' RED='' DIM='' RESET=''
fi

banner() {
    clear
    printf "${CYAN}"
    printf '  ================================================\n'
    printf '                   Apex Setup\n'
    printf '  ================================================\n'
    printf "${RESET}\n"
}

ok()   { printf "  ${GREEN}[OK]${RESET}  %s\n" "$1"; }
err()  { printf "  ${RED}[ERR]${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}[!]${RESET}  %s\n" "$1"; }
info() { printf "  ${DIM}%s${RESET}\n" "$1"; }

# ---------------------------------------------------------------------------
# Cleanup / error trap
# ---------------------------------------------------------------------------

on_exit() {
    local code=$?
    if [ $code -ne 0 ] && [ $code -ne 130 ]; then
        echo ""
        err "Setup exited with an error (code $code)."
        echo ""
        info "If you need help, open an issue at:"
        info "  https://github.com/use-ash/apex/issues"
        echo ""
        # Keep terminal open so user can read the error
        if [ -t 0 ]; then
            printf "  Press any key to close... "
            read -r -n 1 -s 2>/dev/null || true
            echo ""
        fi
    fi
}
trap on_exit EXIT

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

detect_platform() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"

    case "$OS" in
        Darwin) OS_LABEL="macOS" ;;
        Linux)  OS_LABEL="Linux" ;;
        *)      OS_LABEL="$OS" ;;
    esac

    ok "$OS_LABEL ($ARCH)"
}

# ---------------------------------------------------------------------------
# Python detection
# ---------------------------------------------------------------------------

PYTHON=""

# Check if a Python binary is 3.10+. Sets PYTHON on success.
_check_python_version() {
    local candidate="$1"
    local ver
    ver="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || return 1
    local major minor
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
        PYTHON="$candidate"
        ok "Python $ver ($candidate)"
        return 0
    fi
    return 1
}

find_python() {
    # Prefer existing venv Python — avoids re-searching system PATH
    if [ -x "$VENV_DIR/bin/python3" ]; then
        if _check_python_version "$VENV_DIR/bin/python3"; then
            return 0
        fi
    fi

    # Search system Python
    local candidates=()

    if command -v python3 &>/dev/null; then
        candidates+=("$(command -v python3)")
    fi

    # macOS Homebrew locations
    if [ "$OS" = "Darwin" ]; then
        for p in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
            [ -x "$p" ] && candidates+=("$p")
        done
    fi

    for candidate in "${candidates[@]}"; do
        if _check_python_version "$candidate"; then
            return 0
        fi
    done

    # Not found
    err "Python 3.10+ is required but was not found."
    echo ""
    if [ "$OS" = "Darwin" ]; then
        info "To install Python on macOS:"
        echo ""
        info "  Option 1 (Homebrew):  brew install python@3.12"
        info "  Option 2 (Official):  https://www.python.org/downloads/"
    else
        info "To install Python on Linux:"
        echo ""
        info "  Ubuntu/Debian:  sudo apt install python3 python3-venv"
        info "  Fedora/RHEL:    sudo dnf install python3"
        info "  Arch:           sudo pacman -S python"
    fi
    echo ""
    info "After installing Python, run this installer again."
    return 1
}

# ---------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------

setup_venv() {
    if [ -x "$VENV_DIR/bin/python3" ]; then
        ok "Virtual environment exists"
    else
        info "Creating virtual environment..."
        "$PYTHON" -m venv "$VENV_DIR" || {
            err "Failed to create virtual environment."
            if [ "$OS" = "Linux" ]; then
                info "On Debian/Ubuntu, you may need: sudo apt install python3-venv"
            fi
            return 1
        }
        ok "Virtual environment created"
    fi

    # Always sync dependencies (handles upgrades between versions)
    info "Installing dependencies..."
    "$VENV_DIR/bin/python3" -m pip install -q --upgrade pip 2>/dev/null || true
    "$VENV_DIR/bin/python3" -m pip install -q --upgrade -r "$REQUIREMENTS" || {
        err "pip install failed. Check your network connection."
        return 1
    }
    # Jupyter deps are optional but enable the execute_code tool (stateful Python).
    # Install separately so a build failure doesn't break the main install.
    if ! "$VENV_DIR/bin/python3" -c "import jupyter_client" 2>/dev/null; then
        info "Installing Jupyter kernel (for execute_code tool)..."
        "$VENV_DIR/bin/python3" -m pip install -q jupyter_client ipykernel 2>/dev/null && \
            ok "Jupyter kernel installed" || \
            warn "Jupyter install failed (execute_code tool will be unavailable)"
    fi
    ok "Dependencies installed"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

banner

printf "  ${BOLD}Checking system...${RESET}\n\n"

detect_platform
find_python

echo ""
printf "  ${BOLD}Preparing environment...${RESET}\n\n"

setup_venv

# ---------------------------------------------------------------------------
# Create `apex` CLI wrapper
# ---------------------------------------------------------------------------

BIN_DIR="$SCRIPT_DIR/.venv/bin"
APEX_CLI="$BIN_DIR/apex"

_create_apex_wrapper() {
    [ -d "$BIN_DIR" ] || return 1
    cat > "$APEX_CLI" <<INNEREOF
#!/usr/bin/env bash
# Apex CLI — generated by install.sh
APEX_ROOT="$SCRIPT_DIR"
exec "\$APEX_ROOT/.venv/bin/python3" "\$APEX_ROOT/setup.py" "\$@"
INNEREOF
    chmod +x "$APEX_CLI"
}

_create_apex_wrapper || warn "Could not create apex CLI wrapper (will retry after setup)"

echo ""
printf "  ${BOLD}Launching setup wizard...${RESET}\n\n"
info "─────────────────────────────────────────────────"
echo ""

# Hand off to the Python wizard
"$VENV_DIR/bin/python3" "$SETUP_PY" "$@"
SETUP_EXIT=$?

# Ensure wrapper exists after setup (belt-and-suspenders)
if [ ! -x "$APEX_CLI" ]; then
    _create_apex_wrapper 2>/dev/null || true
fi

# Show PATH instructions (only on successful first-time setup)
if [ $SETUP_EXIT -eq 0 ] && [ -x "$APEX_CLI" ]; then
    # Check if apex is already on PATH
    if ! command -v apex &>/dev/null; then
        echo ""
        printf "  ${CYAN}─────────────────────────────────────────────────${RESET}\n"
        printf "  ${BOLD}One more step:${RESET} Add ${CYAN}apex${RESET} to your PATH\n"
        printf "  ${CYAN}─────────────────────────────────────────────────${RESET}\n"
        echo ""

        # Detect shell config file
        SHELL_NAME="$(basename "$SHELL" 2>/dev/null || echo "bash")"
        case "$SHELL_NAME" in
            zsh)  SHELL_RC="$HOME/.zshrc" ;;
            fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
            *)    SHELL_RC="$HOME/.bashrc" ;;
        esac

        PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\""
        if [ "$SHELL_NAME" = "fish" ]; then
            PATH_LINE="fish_add_path $BIN_DIR"
        fi

        printf "  Run this command (or add it to ${DIM}%s${RESET}):\n" "$SHELL_RC"
        echo ""
        printf "    ${GREEN}%s${RESET}\n" "$PATH_LINE"
        echo ""
        info "Then you can use:"
        info "  apex              Start the server"
        info "  apex --setup      Setup menu (keys, certs, knowledge)"
        info "  apex --uninstall  Remove Apex"
        echo ""
    fi
fi

exit $SETUP_EXIT
