# Design — M-TOOLING: giving the host tooling an architecture

> Owner: Architect
> Status: **proposed** — 2026-08-16
> Date: 2026-08-16
> Companion to: [M-SRCLAYOUT](M-SRCLAYOUT-main-decomposition.md) — the same disease, the other tree
> Tracked-as: TASK-478 … TASK-482
> Extends: **LL-114** (host tools rot because they have no gate)

**The headline.** `app/tools/` is **36 877 lines of Python across 99 files** — **larger than the
firmware it supports** (`app/src` is 30 201 lines). It has never been architected. Every convention
in it is emergent, and one file in it is a bigger monolith than `main.cpp` ever was.

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
