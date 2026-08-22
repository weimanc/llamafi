#pragma once
// stock/stockChart.h — StockChart component (M-SRCLAYOUT Stage F / TASK-472).
// Owns the chart-detail view's render/tick/interaction logic; operates on
// the StockAppState owned by StockApp (shared data model, not duplicated —
// see stock/stockShared.h) via a back-reference bound at construction.

#include "stock/stockShared.h"

class StockApp;

class StockChart {
public:
  explicit StockChart(StockApp& app) : _app(app) {}

  void repaint();
  void drillTo(uint8_t tickerIdx);
  void drillToBySym(const char* sym, uint8_t rangeIdx);
  void tick();

private:
  StockApp& _app;
};
