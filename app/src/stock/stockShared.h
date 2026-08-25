#pragma once
// stock/stockShared.h — shared data model + layout constants for the Stock
// app family (StockApp/StockChart/StockHeatmap). TASK-472 (M-SRCLAYOUT
// Stage F) splits the former apps/stockApp.h monolith into three
// components; StockAppState stays a single unified struct (the shared data
// model — see docs/architecture/designs/M-SRCLAYOUT-main-decomposition.md,
// "stock/ becomes three components") owned solely by StockApp and passed by
// reference into StockChart/StockHeatmap. Do not split this struct.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "dataTask.h"

#include "display/tft.h"

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

// Shared between StockApp::repaintList() (list price column) and
// StockChart::repaint() (header price) — defined once in stock/stockApp.cpp.
String formatStockPrice(float price);
