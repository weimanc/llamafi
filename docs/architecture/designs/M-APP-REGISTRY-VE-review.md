# M-APP-REGISTRY — VE Review

> Reviewer: Verification Engineer  
> Date: 2026-06-06  
> Design doc: [M-APP-REGISTRY.md](M-APP-REGISTRY.md)  
> ADR: [ADR-041](../decisions/ADR-041.md)  
> Status: **Pre-implementation review — do not implement until blockers resolved**

---

## VE Review

### 1. Testability of the disable-app workflow

**Problem:**  
The design proposes `if "Matrix" not in APP_SLOT: skip(...)` as the runtime guard inside test functions. This is correct for tests that are keyed to a single named app. However, `_switch_to(dut, "Matrix", APP_SLOT["Matrix"])` passes the **slot index** to `tap_taskbar_slot()`, which computes a Y-coordinate as `app_id * TASKBAR_SLOT_H + TASKBAR_SLOT_H // 2`. When an app is disabled, every app below it shifts one slot up. A test that navigates by `APP_SLOT["Life"]` will now physically tap the wrong on-screen row if the DUT firmware was built with a different registry than the `app_ids_gen.py` that was imported at test-launch time.

The guard `if "Matrix" not in APP_SLOT` protects the **test logic**, but there is no guard verifying that the firmware on the DUT was built from the same `appRegistry.h` revision that produced the currently-loaded `app_ids_gen.py`. If the DUT is flashed with an older firmware and the test suite is re-run after a codegen update (or vice versa), `APP_SLOT` will be out of sync with the DUT's actual slot layout. No error will be reported — the tap lands on the wrong slot and the test fails with a misleading app-name mismatch.

Additionally, the scroll-offset assumption is separate from the skip-guard (see point 6).

**Severity:** High

**Resolution:**  
Add a boot-time serial probe that reads the DUT's app count (`get appCount` or `get appId` cycling) and compares it to `APP_COUNT` from `app_ids_gen.py`. Fail fast with a clear error message if they disagree. Alternatively, expose a `get registryHash` debug command that returns a short hash of the active `appRegistry.h` bake, and verify it against a companion value emitted by `gen_app_registry.py`.

---

### 2. Golden hash / check_build.sh atomicity

**Problem:**  
The design says "update golden hash after firmware rebuild" as step 3 of the disable-app workflow. The current `golden.sha256` covers `skin_assets.c`, `skin_layout.h`, and `shell_layout.h` — the skin/layout codegen outputs. It does **not** cover `app_ids_gen.py` or `configurable_apps.h`. Updating the golden hash is therefore a separate, manual step with no enforcement relationship to the codegen step.

The risk is a half-committed state: `appRegistry.h` is edited, codegen is re-run (generating new `app_ids_gen.py` and `configurable_apps.h`), but the developer forgets to rebuild and re-bake the golden hash. `check_build.sh` passes (the skin assets are unchanged), giving a false green.

**Severity:** Medium

**Resolution:**  
Two options:

- **Option A (preferred):** Add `app_ids_gen.py` and `configurable_apps.h` to the golden hash file so `check_build.sh` catches stale generated files as part of its existing check 3. This means adding a staleness check step to `check_build.sh` that re-runs `gen_app_registry.py` into a temp dir and diffs the output (see also point 5).

- **Option B:** Document in `appRegistry.h` (as a comment block, not just as a reminder) that codegen + golden-hash update are atomic. This relies on discipline, not enforcement — acceptable only as a short-term mitigation.

The design notes "check_build.sh can optionally verify the generated files are not stale" — this should be promoted from optional to required.

---

### 3. App rename (g_spotifyApp → g_SpotifyApp) — partial-rename failure mode

**Problem:**  
The design specifies a sed-pass rename of all `g_<name>App` globals to `g_<Name>App` (capitalised). A partial rename — missing one reference — is **not** caught at compile time as a link error if the definition and the extern declaration are in different translation units. Specifically:

- `g_spotifyApp` is defined as a `static SpotifyApp g_spotifyApp;` inside an anonymous scope in `main.cpp`.
- The X-macro expansion produces `extern App g_SpotifyApp;` in the forward-declaration pass.
- These are two **distinct** names. The compiler emits an `undefined reference to g_SpotifyApp` linker error — so a total miss is caught.

However, the failure is at link time, not compile time, and only on the target that includes both expansions. The debug build and the production build are linked separately. If only one build target is tested after the rename (e.g. `cyd2usb_winamp` compiles but `cyd2usb_winamp_debug` is not tried), a missed reference in the debug-only section of `main.cpp` could slip through.

There is also a subtler risk: the `_switch_to_stock` helper uses `switchApp _STOCK_APP_ID` (a numeric serial command), bypassing the dispatch table entirely. No rename is needed there, but if during the refactor the Developer accidentally renames the numeric `switchApp <N>` handler along with the enum, that path breaks silently — the serial command still accepts a number but now indexes into a different app.

**Severity:** Medium

**Resolution:**  
`check_build.sh` already builds both `cyd2usb_winamp` and `cyd2usb_winamp_debug`. This is sufficient to catch link errors as long as both builds exercise the renamed symbols. The rename procedure should explicitly state: run `check_build.sh` immediately after the sed pass, before any other changes. Add a grep assertion to the implementation task: `grep -rn 'g_spotifyApp\|g_clockApp\|g_weatherApp' app/src/` must return zero matches after the rename.

---

### 4. Test coverage gaps for the refactor itself

The design document lists a manual verification checklist (comment out Aquarium, rebuild, flash, check taskbar) but does not specify automated assertions that can be run on every build. The following are missing:

**4a. `icons[]` count vs `AppId::COUNT`**  
After the refactor, `icons[]` is generated via X-macro and its size equals `AppId::COUNT` automatically — no explicit `static_assert`. There is currently a `static_assert(TASKBAR_X == 275, ...)` guard in `appShell.h` (line 127). A companion assert should be added:

```cpp
static_assert(sizeof(icons) == (int)AppId::COUNT, "icons[] out of sync with AppId");
```

This must be in a context where `icons[]` is visible — either inline in `renderTaskbar` or via a separate `constexpr` count. Without it, if someone hand-edits `taskbar.h` after the refactor, drift re-emerges silently.

**4b. `kConfigurableApps` count vs CONFIGURABLE flag count**  
After the refactor, `kConfigurableApps` is generated by `gen_app_registry.py` and `CONFIGURABLE_APP_COUNT` is a macro in `configurable_apps.h`. There is no C++ or Python assertion verifying that `CONFIGURABLE_APP_COUNT` equals the number of rows with `cfg==1` in `appRegistry.h`. A Python-side check in `gen_app_registry.py` itself (assert len(configurable_names) == CONFIGURABLE_APP_COUNT before writing the file) would close this.

**4c. `APP_COUNT` in Python vs `AppId::COUNT` in firmware**  
There is no DUT-side probe that reads the firmware's `AppId::COUNT` and compares it to `APP_COUNT` from `app_ids_gen.py`. The `get appCount` or `get tbScrollOffset` commands could be used for a startup sanity check in the test harness. This is the same issue raised in point 1 but deserves its own test assertion.

**4d. Settings > Applications row count vs registry CONFIGURABLE count**  
Covered separately in point 7.

**Severity:** Medium (4a, 4b), Low (4c — partially covered by operational failure)

**Resolution:**  
- Add `static_assert(sizeof(icons) == (int)AppId::COUNT, ...)` inside `renderTaskbar` or in a dedicated `appRegistry_checks.h`.  
- Add a Python assertion in `gen_app_registry.py` after computing the configurable list.  
- Add a DUT-vs-`app_ids_gen.py` count check to the Dut `_verify_debug_firmware()` startup sequence or as an explicit precondition in `run_serialdbg_tests.py`.

---

### 5. Stale generated files — no staleness guard

**Problem:**  
`app_ids_gen.py` and `configurable_apps.h` are checked into git (by design) and generated by a script that is run on demand. The design acknowledges this and mentions "a comment block at the top of `appRegistry.h` reminds the developer to re-run the script." This is the same "honour system" approach that caused the original six-file drift problem the design is solving.

Concretely:

1. Developer edits `appRegistry.h` (adds a new app row).
2. Forgets to run `gen_app_registry.py`.
3. `check_build.sh` step 1 and 2 pass — the C++ macro expands from `appRegistry.h` directly, so the firmware is correct.
4. `check_build.sh` step 3 passes — `golden.sha256` covers skin assets, not generated Python/C files.
5. Tests run using the **old** `app_ids_gen.py` with the old `APP_SLOT` mapping. Tests navigate to wrong slots and fail with misleading errors — or worse, accidentally pass because the new app was appended at the end and slot numbers below it are unchanged.

**Severity:** High

**Resolution:**  
`check_build.sh` must include a staleness check for `app_ids_gen.py` and `configurable_apps.h`. Implement as follows in `check_build.sh`:

```bash
echo "[5/5] gen_app_registry staleness check"
TMPDIR=$(mktemp -d)
"$VENV_PY" app/tools/gen_app_registry.py --out-dir "$TMPDIR"
if diff -q "$TMPDIR/app_ids_gen.py" app/tools/app_ids_gen.py > /dev/null && \
   diff -q "$TMPDIR/configurable_apps.h" app/gen/configurable_apps.h > /dev/null; then
    ok "generated files are up to date"
else
    fail "app_ids_gen.py or configurable_apps.h is stale — re-run gen_app_registry.py"
fi
rm -rf "$TMPDIR"
```

This is the only mechanical guard that makes the "single source of truth" claim true end-to-end.

---

### 6. Taskbar scroll offset assumption in `_switch_to`

**Problem:**  
`_switch_to(dut, "Matrix", APP_SLOT["Matrix"])` calls `tap_taskbar_slot(APP_SLOT["Matrix"])` which computes `y = slot * TASKBAR_SLOT_H + TASKBAR_SLOT_H // 2`. This is the **visual** position of slot N assuming `tbScrollOffset == 0`. If `tbScrollOffset != 0`, the app displayed at that Y-coordinate is `(slot - tbScrollOffset) % COUNT`, not `slot`. The tap lands on the wrong app.

Inspecting the test suite: the `_tb_precondition` function (used by T162–T166) explicitly resets `tbScrollOffset` to 0 before each test. However, `_switch_to` callers in T_MA_01–T_MA_03, T_GOL_01–T_GOL_04, T_WX_01–T_WX_05, and T_CX_01–T_CX_05 call only `_restore_spotify(dut)` beforehand. `_restore_spotify` taps slot 0 (`tap_taskbar_slot(0)`) which works regardless of scroll offset (Spotify is always the displayed icon at physical Y=20 only if `tbScrollOffset==0` or Spotify happens to be at offset position 0 due to wrap). If a previous test leaves `tbScrollOffset` at a non-zero value, `_restore_spotify` itself will fail silently (it taps the wrong app and then checks `get appId`), causing the next test to skip rather than exposing the scroll-offset corruption.

This is a pre-existing fragility that the refactor makes worse: after the refactor the slot numbers in `APP_SLOT` are authoritative, but there is still no per-test precondition in `_switch_to` callers (outside T162–T166) that resets `tbScrollOffset`.

**Severity:** Medium (pre-existing fragility, worsened by refactor expanding the test scope)

**Resolution:**  
Either:

- **Option A:** Add `_tb_set_offset(dut, 0)` as the first step inside `_switch_to` itself (make it always-safe, not caller responsibility).
- **Option B:** Add a `_require_offset_zero` precondition to every test function that calls `_switch_to`, documented as a house rule.

Option A is strongly preferred — it makes `_switch_to` self-contained. The cost is one or more drag gestures per call; negligible for correctness.

Note also: `_restore_spotify` also hardcodes `tap_taskbar_slot(0)`. After the refactor it should be updated to `tap_taskbar_slot(APP_SLOT["Spotify"])` and should call `_tb_set_offset(dut, 0)` first.

---

### 7. Settings > Applications list — no test covers the configurable set

**Problem:**  
The current `appsSection.h` has a hardcoded `kNames[] = { "Stock","Crypto","Aquarium","Matrix","Life" }` (5 entries, matching 5 apps with `cfg==1`). After the refactor this list is generated from `configurable_apps.h`. The existing test T-SET-03 taps "row 5" (the Applications section), then taps "row 0" (which it expects to be Stock). T-SET-07 drills into "row 2" (expected to be Aquarium).

These tests assume a specific row-to-app mapping that is currently correct by coincidence (the generated order matches the current hardcoded order). If a developer:

1. Adds a new configurable app inserted **before** Stock in `appRegistry.h`, or
2. Reorders existing configurable apps, or
3. Disables one configurable app (e.g. Stock),

then T-SET-03's `tap row 0 → expect submenu==0 (Stock)` and T-SET-07's `tap row 2 → expect Aquarium` will silently navigate to the wrong submenu. The test will either fail with an unexpected submenu index or, if the new first app happens to have submenu==0, pass falsely.

There is **no test that reads back the on-screen Settings > Applications list and verifies it matches the `CONFIGURABLE` set from `app_ids_gen.py`**.

**Severity:** High

**Resolution:**  
Two changes needed:

1. Add a serial debug command `get configAppCount` (or read `settingsSection`/`submenu` state after drilling) so the test harness can read the number of configurable apps at runtime and compare to `len(CONFIGURABLE)` from `app_ids_gen.py`. Expose the configurable app name at a given index via `get configAppName <i>`.

2. Update T-SET-03 and T-SET-07 to navigate by name, not by hardcoded row index. Compute the target row by looking up `sorted(list(CONFIGURABLE)).index("Stock")` (or whatever ordering `configurable_apps.h` imposes) rather than hardcoding `0` and `2`. Add a new test `T-SET-XX` that iterates over every entry in `CONFIGURABLE` and verifies it appears in the Settings > Applications list.

Until these changes are made, the Settings tests will become a source of false-passing or misleading failures immediately after any registry reorder.

---

## VE Sign-off

### Blockers — must fix before implementation begins

| # | Concern | Location |
|---|---------|----------|
| B1 | No staleness guard for generated files in `check_build.sh` (point 5) | `check_build.sh` |
| B2 | Settings tests navigate by hardcoded row index; will silently pass/fail wrong after any reorder or disable (point 7) | `run_serialdbg_tests.py`, T-SET-03, T-SET-07 |
| B3 | No firmware-vs-test-suite sync check; `APP_SLOT` drift goes undetected at test runtime (point 1) | `run_serialdbg_tests.py` startup |

### Recommendations — should fix during implementation

| # | Concern | Location |
|---|---------|----------|
| R1 | `_switch_to` does not reset `tbScrollOffset`; all non-T162 callers are fragile (point 6) | `run_serialdbg_tests.py`, `_switch_to` |
| R2 | No `static_assert` that `icons[]` size == `AppId::COUNT` after refactor (point 4a) | `taskbar.h` or new `appRegistry_checks.h` |
| R3 | `gen_app_registry.py` should assert `len(configurable_names) == CONFIGURABLE_APP_COUNT` before writing (point 4b) | `gen_app_registry.py` |
| R4 | Golden hash update for the skin codegen should be explicitly excluded from the atomicity requirement, but the design doc must state clearly what IS atomic (codegen + `check_build.sh` staleness step) (point 2) | `check_build.sh`, design doc |
| R5 | `_restore_spotify` should use `APP_SLOT["Spotify"]` and pre-reset scroll after refactor (point 6) | `run_serialdbg_tests.py` |

### Acceptable as-is

| # | Concern | Rationale |
|---|---------|-----------|
| A1 | Partial-rename failure at link time (point 3) | Both targets are built by `check_build.sh`; linker will catch undefined references. Acceptable if check_build.sh is run immediately after the sed pass. |
| A2 | `_STOCK_APP_ID` bypasses taskbar navigation via `switchApp <N>` (point 3, secondary) | Intentional design choice documented in the design doc ("numeric IDs may shift … acceptable for a dev tool"). No test correctness impact since `_switch_to_stock` uses the serial numeric command. |
| A3 | `coords.py` — no change needed (design doc §4) | `tap_taskbar_slot` is index-agnostic. Correct. |
