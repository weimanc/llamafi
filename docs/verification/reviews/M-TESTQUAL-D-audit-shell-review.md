# M-TESTQUAL WP-D — the shell family's FEATURE class, audited per test

> Owner: **Verification Engineer**
> Status: in progress
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Prior packages: [WP-A harness](M-TESTQUAL-A-harness-review.md), [WP-B taxonomy](M-TESTQUAL-B-taxonomy-review.md), [WP-C gating classes](M-TESTQUAL-C-audit-core-review.md)

---

## 0. Scope, and how the corpus was measured

The 50 ids in `suite/serialdbg/shell.py` whose class is `FEATURE` — everything in
the shell family that WP-C's gating audit did not already cover. The other 46
shell ids (RIG/HEALTH/CORE) are audited in WP-C and are **not** re-audited here;
where a row here depends on one, WP-C's row is cited.

```sh
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
m=build_all_meta()
for t,v in m.items():
    if v['module']=='shell' and v['cls']=='FEATURE': print(t, v['scope'], v['effect'])"
# -> 50 ids: 27 Spotify · 6 Settings · 5 Weather · 5 Crypto · 4 Life · 3 Matrix
# all 50 carry effect=mutating
```

Static audit only, per rubric §5: no flash, no `run/test*`, no serial port; the
board is pinned to the `-DBOD_WATCH` debug build for TASK-557. `build_all_meta`
was the only import made under `app/tools/` (rubric §5 / amendment A1); every
other file — `shell.py`, `_helpers.py`, `coords.py`, `lib/dut.py`, and the
firmware sources under `app/src/` — was read, never imported.

Per amendment A2 the per-test tables put the **body location in column one** and
the id in column two, and no section is headed with a bare id.

### 0.1 What is distinctive about this corpus

Three things separate the FEATURE rows from WP-C's gating rows, and they shape
every finding below.

1. **More than half the corpus (27 of 50) is scoped `Spotify`,** and the owner
   account has had no Premium since TASK-243. Section 6 answers what that leaves
   standing.
2. **The four small-app scopes (Weather, Crypto, Life, Matrix — 17 ids)** were
   written once, in one sitting each, and share one body template. They therefore
   share one set of defects: the same defaulting oracle, the same vacuous bound,
   the same missing restore. Graded individually, but the fix is one edit
   repeated 17 times.
3. **`effect=mutating` on all 50** — none is declared read-only, so WP-B §5.2's
   state-leakage clusters apply to the whole set.

---

## 1. Spotify scope, batch 1 — the Winamp hit-test and PLEDIT-scroll ids (15)

Registry order (`shell.py:3400-3425`). Per amendment A2 the body location is
column one; ids are never a bare first cell.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:60` | T077 | The strip between the POSBAR hitbox and the transport row is dead — a tap there is neither TRANSPORT, POSBAR nor VOLUME. | `hit` from the tap reply is **not** one of three names. Purely negative; no positive expectation. | **WEAK** | S6, S8, S2 | `:68-71`. `r.get("hit", "")` (`:66`) defaults to `""`, which passes; so does `hit="CANVAS"`, which is what `cmdTap` returns when the busy gate swallowed the tap (`cmdTouch.cpp:48-51`), and so does any future new region name. `r["ok"]` is never checked. The gap y at `:64` is derived from parsed constants (good — `coords.py:108-130`), but the assertion tolerates every failure mode except the three it names. Sibling `T088` asserts `hit == "DEADZONE"` **and** `action == "FORCE_POLL"` for the same class of coordinate (`:466-469`) — the correct shape, in the same module. |
| `shell.py:77` | T078 | A zero-delta drag in the VOLUME zone does **not** commit `ACT_VOLUME`. | **None for the claim.** The only assertions are `dragState == "D_IDLE"` before and after. The claimed behaviour is handed to a human: `print("      NOTE: verify no 'dequeued action=VOLUME' in log manually")`. | **HOLLOW** | S4, S1, S13, S8 | `:107` is the deferral. `:103-106` asserts `dragState`, which is the *resting* state of the machine — it is `D_IDLE` whether or not a volume commit fired, because `_volumeDragRelease()` clears the state either way (`winampDisplay.cpp:367-369`). The pass detail even says so: "no volume commit expected". The `enqueued ACT_VOLUME` marker the test would need **exists and is greppable** (`winampDisplay.cpp:496`, `:510`) and `T082`/`T151` in this same module already collect it — this test simply does not. The `D_IDLE` half duplicates `T135`'s assertion. |
| `shell.py:164` | T081 | A serial tap on each of the five transport buttons reports `hit=TRANSPORT` with the matching action. | `hit == "TRANSPORT"` and `action ∈ {PREV,PLAY,PAUSE,STOP,NEXT}` per button, from the tap reply. | **SOUND** | S4, S9 | `:174-178`. Five real device-observed pairs, accumulated and failed together. The reply is built from `winampDisplay.lastTouchResult` (`cmdTouch.cpp:161-165`), which is the genuine hit-test output, not a synthesised constant. The pass detail ends "(Spotify effects: verify manually)" (`:180`) — honest labelling of what is *not* covered, which is the right way to carry an S4. `time.sleep(0.3)` at `:176` where `_poll_shell_busy` is already used at `:170`. |
| `shell.py:186` | T082 | A serial volume drag produces `ACT_VOLUME` enqueue events; **"debounce verified by count"**. | `len(enqueue_lines) >= 2` over a 60-step drag, within 20 s. | **WEAK** | S8, S10 | `:217-220`. The marker is real (`winampDisplay.cpp:496` `LOG_D("touch", "enqueued ACT_VOLUME pct=%ld")`) and counting it is the right instrument. The bound is the problem: the claim is **debounce**, i.e. that 60 move samples produce *fewer* than 60 enqueues — and `>= 2` cannot be violated by a debounce that stopped working, only by one that over-fires in the other direction. A firmware emitting one enqueue per sample passes with 61. The assertion needed is an upper bound (`2 <= n << 61`), and the test already has the number. |
| `shell.py:273` | T085 | With `songDuration` forced to 0, a POSBAR tap yields neither `hit=POSBAR` nor `action=SEEK`. | `hit != "POSBAR"` and `action != "SEEK"` after `set songDuration 0`. | **WEAK** | S6, S14 | `:292-297`. The derivation is genuine — `set songDuration` (`winampDisplay.cpp:785-791`) feeds the `seekMs >= 0` branch (`:432`), so the write key and the read path differ. Two defaulting oracles, both in the dangerous direction: `hit = r.get("hit", "")` / `action = r.get("action", "")` (`:288-289`) make a lost reply a pass, and the restore at `:291` uses `saved_ms = r_save.get("ms", 180000)` (`:281`) — a lost entry read silently writes a fabricated 180 s duration rather than restoring. See **D-9**: under TASK-243's 403 no poll ever overwrites it. |
| `shell.py:362` | T087 | SHUFFLE / REPEAT / VIS report their own regions; a LOGO tap gives `TLS_RESET` and emits the TLS-reset log line; a second LOGO tap inside the 2 s cooldown falls through to `DEADZONE/FORCE_POLL`. | Five hit/action pairs from tap replies, plus a `"hard reset"` / `"stopping client"` substring on the wire within 8 s. | **WEAK** | S5, S9, S13 | The five pairs (`:369-399`) are real and the marker exists (`spotifyTaskStorage.cpp:363`, WP-C row `T094`). Two defects. **(a)** The log scan (`:404-413`) uses exactly the split-read pattern `_helpers._tap_and_wait_log` was written to eliminate — its docstring (`_helpers.py:23-42`) documents that `dut.cmd`'s `read_json` silently eats async `spotifyTask` trace lines while hunting for the tap's JSON, and there are **two** `dut.cmd` calls (`:389`, `:396`) between the LOGO tap that arms the reset and the scan that looks for it. This id is the exact failure mode that helper exists for, and does not use it. **(b)** Six unrelated assertions share one id, and every failure routes to `flake()` (`:416`); `T087` **is** declared (`flaky.yaml:27-43`), so a genuine SHUFFLE regression that passes the mandated retry is recorded `FLAKY-PASS` (`lib/results.py:227`) — neither PASS nor FAIL. |
| `shell.py:425` | T088 | Eight canvas coordinates outside every Winamp zone give `DEADZONE/FORCE_POLL`; three coordinates at `x >= TASKBAR_X` give `TASKBAR`. | 11 device-observed `hit` values, eight of them paired with `action == "FORCE_POLL"`. | **SOUND** | S13, S10 | `:460-478`, accumulated into one `fail()` at `:485`. This is the shape `T077` should have had: positive expectation on both fields. Restore is unconditional and precedes the assertion (`:482`) — correct order. Costs: 11 cases in one id (a failure names the label but the id gives no locality), and the `+1`/`-1` probe offsets and `_gap_y` formula are hand-derived from parsed constants rather than from a firmware hitbox definition. |
| `shell.py:303` | T096 | `cmdDrag`'s queue drain is complete: a 60-step drag emits exactly 61 injection samples, a 62-step drag exactly 63. | **Exact equality** on a count of `"inject sample"` lines, twice, with different expected values. | **SOUND** | S10 | `:331-351`. The strongest oracle in the Spotify scope: an exact count, not a bound, on a device-emitted trace, checked at two different step counts so an off-by-one and a truncation are distinguishable. Marker verified: `console.cpp:163` `LOG_D("serial", "inject sample %d/%d …")`. `61`/`63` are hand-derived by comment (`:335`, `:346`) rather than from `steps+1` in code, which is the only thing to fix. Latent, shared with `T082`: both oracles are `LOG_D` lines and so are suppressible by the runtime level gate (`logSink.h:119-123`) — WP-C NEEDS-DUT #7. |
| `shell.py:758` | T134 | A tap in the PLEDIT content area reports `hit=PLEDIT`. | `r["ok"]` then `r["hit"] == "PLEDIT"`. | **SOUND** | S7 | `:772-782`. Real: the reply's `hit` comes from `lastTouchResult.region` on the PLEDIT branch (`cmdTouch.cpp:168-172`), and `pledit_tap(2)` is derived from parsed skin constants (`coords.py:154-159`). Gated on `wait_for_queue(min_count=1)` → `skip()` (`:763`), which under TASK-243 is the routine outcome (§6). |
| `shell.py:788` | T135 | A synthetic swipe-up fires drag-end: a `drag` response arrives and `dragState` returns to `D_IDLE`. | `drag_resp["ok"]` **and** `dragState == "D_IDLE"` after. | **SOUND** | S5, S14 | `:817-830`. Both halves device-observed; the entry precondition is a `fail()`, not a skip (`:792-795`) — deliberate and correct for a state-machine test. `except Exception: break` at `:805-806` degrades to the "no drag response" fail, which is honest. The scrollOffset restore at `:832-833` discards `_do_drag`'s return, so a failed restore is silent. |
| `shell.py:843` | T136 | (Archived plan entry: "`get scrollOffset` returns 0 at initial state", **Status: pass**.) | **None. The body is a single unconditional `skip()`.** | **BROKEN** | S1, S7, S12 | `:846` is the entire body: `skip("T136", "merged into T137 precondition — run T137")`. The id is still registered (`:3421`) and dispatched on every `run/test`, consuming a suite slot and producing a permanent non-result. Its only `test_plan` declaration lives in `test_plan-archive.md:1453` and still carries **`Status: pass (2026-05-24 re-run post-fix)`** for a test that has not executed an assertion since. `check_docs` scans the archive like any other file under `docs/verification/` (`gate/check_docs.py:650`), so C6 is satisfied by that stale row. The plan's own review section already prescribes the fix — "remove as standalone test" (`test_plan.md:2117`) — and it was half-applied: the assertion moved, the registry entry did not. |
| `shell.py:852` | T137 | A swipe-up through PLEDIT increments `scrollOffset` 0 → 1. | `scrollOffset == 1` after the drag, having asserted it was `0` before. | **SOUND** | S7 | `:858-878`. Baseline read in-test, both endpoints device-observed, and the absorbed `T136` precondition is a real `fail()` (`:863`). Gated on `wait_for_queue(min_count=2)` (`:854`). |
| `shell.py:884` | T138 | A swipe-down decrements `scrollOffset` 1 → 0. | `scrollOffset == 0` after, from an established start of `1`. | **SOUND** | S7, S5 | `:886-907`. Establishes its own precondition by driving the offset to 1 (`:888-894`) rather than inheriting it, which is why it is not order-sensitive. The recovery `_do_drag` at `:890` discards its return. |
| `shell.py:913` | T139 | `scrollOffset` clamps at 0 — a swipe-down at the minimum does not underflow. | `scrollOffset == 0` after a second swipe-down at 0. | **WEAK** | S8, S3 | `:918-931`. Unlike `T137`/`T140` this body has **no queue precondition at all**. With a queue shorter than `PLEDIT_ROW_COUNT` — including the empty queue that is today's steady state (§6) — the maximum offset is 0, the view has nothing to scroll, and `scrollOffset` stays 0 no matter what the clamp does. The test then passes having exercised nothing. Its two siblings both gate on `wait_for_queue` and this one was written without it. |
| `shell.py:937` | T140 | `scrollOffset` saturates at `count - PLEDIT_ROW_COUNT`; one more swipe-up does not increment. | `scrollOffset` equal before and after one extra swipe-up, from an empirically saturated start. | **SOUND** | S7, S9, S14 | `:955-968`. A genuine clamp assertion — it saturates by construction (20 swipe-ups), records the value, and asserts equality across one more. `val_sat < 1` is correctly a `fail()`, not a skip (`:958`). Gated on `wait_for_queue(min_count=6)` (`:942`). Thirty-five `_do_drag` calls (`:948`, `:955`) whose returns are all discarded, and it exits leaving `scrollOffset` saturated with no restore — see **D-10**. |

---

## 2. Spotify scope, batch 2 — touch-capture and velocity-scroll (12)

Registry order: `T149`–`T154` (`shell.py:3428-3433`), then `T155`–`T160`
(`:3470-3475`) after the busy/cooldown block.

A firmware fact that decides four of these rows: **`posbarDragMs` is
`_posbarDragCurrentMs`** (`winampDisplay.cpp:737-740`), the *live drag-tracking*
value written on Press-entry (`:434`) and on every Move (`:389`). The committed
seek is a separate event — `_seekSink((long)_posbarDragCurrentMs)` at Release
(`:362`) — and it has **no serial observable at all**. Any test whose claim is
"a seek was committed" is therefore asserting the position the finger reached,
not that anything was enqueued.

A second, sharper one: **the strings `"ACT_SEEK"` and `"seek commit"` are not
emitted by the firmware.** `ACT_SEEK` exists only as an enum name and as the
`"SEEK"` case of `actName()` (`spotifyTask.h:28`, `spotifyTaskStorage.cpp:331`);
`"seek commit"` appears nowhere. The only commit-shaped log line is
`"[D][chrome] drag-end commit pct=…"` for **volume** (`winampDisplay.cpp:522`).
Three ids grep for those dead markers.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:2114` | T149 | "POSBAR drag commits a **single** `ACT_SEEK` on Release at the correct position" (`test_plan.md:1400`, step 5: "assert serial log contains exactly one `ACT_SEEK` entry"). | `50000 <= posbarDragMs <= 120000`, plus `dragState == "D_IDLE"`. The commit is not observed. | **WEAK** | S2, S5, S8, S10 | `:2136-2143`. Three separate gaps between claim and body. **(a)** Plan step 5 is not implemented: `_tc_drag_collect` is called with markers `["ACT_SEEK", "seek commit"]` and the matched lines are **discarded into `_`** (`:2127`). **(b)** Even if they were used, neither string is ever printed by the firmware (see above), so the "exactly one" assertion is unimplementable as written. **(c)** `posbarDragMs` is the drag-tracking variable, not the commit (`winampDisplay.cpp:737`), so "commits" has no oracle. What remains — a 70 s-wide band on a 120 s track, when the plan itself predicts ≈89 032 ms — accepts any endpoint in the right 58 % of the groove. |
| `shell.py:2147` | T150 | Capture holds when the finger drifts above the POSBAR hitbox: `posbarDragMs` keeps updating from the x axis after y has left the groove. | `50000 <= posbarDragMs <= 120000` after a drag whose endpoint y is 22 px above the hitbox. | **SOUND** | S10, S14 | `:2167-2177`. Here the loose band is load-bearing in the right direction: if capture is lost at the first out-of-groove Move, `posbarDragMs` holds the **Press-entry** value `posbarFromX(pbx0+24)` ≈ 11 600 ms (`winampDisplay.cpp:434`), which fails. The claim and the oracle match. One residual, and it is an order dependence: `T149` runs immediately before and leaves `posbarDragMs` ≈ 89 000 — so a regression that prevented the POSBAR gesture from *starting at all* would pass on `T149`'s residue. Not in `_order.py`'s `EDGE_ADJUDICATION`. |
| `shell.py:2181` | T151 | Capture holds when the finger drifts below the VOLUME hitbox: `ACT_VOLUME` still fires. | At least one `"enqueued ACT_VOLUME"` / `"drag-end commit"` line during the drag, **and** `dragState == "D_IDLE"` after. | **SOUND** | S8 | `:2194-2210`. Both markers verified present — `winampDisplay.cpp:496`/`:510` (`LOG_D("touch", …)`) and `:522` (a bare `Serial.printf`, so not level-gated). The empty case is a `fail()`, not a skip (`:2206`). This is the row `T149` should have been modelled on: it collects markers and *uses* them. Presence-only rather than a count, hence S8, but the claimed behaviour genuinely cannot survive a regression here. |
| `shell.py:2214` | T152 | PLEDIT scrollbar capture: a drag begun on the right-hand strip that drifts left into the content area keeps scrolling. | `scrollOffset > 0` after the drift drag, from an established `0`, plus `dragState == "D_IDLE"`. | **SOUND** | S7, S10 | `:2225-2255`. Real, and it establishes its own precondition with ten reset drags (`:2222-2227`, a `fail()` if it cannot). Gated on `wait_for_queue(min_count=6)` → `skip()` (`:2218`). The strip x is derived from parsed constants but the `+9` and `+40` drift offsets and the `+4`/`+44` y span are uncited literals (`:2233-2236`). |
| `shell.py:2258` | T153 | Capture exclusivity: a VOLUME drag that drifts into the POSBAR row must not start a seek. | `posbarDragMs` identical before and after — plus, nominally, the absence of `ACT_SEEK`/`seek commit`/`D_POSBAR` lines. | **WEAK** | S8, S6, S5 | `:2291-2300`. The `posbarDragMs`-unchanged half (`:2293`) is real, self-baselined (`:2268-2269`) and is the assertion doing all the work. The negative log half at `:2297-2298` is **dead**: none of the three markers is ever printed by the firmware — `"ACT_SEEK"` and `"seek commit"` do not exist as log strings anywhere, and `"D_POSBAR"` occurs only inside a `get dragState` reply (`winampDisplay.cpp:683`), which this test does not issue until *after* `_tc_drag_collect` has returned. `lines` cannot be non-empty, so `if lines: fail(...)` is unreachable. Compounding it: `rp_pre`/`rp_post` both default to `-1` (`:2269`, `:2292`), so two lost replies compare equal and pass. |
| `shell.py:2304` | T154 | "POSBAR tap: Press + Release **seeks** to the pressed x position." | `35000 <= posbarDragMs <= 45000` after a tap at `pbx0+164`, plus `hit == "POSBAR"` and `skipped` false. | **WEAK** | S2, S10 | `:2318-2330`. The hit and the `skipped` check are real and correctly `fail()` (`:2319-2322`). The value check is real too — but it reads the Press-entry initialisation (`winampDisplay.cpp:434`), which the body's own failure text admits ("0 = Press-entry init broken"). The **seek** in the claim — `_seekSink` firing at Release (`:362`) — is unobserved, and `pendingReleaseAt`/the sink have no getter. So the id proves the thumb moved, not that the track did. `pbx0+164`, `[35000,45000]` and the ≈39 677 expectation are hand-computed in a comment (`:2314`). |
| `shell.py:2336` | T155 | Plan (`test_plan.md:1534`): "Tap within dead zone **fires ACT_PLAY_URI**", step 3 "assert serial log contains `ACT_PLAY_URI`". | `hit == "PLEDIT"`, `scrollOffset` unchanged, `dragState == "D_IDLE"`. `ACT_PLAY_URI` is never looked for. | **WEAK** | S2, S7 | `:2343-2359`. What is asserted is real and is a genuine tap-versus-scroll discriminator: the same gesture taking the scroll-end branch would move `scrollOffset`. But the plan's headline behaviour — the row actually being played — has no oracle, and the marker does exist to grep for (`winampDisplay.cpp:54` enqueues `ACT_PLAY_URI`; `spotifyTaskStorage.cpp:335` names it in the `dequeued action=…` line at `:420`). This is one of the six ids in §6's "still claims playback coverage" list. Entered through `_vs_precondition` (queue ≥ 10). |
| `shell.py:2362` | T156 | A 13 px drag exceeds the 1 px dead zone, so Release takes the scroll-end branch and suppresses the tap. | `dragState == "D_IDLE"` **and** `cooldown.remainingMs <= 220` — the scroll-end cooldown (150 ms) versus the tap cooldown (300 ms). | **SOUND** | S7, S10 | `:2377-2389`. A real branch discriminator on a device-owned counter, and the substitution of the cooldown proxy for the plan's "no `ACT_PLAY_URI`" is documented in-body (`:2381-2382`). `rc.get("remainingMs", 9999)` defaults to the failing value — the safe direction. Exposed to WP-C **C-18**: `get cooldown` and `get shellCooldown` return the same field name, `Dut.cmd` issues `get shellCooldown` before every tap and drag (`lib/dut.py:1132-1134`), and nothing correlates request to reply. The `220` boundary is uncited. |
| `shell.py:2393` | T157 | Velocity scaling: a `tick 50 20` fired mid-gesture at dy = −13 px advances `scrollOffset` into `[1, 3]` (≈2.0 rows/s). | `dragState == "D_PLEDIT_SCROLL"` mid-gesture, then `1 <= tick.scrollOffset <= 3`. | **SOUND** | S7, S10 | `:2413-2428`. The most technically careful row in the Spotify scope: it interleaves three commands into the serial buffer so the tick lands *between* the drag's Move and Release iterations, and it asserts the gesture really was live (`D_PLEDIT_SCROLL`) before trusting the tick's number. The band is derived from the as-built constants the plan records (`SCROLL_SPEED_K_DEFAULT = 0.1667`, `test_plan.md:1525`) but written as a literal rather than computed. |
| `shell.py:2431` | T158 | "Tick integration: 1 s at dy = −13 advances `scrollOffset` ≥ 1." | `tick.scrollOffset >= 1`. | **WEAK** | S13, S8, S7 | `:2444-2453`. Identical setup, identical command sequence and identical oracle field to `T157` — with a strictly weaker bound. Every failure `T158` can detect, `T157` detects first and more precisely, and `T157` additionally asserts the `D_PLEDIT_SCROLL` precondition that `T158` drops (`:2444` takes any tick reply it finds). Two ids, one assertion; the pair costs two full `_vs_precondition` runs (queue wait + five reset drags each). |
| `shell.py:2456` | T159 | `scrollAccum` is non-zero while the gesture is live and is reset to `0.0000` on Release. | `scrollAccum != 0.0` mid-drag **and** `== 0.0` after Release, with `D_PLEDIT_SCROLL` then `D_IDLE` around it. | **SOUND** | S7 | `:2480-2505`. Four device-observed values including a genuinely hard-to-fake one — a float read from inside a live gesture, obtained by the same serial-buffer interleave as `T157`. Both defaults are in the safe direction: `r_accum_pre.get("val", 0.0)` (`:2488`) defaults to the value that fails the non-zero check, `r_accum_post.get("val", -1.0)` (`:2495`) to the value that fails the zero check. Field verified: `winampDisplay.cpp:762-765`. |
| `shell.py:2508` | T160 | `tickScroll` is a no-op while `dragState` is `D_IDLE`. | `scrollOffset` unchanged across a `tick 50 20` **and** `scrollVelocity == 0.0`. | **SOUND** | S7 | `:2518-2537`. A real negative assertion with two independent terms, and `r_vel.get("val", None)` (`:2532`) defaults to `None`, which fails — safe. Field verified: `winampDisplay.cpp:767-770`. |

---

## 3. The four small-app scopes — Matrix, Life, Weather, Crypto (17)

Registry order `shell.py:3439-3459`. These four families were written to one
template — *round-trip*, *BUG-1 guard*, *canvas residue*, and for the two network
apps a *pre-fetch* and a *data-arrives* row — so the same three defects recur
verbatim across them. They are graded individually below, but D-1, D-2 and D-3
each name four ids.

**The firmware fact that decides the four "BUG-1 guard" rows.** `cmdTap`
dispatches on `currentAppId`; Stock, Settings, Teletext, PlaneRadar, LocalPlayer,
WebRadio and Clock each get a real `handleInput()` call, and everything else
falls into a terminal `else` that calls nothing and prints a **fixed string**:

```c
} else {
  winampDisplay.lastTouchResult = { "CLOCK", -1, "NONE", 0, -1, false };
  Serial.printf("{\"ok\":true,\"cmd\":\"tap\",…\"hit\":\"CLOCK\",\"action\":\"NONE\",…}\n", x, y);
}
```
— `cmdTouch.cpp:141-144`, whose own comment reads *"Other apps retain BUG-1 guard
(hit=CLOCK) — they don't need tap dispatch in tests."* `injectTouch()` is never
called on that branch, so no Winamp hit-test can leak into it and no Winamp zone
name can ever be returned. Contrast WP-C's `T148`, which is SOUND because the
Clock branch really does dispatch and returns `CLOCKAPP`/`CONSUMED`
(`cmdTouch.cpp:134-140`).

**The firmware fact that decides the four "canvas residue" rows.**
`_check_residue` (`_helpers.py:177-192`) watches `lastPlaylistDraw` for 3 s and
calls `pass_()` if it moves. On the way back, `SpotifyApp::resume()` calls
`invalidatePlaylist()` (`spotifyApp.cpp:27`), which sets `_lastDrawMs = 0` and
`_scrollDirty = true` (`pleditView.h:174-179`), forcing the next `draw()` past
the seqno gate regardless of queue content (`:137-143`). So the timestamp
advances on any board that resumes at all — which is why these four are reachable
under TASK-243, and also why they prove a repaint *happened*, not that the canvas
is clean.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:1216` | T_MA_01 | Spotify → Matrix → Spotify round-trip; `appId` correct at each step. | `get appId.name == "Matrix"` after the slot tap, `== "Spotify"` after the restore. | **SOUND** | S9, S14 | `:1224-1232`. Both legs are real device-observed comparisons inside `_switch_to` (`_helpers.py:330-331`) and `_restore_spotify` (`:317-318`), and a failed switch is a `fail()`, not a skip. Fixed `sleep(0.4)`/`sleep(0.3)` where `get idle` exists. Writes `set playerMode spotify` unconditionally — WP-B cluster **C3**, accepted. |
| `shell.py:1237` | T_MA_02 | "Canvas tap while Matrix active returns `hit=CLOCK` — **Winamp zones bypassed**." | `hit == "CLOCK"` — a string literal in `cmdTap`'s terminal `else`, on a branch selected purely by `currentAppId != Spotify`, which `_switch_to` verified by `get appId` two lines earlier. | **HOLLOW** | S3, S1, S12 | `:1246-1253` against `cmdTouch.cpp:141-144`. Textbook S3: the value asserted is fixed by a precondition the test itself just established and re-read. There is no Winamp hit-test on this path to bypass — `injectTouch()` is not called — so the claimed regression is unrepresentable. The one thing it can genuinely detect is unrelated to the claim: a stuck `shell::state().busy` returns `hit="CANVAS"`, `skipped=true` (`cmdTouch.cpp:48-51`). Note also that the assertion is on the *debug console's* dispatch, not on `appShell`'s production touch path, so a routing regression in the real input path is invisible here. |
| `shell.py:1258` | T_MA_03 | Spotify renders correctly (`lastPlaylistDraw` advances) after switching back from Matrix — no TFT state residue. | `lastPlaylistDraw.ms` changes within 3 s of the switch back. | **BROKEN** | S7, S5, S8 | `:1261-1272`. The pass path is real. **The body contains no `fail()` at all**: a failed switch is `skip()` (`:1262`), and `_check_residue` returning `False` — which is exactly the regression the id exists to catch, Spotify not repainting after a switch-back — is also `skip()` (`:1272`), with a reason that blames the account ("Spotify not rendering (not playing?)"). Since `invalidatePlaylist()` guarantees the repaint independently of the queue (see above), that excuse is not even correct. The test cannot fail for the reason it exists; per rubric §2 that is BROKEN, not WEAK. And the claim is broader than the oracle regardless: a repaint timestamp is not evidence of clean pixels. |
| `shell.py:1277` | T_GOL_01 | Spotify → Life → Spotify round-trip. | As `T_MA_01`. | **SOUND** | S9, S14 | `:1283-1290`. Same shape, same evidence. |
| `shell.py:1295` | T_GOL_02 | Canvas tap while Life active returns `hit=CLOCK` — Winamp zones bypassed. | As `T_MA_02` — the same literal, the same branch. | **HOLLOW** | S3, S1, S12, S13 | `:1303-1309`; `cmdTouch.cpp:141-144`. Identical body to `T_MA_02` with one app name changed; the two ids make the same assertion about the same line of firmware. |
| `shell.py:1314` | T_GOL_03 | Spotify renders correctly after Life switch-back. | As `T_MA_03`. | **BROKEN** | S7, S5, S8 | `:1317-1327`. No `fail()` in the body; the guarded regression exits as `skip()` at `:1327`. |
| `shell.py:1332` | T_GOL_04 | `golAlive > 0` after ~3 Life ticks — cells alive **and** `stepGeneration` ran. | `golAlive.count > 0`. | **SOUND** | S9, S8 | `:1340-1349`. Both halves of the claim are genuinely carried by the one number, which is not obvious and is worth recording: `_golAliveCount` is initialised to `-1` ("never ticked") and is assigned **only** inside `stepGeneration` (`lifeApp.h:54`, `lifeApp.cpp:107`), so any value `>= 0` proves the generation stepper ran. `r.get("count", -1)` (`:1345`) defaults to the failing value. Weakness: `> 0` will false-FAIL if the board legitimately reaches extinction, and `sleep(0.35)` for "3+ ticks at 100 ms" is a fixed-sleep race with no retry. |
| `shell.py:1354` | T_WX_01 | Spotify → Weather → Spotify round-trip. | As `T_MA_01`, with `bgPoll` suspended across the switch. | **SOUND** | S9, S14 | `:1360-1370`. Real, and the `_bgpoll_suspended` context manager (`_helpers.py:444-454`) restores in a `finally` — the correct handling of WP-B cluster **C2**, and the only place in this family that uses it. |
| `shell.py:1375` | T_WX_02 | Canvas tap while Weather active returns `hit=CLOCK` — Winamp zones bypassed. | As `T_MA_02`. | **HOLLOW** | S3, S1, S12, S13 | `:1383-1389`; `cmdTouch.cpp:141-144`. |
| `shell.py:1394` | T_WX_03 | Spotify renders correctly after Weather switch-back. | As `T_MA_03`. | **BROKEN** | S7, S5, S8 | `:1397-1407`. No `fail()` in the body. |
| `shell.py:1412` | T_WX_04 | `weatherReady == false` immediately after the **first** switch-in, before the fetch completes. | `weatherReady.ready is not True` on entry and again immediately after the switch. | **BROKEN** | S7 | `:1416-1436`. The oracle is real and the field exists (`cmdGet.cpp:422-425`). The defect is positional and WP-B already measured it (**B §5.3**): `T_WX_01`, `T_WX_02` and `T_WX_03` all switch to Weather and run at indices 158–160, immediately before this id at 161, so `weatherReady` is already `True` and the body takes its "already true — pre-fetch state no longer observable" `skip()` at `:1421` on **every full-suite run**. The test is dead in the shipped ordering and nothing in `EDGE_ADJUDICATION` says so. Cited, not re-derived. |
| `shell.py:1441` | T_WX_05 | `weatherReady` becomes true within 30 s of switching to Weather. | `weatherReady.ready is True` polled every 2 s for 30 s; a timeout is a `fail()` carrying `weatherFetchPhase`. | **SOUND** | S7, S10 | `:1448-1465`. A real end-to-end assertion: the flag can only be set by a completed dataTask fetch, the negative outcome is a `fail()` (`:1461`) not a skip, and the failure text carries a decoded phase for triage (`:1457-1459`). Restores Spotify on both paths. The 30 s budget is uncited. |
| `shell.py:1470` | T_CX_01 | Spotify → Crypto → Spotify round-trip. | As `T_WX_01`. | **SOUND** | S9, S14 | `:1476-1486`. |
| `shell.py:1491` | T_CX_02 | Canvas tap while Crypto active returns `hit=CLOCK` — Winamp zones bypassed. | As `T_MA_02`. | **HOLLOW** | S3, S1, S12, S13 | `:1499-1505`; `cmdTouch.cpp:141-144`. |
| `shell.py:1510` | T_CX_03 | Spotify renders correctly after Crypto switch-back. | As `T_MA_03`. | **BROKEN** | S7, S5, S8 | `:1513-1523`. No `fail()` in the body. |
| `shell.py:1528` | T_CX_04 | `cryptoReady == false` immediately after the first switch-in. | As `T_WX_04`. | **BROKEN** | S7 | `:1531-1549`. Identical mechanism, identical position: `T_CX_01/02/03` at indices 163–165 precede it at 166 (WP-B **B §5.3**). Dead in every full-suite run. |
| `shell.py:1554` | T_CX_05 | `cryptoReady` becomes true within 30 s of switching to Crypto. | As `T_WX_05`, with `cryptoHttpCode` added to the failure text. | **SOUND** | S7, S10 | `:1561-1580`. Same shape as `T_WX_05` and slightly better instrumented (`:1570-1574`). Fields verified: `cmdGet.cpp:427-450`. |

---

## 4. Settings scope — settings-nav-stub-001 (6)

Registry order `shell.py:3489-3494`. Both getters verified present:
`settingsSection` → `_s.section` and `settingsAppSubmenu` → `_apps.submenu()`
(`apps/settingsApp.cpp:72-78`). This is the best-built scope in the FEATURE
corpus — six SOUND rows — and its one systemic defect is shared by all six, so
it is filed once as **D-6** rather than repeated per row.

That defect: the tap geometry is **mirrored by hand**, with the file itself
saying so — *"Settings-list geometry (mirrored from firmware — keep in sync)"*
(`shell.py:2923-2932`). Four constants (`_S_CONTENT_Y`, `_S_ROW_H`,
`_S_CONTENT_H`, `_CONFIGURABLE_APP_COUNT`) and, worse, one **re-implemented
formula**: `_APP_LIST_ROW_H = min(_S_ROW_H, _S_CONTENT_H // _CONFIGURABLE_APP_COUNT)`
(`:2932`) is a Python transcription of `_appListRowH()`
(`app/src/settings/appsSection.h:256-259`). All four values are correct today
(`settingsSection.h:39-43`, `app/gen/configurable_apps.h:4`) — but
`CONFIGURABLE_APP_COUNT` lives in `app/gen/`, i.e. in exactly the generated
header LL-114 says to parse rather than mirror, and the whole point of that
formula is that it *changes* when the app count grows. Drift here does not fail
loudly: the taps land on the neighbouring row and the ids fail with an
off-by-one section index, which reads as a firmware regression. WP-B **B §3.1**
already flagged this constant block from the scope-resolution side.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:2964` | T-SET-01 | `switchApp(Settings)` opens at the category list — `settingsSection == -1`. | `get settingsSection.section == -1`. | **SOUND** | S7, S9 | `:2971-2976`. One device field, one exact value, restore before assert (`:2972`). `_switch_to_settings` verifies `appId == "Settings"` before returning (`:2909-2910`), so a failed switch is a `skip()` (`:2968`), not a mis-attributed fail. |
| `shell.py:2980` | T-SET-02 | Tapping each category row 0…4 sets `section` to that index; the back zone returns it to −1. Ten transitions. | `section == idx` after each row tap, `section == -1` after each back tap. | **SOUND** | S11, S10, S9 | `:2987-3001`. Ten real device-observed comparisons against ten distinct expected values, and the loop fails at the first mismatch naming the row. This is the strongest FEATURE row in the module: a hit-test regression on any single category row is caught and localised. The back zone is tapped at the literal `(30, 14)` (`:2959`) with no cited origin — it happens to fall inside `S_BACK_ZONE_W=60 × S_HEADER_H=28` (`settingsSection.h:39,49`), but nothing ties it there. `_settings_tap_row` discards the tap reply (`:2943`), so a `skipped:true` tap surfaces as a section mismatch rather than as a busy-gate precondition. |
| `shell.py:3005` | T-SET-03 | Applications drill-down: category row 5 → `section 5`/`submenu -1`, app row 0 → `submenu 0`, back ×2 unwinds to −1/−1. | Five device-observed values across four navigation steps, on two independent fields. | **SOUND** | S11, S9 | `:3012-3041`. Genuine multi-level state-machine coverage, and it asserts the *intermediate* state (`submenu == -1` at level 1, `:3019`) rather than only the endpoints — so a drill that skips a level is caught. Restore precedes every `fail()`. Uses the compressed `_settings_tap_app_row` correctly, per the TASK-330 note at `:2947-2952`. |
| `shell.py:3045` | T-SET-06 | `suspend()` resets navigation: leave Settings from inside a submenu, re-enter, and both `section` and `submenu` are −1. | `section == -1` **and** `submenu == -1` on re-entry, having confirmed `submenu == 0` before leaving. | **SOUND** | S7, S9 | `:3054-3071`. The precondition is established and verified (`:3054-3058`), and the two re-entry values are read from the device after a real app switch away and back — the assertion crosses `SettingsApp::suspend()`, which the test did not write. The unreached-submenu exit is a `skip()` (`:3057`); everything after it is a `fail()`. |
| `shell.py:3075` | T-SET-07 | Back from Applications level 2 (app-list row 2) unwinds all three levels. | `section == 5` and `submenu == 2` after the drill, `submenu == -1` after one back, `section == -1` after the second. | **SOUND** | S11, S13, S9 | `:3084-3102`. Real, and it differs from `T-SET-03` in the row index only — row 2 versus row 0, which does exercise the compressed-row arithmetic at a non-zero multiple, so this is a defensible sibling rather than a pure duplicate. The comment at `:3083` is explicit that the assertion is on indices, not app identity. |
| `shell.py:3106` | T-SET-08 | Back from the category list returns to `g_previousAppId` rather than to a fixed app. | `get appId.name == "Crypto"` after the back tap, having entered Settings from Crypto. | **SOUND** | S7, S9, S10 | `:3124-3138`. The best-designed row in the scope: it establishes a *non-default* previous app (Crypto, not Spotify) so that a regression returning to a hardcoded app is caught, and it verifies the entry state (`appId == "Crypto"`, `:3116`) before relying on it. Three `skip()` exits are all genuine setup failures. Restores Spotify on every path. |

---

## 5. Family findings

Severity per rubric §4.3: **P1** the test is counted as coverage but provides
none; **P2** materially weaker than claimed; **P3** hygiene.

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **D-1** | **P1** | **The four "BUG-1 guard" ids assert a string literal that `cmdTap` prints unconditionally.** `T_MA_02`, `T_GOL_02`, `T_WX_02`, `T_CX_02` each tap the canvas and assert `hit == "CLOCK"`. That value comes from `cmdTap`'s terminal `else`, which calls no app handler and no `injectTouch()` — it is a fixed `Serial.printf` reached whenever `currentAppId` is not one of the seven dispatching apps. The branch is selected by `currentAppId`, which `_switch_to` verified by `get appId` on the line before. So the claimed regression ("Winamp zones leak into a small app") is **unrepresentable** on this path, and the assertion is a tautology on the test's own precondition. Four ids, one assertion, zero behavioural content. | `shell.py:1246-1253`, `:1303-1309`, `:1383-1389`, `:1499-1505`; `cmdTouch.cpp:56-58, 141-144` (and its own comment: *"Other apps retain BUG-1 guard (hit=CLOCK) — they don't need tap dispatch in tests"*) | Either give these four apps a real `cmdTap` branch that calls `handleInput()` and reports `CONSUMED`/`NONE` — the shape `T148` is SOUND on (`cmdTouch.cpp:134-140`) — or delete all four ids and record in `test_plan.md` that the small apps have no canvas interaction to test. Do not leave a green row asserting a printf. |
| **D-2** | **P1** | **The four "canvas residue" ids contain no `fail()` at all.** `T_MA_03`, `T_GOL_03`, `T_WX_03`, `T_CX_03` have exactly two exits: `pass_()` from `_check_residue`, or `skip()`. The failure they exist to detect — Spotify not repainting after a switch-back — takes the `skip()` branch with the reason *"lastPlaylistDraw did not advance — Spotify not rendering (not playing?)"*. The excuse is also wrong: `SpotifyApp::resume()` calls `invalidatePlaylist()`, which clears both the seqno sentinel and the rate limit, so the repaint is forced regardless of what is playing. A real residue regression reads green in every run. | `shell.py:1271-1272`, `:1326-1327`, `:1406-1407`, `:1522-1523`; `_helpers.py:177-192`; `spotifyApp.cpp:27`; `pleditView.h:137-143, 174-179` | Change the `_check_residue is False` branch from `skip()` to `fail()` in all four. `_check_residue`'s docstring already says *"Does not call fail() — caller decides on skip vs fail"*; four callers made the wrong choice. |
| **D-3** | **P1** | **`T_WX_04` and `T_CX_04` are dead in the shipped ordering** — their precondition ("this app has never been visited this session") is destroyed by their own three immediate predecessors, so both take the "already true" `skip()` on every full-suite run. Measured by WP-B, cited here from the body side; neither appears in `_order.py`'s `EDGE_ADJUDICATION`. | `shell.py:1420-1424`, `:1535-1539`; indices from WP-B **B §5.3** | Move both ids to the front of their family (before the round-trip row that spoils them), or drive the precondition explicitly with a `set weatherReady 0` / `set cryptoReady 0` debug accessor. Either way, add them to `EDGE_ADJUDICATION`. |
| **D-4** | **P1** | **`T136` is a registered id whose entire body is `skip()`, and its plan declaration still says PASS.** It occupies a suite slot, is dispatched on every run, and produces a permanent non-result. Its only declaration lives in `test_plan-archive.md` and carries `Status: **pass** (2026-05-24 re-run post-fix)`. `check_docs` scans the archive like any other file under `docs/verification/`, so C6.1 is satisfied by a row describing a test that has not executed an assertion in over three months. The plan's own review section prescribes the removal (`test_plan.md:2117`) — the assertion was folded into `T137`, the registry entry was not deleted. | `shell.py:843-846`, `:3421`; `test_plan-archive.md:1453-1465`; `test_plan.md:2117-2118`; `gate/check_docs.py:650` | Delete the `TESTS["T136"]` entry and its body, and add `T136` to `id_binding_exceptions.md` as retired-into-`T137`. |
| **D-5** | **P1** | **`T078` defers its entire claim to a human and asserts a resting state instead.** The claim is "no `ACT_VOLUME` commit on a zero-delta drag"; the body prints `NOTE: verify no 'dequeued action=VOLUME' in log manually` and asserts only `dragState == "D_IDLE"`, which holds either way because `_volumeDragRelease()` clears the state whether or not it committed. The marker it needs is emitted, greppable, and already collected by two other ids in the same module. | `shell.py:103-107`; `winampDisplay.cpp:367-369`, `:496`, `:510`; cf. `shell.py:204` (`T082`) and `:2196` (`T151`) | Reuse `_tc_drag_collect(dut, cmd, ["enqueued ACT_VOLUME"])` and `fail()` if the list is non-empty — the exact inverse of `T151`, which already works. |
| **D-6** | **P2** | **The Settings tap geometry is hand-mirrored from firmware, including a re-implemented formula.** Four constants plus `_APP_LIST_ROW_H = min(_S_ROW_H, _S_CONTENT_H // _CONFIGURABLE_APP_COUNT)`, a Python transcription of `_appListRowH()`. `CONFIGURABLE_APP_COUNT` is in `app/gen/` — the generated header LL-114 says to parse, not mirror — and the whole point of that formula is that it changes when the app count grows. Drift lands the taps on the neighbouring row, and all six Settings ids then fail as if the firmware regressed. | `shell.py:2923-2932` vs `settingsSection.h:39-43`, `appsSection.h:256-259`, `app/gen/configurable_apps.h:4`; WP-B **B §3.1** | Parse `CONFIGURABLE_APP_COUNT` from `app/gen/configurable_apps.h` and the four `S_*` constants from `settingsSection.h`, the way `coords.py:12-38` already does for the skin and shell layouts. Seed WP-A **A-18**'s mirror gate with the pair. |
| **D-7** | **P2** | **Three ids grep for log markers the firmware never emits.** `"ACT_SEEK"` and `"seek commit"` appear nowhere in `app/src/` — `ACT_SEEK` exists only as an enum name and as the `"SEEK"` string of `actName()`. `T149` passes both markers to `_tc_drag_collect` and then **discards the result into `_`**; `T153` passes them plus `"D_POSBAR"` (which only ever appears inside a `get dragState` reply, not during a drag) and gates a `fail()` on the collected list, so `if lines: fail(...)` is unreachable. `T149`'s plan step 5, "assert serial log contains exactly one ACT_SEEK entry", is therefore both unimplemented and unimplementable as written. | `shell.py:2127-2128`, `:2279-2281`, `:2297-2298`; `spotifyTask.h:28`, `spotifyTaskStorage.cpp:331`, `winampDisplay.cpp:683`; `test_plan.md:1413` | Add a seek-commit log line to `_seekSink`'s call site (`winampDisplay.cpp:362`) — `LOG_D("touch", "enqueued ACT_SEEK ms=%ld")`, matching the ACT_VOLUME line right beside it — then make `T149` count it and `T153` assert its absence. Both bodies already have the collection plumbing. |
| **D-8** | **P2** | **`posbarDragMs` is the live drag-tracking value, not the committed seek, so "commits a seek" has no oracle anywhere in the suite.** `T149` claims a commit and `T154` claims "seeks to the pressed x position"; both read `_posbarDragCurrentMs`, which is written on Press-entry and on every Move. The actual commit — `_seekSink((long)_posbarDragCurrentMs)` at Release — has no serial observable and no getter. `T154`'s own failure text concedes it ("0 = Press-entry init broken"). | `winampDisplay.cpp:362`, `:389`, `:434`, `:737-740`; `shell.py:2134-2143`, `:2324-2330` | Same fix as D-7's log line, or a `get lastSeekCommit` accessor. Until one exists, restate both claims as "the seek *thumb* tracks x", which is what they prove. |
| **D-9** | **P2** | **New state-leakage cluster: `songDuration` (`C7`).** `T149`, `T150` and `T153` write `set songDuration 120000` and `T154` writes `60000`; **none restores**. Only `T085` restores, and it restores whatever a predecessor left. The firmware comment justifying the accessor says *"the next /me/player poll overwrites it"* (`winampDisplay.cpp:785-789`) — under TASK-243's persistent 403 there is no successful poll, so the injection is permanent for the run. A non-zero `songDuration` is exactly what makes POSBAR hittable, so this leaks into every later Spotify hit-test id, including `T088`'s `dead-posbar-*` DEADZONE expectations. Not in WP-B §5.2's six clusters. | `shell.py:2116`, `:2149`, `:2261`, `:2306` (writes); `:280-281`, `:291` (the only restore); `winampDisplay.cpp:785-791` | Wrap the four writes in a save/restore, or add a `songDuration` line to the runner's entry/exit snapshot (`runner.py:369-372`) so the leak is at least visible. Add `C7` to WP-B §5.2 and to `EDGE_ADJUDICATION`. |
| **D-10** | **P2** | **`T139` has no queue precondition and is vacuous whenever the queue is short.** It asserts that `scrollOffset` stays 0 after a swipe-down at 0 — but with fewer than `PLEDIT_ROW_COUNT` items the view has nothing to scroll and the offset cannot move whatever the clamp does. Its two siblings, `T137` and `T140`, both gate on `wait_for_queue`; this one was written without it, so under TASK-243 it is the one PLEDIT id that passes green while exercising nothing. Related: `T140` exits leaving `scrollOffset` saturated with no restore. | `shell.py:913-931` (no `wait_for_queue`) vs `:854`, `:942`; `:955-968` | Add `wait_for_queue(min_count=6)` to `T139` — the same gate `T140` uses — and move `T140`'s reset-to-0 from its prologue to a `finally`. |
| **D-11** | **P2** | **`T082`'s bound cannot detect the loss of the debounce it claims to verify.** The docstring says "debounce verified by count"; the assertion is `len(enqueue_lines) >= 2` over a 60-step drag. A firmware that lost its debounce entirely emits 61 enqueues and passes; only *under*-firing fails. The test already knows the step count. | `shell.py:192`, `:217-220` | Assert a two-sided bound: `2 <= n <= 12` (or whatever `VOLUME_DEBOUNCE_MS` implies at 60 samples), citing the firmware constant rather than a literal. |
| **D-12** | **P2** | **`T087` uses the split-read pattern that `_tap_and_wait_log` exists to eliminate, and hides the consequence behind a flake declaration.** Two `dut.cmd` calls sit between the LOGO tap that arms the TLS reset and the `readline` loop that looks for the reset line; `read_json` discards every non-JSON line while hunting for the tap reply, which is precisely how the async `spotifyTask` trace line gets eaten — the failure mode `_helpers.py:23-42` documents from a confirmed DUT capture. Every failure routes to `flake()`, and `T087` is declared, so the resulting `FLAKY-PASS` is neither PASS nor FAIL. Six unrelated assertions also share the id, so a failure names none of them. | `shell.py:389`, `:396`, `:404-416`; `_helpers.py:20-65`; `flaky.yaml:27-43`; `lib/results.py:227` | Rewrite the LOGO leg with `_tap_and_wait_log(dut, lgx, lgy, "hard reset")`, then split `T087` into its four region assertions plus a separate TLS-reset id — and re-evaluate the flake declaration once the race is gone (it names "spotifyTask/TLS timing paths" as the cause). |
| **D-13** | **P2** | **`T158` is `T157` with a weaker bound.** Identical `_vs_precondition`, identical three-command interleave, identical oracle field; `T157` asserts `1 <= so <= 3` and additionally checks the gesture really was in `D_PLEDIT_SCROLL`, `T158` asserts `so >= 1` and takes any tick reply it can find. Every regression `T158` can catch, `T157` catches first and more precisely. Two full precondition runs (queue wait + five reset drags each) for one assertion. | `shell.py:2400-2428` vs `:2435-2453` | Fold `T158` into `T157` and `resv` the id, or give `T158` a distinct integration window (e.g. `tick 100 20` asserting ≥ 3) so the pair brackets the velocity curve instead of nesting. |
| **D-14** | **P3** | **`T077`'s oracle is negative-only with a passing default.** `hit not in ("TRANSPORT","POSBAR","VOLUME")` — so `""` (a lost reply, via `r.get("hit","")`), `"CANVAS"` (the busy gate swallowed the tap), and any future region name all pass, and `ok` is never checked. `T088`, twelve lines of the same module away, asserts the positive `DEADZONE`/`FORCE_POLL` pair for the same class of coordinate. | `shell.py:66-71` vs `:466-469`; `cmdTouch.cpp:48-51` | Assert `hit == "DEADZONE"` and `action == "FORCE_POLL"`, matching `T088`. |
| **D-15** | **P3** | **Three defaulting oracles in the dangerous direction.** `T085`'s restore uses `r_save.get("ms", 180000)` — a lost entry read writes a fabricated 180 s duration instead of restoring; `T085`'s two assertions use `r.get("hit","")`/`r.get("action","")`, both of which pass; `T153` compares `rp_pre.get("ms", -1)` with `rp_post.get("ms", -1)`, so two lost replies compare equal and pass. Same class as WP-C **C-12**. The other 11 defaulting oracles in this corpus all default to a failing value and are fine. | `shell.py:281`, `:288-289`, `:2269`, `:2292` | Read into a variable, `skip()` if the field is absent, and never default an oracle to a value that passes. |
| **D-16** | **P3** | **`_PLEDIT_X`/`_PLSTART_Y`/`_PLEND_Y` are literals duplicating a derivation the same package already owns.** `140`/`163`/`150` are hardcoded in `_helpers.py` while `coords.pledit_swipe()` computes the equivalent geometry from the parsed skin constants, and both are used in the same family — `T137`/`T139`/`T140` take the derived path, `T155`–`T160` take the literal one. A skin-layout change moves one and not the other. | `_helpers.py:149-153` vs `coords.py:154-181`; `shell.py:866` vs `:2343` | Define the three from `coords.pledit_content_zone()` and delete the literals. |
| **D-17** | **P3** | **Two ids bundle enough assertions that a failure cannot be localised.** `T088` makes 11 hit checks under one id and `T087` makes six across four regions plus a cooldown and a log line; both accumulate into a single `fail()` string. Rubric S13's second clause. `T081`'s five-button loop is the acceptable version of this — one behaviour, five instances. | `shell.py:456-487`, `:364-418` | Parameterise: one id per region for `T087` (the regions are independent features), and leave `T088` as-is but record in the plan that it is a table-driven sweep, not a single behaviour. |

---

## 6. What the Spotify scope still covers under TASK-243

The owner account has had no Premium since TASK-243, so `/me/player` answers 403,
the queue snapshot stays empty and no track plays. The question this package was
asked: of the 27 `Spotify`-scoped FEATURE ids, how many still assert something
reachable, how many are vacuous or degraded, and which of those still claim
playback coverage in `test_plan.md`?

### 6.1 The headline, before the numbers

**The Spotify scope never asserted playback — not before TASK-243 and not now.**
Every oracle in all 27 bodies is one of four things: a region name from a
`cmdTap` reply, a `dragState`/`scrollAccum`/`scrollVelocity` value from the
gesture state machine, a `scrollOffset`/`posbarDragMs` counter, or a count of
debug-console trace lines. Not one reads a track name, a playback position, a
device volume, or an HTTP status. So TASK-243 has **not** quietly degraded this
scope from playback coverage into error-path coverage — there was no playback
coverage to degrade. What it has done is turn twelve of the twenty-seven into
permanent SKIPs and one into a vacuous pass, because the Winamp *view* under
test needs a non-empty queue to have anything to hit-test or scroll.

Nor is any of the 27 an "asserts the 403 error path" test: those live in the
`spotify-chrome` scope (`T-ERR-01`…`T-ERR-07`, `T-BGPOLL-*`), which WP-C audited
and which inject `lastHttp` rather than observing a live one.

### 6.2 The counts

| Bucket | n | Ids |
|---|---|---|
| **Reachable today** — no queue and no live session needed; asserts what it claims | **13** | `T077`, `T081`, `T082`, `T085`, `T087`, `T088`, `T096`, `T135`, `T149`, `T150`, `T151`, `T153`, `T154` |
| **Reachable but asserts nothing** (HOLLOW irrespective of TASK-243) | **1** | `T078` |
| **Degraded to a permanent SKIP** — gated on `wait_for_queue` or `_vs_precondition`'s queue ≥ 10, which the empty queue can never satisfy | **11** | `T134`, `T137`, `T138`, `T140`, `T152`, `T155`, `T156`, `T157`, `T158`, `T159`, `T160` |
| **Vacuous pass** — runs, passes, exercises nothing without a queue | **1** | `T139` (**D-10**) |
| **Never runs at all**, independently of the account | **1** | `T136` (**D-4**) |
| **total** | **27** | |

So **12 of 27 (44 %) produce no verdict** in a run today, one more produces a
false green, and the 13 that do work all live on the hit-test/gesture side of
the Winamp view. That the suite reads green through all of it is the S7 problem
WP-C named at the CORE level (**C-5**) reappearing across a whole scope: a SKIP
is invisible in the summary, so 12 dead cells look identical to 12 passing ones.

### 6.3 The six that still claim playback in `test_plan.md`

Six plan entries promise, in their Objective, Preconditions or Steps, something
the body does not and today cannot check:

| Id | What the plan claims | What the body does |
|---|---|---|
| `T078` | Objective: "must not enqueue `ACT_VOLUME`" (`test_plan.md`, T078 Objective) | Asserts `dragState`; defers the claim to a human (**D-5**) |
| `T081` | Preconditions: "Active Spotify device **playing a track**. `info` → `durationMs > 0`" | Never reads `durationMs`, never checks a device; pass detail says "Spotify effects: verify manually" |
| `T082` | Preconditions: "Active Spotify device with `supports_volume: true`"; Status records "Spotify volume effect manual: confirmed slider commit reaches `device.volume_percent`" | Counts local `enqueued ACT_VOLUME` log lines, which `injectTouch` emits synchronously whether or not any HTTP call succeeds |
| `T149` | Step 5: "Assert serial log contains **exactly one** `ACT_SEEK` entry during the drag" | Collects and discards; the marker does not exist (**D-7**) |
| `T155` | Step 3: "Assert serial log contains `ACT_PLAY_URI`" | Asserts `hit == "PLEDIT"` and that `scrollOffset` did not move |
| `T156` | Step 3: "Assert serial log does **NOT** contain `ACT_PLAY_URI`" | Substitutes a cooldown-duration proxy — documented in-body (`shell.py:2381-2382`), so this one is a defensible substitution rather than a silent gap |

Five of the six are genuine over-claims in the plan; `T156` documents its
substitution and is listed only for completeness. Note the shape they share:
every one of them names an **enqueue marker** as the oracle, and three of those
markers (`ACT_VOLUME` ×2, `ACT_PLAY_URI`) are emitted locally by the touch layer
and would work fine today — it is only `ACT_SEEK` that has no log line at all
(**D-7**). The playback-coverage claim in this scope is not blocked by TASK-243;
it is blocked by five bodies that never implemented their own plan step.

### 6.4 What would restore the 12

Nothing in the plan or the suite requires *Premium*; what these 12 require is a
**non-empty `g_queueSnapshot`**. The `set queue N` debug injection already seeds
that snapshot without an account (it is the mechanism the PLEDIT-row work used
when the same 403 blocked it), so `wait_for_queue` and `_vs_precondition` could
be given a seeded fallback and 11 of the 12 would run again. That is a
suite-side fix, not an account-side one, and it is the single highest-yield
change available to this corpus. Filed as **NEEDS-DUT #1** because the seeded
snapshot's interaction with the live-poll overwrite cannot be settled statically.

---

## 7. Counts

| Verdict | Spotify (27) | Matrix (3) | Life (4) | Weather (5) | Crypto (5) | Settings (6) | **Total** |
|---|---|---|---|---|---|---|---|
| SOUND | 15 | 1 | 2 | 2 | 2 | 6 | **28** |
| WEAK | 10 | 0 | 0 | 0 | 0 | 0 | **10** |
| HOLLOW | 1 | 1 | 1 | 1 | 1 | 0 | **5** |
| BROKEN | 1 | 1 | 1 | 2 | 2 | 0 | **7** |
| **total** | **27** | **3** | **4** | **5** | **5** | **6** | **50** |

* **HOLLOW:** `T078`, `T_MA_02`, `T_GOL_02`, `T_WX_02`, `T_CX_02`.
* **BROKEN:** `T136`, `T_MA_03`, `T_GOL_03`, `T_WX_03`, `T_WX_04`, `T_CX_03`, `T_CX_04`.

Smell histogram (occurrences across the 50 rows; a row may carry several):

| Code | Smell | Count |
|---|---|---|
| S7 | Skip-as-pass | 23 |
| S9 | Fixed-sleep synchronisation | 14 |
| S8 | Vacuous bound | 13 |
| S10 | Magic value | 13 |
| S5 | Swallowed failure | 9 |
| S13 | Overlap | 8 |
| S14 | State leakage | 8 |
| S1 | Unconditional pass | 6 |
| S3 | Tautology | 5 |
| S12 | Wrong-id / mis-scoped record | 5 |
| S2 | Ack-not-effect | 4 |
| S6 | Defaulting oracle | 3 |
| S11 | Double bookkeeping | 3 |
| S4 | Deferred to a human | 2 |

Three shifts against WP-C's histogram are worth recording, because they are
properties of the class rather than of the sample:

* **S7 is the dominant smell of the FEATURE class** (23 of 50 rows, versus 16 of
  49 in the gating classes) and here it is far more damaging, because a FEATURE
  id that skips blocks nothing and is simply absent from the run. Twelve of the
  23 are the TASK-243 queue gates (§6.2); the other eleven are precondition
  skips that WP-C's **C-5** would convert to a distinct blocking result.
* **S12 appears five times** where WP-C found none. Four are the D-1 ids, whose
  `(cls, scope)` record says `Matrix`/`Life`/`Weather`/`Crypto` while the body
  drives `cmdTap`'s app-independent fallback and asserts nothing about the named
  app; the fifth is `T136`, a registry entry with no body.
* **S6 is rarer still than WP-C measured** (3 rows, of which 3 are dangerous —
  D-15) because most of this corpus compares against exact values rather than
  reading optional fields.

---

## 8. NEEDS-DUT

Static reading cannot settle these. Each is stated as the question hardware
would answer.

1. **§6.4 — can `set queue N` revive the 11 queue-gated ids?** Does a seeded
   `g_queueSnapshot` survive long enough for `_vs_precondition`'s five reset
   drags plus the gesture, or does the next 403 poll clear it? If it survives,
   11 of the 27 Spotify ids come back for the cost of one helper change.
2. **D-2 — how long have the four residue ids been skipping?** They are the only
   ids in the corpus whose pass and fail paths were never both exercised. With
   the `skip()` changed to `fail()`, do all four pass on a healthy board?
3. **D-9 — does the `songDuration` leak change any later verdict?** `T088`'s
   `dead-posbar-*` cases and `T077` both hit-test near the POSBAR with whatever
   `T154` left. Run `T077`/`T088` immediately after `T154` versus in isolation.
4. **D-10 — is `T139` green today?** It should be, vacuously. Confirm it passes
   with an empty queue, which is the evidence that it is testing nothing.
5. **D-12 — `T087`'s flake rate with and without `_tap_and_wait_log`.** The
   flake declaration blames "spotifyTask/TLS timing"; the split-read race is a
   competing explanation and an A/B on the same board separates them.
6. **`T150`'s residual (§2).** If the POSBAR gesture is prevented from starting
   at all, does `T150` pass on `T149`'s leftover `posbarDragMs`? A single run
   with `T150` selected alone (no `T149` predecessor) answers it.
7. **`T_GOL_04`'s extinction risk.** Does the Life seed ever reach `golAlive == 0`
   within the first few generations on this board? If so the id has a real
   false-FAIL mode that no one has attributed yet.
8. **Whether the `LOG_D` oracles survive a full suite.** `T082`, `T096` and
   `T151` all depend on `LOG_D` lines; WP-C NEEDS-DUT #7 asks the same question
   for `T092`/`T094`/`T095`. One answer covers both packages.

---

## 9. Handover

* Findings that belong to WP-Z's consolidation rather than to this family:
  **D-1** and **D-2** (each names four ids and one firmware/helper decision),
  **D-4** (a registry/plan-archive integrity defect, not a test defect), and
  **D-9** (a new state-leakage cluster, `C7`, for WP-B §5.2's table).
* Cross-references to prior packages: **D-3** is cited from WP-B **B §5.3**, not
  re-derived; **D-6** extends **B §3.1** from the mirror side and seeds WP-A
  **A-18**; **D-15** is a new instance of WP-C **C-12**'s dangerous-default
  class; `T156`'s exposure to the `get cooldown` / `get shellCooldown` field
  collision is WP-C **C-18**; the S7 discussion in §7 is the FEATURE-class
  instance of WP-C **C-5**.
* The one structural contrast with WP-C worth carrying forward: the gating
  classes' failure mode is *a failure that does not block*; the FEATURE class's
  failure mode is *a test that does not run*. Twelve of the 27 Spotify ids and
  two of the four small-app pre-fetch ids produce no verdict at all in a normal
  run, and nothing in the summary says so.
* Nothing under `app/` or `run/` was modified. Nothing under `app/tools/` was
  imported except `suite.serialdbg.build_all_meta`. `./run/check-docs` was run
  once before handover; the C6 result is recorded in the index ledger entry for
  this package.
