#pragma once
// pleditView.h — the one Winamp PLEDIT renderer (M-PLEDIT-ABSTRACTION, ADR-059 D4).
//
// PLEDIT was implemented twice (winampDisplay.h for the Spotify queue,
// webRadioApp.h for the station list) and the two copies had drifted. This
// header owns the union of what they do — chrome blit, row layout and
// truncation, duration column, total-time bottom bar, synthetic scroll thumb,
// velocity scroll, direct-scroll right strip and the seqno-diff redraw gate —
// behind a PlaylistSource interface.
//
// TASK-411 wires the Spotify caller only; webRadioApp.h is deliberately
// untouched so a pixel-identity failure implicates exactly one source. The
// divergence enumeration that TASK-412 must resolve lives in
// docs/architecture/designs/M-PLEDIT-ABSTRACTION-playlist-source.md
// § Divergence log.
//
// Everything here is a verbatim behavioural transcription of the Spotify copy;
// where a WebRadio behaviour differs it is recorded in that log, NOT adopted
// here. The gate for this task is pixel identity, so "obvious" cleanups to the
// geometry, the gesture thresholds or the draw order are out of scope.
//
// State ownership: this view owns the PLEDIT scroll offset, the PLEDIT drag
// anchors, the velocity integrator, the redraw gate and the optimistic
// tap highlight. The host keeps the arbitrating drag state for its OTHER
// gestures (volume, posbar, taskbar) and asks dragging() about this one —
// there is a single owner per gesture, not a mirrored copy.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <string.h>

#include "gen/skin_layout.h"
#include "gen/shell_layout.h"   // TASKBAR_X — the right edge the gutter fill stops at
#include "logSink.h"
#include "skinBlit.h"
#include "touch/hitbox.h"        // Rect / hitTest / hitTestRow — the shared primitive
#include "touch/scrollTuning.h"  // SCROLL_DEAD_ZONE_PX, SCROLL_SPEED_K_DEFAULT, PLEDIT_TAP_*
#include "util/textFit.h"

extern TFT_eSPI tft;
extern const uint16_t SKIN_FONT[];
extern const SkinUV   SKIN_GLYPH[128];

// NOTE (DEV-4 / TASK-327): no default member initialisers in these structs.
// Under -std=gnu++11 an NSDMI makes the struct a non-aggregate and every
// PlRow{...} brace-init call site stops compiling.
struct PlRow {
  char     text[64];      // fully composed row text, source-formatted
  uint32_t durationSec;   // 0 = no duration column for this row
  bool     current;       // the item the source considers "playing"
};

enum PlCap : uint8_t {
  CAP_PLAY = 1, CAP_REORDER = 2, CAP_REMOVE = 4, CAP_ADD = 8, CAP_SAVE = 16
};

// Result of a release that ended a PLEDIT gesture. Aggregate — see DEV-4.
struct PlReleaseResult {
  bool          tapDispatched;  // a row tap was routed to PlaylistSource::onTap()
  unsigned long cooldownMs;     // inter-gesture cooldown the host should arm
};

// ── The source interface (design §2.1, ADR-059 D4) ──────────────────────────
// Invariants (design §2.2): row() is called only for idx < the count captured
// in the same repaint; seqno() changes iff rendered content changes; row() may
// block but never runs on the audio pump task; a cap that is not advertised
// means the renderer HIDES the control rather than relying on a default-false
// mutator; mutators run only from loopTask, only outside an active drag.
struct PlaylistSource {
  virtual uint16_t count()  = 0;
  virtual bool     row(uint16_t idx, PlRow& out) = 0;   // may block on SD
  virtual uint32_t seqno()  = 0;
  virtual uint8_t  caps()   = 0;
  virtual uint32_t totalSec() = 0;
  virtual void     onTap(uint16_t idx) = 0;
  // Not in the design sketch: the renderer owns the redraw gate, so it is the
  // only code that knows WHEN a seqno advance was actually consumed (the
  // PLAYLIST_DRAW_MIN_MS rate limit can defer one). Source-side bookkeeping
  // that must stay in lockstep with the gate hangs off this rather than off a
  // second seqno tracker in the caller.
  virtual void     onListReset() {}
  virtual bool     move(uint16_t from, uint16_t to) { (void)from; (void)to; return false; }
  virtual bool     remove(uint16_t idx)             { (void)idx; return false; }
};

class PleditView {
public:
  // Drag ownership for the PLEDIT zones only. The host's own drag enum keeps
  // its volume/posbar/taskbar states; these two live here.
  enum DragMode : uint8_t { DRAG_NONE = 0, DRAG_ROWS, DRAG_STRIP };

  // ── Redraw gate ───────────────────────────────────────────────────────────

  // Full PLEDIT repaint, gated exactly as the Spotify copy was: a seqno change
  // OR a pending scroll repaint, with seqno changes additionally rate-limited
  // to PLAYLIST_DRAW_MIN_MS. Cheap to call unconditionally from the main loop.
  void draw(PlaylistSource& src, int originX) {
    const unsigned long now = millis();
    const uint32_t sq = src.seqno();
    const bool seqnoChanged = (sq != _lastSeqno);
    if (!seqnoChanged && !_scrollDirty) return;
    if (seqnoChanged && now - _lastDrawMs < PLAYLIST_DRAW_MIN_MS) return;
    _scrollDirty = false;
    _lastDrawMs  = now;
    if (seqnoChanged) {
      _lastSeqno = sq;
      if (_drag == DRAG_ROWS) {
        _drag           = DRAG_NONE;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
      }
      _scrollOffset   = 0;   // TASK-051f
      _optimisticRow  = -1;  // TASK-051a: a new list clears the optimistic highlight
      src.onListReset();
    }

    const uint16_t count = src.count();
    _lastVisibleRows = min((int)count, PLEDIT_ROW_COUNT);
    _lastCount       = (uint8_t)min((int)count, 255);
    _repaints++;   // ADR-059 D12 — see repaints()

    tft.startWrite();

    // Frame chrome (gutters, title bar, side tiles, scrollbar thumb, bottom
    // bar). The bottom bar sits below the rows area, so its order versus the
    // rows below is irrelevant — disjoint regions.
    drawFrame(originX, _scrollOffset, (int)count);
    drawRows(src, originX, count);
    drawTotalTime(src, originX);

    tft.endWrite();
  }

  // Force the next draw() to repaint unconditionally: clears the seqno
  // sentinel AND the rate limit, for callers that have wiped the canvas.
  void invalidate() {
    _lastSeqno   = 0xFFFFFFFF;
    _scrollDirty = true;
    _lastDrawMs  = 0;
  }

  // ── Chrome (public: shared with webRadioApp.h's own renderer until TASK-412) ──

  // Draw the PLEDIT frame chrome — gutters, title bar, side tiles, scrollbar
  // thumb and bottom bar — for a list of `count` rows scrolled to `scroll`.
  // Everything except the rows themselves and any app-specific bottom-bar
  // overlay. Caller owns startWrite()/endWrite().
  void drawFrame(int originX, int scroll, int count) {
    // Gutters outside the 275px chrome window — match the startup fillScreen.
    const int rightEdge = originX + PLEDIT_W;
    if (originX > 0)
      tft.fillRect(0, PLEDIT_Y, originX, PLEDIT_H, TFT_BLACK);
    if (rightEdge < TASKBAR_X)
      tft.fillRect(rightEdge, PLEDIT_Y, TASKBAR_X - rightEdge, PLEDIT_H, TFT_BLACK);

    // Title bar — top PLEDIT_TITLE_H rows of SKIN_PLEDIT_BG atlas.
    tft.pushImage(originX, PLEDIT_Y, SKIN_PLEDIT_BG_W, PLEDIT_TITLE_H, SKIN_PLEDIT_BG);

    // Frame side tiles — always full height (fixed PLEDIT dimensions).
    const int rowsH = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
    for (int sy = PLEDIT_ROWS_Y; sy < PLEDIT_ROWS_Y + rowsH; sy += PLEDIT_SIDE_H_SRC) {
      const int h = min((int)PLEDIT_SIDE_H_SRC, PLEDIT_ROWS_Y + rowsH - sy);
      tft.pushImage(originX,                                       sy, PLEDIT_SIDE_LEFT_W,  h, SKIN_PLEDIT_LEFT_SIDE);
      tft.pushImage(originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W, sy, PLEDIT_SIDE_RIGHT_W, h, SKIN_PLEDIT_RIGHT_SIDE);
    }

    // Scrollbar thumb — sprite blit when the list exceeds the visible rows.
    if (count > PLEDIT_ROW_COUNT) {
      const int denom   = max(1, count - PLEDIT_ROW_COUNT);
      const int thumb_x = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + PLEDIT_THUMB_X_INSET;
      const int thumb_y = PLEDIT_ROWS_Y + scroll * THUMB_TRAVEL / denom;
      tft.pushImage(thumb_x, thumb_y,
                    SKIN_PLEDIT_THUMB_W, SKIN_PLEDIT_THUMB_H,
                    SKIN_PLEDIT_THUMB, PLEDIT_TRANSPARENT_RGB565);
    }

    // Bottom bar — second band of the SKIN_PLEDIT_BG atlas.
    const uint16_t *bottom = SKIN_PLEDIT_BG + (uint32_t)SKIN_PLEDIT_BG_W * PLEDIT_TITLE_H;
    tft.pushImage(originX, PLEDIT_BOTTOM_Y, SKIN_PLEDIT_BG_W, PLEDIT_BOTTOM_H, bottom);
  }

  // TASK-051i: re-tile the right-side strip and blit the thumb at the current
  // offset. Much cheaper than a full draw() — used during a strip drag.
  // Deliberately does NOT bump the repaint counter: it paints the thumb, not
  // the playlist, and T_PLE_04 asserts on playlist repaints.
  void drawScrollThumbOnly(int originX) {
    if (_lastCount <= PLEDIT_ROW_COUNT) return;
    const int rowsH  = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
    const int rightX = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W;
    tft.startWrite();
    for (int sy = PLEDIT_ROWS_Y; sy < PLEDIT_ROWS_Y + rowsH; sy += PLEDIT_SIDE_H_SRC) {
      const int h = min((int)PLEDIT_SIDE_H_SRC, PLEDIT_ROWS_Y + rowsH - sy);
      tft.pushImage(rightX, sy, PLEDIT_SIDE_RIGHT_W, h, SKIN_PLEDIT_RIGHT_SIDE);
    }
    const int denom   = max(1, (int)_lastCount - PLEDIT_ROW_COUNT);
    const int thumb_y = PLEDIT_ROWS_Y + _scrollOffset * THUMB_TRAVEL / denom;
    tft.pushImage(rightX + PLEDIT_THUMB_X_INSET, thumb_y,
                  SKIN_PLEDIT_THUMB_W, SKIN_PLEDIT_THUMB_H,
                  SKIN_PLEDIT_THUMB, PLEDIT_TRANSPARENT_RGB565);
    tft.endWrite();
  }

  // TASK-348: PLEDIT bottom-bar overlay slot — the skin-font glyph blit and
  // position Spotify uses for its total-playlist-time readout (x=127 in the
  // PLEDIT frame, dark LCD area of the bottom bar). WebRadio renders its
  // country code in the identical slot. Caller owns startWrite()/endWrite().
  void drawOverlayText(int originX, const char *str) {
    int tx = originX + 127 + GLYPH_W;
    const int ty = PLEDIT_BOTTOM_Y + 10;
    for (const char *p = str; *p; p++) {
      const SkinUV uv = SKIN_GLYPH[(uint8_t)*p & 0x7F];
      skinBlitSprite(tx, ty, SKIN_FONT, SKIN_FONT_W, uv);
      tx += uv.w;
    }
  }

  // ── Gestures ──────────────────────────────────────────────────────────────

  DragMode dragMode() const { return _drag; }
  bool     dragging() const { return _drag != DRAG_NONE; }

  // Press hit-test. Returns true when a PLEDIT gesture was anchored (the host
  // should treat the touch as consumed). Both zones use hitbox.h rather than
  // open-coded bounds arithmetic.
  bool press(int x, int y, int originX, int originY) {
    if (hitTest(stripRect(originX, originY), x, y)) {
      _drag = DRAG_STRIP;
      updateScrollDirect(y, originX, originY);
      return true;
    }
    const Rect rows = rowsRect(originX, originY);
    if (hitTest(rows, x, y)) {
      if (_drag == DRAG_NONE) {
        _drag                  = DRAG_ROWS;
        _dragStartY            = y;
        _dragCurrentY          = y;
        _dragStartRow          = hitTestRow(rows, PLEDIT_ROW_H, y);
        _dragStartMs           = millis();
        _dragStartScrollOffset = _scrollOffset;
        LOG_D("touch", "PLEDIT drag start: startY=%d row=%d", y, _dragStartRow);
      }
      return true;
    }
    return false;
  }

  // Move while a PLEDIT gesture is captured.
  void move(int y, int originX, int originY) {
    if (_drag == DRAG_STRIP)     updateScrollDirect(y, originX, originY);
    else if (_drag == DRAG_ROWS) _dragCurrentY = y;
  }

  // Release while a PLEDIT gesture is captured. Tap/scroll discrimination is
  // the shipped M-LIST-v4 model: dead zone + elapsed time, with the quick-swipe
  // minimum-one-row fallback.
  PlReleaseResult release(PlaylistSource& src) {
    PlReleaseResult r;
    r.tapDispatched = false;
    r.cooldownMs    = 0;
    if (_drag == DRAG_STRIP) {
      _drag        = DRAG_NONE;
      r.cooldownMs = 100;
      return r;
    }
    if (_drag != DRAG_ROWS) return r;

    const int dy = _dragCurrentY - _dragStartY;
    LOG_D("touch", "PLEDIT drag end: dy=%d startY=%d curY=%d", dy, _dragStartY, _dragCurrentY);
    const unsigned long elapsed = (unsigned long)(millis() - _dragStartMs);
    const bool isTap = abs(dy) < PLEDIT_TAP_PX && elapsed < PLEDIT_TAP_MS;
    _scrollAccum    = 0.0f;
    _scrollVelocity = 0.0f;
    if (isTap) {
      if (_dragStartRow >= 0 && _dragStartRow < _lastVisibleRows) {
        const int playIdx = _scrollOffset + _dragStartRow;
        src.onTap((uint16_t)playIdx);
        _optimisticRow     = playIdx;
        _optimisticUntilMs = millis() + OPTIMISTIC_HOLD_MS;
        _scrollDirty       = true;
        r.tapDispatched    = true;
      }
      r.cooldownMs = 300;
    } else {
      if (elapsed < PLEDIT_TAP_MS) {
        // Quick swipe: tick() accumulated ~0 rows (brief dt); apply a
        // guaranteed delta from the press-time offset so the gesture always
        // registers at least one row.
        const int delta  = max(1, abs(dy) / PLEDIT_ROW_H);
        const int dir    = (dy <= 0) ? 1 : -1;
        const int maxOff = max(0, (int)_lastCount - PLEDIT_ROW_COUNT);
        _scrollOffset = max(0, min(maxOff, _dragStartScrollOffset + dir * delta));
        _scrollDirty  = true;
      }
      // Slow drag (elapsed >= PLEDIT_TAP_MS): the velocity model already
      // applied rows during tick().
      r.cooldownMs = 150;
    }
    _drag = DRAG_NONE;
    return r;
  }

  // Velocity integrator (ADR-030 / M-LIST-v4). Safe to call every loop.
  void tickScroll(float dt) {
    if (_drag != DRAG_ROWS) {
      _scrollAccum    = 0.0f;
      _scrollVelocity = 0.0f;
      return;
    }
    if (dt <= 0.0f || dt > 0.2f) return;

    const int dy = _dragCurrentY - _dragStartY;
    const float effective = max(0.0f, (float)abs(dy) - (float)SCROLL_DEAD_ZONE_PX);
    const float speed = effective * _scrollSpeedK;
    _scrollVelocity = (dy <= 0 ? 1.0f : -1.0f) * speed;

    _scrollAccum += _scrollVelocity * dt;
    const int steps = (int)_scrollAccum;
    if (steps != 0) {
      _scrollAccum -= (float)steps;
      const int maxOffset = max(0, (int)_lastCount - PLEDIT_ROW_COUNT);
      _scrollOffset = max(0, min(maxOffset, _scrollOffset + steps));
      _scrollDirty  = true;
    }
  }

  void resetDrag() { _drag = DRAG_NONE; }

  // ── Observability / host plumbing ─────────────────────────────────────────

  int   scrollOffset()   const { return _scrollOffset; }
  int   visibleRows()    const { return _lastVisibleRows; }
  int   dragStartY()     const { return _dragStartY; }
  float scrollAccum()    const { return _scrollAccum; }
  float scrollVelocity() const { return _scrollVelocity; }
  unsigned long lastDrawMs() const { return _lastDrawMs; }
  void  setSpeedK(float k) { _scrollSpeedK = k; }

  // ADR-059 D12: monotonic count of full PLEDIT repaints since boot. The
  // seqno redraw gate previously had no observable signal at all — "no repaint
  // while seqno is static" was unassertable (VE-2). Counts accepted full
  // repaints only: thumb-only blits during a strip drag do not bump it.
  uint32_t repaints() const { return _repaints; }

  // Row hit zone, populated rows only — an empty slot is not tappable.
  Rect rowsRect(int originX, int originY) const {
    Rect r;
    r.x = (int16_t)(originX + PLEDIT_CONTENT_X);
    r.y = (int16_t)(originY + PLEDIT_ROWS_Y);
    r.w = (int16_t)PLEDIT_CONTENT_W;
    r.h = (int16_t)(_lastVisibleRows * PLEDIT_ROW_H);
    return r;
  }

  // Direct-scroll right strip — full row-band height regardless of row count.
  Rect stripRect(int originX, int originY) const {
    Rect r;
    r.x = (int16_t)(originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W);
    r.y = (int16_t)(originY + PLEDIT_ROWS_Y);
    r.w = (int16_t)(PLEDIT_W - (PLEDIT_CONTENT_X + PLEDIT_CONTENT_W));
    r.h = (int16_t)(PLEDIT_ROW_COUNT * PLEDIT_ROW_H);
    return r;
  }

private:
  // Row text metrics. Font 1 glyph height = 8px; TEXT_VOFF centres it in the
  // 13px row. USABLE is the content width less both margins.
  static const int TEXT_MARGIN = 3;
  static const int TEXT_VOFF   = (PLEDIT_ROW_H - 8) / 2;
  static const int CHAR_W      = 6;   // Font 1 fixed-width glyph (px)
  static const int TEXT_GAP    = 2;   // px gap between the text and the duration
  static const int USABLE      = PLEDIT_CONTENT_W - 2 * TEXT_MARGIN;  // 238 px
  static const int THUMB_TRAVEL = PLEDIT_ROW_COUNT * PLEDIT_ROW_H - SKIN_PLEDIT_THUMB_H;  // 48 px
  static const unsigned long PLAYLIST_DRAW_MIN_MS = 1000;  // 1 Hz cap
  static const unsigned long OPTIMISTIC_HOLD_MS   = 8000;  // TASK-051a

  // Rows: flat fillRect (Audacious playlist-widget.cc) + Font 1 track text.
  void drawRows(PlaylistSource& src, int originX, uint16_t count) {
    tft.setTextFont(1);
    tft.setTextSize(1);
    tft.setTextDatum(TL_DATUM);  // own our text state — don't inherit a datum from another app

    for (int i = 0; i < PLEDIT_ROW_COUNT; i++) {
      const int ry  = PLEDIT_ROWS_Y + i * PLEDIT_ROW_H;
      const int idx = _scrollOffset + i;

      if (idx >= (int)count) {
        // Empty slot — black content area, no text.
        tft.fillRect(originX + PLEDIT_CONTENT_X, ry, PLEDIT_CONTENT_W, PLEDIT_ROW_H, TFT_BLACK);
        continue;
      }

      PlRow pr;
      const bool ok = src.row((uint16_t)idx, pr);
      if (!ok) {
        // Design §2.2: a failed read renders a placeholder and does not abort
        // the repaint. ASCII only — Font 1 has no glyphs beyond it, and the
        // encoding question (design OQ3) is still open.
        strcpy(pr.text, "-- unreadable --");
        pr.durationSec = 0;
        pr.current     = false;
      }

      const bool isOptimistic = (_optimisticRow == idx && millis() < _optimisticUntilMs);
      const uint16_t bg = (pr.current || isOptimistic) ? PLEDIT_BG_SELECTED : PLEDIT_BG_NORMAL;
      const uint16_t fg = (pr.current || isOptimistic) ? PLEDIT_FG_CURRENT  : PLEDIT_FG_NORMAL;
      tft.fillRect(originX + PLEDIT_CONTENT_X, ry, PLEDIT_CONTENT_W, PLEDIT_ROW_H, bg);

      // Right-aligned "M:SS" duration column — drawn for every readable row,
      // including a zero duration ("0:00"), exactly as the pre-extraction code.
      char dur[8];
      dur[0] = '\0';
      int durW = 0;
      if (ok) {
        snprintf(dur, sizeof(dur), "%lu:%02lu",
                 (unsigned long)(pr.durationSec / 60), (unsigned long)(pr.durationSec % 60));
        durW = (int)strlen(dur) * CHAR_W;
      }

      // Ellipsis truncation against the pixel budget left by the duration
      // column (DEV-10). The pre-extraction code truncated the artist-title
      // half against a budget that had the row-number prefix subtracted, then
      // concatenated; because the prefix width is an exact multiple of CHAR_W,
      // truncating the composed string against the un-subtracted budget lands
      // the ellipsis on the identical character. The one place the two forms
      // could differ — a budget under three characters — is unreachable here
      // (USABLE 238 px, duration and prefix at most 42 px each => >= 32 chars).
      textFit(pr.text, USABLE - TEXT_GAP - durW, CHAR_W);

      tft.setTextColor(fg, bg);
      const int textY = ry + TEXT_VOFF;
      tft.drawString(pr.text, originX + PLEDIT_CONTENT_X + TEXT_MARGIN, textY);
      if (dur[0]) {
        const int durX = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W - TEXT_MARGIN - durW;
        tft.drawString(dur, durX, textY);
      }
    }
  }

  // Total playlist time — left-aligned in the scrollbar track (dark LCD area,
  // top row of the right section, x=127 in the PLEDIT frame, y+4 in the bottom
  // bar). Rendered with the skin bitmap font to match the track-name style.
  // Format: "MM:SS" or "H:MM:SS".
  void drawTotalTime(PlaylistSource& src, int originX) {
    const uint32_t totalSec = src.totalSec();
    char tstr[12];
    const uint32_t h = totalSec / 3600;
    const uint32_t m = (totalSec % 3600) / 60;
    const uint32_t s = totalSec % 60;
    if (h > 0)
      snprintf(tstr, sizeof(tstr), "%lu:%02lu:%02lu",
               (unsigned long)h, (unsigned long)m, (unsigned long)s);
    else
      snprintf(tstr, sizeof(tstr), "%lu:%02lu", (unsigned long)m, (unsigned long)s);
    drawOverlayText(originX, tstr);
  }

  // Scrollbar-column positional mapping: finger Y maps straight onto offset.
  void updateScrollDirect(int sy, int originX, int originY) {
    const int py = sy - originY;
    const int maxOffset = max(0, (int)_lastCount - PLEDIT_ROW_COUNT);
    if (maxOffset > 0) {
      const int relY = py - PLEDIT_ROWS_Y;
      const int newOffset = max(0, min(maxOffset, relY * maxOffset / THUMB_TRAVEL));
      if (newOffset != _scrollOffset) {
        _scrollOffset = newOffset;
        _scrollDirty  = true;
        drawScrollThumbOnly(originX);
      }
    }
  }

  // Redraw gate
  uint32_t      _lastSeqno       = 0xFFFFFFFF;  // force first draw
  unsigned long _lastDrawMs      = 0;
  bool          _scrollDirty     = false;
  uint32_t      _repaints        = 0;
  int           _lastVisibleRows = PLEDIT_ROW_COUNT;
  uint8_t       _lastCount       = 0;   // count cached at draw time — the gesture clamp

  // Scroll + gesture
  int           _scrollOffset          = 0;
  DragMode      _drag                  = DRAG_NONE;
  int           _dragStartY            = 0;
  int           _dragCurrentY          = 0;
  int           _dragStartRow          = 0;
  unsigned long _dragStartMs           = 0;
  int           _dragStartScrollOffset = 0;
  float         _scrollVelocity        = 0.0f;
  float         _scrollAccum           = 0.0f;
  float         _scrollSpeedK          = SCROLL_SPEED_K_DEFAULT;

  // TASK-051a optimistic tap highlight — a renderer concern (it exists to make
  // the tap feel instant), so it lives here rather than in the source.
  int           _optimisticRow     = -1;
  unsigned long _optimisticUntilMs = 0;
};
