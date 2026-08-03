#!/usr/bin/env python3
"""EXP-012 measurement pass — input-ring 8K vs 16K (docs/rnd/reports/EXP-012-input-ring-16k.md).

Runs the SAME procedure against either build (baseline cyd2usb_webradio = 8K ring,
trial cyd2usb_webradio_16k = 16K ring) so the two columns of the EXP-012 results
table are directly comparable:

  1. SURVEY (H1, Phase 2.1): play every station once, auto-skip OFF, hold ~18s.
     Per station: decoder-init CP2 lfbInt/lfbDma, arena acquire OK/FAIL, decoder
     OOM ("not enough memory to allocate mp3decoder buffers"), end buf%, underruns,
     sustained playMs. H1 requires 0 decoder OOM + 0 arena FAIL across 10+ stations.
  2. SLOW-STATION SOAK (H2, Phase 2.2): long hold (default 120s) on the Phase 0
     shortlist (st5, st7, st10), sampling wrUnderruns every 10s → underruns/min,
     buf% trace, sustained playMs.

Instrumentation parsed (SERIAL_DEBUG build):
    [membudget] CP1-pre-connect ... / CP2-decoder-init freeInt=.. lfbInt=.. freeDma=.. lfbDma=..
    [membudget] TASK-267 arena acquire=..B lfbBefore=.. OK|FAIL
    "not enough memory to allocate mp3decoder buffers"  (log_e, CORE_DEBUG_LEVEL>=1)
plus: get wrCount / wrPlaying / wrUnderruns, set wrPlay/wrStop/wrAutoSkip.

Usage:
    python3 exp012_measure.py --port /dev/ttyUSB0 [--hold 18] [--slow 5,7,10] [--slow-hold 120]
    python3 exp012_measure.py --survey-only        # H1 pass only
Exit 0 = H1 held (0 decoder OOM, 0 arena FAIL); 1 otherwise. H2 numbers are reported
for the experiment table, not gated.
"""
import re
import sys
import json
import time
import argparse
import serial

from app_ids_gen import APP_SLOT

RE_CP2     = re.compile(r"CP2-decoder-init freeInt=(\d+) lfbInt=(\d+) freeDma=(\d+) lfbDma=(\d+)")
RE_ACQUIRE = re.compile(r"arena acquire=(\d+)B lfbBefore=(\d+)\s+(\S+)")
RE_INBUF   = re.compile(r"inputBufferSize: (\d+) bytes")   # ground truth for the ring size
DECODER_OOM = "not enough memory to allocate mp3decoder buffers"


class SerialDut:
    """Same self-contained wrapper as test_webradio_soak.py (no ELF gate — this
    runs on cyd2usb_webradio / _16k builds, not the canonical debug ELF)."""
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False

    def boot_wait(self, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in l or "spotify=off" in l:
                break
        for _ in range(40):
            if self.cmd("get appId", 2.0).get("name"):
                return True
            time.sleep(1.0)
        return False

    def cmd(self, s, timeout=3.0):
        self.ser.reset_input_buffer()
        self.ser.write((s + "\n").encode())
        self.ser.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if not l:
                continue
            try:
                r = json.loads(l)
                if not isinstance(r, dict):
                    continue          # bare JSON scalars (stray numbers) on serial
                if r.get("last", True):
                    return r
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def raw(self, s):
        self.ser.reset_input_buffer()
        self.ser.write((s + "\n").encode())
        self.ser.flush()

    def read_for(self, secs, early=None):
        lines, end = [], time.monotonic() + secs
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if not l:
                continue
            lines.append(l)
            if early and early in l:
                break
        return lines


def scan(lines, st):
    """Fold [membudget]/decoder log lines into a station record."""
    for l in lines:
        m = RE_CP2.search(l)
        if m:
            st["freeInt"], st["lfbInt"], st["lfbDma"] = \
                int(m.group(1)), int(m.group(2)), int(m.group(4))
        m = RE_ACQUIRE.search(l)
        if m and "OK" not in m.group(3):
            st["arenaFail"] = True
        m = RE_INBUF.search(l)
        if m:
            st["inBufSize"] = int(m.group(1))
        m = re.search(r'Connect to new host: "([^"]+)"', l)
        if m:
            st["url"] = m.group(1)   # station identity — indices shift across refetches
        if DECODER_OOM in l:
            st["decoderOOM"] = True
        # raw evidence trail — membudget probes + audio lib info lines
        if "[membudget]" in l or "audio_info" in l:
            print(f"    | {l}", flush=True)


def play_and_hold(d, idx, hold, sample_every=None):
    """set wrPlay idx, hold `hold` seconds, return station record.
    sample_every: also poll wrUnderruns periodically (slow-station trace)."""
    st = {"idx": idx, "url": None, "freeInt": None, "lfbInt": None, "lfbDma": None,
          "inBufSize": None, "arenaFail": False, "decoderOOM": False,
          "endBufPct": None, "underruns": None, "playMs": 0, "trace": []}
    d.raw(f"set wrPlay {idx}")
    # capture the connect window (CP1/CP2/arena/decoder lines stream here)
    scan(d.read_for(8.0, early="CP2-decoder-init"), st)
    t0 = time.monotonic()
    next_sample = t0 + (sample_every or hold + 1)
    while time.monotonic() - t0 < hold:
        # keep draining the log so OOM/arena lines during playback are seen
        scan(d.read_for(min(2.0, hold - (time.monotonic() - t0))), st)
        if sample_every and time.monotonic() >= next_sample:
            u = d.cmd("get wrUnderruns")
            if u:
                st["trace"].append((round(time.monotonic() - t0),
                                    u.get("underruns"), u.get("bufPct"), u.get("playMs")))
            next_sample += sample_every
    u = d.cmd("get wrUnderruns")
    st["endBufPct"] = u.get("bufPct")
    st["underruns"] = u.get("underruns")
    st["playMs"]    = u.get("playMs") or 0
    d.raw("set wrStop")
    scan(d.read_for(2.0, early="arena released"), st)
    time.sleep(1.0)
    return st


def main():
    ap = argparse.ArgumentParser(description="EXP-012 8K-vs-16K measurement pass")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--hold", type=int, default=18, help="survey hold secs/station (Phase 0 used 18)")
    ap.add_argument("--slow", default="auto",
                    help="slow-station indices for the long soak, or 'auto' = pick the "
                         "3 lowest-end-buf%% PLAYING stations from this run's survey "
                         "(indices are not stable across refetches — auto is safer)")
    ap.add_argument("--slow-hold", type=int, default=120, help="slow-station hold secs")
    ap.add_argument("--survey-only", action="store_true")
    ap.add_argument("--min-playing", type=int, default=10,
                    help="H1 sample-size floor (stations that must reach playback)")
    args = ap.parse_args()

    d = SerialDut(args.port)
    print(f"[exp012] connecting {args.port} …", flush=True)
    if not d.boot_wait():
        print("[exp012] FAIL: shell not ready", flush=True); sys.exit(1)
    d.cmd(f"switchApp {APP_SLOT['WebRadio']}", 3.0)
    time.sleep(1.0)
    # The station list arrives over a multi-page fetch — wait until the count
    # STABILIZES (unchanged for 3 polls), not merely >0. Polling early sees a
    # partial page (a 4-of-16 run burned a full pass before this guard existed).
    cnt, stable = 0, 0
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and stable < 3:
        c = d.cmd("get wrCount").get("count", 0) or 0
        stable = stable + 1 if (c == cnt and c > 0) else 0
        cnt = c
        time.sleep(4.0)
    if cnt <= 0:
        print("[exp012] FAIL: no stations", flush=True); sys.exit(1)
    d.cmd("set wrAutoSkip 0")
    print(f"[exp012] {cnt} stations, auto-skip OFF — survey {args.hold}s/station", flush=True)

    # ── Phase 2.1 survey (H1) ────────────────────────────────────────────────
    survey = []
    for i in range(cnt):
        st = play_and_hold(d, i, args.hold)
        survey.append(st)
        print(f"  st{i}: inBuf={st['inBufSize']} freeInt={st['freeInt']} lfbInt={st['lfbInt']} "
              f"lfbDma={st['lfbDma']} end_buf%={st['endBufPct']} ur={st['underruns']} "
              f"playMs={st['playMs']} "
              f"{'DECODER-OOM! ' if st['decoderOOM'] else ''}{'ARENA-FAIL! ' if st['arenaFail'] else ''}",
              flush=True)

    ooms   = sum(1 for s in survey if s["decoderOOM"])
    afails = sum(1 for s in survey if s["arenaFail"])
    lfbs   = [s["lfbInt"] for s in survey if s["lfbInt"]]
    dmas   = [s["lfbDma"] for s in survey if s["lfbDma"]]
    reached = sum(1 for s in survey if (s["playMs"] or 0) > 0)

    slow_out = []
    if not args.survey_only:
        # ── Phase 2.2 slow-station soak (H2) ────────────────────────────────
        if args.slow == "auto":
            playing = sorted((s for s in survey if (s["playMs"] or 0) > 0),
                             key=lambda s: s["endBufPct"] if s["endBufPct"] is not None else 100)
            targets = [s["idx"] for s in playing[:3]]
            print(f"[exp012] auto slow targets: {targets}", flush=True)
        else:
            targets = [int(x) for x in args.slow.split(",") if x.strip()]
        for i in targets:
            if i >= cnt:
                print(f"  st{i}: SKIP (only {cnt} stations)", flush=True); continue
            print(f"[exp012] slow soak st{i} — {args.slow_hold}s hold", flush=True)
            st = play_and_hold(d, i, args.slow_hold, sample_every=10)
            slow_out.append(st)
            mins = max(st["playMs"] / 60000.0, 1e-9)
            urpm = (st["underruns"] or 0) / mins if st["playMs"] else 0
            print(f"  st{i}: sustained={st['playMs']}ms ur={st['underruns']} "
                  f"({urpm:.1f}/min) end_buf%={st['endBufPct']}", flush=True)
            for t, ur, bp, pm in st["trace"]:
                print(f"      t+{t:>3}s ur={ur} buf%={bp} playMs={pm}", flush=True)

    print("\n================ EXP-012 measurement report ================", flush=True)
    rings = sorted({s["inBufSize"] for s in survey if s["inBufSize"]})
    print(f"input ring size(s)    : {rings or 'NOT OBSERVED'}  (8K build ≈ 7999, 16K trial ≈ 16383)", flush=True)
    print(f"stations surveyed     : {cnt} (reached playback: {reached})", flush=True)
    print(f"decoder OOM           : {ooms}   (H1 gate: must be 0)", flush=True)
    print(f"arena acquire FAIL    : {afails}   (H1 gate: must be 0)", flush=True)
    if lfbs:
        print(f"CP2 lfbInt            : min={min(lfbs)} max={max(lfbs)}", flush=True)
    if dmas:
        print(f"CP2 lfbDma            : min={min(dmas)} max={max(dmas)}", flush=True)
    for st in slow_out:
        mins = max(st["playMs"] / 60000.0, 1e-9)
        urpm = (st["underruns"] or 0) / mins if st["playMs"] else 0
        print(f"slow st{st['idx']:<2}            : sustained={st['playMs']}ms "
              f"ur={st['underruns']} ({urpm:.1f}/min) end_buf%={st['endBufPct']}", flush=True)
    h1 = (reached >= args.min_playing and ooms == 0 and afails == 0)
    print(f"H1 (decoder allocs at this ring size): {'PASS' if h1 else 'FAIL'}", flush=True)
    print("=============================================================", flush=True)
    sys.exit(0 if h1 else 1)


if __name__ == "__main__":
    main()
