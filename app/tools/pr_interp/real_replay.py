#!/usr/bin/env python3
"""real_replay.py — TASK-360: replay dr-damped(tau=2) against REAL London
adsb.fi captures instead of only EXP-014's synthetic scenarios, and test the
human's speed+altitude hypothesis against the same data.

Loads app/tools/fixtures/planeradar/task360_london/london_<cad>_*.json (the
TASK-360 capture set: 8 discrete samples each at nominal 1s/5s/10s intervals,
25 km preset, London/Westminster 51.50830078,-0.1253000), matches aircraft by
`hex` across consecutive samples within each cadence run, and for every
consecutive pair (fix_i -> fix_{i+1}) computes:

  - the RAW dead-reckon correction magnitude in display px (what dr-snap
    would show as a teleport, and what dr-damped(tau=2) spreads over ~2s) —
    same physical quantity EXP-014 scored as `jump_px` on synthetic truth.
  - explanatory variables at fix_i: |track change| deg (turning), |gs
    change| kt (speed change), baro_rate ft/min (vertical rate, signed),
    |altitude change| ft between the pair.

Then reports: (1) real vs synthetic jump-px distribution, (2) correlation of
correction magnitude against turning vs against vertical-rate/altitude-change,
to disposition the speed+altitude hypothesis without assuming the answer.

Run: ~/proj/esp/venv/bin/python3 app/tools/pr_interp/real_replay.py
"""

from __future__ import annotations

import glob
import json
import math
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0]))  # app/tools (pr_adsb_probe)

from model import Fix, track_to_vxy, to_px, px_per_m, KNOTS_TO_MS, EARTH_R  # noqa: E402

FIXTURE_DIR = HERE.parents[0] / "fixtures" / "planeradar" / "task360_london"
CENTER_LAT = 51.50830078
CENTER_LON = -0.1253000
PRESET_KM = 25


def load_run(cadence_label: str):
    files = sorted(
        p for p in glob.glob(str(FIXTURE_DIR / f"london_{cadence_label}_*.json"))
        if "pretty" not in p
    )
    samples = []
    for f in files:
        d = json.loads(pathlib.Path(f).read_text())
        samples.append((d["now"] / 1000.0, {a["hex"]: a for a in d["ac"] if a.get("lat") is not None}))
    return samples


def to_enu(lat, lon):
    coslat = math.cos(math.radians(CENTER_LAT))
    x = math.radians(lon - CENTER_LON) * EARTH_R * coslat
    y = math.radians(lat - CENTER_LAT) * EARTH_R
    return x, y


def build_pairs(samples):
    """Yield (hex, fix_i, fix_ip1, raw_a_i, raw_a_ip1) for every consecutive
    sample pair where the aircraft is present in both and reports track+gs."""
    out = []
    for (t0, m0), (t1, m1) in zip(samples, samples[1:]):
        common = set(m0) & set(m1)
        for h in common:
            a0, a1 = m0[h], m1[h]
            if a0.get("alt_baro") == "ground" or a1.get("alt_baro") == "ground":
                continue  # taxiing aircraft: not the DR use case
            trk0 = a0.get("track")
            gs0 = a0.get("gs")
            if trk0 is None or gs0 is None:
                continue
            x0, y0 = to_enu(a0["lat"], a0["lon"])
            x1, y1 = to_enu(a1["lat"], a1["lon"])
            f0 = Fix(t=t0, x=x0, y=y0, track_deg=int(round(trk0)) % 360, gs_knots=int(round(gs0)))
            f1 = Fix(t=t1, x=x1, y=y1, track_deg=0, gs_knots=0)  # track/gs unused for f1 here
            out.append((h, f0, f1, a0, a1))
    return out


def ang_diff(a, b):
    d = (b - a + 180) % 360 - 180
    return d


def analyze(cadence_label):
    samples = load_run(cadence_label)
    pairs = build_pairs(samples)
    rows = []
    for h, f0, f1, a0, a1 in pairs:
        dt = f1.t - f0.t
        if dt <= 0:
            continue
        vx, vy = track_to_vxy(f0.track_deg, f0.gs_knots * KNOTS_TO_MS)
        pred_x, pred_y = f0.x + vx * dt, f0.y + vy * dt
        err_m = math.dist((pred_x, pred_y), (f1.x, f1.y))
        err_px = err_m * px_per_m(PRESET_KM)

        track1 = a1.get("track")
        trk_change = abs(ang_diff(f0.track_deg, track1)) if track1 is not None else None
        gs1 = a1.get("gs")
        gs_change = abs(gs1 - a0.get("gs")) if gs1 is not None and a0.get("gs") is not None else None
        baro_rate = a0.get("baro_rate")
        geom_rate = a0.get("geom_rate")
        alt0 = a0.get("alt_baro")
        alt1 = a1.get("alt_baro")
        alt_change = None
        if isinstance(alt0, (int, float)) and isinstance(alt1, (int, float)):
            alt_change = abs(alt1 - alt0)

        rows.append({
            "hex": h, "dt": dt, "err_px": err_px,
            "trk_change": trk_change, "gs_change": gs_change,
            "baro_rate": baro_rate, "geom_rate": geom_rate,
            "alt_change": alt_change,
        })
    return rows


def pearson(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pts) < 5:
        return None, len(pts)
    xs2, ys2 = zip(*pts)
    try:
        return statistics.correlation(xs2, ys2), len(pts)
    except statistics.StatisticsError:
        return None, len(pts)


def summarize(cadence_label, rows):
    print(f"\n== cadence {cadence_label} (n={len(rows)} matched consecutive-fix pairs) ==")
    errs = [r["err_px"] for r in rows]
    print(f"  err_px: mean={statistics.mean(errs):.2f} median={statistics.median(errs):.2f} "
          f"p95={sorted(errs)[int(0.95*len(errs))]:.2f} max={max(errs):.2f}")

    r_trk, n_trk = pearson([r["trk_change"] for r in rows], errs)
    r_gs, n_gs = pearson([r["gs_change"] for r in rows], errs)
    r_baro, n_baro = pearson([abs(r["baro_rate"]) if r["baro_rate"] is not None else None
                               for r in rows], errs)
    r_geom, n_geom = pearson([abs(r["geom_rate"]) if r["geom_rate"] is not None else None
                               for r in rows], errs)
    r_alt, n_alt = pearson([r["alt_change"] for r in rows], errs)
    print(f"  corr(err_px, |track_change_deg|)  r={r_trk!s:>8} (n={n_trk})")
    print(f"  corr(err_px, |gs_change_kt|)      r={r_gs!s:>8} (n={n_gs})")
    print(f"  corr(err_px, |baro_rate_fpm|)     r={r_baro!s:>8} (n={n_baro})")
    print(f"  corr(err_px, |geom_rate_fpm|)     r={r_geom!s:>8} (n={n_geom})")
    print(f"  corr(err_px, |alt_change_ft|)     r={r_alt!s:>8} (n={n_alt})")

    # Level vs vertically-active split (>=250 fpm magnitude = FAA "level" threshold-ish)
    level = [r for r in rows if r["baro_rate"] is not None and abs(r["baro_rate"]) < 250]
    vertical = [r for r in rows if r["baro_rate"] is not None and abs(r["baro_rate"]) >= 250]
    if level and vertical:
        print(f"  level flight  (|baro_rate|<250fpm, n={len(level)}): "
              f"mean err_px={statistics.mean(r['err_px'] for r in level):.2f}")
        print(f"  climbing/descending (n={len(vertical)}): "
              f"mean err_px={statistics.mean(r['err_px'] for r in vertical):.2f}")

    # Turning vs straight split (>=3 deg/interval as a coarse "maneuvering" cut)
    straight = [r for r in rows if r["trk_change"] is not None and r["trk_change"] < 3]
    turning = [r for r in rows if r["trk_change"] is not None and r["trk_change"] >= 3]
    if straight and turning:
        print(f"  straight (|trk_change|<3deg, n={len(straight)}): "
              f"mean err_px={statistics.mean(r['err_px'] for r in straight):.2f}")
        print(f"  turning  (n={len(turning)}): "
              f"mean err_px={statistics.mean(r['err_px'] for r in turning):.2f}")

    # Among level-flight-only rows, does vertical rate still explain anything?
    # (guards against "vertical rate is just a turning proxy" confound)
    if len(level) >= 5:
        r_lvl, n_lvl = pearson([r["trk_change"] for r in level], [r["err_px"] for r in level])
        print(f"  within level flight, corr(err_px, |track_change|) r={r_lvl!s:>8} (n={n_lvl})")
    return rows


def main():
    all_rows = {}
    for cad in ("1s", "5s", "10s"):
        rows = analyze(cad)
        all_rows[cad] = summarize(cad, rows)

    all_errs = [r["err_px"] for rows in all_rows.values() for r in rows]
    print(f"\n== combined all cadences (n={len(all_errs)}) ==")
    print(f"  err_px: mean={statistics.mean(all_errs):.2f} median={statistics.median(all_errs):.2f} "
          f"p95={sorted(all_errs)[int(0.95*len(all_errs))]:.2f} max={max(all_errs):.2f}")
    print("  (EXP-014 synthetic dr-snap jump_px @ 10s cadence, mean over scenarios: 9.6 px)")


if __name__ == "__main__":
    main()
