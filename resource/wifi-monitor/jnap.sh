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
raw)   jnap "$2" "${3:-{\}}" | pp ;;
*) grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
