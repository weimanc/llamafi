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
