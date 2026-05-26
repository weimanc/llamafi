#pragma once
// taskbar.h — 45×240 px vertical icon strip on the right edge (M-MULTIAPP, TASK-087a).
// renderTaskbar() draws the background, icon glyphs, and active-app indicator.
// Called from repaintChrome() on startup and from switchApp() on app switch.

#include <TFT_eSPI.h>
#include "gen/shell_layout.h"
#include "appShell.h"

inline void renderTaskbar(TFT_eSPI& tft, AppId activeApp,
                           int scrollOffset, int totalApps) {
    tft.fillRect(TASKBAR_X, 0, TASKBAR_W, 240, TASKBAR_BG_RGB565);

    const char icons[] = {'S', 'C', 'W', '$', 'M', 'G', '=', 'K'};

    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
        int appIdx = (scrollOffset + i) % totalApps;
        int slotY  = i * TASKBAR_SLOT_H;

        if (TASKBAR_SEP_ENABLED && i < TASKBAR_SLOT_COUNT - 1)
            tft.drawFastHLine(TASKBAR_X, slotY + TASKBAR_SLOT_H - 1, TASKBAR_W, TASKBAR_SEP_COLOR);

        int iconX = TASKBAR_X + (TASKBAR_W / 2) - 5;
        int iconY = slotY + (TASKBAR_SLOT_H - 26) / 2;
        tft.setTextColor(TFT_WHITE, TASKBAR_BG_RGB565);
        tft.drawChar(icons[appIdx], iconX, iconY, 4);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);  // ADR-027 producer rule

        if (appIdx == (int)activeApp)
            tft.fillRect(TASKBAR_X, slotY, 3, TASKBAR_SLOT_H, TASKBAR_ACTIVE_COLOR);
    }
}
