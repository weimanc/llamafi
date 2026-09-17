# Design note — TASK-702: the repaint signal ADR-063 D4 wants may not be cheaply buildable

> Owner: Architect
> Status: proposed
> This is a scope question for human ruling, not an implementation plan — see
> "Options for the human" at the foot; no option is recommended over another.
> Date: 2026-09-17
> Feeds: TASK-702
> Tracked-as: TASK-702
> Registers: none

## What D4 already decided, and why the first attempt failed

`ADR-063.md` D4 already picked the mechanism, in detail: *"progress is a shell-owned counter array, not an app-owned counter... A counter the app increments in its own tick is a counter the app can be wrong about in exactly the way the test is trying to detect; a counter the shell increments is one the app cannot fake."* TASK-702 is not "pick a mechanism" — that's done. It's "find the shell-observable signal D4 requires, without changing `App::tick()`'s contract across 13 apps."

The one prior attempt (`60f98004`, reverted before any DUT run) incremented a shell-side counter in lockstep with the shell's own `appTick()` dispatch call — which counts *calls*, not *repaints*. It was correctly pulled: it claimed a measurement (`appRepaints`) it wasn't making, and IFC-007 would have frozen that false claim permanently.

## The one working precedent doesn't generalize

`ADR-059 D12`'s `pleditRepaints` (`app/src/winamp/pleditView.h:159`, `_repaints++`) is the cited model, and it works — but it works by being **inside the component's own draw function, past that component's own internal dirty-check guard** (`if (!seqnoChanged && !_scrollDirty) return;`, `app/src/winamp/pleditView.h:140`). That's an app-owned signal, placed correctly by the app that knows its own repaint logic. It is exactly the shape D4 says is unacceptable as the *general* mechanism ("a counter the app increments... can be wrong in exactly the way the test is trying to detect") — it only escapes that objection here because pleditView already had a dedicated VE finding (D12) demanding it, and a human decided placing it there was trustworthy enough for that specific gate. It was never meant to generalize to "the shell's cross-cutting per-app signal," and per D4's own stated reasoning, it can't: an app-placed counter is exactly the kind of thing D4 exists to rule out at the shell level.

## Two candidate shell-level mechanisms, both checked and both blocked

**Hook a universal drawing entry point.** If every app funneled its drawing through one shared call (e.g. `tft.startWrite()`), the shell could wrap that one call, keyed by `currentAppId`, with zero per-app cooperation — exactly D4's "app cannot fake it" bar. **Checked, refuted**: only 4 of the ~13+ drawing sources in `app/src/` (`clockApp.cpp`, `vuMeter.h`, `pleditView.h`, `winampDisplay.cpp`) call `tft.startWrite()`/`endWrite()` explicitly (for batched multi-op transactions); the rest presumably call individual `TFT_eSPI` primitives (`fillRect`, `drawString`, ...) that handle their own transaction internally, per-call, inside the library. There is no single call site in *this project's* code that all apps' drawing passes through.

**Patch the library itself.** The actual universal point — inside `TFT_eSPI`'s own primitive draw methods — would close this cleanly (same shape as this project's existing vendored-and-patched libraries: `app/lib/SD`, `app/lib/WiFiClientSecure`, each with a `LOCAL_PATCHES.md`). **Checked, and this is the real finding**: `TFT_eSPI` is **not vendored** in this repo (`app/platformio.ini:23`: `bodmer/TFT_eSPI@^2.5.33`, a plain registry dependency, unlike SD/WiFiClientSecure/ESP32-audioI2S which are all deliberately vendored+patched+documented). Vendoring a third-party graphics library — with its own update/security-patch tracking burden going forward — to answer a P3 test-observability finding is a disproportionate, precedent-setting cost this design does not recommend paying.

**A third option, checked and rejected on the project's own stated grounds**: a new virtual method (e.g. `App::didRepaint()`) with a safe default, following the exact incremental-override pattern ADR-063 D1-D3 already uses for the identity guard (safe default, one app per commit, never a forced sweep — D6). This looked promising as "reuse the pattern this project already trusts" until re-reading D4's own reasoning: **this is, structurally, exactly the app-owned counter D4 already named and rejected** — the app decides what `didRepaint()` returns, which is "wrong in exactly the way the test is trying to detect." Reusing D1-D3's *shape* doesn't fix that D4 requires the *shell*, not the app, to hold the ground truth.

## The actual tension

D4's requirement (shell-owned, app-cannot-fake, no `App::tick()` contract change) and this codebase's actual rendering architecture (no universal draw hook in project code, `TFT_eSPI` not vendored) are in real conflict. Every mechanism that satisfies "app cannot fake it" requires either changing `tick()`'s contract (ruled out by TASK-702's own framing) or vendoring a library this project has never needed to vendor before (a real, disproportionate cost for what this is). Every mechanism cheap enough to avoid both of those is, on inspection, an app-owned signal D4 already rejected by name.

This is not a "pick the lean option" situation the way TASK-706/708 were. It's a scope conflict between two already-made decisions (D4's falsifiability bar, and "don't touch `tick()`'s contract") that the original ADR didn't anticipate would collide this specific way, because the `pleditRepaints` precedent it cited doesn't generalize the way it reads like it should.

## Options for the human, not a recommendation

1. **Relax D4's falsifiability bar** for this specific signal — accept an app-owned "did I repaint" signal (the D1-D3-shaped virtual method), on the reasoning that a wrong-by-omission app is still strictly better than today's total absence of a signal, and note the residual risk explicitly (an app *could* misreport, same as any self-attested state) rather than pretending the shell verifies it.
2. **Change `App::tick()`'s contract after all**, in the D6-mandated one-app-at-a-time landing order, accepting the larger, slower rollout TASK-702's own framing was trying to avoid.
3. **Vendor `TFT_eSPI`** to get a true shell-owned hook — the "correct" answer to D4's letter, at a real and lasting maintenance cost this design does not recommend paying for a P3 finding.
4. **Close TASK-702 as `UNOBSERVABLE`, dated** — D6 itself already names this exact escape hatch for the per-app clauses ("if a freshly derived `.dram0.bss` headroom reads under ~1 KB, stop... and ledger the per-app clauses as dated `UNOBSERVABLE` rows"); this finding is arguably in the same shape — a genuine gap, honestly recorded as currently unclosable at reasonable cost, rather than forced shut.

This design does not pick between these — it's a genuine values tradeoff (falsifiability vs. contract stability vs. new vendoring burden) that needs a human ruling, not an Architect's technical judgment call.
