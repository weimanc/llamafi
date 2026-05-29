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
        _spriteReady = (_canvas.createSprite(AQ_CANVAS_W, AQ_CANVAS_H) != nullptr);
        Serial.printf("[aquarium] init sprite %dx%d 8bpp: %s  heap=%lu maxAlloc=%lu\n",
            AQ_CANVAS_W, AQ_CANVAS_H,
            _spriteReady ? "OK" : "FAILED",
            (unsigned long)ESP.getFreeHeap(),
            (unsigned long)ESP.getMaxAllocHeap());
        _canvas.setTextFont(2);  // needed for glyph metrics regardless of alloc result

        initFishGlyphMetrics();
        applyFishPopulation();
        spreadInitialFishLayout();
        applyBubblePopulation(true);

        unsigned long now = millis();
        _lastTickMs   = now;
        _aquariumNowMs = now;
    }

    void resume() override {
        _retryShown  = false;
        _lastRetryMs = 0;
        _canvas.setColorDepth(8);
        _spriteReady = (_canvas.createSprite(AQ_CANVAS_W, AQ_CANVAS_H) != nullptr);
        Serial.printf("[aquarium] resume sprite: %s  heap=%lu maxAlloc=%lu\n",
            _spriteReady ? "OK" : "FAILED",
            (unsigned long)ESP.getFreeHeap(),
            (unsigned long)ESP.getMaxAllocHeap());
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
            // Retry sprite allocation every 500 ms — SSL/TLS buffers may free up after
            // the first Spotify poll, giving us the contiguous 66 KB we need.
            unsigned long now2 = millis();
            if (now2 - _lastRetryMs >= 500) {
                _lastRetryMs = now2;
                _canvas.setColorDepth(8);
                _spriteReady = (_canvas.createSprite(AQ_CANVAS_W, AQ_CANVAS_H) != nullptr);
                if (_spriteReady) {
                    _canvas.setTextFont(2);
                    _lastTickMs = now2;
                    Serial.printf("[aquarium] retry succeeded  heap=%lu\n",
                        (unsigned long)ESP.getFreeHeap());
                } else {
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
        updateClock();
        updateFlakes(dt);
        updateBubbles(dt);
        updateFish(dt);
        updateOctopus(_aquariumNowMs, dt);
        updateSeahorse(_aquariumNowMs, dt);
        keepVisitorsSeparated();
        renderFrame();
    }

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase == TouchPhase::Press) {
            spawnFlake((float)x, (float)y);
            return true;
        }
        return false;
    }

private:
    // ── Constants ──────────────────────────────────────────────────────────
    static constexpr int   AQ_CANVAS_W            = 275;
    static constexpr int   AQ_CANVAS_H            = 240;
    static constexpr int   AQ_SEA_LEVEL_Y         = AQ_CANVAS_H - 8;
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
    static constexpr int   AQ_BACKGROUND_GRADIENT_H = AQ_CANVAS_H / 4;  // 60
    static constexpr int   AQ_CLOCK_Y             = 4;
    static constexpr uint16_t AQ_CLOCK_COLOR      = 0xFFFF;
    static constexpr uint16_t AQ_BG_COLOR         = 0x0000;
    static constexpr int   AQ_SEAWEED_ROOTS       = 12;
    static constexpr int   AQ_GLYPH_COUNT         = 12;
    static constexpr size_t AQ_GLYPH_BUF          = 28;

    // Physics constants (transcribed from upstream lines 300-327)
    static constexpr float FISH_SWIM_WAVE_AMPLITUDE     = 1.5f;
    static constexpr float FISH_SWIM_WAVE_SPEED         = 5.6f;
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

    // ── Members ──────────────────────────────────────────────────────────────
    TFT_eSprite   _canvas{&tft};
    bool          _spriteReady     = false;
    bool          _retryShown      = false;
    unsigned long _lastTickMs      = 0;
    unsigned long _lastRetryMs     = 0;
    unsigned long _aquariumNowMs   = 0;
    int           _clockHour       = 0;
    int           _clockMinute     = 0;

    Fish     _fishPool[AQ_FISH_POOL_MAX];
    Flake    _flakes[AQ_FLAKE_MAX];
    Bubble   _bubbles[AQ_BUBBLE_POOL_MAX];
    Octopus  _octopus;
    Seahorse _seahorse;

    uint16_t _gradTile[AQ_BACKGROUND_GRADIENT_H][32];
    bool     _gradientBandCached = false;

    static const float kHeightNoise[AQ_SEAWEED_ROOTS];

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
        return a + (b - a) * float(random(0, 10000)) / 9999.0f;
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
        f.y = _frand(20.0f, float(AQ_SEA_LEVEL_Y) - 10.0f);
        f.vx = _frand(-1.0f, 1.0f);
        f.vy = _frand(-0.5f, 0.5f);
        f.speed = uint8_t(_frand(14.0f, 30.0f));
        f.phase = _frand(0.0f, 6.28318f);
        f.wanderBias = _frand(0.4f, 1.3f);
    }

    void applyFishPopulation() {
        for (int i = 0; i < AQ_FISH_POOL_MAX; ++i) {
            bool want = (i < AQ_FISH_COUNT);
            if (want  && !_fishPool[i].active) _activateFish(_fishPool[i], true);
            if (!want &&  _fishPool[i].active) _fishPool[i].active = false;
        }
    }

    bool _spawnClear(int idx, float x, float y, float gx, float gy) {
        float cx = x + _fishPool[idx].visualWidth * 0.5f;
        float cy = y + FISH_CENTER_Y_OFFSET;
        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            if (i == idx || !_fishPool[i].active) continue;
            float ox = _fishPool[i].x + _fishPool[i].visualWidth * 0.5f;
            float oy = _fishPool[i].y + FISH_CENTER_Y_OFFSET;
            if (fabsf(ox - cx) < gx && fabsf(oy - cy) < gy) return false;
        }
        return true;
    }

    void spreadInitialFishLayout() {
        float gx = FISH_AVOID_RADIUS_X * 0.92f, gy = FISH_AVOID_RADIUS_Y * 1.05f;
        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;
            float bx = f.x, by = f.y;
            for (int a = 0; a < 80; ++a) {
                float cx = _frand(10.0f, AQ_CANVAS_W - f.visualWidth - 10.0f);
                float cy = _frand(18.0f, float(AQ_SEA_LEVEL_Y) - 18.0f);
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
            _flakes[i].x += sinf(t * 1.2f + i) * 8.0f * dt;
            if (_flakes[i].y > float(AQ_SEA_LEVEL_Y)) _flakes[i].active = false;
        }
    }

    void updateBubbles(float dt) {
        float t = _timeSec();
        for (int i = 0; i < AQ_BUBBLE_COUNT; ++i) {
            if (!_bubbles[i].active) continue;
            _bubbles[i].y -= _bubbles[i].vy * dt;
            _bubbles[i].x = _bubbles[i].baseX
                           + sinf(t * 1.8f + _bubbles[i].phase) * _bubbles[i].swayAmp;
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
        float sx = dx/OCTOPUS_FISH_AVOID_RADIUS_X, sy = dy/OCTOPUS_FISH_AVOID_RADIUS_Y;
        float sd2 = sx*sx + sy*sy;
        if (sd2 <= 0.0001f || sd2 >= 1.0f) return;
        float dist = sqrtf(dx*dx + dy*dy) + 0.0001f;
        float push = (1.0f - sd2); push *= push;
        f.vx += (dx/dist) * push * OCTOPUS_FISH_AVOID_STRENGTH * dt;
        f.vy += (dy/dist) * push * OCTOPUS_FISH_AVOID_STRENGTH * dt;
    }

    void _steerFromSeahorse(Fish& f, float fcx, float fcy, float dt) {
        if (!_seahorse.active) return;
        float hcx = _seahorse.x + SEAHORSE_CENTER_X_OFFSET;
        float hcy = _seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
        float dx = fcx - hcx, dy = fcy - hcy;
        float sx = dx/SEAHORSE_FISH_AVOID_RADIUS_X, sy = dy/SEAHORSE_FISH_AVOID_RADIUS_Y;
        float sd2 = sx*sx + sy*sy;
        if (sd2 <= 0.0001f || sd2 >= 1.0f) return;
        float dist = sqrtf(dx*dx + dy*dy) + 0.0001f;
        float push = (1.0f - sd2); push *= push;
        f.vx += (dx/dist) * push * SEAHORSE_FISH_AVOID_STRENGTH * dt;
        f.vy += (dy/dist) * push * SEAHORSE_FISH_AVOID_STRENGTH * dt;
    }

    void _pushOutOfOctopus(Fish& f) {
        if (!_octopus.active) return;
        float fcx = f.x + f.visualWidth*0.5f, fcy = f.y + FISH_CENTER_Y_OFFSET;
        float ocy = _octopus.y + OCTOPUS_CENTER_Y_OFFSET;
        float dx = fcx - _octopus.x, dy = fcy - ocy;
        float sx = dx/OCTOPUS_FISH_CLEAR_RADIUS_X, sy = dy/OCTOPUS_FISH_CLEAR_RADIUS_Y;
        float sd2 = sx*sx + sy*sy;
        if (sd2 >= 1.0f) return;
        if (sd2 <= 0.0001f) {
            dx = (f.vx >= 0.0f) ? 1.0f : -1.0f;
            dy = (f.vy >= 0.0f) ? 0.35f : -0.35f;
            sd2 = (dx/OCTOPUS_FISH_CLEAR_RADIUS_X)*(dx/OCTOPUS_FISH_CLEAR_RADIUS_X)
                + (dy/OCTOPUS_FISH_CLEAR_RADIUS_Y)*(dy/OCTOPUS_FISH_CLEAR_RADIUS_Y);
        }
        float scale = 1.0f / sqrtf(sd2);
        f.x += (_octopus.x + dx*scale - fcx) * 0.55f;
        f.y += (ocy        + dy*scale - fcy) * 0.55f;
    }

    void _pushOutOfSeahorse(Fish& f) {
        if (!_seahorse.active) return;
        float fcx = f.x + f.visualWidth*0.5f, fcy = f.y + FISH_CENTER_Y_OFFSET;
        float hcx = _seahorse.x + SEAHORSE_CENTER_X_OFFSET;
        float hcy = _seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
        float dx = fcx - hcx, dy = fcy - hcy;
        float sx = dx/SEAHORSE_FISH_CLEAR_RADIUS_X, sy = dy/SEAHORSE_FISH_CLEAR_RADIUS_Y;
        float sd2 = sx*sx + sy*sy;
        if (sd2 >= 1.0f) return;
        if (sd2 <= 0.0001f) {
            dx = (f.vx >= 0.0f) ? 1.0f : -1.0f;
            dy = (f.vy >= 0.0f) ? 0.35f : -0.35f;
            sd2 = (dx/SEAHORSE_FISH_CLEAR_RADIUS_X)*(dx/SEAHORSE_FISH_CLEAR_RADIUS_X)
                + (dy/SEAHORSE_FISH_CLEAR_RADIUS_Y)*(dy/SEAHORSE_FISH_CLEAR_RADIUS_Y);
        }
        float scale = 1.0f / sqrtf(sd2);
        f.x += (hcx + dx*scale - fcx) * 0.45f;
        f.y += (hcy + dy*scale - fcy) * 0.45f;
    }

    void updateFish(float dt) {
        const float t = _timeSec();
        float cx[AQ_FISH_POOL_MAX], cy[AQ_FISH_POOL_MAX];
        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            Fish& f = _fishPool[i];
            cx[i] = f.active ? f.x + f.visualWidth*0.5f : 0.0f;
            cy[i] = f.active ? f.y + FISH_CENTER_Y_OFFSET : 0.0f;
        }

        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;

            f.vx += cosf(f.phase + t*0.9f) * 0.45f * f.wanderBias * dt;
            f.vy += sinf(f.phase*1.7f + t*0.7f) * 0.22f * dt;

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
                float ssx = sdx/FISH_AVOID_RADIUS_X, ssy = sdy/FISH_AVOID_RADIUS_Y;
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
                avgVX /= nearCount; avgVY /= nearCount;
                scx /= nearCount;   scy /= nearCount;
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

            if (f.y < 18) f.vy += 0.8f * dt;
            if (f.y > float(AQ_SEA_LEVEL_Y) - 8) f.vy -= 0.8f * dt;

            float mag = sqrtf(f.vx*f.vx + f.vy*f.vy);
            if (mag < 0.0001f) { f.vx = 1.0f; f.vy = 0.0f; mag = 1.0f; }
            f.vx /= mag; f.vy /= mag;

            float spd = f.speed + sinf(t*3.2f + f.phase) * 4.0f;
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
            f.y = _clamp(f.y, 14.0f, float(AQ_SEA_LEVEL_Y) - 6.0f);
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
        _octopus.y  = _octopus.baseY + sinf(t*0.45f + _octopus.phase) * 6.0f;
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
        float pulse = 1.0f + sinf(t*0.55f + _seahorse.phase) * 0.18f;
        _seahorse.x += _seahorse.vx * pulse * dt;
        _seahorse.y  = _seahorse.baseY
                     + sinf(t*0.82f  + _seahorse.phase)        * 4.5f
                     + sinf(t*2.15f  + _seahorse.phase * 1.7f) * 0.9f;
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
        float sx = dx/VISITOR_CLEAR_RADIUS_X, sy = dy/VISITOR_CLEAR_RADIUS_Y;
        float sd2 = sx*sx + sy*sy;
        if (sd2 >= 1.0f) return;
        if (sd2 <= 0.0001f) {
            dx = (_seahorse.vx >= _octopus.vx) ? 1.0f : -1.0f;
            dy = 0.35f;
            sd2 = (dx/VISITOR_CLEAR_RADIUS_X)*(dx/VISITOR_CLEAR_RADIUS_X)
                + (dy/VISITOR_CLEAR_RADIUS_Y)*(dy/VISITOR_CLEAR_RADIUS_Y);
        }
        float scale = 1.0f / sqrtf(sd2);
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
        int gradH = AQ_CANVAS_H / 4;
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
        int gradH = AQ_CANVAS_H / 4;
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
    void _swayPoint(float u, float bx, int y0, float bh, float sw,
                    float phaseBody, float phaseRipple, float& ox, float& oy) {
        u = _clamp(u, 0.0f, 1.0f);
        float body   = sinf(phaseBody   - u*5.1f);
        float ripple = sinf(phaseRipple + u*9.0f);
        float bend   = sw * u * (0.20f + u*0.80f);
        float travel = body * (1.5f + bh*0.055f) * u * u;
        float detail = ripple * 1.2f * u;
        ox = bx + bend + travel + detail;
        oy = y0 - bh * u;
    }

    void _seaweedBranches(int bi, float bh, float sw,
                          float phaseBody, float phaseRipple, float t, float bx, int y0) {
        int bc = _clamp(int(bh/14.0f), 2, 5);
        for (int b = 0; b < bc; ++b) {
            float u = 0.30f + b*0.14f + ((bi+b)%3)*0.018f;
            if (u > 0.88f) u = 0.88f;
            float px, py;
            _swayPoint(u, bx, y0, bh, sw, phaseBody, phaseRipple, px, py);
            float side = ((bi+b)&1) ? 1.0f : -1.0f;
            float bl   = 5.5f + ((bi*3 + b*5) % 5);
            float bwig = sinf(t*(1.1f+bi*0.03f)*AQ_SWAY + bi + b*1.7f) * 1.2f;
            int ex = int(px + side*(bl*0.58f + fabsf(sw)*0.05f) + bwig);
            int ey = int(py - bl*0.78f);
            _canvas.drawLine(int(px), int(py), ex, ey, (b&1) ? TFT_DARKGREEN : TFT_GREEN);
        }
    }

    void drawSeaweed(float t) {
        for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
            float bx  = 10.0f + i * (AQ_CANVAS_W - 20.0f) / float(AQ_SEAWEED_ROOTS - 1);
            float amp = 5.0f + (i % 4) * 2.0f;
            float sw  = sinf(t*(0.8f+0.09f*i)*AQ_SWAY + i*0.7f) * amp;
            float hv  = 1.0f + AQ_SEAWEED_RAND * kHeightNoise[i];
            float bh  = _clamp(32.0f * AQ_SEAWEED_LEN * hv, 18.0f, 72.0f);
            int   y0  = AQ_CANVAS_H - 2;
            float phaseBody   = t * (1.05f + i*0.025f) * AQ_SWAY + i*0.72f;
            float phaseRipple = t * 0.72f * AQ_SWAY + i*1.31f;
            float px = bx, py = float(y0);
            for (int seg = 1; seg <= 7; ++seg) {
                float u = float(seg) / 7;
                float nx, ny;
                _swayPoint(u, bx, y0, bh, sw, phaseBody, phaseRipple, nx, ny);
                uint16_t col = (u < 0.38f) ? TFT_DARKGREEN
                             : (u < 0.76f) ? TFT_GREEN : TFT_GREENYELLOW;
                _canvas.drawLine(int(px), int(py), int(nx), int(ny), col);
                if (u < 0.78f)
                    _canvas.drawLine(int(px)+1, int(py), int(nx)+1, int(ny), TFT_DARKGREEN);
                px = nx; py = ny;
            }
            _seaweedBranches(i, bh, sw, phaseBody, phaseRipple, t, bx, y0);
        }
    }

    // ── Draw entities ─────────────────────────────────────────────────────────
    void drawFlakes() {
        _canvas.setTextSize(1);
        _canvas.setTextDatum(MC_DATUM);
        for (int i = 0; i < AQ_FLAKE_MAX; ++i) {
            if (!_flakes[i].active) continue;
            _canvas.setTextColor(_flakes[i].color);
            _canvas.drawString("*", int(_flakes[i].x), int(_flakes[i].y));
        }
    }

    void drawBubbles() {
        _canvas.setTextSize(1);
        _canvas.setTextDatum(MC_DATUM);
        for (int i = 0; i < AQ_BUBBLE_COUNT; ++i) {
            if (!_bubbles[i].active) continue;
            _canvas.setTextColor(_bubbles[i].color);
            _canvas.drawString("o", int(_bubbles[i].x), int(_bubbles[i].y));
        }
    }

    void drawFish() {
        _canvas.setTextFont(2);
        _canvas.setTextSize(1);
        _canvas.setTextDatum(TL_DATUM);
        const float t = _timeSec();
        const float waveBase = t * FISH_SWIM_WAVE_SPEED;
        static const float kSin = sinf(FISH_SWIM_WAVE_SPACING);
        static const float kCos = cosf(FISH_SWIM_WAVE_SPACING);
        for (int i = 0; i < AQ_FISH_COUNT; ++i) {
            Fish& f = _fishPool[i];
            if (!f.active) continue;
            const char*    right   = _species()[f.type].right;
            const uint8_t* cw      = _fishCharWidthRight[f.type];
            uint8_t        len     = _fishGlyphLenRight[f.type];
            bool           goRight = (f.vx >= 0.0f);
            float angle  = waveBase + f.phase;
            float wave   = sinf(angle);
            float waveC  = cosf(angle);
            _canvas.setTextColor(f.renderColor);
            int16_t xpos = 0;
            for (uint8_t c = 0; c < len; ++c) {
                uint8_t rc = goRight ? c : uint8_t(len - 1 - c);
                char    gl = goRight ? right[rc] : _mirrorBracket(right[rc]);
                if (gl != ' ') {
                    float yo  = wave * FISH_SWIM_WAVE_AMPLITUDE;
                    int   cx2 = int(f.x) + xpos;
                    int   cy2 = int(f.y) + int(yo + (yo >= 0.0f ? 0.5f : -0.5f));
                    _canvas.drawChar(uint16_t(gl), cx2, cy2);
                }
                xpos += int16_t(cw[rc]);
                float nw = wave*kCos + waveC*kSin;
                waveC = waveC*kCos - wave*kSin;
                wave = nw;
            }
        }
    }

    void drawOctopus() {
        if (!_octopus.active) return;
        float t  = _timeSec();
        int   cx = int(_octopus.x), cy = int(_octopus.y);
        int   r  = 205 + int(42.0f * sinf(t*0.18f + _octopus.colorPhase));
        int   g  = 78  + int(38.0f * sinf(t*0.13f + _octopus.colorPhase + 2.1f));
        int   b  = 178 + int(58.0f * sinf(t*0.16f + _octopus.colorPhase + 4.2f));
        _canvas.setTextSize(1);
        _canvas.setTextDatum(TL_DATUM);
        _canvas.setTextColor(_rgb888to565(r,g,b));
        float tw = sinf(t*1.25f + _octopus.phase) * 1.4f;
        _canvas.drawChar('(', cx-13, cy + int(tw));
        _canvas.drawChar('.', cx- 3, cy - 5);
        _canvas.drawChar('.', cx+ 7, cy - 5);
        _canvas.drawChar(')', cx+16, cy - int(tw));
        static const char  tg[] = {'(','(','(',')',')',')'};
        static const int   tx[] = {-24,-16,-8,2,10,18};
        for (int i = 0; i < 6; ++i) {
            float w = sinf(t*1.75f + _octopus.phase + i*0.72f);
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

    void drawSeahorse() {
        if (!_seahorse.active) return;
        static const char* rows[] = {
            "  ^^  ", " / o) ", "[__-/ ",
            "  /|  ", " / |  ", " \\ |  ",
            "  ( ) ", "  \\_/ ",
        };
        float t  = _timeSec();
        int   x  = int(_seahorse.x), y = int(_seahorse.y);
        int   sw = int(sinf(t*1.15f + _seahorse.phase) * 1.2f);
        int   ff = int(sinf(t*10.0f + _seahorse.finPhase) * 1.2f);
        int   r  = 238 + int(12.0f * sinf(t*0.11f + _seahorse.phase));
        int   g  = 142 + int(18.0f * sinf(t*0.16f + _seahorse.phase + 1.4f));
        int   b  = 48  + int(12.0f * sinf(t*0.13f + _seahorse.phase + 2.8f));
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
        const char* fin = (sinf(t*12.0f + _seahorse.finPhase) > 0.0f) ? "~" : "-";
        _canvas.drawString(fin, finX, y+24);
        _canvas.setTextFont(2);
    }

    // ── Render ────────────────────────────────────────────────────────────────
    void renderFrame() {
        float t = _timeSec();
        drawBackground();
        drawSeaweed(t);
        drawBubbles();
        drawFlakes();
        drawFish();
        drawOctopus();
        drawSeahorse();
        drawClock();
        _canvas.pushSprite(0, 0);
    }
};

// sinf(i * 2.173f + 0.61f) for i = 0..11 — placed in .rodata (flash), zero DRAM cost
const float AquariumApp::kHeightNoise[AquariumApp::AQ_SEAWEED_ROOTS] = {
     0.5729f,  0.3510f, -0.9705f,  0.7485f,  0.1225f, -0.8873f,
     0.8827f, -0.1128f, -0.7549f,  0.9681f, -0.3418f, -0.5808f,
};
