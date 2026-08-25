#pragma once
// aquariumApp.h — ASCII Aquarium port (M-AQUARIUM). Self-contained per
// D0/SF.11 (M-SRCLAYOUT Stage E / TASK-471) — method bodies live in
// aquariumApp.cpp.
// Source: resource/ASCII_Aquarium/ASCII_Aquarium_CYD.ino v1.67
// Decisions: ADR-031 (275px sprite, 8-bit, Preferences dropped).

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <time.h>
#include <cstring>
#include <cmath>
#include "appShell.h"
#include "settingsStorage.h"
#include "util/mathUtil.h"
#include "util/timeFmt.h"   // WIRE2-G2: clockHour()

#include "display/tft.h"

class AquariumApp : public App {
public:
    // TASK-518 (P4): no hasInFlightOp() override — pure local animation. The
    // only non-render work is the sprite alloc, which is synchronous inside
    // init()/the retry tick, so it can never be observed as "in flight" from
    // the loop task. Inherits the App default (false), which is true.

    void init() override;
    void resume() override;
    void suspend() override {
        _canvas.deleteSprite();
        _spriteReady = false;
    }
    void tick() override;
    bool handleInput(TouchPhase phase, int x, int y) override;

#ifdef SERIAL_DEBUG
    bool dbgGet(const char* var, char* buf, int len) const;
#endif

private:
    // ── Constants ──────────────────────────────────────────────────────────
    // M-CODEQUAL C5 (TASK-461): was an independent `275` literal; now the one
    // canonical source (gen/shell_layout.h's APP_CANVAS_W, visible here via
    // appShell.h's include of it above).
    static constexpr int   AQ_CANVAS_W            = APP_CANVAS_W;
    static constexpr int   AQ_CANVAS_H            = 240;  // informational; no single sprite this size
    static constexpr int   AQ_STRIP_H             = 40;
    static constexpr int   AQ_STRIP_COUNT         = 6;
    static constexpr int   AQ_SEA_LEVEL_Y         = 152;
    static constexpr int   AQ_FISH_COUNT          = 16;
    static constexpr int   AQ_FISH_POOL_MAX       = 16;
    static constexpr int   AQ_BUBBLE_COUNT        = 10;
    static constexpr int   AQ_BUBBLE_POOL_MAX     = 10;
    static constexpr int   AQ_FLAKE_MAX           = 16;
    static constexpr int   AQ_OCTOPUS_FREQ        = 1;
    static constexpr int   AQ_SEAHORSE_FREQ       = 1;
    static constexpr float AQ_SWAY                = 1.10f;
    static constexpr float AQ_SEAWEED_LEN         = 1.35f;
    static constexpr float AQ_SEAWEED_RAND        = 0.35f;
    static constexpr int   AQ_BACKGROUND_GRADIENT_H = AQ_STRIP_H;  // 40 = strip 0 exactly
    static constexpr int   AQ_CLOCK_Y             = 4;
    static constexpr uint16_t AQ_CLOCK_COLOR      = 0xFFFF;
    static constexpr uint16_t AQ_BG_COLOR         = 0x0000;
    static constexpr int   AQ_SEAWEED_ROOTS       = 12;
    static constexpr int   kSeaweedPhases         = 32;
    static constexpr int   kSeaweedSegs           = 8;
    static constexpr float kSeaweedPhasesPerRad   = kSeaweedPhases / 6.28318f;
    static constexpr int   AQ_GLYPH_COUNT         = 12;
    static constexpr size_t AQ_GLYPH_BUF          = 28;

    // Crab constants (M-AQUARIUM-CRAB)
    static constexpr int   CRAB_CHAR_W           = 6;
    static constexpr int   CRAB_CHAR_H           = 14;
    static constexpr int   CRAB_W_PX             = 7 * CRAB_CHAR_W;
    static constexpr int   CRAB_LEG_OVERLAP_PX   = 8;
    static constexpr int   CRAB_BOTTOM_MARGIN_PX = 4;
    static constexpr int   CRAB_FOOT_PX          = CRAB_BOTTOM_MARGIN_PX + CRAB_CHAR_H + CRAB_LEG_OVERLAP_PX;
    static constexpr int   CRAB_Y                = AQ_CANVAS_H - CRAB_FOOT_PX;
    static constexpr int   CRAB_Y_MIN            = CRAB_Y - 4;
    static constexpr int   CRAB_Y_MAX            = CRAB_Y;
    static constexpr float CRAB_VY_MAX_PX_S      = 1.0f;
    static constexpr int   CRAB_MARGIN_PX        = 8;
    static constexpr float CRAB_SPEED_PX_S       = 12.0f;
    static constexpr int   CRAB_PINCH_RANGE_PX   = 45;
    static constexpr int   CRAB_BOTTOM_ZONE_Y    = AQ_CANVAS_H - 80;
    static constexpr uint32_t CRAB_WALK_STEP_MS  = 200;
    static constexpr uint32_t CRAB_PINCH_FRAME_MS = 180;
    static constexpr uint32_t CRAB_PINCH_HOLD_MS  = 200;
    static constexpr int   CRAB_CLAW_RISE_PX     = 3;
    static constexpr float CRAB_CUTE_CHANCE      = 0.0004f;
    static constexpr uint32_t CRAB_CUTE_BLINK_MS = 375;
    static constexpr uint32_t CRAB_CUTE_IDLE_MS  = 1500;
    static constexpr uint32_t CRAB_CUTE_HIT_MS   = 3000;
    static constexpr uint32_t CRAB_IDLE_SLEEP_MS = 20000;
    static constexpr uint32_t CRAB_SLEEP_MS      = 5000;
    static constexpr int   CRAB_SLEEP_BASE_Y     = 16;
    static constexpr int   CRAB_SLEEP_STEP_PX    = 7;
    static constexpr int   CRAB_SLEEP_Z_COUNT    = 4;
    static constexpr uint32_t CRAB_SLEEP_Z_MS    = 400;
    static constexpr float    CRAB_SLEEP_SWAY_AMP      = 4.0f;
    static constexpr float    CRAB_SLEEP_SWAY_Y_AMP    = 2.0f;
    static constexpr float    CRAB_SLEEP_SWAY_SPEED    = 1.5f;
    static constexpr float    CRAB_SLEEP_SWAY_PHASE    = 0.5f;
    static constexpr uint16_t CRAB_SLEEP_Z_COLOR       = 0x780A;
    static constexpr int      CRAB_LEG_CHAR_W          = 3;
    static constexpr float    CRAB_LEG_WAVE_SPEED      = 4.0f;
    static constexpr float    CRAB_LEG_WAVE_AMP        = 2.0f;
    static constexpr float    CRAB_LEG_WAVE_SPACING    = 0.85f;
    static constexpr float    CRAB_LEG_WAVE_IDLE_SCALE = 0.15f;
    static constexpr float    CRAB_LEG_WAVE_LERP_RATE  = 2.0f;
    static constexpr uint16_t CRAB_LEG_COLOR           = 0xA000;
    static constexpr uint32_t CRAB_MEAL_SLEEP_MIN_MS   = 10000;
    static constexpr uint32_t CRAB_MEAL_SLEEP_MAX_MS   = 60000;
    static constexpr int      CRAB_MEAL_FISH_W_MIN     = 12;
    static constexpr int      CRAB_MEAL_FISH_W_MAX     = 66;
    static constexpr uint32_t CRAB_SATIATED_MS         = 30000;
    static constexpr uint32_t CRAB_TAP_SLEEP_SKIP_MS    = 8000;
    static constexpr uint32_t CRAB_TAP_SATIATED_SKIP_MS = 10000;
    static constexpr int      CRAB_FISH_HIT_CHANCE      = 6;
    static constexpr float    CRAB_SCATTER_RADIUS_PX    = float(CRAB_W_PX);
    static constexpr float    CRAB_SCATTER_SPEED_PX_S   = 80.0f;
    static constexpr uint32_t CRAB_SCATTER_FLEE_MS      = 600;
    static constexpr float    CRAB_SCATTER_Y_BIAS       = 0.35f;

    // Physics constants (transcribed from upstream lines 300-327)
    static constexpr float FISH_SWIM_WAVE_AMPLITUDE     = 1.5f;
    static constexpr float FISH_SWIM_WAVE_SPEED         = 5.6f;
    static constexpr float FISH_SWIM_WAVE_SPEED_FLEE    = 16.0f;
    static constexpr float FISH_SWIM_WAVE_SPACING       = 0.85f;
    static constexpr float FISH_AVOID_RADIUS_X          = 52.0f;
    static constexpr float FISH_AVOID_RADIUS_Y          = 20.0f;
    static constexpr float FISH_AVOID_STRENGTH          = 4.2f;
    static constexpr float FISH_CENTER_Y_OFFSET         = 7.0f;
    static constexpr float OCTOPUS_EXIT_PAD             = 42.0f;
    static constexpr float OCTOPUS_CENTER_Y_OFFSET      = 8.0f;
    static constexpr float OCTOPUS_FISH_AVOID_RADIUS_X  = 76.0f;
    static constexpr float OCTOPUS_FISH_AVOID_RADIUS_Y  = 34.0f;
    static constexpr float OCTOPUS_FISH_AVOID_STRENGTH  = 8.0f;
    static constexpr float OCTOPUS_FISH_CLEAR_RADIUS_X  = 46.0f;
    static constexpr float OCTOPUS_FISH_CLEAR_RADIUS_Y  = 22.0f;
    static constexpr float SEAHORSE_EXIT_PAD            = 48.0f;
    static constexpr float SEAHORSE_CENTER_X_OFFSET     = 15.0f;
    static constexpr float SEAHORSE_CENTER_Y_OFFSET     = 24.0f;
    static constexpr float SEAHORSE_FISH_AVOID_RADIUS_X = 58.0f;
    static constexpr float SEAHORSE_FISH_AVOID_RADIUS_Y = 38.0f;
    static constexpr float SEAHORSE_FISH_AVOID_STRENGTH = 6.0f;
    static constexpr float SEAHORSE_FISH_CLEAR_RADIUS_X = 34.0f;
    static constexpr float SEAHORSE_FISH_CLEAR_RADIUS_Y = 28.0f;
    static constexpr float SEAHORSE_SPEED_BOOST         = 1.18f;
    static constexpr float VISITOR_CLEAR_RADIUS_X       = 56.0f;
    static constexpr float VISITOR_CLEAR_RADIUS_Y       = 38.0f;

    // Reciprocals for radius denominators (P2: eliminate FP division at call sites)
    static constexpr float kInv9999                      = 1.0f / 9999.0f;
    static constexpr float kInvFishAvoidRX               = 1.0f / FISH_AVOID_RADIUS_X;
    static constexpr float kInvFishAvoidRY               = 1.0f / FISH_AVOID_RADIUS_Y;
    static constexpr float kInvOctFishAvRX               = 1.0f / OCTOPUS_FISH_AVOID_RADIUS_X;
    static constexpr float kInvOctFishAvRY               = 1.0f / OCTOPUS_FISH_AVOID_RADIUS_Y;
    static constexpr float kInvOctFishClRX               = 1.0f / OCTOPUS_FISH_CLEAR_RADIUS_X;
    static constexpr float kInvOctFishClRY               = 1.0f / OCTOPUS_FISH_CLEAR_RADIUS_Y;
    static constexpr float kInvSHFishAvRX                = 1.0f / SEAHORSE_FISH_AVOID_RADIUS_X;
    static constexpr float kInvSHFishAvRY                = 1.0f / SEAHORSE_FISH_AVOID_RADIUS_Y;
    static constexpr float kInvSHFishClRX                = 1.0f / SEAHORSE_FISH_CLEAR_RADIUS_X;
    static constexpr float kInvSHFishClRY                = 1.0f / SEAHORSE_FISH_CLEAR_RADIUS_Y;
    static constexpr float kInvVisClRX                   = 1.0f / VISITOR_CLEAR_RADIUS_X;
    static constexpr float kInvVisClRY                   = 1.0f / VISITOR_CLEAR_RADIUS_Y;

    // ── Structs ──────────────────────────────────────────────────────────────
    struct Flake {
        bool active;
        float x, y, vy;
        uint16_t color;
    };
    struct Bubble {
        bool active;
        float x, y, baseX, vy, phase, swayAmp;
        uint16_t color;
    };
    struct FishSpecies {
        const char* right;
        uint16_t    baseColor;
    };
    struct Fish {
        float    x, y, vx, vy, phase, wanderBias, depthBrightness;
        uint16_t displayColor, renderColor;
        uint8_t  speed;
        uint8_t  type;
        uint8_t  visualWidth;
        bool     active;
        uint32_t fleeUntilMs;
    };
    struct Octopus {
        bool active;
        float x, y, baseY, vx, phase, colorPhase;
        unsigned long nextSpawnMs;
    };
    struct Seahorse {
        bool active, facingRight;
        float x, y, baseY, vx, phase, finPhase;
        unsigned long nextSpawnMs;
    };

    struct Crab {
        enum class State : uint8_t { WALK, PINCH_L, PINCH_R, CUTE, SLEEP };
        float    x;
        float    y;
        float    vy;
        int8_t   direction;
        State    state;
        uint8_t  walkFrame;
        uint8_t  pinchFrame;
        uint8_t  sleepZFrame;
        uint32_t cuteDurationMs;
        uint32_t stateEnteredMs;
        uint32_t walkFrameMs;
        uint32_t pinchFrameMs;
        uint32_t sleepZFrameMs;
        uint32_t lastTargetSeenMs;
        uint32_t sleepDurationMs;
        uint32_t satiatedUntilMs;
        float    phase;
        float    legWaveIntensity;
    };

    // ── Members ──────────────────────────────────────────────────────────────
    TFT_eSprite   _canvas{&tft};
    bool          _spriteReady        = false;
    bool          _retryShown         = false;
    unsigned long _lastTickMs         = 0;
    unsigned long _lastRetryMs        = 0;
    uint8_t _activeFish  = 8;
    float   _speedMult   = 1.0f;
    unsigned long _aquariumNowMs      = 0;
    unsigned long _lastClockUpdateMs  = 0;
    int           _clockHour       = 0;
    int           _clockMinute     = 0;

    Fish     _fishPool[AQ_FISH_POOL_MAX];
    Flake    _flakes[AQ_FLAKE_MAX];
    Bubble   _bubbles[AQ_BUBBLE_POOL_MAX];
    Octopus  _octopus;
    Seahorse _seahorse;
    Crab     _crab;
    int16_t  _crabBodyW = 49;
    float    _seaweedBaseX[AQ_SEAWEED_ROOTS];
    float    _seaweedSpeed[AQ_SEAWEED_ROOTS];
    float    _seaweedPhase[AQ_SEAWEED_ROOTS];

    uint16_t _gradTile[AQ_BACKGROUND_GRADIENT_H][32];
    bool     _gradientBandCached = false;

    uint32_t _perfCycUpdate = 0;
    uint32_t _perfCycDraw   = 0;
    uint32_t _perfCycTick   = 0;
    uint32_t _perfFrames    = 0;

    static const float   kHeightNoise[AQ_SEAWEED_ROOTS];
    static const int8_t  kSeaweedDisp[32][8] PROGMEM;

    uint8_t _fishGlyphLenRight[AQ_GLYPH_COUNT];
    int16_t _fishGlyphWidthRight[AQ_GLYPH_COUNT];
    uint8_t _fishCharWidthRight[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];

    // ── Static fish/color data (Meyer's singleton, header-safe) ──────────────
    static const FishSpecies* _species();
    static const uint16_t* _altColors();
    static constexpr int kAltColorCount = 8;

    // ── Utility ──────────────────────────────────────────────────────────────
    static constexpr uint16_t _RGB565(uint8_t r, uint8_t g, uint8_t b) {
        return uint16_t((uint16_t(r & 0xF8) << 8) | (uint16_t(g & 0xFC) << 3) | (b >> 3));
    }

    template <typename T>
    static T _clamp(T v, T lo, T hi) { return v < lo ? lo : (v > hi ? hi : v); }

    float _frand(float a, float b) {
        return a + (b - a) * float(random(0, 10000)) * kInv9999;
    }

    float _timeSec() const { return _aquariumNowMs * 0.001f; }

    uint16_t _scaleColor(uint16_t color, float br);
    uint16_t _randBubbleColor();
    uint16_t _randFoodColor();

    // ── Fish glyph mirroring ──────────────────────────────────────────────────
    static char _mirrorBracket(char c);
    void initFishGlyphMetrics();
    int _glyphVisW(const Fish& f) const;

    // ── Fish population ───────────────────────────────────────────────────────
    void _applyAquariumSettings();
    void _activateFish(Fish& f, bool on);
    void applyFishPopulation();
    bool _spawnClear(int idx, float x, float y, float gx, float gy);
    void spreadInitialFishLayout();

    // ── Bubble population ─────────────────────────────────────────────────────
    void _resetBubble(Bubble& b, bool spread);
    void applyBubblePopulation(bool spread = false);

    // ── Flakes ────────────────────────────────────────────────────────────────
    void spawnFlake(float x, float y);

    // ── Update ────────────────────────────────────────────────────────────────
    void updateFlakes(float dt);
    void updateBubbles(float dt);
    int _closestFlake(const Fish& f, float maxD);
    void _steerFromOctopus(Fish& f, float fcx, float fcy, float dt);
    void _steerFromSeahorse(Fish& f, float fcx, float fcy, float dt);
    void _pushOutOfOctopus(Fish& f);
    void _pushOutOfSeahorse(Fish& f);
    void updateFish(float dt);

    // ── Octopus ───────────────────────────────────────────────────────────────
    void _schedOctopus(unsigned long now);
    void _spawnOctopus(unsigned long now);
    void updateOctopus(unsigned long now, float dt);

    // ── Seahorse ──────────────────────────────────────────────────────────────
    void _schedSeahorse(unsigned long now);
    void _spawnSeahorse(unsigned long now);
    void updateSeahorse(unsigned long now, float dt);

    void keepVisitorsSeparated();

    // ── Clock ─────────────────────────────────────────────────────────────────
    void updateClock();
    void drawClock();

    // ── Gradient / Background ─────────────────────────────────────────────────
    static int _c5to8(int v) { return (v << 3) | (v >> 2); }
    static int _c6to8(int v) { return (v << 2) | (v >> 4); }
    static int _bayerT(int x, int y, int scale);
    static uint16_t _rgb888to565(int r, int g, int b);
    static void _gradAtT(const uint16_t* colors, const uint8_t* stops, int n, int t255,
                          int& r8, int& g8, int& b8);
    void _buildGradTile(const uint16_t* colors, const uint8_t* stops, int n);
    void drawBackground();

    // ── Seaweed ───────────────────────────────────────────────────────────────
    void _seaweedBranches(int bi, float bh, float scale, uint8_t pi,
                          float t, float bx, int y0_world, int stripY);
    void drawSeaweed(float t, int stripY);

    // ── Draw entities ─────────────────────────────────────────────────────────
    void drawFlakes(TFT_eSprite& canvas, int stripY);
    void drawBubbles(TFT_eSprite& canvas, int zoneY);
    void drawFish(int stripY);
    void drawOctopus(int stripY);
    static char _mirrorHorse(char c);
    void drawSeahorse(int stripY);

    // ── Seaweed init ──────────────────────────────────────────────────────────
    void initSeaweed();
    uint8_t _seaweedPhaseIdx(int i, float t) const;

    // ── Crab ──────────────────────────────────────────────────────────────────
    void initCrab();
    int findPinchTarget();
    void _scatterFish(int cx, int cy);
    void updateCrab(float dt);
    void drawCrab(int stripY);

    // ── Render ────────────────────────────────────────────────────────────────
    void renderFrame();
};
