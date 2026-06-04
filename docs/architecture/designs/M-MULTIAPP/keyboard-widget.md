# Design — KeyboardWidget

> Owner: Architect
> Status: draft
> Date: 2026-06-04
> Part of: M-MULTIAPP
> Consumers: [wifi-settings.md](wifi-settings.md), settings `app` tab (stock/crypto ticker entry)
> See also: [settings.md](settings.md), [touch-calibration.md](touch-calibration.md)

---

## Role

`KeyboardWidget` is a **reusable, modal, full-canvas on-screen keyboard**.
It is not an `App`, not an `AppId`, and does not appear in the taskbar.
Any `App` or flow component can activate it, receive the submitted string,
and dismiss it.

Known consumers:

| Consumer | Mode | Prompt | Max len |
|----------|------|--------|---------|
| `WifiFlow` — password entry | `Full` | `"Password: <ssid>"` | 64 |
| Settings `app` tab — stock ticker | `UpperAlpha` | `"Enter ticker"` | 6 |
| Settings `app` tab — crypto coin | `UpperAlpha` | `"Enter coin"` | 8 |

---

## Interface

```cpp
class KeyboardWidget {
public:
    enum class Mode {
        Full,        // a-z, A-Z (shift), 0-9, symbols — WiFi passwords
        UpperAlpha,  // A-Z only + backspace/OK — tickers, short codes
    };

    // Activate the keyboard. Caller retains ownership of prompt/initial strings.
    void show(const char*  prompt,
              const char*  initial,
              Mode         mode,
              uint8_t      maxLen,
              void (*onSubmit)(const char* text, void* ctx),
              void (*onCancel)(void* ctx),
              void*        ctx);

    void hide();
    bool active() const { return _active; }

    void tick();
    bool handleInput(TouchPhase phase, int x, int y);

private:
    bool    _active = false;
    Mode    _mode;
    uint8_t _maxLen;
    char    _buf[65];   // maxLen ≤ 64 + NUL
    uint8_t _len;
    uint8_t _page;      // 0 = alpha/lower, 1 = alpha/upper, 2 = symbols/numbers
    bool    _dirty;
    void (*_onSubmit)(const char*, void*);
    void (*_onCancel)(void*);
    void*   _ctx;
    char    _prompt[48];

    void repaint();
    void repaintInputBar();
    void repaintKeys();
    bool hitTest(int x, int y, char* outChar, uint8_t* outAction);
    void appendChar(char c);
    void backspace();
    void submit();
    void cancel();
    void cyclePage();
};

extern KeyboardWidget g_keyboard;   // singleton, defined in main.cpp
```

Callback uses raw function pointer + `void* ctx` rather than `std::function`
to avoid heap allocation on a device with constrained RAM.

---

## Canvas

`KeyboardWidget` takes over the **full 275×240 left canvas** while active.
The taskbar strip (x ≥ 275) is untouched.

**Alpha pages (0/1):**
```
y=0   +-----------------------------------+
      |  input bar  (h=40)                |
y=40  +-----------------------------------+
      |  row 1  Q W E R T Y U I O P  h=40|
y=80  |  row 2    A S D F G H J K L  h=40|
y=120 |  row 3  ⇧ Z X C V B N M  ⌫   h=40|
y=160 |  action     SYM  [SPACE]  OK h=40|
y=200 +-----------------------------------+
      |  (unused — dark fill)        h=40 |
y=240 +-----------------------------------+
```

**Symbol pages (2/3/4):**
```
y=0   +-----------------------------------+
      |  input bar  (h=40)                |
y=40  +-----------------------------------+
      |  symbol row 1   10 keys      h=40 |
y=80  |  symbol row 2   10 keys      h=40 |
y=120 |  symbol row 3   10 keys      h=40 |
y=160 |  action  ABC  NEXT  [SPACE] ⌫ OK  |
y=200 +-----------------------------------+
      |  symbol row 4   10 keys      h=40 |
y=240 +-----------------------------------+
```

Total: 40 (input) + 4×40 (key rows) + 40 (action) = 240 ✓

Symbol pages use a uniform 10-key-per-row grid for all 4 rows.
Row 4 (y=200..239) is only drawn when the page has enough symbols to fill it.

In `UpperAlpha` mode, pages 1–2 are suppressed; only uppercase A-Z is shown,
no symbol pages, no page-cycle button.

---

## Key geometry

```c
#define KB_INPUT_H    40    // input bar height
#define KB_ROW_H      40    // key row height
#define KB_KEY_W      27    // standard key width
#define KB_KEY_GAP     1    // gap between keys (visual only, not in hit test)
#define KB_CANVAS_W  275
```

### Row 1 — 10 keys (QWERTYUIOP)

```
x positions: i * (KB_CANVAS_W / 10)  for i = 0..9
width:        KB_CANVAS_W / 10  (27.5 → alternating 27/28)
```

### Row 2 — 9 keys (ASDFGHJKL)

```
x_start = (KB_CANVAS_W - 9 * KB_KEY_W) / 2  = 16
x_i     = x_start + i * KB_KEY_W
```

### Row 3 — ⇧ + 7 letters + ⌫

```
⇧ width = 40px (wider target — shift is easy to mis-tap)
⌫ width = 40px
7 letter keys = (KB_CANVAS_W - 40 - 40) / 7 = 27.9 → 28px each
layout: [⇧ 40][Z][X][C][V][B][N][M][⌫ 40]  = 40 + 7×28 + 40 = 276 ≈ 275
```

### Action row — alpha pages (0/1)

```
[SYM 46px][         SPACE 156px         ][OK 73px]  = 275px ✓
```

`SYM` label: `"123"` on page 0/1.

### Action row — symbol pages (2/3/4)

```
[ABC 40px][NEXT 40px][   SPACE 100px   ][⌫ 35px][OK 60px]  = 275px ✓
```

`NEXT` label cycles: `"#+="`  on page 2, `"~\`"` on page 3, `"123"` on page 4
(wraps back to page 2). `ABC` always returns to page 0.

`⌫` is in the action row for symbol pages because the uniform symbol grid has
no dedicated backspace key (unlike the alpha layout's row 3).

### Symbol pages — full key layout

All 32 printable ASCII punctuation marks + 10 digits distributed across 3 pages.
Uniform grid: 10 keys × 27px = 270px; last key fills to 275px.

**Page 2** (`"123"` → 30 keys across rows 1–3):

```
Row 1 (y= 40): 1  2  3  4  5  6  7  8  9  0
Row 2 (y= 80): !  @  #  $  %  ^  &  *  (  )
Row 3 (y=120): -  _  =  +  [  ]  {  }  \  |
Row 4 (y=200): (empty — dark fill)
```

**Page 3** (`"#+="`  → 20 keys across rows 1–2):

```
Row 1 (y= 40): ;  :  '  "  ,  .  /  <  >  ?
Row 2 (y= 80): ~  `  (8 empty slots — dark fill)
Row 3 (y=120): (empty)
Row 4 (y=200): (empty)
```

**Page 4** (`"~\`"` → 2 keys, rest empty):

```
Row 1 (y= 40): ~  `  (8 empty slots)
Row 2 (y= 80): (empty)
Row 3 (y=120): (empty)
Row 4 (y=200): (empty)
```

Page 4 exists to make `~` and `` ` `` reachable without squeezing them into an
already-full page. Empty key cells are filled with the background colour and
are non-interactive (hit test returns no character).

**Full coverage:** all 42 non-alpha characters (`0`–`9` + 32 ASCII punct) are
reachable within 3 SYM taps from the alpha page.

---

## Input bar

```
y=0
+---+------------------------------------------+----+
|   |  prompt text         input text▌         | ⌫  |
+---+------------------------------------------+----+
x=0 x=8                              x=240      x=248 x=275
```

- Prompt (left, greyed): e.g. `"Password:"` or `"Ticker:"`
- Input text (right-aligned to cursor): current `_buf` content, monospace font
- Cursor: blinking `▌` (1 Hz toggle in `tick()`)
- `⌫` in top-right (27px wide) — alternative backspace touch zone for
  users who find row-3 ⌫ hard to reach

Background: `KB_INPUT_BG = 0x2104` (match settings background).
Input text color: `0xFFFF`. Prompt color: `0x7BEF` (grey).

---

## Pages

| `_page` | Label | Keys | SYM/NEXT label |
|---------|-------|------|----------------|
| 0 | Lowercase | a–z | `"123"` |
| 1 | Uppercase | A–Z | `"123"` |
| 2 | Digits + punct batch 1 | `1–0 ! @ # … \ |` | `"#+="`  |
| 3 | Punct batch 2 | `; : ' " , . / < > ? ~ \`` | `"~\`"` |
| 4 | Misc / rare | `~ \`` (sparse) | `"123"` → wraps to page 2 |

**Page transitions:**

```
⇧ tap              → toggle page 0 ↔ 1
SYM tap (page 0/1) → go to page 2
NEXT tap (page 2)  → go to page 3
NEXT tap (page 3)  → go to page 4
NEXT tap (page 4)  → go to page 2  (wrap)
ABC  tap (any sym) → go to page 0
```

One-shot shift (optional): after typing one character on page 1, auto-revert
to page 0. Implemented via `_oneShot` bool set on ⇧ tap.

`UpperAlpha` mode: `_page` locked at 1. SYM, NEXT, ⇧ buttons all hidden.
Action row simplified to `[SPACE 202px][OK 73px]`.

---

## Key colour states

| State | Background | Label color |
|-------|-----------|-------------|
| Normal letter | `0x2104` (dark) | `0xFFFF` (white) |
| Action key (⇧, ⌫, SYM, OK) | `0x4208` (mid-grey) | `0xFFFF` |
| OK key | `0x03E0` (green) | `0x0000` (black) |
| Active shift (page=1) | `0x07E0` (green) | `0x0000` |
| Pressed (brief highlight) | `0xFFFF` (white) | `0x0000` |

"Pressed" state: on `TouchPhase::Press`, highlight the key for one `tick()`
then revert. Gives tactile feedback without debounce complexity.

---

## Input rules

- `appendChar(c)`: append if `_len < _maxLen`.
- `backspace()`: remove last char if `_len > 0`.
- `submit()`: call `_onSubmit(_buf, _ctx)`; `hide()`.
- `cancel()`: call `_onCancel(_ctx)`; `hide()`.
- OK button disabled (greyed) if `_len == 0`.
- `maxLen` enforced silently (no error state — key press is just ignored when full).

---

## Hit testing

```cpp
// Returns true if (x, y) hit a key; sets outChar or outAction
bool KeyboardWidget::hitTest(int x, int y, char* outChar, uint8_t* outAction) {
    int row = (y - KB_INPUT_H) / KB_ROW_H;   // 0..4
    // per-row x → key index lookup
    // outAction codes: ACT_SHIFT, ACT_BACKSPACE, ACT_SYM, ACT_SPACE, ACT_OK, ACT_CANCEL
}
```

Only `TouchPhase::Release` triggers key action (avoids accidental double-fire).
`TouchPhase::Press` triggers the pressed-highlight repaint only.

---

## Repaint strategy

Full repaint on `show()` and page change. Partial repaint on:
- Single character appended/deleted → redraw input bar only.
- Key press/release → redraw that key cell only (bounding box fill + label).

`_dirty` flag triggers full repaint on next `tick()`. Partial repaints
bypass `_dirty` and call their draw routines directly.

---

## Open questions

1. ~~**Symbol page layout**~~ — **resolved**: Option A — 3 symbol pages (2/3/4),
   each with full 40px key rows. All 42 non-alpha chars covered.
2. **Auto-shift after one uppercase** — pleasant UX but adds state; optional,
   implement as `_oneShot` flag.
3. **Cursor blink** — `tick()` toggles blink state at 500ms interval.
   Requires `millis()` delta tracking; low cost, confirm not annoying on device.
4. **Swipe-to-delete** — left swipe on input bar clears whole field. Deferred;
   not needed for MVP.

---

## Exit criteria

- **C1** — `Full` mode: all a–z, A–Z (via shift), 0–9, all 32 ASCII punctuation chars reachable within 3 SYM/NEXT taps from the alpha page.
- **C2** — `UpperAlpha` mode: only A–Z + backspace + OK visible; no SYM, no
  lowercase, no symbol row.
- **C3** — `maxLen` enforced; no buffer overrun.
- **C4** — `onSubmit` called with NUL-terminated string on OK tap.
- **C5** — `onCancel` called on `< back` tap with no change to caller state.
- **C6** — Input bar updates after every key press; cursor position correct.
- **C7** — No pixels drawn outside x:0..274 / y:0..239 (taskbar untouched).
- **C8** — `WifiFlow` password entry: submitted string passed verbatim to
  `WiFi.begin(ssid, pass)` (no truncation, no extra NUL issues).
