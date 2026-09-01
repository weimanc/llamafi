# Adjudication — masked-FAIL `skip()` sites in `app/tools/suite/serialdbg/`

**TASK-574** · Owner: @VE · Date: 2026-09-01 · Source adjudication only (no DUT was touched)
Scope: every `skip()` call site in `app/tools/suite/serialdbg/*.py` at this commit — **256 sites**
(the raw `grep -c "skip("` figure of 261 counts the `def skip` import/definition mentions and two
prose references in comments; 256 is the AST call-site count).

---

## 1. What was being asked

A prior @VE review found that the "other" bucket among these `skip()` sites contained assertions
that failed and were recorded as non-results — false greens, because a SKIP does not fail a run.
This document adjudicates every site into one of three buckets:

| Bucket | Meaning | Action |
|---|---|---|
| **A** | Genuine precondition — the test could not establish its starting state, and that state is not itself the thing under test. | Leave `skip()`. |
| **B** | Masked FAIL — an assertion about behaviour under test failed and was recorded as a non-result. | Convert to `fail()`, same message. |
| **C** | Ambiguous — readable either way, or converting would change what the test means. | Leave `skip()`, list for a human. |

The instruction was to bias hard toward A and C: a wrong B turns the suite red for a bad reason.

---

## 2. Verdict

| Bucket | Count |
|---|---|
| **A** — genuine precondition | **240** (of which 7 are "not applicable to an automated run": `T093`, `T094`, `T095`, `T171`, `T179` manual/interactive; `T136` retired; `T_PMT_04` leg-A build variant) |
| **B** — masked FAIL, converted to `fail()` | **0** |
| **C** — ambiguous, referred to a human | **16** |

**No code was changed.** No `skip()` was converted. That is the honest result of the adjudication,
and §3 explains why the two example shapes named in the task brief — `"drill-in did not fire"` and
`"lastPlaylistDraw did not advance"` — both turned out **not** to be safe conversions.

Because nothing was converted:

* no currently-green cell turns red;
* `player-gate-baseline.md`'s declared pass set is **unaffected** — no cell in `T_PLR_01`–`26` or
  `T_PMT_00`–`04` changed verdict semantics (the one player-gate site that looked like a candidate,
  `T_PLR_09`, is bucket C and left alone — see §3.3);
* `test_plan.md` needs no per-id "verdict semantics changed" note; the adjudication itself is
  recorded there instead.

---

## 3. Why the two flagged shapes are not conversions

### 3.1 `"lastPlaylistDraw did not advance"` — six sites, all C

Six tests (`T172`, `T182`, `T_MA_03`, `T_GOL_03`, `T_WX_03`, `T_CX_03`) end in
`_helpers.py::_check_residue()`, which records the PASS itself and returns `False` otherwise; the
caller then SKIPs. Five of the six have **no `pass_()` of their own at all** — they can only be
PASS or SKIP, never FAIL. That is exactly the false-green shape the review flagged, so this was the
strongest B candidate in the file.

It does not survive contact with the firmware. `get lastPlaylistDraw` returns
`PleditView::_lastDrawMs` (`app/src/winamp/winampDisplay.cpp:758`), and `PleditView::draw()`
(`app/src/winamp/pleditView.h:134-143`) only bumps it when the queue **seqno changes** or a scroll
repaint is pending:

```
if (!seqnoChanged && !_scrollDirty) return;
if (seqnoChanged && now - _lastDrawMs < PLAYLIST_DRAW_MIN_MS) return;
```

`SpotifyApp::resume()` does call `invalidatePlaylist()`, which forces exactly **one** repaint on the
first tick after the switch back. Every one of these six tests reads its baseline *after* that tick
has already had time to run (0.1–0.5 s of serial round-trips). So the 3 s observation window is not
watching "does Spotify repaint at all" — it is watching for the **next queue-snapshot seqno bump**,
and `seqno` is incremented only in `spotifyTaskStorage.cpp:230` on a successful queue poll (~60 s
cadence, and never while the account is 403-latched — TASK-243). The existing reason string
("Spotify not rendering (not playing?)") is therefore *substantially correct*, and converting these
to `fail()` would produce environment-driven reds.

**Recommendation (a separate task, not this one):** re-point the residue check at
`get pleditRepaints` — the monotonic full-repaint counter added for ADR-059 D12
(`app/src/winamp/pleditView.h:414`, exposed at `app/src/winamp/winampDisplay.cpp:749`). Sequence: read `pleditRepaints`, switch
back, assert the count advanced. That is playback-independent (the `invalidate()` in `resume()`
guarantees one repaint), and once it is, all six sites become unambiguous **B** and should be
converted. Four of the six additionally never verify that the switch-back landed (they fire a raw
taskbar tap and never check `appId`) — that check must be added in the same change or a missed tap
becomes a false red.

### 3.2 `"drill-in did not fire"` / `"did not enter chart view"` — A, except two

The suite already has a deliberate and consistent convention here: the transition is asserted with
`fail()` in the test that **owns** it, and skipped as setup everywhere else.

| Transition | `fail()` in (owner) | `skip()` in (setup) |
|---|---|---|
| row tap → chart | `T174` | `T175`, `T180`, `T181`, `T188`, `T204`, `T182`, `T177` |
| HEAT tap → heatmap | `T200` | `T202`, `T203`, `T192`, `T193`, `T194` |
| HEAT tap in heatmap → list | `T201` | — |
| tile tap → chart | `T202` | `T203`, `T192`, `T193`, `T194` |
| app switch liveness | `T_MA_01`, `T_GOL_01`, `T231` | `T_MA_02/03`, `T_GOL_02/03`, and the whole "could not switch to X" family |

That convention answers the brief's hard case directly: `"could not switch to <App>"` is a
precondition **everywhere it appears as a skip**, because the tests where app-switch liveness IS the
subject already fail on it. The two exceptions kept as C are `T178:396` (the drill-in is the test's
own action, but it is read after a deliberate 0.1 s race-the-fetch wait) and `_t18x_guard:781`
(`T186`/`T187`, where a regression of the tickerIdx guard could plausibly present as exactly this).

### 3.3 The C sites worth a human's time, in priority order

1. **`app/tools/suite/serialdbg/shell.py:1933` — `T-CDWN-02`.** The docstring calls the skipped condition the *primary
   assertion* ("second cmdTap returns `skipped:true`"). A regression of the `g_shellBusy` tap gate
   would hide here indefinitely. **Fix then convert:** assert `get shellBusy == true` between tap 1
   and tap 2; with that in place, "tap2 not skipped" has no innocent explanation left.
2. **`app/tools/suite/serialdbg/shell.py:1689` — `T-BUSY-01b`.** Its only assertion is "shellBusy=true after the 5D tab tap",
   and that condition is skipped. Same fix shape: prove the fetch was actually issued (the test
   already snapshots `fetchOkCount`) before judging the busy window.
3. **The six residue sites** (§3.1) — convert together with the `pleditRepaints` redesign.
4. **`app/tools/suite/serialdbg/shell.py:1391` / `app/tools/suite/serialdbg/shell.py:1504` — `T_WX_04` / `T_CX_04`.** "weatherReady/cryptoReady=true
   immediately" is the negation of the subject; the "network too fast" explanation is real but
   untested. Needs a discriminator (e.g. assert `*Ready==false` within one tick of `switchApp`).
5. **`app/tools/suite/serialdbg/player.py:507` — `T_PLR_09`.** Carries an explicit VE note that it must become `fail()` on
   `cyd2usb_player` once **TASK-443**'s ruling lands. TASK-443 was *withdrawn*; the successor
   **TASK-452** is OPEN, so the trigger has not fired and the SKIP stands. The in-code comment and
   the reason string still name TASK-443 and should be re-pointed at TASK-452 when someone next
   touches that file.
6. **`app/tools/suite/serialdbg/stock.py:1450` — `T194`.** Behavioural in shape, but TASK-385 explicitly designated this cell
   the suite's heap/queue-pressure canary and wired four diagnostic snapshots into the reason
   string. Whether pressure-induced non-advance is a product failure is a product call, not a
   verification one.
7. **`app/tools/suite/serialdbg/webradio.py:665` / `app/tools/suite/serialdbg/webradio.py:738` — `T_WR_HEAP_01` / `T_WR_HEAP_03`.** Instrumentation, not
   threshold: if the firmware stopped storing/emitting the heap figures, both cells green forever.
   Low priority, but they are real blind spots. (`T_WR_HEAP_03`'s message says 35 s while the call
   waits 65 s — a stale string.)
8. **`app/tools/suite/serialdbg/stock.py:396` / `app/tools/suite/serialdbg/stock.py:781`** — see §3.2.

---

## 4. Standing convention this adjudication establishes

For future test authors, the rule the suite already follows and which should now be written down:

> `skip()` is for the rig, a fixture, a build variant, an external service, or a starting state the
> test could not establish. `fail()` is for anything the test set out to observe. If a condition is
> the negation of the test's own docstring, it must be a `fail()` — and if it cannot be made
> reliably distinguishable from a race, the test needs a discriminator, not a `skip()`.

Applied to the C list, that rule says the eight items in §3.3 are all **test-design debt**, not
adjudication ambiguity: each one needs one extra assertion before its skip becomes an honest fail.

## 5. Full adjudication table

| # | Site (`file:line`) | Test id | Current reason string | Bucket | Justification |
|---|---|---|---|---|---|
| 1 | `app/tools/suite/serialdbg/_helpers.py:435` | `(_tb_precondition)` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 2 | `app/tools/suite/serialdbg/_helpers.py:438` | `(_tb_precondition)` | f"precondition: tbScrollOffset={_tb_get_offset(dut)} could not be reset to 0" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 3 | `app/tools/suite/serialdbg/planeradar.py:34` | `T_PR_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 4 | `app/tools/suite/serialdbg/planeradar.py:66` | `T_PR_02` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 5 | `app/tools/suite/serialdbg/planeradar.py:103` | `T_PR_03` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 6 | `app/tools/suite/serialdbg/planeradar.py:132` | `T_PR_04` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 7 | `app/tools/suite/serialdbg/planeradar.py:138` | `T_PR_04` | f"could not set prRange=25 pre-reboot, got {r_pre.get('val')}" | **A** | debug-surface setup could not establish the starting offset/state. |
| 8 | `app/tools/suite/serialdbg/planeradar.py:170` | `T_PR_05` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 9 | `app/tools/suite/serialdbg/planeradar.py:186` | `T_PR_05` | "could not establish a clean baseline poll within 90s" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 10 | `app/tools/suite/serialdbg/planeradar.py:207` | `T_PR_05` | "no fetch error surfaced in 20 rapid-fire attempts — " "adsb.fi rate limit not hit this run (network-dependent)" | **A** | external data/network availability — the test's inputs never arrived. |
| 11 | `app/tools/suite/serialdbg/planeradar.py:241` | `T_PR_06` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 12 | `app/tools/suite/serialdbg/planeradar.py:340` | `T_PRM_02` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 13 | `app/tools/suite/serialdbg/planeradar.py:357` | `T_PRM_02` | "first poll never resolved within 90s — no baseline" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 14 | `app/tools/suite/serialdbg/planeradar.py:436` | `T_PRI_01` | "could not switch to PlaneRadar" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 15 | `app/tools/suite/serialdbg/player.py:40` | `T_PLR_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 16 | `app/tools/suite/serialdbg/player.py:145` | `T_PLR_05` | "precondition: could not switch to Clock" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 17 | `app/tools/suite/serialdbg/player.py:203` | `T_PLR_06` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 18 | `app/tools/suite/serialdbg/player.py:300` | `T_PLR_06` | "Player leg: file-browser alloc failed under heap pressure after the " "Spotify+WebRadio legs fragmented the heap (LocalPlayerApp reported " "error=true, not a crash) — known M-HEAP-FRAGMENTATION-class risk, not " "an eject-verb defect; Spotify/WebRadio legs above already passed" | **A** | documented heap-fragmentation risk in the third leg of a three-leg test whose first two legs already passed; the reason string itself distinguishes it from an eject-verb defect. |
| 19 | `app/tools/suite/serialdbg/player.py:318` | `T_PLR_07` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 20 | `app/tools/suite/serialdbg/player.py:388` | `(_enter_player)` | "precondition: could not step off the player slot" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 21 | `app/tools/suite/serialdbg/player.py:411` | `(_enter_player)` | f"precondition: appId={name!r} (expected LocalPlayer, 2 attempts)" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 22 | `app/tools/suite/serialdbg/player.py:436` | `T_PLR_08` | f"fixture {_PL_GATE} not on the card (gen_playlist_fixtures.py) — reply={r}" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 23 | `app/tools/suite/serialdbg/player.py:468` | `T_PLR_09` | f"fixture {_PL_GATE} missing or short (count={r.get('count')})" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 24 | `app/tools/suite/serialdbg/player.py:507` | `T_PLR_09` | "track never reached playing=true — audio precondition failed, " "not a scroll result (check the card's /mp3 files). NOTE: this " "must become a FAIL on cyd2usb_player once TASK-443's ruling " "lands — see the comment above this call" | **C** | carries an explicit VE note (2026-08-15) that it must become fail() on cyd2usb_player once TASK-443's ruling lands. TASK-443 was WITHDRAWN; successor TASK-452 is OPEN, so the condition has not been met — left SKIP. The in-code note and message still name TASK-443 and should be re-pointed at TASK-452. |
| 25 | `app/tools/suite/serialdbg/player.py:556` | `T_PLR_10` | f"fixture {_PL_REL} not on the card (gen_playlist_fixtures.py)" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 26 | `app/tools/suite/serialdbg/player.py:606` | `T_PLR_11` | f"fixture {_PL_BAD} not on the card (gen_playlist_fixtures.py)" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 27 | `app/tools/suite/serialdbg/player.py:673` | `T_PLR_12` | "precondition: could not switch to Clock for the baseline" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 28 | `app/tools/suite/serialdbg/player.py:694` | `T_PLR_12` | "could not leave Player mode for the free measurement" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 29 | `app/tools/suite/serialdbg/player.py:799` | `T_PLR_13` | f"fixture {_FB_BIG} not on the card (TASK-408's probe fixture) — reply={r}" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 30 | `app/tools/suite/serialdbg/player.py:841` | `T_PLR_14` | "fixture /probe200/anchor.m3u not on the card" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 31 | `app/tools/suite/serialdbg/player.py:854` | `T_PLR_14` | f"g_shellBusy never observed true after eject — reply={busy}; " "walk finished before this could be checked" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 32 | `app/tools/suite/serialdbg/player.py:889` | `T_PLR_15` | f"fixture {_FB_BIG} not on the card" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 33 | `app/tools/suite/serialdbg/player.py:1020` | `T_PLR_17` | "precondition: could not restore Spotify app" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 34 | `app/tools/suite/serialdbg/player.py:1084` | `T_PLR_18` | "precondition: could not switch to WebRadio" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 35 | `app/tools/suite/serialdbg/player.py:1277` | `T_PLR_20` | f"fixture {_PL_20} not on the card (gen_playlist_fixtures.py + sd_put.py)" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 36 | `app/tools/suite/serialdbg/player.py:1321` | `T_PLR_21` | f"fixture {_PL_20} not on the card (count={r.get('count')})" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 37 | `app/tools/suite/serialdbg/player.py:1388` | `T_PLR_22` | f"fixture {_PL_20} not on the card (count={r.get('count')})" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 38 | `app/tools/suite/serialdbg/player.py:1430` | `T_PLR_23` | f"fixture {_PL_20} not on the card (count={r.get('count')})" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 39 | `app/tools/suite/serialdbg/player.py:1487` | `T_PLR_24` | f"fixture {_PL_20} not on the card (count={r.get('count')})" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 40 | `app/tools/suite/serialdbg/player.py:1540` | `T_PLR_25` | f"fixture {_PL_SHORT5} not on the card" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 41 | `app/tools/suite/serialdbg/player.py:1604` | `T_PLR_26` | "precondition: could not step off Player before reboot" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 42 | `app/tools/suite/serialdbg/player.py:1727` | `T_PMT_00` | f"playerBind region={region!r} — surface relocated; update this test " "(that is the design intent: ONE edit, here)" | **A** | build-variant / test-maintenance guard, not product behaviour. |
| 43 | `app/tools/suite/serialdbg/player.py:1801` | `T_PMT_04` | f"leg A (variant spotify={var.get('spotify')!r}) — local playback needs " f"cyd2usb_player (TASK-425/431/442). Run: DUT_ENV=cyd2usb_player " f"python3 -u tools/run_serialdbg_tests.py --tests T_PMT_04" | **A** | wrong build variant — local playback needs cyd2usb_player; the message names the exact re-run command. |
| 44 | `app/tools/suite/serialdbg/player.py:1809` | `T_PMT_04` | f"get arenaStats unsupported on this build: {base}" | **A** | build-variant / test-maintenance guard, not product behaviour. |
| 45 | `app/tools/suite/serialdbg/player.py:1835` | `T_PMT_04` | f"precondition: the arena is ALREADY held at baseline " f"(acquires={base_acq} active={base.get('active')} " f"hwm={base.get('hwm')}). mb_arena_acquire() is idempotent and does " f"not re-count, so the 0->1 edge this test asserts cannot be " f"observed. Something earlier in this boot acquired and did not " f"release — T_PLR_25 is the known one. Run it from a fresh boot: " f"NO_WIFI=1 DUT_ENV=cyd2usb_player ./run/test-targeted T_PMT_04" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 46 | `app/tools/suite/serialdbg/player.py:1854` | `T_PMT_04` | f"set plLoad {_PMT04_PLAYLIST} failed — SD fixture missing " f"(push it with app/tools/sd_put.py): {r}" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 47 | `app/tools/suite/serialdbg/player.py:1860` | `T_PMT_04` | f"plCount={c.get('count')} after loading {_PMT04_PLAYLIST} " f"— fixture empty or unreadable: {c}" | **A** | SD fixture missing — rig state, nothing about firmware behaviour. |
| 48 | `app/tools/suite/serialdbg/shell.py:59` | `T078` | f"dragState={rg.get('state')} not D_IDLE" | **A** | debug-surface setup could not establish the starting offset/state. |
| 49 | `app/tools/suite/serialdbg/shell.py:535` | `T093` | "visual test — re-run with --interactive" | **A** | not applicable to an automated run — needs a human at the DUT. |
| 50 | `app/tools/suite/serialdbg/shell.py:566` | `T094` | "physical-tap test — re-run with --interactive (T087 covers serial proxy)" | **A** | not applicable to an automated run — needs a human at the DUT. |
| 51 | `app/tools/suite/serialdbg/shell.py:607` | `T095` | "requires --interactive flag (human operator at DUT). " "Re-run: python3 run_serialdbg_tests.py --interactive --tests T095" | **A** | not applicable to an automated run — needs a human at the DUT. |
| 52 | `app/tools/suite/serialdbg/shell.py:728` | `T134` | "precondition: queue count=0 after 30s — Spotify not playing" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 53 | `app/tools/suite/serialdbg/shell.py:808` | `T136` | "merged into T137 precondition — run T137" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 54 | `app/tools/suite/serialdbg/shell.py:816` | `T137` | "precondition: queue count<2 after 30s — Spotify not playing" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 55 | `app/tools/suite/serialdbg/shell.py:853` | `T138` | f"pre-condition: scrollOffset={pre} not 1 — Spotify not playing?" | **A** | debug-surface setup could not establish the starting offset/state. |
| 56 | `app/tools/suite/serialdbg/shell.py:901` | `T140` | "queue snapshot ≤ PLEDIT_ROW_COUNT items — max scrollOffset=0; " "snapshot expansion needed (see TASK-081 notes)" | **A** | external data/network availability — the test's inputs never arrived. |
| 57 | `app/tools/suite/serialdbg/shell.py:935` | `T147` | f"precondition: need Spotify active, got {r.get('name')!r}" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 58 | `app/tools/suite/serialdbg/shell.py:973` | `T148` | f"precondition: could not switch to Clock (appId={r_pre.get('name')!r})" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 59 | `app/tools/suite/serialdbg/shell.py:1006` | `T_BI_01` | "queue empty after 30s — Spotify not playing?" | **A** | external data/network availability — the test's inputs never arrived. |
| 60 | `app/tools/suite/serialdbg/shell.py:1056` | `T_BI_02` | f"precondition: need Spotify active, got {r.get('name')!r}" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 61 | `app/tools/suite/serialdbg/shell.py:1091` | `T_BI_03` | "queue count<2 after 30s — Spotify not playing?" | **A** | external data/network availability — the test's inputs never arrived. |
| 62 | `app/tools/suite/serialdbg/shell.py:1150` | `T_BI_04` | f"precondition: need Spotify active, got {r.get('name')!r}" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 63 | `app/tools/suite/serialdbg/shell.py:1178` | `T_MA_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 64 | `app/tools/suite/serialdbg/shell.py:1198` | `T_MA_02` | "could not switch to Matrix" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 65 | `app/tools/suite/serialdbg/shell.py:1219` | `T_MA_03` | "could not switch to Matrix" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 66 | `app/tools/suite/serialdbg/shell.py:1229` | `T_MA_03` | "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)" | **C** | residue check is T_MA_03's ONLY verdict (pass-or-skip, never fail), but `lastPlaylistDraw` advances only on a PLEDIT seqno bump or a pending scroll repaint (app/src/winamp/pleditView.h:134-143). The post-switch invalidate()-driven repaint almost always lands before the baseline read, so the 3 s window is really waiting on a Spotify queue poll — playback/network dependent. Cannot be converted as written; see §4 recommendation. |
| 67 | `app/tools/suite/serialdbg/shell.py:1238` | `T_GOL_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 68 | `app/tools/suite/serialdbg/shell.py:1256` | `T_GOL_02` | "could not switch to Life" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 69 | `app/tools/suite/serialdbg/shell.py:1275` | `T_GOL_03` | "could not switch to Life" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 70 | `app/tools/suite/serialdbg/shell.py:1284` | `T_GOL_03` | "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)" | **C** | same residue construct as T_MA_03 — same seqno-gate reasoning; switch-back here is an unverified taskbar tap, so a missed tap is indistinguishable from residue. |
| 71 | `app/tools/suite/serialdbg/shell.py:1293` | `T_GOL_04` | "could not switch to Life" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 72 | `app/tools/suite/serialdbg/shell.py:1315` | `T_WX_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 73 | `app/tools/suite/serialdbg/shell.py:1336` | `T_WX_02` | "could not switch to Weather" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 74 | `app/tools/suite/serialdbg/shell.py:1355` | `T_WX_03` | "could not switch to Weather" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 75 | `app/tools/suite/serialdbg/shell.py:1364` | `T_WX_03` | "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)" | **C** | same residue construct as T_MA_03. |
| 76 | `app/tools/suite/serialdbg/shell.py:1378` | `T_WX_04` | "weatherReady already true — Weather fetched data earlier this session; " "pre-fetch state no longer observable" | **A** | session state consumed by an earlier test — pre-fetch state no longer observable. |
| 77 | `app/tools/suite/serialdbg/shell.py:1391` | `T_WX_04` | "weatherReady=true immediately — data arrived before check; network too fast?" | **C** | the test's subject is exactly 'weatherReady=false immediately after switch-in'; observing true instead is either the defect or a lost race with a fast network. No in-test discriminator. |
| 78 | `app/tools/suite/serialdbg/shell.py:1402` | `T_WX_05` | "could not switch to Weather" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 79 | `app/tools/suite/serialdbg/shell.py:1431` | `T_CX_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 80 | `app/tools/suite/serialdbg/shell.py:1452` | `T_CX_02` | "could not switch to Crypto" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 81 | `app/tools/suite/serialdbg/shell.py:1471` | `T_CX_03` | "could not switch to Crypto" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 82 | `app/tools/suite/serialdbg/shell.py:1480` | `T_CX_03` | "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)" | **C** | same residue construct as T_MA_03. |
| 83 | `app/tools/suite/serialdbg/shell.py:1493` | `T_CX_04` | "cryptoReady already true — Crypto fetched data earlier this session; " "pre-fetch state no longer observable" | **A** | session state consumed by an earlier test — pre-fetch state no longer observable. |
| 84 | `app/tools/suite/serialdbg/shell.py:1504` | `T_CX_04` | "cryptoReady=true immediately — data arrived before check" | **C** | same shape as T_WX_04. |
| 85 | `app/tools/suite/serialdbg/shell.py:1515` | `T_CX_05` | "could not switch to Crypto" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 86 | `app/tools/suite/serialdbg/shell.py:1546` | `T_X07_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 87 | `app/tools/suite/serialdbg/shell.py:1623` | `T-BUSY-01` | "could not switch to StockApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 88 | `app/tools/suite/serialdbg/shell.py:1665` | `T-BUSY-01b` | "could not switch to StockApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 89 | `app/tools/suite/serialdbg/shell.py:1680` | `T-BUSY-01b` | "initial chart fetch did not complete — cannot test tab-range path" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 90 | `app/tools/suite/serialdbg/shell.py:1689` | `T-BUSY-01b` | "shellBusy=true not observed within 5 s after 5D tap — warm fetch too fast" | **C** | 'shellBusy=true after the 5D tab tap' IS this test's whole assertion, so the SKIP is the false-green shape. Not converted because a warm cached fetch can genuinely close the window before the 5 s poll sees it. |
| 91 | `app/tools/suite/serialdbg/shell.py:1700` | `T-BUSY-02` | "could not restore Spotify app" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 92 | `app/tools/suite/serialdbg/shell.py:1764` | `T-BUSY-05` | "could not switch to StockApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 93 | `app/tools/suite/serialdbg/shell.py:1778` | `T-BUSY-05` | "could not drill to chart (tap skipped or wrong subView)" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 94 | `app/tools/suite/serialdbg/shell.py:1783` | `T-BUSY-05` | "shellBusy=true not observed within 5 s — warm connection completed fetch too fast" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 95 | `app/tools/suite/serialdbg/shell.py:1815` | `T-CDWN-01` | "could not restore Spotify app" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 96 | `app/tools/suite/serialdbg/shell.py:1825` | `T-CDWN-01` | "g_shellBusy never cleared — cannot tap" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 97 | `app/tools/suite/serialdbg/shell.py:1874` | `T-CDWN-01` | "g_shellBusy never cleared before tap 3" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 98 | `app/tools/suite/serialdbg/shell.py:1907` | `T-CDWN-02` | "could not switch to StockApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 99 | `app/tools/suite/serialdbg/shell.py:1920` | `T-CDWN-02` | "get fetchOkCount failed" | **A** | baseline read failed before the trigger. |
| 100 | `app/tools/suite/serialdbg/shell.py:1925` | `T-CDWN-02` | "drill tap skipped — shell still busy after precondition wait" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 101 | `app/tools/suite/serialdbg/shell.py:1933` | `T-CDWN-02` | "tap2 not skipped — warm connection completed fetch before tap2 arrived" | **C** | the docstring names this the PRIMARY assertion ('second cmdTap returns skipped:true'). A gate regression would hide here forever. Not converted only because the test never asserts shellBusy==true between tap1 and tap2, so 'fetch already resolved' is a real alternative explanation. Convert AFTER adding that assertion. |
| 102 | `app/tools/suite/serialdbg/shell.py:1968` | `T-CDWN-03` | "could not switch to StockApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 103 | `app/tools/suite/serialdbg/shell.py:2018` | `(_vs_precondition)` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 104 | `app/tools/suite/serialdbg/shell.py:2021` | `(_vs_precondition)` | "precondition: queue count < 10 after 30 s — need ≥ 10 items loaded" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 105 | `app/tools/suite/serialdbg/shell.py:2028` | `(_vs_precondition)` | f"precondition: scrollOffset={so} could not be reset to 0" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 106 | `app/tools/suite/serialdbg/shell.py:2032` | `(_vs_precondition)` | f"precondition: dragState={rg.get('state')!r} not D_IDLE" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 107 | `app/tools/suite/serialdbg/shell.py:2171` | `T152` | "queue < 6 items — scrollOffset max=0; need more queued tracks" | **A** | external data/network availability — the test's inputs never arrived. |
| 108 | `app/tools/suite/serialdbg/shell.py:2551` | `T164` | f"could not set tbScrollOffset=1; actual={_tb_get_offset(dut)}" | **A** | debug-surface setup could not establish the starting offset/state. |
| 109 | `app/tools/suite/serialdbg/shell.py:2572` | `T165` | f"precondition offset={baseline}, expected 0" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 110 | `app/tools/suite/serialdbg/shell.py:2589` | `T166` | f"could not set tbScrollOffset={_TB_N - 1}; actual={_tb_get_offset(dut)}" | **A** | debug-surface setup could not establish the starting offset/state. |
| 111 | `app/tools/suite/serialdbg/shell.py:2742` | `T_TBFB_03` | "could not switch to Clock for the redirect tap" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 112 | `app/tools/suite/serialdbg/shell.py:2781` | `T_TBFB_04` | "could not restore Spotify for the canvas half" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 113 | `app/tools/suite/serialdbg/shell.py:2905` | `T-SET-01` | "could not switch to Settings" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 114 | `app/tools/suite/serialdbg/shell.py:2920` | `T-SET-02` | "could not switch to Settings" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 115 | `app/tools/suite/serialdbg/shell.py:2944` | `T-SET-03` | "could not switch to Settings" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 116 | `app/tools/suite/serialdbg/shell.py:2983` | `T-SET-06` | "could not switch to Settings" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 117 | `app/tools/suite/serialdbg/shell.py:2991` | `T-SET-06` | f"could not reach submenu 0, got {sub!r}" | **A** | Settings drill used as setup; T-SET-03 owns that drill and asserts it with fail(). |
| 118 | `app/tools/suite/serialdbg/shell.py:3012` | `T-SET-07` | "could not switch to Settings" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 119 | `app/tools/suite/serialdbg/shell.py:3043` | `T-SET-08` | "could not switch to Crypto" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 120 | `app/tools/suite/serialdbg/shell.py:3049` | `T-SET-08` | f"appId={r2.get('name')!r} — could not confirm Crypto" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 121 | `app/tools/suite/serialdbg/shell.py:3053` | `T-SET-08` | "could not switch to Settings from Crypto" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 122 | `app/tools/suite/serialdbg/shell.py:3082` | `T-UART-01` | "could not switch to StockApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 123 | `app/tools/suite/serialdbg/shell.py:3158` | `T-BGPOLL-03` | "could not switch to Spotify app" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 124 | `app/tools/suite/serialdbg/shell.py:3200` | `T-ERR-01` | "could not restore Spotify" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 125 | `app/tools/suite/serialdbg/shell.py:3225` | `T-ERR-02` | "could not restore Spotify" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 126 | `app/tools/suite/serialdbg/shell.py:3251` | `T-ERR-04` | "could not restore Spotify" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 127 | `app/tools/suite/serialdbg/shell.py:3273` | `T-ERR-05` | "could not restore Spotify" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 128 | `app/tools/suite/serialdbg/stock.py:79` | `T169` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 129 | `app/tools/suite/serialdbg/stock.py:113` | `T170` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 130 | `app/tools/suite/serialdbg/stock.py:158` | `T171` | "pixel verification required — run manually; check green/red rows after fetch" | **A** | not applicable to an automated run — needs a human at the DUT. |
| 131 | `app/tools/suite/serialdbg/stock.py:167` | `T172` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 132 | `app/tools/suite/serialdbg/stock.py:178` | `T172` | "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)" | **C** | residue check is T172's only verdict; switch-back IS verified here (fail() above), so this is the closest of the six to a (B) — but the seqno gate still makes 'did not advance' explainable by a quiet Spotify poll. Left SKIP pending the repaint-counter redesign. |
| 133 | `app/tools/suite/serialdbg/stock.py:187` | `T173` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 134 | `app/tools/suite/serialdbg/stock.py:193` | `T173` | "no quote fetch recorded yet — cannot verify resume cache" | **A** | external data/network availability — the test's inputs never arrived. |
| 135 | `app/tools/suite/serialdbg/stock.py:218` | `T174` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 136 | `app/tools/suite/serialdbg/stock.py:223` | `T174` | f"stockSubView={r_sv.get('val')!r} — expected list; prior test may have left chart view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 137 | `app/tools/suite/serialdbg/stock.py:254` | `T175` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 138 | `app/tools/suite/serialdbg/stock.py:263` | `T175` | "drill-in did not fire (fetchFailed?) — cannot test back navigation" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 139 | `app/tools/suite/serialdbg/stock.py:284` | `T176` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 140 | `app/tools/suite/serialdbg/stock.py:297` | `T176` | "fetch pipeline never drained within 200 s — " "dataTask/spotifyTask wedged (investigate via get dataq)" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 141 | `app/tools/suite/serialdbg/stock.py:307` | `T176` | "could not enter chart view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 142 | `app/tools/suite/serialdbg/stock.py:328` | `T177` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 143 | `app/tools/suite/serialdbg/stock.py:335` | `T177` | "could not enter chart view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 144 | `app/tools/suite/serialdbg/stock.py:368` | `T178` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 145 | `app/tools/suite/serialdbg/stock.py:382` | `T178` | "fetch pipeline never drained within 200 s — " "cannot isolate placeholder state" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 146 | `app/tools/suite/serialdbg/stock.py:396` | `T178` | "drill-in did not fire" | **C** | the drill-in is the test's own action, but subView is read after a deliberate 0.1 s wait chosen to beat dataTask — a lost race here is a test-timing artefact as often as a defect. |
| 147 | `app/tools/suite/serialdbg/stock.py:414` | `T179` | "pixel verification required — run manually; check lo:/hi: at y=214 after fetch" | **A** | not applicable to an automated run — needs a human at the DUT. |
| 148 | `app/tools/suite/serialdbg/stock.py:423` | `T180` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 149 | `app/tools/suite/serialdbg/stock.py:438` | `T180` | "first drill-in failed" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 150 | `app/tools/suite/serialdbg/stock.py:469` | `T181` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 151 | `app/tools/suite/serialdbg/stock.py:477` | `T181` | "first drill-in failed" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 152 | `app/tools/suite/serialdbg/stock.py:504` | `T182` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 153 | `app/tools/suite/serialdbg/stock.py:514` | `T182` | "could not enter chart view — cannot test canvas isolation" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 154 | `app/tools/suite/serialdbg/stock.py:526` | `T182` | f"tbScrollOffset={r_off.get('val')} — taskbar scroll failed; cannot verify taskbar path" | **A** | debug-surface setup could not establish the starting offset/state. |
| 155 | `app/tools/suite/serialdbg/stock.py:542` | `T182` | f"appId={r_app.get('name')!r} — taskbar tap missed Stock slot" | **A** | taskbar tap landed on the wrong slot — touch-injection rig state, and T163-T166 own taskbar slot arithmetic. |
| 156 | `app/tools/suite/serialdbg/stock.py:557` | `T182` | "lastPlaylistDraw did not advance after return to Spotify" | **C** | T182 has no pass_() of its own — it can only PASS via _check_residue or SKIP here. Same seqno-gate ambiguity; converting alone would make the cell red on any quiet-poll run. |
| 157 | `app/tools/suite/serialdbg/stock.py:567` | `T183` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 158 | `app/tools/suite/serialdbg/stock.py:599` | `T184` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 159 | `app/tools/suite/serialdbg/stock.py:606` | `T184` | "could not enter chart view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 160 | `app/tools/suite/serialdbg/stock.py:652` | `(t231)` | "could not switch to Stock for baseline" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 161 | `app/tools/suite/serialdbg/stock.py:731` | `T185` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 162 | `app/tools/suite/serialdbg/stock.py:766` | `(_t18x_guard)` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 163 | `app/tools/suite/serialdbg/stock.py:781` | `T186/T187` | f"drill-in did not enter chart view (subView={r_sv.get('val')!r})" | **C** | _t18x_guard's subject is the tickerIdx guard; a guard regression could plausibly present exactly as 'drill-in did not enter chart view'. Ambiguous with an ordinary missed tap — needs a tap-not-skipped check first. |
| 164 | `app/tools/suite/serialdbg/stock.py:822` | `T188` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 165 | `app/tools/suite/serialdbg/stock.py:836` | `T188` | "could not drill into chart view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 166 | `app/tools/suite/serialdbg/stock.py:892` | `T204` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 167 | `app/tools/suite/serialdbg/stock.py:905` | `T204` | "could not drill into chart view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 168 | `app/tools/suite/serialdbg/stock.py:995` | `T196` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 169 | `app/tools/suite/serialdbg/stock.py:1023` | `T200` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 170 | `app/tools/suite/serialdbg/stock.py:1027` | `T200` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 171 | `app/tools/suite/serialdbg/stock.py:1048` | `T201` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 172 | `app/tools/suite/serialdbg/stock.py:1053` | `T201` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 173 | `app/tools/suite/serialdbg/stock.py:1058` | `T201` | "set triggerHeatmap 1 failed" | **A** | external data/network availability — the test's inputs never arrived. |
| 174 | `app/tools/suite/serialdbg/stock.py:1064` | `T201` | f"stockSubView={r_sv_pre.get('val')!r} after triggerHeatmap — expected 'heatmap'" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 175 | `app/tools/suite/serialdbg/stock.py:1084` | `T202` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 176 | `app/tools/suite/serialdbg/stock.py:1088` | `T202` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 177 | `app/tools/suite/serialdbg/stock.py:1095` | `T202` | "set triggerHeatmap 1 failed (no cached heatmap)" | **A** | external data/network availability — the test's inputs never arrived. |
| 178 | `app/tools/suite/serialdbg/stock.py:1099` | `T202` | "heatmapCount still 0 after 60 s — no tiles to tap" | **A** | external data/network availability — the test's inputs never arrived. |
| 179 | `app/tools/suite/serialdbg/stock.py:1108` | `T202` | "HEAT tap did not enter heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 180 | `app/tools/suite/serialdbg/stock.py:1133` | `T203` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 181 | `app/tools/suite/serialdbg/stock.py:1137` | `T203` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 182 | `app/tools/suite/serialdbg/stock.py:1144` | `T203` | "set triggerHeatmap 1 failed (no cached heatmap)" | **A** | external data/network availability — the test's inputs never arrived. |
| 183 | `app/tools/suite/serialdbg/stock.py:1148` | `T203` | "heatmapCount still 0 after 60 s — no tiles" | **A** | external data/network availability — the test's inputs never arrived. |
| 184 | `app/tools/suite/serialdbg/stock.py:1157` | `T203` | "HEAT tap did not enter heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 185 | `app/tools/suite/serialdbg/stock.py:1166` | `T203` | "could not drill to chart from heatmap tile tap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 186 | `app/tools/suite/serialdbg/stock.py:1171` | `T203` | "shellBusy did not clear after tile drill — chart fetch stuck?" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 187 | `app/tools/suite/serialdbg/stock.py:1192` | `T192` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 188 | `app/tools/suite/serialdbg/stock.py:1196` | `T192` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 189 | `app/tools/suite/serialdbg/stock.py:1203` | `T192` | "set triggerHeatmap 1 failed (no cached heatmap data)" | **A** | external data/network availability — the test's inputs never arrived. |
| 190 | `app/tools/suite/serialdbg/stock.py:1207` | `T192` | "heatmapCount still 0 after 60 s" | **A** | external data/network availability — the test's inputs never arrived. |
| 191 | `app/tools/suite/serialdbg/stock.py:1216` | `T192` | "HEAT tap did not enter heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 192 | `app/tools/suite/serialdbg/stock.py:1226` | `T192` | "could not drill to chart from heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 193 | `app/tools/suite/serialdbg/stock.py:1233` | `T192` | "shellBusy did not clear after tile drill — chart fetch stuck?" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 194 | `app/tools/suite/serialdbg/stock.py:1243` | `T192` | f"stockChartRange={r_range.get('val')!r} after 5D tap — tab not registered" | **A** | the 5D tab tap not registering is setup for the auto-refresh assertion; T177 owns the tab-tap assertion and fail()s on it. |
| 195 | `app/tools/suite/serialdbg/stock.py:1270` | `T193` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 196 | `app/tools/suite/serialdbg/stock.py:1274` | `T193` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 197 | `app/tools/suite/serialdbg/stock.py:1286` | `T193` | "set triggerHeatmap 1 failed (no cached heatmap data)" | **A** | external data/network availability — the test's inputs never arrived. |
| 198 | `app/tools/suite/serialdbg/stock.py:1290` | `T193` | "heatmapCount still 0 after 60 s" | **A** | external data/network availability — the test's inputs never arrived. |
| 199 | `app/tools/suite/serialdbg/stock.py:1301` | `T193` | "HEAT tap did not enter heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 200 | `app/tools/suite/serialdbg/stock.py:1310` | `T193` | "could not drill to chart from heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 201 | `app/tools/suite/serialdbg/stock.py:1317` | `T193` | "shellBusy did not clear after tile drill" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 202 | `app/tools/suite/serialdbg/stock.py:1343` | `T193` | f"chartLen={chart_len} after auto-refresh — Yahoo returned empty data (external API flakiness)" | **A** | external data/network availability — the test's inputs never arrived. |
| 203 | `app/tools/suite/serialdbg/stock.py:1360` | `T194` | "could not switch to Stock" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 204 | `app/tools/suite/serialdbg/stock.py:1364` | `T194` | "could not normalize to list view" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 205 | `app/tools/suite/serialdbg/stock.py:1372` | `T194` | "set triggerHeatmap 1 failed (no cached heatmap data)" | **A** | external data/network availability — the test's inputs never arrived. |
| 206 | `app/tools/suite/serialdbg/stock.py:1376` | `T194` | "heatmapCount still 0 after 60 s" | **A** | external data/network availability — the test's inputs never arrived. |
| 207 | `app/tools/suite/serialdbg/stock.py:1385` | `T194` | "HEAT tap did not enter heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 208 | `app/tools/suite/serialdbg/stock.py:1394` | `T194` | "could not drill to chart from heatmap" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 209 | `app/tools/suite/serialdbg/stock.py:1399` | `T194` | "shellBusy did not clear after tile drill" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 210 | `app/tools/suite/serialdbg/stock.py:1415` | `T194` | f"could not navigate back to list; subView={r_sv.get('val')!r}" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 211 | `app/tools/suite/serialdbg/stock.py:1431` | `T194` | "could not drill to chart from list row" | **A** | in-app navigation used as setup; the test that OWNS this transition asserts it with fail() (T174 drill-in, T200/T201 HEAT toggle, T202 tile drill). |
| 212 | `app/tools/suite/serialdbg/stock.py:1438` | `T194` | "shellBusy did not clear after list-drill" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 213 | `app/tools/suite/serialdbg/stock.py:1450` | `T194` | "fetchOkCount did not advance on list-drilled tab-switch \| " f"entry={entry_diag} \| pre-list-drill={list_drill_diag} \| " f"pre-tab-switch={tab_diag} \| timeout={timeout_diag}" | **C** | behavioural in shape ('fetchOkCount did not advance'), but TASK-385 documented this exact cell as the suite's heap/queue-pressure canary and wired four diagnostic snapshots into the reason. Human call whether pressure-induced non-advance is a product failure. |
| 214 | `app/tools/suite/serialdbg/teletext.py:29` | `(t272)` | "get lastPlaylistDraw failed — Spotify not active?" | **A** | baseline read failed before the test began. |
| 215 | `app/tools/suite/serialdbg/teletext.py:36` | `(t272)` | "switchApp Teletext failed — app not registered?" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 216 | `app/tools/suite/serialdbg/teletext.py:67` | `(t272)` | f"teletextReady false — HTTP {http_code} (network, not contention)" | **A** | external data/network availability — the test's inputs never arrived. |
| 217 | `app/tools/suite/serialdbg/teletext.py:106` | `(t270)` | "could not switch to TeletextApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 218 | `app/tools/suite/serialdbg/teletext.py:169` | `(t271)` | "could not switch to TeletextApp" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 219 | `app/tools/suite/serialdbg/webradio.py:42` | `(_vs_precondition_webradio)` | "precondition: could not switch to WebRadio" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 220 | `app/tools/suite/serialdbg/webradio.py:46` | `(_vs_precondition_webradio)` | f"precondition: set wrDeadUrls 15 failed: {r_dead}" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 221 | `app/tools/suite/serialdbg/webradio.py:50` | `(_vs_precondition_webradio)` | f"precondition: wrCount={r_c.get('count')} after set wrDeadUrls 15" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 222 | `app/tools/suite/serialdbg/webradio.py:57` | `(_vs_precondition_webradio)` | f"precondition: scrollOffset={so} could not be reset to 0" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 223 | `app/tools/suite/serialdbg/webradio.py:61` | `(_vs_precondition_webradio)` | f"precondition: dragState={rg.get('state')!r} not D_IDLE" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 224 | `app/tools/suite/serialdbg/webradio.py:305` | `(_ensure_webradio)` | "could not switch to WebRadio" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 225 | `app/tools/suite/serialdbg/webradio.py:393` | `T_WR_EJECT_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 226 | `app/tools/suite/serialdbg/webradio.py:447` | `T_WR_EJECT_02` | "could not enter WebRadio" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 227 | `app/tools/suite/serialdbg/webradio.py:498` | `(_wr_err_test)` | "could not enter WebRadio app" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 228 | `app/tools/suite/serialdbg/webradio.py:565` | `T_WR_COEX_01` | "station list unavailable (network or fetch failure)" | **A** | external data/network availability — the test's inputs never arrived. |
| 229 | `app/tools/suite/serialdbg/webradio.py:587` | `T_WR_COEX_02` | "not in PLAYING state — run T_WR_COEX_01 first" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 230 | `app/tools/suite/serialdbg/webradio.py:617` | `T_WR_COEX_04` | "not in PLAYING state" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 231 | `app/tools/suite/serialdbg/webradio.py:658` | `T_WR_HEAP_01` | "could not switch to WebRadio" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 232 | `app/tools/suite/serialdbg/webradio.py:665` | `T_WR_HEAP_01` | "get wrHeap returned zeros (init values not stored?)" | **C** | `get wrHeap` returning zeros is the debug surface failing, not the >=30 KB threshold — but a firmware regression that stopped storing the init figures would silently green this cell forever. |
| 233 | `app/tools/suite/serialdbg/webradio.py:708` | `T_WR_HEAP_02` | "HEAP post-fetch not captured (log missed and get wrHeap=0)" | **A** | instrumentation capture miss, with a documented fallback path. |
| 234 | `app/tools/suite/serialdbg/webradio.py:725` | `T_WR_HEAP_03` | "not in WebRadio — run T_WR_COEX_01 first" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 235 | `app/tools/suite/serialdbg/webradio.py:729` | `T_WR_HEAP_03` | "no stations loaded — run T_WR_COEX_01 first" | **A** | external data/network availability — the test's inputs never arrived. |
| 236 | `app/tools/suite/serialdbg/webradio.py:733` | `T_WR_HEAP_03` | "could not reach PLAYING state" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 237 | `app/tools/suite/serialdbg/webradio.py:738` | `T_WR_HEAP_03` | "HEAP play log line not seen within 35s" | **C** | the HEAP-play log line is instrumentation, not the >=40 KB subject; a firmware regression that stopped emitting it hides the cell. Also note the message says 35 s while the call waits 65 s. |
| 238 | `app/tools/suite/serialdbg/webradio.py:760` | `T_WR_HEAP_04` | "not in WebRadio — run T_WR_COEX_01 first" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 239 | `app/tools/suite/serialdbg/webradio.py:764` | `T_WR_HEAP_04` | "no stations loaded — run T_WR_COEX_01 first" | **A** | external data/network availability — the test's inputs never arrived. |
| 240 | `app/tools/suite/serialdbg/webradio.py:768` | `T_WR_HEAP_04` | "could not reach PLAYING state" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 241 | `app/tools/suite/serialdbg/webradio.py:787` | `T_WR_VOL_03` | "no stations loaded (network or fetch failure)" | **A** | external data/network availability — the test's inputs never arrived. |
| 242 | `app/tools/suite/serialdbg/webradio.py:832` | `(t_wr_vol_clamp)` | "could not enter WebRadio via taskbar player-slot cycle" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 243 | `app/tools/suite/serialdbg/webradio.py:892` | `(t237)` | "could not enter WebRadio via taskbar player-slot cycle" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 244 | `app/tools/suite/serialdbg/webradio.py:997` | `(t276)` | "could not enter WebRadio via taskbar player-slot cycle" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 245 | `app/tools/suite/serialdbg/webradio.py:1105` | `T_WR_TLS_01` | "fetch pipeline never drained within 200 s — " "dataTask/spotifyTask wedged (investigate via get dataq)" | **A** | timing/quiescence precondition — the window the test needs was not observable. |
| 246 | `app/tools/suite/serialdbg/webradio.py:1112` | `T_WR_TLS_01` | "could not switch to WebRadio" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 247 | `app/tools/suite/serialdbg/webradio.py:1164` | `T_WR_TLS_01` | "all mirrors unreachable (http=-1, count=0) — " "network, not a TLS-path defect" | **A** | external data/network availability — the test's inputs never arrived. |
| 248 | `app/tools/suite/serialdbg/webradio.py:1189` | `T_WR_SPOTIFY_RESUME_01` | "precondition: could not restore Spotify" | **A** | explicitly labelled starting-state failure; not the subject under test. |
| 249 | `app/tools/suite/serialdbg/webradio.py:1193` | `T_WR_SPOTIFY_RESUME_01` | "station list unavailable (network or fetch failure)" | **A** | external data/network availability — the test's inputs never arrived. |
| 250 | `app/tools/suite/serialdbg/webradio.py:1197` | `T_WR_SPOTIFY_RESUME_01` | "could not reach PLAYING state — see T_WR_COEX_01" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 251 | `app/tools/suite/serialdbg/webradio.py:1296` | `(_webradio_ensure_playing)` | "station list unavailable (network or fetch failure)" | **A** | external data/network availability — the test's inputs never arrived. |
| 252 | `app/tools/suite/serialdbg/webradio.py:1302` | `(_webradio_ensure_playing)` | "could not reach PLAYING state (wrState=2) after set wrPlay 0" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 253 | `app/tools/suite/serialdbg/webradio.py:1440` | `T_WR_VIS_03` | "could not switch to Spotify app" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 254 | `app/tools/suite/serialdbg/webradio.py:1446` | `T_WR_VIS_03` | f"Spotify has no active playback this session " f"(isPlaying={is_playing}, consecutiveFailures={cf}) — likely " f"TASK-243 external blocker (Premium lapsed, poll 403s), not testable now" | **A** | no live Spotify playback this session — the known TASK-243 external blocker (Premium lapsed), explicitly a rig/account precondition. |
| 255 | `app/tools/suite/serialdbg/webradio.py:1524` | `T_WR_VIS_05` | "could not switch to Spotify app" | **A** | app/mode entry used as setup. The suite already fail()s this same condition in the tests that own switch liveness (T_MA_01, T_GOL_01, T231), so the skip/fail split is deliberate. |
| 256 | `app/tools/suite/serialdbg/webradio.py:1528` | `T_WR_VIS_05` | f"Spotify has no active playback this session " f"(isPlaying={r_info.get('isPlaying')}) — likely TASK-243 " f"external blocker, not testable now" | **A** | no live Spotify playback this session — the known TASK-243 external blocker, as above. |

---

## 6. Method

Sites were enumerated with an AST walk over `app/tools/suite/serialdbg/*.py` (every `Call` whose
callee is the name `skip`), so comments, docstrings and the `from lib.results import skip` line are
excluded. Each site was then read in context — the enclosing test function, its docstring, and where
the same condition is asserted elsewhere in the suite — before a bucket was assigned. Where a
verdict depended on what the firmware actually does (the residue family), the firmware was read:
`app/src/winamp/pleditView.h`, `app/src/winamp/winampDisplay.cpp`, `app/src/apps/spotifyApp.cpp`,
`app/src/spotifyTaskStorage.cpp`.

No DUT was touched. `./run/check` was run host-only and stayed at 11/11.
