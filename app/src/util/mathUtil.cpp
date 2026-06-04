#include "mathUtil.h"

float g_sinLUT[512];

void buildMathLUT() {
    for (int i = 0; i < 512; ++i)
        g_sinLUT[i] = sinf(i * (6.28318530f / 512.0f));
}
