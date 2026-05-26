# Design — Heap Arbitration: Sprite Apps vs. SSL Tasks

> Owner: Architect
> Status: draft
> Date: 2026-05-26
> Feeds: ADR-032
> Tracked-as: (unscheduled — pending PM)

---

## Context / pain points

The aquarium app allocates a 275 × h px 8-bit sprite from the ESP32 internal heap.
With `maxAllocHeap ≈ 40.9 KB`, the dynamic-sizing logic (M-AQUARIUM ADR-031 follow-on)
computes `h = 119`, giving a sprite of 32 725 bytes — within the available block.

After sprite allocation the remaining contiguous heap is ≈ 8 KB. The mbedTLS SSL
handshake requires a single contiguous allocation of ≈ 36 KB. While the sprite is held,
every SSL connection from `dataTask` (weather, crypto) fails with
`2) SSL - Memory allocation failed`, falling back to a `-1` HTTP result.

The degradation is **graceful** (data tasks retry; stale data is shown; updates resume
within one poll cycle after navigating away from the aquarium), but it represents a
correctness gap: background data should update independently of the active app.

**Observed evidence (2026-05-26 serial log):**

```
[aquarium] resume sprite: OK  heap=78444 maxAlloc=40948
2) SSL - Memory allocation failed   ← dataTask.weather
2) SSL - Memory allocation failed   ← dataTask.crypto
[I][hb] display=winamp heap=100k    ← aquarium suspended; SSL recovers next poll
[D][dataTask.crypto] GET 200 ok
```

This problem is latent in any app that holds a large contiguous heap allocation while
background tasks perform SSL. The aquarium is the first such app; the pattern may recur
(e.g. a future album-art or visualization app with a sprite).

---

## Goals

1. Weather and crypto fetches succeed at least once per poll interval regardless of
   which app is active.
2. No TFT_eSprite operation is ever called from a non-loop() thread (thread-safety
   invariant of TFT_eSPI).
3. The mechanism is opt-in: apps that do not hold large heap allocations return a
   no-op default; the data task does not need to know which app is active.
4. The round-trip overhead on the main loop thread is bounded and acceptable (<< 1
   frame budget, ~30 ms).
5. No new FreeRTOS primitives (mutexes, semaphores) owned by the app layer — existing
   volatile-flag pattern used by `spotifyTask` snapshot is sufficient.

---

## Non-goals

- PSRAM (CYD has none).
- Reducing SSL buffer size (mbedTLS configuration, high risk).
- Making SSL work *concurrently* with the sprite in memory — not feasible on this heap.
- Extending this to the Spotify task (it does not use SSL while the aquarium is active;
  the Spotify SSL connection is established before the aquarium is ever launched).

---

## Design space

### Option A — Accept the conflict (status quo)

Weather/crypto fail silently while aquarium is active. Data tasks retry every 5 s.
When the user navigates away, the sprite is released and SSL succeeds within one cycle.

**Pro:** zero code change, zero complexity.  
**Con:** data is stale for as long as the user stays in the aquarium. For a screensaver-
style app that may run for many minutes, this is a real UX gap.  
**Verdict:** viable interim; not acceptable as a permanent state once the aquarium ships.

---

### Option B — App heap-yield interface (`yieldHeap` / `reclaimHeap`)

Extend the `App` interface with two new virtual methods with default no-op
implementations:

```cpp
// App voluntarily releases large heap allocations to allow system SSL.
// Called from loop() thread only. Returns true if any allocation was released.
virtual bool yieldHeap()   { return false; }

// Called from loop() thread after the heap-pressure event has passed.
// App re-acquires what yieldHeap() released.
virtual void reclaimHeap() {}
```

`AquariumApp` overrides:
- `yieldHeap()`: calls `_canvas.deleteSprite()`, sets `_spriteReady = false`, returns
  `true`.
- `reclaimHeap()`: calls `_calcDynamicSize()` + `createSprite(...)`.

The shell exposes a **heap arbitrator** (new translation unit `heapArbitrator.h`):

```cpp
namespace heapArbitrator {
    // Called by dataTask before an SSL connection.
    // Sets a volatile request flag; blocks (polls) until the active app's tick()
    // acknowledges the yield or a timeout expires.
    // Returns true if the active app yielded heap; false if timed out or no-op.
    bool request(uint32_t timeoutMs = 150);

    // Called by dataTask after the SSL connection completes (success or failure).
    // Signals the active app to reclaim.
    void release();
}
```

Threading model:
- `request()` runs on `dataTask` thread (core 1). Sets `g_heapYieldRequested = true`
  (volatile), polls `g_heapYieldAcknowledged` with a bounded spin (~150 ms max).
- Active app's `tick()` runs on `loop()` thread (core 0). Checks
  `g_heapYieldRequested`; if set, calls `yieldHeap()`, sets `g_heapYieldAcknowledged`.
- `release()` runs on `dataTask` thread. Clears both flags; active app's next `tick()`
  calls `reclaimHeap()`.
- All TFT_eSprite calls remain on the loop() thread. No cross-thread sprite access.

**Pro:** clean interface, opt-in, loop()-thread safety maintained, bounded wait.  
**Con:** adds complexity to `App` interface and shell; requires careful volatile
semantics; the 150 ms stall in `dataTask` is acceptable but must be documented.

---

### Option C — Data task polls maxAllocHeap before SSL (autonomous)

`dataTask` polls `ESP.getMaxAllocHeap()` before attempting an SSL handshake. If the
largest free block is below a threshold (e.g. 38 KB), it skips the fetch and queues a
retry after a short delay, relying on the active app eventually suspending.

**Pro:** zero change to `App` interface or shell.  
**Con:** the data task can never know when the heap will be free — this degenerates to
repeated retries identical to Option A but with an explicit threshold check. Provides
no mechanism for the app to proactively release. Rejected.

---

### Option D — Suspend sprite for the duration of every data-task fetch

`dataTask` signals a "fetch starting" event on enqueue; the app shell calls
`suspend()` on the active app unconditionally, restoring it after the fetch. The screen
goes dark (or shows a frozen frame) during every poll interval.

**Pro:** guaranteed SSL success; simplest signal path.  
**Con:** visible rendering gap every 5 s for all apps, not just aquarium. Unacceptable
UX regression. Rejected.

---

## Lean / decision

**Option B** is the correct architecture. It is the only option that:

- keeps all sprite operations on the loop() thread,
- is transparent to apps that do not hold heap (default no-op),
- bounds the stall on `dataTask` to one frame budget,
- does not impose a rendering gap on non-heap-holding apps.

The `heapArbitrator` translation unit is small (≈ 40 lines) and its interface is stable.
Option A remains acceptable as the interim state until this is implemented.

---

## Interface sketch

### `App` interface additions (`appShell.h`)

```cpp
// Heap-yield protocol. Default implementations are no-ops.
// yieldHeap():   called from loop() thread when dataTask signals heap pressure.
//                Release large contiguous allocations (e.g. sprite). Return true
//                if anything was released, false otherwise.
// reclaimHeap(): called from loop() thread after heap pressure clears.
//                Re-acquire what yieldHeap() released.
virtual bool yieldHeap()   { return false; }
virtual void reclaimHeap() {}
```

### `heapArbitrator.h` (new, `app/src/heapArbitrator.h`)

```cpp
namespace heapArbitrator {
    // Volatile flags — written from dataTask thread, read from loop() thread and back.
    extern volatile bool g_yieldRequested;    // dataTask → loop(): please yield
    extern volatile bool g_yieldAcknowledged; // loop() → dataTask: done, SSL can run
    extern volatile bool g_reclaimRequested;  // dataTask → loop(): SSL done, reclaim

    // Called from loop() — check and service any pending yield/reclaim request.
    // Must be called once per loop() iteration (e.g. at the top of the main loop,
    // before appTick).
    void service(App* activeApp);

    // Called from dataTask thread before an SSL operation.
    // Returns true if the active app yielded heap; false on timeout (SSL will likely
    // fail but that is the existing graceful-degradation path).
    bool request(uint32_t timeoutMs = 150);

    // Called from dataTask thread after the SSL operation (success or failure).
    void release();
}
```

### `dataTask` call sites (pseudo)

```cpp
// Before SSL:
bool heapYielded = heapArbitrator::request();
int httpResult   = httpsClient.get(url);
if (heapYielded) heapArbitrator::release();
```

### `loop()` integration

```cpp
void loop() {
    heapArbitrator::service(g_apps[(int)currentAppId]);  // NEW — before appTick
    appTick(currentAppId);
    appHandleInput(currentAppId);
    // ...
}
```

---

## Open questions

1. **`service()` placement**: must run every loop() to keep the stall < 1 frame
   budget. Confirm the main loop period (~20–30 ms measured) is well within the 150 ms
   timeout. If the loop can stall longer (e.g. during a large playlist render), the
   timeout needs to be extended or `service()` needs a second call site.

2. **Re-entrancy**: if `dataTask` posts two requests in quick succession (weather and
   crypto both become stale simultaneously), the second `request()` must block until the
   first `release()` completes. A simple `g_arbitratorBusy` flag in `request()` handles
   this; alternatively serialize fetches in `dataTask` (one at a time, already the case
   if the queue is depth-1 per type).

3. **VE testability**: the protocol involves two threads and timing. VE should be
   consulted on whether a host-side unit test can exercise the flag handshake, or whether
   this requires a device integration test. Recommend IFC-001 definition before
   implementation so VE can write the test plan alongside.

4. **Other heap-holding apps**: if a future app also overrides `yieldHeap()`, the
   protocol is already correct — `heapArbitrator::service()` calls `yieldHeap()` on
   whatever the active app is. No change to the arbitrator needed.

5. **`reclaimHeap()` failure**: if `createSprite` fails on reclaim (heap still
   fragmented after SSL completes), `AquariumApp` should handle this identically to the
   existing `!_spriteReady` retry path. No new failure mode introduced.

---

## Exit criteria

- [ ] `heapArbitrator::request()` / `release()` / `service()` implemented and
      building.
- [ ] `AquariumApp::yieldHeap()` and `reclaimHeap()` implemented.
- [ ] Serial log shows `[aquarium] yield → SSL → reclaim` sequence with weather/crypto
      `GET 200` while aquarium is the active display.
- [ ] No rendering artefacts: app screen is blank (or shows last frame) during yield;
      restores cleanly on reclaim.
- [ ] All other apps unaffected: switching to Clock, Matrix, Life while
      heapArbitrator is wired in produces no change in behaviour.
- [ ] `check_build.sh` passes (both targets, golden hash).
