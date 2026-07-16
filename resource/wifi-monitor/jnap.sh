#!/usr/bin/env bash
# jnap.sh — drive a Linksys Velop router via its JNAP HTTP API.
#
# No SSH/telnet on Velop; JNAP (JSON over HTTP POST to /JNAP/) is the only CLI.
# Username is always "admin"; password = router admin password (NOT the WiFi
# password, NOT necessarily default). Auth header is Basic base64(admin:PW).
#
# Password handling — never pass it on the command line (leaks to shell history
# / process list). Put it in the environment for the current shell only:
#     read -rs LINKSYS_PW && export LINKSYS_PW      # prompts, no echo
# then run this script. Or:  LINKSYS_PW='...' ./jnap.sh <cmd>
#
# Commands:
#   ./jnap.sh info                      # GetDeviceInfo (no auth needed)
#   ./jnap.sh raw <action> [json]       # any JNAP action, e.g.
#       ./jnap.sh raw wirelessap/GetRadioInfo
#   ./jnap.sh radio                     # GetRadioInfo (2.4/5 GHz channel+mode)
#   ./jnap.sh check                     # verify the password works
#   ./jnap.sh logon                     # enable the router event log (SetLogSettings)
#   ./jnap.sh dhcplog [MAC]             # DHCP log entries (optionally filtered to one
#   ./jnap.sh dhcpfollow               # live tail of the DHCP log (new (re)connects)
#                                         client MAC). A full Discover->Ack handshake =
#                                         a fresh association after a disconnect, so this
#                                         is a ROUTER-SIDE reconnect timestamp. The only
#                                         readable log this firmware exposes; there is NO
#                                         radio/system/event log (GetRadioInfo* is config
#                                         only). DUT MAC on this bench: D4:8A:FC:C8:EE:D0.
set -u

ROUTER="${ROUTER:-192.168.1.1}"
BASE="http://$ROUTER/JNAP/"
PFX="http://linksys.com/jnap/"

auth_hdr() {
    [ -n "${LINKSYS_PW:-}" ] || { echo "LINKSYS_PW not set (see header)" >&2; return 1; }
    printf 'X-JNAP-Authorization: Basic %s' \
        "$(printf 'admin:%s' "$LINKSYS_PW" | base64 -w0)"
}

jnap() {  # $1=action  $2=json-body  ($3=noauth to skip auth header)
    local action="$1" body="${2:-{\}}" hdr=()
    [ "${3:-}" = noauth ] || hdr=(-H "$(auth_hdr)") || return 1
    curl -sk -m 8 -X POST "$BASE" \
        -H "X-JNAP-Action: ${PFX}$1" \
        -H "Content-Type: application/json" \
        "${hdr[@]}" -d "$body"
}

pp() { if command -v jq >/dev/null; then jq .; else cat; fi; }

case "${1:-}" in
info)  jnap core/GetDeviceInfo '{}' noauth | pp ;;
check) jnap core/CheckAdminPassword '{}' | pp ;;
radio) jnap wirelessap/GetRadioInfo '{}' | pp ;;
logon) jnap routerlog/SetLogSettings '{"isLoggingEnabled":true}' | pp ;;
dhcplog)
    out=$(jnap routerlog/GetDHCPLogEntries '{"firstEntryIndex":1,"entryCount":100}')
    if command -v jq >/dev/null; then
        if [ -n "${2:-}" ]; then
            echo "$out" | jq -r --arg m "$2" \
              '.output.entries[]? | select(.macAddress==($m|ascii_upcase)) | "\(.timestamp) \(.messageType) \(.ipAddress // "")"'
        else
            echo "$out" | jq -r '.output.entries[]? | "\(.timestamp) \(.messageType) \(.macAddress) \(.ipAddress // "")"'
        fi
    else echo "$out"; fi ;;
dhcpfollow)
    # tail -f style: poll the DHCP log, print only NEW entries as they appear.
    # The router log is poll-only (no streaming), so we emulate it. Ctrl-C to stop.
    declare -A NM
    while IFS=$'\t' read -r m n; do NM[$m]="$n"; done < <(
      jnap router/GetDHCPClientLeases '{}' | jq -r '.output.leases[]?|"\(.macAddress|ascii_upcase)\t\(.hostName//"?")"' 2>/dev/null)
    seen=$(mktemp)
    echo "following router DHCP log (new device (re)connects appear below; Ctrl-C to stop)"
    while true; do
      jnap routerlog/GetDHCPLogEntries '{"firstEntryIndex":1,"entryCount":80}' \
        | jq -r '.output.entries[]?|"\(.timestamp)\t\(.messageType)\t\(.macAddress|ascii_upcase)\t\(.ipAddress//"")"' 2>/dev/null \
        | while IFS=$'\t' read -r ts mt mac ip; do
            key="$ts|$mt|$mac"
            grep -qxF "$key" "$seen" 2>/dev/null || { echo "$key" >> "$seen"; \
              printf '%s  %-9s %-20s %s\n' "$ts" "$mt" "${NM[$mac]:-$mac}" "$ip"; }
          done
      sleep 4
    done ;;
raw)   jnap "$2" "${3:-{\}}" | pp ;;
*) grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
