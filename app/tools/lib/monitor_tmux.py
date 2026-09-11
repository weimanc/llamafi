#!/usr/bin/env python3
"""lib/monitor_tmux.py — H-1 (TASK-677/678, PROP-011-runbook.md §0.1 rule 1):
the ONLY way any H-1 driver talks to the board. Sends console commands
through the existing tmux monitor session and reads its replies back from
the plain-text log the monitor already writes — it never opens the serial
port itself (a port open asserts DTR, which resets the ESP32 and ends a
TASK-557 observation window).

IMPORT SAFETY (gate/check_import_safety.py, PROP-011-runbook.md §0.1 rule 5).
Importing this module does nothing: no subprocess, no file I/O. Every
side-effecting function (`send`) is only ever called from a driver's `main()`
after an explicit, non-dry-run invocation — same convention as
lib/rigwatch.py's daemon/stamp functions.

`send()` runs `tmux send-keys`, which itself never opens /dev/tty* — it talks
to the tmux server, which already owns the pane holding the real serial
connection (`run/monitor-start`). A driver that never calls `send()` (a
--dry-run, or a fixture-only test) touches nothing.
"""

from __future__ import annotations

import os
import subprocess

DEFAULT_SESSION = "spotify-mon"
DEFAULT_LOG = "/tmp/spotify-mon-serial.log"


def session_name() -> str:
    return os.environ.get("MONITOR_TMUX_SESSION", DEFAULT_SESSION)


def log_path() -> str:
    return os.environ.get("MONITOR_LOG", DEFAULT_LOG)


def send(cmd: str, session: str | None = None, timeout: float = 10.0) -> None:
    """`tmux send-keys -t <session> '<cmd>' Enter`. The one function in this
    module that touches anything outside the interpreter — callers gate it
    behind --dry-run."""
    subprocess.run(
        ["tmux", "send-keys", "-t", session or session_name(), cmd, "Enter"],
        check=True, timeout=timeout)


def send_literal(text: str, session: str | None = None, timeout: float = 10.0) -> None:
    """`tmux send-keys -l -t <session> -- <text>` — literal bytes, no key-name
    translation and NO appended Enter (a caller that wants a newline puts it
    in `text` itself). Used for feeding a raw payload — serialsink/serialecho
    — where an unwanted extra Enter would corrupt the byte count or line
    boundary being measured."""
    subprocess.run(
        ["tmux", "send-keys", "-l", "-t", session or session_name(), "--", text],
        check=True, timeout=timeout)


def size(path: str | None = None) -> int:
    """Current byte size of the monitor log, for "slice from here" reads —
    the same offset-then-slice idiom EXP-026 §1.5 used by hand."""
    p = path or log_path()
    return os.path.getsize(p) if os.path.exists(p) else 0


def read_from(offset: int, path: str | None = None) -> str:
    """Log bytes from `offset` to EOF, decoded leniently (a serial log can
    carry a torn multi-byte sequence at a chunk boundary)."""
    p = path or log_path()
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        return fh.read()


def tail(n: int = 200, path: str | None = None) -> list[str]:
    p = path or log_path()
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return lines[-n:] if n else lines
