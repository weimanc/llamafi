# Design — M-PLEDIT-ABSTRACTION: one playlist renderer behind a source interface

> Owner: Architect
> Status: **accepted 2026-08-07** (ADR-059 signed off; implementation authorised)
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

## 7a. TASK-411 implementation record (2026-08-08) — **PARTIAL, not closeable**

Code landed. The DUT was released mid-session and the gate was run as far as it goes: **the empty-queue
state of `T_PLE_01` passes with zero differing pixels**, and every count-independent assertion passes.
**Four of the six ids remain unrun, blocked externally — not by DUT availability.** See
"Gate coverage" below. **Do not mark TASK-411 DONE.**

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

`run/check` 6/6 on both envs.

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

| id | Verdict | Evidence |
|---|---|---|
| `T_PLE_01` | **PARTIAL — 1 of ≥5 states** | Empty queue: **0 differing pixels**. Baseline `winampDisplay.h` @ `12697bd` built, flashed and captured; `HEAD` built, flashed and captured; PLEDIT rect (`x 0–320, y 116–239`) diffed. All six pairings across the four captures were 0/39 680 px — full band, `x 0–275` sub-band and the `x 275–320` taskbar band alike. The other four states need a non-empty queue (blocked, below). |
| `T_PLE_02` | **UNRUN — blocked** | Needs a long "Artist - Title" row. |
| `T_PLE_03` | **UNRUN — blocked** | Thumb only draws when `count > PLEDIT_ROW_COUNT`; queue is 0. |
| `T_PLE_04` | **PARTIAL** | "Does not advance while seqno is static" **passes** — `get pleditRepaints` held at 1 across 6 s idle and across every injected gesture. "Advances exactly once per seqno change" and the `PLAYLIST_DRAW_MIN_MS` rate-gate assertion need a seqno advance (blocked). |
| `T_PLE_05` | **UNRUN** | Eyeball gate, and there is nothing to scroll with an empty list. |
| `T_PLE_06` | **UNRUN — blocked** | Needs ≥ 5 rows to tap. The negative case passes: with `count == 0` the rows rect is zero-height, and both a tap and a held drag on it report `DEADZONE` / `D_IDLE` rather than anchoring a PLEDIT gesture. |

**Instrument noise floor was measured, not assumed.** Two `screendump` captures of the *same*
firmware differed by 0 px. Without that, "0 differing pixels" between builds would not be evidence of
anything.

Count-independent checks, all green (17/17):

- `get pleditRepaints` exists and reports (`{"var":"pleditRepaints","count":1}`) — the D12 deliverable.
- Full serial-contract parity: `get scrollOffset` / `dragState` / `scrollAccum` / `scrollVelocity` /
  `cooldown` / `lastPlaylistDraw` and `set speedK` all answer with their pre-change shapes, now served
  from the view.
- The derived `dragState` strings are correct under a live capture: a held drag in the right strip
  reports `D_PLEDIT_SCROLL_DIRECT`, and `D_IDLE` after release.
- Both PLEDIT zones hit-test correctly through `hitbox.h`: a tap at `x=261` (right strip) reports
  `hit:PLEDIT, action:SCROLL_DIRECT`; a tap at `x=134, y=142` (rows, empty list) reports `DEADZONE`.
- `tick 20 20` while idle leaves `scrollOffset=0`, `scrollVelocity=0.0` (T160-equivalent).

### Why the rest is blocked — and it is not the DUT

The PLEDIT rows come from `spotifyTask`'s queue snapshot, and **there is no serial injection surface
for it** — the existing `T155`–`T160` all gate on `wait_for_queue(min_count=10)` and skip without a
live queue. Two independent things stop that queue being populated today:

1. **TASK-243** — the owner account's Premium has lapsed. Verified host-side this session:
   `app/tools/spotify_state.py` → `{"ok": false, "error": "HTTP 403"}`. This is the authoritative
   check; the device cannot do better.
2. **The 2.4 GHz AP is gone.** The device logs `NO_AP_FOUND (reason 201)` for
   `<home-ssid>`, and a host-side `nmcli dev wifi list` confirms it: only
   `<home-ssid>` on **channel 104 (5 GHz)** is present, which an ESP32 cannot join. AP-side, same
   shape as the previous SSID rename.

Either one alone empties the queue, so fixing the WiFi would not unblock the gate while the 403
stands.

**Recommendation (for PM to route).** These three ids have now been blocked by TASK-243 across
multiple sessions, and TASK-243 is an external dependency with no owner-side fix. A small
`set queue`-style debug injection — seeding `g_queueSnapshot` with N synthetic entries and bumping
the seqno — would make `T_PLE_01`/`02`/`03`, `T_PLE_04`'s second half, `T_PLE_06` and the whole
`T155`–`T160` family runnable without a Spotify account at all, and would give `T_PLE_02` something
the live API cannot: a *deterministic* long title, so the truncation diff is repeatable rather than
whatever happens to be playing. It is also the only way the before/after halves of a pixel diff can
be guaranteed to render the same content. Deliberately **not** built as part of TASK-411 — it is new
scope and it changes the firmware under test.

**Handover — remaining gate**

- `T_PLE_01`/`02`/`03` need `run/screendump` with the diff scoped to the **PLEDIT rect**
  (`PLEDIT_Y` … `PLEDIT_Y + PLEDIT_H`, full width). The `-H` flag is the height (`-h` is help).
  With the diff scoped this way the visualiser is already outside the rect (vis sits at `y≈43–58`),
  so VE-4's "vis off" requirement is satisfied by the scoping — it matters for a whole-canvas diff,
  which is what makes a whole-canvas "zero differing pixels" bar unpassable. The same applies to
  `T_PLE_07`.
- Reach the list states by **serial injection**; `run/screendump` cannot capture live navigated app
  state (it DTR-resets on connect).
- `T_PLE_06` asserts the absolute index (`scrollOffset + row`), which is unchanged — but see D15: the
  index is taken from the **live** scroll offset at release, not the press-time one.
- Rig note: the CH340 moved `/dev/ttyUSB0` → `/dev/ttyUSB1` mid-session. Use `./run/port`, never a
  hardcoded node.

## 7. Exit criteria

1. Spotify PLEDIT pixel-identical before/after TASK-411 — verified on the LCD, not inferred from
   serial.
2. WebRadio PLEDIT pixel-identical and scroll-feel unchanged after TASK-412 — T277 suite green **and**
   eyeballed.
3. `webRadioApp.h` contains no PLEDIT rendering or scroll code.
4. The divergence enumeration from §3 is recorded, with the chosen behaviour per divergence.
5. `./run/check` 6/6 after each step.
