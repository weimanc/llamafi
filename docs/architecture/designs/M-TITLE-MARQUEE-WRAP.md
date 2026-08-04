# Design — endless-ticker wraparound for the Winamp title marquee

> Owner: Architect
> Status: accepted (lean) — human-approved 2026-08-04 (Option B)
> Date: 2026-08-04
> Feeds: (ADR TBD — promote once implemented + VE-verified)
> Tracked-as: TASK-399
> Registers: — (touches existing feature `m3-001`; no new feature id, no new cross-feature edge)

## Context / pain points

The title strip (`TITLE_X/Y/W` = 111,27,154, `app/gen/skin_layout.h`) shows the current
Spotify track or WebRadio station via `winampDisplay::setTitle()` / `_tickMarquee()`
(`app/src/winamp/winampDisplay.h:836-848`). Feature `m3-001` (`feature_inventory.yaml:186`)
registers this as "title marquee scroll (1500 ms hold, 120 ms step, edge clipping)."

Human observation that started this doc: real Winamp 2's title marquee, once the text is
wider than the slot, scrolls **endlessly** — text exits stage left, the same text re-enters
from the right with no pause, separated by a small glyph that (in the classic font) reads
visually like a four-point star / shuriken, not scroll-out-then-blank-then-restart. The user
found the glyph in this skin's own `TEXT.BMP`: row 2, column 1 — immediately after `?` in
`bake_skin.py`'s `CHAR_MAP` (`"?*                             "`, `app/tools/bake_skin.py:174`).
Confirmed by cropping that cell out of `app/skins/base-2.91/TEXT.BMP`: it renders as a
4-pointed star, not a typewriter asterisk — `CHAR_MAP` maps it to ASCII `'*'` for lack of a
better host character, but the baked glyph is cosmetically a ninja-star/shuriken, and three of
them in a row is what old-Winamp screenshots showing "***" between marquee loops actually are.

**What the firmware does today** (`_tickMarquee()`, `winampDisplay.h:836-848`):
1. Hold at `titleScrollOffset = 0` for `TITLE_SCROLL_HOLD_MS` (1500ms).
2. Step `titleScrollOffset` left by one glyph cell every `TITLE_SCROLL_STEP_MS` (120ms).
3. `drawTitleText()` blanks the slot from `SKIN_MAIN_BG` and redraws only the surviving
   substring — once `titleScrollOffset` exceeds the text's pixel width the slot is empty.
4. When `titleScrollOffset > textPx`, it's reset to `-TITLE_W / (GLYPH_W + 1)` — i.e. the text
   starts fully off-screen right and scrolls back in from scratch.

So today's motion is **scroll-out → hold-blank → scroll-in-from-the-right**, not a continuous
loop. There is no second copy of the string and no separator glyph anywhere in the current
code — single `lastTitle` buffer, single pass through it per `drawTitleText()` call
(`winampDisplay.h:1209`).

Notably, `M-UI-POLISH-fidelity.md` (status: done, TASK-048) already *specified* endless-loop
behavior — "Scroll gap: insert `"   "` (3 spaces) between end and loop-back start (classic
Winamp endless ticker)" — but the shipped `_tickMarquee()`/`drawTitleText()` pair does not
implement it; TASK-048 landed the `"Artist - Title"` composition half of that item and not the
gap/loop half (`git log` shows no separate follow-up). That's a real design-vs-implementation
gap this doc should close rather than repeat.

## Goals

1. Match real Winamp's endless-ticker motion: once `lastTitle` is wider than `TITLE_W`, the
   marquee never fully blanks — the tail of one pass and the head of the next are visible in
   the same frame, joined by a separator.
2. Use the skin's actual shuriken glyph (`CHAR_MAP` row2/col1, baked into `SKIN_GLYPH['*']`)
   as that separator, matching the visual the user identified in `TEXT.BMP` — not literal
   ASCII `***` chosen independently of the skin, and not the `"   "` spacer TASK-048 specified
   without reference to the glyph.
3. Keep the short-text path (`textPx <= TITLE_W`) exactly as-is: static, centered-by-convention
   at offset 0, no separator, no motion. Real Winamp only loops when the text doesn't fit.
4. No new RAM growth beyond what a slightly longer effective scroll string requires — `m3-001`
   and `M-BOOT-UI` both note this display stack runs under real DRAM/BSS pressure
   (`_wifiDownStash` was already moved off static BSS for exactly this reason,
   `winampDisplay.h:701-706`).
5. Preserve the WiFi-down override and boot-status callers (`main.cpp`, `showWifiDownOverride()`)
   unchanged — they call `setTitle()`/`_forceSetTitle()` with short strings that never trigger
   the wrap path today; the new loop logic must be a no-op for them, not something they need to
   opt into or out of.

## Design space (options + tradeoffs)

### Option A — render `lastTitle` twice with a fixed separator, single conceptual string

Compose the *scroll* string once per `setTitle()`/`_forceSetTitle()` call, not per frame:
`scrollBuf = lastTitle + " * * * " + lastTitle` (using the shuriken glyph, `SKIN_GLYPH['*']`,
for `*`), and drive `titleScrollOffset` through `strlen(lastTitle) + separatorPx` pixels before
wrapping back to 0 — i.e. the wrap point is exactly one full period of (text + separator), so
the second copy's head seamlessly becomes what the first copy's head looked like at offset 0.

- **+** Simplest mental model — one extra buffer, `drawTitleText()` unchanged except it reads
  from `scrollBuf` instead of `lastTitle` once scrolling.
  extra buffer.
- **+** Trivially matches "no blank hold" — the slot always has *something* on-screen mid-loop.
- **−** Doubles the string's static storage at rest (`scrollBuf` sized like `lastTitle` × 2 +
  separator) — 264B → ~536B if it's a fixed same-shape member. Mitigated by lazy `malloc`
  (same pattern already used for `_wifiDownStash`, `winampDisplay.h:707`) sized to the *actual*
  `strlen(lastTitle)*2 + sep` rather than worst case.
- **−** Every `setTitle()` call does a second `strcpy`-equivalent; negligible at track-change
  frequency (seconds, not frames).

### Option B — modular index into `lastTitle` at render time, separator synthesized in `drawTitleText()`

Don't materialize a doubled string. Keep `titleScrollOffset` as a pixel offset modulo
`period = textPx + sepPx`, and in `drawTitleText()`, walk a virtual sequence: characters of
`lastTitle`, then the fixed separator glyphs, then characters of `lastTitle` again — computed
glyph-by-glyph via `offset % period` and a small index arithmetic branch (three cases: in first
copy, in separator, in second copy) instead of a real second copy in memory.

- **+** Zero extra buffer — no malloc, no doubled storage, matches Goal 4 most directly.
- **+** No `setTitle()`-time work beyond what already happens (single `strncpy` into
  `lastTitle`, unchanged).
- **−** `drawTitleText()` gets a 3-way branch inside its per-glyph loop instead of one flat
  `for (const char *p = lastTitle; *p; ++p)` — more surface for an off-by-one than Option A,
  though the loop is already doing clipping arithmetic (`winampDisplay.h:1209-1226`) so it's
  not introducing branchiness where there was none.
- **+** Separator glyph sequence lives as a `static constexpr` array of `SkinUV` (or char
  codes run through the same `SKIN_GLYPH[]` lookup already used for real text) — no new asset,
  no bake-tool change; `SKIN_GLYPH['*']` already exists (`app/gen/skin_assets.c`, generated by
  `bake_skin.py:962-967`).

### Option C — keep bounce motion, just change what's drawn during the blank hold

Smallest possible diff: leave `_tickMarquee()`'s scroll-out/reset-to-off-screen/scroll-in
structure exactly as-is, but instead of letting the slot go blank between passes, hold the
separator glyphs centered/left-aligned during the dead time.

- **+** Least code churn — touches only the `textPx <= TITLE_W` fallthrough and the reset
  branch in `_tickMarquee()`.
- **−** Does not actually deliver Goal 1 — motion is still bounce, not endless ticker; a
  stationary shuriken during the hold is not what the user described or what real Winamp does.
  Rejected as not meeting the stated goal, kept here only because it was the cheapest option
  and worth naming why it doesn't clear the bar.

## Lean / decision

**Option B — human-approved 2026-08-04.** It's the only one of the three that gets full marks on both Goal 1 (true endless
loop) and Goal 4 (no new RAM) without a malloc/lazy-init dance layered on top — and the
increased branch complexity in `drawTitleText()`'s hot loop is bounded (one `%` and a 3-way
range check per glyph, still O(visible glyphs) same as today) and testable in isolation via the
existing `wrMarquee` debug var (`winampDisplay.h:1110`, already exposes `lastTitle`/
`scrollOffset` for TASK-390-style observability — extend it to expose the computed period too).

Concretely:
- Separator constant: 3 shuriken glyphs, single-space-gapped on each side to read cleanly —
  i.e. the classic `"   ***   "` shape but built from `SKIN_GLYPH['*']` (the real baked glyph)
  rather than three literal `'*'` ASCII draws that happen to resolve to the same table entry
  today anyway (`SKIN_GLYPH[(uint8_t)'*']` already points at the shuriken cell per
  `CHAR_MAP`/`build_glyph_table()` — so no bake-tool change is required either way; the design
  choice is about *loop structure*, not sourcing a new glyph). Exact spacing is a VE/visual-fit
  question, not an architectural one — flagged as an open question below rather than picked
  here.
- `period = textPx + sepPx` (both computed once in `setTitle()`/`_forceSetTitle()`, cached
  alongside `lastTitle`, not recomputed per frame).
- `_tickMarquee()` drops its `if (titleScrollOffset > textPx) reset` branch entirely — replace
  with unconditional `titleScrollOffset = (titleScrollOffset + 1) % period` once `textPx >
  TITLE_W`; no more "off-screen respawn," no more hold-blank between passes. The initial
  `TITLE_SCROLL_HOLD_MS` hold-at-0 before the *first* pass starts should stay — that pause is
  what lets a short-lived title be read at all before it starts moving, and nothing about
  switching to endless-loop motion argues for removing it.
- `drawTitleText(offset)` walks a virtual index `i = 0..period-1` via `offset`: if
  `i < textLen`, draw `lastTitle[i]`; if `i < textLen + sepLen`, draw `separator[i - textLen]`;
  else draw `lastTitle[i - textLen - sepLen]`. Same clip-to-slot-edges logic as today, just
  fed from the virtual sequence instead of a flat `lastTitle` walk.

## Open questions

- **Exact separator glyph run and spacing** — `" * * * "` vs `"   ***   "` vs something
  narrower. This is a visual-fit call best made by looking at it on the actual TFT (DUT) or a
  `preview_layout.py`-rendered mock, not decided from the BMP crop alone. Recommend Developer
  render a couple of candidates via `app/tools/preview_layout.py` before committing.
- **Does the separator participate in the hold-at-start pause?** i.e. does the very first frame
  (`titleScrollOffset = 0`, pre-scroll hold) show `lastTitle` alone (today's behavior,
  preserved) or already include a trailing hint of the separator peeking in from the right?
  Leaning toward "alone" (simplest, matches today, matches Goal 3's short-text-path parity) but
  not settled here.
- **`wrMarquee` debug var** — should it report `period`/`sepPx` once those exist, for the same
  observability reasons TASK-390 added the existing fields? Cheap to add alongside the
  implementation; not core to the design.
- **Interaction with `M-WR-CONNECT-ASYNC` (TASK-398, in progress)** — that design's WebRadio
  connect-state work touches `_tickMarquee()`'s caller (`webRadioApp.h` tick path) but not
  `_tickMarquee()`/`drawTitleText()` themselves; no ordering dependency identified, flagged only
  because both land in the same file around the same time.

## Exit criteria

- DUT: a title/station string wider than `TITLE_W` scrolls endlessly — tail of one pass and
  head of the next both visible mid-transition, shuriken separator between them, no blank hold
  between passes.
- DUT: a short title/station string (`textPx <= TITLE_W`) behaves exactly as today — static,
  no separator, no motion.
- DUT: WiFi-down override strings (`"WI-FI: RECONNECTING..."` et al, all short) unaffected —
  render identically to current behavior.
- No DRAM/BSS regression vs current build (`run/check` gate; `.dram0.bss` budget per
  `M-MEMBUDGET-memory-budget.md`).
- `wrMarquee` debug var still returns valid data for the extended state.
