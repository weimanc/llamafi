# M-MULTIAPP — Stock App: List View

> Owner: Architect
> Status: POC scope — ready for implementation
> Date: 2026-05-29
> Part of: [stock.md](stock.md)
> See also: [stock-chart.md](stock-chart.md)

---

## Layout

Direct analog of crypto.md. 6 rows × 17 px = 102 px.
Header 14 px + rule 1 px + 102 px + 7 px margin = 124 px ✓.

```
x=0                                  x=274
┌────────────────────────────────────┐  y=116
│ STOCK TERMINAL          (font 2)   │  y=118
├────────────────────────────────────┤  y=130  (rule)
│ AAPL   188.45              +1.2%   │  y=132
│ MSFT   415.10              -0.3%   │  y=149
│ NVDA   950.02              +4.1%   │  y=166
│ AMZN   185.30              +0.7%   │  y=183
│ META   490.75              -1.5%   │  y=200
│ GOOG   175.80              +2.1%   │  y=217
└────────────────────────────────────┘  y=239
```

Column positions:

| Column | x | Datum | Notes |
|--------|---|-------|-------|
| Symbol | 5 | TL_DATUM | e.g. `"AAPL"` |
| Price | 55 | TL_DATUM | formatted by `formatStockPrice()` |
| Change% | 270 | TR_DATUM (right-align) | e.g. `"+1.2%"` |

Row baseline: `ST_LIST_ROW_START_Y + rowIdx * ST_LIST_ROW_H + 12` (font 2 ascent ~12 px).

---

## Price formatting

```cpp
String formatStockPrice(float price) {
    if (price >= 1000) return String((int)price);
    if (price >= 10)   return String(price, 2);
    return String(price, 4);   // sub-$10 (e.g. some ETFs)
}
```

Change% text: prefix `"+"` for positive, TFT colour `0x07E0` (green) / `0xF800` (red).
Placeholder `"---"` before first successful fetch.

---

## Touch input

Row hit-test (active only when `subView == StockSubView::List`):

```cpp
if (phase == TouchPhase::End
    && p.y >= ST_LIST_ROW_START_Y && p.y < ST_CANVAS_Y + ST_CANVAS_H) {
    int rowIdx = (p.y - ST_LIST_ROW_START_Y) / ST_LIST_ROW_H;
    rowIdx = constrain(rowIdx, 0, STOCK_TICKER_COUNT - 1);
    drillToChart(rowIdx);
}
```

`drillToChart(rowIdx)` sets `_s.chartTickerIdx = rowIdx`, `_s.subView = ChartDetail`,
triggers an immediate chart fetch (if not cached or stale), then calls `repaintChart()`.

No other tap zones in List view.

---

## Error render (`repaintError`)

When `fetchFailed == true`, both List and Chart detail call `repaintError()` instead of
their normal render. Full sub-canvas replaced:

```
x=0                                  x=274
┌────────────────────────────────────┐  y=116
│                                    │
│       STOCK FETCH FAILED           │  centred, font 2, red (0xF800)
│          NET ERR  -1               │  centred, font 2, red — shows fetchErrorCode
│      retrying in 60s...            │  centred, font 1, grey (0x7BEF)
│                                    │
│                                    │
└────────────────────────────────────┘  y=239
```

```cpp
void StockApp::repaintError() {
    tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xF800, TFT_BLACK);
    tft.setTextFont(2);
    tft.drawString("STOCK FETCH FAILED", 137, ST_CANVAS_Y + 40);
    char buf[24];
    snprintf(buf, sizeof(buf), "NET ERR  %d", _s.fetchErrorCode);
    tft.drawString(buf, 137, ST_CANVAS_Y + 60);
    tft.setTextColor(0x7BEF, TFT_BLACK);
    tft.setTextFont(1);
    tft.drawString("retrying in 60s...", 137, ST_CANVAS_Y + 80);
    tft.setTextDatum(TL_DATUM);   // ADR-027 producer rule: reset datum
}
```

Tap anywhere in the sub-canvas while error is shown: no action (drill-in disabled while `fetchFailed`).
Error clears automatically when the next scheduled fetch succeeds.

---

## Render sequence

1. `fillRect` sub-canvas (`ST_CANVAS_Y`, `ST_CANVAS_H`) with background colour.
2. Draw `"STOCK TERMINAL"` header (font 2, x=5, y=`ST_LIST_HEADER_Y`).
3. Draw horizontal rule at `ST_LIST_RULE_Y`, width `ST_CANVAS_X2 - 5`.
4. For each row `i` in 0..5:
   a. Draw symbol (`tickers[i]`, white).
   b. Draw price (`formatStockPrice(prices[i])`, white) or `"---"` if not fetched.
   c. Draw change% (coloured, right-aligned at x=`ST_LIST_COL_CHANGE`).

---

## Exit criteria

- **L1** — All 6 rows render within sub-canvas (x:0..274, y:116..239). No overflow above y=116 or below y=239.
- **L2** — `"---"` shown for price and change% before first fetch completes.
- **L3** — Positive change% rendered green (0x07E0); negative red (0xF800).
- **L4** — App switch Spotify → Stock → Spotify: Winamp chrome pixel-correct, no stock row residue above y=116.
- **L5** — Cached prices shown immediately on `resume()`; re-fetch enqueued if last fetch >60 s ago.
- **L6** — Tapping any row transitions to Chart detail for the correct ticker (verified by chart header showing tapped ticker symbol).
