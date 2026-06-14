#!/usr/bin/env python3
"""gen_webradio_countries.py — Generate kWebRadioCountries[] for the Web Radio app.

Steps:
  1. Parse kCities[] in app/src/settings/cities.h to extract unique ISO 3166-1 alpha-2 codes.
  2. Fetch https://de1.api.radio-browser.info/json/countrycodes and build a station-count map.
  3. Print a coverage report (flag codes with 0 stations).
  4. Output the static C array, sorted by display name, to stdout AND app/gen/webradio_countries.h.

Usage:
  ~/proj/esp/venv/bin/python3 app/tools/gen_webradio_countries.py
"""

import re
import sys
import urllib.request
import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Hardcoded display-name map for all ISO codes found in cities.h
# (covers the ~35 codes present; add more if cities.h is ever extended)
# ---------------------------------------------------------------------------
COUNTRY_NAMES = {
    "AE": "United Arab Emirates",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "AZ": "Azerbaijan",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "EG": "Egypt",
    "ES": "Spain",
    "FI": "Finland",
    "FJ": "Fiji",
    "FR": "France",
    "GB": "United Kingdom",
    "GH": "Ghana",
    "GR": "Greece",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IN": "India",
    "IQ": "Iraq",
    "IR": "Iran",
    "IT": "Italy",
    "JP": "Japan",
    "KE": "Kenya",
    "KR": "South Korea",
    "KZ": "Kazakhstan",
    "LK": "Sri Lanka",
    "MA": "Morocco",
    "MM": "Myanmar",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NC": "New Caledonia",
    "NG": "Nigeria",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NZ": "New Zealand",
    "PE": "Peru",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TH": "Thailand",
    "TR": "Turkey",
    "TW": "Taiwan",
    "UA": "Ukraine",
    "US": "United States",
    "UZ": "Uzbekistan",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "ZA": "South Africa",
}

# ---------------------------------------------------------------------------
# Step 1: parse cities.h
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CITIES_H = REPO_ROOT / "app" / "src" / "settings" / "cities.h"
OUT_H = REPO_ROOT / "app" / "gen" / "webradio_countries.h"

print(f"Parsing {CITIES_H} ...", file=sys.stderr)

cities_text = CITIES_H.read_text()

# Each struct initialiser row looks like:
#   { "Auckland", "NZ", ...
# The country code is the 2nd quoted string field in each initialiser.
# Pattern: opening brace, optional whitespace, quoted city, comma, optional
# whitespace, quoted country code.
ROW_RE = re.compile(
    r'\{\s*"[^"]*"\s*,\s*"([A-Z]{2})"\s*,',
)

raw_codes = ROW_RE.findall(cities_text)
unique_codes = sorted(set(raw_codes))

print(f"  Found {len(raw_codes)} city rows, {len(unique_codes)} unique country codes.", file=sys.stderr)
print(f"  Codes: {', '.join(unique_codes)}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Step 2: fetch radio-browser.info country codes
# ---------------------------------------------------------------------------
API_URL = "https://de1.api.radio-browser.info/json/countrycodes"
print(f"\nFetching {API_URL} ...", file=sys.stderr)

req = urllib.request.Request(
    API_URL,
    headers={"User-Agent": "esp_spotify/gen_webradio_countries.py"},
)
with urllib.request.urlopen(req, timeout=15) as resp:
    rb_data = json.load(resp)

# Build map: ISO code (upper) -> station count
rb_map = {}
for entry in rb_data:
    iso = (entry.get("iso_3166_1") or entry.get("name") or "").upper().strip()
    count = int(entry.get("stationcount", 0))
    if iso:
        rb_map[iso] = rb_map.get(iso, 0) + count

print(f"  radio-browser.info returned {len(rb_data)} entries, {len(rb_map)} unique codes.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Step 3: coverage report
# ---------------------------------------------------------------------------
print("\n--- Coverage report ---", file=sys.stderr)
zero_station_codes = []
for code in unique_codes:
    count = rb_map.get(code, 0)
    status = "OK" if count > 0 else "ZERO STATIONS"
    display = COUNTRY_NAMES.get(code, f"(unknown — add to COUNTRY_NAMES)")
    print(f"  {code:4s}  {count:6d} stations  {status:14s}  {display}", file=sys.stderr)
    if count == 0:
        zero_station_codes.append(code)

print(f"\n  Total: {len(unique_codes)} codes; {len(zero_station_codes)} with zero stations.", file=sys.stderr)
if zero_station_codes:
    print(f"  Zero-station codes: {', '.join(zero_station_codes)}", file=sys.stderr)

# Check for codes that appear in cities.h but are missing from COUNTRY_NAMES
unknown_codes = [c for c in unique_codes if c not in COUNTRY_NAMES]
if unknown_codes:
    print(f"\n  WARNING: codes not in COUNTRY_NAMES dict: {', '.join(unknown_codes)}", file=sys.stderr)
    print("  Add them to the COUNTRY_NAMES dict in this script.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Step 4: generate C array
# ---------------------------------------------------------------------------
# Only include codes with > 0 stations AND a known display name
valid_codes = [c for c in unique_codes if rb_map.get(c, 0) > 0 and c in COUNTRY_NAMES]

# Sort by display name
valid_codes.sort(key=lambda c: COUNTRY_NAMES[c])

lines = [
    "// Generated by app/tools/gen_webradio_countries.py",
    "// Do not edit manually.",
    "//",
    "// Coverage: codes from app/src/settings/cities.h cross-checked against",
    "// radio-browser.info/json/countrycodes. Codes with zero stations omitted.",
    "",
    "#pragma once",
    "#include <Arduino.h>",
    "",
    "struct WebRadioCountry {",
    "    const char* code;         // ISO 3166-1 alpha-2",
    "    const char* displayName;  // Human-readable English name",
    "};",
    "",
    "static const WebRadioCountry kWebRadioCountries[] = {",
]

for code in valid_codes:
    name = COUNTRY_NAMES[code]
    lines.append(f'    {{"{code}", "{name}"}},')

lines += [
    "};",
    "",
    f"static const uint8_t kWebRadioCountryCount = {len(valid_codes)};",
    "",
]

output = "\n".join(lines)

# Print to stdout
print("\n--- Generated C header ---")
print(output)

# Save to app/gen/webradio_countries.h
OUT_H.parent.mkdir(parents=True, exist_ok=True)
OUT_H.write_text(output)
print(f"\n[Saved to {OUT_H}]", file=sys.stderr)

# Final summary
print(
    f"\nSummary: {len(unique_codes)} codes in cities.h; "
    f"{len(zero_station_codes)} with zero stations; "
    f"{len(valid_codes)} entries written to kWebRadioCountries[].",
    file=sys.stderr,
)
