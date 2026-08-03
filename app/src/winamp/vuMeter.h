#pragma once
// vuMeter.h — M6 synthetic VU meter + M-VIS tap-cycling visualizer.
//
// Synthesis recipe per ADR-009 (decoration, not real audio):
//   - 20 Hz tick (50 ms) gated by millis()
//   - target envelope = slow swell + noise floor + beat transient
//   - beat clock = dual oscillators ~100 BPM + ~152 BPM (3b); L/R split via slow LFO (±15%)
//   - per-bar inertia: spring-damper gives organic overshoot/settle on transients (3c)
//   - spectral tilt: rolloff peak drifts ±3 bars over ~14 s (3e)
//   - attack/release smoothing; decays to zero on !is_playing
//
// M-VIS (TASK-050a/b/c): tap vis area to cycle Atlas → WaveAtlas → VU → Blank → Atlas.
// VIS_ATLAS: 20 Hz playback of bar-height atlas from real Winamp footage (PROP-002/TASK-052d).
// VIS_WAVE_ATLAS: 20 Hz playback of waveform atlas from real Winamp footage (M-WAVE-ATLAS).
// VIS_SPECTRUM / VIS_WAVE (synthetic) removed from the shared cycle — superseded by atlases.
// TASK-387/M-WEBRADIO-REAL-VIS-SPECTRUM: VIS_SPECTRUM re-added to WebRadio's
// own tap-cycle only (Atlas → WaveAtlas → VU → Wave → Spectrum → Blank →
// Atlas), driven by real per-band energy there — see nextMode()'s
// appHasSpectrum param. TASK-388/M-WEBRADIO-REAL-VIS-WAVE: VIS_WAVE re-added
// the same way, but repointed to a real 19-column oscilloscope trace
// (tickWaveTrace()) — the old synthetic sine this slot used to mean is gone,
// not just unreachable (no call site left once WebRadio owns the slot;
// Spotify never reached VIS_WAVE either, before or after). Spotify's cycle
// is unchanged (Atlas → WaveAtlas → VU → Blank).
// All other modes derive from the same synthetic envelope (lLvl, rLvl, beatRaw).
//
// Vis area (window-local): x=24..99 (76px), y=43..58 (16px) — MAIN.BMP border excluded.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "gen/skin_layout.h"
#include "gen/vis_atlas.h"   // VIS_ATLAS_FRAMES, VIS_ATLAS_BARS, VIS_ATLAS[] — global scope
#include "gen/wave_atlas.h"  // WAVE_ATLAS_FRAMES, WAVE_ATLAS_COLS, WAVE_ATLAS[] — global scope
#include "perf.h"
#include "util/mathUtil.h"

extern TFT_eSPI tft;

namespace vu {

// Vis area geometry (window-local)
constexpr int RECT_X        = 24;
constexpr int LEFT_Y        = 43;
constexpr int RIGHT_Y       = 50;
constexpr int RECT_W        = 76;
constexpr int RECT_H        = 6;
constexpr int VIS_H         = 16;   // full active height y=43..58

// Spectrum geometry
constexpr int SPEC_BARS     = 19;
constexpr int SPEC_BAR_W    = 3;
constexpr int SPEC_BAR_STEP = 4;   // bar + gap

// Envelope timing
constexpr unsigned long TICK_MS          = 50;
constexpr unsigned long BEAT_PERIOD_A_MS = 600;   // ~100 BPM (first oscillator)
constexpr unsigned long BEAT_PERIOD_B_MS = 394;   // ~152 BPM (second; ~3:2 ratio)
constexpr unsigned long BEAT_DECAY_MS    = 80;
constexpr float MIX_BEAT  = 0.40f;
constexpr float MIX_NOISE = 0.18f;
constexpr float MIX_SWELL = 0.30f;
constexpr float ATTACK    = 0.45f;
constexpr float RELEASE   = 0.10f;

// VISCOLOR.TXT palette — row index r = pixel_y - LEFT_Y (row 0 = red/top, 15 = dark-green/bottom)
static constexpr uint16_t VIS_ROW_COLOR[16] = {
    0xE982, // row  0  y=43  (239, 49,16) red
    0xC942, // row  1  y=44  (206, 41,16)
    0xD2C0, // row  2  y=45  (214, 90, 0)
    0xD320, // row  3  y=46  (214,102, 0)
    0xD380, // row  4  y=47  (214,115, 0)
    0xC3C1, // row  5  y=48  (198,123, 8)
    0xDD23, // row  6  y=49  (222,165,24)
    0xD5A4, // row  7  y=50  (214,181,33)
    0xBEE5, // row  8  y=51  (189,222,41)
    0x96E4, // row  9  y=52  (148,222,33)
    0x2E62, // row 10  y=53  ( 41,206,16)
    0x35E2, // row 11  y=54  ( 50,190,16)
    0x3DA2, // row 12  y=55  ( 57,181,16)
    0x34E1, // row 13  y=56  ( 49,156, 8)
    0x2CA0, // row 14  y=57  ( 41,148, 0)
    0x1C21, // row 15  y=58  ( 24,132, 8) dark green
};
static constexpr uint16_t VIS_WAVE_COLOR = 0xFFFF;  // VISCOLOR[18] white
static constexpr uint16_t VIS_PEAK_COLOR = 0x94B2;  // VISCOLOR[23] grey

// --- Visualizer mode ---

enum VisMode { VIS_VU, VIS_SPECTRUM, VIS_ATLAS_MODE, VIS_WAVE, VIS_WAVE_ATLAS, VIS_BLANK };

// State accessors — inline statics, one instance per program
inline unsigned long &nextTickRef()     { static unsigned long t = 0; return t; }
inline float         &lLevelRef()       { static float v = 0.0f; return v; }
inline float         &rLevelRef()       { static float v = 0.0f; return v; }
inline int           &lLastWRef()       { static int v = -1; return v; }
inline int           &rLastWRef()       { static int v = -1; return v; }
inline VisMode       &s_modeRef()       { static VisMode m = VIS_ATLAS_MODE; return m; }
inline VisMode       &s_prevModeRef()   { static VisMode m = VIS_ATLAS_MODE; return m; }
inline VisMode        currentMode()     { return s_modeRef(); }
inline uint16_t      &atlasFrameRef()     { static uint16_t f = 0; return f; }
inline uint16_t      &waveAtlasFrameRef() { static uint16_t f = 0; return f; }

// PROP-005 rung 3 (EXP-018/TASK-387): real per-band energy for VIS_SPECTRUM.
// Band count matches SPEC_BARS (19, == VIS_ATLAS_BARS — the real-Winamp-
// footage atlas mode's bar count, i.e. what this firmware's spectrum-style
// vis already shows). Log-spaced 80 Hz-14 kHz — flash-resident (constexpr),
// zero DRAM cost (lands in .rodata, confirmed via EXP-018's nm check).
constexpr int SPEC_BAND_COUNT = 19;
static_assert(SPEC_BAND_COUNT == SPEC_BARS, "band table must match SPEC_BARS");
constexpr float SPEC_BAND_FREQ[SPEC_BAND_COUNT] = {
  80.0f, 106.6f, 142.0f, 189.2f, 252.1f, 335.9f, 447.5f, 596.2f, 794.3f,
  1058.3f, 1410.0f, 1878.6f, 2502.9f, 3334.7f, 4443.0f, 5919.5f, 7886.8f,
  10507.9f, 14000.0f,
};

// EXP-018's storage resolution: SERIAL_DEBUG-enabled builds have ~0 bytes of
// static-BSS headroom (EXP-015) — even one new 4-byte static pointer
// overflows the link. tickSpectrum's own specPeak/specH/specVel arrays
// already exist unconditionally (production code); promoting them from
// function-local statics to namespace-scope accessors (same pattern as
// lLevelRef()/rLevelRef()) reuses that existing storage instead of adding a
// channel — net new static bytes: zero. webRadioApp's audio_process_extern
// (pump task, real mode) becomes the writer via updateSpectrumBar() below;
// tickSpectrum itself is the writer in synthetic/Spotify mode — never both
// at once, same single-writer discipline as lLevelRef()/rLevelRef().
inline float  *specPeakRef()    { static float  a[SPEC_BARS] = {}; return a; }
inline float  *specHRef()       { static float  a[SPEC_BARS] = {}; return a; }
inline float  *specVelRef()     { static float  a[SPEC_BARS] = {}; return a; }

// Spring-damper (3c) + peak-fall smoothing for one spectrum bar, given a raw
// 0..1 target level. Shared by tickSpectrum's synthetic path and (real mode)
// webRadioApp's pump-task Goertzel writer — same formula either way, only
// the caller/cadence differs.
inline void updateSpectrumBar(int i, float lvl) {
  if (lvl > 1.0f) lvl = 1.0f;
  if (lvl < 0.0f) lvl = 0.0f;
  float *specH    = specHRef();
  float *specVel  = specVelRef();
  float *specPeak = specPeakRef();
  const float targetH = lvl * (float)VIS_H;
  specVel[i] = 0.7f * specVel[i] + 0.3f * (targetH - specH[i]);
  specH[i]  += specVel[i];
  if (specH[i] < 0.0f) specH[i] = 0.0f;
  if (specH[i] > (float)VIS_H) specH[i] = (float)VIS_H;

  constexpr float kInvVisH = 1.0f / (float)VIS_H;
  const float smoothLvl = specH[i] * kInvVisH;
  if (smoothLvl > specPeak[i]) specPeak[i] = smoothLvl;
  specPeak[i] -= kInvVisH;
  if (specPeak[i] < 0.0f) specPeak[i] = 0.0f;
}

// TASK-388/M-WEBRADIO-REAL-VIS-WAVE: real 19-column oscilloscope trace for
// VIS_WAVE. One column = one decimated sample (plain sub-sampling,
// idx = i*len/19) from the pump task's most recently decoded block, L
// channel only (same mono-adjacent simplification tickSpectrum's synthetic
// mode and the real Goertzel path both already made). int8_t (raw int16
// sample >> 8) — 19 new bytes, EXP-021-confirmed to fit measured
// dram0_0_seg headroom; re-verified fresh via .map diff at TASK-388
// implementation time (that report's own explicit warning: don't trust its
// snapshot as durable). Ported from the throwaway spike branch
// rnd/webradio-wave-spike (commits bcd2d0c, b698a2f) — ADR-056/EXP-021/022.
inline int8_t *waveTraceRef() { static int8_t buf[SPEC_BARS] = {}; return buf; }

// TASK-389: per-mode enable mask for the tap-cycle (Settings > WebRadio >
// Vis modes). VIS_BLANK has no bit — it's always enabled, the guaranteed
// fallback if a caller disables every other mode. Bit values are part of
// the call-site contract (webRadioApp.h builds the mask from g_settings),
// not persisted directly — settingsStorage.cpp owns the on-disk JSON keys.
enum ModeFlags : uint8_t {
  MF_ATLAS      = 1 << 0,
  MF_WAVE_ATLAS = 1 << 1,
  MF_VU         = 1 << 2,
  MF_SPECTRUM   = 1 << 3,
  MF_WAVE       = 1 << 4,
  MF_ALL        = MF_ATLAS | MF_WAVE_ATLAS | MF_VU | MF_SPECTRUM | MF_WAVE,
};

inline bool modeEnabled(VisMode m, uint8_t enabledMask) {
  switch (m) {
    case VIS_ATLAS_MODE: return enabledMask & MF_ATLAS;
    case VIS_WAVE_ATLAS: return enabledMask & MF_WAVE_ATLAS;
    case VIS_VU:         return enabledMask & MF_VU;
    case VIS_SPECTRUM:   return enabledMask & MF_SPECTRUM;
    case VIS_WAVE:        return enabledMask & MF_WAVE;
    default:              return true;   // VIS_BLANK (and anything else): always on
  }
}

// appHasSpectrum/appHasWave: per-caller branch (same shape as vu::tick()'s
// realAudio param) — TASK-387/TASK-388, M-WEBRADIO-REAL-VIS-SPECTRUM/WAVE
// Option B. WebRadio's tap-cycle gains real-data Spectrum and Wave stops;
// Spotify's stays untouched (ADR-009's synthetic-only reasoning for Spotify
// is not revisited here). VIS_SPECTRUM/VIS_WAVE always fall through to the
// next stop regardless of the flag — covers the case where mode state (a
// global) carried one of them over from WebRadio into a Spotify session;
// Spotify's own synthetic tickSpectrum path already renders correctly in
// that case (VIS_WAVE has no synthetic path left to fall back to — see the
// file-header comment — but Spotify's tap-cycle never lands there either
// way), this just keeps its own tap-cycle from ever landing there again.
//
// enabledMask (TASK-389): the single natural-next hop below is now wrapped
// in a bounded loop (at most one full lap of the 6-state ring) that skips
// any mode the mask disables. VIS_BLANK is unconditionally enabled, so the
// loop is guaranteed to terminate even with every bit clear — the cycle
// just settles on Blank. Spotify's call site passes the default MF_ALL
// (irrelevant anyway, since appHasSpectrum/appHasWave=false already keeps
// it off both) — only WebRadio's call site builds a real mask from g_settings.
inline void nextMode(bool appHasSpectrum = false, uint8_t enabledMask = MF_ALL,
                      bool appHasWave = false) {
  VisMode &m = s_modeRef();
  VisMode next = m;
  for (int i = 0; i < 7; i++) {
    switch (next) {
      case VIS_ATLAS_MODE: next = VIS_WAVE_ATLAS; break;
      case VIS_WAVE_ATLAS: next = VIS_VU;         break;
      case VIS_VU:         next = appHasWave ? VIS_WAVE
                                  : (appHasSpectrum ? VIS_SPECTRUM : VIS_BLANK); break;
      case VIS_WAVE:        next = appHasSpectrum ? VIS_SPECTRUM : VIS_BLANK; break;
      case VIS_SPECTRUM:   next = VIS_BLANK;      break;
      case VIS_BLANK:      next = VIS_ATLAS_MODE; break;
      default:              next = VIS_ATLAS_MODE; break;
    }
    if (modeEnabled(next, enabledMask)) break;
  }
  m = next;
}

// Restore SKIN_MAIN_BG pixels for the full 76×16 vis area.
// Called on mode entry (VU, Blank) and every tick (Spectrum, Wave).
inline void blitVisBackground(int originX, int originY, const uint16_t *mainBg) {
  if (!mainBg) return;
  tft.startWrite();
  for (int row = 0; row < VIS_H; row++) {
    tft.pushImage(originX + RECT_X, originY + LEFT_Y + row, RECT_W, 1,
                  mainBg + (LEFT_Y + row) * SKIN_MAIN_BG_W + RECT_X);
  }
  tft.endWrite();
}

// --- Per-mode renderers ---

inline uint16_t levelColor(float level) {
  if (level < 0.50f) return TFT_GREEN;
  if (level < 0.80f) return TFT_YELLOW;
  return TFT_RED;
}

inline void tickVU(int originX, int originY, const uint16_t *mainBg,
                   float lLvl, float rLvl) {
  int lW = (int)(lLvl * RECT_W + 0.5f);
  int rW = (int)(rLvl * RECT_W + 0.5f);
  if (lW < 0) lW = 0; if (lW > RECT_W) lW = RECT_W;
  if (rW < 0) rW = 0; if (rW > RECT_W) rW = RECT_W;

  int &lLastW = lLastWRef();
  int &rLastW = rLastWRef();
  const bool lDirty = (lW != lLastW);
  const bool rDirty = (rW != rLastW);

  if (lDirty || rDirty) {
    const int lx = originX + RECT_X;
    const int ly = originY + LEFT_Y;
    const int ry = originY + RIGHT_Y;
    tft.startWrite();
    if (lDirty) {
      const uint16_t c = levelColor(lLvl);
      if (lW > 0) tft.fillRect(lx, ly, lW, RECT_H, c);
      if (lW < RECT_W) {
        if (mainBg) {
          for (int row = 0; row < RECT_H; row++)
            tft.pushImage(lx + lW, ly + row, RECT_W - lW, 1,
                          mainBg + (LEFT_Y + row) * SKIN_MAIN_BG_W + RECT_X + lW);
        } else {
          tft.fillRect(lx + lW, ly, RECT_W - lW, RECT_H, TFT_BLACK);
        }
      }
      lLastW = lW;
    }
    if (rDirty) {
      const uint16_t c = levelColor(rLvl);
      if (rW > 0) tft.fillRect(lx, ry, rW, RECT_H, c);
      if (rW < RECT_W) {
        if (mainBg) {
          for (int row = 0; row < RECT_H; row++)
            tft.pushImage(lx + rW, ry + row, RECT_W - rW, 1,
                          mainBg + (RIGHT_Y + row) * SKIN_MAIN_BG_W + RECT_X + rW);
        } else {
          tft.fillRect(lx + rW, ry, RECT_W - rW, RECT_H, TFT_BLACK);
        }
      }
      rLastW = rW;
    }
    tft.endWrite();
  }
}

// Spectrum: 19 bars × 3px wide, 1px gap. Row colour by absolute y position.
// Peak dots: 3px wide grey, decay 1 row per tick (~50 ms/row).
// 3c: per-bar spring-damper inertia — bars overshoot and settle on transients.
// 3e: spectral tilt LFO — rolloff peak drifts ±3 bars over ~14 s.
// PROP-005 rung 3 (EXP-018/TASK-387): realAudio=true skips the per-bar
// compute below entirely and just reads specH()/specPeak() as already
// fresh — real mode's writer is webRadioApp's audio_process_extern, calling
// updateSpectrumBar() per band per decoded block on the pump task (see the
// accessor comments above for why this reuses storage instead of adding a
// channel). Synthetic mode (Spotify, or WebRadio pre-play) is unchanged:
// still computes envelope/shape/tilt/boost and calls updateSpectrumBar()
// itself, on the UI thread, exactly as before this refactor.
inline void tickSpectrum(int originX, int originY, const uint16_t *mainBg,
                          float lLvl, float rLvl, float beatRaw, long elapsed,
                          bool realAudio = false) {
  static int8_t lastBinH[SPEC_BARS]    = {-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};
  static int8_t lastPeakRow[SPEC_BARS] = {-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};

  const float envelope = (lLvl + rLvl) * 0.5f;
  // 3e: rolloff peak drifts ±3 bars over ~14 s (synthetic mode only)
  const float tilt = lut_sin((float)elapsed * (1.0f / 14000.0f)) * 3.0f;
  float *specH    = specHRef();
  float *specPeak = specPeakRef();

  // Compute all bars; dedup: skip SPI if nothing changed
  int8_t newBinH[SPEC_BARS];
  int8_t newPeakRow[SPEC_BARS];
  bool dirty = false;

  for (int i = 0; i < SPEC_BARS; i++) {
    if (!realAudio) {
      float ei = (float)i - tilt;                        // 3e: tilt shifts rolloff peak
      if (ei < 0.0f) ei = 0.0f; if (ei > 18.0f) ei = 18.0f;
      constexpr float kInv18 = 1.0f / 18.0f;
      const float shape = 1.0f - (ei * kInv18) * 0.6f;  // pink-noise rolloff, tilted
      const float boost = (i < 4) ? beatRaw * 0.8f : 0.0f;
      const float lvl = envelope * shape * (1.0f + boost);
      updateSpectrumBar(i, lvl);
    }
    // else: real mode already updated specH/specVel/specPeak on the pump task.

    newBinH[i] = (int8_t)(specH[i] + 0.5f);
    int pr = (int)((1.0f - specPeak[i]) * VIS_H);
    if (pr < 0) pr = 0;
    if (pr >= VIS_H) pr = VIS_H - 1;
    newPeakRow[i] = (int8_t)pr;

    if (newBinH[i] != lastBinH[i] || newPeakRow[i] != lastPeakRow[i]) dirty = true;
  }

  if (!dirty) return;

  blitVisBackground(originX, originY, mainBg);

  tft.startWrite();
  for (int i = 0; i < SPEC_BARS; i++) {
    const int barX = originX + RECT_X + i * SPEC_BAR_STEP;
    const int bh   = newBinH[i];
    for (int r = VIS_H - bh; r < VIS_H; r++) {
      tft.drawFastHLine(barX, originY + LEFT_Y + r, SPEC_BAR_W, VIS_ROW_COLOR[r]);
    }
    tft.drawFastHLine(barX, originY + LEFT_Y + newPeakRow[i], SPEC_BAR_W, VIS_PEAK_COLOR);
    lastBinH[i]    = newBinH[i];
    lastPeakRow[i] = newPeakRow[i];
  }
  tft.endWrite();
}

// Atlas: play back pre-extracted bar heights from real Winamp vis footage.
// 20 Hz frame advance; freeze on !is_playing; loop mod VIS_ATLAS_FRAMES.
// Peak dots: gravity-accelerated fall (0.08 px/frame²), floor at 1px, colour VIS_PEAK_COLOR.
inline void tickAtlas(int originX, int originY, const uint16_t *mainBg, bool playing) {
  static float atlasPeak[SPEC_BARS]    = {};   // peak height, bar-height units (0..VIS_H)
  static float atlasPeakVel[SPEC_BARS] = {};   // fall velocity (px/frame), gravity-driven

  uint16_t &frame = atlasFrameRef();
  if (playing) frame = (frame + 1) % VIS_ATLAS_FRAMES;

  blitVisBackground(originX, originY, mainBg);

  tft.startWrite();
  for (int i = 0; i < SPEC_BARS; i++) {
    const float bh   = (float)VIS_ATLAS[frame][i];
    const int   barX = originX + RECT_X + i * SPEC_BAR_STEP;

    // Gravity peak tracker: snap up instantly, accelerating fall
    if (bh >= atlasPeak[i]) {
      atlasPeak[i]    = bh;
      atlasPeakVel[i] = 0.0f;
    } else {
      atlasPeakVel[i] += 0.08f;
      atlasPeak[i]    -= atlasPeakVel[i];
      if (atlasPeak[i] < 1.0f) atlasPeak[i] = 1.0f;  // floor: never below 1px bar
    }
    int pr = (int)(VIS_H - atlasPeak[i] + 0.5f);
    if (pr < 0) pr = 0;
    if (pr >= VIS_H) pr = VIS_H - 1;

    // Draw bar
    const int bhi = (int)bh;
    for (int r = VIS_H - bhi; r < VIS_H; r++) {
      tft.drawFastHLine(barX, originY + LEFT_Y + r, SPEC_BAR_W, VIS_ROW_COLOR[r]);
    }
    // Draw peak dot (on top of bar if bar reaches peak row)
    tft.drawFastHLine(barX, originY + LEFT_Y + pr, SPEC_BAR_W, VIS_PEAK_COLOR);
  }
  tft.endWrite();
}

// TASK-388/M-WEBRADIO-REAL-VIS-WAVE: real 19-column oscilloscope trace.
// Reads waveTraceRef() (already fresh — written by webRadioApp's
// audio_process_extern on the pump task, same single-writer discipline as
// tickSpectrum/updateSpectrumBar) and draws it as a connected line between
// columns, oscilloscope-style. Ported from rnd/webradio-wave-spike
// (bcd2d0c, b698a2f) — full redraw every call, no dirty-diff (spike
// simplicity; the old synthetic sine this replaces did the same, so this
// isn't a regression in that respect — optimize only if a real cost
// problem shows up, per the design doc's exit criteria).
inline void tickWaveTrace(int originX, int originY, const uint16_t *mainBg) {
  blitVisBackground(originX, originY, mainBg);
  int8_t *buf = waveTraceRef();
  const int centreY = originY + LEFT_Y + (VIS_H - 1) / 2;
  const int yMin    = originY + LEFT_Y;
  const int yMax    = originY + LEFT_Y + VIS_H - 1;

  int prevX = originX + RECT_X;
  int prevY = constrain(centreY + ((int)buf[0] * (VIS_H / 2)) / 127, yMin, yMax);

  tft.startWrite();
  for (int i = 1; i < SPEC_BARS; i++) {
    const int x = originX + RECT_X + i * SPEC_BAR_STEP;
    const int y = constrain(centreY + ((int)buf[i] * (VIS_H / 2)) / 127, yMin, yMax);
    tft.drawLine(prevX, prevY, x, y, VIS_WAVE_COLOR);
    prevX = x;
    prevY = y;
  }
  tft.endWrite();
}

// WaveAtlas: play back pre-extracted waveform rows from real Winamp footage.
// 20 Hz frame advance (continuous — not gated on playing). White vertical fill between samples.
// prevY initialised from row[0], not centreY — avoids left-edge spike artefact.
inline void tickWaveAtlas(int originX, int originY, const uint16_t *mainBg) {
  uint16_t &frame = waveAtlasFrameRef();
  static uint32_t lastMs = 0;

  const uint32_t now = millis();
  if (now - lastMs >= 50) {
    lastMs = now;
    frame = (frame + 1) % WAVE_ATLAS_FRAMES;
  }

  blitVisBackground(originX, originY, mainBg);

  const uint8_t *row = WAVE_ATLAS[frame];
  const int yBase = originY + LEFT_Y + 1;
  const int yMin  = yBase;
  const int yMax  = yBase + VIS_H - 1;

  int prevY = constrain(yBase + (int)row[0], yMin, yMax);

  tft.startWrite();
  for (int x = 0; x < RECT_W; x++) {
    int y = constrain(yBase + (int)row[x], yMin, yMax);
    const int yTop = min(y, prevY);
    const int yBot = max(y, prevY);
    tft.drawFastVLine(originX + RECT_X + x, yTop, yBot - yTop + 1, VIS_WAVE_COLOR);
    prevY = y;
  }
  tft.endWrite();
}

// --- Main entry point ---

// TASK-350: caller supplies (playing, elapsedMs) instead of this reaching
// into spotifyTask state directly — decouples the synthesis (still ADR-009
// mock) from Spotify so WebRadio can drive it with its own state without
// dancing to a stale Spotify snapshot. Spotify's call site (main.cpp) reads
// its own snapshot + songStartMillis and passes them in, byte-identical to
// the old inline behaviour.
// PROP-005 rung 2 (EXP-016): realAudio=true skips the synthetic swell/beat/
// noise computation below and trusts lLevelRef()/rLevelRef() as already
// fresh — webRadioApp's audio_process_extern hook writes real peak-envelope
// values directly into those same statics on the pump task (single-writer
// while WebRadio real-mode is active; vu::tick() itself is the only other
// writer, active only in synthetic/Spotify mode — never both at once).
// Reusing the existing statics instead of adding new ones matters here:
// SERIAL_DEBUG-enabled builds have ~0 bytes of static-BSS headroom (EXP-015).
inline void tick(int originX, int originY, const uint16_t *mainBg, bool playing, long elapsedMs,
                 bool realAudio = false) {
  const unsigned long now = millis();
  if (now < nextTickRef()) return;
  nextTickRef() = now + TICK_MS;
  const unsigned long t0 = millis();

  long  elapsed  = playing ? elapsedMs : 0L;
  float beatRaw  = 0.0f;
  float &lLvl = lLevelRef();
  float &rLvl = rLevelRef();

  if (realAudio) {
    if (!playing) { lLvl = 0.0f; rLvl = 0.0f; }
    // else: lLvl/rLvl already hold the current real envelope — nothing to do.
  } else {
    float target = 0.0f;
    if (playing) {
      const float swell = MIX_SWELL * (1.0f + lut_sin((float)elapsed * (1.0f / 3000.0f)));
      const float noise = (random(0, 1000) / 1000.0f) * MIX_NOISE;
      // 3b: dual beat oscillators ~100 BPM + ~152 BPM — removes flat periodic regularity
      float beatA = 0.0f, beatB = 0.0f;
      const long phaseA = elapsed % (long)BEAT_PERIOD_A_MS;
      if (phaseA < (long)BEAT_DECAY_MS)
        beatA = 1.0f - (float)phaseA / (float)BEAT_DECAY_MS;
      const long phaseB = elapsed % (long)BEAT_PERIOD_B_MS;
      if (phaseB < (long)BEAT_DECAY_MS)
        beatB = 1.0f - (float)phaseB / (float)BEAT_DECAY_MS;
      beatRaw = beatA * 0.6f + beatB * 0.4f;
      if (beatRaw > 1.0f) beatRaw = 1.0f;
      target = swell + noise + beatRaw * MIX_BEAT;
      if (target > 1.0f) target = 1.0f;
    }

    const float lfo = lut_sin((float)now * (1.0f / 700.0f)) * 0.15f;
    float lTarget = target * (1.0f + lfo);
    float rTarget = target * (1.0f - lfo);
    if (lTarget > 1.0f) lTarget = 1.0f; if (lTarget < 0.0f) lTarget = 0.0f;
    if (rTarget > 1.0f) rTarget = 1.0f; if (rTarget < 0.0f) rTarget = 0.0f;

    lLvl += (lTarget - lLvl) * ((lTarget > lLvl) ? ATTACK : RELEASE);
    rLvl += (rTarget - rLvl) * ((rTarget > rLvl) ? ATTACK : RELEASE);
  }

  // Mode transition: restore vis background and reset caches when entering
  // VU or Blank mode; Spectrum/Atlas/Wave blit inside their own tick functions.
  const VisMode cur = s_modeRef();
  if (cur != s_prevModeRef()) {
    if (cur == VIS_VU || cur == VIS_BLANK)
      blitVisBackground(originX, originY, mainBg);
    if (cur == VIS_VU) { lLastWRef() = -1; rLastWRef() = -1; }
    s_prevModeRef() = cur;
  }

  switch (cur) {
    case VIS_VU:         tickVU(originX, originY, mainBg, lLvl, rLvl); break;
    case VIS_SPECTRUM:   tickSpectrum(originX, originY, mainBg, lLvl, rLvl, beatRaw, elapsed, realAudio); break;
    case VIS_ATLAS_MODE: tickAtlas(originX, originY, mainBg, playing); break;
    case VIS_WAVE:       tickWaveTrace(originX, originY, mainBg); break;
    case VIS_WAVE_ATLAS: tickWaveAtlas(originX, originY, mainBg); break;
    case VIS_BLANK:      break;  // background blitted on mode entry above
  }

  perf::record("vu.tick", millis() - t0);
}

// Reset cached state — call on showDefaultScreen or any full repaint.
// Forces the next tick to repaint from scratch regardless of cached widths.
inline void invalidate() {
  lLastWRef()    = -1;
  rLastWRef()    = -1;
  s_prevModeRef() = static_cast<VisMode>(99);  // trigger mode-entry logic on next tick
}

}  // namespace vu
