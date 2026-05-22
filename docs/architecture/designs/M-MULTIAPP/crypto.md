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
void runCrypto() {
  if (!modeChanged) return;   // only redraws on mode entry or explicit refresh
  // GET https://api.coingecko.com/api/v3/simple/price?ids=...&vs_currencies=usd
  //     &include_24hr_change=true
  // 9 coins: BTC ETH BNB SOL XRP ADA TRX DGE SHIB
  // Each row: symbol (left) | price (centre) | 24h change % (right, green/red)
  // Row height: 31 px. Divider line between rows.
  // Header: "CRYPTO TERMINAL" + horizontal rule at y=25.
  lastCryptoFetch = millis(); modeChanged = false;
}
```

Portrait layout (240×320):

| Element | y | notes |
|---------|---|-------|
| Header "CRYPTO TERMINAL" | 5 | font 2 |
| Horizontal rule | 25 | full width |
| Row 0 (BTC) | 32 | |
| … | +31 each | |
| Row 8 (SHIB) | 32 + 8×31 = 280 | fits in 320 |

Each row: symbol at x=5, price at x=55, change% right-aligned at x=235.

---

## Landscape adaptation

Canvas: **275×124 sub-canvas** (y:116..239) — list view suits the sub-canvas.

9 rows × 31px = 279px — does **not** fit in 124px. Options:

**Option A — Scroll / pagination**: show 4 rows at a time, auto-advance every
N seconds or on tap. Adds complexity.

**Option B — Compress row height** ← lean: 9 rows in 124px = ~13px per row.
Font 1 (6×8 px glyphs) fits symbol + price in 13px. 24h change omitted or
shown as a coloured dot (▲/▼) instead of text.

**Option C — Reduce coin count**: show top 5–6 coins only. Simpler layout,
fewer API tokens, fits in sub-canvas at 20px rows.

**Decision: open** — depends on legibility at font 1 on the physical display.
Confirm with a preview before implementing. Lean B if font 1 is readable; C
otherwise.

Regardless of option, the API endpoint, JSON parse, green/red colouring, and
`modeChanged`-gate logic port verbatim.

---

## Data fetch integration

Same `dataTask` pattern as Weather (see `app-lifecycle.md`). Fetch on mode
entry if `lastCryptoFetch == 0` or cache stale (> 60 s). Source fetches
inside `runCrypto()` on the main thread — in the shell this moves to `dataTask`
to avoid blocking.

CoinGecko free tier has rate limits. 60 s refresh is fine; do not reduce.

---

## State

```cpp
struct CryptoAppState {
    float prices[9];
    float changes[9];
    unsigned long lastCryptoFetch;
};
```

On `restoreAppState(Crypto)`: repaint list from cached prices immediately.
If `lastCryptoFetch == 0`, trigger a fetch first.

---

## Open questions

1. **Row layout in sub-canvas** — Option B vs. C; confirm with physical display
   preview. Target: price readable at arm's length.
2. **Coin selection** — source hardcodes 9 coins (BTC..SHIB). If Option C,
   which 5–6 to keep? Suggest: BTC, ETH, BNB, SOL, XRP, ADA.
3. **CoinGecko API key** — free tier unauthenticated endpoint used by source.
   May hit rate limits on shared IPs. If blocked, add `x-cg-demo-api-key`
   header via `configFile.h`.
