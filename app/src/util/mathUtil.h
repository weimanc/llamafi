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
