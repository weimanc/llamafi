#!/usr/bin/env python3
"""T_GEO_01–T_GEO_04 — Stream geo-lock probe for 15 countries × 20 stations.

Fetches top-20 MP3 stations per country from radio-browser.info, then
attempts an HTTP connection to each url_resolved.  Classifies each station
as ACCESSIBLE, BLOCKED, PLAYLIST, TIMEOUT, or ERROR.

Addresses M-WEBRADIO Gap 3: geo-lock risk assessment before firmware
implementation.  Results quantify per-country accessibility from this host's
IP — a proxy for real-world ESP32 reachability.

Countries probed (15):
  NL GB FR DE ES US AU IT CA SE NO BR JP PL IN

Checks:
  T_GEO_01  Station lists fetched (20 per country, codec=MP3, hidebroken=true)
  T_GEO_02  Each url_resolved probed: status, content-type, magic bytes
  T_GEO_03  Per-country accessibility table printed
  T_GEO_04  Overall summary + risk rating per country

Note: results reflect reachability from THIS machine's IP.  Geo-lock
behaviour will differ on the ESP32 (same network) but User-Agent may vary.

Usage:
  python3 tools/test_stream_geo.py
  python3 tools/test_stream_geo.py --workers 10 --timeout 8

Exit 0 = all countries have ≥ 1 accessible station.
Exit 1 = at least one country has 0 accessible stations.
"""
import argparse
import http.client as _http
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

COUNTRIES = [
    ("NL", "Netherlands"),
    ("GB", "United Kingdom"),
    ("FR", "France"),
    ("DE", "Germany"),
    ("ES", "Spain"),
    ("US", "United States"),
    ("AU", "Australia"),
    ("IT", "Italy"),
    ("CA", "Canada"),
    ("SE", "Sweden"),
    ("NO", "Norway"),
    ("BR", "Brazil"),
    ("JP", "Japan"),
    ("PL", "Poland"),
    ("IN", "India"),
]

TOP_N          = 20
API_MIRRORS    = ["de1.api.radio-browser.info", "at1.api.radio-browser.info",
                  "nl1.api.radio-browser.info"]
DEFAULT_WORKERS  = 20
DEFAULT_TIMEOUT  = 7      # seconds per station probe
READ_BYTES       = 512    # bytes to read from stream body (enough for magic bytes)

PLAYLIST_EXTS = {".m3u", ".m3u8", ".pls", ".xspf", ".asx"}
PLAYLIST_CTYPES = {
    "audio/x-mpegurl", "audio/mpegurl", "audio/x-scpls",
    "application/vnd.apple.mpegurl", "application/x-mpegurl",
}
AUDIO_CTYPES = {
    "audio/mpeg", "audio/mp3", "audio/aac", "audio/ogg",
    "audio/x-mpeg", "audio/x-mp3", "audio/x-ogg",
    "application/octet-stream",  # some servers use this for streams
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
        "Gecko/20100101 Firefox/120.0"
    ),
    "Accept": "*/*",
    "Icy-MetaData": "0",
    "Connection": "close",
}

# Audio magic bytes: ID3, MPEG sync, OggS, ADTS AAC
AUDIO_MAGIC = [
    b"ID3",          # MP3 with ID3 tag
    b"\xff\xfb",     # MPEG Layer 3 sync
    b"\xff\xfa",     # MPEG Layer 3 sync (no CRC)
    b"\xff\xf3",     # MPEG Layer 3 sync
    b"\xff\xf2",     # MPEG Layer 3 sync
    b"OggS",         # Ogg container
    b"\xff\xf1",     # ADTS AAC
    b"\xff\xf9",     # ADTS AAC
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _info(s):  print(f"  [INFO] {s}")
def _ok(s):    print(f"  [PASS] {s}")
def _fail(s):  print(f"  [FAIL] {s}", file=sys.stderr)
def _warn(s):  print(f"  [WARN] {s}")


def _fetch_stations(cc, limit=TOP_N):
    """Fetch top-N MP3 stations for a country from radio-browser.info."""
    path = (
        f"/json/stations/search"
        f"?countrycode={cc}&codec=MP3&hidebroken=true"
        f"&order=votes&limit={limit}"
    )
    for mirror in API_MIRRORS:
        url = f"https://{mirror}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                stations = json.loads(r.read())
                if stations:
                    return stations
        except Exception:
            time.sleep(0.5)
    return []


def _is_audio_magic(data: bytes) -> bool:
    for magic in AUDIO_MAGIC:
        if data[:len(magic)] == magic:
            return True
    return False


def _is_playlist_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in PLAYLIST_EXTS)


def _classify(station: dict, timeout: float) -> dict:
    """Probe one station URL and return a result dict."""
    name        = station.get("name", "?")
    url         = (station.get("url_resolved") or "").strip()
    bitrate     = int(station.get("bitrate") or 0)
    station_id  = station.get("stationuuid", "")

    base = {"name": name, "url": url, "bitrate": bitrate, "uuid": station_id}

    if not url:
        return {**base, "class": "NO-URL"}

    if _is_playlist_url(url):
        return {**base, "class": "PLAYLIST"}

    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return {**base, "class": f"SCHEME-{scheme.upper()}"}

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ct = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
            body = resp.read(READ_BYTES)

        if status == 200:
            if ct in AUDIO_CTYPES or "audio" in ct or _is_audio_magic(body):
                return {**base, "class": "ACCESSIBLE", "content_type": ct}
            if ct in PLAYLIST_CTYPES or "mpegurl" in ct or "scpls" in ct:
                return {**base, "class": "PLAYLIST", "content_type": ct}
            if "text/html" in ct or "text/plain" in ct:
                return {**base, "class": "BLOCKED-HTML", "content_type": ct}
            # Unknown content-type but check magic bytes
            if _is_audio_magic(body):
                return {**base, "class": "ACCESSIBLE", "content_type": ct}
            return {**base, "class": f"UNKNOWN-200", "content_type": ct}

        return {**base, "class": f"HTTP-{status}"}

    except urllib.error.HTTPError as e:
        if e.code in (403, 451):
            return {**base, "class": "BLOCKED"}
        return {**base, "class": f"HTTP-{e.code}"}

    except _http.BadStatusLine as e:
        # ICY protocol: server responds "ICY 200 OK" — treat as accessible
        msg = str(e)
        if "ICY" in msg or "icy" in msg:
            return {**base, "class": "ACCESSIBLE-ICY"}
        return {**base, "class": "PROTOCOL-ERROR"}

    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            return {**base, "class": "TIMEOUT"}
        if "refused" in reason.lower():
            return {**base, "class": "REFUSED"}
        return {**base, "class": "ERROR", "detail": reason[:60]}

    except socket.timeout:
        return {**base, "class": "TIMEOUT"}

    except ssl.SSLError as e:
        return {**base, "class": "SSL-ERROR", "detail": str(e)[:60]}

    except Exception as e:
        return {**base, "class": "ERROR", "detail": str(e)[:60]}


# ── report helpers ────────────────────────────────────────────────────────────

def _is_accessible(cls: str) -> bool:
    return cls in ("ACCESSIBLE", "ACCESSIBLE-ICY")


def _is_blocked(cls: str) -> bool:
    return cls.startswith("BLOCKED") or cls in ("HTTP-403", "HTTP-451")


def _country_risk(ok_pct: float) -> str:
    if ok_pct >= 0.70:
        return "LOW"
    if ok_pct >= 0.40:
        return "MED"
    return "HIGH"


# ── checks ────────────────────────────────────────────────────────────────────

def run_probe(workers: int, timeout: float):
    # T_GEO_01 — fetch station lists
    print(f"\nT_GEO_01  Fetching station lists ({TOP_N} stations × {len(COUNTRIES)} countries)")
    all_stations: dict[str, list] = {}
    for cc, name in COUNTRIES:
        stations = _fetch_stations(cc, TOP_N)
        all_stations[cc] = stations
        status = f"{len(stations)} stations" if stations else "FETCH FAILED"
        marker = "[PASS]" if stations else "[FAIL]"
        print(f"  {marker} {cc:2s} {name:<20s} {status}")
        time.sleep(0.15)   # polite rate-limit on the API

    total_fetched = sum(len(v) for v in all_stations.values())
    print(f"\n  Total stations to probe: {total_fetched}")

    # T_GEO_02 — probe each url_resolved
    print(f"\nT_GEO_02  Probing stream URLs ({workers} workers, {timeout}s timeout each)")

    results_by_cc: dict[str, list] = {cc: [] for cc, _ in COUNTRIES}
    all_tasks = [(cc, s) for cc, stations in all_stations.items() for s in stations]
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_classify, s, timeout): cc for cc, s in all_tasks}
        for fut in as_completed(future_map):
            cc = future_map[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"class": "ERROR", "detail": str(e)[:60], "name": "?", "url": "?", "bitrate": 0}
            results_by_cc[cc].append(res)
            done += 1
            if done % 30 == 0 or done == len(all_tasks):
                print(f"  … {done}/{len(all_tasks)}", end="\r", flush=True)

    print()

    # T_GEO_03 — per-country table
    print(f"\nT_GEO_03  Per-country accessibility table")
    print(f"\n  {'Country':<22s} {'Total':>5s} {'OK':>5s} {'Blocked':>8s} {'Playlist':>9s} "
          f"{'Timeout':>8s} {'Error':>6s} {'OK%':>5s} {'Risk':>5s}")
    print("  " + "─" * 80)

    any_zero = False
    country_summaries = []
    for cc, name in COUNTRIES:
        results = results_by_cc[cc]
        total   = len(results)
        ok      = sum(1 for r in results if _is_accessible(r["class"]))
        blocked = sum(1 for r in results if _is_blocked(r["class"]))
        playlist= sum(1 for r in results if r["class"] == "PLAYLIST")
        timeout = sum(1 for r in results if r["class"] == "TIMEOUT")
        error   = total - ok - blocked - playlist - timeout
        ok_pct  = ok / total if total else 0.0
        risk    = _country_risk(ok_pct)
        label   = f"{cc}  {name}"
        print(f"  {label:<22s} {total:>5d} {ok:>5d} {blocked:>8d} {playlist:>9d} "
              f"{timeout:>8d} {error:>6d} {ok_pct:>4.0%} {risk:>5s}")
        if ok == 0:
            any_zero = True
        country_summaries.append({
            "cc": cc, "name": name, "total": total, "ok": ok,
            "blocked": blocked, "playlist": playlist, "timeout": timeout,
            "error": error, "ok_pct": ok_pct, "risk": risk,
            "results": results,
        })

    # T_GEO_04 — overall summary
    print(f"\nT_GEO_04  Overall summary")
    total_all = sum(s["total"] for s in country_summaries)
    ok_all    = sum(s["ok"]    for s in country_summaries)
    blocked_all   = sum(s["blocked"]  for s in country_summaries)
    playlist_all  = sum(s["playlist"] for s in country_summaries)
    timeout_all   = sum(s["timeout"]  for s in country_summaries)
    ok_pct_all    = ok_all / total_all if total_all else 0.0

    print(f"\n  Total probed   : {total_all}")
    print(f"  Accessible     : {ok_all}  ({ok_pct_all:.0%})")
    print(f"  Blocked        : {blocked_all}")
    print(f"  Playlist (skip): {playlist_all}  (firmware must parse playlist — out of MVP scope)")
    print(f"  Timeout/Error  : {total_all - ok_all - blocked_all - playlist_all}")

    # High-risk countries
    high_risk = [s for s in country_summaries if s["risk"] == "HIGH"]
    med_risk  = [s for s in country_summaries if s["risk"] == "MED"]
    if high_risk:
        print(f"\n  HIGH-risk countries (< 40% accessible):")
        for s in high_risk:
            print(f"    {s['cc']}  {s['name']:<20s}  {s['ok']}/{s['total']} accessible")
    if med_risk:
        print(f"\n  MED-risk countries (40–69% accessible):")
        for s in med_risk:
            print(f"    {s['cc']}  {s['name']:<20s}  {s['ok']}/{s['total']} accessible")

    # Sample blocked stations (first 3 per high-risk country)
    for s in high_risk + med_risk:
        blocked_ex = [r for r in s["results"] if _is_blocked(r["class"])][:3]
        if blocked_ex:
            print(f"\n  Blocked examples — {s['cc']}:")
            for r in blocked_ex:
                print(f"    {r['class']:<14s} {r['name'][:40]:<40s}  {r['url'][:60]}")

    # Implication for firmware
    print(f"\n  Firmware implication:")
    print(f"  → url_resolved from radio-browser.info is not a guaranteed playable URL.")
    print(f"  → Playlist URLs ({playlist_all} seen) require M3U/PLS parsing — out of MVP scope;")
    print(f"    firmware should skip or display 'unsupported' when url ends in .m3u/.pls.")
    print(f"  → Geo-blocked stations ({blocked_all}) will manifest as audio.connecttohost()")
    print(f"    returning an error or staying silent — firmware needs a 'BLOCKED' state")
    print(f"    distinct from 'ERROR: conn lost' (different user message).")
    if any_zero:
        print(f"\n  WARNING: one or more countries returned 0 accessible stations.")
        print(f"  Consider filtering those countries from the picker or showing a warning.")

    return 0 if not any_zero else 1, country_summaries


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel probe threads (default {DEFAULT_WORKERS})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"Per-station timeout in seconds (default {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    print("Stream geo-lock probe — M-WEBRADIO Gap 3 (TASK-201 follow-up)")
    print(f"Countries : {' '.join(cc for cc, _ in COUNTRIES)}")
    print(f"Stations  : top {TOP_N} MP3 / country (hidebroken=true, order=votes)")
    print(f"Workers   : {args.workers}   Timeout: {args.timeout}s / station")
    print(f"Source IP : (this machine — geo-lock results reflect local IP)")

    rc, _ = run_probe(args.workers, args.timeout)
    print()
    if rc == 0:
        print("PASS — all countries have ≥ 1 accessible station (T_GEO_01–T_GEO_04)")
    else:
        print("FAIL — one or more countries have 0 accessible stations (T_GEO_04)")
    sys.exit(rc)


if __name__ == "__main__":
    main()
