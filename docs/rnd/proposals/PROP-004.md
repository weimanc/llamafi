> Owner: R&D

### PROP-004 — 2026-06-03 — Pre-allocate heatmap JSON pool to fix NoMemory / IncompleteInput

**Origin**: EXP-003

**Summary**: Replace the per-call `DynamicJsonDocument doc(4096)` in `fetchHeatmapQuote()`
with a static pre-allocated document that is cleared and reused on each fetch cycle.
This eliminates the `malloc` failure risk from heap fragmentation after long uptime.

**Prototype evidence**: EXP-003 live DUT observation + ArduinoJson 6.21.6 memory-model
source analysis:
- Theoretical memory requirement for filtered heatmap document: ~1869 B
  (104 VariantSlots × 16 B + ~205 B deduplicated strings on ESP32/32-bit).
- 1869 B << 4096 B pool capacity → pool size is not the root cause.
- `NoMemory` with 123 KB total free heap is consistent with `malloc(4096)` failing due to
  heap fragmentation after 60+ min TLS session cycling (each session temporarily allocates
  ~32 KB; FreeRTOS heap_4 free-list can have no contiguous 4096-byte block even with ample
  total free space).
- `ESP.getMaxAllocHeap()` is not currently logged; fragmentation cannot be directly confirmed
  from logs, but the pattern is textbook long-uptime TLS fragmentation.

**Suggested scope**:

1. **Replace per-call `DynamicJsonDocument` with static pre-allocated document.**

   `dataTaskStorage.cpp` — at file scope (near other static storage, before
   `fetchHeatmapQuote`):
   ```cpp
   static DynamicJsonDocument s_heatmapDoc(4096);
   ```

   Inside `fetchHeatmapQuote()` — replace:
   ```cpp
   DynamicJsonDocument doc(4096);
   ```
   with:
   ```cpp
   s_heatmapDoc.clear();
   DynamicJsonDocument& doc = s_heatmapDoc;
   ```

   Thread safety: only the dataTask calls `fetchHeatmapQuote()` → safe.
   Allocated once at firmware startup when heap is unfragmented.

2. **Add diagnostic logging** (keep permanently; < 1 ms, ~30 B log overhead):

   After `s_heatmapDoc.clear()`:
   ```cpp
   LOG_D("dataTask.stock", "heatmap doc cap=%u", doc.capacity());
   ```
   After successful parse (success branch, after `r.count` loop):
   ```cpp
   LOG_D("dataTask.stock", "heatmap ok count=%u usage=%u/%u",
         r.count, doc.memoryUsage(), doc.capacity());
   ```
   If `capacity()` ever logs 0, it means the initial startup malloc failed (very low free
   heap at boot) — would require investigation. Expected: `cap=4096` always.
   `memoryUsage()` will confirm whether the 1869 B estimate was accurate.

3. **Add `ESP.getMaxAllocHeap()` to heartbeat** (`logHeartbeat.h`).
   Surfaces fragmentation state every 30 s. Append to existing `[I][hb]` line:
   ```
   heap=123k maxAlloc=87k
   ```
   Permanently useful, not just for this bug.

4. **Amend TASK-127 exit criterion** in `tasks.md`:
   Add: "JSON parse succeeds; `heatmap ok count=N` logged for 5+ consecutive
   cycles spaced 120 s apart."

**What this does NOT include**:
- Changing pool size (not needed — 1869 B << 4096 B).
- Adding error retry logic.
- Addressing `IncompleteInput` separately (likely resolves once malloc succeeds; if it
  persists after this fix, raise a new task).

**Risks / unknowns**:
- If pool IS genuinely too small (pool-overflow secondary hypothesis), NoMemory will still
  appear after this fix. The `memoryUsage()` log will reveal this immediately; bump to 6144 B.
- Permanent 4096 B heap reservation: DUT has ~123 KB free → acceptable.
- `doc.clear()` resets pool pointers without zeroing memory → clean state for next parse.

**Recommended next step**: Hand to Developer for implementation. One build, one DUT flash,
verify `heatmap ok count=N` in serial log and tiles populate in HeatmapDetail view.
