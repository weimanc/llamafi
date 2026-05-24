#pragma once
// screenLog.h — full-screen log overlay (TASK-018, M-LOG2).
//
// Paints recent ringbuffer lines across the entire 320×240 panel using
// TFT_eSPI font 1 (6×8 px GLCD), green-on-black. Newest line at the bottom,
// older lines scroll up; oldest scrolls off the top. The Winamp chrome is
// then re-blitted on top via display->repaintChrome(), naturally clipping
// whatever the chrome covers.
//
// Default OFF — only built in when SCREEN_LOG is defined (env
// cyd2usb_winamp_screenlog). Zero overhead otherwise. The .ino guards both
// the include and the tick() call with #ifdef SCREEN_LOG.
//
// Usage (inside #ifdef SCREEN_LOG in the .ino):
//   screenlog::tick(spotifyDisplay);   // call every loop()
//
// `tick()` is a no-op when the ringbuffer head hasn't advanced since the
// last redraw, OR when the 250 ms rate-limit window hasn't elapsed.

#include <Arduino.h>
#include <TFT_eSPI.h>

#include "logSink.h"
#include "winamp/winampDisplay.h"

extern TFT_eSPI tft;  // defined in cheapYellowLCD.h

namespace screenlog {

constexpr unsigned long REDRAW_MIN_INTERVAL_MS = 250;  // 4 Hz cap
constexpr int FONT_ID   = 1;                            // 6×8 px GLCD
constexpr int CHAR_W    = 6;
constexpr int CHAR_H    = 8;
constexpr int PANEL_W   = 320;
constexpr int PANEL_H   = 240;
constexpr int LINES_FIT = PANEL_H / CHAR_H;             // 30
constexpr int CHARS_FIT = PANEL_W / CHAR_W;             // 53
constexpr uint16_t FG   = TFT_GREEN;
constexpr uint16_t BG   = TFT_BLACK;

inline void tick(SpotifyDisplay *display) {
  static uint16_t lastHead   = 0xFFFF;
  static unsigned long nextAt = 0;

  unsigned long now = millis();
  if (now < nextAt) return;  // hard rate-limit

  uint16_t head;
  portENTER_CRITICAL_SAFE(&logsink::g_mux);
  head = logsink::g_head;
  portEXIT_CRITICAL_SAFE(&logsink::g_mux);
  if (head == lastHead) return;  // nothing new
  lastHead = head;
  nextAt = now + REDRAW_MIN_INTERVAL_MS;

  // Save the byte-swap state from the Winamp pushImage path; drawString
  // writes raw 16-bit colors and gets garbled if we leave swap on.
  bool prevSwap = tft.getSwapBytes();
  tft.setSwapBytes(false);
  tft.fillScreen(BG);
  tft.setTextColor(FG, BG);
  tft.setTextFont(FONT_ID);
  tft.setTextSize(1);

  // Snapshot up to LINES_FIT most-recent lines (oldest-first per the
  // ringForEachLast contract), then replay newest-at-bottom.
  struct Line { char data[CHARS_FIT + 1]; };
  static Line lines[LINES_FIT];
  int collected = 0;
  logsink::ringForEachLast(LINES_FIT, [&](const char *buf, size_t len) {
    if (collected >= LINES_FIT) return;
    size_t copy_len = len > (size_t)CHARS_FIT ? (size_t)CHARS_FIT : len;
    memcpy(lines[collected].data, buf, copy_len);
    lines[collected].data[copy_len] = 0;
    // Strip trailing newline so it doesn't render as a glyph box.
    if (copy_len > 0 && lines[collected].data[copy_len - 1] == '\n') {
      lines[collected].data[copy_len - 1] = 0;
    }
    collected++;
  });

  int line_y = PANEL_H - CHAR_H;  // y of the newest line
  for (int i = collected - 1; i >= 0 && line_y >= 0; --i, line_y -= CHAR_H) {
    tft.drawString(lines[i].data, 0, line_y, FONT_ID);
  }

  // Restore byte-swap for the chrome blits.
  tft.setSwapBytes(prevSwap);

  // Chrome on top — relies on WinampDisplay::repaintChrome (TASK-018a).
  if (auto *wd = static_cast<WinampDisplay *>(display)) {
    wd->repaintChrome();
  }
}

}  // namespace screenlog
