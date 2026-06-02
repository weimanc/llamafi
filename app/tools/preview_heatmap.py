#!/usr/bin/env python3
"""preview_heatmap.py — StockApp HeatmapDetail host-side POC.

Phase 1 : Visual POC — live Yahoo Finance screener, squarified treemap,
          List ↔ Heatmap toggle, tile drill-through to chart.
Phase 2 : DUT cost report printed at quit (fetch timing, JSON budget,
          tile compute, estimated ESP32 cycle time).
Phase 3 : Optimization notes printed at quit.

Screen geometry matches firmware exactly:
    320×240 total | taskbar x=275..319 (45 px) | app canvas x=0..274, y=0..239

Usage:
    ~/proj/esp/venv/bin/python3 app/tools/preview_heatmap.py
    ~/proj/esp/venv/bin/python3 app/tools/preview_heatmap.py --scale 3
    ~/proj/esp/venv/bin/python3 app/tools/preview_heatmap.py --no-fetch

Keyboard / mouse:
    click [List] or [Heat] header buttons  — toggle List ↔ Heatmap
    click list row                          — drill to 1D chart
    click heatmap tile                      — drill to 1D chart
    click back zone (x<30, y<18, chart)    — return to prev view
    r    force screener refresh
    +/-  adjust scale
    [/]  decrease / increase ticker count shown (3..25)
    q    quit (prints Phase 2 + 3 reports)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
import time
import urllib.request
from typing import Optional

import dut_fonts as _dut_fonts


# ── screen / firmware geometry ────────────────────────────────────────────────

SCREEN_W  = 320
SCREEN_H  = 240
TASKBAR_X = 275
TASKBAR_W = 45
APP_W     = 275   # x: 0..274
APP_H     = 240   # y: 0..239
HEADER_H  = 18    # shared header strip, y: 0..17

# list-view geometry (mirrors firmware constants in main.cpp)
LIST_HEADER_Y   = 5
LIST_RULE_Y     = 22
LIST_ROW_START  = 25
LIST_ROW_H      = 26
LIST_N_ROWS     = 8
LIST_COL_SYMBOL = 5
LIST_COL_PRICE  = 55
LIST_COL_CHANGE = 270

# heatmap tile canvas
HM_X, HM_Y = 0,      HEADER_H           # (0, 18)
HM_W, HM_H = APP_W,  APP_H - HEADER_H   # (275, 222)

# toggle button zones in header
TOGGLE_LIST_X1, TOGGLE_LIST_X2 = 190, 232
TOGGLE_HEAT_X1, TOGGLE_HEAT_X2 = 233, 274

# chart back zone
BACK_X2 = 30

# taskbar
TASKBAR_SLOT_H     = 40
TASKBAR_SLOT_COUNT = 6

# label visibility threshold (mirrors ADR-036 D6)
LABEL_MIN_W = 40
LABEL_MIN_H = 26

# treemap orientation bias: ramps from 1.0 (large tiles) to HORIZONTAL_BIAS
# (small tiles). BIAS_FULL_SHORT: short-side px at which full bias is reached;
# above that the bias linearly decays back to 1.0 (standard squarify).
HORIZONTAL_BIAS      = 1.5   # max bias; tune 1.3–2.0
BIAS_FULL_SHORT      = 80    # px: short side at/below which full bias applies


# ── colours (RGB) ─────────────────────────────────────────────────────────────

C_BG          = (0,   0,   0)
C_HEADER_BG   = (12,  12,  22)
C_RULE        = (45,  45,  58)
C_TEXT        = (215, 215, 215)
C_TEXT_DIM    = (110, 110, 120)
C_GREEN       = (0,   155, 0)
C_RED         = (175, 25,  25)
C_NEUTRAL     = (30,  30,  42)
C_TOGGLE_ON   = (50,  85,  120)
C_TOGGLE_OFF  = (22,  22,  34)
C_TASKBAR_BG  = (14,  14,  28)
C_TASKBAR_SEP = (35,  35,  55)
C_BACK_BG     = (35,  35,  60)
C_CHART_LINE  = (0,   175, 215)
C_CHART_BG    = (8,   8,   18)

CHANGE_SAT_PCT = 5.0   # ±% at which tile colour saturates to full green/red


# ── Yahoo Finance ─────────────────────────────────────────────────────────────

SCREENER_URL = (
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    "?scrIds=ms_technology&count=20&formatted=false"
)
CHART_URL_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
YF_HEADERS = {"User-Agent": "Mozilla/5.0"}


# ── squarified treemap (Bruls et al.) ─────────────────────────────────────────

def _worst(sizes: list[float], w: float) -> float:
    """Worst aspect ratio for a strip of items with given short-side dimension."""
    if not sizes or w <= 0:
        return float("inf")
    s = sum(sizes)
    if s <= 0:
        return float("inf")
    mx = max(sizes)
    mn = min(sizes)
    return max(w * w * mx / (s * s), s * s / (w * w * mn))


def _squarify(items: list[tuple[float, int]],
              x: float, y: float, w: float, h: float,
              out: list) -> None:
    """
    Recursive squarified layout.
    items  : [(normalized_area, original_idx), ...] sorted descending by area
    w, h   : remaining rectangle in pixels
    out    : accumulator; receives (tile_x, tile_y, tile_w, tile_h, orig_idx)
    """
    if not items or w <= 0 or h <= 0:
        return
    if len(items) == 1:
        a, idx = items[0]
        out.append((round(x), round(y), max(1, round(w)), max(1, round(h)), idx))
        return

    short = min(w, h)
    row_areas: list[float] = []
    row_idxs:  list[int]   = []
    rest = list(items)

    # Greedily extend row while worst aspect ratio improves (or row is empty)
    while rest:
        a, idx = rest[0]
        candidate = row_areas + [a]
        if not row_areas or _worst(candidate, short) <= _worst(row_areas, short):
            row_areas.append(a)
            row_idxs.append(idx)
            rest = rest[1:]
        else:
            break

    row_sum = sum(row_areas)

    t    = max(0.0, 1.0 - short / BIAS_FULL_SHORT)
    bias = 1.0 + (HORIZONTAL_BIAS - 1.0) * t
    if w > h * bias:
        # Strip runs top-to-bottom along the height; width = row_sum / h
        strip_w = row_sum / h
        cy = y
        for a, idx in zip(row_areas, row_idxs):
            th = (a / row_sum) * h
            border = 1 if (strip_w >= 3 and th >= 3) else 0
            out.append((round(x + border), round(cy + border),
                        max(1, round(strip_w - border * 2)),
                        max(1, round(th - border * 2)), idx))
            cy += th
        _squarify(rest, x + strip_w, y, max(0.0, w - strip_w), h, out)
    else:
        # Strip runs left-to-right along the width; height = row_sum / w
        strip_h = row_sum / w
        cx = x
        for a, idx in zip(row_areas, row_idxs):
            tw = (a / row_sum) * w
            border = 1 if (tw >= 3 and strip_h >= 3) else 0
            out.append((round(cx + border), round(y + border),
                        max(1, round(tw - border * 2)),
                        max(1, round(strip_h - border * 2)), idx))
            cx += tw
        _squarify(rest, x, y + strip_h, w, max(0.0, h - strip_h), out)


def compute_treemap(weights: list[float],
                    x: int, y: int, w: int, h: int) -> list[tuple]:
    """
    Squarified treemap over canvas (x, y, w, h).
    weights  : positive floats (market caps); order = original ticker index
    Returns  : list of (tile_x, tile_y, tile_w, tile_h, original_index)
    """
    if not weights or w <= 0 or h <= 0:
        return []
    total = sum(weights)
    if total <= 0:
        return []
    area = float(w * h)
    items = sorted(
        [(v / total * area, i) for i, v in enumerate(weights)],
        key=lambda t: t[0],
        reverse=True,
    )
    out: list = []
    _squarify(items, float(x), float(y), float(w), float(h), out)
    return out


# ── colour helpers ────────────────────────────────────────────────────────────

def change_to_color(pct: float) -> tuple[int, int, int]:
    """Map change% to tile background RGB. Saturates at ±CHANGE_SAT_PCT."""
    t = max(-1.0, min(1.0, pct / CHANGE_SAT_PCT))
    if t >= 0:
        return (0, int(55 + t * 145), 0)
    else:
        return (int(55 + (-t) * 145), 0, 0)


def lighten(c: tuple[int, int, int], f: float = 0.6) -> tuple[int, int, int]:
    return tuple(int(c[i] + (255 - c[i]) * f) for i in range(3))  # type: ignore


# ── data layer ────────────────────────────────────────────────────────────────

class TickerData:
    __slots__ = ("symbol", "price", "change_pct", "market_cap")

    def __init__(self, symbol: str = "", price: float = 0.0,
                 change_pct: float = 0.0, market_cap: float = 0.0):
        self.symbol     = symbol
        self.price      = price
        self.change_pct = change_pct
        self.market_cap = market_cap


def _yf_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=YF_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_screener() -> tuple[list[TickerData], dict]:
    """Single request → top-25 ms_technology tickers with price, change%, marketCap."""
    perf: dict = {}
    t0  = time.perf_counter()
    raw = _yf_get(SCREENER_URL)
    perf["fetch_ms"]  = (time.perf_counter() - t0) * 1000
    perf["raw_bytes"] = len(raw)

    t1  = time.perf_counter()
    doc = json.loads(raw)
    perf["parse_ms"] = (time.perf_counter() - t1) * 1000

    quotes  = doc["finance"]["result"][0]["quotes"]
    tickers = []
    for q in quotes:
        tickers.append(TickerData(
            symbol     = q.get("symbol", "???"),
            price      = float(q.get("regularMarketPrice", 0) or 0),
            change_pct = float(q.get("regularMarketChangePercent", 0) or 0),
            market_cap = float(q.get("marketCap", 0) or 0),
        ))
    return tickers, perf


def fetch_chart_1d(symbol: str) -> list[float]:
    """Fetch 1D 5-min chart; return list of non-null close prices."""
    url = f"{CHART_URL_BASE}{symbol}?interval=5m&range=1d"
    raw = _yf_get(url)
    doc = json.loads(raw)
    closes = (
        doc["chart"]["result"][0]
        .get("indicators", {})
        .get("quote", [{}])[0]
        .get("close", [])
    )
    return [float(v) for v in closes if v is not None]


def make_fake_tickers(n: int = 25) -> list[TickerData]:
    """Offline fallback — plausible random data."""
    syms = ["NVDA","AAPL","MSFT","TSM","AVGO","MU","AMD","ASML","INTC","ORCL",
            "CSCO","LRCX","AMAT","ARM","PLTR","TXN","IBM","KLAC","QCOM","SNDK",
            "PANW","SAP","ADI","ANET","DELL"][:n]
    caps_T = [5.1,4.6,3.3,2.2,2.1,1.1,0.84,0.62,0.58,0.65,
              0.22,0.11,0.18,0.08,0.17,0.16,0.14,0.09,0.12,0.04,
              0.10,0.09,0.08,0.07,0.06][:n]
    result = []
    random.seed(42)
    for s, c in zip(syms, caps_T):
        result.append(TickerData(
            symbol     = s,
            price      = round(random.uniform(50, 950), 2),
            change_pct = random.uniform(-6.5, 6.5),
            market_cap = c * 1e12,
        ))
    return result


# ── main POC class ────────────────────────────────────────────────────────────

class HeatmapPoc:

    def __init__(self, scale: int = 3, no_fetch: bool = False):
        self.scale    = scale
        self.no_fetch = no_fetch

        self.view      = "list"
        self.prev_view = "list"

        self.ticker_count: int           = 20
        self.tickers:   list[TickerData] = []
        self.hm_layout: list[tuple]      = []
        self.loading    = False
        self.error      = ""
        self.perf: dict = {}

        self.chart_symbol:  Optional[str]   = None
        self.chart_prices:  list[float]     = []
        self.chart_loading  = False

        self._lock = threading.Lock()

        # DUT-accurate fonts: Font1 = GLCD 5×7, Font2 = Font16 variable-width 16px
        self._f1, self._f2 = _dut_fonts.load()

    # ── data management ───────────────────────────────────────────────────

    def refresh(self):
        with self._lock:
            if self.loading:
                return
            self.loading = True
        threading.Thread(target=self._do_fetch, daemon=True).start()

    def _do_fetch(self):
        try:
            if self.no_fetch:
                time.sleep(0.2)
                tickers = make_fake_tickers()
                perf: dict = {"fetch_ms": 0, "raw_bytes": 0, "parse_ms": 0}
            else:
                tickers, perf = fetch_screener()

            with self._lock:
                count = self.ticker_count

            t0     = time.perf_counter()
            layout = compute_treemap(
                [max(0.0, t.market_cap) for t in tickers[:count]],
                HM_X, HM_Y, HM_W, HM_H,
            )
            perf["tile_ms"] = (time.perf_counter() - t0) * 1000

            with self._lock:
                self.tickers   = tickers
                self.hm_layout = layout
                self.perf      = perf
                self.loading   = False
                self.error     = ""
        except Exception as e:
            with self._lock:
                self.loading = False
                self.error   = str(e)[:60]

    def drill_chart(self, symbol: str):
        with self._lock:
            self.prev_view     = self.view
            self.view          = "chart"
            self.chart_symbol  = symbol
            self.chart_prices  = []
            self.chart_loading = True
        threading.Thread(target=self._do_fetch_chart, args=(symbol,),
                         daemon=True).start()

    def _do_fetch_chart(self, symbol: str):
        try:
            if self.no_fetch:
                prices = [100 + math.sin(i * 0.25) * 8 + random.gauss(0, 1)
                          for i in range(78)]
            else:
                prices = fetch_chart_1d(symbol)
            with self._lock:
                if self.chart_symbol == symbol:
                    self.chart_prices  = prices
                    self.chart_loading = False
        except Exception:
            with self._lock:
                self.chart_loading = False

    def go_back(self):
        with self._lock:
            self.view = self.prev_view

    def set_view(self, v: str):
        with self._lock:
            self.view = v

    def set_ticker_count(self, n: int):
        with self._lock:
            n = max(3, min(n, len(self.tickers) if self.tickers else 25))
            if n == self.ticker_count:
                return
            self.ticker_count = n
            if self.tickers:
                self.hm_layout = compute_treemap(
                    [max(0.0, t.market_cap) for t in self.tickers[:n]],
                    HM_X, HM_Y, HM_W, HM_H,
                )

    # ── render ────────────────────────────────────────────────────────────

    def render(self):
        from PIL import Image, ImageDraw
        canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), C_BG)
        draw   = ImageDraw.Draw(canvas)

        with self._lock:
            view          = self.view
            tickers       = list(self.tickers)
            layout        = list(self.hm_layout)
            loading       = self.loading
            error         = self.error
            chart_sym     = self.chart_symbol
            chart_prices  = list(self.chart_prices)
            chart_loading = self.chart_loading
            ticker_count  = self.ticker_count

        if view == "list":
            self._render_list(draw, tickers, ticker_count, loading, error)
        elif view == "heatmap":
            self._render_heatmap(draw, tickers, ticker_count, layout, loading, error)
        elif view == "chart":
            self._render_chart(draw, tickers, chart_sym, chart_prices, chart_loading)

        self._render_taskbar(draw)
        return canvas

    def _render_header(self, draw, title: str, active_view: str):
        """Header strip: title left, [List][Heat] toggle right."""
        draw.rectangle([0, 0, APP_W - 1, HEADER_H - 1], fill=C_HEADER_BG)
        self._f2.draw_left(draw, 5, HEADER_H // 2, title, fg=C_TEXT)
        for label, x1, x2, is_active in (
            ("List", TOGGLE_LIST_X1, TOGGLE_LIST_X2, active_view == "list"),
            ("Heat", TOGGLE_HEAT_X1, TOGGLE_HEAT_X2, active_view == "heatmap"),
        ):
            bg = C_TOGGLE_ON if is_active else C_TOGGLE_OFF
            draw.rectangle([x1, 2, x2, HEADER_H - 3], fill=bg)
            self._f1.draw_centered(draw, (x1 + x2) // 2, HEADER_H // 2,
                                   label, fg=C_TEXT)

    def _render_list(self, draw, tickers, ticker_count, loading, error):
        n_rows = min(ticker_count, LIST_N_ROWS)
        self._render_header(draw, f"Tech Stocks ({ticker_count})", "list")
        draw.line([(LIST_COL_SYMBOL, LIST_RULE_Y), (APP_W - 1, LIST_RULE_Y)],
                  fill=C_RULE)

        if loading and not tickers:
            self._f2.draw(draw, 10, 62, "Fetching screener...", fg=C_TEXT_DIM)
            return
        if error and not tickers:
            self._f1.draw(draw, 5, 66, f"Error: {error}", fg=C_RED)
            return

        for i, td in enumerate(tickers[:n_rows]):
            cy = LIST_ROW_START + i * LIST_ROW_H + LIST_ROW_H // 2

            self._f2.draw_left(draw, LIST_COL_SYMBOL, cy, td.symbol, fg=C_TEXT)

            price_str = f"{td.price:.2f}"
            self._f2.draw_left(draw, LIST_COL_PRICE, cy, price_str, fg=C_TEXT)

            sign = "+" if td.change_pct >= 0 else ""
            chg_str = f"{sign}{td.change_pct:.2f}%"
            col = C_GREEN if td.change_pct >= 0 else C_RED
            self._f2.draw_right(draw, LIST_COL_CHANGE, cy, chg_str, fg=col)

            if i < n_rows - 1:
                sep_y = LIST_ROW_START + (i + 1) * LIST_ROW_H - 1
                draw.line([(0, sep_y), (APP_W - 1, sep_y)], fill=C_RULE)

    def _render_heatmap(self, draw, tickers, ticker_count, layout, loading, error):
        self._render_header(draw, f"Tech Heatmap ({ticker_count})", "heatmap")
        draw.rectangle([0, HEADER_H, APP_W - 1, APP_H - 1], fill=C_BG)

        if loading and not tickers:
            self._f2.draw_centered(draw, APP_W // 2, HEADER_H + HM_H // 2,
                                   "Fetching screener...", fg=C_TEXT_DIM)
            return
        if error and not tickers:
            self._f1.draw(draw, 5, HEADER_H + 16, f"Error: {error}", fg=C_RED)
            return
        if not layout:
            return

        for tx, ty, tw, th, idx in layout:
            if idx >= len(tickers):
                continue
            td  = tickers[idx]
            bg  = change_to_color(td.change_pct)
            lbl = lighten(bg, 0.65)

            draw.rectangle([tx, ty, tx + tw - 1, ty + th - 1], fill=bg)

            if tw < 4 or th < 4:
                continue

            cx, cy = tx + tw // 2, ty + th // 2
            sign = "+" if td.change_pct >= 0 else ""
            pct1 = f"{sign}{td.change_pct:.1f}"   # "+2.3"

            if tw >= LABEL_MIN_W and th >= LABEL_MIN_H:
                # Large: Font2 symbol + Font1 change
                self._f2.draw_centered(draw, cx, cy - 5, td.symbol, fg=lbl)
                self._f1.draw_centered(draw, cx, cy + 9, pct1, fg=lbl)
            elif tw >= 28 and th >= 16:
                # Medium: Font1 symbol + Font1 change
                self._f1.draw_centered(draw, cx, cy - 4, td.symbol, fg=lbl)
                self._f1.draw_centered(draw, cx, cy + 5, pct1, fg=lbl)
            elif tw >= 16 and th >= 9:
                # Small: symbol only, drop change first
                self._f1.draw_centered(draw, cx, cy, td.symbol[:4], fg=lbl)
            elif tw >= 12 and th >= 7:
                # Tiny: symbol only (truncated)
                self._f1.draw_centered(draw, cx, cy, td.symbol[:3], fg=lbl)

    def _render_chart(self, draw, tickers, symbol, prices, loading):
        # Header with back zone
        draw.rectangle([0, 0, APP_W - 1, HEADER_H - 1], fill=C_HEADER_BG)
        draw.rectangle([0, 0, BACK_X2 - 1, HEADER_H - 1], fill=C_BACK_BG)
        self._f1.draw_centered(draw, BACK_X2 // 2, HEADER_H // 2, "<", fg=C_TEXT)

        td = next((t for t in tickers if t.symbol == symbol), None)
        if td:
            sign = "+" if td.change_pct >= 0 else ""
            col  = C_GREEN if td.change_pct >= 0 else C_RED
            self._f1.draw_left(draw, BACK_X2 + 4, HEADER_H // 2,
                               f"{symbol}  {td.price:.2f}  {sign}{td.change_pct:.2f}%",
                               fg=C_TEXT)
        else:
            self._f2.draw_left(draw, BACK_X2 + 4, HEADER_H // 2,
                               symbol or "---", fg=C_TEXT)

        chart_y0 = HEADER_H + 2
        chart_y1 = APP_H - 2
        chart_h  = chart_y1 - chart_y0
        draw.rectangle([0, chart_y0, APP_W - 1, chart_y1], fill=C_CHART_BG)

        if loading:
            self._f2.draw_centered(draw, APP_W // 2, chart_y0 + chart_h // 2,
                                   "Loading...", fg=C_TEXT_DIM)
            return
        if not prices:
            self._f2.draw_centered(draw, APP_W // 2, chart_y0 + chart_h // 2,
                                   "No data", fg=C_TEXT_DIM)
            return

        lo, hi  = min(prices), max(prices)
        rng     = hi - lo if hi != lo else 1.0
        pad     = 5
        n       = len(prices)

        def py(p: float) -> int:
            return chart_y1 - pad - round((p - lo) / rng * (chart_h - 2 * pad))

        pts = [(round(i / max(n - 1, 1) * (APP_W - 1)), py(p))
               for i, p in enumerate(prices)]
        if len(pts) >= 2:
            draw.line(pts, fill=C_CHART_LINE, width=1)

        self._f1.draw(draw, 3, chart_y1 - 9, f"{lo:.2f}", fg=C_TEXT_DIM)
        self._f1.draw(draw, 3, chart_y0 + 2, f"{hi:.2f}", fg=C_TEXT_DIM)
        self._f1.draw_right(draw, APP_W - 3, chart_y1 - 5, "1D", fg=C_TEXT_DIM)

    def _render_taskbar(self, draw):
        draw.rectangle([TASKBAR_X, 0, SCREEN_W - 1, SCREEN_H - 1],
                       fill=C_TASKBAR_BG)
        labels = ["S", "C", "W", "$", "M", "St"]
        active_slot = 5   # Stock = last slot (index 5, AppId=7)
        for s in range(TASKBAR_SLOT_COUNT):
            sy = s * TASKBAR_SLOT_H
            if s < TASKBAR_SLOT_COUNT - 1:
                draw.line(
                    [(TASKBAR_X, sy + TASKBAR_SLOT_H - 1),
                     (SCREEN_W - 1, sy + TASKBAR_SLOT_H - 1)],
                    fill=C_TASKBAR_SEP,
                )
            if s == active_slot:
                draw.rectangle(
                    [TASKBAR_X, sy, TASKBAR_X + 2, sy + TASKBAR_SLOT_H - 1],
                    fill=C_GREEN,
                )
            self._f1.draw_centered(
                draw,
                TASKBAR_X + TASKBAR_W // 2, sy + TASKBAR_SLOT_H // 2,
                labels[s], fg=C_TEXT_DIM,
            )

    # ── interaction ───────────────────────────────────────────────────────

    def handle_click(self, lx: int, ly: int):
        if lx >= TASKBAR_X:
            return   # taskbar — not handled in POC

        with self._lock:
            view   = self.view
            tickers = list(self.tickers)
            layout  = list(self.hm_layout)

        if view in ("list", "heatmap"):
            # Toggle header buttons
            if 0 <= ly < HEADER_H:
                if TOGGLE_LIST_X1 <= lx <= TOGGLE_LIST_X2:
                    self.set_view("list")
                    return
                if TOGGLE_HEAT_X1 <= lx <= TOGGLE_HEAT_X2:
                    self.set_view("heatmap")
                    return

            # Content area drill-in
            if view == "list" and ly >= LIST_ROW_START:
                row = (ly - LIST_ROW_START) // LIST_ROW_H
                if 0 <= row < min(LIST_N_ROWS, len(tickers)):
                    self.drill_chart(tickers[row].symbol)

            elif view == "heatmap":
                for tx, ty, tw, th, idx in layout:
                    if tx <= lx < tx + tw and ty <= ly < ty + th:
                        if idx < len(tickers):
                            self.drill_chart(tickers[idx].symbol)
                        break

        elif view == "chart":
            if lx < BACK_X2 and 0 <= ly < HEADER_H:
                self.go_back()

    # ── phase reports ─────────────────────────────────────────────────────

    def print_phase2(self):
        p = self.perf
        print()
        print("═" * 58)
        print("  Phase 2 — DUT Cost Estimate")
        print("═" * 58)
        if not p:
            print("  (no fetch completed — run with live data for timings)")
            print("═" * 58)
            return

        fetch_ms = p.get("fetch_ms", 0)
        parse_ms = p.get("parse_ms", 0)
        raw_b    = p.get("raw_bytes", 0)
        tile_ms  = p.get("tile_ms", 0)

        # DUT estimates:
        # Network fetch: roughly the same (network-bound, not CPU-bound)
        # JSON parse: ~12× slower CPU; ArduinoJson filter reduces work ~4×
        # Tile compute: CPU-bound, ~12× slower; N=25 still trivial
        dut_parse  = parse_ms * 12 / 4
        dut_tile   = tile_ms  * 12
        dut_total  = fetch_ms + dut_parse + dut_tile

        print(f"  Screener fetch (host)  : {fetch_ms:7.0f} ms")
        print(f"  Screener fetch (DUT)   : {'~'+str(round(fetch_ms)):>7s} ms  (network-bound; similar)")
        print(f"  Raw payload            : {raw_b:7d} B   full response")
        print(f"  JSON payload (4 fields): {'~'+str(round(raw_b*4/80)):>7s} B   est. after filter")
        print(f"  ArduinoJson budget     :    8192 B   DynamicJsonDocument with filter")
        print(f"  JSON parse (host)      : {parse_ms:7.2f} ms")
        print(f"  JSON parse (DUT est)   : {'~'+str(round(dut_parse)):>7s} ms  (12× CPU, ÷4 filter)")
        print(f"  Tile compute (host)    : {tile_ms:7.4f} ms  squarify N=25")
        print(f"  Tile compute (DUT est) : {'~'+str(round(dut_tile,2)):>7s} ms  trivial")
        print(f"  ─────────────────────────────────────────────────────")
        print(f"  Total cycle (DUT est)  : {'~'+str(round(dut_total)):>7s} ms")
        print(f"  Refresh interval       :  120 000 ms  (lazy, heatmap active only)")
        print(f"  DUT budget headroom    : {'~'+str(round(120000-dut_total)):>7s} ms  per cycle")
        print("═" * 58)

    @staticmethod
    def print_phase3():
        notes = [
            ("Squarify sort",
             "N=25 is tiny. Insertion sort beats qsort\n"
             "    (no function-pointer call overhead; fits in icache)."),
            ("Layout stability",
             "Compare sorted rank[] not raw market caps.\n"
             "    Skip recompute if rank is unchanged → saves ~tile_ms×12 / cycle."),
            ("Colour LUT",
             "Precompute 64-entry RGB565 palette at startup.\n"
             "    Eliminates per-tile float division in render loop on DUT."),
            ("Tile label bake",
             "Write show_label flag into HeatmapTile at layout time.\n"
             "    Avoids w>=40 && h>=26 branch per tile per frame."),
            ("ArduinoJson budget",
             "StaticJsonDocument<4096> viable with filter\n"
             "    (4 fields × 25 quotes ≈ 100 JSON values stored)."),
            ("Partial TFT repaint",
             "Only redraw tiles whose change% shifted > 0.1%.\n"
             "    TFT SPI bus is the dominant DUT cost; saving redraws matters more\n"
             "    than saving CPU cycles."),
            ("Screener resilience",
             "scrIds=ms_technology is undocumented Yahoo API.\n"
             "    Rate-limit or 4xx → error state (ADR-036 D8). No static fallback.\n"
             "    Monitor for endpoint drift on DUT firmware updates."),
        ]
        print()
        print("═" * 58)
        print("  Phase 3 — Optimization Opportunities")
        print("═" * 58)
        for i, (title, desc) in enumerate(notes, 1):
            print(f"  {i}. {title}:\n    {desc}")
            print()
        print("═" * 58)

    # ── pygame loop ───────────────────────────────────────────────────────

    def run(self):
        try:
            import pygame
        except ImportError:
            sys.exit("pip install pygame  (required for interactive preview)")

        pygame.init()
        pygame.display.set_caption(
            "StockApp Heatmap POC — click=[List]/[Heat] toggle  r=refresh  q=quit"
        )
        scale  = self.scale
        screen = pygame.display.set_mode((SCREEN_W * scale, SCREEN_H * scale))
        clock  = pygame.time.Clock()

        self.refresh()

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    k = event.key
                    if k == pygame.K_q:
                        running = False
                    elif k == pygame.K_r:
                        self.refresh()
                    elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                        scale = min(4, scale + 1)
                        screen = pygame.display.set_mode(
                            (SCREEN_W * scale, SCREEN_H * scale))
                    elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        scale = max(1, scale - 1)
                        screen = pygame.display.set_mode(
                            (SCREEN_W * scale, SCREEN_H * scale))
                    elif k == pygame.K_RIGHTBRACKET:
                        self.set_ticker_count(self.ticker_count + 1)
                    elif k == pygame.K_LEFTBRACKET:
                        self.set_ticker_count(self.ticker_count - 1)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    self.handle_click(mx // scale, my // scale)

            frame = self.render()
            surf  = pygame.image.fromstring(frame.tobytes(), frame.size, "RGB")
            if scale > 1:
                surf = pygame.transform.scale(
                    surf, (SCREEN_W * scale, SCREEN_H * scale))
            screen.blit(surf, (0, 0))
            pygame.display.flip()
            clock.tick(30)

        pygame.quit()
        self.print_phase2()
        self.print_phase3()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scale", type=int, default=3, choices=[1, 2, 3, 4],
                    help="Display scale factor (default 3 → 960×720 window)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="Offline mode — use random fake data (no network calls)")
    args = ap.parse_args()

    poc = HeatmapPoc(scale=args.scale, no_fetch=args.no_fetch)
    poc.run()


if __name__ == "__main__":
    main()
