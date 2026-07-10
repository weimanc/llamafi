# M-PLANERADAR phase-0 fixture manifest

Design: `docs/architecture/designs/M-PLANERADAR/phase0-api-probe.md`
Source API: `https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}`
Each `<name>.json` is the compact body used by tools; `<name>.pretty.json` is the
human-readable copy (same data).

| Fixture | Origin | Captured | Notes |
|---|---|---|---|
| `home_13km.json` | live, home site (52.3676, 4.9041) dist 7.9 NM (corrected radius) | 2026-07-10 ~09:15 CEST (daytime re-capture; original 02:00 night capture superseded — review finding) | typical frame: 10 605 B, 23 records, 2 airborne — matches soak p50 |
| `busy_33km.json` | live, Schiphol site (52.3086, 4.7639); initial 18.0 NM night capture, then overwritten by `--hunt-max` at 19.9 NM (corrected radius) through the morning wave | 2026-07-10 | worst case: 34 921 B / 71 records at last trial run; hunt-max may still raise it |
| `sparse.json` | live, rural site (52.8, 6.9) dist 18.0 NM | 2026-07-10 ~02:00 CEST | empty `ac` at capture time |
| `empty.json` | live, rural site, dist 3.6 NM | 2026-07-10 ~02:00 CEST | empty `ac` |
| `ground_mix.json` | live, home site dist 7.2 NM | 2026-07-10 ~01:45 CEST | 5 records, all `alt_baro:"ground"` (Schiphol ground vehicles) — ground-filter test |
| `truncated.json` | **synthetic**: `busy_33km.json` first 60% of bytes | 2026-07-10 (re-derived evening from the final 71-ac capture) | cut mid-object; must fail parse cleanly |
| `nofields.json` | **synthetic**: `busy_33km.json` with `track/true_heading/mag_heading/dir/gs/tas/ias/flight/t` removed from every aircraft | 2026-07-10 (re-derived evening from the final 71-ac capture) | fallback-chain test |
| `soak.jsonl` | probe `--soak` log (not a fixture) | rolling | one JSON record per fetch: t/http/ms/bytes/ac/err |
| `soak_evening.jsonl` | probe `--soak` log, second time-of-day sample (not a fixture) | 2026-07-10 21:19-22:18 | 350/350 HTTP 200; shortened by decision (~58 min vs 6h) — see phase0-api-probe.md |
| `airports_preview.json` | OurAirports (davidmegginson/ourairports-data @ main), large_airport class — EHAM + EHRD only | 2026-07-10 | real runway-endpoint data for the Q4 preview-tool overlay (phase0-preview-ui.md); not an adsb.fi fixture |

**Byte-size note:** `<name>.json` files are re-serialized compact
(`json.dumps(…, separators=(",",":"))`), so their on-disk size differs
slightly from the raw wire size the probe logs (e.g. an empty response is
101 B on the wire, 88 B as a fixture).

**Naming note:** the `_33km`/`_13km` suffixes derive from the *outer-ring* scale
of the 25 km / 10 km presets as originally (under-)computed; the actual fetch
radii after the corrected `fetchRadiusKm()` formula are 36.8 km / 14.7 km.
Names kept for stability (they are capture labels, not measurements).

Regenerate live captures: `pr_adsb_probe.py --capture <name> --site <site> --preset <km>`.
Synthetic edits documented above; re-derive after re-capturing `busy_33km`.
