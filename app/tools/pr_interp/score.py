# score.py — PROP-006 score matrix: cadence x algorithm on synthetic truth.
#
# Metrics per (scenario, cadence, algorithm), all in DISPLAY PIXELS at the
# chosen range preset (default 10 km), rendered at 30 fps:
#   rms_px   — RMS position error vs truth (accuracy incl. staleness)
#   p95_px   — tail error
#   jump_px  — max frame-to-frame rendered displacement BEYOND what the
#              aircraft's true speed explains (the teleport artifact;
#              0 = perfectly smooth, snap corrections show up here)
#   jit_degs — RMS frame-to-frame change of rendered heading, deg/frame
#              (visual wobble; quantization noise amplifiers show up here)
#
# Usage:  python3 score.py [--preset 10] [--minutes 6] [--md out.md]

import argparse
import math
import statistics

from model import to_px, px_per_m, PRESETS_KM
from synth import default_scenarios, integrate, truth_at, sample_fixes
from algorithms import ladder

FPS = 30
CADENCES_S = (1, 5, 10, 15, 30)


def run_one(states, fixes, algo, preset_km):
    """Replay: deliver fixes in time order while rendering at FPS."""
    errs, jumps, jits = [], [], []
    fi = 0
    prev_px = None
    prev_head = None
    t0, t_end = fixes[0].t, states[-1].t
    frames = int((t_end - t0) * FPS)
    for n in range(frames):
        t = t0 + n / FPS
        while fi < len(fixes) and fixes[fi].t <= t:
            algo.update(fixes[fi])
            fi += 1
        pos = algo.position(t)
        if pos is None:
            prev_px = None
            continue
        px = to_px(pos[0], pos[1], preset_km)
        tr = truth_at(states, t)
        tpx = to_px(tr.x, tr.y, preset_km)
        errs.append(math.dist(px, tpx))
        if prev_px is not None:
            step = math.dist(px, prev_px)
            # displacement the true ground speed explains in one frame:
            allowed = tr.gs_ms * px_per_m(preset_km) / FPS
            jumps.append(max(0.0, step - allowed * 1.5))  # 50% slack
            if step > 0.05:
                head = math.atan2(px[1] - prev_px[1], px[0] - prev_px[0])
                if prev_head is not None:
                    d = math.degrees(head - prev_head)
                    while d > 180: d -= 360
                    while d < -180: d += 360
                    jits.append(d)
                prev_head = head
        prev_px = px
    if not errs:
        return None
    return {
        "rms_px": math.sqrt(sum(e * e for e in errs) / len(errs)),
        "p95_px": statistics.quantiles(errs, n=20)[18] if len(errs) > 20 else max(errs),
        "jump_px": max(jumps) if jumps else 0.0,
        "jit_degs": math.sqrt(sum(j * j for j in jits) / len(jits)) if jits else 0.0,
    }


def sweep(preset_km=10, minutes=6.0, seed=42):
    rows = []
    for sc in default_scenarios(preset_km):
        states = integrate(sc, minutes * 60)
        for cad in CADENCES_S:
            fixes = sample_fixes(states, cad, seed=seed)
            if len(fixes) < 4:
                continue
            for algo in ladder():
                m = run_one(states, fixes, algo, preset_km)
                if m:
                    rows.append({"scenario": sc.name, "cadence": cad,
                                 "algo": algo.name, **m})
    return rows


def aggregate(rows):
    """Mean over scenarios -> one row per (cadence, algo)."""
    agg = {}
    for r in rows:
        k = (r["cadence"], r["algo"])
        agg.setdefault(k, []).append(r)
    out = []
    for (cad, algo), rs in sorted(agg.items()):
        out.append({
            "cadence": cad, "algo": algo,
            "rms_px": statistics.mean(x["rms_px"] for x in rs),
            "p95_px": statistics.mean(x["p95_px"] for x in rs),
            "jump_px": max(x["jump_px"] for x in rs),
            "jit_degs": statistics.mean(x["jit_degs"] for x in rs),
        })
    return out


def render_md(agg_rows):
    lines = ["| cadence | algorithm | RMS px | p95 px | max jump px | jitter °/fr |",
             "|---|---|---|---|---|---|"]
    for r in agg_rows:
        lines.append(f"| {r['cadence']} s | {r['algo']} | {r['rms_px']:.1f} "
                     f"| {r['p95_px']:.1f} | {r['jump_px']:.1f} | {r['jit_degs']:.2f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", type=int, default=10, choices=PRESETS_KM)
    ap.add_argument("--minutes", type=float, default=6.0)
    ap.add_argument("--md", help="write markdown table to file")
    a = ap.parse_args()
    rows = sweep(a.preset, a.minutes)
    md = render_md(aggregate(rows))
    print(md)
    if a.md:
        with open(a.md, "w") as f:
            f.write(md + "\n")
