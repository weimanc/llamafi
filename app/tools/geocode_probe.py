#!/usr/bin/env python3
"""geocode_probe.py — M-PR-LOCATIONS phase 0: Nominatim geocode probe.

Design: docs/architecture/designs/M-PR-LOCATIONS-location-presets.md
         ("Geocode provider decision", "Geocode fetch — dataTask one-shot",
         "Geocode query — derisk on host, phase-0 style")
Report pattern: docs/architecture/designs/M-PLANERADAR/phase0-api-probe.md
Report:  docs/architecture/designs/M-PR-LOCATIONS/phase0-geocode-probe.md
Roster:  ./run/check-datatask-certs (this script replicates its strict-verify
         method exactly for nominatim.openstreetmap.org)

Formalizes the 2026-07-13 ad-hoc probes (TASK-315) into a repeatable script:

  1. Query matrix — structured search (format=jsonv2&limit=1&addressdetails=0)
     against a fixed set of NL/UK/DE postcodes (full vs truncated) + one
     garbage postcode, custom User-Agent, >=1.1s spacing (Nominatim policy).
  2. UA policy — one request with the default python-requests UA (expect 403).
  3. HTTP/1.0 compat — one request forced to HTTP/1.0 (mirrors ESP32
     HTTPClient's useHTTP10(true)).
  4. Cert chain — strict offline verify against nominatim.openstreetmap.org
     using the exact method of run/check-datatask-certs (extract
     OPEN_METEO_ROOT_CA PEM from app/src/dataTaskCerts.h, openssl s_client
     -CAfile <root-only> -verify_return_error), plus the served chain's
     subject/issuer lines for the cross-sign evidence.

Total live requests: 7 (matrix) + 1 (UA) + 1 (HTTP/1.0) = 9, all to Nominatim,
well under the ~12 budget; the cert probe is a raw TLS handshake via openssl,
not a Nominatim API call. Every Nominatim request is spaced >=1.1s apart
(hard requirement — Nominatim usage policy caps at 1 req/s).

Run from the project venv or plain python3 (requests + stdlib only):
    ~/proj/esp/venv/bin/python3 app/tools/geocode_probe.py
    ~/proj/esp/venv/bin/python3 app/tools/geocode_probe.py --report > report.md

Exit 0 if every check landed on its expected outcome; nonzero otherwise.
"""

from __future__ import annotations

import argparse
import http.client
import re
import ssl
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests

PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
CERTS_H = PROJ_ROOT / "app" / "src" / "dataTaskCerts.h"

HOST = "nominatim.openstreetmap.org"
BASE = f"https://{HOST}/search"
PROJECT_UA = "esp32-cyd-multiapp/1.0 (github.com/weimanc; dev probe)"
MIN_SPACING_S = 1.1
TIMEOUT_S = 10

# Query matrix (label, country code, postcode, expect_match).
# expect_match encodes the "full postcode" provider-decision rule
# (M-PR-LOCATIONS-location-presets.md's provider table): Nominatim matches
# full postcodes street-level in NL/UK/DE but NOT NL's 4-digit PC4 prefix or
# UK's outward-only code — those are the ✗ cells in that table.
QUERY_MATRIX = [
    ("NL full", "NL", "2513AA", True),
    ("NL PC4 (truncated)", "NL", "2513", False),
    ("UK full (SW1A 1AA)", "GB", "SW1A 1AA", True),
    ("UK full (B33 8TH)", "GB", "B33 8TH", True),
    ("UK outward (M1)", "GB", "M1", False),
    ("DE full (10115 Berlin)", "DE", "10115", True),
    ("garbage postcode", "XX", "NOTAPOSTCODE1", False),
]


@dataclass
class QueryResult:
    label: str
    url: str
    status: int
    size_bytes: int
    matched: bool | None
    lat: str | None
    lon: str | None
    lat_type: str | None
    display_name: str | None
    expect_match: bool
    note: str = ""

    @property
    def ok(self) -> bool:
        if self.status != 200:
            return False
        return self.matched == self.expect_match


@dataclass
class SimpleCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class CertResult:
    status: str  # PASS / FAIL / ERROR
    detail: str
    chain_lines: list[str] = field(default_factory=list)


_last_request_t: float | None = None


def _throttle() -> None:
    """Enforce >=MIN_SPACING_S between Nominatim requests."""
    global _last_request_t
    now = time.monotonic()
    if _last_request_t is not None:
        wait = MIN_SPACING_S - (now - _last_request_t)
        if wait > 0:
            time.sleep(wait)
    _last_request_t = time.monotonic()


def build_url(country: str, postcode: str) -> str:
    """Manual percent-encoding — mirrors the minimal encoder the firmware
    fetcher will add (design doc: no urlEncode helper exists today; space +
    non-alnum get percent-encoded). Deliberately NOT using requests' params=
    dict (which would '+'-encode spaces via urlencode()) so this exercises
    the same %20-style encoding the device will actually send.
    """
    cc = quote(country, safe="")
    pc = quote(postcode, safe="")
    return f"{BASE}?country={cc}&postalcode={pc}&format=jsonv2&limit=1&addressdetails=0"


def run_query_matrix() -> list[QueryResult]:
    results = []
    for label, cc, postcode, expect_match in QUERY_MATRIX:
        url = build_url(cc, postcode)
        assert " " not in url, f"unencoded space leaked into URL: {url}"
        if " " in postcode:
            assert "%20" in url, f"space not percent-encoded: {url}"
        _throttle()
        try:
            r = requests.get(url, headers={"User-Agent": PROJECT_UA}, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            results.append(QueryResult(label, url, 0, 0, None, None, None, None, None, expect_match, note=f"request error: {e}"))
            continue
        size = len(r.content)
        lat = lon = lat_type = display_name = None
        matched = None
        note = ""
        if r.status_code == 200:
            try:
                body = r.json()
            except ValueError:
                note = "non-JSON body"
                body = None
            if body is not None:
                matched = len(body) > 0
                if matched:
                    first = body[0]
                    lat = first.get("lat")
                    lon = first.get("lon")
                    lat_type = type(first.get("lat")).__name__
                    display_name = first.get("display_name")
        else:
            note = f"non-200: {r.text[:120]!r}"
        results.append(QueryResult(label, url, r.status_code, size, matched, lat, lon, lat_type, display_name, expect_match, note))
    return results


def run_ua_policy_check() -> SimpleCheck:
    """Default requests UA (python-requests/x.y.z) — Nominatim policy expects
    this to be rejected with 403. Recorded honestly either way."""
    url = build_url("NL", "2513AA")
    _throttle()
    try:
        r = requests.get(url, timeout=TIMEOUT_S)  # no custom UA header
    except requests.RequestException as e:
        return SimpleCheck("UA policy (default UA)", False, f"request error: {e}")
    ua_sent = r.request.headers.get("User-Agent", "<none>")
    if r.status_code == 403:
        return SimpleCheck("UA policy (default UA)", True, f"UA={ua_sent!r} -> 403 as expected (policy enforced)")
    return SimpleCheck(
        "UA policy (default UA)",
        False,
        f"UA={ua_sent!r} -> {r.status_code} (expected 403 — policy NOT enforced as documented; recording honestly)",
    )


class _HTTP10Connection(http.client.HTTPSConnection):
    """http.client connection forced to send 'GET ... HTTP/1.0'. Mirrors
    ESP32 HTTPClient's useHTTP10(true), which openHttps() sets unconditionally
    (M-PR-LOCATIONS design: 'confirm Nominatim answers HTTP/1.0 sanely')."""
    _http_vsn = 10
    _http_vsn_str = "HTTP/1.0"


def run_http10_check() -> SimpleCheck:
    cc, postcode = "NL", "2513AA"
    path = f"/search?country={cc}&postalcode={quote(postcode)}&format=jsonv2&limit=1&addressdetails=0"
    _throttle()
    try:
        ctx = ssl.create_default_context()
        conn = _HTTP10Connection(HOST, 443, timeout=TIMEOUT_S, context=ctx)
        # http.client only auto-adds a Host header when _http_vsn == 11 (verified
        # against example.com during script dev: HTTP/1.0 request without an
        # explicit Host header got a bare 403/421 from the Cloudflare-fronted
        # host — not a Nominatim-specific quirk, a Python http.client quirk).
        # ESP32 HTTPClient always sends Host explicitly regardless of HTTP
        # version, so set it here too to test the behaviour firmware will see.
        conn.request("GET", path, headers={"Host": HOST, "User-Agent": PROJECT_UA, "Connection": "close"})
        resp = conn.getresponse()
        body = resp.read()
        status = resp.status
        transfer_encoding = resp.getheader("Transfer-Encoding")
        conn.close()
    except Exception as e:  # noqa: BLE001 — probe script, report any failure honestly
        return SimpleCheck("HTTP/1.0 compat", False, f"request error: {type(e).__name__}: {e}")
    ok = status == 200 and not transfer_encoding  # HTTP/1.0 has no chunked transfer-encoding
    detail = f"status={status} bytes={len(body)} transfer-encoding={transfer_encoding!r}"
    return SimpleCheck("HTTP/1.0 compat", ok, detail)


BLOCK_RE = re.compile(r'static const char (\w+)\[\]\s*=\s*R"EOF\((.*?)\)EOF";', re.DOTALL)


def load_open_meteo_root_ca() -> str:
    text = CERTS_H.read_text()
    m = BLOCK_RE.search(text)
    for name, pem in BLOCK_RE.findall(text):
        if name == "OPEN_METEO_ROOT_CA":
            return pem.strip() + "\n"
    raise RuntimeError(f"OPEN_METEO_ROOT_CA not found in {CERTS_H}")


def run_cert_verify() -> CertResult:
    """Exact method of run/check-datatask-certs: openssl s_client -CAfile
    <root-only> -verify_return_error against the live host, using the PEM
    the firmware would pin (OPEN_METEO_ROOT_CA — NOMINATIM_ROOT_CA is a
    same-cert alias that doesn't exist in dataTaskCerts.h yet, see report)."""
    pem = load_open_meteo_root_ca()
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(pem)
        ca_path = f.name
    try:
        proc = subprocess.run(
            ["openssl", "s_client", "-connect", f"{HOST}:443", "-servername", HOST,
             "-CAfile", ca_path, "-verify_return_error"],
            input="", capture_output=True, text=True, timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return CertResult("ERROR", "timed out")
    except FileNotFoundError:
        return CertResult("ERROR", "openssl not on PATH")
    finally:
        Path(ca_path).unlink(missing_ok=True)

    out = proc.stdout + proc.stderr
    m = re.search(r"Verify return code: (\d+) \(([^)]+)\)", out)
    status = "ERROR"
    detail = "no verify result in openssl output"
    if m:
        code, msg = m.group(1), m.group(2)
        status = "PASS" if code == "0" else "FAIL"
        detail = msg if code == "0" else f"verify code {code} ({msg})"

    # Second call to get the *served* chain's subject/issuer lines
    # (cross-sign evidence) — separate from the strict-verify call above so
    # the pinned-root verify result is never influenced by -showcerts.
    chain_lines: list[str] = []
    try:
        proc2 = subprocess.run(
            ["openssl", "s_client", "-connect", f"{HOST}:443", "-servername", HOST, "-showcerts"],
            input="", capture_output=True, text=True, timeout=TIMEOUT_S,
        )
        out2 = proc2.stdout + proc2.stderr
        capture = False
        in_pem = False
        for line in out2.splitlines():
            if line.startswith("Certificate chain"):
                capture = True
                continue
            if not capture:
                continue
            if line.startswith("-----BEGIN CERTIFICATE-----"):
                in_pem = True
                continue
            if line.startswith("-----END CERTIFICATE-----"):
                in_pem = False
                continue
            if in_pem:
                continue
            if line.strip() == "---":
                break  # end of "Certificate chain" section
            if line.strip():
                chain_lines.append(line.rstrip())
    except Exception:  # noqa: BLE001
        pass

    return CertResult(status, detail, chain_lines)


def human_report(matrix, ua_check, http10_check, cert) -> int:
    print("== Query matrix ==")
    max_size = 0
    for r in matrix:
        max_size = max(max_size, r.size_bytes)
        status = "PASS" if r.ok else "FAIL"
        print(f"{status:5s} {r.label:26s} status={r.status:<3d} bytes={r.size_bytes:<5d} "
              f"matched={r.matched} lat={r.lat!r}({r.lat_type}) note={r.note}")
        if r.display_name:
            print(f"        display_name={r.display_name!r}")
    print(f"\nmax response size observed: {max_size} bytes\n")

    print("== UA policy ==")
    print(f"{'PASS' if ua_check.ok else 'FAIL':5s} {ua_check.detail}")

    print("\n== HTTP/1.0 compat ==")
    print(f"{'PASS' if http10_check.ok else 'FAIL':5s} {http10_check.detail}")

    print("\n== Cert chain verify (nominatim.openstreetmap.org, OPEN_METEO_ROOT_CA) ==")
    print(f"{cert.status:5s} {cert.detail}")
    for line in cert.chain_lines:
        print(f"      {line}")

    all_ok = all(r.ok for r in matrix) and ua_check.ok and http10_check.ok and cert.status == "PASS"
    print(f"\n{'PASS' if all_ok else 'FAIL'}  overall: "
          f"{sum(r.ok for r in matrix)}/{len(matrix)} matrix, "
          f"UA={'ok' if ua_check.ok else 'FAIL'}, "
          f"HTTP10={'ok' if http10_check.ok else 'FAIL'}, "
          f"cert={cert.status}")
    return 0 if all_ok else 1


def markdown_report(matrix, ua_check, http10_check, cert) -> str:
    lines = []
    lines.append("### Query matrix\n")
    lines.append("| Query | Status | Bytes | Matched (expect) | lat type | display_name |")
    lines.append("|---|---|---|---|---|---|")
    for r in matrix:
        exp = "match" if r.expect_match else "no-match"
        got = "match" if r.matched else "no-match" if r.matched is not None else "?"
        mark = "OK" if r.ok else "**MISMATCH**"
        dn = (r.display_name or "")[:60]
        lines.append(f"| {r.label} | {r.status} | {r.size_bytes} | {got} ({exp}) {mark} | {r.lat_type} | {dn} |")
    max_size = max((r.size_bytes for r in matrix), default=0)
    lines.append(f"\nMax response size observed: **{max_size} bytes**.\n")

    lines.append("### UA policy\n")
    lines.append(f"- {'PASS' if ua_check.ok else 'FAIL'}: {ua_check.detail}\n")

    lines.append("### HTTP/1.0 compat\n")
    lines.append(f"- {'PASS' if http10_check.ok else 'FAIL'}: {http10_check.detail}\n")

    lines.append("### Cert chain verify\n")
    lines.append("```")
    lines.append(f"{cert.status}  {cert.detail}")
    for line in cert.chain_lines:
        lines.append(line)
    lines.append("```\n")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="also emit a markdown summary block to stdout")
    args = ap.parse_args()

    matrix = run_query_matrix()
    ua_check = run_ua_policy_check()
    http10_check = run_http10_check()
    cert = run_cert_verify()

    rc = human_report(matrix, ua_check, http10_check, cert)

    if args.report:
        print("\n\n----- markdown report -----\n")
        print(markdown_report(matrix, ua_check, http10_check, cert))

    return rc


if __name__ == "__main__":
    sys.exit(main())
