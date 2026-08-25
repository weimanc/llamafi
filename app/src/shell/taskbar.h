#pragma once
// shell/taskbar.h — 45×240 px vertical icon strip on the right edge (M-MULTIAPP,
// TASK-087a). renderTaskbar() draws the background, icon glyphs, and active-app
// indicator. Called from repaintChrome() on startup and from switchApp() on app
// switch. Moved from taskbar/taskbar.h (M-SRCLAYOUT Stage E / TASK-471) —
// relocated into shell/ per the design doc's target tree, alongside the other
// shell-owned components (appTable.h, shellState.h, shellDispatch.h).

#include <TFT_eSPI.h>
#include "gen/shell_layout.h"
#include "ui/palette.h"         // M-CODEQUAL C6 (TASK-463): UI_SEP_COLOR
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
// M-CODEQUAL C6 (TASK-463): was an independent literal (matching the comment's
// own "== TASKBAR_SEP_COLOR" note); now an alias for the one canonical source.
#define TASKBAR_PRESSED_BG UI_SEP_COLOR

// TASK-242 / TASK-413 (ADR-059 D7): number of apps the taskbar cycles through.
// WebRadio and LocalPlayer are entered ONLY via the Winamp player-slot mode
// (eject button / taskbar-icon cycle, M-WEBRADIO / M-PLAYER-STATE) — neither has
// a taskbar slot. The taskbar must therefore iterate only the apps up to and
// including Settings, not all AppId::COUNT, or an eject-only mode leaks into the
// scroll cycle and (with no baked icon) crashes in pushImage(nullptr).
//
// Anchored to Settings (the last taskbar slot) rather than to the eject-only tail
// itself, so this survives any number of eject-only tail modes — a literal
// "COUNT - N" here would silently break the moment a third one is added, which is
// the exact failure this invariant exists to prevent (ADR-059 D7, corrected
// 2026-08-07: the original draft got this backwards).
static constexpr int TASKBAR_APP_COUNT = (int)AppId::Settings + 1;

static_assert((int)AppId::Settings + 1 == TASKBAR_APP_COUNT,
              "Settings must remain the last taskbar slot; every AppId after it is "
              "eject-only and must have no taskbar slot. See "
              "docs/architecture/designs/NEW-APP-CHECKLIST.md.");

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

// M-WEBRADIO-ICON (+ TASK-413): WebRadio and LocalPlayer share the Spotify/player
// slot rather than owning a taskbar slot of their own (TASKBAR_APP_COUNT above
// deliberately excludes both), so callers pass currentAppId straight through and it
// may legitimately equal AppId::WebRadio or AppId::LocalPlayer. Every entry point
// below remaps either to AppId::Spotify for comparison/indexing — otherwise the
// active-slot highlight addresses an AppId past TASKBAR_APP_COUNT and never matches
// any real slot, leaving the taskbar with no highlight at all while in that mode.
// webRadioSkin separately signals the icon (but not the busy/error/idle indicator
// colour) to swap for the orange->red recoloured variant — LocalPlayer has no such
// variant yet (no baked asset, TASK-413 is shell-logic-only) and renders the plain
// active Spotify icon. Do NOT resolve this ahead of a renderTaskbar() call and pass
// the resolved AppId down — renderTaskbarSlot needs the original value to compute
// webRadioSkin itself.
bool isWebRadioSkin(AppId activeApp);
AppId resolveTaskbarSlotApp(AppId activeApp);

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
void recolorOrangeToRed(const uint16_t* src, uint16_t* dst, int count);

// Repaints only the 3 px active indicator for the slot showing activeApp.
// Call when busy state changes; renderTaskbar() delegates to this internally.
void renderActiveIndicator(TFT_eSPI& tft, AppId activeApp,
                            int scrollOffset, int totalApps, bool busy,
                            bool error = false, bool connecting = false);

// TASK-279 / M-TASKBAR-FEEDBACK: one slot's full body — bg (pressed or normal),
// separator, null-guarded icon, and the ADR-046 indicator when the slot is active.
// Extracted from renderTaskbar so the pressed-slot repaint REUSES the exact guarded
// slot body (QM-3-2) instead of reimplementing the index math that rotted into the
// TASK-242/LL-085 crash. Pressing the active slot repaints its indicator too (DEV-3-3).
void renderTaskbarSlot(TFT_eSPI& tft, int slot, AppId activeApp,
                        int scrollOffset, int totalApps, bool busy,
                        bool error = false, bool connecting = false,
                        bool pressed = false);

void renderTaskbar(TFT_eSPI& tft, AppId activeApp,
                    int scrollOffset, int totalApps, bool busy = false,
                    bool error = false, bool connecting = false);
