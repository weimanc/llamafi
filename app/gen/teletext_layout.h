// Touch zone constants for TeletextApp. Strip zone y-values derived from
// preview_teletext.py (locked 2026-06-13). Fast-text bar section derived from
// APP_W=275. Applications submenu row coordinates TBD (TASK-177).
#pragma once

#include <stdint.h>

// Character grid geometry
#define TTXT_CHAR_W       6    // glyph width (px)
#define TTXT_CHAR_H       8    // glyph height (px)
#define TTXT_COLS        40    // columns per row
#define TTXT_ROWS        25    // rows per page

// Grid pixel dimensions
#define TTXT_GRID_W     240    // COLS × CHAR_W
#define TTXT_GRID_H     200    // ROWS × CHAR_H

// Fast-text bar (bottom band, full APP_W=275)
#define TTXT_BAR_Y0     200    // top edge of fast-text bar
#define TTXT_BAR_Y1     239    // bottom edge of fast-text bar (inclusive)
#define TTXT_BAR_H       40    // bar height (px)
#define TTXT_FTL_BTN_W   68    // button width (275 // 4); button i: x = i*68..(i+1)*68-1

// Side strip position (right of grid, left of taskbar)
#define TTXT_STRIP_X    240    // left edge of nav strip
#define TTXT_STRIP_W     35    // width of nav strip (px)

// Strip touch zones — y ranges are inclusive
#define TTXT_STRIP_SUBUP_Y0   0    // sub-page up   (34 px)
#define TTXT_STRIP_SUBUP_Y1  33
#define TTXT_STRIP_PAGE_Y0   34    // page num / keypad (33 px)
#define TTXT_STRIP_PAGE_Y1   66
#define TTXT_STRIP_BACK_Y0   67    // ◄◄ back        (33 px)
#define TTXT_STRIP_BACK_Y1   99
#define TTXT_STRIP_PREV_Y0  100    // previous page  (33 px)
#define TTXT_STRIP_PREV_Y1  132
#define TTXT_STRIP_NEXT_Y0  133    // next page      (33 px)
#define TTXT_STRIP_NEXT_Y1  165
#define TTXT_STRIP_SUBDN_Y0 166    // sub-page down  (34 px)
#define TTXT_STRIP_SUBDN_Y1 199
