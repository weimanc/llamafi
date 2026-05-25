#pragma once
// taskbar.h — 45×240 px vertical icon strip on the right edge (M-MULTIAPP, TASK-087a).
// renderTaskbar() draws the background, icon glyphs, and active-app indicator.
// Called from repaintChrome() on startup and from switchApp() on app switch.

#include <TFT_eSPI.h>
#include "gen/shell_layout.h"
#include "appShell.h"

inline void renderTaskbar(TFT_eSPI& tft, AppId activeApp) {
    tft.fillRect(TASKBAR_X, 0, TASKBAR_W, 240, TASKBAR_BG_RGB565);

    const char icons[] = {'S', 'C', 'W', '$', 'M', 'G'};

    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
        int slotY = i * TASKBAR_SLOT_H;

        // Separator line at the bottom of each slot except the last.
        if (TASKBAR_SEP_ENABLED && i < TASKBAR_SLOT_COUNT - 1) {
            tft.drawFastHLine(TASKBAR_X, slotY + TASKBAR_SLOT_H - 1, TASKBAR_W, TASKBAR_SEP_COLOR);
        }

        // Icon glyph centred in the 45×40 cell using TFT_eSPI font 4 (~26 px tall).
        // iconX centres a ~14px-wide char in 45px; iconY centres 26px in 40px.
        int iconX = TASKBAR_X + (TASKBAR_W / 2) - 5;  // ≈ 285, visual centre
        int iconY = slotY + (TASKBAR_SLOT_H - 26) / 2; // ≈ slotY + 7
        tft.setTextColor(TFT_WHITE, TASKBAR_BG_RGB565);
        tft.drawChar(icons[i], iconX, iconY, 4);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);  // reset — ADR-027 producer rule

        // Active indicator: TASKBAR_ACTIVE_STYLE 'A' = 3 px left-edge bar.
        if ((int)activeApp == i) {
            tft.fillRect(TASKBAR_X, slotY, 3, TASKBAR_SLOT_H, TASKBAR_ACTIVE_COLOR);
        }
    }
}
