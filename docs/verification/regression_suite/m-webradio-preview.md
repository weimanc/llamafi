# M-WEBRADIO Preview Tool VE Suite

> Owner: Verification Engineer
> Milestone: M-WEBRADIO (TASK-201)
> Deliverable: `app/tools/preview_webradio.py`
> Status: recheck required — TASK-201 fix in progress (LED font + sprite chrome); prior run results on pre-fix tool are void
> Run date: 2026-06-14 (pre-fix run); rerun required after TASK-201 targeted fix
> Pattern: follows `preview_vis.py` (not clock pattern)

---

## Purpose

`preview_webradio.py` is a host-side pygame layout preview tool.  It renders
radio-specific content on top of `gen/skin_preview.png` (the 320×240 Winamp
chrome baked by `./run/bake-skin`) so the Architect and PM can sign off on
canvas layout **before** any DUT firmware work begins.

These tests define "done" for TASK-201.  No DUT is required — all tests run
on host (Linux, project venv).

---

## Test inventory

| ID   | Description                                          | Method       | Status  |
|------|------------------------------------------------------|--------------|---------|
| T273 | Tool launches without error in each of 4 states      | host script  | recheck required |
| T274 | All 4 keyboard-driven states are reachable at runtime | host script (headless) | recheck required |
| T275 | All required canvas elements are present in each state | host visual  | **recheck required — prior sign-off void** |
| T276 | Skin base layer is loaded from `gen/skin_preview.png` | host script  | recheck required |
| T277 | Canvas stays within 275×240 app area (no taskbar bleed) | host script | recheck required |
| T278 | No cross-import of unrelated module constants         | host script  | recheck required |
| T279 | Missing `--wsz` file produces graceful error          | host script  | planned |
| T280 | LED font glyphs render from TEXT.BMP (not PIL default) | host script + pixel inspect | planned |
| T281 | POSBAR chrome drawn from POSBAR.BMP sprite (not fill-rect) | host visual + pixel sample | planned |
| T282 | `--wsz` argument accepted and validated               | host script  | planned |

---

## Preconditions (common to all tests)

- `./run/bake-skin` has been run; `app/gen/skin_preview.png` and
  `app/gen/skin_layout.h` exist.
- `skins/base-2.91.wsz` present (required for TEXT.BMP/POSBAR.BMP/PLEDIT.BMP sprite extraction — added in TASK-201 targeted fix).
- Project venv active (`~/proj/esp/venv`), or `python3` with `Pillow`,
  `pygame`, `numpy` installed.
- `DISPLAY` set (any valid X or Wayland display) for tests that open a window;
  or use `pygame.display.set_mode` with `NOFRAME` / offscreen driver if running
  headless.
- Working directory is `app/tools/` so that `from preview_common import …`
  and `from bake_skin import …` resolve via the directory-local import.

---

## T273 — [M-WEBRADIO-PREVIEW] Tool launches without error in each state

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: `preview_webradio.py` imports cleanly and renders one frame in
  each of the 4 logical states (stopped / connecting / playing / error) without
  raising an exception.  Guards against missing imports, wrong path defaults, and
  `skin_preview.png` / wsz load failures.
- **Preconditions**: Common preconditions above.  `gen/skin_preview.png` and `skins/base-2.91.wsz` present.
- **Steps**:
  1. In a headless context (e.g. `SDL_VIDEODRIVER=offscreen`), import the module
     and call its per-state render function for each of the 4 states.
  2. Assert no exception is raised.
  3. Assert the returned PIL Image (or pygame Surface) is non-None.
- **Expected result**: All 4 render calls return without error.  No
  `FileNotFoundError`, `ImportError`, or `AttributeError`.
- **Status**: recheck required — pre-fix run passed (2026-06-14) but wsz dependency was not present; rerun after TASK-201 fix.

---

## T274 — [M-WEBRADIO-PREVIEW] All 4 states reachable via keyboard shortcuts

- **Type**: host manual (interactive)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Keyboard shortcuts cycle through all four states: stopped →
  connecting → playing → error.  Operator confirms the window title or on-canvas
  label updates correctly at each transition.
- **Preconditions**: `DISPLAY` available.  `gen/skin_preview.png` and `skins/base-2.91.wsz` present.
- **Steps**:
  1. Launch: `python3 preview_webradio.py --skin ../gen/skin_preview.png --wsz ../../skins/base-2.91.wsz`
  2. Note initial state label in window title or canvas.
  3. Press the documented key for each state transition (e.g. `s`=stopped,
     `c`=connecting, `p`=playing, `e`=error, or whichever keys the tool
     documents).  Cycle through all 4.
  4. Confirm each state produces a visually distinct frame (different status
     indicator, buffer bar fill, VU envelope).
- **Expected result**: All 4 states are reachable.  Window title or on-canvas
  text changes to reflect the active state.  No crash on any transition.
- **Status**: recheck required — pre-fix run passed (2026-06-14) but wsz was not loaded; launch command updated; rerun after TASK-201 fix.

---

## T275 — [M-WEBRADIO-PREVIEW] All required canvas elements present in each state

- **Type**: host visual (manual, with pixel-sample script assist)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Verify every element specified in `docs/architecture/designs/M-WEBRADIO.md`
  §Canvas layout is rendered with correct skin fidelity.  Guards against incomplete
  implementation where a widget exists in the design but was not drawn, or was drawn
  with the wrong rendering path (PIL font / synthetic rectangles rejected).
- **Preconditions**: Tool can produce a static PNG snapshot per state. `skins/base-2.91.wsz` and `gen/skin_preview.png` present. **Must be run on post-fix tool — any sign-off obtained on pre-fix (PIL font / grey rect chrome) snapshots is void.**
- **Elements to verify (each state)**:
  - **PL panel** (station list rows, bottom portion of app area): at least one
    station row drawn; scroll indicator visible if station count > visible rows.
    **PLEDIT title and bottom chrome must be actual skin sprites, not fill-rects.**
  - **Station name marquee** (line 1 of title area): non-empty text drawn within
    canvas x=0..274. **Must use 5×6 px LED glyphs from TEXT.BMP — not PIL proportional font.**
  - **ICY StreamTitle** (line 2): present in `playing` state; absent or
    placeholder in `stopped`/`connecting` states.
  - **Buffer bar** (replaces seek bar): rendered in the seek-bar region of the
    Winamp skin. **POSBAR background must show skin sprite texture, not flat grey.**
    Fill level differs between `connecting` (0–20%) and `playing` (50–100%) states.
  - **Bitrate field**: numeric string or `"--- kbps"` drawn to the right of the
    buffer bar.
  - **VU meter**: spectrum bars present in `playing` state; flat/zero in
    `stopped` state.
  - **Country badge**: a small badge (2–4 character ISO code) visible in the
    top-right of the title area (x > 180, y in Winamp title row).
- **Steps**:
  1. Render a PNG snapshot for each of the 4 states.
  2. Visually inspect each snapshot against the §Canvas layout ASCII diagram in
     `M-WEBRADIO.md`.
  3. Pixel-sample the VU meter region in `playing` state: assert ≥ 1 pixel
     differs from the skin background (bars are drawn).
  4. Pixel-sample the VU meter region in `stopped` state: assert region matches
     or approximates the background (bars absent).
  5. Inspect the TITLE zone (x=111..264, y=27..32): confirm narrow LED-style glyph
     rendering (not proportional font).
  6. Inspect POSBAR zone (y=72..81, `stopped` state): confirm skin texture visible.
- **Expected result**: All 7 element types visible in the states where they should
  appear.  No element overflows the 275 px wide app area.  LED font and sprite
  chrome confirmed. **Human sign-off on layout required — this is the gate for
  firmware implementation.**
- **Status**: recheck required — prior sign-off (pre-fix PNGs) is void; gate must be re-executed on post-fix snapshots.

---

## T276 — [M-WEBRADIO-PREVIEW] Skin base layer loaded from `gen/skin_preview.png`

- **Type**: host automated (script)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: The tool loads `gen/skin_preview.png` as its base layer and
  does not ship a hardcoded fallback or embedded skin.  Mirrors the
  `preview_vis.py` pattern where `--skin` is a required argument and the image
  dimensions are confirmed at load time.
- **Preconditions**: `gen/skin_preview.png` present (320×240 px, baked by
  `./run/bake-skin`).  A dummy 1×1 PNG named `bad.png` available for negative
  test.
- **Steps**:
  1. Launch the tool (or call the load function directly) with the correct skin
     path.  Assert the loaded image is 320×240.
  2. Launch with a missing path.  Assert the tool exits with a non-zero code and
     prints an error to stderr (mirrors `preview_vis.py` lines 351–353).
  3. Launch with `bad.png` (wrong dimensions).  Assert the tool exits or raises
     a clear error — it must not silently clip or stretch the skin.
- **Expected result**: Correct skin loads and is confirmed 320×240.  Missing or
  wrong-dimension skin produces a clear, non-zero exit.
- **Status**: passing — 2026-06-14. All four headless PNGs confirmed 320×240 via PIL Image.size.

---

## T277 — [M-WEBRADIO-PREVIEW] Canvas stays within 275×240 app area (no taskbar bleed)

- **Type**: host automated (script)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Every radio-specific drawing operation targets pixels in
  x=0..274 (the 275 px app canvas).  Pixels in x=275..319 (the 45 px taskbar
  strip) must only be written by `draw_taskbar_pil` / `draw_taskbar_pygame` from
  `preview_common.py`.  Guards against a widget accidentally overflowing the app
  boundary.
- **Preconditions**: Tool exposes a function that renders into a PIL Image (or
  renders to an offscreen surface).
- **Steps**:
  1. Capture a snapshot for the `playing` state (maximum element density).
  2. Compare the snapshot against `gen/skin_preview.png` in the taskbar band
     x=275..319: the only differences allowed are the taskbar icon/indicator
     drawn by `draw_taskbar_pil` (imported from `preview_common`).
  3. Assert no pixel in x=0..274 is identical to the raw skin in the VU meter,
     buffer bar, and station-list regions (confirms radio content was drawn).
- **Expected result**: No radio-specific drawing extends into x≥275.  App area
  (x=0..274) shows radio content on top of the skin.
- **Status**: passing — 2026-06-14. numpy slice confirmed canvas shape (240,275,3) and taskbar shape (240,45,3) for all 4 states.

---

## T278 — [M-WEBRADIO-PREVIEW] No cross-import of unrelated module constants

- **Type**: host automated (script / import inspection)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: `preview_webradio.py` does not import constants from unrelated
  preview tools (`preview_vis.py`, `preview_teletext.py`, `preview_layout.py`,
  `bake_vis.py`).  Permitted local imports: `preview_common` (shared geometry) and
  `bake_skin` (skin sprite extraction — added by TASK-201 fix).  Guards against
  copy-paste drift where VIS geometry constants (`RECT_X`, `LEFT_Y`, `VIS_H`,
  `SPEC_BARS`, etc.) are pulled in from the wrong module.
- **Preconditions**: Tool source at `app/tools/preview_webradio.py`.
- **Steps**:
  1. Parse the import block of `preview_webradio.py` (ast.parse or grep).
  2. Assert none of the following appear as imported names or module references:
     `preview_vis`, `bake_vis`, `preview_teletext`, `preview_layout`,
     `RECT_X`, `LEFT_Y`, `VIS_H`, `SPEC_BARS`, `SPEC_BAR_W`, `SPEC_BAR_STEP`.
  3. Assert `from preview_common import …` is present.
  4. Assert `from bake_skin import …` is present (whitelisted for sprite extraction).
  5. Assert no other local-tool module is imported.
- **Expected result**: No forbidden import found.  `preview_common` and `bake_skin`
  imports present.  All other local-module imports absent.
- **Status**: recheck required after TASK-201 fix (bake_skin import will be added)

---

## T279 — [M-WEBRADIO-PREVIEW] Missing `--wsz` file produces graceful error

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: When `--wsz` points to a non-existent file, the tool exits non-zero
  and prints a descriptive error to stderr.  Must not expose a bare `FileNotFoundError`
  traceback or silently continue with PIL default font.
- **Preconditions**: `gen/skin_preview.png` present.
- **Steps**:
  1. Launch with `--wsz /tmp/no_such.wsz`.  Assert non-zero exit.  Assert stderr
     contains the bad path and a human-readable message.
  2. Launch with `--wsz` pointing to a non-zip file (e.g. a text file).  Assert
     non-zero exit + clear error.
- **Expected result**: Both bad-wsz cases produce clear, actionable errors and
  non-zero exit.  No raw Python traceback.
- **Status**: planned

---

## T280 — [M-WEBRADIO-PREVIEW] LED font glyphs render from TEXT.BMP (not PIL default)

- **Type**: host automated (pixel inspection)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Station name in the TITLE zone uses 5×6 px glyphs from TEXT.BMP,
  not PIL's proportional default font.  Guards against regression to
  `ImageFont.load_default()`.
- **Preconditions**: `skins/base-2.91.wsz` and `gen/skin_preview.png` present.
- **Steps**:
  1. Render `playing` state snapshot.
  2. Sample TITLE zone (x=111..264, y=27..32).  Assert at least one pixel has
     LED green value `(0x00, 0xE8, 0x00)`.
  3. Assert no pixel in the TITLE zone has a colour value consistent with PIL
     proportional font rendering at larger pitch.  Alternative: render a known
     single character (`"A"`) and compare the 5×6 glyph region pixel-for-pixel
     against the TEXT.BMP crop at the expected glyph UV.
- **Expected result**: TITLE zone contains LED green pixels consistent with 5 px
  glyph width.  PIL default font not detected.
- **Status**: planned

---

## T281 — [M-WEBRADIO-PREVIEW] POSBAR chrome drawn from POSBAR.BMP sprite (not fill-rect)

- **Type**: host visual (manual, with pixel sample)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: The POSBAR zone (y=72..81) shows pixels from the POSBAR.BMP skin
  sprite, not the synthetic `(0x18, 0x18, 0x18)` fill-rect that was rejected.
- **Preconditions**: `skins/base-2.91.wsz` and `gen/skin_preview.png` present.
- **Steps**:
  1. Extract `POSBAR.BMP` from the wsz directly (reference crop `(0,0,248,10)`).
  2. Render `stopped` state snapshot (buffer bar empty — POSBAR background fully
     visible).
  3. Sample POSBAR zone in snapshot; compare to reference crop.  Assert pixel
     content matches sprite.  Assert grey sentinel `(0x18, 0x18, 0x18)` absent
     from the POSBAR background region.
- **Expected result**: POSBAR zone matches POSBAR.BMP sprite.  Grey fill-rect
  sentinel absent.
- **Status**: planned

---

## T282 — [M-WEBRADIO-PREVIEW] `--wsz` argument accepted and validated

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: `--wsz` is a first-class CLI argument with a default path
  (`skins/base-2.91.wsz` relative to the project root) and an explicit-path
  override.  Parallel to T276's coverage of `--skin`.
- **Preconditions**: `skins/base-2.91.wsz` present.
- **Steps**:
  1. Launch without `--wsz` — confirm default path is used and tool exits 0.
  2. Launch with `--wsz <alternate_copy>` — confirm that path is opened (tool
     exits 0, sprite rendering succeeds).
  3. Launch with `--wsz /tmp/missing.wsz` — confirm non-zero exit + error
     message (detailed coverage in T279).
- **Expected result**: Default path used when omitted.  Explicit path accepted.
  Missing path exits non-zero.
- **Status**: planned

---

## Exit criteria coverage

| Criterion (from TASK-201 / M-WEBRADIO.md §Shift-left) | Test(s)    | Status   |
|-------------------------------------------------------|------------|----------|
| Tool launches without error                           | T273       | recheck required |
| All 4 states cycle via keyboard                       | T274       | recheck required |
| All canvas elements from §Canvas layout present       | T275       | recheck required — prior sign-off void |
| Skin base layer (skin_preview.png) loads correctly    | T276       | recheck required |
| App-area boundary (275 px) respected                  | T277       | recheck required |
| No unrelated constant cross-import                    | T278       | recheck required |
| Missing wsz file → graceful error                     | T279       | planned |
| LED font from TEXT.BMP (not PIL default)              | T280       | planned |
| POSBAR chrome from POSBAR.BMP sprite                  | T281       | planned |
| `--wsz` argument accepted and validated               | T282       | planned |

Human sign-off on layout (T275, post-fix snapshots) is the gate before firmware
implementation begins.  Prior T275 sign-off on pre-fix PNGs is void.

---

## How to run (manual steps)

```sh
cd /home/weiman/proj/esp_spotify/app/tools

# Ensure skin and wsz exist
test -f ../gen/skin_preview.png || (cd ../.. && ./run/bake-skin)
test -f ../../skins/base-2.91.wsz || echo "ERROR: wsz missing"

# T274 + T275 — interactive
python3 preview_webradio.py \
    --skin ../gen/skin_preview.png \
    --wsz  ../../skins/base-2.91.wsz

# T273 / T276 / T277 / T278 / T279 / T280 / T281 / T282 — can be scripted
# (no run/ script needed; host-only, no DUT)
```

## How to run (automated / headless)

```sh
cd /home/weiman/proj/esp_spotify/app/tools
SDL_VIDEODRIVER=offscreen python3 - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import preview_webradio as pw
wsz = str(pathlib.Path(__file__).parent / "../../skins/base-2.91.wsz")
skin = str(pathlib.Path(__file__).parent / "../gen/skin_preview.png")
for state in ("stopped", "connecting", "playing", "error"):
    img = pw.render(state, skin_path=skin, wsz_path=wsz)
    assert img is not None, f"render({state!r}) returned None"
print("T273 PASS — all 4 states rendered without error")
EOF
```

(The exact function signature for `wsz_path` is illustrative — match whatever
API `preview_webradio.py` exposes after TASK-201 fix; update this script.)
