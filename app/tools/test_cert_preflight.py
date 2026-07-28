#!/usr/bin/env python3
"""T_CERT_HOST_01/02 — cert preflight checker tests (TASK-342/343, M-CERT-ERRCODE).

T_CERT_HOST_02 (offline, no network) validates --expiry-only:
  1. A synthetic near-expiry cert (30-day validity) trips the WARN line.
  2. The real shipped roster (app/src/dataTaskCerts.h) stays silent — every
     pinned root currently expires 2035-2038 (see design doc), so a WARN
     against the real header would itself be a regression worth catching.

T_CERT_HOST_01 (needs network — hits a live host) validates --propose-fix:
  A cert header with OPEN_METEO_ROOT_CA pointed at an unrelated-but-valid
  pinned root (YAHOO_FINANCE_ROOT_CA's DigiCert root, guaranteed mismatch —
  api.open-meteo.com's real chain roots to ISRG) makes the preflight FAIL,
  and the resulting --propose-fix report names the chain's actual serving
  root (ISRG Root X1, via the cross-signed "ISRG Root YR" intermediate —
  same case the design doc's Nominatim discussion describes).

Usage:
  python3 tools/test_cert_preflight.py

Exit 0 = all checks pass. Exit 1 = one or more failures.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = PROJ_ROOT / "run" / "check-datatask-certs"
REAL_CERTS_H = PROJ_ROOT / "app" / "src" / "dataTaskCerts.h"

CERT_HEADER_TEMPLATE = '''// Synthetic cert header for {label} — not real firmware output.
static const char {const_name}[] = R"EOF(
{pem}
)EOF";
'''

BLOCK_RE = re.compile(
    r'static const char (\w+)\[\]\s*=\s*R"EOF\((.*?)\)EOF";', re.DOTALL
)


def gen_near_expiry_pem(days: int) -> str:
    proc = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", "/dev/null", "-days", str(days),
         "-subj", "/CN=test-near-expiry", "-out", "-"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0 or "BEGIN CERTIFICATE" not in proc.stdout:
        raise RuntimeError(f"openssl req failed: {proc.stderr}")
    return proc.stdout.strip()


def run_checker(*extra_args: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), *extra_args],
        capture_output=True, text=True, timeout=60,
    )
    return proc.stdout + proc.stderr


def t_cert_host_02() -> int:
    failures = 0

    # Check 1: synthetic near-expiry cert trips the warn.
    pem = gen_near_expiry_pem(days=30)
    with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as f:
        f.write(CERT_HEADER_TEMPLATE.format(
            label="T_CERT_HOST_02", const_name="TEST_NEAR_EXPIRY_ROOT_CA", pem=pem))
        synthetic_h = Path(f.name)
    try:
        out = run_checker("--expiry-only", "--certs-file", str(synthetic_h))
        if "WARN" in out and "TEST_NEAR_EXPIRY_ROOT_CA" in out:
            print("PASS  T_CERT_HOST_02a: synthetic 30-day cert trips WARN")
        else:
            print(f"FAIL  T_CERT_HOST_02a: synthetic 30-day cert did not trip WARN — output:\n{out}")
            failures += 1
    finally:
        synthetic_h.unlink(missing_ok=True)

    # Check 2: real shipped roster stays silent.
    out = run_checker("--expiry-only", "--certs-file", str(REAL_CERTS_H))
    if "WARN" not in out:
        print("PASS  T_CERT_HOST_02b: shipped roster (dataTaskCerts.h) stays silent")
    else:
        print(f"FAIL  T_CERT_HOST_02b: shipped roster tripped an unexpected WARN:\n{out}")
        failures += 1

    return failures


def t_cert_host_01() -> int:
    real_text = REAL_CERTS_H.read_text()
    real_certs = dict(BLOCK_RE.findall(real_text))
    mismatched_pem = real_certs["YAHOO_FINANCE_ROOT_CA"].strip()  # DigiCert — unrelated to ISRG

    with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as f:
        f.write(CERT_HEADER_TEMPLATE.format(
            label="T_CERT_HOST_01", const_name="OPEN_METEO_ROOT_CA", pem=mismatched_pem))
        mismatch_h = Path(f.name)

    with tempfile.TemporaryDirectory() as scratch_dir:
        try:
            out = run_checker("--certs-file", str(mismatch_h),
                               "--propose-fix", "--scratch-dir", scratch_dir)
        finally:
            mismatch_h.unlink(missing_ok=True)

        if "FAIL  api.open-meteo.com" not in out:
            print(f"FAIL  T_CERT_HOST_01a: expected a preflight FAIL for api.open-meteo.com — output:\n{out}")
            return 1
        print("PASS  T_CERT_HOST_01a: mismatched root FAILs preflight as expected")

        m = re.search(r"propose-fix report: (\S+)", out)
        if not m:
            print(f"FAIL  T_CERT_HOST_01b: no propose-fix report path in output:\n{out}")
            return 1
        report = Path(m.group(1))
        if not report.exists():
            print(f"FAIL  T_CERT_HOST_01b: report path printed but file missing: {report}")
            return 1

        report_text = report.read_text()
        # The chain's real serving root is ISRG (either sent directly, self-
        # signed, or named as the issuer of a cross-signed intermediate —
        # both are correct per the design doc's Nominatim precedent). Either
        # way "ISRG" must appear, and a PEM block must be present so a human
        # has something to paste.
        checks = {
            "names ISRG in the report": "ISRG" in report_text,
            "includes a PEM block": "-----BEGIN CERTIFICATE-----" in report_text,
            "includes the fingerprint judgement-call reminder": "fingerprint" in report_text.lower(),
            "includes the replace-vs-bundle judgement-call reminder": "bundle" in report_text.lower(),
            "never touches dataTaskCerts.h": "never touches" in report_text.lower(),
        }
        failures = 0
        for desc, ok in checks.items():
            if ok:
                print(f"PASS  T_CERT_HOST_01c: report {desc}")
            else:
                print(f"FAIL  T_CERT_HOST_01c: report does NOT {desc}")
                failures += 1
        return failures


def main() -> int:
    failures = t_cert_host_02()
    failures += t_cert_host_01()

    print()
    if failures:
        print(f"FAIL  {failures} check(s) failed.")
        return 1
    print("PASS  all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
