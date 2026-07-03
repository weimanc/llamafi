# wifi-monitor — router radio-dropout evidence collector

Standalone host-side tool. No root, no monitor mode, no project dependencies —
just `nmcli` (NetworkManager) on any Linux laptop on the same network.

Born 2026-07-03: the Linksys MX5600 (FW 1.0.2.216845) was caught taking its
**2.4 GHz radio off the air for 5–40+ second stretches** while 5 GHz stayed up.
Confirmed by two independent observers: an ESP32 running a promiscuous-mode
beacon watcher at the antenna (`app/tools/wifi_watch.py`, TASK-282), and this
host's own radio via active scans. Cross-referenced evidence: M-WIFI-DIAG
(docs/architecture/designs/M-WIFI-DIAG-outage-attribution.md), TASK-282/283.

## Collect

```sh
./wifi_evidence.sh monitor                  # current SSID, 15 s samples
./wifi_evidence.sh monitor yellowbrickroad 15
```

Runs until Ctrl-C. Appends to `logs/wifi_evidence_<SSID>.log` (gitignored).
Leave it running for days — that's the point. For unattended collection,
`tmux new -s wifi ./wifi_evidence.sh monitor` or a systemd user unit.

An `ABSENT` verdict is only logged after an immediate confirmation rescan
(two consecutive scan misses ~2 s apart), so single scan hiccups don't
pollute the record.

## Report (for the ISP complaint)

```sh
./wifi_evidence.sh report
```

Produces a dated outage table + availability percentage:

```
  outage  1  2026-07-03T10:03:22 -> 2026-07-03T10:04:16
2.4 GHz: 41/312 samples absent (availability 86.9%), 7 distinct outages
```

The 5 GHz column doubles as the control: same router, same location, same
observer — only the 2.4 GHz band drops. That's what makes it a router defect
rather than "your WiFi environment", which is what the ISP will claim first.

## Root cause (2026-07-03)

`jnap.sh` (Velop JNAP HTTP API driver — no SSH/telnet on these units) read the
live radio config and found the 2.4 GHz radio set to **`channel: 0` (auto-select)**.
Auto-channel-selection periodically takes the radio off-air to survey — the exact
5–40 s beacon blackouts both observers caught. The Linksys phone app does **not**
expose a manual 2.4 GHz channel control; the JNAP `wirelessap/SetRadioSettings`
action does. Pinned 2.4 GHz to a fixed channel (auto-channel disabled) as the fix:

```sh
read -rs LINKSYS_PW && export LINKSYS_PW   # admin password, silent
./jnap.sh check                            # verify auth
./jnap.sh radio                            # read both radios' settings
# SetRadioSettings write: see git log / rebuild payload from ./jnap.sh radio
```

**Channel choice — optimise for the WEAK client's RSSI, not neighbour count.**
First pinned ch 11 (fewest neighbours by host survey); the ESP32 then saw the AP
at −65 dBm and kept dropping while the *host* saw it strong (−59) and present —
i.e. a DUT-antenna-margin problem, not the router. Re-pinned ch 6 where the
ESP32 sits at −54 dBm (its healthy baseline). Lesson: the CYD's weak antenna
(design H-C) is ~15 dB down from a laptop; 10 dB of RSSI margin beats avoiding
two co-channel neighbours. Compare host `sig` vs the DUT beacon `rssi`
(`app/tools/wifi_watch.py` `get beacon`) before committing a channel.

If a firmware update later re-enables auto-channel, re-pin. If the 2.4 GHz radio
still blackouts on a *fixed* channel **and the host confirms it ABSENT** (not
just the DUT), that's a hardware/firmware defect with no config workaround —
escalate to Linksys/ISP with the outage report below. A DUT-only drop while the
host sees the AP present is a client-side margin issue, not a router fault.

## What strengthens the complaint

- Days of samples, not minutes (dropouts cluster in evenings here).
- Router model + firmware version + reboot timestamps noted in the log
  (add them: `echo "$(date +%FT%T) === NOTE router rebooted ===" >> logs/...`).
- The 5 GHz control staying green through every 2.4 GHz outage.
- If they ask "is it your device?": two independent radios observed the same
  absences at the same timestamps (this tool + the ESP32 beacon watcher).
