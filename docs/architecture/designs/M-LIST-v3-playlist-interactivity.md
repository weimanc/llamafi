# Design — M-LIST-v3 Playlist Interactivity

> Owner: Developer
> Status: planned (2026-05-15; updated 2026-05-22)
> Tracked-as: TASK-051a–h
> Deps: M-LIST-v2, TASK-021 (tap-to-play)

## Feature 1 — Selected-row highlight tracks current song

After `ACT_PLAY_URI param=N`, `winampDisplay` tracks `optimisticSelectedRow` (same pattern as `optimisticVolumeUntilMs`). `drawPlaylist()` renders that row as selected instead of row 0 until queue snapshot seqno advances or timeout (~8 s). On track change (seqno advance), reset to row 0 (items[0] = currently playing, always correct post-poll).

Sub-task: TASK-051a.

## Feature 2 — Virtual scroll (queue > 5 items)

- Extend `SPOTIFY_QUEUE_MAX_ITEMS` (patched in `lib/SpotifyArduino/`) to ~20. `QueueSnapshot` grows accordingly.
- Add `scrollOffset` (int, 0-based) to `WinampDisplay`. `drawPlaylist()` renders `items[scrollOffset .. scrollOffset + PLEDIT_ROW_COUNT - 1]`.
- Touch: row tap maps to `scrollOffset + row` for `ACT_PLAY_URI`.
- Swipe in PLEDIT content area increments/decrements `scrollOffset` (reuse `dragState` pattern).

Sub-tasks: TASK-051b (extend queue), TASK-051c (scrollOffset + slice), TASK-051d (swipe gesture).

## Feature 3 — Live scrollbar thumb

Thumb position = `scrollOffset / (count - PLEDIT_ROW_COUNT)` × scrollbar track height. Blit thumb sprite at computed Y on each `drawPlaylist()` redraw. Depends on Feature 2.

Sub-task: TASK-051e.

## Cross-feature — Auto-scroll to current track on track change

On seqno advance, reset `scrollOffset = 0`. Items[0] (currently playing) always in view after track change.

Sub-task: TASK-051f.

## Feature 4 — Row formatting: number, artist–title, duration

### Format

```
N. Artist - Title...         M:SS
```

- **N** — queue-relative track number, 1-based. Computed as `songsSeen + scrollOffset + i + 1` for screen row `i`. See Feature 5 for `songsSeen`.
- **Artist - Title** — left-aligned, truncated with `"..."` (three dots) if the middle section overflows.
- **M:SS** — per-row duration, right-aligned in the content area.

### Pixel layout

Content area: `PLEDIT_CONTENT_W = 244px`, `TEXT_MARGIN = 3px` each side → **238px usable**. Font 1 (TFT_eSPI Glcd) = 6px/char fixed → ~39 usable chars.

```
[LEFT_MARGIN=3px] [N. ] [Artist - Title...] [gap] [M:SS] [RIGHT_MARGIN=3px]
```

- Number prefix: `snprintf` into a fixed buffer; width = `strlen("N. ") * 6px`.
- Duration string: `snprintf` `M:SS` or `MM:SS`; width = `strlen(dur) * 6px`. Draw at `right_edge - dur_width`.
- Middle budget = `238 - prefix_width - dur_width - 2px_gap`. If `strlen("Artist - Title") * 6 > budget` → trim to fit, append `"..."`.

### Font note

Current row rendering uses Font 1 (TFT_eSPI Glcd, 6px/char, ~39 chars). SKIN_FONT (Winamp bitmap, 5px/char fixed, ~47 chars) would gain 8 chars per row and be more authentic but requires switching `drawPlaylist()` to per-glyph `blitSprite` calls. SKIN_FONT has no single-char ellipsis — `"..."` is the best available. Font migration is deferred; a follow-on sub-task can upgrade if row space is too tight in practice.

Sub-task: TASK-051g.

## Feature 5 — `songsSeen` counter with 2-entry URI history

### Motivation

Row numbers always starting at 1 are monotonous. `songsSeen` offsets the numbering by how many tracks have naturally advanced since boot, giving varied, session-relative numbers (e.g. "47. Artist - Title").

### State

```cpp
uint16_t songsSeen   = 0;                          // RAM only, resets on boot
char     prevNextUri[SPOTIFY_URI_CHAR_LENGTH] = {}; // uri of items[1] from last poll
bool     skipPending = false;                       // set by ACT_NEXT or ACT_PLAY_URI dispatch
```

### Increment rule

After each queue snapshot fetch, before updating `prevNextUri`:

```
if (items[0].uri == prevNextUri && !skipPending)
    songsSeen++
skipPending = false
prevNextUri = items[1].uri   // store for next poll; empty string if count < 2
```

### What this correctly handles

| Event | Outcome |
|-------|---------|
| Natural track end | `items[0]` = old `items[1]` → **increment** ✓ |
| DUT skip (`ACT_NEXT`) | `skipPending` set → **no increment** ✓ |
| DUT tap-to-play row > 1 | `items[0]` ≠ old `items[1]` (and `skipPending` set) → **no increment** ✓ |
| DUT tap-to-play row 1 | URI matches but `skipPending` set → **no increment** ✓ |
| External skip (phone, random track) | `items[0]` ≠ old `items[1]` → **no increment** ✓ |
| External next-press (phone) | `items[0]` = old `items[1]`, no flag → **increment** (acceptable; song played) |
| Pause | No track change, no URI diff → **no increment** ✓ |
| Go back | `items[0]` ≠ old `items[1]` → **no increment** ✓ |

### `skipPending` set by

- `spotifyTask::enqueue(ACT_NEXT, ...)` dispatch
- `spotifyTask::enqueue(ACT_PLAY_URI, ...)` dispatch (any row, covers row-1 match edge case)

### Persistence

RAM only (resets on boot). NVS persistence deferred — boot-reset is acceptable for the aesthetic goal.

Sub-task: TASK-051h.

---

## Known issue — tap-to-play replaces queue (2026-05-16 DUT observation)

Current `playAdvanced(uri)` in TASK-021 starts the selected track as a new session, clearing the Spotify queue. PLEDIT shows 5 identical rows of the new track; Spotify shows 1 item. User expectation: preserve queue, jump to selected position.

Resolution options:
- **Context play** (preferred): surface `context_uri` from `/me/player` into `Snapshot`; use `PUT /v1/me/player/play` with `{"context_uri": "...", "offset": {"uri": "..."}}`. Works for playlist/album contexts. Needs new lib patch to capture `context_uri`.
- **Blind skip**: call `next` N times (N = row index). Fragile if queue mutates between tap and execution.

Pre-requisite for option 1: `context_uri` added to `Snapshot` (new LOCAL_PATCHES entry).

---

## Exit criteria

- Selected row highlight follows playing track within one poll; optimistic highlight appears immediately on tap.
- With queue > 5 items, swipe up/down scrolls visible window; all rows reachable.
- Scrollbar thumb position matches scroll position.
- Track change snaps view to show currently-playing in row 0.
- Each row displays: `N. Artist - Title   M:SS` with N queue-relative, duration right-aligned, middle truncated with `"..."` on overflow.
- `songsSeen` increments on natural track advance only; DUT skips and back-navigation do not increment.
- No regression in tap-to-play (TASK-021) or PLEDIT chrome (TASK-047).
