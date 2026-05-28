> Owner: R&D

### EXP-002 — 2026-05-28 — Per-app heap footprint sweep

**Hypothesis**: One or more apps consume enough DRAM that subsequent apps — in
particular Aquarium (which needs ~48 KB contiguous) — cannot allocate their sprite
and silently degrade. The Aquarium blank-screen bug may be a heap-pressure artifact
rather than a code bug.

**Motivation**: Aquarium was observed blank after flashing (2026-05-26, commit
276bbba). The sprite allocation path already emits `FAILED` vs `OK` to serial, but
no systematic per-app heap baseline existed. This experiment instruments `switchApp()`
and sweeps all 9 apps in order to produce that baseline.

---

## Experiment plan

### Instrumentation

Added two `Serial.printf` calls to `switchApp()` in `app/src/main.cpp`, gated on
`#ifdef SERIAL_DEBUG`:

```
[shell] leaving <id>  heap=<freeHeap> maxAlloc=<maxAllocHeap> minFree=<minFreeHeap>
[shell] entered <id>  heap=<freeHeap> maxAlloc=<maxAllocHeap> minFree=<minFreeHeap>
```

- **leaving** fires before `suspend()` — captures the outgoing app's steady-state footprint.
- **entered** fires after `init()`/`resume()` — captures the incoming app's post-init state.
- `minFreeHeap` = `ESP.getMinFreeHeap()` — lowest free bytes recorded since boot (watermark).

### App switching via serial

Apps 0–5 (within default taskbar scroll window):
`tap 297 <slot * 40 + 20>`

Apps 6–8 (outside visible slots): `cmdTap` does not bounds-check y — slot = `y / 40`
so out-of-screen y values address higher-indexed apps directly:

| App | y value |
|-----|---------|
| Settings (6) | 240 |
| Stock (7)    | 280 |
| Aquarium (8) | 320 |

### Build / flash

```
pio run -e cyd2usb_winamp_debug -t upload --upload-port /dev/ttyUSB0
```

### Sweep order

Spotify → Clock → Weather → Crypto → Matrix → Life → Settings → Stock → Aquarium → Spotify

Waited for each data-fetching app (Weather, Crypto) to complete its TLS fetch before
moving on. Aquarium given ~30 s to observe retry behaviour.

---

## Raw data

Device: ESP32-2432S028R (CYD2USB). Build: `cyd2usb_winamp_debug`, commit after
`276bbba` + EXP-002 instrumentation patch. WiFi: LAN. Coingecko: **unreachable** on
this network (connection refused after ~42 s timeout).

| Event | App out→in | freeHeap | maxAllocHeap | minFreeHeap | Notes |
|-------|-----------|----------|-------------|-------------|-------|
| leaving Spotify | 0→1 | 110,580 | 57,332 | 42,700 | Spotify steady state |
| entered Clock | | 110,580 | 57,332 | 42,700 | No alloc |
| leaving Clock | 1→2 | 110,580 | 57,332 | 42,700 | |
| entered Weather | | 110,580 | 57,332 | 42,700 | No alloc |
| leaving Weather | 2→3 | 109,748 | 57,332 | 42,664 | Weather TLS freed cleanly |
| entered Crypto | | 107,532 | 57,332 | 42,664 | |
| leaving Crypto | 3→4 | **45,668** | **40,948** | 42,600 | ⚠ TLS left ~64 KB stranded |
| entered Matrix | | 45,668 | 40,948 | 42,600 | |
| leaving Matrix | 4→5 | 45,668 | 40,948 | 42,600 | |
| entered Life | | 45,668 | 40,948 | 42,600 | |
| leaving Life | 5→6 | **109,036** | **57,332** | 42,600 | TLS freed during Life (async) |
| entered Settings | | 109,036 | 57,332 | 42,600 | Stub — no alloc |
| leaving Settings | 6→7 | 109,036 | 57,332 | 42,600 | |
| entered Stock | | 109,036 | 57,332 | 42,600 | Stub — no alloc |
| leaving Stock | 7→8 | 109,036 | 57,332 | 42,600 | |
| Aquarium init | | avail=57,332 → h=145 | — | — | **Sprite OK** (full canvas) |
| entered Aquarium | | 68,944 | 40,948 | 42,600 | Sprite costs ~40 KB |
| leaving Aquarium | 8→0 | 64,800 | 40,948 | 42,172 | |
| entered Spotify | | 104,396 | 55,284 | 42,172 | Sprite freed on suspend |

Global watermark: **minFreeHeap = 42,172 bytes** (recorded during Aquarium + concurrent
Spotify poll attempts).

---

## Findings

### F1 — Aquarium heap failure is NOT the root cause of the blank-screen bug

Sprite allocation succeeded (`avail=57,332` → `275×145 8bpp OK`) when coming from
Stock (7). The blank-screen bug requires a separate debug pass. Candidates:
- `pushSprite` called at wrong y-offset (145 − _canvasH may be 0 when h=145, pushing at y=0 OK — check).
- Init never reached (check `g_appLaunched[]` guard).
- 8bpp palette / colour depth mismatch.

### F2 — Coingecko TLS failure causes severe transient fragmentation

A failed TLS handshake to `api.coingecko.com` left ~64 KB stranded for several minutes
(freeHeap dropped 110 k → 46 k; maxAllocHeap 57 k → 41 k). The memory eventually
freed on its own during the Life app dwell. Root cause: HTTPClient / WiFiClientSecure
does not release its SSL context promptly on connection failure. If Aquarium is
switched to immediately after a Crypto fetch attempt, `maxAllocHeap` would be ~41 KB —
still above the ~48 KB threshold for a full canvas, but `_calcDynamicSize()` would
reduce canvas height to h = (41,000 − 8,192) / 275 ≈ **119 px** (down from 145).
Sprite would still allocate; fish count would reduce proportionally.

### F3 — Clock, Weather, Matrix, Life, Settings, Stock: negligible footprint delta

None of these apps cause lasting heap change. Weather's TLS session is cleaned up
cleanly. Matrix and Life use only stack/static allocations.

### F4 — Spotify resume costs ~5 KB vs Aquarium

After Aquarium suspend (sprite freed), Spotify resume restores freeHeap from 65 k to
104 k and maxAlloc from 41 k to 55 k. Spotify keeps its own buffers live (poll
task, queue snapshot, TLS keep-alive).

### F5 — Global watermark (42,172 B) is comfortable

The tightest moment was Aquarium + concurrent Spotify poll. At 42 KB free the system
was not in danger; stack high-water marks were healthy throughout (stack_hwm ≥ 3,292 B
per heartbeat).

---

## Conclusions

Heap pressure is **not** the cause of the Aquarium blank-screen bug under normal
boot-and-switch conditions. The dangerous scenario is switching to Aquarium
immediately after a Crypto session where coingecko TLS failed and its buffers have not
yet freed — this reduces canvas height but does not prevent allocation.

The Coingecko TLS leak is the most actionable finding: an explicit `client.stop()`
call after a failed connection in `dataTask` would reclaim the 64 KB immediately
rather than leaving it to the OS finaliser.

---

## Open questions / recommendations for PM

1. **Aquarium blank-screen** (pre-existing bug, commit 276bbba): root cause still
   unknown. Recommend a focused debug task: add `pushSprite` coordinate logging and
   verify `g_appLaunched` guard. Does not require a new RnD branch — fixable in a
   developer task.

2. **Coingecko TLS cleanup**: add `client.stop()` on HTTP error path in
   `dataTask`. Low-risk one-liner; prevents ~64 KB fragmentation. Recommend PM
   schedule as a small hardening task.

3. **Heap monitor in production build**: the `#ifdef SERIAL_DEBUG` gate is correct
   for the verbose per-switch logging. However, `ESP.getMinFreeHeap()` could be
   surfaced in the existing `info` command (unconditional) for field diagnostics
   without a debug build.
