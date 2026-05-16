# Design — M-CONN Connection Health UI + TLS Recovery Controls

> Owner: Developer
> Status: implemented (2026-05-16); DUT validation outstanding
> Tracked-as: TASK-053a–f
> Deps: TASK-052 (M-IO backoff reset), M-CHROME (TITLEBAR.BMP bake), m3-001 renderer

## Feature 1 — Inactive title bar variants

`TITLEBAR.BMP` (344×87): row 0 = active, row 1 = inactive (dimmer, greyed palette).
`PLEDIT.BMP` (280×186): row 0 = active PLEDIT title, row 1 = inactive.

Approach:
- Bake both active + inactive variants → `SKIN_TITLEBAR_ACTIVE/INACTIVE`, `SKIN_PLEDIT_TITLE_ACTIVE/INACTIVE` in `gen/skin_assets.c` + `gen/skin_layout.h`.
- `spotifyTask::isHealthy()` returns true if `s_consecutiveFailures < 2`.
- `drawChrome()` + `drawPlaylist()` read `isHealthy()`, blit matching variant. Switch triggers forced title-bar redraw (bypass seqno gate for that element only).

Sub-tasks: TASK-053a (bake sprites), TASK-053b (`isHealthy()` + state propagation), TASK-053c (renderer switch).

## Feature 2 — Serial `reconnect` command

- Main `loop()` checks `Serial.available()`. Line `"reconnect\n"` → call `spotifyTask::resetTls()` + enqueue `ACT_FORCE_POLL`.
- `resetTls()`: `stop()` on `WiFiClientSecure` inside `SpotifyArduino` (patch lib to expose `void resetClient()`); zero `s_consecutiveFailures`.

Sub-task: TASK-053e.

## Feature 3 — Winamp logo tap → TLS reset

Logo sits at bottom-right of `MAIN.BMP` (~`x=250..274, y=100..115`; confirm via bake-tool inspection).

Approach:
- `hitTestLogo(int sx, int sy)` in `WinampDisplay` — returns true if tap lands in logo rect (adjusted by `originX/originY`).
- On hit: `spotifyTask::resetTls()` + `enqueue(ACT_FORCE_POLL)` + `resetBackoff()`. Log `[conn] logo tap → TLS reset`.
- 2 s cooldown (separate from `touchScreenCoolDownTime`).
- No optimistic UI — wait for next successful poll to restore active title bars.

Sub-task: TASK-053f.

## Exit criteria

- After 2+ consecutive poll failures, both title bars switch to inactive within one render cycle.
- On poll success, title bars restore to active.
- `reconnect\n` on serial closes TLS, triggers fresh poll, logs confirmation.
- Logo tap closes TLS, triggers fresh poll; title bars restore if poll succeeds.
- No regression in transport controls, posbar, volume, PLEDIT tap-to-play.
