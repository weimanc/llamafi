#!/usr/bin/env python3
"""T_CERT_HOST_02 — offline cert expiry check (TASK-342, M-CERT-ERRCODE).

Validates run/check-datatask-certs's --expiry-only mode:
  1. A synthetic near-expiry cert (30-day validity) trips the WARN line.
  2. The real shipped roster (app/src/dataTaskCerts.h) stays silent — every
     pinned root currently expires 2035-2038 (see design doc), so a WARN
     against the real header would itself be a regression worth catching.

Fully offline: no network, no DUT, no serial port. Generates its own
self-signed cert via openssl req.

Usage:
  python3 tools/test_cert_preflight.py

Exit 0 = both checks pass. Exit 1 = one or more failures.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = PROJ_ROOT / "run" / "check-datatask-certs"
REAL_CERTS_H = PROJ_ROOT / "app" / "src" / "dataTaskCerts.h"

CERT_HEADER_TEMPLATE = '''// Synthetic cert header for T_CERT_HOST_02 — not real firmware output.
static const char TEST_NEAR_EXPIRY_ROOT_CA[] = R"EOF(
{pem}
)EOF";
'''


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


def run_expiry_only(certs_file: Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--expiry-only", "--certs-file", str(certs_file)],
        capture_output=True, text=True, timeout=30,
    )
    return proc.stdout + proc.stderr


def main() -> int:
    failures = 0

    # --- Check 1: synthetic near-expiry cert trips the warn ---------------
    pem = gen_near_expiry_pem(days=30)
    with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as f:
        f.write(CERT_HEADER_TEMPLATE.format(pem=pem))
        synthetic_h = Path(f.name)
    try:
        out = run_expiry_only(synthetic_h)
        if "WARN" in out and "TEST_NEAR_EXPIRY_ROOT_CA" in out:
            print("PASS  synthetic 30-day cert trips WARN")
        else:
            print(f"FAIL  synthetic 30-day cert did not trip WARN — output:\n{out}")
            failures += 1
    finally:
        synthetic_h.unlink(missing_ok=True)

    # --- Check 2: real shipped roster stays silent -------------------------
    out = run_expiry_only(REAL_CERTS_H)
    if "WARN" not in out:
        print("PASS  shipped roster (dataTaskCerts.h) stays silent")
    else:
        print(f"FAIL  shipped roster tripped an unexpected WARN — a real pin may be near expiry:\n{out}")
        failures += 1

    print()
    if failures:
        print(f"FAIL  {failures} check(s) failed.")
        return 1
    print("PASS  all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
