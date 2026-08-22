// stock/stockChart.cpp — StockChart method bodies (M-SRCLAYOUT Stage F / TASK-472).
#include "stock/stockChart.h"
#include "stock/stockApp.h"
#include "logSink.h"   // LOG_D

void StockChart::repaint() {
  StockAppState& _s = _app._s;
  if (_s.fetchFailed) { _app.repaintError(); return; }
  tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);

  // header: back glyph + ticker + price
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(0xFFFF);
  tft.drawString("<", 5, ST_CHART_HEADER_Y, 2);
  String hdr = String(_s.chartSymbol[0] ? _s.chartSymbol : _s.tickers[_s.chartTickerIdx]);
  hdr += (_s.chartLen > 0)
           ? (" " + formatStockPrice(_s.chartPoints[_s.chartLen - 1]))
           : " ---";
  tft.drawString(hdr, ST_CHART_TICKER_X, ST_CHART_HEADER_Y, 2);

  // range tabs
  static const char* TAB_LABELS[4] = {"1D","5D","1M","YTD"};
  for (int t = 0; t < 4; t++) {
    int tx = ST_CHART_TABS_X + t * ST_CHART_TAB_W;
    if ((uint8_t)_s.chartRange == (uint8_t)t)
      tft.fillRect(tx, ST_CHART_HEADER_Y, ST_CHART_TAB_W, ST_CHART_HEADER_H, 0x4208);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xFFFF);
    tft.drawString(TAB_LABELS[t], tx + ST_CHART_TAB_W / 2, ST_CHART_HEADER_Y + 7, 2);
  }
  tft.setTextDatum(TL_DATUM);

  // plot area
  if (_s.chartLen < 2) {
    tft.drawFastHLine(0, ST_CHART_PLOT_Y + ST_CHART_PLOT_H / 2,
                      ST_CANVAS_X2 + 1, 0x07FF);
  } else {
    float xStep  = (float)ST_CANVAS_X2 / (_s.chartLen - 1);
    float rng    = _s.chartHi - _s.chartLo;
    if (rng < 0.001f) rng = 0.001f;
    float yScale = (float)(ST_CHART_PLOT_H - 2) / rng;
    for (int i = 1; i < (int)_s.chartLen; i++) {
      int x0 = (int)((i - 1) * xStep);
      int x1 = (int)(i       * xStep);
      int y0 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2
               - (int)((_s.chartPoints[i - 1] - _s.chartLo) * yScale);
      int y1 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2
               - (int)((_s.chartPoints[i]     - _s.chartLo) * yScale);
      tft.drawLine(x0, y0, x1, y1, 0x07FF);
    }
  }

  // footer
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(0x7BEF);
  if (_s.chartLen == 0) {
    tft.drawString("lo: ---", 5, ST_CHART_FOOTER_Y, 1);
    tft.setTextDatum(TR_DATUM);
    tft.drawString("hi: ---", ST_CANVAS_X2 - 5, ST_CHART_FOOTER_Y, 1);
  } else {
    tft.drawString(String("lo: ") + String(_s.chartLo, 2), 5, ST_CHART_FOOTER_Y, 1);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(String("hi: ") + String(_s.chartHi, 2),
                   ST_CANVAS_X2 - 5, ST_CHART_FOOTER_Y, 1);
  }
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
}

void StockChart::drillTo(uint8_t tickerIdx) {
  StockAppState& _s = _app._s;
  bool& _pendingAsync = _app._pendingAsync;
  _s.prevSubView    = _s.subView;
  _s.chartTickerIdx = tickerIdx;
  _s.chartSymbol[0] = '\0';
  _s.chartRange     = StockRange::D1;
  _s.subView        = StockSubView::ChartDetail;
  // TASK-380: always fetch on drill-in, keyed to the tapped ticker — a prior
  // fetch for a DIFFERENT ticker within STOCK_CHART_FETCH_D1 previously made
  // this look "still fresh" via a recency-only guard and silently skipped
  // the request. Matches drillToChartBySym()/the tab-switch handler, which
  // already enqueue unconditionally on any symbol/range change.
  dataTask::enqueueStockChart(tickerIdx, (uint8_t)StockRange::D1);
  _s.lastChartFetch = millis();
  _pendingAsync      = true;
  _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
  repaint();
}

void StockChart::drillToBySym(const char* sym, uint8_t rangeIdx) {
  StockAppState& _s = _app._s;
  bool& _pendingAsync = _app._pendingAsync;
  _s.prevSubView = _s.subView;
  strncpy(_s.chartSymbol, sym, 7); _s.chartSymbol[7] = '\0';
  _s.chartRange  = (StockRange)rangeIdx;
  _s.subView     = StockSubView::ChartDetail;
  dataTask::enqueueStockChartBySym(sym, rangeIdx);
  _s.lastChartFetch = millis();
  _pendingAsync     = true;
  _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
  repaint();
}

void StockChart::tick() {
  StockAppState& _s = _app._s;
  bool& _pendingAsync = _app._pendingAsync;
  bool& _everHadData  = _app._everHadData;
  unsigned long now      = millis();
  unsigned long fetchMs  = (_s.chartRange == StockRange::D1)
                             ? STOCK_CHART_FETCH_D1 : STOCK_CHART_FETCH_SLOW;
  if (!_s.lastChartFetch || now - _s.lastChartFetch > fetchMs) {
    if (_s.chartSymbol[0])
      dataTask::enqueueStockChartBySym(_s.chartSymbol, (uint8_t)_s.chartRange);
    else
      dataTask::enqueueStockChart(_s.chartTickerIdx, (uint8_t)_s.chartRange);
    _s.lastChartFetch = now;
  }
  dataTask::StockChartResult r;
  if (dataTask::pollStockChart(&r)) {
    // TASK-300: a result parked while nobody was in chart view (back-out
    // before fetch returned, app switch, range change) can belong to a
    // superseded request — rendering it here shows the wrong symbol/range.
    // Discard on identity mismatch and keep waiting for our own fetch.
    const char* want = _s.chartSymbol[0] ? _s.chartSymbol
                                         : _s.tickers[_s.chartTickerIdx];
    if (strcmp(r.symbol, want) != 0 || r.rangeIdx != (uint8_t)_s.chartRange) {
      LOG_D("stock", "chart drop stale result sym=%s range=%u (want %s/%u)",
            r.symbol, r.rangeIdx, want, (unsigned)_s.chartRange);
      return;
    }
    _pendingAsync = false;
    if (r.ok) {
      memcpy(_s.chartPoints, r.points, r.len * sizeof(float));
      _s.chartLen       = r.len;
      _s.chartLo        = r.lo;
      _s.chartHi        = r.hi;
      _s.fetchFailed    = false;
      _s.fetchErrorCode = 0;
      _s.fetchOkCount++;
      _everHadData = true;   // TASK-245: first data → bar leaves amber
    } else {
      _s.fetchFailed    = true;
      _s.fetchErrorCode = r.errorCode;
      _s.fetchErrCount++;
    }
    repaint();
  }
}
