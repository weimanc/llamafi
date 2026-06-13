# Design — M-TELETEXT: NOS Teletekst App

> Owner: Architect
> Status: draft
> Date: 2026-06-13
> Feeds: ADR-044
> Tracked-as: (TBD — pending PM scheduling)

---

## Context / pain points

The multiapp shell has 9 apps; the taskbar scrolls to accommodate more. A live
teletext reader was identified as a natural fit: low network cost (~1.1 KB per
fetch), no JSON parsing, content that refreshes on a human-readable cadence, and
a visual style distinct from every other app.

A proof-of-concept was fully validated on-host:
- NOS API reverse-engineered (`teletekst-data.nos.nl/page/{N}`, ISO-8859-1,
  25×40 teletext grid in a `<pre>` block, no `.json` suffix).
- Teletext control codes decoded: text mode (0x01–0x07) vs mosaic graphics mode
  (0x10–0x17); mosaic 2×3 pixel patterns correctly derived from the byte value.
- Navigation metadata parsed: `pn=p_/n_/ns/ps` (prev/next page and subpage),
  `ftl=` (4 fast-text link targets + bottom-row coloured labels).
- Preview tool `app/tools/preview_teletext.py` renders the full 320×240 canvas
  including taskbar, at 1×/2×/3× zoom, with live page navigation.

Open design questions being iterated in the preview tool:
1. Right-margin strip usage (35px between grid and taskbar).
2. Inline hyperlink tap model for index pages.
3. Settings exposure.
4. Multi-country future path.

---

## Goals

- 10th app in `appRegistry.h` (slot after Aquarium); appears in Settings → Applications.
- Live NOS Teletekst page fetch + render on the 275×240 app canvas.
- Touch navigation: fast-text buttons, right-strip page nav, inline row links.
- Settings: default page, poll interval, (future) country/service.
- Architecture: slot into existing `dataTask` pattern — no new FreeRTOS task.

---

## Canvas geometry

```
┌──────────────────────────────────────────────────────┬─────────┐
│  Teletext grid  40 cols × 6 px = 240 px wide         │         │
│  25 rows × 8 px = 200 px tall                        │ taskbar │
│                                         right strip   │  45 px  │
│                                         ← 35 px →    │         │
├──────────────────────────────────────────────────────┤         │
│  Fast-text nav bar  40 px tall  (4 colour buttons)   │         │
└──────────────────────────────────────────────────────┴─────────┘
         275 px (APP_W)                                  45 px
                        320 px (SCREEN_W)
```

**Cell size**: 6 × 8 px. All 40 columns fit in 240 px; 35 px right strip is spare.

---

## Design space

### DS-1: Right-strip usage (35 × 200 px)

**Option A — Page nav strip (chosen lean)**

```
┌──────┐  y=0
│  ▲   │  subpage up (if exists)  — tap zone ~50 px tall
├──────┤  y=50
│ 101  │  current page number (3 chars, centred)
├──────┤  y=90
│  ◄   │  prev page — tap zone ~30 px
├──────┤  y=120
│  ►   │  next page — tap zone ~30 px
├──────┤  y=150
│  ▼   │  subpage down (if exists) — tap zone ~50 px tall
└──────┘  y=200
```

Renders as simple coloured rects with white arrow glyphs.
Active (has target) = bright; inactive = dim grey.

**Option B — Blank / black gutter**: simplest, wastes affordance.

**Option C — Subpage carousel only**: only show ▲/▼ for subpages; use fast-text
buttons for prev/next. Loses discoverability.

**Lean: Option A.** 35 px is enough for small glyphs. Gives page number
at a glance and four touch targets without obscuring content.

---

### DS-2: Inline hyperlinks (content-area tap)

Index pages (101, 102, 601, etc.) have a consistent layout:
```
 Headline text.............................. NNN
```
The 3-digit page ref occupies columns ~36–38 on headline rows, preceded by dots.

**Option A — Row-tap hyperlink (chosen lean)**

- On tap in the grid area: compute `row = y / CHAR_H`.
- Scan columns 35–39 of that row for 3 contiguous digit characters.
- If found: navigate to that page (push current page onto history stack).
- No visible underline — the colour highlight (cyan text) serves as the cue.

**Option B — Explicit highlighted link boxes**: draw a coloured rect under
detected link rows. Adds clutter; not authentic to teletext style.

**Option C — No inline links**: rely on fast-text only. Loses the primary
navigation affordance of index pages.

**Lean: Option A.** Tap target is an 8 px tall row — manageable on the CYD
resistive touch. History stack (depth ≤ 10) enables back navigation.
Debounce to 300 ms to avoid double-fires on resistive touch.

---

### DS-3: Fetch architecture

**Option A — Slot into dataTask (chosen lean)**

Add `FETCH_TELETEXT_PAGE` to the `dataTask::FetchType` enum. The task body
handles the request, stack-allocates `WiFiClientSecure + HTTPClient`, parses
the 1.1 KB response, and writes the result into a spinlock-guarded struct
(`TeletextState`). `TeletextApp::tick()` polls `dataTask::pollTeletext()`.

Matches the existing weather/crypto/stock pattern exactly. No new task.

**Option B — New dedicated task**: unnecessary; response is 1.1 KB with a 30–
120 s cadence. Task overhead not justified.

**Lean: Option A.**

---

### DS-4: TLS root CA

**Confirmed** (`openssl s_client`, 2026-06-13).

Chain: leaf → Sectigo Public Server Authentication CA DV R36 (intermediate) →
Sectigo Public Server Authentication Root R46 (cross-signed intermediate) →
**USERTrust RSA Certification Authority** (self-signed root, valid 2010–2038).

This is **not** DigiCert or ISRG. Add `TELETEXT_NOS_ROOT_CA` (USERTrust RSA
Certification Authority PEM) to `dataTaskCerts.h`. The same root also signs
`comodoca.com` and other Sectigo customers — it may serve future country entries
without a separate cert add.

---

### DS-5: Settings exposure

| Setting | Type | Default | Notes |
|---------|------|---------|-------|
| `teletextPage` | `uint16_t` | 101 | Starting page on app launch |
| `teletextPollSecs` | `uint8_t` | 60 | Refresh interval: 30/60/120 s |
| `teletextCountry` | `uint8_t` enum | 0 (NOS/NL) | Reserved; only NOS implemented initially |

Settings UI: two rows in the Teletext sub-section of Settings → Applications.
- **Start page**: tap to cycle preset pages (News 101 / Sport 601 / Weather 702 / Football 800).
- **Refresh**: tap to cycle 30 s / 60 s / 120 s.
- **Country**: greyed out / "NL (NOS)" until multi-country is implemented.

`TeletextApp::resume()` reads these three fields from `g_settings` and applies
them immediately — consistent with the pull-on-resume model (ADR-043).

---

### DS-6: Multi-country future path

**R&D spike completed 2026-06-13.** None of the five candidate services is a
drop-in NOS clone. Findings:

| Country | Service | Format | Compat | Notes |
|---------|---------|--------|--------|-------|
| NL | NOS Teletekst | `<pre>` 25×40, ISO-8859-1, control codes 0x01–0x17 | ✓ native | Confirmed; ~1.1 KB/page |
| AT | ORF Teletext | Vue.js SPA — no data without JS | ✗ blocked | No public JSON API found; needs reverse-engineered XHR |
| DE | ARD Text | HTML `div.ardtext_classic`, CSS color classes, UTF-8 | ✗ scrape | CDN blocks direct fetch; no control codes |
| SE | SVT Text | JSON via `texttv.nu` API; `content_plain` ~1–2 KB, 23 rows, UTF-8 | ~ JSON | 25–30 KB total response; ESP32 must stream-discard or extract field only |
| IT | RAI Televideo | PNG image only (720×456 px) | ✗ hard no | No text path without OCR |
| FI | YLE Teksti-TV | `<pre>` on web page BUT 150–200 KB page; JSON API needs `app_id`+`app_key` | ~ gated | JSON API has `text` content type at comparable size; requires key registration |

**Implications for `teletextCountry` enum:**

- `0 = NOS (NL)` — implemented in MVP, native `<pre>` parser.
- `1 = SVT (SE)` — feasible as a second entry; requires a separate JSON fetch path
  (texttv.nu `GET /api/get/{N}?includePlainTextContent=1`, extract `content_plain`
  key). UTF-8 — no control codes; colour-stripping not needed.
- ORF / ARD — blocked unless a host proxy normalises them to the NOS format.
- RAI — incompatible.
- YLE — possible via API key; defer until key is obtained.

The `teletextCountry` settings field remains reserved; enable SVT entry in the
UI once the JSON fetch path is implemented and tested.

---

## Lean / decision

→ See ADR-044.

---

## Open questions

All resolved 2026-06-13.

1. **Right-strip font** ✓ — Font1/GLCD covers ASCII 0x00–0xFF but has **no
   ▲/▼ glyphs** (0x1E/0x1F render diamond patterns). **Decision: `fillTriangle()`**
   — confirmed via font table inspection in
   `Spotify-Diy-Thing/.pio/libdeps/…/TFT_eSPI/Fonts/glcdfont.c`. No font
   dependency.

2. **History stack location** ✓ — 10 × `uint16_t` (20 B) on `TeletextAppState`
   as a member array. Consistent with all existing apps (static per-app state
   structs). 20 B is trivial vs LifeAppState (2,651 B) or StockAppState (~1 KB).

3. **Subpage auto-advance** ✓ — Off by default; add `teletextAutoAdvance` bool
   to Settings. No firmware action needed before MVP.

4. **Multi-country API spike** ✓ — See DS-6 above. SVT (SE) via texttv.nu JSON
   is the viable second entry; ORF/ARD blocked; RAI incompatible; YLE gated.
   `teletextCountry` stays greyed out until SVT fetch path lands.

5. **Root CA cert** ✓ — **USERTrust RSA Certification Authority** (self-signed,
   2010–2038). See DS-4. Add `TELETEXT_NOS_ROOT_CA` to `dataTaskCerts.h` before
   first DUT flash.

---

## Exit criteria

- `preview_teletext.py` demonstrates right-strip nav + row-tap links at 3× zoom
  (UI question settled before firmware is written).
- `dataTask` extended with `FETCH_TELETEXT_PAGE`; `TeletextState` struct defined.
- `TeletextApp` renders 25×40 grid with correct text/mosaic mode switching.
- All touch zones (fast-text bar, right strip, row links) pass DUT tap tests.
- Settings rows appear in Settings → Applications → Teletext.
- `run/check` (5-gate) passes clean.
