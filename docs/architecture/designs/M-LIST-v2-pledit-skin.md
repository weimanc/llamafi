# Design — M-LIST-v2 Winamp PLEDIT Playlist Skin

> Owner: Developer
> Status: planned (2026-05-15)
> Tracked-as: TASK-047a–e
> Deps: M-LIST (TASK-020 done), M2 bake pipeline, M3 renderer
> Decision: ADR-018

## Scope

Replace plain-black row list from TASK-020 with proper Winamp Playlist Editor (`PLEDIT.BMP`) skin. Option C hybrid: baked title bar (14 px) + bottom bar (16 px) + `SKIN_PLEDIT_ROW_HIGHLIGHT` sprite; 5 track rows with `MM:SS` duration right-aligned; total playlist time in bottom bar.

## Decisions (ADR-018)

| Decision | Choice |
|---|---|
| Fitting strategy | Option C — PLEDIT title bar + bottom bar baked; 5 track rows |
| Row count | 5 (authenticity over count) |
| Duration format | `MM:SS` right-aligned per row |
| Scrollbar | Static decoration (tier 1); live position deferred tier 2 |
| Total time | Sum `durationMs`, rendered in PLEDIT bottom bar time slot |

## Sub-tasks

| Task | Scope | Tier |
|---|---|---|
| TASK-047a | `bake_skin.py` PLEDIT extraction + atlas + preview | 1 |
| TASK-047b | `durationMs` in `QueueEntry` + `getQueue()` filter | 1 |
| TASK-047c | `drawPlaylist()` redesign — PLEDIT chrome + row format | 1 |
| TASK-047d | Total time in PLEDIT bottom bar | 1 |
| TASK-021 | Tap-on-row → play that track | 2 (deferred) |
| TASK-047e | Scrollbar live position | 2 (deferred) |

## Exit criteria

- `gen/skin_preview.png` shows PLEDIT title bar + 5 rows + bottom bar below main chrome.
- DUT: PLEDIT title bar at `y=116`, bottom bar at `y=224`.
- DUT: row 0 `► Artist - Title   MM:SS` with PLEDIT highlight bg.
- DUT: rows 1-4 PLEDIT green text, right-aligned `MM:SS`, black bg.
- DUT: total time in bottom bar time slot.
- Flash delta ≤ +2% on `cyd2usb_winamp`.
- `sha256sum -c golden.sha256` passes after re-bake.
- No regression in main chrome.
