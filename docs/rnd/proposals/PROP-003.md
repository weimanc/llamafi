> Owner: R&D

### PROP-003 — 2026-06-03 — Fix Yahoo Finance HTTP/1.0 + User-Agent on Quote/Chart Fetches

**Origin**: EXP-001

**Summary**: Apply the same `useHTTP10(true)` + `User-Agent: Mozilla/5.0` pattern already
used in `fetchHeatmapQuote` to `fetchStockQuote`, `fetchStockChart`, and
`fetchStockChartBySym`. This eliminates -92 (`JSON_INCOMPLETE`) and the -1
(`HTTPC_CONNECTION_REFUSED`) cascades they trigger.

**Prototype evidence**: EXP-001 header probe confirmed:
- `v8/finance/chart` returns `Transfer-Encoding: chunked` under HTTP/1.1.
- `http.getStream()` exposes raw chunked bytes → ArduinoJson returns `IncompleteInput` (-92).
- -92 mid-stream failures cause TCP RST on `http.end()` → Yahoo CDN per-IP throttle → -1.
- `fetchHeatmapQuote` already has the correct fix; it was not propagated to quote/chart.

**Suggested scope**:

Three-line change per function (quote, chart, chart-by-sym) — before `http.GET()`:

```cpp
http.addHeader("User-Agent", "Mozilla/5.0");
http.useHTTP10(true);
```

Apply to:
- `fetchStockQuote` (lines ~158–165 `dataTaskStorage.cpp`)
- `fetchStockChart` (lines ~214–223)
- `fetchStockChartBySym` (lines ~357–364)

No structural changes. No new state. No impact to other fetch functions.

**What it does NOT include**:
- Exponential back-off (no longer needed once -92 is fixed)
- HTTP/1.1 connection reuse (future optimisation, separate proposal)
- Staggered ticker fetches (nice-to-have, separate proposal)

**Risks / unknowns**:
- HTTP/1.0 forces a new TCP+TLS handshake per request (same as current behaviour — there is
  no session reuse today). No regression expected.
- `useHTTP10` disables HTTP/1.1 features (keep-alive, pipelining) — not used today anyway.
- Quote endpoint already uses Content-Length (no chunked), so `useHTTP10` there is defensive
  only. Low risk.

**Recommended next step**: Hand to PM for scheduling as a bug-fix task under TASK-124.
Developer can implement directly from this proposal — no design review needed (pattern already
established in `fetchHeatmapQuote`).

**Branch**: No R&D branch — fix is a direct copy of existing `fetchHeatmapQuote` pattern.
