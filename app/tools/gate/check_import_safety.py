#!/usr/bin/env python3
"""check_import_safety.py — importing a module under app/tools/ MUST NOT touch
the board. TASK-609 / M-HARNESS2 R48.

WHY THIS EXISTS. Six top-level DUT scripts ran their entire suite at module
level: `prloc_smoke.py`, `prloc_ve_smoke.py`, `prloc_manual_smoke.py`,
`prloc_editor_smoke.py`, `settings_kit_smoke.py`, `clock_tap_smoke.py`. Opening
the port asserts DTR, which RESETS the ESP32 — so `import prloc_smoke` was a
board reset plus an injected tap sequence. One such import reset the DUT during
the very review that found them (WP-A `A-12`) and destroyed a TASK-557
observation window. It also blocks every import-level lint over `app/tools/`,
including several gates the M-HARNESS2 programme needs.

WHAT IT ASSERTS. Every `*.py` under `app/tools/` imports cleanly WITHOUT:

  * constructing a `serial.Serial(...)`,
  * opening any `/dev/tty*` path through `open()` or `os.open()`,
  * hanging (an import that does not terminate is an import-time side effect
    too — it is how a poll loop at module level presents),
  * killing the interpreter (`os._exit`) — attributed via the progress log.

An import that fails for an unrelated reason (a missing third-party package, a
`SystemExit` from an arg parser) is NOT a failure. It is reported, because a
module that cannot be imported also cannot be proven safe, and the count is
printed so it cannot grow silently.

HOW THE GATE ITSELF IS PREVENTED FROM OPENING THE REAL PORT — this is the part
that matters, because a checker that opens the port to prove nothing opens the
port has reproduced the defect at a higher level. Four independent barriers, in
the child process, installed before a single project module is imported:

  1. A stub `serial` module is placed in `sys.modules` — the real pyserial is
     therefore unreachable by name for the rest of the child's life.
  2. A stub directory is placed FIRST on `sys.path`, so even a module that
     deletes the `sys.modules` entry and re-imports gets the stub.
  3. `builtins.open` and `os.open` are wrapped to REFUSE any `/dev/tty*` path.
  4. `$PORT` is set to a non-device sentinel, so `lib.dut.resolve_port()`
     returns it immediately and never shells out to `run/port`/udevadm.

Barriers 1-3 RECORD the attempt to a trip file and then RAISE. The trip file is
read by the parent regardless of the child's exit code, so a module that
swallows the exception is still caught — the recording, not the exception, is
the detector.

ONE CHILD, NOT ONE PER MODULE. 123 modules × a fresh interpreter would cost tens
of seconds against Phase 1's 90 s `run/check` budget. The child imports them in
a loop under a per-module SIGALRM and writes a progress line before each import,
so a hang or a hard exit is still attributed to a named module.

No DUT, no serial port, no network, no build.

    python3 app/tools/gate/check_import_safety.py [--verbose]
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

#: seconds a single module's import may take before it is called a hang.
PER_MODULE_TIMEOUT = 20

#: seconds the whole child may take.
BATCH_TIMEOUT = 240

#: A path that cannot be a serial device. `lib.dut.resolve_port()` returns
#: $PORT before it tries anything else, so this stops the udevadm shell-out.
SENTINEL_PORT = "/nonexistent/harness2-import-safety-stub"

EXCLUDE_DIRS = ("__pycache__",)


def module_files(root: str = TOOLS) -> list[str]:
    """Every importable `*.py` under app/tools/, as repo-relative paths."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), ROOT)
                           .replace(os.sep, "/"))
    return sorted(out)


# ── the child ────────────────────────────────────────────────────────────────
# Kept as a string rather than a file so the barriers are installed by the FIRST
# statements the interpreter runs; a separate module would have to be imported,
# and an import is the thing being made safe.

_CHILD = r'''
import builtins, importlib.util, os, signal, sys, types

TRIP = os.environ["H2_TRIP"]
PROGRESS = os.environ["H2_PROGRESS"]
STUBDIR = os.environ["H2_STUBDIR"]
TOOLS = os.environ["H2_TOOLS"]
ROOT = os.environ["H2_ROOT"]

def trip(kind, detail):
    with open(TRIP, "a", encoding="utf-8") as fh:
        fh.write("%s\t%s\t%s\n" % (CURRENT[0], kind, detail))

CURRENT = ["<preamble>"]

# ── barrier 1: a stub `serial`, in sys.modules before anything else ──────────
class _StubSerialException(Exception):
    pass

class _StubSerial:
    def __init__(self, *a, **kw):
        port = (a[0] if a else kw.get("port", "?"))
        trip("serial.Serial", "port=%r" % (port,))
        raise _StubSerialException(
            "check_import_safety: serial.Serial() at import time (stubbed; the "
            "real port was never opened)")

_serial = types.ModuleType("serial")
_serial.Serial = _StubSerial
_serial.SerialException = _StubSerialException
_serial.SerialTimeoutException = _StubSerialException
_serial.__path__ = [STUBDIR]
_tools = types.ModuleType("serial.tools")
_tools.__path__ = [STUBDIR]
_lp = types.ModuleType("serial.tools.list_ports")
_lp.comports = lambda *a, **kw: []
_tools.list_ports = _lp
_serial.tools = _tools
sys.modules["serial"] = _serial
sys.modules["serial.tools"] = _tools
sys.modules["serial.tools.list_ports"] = _lp

# ── barrier 3: refuse any /dev/tty* path ─────────────────────────────────────
def _is_tty(p):
    try:
        s = os.fsdecode(p)
    except Exception:
        return False
    return s.startswith("/dev/tty") or s.startswith("/dev/serial")

_real_open = builtins.open
def _guarded_open(file, *a, **kw):
    if _is_tty(file):
        trip("open", "path=%r" % (file,))
        raise PermissionError("check_import_safety: open(%r) at import time" % (file,))
    return _real_open(file, *a, **kw)
builtins.open = _guarded_open

_real_os_open = os.open
def _guarded_os_open(path, *a, **kw):
    if _is_tty(path):
        trip("os.open", "path=%r" % (path,))
        raise PermissionError("check_import_safety: os.open(%r) at import time" % (path,))
    return _real_os_open(path, *a, **kw)
os.open = _guarded_os_open

# ── the sweep ────────────────────────────────────────────────────────────────
sys.path.insert(0, STUBDIR)     # barrier 2
sys.path.insert(1, TOOLS)       # the import root every family module assumes

class _Timeout(Exception):
    pass

def _alarm(signum, frame):
    raise _Timeout()

signal.signal(signal.SIGALRM, _alarm)

rels = [ln for ln in sys.stdin.read().split("\n") if ln.strip()]
skipped = []
for rel in rels:
    CURRENT[0] = rel
    with _real_open(PROGRESS, "w", encoding="utf-8") as fh:
        fh.write(rel)
    path = os.path.join(ROOT, rel)
    name = "h2probe_" + rel.replace("/", "_")[:-3]
    signal.alarm(int(os.environ["H2_PER_TIMEOUT"]))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    except _Timeout:
        trip("hang", "did not finish importing within %ss" % os.environ["H2_PER_TIMEOUT"])
    except BaseException as exc:
        skipped.append("%s\t%s: %s" % (rel, type(exc).__name__, str(exc).split("\n")[0][:160]))
    finally:
        signal.alarm(0)
        sys.modules.pop(name, None)

CURRENT[0] = "<done>"
with _real_open(PROGRESS, "w", encoding="utf-8") as fh:
    fh.write("<done>")
with _real_open(os.environ["H2_SKIPPED"], "w", encoding="utf-8") as fh:
    fh.write("\n".join(skipped))
'''


def run(rels: list[str], per_timeout: int = PER_MODULE_TIMEOUT) -> dict:
    """Import every `rel` in one guarded child. Returns a findings dict."""
    tmp = tempfile.mkdtemp(prefix="h2-import-safety-")
    trip_path = os.path.join(tmp, "trips.tsv")
    prog_path = os.path.join(tmp, "progress")
    skip_path = os.path.join(tmp, "skipped.tsv")
    stub_dir = os.path.join(tmp, "stub")
    os.makedirs(stub_dir)
    # Barrier 2: a real `serial.py` on disk, first on the child's sys.path, so a
    # module that clears sys.modules and re-imports still cannot reach pyserial.
    with open(os.path.join(stub_dir, "serial.py"), "w", encoding="utf-8") as fh:
        fh.write("class SerialException(Exception):\n    pass\n"
                 "SerialTimeoutException = SerialException\n"
                 "class Serial:\n"
                 "    def __init__(self, *a, **kw):\n"
                 "        raise SerialException('import-safety stub')\n")
    for p in (trip_path, prog_path, skip_path):
        open(p, "w", encoding="utf-8").close()

    env = dict(os.environ)
    env.update({
        "H2_TRIP": trip_path, "H2_PROGRESS": prog_path, "H2_SKIPPED": skip_path,
        "H2_STUBDIR": stub_dir, "H2_TOOLS": TOOLS, "H2_ROOT": ROOT,
        "H2_PER_TIMEOUT": str(per_timeout),
        # Barrier 4: resolve_port() returns $PORT and never shells out.
        "PORT": SENTINEL_PORT,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    proc = subprocess.run([sys.executable, "-c", _CHILD], input="\n".join(rels),
                          text=True, capture_output=True, env=env,
                          timeout=BATCH_TIMEOUT)

    trips = []
    with open(trip_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                mod, kind, detail = (line.rstrip("\n").split("\t") + ["", ""])[:3]
                trips.append((mod, kind, detail))
    skipped = []
    with open(skip_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                mod, why = (line.rstrip("\n").split("\t") + [""])[:2]
                skipped.append((mod, why))
    progress = open(prog_path, encoding="utf-8").read().strip()
    died = None
    if progress != "<done>":
        died = progress or "<preamble>"
    return {"trips": trips, "skipped": skipped, "died": died,
            "rc": proc.returncode, "stderr": proc.stderr[-2000:]}


def evaluate(result: dict) -> list[str]:
    """Pure: a findings dict -> the list of blocking failure lines."""
    out = []
    for mod, kind, detail in result["trips"]:
        if kind == "hang":
            out.append(f"{mod}: import did not terminate ({detail}) — a module-level "
                       f"poll loop is an import-time side effect")
        else:
            out.append(f"{mod}: touched the board at import via {kind} ({detail}) — "
                       f"wrap the executable body in `if __name__ == \"__main__\":`")
    if result["died"]:
        out.append(f"{result['died']}: the import child died without finishing "
                   f"(os._exit at module level?) rc={result['rc']}")
    return out


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    rels = module_files()
    print(f"check_import_safety: importing {len(rels)} modules under app/tools/ "
          f"in one guarded child (stubbed transport, no port can be opened)")
    result = run(rels)
    failures = evaluate(result)

    if result["skipped"]:
        print(f"  {len(result['skipped'])} module(s) could not be imported for "
              f"unrelated reasons (reported, not failed):")
        for mod, why in result["skipped"] if verbose else result["skipped"][:8]:
            print(f"    {mod}: {why}")
        if not verbose and len(result["skipped"]) > 8:
            print(f"    ... {len(result['skipped']) - 8} more (--verbose)")

    if failures:
        print(f"\nFAIL: {len(failures)} module(s) touch the board at import time")
        for f in failures:
            print(f"  {f}")
        if result["stderr"] and verbose:
            print("  child stderr tail:\n" + result["stderr"])
        return 1
    print(f"  PASS  0 modules touch the board at import "
          f"({len(rels) - len(result['skipped'])} imported cleanly)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
