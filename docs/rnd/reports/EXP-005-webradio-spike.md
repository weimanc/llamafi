# EXP-005 — Web Radio R&D Spike

> R&D Engineer  
> Date: 2026-06-13  
> Status: complete — all four questions resolved  
> Feeds: M-WEBRADIO design doc, ADR-045 (pending)

---

## Summary

All four R&D questions are resolved. The M-WEBRADIO feature is **technically
feasible** on the CYD hardware. Two risks require empirical validation before
implementation is scheduled: flash budget and stream buffer depth.

| RQ | Question | Verdict |
|----|----------|---------|
| RQ-1 | radio-browser.info API fitness | **GO** |
| RQ-2 | CYD audio output path | **GO** (external speaker required) |
| RQ-3 | ESP32-audioI2S library | **Conditional GO** (flash + buffer risks) |
| RQ-4 | ICY stream metadata | **GO** |

---

## RQ-1 — radio-browser.info API

**Verdict: GO**

- HTTPS confirmed, no auth, open licence — no ToS issues for IoT.
- Station-by-country endpoint:
  ```
  GET https://de1.api.radio-browser.info/json/stations/search
      ?countrycode=NL&codec=MP3&hidebroken=true&order=votes&limit=100
  ```
  Use `countrycode` (ISO 3166-1 alpha-2), not the deprecated `country` param.
- `url_resolved` is pre-resolved server-side — ESP32 does not need to follow
  redirects.
- **Critical:** 100-station response is ~220–240 KB. Must parse with
  `ArduinoJson` using a filter document — do not buffer the full response body
  into a `String`. Extract only `name`, `url_resolved`, `bitrate`, `votes`.
- Multiple mirrors: `de1`, `nl1`, `at1`. Hardcode 2–3 as fallbacks; retry next
  on connection failure. Do not attempt DNS SRV on-device.
- No documented rate limits; cache results (refresh hourly or on country change
  only, not every boot).

---

## RQ-2 — CYD audio output path

**Verdict: GO — external 8 Ω speaker required**

The ESP32-2432S028R has an on-board audio amplifier (SC8002B or PAM8002A,
~1 W) wired to a 2-pin SPEAK connector. There is no on-board speaker; one
must be plugged in externally.

**Pin assignments confirmed:**

| GPIO | Assignment |
|------|-----------|
| GPIO26 | On-board SC8002B amp input — **audio DAC out** |
| GPIO25 | XPT2046 touch controller SPI SCK — **taken, cannot use** |

On ESP32, I2S-DAC mode maps:
- `I2S_DAC_CHANNEL_LEFT_EN` → GPIO26 → on-board amp ✓ (use this)
- `I2S_DAC_CHANNEL_RIGHT_EN` → GPIO25 → touch conflict ✗

No conflict with TFT HSPI (GPIO 12/13/14/15) or backlight (GPIO21).

Audio characteristics:
- 8-bit resolution (ESP32 internal DAC hardware limit)
- Mono only (one channel available)
- Sample rate: up to ~44.1 kHz via I2S-DAC; practical quality ~22 kHz
- Quality: acceptable for voice/web radio, not hi-fi

Keep software volume ≤ 10/21 — the SC8002B has ~14.5× fixed gain and clips
at high volume. Audio current draw can spike >500 mA; account for this in
USB power budget.

---

## RQ-3 — ESP32-audioI2S library

**Verdict: Conditional GO — validate flash budget empirically**

Library: `esphome/ESP32-audioI2S` (PlatformIO registry).  
Add to `platformio.ini`:
```ini
lib_deps =
    ...
    esphome/ESP32-audioI2S
```

**Framework compatibility:** confirmed stable with `espressif32@6.9.0`
(Arduino-ESP32 2.0.17, I2S v1 API). The breaking I2S v2 change only affects
Arduino-ESP32 3.x. Pin library to a 2.x-compatible release tag if needed.

**Flash:** ~300–500 KB additional (includes HELIX MP3, AAC, FLAC, Opus
decoders). This is the primary risk — must be validated with `pio run` output
against the current partition scheme before implementation is scheduled. If
tight, a stripped fork (MP3-only) reduces footprint.

**SRAM:** No PSRAM on ESP32-2432S028R → 6.25 KB input buffer. At 128 kbps
MP3 (16 KB/s), this is ~400 ms of buffer — marginal. Mitigations:
- Prefer stations at 64–96 kbps (most AM-equivalent radio streams).
- Use `inBufferFilled()` / `inBufferFree()` to drive the buffer health bar
  and warn user when buffer is draining.
- Decoder working memory: ~25–30 KB heap at runtime; total SRAM pressure
  ~40–60 KB — feasible but tight alongside TFT_eSPI DMA buffers.

**CPU:** Library runs its own FreeRTOS task. Configure:
```cpp
audio.setAudioTaskCore(1);   // core 1 for audio
// display + main loop stays on core 0
```
HELIX decoder is faster than I2S output rate — self-throttles via queue.
Community consensus: concurrent 30 fps SPI display + MP3 decode works on
stock ESP32.

**API surface confirmed:**
```cpp
Audio audio(true, I2S_DAC_CHANNEL_LEFT_EN);   // internal DAC → GPIO26
audio.connecttohost(url);                      // streams, follows redirects
audio.stopSong();                              // stop / suspend
uint32_t vu    = audio.getVUlevel();           // for VU meter
uint32_t fill  = audio.inBufferFilled();       // for buffer bar
uint32_t free_ = audio.inBufferFree();
```

---

## RQ-4 — ICY stream metadata

**Verdict: GO**

The library fires a single `audio_info_callback` for all events:
```cpp
// Register once in setup():
Audio::audio_info_callback = [](Audio::msg_t m) {
    switch (m.e) {
        case Audio::evt_name:        // station name (fires once on connect)
        case Audio::evt_streamtitle: // track "Artist - Title" (per-track)
        case Audio::evt_bitrate:     // stream bitrate kbps
    }
    // m.msg is char* — pre-parsed, UTF-8, HTML-entities decoded
};
```

- `evt_name` — from `icy-name` response header; fires once on connect.
- `evt_streamtitle` — per-track; library strips `StreamTitle='…';` framing,
  decodes Latin-1 → UTF-8, handles XML variants.
- `Icy-MetaData: 1` is injected automatically by `connecttohost()`.
- If the server sends no ICY metadata: `evt_streamtitle` simply never fires —
  no error, no empty callback.

**Threading — critical:**  
The callback runs in the **audio task's FreeRTOS context**, not in `loop()`.
Writing directly to display buffers or `WebRadioState` is unsafe. Use a
1-element `xQueue` of `char[256]` consumed in `loop()`:
```cpp
// audio task context (callback):
xQueueOverwrite(g_titleQueue, m.msg);

// loop() / display tick:
char title[256];
if (xQueuePeek(g_titleQueue, title, 0)) { /* update marquee */ }
```

---

## Remaining unknowns (validate during implementation)

1. **Flash budget** — run `pio run -e cyd2usb_winamp` with library added;
   confirm it fits the current partition before merging. This is the single
   blocking risk.
2. **Buffer dropouts** — test 128 kbps streams on-DUT; determine whether 64–96
   kbps cap is needed in UX (e.g. filter stations by bitrate in API query).
3. **Touch + audio coexistence** — XPT2046 SPI and I2S-DAC both active
   simultaneously; verify no electrical interference on the board.
4. **Amp volume calibration** — determine safe `audio.setVolume()` ceiling
   (avoid clipping at SC8002B's fixed gain).
