# Design — M-PERF Profiling + Targeted Optimisation

> Owner: Developer (tier 1) / Architect (tier 2 ADRs) / Developer (tier 3 impl)
> Status: planned (added 2026-05-08)
> Tracked-as: TASK-029–033
> Deps: M-LOG (log-001 heartbeat plumbing), M3, M-IO

## Symptoms (trigger)

User-reported "LCD flicker + sluggish controls" during M5 use. Two distinct symptoms — instrument before deciding what to ship.

- **LCD/backlight flicker.** Candidates: aggressive SPI clock (55 MHz), mid-blit tear, power dip under WiFi-TX + display + JPEG decode.
- **Sluggish controls.** Partially diagnosed via M-IO `block_max_ms`: synchronous polls blocking loop ~600–2000 ms; touch not sampled during poll.

## Tier 1 — Instrumentation (TASK-029, TASK-030)

| Deliverable | Notes |
|---|---|
| Loop-iteration timer; `LOG_W` when iteration > 50 ms | adds `loop_max_ms` to heartbeat |
| `micros()` pairs around hot paths (`getCurrentlyPlaying`, `screenlog::tick`, `repaintChrome`, `displayTrackProgress`, `checkForInput`) | `path_max=<name>:Nms` in heartbeat |
| Stack high-water mark in heartbeat (`uxTaskGetStackHighWaterMark`) | stack overflow early warning |
| 40 MHz vs 55 MHz SPI A/B (build flag flip, TASK-030) | rules in/out signal-integrity flicker |

~60 LOC + one build-flag flip.

## Tier 2 — ADR decisions (gated on tier-1 data)

| ADR | Condition to write |
|---|---|
| Async Spotify poll (FreeRTOS task on APP_CPU) — TASK-031 | only if polling is confirmed bottleneck |
| DMA SPI for big blits (`tft.initDMA`, `tft.pushImageDMA`) — TASK-032 | only if blits are dominant |
| screenLog incremental redraw (diff-against-previous) — TASK-032 | only if SCREEN_LOG on by default |

## Tier 3 — Implementation (TASK-033, gated on tier-2 ADRs)

Async poll task, DMA blit paths, screenLog incremental redraw, touch debounce state-machine (replace 80 ms `delay()` with millis-tracked release-on-timer).

## Exit criteria

- Tier 1 lands; DUT data captured for ≥5 min session including at least one network blip.
- Honest diagnosis: which paths exceed 50 ms, `loop_max_ms` during touch/pause, SPI A/B flicker result.
- Tier-2 ADRs only written for paths the data justifies.
