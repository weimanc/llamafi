#pragma once
#include <cmath>
#include <cstring>
#include <cstdint>

// 512-entry sin LUT in DRAM. 2 KB; demoscene-opt freed headroom (ADR-031).
extern float g_sinLUT[512];

void buildMathLUT();

// ~4–6 cycles vs ~80 for sinf. Max error ~0.006 at visual amplitudes (imperceptible).
static inline float lut_sin(float a) {
    int i = (int)(a * (512.0f / 6.28318f)) & 511;
    return g_sinLUT[i];
}
static inline float lut_cos(float a) { return lut_sin(a + 1.5707963f); }

// Quake III fast inverse sqrt. ~10–15 cycles vs ~80 for 1/sqrtf. ~3% max error.
static inline float q_rsqrt(float x) {
    float xh = 0.5f * x;
    int32_t i;
    memcpy(&i, &x, 4);
    i = 0x5f3759df - (i >> 1);
    memcpy(&x, &i, 4);
    return x * (1.5f - xh * x * x);
}

// HSV (each 0..255) → RGB (each 0..255). Integer-only.
struct RGB8 { uint8_t r, g, b; };
static inline RGB8 hsvToRgb(uint8_t h, uint8_t s, uint8_t v) {
    if (s == 0) { return { v, v, v }; }
    uint8_t region = h / 43u;
    uint8_t rem    = (uint8_t)((h - region * 43u) * 6u);
    uint8_t p = (uint8_t)((uint16_t)v * (255u - s) >> 8);
    uint8_t q = (uint8_t)((uint16_t)v * (255u - (((uint16_t)s * rem) >> 8)) >> 8);
    uint8_t t = (uint8_t)((uint16_t)v * (255u - (((uint16_t)s * (255u - rem)) >> 8)) >> 8);
    switch (region) {
        case 0:  return { v, t, p };
        case 1:  return { q, v, p };
        case 2:  return { p, v, t };
        case 3:  return { p, q, v };
        case 4:  return { t, p, v };
        default: return { v, p, q };
    }
}

// HSV → packed RGB565 for direct TFT draw.
static inline uint16_t hsvToRgb565(uint8_t h, uint8_t s, uint8_t v) {
    RGB8 c = hsvToRgb(h, s, v);
    return (uint16_t)(((uint16_t)(c.r >> 3) << 11) | ((uint16_t)(c.g >> 2) << 5) | (c.b >> 3));
}
