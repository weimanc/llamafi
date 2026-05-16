# Design — M2 Skin Asset Pipeline

> Owner: Architect / Developer
> Status: in_progress (tier 1 done 2026-05-07; tier 2 in progress)
> Tracked-as: feature m2-001

## Scope

Host-side bake tool (`tools/bake_skin.py`) converts `skins/base-2.91.wsz` to:
- `gen/skin_assets.c` — RGB565 atlas
- `gen/skin_layout.h` — button rects, VU rect, text rects, slider tracks, 9-slice metadata

No firmware change — output verified by inspection and throwaway preview render.

## Tier status

| Tier | Scope | Status |
|---|---|---|
| 1 | Bake tool + main bg + transport buttons + raw font atlas | done 2026-05-07 |
| 2 | Glyph UV table, time digits, sliders | in progress (alongside M3 wiring) |

## Determinism check (T025)

Re-bake must be byte-identical to committed `gen/`:
```sh
cd Spotify-Diy-Thing/tools
python3 bake_skin.py -i ../skins/base-2.91.wsz -o ../SpotifyDiyThing/gen
cd ../SpotifyDiyThing/gen && sha256sum -c golden.sha256
```

## Exit criteria

- Atlas + layout regenerate deterministically from source skin.
- Atlas size known → confirms RGB565 against flash budget.
