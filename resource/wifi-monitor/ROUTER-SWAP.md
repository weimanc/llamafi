# Router replacement guide — swapping out the Linksys Velop MX5600

> Captured 2026-07-03 from the live router via JNAP (`jnap.sh`). Re-read any value
> with `./jnap.sh raw <action>` if it may have changed since. Secrets (admin
> password, WiFi passphrase) are **not** stored here — read them from the running
> router or your password manager.

## TL;DR

There is **no meaningful ISP-specific configuration to copy.** The WAN is plain
**DHCP** — no PPPoE credentials, no static IP, no VLAN tag, no MAC clone. Set a new
router's WAN to DHCP (the default), match the LAN + WiFi below, and it works. The
only realistic snag is ISP MAC-binding (workaround below).

## Current router identity

| | |
|---|---|
| Model | Linksys **MX56HF** (Velop 6SP), single node |
| Firmware | 1.0.2.216845 (2026-01-16) |
| Serial | 66H10M22F02460 |
| Base MAC | `74:12:13:16:52:28` (WAN MAC ≈ base; radios are …:29 / …:2A) |
| Admin UI | http://192.168.1.1 (JNAP API at /JNAP/) |

## WAN (the ISP side) — nothing special

| Field | Value | Notes |
|---|---|---|
| WAN type | **DHCP** | auto-IP; no credentials/tags to copy |
| WAN IP | `100.64.73.201` | **CGNAT** (100.64/10) — you are behind ISP NAT, no public IP |
| Gateway | `100.64.0.3` | |
| DHCP lease | 10 min | short; carrier-typical |
| MTU | default (1500) | |
| IPv6 | Automatic | |
| MAC clone | disabled | ISP is not bound to a cloned MAC on our side |

**CGNAT caveat (not a router setting):** you have no public IP, so inbound
port-forwarding / self-hosting won't work regardless of router. A new router can't
change this — it's an ISP-side call (ask them for a public/static IP if you need one).

## LAN (replicate these so devices don't need reconfiguring)

| Field | Value |
|---|---|
| Router IP / subnet | `192.168.1.1` / `255.255.255.0` (/24) |
| DHCP | enabled, range `192.168.1.10` – `192.168.1.254`, lease 1440 min |
| DNS handed out | `8.8.8.8` / `1.1.1.1` (Google / Cloudflare — not ISP DNS) |
| Static reservations | none |

## WiFi (reuse SSID + password → every device auto-reconnects)

| Band | SSID | Security | Channel | Width |
|---|---|---|---|---|
| 2.4 GHz | `<home-ssid>-2.4Ghz` | WPA2-Personal | fixed (3) | **20 MHz / "Standard"** |
| 5 GHz | `<home-ssid>` | WPA2-Personal | fixed (non-DFS pref.) | Wide80 |

> **The setting that actually fixed the 2.4 GHz dropouts: width = 20 MHz.** Our
> channel-pinning only reduced them (~6x); the ISP set 2.4 GHz width from Auto
> (40 MHz-capable) to 20 MHz on 2026-07-20 and the drops stopped (316 blackouts in
> the 3 days before → ~0 after; see README RESOLUTION). 40 MHz on 2.4 GHz forces
> the AP to periodically scan the band (40/20 coexistence), taking the radio
> off-air — worst in the evening when the band is busy. **On any router: set 2.4
> GHz to 20 MHz, fixed channel. Do this first.**

> Both channels are manually pinned (2.4→6 on 2026-07-03, 5 GHz→44 on 2026-07-04)
> to reduce this unit's auto-channel scans taking the radios off-air. **Pin BOTH
> bands to fixed channels on a new router** — 2.4-auto causes long blackouts, and
> 5 GHz-auto's background scan causes short (~60 s-periodic) 2.4 blackouts; leaving
> either on auto keeps a scan running (see README.md root-cause). Pick the 2.4
> channel for the weakest client's RSSI, not neighbour count (6 tested good for the
> ESP32 here; 11 was worse). 5 GHz: any non-DFS channel (44 = UNII-1, no radar scan).
> Note: pinning both **greatly reduced but did not eliminate** the 2.4 blackouts
> on this MX5600. Same-instrument A/B (2026-07-06): AUTO ~1 blackout/2.1 min → both
> PINNED ~1 per 13 min avg (bursty), and the *long* (5–40 s, DUT-killing) sweeps go
> away entirely — the residual is short ~3 s blips. Only the 2.4 radio drops (5 GHz
> control: 0 vs 33). The persistent residual is a genuine radio/firmware trait, not
> config — reason enough to prefer a different router (or a newer firmware).

## Swap procedure

1. **Note the WiFi passphrase** (read it now: `./jnap.sh raw wirelessap/GetRadioInfo`
   → `.settings.wpaPersonalSettings.passphrase`) — you'll re-enter it on the new router.
2. New router: set **WAN = DHCP** (default), **LAN = 192.168.1.1/24 + DHCP on**.
3. New router WiFi: SSID `<home-ssid>`, WPA2 (or WPA2/WPA3), same passphrase,
   **2.4 GHz set to 20 MHz width + fixed channel** (the width is the important one
   — see the WiFi table note above).
4. Power off the Linksys, connect the new router's WAN port to the same ONT/handoff,
   power on.
5. If the new router **gets a WAN IP** (check its status page shows a `100.64.x.x`
   address) — done, everything reconnects.
6. If it **does not get a WAN IP** → ISP MAC-binding. Either:
   - clone the Linksys WAN MAC `74:12:13:16:52:28` onto the new router's WAN, **or**
   - power-cycle the ONT/fiber handoff for ~5 min to clear the ISP's DHCP binding,
     then reboot the new router. (The 10-min lease suggests bindings clear fast here.)

## Re-reading live values before you swap

```sh
cd resource/wifi-monitor
read -rs LINKSYS_PW && export LINKSYS_PW     # admin password, silent
./jnap.sh raw router/GetWANSettings          # WAN type (confirm still DHCP)
./jnap.sh raw router/GetLANSettings          # LAN + DHCP range + reservations
./jnap.sh radio                              # SSID / security / channel / passphrase
```

If `GetWANSettings` ever shows `wanType` other than `DHCP` (e.g. `PPPoE`), the ISP
changed the handoff and you'll need those credentials — re-capture this file then.
