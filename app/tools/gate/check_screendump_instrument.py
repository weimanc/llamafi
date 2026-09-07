#!/usr/bin/env python3
"""check_screendump_instrument.py — the `run/screendump` instrument is not
merely importable, it still DECODES. TASK-589 / WP-A `A-1`.

WHY THIS EXISTS. `screendump.py` imported `_PORTAL_INDICATORS` from
`lib/dut.py`. TASK-555 deleted that constant (the WiFiManager firmware it
watched for left in `ddf6433`, 2026-06-11), so from 2026-09-01 the instrument
raised `ImportError` BEFORE opening the port, and so did its three dependants —
`clock_delta_smoke.py`, `pr_delta_smoke.py`, `slider_delta_smoke.py`. Nothing
noticed. `CLAUDE.md` went on documenting `run/screendump` as a working tool, and
ADR-064 sanctioned GRAM readback as the project's render-verification mechanism
on the strength of this path working.

`check_import_safety.py` ran over the file every time and reported it under
"could not be imported for unrelated reasons (reported, not failed)" — which is
correct for ITS subject (nothing that fails to import can touch the board) and
useless for this one. That asymmetry is the whole defect class: a tool nobody
runs between uses rots, and a check that only greps for the import line rots
with it, because the next break will be in the decode, not the import.

So every arm here EXECUTES real instrument code (the C5/C6 shape from
`check_entrypoint_lifecycle.py`), against a fabricated serial transcript rather
than a board. No DUT, no port, no network, ~1 s.

  A  The four modules import. BLOCKING, unlike `check_import_safety`'s report.
     This is the arm that would have caught `A-1` the day TASK-555 landed.

  B  The band protocol really round-trips. A firmware-accurate transcript for a
     known image is fed to the real `dump_with_retry` through a fake serial, and
     the reassembled canvas must equal the source EXACTLY. Two arms that
     reproduce live conditions: an interleaved `[hb]` heartbeat between bands
     (the firmware has no cross-task Serial-write lock), and a band whose base64
     is corrupted on first read, which the retry path must heal. A capture that
     silently zero-fills a dropped band is the failure ADR-064 cannot tolerate —
     it reads as a black rectangle, i.e. as CONTENT.

  C  `rgb565_to_rgb888` against ground truth. A channel swap here is invisible
     on a screenshot of a mostly-grey UI and fatal to a render signature.

  D  The TASK-340 transform, pinned. `colorprobe`'s adjudicator must require a
     byte swap on a `fill` probe and identity on a `push` probe; both inverted
     forms must be REPORTED, or `./run/screendump --colorprobe` would pass on a
     board whose readback had degraded the way TASK-340's did at 20 MHz.

  E  The wrapper still reaches the module and still forwards its arguments.
     Text-only, and labelled as such: executing `run/screendump` would kill and
     restart the live tmux monitor, which is a side effect on the rig.

Exit 0 clean, 1 with findings. Negative suite:
``gate/test_check_screendump_instrument.py``.

    python3 app/tools/gate/check_screendump_instrument.py [--verbose]
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent.parent

#: The instrument and everything that imports it. A closed set: a new importer
#: of `screendump` is expected to be added here in the same commit.
MODULES = ("screendump", "clock_delta_smoke", "pr_delta_smoke",
           "slider_delta_smoke")

#: A path that cannot be a serial device, so `resolve_port()` returns it
#: instead of shelling out to `run/port`/udevadm. Same barrier as
#: check_import_safety.py's fourth.
SENTINEL_PORT = "/nonexistent/task589-screendump-gate"


# ── the child: everything below runs in a subprocess with the real modules ────
# Kept as a string for the same reason check_import_safety.py keeps its child
# as one — the point is what happens when the real files are loaded, and a
# helper module would have to be imported first.

_CHILD = r'''
import base64, json, os, sys

# `python -c` puts the CWD first on sys.path. Drop it: `run/check` invokes this
# from app/tools, so without this the child would import the LIVE instrument
# while claiming to import the tree it was pointed at — and the negative
# suite's mutations would silently have no effect (caught by N11).
_cwd = os.getcwd()
sys.path[:] = [p for p in sys.path if p not in ("", ".", _cwd)]
sys.path.insert(0, TOOLS)

findings = []


def A_imports():
    """A — the modules import at all. The `A-1` arm."""
    for name in MODULES:
        try:
            __import__(name)
        except BaseException as exc:
            findings.append(
                "A %s does not import: %s: %s -- run/screendump and everything "
                "built on it are dead, and ADR-064's render verification with "
                "them" % (name, type(exc).__name__, str(exc).split(chr(10))[0][:200]))


class _FakeSerial:
    """Serves a firmware-accurate `screendump` transcript for `src`.

    Mirrors app/src/debug/serialConsole/cmdMisc.cpp cmdScreenDump(): one JSON
    header, then `SCREENDUMP:BAND <ry> <rows> <base64 little-endian RGB565>`
    in kBandRows=8 row bands, then SCREENDUMP:END. The firmware has already
    undone readRect()'s byte swap (TASK-340), so the wire is true RGB565.
    """

    BAND_ROWS = 8

    def __init__(self, src, corrupt_rows=(), noise_after=()):
        self.src = src
        self.corrupt_rows = set(corrupt_rows)   # ABSOLUTE y of a band to break
        self.noise_after = set(noise_after)     # ABSOLUTE y to follow with chatter
        self.corrupted = []                     # what we actually broke
        self.queue = []
        self.timeout = 1.0
        self.requests = []

    def serve(self, x, y, w, h):
        self.requests.append((x, y, w, h))
        out = [json.dumps({"ok": True, "cmd": "screendump", "x": x, "y": y,
                           "w": w, "h": h, "bpp": 16})]
        for ry in range(0, h, self.BAND_ROWS):
            rows = min(self.BAND_ROWS, h - ry)
            band = self.src[y + ry:y + ry + rows, x:x + w]
            raw = band.astype("<u2").tobytes()
            b64 = base64.b64encode(raw).decode()
            ay = y + ry
            if ay in self.corrupt_rows:
                # A base64 body mangled the way an interleaved log line mangles
                # it. Break it ONCE: the retry must then succeed, which is what
                # separates "the retry path runs" from "the retry path works".
                self.corrupt_rows.discard(ay)
                self.corrupted.append(ay)
                b64 = b64[:-6] + "!!!!"
            out.append("SCREENDUMP:BAND %d %d %s" % (ry, rows, b64))
            if ay in self.noise_after:
                out.append("[I][hb] display=winamp wifi=rssi(-61) heap=105k")
        out.append("SCREENDUMP:END")
        self.queue.extend(out)

    def readline(self):
        if not self.queue:
            return b""
        return (self.queue.pop(0) + "\n").encode()


class _FakeDut:
    def __init__(self, ser):
        self.ser = ser

    def send(self, cmd):
        parts = cmd.split()
        assert parts[0] == "screendump", parts
        self.ser.serve(*[int(v) for v in parts[1:5]])


def B_decode(sd, np):
    """B — the real band parser reassembles a known image, exactly."""
    rng = np.random.default_rng(589)
    src = rng.integers(0, 0x10000, size=(24, 17), dtype=np.uint16)

    # B1 clean.
    ser = _FakeSerial(src)
    got = sd.dump_with_retry(_FakeDut(ser), 0, 0, 17, 24)
    if not np.array_equal(got, src):
        findings.append("B1 a clean transcript did not round-trip: %d of %d "
                        "pixels differ" % (int((got != src).sum()), src.size))

    # B2 background chatter between bands. The firmware has no cross-task
    # Serial-write lock, so this is the normal case, not the exotic one.
    ser = _FakeSerial(src, noise_after=(0, 8, 16))
    got = sd.dump_with_retry(_FakeDut(ser), 0, 0, 17, 24)
    if not np.array_equal(got, src):
        findings.append("B2 an interleaved log line broke the capture: %d of %d "
                        "pixels differ" % (int((got != src).sum()), src.size))

    # B3 a corrupted band, healed by the retry. The arm that matters: a band
    # that never decodes is left as ZEROS, which reads as a black rectangle --
    # as content -- and a render signature over it is a confident lie.
    ser = _FakeSerial(src, corrupt_rows=(8,))
    got = sd.dump_with_retry(_FakeDut(ser), 0, 0, 17, 24)
    if not ser.corrupted:
        findings.append("B3 the fixture never corrupted a band, so the retry "
                        "path was not exercised -- this arm proves nothing")
    elif not np.array_equal(got, src):
        n = int((got[8:16] != src[8:16]).sum())
        findings.append("B3 a corrupted band was NOT healed by the retry: %d px "
                        "wrong in the affected band. An unhealed band stays "
                        "ZERO and reads as black CONTENT, not as a gap" % n)
    elif len(ser.requests) < 2:
        findings.append("B3 the canvas matched but no re-request was made -- "
                        "the corrupted band was accepted, not retried")

    # B4 a header that never arrives must RAISE, not return a blank canvas.
    class _Silent(_FakeSerial):
        def serve(self, *a):
            self.queue.append("[I][hb] nothing to see here")
    try:
        sd._dump_region(_FakeDut(_Silent(src)), 0, 0, 17, 24, timeout=0.2)
    except RuntimeError:
        pass
    else:
        findings.append("B4 a missing header returned a canvas instead of "
                        "raising -- a blank frame would be reported as a capture")


def C_colour(sd, np):
    """C — RGB565 -> RGB888 against ground truth."""
    cases = {0xF800: (255, 0, 0), 0x07E0: (0, 255, 0), 0x001F: (0, 0, 255),
             0xFFFF: (255, 255, 255), 0x0000: (0, 0, 0),
             0xFFE0: (255, 255, 0), 0x07FF: (0, 255, 255)}
    for v, want in cases.items():
        got = tuple(int(c) for c in
                    sd.rgb565_to_rgb888(np.array([[v]], dtype=np.uint16))[0][0])
        if got != want:
            findings.append("C rgb565_to_rgb888(%#06x) = %s, want %s -- a "
                            "channel error here is invisible on a grey UI and "
                            "fatal to a render signature" % (v, got, want))


def D_colorprobe(sd):
    """D — TASK-340's transform, pinned in both directions."""
    swap = lambda v: ((v << 8) | (v >> 8)) & 0xFFFF
    fills = [0xF800, 0x07E0, 0x001F, 0xFFFF, 0x4208]
    pushes = [0xAAAA, 0x5555, 0xDEAD, 0xF0F0]

    ok, total, fails = sd.colorprobe_verdict(
        [("fill", v, swap(v)) for v in fills] +
        [("push", v, v) for v in pushes])
    if fails or ok != total or total != len(fills) + len(pushes):
        findings.append("D a correct TASK-340 sweep was adjudicated %d/%d with "
                        "%r -- ./run/screendump --colorprobe would report a "
                        "healthy readback path as broken" % (ok, total, fails))

    # The inversions. Both are what a DEGRADED read looks like (TASK-340 at
    # 20 MHz found no clean transform at all); an oracle that accepts them
    # cannot detect the fault it exists for.
    _, _, f_unswapped = sd.colorprobe_verdict([("fill", v, v) for v in fills
                                               if swap(v) != v])
    if len(f_unswapped) != len([v for v in fills if swap(v) != v]):
        findings.append("D an UNSWAPPED fill probe was accepted -- readRect's "
                        "byte swap (TASK-340) is no longer being asserted")
    _, _, f_swapped = sd.colorprobe_verdict([("push", v, swap(v)) for v in pushes
                                             if swap(v) != v])
    if len(f_swapped) != len([v for v in pushes if swap(v) != v]):
        findings.append("D a BYTE-SWAPPED push probe was accepted -- pushRect's "
                        "raw round trip (TASK-340) is no longer being asserted")

    if getattr(sd, "COLORPROBE_SWATCH_VALUE", None) != 0xF0F0:
        findings.append("D COLORPROBE_SWATCH_VALUE is %r, but cmdColorProbe's "
                        "kPushSweep ends 0xF0F0 -- the end-to-end swatch check "
                        "would compare against the wrong ground truth"
                        % (getattr(sd, "COLORPROBE_SWATCH_VALUE", None),))


A_imports()
if not findings:
    import numpy as np
    import screendump as sd
    B_decode(sd, np)
    C_colour(sd, np)
    D_colorprobe(sd)

print(json.dumps(findings))
'''


def _run_child(tools: pathlib.Path, modules=MODULES) -> list[str]:
    """Execute the arms against `tools`, in a child that cannot open a port."""
    env = dict(os.environ)
    env.update({"PORT": SENTINEL_PORT, "PYTHONDONTWRITEBYTECODE": "1"})
    preamble = (f"TOOLS = {str(tools)!r}\nMODULES = {tuple(modules)!r}\n")
    proc = subprocess.run([sys.executable, "-c", preamble + _CHILD],
                          capture_output=True, text=True, env=env, timeout=120)
    tail = (proc.stdout.strip().split("\n") or [""])[-1]
    try:
        return json.loads(tail)
    except json.JSONDecodeError:
        return [f"the gate's own child died (rc={proc.returncode}) before "
                f"reporting: {(proc.stderr or proc.stdout).strip()[-400:]!r}"]


def check_wrapper(root: pathlib.Path) -> list[str]:
    """E — the shell wrapper still reaches the module and forwards its args.

    TEXT, not execution, and deliberately so: running `run/screendump` kills and
    restarts the live tmux monitor. Naming that here rather than leaving a
    reader to wonder which arms are real.
    """
    out: list[str] = []
    wrapper = root / "run" / "screendump"
    if not wrapper.is_file():
        return ["E run/screendump is missing"]
    text = wrapper.read_text()
    if "tools/screendump.py" not in text:
        out.append("E run/screendump no longer invokes app/tools/screendump.py")
    if '"$@"' not in text:
        out.append('E run/screendump does not forward "$@" — -x/-y/-w/-H/-o and '
                   "--colorprobe would be silently dropped")
    r = subprocess.run(["bash", "-n", str(wrapper)], capture_output=True, text=True)
    if r.returncode != 0:
        out.append(f"E run/screendump is not valid bash: {r.stderr.strip()[:200]}")
    return out


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    print("check_screendump_instrument: executing the readback instrument "
          f"({len(MODULES)} modules, band decode, colour, TASK-340 transform) "
          "against a fabricated transcript — no DUT")
    findings = _run_child(TOOLS) + check_wrapper(ROOT)
    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    print("  PASS  screendump imports, decodes exactly, heals a corrupt band, "
          "and still asserts TASK-340's transform")
    if verbose:
        print(f"  modules: {', '.join(MODULES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
