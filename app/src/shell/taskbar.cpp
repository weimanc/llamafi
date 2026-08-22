// shell/taskbar.cpp — see shell/taskbar.h for design notes. Moved from
// taskbar/taskbar.h (M-SRCLAYOUT Stage E / TASK-471), pure move, bodies verbatim.

#include "shell/taskbar.h"

#include <math.h>

bool isWebRadioSkin(AppId activeApp) { return activeApp == AppId::WebRadio; }
AppId resolveTaskbarSlotApp(AppId activeApp) {
    return (activeApp == AppId::WebRadio || activeApp == AppId::LocalPlayer)
        ? AppId::Spotify : activeApp;
}

void recolorOrangeToRed(const uint16_t* src, uint16_t* dst, int count) {
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

void renderActiveIndicator(TFT_eSPI& tft, AppId activeApp,
                            int scrollOffset, int totalApps, bool busy,
                            bool error, bool connecting) {
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

void renderTaskbarSlot(TFT_eSPI& tft, int slot, AppId activeApp,
                        int scrollOffset, int totalApps, bool busy,
                        bool error, bool connecting,
                        bool pressed) {
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

void renderTaskbar(TFT_eSPI& tft, AppId activeApp,
                    int scrollOffset, int totalApps, bool busy,
                    bool error, bool connecting) {
    // Slot bodies tile the full strip (TASKBAR_SLOT_COUNT × TASKBAR_SLOT_H == 240),
    // each filling its own background — no separate whole-strip fill needed.
    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i)
        renderTaskbarSlot(tft, i, activeApp, scrollOffset, totalApps,
                          busy, error, connecting, false);
}
