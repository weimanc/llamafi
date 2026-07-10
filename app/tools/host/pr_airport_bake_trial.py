#!/usr/bin/env python3
"""pr_airport_bake_trial.py — M-PLANERADAR phase 0: airport/runway DB variant sizing.

Design: docs/architecture/designs/M-PLANERADAR/phase0-airport-db.md

Replicates the reference build_large_airports.py selection logic (large_airport
class, non-helipad runways with both endpoints) against a PINNED OurAirports
commit, then for each bake variant reports record counts, exact flash bytes
(reference struct layout: Airport 16 B, Runway 24 B, both padded), and the
in-range content check around the home default.

Variants: V-global (no filter), V-europe (lat 35..62, lon -11..30),
V-nl500 (500 km around home default). Also answers the medium_airport open
question with counts.

Usage: pr_airport_bake_trial.py [--commit <sha-or-main>]
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import urllib.request

# Pin: resolve once, record here after first run (phase0-airport-db.md adoption plan).
DEFAULT_COMMIT = "main"  # TODO(bake adoption): replace with pinned commit sha
BASE = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/{commit}/"

HOME = (52.3676, 4.9041)
SIZEOF_AIRPORT = 16   # char[5] + pad + 2×int32 (4-byte aligned)
SIZEOF_RUNWAY = 24    # u16 + pad + 4×int32 + u16 + pad


def fetch_csv(url: str) -> list[dict[str, str]]:
    with urllib.request.urlopen(url, timeout=120) as resp:
        text = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


# --- reference selection logic (mirrors build_large_airports.py) --------------
def is_h_designator(s: str) -> bool:
    if not s or s[0] != "H":
        return False
    rest = s[1:]
    if not rest or rest[0] in "-_":
        return True
    return rest.isdigit()


def is_helipad(row: dict[str, str]) -> bool:
    le = (row.get("le_ident") or "").strip().upper()
    he = (row.get("he_ident") or "").strip().upper()
    if not is_h_designator(le) and not is_h_designator(he):
        return False
    try:
        length_ft = int(row.get("length_ft") or 0)
    except ValueError:
        length_ft = 0
    if is_h_designator(le) and is_h_designator(he):
        return True
    return length_ft < 2500


def runway_ok(row: dict[str, str]) -> bool:
    if (row.get("closed") or "0").strip() == "1":
        return False
    if is_helipad(row):
        return False
    for k in ("le_latitude_deg", "le_longitude_deg",
              "he_latitude_deg", "he_longitude_deg"):
        v = row.get(k)
        if not v or not v.strip():
            return False
    return True


def haversine_km(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# --- variants ------------------------------------------------------------------
def v_global(ap) -> bool:
    return True


def v_europe(ap) -> bool:
    return 35.0 <= ap["lat"] <= 62.0 and -11.0 <= ap["lon"] <= 30.0


def v_nl500(ap) -> bool:
    return haversine_km((ap["lat"], ap["lon"]), HOME) <= 500.0

VARIANTS = [("V-global", v_global), ("V-europe", v_europe), ("V-nl500", v_nl500)]


def select(airports_rows, runways_rows, classes: tuple[str, ...]):
    """Return (airports, runways_by_airport) for the given airport classes."""
    aps = {}
    for row in airports_rows:
        if (row.get("type") or "").strip() not in classes:
            continue
        ident = (row.get("ident") or "").strip()
        try:
            lat = float(row["latitude_deg"])
            lon = float(row["longitude_deg"])
        except (KeyError, ValueError):
            continue
        if len(ident) != 4:
            continue
        aps[ident] = {"ident": ident, "lat": lat, "lon": lon, "runways": 0}
    for row in runways_rows:
        ident = (row.get("airport_ident") or "").strip()
        if ident in aps and runway_ok(row):
            aps[ident]["runways"] += 1
    return [a for a in aps.values() if a["runways"] > 0]


def report(name, aps):
    n_ap = len(aps)
    n_rw = sum(a["runways"] for a in aps)
    flash = n_ap * SIZEOF_AIRPORT + n_rw * SIZEOF_RUNWAY
    in37 = [a for a in aps if haversine_km((a["lat"], a["lon"]), HOME) <= 36.8]
    in100 = [a for a in aps if haversine_km((a["lat"], a["lon"]), HOME) <= 100.0]
    print(f"{name:<10} airports={n_ap:>5} runways={n_rw:>5} "
          f"flash={flash:>7} B ({flash/1024:.1f} KB)  "
          f"in36.8km={len(in37)} in100km={len(in100)} "
          f"[{', '.join(a['ident'] for a in in100)}]")
    return flash


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--commit", default=DEFAULT_COMMIT)
    args = p.parse_args()
    base = BASE.format(commit=args.commit)

    print(f"fetching OurAirports CSVs @ {args.commit} ...", file=sys.stderr)
    airports_rows = fetch_csv(base + "airports.csv")
    runways_rows = fetch_csv(base + "runways.csv")
    print(f"airports.csv rows={len(airports_rows)} runways.csv rows={len(runways_rows)}",
          file=sys.stderr)

    print("\n== large_airport only (reference filter) ==")
    large = select(airports_rows, runways_rows, ("large_airport",))
    for name, pred in VARIANTS:
        report(name, [a for a in large if pred(a)])

    print("\n== large + medium (OQ: class filter) ==")
    both = select(airports_rows, runways_rows, ("large_airport", "medium_airport"))
    for name, pred in VARIANTS:
        report(name, [a for a in both if pred(a)])

    print("\nmedium-only delta inside V-europe = inclusion cost of the OQ decision")


if __name__ == "__main__":
    main()
