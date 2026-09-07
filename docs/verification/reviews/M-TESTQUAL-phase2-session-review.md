# M-TESTQUAL Phase 2 — the hardware session

> Owner: **Verification Engineer**
> Status: **done** — ~3 h of board time, 2026-09-06 23:00 → 2026-09-07 01:1x
> Artifacts, copied out of `/tmp` to survive a reboot: **`~/tq2-session-20260906/`** —
> `run-phase1.txt` (193 verdicts), `serial-phase1.log` (1.49 MB raw), `p3a|b|c.txt` +
> `serial-p3a|b|c.log`, `settings-phase0.json`/`settings-phase4.json`; plus in-repo
> `app/tools/.runs/run-20260906T220505-1066098-8821d29d.json`
> (schema 1.2, run token `8821d29d137947b3`, board `d48afcc8eed0`)
> Date: 2026-09-06/07 · Board: CYD ESP32-2432S028R, two-USB, `cyd2usb_winamp_debug` (`-DBOD_WATCH`)
> Executes: [WP-Z §5](M-TESTQUAL-Z-findings-review.md) · Task: TASK-634 · also discharges TASK-645
> (`get boardId` hardware verification) and TASK-657 (four progress atoms' first hardware run)
> BP-075 binds: a criterion is closed only against the oracle it names; a human judgement is
> **ACCEPTED**, never PASS.

---

## 0. Session log

(appended as it happens; nothing here is written from memory)

### Phase 0 — pre-flight

| # | Step | Result |
|---|---|---|
| 0.1 | orphaned monitors (`pgrep -f '[p]io device monitor'`) | one, the session's own `spotify-mon`; no orphans |
| 0.2 | `./run/monitor-read 25` — uptime advancing, log mtime ~now | PASS. `uptime=00:03:34` advancing across three heartbeats, `/tmp/spotify-mon-serial.log` mtime 23:02:57 against a 23:03:01 wall clock. `build=Sep 2 2026-22:42:17` — the pre-session firmware |
| 0.3 | `./run/spiffs pull settings.json` — the `H-10` baseline | captured, `/tmp/tq2/settings-phase0.json`, 1427 B. `stock.mode="list"`, `clock.style="digital"`, `planeRadar.rangeIdx=1`, `webRadio.bitrateCap=128`, `player.mode=0` |
| 0.4 | `./run/check-datatask-certs` | **7/9 PASS, 2 ERROR** — see F-0 below |
| 0.5 | `./run/flash-debug` (permitted: `ENV_DEBUG=cyd2usb_winamp_debug` carries `-DBOD_WATCH`, so the TASK-557 pin holds) | SUCCESS in 37.8 s, 1 950 880 B, hash verified |
| 0.6 | `./run/dut-health` — pre-flight on the new build | 3/3 PASS, `[health] PASS — fit to test` |

**F-0 (new, environmental, real).** `nl1.api.radio-browser.info` and `at1.api.radio-browser.info`
**no longer exist in DNS** (`getent hosts` → NXDOMAIN for both; `de1` resolves and its chain
verifies). `run/check-datatask-certs` reports these as `ERROR … network unreachable from this
host`, whose own guidance says "may just mean this network can't reach the host — re-run from an
unrestricted network". That guidance is wrong here and misleads in the expensive direction: the
mirrors are gone upstream, and the firmware's mirror list still names them. This is a candidate
explanation for the intermittent WebRadio station-fetch failures the memory index records against
TASK-284 ("mirror truncation comes and goes, likely rate limiting"). **The gate cannot presently
distinguish a dead hostname from a sandboxed network** — a one-line DNS check would.

### TASK-645 — `get boardId` on hardware: **VERIFIED**

`run/dut-health` on the freshly flashed build wrote
`app/tools/.runs/run-20260906T220505-1066098-8821d29d.json` (schema **1.2**, run token
`8821d29d137947b3`). Its `premise.board`:

```json
"board": { "id": "d48afcc8eed0", "id_source": "efuse-mac",
           "transport": { "port": "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0",
                          "baud": 115200 } }
```

The pre-session run recorded `id: null, id_source: "absent"` on firmware predating the key. Both
arms of TASK-645's design are therefore exercised on real hardware: the honest degradation
(`absent`) and the identity (`efuse-mac`, twelve lowercase hex digits, matching `_BOARD_ID_RE`).
The harness half of the premise also resolves: `harness_version: "src-4d944baf37cb"` over 194
source files across `app/tools` + `run`, with git as provenance only (`git_dirty: true` — this
document). **TASK-645's owed hardware verification is discharged.**

### D-1 (new, P1) — the TASK-633 conversion had never been run against a board

Two defects, both fatal to every DUT entry point, both invisible to the 27-arm negative suite and
to `gate/check_entrypoint_lifecycle.py`, and both found in the first four minutes of hardware time.

**D-1a — wrong cwd: `No module named lib.verify_build`.** `run/lib.sh:470` ran
`( cd "$PIO_DIR" && … "$VENV_PY" -m lib.verify_build … )`. `$PIO_DIR` is `app/`; the `lib` package
is at `app/tools/lib`. Every one of the fourteen converted entry points therefore died with

```
/home/weiman/proj/esp/venv/bin/python3: No module named lib.verify_build
env failed with exit status 1.
```

before running a single test — **exit 1, which is neither the 3 nor the 4 the contract defines**,
so even the exit-code vocabulary ADR-067 built was bypassed. Reproduced on `run/test`; the call
site is shared, so it holds for all fourteen. Fixed in the working tree
(`cd "$PIO_DIR/tools"`), uncommitted, with the reason in a comment. **Without this fix there is no
Phase 2 session at all** — and no session since TASK-633 landed on 2026-09-06 could have run
either.

**D-1b — the preflight opens the port while the monitor still holds it.** `require_build` is
called *before* the monitor is stopped, deliberately ("a refusal here happens before the monitor is
touched, so a wrong-build run leaves the rig exactly as it found it" — `run/test-targeted:31-33`).
But the steady state of this rig is *monitor running* — `run/dut-health` restarts it on exit, and
CLAUDE.md documents that `run/flash*`/`run/test*` "kill it automatically". With a monitor up,
`run/test` now exits 3:

```
[test] could not address a board on /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0:
       SerialException: device reports readiness to read but returned no data
       (device disconnected or multiple access on port?)
  NO TESTS RAN. Rig condition (exit 3).
```

That is a **false RIG verdict**: the board is fine and on the right build. The old flash step used
to kill the monitor first; deleting the flash deleted the kill with it. Worked around here by
`./run/monitor-stop` before each entry point — **not** fixed in the tree, because the right fix is
a design question (stop-and-restore the monitor around the verify, versus documenting that the
monitor must be down) that belongs to the conversion's owner. It also means the exit-3 vocabulary
now fires most often for a cause that is not a rig fault at all, which is exactly the confusion
ADR-067 D2 was written to prevent.

### D-2 (new, P1) — the ELF-mismatch gate has been inert since 2026-08-17

The first line the fixed preflight printed is the finding:

```
[test] verified: board=d48afcc8eed0 (efuse-mac) elf=? expected=? build=cyd2usb_winamp_debug
```

`elf=? expected=?` means `Dut.elf` and `Dut.elf_expected` are both `None` — **no ELF comparison
was performed**, on the one run whose entire purpose per ADR-067 is to perform it. Cause
(`lib/dut.py:1219-1221`):

```python
_fw = (pathlib.Path(__file__).parent.parent / ".pio" / "build" / _DUT_ENV / "firmware.bin")
if _fw.exists():          # ← never true
```

`__file__` is `app/tools/lib/dut.py`, so `parent.parent` is `app/tools`, and it looks for
`app/tools/.pio/build/…`. That directory does not exist; the artifacts are at `app/.pio/build/…`
(verified: `ls -d app/tools/.pio` → no such file or directory). The whole `elf-mismatch`
`SetupFailure` — its banner, its exit code, `verify_build._WRONG_BUILD_REASONS`, and the
`premise.elf` field TASK-608 added — sits inside that dead `if`.

**When it broke, and why nobody saw it.** `git log --diff-filter=A` puts the expression's arrival
in `lib/dut.py` at `989c1ea` (2026-08-17, TASK-478), whose own message says the code was "moved
VERBATIM. Verified byte-identical against HEAD before committing." It was byte-identical, and that
is exactly the defect: in its old home, `app/tools/run_serialdbg_tests.py`, `parent.parent` *was*
`app/`. **A verbatim move is not path-safe when the moved code computes a path from `__file__`,**
and byte-identity is the check that cannot catch it. BP-017's "never test yesterday's binary"
guard has therefore been off for three weeks, across every run in that period, and TASK-633 built
its refusal contract on top of it without ever observing it fire.

Not fixed here: unlike D-1a this is not blocking the session, and a one-line path change to the
guard that decides whether a run is allowed to proceed should land with its own negative arm
(`lib/verify_build.py` already has the fixture hook — `build_root` — to write one).

### Why the gates missed D-1 and D-2 — and the general lesson

`gate/check_entrypoint_lifecycle.py` is a **text grep over the shell scripts**: `_UPLOAD_RE` looks
for `-t upload` on `$ENV_PROD`/`$ENV_*`, and rule C3 asserts only that the string
`require_build` *appears* in a script that opens a DUT (`:141-146`). It never executes
`require_build`, never resolves the cwd it runs the module in, and never checks that the module it
names is importable from there. Three checks, all satisfied by a call that cannot run.

That is the same shape as the register's own theme T2 one level up the stack: **an oracle that
cannot observe its subject**. WP-Z found it in 130 test bodies; here it is in the gate that
polices the entry points — and the entry points are where a wrong result is most expensive,
because a broken one produces no result at all and a false rig verdict instead. The finding is not
"someone forgot a path"; it is that **the entire ADR-067 conversion — fourteen entry points, a
27-arm negative suite, a blocking gate at zero — shipped without one execution against a board.**
Its two headline mechanisms (the refusal, and the ELF comparison the refusal is *for*) were both
dead, and every artefact in the programme says otherwise.

### Scope correction — four of WP-Z §5's targets no longer exist

Between WP-Z (2026-09-02) and this session, TASK-603/615/625 retired 18 ids. Four are named in
§5.2/§5.3 and are **moot, not unsettled**: `T194` (deleted, `G-6`), `T_WR_ERR_04` (deleted, `F-3`),
`T_WR_VOL_03` (UNOBSERVABLE, `F-7`), and `T_PLR_25`'s registry copy (deleted; the id lives on in
`test_playorder_player.py`, `E-2`'s false red gone with it). The live registry is **196 ids**
(`build_all_tests()`), classed **CORE 18 · FEATURE 175 · HEALTH 3 · RIG 3** — WP-Z's "43 CORE" is
two demotions out of date (TASK-591 43→23, TASK-626 23→18). The CORE skip census below is against
18, not 43.

---

## 1. Phase 1 — the full-suite run

Command, exactly as issued (redirected, never piped — a pipe through `tail` discards the summary):

```sh
systemd-inhibit --mode=block --who="VE phase2" --why="DUT suite run" \
  env LOG_FILE=/tmp/tq2/serial-phase1.log ./run/test > /tmp/tq2/run-phase1.txt 2>&1
```

Preflight line: `board=d48afcc8eed0 (efuse-mac)`, `build=cyd2usb_winamp_debug`, generation
`gen=12.1` at open (later 12.2, 12.3, 12.4 across the suite's own reboot tests).

### 1.1 `F-4` — WebRadio `set wrDeadUrls` / `_debugForceConnFail`: **CONFIRMED**

Every element of the prediction landed.

| Evidence | Value |
|---|---|
| `set wrDeadUrls 15` arms, in the raw log | six, at lines **12346, 12530, 12711, 12895, 13079, 13265** — the six `T_PLE_WR_155…160` bodies |
| first clear (`set wrDeadUrls 0`) | line **14219** — *inside `T237`*, ~950 lines later |
| `[W][webradio] play idx=N — forced connect-fail (debug wrDeadUrls)` | **45 occurrences**, spanning idx 0–9 |
| `T_WR_COEX_01` | **FAIL — `timeout — wrState=5 (expected 2 after set wrPlay 0)`** |
| `T_WR_COEX_02`, `T_WR_COEX_04` | **SKIP** — "not in PLAYING state" |
| `T_WR_HEAP_03`, `T_WR_HEAP_04` | **SKIP** — "could not reach PLAYING state" |

The flag is armed by six ids that do not clear it, stays armed across the whole gap, and the first
downstream id whose oracle needs a live connection fails **with `wrState=5`, the exact value the
flag assigns**. `flaky.yaml:72-108` attributes that symptom to radio-browser.info churn
(TASK-540). **That attribution is wrong**: no network was involved — the connect never left the
board. Five verdicts in this run (one FAIL, four SKIP) are products of a suite-order defect and
have been filed as network flake for about a year.

Note also that the two ids that legitimately drive the flag, `T237` and `T276`, **both PASS**, and
`T237` is the id that finally clears it. The injector works; only its custody is broken.

### 1.2 `G-1` — Stock `set triggerHeatmap` / `prevSubView`: **CONFIRMED, with a corrected mechanism**

The predicted verdicts are exact — six ids, the predicted skip string, verbatim:

```
[SKIP] T200  could not normalize to list view
[SKIP] T201  could not normalize to list view
[SKIP] T202  could not normalize to list view
[SKIP] T203  could not normalize to list view
[SKIP] T192  could not normalize to list view
[SKIP] T193  could not normalize to list view
```

(`T194`, the seventh in WP-Z's list, was retired by TASK-603 before this run.) The residue is
`chart`, as WP-Z's Phase 2 probe predicted — `get stockSubView` answers `"chart"` at every read
from line 3433 to line 9048, thousands of lines and several app switches later.

**What the run adds is the mechanism, and it is not quite the one WP-Z stated.** The raw log holds
the whole chain:

1. `T204` drills into a chart (`tap x=137 y=36` → `stockSubView` `list`→`chart`), taps a range tab
   (`x=256 y=9`), then **FAILs on the fetch** (`fetchOkCount did not advance on Ytd`) and exits.
   Its restore is on the pass path, so it leaves the app **in ChartDetail**.
2. `T196` runs `set triggerHeatmap 1` (line 3140). That is
   `_s.prevSubView = _s.subView` (`stockApp.cpp:248`) — and `_s.subView` is **ChartDetail**, not
   List. `prevSubView` is now ChartDetail.
3. `T196` then FAILs too (`heatmapCount still 0 after 60 s`), leaving the app in HeatmapDetail.
4. The next back tap runs `backToPrevView()`: `subView = prevSubView` → **ChartDetail**. The escape
   hatch on the following line — `if (_s.subView == HeatmapDetail) _s.prevSubView = List`
   (`stockApp.cpp:315`) — tests the *new* `subView`, which is ChartDetail, so it does **not** fire.
5. From here `backToPrevView()` is the identity: `subView = prevSubView = ChartDetail`. Confirmed
   directly in the log — three consecutive back taps, all landing
   (`{"cmd":"tap","x":10,"y":7,"hit":"STOCK","action":"CONSUMED","skipped":false}`, and
   x=10 < `ST_CHART_BACK_W*2` = 60, y=7 < `ST_CHART_HEADER_H` = 18, so `backToPrevView()` really is
   called), each followed by `stockSubView: "chart"`. Unchanged.

So the fixed point is real and the six SKIPs are real, but **`set triggerHeatmap` alone does not
create it** — statically, from a List view, it is escapable in one tap. It creates the fixed point
**only when a predecessor has already left the app in ChartDetail**, which on this run is a
*failed* test's residue. Two consequences:

* The defect is a **conjunction**, and that is why a year of isolated re-runs never reproduced it:
  the isolated arm cold-boots to List, so `triggerHeatmap` is harmless there.
* `stockApp.cpp:315`'s one-line escape hatch is written for the wrong variable. Testing the
  *outgoing* view (`if (prevSubView == ChartDetail) prevSubView = List`) would close it.

**A correction WP-Z would want on the record:** `T196` was predicted PASS ("with `T196` PASS behind
them"). It **FAILed**, for an unrelated reason (see §1.6), and that failure is a necessary link in
the chain above. The prediction's shape was right; its premise was not.

**§3's isolated re-runs settle the mechanism exactly** — see §3.2, which reproduces the whole
chain in three tests and shows the arming step does *not* require a failing predecessor.

### 1.3 `H-1` — PlaneRadar `set prInjectAircraft` / `_injected`: **REFUTED**

All eight PlaneRadar ids PASS, including the two the finding said were poisoned:

| Id | Verdict | The line that refutes the prediction |
|---|---|---|
| `T_PR_06` | **PASS** | `injected 3 aircraft -> prAircraftCount=3; prClearInject -> count=3 (real poll resumes)` |
| `T_PRI_01` | **PASS** | `offset 1.96px -> 0.71px (t+2s) -> 0.26px (t+4s), decaying toward 0 (tau=2s)` |
| `T_PR_01/02/03/04`, `T_PRM_01` | PASS | `T_PR_04` and `T_PRM_01` each survive a reboot; `T_PR_02` resolves a real first poll |

`_injected` is armed and then cleared inside the family, and no id downstream of PlaneRadar shows
a frozen radar. `T_PRM_02` FAILs, but on `TimeoutError: no JSON response within 3.0s` — a serial
timeout, not a stuck aircraft count (and it is the id `H-16` already flagged as the most
flake-exposed in its corpus, with a 300 s live-network window, on a night when the AP was
flapping — see §1.6).

**H-1 is refuted as a live defect.** The static reading of `planeRadarApp.cpp` was correct about
what `_injected` guards; what it could not see is that the family clears it. WP-Z said the finding
"costs no verdict today, and only by accident" — the hardware says it costs no verdict, full stop.

**A second finding falls out of the same eight lines.** `H-5` said `set prForceParseFail` has no
consumer anywhere and `T_PR_05` "has been a permanent SKIP since 2026-07-11". `T_PR_05` **PASSED**:
`error code=-92 -> activeError.active=true, responsive, recovered -> activeError.active=false`.
The hook has a consumer and the id reaches a verdict. `H-5` is **stale**, not wrong-at-the-time —
something between WP-H and this run wired it up. `flaky.yaml:157` and the plan row still say
otherwise and should be corrected.

**One thing to be careful about.** Because the harness's own settings-restore step reboots the
board (§4), the *post-run* residue probes WP-Z §5.2 Phase 2 planned — `get prAircraftCount`
predicted 1 and frozen — were **not available**: by the time the console was reachable the board
had rebooted and answered `prAircraftCount=0`, `wrState=0`, `stockSubView=list`. That is WP-Z
§5.1's own warning about step 5b, now confirmed operationally. The refutation above therefore
rests on the in-run verdicts and the raw serial log, not on a residue read — which is the stronger
evidence anyway, because it is *in situ*.

### 1.4 The CORE skip census (`C-5`): **17 of 18 reach a verdict**

| Class | Result |
|---|---|
| CORE ids in the live registry | **18** (WP-Z's 43, after TASK-591 and TASK-626) |
| PASS | **17** |
| SKIP | **1** — `T_BI_03`, `queue count<2 after 30s — Spotify not playing?` |
| FAIL | 0 |

`C-5`'s structural claim — a `skip()` exit does not match `_gate.py`'s `FAIL`-prefix test, so a
failed CORE precondition gates nothing — **remains true as written**. Its *magnitude* claim
("31 of 43 CORE ids have a `skip()` exit", presented as the reason the CORE block "almost never
fires") is, in practice on a real run, **one id**. The class is in far better shape than the
static count suggested, and the reason is TASK-591/TASK-626: the demotions took the network-fragile
ids out of CORE, which is exactly the fix the finding implied. The one remaining skip is
`T_BI_03`, and §2 below removes it.

### 1.5 `T_BI_03` — does `set queue N` satisfy `wait_for_queue(min_count=2)`? **YES**

The last row of the gating-offline ledger, answered with two console commands on the live board:

```
> set queue 5
[D][spotify.queue] injected count=5 seqno=1
{"ok":true,"cmd":"set","var":"queue","val":"5"}
> get queue
{"ok":true,...,"part":0,"last":false,"idx":0,"track":"Track 00",...}
{"ok":true,...,"part":1,"last":false,"idx":1,"track":"A Very Long Track Title That Must Truncate 01",...}
{"ok":true,...,"part":2,"last":false,"idx":2,"track":"Track 02",...}
{"ok":true,...,"part":3,"last":false,"idx":3,"track":"A Very Long Track Title That Must Truncate 03",...}
{"ok":true,...,"part":4,"last":true, "idx":4,"track":"Track 04",...}
```

`Dut.wait_for_queue` counts parts containing a `track` key (`lib/dut.py:1176`). Five parts, five
`track` keys, `5 >= 2` on the first poll. **The injection satisfies the precondition.**

`gating_offline_exceptions.md:73,130` deferred exactly this question to this session and predicted
it "would clear the row with no class change". **It does.** `T_BI_03` needs two lines — a
`set queue 5` before `wait_for_queue`, and a restore — and then the gating-offline ledger is empty
and CORE reaches 18/18 offline. Note the raw log confirms the id does **not** do this today:
`[spotify.queue] injected count=` appears **zero** times in the 1.49 MB Phase 1 log.

### 1.6 The environment, stated plainly — and what it cost

This is the premise every Stock, Weather, Crypto, Teletext and WebRadio verdict in Phase 1 sits on,
so it goes before the results that depend on it rather than after.

**The AP was flapping and DNS was failing all night.** Evidence, in order of directness:

* `[E][WiFiGeneric.cpp:1583] hostByName(): DNS Failed for query1.finance.yahoo.com` in the raw log,
  immediately before `heatmap GET -1 elapsed=9ms` — the "9 ms fetch" is a DNS failure, not a fetch.
* The same for `api.spotify.com` during a Phase 3 boot.
* A `run/test-targeted` boot that **never associated at all**: `SETUP-FAIL wifi-not-connected
  cls=HEALTH`, "not connected within 100s of the port-open reset (25s + a 75s extension)". Correctly
  classed HEALTH, correctly exit 4, no tests run — the machinery worked.
* A later heartbeat: `wifi=rssi(-58) disc=65` — signal fine, **65 disconnects**.

**F-0's DUT consequence, confirmed.** `T_WR_TLS_01` **FAIL**: `station fetch failed on all mirrors
after both TLS paths: http=-120 count=0`. Two of the three mirrors it tries no longer resolve
anywhere (§0, F-0). Four more ids then SKIP on `station list unavailable`. So the dead-hostname
finding is not a host-side curiosity: it costs one FAIL and four SKIPs per run, and the host gate
that should have caught it reports the same condition as "network unreachable from this host".

**What the operator must not do with this.** Nine Phase 1 failures are attributable to the network
(`T186`, `T187`, `T204`, `T196`, `T_WR_TLS_01`, `T_PRM_02`, `T_PLR_01`, `T088`, and `T_DTP_01`'s
UNMET). They are **not** evidence about the firmware, and re-running them on a good night is the
only way to know. They are, however, excellent evidence about the *suite*: see §1.7.

### 1.7 `G-10` confirmed on hardware — three failure messages that name the wrong cause

WP-Z's `G-10` said three Stock messages attribute an upstream timeout to a named firmware fix. All
three fired, and every one of them is wrong about why:

| Id | What the suite printed | What the log shows |
|---|---|---|
| `T186` | `fetchOkCount did not advance after 45 s for MSFT — guard fix may not have landed` | `DNS Failed for query1.finance.yahoo.com` |
| `T187` | `… for NVDA — guard fix may not have landed` | same |
| `T204` | `fetchOkCount did not advance on Ytd (cycle 1/6) — **heap pressure failure?**` … followed by three `_diag_snapshot`s showing `freeInt=107580 → 107564`, a **16-byte** change | same |

`T204`'s message is the sharpest example in the review of an oracle indicting the wrong subject:
it asks "heap pressure failure?" while printing, in its own failure string, the heap numbers that
refute the question — and `G-17` is exactly right that nothing ever compares them. A reader
following these three messages goes looking for a missing guard fix and a heap leak, on a night
when the actual cause is one line in the raw log that the suite already captured. Fixing this is
cheap: the `dataTask` layer knows it got `http=-1`/DNS, and the message should say so.

### 1.8 Other §5.2 rows, settled

| Row | Prediction | Hardware | Verdict |
|---|---|---|---|
| `D-10` — `T139` passes green while exercising nothing | PASS with an empty queue | **PASS**, `scrollOffset stays 0 on swipe-down at minimum` — and `get queue` was `count:0` all run | **confirmed** |
| `B-3`/`D-3` — `T_WX_04` and `T_CX_04` can never run | both SKIP | **split**: `T_WX_04` **PASS** (`weatherReady=false on switch-in — pre-fetch state confirmed`); `T_CX_04` **SKIP** (`cryptoReady=true immediately — data arrived before check`) | **half refuted** — the finding is right about `T_CX_04`'s mechanism and wrong that it generalises |
| `E-6` — negative assertions on a channel that can be off | `[D]` lines may be absent | **3 377 `[D]` lines** in the raw log; `T_PLR_18` and `T_PLR_19` both PASS | **not realised this run** — the channel was live, so those assertions meant something. The structural risk stands |
| `H-8` — a tap swallowed by the busy gate passes on its predecessor's residue | `"skipped":true` in `T270`/`T271`'s taps | **9** `"skipped":true` replies in the run; `T270`/`T271` both PASS, and `T270`'s own string reports `shellBusy=true confirmed` | **not reproduced for those two ids**; the discarded-flag risk is real and visible elsewhere (§1.9) |
| `H-18` — `T_CLK_11`'s 4096 B bound on a path that allocates nothing | the bound was never a threshold | **PASS, `leak=0B (before=108272 after=108272)`** — byte-identical | **confirmed**: the bound has 4096 B of slack against a measured 0 |
| `C-7` — flake declarations mismatched in both directions | `T092`, `T_PLR_07` call `flake()` undeclared | **both FAIL with `UNDECLARED flake — no entry in flaky.yaml`** | **confirmed, and now enforced** — TASK-626's gate turns the bookkeeping mismatch into a real FAIL, which is the correct outcome |
| `D-12` — `T087`'s split-read race hidden behind a flake declaration naming a different cause | — | **FAIL: `declared flake REPRODUCED on retry`** | the flake policy failed closed, exactly as `lib/results.py` is designed to |

### 1.9 A new firmware defect the suite found on its own: `T078`

```
[FAIL] T078  zero-delta drag at (140,63) COMMITTED a volume change:
             ['[D][touch] enqueued ACT_VOLUME pct=49'] — the deadband is not holding
```

WP-Z's `D-5` filed `T078` as an id that "defers its whole claim to a human
(`NOTE: verify … manually`) and asserts a resting state that holds either way". That is no longer
true — the body now greps the marker `D-5` said was "emitted, greppable, and already collected by
two other ids" — and the moment it did, it caught a real touch-input regression: a **zero-delta**
drag enqueues `ACT_VOLUME`. This is the review's own thesis demonstrated end to end: the id was
hollow because nobody had pointed it at the available observable, and pointing it there found a
bug on the first hardware run. `D-5` should be recorded **fixed, and vindicated**.

### 1.10 TASK-657 — the four progress atoms' first hardware verdicts

| Id | Verdict | Evidence |
|---|---|---|
| `T_DTP_01` | **UNMET** | `premise not established: no fetch completed inside the window — stockQuoteProgress was polled 2741x and saw [-1]` |
| `T_DTP_02` | **PASS** | `stockChartProgress left the sentinel (saw [0, 1, 2]), stayed inside (0, 2), and returned to -1` |
| `T_WX_07` | **FAIL** | `weatherFetchPhase never left the -1 sentinel across a completed fetch (1 polls)` |
| `T_CX_07` | **FAIL** | `cryptoFetchPhase never left the -1 sentinel across a completed fetch (1 polls)` |

Three observations, in decreasing confidence.

1. **`T_DTP_02` is a clean PASS and the design works.** It saw `[0, 1, 2]`, stayed inside its
   declared domain and returned to the sentinel — all three clauses, on a real fetch. The
   M-DATATASK-PROGRESS atom mechanism is demonstrated on hardware for the first time.
2. **`T_DTP_01`'s UNMET is the typed verdict doing its job.** No fetch completed (the DNS failure),
   so the premise did not hold, and TASK-624's `UNMET` says so instead of reporting a green or a
   red. 2 741 polls, all `-1`. This is the right outcome and it says nothing about the atom.
   TASK-660 narrowed this id's domain clause to `(0,0)` two days ago; **that narrowing is still
   unexercised on hardware** and TASK-657 is not fully discharged for `T_DTP_01`.
3. **`T_WX_07` and `T_CX_07` FAIL, and the number to be careful about is `(1 polls)`.** The claim —
   the atom is never written — would be a real firmware gap. But a single poll inside the window is
   too thin to carry it: the id may simply have sampled once, after the fetch completed and the
   atom had returned to `-1`. Compare `T_DTP_02`, which polled enough to see `[0, 1, 2]`. Under
   BP-075 these two are **FAIL as recorded** — that is what the oracle they name returned — but the
   *diagnosis* is open, and the first action is to find out why the poll loop ran once. Filing them
   as "the weather/crypto atoms are missing" on this evidence would repeat the mistake §1.7 is
   about.

**Diagnosis, from the raw log — they are test defects, not firmware defects.** The relevant lines
are consecutive:

```
19406: {"ok":true,"cmd":"get","var":"weatherReady","ready":true,"last":true}   ← fetch already done
19434: {"ok":true,"cmd":"get","var":"weatherFetchPhase","val":-1,"last":true}  ← poll 1
19435: {"ok":true,"cmd":"get","var":"weatherReady","ready":true,"last":true}   ← done() → break
```

and identically for crypto at 19584 / 19648 / 19649. `_observe_progress_atom`
(`_helpers.py:420-432`) polls the atom, then calls `done()`, and **breaks the moment `done()` is
true**. `_ready_flag` (`shell.py:1637-1644`) reads `weatherReady`/`cryptoReady`, which are latched
"data has arrived" flags, not per-fetch edges — and `_switch_to(dut, "Weather")` completes the
fetch *before* the polling starts. So the loop takes exactly one sample, of an atom that has
already returned to its sentinel, and reports "never left the sentinel".

The helper's docstring gets the contract half right: "the atom is what is under test, so
[`done()`] must never also be the thing that says the fetch finished." The missing half is that
**`done()` must also be FALSE when the loop starts**. `T_DTP_02` passes because it triggers its
own chart fetch and its oracle really does start false; `T_CX_04`'s SKIP this run
(`cryptoReady=true immediately — data arrived before check`) is the same latched flag, caught
honestly by a different id in the same corpus.

So: `T_WX_07` and `T_CX_07` **FAIL** (recorded as such — BP-075), the **firmware is not
implicated**, and the fix is an entry-guard in `_observe_progress_atom` — refuse to start, as
`UNMET`, when `done()` is already true — plus a forced fetch in both bodies. That entry-guard
would also have converted this run's two red cells into two honest UNMETs.


---

## 2. Phase 2 — console probes

Mechanism: `./run/monitor-start`, commands typed into the tmux pane, `./run/monitor-read` to
collect — the one step WP-Z §5.2 deliberately lists as not a `run/` script. No flash, no restore.

Two results are recorded above where they belong: `get boardId` (§0, TASK-645) and the `set queue`
probe (§1.5, `T_BI_03`). The direct `get boardId` reply is worth quoting once in full, because it
is the primary artefact of TASK-645's hardware verification and does not depend on any harness
parsing:

```
{"ok":true,"cmd":"get","var":"boardId","val":"d48afcc8eed0","src":"efuse-mac","rev":3,"last":true}
```

Independently corroborated by `esptool` during the session's own SPIFFS write:
`MAC: d4:8a:fc:c8:ee:d0`. The identity is the board's, it is stable across reboots, and it does not
come from the port.

**The residue probes could not be taken.** `run/test`'s step 5b (settings restore) pushes SPIFFS,
which hard-resets the board, so by the time the console was reachable the post-suite state was
gone: `stockSubView=list`, `wrState=0`, `prAircraftCount=0` — all boot defaults. WP-Z §5.1
predicted exactly this and asked for the diff to be "pulled between the runner exiting and the
trap completing — which is not possible from outside the script". Confirmed: it is not. Everything
those probes were meant to establish was instead read out of the raw serial log, in situ, which is
better evidence — but the finding stands that **`run/test` destroys its own run's residue**, and
`H-10` cannot be measured through it.

---

## 3. Phase 3 — isolated versus in-suite

### 3.1 `F-4` — `T_WR_COEX_01`

| Arm | Verdict | Message |
|---|---|---|
| in-suite (Phase 1) | **FAIL** | `timeout — wrState=5 (expected 2 after set wrPlay 0)` |
| isolated (`./run/test-targeted T_WR_COEX_01`) | **SKIP** | `station list unavailable (network or fetch failure)` |

The split is real: **`wrState=5` does not occur in isolation.** The prediction was "isolated PASS
vs in-suite FAIL"; what happened is "isolated SKIP", because the isolated arm hit the independent
dead-mirror failure (F-0) before it could reach the state under test. So the arm is **contaminated
and cannot deliver a clean PASS tonight** — but it does not need to: the discriminating
observation is the *symptom*, and `wrState=5` — the value `_debugForceConnFail` assigns, reached
without touching the network — appears only when the six PLEDIT ids have run first. Combined with
the 45 `forced connect-fail` lines and the arm/clear line numbers in §1.1, `F-4` is confirmed;
this arm adds that the symptom is order-dependent, not environmental.

### 3.2 `G-1` — `T200`, and the mechanism reproduced in three tests

| Arm | Verdict |
|---|---|
| in-suite (Phase 1) | **SKIP** — `could not normalize to list view` |
| isolated (`./run/test-targeted T200`) | **PASS** |
| ordered (`./run/test-targeted T204,T196,T200`) | `T204` **PASS** · `T196` **FAIL** · `T200` **SKIP** |

This is the session's cleanest result. The third run reproduces the defect **deterministically in
about five minutes**, and its raw log holds the entire chain with no inference left in it:

```
211: tap x=137 y=36 → CONSUMED          213: stockSubView "list" → "chart"     (T204 drills in)
428: tap x=148 y=9  → CONSUMED                                                 (T204's last tab tap)
479: set triggerHeatmap 1               480: stockSubView "heatmap"            (T196 — prevSubView := ChartDetail)
550: stockSubView "heatmap"             553: tap x=220 y=10 → CONSUMED         (T200 normalize, heatmap back zone x>190)
557: stockSubView "chart"                                                      ← backToPrevView() → prevSubView
561: tap x=10  y=7  → CONSUMED          563: stockSubView "chart"              ← identity
567: tap x=10  y=7  → CONSUMED          569: stockSubView "chart"              ← identity → SKIP
```

**And it corrects §1.2's own refinement.** `T204` **PASSED** here and the latch still armed — so
the arming condition is *not* "a failed predecessor". It is simply that `T204` leaves the app in
ChartDetail on **either** path (it has no restore to list), and `set triggerHeatmap` then executes
`_s.prevSubView = _s.subView` (`stockApp.cpp:248`) with `subView == ChartDetail`. From there:

* `backToPrevView()` sets `subView = prevSubView` → ChartDetail;
* the escape hatch on the next line, `if (_s.subView == HeatmapDetail) _s.prevSubView = List`
  (`stockApp.cpp:315`), tests the **incoming** view, which is now ChartDetail, so it never fires;
* every subsequent chart back tap is the identity — verified twice, with the taps landing
  (`x=10 < ST_CHART_BACK_W*2 = 60`, `y=7 < ST_CHART_HEADER_H = 18`, `"action":"CONSUMED"`).

**`G-1` is confirmed** — six ids permanently SKIP in a full run, and the isolated arm passes, which
is why a year of re-runs never caught it. Two corrections to the finding as written:

1. The escape hatch at `stockApp.cpp:315` exists and is one word wrong. Testing the *outgoing*
   view — `if (_s.prevSubView == ChartDetail) _s.prevSubView = List` — closes the fixed point.
   This is a **one-line firmware fix**, not a test change, and it is worth stating that way to
   @Architect.
2. `set triggerHeatmap` is not sufficient on its own. From a List view it is escapable in one tap.
   The defect is the **conjunction** of "a predecessor left ChartDetail" and "`triggerHeatmap`
   captures whatever is current", which is precisely the shape `_order.py`'s 0→1-edge enumeration
   cannot see (`B-4`) — a concrete instance of that finding, on hardware.

---

## 4. Phase 4 — close-out and board state

| Step | Result |
|---|---|
| `./run/spiffs pull settings.json`, diffed against the Phase 0 baseline | **one drift**: `player.mode` `0` → `1` (Spotify → WebRadio) |
| restore | `player.mode` written back to `0` and pushed; re-pulled and verified — the file is now **byte-equivalent to the Phase 0 baseline** (`clock digital`, `stock list`, `prRange 1`, `player.mode 0`) |
| monitor | `./run/monitor-start` — running, `spotify-mon`, disk log `/tmp/spotify-mon-serial.log` |
| firmware | `cyd2usb_winamp_debug` (`-DBOD_WATCH`), `build=Sep 6 2026-23:04`, elf `732c8567`. **Production was never flashed and never restored.** The TASK-557 pin held for the whole session |

**On `H-10`.** The finding predicted the corpus leaves the user's persisted settings changed "only
by luck". One value out of the whole file drifted across a full suite plus four targeted runs, and
it drifted during the **targeted** runs — `run/test-targeted` has no settings snapshot at all,
unlike `run/test`. That is the gap worth recording: the entry point CLAUDE.md sends you to for
everyday work is the one with no settings custody.

---

## 5. Ledger — the 58 NEEDS-DUT items

**Settled this session: 21.** Not the ~32 WP-Z projected, and the reasons are worth naming rather
than averaging away: four target ids were retired before the run (scope correction, §0); the
post-run residue probes were destroyed by the harness's own restore (§2); the network took nine
verdicts out of play (§1.6); and roughly ninety minutes of board time went into finding and
working around D-1, which was not in anyone's plan.

| Settled | Result |
|---|---|
| `F-4` armed-injector confirmation (WP-F #1) | **CONFIRMED** §1.1 |
| `G-1` armed-injector confirmation (WP-G #1) | **CONFIRMED**, mechanism corrected §1.2/§3.2 |
| `H-1` armed-injector confirmation (WP-H #1) | **REFUTED** §1.3 |
| `H-5` — `set prForceParseFail` has no consumer, `T_PR_05` a permanent SKIP | **STALE** — `T_PR_05` PASSES §1.3 |
| `C-5` CORE skip census (WP-C #6) | **17/18 reach a verdict** §1.4 |
| `T_BI_03` / `set queue` (gating-offline ledger's last row) | **YES — clears with no class change** §1.5 |
| `F-4` isolated-vs-in-suite split (WP-F #2) | **established** §3.1 |
| `G-1` isolated-vs-in-suite split (WP-G #2a, #2b) | **established, both arms** §3.2 |
| `B-3`/`D-3` — `T_WX_04`, `T_CX_04` (WP-B N-B1) | **half refuted** §1.8 |
| `D-10` — `T139` (WP-D #4) | **CONFIRMED** §1.8 |
| `E-6` — `[D]` channel live? (WP-C #7, D #8, E #1) | **live this run** §1.8 |
| `H-8` — `"skipped":true` at `T270`/`T271` (WP-H #6) | **not reproduced** §1.8 |
| `H-18` — `T_CLK_11`'s 4096 B bound (WP-H #8) | **CONFIRMED** — measured 0 B §1.8 |
| `G-17` — the `_diag_snapshot`s nobody compares (WP-G #6) | **CONFIRMED** — 16 B of movement under a "heap pressure?" message §1.7 |
| `G-10` — messages naming the wrong cause | **CONFIRMED**, all three §1.7 |
| `C-7` flake-declaration mismatches | **CONFIRMED and now enforced** §1.8 |
| `T_DTP_01` first hardware verdict (TASK-657) | **UNMET** §1.10 |
| `T_DTP_02` first hardware verdict (TASK-657) | **PASS** §1.10 |
| `T_WX_07` first hardware verdict (TASK-657) | **FAIL** — test defect diagnosed §1.10 |
| `T_CX_07` first hardware verdict (TASK-657) | **FAIL** — test defect diagnosed §1.10 |
| `D-5` — `T078` defers its claim to a human | **fixed since WP-Z, and it caught a real bug** §1.9 |

**Still open, with the reason:**

* `H-10` (what the suite leaves in persisted settings) — measurable only in part; `run/test`
  restores and reboots before it can be read (§2). One drift observed via the targeted runs (§4).
* The `T_WR_ERR_*`, `T_WR_VOL_03`, `T194` and `T_PLR_25` items — **moot**, the ids are retired.
* Everything WP-Z §5.5 already listed as needing other firmware, a code change first,
  `run/screendump`, or repetition. Nothing in this session moved those.
* `T_DTP_01`'s TASK-660 domain narrowing — still unexercised; needs a run with working DNS.
* The nine network-attributable failures (§1.6) — need a re-run on a good night before any of them
  can be read as evidence about the firmware.

---

# Session B — 2026-09-07: the items session A could not reach

> Owner: **Verification Engineer**
> Status: **done** — ~2 h of board time, 2026-09-07 08:00 → 10:1x
> Artifacts, copied out of `/tmp` to survive a reboot: **`~/tq2b-session-20260907/`** —
> `NOTES.md` (written incrementally during the session), and per run a `run-*.txt` stdout
> capture plus its `serial-*.log` raw capture: `atoms`, `stock` (interrupted) / `stock2`,
> `wr`, `plr18`, `plr1718`, `t150` (SETUP-FAIL) / `t150b`.
> Board: `d48afcc8eed0`, `cyd2usb_winamp_debug` (`-DBOD_WATCH`), elf **`5c6d6eca`**
> Executes: TASK-634 remainder · discharges TASK-657 and TASK-660 · lands TASK-579 and TASK-580
> BP-068, BP-073, BP-074, BP-075 bind. Production was never flashed. The TASK-557 pin held.

Session A's four named causes for reaching only 21 of 58 were: four ids retired before the run,
the harness's own restore destroying the residue window, a flapping AP, and ~90 minutes lost to a
broken rig. Only the third recurred here, and only once.

**Every run in this session recorded a real ELF comparison** — `elf=5c6d6eca expected=5c6d6eca`
on all seven. D-2's guard, dead for three weeks until `2ae9374`, is now doing its job on every
entry.

---

## B.1 TASK-657 — the four progress atoms, at real verdicts

Session A §1.10 recorded `T_WX_07`/`T_CX_07` as FAIL and diagnosed them as **test** defects. The
diagnosis was right, and the fix confirms it.

**What was wrong.** `_observe_progress_atom`'s docstring stated half its contract — `done()` must
not also be the atom. The missing half is that **`done()` must be FALSE when the loop starts**.
Both ids handed in `_ready_flag(dut, "weatherReady"/"cryptoReady")`, and those flags are
*latched*: `WeatherApp::_dataReady` is set true on the first good parse and never cleared
(`weatherApp.cpp:107`), likewise `CryptoApp`. After the app's first success they answer true
forever, so the loop took exactly one sample of an atom that had long since returned to `-1`.

**The fix, in three parts.**

1. An **entry guard** in `_observe_progress_atom` (`_helpers.py`): if `done()` is already true at
   entry, return `preheld` and take no sample. `_progress_atom_verdict` adjudicates that as
   **UNMET**, not FAIL — a completion oracle that is already satisfied cannot bracket a fetch, so
   there is no verdict to give. This alone would have turned session A's two red cells into two
   honest UNMETs.
2. A real per-fetch edge oracle, **`_dataq_fetch_edge(dut, fetch_type)`**, off `get dataq`'s
   `pendingMask`/`inFlight`. Those are the queue's own bookkeeping — `pendingMask` is set in
   `enqueue()`/`enqueueWeather()` and cleared by the dispatch loop after the fetch function
   returns (`dataTaskStorage.cpp:1715`) — so the oracle is maintained *outside* the fetch body
   that writes the progress atom, and stays independent of its subject.
3. The window widened 30 s → 80 s, because `WEATHER_FETCH_MS` and `CRYPTO_FETCH_MS` are both
   60 000 ms: a worst case is a full cadence wait plus the fetch. At 30 s these ids could only
   ever have produced UNMETs on a healthy board.

`_ready_flag` was **deleted** rather than left in place, with a comment saying why, so it cannot
be reached for again.

**The new mechanism ships with its own negative arm.** `D-2`'s lesson was that a guard nobody has
watched fire is a guard that is not there, so `test_progress_atoms.py` gains **arm N7**: a
`done()` that is already true at entry must produce `preheld`, **zero** samples, no reads at all,
and an **UNMET** whose message names the real cause. Running the suite before the fix reproduces
session A's exact red cell; after it, N7 passes and `run/check` gate 8 is green at 11/11. `N6`'s
fixture needed one adjustment — the guard calls `done()` once before the window, so its oracle now
completes on call 6 rather than 5 to keep five window polls. That coupling is itself worth noting:
`N6` was asserting against a `done()` call count, which is why a change to the observer's
call pattern broke it.

**The verdicts** (`run-atoms.txt`, run token `50f0091f496941e6`, artifact
`app/tools/.runs/run-20260907T081143-1407000-50f0091f.json`, exit 0):

| Id | Verdict | Observation |
|---|---|---|
| `T_DTP_01` | **PASS** | 58 polls, saw `[-1, 0]`, domain `(0,0)`, completed, returned idle |
| `T_DTP_02` | **PASS** | 65 polls, saw `[1, 2]` |
| `T_WX_07` | **PASS** | 48 polls, saw `[1]` |
| `T_CX_07` | **PASS** | 168 polls, saw `[-1, 1]` |

**4 passed, 0 failed, 0 skipped.** The firmware writes all four atoms. **TASK-657 is discharged in
full**, and **TASK-660's `(0, 0)` narrowing for `stockQuoteProgress` is exercised on hardware for
the first time** — `T_DTP_01` saw exactly `{0}`, which is what session A left owed.

One thing to keep in proportion: three of the four saw a *subset* of their domain (`[1]`, `[1,2]`,
`{0}`). That is sampling, not a defect — the domain clause is an upper bound on what is legal, not
a requirement to observe every value. No id saw anything outside its domain.

## B.2 TASK-580 / `G-1` — the one-line firmware fix, and what it freed

**The change** (`app/src/stock/stockApp.cpp`, `backToPrevView()`):

```cpp
-  if (_s.subView == StockSubView::HeatmapDetail) _s.prevSubView = StockSubView::List;
+  if (_s.subView != StockSubView::List)         _s.prevSubView = StockSubView::List;
```

Session A §3.2 recommended testing the *outgoing* view. At this line `subView` has just been
assigned from `prevSubView`, so the two formulations coincide; the form above states the actual
invariant — **List is the back target of any detail view you land on** — and subsumes the old
HeatmapDetail case rather than sitting beside it. Built clean (RAM 35.6 %, Flash 74.2 %), flashed
with `run/flash-debug` (permitted: `ENV_DEBUG` carries `-DBOD_WATCH`), elf `5c6d6eca`.

**The verdicts** (`run-stock2.txt`, run token `c0e941afa58643dc`, artifact
`run-20260907T082835-1417216-c0e941af.json`, exit 0, gen 30.1):

| Id | Session A (full suite) | Session B |
|---|---|---|
| `T200` | SKIP — could not normalize to list view | **PASS** — HEAT tap in list → subView=heatmap |
| `T201` | SKIP — same | **PASS** — HEAT tap in heatmap → subView=list (back) |
| `T202` | SKIP — same | **PASS** — tile tap → ChartDetail; drilled symbol='NVDA' |
| `T203` | SKIP — same | **PASS** — chart back → subView=heatmap (prevSubView preserved) |
| `T192` | SKIP — same | **FAIL** — see B.2.2 |
| `T193` | SKIP — same | **PASS** — drilled='NVDA'; auto-refresh same symbol; chartLen=79 |

**`could not normalize to list view` occurs zero times in the run** (`grep -c` = 0). All six
previously-permanent SKIPs reach a verdict; five pass. **The fixed point is gone.**

`T203` is the positive control that the fix did not overreach: the legitimate two-level path
List → Heatmap → Chart-by-symbol still backs out to Heatmap, exactly as the old line did. The
run reproduced the poisoning conjunction on the way there — `T204` FAILed (leaving ChartDetail),
`T196` then ran `set triggerHeatmap 1` and FAILed (leaving HeatmapDetail) — and `T200` normalized
anyway. That is the same sequence that wedged the app in session A.

### B.2.1 What the hardware said that contradicts the static audit — `T204`/`T196`

**The network was healthy.** Twelve of the thirteen stock fetches in `serial-stock2.log` returned
200 in 1.8–11.3 s. There is no DNS failure anywhere in the log. Exactly one request failed:

```
489: [D][dataTask.stock] chart GET sym=AAPL range=ytd -1 elapsed=120052ms
493: [D][dataTask.stock] heatmap GET 200 elapsed=3482ms
```

A single `range=ytd` request hung for **120 seconds** and returned `-1`. That is `T204`'s entire
failure — not heap pressure (the question its own message asks), and not DNS (session A's
attribution). And it cascades: it holds the dataTask queue, so `T196`'s heatmap fetch could not be
dispatched inside its 60 s window — the heatmap GET four lines later returned **200 in 3.5 s**.
`T196` is a **queue-serialization casualty of `T204`'s stall**, not a heatmap defect, and its
message ("screener fetch did not complete") is true only in the sense that it never started.

Session A also failed `T204` on Ytd (cycle 1/6). Its raw log contains **no `range=ytd` line at
all**. Two sessions, two different network conditions, the same range. `G-10`/`G-17` are
re-confirmed here in a sharper form than session A could: the message asks "heap pressure
failure?" while the answer is one line in the log the suite already captured.

### B.2.2 `T192` — a verdict nobody has ever seen, and it is not the network either

`T192` FAILs with "fetchOkCount did not advance after tab-switch — TASK-121 fix may be missing".
The raw log shows the 5D fetch it is waiting on **succeeding, twice**:

```
675: [D][dataTask.stock] chart START sym=NVDA range=5d heap free=62k maxBlk=31k
680: [D][dataTask.stock] chart GET sym=NVDA range=5d 200 elapsed=3981ms
690: [D][dataTask.stock] chart GET sym=NVDA range=5d 200 elapsed=2284ms
```

and `get dataq` shows `inFlight=5` (`STOCK_CHART_BY_SYM`) returning to `-1` at `ms=365619`,
roughly 30 s inside the 45 s window, with `stockChartProgress` back at `-1` (idle). Two HTTP
200s, the fetch dispatched and completed — and `fetchOkCount` never moved. Line 674 shows the
mechanism's neighbourhood: `[D][stock] chart drop stale result sym=NVDA range=0 (want NVDA/1)`,
the range-identity discard. Either the 5D results are being discarded the same way, or
`fetchOkCount` is not bumped on the BY_SYM path.

**Not diagnosed here — filed as an observation.** It is the same shape as `G-10`: the message
names TASK-121 while the log names something else. It is also the first time this id has produced
any information at all, which is the point of the fix above.

## B.3 TASK-579 / `F-4` — the WebRadio injector's custody, fixed and verified

**The change** (`app/tools/suite/serialdbg/webradio.py`): a `_wr_deadurls_custody` decorator wraps
all six `T_PLE_WR_155`…`160` bodies in `Dut.injected("wrDeadUrls", 15, clear_to=0)`. `injected` is
the mechanism BP-073 provides for exactly this shape — a write-only injector with no read-back,
whose disarming value (`0`, on which `webRadioApp.cpp:1032-1041` clears both the flag and the
synthetic list) is a fact about the firmware the caller knows and `dut.py` does not. A decorator
rather than a re-indent because the context must outlive every `return` in the body, and the
precondition's own re-arm after the WebRadio switch-in is idempotent. **No firmware changed.**

**The custody evidence** (`serial-wr.log`, run token `db4c0999586e4fe4`, artifact
`run-20260907T083929-1423483-db4c0999.json`, exit 0, gen 32.1). Every arm now has its clear:

| arm | arm | clear |
|---|---|---|
| 170 | 186 | **368** |
| 377 | 381 | **577** |
| 579 | 583 | **765** |
| 767 | 771 | **953** |
| 955 | 959 | **1143** |
| 1145 | 1149 | **1326** |

The last clear is at line **1326**, before any downstream id runs. Compare session A: six arms,
first clear ~950 lines later inside `T237`.

| Signal | Session A | Session B |
|---|---|---|
| `forced connect-fail (debug wrDeadUrls)` | **45**, spanning idx 0–9 | **1** — line 360, inside `T_PLE_WR_155`'s own window |
| `wrState=5` | `T_WR_COEX_01` **FAIL** | **0 occurrences in the whole log** |

**The eleven downstream ids no longer inherit a forced connect-fail.**

| Id | Session A | Session B |
|---|---|---|
| `T_PLE_WR_155`…`160` | PASS ×6 | **PASS ×6** (unchanged — the fix costs them nothing) |
| `T_WR_EJECT_01` | — | **FAIL** — undeclared flake, see below |
| `T_WR_EJECT_02` | — | **PASS** — hit=EJECT; appId=WebRadio; wrEnqueues 2→3 |
| `T_WR_COEX_01` | **FAIL — `wrState=5`** | **SKIP — station list unavailable** |
| `T_WR_COEX_02` | SKIP — not in PLAYING | SKIP — not in PLAYING (now *behind* the SKIP above) |
| `T_WR_COEX_04` | SKIP — not in PLAYING | SKIP — same |
| `T_WR_HEAP_01` | — | **PASS** — free=67k min=43k |
| `T_WR_HEAP_02` | — | **PASS** — free=104k min=42k |
| `T_WR_HEAP_03` | SKIP — could not reach PLAYING | SKIP — no stations loaded |
| `T_WR_HEAP_04` | SKIP — same | SKIP — same |
| `T_WR_VOL_CLAMP` | — | **PASS** — soft-cap 12 enforced, 8/8 cases |

The five SKIPs that remain are a **different failure with a different cause**, and it is a real
one — §B.4. The distinction is exactly the one the flake register could not previously draw:
`wrState=5` is the injector and can only be a suite-order defect; "station list unavailable" is
the outside world.

**A third `C-7` case.** `T_WR_EJECT_01` FAILs with "UNDECLARED flake — no entry for
`T_WR_EJECT_01` in flaky.yaml"; its original claim was "hit=EJECT action=EJECT, appId stayed
Spotify, but no TLS-reset log line within 8 s". Session A found the same shape at `T092` and
`T_PLR_07`. Three ids now. TASK-626's gate is doing what `C-7` asked for; the bookkeeping is what
is behind. Feeds TASK-595.

## B.4 `F-0` CORRECTED — the station fetch fails on a **cert chain**, not on dead mirrors

Session A read the two `run/check-datatask-certs` ERRORs (nl1/at1 NXDOMAIN) as the DUT's cause:
"the mirrors are gone upstream, and the firmware's mirror list still names them." Hardware says
otherwise, and the correction matters because it points at a different fix.

**The firmware does not name nl1 or at1** (`dataTaskStorage.cpp:938-941`):

```cpp
static const char* kRadioBrowserMirrors[] = {
    "all.api.radio-browser.info",
    "de1.api.radio-browser.info",
};
```

Both of those resolve today; nl1 and at1 are NXDOMAIN, and the firmware has not asked for them.

**What the DUT actually gets** (`serial-wr.log` 421-462, and again at 1408-1413):

```
[I][dataTask.webradio] GET mirror=all.api.radio-browser.info code=-120 elapsed=295ms
[W][dataTask.webradio] mirror=all.api.radio-browser.info failed code=-120
[I][dataTask.webradio] GET mirror=de1.api.radio-browser.info code=-120 elapsed=207ms
[W][dataTask.webradio] mirror=de1.api.radio-browser.info failed code=-120
[W][webradio] station fetch failed ok=0 http=-120 jsonErr=
```

`-120` is **CERT_VERIFY_FAILED** (`app/src/logDecode.h:61`). ~200 ms is a handshake rejection, not
a timeout. That boot holds **72** cert-failure lines and **zero** successful GETs of any kind; the
same board did fifteen successful HTTPS 200s to Yahoo one boot earlier, so this is neither the
clock nor board-wide TLS.

**The host says both mirrors are fine.** Replicating the gate's own oracle — `openssl s_client`,
single pinned root, offline, `-verify_return_error` — against `RADIO_BROWSER_ROOT_CA` parsed out
of `dataTaskCerts.h` (ISRG Root X1, valid to 2035): `Verification: OK` for **both** `all.` and
`de1.`.

**The likely mechanism, and it is new.** radio-browser now presents a **three-cert** chain through
Let's Encrypt's new hierarchy:

```
leaf CN=*.radio-browser.info  <-  CN=YR2  <-  CN=ISRG Root YR  <-  ISRG Root X1  (the pinned root)
```

All RSA/sha256, so there is no algorithm gap. `openssl` builds that path; the board's mbedTLS does
not. This is a concrete, testable explanation for the WebRadio station-fetch symptom open since
TASK-284 ("mirror truncation comes and goes, likely rate limiting") — and it is neither rate
limiting nor mirror churn.

**And the gate cannot see it.** `run/check-datatask-certs`'s `ENDPOINTS` table (lines 40-47) lists
`de1`, `nl1`, `at1`. It therefore

* **never tests `all.api.radio-browser.info`** — the firmware's *primary* mirror, and the one the
  in-file comment at `dataTaskStorage.cpp:930-937` says was deliberately promoted to primary;
* spends two of its nine rows on hosts the firmware does not contact and which no longer exist,
  reporting them every run as "network unreachable from this host";
* **PASSes `de1`, which the DUT rejects.**

The endpoint table has drifted from the firmware's mirror array, and the guidance text ("may just
mean this network can't reach the host — re-run from an unrestricted network") steers the reader
away from both facts. This is WP-Z's theme **T2 — an oracle that cannot observe its subject** — in
the preflight whose whole job is to observe it, and it is the third instance this programme has
found in an instrument rather than a test (after `check_entrypoint_lifecycle` and the ELF guard).

Recommended: derive `ENDPOINTS` from `kRadioBrowserMirrors` rather than restating it, add a DNS
resolution check so a dead hostname is not reported as a sandboxed network, and reproduce the
mbedTLS path build rather than openssl's.

## B.5 The isolated-vs-in-suite arms session A did not reach

### `E #2` — `T_PLR_18`'s suspected dependence on `T_PLR_17`: **REFUTED**

| Arm | Result |
|---|---|
| `./run/test-targeted T_PLR_18` | **PASS** — caps=1 (CAP_TRANSPORT only) … (token `79dc7e465a5c44a9`, exit 0) |
| `./run/test-targeted T_PLR_17,T_PLR_18` | `T_PLR_17` **FAIL** · `T_PLR_18` **PASS** (token `628dad50144847ed`) |

The prediction was "isolated SKIP; PASS only in that order". `T_PLR_18` passes alone, and passes
again behind a *failing* `T_PLR_17`. It has no dependence on its predecessor. (`T_PLR_17`'s own
FAIL — "no `dequeued action=SHUFFLE` within 20 s" — is its standing `flaky.yaml` entry, TASK-520,
on a rig under the TASK-243 Spotify 403.)

### `D #6` — does `T150` pass on `T149`'s leftover? **CONFIRMED, and the proof is a number**

| Arm | Result |
|---|---|
| in-suite (session A) | `[PASS] T149  posbarDragMs=**89032** ms; dragState=D_IDLE` |
| in-suite (session A) | `[PASS] T150  posbarDragMs=**89032** ms despite y-drift above groove` |
| isolated (this run) | `[FAIL] T150  posbarDragMs=**0** not in [50000, 120000] (~0 = capture broken; Move samples dropped after y left groove)` (token `8542d246285c4adb`) |

The two ids report the **identical** value, 89032 ms, in the same run. `T150` is not measuring its
own drag: it reads what `T149` left behind, and its green in every full-suite run is entirely its
predecessor's residue. Run alone, its own capture yields 0 and it fails — and the failure string
it prints has been describing the real defect all along. This is the review's central thesis with
a byte-identical number as the evidence, and it is the cheapest reproduction in the programme.

## B.6 Two rig-messaging findings, both observed rather than reasoned

### A HEALTH-classed board fault is delivered to the operator as a RIG verdict

The first `T150` attempt aborted on a genuine WiFi outage — an AP flap, `reason=201`
(`NO_AP_FOUND`), the supervisor cycling `<home-ssid>` → `<home-ssid>` →
`<home-ssid>` and recovering on kick 3 after ~120 s. The runner classed it correctly
and said so at length:

```
[SETUP-FAIL] wifi-not-connected  cls=HEALTH
This is a HEALTH condition, not a test result … It is NOT a rig condition — do not blame the
cable, the port or the host until this is resolved. Diagnose the DEVICE …
```

Then `explain_exit_code` (`run/lib.sh:544-552`) printed, as the **last thing on screen**:

```
[SETUP-FAIL] rig condition — NO TESTS RAN. This is not a test failure.
             Wrong build on the board, WiFi never came up, or the port was busy.
```

The exit code staying 3 for both classes is deliberate and documented — `runner.py::_setup_fail`:
"The exit code stays 3 for both classes: exit 4 belongs to the suite's HEALTH gate (TASK-566) and
may not ship before EC-G7's consumers understand it. **What changes here is the SENTENCE**, which
is the half that misdirects a reader." The runner changed its sentence. The wrapper's exit-3
branch did not, and it lists "WiFi never came up" as a *rig* cause. The corrected sentence is
overwritten by the uncorrected one four lines later, and the wrapper's is the one the operator
reads last.

### A correction to this document's own session-A record

Session A §1.6 wrote of an identical abort: "Correctly classed HEALTH, **correctly exit 4**, no
tests ran — the machinery worked." The exit code was **3**, not 4, and by design; `_setup_fail`
has only ever exited `SETUP_FAIL_EXIT = 3`. The *classification* worked. The exit code did not
distinguish, and could not have.

## B.7 Corrections landed in `flaky.yaml`

* **`T_WR_COEX_01`** — the entry attributed `wrState=5` to radio-browser.info churn (TASK-540) for
  about a year. `wrState=5` is the value `_debugForceConnFail` assigns; the connect never leaves
  the board, so no station list and no mirror can be responsible. The entry is kept but **narrowed
  to what remains genuinely environmental** (timeout at `wrState=1`/`0`, station list unavailable),
  the `wrState=5` arm is removed with the hardware evidence and the arm/clear line numbers recorded
  in a header comment, and the entry is marked **for deletion outright** if the next full-suite run
  shows no `wrState=5`. Why TASK-540's five re-runs could not reproduce it is now on the record
  too: every one of them was isolated, and the symptom is suite-order-only.
* **`T_PR_05`** (candidates list) — annotated as `H-5`'s "no consumer anywhere, permanent SKIP
  since 2026-07-11". It **PASSED** on hardware in session A. The note now records that, keeps the
  id as a candidate on network grounds only, and says what would retire it.

`T_WR_VOL_03`, the second entry session A's `flaky.yaml:72-108` reference covered, was already
removed when TASK-603 retired the id; only its explanatory comment remains, and it is correct.

## B.8 Ledger

**Settled in session B: 15.** Running total **36 of 58**.

| Settled this session | Result |
|---|---|
| `T_DTP_01` at a real verdict (TASK-657) | **PASS** §B.1 |
| `T_DTP_02` re-confirmed after the observer change | **PASS** §B.1 |
| `T_WX_07` at a real verdict (TASK-657) | **PASS** §B.1 |
| `T_CX_07` at a real verdict (TASK-657) | **PASS** §B.1 |
| `T_DTP_01`'s TASK-660 `(0,0)` narrowing, unexercised after session A | **exercised — saw exactly {0}** §B.1 |
| `G-1` — does the one-line firmware fix free the block? | **YES — 6/6 ids reach a verdict, 0 SKIPs** §B.2 |
| `G-1` — does the fix break the legitimate two-level path? | **NO — `T203` PASS** §B.2 |
| `F-4` — does `Dut.injected` custody clear the injector? | **YES — 45 forced-fails → 1; `wrState=5` → 0** §B.3 |
| `F-4` — do the eleven downstream ids stop inheriting it? | **YES — 4 new PASSes; remaining SKIPs have a different cause** §B.3 |
| `F-0` — is the station fetch failing on dead mirrors? | **NO — CERT_VERIFY_FAILED on two live mirrors** §B.4 |
| `E #2` — `T_PLR_18` depends on `T_PLR_17` | **REFUTED** §B.5 |
| `D #6` — `T150` passes on `T149`'s leftover | **CONFIRMED — identical 89032 ms** §B.5 |
| `G-10`/`G-17` on a healthy network (`T204`) | **re-confirmed, sharper: one 120 s Ytd stall** §B.2.1 |
| `T192` — first verdict in its life | **FAIL, and not for the reason it names** §B.2.2 |
| `C-7` — a third undeclared-flake id | **`T_WR_EJECT_01`** §B.3 |

**Still open, with the reason** (unchanged from session A unless noted):

* `H-10` — still measurable only in part; `run/test` restores and reboots before it can be read.
  Not re-attempted here: this session ran only `run/test-targeted`, which has no settings snapshot
  at all.
* The console-probe items (`G-9` `get stockTicker0…7`, `H-10`'s in-RAM reads) — **not taken**.
  They require typing into the tmux monitor pane, which session A did and this session's operating
  rules explicitly forbade (`run/` scripts only). They need either a sanctioned console entry
  point or an explicit exception; they are not blocked by the board.
* `T194`, `T_WR_ERR_04`, `T_WR_VOL_03`, `T_PLR_25` — **moot**, the ids are retired.
* WP-Z §5.5's three walls — other firmware on the board (blocked by TASK-557), a code change
  first, or `run/screendump` (TASK-589). Nothing here moved them.
* The nine network-attributable session-A failures — **two are now settled and were never
  network**: `T204`/`T196` (§B.2.1) and, by implication, the WebRadio pair (§B.4). The rest still
  need a clean re-run.
* `T_WR_COEX_01`'s PLAYING-state arm — cannot be reached until §B.4's cert-chain failure is fixed.
  This is now a *named* blocker rather than an intermittent one.

## B.9 Board state at hand-over

| | |
|---|---|
| board | `d48afcc8eed0` (efuse-mac), verified on all seven runs |
| firmware | `cyd2usb_winamp_debug` (`-DBOD_WATCH`), elf **`5c6d6eca`**, `build=Sep 7 2026-09:08:35`. **Production was never flashed and never restored — the TASK-557 pin held for the whole session.** |
| monitor | running, restarted by `run/test-targeted`'s own step 3/3 |
| WiFi | recovered from the mid-session flap on the supervisor's third kick; `rssi(-59)` |
| settings | **not touched** — `run/test-targeted` has no settings snapshot and writes none; no `spiffs push` was issued |
| working tree | five files changed, **nothing committed** (§B.10) |

## B.10 What is in the working tree, uncommitted

| File | Change |
|---|---|
| `app/src/stock/stockApp.cpp` | TASK-580's one-line `backToPrevView()` guard + its rationale |
| `app/tools/suite/serialdbg/_helpers.py` | `_observe_progress_atom` entry guard; `_progress_atom_verdict` preheld→UNMET arm; `_dataq_fetch_edge` + `_FETCH_TYPE` |
| `app/tools/suite/serialdbg/shell.py` | `T_WX_07`/`T_CX_07` oracle + window; `_ready_flag` deleted with a note |
| `app/tools/test_progress_atoms.py` | **new arm N7** for the entry guard (see below), and `N6`'s fixture adjusted for the guard's one extra `done()` call |
| `app/tools/suite/serialdbg/webradio.py` | `_wr_deadurls_custody`, applied to the six `T_PLE_WR_*` bodies |
| `docs/verification/flaky.yaml` | the two attribution corrections (§B.7) |

**Not done here, for @PM/@Architect:** `T204`'s 120 s Ytd stall, `T192`'s completed-but-uncounted
fetch, the `run/check-datatask-certs` endpoint drift + the mbedTLS chain failure, `T_WR_EJECT_01`'s
missing flake declaration, and `run/lib.sh`'s exit-3 sentence each want a task. TASK-579 and
TASK-580 have their fixes in the tree and their hardware verification above.
