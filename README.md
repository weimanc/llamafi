# ESP32 Spotify Display

A Winamp-style Spotify "now playing" display for the ESP32 Cheap Yellow Display (CYD). Shows track, artist, progress bar, VU meter, playlist, and playback controls rendered with a classic Winamp 2.x skin.

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
git clone https://github.com/your-username/your-repo.git
cd your-repo
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

### 6. Get a Winamp skin

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

### 7. Flash

Flash the firmware and upload the SPIFFS partition (config file):

```sh
./run/flash              # flash firmware
./run/spiffs push        # upload credentials to SPIFFS (non-destructive)
```

The board's serial port is detected automatically via USB VID:PID.
Override with `PORT=/dev/ttyUSB1 ./run/flash` if needed.

---

### 9. First boot — WiFi

If you ran `./run/setup` and accepted the spiffs push offer, the device reads
`wifi_creds.json` from SPIFFS and connects automatically — no portal needed.

If WiFi credentials are not configured (fresh device, no `wifi_creds.json` on
SPIFFS, no `wifi_creds.h`), the device falls back to a captive portal:

1. The device broadcasts a hotspot: **SSID `SpotifyDIY`**, password `thing123`.
2. Connect your phone to it.
3. A captive portal opens — tap **"Configure WiFi"** (not "Info").
4. Enter your WiFi SSID and password and save.

The device connects, loads the Spotify config from SPIFFS, and starts displaying
the currently playing track.

---

### 10. Monitor serial output

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
