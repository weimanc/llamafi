# M-ARCH — architecture work board (M-SRCLAYOUT · M-CODEQUAL · M-TOOLING · M-DOCLIFE)

> Owner: Project Manager · Split out of [tasks.md](tasks.md) on 2026-08-16.
>
> **Why this file exists.** A 2026-08-16 Architect pass produced nine design documents, two ADRs and
> three IFCs, reserving 35 task ids. Filing those inline would have taken `tasks.md` from ~1 200
> lines back past 2 500, undoing the archive sweep done the day before. Same treatment as the
> M-WINAMP-PLAYER board.
>
> **Read this first — the honest state.** Three refactor commits (`a044f5d`, `78caa95`, `b36f184`)
> **already landed** ahead of ADR sign-off. **As of 2026-08-16 they are reviewed and DUT-verified
> (TASK-488) and the owed ≥3-run baseline is taken (TASK-497) — nothing was reverted.** What that
> does *not* change: by ADR-060 D0's measure they created **zero components** — `main.cpp` went
> 5 880 → 1 726 lines, which is readability, not physical design. **TASK-453 and TASK-454 are filed
> as landed-and-verified, not as open work.**
>
> Closed entries go to [tasks-archive.md](tasks-archive.md).

> ## Row format (BP-069, 2026-08-25, human) — read before adding or closing any row
>
> **A row is a pointer, not a record.** It holds exactly: task id, priority, status, a one-line
> title/summary, a link to the governing design doc (only when the task is a genuine design or
> architectural decision — not for a mechanical or hygiene fix), and the landing commit hash(es).
> **It does not hold the verification narrative** — no diff summaries, no byte-deltas, no DUT logs,
> no judgment-call rationale pasted into the cell. That evidence already has two homes: the commit
> message (which should carry it in full — write the commit message as if the row won't), and, for
> tasks with a governing design doc, that doc's own as-built section (BP-065) — updated by the agent
> that lands the work, in the same commit, not as a follow-up.
>
> **Template:**
> ```
> | TASK-NNN | P2 | DONE 2026-08-25 (`abc1234`) | One-line summary of what shipped. |
> ```
> With a design doc behind it:
> ```
> | TASK-NNN | P2 | DONE 2026-08-25 (`abc1234`) | One-line summary — see the governing design doc's as-built section for the shape and detail. |
> ```
>
> **A real before/after**, TASK-472, this session: the original row was ~600 words of stock-split
> mechanics, back-reference/`friend` reasoning, a full levelization-audit account and a DUT
> verification narrative, all pasted into one table cell (still readable in full at
> [tasks-archive.md § TASK-472](tasks-archive.md#task-472-full-record-archived-2026-08-25-from-tasks-architecturemd)
> — none of that content was lost, it just isn't inline any more). It is now:
> `| **TASK-472** | P3 | **DONE 2026-08-22** — DUT-verified (`7669460`/TASK-529), levelization audit
> complete | Stage F — `stock/` → 3-component split; real gap surfaced and filed as TASK-530. [full
> record in tasks-archive.md](tasks-archive.md#task-472-full-record-archived-2026-08-25-from-tasks-architecturemd)
> |` — one line, everything still findable, nothing duplicated.
>
> **Do**: keep the row skimmable in one glance · link out for detail (design doc, commit, archive)
> · write the commit message as the actual record, not an afterthought.
> **Don't**: paste a diff summary, DUT log or byte-delta into the row · create a design doc for a
> one-line hygiene fix · retroactively rewrite an old verbose row (archive passes handle that,
> ordinarily — this convention is going-forward only, per BP-069).
>
> This applies to every board using this format — `tasks.md`, `tasks-architecture.md`,
> `tasks-winamp-player.md` — not just this file.

> ## ⚠ @PM verdict, 2026-08-16 — read before scheduling anything here
>
> **This board should lose to closing M-WINAMP-PLAYER, and the count is inflated.**
>
> **On the count:** 47 entries, but **~10–12 are actually actionable** without a design decision
> first. The rest are BLOCKED on the five-deep serial chain, SKELETON (research prompts with "no
> conclusions" by design), or gated on an unresolved question. *"47 tasks"* must not be quoted
> without that caveat.
>
> **On the altitude — the finding that matters:** M-WINAMP-PLAYER has 12 open entries and was
> **paused by the human over work quality**. Its PM note diagnoses three failure modes. **This board
> reproduces two of them, on a compressed timescale, in the same week**: nine design docs and 47
> tasks in one day; three commits landed ahead of ADR sign-off with no baseline (BP-062's
> "measurement without conditions", and D13 skipped outright); and a review chain that found errors
> in *every document it reviewed* — 8 of 9 confirmed, including an invariant false about its own
> example. **Higher volume, lower verification, same week, same shop.** Scheduling 47 new
> architecture tasks while 12 paused player tasks sit unresolved is the wrong order regardless of how
> good TASK-458/466/475/478 are individually.
>
> Escalated as **E-05**. The Architect does not overrule this.
>
> ### Human ruling, 2026-08-16: **M-ARCH is prioritised. PM's recommendation is overruled.**
>
> **This is CLOSED, not open.** PM's case is preserved below for the record, **not as a live
> objection** — do not reopen it. *(Clarified 2026-08-16 on PM's own request: a cold agent skimming
> "PM's case intact" could misread it as unresolved.)*
>
> Recorded rather than quietly applied, because PM's reasoning stands on its own and the next reader
> should see both. PM's case — that this board reproduces two of M-WINAMP-PLAYER's diagnosed failure
> modes while that paused milestone waits — is **not withdrawn and is not wrong**. The human has
> weighed it and chosen differently, which is theirs to do.
>
> What does **not** change under this ruling: **TASK-488 still gates the M-SRCLAYOUT chain** (three
> commits landed unreviewed and un-baselined; prioritising the programme does not un-land them)
> — *gate satisfied 2026-08-16: 488 and 497 both closed, chain unblocked* — and
> **BP-066 now applies to everything on this board** — no document here gates work or is cited as
> fact until independently reviewed. Prioritising the programme raises the value of both, not less.

**Priority key**: P1 blocking · P2 should-do · P3 nice-to-have · P4 watch

---

## ▶ EXECUTION SEQUENCE — start here

**Updated 2026-08-22** — the 2026-08-16 version of this table was stale (still listed TASK-478 and
the 455/456/471/472 decision as pending; both are long done). Corrected against `git log` and each
task's own row rather than carried forward. **Do these in order**; everything not listed stays
filed and unscheduled.

| # | Do | Why this position |
|---|---|---|
| ~~**1**~~ **DONE 2026-08-16** | ~~**TASK-488 + TASK-497 — one DUT block**~~ | Three refactor commits sit on master unreviewed with no baseline. Everything in M-SRCLAYOUT is gated on this, and **the cost of delay compounds**: each further commit on top widens the blame surface from one to four. Same hardware session covers both — 488's byte-identity/`.map` review and 497's retrospective ≥3-run baseline. |
| ~~**1a**~~ **DONE** | *(prerequisite, ~15 lines)* ~~**write TASK-488's pass criteria first**~~ | Its DUT procedure is currently one sentence — *"a pass over app switching, taskbar cycling, eject and Settings navigation"* — with no id, steps, iteration count or fail condition. Compare `T_AE_04`, which specifies ×10 and a 100 ms bound. **Running 488 without criteria is closing against a proxy (BP-061)**: nothing visibly breaks, it gets called verified. |
| ~~**2**~~ **DONE 2026-08-22** | ~~**Decide 455/456/471/472 on what 488 finds**~~ | **488 found nothing wrong — continuation, not rework.** TASK-471 (Stage E, every component conversion) and TASK-472 (Stage F, `stock/` split + levelization audit) both landed and are DUT-verified (**TASK-529**). `main.cpp` 1042 → 357 lines. TASK-530 (the audit's own follow-up — 5 apps that never moved into `apps/`) also done. See these four tasks' archived records ([tasks-archive.md](tasks-archive.md)) for the full account. |
| ~~**3**~~ **PHASES 1, 2, 4 DONE** — phase 3 advisory by choice, phase 5 optional | **TASK-475** — `run/check-docs` | Phase 1 shipped (`b0d0202`): C5 + C1-`delta` blocking. Phase 2 (`5e46d92`) and phase 4 (`579775c`) shipped 2026-08-25: C2 and C4 both blocking now, both re-verified at 0 immediately before promotion. Phase 3 (C3) is unblocked (ADR-061 D8 / TASK-467 landed) but its count — 58 occurrences across 10 unknown env names, mostly historical ADR references to renamed/retired `cyd2usb*` envs — is not near zero, so it was left advisory and reported rather than force-promoted. Phase 5 (C1-full) needs the 279-citation backlog cleared first; the spec itself says this "likely stays advisory permanently... on purpose." Full narrative — including two independent reviews (@Architect, @VE) that each found real defects in the phase-1 landing — is in [TASK-475's archived record](tasks-archive.md#task-475-full-record-archived-2026-08-25-from-tasks-architecturemd). |
| ~~**4**~~ **DONE** | ~~**TASK-478** — `tools/lib/dut.py`~~ | Landed (`989c1ea`). Unblocked 479/480, both still OPEN. |
| ~~**5**~~ **DONE 2026-08-22** | ~~**TASK-458** — RAII guards — **with TASK-495 as its first commit**~~ | Real bug class with a proven instance (TASK-222). Both landed as two commits: TASK-495 (`1df8b33`) then TASK-458 (`15d3c55`). See [TASK-458's archived record](tasks-archive.md#task-458-full-record-archived-2026-08-25-from-tasks-architecturemd) for the full account, including a live double-`tlsResume()` defect found and fixed as a side effect. |
| **6** | **M-WINAMP-PLAYER** | Still paused, 12 entries in `tasks-winamp-player.md`. @PM would put **TASK-424** (SD write panic, card-independent) ahead of most of this board if DUT time is scarce. |

**Already done, do not re-schedule:** TASK-466 (build gate, 3 → 11 envs), 467, 477, 491, 496, 488,
497 (all 2026-08-16) — plus **TASK-471, 472, 478, 529, 530, 495, 458, 459, 460, 508, 535** and
**TASK-475 phases 2 and 4** (2026-08-21/25, this session). **Next in sequence is #6, M-WINAMP-PLAYER
(still paused) or TASK-424 if DUT time is scarce.** TASK-475 phase 3 is left advisory by choice (C3's
58-occurrence count isn't near zero); phase 5 is intentionally advisory-forever per the check-docs
spec's own text. New follow-ups from the TASK-488 verification: 503–506 (503 already DONE, see its
own row). TASK-535 (live DUT check of TASK-460's four fetch paths) is **DONE 2026-08-25** — 3/4
clean, the fourth (T220/Crypto) A/B-confirmed as a pre-existing heap-headroom characteristic,
unrelated to the refactor.

**Not scheduled by design — PM triage, 2026-08-25** (corrects this line's own stale contents; full
detail on every id below is in each task's own row): the four skeletons (483–486) remain genuinely
open research, no Developer action. TASK-489, 490, 491 and 500 were listed here but are already
DONE/LANDED — removed from this line, left in their own rows for the record. Everything else in the
category is **READY to schedule, not blocked on a design question** — the design/ADR work each one
needs was already done when it was filed: TASK-461, 462, 463 (M-CODEQUAL remainder), TASK-465, 468
(ADR-061 tail — 469/470 remain correctly chain-blocked on 468), TASK-479, 480 (M-TOOLING — 480 still
owes its ≥3-run baseline first), TASK-492, 493 (handoff debt — both now more overdue than when
filed), TASK-494 (was blocked on TASK-471, which has since landed — see its own row), TASK-501, 502.
TASK-482 (M-TOOLING spike-retirement rule) has a stale blocker note — see its own row for the
correction needed before scheduling it either way.

---

## Owed before anything else proceeds

| task | pri | status | title |
|---|---|---|---|
| **TASK-488** | **P1** | **DONE 2026-08-16** — verified, nothing reverted | review `a044f5d` / `78caa95` / `b36f184` per M-SRCLAYOUT §7a, and take the owed DUT baseline |
| **TASK-529** | **P1** | **DONE 2026-08-22** — DUT baseline taken, clean | take the owed DUT baseline for TASK-471/472 (`2a2f83e`..`7669460`, 16 commits) — same discipline as TASK-488. **Correction: the original filing of this task wrongly stated "no DUT in this environment" — a DUT was connected on `/dev/ttyUSB0` the whole session; that was an unverified assumption baked into three subagent prompts, caught by the user, not a real environment limit.** Once corrected, the baseline was taken for real. `run/task488` (39 app switches, taskbar, 9 player-mode cycles, 7 Settings sections): **T_488_04-09 all PASS**. T_488_10 FAIL is a stale test-harness artifact (`_EXPECTED_CMDS` hardcoded from `b36f184~1`, months before `playerCycle`/`sdopendir`/`sdslots` existed — `missing=[]` proves nothing was dropped by this session's work). T_488_11 FAIL (heap decline over repeated sweeps) matches already-documented pre-existing drift (TASK-504/505), reproduced on pre-refactor firmware too — not a regression. Additional ad-hoc DUT check for TASK-472 specifically (`app/tools/lib/dut.py`, one-off scripts, real serial + real network fetches, not the `run/task488` harness which predates the Stock split): **List, Chart, and Heatmap all verified working end-to-end** — `quoteOkCount` advanced after a forced List fetch, `fetchOkCount` advanced after a real tap-drill into Chart (drove production touch dispatch, not just a debug shortcut), `heatmapCount` reached 20 after a forced Heatmap fetch — confirming the `StockChart`/`StockHeatmap` split's shared-state design (friend + back-reference into the one `StockAppState`) works under live conditions, not just in source review. Production firmware restored via `run/flash` on completion |

**TASK-488's full result table, pass criteria, and closed-gate note archived 2026-08-22** — see
[tasks-archive.md § TASK-488](tasks-archive.md#task-488-full-result--pass-criteria-archived-2026-08-22-from-tasks-architecturemd).
Summary: all three commits verified pure moves, nothing reverted; `T_488_01`–`10` PASS, `T_488_11`
(heap-stability threshold) FAILED as written but not attributable to the commits (byte-identical
binaries, A/B on hardware reproduced the same decline on pre-refactor firmware too) — redesign
filed as TASK-504, the pre-existing settling behaviour as TASK-505. The `T_488_*` ids themselves
are registered canonically in `docs/verification/test_plan.md`, not here.

---

## M-SRCLAYOUT — decompose main.cpp ([design](../architecture/designs/M-SRCLAYOUT-main-decomposition.md) · [ADR-060](../architecture/decisions/ADR-060.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-453 | — | **LANDED, VERIFIED 2026-08-16** (`78caa95`) | Stage A — 7 app classes → `apps/*.h`. [full record in tasks-archive.md](tasks-archive.md#task-453-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-454 | — | **LANDED, VERIFIED 2026-08-16** (`b36f184`) | Stage B — SERIAL_DEBUG console → `debug/serialConsole/*.h`. [full record in tasks-archive.md](tasks-archive.md#task-454-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-455 | — | **LANDED** (`8cb5578`) — pure move, symbol identity | Stage C — `setup()` (621 lines) → `boot/boot.h`, verbatim (D1a). [full record in tasks-archive.md](tasks-archive.md#task-455-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-456 | — | **LANDED, DUT-VERIFIED** (`825da41`, `63aad48`, `ca74819`) | Stage D — `shell/appTable.h` composition root + `ShellState` (D2/D3/D4). [full record in tasks-archive.md](tasks-archive.md#task-456-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| **TASK-471** | P3 | **DONE 2026-08-22** — 28 commits (`2a2f83e`..`0bcd0c2`), DUT baseline clean (TASK-529) | Stage E — component conversion; every entry in the design doc's D1 target tree landed, `main.cpp` 1042 → 357 lines. [full record in tasks-archive.md](tasks-archive.md#task-471-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| **TASK-472** | P3 | **DONE 2026-08-22** — DUT-verified (`7669460`/TASK-529), levelization audit complete | Stage F — `stock/` → 3-component split; real gap surfaced and filed as TASK-530. [full record in tasks-archive.md](tasks-archive.md#task-472-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| **TASK-530** | P4 | **DONE 2026-08-22** (`fc8b713`) | Moved the 5 remaining apps into `apps/` per D1's target tree; all 13 apps now correctly placed. [full record in tasks-archive.md](tasks-archive.md#task-530-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-457 | P3 | OPEN | hygiene — `appRegistry.h` double-include comment, `currentAppId`/`g_previousAppId` unify |
| TASK-464 | — | **LANDED** (`f8bae91`) | Documentation-reference sweep — 331 `main.cpp:NNN` cites across 57 files converted to symbol references; TASK-503 folded in. [full record in tasks-archive.md](tasks-archive.md#task-464-full-record-archived-2026-08-25-from-tasks-architecturemd) |

## M-CODEQUAL — duplication and abstraction ([design](../architecture/designs/M-CODEQUAL-duplication-and-abstraction.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-458 | **P2** | **DONE 2026-08-22** (`15d3c55`, after TASK-495's `1df8b33`) | C2 — `TlsYieldGuard` RAII guard for the 8 `tlsYield()`/`tlsResume()`-pair fetches; found + fixed a live double-`tlsResume()` defect in `fetchTeletext()` as a side effect. `HttpSession` half deferred, filed as TASK-512. [full record in tasks-archive.md](tasks-archive.md#task-458-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-459 | P3 | **DONE 2026-08-25** (`5225208`) | C2b — migrated `s_aeSpotifyYielded` to a transferable `TlsYieldGuard`; DUT-confirmed the code path is unrelated to `T_AE_04`'s pre-existing failure (filed as TASK-533). [full record in tasks-archive.md](tasks-archive.md#task-459-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-533 | P3 | OPEN — new, filed 2026-08-25 | `run/ae04` (`T_AE_04`) currently fails 0/5 clean on unmodified `master` (confirmed via `git stash` A/B during TASK-459) — "pump gone but no `wrpump: torn down (...)` line" every cycle. Pre-existing, not caused by TASK-459 (that migration's code is never on `T_AE_04`'s call path — see TASK-459's row). Needs its own DUT investigation: either the dead-IP raw-TCP timeout (`10.255.255.1:1`) is now resolving/failing differently on this network (ICMP unreachable instead of a silent blackhole, changing which teardown branch fires) or there's a real regression somewhere between whenever `T_AE_04` last passed and now — not diagnosed here, out of scope for TASK-459. |
| TASK-460 | P2 | **DONE 2026-08-25** (`98c56da`) | C1 — consolidated the four buffered fetches (Weather/Crypto/Teletext/Geocode) onto one `httpFetchJsonBuffered()` skeleton in `dataTaskStorage.cpp`; the streaming five and `fetchWebRadioStations` stay out of scope. DUT check blocked this session by a rig-wide WiFi outage, A/B-confirmed unrelated; taken separately as TASK-535. [full record in tasks-archive.md](tasks-archive.md#task-460-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-535 | P3 | **DONE 2026-08-25** | Live DUT check of TASK-460's four converted fetch paths. Weather/Teletext/Geocode and the per-tag `-120` cert-break sentinel all PASS; T220 (Crypto) FAILs but is A/B-confirmed as a pre-existing heap-headroom characteristic of this device/session, not a regression. [full record in tasks-archive.md](tasks-archive.md#task-535-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-512 | P3 | OPEN — new, filed 2026-08-22 | C2 remainder — `HttpSession` RAII guard for `http.begin()`/`http.end()` in `dataTaskStorage.cpp`. Deliberately deferred out of TASK-458 (see its archived row): the pairing is already correctly balanced on every exit path today, so this is a DRY/consistency win, not a bug fix — lower urgency and higher control-flow risk (streaming parse, mirror-loop retries in `fetchOneMirror`/`fetchStockChartOnce`) than the TlsYieldGuard half was. |
| TASK-461 | P2 | **DONE 2026-08-25** (`f05de7e`) | C5 — one canonical source per canvas/screen dimension: `gen/shell_layout.h` now emits `SCREEN_W`/`SCREEN_H`/`APP_CANVAS_W`/`APP_CANVAS_H`, four named duplicates aliased to it, host tooling updated to parse rather than hand-type. [full record in tasks-archive.md](tasks-archive.md#task-461-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-462 | P3 | **UNBLOCKED** (454 verified) | C3 — table-driven `cmdGet`/`cmdSet` (1 308 lines → a table). **Investigation note (no status change):** the per-app `dbgGet()` delegation chain in `app/src/debug/serialConsole/cmdGet.cpp`/`cmdSet.cpp` is interleaved within the strcmp dispatch sequence, not cleanly separable before or after it — a naive single-table extraction per M-CODEQUAL's C3 design would silently change dispatch priority for any future key-name collision. Worth recording before this is picked up again, since ~128 DUT tests depend on this debug surface. |
| TASK-463 | P3 | **DONE 2026-08-25** (`bddbbc0`) | C4 debug-code convention — found ADR-061 D1–D5 already ratifies the identical convention (see TASK-465); proposed to QM as `LL-144`, awaiting human sign-off. C6 shared UI palette — `app/src/ui/palette.h`, two genuinely-shared colours aliased from 9 named duplicates. [full record in tasks-archive.md](tasks-archive.md#task-463-full-record-archived-2026-08-25-from-tasks-architecturemd) |

## ADR-061 — build-variant hygiene ([ADR](../architecture/decisions/ADR-061.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-465 | P3 | **DONE 2026-08-25** (`bddbbc0`, alongside TASK-463) | Read ADR-061 D1–D5 and found it's the same convention as M-CODEQUAL's C4 (see TASK-463); one shared `LL-144` retrospective entry filed for both, not two. [full record in tasks-archive.md](tasks-archive.md#task-465-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-466 | — | **LANDED** (`dff3263`) | D6+D7 — full-matrix build gate (66 s measured) + three name-consistency checks. [full record in tasks-archive.md](tasks-archive.md#task-466-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-467 | — | **LANDED** (`0b1d13e`) | D8 — decommission: `cyd2usb`→base, `matrixDisplay.h`, `SPIKE_MODE`, ceefax leftovers, 10 libdeps orphans, doc corrections. [full record in tasks-archive.md](tasks-archive.md#task-467-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-468 | P2 | **DONE 2026-08-25** (`02df058` stage 1, `ae2702a` stage 2) | D9 step 1 — `display/tft.{h,cpp}` component, rehomes the ~797-call-site `tft` global; RAM/flash delta negligible. Unblocks TASK-469/470. [full record in tasks-archive.md](tasks-archive.md#task-468-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-469 | P3 | **DONE 2026-08-25** (`e1307d9` flatten, `e7a8970` row update) | D9 step 3 — flattened `WinampDisplay` onto `SpotifyDisplay`, converted `winampDisplay.h` to a real `.h`/`.cpp` component; RAM -40 B, flash -9608 B. DUT-verified clean boot. Unblocks TASK-470. [full record in tasks-archive.md](tasks-archive.md#task-469-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-470 | P3 | **DONE 2026-08-25** (`411ba20`) | D9 step 4 — deleted `cheapYellowLCD.h`/`.cpp`, folded `[cyd2usb_base]` into `[env:cyd2usb_winamp]`. ADR-061 D9's full prerequisite chain (steps 1, 3, 4) now closed. [full record in tasks-archive.md](tasks-archive.md#task-470-full-record-archived-2026-08-25-from-tasks-architecturemd) |

## M-CONCURRENCY / IFC ([design](../architecture/designs/M-CONCURRENCY-task-ownership-contract.md) · [IFC-002](../architecture/interfaces/IFC-002.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-473 | P2 | OPEN | close the contract's gaps — G1 WiFi radio arbiter (three bugs: X014, TASK-436, TASK-404), G2 assert I2/I3, G3 dual mirrors |

## M-DOCLIFE — document decay ([design](../architecture/designs/M-DOCLIFE-keeping-design-docs-alive.md) · [spec](../architecture/designs/M-DOCLIFE-check-docs-spec.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-475 | **P2** | **PHASES 1/2/4 DONE** (`b0d0202`, `5e46d92`, `579775c`) — functionally settled | `run/check-docs`: C5, C1-`delta`, C2, C4 all blocking. Phase 3 (C3, 58 historical build-env citations) deliberately left advisory pending a PM/Architect call. Phase 5 (C1-full) intentionally advisory-forever per the spec's own text. [full record in tasks-archive.md](tasks-archive.md#task-475-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-508 | P2 | **DONE 2026-08-25** (`6361ef3`) | C4 status-vocabulary rulings (2026-08-23) + 189-header migration to the closed vocabulary/as-built structure. Re-measured C4: 0 non-conforming of 189. 14 files with no `Status:` field at all filed as TASK-534. [full record in tasks-archive.md](tasks-archive.md#task-508-full-record-archived-2026-08-25-from-tasks-architecturemd) |
| TASK-534 | P3 | OPEN — new, filed 2026-08-25 | 14 architecture docs in C4's scope have no `Status:` field at all (list in [TASK-508's archived record](tasks-archive.md#task-508-full-record-archived-2026-08-25-from-tasks-architecturemd)) — not a C4 vocabulary failure (C4 checks the word, not presence) but a real gap BP-065 implies these docs shouldn't have. Needs an Architect/PM call on whether presence becomes a new rule (its own C4b, or folded into C4) before anyone adds headers to these 14 by hand. |
| TASK-474 | P3 | OPEN | PM/QM process items — `docs-touched:` in exit criteria, closed status vocabulary, reservations land immediately |

## M-TOOLING — host tool architecture ([design](../architecture/designs/M-TOOLING-host-tool-architecture.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-478 | — | **LANDED** (`989c1ea`) | `tools/lib/dut.py` — one DUT session helper, delegating to `run/port`. Re-scoped in landing: `Dut` already existed with 16 importers, so this was an extraction + `resolve_port()` + one timeout policy, not a build |
| TASK-479 | P3 | **PARTIAL DONE 2026-08-25** (`b5d837c`) — port-resolution half done; send/expect-loop half deliberately deferred, see below | migrate 33 port-resolution copies + 29 send/expect loops onto it. Re-measured before starting: the port-resolution half had already drifted down from 33, since several `ve_suite_base.py`-based suites picked up `resolve_port()` as their shared parser's default in earlier sessions. **Migrated 15 files' port resolution onto `lib.dut.resolve_port()`**: `prloc_editor_smoke.py`/`prloc_manual_smoke.py`/`prloc_smoke.py`/`prloc_ve_smoke.py`/`settings_kit_smoke.py` (hand-rolled positional-arg `sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSBN"`), `run_sync_tests.py`/`sd_put.py`/`wifi_poll.py`/`wifi_watch.py` (hardcoded argparse/module default), `test_ae04_teardown.py`/`test_fbrowser_player.py`/`test_playorder_player.py` (`required=True` → a real default — additive only, all three are always invoked with an explicit `--port` by their wrapping `run/` scripts), `clock_tap_smoke.py` (replaced `screendump.py`'s `autodetect_port()`, an independent duplicate of the same `run/port`-shelling logic, with `resolve_port()` directly). Also migrated 3 files off the legacy `from run_serialdbg_tests import Dut` re-export path onto `from lib.dut import Dut` directly (`test_fetch_stress.py`, `test_tls_yield_reliability.py`, `wifi_watch.py`) — `dut.py`'s own docstring asks for this "a few at a time," same class, just the import source. **Send/expect-loop consolidation (the other 29) deliberately NOT attempted this session** — each of these scripts' send/expect logic (custom `Dut`-shaped classes in `clock_tap_smoke.py`/`sd_put.py`, or bespoke JSON pairing in the `prloc_*` scripts) has its own protocol nuances (timeouts, retry/backoff, destructive-scope guards); collapsing them onto the shared `Dut` class is a genuine per-file behavioral rewrite, not a mechanical port-default swap, and several of the scripts are explicitly documented as destructive to live device state (`prloc_editor_smoke.py`'s own docstring) — not something to verify by just running it. Flagging as real remaining scope rather than closing the row as fully done. Also left alone: `test_heatmap_reliability.py`/`pr_fetch_soak_report.py`/`test_planeradar_soak.py` (still import `Dut` alongside suite-only helpers — `_switch_to`, `_switch_to_stock`, etc. — that live only in `run_serialdbg_tests.py`, not yet in `lib.dut`; splitting one import statement across two source-of-truth modules ahead of TASK-480's split buys nothing) and the 6 `app/tools/spike/task<NNN>_*.py` scripts already flagged retirement-due by TASK-482 (migrating tools about to be deleted is wasted work). **Verified**: every migrated file `py_compile`s; every argparse-based one runs `--help` cleanly with no DUT attached, proving `resolve_port()`'s graceful degrade-to-fallback works standalone; one module-level script (`prloc_smoke.py`) was run far enough to confirm it resolved the real DUT port correctly before hitting an expected serial-contention error (the tmux monitor already held the port) — not run to completion, given its destructive-scope warning. `run/check` 11/11 (host-tooling only, no firmware touched). |
| TASK-480 | P2 | **BASELINE 1/3 TAKEN 2026-08-25, split NOT started — see note** | split `run_serialdbg_tests.py` (10 229 lines, 128 tests) into `suite/serialdbg/`, mirroring the VE taxonomy. **≥3 baseline runs owed first.** Sized the precondition before committing to the rest of the task: `run/test`'s own header comment warns failures can surface "30+ minutes in," and the suite is 128 tests against live Spotify + live network. **Baseline run 1/3 taken**: `./run/test` on unmodified `master`, **41m 31s wall clock**, **143 passed / 16 failed / 51 skipped / 0 declared-flake**. Log: `/tmp/serialdbg_baseline_run1.log` (workspace-only, not committed). Of the 16 failures, at least 6 are explicit `DUT WiFi not connected within 100s` exceptions or the `TimeoutError: no JSON response` that follows from the same cause (`T_PLR_26`, `T_PR_04`, `T_PRM_01`, `T_PRM_02`, plus WebRadio state timeouts `T_WR_COEX_01`/`T_WR_VOL_03` that read as a stalled/disconnected link, not app logic) — **confirmed live, not inferred**: immediately after the run, `tmux capture-pane` on the production monitor showed the DUT mid-boot cycling both saved SSIDs (`<home-ssid>`, `<home-ssid>`) with `NO_AP_FOUND` on every attempt, in real time, no test running — the same rig-wide WiFi outage already independently documented this session in TASK-460/533/535's rows (there, resolved only by a human physically moving the DUT closer to the AP). **Stopping here rather than taking runs 2/3 now**: (1) cost — 3 runs alone is ~2 hours of DUT-blocking wall time at this measured rate, before the actual 10 005-line/128-test-body split and its own required post-split parity run; (2) validity — running 2 more baseline passes into an actively ongoing rig-wide WiFi outage would bake environmental noise into the "flaky set" declaration ADR-059 D13 requires, rather than a clean signal of which tests are flaky on their own. Recommend re-attempting the remaining 2 baseline runs once the WiFi rig is confirmed stable (repeat the TASK-460-style A/B: re-run after the outage clears and compare), then proceeding to the actual split as its own dedicated pass — this task's split itself was not started, no `suite/serialdbg/` files exist yet. Production firmware confirmed restored to the DUT (`run/test`'s own trap cleanup did this; independently verified via `tmux capture-pane`). |
| TASK-481 | P3 | BLOCKED on 480 | directory + naming taxonomy; pair with TASK-464 (breaks doc paths) |
| TASK-482 | P3 | **DONE 2026-08-25** (`76c608e`) | Added the spike-retirement check to `check_docs.py` per M-TOOLING §4 rule 3: any `app/tools/**/task<NNN>_*` (glob covers both flat `app/tools/` today and `app/tools/spike/` once TASK-481's directory move lands, without needing to know which) whose leading `TASK-NNN` appears in `tasks-archive.md` is flagged. Named it `SPIKE` rather than folding it into the `C1`–`C6` numbering — it's a separate mechanism from the M-DOCLIFE decay-mode taxonomy those implement (a naming/archival fact about `app/tools/`, not a doc citation), and the design doc itself never ties the two together (this row's own PM correction). Only the *leading* embedded number is checked (`task399_402_dut_verify.py` → `TASK-399` only), matching the doc's "named for its task" (singular) and its own "five-line grep" simplicity bar. **Confirmed today's 6 spikes fail as expected** — the design doc's own stated "correct first result": `task398_connect_async_verify.py`, `task399_402_dut_verify.py`, `task400_401_dut_verify.py`, `task402_posbar_trace.py`, `task405_slew_verify.py`, `task432_alloc_guard_gate.py`, all 6 leading numbers confirmed present in `tasks-archive.md` before writing the check, not assumed. **Advisory on landing** (judgment call, per the coordinator's steer to use the established pattern): C5/C1-`delta`/C2/C4 all landed blocking specifically because they read **0** on landing day — the precondition M-TOOLING's own text rules out here ("today's six spikes all fail... immediately"). Landing this blocking would red out `run/check` on day one purely from the expected backlog, not a real find; same reasoning `check_docs.py`'s own C3 comment already uses ("promoting it is a scope call for a human, not a mechanical one"). Added `T_DOC_15` (`test_check_docs.py`) — positive control (an open task's spike, not flagged), the leading-number-only proof, and the non-spike-filename exclusion (`helpers.py`) — plus its `test_plan.md` row (C6 flagged the new executable id with no doc row on the first `run/check`; fixed before re-running, not left red). Regenerated `testdata/check_docs/golden.txt` deliberately (one new advisory line, `0 retirement-due of 0` against the fixture's empty `app/tools/`) per `T_DOC_03`'s own instruction to do so rather than let it drift. Verified: `run/check` 11/11, `test_check_docs.py` 15/15. Host-tooling only — no firmware touched, no DUT verification needed. |
| TASK-536 | P3 | **DONE 2026-08-26** (`dea7ab3`) | `ROWLEN` advisory row-length check, per [M-ROWGATE-task-board-length-check.md](../architecture/designs/M-ROWGATE-task-board-length-check.md) — see its As-built (§7) for the measured threshold and count. |
| TASK-537 | **P2** | OPEN — filed 2026-08-26, **blocks TASK-481** | Add a `gate/` level to the §3 taxonomy: 34 of 103 tools (incl. all four `check_*.py` gates) have no home in it — see [M-TOOLING](../architecture/designs/M-TOOLING-host-tool-architecture.md) §3 R5 + §8. |
| TASK-538 | P3 | OPEN — filed 2026-08-26 | Clear the 6 archived spikes, then flip `check_docs.py`'s SPIKE check to blocking in the same commit — see [M-TOOLING](../architecture/designs/M-TOOLING-host-tool-architecture.md) §4 R6. |
| TASK-539 | P3 | **DONE 2026-08-26** (`45f8961`) | Documented the 15 `run/` scripts M-TOOLING F5/R9 found missing from `CLAUDE.md`'s run-script list (re-verified against `ls run/` before adding, count and members matched R9 exactly). |

## Vendoring / `app/lib` ([ADR-060 D2b](../architecture/decisions/ADR-060.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-476 | P3 | OPEN | relocate `mb_arena` → `app/src/mem/arena`. **Blocked on an unanswered question**: can a PlatformIO `lib/` dir include from `src/`? Answer that first |
| TASK-477 | — | **LANDED** (`f2730cc`) | fix `mb_arena.h`'s header comment — it claims production is "byte-clean"; `platformio.ini:93` defines `MEMBUDGET_PHASE1` in `[env:cyd2usb_winamp]` |

## Skeletons — problems with a home, not yet designed

Each has a **SKELETON** banner: a starting point, no conclusions, expect to restructure rather than
fill in.

| task | pri | status | title |
|---|---|---|---|
| TASK-483 | P3 | SKELETON | [M-TESTARCH](../architecture/designs/M-TESTARCH-test-architecture.md) — test architecture. **VE owns OQ1**: a host unit tier may not be worth it here |
| TASK-484 | P3 | SKELETON | [M-ERRMODEL](../architecture/designs/M-ERRMODEL-error-model.md) — four overlapping error conventions; IFC-001 already ships the `errorCode==0` ambiguity |
| TASK-485 | P2 | SKELETON | [M-LEVELS](../architecture/designs/M-LEVELS-dependency-audit.md) — audit D2a's asserted levels. **No include graph has ever been generated**; the audit may contradict D2a |
| TASK-486 | P3 | SKELETON | [M-VENDORING](../architecture/designs/M-VENDORING-upstream-policy.md) — five vendored trees, five conventions, no upstream refs recorded |
| ~~TASK-487~~ | — | **FOLDED into TASK-493** | @PM: a five-minute re-read, not a milestone thread. Carry it as a checklist line on the `architecture.md` sync, not a standalone task id. The doc stays. |

## Handoff debt — reservations the Architect owed and did not perform

These are the failure AGENTS.md rule 10 was written to prevent, reproduced by the pass that cited
the rule. Filed 2026-08-16 after a second sweep for uncaptured items.

| task | pri | status | title |
|---|---|---|---|
| TASK-489 | P2 | **DONE 2026-08-16** | reserve X065 in `cross_feature_matrix.yaml` — Developer completes |
| TASK-490 | P2 | **DONE 2026-08-16** | reserve `T_CC_`/`T_SRC_`/`T_CQ_` families in `test_plan.md` — VE completes |
| TASK-491 | — | **LANDED** (`e2f70db`) | correct X015 — it claims `dataTask` runs on Core 0; it pins to `APP_CPU_NUM` |
| TASK-492 | P3 | **DONE 2026-08-25** (`04b3f1c`) | Retired the DUPLICATE `D_VOLUME_DRAG` state-machine IMPLEMENTATION, not the `handleVolumeGesturePublic()` symbol itself — **judgment call, checked against current source before touching anything, reported here rather than made silently.** The machine was implemented **twice**: inline in `handleWinampInput()` (Spotify's real-touch path, 3 sites — Press hit-test capture, Move continuation, Release commit) and again, nearly identically, in `handleVolumeGesturePublic()` (WebRadio's narrow capture entry, TASK-352). That duplication had already cost one bug (TASK-406: a missing `LOG_D` line in the WebRadio copy) and this session found a **second, previously-undiscovered divergence** in the same class: the Release path's drag-end diagnostics (`Serial.printf("[D][chrome] drag-end commit ...")` + `_lastInputWasAsync = true`) existed in `handleWinampInput()`'s copy and were silently absent from `handleVolumeGesturePublic()`'s. (`_lastInputWasAsync` has zero readers anywhere in the tree — confirmed by grep before relying on this — so setting it uniformly is a no-op either way, not a behaviour change; the log line is a real, if minor, added diagnostic for WebRadio's path.) Extracted the one state machine into three private helpers (`_volumeDragCapture`/`_volumeDragContinue`/`_volumeDragRelease`) that both `handleWinampInput()` and `handleVolumeGesturePublic()` now call — a future edit to one can no longer silently diverge from the other, closing the actual defect class OQ2/TASK-406 both point at. **Did NOT route WebRadio through the full `handleWinampInput()`** (the more literal reading of OQ2's "`handleWinampInput()` is Spotify-hardcoded, which the capability mask fixes," and the reading `handleVolumeGesturePublic()`'s retirement most obviously suggests) — checked `webRadioApp.cpp`'s `handleInput()` first and found it has its **own, separately maintained dispatch** for transport/PLEDIT/eject/vis (`hitTestTransportPublic`/`pleditPress`/`pleditDragging`/`pleditMove`/`pleditRelease`/`hitTestEject`), built exactly so WebRadio never reaches `handleWinampInput()`'s own `_plView.dragging()`/`D_POSBAR_DRAG` internals even now that `CAP_SEEK` is off for its mask. Routing WebRadio's volume touches through the full dispatch would reintroduce that exact hazard (the same `_plView` instance reachable via two independent paths, double-dispatch risk) for zero benefit over sharing just the volume sub-machine — so the public entry point stays, its duplicate body doesn't. **Verified**: `run/check` 11/11 across all 6 envs. **DUT** (WiFi down on this rig again, pre-existing RF issue, unrelated — worked around it since volume-drag doesn't need network): a 61-step drag on the volume slider (`drag 110 63 170 63 61`, mirroring TASK-406's own verification shape exactly) against **both** WebRadio and Spotify produced the identical result each time — `2` `enqueued ACT_VOLUME` lines (matches TASK-406's own recorded baseline exactly) and the drag-end commit log line now present for **both** (previously WebRadio-absent, confirming the fix); a follow-up tap after release hit-tested `VOLUME` cleanly on Spotify, confirming `dragState` returned to `D_IDLE`, not stuck. `get dataq` before/after unchanged (no cross-subsystem state corruption). Production firmware restored. |
| TASK-493 | P2 | **DONE 2026-08-25** | `docs/architecture/architecture.md`'s Component Architecture diagram (the one box, `:49`) said `loop() — app shell (appShell.h)` as if `loop()` itself lived in `appShell.h` — stale since TASK-471's Stage E split. **Verified against current source before editing**: `loop()` is in `app/src/main.cpp` (357 lines, confirmed by `wc -l`); the per-app dispatch it calls out to (`switchApp`/`appTick`/`appHandleInput`) is in `app/src/appShell.cpp` (314 lines) with `appShell.h` now just the 45-line declaration header; `handleSerialCommands()`/`drainInjectionQueue()` moved to `app/src/debug/serialConsole/console.cpp`; `setup()` moved to `app/src/boot/boot.cpp` (off the `loop()` path entirely, so didn't belong in this box to begin with). Corrected the box to `loop() (main.cpp, 357 lines) -> appShell.cpp dispatch`, named the split-out console/boot files explicitly, and left the rest of the diagram (dataTask/spotifyTask boxes, the per-app row) untouched — those were already accurate. Rest of the doc checked for the same staleness (`main.cpp`/`appShell`/`loop()`/line-count references) — nothing else found; the `App` ABC citation at `:93` (`appShell.h`) is still correct, that interface declaration didn't move. Verified: `run/check --docs-only` clean (C5 + C1-delta + C2 + C4 + C6), no new C1/C3 findings. |
| TASK-494 | P3 | **DONE 2026-08-25** | Renamed `feature_inventory.yaml`'s `files:` key to `components:` on all 82 feature entries (`sed`, including the 3 empty-list `files: []` entries a bare-key pattern missed on the first pass — re-checked with `grep -c` before/after, 0 `files:` remaining, 82 `components:` present). Confirmed no tooling reads this file programmatically (`grep -rn feature_inventory --include=*.py .` — empty; it's Developer-maintained data, per its own header, not machine-parsed) so a pure key rename carries no script-breakage risk. Also fixed the two places that named the old key rather than just the filename: a stale `files` mention inside one entry's own prose notes (`:2162`, the `M-DISPLAY-DELTA-COMMON` reservation note) and, more importantly, the canonical schema template in `docs/agents/developer.md` (`:28`) that every future entry gets copied from — left that unfixed and the rename would have silently reverted on the next feature addition. Did not remap the VALUES (the actual file-path lists) to component names — TASK-494's own filing text is the key rename only ("`files:` → `components:`"), and the values already are components in the Lakos D0 sense used by M-SRCLAYOUT (a component's `.h`/`.cpp` pair *is* a pair of file paths, so the existing lists needed no semantic translation, just the label). Verified: `python3 -c "import yaml; ..."` parses cleanly, 82 features, `components` present on every entry's key set. `run/check --docs-only` clean, no new C1/C3 findings. |

**TASK-489 / TASK-490 — reservations performed.** M-SRCLAYOUT's header claimed *"registers as
X065"*; the matrix contained no such row. M-CONCURRENCY mined 24 matrix entries and registered none
back. ~19 test ids (`T_CC_01–05`, `T_SRC_01–08`, `T_CQ_01–06`) existed only inside design docs, with
`test_plan.md` — which VE owns — untouched. Both now carry **reservations**, explicitly marked
incomplete: Developer corrects and completes the matrix row, VE writes the test entries and may
rename or discard any of them. The Architect reserves; it does not fill in other roles' files.

**TASK-491 — X015 is factually wrong.** It states *"dataTask fetch functions … run on Core 0"*.
`dataTaskStorage.cpp:117` pins to `APP_CPU_NUM` (core 1), and `git log -S'PRO_CPU_NUM'` shows it
never did otherwise. The entry's *conclusion* (spinlock-published results) is correct; its stated
reason is not. Matters because IFC-002 §1.1 turns on all four contexts sharing one core — a reader
who believes X015 will reason about SMP races that cannot occur. Developer owns the file.

**TASK-492 — `handleVolumeGesturePublic()`.** M-AUDIO-ENGINE OQ2 had two halves. The first — the
Spotify-hardcoded `handleWinampInput()` — **is fixed**: ADR-059 D7's capability mask landed and
`winampDisplay.h:593-597` gates every zone on `_playerCaps`. The second is the workaround that
hardcoding forced: `handleVolumeGesturePublic()` at `winampDisplay.h:696`, still called from
`webRadioApp.h:821`. OQ2 is explicit that it must be retired **in its own commit, never as a side
effect** — it shares the `D_VOLUME_DRAG` state machine (TASK-352), and WebRadio's volume-drag path
already cost TASK-406 a missing-log-line bug.

**TASK-493 — `architecture.md` sync.** AGENTS.md rule 8 makes this the Architect's job. Line 49 still
draws `loop() — app shell (appShell.h)`, which the three landed commits and ADR-060 D0/D1 both
contradict. **Do it after TASK-488**, not before: the living spec should reflect *validated*
implementation, and none of it is validated yet.

**TASK-494 — the inventory join key.** `feature_inventory.files:` is the only mapping between the
functional decomposition (81 features) and the physical one (~28 components). It broke the moment
Stages A/B landed. Pointing it at components instead of files makes it survive moves — and makes
"31 of 81 features list `main.cpp`" into a metric rather than noise. Blocked until components exist
(TASK-471).

---

---

## From the @Developer review, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| **TASK-495** | P3 | **DONE 2026-08-22** (`1df8b33`) | `fetchCrypto` moves its `tlsResume()` to after its JSON parse, matching `fetchWeather`. Decision made (E-02, resume-AFTER); landed as TASK-458's first commit, exactly as the ordering note below required. |
| TASK-496 | — | **LANDED** (`33b3003`) | `appRegistry.h` has no conditional-compilation column; 3 of 13 apps are `#ifdef WINAMP_DISPLAY` |

> ### ⚠ PARKED 2026-08-16 — read this before starting TASK-458 or TASK-460
>
> **The decision is made; the code change is not.** Parking is safe *on its own* — the divergence has
> existed for months and no reported symptom is attributed to it. What is **not** safe is doing
> TASK-458 or TASK-460 while this stays parked.
>
> A `TlsYieldGuard` scoped to end-of-function, or the C1 fetch consolidation, **normalises crypto to
> resume-after as a side effect.** That happens to be the correct outcome — so it would not be a
> *bug*, it would be an **untracked behaviour change buried inside a refactor.** If crypto then
> misbehaves, nothing distinguishes "the guard broke it" from "the timing change broke it", which is
> exactly the diagnostic trap `tasks-winamp-player.md`'s post-mortem is about.
>
> **Therefore: if TASK-458 or TASK-460 is scheduled, TASK-495 lands first, as its own commit.** Two
> lines, ten minutes, bisectable. It is not worth scheduling alone, and it must not be skipped in
> front of those two.
>
> **RESOLVED 2026-08-16 (E-02, human): resume-AFTER the parse.** `fetchCrypto` changes to match
> `fetchWeather`; the stale comment at `dataTaskStorage.cpp:262-265` claiming they already match
> becomes true. Rationale: resume-before hands heap back sooner but lets the Spotify task reconnect
> *during* a parse — the TASK-289 shape. Resume-after is the safer of the two and is what the
> `TlsYieldGuard` scoped to end-of-function would produce anyway, so TASK-458 no longer has to change
> behaviour silently. **TASK-458 is unblocked**; do this as its first commit, separately, so the
> behaviour change is reviewable on its own.
>
> *Original finding, retained:*
> **TASK-495 — a live divergence, found by review, verified in source.** `fetchWeather` resumes the
Spotify TLS session **after** its JSON parse (`dataTaskStorage.cpp:311`; parse `:289-309`).
`fetchCrypto` resumes **before** its parse (`:360`; parse `:362-386`). The comment at `:262-265`
asserts weather *"matches crypto below"* — it does not. One of these is wrong, or the difference is
deliberate and undocumented; nobody currently knows which. **This must be settled before TASK-458's
`TlsYieldGuard` lands**, because a guard scoped to end-of-function silently moves crypto's resume to
after its parse — changing when Spotify may reconnect and re-take heap mid-parse. A refactor must not
make that decision by accident. Blocks TASK-460 (C1) and gates TASK-458.

**TASK-496 — the composition root cannot be built as designed.** `main.cpp:242-245` / `:296-303` gate
`SpotifyApp`, `WebRadioApp` and `LocalPlayerApp` behind `#ifdef WINAMP_DISPLAY`, and `:314-321`
already forks `g_apps[]` — populated under that flag, `{}` otherwise. ADR-060 D2's X-macro sketch has
no conditional mechanism. Resolve by **retiring `cyd2usb`** (ADR-061 D8 already proposes demoting it —
so TASK-496 and TASK-467 are interdependent) or by adding a conditional column to the registry.
Un-gated today because `check_build.sh` builds only `WINAMP_DISPLAY` envs — which is ADR-061 D6's
argument arriving from a second direction. **Blocks TASK-456.**

---

## From the @VE review, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| **TASK-497** | **P2** | **DONE 2026-08-16** — 3 runs at HEAD; base-tree half retired on evidence | retrospective ≥3-run DUT baseline for the landed Stages A/B. *@PM: worth paying for — it is the only way left to recover D13's guarantee, and the cost is bounded and one-time. But it needs the same DUT block as 488's diff review. **One scheduling block, not two.*** |
| TASK-498 | P3 | OPEN | `T_SRC_09` — regression test for IFC-003 I9 (the TASK-384 swallow shape) |
| TASK-499 | P3 | OPEN | a `T_CC_` id for M-CONCURRENCY G1: enumerate every `WiFi.` call site against the known-safe set |

**TASK-497 — the baseline window is not closed, but it now costs double.** ADR-059 D13 and
`T_SRC_01` both require ≥3 full runs *before* a stage lands. Stages A (`78caa95`) and B (`b36f184`)
landed without one. @VE's ruling: because both are claimed **pure text moves**, the pre-refactor tree
still exists in git — checkout `78caa95~1`, run the suite 3×, then diff against 3 fresh runs on
master. That **does** recover D13's actual guarantee (no test passing in all baselines fails after).
What it cannot recover is catching a regression *live*, when a bisect would have been cheap.
**"We'll trust the diff review instead" is explicitly insufficient** — that is the
review-reinforces-a-wrong-frame failure the milestone note called out. Pairs with TASK-488.

**TASK-497 — result, 2026-08-16.** Three full `./run/test` runs at HEAD (`3d300e4`), same DUT
session as TASK-488, sleep-inhibited, each trap-restoring production.

| run | passed | failed | skipped | flaked |
|---|---|---|---|---|
| 1 | 138 | 15 | 47 | 5 |
| 2 | 133 | 17 | 51 | 4 |
| 3 | 134 | 16 | 51 | 4 |

**Stable core — failed in all three runs (6):** `T_WR_TLS_01`, `T_WR_COEX_01`, `T_WR_VOL_03`,
`T_WR_EJECT_02`, `T_PLR_06`, `T_PRM_02`. `T_WR_TLS_01` is the root — station fetch failed on every
mirror (the TASK-284 truncation shape) — and the four other WebRadio/Player ids all need a station
list, so they cascade from it. None sits near the moved code.

**Union across the three runs: 29 ids — so 23 of 29 failures are run-specific.** Environmental noise
outweighs deterministic failure on this rig by roughly 4:1. Run 2's extra failures were a network
degradation visible in the diagnostics as the dataTask backoff counter climbing `cf=17→19` (`T186`,
`T188`, `T192`, `T193`, `T204`, `T-BUSY-01`, `T272`); run 1's extra failures were missing SD fixtures.

**That ratio is the baseline's real product.** D13's guarantee — *no test passing in all baselines
fails after* — can only be read against the 6-id core; a single post-change run proves close to
nothing here. Anyone comparing a future run against this baseline must compare **sets**, per LL-104.

**The base-tree half was retired on evidence, with human sign-off.** The plan was 3 runs at
`78caa95~1` then 3 at HEAD. `T_488_03` established that the debug binaries at those two trees are the
same machine code (73 bytes of build metadata apart), so the base-tree runs would have executed an
identical binary. The human chose to skip them. `78caa95~1` **does** build (verified), so the option
is still open if the ruling is ever revisited.

**TASK-499 — G1 has no test id at all.** M-CONCURRENCY calls the missing WiFi arbiter "the largest
unclosed gap" and then reserves nothing for it. If OQ1 there resolves to *document-only*, that
decision itself needs an id whose job is proving the three known collisions (X014, TASK-436,
TASK-404) have no fourth sibling waiting.

---

## Follow-ups raised by the TASK-467/496 implementation, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| TASK-500 | P3 | **DONE 2026-08-23** | **Architect ruling: same-core preemption race, not cross-core.** `serialdbg` is `loopTask` (`handleSerialCommands()` runs inline from `loop()`, `main.cpp:269`) — not a separate task. IFC-002 already tabulates `loopTask` and `dataTask` both pinned to core 1 and states system-wide "there is no true parallelism between them... every race here is a preemption race." X015 was one instance of that already-settled general case, not a novel decision — updated its `description` to cite IFC-002 directly and fixed a leftover stray "Core 0" reference in the same entry that TASK-491's original fix had missed. `interaction_type`/`risk` unchanged (both were already correct). |
| TASK-501 | P3 | **DONE 2026-08-25** | Swept the remaining `#ifdef WINAMP_DISPLAY` blocks, now scattered across `boot/boot.cpp`, `main.cpp`, `appShell.cpp`, `debug/serialConsole/{console,cmdTouch,cmdGet,cmdSet}.cpp` post-TASK-471's file moves — filed count was ~20/24, actual as-of-today was **26** opening directives (`grep -rnE` for `#ifdef WINAMP_DISPLAY` / `#if defined WINAMP_DISPLAY`), noted here as the corrected count. Re-verified this task's own precondition before touching anything: `app/platformio.ini` defines `-DWINAMP_DISPLAY` exactly once (`[env:cyd2usb_winamp]`) and all 6 buildable envs extend it directly or transitively — every env really does define the flag. **Converted 24 of the 26** by deleting the `#ifdef`/`#endif` (or `#ifdef`/`#else`/`#endif` where the else-branch was a trivial dead-code placeholder, e.g. `(void)step;` or a "NONE" JSON fallback — same shape TASK-496 removed) and keeping the always-taken branch unconditional. **Left 2 sites untouched, and reverted one attempt** — `main.cpp:168` (the core `SpotifyDisplay*` backend instantiation: `WinampDisplay` vs `CheapYellowDisplay` vs `MatrixDisplay`) and `logHeartbeat.h:48` (`displayName()`, the same three-way selector) are not simple presence/absence gates like the other 24 — they are the actual multi-display-backend selection logic. Collapsing them would delete `CheapYellowDisplay`/`MatrixDisplay` support outright, which is explicitly TASK-470's reserved, not-yet-authorized scope ("delete `cheapYellowLCD.h`", blocked behind TASK-468/469 in that chain) — not this task's call to make. (Caught this mid-edit: `logHeartbeat.h` was briefly collapsed to `return "winamp";` unconditionally, then reverted to its original 3-way `#if`/`#elif`/`#elif`/`#else` before committing — flagging here since the instruction was to report genuine ambiguity, and this is exactly that class of judgment call, just resolved by finding TASK-470's own row rather than needing to stop and ask.) Verified: `run/check` 11/11 across all 6 firmware envs (not just one), `golden.sha256` clean, `check_app_conformance`/`check_player_binding`/doc gates all still pass. **DUT**: flashed debug, confirmed boot (heartbeat present), `switchApp`/`tap`/`drag`/`get kb` all functional (exercises the touch-injection sites in `cmdTouch.cpp`/`console.cpp`), and `get stacks` returns correct `wrPumpSize/Free/Used` (the ternary in `cmdGet.cpp` this task simplified — `0/0/0` pre-WebRadio-use, exactly as designed) — confirms the removed branches compile to the same behavior, not just the same binary size. Production firmware restored. |
| TASK-502 | P3 | **DONE 2026-08-25** | Fixed both "5-gate" mentions (`project_run_scripts.md:28`, `dut_workflow.md:71`) to the real 11-gate count, sourced from `check_build.sh`'s own header comment (1-6 firmware env matrix, 7 golden hash, 8 tool smoke, 9 app-registry staleness, 10 mem_layout staleness+budget, 11 check-docs) rather than re-deriving it. **Cross-reference table**: the six named scripts (`ae04`, `wr-soak`, `stress`, `pr-soak`, `wr-gate`, `task488`) had no home in `dut_workflow.md` at all — not just missing from the table, the sections themselves didn't exist. Added a new `dut_workflow.md` §5e ("Soak & gate scripts") describing all six (flash target + one-line purpose, sourced from each script's own header comment) plus `pr-fetch-soak` (same family, directly adjacent to `pr-soak`, an equally obvious omission not worth a second pass to catch later), then added matching rows to `project_run_scripts.md`'s cross-reference table pointing at §5e. Did not attempt a full audit of every other `run/` script against these two docs (e.g. `screendump`, `check-teletext-api`, `player-gate`, `playorder-player`, `browser-player`, `bake-airports`, `bake-icons` are also absent from both) — out of scope for this row, which named a specific six plus the gate count; flagged here for whoever picks up a broader pass. Verified: `run/check --docs-only` clean, no new C1/C3 findings (C3's "unknown env name" count unchanged — the added `cyd2usb_webradio` references are a known env). |

---

## Follow-ups raised by the TASK-488 verification, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| TASK-503 | — | **DONE**, via TASK-464 (`f8bae91`) | Design docs describing `SpotifyAppState` / `ClockAppState` / `AquariumAppState`. All five sites checked (`app-lifecycle.md`, `clock.md`, `source-ownership.md`, `M-AQUARIUM/overview.md`, `roadmap.md`) now carry an explicit "removed/superseded, deleted in `a044f5d`, retained as design record" note ahead of the struct text — none present the types as live. |
| TASK-504 | **P2** | OPEN | **`T_488_11` is not measurable as written** — redesign it. Entering WebRadio / LocalPlayer takes and releases the ~48 KB A-lite arena, which swamps a before/after free-heap read (one pre-refactor sweep measured **+39144 B**). Options: exclude the two player apps (`--no-players`, already implemented), or force arena release before sampling. Also mandate a same-duration **idle control** — a bare before/after at two uptimes cannot separate a leak from settling drift, which is what made the first run's −6768 B unreadable. |
| TASK-505 | P3 | OPEN | Free internal heap falls ~10 KB then ~8.6 KB over the first two 33-switch app sweeps, then flattens (+24 B on the third). **Pre-existing** — reproduced on pre-refactor firmware — so not a TASK-488 regression, but nobody has established whether the plateau is genuine or just a slower slope. Wants a longer sweep count on a quiet rig. |
| TASK-507 | P2 | **DONE 2026-08-16** | **`T_488_04`–`T_488_11` exist as a harness (`app/tools/test_task488_partb.py`) but are not registered in `docs/verification/test_plan.md`** — eight ids with pass criteria, a driver script and a green run, invisible to the VE artifact that is supposed to be the test inventory. @VE to register, with `T_488_11` marked as the known-unmeasurable one pending TASK-504. Same class of gap TASK-490 was filed to prevent. |
| TASK-506 | P3 | OPEN | `./run/test` leaves user settings mutated: after the TASK-497 runs, `settings.json` came back with `clock.style` vfd→digital, `planeRadar.rangeIdx` 3→1 and `pollSec` 30→10, `player.mode`/`playlist`/`repeat` changed, and four `webRadio` fields including `volumePct` 55→49. BP-049's snapshot made it recoverable, but the suite should restore what it changes — `T_PRM_01` failing "prPollSec not persisted" is the same defect seen from inside. |

---

## PM note — the honest read

This board was produced in a single day by one Architect pass, and its shape reflects that. Three
things a scheduler should know:

1. ~~**Nothing here is verified.**~~ **Superseded 2026-08-16.** TASK-488 closed: Stages A and B
   (`a044f5d`, `78caa95`, `b36f184`) are verified pure moves — byte-identical blocks, identical
   `.map` extents, and a DUT pass over app switching, taskbar, eject, Settings and the whole debug
   console. TASK-497's 3-run baseline is taken. The chain below is unblocked; TASK-455 can start.
2. **The dependency chain is long and mostly serial** — 488 → 455 → 456 → 471 → 472. Anything
   promising "main.cpp under 40 lines" is five tasks away, not one.
3. **Four tasks are independently valuable and unblocked today**: TASK-458 (RAII guards, fixes a real
   bug class), TASK-466 (build matrix — an env has been broken for months), TASK-475
   (`run/check-docs`), TASK-478 (`lib/dut.py`). If this board gets partially scheduled, those four
   are the ones that pay for themselves without the rest.
