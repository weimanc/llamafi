#pragma once
// taskbar.h — 45×240 px vertical icon strip on the right edge (M-MULTIAPP, TASK-087a).
// renderTaskbar() draws the background, icon glyphs, and active-app indicator.
// Called from repaintChrome() on startup and from switchApp() on app switch.

#include <TFT_eSPI.h>
#include "gen/shell_layout.h"
#include "gen/taskbar_icons.h"
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

    static constexpr int iconOffX = (TASKBAR_W - TASKBAR_ICON_BAKED_W) / 2;
    static constexpr int iconOffY = (TASKBAR_SLOT_H - TASKBAR_ICON_BAKED_H) / 2;

    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
        int appIdx = (scrollOffset + i) % totalApps;
        int slotY  = i * TASKBAR_SLOT_H;

        if (TASKBAR_SEP_ENABLED && i < TASKBAR_SLOT_COUNT - 1)
            tft.drawFastHLine(TASKBAR_X, slotY + TASKBAR_SLOT_H - 1, TASKBAR_W, TASKBAR_SEP_COLOR);

        bool isActive = (appIdx == (int)activeApp);
        const uint16_t* icon = isActive
            ? kTaskbarIcons[appIdx].active
            : kTaskbarIcons[appIdx].inactive;
        tft.pushImage(TASKBAR_X + iconOffX, slotY + iconOffY,
                      TASKBAR_ICON_BAKED_W, TASKBAR_ICON_BAKED_H,
                      icon);
    }
    renderActiveIndicator(tft, activeApp, scrollOffset, totalApps, busy);
}
