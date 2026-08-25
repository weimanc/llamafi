// winamp/winampDisplay.cpp — WinampDisplay + SpotifyQueueSource method bodies,
// out-of-line (ADR-060 D0 / ADR-061 D9 step 3, TASK-469). See winampDisplay.h
// for the class declarations and the trivial inline members.
// spotifyDisplay.h's pure virtuals use SpotifyArduino/CurrentlyPlaying/boolean
// without including what defines them (pre-existing upstream-header gap, not
// introduced here) — every .cpp that instantiates it needs these ahead of it,
// same as every existing includer of winamp/winampDisplay.h already does.
#include <Arduino.h>
#include <SpotifyArduino.h>
#include <WiFi.h>   // drawRefreshTokenMessage(): WiFi.localIP()

#include "winamp/winampDisplay.h"

// ---------------------------------------------------------------------------
// SpotifyQueueSource
// ---------------------------------------------------------------------------

bool SpotifyQueueSource::row(uint16_t idx, PlRow &out) {
  if (!_snap || idx >= _snap->count) return false;
  const spotifyTask::QueueEntry &e = _snap->items[idx];
  snprintf(out.text, sizeof(out.text), "%u. %s - %s",
           (unsigned)(_songsSeen + idx + 1),
           e.artist[0] ? e.artist : "?",
           e.name[0]   ? e.name   : "?");
  out.durationSec = e.durationMs / 1000;
  out.current     = (idx == 0);   // [0] is currently_playing (ADR-017)
  // D3: right column is the row's own "M:SS" duration, drawn in the row's
  // fg (rightColor left 0 — the renderer falls back to fg for that).
  snprintf(out.rightText, sizeof(out.rightText), "%lu:%02lu",
           (unsigned long)(out.durationSec / 60), (unsigned long)(out.durationSec % 60));
  out.rightColor = 0;
  return true;
}

uint32_t SpotifyQueueSource::totalSec() {
  if (!_snap) return 0;
  uint32_t totalMs = 0;
  for (uint8_t i = 0; i < _snap->count; i++) totalMs += _snap->items[i].durationMs;
  return totalMs / 1000;   // sum first, divide once — matches the original rounding
}

void SpotifyQueueSource::overlayText(char *buf, size_t bufSize) {
  const uint32_t total = totalSec();
  const uint32_t h = total / 3600;
  const uint32_t m = (total % 3600) / 60;
  const uint32_t s = total % 60;
  if (h > 0)
    snprintf(buf, bufSize, "%lu:%02lu:%02lu", (unsigned long)h, (unsigned long)m, (unsigned long)s);
  else
    snprintf(buf, bufSize, "%lu:%02lu", (unsigned long)m, (unsigned long)s);
}

void SpotifyQueueSource::onTap(uint16_t idx) {
  spotifyTask::enqueue(spotifyTask::ACT_PLAY_URI, (int32_t)idx);
  _skipPending = true;
}

void SpotifyQueueSource::onListReset() {
  // TASK-051h: songsSeen — a natural advance is "the item that was next-up
  // last time is playing now", and only when the user did not skip.
  if (_snap && _snap->count > 0 && _prevNextUri[0] &&
      strcmp(_snap->items[0].uri, _prevNextUri) == 0 && !_skipPending) {
    _songsSeen++;
  }
  _skipPending = false;
  strlcpy(_prevNextUri,
          (_snap && _snap->count > 1) ? _snap->items[1].uri : "",
          sizeof(_prevNextUri));
}

// ---------------------------------------------------------------------------
// WinampDisplay
// ---------------------------------------------------------------------------

void WinampDisplay::displaySetup(SpotifyArduino *spotifyObj) {
  // ADR-061 D9 step 3 / TASK-469: this used to be
  // `CheapYellowDisplay::displaySetup(spotifyObj)` followed by this class's
  // own additions. Flattened onto one body now that there is no base class
  // to delegate to — same sequence, same effect, one fewer virtual hop.
  spotify_display = spotifyObj;
  touchSetup(spotifyObj);
  Serial.println("winamp display setup");

  setWidth(320);
  setHeight(240);
  setImageHeight(150);
  setImageWidth(150);

  // Start the tft display and set it to black.
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(TFT_BLACK);

  tft.setSwapBytes(true);  // RGB565 LE in gen/ — pushImage expects byte-swap on
  originX = 0;
  originY = 0;
}

void WinampDisplay::tbGesturePress(int y) {
  _tbDragStartY  = y;
  _tbDragBaseOff = _tbScrollOffset;
  _tbScrollAccum = 0.0f;
  _tbIsScrolling = false;
  dragState      = D_TASKBAR_SCROLL;
}

bool WinampDisplay::tbGestureContinue(int y, int totalApps) {
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

bool WinampDisplay::tbGestureEnd(int y, int totalApps, int* outAppIdx) {
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

void WinampDisplay::showDefaultScreen() {
  tft.fillScreen(TFT_BLACK);
  lastThumbPx = -1;
  lastTitle[0] = '\0';
  titleScrollOffset = 0;
  titleScrollDeadline = 0;
  lastSeconds = -1;
  currentStatusUv = PP_STOP;
  repaintChrome();
}

void WinampDisplay::repaintChrome() {
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
  // TASK-417 / ADR-059 D8: gated by capability — a mode that doesn't
  // advertise CAP_SHUFFLE/CAP_REPEAT gets neither sprite drawn (previously
  // both were always drawn here regardless of mode, sourced from whatever
  // this shared cache last held — visible-but-dead icons in WebRadio and
  // Player before either could interact with them).
  if (_playerCaps & CAP_SHUFFLE) {
    drawShuffle(lastShuffleRendered == 1 ? 1 : 0);
  }
  if (_playerCaps & CAP_REPEAT) {
    drawRepeat (lastRepeatRendered  >= 0 && lastRepeatRendered <= 2
                ? (int)lastRepeatRendered : 2);
  }
  // VU rect lives inside the area we just blitted from MAIN.BMP, so
  // any cached pixel-widths are stale. Force the next vu::tick to
  // repaint from scratch.
  vu::invalidate();
  // TASK-402: the POSBAR groove was just re-blitted above (line ~148) as
  // part of this full chrome repaint, so drawBufferBar()'s own partial-
  // diff "under" blit (keyed on lastBufThumbPx) would be stale/no-op
  // against it. Invalidate so its next call redoes a real groove blit
  // instead of diffing against a thumb position that predates this
  // repaint (OQ3, M-WEBRADIO-POSBAR-SMOOTH.md).
  lastBufThumbPx = -1;
  g_lastRenderMs = millis();  // TASK-059: mark full chrome repaint time
}

void WinampDisplay::drawBufferBar(uint8_t pct) {
  if (pct > 100) pct = 100;
  const int travel  = POSBAR_BG.w - POSBAR_THUMB_N.w;   // same as the seek bar
  const int thumbPx = (int)pct * travel / 100;
  if (thumbPx == lastBufThumbPx) return;   // no visible change since last draw
  int slotX = originX + POSBAR_X;
  int slotY = originY + POSBAR_Y;
  tft.startWrite();
  if (lastBufThumbPx < 0) {
    blitSprite(slotX, slotY, SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_BG);
  } else {
    SkinUV under = { (int16_t)lastBufThumbPx, 0, POSBAR_THUMB_N.w, POSBAR_BG.h };
    blitSprite(slotX + lastBufThumbPx, slotY, SKIN_POSBAR, SKIN_POSBAR_W, under);
  }
  blitSprite(slotX + thumbPx, slotY, SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N);
  lastBufThumbPx = thumbPx;
  tft.endWrite();
}

void WinampDisplay::setTitle(const char* text) {
  // M-BOOT-UI §6 / ADR-055 decision 5: while the WiFi-down override owns
  // the marquee, remember what this caller *tried* to show (so restore
  // is correct even for a caller that never fires again during the
  // outage) but don't let it paint over the override.
  if (_wifiDownOverrideActive) {
    if (!_wifiDownStash) _wifiDownStash = (char*)malloc(sizeof(lastTitle));
    if (_wifiDownStash) {
      strncpy(_wifiDownStash, text, sizeof(lastTitle) - 1);
      _wifiDownStash[sizeof(lastTitle) - 1] = '\0';
    }
    return;
  }
  if (strcmp(lastTitle, text) == 0) return;
  _forceSetTitle(text);
}

void WinampDisplay::showWifiDownOverride() {
  if (_wifiDownOverrideActive) return;
  if (!_wifiDownStash) _wifiDownStash = (char*)malloc(sizeof(lastTitle));
  if (_wifiDownStash) {
    strncpy(_wifiDownStash, lastTitle, sizeof(lastTitle) - 1);
    _wifiDownStash[sizeof(lastTitle) - 1] = '\0';
  }
  _wifiDownOverrideActive = true;
  _forceSetTitle("WI-FI: RECONNECTING...");
}

void WinampDisplay::clearWifiDownOverride() {
  if (!_wifiDownOverrideActive) return;
  _wifiDownOverrideActive = false;
  _forceSetTitle(_wifiDownStash ? _wifiDownStash : "");
}

void WinampDisplay::drawVolume(int percent) {
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

void WinampDisplay::drawShuffle(int on) {
  SkinUV uv;
  if (on) { uv = SR_SHUFFLE_ON; }
  else    { uv = SR_SHUFFLE_OFF; }
  tft.startWrite();
  blitSprite(originX + SHUFFLE_X, originY + SHUFFLE_Y,
             SKIN_SHUFREP, SKIN_SHUFREP_W, uv);
  tft.endWrite();
  lastShuffleRendered = on ? 1 : 0;
}

void WinampDisplay::drawRepeat(int state) {
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

void WinampDisplay::displayTrackProgress(long progress, long duration) {
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

void WinampDisplay::printCurrentlyPlayingToScreen(CurrentlyPlaying currentlyPlaying) {
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

bool WinampDisplay::handleWinampInput(TouchPhase phase, int x, int y) {
  // Deferred press-release: fires on Release, or on Move/Press timer.
  if (phase == TouchPhase::Release) {
    if (pendingReleaseAt != 0) {
      drawTransportButtons(-1);
      pendingReleaseAt = 0;
    }
    // Drag-end handling on Release. TASK-411: the PLEDIT gesture (both the
    // row drag and the right-strip drag) is owned by _plView; it reports back
    // the inter-gesture cooldown and whether a tap was dispatched.
    if (_plView.dragging()) {
      const PlReleaseResult r = _plView.release(_queueSource);
      if (r.tapDispatched) _lastInputWasAsync = true;
      if (r.cooldownMs)    touchScreenCoolDownTime = millis() + r.cooldownMs;
    }
    if (dragState == D_POSBAR_DRAG) {
      _seekSink((long)_posbarDragCurrentMs);
      _lastInputWasAsync = true;
      songStartMillis = millis() - _posbarDragCurrentMs;
      touchScreenCoolDownTime = millis() + 200;
      dragState = D_IDLE;
    }
    if (dragState == D_VOLUME_DRAG) {
      _volumeDragRelease();   // TASK-492: shared with handleVolumeGesturePublic()
    }
    // Marquee tick on Release too (runs below for Move/Press).
    _tickMarquee();
    return false;
  }

  // Press or Move.
  // Phase 1 — captured gesture: route directly to owning handler, no hit-test.
  if (_plView.dragging()) {
    _plView.move(y, originX, originY);
    _tickMarquee();
    return true;
  }
  if (dragState != D_IDLE) {
    switch (dragState) {
      case D_VOLUME_DRAG:
        _volumeDragContinue(x);   // TASK-492: shared with handleVolumeGesturePublic()
        break;
      case D_POSBAR_DRAG:
        _posbarDragCurrentMs = posbarFromX(x);
        updateSeekThumb(_posbarDragCurrentMs);
        songStartMillis = millis() - _posbarDragCurrentMs;
        break;
      default: break;
    }
    _tickMarquee();
    return true;
  }

  // Phase 2 — D_IDLE only: run hit-tests to start a new gesture.
  // TASK-417 / ADR-059 D8: each hit-test is gated by the active mode's
  // capability mask — a zone whose bit is absent is skipped entirely
  // (not just its dispatch), so it never fires and never eats the touch
  // ahead of whatever real zone is underneath. Volume and vis are outside
  // the mask by design (unaffected by this task — TASK-352 owns volume,
  // and vis is universal).
  if (millis() <= touchScreenCoolDownTime) { _tickMarquee(); return false; }
  int  pressed    = (_playerCaps & CAP_TRANSPORT) ? hitTestTransport(x, y) : -1;
  long seekMs     = (_playerCaps & CAP_SEEK)      ? hitTestPosbar(x, y)    : -1;
  long volPct     = hitTestVolume(x, y);
  int  hitShuffle = (_playerCaps & CAP_SHUFFLE)   ? hitTestShuffle(x, y)   : 0;
  int  hitRepeat  = (_playerCaps & CAP_REPEAT)    ? hitTestRepeat (x, y)   : 0;
  bool hitVis     = hitTestVis(x, y);

  bool consumed = false;

  if (pressed >= 0) {
    drawTransportButtons(pressed);
    switch (pressed) {
      case 0: spotifyTask::enqueue(spotifyTask::ACT_PREV);  break;
      case 1: spotifyTask::enqueue(spotifyTask::ACT_PLAY);  break;
      case 2: spotifyTask::enqueue(spotifyTask::ACT_PAUSE); break;
      case 3: spotifyTask::enqueue(spotifyTask::ACT_PAUSE); break;
      case 4: spotifyTask::enqueue(spotifyTask::ACT_NEXT); _queueSource.noteIntentionalSkip(); break;
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
    _shuffleSink(next);
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
    _repeatSink(next);
    _lastInputWasAsync = true;
    optimisticShufRepUntilMs = millis() + SHUFREP_OPTIMISTIC_HOLD_MS;
    touchScreenCoolDownTime = millis() + 250;
    consumed = true;
  } else if (hitVis) {
    vu::nextMode();
    touchScreenCoolDownTime = millis() + 300;
    consumed = true;
  } else if (volPct >= 0) {
    _volumeDragCapture(volPct);   // TASK-492: shared with handleVolumeGesturePublic()
    consumed = true;
  } else {
    // TASK-411: both PLEDIT zones (right strip, then rows) are hit-tested and
    // anchored by the view — see PleditView::press().
    if (_plView.press(x, y, originX, originY)) {
      consumed = true;
    } else if (dragState == D_IDLE) {
      if (hitTestLogo(x, y) && tryReconnect()) {
        _lastInputWasAsync = true;
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

void WinampDisplay::_volumeDragCapture(long volPct) {
  dragState = D_VOLUME_DRAG;
  drawVolume((int)volPct);
  unsigned long now = millis();
  if (now - lastVolumeEnqueuedMs > VOLUME_DRAG_DEBOUNCE_MS &&
      (int8_t)volPct != lastVolumeEnqueuedPct) {
    _volumeSink((int)volPct);
    LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", volPct);
    lastVolumeEnqueuedMs = now;
    lastVolumeEnqueuedPct = (int8_t)volPct;
  }
  optimisticVolumeUntilMs = now + VOLUME_OPTIMISTIC_HOLD_MS;
}

void WinampDisplay::_volumeDragContinue(int x) {
  long pct = volumeFromX(x);
  drawVolume((int)pct);
  unsigned long now = millis();
  if (now - lastVolumeEnqueuedMs > VOLUME_DRAG_DEBOUNCE_MS &&
      (int8_t)pct != lastVolumeEnqueuedPct) {
    _volumeSink((int)pct);
    LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", pct);
    lastVolumeEnqueuedMs = now;
    lastVolumeEnqueuedPct = (int8_t)pct;
  }
  optimisticVolumeUntilMs = now + VOLUME_OPTIMISTIC_HOLD_MS;
}

void WinampDisplay::_volumeDragRelease() {
  if (lastVolumeRendered >= 0 && lastVolumeRendered != lastVolumeEnqueuedPct) {
    _volumeSink((int)lastVolumeRendered);
    _lastInputWasAsync = true;
    lastVolumeEnqueuedPct = lastVolumeRendered;
    Serial.printf("[D][chrome] drag-end commit pct=%d\n", (int)lastVolumeRendered);
  }
  dragState = D_IDLE;
}

bool WinampDisplay::handleVolumeGesturePublic(TouchPhase phase, int x, int y) {
  if (dragState == D_VOLUME_DRAG) {
    if (phase == TouchPhase::Release) {
      _volumeDragRelease();
      return true;
    }
    _volumeDragContinue(x);
    return true;
  }
  if (phase != TouchPhase::Press) return false;
  long volPct = hitTestVolume(x, y);
  if (volPct < 0) return false;
  _volumeDragCapture(volPct);
  return true;
}

void WinampDisplay::resetDragState() {
  dragState = D_IDLE;
  _plView.resetDrag();
  pendingReleaseAt = 0;
#ifdef SERIAL_DEBUG
  _injectingDrag = false;
#endif
}

// ---------------------------------------------------------------------------
// ADR-061 D9 step 3 / TASK-469 — absorbed CheapYellowDisplay members.
// ---------------------------------------------------------------------------

void WinampDisplay::clearImage() {
  // Dead in this build (M-NOART / TASK-062; grep-confirmed no caller), but
  // ported faithfully rather than left unimplemented — a future caller
  // reached through the SpotifyDisplay* interface gets the same behaviour
  // CheapYellowDisplay always gave it.
  int imagePosition = screenCenterX - (imageWidth / 2);
  tft.fillRect(imagePosition, 0, imageWidth, imageHeight, TFT_BLACK);
}

void WinampDisplay::markDisplayAsTagRead() {
  // Dead in this build (grep-confirmed no caller) — ported faithfully.
  int imagePosition = screenCenterX - (imageWidth / 2);
  tft.drawRect(imagePosition, 0, imageWidth, imageHeight, TFT_BLUE);
  tft.drawRect(imagePosition + 2, 2, imageWidth - 4, imageHeight - 4, TFT_RED);
}

void WinampDisplay::markDisplayAsTagWritten() {
  // Dead in this build (grep-confirmed no caller) — ported faithfully.
  int imagePosition = screenCenterX - (imageWidth / 2);
  tft.drawRect(imagePosition, 0, imageWidth, imageHeight, TFT_RED);
  tft.drawRect(imagePosition + 2, 2, imageWidth - 4, imageHeight - 4, TFT_GREEN);
}

void WinampDisplay::drawRefreshTokenMessage() {
  // The one real (non-dead) member in this group — boot.cpp calls this via
  // the SpotifyDisplay* handle for the refresh-token-mode screen. Ported
  // with full fidelity from CheapYellowDisplay's implementation.
  Serial.println("Refresh Token Mode");
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawCentreString("Refresh Token Mode:", screenCenterX, 5, 2);
  tft.drawString("You need to authorize this device to use", 5, 28, 2);
  tft.drawString("your spotify account.", 5, 46, 2);

  tft.drawString("Visit the following address and follow", 5, 82, 2);
  tft.drawString("the instrucitons:", 5, 100, 2);
  tft.setTextColor(TFT_BLUE, TFT_BLACK);
  tft.drawString(WiFi.localIP().toString(), 10, 128, 2);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
}

// ---------------------------------------------------------------------------

#ifdef SERIAL_DEBUG
void WinampDisplay::injectTouch(int sx, int sy) {
  if (millis() <= touchScreenCoolDownTime) {
    lastTouchResult = { "NONE", -1, "NONE", 0, -1, true };
    return;
  }
  spotifyTask::resetBackoff();
  // Capture pre-state to build lastTouchResult after the call.
  const bool prevPleditDragging = _plView.dragging();
  unsigned long prevLogoCooldown = logoTapCooldownMs;  // detect logo tap processed
  handleWinampInput(TouchPhase::Press, sx, sy);
  // Populate lastTouchResult based on what handleWinampInput did.
  // We detect the action by checking what changed.
  // TASK-417: mirror handleWinampInput()'s own capability gating here —
  // otherwise a WebRadio/Player cmdTap could report a SHUFFLE/REPEAT/
  // POSBAR hit that handleWinampInput() itself skipped (or vice versa for
  // Player once its own real-touch path also hit-tests these zones).
  int  pressed    = (_playerCaps & CAP_TRANSPORT) ? hitTestTransport(sx, sy) : -1;
  long seekMs     = (_playerCaps & CAP_SEEK)      ? hitTestPosbar(sx, sy)    : -1;
  long volPct     = hitTestVolume(sx, sy);
  int  hitShuffle = (_playerCaps & CAP_SHUFFLE)   ? hitTestShuffle(sx, sy)   : 0;
  int  hitRepeat  = (_playerCaps & CAP_REPEAT)    ? hitTestRepeat(sx, sy)    : 0;
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
    const Rect plStrip = _plView.stripRect(originX, originY);
    const Rect plRows  = _plView.rowsRect(originX, originY);
    if (hitTest(plStrip, sx, sy)) {
      lastTouchResult = { "PLEDIT", _plView.scrollOffset(), "SCROLL_DIRECT", 0, -1, false };
    } else if (hitTest(plRows, sx, sy)) {
      const int row = hitTestRow(plRows, PLEDIT_ROW_H, sy);
      const char *act = prevPleditDragging ? "DRAG_MOVE" : "DRAG_START";
      lastTouchResult = { "PLEDIT", row, act, (long)(sy - _plView.dragStartY()), -1, false };
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

void WinampDisplay::injectRelease() {
  handleWinampInput(TouchPhase::Release, 0, 0);
  _injectingDrag = false;
  // Synthesise lastTouchResult for the drag-end case.
  if (dragState == D_IDLE) {
    // Already transitioned; no extra result needed.
  }
}

bool WinampDisplay::dbgGet(const char* var, char* buf, int len) const {
  unsigned long now = millis();
  if (strcmp(var, "cooldown") == 0) {
    uint32_t rem = touchScreenCoolDownTime > now
                   ? (uint32_t)(touchScreenCoolDownTime - now) : 0;
    snprintf(buf, len, "\"var\":\"cooldown\",\"remainingMs\":%u,\"last\":true", rem);
    return true;
  }
  if (strcmp(var, "dragState") == 0) {
    // TASK-411: the two PLEDIT states are derived from the view (their sole
    // owner); the rest are this class's own. The reported strings are
    // unchanged — the serial contract predates the extraction.
    const char* dsStr = _plView.dragMode() == PleditView::DRAG_ROWS  ? "D_PLEDIT_SCROLL"
                      : _plView.dragMode() == PleditView::DRAG_STRIP ? "D_PLEDIT_SCROLL_DIRECT"
                      : dragState == D_VOLUME_DRAG                   ? "D_VOLUME_DRAG"
                      : dragState == D_POSBAR_DRAG                   ? "D_POSBAR_DRAG"
                      : dragState == D_TASKBAR_SCROLL                ? "D_TASKBAR_SCROLL"
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
  // TASK-417 / ADR-059 D8: T_PLR_17-19 observability. shufRep reports the
  // currently-rendered sprite state (whatever mode last drew it — the
  // point of D8 is that this is now sourced from the active mode, not
  // always Spotify's snapshot) alongside the active capability mask, so a
  // test can confirm both "is this drawn" (playerCaps bit) and "does the
  // sprite reflect this mode's own state" (lastShuffle/lastRepeat) without
  // a separate getter per mode.
  if (strcmp(var, "shufRep") == 0) {
    snprintf(buf, len,
             "\"var\":\"shufRep\",\"caps\":%u,\"lastShuffle\":%d,\"lastRepeat\":%d,"
             "\"last\":true",
             (unsigned)_playerCaps, (int)lastShuffleRendered, (int)lastRepeatRendered);
    return true;
  }
  // TASK-390: marquee/title state observability — no prior getter exposed
  // any of this. deadlineInMs is signed (can go negative: a positive
  // titleScrollDeadline that's already in the past would mean _tickMarquee()
  // should have fired but hasn't — the smoking gun for a stuck marquee,
  // vs. deadline==0 which is the *intentional* static-title (fits on
  // screen, no scroll needed) resting state, not a bug by itself.
  if (strcmp(var, "wrMarquee") == 0) {
    long deadlineInMs = titleScrollDeadline
                       ? (long)titleScrollDeadline - (long)now : 0;
    // TASK-399: textPx/periodPx/scrolling let a DUT session confirm the
    // endless-loop period matches lastTitle+separator without eyeballing.
    snprintf(buf, len,
             "\"var\":\"wrMarquee\",\"lastTitle\":\"%s\",\"scrollOffset\":%d,"
             "\"scrollDeadlineSet\":%s,\"deadlineInMs\":%ld,"
             "\"wifiDownOverrideActive\":%s,\"textPx\":%d,\"periodPx\":%d,"
             "\"scrolling\":%s,\"last\":true",
             lastTitle, titleScrollOffset,
             titleScrollDeadline ? "true" : "false", deadlineInMs,
             _wifiDownOverrideActive ? "true" : "false",
             titleTextPx, titlePeriodPx, titleTextPx > TITLE_W ? "true" : "false");
    return true;
  }
  if (strcmp(var, "posbarDragMs") == 0) {
    snprintf(buf, len, "\"var\":\"posbarDragMs\",\"ms\":%ld,\"last\":true",
             _posbarDragCurrentMs);
    return true;
  }
  if (strcmp(var, "scrollOffset") == 0) {
    snprintf(buf, len, "\"key\":\"scrollOffset\",\"val\":%d", _plView.scrollOffset());
    return true;
  }
  // ADR-059 D12 / TASK-411: monotonic PLEDIT repaint counter. The seqno
  // redraw gate had no observable signal before this — "no repaint while
  // seqno is static" (T_PLE_04, T_PLE_14) was unassertable from serial.
  if (strcmp(var, "pleditRepaints") == 0) {
    snprintf(buf, len, "\"var\":\"pleditRepaints\",\"count\":%lu,\"last\":true",
             (unsigned long)_plView.repaints());
    return true;
  }
  if (strcmp(var, "tbScrollOffset") == 0) {
    snprintf(buf, len, "\"key\":\"tbScrollOffset\",\"val\":%d", _tbScrollOffset);
    return true;
  }
  if (strcmp(var, "lastPlaylistDraw") == 0) {
    snprintf(buf, len, "\"var\":\"lastPlaylistDraw\",\"ms\":%lu", _plView.lastDrawMs());
    return true;
  }
  if (strcmp(var, "scrollAccum") == 0) {
    snprintf(buf, len, "\"var\":\"scrollAccum\",\"val\":%.4f,\"last\":true",
             _plView.scrollAccum());
    return true;
  }
  if (strcmp(var, "scrollVelocity") == 0) {
    snprintf(buf, len, "\"var\":\"scrollVelocity\",\"val\":%.4f,\"last\":true",
             _plView.scrollVelocity());
    return true;
  }
  return false;
}

bool WinampDisplay::dbgSet(const char* var, const char* val) {
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
    _plView.setSpeedK((val && *val) ? strtof(val, nullptr) : SCROLL_SPEED_K_DEFAULT);
    return true;
  }
  return false;
}
#endif // SERIAL_DEBUG

void WinampDisplay::updateSeekThumb(long ms) {
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

void WinampDisplay::_forceSetTitle(const char* text) {
  strncpy(lastTitle, text, sizeof(lastTitle) - 1);
  lastTitle[sizeof(lastTitle) - 1] = '\0';
  titleScrollOffset   = 0;
  titleScrollDeadline = millis() + TITLE_SCROLL_HOLD_MS;
  titleTextPx   = (int)strlen(lastTitle) * (GLYPH_W + 1);
  titlePeriodPx = titleTextPx + kTitleMarqueeSepLen * (GLYPH_W + 1);
  drawTitleText(0);
}

void WinampDisplay::_tickMarquee() {
  if (titleScrollDeadline && millis() >= titleScrollDeadline) {
    drawTitleText(titleScrollOffset);
    if (titleTextPx <= TITLE_W) {
      titleScrollDeadline = 0;
    } else {
      titleScrollOffset = (titleScrollOffset + 1) % titlePeriodPx;
      titleScrollDeadline = millis() + TITLE_SCROLL_STEP_MS;
    }
  }
}

SkinUV WinampDisplay::pickKeyframe(int percent) {
  if (percent < 0)   return VOLUME_KEYFRAME_NONE;
  if (percent < 20)  return VOLUME_KEYFRAME_0;
  if (percent < 40)  return VOLUME_KEYFRAME_1;
  if (percent < 60)  return VOLUME_KEYFRAME_2;
  if (percent < 80)  return VOLUME_KEYFRAME_3;
  return VOLUME_KEYFRAME_4;
}

const char *WinampDisplay::keyframeName(int percent) {
  if (percent < 0) return "NONE";
  static const char *n[] = { "0", "1", "2", "3", "4" };
  int i = percent < 20 ? 0 : percent < 40 ? 1 : percent < 60 ? 2 : percent < 80 ? 3 : 4;
  return n[i];
}

void WinampDisplay::drawTransportButtons(int pressedIndex) {
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

int WinampDisplay::hitTestTransport(int sx, int sy) {
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

long WinampDisplay::hitTestVolume(int sx, int sy) {
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

long WinampDisplay::hitTestPosbar(int sx, int sy) {
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

void WinampDisplay::drawEjectButton(bool pressed) {
  const SkinUV uv = pressed ? CB_EJECT_P : CB_EJECT_N;
  tft.startWrite();
  blitSprite(originX + CB_EJECT_X, originY + CB_EJECT_Y, SKIN_CBUTTONS, SKIN_CBUTTONS_W, uv);
  tft.endWrite();
}

bool WinampDisplay::tryReconnect() {
  if (millis() < logoTapCooldownMs) return false;
  spotifyTask::resetTls();
  spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
  logoTapCooldownMs = millis() + LOGO_TAP_COOLDOWN_MS;
  return true;
}

bool WinampDisplay::hitTestPosbarZonePublic(int sx, int sy) {
  const int py0 = originY + POSBAR_Y;
  const int py1 = py0 + POSBAR_BG.h;
  if (sy < py0 || sy >= py1) return false;
  const int px0 = originX + POSBAR_X;
  const int px1 = px0 + POSBAR_BG.w;
  return (sx >= px0 && sx < px1);
}

void WinampDisplay::drawTimeDigits(int seconds, bool force) {
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

void WinampDisplay::drawTitleText(int offset) {
  int slotX = originX + TITLE_X;
  int slotY = originY + TITLE_Y;
  // TASK-038: bracket the slot wipe + glyph blits in one transaction.
  tft.startWrite();
  for (int row = 0; row < TITLE_H; ++row) {
    const uint16_t *src = SKIN_MAIN_BG + (TITLE_Y + row) * SKIN_MAIN_BG_W + TITLE_X;
    tft.pushImage(slotX, slotY + row, TITLE_W, 1, src);
  }
  // TASK-399: once scrolling, walk a virtual index across lastTitle +
  // separator + lastTitle (modulo the cached period) instead of a flat
  // pointer walk -- no doubled string in memory (Option B, see
  // M-TITLE-MARQUEE-WRAP.md). Short/static text keeps the original flat
  // walk unchanged (Goal 3).
  const bool scrolling = titleTextPx > TITLE_W;
  const int textLen = (int)strlen(lastTitle);
  const int sepLen  = kTitleMarqueeSepLen;
  const int cycleLen = textLen + sepLen;

  int x = -offset;
  for (int i = 0; x < TITLE_W; ++i) {
    bool draw = true;
    SkinUV uv;
    if (scrolling) {
      int m = i % cycleLen;
      if (m < textLen) {
        uint8_t code = (uint8_t)lastTitle[m];
        if (code >= 128) code = '?';
        uv = SKIN_GLYPH[code];
      } else {
        // Separator zone: middle 3 slots carry the glyph, outer slots on
        // each side are blank gap -- nothing to draw for those.
        int s = m - textLen;
        if (s >= 3 && s < 6) {
          uv = kTitleMarqueeSepGlyph;
        } else {
          draw = false;
        }
      }
    } else {
      if (i >= textLen) break;
      uint8_t code = (uint8_t)lastTitle[i];
      if (code >= 128) code = '?';
      uv = SKIN_GLYPH[code];
    }
    if (draw && x + GLYPH_W > 0) {
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

void WinampDisplay::drawPlaylist() {
  // TASK-053c: repaint chrome + PLEDIT title bar if health state changed.
  // Not PLEDIT content — this is the connection-health indicator that
  // happens to repaint the title strip, so it stays with the Spotify caller.
  bool healthy = spotifyTask::isHealthy();
  if (healthy != lastHealthy) {
    lastHealthy = healthy;
    repaintChrome();
    const uint16_t *pleditTitle = healthy ? SKIN_PLEDIT_BG : SKIN_PLEDIT_TITLE_INACTIVE;
    tft.pushImage(originX, PLEDIT_Y, SKIN_PLEDIT_BG_W, PLEDIT_TITLE_H, pleditTitle);
  }

  // The snapshot is stack-resident for exactly this call; the source borrows
  // it for the duration of the repaint and gives it back (see
  // SpotifyQueueSource::bind() for why it is not a member).
  spotifyTask::QueueSnapshot qs;
  spotifyTask::copyQueueSnapshot(&qs);
  _queueSource.bind(&qs);
  _plView.draw(_queueSource, originX);
  _queueSource.bind(nullptr);
}
