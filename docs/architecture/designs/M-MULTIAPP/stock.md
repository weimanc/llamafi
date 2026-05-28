# M-MULTIAPP — Stock App Design

> Owner: Architect
> Status: draft — display mode UX open; not yet scheduled for implementation
> Date: 2026-05-25
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [app-interface.md](app-interface.md), [crypto.md](crypto.md), [settings.md](settings.md)

No source reference — new app, not ported from 5in1.

---

## Concept

A glanceable stock market display. Three display modes are under consideration;
the mode active at any time is a user preference stored in Settings
(see [settings.md §app tab](settings.md)):

| Mode | Description | Data source |
|------|-------------|-------------|
| **List** | 6-row ticker table: symbol, price, 24 h change%. Same geometry as crypto.md. | Yahoo Finance v7 (quote, bulk) |
| **Chart** | Per-ticker line graph. Range selectable: 1d / 5d / 1mo / ytd. | Yahoo Finance v8 (chart, per-symbol) |
| **Heatmap** | N-cell colour grid. Cell colour = green/red by change%, intensity = magnitude. | Yahoo Finance v7 (quote, bulk) |

**UX for mode switching** (display mode and ticker selection) is open — see
§Open questions and [settings.md §Open questions](settings.md).

---

## Data service

**Yahoo Finance** — unofficial REST API, no API key required. Same zero-key
pattern as CoinGecko in crypto.md.

### Quote endpoint (List and Heatmap modes)

```
GET https://query1.finance.yahoo.com/v7/finance/quote
    ?symbols=AAPL,MSFT,NVDA,AMZN,META,GOOG
```

Per-symbol response fields used:

| Field | Meaning |
|-------|---------|
| `regularMarketPrice` | Current price (float) |
| `regularMarketChange` | Absolute change from previous close (float) |
| `regularMarketChangePercent` | % change from previous close (float) |

One request, all 6 symbols. JSON payload: ~4–6 KB depending on symbol count
and response verbosity. Use `DynamicJsonDocument doc(6144)` (ArduinoJson v6).

### Chart endpoint (Chart mode)

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}
    ?interval={interval}&range={range}
```

Range → interval mapping:

| Range param | Interval param | Approx. points |
|-------------|---------------|----------------|
| `1d` | `5m` | ~78 (market hours only) |
| `5d` | `60m` | ~33 |
| `1mo` | `1d` | ~22 |
| `ytd` | `1d` | ~100 (grows through year) |

Response fields used:

- `chart.result[0].timestamp[]` — Unix timestamp array
- `chart.result[0].indicators.quote[0].close[]` — close price array (parallel)

One request per symbol per range switch. JSON payload: largest case (ytd/1d,
~100 points) fits in `DynamicJsonDocument doc(8192)`. Use `http.getString()`
not `getStream()` — chunked HTTPS on Arduino-ESP32 2.0.17 fails `deserializeJson`
on raw stream (same constraint as crypto.md).

---

## TLS

Yahoo Finance uses ISRG Root X1 (Let's Encrypt) or DigiCert roots — **different
chain from CoinGecko** (GTS Root R4, ADR-029). Pin the correct root CA in
`dataTaskCerts.h`:

```cpp
// Yahoo Finance root CA — verify with:
//   openssl s_client -connect query1.finance.yahoo.com:443 2>/dev/null | openssl x509 -noout -issuer
static const char YAHOO_FINANCE_ROOT_CA[] PROGMEM = R"(
-----BEGIN CERTIFICATE-----
... (to be confirmed at implementation time) ...
-----END CERTIFICATE-----
)";
```

Same `WiFiClientSecure` + `http.begin(tls, url)` pattern as crypto.md and weather.md
(ADR-029 compliance).

---

## Sub-canvas

Same geometry as crypto.md: **275×124 px** (y:116..239). Winamp chrome stays
visible above. All three modes render within this boundary.

---

## List mode layout

Direct analog of crypto.md. 6 rows × 17 px = 102 px. Header 14 px + rule 1 px
+ 102 px + 7 px margin = 124 px ✓.

```
x=0                        x=274
┌─────────────────────────┐  y=116
│ STOCK TERMINAL  (font 2)│  y=118
├─────────────────────────┤  y=130  (rule)
│ AAPL  188.45   +1.2%   │  y=132
├─────────────────────────┤  y=149
│ MSFT  415.10   -0.3%   │  y=149
...
│ GOOG  175.80   +2.1%   │  y=217
└─────────────────────────┘  y=239
```

Column positions (identical to crypto.md):

| Column | x | Datum |
|--------|---|-------|
| Symbol | 5 | TL_DATUM |
| Price | 55 | TL_DATUM |
| Change% | 270 | right-align |

Price formatting:

```cpp
String formatStockPrice(float price) {
    if (price >= 1000) return String((int)price);
    if (price >= 10)   return String(price, 2);
    return String(price, 4);   // sub-$10 stocks (e.g. some ETFs)
}
```

---

## Heatmap mode layout

N equal cells, coloured by `regularMarketChangePercent`. Canvas 275×124 px.

6 cells in a 3×2 grid:

```
x=0       x=92      x=183     x=274
┌─────────┬─────────┬─────────┐  y=116
│  AAPL   │  MSFT   │  NVDA   │
│ +1.2%   │ -0.3%   │ +4.1%   │  h=62
└─────────┴─────────┴─────────┘  y=178
┌─────────┬─────────┬─────────┐  y=178
│  AMZN   │  META   │  GOOG   │
│ +0.7%   │ -1.5%   │ +2.1%   │  h=61
└─────────┴─────────┴─────────┘  y=239
```

Cell geometry: width = 275/3 ≈ 91 px (distribute remainder). Height = 62 / 62
(top/bottom rows sum to 124 ✓).

Cell fill colour:

```cpp
uint16_t heatmapColor(float changePct) {
    // Positive: green intensity scales with magnitude, cap at +5%
    // Negative: red intensity scales with magnitude, cap at -5%
    float clamped = constrain(changePct, -5.0f, 5.0f);
    if (clamped >= 0) {
        uint8_t g = (uint8_t)(clamped / 5.0f * 31) << 1;   // 6-bit green field
        return (g << 5);   // RGB565: pure green channel
    } else {
        uint8_t r = (uint8_t)(-clamped / 5.0f * 31);
        return (r << 11);  // RGB565: pure red channel
    }
}
```

Symbol + change% text centred in each cell, white on coloured background.

---

## Chart mode layout

Full sub-canvas used for graph: 275×124 px (y:116..239).

```
x=0                                    x=274
┌──────────────────────────────────────┐  y=116
│ AAPL  188.45  [1D][5D][1M][YTD]      │  header h=16
├──────────────────────────────────────┤  y=132
│                                      │
│         sparkline / line graph       │  plot area h=92
│                                      │
├──────────────────────────────────────┤  y=224
│ lo: 182.10          hi: 191.30       │  footer h=15
└──────────────────────────────────────┘  y=239
```

Header: current price + range selector tabs (4 equal cells, 68 px each ≈ 275/4).
Plot area: close prices mapped to y-range (lo..hi). X-axis = time, evenly spaced.
Footer: min / max of fetched range.

Range selector tab hit-test: `rangeIdx = (p.x / 68)` clamped to 0..3 when
`p.y` is in header row (y:116..131).

---

## Fetch strategy

- **List / Heatmap modes:** one bulk quote fetch every 60 s (same interval as
  Crypto). `dataTask` enqueue pattern from crypto.md.
- **Chart mode:** fetch triggered on:
  1. First entry to chart mode (or ticker/range change).
  2. Range selection change via touch.
  3. Periodic refresh: 60 s for 1d (market data changes); 300 s for 5d/1mo/ytd.
  One symbol, one range per request. No background prefetch of other ranges.

---

## App ABC integration

```cpp
class StockApp : public App {
public:
    void init() override;      // load config from Settings, initial fetch
    void resume() override;    // repaint from cached state
    void suspend() override;
    void tick() override;      // staleness check + poll dataTask result
    bool handleInput(TouchPhase, int x, int y) override;

private:
    StockAppState _s;

    void repaintList();
    void repaintHeatmap();
    void repaintChart();
    void stockTick();
    void fetchQuotes();
    void fetchChart(uint8_t tickerIdx, uint8_t rangeIdx);
};
```

Mode dispatch in `repaint()` and `tick()`:

```cpp
void StockApp::tick() {
    switch (_s.mode) {
        case StockMode::List:    // fall through — same data source
        case StockMode::Heatmap: stockTickQuotes(); break;
        case StockMode::Chart:   stockTickChart();  break;
    }
}
```

---

## State

```cpp
enum class StockMode : uint8_t { List = 0, Heatmap = 1, Chart = 2 };
enum class StockRange : uint8_t { D1 = 0, D5 = 1, Mo1 = 2, Ytd = 3 };

struct StockAppState {
    // Config (loaded from Settings / SPIFFS)
    char     tickers[6][8];          // e.g. "AAPL\0"
    StockMode mode;

    // Quote data (List / Heatmap)
    float    prices[6];
    float    changePct[6];
    unsigned long lastQuoteFetch;    // 0 = never fetched

    // Chart data
    uint8_t  chartTickerIdx;         // which of the 6 tickers is shown
    StockRange chartRange;
    float    chartPoints[110];       // max ytd points; actual count in chartLen
    uint8_t  chartLen;
    float    chartLo, chartHi;
    unsigned long lastChartFetch;    // 0 = never fetched
};
```

Total size: ~6×8 + 3 + 6×4 + 6×4 + 4 + 1 + 1 + 110×4 + 1 + 4 + 4 + 4 ≈ **530 B**.

---

## Touch input

| Zone | Action |
|------|--------|
| Chart header range tabs (y:116..131, x / 68) | Select 1d / 5d / 1mo / ytd |
| Chart body tap | Cycle to next ticker (chartTickerIdx + 1 mod 6) |
| List / Heatmap tap | (open — cycle display mode? no-op?) |

Touch handling is partial pending UX decision.

---

## Settings integration

`StockApp::init()` reads from SPIFFS (or Settings state struct once defined):

```cpp
void StockApp::init() {
    // Load tickers and mode from settings.json
    loadStockConfig(_s);

    // Default if not yet configured
    if (_s.tickers[0][0] == '\0') {
        const char* defaults[] = {"AAPL","MSFT","NVDA","AMZN","META","GOOG"};
        for (int i = 0; i < 6; i++) strlcpy(_s.tickers[i], defaults[i], 8);
        _s.mode = StockMode::List;
    }

    // Initial fetch
    fetchQuotes();
    repaintList();   // or repaintHeatmap() / repaintChart() per mode
}
```

---

## Constants

```cpp
#define STOCK_TICKER_COUNT      6
#define STOCK_QUOTE_FETCH_MS    60000UL     // 60 s quote refresh
#define STOCK_CHART_FETCH_D1    60000UL     // 60 s for 1d range
#define STOCK_CHART_FETCH_SLOW  300000UL    // 5 min for 5d/1mo/ytd
#define STOCK_CHART_MAX_POINTS  110         // ytd at 1d interval

// Yahoo Finance endpoints
#define STOCK_QUOTE_URL_BASE    "https://query1.finance.yahoo.com/v7/finance/quote?symbols="
#define STOCK_CHART_URL_BASE    "https://query1.finance.yahoo.com/v8/finance/chart/"

// Sub-canvas geometry (same as crypto.md)
#define ST_CANVAS_Y             116
#define ST_CANVAS_H             124
#define ST_HEADER_Y             118
#define ST_RULE_Y               130
#define ST_ROW_START_Y          132
#define ST_ROW_H                17
#define ST_COL_SYMBOL           5
#define ST_COL_PRICE            55
#define ST_COL_CHANGE           270
#define ST_RULE_W               270

// Chart mode geometry
#define ST_CHART_HEADER_H       16          // y:116..131
#define ST_CHART_PLOT_Y         132         // plot area top
#define ST_CHART_PLOT_H         92          // y:132..223
#define ST_CHART_FOOTER_Y       224         // footer top
#define ST_CHART_FOOTER_H       15          // y:224..239
#define ST_CHART_RANGE_W        68          // 275/4 — range tab width
```

---

## Open questions

1. **UX for ticker selection** — predefined list (recommended for resistive
   touch), QWERTY keyboard widget, or hybrid. Deferred to UX pass.
   See [settings.md §Open questions](settings.md).

2. **Display mode switching** — how does user change list/chart/heatmap?
   Options: tap a mode-selector row in Settings `app` tab only; or in-app
   gesture (long-press canvas cycles mode). Open.

3. **Chart ticker selection** — in chart mode, which ticker is shown?
   Tap-to-cycle (any canvas tap cycles through 6 tickers) is described above
   but not confirmed.

4. **Heatmap cell count** — 6 cells (3×2) matches ticker count. If ticker
   count grows, layout must adapt. Keep at 6 for now.

5. **Yahoo Finance reliability** — unofficial API, no SLA. If endpoint changes
   or rate-limits, app shows cached data with staleness indicator. Monitor
   `http.GET()` return code; log non-200.

6. **TLS root CA** — Yahoo Finance cert chain must be confirmed at
   implementation time with `openssl s_client`. Do not assume ISRG Root X1
   without verification.

7. **Market hours** — outside US market hours, `regularMarketPrice` is still
   the last traded price. No special handling needed for the display, but a
   "CLOSED" indicator in the header could be useful. Open.

---

## Exit criteria

### List mode
- **L1** — All 6 rows render within sub-canvas (x:0..274, y:116..239).
- **L2** — `"---"` shown before first fetch. Prices appear after first
  successful quote response.
- **L3** — Positive change% green (0x07E0); negative red (0xF800).
- **L4** — App switch: Spotify → Stock → Spotify. Winamp chrome pixel-correct;
  no stock row residue above y=116.
- **L5** — Cached prices shown immediately on resume; re-fetch triggered
  if >60 s stale.

### Heatmap mode
- **H1** — 6 cells tile 275×124 sub-canvas exactly. No overflow.
- **H2** — Cell colour scales correctly: +5% or greater = full green;
  -5% or less = full red; 0% = near-black.
- **H3** — Symbol + change% text legible (white on coloured cell).

### Chart mode
- **C1** — Line plot uses all available close-price points, scaled to
  plot area height (y:132..223).
- **C2** — Range tab highlight updates on tap. New chart data fetched
  for selected range.
- **C3** — `"---"` header price and flat line shown before first fetch.
- **C4** — `chartLo` / `chartHi` displayed correctly in footer.

### Settings integration
- **S1** — Ticker list and mode loaded from SPIFFS on `init()`. Defaults
  applied if no config present.
- **S2** — Changing tickers in Settings and switching to Stock app reflects
  new symbols without reboot.
