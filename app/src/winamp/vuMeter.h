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
// VIS_SPECTRUM / VIS_WAVE (synthetic) removed from cycle — superseded by atlases.
// All other modes derive from the same synthetic envelope (lLvl, rLvl, beatRaw).
//
// Vis area (window-local): x=24..99 (76px), y=43..58 (16px) — MAIN.BMP border excluded.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "gen/skin_layout.h"
#include "gen/vis_atlas.h"   // VIS_ATLAS_FRAMES, VIS_ATLAS_BARS, VIS_ATLAS[] — global scope
#include "gen/wave_atlas.h"  // WAVE_ATLAS_FRAMES, WAVE_ATLAS_COLS, WAVE_ATLAS[] — global scope
#include "perf.h"
#include "spotifyTask.h"

extern TFT_eSPI tft;
extern long     songStartMillis;
extern long     songDuration;

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
inline uint16_t      &atlasFrameRef()     { static uint16_t f = 0; return f; }
inline uint16_t      &waveAtlasFrameRef() { static uint16_t f = 0; return f; }

inline void nextMode() {
  VisMode &m = s_modeRef();
  switch (m) {
    case VIS_ATLAS_MODE: m = VIS_WAVE_ATLAS; break;
    case VIS_WAVE_ATLAS: m = VIS_VU;         break;
    case VIS_VU:         m = VIS_BLANK;      break;
    case VIS_BLANK:      m = VIS_ATLAS_MODE; break;
    default:             m = VIS_ATLAS_MODE; break;
  }
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
inline void tickSpectrum(int originX, int originY, const uint16_t *mainBg,
                          float lLvl, float rLvl, float beatRaw, long elapsed) {
  static float  specPeak[SPEC_BARS]    = {};
  static float  specH[SPEC_BARS]       = {};   // 3c: smoothed bar heights (0..VIS_H)
  static float  specVel[SPEC_BARS]     = {};   // 3c: bar velocity
  static int8_t lastBinH[SPEC_BARS]    = {-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};
  static int8_t lastPeakRow[SPEC_BARS] = {-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};

  const float envelope = (lLvl + rLvl) * 0.5f;
  // 3e: rolloff peak drifts ±3 bars over ~14 s
  const float tilt = sinf((float)elapsed / 14000.0f) * 3.0f;

  // Compute all bars; dedup: skip SPI if nothing changed
  int8_t newBinH[SPEC_BARS];
  int8_t newPeakRow[SPEC_BARS];
  bool dirty = false;

  for (int i = 0; i < SPEC_BARS; i++) {
    float ei = (float)i - tilt;                        // 3e: tilt shifts rolloff peak
    if (ei < 0.0f) ei = 0.0f; if (ei > 18.0f) ei = 18.0f;
    const float shape = 1.0f - (ei / 18.0f) * 0.6f;  // pink-noise rolloff, tilted
    const float boost = (i < 4) ? beatRaw * 0.8f : 0.0f;
    float lvl = envelope * shape * (1.0f + boost);
    if (lvl > 1.0f) lvl = 1.0f;
    if (lvl < 0.0f) lvl = 0.0f;

    // 3c: spring-damper inertia — bars converge toward target over 2–3 ticks
    const float targetH = lvl * (float)VIS_H;
    specVel[i] = 0.7f * specVel[i] + 0.3f * (targetH - specH[i]);
    specH[i]  += specVel[i];
    if (specH[i] < 0.0f) specH[i] = 0.0f;
    if (specH[i] > (float)VIS_H) specH[i] = (float)VIS_H;

    const float smoothLvl = specH[i] / (float)VIS_H;
    if (smoothLvl > specPeak[i]) specPeak[i] = smoothLvl;
    specPeak[i] -= 1.0f / VIS_H;
    if (specPeak[i] < 0.0f) specPeak[i] = 0.0f;

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

// Wave: phase-advancing sine, vertical fill between consecutive samples.
// Colour: white (0xFFFF). Flat line at midline when paused (lLvl → 0).
inline void tickWave(int originX, int originY, const uint16_t *mainBg, float lLvl) {
  static float wavePhase = 0.0f;
  static constexpr float WAVE_CYCLES = 2.5f;
  static constexpr float TWO_PI_F    = 6.28318530f;

  blitVisBackground(originX, originY, mainBg);

  const int centreY = originY + LEFT_Y + (VIS_H - 1) / 2;  // y = originY + 50
  const int yMin    = originY + LEFT_Y;
  const int yMax    = originY + LEFT_Y + VIS_H - 1;
  int prevY = centreY;

  tft.startWrite();
  for (int x = 0; x < RECT_W; x++) {
    int y = centreY + (int)roundf(lLvl * 5.0f *
                sinf(wavePhase + x * WAVE_CYCLES * TWO_PI_F / RECT_W));
    if (y < yMin) y = yMin;
    if (y > yMax) y = yMax;

    const int yTop = (x == 0) ? y : (y < prevY ? y : prevY);
    const int yBot = (x == 0) ? y : (y > prevY ? y : prevY);
    tft.drawFastVLine(originX + RECT_X + x, yTop, yBot - yTop + 1, VIS_WAVE_COLOR);
    prevY = y;
  }
  tft.endWrite();

  wavePhase += 0.3f;
  if (wavePhase > TWO_PI_F * 32.0f) wavePhase -= TWO_PI_F * 32.0f;
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

inline void tick(int originX, int originY, const uint16_t *mainBg = nullptr) {
  const unsigned long now = millis();
  if (now < nextTickRef()) return;
  nextTickRef() = now + TICK_MS;
  const unsigned long t0 = millis();

  spotifyTask::Snapshot snap;
  spotifyTask::copySnapshot(&snap);
  const bool playing = snap.valid && snap.isPlaying && songStartMillis != 0;

  long  elapsed  = playing ? (long)(now - (unsigned long)songStartMillis) : 0L;
  float target   = 0.0f;
  float beatRaw  = 0.0f;
  if (playing) {
    const float swell = MIX_SWELL * (1.0f + sinf(elapsed / 3000.0f));
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

  const float lfo = sinf(now / 700.0f) * 0.15f;
  float lTarget = target * (1.0f + lfo);
  float rTarget = target * (1.0f - lfo);
  if (lTarget > 1.0f) lTarget = 1.0f; if (lTarget < 0.0f) lTarget = 0.0f;
  if (rTarget > 1.0f) rTarget = 1.0f; if (rTarget < 0.0f) rTarget = 0.0f;

  float &lLvl = lLevelRef();
  float &rLvl = rLevelRef();
  lLvl += (lTarget - lLvl) * ((lTarget > lLvl) ? ATTACK : RELEASE);
  rLvl += (rTarget - rLvl) * ((rTarget > rLvl) ? ATTACK : RELEASE);

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
    case VIS_SPECTRUM:   tickSpectrum(originX, originY, mainBg, lLvl, rLvl, beatRaw, elapsed); break;
    case VIS_ATLAS_MODE: tickAtlas(originX, originY, mainBg, playing); break;
    case VIS_WAVE:       tickWave(originX, originY, mainBg, lLvl); break;
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
