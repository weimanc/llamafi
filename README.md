# llamafi

A Winamp-style Spotify "now playing" display for the ESP32 Cheap Yellow Display (CYD), with a multi-app shell that keeps things interesting between tracks.

> Vibecoded with [Claude Code](https://claude.ai/code) 🦙

---

## What's inside

### Spotify — the main event

The Spotify app renders a pixel-faithful Winamp 2.x skin on the CYD's 320×240 display. Bake any `.wsz` skin you like and it shows up on hardware. Track title, artist, album art region, progress bar, playlist panel, and a synthesised VU meter that bounces to the music envelope. Full playback controls via touch — play/pause, next, previous, seek, volume slider. Position interpolates smoothly between ~1 Hz Spotify polls so the seek bar feels live.

### Multi-app shell

Eight more apps live alongside Spotify, switchable via a scrolling taskbar:

| App | What it does |
|---|---|
| **Clock** | Full-screen clock |
| **Weather** | Current conditions + forecast |
| **Crypto** | Cryptocurrency price ticker |
| **Stock** | Stock quotes, line charts, and a heatmap view |
| **Matrix** | Matrix rain effect |
| **Life** | Conway's Game of Life |
| **Aquarium** | ASCII aquarium with fish, bubbles, and a crab |
| **Settings** | On-device WiFi setup, display brightness, time zone, and more |

### Settings — on device, no portal

WiFi credentials and time zone are configured entirely on the device via touch. No captive portal, no phone app. The settings app has a city picker (78 cities), LDR-based auto-brightness calibration, and a scrollable app registry.

---

## Inspiration

- **[witnessmenow/Spotify-Diy-Thing](https://github.com/witnessmenow/Spotify-Diy-Thing)** — the base project this grew out of. Spotify Web API client, CYD display driver, and touch input all originate here.
- **[Winamp 2.x skin format](https://skins.webamp.org)** — the Winamp Skin Museum and the webamp project were invaluable references for decoding the `.wsz` format and layout.
- **[POWER-PILL/ASCII-Aquarium](https://github.com/POWER-PILL/ASCII-Aquarium)** — inspiration for the aquarium app.
- **[Hacktuber](https://www.youtube.com/@Hacktuber)** — the multi-app shell concept originated from Hacktuber's [5in1 Cyber Deck for ESP32 CYD](https://youtu.be/qM6bYuTQb-I). The idea of running multiple apps on a single CYD device, switchable from a launcher, came directly from that project.

---

## Where the time went

Most of the development effort went into four areas:

- **Winamp display** — skin baking pipeline (`.wsz` → C arrays), pixel-perfect sprite atlas, layout engine, VU meter synthesis, and the full touch hit-zone map.
- **Aquarium** — demoscene-style optimisation to hit smooth framerates on ESP32 PSRAM, plus a procedurally animated crab creature.
- **Stock app** — async data fetching, candlestick/line chart renderer, and a portfolio heatmap.
- **Settings** — on-device WiFi connect flow (scan → keyboard → connect), LDR auto-brightness calibration, city picker with UTC offset column, and the on-screen keyboard widget used across the whole shell.

---

## Hardware

**ESP32-2432S028R "Cheap Yellow Display" — two-USB variant.**

The two-USB variant is required. The single-USB variant produces inverted colors with this firmware. Both look identical externally; check the listing or the PCB silkscreen.

- [AliExpress](https://www.aliexpress.com/item/1005004502250619.htm)
- [Makerfabs](https://www.makerfabs.com/sunton-esp32-2-8-inch-tft-with-touch.html)

---

## Getting Started

### 1. Prerequisites

**PlatformIO** — install the CLI:

```sh
pip install platformio
```

**Python 3 + Pillow** — for skin baking:

```sh
pip install Pillow
```

**ImageMagick** — also for skin baking (Pillow can't decode all Winamp BMPs):

```sh
sudo dnf install ImageMagick   # Fedora
sudo apt install imagemagick   # Debian/Ubuntu
```

---

### 2. Clone

```sh
git clone https://github.com/weimanc/llamafi.git
cd llamafi
```

---

### 3. Spotify Developer setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create an app.
2. In the app settings, add this exact redirect URI:
   ```
   http://127.0.0.1:8888/callback/
   ```
3. Note your **Client ID** and **Client Secret**.

> Spotify no longer accepts LAN IP redirect URIs (e.g. `http://192.168.x.x/...`).
> The loopback URI above is the only non-HTTPS form still allowed.

---

### 4. Run the setup wizard

```sh
./run/setup
```

The wizard prompts for WiFi credentials and Spotify API keys, handles the OAuth
flow, writes both credential files to `app/data/`, and offers to upload them to
the device in one step.

> Both credential files are gitignored — they will never be committed.

<details>
<summary>Manual alternative (headless / scripted re-auth)</summary>

```sh
# Spotify only — writes app/data/spotify_diy_config.json
./get_refresh_token.py <CLIENT_ID> <CLIENT_SECRET>

# WiFi — create app/data/wifi_creds.json manually:
# {"ssid": "YourNetwork", "pass": "YourPassword"}

# Then upload both:
./run/spiffs push
```

</details>

---

### 5. Get a Winamp skin

The Winamp base skin is not included (licensing). Download any Winamp 2.x `.wsz`
skin and place it at `app/skins/`:

```sh
# Example — rename whatever you downloaded:
mv ~/Downloads/my_skin.wsz app/skins/base-2.91.wsz
```

[Winamp Skin Museum](https://skins.webamp.org) has thousands of skins to choose from.

Then bake the skin into C arrays for the firmware:

```sh
./run/bake-skin
# or use a different skin:
./run/bake-skin app/skins/my_other_skin.wsz
```

> Baking only needs to be re-run when you change the skin.

---

### 6. Flash

Flash the firmware and upload the SPIFFS partition (config file):

```sh
./run/flash              # flash firmware
./run/spiffs push        # upload credentials to SPIFFS (non-destructive)
```

The board's serial port is detected automatically via USB VID:PID.
Override with `PORT=/dev/ttyUSB1 ./run/flash` if needed.

---

### 7. First boot — WiFi

If you ran `./run/setup` and accepted the spiffs push offer, the device reads
`wifi_creds.json` from SPIFFS and connects automatically — no portal needed.

If WiFi credentials are not configured (fresh device, no `wifi_creds.json` on
SPIFFS, no `wifi_creds.h`), the device opens the WiFi Settings screen
automatically on boot:

1. A list of nearby networks appears on the display.
2. Tap a network name to select it.
3. For a password-protected network, an on-screen keyboard appears — type the
   password and confirm.
4. The device connects and starts displaying the currently playing track.

---

### 8. Monitor serial output

```sh
./run/monitor-start          # start serial monitor in a tmux session
./run/monitor-read           # dump last 200 lines
./run/monitor-stop           # stop monitor
```

---

## Run scripts reference

All build, flash, and monitor operations go through `run/`. Raw `pio` commands
are not recommended — the scripts handle port detection, monitor lifecycle, and
DUT safety automatically.

| Script | What it does |
|---|---|
| `./run/setup` | First-time setup wizard (WiFi + Spotify credentials) |
| `./run/build` | Compile production firmware |
| `./run/flash` | Flash production firmware |
| `./run/spiffs push [file]` | Upload credential file(s) to SPIFFS non-destructively |
| `./run/spiffs ls` | List files on device |
| `./run/spiffs pull [file]` | Extract all files → `app/data/spiffs-dump/`, or single file → stdout |
| `./run/spiffs rm <file>` | Remove a single file from device |
| `./run/flash-fs` | Full SPIFFS format + rewrite (escape hatch; use `run/spiffs push` instead) |
| `./run/bake-skin [skin.wsz]` | Bake Winamp skin → `app/gen/` |
| `./run/monitor-start` | Start serial monitor (tmux) |
| `./run/monitor-read [N]` | Dump last N lines (default 200) |
| `./run/monitor-stop` | Stop monitor |
| `./run/check` | 5-gate build check (run before committing) |

---

## License

[MIT](LICENSE) — project code only.

Winamp skin assets are not included and must be obtained separately.
SpotifyArduino (vendored in `app/lib/`) is MIT © Brian Lough.
