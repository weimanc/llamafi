# M-CLOCK-STYLES VE Suite

> Owner: Verification Engineer  
> Milestone: M-CLOCK-STYLES (TASK-193)  
> Status: **0 of 8 exit criteria mechanically met** — C1 through C8 are **all** DEFERRED, and only C1
> was ever recorded that way. 10 of 14 ids live (4 retired `UNOBSERVABLE`, TASK-603).
> The original 2026-06-13 header read "PASS — 14/14"; it was wrong on both halves (H-2, TASK-587).
> **The milestone is not blocked on them** and no further work is scheduled — human ruling
> 2026-09-06, recorded in the last section of this file. That ruling did **not** satisfy the
> criteria; it scheduled no further work on them.  
> DUT: ESP32-2432S028R CYD2USB, firmware cyd2usb_winamp_debug  
> Exit criteria: M-CLOCK-STYLES.md C1–C8

---

## Test inventory

| ID | Description | Method | Result |
|----|-------------|--------|--------|
| T_CLK_01 | switchApp(1) switches to Clock; appId confirmed | serial | PASS |
| T_CLK_02 | clockStyle defaults to digital | — body deleted | UNOBSERVABLE (2026-09-05, TASK-603) — the only oracle was a settings byte read back through the command that wrote it. Owner TASK-638 |
| T_CLK_03 | set clockStyle flip — accepted, readback matches | serial | PASS |
| T_CLK_04 | set clockStyle nixie — accepted, readback matches | serial | PASS |
| T_CLK_05 | set clockStyle vfd — accepted, readback matches | serial | PASS |
| T_CLK_06 | set clockStyle by numeric index 0..3 | serial | PASS |
| T_CLK_07 | invalid clockStyle value rejected (ok=false) | serial | PASS |
| T_CLK_08 | clockStyle persists via settings save (settings.json) | serial | PASS |
| T_CLK_09 | style preserved across app-switch round-trip (Matrix→Clock) | — body deleted | UNOBSERVABLE (2026-09-05, TASK-603) — as T_CLK_02. Owner TASK-638 |
| T_CLK_10 | appId remains 1 (Clock) while VFD style active | serial | PASS |
| T_CLK_11 | heap stable after cycling all 4 styles ×2 | serial | PASS |
| T_CLK_12 | Clock→Spotify transition stable; Spotify appId=0 after | serial | PASS |
| T_CLK_13 | device responsive to serial during Flip style | — body deleted | UNOBSERVABLE (2026-09-05, TASK-603) — nothing observed an interval, a frame count or `_anyFlipActive()`. Owner TASK-615 (add `frames`/`gateMs` to `get clockStyle`) |
| T_CLK_14 | get clockStyle response has val (int), name (str), last=true | — body deleted | UNOBSERVABLE (2026-09-05, TASK-603) — the reply shape is the harness's own echo. Owner TASK-638 |

---

## Notes

- T_CLK_11 heap: before=124736 after=124736 (leak=0 B across 8 style switches)
- T_CLK_13 tested DUT responsiveness during Flip animation; direct tick-gate
  measurement (30ms) is firmware-internal and not observable via serial. **That is
  the finding, not a mitigation**: a responsiveness proxy is not the tick gate, so
  the id was retired UNOBSERVABLE on 2026-09-05 (TASK-603) rather than left green.
- Exit criteria C1 (MM x-position stability), C4 (flip pixel residue), C5 (Nixie bounds),
  C6 (VFD segment visibility) and C8 (app-switch pixel residue) are visual/display criteria.
  All are DEFERRED. **They are not "covered by T_CLK_03/04/05 (DUT-responsive proxy)"** — that
  sentence stood here until 2026-09-06 and was the wording H-2 named: a proxy that reads back a
  settings byte is not coverage of a pixel claim, and describing it as coverage is what let five
  criteria read PASS. The mechanism that will settle them is ADR-064's `get sig`, not an operator's
  eye; "pending physical screen review by operator" was never scheduled and is not a plan.

---

## Exit criteria coverage

| Criterion | Test(s) | Status |
|-----------|---------|--------|
| C1 MM stays x-pos across 10 blink cycles | visual — DEFERRED | DEFERRED |
| C2 Settings Style row cycles 4 styles on tap | T_CLK_06 — `set clockStyle <n>` over serial; **no body taps the Settings row** | **DEFERRED** (2026-09-06, TASK-587) — the criterion is about the *tap*, and the oracle bypasses the touch path entirely by writing the field over the console. Unlike C5-C8 the mechanism **already exists**: `tap <x> <y>` (`app/src/debug/serialConsole/cmdTouch.cpp:21`) plus a `get clockStyle` readback, with the row's coordinates derived from the generated layout, never typed (ADR-064 D7). Owner **TASK-639** |
| C3 Style persists across app switch + power cycle | T_CLK_08 (fixed under TASK-603 — now reports `SettingsStorage::save()`'s return); T_CLK_09 **retired UNOBSERVABLE** | **DEFERRED** — the power-cycle half has never been observed: no body reboots. Re-run C3 once T_CLK_08's re-write lands on hardware |
| C4 Flip: animation ≤500ms; no pixel residue | T_CLK_13 **retired UNOBSERVABLE** (TASK-615) | **DEFERRED** — read PASS on a responsiveness proxy that measures neither the animation duration nor a pixel. This is `H-2`'s mechanism |
| C5 Nixie: tubes within y:5..85 | T_CLK_04 — `set clockStyle nixie` accepted, readback matches; **no oracle reads a pixel or a coordinate** | **DEFERRED** (2026-09-06, TASK-587) — settled by ADR-064 `get sig <x> <y> <w> <h>`: `inkCount > N` inside y:5..85 **and** `inkCount == 0` in a band above/below it, `distinctColors > 1` (D3), region from `shell_layout.h` (D7), quiescent via `get idle` (D8). Owner **TASK-638** (mechanism) → **TASK-639** (the id) |
| C6 VFD: active/inactive segments visible | T_CLK_05 — as C5, `vfd`; **no oracle reads a colour** | **DEFERRED** (2026-09-06, TASK-587) — settled by `get sig`'s `distinctColors > 1` with `bgColor` named, over the digit region: active and inactive segments visible *is* a two-colour claim, which is D3's structural assertion needing no golden and no `set now`. Owner **TASK-638** → **TASK-639** |
| C7 Non-Flip styles: 1000ms tick gate | T_CLK_11 — heap unchanged across 8 style switches; **no oracle reads an interval, a frame or a tick** | **DEFERRED** (2026-09-06, TASK-587) — a leak-free heap is not a tick gate. Needs the firmware field H-2 names (a frame or `_lastTickMs` counter on `get clockStyle`, owner **TASK-615**); `get sig` alone cannot settle it, because a differential over an animation window (ADR-064 D6) shows *that* it changed, not *at what interval*. Owner **TASK-615** |
| C8 Spotify→Clock→Spotify: no pixel residue | T_CLK_12 — Spotify `appId == 0` after the round trip; **no oracle reads a pixel** | **DEFERRED** (2026-09-06, TASK-587) — settled by ADR-064 D6's differential shape: `sig(Spotify, before) == sig(Spotify, after)` over the canvas, quiescent at both ends. Residue is exactly a signature difference, so this needs neither a golden nor `set now`. Owner **TASK-638** → **TASK-639** |

---

## How to run

```sh
./run/test-targeted T_CLK_01,T_CLK_03,T_CLK_04,T_CLK_05,T_CLK_06,T_CLK_07,T_CLK_08,T_CLK_10,T_CLK_11,T_CLK_12
# (T_CLK_02/09/13/14 retired UNOBSERVABLE 2026-09-05 — TASK-603)
```

---

## 2026-09-05 — TASK-603

Four of the fourteen ids (`T_CLK_02`, `T_CLK_09`, `T_CLK_13`, `T_CLK_14`) were retired to
`UNOBSERVABLE` and their bodies deleted; two exit criteria that rested on them (C3, C4) were
re-recorded **DEFERRED**. The remaining `PASS` cells on proxy criteria — C2, C5, C6, C7, C8, each
reading PASS on "the DUT accepted the command and did not crash" — are **TASK-587's** subject and
are deliberately left alone here; TASK-587 is the row that re-records them.
Register: [retired_test_ids.md](../retired_test_ids.md). Procedure: [test_id_retirement.md](../../process/test_id_retirement.md).

---

## 2026-09-06 — TASK-587

The remaining false PASSes are re-recorded **DEFERRED**. TASK-603 handled C3 and C4 (both rested on
ids it retired); this row handles what was left: **C5, C6, C8** — H-2's three survivors — **plus C7
and C2**, which the TASK-603 note above explicitly parked here.

| criterion | what the PASS actually rested on | now |
|---|---|---|
| C2 | `set clockStyle <n>` over the console — the tap is never performed | DEFERRED, owner TASK-639. **The only one whose mechanism exists today** (`tap`), so it is the cheapest of the five |
| C5 | `set clockStyle nixie` accepted, readback matches | DEFERRED, owner TASK-638 → TASK-639 |
| C6 | `set clockStyle vfd` accepted, readback matches | DEFERRED, owner TASK-638 → TASK-639 |
| C7 | heap unchanged across 8 style switches | DEFERRED, owner **TASK-615** — needs a firmware counter, not `get sig` |
| C8 | Spotify `appId == 0` after the round trip | DEFERRED, owner TASK-638 → TASK-639 |

**Why DEFERRED and not deleted.** Every one of the five is a claim the project holds — the faces are
supposed to render, and the milestone is about the faces. `retired_test_ids.md` states the rule this
follows: a claim that is real and cannot be observed today gets a row with an owning task and a
statement of what would make it observable. Deleting these criteria would make the milestone report
consistent by making it say less than the project means.

**No id changes.** This row re-records criteria only. `T_CLK_03/04/05` keep their PASS cells and
those cells are honest at their own scope — the command is accepted and the field reads back. What
was wrong was booking that evidence against a criterion about pixels. (Whether those three ids should
exist at all is **H-11**, a different question, not decided here.)

**What is still owed after this row.** Nothing of TASK-587's; the criteria are recorded honestly. The
milestone itself, however, is now visibly **not complete** — 0 of 8 criteria met — where it read
14/14 for twelve weeks. That is a status change on M-CLOCK-STYLES (TASK-193) and belongs to @PM, not
to this document.

---

## 2026-09-06 — human ruling: the milestone is not blocked; the criteria stay DEFERRED

**Ruled by:** the human operator, 2026-09-06, on @PM's escalation of TASK-587's outcome.
**Ruling, verbatim:** *"I've visually inspected them, it's ok to move on."*

**What this changes.** M-CLOCK-STYLES (TASK-193) is **not blocked** on C1–C8, and **no further work
is scheduled** to close them. The mechanism tasks named in the tables above (TASK-638 `get sig`,
TASK-639, TASK-615) keep their own lives inside M-HARNESS2; nothing here schedules them for this
milestone's sake.

**What this does not change — read this before quoting the ruling.** All eight criteria remain
**DEFERRED**. None of them was satisfied, and none may be re-recorded PASS on the strength of this
ruling. The tables above are unchanged and stay the record of what each criterion is still owed.

**The evidence, stated exactly.** A **human visual inspection of the clock faces on 2026-09-06**.
It is:

* **informal** — no procedure, no build hash, no recorded observation of any specific criterion;
* **unrepeatable** — nothing about it can be re-run, by a person or by the harness;
* **not mechanically verified** — no oracle read a pixel, a coordinate, a colour or an interval, and
  the oracles that would (ADR-064's `get sig`, a firmware tick counter, `tap`) still do not exist;
* **not a substitute for `get sig`** — if anyone later wants these criteria actually met, the work
  is exactly what the tables above name, unchanged by this ruling.

A future reader must not read this section as the criteria having been satisfied. It is a decision to
stop spending on them, taken with the gap fully in view.
