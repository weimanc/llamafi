# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> Completed/closed/fixed/resolved tasks are periodically moved to [tasks-archive.md](tasks-archive.md) to keep this file WIP-only. **Last archive pass: 2026-08-15** — 80 closed entries / 7 561 lines swept out, and the M-WINAMP-PLAYER board split into its own file (see below). `tasks.md` went 9 787 → ~1 200 lines. Verified: 480 distinct task ids across the three files, no duplicates, none lost. Note for the next pass: result/resolution sub-sections are `###`-level in this project and must travel with their parent task — splitting on heading level alone orphans them. Prior pass: 2026-08-07 (moved 7 fully-closed milestone sections — M-CERT-ERRCODE remainder, M-APP-ORDER, M-WEBRADIO-WINAMP-UI, M-WEBRADIO-REAL-VIS, M-PR-LOCATIONS, M-MEMPLAN hygiene, M-CEEFAX — 2,513 lines — see archive file for the batch note). Prior pass: 2026-07-12 (TASK-143..313 range, 149 entries).

> **PM sync 2026-07-18 (parallel session — M-CERT-ERRCODE remainder scheduled + ADR sweep)** —
> Ran alongside the clock-faces agent (clock files untouched by this session). Two deliverables:
> **(1)** M-CERT-ERRCODE remainder broken down into TASK-341..344 (section below) from the existing
> design doc — TASK-341/342/343 are host-or-build-verified and DUT-free; TASK-344 needs a DUT window.
> **(2)** ADR hygiene sweep: all nine stale-`proposed` ADRs dispositioned with code evidence —
> ADR-024/025/026/031/035/039/041 **accepted** (all implemented and load-bearing),
> ADR-028 (Canvas abstraction) **rejected — not adopted** (no `canvas.h`; renderers still bind
> `TFT_eSPI` directly; preview needs met host-side), ADR-032 (yieldHeap/reclaimHeap)
> **superseded** (protocol never implemented; tlsYield arbitration + demoscene .bss cuts solved it).
> Human review flag: the ADR-028 rejection and ADR-032 supersession are the two judgement calls —
> the seven accepts are mechanical.

## Open — M-PR-MOTION (2026-07-18)

Human request: PlaneRadar poll interval as a settings slider (1 s minimum), and interpolation
for smooth motion — research/preview on host FIRST (samples × algorithm). Design:
[M-PR-MOTION.md](../architecture/designs/M-PR-MOTION.md). The production interpolation task is
deliberately NOT filed — it waits for the study's graduation proposal (R&D protocol).

## Split-out boards

- **M-WINAMP-PLAYER** active tasks: [tasks-winamp-player.md](tasks-winamp-player.md) — 12 entries.
- **M-ARCH** (M-SRCLAYOUT · M-CODEQUAL · M-TOOLING · M-DOCLIFE) active tasks:
  [tasks-architecture.md](tasks-architecture.md) — 47 entries.
- Closed tasks (all milestones): [tasks-archive.md](tasks-archive.md).

---

## M-ARCH — placeholders (full entries in [tasks-architecture.md](tasks-architecture.md))

From the 2026-08-16 Architect pass: nine design docs, ADR-060/061, IFC-002/003 (+004–006 stubs).
Stubs only — **the entries live in the split file** and are edited there.

**Read first:** three refactor commits (`a044f5d`, `78caa95`, `b36f184`) landed ahead of ADR sign-off.
**TASK-488 closed them out on 2026-08-16 (`64bf839`): verified pure moves, nothing reverted**, with
TASK-497's owed 3-run baseline taken in the same DUT block. The gate is lifted. What still stands:
by ADR-060 D0's measure they created **zero components**, so Stages C–F remain the actual work.

| task | pri | status | title |
|---|---|---|---|
| **TASK-488, 497** | **P1/P2** | **DONE 2026-08-16** (`64bf839`) | three refactor commits verified + 3-run DUT baseline taken |
| TASK-453/454 | — | LANDED, VERIFIED | Stage A/B — app classes and debug console out of `main.cpp` |
| TASK-455/456/471/472 | P2 | **455 UNBLOCKED**, rest chained | Stages C–F — `boot/`, composition root, component conversion, `stock/` split |
| TASK-457, 464 | P2/P3 | OPEN | shell hygiene; documentation-reference sweep (308 cites / 49 files) |
| **TASK-458** | **P2** | OPEN | RAII scope guards — fixes a bug class with a proven instance (TASK-222) |
| TASK-459/460/461/462/463 | P2/P3 | MIXED | fetch-skeleton consolidation, canvas constants, table dispatch, palette |
| TASK-465…470 | P2/P3 | OPEN | ADR-061 — debug convention, build-matrix gate, decommission, `display/tft` |
| TASK-473 | P2 | OPEN | concurrency contract gaps — WiFi arbiter, assert I2/I3 |
| **TASK-475**, 474 | P2/P3 | **475 PHASE 1 DONE** (`b0d0202`) | `run/check-docs` gate shipped as counted gate 12 (C5 + C1-delta blocking); 474 PM/QM doc-lifecycle process still open |
| **TASK-478** | P2 | **DONE-superseded** (`989c1ea`) | `tools/lib/dut.py` landed as M-TESTBASE **P1**, re-scoped: `Dut` already existed with 16 importers, so this was an extraction + `resolve_port()` + one timeout policy, not a build. Runner 10 229 → 9 705 lines |
| TASK-479/481/482 | P3 | OPEN | migrate the 16 importers off the compat shim; directory move + taxonomy; spike retirement |
| **TASK-480** | P3 | **BLOCKED-behind-P1-remainder** | split the runner. Must follow the importer migration (TASK-479) — 16 tools still reach through the shim, several for private names |
| TASK-476/477 | P3 | OPEN | `mb_arena` relocation (blocked on a build question); header-comment fix |
| TASK-483…487 | P2–P4 | SKELETON | test architecture, error model, levelization audit, vendoring, ADR-028 revisit |
| TASK-489…494 | P2/P3 | MIXED | handoff debt — X065 + test-id reservations (done), X015 fix, `architecture.md` sync |
| **TASK-455** | P2 | **DONE** | M-SRCLAYOUT **Stage C** — `setup()` (617 lines) → `app/src/boot/boot.h`, verbatim. `main.cpp` 1736 → 1120. Pure move proven by **symbol identity** on 3 envs (10870/11259/11183 symbols, all matching) + identical text/data/bss; only DWARF `.debug_info`/`.debug_line` differ, which are not loaded onto the device |
| **TASK-464** | P2 | **DONE** | documentation-reference sweep: 331 `main.cpp:NNN` citations across 57 files converted to **symbol** citations (not renumbered — they would rot again at Stage C/D/E). C1 improved 268/740 → **146/558**. Zero line citations remain in the editable living corpus; 138 residuals are in gate-exempt historical records, 5 are deliberate rot exemplars, 2 in board files. TASK-503 folded in |
| **TASK-509** | P2 | OPEN | **`T_PLE_14` is unspecified anywhere** — the X055 seqno gap (StationListSource bumps exactly once per change). @VE named it in the M-WINAMP-PLAYER review; nobody filed it. Needs an Architect spec before VE can write it; it is the one genuinely missing *specification* in the X050–X064 range |
| **TASK-510** | P3 | OPEN | apply the P0 convention repo-wide — `test_coverage:` lists only ids with a running body, everything else under `notes: PLANNED COVERAGE:`. Done for X050–X064 (`cross_feature_matrix.yaml`); the other 50 interactions are unswept, and 3 of the 15 swept rows had claimed coverage that did not exist |
| **TASK-511** | P2 | **DONE** | `T_DOC_02` asserted live-corpus counts (`==234`/`==69`) as pass conditions — the exact thing `test_check_docs.py`'s own docstring forbids. Adding 4 design docs turned `run/check` gate 9 red for a reason unrelated to the checker. Replaced with invariants (non-empty, gated > exempt, disjoint) + counts printed as observations |
| **TASK-513** | P2 | **DONE** (`T_PMT_04`) | **M2/X052 arena coverage is vacuous** — `T_PMT_03` asserts `arenaHeld==0` but a 2026-08-17 probe shows `acquires=0` on BOTH build legs; mode switching never acquires the arena, playback does. **CLOSED 2026-08-17** — `T_PMT_04` measures the real acquire/release edge on `cyd2usb_player`:
baseline `acquires=0` → mid-playback `acquires=1 active=1 hwm=23216 arenaHeld=1` → after leaving Player
`acquires=1 releases=1 active=0 hwm=0`. Independently reproduced. The test **hard-FAILs** if playback
never starts, naming the vacuum, so it cannot go green without a real acquire. **CORRECTED 2026-08-17**: the filing said the SD fixture precondition was unmet — it is not. A direct probe shows the card mounted and stocked (`/mp3` 20+ real MP3s, `/playlists` 7 fixtures incl. `short5.m3u`). `plCount=0` meant *no playlist loaded*, not *no playlist present*; no `sd_put.py` push is required |
| — | — | — | **M-TESTBASE phase 1 — [design](../architecture/designs/M-TESTBASE-phase1-player-gate.md); scoped to the 3-mode player, everything else in M-QUALITY deferred** |
| **TASK-514** | P2 | **DONE** (`116c64f`, `6107a73`) | **P0** — register `T_PLR_01..41` + `T_PMT_00..03` in `test_plan.md` with an implementation-status column (26 impl / 8 blocked / 10 resv); fix the `T_PLR_17`/`18` spec-vs-code swap; propose the `X050`–`X064` `test_coverage` values |
| **TASK-515** | P2 | **DONE** (`55cc2d6`) | **P2** — `get player`, the player-slot contract in one observation. DUT-verified in all 3 modes; zero `.dram0.bss` cost |
| **TASK-516** | P2 | **DONE** (`74ae09d`, `7bc98ce`) | **§8** — decouple the mode-cycle from its hit-surface: `playerCycle` + `get playerBind` + `check_player_binding.py` at `run/check` gate 9. Also fixed a P1 bug hardware found (`resolve_port` off-by-one) |
| **TASK-517** | P2 | **DONE** (`df21bbd`, `b945c8f`) | **P3** — `T_PMT_00..03`, operation-driven mode transitions. 4/4 on **both** build legs. NOTE: does **not** close M2/arena — see TASK-513 |
| **TASK-518** | P2 | **BLOCKED-behind-Stage-D** | **P4** — `hasInFlightOp()`/`get idle`. Collides with M-SRCLAYOUT Stage D (`ShellState`/`appTable` own `g_shellBusy`/`g_apps[]`); and per review B3 it is an `App`-interface change across 13 implementations, not a debug key |
| **TASK-519** | P3 | **DONE** | `run/player-gate` — two legs at one commit, pass set in `regression_suite/player-gate-baseline.md`, condition (a) enforced (refuses a leg with no cross-mode cell, rc=2, zero pio), `--selftest` for the comparator. First real run **correctly returned GATE FAIL** on a regressed cell |
| **TASK-520** | P2 | **DONE** | `lib/flaky.py` + `lib/results.py`; undeclared `flake()` = FAIL, expired `review_by` = FAIL, retry-once with both outcomes, unreadable set fails closed. 22 host tests in `test_flaky_policy.py` |
| TASK-503…506 | P2/P3 | OPEN | from the TASK-488 verification — stale `*AppState` docs, `T_488_11` redesign, heap-settling question, `run/test` mutates user settings |

> **▶ Execution order lives in [tasks-architecture.md](tasks-architecture.md) § EXECUTION SEQUENCE**
> — start there, not with this table. **Steps 1/1a are done (488 + 497, `64bf839`); the chain was
> continued, not reworked.** Next is 475 → 478 → 458 (with 495 in front), then M-WINAMP-PLAYER.
>
> **Landed 2026-08-16:** TASK-466 (build gate 3 → 11 envs), 467, 477, 491, 496, **488, 497**.

> **Drift warning:** hand-maintained, same as the player board. The split file is the entry; this is
> a label. If they disagree, the split file wins.

---

## M-WINAMP-PLAYER — placeholders (full entries in [tasks-winamp-player.md](tasks-winamp-player.md))

These are stubs so the ids stay visible and searchable from the main board; **the entries themselves
live in the split file** and are edited there, not here. Anchors are best-effort — if one misses,
search the task id in that file.

| task | pri | status | title |
|---|---|---|---|
| **[TASK-407](tasks-winamp-player.md#task-407--gsettingsplayermode-reverts-to-webradio-between-dut-sessions-with-no-manual-trigger-found)** | P4 | OPEN | `g_settings.playerMode` reverts to WebRadio between DUT sessions wi… |
| **[TASK-424](tasks-winamp-player.md#task-424--sd-write-path-panics-in-fatfs-card-independent)** | P2 | OPEN | SD write path panics in FatFs (card-independent) |
| **[TASK-452](tasks-winamp-player.md#task-452--retire-the-arena-from-the-file-path-successor-to-the-withdrawn-task-443)** | P3 | OPEN | retire the arena from the FILE path (TASK-443 withdrawn, see archive) |
| **[TASK-444](tasks-winamp-player.md#task-444--mbarenafree-can-call-libc-free-on-a-pointer-inside-an-already-freed-arena)** | P2 | DONE | `mb_arena_free()` can call libc `free()` on a pointer inside an alr… |
| **[TASK-445](tasks-winamp-player.md#task-445--mbarenahs-header-comment-misdescribes-which-sites-call-the-arena)** | P3 | DONE | `mb_arena.h`'s header comment misdescribes which sites call the arena |
| **[TASK-446](tasks-winamp-player.md#task-446--mp3-only-make-the-unreachable-codecs-actually-unreachable)** | P2 | IMPL | MP3 only: make the unreachable codecs actually unreachable |
| **[TASK-419](tasks-winamp-player.md#task-419--real-posbar-seek-for-local-files)** | P3 | READY | real posbar seek for local files |
| **[TASK-420](tasks-winamp-player.md#task-420--pledit-edit-mode-button-strip-reorder-delete)** | P2 | BLOCKED | PLEDIT edit mode: button strip, reorder, delete |
| **[TASK-421](tasks-winamp-player.md#task-421--add-from-browser-staging-save-restore)** | P2 | BLOCKED | add-from-browser (staging), save, restore |
| **[TASK-422](tasks-winamp-player.md#task-422--build-variants-soak-ve-suite-registry-completion)** | P2 | PARTIAL | build variants, soak, VE suite, registry completion |
| **[TASK-428](tasks-winamp-player.md#task-428--apply-the-ascii-fold-to-the-spotify-queue-and-station-list-rows)** | P3 | OPEN | apply the ASCII fold to the Spotify queue and station-list rows |
| **[TASK-429](tasks-winamp-player.md#task-429--a-settings-save-during-playback-silently-aborts)** | P2 | DONE | a settings save during playback silently aborts |

> **Drift warning:** this table is hand-maintained. If a status changes in the split file and not
> here, the split file wins — it is the entry, this is a label. Re-generate the table when the player
> board changes rather than patching single rows.

---

### TASK-451 — five unexplained full-suite failures, unowned since 2026-08-11

**Promoted 2026-08-15 from an unnumbered sub-section of TASK-433.** It was filed as prose inside a
task that later closed, and today's archive sweep moved it — still OPEN — into `tasks-archive.md`
with its parent. Nothing was wrong with the item; it had no number, so nothing could track it. This
is precisely the "flagged but never filed" failure mode BP-050 exists for, one level up: it *was*
written down, just not as an entry.

The 2026-08-11 full-suite baseline showed **133 passed / 10 failed / 47 skipped / 5 flaked**. Beyond
the three ids TASK-433 explained, five sit **outside** the 2026-08-09 pre-declared flaky set:

| id | reported reason |
|---|---|
| `T082` | `only 0 ACT_VOLUME enqueue(s); need >= 2 for debounce coverage` |
| `T181` | `re-drill did not enter chart view` |
| `T186` / `T187` | `fetchOkCount did not advance after 45 s` (MSFT / NVDA) |
| `T_PRM_01` | `prPollSec=10 after reboot, expected 30 (not persisted)` |

`T_WR_COEX_01` and `T_WR_VOL_03` also failed but ARE on the pre-declared list.

**Do not assume these are regressions from 2026-08-11's commits, and do not assume they are
environmental.** The 2026-08-09 baseline predates TASK-415/425/427/430/416, so the comparison is
confounded and cannot be settled by argument. Settle it with a bisect run at `c5e0e78^`.

**One update since filing:** `T_PRM_01` is a settings-persist failure, and **TASK-429 — a settings
save aborting under heap pressure — was root-caused and fixed on 2026-08-15** (defer-and-retry, gate
green). That is a live candidate for `T_PRM_01` specifically and should be re-run before any bisect:
`prPollSec` is written by a PlaneRadar settings path, and if the write happened while the audio arena
was up it would have been silently dropped exactly as `fmt24h` was. If `T_PRM_01` now passes, the
remaining four are a smaller and differently-shaped problem.

**Owner:** VE · **Deps:** none · **Gate:** each of the five either reproduces at `c5e0e78^` (→ not a
regression from that range) or does not (→ bisect the range), with the disposition recorded per id ·
**Priority:** P2 · **Status:** OPEN — **1 of 5 explained and fixed 2026-08-15**; four remain.

#### `T_PRM_01` — RESOLVED 2026-08-15 (root cause + fix, no bisect needed)

Reproduced on demand rather than waiting for a suite run, and the mechanism is TASK-429's:

```
get prPollSec -> 10 ;  set prPollSec 30 (during playback) ;  get -> 30 (live) ;  reboot -> 10
settingsSaveCount: count:0  failAlloc:1  pending:true
```

The write aborted because the audio arena held the contiguous heap, exactly as `fmt24h` did. So
`T_PRM_01` was never a PlaneRadar defect and never environmental — it is a settings-persistence
failure whose trigger is "something held the heap when the value was set".

**It also exposed a gap in TASK-429's own fix.** The deferred write is retried at engine teardown and
on the `loop()` tick, and **an intentional reboot beat both** — `tickDeferredSave(force)` skips the
retry *interval*, but it cannot conjure heap, so on a reboot issued while audio plays the retry fails
exactly as the original save did. First attempt at this fix did precisely that and still lost the
value; the measurement is what caught it.

**Fix:** `prepareForReboot()` in `main.cpp`, wired into all three intentional-restart paths (`set
reboot`, the `reboot` command, and Settings → System → Reboot). It tears the audio engine down first
— returning the arena, Audio and pump — and only then flushes the deferred save. Harmless by
construction: the device is about to restart, so stopping audio a few ms early costs nothing. A crash
reset still loses a pending write, which is accepted and recorded.

**Verified end to end:**

```
set prPollSec 30 during playback -> save aborted … Deferred; will retry
set reboot 1                     -> deferred save landed (TASK-429)
                                    saved (doc 1929/6144 B)
after reboot                     -> prPollSec = 30
```

**Remaining four** (`T082`, `T181`, `T186`/`T187`) are untouched by this and still want the
`c5e0e78^` comparison. Note `T186`/`T187` are yahoo-network-shaped, which this project has a
documented flake history for.

### TASK-243 — BLOCKER: Spotify Web API 403 — owner account lacks active Premium

**This blocks all remaining WebRadio verification** (TASK-241 tight-condition test, the WebRadio
serialdbg suite, and TASK-242's T242 + eject-harness validation) and any device feature that reads
Spotify playback state.

**Definitive root cause (host-confirmed, not device).** `app/tools/spotify_state.py` and a raw
host call reproduce the device's exact 403 from the laptop with the same creds — token refresh
succeeds (correct scope), but `/v1/me`, `/v1/me/player`, and `/v1/me/player/currently-playing` all
return **403** with body:
> *"Active premium subscription required for the owner of the app. When the subscription status
> changes, it can take a few hours before requests are allowed again."*

Spotify now requires the **app owner** (clientId `db2ff3…`) to hold active Premium for Web API
access; that lapsed. **Not** the device, firmware, token, scope, or dev-mode allowlist — re-auth +
`spiffs push` were done and are correct; they'll just start working once Premium is restored.

**Knock-on:** EXP-007's "78 K pre-connect = Spotify playing" baseline was almost certainly never a
live session (Premium already lapsed), so TASK-241's provisional numbers rest on an unconfirmed
baseline — re-take once the API is live.

**Resolution (user/owner action — external):** restore active Premium on the owning Spotify
account, then wait the few hours Spotify mentions. **Verify-first procedure when back:** run
`./run/… spotify_state.py` (host) and confirm `ok:true` / `isPlaying` tracks playback *before*
spending any DUT time — this host check is the cheap gate that should precede device work
(process lesson from this session: host-validate the API path first).
**Priority:** P1 — external blocker · **Status:** open (blocked on owner-account Premium)
**Opened:** 2026-06-25 · **Milestone:** M-WEBRADIO / infra
**Owner:** Human (Spotify account) · **Deps:** none (external)

---

### TASK-284 — WebRadio station-list fetch: both radio-browser.info mirrors return truncated JSON (IncompleteInput)

Found 2026-07-06 attempting TASK-278 E1 DUT validation. Fresh boot, `switchApp` into WebRadio
kicks the fetch normally, but both configured mirrors fail identically:
```
[I][dataTask.webradio] GET mirror=de1.api.radio-browser.info code=200 elapsed=2638ms
[W][dataTask.webradio] JSON err mirror=de1.api.radio-browser.info: IncompleteInput
[I][dataTask.webradio] GET mirror=all.api.radio-browser.info code=200 elapsed=2479ms
[W][dataTask.webradio] JSON err mirror=all.api.radio-browser.info: IncompleteInput
[W][webradio] station fetch failed ok=0 http=-100 jsonErr=IncompleteInput
```
HTTP 200 on both, but the JSON body is truncated before the parser completes — `wrCount` stays 0
permanently (`pending` correctly flips 1→0, so the fetch *did* run and *did* fail, this isn't a
stuck-pending bug). Effect: WebRadio can never leave STOPPED via the normal station-list path,
which blocks TASK-278's E1/E2/E3 wr_playing measurement entirely (`set wrUrl` direct-station
injection is the known workaround — used for E3's real-stream-death case already). Not caused by
the TASK-278 diff — `dataTask`'s HTTP/JSON station-list path is untouched by that change.
**Not yet root-caused**: could be a response-buffer-too-small truncation in the dataTask HTTP
client, a timeout cutting the body short, or an actual upstream API change/outage on both mirrors
simultaneously (less likely, but check by hand before assuming firmware-side).

**Investigation (2026-07-08):** ruled out "persistent server/mirror fault" and "response-buffer-
too-small" as the cause. Host-side `curl --http1.0` with the identical UA/URL/query params the
firmware sends returns a complete, valid 33.7 KB JSON body from `de1.api.radio-browser.info`
every time tried — no Content-Length (HTTP/1.0 close-delimited body), which rules out a
firmware-side buffer-size bug (the parse doc streams via `deserializeJson(doc, Stream&)`, it
doesn't pre-size a receive buffer). Also checked whether ArduinoJson's Stream reader silently
truncates on a transient stall: it explicitly uses `Stream::readBytes()` (not `read()`) *because*
`read()` ignores the client's timeout — and `WiFiClientSecure`'s default `_timeout` is 30 s (no
explicit `setTimeout()` call was overriding it down), generous for a 33 KB TLS body. No
deterministic firmware bug found; "both mirrors fail identically in the same attempt" reads as
two independent transient network stalls landing back-to-back, not a systemic block — consistent
with the intermittent field pattern already logged (comes and goes; 2026-07-07 runs were clean,
count=16).

**Fix (best-effort mitigation, 2026-07-08):** `fetchWebRadioStations()`'s per-mirror page-0 loop
now retries the SAME mirror once with a fresh connection on a `-100` (JSON parse error, i.e.
`IncompleteInput`) before falling through to the next mirror — cheap (one extra handshake+GET
only on the error path) and turns a single transient stall into a non-issue instead of burning
both configured mirrors in the same unlucky window.

**Caveat — this could not be DUT-verified against the actual failure**, since the truncation
isn't reproducible on demand (host-side requests never truncated in this session either). DUT
regression only confirms the happy path is unaffected: `T_WR_COEX_01`/`T_WR_HEAP_01`/`02` all
PASS post-fix (`wrCount=16`, retry path not exercised — mirror succeeded on the first try, as
usual). `./run/check` 6/6. Leaving open rather than DONE until a live recurrence confirms the
retry actually clears it; if it recurs with the retry landed, the next data point is whether the
retry itself also fails (pointing at something more systemic than a one-off stall) or succeeds
(confirming the mitigation).

**Priority:** P2 — blocks TASK-278 DUT validation (wr_playing state unreachable normally) ·
**Status:** open — investigated, best-effort mitigation landed (same-mirror retry-once on JSON
parse error); awaiting a live recurrence to confirm it actually resolves the field symptom ·
**Opened:** 2026-07-06 · **Milestone:** M-WR-AUDIO-TASK · **Owner:** Developer · **Deps:** — ·
**Branch:** master

---

### TASK-385 — T193 auto-refresh fetch timeout — likely TASK-383-adjacent, unconfirmed

**Filed 2026-08-01, low confidence.** `T193` failed: `fetchOkCount did not advance after
triggerFetch — auto-refresh did not fire` (45s timeout). Traced the trigger path
(`main.cpp:1332-1334`, `triggerFetch=1` resets `_s.lastChartFetch=0`, forcing `stockTickChart()`'s
own cadence check to re-enqueue on the next tick) — this is a **different** code path from
TASK-384 above (no tap involved, not gated by `g_shellBusy`, and `stockTickChart()`'s cadence
re-fetch was untouched by any of today's fixes). No obvious mechanism connects this to TASK-379/380
directly. Best guess: simply increased exposure to TASK-383's already-documented rare connect-level
failure (`code=-1`, no retry fires for non-200) or two consecutive `IncompleteInput` parse failures
(TASK-381/382's retry only covers one) — this run's `T_PRM_02` degradation (19/300s vs. the usual
36/300s) suggests the network was generally worse than usual during this run, and TASK-380 also
means more real chart fetches happen throughout the full suite than before, proportionally raising
odds of hitting *any* single-request failure mode somewhere in the run. Unconfirmed — no serial
capture for this run to check for `IncompleteInput`/connect-timeout evidence at the actual failure
point.

**Investigated 2026-08-02.** Re-ran `run/test-targeted T193` five times back-to-back with `LOG_FILE=`
capture (full flash/test/restore cycle each time, DUT restored to prod cleanly all 5×), same method
as TASK-383's investigation. **0/5 reproduced.** Every run showed the identical clean pattern: both
chart GETs (`NVDA range=1d` — the initial drill-fetch and the `triggerFetch`-forced auto-refetch)
returned HTTP 200 on the first attempt, `elapsed` in the normal ~2.9-3.0s band, no `IncompleteInput`,
no `code=-1`, no retry ever fired, `fetchOkCount` advanced 1→2 and `chartLen=79` every time (10
total chart fetches across the 5 runs, all clean). One useful side observation: run 1's log did show
a live `code=-1 HTTPC_CONNECTION_REFUSED`, but on a *Spotify* poll reconnect (unrelated call site),
not the stock chart fetch — confirms the failure mode TASK-383 characterized is real and still
occurs in this build's fetch stack generally, just not caught landing on T193's specific fetch in
this sample.

**Reopened 2026-08-02 — the 0/5 result above doesn't rule out what it looks like it rules out.**
`run/test-targeted` flashes fresh and boots the DUT immediately before running only the named
test(s) — every one of the 5 re-runs started from a clean boot (~2-3 min uptime, heap freeInt
~74-118k, no prior test history). But the run T193 originally failed in was a `run/test` full-suite
pass: one flash, one boot, then ~167 tests run sequentially with **no reboot in between** — T193
executed after roughly 150 prior tests had already been exercising heap alloc/free, the dataTask
queue, WiFi, and Spotify's 403-poll/backoff loop for however long the suite had been running by
that point. The isolated re-runs only tested "does T193 fail from a cold boot" (answer: no) — they
never tested "does T193 fail once ~150 tests' worth of state has accumulated," which is the
condition it actually failed under. Walking the CLOSED disposition back to open pending real
evidence from that condition, not a synthetic approximation of it.

**Plausible causes, now framed against the isolated-vs-suite-accumulated gap** (untested,
listed for the next full-suite pass to discriminate between, most to least likely):

1. **dataTask queue congestion / poll-bounded serialization** (TASK-244/299/300 precedent) — if a
   fetch enqueued by a test running shortly before T193 is still in flight or queued when
   `triggerFetch` lands, TASK-244's already-accepted "queued fetch can serialize behind Spotify's
   poll cycle for up to minutes" behavior could push completion past the 45s deadline with **no
   failure at all** on the wire — a false test failure, not a firmware bug. Distinguishing test:
   `T193-pre-trigger`'s new `dataq` snapshot (queueWaiting/inFlight) — clean-boot baseline is 0/0.
2. **Heap fragmentation under sustained load** (TASK-381/382 precedent, same mechanism TASK-386
   already flagged for T204/T-BUSY-01) — ~150 tests' worth of alloc/free cycles could leave
   `lfbInt`/`lfbDma` (largest free block, not just free bytes) measurably smaller than the
   clean-boot baseline (~41-45k), which is what actually gates whether `DynamicJsonDocument` can
   allocate contiguously. Distinguishing test: the new `heap()` snapshots' `lfbInt`/`lfbDma` fields
   vs. the 2026-08-02 clean-boot baseline.
3. **tlsYield arbitration contention** (TASK-287/299's tlsYield-starvation precedent) — extended uptime means
   many more Spotify 403-poll/backoff cycles have run and contested the shared TLS yield lock than
   in a 2-3 min isolated boot; if the chart fetch's `tlsYield()` call has to wait longer to acquire
   it under sustained contention, that eats into the 45s budget before the GET even starts.
   Distinguishing test: the new `dataq` snapshots' `spAct`/`spActMs`/`yieldCount`/`tlsStopped`
   fields at `pre-trigger` — elevated `spActMs` or a non-idle `spAct` right before the trigger
   would implicate this.
4. **Plain connect-level noise, more exposure** (TASK-383's original hypothesis) — more total
   fetches happen throughout a longer, busier run, proportionally raising the odds of hitting
   TASK-383's already-characterized rare `code=-1` connect failure on any single request,
   independent of any accumulated-state mechanism. Distinguishing signal: a `T193-timeout` snapshot
   that looks identical to the clean-boot baseline (nothing degraded) points here instead of 1-3.

**Diagnostics added 2026-08-02 (code, no DUT run performed — batched for the next real `run/test`
pass instead of another isolated repro attempt):** new `_diag_snapshot()` helper in
`run_serialdbg_tests.py` (`get heap` + `get backoff` + `get dataq` in one call) wired into both
`t193()` and `t194()` at entry, immediately before each test's risky fetch-trigger step, and — for
the specific `fetchOkCount`-did-not-advance failure — again at the moment of timeout. Snapshots are
embedded directly in the `fail()`/`skip()` reason string itself (not just printed), so the evidence
survives in the test-summary output even on a run with no `LOG_FILE=` capture — closing the exact
gap this task was originally blocked on. T194 got the same instrumentation as T193 (entry +
pre-list-drill + pre-tab-switch + timeout) even though it wasn't the one that failed: it runs
immediately after T193 in suite order, does a heavier fetch cascade (heatmap + 2 chart fetches + a
tab-switch fetch vs. T193's 2), and is therefore the more sensitive canary for the same
suite-accumulation hypotheses — a same-run comparison of T193's and T194's entry snapshots is a
second, free data point.

**Full-suite `run/test` pass 2026-08-02, with the new `LOG_FILE=` capture.** First real
suite-condition test since filing — single boot, ~167 tests sequentially, no reboot in between
(the actual condition T193 originally failed under, unlike the isolated re-runs above). **0/1
reproduced.** Located T193's exact run in the raw log via its unique `set triggerFetch` marker
(the heatmap-tile-drill → `triggerFetch` sequence is unambiguous): fired at uptime ~663s (~11 min
into the suite), `pre-trigger` diag snapshot read `heap(freeInt=117604,lfbInt=42996,freeDma=74460,
lfbDma=42996) backoff(cf=17) dataq(queueWaiting=0,inFlight=-1,tlsStopped=false,spAct=0)` —
materially *healthier* than the isolated clean-boot baseline, not degraded — chart GET returned
200 in 2881ms, `fetchOkCount` advanced, test passed clean. T194 (same run, ~1 min later) also
passed clean, both new diag triples (`pre-list-drill`, `pre-tab-switch`) confirmed present and
readable in the log exactly where the instrumentation should place them — the new tooling itself
is validated working, independent of whether it caught a failure this time. Also checked
suite-wide: zero non-200 chart GETs, zero `IncompleteInput`/parse failures, zero `fetchFailed=true`
anywhere in the entire ~9,300-line log for any Stock test (the 13 `IncompleteInput` hits in this
run are all PlaneRadar/adsb.fi — TASK-313's already-accepted issue, unrelated). No crash/panic;
two `SW_CPU_RESET` events were both harness-issued `reboot` commands (deliberate persistence-test
reboots), not faults.

**Disposition unchanged — one clean run doesn't retire an intermittent hypothesis, but it's a real
data point now, not a synthetic one.** This run's heap simply never got as pressured as the
original filing's (`lfbInt` held rock-steady ~41-43k the entire suite, vs. the original run's noted
`T_PRM_02` degradation suggesting a rougher network night) — consistent with hypothesis 2 (heap
fragmentation under load) requiring conditions this particular run didn't hit, not with the
mechanism being wrong. Keep `LOG_FILE=` on future `run/test` passes going forward; either a repro
eventually lands with full diagnostic context attached, or enough clean runs accumulate to
downgrade this with real evidence instead of a guess.

**Owner:** Developer · **Deps:** possibly TASK-383 (same failure class, different trigger path);
shares its diagnostic mechanism with TASK-386's T204/T-BUSY-01 (same heap-pressure-under-load
hypothesis, worth checking together) · **Gate:** keep `LOG_FILE=` on future full `run/test` passes;
next repro (if any) — inspect the diag snapshots against the 2026-08-02 clean-boot baseline (heap
freeInt~74-118k/lfbInt~41-45k, dataq queueWaiting=0/inFlight=0 pre-trigger, spAct idle) to
discriminate between hypotheses 1-4 · **Priority:** P3 · **Status:** **OPEN — instrumented and now
validated working under real suite conditions; 0/1 full-suite repro + 0/5 isolated repro so far.**

**Update (2026-08-06, second full-suite `run/test` pass, `LOG_FILE=` capture) — 0/1 again, first
run since diagnostics moved into the shared helpers.** T193 passed clean: `[T193-entry]`/
`[T193-pre-trigger]` diag markers present and correctly placed in the raw log (confirms the
generalized shared-helper instrumentation from TASK-386's later update — not just the earlier
hand-instrumented version — is live and working, not only code-reviewed). `pre-trigger` snapshot:
`heap(freeInt=117612,lfbInt=42996,...)` — same healthy shape as every prior clean run, no
degradation trend. `fetchOkCount` advanced, `chartLen=61`. Real failures this run were elsewhere
and unrelated: `T079`/`T082` (new, not previously seen — see note below) and the already-tracked
`T_WR_TLS_01`/`T_PRM_02` flakes (TASK-284/TASK-313; this run's cert-preflight step also logged
`nl1`/`at1` radio-browser mirrors network-unreachable **from the host**, consistent with
`T_WR_TLS_01`'s failure, not a new cause). Tally: 132 passed, 4 failed, 36 skipped, 1 flaked; DUT
restored to prod cleanly. Now 3 consecutive clean full-suite passes for T193 (2026-08-02 ×2,
2026-08-06) — no repro yet under any condition tested, including this run's real network noise
elsewhere in the suite.

**Side note, out of scope for this task:** `T079` (`tap not skipped while gate armed`) and `T082`
(`only 0 ACT_VOLUME enqueue(s)`) failed this run with no prior record in this file — not
investigated (unrelated code path, Winamp gesture/volume-debounce tests, not stock-fetch), flagging
here rather than dropping silently. Worth a look if they recur.

## Open — TASK-386 (2026-08-01, filed from a third full-suite `run/test` pass, post-TASK-384)

Re-ran `./run/test` after TASK-384 landed. **Result: 122 passed, 4 failed, 41 skipped, 3 flaked** —
best result yet across the three full-suite passes today. Every fix from today
(TASK-379/380/381/382/384) confirmed holding simultaneously in this run: `T148`, `T176`, `T184`,
`T188`, `T192`(skip, unrelated precondition)/`T193`, `T231` all pass. `T091` back to its usual
`FLAKE` (not `FAIL`) — no new information. `T_WR_TLS_01`/`T_PRM_02` remain the already-tracked
flakes (TASK-284/313) — `T_PRM_02`'s gaps this run (up to 27573ms) are again on the degraded side,
consistent with a generally rough network night rather than a new issue.

### TASK-386 — T204 + T-BUSY-01: two more `fetchOkCount`/`chartLen` stalls, likely TASK-381/382's known residual risk

**Filed 2026-08-01, not independently investigated — high-confidence hypothesis from pattern
match.** Two new failures, both Stock-chart-fetch tests that have passed cleanly in both prior
full-suite runs today:
- `T204` (`D1↔Ytd rapid alternating stress`, M-STOCK-VE-STRESS — deliberately hammers
  `DynamicJsonDocument` alloc/free under heap pressure by design): `fetchOkCount did not advance on
  Ytd — heap pressure failure?` (the test's own hypothesis, baked into its fail message).
- `T-BUSY-01` (`StockApp row tap → amber → clears on fetch complete`): `chartLen did not exceed 0
  after 45s — fetch did not complete`.

Both show the identical `dataq` shape already characterized for TASK-381/382/383: `inFlight`
transitions out of flight within a few seconds (fetch attempt(s) genuinely completed, not stuck) but
`fetchOkCount`/`chartLen` never advances. **Not re-investigated with a fresh `LOG_FILE=` capture**,
but the shape, the same fetch codepath (`fetchStockChart`/`fetchStockChartBySym` via
`fetchStockChartWithRetry`), and — most tellingly — `T_PRM_02`'s notably degraded gaps in this exact
same run all point at the same already-documented, already-accepted residual risk: TASK-381/382's
retry-once mitigation covers exactly one extra attempt, and under sustained heap/network pressure
(evidenced this run) two consecutive failures (two `IncompleteInput`s, or one `IncompleteInput` +
one `code=-1` connect failure) still produce a genuine, uncovered failure. This is expected residual
behavior of a retry-*once* design, not retry-forever — TASK-381/382's commit message said as much.

**Not attributed to TASK-384** — that fix touches only tap-dispatch/busy-gate logic, no HTTP/JSON/
heap code at all, and both failures are squarely in the fetch/parse path TASK-384 never touched.

**Investigated 2026-08-02 — code-only, no DUT run (human direction: batch diagnostics before any
rerun).** Read `fetchStockChartWithRetry()` (`dataTaskStorage.cpp:545-581`) to confirm the retry
mechanism precisely: retries **only** when `code==200 && !r.ok` (HTTP succeeded, JSON parse
failed — the `IncompleteInput` case); a non-200/connect-level failure on the *first* attempt never
retries at all, by design (retrying a connect failure "just burns another TLS handshake for no
benefit", per the code comment). So a genuine double-failure covers exactly two shapes: two
consecutive `IncompleteInput`s, or one `IncompleteInput` (retried) followed by a second failure of
either kind — but a **first-attempt connect-level `code=-1`** would show as this exact same
`fetchOkCount`-never-advanced/`chartLen`-stayed-0 symptom from the test's point of view, with *zero*
retry ever attempted (TASK-383's failure mode, not TASK-381/382's). The existing firmware LOG_D
lines (`chart START ... heap free=Xk maxBlk=Yk`, `chart GET ... <code> elapsed=Xms`, `chart parse
failed rc=X -> retry`, `chart retry ok=Y rc=Z`) already distinguish all of this cleanly — they just
weren't captured, because **`run/test` (the full-suite script) had no `LOG_FILE=` support at all**
(only `run/test-targeted` did) — the actual reason TASK-383's/TASK-386's own filed gates could only
ever recommend an *isolated* re-run, which TASK-385's investigation this session established
is the wrong tool for a suite-order-dependent failure.

**Applying the TASK-385 lesson here too:** `T204` and `T-BUSY-01` are not equally suite-state-
dependent. `T204` self-induces its own heap pressure (6 rapid back-to-back fetches by design), so
an isolated `run/test-targeted T204` repro attempt would actually be a fair test of the
heap-pressure hypothesis on its own — unlike T193. `T-BUSY-01` is a single self-contained fetch,
structurally identical to T193's case: its failure is more plausibly suite-accumulated-state-
dependent (heap fragmentation, dataTask queue backlog, tlsYield contention left over from ~150
prior tests) than something a fresh-boot isolated rerun could validate.

**Diagnostics added 2026-08-02 (code, no DUT run performed):**
1. **`run/test` gained `LOG_FILE=` support**, mirroring `run/test-targeted`'s existing flag —
   previously only isolated targeted re-runs could capture raw serial (`run_serialdbg_tests.py`
   already accepted `--log-file` in full-suite mode; the full-suite *wrapper script* just never
   passed it through). This is the single highest-value fix here: the next full `run/test` pass can
   now capture the complete firmware-side retry-cascade evidence for T204/T-BUSY-01 (and T193/T194)
   in situ, under real suite conditions, with zero isolated-repro ambiguity.
2. Same `_diag_snapshot()` helper from TASK-385 wired into both tests: `T204` gets a baseline at
   entry plus a snapshot before **every one of its 6 taps** (not just on failure — the
   heap-pressure hypothesis is specifically about a *trend* across the cycle, which a single
   failure-point snapshot can't show) and on any failure; `T-BUSY-01` gets entry/pre-trigger/
   timeout snapshots, same shape as T193's. All embedded directly in the `fail()` reason so the
   evidence survives even on a `run/test` pass someone forgets to point `LOG_FILE=` at.

**Full-suite `run/test` pass 2026-08-02, with the new `LOG_FILE=` capture.** Same run used for
TASK-385's re-check. Located T204's exact block via its unique alternating-tap signature
((256,9)/(148,9) × 3): fired ~12 min into the suite, entry snapshot `heap(freeInt=76268,
lfbInt=42996,...)`, all 6 cycles (Ytd/D1 × 3) returned HTTP 200 with `err=Ok`, `fetchOkCount`
advanced monotonically 12→18, `lfbInt` held flat at 42996 across every single one of the 6
pre-tap snapshots — **no heap-pressure trend at all this run**, contrary to what the hypothesis
would predict if conditions were similar to the original filing. `fetchFailed` read `false` after
every cycle. **T204: 0/1 reproduced.**

`T-BUSY-01` could not be individually isolated in the raw log — this suite has several other
Stock tests that tap the same AAPL list-row coordinate in adjacent sequences, and without the
python-level PASS/FAIL boundary (lost to a `tail -100` truncation on the background command —
noted for next time: don't pipe a long-running full-suite run through `tail`, let the harness
capture the whole thing) its exact block couldn't be confidently distinguished from the others by
raw-log pattern alone. However, a suite-wide sweep settles it anyway: **zero non-200 chart GETs,
zero `IncompleteInput`/parse failures, zero `fetchFailed=true`, and zero post-JSON parse errors
appear anywhere in the entire ~9,300-line log for any Stock test this run** (the only
`IncompleteInput` hits are PlaneRadar/adsb.fi, TASK-313's unrelated already-accepted issue). Since
T-BUSY-01 is just another stock chart fetch and no stock chart fetch failed anywhere in this run,
T-BUSY-01 passed too, by construction. **T-BUSY-01: 0/1 reproduced** (via exhaustive negative
sweep, not direct isolation).

Same disposition logic as TASK-385: this run's heap simply never got as pressured as the original
filing's — informative (the new instrumentation is confirmed working, ready to catch it next time
with full context) but not yet conclusive either way.

**Generalized 2026-08-02 (human: "does this pattern apply to other tests? could we improve suite
quality?").** Surveyed every caller of the same family of async-wait-or-timeout helpers.
`_wait_chart_complete` alone (the exact helper T193/T204's failures went through) is also called by
`T176`, `T185`, `T188`, `T192`, and `T-BUSY-01b` — T188/T192 are literally TASK-381/382's own
`IncompleteInput` regression tests, so they're the most relevant uninstrumented gap of all. Parallel
un-instrumented helper families exist for stock quotes (`_wait_quote_fetch`) and WebRadio
(`_wait_wr_count`/`_wait_wr_state`) — same single-async-op-plus-timeout shape, same theoretical
exposure to heap/queue/tlsYield pressure.

Rather than hand-instrumenting each call site (what TASK-385/386 did for T193/T194/T204/T-BUSY-01),
pushed `_diag_snapshot()` **into the shared helpers themselves**, on their timeout path only (never
on a legitimate early-exit like `_wait_wr_count`'s `pending==0`/"no stations" case): `_wait_chart_
complete`, `_poll_chart_len_positive`, `_wait_quote_fetch`, `_wait_wr_count`, `_wait_wr_state`,
`_wait_heatmap_count`, `_wait_shell_not_busy`. Return types/signatures are **unchanged** (still
`bool`/`int`) — zero risk to any of the existing ~15+ call sites across the suite, since the
diagnostic `get`s land on the wire (captured by any `LOG_FILE=` in effect) purely as a side effect
before the existing `return False`/`return 0`. Every current caller — instrumented or not — and any
future test written against these helpers now gets this for free.

Also added a **serial-side per-test marker**: the main dispatch loop (`run_serialdbg_tests.py`
`main()`) now issues `get __TEST_<id>__` immediately before invoking each test. That's
intentionally an unrecognized var — the firmware's existing "unknown var" fallback echoes it
straight back on serial with zero firmware changes, giving `LOG_FILE=` captures an unambiguous
per-test boundary. This directly targets the exact problem hit during this investigation: `T-BUSY-
01` couldn't be individually isolated in the raw log because several tests share its tap
coordinates, and the python-level PASS/FAIL boundary had been lost to a `tail -100` truncation on
the backgrounded command. Future investigations won't need the kind of manual signature-matching
this one required.

**Owner:** Developer · **Deps:** TASK-381/382 (shared mechanism), TASK-383 (established the
accept-transient-network-noise precedent this likely falls under), TASK-385 (shared diagnostic
mechanism + the isolated-rerun-vs-suite-state methodology lesson) · **Gate:** keep `LOG_FILE=` on
future full `run/test` passes; next repro (if any) — check (a) the LOG_D retry-cascade lines to see
whether it was a genuine double-`IncompleteInput`/mixed failure (TASK-381/382's accepted residual)
vs. a first-attempt `code=-1` with no retry (TASK-383's class) vs. something new, and (b) the new
`_diag_snapshot()` lines for a heap/queue/tlsYield trend · **Priority:** P3 (unchanged) ·
**Status:** **OPEN — instrumented and validated working under real suite conditions; 0/1 full-suite
repro for both tests so far** (T204 directly confirmed clean, T-BUSY-01 via exhaustive sweep).

**Update (2026-08-06, second full-suite `run/test` pass, `LOG_FILE=` capture) — both 0/1 again,
this time each test directly isolated** (T-BUSY-01 needed the exhaustive-sweep workaround last
time because its PASS/FAIL boundary was lost to a `tail` truncation — the per-test `__TEST_<id>__`
serial marker added afterward fixed exactly that; both tests' blocks were unambiguous in this raw
log). T204: all 6 alternating D1/Ytd taps passed, `fetchOkCount` advanced 14→19 monotonically,
`lfbInt` held dead flat at 42996 across every one of the 6 pre-tap snapshots — zero heap-pressure
trend, same as the first clean run. T-BUSY-01: `shellBusy` cleared correctly on fetch completion,
`[T-BUSY-01-entry]`/`[T-BUSY-01-pre-trigger]` markers present and correctly placed. Real failures
this run were unrelated (`T079`/`T082`, new — see TASK-385's note above; `T_WR_TLS_01`/`T_PRM_02`,
already-tracked TASK-284/313 flakes). Now 2 consecutive clean full-suite passes for both T204 and
T-BUSY-01 — still no repro under any condition tested.

**Update (2026-08-06, third full-suite `run/test` pass, same session):** T193/T204/T-BUSY-01 all
pass clean again (3rd consecutive for T193, 2nd for T204/T-BUSY-01 counting only full-suite
passes — 4th overall counting the earlier isolated hand-check). `fetchOkCount` advanced
monotonically through all 6 T204 taps as before, no heap trend. This run's real failures were
`T082` (again — see TASK-406's correction above, root-caused and fixed this time, unrelated to
the heap-pressure hypothesis) plus the already-tracked `T_WR_TLS_01`/`T_PRM_02`/`T_WR_COEX_04`/
`T_WR_VOL_03`/`T_PR_04` flakes (network/timing noise, not investigated further this session).
Diminishing returns at this point — 3-4 clean full-suite passes with zero heap-pressure trend on
every single check. Still open per the discipline established above (a clean run doesn't retire
an intermittent hypothesis), but further blind full-suite reruns are unlikely to be the highest-
value next step; a real repro would need either a genuinely worse network night (like the
original filing's `T_PRM_02` degradation) or a purpose-built heap-fragmentation stress harness
rather than waiting on ambient conditions.

---

## Open — M-WEBRADIO-REAL-VIS follow-on: Spectrum + Wave graduation (2026-08-02)

Two Architect design docs (`M-WEBRADIO-REAL-VIS-SPECTRUM.md`, `M-WEBRADIO-REAL-VIS-WAVE.md`)
resolved the open tap-cycle-length question by human decision 2026-08-02: ship both together,
keep `VIS_WAVE_ATLAS`. WebRadio's tap-cycle becomes the 6-stop Atlas → WaveAtlas → VU → Wave →
Spectrum → Blank → Atlas; Spotify's cycle is untouched (Atlas → WaveAtlas → VU → Blank). Both
tasks are DUT-gated (no DUT this session — scheduled, not started).

### TASK-390 — WebRadio marquee/title display freezes on sustained real playback — unconfirmed, filed for investigation

**Filed 2026-08-03, human-observed live on DUT (production firmware, not a test-harness finding).**
While a WebRadio station (SLAM!, a real Dutch commercial station — matches the default
`webRadioCountry=NL`) had been playing for an extended, unmeasured duration, the marquee/title
area froze showing a fragment of a show name ("...n de pauzuh", likely "in de pauze" — Dutch for
"on break"/between-programme ID). Human confirmed the touchscreen was still responding to input
at the time — this rules out a full `loopTask` hang (touch polling and the marquee tick both run
in the same `loop()`), so this is not TASK-285/288's class of watchdog-relevant freeze.

**Corroborating evidence, from the live serial heartbeat (not reconstructed after the fact):**
`last_render_age_ms` was climbing in exact lockstep with `uptime` across three consecutive
30s-interval heartbeats (32027 → 62027 → 92027, i.e. +30000 each time) — zero full-screen repaints
happened in that window and counting. This is a *display-pipeline* symptom, not merely "the ICY
title stopped updating text" — something stopped calling the render path that would normally fire
every tick regardless of content changes.

**No forensic trail into the actual triggering event.** The monitor session capturing the original
freeze went silent independently (the board's CH340 adapter flapped `/dev/ttyUSB0` → `/dev/ttyUSB1`
mid-session — a known quirk, see `docs/process/dut_workflow.md`), and was killed/restarted before
its scrollback could be searched for the triggering sequence. Production firmware
(`cyd2usb_winamp`, no `SERIAL_DEBUG`) has no live `get`/`set` query surface, so nothing could be
pulled from the frozen device directly either. This task starts from symptom + one confirmed
mechanism-level fact (render pipeline stalled, not full loopTask) and no direct cause evidence.

**Diagnostic gap found while investigating (worth closing regardless of root cause):** neither
`WinampDisplay`'s marquee state (`titleScrollOffset`/`titleScrollDeadline`/`lastTitle`/
`_wifiDownOverrideActive` — `winampDisplay.h:693-710`) nor the WiFi-down-override latch has any
debug getter today. `get wrIcy` (webRadioApp.h) exposes the *source* ICY title but not what the
marquee is actually doing with it — there is currently no way to tell "ICY title stopped arriving"
apart from "marquee logic itself is stuck" apart from "WiFi-down override latched and never
cleared" without new instrumentation.

**Plausible causes, ranked most to least likely (all unconfirmed — this is the investigation's
starting hypothesis set, same discipline as TASK-385/386):**

1. **ICY-metadata pipeline stalled independent of audio/touch/loopTask.** `s_icyTitleQueue`
   (`webRadioApp.h:107`, single-slot `xQueueOverwrite`) is fed by the Audio library's metadata
   callback and drained non-blockingly in `tick()`. The existing stall-detection apparatus
   (`WR_STREAM_DEAD_MS`, TASK-218/291's "no bytes consumed" debounce) is tuned to catch the PCM
   byte-level stall case; it's unconfirmed whether metadata delivery specifically can silently stop
   while byte-level stall-detection still reads the stream as healthy (or vice versa — audio still
   audibly playing while metadata parsing wedges). This would produce exactly the observed symptom:
   a real, stale title frozen on screen, with everything else (touch, heartbeat, presumably audio)
   still alive. Distinguishing test: `get wrIcy` during a live freeze — if it matches the frozen
   on-screen text, metadata delivery stopped upstream of the marquee; if it shows a *newer* title
   the marquee never picked up, the bug is in the marquee's consumption of the queue instead.
2. **Marquee scroll-state stuck independent of ICY delivery.** `_tickMarquee()`
   (`winampDisplay.h:836`) only redraws when `titleScrollDeadline != 0 && millis() >= deadline`. A
   short title intentionally sets `titleScrollDeadline = 0` (static display, no scroll — not a bug
   by itself), but if a *new* title never gets to `setTitle()` at all (see hypothesis 1) this reads
   identically to "marquee is broken." Needs the new getter (below) to tell apart from hypothesis 1.
3. **WiFi-down override (`_wifiDownOverrideActive`, `winampDisplay.h:196-234`) latched and never
   cleared.** Ranked low-likelihood specifically because the visible text was real station content
   ("...n de pauzuh"), not the override's fixed `"WI-FI: RECONNECTING..."` string — if this were
   active, that string would show, not stale station content. Kept as a hypothesis only because the
   override *could* have engaged and cleared earlier in the session in a way that left some other
   state inconsistent; the getter below settles it in one read.
4. **Extended-uptime resource contention as a contributing factor, not the direct mechanism.** The
   live log showed Spotify's background poll continuously failing (`HTTPC_CONNECTION_REFUSED`
   alternating with `403`, backoff climbing every ~30-60s cycle) concurrently with WebRadio
   playback, for over an hour of uptime by the time the freeze was noticed. Matches this project's
   prior tlsYield-contention/heap-fragmentation-under-sustained-load precedent class
   (TASK-287/288/289, and TASK-385/386's still-open hypotheses for an unrelated app). Not a
   standalone mechanism — would need to combine with 1 or 2 to actually produce a frozen marquee —
   but worth checking `get heap`'s `lfbInt`/`lfbDma` at repro time against this session's
   established baselines.
5. **Regression from today's TASK-387/388/389 changes.** Lowest likelihood: none of today's edits
   touch `WinampDisplay`'s marquee code, the ICY queue, or the top-level render dispatch — they're
   scoped to the vis area (`vuMeter.h`), `audio_process_extern`'s per-block math
   (`webRadioApp.h`), and the Settings UI (`appsSection.h`/`settingsStorage.*`). Kept as a
   hypothesis only for completeness and because it's the cheapest to rule out: if reproduced, A/B
   against a build with today's three commits reverted settles it in one soak.

**Investigation plan (not yet executed — DUT-gated, needs a long unattended/monitored window):**

- Add a `get wrMarquee` debug getter (mirrors this session's `wrSpec`/`wrWave` precedent) dumping
  `titleScrollOffset`, `titleScrollDeadline` (plus `millis()` so the caller can compute the delta
  without a race), `lastTitle`, and `_wifiDownOverrideActive` — the single missing piece that lets
  hypotheses 1-3 be told apart the moment a freeze is caught live.
- Flash `cyd2usb_winamp_debug`, tune into a real, currently-live station — ideally SLAM! or another
  ID-heavy commercial station (frequent title changes stress the ICY-update path harder than a
  quiet talk station would) — and sustain playback for an extended, unattended window (no existing
  canned soak fits this: `run/wr-soak` cycles play/leave every ~20s by design, which is the wrong
  shape for a "sits on one station for a long time" bug). Leave Spotify's background poll running
  rather than suspending it, matching the environment the original freeze happened in (hypothesis 4
  needs that concurrent churn present to have a chance of mattering).
- Poll `get wrIcy` + the new `get wrMarquee` + `get heap` + `get wrPump` + a screendump on an
  interval (e.g. every 60-120s) for the full soak duration. On a freeze: compare `wrIcy` against
  the on-screen text and `wrMarquee`'s state to place the fault per hypothesis 1 vs. 2 vs. 3.
- If not reproduced in a reasonable window (say, 60-90 min — unknown true MTTF, this is a budget
  not a bound): disposition as unconfirmed/intermittent, same honest framing TASK-385/386 already
  use, rather than closing on absence of a forced repro.

**Architect review (2026-08-03):** No new ADR or design doc warranted — this is a bug
investigation with a small, well-scoped diagnostic addition (one debug getter, read-only, no new
persistent state, no cross-component interface change), not a design decision. Cross-component
note worth flagging for whoever picks this up: hypothesis 1's queue (`s_icyTitleQueue`) and the
marquee's `setTitle()` gate both live on the boundary between the pump/Audio-library callback
context and the UI-thread render path — same class of boundary TASK-387/388 already had to reason
about carefully for `vu::specHRef()`/`waveTraceRef()` (single-writer discipline). Worth explicitly
confirming the ICY callback and `tick()`'s drain are still correctly single-producer/single-consumer
before assuming the queue mechanism itself is innocent — it wasn't audited as part of this filing.
No storage-headroom concern: `get wrMarquee` is a pure read-only getter over existing fields, same
shape as `wrSpec`/`wrWave` (net zero new static bytes) — this board's shrinking `dram0_0_seg`
headroom (see `[[project_webradio_headroom_finding]]`, 20B as of this session) is not at risk here,
but flagging since it's a live constraint on this exact file. Approved for scheduling as filed.

**VE review (2026-08-03):** Exit criteria as drafted above are testable but not yet automatable —
this is a real gap, not an oversight: the repro depends on real-world station content and an
unknown, possibly long, time-to-failure, which doesn't fit `run_serialdbg_tests.py`'s
short-deterministic-assertion model. Recommend, once reproduced at least once with the new getter:
(a) capture the exact `wrIcy`/`wrMarquee` state pairing that a real freeze produces and turn *that*
specific signature into a fast synthetic test (`set wrIcy <value>` injection already exists per
`webRadioApp.h:1347-1350` — a synthetic repro harness is plausible once the real mechanism is
known, not before); (b) until then, this stays a manual/soak-verified item, not a suite addition —
do not force a T_WR_MARQUEE_xx id into `run_serialdbg_tests.py` before the failure mode is
understood, that would just encode a guess as a permanent assertion. Testability challenge for the
Developer taking this on: the "not reproduced in 60-90 min" disposition path needs an explicit,
stated confidence level (this is a budget, not a bound, per the investigation plan above) — don't
let a single clean soak read as "fixed" the way TASK-385's first isolated-rerun mistake did.

**Owner:** Developer (investigation) · **Deps:** none blocking; loosely related to TASK-385/386's
open extended-uptime/resource-contention hypothesis class (#4 above) and shares this session's
`get wrSpec`/`get wrWave` getter precedent for the new `get wrMarquee` · **Gate:** DUT session with
an extended unattended soak window, new getter added first · **Priority:** P2 (real user-observed
defect on production firmware, not a test artifact) · **Status:** open — filed, reviewed
(Architect approved as filed; VE flagged the automation gap above), **soak attempted same session,
paused mid-investigation — see below.**

**Soak attempt 2026-08-03 (same day as filing) — paused, not completed.** `get wrMarquee`
implemented (`winampDisplay.h`, chained through the existing `spotifyDisplay->dbgGet()` polymorphic
path — `spotifyDisplay` is `&winampDisplay` for this build, so no new dispatch wiring was needed;
zero new static bytes, confirmed via unchanged RAM-used in the build report). Flashed
`cyd2usb_winamp_debug`, entered WebRadio with Spotify's background poll deliberately left running
(matching the original freeze's environment), loaded the real 30-station NL list, selected "SLAM!
DANCE CLASSICS" (index 23 — the closest real match to the human's original report), started
playback.

**What actually happened, not what was originally being tested for:** within 90s, `wrState`
transitioned to `ERROR_UNREACHABLE` ("Station unreachable") and stayed there across 4 consecutive
90s-spaced polls (240s+) with zero visible recovery. This is **not** the originally-reported
symptom — the marquee correctly showed the error text, not frozen-stale-real-content — but it's a
second, real, DUT-observed WebRadio defect-shaped signal worth its own line: `wrPump` stayed alive
with `cycles` climbing steadily (~45,000/90s, consistent, no stall in the pump task itself) and
heap stayed rock-stable (`lfbInt` flat at 42996 across the whole window, no fragmentation) — so
whatever's happening isn't a crash, leak, or pump-task hang, just an apparent failure to progress
past the error state.

**Self-caught methodology gap, worth recording as its own lesson:** the first soak's poller
captured `wrState`/`wrIcy`/`wrMarquee`/`heap`/`wrPump` but **not** `wrIdx` or `get wrSkip`
(`autoSkip`/`tried`/`retries`). `webRadioApp.h:610-648`'s auto-skip logic has two layers — an
immediate multi-station burn-through on connect failure, and (once parked in a terminal error) a
30s-paced re-arm that retries whatever station it's currently parked on, not necessarily a
*different* one. Without `wrIdx` per-poll, "stuck in `ERROR_UNREACHABLE` for 4 minutes" cannot be
told apart from "auto-skip correctly cycling through a network that's currently bad end-to-end" —
these look identical from `wrState` alone. **Initially over-called this as a confirmed stuck-state
bug before catching the gap** — corrected before writing it up as more certain than the evidence
supports. This is exactly the discipline TASK-385's history already flagged (don't let an
incomplete read pass as a confirmed finding) — recorded here as a second instance of the same
lesson, not just a one-off.

**Follow-up attempt blocked, investigation paused (human decision):** rebuilt the poller to add
`wrIdx`/`get wrSkip`, but the station-list fetch then failed **three consecutive times** on
re-entry — confirmed NOT the heap-guard this time (`get heap` on a fresh boot showed
`lfbInt=42996`, comfortably clear of the ~40k gate) — a live recurrence of the pre-existing
TASK-284 radio-browser-flakiness class, not a new issue and not something to hammer further
per that task's own "space out fetches" lesson. Human paused the investigation here rather than
continuing to burn reconnect/fetch attempts against a currently-uncooperative external service.
Production firmware restored, DUT left clean.

**State for whoever resumes this:** the original marquee-freeze-with-stale-content symptom was
**not reproduced** this session — zero data either way on hypotheses 1-3. The `ERROR_UNREACHABLE`-
parking observation above is a **separate, real signal**, currently unclassified (bug vs. expected
behavior against bad network conditions) pending a clean run with `wrIdx`/`wrSkip` instrumentation
(the corrected poller already exists, just never got a clean station-list fetch to run against —
`/tmp` scratch path from this session, not committed; whoever resumes should rewrite it fresh
rather than hunt for the throwaway). Next session: retry once radio-browser is healthy again
(`get wrCount` succeeding is the go/no-go signal, same as every other WebRadio DUT session this
project has had), watch `wrIdx` specifically to resolve the auto-skip question first — that's now
higher-priority than the original marquee hypothesis, since it's the thing actually reproduced.

**TASK-391 update (2026-08-03):** host-side A/B testing found real, repeat-run evidence that
`Audio.h`'s tight default connect-timeout (250ms HTTP/2700ms HTTPS) is clipping genuinely-good
connects (0/36 failures at 5s budget vs. 11/36 at the default budget, same hosts/network) — a
plausible contributor to this task's `ERROR_UNREACHABLE`-parking signal specifically. Does **not**
reproduce or explain the original marquee-freeze symptom (host-side 10-minute soak against SLAM!
DANCE CLASSICS stayed healthy throughout, no sustained stall) — that thread stays open, unchanged,
pending the `wrIdx`/auto-skip retry above. Candidate timeout fix filed as TASK-392, gated on DUT
confirmation. Full results: TASK-391 entry below.

**Live correlation found 2026-08-03, later same session (human-flagged):** a DUT was already
running (production `cyd2usb_winamp`, `spotify-mon` tmux monitor session, boot ~15:20) when this
session's TASK-391 work started — missed initially; should have been checked per the design doc's
own "Correlation with DUT runs" section. Once found, its live heartbeat showed the *exact*
TASK-390 signature actively in progress: `last_render_age_ms` climbing in lockstep with `uptime`,
zero repaints. Back-calculated onset from two heartbeat readings (both agree): **~18:20:42**,
~180.7 min into uptime — about 20 min *before* TASK-391's 3-hour host soak started (18:41:33), and
it was still frozen when that soak completed at 21:41:33 (200+ min frozen and counting, confirmed
again after). `heap=128k`/`maxAlloc=41k` unchanged throughout (not a crash/heap issue),
WiFi rssi stayed in a normal range (-43 to -55, not a WiFi drop), `poll=0/177` (Spotify polling,
unrelated to WebRadio) failing the whole session.

**This gives the disposition-matrix outcome #4 comparison the design doc asked for, even though
the overlap was partial (missed the actual onset moment):** for the entire 3-hour host soak
window, the host sustained a healthy connection to the *same station family* (SLAM! DANCE
CLASSICS) — 180 min, only 5 brief reconnects (each recovering within seconds, real titles tracked
throughout, 45 timeline events) — while the DUT sat completely frozen the whole time, both before
and during. Network/CDN health is not in question here; the DUT's render pipeline stopped calling
repaint on its own. This points at outcome #4 (DUT-specific, in the render/marquee pipeline, not
network) as the more likely explanation for the original marquee-freeze report, though it's a
timing correlation, not a captured root cause.

**Confirmed no live introspection possible on this instance:** sent a single safe, read-only probe
(`help`, matches `cmdHelp` in the SERIAL_DEBUG-only list — not the always-compiled `reconnect`
command, deliberately avoided since it forces a TLS reset + poll and would have cleared the frozen
state). Response: `{"ok":false,"error":"unknown command","cmd":"help"}` — confirms production
build, no `get`/`set`/`screendump` surface, exactly the wall this task's own "diagnostic gap"
paragraph above already flagged. No further live diagnosis possible on this instance without
reflashing debug (which would reboot and lose it). Left running, not touched further, decision on
reflash-vs-continue-observing handed to the human.

**Session note (2026-08-06) — `last_render_age_ms` caught disagreeing with a direct eyeball check;
weakens it as this task's primary diagnostic signature.** Found a live production `spotify-mon`
tmux session already running (`tmux ls`, per `[[feedback_check_for_live_dut_session_before_host_only_claims]]`)
mid-WebRadio-playback, auto-skipping between several NL stations over ~2h40m uptime.
`last_render_age_ms` climbed in lockstep with `uptime` between every station switch (resetting
only on switch events) — superficially matching this task's original signature. But at one
specific moment the human was asked to look at the physical screen directly, live: title had "just
changed, scrolling to 'radio 10'" — a real, directly-observed, correctly-scrolling repaint — while
the log's `last_render_age_ms` at that same moment showed no reset and kept climbing for 11+
minutes past it (`StreamTitle=''` → station-name-fallback repaint, not a `StreamTitle` change, is
the likely uninstrumented path). **Reading:** the counter does not cover every repaint code path
(the station-name-fallback case specifically), so a climbing `last_render_age_ms` does **not**
reliably mean the screen is stuck — it can be actively, correctly updating while the counter
reports otherwise. **Confirmed a second time, same session, ~10 min later:** switched to Radio 10,
a real `StreamTitle='Robbie Williams - Supreme'` arrived in the log and was directly observed on
the physical screen scrolling correctly at the same moment — `last_render_age_ms` again did not
reset (1165632 → 1195633 across that exact log line). So this isn't limited to the station-name-
fallback path either; a normal ICY-driven title-change repaint also doesn't reset the counter.
Broadens the finding: treat `last_render_age_ms` as unreliable for *any* mid-station title-change
repaint, not just the fallback case. This does **not** confirm or disprove the original 2026-08-03 report (a direct
human sighting of a genuinely stuck title fragment, independent of this counter) — it only weakens
confidence in using this specific field as a stand-in for "is the marquee actually stuck" going
forward. **Not closing as unable-to-reproduce** — no attempt this session actually tried to
reproduce the original conditions (extended single-station play, no auto-skip churn); this was an
opportunistic check of an already-running unrelated session. **Revised "what to look for" for
future repro attempts:** direct eyeball only, don't trust `last_render_age_ms` alone — watch for
(a) ticker text that has stopped scrolling/animating when it's long enough that it should be
scrolling, and (b) title text that visibly doesn't match what's currently audible/announced for an
extended stretch (the original report's "...n de pauzuh" fragment is the shape of a real positive:
a stale, static, truncated-looking title). If `last_render_age_ms` is used as a corroborating
signal, treat a *long* stretch with zero station switches as the only regime where it's meaningful
(the reset-on-switch masking observed here doesn't apply when nothing switches for a long time,
matching the original single-station report's setup) — cross-check any live reading against the
physical screen before trusting it alone.

### TASK-403 — PlaneRadar fetch: HTTP response compression (brotli) support

Origin: TASK-361's candidate-scoping pass (2026-07-25). Live `curl -H "Accept-Encoding: br"`
against `opendata.adsb.fi` returned a **9.2 KB body vs. 56.9 KB uncompressed at the same JFK
query — a 6.15x reduction** — which per TASK-361's own confirmed size-scaling data (truncation
failure rate climbs with payload size) would very plausibly collapse the fetch-truncation
failure rate back toward TASK-313's original floor. Called "probably the single highest-impact
lever available" at the time, explicitly not implemented as part of TASK-361 (too large for that
task's scope) and never filed since.

**Why it's real work, not a quick win:** the vendored Arduino-ESP32 `HTTPClient.cpp`
(`framework-arduinoespressif32/libraries/HTTPClient/src/HTTPClient.cpp:1217`) unconditionally
sends `Accept-Encoding: identity;q=1,chunked;q=0.1,*;q=0` — no user override point as vendored —
and there is no gzip/brotli decoder anywhere in this firmware today (confirmed via grep across
`app/src`). Fixing this needs: (1) a library patch making the Accept-Encoding header overridable
(this project already has a `LOCAL_PATCHES.md` precedent for SpotifyArduino — same mechanism);
(2) a streaming decompressor integrated as a `Stream` adapter feeding `prParseStream()` — brotli
decode is heavier than gzip/deflate, and even deflate's ~32 KB window is a lot against this
board's tight DRAM budget (see `[[feedback_dram_bss_static_buffers]]` memory note — this board
has overflowed DRAM on additions as small as 264 bytes before); (3) a RAM budget review before
committing to which codec, if any, actually fits.

**Owner:** Architect (design/feasibility pass first — this is exactly the "separately-scoped
design/task" TASK-361 deferred to) · **Deps:** TASK-361 (shipped mitigation already lowers the
acute urgency — radius-capped 2nd retry is in production and TASK-361's own follow-up soaks
never reproduced the original "both attempts fail" condition live) · **Priority:** P3 (real,
well-evidenced, but not currently blocking — TASK-361's cheaper fix is holding) · **Size:**
L (library patch + decompressor + RAM budget review) · **Gate:** design doc first; no
implementation without an Architect feasibility call, given the DRAM-budget risk. ·
**Status:** **OPEN — feasibility gate cleared 2026-08-06, deferred at P3** (design doc landed,
not implemented; see session update below).

**Session update (2026-08-06) — Architect feasibility pass done, gate cleared for a future
implementation task; not implemented this session.** Full design doc:
[`M-PLANERADAR-http-compression.md`](../architecture/designs/M-PLANERADAR-http-compression.md).
Findings in brief:
- **RAM verdict: feasible, and easier than the gate's framing implied.** Deflate/gzip's window is
  spec-capped at 32 KB (unlike brotli, which the original `curl` test happened to use first, not
  deliberately chose); as a transient dataTask-serial scratch buffer freed right after parse, it's
  the same lifecycle already carried by `planeradar_doc`/`heatmap_doc`/`crypto_doc` in
  `app/mem_manifest.yaml`, comfortably inside today's ~185 K nominal unallocated INTERNAL headroom.
  No WebRadio-style arena/reclaim design needed — this fetch has no DMA-contiguity or long-residency
  constraint.
- **Mechanism verdict: already proven on this board.** `app/lib/WiFiClientSecure/` already vendors
  and patches (PATCH-001/003) a framework-supplied library to shadow the Arduino-ESP32 core's own
  copy — the exact mechanism TASK-403 needs for `HTTPClient.cpp`'s unconditional `Accept-Encoding`
  header, not a novel approach.
- **Scope correction: recommend gzip, not brotli**, as the implementation target — lighter decoder,
  bounded window, no embedded precedent gap to close. Brotli (TASK-361's only actual measurement)
  is explicitly not the recommended codec.
- **Priority verdict: concur with P3, stay deferred.** TASK-361's radius-capped retry2 is
  code-reviewed and fault-injection-proven to fire correctly, and three post-fix soaks at
  JFK-scale traffic found the original truncation condition not reproducing organically — final
  failure rate 0% in every soak since. No open user-visible symptom this would currently fix;
  revisit on real recurrence (watch for frequent `radius-capped`/`retry2` log lines) or a future
  need to shrink fetch size for its own sake.
- Open questions before any implementation starts (full list in the design doc): whether
  `opendata.adsb.fi` actually serves `gzip` (only `br` was ever tested), the real gzip ratio on
  this payload shape, and which embedded inflate implementation to use.

### TASK-439 — progress-based DUT readiness wait (TASK-434 item 3, redesigned)

Deferred from TASK-434 on VE's challenge. The goal stands: replace a fixed deadline with "wait while
the boot is making progress, fail fast when it is not", so a healthy-but-slow boot is not failed and
a wedged one does not burn the full budget.

**What is already settled**, so the next attempt does not re-derive it:
- The literal string `NO_AP_FOUND` is never printed by this firmware. The observable is
  `[wifi-ev] t=<ms> ev=5 STA_DISCONNECTED reason=<code>` (`wifiDiag.cpp`).
- `reason=201` **is** the live AP-absent code, measured on this rig 2026-08-14 (TASK-436): a metronomic
  2.42 s cadence while the saved AP was out of range.
- `wifiDiag` caps `[wifi-ev]` at 10 lines per rolling minute, then prints only a `suppressed=N`
  summary — so an actively flapping DUT can be silent for up to ~60 s. Silence alone cannot mean
  "give up".
- A healthy boot emits `STA_START` → `STA_CONNECTED` → *silence for the DHCP round trip* →
  `STA_GOT_IP`. Any silence rule must treat the post-`STA_CONNECTED` gap as expected.

**Design constraint:** key on `reason=` value and repetition count, not on string presence, and
anchor the silence rule to which event was last seen rather than to a bare timer.

**Owner:** VE (design) / Developer (implement) · **Deps:** TASK-434 (landed) · **Gate:** a healthy
boot must not be slowed measurably; an AP-absent boot must fail faster than the 100 s TASK-434 now
allows, and must still print the `[SETUP-FAIL]` block with its serial tail · **Priority:** P3 — the
100 s bounded wait plus a clear setup status already removes the misread that made this urgent ·
**Status:** OPEN — filed 2026-08-14.

### TASK-437 — a WiFi password entered in the Settings UI did not connect

Observed 2026-08-14 immediately after TASK-436's scan fix let the network list render for the first
time on a foreign AP. The operator selected the AP, typed the password on the on-screen keyboard,
and the connect failed. Real failure, not a UI misreport: `/wifi_networks.json` still holds only the
pre-existing `<home-ssid>` entry, and `_onConnectSuccess()` is the only writer.

**Root cause NOT established, and deliberately not guessed at.** The serial capture had already
wrapped (~167 lines of tmux scrollback) so the `[wifi-ev]` reason code is gone. The one datum that
would split the candidates is what `repaintResult()` printed, which the operator saw and can
report — it already distinguishes three cases:

| Screen text | `_failReason` | Points at |
|---|---|---|
| `Wrong password` | `WL_CONNECT_FAILED` | keyboard entry — a dropped shift on a mixed-case password, or a real `keyboardWidget` defect |
| `Network not found` | `WL_NO_SSID_AVAIL` | scan/association mismatch — band steering or an SSID that scanned but would not associate |
| `Timed out` | neither (15 s bound in `tick()`) | the 15 s window is too tight; a BT Whole Home mesh can exceed it, and the boot chain elsewhere allows far longer |

The third is the one with real fix content: `tick()`'s bound is a bare `15000` while the boot
cascade budgets much more per candidate, and a connect that succeeds at 16 s would render as a
failure *and* still land in NVS via `WiFi.persistent(true)` — a confusing "it says failed but it
works later" state.

**Do not close this by reasoning from the three candidates.** Get the screen text first, or
reproduce with the debug build (`kb:submit pass_len=` is `SERIAL_DEBUG`-gated, and the `[wifi-ev]`
reason code names AUTH_FAIL vs NO_AP_FOUND directly). Raise the tmux scrollback before retrying —
losing the evidence window is what made this un-diagnosable the first time.

**Owner:** Developer · **Deps:** none · **Priority:** P2 — the SPIFFS push
(`./run/spiffs push wifi_creds.json`) is a working operator path, so this is not a device-bricking
gap; but it is the *only* on-device way to join a new network, so it is P1 for anyone without a
host · **Status:** OPEN — filed 2026-08-14, awaiting the screen text.

### TASK-438 — the WebRadio station fetch can stay `pending` indefinitely, and abort does not clear it

Observed 2026-08-14 while building TASK-432's gate, on `cyd2usb_winamp_debug` with WiFi up (RSSI -43,
`disc=0`, the device was reachable by ping from the host throughout). `get wrCount` returned
`count=0,pending=1` on every poll for 90 s continuously. `set wrUrl` — which calls
`dataTask::abortWebRadioFetch()` before deferring — did not clear it either, so the deferred
injection it queues (`_deferredInject`, played by `tick()` "once the result lands") never fired.

**Consequence:** any path that waits on the fetch resolving waits forever. That includes `set wrUrl`
without an explicit `set wrPlay` kick, which is why two runs of TASK-432's gate sat watching
`state=STOPPED`.

**Not yet distinguished, and the whole point of the task:** whether this is (a) the network — this
was an unfamiliar AP, and TASK-284 already documents radio-browser mirror truncation and rate
limiting coming and going, or (b) `abortWebRadioFetch()` genuinely failing to park a result when the
in-flight request is stuck in DNS/connect rather than at a checkpoint. Case (b) would be a real
defect and would also explain some of TASK-284's "empty list forever" history.

**How to tell them apart:** run `app/tools/test_radiobrowser_api.py` from the host on the same
network first (per the established "validate on the host before flailing on the device" practice). A
host fetch that also fails puts it on the network; a host fetch that succeeds while the device sits
at `pending=1` puts it on the abort path. Then check whether `dataTask` ever posts a result with
`http=-102` after an abort.

**Owner:** Developer · **Deps:** none · **Priority:** P2 · **Status:** OPEN — filed 2026-08-14 from
TASK-432's gate development. Do not merge into TASK-284 until (a) vs (b) is settled; they are only
the same bug under hypothesis (a).

### TASK-262 — Cleanup placeholder: revert TASK-261 spike artefacts on FAIL/shelve

Lifecycle placeholder for TASK-261 (BP-040: an experiment names its cleanup id before scheduling; filed in the
same change as TASK-261). **Action on a Phase-1 FAIL or a shelve:** if any spike artefact reached trunk (the
vendored `lib/ESP32-audioI2S` fork, the reserved-arena allocator, the caps-split probe if deemed not worth
keeping, any `[env:]`/`-D` flag, the `cross_feature_matrix` rows), revert it; remove any `run/check` entry.
**No-op if nothing merged** — the design keeps the fork/arena on `rnd/membudget` until a Phase-2 PASS, so the
expected steady state is "nothing to clean."

**UPDATE 2026-06-28 — spike PASSED, so the FAIL-cleanup branch is moot; this task is REPURPOSED as the A-lite
PROMOTION gate** (human chose "de-risk then promote"). Promotion = merge `rnd/membudget` → master + ungate
(make the arena/fork production, not `MEMBUDGET_PHASE1`-only). **Gated on ALL of:** TASK-263 (halved-DMA
validation) green, TASK-264 (M-RECLAIM Q3-a overlay) green, TASK-265 (live fetch) green, **and TASK-243
(Premium) cleared** for the Spotify-active coexistence validation. Until all green, the fork stays branch-only.
**Priority:** P2 — promotion gate · **Status:** **blocked — gated ONLY on TASK-243 (Premium)** — all design/
engineering de-risk complete: TASK-263 (halved DMA) ✅, TASK-264 (overlay Q3-a) ✅, TASK-265 (fetch finding)
✅, **TASK-267 (fetch-vs-arena fix) DUT-verified PASS 2026-06-28** ✅. **Mainlined 2026-06-28 (`adeab7c`)** — `rnd/membudget` merged to master with A-lite **gated**
(`MEMBUDGET_PHASE1`); production `cyd2usb_winamp` byte-clean (count 0), `run/check` 5/5. The dead-mirror fix +
TASK-259 player-mode + all records are now on master; the `ef8e32c` divergence + a doubled-`#ifdef` auto-merge
artifact were resolved. **Remaining for promotion (the only un-done step):** TASK-243 (Premium) clears →
validate Spotify-active coexistence on the full multi-app build → **ungate `MEMBUDGET_PHASE1` for production**
(flip it on in `cyd2usb_winamp`).

**PROMOTED 2026-06-29 (provisional, without Premium) — branch `feature/task-262-promote-alite`.** Decision
(human): the TASK-243 gate is belt-and-suspenders — `MEMBUDGET_PHASE1` gates **only WebRadio-exclusive code**
(JIT `mb_arena`, halved-DMA fork, decoder→`mb_arena_alloc` routing), and this device outputs **no audio for
Spotify** (display/control only — no I2S/DMA path), so flipping it on changes **zero Spotify runtime
behaviour**. The TASK-264 TLS-drop coexistence mechanism was already in production (gated by `DISABLE_SPOTIFY`,
not the budget flag). What changed:
- `-DMEMBUDGET_PHASE1` moved from `cyd2usb_winamp_debug` → **`cyd2usb_winamp` (production)**; debug inherits it.
- The verbose `[membudget]`/`[mbdbg]` probes (CP0/CP1/CP2, `mb_heap_probe`, arena acquire/release/first-alloc,
  helix-alloc) re-gated `MEMBUDGET_PHASE1 && SERIAL_DEBUG` → **ship silent** in production.
- Dropped the dead `MEMPLAN_STATIC_DECODER` OQ1 experiment; arena `mb_arena_acquire()` call made unconditional
  (libc-fallback when flag absent). `run/check` 6/6 (production now compiles **with** the arena).

**DUT validation 2026-06-29:** arena code proven on the equivalent build (`cyd2usb_webradio`, same
`MEMBUDGET_PHASE1`, no 403 starvation) — `arena acquire=24576B lfbBefore=61428 **OK**` (real 24 K internal
block, not libc-fallback), `arena FIRST alloc ... cap=24576` (Helix decoder allocates **from** the arena),
`wrState=2 wrPlaying=1` (**PLAYING**), idempotent re-acquire — **6/6**. Production `cyd2usb_winamp` boots clean
(heap=134k/maxAlloc=47k idle), runs steady, **no probe spam**, no panic.

**Residual (the only thing Premium would add):** confirming Spotify *renders a playing track* under the
promoted build — nil risk, since the promoted build changes no Spotify code path; and the WebRadio station
fetch on the Spotify-enabled build is itself starved by the TASK-243 403 (project memory: tlsYield
starvation). **Rollback:** TASK-256 (revert `-DMEMBUDGET_PHASE1` from `cyd2usb_winamp`). · **Status:**
**PROMOTED — provisional, DUT-validated 2026-06-29; residual Spotify-render check owed on TASK-243** ·
**Opened:** 2026-06-27 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:**
Developer/PM · **Deps:** TASK-261 (done), ~~TASK-263~~, ~~TASK-264~~, ~~TASK-265 (done→TASK-267)~~,
**TASK-267**, TASK-243 (residual only)

---

### TASK-393 — WebRadio ERROR_* render freeze, live-reproduced on debug build; terminal-retry not firing

**Filed 2026-08-03, same session as TASK-390/391, human-directed** ("could we do an extended soak,
3h?" → live DUT correlation found while that soak ran → flashed debug build → drove WebRadio into
the exact failure and caught it live with full introspection). This is the strongest evidence yet
for TASK-390's render-freeze thread — reproduced on demand, not just observed after the fact.

**Repro steps (debug build `cyd2usb_winamp_debug`, via `tmux send-keys` into the already-open
monitor — no new serial connection, no DTR reset):**
1. `switchApp 11` (WebRadio's current `AppId` — verified via `app/tools/app_ids_gen.py`'s
   `APP_SLOT` map, **not** the `switchApp 10` `test_webradio_soak.py` hardcoded. **Correction
   (2026-08-03, later same session):** the guess here that `cyd2usb_webradio` has a different,
   trimmed app registry was wrong — `appRegistry.h` is one unconditional list, identical across
   every env; `WEBRADIO_ONLY` is an unrelated memory-budget flag, not a registry trim. `10` was
   simply stale everywhere, full stop — see TASK-394, which traces exactly when and fixes it.).
2. Station list fetch hit a live `HTTP 503` from radio-browser (`get wrLastHttp` — real, ambient
   flakiness, unrelated to anything in this session). Sidestepped with the debug-only
   `set wrUrl http://stream.slam.nl/WEB15_MP3` (TASK-261 Phase 2 lever — injects a single
   synthetic station and plays it immediately, bypassing the fetch).
3. First connect succeeded (`StreamTitle='September - Cry For You'`, `last_render_age_ms` reset to
   4398 — **confirms active playback does reset the render clock; idle screens climbing on their
   own is separately normal, not a symptom** — this session briefly worried a fresh idle boot's
   own climbing `last_render_age_ms` was the same bug; it isn't, this comparison settles it).
4. ~5s in: `stream dead (isRunning=1 for 0ms, bufStalled for 5000ms)`, one stall-retry per
   `_onPlaybackFailed`'s policy, retry's `connecttohost()` to `stream.slam.nl` itself failed
   (`"Request ... failed!"`) — plausibly another instance of TASK-391/392's connect-timeout
   finding, though not confirmed as the specific cause here. `_state → ERROR_UNREACHABLE` (5).

**From that point, `last_render_age_ms` climbed in exact lockstep with `uptime` for the entire
observation window (348s+, zero resets, two independent `get wrState` checks both returned `5`
throughout) — the identical signature as the live DUT correlation found earlier this session and
TASK-390's original report.** `get wrScroll` while parked: `offset=0 drag=0 vel=0 accum=0` — fully
static, matching the human's own live observation on the physical LCD this session ("buffer/POS is
at zero (left)"). `get heap`/`get stacks` both healthy throughout — not a resource issue.

**Root-cause candidate, not fully confirmed:** `webRadioApp.h`'s `tick()` only calls `_drawFull()`
when `_dirty` is set, and once parked in an `ERROR_*` state nothing in the normal per-tick PLAYING
block runs (it's gated on `_state == PLAYING`), so `_dirty` only gets set once (the transition into
the error state) and never again — matching the freeze. **This is expected to be already handled**
by TASK-276's own terminal-retry mechanism (`webRadioApp.h:623-634`, `WR_TERMINAL_RETRY_MS=30000`)
— re-arms a fresh play attempt every 30s specifically so the app never parks forever. **That
mechanism did not fire even once in 348+ seconds** (no `"terminal retry — re-arming scan"` log
line ever appeared, `wrState` never left `5`), despite every logged precondition appearing
satisfied (`webRadioAutoSkip` defaults `true`, `_state` is one of the three retryable errors,
`_stationCount=1 > 0`, elapsed time was >10x the threshold). **Why the re-arm isn't firing is not
determined** — `get wrAutoSkip` isn't a valid debug var (that key belongs to a different app's
dbgGet, a dead end), and further tracing needs either a breakpoint/instrumented build or reading
`_pendingAction`'s actual runtime value some other way. Flagged as the concrete next step, not
solved here.

**Relationship to other WebRadio tasks:** doesn't fully explain the *original* human report (this
repro's `wrIcy` was empty when frozen — no stale title text — whereas the original report saw a
stale real fragment, "...n de pauzuh"). Same *class* of bug (render pipeline stuck while parked),
not necessarily byte-identical mechanism. Directly classifies the "ERROR_UNREACHABLE parking"
signal TASK-390 flagged as "separate, real, currently unclassified" — it's now classified: real,
reproducible, and its supposed auto-recovery isn't working.

**Owner:** Developer · **Deps:** TASK-390 (feeds it), TASK-391/392 (connect-timeout evidence this
repro's own connect failure is consistent with) · **Priority:** P2 (downgraded from P1 — see
below; the original freeze was directly witnessed and logged, but three independent real-network
repro attempts couldn't re-break the retry mechanism, so this is no longer a reliably-reproducible
defect to hand a Developer as "fix this") · **Status:** open — the render-freeze-while-parked
*symptom* was live-reproduced once; the *retry-doesn't-recover* mechanism behind it could not be
re-triggered in three further attempts (see update below). Needs recurrence + better
instrumentation-at-the-moment before a root cause is findable.

**Update (TASK-395's `T276` test, same day):** the retry re-arm's own condition logic tested
correctly (PASS, fired at 32s) under `wrDeadUrls`'s synthetic forced-fail path — see TASK-395 for
the full result. That path never calls the real `connecttohost()`, so this narrows the regression
to something specific to state left behind by a genuine failed connect, not the retry logic
itself. Next repro should use a real dead URL (`set wrUrl`), not the synthetic hook.

**Update (real-dead-URL reproduction attempted, same day, human-directed) — could NOT re-break it,
three separate ways:**

1. **Real raw-IP dead host (`set wrUrl http://192.0.2.1/dead`, RFC 5737 TEST-NET, single injected
   station, immediate `connecttohost()` failure via the real network stack — no PLAYING ever
   happened first):** landed terminal `ERROR_UNREACHABLE` on the first attempt. Retry fired
   reliably at **30s, then 30s, then 30s again** — three consecutive clean cycles, heap stable
   (54k, no drift), before being stopped manually. (Note: raw-IP hosts hit TASK-295's existing
   `10000ms` timeout bump, not the normal 250ms — expected, unrelated to this question; each
   `_play()` attempt itself took ~10s to fail, the *retry cadence* was still a clean 30s.)
2. **Real hostname (`set wrUrl http://stream.slam.nl/WEB15_MP3`), natural connect → play → stall →
   stall-retry → second failure → terminal — structurally the same shape as the original human
   report and this task's own live repro above:** reached terminal `ERROR_STALL`/`ERROR_UNREACHABLE`
   repeatedly as the real stream connected, played briefly, and stalled again (real StreamTheWorld
   edge-server flakiness, matches TASK-391's own findings). **The terminal-retry fired every single
   time it was checked — four separate `"terminal retry — re-arming scan idx=0"` log lines across
   one continuous ~5-minute session**, each landing back at a fresh connect attempt.

**None of the three independent reproduction methods (synthetic multi-station, real single-station
immediate-fail, real single-station stall-then-fail matching the original conditions structurally)
could reproduce the 348+s-with-zero-re-arms behavior originally observed.** The terminal-retry
mechanism held up under repeated, deliberate stress today. This does not mean the original
observation was wrong or imagined — it was directly witnessed, logged, and math-checked at the
time (two independent `last_render_age_ms` readings agreeing on a stable, non-recovering freeze
duration) — but it does mean **this is not a simple, reliably-reproducible logic defect in the
retry condition itself.** Candidate explanations, none confirmed: (a) some one-off state left over
from that specific session's unusually long precursor history (5.5h frozen prod instance, a
reflash, a real radio-browser 503 mid-session, the `_deferredInject` path) that a clean repro
wouldn't hit; (b) a genuine but rare timing race that today's ~7 total retry cycles across three
tests simply didn't happen to trigger. **Downgrading confidence accordingly** — this is now
"observed once, robust against every repro attempt so far," not "confirmed broken." If it recurs,
capture `_pendingAction`/`_lastAttemptMs`/`_autoSkipTried` via a debug build at the moment it's
noticed, before touching anything else — that's the instrumentation this investigation was missing
each time.

**Update (TASK-397 4-hour unattended soak, 2026-08-04, 05:20:40–09:20:55):** ran the purpose-built
`test_webradio_long_soak.py` v2 (see TASK-397 for its own build history) against the single real
target station (`SLAM! DANCE CLASSICS`, `http://stream.slam.nl/WEB15_MP3`), no Spotify present
(`cyd2usb_winamp_debug_noSpotify`), `wrAutoSkip` confirmed on throughout. **Result: 14401.9s
(4h00m02s) elapsed, 0 anomalies, `status=complete`.** `wrState` stayed `2` (PLAYING) for the entire
run — never entered an `ERROR_*` state, so the terminal-retry mechanism this soak exists to stress
was never actually invoked; heap stable 49–58k across 479 heartbeat samples (no drift); 71 real ICY
title changes tracked correctly; DUT-silence watchdog never tripped (max gap between raw serial
lines: 40s, well under its 90s threshold); zero `terminal retry`/`stream dead`/`connecttohost
failed`/`ERROR_` lines anywhere in the 1872-line raw log. Report:
`app/tools/rnd_logs/webradio_long_soak_20260804T052040.json`, raw log
`app/tools/rnd_logs/webradio_long_soak_20260804T052040_raw.log`. Also caught mid-run, on-device (not
a bug): the Winamp skin's play-time digits legitimately wrap at 6000s / 100min
(`webRadioApp.h:786`, `_snapPlaySec % 6000`, TASK-349's own documented design for streams that
outlive classic MM:SS range) — human saw the on-screen clock drop from ~90min to ~1min and flagged
it as a possible reset; confirmed from the raw log (zero reconnect events at that timestamp) and
source it was the intentional wrap, not a real reconnect.

**This is new evidence, not resolution.** A single clean 4-hour run where the target error states
were never entered doesn't confirm or rule out TASK-393's original observation — it mainly confirms
`stream.slam.nl` didn't happen to fail during this particular window, so the terminal-retry-recovery
question this soak was built to answer remains untested by this run. Consistent with the "observed
once, robust against every repro attempt so far" framing above, now with a fourth clean attempt
added to that list (three real-network repro attempts + this soak). If a real anomaly is ever
caught by this tool (or another `--hours` run against a flakier station), the report JSON's
`anomalies[]` array carries the full diagnostic snapshot at the moment it fires — that's what
would move this from "not reproduced" to "confirmed."

**Update (Spotify-present 4-hour soak, 2026-08-04, 11:40:13–15:40:14) — did not reproduce the
render-freeze, but found a large, separate, well-evidenced connect-reliability finding.** Added a
`--spotify-present` flag to `test_webradio_long_soak.py` (skips the `set bgPoll 0` disable, leaving
Spotify's background polling active as a concurrent TLS user — the one condition from the original
human sighting the noSpotify-build runs above don't cover). Flashed the regular
`cyd2usb_winamp_debug` build (Spotify enabled, TASK-243's Premium lapse means `bgPoll` is
continuous 403 retries rather than real playback polling — still real TLS churn either way). Ran
the identical single-station soak (`SLAM! DANCE CLASSICS`) on a build that also already had
TASK-392's connect-timeout fix (5000ms/7000ms) applied.

**Result: 14401.9s (4h00m02s) elapsed, 0 anomalies, `status=complete`.** `render_age` never
climbed in lockstep with `uptime` at any point — the render-freeze detector correctly never fired,
so **this run does not reproduce TASK-393's specific symptom**, same disposition as every prior
attempt (now a fifth). But the connect-outcome numbers are dramatic and unambiguous: **415 connect
failures vs. 13 successful plays over the full 4 hours (~97% failure rate)**, against the identical
code/station/URL that held **0 failures, 71 successful title updates, one continuous connection for
nearly the entire 4 hours** in the no-Spotify run directly above. Heap stable 44-117k (mostly 47-49k
observed live, no leak — `anomalies=0` would have caught sustained drift), silence watchdog never
tripped (max gap between raw serial lines: 24.7s). Report:
`app/tools/rnd_logs/webradio_long_soak_20260804T114000.json`, raw log
`app/tools/rnd_logs/webradio_long_soak_20260804T114000_raw.log`.

**Live investigation during the run, both leads chased and both disproven — recorded so a future
session doesn't repeat them:**
1. *SSL-edge-timeout theory (wrong):* every failure takes almost exactly **7.007s**, matching
   `WR_CONNECT_TIMEOUT_MS_SSL`, which looked at first like the device was being redirected to an
   HTTPS StreamTheWorld edge (`stream.slam.nl` genuinely does 302-redirect there — confirmed via a
   live host `curl`, real audio streamed fine externally). Disproven by the raw log itself: the
   `"Connect to new host"` and `"Request ... failed!"` lines both reference the exact same string,
   `http://stream.slam.nl/WEB15_MP3` — no `"redirect to new host"` line ever appears in a failing
   cycle. The failure happens at the very first hop, on the plain-HTTP URL, which per
   `Audio.cpp:476-477` means `m_f_ssl` should be `false` and the **5000ms** plain budget should
   apply — not 7000ms. The precise 7.007s timing (confirmed consistent from the run's start to its
   final failure just before completion) remains **unexplained** — flagged, not resolved.
2. *General router-DNS unhealthiness (not supported):* one cold `dig @<gateway> stream.slam.nl`
   took 10.02s, suggestively close to the unaccounted-for ~2s gap. Immediately re-tested: a fresh,
   never-queried hostname (`stream.radiocorp.nl`, the CNAME target) resolved in 0.01s, `www.google.com`
   resolved in 0.02-0.19s across three tries, and `stream.slam.nl` itself resolved in 0.10s on a
   second (genuinely TTL-expired, re-resolved) query. One isolated slow blip, not a sustained
   pattern — doesn't survive its own follow-up test, so not trusted as the explanation either.
3. **What is confirmed, from source, and stays useful regardless of which theory is right:**
   `framework-arduinoespressif32/libraries/WiFi/src/WiFiClient.cpp:302-309` —
   `WiFiClient::connect(host, port, timeout_ms)` calls `hostByName()` (DNS resolve) with **no
   timeout at all**; only the subsequent raw-IP `connect()` gets the requested budget. This sharpens
   (with actual source evidence, not a guess) the DNS caveat TASK-391 already flagged as unresolved
   — DNS-resolve time is additional and unbounded on top of `setConnectionTimeout()`'s budget, not
   counted against it. Still doesn't fully explain the precise 7.007s figure on its own.

**Bearing on TASK-392:** this build already had TASK-392's timeout fix (5000ms/7000ms) applied, and
the connect failure rate was still ~97% under Spotify-present conditions — raising the budget alone
clearly does not fix connect reliability when Spotify is concurrently active. TASK-392's own gate
(run without Spotify present, both before/after clean) and this result are not directly comparable
— different variable under test — but this is a strong signal that Spotify-concurrency is a bigger
lever on connect reliability than the timeout budget was, at least for this station tonight.

**Honest bottom line:** TASK-390's original concurrent-Spotify-TLS-contention hypothesis now has
real, dramatic, reproducible-tonight support at the *connect-reliability* level (100%→3% success
swing, same code/station/URL, only Spotify's presence differs) — but it still has **zero** support
at the *render-freeze* level (the actual symptom TASK-393 was filed for). These may be related
(repeated connect failure is a precondition for ever reaching a parked `ERROR_*` state) or may be
two separate WebRadio-reliability issues that happen to share a station. Don't conflate "WebRadio
struggles to connect when Spotify is present" (now well-evidenced) with "WebRadio's error-recovery
gets permanently stuck" (still unreproduced) when reporting this further up.

**Update (2026-08-04, later same day) — the Spotify-present run's own raw log already answered a
different, bigger, previously-open question, with zero new instrumentation required.** Re-reading
the existing `[W][perf] iter=...ms (worst path so far: app.tick:...)` lines already captured in
that soak's raw log: **every one of the run's 415 failed connect attempts blocked `loopTask` — the
main app-dispatch loop: touch, rendering, taskbar, every other app — for 7-9+ seconds.** 421
individual tick iterations exceeded 5000ms over the 4-hour run (`grep -oE "iter=[0-9]+ms"` on the
raw log, filtered >5000), roughly one every ~34s, matching the failure cadence almost exactly.
Successful connects are fast (29-332ms observed). Cross-checked against the clean no-Spotify run:
worst `app.tick` there was 79ms, zero iterations over 5000ms.

**Self-correction, same session, before this went further:** initially wrote this up as "failed
connects fall through to a generic `app.tick` bucket instead of the `wr.connect` perf label — a
secondary instrumentation gap." Checked the actual `_play()` call site
(`webRadioApp.h:1690-1694`) before repeating that claim in TASK-398, and it's wrong —
`perf::record("wr.connect", ...)` runs *unconditionally*, before the success/failure branch, so
failures ARE recorded under `wr.connect` (confirmed: 47 `wr.connect`-labelled worst-path lines in
this same raw log, including fast successful connects). `app.tick` shows as the reported "worst
path" during failures simply because `perf::worstPathName()` reports whichever named slot has the
largest value, and `app.tick` (the outer `tick()` span, containing the nested `wr.connect` call
plus everything else) is always ≥ `wr.connect` for the same iteration — not a gap, expected
behavior for a max-over-named-spans profiler. The 7-9s/421-freezes finding itself is unaffected;
only the "why app.tick and not wr.connect" secondary detail was wrong. See
`M-WR-AUDIO-TASK.md`'s OQ4 for the corrected version.

**This is not a new architectural discovery — it's the first real measurement of an already-known,
already-explicitly-deferred open question.** `docs/architecture/designs/M-WR-AUDIO-TASK.md` (the
design behind TASK-278's audio-pump-task offload, accepted 2026-07-03) documents this exact gap at
filing time: *"A third, adjacent latency source: `connecttohost()` blocks loopTask for up to
several seconds... Not this design's primary target, but the option space should not foreclose
fixing it."* Phase 1 (implemented, TASK-278) **deliberately left connect-blocking out of scope**
— TASK-278's own E1 exit-criteria explicitly excluded CONNECTING-state windows from its UI-latency
measurement. Phase 2 (async connect via a command-queue architecture, "real surgery on the
freshly validated ADR-045/TASK-276 machine," per the design doc) was proposed and explicitly
deferred, gated on OQ4 — *"measure (`perf::record("wr.connect")`) during Phase 1 to decide whether
Phase 2 is worth the state-machine surgery"* — which had only ever been sampled once, under
healthy conditions (`wr.connect:83ms`, excluded as an outlier in the 2026-07-07 E1 campaign).
**Tonight's 421-freezes-in-4-hours number is that measurement**, just arrived at from the failure
path instead of the success path OQ4 originally expected. OQ4 marked RESOLVED in the design doc
with this update; a caught-live self-correction is on record there too (an early read of the
`app.tick` worst-path values as "growing over time due to fragmentation" was wrong — same benign
~73ms/cycle phase-drift artifact as `render_age`'s drift, not real degradation; walked back before
being asserted as fact).

**Filed as TASK-398** to actually scope Phase 2 (or a narrower connect-specific mitigation) now
that the freeze magnitude is real data, not a deferred theoretical.

**Post-TASK-398 soak, 2026-08-05 (2h, Spotify-present, `--spotify-present` flag, SLAM! DANCE
CLASSICS, `cyd2usb_winamp_debug`) — sixth repro attempt overall, first since TASK-398 landed.**
Run via `test_webradio_long_soak.py` in the background while unrelated host-side implementation
work (TASK-400/401) proceeded in parallel. **Result: 0 anomalies, `status=complete`, 7200s
elapsed.** `render_age` never climbed in lockstep with `uptime` at any point (the render-freeze
detector correctly never fired) — same disposition as all five prior attempts, still unreproduced.
Raw-log counts (`grep` against the persisted log, not live reads): 213 `connecttohost failed` /
67 successful connects (~76% failure rate this run — lower than the pre-TASK-398 97% figure from
the 2026-08-04 run, but station/network conditions differ enough between sessions that this is not
a controlled before/after comparison, just a data point), and — the actually load-bearing number —
**232 `terminal retry — re-arming scan` firings, every single one followed by a fresh `play idx=`
attempt, zero permanent `ERROR_*` parks over the full 2 hours.** Heap stable (42-117k, no drift),
no crash/panic/reboot lines. This is meaningfully different from the pre-TASK-398 picture: the
device now visibly enters and recovers from the connect-fail/terminal-retry cycle roughly every
30s for two straight hours, under the same adverse Spotify-concurrent conditions that used to
produce 7-9s whole-device freezes, without ever wedging — consistent with TASK-398's async-connect
fix having removed the freeze mechanism even though it hasn't fixed (and was never intended to fix)
the underlying connect-reliability rate against this specific station under Spotify contention.
Does not confirm the original stale-title marquee-freeze symptom either way (TASK-390's own open
thread — no fresh evidence for or against this session). Reports:
`app/tools/rnd_logs/webradio_long_soak_20260805T114034.json` (+ `_raw.log`).

**Eighth repro attempt, 2026-08-05 22:46–00:50 (overnight, unattended).** First launch
(`..._20260805T224632_raw.log`, 9KB) aborted itself after 43s — booted into production firmware
(no `SERIAL_DEBUG` surface), every `get` poll returned `{"ok":false,"error":"unknown command"}`;
harness detected this and relaunched rather than logging a false-clean result. Second launch
(`..._20260805T225002`, `status=complete`, `elapsed_s=7200.1`, 0 anomalies) is the real run: boot
line shows `spotify=idle (playerMode=webradio) — refresh deferred to first toggle` — this run did
**not** have Spotify's background poll active (`--spotify-present` was not set), unlike the sixth
attempt above. 175 `wrState` polls, 66 `terminal retry — re-arming scan` firings (each followed by
a fresh `play idx=` attempt, same pattern as the sixth run), 28 `connecttohost failed` lines, 0
permanent `ERROR_*` parks, `render_age` never climbed in lockstep with `uptime`. Same disposition
as all seven prior attempts — still unreproduced. Reports:
`app/tools/rnd_logs/webradio_long_soak_20260805T225002.json` (+ `_raw.log`); the aborted false-start
kept alongside it as `..._20260805T224632_raw.log` (evidence the harness's abort-on-no-debug-surface
behavior works, not a separate finding).

**Update (2026-08-06, instrumentation gap closed, no new repro attempted):** every "if it recurs,
capture X" note above pointed at `_pendingAction`/`_lastAttemptMs`/`_autoSkipTried` — but
`_pendingAction` and `_autoSkipTried` were already exposed via the existing `get wrSkip` getter
(`pending`/`tried`/`retries`/`autoSkip` fields, `webRadioApp.h`) the whole time; every "dead end"
note in this task about needing a breakpoint or new instrumentation was really just this getter
going unchecked. The one genuinely missing piece was `_lastAttemptMs` itself — with no elapsed-time
field, a live catch couldn't tell whether the terminal-retry gate's `>= WR_TERMINAL_RETRY_MS` term
was the one holding it back from the other three ANDed conditions. Added `sinceAttemptMs`
(`millis() - _lastAttemptMs`) to `get wrSkip`'s JSON output — SERIAL_DEBUG-only, zero new static
storage (computed inline), `run/check` 6/6 clean. `test_webradio_long_soak.py` already snapshots
`get wrSkip` on every anomaly capture (line 322), so the next anomaly report picks this field up
for free with no tool changes. Net effect: the four gating conditions in `tick()`'s terminal-retry
check (`webRadioApp.h:863-874` — `autoSkip`, `pendingAction`, `state`, elapsed-vs-30s) are now all
readable in one `get wrState` + `get wrSkip` pair at the moment of a freeze, closing the gap this
task's repro attempts kept citing. Does not itself explain the original unreproduced freeze —
still 8/8 repro attempts clean, mechanism holds up under stress — this only removes the excuse for
the *next* live catch (spontaneous or soak-caught) coming back inconclusive again.

