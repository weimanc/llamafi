#!/usr/bin/env bash
# audit_log_hygiene.sh — fail-fast grep for log-hygiene regressions.
# Runs over our sketch (SpotifyDiyThing/) — vendored libs in lib/ are out of scope.
# Intended for review checklist + future CI gate.
#
# Banned patterns (per ADR-010 / TASK-016b/e):
#   - Bearer header literal printed to a sink
#   - URL containing client_secret=
#   - Serial.print* of an identifier matching *token*, *secret*, *refresh*
#     (case-insensitive), unless wrapped in redact()
#
# Exits 1 on first hit. Output is grep-style — file:line: matched-text.

set -u
cd "$(dirname "$0")/.." || exit 2

SKETCH=SpotifyDiyThing
fail=0

# 1. Bearer header in a print path.
hits=$(grep -RnE 'Serial\.(print|println|printf).*Bearer ' "$SKETCH" 2>/dev/null \
       | grep -v "redact(" || true)
if [ -n "$hits" ]; then
  echo "[!] Bearer header in Serial output:"
  echo "$hits"
  fail=1
fi

# 2. client_secret= in a literal URL string passed to a sink.
hits=$(grep -RnE 'client_secret=' "$SKETCH" 2>/dev/null \
       | grep -v "redact(" || true)
if [ -n "$hits" ]; then
  echo "[!] client_secret= literal:"
  echo "$hits"
  fail=1
fi

# 3. Serial.print* of an identifier whose name suggests a secret, without redact().
# We're conservative: any Serial.print<*>(<expr>) where <expr> contains
# token/secret/refresh as a sub-word and does NOT contain redact( is suspect.
hits=$(grep -RnE 'Serial\.(print|println|printf)[^;]*[Tt]oken[^;]*' "$SKETCH" 2>/dev/null \
       | grep -ivE 'redact\(|"[^"]*[Tt]oken[^"]*"\s*[,)]' || true)
hits+=$(printf '\n%s' "$(grep -RnE 'Serial\.(print|println|printf)[^;]*[Ss]ecret[^;]*' "$SKETCH" 2>/dev/null \
        | grep -ivE 'redact\(|"[^"]*[Ss]ecret[^"]*"\s*[,)]' || true)")
hits+=$(printf '\n%s' "$(grep -RnE 'Serial\.(print|println|printf)[^;]*[Rr]efresh[^;]*' "$SKETCH" 2>/dev/null \
        | grep -ivE 'redact\(|"[^"]*[Rr]efresh[^"]*"\s*[,)]' || true)")
hits=$(printf '%s' "$hits" | sed '/^$/d')
if [ -n "$hits" ]; then
  echo "[!] Serial.print* of secret-named identifier without redact():"
  echo "$hits"
  fail=1
fi

# 4. serializeJsonPretty(<doc>, Serial) — the historical configFile.h leak.
hits=$(grep -RnE 'serializeJson(Pretty)?\([^,]+,\s*Serial' "$SKETCH" 2>/dev/null || true)
if [ -n "$hits" ]; then
  echo "[!] serializeJson*(..., Serial) — config JSON dumped to Serial:"
  echo "$hits"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "audit_log_hygiene: clean."
fi
exit "$fail"
