#!/usr/bin/env python3
"""T_RB_01–T_RB_06 — radio-browser.info API probe (WebRadio POC, TASK-200).

Validates the API endpoints the WebRadio firmware will use and identifies the
TLS root CA for dataTaskCerts.h.

Checks:
  T_RB_01  HTTPS GET 100-station NL/MP3 query returns HTTP 200
  T_RB_02  TLS cert chain printed — root CA identified for dataTaskCerts.h
  T_RB_03  Raw response body size reported (expect ~220–240 KB)
  T_RB_04  JSON shape: name, url_resolved, bitrate, votes present in first 3 stations
  T_RB_05  Mirror fallback: de1 → nl1 → at1 — each mirror probed and status reported
  T_RB_06  Country spot-check: NL, DE, US, JP, AU — 5 stations each, count reported

No DUT, no credentials, no serial port required.
Run before TASK-202 — T_RB_02 output identifies the root CA for dataTaskCerts.h.

Usage:
  python3 tools/test_radiobrowser_api.py
  python3 tools/test_radiobrowser_api.py --no-tls

Exit 0 = all pass. Exit 1 = one or more failures.
"""
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import argparse

# Primary search endpoint — same query the firmware will use.
# de1 is the default mirror; nl1/at1 are failover candidates.
MIRRORS = ["de1", "nl1", "at1"]
API_HOST_TEMPLATE = "{mirror}.api.radio-browser.info"
SEARCH_PATH = "/json/stations/search?countrycode=NL&codec=MP3&hidebroken=true&order=votes&limit=100"

# Fields the firmware will extract from each station object.
REQUIRED_FIELDS = ["name", "url_resolved", "bitrate", "votes"]

# Country codes to spot-check (sample from cities.h universe).
SPOT_CHECK_COUNTRIES = ["NL", "DE", "US", "JP", "AU"]
SPOT_CHECK_LIMIT = 5   # stations per country

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) esp_spotify/probe",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except OSError as e:
        return None, str(e).encode()


def _ok(label, detail=""):
    print(f"  [PASS] {label}" + (f": {detail}" if detail else ""))


def _fail(label, detail=""):
    print(f"  [FAIL] {label}" + (f": {detail}" if detail else ""), file=sys.stderr)


def _info(label, detail=""):
    print(f"  [INFO] {label}" + (f": {detail}" if detail else ""))


# ── checks ────────────────────────────────────────────────────────────────────

def check_primary_fetch():
    """T_RB_01 — HTTPS GET 100-station NL/MP3 query returns HTTP 200."""
    print("\nT_RB_01  Primary fetch: de1 NL/MP3/100-station query")
    url = f"https://{API_HOST_TEMPLATE.format(mirror='de1')}{SEARCH_PATH}"
    _info("URL", url)
    status, body = _get(url)
    if status == 200:
        _ok("de1 primary fetch", f"HTTP {status}  {len(body)} bytes")
        return True, body
    else:
        _fail("de1 primary fetch", f"HTTP {status}: {body[:120].decode(errors='replace')}")
        return False, body


def check_body_size(body):
    """T_RB_03 — Raw response body size (informational, expect ~220–240 KB)."""
    print("\nT_RB_03  Raw response body size")
    size_kb = len(body) / 1024
    _info("body size", f"{len(body)} bytes ({size_kb:.1f} KB)")
    if len(body) < 100_000:
        _fail("body suspiciously small", f"{len(body)} B — expected ~220–240 KB for 100 stations")
        return False
    _ok("body size plausible", f"{size_kb:.1f} KB")
    return True


def check_json_shape(body):
    """T_RB_04 — JSON shape: name, url_resolved, bitrate, votes in first 3 stations."""
    print(f"\nT_RB_04  JSON shape: {', '.join(REQUIRED_FIELDS)} present in first 3 stations")
    try:
        stations = json.loads(body)
    except json.JSONDecodeError as e:
        _fail("JSON parse", str(e))
        return False

    if not isinstance(stations, list):
        _fail("top-level type", f"expected list, got {type(stations).__name__}")
        return False

    _info("total stations in response", str(len(stations)))
    all_ok = True
    for i, station in enumerate(stations[:3]):
        name = station.get("name", "<missing>")
        missing = [f for f in REQUIRED_FIELDS if f not in station or station[f] is None]
        if missing:
            _fail(f"station[{i}] {name!r}", f"missing fields: {missing}")
            all_ok = False
        else:
            summary = (
                f"name={station['name']!r}  "
                f"bitrate={station['bitrate']}  "
                f"votes={station['votes']}"
            )
            _ok(f"station[{i}]", summary)
    return all_ok


def check_mirror_fallback():
    """T_RB_05 — Mirror fallback: de1 → nl1 → at1 probed and status reported."""
    print("\nT_RB_05  Mirror fallback: de1 → nl1 → at1")
    results = {}
    for mirror in MIRRORS:
        url = f"https://{API_HOST_TEMPLATE.format(mirror=mirror)}{SEARCH_PATH}"
        status, body = _get(url, timeout=15)
        if status == 200:
            _ok(mirror, f"HTTP {status}  {len(body)} bytes")
            results[mirror] = "ok"
        else:
            msg = body[:80].decode(errors="replace") if isinstance(body, bytes) else str(body)
            _fail(mirror, f"HTTP {status}: {msg}")
            results[mirror] = "fail"
        time.sleep(0.5)
    # Pass if at least one mirror is reachable.
    if any(v == "ok" for v in results.values()):
        _ok("mirror fallback", f"at least one mirror reachable: {results}")
        return True
    _fail("mirror fallback", "all mirrors unreachable")
    return False


def check_country_spotcheck():
    """T_RB_06 — Spot-check 5 country codes: NL, DE, US, JP, AU (5 stations each)."""
    print(f"\nT_RB_06  Country spot-check: {', '.join(SPOT_CHECK_COUNTRIES)} ({SPOT_CHECK_LIMIT} stations each)")
    all_ok = True
    for cc in SPOT_CHECK_COUNTRIES:
        path = f"/json/stations/search?countrycode={cc}&codec=MP3&hidebroken=true&order=votes&limit={SPOT_CHECK_LIMIT}"
        url = f"https://{API_HOST_TEMPLATE.format(mirror='de1')}{path}"
        status, body = _get(url, timeout=15)
        if status != 200:
            _fail(cc, f"HTTP {status}")
            all_ok = False
            time.sleep(0.3)
            continue
        try:
            stations = json.loads(body)
            count = len(stations)
        except json.JSONDecodeError as e:
            _fail(cc, f"JSON parse: {e}")
            all_ok = False
            time.sleep(0.3)
            continue
        if count == 0:
            _fail(cc, "0 stations returned — code may be invalid or have no MP3 streams")
            all_ok = False
        else:
            _ok(cc, f"{count} station(s) returned")
        time.sleep(0.3)
    return all_ok


def check_tls(skip):
    """T_RB_02 — TLS cert chain: subject, issuer, SANs, validity, root CA identification.

    ssl.get_server_certificate() returns only the leaf.  We use openssl s_client
    -showcerts to get every cert in the chain, then display subject/issuer/dates
    for each.  The deepest cert the server sends is the pinning candidate for
    dataTaskCerts.h — pinning it survives leaf rotation without requiring a root
    cert fetch.
    """
    print("\nT_RB_02  TLS cert chain (for dataTaskCerts.h root CA identification)")
    if skip:
        _info("skipped via --no-tls")
        return True

    host = API_HOST_TEMPLATE.format(mirror="de1")

    # Try openssl s_client for full chain.
    try:
        sc = subprocess.run(
            ["openssl", "s_client", "-connect", f"{host}:443", "-showcerts"],
            input=b"", capture_output=True, timeout=12,
        )
        chain_pem = sc.stdout.decode(errors="replace")
    except FileNotFoundError:
        _info("openssl not on PATH — run manually:")
        print(f"  openssl s_client -connect {host}:443 -showcerts 2>/dev/null")
        return True
    except subprocess.TimeoutExpired:
        _info("openssl s_client timed out")
        return True

    pem_blocks = re.findall(
        r"(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)",
        chain_pem, re.DOTALL,
    )
    if not pem_blocks:
        _info("no certificates found in s_client output")
        return True

    print(f"  {len(pem_blocks)} cert(s) in chain (0=leaf, {len(pem_blocks)-1}=deepest sent by server):")
    for i, pem in enumerate(pem_blocks):
        result = subprocess.run(
            ["openssl", "x509", "-noout", "-subject", "-issuer", "-dates", "-ext", "subjectAltName"],
            input=pem.encode(), capture_output=True, timeout=5,
        )
        lines = result.stdout.decode(errors="replace").strip().splitlines()
        if i == 0:
            label = "leaf"
        elif i < len(pem_blocks) - 1:
            label = f"intermediate-{i}"
        else:
            label = "deepest (pin candidate for dataTaskCerts.h)"
        print(f"\n  [{i}] {label}")
        for line in lines:
            print(f"    {line.strip()}")

    print()
    print("  Pinning recommendation for dataTaskCerts.h:")
    print(f"  → Pin cert [{len(pem_blocks)-1}] (deepest in chain) as RADIO_BROWSER_ROOT_CA[].")
    print("    This survives leaf rotation. Replace only if the CA changes its intermediate family.")
    print("  → For maximum longevity: fetch the actual self-signed root PEM from the CA's website")
    print("    (root is not sent by server — must be fetched separately from Mozilla CA bundle).")
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--no-tls", action="store_true", help="Skip T_RB_02 cert dump")
    args = parser.parse_args()

    print("radio-browser.info API probe — WebRadio POC (TASK-200)")
    print(f"Primary mirror : de1.api.radio-browser.info")
    print(f"Fallback mirrors: nl1, at1")
    print(f"Query          : countrycode=NL, codec=MP3, hidebroken=true, order=votes, limit=100")
    print(f"Spot-check     : {', '.join(SPOT_CHECK_COUNTRIES)} ({SPOT_CHECK_LIMIT} stations each)")

    failures = []

    ok, body = check_primary_fetch()
    if not ok:
        failures.append("T_RB_01")

    check_tls(args.no_tls)

    if body and ok:
        if not check_body_size(body):
            failures.append("T_RB_03")
        if not check_json_shape(body):
            failures.append("T_RB_04")
    else:
        failures += ["T_RB_03", "T_RB_04"]

    if not check_mirror_fallback():
        failures.append("T_RB_05")

    if not check_country_spotcheck():
        failures.append("T_RB_06")

    print()
    if failures:
        print(f"FAIL — {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("PASS — all checks passed (T_RB_01–T_RB_06)")
    sys.exit(0)


if __name__ == "__main__":
    main()
