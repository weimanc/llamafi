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

import sys as _sys
import pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).parent))
import dut_fonts as _dut_fonts

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
    """System TrueType fallback — used for taskbar labels only."""
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

    Uses exact TFT_eSPI bitmap fonts parsed from the library source:
      Font6 (48px) for HH:MM — same as setTextFont(6) on DUT
      Font4 (26px) for day/date — same as setTextFont(4) on DUT

    Positions mirror firmware exactly:
      HH  MR_DATUM at (129, 45)   colon MC_DATUM at (137, 45)   MM ML_DATUM at (145, 45)
      day MC_DATUM at (137, 170)  date  MC_DATUM at (137, 200)
    """

    def __init__(self):
        self._font_time = _dut_fonts.Font6()
        self._font_date = _dut_fonts.Font4()

    def help_text(self) -> str:
        return "(no style keys — demonstrating fixed-position MM)"

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, APP_W - 1, APP_H - 1], fill=(0, 0, 0))

        # chrome boxes
        draw.rounded_rectangle([5,   5, 270,  85], radius=10, outline=(255, 0, 255),   width=2)
        draw.rounded_rectangle([5,  88, 270, 135], radius=10, outline=(0, 255, 255),   width=2)
        draw.rounded_rectangle([5, 138, 270, 235], radius=10, outline=(255, 255, 0),   width=2)

        # HH / colon / MM — exact firmware anchors: MR@129, MC@137, ML@145, cy=45
        hh = f"{t.tm_hour:02d}"
        mm = f"{t.tm_min:02d}"
        show_colon = (t.tm_sec % 2 == 0)

        self._font_time.draw_right(draw, 129, TIME_CY, hh,  fg=(255, 255, 255))
        self._font_time.draw_left( draw, 145, TIME_CY, mm,  fg=(255, 255, 255))
        if show_colon:
            self._font_time.draw_centered(draw, 137, TIME_CY, ":", fg=(255, 255, 255))

        # seconds bar
        for i in range(60):
            x = 8 + int(i * 4.3)
            c = rainbow_color(i) if i < t.tm_sec else (0, 80, 80)
            draw.rectangle([x, SEC_BAR_Y, x + 1, SEC_BAR_Y + SEC_BAR_H - 1], fill=c)

        # day / date — MC_DATUM at (137, 170) and (137, 200)
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        self._font_date.draw_centered(draw, 137, DATE_DAY_Y,  days[t.tm_wday], fg=(255, 255, 255))
        ds = f"{t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year}"
        self._font_date.draw_centered(draw, 137, DATE_DATE_Y, ds,              fg=(255, 255, 255))

    def on_key(self, key: str) -> bool:
        return False

    def param_dict(self) -> dict:
        return {"style": "digital"}

# ── Taskbar stub ──────────────────────────────────────────────────────────────

# App order matches appRegistry.h: Spotify(0) Clock(1) Weather(2) Crypto(3) Matrix(4) Life(5)
# Settings(6) Stock(7) Aquarium(8). Taskbar shows first 6 slots (TASKBAR_SLOT_COUNT=6).
_ICONS_DIR = pathlib.Path(__file__).parent.parent / "icons" / "taskbar"
_APP_NAMES  = ["spotify", "clock", "weather", "crypto", "matrix", "life",
               "settings", "stock", "aquarium"]
_TASKBAR_SLOT_COUNT = 6
_TASKBAR_SLOT_H     = 40
_TASKBAR_ICON_W     = 24
_TASKBAR_ICON_H     = 24
_TASKBAR_BG         = (32, 32, 32)   # 0x2104 RGB565 → ~(32,32,32)
_TASKBAR_ACTIVE_COL = (0, 255, 0)   # 0x07E0 = green
_TASKBAR_SEP_COL    = (64, 64, 64)  # 0x4208 RGB565 → ~(64,64,64)


def _load_icon(name: str, active: bool) -> Optional[Image.Image]:
    suffix = "_active" if active else ""
    path   = _ICONS_DIR / f"{name}{suffix}.png"
    if not path.exists():
        return None
    ico = Image.open(path).convert("RGBA")
    if ico.size != (_TASKBAR_ICON_W, _TASKBAR_ICON_H):
        ico = ico.resize((_TASKBAR_ICON_W, _TASKBAR_ICON_H), Image.LANCZOS)
    return ico


def _draw_taskbar(img: Image.Image, active_slot: int,
                  scroll_offset: int = 0) -> None:
    draw = ImageDraw.Draw(img)
    draw.rectangle([TASKBAR_X, 0, SCREEN_W - 1, SCREEN_H - 1], fill=_TASKBAR_BG)

    icon_off_x = (TASKBAR_W - _TASKBAR_ICON_W) // 2
    icon_off_y = (_TASKBAR_SLOT_H - _TASKBAR_ICON_H) // 2

    for i in range(_TASKBAR_SLOT_COUNT):
        app_idx = (scroll_offset + i) % len(_APP_NAMES)
        y0      = i * _TASKBAR_SLOT_H
        y1      = y0 + _TASKBAR_SLOT_H - 1
        is_active = (app_idx == active_slot)

        # separator line
        if i < _TASKBAR_SLOT_COUNT - 1:
            draw.line([TASKBAR_X, y1 + 1, SCREEN_W - 1, y1 + 1], fill=_TASKBAR_SEP_COL)

        # icon
        ico = _load_icon(_APP_NAMES[app_idx], is_active)
        if ico:
            img.paste(ico, (TASKBAR_X + icon_off_x, y0 + icon_off_y), mask=ico)

        # active indicator: 3px green bar on left edge
        if is_active:
            draw.rectangle([TASKBAR_X, y0, TASKBAR_X + 2, y1], fill=_TASKBAR_ACTIVE_COL)

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
