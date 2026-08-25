# Design — M-PLEDIT-ABSTRACTION: one playlist renderer behind a source interface

> Owner: Architect
> Status: accepted
> As-built: 2026-08-07 (ADR-059 signed off; implementation authorised)
> Date: 2026-08-07
> Parent: [M-WINAMP-PLAYER.md](M-WINAMP-PLAYER.md) (workstream 3 of 4)
> Feeds: ADR-059 D4
> Tracked-as: TASK-411, TASK-412
> Registers: `plmodel-001` · X054 · X055

**Standalone value: high, and independent of everything else in the parent milestone.** PLEDIT is
implemented twice today; the two copies have already diverged. Collapsing them pays for itself in
the current codebase — no SD card, no local playback, no new hardware required. This workstream can
land on its own schedule and should be judged on its own merits.

---

## 1. The duplication, concretely

| | `winamp/winampDisplay.h` | `webRadioApp.h` |
|---|---|---|
| Data source | `spotifyTask::copyQueueSnapshot()` | `_stations[]` |
| Change detection | `lastQueueSeqno` seqno-diff + `PLAYLIST_DRAW_MIN_MS` rate gate | `_pleditDirty` flag |
| Rows | `drawPlaylist()` — number, artist–title, ellipsis truncation, `M:SS` right-aligned | own row painter |
| Drag machine | `dragState` ∈ {`D_PLEDIT_SCROLL`, `D_PLEDIT_SCROLL_DIRECT`, …} | `_dragStartRow`, `_scrollAccum`, `_scrollVelocity` |
| Velocity model | TASK-277 / M-LIST-v4 | second implementation of the same model |
| Scroll thumb | synthetic `fillRect` over tiled `SKIN_PLEDIT_RIGHT_SIDE` | same maths, restated |
| Direct-scroll strip | `PLEDIT_CONTENT_X + PLEDIT_CONTENT_W … PLEDIT_W` | same geometry, restated |
| **Shared** | `touch/scrollTuning.h` (tuning constants only) | ← that is the entire overlap |

Both consume the same `gen/skin_layout.h` geometry constants and produce the same pixels from
different code. A third source would mean a third copy.

Note the shape of the existing workaround: `winampDisplay.h`'s `handleVolumeGesturePublic()` exists
solely because `handleWinampInput()` hit-tests "Spotify-only zones — transport/posbar-seek/PLEDIT/
shuffle/repeat" and WebRadio cannot call it. That comment is the duplication's root cause written
down in the source.

## 2. Design

### 2.1 The interface

```
// NOTE (DEV-4): no default member initialisers in these structs. Under -std=gnu++11 an NSDMI
// makes the struct a non-aggregate and brace-init at every call site stops compiling — the
// TASK-327 lesson (SButton et al, field-by-field assignment throughout).
struct PlRow { char text[64]; uint32_t durationSec; bool current; };

enum PlCap : uint8_t {
    CAP_PLAY = 1, CAP_REORDER = 2, CAP_REMOVE = 4, CAP_ADD = 8, CAP_SAVE = 16
};

struct PlaylistSource {
    virtual uint16_t count() = 0;
    virtual bool     row(uint16_t idx, PlRow& out) = 0;   // may block on SD
    virtual uint32_t seqno() = 0;
    virtual uint8_t  caps() = 0;
    virtual uint32_t totalSec() = 0;
    virtual void     onTap(uint16_t idx) = 0;
    virtual bool     move(uint16_t from, uint16_t to) { return false; }
    virtual bool     remove(uint16_t idx)             { return false; }
};
```

| Implementer | caps | backing |
|---|---|---|
| `SpotifyQueueSource` | `CAP_PLAY` | `copyQueueSnapshot()`, forwards the existing poll seqno |
| `StationListSource` | `CAP_PLAY` | WebRadio `_stations[]` |
| `LocalPlaylistSource` | all five | parent design's index model |

### 2.2 Invariants (draft IFC — promote at acceptance)

1. `row(idx, …)` is called only for `idx < count()` captured in the same repaint.
2. `seqno()` changes **iff** rendered content changes. The renderer's redraw gate depends on this and
   on nothing else. Read-only sources forward their poll seqno; mutable sources bump on mutation.
3. `row()` may block on SD but must return within the M-SDFS latency bar, and must **never** be
   called from the audio pump task.
4. A source that does not advertise a cap must never have the matching mutator called — the renderer
   *hides the control*, rather than relying on the default-false return.
5. Mutators are called only from loopTask, only outside an active drag.

*Error handling:* `row()` returning false renders `"— unreadable —"` and does not abort the repaint;
a read failure marks the source degraded, surfaced through the app's `hasError()`.

### 2.3 The renderer

`winamp/pleditView.h` owns the union of what the two copies do: chrome blit, row layout and
truncation, duration column, total-time bottom bar, synthetic thumb, velocity scroll, direct-scroll
strip, seqno-diff redraw gate.

## 3. Sequencing — the risk control

This is the most gesture-tuned code in the project (TASK-051b–f, TASK-277, M-LIST-v4). Three
separately-verified commits, in order:

| Step | Change | Gate |
|---|---|---|
| TASK-411 | Extract renderer; `winampDisplay.h` delegates. WebRadio untouched. | pixel-identical for Spotify |
| TASK-412 | Delete WebRadio's copy; wire `StationListSource`. | T277-family scroll suite + **LCD eyeball** (BP-048) |
| (parent) | `LocalPlaylistSource` + edit ops | parent design |

**Documented fallback:** if step 1 or 2 cannot be made pixel-identical, stop and give local playlists
their own third renderer. The duplication is worse, but shipped scroll behaviour is not traded for
deduplication.

The two copies have **diverged**. Merging them means picking one behaviour deliberately per
divergence — not silently inheriting whichever caller lands second. Enumerate the divergences before
writing the merged renderer; that enumeration is a deliverable of TASK-411, not an implementation
detail. That enumeration is the **Divergence log** below (`T_PLE_10` reviews it).

## Divergence log

> Recorded by the Developer during TASK-411 (2026-08-08), from
> `winampDisplay.h` (Spotify, `drawPlaylist()` / `handleWinampInput()` / `tickScroll()` /
> `updateScrollDirect()`) and `webRadioApp.h` (`_drawPledit()` / `handleInput()` / `_gestureEnd()` /
> `_tickScroll()` / `_updateScrollDirect()`) as they stood at commit `12697bd`.
>
> **TASK-411 adopted the Spotify behaviour for every row below, without exception** — that task's gate
> is Spotify pixel-identity, so any other choice would have failed it by construction. The "TASK-412
> disposition" column is the recommendation for the second caller, and is the part that still needs a
> decision. Nothing here has been applied to `webRadioApp.h`; it is untouched.

### The finding that governs the rest

`T_PLE_01` demands zero differing pixels for **Spotify**; `T_PLE_07` demands zero differing pixels for
**WebRadio**. Both are measured against each caller's own pre-extraction baseline. Together they say
that **no pixel-affecting divergence may be resolved by picking a winner** — a winner necessarily
changes the loser's pixels and fails one of the two gates.

So the divergences split cleanly, and TASK-412 must treat them as two different kinds of work:

- **Pixel-affecting divergences (D1–D10)** cannot be "resolved". They must become **per-source
  parameters** — a small style/format block the source supplies — or `T_PLE_07` fails. Deduplicating
  the *code* is still the win; the *pixels* stay per-caller by contract.
- **Behaviour-only divergences (D11–D22)** have no pixel consequence and can be resolved by choosing
  a winner. Most are cases where WebRadio's copy silently dropped something the donor had.

If TASK-412 would rather standardise the appearance than keep it, that is a legitimate product call —
but it is a **deliberate UI change to WebRadio**, and it must be taken as one: `T_PLE_07` gets
rewritten to describe the intended new pixels *before* the code changes, not relaxed afterwards to
accommodate them. Silently letting `T_PLE_07` slide is the failure mode this log exists to prevent.

### Pixel-affecting

| # | Spotify (`winampDisplay.h`) | WebRadio (`webRadioApp.h`) | TASK-411 | TASK-412 disposition |
|---|---|---|---|---|
| D1 | Row background: `PLEDIT_BG_NORMAL` (`0x0000`), `PLEDIT_BG_SELECTED` (`0x0018`) for the current row | `PLEDIT_BODY_BG` (`0x18E5`) for **every** row; the current row gets no background treatment | Spotify | **Parameterise.** Two background colours per source. Skin-authentic (PLEDIT.TXT) is Spotify's, but adopting it repaints every WebRadio row. |
| D2 | Row text starts at `PLEDIT_CONTENT_X + 3` (`TEXT_MARGIN`) | starts at `PLEDIT_CONTENT_X` (flush, no margin) | Spotify | **Parameterise** (`marginPx`). A 3 px shift on every WebRadio row otherwise. |
| D3 | Right column is a right-aligned `M:SS` duration, `TEXT_MARGIN` in from the content edge, in the row's `fg` | right-aligned bitrate `"%uk"` at the content edge (no margin), in a fixed dim `0x4208`, and only when `bitrate > 0` | Spotify | **Parameterise.** The renderer already takes `PlRow::durationSec`; WebRadio needs a per-row right-hand *string* + colour, not a duration. Cheapest form: widen `PlRow` with a short `rightText[8]` and let `durationSec` be one way to fill it. |
| D4 | Row text is `"N. Artist - Title"`, N session-relative (`songsSeen + idx + 1`) | station name only, no number | Spotify | **Already source-owned.** `PlRow::text` is composed by the source, so this needs no renderer change (resolved in TASK-411). |
| D5 | Ellipsis truncation to the remaining pixel budget | none — a long station name overruns the right column and is overdrawn by the bitrate | Spotify | **Adopt Spotify's** — but note it is pixel-affecting for any WebRadio row long enough to overrun today, so it belongs with the `T_PLE_07` rewrite, not with the "free" changes. |
| D6 | Empty slot (`idx >= count`) painted `TFT_BLACK` | painted `PLEDIT_BODY_BG`, same as a populated row | Spotify | Falls out of D1. |
| D7 | "current" = `idx == 0` (queue head), **plus** an 8 s optimistic highlight after a tap | "current" = `idx == _currentIdx` **and** `_state != STOPPED`; no optimistic highlight | Spotify | **Source-owned** (`PlRow::current`) for the definition. The optimistic highlight is renderer-side and WebRadio gains it — pixel-affecting for ~8 s after a tap only, and arguably a fix (WebRadio's tap has no feedback until the station connects). |
| D8 | Current-row foreground via `PLEDIT_FG_CURRENT` | hardcoded `0xFFFFU` literal | Spotify | Same value — code-level only, no pixel effect. Resolved by using the macro. |
| D9 | Text baseline `ry + (PLEDIT_ROW_H - 8) / 2` | `rowY + 2` | Spotify | Identical in effect (both 2). Coincidence, not agreement — worth stating so nobody "harmonises" one of them later. |
| D10 | Bottom-bar overlay = total playlist time (`M:SS` / `H:MM:SS`) | bottom-bar overlay = country code | Spotify | **Parameterise.** `totalSec()` is too narrow: it can only express a time. Prefer `overlayText(char*, int)` on the source, with the time formatter as the Spotify implementation. |

### Behaviour-only

| # | Spotify | WebRadio | TASK-411 | TASK-412 disposition |
|---|---|---|---|---|
| D11 | Redraw gate: seqno diff + `PLAYLIST_DRAW_MIN_MS` (1 Hz) rate cap + a separate scroll-dirty bypass | `_pleditDirty` bool, no rate cap, and suppressed entirely when the app's full-repaint `_dirty` is set | Spotify | **Adopt Spotify's.** This is the X055 gap `T_PLE_14` was written for: a bool has no way to express "changed twice", so the conversion has two distinct failure modes (missed repaint, repaint storm). The rate cap is the reason the counter in D12 exists. |
| D12 | `invalidatePlaylist()` clears the seqno sentinel **and** zeroes the rate limit, for callers that wiped the canvas | no equivalent; WebRadio relies on a whole-app `_dirty` repaint | Spotify | **Adopt Spotify's.** WebRadio's full-repaint path subsumes it today but will not once the renderer owns the gate. |
| D13 | On every consumed seqno change, `scrollOffset` resets to 0 (TASK-051f) | never auto-resets; instead `_scrollOffset` *follows* the current station so it stays visible | **Spotify (kept)** | **Keep both — this is a genuine product difference, not drift.** A refreshed Spotify queue is a new list (position 0 is meaningful); a refetched station list is the same list. Make it a source cap/flag rather than picking one. Getting this wrong is invisible in a screenshot and obvious in use. |
| D14 | PLEDIT drag shares one `dragState` enum with volume/posbar/taskbar | private `_wrs` enum, PLEDIT states only | View owns it; the host's enum keeps its other gestures | **Adopt the TASK-411 split.** One owner per gesture; the host asks `dragging()`. Note `dbgGet("dragState")` still reports `D_PLEDIT_SCROLL` / `D_PLEDIT_SCROLL_DIRECT` — the serial contract is unchanged, the strings are just derived now. |
| D15 | Tap index = **live** `scrollOffset + _dragStartRow` | tap index = **press-time** `_dragStartScrollOffset + _dragStartRow` | Spotify | **Adopt Spotify's.** Reachable only if the list scrolls during a gesture that still qualifies as a tap (`abs(dy) < 6 px`, `< 250 ms`) — rare but not impossible, since a seqno-driven reset can move the list under a stationary finger. The live offset is what the user is looking at. |
| D16 | Tap validity = `_dragStartRow < lastVisibleRows` (the count cached at the last repaint) | tap validity = `idx < _stationCount` (live count) | Spotify | **Adopt Spotify's** — the cached count is what was actually drawn, so it matches what the finger landed on. |
| D17 | Drag-end arms an inter-gesture cooldown: 300 ms tap / 150 ms scroll / 100 ms strip | no cooldown at all | Spotify | **Adopt Spotify's.** WebRadio's omission is a bug of the "never noticed" kind — it allows an immediate second gesture on release bounce. |
| D18 | Strip drag repaints the thumb immediately (`drawScrollThumbOnly()`) and marks dirty | marks `_pleditDirty` only; the thumb moves on the next full repaint | Spotify | **Adopt Spotify's.** Direct-scroll with a thumb that lags a full repaint is the "feel" half of `T_PLE_09`. |
| D19 | Velocity integrator writes `scrollOffset` and marks dirty on every non-zero step, even when the clamp makes it a no-op | only marks dirty when the offset actually changed | **Spotify (kept)** | **Adopt WebRadio's.** This is the one row where the second copy is strictly better: at the top/bottom limit Spotify repaints at the tick rate for no visual change. Deliberately **not** taken in TASK-411 — it is a repaint-count change, and `T_PLE_04` asserts on repaint counts. Do it in TASK-412 with the counter as evidence. |
| D20 | Row-drag anchor is unconditional (the zone is already limited to populated rows) | requires `_stationCount > 0` before anchoring | Spotify | Equivalent in effect (Spotify's zone height is `visibleRows * ROW_H`, i.e. zero when empty). Recorded so the guard is not re-added as a "fix". |
| D21 | one gesture path: anchored Press → Move → Release | **two** paths: the anchored gesture *and* a second, unanchored Release-only tap hit-test (`handleInput` rows branch) that re-derives the row from scratch | Spotify | **Adopt Spotify's**, but check `cmdTap` first: the unanchored path exists because `cmdTap` drives a Release with no prior Press. If the harness still does that, the path is test infrastructure and must be kept deliberately, not deleted by accident. |
| D23 | Flick feel: quick-swipe fallback applies `max(1, abs(dy) / PLEDIT_ROW_H)` rows from the press-time offset | same code, but reached through a different drag machine and repaint cadence (see D18) | Spotify (kept) | **Investigate before choosing.** Operator observation, 2026-08-09: *"Spotify's flick seems worse than WebRadio's PLEDIT implementation."* Both copies share the tuning constants, so if the flick genuinely feels different the cause is elsewhere — most likely D18 (WebRadio repaints the whole PLEDIT after a scroll step, Spotify blits only the thumb during a strip drag) or D19 (Spotify repaints at the clamp, WebRadio does not). This is **pre-existing**, not caused by TASK-411: the extraction reproduces Spotify's flick trajectory exactly (see the gesture battery in §7a). Worth resolving in TASK-412's favour of whichever actually feels better, rather than defaulting to the donor. |

| D22 | Tap dispatches **asynchronously** (`ACT_PLAY_URI` onto the Spotify task queue) and paints an optimistic highlight | tap calls `_play(idx)` **synchronously** on loopTask | Both, via `onTap()` | **Already resolved by the interface** — `PlaylistSource::onTap()` is the seam, and each source keeps its own dispatch discipline. |

### Not divergent (verified, recorded so it is not re-litigated)

Frame chrome (gutters, title bar, side tiles, scrollbar thumb, bottom bar) was **already** shared via
`drawPleditFrame()` (TASK-225), as was the bottom-bar overlay blit (TASK-348) and the whole gesture
*tuning* block (`touch/scrollTuning.h`, TASK-277). The velocity integrator, the tap/scroll
discrimination and the quick-swipe minimum-one-row fallback are line-for-line the same model in both
copies — they were a deliberate pattern copy, and they merged without a decision.

## 4. Adjacent reuse this unlocks

Extracting the renderer surfaces three helpers that are currently one-off or missing, and that three
new callers (browser rows, local PLEDIT rows, ID3 titles) will otherwise re-implement ad hoc:

| Helper | Today | Should be |
|---|---|---|
| Ellipsis truncation to a pixel budget | exactly one implementation, inline in `winampDisplay.h`'s Spotify row formatter | shared `textFit()` in `util/` |
| UTF-8 → renderable ASCII | **nothing anywhere** — the Spotify path has the latent bug today; M3U/ID3 makes it acute | shared transliterate-then-substitute helper |
| Row hit-testing | `touch/hitbox.h` already provides `Rect`/`hitTest`/`hitTestRow` | use it — both PLEDIT copies hand-roll the arithmetic |

`hitbox.h` already exists and is the right primitive; the PLEDIT copies predate it. Adopt it during
extraction rather than porting the hand-rolled bounds maths twice.

## 5. Open questions

- **OQ1** — `PlRow::text[64]` is a formatted row, so the source owns "Artist - Title" composition.
  Alternative: return fields and let the renderer compose. Fields are more flexible (the renderer
  could right-align artist separately) but push per-source formatting knowledge into the renderer.
  Lean: formatted string, because all three sources want the same format.
- **OQ2** — does `pleditView` own the scroll state, or does each app? Own it in the view; apps that
  suspend mid-drag call a single `resetDragState()` (both apps already do this, separately).
- **OQ3** — text encoding (shared with the parent design's OQ2): resolve before row rendering is
  written, since it changes `PlRow`'s contract.

## 6. Test & validation

Ids reserved in the `T_PLE_` family. The governing property is **pixel- and feel-identity**: this
workstream must be invisible to the user. Two of these tests cannot be run from serial and are
explicitly eyeball gates (BP-048).

### TASK-411 — extract renderer, Spotify caller only

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLE_01` | Spotify PLEDIT renders identically | **host** — `run/screendump` before/after, **diff scoped to the PLEDIT rect** (`PLEDIT_Y … PLEDIT_Y + PLEDIT_H`, full width) with **the visualiser disabled** (`vu::setMode(off)`) — VE-4 | zero differing pixels across ≥5 states: empty queue, 1 row, 5 rows, >5 rows scrolled mid-list, scrolled to end |
| `T_PLE_02` | Row formatting unchanged | host — screendump diff on a long "Artist - Title" | truncation point and ellipsis identical; duration column right-edge identical |
| `T_PLE_03` | Scroll thumb geometry unchanged | host — screendump diff at scrollOffset 0 / mid / max | thumb y and height identical at all three |
| `T_PLE_04` | Redraw gate unchanged | DUT serial — **`get pleditRepaints`** (new monotonic counter, ADR-059 D12 / VE-2 — the assertion had no observable signal before) sampled across a static queue and a seqno advance | counter does not advance while seqno is static; advances exactly once per seqno change; `PLAYLIST_DRAW_MIN_MS` rate gate still observed |
| `T_PLE_05` | Scroll **feel** unchanged | **DUT eyeball** — velocity drag, flick, direct-strip drag | indistinguishable from baseline to the operator; no new stickiness or overshoot |
| `T_PLE_06` | Tap-to-play still dispatches | DUT serial — tap each of 5 rows | `ACT_PLAY_URI` with the correct absolute index (`scrollOffset + row`) 5/5 |

### TASK-412 — WebRadio as the second caller

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLE_07` | WebRadio PLEDIT renders identically | host — screendump diff, PLEDIT rect only, vis off (VE-4), ≥5 station-list states | zero differing pixels |
| `T_PLE_08` | WebRadio scroll suite green | DUT — existing `T277`-family / `velocity-scroll-ve-review.md`, **≥3-run baseline with flaky set pre-declared** (ADR-059 D13) | no test passing in all 3 baselines fails after; no new failure outside the pre-declared flaky set |
| `T_PLE_09` | WebRadio scroll **feel** unchanged | **DUT eyeball** | indistinguishable from baseline |
| `T_PLE_10` | Divergences resolved deliberately | **host** — review the §3 divergence enumeration | every divergence has a recorded chosen behaviour and a rationale; none resolved by "whichever landed second" |
| `T_PLE_11` | Caps are honoured | DUT serial — tap a mutator zone on a `CAP_PLAY`-only source | control not drawn and not hit-tested; mutator never invoked |
| `T_PLE_12` | No PLEDIT code left in `webRadioApp.h` | host — grep | zero PLEDIT render/scroll symbols outside `pleditView.h` |
| `T_PLE_13` | Flash went down, not up | host — `firmware.bin` size delta | one renderer replacing two is a **negative** delta; a positive one means the old path was not deleted |
| `T_PLE_14` | **StationListSource seqno obeys the IFC** | DUT serial — `get pleditRepaints` across (a) a station-list change and (b) 60 s of no change (VE, X055 gap) | bumps **exactly once** per station-list change and **not at all** otherwise. WebRadio's change detection is a `_pleditDirty` bool today; converting it to a seqno has two distinct uncovered failure modes — missed repaint and repaint storm |

**Validation notes.** `T_PLE_01`/`07` are the gate; `run/screendump` gives an exact pixel comparison
and removes the judgement call. Note the known limitation from prior work: screendump **cannot
capture live navigated app state** (DTR-resets on connect), so states that require navigation must be
reached via serial injection, not by hand. `T_PLE_05`/`09` exist because pixel-identity does not
imply feel-identity — timing and gesture thresholds do not show up in a screenshot, and this is the
code TASK-277 was spent tuning. **"Indistinguishable to the operator" is a vibe, not a criterion**
(VE-18): use the ≥3-trial A/B protocol established on TASK-402, with the operator blind to build
order where practical. `T_PLE_13` is a cheap tripwire for an incomplete deletion.

**Fallback trigger.** If `T_PLE_01` or `T_PLE_07` cannot be made to pass, that is the signal to take
§3's documented fallback (a third renderer for local playlists) — not to relax the test.

## 7a. TASK-411 implementation record (2026-08-08)

Code landed and **the gate is complete: `T_PLE_01`–`04` and `T_PLE_06` PASS on the DUT; `T_PLE_05`
closed on the objective gesture battery by human acceptance** (its blind A/B returned void — see the
disposition at the end of this section). See "Gate coverage" below.

Getting there needed a new `SERIAL_DEBUG`-only `set queue N` queue injection: PLEDIT rows come only
from the Spotify queue snapshot, TASK-243 has left that snapshot empty across multiple sessions, and
a before/after pixel diff needs both builds to render *the same rows* — which a live account cannot
guarantee even when it works.

**What landed**

| File | |
|---|---|
| `app/src/winamp/pleditView.h` | new — `PlRow` / `PlCap` / `PlaylistSource` / `PleditView`. Owns chrome blit, row layout + truncation, duration column, total-time bar, synthetic thumb, velocity scroll, direct-scroll strip, seqno redraw gate, and the optimistic tap highlight |
| `app/src/util/textFit.h` | new — ellipsis truncation to a **pixel** budget (DEV-10) |
| `app/src/winamp/skinBlit.h` | new — `skinBlitSprite()`, lifted out of `WinampDisplay::blitSprite()` so the view can blit skin-font glyphs without depending on the display class. `WinampDisplay::blitSprite()` forwards to it |
| `app/src/winamp/winampDisplay.h` | delegates. Adds `SpotifyQueueSource` (`CAP_PLAY`), which also absorbed the Spotify queue bookkeeping (`songsSeen`, the two-entry URI history, the skip suppressor) |
| `webRadioApp.h` | **untouched**, by design — a pixel-identity failure must implicate one source |

Net **−187 lines** in `winampDisplay.h`.

**Deviations from §2.1, both deliberate**

1. `PlaylistSource` gained `virtual void onListReset()`. The renderer owns the redraw gate, so it is
   the only code that knows *when* a seqno advance was actually consumed — the `PLAYLIST_DRAW_MIN_MS`
   rate limit can defer one. Source-side bookkeeping that must stay in lockstep with the gate hangs
   off this instead of off a second seqno tracker in the caller.
2. `PleditView` owns the PLEDIT drag outright rather than mirroring the host's `dragState`. The host
   keeps its own enum for volume/posbar/taskbar and asks `dragging()`. `dbgGet("dragState")` still
   emits `D_PLEDIT_SCROLL` / `D_PLEDIT_SCROLL_DIRECT` — the serial contract is unchanged, the strings
   are just derived from `PleditView::dragMode()` now.

**Pixel-identity argument for the row formatter.** The pre-extraction code truncated the
artist-title half against a budget with the row-number prefix already subtracted, then concatenated
the prefix. The extracted form composes first (in the source) and truncates the whole string against
the un-subtracted budget. These are identical because the prefix width is an exact multiple of
`CHAR_W`, so the ellipsis lands on the same character. The one place they could differ — a budget
under three characters, where the original declines to truncate — is unreachable: `USABLE` is 238 px
and the duration and prefix are at most 42 px each, leaving ≥ 32 characters. Buffer-size changes
(`mid[48]` + `leftStr[56]` → `PlRow::text[64]`) are invisible for the same reason: truncation caps the
row at ≤ 39 characters, below every clip point in either form.

**`get pleditRepaints`** (ADR-059 D12) counts **accepted full repaints only**. A thumb-only blit
during a right-strip drag does not bump it — it paints the thumb, not the playlist, and that is what
`T_PLE_04` asserts on.

**Measurements** (re-derived from a fresh `run/build` + `run/build-debug`, `.map` extents — not
remembered numbers):

| | before | after | Δ |
|---|---|---|---|
| `cyd2usb_winamp` `.dram0.bss` | 78 568 B | 78 584 B | **+16 B** |
| `cyd2usb_winamp` `dram0_0_seg` headroom | 13 160 B | 13 144 B | −16 B |
| `cyd2usb_winamp_debug` `.dram0.bss` | 81 624 B | 81 640 B | **+16 B** |
| `cyd2usb_winamp_debug` `dram0_0_seg` headroom | 9 936 B | 9 920 B | −16 B |
| `cyd2usb_winamp` `firmware.bin` | 1 799 840 B | 1 800 320 B | +480 B |
| `cyd2usb_winamp_debug` `firmware.bin` | 1 872 512 B | 1 873 168 B | +656 B |

Adding `set queue N` on top of that moved **nothing** in production — `.dram0.data` (32 848 B),
`.dram0.bss` (78 584 B), headroom (13 144 B) and `firmware.bin` (1 800 320 B) are all byte-identical
to the row above, because the command does not compile in. Debug pays +752 B of flash
(1 873 168 → 1 873 920 B) and **0 B of RAM**.

`run/check` 6/6 on both envs, before and after the injection command.

The task brief asked for a `.bss`-neutral-or-negative extraction and said to report rather than work
around a growth. **It grew by 16 B**, and the 16 B is structural, not slack: one vtable pointer
(`PlaylistSource` is the design's chosen seam), one snapshot borrow pointer, the four-byte repaint
counter D12 required, and alignment. Every field that could move, moved; nothing is duplicated.
Debug headroom is 9 920 B, so this is not a threat — but it is not neutral either, and squeezing it
to zero would mean giving up either the interface or the observability.

The brief also carried a stale premise worth correcting for the next reader: it stated debug headroom
was **304 B** because "TASK-423's reclaim has NOT landed yet". TASK-423 **had** landed (see
`tasks.md`); measured baseline headroom was 9 936 B.

The positive flash delta is expected here and is **not** a `T_PLE_13` failure: that tripwire applies
to TASK-412, where one renderer finally replaces two. Nothing was deleted in this task.

### Gate coverage (DUT session 2026-08-08, `/dev/ttyUSB1`)

**`T_PLE_01`–`04` and `T_PLE_06` PASS on the DUT. `T_PLE_05` closed on the objective gesture
battery by human acceptance — see its disposition at the end of this section.**

| id | Verdict | Evidence |
|---|---|---|
| `T_PLE_01` | **PASS** | **0 differing pixels over 7 states**, 277 760 px compared. Baseline `winampDisplay.h` @ `12697bd` and `HEAD` each built, flashed and captured; PLEDIT rect (`x 0–320, y 116–239`) diffed per state. Zero on the full band and on the `x 0–275` sub-band alike. |
| `T_PLE_02` | **PASS** | Same captures. States 2–7 carry deliberately over-long rows interleaved with short ones, so truncation point, ellipsis and duration right-edge are all inside the compared region — and all identical. |
| `T_PLE_03` | **PASS** | Thumb captured at offset 0 (`s6`), mid (`s4`, offset 3) and max (`s5`, offset 7) on a 12-item list, plus max on a 20-item list (`s7`, offset 15). Identical y and height at every one. |
| `T_PLE_04` | **PASS** | `get pleditRepaints` held at 2 across 8 s of a static queue; advanced by exactly 3 across 3 seqno changes spaced 2 s apart; advanced by 2 (not 5) across 5 changes inside ~0.6 s, which is `PLAYLIST_DRAW_MIN_MS` coalescing as specified. |
| `T_PLE_05` | **CLOSED — objective battery, human-accepted** | Blind A/B attempted 2026-08-09 and **void**: its same-build control drew a large, confident "different", so the operator noise floor exceeds the signal (root cause: the 3 s shell busy lockout, not the renderer). Substituted a deterministic gesture battery — dead zone, speed constant, integrator ramp, both clamps, quick-swipe fallback, tap/scroll threshold and direct-scroll mapping all **identical** on both builds. Perceived smoothness remains unverified; disposition and reasoning at the end of this section. |
| `T_PLE_06` | **PASS 5/5** | With `scrollOffset` deliberately at 3 so row index ≠ absolute index, tapping rows 0–4 dispatched `ACT_PLAY_URI` param 3, 4, 5, 6, 7 — `scrollOffset + row`, confirmed twice per tap (the task's `dequeued action=PLAY_URI param=N` line and the `playAdvanced … uri=spotify:track:injNN` line). |

The seven states: empty · 1 row · 5 rows (exactly `PLEDIT_ROW_COUNT`, no thumb) · 12 rows scrolled
mid-list · 12 rows scrolled to end · 12 rows at top (thumb present, offset 0) · 20 rows at end
(duration column at 5 characters, which is also where it steals a character from the text budget).

**Instrument noise floor was measured, not assumed.** Two capture passes of the *same* firmware
differed by 0 px on every state. Without that, "0 differing pixels" between builds would not be
evidence of anything.

**State parity was verified before each diff**, not assumed: `get queue` count and `get scrollOffset`
were read on both builds for every state and matched exactly (0/1/5/12/12/12/20 and 0/0/0/3/7/0/15).
A pixel diff between two builds rendering *different* content would be meaningless.

Scroll position is set through the real direct-scroll strip (`tap 261 <y>`), not a debug setter:
`updateScrollDirect()` maps `relY` onto the offset with identical arithmetic in both builds, so a
given y yields the same offset in each. That matters because the baseline firmware has no
`set scrollOffset` and adding one would have meant hand-patching the baseline.

Also green, count-independent (17/17): `get pleditRepaints` reports; full serial-contract parity on
`scrollOffset` / `dragState` / `scrollAccum` / `scrollVelocity` / `cooldown` / `lastPlaylistDraw` /
`set speedK`, all now served from the view; the derived `dragState` strings are correct under a live
capture (held strip drag reports `D_PLEDIT_SCROLL_DIRECT`, `D_IDLE` after release); both PLEDIT zones
hit-test correctly through `hitbox.h`; `tick` while idle is a no-op.

### `set queue N` — the injection this needed (new, `SERIAL_DEBUG` only)

PLEDIT rows come only from the Spotify queue snapshot, and there was no way to populate it without a
live account. TASK-243 (owner Premium lapsed — verified host-side again this session:
`spotify_state.py` → `HTTP 403`) has held that state across multiple sessions, and the harness
*skips* rather than fails those tests, so the gap was silent. The 2.4 GHz AP was also absent this
session (`NO_AP_FOUND` reason 201 for `<home-ssid>`; host `nmcli` showed only
`<home-ssid>` on channel 104 / 5 GHz, unjoinable by an ESP32) — either blocker alone empties the
queue.

`set queue N` (0 ≤ N ≤ `QUEUE_MAX`, in `spotifyTaskStorage.cpp`'s `dbg_set`) seeds N synthetic
entries and bumps the seqno, exactly as `storeQueueSnapshot()` does for a real poll. Content is a
pure function of the index, which is the property the gate actually needed: **the same rows on two
different builds**. A live account cannot offer that — whatever is playing during the "before"
capture will not be playing during the "after" one, so a pixel diff against it could never mean
anything. Odd rows carry an over-long artist *and* title so one capture exercises both the truncated
and untruncated layout; durations sweep past 9:59 at i ≥ 15 so the duration column is captured at
both widths.

Cost: **zero production impact** — `.dram0.data`, `.dram0.bss` and `firmware.bin` are byte-identical
to the previous commit in `cyd2usb_winamp`. Debug pays +752 B flash and **0 B RAM**.

This also unblocks `T155`–`T160` and any future PLEDIT-row test. Those still call
`wait_for_queue(min_count=10)` and will keep skipping until VE reworks them onto `set queue`;
`run_serialdbg_tests.py` was deliberately not edited here (another agent held it for part of this
session, and the suite is VE's artefact).

### `T_PLE_05` attempt 1 (2026-08-09) — **inconclusive: the control failed**

Ran the VE-18 blind A/B (≥3 trials, operator blind, presentation order randomised into a file
neither party read). Trial 1's two presentations were **the same build** — a deliberate same-build
control — and the operator reported a large, confident difference: *"A is better; B: none of 1, 2, 3
work reliably."*

There was no code difference between what was compared, so that is the **discrimination noise floor,
and it is larger than any signal this test could resolve.** Attempt 1 is void — not passed, not
failed. The control is the only reason we know that; a 2-presentation A/B without one would have
been read as a regression in whichever build happened to land second.

**The dominant noise source is the shell busy lockout, not the renderer.** `SHELL_BUSY_TIMEOUT_MS`
is 3 000 ms (`app/src/main.cpp`, `SHELL_BUSY_TIMEOUT_MS`) and `appHandleInput` drops input outright while it is set
(`app/src/main.cpp`, `appHandleInput`). Any gesture that qualifies as a tap — `abs(dy) < 6 px` and `< 250 ms` — dispatches
`ACT_PLAY_URI`, which sets busy, which silently swallows **every gesture for the next ~3 s**. During
feel-testing, taps happen constantly by accident, so a run degenerates into "half my gestures did
nothing", and *how many* land differs run to run. This is pre-existing behaviour with nothing to do
with TASK-411, and it is made worse now the AP is back: with WiFi up the dispatched action attempts a
real request (403, with TLS and backoff behind it) instead of failing instantly, so the lockout runs
its full length. The same mechanism was already visible during `T_PLE_06`, where two taps came back
`hit:CANVAS, skipped:true` until the harness paced itself.

**A second operator observation, unrelated to the extraction:** *"A's flick seems worse than
WebRadio's PLEDIT implementation."* A was HEAD, and HEAD reproduces Spotify's flick exactly, so this
is a **pre-existing Spotify-vs-WebRadio feel divergence** — logged as D23 below. It is a TASK-412
input, not a TASK-411 defect.

### `T_PLE_05` objective half — deterministic gesture battery (PASS)

Since the eyeball channel is currently too noisy to resolve anything, the measurable part of "scroll
feel" was measured directly instead: identical serial-driven gestures on both builds, comparing
`scrollOffset` trajectories. `set bgPoll 0` first, to take poll/TLS contention out of the numbers.

**Every result identical between baseline `12697bd` and HEAD:**

| probe | result (both builds) | what it pins down |
|---|---|---|
| `flick_up` / `flick_down` | 0 → 1 / 0 → 0 (clamped) | quick-swipe minimum-one-row fallback, and the clamp |
| `vel_small_up` (dy −3 px) | `[0,0,0,0,0,0]` | dead zone + speed constant at small displacement |
| `vel_large_up` (dy −25 px) | `[5,6,7,7,7,7]` | integrator ramp **and** the clamp at max offset (7 = 12−5) |
| `vel_large_down` at offset 0 | `[0,0,0,0,0,0]` | clamp at min offset |
| `strip_map` (y 136…184) | `0, 1, 3, 5, 7` | direct-scroll positional mapping across the whole track |
| `disc_dy5` / `disc_dy7` | no move / +1 row | tap-vs-scroll boundary sits exactly at `PLEDIT_TAP_PX` = 6 |

That covers the dead zone, the speed constant, the integrator ramp, both clamps, the quick-swipe
fallback, the tap/scroll threshold and the direct-scroll mapping — i.e. everything about "feel" that
is a number. What remains for the eyeball is genuinely subjective: perceived smoothness and any
stickiness the trajectories do not capture.

### `T_PLE_05` disposition — **CLOSED on the objective battery, by human acceptance (2026-08-09)**

The operator signed off on the gesture battery above in place of a completed blind A/B. Recording
exactly what that does and does not buy, so a later audit does not have to reconstruct it:

**Covered.** Every quantitative component of "feel" — dead zone, speed constant, integrator ramp,
both clamps, quick-swipe minimum-one-row fallback, tap/scroll threshold, direct-scroll mapping —
measured identical on both builds.

**Not covered.** Perceived smoothness, and any stickiness that does not move `scrollOffset`
differently. The blind A/B was attempted and returned void, so this id has **no operator-confirmed
result**; it is closed on measurement plus judgement, not on the method its acceptance criterion
names.

**Why that was judged acceptable here** (the reasoning, so it is not treated as precedent for
skipping eyeball gates generally): the renderer is a transcription — the velocity integrator, tap
discrimination and quick-swipe fallback moved line-for-line — the pixel gate passed at 0 differing
pixels over 7 states, and the battery pins every numeric parameter. The residual risk is a
perceptual difference with no mechanism behind it. Against that, the eyeball channel is currently
unusable: the 3 s shell busy lockout (above) produces a noise floor that swamped a same-build
control. Re-running without first fixing that would not have produced evidence, only a second void
result. This is the same shape as `T_RCL_04`'s closure (human accepted code inspection over building
a throwaway probe), and it should be revisited if the busy-lockout confound is ever removed.

**Follows from this, for TASK-412.** `T_PLE_09` is the same eyeball gate for WebRadio and will hit
the identical noise floor. Either fix the confound first, or plan for the same objective-battery
substitution — and decide that *before* running it, not after a void result. D23 (Spotify's flick
reportedly feeling worse than WebRadio's) is an open question the battery cannot answer, since both
copies produce the same trajectories; it needs the eyeball channel working.

**To run it properly if that ever happens.** `set bgPoll 0` first, keep every gesture past 6 px so
nothing dispatches a tap and arms the lockout, `set queue 12`, and use the ≥3-trial blind A/B with
same-build controls included — the control is what made this attempt informative rather than
misleading.

Rig notes for whoever picks this up: the CH340 moved `/dev/ttyUSB0` → `/dev/ttyUSB1` mid-session —
always use `./run/port`. `run/screendump`'s height flag is `-H` (`-h` is help). Injection and capture
must share one serial session: `run/screendump` DTR-resets on connect, which wipes the injected
queue, and so does closing the port — hold it open for the duration instead. With WiFi up the board
boots into whichever player mode is persisted (`bootIntoWebRadio`, `app/src/main.cpp` (`setup`)), so force
`set playerMode spotify` before testing or you will be driving WebRadio's untouched PLEDIT copy
instead of the one under test.

## 7b. TASK-412 implementation record (2026-08-09)

**What landed.** WebRadio's private PLEDIT copy (`_drawPledit()`, `_gestureEnd()`, `_tickScroll()`,
`_updateScrollDirect()`, `_wrs`/`_dragStart*`/`_scrollAccum`/`_scrollVelocity`/`_scrollSpeedK`/
`_pleditDirty`) is gone. `WebRadioApp` gained a nested `StationListSource : PlaylistSource`
(`CAP_PLAY` only, reads `_stations[]`/`_currentIdx`/`_state` directly — nested classes have the same
access rights as any other member, C++11) and now drives the **same** `PleditView` instance Spotify
uses, via new `WinampDisplay::pledit*()` entry points (`pleditPress/Move/Release/Dragging/DragMode/
ScrollOffset/ScrollAccum/ScrollVelocity/SpeedK/SetSpeedK/ScrollToRow/MarkDirty/ResetDrag`,
`touchCoolingDown/armTouchCooldown`, `drawPlaylistFor`). One `PleditView` for the whole app now, not
one per caller — the design's own §2.3 already implied this ("there is exactly one PLEDIT visible at a
time"), TASK-411 just hadn't needed to act on it yet.

**Per-source parameterisation added to `pleditView.h`** for the pixel-affecting divergences (D1–D3,
D10): `PlaylistSource::bgNormal()/bgSelected()/marginPx()` (default = Spotify's pre-extraction values,
so Spotify is unaffected by construction) and a new pure-virtual `overlayText(char*, size_t)`
replacing the renderer's own time-formatting (Spotify implements the "M:SS"/"H:MM:SS" formatter it
always had; WebRadio implements the country-code readout). `PlRow` gained `rightText[8]` +
`rightColor` (D3) — the right column is now source-formatted content, not always a duration;
`durationSec` stays for totalSec()-style aggregation. D19 (only mark the scroll dirty when the offset
actually changed at the clamp) is now live for both callers, gated behind a real `!=` check in
`tickScroll()`.

**Divergence dispositions actually taken**, against the design's own recommendation column: D1–D3,
D6 adopted the "parameterise" plan exactly as written. D4, D7, D8, D9, D22 needed no code change
(already resolved by the interface, per the log). D5 (ellipsis truncation) and D6 (black empty slots)
are now live for WebRadio — deliberate pixel changes to WebRadio, exactly as the log flagged; see the
`T_PLE_07` note below. D10 done via `overlayText()`. D11–D18, D20–D21 fell out for free once WebRadio
routes through the shared view — there's only one redraw gate, one cooldown, one drag-state owner, one
tap-index/count source now, so nothing was "kept" or "adopted" as a separate step. D13 got a
`resetScrollOnChange()` cap (default true = Spotify; `false` for `StationListSource`); since the
scroll offset is shared state now, the app explicitly re-syncs it to the current pick on every
selection and on app entry (`_pleditSync()`, `pleditScrollToRow()`) rather than relying on the
natural seqno-reset path Spotify gets automatically. D23 (the flick-feel report) is unresolved — both
copies still produce identical trajectories (verified: same code path now, trivially), so the reported
difference, if real, has no mechanism in this renderer; needs the eyeball channel, same as D23's
original disposition said.

**Deviation from plan, found by testing, not designed in:** `dbgSet`'s `wrUrl`/`wrDeadUrls` debug
injectors originally didn't bump `_plSeqno` — caught on the DUT (a `set wrDeadUrls N` injection left
`PleditView`'s cached `_lastVisibleRows`/`_lastCount` stale, so PLEDIT-row taps hit-tested against the
wrong geometry and landed on `DEADZONE` instead of `PLEDIT`). Fixed by bumping `_plSeqno` and calling
`pleditScrollToRow(0)` in both injectors, matching the pattern already used at the two production
list-identity-change sites (station-fetch install, config-change reset).

**Measurements** (fresh `run/build` + `run/build-debug`, stash/pop A-B on the unmodified working tree —
not remembered numbers):

| | before | after | Δ |
|---|---|---|---|
| `cyd2usb_winamp` `firmware.bin` (Flash used) | 1 795 245 B | 1 795 281 B | **+36 B** |
| `cyd2usb_winamp` RAM used | 111 432 B | 111 400 B | −32 B |
| `cyd2usb_winamp_debug` `firmware.bin` (Flash used) | 1 868 741 B | 1 868 901 B | **+160 B** |
| `cyd2usb_winamp_debug` RAM used | 114 652 B | 114 620 B | −32 B |

**`T_PLE_13` does not pass as a literal "negative delta."** Flash grew slightly on both envs; RAM
shrank on both (WebRadio's own scroll-state fields, ~40 B, are gone — replaced by `StationListSource`'s
one pointer + `_plSeqno`, ~8 B — consistent with the RAM delta). The flash growth is the shared
renderer's per-source dispatch (five new virtual calls per row/redraw path, now paid by *every* caller
including Spotify) outweighing the code actually deleted from `webRadioApp.h` (~150 lines of gesture
math that was already fairly compact, reusing `touch/scrollTuning.h` constants and simple inline
geometry rather than anything duplicated at length). Reported rather than chased — the brief says
report a growth, not work around it; `T_PLE_12`'s grep gate (below) is the one that actually catches an
incomplete deletion, and it's clean.

**Gate coverage.**

| id | Verdict | Evidence |
|---|---|---|
| `T_PLE_12` | **PASS** | `grep PLEDIT app/src/webRadioApp.h` — only two literal identifier hits left, both `PLEDIT_BODY_BG` inside `StationListSource::bgNormal()/bgSelected()`, i.e. the per-source *style data* the interface now requires a source to supply (D1) — not render/scroll code. No `PleditView`/`drawPledit`/`_gestureEnd`/`_tickScroll`/`_updateScrollDirect` symbols remain outside comments. |
| `T_PLE_13` | **FAIL (as literally worded), analysed above** | +36 B / +160 B, not negative. Not an incomplete deletion (see `T_PLE_12`) — the shared per-source virtual dispatch costs more than the deleted flat code saved. |
| `T_PLE_14` | **PASS** | DUT serial: `pleditRepaints` held flat (10→10) over 8 s with a static list; advanced by exactly one per `set wrDeadUrls N` call across four consecutive list changes (2→3→4 with only list-identity-changing calls in between; unrelated `_dirty`-only chrome redraws don't bump it). |
| `T_PLE_11` | **PASS, vacuously** | `StationListSource` is `CAP_PLAY`-only and the renderer draws no mutator control at all yet (reorder/remove/add/save are `LocalPlaylistSource`/parent-design scope) — "not drawn, not hit-tested, never invoked" holds by construction, not by a cap check exercised at runtime. |
| `T_PLE_07` | **3/5 states pixel-identical; 2 documented divergences** | Screendump A/B (baseline = this commit's parent, stashed; PLEDIT rect, `set bgPoll 0`, `set wrDeadUrls N` for deterministic content, one held serial session per build to avoid the DTR-reset-wipes-injection gap): **0 px diff** at exactly-5-rows (no scrollbar) and 8-rows-top-of-list. **Diff at empty (0 stations, all 5 rows) and 3-rows (2 empty slots)** — entirely inside the empty-slot rows, i.e. exactly the D6 disposition (black instead of `PLEDIT_BODY_BG`), reproduced identically across two independent capture runs. **Diff at 8-rows-scrolled (346 px)** traced to a `cmdTap`-harness artifact, not a rendering difference: `cmdTap`'s WebRadio branch (`main.cpp`) calls `winampDisplay.injectTouch()` (Press, Spotify-shaped diagnostic path) then `WebRadioApp::handleInput(Release,...)` — it never calls WebRadio's own `handleInput(Press,...)`. Pre-merge, a strip-zone Press only updated *Spotify's* separate `_plView`/offset (invisible, since WebRadio drew its own copy); post-merge the same Press updates the *shared* view WebRadio now actually draws from, so a bare `tap` on the strip now visibly scrolls where it silently no-op'd before. Confirmed deterministic (identical pixel count on a second independent A/B run) and confirmed by hand-tracing `_updateScrollDirect()`'s formula (offset=2 both ways) — not investigated further as a rendering bug because it isn't one; real device touches were never affected (they call `handleInput(Press,...)` directly). Flagged for VE: `cmdTap`'s WebRadio branch may want its own Press call for harness fidelity, independent of TASK-412. |
| `T_PLE_08` | **PASS — 3/3 clean baselines, 18/18** | New WebRadio-targeted battery (`T_PLE_WR_155`–`160` in `run_serialdbg_tests.py`, mirroring `T155`–`T160`/`velocity-scroll-ve-review.md` against `StationListSource` via `set wrDeadUrls 15` instead of Spotify's queue). ADR-059 D13 ≥3-run baseline: 3 independent debug-flash runs, 6/6 PASS every time, zero flaky. First attempt (interleaved-send pattern copied verbatim from T157–159) FAILed 3/6 — root-caused as a harness-timing artifact, not a regression: those sends raced the injection queue's Press step because `WebRadioApp`'s `loop()` cost differs from Spotify's, breaking the iteration-count-tuned interleaving T157–159 depend on. Confirmed by a manual delay-padded probe (same gesture reaches `D_PLEDIT_SCROLL`, vel≈2.0004 rows/s) before rewriting the three to use `drag ... hold` + `release` + `get wrScroll` (WebRadio's real debug surface — `tick`'s JSON `scrollOffset` field is `winampDisplay`-only per the TASK-277 VE-1-5 comment in `cmdTick`), which is both correct and no longer timing-fragile. |
| `T_PLE_09` | **PASS — human-accepted, 2026-08-10** | Live DUT feel-check on production firmware: operator scrolled WebRadio's station list side-by-side against Spotify's queue (same `PleditView` instance) — acceleration/deceleration, quick-swipe minimum-one-row fallback, top/bottom clamp behaviour, and direct-scroll strip thumb tracking all reported identical. Same standard as `T_PLE_05` — objective battery (`T_PLE_08`) plus human acceptance in place of a blind A/B, since the 3 s shell-busy lockout makes blind A/B unreliable on this device. |

**Not done:** `./run/check` was run and is 6/6 after this change (see below), but the full ≥5-state
`T_PLE_07` battery (only 5 states captured here vs. TASK-411's 7), `T_PLE_08`, and `T_PLE_09` want a
dedicated DUT/VE session rather than being squeezed into this one.

## 7. Exit criteria

1. Spotify PLEDIT pixel-identical before/after TASK-411 — verified on the LCD, not inferred from
   serial.
2. WebRadio PLEDIT pixel-identical and scroll-feel unchanged after TASK-412 — T277 suite green **and**
   eyeballed.
3. `webRadioApp.h` contains no PLEDIT rendering or scroll code.
4. The divergence enumeration from §3 is recorded, with the chosen behaviour per divergence.
5. `./run/check` 6/6 after each step.
