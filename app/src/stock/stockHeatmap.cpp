// stock/stockHeatmap.cpp — StockHeatmap method bodies (M-SRCLAYOUT Stage F / TASK-472).
#include "stock/stockHeatmap.h"
#include "stock/stockApp.h"
#include "util/tftViewportRepair.h"

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

void StockHeatmap::enter() {
  StockAppState& _s = _app._s;
  _s.prevSubView = StockSubView::List;
  _s.subView     = StockSubView::HeatmapDetail;
  if (!_s.lastHeatmapFetch) {
    dataTask::enqueueHeatmapQuote();
    _s.lastHeatmapFetch = millis();
  }
  repaint();
}

void StockHeatmap::computeLayout() {
  StockAppState& _s = _app._s;
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
    // M-CODEQUAL C5 (TASK-461): was raw 275.0f/240 literals.
    wt[i] = _s.heatmapData.marketCap[order[i]] / total
            * ((float)APP_CANVAS_W * (float)(APP_CANVAS_H - ST_LIST_RULE_Y));

  // Squarified treemap — iterative strip layout (y=22..239, top row reserved for header)
  float rx=0, ry=ST_LIST_RULE_Y, rw=APP_CANVAS_W, rh=APP_CANVAS_H-ST_LIST_RULE_Y;
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

void StockHeatmap::repaint() {
  StockAppState& _s = _app._s;
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

void StockHeatmap::tick() {
  StockAppState& _s = _app._s;
  bool& _everHadData = _app._everHadData;
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
    computeLayout();
    repaint();
  }
}
