# M-DATATASK-PROGRESS — Live dataTask progress indicators for long-running fetches

> Owner: Architect  
> Status: design  
> Created: 2026-06-12

---

## Problem

`fetchStockQuote()` (and other multi-step dataTask functions) run entirely on Core 0. They publish a single atomic result at the very end — or nothing at all if they hang. Core 1 (serial handler, StockApp tick) has zero visibility into in-progress state.

When T170 fails with "quoteOkCount did not advance within 65 s", the serialdbg interface is fully responsive on Core 1, but querying `fetchFailed` / `fetchErrorCode` returns the last *committed* state — which is the default (false / 0) if the function never completed. The test can tell that nothing arrived; it cannot tell where the function is stuck or why.

The same blind-spot exists for any dataTask function that issues multiple sequential HTTP requests:

| Function | Steps | Blind-spot |
|---|---|---|
| `fetchStockQuote()` | 8 consecutive Yahoo Finance TLS connections | Which ticker (0–7) is hanging |
| `fetchStockChart()` | 1 Yahoo Finance connection + streaming parse | Whether TLS or parse is slow |
| `fetchCrypto()` | 1 CoinGecko connection | TLS vs parse vs JSON key lookup |
| `fetchWeather()` | 1 OpenMeteo connection | Same |

Imposing per-connection `http.setTimeout()` would mask the symptom without exposing the cause. A live progress indicator visible to Core 1 while Core 0 is mid-fetch is the right diagnostic layer.

---

## Proposed design

### Core primitive: per-function progress atom

Add a `volatile int8_t` (or `volatile uint8_t`) progress variable per long-running fetch, updated atomically at the start of each discrete step. Value semantics:

| Value | Meaning |
|---|---|
| `-1` | Idle (function not running) |
| `0..N-1` | Step N currently in progress |
| `-2` | Complete (set on normal exit, cleared to -1 by next enqueue) |

Because Core 0 writes and Core 1 reads, `volatile` is sufficient for single-scalar progress — no spinlock needed (torn reads are impossible on 32-bit aligned access; `int8_t` is a single byte).

### Initial implementation: `fetchStockQuote()`

```cpp
// dataTaskStorage.cpp
static volatile int8_t s_stockQuoteProgress = -1;  // -1=idle, 0-7=ticker index

static void fetchStockQuote() {
    s_stockQuoteProgress = 0;  // entering fetch
    spotifyTask::tlsYield();
    ...
    for (int i = 0; i < 8 && r.ok; i++) {
        s_stockQuoteProgress = (int8_t)i;   // which ticker we are fetching
        ... http.GET() ...
    }
    ... publish result ...
    s_stockQuoteProgress = -1;  // idle
}
```

Expose via `dataTask.h`:
```cpp
int8_t stockQuoteProgress();   // -1=idle, 0-7=ticker index in flight
```

Global serial handler (`main.cpp`):
```cpp
if (strcmp(args, "stockQuoteProgress") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stockQuoteProgress\","
                  "\"val\":%d,\"last\":true}\n", dataTask::stockQuoteProgress());
}
```

### Test usage (T170 improved failure path)

Instead of a flat 65 s wait that silently expires, T170 polls both `quoteOkCount` (completion) and `stockQuoteProgress` (in-progress). On timeout:

```python
r_prog = dut.cmd("get stockQuoteProgress", timeout=3.0)
ticker_idx = r_prog.get("val", "?")
ticker_name = tickers[ticker_idx] if isinstance(ticker_idx, int) and 0 <= ticker_idx < 8 else "?"
fail("T170", f"quoteOkCount did not advance — stuck on ticker {ticker_idx} ({ticker_name})")
```

This turns "quoteOkCount did not advance within 65 s" into "stuck on ticker 4 (ARM)" — a specific, actionable failure message.

Optionally: detect stalls mid-wait rather than only at timeout:

```python
last_progress = None
last_progress_time = time.monotonic()
while time.monotonic() < deadline:
    prog = dut.cmd("get stockQuoteProgress", ...)
    if prog != last_progress:
        last_progress = prog
        last_progress_time = time.monotonic()
    elif time.monotonic() - last_progress_time > 20.0:
        fail("T170", f"stockQuoteProgress stuck at {last_progress} for >20 s")
        return
    if quoteOkCount_advanced: break
    time.sleep(2.0)
```

---

## Open question: where else does this pattern apply?

This pattern is valuable anywhere a Core 0 dataTask function has multiple discrete steps that Core 1 tests or apps may want to observe in real time. Candidates:

| Function | Steps | Progress indicator candidates |
|---|---|---|
| `fetchStockQuote()` | 8 ticker fetches | `stockQuoteProgress` (ticker index 0–7) |
| `fetchWeather()` | 1 HTTP + 1 JSON parse | `weatherFetchPhase` (0=TLS, 1=GET, 2=parse, -1=idle) |
| `fetchCrypto()` | 1 HTTP + 1 JSON parse | `cryptoFetchPhase` |
| `fetchHeatmapQuote()` | 1 HTTP + streaming parse | `heatmapFetchPhase` |
| dataTask queue depth | N items waiting | `dataTaskQueueDepth` (already partially addressable via `get` commands) |
| SPIFFS load at boot | multi-file read | not a dataTask item but same principle |

The weather and crypto cases are simpler (1 connection) but the phase indicator is still valuable: "TLS handshake vs read vs parse" tells you whether a -1 is a connectivity failure or a JSON issue.

**Broader principle:** any firmware function that:
1. Runs on a different thread/core from the serial handler, AND
2. Has multiple distinct phases or sub-steps, AND
3. Can take >5 s to complete

…is a candidate for a volatile progress indicator visible to the serial debug layer. This is a general testability pattern, not a one-off fix.

---

## Scope for initial implementation (M-DATATASK-PROGRESS phase 1)

Implement only `fetchStockQuote()` progress — this is the confirmed pain point. Use it to validate the pattern and refine the test-side polling idiom before applying it elsewhere.

Phase 2 (if the pattern proves useful in VE): extend to `fetchWeather()` and `fetchCrypto()` using the same `volatile int8_t` primitive and the same serialdbg exposure pattern.

---

## Constraints and non-goals

- **No timeout introduced.** The progress indicator is diagnostic only; the fetch runs at its natural pace. If a ticker genuinely hangs, the progress indicator says which one — the decision about what to do is left to the test or operator.
- **No lock needed** for a single `volatile int8_t` updated and read by two cores (ESP32 is 32-bit, byte writes are atomic; no partial-word tear possible).
- **Not a replacement for `fetchFailed` / `fetchErrorCode`** — those still capture the committed result. This captures in-progress state.
- **Not a queue-split refactor** — splitting `fetchStockQuote()` into 8 individual queue items is a valid architectural improvement but a separate decision. This design adds observability without restructuring.
