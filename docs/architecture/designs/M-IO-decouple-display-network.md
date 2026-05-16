# Design — M-IO Decouple Display from Blocking Network Calls

> Owner: Developer / Architect
> Status: done (TASK-019 async FreeRTOS poll; TASK-052 tap resets backoff 2026-05-16)
> Tracked-as: TASK-019, TASK-052

## Problem

Symptoms observed 2026-05-07 M3 DUT verify:
- Slow first sync after boot.
- Occasional hangs — clock + progress thumb stop advancing.
- LCD shows previous track for many seconds after Spotify moved on.
- Heartbeat captured 56 s gaps between ticks during TLS retries.

Root causes confirmed: synchronous `getCurrentlyPlaying` blocks renderer for full TLS+HTTP duration; HTTP retry storms on TLS handshake failure; 5 s `delayBetweenRequests` too long for short tracks.

## Tier 1 — Done (TASK-019)

Async Spotify poll via FreeRTOS task (ADR-011 / ADR-012). Poll runs on APP_CPU; main loop reads snapshot slot without blocking.

## Tier 2 — TASK-052 (planned)

Any tap resets backoff + force-polls; 1 s cooldown on dead zones. Ensures a user tap always escapes a backoff run within one poll cycle.

## Exit criteria

- Heartbeat gap distribution stays under 5 s p95 across normal play.
- Any screen tap escapes a backoff run within one poll cycle (TASK-052).
