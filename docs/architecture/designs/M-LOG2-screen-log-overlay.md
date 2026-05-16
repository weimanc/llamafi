# Design — M-LOG2 On-screen Log Overlay

> Owner: Developer
> Status: done (TASK-018 DUT-verified 2026-05-07); PLEDIT compat fix needed before M-LIST-v2 ships
> Tracked-as: TASK-018
> Deps: log-001 (M-LOG ringbuffer in `logSink.h`), M3 (chrome as top layer)

## Scope

Full-screen log terminal visible on the DUT without a serial cable. The Winamp main chrome repaints on top of the log, naturally masking whatever it covers. Diagnostic only — off by default, enabled via the `cyd2usb_winamp_screenlog` env.

## Screen geometry (as DUT-verified, pre-M-LIST-v2)

Font 1 (6×8 px GLCD): 30 rows × 53 chars on a 320×240 panel. Row n (0 = newest, 29 = oldest) drawn at `y = 232 - n*8`.

With only main chrome active (no PLEDIT — the state at DUT verification 2026-05-07):

| Row range | y range | Visibility |
|---|---|---|
| 0..14 (newest 15) | 120..232 | **Visible** — below chrome (y≥116) |
| 15..29 (older 15) | 0..112 | Hidden under main chrome (y=0..115) |

The original design spec ("top strip y=0..62 + bottom strip y=178..240") was written before the chrome position was finalised at `originY=0`. The actual visible area is the single bottom strip y=116..239. DUT verification confirmed green log text in this region; "top + bottom strips" in the TASK-018 note refers to the design intent, not what was empirically observed.

## Dirty detection and redraw rate

`screenlog::tick()` (called every `loop()` iteration) uses two guards:

1. **Change gate:** compares `logsink::g_head` (ringbuffer write head) to a cached `lastHead`. If equal, no new push since last redraw — return immediately.
2. **Rate cap:** hard 250 ms interval (`REDRAW_MIN_INTERVAL_MS = 250`). Prevents SPI saturation during log bursts. Effective redraw rate: ≤4 Hz.

No separate dirty boolean — `g_head` comparison serves that role.

## Repaint sequence (each triggered redraw)

1. `tft.fillScreen(BG)` — flood panel black.
2. Snapshot up to 30 most-recent lines via `logsink::ringForEachLast`.
3. Draw rows newest-at-bottom (`y=232` for row 0, up by 8 px per older row).
4. Restore `tft.setSwapBytes` to the chrome path's expected state.
5. `WinampDisplay::repaintChrome()` — overlays main chrome (y=0..115) in one TFT transaction. Internally calls `vu::invalidate()`.

`drawPlaylist()` is **not** called inside `screenlog::tick()` — the PLEDIT area (y=116..239) remains log text.

## Build configuration

| Flag | Value |
|---|---|
| `cyd2usb_winamp_screenlog` env | extends `cyd2usb_winamp`, adds `-DSCREEN_LOG` |

Both `WINAMP_DISPLAY` and `SCREEN_LOG` are defined in this env. Without `SCREEN_LOG`: `screenlog::tick()` compiled out — zero overhead.

## PLEDIT compatibility — fix required before M-LIST-v2 ships

`SpotifyDiyThing.ino` calls `drawPlaylist()` unconditionally inside `#ifdef WINAMP_DISPLAY`:

```cpp
#ifdef WINAMP_DISPLAY
  vu::tick(...);
  winampDisplay.drawPlaylist();   // ← runs every loop in screenlog env too
#endif
```

After M-LIST-v2 ships, `drawPlaylist()` will paint PLEDIT chrome over y=116..239 on every loop iteration, erasing the visible log rows. SCREEN_LOG worked at TASK-018 verification because PLEDIT did not yet exist.

**Required fix** (in `.ino`, before `cyd2usb_winamp_screenlog` is used after M-LIST-v2):

```cpp
#ifdef WINAMP_DISPLAY
  vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(), SKIN_MAIN_BG);
  #ifndef SCREEN_LOG
  winampDisplay.drawPlaylist();
  #endif
#endif
```

This is a 2-line change. Register as a sub-task of M-LIST-v2 or M-LOG2 maintenance.

## Exit criteria (original — already met)

- Build `cyd2usb_winamp_screenlog`: clean build, zero overhead when `SCREEN_LOG` not defined.
- DUT: y=116..239 shows green-on-black log text; newest at bottom; entries scroll up as log grows.
- DUT: main chrome (transport, posbar, time, title, VU) renders correctly.
- DUT: build without `SCREEN_LOG` unaffected.

## Exit criteria (compat fix — outstanding)

- After PLEDIT compat fix: `cyd2usb_winamp_screenlog` build shows log text in PLEDIT area with M-LIST-v2 PLEDIT skin shipped.
- No PLEDIT chrome visible in `SCREEN_LOG` mode.
