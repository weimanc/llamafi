#pragma once
// aquariumApp.h — ASCII Aquarium port (M-AQUARIUM). Single-header App class.
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

extern TFT_eSPI tft;

class AquariumApp : public App {
public:
    void init() override {
        memset(_fishPool, 0, sizeof(_fishPool));
        memset(_flakes,   0, sizeof(_flakes));
        memset(_bubbles,  0, sizeof(_bubbles));
        _octopus  = Octopus{};
        _seahorse = Seahorse{};
        _gradientBandCached = false;
        _retryShown         = false;
        _lastRetryMs        = 0;

        _canvas.setColorDepth(8);
        bool c1 = (_canvas.createSprite(AQ_CANVAS_W, AQ_STRIP_H) != nullptr);
        _spriteReady = c1;
        if (!c1) _canvas.deleteSprite();
        Serial.printf("[aquarium] init sprite %dx%d 8bpp: %s  heap=%lu maxAlloc=%lu\n",
            AQ_CANVAS_W, AQ_STRIP_H, c1 ? "OK" : "FAILED",
            (unsigned long)ESP.getFreeHeap(), (unsigned long)ESP.getMaxAllocHeap());
        _canvas.setTextFont(2);  // needed for glyph metrics regardless of alloc result

        initFishGlyphMetrics();
        applyFishPopulation();
        spreadInitialFishLayout();
        initSeaweed();
        initCrab();
        applyBubblePopulation(true);

        unsigned long now = millis();
        _lastTickMs   = now;
        _aquariumNowMs = now;
    }

    void resume() override {
        _applyAquariumSettings();
        _retryShown  = false;
        _lastRetryMs = 0;
        _canvas.setColorDepth(8);
        bool c1 = (_canvas.createSprite(AQ_CANVAS_W, AQ_STRIP_H) != nullptr);
        _spriteReady = c1;
        if (!c1) _canvas.deleteSprite();
        Serial.printf("[aquarium] resume sprite: %s  heap=%lu maxAlloc=%lu\n",
            c1 ? "OK" : "FAILED",
            (unsigned long)ESP.getFreeHeap(), (unsigned long)ESP.getMaxAllocHeap());
        if (_spriteReady) {
            _canvas.setTextFont(2);
        }
        _lastTickMs = millis();
    }

    void suspend() override {
        _canvas.deleteSprite();
        _spriteReady = false;
    }

    void tick() override {
        if (!_spriteReady) {
            // Retry sprite allocation every 500 ms — SSL/TLS buffers may free up
            // after the first Spotify poll, giving us the ~11 KB we need.
            unsigned long now2 = millis();
            if (now2 - _lastRetryMs >= 500) {
                _lastRetryMs = now2;
                _canvas.setColorDepth(8);
                bool c1 = (_canvas.createSprite(AQ_CANVAS_W, AQ_STRIP_H) != nullptr);
                _spriteReady = c1;
                if (_spriteReady) {
                    _canvas.setTextFont(2);
                    _lastTickMs = now2;
                    Serial.printf("[aquarium] retry succeeded  heap=%lu\n",
                        (unsigned long)ESP.getFreeHeap());
                } else {
                    if (c1) _canvas.deleteSprite();
                    Serial.printf("[aquarium] retry failed  heap=%lu maxAlloc=%lu\n",
                        (unsigned long)ESP.getFreeHeap(),
                        (unsigned long)ESP.getMaxAllocHeap());
                    if (!_retryShown) {
                        _retryShown = true;
                        tft.fillRect(0, 0, TASKBAR_X, 240, 0x000F /*dark navy*/);
                        tft.setTextColor(TFT_WHITE, 0x000F);
                        tft.setTextDatum(MC_DATUM);
                        tft.drawString("Aquarium", TASKBAR_X / 2, 100, 4);
                        tft.drawString("heap full", TASKBAR_X / 2, 140, 2);
                        char hb[32];
                        snprintf(hb, sizeof(hb), "max block: %lu B",
                            (unsigned long)ESP.getMaxAllocHeap());
                        tft.drawString(hb, TASKBAR_X / 2, 158, 2);
                        tft.setTextDatum(TL_DATUM);
                        tft.setTextColor(TFT_WHITE, TFT_BLACK);
                    }
                }
            }
            return;
        }
        unsigned long now     = millis();
        unsigned long elapsed = now - _lastTickMs;
        _lastTickMs = now;
        unsigned long step = elapsed < 1UL ? 1UL : (elapsed > 50UL ? 50UL : elapsed);
        _aquariumNowMs += step;
        float dt = step * 0.001f;

        uint32_t t_tick = xthal_get_ccount();
        updateClock();

        uint32_t t_upd = xthal_get_ccount();
        updateFlakes(dt);
        updateCrab(dt);
        updateBubbles(dt);
        updateFish(dt);
        updateOctopus(_aquariumNowMs, dt);
        updateSeahorse(_aquariumNowMs, dt);
        keepVisitorsSeparated();
        _perfCycUpdate += xthal_get_ccount() - t_upd;

        uint32_t t_draw = xthal_get_ccount();
        renderFrame();
        _perfCycDraw += xthal_get_ccount() - t_draw;

        _perfCycTick += xthal_get_ccount() - t_tick;
        ++_perfFrames;
        if (_perfFrames >= 300) {
            float div = _perfFrames * 240.0f;
            Serial.printf("[aq perf] tick=%.0fus upd=%.0fus draw=%.0fus frames=%lu\n",
                _perfCycTick / div, _perfCycUpdate / div, _perfCycDraw / div,
                (unsigned long)_perfFrames);
            _perfCycUpdate = _perfCycDraw = _perfCycTick = _perfFrames = 0;
        }

        // Frame rate cap: pad short frames to 42 ms so all frames are uniform,
        // smoothing out the perceptual stutter from WiFi/DMA timing variance.
        long _rem = 42L - (long)(millis() - now);
        if (_rem > 0) vTaskDelay(pdMS_TO_TICKS((uint32_t)_rem));
    }

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase == TouchPhase::Press) {
            bool onCrab = (x >= (int)_crab.x && x <= (int)_crab.x + CRAB_W_PX
                        && y >= (int)_crab.y - 4
                        && y <= (int)_crab.y + CRAB_CHAR_H + CRAB_LEG_OVERLAP_PX + 4);
            if (onCrab) {
                uint32_t now = millis();
                if (_crab.state == Crab::State::SLEEP) {
                    uint32_t limit = (_crab.sleepDurationMs > 0) ? _crab.sleepDurationMs : CRAB_SLEEP_MS;
                    uint32_t elapsed = now - _crab.stateEnteredMs;
                    if (elapsed + 1 < limit)
                        _crab.stateEnteredMs += _clamp(CRAB_TAP_SLEEP_SKIP_MS, 0u, limit - elapsed - 1u);
                } else if (_crab.state == Crab::State::WALK && now < _crab.satiatedUntilMs) {
                    if (_crab.satiatedUntilMs > now + CRAB_TAP_SATIATED_SKIP_MS)
                        _crab.satiatedUntilMs -= CRAB_TAP_SATIATED_SKIP_MS;
                    else
                        _crab.satiatedUntilMs = now;
                }
                return true;
            }
            spawnFlake((float)x, (float)y);
            return true;
        }
        return false;
    }

#ifdef SERIAL_DEBUG
    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "aquariumFish") == 0) {
            snprintf(buf, len, "\"var\":\"aquariumFish\",\"val\":%u,\"last\":true",
                     (unsigned)_activeFish);
            return true;
        }
        return false;
    }
#endif

private:
    // ── Constants ──────────────────────────────────────────────────────────
    static constexpr int   AQ_CANVAS_W            = 275;
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
    static const FishSpecies* _species() {
        // Colors computed once at first call; _RGB565 not available as constexpr at class-parse time.
        const uint16_t EM = _RGB565(80,200,120), AZ = _RGB565(0,150,255);
        const uint16_t AM = _RGB565(255,184,0),  TL = _RGB565(0,180,170);
        const uint16_t IN = _RGB565(75,0,156),   LI = _RGB565(200,120,255);
        const uint16_t PT = _RGB565(255,158,200);
        static FishSpecies s[] = {
            {"<>",          EM},
            {">)))'>",      AZ},
            {"oO0",         0xFE19 /*TFT_PINK*/},
            {"><((( '>",    AM},
            {"~~{o}",       0x8010 /*TFT_VIOLET*/},
            {"><(((o>",     0xF800 /*TFT_RED*/},
            {"><((((>`",    0xFD20 /*TFT_ORANGE*/},
            {"><((( '>",    TL},
            {"}>{{{{* >",   IN},
            {"><((( *>",    LI},
            {">(')>",       PT},
            {">'>",         0xFFE0 /*TFT_YELLOW*/},
        };
        return s;
    }

    static const uint16_t* _altColors() {
        static const uint16_t c[] = {
            0x07FF /*TFT_CYAN*/, 0xF81F /*TFT_MAGENTA*/, 0xFFFF /*TFT_WHITE*/,
            0x867D /*TFT_SKYBLUE*/, 0xFFD700>>8 /*approx gold*/,
            0xFD20 /*TFT_ORANGE*/, 0xB7E0 /*TFT_GREENYELLOW*/, 0x7BEF /*TFT_DARKGREY*/
        };
        return c;
    }
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

    uint16_t _scaleColor(uint16_t color, float br) {
        if (br < 0.0f) br = 0.0f;
        if (br > 1.0f) br = 1.0f;
        uint16_t r = uint16_t(((color >> 11) & 0x1F) * br);
        uint16_t g = uint16_t(((color >>  5) & 0x3F) * br);
        uint16_t b = uint16_t(( color        & 0x1F) * br);
        return uint16_t((r << 11) | (g << 5) | b);
    }

    uint16_t _randBubbleColor() {
        return _RGB565(uint8_t(random(0,5)), uint8_t(random(8,24)), uint8_t(random(45,106)));
    }
    uint16_t _randFoodColor() {
        return _RGB565(uint8_t(random(220,256)), uint8_t(random(118,166)), uint8_t(random(0,34)));
    }

    // ── Fish glyph mirroring ──────────────────────────────────────────────────
    static char _mirrorBracket(char c) {
        switch (c) {
            case '>': return '<'; case '<': return '>';
            case '(': return ')'; case ')': return '(';
            case '{': return '}'; case '}': return '{';
            case '[': return ']'; case ']': return '[';
            default:  return c;
        }
    }

    void initFishGlyphMetrics() {
        const FishSpecies* sp = _species();
        for (int i = 0; i < AQ_GLYPH_COUNT; ++i) {
            const char* right = sp[i].right;
            size_t n = strlen(right);
            if (n >= AQ_GLYPH_BUF) n = AQ_GLYPH_BUF - 1;
            _fishGlyphLenRight[i] = uint8_t(n);
            int16_t totalW = 0;
            for (size_t c = 0; c < n; ++c) {
                char tmp[2] = {right[c], '\0'};
                uint8_t w = uint8_t(_canvas.textWidth(tmp));
                _fishCharWidthRight[i][c] = w;
                totalW += w;
            }
            _fishGlyphWidthRight[i] = totalW;
        }
    }

    int _glyphVisW(const Fish& f) const {
        if (f.visualWidth > 0) return f.visualWidth;
        return int(strlen(_species()[f.type].right)) * 12;
    }

    // ── Fish population ───────────────────────────────────────────────────────
    void _applyAquariumSettings() {
        _activeFish = g_settings.aquariumFish;
        if (_activeFish < 1)  _activeFish = 1;
        if (_activeFish > AQ_FISH_POOL_MAX) _activeFish = AQ_FISH_POOL_MAX;
        switch (g_settings.aquariumSpeed) {
            case AppSpeed::Slow:   _speedMult = 0.6f; break;
            case AppSpeed::Fast:   _speedMult = 1.7f; break;
            default:               _speedMult = 1.0f; break;
        }
    }

    void _activateFish(Fish& f, bool on) {
        f.active = on;
        if (!on) return;
        const FishSpecies* sp = _species();
        f.type = uint8_t(random(0, AQ_GLYPH_COUNT));
        f.visualWidth = uint8_t(_fishGlyphWidthRight[f.type]);
        if (f.visualWidth == 0) f.visualWidth = uint8_t(int(strlen(sp[f.type].right)) * 12);
        f.displayColor = sp[f.type].baseColor;
        if (random(100) < 20) f.displayColor = _altColors()[random(0, kAltColorCount)];
        int roll = random(100);
        f.depthBrightness = (roll < 28) ? _frand(0.48f,0.64f)
                          : (roll < 70) ? _frand(0.66f,0.84f) : _frand(0.88f,1.0f);
        f.renderColor = _scaleColor(f.displayColor, f.depthBrightness);
        f.x = _frand(-42.0f, AQ_CANVAS_W + 12.0f);
        f.y = _frand(20.0f, float(AQ_CANVAS_H) - 30.0f);
        f.vx = _frand(-1.0f, 1.0f);
        f.vy = _frand(-0.5f, 0.5f);
        f.speed = uint8_t(_frand(14.0f, 30.0f) * _speedMult);
        f.phase = _frand(0.0f, 6.28318f);
        f.wanderBias = _frand(0.4f, 1.3f);
        f.fleeUntilMs = 0;
    }

    void applyFishPopulation() {
        for (int i = 0; i < AQ_FISH_POOL_MAX; ++i) {
            bool want = (i < _activeFish);
            if (want  && !_fishPool[i].active) _activateFish(_fishPool[i], true);
            if (!want &&  _fishPool[i].active) _fishPool[i].active = false;
        }
    }

    bool _spawnClear(int idx, float x, float y, float gx, float gy) {
        float cx = x + _fishPool[idx].visualWidth * 0.5f;
        float cy = y + FISH_CENTER_Y_OFFSET;
        for (int i = 0; i < _activeFish; ++i) {
            if (i == idx || !_fishPool[i].active) continue;
            float ox = _fishPool[i].x + _fishPool[i].visualWidth * 0.5f;
            float oy = _fishPool[i].y + FISH_CENTER_Y_OFFSET;
            if (fabsf(ox - cx) < gx && fabsf(oy - cy) < gy) return false;
        }
        return true;
    }

    void spreadInitialFishLayout() {
        float gx = FISH_AVOID_RADIUS_X * 0.92f, gy = FISH_AVOID_RADIUS_Y * 1.05f;
        for (int i = 0; i < _activeFish; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;
            float bx = f.x, by = f.y;
            for (int a = 0; a < 80; ++a) {
                float cx = _frand(10.0f, AQ_CANVAS_W - f.visualWidth - 10.0f);
                float cy = _frand(18.0f, float(AQ_CANVAS_H) - 34.0f);
                bx = cx; by = cy;
                if (_spawnClear(i, cx, cy, gx, gy)) break;
            }
            f.x = bx; f.y = by;
            f.vx = (random(100) < 50) ? -1.0f : 1.0f;
            f.vy = _frand(-0.22f, 0.22f);
        }
    }

    // ── Bubble population ─────────────────────────────────────────────────────
    void _resetBubble(Bubble& b, bool spread) {
        b.active = true;
        b.baseX  = _frand(8.0f, AQ_CANVAS_W - 8.0f);
        b.x      = b.baseX;
        b.y      = spread ? _frand(4.0f, float(AQ_CANVAS_H) + 48.0f)
                           : _frand(float(AQ_CANVAS_H) - 4.0f, float(AQ_CANVAS_H) + 48.0f);
        b.vy     = _frand(12.0f, 28.0f);
        b.phase  = _frand(0.0f, 6.28318f);
        b.swayAmp = _frand(2.0f, 7.0f);
        b.color  = _randBubbleColor();
    }

    void applyBubblePopulation(bool spread = false) {
        for (int i = 0; i < AQ_BUBBLE_POOL_MAX; ++i) {
            bool want = (i < AQ_BUBBLE_COUNT);
            if (want  && !_bubbles[i].active) _resetBubble(_bubbles[i], spread);
            if (!want &&  _bubbles[i].active) _bubbles[i].active = false;
        }
    }

    // ── Flakes ────────────────────────────────────────────────────────────────
    void spawnFlake(float x, float y) {
        for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
            if (!_flakes[i].active) {
                _flakes[i] = { true, x, y, _frand(22.0f, 48.0f), _randFoodColor() };
                return;
            }
        }
    }

    // ── Update ────────────────────────────────────────────────────────────────
    void updateFlakes(float dt) {
        float t = _timeSec();
        for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
            if (!_flakes[i].active) continue;
            _flakes[i].y += _flakes[i].vy * dt;
            _flakes[i].x += lut_sin(t * 1.2f + i) * 8.0f * dt;
            if (_flakes[i].y >= float(AQ_CANVAS_H)) _flakes[i].active = false;
        }
    }

    void updateBubbles(float dt) {
        float t = _timeSec();
        for (int i = 0; i < AQ_BUBBLE_COUNT; ++i) {
            if (!_bubbles[i].active) continue;
            _bubbles[i].y -= _bubbles[i].vy * dt;
            _bubbles[i].x = _bubbles[i].baseX
                           + lut_sin(t * 1.8f + _bubbles[i].phase) * _bubbles[i].swayAmp;
            if (_bubbles[i].y < -10.0f) _resetBubble(_bubbles[i], false);
        }
    }

    int _closestFlake(const Fish& f, float maxD) {
        int best = -1; float bestD2 = maxD * maxD;
        for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
            if (!_flakes[i].active) continue;
            float dx = _flakes[i].x - f.x, dy = _flakes[i].y - f.y;
            float d2 = dx*dx + dy*dy;
            if (d2 < bestD2) { bestD2 = d2; best = i; }
        }
        return best;
    }

    void _steerFromOctopus(Fish& f, float fcx, float fcy, float dt) {
        if (!_octopus.active) return;
        float dx = fcx - _octopus.x, dy = fcy - (_octopus.y + OCTOPUS_CENTER_Y_OFFSET);
        float sx = dx*kInvOctFishAvRX, sy = dy*kInvOctFishAvRY;
        float sd2 = sx*sx + sy*sy;
        if (sd2 <= 0.0001f || sd2 >= 1.0f) return;
        float inv = q_rsqrt(dx*dx + dy*dy + 0.00000001f);
        float push = (1.0f - sd2); push *= push;
        f.vx += (dx*inv) * push * OCTOPUS_FISH_AVOID_STRENGTH * dt;
        f.vy += (dy*inv) * push * OCTOPUS_FISH_AVOID_STRENGTH * dt;
    }

    void _steerFromSeahorse(Fish& f, float fcx, float fcy, float dt) {
        if (!_seahorse.active) return;
        float hcx = _seahorse.x + SEAHORSE_CENTER_X_OFFSET;
        float hcy = _seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
        float dx = fcx - hcx, dy = fcy - hcy;
        float sx = dx*kInvSHFishAvRX, sy = dy*kInvSHFishAvRY;
        float sd2 = sx*sx + sy*sy;
        if (sd2 <= 0.0001f || sd2 >= 1.0f) return;
        float inv = q_rsqrt(dx*dx + dy*dy + 0.00000001f);
        float push = (1.0f - sd2); push *= push;
        f.vx += (dx*inv) * push * SEAHORSE_FISH_AVOID_STRENGTH * dt;
        f.vy += (dy*inv) * push * SEAHORSE_FISH_AVOID_STRENGTH * dt;
    }

    void _pushOutOfOctopus(Fish& f) {
        if (!_octopus.active) return;
        float fcx = f.x + f.visualWidth*0.5f, fcy = f.y + FISH_CENTER_Y_OFFSET;
        float ocy = _octopus.y + OCTOPUS_CENTER_Y_OFFSET;
        float dx = fcx - _octopus.x, dy = fcy - ocy;
        float sx = dx*kInvOctFishClRX, sy = dy*kInvOctFishClRY;
        float sd2 = sx*sx + sy*sy;
        if (sd2 >= 1.0f) return;
        if (sd2 <= 0.0001f) {
            dx = (f.vx >= 0.0f) ? 1.0f : -1.0f;
            dy = (f.vy >= 0.0f) ? 0.35f : -0.35f;
            sd2 = (dx*kInvOctFishClRX)*(dx*kInvOctFishClRX)
                + (dy*kInvOctFishClRY)*(dy*kInvOctFishClRY);
        }
        float scale = q_rsqrt(sd2);
        f.x += (_octopus.x + dx*scale - fcx) * 0.55f;
        f.y += (ocy        + dy*scale - fcy) * 0.55f;
    }

    void _pushOutOfSeahorse(Fish& f) {
        if (!_seahorse.active) return;
        float fcx = f.x + f.visualWidth*0.5f, fcy = f.y + FISH_CENTER_Y_OFFSET;
        float hcx = _seahorse.x + SEAHORSE_CENTER_X_OFFSET;
        float hcy = _seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
        float dx = fcx - hcx, dy = fcy - hcy;
        float sx = dx*kInvSHFishClRX, sy = dy*kInvSHFishClRY;
        float sd2 = sx*sx + sy*sy;
        if (sd2 >= 1.0f) return;
        if (sd2 <= 0.0001f) {
            dx = (f.vx >= 0.0f) ? 1.0f : -1.0f;
            dy = (f.vy >= 0.0f) ? 0.35f : -0.35f;
            sd2 = (dx*kInvSHFishClRX)*(dx*kInvSHFishClRX)
                + (dy*kInvSHFishClRY)*(dy*kInvSHFishClRY);
        }
        float scale = q_rsqrt(sd2);
        f.x += (hcx + dx*scale - fcx) * 0.45f;
        f.y += (hcy + dy*scale - fcy) * 0.45f;
    }

    void updateFish(float dt) {
        const float t = _timeSec();
        uint32_t now = millis();
        float cx[AQ_FISH_POOL_MAX], cy[AQ_FISH_POOL_MAX];
        for (int i = 0; i < _activeFish; ++i) {
            Fish& f = _fishPool[i];
            cx[i] = f.active ? f.x + f.visualWidth*0.5f : 0.0f;
            cy[i] = f.active ? f.y + FISH_CENTER_Y_OFFSET : 0.0f;
        }

        for (int i = 0; i < _activeFish; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;

            if (f.fleeUntilMs != 0) {
                if (now < f.fleeUntilMs) {
                    f.x += f.vx * dt;
                    f.y += f.vy * dt;
                    f.y = _clamp(f.y, 14.0f, float(AQ_CANVAS_H) - 20.0f);
                    float wrapPad = float(_glyphVisW(f)) + 10.0f;
                    if (f.x >  AQ_CANVAS_W + wrapPad) f.x = -wrapPad;
                    if (f.x < -wrapPad)               f.x = AQ_CANVAS_W + wrapPad;
                    continue;
                }
                f.fleeUntilMs = 0;
            }

            f.vx += lut_cos(f.phase + t*0.9f) * 0.45f * f.wanderBias * dt;
            f.vy += lut_sin(f.phase*1.7f + t*0.7f) * 0.22f * dt;

            float avgVX=0, avgVY=0, scx=0, scy=0;
            int nearCount=0, repelCount=0;
            float repelX=0, repelY=0;
            float fcx = cx[i], fcy = cy[i];

            for (int j = 0; j < AQ_FISH_COUNT; ++j) {
                if (i==j || !_fishPool[j].active) continue;
                Fish& n = _fishPool[j];
                if (n.type == f.type) {
                    float d2 = (n.x-f.x)*(n.x-f.x) + (n.y-f.y)*(n.y-f.y);
                    if (d2 < 3600.0f) {
                        avgVX += n.vx; avgVY += n.vy;
                        scx += n.x; scy += n.y;
                        nearCount++;
                    }
                }
                float sdx = cx[j] - fcx, sdy = cy[j] - fcy;
                if (sdx >  AQ_CANVAS_W * 0.5f) sdx -= AQ_CANVAS_W;
                if (sdx < -AQ_CANVAS_W * 0.5f) sdx += AQ_CANVAS_W;
                float ssx = sdx*kInvFishAvoidRX, ssy = sdy*kInvFishAvoidRY;
                float sd2 = ssx*ssx + ssy*ssy;
                if (sd2 > 0.0001f && sd2 < 1.0f) {
                    float dist = sqrtf(sdx*sdx + sdy*sdy) + 0.0001f;
                    float push = 1.0f - sd2; push *= push;
                    repelX -= (sdx/dist)*push;
                    repelY -= (sdy/dist)*push;
                    repelCount++;
                }
            }
            if (nearCount > 0) {
                float invN = 1.0f / nearCount;
                avgVX *= invN; avgVY *= invN;
                scx   *= invN; scy   *= invN;
                f.vx += (avgVX - f.vx) * 0.45f * dt;
                f.vy += (avgVY - f.vy) * 0.25f * dt;
                f.vx += (scx - f.x) * 0.0018f;
                f.vy += (scy - f.y) * 0.0012f;
            }

            int fi = _closestFlake(f, 140.0f);
            if (fi >= 0) {
                float dx = _flakes[fi].x - f.x, dy = _flakes[fi].y - f.y;
                float d  = sqrtf(dx*dx + dy*dy) + 0.0001f;
                f.vx += (dx/d) * 0.95f * dt;
                f.vy += (dy/d) * 0.95f * dt;
                if (d < 8.0f) _flakes[fi].active = false;
            }

            _steerFromOctopus(f, fcx, fcy, dt);
            _steerFromSeahorse(f, fcx, fcy, dt);

            if (repelCount > 0) {
                f.vx += (repelX/repelCount) * FISH_AVOID_STRENGTH * dt;
                f.vy += (repelY/repelCount) * FISH_AVOID_STRENGTH * dt;
            }

            if (f.y < 18)                          f.vy += 0.8f * dt;
            if (f.y > float(AQ_CANVAS_H) - 22.0f) f.vy -= 0.8f * dt;

            float mag2 = f.vx*f.vx + f.vy*f.vy;
            if (mag2 < 0.00000001f) { f.vx = 1.0f; f.vy = 0.0f; }
            else { float inv = q_rsqrt(mag2); f.vx *= inv; f.vy *= inv; }

            float spd = f.speed + lut_sin(t*3.2f + f.phase) * 4.0f;
            f.x += f.vx * spd * dt;
            f.y += f.vy * spd * dt;
            _pushOutOfOctopus(f);
            _pushOutOfSeahorse(f);

            float wrapPad = float(_glyphVisW(f)) + 10.0f;
            if (f.x >  AQ_CANVAS_W + wrapPad) {
                f.x = -wrapPad;
                int roll2 = random(100);
                f.depthBrightness = (roll2 < 28) ? _frand(0.48f,0.64f)
                                  : (roll2 < 70) ? _frand(0.66f,0.84f) : _frand(0.88f,1.0f);
                f.renderColor = _scaleColor(f.displayColor, f.depthBrightness);
            }
            if (f.x < -wrapPad) {
                f.x = AQ_CANVAS_W + wrapPad;
                int roll2 = random(100);
                f.depthBrightness = (roll2 < 28) ? _frand(0.48f,0.64f)
                                  : (roll2 < 70) ? _frand(0.66f,0.84f) : _frand(0.88f,1.0f);
                f.renderColor = _scaleColor(f.displayColor, f.depthBrightness);
            }
            f.y = _clamp(f.y, 14.0f, float(AQ_CANVAS_H) - 20.0f);
        }
    }

    // ── Octopus ───────────────────────────────────────────────────────────────
    void _schedOctopus(unsigned long now) {
        _octopus.nextSpawnMs = now + 3600000UL / AQ_OCTOPUS_FREQ;
    }

    void _spawnOctopus(unsigned long now) {
        bool left = (random(100) < 50);
        _octopus.active    = true;
        _octopus.vx        = left ? _frand(4.5f,8.0f) : -_frand(4.5f,8.0f);
        _octopus.x         = left ? -OCTOPUS_EXIT_PAD : (AQ_CANVAS_W + OCTOPUS_EXIT_PAD);
        _octopus.baseY     = _frand(36.0f, float(AQ_SEA_LEVEL_Y) - 48.0f);
        _octopus.y         = _octopus.baseY;
        _octopus.phase     = _frand(0.0f, 6.28318f);
        _octopus.colorPhase = _frand(0.0f, 6.28318f);
        _schedOctopus(now);
    }

    void updateOctopus(unsigned long now, float dt) {
        if (!_octopus.active) {
            if (_octopus.nextSpawnMs == 0) _schedOctopus(now);
            else if ((long)(now - _octopus.nextSpawnMs) >= 0) _spawnOctopus(now);
            return;
        }
        float t = now * 0.001f;
        _octopus.x += _octopus.vx * dt;
        _octopus.y  = _octopus.baseY + lut_sin(t*0.45f + _octopus.phase) * 6.0f;
        if ((_octopus.vx > 0.0f && _octopus.x >  AQ_CANVAS_W + OCTOPUS_EXIT_PAD) ||
            (_octopus.vx < 0.0f && _octopus.x < -OCTOPUS_EXIT_PAD))
            _octopus.active = false;
    }

    // ── Seahorse ──────────────────────────────────────────────────────────────
    void _schedSeahorse(unsigned long now) {
        _seahorse.nextSpawnMs = now + 3600000UL / AQ_SEAHORSE_FREQ;
    }

    void _spawnSeahorse(unsigned long now) {
        bool left = (random(100) < 50);
        _seahorse.active      = true;
        _seahorse.facingRight = left;
        _seahorse.vx          = left ? _frand(1.6f,2.9f)*SEAHORSE_SPEED_BOOST
                                     : -_frand(1.6f,2.9f)*SEAHORSE_SPEED_BOOST;
        _seahorse.x           = left ? -SEAHORSE_EXIT_PAD : (AQ_CANVAS_W + SEAHORSE_EXIT_PAD);
        _seahorse.baseY       = _frand(34.0f, float(AQ_SEA_LEVEL_Y) - 56.0f);
        _seahorse.y           = _seahorse.baseY;
        _seahorse.phase       = _frand(0.0f, 6.28318f);
        _seahorse.finPhase    = _frand(0.0f, 6.28318f);
        _schedSeahorse(now);
    }

    void updateSeahorse(unsigned long now, float dt) {
        if (!_seahorse.active) {
            if (_seahorse.nextSpawnMs == 0) _schedSeahorse(now);
            else if ((long)(now - _seahorse.nextSpawnMs) >= 0) _spawnSeahorse(now);
            return;
        }
        float t = now * 0.001f;
        float pulse = 1.0f + lut_sin(t*0.55f + _seahorse.phase) * 0.18f;
        _seahorse.x += _seahorse.vx * pulse * dt;
        _seahorse.y  = _seahorse.baseY
                     + lut_sin(t*0.82f  + _seahorse.phase)        * 4.5f
                     + lut_sin(t*2.15f  + _seahorse.phase * 1.7f) * 0.9f;
        if ((_seahorse.vx > 0.0f && _seahorse.x >  AQ_CANVAS_W + SEAHORSE_EXIT_PAD) ||
            (_seahorse.vx < 0.0f && _seahorse.x < -SEAHORSE_EXIT_PAD))
            _seahorse.active = false;
    }

    void keepVisitorsSeparated() {
        if (!_octopus.active || !_seahorse.active) return;
        float ocx = _octopus.x,  ocy = _octopus.y + OCTOPUS_CENTER_Y_OFFSET;
        float hcx = _seahorse.x + SEAHORSE_CENTER_X_OFFSET;
        float hcy = _seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
        float dx = hcx - ocx, dy = hcy - ocy;
        float sx = dx*kInvVisClRX, sy = dy*kInvVisClRY;
        float sd2 = sx*sx + sy*sy;
        if (sd2 >= 1.0f) return;
        if (sd2 <= 0.0001f) {
            dx = (_seahorse.vx >= _octopus.vx) ? 1.0f : -1.0f;
            dy = 0.35f;
            sd2 = (dx*kInvVisClRX)*(dx*kInvVisClRX)
                + (dy*kInvVisClRY)*(dy*kInvVisClRY);
        }
        float scale = q_rsqrt(sd2);
        float thx = ocx + dx*scale, thy = ocy + dy*scale;
        float px  = (thx - hcx) * 0.18f, py = (thy - hcy) * 0.22f;
        _seahorse.x    += px;
        _seahorse.baseY = _clamp(_seahorse.baseY + py, 24.0f, float(AQ_SEA_LEVEL_Y) - 54.0f);
        _seahorse.y    += py;
        _octopus.x     -= px * 0.55f;
        _octopus.baseY  = _clamp(_octopus.baseY - py*0.55f, 28.0f, float(AQ_SEA_LEVEL_Y) - 44.0f);
        _octopus.y     -= py * 0.55f;
    }

    // ── Clock ─────────────────────────────────────────────────────────────────
    void updateClock() {
        unsigned long ms = millis();
        if (ms - _lastClockUpdateMs < 1000) return;
        _lastClockUpdateMs = ms;
        time_t now = time(nullptr);
        struct tm ti;
        localtime_r(&now, &ti);
        _clockHour   = ti.tm_hour;
        _clockMinute = ti.tm_min;
    }

    void drawClock() {
        char buf[8];
        snprintf(buf, sizeof(buf), "%02d:%02d", _clockHour, _clockMinute);
        _canvas.setTextSize(1);
        _canvas.setTextDatum(TC_DATUM);
        _canvas.setTextColor(AQ_CLOCK_COLOR);
        _canvas.drawString(buf, AQ_CANVAS_W / 2, AQ_CLOCK_Y);
    }

    // ── Gradient / Background ─────────────────────────────────────────────────
    static int _c5to8(int v) { return (v << 3) | (v >> 2); }
    static int _c6to8(int v) { return (v << 2) | (v >> 4); }

    static int _bayerT(int x, int y, int scale) {
        static const uint8_t kB[64] = {
             0,48,12,60, 3,51,15,63, 32,16,44,28,35,19,47,31,
             8,56, 4,52,11,59, 7,55, 40,24,36,20,43,27,39,23,
             2,50,14,62, 1,49,13,61, 34,18,46,30,33,17,45,29,
            10,58, 6,54, 9,57, 5,53, 42,26,38,22,41,25,37,21
        };
        return kB[((y/scale)&7)*8 + ((x/scale)&7)] << 2;
    }

    static uint16_t _rgb888to565(int r, int g, int b) {
        r = r < 0 ? 0 : (r > 255 ? 255 : r);
        g = g < 0 ? 0 : (g > 255 ? 255 : g);
        b = b < 0 ? 0 : (b > 255 ? 255 : b);
        return _RGB565(uint8_t(r), uint8_t(g), uint8_t(b));
    }

    static void _gradAtT(const uint16_t* colors, const uint8_t* stops, int n, int t255,
                          int& r8, int& g8, int& b8) {
        if (n <= 0) { r8=g8=b8=0; return; }
        auto ext = [](uint16_t c, int& r, int& g, int& b) {
            r = _c5to8((c>>11)&0x1F); g = _c6to8((c>>5)&0x3F); b = _c5to8(c&0x1F);
        };
        if (t255 <= stops[0])   { ext(colors[0],   r8,g8,b8); return; }
        if (t255 >= stops[n-1]) { ext(colors[n-1], r8,g8,b8); return; }
        for (int i = 1; i < n; ++i) {
            if (t255 <= stops[i]) {
                int seg = stops[i] - stops[i-1];
                int blend = seg > 0 ? ((t255 - stops[i-1])*255)/seg : 255;
                int inv = 255 - blend;
                int r0,g0,b0,r1,g1,b1;
                ext(colors[i-1],r0,g0,b0); ext(colors[i],r1,g1,b1);
                r8=(r0*inv+r1*blend)/255; g8=(g0*inv+g1*blend)/255; b8=(b0*inv+b1*blend)/255;
                return;
            }
        }
    }

    void _buildGradTile(const uint16_t* colors, const uint8_t* stops, int n) {
        int gradH = AQ_BACKGROUND_GRADIENT_H;
        for (int y = 0; y < gradH; ++y) {
            int base = (y * 255) / (gradH - 1);
            for (int x = 0; x < 32; ++x) {
                int thr = _bayerT(x, y, 4) - 128;
                int t = base + (thr * 28) / 128;
                t = t < 0 ? 0 : (t > 255 ? 255 : t);
                int r,g,b;
                _gradAtT(colors, stops, n, t, r, g, b);
                uint16_t c = _rgb888to565(r,g,b);
                _gradTile[y][x] = uint16_t((c<<8)|(c>>8));
            }
        }
    }

    void drawBackground() {
        static const uint8_t  kStops[] = {0,18,42,74,112,156,204,232,255};
        static const uint16_t kBlue[]  = {
            _RGB565(0,8,255), _RGB565(0,6,228), _RGB565(0,5,198),
            _RGB565(0,4,164), _RGB565(0,3,126), _RGB565(0,2,90),
            _RGB565(0,1,58),  _RGB565(0,0,30),  0x0000,
        };
        _canvas.fillSprite(AQ_BG_COLOR);
        int gradH = AQ_BACKGROUND_GRADIENT_H;
        if (!_gradientBandCached) {
            _buildGradTile(kBlue, kStops, 9);
            _gradientBandCached = true;
        }
        uint16_t rowBuf[AQ_CANVAS_W];
        for (int y = 0; y < gradH; ++y) {
            for (int x = 0; x < AQ_CANVAS_W; ++x)
                rowBuf[x] = _gradTile[y][x & 31];
            _canvas.pushImage(0, y, AQ_CANVAS_W, 1, rowBuf);
        }
    }

    // ── Seaweed ───────────────────────────────────────────────────────────────
    void _seaweedBranches(int bi, float bh, float scale, uint8_t pi,
                          float t, float bx, int y0_world, int stripY) {
        int bc = _clamp(int(bh / 14.0f), 2, 5);
        for (int b = 0; b < bc; ++b) {
            float u = 0.30f + b * 0.14f + ((bi + b) % 3) * 0.018f;
            if (u > 0.88f) u = 0.88f;
            int seg = int(u * float(kSeaweedSegs - 1) + 0.5f);
            if (seg >= kSeaweedSegs) seg = kSeaweedSegs - 1;
            float px = bx + (int8_t)pgm_read_byte(&kSeaweedDisp[pi][seg]) * scale;
            float py = float(y0_world) - bh * u - float(stripY);
            float side = ((bi + b) & 1) ? 1.0f : -1.0f;
            float bl   = 5.5f + float((bi * 3 + b * 5) % 5);
            float bwig = lut_sin(t * (1.1f + bi * 0.03f) * AQ_SWAY + bi + b * 1.7f) * 1.2f;
            int ex = int(px + side * bl * 0.58f + bwig);
            int ey = int(py - bl * 0.78f);
            _canvas.drawLine(int(px), int(py), ex, ey, (b & 1) ? TFT_DARKGREEN : TFT_GREEN);
        }
    }

    void drawSeaweed(float t, int stripY) {
        const int y0 = AQ_CANVAS_H - 2;    // 238 — world y of seaweed roots
        for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
            float bx    = _seaweedBaseX[i];
            float hv    = 1.0f + AQ_SEAWEED_RAND * kHeightNoise[i];
            float bh    = _clamp(32.0f * AQ_SEAWEED_LEN * hv, 18.0f, 72.0f);
            float scale = bh / 50.0f;
            uint8_t pi  = _seaweedPhaseIdx(i, t);
            float px = bx, py = float(y0 - stripY);
            for (int s = 1; s < kSeaweedSegs; ++s) {
                float nx = bx + (int8_t)pgm_read_byte(&kSeaweedDisp[pi][s]) * scale;
                float ny = float(y0) - bh * s / float(kSeaweedSegs - 1) - float(stripY);
                uint16_t col = (s < 3) ? TFT_DARKGREEN : (s < 6) ? TFT_GREEN : TFT_GREENYELLOW;
                _canvas.drawLine(int(px), int(py), int(nx), int(ny), col);
                if (s < 6)
                    _canvas.drawLine(int(px)+1, int(py), int(nx)+1, int(ny), TFT_DARKGREEN);
                px = nx; py = ny;
            }
            _seaweedBranches(i, bh, scale, pi, t, bx, y0, stripY);
        }
    }

    // ── Draw entities ─────────────────────────────────────────────────────────
    void drawFlakes(TFT_eSprite& canvas, int stripY) {
        canvas.setTextSize(1);
        canvas.setTextDatum(MC_DATUM);
        for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
            if (!_flakes[i].active) continue;
            canvas.setTextColor(_flakes[i].color);
            canvas.drawString("*", int(_flakes[i].x), int(_flakes[i].y) - stripY);
        }
    }

    void drawBubbles(TFT_eSprite& canvas, int zoneY) {
        canvas.setTextSize(1);
        canvas.setTextDatum(MC_DATUM);
        for (int i = 0; i < AQ_BUBBLE_COUNT; ++i) {
            if (!_bubbles[i].active) continue;
            canvas.setTextColor(_bubbles[i].color);
            canvas.drawString("o", int(_bubbles[i].x), int(_bubbles[i].y) - zoneY);
        }
    }

    void drawFish(int stripY) {
        _canvas.setTextFont(2);
        _canvas.setTextSize(1);
        _canvas.setTextDatum(TL_DATUM);
        const float t = _timeSec();
        uint32_t nowMs = millis();
        static const float kSin = lut_sin(FISH_SWIM_WAVE_SPACING);
        static const float kCos = lut_cos(FISH_SWIM_WAVE_SPACING);
        const int fontH = (int)_canvas.fontHeight();
        for (int i = 0; i < _activeFish; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;
            const char*    right   = _species()[f.type].right;
            const uint8_t* cw      = _fishCharWidthRight[f.type];
            uint8_t        len     = _fishGlyphLenRight[f.type];
            bool           goRight = (f.vx >= 0.0f);
            bool  fleeing  = (f.fleeUntilMs != 0 && nowMs < f.fleeUntilMs);
            float waveSpd  = fleeing ? FISH_SWIM_WAVE_SPEED_FLEE : FISH_SWIM_WAVE_SPEED;
            float angle    = t * waveSpd + f.phase;
            float wave   = lut_sin(angle);
            float waveC  = lut_cos(angle);
            _canvas.setTextColor(f.renderColor);
            int16_t xpos = 0;
            for (uint8_t c = 0; c < len; ++c) {
                uint8_t rc = goRight ? c : uint8_t(len - 1 - c);
                char    gl = goRight ? right[rc] : _mirrorBracket(right[rc]);
                if (gl != ' ') {
                    float yo       = wave * FISH_SWIM_WAVE_AMPLITUDE;
                    int   cx2      = int(f.x) + xpos;
                    int   cy2      = int(f.y) + int(yo + (yo >= 0.0f ? 0.5f : -0.5f));
                    int   cy2_local = cy2 - stripY;
                    if (cy2_local >= -fontH && cy2_local < AQ_STRIP_H)
                        _canvas.drawChar(uint16_t(gl), cx2, cy2_local);
                }
                xpos += int16_t(cw[rc]);
                float nw = wave*kCos + waveC*kSin;
                waveC = waveC*kCos - wave*kSin;
                wave = nw;
            }
        }
    }

    void drawOctopus(int stripY) {
        if (!_octopus.active) return;
        float t  = _timeSec();
        int   cx = int(_octopus.x), cy = int(_octopus.y) - stripY;
        int   r  = 205 + int(42.0f * lut_sin(t*0.18f + _octopus.colorPhase));
        int   g  = 78  + int(38.0f * lut_sin(t*0.13f + _octopus.colorPhase + 2.1f));
        int   b  = 178 + int(58.0f * lut_sin(t*0.16f + _octopus.colorPhase + 4.2f));
        _canvas.setTextSize(1);
        _canvas.setTextDatum(TL_DATUM);
        _canvas.setTextColor(_rgb888to565(r,g,b));
        float tw = lut_sin(t*1.25f + _octopus.phase) * 1.4f;
        _canvas.drawChar('(', cx-13, cy + int(tw));
        _canvas.drawChar('.', cx- 3, cy - 5);
        _canvas.drawChar('.', cx+ 7, cy - 5);
        _canvas.drawChar(')', cx+16, cy - int(tw));
        static const char  tg[] = {'(','(','(',')',')',')'};
        static const int   tx[] = {-24,-16,-8,2,10,18};
        for (int i = 0; i < 6; ++i) {
            float w = lut_sin(t*1.75f + _octopus.phase + i*0.72f);
            _canvas.drawChar(uint16_t(tg[i]), cx+tx[i]+int(w*1.4f), cy+13+int(w*2.2f));
        }
    }

    static char _mirrorHorse(char c) {
        switch (c) {
            case '/':  return '\\'; case '\\': return '/';
            case '[':  return ']';  case ']':  return '[';
            case '(':  return ')';  case ')':  return '(';
            case '<':  return '>';  case '>':  return '<';
            default:   return c;
        }
    }

    void drawSeahorse(int stripY) {
        if (!_seahorse.active) return;
        static const char* rows[] = {
            "  ^^  ", " / o) ", "[__-/ ",
            "  /|  ", " / |  ", " \\ |  ",
            "  ( ) ", "  \\_/ ",
        };
        float t  = _timeSec();
        int   x  = int(_seahorse.x), y = int(_seahorse.y) - stripY;
        int   sw = int(lut_sin(t*1.15f + _seahorse.phase) * 1.2f);
        int   ff = int(lut_sin(t*10.0f + _seahorse.finPhase) * 1.2f);
        int   r  = 238 + int(12.0f * lut_sin(t*0.11f + _seahorse.phase));
        int   g  = 142 + int(18.0f * lut_sin(t*0.16f + _seahorse.phase + 1.4f));
        int   b  = 48  + int(12.0f * lut_sin(t*0.13f + _seahorse.phase + 2.8f));
        _canvas.setTextSize(1);
        _canvas.setTextFont(1);
        _canvas.setTextDatum(TL_DATUM);
        _canvas.setTextColor(_rgb888to565(r,g,b));
        for (int row = 0; row < 8; ++row) {
            const char* line = rows[row];
            int len = strlen(line);
            int rsw = (row >= 1 && row <= 3) ? sw : 0;
            for (int col = 0; col < 6; ++col) {
                char gl = (col < len) ? line[col] : ' ';
                if (gl == ' ') continue;
                int dc = col;
                if (_seahorse.facingRight) { dc = 5 - col; gl = _mirrorHorse(gl); }
                _canvas.drawChar(uint16_t(gl), x + dc*5 + rsw, y + row*6);
            }
        }
        _canvas.setTextColor(_rgb888to565(255,188,82));
        int finX = _seahorse.facingRight ? x+5+ff : x+20+ff;
        const char* fin = (lut_sin(t*12.0f + _seahorse.finPhase) > 0.0f) ? "~" : "-";
        _canvas.drawString(fin, finX, y+24);
        _canvas.setTextFont(2);
    }

    // ── Seaweed init ──────────────────────────────────────────────────────────
    void initSeaweed() {
        for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
            _seaweedBaseX[i] = 10.0f + i * (AQ_CANVAS_W - 20.0f) / float(AQ_SEAWEED_ROOTS - 1);
            _seaweedSpeed[i] = (0.8f + 0.09f * i) * AQ_SWAY;
            _seaweedPhase[i] = (i * 0.7f) * kSeaweedPhasesPerRad;
        }
    }

    uint8_t _seaweedPhaseIdx(int i, float t) const {
        return (uint8_t)(int(t * _seaweedSpeed[i] * kSeaweedPhasesPerRad
                            + _seaweedPhase[i]) & (kSeaweedPhases - 1));
    }

    // ── Crab ──────────────────────────────────────────────────────────────────
    void initCrab() {
        _canvas.setTextFont(2);
        _crabBodyW = (int16_t)_canvas.textWidth("v(._.)v");
        uint32_t now           = millis();
        _crab.x                = AQ_CANVAS_W * 0.5f;
        _crab.y                = float(CRAB_Y);
        _crab.vy               = _frand(-CRAB_VY_MAX_PX_S, CRAB_VY_MAX_PX_S);
        _crab.direction        = 1;
        _crab.state            = Crab::State::WALK;
        _crab.walkFrame        = 0;
        _crab.pinchFrame       = 0;
        _crab.sleepZFrame      = 0;
        _crab.cuteDurationMs   = CRAB_CUTE_IDLE_MS;
        _crab.stateEnteredMs   = now;
        _crab.walkFrameMs      = now;
        _crab.pinchFrameMs     = now;
        _crab.sleepZFrameMs    = now;
        _crab.lastTargetSeenMs = now;
        _crab.sleepDurationMs  = 0;
        _crab.satiatedUntilMs  = 0;
        _crab.phase            = _frand(0.0f, 6.28318f);
        _crab.legWaveIntensity = 1.0f;
    }

    // Returns fish pool index of nearest fish in pinch range, or -1.
    int findPinchTarget() {
        float cx = _crab.x;
        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            if (_fishPool[i].active &&
                fabsf(_fishPool[i].x - cx) < float(CRAB_PINCH_RANGE_PX) &&
                _fishPool[i].y > float(CRAB_BOTTOM_ZONE_Y))
                return i;
        }
        return -1;
    }

    void _scatterFish(int cx, int cy) {
        uint32_t now = millis();
        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;
            float dx = f.x - float(cx);
            float dy = f.y - float(cy);
            float dist = sqrtf(dx * dx + dy * dy);
            if (dist > CRAB_SCATTER_RADIUS_PX) continue;
            float nx = (dist > 0.5f) ? dx / dist : (f.x < float(cx) ? -1.0f : 1.0f);
            float ny = (dist > 0.5f) ? dy / dist : -1.0f;
            ny *= CRAB_SCATTER_Y_BIAS;
            float blen = sqrtf(nx*nx + ny*ny);
            if (blen > 0.01f) { nx /= blen; ny /= blen; }
            f.vx = nx * CRAB_SCATTER_SPEED_PX_S;
            f.vy = ny * CRAB_SCATTER_SPEED_PX_S;
            f.fleeUntilMs = now + CRAB_SCATTER_FLEE_MS;
        }
    }

    void updateCrab(float dt) {
        uint32_t now = millis();
        Crab& c = _crab;

        if (c.state == Crab::State::CUTE) {
            if (now - c.stateEnteredMs >= c.cuteDurationMs) {
                if (c.sleepDurationMs > 0) {
                    c.state = Crab::State::SLEEP;
                } else {
                    c.state = Crab::State::WALK;
                }
                c.stateEnteredMs = now;
                c.sleepZFrameMs  = now;
                c.sleepZFrame    = 0;
            }
            float waveTarget = CRAB_LEG_WAVE_IDLE_SCALE;
            c.legWaveIntensity += (waveTarget - c.legWaveIntensity) * CRAB_LEG_WAVE_LERP_RATE * dt;
            return;
        }

        if (c.state == Crab::State::SLEEP) {
            if (now - c.sleepZFrameMs >= CRAB_SLEEP_Z_MS) {
                c.sleepZFrame = (c.sleepZFrame + 1) % CRAB_SLEEP_Z_COUNT;
                c.sleepZFrameMs = now;
            }
            bool targetNear = false;
            for (int i = 0; i < AQ_FLAKE_MAX && !targetNear; ++i)
                if (_flakes[i].active && fabsf(_flakes[i].x - c.x) < float(CRAB_PINCH_RANGE_PX) && _flakes[i].y > float(CRAB_BOTTOM_ZONE_Y))
                    targetNear = true;
            uint32_t sleepLimit = (c.sleepDurationMs > 0) ? c.sleepDurationMs : CRAB_SLEEP_MS;
            if (targetNear || now - c.stateEnteredMs >= sleepLimit) {
                if (c.sleepDurationMs > 0)
                    c.satiatedUntilMs = now + CRAB_SATIATED_MS;
                c.sleepDurationMs  = 0;
                c.state            = Crab::State::WALK;
                c.stateEnteredMs   = now;
                c.lastTargetSeenMs = now;
            }
            float waveTarget = CRAB_LEG_WAVE_IDLE_SCALE;
            c.legWaveIntensity += (waveTarget - c.legWaveIntensity) * CRAB_LEG_WAVE_LERP_RATE * dt;
            return;
        }

        if (c.state == Crab::State::PINCH_L || c.state == Crab::State::PINCH_R) {
            uint32_t elapsed = now - c.pinchFrameMs;
            if (c.pinchFrame < 3 && elapsed >= CRAB_PINCH_FRAME_MS) {
                c.pinchFrame++;
                c.pinchFrameMs = now;
            } else if (c.pinchFrame == 3 && elapsed >= CRAB_PINCH_HOLD_MS) {
                int hitFish = findPinchTarget();
                int hitFlake = -1;
                if (hitFish < 0) {
                    for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
                        if (_flakes[i].active &&
                            fabsf(_flakes[i].x - c.x) < float(CRAB_PINCH_RANGE_PX) &&
                            _flakes[i].y > float(CRAB_BOTTOM_ZONE_Y)) {
                            hitFlake = i;
                            break;
                        }
                    }
                }
                if (hitFish >= 0) {
                    bool hitLands = (random(CRAB_FISH_HIT_CHANCE) == 0);
                    if (hitLands) {
                        int fw = _clamp((int)_fishPool[hitFish].visualWidth,
                                        CRAB_MEAL_FISH_W_MIN, CRAB_MEAL_FISH_W_MAX);
                        c.sleepDurationMs = CRAB_MEAL_SLEEP_MIN_MS
                            + uint32_t((fw - CRAB_MEAL_FISH_W_MIN)
                                       * (CRAB_MEAL_SLEEP_MAX_MS - CRAB_MEAL_SLEEP_MIN_MS)
                                       / (CRAB_MEAL_FISH_W_MAX - CRAB_MEAL_FISH_W_MIN));
                        _fishPool[hitFish].active = false;
                        c.state = Crab::State::CUTE;
                        c.cuteDurationMs = CRAB_CUTE_HIT_MS;
                    } else {
                        c.state = Crab::State::WALK;
                    }
                } else if (hitFlake >= 0) {
                    _flakes[hitFlake].active = false;
                    c.state = Crab::State::CUTE;
                    c.cuteDurationMs = CRAB_CUTE_HIT_MS;
                } else {
                    c.state = Crab::State::WALK;
                }
                _scatterFish((int)c.x + _crabBodyW / 2, (int)c.y);
                c.pinchFrame     = 0;
                c.stateEnteredMs = now;
            }
            float waveTarget = CRAB_LEG_WAVE_IDLE_SCALE;
            c.legWaveIntensity += (waveTarget - c.legWaveIntensity) * CRAB_LEG_WAVE_LERP_RATE * dt;
            return;
        }

        // WALK state — proximity scan
        bool anyTarget = false;
        int pinchFlake = -1, pinchFish = -1;
        for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
            if (_flakes[i].active && fabsf(_flakes[i].x - c.x) < float(CRAB_PINCH_RANGE_PX) && _flakes[i].y > float(CRAB_BOTTOM_ZONE_Y)) {
                anyTarget = true;
                if (pinchFlake < 0) pinchFlake = i;
            }
        }
        bool satiated = (c.satiatedUntilMs != 0) && (now < c.satiatedUntilMs);
        if (!satiated) {
            for (int i = 0; i < AQ_FISH_COUNT; ++i) {
                if (_fishPool[i].active && fabsf(_fishPool[i].x - c.x) < float(CRAB_PINCH_RANGE_PX) && _fishPool[i].y > float(CRAB_BOTTOM_ZONE_Y)) {
                    anyTarget = true;
                    if (pinchFish < 0) pinchFish = i;
                }
            }
        }
        if (anyTarget) c.lastTargetSeenMs = now;

        if (now - c.lastTargetSeenMs >= CRAB_IDLE_SLEEP_MS) {
            c.satiatedUntilMs = 0;
            c.state           = Crab::State::SLEEP;
            c.stateEnteredMs  = now;
            c.sleepZFrameMs   = now;
            c.sleepZFrame     = 0;
            return;
        }

        if (pinchFlake >= 0 || pinchFish >= 0) {
            float targetX = (pinchFlake >= 0) ? _flakes[pinchFlake].x : _fishPool[pinchFish].x;
            c.state       = (targetX >= c.x) ? Crab::State::PINCH_R : Crab::State::PINCH_L;
            c.pinchFrame  = 0;
            c.pinchFrameMs = now;
            c.stateEnteredMs = now;
            return;
        }

        if (!anyTarget && float(random(0, 10000)) < CRAB_CUTE_CHANCE * 10000.0f) {
            c.state          = Crab::State::CUTE;
            c.cuteDurationMs = CRAB_CUTE_IDLE_MS;
            c.stateEnteredMs = now;
            return;
        }

        // Walk movement + edge reversal
        float nextX  = c.x + float(c.direction) * CRAB_SPEED_PX_S * dt;
        float minX   = float(CRAB_MARGIN_PX);
        float maxX   = float(AQ_CANVAS_W - CRAB_W_PX - CRAB_MARGIN_PX);
        if (nextX < minX) { nextX = minX; c.direction =  1; c.vy = _frand(-CRAB_VY_MAX_PX_S, CRAB_VY_MAX_PX_S); }
        if (nextX > maxX) { nextX = maxX; c.direction = -1; c.vy = _frand(-CRAB_VY_MAX_PX_S, CRAB_VY_MAX_PX_S); }
        c.x = nextX;

        c.y += c.vy * dt;
        c.y = _clamp(c.y, float(CRAB_Y_MIN), float(CRAB_Y_MAX));
        if (c.y <= float(CRAB_Y_MIN) || c.y >= float(CRAB_Y_MAX)) c.vy = -c.vy;

        if (now - c.walkFrameMs >= CRAB_WALK_STEP_MS) {
            c.walkFrame   = (c.walkFrame + (c.direction > 0 ? 1u : 3u)) & 3u;
            c.walkFrameMs = now;
        }

        c.legWaveIntensity += (1.0f - c.legWaveIntensity) * CRAB_LEG_WAVE_LERP_RATE * dt;
    }

    void drawCrab(int stripY) {
        int localBodyY = (int)_crab.y - stripY;
        // 51 = CRAB_SLEEP_BASE_Y + (CRAB_SLEEP_Z_COUNT-1)*CRAB_SLEEP_STEP_PX + CRAB_CHAR_H
        static constexpr int kCrabDrawReach = CRAB_SLEEP_BASE_Y
                                            + (CRAB_SLEEP_Z_COUNT - 1) * CRAB_SLEEP_STEP_PX
                                            + CRAB_CHAR_H;
        if (localBodyY <= -CRAB_CHAR_H || localBodyY >= AQ_STRIP_H + kCrabDrawReach) return;

        static const char* kLegFrames[4] = { ".,,,", ",.,," , ",,.," , ",,,."};

        _canvas.setTextFont(2);
        _canvas.setTextSize(1);
        _canvas.setTextDatum(TL_DATUM);
        _canvas.setTextColor(TFT_RED);

        int cx        = (int)_crab.x;
        int crabRight = cx + _crabBodyW;
        int drawCx    = cx;
        int bodyW     = (int)_crabBodyW;
        int ly = localBodyY + CRAB_LEG_OVERLAP_PX;

        switch (_crab.state) {
            case Crab::State::WALK:
                _canvas.drawString("v(._.)v", cx, localBodyY);
                break;
            case Crab::State::CUTE: {
                uint32_t elapsed = millis() - _crab.stateEnteredMs;
                bool showCute = ((elapsed / CRAB_CUTE_BLINK_MS) % 2) == 1;
                _canvas.drawString(showCute ? "v(^.^)v" : "v(._.)v", cx, localBodyY);
                break;
            }
            case Crab::State::SLEEP:
                _canvas.drawString("v(-.-)v", cx, localBodyY);
                break;
            case Crab::State::PINCH_R:
                switch (_crab.pinchFrame) {
                    case 0: _canvas.drawString("v(._.)v",  cx, localBodyY); break;
                    case 1: _canvas.drawString("v(o_o)v",  cx, localBodyY); break;
                    case 2:
                        _canvas.drawString("v(o_O) ",  cx, localBodyY);
                        _canvas.drawString("V", cx + 6 * CRAB_CHAR_W, localBodyY - CRAB_CLAW_RISE_PX);
                        break;
                    case 3: _canvas.drawString("v(o_o(|)", cx, localBodyY); break;
                }
                break;
            case Crab::State::PINCH_L: {
                const char* frameBody = nullptr;
                switch (_crab.pinchFrame) {
                    case 0: frameBody = "v(._.)v";   break;
                    case 1: frameBody = "v(o_o)v";   break;
                    case 2: frameBody = " (O_o)v";   break;
                    case 3: frameBody = "(|)(o_o)v"; break;
                }
                bodyW  = (int)_canvas.textWidth(frameBody);
                drawCx = crabRight - bodyW;
                _canvas.drawString(frameBody, drawCx, localBodyY);
                if (_crab.pinchFrame == 2)
                    _canvas.drawString("V", drawCx, localBodyY - CRAB_CLAW_RISE_PX);
                break;
            }
        }

        bool walking = (_crab.state == Crab::State::WALK);
        const char* leftLegs  = walking ? kLegFrames[_crab.walkFrame]           : ",,,,";
        const char* rightLegs = walking ? kLegFrames[(_crab.walkFrame + 2) & 3] : ",,,,";
        int lx = cx + CRAB_CHAR_W;
        int rx = cx + (int)_crabBodyW - CRAB_CHAR_W - CRAB_LEG_CHAR_W * 4;

        float effectiveAmp   = CRAB_LEG_WAVE_AMP   * _crab.legWaveIntensity;
        float effectiveSpeed = CRAB_LEG_WAVE_SPEED  * _crab.legWaveIntensity;
        float waveBase = _timeSec() * effectiveSpeed + _crab.phase;
        float wave  = lut_sin(waveBase);
        float waveC = lut_cos(waveBase);
        static const float kLegSin = lut_sin(CRAB_LEG_WAVE_SPACING);
        static const float kLegCos = lut_cos(CRAB_LEG_WAVE_SPACING);

        _canvas.setTextColor(CRAB_LEG_COLOR);
        for (int i = 0; i < 4; ++i) {
            int yo = (int)(wave * effectiveAmp);
            _canvas.drawChar(uint16_t(leftLegs[i]), lx + i * CRAB_LEG_CHAR_W, ly + yo);
            float nw = wave * kLegCos + waveC * kLegSin;
            waveC = waveC * kLegCos - wave * kLegSin;
            wave = nw;
        }
        for (int i = 0; i < 4; ++i) {
            int yo = (int)(wave * effectiveAmp);
            _canvas.drawChar(uint16_t(rightLegs[i]), rx + i * CRAB_LEG_CHAR_W, ly + yo);
            float nw = wave * kLegCos + waveC * kLegSin;
            waveC = waveC * kLegCos - wave * kLegSin;
            wave = nw;
        }
        _canvas.setTextColor(TFT_RED);

        if (_crab.state == Crab::State::SLEEP) {
            float nowSec = millis() * 0.001f;
            int   zx     = cx + 3 * CRAB_CHAR_W;
            _canvas.setTextColor(CRAB_SLEEP_Z_COLOR);
            for (int i = 0; i < CRAB_SLEEP_Z_COUNT; ++i) {
                int   zy    = localBodyY - CRAB_SLEEP_BASE_Y - i * CRAB_SLEEP_STEP_PX;
                float phase = float(i) * CRAB_SLEEP_SWAY_PHASE;
                float ang   = nowSec * CRAB_SLEEP_SWAY_SPEED + phase;
                float swayX = lut_sin(ang) * CRAB_SLEEP_SWAY_AMP;
                float swayY = lut_cos(ang) * CRAB_SLEEP_SWAY_Y_AMP;
                char  ch    = (i == (int)_crab.sleepZFrame) ? 'Z' : 'z';
                _canvas.drawChar(uint16_t(ch), zx + (int)swayX, zy + (int)swayY);
            }
            _canvas.setTextColor(TFT_RED);
        }
    }

    // ── Render ────────────────────────────────────────────────────────────────
    void renderFrame() {
        float t = _timeSec();

        // 6 strip passes covering y:0..239
        for (int s = 0; s < AQ_STRIP_COUNT; ++s) {
            int sy = s * AQ_STRIP_H;
            _canvas.fillSprite(AQ_BG_COLOR);
            if (s == 0) { drawBackground(); drawClock(); }
            drawBubbles(_canvas, sy);
            drawFlakes(_canvas, sy);
            drawSeaweed(t, sy);
            drawCrab(sy);
            drawFish(sy);
            drawOctopus(sy);
            drawSeahorse(sy);
            _canvas.pushSprite(0, sy);
        }
    }
};

// lut_sin(i * 2.173f + 0.61f) for i = 0..11 — placed in .rodata (flash), zero DRAM cost
const float AquariumApp::kHeightNoise[AquariumApp::AQ_SEAWEED_ROOTS] = {
     0.5729f,  0.3510f, -0.9705f,  0.7485f,  0.1225f, -0.8873f,
     0.8827f, -0.1128f, -0.7549f,  0.9681f, -0.3418f, -0.5808f,
};

// 32-phase × 8-segment canonical seaweed displacement LUT (CRAB-FIX-004).
// Generated by Python: bh=50, amp=7, AQ_SWAY=1.10. Range -5..+8 px (fits int8_t).
// At render time: nx = bx + pgm_read_byte(&kSeaweedDisp[phaseIdx][seg]) * (bh/50).
const int8_t AquariumApp::kSeaweedDisp[32][8] PROGMEM = {
    {   0,    0,    0,   -1,   -1,    1,    4,    4},
    {   0,    0,    0,   -1,   -1,    2,    5,    6},
    {   0,    0,    0,   -1,    0,    2,    5,    7},
    {   0,    0,    0,    0,    0,    2,    5,    7},
    {   0,    0,    0,    0,    0,    2,    5,    8},
    {   0,    0,    0,    0,    0,    2,    5,    8},
    {   0,    0,    1,    0,    1,    2,    5,    8},
    {   0,    0,    1,    1,    1,    2,    4,    7},
    {   0,    0,    1,    1,    1,    3,    4,    7},
    {   0,    0,    1,    1,    2,    3,    3,    6},
    {   0,    0,    1,    1,    2,    3,    3,    5},
    {   0,    0,    1,    1,    2,    2,    2,    3},
    {   0,    0,    1,    2,    2,    2,    1,    2},
    {   0,    0,    1,    2,    3,    2,    1,    1},
    {   0,    0,    1,    2,    3,    2,    0,   -1},
    {   0,    0,    0,    2,    3,    2,    0,   -2},
    {   0,    0,    0,    1,    3,    2,   -1,   -3},
    {   0,    0,    0,    1,    2,    2,   -1,   -4},
    {   0,    0,    0,    1,    2,    1,   -2,   -4},
    {   0,    0,    0,    1,    2,    1,   -2,   -5},
    {   0,    0,    0,    0,    1,    0,   -2,   -5},
    {   0,    0,   -1,    0,    1,    0,   -2,   -5},
    {   0,    0,   -1,    0,    0,   -1,   -2,   -5},
    {   0,    0,   -1,   -1,    0,   -1,   -3,   -5},
    {   0,   -1,   -1,   -1,   -1,   -2,   -3,   -4},
    {   0,   -1,   -1,   -1,   -2,   -2,   -3,   -4},
    {   0,   -1,   -1,   -1,   -2,   -3,   -3,   -3},
    {   0,   -1,   -1,   -2,   -3,   -3,   -3,   -3},
    {   0,    0,   -1,   -2,   -3,   -4,   -3,   -2},
    {   0,    0,   -1,   -2,   -3,   -4,   -3,   -1},
    {   0,    0,   -1,   -2,   -4,   -4,   -3,   -1},
    {   0,    0,   -1,   -2,   -4,   -4,   -3,    0},
};
