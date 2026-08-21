// apps/stockApp.cpp — StockApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "apps/stockApp.h"

static uint16_t heatmapColour(float pct) {
    if (pct > 5.0f) pct = 5.0f;
    if (pct < -5.0f) pct = -5.0f;
    if (pct >= 0.0f) {
        float t = pct / 5.0f;
        uint8_t r = (uint8_t)(4.0f * (1.0f - t));
        uint8_t g = (uint8_t)(8.0f + 55.0f * t);
        uint8_t b = (uint8_t)(4.0f * (1.0f - t));
        return ((uint16_t)r << 11) | ((uint16_t)g << 5) | b;
    } else {
        float t = (-pct) / 5.0f;
        uint8_t r = (uint8_t)(4.0f + 27.0f * t);
        uint8_t g = (uint8_t)(8.0f * (1.0f - t));
        uint8_t b = (uint8_t)(4.0f * (1.0f - t));
        return ((uint16_t)r << 11) | ((uint16_t)g << 5) | b;
    }
}

static String formatStockPrice(float price) {
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
    case StockSubView::List:          repaintList();    break;
    case StockSubView::ChartDetail:   repaintChart();   break;
    case StockSubView::HeatmapDetail: repaintHeatmap(); break;
  }
}

void StockApp::_applyLaunchView() {
  _appliedMode = g_settings.stockMode;
  switch (g_settings.stockMode) {
    case StockViewMode::Chart:   drillToChart(0); break;   // first configured ticker
    case StockViewMode::Heatmap: enterHeatmap();  break;
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
    case StockSubView::ChartDetail:   stockTickChart();   break;
    case StockSubView::HeatmapDetail: stockTickHeatmap(); break;
  }
}

bool StockApp::handleInput(TouchPhase phase, int x, int y) {
  if (phase != TouchPhase::Release)
    return (_s.subView == StockSubView::ChartDetail ||
            _s.subView == StockSubView::HeatmapDetail);

  if (_s.subView == StockSubView::List) {
    if (y < ST_LIST_RULE_Y && x > 190) { enterHeatmap(); return true; }
    if (_s.fetchFailed) return true;
    if (y >= ST_LIST_ROW_START_Y && y < ST_CANVAS_Y + ST_CANVAS_H) {
      int rowIdx = constrain((y - ST_LIST_ROW_START_Y) / ST_LIST_ROW_H,
                             0, STOCK_TICKER_COUNT - 1);
      drillToChart((uint8_t)rowIdx);
      return true;
    }
  } else if (_s.subView == StockSubView::HeatmapDetail) {
    if (y < ST_LIST_RULE_Y && x > 190) { backToPrevView(); return true; }
    for (uint8_t i=0; i<_s.heatmapData.count; i++) {
      const HeatmapTile& t = _s.heatmapLayout[i];
      if (x>=t.x && x<t.x+t.w && y>=t.y && y<t.y+t.h) {
        drillToChartBySym(_s.heatmapData.symbols[t.tickerIdx], 0);
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
    repaintHeatmap();
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

void StockApp::repaintChart() {
  if (_s.fetchFailed) { repaintError(); return; }
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

void StockApp::drillToChart(uint8_t tickerIdx) {
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
  repaintChart();
}

void StockApp::drillToChartBySym(const char* sym, uint8_t rangeIdx) {
  _s.prevSubView = _s.subView;
  strncpy(_s.chartSymbol, sym, 7); _s.chartSymbol[7] = '\0';
  _s.chartRange  = (StockRange)rangeIdx;
  _s.subView     = StockSubView::ChartDetail;
  dataTask::enqueueStockChartBySym(sym, rangeIdx);
  _s.lastChartFetch = millis();
  _pendingAsync     = true;
  _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
  repaintChart();
}

void StockApp::enterHeatmap() {
  _s.prevSubView = StockSubView::List;
  _s.subView     = StockSubView::HeatmapDetail;
  if (!_s.lastHeatmapFetch) {
    dataTask::enqueueHeatmapQuote();
    _s.lastHeatmapFetch = millis();
  }
  repaintHeatmap();
}

void StockApp::backToPrevView() {
  _s.subView = _s.prevSubView;
  if (_s.subView == StockSubView::List)        _s.chartSymbol[0] = '\0';
  if (_s.subView == StockSubView::HeatmapDetail) _s.prevSubView = StockSubView::List;
  switch (_s.subView) {
    case StockSubView::List:          repaintList();    break;
    case StockSubView::HeatmapDetail: repaintHeatmap(); break;
    default:                          repaintList();    break;
  }
}

void StockApp::computeHeatmapLayout() {
  uint8_t n = _s.heatmapData.count;
  if (n == 0) { _s.heatmapLayoutDirty = false; return; }
  if (n > 20) n = 20;

  // Insertion-sort order[] by marketCap descending
  uint8_t order[20];
  for (uint8_t i=0; i<n; i++) order[i]=i;
  for (uint8_t i=1; i<n; i++) {
    uint8_t k=order[i]; int j=i-1;
    while (j>=0 && _s.heatmapData.marketCap[order[j]] < _s.heatmapData.marketCap[k])
      { order[j+1]=order[j]; j--; }
    order[j+1]=k;
  }

  // Normalize weights to canvas area px²
  float total=0;
  for (uint8_t i=0; i<n; i++) total += _s.heatmapData.marketCap[order[i]];
  if (total == 0.0f) total = 1.0f;
  float wt[20];
  for (uint8_t i=0; i<n; i++)
    wt[i] = _s.heatmapData.marketCap[order[i]] / total * (275.0f * (float)(240 - ST_LIST_RULE_Y));

  // Squarified treemap — iterative strip layout (y=22..239, top row reserved for header)
  float rx=0, ry=ST_LIST_RULE_Y, rw=275, rh=240-ST_LIST_RULE_Y;
  uint8_t si=0;
  while (si < n && rw > 0.5f && rh > 0.5f) {
    bool horiz = (rh > rw);
    float slen = (rw < rh) ? rw : rh;

    float sum=0, smax=0, smin=1e30f;
    uint8_t ei = si;

    for (uint8_t i=si; i<n; i++) {
      float ns = sum + wt[i];
      float nx = (wt[i] > smax) ? wt[i] : smax;
      float ni = (i==si || wt[i] < smin) ? wt[i] : smin;
      float nw = (slen*slen*nx/(ns*ns) > ns*ns/(slen*slen*ni)) ?
                  slen*slen*nx/(ns*ns) : ns*ns/(slen*slen*ni);
      float ow = (i==si) ? 1e30f :
                 (slen*slen*smax/(sum*sum) > sum*sum/(slen*slen*smin) ?
                  slen*slen*smax/(sum*sum) : sum*sum/(slen*slen*smin));
      if (nw <= ow || i==si) { sum=ns; smax=nx; smin=ni; ei=i+1; }
      else break;
    }

    // Flush strip [si..ei) into remaining rect
    if (horiz) {
      float sh = sum / rw;
      float cx = rx;
      for (uint8_t i=si; i<ei; i++) {
        float tw = wt[i] / sh;
        HeatmapTile& t = _s.heatmapLayout[i];
        t.x = (int16_t)roundf(cx);
        t.y = (int16_t)roundf(ry);
        t.h = (int16_t)roundf(sh);
        t.w = (i==ei-1) ? (int16_t)(roundf(rx+rw) - t.x)
                         : (int16_t)(roundf(cx+tw) - t.x);
        t.tickerIdx = order[i];
        cx += tw;
      }
      ry += sh; rh -= sh;
    } else {
      float sw = sum / rh;
      float cy = ry;
      for (uint8_t i=si; i<ei; i++) {
        float th = wt[i] / sw;
        HeatmapTile& t = _s.heatmapLayout[i];
        t.x = (int16_t)roundf(rx);
        t.y = (int16_t)roundf(cy);
        t.w = (int16_t)roundf(sw);
        t.h = (i==ei-1) ? (int16_t)(roundf(ry+rh) - t.y)
                         : (int16_t)(roundf(cy+th) - t.y);
        t.tickerIdx = order[i];
        cy += th;
      }
      rx += sw; rw -= sw;
    }
    si = ei;
  }
  _s.heatmapLayoutDirty = false;
}

void StockApp::repaintHeatmap() {
  tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
  // Header strip (y=0..21) — title left, LIST toggle right
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(0xFFE0, TFT_BLACK);
  tft.drawString("MKTCAP HEAT", ST_LIST_COL_SYMBOL, ST_LIST_HEADER_Y, 2);
  tft.setTextDatum(TR_DATUM);
  tft.setTextColor(0x07E0, TFT_BLACK);
  tft.drawString("<LIST", ST_CANVAS_X2 - 2, ST_LIST_HEADER_Y, 2);
  tft.setTextDatum(TL_DATUM);
  tft.drawFastHLine(ST_LIST_COL_SYMBOL, ST_LIST_RULE_Y,
                    ST_CANVAS_X2 - ST_LIST_COL_SYMBOL, 0x4208);
  if (!_s.heatmapData.ok && _s.heatmapData.errorCode == 0) {
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0x7BEF, TFT_BLACK);
    tft.drawString("LOADING...", 137, 120, 2);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    return;
  }
  if (!_s.heatmapData.ok) {
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xF800, TFT_BLACK);
    tft.drawString("HEATMAP FETCH FAILED", 137, 100, 2);
    char buf[20]; snprintf(buf, sizeof(buf), "ERR %d", _s.heatmapData.errorCode);
    tft.drawString(buf, 137, 125, 2);
    tft.setTextColor(0x7BEF, TFT_BLACK);
    tft.drawString("retry in 120s", 137, 150, 1);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    return;
  }
  tft.setTextDatum(MC_DATUM);
  for (uint8_t i=0; i<_s.heatmapData.count; i++) {
    const HeatmapTile& t = _s.heatmapLayout[i];
    if (t.w <= 0 || t.h <= 0) continue;
    float pct = _s.heatmapData.changePct[t.tickerIdx];
    uint16_t col = heatmapColour(pct);
    tft.fillRect(t.x, t.y, t.w, t.h, col);
    tft.drawRect(t.x, t.y, t.w, t.h, 0x2104);
    int16_t cx = t.x + t.w / 2;
    int16_t cy = t.y + t.h / 2;
    tft.setTextColor(TFT_WHITE, col);
    const char* sym = _s.heatmapData.symbols[t.tickerIdx];
    char pb[10]; snprintf(pb, sizeof(pb), "%+.1f%%", pct);
    if (t.h >= HM_T1_H && t.w >= HM_T1_W) {
      tft.drawString(sym, cx, cy - 9, 2);
      tft.drawString(pb,  cx, cy + 9, 2);
    } else if (t.h >= HM_T2_H && t.w >= HM_T2_W) {
      tft.drawString(sym, cx, cy - 5, 2);
      tft.drawString(pb,  cx, cy + 9, 1);
    } else if (t.h >= HM_T3_H && t.w >= HM_T3_W) {
      tft.drawString(sym, cx, cy - 5, 1);
      tft.drawString(pb,  cx, cy + 5, 1);
    } else if (t.h >= HM_T4_H && t.w >= HM_T4_W) {
      tft.drawString(sym, cx, cy - 5, 1);
      tft.drawString(pb,  cx, cy + 5, 1);
    } else if (t.h >= HM_T5_H && t.w >= HM_T5_W && (size_t)(strlen(sym) * 6) <= (size_t)t.w) {
      tft.drawString(sym, cx, cy, 1);
    } else if (t.w >= HM_T6_MIN_W) {
      TFT_eSprite spr(&tft);
      uint8_t  slen = (uint8_t)strlen(sym);
      uint8_t  plen = (uint8_t)strlen(pb);
      uint16_t symW = (uint16_t)slen * 6;
      uint16_t pctW = (uint16_t)plen * 6;
      // After -90° rotation sprite-left→screen-bottom, sprite-right→screen-top.
      // Layout [pct|SEP|sym] so sym lands above pct on screen.
      bool showRotPct = (t.h >= (int16_t)(symW + HM_T6_SEP + pctW));
      uint16_t sprW   = showRotPct ? (pctW + HM_T6_SEP + symW) : symW;
      if (spr.createSprite(sprW, 8)) {
        spr.fillSprite(col);
        spr.setTextFont(1);
        spr.setTextColor(TFT_WHITE, col);
        if (showRotPct) {
          spr.drawString(pb,  0,                0, 1);
          spr.drawString(sym, pctW + HM_T6_SEP, 0, 1);
        } else {
          spr.drawString(sym, 0, 0, 1);
        }
        spr.setPivot(sprW / 2, 4);
        tft.setPivot(cx, cy);
        withViewportRepair(tft, t.x, t.y, t.w, t.h, [&]{
          spr.pushRotated(-90, col);
        });
        spr.deleteSprite();
      }
    }
  }
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
}

void StockApp::stockTickHeatmap() {
  unsigned long now = millis();
  if (!_s.lastHeatmapFetch || now - _s.lastHeatmapFetch > STOCK_HEATMAP_FETCH_MS) {
    dataTask::enqueueHeatmapQuote();
    _s.lastHeatmapFetch = now;
  }
  dataTask::HeatmapQuoteResult r;
  if (dataTask::pollHeatmapQuote(&r)) {
    if (r.ok) {
      _s.heatmapData        = r;
      _s.heatmapLayoutDirty = true;
      _everHadData = true;   // TASK-245: first data → bar leaves amber
      _s.fetchFailed = false; // TASK-246: clear red on success
    } else if (!_s.heatmapData.ok) {
      // No good data yet — propagate error so screen shows it
      _s.heatmapData        = r;
      _s.heatmapLayoutDirty = true;
      _s.fetchFailed = true;  // TASK-246: failed heatmap fetch, no good data → red
    }
    // else: keep last good data on screen; transient fetch error is silently retried
    // (no red — we still have valid data to show)
  }
  if (_s.heatmapLayoutDirty) {
    computeHeatmapLayout();
    repaintHeatmap();
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

void StockApp::stockTickChart() {
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
    repaintChart();
  }
}
