#pragma once
// stock/stockHeatmap.h — StockHeatmap component (M-SRCLAYOUT Stage F / TASK-472).
// Owns the heatmap-detail view's render/tick/interaction logic; operates on
// the StockAppState owned by StockApp (shared data model, not duplicated —
// see stock/stockShared.h) via a back-reference bound at construction.

#include "stock/stockShared.h"

class StockApp;

class StockHeatmap {
public:
  explicit StockHeatmap(StockApp& app) : _app(app) {}

  void enter();
  void computeLayout();
  void repaint();
  void tick();

private:
  StockApp& _app;
};
