# Design — Multi-App Shell (M-MULTIAPP)

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Feeds: ADR TBD (app-switching model)
> Split docs: [layout.md](layout.md) · [taskbar.md](taskbar.md) · [app-lifecycle.md](app-lifecycle.md) · [preview-tooling.md](preview-tooling.md)

## Context

The device currently runs a single app: the Winamp-skinned Spotify player.
The 5in1 reference project (resource/5in1) demonstrates five lightweight
apps (Clock, Weather, Crypto, Matrix rain, Game of Life) that share the same
display and switch on touch. Porting those apps creates a multi-app shell
where the Spotify player is one of several modes.

The chosen layout is **Option B — co-existence**: Winamp chrome stays on
screen, shifted to the left edge, with a 45 px icon-only taskbar on the
right. Apps do not run concurrently; the taskbar is always present and acts
as the switching mechanism.

## App registry

| ID | Name | Network? | State size |
|----|------|----------|-----------|
| 0 | Spotify / Winamp | yes (spotifyTask) | ~600 B (WinampDisplay fields) |
| 1 | Clock | NTP only (already done) | ~0 B |
| 2 | Weather | yes — Open-Meteo | ~20 B (3 floats + timestamp) |
| 3 | Crypto | yes — CoinGecko | ~80 B (9 prices + timestamp) |
| 4 | Matrix rain | no | ~140 B (14 × MatrixColumn) |
| 5 | Game of Life | no | ~2.9 KB (48×60 grid + counters) |

## Guiding decisions

- **Single active app.** No concurrent app execution. The taskbar is a
  persistent input layer, not a separate FreeRTOS task.
- **State preserved across switches.** Each app's state struct is kept in
  RAM. On switch: save active app state → clear app canvas → restore new
  app state → call app's `init()` if first launch.
- **Network apps use a dedicated FreeRTOS task** (same pattern as
  spotifyTask: queue + spinlock). Weather and Crypto share a single
  `dataTask`; Spotify keeps its own `spotifyTask`.
- **Taskbar always rendered.** The rightmost 45 px column is never cleared
  by any app. Apps constrain their canvas to x: 0..274.
- **Winamp chrome is always visible.** It is not a full-screen takeover
  app. Its 275×116 main window + 275×124 PLEDIT region fill the 275×240
  left canvas exactly.

## Work breakdown (doc references)

| Topic | Doc |
|-------|-----|
| Pixel budget, Winamp shift, canvas constraint | [layout.md](layout.md) |
| Taskbar icons, hitbox, RTOS role | [taskbar.md](taskbar.md) |
| App enum, state structs, switchApp() | [app-lifecycle.md](app-lifecycle.md) |
| bake_skin.py extension for taskbar preview (static PNG) | [preview-tooling.md](preview-tooling.md) |
| Interactive preview tooling (pygame + HTML) | [interactive-preview.md](interactive-preview.md) |
| Shell geometry header — single source of truth | [shell-layout.md](shell-layout.md) |

## Status

Draft. Taskbar aesthetics to be resolved by preview tooling before
implementation tasks are filed.
