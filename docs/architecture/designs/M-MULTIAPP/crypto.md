# M-MULTIAPP — Crypto App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runCrypto()`

---

## Source algorithm

```cpp
// --- globals ---
unsigned long lastCryptoFetch = 0;
const char* ids[]     = {"bitcoin","ethereum","binancecoin","solana","ripple",
                          "cardano","tron","dogecoin","shiba-inu"};
const char* symbols[] = {"BTC","ETH","BNB","SOL","XRP","ADA","TRX","DGE","SHIB"};

void runCrypto() {
  if (!modeChanged) return;   // only rerenders on mode entry or explicit refresh
  HTTPClient http;
  http.begin("https://api.coingecko.com/api/v3/simple/price?"
             "ids=bitcoin,ethereum,binancecoin,solana,ripple,cardano,tron,"
             "dogecoin,shiba-inu&vs_currencies=usd&include_24hr_change=true");
  if (http.GET() == 200) {
    DynamicJsonDocument doc(4096); deserializeJson(doc, http.getString());
    tft.fillScreen(TFT_BLACK); tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0xFFE0); tft.drawString("CRYPTO TERMINAL", 10, 5, 2);
    tft.drawFastHLine(0, 25, 240, 0x07FF);
    int yPos = 32;
    for (int i = 0; i < 9; i++) {
      float price  = doc[ids[i]]["usd"];
      float change = doc[ids[i]]["usd_24h_change"];
      tft.setTextColor(0xFFFF); tft.drawString(symbols[i], 5, yPos, 2);
      tft.setTextColor(0x07FF);
      String pStr;
      if      (String(symbols[i]) == "SHIB") pStr = String(price, 9);
      else if (String(symbols[i]) == "DGE")  pStr = String(price, 4);
      else if (String(symbols[i]) == "TRX"  ||
               String(symbols[i]) == "ADA"  ||
               String(symbols[i]) == "XRP") pStr = String(price, 4);
      else pStr = (price >= 1000) ? String((int)price) : String(price, 2);
      tft.drawString(pStr, 55, yPos, 2);
      tft.setTextColor((change >= 0) ? 0x07E0 : 0xF800);
      tft.drawRightString(String(change, 1) + "%", 235, yPos, 2);
      yPos += 31;
      tft.drawFastHLine(5, yPos - 3, 230, 0x2104);
    }
    lastCryptoFetch = millis(); modeChanged = false;
  }
  http.end();
}
```

Portrait layout (240×320): header at y=5, rule at y=25, 9 rows at yPos=32
with stride 31 px. Row 8 lands at y=280 — fits in 320 portrait with 40 px spare.

---

## Landscape adaptation

Canvas: **275×124 sub-canvas** (y:116..239). Winamp chrome stays visible above.

9 rows × 31 px = 279 px >> 124 px — cannot port verbatim.

### Coin selection

Drop TRX, DOGE (DGE), SHIB — micro-cap / meme coins with low informational
value on a glanceable display. Keep the six liquid large-caps:

```cpp
static const char* ids[]     = {"bitcoin","ethereum","binancecoin",
                                 "solana","ripple","cardano"};
static const char* symbols[] = {"BTC","ETH","BNB","SOL","XRP","ADA"};
```

### Row geometry

6 rows × 17 px = 102 px. Header 14 px + rule 1 px + 102 px rows + 7 px margin = **124 px ✓**

```
x=0                        x=274
┌─────────────────────────┐  y=116
│ CRYPTO TERMINAL  (font 2)│  y=118  (TL_DATUM, x=5)
├─────────────────────────┤  y=130  (rule)
│ BTC  104235    +2.3%    │  y=132
├─────────────────────────┤  y=146
│ ETH    3412    -0.8%    │  y=149
├─────────────────────────┤  y=163
│ BNB     612    +1.1%    │  y=166
├─────────────────────────┤  y=180
│ SOL     178    +4.2%    │  y=183
├─────────────────────────┤  y=197
│ XRP    0.5123  -1.2%    │  y=200
├─────────────────────────┤  y=214
│ ADA    0.4501  +0.5%    │  y=217
└─────────────────────────┘  y=239
```

Verification:
- Row 0 top: y=132. Row 5 top: y=132+(5×17)=217.
- Row 5 text bottom: 217+14=231. Divider: 217+17-2=232 < 239. ✓
- Header text at y=118, font 2 (h≈14) → bottom y=132, rule at y=130. ✓

### Column positions

Portrait columns port unchanged — landscape canvas is 275 px (wider than portrait
240 px), so source column positions fit with room to spare:

| Column | Source x | Ours | Notes |
|--------|----------|------|-------|
| Symbol | 5 (TL) | 5 (TL) | unchanged |
| Price | 55 (TL) | 55 (TL) | unchanged |
| Change% | 235 (right-align) | 270 (right-align) | wider canvas |
| H-rule width | 230 | 270 | source: `drawFastHLine(5,…,230)`; ours: `(0,…,270)` |

Change% right-aligned at x=270 leaves 5 px margin from canvas right edge (274).

### Price formatting

Source formatting ported for our 6 coins:

```cpp
String formatPrice(const char* sym, float price) {
    if (strcmp(sym, "XRP") == 0 || strcmp(sym, "ADA") == 0)
        return String(price, 4);          // 4 dp for sub-$1 coins
    return (price >= 1000) ? String((int)price)
                           : String(price, 2);   // integer or 2 dp
}
```

TRX / SHIB / DOGE formatting rules dropped (those coins removed).

---

## Full render

Called on init and on every data refresh (fetches are infrequent at 60 s;
full repaint is simpler than partial updates and costs negligible time):

```cpp
void repaintCrypto(const CryptoAppState &s) {
    tft.fillRect(0, 116, 275, 124, TFT_BLACK);   // clear sub-canvas only
    tft.setTextDatum(TL_DATUM);

    // Header
    tft.setTextColor(0xFFE0);
    tft.drawString("CRYPTO TERMINAL", 5, 118, 2);
    tft.drawFastHLine(0, 130, 270, 0x07FF);

    // Rows
    int yPos = 132;
    for (int i = 0; i < 6; i++) {
        // Symbol
        tft.setTextColor(0xFFFF);
        tft.drawString(symbols[i], 5, yPos, 2);

        // Price
        tft.setTextColor(0x07FF);
        String pStr = (s.lastCryptoFetch == 0) ? "---"
                                                 : formatPrice(symbols[i], s.prices[i]);
        tft.drawString(pStr, 55, yPos, 2);

        // 24h change
        if (s.lastCryptoFetch == 0) {
            tft.setTextColor(0x7BEF);
            tft.drawRightString("---", 270, yPos, 2);
        } else {
            tft.setTextColor((s.changes[i] >= 0) ? 0x07E0 : 0xF800);
            tft.drawRightString(String(s.changes[i], 1) + "%", 270, yPos, 2);
        }

        yPos += 17;
        tft.drawFastHLine(0, yPos - 2, 270, 0x2104);   // divider
    }
}
```

---

## Data fetch

Source: blocking HTTP on main thread inside `runCrypto()`. In shell: moves to
`dataTask` to avoid blocking `loop()`.

API endpoint (6 coins):
```
https://api.coingecko.com/api/v3/simple/price
  ?ids=bitcoin,ethereum,binancecoin,solana,ripple,cardano
  &vs_currencies=usd
  &include_24hr_change=true
```

JSON parsing:

```cpp
// In dataTask — runs off main thread
void fetchCrypto(CryptoDataResult &out) {
    HTTPClient http;
    http.begin(CRYPTO_API_URL);
    if (http.GET() == 200) {
        JsonDocument doc;   // ArduinoJson v7 — no size arg needed
        deserializeJson(doc, http.getString());
        for (int i = 0; i < 6; i++) {
            out.prices[i]  = doc[ids[i]]["usd"];
            out.changes[i] = doc[ids[i]]["usd_24h_change"];
        }
        out.ok = true;
    }
    http.end();
}
```

Note: source uses `DynamicJsonDocument doc(4096)` (ArduinoJson v6). Shell
uses v7 `JsonDocument` (no size arg) — consistent with `updateWeather()`.
Heap usage is lower with 6 coins vs 9.

Fetch interval: 60 s. CoinGecko free tier allows 30 calls/min; one call per
60 s is well within limits. No API key required.

---

## appTick integration

No per-second update (unlike Clock/Weather). `cryptoTick` only acts when
new data arrives from `dataTask`:

```cpp
void cryptoTick(CryptoAppState &s) {
    // Trigger fetch if stale
    unsigned long now = millis();
    if (s.lastCryptoFetch == 0 || now - s.lastCryptoFetch > CRYPTO_FETCH_MS) {
        dataTask::enqueue(DATA_FETCH_CRYPTO);
        s.lastCryptoFetch = now;   // prevent re-queuing until result lands
    }
    // Check for new data
    CryptoDataResult result;
    if (dataTask::pollCrypto(&result) && result.ok) {
        for (int i = 0; i < 6; i++) {
            s.prices[i]  = result.prices[i];
            s.changes[i] = result.changes[i];
        }
        s.lastCryptoFetch = now;
        repaintCrypto(s);   // full repaint on new data
    }
}
```

---

## State

```cpp
struct CryptoAppState {
    float prices[6];
    float changes[6];
    unsigned long lastCryptoFetch;   // 0 = never fetched
};
```

`prices` / `changes` arrays sized to 6 (not 9). On `restoreAppState(Crypto)`:
call `repaintCrypto(s)` immediately — cached prices paint at once. If
`lastCryptoFetch != 0`, data is valid (shows last known values). If stale
(>60 s), `cryptoTick` triggers a refresh on the next loop iteration.

---

## Touch input

No crypto-specific touch response. Display is read-only; taps fall through
to shell navigation only.

---

## Constants

```cpp
#define CRYPTO_FETCH_MS     60000UL
#define CRYPTO_COIN_COUNT   6
#define CRYPTO_API_URL      "https://api.coingecko.com/api/v3/simple/price" \
                            "?ids=bitcoin,ethereum,binancecoin,solana,ripple,cardano" \
                            "&vs_currencies=usd&include_24hr_change=true"

// Sub-canvas geometry
#define CX_CANVAS_Y         116
#define CX_CANVAS_H         124
#define CX_HEADER_Y         118    // "CRYPTO TERMINAL" text y
#define CX_RULE_Y           130    // horizontal rule y
#define CX_ROW_START_Y      132    // first row top y
#define CX_ROW_H            17     // row stride (px)
#define CX_COL_SYMBOL       5      // symbol x (TL_DATUM)
#define CX_COL_PRICE        55     // price x (TL_DATUM)
#define CX_COL_CHANGE       270    // change% x (right-align)
#define CX_RULE_W           270    // rule and divider width
```

---

## Open questions

1. **CoinGecko rate limiting** — free unauthenticated endpoint has been known
   to return 429 on shared IP addresses. If this occurs, add a demo API key
   via `configFile.h` and set the `x-cg-demo-api-key` header. Monitor `http.GET()`
   return code in `fetchCrypto()` and log on non-200.

---

## Exit criteria

- **C1** — All 6 rows render within sub-canvas (x:0..274, y:116..239).
  Last row bottom: 217+14=231 < 239 ✓. Last divider: 232 < 239 ✓.
- **C2** — `"---"` shown for all prices and changes before first fetch.
- **C3** — After fetch, correct prices and changes displayed. BTC/ETH/BNB/SOL
  formatted as integer (if ≥1000) or 2 dp; XRP/ADA formatted to 4 dp.
- **C4** — Positive change% shown in green (0x07E0); negative in red (0xF800).
- **C5** — App switch: Spotify → Crypto → Spotify. Winamp chrome pixel-correct;
  no crypto row residue above y=116.
- **C6** — Restore: cached prices shown immediately on switch-in; fresh fetch
  triggered within one `cryptoTick()` if data is >60 s stale.
- **C7** — `http.GET()` non-200 response (e.g. 429) does not crash or freeze;
  existing cached data retained, fetch retried on next interval.
