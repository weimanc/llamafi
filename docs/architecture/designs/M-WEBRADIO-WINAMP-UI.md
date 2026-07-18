# Design — M-WEBRADIO-WINAMP-UI: skin-native country/time/vis in radio mode

> Owner: Architect
> Status: scheduled — designed 2026-07-18 (human request, 4 items), filed as
> TASK-348/349/350 + PROP-005 (RnD). No ADR needed for items 1–3 (pure use of
> existing skin surfaces); item 4's outcome may amend ADR-009.
> Deps: M-WEBRADIO (shipped), ADR-018 (PLEDIT chrome), ADR-009 (synthetic VU),
> M-VIS (vis tap cycle), TASK-278 (pump-task read discipline)

## Intent (human, 2026-07-18)

WebRadio mode should stop drawing ad-hoc overlays on top of the Winamp skin
and use the skin's own UI elements instead:

1. Country code moves off its superimposed badge into the **PLEDIT bottom
   bar** (the strip that holds Spotify's total-playlist-time readout).
2. The main-window **time digits** — unused in radio mode — show current
   stream play time.
3. The **visualizer** area — dead in radio mode — reuses the existing
   Spotify synthetic vis (explicitly kept mock for now).
4. An **RnD activity** is registered to explore real visualization from the
   WebRadio audio stream (→ PROP-005; separate doc, rnd branch).

## Item 1 — country code into the PLEDIT bottom bar (TASK-348)

**Today:** `webRadioApp.h` draws a badge at `WR_BADGE_X/Y` (241,10 — over the
bitrate-legend area): a `fillRect` + centred text (`:1556`). It's the last
non-skin overlay in radio mode.

**Change:** WebRadio's `_drawPledit()` already calls the shared
`drawPleditFrame()` (ADR-018), which paints the bottom bar from the
`SKIN_PLEDIT_BG` atlas and leaves the overlay slot to the app — exactly where
Spotify blits its total-time with `SKIN_GLYPH` (`winampDisplay.h:1287`:
`x = originX + 127 + GLYPH_W`, `y = PLEDIT_BOTTOM_Y + 10`). Render the
country code there with the same glyph blit (e.g. `NL`; optionally
`NL <stationCount>` — decide at implementation, keep it short: the slot fits
Spotify's `H:MM:SS`, so ≤ 8 glyphs). Delete the badge draw + the
`WR_BADGE_*` constants, and update `preview_webradio.py`'s zone map (the
constants' comment says it mirrors them — check it parses rather than
mirrors, LL-114).

Repaint triggers: country changes only via settings edit → the existing
resume-diff / station-refetch path already repaints PLEDIT; no new dirty
tracking needed. Bottom bar redraw is part of `drawPleditFrame` — re-blit the
overlay after every frame draw, same as Spotify does.

## Item 2 — wire stream play time to the main-window digits (TASK-349)

**Today:** `drawTimeDigits()` (`winampDisplay.h:1033`, MM:SS from
`SKIN_NUMBERS`, self-guarded against no-change repaints) is never called in
radio mode — the digits sit at whatever Spotify last drew or the boot state.

**Source of truth:** the vendored audioI2S `Audio` object exposes
`getAudioCurrentTime()` (seconds of decoded stream). The audio object lives
on the pump task — **UI-side reads must follow the TASK-278 discipline**:
short timeout-take (`WR_PUMP_READ_TIMEOUT_TICKS`) like the existing per-tick
`inBufferFilled`/`isRunning` reads. Extend that existing per-tick read block
with one `getAudioCurrentTime()` call — do not add a second mutex touchpoint.
On take-timeout, skip the update (digits hold; same degrade-gracefully rule
as the buffer gauge).

Semantics: reset to 0:00 on station change/stop (STOPPED state draws 0:00
once); freeze during rebuffer (the lib's counter stalls with decode, which is
honest). Overflow: `drawTimeDigits` clamps at 99:59 — for a radio stream
that's ~1.7 h and then pins. **Wrap instead: pass `seconds % 6000`** so the
digits stay live on long sessions; note the wrap in a comment (classic 4-digit
MM:SS has no better answer and H:MM would need a different blit layout — not
worth it).

Repaint cost: one guarded call per UI tick, 4 sprite blits at most 1×/second.

## Item 3 — reuse the synthetic visualizer in radio mode (TASK-350)

**Today:** `vu::tick()` is called only from the Spotify app's tick
(`main.cpp:243`); the vis area in radio mode is static `MAIN_BG`. Blocker:
`vu::tick()` **internally** grabs `spotifyTask::copySnapshot()` and
`songStartMillis` to derive `playing`/`elapsed` (`vuMeter.h:368-378`) — it is
hard-coupled to Spotify state and would render a dead vis (or worse, dance to
a stale Spotify snapshot) if simply called from WebRadio.

**Change — decouple the data feed, keep the synthesis:**

- Refactor the entry point to `vu::tick(originX, originY, mainBg, playing,
  elapsedMs)`; move the snapshot read into a thin Spotify-side wrapper (or
  the call site at `main.cpp:243`) so the Spotify path is byte-identical in
  behaviour.
- WebRadio's tick calls it with `playing = (_state == PLAYING)` and
  `elapsedMs` from the item-2 time source (seconds×1000 is fine — the
  envelope's beat oscillators don't need sub-second phase accuracy from us).
- **Everything downstream stays mock** (ADR-009 synthesis: swell + noise +
  dual beat oscillators). Explicit human instruction: keep it mock for now.
- Mode state (`vu::currentMode()`, atlas frame counters) is global — the
  chosen mode carries across the Spotify↔Radio eject toggle for free. Vis
  tap-to-cycle: the hit zone lives in the Winamp touch path; if WebRadio's
  `handleInput` doesn't already fall through to it, route a tap in the vis
  rect to `vu::nextMode()` — small, and the M-VIS zone geometry is already
  in `vuMeter.h`.
- `get visMode` (`main.cpp:3050`) works unchanged — same global.

Interaction with item 2: both read pump-task state each tick; keep them in
the same read block (one take, both values out).

## Item 4 — RnD: real visualization from the radio stream (PROP-005)

Registered as **PROP-005** (`docs/rnd/proposals/PROP-005-webradio-real-vis.md`)
— see that doc. Framing note that belongs here: ADR-009 chose *synthetic*
vis because the Spotify path has no local audio — **WebRadio invalidates
that premise**: real PCM is decoded on-device on the pump task. Whether
there's CPU/heap headroom to derive levels (envelope, bands, or FFT-lite)
inside the no-PSRAM budget and TASK-278's decode-tail constraints is exactly
the open question, hence RnD on an `rnd/` branch, not a production task.
Items 1–3 do not depend on it; item 3's refactor (caller-supplied
levels seam) is deliberately the interface PROP-005 would feed real data
into.

## Verification sketch (VE to own)

- **T_WRUI_01 (DUT):** country code renders in the PLEDIT bottom bar with
  skin glyphs; the old badge area shows untouched skin background; settings
  country edit → bottom bar updates after refetch.
- **T_WRUI_02 (DUT):** play a station ≥ 65 s — digits advance 0:00 → 1:0x;
  station skip resets to 0:00; stop shows 0:00.
- **T_WRUI_03 (DUT):** vis animates while PLAYING, decays to idle on STOP
  (envelope's `!playing` decay); `get visMode` cycles in radio mode; eject
  back to Spotify → vis unaffected (wrapper regression check).
- Eyeball (BP-048): one screendump pass of the radio main window — digits,
  bottom bar, vis all skin-correct.
- Host: `preview_webradio.py` zone map updated; `run/check` full pass.

## Effort / risk

Items 1–2 small. Item 3 medium-small (the refactor touches the Spotify path —
the wrapper must keep it behaviourally identical; T_WRUI_03's eject leg is
the guard). Risk concentrates in pump-task read discipline (mitigated: reuse
the existing timeout-take block, one take per tick) and in vis-tap routing
inside WebRadio's input handler (fallback: ship without tap-cycle in radio
mode, inherit whatever mode Spotify last set — still meets the ask).
