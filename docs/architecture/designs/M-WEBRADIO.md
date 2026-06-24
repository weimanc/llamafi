# Design — M-WEBRADIO: International Web Radio App

> Owner: Architect  
> Status: design draft (R&D complete — EXP-005)  
> Date: 2026-06-13  
> Tracked-as: (TBD — pending PM scheduling)

---

## Context

Add an international web radio app to the multiapp shell. Reuse the Winamp
UI frame; browse stations by country via radio-browser.info; toggle between
Spotify and radio via the existing taskbar. R&D spike EXP-005 confirmed all
four feasibility questions (see below). Hardware path validated by CYD upstream
HelloRadio example; this design formalises it into the multiapp architecture.

The CYD (ESP32-2432S028R) has an on-board SC8002B audio amplifier wired to a
SPEAK header — an external 8 Ω speaker is required. Audio is 8-bit mono DAC via
GPIO26; quality is acceptable for web radio.

---

## Goals

- 11th app in `appRegistry.h` (slot after Teletext); **no taskbar slot** — entered
  via the Winamp eject button, not taskbar scroll.
- Browse and play internet radio stations, categorised by country.
- Winamp skin reused; controls remapped to radio semantics.
- Country/region settable in Settings → Applications → Web Radio.
- Station list fetched from **radio-browser.info** REST API (MP3 only).
- Toggle Spotify ↔ Web Radio via the **eject button** (screen pos 136, 89).

---

## Non-goals

- EQ / crossfader / recording.
- AAC or OGG stream support (MP3 first cut only).
- Simultaneous Spotify + radio playback.
- Saving favourite stations (post-MVP).

---

## App lifecycle

```
// Entry: eject button tap in Spotify/Winamp context
hitTestEject(x, y) → ACT_EJECT → switchApp(AppId::WebRadio)

switchApp(AppId::WebRadio)
  → appTick() calls webRadioTick()
       first tick: trigger dataTask fetch of station list for selected country
       on list ready: render playlist view
       on user selects station: audio.connecttohost(url)

// Exit: eject button tap in WebRadio context
hitTestEject(x, y) → ACT_EJECT → switchApp(AppId::Spotify)

switchApp(AppId::Spotify)  [or any other app via taskbar]
  → webRadioSuspend(): audio.stopSong(); release I2S-DAC handle
```

When WebRadio is not active, the audio task is suspended and Spotify polling
resumes normally. Modes are mutually exclusive via `switchApp`.

WebRadio is **not reachable via taskbar scroll** — the Winamp/Spotify taskbar
slot stays as-is. The eject button is the sole entry/exit point.

---

## Eject button toggle

The Winamp eject button is the sole entry/exit point for WebRadio.

### Current state (pre-M-WEBRADIO)

`bake_skin.py` pastes the eject sprite statically onto `MAIN_BG` at bake time
(line ~768: `main_bg.paste(eject, (136, 89))`). No touch handler exists. The
bake comment: *"eject has no Spotify equivalent"* — now it does.

### Required changes

**`bake_skin.py`:**
- Remove the static eject paste from `MAIN_BG` (currently line ~768).
- Emit two UV-offset constants into `skin_layout.h` — **not** separate pixel
  arrays; both are crops of the existing `SKIN_CBUTTONS` atlas:

```c
// In skin_layout.h (emitted by bake_skin.py):
#define SKIN_EJECT_N_X  114   // UV x in SKIN_CBUTTONS, normal state
#define SKIN_EJECT_N_Y    0
#define SKIN_EJECT_P_X  114   // UV x in SKIN_CBUTTONS, pressed state
#define SKIN_EJECT_P_Y   18   // bottom row (SKIN_CBUTTONS_H=36, 2×18 rows)
#define SKIN_EJECT_W     22
#define SKIN_EJECT_H     16
```

Firmware blits via `tft.pushImage(originX+136, originY+89, SKIN_EJECT_W,
SKIN_EJECT_H, SKIN_CBUTTONS + SKIN_EJECT_N_Y*SKIN_CBUTTONS_W + SKIN_EJECT_N_X)`.

**`winampDisplay.h`:**
- Add `hitTestEject(sx, sy)` at `(originX+136, originY+89, 22, 16)`, mirroring
  `hitTestLogo()`. Fires in both Spotify and WebRadio contexts — both use the
  same `WinampDisplay::handleWinampInput` path since WebRadio reuses the Winamp
  skin frame.
- On hit: blit pressed-state crop of `SKIN_CBUTTONS`, set 100 ms cooldown,
  populate `lastTouchResult` as `{ "EJECT", -1, "EJECT", 0, -1, false }`.
- Add `"EJECT"` to the action-string enum comment at line 537.

**`main.cpp`:**

```cpp
// In Spotify app tick / input handler:
case ACT_EJECT:
    switchApp(AppId::WebRadio);
    break;

// In WebRadio app tick / input handler:
case ACT_EJECT:
    switchApp(AppId::Spotify);
    break;
```

**`appRegistry.h`:**
- Add `APP_X(WebRadio, 'R', 0)` — `AppId` entry exists, but the app is **not**
  added to `gen_taskbar_icons.py`'s `APPS` list and carries no taskbar icon.

### Sprite geometry

| Constant | Source UV | Size | Screen pos |
|----------|-----------|------|-----------|
| `SKIN_EJECT_N` | `CBUTTONS.BMP (114, 0, 22, 16)` | 22×16 | `(136, 89)` |
| `SKIN_EJECT_P` | `CBUTTONS.BMP (114, 18, 22, 16)` | 22×16 | `(136, 89)` |

The pressed-state blit is shown for one frame on tap, then `repaintChrome()`
restores the normal state on the next display tick.

---

## Canvas layout (275 × 240 px)

Winamp main-unit geometry reused with adapted semantics:

```
┌──────────────────────────────────────────────────────┬─────────┐
│  [⏮]  [⏹] [▶/⏸]  [⏭]   EQ  PL        clkwdgt      │         │
│  ────────────────────────────────────────────────    │taskbar  │
│  Station name (scrolling marquee)                    │  45 px  │
│  ICY StreamTitle (artist — title)                    │         │
│  [buffer bar replaces seek bar]   bitrate  kbps      │         │
│  ════════════════════════════════════════════════    │         │
│  ▌▌▌▌▌▌▌  VU meter (getVUlevel())  ▌▌▌▌▌▌▌           │         │
│  ────────────────────────────────────────────────    │         │
│  [PL panel: station list]         [▐ scroll rail ▌]  │         │
└──────────────────────────────────────────────────────┴─────────┘
```

> **Architect note (2026-06-14):** The `[COUNTRY]` badge shown in earlier drafts
> has no counterpart in `winampDisplay.h` and would overwrite Winamp skin chrome
> at that position. It is **removed from the design**. The active country is
> surfaced via the Settings entry point only — not via any overlay on the main
> window or PLEDIT title bar (see §Firmware rendering notes).

**Control mapping**

| Winamp control | Spotify meaning | Web Radio meaning |
|----------------|-----------------|-------------------|
| ⏮ prev         | prev track       | prev station in list |
| ⏭ next         | next track       | next station in list |
| ⏹ stop         | stop             | stop stream / disconnect |
| ▶/⏸ play/pause | play/pause       | connect / pause |
| seek bar       | track position   | stream buffer health (`inBufferFilled()`) |
| bitrate area   | kbps             | stream bitrate (from `evt_bitrate`) |
| title line 1   | "Artist — Title" | station name (`evt_name`) |
| title line 2   | album            | ICY `StreamTitle` (`evt_streamtitle`) |
| PL panel       | playlist         | station list for selected country |

---

## Firmware rendering notes

Authoritative contract between `preview_webradio.py` and firmware implementors.
All constants from `app/gen/skin_layout.h`; all rendering from
`app/src/winamp/winampDisplay.h`.

### a. POSBAR ("seek bar" / "buffer bar")

The POSBAR is rendered in two sprite blits — **no fill rectangle is used**:

```cpp
// repaintChrome() — always draw background first:
blitSprite(originX + POSBAR_X, originY + POSBAR_Y,
           SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_BG);      // full 248×10 groove

// then draw thumb at position (when thumb has been set):
blitSprite(originX + POSBAR_X + lastThumbPx, originY + POSBAR_Y,
           SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N); // 29×10 thumb sprite
```

| Constant | Value | Role |
|----------|-------|------|
| `POSBAR_X` | 16 | Left edge of groove (window coords) |
| `POSBAR_Y` | 72 | Top edge of groove |
| `POSBAR_BG` | `{0, 0, 248, 10}` | Full groove sprite (SkinUV into SKIN_POSBAR) |
| `POSBAR_THUMB_N` | `{248, 0, 29, 10}` | Normal-state thumb sprite |
| Thumb travel | `POSBAR_BG.w − POSBAR_THUMB_N.w = 219 px` | |

**For WebRadio:** `inBufferFilled()` (0–100 %) drives `thumb_px` exactly as
`displayTrackProgress()` drives it for Spotify:

```cpp
const int travel = POSBAR_BG.w - POSBAR_THUMB_N.w;  // 219
int thumb_px = map(bufferHealthPct, 0, 100, 0, travel);
// then blitSprite at POSBAR_X + thumb_px as above
```

The groove background is NOT partially filled — only the thumb position changes.
A buffer at 100 % shows the thumb at the rightmost position; an empty buffer
shows it at the leftmost position (or hidden if `thumb_px < 0`).

---

### b. PLEDIT title bar

Line 1112 of `drawPlaylist()`:

```cpp
tft.pushImage(originX, PLEDIT_Y, SKIN_PLEDIT_BG_W, PLEDIT_TITLE_H, SKIN_PLEDIT_BG);
```

This blits the **top `PLEDIT_TITLE_H` (20) rows of the `SKIN_PLEDIT_BG` atlas** —
pure skin chrome, pixel-perfect. **No text is drawn over the title bar** in any
code path. The firmware never calls `drawString` or any glyph blit in this region.

Implication for WebRadio: the active country name cannot be displayed on the
PLEDIT title bar. Country is surfaced via Settings only.

| Constant | Value |
|----------|-------|
| `PLEDIT_Y` | 116 — top of the entire PLEDIT frame |
| `PLEDIT_TITLE_H` | 20 — rows consumed by the title bar blit |
| `SKIN_PLEDIT_BG_W` | 275 — atlas width (= PLEDIT_W) |
| Health-inactive variant | `SKIN_PLEDIT_TITLE_INACTIVE` (275×20) blitted instead when `!isHealthy()` |

---

### c. PLEDIT scrollbar thumb

See §PLEDIT scrollbar below for full geometry. Key rendering call (line 1129):

```cpp
tft.pushImage(thumb_x, thumb_y,
              SKIN_PLEDIT_THUMB_W, SKIN_PLEDIT_THUMB_H,
              SKIN_PLEDIT_THUMB, PLEDIT_TRANSPARENT_RGB565);
```

- `thumb_x = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + PLEDIT_THUMB_X_INSET`
  = 0 + 12 + 244 + 5 = **261 px** (absolute screen x)
- `thumb_y = PLEDIT_ROWS_Y + scrollOffset * travel / max(1, count − PLEDIT_ROW_COUNT)`
- Transparent colour key: `PLEDIT_TRANSPARENT_RGB565 = 0x063F` (RGB 0, 198, 255)
- Only drawn when `count > PLEDIT_ROW_COUNT` (i.e. more stations than visible rows)

---

### d. Country badge

**Removed from design.** There is no firmware rendering for a country badge and
no atlas slot for one. Adding an overlay at any main-window position would
overwrite baked Winamp skin chrome. Country is surfaced only via the Settings
entry point (Settings → Applications → Web Radio → Country).

---

### e. PLEDIT bottom bar

Line 1200-1201 of `drawPlaylist()`:

```cpp
const uint16_t *bottom = SKIN_PLEDIT_BG + (uint32_t)SKIN_PLEDIT_BG_W * PLEDIT_TITLE_H;
tft.pushImage(originX, PLEDIT_BOTTOM_Y, SKIN_PLEDIT_BG_W, PLEDIT_BOTTOM_H, bottom);
```

The bottom bar is the **second band of the `SKIN_PLEDIT_BG` atlas**, starting at
row `PLEDIT_TITLE_H` (20). It is not a separate sprite — it is an offset pointer
into the same array.

| Constant | Value |
|----------|-------|
| `PLEDIT_BOTTOM_Y` | 201 — top of bottom bar (screen px) |
| `PLEDIT_BOTTOM_H` | 38 — height of bottom bar |
| Atlas offset | `SKIN_PLEDIT_BG + SKIN_PLEDIT_BG_W * PLEDIT_TITLE_H` |
| `SKIN_PLEDIT_BG_H` | 58 = `PLEDIT_TITLE_H (20) + PLEDIT_BOTTOM_H (38)` |

Total playlist time is rendered on top of the bottom bar using the Winamp LED
bitmap font (`SKIN_FONT` / `SKIN_GLYPH`), left-aligned at
`(originX + 127 + GLYPH_W, PLEDIT_BOTTOM_Y + 10)`.

### f. Live kbps display

The kbps and kHz fields at `(110, 43)` and `(156, 43)` on `MAIN_BG` are baked
statically by `bake_skin.py` as `"192"` / `"44"` (ADR-014).  WebRadio is the
**first app to carry a live bitrate value** (`evt_bitrate` callback), so it
must overdraw those baked digits after `blitMainBackground()`.

**Erase + redraw contract:**

1. Fill the kbps zone `(110, 43, 18, 6)` with solid background colour
   `MAIN_BG_DARK` (`0x0000` in RGB565 — the pixel colour of that region in
   `MAIN.BMP`).  Three digits × 6 px glyph pitch = 18 px wide.
2. Render new digits left-aligned at `(110, 43)` using `SKIN_GLYPH` (the
   TEXT.BMP sprite already baked into `skin_layout.h`).  One digit per
   `drawGlyph(x, 43, ch)` call, advancing `x` by `GLYPH_W + 1 = 6` px.
3. Update on `evt_bitrate` only — not on every display tick.  Cache last
   rendered value; skip redraw if unchanged.

The kHz field (`"44"` at `(156, 43)`) stays baked for MVP.  Most MP3 streams
are 44.1 kHz; `evt_info` carries sample rate if live kHz becomes wanted later.

`MONO/STEREO` indicator stays baked as `STEREO` for MVP (the SC8002B path is
mono but the indicator requires re-introducing the MONOSTER atlas — not worth
it for this milestone).

---

## PLEDIT scrollbar — exact firmware behaviour

> Source: `winampDisplay.h` `drawPlaylist()` lines 1114-1131,
> `drawScrollThumbOnly()` lines 1040-1056.  Sprite source: `bake_skin.py`
> lines 339-348.

### Geometry (all values from `skin_layout.h`)

| Constant | Value | Meaning |
|----------|-------|---------|
| `PLEDIT_ROWS_Y` | 136 | Top of rows area (screen px) |
| `PLEDIT_ROW_COUNT` | 5 | Visible rows |
| `PLEDIT_ROW_H` | 13 | Row height px |
| `PLEDIT_CONTENT_X` | 12 | Left frame rail width |
| `PLEDIT_CONTENT_W` | 244 | Content width between rails |
| `PLEDIT_SIDE_RIGHT_W` | 19 | Right rail tile width |
| `PLEDIT_SIDE_H_SRC` | 29 | Right rail tile height (tiled vertically) |
| `SKIN_PLEDIT_THUMB_W` | 9 | Scrollbar thumb width |
| `SKIN_PLEDIT_THUMB_H` | 17 | Scrollbar thumb height |
| `PLEDIT_THUMB_X_INSET` | 5 | Thumb x offset inside rail |

**Derived:**
- `track_h = 5 × 13 = 65 px` (rows area height)
- `travel = track_h − THUMB_H = 65 − 17 = 48 px` (thumb travel range)
- `thumb_x (abs) = PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + PLEDIT_THUMB_X_INSET = 12 + 244 + 5 = 261`

### Sprite sources (from PLEDIT.BMP in the .wsz)

| Sprite | BMP crop | Size |
|--------|----------|------|
| Right rail tile | `(32, 42, 51, 71)` | 19 × 29 |
| Scrollbar thumb | `(52, 54, 61, 71)` | 9 × 17 |

Transparent key: **RGB (0, 198, 255)** / RGB565 `0x063F` (standard Winamp skin
transparency colour). Pixels matching this key must be masked out when blitting
the thumb — the firmware passes it as the colour-key argument to `pushImage`.

### Thumb position formula

```cpp
// from drawPlaylist() line 1125-1128
constexpr int travel = track_h - SKIN_PLEDIT_THUMB_H;   // 48 px
const int denom      = max(1, (int)count - PLEDIT_ROW_COUNT);
const int thumb_y    = PLEDIT_ROWS_Y + scrollOffset * travel / denom;
```

`scrollOffset` is the index of the first visible row (0 = top).

### Visibility condition

The thumb (and rail-blit step) is only performed when `count > PLEDIT_ROW_COUNT`
(more stations than fit on screen). When `count ≤ 5` the right-side position
still shows the tiled `SKIN_PLEDIT_RIGHT_SIDE` rail (always drawn), but no thumb
is blitted on top.

### Fast scroll path

`drawScrollThumbOnly()` retiles the rail and reblits the thumb at the new
`scrollOffset` without redrawing rows. Called during `D_PLEDIT_SCROLL_DIRECT`
drag state. Row text uses `TFT_eSPI` **Font 1** (fixed 6×8 px), not the Winamp
LED bitmap font — this is the same font used for PLEDIT rows in Spotify mode.

### Preview implementation (TASK-201 fix)

```python
# Crop sprites from pledit_raw (loaded once from wsz)
rail_tile  = pledit_raw.crop((32, 42, 51, 71))   # 19×29
thumb_img  = pledit_raw.crop((52, 54, 61, 71))   # 9×17, has transparent pixels

# Tile rail over rows area (y=136..200)
rows_h = 5 * 13  # 65 px
for sy in range(PLEDIT_ROWS_Y, PLEDIT_ROWS_Y + rows_h, 29):
    h = min(29, PLEDIT_ROWS_Y + rows_h - sy)
    img.paste(rail_tile.crop((0, 0, 19, h)), (PLEDIT_CONTENT_X + PLEDIT_CONTENT_W, sy))

# Blit thumb when station count > 5
if len(stations) > 5:
    travel  = rows_h - 17   # 48
    denom   = len(stations) - 5
    thumb_y = PLEDIT_ROWS_Y + scroll_offset * travel // denom
    # Mask transparency key (0,198,255) with tolerance 30
    mask = thumb_img.convert("RGBA")
    px   = mask.load()
    for y in range(mask.height):
        for x in range(mask.width):
            r, g, b, _ = px[x, y]
            if abs(r-0) < 30 and abs(g-198) < 30 and abs(b-255) < 30:
                px[x, y] = (r, g, b, 0)
    img.paste(thumb_img.convert("RGB"), (261, thumb_y), mask.split()[3])
```

---

## Data flow

### Station list fetch (existing dataTask)

```
GET https://de1.api.radio-browser.info/json/stations/search
    ?countrycode={CC}&codec=MP3&hidebroken=true&order=votes&limit=100

→ parse with ArduinoJson filter (extract name, url_resolved, bitrate, votes only)
→ store in WebRadioState::stations[MAX_STATIONS=100]
```

**Parser note (critical):** 100-station response is ~220–240 KB (TASK-200
measured 109.5 KB for 100 NL stations). Must use `ArduinoJson` streaming parse
— **never** buffer into a `String`. Follow the existing dataTask pattern:

```cpp
StaticJsonDocument<128> filter;
filter[0]["name"]         = true;
filter[0]["url_resolved"] = true;
filter[0]["bitrate"]      = true;
filter[0]["votes"]        = true;
StaticJsonDocument<8192> doc;
deserializeJson(doc, http.getStream(),
                DeserializationOption::Filter(filter));
```

**BP-031 (tlsYield) required:** This fetch is a new HTTPS session in `dataTask`.
Call `spotifyTask::tlsYield()` before `WiFiClientSecure client` and
`spotifyTask::tlsResume()` after `http.end()` in all exit paths — including
error returns. Omitting this caused a confirmed crash in `fetchTeletext()`
(T272, LL-071). Not optional.

`url_resolved` is pre-resolved server-side — no redirect following needed.

Mirror fallback order: `de1` → `nl1` → `at1`. Retry next mirror on connection
failure. Cache station list; refresh only on country change or explicit reload.

### Audio streaming (new dedicated FreeRTOS task)

```cpp
Audio audio(true, I2S_DAC_CHANNEL_LEFT_EN);   // GPIO26 → SC8002B amp
audio.setAudioTaskCore(1);                     // core 1; display stays on core 0
audio.setVolume(settings.webRadio.maxVolume);  // ceiling from settings (default 10; 18 with HW mod)
audio.connecttohost(url_resolved);             // streams MP3, follows redirects
audio.stopSong();                              // on app switch / user stop
```

The audio task runs independently of `dataTask`. Station-list fetches complete
before playback starts (TLS heap spikes do not overlap with decode buffer).

`ESP32-audioI2S` creates its audio task at **priority 2** (above spotifyTask /
dataTask priority 1). This is intentional — audio must not be preempted by
polling tasks. Spotify polling is already suspended while WebRadio is active.

### ICY metadata → display (FreeRTOS queue)

The `audio_info_callback` fires in the **audio task's context**. Write to
display state via a queue to avoid data races:

```cpp
// One-time setup:
QueueHandle_t g_titleQueue = xQueueCreate(1, sizeof(char[256]));

// Callback (audio task context):
Audio::audio_info_callback = [](Audio::msg_t m) {
    if (m.e == Audio::evt_streamtitle)
        xQueueOverwrite(g_titleQueue, m.msg);   // m.msg is UTF-8, pre-parsed
    if (m.e == Audio::evt_name)
        /* store station name similarly */;
    if (m.e == Audio::evt_bitrate)
        /* store bitrate */;
};

// webRadioTick() (loop/display context):
char title[256];
if (xQueuePeek(g_titleQueue, title, 0))
    marqueeUpdate(title);
```

`Icy-MetaData: 1` is injected automatically by `connecttohost()`. If the
server sends no metadata, `evt_streamtitle` simply never fires — no error.

### VU meter

`audio.getVUlevel()` — polled from `webRadioTick()`. Feeds the existing VU
meter envelope directly. Option A confirmed viable (EXP-005 RQ-3).

---

## Audio hardware path (confirmed EXP-005 RQ-2)

```
ESP32 I2S-DAC → GPIO26 → SC8002B amp (~14.5× gain) → SPEAK header → 8 Ω speaker
```

- GPIO25 is **not available** (XPT2046 touch SPI SCK — hard conflict).
- GPIO26 is dedicated to the on-board amp; no TFT or other peripheral conflict.
- 8-bit, mono, up to 44.1 kHz sample rate. Acceptable for radio.
- **External 8 Ω speaker required** — nothing on-board.
- Stock: keep `audio.setVolume()` ≤ 10/21 (hard DAC overload + clipping above this).
- With gain-reduction HW mod: full 0–21 range usable; default ceiling 18.
- See §Settings for the HW Mod Installed / Max Volume settings pair.

---

## Library (confirmed EXP-005 RQ-3)

```ini
# platformio.ini — add to lib_deps:
esphome/ESP32-audioI2S
```

Compatible with `espressif32@6.9.0` (Arduino-ESP32 2.0.17, I2S v1 API).
Breaking I2S v2 change only affects Arduino-ESP32 3.x — not a risk here.

**Flash risk:** library adds ~300–500 KB (includes all decoders). Must measure
`pio run` output with library added before implementation is scheduled. If
budget is tight, a stripped MP3-only fork reduces footprint.

**SRAM / ring buffer:** `esphome/ESP32-audioI2S` default ring buffer is
**25 chunks × 1 600 B = 40 000 B** (≈ 2.5 s at 128 kbps, ≈ 1.0 s at 320 kbps).
The EXP-005 "6.25 KB" estimate was the socket receive buffer, not the audio
ring buffer.  Prefer stations ≤ 96 kbps for maximum stall tolerance (3.3 s
drain time vs 2.5 s at 128 kbps).  Display `inBufferFilled()` in the POSBAR
as a real-time health indicator; see §POSBAR buffer health below.

---

## Error states

> **Architect scope decision — 2026-06-21 (TASK-219).** This section is split by
> *why each part exists*; only Tier 1 is M-WEBRADIO MVP scope. Tiers 2–3 are
> **deferred post-MVP** (tracked as TASK-219).
>
> - **Tier 1 — MVP-mandatory (correctness, implemented):** a single catch-all
>   "playback stopped unexpectedly → resume the yielded Spotify TLS → show *an*
>   error" path. This is load-bearing for the TLS-yield coexistence design, not
>   UX polish: without it a stream death silently starves Spotify (the TASK-218
>   regression). Implemented as the debounced `isRunning()` watchdog in
>   `webRadioApp.h::tick()` (`WR_STREAM_DEAD_MS`), which catches *every* root
>   cause below — all manifest as `isRunning()==false` — and lands in
>   `ERROR_STALL`. `ERROR_UNREACHABLE` on synchronous connect-fail also stays.
>   *Status: implemented, DUT-verification pending (TASK-218).*
> - **Tier 2 — DEFERRED: root-cause classification.** Distinguishing
>   `ERROR_WIFI` / `ERROR_BLOCKED` / `ERROR_STALL` as distinct titles needs
>   `WiFi.status()` polling + HTTP-status parsing from `audio_info`. This is UX
>   precision on top of a recovery that already works. The detection rows below
>   describe the *target* design, not shipped MVP behaviour.
> - **Tier 3 — ~~DEFERRED~~ GRADUATED TO MVP for no-PSRAM hardware (ADR-045, 2026-06-24):**
>   auto-retry / auto-skip automation (the §Auto-retry and auto-skip policy table).
>   Re-classified from "convenience" to **load-bearing** by the TASK-233 DUT finding:
>   on this no-PSRAM board the MP3 decoder fails to allocate intermittently, so many
>   stations enter PLAYING then die in ~5 s (`ERROR_STALL`). Without auto-skip the UI
>   parks on a dead station; *with* it the device tunes past dead stations to a playable
>   one. The bounded retry→skip subset (retry once, then advance, stop after one pass
>   over the list) is now MVP-mandatory and `webRadioAutoSkip` **defaults ON**. Tracked
>   as TASK-234. (Tier 2 root-cause classification stays deferred.)
>
> **MVP exit criterion (revised by ADR-045 for no-PSRAM hardware):** supersedes the
> Tier-1-only criterion below. M-WEBRADIO closes when, from cold entry on the no-PSRAM
> DUT, WebRadio reaches a stable PLAYING state (holds ≥ 60 s) within ≤ 6 auto-skips on
> ≥ 90 % of attempts — i.e. Tier 1 (watchdog) **and** Tier 3 (auto-skip) both DUT-verified.
> Tier 2 does **not** gate close. The synthetic injection tests (T_WR_ERR_01–04,
> TASK-212) verify error-state *rendering* and remain valid; they do not assert
> detection, which is exactly the Tier-2 gap they will exercise when it lands.
>
> Adjacent finding (not the error machine): `webRadioBitrateCap` is likewise
> stored but never applied to the radio-browser query (`bitrate_max` absent) —
> also config-only/inert. Flagged for the same reconciliation pass.

### Detection logic

Checked when `audio.isRunning()` returns false or `inBufferFilled()` reaches 0:

```
audio stops or fails to start
    │
    ├─ WiFi.status() != WL_CONNECTED
    │       state → ERROR_WIFI       title "WiFi lost"
    │       recovery: poll WiFi.status(); reconnect; retry same station
    │
    ├─ WiFi connected + HTTP 403 / 451 (from audio_info callback)
    │       state → ERROR_BLOCKED    title "Station blocked"
    │       recovery: auto-skip if setting on; else remain on station
    │
    ├─ WiFi connected + HTTP 200 + buffer drains to 0
    │       state → ERROR_STALL      title "Buffering…" → "Stream stall"
    │       POSBAR shows drain live; retry connecttohost() once;
    │       if still drains → auto-skip if setting on
    │
    └─ WiFi connected + connect failed (DNS / TCP timeout)
            state → ERROR_UNREACHABLE  title "Station unreachable"
            recovery: retry once; then move to next station
```

The `audio_info(const char* info)` callback carries the HTTP status line
(`"HTTP/1.1 403 Forbidden"`, etc.) so 403/451 is detectable before audio
decode begins.  The stall case is visible from `inBufferFilled()` approaching
zero with `WiFi.status() == WL_CONNECTED`.

### State / title mapping

| State | POSBAR | Marquee title text |
|-------|--------|--------------------|
| STOPPED | left (0%) | station name |
| CONNECTING | animated fill | "Connecting…" |
| BUFFERING | draining, < 20% | "Buffering…" |
| PLAYING | live fill level | station name → ICY StreamTitle |
| ERROR_WIFI | left (0%) | "WiFi lost" |
| ERROR_BLOCKED | left (0%) | "Station blocked" |
| ERROR_STALL | left (0%) | "Stream stall" |
| ERROR_UNREACHABLE | left (0%) | "Station unreachable" |

### POSBAR buffer health

```cpp
// Called on each display tick while PLAYING or BUFFERING:
uint32_t filled = audio.inBufferFilled();
uint32_t free_  = audio.inBufferFree();
float    frac   = (float)filled / max(1u, filled + free_);
int      thumb  = (int)(frac * POSBAR_TRAVEL);  // POSBAR_TRAVEL = 219 px
// blitSprite(POSBAR_BG) then blitSprite(POSBAR_THUMB_N at thumb_px)
```

Left (thumb = 0) = buffer empty; right (thumb = 219) = buffer full.
Same two-blit POSBAR contract as existing firmware — only `thumb_px` source
changes (buffer fraction instead of playback position).

### Auto-retry and auto-skip policy

| Event | With Auto-skip OFF | With Auto-skip ON |
|-------|-------------------|-------------------|
| ERROR_STALL (once) | retry same station | retry same station |
| ERROR_STALL (twice) | show error, wait | advance to next station |
| ERROR_BLOCKED | show error, wait | advance to next station |
| ERROR_UNREACHABLE | retry once, show error | retry once, advance |
| ERROR_WIFI | wait for WiFi | wait for WiFi (no skip) |

---

## Settings

Settings → Applications → Web Radio:

| Setting | Type | Default | Notes |
|---------|------|---------|-------|
| Country | enum (ISO 3166-1 alpha-2) | `NL` | Drives station list fetch; searchable via KeyboardWidget |
| Autoplay | bool | false | Reconnect last station on app launch |
| Bitrate cap | enum (kbps) | 96 | API query `?bitrate_max=N`; limits drain rate so 40 KB buffer lasts ≥ 3.3 s; options: 64 / 96 / 128 / 192 / off |
| Auto-skip on stall | bool | false | Advance to next station when `ERROR_STALL` repeats; see §Error states auto-retry policy |
| HW Mod Installed | bool | false | SC8002B gain-reduction mod applied (see §Audio hardware path); unlocks Max Volume above 10 |
| Max Volume | int 1–21 | 10 (stock) / 18 (HW mod) | Ceiling passed to `audio.setVolume()`; default auto-raised when HW Mod toggled on |
| Last station idx | int | 0 | Persisted in `settings.json` (SPIFFS); internal |

### Country picker

Country list is derived at compile time from `kCities[]` in `settings/cities.h` —
deduplicate the `country` ISO 3166-1 alpha-2 field. Yields ~40–50 entries; good
coverage for radio-browser.info. Not runtime-fetched.

The picker renders as a scrollable list. Tapping the search icon opens
`KeyboardWidget` (Full mode); typed characters filter the list by country name
(static name mapping alongside each code). Clearing the input resets the filter.

### HW Mod and Max Volume interaction

```
HW Mod = false → Max Volume default = 10; soft cap at 12 (code enforces)
HW Mod = true  → Max Volume default = 18; cap removed (user can set 1–21)
```

The mod replaces resistors around the SC8002B to lower the ~14.5× gain and
raise input impedance. Without it the 8-bit DAC output is overloaded and clips
above ~10/21. Reference: https://github.com/hexeguitar/ESP32_TFT_PIO#audio-amp-gain-mod

---

## Memory envelope (EXP-005 updated)

| Item | SRAM | Notes |
|------|------|-------|
| Station list (100 × ~80 B) | ~8 KB | persistent |
| Audio decode + I2S buffers | ~40–60 KB | runtime (heap) |
| TLS heap spike (station fetch) | ~50–70 KB | transient, non-overlapping |
| `WebRadioState` struct | ~1 KB | persistent |
| ICY title queue | ~256 B | persistent |

Peak transient is the TLS spike (~50–70 KB), which dissipates before playback
starts. Empirical validation needed — run heap watermark logging on DUT.

---

## Dependencies

- M-MULTIAPP (done) — AppId enum, appRegistry, switchApp, dataTask
- M-TASKBAR-ICONS (done) — no new icons required; eject toggle eliminates need
  for `radio.png` / `radio_active.png` (open item 6 resolved)
- EXP-005 R&D spike — **done** (2026-06-13)

---

## BP-036 new-app integration checklist

Required per BP-036. Developer must satisfy all three before milestone close:

| Integration | Requirement | WebRadio note |
|-------------|-------------|---------------|
| `hasPendingAsync()` | Return `true` while station-list dataTask fetch is in flight | WebRadio enqueues async work from tick; default `false` is wrong |
| `tlsYield()` / `tlsResume()` | Wrap every new HTTPS fetch in dataTask (BP-031) | Station-list fetcher; required — see §Data flow parser note |
| Serial `dbgGet` / `dbgSet` | Surface `playState`, `stationIdx`, `lastTouchResult` for VE testability | Needed for TASK-211 ACT_EJECT accessor and error-state injection (TASK-212) |

QM audits this checklist at M-WEBRADIO retrospective.

---

## Shift-left pre-implementation plan

Risk is front-loaded: burn down unknowns on host before any DUT flash. ~70% of
pre-implementation risk is host-resolvable. DUT sessions become targeted and
short.

### Host-only phase (TASK-199 – TASK-202, no DUT required)

| Task | Deliverable | De-risks |
|------|-------------|----------|
| **TASK-199** Flash budget gate | Add `esphome/ESP32-audioI2S` to `platformio.ini`; run `pio run -e cyd2usb_winamp`; report binary size | Only blocking gate. If budget fails, re-scope before any UI work. |
| **TASK-200** API probe + TLS cert | `test_radiobrowser_api.py` (JSON shape, response size, mirror fallback, TLS cert issuer); Python ICY metadata probe against a live stream | Root CA for `dataTaskCerts.h`; confirms API contract before firmware parser is written; confirms ICY `StreamTitle` format |
| **TASK-201** Canvas layout preview | `preview_webradio.py` — loads `gen/skin_preview.png` as base; draws radio content on top: PL list, marquee, buffer bar, bitrate, VU meter, functional scrollbar; keyboard to cycle states. **No country badge** (removed — see §Canvas layout note). **Implementation constraints:** `skin_preview.png` is the main-window background only — POSBAR chrome, PLEDIT chrome, and scrollbar rail/thumb are all runtime sprite blits in firmware, not baked into the PNG. Preview must: (1) extract TEXT.BMP from `.wsz` and call `composite_text()` from `bake_skin.py` for LED font glyphs; (2) paste POSBAR.BMP crop at `(POSBAR_X=16, POSBAR_Y=72)`; (3) blit PLEDIT chrome via `build_pledit_atlas()`; (4) tile right-side rail (19×29 from PLEDIT.BMP at (32,42,51,71)) and blit scrollbar thumb (9×17 from PLEDIT.BMP at (52,54,61,71)) with RGB(0,198,255) transparency masking — see §PLEDIT scrollbar for exact formula. PIL default font and synthetic fill-rectangles are not acceptable. | Layout locked before firmware; scrollbar geometry and transparency masking confirmed before sprite atlas is wired into firmware |
| **TASK-202** Country list generator | Host script: deduplicate `kCities[].country` from `cities.h`; cross-check against radio-browser.info `countrycode` availability; output static `kWebRadioCountries[]` `{code, name}` array | Country enum ready to paste into firmware; coverage gaps known before implementation |

Execute in order: TASK-199 first (gate). TASK-200–202 can run in parallel once
TASK-199 passes.

### DUT-only phase (after host phase clears)

| Item | Why host cannot cover it |
|------|--------------------------|
| Open item 2 — Buffer dropout | Real WiFi throughput + SRAM decode buffers at 128 kbps |
| Open item 3 — Touch + audio coexistence | GPIO25/26 electrical interaction, board-specific |
| Heap watermark | ESP32 SRAM envelope under real audio decode + TLS spike |
| Volume ceiling calibration | SC8002B + speaker output — empirical, subjective |

Schedule DUT session after firmware implementation is functionally complete.
Buffer dropout and coexistence are back-to-back empirical checks — one session.

---

## Open items before implementation

1. ~~**Flash budget gate**~~ — **resolved (TASK-199, 2026-06-14)**: build at 55.6%
   flash with `esphome/ESP32-audioI2S` + `-DAUDIO_NO_SD_FS` + `SD_MMC` in
   `lib_ignore`.  Gate cleared.
2. ~~**Buffer dropout / bitrate cap**~~ — **resolved by host probe
   (`test_stream_buffer.py`, 2026-06-14)**: ring buffer is 40 KB (not 6.25 KB
   as stated in EXP-005); 26% of 280 probed stations show real network stalls
   (≥ 1.2 s pause).  Bitrate cap of **96 kbps** added to Settings (default);
   gives 3.3 s drain tolerance vs 2.5 s at 128 kbps.  Firmware must also
   implement retry-on-stall; see §Error states.
3. ~~**Geo-lock**~~ — **resolved by host probe (`test_stream_geo.py`,
   2026-06-14)**: 90% of 300 probed stations across 15 countries are
   accessible from local IP.  6 blocked (HTTP 403/451), 1 playlist URL.
   Firmware must detect and surface these as distinct error states; see
   §Error states.  Playlist URLs (`.m3u`/`.pls`) are out of MVP scope —
   firmware skips them with "Unsupported format" title.
4. **Touch + audio coexistence** — XPT2046 SPI (GPIO25) and I2S-DAC (GPIO26)
   active simultaneously; verify no electrical interference on this board rev.
   → DUT phase.  Peripheral buses are independent (SPI vs internal DAC); low
   electrical risk but requires empirical confirmation.
5. ~~**Amp volume ceiling**~~ — **resolved by design**: `HW Mod Installed` bool +
   `Max Volume` int exposed in settings. Stock default 10; mod default 18. Soft
   cap enforced in code when HW Mod = false. Reference mod: hexeguitar/ESP32_TFT_PIO.
6. ~~**Source taskbar icons**~~ — **resolved by design (2026-06-14)**: WebRadio has
   no taskbar slot. Toggle is via the Winamp **eject button** (pos 136, 89, 22×16 px).
   No `radio.png` / `radio_active.png` required. See §Eject button toggle.
7. ~~**Country list**~~ — **resolved (TASK-202, 2026-06-14)**: 65 entries, 0
   coverage gaps; `app/gen/webradio_countries.h` generated.
