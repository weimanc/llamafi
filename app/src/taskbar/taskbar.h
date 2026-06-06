#pragma once
// taskbar.h — 45×240 px vertical icon strip on the right edge (M-MULTIAPP, TASK-087a).
// renderTaskbar() draws the background, icon glyphs, and active-app indicator.
// Called from repaintChrome() on startup and from switchApp() on app switch.

#include <TFT_eSPI.h>
#include "gen/shell_layout.h"
#include "appShell.h"

// Amber indicator while shell busy (firmware-only constant — not in generated shell_layout.h
// to avoid invalidating check_build.sh golden hash).
#define TASKBAR_BUSY_COLOR 0xFD20

// Repaints only the 3 px active indicator for the slot showing activeApp.
// Call when busy state changes; renderTaskbar() delegates to this internally.
inline void renderActiveIndicator(TFT_eSPI& tft, AppId activeApp,
                                  int scrollOffset, int totalApps, bool busy) {
    uint16_t col = busy ? TASKBAR_BUSY_COLOR : TASKBAR_ACTIVE_COLOR;
    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
        int appIdx = (scrollOffset + i) % totalApps;
        if (appIdx == (int)activeApp) {
            int slotY = i * TASKBAR_SLOT_H;
            tft.fillRect(TASKBAR_X, slotY, 3, TASKBAR_SLOT_H, col);
            return;
        }
    }
}

inline void renderTaskbar(TFT_eSPI& tft, AppId activeApp,
                           int scrollOffset, int totalApps, bool busy = false) {
    tft.fillRect(TASKBAR_X, 0, TASKBAR_W, 240, TASKBAR_BG_RGB565);

#define APP_X(Name, icon, cfg) icon,
    const char icons[] = {
#include "appRegistry.h"
    };
#undef APP_X
    static_assert(sizeof(icons) == (int)AppId::COUNT, "icons[] out of sync with appRegistry.h");

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
    }
    renderActiveIndicator(tft, activeApp, scrollOffset, totalApps, busy);
}
