#pragma once
// taskbar.h — 45×240 px vertical icon strip on the right edge (M-MULTIAPP, TASK-087a).
// renderTaskbar() draws the background, icon glyphs, and active-app indicator.
// Called from repaintChrome() on startup and from switchApp() on app switch.

#include <TFT_eSPI.h>
#include <math.h>
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

// TASK-347: Settings is a utility, not a destination app — pinned as the last
// visible taskbar slot, i.e. the second-to-last registry row (directly before
// the eject-only WebRadio). Future apps insert BEFORE Settings; see
// docs/architecture/designs/M-APP-ORDER-settings-last.md and NEW-APP-CHECKLIST.md.
static_assert((int)AppId::Settings == (int)AppId::WebRadio - 1,
              "Settings must remain the last taskbar slot (second-to-last AppId, "
              "directly before WebRadio). Insert new apps BEFORE Settings — see "
              "docs/architecture/designs/M-APP-ORDER-settings-last.md.");

// Compile-time gate (TASK-242): every taskbar app must have a baked icon. The
// generator emits TASKBAR_ICON_COUNT = number of icon pairs; if it drifts from
// TASKBAR_APP_COUNT (e.g. a taskbar app added to AppId but not to the icon
// generator's APPS list — the exact WebRadio defect), this fails to compile.
static_assert(TASKBAR_ICON_COUNT == TASKBAR_APP_COUNT,
              "taskbar icon count != taskbar app count: a taskbar app is missing a "
              "baked icon (add <app>.png + <app>_active.png and re-run run/bake-icons), "
              "or an eject-only app leaked into the taskbar. See NEW-APP-CHECKLIST.md.");

// M-WEBRADIO-ICON: WebRadio shares the Spotify/player slot rather than owning a
// taskbar slot of its own (TASKBAR_APP_COUNT above deliberately excludes it), so
// callers pass currentAppId straight through and it may legitimately equal
// AppId::WebRadio. Every entry point below remaps that to AppId::Spotify for
// comparison/indexing, and separately signals webRadioSkin so the icon (but not
// the busy/error/idle indicator colour) gets swapped for the orange->red
// recoloured variant. Do NOT resolve this ahead of a renderTaskbar() call and
// pass the resolved AppId down — renderTaskbarSlot needs the original value to
// compute webRadioSkin itself.
inline bool isWebRadioSkin(AppId activeApp) { return activeApp == AppId::WebRadio; }
inline AppId resolveTaskbarSlotApp(AppId activeApp) {
    return isWebRadioSkin(activeApp) ? AppId::Spotify : activeApp;
}

// Recolours orange-ish RGB565 pixels to red via an HSV hue rotation, leaving
// everything else (the white diamond outline, transparent bg) untouched.
// Lets WebRadio reuse the existing baked spotify_active icon (the winamp
// bolt) instead of needing its own baked array. Only runs on slot repaint
// (app switch / tap / busy-state change), never per animation frame, so the
// float HSV<->RGB math here (one 24x24 slot) is negligible.
//
// A first version thresholded on raw RGB channels (r>140, b<120, g<r-30) and
// only caught the bolt's deep saturated orange (~0xFB8C00, H=33.5 S=1.0),
// missing the pale highlight orange (~0xFFCC80, H=35.9 S=0.5) -- its B
// channel sits just above that b<120 cutoff. Both shades sample to the same
// ~33-36 degree hue at different saturation (colorsys.rgb_to_hsv), so a hue
// rotation catches both by construction, and preserves the source art's
// tonal design (the highlight stays a lighter tint of the body colour)
// instead of an ad-hoc per-channel patch.
inline void recolorOrangeToRed(const uint16_t* src, uint16_t* dst, int count) {
    constexpr float kHueShiftDeg = -30.0f;
    constexpr float kHueLo = 20.0f, kHueHi = 50.0f, kSatMin = 0.35f;
    for (int i = 0; i < count; ++i) {
        uint16_t px = src[i];
        uint8_t r5 = (px >> 11) & 0x1F;
        uint8_t g6 = (px >> 5) & 0x3F;
        uint8_t b5 = px & 0x1F;
        float r = r5 / 31.0f, g = g6 / 63.0f, b = b5 / 31.0f;
        float maxc = fmaxf(r, fmaxf(g, b));
        float minc = fminf(r, fminf(g, b));
        float delta = maxc - minc;
        float s = (maxc <= 0.0f) ? 0.0f : delta / maxc;
        if (s < kSatMin || delta <= 0.0f) { dst[i] = px; continue; }

        float h;
        if (maxc == r)      h = 60.0f * fmodf((g - b) / delta + 6.0f, 6.0f);
        else if (maxc == g) h = 60.0f * ((b - r) / delta + 2.0f);
        else                h = 60.0f * ((r - g) / delta + 4.0f);
        if (h < kHueLo || h > kHueHi) { dst[i] = px; continue; }

        h = fmodf(h + kHueShiftDeg + 360.0f, 360.0f);
        float v = maxc;
        float c = v * s;
        float x = c * (1.0f - fabsf(fmodf(h / 60.0f, 2.0f) - 1.0f));
        float m = v - c;
        float r2, g2, b2;
        if      (h < 60)  { r2 = c; g2 = x; b2 = 0; }
        else if (h < 120) { r2 = x; g2 = c; b2 = 0; }
        else if (h < 180) { r2 = 0; g2 = c; b2 = x; }
        else if (h < 240) { r2 = 0; g2 = x; b2 = c; }
        else if (h < 300) { r2 = x; g2 = 0; b2 = c; }
        else              { r2 = c; g2 = 0; b2 = x; }
        r2 += m; g2 += m; b2 += m;

        uint8_t r5n = (uint8_t)lroundf(r2 * 31.0f);
        uint8_t g6n = (uint8_t)lroundf(g2 * 63.0f);
        uint8_t b5n = (uint8_t)lroundf(b2 * 31.0f);
        dst[i] = ((uint16_t)r5n << 11) | ((uint16_t)g6n << 5) | b5n;
    }
}

// Repaints only the 3 px active indicator for the slot showing activeApp.
// Call when busy state changes; renderTaskbar() delegates to this internally.
inline void renderActiveIndicator(TFT_eSPI& tft, AppId activeApp,
                                  int scrollOffset, int totalApps, bool busy,
                                  bool error = false, bool connecting = false) {
    activeApp = resolveTaskbarSlotApp(activeApp);
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

    bool webRadioSkin = isWebRadioSkin(activeApp);
    activeApp = resolveTaskbarSlotApp(activeApp);

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
    // M-WEBRADIO-ICON: WebRadio reuses this (Spotify/player) slot's active icon,
    // recoloured orange->red at render time — see recolorOrangeToRed() above.
    if (icon && isActive && webRadioSkin) {
        static uint16_t s_webRadioIcon[TASKBAR_ICON_BAKED_PX];
        recolorOrangeToRed(icon, s_webRadioIcon, TASKBAR_ICON_BAKED_PX);
        icon = s_webRadioIcon;
    }
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
