#!/usr/bin/env python3
"""preview_planeradar.py — M-PLANERADAR phase 0 UI proof-of-concept.

Design: docs/architecture/designs/M-PLANERADAR/phase0-preview-ui.md

Renders the plane-radar app canvas (275×240 + taskbar) from adsb.fi fixtures,
a synthetic traffic generator, or live API polls. Iterates the OQ4 layout
question (side strip vs on-disc furniture), tag-collision rules, and rim-dot
treatment before any firmware exists.

Keys:
  click disc   cycle range preset (5/10/15/25 km) — the firmware tap gesture
  l            toggle layout variant: strip | disc  (OQ4 / Q1)
  c            cycle tag-collision rule: a=reference b=+nudge c=+drop (Q2)
  r            toggle rim-dot placement: disc-rim | canvas-edge (Q3)
  a            cycle runway label density: all | nearest | off (Q4)
  h            toggle location-slot highlight: inverse-box | colour-emphasis
                (M-PR-LOCATIONS TASK-316)
  f            next fixture   F  previous fixture
  s            toggle synthetic mode        L  live fetch mode (10 s cadence)
  SPACE        advance one frame (synthetic/replay)
  p            save PNG   g  record 10 s GIF
  +/- or 1..4  zoom       q  quit
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import preview_common as pc
import dut_fonts

HERE = pathlib.Path(__file__).parent
FIXTURES = sorted((HERE / "fixtures" / "planeradar").glob("*.json"),
                  key=lambda p: p.name)
FIXTURES = [p for p in FIXTURES
            if not p.name.endswith(".pretty.json") and p.suffix == ".json"
            and p.name not in ("truncated.json",)]
IMG_OUT = HERE.parent.parent / "docs" / "architecture" / "designs" / "M-PLANERADAR" / "img"
# TASK-316 (M-PR-LOCATIONS): location-slot strip eyeball-gate PNGs live under
# the sibling milestone's img/ dir, not M-PLANERADAR's.
PRLOC_IMG_OUT = (HERE.parent.parent / "docs" / "architecture" / "designs"
                 / "M-PR-LOCATIONS" / "img")
AIRPORTS_PATH = HERE / "fixtures" / "planeradar" / "airports_preview.json"

# ── palette (RGB565-safe; radar_theme.h equivalents) ──────────────────────────
def rgb565(r, g, b):
    """Quantise an (r,g,b) to what RGB565 can actually show."""
    return (r & 0xF8, g & 0xFC, b & 0xF8)

# Matched 1:1 to the reference's radar_theme.h initPalette() (ESP32-Plane-Radar).
# Constants with no reference counterpart (STRIP_*, STALE, ERR — our square-panel
# side strip has no analogue in the reference's round-display UI) are our own
# design calls, unchanged.
COL_FIELD        = rgb565(4, 10, 28)     # ref kColorBackground
COL_RING         = rgb565(16, 100, 32)   # ref kColorGrid (all rings — no per-ring highlight, matches TASK-312 firmware)
COL_BEZEL        = rgb565(255, 255, 255) # ref kColorLabel / kColorCenter — N/E/S/W + centre dot
COL_AIRCRAFT     = rgb565(255, 0, 0)     # ref kColorAircraft
COL_VECTOR       = rgb565(255, 0, 255)   # ref kColorTrackVector
COL_TAG_CALLSIGN = rgb565(255, 255, 255) # ref kColorLabel
COL_TAG_TYPE     = rgb565(255, 200, 0)   # ref kColorTagType
COL_TAG_ALT      = rgb565(90, 200, 255)  # ref kColorTagAltitude
COL_RUNWAY       = rgb565(56, 150, 170)  # ref kColorRunway
COL_RUNWAY_LABEL = rgb565(110, 210, 230) # ref kColorRunwayLabel
COL_STRIP_BG = rgb565(8, 8, 16)
COL_STRIP_TX = rgb565(160, 255, 160)
COL_STALE    = rgb565(255, 180, 0)
COL_ERR      = rgb565(255, 64, 64)
# M-PR-LOCATIONS (TASK-316): dimmed label colour for inactive slots (colour
# highlight variant) — no reference-project analogue, our own design call.
COL_STRIP_DIM = rgb565(90, 90, 90)

# Location-slot strip band (TASK-316 / M-PR-LOCATIONS "Radar app — strip
# becomes the location switcher"): N^ marker removed outright (Q3) frees
# y55..185; 4 rows (Q1) at ~26 px pitch, comfortably inside that band and
# clear of the AGE row below (drawn at y200 in this tool's strip layout —
# see PR_STRIP_ROW_AGE_Y=193 in planeRadarApp.h for the firmware-side value).
PR_PREVIEW_SLOT_COUNT = 4
PR_PREVIEW_SLOT_Y0    = 68
PR_PREVIEW_SLOT_PITCH = 26

PRESETS_KM = [5, 10, 15, 25]
KM_PER_NM = 1.852

# ── layout variants (Q1) ───────────────────────────────────────────────────────
LAYOUTS = {
    # side strip: disc left, 35 px strip between disc and taskbar
    "strip": {"cx": 120, "cy": 120, "r": 118, "strip_x": 240},
    # on-disc furniture (reference port): disc centred in the 275 px canvas
    "disc":  {"cx": 137, "cy": 120, "r": 118, "strip_x": None},
}

F1 = dut_fonts.Font1()


# ── data sources ───────────────────────────────────────────────────────────────
def load_fixture(path: pathlib.Path) -> list[dict]:
    try:
        return json.loads(path.read_text()).get("ac", []) or []
    except (json.JSONDecodeError, OSError):
        return []


def load_airports() -> list[dict]:
    """Real large_airport runway data (EHAM + EHRD) for the Q4 overlay trial.
    Generated from the same OurAirports source as phase0-airport-db.md's bake
    trial (see fixtures/planeradar/README.md)."""
    try:
        return json.loads(AIRPORTS_PATH.read_text()).get("airports", [])
    except (json.JSONDecodeError, OSError):
        return []


AIRPORTS = load_airports()


def synthetic_frame(t: float) -> list[dict]:
    """Parametric traffic: inbound crosser, orbiter at ring edge, outbound,
    beyond-ring bearing-only target, one field-poor target (fallback test)."""
    ac = []
    lat0, lon0 = 52.3676, 4.9041
    kmlat = 1 / 110.574
    kmlon = 1 / (111.320 * math.cos(math.radians(lat0)))
    # inbound from NE at 250 kn
    d = max(1.0, 18.0 - 0.12 * t)
    ac.append(dict(hex="s1", flight="INBND01", t="B738", alt_baro=8000 - 40 * t,
                   gs=250.0, track=225.0, true_heading=225.0,
                   lat=lat0 + d * 0.707 * kmlat, lon=lon0 + d * 0.707 * kmlon,
                   dst=d / KM_PER_NM, dir=45.0))
    # orbiter near ring 3
    ang = (t * 6.0) % 360.0
    ac.append(dict(hex="s2", flight="ORBIT02", t="C172", alt_baro=2000,
                   gs=90.0, track=(ang + 90) % 360,
                   lat=lat0 + 9.5 * math.cos(math.radians(ang)) * kmlat,
                   lon=lon0 + 9.5 * math.sin(math.radians(ang)) * kmlon,
                   dst=9.5 / KM_PER_NM, dir=ang))
    # outbound west, crosses ring outward
    d2 = 2.0 + 0.10 * t
    ac.append(dict(hex="s3", flight="OUTBW03", t="A320", alt_baro=3000 + 80 * t,
                   gs=210.0, track=270.0,
                   lat=lat0, lon=lon0 - d2 * kmlon,
                   dst=d2 / KM_PER_NM, dir=270.0))
    # beyond-ring SE — rim-dot case
    ac.append(dict(hex="s4", flight="FARAW04", t="B77W", alt_baro=36000,
                   gs=480.0, track=135.0,
                   lat=lat0 - 20.0 * 0.707 * kmlat, lon=lon0 + 20.0 * 0.707 * kmlon,
                   dst=20.0 / KM_PER_NM, dir=135.0))
    # field-poor (no flight/track/gs) near centre — fallback rendering
    ac.append(dict(hex="ABCDEF", alt_baro=1500,
                   lat=lat0 + 1.2 * kmlat, lon=lon0 + 0.4 * kmlon,
                   dst=1.3 / KM_PER_NM, dir=20.0))
    return ac


# ── field pickers (mirror reference fallback chains) ──────────────────────────
def _pick(plane, keys, dflt=0.0):
    for k in keys:
        v = plane.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return dflt


def nose_deg(p):
    # Q6 / phase0-parse-heap.md:108 — firmware stores noseDeg as whole-degree
    # int16_t; round here so the preview renders what ships, not float precision.
    return float(round(_pick(p, ("true_heading", "mag_heading", "track", "dir"))))


def track_deg(p):
    return float(round(_pick(p, ("track", "true_heading", "mag_heading", "dir"))))
def gs_knots(p):  return _pick(p, ("gs", "tas", "ias"))


def callsign(p):
    s = (p.get("flight") or "").strip() or (p.get("hex") or "?")
    return s[:8]


def alt_tag(p):
    ab = p.get("alt_baro")
    if ab == "ground":
        return "GND"
    if isinstance(ab, (int, float)):
        return f"{int(round(ab))}ft"
    ag = p.get("alt_geom")
    if isinstance(ag, (int, float)):
        return f"{int(round(ag))}ft"
    return ""


def is_ground(p):
    return p.get("alt_baro") == "ground"


# ── renderer ───────────────────────────────────────────────────────────────────
class Radar:
    def __init__(self):
        self.layout = "strip"
        self.collision = "b"          # Q2 default candidate
        self.rim_mode = "disc-rim"    # Q3
        self.runway_density = "all"   # Q4 decision: label every in-range airport
        self.preset_i = 1             # 10 km
        self.center = (52.3676, 4.9041)
        self.last_fetch_age = 0.0
        self.http_err = 0
        # M-PR-LOCATIONS (TASK-316): location-slot strip. `slots` is a
        # length-≤4 list, `None`/falsy entries are empty slots (render
        # nothing — Q1..Q3). `highlight` selects the active-slot treatment:
        # "box" = inverse filled box, field-coloured text; "colour" = bright
        # vs dimmed text + left-edge marker bar. Both are the two candidates
        # the design doc leaves for the preview to decide between.
        self.slots = ["HOME", "WORK", "CABIN", "AIRPT"]
        self.active_slot = 0
        self.highlight = "box"        # box | colour

    @property
    def preset_km(self):
        return PRESETS_KM[self.preset_i]

    @property
    def outer_km(self):
        return self.preset_km * 4.0 / 3.0

    def project(self, lat, lon, L):
        """Equirectangular lat/lon → canvas px. North = up."""
        lat0, lon0 = self.center
        dx_km = (lon - lon0) * 111.320 * math.cos(math.radians(lat0))
        dy_km = (lat - lat0) * 110.574
        s = L["r"] / self.outer_km
        return L["cx"] + dx_km * s, L["cy"] - dy_km * s

    def draw(self, planes: list[dict]) -> Image.Image:
        L = LAYOUTS[self.layout]
        img = Image.new("RGB", (pc.SCREEN_W, pc.SCREEN_H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, pc.APP_W - 1, pc.SCREEN_H - 1], fill=COL_FIELD)

        cx, cy, r = L["cx"], L["cy"], L["r"]
        # rings at 1/4..4/4 — all four the same colour (TASK-312: no per-ring
        # highlight, matches both the firmware and the reference).
        for i in (1, 2, 3, 4):
            rr = r * i // 4
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=COL_RING)
        d.line([cx - r, cy, cx + r, cy], fill=COL_RING)
        d.line([cx, cy - r, cx, cy + r], fill=COL_RING)
        d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=COL_BEZEL)

        if self.runway_density != "off":
            self._runways(d, L)

        if self.layout == "disc":
            F1.draw_centered(d, cx, cy - r + 6, "N", COL_BEZEL)
            F1.draw_centered(d, cx, cy + r - 6, "S", COL_BEZEL)
            F1.draw_centered(d, cx - r + 6, cy, "W", COL_BEZEL)
            F1.draw_centered(d, cx + r - 6, cy, "E", COL_BEZEL)
            F1.draw_left(d, cx + r * 3 // 4 + 3, cy - 6, f"{self.preset_km}km", COL_STRIP_TX)

        occupied = []  # tag rects for collision rule
        n_shown = 0
        for p in planes:
            if is_ground(p):
                continue
            x, y = self.project(p["lat"], p["lon"], L)
            dx, dy = x - cx, y - cy
            dist_px = math.hypot(dx, dy)
            if dist_px > r:
                # beyond outer ring — bearing dot (Q3)
                ang = math.atan2(dy, dx)
                if self.rim_mode == "disc-rim":
                    bx, by = cx + (r - 2) * math.cos(ang), cy + (r - 2) * math.sin(ang)
                else:  # canvas-edge
                    k = max(abs(dx) / (pc.APP_W / 2 - 2), abs(dy) / (pc.SCREEN_H / 2 - 2))
                    bx, by = cx + dx / k, cy + dy / k
                d.ellipse([bx - 2, by - 2, bx + 2, by + 2], fill=COL_AIRCRAFT)
                continue
            n_shown += 1
            self._aircraft(d, x, y, p)
            self._tag(d, x, y, p, cx, occupied)

        if self.layout == "strip":
            self._strip(d, n_shown)

        pc.draw_taskbar_pil(img, active_app="")  # no planeradar icon yet — slot TBD
        return img

    def _runways(self, d, L):
        """Q4: draw runway centerlines + ICAO labels for in-range airports.
        density: 'all' labels every in-range airport, 'nearest' labels only
        the closest, 'off' draws nothing (caller already skips this method)."""
        cx, cy, r = L["cx"], L["cy"], L["r"]
        in_range = []
        for ap in AIRPORTS:
            ax, ay = self.project(ap["lat"], ap["lon"], L)
            if math.hypot(ax - cx, ay - cy) <= r:
                in_range.append((ap, ax, ay))
        if not in_range:
            return
        nearest = min(in_range, key=lambda t: math.hypot(t[1] - cx, t[2] - cy))
        for ap, ax, ay in in_range:
            for rw in ap["runways"]:
                lx, ly = self.project(rw["le_lat"], rw["le_lon"], L)
                hx, hy = self.project(rw["he_lat"], rw["he_lon"], L)
                d.line([lx, ly, hx, hy], fill=COL_RUNWAY)
            show_label = self.runway_density == "all" or (ap, ax, ay) is nearest
            if show_label:
                F1.draw_centered(d, int(ax), int(ay) - 9, ap["icao"], COL_RUNWAY_LABEL)

    def _aircraft(self, d, x, y, p):
        nose = math.radians(nose_deg(p) - 90)   # 0° = north = up
        # heading triangle, 7 px
        tip = (x + 7 * math.cos(nose), y + 7 * math.sin(nose))
        l = (x + 4 * math.cos(nose + 2.5), y + 4 * math.sin(nose + 2.5))
        rgt = (x + 4 * math.cos(nose - 2.5), y + 4 * math.sin(nose - 2.5))
        d.polygon([tip, l, rgt], fill=COL_AIRCRAFT)
        # speed vector: 60 s of travel along track
        gs = gs_knots(p)
        if gs > 0:
            km_min = gs * KM_PER_NM / 60.0
            L = LAYOUTS[self.layout]
            vec_px = km_min * (L["r"] / self.outer_km)
            tr = math.radians(track_deg(p) - 90)
            ex, ey = x + vec_px * math.cos(tr), y + vec_px * math.sin(tr)
            # clip at the outer ring (reference behaviour): walk the endpoint
            # back along the vector until it is inside the disc
            cx, cy, r = L["cx"], L["cy"], L["r"]
            de = math.hypot(ex - cx, ey - cy)
            if de > r:
                # binary clip along the segment (x,y)->(ex,ey)
                lo, hi = 0.0, 1.0
                for _ in range(12):
                    mid = (lo + hi) / 2
                    mx_, my_ = x + (ex - x) * mid, y + (ey - y) * mid
                    if math.hypot(mx_ - cx, my_ - cy) > r:
                        hi = mid
                    else:
                        lo = mid
                ex, ey = x + (ex - x) * lo, y + (ey - y) * lo
            d.line([x, y, ex, ey], fill=COL_VECTOR)

    def _tag(self, d, x, y, p, cx, occupied):
        # (text, colour) pairs in fixed callsign/type/alt order — matches the
        # reference's 3-colour tag scheme (kColorLabel/kColorTagType/kColorTagAltitude).
        fields = [(callsign(p), COL_TAG_CALLSIGN), (p.get("t") or "", COL_TAG_TYPE),
                  (alt_tag(p), COL_TAG_ALT)]
        fields = [(t, c) for t, c in fields if t]
        lines = [t for t, _ in fields]
        w = max((len(t) for t in lines), default=0) * 6
        h = len(lines) * 8
        tx = x + 9 if x < cx else x - 9 - w   # centre-side placement (reference rule)
        ty = y - h // 2
        rect = [tx, ty, tx + w, ty + h]

        def overlaps(rc):
            return any(not (rc[2] < o[0] or rc[0] > o[2] or rc[3] < o[1] or rc[1] > o[3])
                       for o in occupied)

        if self.collision in ("b", "c") and overlaps(rect):
            for nudge in (10, -10, 20, -20):   # vertical nudge (rule b)
                rc = [rect[0], rect[1] + nudge, rect[2], rect[3] + nudge]
                if not overlaps(rc):
                    rect = rc
                    ty += nudge
                    break
            else:
                if self.collision == "c":      # rule c: drop tag, keep symbol
                    return
        occupied.append(rect)
        for i, (t, col) in enumerate(fields):
            F1.draw(d, int(rect[0]), int(ty + i * 8), t, col)

    def _strip(self, d, n_shown):
        sx = LAYOUTS["strip"]["strip_x"]
        d.rectangle([sx, 0, pc.APP_W - 1, pc.SCREEN_H - 1], fill=COL_STRIP_BG)
        d.line([sx, 0, sx, pc.SCREEN_H - 1], fill=COL_RING)
        F1.draw_centered(d, sx + 17, 12, f"{self.preset_km}", COL_STRIP_TX)
        F1.draw_centered(d, sx + 17, 22, "km", COL_STRIP_TX)
        F1.draw_centered(d, sx + 17, 50, f"{n_shown}ac", COL_STRIP_TX)
        # Q3: N^ bezel marker removed outright (not relocated) — the freed
        # y55..185 band now holds the location-slot rows.
        self._location_slots(d, sx)
        age = int(self.last_fetch_age)
        F1.draw_centered(d, sx + 17, 200, f"{age}s",
                         COL_STALE if age > 30 else COL_STRIP_TX)
        if self.http_err:
            F1.draw_centered(d, sx + 17, 220, f"E{self.http_err}", COL_ERR)

    def _location_slots(self, d, sx):
        """M-PR-LOCATIONS strip switcher (TASK-316). Up to
        PR_PREVIEW_SLOT_COUNT rows, 5-char labels, centered at the same
        strip label x as every other strip field (sx+17). Empty slots
        (falsy entry) draw nothing — including the degenerate 1-slot case,
        where rows 2-4 are simply absent, not placeholders."""
        label_x = sx + 17
        for i, label in enumerate(self.slots[:PR_PREVIEW_SLOT_COUNT]):
            if not label:
                continue
            y = PR_PREVIEW_SLOT_Y0 + i * PR_PREVIEW_SLOT_PITCH
            text = label[:5]
            is_active = (i == self.active_slot)
            if self.highlight == "box":
                if is_active:
                    # (a) inverse box: filled rect behind the label,
                    # field-coloured text. Rect spans the strip's usable
                    # width (34 px — strip W35 minus the x=sx border line).
                    x0, x1 = sx + 1, pc.APP_W - 1
                    y0, y1 = y - 5, y + 4
                    d.rectangle([x0, y0, x1, y1], fill=COL_STRIP_TX)
                    F1.draw_centered(d, label_x, y, text, COL_FIELD)
                else:
                    F1.draw_centered(d, label_x, y, text, COL_STRIP_TX)
            else:
                # (b) colour emphasis: bright STRIP_TX for active, dimmed
                # grey for inactive, plus a left-edge marker bar on the
                # active row.
                if is_active:
                    d.rectangle([sx + 1, y - 5, sx + 3, y + 4], fill=COL_STRIP_TX)
                    F1.draw_centered(d, label_x, y, text, COL_STRIP_TX)
                else:
                    F1.draw_centered(d, label_x, y, text, COL_STRIP_DIM)


# ── headless screenshot mode (design-doc evidence without a display) ───────────
def shot_mode(argv: list[str]) -> None:
    """--shot [fixture|synthetic] — render every layout × collision-rule combo
    to docs/architecture/designs/M-PLANERADAR/img/ as PNG at 2×. Headless."""
    src = argv[0] if argv else "busy_33km"
    radar = Radar()
    IMG_OUT.mkdir(parents=True, exist_ok=True)
    if src == "synthetic":
        planes = synthetic_frame(40.0)
    else:
        path = next((p for p in FIXTURES if p.stem == src), None)
        if path is None:
            sys.exit(f"no fixture {src}; have {[p.stem for p in FIXTURES]}")
        planes = load_fixture(path)
    for layout in LAYOUTS:
        for coll in ("a", "b", "c"):
            radar.layout, radar.collision = layout, coll
            img = radar.draw(planes).resize((pc.SCREEN_W * 2, pc.SCREEN_H * 2),
                                            Image.NEAREST)
            out = IMG_OUT / f"q1_{layout}_coll-{coll}_{src}_{radar.preset_km}km.png"
            img.save(out)
            print("wrote", out)
    # Q3 rim-dot comparison on the strip layout
    radar.layout, radar.collision = "strip", "b"
    for rim in ("disc-rim", "canvas-edge"):
        radar.rim_mode = rim
        img = radar.draw(planes).resize((pc.SCREEN_W * 2, pc.SCREEN_H * 2),
                                        Image.NEAREST)
        out = IMG_OUT / f"q3_{rim}_{src}.png"
        img.save(out)
        print("wrote", out)
    radar.rim_mode = "disc-rim"

    # Q4 runway label density, strip layout, all presets that put EHAM in
    # range (5/10/15/25 km all qualify — EHAM sits ~5.4 km from the home
    # default) — render at 25 km (worst case: largest on-screen scale change)
    radar.preset_i = PRESETS_KM.index(25)
    for density in ("all", "nearest", "off"):
        radar.runway_density = density
        img = radar.draw(planes).resize((pc.SCREEN_W * 2, pc.SCREEN_H * 2),
                                        Image.NEAREST)
        out = IMG_OUT / f"q4_{density}_{src}_{radar.preset_km}km.png"
        img.save(out)
        print("wrote", out)
    radar.runway_density = "all"

    # M-PR-LOCATIONS (TASK-316): location-slot strip eyeball gate. Strip
    # layout only (the slot band has no on-disc analogue); busy fixture at
    # 10 km, same representative scene the strip layout was originally
    # frozen against in phase0-preview-ui.md (q1_strip_coll-*_busy_33km_10km).
    radar.layout, radar.collision = "strip", "b"
    radar.preset_i = PRESETS_KM.index(10)
    PRLOC_IMG_OUT.mkdir(parents=True, exist_ok=True)

    def _prloc_shot(name, slots, active_slot, highlight):
        radar.slots = slots
        radar.active_slot = active_slot
        radar.highlight = highlight
        img = radar.draw(planes).resize((pc.SCREEN_W * 2, pc.SCREEN_H * 2),
                                        Image.NEAREST)
        out = PRLOC_IMG_OUT / name
        img.save(out)
        print("wrote", out)

    # 4 filled slots, both highlight variants (Q: box vs colour emphasis —
    # this is the decision the eyeball gate exists to make).
    _prloc_shot("strip_4slots_highlight-box.png",
                ["HOME", "WORK", "CABIN", "AIRPT"], 1, "box")
    _prloc_shot("strip_4slots_highlight-colour.png",
                ["HOME", "WORK", "CABIN", "AIRPT"], 1, "colour")
    # Empty-slot case: slots 3-4 empty, nothing drawn for them.
    _prloc_shot("strip_2slots.png", ["HOME", "WORK", None, None], 0, "box")
    # Single-slot degenerate case (always active, no marker collision).
    _prloc_shot("strip_1slot.png", ["HOME", None, None, None], 0, "box")

    # restore defaults for anything appended after shot_mode returns
    radar.slots = ["HOME", "WORK", "CABIN", "AIRPT"]
    radar.active_slot = 0
    radar.highlight = "box"


# ── main loop ──────────────────────────────────────────────────────────────────
def main():
    import pygame
    radar = Radar()
    win = pc.PreviewWindow("planeradar preview", scale=2)
    fix_i = 0
    mode = "fixture"           # fixture | synthetic | live
    syn_t = 0.0
    planes = load_fixture(FIXTURES[fix_i]) if FIXTURES else []
    last_live = 0.0
    gif_frames = None
    IMG_OUT.mkdir(parents=True, exist_ok=True)
    print(__doc__)
    print(f"fixtures: {[p.name for p in FIXTURES]}")

    clock = pygame.time.Clock()
    fetch_t0 = time.time()
    while True:
        for ev in pygame.event.get():
            if win.handle_event(ev):
                continue
            if ev.type == pygame.KEYDOWN:
                k = ev.key
                if k == pygame.K_l and (ev.mod & pygame.KMOD_SHIFT) == 0:
                    radar.layout = "disc" if radar.layout == "strip" else "strip"
                elif k == pygame.K_l:
                    mode = "live"
                elif k == pygame.K_c:
                    radar.collision = {"a": "b", "b": "c", "c": "a"}[radar.collision]
                elif k == pygame.K_r:
                    radar.rim_mode = ("canvas-edge" if radar.rim_mode == "disc-rim"
                                      else "disc-rim")
                elif k == pygame.K_a:
                    radar.runway_density = {"all": "nearest", "nearest": "off",
                                             "off": "all"}[radar.runway_density]
                elif k == pygame.K_h:
                    radar.highlight = "colour" if radar.highlight == "box" else "box"
                elif k == pygame.K_f and FIXTURES:
                    step = -1 if (ev.mod & pygame.KMOD_SHIFT) else 1
                    fix_i = (fix_i + step) % len(FIXTURES)
                    mode = "fixture"
                    planes = load_fixture(FIXTURES[fix_i])
                    fetch_t0 = time.time()
                elif k == pygame.K_s:
                    mode = "synthetic" if mode != "synthetic" else "fixture"
                    syn_t = 0.0
                elif k == pygame.K_SPACE:
                    syn_t += 5.0
                elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    win.scale = k - pygame.K_0
                elif k == pygame.K_p:
                    name = (f"{radar.layout}_{mode}_"
                            f"{FIXTURES[fix_i].stem if mode=='fixture' and FIXTURES else mode}"
                            f"_{radar.preset_km}km.png")
                    img.save(IMG_OUT / name)
                    print("saved", IMG_OUT / name)
                elif k == pygame.K_g:
                    gif_frames = []
                    print("recording 100 frames...")
            if ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                mx //= win.scale
                my //= win.scale
                L = LAYOUTS[radar.layout]
                if math.hypot(mx - L["cx"], my - L["cy"]) <= L["r"]:
                    radar.preset_i = (radar.preset_i + 1) % len(PRESETS_KM)

        if mode == "synthetic":
            syn_t += 0.15
            planes = synthetic_frame(syn_t)
            radar.last_fetch_age = 0
        elif mode == "live" and time.time() - last_live > 10:
            import pr_adsb_probe as probe
            lat, lon = radar.center
            code, dt, nb, parsed, err = probe.fetch(
                lat, lon, radar.outer_km / KM_PER_NM)
            last_live = time.time()
            radar.http_err = 0 if code == 200 else code
            if parsed:
                planes = parsed.get("ac", []) or []
                fetch_t0 = time.time()
        if mode != "synthetic":
            radar.last_fetch_age = time.time() - fetch_t0

        img = radar.draw(planes)
        if gif_frames is not None:
            gif_frames.append(img.copy())
            if len(gif_frames) >= 100:
                pc.write_gif(gif_frames, IMG_OUT / f"anim_{radar.layout}.gif", fps=10)
                gif_frames = None
        win.blit_pil(img)
        win.flip()
        clock.tick(10)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--shot":
        shot_mode(sys.argv[2:])
    else:
        main()
