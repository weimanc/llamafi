# preview_interp.py — PROP-006 eyeball harness on the REAL radar renderer.
#
# Reuses preview_planeradar.Radar for the device-faithful frame (palette,
# rings, aircraft glyph + clipped speed vector, tags) and
# preview_common.PreviewWindow for windowing (+/- scale, q quit) — the study
# only adds the reconstruction overlays.
#
# All five scenario aircraft fly simultaneously; every enabled algorithm's
# estimate is overlaid as a coloured trail + ring on each aircraft, so
# algorithms are compared on the same planes in the same frame.
#
# Keys:
#   1..6      toggle algorithms (see legend; default: snap, damped(2), lerp)
#   c / v     poll cadence up / down (1/5/10/15/30 s)
#   s         solo plane cycle (all -> cruise -> turn -> ... -> all)
#   SPACE     pause      r  restart      +/-  scale      q  quit
#
# Headless (report artifacts):
#   python3 preview_interp.py --headless out_dir [--gif] [--scenario turn]

import argparse
import math
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))  # app/tools

from PIL import ImageDraw

from synth import default_scenarios, integrate, truth_at, sample_fixes
from algorithms import ladder
from score import CADENCES_S, FPS

FPS_GIF = 10
TRAIL = 600            # frames of trail (20 s at 30 fps)

# Per-algo overlay colours (ladder order: snap, damped1, damped2, damped4,
# lerp, catmull). Truth uses the device's own white glyph.
ALGO_COLS = [(230, 70, 70), (240, 160, 60), (70, 220, 70),
             (70, 200, 200), (225, 225, 70), (200, 110, 220)]
DEFAULT_ON = {0, 2, 4}
TRUTH_TRAIL_COL = (110, 110, 110)


def _radar(preset_km):
    """Device-faithful Radar from preview_planeradar, configured for study."""
    from preview_planeradar import Radar, PRESETS_KM as RADAR_PRESETS
    r = Radar()
    r.layout = "disc"
    r.runway_density = "off"
    r.preset_i = RADAR_PRESETS.index(preset_km)
    return r


def _enu_to_latlon(radar, x_m, y_m):
    lat0, lon0 = radar.center
    lat = lat0 + (y_m / 1000.0) / 110.574
    lon = lon0 + (x_m / 1000.0) / (111.320 * math.cos(math.radians(lat0)))
    return lat, lon


def _enu_to_px(radar, x_m, y_m):
    """Same mapping Radar.project uses: outer ring (r px) = preset*4/3 km."""
    from preview_planeradar import LAYOUTS
    L = LAYOUTS[radar.layout]
    s = L["r"] / (radar.outer_km * 1000.0)
    return L["cx"] + x_m * s, L["cy"] - y_m * s


class Sim:
    """All scenarios flying at once; per-(plane, algo) reconstruction state.

    Trails accumulate in step() (not render()) so they are complete even when
    frames are sampled sparsely (headless PNG/GIF modes)."""

    def __init__(self, preset_km, cadence_s, radar, duration_s=360):
        self.radar = radar
        self.preset_km = preset_km
        self.cadence = cadence_s
        self.scenarios = default_scenarios(preset_km)
        self.states = [integrate(sc, duration_s) for sc in self.scenarios]
        self.fixes = [sample_fixes(st, cadence_s, seed=17 + i)
                      for i, st in enumerate(self.states)]
        self.algos = [ladder() for _ in self.scenarios]   # per plane
        self.fi = [0] * len(self.scenarios)
        self.trails_true = [[] for _ in self.scenarios]
        self.trails = [[[] for _ in self.algos[0]] for _ in self.scenarios]
        self.t = 0.0
        self.end = min(st[-1].t for st in self.states)

    def step(self, dt):
        self.t += dt
        if self.t >= self.end:
            return False
        for p in range(len(self.scenarios)):
            while (self.fi[p] < len(self.fixes[p])
                   and self.fixes[p][self.fi[p]].t <= self.t):
                fx = self.fixes[p][self.fi[p]]
                for a in self.algos[p]:
                    a.update(fx)
                self.fi[p] += 1
        for p in range(len(self.scenarios)):
            tr = truth_at(self.states[p], self.t)
            self.trails_true[p].append(_enu_to_px(self.radar, tr.x, tr.y))
            for ai, algo in enumerate(self.algos[p]):
                pos = algo.position(self.t)
                self.trails[p][ai].append(
                    _enu_to_px(self.radar, pos[0], pos[1]) if pos else None)
        return True

    def render(self, radar, enabled, solo=None, hud=""):
        """One PIL frame: real radar chrome + truth planes + algo overlays."""
        planes = []
        idxs = range(len(self.scenarios)) if solo is None else [solo]
        for p in idxs:
            tr = truth_at(self.states[p], self.t)
            lat, lon = _enu_to_latlon(radar, tr.x, tr.y)
            planes.append({"hex": self.scenarios[p].name,
                           "flight": self.scenarios[p].name.upper()[:7],
                           "lat": lat, "lon": lon,
                           "track": tr.track_deg, "nose": tr.track_deg,
                           "gs": tr.gs_ms / 0.514444, "alt_baro": 10000})
        img = radar.draw(planes)
        d = ImageDraw.Draw(img)
        for p in idxs:
            for pt in self.trails_true[p][-TRAIL::4]:
                d.point(pt, fill=TRUTH_TRAIL_COL)
            for ai in enabled:
                col = ALGO_COLS[ai]
                tr_a = self.trails[p][ai]
                for pt in tr_a[-TRAIL::2]:
                    if pt:
                        d.point(pt, fill=col)
                if tr_a and tr_a[-1]:
                    apx = tr_a[-1]
                    d.ellipse([apx[0] - 3, apx[1] - 3, apx[0] + 3, apx[1] + 3],
                              outline=col)
        # Legend + HUD (kept inside the 275 px app canvas, top-left).
        y = 2
        for ai, algo in enumerate(self.algos[0]):
            mark = "#" if ai in enabled else "-"
            d.text((3, y), f"{ai + 1}{mark} {algo.name}",
                   fill=ALGO_COLS[ai] if ai in enabled else (80, 80, 80))
            y += 10
        d.text((3, y + 2), hud, fill=(200, 200, 90))
        return img


KEY_HELP = """\
PROP-006 interpolation study — keys:
  1..6    toggle algorithms (legend top-left; # = on, default snap/damped2/lerp)
  c / v   poll cadence up / down (1/5/10/15/30 s)
  s       solo plane cycle (all -> cruise -> turn -> holding -> approach -> climbout -> all)
  SPACE   pause            r   restart run
  + / -   window scale     q   quit
White glyph+vector = ground truth; coloured trails/rings = reconstructions."""


def interactive(preset_km):
    import pygame
    from preview_common import PreviewWindow
    print(KEY_HELP)
    win = PreviewWindow("PROP-006 interpolation study", scale=3)
    radar = _radar(preset_km)
    ci = CADENCES_S.index(10)
    sim = Sim(preset_km, CADENCES_S[ci], radar)
    enabled = set(DEFAULT_ON)
    solo = None          # None = all planes; else scenario index
    paused = False
    clock = pygame.time.Clock()
    while True:
        for ev in pygame.event.get():
            if win.handle_event(ev):
                continue
            if ev.type == pygame.KEYDOWN:
                k = ev.key
                if pygame.K_1 <= k <= pygame.K_6:
                    ai = k - pygame.K_1
                    enabled ^= {ai}
                elif k == pygame.K_SPACE:
                    paused = not paused
                elif k in (pygame.K_c, pygame.K_v):
                    ci = (ci + (1 if k == pygame.K_c else -1)) % len(CADENCES_S)
                    sim = Sim(preset_km, CADENCES_S[ci], radar)
                elif k == pygame.K_s:
                    order = [None] + list(range(len(sim.scenarios)))
                    solo = order[(order.index(solo) + 1) % len(order)]
                elif k == pygame.K_r:
                    sim = Sim(preset_km, CADENCES_S[ci], radar)
        if not paused and not sim.step(1 / FPS):
            sim = Sim(preset_km, CADENCES_S[ci], radar)
        hud = (f"{CADENCES_S[ci]}s poll | "
               f"{'ALL' if solo is None else sim.scenarios[solo].name}"
               f"{' | PAUSED' if paused else ''}")
        win.blit_pil(sim.render(radar, enabled, solo, hud))
        win.flip()
        clock.tick(FPS)


def headless(out_dir, preset_km, n_frames, scenario_name, gif=False):
    os.makedirs(out_dir, exist_ok=True)
    radar = _radar(preset_km)
    names = [s.name for s in default_scenarios(preset_km)]
    solo = names.index(scenario_name) if scenario_name else None
    enabled = set(range(len(ALGO_COLS)))
    for cad in CADENCES_S:
        sim = Sim(preset_km, cad, radar, duration_s=180)
        frames = []
        n = 0
        while sim.step(1 / FPS):
            n += 1
            want_gif = gif and n % (FPS // FPS_GIF) == 0
            want_png = (not gif) and n % max(1, int(sim.end * FPS) // n_frames) == 0
            if want_gif or want_png:
                img = sim.render(radar, enabled, solo, f"{cad}s poll")
                if want_gif:
                    frames.append(img)
                else:
                    img.save(os.path.join(
                        out_dir, f"{scenario_name or 'all'}_{cad}s_{n:05d}.png"))
        if gif:
            from preview_common import write_gif
            write_gif(frames, os.path.join(
                out_dir, f"{scenario_name or 'all'}_{cad}s.gif"), fps=FPS_GIF)
        else:
            print(f"[headless] {cad}s: done")


if __name__ == "__main__":
    from model import PRESETS_KM
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", type=int, default=10, choices=PRESETS_KM)
    ap.add_argument("--headless", metavar="OUT_DIR")
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--gif", action="store_true")
    ap.add_argument("--scenario", default=None)
    a = ap.parse_args()
    if a.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        headless(a.headless, a.preset, a.frames, a.scenario, gif=a.gif)
    else:
        interactive(a.preset)
