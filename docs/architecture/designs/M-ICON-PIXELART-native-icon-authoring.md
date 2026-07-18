# Design — Native pixel-art icon authoring at taskbar slot resolution

> Owner: Architect
> Status: decided — see ADR-051 (2026-07-18: 36×36 budget, Option B, warn-only fill check)
> Date: 2026-07-12 (decided 2026-07-18)
> Feeds: [ADR-051](../decisions/ADR-051.md)
> Tracked-as: roadmap M-ICON-PIXELART (PM to file implementation tasks)

## Context / pain points

`gen_taskbar_icons.py` (M-TASKBAR-ICONS, done 2026-06-12) unconditionally
resizes whatever source PNG sits in `app/icons/taskbar/<app>.png` /
`<app>_active.png` down to `TASKBAR_ICON_W` x `TASKBAR_ICON_H` — currently
24x24, read at bake time from `gen/shell_layout.h` — via
`Image.resize((w, h), Image.LANCZOS)`, regardless of the source file's own
resolution. That resolution varies wildly across the existing set: 20x20 was
the original M-TASKBAR-ICONS spec, but shipped files range from 32x32
(`clock.png`, `weather.png`, `stock.png`, `teletext.png`) up to 256x256
(`spotify_active.png`, the imported Winamp bolt logo).

This surfaced as a real, repeated point of confusion while redesigning the
PlaneRadar taskbar icon this session (TASK-302's follow-up):

1. **Scaling a shape and its frame together is invisible post-bake.** An
   early pass grew the ring radius by 30% and grew the canvas/margin by the
   same 30%, reasoning that "the rest has to scale too." Because only the
   *ratio* of ring-radius to canvas-size survives the resize-to-24 step,
   this was a mathematical no-op — the baked icon came out pixel-identical
   to the original. Diagnosed only by measuring the true post-bake bbox
   fill ratio directly, not by reasoning about the source-canvas geometry.

2. **Double-resampling compounds unpredictably.** The subsequent fix drew at
   an intermediate 44x44 canvas (10x supersampled internally for
   antialiasing, then LANCZOS'd down to 44x44) targeting a measured ~93%
   fill ratio *at that intermediate size*. `gen_taskbar_icons.py`'s own
   44→24 LANCZOS resize then pushed the **true** baked fill to 100% —
   edge-to-edge, more than intended, because two successive LANCZOS passes
   don't preserve a fill fraction linearly (ringing/overshoot at each
   resample step). The only way to know the real number was to resize to
   24x24 and measure again.

3. **The 24x24 budget is fixed but invisible to whoever's drawing.** The
   taskbar slot is 45x40 (`TASKBAR_W` x `TASKBAR_SLOT_H`), icon glyph
   centred within it at a hardcoded 24x24 (`iconOffX`/`iconOffY` in
   `taskbar.h`). Nothing in the authoring workflow surfaces that budget
   up front — you find out only by baking and measuring, after the fact.

4. **The 24x24 budget itself is a self-imposed constant, not a hardware
   limit — and it leaves real estate on the table.** The taskbar slot is
   45x40 (`TASKBAR_W` x `TASKBAR_SLOT_H`); the icon glyph is centred at a
   hardcoded 24x24 within it. That's only **53% of the slot's width and
   60% of its height** — margins of ~10.5px each side horizontally, ~8px
   each side vertically. Nothing about the display or the taskbar's
   separator lines requires that much margin; `TASKBAR_ICON_W`/`_H` is just
   a `#define`. Points 1-3 above were all about faithfully hitting a
   24x24 target — but 24x24 may itself be an under-sized target that
   should be revisited as part of the same change, not just re-hit more
   precisely. Human observation (this session): this is the more
   fundamental point, and arguably should be resolved before the
   authoring-workflow question in points 1-3 (a bigger budget changes how
   much detail a redesigned icon like PlaneRadar's can actually carry).

5. **No documented fill-ratio convention — every icon's is an accident.**
   Measured at the *true* 24x24 baked resolution (bbox of alpha>128 ÷ 24),
   this session:

   | icon | fill (w × h) |
   |---|---|
   | planeradar (as shipped this session) | 100% × 100% |
   | crypto | 96% × 96% |
   | spotify_active | 92% × 92% |
   | clock / teletext | 83% × 83% |
   | weather | 83% × 79% |
   | stock | 83% × 50% |
   | aquarium | 100% × 29% (wide flat glyph) |

   There's no stated target here (crypto's 96% is the closest thing to a de
   facto norm) and no bake-time check comparable to the existing
   `TASKBAR_ICON_COUNT == TASKBAR_APP_COUNT` static_assert gate that would
   catch an icon landing wildly outside it.

## Goals

Per human direction this session: reduce/remove reliance on scaling
arbitrary-resolution source art down to the taskbar's fixed budget. Author
icons — at least hand-drawn/programmatic ones — as pixel art **directly at**
the taskbar's actual resolution, treating the fixed slot as a first-class
input to the icon's design, not an incidental resize target discovered after
the fact.

That "actual resolution" is itself in scope, not assumed to be 24x24: pain
point 4 above means this design should first ask whether `TASKBAR_ICON_W`/
`_H` should grow to use more of the 45x40 slot (e.g. something in the
~36-38 px range, leaving a small deliberate margin rather than the current
~10px/~8px), and only then have icons authored natively at whatever that
resolved size turns out to be.

## Design space (options + tradeoffs)

**Option A — status quo.** Keep arbitrary-resolution sources + bake-time
LANCZOS resize (current M-TASKBAR-ICONS pipeline), unchanged.
- *Pro:* zero migration cost; correct approach for imported/licensed art
  (Material Symbols, the Winamp bolt) that legitimately originates at a
  different resolution and benefits from a high-res master if
  `TASKBAR_ICON_W/H` ever changes.
- *Con:* exactly the pain above, for every hand-authored/programmatic icon
  going forward.

**Option B — native resolution for hand-authored icons only.** Programmatic
generators (`gen_icon_drafts.py` and any future icon-drawing tooling) render
directly at `TASKBAR_ICON_W` x `TASKBAR_ICON_H`, read from `shell_layout.h`
rather than hardcoded, so the saved PNG *is* what ships — the bake step
becomes a pass-through for these files. Imported art keeps its own
resolution and the existing resize path. Two authoring paths coexist, but
the pixel-art one becomes WYSIWYG.
- *Pro:* fixes the actual pain point with minimal disruption — no existing
  file needs to change.
- *Con:* two conventions to remember; a future contributor could still
  reintroduce an oversized programmatic source without realizing why.

**Option C — uniform native resolution for all taskbar icons.** Re-fit
every source PNG (including `spotify_active.png`) to exactly
`TASKBAR_ICON_W` x `TASKBAR_ICON_H` once, check that in, and make
`gen_taskbar_icons.py`'s resize step assert source dimensions match exactly
(fail loudly on drift) instead of silently resizing.
- *Pro:* maximum consistency; eliminates the indirection and this whole
  class of bug permanently; turns "did the source drift from the baked
  size" into a build-time check.
- *Con:* one-time cost to re-touch every existing icon (fine detail in e.g.
  the Winamp bolt's diagonal bolt shape may not survive a hard shrink to
  24x24 cleanly and could need manual cleanup); loses the "keep a high-res
  master, regenerate for free if the slot size ever grows" resilience
  Option A/current pipeline provides.

**Cross-cutting, independent of A/B/C:**

- **Grow `TASKBAR_ICON_W`/`_H` itself.** Currently 24x24 inside a 45x40
  slot — 53%/60% fill of available space, ~10.5px/~8px margin each side,
  self-imposed rather than display- or separator-driven. The centering math
  in `taskbar.h` (`iconOffX`/`iconOffY`) already derives from these
  constants, so growing them doesn't need new layout code — but it DOES
  mean every existing baked icon gets bigger too (not just a re-authored
  PlaneRadar), since `gen_taskbar_icons.py` resizes whatever source exists
  to the new target. A source that's already smallish relative to the new
  target (e.g. a 32x32 file resized up to 38x38) will look softer, not
  crisper — reinforcing Option C's re-touch-everything case if this is
  taken. Also unverified: whether `run/check`'s golden-hash gate covers
  taskbar icon output (it's confirmed to cover the skin bake,
  `app/gen/skin_assets.c` — needs checking for `taskbar_icons.c`) and would
  need updating either way.
- Whether to codify a fill-ratio convention (target %, ± tolerance) and add
  a bake-time check for it, analogous to the existing icon-count
  static_assert. Would turn "was this too big/small" from an
  eyeball-and-remeasure loop into a repeatable gate.

These two are logically prior to A/B/C: the authoring-workflow question
(how icons get to the target size) only matters once the target size itself
is settled.

## Lean

Not pre-decided — genuinely a case with real tradeoffs on both sides
(Option C's consistency vs. its one-time retouch cost and loss of
resize-on-demand resilience for imported art). Weak lean toward **Option
B** as the lower-disruption starting point — it directly fixes the
confusion this session hit without a flag day on every shipped icon — but
this is the human's call to make, particularly given the appetite for
Option C's stronger consistency guarantee.

## Open questions

- How much of the 45x40 slot should the icon actually claim — full 24x24 →
  ~36-38x~32-36 growth is on the table per the self-imposed-limitation
  point above. What margin is the human comfortable losing (currently
  ~10.5px/~8px each side)?
- Does `TASKBAR_ICON_W/H` (24x24) have any expected future change (bigger
  display, different DUT) that would make native-resolution assets lose
  the "regenerate from a bigger master for free" property Option A gives?
- Should imported/licensed art (Material Symbols per M-TASKBAR-ICONS's
  original sourcing note, the Winamp bolt) be exempted from a
  native-resolution requirement under Option C, or re-touched to match
  anyway for full uniformity?
- Is there an appetite for a documented fill-ratio target (crypto's 96% is
  the closest thing to a de facto standard today) with a bake-time
  warn/fail check, independent of which option is chosen for authoring?

## Resolution (2026-07-18)

Human decided all three gates in one pass (ADR-051):

- **Size: 36×36** (80%/90% of slot; 4px x-offset clears the 3px
  active-indicator bar, 2px y-offset clears the 1px separator).
- **Authoring: Option B** — native-resolution for hand-authored icons,
  bake becomes pass-through on exact dimension match; imported art keeps
  hi-res master + resize path.
- **Fill check: warn-only** — major-axis fill outside [85%, 97%] warns at
  bake; minor axis unchecked (wide-flat glyphs legal); never fails build.

Verified during decision prep: `golden.sha256` **does** cover
`taskbar_icons.cpp/h` and `shell_layout.h` (closes the "unverified" note
under cross-cutting) — size bump + re-bake need a golden regen.

## Exit criteria

- Human picks A / B / C (+ fill-ratio-check appetite); Architect records
  the decision as an ADR.
- If B or C: `gen_icon_drafts.py` (and any successor icon-authoring
  tooling) updated to target `TASKBAR_ICON_W`/`_H` natively, read from
  `shell_layout.h` rather than hardcoded.
- PlaneRadar's icon pair re-authored under the accepted approach as the
  first real test case (it's the icon that surfaced this whole design
  question).
