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

// TASK-245 / ADR-046: red indicator when the active app reports a sustained error
// (App::hasError()). Firmware-only constant — kept OUT of generated shell_layout.h
// for the same golden-hash reason as TASKBAR_BUSY_COLOR. Precedence in
// renderActiveIndicator is error > busy > idle.
#define TASKBAR_ERR_COLOR 0xF800

// TASK-279 / M-TASKBAR-FEEDBACK: pressed-slot background (F-a). Brightened grey
// (== TASKBAR_SEP_COLOR) painted behind the icon while the finger is down — the
// opaque baked icon stays dark inside the halo (DEV-3-4 bake constraint, accepted
// per OQ1). Firmware-only constant, same golden-hash rule as TASKBAR_BUSY_COLOR.
#define TASKBAR_PRESSED_BG 0x4208

// TASK-242: number of apps the taskbar cycles through. WebRadio (the last AppId)
// is entered ONLY via the Winamp eject button — it has NO taskbar slot
// (M-WEBRADIO design §Eject button toggle). The taskbar must therefore iterate
// the apps BEFORE WebRadio, not all AppId::COUNT, or WebRadio leaks into the
// scroll cycle and (with no baked icon) crashes in pushImage(nullptr).
static_assert((int)AppId::WebRadio == (int)AppId::COUNT - 1,
              "WebRadio must remain the last AppId (eject-only, excluded from taskbar). "
              "A new app added after it would re-leak it into the taskbar — see "
              "docs/architecture/designs/NEW-APP-CHECKLIST.md.");
static constexpr int TASKBAR_APP_COUNT = (int)AppId::WebRadio;

// Compile-time gate (TASK-242): every taskbar app must have a baked icon. The
// generator emits TASKBAR_ICON_COUNT = number of icon pairs; if it drifts from
// TASKBAR_APP_COUNT (e.g. a taskbar app added to AppId but not to the icon
// generator's APPS list — the exact WebRadio defect), this fails to compile.
static_assert(TASKBAR_ICON_COUNT == TASKBAR_APP_COUNT,
              "taskbar icon count != taskbar app count: a taskbar app is missing a "
              "baked icon (add <app>.png + <app>_active.png and re-run run/bake-icons), "
              "or an eject-only app leaked into the taskbar. See NEW-APP-CHECKLIST.md.");

// Repaints only the 3 px active indicator for the slot showing activeApp.
// Call when busy state changes; renderTaskbar() delegates to this internally.
inline void renderActiveIndicator(TFT_eSPI& tft, AppId activeApp,
                                  int scrollOffset, int totalApps, bool busy,
                                  bool error = false, bool connecting = false) {
    // TASK-245 / ADR-046: precedence error (red) > busy|connecting (amber) > idle (green).
    // busy and connecting both read amber (work in flight / not yet resolved).
    uint16_t col = error ? TASKBAR_ERR_COLOR
                         : ((busy || connecting) ? TASKBAR_BUSY_COLOR : TASKBAR_ACTIVE_COLOR);
    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
        int appIdx = (scrollOffset + i) % totalApps;
        if (appIdx == (int)activeApp) {
            int slotY = i * TASKBAR_SLOT_H;
            tft.fillRect(TASKBAR_X, slotY, 3, TASKBAR_SLOT_H, col);
            return;
        }
    }
}

// TASK-279 / M-TASKBAR-FEEDBACK: one slot's full body — bg (pressed or normal),
// separator, null-guarded icon, and the ADR-046 indicator when the slot is active.
// Extracted from renderTaskbar so the pressed-slot repaint REUSES the exact guarded
// slot body (QM-3-2) instead of reimplementing the index math that rotted into the
// TASK-242/LL-085 crash. Pressing the active slot repaints its indicator too (DEV-3-3).
inline void renderTaskbarSlot(TFT_eSPI& tft, int slot, AppId activeApp,
                              int scrollOffset, int totalApps, bool busy,
                              bool error = false, bool connecting = false,
                              bool pressed = false) {
    if (slot < 0 || slot >= TASKBAR_SLOT_COUNT) return;
    static constexpr int iconOffX = (TASKBAR_W - TASKBAR_ICON_BAKED_W) / 2;
    static constexpr int iconOffY = (TASKBAR_SLOT_H - TASKBAR_ICON_BAKED_H) / 2;

    int appIdx = (scrollOffset + slot) % totalApps;
    int slotY  = slot * TASKBAR_SLOT_H;

    tft.fillRect(TASKBAR_X, slotY, TASKBAR_W, TASKBAR_SLOT_H,
                 pressed ? TASKBAR_PRESSED_BG : TASKBAR_BG_RGB565);

    if (TASKBAR_SEP_ENABLED && slot < TASKBAR_SLOT_COUNT - 1)
        tft.drawFastHLine(TASKBAR_X, slotY + TASKBAR_SLOT_H - 1, TASKBAR_W, TASKBAR_SEP_COLOR);

    bool isActive = (appIdx == (int)activeApp);
    const uint16_t* icon = (appIdx >= 0 && appIdx < (int)AppId::COUNT)
        ? (isActive ? kTaskbarIcons[appIdx].active
                    : kTaskbarIcons[appIdx].inactive)
        : nullptr;
    // Null-safe: an un-baked icon (kTaskbarIcons entry never regenerated for a
    // newly-added app) must render as a blank slot, never deref nullptr in
    // pushImage() — that was a hard crash on the WebRadio slot (TASK-242).
    if (icon)
        tft.pushImage(TASKBAR_X + iconOffX, slotY + iconOffY,
                      TASKBAR_ICON_BAKED_W, TASKBAR_ICON_BAKED_H,
                      icon);
    if (isActive) {
        uint16_t col = error ? TASKBAR_ERR_COLOR
                             : ((busy || connecting) ? TASKBAR_BUSY_COLOR
                                                     : TASKBAR_ACTIVE_COLOR);
        tft.fillRect(TASKBAR_X, slotY, 3, TASKBAR_SLOT_H, col);
    }
}

inline void renderTaskbar(TFT_eSPI& tft, AppId activeApp,
                           int scrollOffset, int totalApps, bool busy = false,
                           bool error = false, bool connecting = false) {
    // Slot bodies tile the full strip (TASKBAR_SLOT_COUNT × TASKBAR_SLOT_H == 240),
    // each filling its own background — no separate whole-strip fill needed.
    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i)
        renderTaskbarSlot(tft, i, activeApp, scrollOffset, totalApps,
                          busy, error, connecting, false);
}
