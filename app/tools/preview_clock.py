#!/usr/bin/env python3
"""preview_clock.py — interactive concept tool for M-CLOCK-STYLES.

Renders all four ClockApp styles on the device canvas (275×240) in a scaled
pygame window. Use keyboard shortcuts to switch styles and tune parameters
before any firmware is written.  Approved parameters are printed with 'p'
and saved to gen/clock_concepts/ with 'S'.

Usage:
    python3 app/tools/preview_clock.py
    python3 app/tools/preview_clock.py --style flip
    python3 app/tools/preview_clock.py --freeze 12:34:45
    python3 app/tools/preview_clock.py --scale 3

Keyboard (global):
    1 / 2 / 3 / 4   switch style  (1=Digital  2=Flip  3=Nixie  4=VFD)
    p               print current params dict  (paste into design doc)
    S               save screenshot → gen/clock_concepts/<style>_<ts>.png
    + / -           scale up / down  (1–4)
    q               quit

Style-specific keys are printed when you switch to that style.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time as _time
from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ── geometry (mirrors firmware) ───────────────────────────────────────────────

SCREEN_W  = 320
SCREEN_H  = 240
TASKBAR_X = 275
TASKBAR_W = 45
APP_W     = 275
APP_H     = 240
CENTRE_X  = 137   # horizontal centre of app canvas

# Standard Digital clock layout  (all styles may deviate)
TIME_BOX_Y  =   5;  TIME_BOX_H  =  80;  TIME_CY    =  45
SEC_BOX_Y   =  88;  SEC_BOX_H   =  47
SEC_BAR_Y   = 100;  SEC_BAR_H   =  25
DATE_BOX_Y  = 138;  DATE_BOX_H  =  97
DATE_DAY_Y  = 170;  DATE_DATE_Y = 200

# ── colour helpers ────────────────────────────────────────────────────────────

def rainbow_color(i: int, total: int = 60) -> tuple[int, int, int]:
    """RGB for seconds-bar segment i  (mirrors firmware hue formula)."""
    h = int(i * 255 / total)
    if h < 85:
        return (255 - h * 3, h * 3, 0)
    elif h < 170:
        h -= 85; return (0, 255 - h * 3, h * 3)
    else:
        h -= 170; return (h * 3, 0, 255 - h * 3)

# ── font helpers ──────────────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSansMono-ExtraBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]

def find_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)

# ── base renderer ─────────────────────────────────────────────────────────────

class ClockRenderer(ABC):
    CANVAS_W = APP_W
    CANVAS_H = APP_H

    def help_text(self) -> str:
        """One-line description of style-specific keys (printed on switch)."""
        return "(no style-specific keys)"

    @abstractmethod
    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        """Full 275×240 canvas render — must fill own background."""
        ...

    @abstractmethod
    def on_key(self, key: str) -> bool:
        """Handle a style-specific keypress.  Return True if redraw needed."""
        ...

    @abstractmethod
    def param_dict(self) -> dict:
        """Current tunable parameters (for p-key output and design doc)."""
        ...

# ── Digital renderer — demonstrates the fixed-position MM fix ────────────────

class DigitalRenderer(ClockRenderer):
    """Firmware Digital style with the MM-jump bug fixed.

    HH and MM are drawn at absolute x anchors so the colon blink never
    shifts the minute digits left/right (the firmware bug this milestone fixes).
    """

    def __init__(self):
        self._font_time = find_font(48)
        self._font_date = find_font(22)

    def help_text(self) -> str:
        return "(no style keys — demonstrating fixed-position MM)"

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, APP_W - 1, APP_H - 1], fill=(0, 0, 0))

        # chrome boxes
        draw.rounded_rectangle([5,   5, 270,  85], radius=10, outline=(255, 0, 255),   width=2)
        draw.rounded_rectangle([5,  88, 270, 135], radius=10, outline=(0, 255, 255),   width=2)
        draw.rounded_rectangle([5, 138, 270, 235], radius=10, outline=(255, 255, 0),   width=2)

        # fixed-position HH / colon / MM  ← the fix
        hh = f"{t.tm_hour:02d}"
        mm = f"{t.tm_min:02d}"
        show_colon = (t.tm_sec % 2 == 0)

        col_w = draw.textlength(":", font=self._font_time)
        hh_w  = draw.textlength(hh,  font=self._font_time)
        bb    = draw.textbbox((0, 0), "0", font=self._font_time)
        ch    = bb[3] - bb[1]

        hh_x = CENTRE_X - col_w / 2 - hh_w
        col_x = CENTRE_X - col_w / 2
        mm_x  = CENTRE_X + col_w / 2
        ty    = TIME_CY - ch // 2

        draw.text((hh_x, ty), hh, font=self._font_time, fill=(255, 255, 255))
        draw.text((mm_x, ty), mm, font=self._font_time, fill=(255, 255, 255))
        if show_colon:
            draw.text((col_x, ty), ":", font=self._font_time, fill=(255, 255, 255))

        # seconds bar
        for i in range(60):
            x = 8 + int(i * 4.3)
            c = rainbow_color(i) if i < t.tm_sec else (0, 80, 80)
            draw.rectangle([x, SEC_BAR_Y, x + 1, SEC_BAR_Y + SEC_BAR_H - 1], fill=c)

        # date
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        draw.text((CENTRE_X, DATE_DAY_Y), days[t.tm_wday],
                  font=self._font_date, fill=(255, 255, 255), anchor="mm")
        ds = f"{t.tm_mday:02d}/{t.tm_mon + 1:02d}/{t.tm_year + 1900}"
        draw.text((CENTRE_X, DATE_DATE_Y), ds,
                  font=self._font_date, fill=(255, 255, 255), anchor="mm")

    def on_key(self, key: str) -> bool:
        return False

    def param_dict(self) -> dict:
        return {"style": "digital"}

# ── Taskbar stub ──────────────────────────────────────────────────────────────

_TASKBAR_LABELS = list("SCWM$MG=K~")   # rough slot labels (S=Spotify, C=Clock …)
_TASKBAR_LABEL  = ["S", "C", "W", "$", "M", "G"]

def _draw_taskbar(img: Image.Image, active_slot: int) -> None:
    draw   = ImageDraw.Draw(img)
    SLOT_H = 40
    font   = find_font(13)
    draw.rectangle([TASKBAR_X, 0, SCREEN_W - 1, SCREEN_H - 1], fill=(10, 10, 22))
    for i, lbl in enumerate(_TASKBAR_LABEL):
        y0 = i * SLOT_H
        y1 = y0 + SLOT_H - 1
        if i == active_slot:
            draw.rectangle([TASKBAR_X, y0, SCREEN_W - 1, y1], fill=(28, 28, 55))
            draw.rectangle([TASKBAR_X, y0, TASKBAR_X + 2, y1], fill=(0, 200, 255))
        cx = TASKBAR_X + TASKBAR_W // 2
        cy = y0 + SLOT_H // 2
        draw.text((cx, cy), lbl, font=font,
                  fill=(220, 220, 220) if i == active_slot else (120, 120, 140),
                  anchor="mm")
        if i < len(_TASKBAR_LABEL) - 1:
            draw.line([TASKBAR_X, y1 + 1, SCREEN_W - 1, y1 + 1], fill=(28, 28, 50))

# ── renderer registry ─────────────────────────────────────────────────────────

STYLE_NAMES = {1: "Digital", 2: "Flip", 3: "Nixie", 4: "VFD"}
STYLE_KEYS  = {"digital": 1, "flip": 2, "nixie": 3, "vfd": 4}

def _load_renderers() -> dict[int, ClockRenderer]:
    renderers: dict[int, ClockRenderer] = {1: DigitalRenderer()}
    _tools = str(pathlib.Path(__file__).parent)
    if _tools not in sys.path:
        sys.path.insert(0, _tools)

    for key, name, mod_name, cls_name in [
        (2, "Flip",  "_clock_flip",  "FlipRenderer"),
        (3, "Nixie", "_clock_nixie", "NixieRenderer"),
        (4, "VFD",   "_clock_vfd",   "VFDRenderer"),
    ]:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            renderers[key] = getattr(mod, cls_name)()
        except (ImportError, AttributeError, Exception) as exc:
            print(f"[preview_clock] {name} renderer unavailable: {exc}")

    return renderers

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Clock style concept preview")
    ap.add_argument("--style",      default="digital",
                    choices=list(STYLE_KEYS), help="Starting style")
    ap.add_argument("--freeze",     metavar="HH:MM:SS",
                    help="Freeze fake time  e.g. 12:34:00")
    ap.add_argument("--scale",      type=int, default=3, choices=[1,2,3,4],
                    help="Display scale factor (default 3 → 960×720 window)")
    ap.add_argument("--screenshot", metavar="DIR", default="gen/clock_concepts",
                    help="Directory for S-key screenshots")
    args = ap.parse_args()

    style_key = STYLE_KEYS[args.style]

    frozen: Optional[_time.struct_time] = None
    if args.freeze:
        parts = [int(x) for x in args.freeze.split(":")]
        base  = list(_time.localtime())
        if len(parts) > 0: base[3] = parts[0]
        if len(parts) > 1: base[4] = parts[1]
        if len(parts) > 2: base[5] = parts[2]
        frozen = _time.struct_time(base)

    screenshot_dir = pathlib.Path(args.screenshot)

    try:
        import pygame
    except ImportError:
        sys.exit("pip install pygame  (required for interactive preview)")

    renderers = _load_renderers()
    renderer  = renderers.get(style_key, renderers[1])

    pygame.init()
    pygame.display.set_caption(f"preview_clock — {STYLE_NAMES[style_key]}")
    scale  = args.scale
    screen = pygame.display.set_mode((SCREEN_W * scale, SCREEN_H * scale))
    clock  = pygame.time.Clock()

    print(__doc__)
    print(f"Loaded styles: {[STYLE_NAMES[k] for k in sorted(renderers)]}")
    print(f"Style-specific keys: {renderer.help_text()}")

    while True:
        t_now = frozen or _time.localtime()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); return

            elif event.type == pygame.KEYDOWN:
                k = event.key

                if k == pygame.K_q:
                    pygame.quit(); return

                elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    scale = min(4, scale + 1)
                    screen = pygame.display.set_mode((SCREEN_W*scale, SCREEN_H*scale))

                elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    scale = max(1, scale - 1)
                    screen = pygame.display.set_mode((SCREEN_W*scale, SCREEN_H*scale))

                elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    new_key = k - pygame.K_0
                    if new_key in renderers:
                        style_key = new_key
                        renderer  = renderers[style_key]
                        pygame.display.set_caption(f"preview_clock — {STYLE_NAMES[style_key]}")
                        print(f"\n[style] {STYLE_NAMES[style_key]}  "
                              f"keys: {renderer.help_text()}")

                elif k == pygame.K_p:
                    import pprint
                    d = renderer.param_dict()
                    d["style"] = STYLE_NAMES.get(style_key, "?")
                    print("\n── params ──"); pprint.pprint(d); print("────────────")

                elif k == pygame.K_s:
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    ts    = _time.strftime("%Y%m%d_%H%M%S")
                    name  = f"{STYLE_NAMES.get(style_key,'?').lower()}_{ts}.png"
                    fpath = screenshot_dir / name
                    img   = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
                    renderer.render(img, t_now)
                    _draw_taskbar(img, active_slot=style_key - 1)
                    img.save(fpath)
                    print(f"[screenshot] {fpath}")

                else:
                    renderer.on_key(pygame.key.name(k))

        # render
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        renderer.render(img, t_now)
        _draw_taskbar(img, active_slot=style_key - 1)

        surf = pygame.image.fromstring(img.tobytes(), img.size, "RGB")
        if scale > 1:
            surf = pygame.transform.scale(surf, (SCREEN_W * scale, SCREEN_H * scale))
        screen.blit(surf, (0, 0))
        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
