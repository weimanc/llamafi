# M-TESTQUAL WP-H — the Clock, Teletext and PlaneRadar families, audited per test

> Owner: **Verification Engineer**
> Status: done
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Prior packages: [WP-A harness](M-TESTQUAL-A-harness-review.md), [WP-B taxonomy](M-TESTQUAL-B-taxonomy-review.md), [WP-C gating classes](M-TESTQUAL-C-audit-core-review.md), [WP-D shell FEATURE](M-TESTQUAL-D-audit-shell-review.md), [WP-E player](M-TESTQUAL-E-audit-player-review.md), [WP-F webradio](M-TESTQUAL-F-audit-webradio-review.md), [WP-G stock](M-TESTQUAL-G-audit-stock-review.md)

---

## 0. Scope, and how the corpus was measured

Every id whose body lives in `app/tools/suite/serialdbg/clock.py`,
`teletext.py` or `planeradar.py`.

```sh
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
m=build_all_meta()
for t,v in m.items():
    if v['module'] in ('clock','teletext','planeradar'):
        print(v['module'], t, v['cls'], v['scope'], v['effect'])"
# -> 26 ids: 14 clock, 3 teletext, 9 planeradar.
#    All cls=FEATURE. scope = Clock / Teletext / PlaneRadar (module-seeded).
#    effect = mutating, except T_PR_04 and T_PRM_01 = resetting.
```

The index's §3 row says "26 ids". **It is 26** — the first family row in this
review that was already correct. `TESTS` confirms it: `clock.py:244-259`
(14 entries), `teletext.py:213-217` (3), `planeradar.py:495-505` (9).

The taxonomy is **100 % module-seeded**. No `@meta(...)` declaration appears in
any of the three files (`grep -n "@meta" clock.py teletext.py planeradar.py` →
no hits), so every `(cls, scope, effect)` triple is `_meta.py`'s inference from
the module name and id prefix (`_meta.py:29-33`). Unlike WP-G's `T182`, nothing
in this corpus is materially mis-scoped — the only near-miss is `T272`, whose
subject is Spotify/dataTask TLS contention rather than Teletext rendering, but
it does drive the Teletext fetch and `--scope Teletext` is the right selector.

**Registry position matters here more than in any prior package.** These 26 ids
are indices **0–25 of 213** — the whole corpus runs before anything else in the
suite:

```sh
python3 -c "import sys;sys.path.insert(0,'app/tools')
from suite.serialdbg import build_all_tests, build_all_meta
t=list(build_all_tests()); m=build_all_meta()
for i,k in enumerate(t):
    if m[k]['module'] in ('clock','teletext','planeradar'): print(i,k)"
# 0..13  T_CLK_01..T_CLK_14
# 14..16 T272, T270, T271
# 17..25 T_PR_01..T_PR_06, T_PRM_01, T_PRM_02, T_PRI_01
```

So every state this corpus leaks is leaked into 187 downstream ids, and every
`_order.py` question about it is unanswered: **`_order.py` contains not one
entry for any of these 26 ids** (`grep -n "T_CLK\|T27[012]\|T_PR" _order.py` →
no hits).

Static audit only, per rubric §5: no flash, no `run/test*`, no serial port. The
board is pinned to the `-DBOD_WATCH` debug build for TASK-557.
`build_all_tests`/`build_all_meta` were the only imports made under `app/tools/`
(rubric §5 / amendment A1); `clock.py`, `teletext.py`, `planeradar.py`,
`_helpers.py`, `_meta.py`, `_order.py`, `coords.py`, `app_ids_gen.py`,
`lib/dut.py`, `clock_tap_smoke.py`, `flaky.yaml`, `test_plan.md`,
`regression_suite/m-clock-styles.md`, and the firmware under `app/src/apps/`,
`app/src/debug/serialConsole/`, `app/src/dataTask.h`,
`app/src/dataTaskStorage.cpp`, `app/src/planeRadarConfig.h`,
`app/gen/teletext_layout.h` and `app/src/main.cpp` were **read**, never imported
or executed.

Per amendment A2 the per-test tables put the **body location in column one** and
the id in column two, and no section is headed with a bare id.

### 0.1 What is distinctive about this corpus

1. **Three families, three different engineering eras, and the spread is the
   finding.** PlaneRadar (2026-07, TASK-307/355/357) designed its observables
   first — `get activeError`'s `active`/`connecting` split, `get prInterp`'s
   decayed `offsetPx`, `get dataq`'s `inFlightMs` — and six of its nine ids are
   SOUND. Clock (2026-06, TASK-193) was given exactly one observable,
   `get clockStyle`, and wrote fourteen ids against it; **one** is SOUND. It is
   WP-E's and WP-G's lesson for the third and fourth time — *the quality of a
   test tracks the quality of the observable it was given* — and here it is
   visible as a 6× spread inside one 26-id package.
2. **The Clock family's exit-criteria table books five visual criteria against
   oracles that cannot see a pixel.** `regression_suite/m-clock-styles.md:46-55`
   records **PASS** for C4 (flip animation ≤500 ms, no pixel residue) against
   `T_CLK_13` "responsiveness proxy", C5 (Nixie tubes within y:5..85) against
   `T_CLK_04` "DUT accepts, no crash", C6 (VFD segment visibility) against
   `T_CLK_05` same, C7 (non-Flip 1000 ms tick gate) against `T_CLK_11` "no heap
   anomaly", and C8 (Spotify→Clock→Spotify no pixel residue) against `T_CLK_12`
   "app stable". **A clock face that rendered as a solid black rectangle would
   pass all five, and the whole 14-id family.** That is **H-2**, and it is the
   most direct answer this review has produced to the rubric's one question.
3. **The third armed-and-never-cleared debug injector is here, and it is the
   cleanest instance of the three.** `set prInjectAircraft` sets
   `_injected = true` (`planeRadarApp.cpp:279`), which makes `tick()`,
   `resume()`, `handleInput()`'s range branch and `_setActiveLoc()` all skip the
   real fetch (`:27`, `:33`, `:37`, `:135`, `:164`). It is cleared by exactly
   two things: `set prClearInject 1` (`:268-272`) and `init()` (`:8`) — and
   `resume()` **explicitly does not** (`:27` is a *guarded* fetch, not a clear).
   `T_PRI_01`, the last id in the corpus, injects twice and never clears.
   **H-1.**
4. **Teletext is three ids against a 596-line app, and the interesting finding
   is what is absent.** All three are sound-or-weak and none of them is cheating.
   But the app's synthetic-content injector (`set teletextPageContent`), its
   numpad, its fast-text bar, its grid hit-test, its history ring, its error
   latch and four of its seven `dbgGet` keys have **no reader anywhere under
   `app/tools/`**. §5 is the required list.

---

## 1. The Clock family — `T_CLK_01`…`T_CLK_14` (14)

Registry order `clock.py:244-259`, indices 0–13.

### 1.1 The five firmware facts that decide this whole family

**(a) `clock.py` drives apps by hardcoded slot number, and never imports the
generated registry.** `_switch_to_clock` sends `switchApp 1` (`clock.py:11`),
`_restore_spotify_from_clock` sends `switchApp 0` (`:20`), and `T_CLK_09` sends
`switchApp 4  # Matrix` (`:152-153`). `grep -n "app_ids_gen\|APP_SLOT" clock.py`
→ **no hits**; `teletext.py:9` and `_helpers.py:16` both import it. This is WP-A
**A-8** / **D1**.
**The numbers are currently correct** — `app_ids_gen.py:4` gives
`APP_ORDER = ['Spotify','Clock','Weather','Crypto','Matrix', …]`, so Spotify=0,
Clock=1, Matrix=4 — so **A-8/D1's stronger reading, that the family "could be
driving the wrong app and still pass", is refuted as a live defect and confirmed
as a latent one**: the mirror is right today and nothing would tell you the day
it stopped being right. `console.cpp:91`'s own help string is already stale on
the same fact (`"<appId 0..8>"` against `APP_COUNT = 13`).

**(b) `_switch_to_clock` verifies nothing.** It returns `True` on
`r.get("ok")` (`clock.py:11-15`), and `cmdSwitchApp` prints
`{"ok":true,"cmd":"switchApp","id":%d}` echoing **the id the host sent**, not
`currentAppId` (`cmdMisc.cpp:26-27`). So the ack is literally the harness's own
argument coming back. Thirteen of the fourteen ids enter Clock this way and
**only `T_CLK_01` ever reads `get appId`**. Contrast `_helpers._switch_to`,
which taps the real taskbar slot and then asserts
`r.get("name") == app_name` (`_helpers.py:321-331`) — the path both other
families in this package use.

**(c) `set clockStyle` writes flash on every call.** `cmdSet.cpp:669-671`
assigns `g_settings.clockStyle`, calls `SettingsStorage::save()`
**unconditionally**, and then calls `g_ClockApp.resume()` if Clock is the
foreground app. `get clockStyle` reads back the same `g_settings.clockStyle`
(`cmdGet.cpp:538`). So every `set`/`get` pair in this family is a round trip
through one settings member with a flash write in the middle — and the family
issues roughly **forty** of them (`T_CLK_06` 5, `T_CLK_11` 9, `T_CLK_12` 4, plus
one per `_restore_spotify_from_clock`, `clock.py:18`).

**(d) `get clockStyle`'s `last` field is a compile-time literal.**
`cmdGet.cpp:542-547` prints `\"last\":true` as a fixed string. No device state
can make it anything else. `T_CLK_14` asserts it.

**(e) Nothing in this family observes a pixel, a tap, or a reboot.** No id calls
`tap`; no id reboots; no id reads `get clockLastAction` (`cmdGet.cpp:552-558`),
the `dirty` field (`cmdGet.cpp:544`), `nixieTheme`/`vfdTheme`, or
`settingsSaveCount`. `ClockApp::repaint()`/`_doTick()` and the four face
renderers are 330 lines of drawing (`clockApp.cpp:89-454`) with no `dbgGet`
surface at all.

### 1.2 Per-test table

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `clock.py:23` | T_CLK_01 | `switchApp(1)` switches to Clock. | `get appId`'s `id == 1` after the switch. | **SOUND** | S11, S14 | `:27-33`. The only body in the family that reads a device value the harness did not write: `get appId` reports `(int)currentAppId` and the name from the generated `appRegistry.h` table (`cmdGet.cpp:225-236`), so a `switchApp` that silently failed fails here. Costs: the `1` is fact (a) — a mirror of `APP_SLOT["Clock"]` that no gate checks; it uses the serial `switchApp` rather than the taskbar tap, so the production entry path is untested (`_helpers.py:321-331` is one import away); and `_restore_spotify_from_clock` writes `set clockStyle 0` (`:18`) on the way out, i.e. a flash write and a user-setting overwrite in a test that never set a style. |
| `clock.py:37` | T_CLK_02 | "`clockStyle` **defaults** to digital after a fresh settings load." | `get clockStyle`'s `name == "digital"` — read 200 ms after the body's own `set clockStyle 0`. | **HOLLOW** | S3, S2 | `:44-47`. The body's own comment says what it did: *"Force digital first to ensure a known baseline"*. There is no fresh settings load, no reboot, no `SettingsStorage::load()` and no default anywhere in the sequence — `set clockStyle 0` writes `g_settings.clockStyle` (`cmdSet.cpp:669`) and `get clockStyle` reads the same member back (`cmdGet.cpp:538`), with nothing between the write and the read. The claimed behaviour — that a device with no `settings.json`, or a corrupt one, comes up Digital — is asserted by nothing in the suite. This is `T178`'s shape (WP-G **G-7**) with the injection and the assertion on the *same* key. |
| `clock.py:51` | T_CLK_03 | `set clockStyle flip` is accepted and reads back. | `set`'s own `name == "flip"`, then `get clockStyle`'s `name == "flip"`. | **WEAK** | S2, S3, S13 | `:57-63`. There is one real term here and it is worth naming precisely: `set` maps name→index through `kSN` in `cmdSet.cpp:660` and `get` maps index→name through a **second, separate** `kSN` in `cmdGet.cpp:537`, so a divergence between the two tables does fail this id. Everything else is the harness's own input — the `set` reply's `name` is the set handler echoing its own table, and the readback is the same settings member. What it cannot see is the entire subject: `resume()` → `repaint()` → `_tickFlip()` (`clockApp.h:45`, `clockApp.cpp:89-96`, `:235-265`). A Flip face that painted a black rectangle passes. |
| `clock.py:67` | T_CLK_04 | `set clockStyle nixie` accepted + readback. | Same two terms, `"nixie"`. | **WEAK** | S2, S3, S13 | `:73-79`. Byte-for-byte `T_CLK_03` with one string changed. Same single real term (the two `kSN` tables), same blindness to `_tickNixie`/`_drawNixieTube`/`_tintNixieGlyph` (`clockApp.cpp:346-404`). `m-clock-styles.md:52` books this id as **PASS** for exit criterion **C5, "Nixie: tubes within y:5..85"**, annotated *"(DUT accepts, no crash)"* — a geometry criterion recorded as met by a settings round trip. |
| `clock.py:83` | T_CLK_05 | `set clockStyle vfd` accepted + readback. | Same two terms, `"vfd"`. | **WEAK** | S2, S3, S13 | `:89-95`. Same again. `m-clock-styles.md:53` books it as **PASS** for **C6, "VFD: active/inactive segments visible"** — a visibility criterion against a settings round trip, while `_drawVFDDigitSlot`'s on/off segment colours (`clockApp.cpp:406-421`, `_vfdOnColor`/`_vfdOffColor`, `clockApp.h:257-258`) are exactly what a regression would break and exactly what nothing reads. |
| `clock.py:99` | T_CLK_06 | All four styles are reachable by numeric index 0..3. | Per index: `set`'s `val == i`, then `get clockStyle`'s `name == names[i]`. | **WEAK** | S2, S3, S13, S11 | `:105-113`. The strongest of the four style ids and a **strict superset of `T_CLK_03`/`04`/`05`** — it covers all four names *and* the numeric-parse branch (`cmdSet.cpp:662`'s `sscanf` fallback), which the three name-only ids do not. Three registry ids therefore collapse into this one (S13, and the clearest duplicate-test instance in the package). Costs unchanged: `["digital","flip","nixie","vfd"]` at `:105` is a fourth copy of `kSN`, mirrored rather than parsed; nothing observes a face. |
| `clock.py:117` | T_CLK_07 | An invalid `clockStyle` value is rejected. | `set clockStyle oled` → `ok is not False`, then `set clockStyle 9` → same. | **WEAK** | S2, S6 | `:123-128`. A genuine negative on a real validator — `cmdSet.cpp:661-668` rejects both a bad name and an out-of-range index, and `atoi`-style silent coercion would fail this id. The weakness is that **`ok:false` is not specific to that validator**: the rejection reply carries no `"var"` field at all (`cmdSet.cpp:665-667`), and `cmdSet`'s unknown-var fallthrough returns `ok:false` too — so the id passes identically if `clockStyle` were removed from `cmdSet` entirely. It also never re-reads `get clockStyle` to confirm the rejected value was **not** applied, which is the half that matters. One `r.get("error","").startswith("bad val")` plus one readback closes both. |
| `clock.py:132` | T_CLK_08 | "`clockStyle` **persists in settings.json** (save confirmed)." | `get clockStyle`'s `name == "nixie"`, 400 ms after the body's own `set clockStyle nixie`. | **HOLLOW** | S3, S2, S12 | `:138-141`. The claim is persistence; the oracle is a RAM member read back through the same command that wrote it (`cmdSet.cpp:669` → `cmdGet.cpp:538`). **Nothing in the body reboots, reads SPIFFS, reads `get clockStyle`'s `dirty` field, or reads `settingsSaveCount`** — all three of which exist (`cmdGet.cpp:544`, `clockApp.h:60-68`, `clock_tap_smoke.py:64`). The firmware *does* save (`cmdSet.cpp:670`), and the adjacent `set fmt24h` even reports whether the save succeeded — `\"saved\":%s` from `SettingsStorage::save()`'s return (`cmdSet.cpp:634-638`) — while `set clockStyle` throws that return away, so the one honest observable is not even emitted. `m-clock-styles.md:50` books this id (with `T_CLK_09`) as **PASS** for **C3, "Style persists across app switch + power cycle"**; no id in the family power-cycles. `T_PR_04` and `T_PRM_01`, twenty ids later, show what a real persistence test looks like. |
| `clock.py:145` | T_CLK_09 | An app switch away and back preserves `clockStyle`. | `get clockStyle`'s `name == "flip"` after `switchApp 4` → `switchApp 1`. | **HOLLOW** | S3, S8, S2 | `:151-156`. `clockStyle` is a field of the global `g_settings` (`cmdSet.cpp:669`), and **no app-switch code path writes it** — `switchApp` runs `init()` or `resume()` (`appShell.cpp:200-207`), and `ClockApp::init`/`resume` call `_snapshotPersisted()` + `repaint()`, neither of which touches `g_settings.clockStyle` (`clockApp.h:44-45`, `clockApp.cpp:50-55`). The assertion cannot fail for the reason it exists; it is a global variable compared against itself across two commands. The Matrix hop is unverified as well (`switchApp 4` is fire-and-forget, fact (b)), so the id does not even establish that it left Clock. |
| `clock.py:160` | T_CLK_10 | `appId` stays Clock=1 while the VFD style is active. | `get appId`'s `id == 1` after `set clockStyle vfd`. | **WEAK** | S3, S8, S13 | `:166-169`. Claim and oracle match exactly, and the claim is trivial: `currentAppId` changes only on a `switchApp` or a taskbar tap, neither of which happens here, so the only regression reachable is a **hang or crash inside `_tickVFD`** — which is real, because `runner.py:431-433` converts a `TimeoutError` from `dut.cmd` into `fail(tid, …)`. That is the whole value of the id: a VFD-renderer watchdog. It is worth having and it is not what the row claims to be about; `T_CLK_13` is the same watchdog for Flip (S13). |
| `clock.py:173` | T_CLK_11 | Heap is stable after cycling all four styles twice. | `info`'s `heap` before vs after; `fail` if `h0 - h1 >= 4096`. | **WEAK** | S6, S8, S10 | `:179-189`. Two real device reads (`ESP.getFreeHeap()`, `cmdMisc.cpp:41,50`) compared against a threshold, so it is not hollow. Three things narrow it. **(a) S6 in the unsafe direction:** `r0.get("heap", 0)` and `r1.get("heap", 0)` (`:180`, `:186`) — if `info` ever fails or is raced, both default to `0`, `leak = 0`, and the id passes without a measurement. **(b) The bound cannot be violated.** The cycled code path is `repaint()` → `fillRect` + `memset` + `tick()` (`clockApp.cpp:89-117`); nothing on it allocates, so no realistic regression reaches 4096 B. `4096` has no cited origin. **(c)** `h0` is taken immediately after the switch with no settle, against the project's own 150 s heap-settle rule (memory `project_task425_arena_sd_shortfall`). And `m-clock-styles.md:54` books it as **PASS** for **C7, "non-Flip styles: 1000 ms tick gate"** — a heap delta cannot observe a tick interval. |
| `clock.py:193` | T_CLK_12 | Clock→Spotify transition is stable; Spotify is active afterwards. | `get appId`'s `id == 0` after four style writes and `switchApp 0`. | **WEAK** | S13, S14, S8 | `:199-204`. The device read is real and is the inverse of `T_CLK_01` — which is also what every other body in the family performs as teardown (`_restore_spotify_from_clock`, `:20-21`), so as an assertion it is the family's thirteenth switch-back with a `get appId` bolted on (S13). Two costs. **It is the one body that omits the restore** — no `_restore_spotify_from_clock` call, so it exits with `clockStyle = 3 (vfd)` **written to `settings.json`** (`cmdSet.cpp:670`); `T_CLK_13`/`T_CLK_14` behind it happen to restore Digital, so the leak is contained by luck, not design (S14, **H-4**). And `m-clock-styles.md:55` books it as **PASS** for **C8, "Spotify→Clock→Spotify: no pixel residue"** while reading no pixel — every other family's residue test at least polls `lastPlaylistDraw` through `_check_residue` (`_helpers.py:177-192`), which this one does not, although it is in the shared helper module the file does not import. |
| `clock.py:207` | T_CLK_13 | "Flip animation **tick gate** — 30 ms while animating vs 1000 ms stable." | `get clockStyle`'s `name == "flip"` (the body's own write) and `get appId`'s `id == 1`. | **HOLLOW** | S3, S4, S12, S8 | `:213-222`. The claimed subject is `ClockApp::tick()`'s `gate = anyFlip ? 30 : 1000` (`clockApp.cpp:31-33`). **Nothing in the body observes an interval, a frame count, or `_anyFlipActive()`** — there is no `dbgGet` for any of them — and the body says so in a comment (`:211-212`), then asserts two values that cannot fail: the style it just set, and an `appId` no command in the body could change. What remains is `T_CLK_10`'s crash watchdog with a different face. The pass string quietly redefines the id — *"device responsive during Flip style"* (`:224`) — which is not the claim in its own docstring, in `test_plan`'s absence, or in `m-clock-styles.md:51`, where it is booked **PASS** for **C4, "Flip: animation ≤500 ms; no pixel residue"**. Under the rubric that is a claim-vs-oracle mismatch (S12) on top of a tautology. |
| `clock.py:226` | T_CLK_14 | `get clockStyle`'s response format: `val` int, `name` str, `last` true. | Three field comparisons after `set clockStyle 2`. | **HOLLOW** | S3, S8, S13 | `:232-239`. All three terms are unfalsifiable by anything except deleting the getter. `val == 2` and `name == "nixie"` are the body's own `set clockStyle 2` read back (fact (c)); `last is True` is a **compile-time string literal** in the printf (`cmdGet.cpp:545`) that no device state can vary (fact (d)). The one genuine service it performs — catching a schema break in `get clockStyle` — is already performed generically and for every app by `test_task488_partb.py:177`, which asserts the key resolves and carries `("style","val","name")`. A schema test whose every value is a constant is the rubric's S3 in its purest form. |

### 1.3 What the Clock family would have to do to be a Clock test

Not a fix list — a statement of how far the observables are from the subject,
because five of the fourteen verdicts turn on it.

* The app has **one** debug read (`get clockStyle`) that reports a setting, and
  **one** (`get clockLastAction`) that reports an input outcome. Nothing reports
  a rendered fact: no digit positions, no colours, no frame counter, no
  `_anyFlipActive()`, no `_lastTickMs`.
* `run/screendump` exists and four WebRadio ids use it for exactly this class of
  claim (`webradio.py:1398-1428`, WP-F §6). C5 ("tubes within y:5..85") and C6
  ("segments visible") are colour/geometry assertions a screendump answers
  directly; C4's "no pixel residue" is the same delta-image comparison
  `T_WR_VIS_02` already performs.
* The two cheapest firmware additions — a `frames`/`gateMs` field on
  `get clockStyle`, and reporting `SettingsStorage::save()`'s return the way
  `set fmt24h` already does (`cmdSet.cpp:634-638`) — would convert `T_CLK_13`
  and `T_CLK_08` from HOLLOW to SOUND without touching either body's shape.

---

## 2. The Teletext family — `T272`, `T270`, `T271` (3)

Registry order `teletext.py:213-217`, indices 14–16.

### 2.1 The four firmware facts that decide these three rows

**(a) `_lastAction` is written before the guard, in every strip zone.**
`TeletextApp::_handleStrip` does `strlcpy(_lastAction, "STRIP_SUBDN", …)` and
*then* `if (_st.subpageNext) _navigate(…)` (`teletextApp.cpp:328-330`); the same
shape in all six zones (`:297-330`). So `get teletextLastAction` is an honest
**zone-routing** observable and is *not* evidence that the zone's action ran.
`T271`'s claim is routing, so this is exactly right for it; `T270`'s claim is
the navigate, so it needs a second term — and it has one.

**(b) `shellBusy` for Teletext is a real effect, not a tap side-effect.**
`cmdTap`'s Teletext branch sets busy **only** when the app reports pending async
work — `if (!shell::state().busy && g_apps[Teletext]->hasPendingAsync()) shell::setBusy(true)`
(`cmdTouch.cpp:70-74`) — and Teletext's `hasPendingAsync()` is
`_active()->hasPendingAsync()` = `NosTeletextSource::_pendingFetch`
(`teletextApp.h:105`, `:65`), which only `navigate()` sets true
(`teletextApp.cpp:69-72`). So `shellBusy == true` after a SUBDN tap **does**
prove `_navigate(617,2)` fired.

**(c) `set cooldown 0` is the wrong variable, three times.** `T270:111` and
`T271:187,199` issue it to clear the tap gate. It resolves to
`WinampDisplay::dbgSet("cooldown")`, which zeroes `touchScreenCoolDownTime`
(`winampDisplay.cpp:776-782`) — the TASK-052 **Spotify** dead-zone force-poll
timer. `cmdGet.cpp:468-470` documents the confusion in so many words
(*"Distinct from winampDisplay's `cooldown` var … despite the similar name"*).
The gate that actually applies here is `TeletextApp::handleInput`'s own 300 ms
`_lastTapMs` debounce (`teletextApp.cpp:139-144`); the shell's `cooldownMs` is a
third thing again, set only on a taskbar drag release (`console.cpp:135`). The
three calls are inert; `T271`'s `time.sleep(0.35)` is what is really clearing
the debounce.

**(d) The strip zone constants are generated, and the suite mirrors them
anyway.** `TTXT_STRIP_PAGE_Y1 = 66`, `BACK_Y0 = 67`, `BACK_Y1 = 99`,
`PREV_Y0 = 100`, `SUBDN_Y0/Y1 = 166/199`, `TTXT_STRIP_X = 240`
(`app/gen/teletext_layout.h:25-40`) — a **generated** header. `coords.py`
already parses two other generated headers with a generic `#define` regex
(`coords.py:9-23`) and does not parse this one; `teletext.py:8` imports
`coords as _c` and **never uses it** (`grep -n "_c\." teletext.py` → no hits).
So `257`, `182`, `66`, `67`, `99`, `100` are hand-copied literals sitting one
three-line function away from being parsed (LL-114, WP-A **A-9**).

### 2.2 Per-test table

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `teletext.py:15` | T272 | `fetchTeletext()` completes without OOM/watchdog while `spotifyTask` holds a TLS session, and Spotify survives it (ADR-044 item 9). | Two independent device reads: `get teletextReady`'s `ready is True` within 30 s, then `get lastPlaylistDraw`'s `ms > draw0` within 10 s after the switch back. | **SOUND** | S2, S7, S10 | `:27-89`. Both terms are real, both markers resolve (`teletextReady` at `teletextApp.cpp:171-175`; `lastPlaylistDraw` is the same field `_check_residue` uses, `_helpers.py:177-192`), and the second term is the one that makes it a *contention* test rather than a fetch test — a Spotify task starved or deadlocked by the teletext TLS session leaves the draw stamp parked and the id fails with the baseline in the message (`:86`). The failure-triage branch is also correctly directed: `http_code` defaults to `0` and `0` routes to `fail`, not `skip` (`:63-69`), so a missing getter cannot buy a skip. It is the only id in this package that imports the generated registry — `switchApp {APP_SLOT['Teletext']}` (`:34`). Costs: that switch is ack-only and a failure is a `skip` (`:35-38`), the same fact (b) defect as the Clock family though here it is a precondition rather than the subject; `_restore_spotify`'s return is discarded (`:56`); `30.0`/`10.0` are uncited; and `except TimeoutError: break` (`:52`, `:81`) silently converts a wedged DUT into the `not ready` / `not draw_advanced` path — which does end in `fail()`, so it is safe, but the reason string then blames the wrong thing. |
| `teletext.py:94` | T270 | A SUBDN tap **enqueues a subpage fetch** when `subpageNext` is set — `_navigate(617,2)` is called. No live network required. | Three terms: `get teletextSubpage`'s `next == 617 && nextSub == 2`; `get teletextLastAction == "STRIP_SUBDN"`; **`get shellBusy`'s `busy` true**. | **SOUND** | S3, S10, S11, S14 | `:114-149`. The load-bearing term is the third and it is genuinely load-bearing: by fact (b) `busy` goes true only through `hasPendingAsync()` → `_pendingFetch` → `navigate()`, so a SUBDN branch that routed correctly but never called `_navigate` — precisely the regression the id names in its own failure string (`:144`) — fails here. The other two terms are weaker than they look: term 1 is a round trip through `_st.subpageNext` written by the test's own `set teletextSubpageNext` (`teletextApp.cpp:234-242` → `dbgGet` `:202-208`), i.e. S3; term 2 is fact (a), a zone read that a no-op SUBDN would also satisfy. Costs: the tap reply's **`"skipped"` field is discarded** (`cmdTouch.cpp:47-51`) — if the busy gate swallowed the tap, `_lastAction` keeps its previous value and `shellBusy` reads true, so a *repeat* SUBDN under a stuck busy flag is a false pass; both `_wait_shell_not_busy` return values are discarded (`:110`, `:148`); `set cooldown 0` is fact (c); `257`/`182` are fact (d); and the comment at `:128-129` justifying the debounce is **wrong** — it says *"resume() set it to 0"*, but `resume()` → `_activateSource()` (`teletextApp.cpp:110-121`) does not touch `_lastTapMs`; only `init()` does (`:102`). The id works because `T272` is Teletext's first entry and therefore ran `init()`. |
| `teletext.py:154` | T271 | Right-strip **1-px zone boundaries** for PAGE_NUM / BACK / PREV_PAGE. | `get teletextLastAction` after four taps: y=67→`STRIP_BACK`, y=99→`STRIP_BACK`, y=100→`STRIP_PREV`, y=66→`STRIP_PAGE`. | **WEAK** | S3, S9, S10, S11, S14 | `:175-207`. `_lastAction` is the *right* observable for a routing claim (fact (a)) and two of the four taps are true 1-px boundaries against the generated header — 66/67 straddles `PAGE_Y1`/`BACK_Y0` and 99/100 straddles `BACK_Y1`/`PREV_Y0` (`teletext_layout.h:31-35`). What holds it at WEAK is that **step 2 cannot fail**: step 1 (y=67) has already left `_lastAction == "STRIP_BACK"`, so if step 2's tap is swallowed by the busy gate or the 300 ms debounce, the residue satisfies the assertion — and neither the tap reply's `skipped` flag nor `_wait_shell_not_busy`'s return is read at any of the four steps (`:185-189`, `:197-202`). One of the four boundary checks is therefore a residue pass. Three further costs. The 0.35 s sleeps are the real debounce handling (S9) — honestly derived from the firmware's 300 ms and stated in the comment (`:186`), but a sleep is still the synchroniser. The literals are fact (d). And the PAGE step **toggles `_numpadActive` on and nothing turns it off** (`teletextApp.cpp:302-306`) — the app is left with the keypad drawn over the grid until the next `_activateSource()` clears it (`:118`), self-healing but not by this test's doing (S14). Also worth recording: the id covers **2 of the strip's 5 boundaries**; SUBUP/PAGE (33/34), PREV/NEXT (132/133) and NEXT/SUBDN (165/166) are untested. |

### 2.3 The plan rows for all three no longer describe the bodies

Not a per-test verdict, but it is the third instance of WP-G **G-12** and it is
worse here because all three plan entries still read **Status: planned**
(`test_plan.md:4467`, `:4479`) or carry a `[Blocked: …]` tag on an id that has
been in the registry and dispatched by `run/test` since TASK-197:

* `### T270` (`test_plan.md:4459-4466`) is headed *"Subpage ▲/▼ zones"*, tagged
  `[NETWORK] [Blocked: G1, G2]`, and its Steps say `tap 257 16` (the **SUBUP**
  centre) asserting `get teletextSubpage != S0`. The body taps `257 182`
  (SUBDN), asserts `teletextLastAction` + `shellBusy`, needs no network, and
  covers only ▼.
* `### T271` (`:4468-4480`) is headed *"◄◄ back zone 1-px boundary"* and its four
  Steps expect the action strings **`KEYPAD_OPEN`, `BACK`, `BACK`,
  `PREV_PAGE`**. The firmware has never emitted any of those — the strings are
  `STRIP_PAGE`/`STRIP_BACK`/`STRIP_PREV` (`teletextApp.cpp:297-330`), and
  `grep -rn KEYPAD_OPEN app/src/` returns nothing. A reader triaging a red run
  from the plan would grep the firmware for a marker that does not exist.
* `### T272` (`:4481-4497`) is the one that matches, and it is the only one of
  the three whose "Steps" a reader could follow.

---

## 3. The PlaneRadar family — `T_PR_01`…`T_PRI_01` (9)

Registry order `planeradar.py:495-505`, indices 17–25.

### 3.1 The four firmware facts that decide these rows

**(a) `_injected` is a boot-scoped latch that `resume()` does not clear.**
`set prInjectAircraft` sets `_injected = true` (`planeRadarApp.cpp:279`);
`set prClearInject 1` (`:268-272`) and `init()` (`:8`) are the only two things
that clear it. Every real-fetch site is guarded — `resume()`'s enqueue (`:27`),
`tick()`'s poll-interval enqueue and its `pollPlaneRadar()` drain (`:33`, `:37`),
the range-tap re-enqueue (`:135`) and `_setActiveLoc()`'s (`:164`) — so while it
is set, the app renders whatever was injected and **never fetches again**. This
is **H-1**.

**(b) `isConnecting()` is `!_everHadResult`, a never-had-data latch.**
`planeRadarApp.h:244`, `:278`. It is set true by a successful poll (`:60`) *and*
by an injection (`:306`), and reset only by `init()` (`:6`) and `_setActiveLoc()`
(`:153`). So `connecting → false` is a **once-per-boot** transition; every id
that waits on it after the first PlaneRadar entry is waiting on a latch that is
already down. The family knows this about `errorCode` — the TASK-313 lesson,
cited at length in three docstrings — and does not know it about `connecting`.

**(c) A deterministic fault injector exists and no test uses it.**
`set prForceParseFail n` (`planeRadarApp.cpp:242-245`) →
`debugForcePlaneRadarParseFail` (`dataTaskStorage.cpp:2020-2023`), which makes
the next *n* fetch attempts return `r.ok = false, errorCode = -92` without
touching the network (`:1305-1317`), which drives `_prErr = true` (`:72-73`),
which is `hasError()` (`planeRadarApp.h:245`) — exactly the `activeError.active`
latch `T_PR_05` spends twenty rate-limit attempts trying to provoke.
`grep -rn prForceParseFail app/tools/ run/` returns **nothing**.

**(d) Every range write is a flash write.** `_setPreset()` assigns
`g_settings.prRangeIdx` and calls `SettingsStorage::save()`
(`planeRadarApp.cpp:347-350`), and both the disc tap and `set prRange` share it
(`:135`, `:246-254`). `T_PR_03` alone performs five.

### 3.2 Per-test table

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `planeradar.py:30` | T_PR_01 | Spotify→PlaneRadar→Spotify round trip; `appId` correct at each step. | `_switch_to`'s and `_restore_spotify`'s own `get appId` `name` comparisons, both directions. | **SOUND** | S13, S14 | `:33-46` via `_helpers.py:321-331`, `:286-306`. Both legs are device-verified against the app name, and — unlike the Clock family's equivalent — the entry is the **real taskbar tap** (`_c.tap_taskbar_slot(APP_SLOT["PlaneRadar"])`), so the id covers the production path. It is also the only body in the package that suspends background Spotify polling across the switch (`_bgpoll_suspended`, `:37-38`, `_helpers.py:445-454`), the contention hygiene WP-G noted `T169` for. Costs: it is thin (the assertions live entirely in shared helpers) and it duplicates the switch-in precondition every later id in the family performs (S13); and by fact (b) it is the entry that consumes `_everHadResult` for the boot, which is `T_PR_02`'s oracle. |
| `planeradar.py:49` | T_PR_02 | Exit criterion 1: **live aircraft render** within one poll of app entry. | `get activeError`'s `connecting` going false inside 90 s, then `active` false. `prAircraftCount` is read and **only printed**. | **WEAK** | S8, S13, S6, S4 | `:69-89`. The choice of `connecting` over `prLastHttp == 200` is correct and well-argued (the docstring's TASK-313 reasoning matches `planeRadarApp.cpp:55-73` exactly — a successful fetch leaves `errorCode` at its default 0), and the 90 s budget is derived rather than guessed. Two things hold it at WEAK. **(a) The oracle is a boot-scoped latch (fact b), and its own predecessor is the entry that flips it.** `T_PR_01` at index 17 is PlaneRadar's first entry, so `init()` runs there and enqueues; by the time `T_PR_02` enters at 18, `resume()`'s enqueue plus the drain of any result left queued from `T_PR_01` can satisfy `connecting == false` within one tick — proving "a fetch has resolved since boot", which is not "within one poll of *this* app entry". On any third or later entry the term is pre-satisfied outright. **(b) The word in the criterion is "render" and no pixel, count or draw stamp is asserted** — `prAircraftCount` is read at `:78` and interpolated into the pass string at `:89`, never compared, and the plan explicitly allows `prAircraftCount == 0` to pass (`test_plan.md:4701`). `err_r.get("active")` also has no default (`:85`), so a malformed reply reads as "no error". |
| `planeradar.py:92` | T_PR_03 | Exit criterion 2a: a disc tap cycles the range presets 5→10→15→25→5. | `get prRange` after each of four taps, compared against the exact list `[10, 15, 25, 5]`. | **SOUND** | S11, S14, S10 | `:106-122`. Four device reads against an exact sequence — the strongest oracle shape in the package. `get prRange` reports `kPrPresetKm[_presetIdx]` (`planeRadarApp.cpp:177-180`) against `kPrPresetKm = {5,10,15,25}` (`planeRadarConfig.h:13`), and `handleInput` advances `(_presetIdx + 1) % PR_NUM_PRESETS` (`:133`), so an ordering change, an off-by-one, or a failed wrap each fail loudly. The injection is used for a documented and *correct* reason — the `!_injected` guard at `:135` would otherwise re-arm `hasPendingAsync()` per tap and let the busy gate swallow the next one — and, unlike `T_PRI_01`, **it clears** (`:117`). Costs: `PR_CX, PR_CY = 120, 120` (`:28`) mirrors `planeRadarApp.h:22` and the preset list is mirrored as a Python literal (S11, both self-documented); five `SettingsStorage::save()` calls by fact (d); and it exits with `prRange = 5` rather than the default 10, with no restore (S14). |
| `planeradar.py:125` | T_PR_04 | Exit criterion 2b: the range preset survives a **reboot**. | `set prRange 25` → `reboot` → `_wait_for_ready()` → re-enter → `get prRange == 25`. | **SOUND** | S7, S14 | `:135-152`. A real power-cycle oracle: `dut.send("reboot")` followed by `dut._wait_for_ready()` (`lib/dut.py:606`), then a fresh `_switch_to` and a readback. `_setPreset` persists through `SettingsStorage::save()` (`planeRadarApp.cpp:349-350`) and `_applyRangeSetting()` re-seeds `_presetIdx` from `g_settings.prRangeIdx` on entry (`:337`), so a broken load path or a dropped save fails here. **This and `T_PRM_01` are the only two genuine persistence tests in the 26-id corpus** — the direct contrast with `T_CLK_08`, which claims persistence and never leaves RAM. Costs: the pre-reboot readback failure exits as a `skip` (`:137-139`) although it is the test's own `set` failing, not an environment precondition (S7); `prRange = 25` is left persisted with no restore, and only `T_PRI_01` four ids later happens to put it back to 10 (`:480`) as a side effect of its own setup (S14); and it reaches into `Dut._wait_for_ready`, a name-mangled private, as do `T_PRM_01` (`:303`) and `player.py:1610`. |
| `planeradar.py:155` | T_PR_05 | Exit criterion 3: a fetch error surfaces as `activeError.active`, the app stays responsive, and it recovers on the next poll. | When an error is provoked: `active` true → `get appId.name == "PlaneRadar"` → `active` false within 30 s. **Otherwise `skip`.** | **WEAK** | S7, S10 | `:176-230`. When it runs, the oracles are right, and the family gets the `activeError`-vs-`errorCode` question right on purpose: it gates on the boolean `active` (`hasError()` = `_prErr`, `planeRadarApp.h:245`, `cmdGet.cpp:242`) with the ambiguity of `errorCode == 0` spelled out in the docstring — WP-G found Stock reaching the same answer by accident, this family reaches it by argument. But the precondition is a **live rate-limit** and it is not reliably reachable: `test_plan.md:4727` records the id as **SKIP 2026-07-11** and `flaky.yaml:157` lists it as an unmeasured candidate. **Fact (c) is the finding**: a deterministic hook (`set prForceParseFail 3`) that produces exactly this latch has existed since TASK-361, and both the body's docstring (`:159-160`) and the plan row (`:4727`) still state *"No dedicated fault-injection hook exists for PlaneRadar yet"* — written before it did. Two lines convert a permanent SKIP into a deterministic test. `12.0`/`20`/`30.0`/`90.0` are uncited. |
| `planeradar.py:233` | T_PR_06 | Exit criterion 6: **synthetic-injection render test** — inject 3 → count 3, `prLastHttp` unchanged (no fetch attempted), clear → count 0. | `get prAircraftCount == 3`. Nothing else is compared. | **WEAK** | S3, S6, S4, S14 | `:244-257`. One of the three stated claims is asserted, and it is the weakest of the three: `prAircraftCount` reports `_result.count` (`planeRadarApp.cpp:168-170`) which `set prInjectAircraft` itself wrote (`:301`), so it is a round trip through one struct field — real enough to catch a broken record parser (`sscanf`'s `n == 9` gate, `:294-300`) but not a render. The other two claims are read and dropped: `r_after` is fetched at `:251` and appears **only in the pass string** at `:256-257`, so the `prClearInject` half of the criterion has no assertion at all, and `prLastHttp` is never read despite the docstring's *"prLastHttp stays whatever it was"*. And, as with `T_PR_02`, the criterion says *render* and the oracle is a counter — `_render()`/`_erasePrev()`/`_updateStripDynamic()` are never observed. |
| `planeradar.py:271` | T_PRM_01 | `prPollSec` round-trips at 1/10/30, clamps 99→30, and **persists across a reboot**. | Three set/get round trips, one clamp assertion, then `reboot` → `_wait_for_ready()` → `get prPollSec == 30`. | **SOUND** | S11, S3 | `:286-309`. Five assertions of which two are real firmware behaviour rather than round trips: the **clamp** (`set prPollSec 99` → `if (s > PR_POLL_MAX_SEC) s = PR_POLL_MAX_SEC`, `planeRadarApp.cpp:259-262`) and the **reboot persistence** (`SettingsStorage::save()` inside the same handler, `:263`). It is also the most disciplined teardown in the corpus — `set prPollSec 10` is issued on **every** exit path (`:291`, `:298`, `:305`), including both failure paths, which no other body in this package manages. Costs: `1`/`30` mirror `PR_POLL_MIN_SEC`/`PR_POLL_MAX_SEC` as literals (S11); the three 1/10/30 round trips are S3 in isolation and earn their place only as the clamp's control; `dut._wait_for_ready()` again; and **the id has no `### T_PRM_01` entry in `test_plan.md`** — this is the exact id WP-B hit as a C6 orphan (index ledger 2026-09-03, rubric A2). |
| `planeradar.py:312` | T_PRM_02 | At `prPollSec = 1` the poll loop is fetch-completion-paced (~4–5 s), serialized, does not pile up, and does not starve Spotify — over a 5-minute window. | Five bounded assertions over 300 s of `get dataq` samples: `>= 20` distinct `inFlightMs` stamps while `inFlight == 8`; `min gap >= 1500 ms`; `3000 <= median gap <= 9000`; `max queueWaiting <= 2`; `max (ms - spActMs) <= 120000`. | **SOUND** | S6, S11, S10 | `:359-406`. The best-instrumented body in the package and one of the best in the review. Every term is a device-observed field that exists (`DbgQueueState`, `dataTask.h:350-358`; emitted at `cmdGet.cpp:103-118` with `ms`, `queueWaiting`, `inFlight`, `inFlightMs`, `spActMs` all present), every bound has a stated derivation (`_pendingFetch` serialization for the min gap, TASK-313's ~4.3 s measured edge pacing for the median, "other apps' bg fetches legitimately queue" for the ≤2), it uses the **dispatch-start stamp as a fetch identity** rather than counting samples — immune to aliasing, and exactly the `_fetchIssuedMs` lesson from TASK-367/377 — and it restores `prPollSec = 10` **before** judging (`:374`) so a failure cannot leave the board at 1 s. `PR_FETCH_TYPE = 8` (`:269`) matches `DATA_FETCH_PLANERADAR = 8` (`dataTask.h:20`): **WP-A finding D6's mirror is correct today**, and it is still a hand-maintained mirror with a "keep in sync with the enum" comment and no gate (S11). Costs: `q.get("queueWaiting", 0)` and the `spActMs`/`ms` guard (`:369-371`) default in the **pass** direction — a renamed field silently satisfies two of the five bounds (S6); there is no `### T_PRM_02` plan entry; and it is the most flake-exposed id in the corpus (a 300 s live-network window at index 24) and is **not** in `flaky.yaml`. |
| `planeradar.py:413` | T_PRI_01 | TASK-357: the dr-damped(τ=2 s) motion offset is continuous on a re-sighting and **decays** toward 0. | Four comparisons on `get prInterp`'s `offsetPx`: exactly `0.0` on first sighting; `0.3 <= off0 <= 39.0` after the shifted second fix; `off1 < 0.6 * off0` at t+2 s; `off2 < 0.3 * off0` at t+4 s. | **SOUND** | S10, S14 | `:439-492`. Four assertions on a **computed** value, not a stored one: `dbgGet("prInterp")` recomputes `offsetPx` with `expf(-fixAgeMs / PR_INTERP_TAU_MS)` at read time (`planeRadarApp.cpp:203-217`), so the decay terms genuinely test the decay law and a τ change fails them. The upper bound `39.0` is tied to `PR_INTERP_SNAP_PX = 40` (`planeRadarApp.h:157`), which makes the un-snapped window a real, non-vacuous band rather than a guess. And it is **the only body in the whole package whose defaults all point the safe way**: `r_first.get("offsetPx", -1) != 0.0` fails on a missing field, and `off1 = r_t1.get("offsetPx", off0)` makes a missing field fail the `< 0.6 * off0` test. The two DUT-verification bugs that produced that discipline are documented in place (`:418-424` the leftover-preset trap, `:466-473` the restore-before-read trap that made both decay reads return a "nothing tracked" 0.0 — *"decaying-looking, but for the wrong reason"*), and both are exactly the failure class this review keeps finding elsewhere. Costs: `0.3`, `0.6` and `0.3` are uncited (only `39.0` is tied to a constant, and only in prose); there is no `### T_PRI_01` plan entry; and it exits with **`_injected` still true** — **H-1**, a family finding rather than a verdict on the body, which can fail for its reason. |

---

## 4. The deliberate hunt — a third armed injector, and what else leaks

### 4.1 `set prInjectAircraft` is the third one (**H-1**, proposed cluster `C11`)

The brief asked for a third instance of WP-F **F-4** (`set wrDeadUrls`, cluster
`C9`) and WP-G **G-1** (`set triggerHeatmap`'s `prevSubView` write, cluster
`C10`): *a `set` command whose effect outlives the test that issued it, with no
restore in the body and no clear in the firmware's `init()`/`enter()`/`resume()`*.
There is one, and structurally it is the cleanest of the three.

**The mechanism, in five lines of firmware.**

1. `set prInjectAircraft <records>` assigns `_injected = true`
   (`planeRadarApp.cpp:279`), installs a synthetic `PlaneRadarResult`, and sets
   `_everHadResult = true`, `_prErr = false` (`:305-307`).
2. **Every** real-fetch site is guarded on `!_injected`: `resume()`'s entry
   enqueue (`:27`), `tick()`'s poll-interval enqueue (`:33`), `tick()`'s
   `pollPlaneRadar()` result drain (`:37`), the disc-tap range re-enqueue
   (`:135`), and `_setActiveLoc()`'s (`:164`).
3. It is cleared by exactly two things: `set prClearInject 1` (`:268-272`) and
   `PlaneRadarApp::init()` (`:8`).
4. **`resume()` does not clear it.** Line `:27` is a *guarded enqueue*, not a
   reset — and `switchApp` runs `init()` only on an app's first entry per boot,
   `resume()` on every later one (`appShell.cpp:200-207`). So an app switch does
   not clear it; only a reboot does.
5. Therefore `_injected == true` is a fixed point for the rest of the boot, and
   it is reachable **only** through the debug injector.

**`T_PRI_01` leaves it set.** The body clears at the *start*
(`planeradar.py:440`), injects twice (`:442`, `:453`), and its teardown is
`set prRange 10` + `_restore_spotify` (`:480-481`) — **no `set prClearInject`**.
Its two siblings both clear (`T_PR_03:117`, `T_PR_06:249`); `T_PRI_01` is the
one that does not, and it is the last id in the family.

**Blast radius, stated honestly.** Smaller than `C9`'s or `C10`'s, and only by
accident of registry order:

* `T_PRI_01` is index **25**; no later registry id enters PlaneRadar
  (`grep -rn "PlaneRadar" app/tools/suite/serialdbg/*.py` outside
  `planeradar.py` → only `player.py:394`'s comment and `_helpers.py:400`'s
  `_TB_N` derivation), so **no other id's verdict changes**.
* What *is* damaged is the device for the remaining 187 ids: PlaneRadar sits in
  injected mode showing one frozen aircraft (`AAA111`) with `_everHadResult`
  latched true and `_prErr` false, until the next reboot — which in the current
  order is `T_PLR_26` at index ~111 (`player.py:1610`). Anyone who looks at the
  radar after a `run/test`, or runs `test_planeradar_soak.py` in the same boot
  (its oracle is `get appId.name`, and it *prints* `prAircraftCount` without
  comparing it — `test_planeradar_soak.py:88-98`), sees a green result on an app
  that has not fetched since index 25.
* Under the class-ordered switch (WP-B **B-8**) the reboot moves and the window
  changes; nothing in `_order.py` records the dependency either way, because
  `_order.py` has no entry for any id in this corpus (§0).

**The fix is one line** — `dut.cmd("set prClearInject 1")` alongside the
`set prRange 10` at `planeradar.py:480`, which is what `T_PR_03` and `T_PR_06`
already do. The firmware-side fix, and the better one for the same reason WP-G
gave for `C10`, is for `PlaneRadarApp::resume()` to clear `_injected`: an
injection is a *within-app-visit* instrument, and no test in the suite wants it
to survive an app switch.

### 4.2 Two candidates that turned out to be self-healing

Recorded because a refuted candidate is a result:

* **`set teletextSubpageNext 617-2`** (`T270:114-118`) writes `_st.subpageNext`
  and `_activateSource()` does **not** clear `_st` (`teletextApp.cpp:110-121`;
  only `init()` memsets it, `:100`). But `NosTeletextSource::poll()` assigns
  `*out = result` — a wholesale copy of a freshly default-constructed
  `TeletextState` (`:75-91`) — so the **next successful page fetch overwrites
  both subpage targets**, and Teletext fetches on its own poll interval while
  foreground. Self-healing within one poll. Not a `C9`-class leak.
* **`set clockStyle`** persists (§1.1 (c)) and `T_CLK_12` never restores, but
  `T_CLK_13` and `T_CLK_14` behind it both call `_restore_spotify_from_clock`,
  which writes `set clockStyle 0` (`clock.py:18`). The user's setting is
  clobbered and the *suite* is not damaged. Filed as **H-10**, P2, not P1.

### 4.3 S14 leakage against WP-B §5.2's clusters, plus `C7`/`C9`/`C10`

Nine of 26 rows carry S14. Mapped against the existing clusters:

| Leaked quantity | Ids | Restored? | Cluster |
|---|---|---|---|
| `_injected` (PlaneRadar synthetic mode) | `T_PRI_01` | **no** | **new `C11`** (§4.1) |
| `g_settings.clockStyle` (persisted, flash) | all 14 clock ids write it; `T_CLK_12` alone omits the restore | by the *next* id, not by itself | extends `C1`'s shape (WP-B **B-5**) — but unlike `stockMode` this one is written to `settings.json` on every call, so it is worse |
| `g_settings.prRangeIdx` (persisted, flash) | `T_PR_03` exits at 5, `T_PR_04` exits at 25 | only incidentally, by `T_PRI_01:480` | new, minor; same shape as `C1` |
| `g_settings.prPollSec` | `T_PRM_01`, `T_PRM_02` | **yes**, on every exit path | — (the model to copy) |
| `_numpadActive` (Teletext keypad left open) | `T271` | by the next `_activateSource()` | self-healing |
| `_st.subpageNext/Prev` | `T270` | by the next successful poll | self-healing (§4.2) |
| app-under-test left non-Spotify | none — every body restores | — | — |

**Nothing in this corpus touches `C7` (`songDuration`, WP-D), `C9`
(`wrDeadUrls`) or `C10` (`prevSubView`)**, and nothing downstream of index 25 in
this corpus arms them. The corpus's own contribution is `C11` plus a settings-
persistence leak that is a *user-facing* defect rather than a suite one.

### 4.4 Firmware markers and `get` keys: every one resolves

WP-G found `get fetchErrorCode` had never existed (**G-3**), so this package
checked every key and every asserted string against `app/src/`. **All resolve:**

| Key / marker | Read by | Firmware |
|---|---|---|
| `get appId` (`id`, `name`) | `T_CLK_01`, `T_CLK_10`, `T_CLK_12`, `T_CLK_13`, `T_PR_05`, `T_PRM_02` | `cmdGet.cpp:225-236` |
| `get clockStyle` (`val`, `name`, `last`) | 12 clock ids | `cmdGet.cpp:536-548` |
| `info` (`heap`) | `T_CLK_11` | `cmdMisc.cpp:39-50` |
| `get teletextReady` (`ready`) | `T272` | `teletextApp.cpp:171-175` |
| `get teletextHttpCode` (`val`) | `T272` | `teletextApp.cpp:186-190` |
| `get lastPlaylistDraw` (`ms`) | `T272` | (shared with `_check_residue`, `_helpers.py:177-192`) |
| `get teletextSubpage` (`next`, `nextSub`) | `T270` | `teletextApp.cpp:202-209` |
| `get teletextLastAction` (`val`) | `T270`, `T271` | `teletextApp.cpp:191-195` |
| `STRIP_SUBDN` / `STRIP_BACK` / `STRIP_PREV` / `STRIP_PAGE` | `T270`, `T271` | `teletextApp.cpp:298`, `:310`, `:319`, `:303` |
| `get shellBusy` (`busy`) | `T270` | `cmdGet.cpp:462-466` |
| `get activeError` (`active`, `connecting`) | `T_PR_02`, `T_PR_05`, `T_PRM_02` | `cmdGet.cpp:238-256` |
| `get prRange`, `prAircraftCount`, `prLastHttp`, `prPollSec`, `prInterp` | 7 PlaneRadar ids | `planeRadarApp.cpp:168-224` |
| `get dataq` (`ms`, `queueWaiting`, `inFlight`, `inFlightMs`, `spActMs`) | `T_PRM_02` | `dataTask.h:350-358`, `cmdGet.cpp:100-119` |
| `PR_FETCH_TYPE = 8` | `T_PRM_02` | `DATA_FETCH_PLANERADAR = 8`, `dataTask.h:20` — **WP-A `D6`'s mirror is correct today** |

The one *asserted string* in the package that does not exist in the firmware is
in `test_plan.md`, not in a body: `### T271`'s Steps expect `KEYPAD_OPEN`,
`BACK`, `PREV_PAGE` (`test_plan.md:4472-4477`) and
`grep -rn "KEYPAD_OPEN" app/src/` returns nothing (**H-13**).

---

## 5. Coverage absence — what each app has that nothing tests

The extra section this package was asked for. Every entry names a concrete
surface (a `dbgGet`/`dbgSet` key with no reader, an input handler no id taps, a
documented criterion with no id), not a hypothetical bug. "No reader" means
`grep -rn --include=*.py <key> app/tools/` returns nothing outside the file
named.

### 5.1 Clock — the tap-cycle feature is entirely outside the registry

| Surface | Firmware | Registry coverage |
|---|---|---|
| `ClockApp::handleInput` — the two tap zones (`CLK_TAP_SPLIT_Y`), `_cycleFace()`, `_cycleTheme()` | `clockApp.cpp:38-48`, `:63-87` | **none — no clock id issues a `tap` at all** |
| `TAP_FACE` / `TAP_THEME` / `TAP_THEME_NA` / `DEBOUNCE` outcomes | `clockApp.cpp:43`, `:66`, `:81`, `:84` | **none** |
| `get clockLastAction` | `cmdGet.cpp:552-558` | **no registry reader** — only `clock_tap_smoke.py:104,125`, a standalone harness with no id (and one of the six modules that open the port at import time, rubric §5) |
| `get clockStyle`'s `dirty` field + `_flushStyleIfDirty()` / `_snapshotPersisted()` deferred-persistence design | `cmdGet.cpp:544`, `clockApp.cpp:50-61`, `clockApp.h:60-68` | **no registry reader**; `clock_tap_smoke.py:140` only |
| `get settingsSaveCount` | (paired with `dirty` by design) | **no registry reader** |
| `set nixieTheme` / `set vfdTheme`, the 4×4 `kNixieThemes`/`kVfdThemes` tables | `cmdSet.cpp:676-698`, `clockApp.cpp:12-13`, `:346-368`, `clockApp.h:257-259` | **none** — 8 themes, 0 ids |
| `set fmt24h` / `set dateFmt` (WIRE2-G2/G3) driving `_drawDigital`/`_drawDate`/`clockHour`/`clockAmPm` | `cmdSet.cpp:626-657`, `clockApp.cpp:163-218` | **no clock id** |
| Power-cycle persistence of any clock setting | — | **none** — no clock id reboots, although `m-clock-styles.md:50` books C3 ("app switch **+ power cycle**") as PASS |
| Any rendered fact: digit position, colour, segment state, flip frame count, tick interval | `clockApp.cpp:89-454` (330 lines) | **none** — five exit criteria (C1, C4, C5, C6, C8) are visual and four of them are recorded PASS against non-visual proxies (**H-2**) |

### 5.2 Teletext — three ids against a 596-line app

| Surface | Firmware | Registry coverage |
|---|---|---|
| `set teletextPageContent` — the synthetic 25×40 grid injector, built precisely so render tests need no network | `teletextApp.cpp:253-275` | **no reader anywhere in `app/tools/`** |
| `set teletextPage` — the page-navigate path incl. the 100..899 range guard | `teletextApp.cpp:220-228` | **no registry reader** (`test_fetch_stress.py` reads `get teletextPage` only) |
| `get teletextPage`, `teletextPollSecs`, `teletextHasSubpages`, `teletextBackend` | `teletextApp.cpp:176-215` | **no reader anywhere** — 4 of the app's 7 `dbgGet` keys |
| Numpad: `_numpadActive`, `_handleNumpad`, `_drawNumpad`, the PAGE-toggle dismiss path | `teletextApp.cpp:151-158`, `:302-306` | **none** — `T271` toggles it on as a side effect and never exercises it |
| Fast-text bar: `_handleBar`, `BAR_FTL0..3`, `_st.ftlTargets` | `teletextApp.cpp:338-346` | **none** |
| Grid hit-test `_handleGrid` (in-page link taps) | `teletextApp.cpp:163-165` | **none** |
| History ring: `_histDepth`, `_history`, `_goBack()` | `teletextApp.cpp:289-293`, `:307-317` | **none** — `T271` taps BACK twice with `_histDepth == 0`, so `_goBack()` never runs; the plan's own precondition (*"History ring non-empty"*, `test_plan.md:4471`) is not established by the body |
| SUBUP zone and 3 of the 5 strip boundaries (33/34, 132/133, 165/166) | `teletext_layout.h:29-40` | **none** — `T271` covers 66/67 and 99/100 only |
| Error latch `_ttErr` → `hasError()` → the ADR-046 red indicator for Teletext | `teletextApp.cpp:88-91` | **none** — the PlaneRadar plan text cites "T-ERR-01/04/06/07" as the shared proof, and none of those is a Teletext id |
| Any rendered fact: glyph grid, colour attributes, strip icons, the numpad overlay | `teletextApp.cpp:400-596` | **none**, and `run/screendump` exists |
| The `run/check-teletext-api` upstream canary | `run/check-teletext-api` | not wired to any id; `T272` is the only id whose failure the canary would explain, and it does not consult it |

### 5.3 PlaneRadar — the richest debug surface, and the two biggest holes are outside the registry

| Surface | Firmware | Registry coverage |
|---|---|---|
| `set prForceParseFail` / `get prForceParseFail` — the deterministic fetch-failure injector (TASK-361) | `planeRadarApp.cpp:182-186`, `:242-245`; `dataTaskStorage.cpp:1305-1317`, `:2020-2030` | **no reader in `app/tools/` or `run/`** — while `T_PR_05`, the id it would fix, is a permanent SKIP (**H-5**) |
| `get prLastAction` — the outcome of every disc/strip tap | `planeRadarApp.cpp:187-190` | **no registry reader**; `prloc_ve_smoke.py` only |
| Location slots: `_setActiveLoc()`, `prActiveLoc`, `PR_NUM_LOCS`, `_drawLocSlots()`, the `_locEpoch` stale-result discard (VE-PRL-6) | `planeRadarApp.cpp:139-166`, `:44-52` | **no registry id at all** — M-PR-LOCATIONS coverage lives entirely in `prloc_smoke.py`, `prloc_ve_smoke.py`, `prloc_manual_smoke.py` and `prloc_editor_smoke.py`, four standalone harnesses with no ids, all four of which open the serial port at import time (WP-A **A-12**) |
| `_radiusCapActive` / `_radiusCapNm` — TASK-378 horizon shading and TASK-361's radius-capped retry2 | `planeRadarApp.cpp:63-68` | **none** |
| Runway/airport overlay (ADR-049, `run/bake-airports`) | `_redrawGridStatics()`, `planeRadarApp.h:542` | **none** |
| Exit criterion 4 — the 30-min Spotify coexistence soak | — | out of registry by design (`test_planeradar_soak.py`, and `test_plan.md:4740` says so) |
| Any rendered fact: `_render()`, `_erasePrev()`, `_updateStripDynamic()`, the disc, the aircraft glyphs | `planeRadarApp.cpp:380-600` | **none** — the two ids whose criteria say "render" (`T_PR_02` criterion 1, `T_PR_06` criterion 6) both resolve to a struct counter |

**The pattern across all three.** Every one of these apps has a *drawing*
subject and a *struct* debug surface, and in every case the automatable half was
built and the visual half was booked to a proxy or to a human. That is WP-G's
closing sentence — *a test whose subject is on the screen and whose oracle is in
a struct* — reproduced in three more apps, and here it is sharper because
`run/screendump` has existed since the WebRadio work and none of these families
uses it.

---

## 6. Family findings

### 6.1 The test is counted as coverage and provides none — P1

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **H-1** | **P1** | **The third armed-and-never-cleared injector — `set prInjectAircraft` leaves `_injected` true for the rest of the boot, and `T_PRI_01` never clears it.** `_injected` guards every real-fetch site in the app (`resume()`'s entry enqueue, `tick()`'s poll enqueue and result drain, the range-tap re-enqueue, `_setActiveLoc()`'s), and is cleared by exactly two things: `set prClearInject 1` and `init()`. `resume()` does **not** clear it, and `switchApp` runs `resume()` on every entry after the first, so an app switch cannot recover it — only a reboot can. `T_PRI_01` (index 25, the last id in the family) clears at the *start*, injects twice, and its teardown is `set prRange 10` + `_restore_spotify` with no `prClearInject`; its two siblings `T_PR_03` and `T_PR_06` both clear. Third instance of the pattern after WP-F **F-4** (`C9`) and WP-G **G-1** (`C10`). **Blast radius is smaller than either, and only by accident of registry order:** no later registry id enters PlaneRadar, so no verdict changes — but the app is left frozen on one synthetic aircraft, not fetching, for the remaining 187 ids until `T_PLR_26`'s reboot at index ~111, and `test_planeradar_soak.py` reads `prAircraftCount` without comparing it. | `planeRadarApp.cpp:279`, `:305-307`, `:268-272`, `:8`, `:27`, `:33`, `:37`, `:135`, `:164`; `appShell.cpp:200-207`; `planeradar.py:440`, `:442`, `:453`, `:480-481`, `:117`, `:249`; `player.py:1610`; `test_planeradar_soak.py:88-98`; §4.1 | Suite: add `dut.cmd("set prClearInject 1")` beside the `set prRange 10` at `planeradar.py:480` — one line, and the idiom two ids up. Firmware, better: clear `_injected` in `PlaneRadarApp::resume()`; an injection is a within-visit instrument and no test wants it to survive an app switch. Then add cluster **`C11`** to WP-B §5.2 and the first `_order.py` entries this corpus has ever had. |
| **H-2** | **P1** | **Five M-CLOCK-STYLES exit criteria are recorded PASS against oracles that cannot observe them — a clock face rendering as a black rectangle passes the entire 14-id family.** `regression_suite/m-clock-styles.md:46-55` books **C4** (flip animation ≤500 ms, no pixel residue) to `T_CLK_13` *"responsiveness proxy"*, **C5** (Nixie tubes within y:5..85) to `T_CLK_04` *"DUT accepts, no crash"*, **C6** (VFD segment visibility) to `T_CLK_05` same, **C7** (non-Flip 1000 ms tick gate) to `T_CLK_11` *"no heap anomaly"*, and **C8** (Spotify→Clock→Spotify no pixel residue) to `T_CLK_12` *"app stable"*. Not one of the five oracles reads a pixel, a coordinate, a colour or a frame interval; four of the five read `g_settings.clockStyle` back through the command that wrote it. **C3** ("persists across app switch **+ power cycle**") is booked to `T_CLK_08`/`T_CLK_09`, neither of which power-cycles. The M-CLOCK-STYLES milestone is therefore recorded as 14/14 PASS on evidence that would survive the complete removal of all four face renderers. | `regression_suite/m-clock-styles.md:5`, `:37-40`, `:46-55`; `clock.py:73-79`, `:89-95`, `:179-189`, `:199-204`, `:213-222`; `clockApp.cpp:89-454`; `cmdGet.cpp:536-548` | Re-open C1/C4/C5/C6/C8 as **DEFERRED** in `m-clock-styles.md` (the file already marks C1 that way — the other four should never have been PASS), and automate them with `run/screendump`, which four WebRadio ids already use for exactly this class of claim (`webradio.py:1398-1428`). C7 needs one firmware field (a frame or `_lastTickMs` counter on `get clockStyle`); C3 needs one `reboot`, the idiom `T_PR_04` and `T_PRM_01` already use twenty ids later. |
| **H-3** | **P1** | **Five Clock ids assert only values the harness itself wrote or the firmware hardcodes.** `T_CLK_02` claims *"defaults to digital after a fresh settings load"* and force-writes digital first, by its own comment. `T_CLK_08` claims settings.json persistence and reads a RAM member back through the command that wrote it, with no reboot, no `dirty` read and no `settingsSaveCount` read — while the adjacent `set fmt24h` already reports `SettingsStorage::save()`'s return as `"saved"` and `set clockStyle` throws it away. `T_CLK_09` claims an app switch preserves the style, and no app-switch code path writes `g_settings.clockStyle`. `T_CLK_13` claims the 30 ms/1000 ms Flip tick gate and asserts a style readback plus an unchangeable `appId`. `T_CLK_14` asserts three fields of which `last` is a compile-time string literal in the printf. That is **5 of 14 HOLLOW — 36 %, the highest HOLLOW rate of any family in this review** (WP-G's was 13 %). | `clock.py:44-47`, `:138-141`, `:151-156`, `:213-222`, `:232-239`; `cmdSet.cpp:634-638` vs `:669-674`; `cmdGet.cpp:538`, `:545`; `clockApp.h:44-45`; `appShell.cpp:200-207` | `T_CLK_08`: reboot and read back, or read `dirty` + `settingsSaveCount`; and have `set clockStyle` report `saved` the way `set fmt24h` does. `T_CLK_02`: reboot with a wiped `settings.json`, or retire — the default cannot be tested without a load. `T_CLK_09`: retire, or re-point at a value an app switch *can* change. `T_CLK_13`: needs a firmware observable (frame count / `_lastTickMs`) or it is untestable as written. `T_CLK_14`: subsumed by `test_task488_partb.py:177`; retire. |
| **H-4** | **P1** | **Thirteen of the fourteen Clock ids enter the app through an ack that echoes the harness's own argument, and none of them checks it.** `_switch_to_clock` returns `True` on `r.get("ok")`, and `cmdSwitchApp` prints `{"ok":true,"cmd":"switchApp","id":%d}` where `%d` is **the id the host sent**, not `currentAppId`. Only `T_CLK_01` ever issues `get appId`. So if `switchApp` stopped switching, thirteen ids would still enter their bodies — and because all thirteen then assert `g_settings.clockStyle`, a **global** readable from any app, all thirteen would still pass. The family's slots are hardcoded (`switchApp 1`/`0`/`4`) and `app_ids_gen` is never imported, although `teletext.py:9` and `_helpers.py:16` both do; the numbers are correct today (`APP_ORDER` gives Clock=1, Spotify=0, Matrix=4), so WP-A **A-8**/**D1**'s stronger reading is **refuted as a live defect and confirmed as a latent one**. `console.cpp:91`'s help string is already stale on the same fact (`"<appId 0..8>"` vs `APP_COUNT = 13`). | `clock.py:10-15`, `:20`, `:152-153`; `cmdMisc.cpp:20-28`; `cmdGet.cpp:225-236`; `app_ids_gen.py:4`; `_helpers.py:321-331`; `console.cpp:91` | Replace `_switch_to_clock` with `_helpers._switch_to(dut, "Clock")` — it taps the real taskbar slot, derives the slot from `APP_SLOT`, and asserts `get appId.name`. One import, one call site, and it converts the family's entry from unverified to verified *and* from serial-only to the production path. |

### 6.2 Oracles narrower than the claim — P2

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **H-5** | **P2** | **`T_PR_05` is a permanent SKIP waiting on a live rate limit, while a deterministic injector for exactly its subject has existed since TASK-361 and no test in the repo uses it.** `set prForceParseFail n` forces the next *n* fetch attempts to return `ok=false, errorCode=-92` without touching the network, which sets `_prErr` — the `activeError.active` latch `T_PR_05` hammers `triggerPlaneRadarFetch` twenty times hoping to provoke. `grep -rn prForceParseFail app/tools/ run/` returns **nothing**. Both the body's docstring and the plan row still assert *"No dedicated fault-injection hook exists for PlaneRadar yet"* — true when written, false since TASK-361. `test_plan.md:4727` records the id SKIP since 2026-07-11 and `flaky.yaml:157` carries it as an unmeasured candidate. | `planeradar.py:159-160`, `:188-209`; `planeRadarApp.cpp:242-245`, `:72-73`, `:182-186`; `dataTaskStorage.cpp:1305-1317`, `:2020-2030`; `test_plan.md:4724-4728`; `flaky.yaml:157` | Replace the 20-attempt hammer with `set prForceParseFail 3` + `set triggerPlaneRadarFetch 1`, keep the responsive and recovery legs unchanged, and delete the flake candidacy. Correct both docstrings. |
| **H-6** | **P2** | **`T_PR_02`'s oracle is a boot-scoped latch its own predecessor consumes.** `isConnecting()` is `!_everHadResult`, set true by the first successful poll *or* by any injection, and reset only by `init()` and `_setActiveLoc()`. `T_PR_01` at index 17 is PlaneRadar's first entry, so `init()` runs there; by `T_PR_02` at 18, `resume()`'s enqueue plus the drain of a result already queued can satisfy `connecting == false` within one tick, and on any third-or-later entry the term is pre-satisfied outright. What the id proves is "a PlaneRadar fetch has resolved since boot", not "within one poll of app entry". The render half of exit criterion 1 has no oracle at all — `prAircraftCount` is read and only interpolated into the pass string, and the plan explicitly allows `0` to pass. The same latch is the baseline gate in `T_PR_05:180` and `T_PRM_02:349`. | `planeRadarApp.h:244`, `:278`; `planeRadarApp.cpp:6`, `:60`, `:153`, `:306`; `planeradar.py:69-89`, `:78`, `:88-89`; `test_plan.md:4701` | Snapshot `prAircraftCount`/`prLastHttp` before the switch and assert a change, or add a per-entry `_lastGoodMs`-based observable; and record the latch as an `_order.py` VACUITY edge for `T_PR_02` behind `T_PR_01`. |
| **H-7** | **P2** | **`T_PR_06` asserts one of the three things it claims, and the criterion it serves says "render".** The docstring promises `prAircraftCount == 3`, `prLastHttp` unchanged (no fetch attempted), and count back to 0 after `prClearInject`. Only the first is compared: `r_after` is read and appears **only in the pass string**, so the clear half of exit criterion 6 is unasserted, and `prLastHttp` is never read at all. The one assertion is a round trip through `_result.count`, written by the same command. | `planeradar.py:234-238`, `:247-257`; `planeRadarApp.cpp:168-170`, `:274-307`; `test_plan.md:4732-4735` | Two `if` statements: assert `r_after.get("val") == 0` and assert `prLastHttp` is unchanged across the injection. Both values are already read. |
| **H-8** | **P2** | **The tap reply's `"skipped"` flag is discarded at every tap site in this corpus, and one of `T271`'s four boundary steps is a residue pass because of it.** `cmdTap`'s busy gate returns `{"…","action":"NONE","skipped":true}` without dispatching to the app, leaving `_lastAction` at its previous value. `T271` taps y=67 expecting `STRIP_BACK` and then y=99 **expecting `STRIP_BACK` again** — so a step-2 tap swallowed by the busy gate or the 300 ms debounce passes on step 1's residue. `T270` has the same exposure on a repeat SUBDN. Neither reads `skipped`; neither reads `_wait_shell_not_busy`'s return either (`T270:110`, `:148`; `T271:185`, `:197`). | `cmdTouch.cpp:47-51`, `:70-77`; `teletext.py:185-194`, `:197-207`, `:132-139`; `teletextApp.cpp:139-144` | Assert `r.get("skipped") is False` on every `tap` in the corpus (the field is already in the reply), and check `_wait_shell_not_busy`'s return. Reorder `T271`'s BACK pair so no two consecutive steps expect the same action. |
| **H-9** | **P2** | **`set cooldown 0` is the wrong variable in all three Teletext call sites.** It resolves to `WinampDisplay::dbgSet("cooldown")`, which zeroes `touchScreenCoolDownTime` — the TASK-052 **Spotify** dead-zone force-poll timer. The gate that actually applies to a Teletext tap is `TeletextApp::handleInput`'s own 300 ms `_lastTapMs` debounce; the shell's post-gesture `cooldownMs` is a third thing again, set only on a taskbar drag release and read as `get shellCooldown`. `cmdGet.cpp:469-470` documents the name collision explicitly. The three calls are inert; `T271`'s `time.sleep(0.35)` is what really clears the debounce, and `T270`'s comment justifying its own timing is wrong on the same subject (*"resume() set it to 0"* — `resume()`→`_activateSource()` does not touch `_lastTapMs`; only `init()` does). | `teletext.py:111`, `:128-129`, `:187`, `:199`; `winampDisplay.cpp:776-782`; `cmdGet.cpp:462-474`; `console.cpp:135`; `teletextApp.cpp:102`, `:110-121`, `:139-144` | Drop the three `set cooldown 0` calls or replace them with `dut.wait_shell_cooldown_clear()` (`lib/dut.py:1138-1150`), which polls the variable that exists; correct the `T270` comment. |
| **H-10** | **P2** | **The corpus writes `settings.json` roughly fifty times per suite run and restores the user's values by luck.** `set clockStyle` calls `SettingsStorage::save()` unconditionally on every call (~40 calls across the 14 clock ids: `T_CLK_06` 5, `T_CLK_11` 9, `T_CLK_12` 4, one per teardown), and `_setPreset()` does the same for every range change (`T_PR_03` alone makes 5). `T_CLK_12` is the one body that omits its teardown, leaving `clockStyle = vfd` persisted — recovered only because `T_CLK_13`/`T_CLK_14` behind it happen to write digital; `T_PR_04` leaves `prRange = 25` persisted, recovered only because `T_PRI_01` four ids later sets 10 as its own setup. Unlike WP-B **B-5**'s `stockMode`, which `dbgSet` writes in RAM only, these are real flash writes: the user's clock face and radar range are overwritten by every suite run, and the *restore* is a side effect of another test rather than a teardown. | `cmdSet.cpp:669-671`; `planeRadarApp.cpp:347-350`; `clock.py:18`, `:105-113`, `:181-184`, `:199-201`; `planeradar.py:106-117`, `:135`, `:480` | Snapshot `get clockStyle`/`get prRange` on family entry and restore in a `finally`, the `_bgpoll_suspended` pattern (`_helpers.py:445-454`) and the one `T_PRM_01` already follows on every exit path. Give `T_CLK_12` the teardown every sibling has. |
| **H-11** | **P2** | **`T_CLK_03`, `T_CLK_04` and `T_CLK_05` are a strict subset of `T_CLK_06`.** All four assert the same thing — that `set clockStyle <name>` reaches `g_settings.clockStyle` and `get clockStyle` names it back — and `T_CLK_06` covers all four styles *and* the numeric-parse branch the other three do not touch. Three registry ids, three minutes of DUT time and three plan rows for an assertion that is already made. This is the package's clearest S13 instance and the only one worth acting on. | `clock.py:51-65`, `:67-81`, `:83-97`, `:99-115`; `cmdSet.cpp:659-674` | Retire `T_CLK_03`/`04`/`05`, or re-point each at the *face* it names once a pixel oracle exists (**H-2**) — which is what their exit-criteria rows already claim they do. |
| **H-12** | **P2** | **`app/gen/teletext_layout.h` is a generated header the suite mirrors by hand, and both files that would parse it import the parser and never use it.** `TTXT_STRIP_X = 240`, `PAGE_Y1 = 66`, `BACK_Y0/Y1 = 67/99`, `PREV_Y0 = 100`, `SUBDN_Y0/Y1 = 166/199` are generated; `teletext.py` hardcodes `257`, `182`, `66`, `67`, `99`, `100`. `coords.py` already parses two other generated headers with a generic `#define` regex and does not parse this one; `teletext.py:8` and `planeradar.py:8` both `import coords as _c` and neither uses it (`grep -n "_c\." ` → no hits in either). Same shape on the PlaneRadar side: `PR_CX, PR_CY = 120, 120` mirrors `planeRadarApp.h:22`, the preset list mirrors `planeRadarConfig.h:13`, `PR_POLL_MIN/MAX_SEC` are mirrored as `1`/`30`, and `PR_FETCH_TYPE = 8` mirrors `dataTask.h:20` with a "keep in sync" comment and no gate. LL-114, and WP-A **A-9**'s instance in this corpus. | `app/gen/teletext_layout.h:25-40`; `coords.py:9-23`; `teletext.py:8`, `:132`, `:177-182`; `planeradar.py:8`, `:28`, `:119`, `:269`; `planeRadarApp.h:22`, `:157`; `planeRadarConfig.h:13`; `dataTask.h:20` | Add `teletext_layout.h` and `planeRadarConfig.h` to `coords.py`'s `_parse` list (three lines each, the mechanism exists) and derive the six teletext y-values and the preset table from them; then either use `_c` in both files or drop the unused import. |

### 6.3 Records, messages and hygiene — P3

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **H-13** | **P3** | **All three Teletext plan rows are stale, and one specifies markers the firmware has never emitted.** `### T271`'s Steps expect `KEYPAD_OPEN`, `BACK`, `BACK`, `PREV_PAGE`; the firmware emits `STRIP_PAGE`/`STRIP_BACK`/`STRIP_PREV` and `grep -rn KEYPAD_OPEN app/src/` returns nothing. `### T270` is headed *"Subpage ▲/▼ zones"*, tagged `[NETWORK] [Blocked: G1, G2]`, and specifies `tap 257 16` (SUBUP) asserting `teletextSubpage != S0`; the body taps SUBDN at `257 182`, asserts `teletextLastAction` + `shellBusy`, and needs no network. Both rows still read **Status: planned** for ids that have been dispatched by `run/test` since TASK-197. | `test_plan.md:4459-4480`; `teletextApp.cpp:297-330`; `teletext.py:114-149`, `:175-207` | Rewrite both Steps blocks from the bodies and drop the `[Blocked]`/`planned` markers; second instance of WP-G **G-12**. |
| **H-14** | **P3** | **The Clock family's only plan-of-record is a `regression_suite` report whose exit-criteria mapping is wrong.** Seventeen of the 26 ids have no `### ` entry in `test_plan.md` (all 14 `T_CLK_*`, plus `T_PRM_01`/`T_PRM_02`/`T_PRI_01`). The three PlaneRadar ones are **correctly on the ledger** as accepted orphans (`id_binding_exceptions.md:65-67`, TASK-355/357). The 14 clock ids bind instead through `m-clock-styles.md:15-28`'s inventory table — which is the same document that carries **H-2**'s five wrong criterion mappings, so the family's only authored description of what its tests cover is also the document that overstates it. | `grep -n "^### T_CLK_" test_plan.md` → none; `id_binding_exceptions.md:65-67`; `m-clock-styles.md:11-55` | Either write the 14 plan rows or make `m-clock-styles.md` accurate; the second is cheaper and is **H-2**'s fix anyway. |
| **H-15** | **P3** | **`_order.py` has no entry for any of the 26 ids, although they are indices 0–25 and therefore precede all 187 others.** No ORDER-SENSITIVE, no VACUITY and no adjudication row mentions `T_CLK_*`, `T27x`, `T_PR_*`, `T_PRM_*` or `T_PRI_*`. The three real dependencies this audit found — `T_PRI_01`'s `_injected` leak (**H-1**), `T_PR_02`'s latch behind `T_PR_01` (**H-6**), and the clock/range settings leaks (**H-10**) — are all invisible to the TASK-566 edge enumeration for the same reason WP-B's three hidden clusters were. | `grep -n "T_CLK\|T27\|T_PR" _order.py` → no hits; §0's index listing | Three `EDGE_ADJUDICATION` rows: `T_PRI_01`→everything (LEAK, `C11`), `T_PR_02` behind `T_PR_01` (VACUITY), `T_CLK_12` (LEAK, persisted). |
| **H-16** | **P3** | **`T_PRM_02` is the most flake-exposed id in the corpus and is not in `flaky.yaml`; `T_PR_05` is, with an accurate note.** `T_PRM_02` holds a 300 s live-network observation window at index 24, fails on five separate bounds including a median derived from one 2026-07 measurement, and carries no declaration or candidacy. `T_PR_05`'s candidacy note — *"annotated [NETWORK]-flaky in the suite itself"* — is accurate, unlike the `T169` note WP-G corrected; it should be **retired rather than measured**, because **H-5** makes the id deterministic. | `flaky.yaml:150-160`; `planeradar.py:312-406`, `:155-230` | Add `T_PRM_02` as a candidate with the real failure mode (upstream pacing drift moving the median outside [3 s, 9 s]); delete `T_PR_05`'s once **H-5** lands. |
| **H-17** | **P3** | **Three suite bodies reach into `Dut._wait_for_ready()`, a private.** `planeradar.py:142`, `:303` and `player.py:1610` call it directly after `dut.send("reboot")`. It is the only reboot-settle primitive there is, and it is not part of `Dut`'s public surface — so the one operation that makes a persistence test possible is reached by convention. | `planeradar.py:142`, `:303`; `player.py:1610`; `lib/dut.py:606-620` | Promote it: `Dut.reboot_and_wait()` wrapping `send("reboot")` + settle, and have the three call sites use it. WP-A **A-1**'s shared-layer question, one method wide. |
| **H-18** | **P3** | **Uncited thresholds throughout, in a corpus that otherwise cites well.** `4096` (`T_CLK_11`'s leak bound, on a code path that allocates nothing), `30.0`/`10.0` (`T272`), `8.0`/`0.35`/`0.1` (`T270`/`T271`), `12.0`/`20`/`30.0` (`T_PR_05`), `0.3`/`0.6`/`0.3` (`T_PRI_01`'s decay bounds — only `39.0` is tied to `PR_INTERP_SNAP_PX`, and only in prose). The contrast is instructive: `T_PR_02`'s `90.0` and `T_PRM_02`'s five bounds all carry a derivation in the docstring, and they are the two best-graded network ids in the package. | `clock.py:188`; `teletext.py:44`, `:73`, `:110`, `:186`; `planeradar.py:192`, `:190`, `:218`, `:460`, `:483`, `:487`; vs `planeradar.py:57-63`, `:334-337` | Tie the two that have constants (`PR_INTERP_SNAP_PX`, `PR_INTERP_TAU_MS`) to parsed values under **H-12**, and give the rest a one-line derivation or a dated measurement. |
| **H-19** | **P3** | **`console.cpp`'s `switchApp` help string is stale.** `"<appId 0..8>"` against `APP_COUNT = 13`. Cosmetic, but it is the same mirror-drift class as **H-4** and it is in the firmware, where a reader would trust it. | `console.cpp:91`; `app_ids_gen.py:4-8` | Derive the range from `AppId::COUNT` in the help string, or state it as `0..COUNT-1`. |

---

## 7. Counts

### 7.1 Verdicts

| Verdict | Clock (14) | Teletext (3) | PlaneRadar (9) | **Combined (26)** |
|---|---|---|---|---|
| SOUND | 1 | 2 | 6 | **9** |
| WEAK | 8 | 1 | 3 | **12** |
| HOLLOW | 5 | 0 | 0 | **5** |
| BROKEN | 0 | 0 | 0 | **0** |
| **total** | **14** | **3** | **9** | **26** |

* **SOUND (9):** `T_CLK_01`; `T272`, `T270`; `T_PR_01`, `T_PR_03`, `T_PR_04`,
  `T_PRM_01`, `T_PRM_02`, `T_PRI_01`.
* **WEAK (12):** `T_CLK_03`, `T_CLK_04`, `T_CLK_05`, `T_CLK_06`, `T_CLK_07`,
  `T_CLK_10`, `T_CLK_11`, `T_CLK_12`; `T271`; `T_PR_02`, `T_PR_05`, `T_PR_06`.
* **HOLLOW (5):** `T_CLK_02`, `T_CLK_08`, `T_CLK_09`, `T_CLK_13`, `T_CLK_14` —
  **all five in one family**.
* **BROKEN (0).**

**35 % SOUND combined — the worst per-test result in the review**, below WP-G's
40 %, WP-F's 50 %, WP-D's 56 %, WP-C's 59 % and WP-E's 77 %. But the combined
number is the least interesting one in the table, because the spread inside it
is 6×:

| Family | SOUND | Observables it was given |
|---|---|---|
| PlaneRadar | **6/9 = 67 %** | 7 `dbgGet` keys designed against the tests (`activeError`'s `active`/`connecting` split, `prInterp`'s *recomputed* decayed offset, `dataq`'s `inFlightMs` fetch identity), 2 injectors, 1 fault injector |
| Teletext | **2/3 = 67 %** | 7 `dbgGet` keys, an unconditional `_lastAction` zone observable, a content injector |
| Clock | **1/14 = 7 %** | one settings round trip, and an input observable no id reads |

That is WP-E's finding — *the quality of a test tracks the quality of the
observable it was given* — restated as a controlled experiment, because all
three families were written by the same VE against the same harness and differ
mainly in what the firmware offered them.

**Zero BROKEN is real and worth stating.** This is the first family package with
none: no inverted guard, no unreachable `fail()`, no `_check_residue` caller
making WP-D **D-2**'s wrong choice, no dead log marker, no `get` key that does
not exist (§4.4), and — with one exception, `T_PR_05`'s external-precondition
skip — no `skip()` standing where a `fail()` belongs. The corpus's problem is
not that its tests break. It is that five of them cannot fail, and that the
milestone report for the family they are in records their passes against five
criteria they cannot see.

### 7.2 Smell histogram

77 occurrences across the 26 rows (a row may carry several).

| Code | Smell | Count |
|---|---|---|
| S3 | Tautology | **14** |
| S2 | Ack-not-effect | 9 |
| S13 | Overlap | 9 |
| S14 | State leakage | 9 |
| S10 | Magic value | 8 |
| S8 | Vacuous bound | 7 |
| S11 | Double bookkeeping | 7 |
| S6 | Defaulting oracle | 5 |
| S4 | Deferred to a human | 3 |
| S7 | Skip-as-pass | 3 |
| S12 | Wrong-id / mis-scoped record | 2 |
| S9 | Fixed-sleep synchronisation | 1 |
| S1 | Unconditional pass | 0 |
| S5 | Swallowed failure | 0 |

Four things in that distribution belong to this corpus rather than to the
sample.

* **S3 is the top code for the first time in the review, at 14 of 77**, and ten
  of the fourteen are in `clock.py`. WP-F's tautologies were `set X`/`get X` on
  one state byte; WP-G's were a value written through a *second* command; this
  family's are the simplest form of all — one settings member, one command to
  write it, one to read it, and a claim about rendering or persistence wrapped
  around the pair.
* **S7 is 3, against WP-D's 23 and WP-G's 16 — the lowest in the review by a
  wide margin.** These families fail rather than skip. Of the three, `T272`'s and
  `T_PR_04`'s are honest environment preconditions and only `T_PR_05`'s is the
  test's whole subject — and **H-5** shows it does not have to be.
* **S5 is zero and S1 is zero.** No `except: pass`, no helper returning `True`
  on ambiguity, no body reaching `pass_()` without a comparison. Every non-SOUND
  verdict here is earned by a *weak* comparison, not by a missing one — a
  materially different failure mode from every prior package.
* **S6 is 5, and its direction is mixed rather than uniformly bad.** The two
  unsafe ones are `T_CLK_11`'s `r.get("heap", 0)` (both ends default to the same
  value, so a dead getter reads as leak=0) and `T_PRM_02`'s
  `q.get("queueWaiting", 0)`/`spActMs` guard (a renamed field silently satisfies
  two of five bounds). Against that, `T272`'s `http_code` default routes to
  `fail` and **`T_PRI_01`'s three defaults all fail on a missing field** — the
  only body in the review so far that gets every default right, and its
  docstring records the DUT session that taught it (`planeradar.py:466-473`).

---

## 8. NEEDS-DUT

Static reading cannot settle these. Each is stated as the question hardware
would answer, with the prediction that would confirm or refute it.

1. **H-1 — does `_injected` actually survive to the end of the run?** After a
   full `run/test`, and *before* any reboot, issue
   `get prAircraftCount` / `get prLastHttp` with PlaneRadar foregrounded.
   **Prediction:** `prAircraftCount == 1`, the callsign on screen is `AAA111`,
   `prLastHttp == 0`, and the count never changes however long you wait —
   because `tick()`'s enqueue and drain are both behind `!_injected`. Confirm
   the clear works by then issuing `set prClearInject 1` and watching the count
   move within one poll interval.
2. **H-1 (b) — the isolated/in-suite split.** `./run/test-targeted T_PRI_01`
   from a cold boot, then `get prAircraftCount` twice 15 s apart; repeat with
   `T_PR_06,T_PRI_01`. **Prediction:** identical in both — this leak, unlike
   `C9`/`C10`, is not order-dependent, it is unconditional. That is worth
   confirming precisely because it means no rerun pattern would ever have
   surfaced it.
3. **H-2 — is any of the five booked criteria actually met?** One
   `run/screendump` per style with the clock foregrounded (four dumps).
   **Prediction (open):** the point is not that the faces are broken — they
   almost certainly render correctly — but that the four images are the
   evidence C4/C5/C6/C8 were recorded PASS without, and they take four commands
   to obtain. If a face *is* wrong, the whole 14-id family is currently green.
4. **H-6 — is `T_PR_02` vacuous in the current order?** Log
   `get activeError.connecting` immediately on entry to `T_PR_02`, before the
   poll loop starts, in a full run. **Prediction:** already `false` on some or
   most runs, because `T_PR_01`'s `init()`-driven fetch resolved on `T_PR_02`'s
   own first tick. If it is always `true`, the latch is being consumed by
   `T_PR_02` itself and the finding drops to P3.
5. **H-5 — does `set prForceParseFail 3` drive `activeError.active`?**
   `switchApp` PlaneRadar → `set prForceParseFail 3` →
   `set triggerPlaneRadarFetch 1` → poll `get activeError`.
   **Prediction:** `active` goes true within one fetch cycle (~5 s) and clears
   on the next unforced poll — i.e. `T_PR_05`'s entire subject, deterministic,
   in two commands. If it does, **H-5**'s fix is mechanical.
6. **H-8 — how often is a tap actually swallowed?** Capture the raw `tap`
   replies for `T270` and `T271` in a full run and count `"skipped":true`.
   **Prediction (open):** if any of `T271`'s four steps is ever skipped, step 2
   passed on residue and the boundary it claims to cover was not tested that
   run.
7. **H-10 — what does the suite leave in `settings.json`?**
   `./run/spiffs pull settings.json` before and after a full `run/test`.
   **Prediction:** `clockStyle` and `prRangeIdx` differ from the pre-run values
   (and `stockMode`, per WP-G **G-4**, if any save fired). Confirms the leak is
   user-visible rather than RAM-only.
8. **`T_CLK_11`'s bound.** Extract `h0`/`h1` from one run.
   **Prediction (open):** the delta is a few hundred bytes or zero — the
   `m-clock-styles.md:34` note already records `leak=0 B` from 2026-06-13 — in
   which case `4096` was never a threshold and the id is a `get info` liveness
   check with arithmetic attached.

---

## 9. Handover

* **Findings that belong to WP-Z's consolidation rather than to this family:**
  **H-1** (the third armed injector — a new state-leakage cluster `C11` for
  WP-B §5.2, completing the `C9`/`C10`/`C11` set the brief predicted, and the
  first of the three whose fix is one line in the suite *and* one line in the
  firmware); **H-2** (a milestone report recording five visual exit criteria
  PASS against non-visual oracles — this is a *documentation* defect with a
  coverage consequence, and WP-Z should decide whether other
  `regression_suite/*.md` reports carry the same); **H-4** (the entry-path
  finding that closes WP-A **A-8**/**D1** in both directions); **H-5** (a
  firmware VE hook with no consumer anywhere in the repo, mirroring WP-G
  **G-3**'s debug-surface gap from the opposite side — there the suite needed a
  getter that did not exist, here a hook exists and the suite that needs it does
  not know); **H-12** (a *generated* header mirrored by hand, with the parser
  imported and unused in both files — LL-114's sharpest instance so far).
* **Cross-references, cited not re-derived:** **H-1** is WP-F **F-4** / WP-G
  **G-1**'s pattern, third instance; **H-4** adjudicates WP-A **A-8**/**D1**
  (refuted as a live defect, confirmed as latent — the slot literals are correct
  today); **H-12** is WP-A **A-9**'s instance here; **H-13** is WP-G **G-12**,
  second instance; **H-15** is WP-B's hidden-cluster problem in a corpus
  `_order.py` does not mention at all; §4.4's key-and-marker sweep is WP-G
  **G-3**'s method applied and returning clean.
* **The corpus was re-measured at 26 ids and the index's §3 row was already
  correct** — the first family row in this review that needed no correction.
  Registry indices 0–25 of 213.
* **On the brief's three specific questions.** (i) `clock.py`'s hardcoded slots:
  confirmed as a mirror, **refuted** as a live defect — but the deeper half of
  A-8/D1 is worse than reported, because `_switch_to_clock` verifies nothing
  *and* every clock oracle is a global readable from any app, so a broken
  `switchApp` would not fail a single clock id (**H-4**). (ii) The style tests:
  a face rendering as a black rectangle fails **nothing** — not one of the 14,
  and not one of the eight M-CLOCK-STYLES exit criteria, five of which are
  recorded PASS against proxies (**H-2**). (iii) `T_CLK_12` does indeed omit the
  restore (`clock.py:193-205`), leaving `clockStyle = vfd` **persisted to
  settings.json**, recovered only by its two successors (**H-10**).
* **The structural contrast for the running series.** WP-C: *a failure that does
  not block.* WP-D: *a test that does not run.* WP-E: *a test that leaves the
  board changed.* WP-F: *a test that measures a proxy and a harness that leaves
  the proxy armed.* WP-G: *a test whose subject is on the screen and whose
  oracle is in a struct.* WP-H: **a test that cannot fail, and a milestone
  report that counts it anyway** — five HOLLOW ids in one family, zero BROKEN in
  all three, and an exit-criteria table booking pixel claims to a settings round
  trip. The corollary is the package's most useful result: the two families in
  the same package whose firmware was designed with the tests in mind score
  67 % SOUND against Clock's 7 %, on the same harness and the same author.
* Nothing under `app/` or `run/` was modified. Nothing under `app/tools/` was
  imported except `suite.serialdbg.build_all_tests`/`build_all_meta`.
  `./run/check-docs` was run once before handover: **6 passed / 0 failed**, C6
  `265 registry ids, 424 doc ids, 224 bound; 41 orphan / 3 undeclared /
  0 mismatched; 44 on the ledger, 0 unexcepted` — **identical to every prior
  package's figures, so amendment A2 held a sixth time.**
