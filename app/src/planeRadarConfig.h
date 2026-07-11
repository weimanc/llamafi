#pragma once
// planeRadarConfig.h — constants shared between planeRadarApp.h (render/data)
// and settings/appsSection.h (Settings > Applications > PlaneRadar UI).
//
// Split out (TASK-310 audit finding #6) because appsSection.h's own copy of
// the preset table (`kRangeKm[] = {5,10,15,25}`) silently re-stated
// kPrPresetKm — a preset-table edit could desync the Settings UI from the
// disc with no error. One definition, both files include it.

#include <stdint.h>

static constexpr uint8_t  PR_NUM_PRESETS = 4;
static constexpr uint16_t kPrPresetKm[PR_NUM_PRESETS] = {5, 10, 15, 25};

static constexpr float PR_KM_PER_NM = 1.852f;

// Fetch radius (NM) per preset — reference's fetchRadiusKm() margin factor,
// per phase0-api-probe.md. Derived per-element from kPrPresetKm (TASK-311
// audit finding #6) instead of baked literals, so the two tables can't
// drift out of sync:
//   fetch_nm = preset_km * (outer/ring3 margin) * (our disc / reference grid
//              radius margin) / km-per-NM
// Values land within a rounding hair of the old baked {4.0, 7.9, 11.9, 19.9}
// — expected, since those were this same formula hand-computed once.
static constexpr float PR_FETCH_RING3_TO_OUTER = 4.0f / 3.0f;     // outer_km = preset_km * 4/3 (ring3 -> outer)
static constexpr float PR_FETCH_GRID_MARGIN    = 118.0f / 107.0f; // our PR_R=118 vs reference's grid radius 107
static constexpr float kPrFetchNm[PR_NUM_PRESETS] = {
    kPrPresetKm[0] * PR_FETCH_RING3_TO_OUTER * PR_FETCH_GRID_MARGIN / PR_KM_PER_NM,
    kPrPresetKm[1] * PR_FETCH_RING3_TO_OUTER * PR_FETCH_GRID_MARGIN / PR_KM_PER_NM,
    kPrPresetKm[2] * PR_FETCH_RING3_TO_OUTER * PR_FETCH_GRID_MARGIN / PR_KM_PER_NM,
    kPrPresetKm[3] * PR_FETCH_RING3_TO_OUTER * PR_FETCH_GRID_MARGIN / PR_KM_PER_NM,
};
