#pragma once
// textFit.h — ellipsis truncation to a PIXEL budget (M-PLEDIT-ABSTRACTION §4).
//
// Extracted verbatim from winampDisplay.h's Spotify PLEDIT row formatter
// (TASK-411 / DEV-10). The original was entangled with the number-prefix and
// duration-column width maths, so the shared form takes a pixel budget plus a
// glyph width rather than a column spec — the caller keeps ownership of how
// the budget was derived.
//
// Semantics are byte-identical to the inline original, deliberately including
// its two edge-case behaviours:
//   - budget < 3 chars  → no truncation at all (the string overflows). Kept
//     because relaxing it would change rendering in exactly the case the
//     original leaves alone.
//   - the ellipsis is three ASCII dots written OVER the last three fitting
//     characters, so the result is exactly `budget` chars, never longer.
//
// Only meaningful for the fixed-width glyph fonts this project renders rows
// with (TFT_eSPI Font 1, 6 px/char). A proportional font would need per-glyph
// advance widths, not a divide.

#include <string.h>

// Truncates `s` in place so it renders within `budgetPx` at `charPx` px per
// character, appending "..." when it does not fit. No-op when it already fits
// or when the budget is under three characters.
inline void textFit(char *s, int budgetPx, int charPx) {
  if (!s || charPx <= 0) return;
  const int budget = budgetPx / charPx;
  if (budget < 3) return;
  if ((int)strlen(s) <= budget) return;
  s[budget - 3] = '.';
  s[budget - 2] = '.';
  s[budget - 1] = '.';
  s[budget]     = '\0';
}
