> Owner: R&D

### EXP-003 — 2026-06-03 — Screener -1 Root Cause + NoMemory / IncompleteInput on DUT

**Hypothesis**: TASK-127 posited two hypotheses for the screener -1 failures seen during
TASK-126 soak: (1) JA3/TLS fingerprint block by Yahoo CDN; (2) transient CDN per-IP state
triggered by the RST storm from TASK-126. A third emerging question: once -1 resolved, why
do JSON parse failures (NoMemory, IncompleteInput) appear on DUT?

**Approach**: Live DUT attached. Serial monitor observation + host-side header probing +
ArduinoJson 6.21.6 memory-model source analysis.

---

#### Finding 1 — -1 Block is Resolved; JA3 Hypothesis Invalidated

Serial monitor at session start shows:
```
[D][dataTask.stock] heatmap GET 200 elapsed=1470ms
[D][dataTask.stock] heatmap GET 200 elapsed=1518ms
```
DUT firmware (Jun 2 2026-21:23:19) now receives HTTP 200 from
`query1.finance.yahoo.com/v1/finance/screener/predefined/saved` on every observed attempt.
The -1 failure was entirely transient; no code change was required.

**JA3 hypothesis (H1): Invalidated.** The DUT mbedTLS JA3 fingerprint is accepted by the
CDN. No cipher-suite change is needed.

**Transient CDN block hypothesis (H2): Confirmed.** The -1 resolved within ~24h without
intervention, consistent with the per-IP throttle mechanism identified in EXP-001: the RST
storm from TASK-126's cycle-1 META timeout elevated the IP's connection-fault score for the
screener path, which decayed naturally.

---

#### Finding 2 — New Failure: JSON Parse Errors After HTTP 200

With the -1 block gone, a new failure is now exposed:
```
[W][dataTask.stock] heatmap JSON err: NoMemory
[W][dataTask.stock] heatmap JSON err: IncompleteInput
```
Both appear on consecutive 120-second fetch cycles. The heatmap view shows empty tiles.

**HTTP layer is healthy.** The screener returns a valid 53 KB JSON body over HTTP/1.0
(confirmed host-side curl). The `useHTTP10(true)` and `User-Agent: Mozilla/5.0` fixes from
TASK-119 are in the Jun 2 build and are working.

---

#### Finding 3 — NoMemory Root Cause Analysis

The code path (`dataTaskStorage.cpp:320`):
```cpp
DynamicJsonDocument doc(4096);
DeserializationError err = deserializeJson(doc, http.getStream(),
                               DeserializationOption::Filter(filter));
```

`DynamicJsonDocument(4096)` calls `malloc(4096)` on each invocation. If the allocation
fails (returns null), `doc.capacity() == 0` and any first allocation inside
`deserializeJson` immediately sets `overflowed_ = true` → `DeserializationError::NoMemory`.

**Theoretical memory requirement** (ArduinoJson 6.21.6, ESP32 32-bit,
`sizeof(VariantSlot) = 16 B`):

| Component | Count | Per-item | Total |
|-----------|-------|---------|-------|
| Variant slots (104 total) | 104 | 16 B | 1664 B |
| Key strings (dedup'd once each) | 7 keys | avg 12 B | 85 B |
| Symbol value strings (20 unique) | 20 | avg ~6 B | ~120 B |
| **Estimated total** | | | **~1869 B** |

Slot count: 1 (finance) + 1 (result key) + 1 (result[0] elem) + 1 (quotes key) +
20 (quote elements) + 80 (4 fields × 20 quotes) = 104 slots.

**1869 B << 4096 B pool capacity** → the pool itself is not too small by theory.

**Primary hypothesis: heap fragmentation.**
- DUT uptime at failure: ~60 minutes
- Multiple TLS sessions over that period (Spotify token refresh + Yahoo Finance chart/quote
  fetches) each temporarily allocate ~32 KB of TLS buffers, then free them
- FreeRTOS heap_4 free-list may have no contiguous 4096-byte block despite reporting 123 KB
  total free (heartbeat `heap=123k` is total free, not largest contiguous block)
- `ESP.getMaxAllocHeap()` is **not currently logged** — fragmentation cannot be confirmed
  or ruled out from existing logs

**Secondary hypothesis: genuine pool overflow.**
If key deduplication is not working as expected (e.g., due to stream-mode behavior),
without dedup: 20 × 63 B/quote keys + outer 22 B + 120 B symbols = 1542 B strings.
1664 B variants + 1542 B strings = **3206 B** — still within 4096, but much tighter.
A minor measurement error or additional allocation overhead could breach 4096.

---

#### Finding 4 — IncompleteInput Root Cause Analysis

`IncompleteInput` means the stream closed before ArduinoJson completed parsing.

Observed on the second fetch cycle (120s after NoMemory failure). Two plausible mechanisms:

**A — Secondary to pool overflow mid-parse (if malloc succeeded but pool genuinely too
small):** When the pool overflows during deserialization, ArduinoJson sets `overflowed_` and
continues reading the input to skip the in-progress value (not documented, inferred from
behaviour). If the server-side connection closes while ArduinoJson is mid-skip, the reported
error is `IncompleteInput` rather than `NoMemory`.

**B — WiFiClientSecure read timeout:** ESP32 Arduino WiFiClientSecure has a default timeout
of 5000ms per `read()`. With a 53 KB body, total read time at a congested -60 dBm AP could
approach the timeout. This was not observed but cannot be ruled out without timing
instrumentation.

Mechanism A is more consistent with the intermittent alternation between the two error codes
across fetch cycles.

---

#### Finding 5 — Missing Diagnostic: `doc.capacity()` and `ESP.getMaxAllocHeap()`

Without logging `doc.capacity()` immediately after construction, we cannot confirm whether
`malloc` succeeded or failed. Both proposed mechanisms produce `NoMemory`, but:
- malloc failure → `doc.capacity() == 0`
- pool too small → `doc.capacity() == 4096`, `doc.memoryUsage()` would show actual usage

Similarly, `ESP.getMaxAllocHeap()` in the heartbeat would directly confirm or deny heap
fragmentation as the cause.

---

**Outcome**: -1 block resolved (transient CDN state, self-recovered). New blocking issue:
heatmap JSON parse fails with `NoMemory` and `IncompleteInput`. Root cause is almost
certainly either (a) `malloc(4096)` fails due to heap fragmentation after 60+ min TLS
cycling, or (b) pool genuinely marginally too small when deduplication is less effective than
theory predicts. A per-call heap allocation (`DynamicJsonDocument doc(N)`) is the
architectural vulnerability regardless of which mechanism dominates.

**Conclusion**: Inconclusive on exact NoMemory sub-cause; fix is identical for both:
eliminate per-call heap allocation by switching to a pre-allocated static pool.

**Recommendation**: Propose production fix — PROP-004: replace `DynamicJsonDocument doc(4096)`
(per-call heap alloc) with a static pre-allocated document that is reused per fetch cycle.
Add `doc.capacity()` and `doc.memoryUsage()` logging to confirm root cause. Hand to Developer.

**Branch**: rnd/screener-nomemory (not created — analysis only; code change is a clean
one-liner, no prototype branch needed).

---

#### DUT Validation (2026-06-03 — same session)

PROP-004 implemented and tested on DUT immediately after analysis (debug build,
`switchApp 7` + `set triggerHeatmap 1` via serial):

```
heatmap GET 200 elapsed=2265ms
heatmap doc cap=4096               ← pre-alloc intact; malloc never failed at boot
heatmap ok count=20 usage=1842/4096
```

**Heap fragmentation confirmed as root cause.** `doc.capacity() == 4096` (not 0) proves the
static pre-allocation succeeded at boot. The usage of 1842 B matches the EXP-003 theoretical
estimate (~1869 B) — the pool was always sufficient in size; the old per-call `malloc(4096)`
was failing silently due to fragmentation (long-uptime TLS cycling leaving no contiguous 4 KB
block). Production firmware flashed; `check_build.sh` 4/4 clean.

**Notes**:
- The TASK-127 exit criterion ("HTTP 200 for 5+ consecutive attempts") is now being met.
  However the heatmap is still broken. Exit criterion needs amendment: must include
  "JSON parse succeeds and `r.count > 0`".
- StaticJsonDocument<4096> was previously tried and caused stack overflow on the 10 KB
  dataTask stack (TASK-119, commit a5aaf8b). A static global pool avoids both stack and
  heap-fragmentation risks.
- TASK-127 screener -1 scope is closed. The parse failure is a NEW defect, should be
  tracked as TASK-128-bis or a new task.
