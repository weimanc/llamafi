# M-MEMPLAN — Static app-memory overlay planner (single source of truth, build-time)

> Owner: Architect · Status: **DESIGN (proposal)** · 2026-06-28
> Formalizes M-MEMBUDGET (the ad-hoc 24 K runtime arena) into a declarative, build-time-planned memory
> **overlay** with a **single source of truth** and a **worst-case budget gate**. Mirrors the
> `gen_app_registry.py` codegen pattern. Successor to the runtime `mb_arena_*` machinery (migration in §8).

## 1. Goal

Replace per-feature, runtime, hand-tuned memory reservation with **one declarative manifest** of every app's
memory needs and an **offline (host, pre-build) algorithm** that:
1. computes a **static overlay layout** — mutually-exclusive apps *share* the same physical region (union),
2. assigns each buffer a deterministic **location** (region + offset),
3. **gates the build** against a RAM ceiling (worst-case memory usage — the WCMU sibling of WCET),
4. emits a generated header the firmware uses — **no runtime allocation, no fragmentation, no JIT timing**
   for the buffers it covers.

This makes memory a *budgeted, reviewed, build-checked* resource (like flash via the linker), not a runtime
gamble. It is the principled form of the overlay idea from M-MEMBUDGET §4a (sized to **MAX, not SUM**).

## 2. Model

- **Buffer** — a named block an app needs: `{ name, owner-app, size, caps, group }`.
- **Caps** — the SRAM class required: `DMA` (I2S/peripheral), `INTERNAL` (decoder/scratch, non-DMA),
  `ANY` (general). Overlay only happens *within* one caps class (you can't union DMA with INTERNAL).
- **Working set** — all buffers an app holds *simultaneously* while active. Buffers of one app in one group
  **coexist** → they **sum**.
- **Overlay group (exclusivity class)** — buffers from *different* apps in the same group are **never live at
  the same time** → they **overlay** (share the region; the region is sized to the **max** working set).
  The two sources of mutual exclusion on this device:
  - **`foreground`** — single-screen ⇒ exactly one app foreground at a time (M-MEMBUDGET §4a). All foreground
    working buffers (sprites, parse docs, the audio decoder/InBuff) are mutually exclusive.
  - **`sequential`** — phases within one app that never overlap (e.g. WebRadio *fetch* at `init()` vs
    *decode* at `_play()` — TASK-265/267). These can overlay **only if both members are planner-placeable**
    (see §6 boundary — the fetch's mbedtls TLS is **not**, so that pair stays runtime).

## 3. Single source of truth — the manifest

`app/mem_manifest.yaml` — the authoritative declaration. Schema:

```yaml
ceiling:                     # RAM pool available to overlays + heap headroom, per caps class
  INTERNAL: 290000           # bytes (after firmware static); the WCMU gate compares against this
  DMA:      48000
headroom:                    # reserved for transient heap the planner does NOT place (TLS, system)
  INTERNAL: 60000            # e.g. the ~40 K mbedtls fetch context + margin (§6)
buffers:
  - { name: webradio_decoder, app: WebRadio, caps: INTERNAL, group: foreground, size: 23216, kind: scratch }
  - { name: webradio_inbuf,   app: WebRadio, caps: INTERNAL, group: foreground, size: 6400,  kind: scratch }
  - { name: heatmap_doc,      app: Stock,    caps: ANY,      group: foreground, size: 2560,  kind: scratch }
  - { name: aquarium_strip,   app: Aquarium, caps: ANY,      group: foreground, size: 4096,  kind: scratch }
```

`kind: scratch | state` enforces the **M-MEMBUDGET §4b invariant** (only *regenerable scratch* may be
overlaid; persistent `state` must NOT be in an overlay region — the planner rejects `kind: state` in any
multi-app group). One file; every app's memory is visible and diff-reviewable here.

## 4. The offline algorithm (the planner — `app/tools/gen_mem_layout.py`)

```
group buffers by (caps, group)
for each (caps, group):
    for each app a with buffers in this (caps, group):
        app_set[a] = sum(b.size for b in buffers if b.app==a)         # coexist within an app → SUM
    region_size = max(app_set.values())                              # exclusive across apps → MAX
    assign each app's buffers contiguous offsets [0 .. app_set[a])    # per-app layout within the region
for each caps:
    total[caps] = sum(region_size for all groups in caps)
    assert total[caps] + headroom[caps] <= ceiling[caps]             # WCMU BUILD GATE — fail loudly
emit app/gen/mem_layout.h + app/gen/mem_layout.py (test mirror)
```

Properties: deterministic (sorted iteration) → **golden-hashable** (re-run is byte-identical, like
`gen_app_registry`); the budget assertion is a **hard build failure** with a precise overflow message
(*"INTERNAL overlay 31 K + headroom 60 K > ceiling 290 K by N"*). Adding/resizing an app buffer that breaks
the budget fails the build, not the device.

## 5. Output — generated layout

```c
// app/gen/mem_layout.h  (AUTO-GENERATED — do not edit; re-run gen_mem_layout.py)
static uint8_t s_overlay_internal_foreground[29616] __attribute__((aligned(4)));
#define MEM_webradio_decoder (s_overlay_internal_foreground + 0)
#define MEM_webradio_inbuf   (s_overlay_internal_foreground + 23216)
static uint8_t s_overlay_any_foreground[4096] __attribute__((aligned(4)));
#define MEM_heatmap_doc      (s_overlay_any_foreground + 0)   // overlaid with…
#define MEM_aquarium_strip   (s_overlay_any_foreground + 0)   // …these (mutually exclusive)
#define MEM_BUDGET_INTERNAL_USED 29616
```

The region is a **static array** → the linker places it, it's part of static RAM, **zero runtime allocation
or fragmentation**, location known at build time. Apps use `MEM_<name>` as the buffer address. For the forked
decoder, point the existing free-list at the static region — `mb_arena_init(MEM_webradio_decoder, 29616)` —
so the allocator stays, only its backing buffer becomes static-and-planned instead of `heap_caps_malloc`'d
(§8).

## 6. The honest boundary — what the planner can and cannot place

The planner places buffers **we control** (our app buffers; forked-library buffers routed through our
allocator, e.g. the decoder/InBuff). It **cannot** place memory a **third-party library allocates
internally** — most importantly the **mbedtls TLS context** (the ~40 K fetch handshake) and system/LWIP.
Consequence:
- **Statically planned (this design):** sprites, parse docs, the decoder + InBuff overlay → deterministic.
- **Stays heap, planner reserves *headroom* for it:** mbedtls TLS, WiFi/LWIP, task stacks. The manifest's
  `headroom` is the planner's *promise* that this much heap is left after the overlays — the WCMU gate
  enforces it.
- **The fetch-vs-decoder `sequential` overlay (TASK-267) cannot be made static**, because one member (TLS) is
  heap+library-owned. That pair must stay a **runtime** overlay (the current JIT-at-`_play()` — keep it). The
  planner contributes the decoder's *size* and the *headroom* the fetch needs; the *timing* stays runtime.

So M-MEMPLAN is **not** "everything static." It is: *statically plan and budget everything we own; declare and
gate the headroom for what we don't.* That honest split is the whole value — the unknowns become a single
budgeted number, checked at build time.

## 7. Integration

- **Tool:** `app/tools/gen_mem_layout.py` (host, venv) — mirrors `gen_app_registry.py`. Inputs
  `app/mem_manifest.yaml`; outputs `app/gen/mem_layout.h` + `app/gen/mem_layout.py`.
- **Gate:** add a 6th `check_build.sh` step — (a) **staleness** (re-gen diffs clean, like [5/5]) and (b) the
  **WCMU budget assertion** (the planner exits non-zero on overflow). Both block the build.
- **Determinism:** fold `mem_layout.*` into the existing golden-hash discipline.
- **Review:** the manifest is the diff-reviewable single source of truth; a memory change is a manifest PR,
  not a scattered hunt through `new`/`malloc`/`createSprite` sites.

## 8. Migration from the runtime arena (what we built)

Incremental, no rip-and-replace:
1. **Author the manifest** from the current real numbers (M-MEMBUDGET §1 + the EXP-010 measurements —
   decoder 23,216, InBuff 6,400, heatmap 2,560, sprites…) and stand up the tool + gate. *(No code change yet —
   just makes the budget declarative + checked.)*
2. **Back the existing `mb_arena` free-list with the planned static region** instead of `mb_arena_acquire`'s
   `heap_caps_malloc` (point `mb_arena_init` at `MEM_webradio_decoder`). Keeps the validated allocator + the
   3-site fork; drops the runtime reservation + JIT-acquire **for the decoder** — *but* re-check §6: a
   static-always decoder region competes with the fetch TLS (the TASK-265 problem). So **either** keep the
   decoder runtime-JIT (overlaid with TLS at the heap level) **or** prove the static region + headroom fits
   the fetch (the WCMU gate decides). This is the key open question (OQ1).
3. **Migrate the easy tenants first** (heatmap doc via ArduinoJson allocator → static region; sprites) — they
   have no TLS tension, so they go fully static immediately and validate the planner on low-risk buffers.

## 9. Invariants & risks

- **§4b scratch-vs-state invariant** is enforced *by the planner* (`kind: state` rejected from multi-app
  groups) — stronger than the prose rule today.
- **(R1 / OQ1)** the decoder-vs-TLS tension (§6) — static-always vs runtime-JIT. The current JIT solution is
  validated (TASK-267 PASS); don't regress it for elegance. The planner may keep the decoder runtime and only
  *budget* it. Decide with the WCMU numbers.
- **(R2)** dynamic sizes — a buffer whose size depends on runtime config (e.g. a per-country station table)
  must declare its **worst case** in the manifest (WCMU is a worst-case discipline).
- **(R3)** third-party allocations the manifest can't see drift the real headroom — the `headroom` figure
  must be measured (EXP-010 caps-split probes) and kept honest, not guessed.
- **(R4)** over-overlay — putting two buffers in the same group that *can* coexist (a missed concurrency)
  corrupts memory. The `group` declaration is load-bearing and must be review-gated (like the NEW-APP-CHECKLIST).

## 10. Open questions

- **OQ1:** decoder region — static-always (simpler layout, but must fit fetch TLS) vs keep runtime-JIT (proven,
  but not "fully planned"). The WCMU budget answers it.
- **OQ2:** manifest format — YAML (proposed, matches `feature_inventory`) vs extend the `appRegistry.h`
  X-macro. YAML is richer; the planner can still cross-check ownership against `appRegistry`.
- **OQ3:** do background tasks (spotifyTask/dataTask stacks) enter the manifest as `headroom` line-items or as
  `kind: state` non-overlaid regions? (They're resident, not overlay-eligible — M-MEMBUDGET §2c.)

## 11. Links

M-MEMBUDGET (the budget + the overlay concept this formalizes) · ADR-047 + Amendment 1 (the runtime arena this
succeeds) · EXP-010 (the measured sizes that seed the manifest) · `gen_app_registry.py` (the codegen pattern)
· linker overlays / `union` / WCMU (the named techniques).
