#!/usr/bin/env python3
"""
spotify_drive.py — Spotify Connect API control (host-side).

Sends a single command to the active (or specified) Connect device via the
Web API. Used by sync-001 TSYNC tests to drive Spotify-side state changes
from the host without touching the DUT.

Usage:
    python3 tools/spotify_drive.py <command> [args...]

Commands:
    pause                           — pause playback
    play                            — resume playback
    next                            — skip to next track
    prev                            — skip to previous track
    seek <positionMs>               — seek to position (ms)
    setVolume <percent>             — set volume 0..100
    setShuffle <true|false>         — toggle shuffle
    setRepeat <off|context|track>   — set repeat mode
    transfer <deviceId>             — transfer playback to device ID

Exit 0 = command sent (HTTP 2xx). Exit 1 = error.

Requirements:
    pip install (nothing — uses stdlib only)
    Valid creds at Spotify-Diy-Thing/data/spotify_diy_config.json
    Active Spotify Premium session.
"""

import base64
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "data" / "spotify_diy_config.json"
API = "https://api.spotify.com/v1/me/player"


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


def api_put(token: str, url: str, body: dict | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def api_post(token: str, url: str, body: dict | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if not CONFIG.exists():
        die(f"creds not found: {CONFIG}")

    cfg = json.loads(CONFIG.read_text())
    try:
        token = get_access_token(cfg)
    except Exception as e:
        die(f"token refresh failed: {e}")

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "pause":
        status = api_put(token, f"{API}/pause")
    elif cmd == "play":
        status = api_put(token, f"{API}/play")
    elif cmd == "next":
        status = api_post(token, f"{API}/next")
    elif cmd == "prev":
        status = api_post(token, f"{API}/previous")
    elif cmd == "seek":
        if not args:
            die("seek requires <positionMs>")
        pos = int(args[0])
        url = f"{API}/seek?" + urllib.parse.urlencode({"position_ms": pos})
        status = api_put(token, url)
    elif cmd == "setVolume":
        if not args:
            die("setVolume requires <percent>")
        pct = int(args[0])
        if not 0 <= pct <= 100:
            die("volume must be 0..100")
        url = f"{API}/volume?" + urllib.parse.urlencode({"volume_percent": pct})
        status = api_put(token, url)
    elif cmd == "setShuffle":
        if not args:
            die("setShuffle requires <true|false>")
        state = args[0].lower()
        if state not in ("true", "false"):
            die("setShuffle arg must be true or false")
        url = f"{API}/shuffle?" + urllib.parse.urlencode({"state": state})
        status = api_put(token, url)
    elif cmd == "toggleShuffle":
        # Convenience: fetch current state, flip it.
        req = urllib.request.Request(
            f"{API}?additional_types=episode",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 204:
                    die("no active device — cannot toggle shuffle")
                raw = json.loads(r.read())
        except urllib.error.HTTPError as e:
            die(f"GET /me/player HTTP {e.code}")
        current = bool(raw.get("shuffle_state"))
        new_state = "false" if current else "true"
        url = f"{API}/shuffle?" + urllib.parse.urlencode({"state": new_state})
        status = api_put(token, url)
        print(f"shuffle: {current} → {new_state}")
    elif cmd == "setRepeat":
        if not args:
            die("setRepeat requires <off|context|track>")
        mode = args[0].lower()
        if mode not in ("off", "context", "track"):
            die("setRepeat arg must be off, context, or track")
        url = f"{API}/repeat?" + urllib.parse.urlencode({"state": mode})
        status = api_put(token, url)
    elif cmd == "transfer":
        if not args:
            die("transfer requires <deviceId>")
        status = api_put(token, API, body={"device_ids": [args[0]], "play": True})
    else:
        die(f"unknown command '{cmd}'. Run with no args for usage.")

    if 200 <= status < 300:
        print(f"ok HTTP {status}")
        sys.exit(0)
    else:
        die(f"command '{cmd}' failed HTTP {status}")


if __name__ == "__main__":
    main()
