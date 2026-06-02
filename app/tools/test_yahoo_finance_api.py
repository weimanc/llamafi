#!/usr/bin/env python3
"""T_SF_01–T_SF_07 — Yahoo Finance API probe (StockApp POC, TASK-109i).

Validates the endpoints the StockApp firmware uses before any DUT flash.
Discovered during TASK-109i: Yahoo Finance v7/finance/quote returns 401 Unauthorized
(gated as of 2026-05). Data strategy revised to use v8/finance/chart for all fetches:

  List view  : 8 × GET v8/finance/chart/{symbol}?interval=1d&range=1d
               Parse chart.result[0].meta: regularMarketPrice + chartPreviousClose
               Derive changePct = (price - prevClose) / prevClose * 100

  Chart view : GET v8/finance/chart/{symbol}?interval={I}&range={R}
               YTD uses interval=1wk (22 pts, ~3.7 KB) — NOT 1d (101 pts, 12 KB > budget)

Checks:
  T_SF_01  Per-symbol quote requests (6 × chart 1d/1d) all return HTTP 200
  T_SF_02  meta.regularMarketPrice + meta.chartPreviousClose non-null for all symbols
  T_SF_03  Each quote payload fits DUT DynamicJsonDocument budget (<=8192 B)
  T_SF_04  Chart ranges (D1/D5/Mo1/Ytd) return HTTP 200
  T_SF_05  timestamp[] and close[] parallel arrays, non-empty, each range
  T_SF_06  Filtered close[] point count fits firmware chartPoints[110] buffer — each range
  T_SF_07  TLS cert issuer printed for TASK-109c pinning (informational)

No DUT, no credentials, no serial port required.
Run before TASK-109c — T_SF_07 output identifies the root CA for dataTaskCerts.h.

Usage:
  python3 tools/test_yahoo_finance_api.py
  python3 tools/test_yahoo_finance_api.py --chart-symbol NVDA
  python3 tools/test_yahoo_finance_api.py --no-tls

Exit 0 = all pass. Exit 1 = one or more failures.
"""
import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

SYMBOLS = ["AAPL", "AMD", "AMZN", "ARM", "GOOG", "META", "MSFT", "NVDA"]

CHART_URL_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

# Quote doc limit — dataTaskStorage.cpp fetchStockQuote() uses a JSON filter that
# extracts only regularMarketPrice + chartPreviousClose before ArduinoJson allocates
# (StaticJsonDocument<128> filter + StaticJsonDocument<256> doc, streaming parse).
# Raw payload size is irrelevant — only the filtered output size matters (LL-048).
QUOTE_DOC_BYTES = 256   # dataTaskStorage.cpp fetchStockQuote() StaticJsonDocument<256> doc

# Chart buffer limit — dataTaskStorage.cpp fetchStockChart() uses a JSON filter that
# extracts only close[] before ArduinoJson allocates (StaticJsonDocument<2048> doc).
# Raw payload size is irrelevant — only the non-null close[] point count matters.
# Firmware caps at 110: `if (r.len >= 110) break` → chartPoints[110] buffer (LL-040).
CHART_MAX_POINTS = 110  # appShell.h StockAppState::chartPoints[110]

# (range_param, interval_param, label)
# YTD uses 1wk interval — 1d would produce ~100 pts; 1wk stays well under 110.
RANGES = [
    ("1d",  "5m",  "D1"),
    ("5d",  "60m", "D5"),
    ("1mo", "1d",  "Mo1"),
    ("ytd", "1wk", "Ytd"),
]

YF_HOST = "query1.finance.yahoo.com"

HEADERS = {"User-Agent": "Mozilla/5.0"}   # 429 without a UA

# ── helpers ──────────────────────────────────────────────────────────────────

def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _ok(label, detail=""):
    print(f"  [PASS] {label}" + (f": {detail}" if detail else ""))


def _fail(label, detail=""):
    print(f"  [FAIL] {label}" + (f": {detail}" if detail else ""), file=sys.stderr)


def _info(label, detail=""):
    print(f"  [INFO] {label}" + (f": {detail}" if detail else ""))


# ── checks ────────────────────────────────────────────────────────────────────

def check_quote_reachable():
    """T_SF_01 — 8 per-symbol chart 1d/1d requests all return HTTP 200."""
    print("\nT_SF_01  Per-symbol quote requests (8 × chart 1d/1d) reachable")
    all_ok = True
    bodies = {}
    for sym in SYMBOLS:
        url = f"{CHART_URL_BASE}{sym}?interval=1d&range=1d"
        status, body = _get(url)
        if status == 200:
            _ok(sym, f"HTTP {status}  {len(body)} B")
            bodies[sym] = body
        else:
            _fail(sym, f"HTTP {status}: {body[:120].decode(errors='replace')}")
            all_ok = False
        time.sleep(0.2)
    return all_ok, bodies


def check_quote_fields(bodies):
    """T_SF_02 — meta.regularMarketPrice + meta.chartPreviousClose non-null."""
    print("\nT_SF_02  meta.regularMarketPrice + meta.chartPreviousClose present")
    all_ok = True
    for sym, body in bodies.items():
        try:
            doc  = json.loads(body)
            meta = doc["chart"]["result"][0]["meta"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            _fail(sym, f"parse error: {e}")
            all_ok = False
            continue
        price  = meta.get("regularMarketPrice")
        prev   = meta.get("chartPreviousClose")
        if price is None or prev is None:
            _fail(sym, f"regularMarketPrice={price!r}  chartPreviousClose={prev!r}")
            all_ok = False
        else:
            chg = (price - prev) / prev * 100 if prev else float("nan")
            _ok(sym, f"price={price:.2f}  prev={prev:.2f}  chg%={chg:+.2f}%")
    return all_ok


def check_quote_budget(bodies):
    """T_SF_03 — filtered quote output (2 meta fields) fits StaticJsonDocument<256>."""
    print(f"\nT_SF_03  Filtered quote output fits StaticJsonDocument<{QUOTE_DOC_BYTES}>")
    all_ok = True
    for sym, body in bodies.items():
        try:
            doc  = json.loads(body)
            meta = doc["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev  = meta.get("chartPreviousClose")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            _fail(sym, f"parse error: {e}")
            all_ok = False
            continue
        # Approximate filtered JSON size: only the two fields firmware extracts.
        n = len(json.dumps({"regularMarketPrice": price, "chartPreviousClose": prev}).encode())
        if n < QUOTE_DOC_BYTES:
            _ok(sym, f"filtered ~{n} B << StaticJsonDocument<{QUOTE_DOC_BYTES}>")
        else:
            _fail(sym, f"filtered {n} B >= StaticJsonDocument<{QUOTE_DOC_BYTES}> limit")
            all_ok = False
    return all_ok


def check_chart_ranges(chart_symbol):
    """T_SF_04–T_SF_06 — chart endpoint all ranges: reachable, valid arrays, budget."""
    print(f"\nT_SF_04  Chart ranges reachable (symbol={chart_symbol})")
    all_ok_04 = True
    range_bodies = {}
    for rng, interval, label in RANGES:
        url = f"{CHART_URL_BASE}{chart_symbol}?interval={interval}&range={rng}"
        status, body = _get(url)
        if status == 200:
            _ok(f"{label} (range={rng}&interval={interval})", f"HTTP {status}  {len(body)} B")
            range_bodies[label] = (rng, interval, body)
        else:
            _fail(f"{label}", f"HTTP {status}: {body[:120].decode(errors='replace')}")
            all_ok_04 = False
        time.sleep(0.3)

    print("\nT_SF_05  timestamp[] and close[] parallel arrays — each range")
    all_ok_05 = True
    null_warn = []
    for label, (_, _, body) in range_bodies.items():
        try:
            doc    = json.loads(body)
            result = doc["chart"]["result"][0]
            ts     = result.get("timestamp") or []
            closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            _fail(label, f"parse error: {e}")
            all_ok_05 = False
            continue
        n_ts  = len(ts)
        n_cl  = len(closes)
        nulls = sum(1 for v in closes if v is None)
        if n_ts == 0 or n_cl == 0:
            _fail(label, f"empty arrays: ts={n_ts}  closes={n_cl}")
            all_ok_05 = False
        elif n_ts != n_cl:
            _fail(label, f"length mismatch: ts={n_ts}  closes={n_cl}")
            all_ok_05 = False
        else:
            note = f"  ({nulls} null — firmware must skip)" if nulls else ""
            _ok(label, f"{n_ts} pts{note}")
            if nulls:
                null_warn.append(f"  {label}: {nulls}/{n_ts} null closes")

    print(f"\nT_SF_06  Filtered close[] fits firmware chartPoints[{CHART_MAX_POINTS}] — each range")
    all_ok_06 = True
    for label, (_, _, body) in range_bodies.items():
        try:
            doc    = json.loads(body)
            closes = (doc["chart"]["result"][0].get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            _fail(label, f"parse error: {e}")
            all_ok_06 = False
            continue
        non_null = sum(1 for v in closes if v is not None)
        if non_null <= CHART_MAX_POINTS:
            _ok(label, f"{non_null} non-null pts <= {CHART_MAX_POINTS}")
        else:
            _fail(label, f"{non_null} non-null pts exceeds chartPoints[{CHART_MAX_POINTS}] — firmware will silently truncate")
            all_ok_06 = False

    if null_warn:
        print()
        print("  NOTE — null close[] values (normal outside market hours):")
        for w in null_warn:
            print(w)
        print("  Firmware: skip null entries when building chartPoints[].")

    return all_ok_04 and all_ok_05 and all_ok_06


def check_tls(skip):
    """T_SF_07 — print full cert chain for TASK-109c root CA pinning (never fails).

    ssl.get_server_certificate() returns only the leaf.  We use openssl s_client
    -showcerts to get every cert in the chain, then display subject/issuer/dates
    for each.  The deepest cert the server sends (closest to the root) is the
    pinning candidate for dataTaskCerts.h — pinning it survives leaf rotation.
    The actual self-signed root is not sent by the server; fetch it from the CA's
    website or Mozilla's CA bundle if you want the longest-lived anchor.
    """
    print("\nT_SF_07  TLS cert chain (informational — for TASK-109c pinning)")
    if skip:
        _info("skipped via --no-tls")
        return True
    try:
        sc = subprocess.run(
            ["openssl", "s_client", "-connect", f"{YF_HOST}:443", "-showcerts"],
            input=b"", capture_output=True, timeout=10,
        )
        chain_pem = sc.stdout.decode(errors="replace")
    except FileNotFoundError:
        _info("openssl not on PATH — run manually:")
        print(f"  openssl s_client -connect {YF_HOST}:443 -showcerts 2>/dev/null")
        return True
    except subprocess.TimeoutExpired:
        _info("openssl s_client timed out")
        return True

    # Split into individual PEM blocks.
    import re
    pem_blocks = re.findall(
        r"(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)", chain_pem, re.DOTALL
    )
    if not pem_blocks:
        _info("no certificates found in s_client output")
        return True

    print(f"  {len(pem_blocks)} cert(s) in chain (0=leaf, {len(pem_blocks)-1}=deepest sent by server):")
    for i, pem in enumerate(pem_blocks):
        result = subprocess.run(
            ["openssl", "x509", "-noout", "-subject", "-issuer", "-dates"],
            input=pem.encode(), capture_output=True, timeout=5,
        )
        lines = result.stdout.decode(errors="replace").strip().splitlines()
        label = "leaf" if i == 0 else f"intermediate-{i}" if i < len(pem_blocks) - 1 else "deepest (pin candidate)"
        print(f"\n  [{i}] {label}")
        for line in lines:
            print(f"    {line.strip()}")

    print()
    print("  Pinning recommendation for dataTaskCerts.h:")
    print(f"  → Pin cert [{len(pem_blocks)-1}] (deepest in chain) as YAHOO_FINANCE_ROOT_CA[].")
    print("    This survives Yahoo leaf rotation. Replace only if DigiCert changes their CA family.")
    print("  → For maximum longevity: fetch the self-signed DigiCert Global Root G2 PEM")
    print("    from https://www.digicert.com/kb/digicert-root-certificates.htm")
    print("    and pin that instead (root not sent by server, must be fetched separately).")
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--chart-symbol", default="AAPL",
                        help="Symbol for chart range checks (default: AAPL)")
    parser.add_argument("--no-tls", action="store_true", help="Skip T_SF_07 cert dump")
    args = parser.parse_args()

    print("Yahoo Finance API probe — StockApp POC (TASK-109i)")
    print(f"Quote symbols : {', '.join(SYMBOLS)}  ({len(SYMBOLS)} symbols)")
    print(f"Chart symbol  : {args.chart_symbol}  ranges: D1(5m) D5(60m) Mo1(1d) Ytd(1wk)")
    print(f"DUT budget    : quote filtered ~50 B → StaticJsonDocument<{QUOTE_DOC_BYTES}>  chart={CHART_MAX_POINTS} pts → StaticJsonDocument<2048>")

    failures = []

    ok, quote_bodies = check_quote_reachable()
    if not ok:
        failures.append("T_SF_01")
    if quote_bodies:
        if not check_quote_fields(quote_bodies):
            failures.append("T_SF_02")
        if not check_quote_budget(quote_bodies):
            failures.append("T_SF_03")
    else:
        failures += ["T_SF_02", "T_SF_03"]

    if not check_chart_ranges(args.chart_symbol):
        failures.append("T_SF_04/05/06")

    check_tls(args.no_tls)

    print()
    if failures:
        print(f"FAIL — {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("PASS — all checks passed (T_SF_01–T_SF_07)")
    sys.exit(0)


if __name__ == "__main__":
    main()
