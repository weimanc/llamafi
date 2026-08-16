# M-ARCH — architecture work board (M-SRCLAYOUT · M-CODEQUAL · M-TOOLING · M-DOCLIFE)

> Owner: Project Manager · Split out of [tasks.md](tasks.md) on 2026-08-16.
>
> **Why this file exists.** A 2026-08-16 Architect pass produced nine design documents, two ADRs and
> three IFCs, reserving 35 task ids. Filing those inline would have taken `tasks.md` from ~1 200
> lines back past 2 500, undoing the archive sweep done the day before. Same treatment as the
> M-WINAMP-PLAYER board.
>
> **Read this first — the honest state.** Three refactor commits (`a044f5d`, `78caa95`, `b36f184`)
> **already landed** ahead of ADR sign-off. They are unreviewed, not DUT-verified, and by ADR-060
> D0's measure they created **zero components** — `main.cpp` went 5 880 → 1 726 lines, which is
> readability, not physical design. The ≥3-run DUT baseline ADR-060 D9 requires was never taken.
> **TASK-453 and TASK-454 are therefore retro-filed as landed-but-unverified, not as open work.**
>
> Closed entries go to [tasks-archive.md](tasks-archive.md).

**Priority key**: P1 blocking · P2 should-do · P3 nice-to-have · P4 watch

---

## Owed before anything else proceeds

| task | pri | status | title |
|---|---|---|---|
| **TASK-488** | **P1** | OPEN | review `a044f5d` / `78caa95` / `b36f184` per M-SRCLAYOUT §7a, and take the owed DUT baseline |

**TASK-488 — review the three landed refactor commits**
**Owner**: human + VE · **Design**: [M-SRCLAYOUT §5a, §7a](../architecture/designs/M-SRCLAYOUT-main-decomposition.md)
Three commits assert pure moves. That assertion is unverified by anyone but their author. §7a gives
the recipe: `git show -M --stat`, byte-identity diffs of each moved block against
`git show <commit>~1:app/src/main.cpp`, `.map` extents before/after, and the zero-reference proof for
the three deleted structs (`SpotifyAppState`, `ClockAppState`, `AquariumAppState`). `run/check` 7/7
covers compile + smoke only — the DUT pass over app switching, taskbar cycling, eject and Settings
navigation has **not** been run. **Nothing in this board should land until this closes.**

---

## M-SRCLAYOUT — decompose main.cpp ([design](../architecture/designs/M-SRCLAYOUT-main-decomposition.md) · [ADR-060](../architecture/decisions/ADR-060.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-453 | — | **LANDED, UNVERIFIED** | Stage A — 7 app classes → `apps/*.h` (`78caa95`) |
| TASK-454 | — | **LANDED, UNVERIFIED** | Stage B — SERIAL_DEBUG console → `debug/serialConsole/*.h` (`b36f184`) |
| TASK-455 | P2 | BLOCKED on 488 | Stage C — `setup()` (621 lines) → `boot/boot.{h,cpp}`, verbatim (D1a) |
| TASK-456 | P2 | BLOCKED on 455 | Stage D — `shell/appTable.{h,cpp}` composition root + `ShellState` (D2/D3/D4) |
| TASK-471 | P2 | BLOCKED on 456 | Stage E — component conversion; real `.h`/`.cpp` pairs, self-contained (D0) |
| TASK-472 | P3 | BLOCKED on 471 | Stage F — `stock/` → 3 components, `sd/sdMount`, levelization audit |
| TASK-457 | P3 | OPEN | hygiene — `appRegistry.h` double-include comment, `currentAppId`/`g_previousAppId` unify |
| TASK-464 | P2 | BLOCKED on 454 | documentation-reference sweep — 308 `main.cpp:NNN` cites across 49 files + 44 in `feature_inventory.yaml`; pay **once**, at end of Stage B |

## M-CODEQUAL — duplication and abstraction ([design](../architecture/designs/M-CODEQUAL-duplication-and-abstraction.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-458 | **P2** | OPEN | C2 — `TlsYieldGuard` / `HttpSession` RAII guards. **Highest value in this board**: fixes a bug class with a proven production instance (TASK-222) |
| TASK-459 | P3 | BLOCKED on 458 | C2b — migrate `s_aeSpotifyYielded` to a transferable guard. Touches audio teardown ordering (`T_AE_04`) |
| TASK-460 | P2 | BLOCKED on 458 | C1 — consolidate the nine `fetch*()` functions onto one skeleton |
| TASK-461 | P2 | OPEN | C5 — one canonical canvas/window constant across firmware, bake and previews. 275 has **six names in three layers** |
| TASK-462 | P3 | BLOCKED on 454 | C3 — table-driven `cmdGet`/`cmdSet` (1 308 lines → a table) |
| TASK-463 | P3 | OPEN | C4 debug-code convention + C6 shared UI palette |

## ADR-061 — build-variant hygiene ([ADR](../architecture/decisions/ADR-061.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-465 | P3 | OPEN | D1–D5 — debug/production convention across `app/src`; propose to QM as a BP |
| TASK-466 | **P2** | OPEN | D6+D7 — full-matrix build gate (66 s measured) + three name-consistency checks |
| TASK-467 | P2 | OPEN | D8 — decommission: `cyd2usb`→base, `matrixDisplay.h`, `SPIKE_MODE`, ceefax leftovers, 10 libdeps orphans, doc corrections |
| TASK-468 | P2 | OPEN | D9 step 1 — `display/tft.{h,cpp}` component; rehome the 797-call-site global |
| TASK-469 | P3 | BLOCKED on 468 | D9 step 2 — flatten `WinampDisplay` onto `SpotifyDisplay` |
| TASK-470 | P3 | BLOCKED on 469 | D9 step 3 — delete `cheapYellowLCD.h` and `[cyd2usb_base]` |

## M-CONCURRENCY / IFC ([design](../architecture/designs/M-CONCURRENCY-task-ownership-contract.md) · [IFC-002](../architecture/interfaces/IFC-002.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-473 | P2 | OPEN | close the contract's gaps — G1 WiFi radio arbiter (three bugs: X014, TASK-436, TASK-404), G2 assert I2/I3, G3 dual mirrors |

## M-DOCLIFE — document decay ([design](../architecture/designs/M-DOCLIFE-keeping-design-docs-alive.md) · [spec](../architecture/designs/M-DOCLIFE-check-docs-spec.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-475 | **P2** | OPEN | implement `run/check-docs` C1–C5 per spec. C5 blocking day one (0 failures); C1 advisory (274/576) |
| TASK-474 | P3 | OPEN | PM/QM process items — `docs-touched:` in exit criteria, closed status vocabulary, reservations land immediately |

## M-TOOLING — host tool architecture ([design](../architecture/designs/M-TOOLING-host-tool-architecture.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-478 | **P2** | OPEN | `tools/lib/dut.py` — one DUT session helper, delegating to `run/port`. **Do first**; its absence caused F2–F4 |
| TASK-479 | P3 | BLOCKED on 478 | migrate 33 port-resolution copies + 29 send/expect loops onto it |
| TASK-480 | P2 | BLOCKED on 478 | split `run_serialdbg_tests.py` (10 229 lines, 128 tests) into `suite/serialdbg/`, mirroring the VE taxonomy. **≥3 baseline runs owed first** |
| TASK-481 | P3 | BLOCKED on 480 | directory + naming taxonomy; pair with TASK-464 (breaks doc paths) |
| TASK-482 | P3 | BLOCKED on 475 | spike retirement rule — a `task<NNN>_*` whose task is archived fails `run/check-docs`. All 6 current spikes fail immediately |

## Vendoring / `app/lib` ([ADR-060 D2b](../architecture/decisions/ADR-060.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-476 | P3 | OPEN | relocate `mb_arena` → `app/src/mem/arena`. **Blocked on an unanswered question**: can a PlatformIO `lib/` dir include from `src/`? Answer that first |
| TASK-477 | P3 | OPEN | fix `mb_arena.h`'s header comment — it claims production is "byte-clean"; `platformio.ini:93` defines `MEMBUDGET_PHASE1` in `[env:cyd2usb_winamp]` |

## Skeletons — problems with a home, not yet designed

Each has a **SKELETON** banner: a starting point, no conclusions, expect to restructure rather than
fill in.

| task | pri | status | title |
|---|---|---|---|
| TASK-483 | P3 | SKELETON | [M-TESTARCH](../architecture/designs/M-TESTARCH-test-architecture.md) — test architecture. **VE owns OQ1**: a host unit tier may not be worth it here |
| TASK-484 | P3 | SKELETON | [M-ERRMODEL](../architecture/designs/M-ERRMODEL-error-model.md) — four overlapping error conventions; IFC-001 already ships the `errorCode==0` ambiguity |
| TASK-485 | P2 | SKELETON | [M-LEVELS](../architecture/designs/M-LEVELS-dependency-audit.md) — audit D2a's asserted levels. **No include graph has ever been generated**; the audit may contradict D2a |
| TASK-486 | P3 | SKELETON | [M-VENDORING](../architecture/designs/M-VENDORING-upstream-policy.md) — five vendored trees, five conventions, no upstream refs recorded |
| TASK-487 | P4 | SKELETON | [M-DISPLAYSEAM](../architecture/designs/M-DISPLAYSEAM-adr028-revisit.md) — re-read ADR-028. Likely outcome: rejection stands |

## Handoff debt — reservations the Architect owed and did not perform

These are the failure AGENTS.md rule 10 was written to prevent, reproduced by the pass that cited
the rule. Filed 2026-08-16 after a second sweep for uncaptured items.

| task | pri | status | title |
|---|---|---|---|
| TASK-489 | P2 | **DONE 2026-08-16** | reserve X065 in `cross_feature_matrix.yaml` — Developer completes |
| TASK-490 | P2 | **DONE 2026-08-16** | reserve `T_CC_`/`T_SRC_`/`T_CQ_` families in `test_plan.md` — VE completes |
| TASK-491 | P3 | OPEN | correct X015 — it claims `dataTask` runs on Core 0; it pins to `APP_CPU_NUM` |
| TASK-492 | P3 | OPEN | retire `handleVolumeGesturePublic()` — M-AUDIO-ENGINE OQ2's surviving half |
| TASK-493 | P2 | OPEN | sync `architecture.md` — its diagram still shows `loop()` as the app shell |
| TASK-494 | P3 | OPEN | `feature_inventory.files:` → `components:` once components exist |

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

## PM note — the honest read

This board was produced in a single day by one Architect pass, and its shape reflects that. Three
things a scheduler should know:

1. **Nothing here is verified.** The only code that landed did so ahead of its own ADR, and TASK-488
   exists to close that. Treat every "LANDED" as provisional.
2. **The dependency chain is long and mostly serial** — 488 → 455 → 456 → 471 → 472. Anything
   promising "main.cpp under 40 lines" is five tasks away, not one.
3. **Four tasks are independently valuable and unblocked today**: TASK-458 (RAII guards, fixes a real
   bug class), TASK-466 (build matrix — an env has been broken for months), TASK-475
   (`run/check-docs`), TASK-478 (`lib/dut.py`). If this board gets partially scheduled, those four
   are the ones that pay for themselves without the rest.
