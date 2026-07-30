# capture_adsb.py — ONE-SESSION 1 Hz ground-truth capture for PROP-006.
#
# Built ON TOP of app/tools/pr_adsb_probe.py (phase-0 tool): fetch(),
# ac_list() (which knows the real response shape), SITES, and
# fetch_radius_nm() are imported, not re-implemented. This file only adds
# the timed 1 Hz JSONL session + the study's Fix-schema loader.
#
# ⚠ DO NOT run casually. The per-IP 429 budget is SHARED with the DUT
# (TASK-313: host probes >=60 s). PROP-006's protocol: run from a network
# that is NOT the DUT's egress IP, or in a declared DUT-quiet window, ONCE,
# and reuse the fixtures forever. --ack forces that conversation.

import argparse
import json
import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))  # app/tools
from pr_adsb_probe import SITES, fetch, fetch_radius_nm, ac_list  # noqa: E402

from model import Fix, EARTH_R  # noqa: E402


def capture(lat, lon, nm, minutes, interval_s, out_path):
    end = time.time() + minutes * 60
    with open(out_path, "w") as f:
        while time.time() < end:
            t0 = time.time()
            code, dt, nbytes, parsed, err = fetch(lat, lon, nm)
            if code == 200 and not err:
                ac = ac_list(parsed)
                f.write(json.dumps({"t": t0, "aircraft": ac}) + "\n")
                f.flush()
                print(f"{time.strftime('%H:%M:%S')} {len(ac)} aircraft "
                      f"({nbytes} B, {dt:.2f}s)")
            else:
                print(f"{time.strftime('%H:%M:%S')} ERROR http={code} {err}",
                      file=sys.stderr)
            time.sleep(max(0.0, interval_s - (time.time() - t0)))


def fixtures_load(path, center_lat, center_lon):
    """JSONL -> {icao_hex: [Fix,...]} in ENU metres around the capture centre."""
    coslat = math.cos(math.radians(center_lat))
    tracks = {}
    t_base = None
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if t_base is None:
                t_base = rec["t"]
            for a in rec["aircraft"]:
                if a.get("lat") is None or a.get("lon") is None:
                    continue
                trk = a.get("track") or a.get("true_heading")
                gs = a.get("gs")
                if trk is None or gs is None:
                    continue
                x = math.radians(a["lon"] - center_lon) * EARTH_R * coslat
                y = math.radians(a["lat"] - center_lat) * EARTH_R
                tracks.setdefault(a["hex"], []).append(
                    Fix(t=rec["t"] - t_base, x=x, y=y,
                        track_deg=int(round(trk)) % 360,
                        gs_knots=int(round(gs))))
    return tracks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=SITES, default="schiphol",
                    help="probe-matrix site (pr_adsb_probe.py SITES)")
    ap.add_argument("--preset", type=float, default=15,
                    help="range preset km -> fetch radius via fetch_radius_nm()")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--out", default="capture.jsonl")
    ap.add_argument("--ack", action="store_true",
                    help="I confirm the 429-budget protocol (non-DUT egress "
                         "IP or declared DUT-quiet window) has been agreed")
    a = ap.parse_args()
    if not a.ack:
        sys.exit("Refusing: pass --ack after arranging the capture window "
                 "(see PROP-006 §Method / TASK-313 shared 429 budget).")
    lat, lon = SITES[a.site]
    capture(lat, lon, fetch_radius_nm(a.preset), a.minutes, a.interval, a.out)
