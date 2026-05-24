# Design — audit_origin.py: PC-Side Origin-Relative Audit

> Owner: Developer
> Status: planned (2026-05-24)
> Tracked-as: TASK-082
> Unblocks: TASK-081 (VE T141–T146 without DUT)

## Scope

Host-side Python tool that verifies all winamp render and hit-test sites are correctly
origin-relative, as a pre-gate for the M-MULTIAPP originX shift (22 → 0). Replaces the
DUT requirement for T142–T146 — the audit is purely geometric and can be validated
entirely from the skin_layout.h constants and a Python reimplementation of the firmware
hit-test functions.

## Why PC-Only Is Sufficient

The M-MULTIAPP originX shift is a **linear translation**: every screen x coordinate
becomes `window_local_x + new_origin_x` instead of `window_local_x + 22`. All
correctness claims reduce to "does firmware compute zone membership from
`sx - originX` (relative)?". This can be proven by:

1. **Static grep** — no bare absolute X integer in tft draw calls in `winampDisplay.h`.
2. **Simulator** — a Python reimplementation of the firmware hit-test functions using
   the same skin_layout.h constants; run at both originX=22 and originX=0; assert zones
   shift identically.

No hardware state is involved. A DUT run adds board noise without additional assurance.

## Tool: `tools/audit_origin.py`

### CLI

```sh
~/proj/esp/venv/bin/python3 tools/audit_origin.py            # T141–T146 text
~/proj/esp/venv/bin/python3 tools/audit_origin.py --visual   # + gen/origin_audit.png
~/proj/esp/venv/bin/python3 tools/audit_origin.py --grep-only # T141 only
```

Exit 0 = all checks pass. Exit non-zero + failure list otherwise.

### Inputs / Reuse

| Input | Source | Reuse method |
|---|---|---|
| All zone constants | `gen/skin_layout.h` | `parse_skin_layout()` from `bake_skin.py` — import or call directly |
| Zone rect definitions | `render_hitzones()` in `bake_skin.py` (~line 1083) | Extract zone rect dict into a shared helper; both call it |
| ORIGIN_X formula | `coords.py` line 25 | `(SCREEN_W - WINDOW_W) // 2` — replicate inline |
| PIL | project venv (Pillow, already installed) | Visual PNG output only |

### Module Structure

```
audit_origin.py
├── parse_layout()         # thin wrapper: calls bake_skin.parse_skin_layout()
├── build_zones(S)         # returns dict{zone_name: Rect} in window-local coords
│                          # extracted from render_hitzones() zone registry
├── hit_test(sx, sy, ox)   # → zone_name  (see §Hit-Test Simulator)
├── t141_grep()            # static X-arg audit of winampDisplay.h
├── t142_t145_zones(ox)    # boundary tests for all zones at given originX
├── t146_full(ox)          # all boundary cases at ox=0 (exit gate)
└── render_visual()        # optional two-panel PNG
```

### Hit-Test Simulator

```
hit_test(sx: int, sy: int, origin_x: int, origin_y: int = 0) -> str
```

Subtracts origin to get window-local coordinates, then checks zones in **firmware
dispatch order** (matches `checkForInput()` in `winampDisplay.h`):

1. TRANSPORT (5 buttons, each its own rect at window-local y=88..106)
2. POSBAR
3. VOLUME
4. SHUFFLE
5. REPEAT
6. VIS
7. PLEDIT-Z2 (scrollbar strip — right column, Zone 2)
8. PLEDIT-Z1 (content area — Zone 1)
9. LOGO
10. DEADZONE (fallthrough)

**Boundary semantics**: inclusive left/top, exclusive right/bottom — matches firmware.

**PLEDIT Y special case**: The firmware compares `py = sy - originY` against absolute
screen Y thresholds (`PLEDIT_ROWS_Y=136`, etc.). In the simulator this is expressed as:

```python
# PLEDIT Y uses absolute screen Y, not window-local wy:
py = sy - origin_y   # same as firmware
if py >= PLEDIT_ROWS_Y and py < PLEDIT_ROWS_Y + ROW_COUNT * ROW_H:
    ...
```

This mirrors the known firmware mismatch (documented in TASK-080 finding 3). The
simulator must replicate it faithfully — validating the behavior, not hiding it.

### T141 — Static Grep

Regex-scan `winampDisplay.h` for every `tft.draw*` / `tft.fill*` / `tft.pushImage`
call. Extract the first positional argument (the X coordinate expression). Accept:

- `originX` or any variable derived from it: `rightX`, `rightEdge`, `slotX`, `barX`,
  `thumb_x`, `knobX`, `dstX`, `lx`, `rx`, `tx`, `x0`, `x1`, `ry`, `sy` (loop var in
  PLEDIT side-tile loop), `leftX`
- `fillRect(0, ...)` — intentional gutter-fill pattern (explicit accept-list)

Flag as failure: any bare integer literal not in the accept-list.

### T142–T145 — Zone Boundary Tests

For each zone, generate the canonical boundary points (same cases as T076/T086):
4 inside (one per edge, 1 px inset) + 4 outside (1 px beyond each edge).

Run `hit_test()` at **both** originX=22 (current) and originX=0 (M-MULTIAPP):

| Case | Expected at originX=22 | Expected at originX=0 |
|------|------------------------|----------------------|
| Inside coord (screen abs) | Correct zone | Correct zone ← coord shifts too |
| Outside coord (screen abs) | DEADZONE | DEADZONE |
| Old inside coord fixed at ox=22 screen pos | Correct zone | DEADZONE (22 px into gutter) |

The third case is the key regression signal: if a zone's boundary were hardcoded to
`sx >= 38` instead of `sx >= originX + 16`, the old coordinate (38) would still hit at
originX=0 — which the test catches.

Zone coverage:
- **T142**: TRANSPORT — left edge of PREV, each button boundary, right edge of NEXT
- **T143**: POSBAR (4+4) + VOLUME (4+4)
- **T144**: PLEDIT Zone 1 (content area) + Zone 2 (scrollbar strip); includes the
  old-T134 coord cross-check (x=156 at originX=0 → DEADZONE; x=134 → PLEDIT)
- **T145**: Canvas corners at both origins; x=275..319 produces no winamp zone (verifies
  the right-margin gap that opens after the shift)

### T146 — Full Regression at originX=0

Run all named-zone inside/outside boundary cases through `hit_test()` at originX=0 only.
All must pass. This is the TASK-081 exit gate.

### Visual Output — `gen/origin_audit.png`

Two-panel PNG (640×240):

```
┌─────────────────────┬─────────────────────┐
│  originX=22 (now)   │  originX=0 (MMAP)   │
│  skin_hitzones      │  skin_hitzones       │
│  outline at ox=22   │  outline at ox=0     │
│  ● green = hit ok   │  ● green = hit ok    │
│  ● red   = miss     │  ● red   = miss      │
└─────────────────────┴─────────────────────┘
```

Extends `render_hitzones()` in `bake_skin.py`: refactor to accept `(image, origin_x,
draw_origin)` so `audit_origin.py` can call it twice into a 640×240 canvas. The
existing call-site (writing `skin_hitzones.png`) passes `origin_x=22` and
`draw_origin=(0,0)` — unchanged externally.

## Files

| File | Change |
|---|---|
| `tools/audit_origin.py` | **create** — ~200 LOC |
| `tools/bake_skin.py` | **minor** — parameterise `render_hitzones()` with `image` + `origin_x` args; existing call-site unchanged |

## Exit Criteria (TASK-082)

- `python3 tools/audit_origin.py` exits 0 on current tree (`originX=22` firmware)
- `--visual` produces `gen/origin_audit.png` with all green dots (no red)
- `--grep-only` exits 0 (no bare absolute X literals in draw calls)
- Running with `origin_x=0` argument also exits 0 (verifies zones shift correctly)
- `sha256sum -c gen/golden.sha256` unaffected (`origin_audit.png` excluded from golden)
