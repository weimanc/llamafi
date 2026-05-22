# M-MULTIAPP — Interactive Preview Tooling

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> Companion: [preview-tooling.md](preview-tooling.md)

## Context / pain points

`preview-tooling.md` specifies a static `--layout-preview` mode for `bake_skin.py`
that renders `gen/layout_preview.png`. This is pixel-accurate — it composites the
real Winamp skin assets via PIL — but requires a full re-run per variant.
The open aesthetic questions (background colour, active indicator style, separator
style, icon approach) have four or more binary axes; exploring the full space via
repeated CLI invocations is slow.

## Decision: pygame live panel (`preview_layout.py`)

New script `Spotify-Diy-Thing/tools/preview_layout.py`. Opens a scaled pygame
window showing the full 320×240 device layout. Keyboard shortcuts cycle parameters
in real time; pressing `e` writes `gen/shell_layout.h` with the approved values.

This is the only interactive approach. Options considered and rejected: HTML
single-file (JS-rendered taskbar is not PIL-accurate for glyphs), Flask hot-reload
(new dep, round-trip latency), Jupyter (heavyweight, not in project).

## Window and scale

The native device canvas is 320×240 — unreadably small on a modern display.
`preview_layout.py` applies a nearest-neighbour integer scale to the PIL composite
before blitting to pygame, preserving pixel accuracy.

Supported scales and fit at common laptop resolutions:

| `--scale` | Window size | Fits at |
|-----------|-------------|---------|
| 1 | 320 × 240 | any |
| 2 (default) | 640 × 480 | all laptops (1366×768+) |
| 3 | 960 × 720 | 1080p+ |
| 4 | 1280 × 960 | 1080p+ (leaves ~120 px for title bar) |
| 5 | 1600 × 1200 | 1440p+ only |

Default: `--scale 2`. Live toggle: `+` / `-` keys cycle through 1–4 without
restarting.

## Icon glyphs: Winamp 5×6 bitmap font

Icons use single uppercase ASCII characters from the Winamp skin's own TEXT.BMP
font atlas — the same glyph table (`SKIN_GLYPH`) already used by the firmware.

| Slot | App | Glyph char | CHAR_MAP location |
|------|-----|------------|-------------------|
| 0 | Spotify / Winamp | `S` | row 0, col 18 → UV (90, 0) |
| 1 | Clock | `C` | row 0, col 2 → UV (10, 0) |
| 2 | Weather | `W` | row 0, col 22 → UV (110, 0) |
| 3 | Crypto | `$` | row 1, col 29 → UV (145, 6) |
| 4 | Matrix rain | `M` | row 0, col 12 → UV (60, 0) |
| 5 | Game of Life | `G` | row 0, col 6 → UV (30, 0) |

Glyph dimensions: **5 × 6 px** (`GLYPH_W=5, GLYPH_H=6` in `bake_skin.py:170`).
Target icon cell: 24 × 24 px. Padding: `(24-5)//2 = 9` px left/right,
`(24-6)//2 = 9` px top, `9+1=10` px bottom.

### Rendering in PIL

`sources["TEXT.BMP"]` is already loaded during a bake run. The preview function
crops each glyph and pastes it into the icon cell:

```python
font_bmp = sources["TEXT.BMP"]          # already loaded in bake context
col, row = glyph_uv[ord(label)]         # from build_glyph_table()
u, v = col * GLYPH_W, row * GLYPH_H
glyph = font_bmp.crop((u, v, u + GLYPH_W, v + GLYPH_H))
# paste into 24×24 icon cell, top-left at (cell_x + 9, cell_y + 9)
cell.paste(glyph, (9, 9))
```

At `--scale 2` the glyph renders as 10×12 screen pixels — legible. At `--scale 4`
it renders as 20×24 — fills the cell.

No TTF fonts, no system fonts, no placeholder rectangles. Glyph is pixel-identical
to what the firmware will render at runtime via `tft.drawChar()` with `SKIN_GLYPH`.

## Keyboard controls

| Key | Action |
|-----|--------|
| `b` | Cycle taskbar background colour |
| `i` | Cycle active indicator style (A: 3 px bar → B: full cell → C: dot) |
| `s` | Toggle separator lines |
| `c` | Cycle active indicator colour |
| `[` / `]` | Step active slot (preview indicator on different app slots) |
| `+` / `-` | Increase / decrease scale (1–4, wraps) |
| `e` | **Export** — write approved params to `gen/shell_layout.h` |
| `p` | Print current params as `bake_skin.py` CLI args to stdout |
| `q` | Quit |

## Approved-params export (`e` key)

Pressing `e` writes `gen/shell_layout.h` directly — this is the M-SHELL-LAYOUT
handoff. No manual transcription. See `shell-layout.md` for the header schema.

The `p` key prints the same values as `bake_skin.py`-compatible CLI args (for
reference / copy-paste into CI scripts).

## Colour-space note

The pygame window and PIL composite operate in sRGB. RGB565 on the ESP32 has a
different gamut for saturated colours — notably Spotify green `#1DB954` maps to
`0x0DE8` in RGB565 and will render slightly differently on device than on screen.
This is a known display-preview discrepancy; no action required. The `e` export
writes the RGB565 value directly, not the sRGB approximation.

## Exit criteria

| Criterion | Verification | Test |
|-----------|-------------|------|
| `preview_layout.py --interactive` opens scaled pygame window; all keyboard controls respond | Manual — requires display | T131 |
| Winamp glyphs visible in icon cells at all supported scales | Manual — visual check during T131 | T131 |
| `e` key writes `gen/shell_layout.h` matching current params | Automated — T125 verifies header completeness post-export | T125 |
| All four open questions in `taskbar.md` answered (no TBD markers) | Automated — `grep -c "TBD"` == 0 | T132 |
| `golden.sha256` excludes `layout_preview.html` and still passes | Automated | T132 |

Note: `preview-tooling-001` feature entry exists in `feature_inventory.yaml`
(T130–T132 tracked there).
