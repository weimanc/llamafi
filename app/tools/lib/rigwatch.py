#!/usr/bin/env python3
"""lib/rigwatch.py — TASK-677 / PROP-011 §5 P0: host+DUT fault correlation.

WHAT THIS IS. Every prior TASK-557 investigation reasoned from one record at a
time (the kernel log, OR the board's serial log, OR a memory of "I flashed
around then") and every asserted-then-retracted causal claim on that task's
record ("it's the cable", "the port-open causes it") came from never cross-
reading them. This module is the cross-read: a kernel-event tail, a harness
event stamper, a DUT-line timestamper, and a merger that turns all three into
one ordered timeline with relative offsets.

WHAT THIS IS NOT, AND MUST NEVER BECOME. It never opens the DUT's serial port.
Every harness port-open asserts DTR and resets the ESP32 (measured, TASK-557) —
so an instrument built to explain resets must not itself be a source of them.
Every fact this module knows about the DUT comes from files: the kernel's own
udev log (`journalctl -k`, unprivileged on this host — verified 2026-09-10) and
the plain-text serial logs OTHER processes already write
(`/tmp/spotify-mon-serial.log` from the tmux `pio device monitor` session; a
harness `--log-file` from `Dut`/`_TeeSerial`). Reading a file is not opening a
port.

IMPORT SAFETY (gate/check_import_safety.py). Importing this module does
nothing: no subprocess, no file I/O, no thread start. Every side-effecting
function is called from `main()`, guarded by `if __name__ == "__main__":`.

── THE FOUR METRICS THIS MODULE COMPUTES (PROP-011 §4) ───────────────────────

  R  reenum            — count of kernel "attach" events in the window.
  U  unexplained_boots  — a DUT `[bootphase] 0` with no harness-stamped
                          flash-end / port-open / reset within +/-3s.
  bod_trips             — count of DUT `[bod] TRIP` lines in the window.
  wifi_disc              — delta of the heartbeat's own `disc=N` counter
                          (NEVER counted from `[wifi-ev]` lines, which are
                          rate-limited server-side — see boot log note below).

── FILES ───────────────────────────────────────────────────────────────────

  RIG_EVENTS   JSONL, append-only. Kernel events (`src":"kernel"`) written by
               the daemon; harness events (`"src":"harness"`) written by
               `stamp`. Default alongside MONITOR_LOG:
               /tmp/spotify-mon-rig-events.jsonl (override: $RIG_EVENTS).

  <MONITOR_LOG>.ts   JSONL sidecar the daemon writes as it tails the plain-text
               monitor log: `{"host_ts": ..., "line": "..."}`, one entry per
               DUT line matching a marker this module cares about
               ([bootreason]/[bootphase]/[bod]/[wifi-ev]/[hb]). Written
               file-to-file — `tail -F`-style polling — never a serial open.

  <dut-log>.ts   The same sidecar shape, written by `lib.dut._TeeSerial` for a
               harness session's own `--log-file` (TASK-677 deliverable B).

RIGWATCH_PIDFILE (default /tmp/spotify-rigwatch.pid) makes `daemon` idempotent:
a second `rigwatch daemon` on a host where one is already running is a no-op,
not a second tailer duplicating every event.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from typing import Optional

# ── paths ───────────────────────────────────────────────────────────────────

DEFAULT_MONITOR_LOG = "/tmp/spotify-mon-serial.log"
DEFAULT_RIG_EVENTS = "/tmp/spotify-mon-rig-events.jsonl"
DEFAULT_PIDFILE = "/tmp/spotify-rigwatch.pid"


def monitor_log_path() -> str:
    return os.environ.get("MONITOR_LOG", DEFAULT_MONITOR_LOG)


def rig_events_path() -> str:
    return os.environ.get("RIG_EVENTS", DEFAULT_RIG_EVENTS)


def pidfile_path() -> str:
    return os.environ.get("RIGWATCH_PIDFILE", DEFAULT_PIDFILE)


def ts_sidecar_path(log_path: str) -> str:
    return log_path + ".ts"


DEFAULT_DUT_LINES = "/tmp/spotify-mon-dut-lines.jsonl"


def dut_lines_path() -> str:
    """The ONE shared DUT-line JSONL. Two writers, never live at the same time
    (the monitor is killed for every harness run): the daemon's MONITOR_LOG tail
    and `lib/dut.py`'s `_TeeSerial`. A run with no `LOG_FILE` used to leave no
    timestamped DUT lines at all, which made U/bod/W in its artifact zero by
    construction — the false-clean reading PROP-011 §1 exists to prevent."""
    return os.environ.get("RIG_DUT_LINES", DEFAULT_DUT_LINES)


# ── DUT line markers — the lines worth timestamping and reasoning about ──────

_DUT_MARKER_RE = re.compile(
    r"\[bootreason\]|\[bootphase\]|\[bod\]|\[wifi-ev\]|\[I\]\[hb\]")
_BOOTPHASE0_RE = re.compile(r"\[bootphase\]\s+0\b")
_BOD_TRIP_RE = re.compile(r"\[bod\]\s+TRIP")
_HB_DISC_RE = re.compile(r"\bdisc=(\d+)\b")

#: Harness event kinds that EXPLAIN a boot (a reset the harness itself caused).
_EXPLAINS_BOOT = {"flash-begin", "flash-end", "port-open", "reset",
                  "monitor-start"}

#: How close a harness stamp must be to a DUT boot to explain it (PROP-011 §4).
UNEXPLAINED_WINDOW_S = 3.0


def is_dut_marker_line(line: str) -> bool:
    return bool(_DUT_MARKER_RE.search(line))


# ── kernel event parsing (journalctl -k -o json, one JSON object per line) ──

_ATTACH_RE = re.compile(r"new (?:full|high|low)-speed USB device number (\d+)")
_DETACH_RE = re.compile(r"USB disconnect, device number (\d+)")
_ERROR_RE = re.compile(r"device not accepting address|error -\d+|"
                       r"descriptor read error")
_TTY_ATTACH_RE = re.compile(r"ch341-uart converter now attached to (tty\w+)")
_TTY_DETACH_RE = re.compile(
    r"ch341-uart (tty\w+): ch341-uart converter now disconnected")
_RESET_RE = re.compile(r"\breset\b", re.I)


def classify_kernel_message(msg: str) -> Optional[str]:
    """-> one of attach|detach|error|enum|reset, or None (not a USB line we
    care about — e.g. an unrelated 'link up' or vendor-specific chatter)."""
    if _ATTACH_RE.search(msg):
        return "attach"
    if _DETACH_RE.search(msg):
        return "detach"
    if _TTY_ATTACH_RE.search(msg) or _TTY_DETACH_RE.search(msg):
        return "enum"
    if _ERROR_RE.search(msg):
        return "error"
    if _RESET_RE.search(msg):
        return "reset"
    return None


def parse_kernel_line(raw_json_line: str, port_filter: Optional[str]) -> Optional[dict]:
    """One `journalctl -k -o json` line -> a rig event dict, or None.

    `port_filter` is the DUT's sysfs USB port (e.g. "1-1"), NOT `ttyUSBn` — the
    whole point (see module docstring / CLAUDE.md's rigwatch note) is that
    ttyUSBn renames on every re-enumeration and the sysfs port does not. A line
    is kept only if it names that port (`usb 1-1: ...`) or, for the ch341-uart
    lines (which do not repeat the usb port number), if no port_filter was
    given at all — those callers are expected to have already narrowed by tty.
    Returns None for anything unrelated (e.g. the fingerprint reader on a
    different port), which is the filter this whole function exists for.
    """
    try:
        obj = json.loads(raw_json_line)
    except (ValueError, TypeError):
        return None
    msg = obj.get("MESSAGE")
    if not isinstance(msg, str):
        return None
    if port_filter:
        # kernel USB lines are "usb <port>: ..." or "<driver> <port>:<iface>: ...";
        # match the port token as a whole segment so "1-1" does not also match
        # "1-14" or "1-1.2" — a real hazard on a hub, though this rig has none.
        if not re.search(rf"\busb {re.escape(port_filter)}\b[:\s]", msg) and \
           not re.search(rf"\b{re.escape(port_filter)}\b:\d", msg):
            return None
    kind = classify_kernel_message(msg)
    if kind is None:
        return None
    devnum = None
    m = _ATTACH_RE.search(msg) or _DETACH_RE.search(msg)
    if m:
        devnum = int(m.group(1))
    tty = None
    m = _TTY_ATTACH_RE.search(msg)
    if m:
        tty = m.group(1)
    else:
        m = _TTY_DETACH_RE.search(msg)
        if m:
            tty = m.group(1)
    host_ts = None
    rt = obj.get("__REALTIME_TIMESTAMP")
    if rt is not None:
        try:
            host_ts = int(rt) / 1_000_000.0
        except (ValueError, TypeError):
            host_ts = None
    return {
        "host_ts": host_ts if host_ts is not None else time.time(),
        "src": "kernel",
        "kind": kind,
        "devnum": devnum,
        "tty": tty,
        "raw": msg,
    }


# ── sysfs port resolution (subprocess only when actually called) ────────────

def dut_sysfs_port(node: Optional[str] = None) -> Optional[str]:
    """The USB topology port ('1-1') a DUT device node sits on, via udevadm.

    `node` defaults to $DUT_BY_PATH, then a live scan of
    /dev/serial/by-id/usb-1a86_* (the CH340 VID). Returns None rather than
    guessing — a wrong port_filter would silently show the wrong device's
    events, which is worse than showing none.
    """
    import glob
    import subprocess

    if node is None:
        node = os.environ.get("DUT_BY_PATH")
    if node is None:
        cands = sorted(glob.glob("/dev/serial/by-id/usb-1a86_*"))
        node = cands[0] if cands else None
    if node is None or not os.path.exists(node):
        return None
    try:
        out = subprocess.run(
            ["udevadm", "info", "-q", "path", "-n", node],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    # .../devices/pci.../usb1/1-1/1-1:1.0/ttyUSB0/tty/ttyUSB0
    # The port segment is the shortest path component matching N-N(.N)* with
    # no ':' (a ':' segment is the interface, one level further down).
    parts = out.stdout.strip().split("/")
    port_re = re.compile(r"^\d+-\d+(\.\d+)*$")
    for p in parts:
        if port_re.match(p):
            return p
    return None


# ── JSONL helpers ─────────────────────────────────────────────────────────

def append_jsonl(path: str, obj: dict) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True) + "\n")


def read_jsonl(path: str):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


# ── stamp (deliverable A "stamp") ────────────────────────────────────────────

#: The vocabulary this module accepts. Not enforced strictly (a caller may add
#: a `note` with any label) but every scripted call site should use one of
#: these so `summary`/`timeline` can reason about them by name.
STAMP_KINDS = {
    "flash-begin", "flash-end", "port-open", "port-close",
    "monitor-start", "monitor-stop", "run-begin", "run-end", "note",
}


def stamp(kind: str, **fields) -> dict:
    """Append one harness event. Never raises — a stamp failing must not fail
    the run/flash/test it is describing."""
    ev = {"host_ts": time.time(), "src": "harness", "kind": kind}
    ev.update(fields)
    try:
        append_jsonl(rig_events_path(), ev)
    except OSError as e:
        print(f"  [rigwatch] WARN: could not stamp {kind!r}: {e}", file=sys.stderr)
    return ev


# ── daemon (deliverable A "daemon") ──────────────────────────────────────────

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def daemon_already_running() -> Optional[int]:
    pf = pidfile_path()
    if not os.path.exists(pf):
        return None
    try:
        with open(pf, encoding="utf-8") as fh:
            pid = int(fh.read().strip())
    except (ValueError, OSError):
        return None
    return pid if _pid_alive(pid) else None


def stop_daemon() -> bool:
    """-> True if a daemon was running and was signalled."""
    pf = pidfile_path()
    pid = daemon_already_running()
    try:
        os.remove(pf)
    except OSError:
        pass
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    return True


def _tail_monitor_log(state: dict) -> None:
    """Poll MONITOR_LOG for new lines, write matched ones to its .ts sidecar.

    File-to-file only — never a serial open. `state['pos']` persists the byte
    offset across calls so re-invocation does not re-timestamp old lines.
    """
    path = monitor_log_path()
    if not os.path.exists(path):
        return
    sidecar = ts_sidecar_path(path)
    size = os.path.getsize(path)
    pos = state.get("pos", 0)
    if size < pos:
        pos = 0  # log was truncated/rotated underneath us
    if size == pos:
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        fh.seek(pos)
        chunk = fh.read()
        state["pos"] = fh.tell()
    now = time.time()
    for line in chunk.splitlines():
        if is_dut_marker_line(line):
            append_jsonl(sidecar, {"host_ts": now, "line": line})
            append_jsonl(dut_lines_path(), {"host_ts": now, "line": line, "via": "monitor"})


def run_daemon(port_filter: Optional[str], poll_s: float = 1.0) -> int:
    """Foreground daemon body: tails `journalctl -k -f -o json` (filtered) and
    polls MONITOR_LOG for new DUT lines. Blocks until SIGTERM/SIGINT.

    Returns an exit code; callers that want backgrounding do it at the shell
    level (nohup ... & — see run/lib.sh), same pattern as run/monitor-start's
    tmux session. This function itself never forks."""
    import subprocess

    already = daemon_already_running()
    if already is not None:
        print(f"[rigwatch] daemon already running (pid {already}) — not starting "
              f"a second one", flush=True)
        return 0

    pf = pidfile_path()
    try:
        d = os.path.dirname(pf)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(pf, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError as e:
        print(f"[rigwatch] WARN: could not write pidfile {pf}: {e}", file=sys.stderr)

    stop = {"flag": False}

    def _on_term(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    proc = None
    try:
        proc = subprocess.Popen(
            ["journalctl", "-k", "-f", "-o", "json", "--no-pager"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            bufsize=1)
    except (OSError, FileNotFoundError) as e:
        print(f"[rigwatch] WARN: journalctl unavailable ({e}) — kernel events "
              f"will not be recorded; MONITOR_LOG tail still runs", file=sys.stderr)

    if proc is not None:
        import fcntl
        fl = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    mon_state: dict = {}
    print(f"[rigwatch] daemon started (pid {os.getpid()}), port_filter="
          f"{port_filter!r}, events -> {rig_events_path()}, monitor tail -> "
          f"{ts_sidecar_path(monitor_log_path())}", flush=True)
    try:
        while not stop["flag"]:
            if proc is not None:
                try:
                    for _ in range(200):
                        line = proc.stdout.readline()
                        if not line:
                            break
                        ev = parse_kernel_line(line, port_filter)
                        if ev is not None:
                            append_jsonl(rig_events_path(), ev)
                except (OSError, ValueError):
                    pass
            _tail_monitor_log(mon_state)
            time.sleep(poll_s)
    finally:
        if proc is not None:
            proc.terminate()
        try:
            os.remove(pf)
        except OSError:
            pass
    return 0


# ── summary / timeline (deliverables A "summary"/"timeline") ────────────────

def parse_since(s: str) -> float:
    """A float epoch, or a duration like '2h'/'30m'/'1d' meaning "now - that"."""
    s = s.strip()
    m = re.match(r"^(\d+(?:\.\d+)?)([smhd])$", s)
    if m:
        n = float(m.group(1))
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
        return time.time() - n * mult
    return float(s)


def _dut_lines_since(since: float):
    """Merge the shared DUT-lines file, MONITOR_LOG's legacy sidecar and any
    RIGWATCH_EXTRA_TS file, host_ts >= since, de-duplicated, sorted."""
    paths = {dut_lines_path(), ts_sidecar_path(monitor_log_path())}
    extra = os.environ.get("RIGWATCH_EXTRA_TS")
    if extra:
        paths.add(extra)
    out, seen = [], set()
    for p in paths:
        for obj in read_jsonl(p):
            ts = obj.get("host_ts")
            if ts is None or ts < since:
                continue
            key = (round(ts, 3), obj.get("line"))
            if key in seen:
                continue
            seen.add(key)
            obj.setdefault("src", "dut")
            out.append(obj)
    out.sort(key=lambda o: o.get("host_ts") or 0)
    return out


_PORT_CACHE: dict = {}


def _cached_dut_port() -> Optional[str]:
    if "port" not in _PORT_CACHE:
        _PORT_CACHE["port"] = dut_sysfs_port(os.environ.get("DUT_BY_PATH") or None)
    return _PORT_CACHE["port"]


def _journal_lines_since(since: float):
    """Raw `journalctl -k -o json` lines from `since` onward. The daemon only
    records events while it runs; a `summary`/`timeline` over a window the
    daemon did not cover (the 1 800 events of 2026-09-01/02, every window
    before TASK-677 landed) must still see the kernel's own record, or the
    tool reports a clean rig for a period that was anything but.
    RIGWATCH_NO_JOURNAL=1 disables it (tests; hosts without systemd)."""
    if os.environ.get("RIGWATCH_NO_JOURNAL") == "1":
        return []
    import subprocess
    try:
        out = subprocess.run(
            ["journalctl", "-k", "-o", "json", "--no-pager", "--since", f"@{int(since)}"],
            capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    return out.stdout.splitlines()


def _harness_events_since(since: float):
    out = [ev for ev in read_jsonl(rig_events_path())
          if ev.get("src") == "harness" and (ev.get("host_ts") or 0) >= since]
    out.sort(key=lambda o: o.get("host_ts") or 0)
    return out


def _kernel_events_since(since: float):
    """Daemon-recorded kernel events merged with a live journal query for the
    same window, de-duplicated on (timestamp, message). The journal half is
    skipped when the DUT's sysfs port cannot be resolved — an unfiltered
    kernel log would count every USB device on the host as the DUT."""
    out = [ev for ev in read_jsonl(rig_events_path())
          if ev.get("src") == "kernel" and (ev.get("host_ts") or 0) >= since]
    seen = {(round(ev.get("host_ts") or 0, 3), ev.get("raw")) for ev in out}
    port = _cached_dut_port() if os.environ.get("RIGWATCH_NO_JOURNAL") != "1" else None
    if port:
        for raw in _journal_lines_since(since):
            ev = parse_kernel_line(raw, port)
            if ev is None or ev["host_ts"] < since:
                continue
            key = (round(ev["host_ts"], 3), ev.get("raw"))
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    out.sort(key=lambda o: o.get("host_ts") or 0)
    return out


def summarize(since: float) -> dict:
    kernel = _kernel_events_since(since)
    harness = _harness_events_since(since)
    dut = _dut_lines_since(since)

    reenum = sum(1 for ev in kernel if ev.get("kind") == "attach")
    bod_trips = sum(1 for o in dut if _BOD_TRIP_RE.search(o.get("line", "")))

    # wifi_disc: max - min of the heartbeat's own disc=N counter in-window.
    disc_vals = []
    for o in dut:
        m = _HB_DISC_RE.search(o.get("line", ""))
        if m and "[I][hb]" in o.get("line", ""):
            disc_vals.append(int(m.group(1)))
    wifi_disc = (max(disc_vals) - min(disc_vals)) if len(disc_vals) >= 2 else \
        (disc_vals[0] if disc_vals else 0)

    explain_ts = [ev["host_ts"] for ev in harness
                 if ev.get("kind") in _EXPLAINS_BOOT]
    unexplained = []
    for o in dut:
        if not _BOOTPHASE0_RE.search(o.get("line", "")):
            continue
        ts = o.get("host_ts") or 0
        explained = any(abs(ts - e) <= UNEXPLAINED_WINDOW_S for e in explain_ts)
        if not explained:
            unexplained.append(o)

    events = sorted(kernel + harness + dut, key=lambda o: o.get("host_ts") or 0)
    return {
        "since": since,
        "reenum": reenum,
        "unexplained_boots": len(unexplained),
        "bod_trips": bod_trips,
        "wifi_disc": wifi_disc,
        "events": events,
    }


def annotate_run_rig(summ: dict) -> Optional[str]:
    """One line in the [triage] convention (lib/results.py TRIAGE_MARKER),
    or None if nothing in this window earns a RIG annotation. Deliberately
    reuses the project's existing triage-context vocabulary rather than
    inventing a second annotation channel — see lib/results.py's
    TRIAGE_MARKER / suite/serialdbg/_triage.py."""
    r, u = summ.get("reenum", 0), summ.get("unexplained_boots", 0)
    if r <= 0 and u <= 0:
        return None
    return (f"[triage] rig: R={r} reenum U={u} unexplained-boot(s) in this run's "
           f"window — PROP-011 §4's RIG threshold (R=0 and U=0) was not met")


def _fmt_ts(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts)) + f".{int((ts % 1) * 1000):03d}"


def render_timeline(summ: dict) -> str:
    events = summ["events"]
    if not events:
        return "(no events in window)"
    lines = []
    t0 = events[0].get("host_ts") or 0
    explain_ts = [e["host_ts"] for e in events
                 if e.get("src") == "harness" and e.get("kind") in _EXPLAINS_BOOT]
    for i, ev in enumerate(events):
        ts = ev.get("host_ts") or 0
        when = _fmt_ts(ts) if i == 0 else f"+{ts - t0:6.2f}s"
        src = ev.get("src", "?")
        if src == "kernel":
            detail = f"{ev.get('kind')} devnum={ev.get('devnum')} tty={ev.get('tty')}"
        elif src == "harness":
            extra = " ".join(f"{k}={v}" for k, v in ev.items()
                             if k not in ("host_ts", "src", "kind"))
            detail = f"{ev.get('kind')} {extra}".rstrip()
        else:  # dut
            line = ev.get("line", "")
            detail = line
            if _BOOTPHASE0_RE.search(line):
                explained = any(abs(ts - e) <= UNEXPLAINED_WINDOW_S for e in explain_ts)
                detail += "" if explained else "   << UNEXPLAINED boot"
        lines.append(f"{when:>12}  {src:<7} {detail}")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────

def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="rigwatch", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    sd = sub.add_parser("daemon", help="tail kernel USB events + MONITOR_LOG "
                        "(foreground; background it with nohup/&)")
    sd.add_argument("--port", default=None,
                    help="DUT device node (default: $DUT_BY_PATH or a live "
                         "by-id scan)")
    sd.add_argument("--stop", action="store_true")

    ss = sub.add_parser("stamp", help="append one harness event")
    ss.add_argument("kind")
    ss.add_argument("kv", nargs="*", help="key=value pairs")

    su = sub.add_parser("summary")
    su.add_argument("--since", default="24h")
    su.add_argument("--json", action="store_true")

    st = sub.add_parser("timeline")
    st.add_argument("--since", default="24h")

    a = ap.parse_args(argv)

    if a.mode == "daemon":
        if a.stop:
            stopped = stop_daemon()
            print("[rigwatch] daemon stopped" if stopped
                 else "[rigwatch] no daemon was running")
            return 0
        port = dut_sysfs_port(a.port)
        if port is None:
            print("[rigwatch] WARN: could not resolve the DUT's sysfs USB port — "
                 "kernel events will not be filtered by port (every USB device's "
                 "events would be recorded, which is worse than none — refusing "
                 "the kernel half; MONITOR_LOG tail still runs)", file=sys.stderr)
            return run_daemon(port_filter="__no_such_port__")
        return run_daemon(port_filter=port)

    if a.mode == "stamp":
        fields = {}
        for kv in a.kv:
            if "=" in kv:
                k, v = kv.split("=", 1)
                fields[k] = v
        stamp(a.kind, **fields)
        return 0

    if a.mode == "summary":
        since = parse_since(a.since)
        summ = summarize(since)
        if a.json:
            print(json.dumps(summ, indent=2, sort_keys=True))
        else:
            print(f"since {time.strftime('%Y-%m-%d', time.localtime(since))} "
                 f"{_fmt_ts(since)}  reenum(R)={summ['reenum']} "
                 f"unexplained_boots(U)={summ['unexplained_boots']} "
                 f"bod_trips={summ['bod_trips']} wifi_disc(W)={summ['wifi_disc']} "
                 f"events={len(summ['events'])}")
            note = annotate_run_rig(summ)
            if note:
                print(note)
        return 0

    if a.mode == "timeline":
        since = parse_since(a.since)
        summ = summarize(since)
        print(render_timeline(summ))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
