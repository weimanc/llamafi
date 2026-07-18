# Design — M-WEBRADIO-WINAMP-UI: skin-native country/time/vis in radio mode

> Owner: Architect
> Status: scheduled — designed 2026-07-18 (human request, 4 items; item 5
> volume slider added same day), filed as TASK-348/349/350/352 + PROP-005
> (RnD). No ADR needed for items 1–3/5 (pure use of existing skin surfaces);
> item 4's outcome may amend ADR-009.
> Deps: M-WEBRADIO (shipped), ADR-018 (PLEDIT chrome), ADR-009 (synthetic VU),
> M-VIS (vis tap cycle), TASK-278 (pump-task read discipline), ADR-035 /
> M-TOUCH-CAPTURE (slider capture prior art), TASK-224 (volume ceiling)

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
5. The main-window **volume slider** — Spotify-only today — controls WebRadio
   volume, with the existing capture/render machinery reused, not duplicated.

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

## Item 5 — volume slider wired for WebRadio (TASK-352)

**Today:** the slider is fully built and Spotify-only. `drawVolume(pct)`
(28-keyframe VOLUME.BMP + knob, self-guarded) plus a complete drag gesture in
`winampDisplay`'s `D_VOLUME_DRAG` state: capture, `volumeFromX()`, debounced
mid-drag commits (`VOLUME_DRAG_DEBOUNCE_MS`), drag-end commit, optimistic
hold (`optimisticVolumeUntilMs`), background-blit restore (`:153-156`).
WebRadio has **no interactive volume at all** — `wrEffectiveVolume()` is a
static ceiling (settings `webRadioMaxVolume` 1–21, soft-capped at 12 stock /
21 with the HW mod, TASK-209/224) applied once per play.

**Reuse analysis — what's shared vs. what's Spotify-coupled:**

- Renderer, gesture state machine, debounce, optimistic hold: mode-agnostic
  (operate in 0–100 pct). Reuse as-is.
- The coupling is exactly **two hard-coded
  `spotifyTask::enqueue(ACT_VOLUME, pct)` calls** (mid-drag `:381`, drag-end
  `:361`). That is the seam.

**Change — cut a volume sink seam, one state machine for both modes:**

1. Replace the two enqueue calls with a `volumeSink(int pct)` indirection
   (function pointer or small interface on `winampDisplay`, same shape as the
   item-3 vu:: seam). Spotify wires the existing `ACT_VOLUME` enqueue —
   behaviourally identical, same debounce cadence.
2. WebRadio wires a sink that maps pct → hardware steps:
   `vol = (pct * wrEffectiveVolume() + 50) / 100` — **the ceiling stays the
   ceiling**; the slider scales *within* the safe range, so the TASK-209
   HW-mod clamp and T_WR_VOL_03 semantics are untouched. Apply via the
   sanctioned control-call pattern (`s_wrAudioMutex` take →
   `s_wr_audio->setVolume()` → give — the `:321` idiom; `setVolume` is
   already on the `:162` sanctioned-control-calls list). Mutex take in the
   sink must be short-timeout, not `portMAX_DELAY` — a drag must never block
   the UI task behind a busy pump (skip the step; the debounced next commit
   lands it).
3. Gesture routing: WebRadio's input path uses piecemeal `hitTest*Public`
   calls, not `checkForInput` — expose the volume gesture as a public
   capture entry (hit-test + Press/Move/Release forwarding into the same
   `D_VOLUME_DRAG` machine) rather than duplicating the state machine in
   `webRadioApp.h`. ADR-035/M-TOUCH-CAPTURE is the pattern reference.
4. State: new `webRadioVolumePct` (0–100, default 100 = current behaviour:
   full ceiling). Persist coalesced-on-suspend iff changed — the
   `lastStation` idiom (ADR-050 rule 3). **ADR-050 static gate applies**: the
   new AppSettings field needs load()+save()+runtime consumer or `run/check`
   step 7 flags it. Applied at `_play()` (replacing the bare
   `wrEffectiveVolume()` call) and on slider commit.
5. Eject transitions: entering radio mode `drawVolume(webRadioVolumePct)`;
   returning to Spotify, the existing snapshot-driven redraw restores the
   Spotify pct. The `:153-156` background-blit restore re-renders
   `lastVolumeRendered` and is mode-correct for free once each mode seeds it
   on entry.

Settings interaction, stated explicitly: `webRadioMaxVolume` (settings
slider) remains the *ceiling*; the Winamp slider is the *session volume
within it*. Raising the ceiling later does not retroactively boost a
persisted 100% session — pct is relative, re-derived per commit.

## Verification sketch (VE to own)

- **T_WRUI_01 (DUT):** country code renders in the PLEDIT bottom bar with
  skin glyphs; the old badge area shows untouched skin background; settings
  country edit → bottom bar updates after refetch.
- **T_WRUI_02 (DUT):** play a station ≥ 65 s — digits advance 0:00 → 1:0x;
  station skip resets to 0:00; stop shows 0:00.
- **T_WRUI_03 (DUT):** vis animates while PLAYING, decays to idle on STOP
  (envelope's `!playing` decay); `get visMode` cycles in radio mode; eject
  back to Spotify → vis unaffected (wrapper regression check).
- **T_WRUI_04 (DUT):** volume drag in radio mode — knob tracks, audible level
  changes (or `get wrVolume` confirms the mapped step), value survives
  suspend/resume (coalesced save), and `webRadioMaxVolume` ceiling is never
  exceeded (extend T_WR_VOL_03's clamp assertions to the pct mapping).
  Eject leg: Spotify slider still enqueues ACT_VOLUME with identical
  debounce (regression on the sink seam).
- Eyeball (BP-048): one screendump pass of the radio main window — digits,
  bottom bar, vis, volume knob all skin-correct.
- Host: `preview_webradio.py` zone map updated; `run/check` full pass
  (incl. step-7 settings-wiring gate for `webRadioVolumePct`).

## Effort / risk

Items 1–2 small. Items 3 and 5 medium-small — both are the same move
(cut a Spotify-coupled seam, keep the Spotify path behaviourally identical)
and both carry an eject regression leg as the guard (T_WRUI_03 / _04).
Risk concentrates in pump-task discipline (item 2/3: reuse the existing
timeout-take read block; item 5: short-timeout mutex take in the volume
sink, never portMAX_DELAY from the UI task) and in gesture routing inside
WebRadio's piecemeal input path (item 3 fallback: ship without tap-cycle;
item 5 has no fallback — the capture-entry exposure is the deliverable,
duplicating the drag state machine is explicitly out per the reuse
instruction).
