#!/usr/bin/env python3
"""
poll_latency_mock.py — PC-side Spotify /me/player RTT baseline.

Measures round-trip latency of GET /v1/me/player from this machine, using the
same credentials and token-refresh path as the DUT. No serial dependency.

Usage:
    python3 tools/poll_latency_mock.py [--count N] [--interval S]

Defaults: --count 20, --interval 5 (matches DUT poll cadence).

Output:
    [1/N] 312 ms  (HTTP 200)
    ...
    p50=305 ms  p95=418 ms  max=522 ms

Requirements: stdlib only. Valid creds at data/spotify_diy_config.json.
"""

import argparse
import base64
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "data" / "spotify_diy_config.json"


def get_access_token(cfg: dict) -> str:
    basic = base64.b64encode(
        f"{cfg['clientId']}:{cfg['clientSecret']}".encode()
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": cfg["refreshToken"],
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def poll_once(token: str) -> tuple[int, float]:
    """Returns (http_status, rtt_ms)."""
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player?additional_types=episode",
        headers={"Authorization": f"Bearer {token}"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            _ = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    t1 = time.monotonic()
    return status, (t1 - t0) * 1000.0


def main():
    ap = argparse.ArgumentParser(description="Measure Spotify /me/player RTT from this host.")
    ap.add_argument("--count", type=int, default=20, help="Number of polls (default 20)")
    ap.add_argument("--interval", type=float, default=5.0, help="Seconds between polls (default 5)")
    args = ap.parse_args()

    if not CONFIG.exists():
        print(f"ERROR: creds not found: {CONFIG}", file=sys.stderr)
        sys.exit(1)

    cfg = json.loads(CONFIG.read_text())
    try:
        token = get_access_token(cfg)
    except Exception as e:
        print(f"ERROR: token refresh failed: {e}", file=sys.stderr)
        sys.exit(1)

    rtts: list[float] = []
    for i in range(1, args.count + 1):
        try:
            status, rtt = poll_once(token)
        except Exception as e:
            print(f"[{i}/{args.count}] ERROR: {e}")
            continue

        rtts.append(rtt)
        print(f"[{i}/{args.count}] {rtt:.0f} ms  (HTTP {status})", flush=True)

        if i < args.count:
            time.sleep(args.interval)

    if not rtts:
        print("ERROR: no successful polls", file=sys.stderr)
        sys.exit(1)

    rtts_sorted = sorted(rtts)
    p50 = statistics.median(rtts_sorted)
    p95 = rtts_sorted[int(len(rtts_sorted) * 0.95)]
    mx = max(rtts_sorted)
    print(f"\np50={p50:.0f} ms  p95={p95:.0f} ms  max={mx:.0f} ms")


if __name__ == "__main__":
    main()
