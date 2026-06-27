# M-RECLAIM — Make resident components dynamic (Q2/Q3/Q4)

> Owner: Architect · Status: **DESIGN (offline; no DUT)** · 2026-06-27
> Parent: M-MEMBUDGET §2c (the ~24–27 K + TLS overlay reclaim). Couples: TASK-259 (player mode-state).
> Feeds: PROP-membudget-spike Phase 3 (overlay financing of the WebRadio arena). Candidate → ADR-047.

## Goal

Convert three *resident* memory consumers into *lifecycle-scoped* ones so their RAM is reclaimed when their
owning app is not active — specifically so it is free **when WebRadio is the active mode** and can finance the
~40 K audio arena (M-MEMBUDGET OQ3). Targets and their reclaim:

| | Component | Used by | Reclaim | Difficulty |
|---|---|---|---|---|
| **Q3** | spotifyTask stack + TLS working set | Spotify only | ~10 K + TLS | medium (needs teardown + null-safety) |
| **Q2** | dataTask stack | 5 fetcher apps | 11–14 K | medium-hard (sharing + churn) |
| **Q4** | heatmap static doc | Stock only | 2.5 K | trivial mechanism, **but** see the fragmentation counter-rationale |

This is **mechanism design only** — sizes (esp. the TLS working set) are confirmed by the spike's Phase 0,
not here.

## The lifecycle seam (already exists)

`App` (`appShell.h:9`) has `init()` / `resume()` / `suspend()` / `tick()` / `handleInput()`. `switchApp()`
(`main.cpp:1762`) already calls `suspend()` on the outgoing app and `init()` (first time) / `resume()` on the
incoming one. **These are the triggers** — no new framework needed. The player mode-state (TASK-259) adds the
Spotify⇄WebRadio sub-state, which is the trigger for Q3 (see §Q3).

### Suspend vs delete — the core architectural choice

FreeRTOS `vTaskSuspend()` keeps the stack allocated (parks the task) → **no RAM reclaim.** Only
`vTaskDelete()` of a *heap-stack* task (our `xTaskCreatePinnedToCore` tasks are heap-stack) frees the stack.
So **reclaiming the stack requires delete, not suspend.** But the heavy, variable part — the **TLS working
set** — is freed by `client.stop()` / `resetTls()` independently of the task's existence. This splits Q3 into
two options of increasing aggressiveness (see §Q3).

## Q3 — spotifyTask dynamic (highest value)

**Current:** `begin(spotifyObj)` (`spotifyTask.h:101`) creates the task once, guards double-begin
(`spotifyTaskStorage.cpp:448`); **no `stop()`**. Unconditional accessors: `isHealthy` / `authError` /
`connecting` / `hasPendingActions` / `stackHighWaterBytes` / `stackSizeBytes` / `copySnapshot` /
`copyQueueSnapshot` / `tlsYield` / `tlsResume` / `enqueue` / `dbg_get` / `dbg_set` / `resetTls` /
`resetBackoff`. Trigger = TASK-259 player mode toggle (Spotify→WebRadio drops it; WebRadio→Spotify restores).

**Two options:**

- **Q3-a (light — RECOMMENDED v1): keep the task, drop the TLS connection on mode-leave.** On
  toggle-to-WebRadio, signal the task to `client.stop()` + `resetTls()` and idle (it already has a
  TLS-yield/stop path via `tlsYield()`/`resetTls()`). Reclaims the **TLS working set** (the heavy, variable
  part); leaves the 10 K stack resident. **No accessor null-safety problem** (task + object still exist), no
  re-create. Simplest, safe, gets the larger half of the reclaim.
- **Q3-b (full — v2 if the extra 10 K is needed): add `stop()` = `vTaskDelete(g_taskHandle)` + free.**
  Reclaims TLS **+ the 10 K stack**. Requires: (1) a **null-safety contract** — every unconditional accessor
  above must return a safe default when `g_taskHandle == nullptr` (this is the LL-085 trap; TASK-255 already
  enumerated the same accessor list for `-DDISABLE_SPOTIFY`, so the audit is shared work); (2) `begin()`
  becomes re-entrant (re-create after delete); (3) reconnect/re-auth latency on toggle-back (token refresh +
  TLS handshake) — masked behind ADR-046's "connecting" bar; the refresh token is already persisted.

**Recommendation:** ship **Q3-a** first (most of the reclaim, none of the null-safety risk), promote to
**Q3-b** only if the spike's Phase 1 shows we still need the extra 10 K after Q3-a + Q2 + Q4.

## Q2 — dataTask dynamic (medium-hard)

**Current:** `begin()` (`dataTask.h:116`) creates once; no `stop()`. Shared by **5** apps (Weather, Crypto,
Stock, Teletext, WebRadio-station-fetch). 11–14 K stack.

**Design:** reference-count the data consumers, not the app. Create dataTask lazily when entering *any* fetcher
app (or on the first `enqueue*`), delete it when leaving the last one. Subtleties:

- **WebRadio sequencing:** WebRadio needs dataTask **only** to fetch its station list, then never during play
  (M-MEMBUDGET ¹). So WebRadio entry = `dataTask up → fetch stations → dataTask down → reserve/own arena →
  play`. The teardown must wait for the in-flight fetch to drain (the task's queue empties + result polled).
- **Churn vs reclaim (the real tension):** reclaim **requires** a heap stack freed on delete; a *static*
  stack (`xTaskCreateStatic`) would avoid create/delete fragmentation **but cannot be reclaimed** (it's
  permanently reserved) — so the two goals conflict. Resolution: deletes/creates happen only on **app
  switches** (low-frequency, user-driven, not a hot loop), and the freed 11–14 K is one large contiguous
  block returning cleanly to the pool. Low-frequency churn is acceptable; **do not** static-park if the goal
  is reclaim.
- **Verdict:** real reclaim, but **second priority** to Q3 — defer unless the spike's Phase 1 shows a
  shortfall after Q3 + Q4. If pursued, it pairs naturally with the WebRadio entry sequence above.

## Q4 — heatmap static doc (trivial mechanism, non-trivial rationale)

**Current:** `static DynamicJsonDocument s_heatmapDoc(2560)` (`dataTaskStorage.cpp:616`), file-scope.
**It is static on purpose** — the comment at `:684` says "pre-allocated at startup (avoids malloc failure
from heap fragmentation)." So the naive "make it a per-fetch local" **re-introduces the exact fragmentation
failure it was added to avoid** (a mid-run 2.5 K `DynamicJsonDocument` alloc can fail on a fragmented heap).

**Design (Stock-app-lifetime ownership, not per-fetch):** move the doc from file-scope-static to **owned by
the Stock app's lifecycle** — allocate it in Stock's `init()`/`resume()` (on app-entry, when the heap is more
contiguous than deep mid-fetch), hold it for the app's active lifetime, free it in `suspend()`. This:
- reclaims the 2.5 K whenever Stock is **not** active (incl. WebRadio mode) — the goal;
- **preserves** the anti-fragmentation property — the doc is allocated once on entry and reused across fetches
  while Stock is active, never malloc'd mid-fetch.

Trivial code, but the design point is: **own it by app lifetime, do not make it per-fetch.**

## Ordering & dependencies

1. **Q4** first (smallest, self-contained, no task surgery; validates the "app-lifetime ownership" pattern).
2. **Q3-a** next (highest value, low risk; trigger wired to TASK-259 mode-state).
3. **Q3-b / Q2** only if the spike's Phase 1 shows Q4 + Q3-a leave us short — both carry real cost
   (null-safety audit; churn sequencing) for incremental reclaim.

Hard dependency: **Q3 trigger = TASK-259** (the Spotify⇄WebRadio mode-state). Q4 and the Q2 mechanism are
independent of TASK-259.

## Risks

- **(R1) Accessor null-deref (Q3-b)** — an unconditional `spotifyTask::` accessor called after delete. LL-085
  family. Mitigation: the shared null-safety contract + a `static_assert`/test gate; reuse TASK-255's audit.
  Q3-a sidesteps this entirely (task object survives).
- **(R2) Reconnect latency (Q3-b)** — toggle-back to Spotify pays TLS re-handshake. Mitigation: cached refresh
  token + "connecting" bar (ADR-046).
- **(R3) Churn fragmentation (Q2)** — repeated create/delete of the 11–14 K stack. Mitigation: low-frequency
  (app-switch only); accept, or don't pursue Q2.
- **(R4) Heatmap fragmentation regression (Q4)** — re-introducing the malloc-failure the static avoided.
  Mitigation: app-lifetime ownership (alloc on entry, not per-fetch) — designed in above.

## Verification (offline-checkable now; DUT later)

- **Build gates:** `run/check` stays green; default `.elf` section hashes unchanged for paths not touched.
- **Null-safety audit (Q3-b):** static review that every unconditional `spotifyTask::` accessor has a
  task-absent safe path (shared with TASK-255).
- **DUT (later, via the spike):** heap probes confirm the reclaim actually lands when WebRadio is active
  (Phase 0/3 of PROP-membudget-spike); reconnect-latency measurement on toggle-back (Q3-b/Phase 3).

## Open questions

- **OQ1:** TLS working-set size — is Q3-a's TLS-only reclaim enough, or do we need Q3-b's stack too? (Phase 0.)
- **OQ2:** Q2 reference-counting granularity — per-app-entry vs first-`enqueue` / last-poll-drained.
- **OQ3:** does Q4's app-lifetime doc move under the reserved arena later (so even its alloc is fragmentation-
  proof), or stay on the general heap? Defer to the arena design.

## Links

M-MEMBUDGET (§2c reclaim arithmetic, the parent budget) · PROP-membudget-spike (Phase 1 decides how much
reclaim we actually need; Phase 3 measures it) · TASK-259 (player mode-state — the Q3 trigger) · TASK-255
(parked `-DDISABLE_SPOTIFY` — its accessor null-safety audit is shared with Q3-b) · LL-085 (the null-safety
trap this design must not re-create).
