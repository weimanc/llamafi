# Design — M-LIST-v3 Playlist Interactivity

> Owner: Developer
> Status: planned (2026-05-15)
> Tracked-as: TASK-051a–f
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

## Exit criteria

- Selected row highlight follows playing track within one poll; optimistic highlight appears immediately on tap.
- With queue > 5 items, swipe up/down scrolls visible window; all rows reachable.
- Scrollbar thumb position matches scroll position.
- Track change snaps view to show currently-playing in row 0.
- No regression in tap-to-play (TASK-021) or PLEDIT chrome (TASK-047).
