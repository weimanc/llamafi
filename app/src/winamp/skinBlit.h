#pragma once
// skinBlit.h — row-at-a-time sprite blit from a baked skin atlas.
//
// Lifted verbatim out of WinampDisplay::blitSprite() during TASK-411 so
// pleditView.h can render the PLEDIT bottom-bar overlay text without either
// duplicating the loop or depending on WinampDisplay. WinampDisplay::blitSprite
// now forwards here, so there is still exactly one implementation.

#include <TFT_eSPI.h>
#include "gen/skin_layout.h"   // SkinUV

extern TFT_eSPI tft;

// Blits uv out of `atlas` (row stride `atlasW`) to (dstX, dstY). One
// pushImage per source row — the atlas is wider than the sprite, so a single
// pushImage cannot express the stride.
inline void skinBlitSprite(int dstX, int dstY, const uint16_t *atlas, int atlasW, SkinUV uv) {
  for (int row = 0; row < uv.h; ++row) {
    const uint16_t *src = atlas + (uv.v + row) * atlasW + uv.u;
    tft.pushImage(dstX, dstY + row, uv.w, 1, src);
  }
}
