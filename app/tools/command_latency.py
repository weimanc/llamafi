#!/usr/bin/env python3
"""
command_latency.py — Spotify command PUT RTT + state-propagation delay.

Measures two things per rep:
  put_rtt_ms    — time for the PUT/POST to return (pure HTTP cost)
  propagation_ms — time from command sent until GET /me/player reflects
                   the expected state change (PUT RTT + Spotify pipeline)

Usage:
    python3 tools/command_latency.py --command pause [--reps N] [--settle S]
    python3 tools/command_latency.py --command next  [--reps N] [--settle S]
    python3 tools/command_latency.py --command prev  [--reps N] [--settle S]

Defaults: --reps 5, --settle 4 (seconds between reps), poll interval 250 ms.

pause alternates pause/play each rep. next/prev skip repeatedly.

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
API = "https://api.spotify.com/v1/me/player"
POLL_INTERVAL = 0.25   # seconds between propagation-check GETs
POLL_TIMEOUT  = 10.0   # give up after this many seconds


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


def _http(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, float]:
    """Send PUT/POST; return (status, rtt_ms)."""
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            _ = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    return status, (time.monotonic() - t0) * 1000.0


def get_state(token: str) -> dict | None:
    """GET /me/player; return parsed object or None on 204/error."""
    req = urllib.request.Request(
        f"{API}?additional_types=episode",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return None
            return json.loads(r.read())
    except urllib.error.HTTPError:
        return None


def poll_until(token: str, predicate, t_cmd: float) -> float | None:
    """
    Poll GET /me/player at POLL_INTERVAL until predicate(state) is True.
    Returns propagation_ms from t_cmd, or None on timeout.
    """
    deadline = t_cmd + POLL_TIMEOUT
    while time.monotonic() < deadline:
        state = get_state(token)
        if state is not None and predicate(state):
            return (time.monotonic() - t_cmd) * 1000.0
        time.sleep(POLL_INTERVAL)
    return None


def ensure_playing(token: str):
    """Send play and wait up to 3s for isPlaying=True."""
    _http("PUT", f"{API}/play", token)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        s = get_state(token)
        if s and s.get("is_playing"):
            return
        time.sleep(0.25)


def main():
    ap = argparse.ArgumentParser(description="Measure Spotify command PUT RTT and propagation delay.")
    ap.add_argument("--command", required=True, choices=["pause", "next", "prev"],
                    help="Command to time")
    ap.add_argument("--reps", type=int, default=5, help="Repetitions (default 5)")
    ap.add_argument("--settle", type=float, default=4.0,
                    help="Seconds to wait between reps (default 4)")
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

    put_rtts: list[float] = []
    props: list[float] = []

    for i in range(1, args.reps + 1):
        # ── set up pre-command state ─────────────────────────────────────
        if args.command == "pause":
            ensure_playing(token)
            time.sleep(0.5)
            url = f"{API}/pause"
            method = "PUT"
            pre_uri = None

            def predicate(s, _=None):
                return not s.get("is_playing", True)

        else:
            # next / prev — capture current trackUri to detect change
            pre = get_state(token)
            if pre is None:
                print(f"[{i}/{args.reps}] SKIP — no active device", flush=True)
                continue
            pre_uri = (pre.get("item") or {}).get("uri", "")
            if args.command == "next":
                url = f"{API}/next"
            else:
                url = f"{API}/previous"
            method = "POST"

            def predicate(s, uri=pre_uri):
                return (s.get("item") or {}).get("uri", "") != uri

        # ── fire command ─────────────────────────────────────────────────
        t_cmd = time.monotonic()
        status, put_rtt = _http(method, url, token)
        put_rtts.append(put_rtt)

        if status not in (200, 201, 202, 203, 204):
            print(f"[{i}/{args.reps}] {args.command}  put_rtt={put_rtt:.0f}ms  HTTP {status} ERROR", flush=True)
            continue

        # ── poll for state change ─────────────────────────────────────────
        prop = poll_until(token, predicate, t_cmd)
        if prop is None:
            print(f"[{i}/{args.reps}] {args.command}  put_rtt={put_rtt:.0f}ms  propagation=TIMEOUT(>{POLL_TIMEOUT*1000:.0f}ms)", flush=True)
        else:
            props.append(prop)
            print(f"[{i}/{args.reps}] {args.command}  put_rtt={put_rtt:.0f}ms  propagation={prop:.0f}ms", flush=True)

        if i < args.reps:
            time.sleep(args.settle)

    # ── summary ──────────────────────────────────────────────────────────
    print()
    if put_rtts:
        s = sorted(put_rtts)
        p50 = statistics.median(s)
        p95 = s[int(len(s) * 0.95)]
        print(f"PUT RTT    p50={p50:.0f}ms  p95={p95:.0f}ms  max={max(s):.0f}ms  (n={len(s)})")
    if props:
        s = sorted(props)
        p50 = statistics.median(s)
        p95 = s[int(len(s) * 0.95)]
        print(f"propagation p50={p50:.0f}ms  p95={p95:.0f}ms  max={max(s):.0f}ms  (n={len(s)})")


if __name__ == "__main__":
    main()
