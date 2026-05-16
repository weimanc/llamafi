# Design — M-UI-POLISH Small UI Fidelity Improvements

> Owner: Developer
> Status: done (2026-05-16)
> Tracked-as: TASK-048, TASK-049
> Deps: M3, M6

## Item 1 — Artist + title in marquee strip (TASK-048)

**Gap:** title strip shows track `name` only. `Snapshot::artistName` already populated, not wired.

**Winamp 2 format:** `"Artist - Title"` (no track-number prefix). Fall back to `"Title"` when artist blank.

Changes:
- `lastTitle[128]` → `lastTitle[260]` (artist 128 + `" - "` 3 + title 128 + NUL 1).
- Compose `artist + " - " + name` on track change; detect change on either field.
- Scroll gap: insert `"   "` (3 spaces) between end and loop-back start (classic Winamp endless ticker).
- `TITLE_SCROLL_STEP_MS=120` unchanged.

~10 LOC in `winampDisplay.h`.

## Item 2 — VU zero-fill from SKIN_MAIN_BG (TASK-049)

**Gap:** `vuMeter.h::tick()` clears "off" portion of each bar with `fillRect(TFT_BLACK)`, overwriting skin's vis-area background texture.

**Fix:** Mirror `drawTitleText()` pattern — blit corresponding `SKIN_MAIN_BG` rows into zero-fill region. VU rects `(x=24, LEFT_Y=43, RIGHT_Y=50, w=76, h=6)` fully within `275×116` `SKIN_MAIN_BG` atlas.

Changes:
- Add `const uint16_t *mainBg` param to `vu::tick()`.
- Replace `fillRect(TFT_BLACK)` with per-row `pushImage` from `SKIN_MAIN_BG` at zero-fill offset.
- Update `vu::tick(originX, originY, SKIN_MAIN_BG)` call site in `.ino`.

~15 LOC in `vuMeter.h` + 1 LOC call site.

## Exit criteria

- DUT: title strip shows `"Artist - Title"`, scrolling with gap spacer between end and loop-start.
- DUT: title strip shows `"Title"` only when artist blank.
- DUT: VU bars restore skin background texture in zero-fill region (no solid black border).
- No regression in title scroll timing, VU animation cadence, chrome repaint.
