#pragma once
// stock/stockApp.h — StockApp component (M-SRCLAYOUT Stage F / TASK-472).
// Splits the former apps/stockApp.h monolith into three components that
// share one StockAppState (see stock/stockShared.h — the shared data model
// stays unified and lives here, owned by StockApp; only the per-view code
// splits): StockApp (list view + coordination), StockChart, StockHeatmap.
// Self-contained per D0/SF.11. Method bodies live in stockApp.cpp.

#include "appShell.h"
#include "settingsStorage.h"
#include "stock/stockShared.h"
#include "stock/stockChart.h"
#include "stock/stockHeatmap.h"

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
  // StockChart/StockHeatmap operate on this StockApp's shared StockAppState
  // and (StockChart only, for _pendingAsync) busy/first-data flags; grant
  // access without making those private members public.
  friend class StockChart;
  friend class StockHeatmap;

  bool _pendingAsync = false;
  bool _everHadData  = false;  // TASK-245: any successful fetch (quote/chart/heatmap) yet?
  StockViewMode _appliedMode = StockViewMode::List;  // TASK-231: last launch-view applied
  StockAppState _s = {};
  StockChart   _chart{*this};
  StockHeatmap _heatmap{*this};

  // Shared by repaintList() and StockChart::repaint() error paths.
  void repaintError();
  void repaintList();
  void backToPrevView();
  void stockTickQuotes();
};
