# model.py — shared data model for the PROP-006 interpolation study.
#
# Units: positions in local ENU metres around the radar centre (equirect
# approximation — fine at <=25 km range), speeds m/s, track compass degrees.
# ADS-B wire fields mirror dataTask.h PrAircraft: lat/lon float, whole-degree
# track (int), gs knots (int) — quantization is applied at the *fix* level so
# every algorithm sees exactly what the firmware would see.
#
# Pixel projection: radar disc centre (120,120), R=118 px (planeRadarApp.h
# PR_CX/PR_CY/PR_R); we treat the outer ring as the active range preset, so
# px_per_m = 118 / (preset_km * 1000). If the firmware's ring3-vs-outer
# mapping differs by a constant factor it scales every algorithm identically
# and does not change the ranking.

from dataclasses import dataclass
import math

KNOTS_TO_MS = 0.514444
EARTH_R = 6371000.0

PR_R_PX = 118
PRESETS_KM = (5, 10, 15, 25)


@dataclass
class Fix:
    """One ADS-B sample as the firmware would receive it (post-quantization)."""
    t: float            # seconds
    x: float            # ENU metres east of radar centre
    y: float            # ENU metres north
    track_deg: int      # whole-degree compass track (0 = north, cw)
    gs_knots: int       # integer knots


@dataclass
class TruthState:
    """Continuous ground-truth state (pre-quantization)."""
    t: float
    x: float
    y: float
    track_deg: float
    gs_ms: float


def track_to_vxy(track_deg: float, gs_ms: float) -> tuple[float, float]:
    """Compass track+speed -> ENU velocity (vx east, vy north)."""
    r = math.radians(track_deg)
    return gs_ms * math.sin(r), gs_ms * math.cos(r)


def quantize(s: TruthState, jitter_m: float = 0.0, rng=None) -> Fix:
    """Apply ADS-B wire quantization (+ optional GPS jitter) to a truth state."""
    x, y = s.x, s.y
    if rng is not None and jitter_m > 0.0:
        x += rng.gauss(0.0, jitter_m)
        y += rng.gauss(0.0, jitter_m)
    return Fix(
        t=s.t, x=x, y=y,
        track_deg=int(round(s.track_deg)) % 360,
        gs_knots=int(round(s.gs_ms / KNOTS_TO_MS)),
    )


def px_per_m(preset_km: int) -> float:
    return PR_R_PX / (preset_km * 1000.0)


def to_px(x_m: float, y_m: float, preset_km: int) -> tuple[float, float]:
    """ENU metres -> screen px (y down), radar centre (120,120)."""
    s = px_per_m(preset_km)
    return 120.0 + x_m * s, 120.0 - y_m * s
