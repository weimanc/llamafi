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

- 11th app in `appRegistry.h` (slot after Teletext).
- Browse and play internet radio stations, categorised by country.
- Winamp skin reused; controls remapped to radio semantics.
- Country/region settable in Settings → Applications → Web Radio.
- Station list fetched from **radio-browser.info** REST API (MP3 only).
- Toggle Spotify ↔ Web Radio via taskbar (existing mechanism).

---

## Non-goals

- EQ / crossfader / recording.
- AAC or OGG stream support (MP3 first cut only).
- Simultaneous Spotify + radio playback.
- Saving favourite stations (post-MVP).

---

## App lifecycle

```
switchApp(AppId::WebRadio)
  → appTick() calls webRadioTick()
       first tick: trigger dataTask fetch of station list for selected country
       on list ready: render playlist view
       on user selects station: audio.connecttohost(url)
switchApp(AppId::Spotify)  [or any other app]
  → webRadioSuspend(): audio.stopSong(); release I2S-DAC handle
```

When WebRadio is not active, the audio task is suspended and Spotify polling
resumes normally. Modes are mutually exclusive via `switchApp`.

---

## Canvas layout (275 × 240 px)

Winamp main-unit geometry reused with adapted semantics:

```
┌──────────────────────────────────────────────────────┬─────────┐
│  [⏮]  [⏹] [▶/⏸]  [⏭]   EQ  PL        clkwdgt      │         │
│  ────────────────────────────────────────────────    │taskbar  │
│  Station name (scrolling marquee)  ••  [COUNTRY]     │  45 px  │
│  ICY StreamTitle (artist — title)                    │         │
│  [buffer bar replaces seek bar]   bitrate  kbps      │         │
│  ════════════════════════════════════════════════    │         │
│  ▌▌▌▌▌▌▌  VU meter (getVUlevel())  ▌▌▌▌▌▌▌           │         │
│  ────────────────────────────────────────────────    │         │
│  [PL panel: station list]  scroll indicator          │         │
└──────────────────────────────────────────────────────┴─────────┘
```

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

## Data flow

### Station list fetch (existing dataTask)

```
GET https://de1.api.radio-browser.info/json/stations/search
    ?countrycode={CC}&codec=MP3&hidebroken=true&order=votes&limit=100

→ parse with ArduinoJson filter (extract name, url_resolved, bitrate, votes only)
→ store in WebRadioState::stations[MAX_STATIONS=100]
```

**Parser note (critical):** 100-station response is ~220–240 KB. Must use
`ArduinoJson` with a `StaticJsonDocument` filter that keeps only the four
needed fields. Do not buffer the full response body.

`url_resolved` is pre-resolved server-side — no redirect following needed.

Mirror fallback order: `de1` → `nl1` → `at1`. Retry next mirror on connection
failure. Cache station list; refresh only on country change or explicit reload.

### Audio streaming (new dedicated FreeRTOS task)

```cpp
Audio audio(true, I2S_DAC_CHANNEL_LEFT_EN);   // GPIO26 → SC8002B amp
audio.setAudioTaskCore(1);                     // core 1; display stays on core 0
audio.setVolume(10);                           // ≤10/21 — avoid amp clipping
audio.connecttohost(url_resolved);             // streams MP3, follows redirects
audio.stopSong();                              // on app switch / user stop
```

The audio task runs independently of `dataTask`. Station-list fetches complete
before playback starts (TLS heap spikes do not overlap with decode buffer).

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
- Keep `audio.setVolume()` ≤ 10/21 to avoid SC8002B clipping + excess current.

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

**SRAM without PSRAM:** 6.25 KB input buffer → ~400 ms at 128 kbps. Prefer
64–96 kbps stations (filter with `bitrate` field from station list). Display
`inBufferFilled()` in the buffer bar as a user-visible health indicator.

---

## Settings

Settings → Applications → Web Radio:

| Setting | Type | Default | Notes |
|---------|------|---------|-------|
| Country | enum (ISO 3166-1 alpha-2) | `NL` | Drives station list fetch |
| Autoplay | bool | false | Reconnect last station on app launch |
| Last station idx | int | 0 | Persisted in `settings.json` (SPIFFS) |

Country enum baked at compile time (~40 active entries). Not runtime-fetched.

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
- M-TASKBAR-ICONS (done) — `radio.png` + `radio_active.png` icons needed (24×24)
- EXP-005 R&D spike — **done** (2026-06-13)

---

## Open items before implementation

1. **Flash budget gate** — add `esphome/ESP32-audioI2S` to `platformio.ini`,
   run `pio run -e cyd2usb_winamp`, confirm binary fits partition. Blocking.
2. **Buffer dropout test** — on-DUT: play 128 kbps stream; measure drop rate;
   decide if 96 kbps cap should be enforced in API query.
3. **Touch + audio coexistence** — XPT2046 SPI (GPIO25) and I2S-DAC (GPIO26)
   active simultaneously; verify no electrical interference on this board rev.
4. **Amp volume ceiling** — calibrate max `audio.setVolume()` below distortion.
5. **Source taskbar icons** — `radio.png` / `radio_active.png` (24×24 RGBA).
6. **Country list** — compile the baked ~40-entry enum from radio-browser country
   coverage data.
