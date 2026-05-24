#!/usr/bin/env python3
"""
spotify_state.py — refresh-token-aware /me/player wrapper.

Fetches Spotify Connect player state and emits a structured JSON object on
stdout. Used as the ground-truth source for all sync-001 TSYNC tests.

Usage:
    python3 tools/spotify_state.py
    python3 tools/spotify_state.py --pretty

Output JSON fields (all from /me/player?additional_types=episode):
    ok            bool   — false on HTTP error or 204 (no active device)
    isPlaying     bool
    progressMs    int    — ms position (may lag by < 1 s)
    durationMs    int
    volumePct     int    — 0..100; -1 if no device / unsupported
    shuffleState  bool
    repeatState   int    — 0=track, 1=context, 2=off  (mirrors Snapshot enum)
    trackUri      str
    trackName     str
    artistName    str    — first artist
    deviceId      str    — active Connect device ID
    deviceName    str
    deviceActive  bool   — true when volume_percent is not null

Exit codes: 0 = ok (200), 1 = error, 2 = 204 no active device.

Requirements:
    pip install (nothing — uses stdlib only)
    Valid creds at Spotify-Diy-Thing/data/spotify_diy_config.json
"""

import argparse
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "data" / "spotify_diy_config.json"

# RepeatState mapping from Spotify string to firmware int.
_REPEAT_MAP = {"track": 0, "context": 1, "off": 2}


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


def fetch_player(token: str) -> tuple[int, dict | None]:
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player?additional_types=episode",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return 204, None
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def parse_player(raw: dict) -> dict:
    item = raw.get("item") or {}
    artists = item.get("artists") or []
    artist_name = artists[0].get("name", "") if artists else ""
    dev = raw.get("device") or {}
    vp = dev.get("volume_percent")
    repeat_str = raw.get("repeat_state", "off")
    return {
        "ok": True,
        "isPlaying": bool(raw.get("is_playing")),
        "progressMs": int(raw.get("progress_ms") or 0),
        "durationMs": int(item.get("duration_ms") or 0),
        "volumePct": int(vp) if vp is not None else -1,
        "shuffleState": bool(raw.get("shuffle_state")),
        "repeatState": _REPEAT_MAP.get(repeat_str, 2),
        "trackUri": item.get("uri", ""),
        "trackName": item.get("name", ""),
        "artistName": artist_name,
        "deviceId": dev.get("id", ""),
        "deviceName": dev.get("name", ""),
        "deviceActive": vp is not None,
    }


def main():
    ap = argparse.ArgumentParser(description="Fetch Spotify Connect player state as JSON.")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print output")
    args = ap.parse_args()

    if not CONFIG.exists():
        print(json.dumps({"ok": False, "error": f"creds not found: {CONFIG}"}))
        sys.exit(1)

    cfg = json.loads(CONFIG.read_text())
    try:
        token = get_access_token(cfg)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"token refresh failed: {e}"}))
        sys.exit(1)

    status, raw = fetch_player(token)

    if status == 204:
        out = {"ok": False, "error": "204 no active device", "isPlaying": False,
               "progressMs": 0, "durationMs": 0, "volumePct": -1,
               "shuffleState": False, "repeatState": 2,
               "trackUri": "", "trackName": "", "artistName": "",
               "deviceId": "", "deviceName": "", "deviceActive": False}
        indent = 2 if args.pretty else None
        print(json.dumps(out, indent=indent))
        sys.exit(2)

    if status != 200 or raw is None:
        print(json.dumps({"ok": False, "error": f"HTTP {status}"}))
        sys.exit(1)

    out = parse_player(raw)
    indent = 2 if args.pretty else None
    print(json.dumps(out, indent=indent))
    sys.exit(0)


if __name__ == "__main__":
    main()
