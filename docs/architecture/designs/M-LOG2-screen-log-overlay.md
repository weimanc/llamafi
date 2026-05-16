# Design — M-LOG2 On-screen Log Overlay

> Owner: Developer
> Status: planned (added 2026-05-07)
> Tracked-as: TASK-018
> Deps: log-001 (M-LOG ringbuffer), M3 (chrome as top layer)

## Scope

Use the full 320×240 panel as a log terminal. Winamp chrome paints on top and clips whatever it covers. Visible: top strip (y 0–62, ~7 older lines) + bottom strip (y 178–240, ~7 newer lines). Middle band (~16 lines) scrolls through but is hidden behind the chrome.

## Design

- New `screenLog.h` renderer; subscribes to existing 12 KB ringbuffer (no new state).
- Layering: log = bottom layer (full-screen). Chrome = top layer.
- Font: TFT_eSPI font 1 (6×8 px) — ~30 lines × 53 chars.
- Newest line at bottom; older lines scroll up; oldest eventually scrolls off top.
- Colors: green-on-black (terminal aesthetic). No anti-aliasing.
- Lines truncated on right (no wrapping).
- Redraw: dirty flag set by `ringPush`; redraw at most ~4 Hz to avoid SPI thrash. Each redraw paints full log then re-blits chrome (background + transport + status + title + posbar).
- Behind `#define SCREEN_LOG` (or `cyd2usb_winamp_screenlog` env). Default off.

## Exit criteria

- With `-DSCREEN_LOG`: panel shows log lines top + bottom, chrome overlaid in middle. New entries appear at bottom and scroll up.
- Without flag: zero overhead — `screenLog::tick()` compiled out; chrome paints to black background as today.
