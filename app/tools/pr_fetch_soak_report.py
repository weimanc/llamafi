#!/usr/bin/env python3
"""PlaneRadar fetch-failure-rate soak — TASK-361 quantification step.

TASK-313 measured adsb.fi (Cloudflare-fronted) parse-truncation at ~9% first-
attempt / 0.47% after-one-retry. TASK-361 is a human-reported regression:
~36% total failure (both attempts) observed live over busy London daytime
traffic (60-70 aircraft). Working hypothesis, NOT YET CONFIRMED: truncation
probability scales with response size, so a fixed one-retry mitigation stops
being enough once both attempts are drawn from a high-truncation-probability
regime.

This tool does NOT assume the hypothesis — it switches to PlaneRadar, watches
the existing `[dataTask.planeradar]` log lines (TASK-361 added `size=`/
`scanned=` fields — see dataTaskStorage.cpp prFetchOnce/prParseStream/
fetchPlaneRadar) over a soak, and buckets first-attempt/final failure rate by
two independent variables:

  - declared response `size` (HTTP Content-Length, read via http.getSize()
    right after the GET headers land — present and TRUTHFUL even when the
    body then gets truncated, since it's set by the origin before Cloudflare's
    edge decides to cut the connection). This is the PRIMARY bucket for
    testing the size-scaling hypothesis — it is NOT biased by truncation.
  - GET `elapsed` time — TASK-313's archive found E-92 lands ~70-90% through
    the body with a prompt clean EOF (not a stall). That is consistent with
    EITHER a body-fraction-based edge cutoff OR a time-based one (a bigger
    body simply takes longer to transfer, so a fixed-time cutoff would
    naturally correlate with size too). Bucketing elapsed separately from
    size lets the two be told apart.

Deliberately NOT bucketed by `scanned` for the hypothesis test: on a FAILED
cycle, `scanned` is how far the parse got before truncation — a lower bound
on the true aircraft count, not the true count. Bucketing failures by their
own truncation point would be circular (a cutoff that always fires ~70-90%
through would put itself in the "small" bucket regardless of true size).
`scanned` is still logged per-cycle (for object-index diagnostics) but is not
used for the size-scaling verdict.

Usage:
    python3 pr_fetch_soak_report.py --port /dev/ttyUSB0 --minutes 30
Requires: DUT flashed with cyd2usb_winamp_debug, WiFi up. Best run during
real busy-traffic hours (daytime) — a quiet-traffic run will just show a low
overall failure rate and thin/empty high-size buckets, which is a valid
(if unexciting) data point, not a tool malfunction.

Exit 0 always (this is a measurement tool, not a pass/fail gate) unless the
DUT wedges (no PlaneRadar switch, or zero cycles observed in the whole run).
"""
import re
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run_serialdbg_tests import Dut, _switch_to, _restore_spotify   # noqa: E402
from ve_suite_base import make_arg_parser                            # noqa: E402

GET_RE    = re.compile(r"\[dataTask\.planeradar\].*GET (-?\d+) elapsed=(\d+)ms size=(-?\d+)")
FINAL_RE  = re.compile(r"\[dataTask\.planeradar\].*ok=(\d) errorCode=(-?\d+) count=(\d+) scanned=(\d+) epoch=(\d+)")
RETRY_HIT = re.compile(r"\[dataTask\.planeradar\].*parse rc=(-?\d+) scanned=(\d+) -> retry")
RETRY_RES = re.compile(r"\[dataTask\.planeradar\].*retry ok=(\d) rc=(-?\d+) scanned=(\d+)")
CRASH_RE  = re.compile(r"\[boot\]|ets Jul|panic|abort|stack overflow|Guru Meditation|"
                       r"LoadProhibited|StoreProhibited", re.I)

# Declared Content-Length buckets (bytes) — TASK-313's host probe measured
# 12.6 KB for 28 aircraft; busy-traffic 60-70 aircraft implies materially
# larger bodies. This is the PRIMARY bucket for the size-scaling verdict.
SIZE_BUCKETS = [(0, 2999), (3000, 5999), (6000, 8999), (9000, 11999),
                (12000, 15999), (16000, 999999)]

# GET elapsed-ms buckets — secondary axis, see module docstring.
ELAPSED_BUCKETS = [(0, 999), (1000, 1999), (2000, 3999), (4000, 7999), (8000, 999999)]


def _fmt_bucket(lo, hi, cap, unit=""):
    return f"{lo}-{hi if hi < cap else '+'}{unit}"


def _size_bucket(n):
    for lo, hi in SIZE_BUCKETS:
        if lo <= n <= hi:
            return _fmt_bucket(lo, hi, 999999, "B")
    return "?"


def _elapsed_bucket(ms):
    for lo, hi in ELAPSED_BUCKETS:
        if lo <= ms <= hi:
            return _fmt_bucket(lo, hi, 999999, "ms")
    return "?"


def _get_prloc(dut):
    return dut.cmd("get prloc", timeout=5.0)


def _set_prloc_slot(dut, slot, label, lat, lon):
    r = dut.cmd(f"set prloc {slot} {label} {lat} {lon}", timeout=5.0)
    if not r.get("ok"):
        raise RuntimeError(f"set prloc {slot} failed: {r}")


def _set_prloc_active(dut, slot):
    r = dut.cmd(f"set prloc active {slot}", timeout=5.0)
    if not r.get("ok"):
        raise RuntimeError(f"set prloc active {slot} failed: {r}")


def main():
    ap = make_arg_parser([], "PlaneRadar fetch-failure-rate soak (TASK-361 quantification)")
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--loc-slot", type=int, default=None,
                    help="prloc slot index (1..6 — never 0, that's home/weather) to "
                         "temporarily repoint at --lat/--lon for this soak, e.g. a busy "
                         "airport in a different timezone's daytime. Restores the "
                         "slot's prior contents + original active index afterward — "
                         "EXCEPT if the slot was empty before, which can't be restored "
                         "to empty via the serial command surface (no 'clear slot' "
                         "verb exists); it will be left holding --label/--lat/--lon.")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--label", default="TEST", help="max 5 chars, uppercased by firmware")
    ap.add_argument("--active-slot", type=int, default=None,
                    help="switch to an EXISTING, already-saved prloc slot for this soak — "
                         "no content overwrite, just the active index, restored afterward. "
                         "Safer than --loc-slot when the location you want is already saved "
                         "(e.g. an LHR/airport slot). Mutually exclusive with --loc-slot.")
    args = ap.parse_args()
    if args.loc_slot == 0 or args.active_slot == 0:
        print("[pr-fetch-soak] refusing slot 0 — that's home, also drives weather")
        sys.exit(1)
    if args.loc_slot is not None and (args.lat is None or args.lon is None):
        print("[pr-fetch-soak] --loc-slot requires --lat and --lon")
        sys.exit(1)
    if args.loc_slot is not None and args.active_slot is not None:
        print("[pr-fetch-soak] --loc-slot and --active-slot are mutually exclusive")
        sys.exit(1)

    dut = Dut(args.port, args.baud)
    cycles = []          # one dict per fetch cycle (first attempt + retry if any)
    crashed = False
    pending_get_size = None      # size= from the most recent GET line (paired to the next outcome line)
    pending_get_elapsed = None   # elapsed=...ms from the same GET line
    orig_active = None
    orig_slot = None   # (label, lat, lon) of args.loc_slot before we overwrote it

    try:
        if args.loc_slot is not None:
            before = _get_prloc(dut)
            orig_active = before.get("active")
            slot_before = next((l for l in before.get("locs", []) if l["i"] == args.loc_slot), None)
            orig_slot = (slot_before["label"], slot_before["lat"], slot_before["lon"]) \
                if slot_before else ("", 0.0, 0.0)
            was_empty = not orig_slot[0]
            print(f"[pr-fetch-soak] slot {args.loc_slot} before: "
                  f"{'EMPTY' if was_empty else orig_slot} — repointing to "
                  f"{args.label} {args.lat},{args.lon}"
                  + ("" if not was_empty else
                     " (was empty — will NOT be restorable to empty, see --help)"))
            _set_prloc_slot(dut, args.loc_slot, args.label, args.lat, args.lon)
            _set_prloc_active(dut, args.loc_slot)

        if args.active_slot is not None:
            before = _get_prloc(dut)
            orig_active = before.get("active")
            print(f"[pr-fetch-soak] switching active slot {orig_active} -> {args.active_slot} "
                  f"(no content changed, just the active index)")
            _set_prloc_active(dut, args.active_slot)

        if not _switch_to(dut, "PlaneRadar", timeout=15.0):
            print("[pr-fetch-soak] FAIL: could not switch to PlaneRadar")
            sys.exit(1)

        t_start = time.monotonic()
        t_end = t_start + args.minutes * 60
        cur = None
        while time.monotonic() < t_end:
            line = dut.ser.readline().decode(errors="replace").strip()
            if not line:
                continue
            if CRASH_RE.search(line):
                print(f"[pr-fetch-soak] CRASH/REBOOT signature: {line!r} — aborting soak")
                crashed = True
                break

            m = GET_RE.search(line)
            if m:
                pending_get_elapsed = int(m.group(2))
                pending_get_size = int(m.group(3))
                continue

            m = RETRY_HIT.search(line)
            if m:
                cur = {"first_rc": int(m.group(1)), "first_scanned": int(m.group(2)),
                       "first_size": pending_get_size, "first_elapsed": pending_get_elapsed}
                continue

            m = RETRY_RES.search(line)
            if m and cur is not None:
                cur["retry_ok"] = bool(int(m.group(1)))
                cur["retry_rc"] = int(m.group(2))
                cur["retry_scanned"] = int(m.group(3))
                cur["retry_size"] = pending_get_size
                cur["retry_elapsed"] = pending_get_elapsed
                continue

            m = FINAL_RE.search(line)
            if m:
                final = {
                    "ok": bool(int(m.group(1))), "errorCode": int(m.group(2)),
                    "count": int(m.group(3)), "scanned": int(m.group(4)),
                }
                if cur is not None:
                    # this cycle had a retry — merge in what we captured above
                    final.update(cur)
                    final["retried"] = True
                else:
                    final["retried"] = False
                    final["first_size"] = pending_get_size
                    final["first_elapsed"] = pending_get_elapsed
                cycles.append(final)
                cur = None
                elapsed_s = time.monotonic() - t_start
                print(f"  [pr-fetch-soak] t+{elapsed_s:.0f}s cycle={len(cycles)} "
                      f"ok={final['ok']} size={final.get('first_size')} "
                      f"scanned={final['scanned']} retried={final['retried']}", flush=True)

    except Exception as e:
        print(f"[pr-fetch-soak] exception: {e}")
    finally:
        if args.loc_slot is not None and orig_slot is not None:
            try:
                olabel, olat, olon = orig_slot
                if olabel:
                    _set_prloc_slot(dut, args.loc_slot, olabel, olat, olon)
                    print(f"[pr-fetch-soak] restored slot {args.loc_slot} -> "
                          f"{olabel} {olat},{olon}")
                else:
                    print(f"[pr-fetch-soak] slot {args.loc_slot} was empty before — "
                          f"left holding {args.label} {args.lat},{args.lon} "
                          f"(no clear-slot command exists to restore emptiness)")
                if orig_active is not None:
                    _set_prloc_active(dut, orig_active)
                    print(f"[pr-fetch-soak] restored active slot -> {orig_active}")
            except Exception as e:
                print(f"[pr-fetch-soak] WARNING: prloc restore failed: {e} — "
                      f"check 'get prloc' by hand")
        elif args.active_slot is not None and orig_active is not None:
            try:
                _set_prloc_active(dut, orig_active)
                print(f"[pr-fetch-soak] restored active slot -> {orig_active}")
            except Exception as e:
                print(f"[pr-fetch-soak] WARNING: active-slot restore failed: {e} — "
                      f"check 'get prloc' by hand")
        try:
            _restore_spotify(dut, timeout=10.0)
        except Exception:
            pass
        dut.close()

    print("\n" + "=" * 78)
    if crashed:
        print("VERDICT: ABORTED — crash/reboot signature seen mid-soak")
        sys.exit(1)
    if not cycles:
        print("VERDICT: NO DATA — zero fetch cycles observed in the soak window")
        sys.exit(1)

    total = len(cycles)
    retried = sum(1 for c in cycles if c.get("retried"))
    first_fail = retried + sum(1 for c in cycles if not c.get("ok") and not c.get("retried"))
    final_fail = sum(1 for c in cycles if not c["ok"])
    retry_also_failed = sum(1 for c in cycles if c.get("retried") and not c["ok"])

    print(f"Total cycles:                {total}")
    print(f"First-attempt failures:      {first_fail} ({100 * first_fail / total:.1f}%)")
    print(f"  of which retried:          {retried}")
    if retried:
        print(f"  retry ALSO failed:         {retry_also_failed} "
              f"({100 * retry_also_failed / retried:.1f}% of retries)")
    else:
        print("  retry ALSO failed:         n/a (no retries this soak)")
    print(f"Final (post-retry) failures: {final_fail} ({100 * final_fail / total:.1f}%)")
    print()

    def _bucketed(key_fn, buckets, bucket_fn, label):
        by = {}
        skipped = 0
        for c in cycles:
            v = key_fn(c)
            if v is None:
                skipped += 1
                continue
            b = bucket_fn(v)
            by.setdefault(b, {"total": 0, "first_fail": 0, "final_fail": 0})
            by[b]["total"] += 1
            if c.get("retried") or (not c["ok"] and not c.get("retried")):
                by[b]["first_fail"] += 1
            if not c["ok"]:
                by[b]["final_fail"] += 1
        print(f"-- by {label} --")
        print(f"{'bucket':<14}{'cycles':<9}{'1st-fail%':<12}{'final-fail%':<12}")
        for lo, hi in buckets:
            key = bucket_fn(lo)
            d = by.get(key)
            if not d:
                continue
            print(f"{key:<14}{d['total']:<9}"
                  f"{100 * d['first_fail'] / d['total']:<12.1f}"
                  f"{100 * d['final_fail'] / d['total']:<12.1f}")
        if skipped:
            print(f"  ({skipped} cycles had no declared size logged — GET line missed/dropped)")
        print()

    print("PRIMARY (size-scaling verdict) — declared Content-Length, truncation-independent:")
    _bucketed(lambda c: c.get("first_size"), SIZE_BUCKETS, _size_bucket, "declared size")

    print("SECONDARY — GET elapsed time (tells time-based vs body-fraction-based cutoff apart):")
    _bucketed(lambda c: c.get("first_elapsed"), ELAPSED_BUCKETS, _elapsed_bucket, "GET elapsed")

    print("=" * 78)
    print("Read the PRIMARY table: if 1st-fail%/final-fail% climb with declared size,")
    print("that CONFIRMS the size-scaling hypothesis. If failure rate is roughly flat")
    print("across size buckets, the TASK-361 regression has a different cause than")
    print("payload size — look elsewhere (time-of-day rate limiting, edge load, etc.)")
    print("before scoping a fix. The SECONDARY table distinguishes a time-based edge")
    print("cutoff (correlates with elapsed, not size directly) from a genuinely")
    print("body-size-keyed one.")


if __name__ == "__main__":
    main()
