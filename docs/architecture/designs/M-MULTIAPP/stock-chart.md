# M-MULTIAPP — Stock App: Chart Detail View

> Owner: Architect
> Status: POC scope — ready for implementation
> Date: 2026-05-29
> Part of: [stock.md](stock.md)
> See also: [stock-list.md](stock-list.md)

Accessed by tapping a row in List view. Displays a line graph for the selected
ticker with selectable time range. `[<]` button in header returns to List.

---

## Layout

Full canvas: 275×240 px (y:0..239).

```
x=0  x=30        x=130  x=166  x=202  x=238   x=274
┌─────┬──────────┬──────┬──────┬──────┬───────┐  y=116
│ [<] │AAPL 188.45│  1D │  5D  │  1M  │  YTD  │
└─────┴──────────┴──────┴──────┴──────┴───────┘  y=131
┌────────────────────────────────────────────────┐  y=132
│                                                │
│              line graph (close prices)         │  h=92
│                                                │
└────────────────────────────────────────────────┘  y=223
┌────────────────────────────────────────────────┐  y=224
│ lo: 182.10                      hi: 191.30     │  h=15
└────────────────────────────────────────────────┘  y=239
```

### Header zones (y:116..131, h=16)

| Zone | x range | Content | Action |
|------|---------|---------|--------|
| Back button | 0..29 | `"<"` (font 2, centred) | `backToList()` |
| Ticker + price | 30..129 | `"AAPL 188.45"` (font 2) | — |
| Tab 0 (1D) | 130..165 | `"1D"` | set range D1, fetch |
| Tab 1 (5D) | 166..201 | `"5D"` | set range D5, fetch |
| Tab 2 (1M) | 202..237 | `"1M"` | set range Mo1, fetch |
| Tab 3 (YTD) | 238..273 | `"YTD"` | set range Ytd, fetch (interval=1wk) |

Active range tab: highlight background (e.g. `0x4208` dark grey) behind label.
Inactive tabs: no background.

### Plot area (y:132..223, h=92)

Close prices mapped linearly to y-range. X-axis evenly spaced across `chartLen` points.

```cpp
float xStep = (float)ST_CANVAS_X2 / (chartLen - 1);
float yScale = (float)(ST_CHART_PLOT_H - 2) / (chartHi - chartLo);

for (int i = 1; i < chartLen; i++) {
    int x0 = (int)((i - 1) * xStep);
    int x1 = (int)(i       * xStep);
    int y0 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2
             - (int)((chartPoints[i-1] - chartLo) * yScale);
    int y1 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2
             - (int)((chartPoints[i]   - chartLo) * yScale);
    tft.drawLine(x0, y0, x1, y1, 0x07FF);   // cyan line
}
```

Flat line at vertical midpoint shown before first fetch (`chartLen == 0`).

### Footer (y:224..239, h=15)

```
lo: 182.10                      hi: 191.30
```

Left-aligned `lo:` at x=5; right-aligned `hi:` at x=270.
Show `"---"` if not yet fetched.

---

## Touch input

All hit-tests active only when `subView == StockSubView::ChartDetail`.

```cpp
bool StockApp::handleInput(TouchPhase phase, int x, int y) {
    if (_s.subView != StockSubView::ChartDetail) return false;
    if (phase != TouchPhase::End) return true;

    if (y >= ST_CHART_HEADER_Y && y < ST_CHART_HEADER_Y + ST_CHART_HEADER_H) {
        if (x < ST_CHART_BACK_W) {
            backToList();
        } else if (x >= ST_CHART_TABS_X) {
            uint8_t tab = constrain((x - ST_CHART_TABS_X) / ST_CHART_TAB_W, 0, 3);
            _s.chartRange = (StockRange)tab;
            _s.lastChartFetch = 0;   // force re-fetch
            fetchChart(_s.chartTickerIdx, tab);
        }
    }
    return true;
}
```

Chart body tap is a no-op in POC.

---

## Error render

`repaintChart()` checks `fetchFailed` at entry and delegates to `repaintError()` (defined in
[stock-list.md §Error render](stock-list.md)) if true. The `[<]` back button remains active —
touch handling still routes `x < ST_CHART_BACK_W` → `backToList()` even in error state, so
the user can always return to the list view.

---

## `drillToChart()` / `backToList()`

```cpp
void StockApp::drillToChart(uint8_t tickerIdx) {
    _s.chartTickerIdx = tickerIdx;
    _s.chartRange     = StockRange::D1;   // default to 1D on drill-in
    _s.subView        = StockSubView::ChartDetail;
    if (_s.lastChartFetch == 0 || millis() - _s.lastChartFetch > STOCK_CHART_FETCH_D1)
        fetchChart(tickerIdx, (uint8_t)StockRange::D1);
    repaintChart();
}

void StockApp::backToList() {
    _s.subView = StockSubView::List;
    repaintList();
}
```

---

## Exit criteria

- **C1** — `[<]` tap returns to List view. List header `"STOCK TERMINAL"` visible; chart residue cleared.
- **C2** — Line plot uses all available `chartLen` points, scaled to plot area (y:132..223). No point overflows canvas bounds.
- **C3** — Active range tab highlighted; tapping a different tab fetches new data and redraws.
- **C4** — `"---"` shown in header price and flat mid-line in plot before first fetch.
- **C5** — `chartLo` / `chartHi` displayed correctly in footer after fetch.
- **C6** — Drill-in always defaults to 1D range. Subsequent drill-ins to same ticker use cached data if <60 s stale.
- **C7** — Back → List → drill same row again: chart redraws correctly (no stale sub-view state).
