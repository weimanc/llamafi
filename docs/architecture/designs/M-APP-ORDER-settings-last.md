# Design — M-APP-ORDER: Settings pinned as last taskbar entry

> Owner: Architect
> Status: scheduled — designed 2026-07-18, filed as TASK-347. No ADR needed
> (ADR-041's X-macro registry already owns ordering; this adds one ordering
> invariant on top of the existing WebRadio-last invariant).
> Deps: ADR-041 (X-macro registry), TASK-242 (WebRadio taskbar exclusion),
> LL-114 (host tools must not mirror firmware constants by hand)

## Product intent (human, 2026-07-18)

Settings is a utility, not a destination app — it should always occupy the
**last taskbar slot**, after every real app. "Always" = an enforced invariant,
not a one-time move: future apps insert *before* Settings, and the build fails
if anyone appends behind it.

## Hard constraint — WebRadio stays the final registry row

`taskbar.h` derives the taskbar roster as
`TASKBAR_APP_COUNT = (int)AppId::WebRadio` and static_asserts
`WebRadio == COUNT - 1` (TASK-242: WebRadio is eject-only; if it gains a slot
it crashes in `pushImage(nullptr)` — LL-085). Therefore "Settings last" means:

- **Settings = last taskbar slot = second-to-last registry row** (index
  `COUNT - 2`, directly before WebRadio).
- WebRadio remains the final row. Any design that puts Settings after WebRadio
  is wrong by construction.

## The change

`app/src/appRegistry.h` — move the Settings row from position 7 to directly
before WebRadio:

```
before:  Spotify Clock Weather Crypto Matrix Life Settings Stock Aquarium Teletext PlaneRadar WebRadio
after:   Spotify Clock Weather Crypto Matrix Life Stock Aquarium Teletext PlaneRadar Settings WebRadio
```

Enum renumbering: Stock 7→6, Aquarium 8→7, Teletext 9→8, PlaneRadar 10→9,
Settings 6→10. Spotify..Life and WebRadio unchanged.

### Invariant enforcement (the "always" part)

1. **Firmware static_assert** (next to the existing WebRadio one in
   `taskbar.h`):
   `static_assert((int)AppId::Settings == (int)AppId::WebRadio - 1, ...)` —
   message points at this doc and NEW-APP-CHECKLIST.
2. **Codegen check**: `gen_app_registry.py` errors out if Settings is not the
   last row before WebRadio (belt-and-braces — catches it at codegen time,
   before a compile).
3. **NEW-APP-CHECKLIST.md**: add "insert new APP_X rows BEFORE Settings
   (Settings and WebRadio are pinned as the last two rows — build enforces
   both)".

## Consumer audit (verified against code, 2026-07-18)

| Surface | Finding | Action |
|---|---|---|
| Persistence | **Safe.** `settings.json` keys are per-app *names* (`doc["stock"]`, `doc["crypto"]`…); player-slot mode is its own uint8, not an AppId. No numeric AppId is persisted anywhere. | none |
| Codegen mirrors | `app_ids_gen.py` (APP_SLOT/APP_ORDER) + `configurable_apps.h` regenerate from the registry; `run/check` step 5 enforces staleness. | re-run `gen_app_registry.py` |
| Settings > Applications list | **Unchanged.** Settings itself is `configurable=0`; the relative order of the other rows is preserved, so `kConfigurableApps` order — and every T-SET/T-SETW row-tap Y — is identical. | none |
| Taskbar icon bake | **The trap.** `gen_taskbar_icons.py` carries a hand-mirrored `APPS` list ("must match appRegistry.h order exactly"). The emitted icon array is indexed by AppId, and the `TASKBAR_ICON_COUNT` static_assert catches *count* drift only — an order mismatch renders wrong icons silently. This is the LL-114 pattern TASK-335 killed for geometry but not for this list. | fix the mirror: derive `APPS` from `app_ids_gen.APP_ORDER` (minus WebRadio, lowercased) instead of resyncing by hand; re-run `run/bake-icons`; regen goldens |
| DUT test suite | Slot references go through the generated `APP_SLOT` mirror (`tap_taskbar_slot`, `switchApp <id>` in `_switch_to_settings`) — auto-adjust after regen. One exception: T182 uses physical-slot arithmetic `(APP_SLOT["Stock"] - 2) % APP_COUNT`; it self-adjusts for this move, but its mod base is `APP_COUNT` (12) where the firmware cycle is `% TASKBAR_APP_COUNT` (11) — align it while touching. | T182 mod-base fix; grep tests/docs for hardcoded `switchApp` numerals / slot indices |
| appsSection dispatch | switch on `AppId::` symbols, not values. | none |
| Taskbar UX | 6 visible slots (240/40), 11-entry wrap cycle. Settings moves from slot 6 to slot 10 — with wrap-scroll it sits one step "behind" slot 0, arguably *more* reachable, not less. | eyeball on DUT |

## Verification (VE)

- `run/check` 7/7 (registry-staleness gate is step 5; icon goldens regenerate).
- Rerun existing taskbar suites on DUT: T088 (hit zones), T136/T137 +
  T162–T166 (scroll), T147 (tap round-trip), T182 (physical-slot), plus the
  settings smoke (entry via `switchApp` mirror).
- **BP-048 eyeball gate**: scroll the full taskbar cycle on DUT — every slot
  shows the right icon (this is the check the silent icon-order-drift failure
  mode needs; no automated gate sees it).
- Negative build check (one-off, not committed): append a dummy APP_X row
  after Settings → both the codegen check and the static_assert must fire.

## Effort / risk

Small. One registry edit, one static_assert, one codegen guard, the
gen_taskbar_icons de-mirroring, two regens (registry + icons), checklist note,
T182 nit. Risk concentrates in the icon-order silent failure — mitigated by
de-mirroring the APPS list (root cause) + the eyeball gate (backstop).
