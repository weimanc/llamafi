#!/usr/bin/env python3
"""pr_delta_smoke.py — TASK-358 (M-DISPLAY-DELTA-COMMON pt 2 / ADR-052) DUT
screendump-diff gate. TASK-358 fixed PlaneRadar's whole-scene-repaint tearing
bug (per-aircraft dirty-rect redraw via `_redrawOneAircraft()` +
`withViewportRepair()`) but its own Gate called for a
`clock_delta_smoke.py`-style screendump-diff assertion that was never
written — flagged as a gap in that task's own notes. This fills it.

Modeled on clock_delta_smoke.py's steady-state screendump-diff pattern, but
uses PlaneRadar's `set prInjectAircraft`/`set prClearInject` debug surface
(TASK-276/T_PR_06 pattern) for deterministic synthetic scenes instead of
clock_delta_smoke's "same minute" wait — no real-network dependency.

  T_PRD_01 — static steady-state, ZERO diff, NO mask. Two stationary
  (gsKnots=0) aircraft, captured only after >= 4*PR_INTERP_TAU_MS
  (planeRadarApp.h, tau=2000ms -> wait >=8s) so any dead-reckon/continuity
  offset has fully decayed (already exactly 0 for a first-ever injection —
  "unmatched aircraft get offset 0, no continuity claim" — but wait anyway:
  robust against a rerun that reuses a callsign still tracked from a prior
  pass). At true steady state, _motionPx() evaluated at any two instants is
  bit-identical, so tick()'s per-aircraft dirty check (`x0!=x1||y0!=y1`)
  never fires and _redrawOneAircraft() never runs at all — a STRONGER
  assertion than clock_delta_smoke's (that one still allows the colon to
  legitimately change; this allows nothing) and the direct regression check
  against the pre-TASK-358 bug: the old whole-scene `_render()` repainted
  every ~10Hz tick regardless of dirty state, reproducing the same pixels
  via wasteful full-scene churn a diff alone can't distinguish from "nothing
  happened" — T_PRD_02 below is what actually catches the SCOPING failure
  mode; this one catches "does a redraw fire when it must not".

  T_PRD_02 — one moving aircraft (nonzero gsKnots, straight-line track) +
  one stationary aircraft placed far away, scoped diff. Outside a generous
  mask around the moving aircraft's start->end pixel path (computed from the
  same equirectangular projection + dead-reckon math planeRadarApp.h uses,
  padded well past the worst-case symbol+vector+tag reach), every pixel —
  the stationary aircraft, the grid rings, the crosshair, and any runway
  overlay that happens to be in range — must be bit-identical between the
  two captures. This directly validates the dirty-rect SCOPING claim (only
  the moving aircraft's own footprint gets touched), not just "some redraw
  happened somewhere".

Needs debug firmware (screendump serial command). Leaves the device on
prRange 10km (restored to whatever it was before), real polling resumed
(prClearInject), switched back to app 0.
"""
import math
import sys
import time
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from screendump import DutLite, dump_with_retry, autodetect_port  # noqa: E402

# ---- planeRadarApp.h / planeRadarConfig.h constants, mirrored here (keep in
# sync — same posture as prloc_ve_smoke.py's mirrored strip geometry) ----
PR_CX, PR_CY, PR_R = 120, 120, 118
PR_KM_PER_DEG_LON = 111.320
PR_KM_PER_DEG_LAT = 110.574
PR_KM_PER_NM = 1.852
PR_FETCH_RING3_TO_OUTER = 4.0 / 3.0
PR_INTERP_TAU_MS = 2000.0

DISC_REGION = (0, 0, 240, 240)   # x,y,w,h — disc is cx=120,cy=120,r=118 (x/y:2..238); small margin
SETTLE_S = 4.0 * PR_INTERP_TAU_MS / 1000.0 + 1.0   # >= 4*tau (8s) + 1s margin

results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def px_per_km(range_km):
    outer_km = range_km * PR_FETCH_RING3_TO_OUTER
    return PR_R / outer_km


def project(lat, lon, home_lat, home_lon, pxkm):
    """Mirrors planeRadarApp.h::_project() exactly."""
    dx_km = (lon - home_lon) * PR_KM_PER_DEG_LON * math.cos(math.radians(home_lat))
    dy_km = (lat - home_lat) * PR_KM_PER_DEG_LAT
    return PR_CX + dx_km * pxkm, PR_CY - dy_km * pxkm


def offset_latlon(home_lat, home_lon, km_east, km_north):
    """Inverse of project(): a point km_east/km_north of home, as lat/lon."""
    dlon = km_east / (PR_KM_PER_DEG_LON * math.cos(math.radians(home_lat)))
    dlat = km_north / PR_KM_PER_DEG_LAT
    return home_lat + dlat, home_lon + dlon


def dump_region(dut, region):
    x, y, w, h = region
    return dump_with_retry(dut, x, y, w, h)


port = autodetect_port()
print(f"== opening {port} (DTR reset) ==", flush=True)
dut = DutLite(port)

orig_range = dut.cmd("get prRange")
orig_range_km = orig_range.get("val", 10)
print("orig prRange:", orig_range, flush=True)

dut.cmd("switchApp 9")   # AppId::PlaneRadar (TASK-347: Settings moved before it, shifting 10→9)
time.sleep(1.0)

loc = dut.cmd("get prloc")
active = loc.get("active", 0)
locs = loc.get("locs") or []
home = locs[active] if active < len(locs) else {}
home_lat = home.get("lat")
home_lon = home.get("lon")
report("V0 got active location lat/lon for injection math",
       home_lat is not None and home_lon is not None, str(loc))
if home_lat is None or home_lon is None:
    print("cannot continue without a home location — aborting", flush=True)
    dut.cmd("set prClearInject 1")
    dut.cmd("switchApp 0")
    sys.exit(1)

RANGE_KM = 10   # kPrPresetKm[1] — mid preset, plenty of disc room either side
dut.cmd(f"set prRange {RANGE_KM}")
time.sleep(0.3)
pxkm = px_per_km(RANGE_KM)

# =========================================================================
# T_PRD_01 — static steady-state: zero diff, no mask
# =========================================================================
lat1, lon1 = offset_latlon(home_lat, home_lon, km_east=0.0, km_north=1.5)
lat2, lon2 = offset_latlon(home_lat, home_lon, km_east=0.0, km_north=-1.5)
rec = (f"PRD1A,A320,{lat1:.6f},{lon1:.6f},0.8,0,0,0,5000;"
       f"PRD1B,B738,{lat2:.6f},{lon2:.6f},0.8,180,180,0,6000")
r = dut.cmd(f"set prInjectAircraft {rec}")
report("T_PRD_01 setup: injection accepted", bool(r.get("ok")), str(r))

print(f"  [T_PRD_01] waiting {SETTLE_S:.1f}s (>=4*tau) for continuity offset to settle…",
      flush=True)
time.sleep(SETTLE_S)

a = dump_region(dut, DISC_REGION)
time.sleep(3.0)
b = dump_region(dut, DISC_REGION)

diff = (a != b)
ndiff = int(diff.sum())
report("T_PRD_01 static steady-state: zero diff, no redraw fires (no mask)",
       ndiff == 0, f"{ndiff} px changed")

# =========================================================================
# T_PRD_02 — one moving + one (distant) stationary aircraft: scoped diff
# =========================================================================
GS_KNOTS = 200            # modest: keeps worst-case total displacement (over
                          # however long the two screendump reads actually
                          # take) safely short of the rim-dot fallback
                          # threshold (PR_R - PR_SYMBOL_INSET = 106px)
TRACK_DEG = 90            # due east — straight line, monotonic in x, so the
                          # start/end pixel pair bounds every point visited
MOVE_START_KM_EAST = 1.5
STAT_KM_WEST = 8.0        # far enough west that the generous mask below can
                          # never reach it, whatever the actual timing turns
                          # out to be

lat_m, lon_m = offset_latlon(home_lat, home_lon, km_east=MOVE_START_KM_EAST, km_north=0.0)
lat_s, lon_s = offset_latlon(home_lat, home_lon, km_east=-STAT_KM_WEST, km_north=0.0)
rec2 = (f"PRD2M,A320,{lat_m:.6f},{lon_m:.6f},1.0,{TRACK_DEG},{TRACK_DEG},{GS_KNOTS},35000;"
        f"PRD2S,C172,{lat_s:.6f},{lon_s:.6f},4.3,270,270,0,8000")
t_inject = time.monotonic()
r2 = dut.cmd(f"set prInjectAircraft {rec2}")
report("T_PRD_02 setup: injection accepted", bool(r2.get("ok")), str(r2))

time.sleep(1.0)
c = dump_region(dut, DISC_REGION)
time.sleep(6.0)
d = dump_region(dut, DISC_REGION)
t_end = time.monotonic()

speed_px_s = GS_KNOTS * PR_KM_PER_NM / 3600.0 * pxkm
start_x, start_y = project(lat_m, lon_m, home_lat, home_lon, pxkm)
elapsed = t_end - t_inject   # host-measured upper bound on the firmware's dtSec
ang = math.radians(TRACK_DEG - 90.0)   # _degToRad(): compass -> screen math angle
end_x = start_x + speed_px_s * elapsed * math.cos(ang)
end_y = start_y + speed_px_s * elapsed * math.sin(ang)

# PAD: worst-case tag reach is PR_TAG_GAP(9) + up to 9 visible chars *
# PR_TAG_CHAR_W(6) = 9 + 54 = 63px from the symbol; +7px for a generous
# margin over vector/erase-pad/float-rounding slop.
PAD = 70
mx0 = max(0, int(min(start_x, end_x) - PAD))
mx1 = min(DISC_REGION[2], int(max(start_x, end_x) + PAD) + 1)
my0 = max(0, int(min(start_y, end_y) - PAD))
my1 = min(DISC_REGION[3], int(max(start_y, end_y) + PAD) + 1)
print(f"  [T_PRD_02] moving aircraft path px=({start_x:.1f},{start_y:.1f})->"
      f"({end_x:.1f},{end_y:.1f}) elapsed={elapsed:.1f}s mask=x[{mx0}:{mx1}] y[{my0}:{my1}]",
      flush=True)

diff2 = (c != d)
in_mask = np.zeros_like(diff2)
in_mask[my0:my1, mx0:mx1] = True
outside_ndiff = int((diff2 & ~in_mask).sum())
inside_ndiff = int((diff2 & in_mask).sum())

report("T_PRD_02 moving aircraft: zero diff OUTSIDE mask "
       "(stationary aircraft/grid/crosshair untouched)",
       outside_ndiff == 0, f"{outside_ndiff} px changed outside mask")
report("T_PRD_02b sanity: motion WAS captured inside the mask (not a trivial pass)",
       inside_ndiff > 0, f"{inside_ndiff} px changed inside mask")

# ---- restore pre-test state ----
dut.cmd("set prClearInject 1")
dut.cmd(f"set prRange {orig_range_km}")
dut.cmd("switchApp 0")

npass = sum(1 for _, ok, _ in results if ok)
nfail = len(results) - npass
print(f"\n== TASK-358 PR DELTA SMOKE: {npass}/{len(results)} PASS ==", flush=True)
sys.exit(1 if nfail else 0)
