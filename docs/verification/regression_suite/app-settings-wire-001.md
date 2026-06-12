# VE Regression Suite — M-SETTINGS-APP-WIRE (app-settings-wire-001)

> Owner: Verification Engineer
> Date: 2026-06-12
> Scope: ADR-043 / TASK-172 — per-app settings wiring (Matrix, Life, Aquarium, Stock, Crypto)
> Design ref: docs/architecture/designs/M-SETTINGS-APP-WIRE.md
> DUT: ESP32-2432S028R CYD2USB, cyd2usb_winamp_debug build, /dev/ttyUSB1
> Serial commands: `switchApp <id>`, `tap <x> <y>`, `get <var>`, `set <var> <val>`, `reboot`

---

## VE Design Review

### Challenges raised before implementation

**CHALLENGE-1 — Missing dbgGet infrastructure (blocks agent-driven tests)**

MatrixApp, LifeApp, AquariumApp, and CryptoApp currently have no `dbgGet` methods.
The design specifies new behavioural state (`_headColor`, `_tailColor`, `_tickMs`,
`_activeFish`, `_speedMult`, `s_cryptoIds`, `s_cryptoCcy`) but no serial exposure.
Without this, colour/speed/fish/coin changes are untestable via the harness —
only visual DUT checks are possible.

**VE requirement:** Developer must implement `dbgGet` for all new state variables
listed in §Required dbgGet surface below before VE can issue agent-driven PASS on E1–E6, E9, E10.

**CHALLENGE-2 — Crypto URL not observable**

`configureCrypto()` writes `s_cryptoIds` and `s_cryptoCcy` inside the dataTask.
There is no existing way to read these back from Core 1. Without either a dbgGet
path or a `[D][dataTask]` log line emitting the URL used at fetch time, the only
observable for a coin change is: did the price for the new coin appear?

**VE requirement:** Developer must either (a) expose `s_cryptoIds[i]` via
`dataTask::getCryptoConfig()` callable from a dbgGet handler on Core 1, or (b) emit
a log line `[D][dataTask.crypto] fetch ids=bitcoin,... ccy=usd` before the HTTP
call. Option (b) is simpler and sufficient.

**CHALLENGE-3 — Stock re-fetch timing**

T-WIRE-STOCK-02 verifies that a ticker change triggers an immediate re-fetch.
The observable is `get quoteOkCount` incrementing. On a cold TLS connection, the
8-ticker quote round takes ~30–60 s. The test must:
- Wrap the re-fetch wait in `_bgpoll_suspended` context (per ADR-042 E3 pattern), OR
- Use a 90 s timeout (budget: 60 s TLS + 30 s margin).
Current harness default timeout is 45 s — insufficient.

**VE requirement:** T-WIRE-STOCK-02 uses extended timeout or suspended-bg context.
Mark as `[SLOW]` in test plan. Not suitable for `run/test-smoke`.

**CHALLENGE-4 — Aquarium speed has no numeric observable**

`_speedMult` (0.5/1.0/2.0) affects fish swim speed. There is no existing timing
observable in the harness. Visual-only.

**VE requirement:** T-WIRE-AQ-02 is MANUAL. Acceptable for milestone sign-off.
If future automation is desired, Developer would need a `get aquariumSpeedMult`
dbgGet (returns "0.50"/"1.00"/"2.00").

**CHALLENGE-5 — Cancel path: g_settings snapshot vs app state**

E12 requires that tapping Cancel in Settings reverts per-app settings. The snapshot
restores `g_settings`, but the test must also verify the app picks up the restored
value on next `resume()` — not just that `g_settings` was restored.

**VE requirement:** T-WIRE-CANCEL-01 must:
1. Record initial app dbgGet value
2. Change setting via Settings UI
3. Confirm dbgGet value changed (resume took effect)
4. Re-enter Settings and tap Cancel
5. Switch back to app and confirm dbgGet returned to original value

**CHALLENGE-6 — Stock `stockMode` cold-init only**

Design spec: `stockMode` seeds `_s.subView` in `init()` only, not `resume()`.
This means the test must trigger a cold `init()` — either via `reboot` or by
ensuring the app was never previously `init()`-ed in the session. The `reboot`
path is the cleanest but requires a full DUT boot cycle (~15 s).

**VE requirement:** T-WIRE-STOCK-03 uses `reboot` to verify cold-init behaviour.
Mark as `[REBOOT]` in test plan.

---

## Required dbgGet surface (Developer must implement)

These variables must be added to the respective app `dbgGet` / serial dispatch
before VE can run agent-driven tests. Format: `get <var>` → JSON with `"val"`.

### MatrixApp dbgGet (add to `matrixDbgGet()` in `main.cpp`)

| Variable | Returns | Notes |
|----------|---------|-------|
| `matrixColor` | `"green"` \| `"white"` \| `"amber"` | From `_headColor`/`_tailColor` pair |
| `matrixTickMs` | numeric string, e.g. `"25"` | `_tickMs` instance variable |

### LifeApp dbgGet (add to `lifeDbgGet()` in `main.cpp`)

| Variable | Returns | Notes |
|----------|---------|-------|
| `lifeColors` | `"rainbow"` \| `"mono"` | From `g_settings.lifeColors` read in `resume()` |
| `lifeTickMs` | numeric string, e.g. `"100"` | `_tickMs` instance variable |

### AquariumApp dbgGet (add to `aquariumApp.h` + serial dispatch)

| Variable | Returns | Notes |
|----------|---------|-------|
| `aquariumFish` | numeric string, e.g. `"8"` | `_activeFish` value |

### StockApp dbgGet (extend existing `stockDbgGet`)

| Variable | Returns | Notes |
|----------|---------|-------|
| `stockTicker0`..`stockTicker7` | symbol string, e.g. `"AAPL"` | `_s.tickers[i]` |

### CryptoApp dbgGet (new `cryptoDbgGet()` in `main.cpp`)

| Variable | Returns | Notes |
|----------|---------|-------|
| `cryptoCoin0`..`cryptoCoin5` | word ID string, e.g. `"bitcoin"` | from `g_settings.cryptoCoins[i]` (read at init/resume) |
| `cryptoCcy` | `"usd"` \| `"eur"` | from `g_settings.cryptoCcy` lowercased |
| `cryptoLastFetch` | ms timestamp | `_s.lastCryptoFetch` |

Register `cryptoDbgGet` in `cmdGet()` dispatch (mirror `stockDbgGet` pattern at
`main.cpp:2255`). Register `matrixDbgGet`, `lifeDbgGet`, `aquariumDbgGet` similarly.

### dataTask log line (CHALLENGE-2 resolution)

`fetchCrypto()` in `dataTaskStorage.cpp` must emit **before** the HTTP call:
```
[D][dataTask.crypto] fetch ids=%s ccy=%s
```
where `%s` is the comma-joined coin IDs and currency. Used by T-WIRE-CRYPTO-03.

---

## Layout reference (Settings tap coordinates)

Derived from `S_CONTENT_Y=28`, `S_ROW_H=26`, `S_HEADER_H=28`. x=137 hits centre of
275 px canvas for all rows.

### Category list (Settings level 1)

| Row | Category | tap y (mid) |
|-----|----------|-------------|
| 0 | WiFi | 41 |
| 1 | Time & Location | 67 |
| 2 | Touch Calibration | 93 |
| 3 | Display | 119 |
| 4 | LED | 145 |
| 5 | Applications | 171 |

### Applications submenu (level 2 — kConfigurableApps order)

| Row | App | tap y (mid) |
|-----|-----|-------------|
| 0 | Crypto | 41 |
| 1 | Matrix | 67 |
| 2 | Life | 93 |
| 3 | Stock | 119 |
| 4 | Aquarium | 145 |

### Per-app rows (level 3)

**Matrix:** Color=41, Speed=67  
**Life:** Speed=41, Colors=67  
**Aquarium:** Fish count=41, Speed=67  
**Stock:** Ticker 1=41, Ticker 2=67, Ticker 3=93, Ticker 4=119, Ticker 5=145, Ticker 6=171, Ticker 7=197, Default view=223  
**Crypto:** Coin 1=41, Coin 2=67, Coin 3=93, Coin 4=119, Coin 5=145, Coin 6=171, Currency=197  

Back zone: `tap 30 14`  
AppIds: Spotify=0, Clock=1, Weather=2, Crypto=3, Matrix=4, Life=5, Settings=6, Stock=7, Aquarium=8

---

## Matrix settings (T-WIRE-MAT)

### T-WIRE-MAT-01 — Color change propagates to app on resume (SERIALDBG)

**Preconditions:** DUT booted, debug build. `switchApp 4` (Matrix) — note `get matrixColor` returns `"green"` (default).

**Steps:**
1. `switchApp 6` — enter Settings
2. `tap 137 171` — tap "Applications"
3. `tap 137 67` — tap "Matrix"
4. `tap 137 41` — tap "Color" row once → cycles green→white
5. `tap 30 14` — back to app list
6. `tap 30 14` — back to category list
7. `tap 30 14` — back / exit Settings → returns to previous app
8. `switchApp 4` — enter Matrix (triggers resume())
9. `get matrixColor`

**Expected:** Step 9 returns `{"ok":true,"cmd":"get","var":"matrixColor","val":"white","last":true}`.

**Pass criterion:** `val == "white"`.

---

### T-WIRE-MAT-02 — Tick interval matches speed setting (SERIALDBG)

**Preconditions:** Default Matrix state (`get matrixTickMs` returns `"25"`).

**Steps (slow):**
1. `switchApp 6` → `tap 137 171` → `tap 137 67` → `tap 137 67` (Speed row) once
2. Exit Settings: `tap 30 14` × 3; `switchApp 4`
3. `get matrixTickMs`

**Expected:** `val == "40"` (slow).

**Steps (fast):**
4. Re-enter Settings, tap Speed twice more (slow→normal→fast)
5. Exit and `switchApp 4`; `get matrixTickMs`

**Expected:** `val == "15"` (fast).

**Pass criterion:** tick intervals 40 / 25 / 15 ms match slow / normal / fast.

---

### T-WIRE-MAT-03 — Matrix color renders amber on DUT [MANUAL]

**Preconditions:** Settings → Applications → Matrix → Color cycled to "amber".

**Steps:** `switchApp 4`. Observe display for ≥ 5 s.

**Expected:** Falling character tails are amber-yellow (~orange), not green.

---

## Life settings (T-WIRE-LIFE)

### T-WIRE-LIFE-01 — Tick interval matches speed setting (SERIALDBG)

**Preconditions:** Default Life state (`get lifeTickMs` returns `"100"`).

**Steps:**
1. Settings → Applications → Life → Speed row tap once (normal→fast)
2. Exit; `switchApp 5`; `get lifeTickMs`

**Expected:** `val == "50"`.

3. Repeat: cycle to slow (fast→slow): Settings → Life → Speed × 2; exit; `switchApp 5`; `get lifeTickMs`

**Expected:** `val == "200"`.

---

### T-WIRE-LIFE-02 — Colors setting propagates (rainbow→mono) (SERIALDBG)

**Preconditions:** Default `get lifeColors` returns `"rainbow"`.

**Steps:**
1. Settings → Applications → Life → Colors row tap once
2. Exit; `switchApp 5`; `get lifeColors`

**Expected:** `val == "mono"`.

---

### T-WIRE-LIFE-03 — Life mono colors renders single color [MANUAL]

**Preconditions:** `g_settings.lifeColors` = mono (set via T-WIRE-LIFE-02).

**Steps:** `switchApp 5`. Observe live cells.

**Expected:** All alive cells render in a single green colour. No multi-colour gradient.

---

## Aquarium settings (T-WIRE-AQ)

### T-WIRE-AQ-01 — Fish count propagates on resume (SERIALDBG)

**Preconditions:** Default `get aquariumFish` returns `"16"`.

**Steps:**
1. Settings → Applications → Aquarium → Fish count tap once (16→4)
2. Exit; `switchApp 8`; `get aquariumFish`

**Expected:** `val == "4"`.

3. Repeat: cycle back to 16 (4→8→12→16): tap Fish count row 3× more; exit; `switchApp 8`; `get aquariumFish`

**Expected:** `val == "16"`.

---

### T-WIRE-AQ-02 — Fish count 4 shows significantly fewer fish on DUT [MANUAL]

**Preconditions:** Fish count set to 4 via Settings.

**Steps:** `switchApp 8`. Observe for ≥ 10 s.

**Expected:** Approximately 4 fish visible. School is sparse; crab may find no targets quickly.

---

### T-WIRE-AQ-03 — Fish count 16 shows full school [MANUAL]

**Preconditions:** Fish count set to 16 via Settings.

**Steps:** `switchApp 8`. Observe for ≥ 10 s.

**Expected:** Dense school of ~16 fish; crab is active with nearby targets.

---

### T-WIRE-AQ-04 — Aquarium speed slow/fast visually distinct [MANUAL]

**Preconditions:** Observe at default (normal), then change to fast.

**Steps:**
1. `switchApp 8`. Observe fish swim pace for 10 s.
2. Settings → Applications → Aquarium → Speed tap once (normal→fast); exit; `switchApp 8`.
3. Observe for 10 s.

**Expected:** Fish at fast setting swim noticeably quicker than normal. Reverse: change to slow and confirm slower pace.

---

## Stock settings (T-WIRE-STOCK)

### T-WIRE-STOCK-01 — Keyboard opens on ticker row tap (SERIALDBG)

**Preconditions:** Debug build. Settings → Applications → Stock submenu visible.

**Steps:**
1. `switchApp 6` → `tap 137 171` → `tap 137 119` (Stock)
2. `tap 137 41` — tap Ticker 1 row

**Expected:** Keyboard canvas appears (UpperAlpha mode). Prompt shows "Ticker 1". Input pre-filled with current ticker (e.g. "AAPL").

**Pass criterion (MANUAL + serial):** Screen shows keyboard. `get matrixColor` type queries still respond (device not locked). Serial confirms no crash.

---

### T-WIRE-STOCK-02 — Valid ticker validates and saves [SLOW] (SERIALDBG)

**Preconditions:** Ticker 1 = "AAPL". Note `Q0 = get quoteOkCount`.

**Steps:**
1. Settings → Applications → Stock → Ticker 1 row tap → keyboard opens
2. Clear input (backspace × 4); type "TSLA"; tap OK
3. Observe serial: validating screen appears
4. Poll `get stockTicker0` with 25 s timeout until `val == "TSLA"` (or timeout → error screen)
5. Exit Settings; `switchApp 7`; poll `get quoteOkCount` ≤ 90 s until `val > Q0`

**Expected:** Step 4: `val == "TSLA"`. Step 5: `quoteOkCount` increments. No `fetchFailed`.

**Note:** [SLOW] — validation chart fetch + quote fetch. Not in `run/test-smoke`.

---

### T-WIRE-STOCK-03 — Invalid ticker shows error screen [SLOW] (SERIALDBG + MANUAL)

**Preconditions:** Stock submenu accessible.

**Steps:**
1. Settings → Stock → Ticker 1 tap → keyboard opens
2. Type "ZZZZZZ"; tap OK
3. Observe display and serial for up to 22 s

**Expected:** Error screen appears: `"ZZZZZZ" not found`. Back tap or retry option visible. `get stockTicker0` still returns old value (not "ZZZZZZ").

**Pass criterion:** `val` unchanged. Error screen rendered. No crash.

---

### T-WIRE-STOCK-04 — Error retry re-opens keyboard with failed ticker pre-filled (SERIALDBG + MANUAL)

**Preconditions:** Error screen shown (from T-WIRE-STOCK-03 or similar invalid input).

**Steps:**
1. Tap content area (not `< back`)
2. Observe keyboard re-opens

**Expected:** Keyboard shows with "ZZZZZZ" (or whatever was typed) pre-filled in input bar.

---

### T-WIRE-STOCK-05 — Ticker change triggers immediate re-fetch [SLOW] (SERIALDBG)

**Preconditions:** StockApp stable, `Q0 = get quoteOkCount`. Ticker 1 changed to "TSLA" (via T-WIRE-STOCK-02).

**Steps:**
1. Exit Settings → `switchApp 7` (triggers `resume()` which detects ticker change)
2. Poll `get quoteOkCount` ≤ 90 s

**Expected:** `quoteOkCount > Q0` within timeout. No `fetchFailed`.

**Note:** [SLOW] — not in `run/test-smoke`.

---

### T-WIRE-STOCK-03 — Default view (stockMode) seeds subView on cold init [REBOOT] (SERIALDBG)

**Preconditions:** Settings → Applications → Stock → Default view tapped until showing `"chart"`.
Exit Settings; save confirmed.

**Steps:**
1. `reboot` — full DUT restart
2. Wait for boot (WiFi up, serial heartbeat)
3. `switchApp 7`
4. `get stockSubView`

**Expected:** `val == "chart"` (seeded from `g_settings.stockMode` in `StockApp::init()`).

**Pass criterion:** `stockSubView == "chart"` on first app activation after reboot.

---

### T-WIRE-STOCK-04 — Active session view NOT overridden by resume (SERIALDBG)

**Preconditions:** StockApp open, user drilled to chart view (`get stockSubView == "chart"` via tap).
`g_settings.stockMode == "list"` (default).

**Steps:**
1. `switchApp 6` → `switchApp 7` — leave and immediately re-enter StockApp
2. `get stockSubView`

**Expected:** `val == "chart"` — `resume()` does not reset to stockMode on re-entry.

---

## Crypto settings (T-WIRE-CRYPTO)

### T-WIRE-CRYPTO-01 — Coin change updates app state (SERIALDBG)

**Preconditions:** Default `get cryptoCoin0` returns `"bitcoin"`.

**Steps:**
1. Settings → Applications → Crypto → Coin 1 row tap once (cycles bitcoin→ethereum or next in pool)
2. Exit Settings; `switchApp 3`
3. `get cryptoCoin0`

**Expected:** `val` is the next coin ID in the pool (e.g. `"ethereum"` if pool cycled forward from `"bitcoin"`).

---

### T-WIRE-CRYPTO-02 — Currency change updates app state (SERIALDBG)

**Preconditions:** Default `get cryptoCcy` returns `"usd"`.

**Steps:**
1. Settings → Applications → Crypto → Currency row tap once
2. Exit Settings; `switchApp 3`
3. `get cryptoCcy`

**Expected:** `val == "eur"`.

---

### T-WIRE-CRYPTO-03 — dataTask fetch log includes configured coin IDs and currency (SERIALDBG)

**Preconditions:** Crypto coin 1 changed to `"dogecoin"`, currency changed to `"eur"` via Settings.
`switchApp 3` (triggers `init()` / `resume()` → `configureCrypto()`).

**Steps:**
1. Monitor serial output for up to 90 s (next fetch cycle or immediate on init)
2. Look for log line matching: `dataTask.crypto] fetch ids=...dogecoin... ccy=eur`

**Expected:** Serial log contains the DOGE ID in the fetch URL log line and `ccy=eur`.

**Pass criterion:** `"dogecoin"` present in fetch log; `"eur"` present in fetch log.

---

### T-WIRE-CRYPTO-04 — Display shows short name for coin ID (SERIALDBG + MANUAL)

**Preconditions:** Default coins: `cryptoCoin0 == "bitcoin"`.

**Steps:**
1. `switchApp 3`
2. Observe first row label on CryptoApp screen

**Expected (manual):** First row shows `"BTC"` (from `cgIdToDisplay("bitcoin")`), not `"bitcoin"`.

**Supplementary (SERIALDBG):** If a `cryptoDisplayName0` dbgGet is added later, verify `val == "BTC"`.
Without it, this is MANUAL-only at this milestone.

---

### T-WIRE-CRYPTO-05 — Price format: price < $1.00 uses 4 decimal places [MANUAL]

**Preconditions:** Set coin to `"ripple"` (XRP, typically < $5 but historically variable) or
`"cardano"` (historically < $1). Check current price to confirm < $1.00.

**Steps:**
1. `switchApp 3`; observe XRP/ADA price display.

**Expected:** Price displayed with 4 decimal places (e.g. `"0.4523"`), not 2.

**Rationale:** Verifies the magnitude-based `formatCryptoPrice()` replaces the per-symbol heuristic.

---

## Cancel / snapshot path (T-WIRE-CANCEL)

### T-WIRE-CANCEL-01 — Settings cancel restores Matrix color (SERIALDBG)

**Preconditions:** `get matrixColor` returns `"green"` (default).

**Steps:**
1. `switchApp 4` → `switchApp 6` (enter Settings with Matrix as context)
2. Tap Applications → Matrix → Color row once (green→white)
3. Exit to category list: `tap 30 14` × 2
4. `switchApp 4`; `get matrixColor` — verify `val == "white"` (change applied)
5. `switchApp 6` (re-enter Settings)
6. Scroll to category list if needed; `tap 137 196` (Cancel row — y = 28 + 6×26 + 1 + 13 = 210 approx)

   *(Note: Cancel row y must be confirmed against implementation; design spec: 1px separator after
   6 category rows at y=184, Cancel row at y=185..210, mid≈197)*

7. `switchApp 4`; `get matrixColor`

**Expected step 7:** `val == "green"` — snapshot restore worked.

---

### T-WIRE-CANCEL-02 — Settings cancel restores Stock ticker after keyboard entry (SERIALDBG) [SLOW]

**Preconditions:** `get stockTicker0` returns `"AAPL"`.

**Steps:**
1. Settings → Stock → Ticker 1 → keyboard → type "MSFT" → OK → wait for validation
2. `get stockTicker0` → confirm `"MSFT"` (change applied)
3. Re-enter Settings; navigate to category list; tap Cancel
4. `switchApp 7`; `get stockTicker0`

**Expected step 4:** `val == "AAPL"` — snapshot restore reverted the keyboard-entered ticker.

---

## Restart persistence (T-WIRE-PERSIST)

### T-WIRE-PERSIST-01 — Matrix color survives reboot [REBOOT] (SERIALDBG)

**Steps:**
1. Settings → Applications → Matrix → Color tap once (green→white); exit Settings
2. `reboot`; wait for boot
3. `switchApp 4`; `get matrixColor`

**Expected:** `val == "white"`.

---

### T-WIRE-PERSIST-02 — Stock tickers survive reboot [REBOOT] (SERIALDBG)

**Steps:**
1. Settings → Applications → Stock → Ticker 1 tap once; exit; note new ticker N
2. `reboot`; wait for boot
3. `switchApp 7`; `get stockTicker0`

**Expected:** `val == N` (not `"AAPL"`).

---

### T-WIRE-PERSIST-03 — Crypto currency survives reboot [REBOOT] (SERIALDBG)

**Steps:**
1. Settings → Crypto → Currency tap once (usd→eur); exit
2. `reboot`; wait; `switchApp 3`; `get cryptoCcy`

**Expected:** `val == "eur"`.

---

## Test IDs for test_plan.md

| ID | Suite | Test name | Type | Status |
|----|-------|-----------|------|--------|
| T222 | app-settings-wire-001 | Matrix color propagates on resume | integration (DUT, SERIALDBG) | planned |
| T223 | app-settings-wire-001 | Matrix tick interval matches speed | integration (DUT, SERIALDBG) | planned |
| T224 | app-settings-wire-001 | Matrix amber color renders correctly | integration (DUT, MANUAL) | planned |
| T225 | app-settings-wire-001 | Life tick interval matches speed | integration (DUT, SERIALDBG) | planned |
| T226 | app-settings-wire-001 | Life colors=mono propagates | integration (DUT, SERIALDBG) | planned |
| T227 | app-settings-wire-001 | Life mono renders single color | integration (DUT, MANUAL) | planned |
| T228 | app-settings-wire-001 | Aquarium fish count propagates | integration (DUT, SERIALDBG) | planned |
| T229 | app-settings-wire-001 | Aquarium fish count 4 shows sparse school | integration (DUT, MANUAL) | planned |
| T230 | app-settings-wire-001 | Aquarium fish count 16 shows full school | integration (DUT, MANUAL) | planned |
| T231 | app-settings-wire-001 | Aquarium speed slow/fast visually distinct | integration (DUT, MANUAL) | planned |
| T232 | app-settings-wire-001 | Stock: keyboard opens on ticker row tap | integration (DUT, MANUAL+SERIALDBG) | planned |
| T233 | app-settings-wire-001 | Stock: valid ticker validates and saves | integration (DUT, SERIALDBG, SLOW) | planned |
| T246 | app-settings-wire-001 | Stock: invalid ticker shows error screen | integration (DUT, SERIALDBG+MANUAL, SLOW) | planned |
| T247 | app-settings-wire-001 | Stock: error retry re-opens keyboard pre-filled | integration (DUT, MANUAL) | planned |
| T248 | app-settings-wire-001 | Stock: ticker change triggers immediate re-fetch | integration (DUT, SERIALDBG, SLOW) | planned |
| T234 | app-settings-wire-001 | Stock stockMode seeds subView on cold init | integration (DUT, SERIALDBG, REBOOT) | planned |
| T235 | app-settings-wire-001 | Stock resume does not override active view | integration (DUT, SERIALDBG) | planned |
| T236 | app-settings-wire-001 | Crypto coin change updates app state | integration (DUT, SERIALDBG) | planned |
| T237 | app-settings-wire-001 | Crypto currency change updates app state | integration (DUT, SERIALDBG) | planned |
| T238 | app-settings-wire-001 | dataTask fetch log includes coin IDs and currency | integration (DUT, SERIALDBG, SLOW) | planned |
| T239 | app-settings-wire-001 | Crypto display shows short name (BTC not bitcoin) | integration (DUT, MANUAL) | planned |
| T240 | app-settings-wire-001 | Crypto price < $1 uses 4 decimal places | integration (DUT, MANUAL) | planned |
| T241 | app-settings-wire-001 | Cancel restores Matrix color | integration (DUT, SERIALDBG) | planned |
| T242 | app-settings-wire-001 | Cancel restores Stock ticker | integration (DUT, SERIALDBG) | planned |
| T243 | app-settings-wire-001 | Matrix color survives reboot | integration (DUT, SERIALDBG, REBOOT) | planned |
| T244 | app-settings-wire-001 | Stock tickers survive reboot | integration (DUT, SERIALDBG, REBOOT) | planned |
| T245 | app-settings-wire-001 | Crypto currency survives reboot | integration (DUT, SERIALDBG, REBOOT) | planned |

---

## Pre-implementation blockers

The following must be resolved before VE can sign off any agent-driven test:

| Blocker | Unblocks |
|---------|---------|
| MatrixApp `dbgGet` for `matrixColor`, `matrixTickMs` | T222, T223, T241, T243 |
| LifeApp `dbgGet` for `lifeColors`, `lifeTickMs` | T225, T226 |
| AquariumApp `dbgGet` for `aquariumFish` | T228 |
| StockApp `dbgGet` for `stockTicker0`..`7` | T232, T242, T244 |
| CryptoApp `dbgGet` for `cryptoCoin0`..`5`, `cryptoCcy` | T236, T237, T245 |
| dataTask fetch log line for crypto coin IDs + currency | T238 |

Visual tests (T224, T227, T229–T231, T239, T240) have no blockers — require person at screen only.
