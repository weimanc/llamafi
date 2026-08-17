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
#include "touch/scrollTuning.h"   // TASK-277: shared gesture tuning (see header)
#include "winamp/skinBlit.h"      // TASK-411: the one skin sprite blit
#include "winamp/pleditView.h"    // TASK-411 / ADR-059 D4: the one PLEDIT renderer

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

// TASK-399: endless-ticker separator between marquee loop passes.
// M-TITLE-MARQUEE-WRAP.md originally specced ASCII '*' (TEXT.BMP row2/col1
// via CHAR_MAP/SKIN_GLYPH), documented there as "cosmetically a ninja-star/
// shuriken" from a BMP-crop read. DUT-verified 2026-08-05 that read was
// wrong -- at actual render size it reads as "o-umlaut", not a star (a
// second independent crop-read, on the screenshot taken to confirm it,
// made the identical mistake). Human picked row2/col4 instead: a cell
// TEXT.BMP has real pixel data in (confirmed via full-atlas scan -- it's
// not blank) but bake_skin.py's CHAR_MAP never wires to any ASCII code
// (row 2 is `"?*                             "` -- col4 is a space, so any
// code that would map there instead falls through to BLANK_COL/BLANK_ROW).
// Referenced directly by pixel position rather than adding a new CHAR_MAP
// entry + re-baking -- only this one fixed spot needs it, not a general
// ASCII mapping.
static constexpr SkinUV kTitleMarqueeSepGlyph = { 4 * GLYPH_W, 2 * GLYPH_H, GLYPH_W, GLYPH_H };
static constexpr int kTitleMarqueeSepLen = 9;  // 3 blank + 3 glyph + 3 blank slots

// TASK-411 / ADR-059 D4 — the Spotify queue as a PlaylistSource (CAP_PLAY only).
// Also the new home of the Spotify-domain playlist bookkeeping that used to sit
// in WinampDisplay: session-relative row numbering (songsSeen), the two-entry
// URI history that distinguishes a natural track advance from a user skip, and
// the skip suppressor itself. None of that is renderer business.
class SpotifyQueueSource : public PlaylistSource {
public:
  // The snapshot lives on the caller's stack for the duration of one repaint.
  // A QueueSnapshot member here would be a permanent multi-KB .bss cost for
  // data that is only live inside drawPlaylist().
  void bind(const spotifyTask::QueueSnapshot *s) { _snap = s; }

  uint16_t count() override { return _snap ? (uint16_t)_snap->count : 0; }
  uint32_t seqno() override { return _snap ? _snap->seqno : 0; }
  uint8_t  caps()  override { return CAP_PLAY; }

  // TASK-051g: "N. Artist - Title", N session-relative via songsSeen. The
  // renderer applies the ellipsis truncation against the remaining pixel
  // budget — composing here keeps the numbering policy with the source that
  // defines it (a station list has no track numbers at all).
  bool row(uint16_t idx, PlRow &out) override {
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

  uint32_t totalSec() override {
    if (!_snap) return 0;
    uint32_t totalMs = 0;
    for (uint8_t i = 0; i < _snap->count; i++) totalMs += _snap->items[i].durationMs;
    return totalMs / 1000;   // sum first, divide once — matches the original rounding
  }

  // D10: total playlist time, "MM:SS" or "H:MM:SS" — the pre-extraction
  // bottom-bar overlay format, unchanged.
  void overlayText(char *buf, size_t bufSize) override {
    const uint32_t total = totalSec();
    const uint32_t h = total / 3600;
    const uint32_t m = (total % 3600) / 60;
    const uint32_t s = total % 60;
    if (h > 0)
      snprintf(buf, bufSize, "%lu:%02lu:%02lu", (unsigned long)h, (unsigned long)m, (unsigned long)s);
    else
      snprintf(buf, bufSize, "%lu:%02lu", (unsigned long)m, (unsigned long)s);
  }

  void onTap(uint16_t idx) override {
    spotifyTask::enqueue(spotifyTask::ACT_PLAY_URI, (int32_t)idx);
    _skipPending = true;
  }

  // Fires when the renderer's gate actually consumes a seqno advance, not on
  // every snapshot write — the 1 Hz rate limit can defer one, and the advance
  // detector must stay in lockstep with what was drawn.
  void onListReset() override {
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

  // Transport NEXT / tap-to-play are both intentional skips; suppress the
  // songsSeen increment the next advance would otherwise earn.
  void noteIntentionalSkip() { _skipPending = true; }

private:
  const spotifyTask::QueueSnapshot *_snap = nullptr;
  uint16_t _songsSeen = 0;          // natural track advances since boot
  char     _prevNextUri[64] = {};   // URI of items[1] from the last consumed poll
  bool     _skipPending = false;
};

// ADR-059 D8 / TASK-417 — per-mode transport capability mask. A zone whose
// capability bit is absent is neither drawn nor hit-tested. Spotify
// advertises all four (today's shipped behaviour); WebRadio advertises
// CAP_TRANSPORT only (unchanged — T_PLR_18); Player advertises all four
// (T_PLR_19). Deliberately a plain top-level enum, not nested in
// WinampDisplay, so every App file that includes this header can build a
// mask literal without qualifying it.
enum : uint8_t {
  CAP_TRANSPORT = 1 << 0,
  CAP_SEEK      = 1 << 1,
  CAP_SHUFFLE   = 1 << 2,
  CAP_REPEAT    = 1 << 3,
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
  // TASK-279 (DEV-3-1): scroll-start signal for the shell's press-highlight cancel —
  // tbGestureContinue() returns true only on ≥1-slot steps, so dead-zone-exceeded with
  // sub-slot travel is otherwise unobservable from the shell.
  bool tbIsScrolling()  const { return _tbIsScrolling; }

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

  // TASK-253 — WebRadio buffer-fullness bar. Reuses the POSBAR exactly as Spotify
  // uses its seek bar: the groove sprite plus the POSBAR thumb, whose POSITION marks
  // buffer fullness (left = empty, right = full) — pct 0..100 mapped over the same
  // travel the seek bar uses. WebRadio-only; the renderer owns SKIN_POSBAR so it
  // restores the groove here. Mirrors app/tools/preview_webradio.py::_draw_buffer_bar.
  // TASK-402 (Option E): partial-diff blit, mirrors updateSeekThumb()'s own
  // pattern in this file — blit only the old-thumb-position "under" sprite
  // plus the new thumb, instead of unconditionally repainting the whole
  // 248x10 groove every call (~20 pushImage calls → ~1 when unchanged, ~12
  // when moved). First call since a full chrome repaint (lastBufThumbPx==-1,
  // see repaintChrome()'s invalidation) still does a real groove blit.
  void drawBufferBar(uint8_t pct) {
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

  // TASK-349 — main-window time digits for WebRadio (stream play time, no
  // posbar thumb — WebRadio's posbar is drawBufferBar() above, not a seek
  // position). Spotify drives the digits via displayTrackProgress(); this is
  // the WebRadio-only entry into the same self-guarded drawTimeDigits().
  void updateTimeDigits(int seconds) { drawTimeDigits(seconds); }

  // TASK-252 — set the marquee title (shared: Spotify track + WebRadio station/
  // state). Redraws only on change; resets scroll + holds before scrolling. The
  // baked SKIN_GLYPH folds lowercase→uppercase, so callers needn't uppercase.
  void setTitle(const char* text) {
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

  // TASK-252 — drive the title marquee scroll (WebRadio calls from its tick();
  // Spotify drives it internally via _tickMarquee in its own tick/input paths).
  void tickMarquee() { _tickMarquee(); }

  // M-BOOT-UI §6 / ADR-055 decision 5 — centralized WiFi-down marquee
  // override, driven by the loop()-level edge-triggered detector in
  // main.cpp. No-op if already active/inactive (idempotent under repeated
  // calls from an edge-triggered caller).
  void showWifiDownOverride() {
    if (_wifiDownOverrideActive) return;
    if (!_wifiDownStash) _wifiDownStash = (char*)malloc(sizeof(lastTitle));
    if (_wifiDownStash) {
      strncpy(_wifiDownStash, lastTitle, sizeof(lastTitle) - 1);
      _wifiDownStash[sizeof(lastTitle) - 1] = '\0';
    }
    _wifiDownOverrideActive = true;
    _forceSetTitle("WI-FI: RECONNECTING...");
  }

  void clearWifiDownOverride() {
    if (!_wifiDownOverrideActive) return;
    _wifiDownOverrideActive = false;
    _forceSetTitle(_wifiDownStash ? _wifiDownStash : "");
  }

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

  // TASK-352: swap the volume-commit seam (nullptr restores the default
  // Spotify ACT_VOLUME enqueue). SpotifyApp::resume() calls this with nullptr
  // on every eject-back so the shared drag machine never sticks on a stale
  // WebRadio sink.
  void setVolumeSink(void (*sink)(int)) {
    _volumeSink = sink ? sink : &_defaultVolumeSink;
  }

  // TASK-417 / ADR-059 D8: mirrors setVolumeSink() — swap the shuffle/
  // repeat/seek commit seams (nullptr restores the Spotify defaults).
  void setShuffleSink(void (*sink)(int))  { _shuffleSink = sink ? sink : &_defaultShuffleSink; }
  void setRepeatSink (void (*sink)(int))  { _repeatSink  = sink ? sink : &_defaultRepeatSink;  }
  void setSeekSink   (void (*sink)(long)) { _seekSink    = sink ? sink : &_defaultSeekSink;    }

  // TASK-417 / ADR-059 D8: each App sets this in resume() to advertise
  // which of CAP_TRANSPORT|CAP_SEEK|CAP_SHUFFLE|CAP_REPEAT it supports. A
  // zone whose bit is absent is neither drawn (repaintChrome()) nor
  // hit-tested (handleWinampInput()).
  void setPlayerCaps(uint8_t caps) { _playerCaps = caps; }
  uint8_t playerCaps() const       { return _playerCaps; }

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
        if (lastVolumeRendered >= 0 && lastVolumeRendered != lastVolumeEnqueuedPct) {
          _volumeSink((int)lastVolumeRendered);
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
    if (_plView.dragging()) {
      _plView.move(y, originX, originY);
      _tickMarquee();
      return true;
    }
    if (dragState != D_IDLE) {
      switch (dragState) {
        case D_VOLUME_DRAG: {
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
          break;
        }
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

  // TASK-352: narrow public capture entry into the SAME D_VOLUME_DRAG state
  // machine handleWinampInput() owns above (dragState, drawVolume(),
  // volumeFromX(), debounce, optimistic hold, the _volumeSink seam) — for
  // callers like WebRadio whose input path is piecemeal hitTest*Public calls,
  // not the full handleWinampInput() dispatch (which would also hit-test
  // Spotify-only zones — transport/posbar-seek/PLEDIT/shuffle/repeat — that
  // WebRadio must not trigger). Deliberately NOT routed through
  // handleWinampInput() for that reason; every field/helper it touches is
  // shared state, so this is reuse of the machine, not a duplicate of it.
  // Press: hit-test only, ignored (returns false) outside the slider.
  // Move/Release: captured — consumes unconditionally once a drag is live.
  bool handleVolumeGesturePublic(TouchPhase phase, int x, int y) {
    if (dragState == D_VOLUME_DRAG) {
      if (phase == TouchPhase::Release) {
        if (lastVolumeRendered >= 0 && lastVolumeRendered != lastVolumeEnqueuedPct) {
          _volumeSink((int)lastVolumeRendered);
          lastVolumeEnqueuedPct = lastVolumeRendered;
        }
        dragState = D_IDLE;
        return true;
      }
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
      return true;
    }
    if (phase != TouchPhase::Press) return false;
    long volPct = hitTestVolume(x, y);
    if (volPct < 0) return false;
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
    return true;
  }

  bool wasLastInputAsync() { bool v = _lastInputWasAsync; _lastInputWasAsync = false; return v; }

  void resetDragState() {
    dragState = D_IDLE;
    _plView.resetDrag();
    pendingReleaseAt = 0;
#ifdef SERIAL_DEBUG
    _injectingDrag = false;
#endif
  }

  void invalidatePlaylist() { _plView.invalidate(); }

  void tickScroll(float dt) { _plView.tickScroll(dt); }

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
  // TASK-411 / ADR-059 D4 — PLEDIT is no longer rendered here. The view owns
  // the redraw gate, the scroll offset, the drag anchors, the velocity
  // integrator and the optimistic tap highlight; the source owns the Spotify
  // queue bookkeeping. Nothing is mirrored back into this class.
  PleditView         _plView;
  SpotifyQueueSource _queueSource;
  int lastThumbPx = -1;
  // TASK-402: separate diff-tracking sentinel for drawBufferBar() (WebRadio's
  // POSBAR reuse) — kept apart from lastThumbPx (Spotify's seek thumb) so the
  // two callers' partial-diff state can't cross-contaminate. -1 = next call
  // must do a full groove blit (no valid prior position to diff against).
  int lastBufThumbPx = -1;
  int lastSeconds = -1;
  // TASK-041 / A1.1 cache. -2 = never rendered (next repaint paints
  // sentinel); -1 = sentinel (no active device); 0..100 = real volume.
  int8_t lastVolumeRendered = -2;
  static constexpr int DIGIT_Y = 26;
  char lastTitle[264] = {0};  // artist(128) + " - "(3) + title(128) + gap(3) + NUL
  int titleScrollOffset = 0;
  unsigned long titleScrollDeadline = 0;
  // TASK-399: cached at _forceSetTitle() time, not recomputed per tick/frame.
  // titleTextPx <= TITLE_W means the static short-text path (Goal 3); the
  // period includes one separator run so the loop wraps seamlessly.
  int titleTextPx = 0;
  int titlePeriodPx = 0;
  // M-BOOT-UI §6 / ADR-055 decision 5: while active, setTitle() stashes
  // every caller's intent instead of drawing — none can paint over the
  // WiFi-down override, none need to know it exists.
  bool _wifiDownOverrideActive = false;
  // Lazily malloc'd (once, first outage, never freed) rather than a second
  // static sizeof(lastTitle)-byte member — the latter overflowed
  // cyd2usb_winamp_debug's .dram0.bss budget by more than this feature's
  // share of it (a real implementation-time constraint the design doc
  // didn't anticipate; full lastTitle-sized capacity is still needed for
  // correctness — see setTitle()'s stash comment — just not as static BSS).
  char* _wifiDownStash = nullptr;
  // Status indicator state survives a full repaint (TASK-018a). Set in
  // showDefaultScreen (PP_STOP) and printCurrentlyPlayingToScreen (PP_PLAY).
  SkinUV currentStatusUv = PP_STOP;

  // TASK-045 / ADR-016 §5-§10 — drag state machine for the volume slider.
  // dragState transitions: D_IDLE → D_VOLUME_DRAG on first touch inside
  // the volume slot; D_VOLUME_DRAG → D_IDLE on the loop iteration where
  // ts.touched() is false. lastVolumeEnqueuedMs/Pct debounce ACT_VOLUME
  // queue traffic to ~3/s. optimisticVolumeUntilMs gates spotifyLogic's
  // dedup against stale snapshot reads during/after drag.
  // TASK-411: D_PLEDIT_SCROLL / D_PLEDIT_SCROLL_DIRECT are retained as the
  // names this class reports over the serial debug surface, but they are never
  // assigned to dragState — PleditView is the single owner of the PLEDIT drag
  // (see dbgGet("dragState"), which derives them from _plView.dragMode()).
  enum DragState { D_IDLE = 0, D_VOLUME_DRAG, D_POSBAR_DRAG, D_PLEDIT_SCROLL, D_PLEDIT_SCROLL_DIRECT, D_TASKBAR_SCROLL };
  DragState dragState = D_IDLE;
  long _posbarDragCurrentMs = 0;
  // TASK-277: SCROLL_DEAD_ZONE_PX / SCROLL_SPEED_K_DEFAULT / PLEDIT_TAP_PX /
  // PLEDIT_TAP_MS live in touch/scrollTuning.h (shared with webRadioApp.h's
  // gesture copy) — same values, single definition site.
  // Taskbar scroll (M-TASKBAR-SCROLL, TASK-105b)
  int   _tbScrollOffset = 0;
  int   _tbDragStartY   = 0;
  int   _tbDragBaseOff  = 0;    // offset captured at press; positional 1:1 anchor
  float _tbScrollAccum  = 0.0f; // LP-filtered pixel displacement from _tbDragStartY
  bool  _tbIsScrolling  = false; // set once dead zone is exceeded; blocks tap-on-release
  static constexpr int   TB_SCROLL_DEAD_ZONE_PX = 3;
  static constexpr float TB_LP_ALPHA             = 0.4f;
  unsigned long lastVolumeEnqueuedMs = 0;
  int8_t lastVolumeEnqueuedPct = -2;
  unsigned long optimisticVolumeUntilMs = 0;
  static constexpr unsigned long VOLUME_DRAG_DEBOUNCE_MS = 300;
  static constexpr unsigned long VOLUME_OPTIMISTIC_HOLD_MS = 2000;
  // TASK-352: volume commit seam — the D_VOLUME_DRAG state machine (capture,
  // debounce, optimistic hold) above is mode-agnostic; only the commit action
  // is Spotify-coupled. Default wires the original ACT_VOLUME enqueue so
  // Spotify's behaviour is unchanged with zero wiring; WebRadio swaps this
  // via setVolumeSink() instead of duplicating the state machine.
  static void _defaultVolumeSink(int pct) {
    spotifyTask::enqueue(spotifyTask::ACT_VOLUME, (int32_t)pct);
  }
  void (*_volumeSink)(int) = &_defaultVolumeSink;

  // TASK-417 / ADR-059 D8: same seam shape as _volumeSink, for the same
  // reason — handleWinampInput()'s hit-test/optimistic-draw machinery is
  // mode-agnostic, only the commit action is Spotify-coupled. Without this,
  // a capability-gated Player mode would still dispatch straight to
  // spotifyTask::ACT_SHUFFLE/ACT_REPEAT/ACT_SEEK whenever the shared
  // dispatch path is exercised on its behalf (SERIAL_DEBUG's injectTouch(),
  // which runs handleWinampInput()'s Press phase regardless of the app
  // that's actually active — see cmdTap in main.cpp). Default wires the
  // original enqueue calls so Spotify's behaviour is unchanged with zero
  // wiring (T_PLR_18); Player swaps these in its own resume().
  static void _defaultShuffleSink(int next) {
    spotifyTask::enqueue(spotifyTask::ACT_SHUFFLE, (int32_t)next);
  }
  static void _defaultRepeatSink(int next) {
    spotifyTask::enqueue(spotifyTask::ACT_REPEAT, (int32_t)next);
  }
  static void _defaultSeekSink(long ms) {
    spotifyTask::enqueue(spotifyTask::ACT_SEEK, (int32_t)ms);
  }
  void (*_shuffleSink)(int)  = &_defaultShuffleSink;
  void (*_repeatSink)(int)   = &_defaultRepeatSink;
  void (*_seekSink)(long)    = &_defaultSeekSink;

  // TASK-417: per-mode transport capability mask (CAP_TRANSPORT|CAP_SEEK|
  // CAP_SHUFFLE|CAP_REPEAT). Defaults to the full set — matches Spotify,
  // which is always the first app initialised at boot (main.cpp inits
  // SpotifyApp before any persisted-mode switchApp() runs), so an early
  // repaintChrome() before any App::resume() has run still renders exactly
  // what it always has.
  uint8_t _playerCaps = CAP_TRANSPORT | CAP_SEEK | CAP_SHUFFLE | CAP_REPEAT;

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

  // M-BOOT-UI §6 / ADR-055 decision 5: unconditional title paint, bypassing
  // both the dedup and the WiFi-down guard — the two entry points that need
  // to force new content into lastTitle regardless of either.
  void _forceSetTitle(const char* text) {
    strncpy(lastTitle, text, sizeof(lastTitle) - 1);
    lastTitle[sizeof(lastTitle) - 1] = '\0';
    titleScrollOffset   = 0;
    titleScrollDeadline = millis() + TITLE_SCROLL_HOLD_MS;
    titleTextPx   = (int)strlen(lastTitle) * (GLYPH_W + 1);
    titlePeriodPx = titleTextPx + kTitleMarqueeSepLen * (GLYPH_W + 1);
    drawTitleText(0);
  }

  // TASK-399: endless loop once textPx > TITLE_W -- offset wraps modulo the
  // (text + separator) period instead of resetting off-screen right, so the
  // tail of one pass and the head of the next are visible in the same frame.
  void _tickMarquee() {
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

  // TASK-411: the loop itself now lives in winamp/skinBlit.h so pleditView.h
  // can use it without depending on this class. One implementation, two users.
  void blitSprite(int dstX, int dstY, const uint16_t *atlas, int atlasW, SkinUV uv) {
    skinBlitSprite(dstX, dstY, atlas, atlasW, uv);
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

  // TASK-053f/414: shared TLS-reset + force-poll reconnect action — the
  // Winamp logo tap (below, internal) and SpotifyApp's eject-tap intercept
  // (main.cpp, external) both perform the same recovery action and must
  // share its cooldown, so it lives here once rather than twice. No-op
  // (returns false) while the cooldown window is still active.
  bool tryReconnect() {
    if (millis() < logoTapCooldownMs) return false;
    spotifyTask::resetTls();
    spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
    logoTapCooldownMs = millis() + LOGO_TAP_COOLDOWN_MS;
    return true;
  }

  // M-WEBRADIO: public transport hit-test for apps other than SpotifyApp.
  int hitTestTransportPublic(int sx, int sy) { return hitTestTransport(sx, sy); }

  // TASK-417 / ADR-059 D8: public wrappers so LocalPlayerApp can hit-test
  // shuffle/repeat itself — real touches for Player never reach
  // handleWinampInput() (that entry point stays SpotifyApp-only, same as
  // hitTestTransportPublic() above), so Player's own handleInput() does its
  // own capability-gated hit-test + dispatch, mirroring how it already
  // calls hitTestTransportPublic() for PLAY/PAUSE/STOP.
  int  hitTestShufflePublic(int sx, int sy) { return hitTestShuffle(sx, sy); }
  int  hitTestRepeatPublic (int sx, int sy) { return hitTestRepeat (sx, sy); }
  // Geometry-only posbar zone check — unlike hitTestPosbar() (Spotify's,
  // gated on the shared `songDuration` global and returning a computed ms
  // offset) this only answers "is (sx,sy) inside the posbar groove", with
  // no duration dependency. Real duration-accurate scrubbing for local
  // files is TASK-419 (`setFilePos()`/`getAudioFileDuration()`); this task
  // only has to prove the zone is reachable (T_PLR_19), not accurate
  // (T_PLR_27/28).
  bool hitTestPosbarZonePublic(int sx, int sy) {
    const int py0 = originY + POSBAR_Y;
    const int py1 = py0 + POSBAR_BG.h;
    if (sy < py0 || sy >= py1) return false;
    const int px0 = originX + POSBAR_X;
    const int px1 = px0 + POSBAR_BG.w;
    return (sx >= px0 && sx < px1);
  }

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
      _plView.setSpeedK((val && *val) ? strtof(val, nullptr) : SCROLL_SPEED_K_DEFAULT);
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

public:
  // TASK-412 / ADR-059 D4: PLEDIT rendering and gesture ownership live in
  // winamp/pleditView.h behind PlaylistSource. This class's public surface is
  // the one PleditView instance shared by every caller (SpotifyApp via
  // drawPlaylist() below, WebRadioApp via the generic entry points here) —
  // there is exactly one PLEDIT visible at a time, so one view instance is
  // correct, not a per-app copy.

  bool pleditPress(int x, int y)   { return _plView.press(x, y, originX, originY); }
  void pleditMove(int y)           { _plView.move(y, originX, originY); }
  PlReleaseResult pleditRelease(PlaylistSource& src) { return _plView.release(src); }
  bool pleditDragging() const      { return _plView.dragging(); }
  PleditView::DragMode pleditDragMode() const { return _plView.dragMode(); }
  int   pleditScrollOffset()   const { return _plView.scrollOffset(); }
  float pleditScrollAccum()    const { return _plView.scrollAccum(); }
  float pleditScrollVelocity() const { return _plView.scrollVelocity(); }
  float pleditSpeedK()         const { return _plView.speedK(); }
  void  pleditSetSpeedK(float k)     { _plView.setSpeedK(k); }
  // D13: scroll the shared view to keep row idx visible (sources whose list
  // doesn't reset the scroll position on a content change still want the
  // current item scrolled into view on selection — see PleditView::scrollToRow).
  void  pleditScrollToRow(int idx)   { _plView.scrollToRow(idx); }
  // Cancel a live PLEDIT drag only — narrower than resetDragState() (which
  // also clears the host's OTHER gestures: volume/posbar/taskbar). For a
  // caller that must not drop an unrelated in-progress drag, e.g. WebRadio's
  // _play() cancelling only its own PLEDIT gesture on an auto-skip (TASK-277
  // QM-1-3), not a concurrent volume-slider drag.
  void  pleditResetDrag()            { _plView.resetDrag(); }
  // Force next draw() to repaint without a full invalidate() (no seqno-
  // sentinel clear, no onListReset(), no scroll reset) — for a host-side
  // change draw()'s own seqno/scroll tracking can't see on its own.
  void  pleditMarkDirty()            { _plView.markDirty(); }

  // Touch cool-down gate (D17): shared across every PLEDIT caller and every
  // other Winamp-chrome gesture, same object either app is driving at a time.
  bool touchCoolingDown() const { return millis() <= touchScreenCoolDownTime; }
  void armTouchCooldown(unsigned long ms) { touchScreenCoolDownTime = millis() + ms; }

  // Generic entry point: draw the shared PLEDIT for any PlaylistSource. Call
  // unconditionally from the main loop; the view returns immediately if the
  // source's seqno hasn't changed and nothing scrolled.
  void drawPlaylistFor(PlaylistSource& src) { _plView.draw(src, originX); }

  // Call unconditionally from the main loop; the view returns immediately if
  // the snapshot seqno has not changed and nothing scrolled.
  void drawPlaylist() {
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
};
