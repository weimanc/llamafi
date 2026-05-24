#!/usr/bin/env python3
"""T073 — assert /me/player is a strict superset of /me/player/currently-playing
for the fields the firmware reads.

Catches future Spotify-side regressions of ADR-015's premise. Exit 0 = pass,
exit 1 with a diff report = fail.

Usage:
  python3 tools/test_player_endpoint_superset.py

Preconditions:
  - Valid creds at Spotify-Diy-Thing/data/spotify_diy_config.json
  - An active Spotify Connect device (any client) playing a track during the
    test window. Without a track, both endpoints return 204 No Content and
    the test reports "skipped — no track playing".
"""
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "data" / "spotify_diy_config.json"

# Fields the firmware actually consumes from the response. Any field present
# in /currently-playing must also be present in /me/player with a matching
# value (progress_ms drift allowed).
FIRMWARE_FIELDS = [
    "is_playing",
    "progress_ms",
    "currently_playing_type",
    "context",       # context.uri compared
    "item",          # item.uri compared
    "actions",       # actions.disallows keys compared
]
# Field that ONLY /me/player reliably returns and the firmware now depends on.
DEVICE_VOLUME_PATH = ("device", "volume_percent")
PROGRESS_DRIFT_LIMIT_MS = 1000  # spec allows ≤ 1 s drift between sequential calls


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def get_access_token(cfg):
    basic = base64.b64encode(f"{cfg['clientId']}:{cfg['clientSecret']}".encode()).decode()
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


def fetch(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        if r.status == 204:
            return r.status, None
        return r.status, json.loads(r.read())


def compare_field(name, a, b):
    if name == "context":
        a_uri = (a or {}).get("uri") if isinstance(a, dict) else None
        b_uri = (b or {}).get("uri") if isinstance(b, dict) else None
        return a_uri == b_uri, f"context.uri: {a_uri!r} vs {b_uri!r}"
    if name == "item":
        a_uri = (a or {}).get("uri") if isinstance(a, dict) else None
        b_uri = (b or {}).get("uri") if isinstance(b, dict) else None
        return a_uri == b_uri, f"item.uri: {a_uri!r} vs {b_uri!r}"
    if name == "actions":
        a_keys = sorted(((a or {}).get("disallows") or {}).keys())
        b_keys = sorted(((b or {}).get("disallows") or {}).keys())
        return a_keys == b_keys, f"actions.disallows keys: {a_keys} vs {b_keys}"
    if name == "progress_ms":
        if a is None or b is None:
            return a == b, f"progress_ms: {a!r} vs {b!r}"
        drift = abs(int(b) - int(a))
        ok = drift <= PROGRESS_DRIFT_LIMIT_MS
        return ok, f"progress_ms: {a} vs {b} (drift={drift}ms, limit={PROGRESS_DRIFT_LIMIT_MS}ms)"
    return a == b, f"{name}: {a!r} vs {b!r}"


def main():
    if not CONFIG.exists():
        fail(f"creds file not found at {CONFIG}")
    cfg = json.loads(CONFIG.read_text())
    token = get_access_token(cfg)

    print("fetching /me/player/currently-playing ...")
    s1, d1 = fetch(
        "https://api.spotify.com/v1/me/player/currently-playing?additional_types=episode",
        token,
    )
    t1 = time.time()
    print(f"  HTTP {s1}")
    print("fetching /me/player ...")
    s2, d2 = fetch("https://api.spotify.com/v1/me/player?additional_types=episode", token)
    t2 = time.time()
    print(f"  HTTP {s2}  (Δt = {(t2-t1)*1000:.0f}ms)")

    if s1 == 204 and s2 == 204:
        print("SKIP: both endpoints returned 204 — no track playing on any device")
        sys.exit(0)
    if s1 == 204 or s2 == 204:
        fail(f"only one endpoint returned 204 — start playing a track and retry "
             f"(currently-playing={s1}, me/player={s2})")
    if s1 != 200:
        fail(f"/me/player/currently-playing returned HTTP {s1}")
    if s2 != 200:
        fail(f"/me/player returned HTTP {s2}")

    failures = []
    print()
    print("comparing firmware-consumed fields:")
    for field in FIRMWARE_FIELDS:
        a, b = d1.get(field), d2.get(field)
        ok, detail = compare_field(field, a, b)
        marker = "✓" if ok else "✗"
        print(f"  [{marker}] {detail}")
        if not ok:
            failures.append(detail)

    print()
    print("checking device.volume_percent on /me/player ...")
    dev = d2.get("device")
    if dev is None:
        failures.append("/me/player has no 'device' field — ADR-015 premise broken")
    else:
        vp = dev.get("volume_percent")
        supports = dev.get("supports_volume")
        print(f"  device.name={dev.get('name')!r} type={dev.get('type')!r} "
              f"supports_volume={supports} volume_percent={vp}")
        if "volume_percent" not in dev:
            failures.append("device.volume_percent key absent — TASK-039 patch can't populate")
        else:
            print(f"  [✓] device.volume_percent present (value={vp!r}, may be null if supports_volume=false)")

    print()
    if failures:
        print(f"FAIL: {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS — /me/player is a strict superset of /me/player/currently-playing for firmware-consumed fields.")
    sys.exit(0)


if __name__ == "__main__":
    main()
