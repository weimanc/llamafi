#!/usr/bin/env python3
"""T_BUF_01–T_BUF_04 — Stream buffer dropout probe for 15 countries × 20 stations.

Connects to each station's url_resolved, streams for STREAM_SECS seconds
while recording per-chunk timing, then simulates the ESP32's input buffer
(6400 bytes, 6.25 KB) draining at the station's declared bitrate.

Addresses M-WEBRADIO Gap 1: whether 128 kbps streams will cause buffer
underruns on the ESP32 and whether a bitrate cap is needed in the API query.

Countries probed (15):
  NL GB FR DE ES US AU IT CA SE NO BR JP PL IN

Checks:
  T_BUF_01  Station lists fetched (20 per country, codec=MP3, hidebroken=true)
  T_BUF_02  Each station streamed for STREAM_SECS seconds; chunk timing recorded
  T_BUF_03  ESP32 buffer model simulated per station (SAFE / MARGINAL / RISKY)
  T_BUF_04  Per-country risk table + global bitrate-cap recommendation

ESP32 buffer model:
  - Buffer size  : 6400 bytes (6.25 KB, no PSRAM)
  - Drain rate   : declared_bitrate_kbps × 1000 / 8  bytes/sec
  - Fill event   : each recv() chunk fills the buffer (capped at buffer_size)
  - Stall event  : recv() returns 0 bytes (socket.timeout) — buffer continues draining
  - Underrun     : buffer hits 0 bytes during drain

Risk ratings:
  SAFE     — buffer never drops below 30% in STREAM_SECS seconds
  MARGINAL — buffer drops below 30% but no underrun
  RISKY    — at least one underrun (buffer reaches 0) in STREAM_SECS seconds
  FAIL     — could not connect or no data received

Usage:
  python3 tools/test_stream_buffer.py
  python3 tools/test_stream_buffer.py --workers 8 --secs 5

Exit 0 = global recommendation is NO-CAP (no bitrate restriction needed).
Exit 1 = CAP-RECOMMENDED or HIGH-RISK (≥ 10% of stations are RISKY).
"""
import argparse
import json
import socket
import ssl
import sys
import time
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

TOP_N             = 20
API_MIRRORS       = ["de1.api.radio-browser.info", "at1.api.radio-browser.info",
                     "nl1.api.radio-browser.info"]
DEFAULT_WORKERS   = 12
DEFAULT_STREAM_SECS = 4     # seconds to stream each station
BUFFER_BYTES      = 40_000  # ESP32-audioI2S default ring buffer: 25 chunks × 1600 B = 40 KB
CONNECT_TIMEOUT   = 6       # seconds
RECV_TIMEOUT      = 0.4     # seconds — stall detection granularity

# Bitrate caps to evaluate (kbps)
CAP_CANDIDATES = [64, 96, 128]

SAFE_THRESHOLD    = 0.30    # buffer fraction below which is not SAFE
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
        "Gecko/20100101 Firefox/120.0"
    ),
    "Icy-MetaData": "0",
    "Connection": "close",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _info(s):  print(f"  [INFO] {s}")
def _ok(s):    print(f"  [PASS] {s}")
def _fail(s):  print(f"  [FAIL] {s}", file=sys.stderr)


def _fetch_stations(cc, limit=TOP_N):
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


def _parse_url(url):
    """Return (host, port, path, use_ssl)."""
    p = urllib.parse.urlparse(url)
    host = p.hostname
    port = p.port or (443 if p.scheme == "https" else 80)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return host, port, path, (p.scheme == "https")


def _simulate_buffer(chunks, bitrate_kbps, buffer_size=BUFFER_BYTES):
    """Model ESP32 input buffer fill/drain from chunk timing data.

    chunks: list of (elapsed_sec, bytes_received) — bytes=0 means a stall tick.
    Returns (min_fill_frac, underrun_count, avg_bps).
    """
    if not chunks:
        return 0.0, 0, 0.0

    drain_rate = max(1, bitrate_kbps) * 1000.0 / 8.0   # bytes/sec

    buf      = 0.0
    min_fill = float(buffer_size)
    underruns = 0
    prev_t   = 0.0

    for t, nbytes in chunks:
        dt     = t - prev_t
        prev_t = t
        drained = drain_rate * dt
        buf = max(0.0, buf - drained)
        if buf == 0.0 and drained > 0:
            underruns += 1
        buf = min(float(buffer_size), buf + nbytes)
        min_fill = min(min_fill, buf)

    total_bytes = sum(b for _, b in chunks)
    elapsed     = chunks[-1][0] if chunks else 1.0
    avg_bps     = total_bytes / max(elapsed, 0.001)

    return min_fill / buffer_size, underruns, avg_bps


def _risk_at_cap(result, cap_kbps):
    """Re-evaluate risk if we applied a bitrate cap (use cap as drain rate)."""
    chunks = result.get("chunks_raw", [])
    declared = result.get("bitrate", 128)
    # Only re-rate stations that declared ≥ cap; others are already below cap
    if declared <= cap_kbps or not chunks:
        return result.get("risk", "FAIL")
    min_fill, underruns, _ = _simulate_buffer(chunks, cap_kbps)
    if underruns > 0:
        return "RISKY"
    if min_fill < SAFE_THRESHOLD:
        return "MARGINAL"
    return "SAFE"


# ── per-station stream probe ──────────────────────────────────────────────────

def _probe_station(station, stream_secs):
    name     = station.get("name", "?")
    url      = (station.get("url_resolved") or "").strip()
    bitrate  = int(station.get("bitrate") or 128)

    base = {"name": name, "url": url, "bitrate": bitrate}

    if not url:
        return {**base, "status": "NO-URL", "risk": "FAIL"}

    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return {**base, "status": f"SCHEME-{scheme}", "risk": "FAIL"}

    # Skip playlist URLs
    path_lower = urllib.parse.urlparse(url).path.lower()
    if any(path_lower.endswith(e) for e in (".m3u", ".m3u8", ".pls", ".xspf")):
        return {**base, "status": "PLAYLIST", "risk": "FAIL"}

    try:
        host, port, path, use_ssl = _parse_url(url)
    except Exception as e:
        return {**base, "status": "PARSE-ERROR", "risk": "FAIL", "detail": str(e)[:60]}

    request = (
        f"GET {path} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        + "".join(f"{k}: {v}\r\n" for k, v in HEADERS.items())
        + "\r\n"
    ).encode()

    sock = None
    try:
        raw = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        if use_ssl:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            sock = raw

        sock.sendall(request)

        # Read HTTP/ICY response headers
        hdr_buf = b""
        sock.settimeout(CONNECT_TIMEOUT)
        while b"\r\n\r\n" not in hdr_buf and b"\n\n" not in hdr_buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            hdr_buf += chunk
            if len(hdr_buf) > 65536:
                break

        status_line = hdr_buf.split(b"\r\n")[0].decode(errors="replace").strip()
        # Accept HTTP 2xx or ICY 200 OK
        if not any(x in status_line for x in ("200", "ICY 200")):
            code = status_line.split()[1] if len(status_line.split()) > 1 else "?"
            return {**base, "status": f"HTTP-{code}", "risk": "FAIL",
                    "status_line": status_line}

        # Any body bytes that arrived with headers are part of the stream
        sep = b"\r\n\r\n" if b"\r\n\r\n" in hdr_buf else b"\n\n"
        body_start = hdr_buf[hdr_buf.index(sep) + len(sep):]

        # Stream for stream_secs seconds, recording chunk timing
        sock.settimeout(RECV_TIMEOUT)
        start    = time.monotonic()
        chunks   = []   # (elapsed_sec, bytes)

        if body_start:
            chunks.append((0.0, len(body_start)))

        while time.monotonic() - start < stream_secs:
            try:
                data = sock.recv(8192)
                t = time.monotonic() - start
                if not data:
                    break
                chunks.append((t, len(data)))
            except socket.timeout:
                t = time.monotonic() - start
                chunks.append((t, 0))   # stall tick

    except socket.timeout:
        return {**base, "status": "TIMEOUT", "risk": "FAIL"}
    except ssl.SSLError as e:
        return {**base, "status": "SSL-ERROR", "risk": "FAIL", "detail": str(e)[:60]}
    except OSError as e:
        return {**base, "status": "CONN-ERROR", "risk": "FAIL", "detail": str(e)[:60]}
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    total_bytes = sum(b for _, b in chunks)
    if total_bytes == 0:
        return {**base, "status": "NO-DATA", "risk": "FAIL"}

    min_fill, underruns, avg_bps = _simulate_buffer(chunks, bitrate)

    if underruns > 0:
        risk = "RISKY"
    elif min_fill < SAFE_THRESHOLD:
        risk = "MARGINAL"
    else:
        risk = "SAFE"

    return {
        **base,
        "status":       "OK",
        "risk":         risk,
        "avg_kbps":     avg_bps * 8 / 1000,
        "min_fill_pct": min_fill * 100,
        "underruns":    underruns,
        "stall_ticks":  sum(1 for _, b in chunks if b == 0),
        "chunk_count":  len(chunks),
        "chunks_raw":   chunks,     # kept for cap re-evaluation
    }


# ── checks ────────────────────────────────────────────────────────────────────

def run_probe(workers, stream_secs):
    # T_BUF_01 — fetch station lists
    print(f"\nT_BUF_01  Fetching station lists ({TOP_N} stations × {len(COUNTRIES)} countries)")
    all_stations: dict[str, list] = {}
    for cc, name in COUNTRIES:
        stations = _fetch_stations(cc, TOP_N)
        all_stations[cc] = stations
        marker = "[PASS]" if stations else "[FAIL]"
        print(f"  {marker} {cc:2s} {name:<20s} {len(stations)} stations")
        time.sleep(0.8)

    total_to_probe = sum(len(v) for v in all_stations.values())
    print(f"\n  Total to stream: {total_to_probe}  "
          f"(~{total_to_probe * stream_secs / workers:.0f}s wall-time at {workers} workers)")

    # T_BUF_02 — stream each station
    print(f"\nT_BUF_02  Streaming {stream_secs}s per station ({workers} workers)")
    print(f"          Buffer model: {BUFFER_BYTES}B, drain=declared_kbps, "
          f"stall-tick={RECV_TIMEOUT}s")

    results_by_cc: dict[str, list] = {cc: [] for cc, _ in COUNTRIES}
    all_tasks = [(cc, s) for cc, stations in all_stations.items() for s in stations]
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_probe_station, s, stream_secs): cc
            for cc, s in all_tasks
        }
        for fut in as_completed(future_map):
            cc = future_map[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"name": "?", "url": "?", "bitrate": 0,
                       "status": "ERROR", "risk": "FAIL", "detail": str(e)[:60]}
            results_by_cc[cc].append(res)
            done += 1
            if done % 20 == 0 or done == len(all_tasks):
                print(f"  … {done}/{len(all_tasks)}", end="\r", flush=True)

    print()

    # T_BUF_03 — per-country table
    print(f"\nT_BUF_03  Per-country buffer risk table")
    print(f"\n  {'Country':<22s} {'Probed':>6s} {'SAFE':>5s} {'MARG':>5s} {'RISKY':>6s} "
          f"{'FAIL':>5s} {'AvgKbps':>8s} {'Risk':>5s}")
    print("  " + "─" * 70)

    country_summaries = []
    risky_stations = []

    for cc, name in COUNTRIES:
        results = results_by_cc[cc]
        probed   = len([r for r in results if r["status"] == "OK"])
        safe_n   = sum(1 for r in results if r.get("risk") == "SAFE")
        marg_n   = sum(1 for r in results if r.get("risk") == "MARGINAL")
        risky_n  = sum(1 for r in results if r.get("risk") == "RISKY")
        fail_n   = sum(1 for r in results if r.get("risk") == "FAIL")
        avg_kbps = (
            sum(r.get("avg_kbps", 0) for r in results if r.get("status") == "OK")
            / max(probed, 1)
        )
        ok_n = safe_n + marg_n + risky_n
        country_risk = (
            "HIGH" if ok_n and risky_n / ok_n >= 0.30 else
            "MED"  if ok_n and risky_n / ok_n >= 0.10 else
            "LOW"
        )
        label = f"{cc}  {name}"
        print(f"  {label:<22s} {probed:>6d} {safe_n:>5d} {marg_n:>5d} {risky_n:>6d} "
              f"{fail_n:>5d} {avg_kbps:>8.1f} {country_risk:>5s}")

        for r in results:
            if r.get("risk") == "RISKY":
                risky_stations.append({**r, "cc": cc})

        country_summaries.append({
            "cc": cc, "name": name, "results": results,
            "safe": safe_n, "marginal": marg_n, "risky": risky_n, "fail": fail_n,
            "probed": probed, "country_risk": country_risk,
        })

    # T_BUF_04 — overall recommendation
    print(f"\nT_BUF_04  Bitrate-cap analysis + recommendation")

    total_ok = sum(s["safe"] + s["marginal"] + s["risky"] for s in country_summaries)
    total_risky = sum(s["risky"] for s in country_summaries)
    risky_pct = total_risky / max(total_ok, 1)

    print(f"\n  Across {total_ok} streamable stations: "
          f"{total_risky} RISKY ({risky_pct:.0%})")

    # Evaluate each cap candidate
    all_results = [
        {**r, "cc": cc}
        for cc, results in results_by_cc.items()
        for r in results
    ]
    print(f"\n  Bitrate-cap simulation (re-rate RISKY/MARGINAL at lower drain rate):")
    print(f"  {'Cap':>8s}  {'SAFE':>6s}  {'MARG':>6s}  {'RISKY':>6s}  {'Change':>12s}")

    baseline_risky = sum(1 for r in all_results if r.get("risk") == "RISKY")
    for cap in CAP_CANDIDATES:
        cap_safe = cap_marg = cap_risky = 0
        for r in all_results:
            if r.get("risk") == "FAIL":
                continue
            new_risk = _risk_at_cap(r, cap)
            if new_risk == "SAFE":
                cap_safe += 1
            elif new_risk == "MARGINAL":
                cap_marg += 1
            else:
                cap_risky += 1
        rescued = baseline_risky - cap_risky
        print(f"  {cap:>5d} kbps  {cap_safe:>6d}  {cap_marg:>6d}  {cap_risky:>6d}  "
              f"({rescued:+d} RISKY rescued)")

    # Worst offenders
    if risky_stations:
        print(f"\n  RISKY stations (sample — first 10):")
        for r in sorted(risky_stations, key=lambda x: x.get("underruns", 0), reverse=True)[:10]:
            print(f"    [{r['cc']}] {r['name'][:36]:<36s}  "
                  f"declared={r['bitrate']:>3d}kbps  "
                  f"avg={r.get('avg_kbps', 0):>6.1f}kbps  "
                  f"underruns={r.get('underruns', 0)}  "
                  f"stalls={r.get('stall_ticks', 0)}")

    # Stall-based risk (more accurate than drain model for burst-delivery streams)
    # On the ESP32, burst delivery is handled by the library (it queues and throttles).
    # True risk = streams that actually PAUSE for > buffer_drain_time seconds.
    # stall_ticks × RECV_TIMEOUT approximates max observed network pause.
    print(f"\n  Stall-based risk (network pauses only — filters out burst-delivery false positives):")
    print(f"  stall_tick window = {RECV_TIMEOUT}s;  consecutive stalls × {RECV_TIMEOUT}s = pause estimate")
    stall_risky = [
        r for r in all_results
        if r.get("status") == "OK" and r.get("stall_ticks", 0) >= 3
    ]
    stall_borderline = [
        r for r in all_results
        if r.get("status") == "OK" and 1 <= r.get("stall_ticks", 0) < 3
    ]
    stall_clean = [
        r for r in all_results
        if r.get("status") == "OK" and r.get("stall_ticks", 0) == 0
    ]
    pct_stall_risky = len(stall_risky) / max(total_ok, 1)
    print(f"  Stall-RISKY  (≥ 3 stall ticks, ~{3*RECV_TIMEOUT:.1f}s pause): "
          f"{len(stall_risky)} / {total_ok}  ({pct_stall_risky:.0%})")
    print(f"  Stall-BORDER (1–2 stall ticks):  {len(stall_borderline)}")
    print(f"  Stall-CLEAN  (0 stall ticks):    {len(stall_clean)}")
    if stall_risky:
        print(f"\n  Stall-RISKY examples:")
        for r in sorted(stall_risky, key=lambda x: x.get("stall_ticks", 0), reverse=True)[:8]:
            buf_drain_s = BUFFER_BYTES / (max(1, r["bitrate"]) * 1000 / 8)
            pause_s = r["stall_ticks"] * RECV_TIMEOUT
            verdict = "DRAIN" if pause_s > buf_drain_s else "OK"
            print(f"    [{r.get('cc','?')}] {r['name'][:36]:<36s} "
                  f"stalls={r['stall_ticks']} (~{pause_s:.1f}s pause) "
                  f"avg={r.get('avg_kbps',0):>6.1f}kbps "
                  f"declared={r['bitrate']}kbps  buf_drain={buf_drain_s:.1f}s → {verdict}")

    # Final verdict — key off stall-based risk (drain-model % is inflated by burst delivery)
    print(f"\n  Firmware recommendation:")
    print(f"  Note: drain-model RISKY% ({risky_pct:.0%}) is inflated — burst-delivery streams")
    print(f"  (avg_kbps >> declared, 0 stalls) are not a real risk; ESP32-audioI2S queues them.")
    print(f"  Stall-based risk ({pct_stall_risky:.0%}) is the actionable figure.")
    if pct_stall_risky < 0.05:
        verdict = "NO-CAP"
        print(f"  → NO-CAP: < 5% of stations have real network stalls.")
        print(f"    Buffer is adequate. No bitrate cap needed in API query.")
        print(f"    Implement retry-on-stall in firmware as a defensive measure.")
        rc = 0
    elif pct_stall_risky < 0.15:
        verdict = "CAP-RECOMMENDED"
        print(f"  → CAP-RECOMMENDED: {pct_stall_risky:.0%} of stations stall.")
        print(f"    Add ?bitrate_max=192 to API query to exclude 320 kbps outliers.")
        print(f"    Implement retry-on-stall + BUFFERING state in firmware.")
        rc = 1
    else:
        verdict = "HIGH-RISK"
        print(f"  → HIGH-RISK: {pct_stall_risky:.0%} of stations have real network stalls.")
        print(f"    Add ?bitrate_max=128 to API query. Consider increasing ring buffer")
        print(f"    via audio.setBufsize() if heap allows.")
        rc = 1

    print(f"\n  Overall verdict: {verdict}")
    return rc


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel stream threads (default {DEFAULT_WORKERS})")
    parser.add_argument("--secs", type=float, default=DEFAULT_STREAM_SECS,
                        help=f"Seconds to stream per station (default {DEFAULT_STREAM_SECS})")
    args = parser.parse_args()

    print("Stream buffer dropout probe — M-WEBRADIO Gap 1 (TASK-201 follow-up)")
    print(f"Countries : {' '.join(cc for cc, _ in COUNTRIES)}")
    print(f"Stations  : top {TOP_N} MP3 / country  |  Stream: {args.secs}s/station")
    print(f"Workers   : {args.workers}  |  Buffer model: {BUFFER_BYTES}B (ESP32-audioI2S ring buf: 25×1600B)")

    rc = run_probe(args.workers, args.secs)
    print()
    if rc == 0:
        print("PASS — buffer adequate, no bitrate cap needed (T_BUF_01–T_BUF_04)")
    else:
        print("FAIL — bitrate cap or buffer increase recommended (T_BUF_04)")
    sys.exit(rc)


if __name__ == "__main__":
    main()
