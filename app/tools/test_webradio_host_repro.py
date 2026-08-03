#!/usr/bin/env python3
"""Host-side WebRadio connectivity reproduction harness (TASK-391).

Design: docs/architecture/designs/M-WEBRADIO-HOST-REPRO.md
Feeds: TASK-390 (WebRadio ERROR_UNREACHABLE / marquee-freeze investigation)

Determines whether WebRadio connectivity failures are reproducible from a
host machine on the same WiFi SSID as the DUT, and directly tests the
leading hypothesis: `Audio.h`'s connect-timeout defaults (250ms plain HTTP,
2700ms HTTPS, `m_timeout_ms`/`m_timeout_ms_ssl`, never raised by
webRadioApp.h via setConnectionTimeout()) are too tight for a real TCP
handshake to a remote icecast/shoutcast host, and read identically to a
dead station from the app's perspective.

Phase 0 (self-check): probe a known-good relay (NPO icecast.omroep.nl) at a
generous timeout. If this fails, the tool itself is broken -- abort before
drawing any conclusion about stations or the network.

Phase 1 (connect-latency A/B, primary test): for each station (5 breadth +
1 depth == SLAM! DANCE CLASSICS), run N=3 connect attempts at a "capped"
timeout matching Audio.h's default exactly, and N=3 at a "generous" timeout
(5s), same host/network/code path, only the timeout value differs. Splits
DNS-resolve / TCP-connect / TLS-handshake phases. A materially higher
failure rate under the capped budget than the generous one, to the *same*
host in the *same* run, is a same-machine causal result -- not an absolute-
latency-vs-threshold guess.

Phase 1 also runs a parser-correctness check against the self-check station
(structural validation of ICY metadata block framing) before any Phase 2
title-tracking timeline is trusted as evidence.

Phase 2 (depth soak, opt-in via --minutes): sustained read against SLAM!
DANCE CLASSICS, logging bytes/sec, drops/reconnects, and every StreamTitle
change with a timestamp -- the host-side analog of TASK-390's original
metadata-stall question.

Station selection is resolved once against radio-browser.info (same query
shape as dataTaskStorage.cpp's fetchOneMirror()) and cached to
app/tools/data/webradio_host_repro_stations.json so repeat runs don't
re-hammer the same rate-limit-sensitive endpoint TASK-284 already flags.

Usage:
  python3 tools/test_webradio_host_repro.py                  # phase 0 + 1 only
  python3 tools/test_webradio_host_repro.py --minutes 5       # + phase 2 soak
  python3 tools/test_webradio_host_repro.py --refresh-stations
  python3 tools/test_webradio_host_repro.py --report-out /tmp/report.json

Exit 0 = self-check passed and at least one disposition reached.
Exit 1 = self-check failed (tool broken, no disposition trustworthy).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
STATIONS_CACHE = TOOLS_DIR / "data" / "webradio_host_repro_stations.json"
REPORT_DIR = TOOLS_DIR / "rnd_logs"

# Matches dataTaskStorage.cpp kRadioBrowserMirrors (dataTaskStorage.cpp:889-890).
RB_MIRRORS = ["all.api.radio-browser.info", "de1.api.radio-browser.info"]
RB_HEADERS = {"User-Agent": "esp_spotify/host-repro-probe (TASK-391)"}
RB_COUNTRY = "NL"
RB_BITRATE_CAP = 128  # matches g_settings.webRadioBitrateCap default (design doc)
RB_BREADTH_N = 5
DEPTH_STATION_NAME = "SLAM! DANCE CLASSICS"

# Matches Audio.h:530-531 exactly (m_timeout_ms / m_timeout_ms_ssl defaults).
CAPPED_TIMEOUT_HTTP_MS = 250
CAPPED_TIMEOUT_HTTPS_MS = 2700
GENEROUS_TIMEOUT_MS = 5000  # VE review suggestion: "e.g. 5s"

ATTEMPTS_PER_BUDGET = 3
ATTEMPT_SPACING_S = 2.0  # matches WR_SKIP_PACE_MS (webRadioApp.h:68)
HEADER_READ_TIMEOUT_S = 8.0  # fixed, independent of the budget under test

# Known-good relay for self-check + parser-correctness check.
SELFCHECK_NAME = "NPO Radio 1 (icecast.omroep.nl)"
SELFCHECK_URL = "http://icecast.omroep.nl/radio1-bb-mp3"

# VE review's falsifiable threshold, decided in advance (not post-hoc):
# capped failures - generous failures >= this, out of ATTEMPTS_PER_BUDGET,
# counts as "timeout hypothesis supported" for that station.
TIMEOUT_SUPPORT_DELTA = 2


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _log(msg):
    print(f"[{_ts()}] {msg}")


# ── DNS resolver disclosure (VE review #3) ──────────────────────────────────

def log_dns_resolver():
    """Best-effort: report which nameserver(s) this host resolves through.

    Not guaranteed to match what the DUT's DHCP lease hands out -- flagged
    as a known limitation, not silently assumed equivalent (VE review #3).
    """
    nameservers = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                line = line.strip()
                if line.startswith("nameserver"):
                    nameservers.append(line.split()[1])
    except OSError:
        pass
    if nameservers:
        _log(f"DNS resolver(s) in use: {nameservers} "
             f"(host OS resolver -- may differ from the DUT's DHCP-assigned "
             f"DNS; known limitation, not verified equivalent)")
    else:
        _log("DNS resolver: could not read /etc/resolv.conf -- unknown, "
             "known limitation")
    return nameservers


# ── station resolution + caching (VE review #4) ─────────────────────────────

def _rb_get(path):
    last_err = None
    for mirror in RB_MIRRORS:
        url = f"https://{mirror}{path}"
        req = urllib.request.Request(url, headers=RB_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                _log(f"radio-browser OK mirror={mirror} path={path}")
                return json.loads(r.read())
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last_err = e
            _log(f"radio-browser FAILED mirror={mirror}: {e}")
    raise RuntimeError(f"all radio-browser mirrors failed: {last_err}")


def resolve_stations(refresh=False):
    """Resolve breadth (top 5 NL/MP3 by votes) + depth (SLAM! DANCE CLASSICS)
    station URLs, once, cached to disk. Reuses the cache unless refresh=True
    or the cache is missing -- don't re-hit radio-browser on every run
    (TASK-284's rate-sensitivity)."""
    if not refresh and STATIONS_CACHE.exists():
        cached = json.loads(STATIONS_CACHE.read_text())
        _log(f"using cached station list from {STATIONS_CACHE} "
             f"(fetched_at={cached.get('fetched_at')}); pass --refresh-stations to re-query")
        return cached

    _log("querying radio-browser for station list (one-shot, will be cached)")
    breadth_path = (
        "/json/stations/search"
        f"?countrycode={RB_COUNTRY}&codec=MP3&hidebroken=true&order=votes&reverse=true"
        f"&limit={RB_BREADTH_N}&offset=0&bitrateMax={RB_BITRATE_CAP}"
    )
    breadth = _rb_get(breadth_path)

    depth_path = (
        "/json/stations/search"
        f"?name={urllib.parse.quote(DEPTH_STATION_NAME)}&codec=MP3&hidebroken=true"
        f"&order=votes&reverse=true&limit=10"
    )
    depth_candidates = _rb_get(depth_path)
    depth = None
    for cand in depth_candidates:
        if cand.get("name", "").strip().upper() == DEPTH_STATION_NAME.upper():
            depth = cand
            break
    if depth is None and depth_candidates:
        _log(f"exact name match for {DEPTH_STATION_NAME!r} not found; "
             f"using first candidate: {depth_candidates[0].get('name')!r}")
        depth = depth_candidates[0]
    if depth is None:
        raise RuntimeError(f"no radio-browser entry found for {DEPTH_STATION_NAME!r}")

    cache = {
        "fetched_at": _ts(),
        "breadth": [
            {"name": s["name"], "url_resolved": s["url_resolved"],
             "bitrate": s.get("bitrate"), "votes": s.get("votes")}
            for s in breadth
        ],
        "depth": {"name": depth["name"], "url_resolved": depth["url_resolved"],
                  "bitrate": depth.get("bitrate"), "votes": depth.get("votes")},
    }
    STATIONS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    STATIONS_CACHE.write_text(json.dumps(cache, indent=2))
    _log(f"cached station list -> {STATIONS_CACHE}")
    return cache


# ── request construction (verbatim match to Audio.cpp:495-507) ─────────────

def _build_request(host, path):
    # Audio.cpp always sends Authorization: Basic <base64(":")> even with no
    # station credentials (auth = strlen(user)+strlen(pwd) == 0, toEncode ==
    # ":"), since webRadioApp.h calls connecttohost(url) with no user/pwd
    # args. Matched here for header-for-header fidelity (Audio.cpp:502).
    auth = base64.b64encode(b":").decode()
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Icy-MetaData:1\r\n"
        f"Authorization: Basic {auth}\r\n"
        f"Accept-Encoding: identity;q=1,*;q=0\r\n"
        f"Connection: keep-alive\r\n\r\n"
    ).encode()


def _parse_url(url):
    p = urllib.parse.urlparse(url)
    host = p.hostname
    port = p.port or (443 if p.scheme == "https" else 80)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return p.scheme, host, port, path


# ── phased connect probe ────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    url: str
    budget_ms: int
    ok: bool
    dns_ms: float | None = None
    tcp_ms: float | None = None
    tls_ms: float | None = None
    total_ms: float | None = None
    http_status: int | None = None
    icy_metaint: int | None = None
    error: str | None = None
    redirected_to: str | None = None


def probe_once(url, budget_ms, _hop=0):
    """Single connect attempt. `budget_ms` governs TCP-connect for plain
    HTTP, or the combined TCP-connect+TLS-handshake for HTTPS -- matching
    how WiFiClient/WiFiClientSecure.connect(timeout) applies the budget in
    ESP32-audioI2S. DNS-resolve, TCP-connect, and TLS-handshake are timed
    separately regardless, so a slow phase is attributable (VE note)."""
    scheme, host, port, path = _parse_url(url)
    t_start = time.perf_counter()

    try:
        t0 = time.perf_counter()
        addrs = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        dns_ms = (time.perf_counter() - t0) * 1000
    except OSError as e:
        return ProbeResult(url, budget_ms, False, error=f"DNS: {e}")

    family, socktype, proto, _, sockaddr = addrs[0]
    remaining_s = budget_ms / 1000.0

    sock = socket.socket(family, socktype, proto)
    try:
        t0 = time.perf_counter()
        sock.settimeout(remaining_s)
        sock.connect(sockaddr)
        tcp_ms = (time.perf_counter() - t0) * 1000
    except OSError as e:
        sock.close()
        return ProbeResult(url, budget_ms, False, dns_ms=dns_ms, error=f"TCP connect: {e}")

    tls_ms = None
    if scheme == "https":
        # HTTPS: remaining budget after TCP connect covers the TLS handshake
        # too (single connect() call in WiFiClientSecure covers both).
        remaining_s = max(0.001, remaining_s - (tcp_ms / 1000.0))
        try:
            ctx = ssl.create_default_context()
            t0 = time.perf_counter()
            sock.settimeout(remaining_s)
            sock = ctx.wrap_socket(sock, server_hostname=host)
            tls_ms = (time.perf_counter() - t0) * 1000
        except (OSError, ssl.SSLError) as e:
            sock.close()
            return ProbeResult(url, budget_ms, False, dns_ms=dns_ms, tcp_ms=tcp_ms,
                                error=f"TLS handshake: {e}")

    # Connect phase (the one under test) succeeded. Header read uses a fixed,
    # generous timeout independent of the budget under test -- this tool is
    # testing connect latency, not total request-completion time.
    try:
        sock.settimeout(HEADER_READ_TIMEOUT_S)
        sock.sendall(_build_request(host, path))
        raw = b""
        while b"\r\n\r\n" not in raw and len(raw) < 16384:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
        head, _, _ = raw.partition(b"\r\n\r\n")
        lines = head.decode(errors="replace").split("\r\n")
        status_line = lines[0] if lines else ""
        m = re.match(r"HTTP/1\.\d\s+(\d+)", status_line)
        http_status = int(m.group(1)) if m else None
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        icy_metaint = int(headers["icy-metaint"]) if "icy-metaint" in headers else None

        if http_status in (301, 302, 303, 307, 308) and "location" in headers and _hop < 3:
            loc = headers["location"]
            if loc.startswith("/"):
                loc = f"{scheme}://{host}:{port}{loc}"
            sock.close()
            _log(f"  redirect ({http_status}) -> {loc}")
            result = probe_once(loc, budget_ms, _hop=_hop + 1)
            result.redirected_to = loc
            return result
    except OSError as e:
        sock.close()
        total_ms = (time.perf_counter() - t_start) * 1000
        return ProbeResult(url, budget_ms, True, dns_ms=dns_ms, tcp_ms=tcp_ms, tls_ms=tls_ms,
                            total_ms=total_ms, error=f"connected but header read failed: {e}")

    sock.close()
    total_ms = (time.perf_counter() - t_start) * 1000
    return ProbeResult(url, budget_ms, True, dns_ms=dns_ms, tcp_ms=tcp_ms, tls_ms=tls_ms,
                        total_ms=total_ms, http_status=http_status, icy_metaint=icy_metaint)


def run_ab_test(name, url):
    """N=3 attempts at capped budget, N=3 at generous budget, spaced
    ATTEMPT_SPACING_S apart (VE review #2 -- single attempt is too thin)."""
    scheme, *_ = _parse_url(url)
    capped_budget = CAPPED_TIMEOUT_HTTPS_MS if scheme == "https" else CAPPED_TIMEOUT_HTTP_MS

    results = {"capped": [], "generous": []}
    for label, budget in (("capped", capped_budget), ("generous", GENEROUS_TIMEOUT_MS)):
        for i in range(ATTEMPTS_PER_BUDGET):
            r = probe_once(url, budget)
            results[label].append(r)
            tag = "OK " if r.ok else "FAIL"
            parts = []
            if r.dns_ms is not None:
                parts.append(f"dns={r.dns_ms:.0f}ms")
            if r.tcp_ms is not None:
                parts.append(f"tcp={r.tcp_ms:.0f}ms")
            if r.tls_ms is not None:
                parts.append(f"tls={r.tls_ms:.0f}ms")
            if r.ok:
                parts.append(f"http={r.http_status} metaint={r.icy_metaint}")
            else:
                parts.append(f"err={r.error}")
            detail = " ".join(parts)
            _log(f"  [{name}] {label} budget={budget}ms attempt={i+1}/{ATTEMPTS_PER_BUDGET} {tag} {detail}")
            time.sleep(ATTEMPT_SPACING_S)

    capped_ok = sum(1 for r in results["capped"] if r.ok)
    generous_ok = sum(1 for r in results["generous"] if r.ok)
    capped_fail = ATTEMPTS_PER_BUDGET - capped_ok
    generous_fail = ATTEMPTS_PER_BUDGET - generous_ok
    delta = capped_fail - generous_fail

    if generous_ok == 0:
        verdict = "both-fail"  # station/network down independent of timeout
    elif delta >= TIMEOUT_SUPPORT_DELTA:
        verdict = "timeout-supported"
    else:
        verdict = "no-timeout-signal"  # station healthy at both budgets (or too noisy to call)

    return {
        "name": name, "url": url, "capped_budget_ms": capped_budget,
        "capped_ok": capped_ok, "generous_ok": generous_ok,
        "capped_latencies_ms": [r.total_ms for r in results["capped"] if r.total_ms],
        "generous_latencies_ms": [r.total_ms for r in results["generous"] if r.total_ms],
        "verdict": verdict,
        "raw": {"capped": [asdict(r) for r in results["capped"]],
                "generous": [asdict(r) for r in results["generous"]]},
    }


# ── phase 0: self-check ──────────────────────────────────────────────────────

def run_selfcheck():
    _log(f"=== Phase 0: self-check against known-good relay ({SELFCHECK_NAME}) ===")
    r = probe_once(SELFCHECK_URL, GENEROUS_TIMEOUT_MS)
    if not r.ok:
        _log(f"SELF-CHECK FAILED: {r.error} -- tool cannot connect to a station "
             f"independently known to work. TOOL IS BROKEN, not the network. Aborting.")
        return False
    _log(f"self-check OK: connected in {r.total_ms:.0f}ms, http={r.http_status}, "
         f"icy-metaint={r.icy_metaint}")
    return True


# ── parser correctness check (VE review #5) ─────────────────────────────────

def check_parser_correctness(url=SELFCHECK_URL, duration_s=30):
    """Connect to a known-good station and validate ICY metadata block
    framing structurally (not just 'a title looked plausible') -- a
    off-by-one on icy-metaint or the length byte would silently masquerade
    as 'metadata stalled', which is exactly the false-positive class this
    investigation has already hit twice this session."""
    _log(f"=== Parser correctness check ({duration_s}s against {SELFCHECK_NAME}) ===")
    scheme, host, port, path = _parse_url(url)
    try:
        sock = socket.create_connection((host, port), timeout=GENEROUS_TIMEOUT_MS / 1000.0)
        sock.settimeout(HEADER_READ_TIMEOUT_S)
        sock.sendall(_build_request(host, path))
        raw = b""
        while b"\r\n\r\n" not in raw and len(raw) < 16384:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
        head, _, body_start = raw.partition(b"\r\n\r\n")
        headers = {}
        for line in head.decode(errors="replace").split("\r\n")[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        if "icy-metaint" not in headers:
            _log("PARSER CHECK FAILED: no icy-metaint header from known-good relay")
            sock.close()
            return False
        metaint = int(headers["icy-metaint"])
        _log(f"icy-metaint={metaint}")

        sock.settimeout(5.0)
        buf = bytearray(body_start)
        titles = []
        blocks_parsed = 0
        deadline = time.time() + duration_s
        audio_remaining = metaint

        while time.time() < deadline:
            if len(buf) < audio_remaining:
                try:
                    chunk = sock.recv(8192)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf.extend(chunk)
                continue
            # Consumed `audio_remaining` bytes of audio; next byte is the
            # metadata length byte (length in units of 16 bytes, per spec).
            del buf[:audio_remaining]
            while len(buf) < 1:
                buf.extend(sock.recv(8192))
            length_byte = buf[0]
            block_len = length_byte * 16
            del buf[:1]
            while len(buf) < block_len:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                buf.extend(chunk)
            block = bytes(buf[:block_len])
            del buf[:block_len]
            blocks_parsed += 1
            if block_len > 0:
                text = block.rstrip(b"\x00").decode(errors="replace")
                m = re.search(r"StreamTitle='([^']*)'", text)
                if m:
                    title = m.group(1)
                    if not titles or titles[-1][1] != title:
                        titles.append((_ts(), title))
                        _log(f"  title: {title!r}")
                elif text:
                    _log(f"PARSER CHECK WARNING: non-empty metadata block did not "
                         f"match StreamTitle='...' pattern: {text[:80]!r}")
            audio_remaining = metaint

        sock.close()
        if blocks_parsed == 0:
            _log("PARSER CHECK FAILED: no metadata block boundary reached in the window "
                 "(stream too slow, or metaint framing wrong) -- do not trust Phase 2 titles yet")
            return False
        _log(f"parser check OK: {blocks_parsed} metadata block(s) parsed cleanly, "
             f"{len(titles)} distinct title(s) observed")
        return True
    except OSError as e:
        _log(f"PARSER CHECK FAILED: {e}")
        return False


# ── phase 2: sustained soak (depth) ─────────────────────────────────────────

def run_soak(name, url, minutes):
    _log(f"=== Phase 2: {minutes}min soak against {name} ===")
    timeline = []
    start = time.time()
    deadline = start + minutes * 60
    reconnects = 0

    def connect_headers(url_now, hop=0):
        """Connect + send request + parse status/headers. Follows 3xx
        redirects (up to 3 hops) exactly like Audio.cpp's connecttohost()
        (sc <= 310 falls through, a Location header triggers a fresh
        connecttohost() to the new host) -- every station probed this
        session issued a fresh 302 per connection (StreamTheWorld edge
        load-balancing), so skipping this step silently hangs the soak
        waiting for a body a redirect response never sends."""
        scheme_now, host_now, port_now, path_now = _parse_url(url_now)
        sock = socket.create_connection((host_now, port_now), timeout=GENEROUS_TIMEOUT_MS / 1000.0)
        if scheme_now == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host_now)
        sock.settimeout(HEADER_READ_TIMEOUT_S)
        sock.sendall(_build_request(host_now, path_now))
        raw = b""
        while b"\r\n\r\n" not in raw and len(raw) < 16384:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed before headers complete")
            raw += chunk
        head, _, body_start = raw.partition(b"\r\n\r\n")
        lines = head.decode(errors="replace").split("\r\n")
        m = re.match(r"HTTP/1\.\d\s+(\d+)", lines[0] if lines else "")
        http_status = int(m.group(1)) if m else None
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        if http_status in (301, 302, 303, 307, 308) and "location" in headers and hop < 3:
            loc = headers["location"]
            if loc.startswith("/"):
                loc = f"{scheme_now}://{host_now}:{port_now}{loc}"
            sock.close()
            _log(f"  [{name}] redirect ({http_status}) -> {loc}")
            return connect_headers(loc, hop=hop + 1)
        return sock, headers, body_start

    def connect_and_read(deadline_abs):
        nonlocal reconnects
        sock, headers, body_start = connect_headers(url)
        metaint = int(headers.get("icy-metaint", 0)) or None
        sock.settimeout(15.0)

        buf = bytearray(body_start)
        audio_remaining = metaint
        bytes_since_log = len(body_start)
        last_log = time.time()
        last_title = None

        while time.time() < deadline_abs:
            chunk = sock.recv(8192)
            if not chunk:
                raise ConnectionError("stream closed")
            buf.extend(chunk)
            bytes_since_log += len(chunk)

            if time.time() - last_log >= 10:
                _log(f"  [{name}] +{bytes_since_log}B in ~10s "
                     f"(elapsed={time.time()-start:.0f}s)")
                bytes_since_log = 0
                last_log = time.time()

            if metaint is None:
                continue
            while len(buf) >= audio_remaining + 1:
                del buf[:audio_remaining]
                length_byte = buf[0]
                block_len = length_byte * 16
                if len(buf) < 1 + block_len:
                    break
                del buf[0]
                block = bytes(buf[:block_len])
                del buf[:block_len]
                audio_remaining = metaint
                if block_len:
                    text = block.rstrip(b"\x00").decode(errors="replace")
                    m = re.search(r"StreamTitle='([^']*)'", text)
                    if m and m.group(1) != last_title:
                        last_title = m.group(1)
                        entry = {"ts": _ts(), "elapsed_s": round(time.time() - start, 1),
                                 "title": last_title}
                        timeline.append(entry)
                        _log(f"  [{name}] title change @ {entry['elapsed_s']}s: {last_title!r}")
        sock.close()

    while time.time() < deadline:
        try:
            connect_and_read(deadline)
        except (OSError, ConnectionError) as e:
            reconnects += 1
            gap_start = time.time()
            _log(f"  [{name}] connection dropped ({e}), reconnecting... "
                 f"(reconnect #{reconnects})")
            time.sleep(2.0)
            timeline.append({"ts": _ts(), "elapsed_s": round(gap_start - start, 1),
                              "event": "disconnect", "error": str(e)})

    _log(f"soak complete: {reconnects} reconnect(s), {len(timeline)} timeline event(s)")
    return {"name": name, "url": url, "minutes": minutes, "reconnects": reconnects,
            "timeline": timeline}


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh-stations", action="store_true",
                     help="re-query radio-browser instead of using the cached station list")
    ap.add_argument("--minutes", type=float, default=0,
                     help="Phase 2 soak duration in minutes against the depth station "
                          "(0 = skip Phase 2, default)")
    ap.add_argument("--skip-parser-check", action="store_true",
                     help="skip the parser-correctness check (not recommended before Phase 2)")
    ap.add_argument("--report-out", type=str, default=None,
                     help="path to write the JSON report (default: app/tools/rnd_logs/)")
    args = ap.parse_args()

    run_start_wall = _ts()
    _log(f"=== TASK-391 WebRadio host repro harness -- run started {run_start_wall} ===")
    log_dns_resolver()

    if not run_selfcheck():
        report = {"run_start": run_start_wall, "self_check": False,
                  "note": "aborted: self-check failed, tool broken"}
        _write_report(report, args.report_out)
        sys.exit(1)

    if not args.skip_parser_check:
        parser_ok = check_parser_correctness()
        if not parser_ok:
            _log("WARNING: parser-correctness check failed -- Phase 2 title-tracking "
                 "(if run) should NOT be trusted as evidence until this is fixed")
    else:
        parser_ok = None

    stations = resolve_stations(refresh=args.refresh_stations)
    _log(f"breadth stations: {[s['name'] for s in stations['breadth']]}")
    _log(f"depth station: {stations['depth']['name']}")

    _log("=== Phase 1: connect-latency A/B (capped vs generous timeout) ===")
    ab_results = []
    for s in stations["breadth"]:
        ab_results.append(run_ab_test(s["name"], s["url_resolved"]))
    depth = stations["depth"]
    ab_results.append(run_ab_test(depth["name"], depth["url_resolved"]))

    supported = [r for r in ab_results if r["verdict"] == "timeout-supported"]
    both_fail = [r for r in ab_results if r["verdict"] == "both-fail"]
    healthy = [r for r in ab_results if r["verdict"] == "no-timeout-signal"]

    _log("=== Phase 1 disposition ===")
    for r in ab_results:
        _log(f"  {r['name']}: capped {r['capped_ok']}/{ATTEMPTS_PER_BUDGET} ok, "
             f"generous {r['generous_ok']}/{ATTEMPTS_PER_BUDGET} ok -> {r['verdict']}")

    if supported:
        overall = ("timeout-too-short SUPPORTED for "
                   f"{len(supported)}/{len(ab_results)} station(s): "
                   f"{[r['name'] for r in supported]} -- candidate fix: raise "
                   "setConnectionTimeout(), gated on DUT-side confirmation")
    elif both_fail:
        overall = (f"{len(both_fail)}/{len(ab_results)} station(s) unreachable at BOTH budgets: "
                   f"{[r['name'] for r in both_fail]} -- real external outage/network-path "
                   "issue, not a timeout-tuning fix")
    else:
        overall = "no station showed a timeout-supported pattern -- all healthy at both budgets"
    _log(f"OVERALL: {overall}")

    soak = None
    if args.minutes > 0:
        soak = run_soak(depth["name"], depth["url_resolved"], args.minutes)

    report = {
        "run_start": run_start_wall,
        "run_end": _ts(),
        "self_check": True,
        "parser_check_ok": parser_ok,
        "dns_resolvers": log_dns_resolver(),
        "stations": stations,
        "phase1_results": ab_results,
        "phase1_overall_disposition": overall,
        "phase2_soak": soak,
    }
    _write_report(report, args.report_out)
    sys.exit(0)


def _write_report(report, report_out):
    if report_out:
        path = Path(report_out)
    else:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        path = REPORT_DIR / f"webradio_host_repro_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    _log(f"report written -> {path}")


if __name__ == "__main__":
    main()
