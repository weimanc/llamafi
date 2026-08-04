# Design — WebRadio on-device diagnostic surfacing (marquee/title-zone insight)

> Owner: Architect
> Status: draft
> Date: 2026-08-04
> Feeds: —
> Tracked-as: —
> Registers: —

## Context / pain points

During the TASK-393 Spotify-present soak (2026-08-04, same day), the human watched the physical
Winamp/WebRadio screen show a static **"Station unreachable"** for 25+ minutes straight with no
way to tell, from the device alone: whether it was about to retry, how long it had been stuck, or
what kind of failure this was. Every diagnostic step that followed — checking `render_age`
lockstep with `uptime`, grepping the raw serial log for `connect_fail`/`terminal retry` cadence,
reading `Audio.cpp` source to understand `m_f_ssl`/timeout behavior, host-side `curl`/`dig`
probes — happened entirely off-device, through a laptop with a live serial connection or a
separate host machine. None of it was visible on the LCD itself.

This is not a new pattern for this project. `webRadioApp.h:1789-1817`'s `_drawTitleZone()`
already sets a **static string per `WRPlayState`** ("Connecting...", "Station unreachable",
"Stream stalled", "WiFi lost", "Station blocked") once on state entry and never updates it again
until the state changes — even though the underlying retry mechanism (`WR_TERMINAL_RETRY_MS`,
`webRadioApp.h:623-634`) is actively ticking the whole time. There's already one precedent for
promoting an internal diagnostic value into that same marquee: **TASK-362** made the
empty-station-list case surface `_lastHttpCode` (200 / -100 / -101 / -102 / raw HTTP code)
instead of an undifferentiated blank "No stations" — proof this pattern is accepted practice for
one specific case, just never generalized.

Human's explicit framing (important, keep this literal): *"I don't want to be reactive and add an
item because of my bad UX"* — i.e. don't cherry-pick "expose DNS timing" just because tonight's
specific investigation needed it. The ask is for a deliberate, evidence-based set of on-screen
diagnostic surfacing, and — the open question this doc exists to carry — **a repeatable method
for finding the rest of that set**, not a one-off list assembled from memory.

## Goals

1. A human looking at the physical LCD during a connectivity problem should be able to tell,
   without a laptop: is it about to retry, how long has it been stuck, roughly what class of
   failure. (Directly answers tonight's actual frustration.)
2. Avoid marquee/title-zone clutter — it's a single scrolling LED-font line shared with the
   track-title display during normal PLAYING; screen real estate is precious and this device's
   existing UI conventions (main-digits, PLEDIT bottom bar, taskbar) are already claimed for other
   purposes.
3. Establish a **non-reactive, evidence-based method** for deciding what else is worth surfacing —
   not a list frozen at tonight's specific bug hunt.

## Design space (options + tradeoffs)

Candidate signals, triaged into three tiers by cost and generality:

**Tier 1 — cheap, data already exists in RAM, no new firmware capability needed:**
- **Retry countdown** ("unreachable, retrying in 12s") while parked in an `ERROR_*` state —
  `WR_TERMINAL_RETRY_MS` minus elapsed is already computed for the retry logic itself
  (`webRadioApp.h:623-634`), just never surfaced to the display.
- **Consecutive-failure counter** ("attempt #4") — distinguishes "just started failing" from
  "been failing 20 minutes" at a glance. Needs a small dedicated counter (existing
  `_autoSkipTried` resets under the single-station condition this soak tooling deliberately
  exercises, so it's not directly reusable as-is — a new field, but a cheap one).
- *Tradeoff:* generically useful for **any** future connectivity flakiness episode, not just
  tonight's station — this is the "boring, obviously-right" tier.

**Tier 2 — valuable, needs new instrumentation (moderate firmware work):**
- **Finer-grained failure reason** — today "Station unreachable" covers DNS failure, TCP-connect
  failure, and a non-200 HTTP response identically. Splitting these apart (the exact distinction
  chased, and not resolved, during tonight's live investigation) requires threading a reason code
  out of the *vendored* `ESP32-audioI2S` `Audio::connecttohost()` path, which doesn't currently
  expose that split — see `app/lib/ESP32-audioI2S/src/Audio.cpp:517-557` and the confirmed-unbound
  DNS-resolve gap in `framework-arduinoespressif32/.../WiFiClient.cpp:302-309` (`hostByName()` has
  no timeout at all; only the subsequent raw-IP `connect()` gets the requested budget).
- *Tradeoff:* this is the tier that's tempting to add **because of tonight specifically**. Real
  value, but touches vendored library code (this project generally avoids patching vendored
  files) and needs its own justification independent of one investigation, not fast-tracked on
  tonight's momentum.

**Tier 3 — real signal, wrong medium — reject for the marquee:**
- Raw DNS-vs-TCP-connect timing split, heap figures, RSSI, raw error codes. Technical enough that
  putting them on the always-visible single-line marquee would clutter it for every user, for
  benefit that only matters during active debugging. Already have a home: the existing debug-shell
  `get` vars (e.g. `get wrState`, `get heap`, `get wrLastHttp`), or a future dedicated diagnostics
  view if screen space is ever allocated for one.

## Lean / decision

**Tier 1 only, for now.** It's the tier that's actually non-reactive — useful for whatever the
*next* connectivity episode looks like, not shaped around tonight's specific mystery. Tier 2 is
real but should wait for its own justification (see Open Questions — the triage method below is
exactly how that justification should be built, rather than assumed). Tier 3 stays off the
marquee entirely; no design change needed there, it's already served by existing debug-shell vars.

This is a **draft lean, not an accepted decision** — needs human sign-off before promotion to an
ADR, per standard process.

## Open questions

**The human's own framing, carried verbatim:** *"I don't know if we can [get] a more exhaustive
list of items that are worth showing. I don't want to be reactive and add an item because of my
bad UX. ... Could we triage some of the debug logs?"*

This is the actual open question this design doc exists to hold, and it deserves a real answer
attempt, not just a restatement. Three concrete, evidence-based triage methods, in increasing
order of effort:

1. **Static frequency audit of `LOG_W`/`LOG_E` call sites.** Every `LOG_W(...)`/`LOG_E(...)` in
   `webRadioApp.h` (and the WebRadio leg of `dataTaskStorage.cpp`) represents a moment the
   developer, at the time, judged notable enough to flag above `LOG_I`. Grep them all, then
   cross-reference against how often each one actually fires in the raw logs this project already
   has on disk (tonight's two 4h-class soak raw logs, TASK-391's host-tool output, any
   `run/test`/`run/wr-soak` captures under `app/tools/rnd_logs/`). A call site that fires
   constantly in real captured sessions is a stronger promotion candidate than one that's never
   once appeared outside a synthetic test — this replaces "what do I remember mattering" with "what
   the actual log corpus shows happens."
2. **Grep `tasks.md` itself for diagnostic-gap language.** This project's own task history already
   contains an implicit, scattered wishlist: TASK-390's own "no debug getter for `WinampDisplay`'s
   marquee state" note, TASK-393's "further tracing needs... an instrumented build," TASK-385's
   "isolated rerun couldn't reproduce the real failure mode" line, tonight's own back-and-forth —
   all examples of "we wished we could see X on the device and couldn't." A single grep pass for
   phrases like *"no visibility into," "couldn't tell," "no debug getter for," "instrumented
   build"* across `tasks.md` would surface this systematically instead of relying on memory of
   which sessions hit which walls.
3. **`get`-var query-frequency audit.** The debug shell's existing `get` variables
   (`dbgGet`/`dbgSet` handlers scattered across `webRadioApp.h`, `spotifyTaskStorage.cpp`, etc.)
   already represent "a developer decided this was worth exposing, at least to the debug shell."
   Grepping this project's own investigation tool output (`app/tools/rnd_logs/`, `run/test*`
   scripts, and this session's own soak logs) for which `get <var>` commands actually get issued
   *during live debugging*, and how often, would rank the existing debug-only surface by
   real demonstrated need — the ones queried most often during real incidents are the strongest
   candidates for promotion from "debug-shell-only" to "always-visible."

None of these three have been run yet — they're proposed methods, not completed triage. Whoever
picks this design doc up next should run at least #1 and #2 (cheap, static, no DUT time) before
expanding past Tier 1, so any future Tier-2-or-beyond addition is justified by the log/task-history
evidence, not by whichever bug happened to be live that week.

**Cross-cutting note for whoever implements Tier 1 (flagging now since it's non-obvious):** a live
retry countdown requires setting `_dirty = true` on a periodic tick *while parked in an `ERROR_*`
state* — which is exactly the condition TASK-393's whole render-freeze investigation is about
(`webRadioApp.h`'s `tick()` only repaints on `_dirty`, and today nothing sets `_dirty` again once
parked in an error state until the next state transition). Implementing Tier 1 as designed would,
as a side effect, force a periodic repaint while parked — which either (a) is a fine, even
desirable UX improvement that happens to also eliminate the *visible symptom* of a TASK-393-style
freeze going forward, or (b) risks masking a real underlying stuck-condition rather than actually
fixing it, if the developer isn't careful to keep the repaint itself lightweight and unconditional
on whatever caused the freeze in the first place. Whoever implements this should read TASK-393's
full entry in `tasks.md` before touching `_drawTitleZone()`/`tick()`, and should treat "the freeze
symptom stopped reproducing after this landed" with real suspicion rather than as confirmation
TASK-393 is fixed.

## Exit criteria

- Triage methods #1 and #2 above run at least once, with results written back into this doc (or a
  follow-up), before any Tier 2 work is scheduled.
- Human review of the Tier 1 lean — confirm scope (just retry-countdown + failure-counter) before
  a Developer implements against this doc.
- If accepted, `Registers:` gets filled in with a feature-id + any `cross_feature_matrix.yaml`
  edges (at minimum, an edge against TASK-393's render-freeze mechanism, per the cross-cutting
  note above) before implementation starts, per standard Architect registration discipline.
- VE should be looped in before implementation lands, specifically on the `_dirty`/repaint-cadence
  question above — this is exactly the kind of testability challenge VE is supposed to raise
  before code, not after.
