# M-TESTQUAL WP-E — the LocalPlayer family, audited per test

> Owner: **Verification Engineer**
> Status: in progress
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Prior packages: [WP-A harness](M-TESTQUAL-A-harness-review.md), [WP-B taxonomy](M-TESTQUAL-B-taxonomy-review.md), [WP-C gating classes](M-TESTQUAL-C-audit-core-review.md), [WP-D shell FEATURE](M-TESTQUAL-D-audit-shell-review.md)

---

## 0. Scope, and how the corpus was measured

Every id whose body lives in `app/tools/suite/serialdbg/player.py` — the 26
`T_PLR_*` ids of M-WINAMP-PLAYER plus the five `T_PMT_*` player-mode transition
cells that were deliberately placed in this module rather than in `shell.py`
(`player.py:4-10`, `_meta.py:22`).

```sh
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
m=build_all_meta()
for t,v in m.items():
    if v['module']=='player': print(t, v['cls'], v['scope'], v['effect'])"
# -> 31 ids, all cls=FEATURE.
#    scope: 28 LocalPlayer, 1 Spotify (T_PMT_01), 1 WebRadio (T_PMT_02),
#           1 LocalPlayer-by-default (T_PMT_03, @meta(scope_reason="cross-mode"))
#    effect: 30 mutating, 1 resetting (T_PLR_26 — it reboots the board)
```

**The index's §3 row says "29 ids". It is 31.** The row was written from the
`T_PLR_01`–`26` + `T_PMT_00`–`03` shape and predates `T_PMT_04` (TASK-513);
`T_PLR_25` is also in the registry even though the gate runs its playback half
elsewhere. §3's row is corrected in this package's index edit; the rollup uses
31.

Static audit only, per rubric §5: no flash, no `run/test*`, no
`run/browser-player`, no `run/playorder-player`, no `run/player-gate`, no serial
port. The board is pinned to the `-DBOD_WATCH` debug build for TASK-557.
`build_all_meta` was the only import made under `app/tools/` (rubric §5 /
amendment A1); `player.py`, `_helpers.py`, `webradio.py`, `coords.py`,
`_order.py`, `_meta.py`, `runner.py`, `lib/results.py`, `lib/dut.py`,
`test_fbrowser_player.py`, `test_playorder_player.py`, `run/player-gate`,
`player-gate-baseline.md` and the firmware under `app/src/` were **read**, never
imported or executed.

Per amendment A2 the per-test tables put the **body location in column one** and
the id in column two, and no section is headed with a bare id.

### 0.1 What is distinctive about this corpus

1. **This family has a physical oracle the other families do not.** LocalPlayer
   decodes real MP3s off an SD card, so "the position advanced", "EOF fired",
   "the next track started" are all observable. §6 answers how much of the family
   actually uses it: **two ids of 31 observe audio progressing** (`T_PLR_09`,
   `T_PLR_25`), and one of those two can only ever skip on the env it runs on.
2. **It has the best debug surface in the suite.** `advance next|prev`,
   `set plCursor`, `get plOrder`, `get plCursor`, `get plMem`, `get fbState`,
   `get player`, `get arenaStats` were purpose-built (ADR-059 D12) so the
   play-order engine could be exercised in seconds instead of hours. That surface
   is why the `T_PLR_20`–`24` block is the strongest run of consecutive SOUND
   rows in any family audited so far — exact permutations, exact counts, exact
   moved/reshuffled flags, no proxies.
3. **Every marker this family greps for exists in the firmware.** Unlike WP-C and
   WP-D, which each found tests waiting on strings `app/src/` never prints, all
   four markers used here are live: `"hard reset — stopping client"`
   (`spotifyTaskStorage.cpp:363`, `LOG_I`), `"dequeued action=SHUFFLE"` /
   `"…=REPEAT"` (`:420` with `actionName()` at `:333-334`, `LOG_D`), and the
   `HEAP …` capture line webradio's entry helper parses. The *level gate* on the
   `LOG_D` pair is a separate problem — **E-6**.
4. **Two ids have a second executable body outside the registry** — `T_PLR_13`
   and `T_PLR_25` (WP-A **A-15**). §7 compares them.
5. **The family has a release gate of its own**, `run/player-gate`, which is the
   only `run/` entry point in the repo that compares results against a
   pre-declared per-id pass set. §8 says what a green leg does and does not prove.
6. **`effect=mutating` on 30 of 31**, and the family's shared entry helper
   `_enter_player` writes `set playerMode player` + `set bgPoll 0` on every
   entry — WP-B cluster **C3** (`playerMode`) and **C2** (`bgPoll`) both run
   through this module.

---

## 1. Mode, eject and TLS — `T_PLR_01`–`07` (7)

Registry order `player.py:1972-1978`.

Two firmware facts decide three of these rows, and both are cited rather than
re-derived below.

**(a) `cmdTap`'s taskbar branch takes the slot modulo the taskbar app count.**
`int slot = y / TASKBAR_SLOT_H; int appIdx = (tbScrollOffset + slot) % TASKBAR_APP_COUNT;`
(`cmdTouch.cpp:29-31`), and `TASKBAR_APP_COUNT` is 11 — `APP_SLOT["WebRadio"]`
(`_helpers.py:400`). So an `appIdx` of 11 (WebRadio) or 12 (LocalPlayer) is
**arithmetically unreachable** from a taskbar tap. The only way either app is
ever the target is `resolvePlayerTap`, which returns its argument unchanged for
anything but `AppId::Spotify` (`appShell.cpp:76-86`).

**(b) `get playerBind` is a fixed `Serial.printf`.** `"op":"playerCycle"`,
`"region":"TASKBAR_SLOT"` are string literals in the reply
(`cmdGet.cpp:612-618`) — the same class of oracle as WP-D's **D-1** ids.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `player.py:35` | T_PLR_01 | A taskbar tap on the *active* player slot cycles Spotify → WebRadio → Player → Spotify → WebRadio over four taps. | Four `get appId.name` values compared as a list against `["WebRadio","LocalPlayer","Spotify","WebRadio"]`. | **SOUND** | S9, S14 | `:45-57`. Four device-observed names against four distinct expected values, failed as one sequence so a cycle that stalls, skips or reverses is caught and printed. `resolvePlayerTap`'s cycle branch is genuinely exercised (`appShell.cpp:83-85` — `playerModeNext` + `persistPlayerMode`), and the tap goes through `cmdTap`'s production resolve path, not a debug shortcut. `time.sleep(0.3)` after each tap where `get idle`/`_poll_shell_busy` exist (`:50`). Writes `set playerMode spotify` and restores Spotify on both exits (`:52-53`) — cluster **C3**, accepted. |
| `player.py:60` | T_PLR_02 | `test_plan.md:383` / baseline: **"mode persists across reboot"**. | **None for that claim.** `set playerMode <name>` then `get playerMode`, three times, comparing against the value just written. No reboot. | **HOLLOW** | S3, S4, S13, S12 | `:70-80`. Textbook S3: every asserted value is the harness's own input, read back out of the same `g_settings.playerMode` byte the setter wrote (`cmdGet.cpp:620-627` vs `cmdSet.cpp`'s `kPmNames` parse). The docstring is honest about it — *"no live reboot here; the boot-restore path itself is covered by manual DUT verification per TASK-413's gate notes"* (`:61-65`) — which is S4: the claimed behaviour is handed to a human and the precondition is called a pass. The reboot idiom exists in this very file and is used correctly by `T_PLR_26` (`:1610-1612`). And what remains after the claim is stripped — "all three values round-trip" — **is `T_PLR_04`'s entire declared subject**, asserted there more thoroughly (numeric form + out-of-range rejection). Two registry slots, one assertion, and the stronger one is the sibling. |
| `player.py:83` | T_PLR_03 | "Taskbar has no leaked slot for WebRadio **or** LocalPlayer — neither eject-only app is ever selected by a taskbar tap" (TASK-242 regression, generalised). | Twelve `_tb_set_offset` steps each followed by "`get appId` returned some name"; then, at two scroll offsets, `name not in ("WebRadio","LocalPlayer")`. | **HOLLOW** | S3, S1, S8, S12 | `:103-111` against `cmdTouch.cpp:29-31` and `appShell.cpp:76-77`. The leak assertion **cannot fail**. The probe taps `tap_taskbar_slot(0)` → y=20 → `slot=0`, so `appIdx = (offset + 0) % 11`; at the two chosen offsets (`_TB_N//2`=5, `_TB_N-1`=10) that is 5 (Life) and 10 (Settings), and `resolvePlayerTap` passes both through untouched because they are not `AppId::Spotify`. WebRadio (11) and LocalPlayer (12) lie outside the modulus entirely — the body's own comment even explains that offset 0 was excluded because it *is* the player slot, which removes the only appIdx that could have produced either name. The leak class is closed at compile time anyway (three `static_assert`s, `test_plan.md:504`). What is left is the scroll-cycle liveness half, whose oracle is `dut.cmd("get appId").get("name")` being truthy (`:95`) — any board that answers at all passes. Same shape as WP-C **C-15** (`T242` samples 2 of 11 offsets and asserts only "not WebRadio") and WP-D **D-1**. Also: `_tb_set_offset`'s return is discarded at `:104`, and both `fail()` paths return without `_restore_spotify`, leaving an arbitrary app and a non-zero `tbScrollOffset` for the next id. |
| `player.py:116` | T_PLR_04 | `get`/`set playerMode` round-trip all three values by **name and by numeric index**, and an out-of-range index is rejected (§6.1 debug-surface widening: the pre-TASK-413 getter collapsed Player(2) to WebRadio(1) and the setter rejected idx>1). | Three `(val, name)` pairs against three distinct expectations, plus `r_bad.get("ok", True)` on `set playerMode 3`. | **SOUND** | S6, S13 | `:122-137`. The mixed name/numeric case list is the point and it is real — `("1", 1, "WebRadio")` exercises the numeric parse the old setter rejected, and `name` is checked as well as `val`, so a getter that collapsed 2→1 fails on both fields. The negative case defaults to `True`, i.e. to the value that **fails** — the safe direction, and the opposite of WP-C **C-12**. Two costs: it subsumes `T_PLR_02` (above), and its restore `set playerMode {r_pm0.get('val', 0)}` (`:130`) is C-12's dangerous default — a lost entry read silently writes mode 0 rather than restoring. Same line shape at `:76` and `:159`; filed once as **E-4**. |
| `player.py:140` | T_PLR_05 | Tapping the player slot from **another** app restores the persisted mode (`resolvePlayerSlot`) rather than cycling; a second tap, now that the player is active, does cycle. | `appId == "LocalPlayer"` after the restore tap **and** `appId == "Spotify"` after the cycle tap. | **SOUND** | S9, S6, S14 | `:145-167`. The two-tap construction is what makes this sound: it establishes a non-default persisted mode (`player`, not the harness default), steps off to Clock so the first tap must take the restore branch, and then asserts the *branch change* on the second tap. A regression that made both taps behave the same fails on one of the two names whichever way it collapsed. Same `r_pm0.get('val', 0)` restore default as `T_PLR_04` (`:159`), and two `time.sleep(0.3)` where `_poll_shell_busy` exists. |
| `player.py:176` | T_PLR_06 | Eject is **per-mode**: Spotify → TLS reset + force poll (app unchanged); WebRadio → station-list refresh (`wrEnqueues` advances, app unchanged); Player → the file browser opens (app unchanged, because the browser is modal *within* the app). | Per leg: `hit`/`action` from the tap reply, `get appId` after, plus a `"hard reset"` log line (Spotify), `get dataq.wrEnqueues` strictly advancing (WebRadio), and `get fbState.active` (Player). | **SOUND** | S7, S13, S9 | `:220-294`. Three genuinely different device-observed effects behind one verb, each with the "and the app did not change" companion that TASK-414's redefinition of eject actually turned on. The Spotify leg uses `_tap_and_wait_log` (`:220`) — the correct instrument, and the docstring at `:211-218` explains why the split-read it replaced was wrong. `wrEnqueues` is compared strictly (`enq_after <= enq_before` is an error, `:249`) and both reads default to 0, so two lost replies fail rather than pass — the safe direction. The docstring `:180-197` is the best piece of test archaeology in the suite: it records that TASK-415 silently invalidated this id's old assertion and that the suite carried a stale expectation for a day. Costs: three unrelated legs under one id, so a failure names the leg but the id gives no locality; and the `heap_pressure_skip` path (`:277-304`) converts a real "eject did not open the browser" into a SKIP whenever `get activeError.active` is set — a documented and defensible S7, but it is the one exit through which a genuine Player-leg defect can leave green. |
| `player.py:312` | T_PLR_07 | The Winamp **logo** tap still resets TLS — a regression check for TASK-414's refactor that moved TLS-reset + force-poll into a shared `tryReconnect()` used by both the logo tap and eject. | `hit == "LOGO"` and `action == "TLS_RESET"` (real), then a bare `dut.ser.readline()` loop hunting `"hard reset"` / `"stopping client"` for 8 s. | **WEAK** | S5, S13 | `:323-337`. The hit-test half is real and `fail()`s properly (`:324-326`). The log half is **the exact split-read race `_tap_and_wait_log` was written to remove**, in the same file, 90 lines below a body that uses the helper for the same marker: `dut.cmd(f"tap …")`'s `read_json` discards every non-JSON line while hunting the tap reply (`lib/dut.py:1079-1091`), and `"[I][spotify.tls] hard reset — stopping client"` is printed from a different FreeRTOS task (`spotifyTaskStorage.cpp:363`) and can land in exactly that window — the failure mode `_helpers.py:23-42` documents from a raw serial capture. When it does, the body calls `flake("T_PLR_07", …)` (`:335`), and **`T_PLR_07` is not declared in `flaky.yaml`** (only `T_PLR_17` and `T_PMT_04` are, `flaky.yaml:112,130`), so `flake()` converts it to `FAIL: UNDECLARED flake — no entry for T_PLR_07 …` (`lib/results.py:185-192`) — a failure message about bookkeeping, on a declared-PASS gate cell. New instance of WP-C **C-7**. Its two assertions also duplicate the LOGO leg of `shell.py`'s `T087` (WP-D §1). |

---

## 2. The M3U index and the file browser — `T_PLR_08`–`16` (9)

Registry order `player.py:1979-1987`. All nine enter through `_enter_player`
(`:366-413`) and exit through `_leave_player` (`:416-420`).

**The shared defect of this block is its fixture oracle.** `_pl_load`
(`:423-426`) issues `set plLoad <path>` and **throws away the reply**, returning
only `get plCount`. `set plLoad`'s reply carries the one field that separates the
two cases — `"ok":true|false` from `dbgLoad()` (`cmdSet.cpp:197-199`) — and
`get plCount`'s `count` is 0 for *three* different reasons: the fixture is not on
the card, the load failed for any other reason, and **the index is not allocated
because the mode is not resumed**, which `cmdGet.cpp:629-633` states explicitly
(*"The index is only allocated while the mode is resumed, so the honest answer
off-screen is count=0"*). Six ids then map `count == 0` onto `skip("… fixture not
on the card")`. Filed as **E-1**.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `player.py:429` | T_PLR_08 | A ≥100-track M3U loads, the count is exact, and the last row is right. | `count == 120` **and** `truncated is false` **and** the text of row `count-1` contains `"(120)"`. | **SOUND** | S7, S10 | `:439-453`. Three independent oracles, one of them the right kind: the last-row spot check catches an off-by-one in the record scan that the count alone cannot (`:447-448` says so). `truncated` is checked separately, so a 120 that is really a cap is distinguished from a 120 that is really 120. `120` and `"(120)"` are mirrored from `gen/gen_playlist_fixtures.py:52` rather than derived, and the `count == 0` skip is **E-1**. |
| `player.py:459` | T_PLR_09 | Scroll the list end to end **while a track plays** — no stall, no reboot, playback survives. | `get plCount.playing` still true after 12 swipes, `scrollOffset` non-zero, DUT responsive. | **SOUND** | S7, S10, S8 | `:485-536`. One of only two ids in the family that observe real audio, and its oracles are the right ones: `playing` is read from `_playing` (`localPlayerApp.cpp:427`), which only the decoder sets, and the post-sweep check is a `fail()`, not a skip (`:529-531`). Its playback **precondition** is a skip (`:491-512`) and that skip is the single most carefully argued comment in the suite — 20 lines naming the env it is correct on (`cyd2usb_winamp_debug`, where the arena cannot be acquired with Spotify's TLS working set resident, TASK-425/431), the env it would be wrong on, and the exact trigger for flipping it. It is also declared `SKIP` in the gate's pass set (`player-gate-baseline.md:68`). The consequence is still that **this id has never produced a verdict on the env the harness runs**: it is a permanent non-result whose body is sound. `if not off` (`:533`) is a truthiness check where `off == 1` would pass a list that scrolled one row in twelve swipes; `12` swipes ≈ 120 rows is hand-derived in a comment (`:515`). |
| `player.py:544` | T_PLR_10 | Relative paths resolve against the **playlist's** directory — bare, `./` and `../` — and a collapsed `..` path actually opens. | `row0.path == "/mp3/01 - Tomorrow Comes Today.mp3"` exactly; row 4 starts `/mp3/` and contains no `./`; a `../` fixture's row 0 equals the same collapsed absolute path; and a playlist loaded *through* `/mp3/../playlists/gate100.m3u` returns `count == 120`. | **SOUND** | S7, S10 | `:559-585`. Four oracles, three of them exact strings on a field (`path`) the firmware computes rather than echoes (`localPlayerApp.cpp:441`). The fourth is the best decision in the block: resolution is proved to *open* by loading a playlist through the `..` path rather than by playing a track, and `:576-581` explains exactly why — routing the proof through the audio engine would make the test fail whenever the Helix arena cannot get its 24 KB, which says nothing about path resolution. That is the reasoning `T_PLR_25` does not apply to itself (**E-2**). The expected paths mirror the fixture generator. |
| `player.py:594` | T_PLR_11 | Malformed M3U degrades — BOM, CRLF, missing/garbage `#EXTINF`, a directive between record and path, a trailing record with no path line, an empty file — and the UTF-8 fold is applied to row text. | `count == 8`, then six `(text, durSec)` pairs against six distinct expectations, a trimmed path on row 7, `count == 0` on the empty file, four folded titles, and `"????"` on the CJK row. | **SOUND** | S13, S5 | `:609-654`. Fourteen exact comparisons against fourteen distinct expected values, every one of them a value the parser computes. The `(4, "05 - Feel Good Inc", 222, …)` row carries its own correction history (`:618-621`) — the expectation was originally wrong and demanded that a malformed *title* discard a good duration. Two defects, both small. The fixture guard `if r.get("count", 0) == 0 and not r.get("ok")` (`:605`) is **unreachable**: `get plCount` is `dbgReport()`, which always prints `"ok":true` (`localPlayerApp.cpp:418`), so a genuinely absent `bad.m3u` falls through and fails with `count=0 (expected 8)` — louder than its siblings, but by accident, and the skip branch is dead code. And 14 assertions share one id. |
| `player.py:664` | T_PLR_12 | The index is bounded (≤5.2 KB) and **returned** on suspend (±256 B), with largest-free-block reported alongside free heap so a clean free-heap figure cannot hide fragmentation. | `freed.allocated` false, `d_load <= 5324`, `abs(d_free) <= 256`, all computed as within-run deltas against a baseline taken with the mode suspended. | **SOUND** | S10, S9 | `:677-717`. A genuine before/allocate/free triangle: the baseline is taken with the index provably not allocated (`base.allocated` is itself asserted, `:678-681`), the peak is sampled with the file handle still open and reported separately from the resting cost, and the residual is checked against the same baseline. `plMem`'s fields all exist (`localPlayerApp.cpp:448-457`). The 3 s wait at `:691` is derived, not arbitrary — it outlasts the 1.5 s idle close of the playlist `File`, whose ~4.4 KB stdio buffer would otherwise be counted as index memory. `5324` and `256` are uncited literals. Unlike its six siblings a missing fixture here is an **error**, not a skip (`:711-713`) — the right call, but the inconsistency is **E-1**'s other half. `base["freeHeap"]` is raw-indexed (`:700`), so a lost reply raises and the dispatcher records a `FAIL: Exception` (`runner.py:432-433`) — loud, but attributed to the wrong cause. |
| `player.py:783` | T_PLR_13 | `test_plan.md:394`: **"browser paging never stalls audio."** The docstring narrows it honestly to "the walk completes cleanly and the DUT stays responsive", and points at `test_fbrowser_player.py` for the audio half. | `st.get("pending")` false within 15 s. That is the whole assertion. | **WEAK** | S8, S2, S4, S13 | `:794-817`. No audio is started, so the plan's claim has no oracle here at all — the body says so (`:786-790`) and §7 takes that up. What remains is one boolean with a 15 s ceiling on a walk the body's own comment measures at ~5 s (`:833-835`), so the bound cannot be violated by anything short of a hang. The walk's *result* is never asserted: `dirCount` and `fileCount` are interpolated into the pass string with the prose "0 expected, TASK-408's fixture is all .txt, filtered" (`:816-817`) — an expectation stated in a pass message rather than compared, which is S4's shape. A browser that returned instantly with zero entries passes. And the one thing it does assert — pending clears — **is `T_PLR_15`'s second assertion verbatim** (`:903`), so this id is a strict subset of its sibling plus a timing bound. Its one distinct contribution is real and worth keeping: `_fb_fixture_missing` (`:753-766`) probes with `sdls`, an independent path that does not go through the browser's own state or heap, so a genuine reopen failure `fail()`s instead of hiding in a skip — filed as TASK-433 after it did exactly that. |
| `player.py:820` | T_PLR_14 | A tap on the browser's back/up zone is honoured **even while a page walk is in flight** — the TASK-384 defect class, where `isNavigationTap()` must except it or `shell::state().busy` swallows it. | `get shellBusy.busy` true (the gate is provably armed), `fbState.active && pending` (the walk is provably in flight), `r2.skipped` false on the back-zone tap, and the browsed `dir` changed afterwards. | **SOUND** | S10, S11, S7 | `:846-869`. The strongest busy-gate test in the suite, and the reason is the construction, not the assertion: it refuses to run unless it has *observed* the gate armed (`:849-857` — a walk that finished too early is a `skip()`, correctly, because the bug under test is then unrepresentable), and it drives the **real** `tap` path rather than the `fbSelect`/`fbCancel` debug shortcuts, which bypass the gate entirely and would prove nothing (`:824-828`). The firmware side is genuinely on the other end of the assertion: `cmdTouch.cpp:41-45` computes `navTapBypass` from the active app's `isNavigationTap`, and `:104-108` sets busy on the LocalPlayer branch specifically so this id has something to exercise. Costs: `tap 10 10` is a literal with the firmware constants named only in a comment (`:862` — "x<S_BACK_ZONE_W(60), y<S_HEADER_H(28)"), which is LL-114's mirror-don't-parse in its mildest form; and the final check is guarded on `st2.get("active")` (`:868`), so a back-zone tap that *closed* the browser instead of ascending passes. |
| `player.py:878` | T_PLR_15 | `hasPendingAsync()` is true from the moment a page walk starts and **self-clears** when it finishes, with no other action — the NEW-APP-CHECKLIST item-1 contract. | `pending` true on the reply taken immediately after `fbOpen`, **and** `pending` false on the reply after the poll loop. | **SOUND** | S7, S13 | `:895-904`. Two device-observed values at two points across a transition the test does not drive — the "self-clears" half is the contract, and nothing between the two reads asks the browser to do anything. Both fields exist (`fileBrowser.h:339-353`). Shares the TASK-433 `sdls` discrimination with `T_PLR_13` (`:887-893`), and subsumes that id's only assertion. |
| `player.py:912` | T_PLR_16 | Deep/edge directory shapes: nested descend, an empty directory, 8.3 vs long filenames, `.m3u` kept and non-audio filtered — no crash, correct filter, correct bucket counts. | Five directory shapes with **exact** `dirCount`/`fileCount` pairs, plus a two-level descend asserting the landed `dir` string and its file count. | **SOUND** | S13, S10, S14 | `:936-960`. Exact equality on both buckets at four paths, and the descend leg (`:942-952`) asserts the *destination* (`dir == "/probefb/nested/deep/"`, `fileCount == 1`) rather than merely that a select was accepted — so a descend that landed in the wrong directory is caught. The root check deliberately asserts only `fileCount == 0` and passes `None` for `dirCount` with the reason written in the label (`:960`), which is the honest way to handle a card-dependent value. A missing fixture here is an `errors.append` → `fail()` (`:924`), not a skip — the opposite of `T_PLR_13`/`15` on the same class of condition (**E-1**). Six shapes under one id, expected counts mirrored from the fixture set, and it exits leaving the browser open on `/` with no `fbCancel` — `T_PLR_06` is the only body in the family that closes it (`:295`). |

---

## 3. The transport capability mask — `T_PLR_17`–`19` (3)

Registry order `player.py:1988-1990`. ADR-059 D8: `CAP_TRANSPORT|CAP_SEEK|
CAP_SHUFFLE|CAP_REPEAT` gate the shuffle/repeat/seek zones per mode, and
`get shufRep` reports the active mask **and** the currently-rendered sprite
indices in one call (`winampDisplay.cpp:708-713`), so a test can separate what is
*reachable* from what is *painted*.

**A filed defect these three inherit.** `T_PLR_17`/`T_PLR_18` are **swapped
between spec and implementation** — the design doc assigns 17 = "WebRadio
unchanged" and 18 = "Spotify unchanged"; the runner implements the reverse, and
firmware comments are split 2–2 between the conventions. Recorded at
`test_plan.md:413-424` as *"DEFECT, unresolved"*, and it makes every citation of
either id ambiguous (including `X061`'s coverage row, `test_plan.md:508`). Cited,
not re-derived, and it is why the plan's rows for both ids deliberately do not
name a mode. That is rubric **S12** on two ids that are otherwise well built.

**A second, unfiled one.** All three carry `scope=LocalPlayer` (§0's command),
but `T_PLR_17` drives **Spotify** end to end and `T_PLR_18` drives **WebRadio**
end to end. `./run/test-targeted --scope Spotify` and `--scope WebRadio` — the
selection path TASK-570 built and CLAUDE.md documents — therefore miss the two
capability-mask regressions for exactly those modes. `T_PMT_01`/`T_PMT_02`, in
this same module, declare `@meta(scope=…, scope_reason="cross-mode")` for
precisely this reason (`:1750`, `:1757`), so the mechanism exists and was not
applied here. **E-5**.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `player.py:1015` | T_PLR_17 | Spotify still advertises **all four** capabilities — shuffle and repeat still drawn, still hit-tested, still dispatching `ACT_SHUFFLE`/`ACT_REPEAT`. "Zero delta is the pass condition." | `caps == 15`; then per sprite, `hit`/`action` from the tap reply **and** a `"dequeued action=SHUFFLE"` / `"…=REPEAT"` line within 20 s. | **SOUND** | S12, S14, S6 | `:1031-1068`. Five device-observed values, and the dispatch half is the correct instrument: the dequeue trace is printed by `spotifyTask`'s own generic dispatcher (`spotifyTaskStorage.cpp:420`, `actionName()` at `:333-334`), so it proves the tap reached the real enqueue rather than only the sprite. Both legs use `_tap_and_wait_log` (`:1051`, `:1062`) and the docstring at `:1042-1048` records the raw-serial capture that proved the old split-read was eating the line. The 20 s bound is justified against `T082`'s measured dequeue lag rather than picked (`:1038-1041`). Three residuals: the swapped id (above); **it exits without restoring shuffle/repeat**, so two real Spotify state toggles are left enqueued for every later id; and `flaky.yaml:112` declares `T_PLR_17` as a flake while the body never calls `flake()` — see **E-3**. |
| `player.py:1077` | T_PLR_18 | WebRadio advertises `CAP_TRANSPORT` only: shuffle/repeat neither drawn nor hit-tested and never reaching `spotifyTask`; volume still hit-tests (TASK-352/406 seam). | `caps == 1`, `hit`/`action` **not** SHUFFLE/REPEAT, `hit == "VOLUME"` — plus two *negative* log scans. | **WEAK** | S8, S14, S12 | `:1089-1125`. Three real assertions, and `caps == 1` is the load-bearing one — it reads `_playerCaps` (`winampDisplay.cpp:711`), which a mask regression would move. Three problems. **(a) The two negative log checks cannot distinguish "no leak" from "no logging."** `_wait_for_log(…, "dequeued action=SHUFFLE", 8.0)` returning `False` *is* the passing outcome (`:1104`, `:1114`), and the marker is a `LOG_D` line subject to the runtime level gate (`logSink.h:119-123`) — so on any board whose `logMinLevel` suppresses debug, both checks pass vacuously while burning 16 s. `T_PLR_17`'s positive use of the same marker fails loudly under that condition; the negative use fails silently. This is the polarity problem behind **E-6**. **(b) Its entry is accidental.** `_switch_to(dut, "WebRadio")` taps `tap_taskbar_slot(APP_SLOT["WebRadio"])` → y=460 → `slot=11` → `appIdx = 11 % 11 = 0`, i.e. **the player slot**, and it reaches WebRadio only because `resolvePlayerTap` *cycles* when the board is already on a player-mode app — which it is, because `T_PLR_17` ran immediately before and left it on Spotify. `webradio.py:30-33` states outright that this helper "tap[s] a taskbar slot WebRadio doesn't have" and directs callers to `_switch_to_webradio_capture_heap` instead; `T_PLR_06` uses that helper (`:233`), this id does not. Run alone from Clock the same tap *restores* the persisted mode and the id skips. Not in `_order.py`'s `EDGE_ADJUDICATION`. **(c)** No restore: it exits in WebRadio with `playerMode=webradio` persisted. |
| `player.py:1134` | T_PLR_19 | Player advertises all four capabilities, with shuffle/repeat state sourced from **Player** and not `spotifyTask::Snapshot` (D8); the seek zone is reachable via the real per-app input path without engaging Spotify's posbar-drag machine. | `caps == 15`; `lastShuffle`/`lastRepeat` **changed** after each tap; two negative dequeue scans; `dragState == "D_IDLE"` after a `drag`; DUT answers a follow-up command. | **SOUND** | S8, S14, S13 | `:1148-1204`. The changed-not-merely-hit assertion (`:1162-1165`, `:1177-1180`) is what makes this the right shape and `T_PLR_18` the wrong one: it compares the sprite state before and after and fails if the tap hit-tested but did not toggle. The seek leg is deliberate and well-argued — it drives `drag` rather than `tap` because `tap` classifies through Spotify's `songDuration`-gated `hitTestPosbar()` and Player never sets `songDuration` (`:1185-1191`) — and it asserts the *negative* state-machine outcome (`D_IDLE`) that D8 requires. The two negative dequeue scans carry the same **E-6** vacuity as `T_PLR_18`'s. Exits with shuffle/repeat left toggled in Player mode and no restore; `T_PLR_26` is the only body in the family that resets them (`:1623-1624`). |

---

## 4. The play-order engine — `T_PLR_20`–`26` (7)

Registry order `player.py:1991-1997`. This block is the best-built run in the
family and, on the evidence of WP-C and WP-D, in the suite. The reason is
structural rather than authorial: ADR-059 D12 added `advance next|prev`,
`set plCursor` and `get plOrder`/`get plCursor` **specifically** so that these
seven behaviours could be asserted exactly, on the same `_stepOrder()` real
playback uses, without a decode (`:1215-1220`, `cmdSystem.cpp:22-40`). Where a
family is given exact observables, its tests assert exact values.

Two shared costs apply to all seven and are not repeated per row: every one
enters via `_pl_load` and so inherits **E-1**'s fixture/skip conflation, and
every one leaves shuffle and/or repeat in a non-default state (only `T_PLR_26`
restores).

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `player.py:1268` | T_PLR_20 | The shuffle bag visits each track **exactly once** over a full cycle — 20 × `advance next` on a 20-track list, no repeats, no skips. | `plOrder` is a 20-entry permutation (`len == 20 and len(set) == 20`); every `advance` reports `moved`; and the visited row sequence **equals `plOrder` element for element**. | **SOUND** | S7, S14 | `:1288-1303`. The last clause is the strong one: it is not "all distinct" but "the walk *is* the bag", so a stepper that visits every track once in the wrong order fails. `plOrder` is `_pl.playOrder()` streamed straight out of the index (`localPlayerApp.cpp:480-494`) and `advance`'s `moved`/`row` come from `_stepOrder` itself (`cmdSystem.cpp:34-38`) — two independent views of the same engine, compared against each other. |
| `player.py:1312` | T_PLR_21 | All four shuffle × repeat end-of-list cells (design §8), forced via `set plCursor <last>` + `advance next`. | Four cells, each asserting an exact `(moved, row, reshuffled)` triple: `moved=false`; `moved=true, row=0, reshuffled=false`; `moved=false`; `moved=true, reshuffled=true`. | **SOUND** | S7, S13, S14 | `:1337-1369`. Four distinct expected outcomes on three fields, and `moved is not False` / `is not True` rather than truthiness, so a missing field fails instead of defaulting. `_force_wrap_from_last` (`:1327-1335`) carries the single best comment in the family: it sets the cursor explicitly every time and refuses to infer "am I already at the end" from a `get plCursor` read, *because that reflects the previous cell's advance rather than this cell's precondition and masks exactly the drifted-cell failure the test exists to catch*. That is the anti-pattern WP-B §5.3 catalogues, avoided deliberately and in writing. Four cells under one id is the only cost. |
| `player.py:1379` | T_PLR_22 | Reshuffle-on-wrap never re-opens with the track that just finished — 20 forced wraps, 0 collisions. | Per wrap: `plOrder` re-read before and after, `moved and reshuffled` both true, and `after[0] != before[19]`. | **SOUND** | S7, S14 | `:1396-1411`. Twenty independent trials of a probabilistic property, each comparing two device-read permutations, and the reshuffle flag is asserted on every iteration so a wrap that silently failed to reshuffle cannot be counted as a non-collision. |
| `player.py:1420` | T_PLR_23 | Prev replays history — walks `playOrder` backward, never rerolls: 5 × next then 5 × prev must be the exact reverse, and `plOrder` must be identical before and after. | The four retraced rows against `reversed(forward[:-1])`, all four `moved` true, the fifth `moved is False`, and `order_before == order_after`. | **SOUND** | S7, S14 | `:1438-1466`. Four assertions on three different aspects, including the boundary (`:1462-1463` — the 5th prev at bag position 0 must report `moved=false`, not wrap) and the no-reroll invariant on the whole permutation. The index arithmetic at `:1453-1456` is spelled out in a comment and is correct. |
| `player.py:1476` | T_PLR_24 | Tap-to-play under shuffle moves the bag cursor to that entry's position — it does **not** reshuffle. | `cursor == order_before.index(5)`, `curRow == 5`, and `plOrder` unchanged. | **SOUND** | S7, S2, S14 | `:1495-1513`. The expected cursor is *computed from the device's own permutation* rather than assumed, which is what makes it a real assertion — the value differs run to run and cannot be satisfied by a stuck cursor. `set plPlay` is used rather than a screen tap for the documented reason that row position depends on live scroll offset (`:1478-1480`), and it is the same `dbgPlayRow` entry point PLEDIT's `onTap()` drives. `pick.get("ok")` is checked (`:1502`) but is only "row index valid", never "started" (`cmdSet.cpp:211-213`) — S2, harmless here because the cursor is the real oracle. |
| `player.py:1526` | T_PLR_25 | Auto-advance end to end — the one real-playback case, proving `audio_eof_mp3()` drives the same `_stepOrder()`/`_startPlayback()` path the debug surface exercises. 5 real ~3 s files, shuffle off, repeat off, 5/5 advances, no WDT. | `played_rows == [0,1,2,3,4]` and playback observed to stop after row 4. | **BROKEN** | S12, S9, S14, S10 | `:1548-1585`. The oracles are the right ones and the intent is exactly right — this is the id that closes the loop between the debug surface and real EOF. It cannot do it **on the only env it is dispatched on**. Local playback does not start on `cyd2usb_winamp_debug` with Spotify's TLS working set resident (TASK-425/431, asserted three times in this same file at `:493-505`, `:788-790`, `:1780-1783`), and unlike its two neighbours this body has **no guard**: `T_PLR_09` skips with a 20-line justification and a flip trigger (`:492-511`), `T_PMT_04` opens with a `get variant` leg guard (`:1803-1809`), `T_PLR_25` has neither. `set plPlay 0` returns `ok:true` regardless (it means "row index valid"), so the body proceeds, polls for the full 60 s, collects `played_rows == [0]` — `curRow` is set by `_playRow` even when the decode never starts — and reports `FAIL: row sequence [0] != [0,1,2,3,4]`. A deterministic 60-second false red in every `run/test`, every `--scope LocalPlayer` run, and every `--tests T_PLR_25`. The gate does not see it because leg A's id list deliberately omits it (`run/player-gate:84-87`) and the pass set says so (`player-gate-baseline.md:94-96`) — which means the family's own release gate has been silently routing around a permanently red registry cell. Per rubric §2 ("cannot do its job as written… a body that no longer matches the firmware surface it drives") that is BROKEN, not WEAK. Second-order: on the env where it *can* run it leaves the arena held after `_leave_player()`, which is the contamination that produced TASK-553's false regression in `T_PMT_04` (`player-gate-baseline.md:98-111`, `test_plan.md:474`) — **E-7**. |
| `player.py:1588` | T_PLR_26 | Shuffle/repeat persist across a **real** reboot; Spotify's own shuffle/repeat are never written to `g_settings.player*` (ADR-059 D9). | `lastShuffle == 1` and `lastRepeat != 2` read back **after** `reboot` + `_wait_for_ready()`. | **SOUND** | S9, S14 | `:1595-1630`. The only genuine persistence test in the family, and the contrast with `T_PLR_02` is the whole point: the assertion crosses a power cycle the test did not simulate, so the value has to survive `suspend()`'s coalesced settings write and the boot restore. The discipline is explicit — it leaves Player *before* rebooting because ADR-050 rule 3 only fires the write on a mode switch away (`:1600-1603`). It restores off/off on the way out (`:1623-1624`), the only body in the family that does. Costs: it is one of the three mid-suite reboots (WP-B cluster **C6**, `player.py:1610`), so everything the preceding 25 ids established is wiped at this point; and the post-reboot `_enter_player` failure path returns without restoring shuffle/repeat, leaving them persisted for the rest of the run. |

---

## 5. Player-mode transitions — `T_PMT_00`–`04` (5)

Registry order `player.py:1998-2002`. M-TESTBASE §8's thesis: drive the
**operation** (`playerCycle`), never a coordinate, so that relocating the surface
costs one edit. `T_PMT_00` is the one cell that touches a coordinate and it
derives it from `get playerBind`.

`_pmt_edge` (`:1670-1710`) is the shared body for 01–03 and asserts the whole
`get player` vector: `mode`, `modeName`, `srcName`, `caps`, `arenaHeld`, and the
presence-or-absence of `plCount`. Every field is compared with no default, so a
missing field reads as `None` and fails — the safe direction throughout. Two of
those fields are genuinely new observables rather than aggregation: `srcName`
(which `PlaylistSource` last drove a PLEDIT draw) and the playlist half's
`playHash`/`viewHash` (`cmdGet.cpp:560-599`, `localPlayerApp.cpp:465-478`).

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `player.py:1713` | T_PMT_00 | **The binding test.** The surface named by `get playerBind` still performs the cycle; if it fails, `T_PMT_01`–`04` are meaningless. | `op == "playerCycle"`, `region == "TASKBAR_SLOT"`, then a tap at that slot and `after != before` on `get player.mode`. | **WEAK** | S3, S8, S7 | `:1719-1747`. Two of the three assertions are tautologies on a fixed `Serial.printf`: `"op":"playerCycle"` and `"region":"TASKBAR_SLOT"` are string literals in the reply itself (`cmdGet.cpp:612-618`), so they can only fail if someone edits that printf — which is, to be fair, precisely the edit M-TESTBASE §8 asks for, but it is a self-consistency check on a debug string, not a behaviour. The load-bearing third assertion is real but is only `after == before` → fail (`:1742`): **a cycle to the wrong mode passes.** The expected successor is knowable (`playerModeNext`, and `_PMT_EXPECT` is defined 70 lines above at `:1643-1647`) and is not used. And the one regression this id exists to catch — the binding relocating, which really happened at TASK-413/414 and invalidated the harness and a design document — exits as `skip("… surface relocated; update this test")` (`:1728-1731`). It is at least visible inside `run/player-gate`, where a declared PASS observed SKIP is a REGRESS (`run/player-gate:195-197`); in a plain `run/test` it is silent. |
| `player.py:1751` | T_PMT_01 | Spotify → WebRadio; the full `get player` vector correct after. | Via `_pmt_edge(0, 1)`: `from/to` on the `playerCycle` reply, then `mode == 1`, `modeName == "WebRadio"`, `srcName == "StationList"`, `caps == 1`, and `plCount` **absent**. | **SOUND** | S9, S14 | `:1675-1706`. Six device-observed values against six distinct expectations, on two independent surfaces (the cycle reply and the post-settle vector). `srcName` is the assertion that earns the row: it proves the right `PlaylistSource` is actually driving PLEDIT, which nothing else in the suite observes, and it is a value the test cannot influence. The `plCount is not None` clause (`:1705-1706`) is a real negative — the firmware emits `"plCount":null` off-Player deliberately (`cmdGet.cpp:596-597`) rather than a plausible zero, and the test checks that. `_PMT_SETTLE_S = 2.5` is a fixed sleep used as the synchronisation for a repaint (`:1648`, `:1682`), which is the row's one flake surface. Correctly declares `@meta(scope="Spotify", scope_reason="cross-mode")` (`:1750`) — the mechanism `T_PLR_17`/`18` should have used (**E-5**). |
| `player.py:1758` | T_PMT_02 | WebRadio → Player; same vector. | `_pmt_edge(1, 2)`: as above with `modeName == "Player"`, `srcName == "LocalPlaylist"`, `caps == 15`, and `plCount` **present**. | **SOUND** | S9, S14 | `:1675-1706`. Same shape, and the `to == 2` branch flips the `plCount` assertion from "absent" to "present" (`:1702-1704`), so the pair brackets the field rather than testing it once. `@meta(scope="WebRadio", …)` declared. |
| `player.py:1765` | T_PMT_03 | Player → Spotify; vector correct **and the arena is not stranded**. | `_pmt_edge(2, 0)`: the vector, plus `arenaHeld in (0, None)`. | **SOUND** | S8, S9, S14 | `:1699-1700`. The vector half is as sound as its two siblings. The arena clause is **vacuous and `test_plan.md:473` says so in the plan itself** — *"mode switching alone never touches the arena (probed 2026-08-17, `acquires=0` on both legs), so that clause asserts 'a counter nothing incremented is still zero'. Kept as a cheap tripwire; the real M2 cell is `T_PMT_04`."* Cited, not re-derived; the honesty of that annotation is why this is S8 on one clause rather than a finding. |
| `player.py:1791` | T_PMT_04 | Real local playback **acquires** the arena and leaving Player **releases** it — the non-vacuous half of M2/X052. | Playback proven live (`plCount.playing && curRow == 0`), then `acquires > base_acq`, `active == 1` mid-play, and after `playerCycle`: `acquires > 0`, `active == 0`, `arenaHeld in (0, None)`, `releases > base_releases`. | **SOUND** | S7, S9, S10, S14 | `:1811-1967`. The strongest test in the family and one of the strongest in the suite. It asserts an **edge** on two independent counters plus the derived `active`, baselined in-test rather than assumed; it proves the subject is real before measuring it (`:1889` — `playing && curRow == 0`); and when playback never starts it **refuses to pass vacuously and says why**: *"the arena assertion below would be vacuous, which is the exact defect TASK-513 exists to remove"* (`:1910-1913`). That is the disposition the rubric's §1 question asks for, written into the body. Its three skips are all genuine precondition guards, each naming the condition and the command to satisfy it: the leg guard on `get variant` (`:1803-1809`), `arenaStats` unsupported (`:1812-1814`), and the arena already held at baseline (`:1838-1847`) — the last being the TASK-553 order dependence, adjudicated `EDGE` in `_order.py:194`, and correct: `mb_arena_acquire()` early-returns on `if (s_owned) return true;` *before* incrementing (`mb_arena.cpp:106`), so the 0→1 edge genuinely is unobservable on a boot where something already acquired. Costs: a 100 s fixed settle (`:1785`, `:1872-1876`) and 3 × 20 s retries; `set bgPoll 0` at `:1854` with **no restore anywhere in the body** (WP-B **B-6**'s hard leak, cited); and `flaky.yaml:130` declares it a flake while the body never calls `flake()` — **E-3**. |

---

## 6. The physical oracle — what this family actually observes

The brief's question: LocalPlayer plays real MP3s, so does each test *use* that,
or settle for a mode/state field?

| Bucket | n | Ids |
|---|---|---|
| **Observes audio progressing** — reads `plCount.playing` / `curRow` across time while a decode is (or should be) running | **2** | `T_PLR_09`, `T_PLR_25` |
| **Observes a real side effect of a decode attempt** — the arena counters, which only `aeConnectFile()` moves | **1** | `T_PMT_04` |
| **Starts playback but asserts on something else** — `set plPlay` is issued, and the oracle is the cursor or a heap figure | **2** | `T_PLR_12`, `T_PLR_24` |
| **Asserts on the index / order engine / browser / mask / mode vector** — no audio anywhere | **26** | everything else |

So **three ids of 31 (10 %)** have any audio-side oracle at all, and of those:

* `T_PLR_09` skips on the harness's own env by design and always has;
* `T_PLR_25` fails on the harness's own env by omission (**E-2**);
* `T_PMT_04` is leg-B only and guards for it explicitly.

**Which means the family's real-playback coverage is entirely outside the
registry**, in the two standalone scripts (§7) and in `T_PMT_04` — and the
registry ids that *say* they cover it (`T_PLR_13`'s plan row, "browser paging
never stalls audio") do not.

This is not the same failure as WP-D's. There the Spotify scope never had a
playback oracle to lose. Here the oracle exists, is cheap (`get plCount` reports
`playing`, `curRow`, `fileOpen` and `lfb8` in one line, `localPlayerApp.cpp:418-429`),
and is simply not used by 28 of 31 bodies — because the debug surface ADR-059 D12
added made it unnecessary for the 20 behaviours that genuinely do not need audio.
That trade was correct. What it did not license is `T_PLR_13` inheriting a
playback claim it never implements, and `T_PLR_25` staying in a registry that
only runs it where it cannot work.

---

## 7. The duplicate bodies — `T_PLR_13` and `T_PLR_25`

Both ids have **two** executable bodies: one in `player.py`, dispatched by
`run/test`; one standalone, dispatched by `run/browser-player` and
`run/playorder-player` and, as separate cells named `T_PLR_13_playback` /
`T_PLR_25_playback`, by leg B of `run/player-gate` (`run/player-gate:548-549`).
WP-A finding **A-15** identified the pair; this section answers whether one can
pass while the other fails, and which body should survive.

### 7.1 `T_PLR_13` — the registry body is a proper subset

| | `player.py:783` (registry, leg A) | `test_fbrowser_player.py` (leg B) |
|---|---|---|
| Env | `cyd2usb_winamp_debug` | `cyd2usb_player` (`-DDISABLE_SPOTIFY`) |
| Audio | **none started** | real track playing throughout (`:197-221`) |
| Assertions | `pending is False` within 15 s (`:805-814`) | `reason == "notfound"` on a nonexistent path *before* playback (`:167-174`); `plLoad` ok; `plPlay` ok; `playing` true within 15 s; `fbOpen` ok; walk finishes within 20 s; `playing` never false at any sample during the walk; `playing` still true after (`:238-261`) |
| Fixture-vs-defect | `sdls` probe → skip or fail (`:753-766`) | `_diagnose_fbopen` → `sdls` probe **plus** the firmware's own `reason`/`free8`/`largest8` fields, and always a `fail()` (`:104-147`) |
| Reboot | not detected | hard FAIL on `ets Jul`/`rst:0x`/`abort() was called`, deliberately not retried (`:50`, `:281-289`) |
| Reporting | `pass_`/`fail`/`skip` into the shared `RESULTS` | `sys.exit(0/1)`; the gate maps the whole script to one PASS/FAIL cell (`run/player-gate:508-522`) |

**Can one pass while the other fails? Yes, in both directions.** The registry body
passes on any board where the walk completes, including one that cannot decode a
single frame — it never asks. The standalone body fails on a pump-starving
regression the registry body is structurally blind to, because only it samples
`plCount.playing` *inside* the walk loop. Conversely the standalone body fails on
conditions the registry body would skip or never reach — `plLoad` failing,
playback not starting, a reset — and it fails rather than skipping in every one
of those cases.

**Which is stronger: the standalone body, by a wide margin.** It is not merely
the registry body plus audio; it is a better-engineered test on four independent
axes — it negative-tests its own diagnostic before relying on it (`:166-174`,
BP-068: *"if this ever reports `nomem`, the reason field is not discriminating
and every 'fixture missing' claim below it is worthless"*); it deliberately
claims the browser's 5 120 B arrays while the heap is healthy so the later
failure is deterministic rather than alternating between `allocfail` and `nomem`
(`:175-182`); it treats a reset as a defect rather than a transient, with the
reasoning for the policy change recorded (`:20-30`); and it refuses an in-process
retry because a soft reconnect lands inside the ESP32 double-reset-detector
window and reproduces the same stuck state (`:290-299`, DUT-measured). Its one
weakness is the gate contract: the whole script is one cell, so a failure names
the script, not the assertion.

**Recommendation.** Keep both, but stop pretending they are one id. The registry
body's unique content — the `sdls` fixture/defect discrimination and the "walk
completes without a WDT on a Spotify-resident build" liveness check — is real and
cheap, and `T_PLR_15` already covers `pending` clearing. Re-register it under its
own id (`T_PLR_13a`, "walk completes on leg A") with the plan row rewritten to
drop the audio claim, and let `T_PLR_13` name the standalone body alone. If only
one survives, it is the standalone.

### 7.2 `T_PLR_25` — the bodies are near-identical, and the registry one is the broken copy

| | `player.py:1526` (registry) | `test_playorder_player.py` (leg B) |
|---|---|---|
| Env guard | **none** | run only via `run/playorder-player`, which flashes `cyd2usb_player` |
| Shuffle/repeat setup | `_pl_shuffle(False)` / `_pl_repeat(True)`, tapping `coords.tap_shuffle()` / `tap_repeat()` — **parsed** from `gen/skin_layout.h` (`coords.py:86-93`) | `cmd(ser, "tap 187 96")` / `"tap 225 96"` — **literals**, with `# SHUFFLE_X/Y centre, see gen/skin_layout.h` (`:138`, `:144`). Both happen to equal the parsed values today (verified: `tap_shuffle()` → `(187, 96)`, `tap_repeat()` → `(225, 96)`) |
| Count check | none — `count == 0` skips, any other count proceeds | `count != 5` → **fail** (`:126-128`) |
| Start check | `plPlay ok`, then `playing` (row not checked) | `plPlay ok`, then `playing **and** curRow == 0` (`:159`) |
| Oracle | `played_rows == [0,1,2,3,4]` and stop after row 4 within 60 s | identical, with a per-track budget (`5 × 15 s`) |
| Reboot | not detected — a crash-reboot mid-run surfaces as a `TimeoutError` from `dut.cmd` | hard FAIL with a distinct message and an `addr2line` instruction (`:224-232`) |
| Failure vocabulary | `skip` on missing fixture, `fail` otherwise | `fail` on everything, including a missing fixture |

The two bodies assert the **same** thing. The difference is entirely in the
guards around it, and the standalone body wins every one of them: it verifies the
fixture count, verifies the *row* and not just the flag, distinguishes a reset
from a timeout, and states the remedy for each failure class.

**Can one pass while the other fails? Not meaningfully — they cannot both run.**
The registry body is dispatched only on leg A, where it cannot pass; the
standalone body only on leg B, where it can. That is the whole finding: this is
not a redundant pair, it is one working test and one copy stranded on the wrong
build.

**Recommendation: the standalone body survives.** Delete `t_plr_25` from
`player.py`'s `TESTS` and register `T_PLR_25` as the standalone cell only — the
shape `T_AE_04` already has (WP-B **B-13**), and the shape the gate's pass set
already assumes by naming `T_PLR_25_playback` on leg B and omitting `T_PLR_25`
from leg A. Before deleting, port the two things the registry copy does better:
`coords.tap_shuffle()`/`tap_repeat()` instead of the literals, and
`_pl_shuffle`/`_pl_repeat`'s bounded convergence loops instead of the open-coded
`for _ in range(3)` / `range(4)`. And fix `T_PLR_25`'s arena leak (**E-7**) in
whichever body survives.

---

## 8. What `run/player-gate` actually gates

In plain English, for a reader who has just seen `GATE PASS` scroll past.

### 8.1 What a green leg does prove

* **Every declared cell in the pass set ran and produced the declared result.**
  The comparison is per id against `player-gate-baseline.md`, not against a count
  — the file's own §1 says why (*"'>=3 runs' without the identity of what passed
  is the exact failure TASK-488 hit"*). A cell that FAILs, that degrades from a
  declared PASS to a SKIP, that goes MISSING, or that never ran (`NOT-RUN`) all
  set rc=1 (`run/player-gate:176-198`).
* **A missing SD fixture is a regression, not a skip.** This is the important
  one, and it is the opposite of what the family's bodies would suggest. Thirteen
  leg-A cells `skip()` when their fixture is absent (**E-1**), but the pass set
  declares them `PASS`, and `PASS:SKIP` falls to the `*)` branch → `REGRESS`
  (`:195-197`). So inside the gate the S7 skips of §2 and §4 are caught; it is
  only outside it that they read green.
* **Both legs ran at the same commit, each with its own build**, and each leg's
  ELF-hash guard checked the binary actually on the device (`:454-475`, `:485-486`).
* **Each leg carried at least one genuinely cross-mode cell.** Enforced at run
  time with exit 2, not by convention (`:221-238`), and negative-tested
  (`:370-377`).
* **The comparator itself is negative-tested.** `--selftest` runs 20 host-only
  cases against the real functions — including the exact TASK-573 regression
  (`FLAKY-PASS` parsed whole, not as a `FLAKY` fragment) and the exit-4-leg
  inversion (`:299-377`). A gate with its own negative tests is rare in this repo
  and worth saying so.

### 8.2 What a green leg does **not** prove

* **It does not prove the two standalone playback scripts asserted anything
  in particular.** Each whole script is one cell: exit 0 → PASS, anything else →
  FAIL (`:506-522`). The gate cannot tell "walked 200 entries with audio
  continuous" from "walked them with the `min_playing_seen` sample loop never
  executing"; there is no per-assertion output to parse. Two of leg B's five
  cells are opaque in this way.
* **It does not gate `T_PLR_25` at all on leg A** — the id is absent from
  `_DEFAULT_A` (`:84-87`) and from the pass set (`player-gate-baseline.md:94-96`),
  which is correct given **E-2** but means the gate is green while the registry
  cell is permanently red in `run/test`.
* **It does not gate `T_PLR_18`'s negative assertions**, or `T_PLR_19`'s. Those
  are `LOG_D` scans whose *absence* is the pass (**E-6**); the gate sees a PASS
  either way.
* **A leg can pass while covering less than the pass set implies.** `T_PLR_09` is
  a declared `SKIP` — a legitimately declared non-result, but a cell that
  contributes no coverage while contributing a green line. `T_PMT_00`'s
  "surface relocated" branch is a SKIP against a declared PASS, so *that* one
  does regress; `T_PLR_09` does not, by design.
* **Its HEALTH machinery is unreachable.** The gate refuses `DUT_HEALTH=warn|skip`
  (`:110-124`), maps a leg exiting 4 to "the board was not a valid subject"
  (`:495-502`), and self-tests both. But `_run_runner_leg` invokes
  `suite/serialdbg/runner.py` **without `--class-order`** (`:485-486`), and
  `runner.py:378` computes `_gate_on = args.class_order and not args.dut_health`
  — so no HEALTH phase runs, `health_fail` is never passed to `print_results`,
  and exit 4 cannot be produced. A gate run today asserts nothing about whether
  the board was a fit subject; it only knows the tests answered. **E-13**.
* **`PARTIAL PASS` is not `GATE PASS`, and the distinction is one line of
  output.** Any reduced id set, `SKIP_SCRIPTS=1`, a single leg, or
  `ALLOW_NO_CROSSMODE=1` downgrades the verdict (`:578-593`) — correctly, but a
  reader grepping for "PASS" finds it in both.

**The one-sentence version.** A green `run/player-gate` proves that, at this
commit, on two builds, every named LocalPlayer cell produced the exact result
someone declared in advance — including that the SD fixtures were present and the
mode/order/browser/mask surfaces behaved; it proves nothing about whether audio
actually played correctly beyond two opaque pass/fail scripts, nothing about the
board's fitness as a subject, and nothing about `T_PLR_25`.

---

## 9. Family findings

Severity per rubric §4.3: **P1** the test is counted as coverage but provides
none; **P2** materially weaker than claimed; **P3** hygiene.

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **E-1** | **P2** | **The family's fixture oracle cannot tell a missing fixture from a broken load, and three different bodies react to it three different ways.** `_pl_load` issues `set plLoad` and **discards the reply**, returning only `get plCount`; `count == 0` is then read as "fixture not on the card". But `set plLoad`'s own `ok` field is the one thing that discriminates (`cmdSet.cpp:197-199`), and `count == 0` is also the honest answer when the index is not allocated because the mode is not resumed — `cmdGet.cpp:629-633` states that explicitly. Six ids `skip()` on it (`T_PLR_08/09/10/20/21/22/23/24`), `T_PLR_12` and `T_PLR_16` `fail()` on the same condition, and `T_PLR_11`'s skip branch is unreachable (**E-16**). A `_enter_player` that returned True while the mode did not actually resume reads as "the card is missing files". | `player.py:423-426`; skips at `:435-437`, `:467-469`, `:554-557`, `:1276-1278`, `:1320-1322`, `:1387-1389`, `:1429-1431`, `:1486-1488`; fails at `:711-713`, `:924`; `cmdSet.cpp:197-199`; `cmdGet.cpp:629-633` | Return the `plLoad` reply from `_pl_load` and branch on it: `ok:false` → `skip` (fixture), `ok:true` with `count == 0` → `fail` (load or resume defect). One helper edit fixes all nine call sites. `set fbOpen` already has the discriminating `reason` field (`cmdSet.cpp:305-322`); give `plLoad` the same treatment. |
| **E-2** | **P1** | **`T_PLR_25` is a deterministic 60-second false red on the only env it is dispatched on, and the family's own gate routes around it.** Local playback cannot start on `cyd2usb_winamp_debug` (TASK-425/431 — asserted three times inside this very file), `set plPlay` returns `ok:true` regardless because it means "row index valid", and the body has no variant guard — unlike `T_PLR_09` (documented skip + flip trigger) and `T_PMT_04` (`get variant` leg guard). Every `run/test`, every `--scope LocalPlayer`, every `--tests T_PLR_25` burns 60 s and reports `row sequence [0] != [0,1,2,3,4]`. The gate stays green only because leg A's list omits the id. | `player.py:1526-1585`, no guard; `:493-505`, `:788-790`, `:1780-1783` (the constraint); `cmdSet.cpp:211-213` (`plPlay ok` semantics); `run/player-gate:84-87`; `player-gate-baseline.md:94-96` | Delete `t_plr_25` from `TESTS` and let the standalone body own the id (§7.2) — the shape `T_AE_04` and the gate's own pass set already assume. If it must stay in the registry, copy `T_PMT_04`'s `get variant` guard verbatim (`player.py:1803-1809`). |
| **E-3** | **P2** | **All three of this family's flake declarations and flake call sites are mismatched — in both directions.** `flaky.yaml:112` declares `T_PLR_17` and `:130` declares `T_PMT_04`, but **neither body ever calls `flake()`** — both use `fail()` — so `run_with_flake_retry` never fires, no mandated retry happens, and the declarations (with owners, tasks and `review_by` dates) buy nothing. Conversely `T_PLR_07` **does** call `flake()` and is **not** declared, so `lib/results.flake()` converts it to `FAIL: UNDECLARED flake — no entry for T_PLR_07 in flaky.yaml`, i.e. a declared-PASS gate cell whose failure message is about bookkeeping rather than about TLS. New instance of WP-C **C-7**. | `flaky.yaml:112-129`, `:130-145`; `player.py:335` (the only `flake()` in the module); `lib/results.py:177-199`, `:205-233` | Either make `T_PLR_17`/`T_PMT_04`'s failure paths call `flake()` so their declarations do something, or delete the declarations; and declare `T_PLR_07` (with the split-read race named as the suspected cause) or fix **E-10** and make it a plain `fail()`. |
| **E-4** | **P3** | **Three `playerMode` restores default to a value that silently rewrites the mode.** `dut.cmd(f"set playerMode {r_pm0.get('val', 0)}")` — if the entry `get playerMode` reply was lost, the restore writes mode 0 rather than restoring. Identical to WP-C **C-12**'s `T_TBFB_03` line, three more times, and `playerMode` is persisted. | `player.py:76`, `:130`, `:159` | Read into a variable, `skip()` if the field is absent, never default a restore to a value that looks like a success. |
| **E-5** | **P2** | **The two capability-mask ids that drive Spotify and WebRadio are scoped `LocalPlayer`, so `--scope Spotify` and `--scope WebRadio` miss them.** `T_PLR_17` taps Spotify's sprites and waits on `spotifyTask`'s dequeue trace; `T_PLR_18` enters WebRadio and asserts its mask. Both carry the module-seeded `scope=LocalPlayer`. The `@meta(scope=…, scope_reason="cross-mode")` mechanism that fixes this is used 30 lines away by `T_PMT_01`/`T_PMT_02` for exactly this situation. Compounded by the **filed** `T_PLR_17`/`18` spec-vs-runner swap, which makes every citation of either id ambiguous. | §0's command output; `player.py:1750`, `:1757` (the mechanism used correctly); `test_plan.md:413-424` (the swap, cited not re-derived); `test_plan.md:508` | Add `@meta(scope="Spotify", scope_reason="cross-mode")` to `t_plr_17` and `@meta(scope="WebRadio", …)` to `t_plr_18`. Settle the 17/18 swap separately — it spans an Architect-owned doc. |
| **E-6** | **P2** | **Four negative log assertions cannot distinguish "no leak" from "no logging", and cost 32 s a run.** `T_PLR_18` and `T_PLR_19` each call `_wait_for_log(dut, "dequeued action=SHUFFLE"/"…=REPEAT", timeout_s=8.0)` twice and treat `False` — the timeout — as the pass. The marker is a `LOG_D` line and `logLine()` drops below-`minLevel` lines unless the tag is kept (`logSink.h:119-123`), so on a board whose log level is raised these four checks pass vacuously and silently. The comments call the 8 s "generous — this is a NEGATIVE check, more time only strengthens it", which is true of timing and false of level gating. Same underlying fact as WP-C NEEDS-DUT #7 and WP-D §8.8, but with the polarity that hides rather than reveals. | `player.py:1104`, `:1114`, `:1167`, `:1181`; `:974-986` (`_wait_for_log`); `logSink.h:116-123`; `spotifyTaskStorage.cpp:420` | Assert the level first: read the current `logMinLevel`/keep-prefix (or issue the `set` that guarantees debug lines) at the top of each body and `skip()` if the marker class is suppressed. A negative assertion on a suppressible channel must prove the channel is open before it can mean anything. |
| **E-7** | **P2** | **New state-leakage cluster: the arena (`C8`).** `T_PLR_25` plays five real tracks and does **not** release the arena on its way out through `_leave_player()`, whereas `T_PMT_04`'s own exit does (`releases 0→1`). `mb_arena_acquire()` early-returns on `if (s_owned) return true;` *before* incrementing, so a later acquire in the same boot is invisible by design — which is exactly how `T_PMT_04` produced a false regression when run behind `T_PLR_25` (TASK-553). Adjudicated `EDGE` for `T_PMT_04` in `_order.py:194`, but the *leaker* is not named anywhere and the cluster is not in WP-B §5.2's six. | `player.py:1576-1577` vs `:1938-1959`; `mem/arena/mb_arena.cpp:106`, `:134-147`; `player-gate-baseline.md:98-111`; `test_plan.md:474` ("**Secondary finding worth its own look**: `T_PLR_25` leaves the arena held after `_leave_player()`") | Release on exit from the playing body (a `set plPlay`-stop or an explicit mode exit before `_leave_player`), and add `C8 — arena ownership` to WP-B §5.2 with `T_PLR_25` as the mutator and `T_PMT_04` as the reader. |
| **E-8** | **P1** | **Two ids assert behaviour that cannot regress.** `T_PLR_02` claims reboot persistence and reads back its own write through the same stored byte, with the reboot handed to a human in the docstring; what is left is `T_PLR_04`'s declared subject, asserted there better. `T_PLR_03` claims "no leaked taskbar slot for WebRadio or LocalPlayer" and probes two scroll offsets at which `appIdx = offset % 11` is 5 and 10 — WebRadio (11) and LocalPlayer (12) are outside the modulus, and `resolvePlayerTap` only remaps `AppId::Spotify`, so the asserted failure is unrepresentable; the leak class is closed by three `static_assert`s anyway. Both are counted as coverage (both are declared `PASS` in the gate's pass set) and neither can fail for the reason it exists. | `player.py:70-80`, `:61-65`; `player.py:103-111` vs `cmdTouch.cpp:29-31`, `appShell.cpp:76-77`, `test_plan.md:504`; `player-gate-baseline.md:61-62` | `T_PLR_02`: either give it a real reboot (the idiom is at `player.py:1610-1612`) or retire it into `T_PLR_04` and record the merge, the way `T136` should have been (WP-D **D-4**). `T_PLR_03`: keep the 12-offset crash sweep, drop the unrepresentable leak assertion, and replace it with a positive one — assert each probed offset resolves to the *expected* app, which is the `T-SET-02` shape and would catch a renumbering. |
| **E-9** | **P2** | **`T_PMT_00`, "THE binding test", asserts two string literals and a change of unspecified direction.** `op == "playerCycle"` and `region == "TASKBAR_SLOT"` are compared against a fixed `Serial.printf` in `cmdGet.cpp` — WP-D **D-1**'s shape. The behavioural half is only `after != before`, so a cycle landing on the wrong mode passes; `_PMT_EXPECT` and `playerModeNext`'s successor are both available. And the relocation regression the id exists for exits as `skip()`. | `player.py:1723-1747`; `cmdGet.cpp:612-618`; `player.py:1643-1647`; `appShell.cpp:83-85` | Assert the successor, not merely a change: `after == playerModeNext(before)`, using `_PMT_EXPECT`'s table. Leave the `playerBind` string comparison — it is the intended tripwire for the one-edit contract — but stop counting it as behavioural coverage. |
| **E-10** | **P2** | **`T_PLR_07` uses the split-read pattern `_tap_and_wait_log` exists to remove, 90 lines below a body in the same file that uses the helper for the identical marker.** `dut.cmd(tap)`'s `read_json` discards non-JSON lines while hunting the tap reply, and `"hard reset — stopping client"` is printed from a different FreeRTOS task; the race is documented from a raw serial capture. The consequence is then routed through an undeclared `flake()` (**E-3**). | `player.py:323-335` vs `:220`; `_helpers.py:20-65`; `lib/dut.py:1079-1091`; `spotifyTaskStorage.cpp:363` | `r, seen = _tap_and_wait_log(dut, lgx, lgy, "hard reset", log_timeout=8.0)` — a two-line change, and `T_PLR_06` is the working template. |
| **E-11** | **P2** | **`T_PLR_18` reaches WebRadio by accident and only because of what ran before it.** `_switch_to(dut, "WebRadio")` taps `tap_taskbar_slot(11)` → y=460 → `slot=11` → `appIdx = 11 % 11 = 0`, i.e. the **player** slot; it lands on WebRadio only because `T_PLR_17` left the board on Spotify, so `resolvePlayerTap` takes the cycle branch. `webradio.py:30-33` says outright that this helper "tap[s] a taskbar slot WebRadio doesn't have" and names `_switch_to_webradio_capture_heap` as the correct entry — which `T_PLR_06` uses. Run alone, or after any non-player app, the same tap *restores* the persisted mode and the id skips. Not in `_order.py`'s `EDGE_ADJUDICATION`; invisible to `edge_candidates()` for the reason WP-B **§5.4** gives. | `player.py:1084-1086`; `_helpers.py:321-331`, `:400`; `coords.py:184-188`; `cmdTouch.cpp:29-33`; `appShell.cpp:76-86`; `webradio.py:30-33`, `:346-378` | Use `_switch_to_webradio_capture_heap` (already imported into this module at `player.py:25`), and add the id to `EDGE_ADJUDICATION` if the dependence is kept. |
| **E-12** | **P3** | **`T_PLR_13`'s only assertion is a strict subset of `T_PLR_15`'s.** Both open `_FB_BIG` and poll `fbState`; `T_PLR_15` asserts `pending` true immediately *and* false after, `T_PLR_13` asserts only the second half plus a 15 s bound on a ~5 s walk. Two full 200-entry walks per run for one and a half assertions. | `player.py:805-814` vs `:895-904` | Fold the timing bound into `T_PLR_15` and re-purpose `T_PLR_13` per §7.1, or retire the registry body outright. |
| **E-13** | **P2** | **`run/player-gate`'s HEALTH machinery cannot fire.** The script refuses `DUT_HEALTH=warn\|skip`, maps a leg's exit 4 to "the board was not a valid subject", and negative-tests both — but it invokes `runner.py` without `--class-order`, and `runner.py` computes `_gate_on = args.class_order and not args.dut_health`, so no HEALTH phase runs and `print_results` is never given `health_fail`. Exit 4 is unreachable on this path. The gate therefore emits PASS/REGRESS without ever having established that the board was a fit subject — the premise its own §18.2 refusal exists to protect. | `run/player-gate:110-124`, `:485-486`, `:495-502`, `:345-366`; `runner.py:376-381`, `:455-462`; `lib/results.py:251-260` | Pass `--class-order` (accepting the order switch, currently HELD) or add a `--health-phase`-only flag to `runner.py` so the gate can require the HEALTH class without adopting class ordering. Until then, say so in the gate's banner rather than in a comment. |
| **E-14** | **P3** | **The gate's log parser sees a `FLAKY-PASS` id twice.** `print_results` prints each id once in the results block and then, for declared flakes, again under "Declared flakes" with the same `  <id>: <status>` shape; `_parse_runner_log`'s `sed` matches both. The declared-cell comparison uses `awk … exit` and is unaffected, but the unbaselined loop iterates the observation file and would emit a duplicate `flaky`/`unbaselined` line. Cosmetic today; it is also a second, unenumerated coupling to an unspecified summary format — WP-A **A-7**'s subject. | `lib/results.py:270-283`; `run/player-gate:161-163`, `:203-216` | Deduplicate in `_parse_runner_log` (`awk '!seen[$1]++'`), and specify the summary line format the two parsers share. |
| **E-15** | **P3** | **The family restores almost nothing it toggles.** `T_PLR_17`/`18`/`19` leave shuffle and repeat toggled (17 in Spotify, where the taps also enqueued two real `ACT_*` actions); `T_PLR_16` exits with the file browser still open on `/` — `T_PLR_06` is the only body that calls `set fbCancel`; `T_PLR_20`–`24` leave shuffle on; `T_PLR_03`'s and `T_PLR_18`'s failure paths leave an arbitrary app and a non-zero `tbScrollOffset`. Only `T_PLR_26` resets shuffle/repeat, and only because its own post-reboot assertion needed a clean state. 17 of the 31 rows carry S14. | `player.py:295` (the only `fbCancel`); `:1623-1624` (the only shuffle/repeat restore); `:110-111`, `:1127-1131` (fail paths without restore) | A `finally`-based `_player_state_restored()` context manager alongside `_bgpoll_suspended` (`_helpers.py:444-454`), restoring shuffle, repeat, browser and app. |
| **E-16** | **P3** | **`T_PLR_11`'s fixture-missing skip is unreachable.** The guard is `if r.get("count", 0) == 0 and not r.get("ok")`, but `get plCount` is `dbgReport()`, which prints `"ok":true` unconditionally, so the second clause is never satisfied. A genuinely absent `bad.m3u` falls through and fails with `count=0 (expected 8)` — louder than the sibling behaviour, but by accident, and the branch is dead. | `player.py:605-608`; `localPlayerApp.cpp:418-422` | Subsumed by **E-1**: once `_pl_load` returns the `plLoad` reply, gate on that instead. |

---

## 10. Counts

| Verdict | `T_PLR_01`–`07` | `T_PLR_08`–`16` | `T_PLR_17`–`19` | `T_PLR_20`–`26` | `T_PMT_00`–`04` | **Total** |
|---|---|---|---|---|---|---|
| SOUND | 4 | 8 | 2 | 6 | 4 | **24** |
| WEAK | 1 | 1 | 1 | 0 | 1 | **4** |
| HOLLOW | 2 | 0 | 0 | 0 | 0 | **2** |
| BROKEN | 0 | 0 | 0 | 1 | 0 | **1** |
| **total** | **7** | **9** | **3** | **7** | **5** | **31** |

* **HOLLOW:** `T_PLR_02`, `T_PLR_03`.
* **BROKEN:** `T_PLR_25`.
* **WEAK:** `T_PLR_07`, `T_PLR_13`, `T_PLR_18`, `T_PMT_00`.

Smell histogram (84 occurrences across the 31 rows; a row may carry several):

| Code | Smell | Count |
|---|---|---|
| S14 | State leakage | 17 |
| S7 | Skip-as-pass | 13 |
| S9 | Fixed-sleep synchronisation | 10 |
| S13 | Overlap | 10 |
| S10 | Magic value | 8 |
| S8 | Vacuous bound | 7 |
| S12 | Wrong-id / mis-scoped record | 5 |
| S3 | Tautology | 3 |
| S6 | Defaulting oracle | 3 |
| S2 | Ack-not-effect | 2 |
| S4 | Deferred to a human | 2 |
| S5 | Swallowed failure | 2 |
| S1 | Unconditional pass | 1 |
| S11 | Double bookkeeping | 1 |

Four shifts against WP-C's and WP-D's histograms are properties of this family
rather than of the sample, and they are the package's headline:

* **This is the best-graded family so far — 77 % SOUND against WP-C's 59 % and
  WP-D's 56 % — and the reason is the debug surface, not the authors.** ADR-059
  D12 gave the play-order engine exact observables (`get plOrder`, `get plCursor`,
  `advance`'s `moved`/`row`/`reshuffled`), and the seven ids built on them assert
  exact permutations and exact triples. Where WP-D found proxies and resting
  states, this family compares device-computed values against device-computed
  values. The lesson generalises: **the quality of a test tracks the quality of
  the observable it was given**, and this is the one family where someone
  designed the observable first.
* **S14 is the dominant smell (17 of 31), where WP-D's was S7.** The failure mode
  has moved again: WP-C's was *a failure that does not block*, WP-D's was *a test
  that does not run*, and this family's is *a test that changes the board and
  leaves it changed*. It matters more here than elsewhere because two of the
  leaked quantities are persisted (`playerMode`, shuffle/repeat) and one is a
  16 KB heap allocation (**E-7**), which is how TASK-553 became a false
  regression.
* **S7 is still 13 of 31, but its character is different.** Every skip in this
  family is a *fixture or variant* precondition, not an account or a queue — and
  inside `run/player-gate` a declared-PASS cell that skips is a REGRESS (§8.1).
  So the S7 surface here is real coverage loss in `run/test` and caught coverage
  loss in the gate. That is the first family where the two entry points disagree
  in the safe direction.
* **Zero dead markers.** Every log string and `get` key in the family resolves in
  `app/src/` — the first family audited of which that is true. The problem is not
  markers that were never printed but four negative assertions on a channel that
  can be switched off (**E-6**).

---

## 11. NEEDS-DUT

Static reading cannot settle these. Each is stated as the question hardware would
answer.

1. **E-6 — is the `LOG_D` channel actually open during a suite run?** `T_PLR_18`
   and `T_PLR_19`'s four negative assertions pass silently if it is not, and
   `T_PLR_17`'s positive ones fail loudly. Read `logMinLevel`/keep-prefix at the
   point those ids run, in a full `run/test`, not in isolation. One answer also
   closes WP-C NEEDS-DUT #7 and WP-D NEEDS-DUT #8.
2. **E-11 — does `T_PLR_18` skip when run alone?** `./run/test-targeted T_PLR_18`
   from a cold boot (board on Spotify, `playerMode` whatever the boot restored)
   versus `T_PLR_17,T_PLR_18`. If the isolated run skips, the id has never been
   independently verifiable and the pass set's `A | T_PLR_18 | PASS` row is an
   artefact of ordering.
3. **E-2 — confirm `T_PLR_25`'s leg-A failure is deterministic and not
   environmental.** `./run/test-targeted T_PLR_25` on the current debug build:
   the prediction is `FAIL: row sequence [0] != [0,1,2,3,4]` after ~60 s, every
   time. If it ever passes, TASK-425/431's constraint has moved and three
   comments in `player.py` are stale.
4. **E-7 — how far does the arena leak reach?** Run `T_PLR_25` then `T_PMT_04`
   on leg B, versus `T_PMT_04` alone from a fresh boot. TASK-553 measured the
   symptom; what is not measured is whether anything *between* them is affected —
   `T_PLR_26`'s reboot sits in between in registry order and would clear it, but
   only on a leg that runs both.
5. **`T_PLR_12`'s ±256 B residual tolerance.** A 256 B window across two app
   switches and a 3 s settle is tight. Is it stable over five consecutive runs on
   a settled board (>150 s post-reset, per TASK-425's heap-settle rule), or is
   this a latent flake nobody has attributed because the id usually runs early?
6. **`_pmt_edge`'s 2.5 s settle and `srcName`.** Does `pleditLastSrcKind()`
   reliably reach the expected value within `_PMT_SETTLE_S` on all three
   transitions, including into Spotify with an empty queue under TASK-243? A
   false FAIL here would look like an M5 regression.
7. **E-13 — does adding a HEALTH phase to the gate change any verdict?** Run
   `run/player-gate` with the runner given a health phase and compare. The
   question is whether the board has ever been silently unfit during a recorded
   gate run.
8. **§7.1 — does the standalone `T_PLR_13` body's `min_playing_seen` loop
   actually execute?** Its samples are inside `while … pending is False: break`;
   on a fast walk the loop may break on the first iteration having sampled
   `plCount` once. If so, "playback continuous throughout" rests on one sample
   and the gate's opaque PASS is weaker than §7.1 credits it.

---

## 12. Handover

* Findings that belong to WP-Z's consolidation rather than to this family:
  **E-2** (a registry cell that can only fail on its own env, and a release gate
  built to route around it), **E-3** (the flaky-declaration/call-site mismatch,
  a third instance of WP-C **C-7**'s class and the first in both directions),
  **E-7** (a new state-leakage cluster, `C8`, for WP-B §5.2's table), and
  **E-13** (a gate whose health premise cannot be established).
* Cross-references to prior packages, cited not re-derived: **E-8**'s `T_PLR_03`
  is WP-C **C-15**'s sampling shape and WP-D **D-1**'s tautology shape;
  **E-4** is a third instance of WP-C **C-12**; **E-3** extends WP-C **C-7**;
  **E-6** is the negative-polarity half of WP-C NEEDS-DUT #7; **E-11**'s
  invisibility to `edge_candidates()` is WP-B **§5.4**; `T_PMT_04`'s `bgPoll`
  leak is WP-B **B-6**; `T_PLR_26`'s reboot is WP-B cluster **C6**; §7 answers
  WP-A **A-15**; §8 audits the parser behind WP-A **A-7**.
* Cited from the plan rather than re-derived: the `T_PLR_17`/`18` spec-vs-runner
  swap (`test_plan.md:413-424`) and the vacuity of `T_PMT_03`'s `arenaHeld`
  clause (`test_plan.md:473`). Both were already known and filed; this package
  adds only the scope consequence (**E-5**).
* The structural contrast worth carrying forward. WP-C: *a failure that does not
  block*. WP-D: *a test that does not run*. WP-E: **a test that is well built
  because someone built its observable first** — and, in the same family, *a test
  left in a registry that can only run it where it must fail*. The `T_PLR_20`–`24`
  block and `T_PMT_04` are the strongest evidence in this review that the suite's
  quality problem is a design problem upstream of the tests, not a discipline
  problem in them.
* Nothing under `app/` or `run/` was modified. Nothing under `app/tools/` was
  imported except `suite.serialdbg.build_all_meta`. `./run/check-docs` was run
  once before handover; the C6 result is recorded in the index ledger entry for
  this package.
