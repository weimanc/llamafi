# R&D — Winamp Vis Video Analysis Method

> Author: R&D Engineer
> Date: 2026-05-16
> Status: final — handover for repeat analysis
> Subject: How to extract spectrum analyzer characteristics from a Winamp screencast

---

## Goal

Extract pixel-accurate measurements from a screencast of Winamp 2 running the spectrum analyzer:
- Scale factor (screen pixels per skin pixel)
- Window origin (crop offset)
- Vis area bounds (x, y, w, h in skin pixels)
- Bar width and gap width
- Colour gradient (per-row, mapped to VISCOLOR.TXT)
- Peak dot colour
- Decay rate

---

## Prerequisites

```sh
pip install pillow numpy
apt install ffmpeg        # or equivalent
```

Input files needed:
- Screencast video (e.g. `resource/Screencast_20260516_060344.webm`)
- Skin file for cross-reference: `skins/base-2.91.wsz` → `MAIN.BMP` and `VISCOLOR.TXT`

Extract skin files:
```sh
cd /tmp && cp /path/to/skins/base-2.91.wsz base.zip && unzip -o base.zip MAIN.BMP VISCOLOR.TXT
```

---

## Step 1 — Extract frames from the video

```sh
ffmpeg -i resource/Screencast_20260516_060344.webm \
  -vf fps=10 /tmp/vis_frames/frame_%04d.png
```

Use `fps=10` for a quick survey; raise to the native framerate (`fps=59` for this file) if you need decay-rate measurements.

Check video properties first:
```sh
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate resource/Screencast_20260516_060344.webm
```

Our recording: 689×316, VP9, ~59 fps.

---

## Step 2 — Determine scale factor

The vis background is a 1-pixel alternating dot-matrix in the skin (`MAIN.BMP`):
- Even positions (x+y even): colour (24, 24, 41) — call these "O" pixels
- Odd positions (x+y odd): colour (0, 0, 0) — call these "." pixels

At scale S, the period of this grid in frame pixels = 2×S.

**Method — scan a horizontal line through the vis area in a frame where the spectrum is blank (or low):**

```python
from PIL import Image
import numpy as np

frame = Image.open("/tmp/vis_frames/frame_0001.png")
px = np.array(frame)

# Pick a row known to be inside the vis (adjust y after first pass)
y_scan = 140   # rough guess — refine after finding window origin

row = px[y_scan, :, :]
# Find the period by looking at where the dark "." dots repeat
# A "." pixel is near (0,0,0); an "O" pixel is near (24,24,41)
dark = (row[:, 0] < 10) & (row[:, 1] < 10) & (row[:, 2] < 10)

# Find run-to-run distance between dark pixels
dark_idx = np.where(dark)[0]
gaps = np.diff(dark_idx)
period = np.median(gaps[gaps < 10])   # filter outliers (bar pixels aren't dark)
print(f"dot period = {period} frame pixels")
scale = period / 2
print(f"scale = {scale}x")
```

Our result: period = 5 frame pixels → **scale = 2.5×**.

---

## Step 3 — Find the window origin and vis bounds using MAIN.BMP

The vis area boundary in `MAIN.BMP` is marked by two blue dotted lines:
- **Vertical line** on the LEFT: x=22, y=42..60 — alternating (0,82,132) and (94,149,234)
- **Horizontal line** on the BOTTOM: y=60, x=22..102 — same blue colours

These blue pixels are distinct from everything else in the skin. Locate them in the video frame to get the window origin.

```python
from PIL import Image
import numpy as np

frame = Image.open("/tmp/vis_frames/frame_0001.png")
px = np.array(frame)

# Find pixels matching the bright blue dot: (94, 149, 234)
mask = (
    (px[:, :, 0] > 80)  & (px[:, :, 0] < 110) &   # R ~ 94
    (px[:, :, 1] > 140) & (px[:, :, 1] < 160) &   # G ~ 149
    (px[:, :, 2] > 220) & (px[:, :, 2] < 250)      # B ~ 234
)
ys, xs = np.where(mask)
print(f"blue dot pixels: x={xs.min()}..{xs.max()}, y={ys.min()}..{ys.max()}")
```

From the matched pixels, the leftmost blue column and bottommost blue row give you the left/bottom dotted lines in frame coordinates. Convert to window origin:

```python
# left dotted line is at skin x=22; bottom dotted line is at skin y=60
frame_left_line_x  = xs.min()          # frame x of the vertical line
frame_bottom_line_y = ys.max()         # frame y of the horizontal line

win_x = frame_left_line_x  - round(22 * scale)
win_y = frame_bottom_line_y - round(60 * scale)
print(f"window origin in frame: ({win_x}, {win_y})")
```

Then the vis content area in frame pixels:
```python
# Skin vis content: x=23..102 (left of left line + 1 .. right edge), y=42..59 (above bottom line)
vis_frame_x1 = round(win_x + 23 * scale)
vis_frame_x2 = round(win_x + 102 * scale)
vis_frame_y1 = round(win_y + 42 * scale)
vis_frame_y2 = round(win_y + 59 * scale)
print(f"vis frame rect: x={vis_frame_x1}..{vis_frame_x2}, y={vis_frame_y1}..{vis_frame_y2}")
```

**Verify** by annotating a frame with a coloured rectangle and visually inspecting:

```python
from PIL import ImageDraw

img = Image.open("/tmp/vis_frames/frame_0001.png").copy()
draw = ImageDraw.Draw(img)
draw.rectangle([vis_frame_x1, vis_frame_y1, vis_frame_x2, vis_frame_y2],
               outline=(0, 255, 0), width=2)
img.save("/tmp/vis_check.png")
```

The rectangle should tightly enclose the spectrum display area with no overshoot onto skin chrome.

---

## Step 4 — Count bars and measure bar geometry

Choose a frame where most bars are at medium height (not maxed, not empty). Scan a horizontal line at mid-height of the vis.

```python
# mid-height in frame pixels
y_mid = (vis_frame_y1 + vis_frame_y2) // 2

row = px[y_mid, vis_frame_x1:vis_frame_x2+1, :]

# A bar pixel is NOT near (0,0,0) or (24,24,41) — it has a non-trivial colour
bg_O = np.array([24, 24, 41])
bg_dot = np.array([0, 0, 0])

def is_bg(p):
    return (np.linalg.norm(p - bg_O) < 15) or (np.linalg.norm(p - bg_dot) < 15)

is_bar = np.array([not is_bg(row[i]) for i in range(len(row))])

# Find runs of bar vs gap
import itertools
runs = [(k, sum(1 for _ in g)) for k, g in itertools.groupby(is_bar)]
bar_runs  = [l for k, l in runs if k]
gap_runs  = [l for k, l in runs if not k]

print(f"bar widths (frame px): {sorted(set(bar_runs))}, median={np.median(bar_runs):.1f}")
print(f"gap widths (frame px): {sorted(set(gap_runs))}, median={np.median(gap_runs):.1f}")

bar_w_native = np.median(bar_runs) / scale
gap_w_native = np.median(gap_runs) / scale
print(f"bar width native: {bar_w_native:.2f} px, gap: {gap_w_native:.2f} px")
```

Our result (2026-05-16): bar = ~3 native px, gap = ~1 native px → 4 px per bar unit → **19 bars in 76 px**.

---

## Step 5 — Extract the colour gradient

Find a frame where at least one bar reaches near-maximum height. Pick the column with the tallest bar.

```python
# Scan every column in the vis area; find the one with the most non-background pixels vertically
best_col = -1
best_height = 0

for col_x in range(vis_frame_x1, vis_frame_x2+1):
    col_pixels = px[vis_frame_y1:vis_frame_y2+1, col_x, :]
    n_bar = sum(1 for p in col_pixels if not is_bg(p))
    if n_bar > best_height:
        best_height = n_bar
        best_col = col_x

print(f"tallest bar at frame x={best_col}, height={best_height} frame px")

# Extract colours top-to-bottom along that column
col_pixels = px[vis_frame_y1:vis_frame_y2+1, best_col, :]
for i, p in enumerate(col_pixels):
    if not is_bg(p):
        print(f"  frame row {i} (skin y={vis_frame_y1//round(scale)+i}): RGB=({p[0]},{p[1]},{p[2]})")
```

Map extracted RGB values to VISCOLOR.TXT entries by proximity:

```python
import zipfile, re

wsz_path = "skins/base-2.91.wsz"
with zipfile.ZipFile(wsz_path) as z:
    txt = z.read("VISCOLOR.TXT").decode("latin-1")

viscolors = []
for m in re.finditer(r"(\d+),\s*(\d+),\s*(\d+)", txt):
    viscolors.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))

def nearest_viscolor(rgb):
    best_i, best_d = 0, 1e9
    for i, vc in enumerate(viscolors):
        d = sum((a-b)**2 for a, b in zip(rgb, vc)) ** 0.5
        if d < best_d:
            best_d, best_i = d, i
    return best_i, best_d

for i, p in enumerate(col_pixels):
    if not is_bg(p):
        idx, dist = nearest_viscolor(p)
        print(f"  row {i}: RGB=({p[0]},{p[1]},{p[2]}) → VISCOLOR[{idx}] dist={dist:.1f}")
```

---

## Step 6 — Measure peak dot decay rate

Use a sequence of frames at native framerate (59 fps). Find a frame where a bar drops sharply, then track the peak dot y position across subsequent frames.

```python
import glob, os

frames = sorted(glob.glob("/tmp/vis_frames_full/frame_*.png"))

# Pick a column (bar) to track
col_x = best_col

def find_peak_dot_y(frame_path, col_x, vis_y1, vis_y2):
    px = np.array(Image.open(frame_path))
    col = px[vis_y1:vis_y2+1, col_x, :]
    peak_color = np.array([150, 150, 150])   # VISCOLOR[23]
    for i, p in enumerate(col):
        if np.linalg.norm(p - peak_color) < 20:
            return i
    return None

dot_positions = [(i, find_peak_dot_y(f, col_x, vis_frame_y1, vis_frame_y2))
                 for i, f in enumerate(frames[100:120], start=100)]
print(dot_positions)
# Each frame = 1/59 s. Rows dropped per frame = decay rate in frame pixels.
# Divide by scale to get native pixels per frame.
```

Our result: ~8 frame pixels drop in 200 ms at 59 fps → ~3–4 native px / frame.

---

## Key pitfalls from the 2026-05-16 analysis

1. **VU vs spectrum confusion.** The recording was initially misidentified as showing only the VU meter because the lower half of the vis appeared empty. Verify the mode before measuring: spectrum bars appear as many narrow vertical columns; VU appears as two wide horizontal fills.

2. **Wrong vis bounds (first attempt).** Computed window origin from the Winamp window frame border, not from the dotted lines in MAIN.BMP. The dotted lines are authoritative — anchor to those.

3. **Background grid confusion.** The alternating O/. grid is the vis background texture, not a grid of gaps between bars. Don't mistake O-pixel columns as bar boundaries.

4. **Scanning an empty column.** When picking a column for colour analysis, always find the tallest bar first. An arbitrary column may land in a gap or a very short bar, giving only background colours.

5. **Scale not an integer.** Scale = 2.5× means skin pixels don't land on exact frame pixel boundaries. Use `round()` consistently when converting; never use integer division.

---

## Reference measurements (2026-05-16, `base-2.91.wsz`)

| Property | Value |
|---|---|
| Video | 689×316 VP9 ~59 fps |
| Scale | 2.5× |
| Window origin in frame | (~1.5, ~9.5) |
| Vis frame rect | x=59..256, y=114..157 (198×44 px) |
| Vis skin rect | x=23..102, y=42..59 (80×18 px) |
| Active spectrum area | x=24..99, y=43..58 (76×16 skin px) |
| Bar width | 3 skin px |
| Gap width | 1 skin px |
| Bars | 19 (76 px / 4 px per bar) |
| Levels | 16 (VISCOLOR[2..17]) |
| Peak dot colour | VISCOLOR[23] = (150,150,150) = 0x94B2 |
| Wave colour | VISCOLOR[18] = (255,255,255) = 0xFFFF |
| Decay rate | ~3–4 skin px/frame at 60 Hz |
