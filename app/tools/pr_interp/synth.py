# synth.py — synthetic ground truth for the PROP-006 study.
#
# Generates continuous aircraft tracks with the manoeuvre repertoire that
# actually stresses interpolation, then samples them at 1 Hz through the
# same quantization the real feed has (whole-degree track, int knots,
# GPS jitter, random dropout). The capture session later replaces this with
# real fixtures via the identical Fix schema — nothing downstream changes.
#
# Scenarios (one aircraft each):
#   cruise    — straight & level through the disc (the easy case)
#   turn      — standard-rate turn (3 deg/s), the classic interpolation killer
#   holding   — racetrack: straights + alternating standard-rate turns
#   approach  — decelerating descent line (speed change, not just heading)
#   climbout  — accelerating departure with a shallow 1.5 deg/s turn

import math
import random
from dataclasses import dataclass, field

from model import TruthState, Fix, quantize, track_to_vxy, KNOTS_TO_MS


@dataclass
class Scenario:
    name: str
    x: float
    y: float
    track_deg: float
    gs_knots: float
    # piecewise script: list of (duration_s, turn_rate_deg_s, accel_kn_s)
    script: list = field(default_factory=list)


def default_scenarios(preset_km: int = 10) -> list[Scenario]:
    r = preset_km * 1000.0
    return [
        Scenario("cruise",   -r * 0.9, -r * 0.4,  70, 250,
                 [(600, 0.0, 0.0)]),
        Scenario("turn",     -r * 0.5,  r * 0.5, 130, 210,
                 [(60, 0.0, 0.0), (60, 3.0, 0.0), (600, 0.0, 0.0)]),
        Scenario("holding",   r * 0.4,  r * 0.3, 270, 180,
                 [(45, 0.0, 0.0), (60, 3.0, 0.0)] * 8),
        Scenario("approach", -r * 0.8,  r * 0.8, 145, 180,
                 [(600, 0.0, -0.15)]),
        Scenario("climbout",  r * 0.1, -r * 0.2, 350, 160,
                 [(30, 0.0, 0.4), (90, 1.5, 0.2), (600, 0.0, 0.0)]),
    ]


def integrate(sc: Scenario, duration_s: float, dt: float = 0.1) -> list[TruthState]:
    """Integrate one scenario at dt resolution. Returns dense truth states."""
    out = []
    x, y, trk, gs = sc.x, sc.y, sc.track_deg, sc.gs_knots * KNOTS_TO_MS
    seg = list(sc.script)
    seg_left = seg[0][0] if seg else float("inf")
    seg_i = 0
    t = 0.0
    while t <= duration_s:
        out.append(TruthState(t=t, x=x, y=y, track_deg=trk % 360.0, gs_ms=gs))
        rate = seg[seg_i][1] if seg_i < len(seg) else 0.0
        acc = seg[seg_i][2] * KNOTS_TO_MS if seg_i < len(seg) else 0.0
        trk += rate * dt
        gs = max(30 * KNOTS_TO_MS, gs + acc * dt)
        vx, vy = track_to_vxy(trk, gs)
        x += vx * dt
        y += vy * dt
        t += dt
        seg_left -= dt
        if seg_left <= 0 and seg_i < len(seg) - 1:
            seg_i += 1
            seg_left = seg[seg_i][0]
    return out


def truth_at(states: list[TruthState], t: float) -> TruthState:
    """Linear interp into the dense truth (dt=0.1 — error negligible)."""
    if t <= states[0].t:
        return states[0]
    if t >= states[-1].t:
        return states[-1]
    i = min(int(t / (states[1].t - states[0].t)), len(states) - 2)
    a, b = states[i], states[i + 1]
    f = (t - a.t) / (b.t - a.t) if b.t > a.t else 0.0
    return TruthState(
        t=t,
        x=a.x + (b.x - a.x) * f,
        y=a.y + (b.y - a.y) * f,
        track_deg=a.track_deg,   # good enough for truth comparison
        gs_ms=a.gs_ms + (b.gs_ms - a.gs_ms) * f,
    )


def sample_fixes(states: list[TruthState], cadence_s: float,
                 jitter_m: float = 8.0, dropout: float = 0.05,
                 seed: int = 42) -> list[Fix]:
    """Downsample dense truth to the poll cadence with wire quantization.

    dropout models missed polls (real feed: fetch errors, aircraft momentarily
    absent from the response) — a dropped fix simply widens the gap, which is
    exactly what the reconstructors must survive.
    """
    rng = random.Random(seed)
    fixes = []
    t = 0.0
    end = states[-1].t
    while t <= end:
        if rng.random() >= dropout:
            fixes.append(quantize(truth_at(states, t), jitter_m, rng))
        t += cadence_s
    return fixes
