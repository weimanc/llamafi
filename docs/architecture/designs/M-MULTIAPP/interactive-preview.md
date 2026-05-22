# M-MULTIAPP — Interactive Preview Tooling

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> Companion: [preview-tooling.md](preview-tooling.md)

## Context / pain points

`preview-tooling.md` specifies a static `--layout-preview` mode for `bake_skin.py`
that renders `gen/layout_preview.png`. This is pixel-accurate — it composites the
real Winamp skin assets via PIL — but it requires a full re-run to see each variant.
The open aesthetic questions (background colour, active indicator style, separator
style, icon approach) have four or more binary axes; exploring the full space via
repeated CLI invocations is slow.

Design goal: make the parameter iteration loop interactive while keeping the same
PIL rendering path that guarantees pixel accuracy.

## Goals

1. Pixel accuracy is non-negotiable — the interactive tool uses the same PIL
   composite path as the static PNG, not a CSS approximation.
2. Zero or minimal new dependencies — the project already has PIL (always
   present) and pygame (lazy-imported in `preview_vis.py`). New deps require
   justification.
3. Fast feedback — parameter change → updated render in under one second.
4. Chosen parameters must flow back to firmware — the tool must make it easy
   to record the approved values as `renderTaskbar()` constants.

## Design space

### Option A — pygame live panel

Extend the existing `--live` pattern in `preview_vis.py` to a new
`preview_layout.py` script (or `--interactive` flag on `bake_skin.py`).
Displays the 320×240 PIL composite in a pygame window at 1:1. Keyboard
shortcuts cycle through the parameter axes:

| Key | Action |
|-----|--------|
| `b` | Cycle taskbar background (`#111` → `#232323` → `#333` → …) |
| `i` | Cycle active indicator style (A: bar → B: cell → C: dot) |
| `s` | Toggle separator lines |
| `c` | Cycle active indicator colour |
| `[` / `]` | Step active slot (to preview indicator on different apps) |
| `p` | Print current params as `bake_skin.py` CLI args to stdout |
| `q` | Quit |

**Pros:** pygame is already a dep (optional, lazy-imported); no server; renders
at native resolution; consistent with `preview_vis.py` pattern.
**Cons:** requires a display (no headless CI); not shareable without running
the script.

### Option B — single-file HTML export

`bake_skin.py --layout-preview --html` emits `gen/layout_preview.html`. The
Winamp skin composites are embedded as base64 PNG data URIs. The taskbar strip
is rendered as a `<canvas>` overlay drawn by inline JS. Sliders and radio
buttons update the canvas in real time; `image-rendering: pixelated` keeps
everything at integer scale. An "Export params" button prints the CLI args
to a `<pre>` block for copy-paste.

**Pros:** no Python deps beyond PIL; opens in any browser; shareable as a
single file; survives headless environments.
**Cons:** taskbar canvas is JS-redrawn, not PIL-redrawn — colours and glyph
positions are accurate but the icon glyphs themselves are placeholder shapes
(font chars or coloured rectangles) until real 24×24 bitmaps are baked in.
Slight colour-space risk (sRGB in browser vs. RGB565 on device).

### Option C — Flask hot-reload loop

Tiny Flask server (~30 lines). Browser `<img>` polls `/preview.png`; a parameter
form posts to `/update`; the server re-runs the PIL composite and refreshes the
image. Pixel-perfect (PIL renders, browser only displays).

**Pros:** full PIL fidelity including icon glyphs; browser devtools can measure
pixel coordinates directly.
**Cons:** new dep (Flask); more setup; one round-trip latency per parameter
change (acceptable but slower than A or B).

### Option D — Jupyter notebook

`ipywidgets` sliders call `render_layout_preview()` inline; `IPython.display`
shows the PIL image. Good for exploratory iteration.

**Cons:** requires Jupyter — not currently in project; heavyweight for a
one-time aesthetic decision pass.

## Lean / decision

**Primary: Option A (pygame live panel).**
Zero new deps, consistent with existing `preview_vis.py` pattern, instant
feedback. Sufficient for the aesthetic decision pass (one developer, one
screen, one session).

**Secondary: Option B (HTML export) as a shareable artefact.**
After the pygame session, run `--layout-preview --html` to emit a single HTML
file that captures the approved configuration alongside the alternatives.
Checked into `gen/` (excluded from `golden.sha256`) as a record of the
decision, and useful if a second opinion is needed without running Python.

Options C and D are deprioritised: Flask adds a dep for no accuracy gain over
A; Jupyter is overkill for a single-pass aesthetic decision.

## Approved-params handoff

When the pygame session ends, pressing `p` prints:

```
# approved taskbar params — paste into renderTaskbar() constants
TASKBAR_BG      = 0x2323  # #232323 in RGB565
ACTIVE_STYLE    = A       # 3 px left bar
ACTIVE_COLOR    = 0x07E0  # #1db954 → nearest RGB565
SEP_COLOR       = 0x4208  # #444444 → nearest RGB565
SEP_ENABLED     = true
ICON_APPROACH   = A       # TFT_eSPI GLCD font chars
```

These values are transcribed into the open-questions section of `taskbar.md`
to close that section and unblock `renderTaskbar()` implementation.

## Relationship to preview-tooling.md exit criteria

The interactive pass satisfies the same exit criteria as the static pass
(three variants compared, all four open questions resolved). The static
`--layout-preview` PNG remains the canonical committed artefact; the
interactive tool is a developer-only session aid.

## Open questions

1. **Icon glyphs in pygame session** — use PIL `ImageFont` with a small TTF
   (already available on Linux via system fonts) or placeholder coloured
   rectangles? Placeholder rects are sufficient for colour/indicator decisions;
   font chars are needed to validate icon readability.
2. **Scale factor** — 320×240 is small on a HiDPI display. pygame `--scale 2`
   (nearest-neighbour zoom) or CSS `transform: scale(2)` in HTML? Must be
   integer scale to preserve pixel accuracy.
3. **HTML colour-space** — browser renders sRGB; RGB565 on device has different
   gamut for saturated colours (notably Spotify green `#1DB954`). Note the
   discrepancy in the HTML artefact so the designer is aware.

## Exit criteria

| Criterion | Verification | Test |
|-----------|-------------|------|
| `preview_layout.py --interactive` opens 320×240 pygame window with keyboard controls and `p` prints params | **Manual** — requires display; no headless path | T131 |
| `bake_skin.py --layout-preview --html` emits `gen/layout_preview.html` with base64 skin assets + `<canvas>` element | **Automated** — file presence + structure grep | T130 |
| "Working JS controls" in HTML | **Manual** — browser runtime required | T131 (visual check) |
| All four open questions in `taskbar.md` answered (no TBD markers) | **Automated** — `grep -c "TBD"` == 0 | T132 |
| `golden.sha256` excludes `layout_preview.html` and still passes | **Automated** — `sha256sum -c` | T132 |

Note: this design doc has no feature inventory entry. A `preview-tooling-001` feature must be added to `feature_inventory.yaml` before T130–T132 can be formally tracked (flagged to Architect and PM).
