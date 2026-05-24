#!/usr/bin/env bash
# Resolve each hostname the firmware needs and emit data/host_overrides.json.
# Re-run when CDN IPs rotate, then `pio run -e cyd2usb -t uploadfs`.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../data/host_overrides.json"
mkdir -p "$(dirname "$OUT")"

HOSTS=(
  accounts.spotify.com
  api.spotify.com
  i.scdn.co
  pool.ntp.org
  time.google.com
  time.cloudflare.com
)

resolve() {
  # Pick any reliable resolver on the host running this script.
  dig +short +time=2 +tries=1 @1.1.1.1 "$1" A | grep -E '^[0-9.]+$' | head -1
}

{
  echo '{'
  echo '  "hosts": {'
  first=1
  for h in "${HOSTS[@]}"; do
    ip="$(resolve "$h" || true)"
    if [[ -z "$ip" ]]; then
      echo "  WARN: failed to resolve $h, skipping" >&2
      continue
    fi
    [[ $first -eq 1 ]] || echo ','
    first=0
    printf '    "%s": "%s"' "$h" "$ip"
  done
  echo
  echo '  }'
  echo '}'
} > "$OUT"

echo "Wrote $OUT:"
cat "$OUT"
