# preview_interp.py — pygame eyeball harness for the PROP-006 study.
#
# Renders the radar disc at 2x scale: ground truth (white) vs one
# reconstruction (green) with fading trails, fix moments flashed amber.
# The eyeball is the study's acceptance criterion — this window is the test.
#
# Keys:  a/z cycle algorithm   c/v cycle cadence   s cycle scenario
#        SPACE pause           q quit
#
# Headless (CI / screenshots for the EXP report):
#   SDL_VIDEODRIVER=dummy python3 preview_interp.py --headless out_dir --frames 40
# writes PNGs sampled across the run for every (algo, cadence) pair on the
# current scenario.

import argparse
import os

# Leave SDL_VIDEODRIVER alone: SDL autodetects wayland/x11 for the window;
# headless mode sets =dummy itself. (Setting it to "" breaks window creation.)
import pygame  # noqa: E402

from model import to_px, PRESETS_KM
from synth import default_scenarios, integrate, truth_at, sample_fixes
from algorithms import ladder
from score import CADENCES_S, FPS

SCALE = 2
W = H = 240 * SCALE
TRAIL = 600  # frames of trail (20 s at 30 fps — enough to see the path shape)


def draw_disc(surf):
    surf.fill((0, 0, 0))
    for r_frac in (0.25, 0.5, 0.75, 1.0):
        pygame.draw.circle(surf, (16, 50, 16), (120 * SCALE, 120 * SCALE),
                           int(118 * SCALE * r_frac), 1)


def run_replay(surf, states, fixes, algo, preset_km, t, trail_true, trail_algo):
    tr = truth_at(states, t)
    tpx = to_px(tr.x, tr.y, preset_km)
    trail_true.append(tpx)
    pos = algo.position(t)
    apx = to_px(pos[0], pos[1], preset_km) if pos else None
    trail_algo.append(apx)
    for trail, col in ((trail_true, (200, 200, 200)), (trail_algo, (40, 220, 60))):
        pts = [p for p in trail[-TRAIL:] if p]
        for i, p in enumerate(pts):
            a = int(40 + 215 * i / max(1, len(pts) - 1))
            c = tuple(min(255, ch * a // 255) for ch in col)
            pygame.draw.circle(surf, c, (int(p[0] * SCALE), int(p[1] * SCALE)), 1)
    pygame.draw.circle(surf, (255, 255, 255),
                       (int(tpx[0] * SCALE), int(tpx[1] * SCALE)), 3)
    if apx:
        pygame.draw.circle(surf, (40, 220, 60),
                           (int(apx[0] * SCALE), int(apx[1] * SCALE)), 3, 1)


def interactive(preset_km):
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    font = pygame.font.SysFont(None, 20)
    scenarios = default_scenarios(preset_km)
    si = ai = ci = 0
    clock = pygame.time.Clock()

    def setup():
        sc = scenarios[si]
        states = integrate(sc, 360)
        fixes = sample_fixes(states, CADENCES_S[ci])
        algos = ladder()
        return sc, states, fixes, algos

    sc, states, fixes, algos = setup()
    t, fi, paused = 0.0, 0, False
    trail_true, trail_algo = [], []
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_q:
                    return
                if ev.key == pygame.K_SPACE:
                    paused = not paused
                if ev.key in (pygame.K_a, pygame.K_z, pygame.K_c, pygame.K_v,
                              pygame.K_s):
                    if ev.key == pygame.K_a:
                        ai = (ai + 1) % len(algos)
                    if ev.key == pygame.K_z:
                        ai = (ai - 1) % len(algos)
                    if ev.key == pygame.K_c:
                        ci = (ci + 1) % len(CADENCES_S)
                    if ev.key == pygame.K_v:
                        ci = (ci - 1) % len(CADENCES_S)
                    if ev.key == pygame.K_s:
                        si = (si + 1) % len(scenarios)
                    sc, states, fixes, algos = setup()
                    t, fi = 0.0, 0
                    trail_true, trail_algo = [], []
        if not paused:
            t += 1 / FPS
            if t >= states[-1].t:
                t, fi = 0.0, 0
                algos = ladder()
                trail_true, trail_algo = [], []
            while fi < len(fixes) and fixes[fi].t <= t:
                algos[ai].update(fixes[fi])
                fi += 1
        draw_disc(screen)
        run_replay(screen, states, fixes, algos[ai], preset_km, t,
                   trail_true, trail_algo)
        label = f"{sc.name} | {algos[ai].name} | {CADENCES_S[ci]}s  (a/z c/v s)"
        screen.blit(font.render(label, True, (200, 200, 80)), (6, 4))
        pygame.display.flip()
        clock.tick(FPS)


def _surface_to_pil(surf):
    from PIL import Image
    return Image.frombytes("RGB", surf.get_size(),
                           pygame.image.tostring(surf, "RGB"))


def headless(out_dir, preset_km, n_frames, scenario_name, gif=False):
    """PNG stills (default) or animated GIFs (--gif, via preview_common's
    write_gif — M-PREVIEW-FRAMEWORK) for the EXP report."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    surf = pygame.Surface((W, H))
    os.makedirs(out_dir, exist_ok=True)
    if gif:
        import sys
        import pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
        from preview_common import write_gif
    scenarios = [s for s in default_scenarios(preset_km)
                 if scenario_name in (None, s.name)]
    for sc in scenarios:
        states = integrate(sc, 360)
        for cad in CADENCES_S:
            fixes = sample_fixes(states, cad)
            for algo in ladder():
                trail_true, trail_algo = [], []
                fi = 0
                total = int(states[-1].t * FPS)
                shots = 0
                gif_frames = []
                for n in range(total):
                    t = n / FPS
                    while fi < len(fixes) and fixes[fi].t <= t:
                        algo.update(fixes[fi])
                        fi += 1
                    draw_disc(surf)
                    run_replay(surf, states, fixes, algo, preset_km, t,
                               trail_true, trail_algo)
                    safe = algo.name.replace("(", "_").replace(")", "").replace("=", "")
                    if gif and n % 3 == 0:            # 10 fps GIF
                        gif_frames.append(_surface_to_pil(surf))
                    elif not gif and n % max(1, total // n_frames) == 0:
                        shots += 1
                        pygame.image.save(
                            surf, os.path.join(
                                out_dir, f"{sc.name}_{cad}s_{safe}_{shots:03d}.png"))
                if gif:
                    write_gif(gif_frames,
                              os.path.join(out_dir, f"{sc.name}_{cad}s_{safe}.gif"),
                              fps=10)
                else:
                    print(f"[headless] {sc.name} {cad}s {algo.name}: {shots} frames")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", type=int, default=10, choices=PRESETS_KM)
    ap.add_argument("--headless", metavar="OUT_DIR")
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--gif", action="store_true",
                    help="headless: write animated GIFs instead of PNG stills")
    ap.add_argument("--scenario", default=None)
    a = ap.parse_args()
    if a.headless:
        headless(a.headless, a.preset, a.frames, a.scenario, gif=a.gif)
    else:
        interactive(a.preset)
