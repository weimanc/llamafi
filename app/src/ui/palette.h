#pragma once
// ui/palette.h — the ~10 genuinely shared UI colours (M-CODEQUAL C6, TASK-463).
//
// Named colours previously existed per-file with no shared source: the same
// RGB565 value recurred under a different name in each subsystem that used
// it (CAL_SEP_COLOR/S_SEP/SETTINGS_SEP_COLOR were all independently `0x4208`;
// CAL_BG_COLOR/S_BG/SETTINGS_BG_RGB565 were all independently `0x2104`) —
// the same duplication-without-a-source-of-truth pattern C5 found for canvas
// geometry, just for colour instead of dimension.
//
// Deliberately narrow: this header holds only colours that are the SAME UI
// CONCEPT reused across multiple subsystems (a shared background, a shared
// separator/neutral-grey), not every colour in the firmware that happens to
// share a numeric RGB565 value by coincidence — app-specific colours
// (clockApp.cpp's nixie glyph dimming, cmdMisc.cpp's colorprobe test
// pattern, stock's per-chart accents, etc.) stay local. Centralising every
// colour here was explicitly ruled out by the design doc ("this is not an
// invitation to centralise every colour in the firmware").

static constexpr uint16_t UI_BG_COLOR  = 0x2104;   // standard dark panel background
static constexpr uint16_t UI_SEP_COLOR = 0x4208;   // standard separator / neutral-grey chevron
