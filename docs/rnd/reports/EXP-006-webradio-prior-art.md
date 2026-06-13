# EXP-006 — Web Radio Prior Art Survey: ESP32 CYD Projects

> R&D Engineer  
> Date: 2026-06-13  
> Status: complete  
> Feeds: M-WEBRADIO design doc, EXP-005

---

## Purpose

Survey existing ESP32 CYD (ESP32-2432S028R) web radio projects to understand
established patterns for station listing and audio streaming before finalising
the M-WEBRADIO firmware design. Four projects were analysed in depth via
parallel source-code review.

---

## Projects Surveyed

| # | Project | Author | URL |
|---|---------|--------|-----|
| 1 | yoRadio | e2002 | github.com/e2002/yoradio |
| 2 | CYD_InternetRadio | Carlo47 | github.com/Carlo47/CYD_InternetRadio |
| 3 | Web Radio ESP32-2432S028-I2S | macsbug | macsbug.wordpress.com |
| 4 | esp32_radio | pschatzmann | github.com/pschatzmann/esp32_radio |

Additional projects found but not deep-dived: CYD-GOLD (ESP32-S3 variant),
CYD_MP3Player (local playback only), DIY CYD FM Radio (FM, not internet).

---

## Findings by Dimension

### Station Listing

| Project | Approach |
|---------|----------|
| yoRadio | SPIFFS CSV (`/data/playlist.csv`). User-managed via self-hosted web UI (gzipped HTML/JS in SPIFFS). Binary index file maps station# → CSV byte offset for O(1) random access into lists up to 65,535 entries. KaRadio `WebStations.txt` import supported. No radio-browser.info integration. |
| CYD_InternetRadio | 28 European stations hardcoded as a C++ struct array in `main.cpp`. No runtime discovery. Reflash to change. |
| macsbug | Hardcoded string arrays in the sketch. Reflash to change. |
| pschatzmann | radio-browser.info REST API (`/json/stations/search?codec=MP3&...`). Country and genre seed lists from local JSON files; actual station records fetched live. Blacklist JSON suppresses specific stations. |

**Pattern:** The two most polished CYD-specific projects (yoRadio, CYD_InternetRadio)
avoid live API discovery in favour of local lists. Only pschatzmann integrates
radio-browser.info — and his project is not CYD-specific and uses a web-app
UI rather than touch. The local-list pattern avoids dependency on an external
service and allows offline startup.

**Implication for M-WEBRADIO:** radio-browser.info integration (our current
plan) is the right call for zero-config discovery, but a hybrid approach
warrants consideration: fetch from radio-browser.info on first launch / country
change, then cache to SPIFFS CSV in yoRadio style. This gives offline resilience
and fast restarts.

---

### Streaming Library

| Project | Library |
|---------|---------|
| yoRadio | Vendored fork of ESP32-audioI2S (`src/audioI2S/Audio.cpp`) — kept in-tree for version control. |
| CYD_InternetRadio | arduino-audio-tools + arduino-libhelix. Pipeline: `ICYStream` → `MP3DecoderHelix` → `VolumeStream` → `I2SStream`. |
| macsbug | ESP32-audioI2S **v2.0.4** (pinned). v3.x breaks on CYD (no PSRAM — see §GPIO25 conflict below). |
| pschatzmann | ESP8266Audio (`AudioFileSourceICYStream` + `AudioGeneratorMP3` + `AudioOutputI2S`). |

ESP32-audioI2S (schreibfaul1) is the most common choice; confirmed viable for
our stack. **Version must be pinned to v2.x** — see critical finding below.

---

### Audio Output Path

| Project | Path | Pins |
|---------|------|------|
| yoRadio | External I2S DAC (default) **or** internal ESP32 DAC (compile flag `I2S_INTERNAL`) | External: DOUT=27, BCLK=26, LRC=25; Internal: GPIO25+26 |
| CYD_InternetRadio | External I2S DAC only. Explicitly avoids internal DAC due to GPIO25 touch conflict. | BCLK=27, WSEL=21, DOUT=22. Chips: UDA1334A or dual MAX98357A. |
| macsbug | External I2S DAC. | BCLK=4, LRC=16, DIN=17. Chips: MAX98357A, PCM5102A, UDA1334A. |
| pschatzmann | External I2S DAC (default); internal DAC noted as alternative. | Default I2S peripheral pins. |

**Pattern:** all projects default to external I2S DAC. The internal DAC
(GPIO25/26) is avoided on CYD due to the GPIO25 touch conflict (see below).
Our design correctly uses only GPIO26 (DAC channel 2, `I2S_DAC_CHANNEL_LEFT_EN`)
routed to the on-board SC8002B amplifier — the one path that avoids the conflict
and requires no external hardware.

---

### Touch UI / Station Browsing

| Project | Approach |
|---------|----------|
| yoRadio | XPT2046 (resistive) or GT911 (capacitive). Swipe up/down enters station list and scrolls proportionally (`TS_STEPS=40`). Tap selects/plays. Long-press repeats scroll. |
| CYD_InternetRadio | Touch zones mapped to buttons: next, prev, first, last station + volume slider. Preferences (last station, volume) saved to NVS. |
| macsbug | Touch zones: volume ±, channel ±1 / ±10, brightness ±, invert. Auto-advance to next station on connect failure. |
| pschatzmann | No touch — web app (Vue.js on GitHub Pages) POSTs stream URL to ESP32 REST API. |

---

### Architecture Highlights (yoRadio — most mature)

yoRadio is the most production-hardened project and worth studying before
finalising M-WEBRADIO firmware design:

- **Dual-core task split**: audio decode on one core, UI/network on the other,
  communicating via a FreeRTOS queue (`playerQueue`). Prevents audio glitches
  during web requests or display redraws.
- **Framebuffer**: boards with PSRAM get a full framebuffer for VU meters and
  scrolling text, applied automatically; non-PSRAM boards fall back gracefully.
- **Self-contained web UI**: gzipped HTML/JS/CSS in SPIFFS — no cloud
  dependency for the management interface.
- **VS1053b fallback**: compile-time swap to a VS1053b hardware decoder chip
  (`src/audioVS1053/`) for better audio quality on boards that have one.
- **SD card mode**: playlist can be served from SD card without WiFi.

---

## Critical Finding: GPIO25 Touch Conflict

The ESP32's internal DAC has exactly two channels:

| Channel | GPIO | I2S enum |
|---------|------|----------|
| DAC 1 | GPIO25 | `I2S_DAC_CHANNEL_RIGHT_EN` |
| DAC 2 | GPIO26 | `I2S_DAC_CHANNEL_LEFT_EN` |

The CYD's XPT2046 resistive touch controller uses **GPIO25 as its SPI SCK
line**. When the I2S peripheral is enabled in DAC mode on GPIO25, it takes
exclusive ownership of the pin and drives it as a continuous audio bit-stream —
destroying the SPI clock signal. Touch stops working completely.

This is why all CYD radio projects either:
(a) use an external I2S DAC on different pins (GPIO21/22/27 etc.), or
(b) use only GPIO26 (DAC channel 2) which is wired to the on-board SC8002B amp
    and has no other peripheral attached.

`I2S_DAC_CHANNEL_BOTH_EN` (GPIO25 + GPIO26 simultaneously, as in yoRadio's
`I2S_INTERNAL` mode) would break touch on the CYD and must not be used.

**Our design correctly uses `I2S_DAC_CHANNEL_LEFT_EN` (GPIO26 only)**, which
is the one safe internal DAC path on this board.

---

## Critical Finding: ESP32-audioI2S v3.x Breaks on CYD

macsbug confirmed: ESP32-audioI2S **v3.x requires PSRAM** for its larger
internal buffers. The CYD has no PSRAM. On v3.x without PSRAM: reception
instability, dropouts, crashes.

**Must pin to v2.x** in `platformio.ini`:
```ini
esphome/ESP32-audioI2S@^2.0.7   # or latest stable 2.x tag
```
Verify latest stable 2.x tag at time of implementation.

---

## Critical Finding: Partition Scheme

macsbug reports a compiled binary of ~1.5 MB when using ESP32-audioI2S,
requiring the **"No OTA (2MB APP / 2MB SPIFFS)"** partition scheme. The
default Arduino ESP32 partition (1.3 MB app) will not fit.

Our project is already large (TFT_eSPI, baked skin assets, multiple apps).
Adding ESP32-audioI2S will push it further. The flash budget gate (EXP-005
Open Item #1) must be validated before implementation is scheduled — and if
the binary does not fit, the partition table must be updated in `platformio.ini`.

---

## Implications for M-WEBRADIO Design

| Finding | Action |
|---------|--------|
| radio-browser.info is the right API source | Confirmed — only one other project uses it; others are manually curated |
| GPIO26-only DAC path confirmed safe | Design confirmed; do not use GPIO25 for audio |
| ESP32-audioI2S v2.x only | Pin version in `platformio.ini` before implementation |
| Partition scheme may need to change | Validate binary size before scheduling implementation |
| yoRadio SPIFFS CSV cache pattern | Consider caching radio-browser.info results to SPIFFS for offline resilience |
| Dual-core FreeRTOS split (yoRadio) | Confirms our audio-task-on-core-1 approach; audio task must not share core with display |
| Auto-advance on connect failure (macsbug) | Good UX default — add to M-WEBRADIO open items |

---

## Open Item Added to M-WEBRADIO

- Consider caching fetched station list to SPIFFS (`/webradio_stations.csv` or
  `.json`) so the app can start without a network round-trip on relaunch.
- Add auto-advance-to-next-station on connect failure (macsbug pattern).
