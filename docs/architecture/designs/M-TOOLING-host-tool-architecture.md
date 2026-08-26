# Design — M-TOOLING: giving the host tooling an architecture

> Owner: Architect
> Status: accepted
> As-built: 2026-08-26
> Date: 2026-08-16
> Companion to: [M-SRCLAYOUT](M-SRCLAYOUT-main-decomposition.md) — the same disease, the other tree
> Tracked-as: TASK-478 … TASK-482
> Extends: **LL-114** (host tools rot because they have no gate)

**The headline.** `app/tools/` is **36 877 lines of Python across 99 files** — **larger than the
firmware it supports** (`app/src` is 30 201 lines). It has never been architected. Every convention
in it is emergent, and one file in it is a bigger monolith than `main.cpp` ever was.

> **CORRECTED — @Architect independent review, 2026-08-26 (R2). "Larger than the firmware it
> supports" is false, and was already false on the day it was written.** The size claim is right; the
> comparison is not.
>
> **Re-measured today.** `app/tools/` = **42 335 lines across 103 tracked `.py`** (106 counting
> `.sh`; the doc's "99 files" corresponds to py+sh, which was 97 at its own date). `app/src` =
> **32 622 lines / 118 files**. Both figures rise, the ratio holds — as a *bare* `app/src`
> comparison.
>
> **But `app/src` is not the firmware.** `app/gen/` — **11 116 lines** — is compiled into every
> build, and is the *output of* `app/tools/`'s own `gen_*` and `bake_*` families. Counting the bakers
> as tooling while excluding what they emit from the firmware biases the comparison twice. Firmware
> compiled out of this repo is **32 622 + 11 116 = 43 738 > 42 335**. Adding the
> `Spotify-Diy-Thing/SpotifyDiyThing/` headers pulled in via `lib_extra_dirs` (2 814) takes it to
> 46 552. Vendored `app/lib/` (30 993) is excluded from both sides as not-ours.
>
> **At the doc's own date (`e6e934c`, the tree as it stood 2026-08-16):** tools 38 082, `app/src`
> 29 798, `app/gen` 11 106 → firmware **40 904 > 38 082**. The headline never held on any denominator
> that includes generated code.
>
> **What survives:** the host tooling is *comparable in size to* the firmware it supports, and one
> file in it is a bigger monolith than `main.cpp` ever was (F1, still true — see R4/R8 below). Both
> are enough to justify this document. "Larger than" is not, and should not be re-cited. **This is
> also OQ2's premise, which falls with it — see §8.**

---

## 1. What is already good — do not disturb it

The shell layer is genuinely cohesive, and the fixes LL-114 prompted did land:

| Asset | Evidence |
|---|---|
| `run/lib.sh` | 63 lines, **sourced by 30 of 36** `run/` scripts. `resolve_port()` and `cert_preflight()` are shared, not copied. |
| `tools/shell_layout.py` | the LL-114 parse-don't-mirror fix; 6 importers |
| `tools/preview_common.py` | 261 lines, 8 importers |
| `gen_*` codegen | staleness-gated by `run/check` steps 6 and 7 — the strongest enforcement anywhere in the project |

**The `run/` layer is the model.** One shared library, thin scripts on top, a documented entry point
per operation. The Python layer beneath it never got the same treatment.

## 2. Findings

### F1 — `run_serialdbg_tests.py` is 10 229 lines. It is `main.cpp` again.

280 top-level functions, **128 of them test bodies** (`t077`, `t078`, …) and ~150 shared helpers
(`_drain_serial`, `_do_drag`, `_diag_snapshot`, `_ensure_stock_list_view`, …).

**Same disease, same cause.** Every test landed there because that is where the helpers already were.
It is the exact gravity well M-SRCLAYOUT §3 describes in `main.cpp`, reproduced in the other tree —
and it has gone unremarked because it is "just tooling".

It is also the project's primary regression suite. Its size is a *verification* risk, not only a
tidiness one.

> **CORRECTED — @Architect independent review, 2026-08-26 (R4). The finding holds and is if anything
> understated; its decomposition is wrong in both directions, and §3's split plan is mis-sized as a
> result.**
>
> Counted at the doc's own commit (`e6e934c`) by top-level `def` prefix, the 280 break down as:
> **128 `t_<family>_<nn>` + 81 `t<NNN>` + 66 `_helper` + 5 other**. Both `t_*` and `t<NNN>` are test
> bodies — and `t077`/`t078`, the two examples this finding names, come from the **81 it excluded**.
>
> So: **209 test bodies, not 128. 66 shared helpers, not ~150.** `suite/serialdbg/_helpers.py` is
> budgeted for roughly three times the mass it would actually hold, and the per-family split of §3
> has **63 % more bodies to distribute** than planned. TASK-480 should re-derive both before sizing
> its stages.
>
> **And the file is growing again — R8.** 10 229 lines here; **9 705** after TASK-478 (`989c1ea`)
> extracted `lib/dut.py`; **10 005 today**, top-level `def` 280 → 283. Nine days re-absorbed ~60 % of
> the extraction's gain. That is F1's gravity well observed operating in real time, and it is the
> strongest argument in this document — stronger than the line count it leads with.

### F2 — the shared layer solves the wrong half

`ve_suite_base.py` is 97 lines with 7 importers, and it provides **result reporting only**:
`pass_`, `fail`, `skip`, `flake`, an arg parser, a suite runner.

It provides **nothing for the actually hard part** — opening a DUT session, resolving the port,
sending a serial command and parsing the reply. So:

| Duplicated concern | Tools re-implementing it |
|---|---|
| port resolution (`ttyUSB` / VID:PID `1A86:7523`) | **33** |
| serial send / expect loop | **29** |
| direct `import serial` | 14 |
| own `find_port()` / `DEFAULT_PORT` | 6 |

`run/lib.sh` already has `resolve_port()`. **The shell layer solved this once; the Python layer solved
it thirty-three times.**

> **CORRECTED — @Architect independent review, 2026-08-26 (R3). The premise is wrong and both
> headline counts are naive greps. A real finding is in here, but it is not this one.**
>
> **The verified half.** `ve_suite_base.py` at `e6e934c` really does provide reporting only — read in
> full: `RESULTS`, `pass_`, `fail`, `skip`, `flake`, `make_arg_parser`, `run_suite`, `print_results`.
> Nothing else. That part of the finding is accurate.
>
> **The inference half fails at the mechanism (BP-067).** At that same commit
> `run_serialdbg_tests.py` already contained a complete `class Dut` — `send()`, `read_json()`,
> `read_json_multi()`, `cmd()`, `cmd_drain()`, `drain_log_lines()`, `_wait_for_ready()`, `close()`,
> plus `_TeeSerial` and `SetupFailure` — with **15 in-tree importers**, and `ve_suite_base.py`'s own
> module docstring *instructs* every new satellite suite to write `from run_serialdbg_tests import
> Dut` alongside it. "Opening a DUT session, sending a serial command and parsing the reply" was not
> missing. It was **misplaced** — buried inside the regression suite, so importing it meant importing
> 10 229 lines. §3's "`lib/dut.py` … is what F2 says is missing" is therefore wrong about its own
> premise, and TASK-478 landed accordingly: its commit message reads "`Dut` already had 16 importers
> … moved VERBATIM". An extraction, not a build.
>
> **The "33" does not mean what it says.** It is a file-count of the string `ttyUSB`, the exact
> shape M-CODEQUAL §13.2's counting note warns against. At `e6e934c`, 33 `.py` files match — and
> **9 of them match only inside a `"""` usage line** (`python3 test_fetch_stress.py --port
> /dev/ttyUSB0 …`), zero code sites. Of the remaining 24, every one except `run_serialdbg_tests.py`
> has exactly **one** code site, and it is a hardcoded *default literal*
> (`ap.add_argument("--port", default="/dev/ttyUSB0")` ×11, `PORT = sys.argv[1] if len(sys.argv) > 1
> else "/dev/ttyUSB0"` ×4, `default="/dev/ttyUSB1"` ×3, …) — not a resolution routine.
>
> **`1A86:7523` appears in zero `.py` files in the tree at that date.** The finding names it in the
> same parenthesis as the count; nothing in the Python layer re-derived it. Exactly **one** file
> implemented port resolution at all — `screendump.py :: autodetect_port()` — and it already shells
> out to `run/port`, which is precisely the prescription §3 gives as its load-bearing
> recommendation. The design's own preferred mechanism had a working in-tree precedent it does not
> cite.
>
> **So the true shape:** the Python layer solved port resolution **once, correctly**, and *defaulted
> and hoped* 23 times. That is a robustness bug (a wrong default silently talks to nothing), not
> thirty-three duplications — which is why TASK-478's exit criterion landed as "all **13** argparse
> `default=` sites", not 33, and why TASK-479 recorded the count as "already drifted down from 33"
> when it went to migrate them. The `import serial` row is also low: **19** files at that date, not
> 14.
>
> **What survives, and is worth keeping:** the shared layer was split across two files with no stated
> relationship — reporting in `ve_suite_base.py`, session in a 10 229-line test runner — so there was
> no single thing to point a new tool at, and the cheap path was a hardcoded default. That justifies
> `lib/dut.py` on its own. The 33/29/14 table should not be re-cited.

### F3 — one-off scripts have no retirement policy

Six scripts named for the task that created them: `task398_connect_async_verify.py`,
`task399_402_dut_verify.py`, `task400_401_dut_verify.py`, `task402_posbar_trace.py`,
`task405_slew_verify.py`, `task432_alloc_guard_gate.py`.

**All seven owning tasks are closed and archived.** Nothing says whether these are retired, reusable,
or load-bearing. They are indistinguishable from live tooling by name, location or convention — so
nobody deletes them, and nobody trusts them either. This is the literal "ad-hoc point solution"
accumulation.

### F4 — the naming families have no rule

`bake_*` (6) · `gen_*` (7) · `preview_*` (14) · `test_*` (19) · `*_smoke*` (10) · `task*` (6) ·
`*_probe*` (3) · `run_*` (2), plus ~30 unclassifiable (`coords`, `screendump`, `sd_put`,
`spotify_state`, `wifi_watch`, `dut_fonts`, `audit_origin`, `tsync_diff`, …).

Nothing defines what separates `test_planeradar_soak.py` from `pr_delta_smoke.py` from
`prloc_ve_smoke.py`. A new contributor — human or agent — cannot tell where a new tool belongs, so
they invent an eighth family.

### F5 — 15 of 36 `run/` scripts are undocumented

`audit-origin`, `bake-airports`, `bake-icons`, `browser-player`, `ceefax-ws-soak`,
`check-datatask-certs`, `check-teletext-api`, `flash-player`, `flash-webradio`, `lib.sh`,
`playorder-player`, `pr-fetch-soak`, `screendump`, `wr-gate` are absent from `CLAUDE.md`'s run-script
table — which that file presents as the complete reference. One of them (`ceefax-ws-soak`) is
permanently broken (ADR-061 D8).

> **CORRECTED — @Architect independent review, 2026-08-26 (R9). The count is right, the count is
> also self-contradicted, and the list is now stale. The finding has not improved.**
>
> The prose says "15 of 36"; **the list names 14 items.** Off-by-one, self-contained in this
> paragraph.
>
> Re-checked today by testing every entry in `run/` for a `run/<name>` mention in `CLAUDE.md`:
> **15 of 37 undocumented** — `audit-origin`, `bake-airports`, `bake-icons`, `browser-player`,
> `check-datatask-certs`, **`check-docs`**, `check-teletext-api`, `flash-player`, `flash-webradio`,
> `lib.sh`, **`player-gate`**, `playorder-player`, `pr-fetch-soak`, `screendump`, `wr-gate`.
>
> The set has churned: `ceefax-ws-soak` is gone from the tree entirely, while `check-docs` and
> `player-gate` were *added* undocumented since. Same number, different members — the interface layer
> is not being maintained as an interface, exactly as OQ3 suspects. Note `run/check-docs` is now
> gate 11 of `check_build.sh`, i.e. **the documentation gate is itself absent from the document it
> gates.** Cite the count, re-derive the list.

## 3. Design — mirror D0, one level down

The firmware got a component model. The tooling gets the same treatment, because the failure mode is
identical: **no physical design, so everything lands wherever the helpers already are.**

```
app/tools/
  lib/                        ← LEVEL 0: the shared layer that should have existed
    dut.py            DUT session: port resolve, open, send, expect, teardown
    report.py         pass_/fail/skip/flake + suite runner  (today's ve_suite_base)
    layout.py         parse gen/*.h                          (today's shell_layout)
    coords.py         derived tap coordinates                (unchanged)
    preview.py        shared render surface                  (today's preview_common)

  gen/                        ← LEVEL 1: codegen — writes into app/gen/, staleness-gated
    gen_app_registry.py  gen_mem_layout.py  gen_countries.py  gen_taskbar_icons.py …

  bake/                       ← LEVEL 1: asset bakes — deterministic, golden.sha256-gated
    bake_skin.py  bake_nixie.py  bake_vis.py  bake_wave.py  bake_airports.py

  preview/                    ← LEVEL 2: host renderers (LL-114: parse, never mirror)
    preview_layout.py  preview_clock.py  preview_teletext.py  preview_heatmap.py …

  suite/                      ← LEVEL 3: DUT suites, one module per family
    serialdbg/            ← F1: split the 10 229-line runner
      __init__.py         registry + runner
      shell.py            t077…  taskbar/app-switch
      stock.py  clock.py  teletext.py  planeradar.py  webradio.py  player.py
      _helpers.py         the ~150 shared helpers, named and owned
    sync.py  cert.py  …

  probe/                      ← LEVEL 2: one-shot host probes against live services
    pr_adsb_probe.py  geocode_probe.py  test_radiobrowser_api.py …

  spike/                      ← EXPIRING: one-offs, with a retirement rule (§4)
    task398_connect_async_verify.py  …
```

> **CORRECTED — @Architect independent review, 2026-08-26 (R5). The taxonomy has no home for the
> gates, and they are the most load-bearing tooling in the tree. Fix this before TASK-481 moves
> anything.**
>
> Every one of the 103 `.py` files under `app/tools/` was classified against the seven directories
> above. **34 files / 8 052 lines — 33 % of the files, 19 % of the lines — fall outside all of
> them.** That bucket is not miscellany. It contains:
>
> - `check_docs.py` (992 lines), `check_app_conformance.py` (554), `check_player_binding.py` (222),
>   `check_settings_wiring.py` (106) — the host gates that `check_build.sh` and `run/check-docs`
>   invoke. They are not `gen/` (they write nothing), not `bake/`, not `preview/`, not `suite/` (they
>   never open a DUT), not `probe/` (no live service), not `spike/`. §1 calls this machinery "the
>   strongest enforcement anywhere in the project" and §3 gives it nowhere to stand.
> - Their own tests — `test_check_docs.py` (1 000+ lines), `test_check_app_conformance.py`. Worse
>   than homeless: their `test_*` names route them into `suite/` under §5, whose row reads "runs
>   against **the DUT**" — a statement that is false about them.
> - Two sub-packages that already exist and this tree does not acknowledge: `app/tools/host/` and
>   `app/tools/pr_interp/` (7 files).
> - An analysis family with no verb in §5: `audit_origin.py`, `tsync_diff.py`, `e0_baseline.py`,
>   `exp012_measure.py`, `command_latency.py`, `dut_fonts.py`.
>
> F4's stated failure mode is "a contributor cannot tell where a new tool belongs, so they invent an
> eighth family". **A taxonomy a third of the corpus cannot be filed into does not prevent that — it
> guarantees it**, and the first things misfiled would be the gates. §3 needs at least a `gate/`
> level (host gates plus their tests, the things `run/check` runs) and a decision on the analysis
> family. Filed as **TASK-537**, blocking TASK-481.
>
> Smaller, same section: `lib/` as specified has five members; **two landed** (`report.py` shipped
> renamed as `lib/results.py`, `dut.py` as specified). `lib/layout.py`, `lib/coords.py` and
> `lib/preview.py` did not — `shell_layout.py` (47), `coords.py` (196) and `preview_common.py` (269)
> are still flat in `app/tools/`, and `ve_suite_base.py` (73) still exists separately rather than
> being subsumed. `lib/flaky.py` (11 KB) landed and is not in this tree at all.

**Dependency rule, same as D2a:** levels depend downward only. A suite may use `lib/`; `lib/` never
imports a suite. `preview/` and `bake/` never import from `suite/`.

**`lib/dut.py` is the load-bearing piece.** It is what F2 says is missing, and it is where 33 copies
of port resolution collapse into one. It should call `run/port` rather than re-deriving VID:PID — the
shell layer already owns that fact, and re-deriving it in Python is LL-114 all over again.

## 4. The anti-ad-hoc mechanism: a retirement rule

Structure alone will not stop accumulation; something has to remove things. Three rules:

1. **A tool written for one task goes in `spike/` and is named for its task.** That is already the
   convention — it just has no consequence attached.
2. **When the owning task is archived, the spike is deleted or promoted.** Promotion means: moved to
   its level, renamed for what it *does* rather than which task made it, given a docstring saying
   when to run it. Deletion is the default; git keeps it.
3. **`run/check-docs` gains a check**: any `spike/task<NNN>_*` whose `TASK-NNN` lives in
   `tasks-archive.md` fails. That is a five-line grep against the existing gate spec, and it makes
   the rule self-enforcing instead of aspirational.

Today's six spikes all fail rule 3 immediately — which is the correct first result.

> **CORRECTED — @Architect independent review, 2026-08-26 (R6). Rule 3 landed advisory, so the
> mechanism is currently the thing this section says it is not: aspirational.**
>
> TASK-482 shipped the check (`76c608e`) as `Result("SPIKE", blocking=False)`. Its reasoning is
> sound and is recorded in its row — landing it blocking would have redded out `run/check` on day one
> purely from the known backlog this section itself predicts. But the consequence inverts §4's own
> claim: rule 3 is described here as what "makes the rule self-enforcing instead of aspirational",
> and what shipped attaches no consequence — the same gap rule 1 diagnoses in the naming convention.
>
> **Verified empirically, not inferred:** all six spikes named in F3 are still present and unmoved at
> `app/tools/task*.py` today, nine days after the check landed. Advisory did not move them.
>
> **Verified that deletion is safe (BP-067 — the consequence checked at the mechanism, not the
> surface):** grepped `run/`, `check_build.sh`, `docs/process/` and every other `app/tools/*.py` for
> all six task numbers. **No invocation of any of them exists** — the sole hit is `check_docs.py`'s
> own comment naming `task399_402_dut_verify.py` as a parsing example. None is load-bearing, so
> "deletion is the default" carries no hidden cost here.
>
> **What §4 is missing is a promotion trigger.** It specifies the end state (blocking) and the day-one
> state (six failures) but not the transition. It should read: clear the six, *then* flip SPIKE to
> blocking in the same commit, so the gate can never be green-because-advisory again. Filed as
> **TASK-538**.

## 5. Naming taxonomy

Directory determines kind; the name says what it acts on. The `test_`/`_smoke`/`_verify` confusion
disappears because the distinction becomes structural:

| Directory | Runs against | Names |
|---|---|---|
| `gen/` | source tree → `app/gen/` | `gen_<what>.py` |
| `bake/` | assets → `app/gen/` | `bake_<what>.py` |
| `preview/` | host only, renders | `preview_<what>.py` |
| `probe/` | live external service | `probe_<service>.py` |
| `suite/` | **the DUT** | `<family>.py` inside the suite package |
| `spike/` | anything, temporarily | `task<NNN>_<what>.py` |

## 6. Staging

| Task | What | Risk |
|---|---|---|
| **TASK-478** | `lib/dut.py` — one DUT session helper, delegating to `run/port` | low, additive |
| **TASK-479** | Migrate the 33 port-resolution copies onto it, a few tools per commit | low, mechanical |
| **TASK-480** | Split `run_serialdbg_tests.py` into `suite/serialdbg/` by family | **medium — this is the regression suite; a baseline run is owed before and after** |
| **TASK-481** | Directory move + naming taxonomy (§3, §5) | low, mechanical; breaks every doc path — pair with TASK-464 |
| **TASK-482** | Retirement rule + the `run/check-docs` spike check | low |

**Do TASK-478 first.** It is additive, it makes every later migration mechanical, and it is the piece
whose absence caused the other findings.

**TASK-480 carries a real gate.** `run_serialdbg_tests.py` is the primary regression suite; splitting
it must be preceded by ≥3 baseline runs with the flaky set pre-declared — the same ADR-059 D13 rule
the firmware stages use, for the same reason.

## 7. Open questions

- **OQ1** — should `app/tools/` become an installable package with a `pyproject.toml`, so
  `from lib.dut import Dut` works without `sys.path` games? Lean: yes, at TASK-481. It is the
  difference between a directory of scripts and a codebase.
- **OQ2** — is 36 877 lines of tooling *itself* a finding? It exceeds the firmware. Some is
  irreducible (a 1 371-line skin baker is doing real work), but 128 test bodies in one file suggests
  the suite has grown by accretion rather than design. Worth a separate look after TASK-480 makes it
  legible.
- **OQ3** — `run/` (36 shell scripts) and `app/tools/` (99 Python) are two entry-point layers with
  overlapping responsibilities. Should every `run/` script be a thin shim over a Python module, or is
  the current split deliberate? Lean: keep the split — `run/` is the human/agent interface and is
  documented in `CLAUDE.md`; Python is the implementation. But F5's 15 undocumented scripts say the
  interface half is not being maintained as an interface.

---

## 8. Independent review — @Architect, 2026-08-26 (BP-066)

**Scope.** Full independent (non-author) review, ten days after authoring. Every claim re-derived
from source — the current tree and the tree at this document's own commit (`e6e934c`) — rather than
accepted as asserted. Corrections to specific claims are embedded as blockquotes at the claim
(headline, F1, F2, §3, §4, F5); the findings below are the ones with no single claim to attach to.

### R1 — this document had never been reviewed, and six tasks executed against it anyway

**Verified.** M-TOOLING is the **only** document in the 2026-08-16/17 Architect batch carrying zero
review markers. Grepped `docs/architecture/designs/` for `CORRECTED` / `@<Role> review` /
`added on review`: M-CODEQUAL has them, M-SRCLAYOUT has them, M-TESTBASE has 28 lines of them
including two rounds, M-TESTARCH, M-DOCLIFE-check-docs-spec, M-DOCLIFE-keeping-design-docs-alive,
M-CONCURRENCY — all reviewed. M-TOOLING: none.

**A methodological note for whoever re-checks this.** A naive case-insensitive grep for `review`
scores this file at 7 hits and makes the gap look filled. All seven are the substring inside
`preview_common.py` / `preview/` / `preview_layout.py`. The word-boundary form is what shows the
truth. This is the same class of error as F2's `ttyUSB` count (R3) — twice in one document, a grep
was reported as if it were a fact about code.

**Consequence.** BP-066 says a document does not gate work or get cited as fact until an independent
review has run. TASK-478, 479, 480, 481, 482 were filed from §6 and four of them have executed; the
prohibition was breached for ten days. The work that landed is nonetheless good — see R10 — which is
the uncomfortable part: the process failure produced no visible damage, and the errors R2/R3/R4 found
were absorbed silently by the executing agents (TASK-478 re-scoped from "build" to "extract" on
contact with reality; TASK-479 re-measured "33" and found it "already drifted down"). **Both agents
hit the same wrong premise, corrected locally, and neither told the document.** That is what BP-066
exists to catch and what BP-065's as-built rule is supposed to backstop.

### R7 — §3's target tree: one directory of seven exists

Checked the filesystem, not the board. Of `lib/`, `gen/`, `bake/`, `preview/`, `suite/`, `probe/`,
`spike/`: **`app/tools/lib/` exists** (`dut.py`, `flaky.py`, `results.py`, `__init__.py` — 4 files,
1 105 lines). The other six do not. Every file §3 assigns to them is still flat in `app/tools/`,
including all six spikes and the unsplit 10 005-line runner.

**The dependency rule holds where it can be tested.** `lib/dut.py`, `lib/flaky.py` and
`lib/results.py` import only stdlib plus `lib.flaky` — nothing in `lib/` imports a suite, and
`run_serialdbg_tests.py` imports downward from `lib/`. D2a's direction is intact so far. It has not
yet been tested in the direction that will actually strain it (`preview/` and `bake/` never importing
`suite/`), because neither directory exists.

### R10 — F-status after re-measurement

| | Verdict |
|---|---|
| **F1** | **Holds, understated.** Decomposition wrong (R4); file has regrown 9 705 → 10 005 (R8). |
| **F2** | **Partially holds.** Premise wrong, both headline counts wrong (R3). The weaker true form still justifies `lib/dut.py`, which landed. |
| **F3** | **Holds unchanged.** Six spikes still present; mechanism landed advisory (R6). |
| **F4** | **Holds** — and R5 shows the proposed cure covers only two thirds of the corpus. |
| **F5** | **Holds.** Count right, list stale and off by one (R9). Nothing has addressed it; no task owns it. Filed as **TASK-539**. |

**§6 staging, verified row by row against `tasks-architecture.md` and the commits, not by task
number.** TASK-478 (`989c1ea`) — landed, but as an *extraction* of an existing `Dut`, not the build
§3 describes; the design was wrong about what was there, the execution was right. TASK-479
(`b5d837c`) — **partial**: port-resolution half migrated across 15 files, the send/expect half
explicitly deferred as a per-file behavioural rewrite rather than a mechanical swap. That deferral is
correct and the design did not anticipate it: §6 rates TASK-479 "low, mechanical", and only half of
it is. TASK-480 — **not started**; baseline 1 of 3 taken (`301debd`), stalled on a rig-wide WiFi
outage. TASK-481 — blocked, correctly, and now additionally blocked on TASK-537 (R5). TASK-482
(`76c608e`) — landed advisory, not blocking (R6). TASK-536 belongs to M-ROWGATE, not to this
document, and is listed in this board's M-TOOLING section only by adjacency.

### R11 — the open questions, answered where they can be

- **OQ1 (packaging) — still open, and materially worse than when asked.** No `pyproject.toml` exists
  anywhere in this repo. `sys.path.insert(...)` appears in **20+** top-level tools to reach siblings,
  and `lib/` is reached the same way. The `sys.path` games OQ1 wanted to remove are now load-bearing
  for the level-0 library itself. The lean ("yes, at TASK-481") still reads correct.
- **OQ2 ("is tooling's own size itself a finding?") — answerable now; answer: yes, but not for the
  reason asked, and the question's premise is dead.** OQ2 rests on "it exceeds the firmware", which
  R2 shows was never true. On growth: `app/tools/` went **38 082 → 42 335 lines (+4 253, +11 %)**
  since this document's baseline, while `app/src` went **29 798 → 32 622 (+2 824, +9.5 %)**.
  Comparable rates — tooling is **not** outpacing the firmware, and there is no runaway to find.
  **The real signal is concentration, not total:** `run_serialdbg_tests.py` alone is 10 005 lines =
  **23.6 % of all host tooling**, and it grew *during* the period a task was open to split it (R8).
  That is F1, already tracked as TASK-480. **OQ2 should be closed as answered rather than deferred
  "until after TASK-480" — the measurement it was waiting for has now been taken and points back at a
  finding the document already has.**
- **OQ3 (`run/` vs `app/tools/` split) — stands, but its lean is now conditional.** 37 shell scripts
  against 103 Python files. The lean is "keep the split, because `run/` is the documented human
  interface" — and R9 shows 41 % of that interface is undocumented, including `run/check-docs`, a
  gate. The split is still right; the *justification given for it* is currently false. Keep the
  split, and treat TASK-539 as the condition that makes the justification true again.

### As-built / disposition (BP-065)

**Status `proposed` → `accepted`.** Not because tasks landed against it — four did, and R10 shows
two of them landed differently from what §6 specified. It is accepted because the *framing* survives
attack where it counts: the diagnosis (no physical design, so everything lands where the helpers
already are), the level model, the downward dependency rule, and the retirement mechanism are all
sound, and the two pieces that have executed (`lib/dut.py`, the SPIKE check) work. Leaving it at
`proposed` after a review has run would be the worse error — it would keep a now-reviewed document
formally uncitable under BP-066.

**Accepted with corrections, not as written.** Four claims in it are false and are struck at the
point of use: the headline's "larger than the firmware" (R2), F2's premise and its 33/29/14 table
(R3), F1's 128/~150 decomposition (R4), F5's list (R9). Two of the four are naive greps reported as
facts about code — the failure M-CODEQUAL's own counting note warns about, repeated here twice.
Anyone citing this document must cite the corrected figures.

**One blocking defect.** §3's taxonomy has no home for a third of the corpus, including the project's
own gates (R5). **TASK-481 must not execute until TASK-537 closes** — a directory move is the one
operation that makes a taxonomy hole permanent and expensive.

**Filed from this review:** TASK-537 (gate/ level, blocks 481), TASK-538 (SPIKE promotion trigger),
TASK-539 (F5 — document the 15).

**Reviewer hit-rate, this pass (BP-066 requires tracking it):** 11 findings raised, all 11 verified
against source before filing. Of the six items the review brief flagged as worth checking, **5 were
confirmed and 1 was refuted** — OQ2's implied premise, that tooling's size relative to the firmware
is the finding, does not survive measurement. The genuinely new findings, not on the brief, are
**R5** (taxonomy has no home for the gates — the only blocking one), **R3** (F2's premise is
inverted: the DUT layer existed and was misplaced, not missing), **R4** (test-body/helper counts),
and **R8** (the monolith is regrowing). A near-100 % confirmed rate on a first-ever review of a
ten-day-old document is exactly what BP-066 warns is a signal about authoring pace, not about review
quality.

**TASK-538 landed (BP-065 update).** R6's promotion trigger executed as specified: the six spikes
named in F3 were re-verified as unreferenced (grepped `run/` and every `app/tools/*.py` for all six
task numbers — the sole hit was `check_docs.py`'s own comment naming one as a parsing example, not a
code dependency) and deleted (git keeps the history), and `check_spike_retirement`'s `Result` was
flipped `blocking=False` → `blocking=True` **and** moved into `run()`'s counted `blocking` list — the
`Result.blocking` flag alone does not gate; a check only counts if the driver places it in that list,
which R6 did not call out and which TASK-538 discovered on contact with the code. SPIKE now reads 0
and is a counted gate alongside C5/C2/C4/C6. §4 rule 3 is no longer aspirational.
