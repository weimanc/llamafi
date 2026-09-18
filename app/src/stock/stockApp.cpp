// stock/stockApp.cpp — StockApp method bodies (M-SRCLAYOUT Stage F / TASK-472).
#include "stock/stockApp.h"
#include "settingsStorage.h"  // g_settings

// Shared with StockChart::repaint() (declared in stock/stockShared.h).
String formatStockPrice(float price) {
  if (price >= 1000.0f) return String((int)price);
  if (price >= 10.0f)   return String(price, 2);
  return String(price, 4);
}

bool StockApp::isNavigationTap(int x, int y) const {
  if (_s.subView == StockSubView::ChartDetail)
    return y >= ST_CHART_HEADER_Y && y < ST_CHART_HEADER_Y + ST_CHART_HEADER_H
           && x < ST_CHART_BACK_W * 2;
  if (_s.subView == StockSubView::HeatmapDetail)
    return y < ST_LIST_RULE_Y && x > 190;
  return false;
}

void StockApp::init() {
  for (int i = 0; i < 8; i++)
    strlcpy(_s.tickers[i], g_settings.stockTickers[i], 8);
  dataTask::configureStockTickers(
      const_cast<const char(*)[8]>(g_settings.stockTickers));
  _s.subView     = StockSubView::List;
  _s.prevSubView = StockSubView::List;
  // TASK-247: do NOT blindly fetch the 8-ticker list quote here — when launching
  // into Heatmap/Chart mode that ~16 s batch (8 sequential Yahoo GETs) is wasted
  // and queues *ahead* of the view's real fetch. _applyLaunchView() enqueues only
  // what the launch view needs (List → quote, Heatmap → screener, Chart → chart).
  _applyLaunchView();   // TASK-231: honour Settings → Stock mode
}

void StockApp::resume() {
  // TASK-706 (M-DATATASK-result-staleness-rule, rule items 3 & 4): drain
  // both of StockApp's mailboxes on every ordinary resume(), unconditionally
  // — the same discard `dbgSet`'s "triggerFetch" handler already does below
  // for its debug-injected reset path (TASK-300), now also on the real
  // resume boundary it was one line short of covering. Runs regardless of
  // which subView is active: a result can park from a chart that was
  // visible before this app was suspended even if the user backed out to
  // List first, and a quote result can equally park while the chart was in
  // view. Reset both fetch gates so the next tick() re-enqueues rather than
  // treating the drained-and-discarded slot as already satisfied.
  {
    dataTask::StockQuoteResult staleQuote;
    dataTask::pollStockQuote(&staleQuote);
  }
  {
    dataTask::StockChartResult staleChart;
    dataTask::pollStockChart(&staleChart);
  }
  _s.lastQuoteFetch = 0;
  _s.lastChartFetch = 0;

  bool changed = false;
  for (int i = 0; i < 8; i++) {
    if (strcmp(_s.tickers[i], g_settings.stockTickers[i]) != 0) {
      strlcpy(_s.tickers[i], g_settings.stockTickers[i], 8);
      changed = true;
    }
  }
  if (changed) {
    dataTask::configureStockTickers(
        const_cast<const char(*)[8]>(g_settings.stockTickers));
    _s.lastQuoteFetch = 0;
  }
  // TASK-231: if the launch-view setting changed since we last applied it
  // (e.g. the user just changed it in Settings), honour it now; otherwise
  // preserve whatever sub-view the user navigated to in-session.
  if (g_settings.stockMode != _appliedMode) {
    _applyLaunchView();
    return;
  }
  switch (_s.subView) {
    case StockSubView::List:          repaintList();       break;
    case StockSubView::ChartDetail:   _chart.repaint();    break;
    case StockSubView::HeatmapDetail: _heatmap.repaint();  break;
  }
}

void StockApp::_applyLaunchView() {
  _appliedMode = g_settings.stockMode;
  switch (g_settings.stockMode) {
    case StockViewMode::Chart:   _chart.drillTo(0); break;   // first configured ticker
    case StockViewMode::Heatmap: _heatmap.enter();  break;
    case StockViewMode::List:
    default:
      _s.subView     = StockSubView::List;
      _s.prevSubView = StockSubView::List;
      dataTask::enqueue(dataTask::DATA_FETCH_STOCK_QUOTE);  // TASK-247: only when List is the launch view
      _s.lastQuoteFetch = millis();
      repaintList();
      break;
  }
}

void StockApp::tick() {
  switch (_s.subView) {
    case StockSubView::List:          stockTickQuotes();  break;
    case StockSubView::ChartDetail:   _chart.tick();      break;
    case StockSubView::HeatmapDetail: _heatmap.tick();    break;
  }
}

bool StockApp::handleInput(TouchPhase phase, int x, int y) {
  if (phase != TouchPhase::Release)
    return (_s.subView == StockSubView::ChartDetail ||
            _s.subView == StockSubView::HeatmapDetail);

  if (_s.subView == StockSubView::List) {
    if (y < ST_LIST_RULE_Y && x > 190) { _heatmap.enter(); return true; }
    if (_s.fetchFailed) return true;
    if (y >= ST_LIST_ROW_START_Y && y < ST_CANVAS_Y + ST_CANVAS_H) {
      int rowIdx = constrain((y - ST_LIST_ROW_START_Y) / ST_LIST_ROW_H,
                             0, STOCK_TICKER_COUNT - 1);
      _chart.drillTo((uint8_t)rowIdx);
      return true;
    }
  } else if (_s.subView == StockSubView::HeatmapDetail) {
    if (y < ST_LIST_RULE_Y && x > 190) { backToPrevView(); return true; }
    for (uint8_t i=0; i<_s.heatmapData.count; i++) {
      const HeatmapTile& t = _s.heatmapLayout[i];
      if (x>=t.x && x<t.x+t.w && y>=t.y && y<t.y+t.h) {
        _chart.drillToBySym(_s.heatmapData.symbols[t.tickerIdx], 0);
        return true;
      }
    }
    return true;
  } else {
    if (y >= ST_CHART_HEADER_Y && y < ST_CHART_HEADER_Y + ST_CHART_HEADER_H) {
      if (x < ST_CHART_BACK_W * 2) {
        backToPrevView();
        return true;
      }
      if (!_s.fetchFailed && x >= ST_CHART_TABS_X) {
        uint8_t tab = (uint8_t)constrain((x - ST_CHART_TABS_X) / ST_CHART_TAB_W, 0, 3);
        _s.chartRange     = (StockRange)tab;
        _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
        if (_s.chartSymbol[0])
          dataTask::enqueueStockChartBySym(_s.chartSymbol, tab);
        else
          dataTask::enqueueStockChart(_s.chartTickerIdx, tab);
        _s.lastChartFetch = millis();
        _pendingAsync     = true;
        return true;
      }
    }
    return true;
  }
  return false;
}

bool StockApp::dbgGet(const char* var, char* buf, int len) const {
  if (strcmp(var, "stockSubView") == 0) {
    snprintf(buf, len, "\"var\":\"stockSubView\",\"val\":\"%s\",\"last\":true",
             _s.subView == StockSubView::HeatmapDetail ? "heatmap" :
             _s.subView == StockSubView::ChartDetail   ? "chart"   : "list");
    return true;
  }
  if (strcmp(var, "stockChartTicker") == 0) {
    snprintf(buf, len, "\"var\":\"stockChartTicker\",\"val\":\"%s\",\"last\":true",
             _s.chartSymbol[0] ? _s.chartSymbol : _s.tickers[_s.chartTickerIdx]);
    return true;
  }
  if (strcmp(var, "stockChartRange") == 0) {
    const char* r = (_s.chartRange == StockRange::D1)  ? "D1"
                  : (_s.chartRange == StockRange::D5)  ? "D5"
                  : (_s.chartRange == StockRange::Mo1) ? "Mo1" : "Ytd";
    snprintf(buf, len, "\"var\":\"stockChartRange\",\"val\":\"%s\",\"last\":true", r);
    return true;
  }
  if (strcmp(var, "lastQuoteFetch") == 0) {
    snprintf(buf, len, "\"var\":\"lastQuoteFetch\",\"val\":%lu,\"last\":true",
             _s.lastQuoteFetch);
    return true;
  }
  if (strcmp(var, "lastChartFetch") == 0) {
    snprintf(buf, len, "\"var\":\"lastChartFetch\",\"val\":%lu,\"last\":true",
             _s.lastChartFetch);
    return true;
  }
  if (strcmp(var, "fetchErrCount") == 0) {
    snprintf(buf, len, "\"var\":\"fetchErrCount\",\"val\":%u,\"last\":true",
             _s.fetchErrCount);
    return true;
  }
  if (strcmp(var, "fetchOkCount") == 0) {
    snprintf(buf, len, "\"var\":\"fetchOkCount\",\"val\":%u,\"last\":true",
             _s.fetchOkCount);
    return true;
  }
  if (strcmp(var, "quoteOkCount") == 0) {
    snprintf(buf, len, "\"var\":\"quoteOkCount\",\"val\":%u,\"last\":true",
             _s.quoteOkCount);
    return true;
  }
  if (strcmp(var, "chartLen") == 0) {
    snprintf(buf, len, "\"var\":\"chartLen\",\"val\":%u,\"last\":true",
             _s.chartLen);
    return true;
  }
  if (strcmp(var, "fetchFailed") == 0) {
    snprintf(buf, len, "\"var\":\"fetchFailed\",\"val\":%s,\"last\":true",
             _s.fetchFailed ? "true" : "false");
    return true;
  }
  if (strcmp(var, "heatmapCount") == 0) {
    snprintf(buf, len, "\"var\":\"heatmapCount\",\"val\":%u,\"last\":true",
             _s.heatmapData.count);
    return true;
  }
  for (int i = 0; i < 8; i++) {
    char key[16]; snprintf(key, sizeof(key), "stockTicker%d", i);
    if (strcmp(var, key) == 0) {
      snprintf(buf, len, "\"var\":\"%s\",\"val\":\"%s\",\"last\":true",
               key, _s.tickers[i]);
      return true;
    }
  }
  return false;
}

bool StockApp::dbgSet(const char* var, const char* val) {
  if (strcmp(var, "fetchFailed") == 0) {
    _s.fetchFailed = val && strcmp(val, "0") != 0;
    return true;
  }
  // TASK-247: force the launch-view mode so VE can deterministically exercise
  // List (0) / Chart (1) / Heatmap (2) regardless of persisted settings. Takes
  // effect on the next Stock launch/resume (resume() re-applies on mode change).
  if (strcmp(var, "stockMode") == 0) {
    int m = val ? atoi(val) : 0;
    if (m < 0 || m > 2) return false;
    g_settings.stockMode = (StockViewMode)m;
    return true;
  }
  if (strcmp(var, "fetchErrorCode") == 0) {
    _s.fetchErrorCode = val ? atoi(val) : 0;
    return true;
  }
  if (strcmp(var, "triggerFetch") == 0 && val && strcmp(val, "1") == 0) {
    _s.lastQuoteFetch = 0;
    _s.lastChartFetch = 0;
    _s.chartLen       = 0;
    _s.fetchFailed    = false;
    // TASK-300: also drop any parked (undelivered) chart result — "reset
    // chart fetch state" must include it, or the next drill-in's first tick
    // pops the stale result and the T178 placeholder check reads its len.
    dataTask::StockChartResult discard;
    dataTask::pollStockChart(&discard);
    return true;
  }
  if (strcmp(var, "fetchErrCount") == 0) {
    _s.fetchErrCount = 0;
    return true;
  }
  if (strcmp(var, "fetchOkCount") == 0) {
    _s.fetchOkCount = 0;
    return true;
  }
  if (strcmp(var, "quoteOkCount") == 0) {
    _s.quoteOkCount = 0;
    return true;
  }
  if (strcmp(var, "triggerHeatmap") == 0) {
    // Enter heatmap sub-view and trigger an immediate fetch (debug/testing).
    _s.prevSubView    = _s.subView;
    _s.subView        = StockSubView::HeatmapDetail;
    _s.lastHeatmapFetch = 0;  // force immediate fetch on next tick
    _heatmap.repaint();
    return true;
  }
  return false;
}

void StockApp::repaintError() {
  tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(0xF800, TFT_BLACK);
  tft.setTextFont(2);
  tft.drawString("STOCK FETCH FAILED", 137, 100);
  char buf[24];
  snprintf(buf, sizeof(buf), "NET ERR  %d", _s.fetchErrorCode);
  tft.drawString(buf, 137, 125);
  tft.setTextColor(0x7BEF, TFT_BLACK);
  tft.setTextFont(1);
  tft.drawString("retrying in 60s...", 137, 150);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
}

void StockApp::repaintList() {
  if (_s.fetchFailed) { repaintError(); return; }
  tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(0xFFE0);
  tft.drawString("STOCK TERMINAL", ST_LIST_COL_SYMBOL, ST_LIST_HEADER_Y, 2);
  // Toggle button — tap to enter HeatmapDetail
  tft.setTextDatum(TR_DATUM);
  tft.setTextColor(0x07E0, TFT_BLACK);
  tft.drawString("HEAT>", ST_CANVAS_X2 - 2, ST_LIST_HEADER_Y, 2);
  tft.setTextDatum(TL_DATUM);
  tft.drawFastHLine(ST_LIST_COL_SYMBOL, ST_LIST_RULE_Y,
                    ST_CANVAS_X2 - ST_LIST_COL_SYMBOL, 0x4208);
  int yPos = ST_LIST_ROW_START_Y;
  for (int i = 0; i < STOCK_TICKER_COUNT; i++) {
    int base = yPos + 11;
    tft.setTextColor(0xFFFF);
    tft.drawString(_s.tickers[i], ST_LIST_COL_SYMBOL, base, 2);
    tft.setTextColor(0x07FF);
    tft.drawString(_s.lastQuoteFetch
                     ? formatStockPrice(_s.prices[i])
                     : String("---"),
                   ST_LIST_COL_PRICE, base, 2);
    tft.setTextDatum(TR_DATUM);
    if (!_s.lastQuoteFetch) {
      tft.setTextColor(0x7BEF);
      tft.drawString("---", ST_LIST_COL_CHANGE, base, 2);
    } else {
      tft.setTextColor((_s.changePct[i] >= 0) ? (uint16_t)0x07E0 : (uint16_t)0xF800);
      String pct = (_s.changePct[i] >= 0 ? String("+") : String(""))
                   + String(_s.changePct[i], 1) + "%";
      tft.drawString(pct, ST_LIST_COL_CHANGE, base, 2);
    }
    tft.setTextDatum(TL_DATUM);
    yPos += ST_LIST_ROW_H;
  }
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
}

void StockApp::backToPrevView() {
  _s.subView = _s.prevSubView;
  if (_s.subView == StockSubView::List)        _s.chartSymbol[0] = '\0';
  // TASK-580 (G-1). This guard read `== HeatmapDetail`, which covers only ONE
  // of the two detail views you can back INTO. The other one is a fixed point:
  // with prevSubView == ChartDetail (which `set triggerHeatmap` produces
  // whenever it is issued from a chart — line 248 captures whatever subView is
  // current), the line above makes subView := ChartDetail, this guard does not
  // fire, and every subsequent back tap is the identity. Reproduced
  // deterministically on hardware 2026-09-06 (`T204,T196,T200`): three
  // consecutive back taps, all CONSUMED, stockSubView "chart" after each — and
  // it costs six Stock ids a verdict in every full suite run, since they can no
  // longer normalize to list view.
  //
  // The invariant is simply that List is the back target of any detail view we
  // land on. The legitimate two-level path (List -> Heatmap -> Chart-by-symbol)
  // is unaffected: backing out of that chart lands on HeatmapDetail, which this
  // sets to List exactly as the old line did.
  if (_s.subView != StockSubView::List) _s.prevSubView = StockSubView::List;
  switch (_s.subView) {
    case StockSubView::List:          repaintList();       break;
    case StockSubView::HeatmapDetail: _heatmap.repaint();  break;
    default:                          repaintList();       break;
  }
}

void StockApp::stockTickQuotes() {
  unsigned long now = millis();
  if (!_s.lastQuoteFetch || now - _s.lastQuoteFetch > STOCK_QUOTE_FETCH_MS) {
    dataTask::enqueue(dataTask::DATA_FETCH_STOCK_QUOTE);
    _s.lastQuoteFetch = now;
  }
  dataTask::StockQuoteResult r;
  if (dataTask::pollStockQuote(&r)) {
    if (r.ok) {
      for (int i = 0; i < STOCK_TICKER_COUNT; i++) {
        _s.prices[i]    = r.prices[i];
        _s.changePct[i] = r.changePct[i];
      }
      _s.fetchFailed    = false;
      _s.fetchErrorCode = 0;
      _s.quoteOkCount++;
      _everHadData = true;   // TASK-245: first data → bar leaves amber
    } else {
      _s.fetchFailed    = true;
      _s.fetchErrorCode = r.errorCode;
      _s.fetchErrCount++;
    }
    repaintList();
  }
}
