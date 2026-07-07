#pragma once

// Shared list-scroll gesture tuning — single source for the ADR-030 velocity
// model's calibration, consumed by BOTH gesture sites:
//   - winampDisplay.h  (Spotify PLEDIT, the original M-LIST-v4 machine)
//   - webRadioApp.h    (WebRadio PLEDIT, TASK-277 pattern copy)
// M-WR-PLEDIT-SCROLL §Lean: the gesture CODE is deliberately duplicated (the
// DUT-validated Spotify machine is untouchable; extraction is the documented
// promotion path on a third consumer) but the FEEL is single-sourced here —
// same dead zone, same speed constant, same tap discrimination at both sites.
// This header is standalone by design [DEV-1-6]: it includes neither consumer
// and depends on nothing.

constexpr int           SCROLL_DEAD_ZONE_PX    = 1;
constexpr float         SCROLL_SPEED_K_DEFAULT = 0.1667f;  // linear: 2 rows/s at 1-row travel
constexpr int           PLEDIT_TAP_PX          = 6;        // < PLEDIT_ROW_H/2; tap distance threshold
constexpr unsigned long PLEDIT_TAP_MS          = 250;      // gesture duration threshold (ms)
