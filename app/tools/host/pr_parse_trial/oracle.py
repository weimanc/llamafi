#!/usr/bin/env python3
"""oracle.py — Python reference for the truncation policy (phase0-parse-heap
exit criterion 3): nearest-first by server `dst`, cap PR_MAX_AIRCRAFT, ground
excluded, records without lat/lon excluded.

Usage:
    ./pr_parse_trial fixture.json --leg C --cap 24 --dump-kept | ./oracle.py fixture.json 24

Compares the trial's KEPT lines against the oracle set; exits 0 on match.
"""
import json
import sys


def oracle_kept(path: str, cap: int) -> set[str]:
    d = json.load(open(path))
    planes = []
    for p in d.get("ac", []) or []:
        if not isinstance(p.get("lat"), (int, float)):
            continue
        if not isinstance(p.get("lon"), (int, float)):
            continue
        if p.get("alt_baro") == "ground":
            continue
        dst = p.get("dst")
        dst = float(dst) if isinstance(dst, (int, float)) else 1e9
        cs = (p.get("flight") or "").strip() or (p.get("hex") or "")
        planes.append((dst, cs[:8]))
    planes.sort(key=lambda t: t[0])
    return {cs for _, cs in planes[:cap]}


def main() -> None:
    fixture, cap = sys.argv[1], int(sys.argv[2])
    expected = oracle_kept(fixture, cap)
    got = set()
    for line in sys.stdin:
        if line.startswith("KEPT "):
            got.add(json.loads(line[5:])["callsign"])
        else:
            print(line, end="")
    missing, extra = expected - got, got - expected
    if missing or extra:
        print(f"ORACLE MISMATCH missing={sorted(missing)} extra={sorted(extra)}")
        sys.exit(1)
    print(f"ORACLE OK ({len(got)} kept)")


if __name__ == "__main__":
    main()
