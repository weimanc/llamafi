#!/usr/bin/env bash
# dev_drops.sh — router-side device drop/rejoin monitor (Linksys Velop, JNAP).
#
# Polls the router's connected-device list + DHCP log and reports when any
# device DROPS off the WiFi and REJOINS — named, with band + signal at the
# event. This catches real client disconnects (the "my phone gets kicked off"
# symptom) regardless of SSID/band, straight from the AP's own view — no
# dependence on the host's own connection or a scanning logger.
#
# Password: read from env LINKSYS_PW, else the session file. See jnap.sh header.
#
# Usage:
#   ./dev_drops.sh                 # 30 s poll, log to logs/dev_drops.log
#   ./dev_drops.sh 15              # 15 s poll
#   WATCH_MACS="FE:D3:.. F2:D2:.." ./dev_drops.sh   # only flag these (still logs all)
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
ROUTER="${ROUTER:-192.168.1.1}"
INTERVAL="${1:-30}"
LOG="$DIR/logs/dev_drops.log"
mkdir -p "$DIR/logs"
PW="${LINKSYS_PW:-$(cat /tmp/claude-1000/-home-weiman-proj-esp-spotify/35543388-5234-4a10-ae2a-f83951f5c18d/scratchpad/.linksys_pw 2>/dev/null)}"

jnap() { # $1=action $2=body
  curl -sk -m 8 -X POST "http://$ROUTER/JNAP/" \
    -H "X-JNAP-Action: http://linksys.com/jnap/$1" \
    -H "X-JNAP-Authorization: Basic $(printf 'admin:%s' "$PW" | base64 -w0)" \
    -H "Content-Type: application/json" -d "${2:-{\}}"
}

emit() { echo "$(date +%FT%T) $*" | tee -a "$LOG"; }

# MAC -> friendly name from the DHCP lease table (best effort; falls back to MAC).
declare -A NAME
while IFS=$'\t' read -r mac name; do [ -n "$mac" ] && NAME[$mac]="$name"; done < <(
  jnap router/GetDHCPClientLeases '{}' | jq -r '.output.leases[]? | "\(.macAddress|ascii_upcase)\t\(.hostName // "?")"' 2>/dev/null)

nm() { echo "${NAME[$1]:-$1}"; }

emit "=== dev_drops start (poll ${INTERVAL}s, ${#NAME[@]} known devices) ==="

declare -A PREV_BAND PREV_SIG
first=1
while true; do
  # current connections: mac band sig rate
  cur=$(jnap networkconnections/GetNetworkConnections '{}' \
        | jq -r '.output.connections[]? | select(.wireless) | "\(.macAddress|ascii_upcase) \(.wireless.band) \(.wireless.signalDecibels) \(.negotiatedMbps)"' 2>/dev/null)
  declare -A NOW_BAND NOW_SIG
  while read -r mac band sig rate; do
    [ -z "$mac" ] && continue
    NOW_BAND[$mac]="$band"; NOW_SIG[$mac]="$sig"
    # REJOIN: present now, absent last cycle (skip first pass)
    if [ "$first" = 0 ] && [ -z "${PREV_BAND[$mac]:-}" ]; then
      emit "REJOIN  $(nm "$mac")  ${band} ${sig}dBm ${rate}Mbps"
    fi
  done <<< "$cur"
  # DROP: present last cycle, absent now
  if [ "$first" = 0 ]; then
    for mac in "${!PREV_BAND[@]}"; do
      if [ -z "${NOW_BAND[$mac]:-}" ]; then
        emit "DROP    $(nm "$mac")  (was ${PREV_BAND[$mac]} ${PREV_SIG[$mac]}dBm)"
      fi
    done
  fi
  # cold reconnects from the DHCP log (Discover = fresh association)
  jnap routerlog/GetDHCPLogEntries '{"firstEntryIndex":1,"entryCount":20}' \
    | jq -r '.output.entries[]? | select(.messageType=="Discover") | "\(.timestamp) \(.macAddress|ascii_upcase)"' 2>/dev/null \
    | while read -r ts mac; do
        key="dhcp:$ts:$mac"; f="$DIR/logs/.seen_dhcp"
        touch "$f"; grep -qF "$key" "$f" || { echo "$key" >> "$f"; emit "DHCP-COLD $(nm "$mac") ($ts)"; }
      done
  # roll state
  unset PREV_BAND PREV_SIG; declare -A PREV_BAND PREV_SIG
  for mac in "${!NOW_BAND[@]}"; do PREV_BAND[$mac]="${NOW_BAND[$mac]}"; PREV_SIG[$mac]="${NOW_SIG[$mac]}"; done
  unset NOW_BAND NOW_SIG
  first=0
  sleep "$INTERVAL"
done
