"""CLI UI helpers for the Apex onboarding wizard.

Interactive terminal helpers using ANSI escape codes.
Stdlib only — no external dependencies. Works on Mac and Linux.
"""

from __future__ import annotations

import getpass
import os
import sys

# ---------------------------------------------------------------------------
# ANSI escape sequences
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BOLD_GREEN = "\033[1;32m"
_BOLD_YELLOW = "\033[1;33m"
_BOLD_RED = "\033[1;31m"
_BOLD_CYAN = "\033[1;36m"
_ERASE_LINE = "\033[2K\r"

# Detect whether the terminal supports colors
def _detect_no_color() -> bool:
    """Detect whether to disable ANSI colors."""
    if os.environ.get("NO_COLOR") is not None:
        return True
    if not sys.stdout.isatty():
        return True
    if os.name == "nt":
        # Try to enable Windows VT100 processing (Windows 10 1511+)
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            if not (mode.value & 0x0004):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return False  # VT100 enabled successfully
        except Exception:
            return True  # Can't enable VT100, disable colors
    return False


_NO_COLOR = _detect_no_color()

# Non-interactive mode — all prompts return their defaults immediately.
# Set via set_non_interactive() when --fast or stdin is not a tty.
_NON_INTERACTIVE = False


def set_non_interactive(enabled: bool = True) -> None:
    """Enable non-interactive mode — all prompts return defaults."""
    global _NON_INTERACTIVE
    _NON_INTERACTIVE = enabled


def _c(code: str, text: str) -> str:
    """Wrap text in ANSI escape codes, respecting NO_COLOR."""
    if _NO_COLOR:
        return text
    return f"{code}{text}{_RESET}"


# ---------------------------------------------------------------------------
# Headers and step indicators
# ---------------------------------------------------------------------------


def print_header(text: str) -> None:
    """Print a bold section header with a divider line."""
    width = max(len(text) + 4, 50)
    print()
    print(_c(_BOLD_CYAN, "=" * width))
    print(_c(_BOLD, f"  {text}"))
    print(_c(_BOLD_CYAN, "=" * width))
    print()


def print_step(number: int, text: str) -> None:
    """Print a numbered step indicator."""
    label = _c(_BOLD_CYAN, f"[{number}]")
    print(f"{label} {_c(_BOLD, text)}")


# ---------------------------------------------------------------------------
# Colored output
# ---------------------------------------------------------------------------


def print_success(text: str) -> None:
    """Print green success message with checkmark."""
    print(f"  {_c(_BOLD_GREEN, 'OK')}  {text}")


def print_warning(text: str) -> None:
    """Print yellow warning message."""
    print(f"  {_c(_BOLD_YELLOW, '!!')}  {text}")


def print_error(text: str) -> None:
    """Print red error message."""
    print(f"  {_c(_BOLD_RED, 'ERR')} {text}")


def print_info(text: str) -> None:
    """Print dim informational text."""
    print(f"      {_c(_DIM, text)}")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def prompt_choice(question: str, options: list[str], default: int = 1) -> int:
    """Numbered choice selector. Returns 0-based index of selected option.

    Parameters
    ----------
    question : str
        The question to display.
    options : list[str]
        List of option labels.
    default : int
        1-based default selection (shown in brackets).

    Returns
    -------
    int
        0-based index of the selected option.
    """
    if _NON_INTERACTIVE:
        print_info(f"{question} -> [{default}] {options[default - 1]} (auto)")
        return default - 1

    print()
    print(_c(_BOLD, question))
    for i, opt in enumerate(options, 1):
        marker = _c(_BOLD_CYAN, "*") if i == default else " "
        print(f"  {marker} {_c(_BOLD, str(i))}. {opt}")

    prompt = f"  Choice [{default}]: "
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return default - 1
        try:
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice - 1
        except ValueError:
            pass
        print_error(f"Enter a number between 1 and {len(options)}")


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Y/n prompt. Returns bool."""
    if _NON_INTERACTIVE:
        answer = "yes" if default else "no"
        print_info(f"{question} -> {answer} (auto)")
        return default

    hint = "Y/n" if default else "y/N"
    prompt = f"  {_c(_BOLD, question)} [{hint}]: "
    while True:
        raw = input(prompt).strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print_error("Please enter y or n")


def prompt_text(question: str, default: str = "", required: bool = False) -> str:
    """Text input with optional default.

    Parameters
    ----------
    question : str
        The question to display.
    default : str
        Default value shown in brackets. Empty string means no default.
    required : bool
        If True, empty input is rejected (unless a non-empty default exists).

    Returns
    -------
    str
        The user's input, or the default.
    """
    if _NON_INTERACTIVE:
        if default:
            print_info(f"{question} -> {default} (auto)")
        return default

    if default:
        prompt = f"  {_c(_BOLD, question)} [{default}]: "
    else:
        prompt = f"  {_c(_BOLD, question)}: "

    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        if default:
            return default
        if required:
            print_error("This field is required")
            continue
        return ""


def prompt_secret(question: str) -> str:
    """Masked input via getpass. Returns the entered string."""
    prompt = f"  {_c(_BOLD, question)}: "
    # getpass prints to stderr by default for security; we use our prompt
    return getpass.getpass(prompt=prompt)


def prompt_confirm(text: str) -> None:
    """User must type the exact text to proceed.

    Used for security acknowledgments like 'I understand'.
    Loops until the user types the exact text or Ctrl-C.
    In non-interactive mode, auto-acknowledges.
    """
    if _NON_INTERACTIVE:
        print_info(f'"{text}" (auto-acknowledged)')
        return

    print()
    print(_c(_DIM, f'  Type "{text}" to continue:'))
    while True:
        raw = input("  > ").strip()
        if raw == text:
            return
        print_error(f'Please type exactly: {text}')


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a simple aligned table.

    All values are converted to strings. Column widths auto-fit.
    """
    if not headers:
        return

    str_rows = [[str(cell) for cell in row] for row in rows]

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    # Header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print()
    print(f"  {_c(_BOLD, header_line)}")
    sep = "  ".join("-" * w for w in widths)
    print(f"  {sep}")

    # Rows
    for row in str_rows:
        cells = []
        for i, cell in enumerate(row):
            w = widths[i] if i < len(widths) else len(cell)
            cells.append(cell.ljust(w))
        print(f"  {'  '.join(cells)}")
    print()


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

_BAR_FILL = "\u2588"  # Full block
_BAR_EMPTY = "\u2591"  # Light shade


def print_progress(current: int, total: int, label: str = "") -> None:
    """Print a progress bar: [XXXX....] 4/10 label

    Overwrites the current line so it can be called repeatedly.
    """
    if total <= 0:
        return

    bar_width = 20
    filled = int(bar_width * current / total)
    bar = _BAR_FILL * filled + _BAR_EMPTY * (bar_width - filled)
    counter = f"{current}/{total}"

    line = f"  [{_c(_GREEN, bar)}] {counter}"
    if label:
        line += f" {label}"

    sys.stdout.write(f"{_ERASE_LINE}{line}")
    sys.stdout.flush()

    # Print newline when complete
    if current >= total:
        print()


def clear_line() -> None:
    """Erase the current terminal line and return cursor to start."""
    sys.stdout.write(_ERASE_LINE)
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Short aliases (used by setup/models.py)
# ---------------------------------------------------------------------------

header = print_header
info = print_info
success = print_success
warn = print_warning
ask_yes_no = prompt_yes_no


def ask_input(question: str, secret: bool = False) -> str:
    """Prompt for text or masked secret input."""
    if secret:
        return prompt_secret(question)
    return prompt_text(question)
