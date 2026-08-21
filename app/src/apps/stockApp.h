#pragma once
// apps/stockApp.h — StockApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11. Method bodies live in stockApp.cpp.
// Stage F (TASK-472) further splits this into stock/{stockApp,stockList,
// stockChart,stockHeatmap} — this conversion is the D0 pair, not that split.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "util/tftViewportRepair.h"
#include "logSink.h"   // LOG_D

extern TFT_eSPI tft;

// ── StockApp (stock.md) ───────────────────────────────────────────────
#define STOCK_TICKER_COUNT      8
#define STOCK_QUOTE_FETCH_MS    60000UL
#define STOCK_CHART_FETCH_D1    60000UL
#define STOCK_CHART_FETCH_SLOW  300000UL
#define STOCK_HEATMAP_FETCH_MS  120000UL

// Tile label tier thresholds — see ADR-037
constexpr int16_t HM_T1_H = 36, HM_T1_W = 40;
constexpr int16_t HM_T2_H = 28, HM_T2_W = 40;
constexpr int16_t HM_T3_H = 20, HM_T3_W = 40;
constexpr int16_t HM_T4_H = 18, HM_T4_W = 40;
constexpr int16_t HM_T5_H = 10, HM_T5_W = 20;
constexpr int16_t HM_T6_MIN_W = 8;           // minimum tile width for rotated text
constexpr int16_t HM_T6_SEP   = 2;           // gap (px) between sym and pct in rotated sprite

#define ST_CANVAS_Y           0
#define ST_CANVAS_H         240
#define ST_CANVAS_X2        274
#define ST_LIST_HEADER_Y      5
#define ST_LIST_RULE_Y       22
#define ST_LIST_ROW_START_Y  25
#define ST_LIST_ROW_H        26
#define ST_LIST_COL_SYMBOL    5
#define ST_LIST_COL_PRICE    55
#define ST_LIST_COL_CHANGE  270
#define ST_CHART_HEADER_Y     0
#define ST_CHART_HEADER_H    18
#define ST_CHART_BACK_W      30
#define ST_CHART_TICKER_X    30
#define ST_CHART_TABS_X     130
#define ST_CHART_TAB_W       36
#define ST_CHART_PLOT_Y      18
#define ST_CHART_PLOT_H     196
#define ST_CHART_FOOTER_Y   214

enum class StockSubView : uint8_t { List = 0, ChartDetail = 1, HeatmapDetail = 2 };
enum class StockRange   : uint8_t { D1 = 0, D5 = 1, Mo1 = 2, Ytd = 3 };

struct HeatmapTile { int16_t x, y, w, h; uint8_t tickerIdx; };

struct StockAppState {
    char          tickers[8][8];
    StockSubView  subView;
    float         prices[8];
    float         changePct[8];
    unsigned long lastQuoteFetch;
    uint8_t       chartTickerIdx;
    StockRange    chartRange;
    float         chartPoints[110];
    uint8_t       chartLen;
    float         chartLo, chartHi;
    unsigned long lastChartFetch;
    bool          fetchFailed;
    int           fetchErrorCode;
    uint16_t      fetchErrCount;   // cumulative JSON parse errors since boot (-91..-95); never auto-clears
    uint16_t      fetchOkCount;    // cumulative successful chart fetches since boot; never auto-clears
    uint16_t      quoteOkCount;    // cumulative successful quote fetches since boot; never auto-clears
    StockSubView  prevSubView;
    unsigned long lastHeatmapFetch;
    dataTask::HeatmapQuoteResult heatmapData;
    HeatmapTile   heatmapLayout[20];
    bool          heatmapLayoutDirty;
    char          chartSymbol[8];  // symbol for heatmap drill-through chart
};

class StockApp : public App {
public:
  bool hasPendingAsync() const override { return _pendingAsync; }
  // TASK-518 (P4): in-flight = _pendingAsync — set at the three chart-request
  // sites (drillToChart / drillToChartBySym / the range-tab handler) and
  // cleared in stockTickChart() when a result with matching identity is
  // consumed, plus suspend(). Transient, self-clearing, so hasPendingAsync()
  // is already the right answer and the App default forwards to it verbatim;
  // spelled out here only because this app is one of the ones whose
  // isConnecting() is a trap.
  //
  // isConnecting() NOT reusable: !_everHadData is a never-had-data latch —
  // true from boot until the first successful fetch of ANY sub-view, and it
  // is never re-armed. An idle-but-empty Stock is idle.
  //
  // Not covered: the periodic list-quote and heatmap refreshes enqueue without
  // touching _pendingAsync (they are cadence, not a requested operation).
  // Those are visible to `get idle` through its dataq term instead.
  // TASK-245 / ADR-046: amber "connecting" bar until the first successful fetch
  // (any sub-view) lands; green thereafter.
  bool isConnecting() const override { return !_everHadData; }
  // TASK-246: red bar when the last fetch failed (_s.fetchFailed; set on a failed
  // quote/chart/heatmap result, cleared on success).
  bool hasError() const override { return _s.fetchFailed; }
  // TASK-384: the chart/heatmap "back to list" zones — same geometry
  // handleInput() checks at ST_CHART_HEADER_Y/ST_LIST_RULE_Y — never start a
  // new fetch, so they're safe to process even while a fetch is in flight.
  bool isNavigationTap(int x, int y) const override;

  void init() override;
  void resume() override;

  // TASK-231: enter the view configured by Settings → Stock "mode". Chart and
  // Heatmap have preconditions (a selected ticker / a fetched dataset) that only
  // the drill/enter helpers set up, so reuse them rather than just assigning
  // _s.subView — that is why init() previously hardcoded List. List is the
  // back-navigation base for both detail views.
  void _applyLaunchView();

  void suspend() override { _pendingAsync = false; }
  void tick() override;
  bool handleInput(TouchPhase phase, int x, int y) override;

  bool dbgGet(const char* var, char* buf, int len) const;
  bool dbgSet(const char* var, const char* val);

private:
  bool _pendingAsync = false;
  bool _everHadData  = false;  // TASK-245: any successful fetch (quote/chart/heatmap) yet?
  StockViewMode _appliedMode = StockViewMode::List;  // TASK-231: last launch-view applied
  StockAppState _s = {};

  void repaintError();
  void repaintList();
  void repaintChart();
  void drillToChart(uint8_t tickerIdx);
  void drillToChartBySym(const char* sym, uint8_t rangeIdx);
  void enterHeatmap();
  void backToPrevView();
  void computeHeatmapLayout();
  void repaintHeatmap();
  void stockTickHeatmap();
  void stockTickQuotes();
  void stockTickChart();
};
