#!/usr/bin/env python3
"""probe/rig_resetgap.py — PROP-011 X-P6: does a short gap between two hardware
resets leave this CYD stuck in the ROM bootloader? Decides BP-018's 12 s rule.

Method (TASK-555's, scaled to n per gap): reset 1 (`--before default_reset
--after hard_reset chip_id`, app boots) → sleep GAP → reset 2 (same) → settle →
probe with `--before no_reset --after no_reset --connect-attempts 1 chip_id`.
A probe that SYNCS means the chip is sitting in the ROM bootloader = WEDGED;
a probe that cannot sync means the application is running = OK. A wedged trial
is recorded, then recovered with one hard reset.

THIS DRIVER RESETS THE BOARD and opens the port with esptool. It refuses to run
without --i-know-this-resets-the-board. Every reset is stamped `reset
who=xp6` in rigwatch first, so the boots it causes never read as unexplained.
Nothing happens at import (gate/check_import_safety.py).

    python3 probe/rig_resetgap.py --i-know-this-resets-the-board \\
        --gaps 1,2,4,8,12 --trials 30 --out /tmp/claude-1000/xp6/trials.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

PORT_DEFAULT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
ESPTOOL = [os.path.expanduser("~/.platformio/penv/bin/python"),
           os.path.expanduser("~/.platformio/packages/tool-esptoolpy/esptool.py")]
SETTLE_S = 3.0


def esptool_argv(port: str, probe: bool) -> list:
    mode = (["--before", "no_reset", "--after", "no_reset", "--connect-attempts", "1"]
            if probe else ["--before", "default_reset", "--after", "hard_reset"])
    return ESPTOOL + ["--chip", "esp32", "--port", port, "--baud", "115200"] + mode + ["chip_id"]


def classify_probe(rc: int, out: str) -> bool:
    """True = WEDGED (the no-reset probe synced with the ROM bootloader)."""
    return rc == 0 and "Chip is ESP32" in out


def summarize(rows: list) -> dict:
    per = {}
    for r in rows:
        g = per.setdefault(str(r["gap"]), {"trials": 0, "wedged": 0, "reset_fail": 0, "reenum": 0})
        g["trials"] += 1
        g["wedged"] += int(r["wedged"])
        g["reset_fail"] += int(r["rc1"] != 0 or r["rc2"] != 0)
        g["reenum"] += r.get("reenum", 0)
    return per


def _run(argv: list, timeout: float):
    import subprocess
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, str(e)


def _reenum_since(t0: float, sysport: str | None) -> int:
    from lib import rigwatch as rw
    if not sysport:
        return -1
    return sum(1 for raw in rw._journal_lines_since(t0)
               if (ev := rw.parse_kernel_line(raw, sysport)) and ev["kind"] == "attach")


def trial(port: str, gap: float, n: int, sysport: str | None) -> dict:
    from lib import rigwatch as rw
    t0 = time.time()
    rw.stamp("reset", who="xp6", gap=str(gap), trial=str(n), leg="1")
    rc1, _ = _run(esptool_argv(port, False), 45)
    time.sleep(gap)
    rw.stamp("reset", who="xp6", gap=str(gap), trial=str(n), leg="2")
    rc2, _ = _run(esptool_argv(port, False), 45)
    time.sleep(SETTLE_S)
    rcp, outp = _run(esptool_argv(port, True), 20)
    wedged = classify_probe(rcp, outp)
    row = {"gap": gap, "trial": n, "rc1": rc1, "rc2": rc2, "rc_probe": rcp,
           "wedged": wedged, "t0": round(t0, 3)}
    if wedged:
        rw.stamp("reset", who="xp6", gap=str(gap), trial=str(n), leg="recover")
        row["rc_recover"], _ = _run(esptool_argv(port, False), 45)
    time.sleep(1.0)
    row["reenum"] = _reenum_since(t0, sysport)
    return row


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="rig_resetgap", description=__doc__.splitlines()[0])
    ap.add_argument("--gaps", default="1,2,4,8,12")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--port", default=PORT_DEFAULT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--i-know-this-resets-the-board", action="store_true")
    a = ap.parse_args(argv)
    gaps = [float(g) for g in a.gaps.split(",") if g]
    if a.dry_run:
        for g in gaps:
            print(f"[dry-run] gap={g}s x{a.trials}: {' '.join(esptool_argv(a.port, False))}"
                  f" ; sleep {g} ; again ; sleep {SETTLE_S} ; probe {' '.join(esptool_argv(a.port, True)[-7:])}")
        return 0
    if not a.i_know_this_resets_the_board:
        print("rig_resetgap: REFUSING — every trial hard-resets the board twice and ends any "
              "observation window. Re-run with --i-know-this-resets-the-board.", file=sys.stderr)
        return 3
    from lib import rigwatch as rw
    sysport = rw.dut_sysfs_port(a.port)
    rows = []
    for g in gaps:
        for n in range(1, a.trials + 1):
            row = trial(a.port, g, n, sysport)
            rows.append(row)
            print(json.dumps(row), flush=True)
            if a.out:
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(row) + "\n")
        print(json.dumps({"gap": g, **summarize([r for r in rows if r["gap"] == g])[str(g)]}), flush=True)
    print(json.dumps({"summary": summarize(rows)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main(sys.argv[1:]))
