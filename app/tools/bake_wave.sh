#!/usr/bin/env bash
# Canonical wave_atlas bake invocation.
# Update this file whenever bake flags change; regenerate gen/wave_atlas.* in the same commit.
#
# --frame-start 30: skip 30 identical lead-in frames from source video (static waveform before
#   music starts). Frames 0-29 are byte-identical; 30 frozen frames = 1.5 s freeze at 20 Hz.
# --dc-offset 3:   systematic vertical calibration correction for this screengrab.
# --boost 2.0:     amplify waveform excursion from centre ×2 (more dynamic range on display).
# --spatial-smooth 3: box-filter along x, eliminates column-to-column staircase artefacts.
# --error-diffusion: Floyd-Steinberg along x per frame, breaks flat plateau runs into dithered
#   alternation (removes 4-level banding that integer extraction produces).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$SCRIPT_DIR/bake_wave.py" \
  -i "$REPO_ROOT/resource/Screencast_20260516_061832.webm" \
  -o "$SCRIPT_DIR/../SpotifyDiyThing/gen" \
  --frame-start 30 \
  --dc-offset 3 \
  --boost 2.0 \
  --spatial-smooth 3 \
  --error-diffusion \
  "$@"
