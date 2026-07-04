#!/usr/bin/env bash
# wifi_evidence.sh — standalone AP-availability logger + outage report.
#
# Purpose: collect timestamped, defensible evidence of a router's per-band
# radio dropouts (observed 2026-07-03: Linksys MX5600 FW 1.0.2.216845, 2.4 GHz
# radio off-air for 5-40+ s stretches while 5 GHz stayed up).
#
# Method: periodic active scan via nmcli from a normal managed-mode WiFi
# client — no root, no monitor mode, does not disturb the host's connection.
# An ABSENT verdict is only logged after an immediate confirmation rescan
# (two consecutive misses), which keeps single scan hiccups out of the record.
#
# Usage:
#   ./wifi_evidence.sh monitor [SSID] [INTERVAL_S]   # default: current SSID, 15 s
#   ./wifi_evidence.sh report  [LOGFILE]             # outage table + availability %
#
# Log lives in logs/wifi_evidence_<SSID>.log (gitignored). One line per sample:
#   2026-07-03T10:04:16 24G=present sig=82 ch=6 5G=present sig=89 ch=44 nbr24=4/71
#   2026-07-03T10:06:58 24G=ABSENT 5G=present sig=88 ch=44 nbr24=4/70  (confirmed by rescan)
# nbr24=<count>/<maxSig> = other 2.4 GHz APs seen in the SAME scan (the control:
#   ours ABSENT while nbr24 count stays >0 = the fault is our router, not the scan).
#
# INTERVAL note: a forced dual-band nmcli scan takes ~6-8 s, so that is the real
# floor — an INTERVAL below ~6 just means back-to-back scans. True 1 s sampling is
# not possible with active scanning (would need iw single-channel or monitor mode).
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
CMD="${1:-}"

scan_bands() {  # $1=ssid -> sets G24 G5 (empty=absent) + NBR (neighbour 2.4 control)
    local ssid="$1" all ours
    # One scan returns every AP; extract ours + a neighbour 2.4 GHz control from it.
    all=$(nmcli -t -f SSID,BSSID,CHAN,FREQ,SIGNAL dev wifi list --rescan yes 2>/dev/null)
    ours=$(echo "$all" | grep -i "^${ssid}:")
    G24=$(echo "$ours" | awk -F: '{n=NF; if ($(n-1) ~ /^2[0-9]{3} MHz$/) {print $(n-2)" "$NF; exit}}')
    G5=$(echo  "$ours" | awk -F: '{n=NF; if ($(n-1) ~ /^5[0-9]{3} MHz$/) {print $(n-2)" "$NF; exit}}')
    # NBR = "<count>/<maxSignal>" of OTHER APs on 2.4 GHz in the same scan. This is
    # the control: if ours goes ABSENT but NBR count stays >0, the scan worked and
    # the fault is OUR router, not a host scan hiccup or general-band interference.
    NBR=$(echo "$all" | awk -F: -v me="$ssid" '
        BEGIN{c=0; mx=0}
        { n=NF; if (tolower($1)!=tolower(me) && $(n-1) ~ /^2[0-9]{3} MHz$/) {
              c++; if ($NF+0>mx) mx=$NF } }
        END{ printf "%d/%d", c, mx }')
}

fmt() {  # $1="ch sig" or "" ; -> "present sig=N ch=N" | "ABSENT"
    [ -n "$1" ] && echo "present sig=${1##* } ch=${1%% *}" || echo "ABSENT"
}

case "$CMD" in
monitor)
    SSID="${2:-$(nmcli -t -f ACTIVE,SSID dev wifi list | awk -F: '/^yes/{print $2; exit}')}"
    INTERVAL="${3:-15}"
    [ -z "$SSID" ] && { echo "no SSID given and none active" >&2; exit 1; }
    LOG="$DIR/logs/wifi_evidence_${SSID}.log"
    mkdir -p "$DIR/logs"
    echo "$(date +%FT%T) === monitor start ssid=$SSID interval=${INTERVAL}s host=$(hostname) ===" | tee -a "$LOG"
    while true; do
        scan_bands "$SSID"
        note=""
        if [ -z "$G24" ]; then
            sleep 2; scan_bands "$SSID"   # confirmation rescan — two misses = ABSENT
            [ -z "$G24" ] && note="   (confirmed by rescan)" \
                          || note=""      # first miss was a scan hiccup; G24 now set
        fi
        echo "$(date +%FT%T) 24G=$(fmt "${G24:-}") 5G=$(fmt "${G5:-}") nbr24=${NBR:-0/0}$note" | tee -a "$LOG"
        sleep "$INTERVAL"
    done
    ;;
report)
    LOG="${2:-$(ls -t "$DIR"/logs/wifi_evidence_*.log 2>/dev/null | head -1)}"
    [ -f "$LOG" ] || { echo "no log found ($LOG)" >&2; exit 1; }
    echo "=== WiFi availability report — $(basename "$LOG") ==="
    echo "generated: $(date +%FT%T)   samples: $(grep -c ' 24G=' "$LOG")"
    echo
    awk '
    / 24G=/ {
        ts = $1
        down = ($2 ~ /ABSENT/) ? 1 : 0
        total++
        if (down) absent++
        if (down && !was) { start = ts; n++ }
        if (!down && was) printf "  outage %2d  %s -> %s\n", n, start, ts
        was = down; last = ts
    }
    END {
        if (was) printf "  outage %2d  %s -> %s (ongoing at log end)\n", n, start, last
        printf "\n2.4 GHz: %d/%d samples absent (availability %.1f%%), %d distinct outages\n",
               absent, total, total ? (100.0*(total-absent)/total) : 0, n
    }' "$LOG"
    echo
    echo "Note: samples are active scans from a second WiFi client (managed mode,"
    echo "nmcli). ABSENT lines are double-checked by an immediate confirmation"
    echo "rescan. 5G column is the same router's 5 GHz radio, logged as control."
    ;;
*)
    grep -E '^# ' "$0" | sed 's/^# //;s/^#//'
    exit 1
    ;;
esac
