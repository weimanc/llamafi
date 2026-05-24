#pragma once
// Secret-bearing string redactor (ADR-010, TASK-016b).
// Use whenever a token, client_secret, refresh_token, or Bearer header value
// is about to cross a logging boundary. NEVER pass raw secrets to Serial,
// ESP_LOGx, or any other sink — call redact() first.
//
// Returns a pointer into a small rotating pool (8 slots), so up to 8 calls
// inside a single printf argument list resolve correctly. Beyond that the
// oldest slot is overwritten — if you're printing more than 8 redacted
// values in one statement, snprintf into a local at the call site.

#include <Arduino.h>

inline const char *redact(const char *s) {
  static char pool[8][40];
  static uint8_t next = 0;
  char *buf = pool[next];
  next = (next + 1) & 7;

  if (s == nullptr) {
    return "<null>";
  }
  size_t n = strlen(s);
  if (n == 0) {
    return "<empty>";
  }
  if (n <= 4) {
    snprintf(buf, sizeof(pool[0]), "<short len=%u>", (unsigned)n);
    return buf;
  }
  snprintf(buf, sizeof(pool[0]), "%c%c\xE2\x80\xA6%c%c (len=%u)",
           s[0], s[1], s[n - 2], s[n - 1], (unsigned)n);
  return buf;
}
