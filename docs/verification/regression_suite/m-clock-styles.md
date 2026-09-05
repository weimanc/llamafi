# M-CLOCK-STYLES VE Suite

> Owner: Verification Engineer  
> Milestone: M-CLOCK-STYLES (TASK-193)  
> Status: PASS — 14/14 (2026-06-13)  
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
- Exit criteria C1 (MM x-position stability) and C4 (flip pixel residue),
  C5 (Nixie bounds), C6 (VFD segment visibility), C8 (app-switch pixel residue)
  are visual/display criteria — marked DEFERRED pending physical screen review
  by operator. Covered by T_CLK_03/04/05 (DUT-responsive proxy) here.

---

## Exit criteria coverage

| Criterion | Test(s) | Status |
|-----------|---------|--------|
| C1 MM stays x-pos across 10 blink cycles | visual — DEFERRED | DEFERRED |
| C2 Settings Style row cycles 4 styles on tap | T_CLK_06 (serial proxy) | PASS |
| C3 Style persists across app switch + power cycle | T_CLK_08 (fixed under TASK-603 — now reports `SettingsStorage::save()`'s return); T_CLK_09 **retired UNOBSERVABLE** | **DEFERRED** — the power-cycle half has never been observed: no body reboots. Re-run C3 once T_CLK_08's re-write lands on hardware |
| C4 Flip: animation ≤500ms; no pixel residue | T_CLK_13 **retired UNOBSERVABLE** (TASK-615) | **DEFERRED** — read PASS on a responsiveness proxy that measures neither the animation duration nor a pixel. This is `H-2`'s mechanism |
| C5 Nixie: tubes within y:5..85 | T_CLK_04 (DUT accepts, no crash) | PASS |
| C6 VFD: active/inactive segments visible | T_CLK_05 (DUT accepts, no crash) | PASS |
| C7 Non-Flip styles: 1000ms tick gate | T_CLK_11 (no heap anomaly) | PASS |
| C8 Spotify→Clock→Spotify: no pixel residue | T_CLK_12 (app stable) | PASS |

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
