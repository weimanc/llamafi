#pragma once
// M3 — Winamp 2 main-window renderer for the CYD2USB.
// Subclasses CheapYellowDisplay; the JPEG/SPIFFS/album-art plumbing is
// compiled out under WINAMP_DISPLAY (M-NOART). Overrides the chrome
// (background, transport buttons, title text, progress bar, status indicator)
// to draw from the baked skin atlas.

#include "cheapYellowLCD.h"
#include "gen/skin_layout.h"
#include "gen/shell_layout.h"
#include "spotifyTask.h"
#include "vuMeter.h"
#include "touchPhase.h"

extern const uint16_t SKIN_MAIN_BG[];
extern const uint16_t SKIN_CBUTTONS[];
extern const uint16_t SKIN_FONT[];
extern const SkinUV SKIN_GLYPH[128];
extern const uint16_t SKIN_NUMBERS[];
extern const uint16_t SKIN_POSBAR[];
extern const uint16_t SKIN_PLAYPAUS[];
extern const uint16_t SKIN_VOLUME[];
extern const uint16_t SKIN_VOLUME_KNOB[];
extern const uint16_t SKIN_SHUFREP[];
extern const uint16_t SKIN_TITLEBAR_INACTIVE[];
extern const uint16_t SKIN_PLEDIT_TITLE_INACTIVE[];

// Track duration + interpolation anchor from spotifyLogic. WinampDisplay
// updates songStartMillis on touch (optimistic UI) so the seek bar and
// time digits stop / jump immediately, before the next poll round trip.
extern long     songDuration;
extern long     songStartMillis;
extern uint32_t g_lastRenderMs;  // TASK-059

// ADR-023 / TASK-060: staleness threshold + amber drift pip.
// 3 × base poll cadence (5 s) = 15 s — three missed polls signals genuine drift.
static constexpr uint32_t N_STALE_MS = 15000;
// 4×4 amber pip (RGB565 0xFD00 ≈ orange-yellow). Baked inline — 32 bytes, no atlas change.
static constexpr uint16_t kDriftPip[4 * 4] = {
  0xFD00, 0xFD00, 0xFD00, 0xFD00,
  0xFD00, 0xFD00, 0xFD00, 0xFD00,
  0xFD00, 0xFD00, 0xFD00, 0xFD00,
  0xFD00, 0xFD00, 0xFD00, 0xFD00,
};

class WinampDisplay : public CheapYellowDisplay {
public:
  void displaySetup(SpotifyArduino *spotifyObj) override {
    CheapYellowDisplay::displaySetup(spotifyObj);
    tft.setSwapBytes(true);  // RGB565 LE in gen/ — pushImage expects byte-swap on
    originX = 0;
    originY = 0;
    Serial.println("winamp display setup");
  }

  int chromeOriginX() const { return originX; }
  int chromeOriginY() const { return originY; }

  // Taskbar gesture API (M-TASKBAR-SCROLL) — called from appHandleInput().
  int  tbScrollOffset() const { return _tbScrollOffset; }
  bool tbIsDragging()   const { return dragState == D_TASKBAR_SCROLL; }

  void tbGesturePress(int y) {
    _tbDragStartY  = y;
    _tbDragBaseOff = _tbScrollOffset;
    _tbScrollAccum = 0.0f;
    _tbIsScrolling = false;
    dragState      = D_TASKBAR_SCROLL;
  }

  // 1:1 positional scroll with LP filter. Returns true when offset changed.
  // Finger UP (negative dy) = higher-index apps scroll into view.
  bool tbGestureContinue(int y, int totalApps) {
    const int rawDy = y - _tbDragStartY;
    // Exponential moving average — smooths digitizer jitter, preserves 1:1 feel.
    _tbScrollAccum += ((float)rawDy - _tbScrollAccum) * TB_LP_ALPHA;
    // Dead zone: don't scroll until clearly past tap threshold.
    if (!_tbIsScrolling && abs(rawDy) < TB_SCROLL_DEAD_ZONE_PX) return false;
    _tbIsScrolling = true;
    // 1:1: negate because finger-up (negative dy) should increase offset.
    const int steps     = (int)(-_tbScrollAccum / TASKBAR_SLOT_H);
    const int newOffset = ((_tbDragBaseOff + steps) % totalApps + totalApps) % totalApps;
    if (newOffset != _tbScrollOffset) {
      _tbScrollOffset = newOffset;
      return true;
    }
    return false;
  }

  // Returns true if gesture was a tap; fills *outAppIdx. Resets drag state.
  bool tbGestureEnd(int y, int totalApps, int* outAppIdx) {
    const bool isTap = !_tbIsScrolling;
    _tbScrollAccum = 0.0f;
    _tbIsScrolling = false;
    dragState      = D_IDLE;
    if (isTap && outAppIdx) {
      *outAppIdx = (_tbScrollOffset + y / TASKBAR_SLOT_H) % totalApps;
      return true;
    }
    return false;
  }

  void showDefaultScreen() override {
    tft.fillScreen(TFT_BLACK);
    lastThumbPx = -1;
    lastTitle[0] = '\0';
    titleScrollOffset = 0;
    titleScrollDeadline = 0;
    lastSeconds = -1;
    currentStatusUv = PP_STOP;
    repaintChrome();
  }

  // Force-paint all chrome elements over whatever's currently underneath
  // (e.g. a screenLog full-screen text layer). Does NOT reset state — use
  // showDefaultScreen for that. Idempotent given the cached state.
  void repaintChrome() {
    // TASK-038: bracket the whole composite repaint with one TFT_eSPI
    // transaction. CS stays asserted across all the inner pushImage
    // calls — eliminates per-call CS toggle + addr-window setup
    // overhead. Inner blits' own auto-transaction code is a no-op
    // when one is already active.
    tft.startWrite();
    blitMainBackground();
    // TASK-053c: overlay inactive title bar when connection is unhealthy.
    if (!spotifyTask::isHealthy()) {
      tft.pushImage(originX, originY, SKIN_TITLEBAR_INACTIVE_W, SKIN_TITLEBAR_INACTIVE_H,
                    SKIN_TITLEBAR_INACTIVE);
    }
    // ADR-023 / TASK-060: amber 4×4 pip when poll age exceeds N_STALE_MS.
    // Layered after conn-001 so both indicators show simultaneously.
    if (spotifyTask::lastSuccessfulPollAgeMs() > N_STALE_MS) {
      tft.pushImage(originX + 268, originY + 1, 4, 4, kDriftPip);
    }
    drawTransportButtons(/*pressedIndex*/ -1);
    drawEjectButton(/*pressed*/ false);
    drawStatusIndicator(currentStatusUv);
    blitSprite(originX + POSBAR_X, originY + POSBAR_Y, SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_BG);
    if (lastThumbPx >= 0) {
      blitSprite(originX + POSBAR_X + lastThumbPx, originY + POSBAR_Y,
                 SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N);
    }
    drawTimeDigits(lastSeconds < 0 ? 0 : lastSeconds, /*force*/ true);
    if (lastTitle[0] != '\0') drawTitleText(titleScrollOffset);
    // ADR-014: kbps / kHz / mono-stereo / titlebar / balance are now
    // baked into MAIN_BG at host time — no runtime renderer needed.
    tft.endWrite();
    // TASK-041 / A1.1: restore VOLUME slider after blitMainBackground
    // overwrote it. -2 (never rendered) → draw sentinel until first
    // poll fills the cache.
    drawVolume(lastVolumeRendered == -2 ? -1 : (int)lastVolumeRendered);
    // chrome-001 final: paint the cached shuffle + repeat. Sentinel
    // values render the OFF sprite (off is the safe default both
    // visually and semantically when there's no snapshot yet).
    drawShuffle(lastShuffleRendered == 1 ? 1 : 0);
    drawRepeat (lastRepeatRendered  >= 0 && lastRepeatRendered <= 2
                ? (int)lastRepeatRendered : 2);
    // VU rect lives inside the area we just blitted from MAIN.BMP, so
    // any cached pixel-widths are stale. Force the next vu::tick to
    // repaint from scratch.
    vu::invalidate();
    g_lastRenderMs = millis();  // TASK-059: mark full chrome repaint time
  }

  // TASK-253 — WebRadio buffer-fullness bar. Reuses the POSBAR exactly as Spotify
  // uses its seek bar: the groove sprite plus the POSBAR thumb, whose POSITION marks
  // buffer fullness (left = empty, right = full) — pct 0..100 mapped over the same
  // travel the seek bar uses. WebRadio-only; the renderer owns SKIN_POSBAR so it
  // restores the groove here. Mirrors app/tools/preview_webradio.py::_draw_buffer_bar.
  void drawBufferBar(uint8_t pct) {
    if (pct > 100) pct = 100;
    const int travel  = POSBAR_BG.w - POSBAR_THUMB_N.w;   // same as the seek bar
    const int thumbPx = (int)pct * travel / 100;
    tft.startWrite();
    blitSprite(originX + POSBAR_X, originY + POSBAR_Y, SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_BG);
    blitSprite(originX + POSBAR_X + thumbPx, originY + POSBAR_Y,
               SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N);
    tft.endWrite();
  }

  // TASK-252 — set the marquee title (shared: Spotify track + WebRadio station/
  // state). Redraws only on change; resets scroll + holds before scrolling. The
  // baked SKIN_GLYPH folds lowercase→uppercase, so callers needn't uppercase.
  void setTitle(const char* text) {
    if (strcmp(lastTitle, text) == 0) return;
    strncpy(lastTitle, text, sizeof(lastTitle) - 1);
    lastTitle[sizeof(lastTitle) - 1] = '\0';
    titleScrollOffset   = 0;
    titleScrollDeadline = millis() + TITLE_SCROLL_HOLD_MS;
    drawTitleText(0);
  }

  // TASK-252 — drive the title marquee scroll (WebRadio calls from its tick();
  // Spotify drives it internally via _tickMarquee in its own tick/input paths).
  void tickMarquee() { _tickMarquee(); }

  // TASK-041 / ADR-014 A1.5 — VOLUME slider renderer.
  // percent: 0..100 → KEYFRAME_0..KEYFRAME_4; <0 → KEYFRAME_NONE.
  // Always blits + updates the cache; caller dedup not required (the
  // updateCurrentlyPlaying integration in spotifyLogic.h still gates
  // on getLastVolumeRendered() to avoid the SPI traffic).
  void drawVolume(int percent) override {
    int clamped = (percent < 0) ? -1 : (percent > 100 ? 100 : percent);
    SkinUV uv = pickKeyframe(clamped);
    tft.startWrite();
    blitSprite(originX + VOLUME_X, originY + VOLUME_Y,
               SKIN_VOLUME, SKIN_VOLUME_W, uv);
    // ADR-016 §3-§4 — knob blit on top of the keyframe. Skipped on
    // sentinel (clamped < 0) to avoid implying a real position when
    // there's no active device.
    if (clamped >= 0) {
      const int knobTravel = VOLUME_W - VOLUME_KNOB_W;  // 54 px
      const int knobX = originX + VOLUME_X + (clamped * knobTravel) / 100;
      const int knobY = originY + VOLUME_Y + (VOLUME_H - VOLUME_KNOB_H) / 2;
      const SkinUV knobUv = { 0, 0, VOLUME_KNOB_W, VOLUME_KNOB_H };
      blitSprite(knobX, knobY, SKIN_VOLUME_KNOB, VOLUME_KNOB_W, knobUv);
    }
    tft.endWrite();
    lastVolumeRendered = (int8_t)clamped;
    Serial.printf("[D][chrome] drawVolume pct=%d keyframe=%s\n",
                  clamped, keyframeName(clamped));
  }

  int8_t getLastVolumeRendered() const override { return lastVolumeRendered; }

  // TASK-045 / ADR-016 §10 — millis() deadline beyond which drag
  // optimism expires. spotifyLogic checks `now < this` to skip the
  // snap-driven dedup gate during/after a drag.
  unsigned long getOptimisticVolumeUntil() const override { return optimisticVolumeUntilMs; }

  void drawShuffle(int on) override {
    SkinUV uv;
    if (on) { uv = SR_SHUFFLE_ON; }
    else    { uv = SR_SHUFFLE_OFF; }
    tft.startWrite();
    blitSprite(originX + SHUFFLE_X, originY + SHUFFLE_Y,
               SKIN_SHUFREP, SKIN_SHUFREP_W, uv);
    tft.endWrite();
    lastShuffleRendered = on ? 1 : 0;
  }
  void drawRepeat(int state) override {
    // Spotify states (RepeatOptions enum): 0=track, 1=context, 2=off.
    // Winamp 2 only has off/on visuals — both 0 and 1 paint the ON sprite.
    int s = (state < 0 || state > 2) ? 2 : state;
    SkinUV uv;
    if (s != 2) { uv = SR_REPEAT_ON; }
    else        { uv = SR_REPEAT_OFF; }
    tft.startWrite();
    blitSprite(originX + REPEAT_X, originY + REPEAT_Y,
               SKIN_SHUFREP, SKIN_SHUFREP_W, uv);
    tft.endWrite();
    lastRepeatRendered = (int8_t)s;
  }
  int8_t getLastShuffleRendered() const override { return lastShuffleRendered; }
  int8_t getLastRepeatRendered()  const override { return lastRepeatRendered;  }
  unsigned long getOptimisticShufRepUntil() const override { return optimisticShufRepUntilMs; }

  void displayTrackProgress(long progress, long duration) override {
    if (duration <= 0) return;
    // Thumb travels along the posbar background; subtract thumb width.
    const int travel = POSBAR_BG.w - POSBAR_THUMB_N.w;
    int thumbPx = map((int)((progress * 100) / duration), 0, 100, 0, travel);
    if (thumbPx != lastThumbPx) {
      int slotX = originX + POSBAR_X;
      int slotY = originY + POSBAR_Y;
      if (lastThumbPx >= 0) {
        SkinUV under = { (int16_t)lastThumbPx, 0, POSBAR_THUMB_N.w, POSBAR_BG.h };
        blitSprite(slotX + lastThumbPx, slotY, SKIN_POSBAR, SKIN_POSBAR_W, under);
      }
      blitSprite(slotX + thumbPx, slotY, SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N);
      lastThumbPx = thumbPx;
    }
    drawTimeDigits((int)(progress / 1000));
  }

  void printCurrentlyPlayingToScreen(CurrentlyPlaying currentlyPlaying) override {
    // TASK-048: compose "Artist - Title   " (3-space scroll gap); fall back
    // to "Title   " when artist blank. Detect change on either field.
    char composed[sizeof(lastTitle)];
    const char *artist = (currentlyPlaying.numArtists > 0 && currentlyPlaying.artists[0].artistName)
                         ? currentlyPlaying.artists[0].artistName : "";
    const char *title  = currentlyPlaying.trackName ? currentlyPlaying.trackName : "";
    if (artist[0]) {
      snprintf(composed, sizeof(composed), "%s - %s   ", artist, title);
    } else {
      snprintf(composed, sizeof(composed), "%s   ", title);
    }
    setTitle(composed);  // TASK-252: shared title primitive (redraw-on-change + scroll)
    currentStatusUv = PP_PLAY;
    drawStatusIndicator(currentStatusUv);
  }

  void checkForInput() override {
    // Retired — shell calls handleWinampInput() directly via SpotifyApp::handleInput().
    // Kept as a no-op override so the vtable slot isn't removed while
    // SpotifyDisplay* callers (WiFiManager flow) still compile.
  }

  // Shell-driven hit-test entry point. Called by SpotifyApp::handleInput().
  // phase/x/y pre-classified by the shell gesture tracker.
  // Returns true if Press was consumed (shell applies inter-gesture cooldown).
  bool handleWinampInput(TouchPhase phase, int x, int y) {
    // Deferred press-release: fires on Release, or on Move/Press timer.
    if (phase == TouchPhase::Release) {
      if (pendingReleaseAt != 0) {
        drawTransportButtons(-1);
        pendingReleaseAt = 0;
      }
      // Drag-end handling on Release.
      if (dragState == D_PLEDIT_SCROLL_DIRECT) {
        dragState = D_IDLE;
        touchScreenCoolDownTime = millis() + 100;
      }
      if (dragState == D_PLEDIT_SCROLL) {
        const int dy = _dragCurrentY - _dragStartY;
        LOG_D("touch", "PLEDIT drag end: dy=%d startY=%d curY=%d", dy, _dragStartY, _dragCurrentY);
        const unsigned long elapsed = (unsigned long)(millis() - _dragStartMs);
        const bool isTap = abs(dy) < PLEDIT_TAP_PX && elapsed < PLEDIT_TAP_MS;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
        if (isTap) {
          if (_dragStartRow >= 0 && _dragStartRow < lastVisibleRows) {
            const int playIdx = scrollOffset + _dragStartRow;
            spotifyTask::enqueue(spotifyTask::ACT_PLAY_URI, (int32_t)playIdx);
            _lastInputWasAsync        = true;
            _skipPending              = true;
            optimisticSelectedRow     = playIdx;
            optimisticSelectedUntilMs = millis() + 8000;
            _pleditScrollDirty = true;
          }
          touchScreenCoolDownTime = millis() + 300;
        } else {
          if (elapsed < PLEDIT_TAP_MS) {
            // Quick swipe: tickScroll accumulated ~0 rows (brief dt); apply guaranteed delta
            // from start offset so the gesture always registers at least 1 row.
            const int delta  = max(1, abs(dy) / PLEDIT_ROW_H);
            const int dir    = (dy <= 0) ? 1 : -1;
            const int maxOff = max(0, (int)lastCount - PLEDIT_ROW_COUNT);
            scrollOffset       = max(0, min(maxOff, _dragStartScrollOffset + dir * delta));
            _pleditScrollDirty = true;
          }
          // Slow drag (elapsed >= PLEDIT_TAP_MS): velocity model already applied rows.
          touchScreenCoolDownTime = millis() + 150;
        }
        dragState = D_IDLE;
      }
      if (dragState == D_POSBAR_DRAG) {
        spotifyTask::enqueue(spotifyTask::ACT_SEEK, (int32_t)_posbarDragCurrentMs);
        _lastInputWasAsync = true;
        songStartMillis = millis() - _posbarDragCurrentMs;
        touchScreenCoolDownTime = millis() + 200;
        dragState = D_IDLE;
      }
      if (dragState == D_VOLUME_DRAG) {
        if (lastVolumeRendered >= 0 && lastVolumeRendered != lastVolumeEnqueuedPct) {
          spotifyTask::enqueue(spotifyTask::ACT_VOLUME, (int32_t)lastVolumeRendered);
          _lastInputWasAsync = true;
          lastVolumeEnqueuedPct = lastVolumeRendered;
          Serial.printf("[D][chrome] drag-end commit pct=%d\n", (int)lastVolumeRendered);
        }
        dragState = D_IDLE;
      }
      // Marquee tick on Release too (runs below for Move/Press).
      _tickMarquee();
      return false;
    }

    // Press or Move.
    // Phase 1 — captured gesture: route directly to owning handler, no hit-test.
    if (dragState != D_IDLE) {
      switch (dragState) {
        case D_VOLUME_DRAG: {
          long pct = volumeFromX(x);
          drawVolume((int)pct);
          unsigned long now = millis();
          if (now - lastVolumeEnqueuedMs > VOLUME_DRAG_DEBOUNCE_MS &&
              (int8_t)pct != lastVolumeEnqueuedPct) {
            spotifyTask::enqueue(spotifyTask::ACT_VOLUME, (int32_t)pct);
            LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", pct);
            lastVolumeEnqueuedMs = now;
            lastVolumeEnqueuedPct = (int8_t)pct;
          }
          optimisticVolumeUntilMs = now + VOLUME_OPTIMISTIC_HOLD_MS;
          break;
        }
        case D_POSBAR_DRAG:
          _posbarDragCurrentMs = posbarFromX(x);
          updateSeekThumb(_posbarDragCurrentMs);
          songStartMillis = millis() - _posbarDragCurrentMs;
          break;
        case D_PLEDIT_SCROLL_DIRECT:
          updateScrollDirect(y);
          break;
        case D_PLEDIT_SCROLL:
          _dragCurrentY = y;
          break;
        default: break;
      }
      _tickMarquee();
      return true;
    }

    // Phase 2 — D_IDLE only: run hit-tests to start a new gesture.
    if (millis() <= touchScreenCoolDownTime) { _tickMarquee(); return false; }
    int  pressed    = hitTestTransport(x, y);
    long seekMs     = hitTestPosbar(x, y);
    long volPct     = hitTestVolume(x, y);
    int  hitShuffle = hitTestShuffle(x, y);
    int  hitRepeat  = hitTestRepeat (x, y);
    bool hitVis     = hitTestVis(x, y);

    bool consumed = false;

    if (pressed >= 0) {
      drawTransportButtons(pressed);
      switch (pressed) {
        case 0: spotifyTask::enqueue(spotifyTask::ACT_PREV);  break;
        case 1: spotifyTask::enqueue(spotifyTask::ACT_PLAY);  break;
        case 2: spotifyTask::enqueue(spotifyTask::ACT_PAUSE); break;
        case 3: spotifyTask::enqueue(spotifyTask::ACT_PAUSE); break;
        case 4: spotifyTask::enqueue(spotifyTask::ACT_NEXT); _skipPending = true; break;
      }
      if (pressed == 0 || pressed == 2 || pressed == 3 || pressed == 4) {
        songStartMillis = 0;
      }
      _lastInputWasAsync = true;
      pendingReleaseAt = millis() + PRESS_HOLD_MS;
      touchScreenCoolDownTime = millis() + 200;
      consumed = true;
    } else if (seekMs >= 0) {
      dragState = D_POSBAR_DRAG;
      _posbarDragCurrentMs = posbarFromX(x);
      updateSeekThumb(_posbarDragCurrentMs);
      songStartMillis = millis() - _posbarDragCurrentMs;
      consumed = true;
    } else if (hitShuffle) {
      int next = (lastShuffleRendered == 1) ? 0 : 1;
      drawShuffle(next);
      spotifyTask::enqueue(spotifyTask::ACT_SHUFFLE, (int32_t)next);
      _lastInputWasAsync = true;
      optimisticShufRepUntilMs = millis() + SHUFREP_OPTIMISTIC_HOLD_MS;
      touchScreenCoolDownTime = millis() + 250;
      consumed = true;
    } else if (hitRepeat) {
      int cur = lastRepeatRendered;
      int next;
      if (cur == 2)      next = 1;
      else if (cur == 1) next = 0;
      else               next = 2;
      drawRepeat(next);
      spotifyTask::enqueue(spotifyTask::ACT_REPEAT, (int32_t)next);
      _lastInputWasAsync = true;
      optimisticShufRepUntilMs = millis() + SHUFREP_OPTIMISTIC_HOLD_MS;
      touchScreenCoolDownTime = millis() + 250;
      consumed = true;
    } else if (hitVis) {
      vu::nextMode();
      touchScreenCoolDownTime = millis() + 300;
      consumed = true;
    } else if (volPct >= 0) {
      dragState = D_VOLUME_DRAG;
      drawVolume((int)volPct);
      unsigned long now = millis();
      if (now - lastVolumeEnqueuedMs > VOLUME_DRAG_DEBOUNCE_MS &&
          (int8_t)volPct != lastVolumeEnqueuedPct) {
        spotifyTask::enqueue(spotifyTask::ACT_VOLUME, (int32_t)volPct);
        LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", volPct);
        lastVolumeEnqueuedMs = now;
        lastVolumeEnqueuedPct = (int8_t)volPct;
      }
      optimisticVolumeUntilMs = now + VOLUME_OPTIMISTIC_HOLD_MS;
      consumed = true;
    } else {
      int py = y - originY;
      const int pleditRowsAll = PLEDIT_ROWS_Y + PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
      if (py >= PLEDIT_ROWS_Y && py < pleditRowsAll &&
          x >= originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W && x < originX + PLEDIT_W) {
        dragState = D_PLEDIT_SCROLL_DIRECT;
        updateScrollDirect(y);
        consumed = true;
      } else if (py >= PLEDIT_ROWS_Y && py < PLEDIT_ROWS_Y + lastVisibleRows * PLEDIT_ROW_H &&
                 x >= originX + PLEDIT_CONTENT_X && x < originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W) {
        const int row = (py - PLEDIT_ROWS_Y) / PLEDIT_ROW_H;
        if (dragState == D_IDLE) {
          dragState              = D_PLEDIT_SCROLL;
          _dragStartY            = y;
          _dragCurrentY          = y;
          _dragStartRow          = row;
          _dragStartMs           = millis();
          _dragStartScrollOffset = scrollOffset;
          LOG_D("touch", "PLEDIT drag start: startY=%d row=%d", y, row);
        }
        consumed = true;
      } else if (dragState == D_IDLE) {
        if (hitTestLogo(x, y) && millis() >= logoTapCooldownMs) {
          spotifyTask::resetTls();
          spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
          _lastInputWasAsync = true;
          logoTapCooldownMs = millis() + LOGO_TAP_COOLDOWN_MS;
          repaintChrome();
          LOG_I("touch", "logo tap → TLS reset + force poll");
          consumed = true;
        } else if (millis() >= deadZoneForcePollAt) {
          spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
          deadZoneForcePollAt = millis() + DEAD_ZONE_FORCE_POLL_COOLDOWN_MS;
          LOG_D("touch", "dead zone tap → force poll");
          consumed = true;
        }
      }
    }

    _tickMarquee();
    return consumed;
  }

  bool wasLastInputAsync() { bool v = _lastInputWasAsync; _lastInputWasAsync = false; return v; }

  void resetDragState() {
    dragState = D_IDLE;
    pendingReleaseAt = 0;
#ifdef SERIAL_DEBUG
    _injectingDrag = false;
#endif
  }

  void invalidatePlaylist() {
    lastQueueSeqno = 0xFFFFFFFF;
    _pleditScrollDirty = true;
    lastPlaylistDrawMs = 0;  // bypass 1-Hz rate limit — caller wiped the canvas
  }

  void tickScroll(float dt) {
    if (dragState != D_PLEDIT_SCROLL) {
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
      const int maxOffset = max(0, (int)lastCount - PLEDIT_ROW_COUNT);
      scrollOffset = max(0, min(maxOffset, scrollOffset + steps));
      _pleditScrollDirty = true;
    }
  }

#ifdef SERIAL_DEBUG
  // TASK-056d: public under SERIAL_DEBUG so cmdTap/cmdDrag in .ino can
  // read lastTouchResult and set _injectingDrag without a cast to private.
  // Suppress premature drag-end: _injectingDrag blocks the !ts.touched()
  // branch in checkForInput() during multi-step synthetic injection.
  bool _injectingDrag = false;
  struct TouchResult {
    const char *region;          // "TRANSPORT","POSBAR","VOLUME","SHUFFLE","REPEAT","VIS","LOGO","EJECT","DEADZONE","NONE"
    int         transportPressed; // 0-4 for TRANSPORT; -1 otherwise
    const char *action;          // "PREV","PLAY","PAUSE","STOP","NEXT","SEEK","VOLUME","SHUFFLE","REPEAT","VIS","TLS_RESET","FORCE_POLL","EJECT","NONE"
    long        seekMs;          // for POSBAR hits; 0 otherwise
    long        volumePct;       // for VOLUME hits; -1 otherwise
    bool        skipped;         // true when cooldown gate blocked this tap
  } lastTouchResult = { "NONE", -1, "NONE", 0, -1, false };
#endif

private:
  // Touch cool-down inherited via CheapYellowDisplay isn't accessible
  // (private), so WinampDisplay tracks its own.
  unsigned long touchScreenCoolDownTime = 0;
  static constexpr unsigned long TITLE_SCROLL_HOLD_MS = 1500;
  static constexpr unsigned long TITLE_SCROLL_STEP_MS = 120;

  // TASK-034: deferred press-release deadline. 0 == no pending release.
  unsigned long pendingReleaseAt = 0;
  static constexpr unsigned long PRESS_HOLD_MS = 80;


  int originX = 0, originY = 0;
  bool lastHealthy = true;
  uint32_t lastQueueSeqno = 0xFFFFFFFF;  // force first draw
  unsigned long lastPlaylistDrawMs = 0;
  int lastVisibleRows = PLEDIT_ROW_COUNT;
  uint8_t lastCount = 0;            // cached qs.count for scroll clamp in touch handler
  static constexpr unsigned long PLAYLIST_DRAW_MIN_MS = 1000;  // 1 Hz cap
  int lastThumbPx = -1;
  int lastSeconds = -1;
  // TASK-041 / A1.1 cache. -2 = never rendered (next repaint paints
  // sentinel); -1 = sentinel (no active device); 0..100 = real volume.
  int8_t lastVolumeRendered = -2;
  static constexpr int DIGIT_Y = 26;
  char lastTitle[264] = {0};  // artist(128) + " - "(3) + title(128) + gap(3) + NUL
  int scrollOffset = 0;       // TASK-051c will drive; 0 = thumb at top
  int titleScrollOffset = 0;
  unsigned long titleScrollDeadline = 0;
  // Status indicator state survives a full repaint (TASK-018a). Set in
  // showDefaultScreen (PP_STOP) and printCurrentlyPlayingToScreen (PP_PLAY).
  SkinUV currentStatusUv = PP_STOP;

  // TASK-045 / ADR-016 §5-§10 — drag state machine for the volume slider.
  // dragState transitions: D_IDLE → D_VOLUME_DRAG on first touch inside
  // the volume slot; D_VOLUME_DRAG → D_IDLE on the loop iteration where
  // ts.touched() is false. lastVolumeEnqueuedMs/Pct debounce ACT_VOLUME
  // queue traffic to ~3/s. optimisticVolumeUntilMs gates spotifyLogic's
  // dedup against stale snapshot reads during/after drag.
  enum DragState { D_IDLE = 0, D_VOLUME_DRAG, D_POSBAR_DRAG, D_PLEDIT_SCROLL, D_PLEDIT_SCROLL_DIRECT, D_TASKBAR_SCROLL };
  DragState dragState = D_IDLE;
  int _dragStartY = 0;    // screen Y at start of D_PLEDIT_SCROLL
  int _dragCurrentY = 0;  // most recent screen Y during D_PLEDIT_SCROLL
  int _dragStartRow = 0;  // row index at drag-start (tap fallback)
  unsigned long _dragStartMs           = 0;   // millis() at D_PLEDIT_SCROLL press
  int           _dragStartScrollOffset = 0;   // scrollOffset at D_PLEDIT_SCROLL press
  long _posbarDragCurrentMs = 0;
  float _scrollVelocity = 0.0f;
  float _scrollAccum    = 0.0f;
  float _scrollSpeedK   = SCROLL_SPEED_K_DEFAULT;
  static constexpr int          SCROLL_DEAD_ZONE_PX    = 1;
  static constexpr float        SCROLL_SPEED_K_DEFAULT = 0.1667f;  // linear: 2 rows/s at 1-row travel
  static constexpr int          PLEDIT_TAP_PX           = 6;       // < PLEDIT_ROW_H/2; distance threshold for tap
  static constexpr unsigned long PLEDIT_TAP_MS          = 250;     // gesture duration threshold (ms)
  bool _pleditScrollDirty = false;  // force drawScrollThumbOnly bypass of rate-limit
  // Taskbar scroll (M-TASKBAR-SCROLL, TASK-105b)
  int   _tbScrollOffset = 0;
  int   _tbDragStartY   = 0;
  int   _tbDragBaseOff  = 0;    // offset captured at press; positional 1:1 anchor
  float _tbScrollAccum  = 0.0f; // LP-filtered pixel displacement from _tbDragStartY
  bool  _tbIsScrolling  = false; // set once dead zone is exceeded; blocks tap-on-release
  static constexpr int   TB_SCROLL_DEAD_ZONE_PX = 3;
  static constexpr float TB_LP_ALPHA             = 0.4f;
  int optimisticSelectedRow = -1;   // TASK-051a: row playing, highlighted until seqno advances
  unsigned long optimisticSelectedUntilMs = 0;
  uint16_t _songsSeen = 0;          // TASK-051h: natural track advances since boot
  char _prevNextUri[64] = {};       // URI of items[1] from last poll (2-entry history)
  bool _skipPending = false;        // suppresses songsSeen++ on intentional skip
  unsigned long lastVolumeEnqueuedMs = 0;
  int8_t lastVolumeEnqueuedPct = -2;
  unsigned long optimisticVolumeUntilMs = 0;
  static constexpr unsigned long VOLUME_DRAG_DEBOUNCE_MS = 300;
  static constexpr unsigned long VOLUME_OPTIMISTIC_HOLD_MS = 2000;

  // chrome-001 final — shuffle / repeat indicator cache + optimistic
  // freeze. -1 / 3 = "never rendered" sentinels.
  int8_t        lastShuffleRendered = -1;
  int8_t        lastRepeatRendered  =  3;
  unsigned long optimisticShufRepUntilMs = 0;
  static constexpr unsigned long SHUFREP_OPTIMISTIC_HOLD_MS = 2000;

  // TASK-052: dead-zone tap → force-poll cooldown. Active-zone taps don't
  // need a cooldown — their enqueued action already wakes the task.
  unsigned long deadZoneForcePollAt = 0;
  static constexpr unsigned long DEAD_ZONE_FORCE_POLL_COOLDOWN_MS = 1000;

  // TASK-053f: logo tap → TLS reset cooldown (2 s). Prevents rapid re-trigger.
  unsigned long logoTapCooldownMs = 0;
  static constexpr unsigned long LOGO_TAP_COOLDOWN_MS = 2000;

  bool _lastInputWasAsync = false;

  long volumeFromX(int sx) const {
    const int x0 = originX + VOLUME_X;
    const int cx = max(x0, min(x0 + VOLUME_W - 1, sx));
    return ((long)(cx - x0) * 100) / (VOLUME_W - 1);
  }

  long posbarFromX(int sx) const {
    if (songDuration <= 0) return 0;
    const int x0 = originX + POSBAR_X;
    const int cx = max(x0, min(x0 + (int)POSBAR_BG.w - 1, sx));
    return ((long)(cx - x0) * songDuration) / POSBAR_BG.w;
  }

  void updateSeekThumb(long ms) {
    if (songDuration <= 0) return;
    const int travel = POSBAR_BG.w - POSBAR_THUMB_N.w;
    long progressForPaint = ms > songDuration ? songDuration : ms;
    int thumbPx = map((int)((progressForPaint * 100) / songDuration), 0, 100, 0, travel);
    if (thumbPx != lastThumbPx) {
      int slotX = originX + POSBAR_X;
      int slotY = originY + POSBAR_Y;
      if (lastThumbPx >= 0) {
        SkinUV under = { (int16_t)lastThumbPx, 0, POSBAR_THUMB_N.w, POSBAR_BG.h };
        blitSprite(slotX + lastThumbPx, slotY, SKIN_POSBAR, SKIN_POSBAR_W, under);
      }
      blitSprite(slotX + thumbPx, slotY, SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N);
      lastThumbPx = thumbPx;
    }
  }

  void updateScrollDirect(int sy) {
    const int py = sy - originY;
    const int maxOffset = max(0, (int)lastCount - PLEDIT_ROW_COUNT);
    if (maxOffset > 0) {
      constexpr int track_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
      constexpr int travel  = track_h - SKIN_PLEDIT_THUMB_H;
      const int relY = py - PLEDIT_ROWS_Y;
      const int newOffset = max(0, min(maxOffset, relY * maxOffset / travel));
      if (newOffset != scrollOffset) {
        scrollOffset = newOffset;
        _pleditScrollDirty = true;
        drawScrollThumbOnly();
      }
    }
  }

  void _tickMarquee() {
    if (titleScrollDeadline && millis() >= titleScrollDeadline) {
      drawTitleText(titleScrollOffset);
      titleScrollOffset++;
      const int textPx = (int)strlen(lastTitle) * (GLYPH_W + 1);
      if (textPx <= TITLE_W) {
        titleScrollDeadline = 0;
      } else {
        if (titleScrollOffset > textPx) titleScrollOffset = -TITLE_W / (GLYPH_W + 1);
        titleScrollDeadline = millis() + TITLE_SCROLL_STEP_MS;
      }
    }
  }

  void blitMainBackground() {
    tft.pushImage(originX, originY, SKIN_MAIN_BG_W, SKIN_MAIN_BG_H, SKIN_MAIN_BG);
  }

  // TASK-041 — VOLUME keyframe selection. 5-bucket linear partition of
  // 0..100 (each bucket 20%); negative percent → sentinel.
  static SkinUV pickKeyframe(int percent) {
    if (percent < 0)   return VOLUME_KEYFRAME_NONE;
    if (percent < 20)  return VOLUME_KEYFRAME_0;
    if (percent < 40)  return VOLUME_KEYFRAME_1;
    if (percent < 60)  return VOLUME_KEYFRAME_2;
    if (percent < 80)  return VOLUME_KEYFRAME_3;
    return VOLUME_KEYFRAME_4;
  }
  static const char *keyframeName(int percent) {
    if (percent < 0) return "NONE";
    static const char *n[] = { "0", "1", "2", "3", "4" };
    int i = percent < 20 ? 0 : percent < 40 ? 1 : percent < 60 ? 2 : percent < 80 ? 3 : 4;
    return n[i];
  }

  void blitSprite(int dstX, int dstY, const uint16_t *atlas, int atlasW, SkinUV uv) {
    for (int row = 0; row < uv.h; ++row) {
      const uint16_t *src = atlas + (uv.v + row) * atlasW + uv.u;
      tft.pushImage(dstX, dstY + row, uv.w, 1, src);
    }
  }

  void drawTransportButtons(int pressedIndex) {
    struct B { int idx, x, y; SkinUV n, p; };
    const B buttons[] = {
      { 0, CB_PREV_X,  CB_PREV_Y,  CB_PREV_N,  CB_PREV_P  },
      { 1, CB_PLAY_X,  CB_PLAY_Y,  CB_PLAY_N,  CB_PLAY_P  },
      { 2, CB_PAUSE_X, CB_PAUSE_Y, CB_PAUSE_N, CB_PAUSE_P },
      { 3, CB_STOP_X,  CB_STOP_Y,  CB_STOP_N,  CB_STOP_P  },
      { 4, CB_NEXT_X,  CB_NEXT_Y,  CB_NEXT_N,  CB_NEXT_P  },
    };
    tft.startWrite();
    for (auto &b : buttons) {
      const SkinUV uv = (b.idx == pressedIndex) ? b.p : b.n;
      blitSprite(originX + b.x, originY + b.y, SKIN_CBUTTONS, SKIN_CBUTTONS_W, uv);
    }
    tft.endWrite();
  }

  // M5 hit-testing — screen coordinates from CYD28_TouchR.getPointScaled().
  // Buttons sit at window-y 88..106, so screen-y originY+88..originY+106.
  // Each is 23 px wide except NEXT (22). Returns 0..4 (PREV..NEXT) or -1.
  int hitTestTransport(int sx, int sy) {
    const int by0 = originY + CB_PREV_Y;
    const int by1 = by0 + 18;
    if (sy < by0 || sy >= by1) return -1;
    const int x0 = originX + CB_PREV_X;
    if (sx < x0)                       return -1;
    if (sx < x0 + 23)                  return 0;  // PREV
    if (sx < x0 + 23 + 23)             return 1;  // PLAY
    if (sx < x0 + 23 + 23 + 23)        return 2;  // PAUSE
    if (sx < x0 + 23 + 23 + 23 + 23)   return 3;  // STOP
    if (sx < x0 + 23 + 23 + 23 + 23 + 22) return 4;  // NEXT
    return -1;
  }

  // chrome-001 final — bool hit-test for the shuffle / repeat sprite
  // slots. Returns 1 if (sx, sy) lands inside the sprite, else 0.
  int hitTestShuffle(int sx, int sy) {
    const int x0 = originX + SHUFFLE_X;
    const int y0 = originY + SHUFFLE_Y;
    return (sx >= x0 && sx < x0 + SHUFFLE_W &&
            sy >= y0 && sy < y0 + SHUFFLE_H) ? 1 : 0;
  }
  int hitTestRepeat(int sx, int sy) {
    const int x0 = originX + REPEAT_X;
    const int y0 = originY + REPEAT_Y;
    return (sx >= x0 && sx < x0 + REPEAT_W &&
            sy >= y0 && sy < y0 + REPEAT_H) ? 1 : 0;
  }

  // M-VIS (TASK-050a): tap anywhere in the 76×16 vis area to cycle mode.
  bool hitTestVis(int sx, int sy) {
    return (sx >= originX + vu::RECT_X && sx < originX + vu::RECT_X + vu::RECT_W &&
            sy >= originY + vu::LEFT_Y  && sy < originY + vu::LEFT_Y  + vu::VIS_H);
  }

  // TASK-053f: Winamp logo tap → TLS reset + force poll.
  int hitTestLogo(int sx, int sy) {
    const int x0 = originX + LOGO_X;
    const int y0 = originY + LOGO_Y;
    return (sx >= x0 && sx < x0 + LOGO_W &&
            sy >= y0 && sy < y0 + LOGO_H) ? 1 : 0;
  }

  // TASK-045 / ADR-016 §6 — returns 0..100 volume percent for a touch
  // inside the volume slot, or -1. Mirrors hitTestPosbar shape; no
  // dependency on songDuration (volume is independent of playback).
  long hitTestVolume(int sx, int sy) {
    const int vy0 = originY + VOLUME_Y;
    const int vy1 = vy0 + VOLUME_H;
    if (sy < vy0 || sy >= vy1) return -1;
    const int vx0 = originX + VOLUME_X;
    const int vx1 = vx0 + VOLUME_W;
    if (sx < vx0 || sx >= vx1) return -1;
    long rel = sx - vx0;
    long pct = (rel * 100) / (VOLUME_W - 1);  // 0..100
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    return pct;
  }

  // Returns the seek position in ms for a tap on the posbar groove, or -1.
  // Requires songDuration > 0 (no-op for 204-no-track state).
  long hitTestPosbar(int sx, int sy) {
    if (songDuration <= 0) return -1;
    const int py0 = originY + POSBAR_Y;
    const int py1 = py0 + POSBAR_BG.h;
    if (sy < py0 || sy >= py1) return -1;
    const int px0 = originX + POSBAR_X;
    const int px1 = px0 + POSBAR_BG.w;
    if (sx < px0 || sx >= px1) return -1;
    long offset = sx - px0;
    return (long)((offset * songDuration) / POSBAR_BG.w);
  }

public:
  // M-WEBRADIO: draw eject button from CBUTTONS atlas. pressed=true for depressed state.
  void drawEjectButton(bool pressed) {
    const SkinUV uv = pressed ? CB_EJECT_P : CB_EJECT_N;
    tft.startWrite();
    blitSprite(originX + CB_EJECT_X, originY + CB_EJECT_Y, SKIN_CBUTTONS, SKIN_CBUTTONS_W, uv);
    tft.endWrite();
  }

  // Returns true when (sx, sy) falls within the eject button hit zone.
  bool hitTestEject(int sx, int sy) {
    return sx >= originX + CB_EJECT_X &&
           sx <  originX + CB_EJECT_X + CB_EJECT_W &&
           sy >= originY + CB_EJECT_Y &&
           sy <  originY + CB_EJECT_Y + CB_EJECT_H;
  }

  // M-WEBRADIO: public transport hit-test for apps other than SpotifyApp.
  int hitTestTransportPublic(int sx, int sy) { return hitTestTransport(sx, sy); }

#ifdef SERIAL_DEBUG
  // TASK-056d — synthetic touch injection (ADR-021 AC-2 resolution).
  // Mirrors the ts.touched() hit-test branch in checkForInput() but
  // bypasses ts.touched() / ts.getPointScaled(). Populates lastTouchResult
  // before returning so cmdTap can emit the per-region JSON fields.
  // Does NOT reset touchScreenCoolDownTime — synthetic inputs must not
  // block physical input after a test.
  // SERIAL_DEBUG injection: thin shims that call handleWinampInput() directly,
  // bypassing the shell gesture tracker (intentional — injection drives its own sequencing).
  void injectTouch(int sx, int sy) override {
    if (millis() <= touchScreenCoolDownTime) {
      lastTouchResult = { "NONE", -1, "NONE", 0, -1, true };
      return;
    }
    spotifyTask::resetBackoff();
    // Capture pre-state to build lastTouchResult after the call.
    int prevDragState = (int)dragState;
    unsigned long prevLogoCooldown = logoTapCooldownMs;  // detect logo tap processed
    handleWinampInput(TouchPhase::Press, sx, sy);
    // Populate lastTouchResult based on what handleWinampInput did.
    // We detect the action by checking what changed.
    int  pressed    = hitTestTransport(sx, sy);
    long seekMs     = hitTestPosbar(sx, sy);
    long volPct     = hitTestVolume(sx, sy);
    int  hitShuffle = hitTestShuffle(sx, sy);
    int  hitRepeat  = hitTestRepeat(sx, sy);
    bool hitVis     = hitTestVis(sx, sy);
    if (pressed >= 0) {
      static const char *ta[] = { "PREV","PLAY","PAUSE","STOP","NEXT" };
      lastTouchResult = { "TRANSPORT", pressed, ta[pressed], 0, -1, false };
    } else if (seekMs >= 0) {
      lastTouchResult = { "POSBAR", -1, "SEEK", seekMs, -1, false };
    } else if (hitShuffle) {
      lastTouchResult = { "SHUFFLE", -1, "SHUFFLE", 0, -1, false };
    } else if (hitRepeat) {
      lastTouchResult = { "REPEAT", -1, "REPEAT", 0, -1, false };
    } else if (hitVis) {
      lastTouchResult = { "VIS", -1, "VIS", 0, -1, false };
    } else if (volPct >= 0) {
      lastTouchResult = { "VOLUME", -1, "VOLUME", 0, volPct, false };
    } else {
      int py = sy - originY;
      const int pleditRowsAll = PLEDIT_ROWS_Y + PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
      if (py >= PLEDIT_ROWS_Y && py < pleditRowsAll &&
          sx >= originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W && sx < originX + PLEDIT_W) {
        lastTouchResult = { "PLEDIT", scrollOffset, "SCROLL_DIRECT", 0, -1, false };
      } else if (py >= PLEDIT_ROWS_Y && py < PLEDIT_ROWS_Y + lastVisibleRows * PLEDIT_ROW_H &&
                 sx >= originX + PLEDIT_CONTENT_X && sx < originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W) {
        const int row = (py - PLEDIT_ROWS_Y) / PLEDIT_ROW_H;
        const char *act = (prevDragState == D_IDLE) ? "DRAG_START" : "DRAG_MOVE";
        lastTouchResult = { "PLEDIT", row, act, (long)(sy - _dragStartY), -1, false };
      } else if (hitTestEject(sx, sy)) {
        lastTouchResult = { "EJECT", -1, "EJECT", 0, -1, false };
      } else if (hitTestLogo(sx, sy)) {
        // Only report TLS_RESET if logoTapCooldownMs advanced (cooldown was not active).
        if (logoTapCooldownMs != prevLogoCooldown) {
          lastTouchResult = { "LOGO", -1, "TLS_RESET", 0, -1, false };
        } else {
          lastTouchResult = { "DEADZONE", -1, "FORCE_POLL", 0, -1, false };
        }
      } else {
        lastTouchResult = { "DEADZONE", -1, "FORCE_POLL", 0, -1, false };
      }
    }
  }

  void injectRelease() override {
    handleWinampInput(TouchPhase::Release, 0, 0);
    _injectingDrag = false;
    // Synthesise lastTouchResult for the drag-end case.
    if (dragState == D_IDLE) {
      // Already transitioned; no extra result needed.
    }
  }

  // TASK-056g — IDebugExportable overrides (ADR-021 A1). Owner-dispatch
  // surface for cmdGet / cmdSet. Variables: cooldown, dragState,
  // optimisticVolume, songDuration.
  bool dbgGet(const char* var, char* buf, int len) const override {
    unsigned long now = millis();
    if (strcmp(var, "cooldown") == 0) {
      uint32_t rem = touchScreenCoolDownTime > now
                     ? (uint32_t)(touchScreenCoolDownTime - now) : 0;
      snprintf(buf, len, "\"var\":\"cooldown\",\"remainingMs\":%u,\"last\":true", rem);
      return true;
    }
    if (strcmp(var, "dragState") == 0) {
      const char* dsStr = dragState == D_VOLUME_DRAG           ? "D_VOLUME_DRAG"
                        : dragState == D_POSBAR_DRAG          ? "D_POSBAR_DRAG"
                        : dragState == D_PLEDIT_SCROLL        ? "D_PLEDIT_SCROLL"
                        : dragState == D_PLEDIT_SCROLL_DIRECT ? "D_PLEDIT_SCROLL_DIRECT"
                        : dragState == D_TASKBAR_SCROLL       ? "D_TASKBAR_SCROLL"
                        : "D_IDLE";
      snprintf(buf, len, "\"var\":\"dragState\",\"state\":\"%s\",\"last\":true", dsStr);
      return true;
    }
    if (strcmp(var, "optimisticVolume") == 0) {
      uint32_t rem = optimisticVolumeUntilMs > now
                     ? (uint32_t)(optimisticVolumeUntilMs - now) : 0;
      snprintf(buf, len,
               "\"var\":\"optimisticVolume\",\"remainingMs\":%u,\"last\":true", rem);
      return true;
    }
    if (strcmp(var, "songDuration") == 0) {
      snprintf(buf, len, "\"var\":\"songDuration\",\"ms\":%ld,\"last\":true",
               songDuration);
      return true;
    }
    if (strcmp(var, "posbarDragMs") == 0) {
      snprintf(buf, len, "\"var\":\"posbarDragMs\",\"ms\":%ld,\"last\":true",
               _posbarDragCurrentMs);
      return true;
    }
    if (strcmp(var, "scrollOffset") == 0) {
      snprintf(buf, len, "\"key\":\"scrollOffset\",\"val\":%d", scrollOffset);
      return true;
    }
    if (strcmp(var, "tbScrollOffset") == 0) {
      snprintf(buf, len, "\"key\":\"tbScrollOffset\",\"val\":%d", _tbScrollOffset);
      return true;
    }
    if (strcmp(var, "lastPlaylistDraw") == 0) {
      snprintf(buf, len, "\"var\":\"lastPlaylistDraw\",\"ms\":%lu", lastPlaylistDrawMs);
      return true;
    }
    if (strcmp(var, "scrollAccum") == 0) {
      snprintf(buf, len, "\"var\":\"scrollAccum\",\"val\":%.4f,\"last\":true",
               _scrollAccum);
      return true;
    }
    if (strcmp(var, "scrollVelocity") == 0) {
      snprintf(buf, len, "\"var\":\"scrollVelocity\",\"val\":%.4f,\"last\":true",
               _scrollVelocity);
      return true;
    }
    return false;
  }
  bool dbgSet(const char* var, const char* val) override {
    if (strcmp(var, "cooldown") == 0) {
      // val=="0" or empty → reset; val>0 → arm gate for that many ms.
      // Arming lets T079 exercise the skipped-tap path from serial alone
      // (injectTouch checks the gate but never arms it — by design, so
      // synthetic taps don't block physical input after a test).
      long ms = (val && *val) ? strtol(val, nullptr, 10) : 0;
      touchScreenCoolDownTime = ms > 0 ? millis() + (unsigned long)ms : 0;
      return true;
    }
    if (strcmp(var, "songDuration") == 0) {
      // Force-set songDuration so T085 (POSBAR tap returns NONE when
      // duration==0) can run without waiting on Spotify-side cleanup of
      // the player session. Any value accepted; the next /me/player poll
      // overwrites it. Counterpart to the existing `get songDuration`.
      songDuration = (val && *val) ? strtol(val, nullptr, 10) : 0;
      return true;
    }
    if (strcmp(var, "speedK") == 0) {
      _scrollSpeedK = (val && *val) ? strtof(val, nullptr) : SCROLL_SPEED_K_DEFAULT;
      return true;
    }
    return false;
  }
#endif // SERIAL_DEBUG

private:
  void drawTimeDigits(int seconds, bool force = false) {
    if (seconds < 0) seconds = 0;
    if (seconds > 99 * 60 + 59) seconds = 99 * 60 + 59;
    if (!force && seconds == lastSeconds) return;
    lastSeconds = seconds;
    int mm = seconds / 60;
    int ss = seconds % 60;
    // Canonical Winamp digit X positions for MM:SS in main-window coords.
    // The colon between minutes and seconds is part of MAIN.BMP.
    const int digit_x[4] = { 48, 60, 78, 90 };
    const int digits[4]  = { mm / 10, mm % 10, ss / 10, ss % 10 };
    tft.startWrite();
    for (int i = 0; i < 4; ++i) {
      blitSprite(originX + digit_x[i], originY + DIGIT_Y,
                 SKIN_NUMBERS, SKIN_NUMBERS_W, DIGIT_UV(digits[i]));
    }
    tft.endWrite();
  }

  void drawStatusIndicator(SkinUV uv) {
    blitSprite(originX + PP_X, originY + PP_Y, SKIN_PLAYPAUS, SKIN_PLAYPAUS_W, uv);
  }

  // Draw lastTitle with a left-shift of `offset` pixels for marquee scroll.
  // Repaints the slot from background first so previous frame is wiped.
  void drawTitleText(int offset) {
    int slotX = originX + TITLE_X;
    int slotY = originY + TITLE_Y;
    // TASK-038: bracket the slot wipe + glyph blits in one transaction.
    tft.startWrite();
    for (int row = 0; row < TITLE_H; ++row) {
      const uint16_t *src = SKIN_MAIN_BG + (TITLE_Y + row) * SKIN_MAIN_BG_W + TITLE_X;
      tft.pushImage(slotX, slotY + row, TITLE_W, 1, src);
    }
    int x = -offset;
    for (const char *p = lastTitle; *p; ++p) {
      if (x >= TITLE_W) break;
      if (x + GLYPH_W > 0) {
        uint8_t code = (uint8_t)*p;
        if (code >= 128) code = '?';
        SkinUV uv = SKIN_GLYPH[code];
        // Clip the glyph to the slot edges.
        int dstX = slotX + (x < 0 ? 0 : x);
        int srcDx = x < 0 ? -x : 0;
        int width = GLYPH_W - srcDx;
        if (x + GLYPH_W > TITLE_W) width -= (x + GLYPH_W - TITLE_W);
        if (width > 0) {
          SkinUV clipped = { (int16_t)(uv.u + srcDx), uv.v, (int16_t)width, uv.h };
          blitSprite(dstX, slotY, SKIN_FONT, SKIN_FONT_W, clipped);
        }
      }
      x += GLYPH_W + 1;
    }
    tft.endWrite();
  }

public:
  // TASK-051i: re-tile right-side strip and blit thumb at current scrollOffset.
  // Much cheaper than a full drawPlaylist() — called during D_PLEDIT_SCROLL_DIRECT.
  void drawScrollThumbOnly() {
    if (lastCount <= PLEDIT_ROW_COUNT) return;
    const int rowsH   = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
    const int rightX  = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W;
    tft.startWrite();
    for (int sy = PLEDIT_ROWS_Y; sy < PLEDIT_ROWS_Y + rowsH; sy += PLEDIT_SIDE_H_SRC) {
      const int h = min((int)PLEDIT_SIDE_H_SRC, PLEDIT_ROWS_Y + rowsH - sy);
      tft.pushImage(rightX, sy, PLEDIT_SIDE_RIGHT_W, h, SKIN_PLEDIT_RIGHT_SIDE);
    }
    constexpr int track_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
    constexpr int travel  = track_h - SKIN_PLEDIT_THUMB_H;
    const int denom  = max(1, (int)lastCount - PLEDIT_ROW_COUNT);
    const int thumb_y = PLEDIT_ROWS_Y + scrollOffset * travel / denom;
    tft.pushImage(rightX + PLEDIT_THUMB_X_INSET, thumb_y, SKIN_PLEDIT_THUMB_W, SKIN_PLEDIT_THUMB_H,
                  SKIN_PLEDIT_THUMB, PLEDIT_TRANSPARENT_RGB565);
    tft.endWrite();
  }

  // ADR-018 TASK-047c — Winamp PLEDIT playlist editor chrome.
  // Call unconditionally from the main loop; returns immediately if the
  // snapshot seqno hasn't changed.
  // Draw the PLEDIT frame chrome — gutters, title bar, side tiles, scrollbar
  // thumb, and bottom bar — for a list of `count` rows scrolled to `scroll`.
  // Everything except the rows themselves and any app-specific overlay (e.g.
  // Spotify's total-time readout). Depends only on PLEDIT geometry + scroll/
  // count, so it is shared by drawPlaylist() (Spotify) and
  // WebRadioApp::_drawPledit() (TASK-225). Caller owns startWrite()/endWrite().
  void drawPleditFrame(int scroll, int count) {
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
      tft.pushImage(originX,                                        sy, PLEDIT_SIDE_LEFT_W,  h, SKIN_PLEDIT_LEFT_SIDE);
      tft.pushImage(originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W, sy, PLEDIT_SIDE_RIGHT_W, h, SKIN_PLEDIT_RIGHT_SIDE);
    }

    // Scrollbar thumb — sprite blit when the list exceeds the visible rows.
    if (count > PLEDIT_ROW_COUNT) {
      constexpr int track_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;   // 65 px
      constexpr int travel  = track_h - SKIN_PLEDIT_THUMB_H;      // 48 px
      const int denom   = max(1, count - PLEDIT_ROW_COUNT);
      const int thumb_x = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + PLEDIT_THUMB_X_INSET;
      const int thumb_y = PLEDIT_ROWS_Y + scroll * travel / denom;
      tft.pushImage(thumb_x, thumb_y,
                    SKIN_PLEDIT_THUMB_W, SKIN_PLEDIT_THUMB_H,
                    SKIN_PLEDIT_THUMB, PLEDIT_TRANSPARENT_RGB565);
    }

    // Bottom bar — second band of the SKIN_PLEDIT_BG atlas.
    const uint16_t *bottom = SKIN_PLEDIT_BG + (uint32_t)SKIN_PLEDIT_BG_W * PLEDIT_TITLE_H;
    tft.pushImage(originX, PLEDIT_BOTTOM_Y, SKIN_PLEDIT_BG_W, PLEDIT_BOTTOM_H, bottom);
  }

  void drawPlaylist() {
    // TASK-053c: repaint chrome + PLEDIT title bar if health state changed.
    bool healthy = spotifyTask::isHealthy();
    if (healthy != lastHealthy) {
      lastHealthy = healthy;
      repaintChrome();
      const uint16_t *pleditTitle = healthy ? SKIN_PLEDIT_BG : SKIN_PLEDIT_TITLE_INACTIVE;
      tft.pushImage(originX, PLEDIT_Y, SKIN_PLEDIT_BG_W, PLEDIT_TITLE_H, pleditTitle);
    }

    spotifyTask::QueueSnapshot qs;
    spotifyTask::copyQueueSnapshot(&qs);

    const unsigned long now = millis();
    const bool seqnoChanged = (qs.seqno != lastQueueSeqno);
    if (!seqnoChanged && !_pleditScrollDirty) return;
    if (seqnoChanged && now - lastPlaylistDrawMs < PLAYLIST_DRAW_MIN_MS) return;
    _pleditScrollDirty = false;
    lastPlaylistDrawMs = now;
    if (seqnoChanged) {
      lastQueueSeqno  = qs.seqno;
      if (dragState == D_PLEDIT_SCROLL) {
        dragState       = D_IDLE;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
      }
      scrollOffset    = 0;   // TASK-051f
      optimisticSelectedRow = -1;  // TASK-051a: new queue clears optimistic
      // TASK-051h: songsSeen — natural advance detection
      if (qs.count > 0 && _prevNextUri[0] &&
          strcmp(qs.items[0].uri, _prevNextUri) == 0 && !_skipPending) {
        _songsSeen++;
      }
      _skipPending = false;
      strlcpy(_prevNextUri, qs.count > 1 ? qs.items[1].uri : "", sizeof(_prevNextUri));
    }

    lastVisibleRows = min((int)qs.count, PLEDIT_ROW_COUNT);
    lastCount = qs.count;

    tft.startWrite();

    // Frame chrome (gutters, title bar, side tiles, scrollbar thumb, bottom bar)
    // — shared with WebRadio's _drawPledit() via drawPleditFrame() (TASK-225).
    // The bottom bar is drawn here too; it sits below the rows area so order
    // versus the rows below is irrelevant (disjoint regions).
    drawPleditFrame(scrollOffset, (int)qs.count);

    // Rows: flat fillRect (Audacious playlist-widget.cc) + Font 1 track text.
    // Font 1 glyph height = 8px; TEXT_VOFF centres it in the 13px row.
    tft.setTextFont(1);
    tft.setTextSize(1);
    tft.setTextDatum(TL_DATUM);  // own our text state — don't inherit datum from other apps
    constexpr int TEXT_MARGIN = 3;
    constexpr int TEXT_VOFF   = (PLEDIT_ROW_H - 8) / 2;
    constexpr int CHAR_W      = 6;   // Font 1 fixed-width glyph (px)
    constexpr int TEXT_GAP    = 2;   // px gap between mid section and duration
    constexpr int USABLE      = PLEDIT_CONTENT_W - 2 * TEXT_MARGIN;  // 238 px

    for (int i = 0; i < PLEDIT_ROW_COUNT; i++) {
      const int ry  = PLEDIT_ROWS_Y + i * PLEDIT_ROW_H;
      const int idx = scrollOffset + i;  // TASK-051c: offset into snapshot

      if (idx >= qs.count) {
        // Empty slot — black content area, no text.
        tft.fillRect(originX + PLEDIT_CONTENT_X, ry, PLEDIT_CONTENT_W, PLEDIT_ROW_H, TFT_BLACK);
        continue;
      }

      // Content background (side areas handled above by sprite tiling).
      const bool isCurrent    = (idx == 0);
      const bool isOptimistic = (optimisticSelectedRow == idx &&
                                 millis() < optimisticSelectedUntilMs);  // TASK-051a
      const uint16_t bg = (isCurrent || isOptimistic) ? PLEDIT_BG_SELECTED : PLEDIT_BG_NORMAL;
      const uint16_t fg = (isCurrent || isOptimistic) ? PLEDIT_FG_CURRENT  : PLEDIT_FG_NORMAL;
      tft.fillRect(originX + PLEDIT_CONTENT_X, ry, PLEDIT_CONTENT_W, PLEDIT_ROW_H, bg);

      // TASK-051g: "N. Artist - Title...  M:SS"
      // Duration right-aligned.
      char dur[8];
      const uint32_t durSec = qs.items[idx].durationMs / 1000;
      snprintf(dur, sizeof(dur), "%lu:%02lu",
               (unsigned long)(durSec / 60), (unsigned long)(durSec % 60));
      const int durW = (int)strlen(dur) * CHAR_W;

      // Number prefix "N. " (1-based, session-relative via songsSeen).
      char pfx[8];
      snprintf(pfx, sizeof(pfx), "%u. ", (unsigned)(_songsSeen + scrollOffset + i + 1));
      const int pfxW = (int)strlen(pfx) * CHAR_W;

      // Middle budget in chars; truncate with "..." if needed.
      const int midBudget = (USABLE - pfxW - TEXT_GAP - durW) / CHAR_W;
      char mid[48];
      snprintf(mid, sizeof(mid), "%s - %s",
               qs.items[idx].artist[0] ? qs.items[idx].artist : "?",
               qs.items[idx].name[0]   ? qs.items[idx].name   : "?");
      if (midBudget >= 3 && (int)strlen(mid) > midBudget) {
        mid[midBudget - 3] = '.';
        mid[midBudget - 2] = '.';
        mid[midBudget - 1] = '.';
        mid[midBudget]     = '\0';
      }

      char leftStr[56];
      snprintf(leftStr, sizeof(leftStr), "%s%s", pfx, mid);

      tft.setTextColor(fg, bg);
      const int textY = ry + TEXT_VOFF;
      tft.drawString(leftStr, originX + PLEDIT_CONTENT_X + TEXT_MARGIN, textY);
      const int durX = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W - TEXT_MARGIN - durW;
      tft.drawString(dur, durX, textY);
    }

    // Bottom bar now drawn by drawPleditFrame() above (TASK-225).

    // Total playlist time — left-aligned in the scrollbar track (dark LCD area, top
    // row of the right section, x=127 in PLEDIT frame, y+4 in bottom bar).
    // Rendered with the skin bitmap font (SKIN_GLYPH / SKIN_FONT) to match
    // track name style. Format: "MM:SS" or "H:MM:SS".
    {
      uint32_t totalMs = 0;
      for (uint8_t i = 0; i < qs.count; i++) totalMs += qs.items[i].durationMs;
      char tstr[12];
      const uint32_t totalSec = totalMs / 1000;
      const uint32_t h = totalSec / 3600;
      const uint32_t m = (totalSec % 3600) / 60;
      const uint32_t s = totalSec % 60;
      if (h > 0)
        snprintf(tstr, sizeof(tstr), "%lu:%02lu:%02lu", (unsigned long)h, (unsigned long)m, (unsigned long)s);
      else
        snprintf(tstr, sizeof(tstr), "%lu:%02lu", (unsigned long)m, (unsigned long)s);
      int tx = originX + 127 + GLYPH_W;
      const int ty = PLEDIT_BOTTOM_Y + 10;
      for (const char *p = tstr; *p; p++) {
        const SkinUV uv = SKIN_GLYPH[(uint8_t)*p & 0x7F];
        blitSprite(tx, ty, SKIN_FONT, SKIN_FONT_W, uv);
        tx += uv.w;
      }
    }

    tft.endWrite();
  }
};
