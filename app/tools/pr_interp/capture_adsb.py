# capture_adsb.py — ONE-SESSION ground-truth capture for PROP-006.
#
# ⚠ DO NOT run casually. The per-IP 429 budget is SHARED with the DUT
# (TASK-313: host probes >=60 s). PROP-006's protocol: run from a network
# that is NOT the DUT's egress IP, or in a declared DUT-quiet window, ONCE,
# and reuse the fixtures forever. The --ack flag exists to force that
# conversation to have happened.
#
# Output: JSONL, one line per poll: {"t": epoch_s, "aircraft": [raw adsb.fi
# aircraft dicts]}. fixtures_load() converts to the study's Fix schema so
# score.py / preview_interp.py run unmodified on real data.

import argparse
import json
import math
import sys
import time
import urllib.request

from model import Fix, EARTH_R

URL = "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}"


def capture(lat, lon, nm, minutes, interval_s, out_path):
    end = time.time() + minutes * 60
    with open(out_path, "w") as f:
        while time.time() < end:
            t0 = time.time()
            try:
                with urllib.request.urlopen(
                        URL.format(lat=lat, lon=lon, nm=nm), timeout=10) as r:
                    data = json.loads(r.read())
                ac = data.get("aircraft", data.get("ac", []))
                f.write(json.dumps({"t": t0, "aircraft": ac}) + "\n")
                f.flush()
                print(f"{time.strftime('%H:%M:%S')} {len(ac)} aircraft")
            except Exception as e:  # noqa: BLE001 — log-and-continue capture loop
                print(f"{time.strftime('%H:%M:%S')} ERROR {e}", file=sys.stderr)
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
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--nm", type=int, default=15)
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
    capture(a.lat, a.lon, a.nm, a.minutes, a.interval, a.out)
