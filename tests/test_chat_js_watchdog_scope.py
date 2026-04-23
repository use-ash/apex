from pathlib import Path


def _function_block(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    next_start = source.find("\nfunction ", start + len(marker))
    if next_start == -1:
        return source[start:]
    return source[start:next_start]


def test_watchdog_ui_filters_stream_ctx_to_current_chat() -> None:
    source = Path("/Users/dana/.openclaw/apex/server/chat_js.py").read_text(encoding="utf-8")

    pick_block = _function_block(source, "_pickWatchdogTarget")
    pills_block = _function_block(source, "_renderWatchdogPills")
    guard = "if (ctx.chatId && ctx.chatId !== currentChat) return;"

    assert guard in pick_block
    assert guard in pills_block
