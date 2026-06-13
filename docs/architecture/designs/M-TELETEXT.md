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

`teletekst-data.nos.nl` is served by DigiCert (same CA family as Spotify and
Open-Meteo). Exact root CA to be confirmed by `openssl s_client` against the
live endpoint. PEM added to `dataTaskCerts.h` alongside existing certs.

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

**Research question (R&D item):** which active teletext services expose a
similar wire format to NOS (`plain text, ISO-8859-1, 25×40 pre block, control
codes 0x01–0x17`)?

Candidates ranked by known API accessibility:

| Country | Service | URL pattern | Format known? |
|---------|---------|-------------|--------------|
| NL | NOS Teletekst | `teletekst-data.nos.nl/page/{N}` | ✓ confirmed |
| AT | ORF Teletext | `teletext.orf.at/…` | ✗ needs spike |
| DE | ARD Text | `ard-text.de/…` | ✗ needs spike |
| SE | SVT Text | `svt.se/svttext/…` | ✗ needs spike |
| IT | RAI Televideo | `televideo.rai.it/…` | ✗ needs spike |
| FI | YLE Teksti-TV | `yle.fi/…` | ✗ needs spike |

**If another service uses the same 25×40 pre-block format**, adding it is a
config change (URL template + country code enum). If it requires HTML scraping
or a different encoding, it may be a separate fetch path.

The `teletextCountry` settings field is reserved now; the enum expands as
services are validated.

---

## Lean / decision

→ See ADR-044.

---

## Open questions

1. **Right-strip font**: can TFT_eSPI Font1 render ▲/▼ glyphs, or do we use
   filled triangles via `fillTriangle()`?  Lean: `fillTriangle()` — no font
   dependency.
2. **History stack location**: SRAM on the app struct (10 × `uint16_t` = 20 B)
   or implicit (only prev/current). Lean: 10-entry ring.
3. **Subpage auto-advance**: cycle through subpages automatically (like a
   broadcast carousel)?  Defer to settings; off by default.
4. **Multi-country API spike**: assigned to R&D; must complete before
   `teletextCountry` setting is enabled in the Settings UI.
5. **Root CA cert**: confirm via `openssl s_client` before implementation.

---

## Exit criteria

- `preview_teletext.py` demonstrates right-strip nav + row-tap links at 3× zoom
  (UI question settled before firmware is written).
- `dataTask` extended with `FETCH_TELETEXT_PAGE`; `TeletextState` struct defined.
- `TeletextApp` renders 25×40 grid with correct text/mosaic mode switching.
- All touch zones (fast-text bar, right strip, row links) pass DUT tap tests.
- Settings rows appear in Settings → Applications → Teletext.
- `run/check` (5-gate) passes clean.
