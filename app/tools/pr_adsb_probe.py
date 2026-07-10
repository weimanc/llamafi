#!/usr/bin/env python3
"""pr_adsb_probe.py — M-PLANERADAR phase 0: adsb.fi API probe.

Design: docs/architecture/designs/M-PLANERADAR/phase0-api-probe.md

Modes:
  --survey                 one fetch per (site x preset), print summary table
  --soak HOURS             sustained polling at --interval (default 10 s), JSONL log
  --census N               field-presence census over N fetches (site: --site)
  --capture NAME           save one raw body to fixtures/planeradar/NAME.json
  --limit-probe            bounded 60 s ramp to 1 req/s, record API behaviour

Run from the project venv: ~/proj/esp/venv/bin/python3 app/tools/pr_adsb_probe.py --survey
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from collections import Counter

import requests

API_BASE = "https://opendata.adsb.fi/api/v3"
HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "planeradar"

# Probe matrix (phase0-api-probe.md): site name -> (lat, lon)
SITES = {
    "home": (52.3676, 4.9041),      # reference default, Amsterdam area
    "schiphol": (52.3086, 4.7639),  # busy TMA worst case
    "rural": (52.8, 6.9),           # sparse control
}

# Range presets (km) -> fetch radius, mirroring reference radar_range.cpp::fetchRadiusKm():
# outer_km = preset * 4/3 (ring 3 = 3/4 of outer), then scaled to the screen edge
# by (screen_r_px / kGridOuterRadius) = 118/107 ~= 1.103.
PRESETS_KM = [5, 10, 15, 25]
KM_PER_NM = 1.852
SCREEN_EDGE_SCALE = 118.0 / 107.0


def fetch_radius_nm(preset_km: float) -> float:
    return preset_km * (4.0 / 3.0) * SCREEN_EDGE_SCALE / KM_PER_NM


def fetch(lat: float, lon: float, dist_nm: float, timeout: float = 10.0):
    """Single API GET. Returns (http_code, elapsed_s, body_bytes, parsed_or_None, error_str).

    Exposed for reuse by preview_planeradar.py live mode (phase0-preview-ui.md).
    """
    url = f"{API_BASE}/lat/{lat:.6f}/lon/{lon:.6f}/dist/{dist_nm:.1f}"
    t0 = time.monotonic()
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        return 0, time.monotonic() - t0, 0, None, type(e).__name__
    elapsed = time.monotonic() - t0
    body = r.content
    parsed = None
    err = ""
    if r.status_code == 200:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as e:
            err = f"truncated/parse: {e}"
    return r.status_code, elapsed, len(body), parsed, err


def ac_list(parsed) -> list:
    if not parsed:
        return []
    ac = parsed.get("ac")
    return ac if isinstance(ac, list) else []


def cmd_survey(args) -> None:
    print(f"{'site':<10} {'preset':>6} {'dist_nm':>7} {'http':>4} {'ms':>6} {'bytes':>8} {'ac':>4}")
    for site, (lat, lon) in SITES.items():
        for preset in PRESETS_KM:
            nm = fetch_radius_nm(preset)
            code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
            n = len(ac_list(parsed))
            print(f"{site:<10} {preset:>4}km {nm:>7.1f} {code:>4} {dt*1000:>6.0f} {nbytes:>8} {n:>4}"
                  + (f"  ERR {err}" if err else ""))
            time.sleep(1.2)  # stay under 1 req/s


def cmd_capture(args) -> None:
    lat, lon = SITES[args.site]
    nm = fetch_radius_nm(args.preset)
    code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
    if code != 200 or err:
        sys.exit(f"capture failed: http={code} err={err}")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    raw = FIXTURES / f"{args.capture}.json"
    # Store raw compact body byte-exact is ideal; requests already gave us bytes.
    url_note = f"{API_BASE}/lat/{lat:.6f}/lon/{lon:.6f}/dist/{nm:.1f}"
    raw.write_text(json.dumps(parsed, separators=(",", ":")))
    pretty = FIXTURES / f"{args.capture}.pretty.json"
    pretty.write_text(json.dumps(parsed, indent=1))
    print(f"captured {raw} bytes={nbytes} ac={len(ac_list(parsed))} from {url_note}")


def cmd_census(args) -> None:
    lat, lon = SITES[args.site]
    nm = fetch_radius_nm(25)
    present: Counter = Counter()
    types: Counter = Counter()
    total = 0
    fetches = 0
    while total < args.census:
        code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
        fetches += 1
        for plane in ac_list(parsed):
            total += 1
            for k, v in plane.items():
                present[k] += 1
                types[f"{k}:{type(v).__name__}"] += 1
        time.sleep(max(args.interval, 1.2))
        if fetches > 200:
            break
    print(f"census: {total} aircraft records over {fetches} fetches @ {args.site}")
    for k, n in sorted(present.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<16} {n:>6}  {100.0*n/total:5.1f}%")
    print("value types:")
    for k, n in sorted(types.items()):
        print(f"  {k:<24} {n:>6}")


def cmd_soak(args) -> None:
    lat, lon = SITES[args.site]
    nm = fetch_radius_nm(args.preset)
    out = pathlib.Path(args.log)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_total = int(args.soak * 3600 / args.interval)
    print(f"soak: {n_total} fetches @ {args.interval}s, site={args.site} preset={args.preset}km -> {out}")
    with out.open("a") as f:
        for i in range(n_total):
            t_wall = time.time()
            code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
            rec = {
                "t": round(t_wall, 1),
                "http": code,
                "ms": round(dt * 1000),
                "bytes": nbytes,
                "ac": len(ac_list(parsed)),
                "err": err,
            }
            f.write(json.dumps(rec) + "\n")
            f.flush()
            time.sleep(max(0.0, args.interval - (time.time() - t_wall)))
    print("soak done")


def cmd_hunt_max(args) -> None:
    """Poll site at --interval for --soak hours; save body each time ac-count sets a new max.

    Purpose: catch the daytime-peak worst case as fixtures/planeradar/busy_33km.json
    without babysitting (night captures are unrepresentative)."""
    lat, lon = SITES[args.site]
    nm = fetch_radius_nm(args.preset)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    best = -1
    n_total = int(args.soak * 3600 / args.interval)
    print(f"hunt-max: {n_total} fetches @ {args.interval}s, site={args.site} preset={args.preset}km")
    for i in range(n_total):
        t0 = time.time()
        code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
        n = len(ac_list(parsed))
        if code == 200 and not err and n > best:
            best = n
            (FIXTURES / f"{args.capture}.json").write_text(
                json.dumps(parsed, separators=(",", ":")))
            (FIXTURES / f"{args.capture}.pretty.json").write_text(
                json.dumps(parsed, indent=1))
            print(f"  [{time.strftime('%H:%M:%S')}] new max ac={n} bytes={nbytes} -> {args.capture}.json")
        time.sleep(max(0.0, args.interval - (time.time() - t0)))
    print(f"hunt-max done, max ac={best}")


def cmd_limit_probe(args) -> None:
    """Bounded: <=60 requests at 1 req/s against the sparse site. One run only."""
    lat, lon = SITES["rural"]
    nm = fetch_radius_nm(5)
    codes: Counter = Counter()
    print("limit-probe: 60 s at 1 req/s (public courtesy limit) — bounded, single run")
    for i in range(60):
        t0 = time.time()
        code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
        codes[code] += 1
        if code != 200 or err:
            print(f"  [{i:02d}] http={code} bytes={nbytes} err={err}")
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))
    print("code histogram:", dict(codes))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--survey", action="store_true")
    p.add_argument("--soak", type=float, metavar="HOURS")
    p.add_argument("--census", type=int, metavar="N")
    p.add_argument("--capture", metavar="NAME")
    p.add_argument("--limit-probe", action="store_true")
    p.add_argument("--hunt-max", action="store_true",
                   help="with --soak/--interval/--capture: save body on each new ac-count max")
    p.add_argument("--site", choices=SITES, default="home")
    p.add_argument("--preset", type=int, choices=PRESETS_KM, default=10)
    p.add_argument("--interval", type=float, default=10.0)
    p.add_argument("--log", default=str(HERE / "fixtures" / "planeradar" / "soak.jsonl"))
    args = p.parse_args()

    if args.survey:
        cmd_survey(args)
    elif args.hunt_max:
        cmd_hunt_max(args)
    elif args.soak:
        cmd_soak(args)
    elif args.census:
        cmd_census(args)
    elif args.capture:
        cmd_capture(args)
    elif args.limit_probe:
        cmd_limit_probe(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
