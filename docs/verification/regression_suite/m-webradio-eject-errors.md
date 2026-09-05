# M-WEBRADIO Eject + Error States VE Suite

> Owner: Verification Engineer
> Milestone: M-WEBRADIO
> Tasks: TASK-211 (eject serial surface), TASK-212 (error state injection)
> Status: open — awaiting DUT run
> DUT: ESP32-2432S028R CYD2USB, firmware cyd2usb_winamp_debug

---

## Test inventory

| ID              | Description                                              | Method | Result |
|-----------------|----------------------------------------------------------|--------|--------|
| T_WR_EJECT_01   | Inject eject tap from Spotify → action=EJECT, switches to WebRadio | serial | open |
| T_WR_EJECT_02   | Inject eject tap from WebRadio → action=EJECT, switches to Spotify | serial | open |
| T_WR_ERR_01     | Inject ERROR_BLOCKED state → marquee shows "Station blocked"       | — body deleted | **retired 2026-09-05 (TASK-603)** |
| T_WR_ERR_02     | Inject ERROR_UNREACHABLE state → marquee shows "Station unreachable" | — body deleted | **retired 2026-09-05 (TASK-603)** |
| T_WR_ERR_03     | Inject ERROR_WIFI state → marquee shows "WiFi lost"                | — body deleted | **retired 2026-09-05 (TASK-603)** |
| T_WR_ERR_04     | Inject CONNECTING state → POSBAR at 0% (thumb at left)            | — body deleted | **retired 2026-09-05 (TASK-603)** |
| T_WR_ERR_05     | **Replacement for all four.** Drive a REAL error path through the dead-URL injector (not a `set wrState` round trip) and assert the resulting banner text and an empty POSBAR against an oracle the harness did not write | serial | `blocked` on TASK-579 — `set wrDeadUrls` is the injector nothing clears (`F-4`). **Records the gap: from 2026-09-05 no id asserts that any WebRadio error state produces its banner, or that `ERROR_*` empties the POSBAR** |

---

## Preconditions (common)

- `./run/build` clean; flashed with `cyd2usb_winamp_debug`.
- Device on WiFi, serial monitor active (`./run/monitor-read`).
- For T_WR_ERR_01–04: stations must be loaded first (`get wrCount` returns `count >= 1`).
  Enter WebRadio app to trigger station fetch; wait for count > 0.

---

## T_WR_EJECT_01 — Eject from Spotify switches to WebRadio

- **Type**: DUT serial
- **Tasks**: TASK-211
- **Objective**: Injecting a tap at the eject button coordinates while in Spotify causes
  the firmware to populate `lastTouchResult` with `action="EJECT"` and switch to WebRadio.
- **Steps**:
  1. Ensure `get appId` returns `{"name":"Spotify"}`.
  2. Send `tap 136 89` (CB_EJECT_X=136, CB_EJECT_Y=89 from `gen/skin_layout.h`).
  3. Assert response contains `"hit":"EJECT"` and `"action":"EJECT"`.
  4. Send `get appId`.
  5. Assert response contains `"name":"WebRadio"`.
- **Expected**: `tap` response: `"hit":"EJECT","action":"EJECT"`.
  `get appId`: `"name":"WebRadio"`.
- **Rationale**: Confirms the `hitTestEject` → `lastTouchResult` path and the app-switch
  wired in `SpotifyApp::handleInput`.

---

## T_WR_EJECT_02 — Eject from WebRadio switches back to Spotify

- **Type**: DUT serial
- **Tasks**: TASK-211
- **Objective**: Injecting a tap at the eject button from inside the WebRadio app stops
  audio and switches back to Spotify.
- **Preconditions**: Device in WebRadio app (`get appId` → `"name":"WebRadio"`).
- **Steps**:
  1. Ensure `get appId` returns `{"name":"WebRadio"}`.
  2. Send `tap 136 89`.
  3. Assert response contains `"hit":"EJECT"` and `"action":"EJECT"`.
  4. Send `get appId`.
  5. Assert response contains `"name":"Spotify"`.
- **Expected**: Same as T_WR_EJECT_01 but in the opposite direction.
- **Rationale**: Confirms `WebRadioApp::handleInput` eject path, `_stopAudio()`,
  and `switchApp(AppId::Spotify)`.

---

## T_WR_ERR_01 — ERROR_BLOCKED → "Station blocked"

- **Status**: **retired 2026-09-05 (TASK-603)** — body deleted; the marquee/POSBAR claim below never had an oracle, it appeared only in the pass string. Replacement: `T_WR_ERR_05`, `blocked` on TASK-579. See [retired_test_ids.md](../retired_test_ids.md).

- **Type**: DUT serial
- **Tasks**: TASK-212
- **Objective**: Forcing `_state = ERROR_BLOCKED` (=6) via serial causes the title zone
  to display "Station blocked" on next repaint.
- **Preconditions**: WebRadio app active, `get wrCount` shows `count >= 1`.
- **Steps**:
  1. Send `set wrState 6` (ERROR_BLOCKED).
  2. Assert response `{"ok":true}`.
  3. Send `get wrState` — assert `"state":6`.
  4. Visually confirm (or via screenshot) title zone shows "Station blocked".
- **Expected**: `set wrState 6` accepted. Title zone text = "Station blocked".
  POSBAR at 0% (empty — no buffer fill in error state).

---

## T_WR_ERR_02 — ERROR_UNREACHABLE → "Station unreachable"

- **Status**: **retired 2026-09-05 (TASK-603)** — body deleted; the marquee/POSBAR claim below never had an oracle, it appeared only in the pass string. Replacement: `T_WR_ERR_05`, `blocked` on TASK-579. See [retired_test_ids.md](../retired_test_ids.md).

- **Type**: DUT serial
- **Tasks**: TASK-212
- **Objective**: Force `_state = ERROR_UNREACHABLE` (=5); assert marquee text.
- **Preconditions**: WebRadio app active, `get wrCount` shows `count >= 1`.
- **Steps**:
  1. Send `set wrState 5`.
  2. Assert `get wrState` returns `"state":5`.
  3. Confirm title zone shows "Station unreachable".
- **Expected**: Title = "Station unreachable". POSBAR empty.

---

## T_WR_ERR_03 — ERROR_WIFI → "WiFi lost"

- **Status**: **retired 2026-09-05 (TASK-603)** — body deleted; the marquee/POSBAR claim below never had an oracle, it appeared only in the pass string. Replacement: `T_WR_ERR_05`, `blocked` on TASK-579. See [retired_test_ids.md](../retired_test_ids.md).

- **Type**: DUT serial
- **Tasks**: TASK-212
- **Objective**: Force `_state = ERROR_WIFI` (=3); assert marquee text.
- **Preconditions**: WebRadio app active, `get wrCount` shows `count >= 1`.
- **Steps**:
  1. Send `set wrState 3`.
  2. Assert `get wrState` returns `"state":3`.
  3. Confirm title zone shows "WiFi lost".
- **Expected**: Title = "WiFi lost". POSBAR empty.

---

## T_WR_ERR_04 — CONNECTING → POSBAR at 0%

- **Status**: **retired 2026-09-05 (TASK-603)** — body deleted; the marquee/POSBAR claim below never had an oracle, it appeared only in the pass string. Replacement: `T_WR_ERR_05`, `blocked` on TASK-579. See [retired_test_ids.md](../retired_test_ids.md).

- **Type**: DUT serial
- **Tasks**: TASK-212
- **Objective**: Force `_state = CONNECTING` (=1); assert POSBAR shows empty (0% fill)
  and title shows "Connecting...".
- **Preconditions**: WebRadio app active, `get wrCount` shows `count >= 1`.
- **Steps**:
  1. Send `set wrState 1` (CONNECTING).
  2. Assert `get wrState` returns `"state":1`.
  3. Confirm title zone shows "Connecting...".
  4. Confirm POSBAR shows no green fill (buffer at 0%).
- **Expected**: Title = "Connecting...". POSBAR empty (no green fill visible).
- **Note**: POSBAR green fill is driven by `_bufPct`. Synthetic injection leaves
  `_bufPct` at its last value; if non-zero from a prior PLAYING state, the fill
  will still show. Stop audio first with `set wrStop 1` to reset `_bufPct = 0`
  before injecting CONNECTING.

---

## Serial command reference

```
# State injection (TASK-212)
set wrState 0   # STOPPED
set wrState 1   # CONNECTING
set wrState 2   # PLAYING
set wrState 3   # ERROR_WIFI
set wrState 4   # ERROR_STALL
set wrState 5   # ERROR_UNREACHABLE
set wrState 6   # ERROR_BLOCKED

# Eject injection (TASK-211)
tap 136 89      # CB_EJECT_X=136, CB_EJECT_Y=89

# Query surfaces
get wrState     # current playState int
get wrCount     # station count
get wrIdx       # current station index
get wrEject     # confirms eject wired (wired=true)
get appId       # current app name
```

---

## Exit criteria coverage

| Criterion (TASK-211/212)                                 | Test(s)       | Status |
|----------------------------------------------------------|---------------|--------|
| `tap 136 89` yields `action=EJECT` from Spotify          | T_WR_EJECT_01 | open   |
| Eject from Spotify → WebRadio (appId switches)           | T_WR_EJECT_01 | open   |
| `tap 136 89` yields `action=EJECT` from WebRadio         | T_WR_EJECT_02 | open   |
| Eject from WebRadio → Spotify (appId switches)           | T_WR_EJECT_02 | open   |
| `set wrState 6` → display "Station blocked"              | T_WR_ERR_05 (`blocked`) | **UNCOVERED** since 2026-09-05 |
| `set wrState 5` → display "Station unreachable"          | T_WR_ERR_05 (`blocked`) | **UNCOVERED** since 2026-09-05 |
| `set wrState 3` → display "WiFi lost"                    | T_WR_ERR_05 (`blocked`) | **UNCOVERED** since 2026-09-05 |
| `set wrState 1` → POSBAR at 0%, title "Connecting..."   | T_WR_ERR_05 (`blocked`) | **UNCOVERED** since 2026-09-05 |

---

## How to run

```sh
./run/test-targeted T_WR_EJECT_01,T_WR_EJECT_02
# T_WR_ERR_01-04 retired 2026-09-05 (TASK-603); the replacement id T_WR_ERR_05 is
# blocked on TASK-579 and has no body yet.
```

---

## 2026-09-05 — the four `T_WR_ERR_*` ids are retired, and this leaves a real gap

TASK-603 deleted `T_WR_ERR_01`–`04`. Every one of them was a `set wrState N` / `get wrState == N`
round trip through a single `_state` member, and `dbgSet` returns `true` for any input, so the `ok`
check proved nothing either. **The named subject of each — a banner, an empty POSBAR — appeared only
in the pass string and never had an oracle.** `T_WR_ERR_03` was worse than hollow: the shared
teardown wrote back `set wrState 3` believing it was STOPPED, and 3 is `ERROR_WIFI`, so all four
exited parked in an error state ahead of six ids whose oracle is `wrState == 2`.

Two consequences, both recorded rather than absorbed:

1. **TASK-583 is closed by this deletion, explicitly.** Its subject was that shared teardown
   (`_wr_err_test`), which is deleted along with the only four bodies that called it. There is
   nothing left for it to fix.
2. **The replacement is `T_WR_ERR_05`, and it is `blocked` on TASK-579.** It must drive a real error
   path through the dead-URL injector; `set wrDeadUrls` is the injector nothing clears (`F-4`), so
   the id cannot be written until that lands. **Until then no id asserts that any WebRadio error
   state produces its banner, or that `ERROR_*` empties the POSBAR.** That is a genuine coverage
   gap, open from 2026-09-05, and it is the only one TASK-603 creates.

Register: [retired_test_ids.md](../retired_test_ids.md).
Procedure: [test_id_retirement.md](../../process/test_id_retirement.md).
