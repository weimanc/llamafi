# M-MULTIAPP — Stock App Design

> Owner: Architect
> Status: POC scoped — List + Chart detail views; implementation ready
> Date: 2026-05-29
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [app-interface.md](app-interface.md), [crypto.md](crypto.md), [settings.md](settings.md)
> View designs: [stock-list.md](stock-list.md) · [stock-chart.md](stock-chart.md)

No source reference — new app, not ported from 5in1.

---

## Concept

Glanceable stock market display. **POC scope: List view + Chart detail (drill-down).**

| View | Description | Data source |
|------|-------------|-------------|
| **List** | 6-row ticker table: symbol, price, 24 h change%. Tap row → Chart detail. | Yahoo Finance v7 (quote, bulk) |
| **Chart detail** | Per-ticker line graph, accessed by tapping a List row. Range: 1D/5D/1M/YTD. Back button returns to List. | Yahoo Finance v8 (chart, per-symbol) |

**Deferred:** Heatmap view, Settings integration, market hours indicator, ticker selection UX.

**Tickers (POC hardcoded):** `AAPL MSFT NVDA AMZN META GOOG`

---

## Data service

**Yahoo Finance** — unofficial REST API, no API key required. Same zero-key
pattern as CoinGecko in crypto.md.

### Quote endpoint (List view)

> **Note (2026-05-29):** `v7/finance/quote` returns 401 Unauthorized — endpoint is gated.
> Quote data is sourced from the chart endpoint instead (same v8 base URL, 6 separate requests).

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}
    ?interval=1d&range=1d
```

One request per symbol, 6 total. JSON payload: ~1.2 KB each (well within budget).
Response fields used from `chart.result[0].meta`:

| Field | Meaning |
|-------|---------|
| `regularMarketPrice` | Current price (float) |
| `chartPreviousClose` | Previous session close (float) |

Change % derived on firmware: `changePct = (price - prevClose) / prevClose * 100`.

Use `DynamicJsonDocument doc(8192)` (ArduinoJson v6) — same document as chart detail fetches.

### Chart endpoint (Chart detail view)

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}
    ?interval={interval}&range={range}
```

Range → interval mapping:

| Range param | Interval param | Approx. points | Payload |
|-------------|---------------|----------------|---------|
| `1d` | `5m` | ~78 (market hours only) | ~8.1 KB |
| `5d` | `60m` | ~33 | ~4.7 KB |
| `1mo` | `1d` | ~22 | ~3.3 KB |
| `ytd` | `1wk` | ~22 | ~3.7 KB |

> **Note:** YTD uses `interval=1wk` (not `1d`). `ytd/1d` produces ~101 points (~12 KB),
> which exceeds the 8192 B `DynamicJsonDocument` budget. Verified by TASK-109i probe.

Response fields used:

- `chart.result[0].timestamp[]` — Unix timestamp array
- `chart.result[0].indicators.quote[0].close[]` — close price array (parallel)
- Null entries in `close[]` are normal outside market hours; firmware must skip them.

One request per symbol per range switch. All ranges fit within
`DynamicJsonDocument doc(8192)`. Use `http.getString()` not `getStream()` — chunked
HTTPS on Arduino-ESP32 2.0.17 fails `deserializeJson` on raw stream (same constraint as crypto.md).

---

## TLS

Yahoo Finance uses ISRG Root X1 (Let's Encrypt) or DigiCert roots — **different
chain from CoinGecko** (GTS Root R4, ADR-029). Confirm chain at implementation time:

```sh
openssl s_client -connect query1.finance.yahoo.com:443 2>/dev/null | openssl x509 -noout -issuer
```

Pin the correct root CA in `dataTaskCerts.h`:

```cpp
static const char YAHOO_FINANCE_ROOT_CA[] PROGMEM = R"(
-----BEGIN CERTIFICATE-----
... (confirm at implementation time) ...
-----END CERTIFICATE-----
)";
```

Same `WiFiClientSecure` + `http.begin(tls, url)` pattern as crypto.md and weather.md
(ADR-029 compliance).

---

## Canvas

Full screen: **275×240 px** (y:0..239). Same as CryptoApp actual implementation.
Note: crypto.md contains an erroneous "sub-canvas y:116..239" spec that was never
implemented — CryptoApp uses full screen (CX_CANVAS_Y=0, CX_CANVAS_H=240). Do not
reference that section of crypto.md.

---

## State

```cpp
enum class StockSubView : uint8_t { List = 0, ChartDetail = 1 };
enum class StockRange   : uint8_t { D1 = 0, D5 = 1, Mo1 = 2, Ytd = 3 };

struct StockAppState {
    // Config (hardcoded for POC; Settings integration deferred)
    char     tickers[6][8];          // "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG"

    // Navigation
    StockSubView subView;            // List or ChartDetail

    // Quote data (List view)
    float    prices[6];
    float    changePct[6];
    unsigned long lastQuoteFetch;    // millis(); 0 = never fetched

    // Chart data (ChartDetail view)
    uint8_t  chartTickerIdx;         // index into tickers[]
    StockRange chartRange;
    float    chartPoints[110];       // close prices; actual count in chartLen
    uint8_t  chartLen;
    float    chartLo, chartHi;
    unsigned long lastChartFetch;    // millis(); 0 = never fetched

    // Fetch error state (shown as full-canvas message — see stock-list.md §Error render)
    bool     fetchFailed;            // true = last fetch attempt got non-200 / TLS error
    int      fetchErrorCode;         // raw HTTPClient return code (negative = conn/TLS)
};
```

Total size: ~565 B.

Error state rules:
- Set `fetchFailed = true` + `fetchErrorCode = <code>` on any non-200 or HTTPClient error.
- Clear both on a fully successful fetch.
- Both views check `fetchFailed` at the top of their repaint and short-circuit to `repaintError()` if true.

---

## Fetch strategy

- **List view:** 6 per-symbol chart fetches (`interval=1d&range=1d`) every 60 s, enqueued sequentially via `dataTask`. Each ~1.2 KB. Price and previous-close extracted from `chart.result[0].meta`; change% computed on device.
- **Chart detail:** fetch triggered on:
  1. First drill-in for a ticker (or range change).
  2. Range tab tap.
  3. Periodic refresh: 60 s for 1D; 300 s for 5D/1M/YTD.
  One symbol, one range per request. No background prefetch of other ranges.

---

## App ABC integration

```cpp
class StockApp : public App {
public:
    void init() override;       // populate hardcoded tickers, initial quote fetch
    void resume() override;     // repaint from cached state
    void suspend() override;
    void tick() override;       // staleness check + poll dataTask result
    bool handleInput(TouchPhase, int x, int y) override;

private:
    StockAppState _s;

    void repaintList();
    void repaintChart();
    void repaintError();             // full-canvas error; called by repaintList/repaintChart when fetchFailed
    void fetchQuotes();
    void fetchChart(uint8_t tickerIdx, uint8_t rangeIdx);
    void drillToChart(uint8_t tickerIdx);
    void backToList();
};
```

Sub-view dispatch:

```cpp
void StockApp::tick() {
    switch (_s.subView) {
        case StockSubView::List:        stockTickQuotes(); break;
        case StockSubView::ChartDetail: stockTickChart();  break;
    }
}
```

---

## Constants

```cpp
#define STOCK_TICKER_COUNT      6
#define STOCK_QUOTE_FETCH_MS    60000UL     // 60 s quote refresh
#define STOCK_CHART_FETCH_D1    60000UL     // 60 s for 1D range
#define STOCK_CHART_FETCH_SLOW  300000UL    // 5 min for 5D/1M/YTD
#define STOCK_CHART_MAX_POINTS  110         // ytd at 1d interval

// Yahoo Finance endpoints
// v7/quote is gated (401) — all fetches use v8/chart
#define STOCK_CHART_URL_BASE    "https://query1.finance.yahoo.com/v8/finance/chart/"
// Quote fetch: STOCK_CHART_URL_BASE + symbol + "?interval=1d&range=1d"
// Chart fetch: STOCK_CHART_URL_BASE + symbol + "?interval=" + I + "&range=" + R

// Full-screen canvas geometry
#define ST_CANVAS_Y             0
#define ST_CANVAS_H             240
#define ST_CANVAS_X2            274         // inclusive right edge

// List view geometry — see stock-list.md
#define ST_LIST_HEADER_Y        5
#define ST_LIST_RULE_Y          22
#define ST_LIST_ROW_START_Y     25
#define ST_LIST_ROW_H           36
#define ST_LIST_COL_SYMBOL      5
#define ST_LIST_COL_PRICE       55
#define ST_LIST_COL_CHANGE      270

// Chart detail geometry — see stock-chart.md
#define ST_CHART_HEADER_Y       0
#define ST_CHART_HEADER_H       18
#define ST_CHART_BACK_W         30          // back button touch zone width
#define ST_CHART_TICKER_X       30          // ticker + price text start
#define ST_CHART_TABS_X         130         // range tab area start x
#define ST_CHART_TAB_W          36          // (275 - 130) / 4
#define ST_CHART_PLOT_Y         18
#define ST_CHART_PLOT_H         196         // y:18..213
#define ST_CHART_FOOTER_Y       214
#define ST_CHART_FOOTER_H       25          // y:214..239
```

---

## Open questions

1. **Yahoo Finance reliability** — unofficial API, no SLA. Log non-200 responses;
   show cached data with staleness on fetch failure. Risk accepted for POC.

2. **TLS root CA** — must confirm Yahoo Finance cert chain with `openssl s_client`
   at implementation time. Do not assume ISRG Root X1 without verification.

**Resolved (POC):**
- Ticker selection → hardcoded defaults `AAPL MSFT NVDA AMZN META GOOG`.
- Display mode switching → drill-down from List row tap; heatmap deferred.
- Chart ticker selection → set by tapping a List row (`drillToChart(rowIdx)`).
- Back navigation → `[<]` button in chart header (x:0..29, y:0..17).
- Heatmap → deferred; no implementation target set.
- Market hours indicator → deferred.
- Settings integration → deferred.
