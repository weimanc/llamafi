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
#   FAST24=1 sudo -E ./wifi_evidence.sh monitor ...  # 2.4-only iw mode (~1-2 s, root)
#   ./wifi_evidence.sh report  [LOGFILE]             # outage table + availability %
#
# Default (nmcli) mode scans both bands; the scan itself takes ~6-8 s, which is the
# real sampling floor (INTERVAL below ~6 just means back-to-back scans). For finer
# resolution, FAST24=1 uses `iw` to scan 2.4 GHz only (~1-2 s) — needs root, drops
# the 5 G control, and briefly stutters the host's own WiFi each scan. `sudo -E`
# preserves the FAST24 env var.
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

# FAST24=1 — 2.4 GHz-only mode via `iw` targeted scan (~1-2 s vs ~6-8 s dual-band).
# REQUIRES ROOT (iw active scan needs CAP_NET_ADMIN — run the whole logger under
# sudo). Tradeoffs: no 5 G control column (2.4-only); each scan briefly (~50-100 ms)
# pulls the card off its own channel, so the host's own WiFi micro-stutters — fine
# at a few-second cadence, avoid hammering. Signal is dBm here (nmcli mode is 0-100%).
# WIFI_DEV overrides the auto-detected interface.
scan_bands24() {  # $1=ssid -> sets G24 (present "sig ch"), NBR ("count/maxdBm"); G5=""
    local ssid="$1" dev raw
    dev="${WIFI_DEV:-$(nmcli -t -f DEVICE,TYPE dev | awk -F: '$2=="wifi"{print $1; exit}')}"
    G5=""
    raw=$(iw dev "$dev" scan freq 2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462 2>/dev/null)
    # Parse iw BSS blocks into "SSID<TAB>signal<TAB>freq" rows.
    local rows
    rows=$(echo "$raw" | awk '
        /^BSS /            {if(s!="")print s"\t"sig"\t"fr; s="";sig="";fr=""}
        /^[ \t]*freq:/     {fr=$2}
        /^[ \t]*signal:/   {sig=$2}
        /^[ \t]*SSID:/     {s=substr($0,index($0,"SSID:")+6)}
        END                {if(s!="")print s"\t"sig"\t"fr}')
    G24=$(echo "$rows" | awk -F'\t' -v me="$ssid" '$1==me{ch=int(($3-2407)/5); print $2"dBm "ch; exit}')
    NBR=$(echo "$rows" | awk -F'\t' -v me="$ssid" '
        BEGIN{c=0;mx=-200} $1!=me && $1!=""{c++; if($2+0>mx)mx=$2} END{printf "%d/%.0f", c, mx}')
}

scan_bands() {  # $1=ssid -> sets G24 G5 (empty=absent) + NBR (neighbour 2.4 control)
    if [ "${FAST24:-0}" = 1 ]; then scan_bands24 "$1"; return; fi
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
    mode="nmcli/dual-band (~6-8 s scan floor)"
    if [ "${FAST24:-0}" = 1 ]; then
        [ "$(id -u)" = 0 ] || { echo "FAST24 needs root (iw active scan): run under sudo" >&2; exit 1; }
        mode="iw/2.4-only (~1-2 s; no 5 G control; host WiFi micro-stutters per scan)"
    fi
    LOG="$DIR/logs/wifi_evidence_${SSID}.log"
    mkdir -p "$DIR/logs"
    echo "$(date +%FT%T) === monitor start ssid=$SSID interval=${INTERVAL}s host=$(hostname) mode=$mode ===" | tee -a "$LOG"
    while true; do
        scan_bands "$SSID"
        note=""
        if [ -z "$G24" ]; then
            sleep 2; scan_bands "$SSID"   # confirmation rescan — two misses = ABSENT
            [ -z "$G24" ] && note="   (confirmed by rescan)" \
                          || note=""      # first miss was a scan hiccup; G24 now set
        fi
        g5disp=$([ "${FAST24:-0}" = 1 ] && echo "n/a" || fmt "${G5:-}")
        echo "$(date +%FT%T) 24G=$(fmt "${G24:-}") 5G=${g5disp} nbr24=${NBR:-0/0}$note" | tee -a "$LOG"
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
