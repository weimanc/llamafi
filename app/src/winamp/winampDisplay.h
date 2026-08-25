#pragma once
// M3 — Winamp 2 main-window renderer for the CYD2USB.
// Inherits SpotifyDisplay directly (ADR-061 D9 step 3 / TASK-469 — flattened
// off `CheapYellowDisplay`; see winampDisplay.cpp for the absorbed setup
// boilerplate and the SpotifyDisplay pure-virtual stubs this class now
// supplies itself instead of inheriting them). The JPEG/SPIFFS/album-art
// plumbing that used to live in `CheapYellowDisplay` is gone entirely, not
// just compiled out — it was already dead in every Winamp build (M-NOART /
// TASK-062) and grep-confirmed to have no callers before this flatten.
// Self-contained per ADR-060 D0/SF.11 — substantive method bodies live in
// winampDisplay.cpp; trivial one-line getters/setters/delegators stay
// inline here, matching the established apps/*.h + .cpp pattern (e.g.
// apps/spotifyApp.h).

#include "spotifyDisplay.h"
#include "display/tft.h"
#include "touchScreen.h"   // touchSetup() — absorbed into displaySetup() below
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

// M-CODEQUAL C5 (TASK-461): the Winamp window (skin_layout.h's WINDOW_W, from
// the .wsz via bake_skin.py) and the app canvas (shell_layout.h's
// APP_CANVAS_W, == TASKBAR_X — the canvas ends where the taskbar begins) are
// independent facts that currently happen to share a value. Do not collapse
// them into one constant — that would couple the skin format to the shell
// layout and make a differently-sized future skin unrepresentable. This
// assert is the one place that records they coincide today; if it ever
// fires, that is a real divergence to resolve deliberately, not a bug in
// the assert.
static_assert(APP_CANVAS_W == WINDOW_W,
              "skin window and app canvas have diverged — intentional? see M-CODEQUAL C5");
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
  PlSrcKind kind() const override { return PlSrcKind::SpotifyQueue; }   // P2
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
  bool row(uint16_t idx, PlRow &out) override;

  uint32_t totalSec() override;

  // D10: total playlist time, "MM:SS" or "H:MM:SS" — the pre-extraction
  // bottom-bar overlay format, unchanged.
  void overlayText(char *buf, size_t bufSize) override;

  void onTap(uint16_t idx) override;

  // Fires when the renderer's gate actually consumes a seqno advance, not on
  // every snapshot write — the 1 Hz rate limit can defer one, and the advance
  // detector must stay in lockstep with what was drawn.
  void onListReset() override;

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

class WinampDisplay : public SpotifyDisplay {
public:
  // ADR-061 D9 step 3 / TASK-469: absorbs what CheapYellowDisplay::displaySetup
  // used to do for every backend (spotify_display assignment, touchSetup(),
  // 320x240 + 150x150 image-area geometry, tft.init()/setRotation/fillScreen)
  // plus what this class always added on top (byte-swap, chrome origin). The
  // old two-line boot log ("cyd display setup" then "winamp display setup")
  // collapses to one line — there is no longer a generic CYD stage distinct
  // from the Winamp one.
  void displaySetup(SpotifyArduino *spotifyObj) override;

  int chromeOriginX() const { return originX; }
  int chromeOriginY() const { return originY; }

  // Taskbar gesture API (M-TASKBAR-SCROLL) — called from appHandleInput().
  int  tbScrollOffset() const { return _tbScrollOffset; }
  bool tbIsDragging()   const { return dragState == D_TASKBAR_SCROLL; }
  // TASK-279 (DEV-3-1): scroll-start signal for the shell's press-highlight cancel —
  // tbGestureContinue() returns true only on ≥1-slot steps, so dead-zone-exceeded with
  // sub-slot travel is otherwise unobservable from the shell.
  bool tbIsScrolling()  const { return _tbIsScrolling; }

  void tbGesturePress(int y);

  // 1:1 positional scroll with LP filter. Returns true when offset changed.
  // Finger UP (negative dy) = higher-index apps scroll into view.
  bool tbGestureContinue(int y, int totalApps);

  // Returns true if gesture was a tap; fills *outAppIdx. Resets drag state.
  bool tbGestureEnd(int y, int totalApps, int* outAppIdx);

  void showDefaultScreen() override;

  // Force-paint all chrome elements over whatever's currently underneath
  // (e.g. a screenLog full-screen text layer). Does NOT reset state — use
  // showDefaultScreen for that. Idempotent given the cached state.
  void repaintChrome();

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
  void drawBufferBar(uint8_t pct);

  // TASK-349 — main-window time digits for WebRadio (stream play time, no
  // posbar thumb — WebRadio's posbar is drawBufferBar() above, not a seek
  // position). Spotify drives the digits via displayTrackProgress(); this is
  // the WebRadio-only entry into the same self-guarded drawTimeDigits().
  void updateTimeDigits(int seconds) { drawTimeDigits(seconds); }

  // TASK-252 — set the marquee title (shared: Spotify track + WebRadio station/
  // state). Redraws only on change; resets scroll + holds before scrolling. The
  // baked SKIN_GLYPH folds lowercase→uppercase, so callers needn't uppercase.
  void setTitle(const char* text);

  // TASK-252 — drive the title marquee scroll (WebRadio calls from its tick();
  // Spotify drives it internally via _tickMarquee in its own tick/input paths).
  void tickMarquee() { _tickMarquee(); }

  // M-BOOT-UI §6 / ADR-055 decision 5 — centralized WiFi-down marquee
  // override, driven by the loop()-level edge-triggered detector in
  // main.cpp. No-op if already active/inactive (idempotent under repeated
  // calls from an edge-triggered caller).
  void showWifiDownOverride();

  void clearWifiDownOverride();

  // TASK-041 / ADR-014 A1.5 — VOLUME slider renderer.
  // percent: 0..100 → KEYFRAME_0..KEYFRAME_4; <0 → KEYFRAME_NONE.
  // Always blits + updates the cache; caller dedup not required (the
  // updateCurrentlyPlaying integration in spotifyLogic.h still gates
  // on getLastVolumeRendered() to avoid the SPI traffic).
  void drawVolume(int percent) override;

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

  void drawShuffle(int on) override;
  void drawRepeat(int state) override;
  int8_t getLastShuffleRendered() const override { return lastShuffleRendered; }
  int8_t getLastRepeatRendered()  const override { return lastRepeatRendered;  }
  unsigned long getOptimisticShufRepUntil() const override { return optimisticShufRepUntilMs; }

  void displayTrackProgress(long progress, long duration) override;

  void printCurrentlyPlayingToScreen(CurrentlyPlaying currentlyPlaying) override;

  void checkForInput() override {
    // Retired — shell calls handleWinampInput() directly via SpotifyApp::handleInput().
    // Kept as a no-op override so the vtable slot isn't removed while
    // SpotifyDisplay* callers (WiFiManager flow) still compile.
  }

  // Shell-driven hit-test entry point. Called by SpotifyApp::handleInput().
  // phase/x/y pre-classified by the shell gesture tracker.
  // Returns true if Press was consumed (shell applies inter-gesture cooldown).
  bool handleWinampInput(TouchPhase phase, int x, int y);

  // TASK-492 (M-AUDIO-ENGINE OQ2's surviving half): the D_VOLUME_DRAG state
  // machine used to be implemented TWICE — once inline in handleWinampInput()
  // (Spotify's real-touch path) and once, nearly identically, right here in
  // handleVolumeGesturePublic() (WebRadio's narrow capture entry, TASK-352).
  // That duplication already cost one bug (TASK-406: a missing LOG_D line in
  // this copy, invisible until a test grepped for it) and a second,
  // previously-undiscovered divergence is closed here too — the Release
  // path's drag-end diagnostics (Serial.printf + _lastInputWasAsync) were
  // present in handleWinampInput()'s copy and absent from this one.
  // (_lastInputWasAsync has no reader anywhere in the tree — dead code — so
  // setting it here is a no-op either way, not a behaviour change; the log
  // line is a real, if minor, added diagnostic for this path.) The three
  // _volumeDrag*() helpers below are the ONE machine now; both
  // handleWinampInput() and this function call them, so a future edit to
  // one cannot silently diverge from the other again.
  //
  // Deliberately did NOT route WebRadio through the full handleWinampInput()
  // instead, even though ADR-059 D7's capability mask (TASK-417) means it
  // COULD now skip the Spotify-only zones — WebRadio has its own, separately
  // maintained dispatch for transport/PLEDIT/eject/vis (webRadioApp.cpp's
  // handleInput(), built from individual public hitTest*Public()/pledit*()
  // calls) specifically so it never touches handleWinampInput()'s own
  // _plView.dragging()/D_POSBAR_DRAG internals. Routing WebRadio's volume
  // touches through the FULL handleWinampInput() would reintroduce exactly
  // that hazard (the same _plView instance reachable via two independent
  // dispatch paths) for no benefit over sharing just the volume sub-machine.
  // Judgment call, not a design-doc mandate — recorded here rather than
  // made silently.

  // Press, once hit-tested valid (volPct >= 0) by the caller.
  void _volumeDragCapture(long volPct);

  // Move, while dragState == D_VOLUME_DRAG already.
  void _volumeDragContinue(int x);

  // Release, while dragState == D_VOLUME_DRAG. Leaves dragState == D_IDLE.
  void _volumeDragRelease();

  // Public capture entry for callers like WebRadio whose input path is
  // piecemeal hitTest*Public calls, not the full handleWinampInput()
  // dispatch — see the design note above. Press: hit-test only, ignored
  // (returns false) outside the slider. Move/Release: captured — consumes
  // unconditionally once a drag is live.
  bool handleVolumeGesturePublic(TouchPhase phase, int x, int y);

  bool wasLastInputAsync() { bool v = _lastInputWasAsync; _lastInputWasAsync = false; return v; }

  void resetDragState();

  void invalidatePlaylist() { _plView.invalidate(); }

  void tickScroll(float dt) { _plView.tickScroll(dt); }

#ifdef SERIAL_DEBUG
  // TASK-056d — public under SERIAL_DEBUG so cmdTap/cmdDrag in .ino can
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

  // ADR-061 D9 step 3 / TASK-469 — the SpotifyDisplay pure-virtual contract
  // members WinampDisplay used to get for free via `CheapYellowDisplay`.
  // Grep-confirmed (full app/src search, plus this class's own overrides)
  // that nothing calls clearImage/processImageInfo/displayImage/
  // markDisplayAsTagRead/markDisplayAsTagWritten in this build — the
  // album-art path was already dead per M-NOART/TASK-062, and no NFC
  // caller reaches these either. drawRefreshTokenMessage is the one real
  // exception (boot.cpp's refresh-token-mode screen) and is ported with
  // full fidelity, not stubbed. The dead ones are ported faithfully too
  // (not just no-op'd) where doing so is nearly free, so a future caller
  // reached through the SpotifyDisplay* interface sees the same behaviour
  // CheapYellowDisplay always gave it — see winampDisplay.cpp for exactly
  // what each one does and why.
  void clearImage() override;
  boolean processImageInfo(CurrentlyPlaying currentlyPlaying) override {
    (void)currentlyPlaying;
    return false;   // album-art path: dead in every Winamp build (M-NOART)
  }
  int displayImage() override { return 0; }   // album-art path: dead in every Winamp build (M-NOART)
  void markDisplayAsTagRead() override;
  void markDisplayAsTagWritten() override;
  void drawRefreshTokenMessage() override;

private:
  // ADR-061 D9 step 3 / TASK-469: this used to be "inherited via
  // CheapYellowDisplay isn't accessible (private), so WinampDisplay tracks
  // its own" — now there is no CheapYellowDisplay at all, so this is simply
  // WinampDisplay's own touch cool-down state, same as it always behaved.
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

  void updateSeekThumb(long ms);

  // M-BOOT-UI §6 / ADR-055 decision 5: unconditional title paint, bypassing
  // both the dedup and the WiFi-down guard — the two entry points that need
  // to force new content into lastTitle regardless of either.
  void _forceSetTitle(const char* text);

  // TASK-399: endless loop once textPx > TITLE_W -- offset wraps modulo the
  // (text + separator) period instead of resetting off-screen right, so the
  // tail of one pass and the head of the next are visible in the same frame.
  void _tickMarquee();

  void blitMainBackground() {
    tft.pushImage(originX, originY, SKIN_MAIN_BG_W, SKIN_MAIN_BG_H, SKIN_MAIN_BG);
  }

  // TASK-041 — VOLUME keyframe selection. 5-bucket linear partition of
  // 0..100 (each bucket 20%); negative percent → sentinel.
  static SkinUV pickKeyframe(int percent);
  static const char *keyframeName(int percent);

  // TASK-411: the loop itself now lives in winamp/skinBlit.h so pleditView.h
  // can use it without depending on this class. One implementation, two users.
  void blitSprite(int dstX, int dstY, const uint16_t *atlas, int atlasW, SkinUV uv) {
    skinBlitSprite(dstX, dstY, atlas, atlasW, uv);
  }

  void drawTransportButtons(int pressedIndex);

  // M5 hit-testing — screen coordinates from CYD28_TouchR.getPointScaled().
  // Buttons sit at window-y 88..106, so screen-y originY+88..originY+106.
  // Each is 23 px wide except NEXT (22). Returns 0..4 (PREV..NEXT) or -1.
  int hitTestTransport(int sx, int sy);

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
  long hitTestVolume(int sx, int sy);

  // Returns the seek position in ms for a tap on the posbar groove, or -1.
  // Requires songDuration > 0 (no-op for 204-no-track state).
  long hitTestPosbar(int sx, int sy);

public:
  // M-WEBRADIO: draw eject button from CBUTTONS atlas. pressed=true for depressed state.
  void drawEjectButton(bool pressed);

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
  bool tryReconnect();

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
  bool hitTestPosbarZonePublic(int sx, int sy);

#ifdef SERIAL_DEBUG
  // TASK-056d — synthetic touch injection (ADR-021 AC-2 resolution).
  // Mirrors the ts.touched() hit-test branch in checkForInput() but
  // bypasses ts.touched() / ts.getPointScaled(). Populates lastTouchResult
  // before returning so cmdTap can emit the per-region JSON fields.
  // Does NOT reset touchScreenCoolDownTime — synthetic inputs must not
  // block physical input after a test.
  // SERIAL_DEBUG injection: thin shims that call handleWinampInput() directly,
  // bypassing the shell gesture tracker (intentional — injection drives its own sequencing).
  void injectTouch(int sx, int sy) override;
  void injectRelease() override;

  // TASK-056g — IDebugExportable overrides (ADR-021 A1). Owner-dispatch
  // surface for cmdGet / cmdSet. Variables: cooldown, dragState,
  // optimisticVolume, songDuration.
  bool dbgGet(const char* var, char* buf, int len) const override;
  bool dbgSet(const char* var, const char* val) override;
#endif // SERIAL_DEBUG

private:
  void drawTimeDigits(int seconds, bool force = false);

  void drawStatusIndicator(SkinUV uv) {
    blitSprite(originX + PP_X, originY + PP_Y, SKIN_PLAYPAUS, SKIN_PLAYPAUS_W, uv);
  }

  // Draw lastTitle with a left-shift of `offset` pixels for marquee scroll.
  // Repaints the slot from background first so previous frame is wiped.
  void drawTitleText(int offset);

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
  // P2: which source last actually drove a PLEDIT draw (observed, not derived).
  PlSrcKind pleditLastSrcKind() const { return _plView.lastSrcKind(); }
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
  void drawPlaylist();
};
