# Design — M-HITZONES Hit-zone Preview PNG

> Owner: Developer
> Status: planned (2026-05-15)
> Tracked-as: TASK-054

## Scope

Extend `tools/bake_skin.py` to emit `gen/skin_hitzones.png` alongside `gen/skin_preview.png`. Same 320×240 composite base; all registered touch hit zones overlaid with semi-transparent magenta rectangles + short text labels. Dev tool only — not a firmware artefact.

## Implementation

~50 LOC in `bake_skin.py`. No new deps (PIL `ImageDraw` already in use). No firmware change.

Rendering:
1. Start from `render_full_preview()` composite.
2. Per zone: `Image.blend` magenta rect at 40% opacity over zone rect.
3. Draw zone label in white at rect centre (`ImageFont` PIL default bitmap).
4. Save as `gen/skin_hitzones.png`.

## Zone registry

| Zone ID | Rect constants | Label |
|---|---|---|
| prev | `CB_PREV_X/Y/W/H` | `PREV` |
| play | `CB_PLAY_*` | `PLAY` |
| pause | `CB_PAUSE_*` | `PAUSE` |
| stop | `CB_STOP_*` | `STOP` |
| next | `CB_NEXT_*` | `NEXT` |
| posbar | `POSBAR_X/Y/W/H` | `SEEK` |
| volume | `VOLUME_X/Y/W/H` | `VOL` |
| shuffle | `SHUFFLE_X/Y/W/H` | `SHUF` |
| repeat | `REPEAT_X/Y/W/H` | `RPT` |
| vis | `VIS_X/Y/W/H` | `VIS` |
| logo | `LOGO_X/Y/W/H` | `LOGO/RECONNECT` |
| pledit rows 0-4 | `PLEDIT_CONTENT_X, PLEDIT_ROWS_Y + i*ROW_H, PLEDIT_CONTENT_W, PLEDIT_ROW_H` | `ROW0`..`ROW4` |

## Exit criteria

- `gen/skin_hitzones.png` regenerates on every `bake_skin.py` run.
- All active zones visible as labelled magenta overlays; positions match DUT touch behaviour.
- `sha256sum -c golden.sha256` still passes (hitzones PNG excluded from golden hash).
