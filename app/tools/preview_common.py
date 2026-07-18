"""preview_common.py — shared constants and helpers for preview_*.py tools.

Provides the canonical geometry constants, APP_ORDER (from app_ids_gen.py),
icon loaders, taskbar renderers (PIL + pygame flavours), GIF writer, and the
PreviewWindow pygame window wrapper.
"""
from __future__ import annotations

import pathlib
import sys

# ── geometry (mirrors firmware shell_layout.h) ────────────────────────────────

SCREEN_W  = 320
SCREEN_H  = 240
TASKBAR_X = 275
TASKBAR_W = 45
APP_W     = 275
APP_H     = 240

TASKBAR_SLOT_H     = 40
TASKBAR_SLOT_COUNT = 6
TASKBAR_ICON_W     = 36   # ADR-051 (was 24) — keep in sync with gen/shell_layout.h
TASKBAR_ICON_H     = 36   # ADR-051 (was 24)

TASKBAR_BG         = (32, 32, 32)    # 0x2104 RGB565
TASKBAR_ACTIVE_COL = (0, 255, 0)     # 0x07E0 RGB565 — green
TASKBAR_SEP_COL    = (64, 64, 64)    # 0x4208 RGB565

# ── APP_ORDER (canonical registry — ADR-041 / app_ids_gen.py) ─────────────────

_HERE = pathlib.Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from app_ids_gen import APP_ORDER as _APP_ORDER_SRC
APP_ORDER: list[str] = list(_APP_ORDER_SRC)   # defensive copy; treat as read-only

_ICONS_DIR = _HERE.parent / "icons" / "taskbar"

# ── PIL icon + taskbar ─────────────────────────────────────────────────────────

def load_icon_pil(name: str, active: bool):
    """Load a PIL RGBA Image from app/icons/taskbar/<name>[_active].png.

    Resizes to TASKBAR_ICON_W × TASKBAR_ICON_H using LANCZOS.
    Returns None if the file does not exist.
    """
    from PIL import Image
    suffix = "_active" if active else ""
    path = _ICONS_DIR / f"{name.lower()}{suffix}.png"
    if not path.exists():
        return None
    ico = Image.open(path).convert("RGBA")
    if ico.size != (TASKBAR_ICON_W, TASKBAR_ICON_H):
        ico = ico.resize((TASKBAR_ICON_W, TASKBAR_ICON_H), Image.LANCZOS)
    return ico


def draw_taskbar_pil(img, active_app: str, scroll_offset: int = 0,
                     app_order=None) -> None:
    """Draw the taskbar strip onto a PIL Image in-place.

    Mirrors firmware renderTaskbar() modulo-wrap logic.
    Slot i shows app_order[(scroll_offset + i) % N].
    Active indicator: 3 px green bar on the left edge of the active slot.
    Separator: horizontal line at the bottom edge of each slot except the last.
    """
    from PIL import ImageDraw
    if app_order is None:
        app_order = APP_ORDER
    N = len(app_order)
    draw = ImageDraw.Draw(img)
    draw.rectangle([TASKBAR_X, 0, SCREEN_W - 1, SCREEN_H - 1], fill=TASKBAR_BG)

    icon_off_x = (TASKBAR_W - TASKBAR_ICON_W) // 2
    icon_off_y = (TASKBAR_SLOT_H - TASKBAR_ICON_H) // 2

    for i in range(TASKBAR_SLOT_COUNT):
        app_idx = (scroll_offset + i) % N
        name = app_order[app_idx]
        y0 = i * TASKBAR_SLOT_H
        y1 = y0 + TASKBAR_SLOT_H - 1
        is_active = (name == active_app)

        if i < TASKBAR_SLOT_COUNT - 1:
            draw.line([TASKBAR_X, y1 + 1, SCREEN_W - 1, y1 + 1],
                      fill=TASKBAR_SEP_COL)

        ico = load_icon_pil(name.lower(), is_active)
        if ico:
            img.paste(ico, (TASKBAR_X + icon_off_x, y0 + icon_off_y), mask=ico)

        if is_active:
            draw.rectangle([TASKBAR_X, y0, TASKBAR_X + 2, y1],
                           fill=TASKBAR_ACTIVE_COL)


# ── pygame icon + taskbar ──────────────────────────────────────────────────────

_pygame_icon_cache: dict = {}


def load_icon_pygame(name: str, active: bool):
    """Load and cache a pygame Surface from app/icons/taskbar/<name>[_active].png.

    Results are cached by (name, active). Returns None if file does not exist.
    """
    import pygame
    key = (name.lower(), active)
    if key not in _pygame_icon_cache:
        suffix = "_active" if active else ""
        path = _ICONS_DIR / f"{name.lower()}{suffix}.png"
        if path.exists():
            ico = pygame.image.load(str(path)).convert_alpha()
            _pygame_icon_cache[key] = pygame.transform.scale(
                ico, (TASKBAR_ICON_W, TASKBAR_ICON_H))
        else:
            _pygame_icon_cache[key] = None
    return _pygame_icon_cache[key]


def draw_taskbar_pygame(surface, active_app: str, scroll_offset: int = 0,
                        app_order=None) -> None:
    """Draw the taskbar strip onto a pygame Surface in-place.

    Mirrors draw_taskbar_pil() semantics; uses pygame drawing primitives
    to avoid forcing a PIL round-trip on tools that render in pygame throughout.
    """
    import pygame
    if app_order is None:
        app_order = APP_ORDER
    N = len(app_order)
    pygame.draw.rect(surface, TASKBAR_BG, (TASKBAR_X, 0, TASKBAR_W, SCREEN_H))
    icon_x = TASKBAR_X + (TASKBAR_W - TASKBAR_ICON_W) // 2

    for i in range(TASKBAR_SLOT_COUNT):
        app_idx = (scroll_offset + i) % N
        name = app_order[app_idx]
        y0 = i * TASKBAR_SLOT_H
        is_active = (name == active_app)

        if i < TASKBAR_SLOT_COUNT - 1:
            pygame.draw.line(surface, TASKBAR_SEP_COL,
                             (TASKBAR_X, y0 + TASKBAR_SLOT_H),
                             (SCREEN_W - 1, y0 + TASKBAR_SLOT_H))

        ico = load_icon_pygame(name, is_active)
        if ico:
            surface.blit(ico, (icon_x, y0 + (TASKBAR_SLOT_H - TASKBAR_ICON_H) // 2))

        if is_active:
            pygame.draw.rect(surface, TASKBAR_ACTIVE_COL,
                             (TASKBAR_X, y0, 3, TASKBAR_SLOT_H))


# ── GIF writer ─────────────────────────────────────────────────────────────────

def write_gif(frames, out_path, fps: int = 20) -> None:
    """Write a list of PIL Images as an animated GIF (median-cut quantisation).

    Prints a one-line summary: path, size in KB, frame count, fps.
    """
    from PIL import Image
    out_path = pathlib.Path(out_path)
    duration_ms = round(1000 / fps)
    quantized = [f.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                 for f in frames]
    quantized[0].save(
        out_path,
        save_all=True,
        append_images=quantized[1:],
        loop=0,
        duration=duration_ms,
        optimize=False,
    )
    print(f"Wrote {out_path} ({out_path.stat().st_size // 1024} KB, "
          f"{len(frames)} frames @ {fps} fps)")


# ── PreviewWindow ──────────────────────────────────────────────────────────────

class PreviewWindow:
    """Scaled pygame window wrapper for 320×240 device preview tools.

    Lazy-imports pygame in __init__ so tools that only use write_gif or
    draw_taskbar_pil can import from this module without triggering pygame.

    Handles +/= (scale up), - (scale down), q/Q/QUIT (exit) via handle_event().
    """

    def __init__(self, title: str, scale: int = 2) -> None:
        import pygame as _pg
        self._pg = _pg
        if not _pg.get_init():
            _pg.init()
        self._title = title
        self._scale = scale
        _pg.display.set_caption(title)
        self._screen = _pg.display.set_mode((SCREEN_W * scale, SCREEN_H * scale))

    @property
    def scale(self) -> int:
        return self._scale

    @scale.setter
    def scale(self, value: int) -> None:
        self._scale = value
        self._screen = self._pg.display.set_mode(
            (SCREEN_W * value, SCREEN_H * value))

    def handle_event(self, event) -> bool:
        """Process a single pygame event.

        Handles:
          +/= — increment scale (max 4), returns True.
          -   — decrement scale (min 1), returns True.
          q/Q / QUIT — calls sys.exit(0). Never returns.
        Returns False for unhandled events.
        """
        pg = self._pg
        if event.type == pg.QUIT:
            pg.quit()
            sys.exit(0)
        if event.type == pg.KEYDOWN:
            k = event.key
            if k == pg.K_q:
                pg.quit()
                sys.exit(0)
            if k in (pg.K_PLUS, pg.K_EQUALS, pg.K_KP_PLUS):
                self.scale = min(4, self._scale + 1)
                return True
            if k in (pg.K_MINUS, pg.K_KP_MINUS):
                self.scale = max(1, self._scale - 1)
                return True
        return False

    def blit_pil(self, img) -> None:
        """Convert PIL Image to pygame Surface, scale, and blit to display.

        Does not call pygame.display.flip() — call flip() separately.
        """
        pg = self._pg
        if img.mode != "RGB":
            img = img.convert("RGB")
        surf = pg.image.fromstring(img.tobytes(), img.size, "RGB")
        if self._scale != 1:
            surf = pg.transform.scale(
                surf, (SCREEN_W * self._scale, SCREEN_H * self._scale))
        self._screen.blit(surf, (0, 0))

    def flip(self) -> None:
        self._pg.display.flip()
