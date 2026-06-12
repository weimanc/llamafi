# Design — M-SETTINGS-APP-WIRE: Wire Per-App Settings to App Behaviour

> Owner: Architect
> Status: accepted
> Date: 2026-06-12 (OQ1–3 resolved 2026-06-12 — human sign-off)
> Feeds: ADR-043 (accepted)
> Tracked-as: TASK-172

---

## Context / pain points

`AppSettings` in `settingsStorage.h` defines per-app preferences for five apps.
The Settings UI (`AppsSection` → `appsSection.h`) correctly reads and cycles these
fields, writes them to `g_settings`, and persists them to SPIFFS via `saveSettings()`.

**None of the apps consume `g_settings` for their per-app fields.**  
Every app ignores the stored preferences and uses hardcoded constants or defaults.

### Gap table

| App | `g_settings` field | Settings UI | App consumes | Hardcoded in |
|-----|--------------------|-------------|--------------|--------------|
| Matrix | `matrixColor` | ✅ green/white/amber | ❌ | `main.cpp:342,344` — `TFT_WHITE` / `TFT_GREEN` |
| Matrix | `matrixSpeed` | ✅ slow/normal/fast | ❌ | `main.cpp:324` — `random(5,15)` range; `MATRIX_TICK_MS=25` |
| Life   | `lifeSpeed`   | ✅ slow/normal/fast | ❌ | `main.cpp:541` — `GOL_TICK_MS=100` constant |
| Life   | `lifeColors`  | ✅ rainbow/mono | ❌ | `main.cpp:590` — always `tft.color565(r, g, 255-r)` |
| Aquarium | `aquariumFish` | ✅ 4/8/12/16 | ❌ | `aquariumApp.h:181` — `AQ_FISH_COUNT=16` compile-time |
| Aquarium | `aquariumSpeed` | ✅ slow/normal/fast | ❌ | hardcoded speed constants in aquariumApp.h |
| Crypto | `cryptoCoins[6]` | ✅ cycle pool | ❌ | `main.cpp:467` `CRYPTO_SYMBOLS[]`; `dataTaskStorage.cpp:75` `CRYPTO_IDS[]` + URL |
| Crypto | `cryptoCcy` | ✅ USD/EUR | ❌ | `dataTaskStorage.cpp:72` — `"usd"` in URL |
| Stock  | `stockTickers[8]` | ✅ cycle pool | ❌ | `main.cpp:925-928` `strcpy` hardcoded; `dataTaskStorage.cpp:79` `STOCK_TICKERS[]` |
| Stock  | `stockMode` | ✅ list/chart/heatmap | ❌ | `main.cpp:929` — always `StockSubView::List` |

---

## Goals

1. Settings UI changes to per-app preferences actually affect app behaviour.
2. Behaviour changes take effect without requiring a device restart.
3. No new cross-task data races introduced (dataTask runs on Core 0).
4. Minimal scope: no new UI, no new settings fields beyond field-size expansion for Crypto.

---

## Resolved design decisions

### D1 — When do settings take effect? → **Pull on resume**

`App::resume()` reads from `g_settings` into local state. Changes take effect the
next time the user navigates to the app. No coupling between SettingsApp and apps.

### D2 — Stock dataTask coupling → **configureStockTickers() + enqueue-time snapshot**

New `dataTask::configureStockTickers(tickers[8][8])` call on Core 1 before enqueue.
`dataTaskStorage.cpp` copies under `s_spinlock`. Thread-safe. See §Stock below.

### D3 — Crypto → **In scope; store CoinGecko word IDs directly**

`g_settings.cryptoCoins[6]` stores CoinGecko word IDs (`"bitcoin"`, `"ethereum"`, …)
instead of ticker symbols. No symbol→ID mapping table needed. IDs are used directly
for URL construction and JSON parsing. A small inline display-name table in
`CryptoApp` provides short labels for the screen (see §Crypto below).

`cryptoCoins[6][8]` → `cryptoCoins[6][16]` (expanded to fit `"binancecoin"` = 11 chars,
`"matic-network"` = 13 chars). JSON serialisation is not affected (named string fields).

### OQ1 — Aquarium fish count → **apply on resume, no full init**

`resume()` writes `g_settings.aquariumFish → _activeFish`. The pool stays max-size (16).
All fish loops use `_activeFish` instead of `AQ_FISH_COUNT`. No `init()` re-call needed.

### OQ2 — Stock re-fetch on ticker change → **immediate re-fetch on resume**

`StockApp::resume()` compares `g_settings.stockTickers` against `_s.tickers`. If any
ticker changed, re-seeds `_s.tickers`, calls `configureStockTickers()`, and enqueues a
fresh `DATA_FETCH_STOCK_QUOTE` immediately. No waiting for the normal poll interval.

### OQ3 — Crypto coin complexity → **resolved by word-ID approach**

Storing word IDs eliminates the mapping table. URL and JSON parsing use the IDs directly.
Display names are a small inline table (12 entries, lookup-only). See §Crypto below.

---

## Design: per-app wiring

### Matrix (`main.cpp`)

`MatrixApp::resume()` reads `g_settings.matrixColor` and `g_settings.matrixSpeed`.
Re-calls `initMatrixState()` to apply the new speed range immediately.

**Color** — `_headColor` / `_tailColor` instance variables:

| `matrixColor` | `_headColor` | `_tailColor` |
|--------------|-------------|-------------|
| `Green` | `TFT_WHITE` | `TFT_GREEN` (current) |
| `White` | `TFT_WHITE` | `TFT_WHITE` |
| `Amber` | `TFT_WHITE` | `0xFD20` (RGB565 ~255,165,0) |

**Speed** — `_tickMs` instance variable + speed range for `random()` in `initMatrixState()`:

| `matrixSpeed` | Speed range | `_tickMs` |
|--------------|-------------|----------|
| `Slow`   | `random(2,  8)` | 40 ms |
| `Normal` | `random(5, 15)` | 25 ms (current) |
| `Fast`   | `random(10,25)` | 15 ms |

`MATRIX_TICK_MS` compile-time constant removed; `_tickMs` used in `matrixTick()`.

---

### Life (`main.cpp`)

`LifeApp::resume()` reads `g_settings.lifeSpeed` and `g_settings.lifeColors`.

**Speed** — `_tickMs` instance variable:

| `lifeSpeed` | `_tickMs` |
|------------|----------|
| `Slow`   | 200 ms |
| `Normal` | 100 ms (current `GOL_TICK_MS`) |
| `Fast`   |  50 ms |

`GOL_TICK_MS` compile-time constant removed; `_tickMs` used in `golTick()`.

**Colors** — branch in `repaintLife()` and `stepGeneration()` on `g_settings.lifeColors`:

- `Rainbow` — current formula: `tft.color565(r, g, 255-r)` per cell (unchanged)
- `Mono` — all alive cells rendered as `0x07E0` (green); no per-cell `color565()`

---

### Aquarium (`aquariumApp.h`)

**Fish count** — `AQ_FISH_COUNT` constant remains as pool bound (16). Add instance
variable `_activeFish` initialised in `resume()` from `g_settings.aquariumFish`.
Replace all `AQ_FISH_COUNT` loop bounds with `_activeFish` (init loop, tick loop,
draw loop, crab proximity loop). The compile-time constant is only used for array
declaration — no other change needed there.

**Speed** — instance variable `_speedMult` set in `resume()` from `g_settings.aquariumSpeed`:

| `aquariumSpeed` | `_speedMult` |
|----------------|-------------|
| `Slow`   | 0.5f |
| `Normal` | 1.0f |
| `Fast`   | 2.0f |

`_speedMult` applied to fish spawn speed and delta-time in `update()`. Implementation
details delegated to Developer (exact speed parameters may differ — review `aquariumApp.h`).

---

### Stock (`main.cpp` + `dataTaskStorage.cpp` + `dataTask.h` + `appsSection.h`)

#### Ticker entry — keyboard + online validation (pivot 2026-06-12)

Ticker rows in the Stock submenu open `KeyboardWidget` (`Mode::UpperAlpha`, max 7
chars) instead of cycling from a pool. The typed symbol is validated against Yahoo
Finance before being saved. This replaces `_cycleStock()` entirely.

**UX state machine (inside `AppsSection` for the Stock submenu):**

```
  _editPhase:  None → KeyboardOpen → Validating → Error
                                            ↓
                                      Idle (save + repaint rows)
```

New private state in `AppsSection`:

```cpp
enum class StockEditPhase : uint8_t { None, Validating, Error };
StockEditPhase _editPhase    = StockEditPhase::None;
int8_t         _editRow      = -1;      // 0..6 = which ticker; 7 = default view
char           _pendingTicker[8] = {};  // ticker being validated
unsigned long  _validateStartMs  = 0;  // millis() when validation enqueued
static constexpr unsigned long VALIDATE_TIMEOUT_MS = 20000;
```

`KeyboardWidget` is the global `g_keyboard` singleton (extern from `keyboardWidget.h`).

**Ticker row tap flow:**

```
Tap Ticker N row
  └→ AppsSection::_editStockTicker(row):
       drain stale chart result (one pollStockChart call, discard)
       g_keyboard.show("Ticker N+1", g_settings.stockTickers[row],
                        KeyboardWidget::Mode::UpperAlpha, 7,
                        _onTickerSubmit, _onTickerCancel, this)
       // keyboard is now active; AppsSection::handleInput forwards events
```

**onSubmit callback:**

```cpp
static void _onTickerSubmit(const char* text, void* ctx) {
    auto* self = static_cast<AppsSection*>(ctx);
    strlcpy(self->_pendingTicker, text, 8);
    // strip any accidental spaces (UpperAlpha mode allows SPACE key)
    for (char* p = self->_pendingTicker; *p; p++) if (*p == ' ') *p = '\0';
    if (self->_pendingTicker[0] == '\0') return;   // empty after strip — ignore

    // Reuse chart-by-sym as validation oracle: D1 is the lightest request
    dataTask::enqueueStockChartBySym(self->_pendingTicker, 0 /*D1*/);
    self->_editPhase       = StockEditPhase::Validating;
    self->_validateStartMs = millis();
    self->_repaintValidating();
}
```

**Validating screen:**

```
+-----------------------------------+
|  <  Stock                         |
+-----------------------------------+
|                                   |
|  Checking TSLA...                 |
|                                   |
+-----------------------------------+
```

`< back` tap during validation cancels and returns to ticker list unchanged.

**tick() during validation:**

```cpp
void AppsSection::tick() override {
    if (_editPhase != StockEditPhase::Validating) return;
    dataTask::StockChartResult r;
    if (dataTask::pollStockChart(&r)) {
        if (r.ok && r.len > 0) {
            // Valid ticker — save and return to list
            strlcpy(g_settings.stockTickers[_editRow], _pendingTicker, 8);
            saveSettings();
            _editPhase = StockEditPhase::None;
            _editRow   = -1;
            repaint();
        } else {
            _editPhase = StockEditPhase::Error;
            _repaintError();
        }
    } else if (millis() - _validateStartMs > VALIDATE_TIMEOUT_MS) {
        _editPhase = StockEditPhase::Error;
        _repaintError();
    }
}
```

**Error screen:**

```
+-----------------------------------+
|  <  Stock                         |
+-----------------------------------+
|                                   |
|  "ZZZZ" not found.                |
|                                   |
|  Tap to try again                 |
|                                   |
+-----------------------------------+
```

Tap anywhere in content area → re-open keyboard with `_pendingTicker` pre-filled.
`< back` tap → cancel, return to ticker list unchanged.

**handleInput routing while keyboard/validating/error active:**

```cpp
SectionResult AppsSection::handleInput(TouchPhase phase, int x, int y) override {
    // Keyboard open: forward all events
    if (g_keyboard.active()) {
        g_keyboard.handleInput(phase, x, y);
        return SectionResult::Continue;
    }
    // Validating: only back tap cancels
    if (_editPhase == StockEditPhase::Validating) {
        if (phase == TouchPhase::Release && isBackTap(x, y)) {
            _editPhase = StockEditPhase::None;
            repaint();
        }
        return SectionResult::Continue;
    }
    // Error: back tap = cancel; any other tap = retry
    if (_editPhase == StockEditPhase::Error) {
        if (phase == TouchPhase::Release) {
            if (isBackTap(x, y)) {
                _editPhase = StockEditPhase::None;
                repaint();
            } else {
                _editPhase = StockEditPhase::None;
                _editStockTicker(_editRow);  // re-open keyboard with _pendingTicker
            }
        }
        return SectionResult::Continue;
    }
    // Normal flow: existing tap dispatch
    // ... (original handleInput body)
}
```

**SettingsApp::hasPendingAsync():**

SettingsApp should return `true` while stock validation is in flight so the shell-busy
indicator fires. Add to `SettingsApp`:

```cpp
bool hasPendingAsync() const override {
    return _apps.isValidating();
}
```

`AppsSection::isValidating()` returns `_editPhase == StockEditPhase::Validating`.

**Tickers — app layer (StockApp):**

`StockApp::init()` seeds `_s.tickers[i]` from `g_settings.stockTickers[i]` (removes
hardcoded `strcpy` at `main.cpp:925-928`).

`StockApp::resume()` compares `g_settings.stockTickers` against `_s.tickers`; if any
differ, re-seeds and triggers immediate re-fetch (same as before — no change from
original D1 decision).

**Tickers — dataTask layer:**

```cpp
// dataTask.h — new declaration
void configureStockTickers(const char tickers[8][8]);
```

`dataTaskStorage.cpp`: replace `static const char* STOCK_TICKERS[8]` with
`static char s_stockTickers[8][8]`. `configureStockTickers()` copies under
`s_spinlock`.

`enqueueStockChartBySym()` is **reused as the validation oracle** — no new API type.
The chart result is consumed by `AppsSection::tick()` during validation; StockApp is
suspended and does not compete for the result.

**Default view:**

`StockApp::init()` seeds `_s.subView` from `g_settings.stockMode`. `resume()` does
**not** re-seed — active session view is preserved. The setting applies on cold start.

---

### Crypto (`main.cpp` + `dataTaskStorage.cpp` + `dataTask.h`)

**Storage schema change:**

`char cryptoCoins[6][8]` → `char cryptoCoins[6][16]` in `AppSettings`.
Default values (in `SettingsStorage::load()`) changed from symbols to CoinGecko IDs:

```cpp
// defaults
{"bitcoin","ethereum","binancecoin","solana","ripple","cardano"}
```

**Cycling pool** in `appsSection.h` `_cycleCrypto()`:

```cpp
static const char* kPool[] = {
    "bitcoin","ethereum","binancecoin","solana","ripple",
    "dogecoin","cardano","avalanche-2","matic-network","chainlink",
    "polkadot","litecoin"
};
```

The settings row label/value display uses `cgIdToDisplay()` (see below) so the user
sees "BTC", "ETH", etc. in the Settings UI.

**Display names** — inline lookup in `CryptoApp` (and shared by `AppsSection`):

```cpp
static const char* cgIdToDisplay(const char* id) {
    static const struct { const char* id; const char* disp; } kMap[] = {
        {"bitcoin","BTC"}, {"ethereum","ETH"}, {"binancecoin","BNB"},
        {"solana","SOL"}, {"ripple","XRP"}, {"dogecoin","DOGE"},
        {"cardano","ADA"}, {"avalanche-2","AVAX"}, {"matic-network","MATIC"},
        {"chainlink","LINK"}, {"polkadot","DOT"}, {"litecoin","LTC"},
    };
    for (const auto& e : kMap)
        if (strcmp(e.id, id) == 0) return e.disp;
    return id; // unknown coin: show raw ID (TFT_eSPI clips at column width)
}
```

This function is used:
- `CryptoApp::repaintCrypto()` left column: `cgIdToDisplay(g_settings.cryptoCoins[i])`
- `AppsSection::_repaintCrypto()` and `_cycleCrypto()` value column

**Price formatting** — remove per-symbol `strcmp` heuristic; replace with magnitude check:

```cpp
static String formatCryptoPrice(float price) {
    if (price < 1.0f)   return String(price, 4);
    if (price < 1000.0f) return String(price, 2);
    return String((int)price);
}
```

**dataTask — configureCrypto():**

```cpp
// dataTask.h — new
void configureCrypto(const char coins[6][16], const char ccy[4]);
```

`dataTaskStorage.cpp`: `s_cryptoIds[6][16]` and `s_cryptoCcy[4]` runtime arrays,
protected by `s_spinlock`. `configureCrypto()` copies under lock.

`fetchCrypto()` builds URL dynamically:

```cpp
String url = "https://api.coingecko.com/api/v3/simple/price?ids=";
for (int i = 0; i < 6; i++) {
    if (i > 0) url += ',';
    url += s_cryptoIds[i];
}
url += "&vs_currencies=";
url += s_cryptoCcy;   // "usd" or "eur" (stored lowercase)
```

JSON parsing uses `s_cryptoIds[i]` as the key and `s_cryptoCcy` for the currency field:

```cpp
r.prices[i]  = doc[s_cryptoIds[i]][s_cryptoCcy].as<float>();
r.changes[i] = doc[s_cryptoIds[i]][String(s_cryptoCcy) + "_24h_change"].as<float>();
```

`cryptoCcy` stored as uppercase ("USD"/"EUR") in `g_settings`; `configureCrypto()`
lowercases on copy (or store lowercase — Developer to decide).

**CryptoApp::init() and resume()** both call `dataTask::configureCrypto()` with
current `g_settings` values before enqueuing `DATA_FETCH_CRYPTO`.

---

## Exit criteria

- **E1** Matrix color: all three values (green, white, amber) render correctly after
  Settings change and next app activation.
- **E2** Matrix speed: slow/normal/fast produce visually distinct speeds.
- **E3** Life speed: slow/normal/fast produce visually distinct generation rates.
- **E4** Life colors: mono shows single-color cells; rainbow unchanged.
- **E5** Aquarium fish count: Settings 4 → ≈4 fish active; 16 → full school.
  Takes effect on next activation (no restart required).
- **E6** Aquarium speed: slow/normal/fast produce visually distinct swim speeds.
- **E7** Stock tickers: change ticker 1 to TSLA in Settings → StockApp shows TSLA
  and fetches fresh price immediately on return.
- **E8** Stock default view: restart with `stockMode=chart` → StockApp opens in chart.
- **E9** Crypto coins: change coin 1 to "dogecoin" in Settings → CryptoApp shows
  DOGE row with live price on next fetch.
- **E10** Crypto currency: change to EUR → prices fetched and displayed in EUR.
- **E11** All other settings (LED, display, time, WiFi) unaffected.
- **E12** Cancel/restore path correct: change Matrix color, tap Cancel → color reverts.
- **E13** Settings survive restart: all per-app settings loaded correctly from SPIFFS.

---

## Work items (for TASK-172)

| ID | Area | Change | File(s) |
|----|------|--------|---------|
| W1 | Matrix | `resume()` seeds `_headColor`/`_tailColor`/`_tickMs`; `initMatrixState()` uses speed range | `main.cpp` |
| W2 | Life | `resume()` seeds `_tickMs`/color mode; `golTick()` uses `_tickMs`; color branch in render | `main.cpp` |
| W3 | Aquarium | `resume()` seeds `_activeFish`/`_speedMult`; loops use `_activeFish` | `aquariumApp.h` |
| W4 | Stock-settings | Replace `_cycleStock()` with keyboard+validation; `StockEditPhase` state machine; `tick()` polls chart; error screen with retry | `appsSection.h` |
| W4b | Stock-app | `init()`/`resume()` seed from `g_settings`; resume re-fetches on change; `SettingsApp::hasPendingAsync()` delegates to `_apps.isValidating()` | `main.cpp` |
| W5 | Stock-dataTask | `configureStockTickers()` + `s_stockTickers` runtime array under spinlock | `dataTask.h`, `dataTaskStorage.cpp` |
| W6 | Crypto-storage | Expand `cryptoCoins[6][8]→[16]`; defaults to word IDs; `SettingsStorage::load/save` | `settingsStorage.h`, `settingsStorageStorage.cpp` |
| W7 | Crypto-app | `cgIdToDisplay()` helper; `repaintCrypto()` uses it; `init()`/`resume()` call `configureCrypto()` | `main.cpp` |
| W8 | Crypto-settings | `_cycleCrypto()` pool uses word IDs; value column uses `cgIdToDisplay()` | `appsSection.h` |
| W9 | Crypto-dataTask | `configureCrypto()` + `s_cryptoIds`/`s_cryptoCcy`; dynamic URL; JSON key from ID | `dataTask.h`, `dataTaskStorage.cpp` |

---

## ADR-043

```
### ADR-043 — [2026-06-12] — Per-app settings wiring: pull-on-resume + word-ID crypto

Status: accepted
Context: AppSettings fields for Matrix, Life, Aquarium, Stock, and Crypto are persisted
  by the Settings UI but ignored by the apps and dataTask fetch layer.
Decision:
  (1) All five apps adopt pull-on-resume: App::resume() reads g_settings into local
      behavioural state. Changes take effect on next app activation.
  (2) Stock: new dataTask::configureStockTickers() pushes an 8-ticker snapshot from
      Core 1 to Core 0 under the existing s_spinlock before each quote enqueue.
      StockApp::resume() triggers an immediate re-fetch when tickers changed.
  (3) Crypto: g_settings.cryptoCoins stores CoinGecko word IDs directly. Field size
      expanded to [6][16]. Dynamic URL and JSON parsing use IDs. A 12-entry inline
      display-name table (cgIdToDisplay) provides short labels for the screen.
      New dataTask::configureCrypto() mirrors the Stock pattern.
  (4) Aquarium fish count: runtime _activeFish counter; static pool stays max-size (16).
Consequences: Settings changes take effect on next activation without restart.
  No mapping-table indirection for Crypto (IDs are the API keys). dataTask API gains
  two new configure functions, both protected by the existing spinlock.
  AppSettings struct size increases by ~48 bytes (cryptoCoins field expansion).
```
