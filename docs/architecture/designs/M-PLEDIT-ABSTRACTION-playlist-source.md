# Design — M-PLEDIT-ABSTRACTION: one playlist renderer behind a source interface

> Owner: Architect
> Status: draft
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
detail.

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
| `T_PLE_01` | Spotify PLEDIT renders identically | **host** — `run/screendump` before/after, pixel diff | zero differing pixels across ≥5 states: empty queue, 1 row, 5 rows, >5 rows scrolled mid-list, scrolled to end |
| `T_PLE_02` | Row formatting unchanged | host — screendump diff on a long "Artist - Title" | truncation point and ellipsis identical; duration column right-edge identical |
| `T_PLE_03` | Scroll thumb geometry unchanged | host — screendump diff at scrollOffset 0 / mid / max | thumb y and height identical at all three |
| `T_PLE_04` | Redraw gate unchanged | DUT serial — seqno-diff behaviour under a static queue | no repaint while seqno static; repaint within one tick of seqno advance; `PLAYLIST_DRAW_MIN_MS` rate gate still observed |
| `T_PLE_05` | Scroll **feel** unchanged | **DUT eyeball** — velocity drag, flick, direct-strip drag | indistinguishable from baseline to the operator; no new stickiness or overshoot |
| `T_PLE_06` | Tap-to-play still dispatches | DUT serial — tap each of 5 rows | `ACT_PLAY_URI` with the correct absolute index (`scrollOffset + row`) 5/5 |

### TASK-412 — WebRadio as the second caller

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLE_07` | WebRadio PLEDIT renders identically | host — screendump diff, ≥5 station-list states | zero differing pixels |
| `T_PLE_08` | WebRadio scroll suite green | DUT — existing `T277`-family / `velocity-scroll-ve-review.md` | identical pass set to baseline |
| `T_PLE_09` | WebRadio scroll **feel** unchanged | **DUT eyeball** | indistinguishable from baseline |
| `T_PLE_10` | Divergences resolved deliberately | **host** — review the §3 divergence enumeration | every divergence has a recorded chosen behaviour and a rationale; none resolved by "whichever landed second" |
| `T_PLE_11` | Caps are honoured | DUT serial — tap a mutator zone on a `CAP_PLAY`-only source | control not drawn and not hit-tested; mutator never invoked |
| `T_PLE_12` | No PLEDIT code left in `webRadioApp.h` | host — grep | zero PLEDIT render/scroll symbols outside `pleditView.h` |
| `T_PLE_13` | Flash went down, not up | host — `firmware.bin` size delta | one renderer replacing two is a **negative** delta; a positive one means the old path was not deleted |

**Validation notes.** `T_PLE_01`/`07` are the gate; `run/screendump` gives an exact pixel comparison
and removes the judgement call. Note the known limitation from prior work: screendump **cannot
capture live navigated app state** (DTR-resets on connect), so states that require navigation must be
reached via serial injection, not by hand. `T_PLE_05`/`09` exist because pixel-identity does not
imply feel-identity — timing and gesture thresholds do not show up in a screenshot, and this is the
code TASK-277 was spent tuning. `T_PLE_13` is a cheap tripwire for an incomplete deletion.

**Fallback trigger.** If `T_PLE_01` or `T_PLE_07` cannot be made to pass, that is the signal to take
§3's documented fallback (a third renderer for local playlists) — not to relax the test.

## 7. Exit criteria

1. Spotify PLEDIT pixel-identical before/after TASK-411 — verified on the LCD, not inferred from
   serial.
2. WebRadio PLEDIT pixel-identical and scroll-feel unchanged after TASK-412 — T277 suite green **and**
   eyeballed.
3. `webRadioApp.h` contains no PLEDIT rendering or scroll code.
4. The divergence enumeration from §3 is recorded, with the chosen behaviour per divergence.
5. `./run/check` 6/6 after each step.
