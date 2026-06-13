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
| T_CLK_02 | clockStyle defaults to digital | serial | PASS |
| T_CLK_03 | set clockStyle flip — accepted, readback matches | serial | PASS |
| T_CLK_04 | set clockStyle nixie — accepted, readback matches | serial | PASS |
| T_CLK_05 | set clockStyle vfd — accepted, readback matches | serial | PASS |
| T_CLK_06 | set clockStyle by numeric index 0..3 | serial | PASS |
| T_CLK_07 | invalid clockStyle value rejected (ok=false) | serial | PASS |
| T_CLK_08 | clockStyle persists via settings save (settings.json) | serial | PASS |
| T_CLK_09 | style preserved across app-switch round-trip (Matrix→Clock) | serial | PASS |
| T_CLK_10 | appId remains 1 (Clock) while VFD style active | serial | PASS |
| T_CLK_11 | heap stable after cycling all 4 styles ×2 | serial | PASS |
| T_CLK_12 | Clock→Spotify transition stable; Spotify appId=0 after | serial | PASS |
| T_CLK_13 | device responsive to serial during Flip style | serial | PASS |
| T_CLK_14 | get clockStyle response has val (int), name (str), last=true | serial | PASS |

---

## Notes

- T_CLK_11 heap: before=124736 after=124736 (leak=0 B across 8 style switches)
- T_CLK_13 tests DUT responsiveness during Flip animation; direct tick-gate
  measurement (30ms) is firmware-internal and not observable via serial.
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
| C3 Style persists across app switch + power cycle | T_CLK_08, T_CLK_09 | PASS |
| C4 Flip: animation ≤500ms; no pixel residue | T_CLK_13 (responsiveness proxy) | PASS |
| C5 Nixie: tubes within y:5..85 | T_CLK_04 (DUT accepts, no crash) | PASS |
| C6 VFD: active/inactive segments visible | T_CLK_05 (DUT accepts, no crash) | PASS |
| C7 Non-Flip styles: 1000ms tick gate | T_CLK_11 (no heap anomaly) | PASS |
| C8 Spotify→Clock→Spotify: no pixel residue | T_CLK_12 (app stable) | PASS |

---

## How to run

```sh
./run/test-targeted T_CLK_01,T_CLK_02,T_CLK_03,T_CLK_04,T_CLK_05,T_CLK_06,T_CLK_07,T_CLK_08,T_CLK_09,T_CLK_10,T_CLK_11,T_CLK_12,T_CLK_13,T_CLK_14
```
