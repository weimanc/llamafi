# Design — M-SDFS: SD card exploration and bring-up

> Owner: Architect
> Status: draft
> Date: 2026-08-07
> Parent: [M-WINAMP-PLAYER.md](M-WINAMP-PLAYER.md) (workstream 1 of 4)
> Feeds: ADR-059 D1
> Tracked-as: TASK-408
> Registers: `sdfs-001` · X053

**Standalone value:** this workstream answers a hardware question the project has never answered.
Its result is useful (and its cost is one task) regardless of whether local playback ever ships.
Nothing else in M-WINAMP-PLAYER starts until it passes.

---

## 1. Context

The ESP32-2432S028R carries a micro-SD slot. This firmware has never mounted it.
`M-AQUARIUM/overview.md` explicitly dropped the donor sketch's `SD.h` capture path as
"dev tool, no hardware in our board config" — which recorded a decision not to use it, not a
finding that it is absent or broken. So the state is genuinely unknown.

## 2. Pin budget (desk-checked, 2026-08-07)

| Bus / function | GPIO |
|---|---|
| TFT (HSPI, `USE_HSPI_PORT`) | 12 MISO · 13 MOSI · 14 SCLK · 15 CS · 2 DC · 21 BL |
| Touch XPT2046 (own SPI, `CYD28_TouchscreenR.h`) | 25 CLK · 32 MOSI · 39 MISO · 33 CS · 36 IRQ |
| Audio | 26 (internal DAC, `I2S_DAC_CHANNEL_LEFT_EN`) |
| RGB LED (`ledFlow.h`) | 4 · 16 · 17 |
| LDR (`backlightFlow.h`) | 34 (ADC1) |

**Free, and exactly the CYD SD wiring: VSPI — 18 SCLK · 19 MISO · 23 MOSI · 5 CS.**
SD gets its own `SPIClass(VSPI)`; TFT keeps HSPI. No pin is shared with any existing peripheral.

Unknowns that only hardware can answer:

- **GPIO5 is a strapping pin** — must read HIGH at reset. SD CS idles high so this is expected
  benign, but a card that pulls it low is a boot-loop class failure.
- **Pull-ups.** Several CYD revisions omit them on the SD lines. SPI mode is more forgiving than
  SDIO, but a bare card may need `INPUT_PULLUP` on MISO or a lower clock.
- **Clock ceiling.** Start at 4 MHz; raise only after the benchmark is clean.
- **Long filenames.** Arduino-ESP32 2.0.17's bundled FATFS LFN configuration is not safe to assume.

## 3. Deliverable — `sdprobe` (debug build, TASK-408)

A serial command reporting, in one shot:

| Measurement | Why it matters |
|---|---|
| mount success, card type, size, FAT type | go / no-go |
| `.dram0.bss` + heap delta across `SD.begin()` | the FATFS work area is heap; the static cost is already known (§4) but the runtime cost is not |
| long-filename round-trip (>8.3, spaces, mixed case) | decides whether M3U paths and browser rows need 8.3 mangling |
| `listDir()` timing on a ~200-file directory | sets the file browser's page size (parent design's browse-001) |
| sustained sequential read, KB/s | decides whether playback is possible at all |
| per-read latency histogram, worst case | decides whether playback is *reliable* |

### Pass bar

| Metric | Bar | Derivation |
|---|---|---|
| mount | succeeds | — |
| sustained read | ≥ 200 KB/s | 320 kbps MP3 needs 40 KB/s; 5× margin covers pump burst refill under UI contention |
| worst single-read latency | ≤ 50 ms | InBuff is 6 400 B ≈ 160 ms of 320 kbps audio, so a 50 ms stall is absorbable |
| `SD.begin()` heap delta | ≤ 8 KB | fits the parent's runtime budget without a reclaim |

**Fail → the parent milestone closes with a hardware note.** SPIFFS is explicitly not an accepted
fallback: 1.4 MB shared with skin, settings and config is roughly one three-minute track.

## 4. Static cost — measured, not estimated (2026-08-07)

Dropping `-DAUDIO_NO_SD_FS` re-enables `connecttoFS()`, the `File audiofile` member and the SD/FS
includes. Measured on `cyd2usb_winamp_debug` by rebuilding with `-UAUDIO_NO_SD_FS` plus a probe
translation unit that actually references `SD.begin()`, `openNextFile()`, `read()` and
`connecttoFS()` (without it the linker garbage-collects most of the cost and the number flatters):

| | `.dram0.data` | `.dram0.bss` | dram0_0_seg headroom | flash |
|---|---|---|---|---|
| debug baseline | 32 912 | 91 360 | **304 B** | 1 797 920 |
| `-UAUDIO_NO_SD_FS`, unreferenced | +0 | +40 | 264 B | +3 904 |
| **`-UAUDIO_NO_SD_FS`, wired** | **+16** | **+72** | **216 B** | **+3 984** |

So SD/FS costs **88 B of static DRAM and ~4 KB of flash**. That is cheap — but see the parent
design's budget section: it lands on a debug build with 304 B of headroom, which is the real
constraint, not this delta.

## 5. Lifecycle

Mount is **lazy** — on entry to Player mode, not at boot — and released on mode exit. This mirrors
the `mb_arena` acquire/release discipline rather than paying boot time and heap for a card the user
may never insert. Consequence: `sdprobe` must be callable independently of Player mode so the
measurement is not entangled with the feature.

## 6. Open questions

- **OQ1** — is the slot even populated on this unit? Visual check before any code.
- **OQ2** — does the card need to be FAT32-formatted specifically (exFAT is not supported by the
  bundled FATFS configuration)? Document the supported format for the user.
- **OQ3** — hot-swap: v1 mounts once per mode entry. Card removal mid-playback is undefined; decide
  whether to detect and fail gracefully or leave it as a known rough edge.

## 7. Test & validation

Architect specifies *what must be proven and how*; VE owns the suite and may renumber. Ids reserved
in the `T_SD_` family (unused before this design).

### TASK-408 — SD probe and benchmark

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_SD_01` | Card mounts on VSPI at 4 MHz | DUT serial — `sdprobe` | `ok:true`, card type and size reported non-zero |
| `T_SD_02` | GPIO5 strapping is benign | DUT — 5 cold boots with card inserted | 5/5 normal boot, no bootloop, no `rst:0x10` in log |
| `T_SD_03` | Long filenames round-trip | DUT serial — write/read `/A long name (test) 01.mp3` | byte-identical name returned by `openNextFile()` |
| `T_SD_04` | Sustained read meets the bar | DUT — `sdprobe` benchmark, ≥2 MB read | **≥200 KB/s** |
| `T_SD_05` | Worst-case read latency meets the bar | DUT — `sdprobe` latency histogram | **≤50 ms**, and the histogram is reported (not just the max — a bimodal distribution is the interesting case, cf. TASK-367's fetch RTT) |
| `T_SD_06` | `SD.begin()` heap cost is bounded | DUT serial — free-heap delta across mount | **≤8 KB** |
| `T_SD_07` | `listDir()` on ~200 files is bounded | DUT — timed `sdprobe` listing | reported; sets the browser page size (`browse-001`) |
| `T_SD_08` | Mount/unmount is repeatable and leak-free | DUT — 20 mount/unmount cycles | free heap returns to within 256 B of baseline each cycle |
| `T_SD_09` | Absent/unformatted card fails cleanly | DUT — probe with no card, then with an exFAT card | `ok:false` with a distinguishable error; no crash, no hang |

**Validation notes.** `T_SD_04`/`T_SD_05` are the go/no-go pair and must be run with the display
actively redrawing — a benchmark on an idle device measures the wrong thing, since the real
contention is SPI/CPU against TFT rendering. `T_SD_08` exists because §5 makes mount lazy and
per-mode-entry: a leak there compounds once per mode switch, not once per boot.

**Negative result is a valid outcome.** If `T_SD_01`, `04`, `05` or `06` fails, record the numbers
and close the milestone — see §3. Do not retune the bar to fit the hardware.

## 8. Exit criteria

1. `sdprobe` runs on the physical DUT and every §3 metric is recorded in the task.
2. All four §3 pass bars met, or the milestone is closed with the numbers that failed.
3. GPIO5 strapping verified benign across ≥5 cold boots with a card inserted.
4. Supported card format and filename constraints documented for the user.
