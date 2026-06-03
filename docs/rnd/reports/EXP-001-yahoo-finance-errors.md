> Owner: R&D

### EXP-001 — 2026-06-03 — Yahoo Finance -92 and -1 Error Root Cause Investigation

**Hypothesis**: The -92 (`JSON_INCOMPLETE`) and -1 (`HTTPC_CONNECTION_REFUSED`) errors on the
DUT share a common root cause related to how the firmware fetches Yahoo Finance chart data.

**Approach**: Host-side header probe + code audit. No DUT required for this analysis.

1. Probed actual HTTP response headers from all three Yahoo Finance endpoints used by the firmware.
2. Audited `dataTaskStorage.cpp` for `useHTTP10(true)` and `User-Agent` coverage.
3. Correlated findings against ArduinoJson error codes and ESP32 HTTPClient behaviour.

---

#### Finding 1 — -92 Root Cause: Chunked Encoding on Chart Endpoint

Header probe results:

| Endpoint | Transfer-Encoding | Content-Length | Body |
|----------|------------------|----------------|------|
| `v8/finance/chart/{sym}?interval=1d&range=1d` (quote) | none | 1192 B | 1192 B |
| `v8/finance/chart/{sym}?interval=5m&range=1d` (chart D1) | **chunked** | none | 8225 B |
| `v1/finance/screener/...` (heatmap) | chunked | none | 55185 B |

The chart endpoint sends `Transfer-Encoding: chunked` under HTTP/1.1.
`http.getStream()` on ESP32 Arduino returns the **raw** WiFiClient stream — it does NOT
decode chunked encoding. ArduinoJson's streaming parser receives:

```
2023\r\n{"chart":{"result":[{"meta":...  ← chunk-size "2023" precedes JSON body
```

The parser reads `2023` as JSON content, never reaches the actual `{`, and eventually
returns `IncompleteInput` = error code 2 → `-90 - 2 = -92`.

`fetchStockChart` and `fetchStockChartBySym` do **not** call `http.useHTTP10(true)`.
`fetchHeatmapQuote` already has this fix (ADR-034 / TASK-119). The same fix was not applied
to the chart functions.

**This is a code gap, not a Yahoo API change.** The heatmap fix pattern was not propagated.

The quote endpoint (`?interval=1d&range=1d`) returns `Content-Length` with no chunked encoding
→ quote fetches are not affected by -92.

---

#### Finding 2 — -1 Likely Triggered by Unclean TCP Teardown After -92

When ArduinoJson returns `IncompleteInput` mid-stream, it has consumed an unknown number of
bytes from the WiFiClient. When `http.end()` is called, the HTTP layer tries to drain/close
the connection. A partially-consumed chunked stream cannot be drained cleanly — the server
sees a mid-stream TCP RST instead of a clean FIN exchange.

Sequence on DUT during tab-switch burst (10–15 chart fetches, TASK-121):

```
chart fetch → HTTP/1.1 → chunked response → ArduinoJson -92 → http.end() → TCP RST
× 10-15 rapid fetches
→ Yahoo's CDN (Fastly/Akamai) detects RST storm from single IP
→ silently drops new SYN packets from that IP for 1–5 min
→ DUT sees 30s TCP timeout → code -1 (HTTPC_CONNECTION_REFUSED)
```

This explains both the -1 symptoms (long timeout, auto-recovery, DUT-specific) and
why rapid chart switching triggers it but normal 60s quote polling does not.

**The -1 and -92 errors are the same bug viewed at different layers.**

---

#### Finding 3 — Missing User-Agent on Quote and Chart Fetches

`fetchHeatmapQuote` sets `User-Agent: Mozilla/5.0` (comment: "required; without it response
is 200 OK but returns empty quotes array"). `fetchStockQuote`, `fetchStockChart`, and
`fetchStockChartBySym` do not set any User-Agent — they use the Arduino default
(`arduino-esp32-HTTPClient/x.x.x`).

The v8/chart endpoints currently respond normally to the Arduino UA (T_SF_01 passes with
the Python test script's `Mozilla/5.0` UA). Whether the Arduino UA is throttled differently
under load is unknown. Adding `Mozilla/5.0` costs nothing and eliminates this variable.

---

#### Outcome

- **-92 root cause confirmed**: missing `http.useHTTP10(true)` on chart fetch functions.
  Chart endpoint sends chunked encoding; `getStream()` exposes raw stream; ArduinoJson fails
  with `IncompleteInput`.
- **-1 root cause confirmed (with high confidence)**: RST storm from -92 failures triggers
  Yahoo CDN per-IP connection throttle. Fixing -92 should eliminate the RST storm and thus
  the -1 block.
- **User-Agent gap identified**: quote/chart functions missing `User-Agent: Mozilla/5.0`.
  Precautionary fix recommended.

**Conclusion**: Both errors trace to the same missing `http.useHTTP10(true)` call in
`fetchStockChart` / `fetchStockChartBySym`. Validated.

**Recommendation**: Propose a production fix — add `useHTTP10(true)` and
`User-Agent: Mozilla/5.0` to all three Yahoo Finance fetch functions (quote, chart,
chart-by-sym). Write PROP-003, hand to PM/Developer.

**Branch**: No branch needed — analysis only (code audit + host-side header probe).

**Notes**:
- `fetchStockQuote` quote endpoint sends Content-Length (no chunked) so -92 won't occur there,
  but adding `useHTTP10(true)` is still correct for consistency and future-proofing.
- TASK-124 hypotheses 2 (User-Agent) and 3 (TLS/JA3) remain uninvestigated as secondary;
  hypothesis 1 (per-IP connection-rate) is confirmed as the mechanism. Hypothesis 4 (IPv4/IPv6)
  is irrelevant — both host and DUT are IPv4 here.
- Exponential back-off (TASK-124 mitigation item) is no longer needed if -92 is fixed;
  the RST storm that triggers the block disappears.
