# Design — M-PR-LOCATIONS Phase 0: Nominatim geocode probe + cert evidence

> Owner: Developer (TASK-315)
> Status: **done** — probe run 2026-07-14, all checks landed on expected outcome
> Date: 2026-07-14
> Parent: [M-PR-LOCATIONS-location-presets.md](../M-PR-LOCATIONS-location-presets.md)
> ("Geocode provider decision", "Geocode fetch — dataTask one-shot", "Geocode
> query — derisk on host, phase-0 style")
> Pattern: [M-PLANERADAR/phase0-api-probe.md](../M-PLANERADAR/phase0-api-probe.md)
> Closes: QM-2 evidentiary bar (cert claim), VE-PRL-12 (roster entry), the
> "full postcode" rule check, and the provisional ~1 KB parse-buffer figure

## Context / pain points

The 2026-07-13 provider-decision probes (Nominatim vs open-meteo geocoding vs
zippopotam.us) that picked Nominatim + "full postcode" as the input rule were
ad-hoc — run once, by hand, not committed as reproducible evidence. Three
downstream facts the parent design currently states as probed-but-unevidenced
need a committed, repeatable source:

1. The "full postcode" rule (works for full postcodes, not truncated ones) —
   claimed for NL/UK, not yet checked for DE.
2. The parse-buffer size (`~1 KB StaticJsonDocument`, explicitly flagged
   "provisional... sized by the phase-0 probe's measured responses before
   freezing", BP-001).
3. The TLS chain claim ("verified OK against the exact `OPEN_METEO_ROOT_CA`
   PEM already in `dataTaskCerts.h`") — QM-2 requires this land via the same
   strict, offline, single-root method as `run/check-datatask-certs`, not a
   read of the issuer string.

## Tool

`app/tools/geocode_probe.py` — stdlib + `requests` (venv `~/proj/esp/venv`,
falls back to plain `python3` since only stdlib + `requests` are used, no
project-specific deps). Four phases, always run in this order with ≥1.1 s
between every Nominatim HTTP request (Nominatim usage policy hard cap):

1. **Query matrix** — 7 structured `/search` queries (`format=jsonv2&limit=1&
   addressdetails=0`), custom UA `esp32-cyd-multiapp/1.0 (github.com/weimanc;
   dev probe)`, manually percent-encoded query string (mirrors the minimal
   encoder the firmware fetcher will add — deliberately not `requests`'
   `params=` dict, which `+`-encodes spaces instead of `%20`).
2. **UA policy** — one request with `requests`' own default UA
   (`python-requests/x.y.z`, not a hand-picked worst case), expecting a 403.
3. **HTTP/1.0 compat** — one request forced onto the wire as
   `GET ... HTTP/1.0`, mirroring `openHttps()`'s unconditional
   `useHTTP10(true)`.
4. **Cert chain** — the exact `run/check-datatask-certs` method: extract
   `OPEN_METEO_ROOT_CA`'s PEM out of `app/src/dataTaskCerts.h` by regex (never
   hand-copied), `openssl s_client -CAfile <that PEM only> -verify_return_error`
   against `nominatim.openstreetmap.org:443`, plus a second `-showcerts` call
   to record the served chain's subject/issuer lines (kept separate from the
   strict-verify call so `-showcerts`'s looser default trust store never
   contaminates the strict result).

Total live requests: 7 (matrix) + 1 (UA) + 1 (HTTP/1.0) = **9** to Nominatim's
`/search` endpoint, all ≥1.1 s apart, under the ~12 budget; the cert probe is
two raw TLS handshakes via `openssl s_client`, not calls to the rate-limited
search API. `--report` emits a markdown summary block (used verbatim for the
tables below). Exit code 0 iff every check lands on its expected outcome.

Run: `~/proj/esp/venv/bin/python3 app/tools/geocode_probe.py --report`

## A bug the script caught in itself

First run: the HTTP/1.0 check got a bare `421`/`403` with no body from
`nominatim.openstreetmap.org` and (in isolation, against `example.com`) a
`403` with no `Host` header on the wire at all. Root cause: Python's
`http.client.HTTPConnection.putrequest()` only auto-adds a `Host` header when
`_http_vsn == 11` — forcing `_http_vsn = 10` for the HTTP/1.0 test silently
drops `Host` unless it's supplied explicitly. Fixed by setting `Host`
explicitly in the request headers (which is also what ESP32 `HTTPClient` does
regardless of HTTP version, so this is the representative test, not a
workaround). Re-verified against `example.com` first (200 with `Host` header
present vs 403 without) before re-running against Nominatim. Left as a code
comment in `geocode_probe.py::run_http10_check()` for the next person who
copies this pattern.

## Results (run 2026-07-14, single clean pass, exit 0)

### Query matrix

| Query | HTTP | Bytes | lat/lon type | Result | Expected | Verdict |
|---|---|---|---|---|---|---|
| NL full (`2513AA`) | 200 | 435 | `lat` str `'52.0795389'` | match — `2513 AA, Centrum, Den Haag, Zuid-Holland, Nederland` | match | PASS |
| NL PC4 (`2513`) | 200 | 2 (`[]`) | — | no match | no match | PASS |
| UK full (`SW1A 1AA`) | 200 | 459 | `lat` str `'51.5013375'` | match — `SW1A 1AA, City of Westminster, Greater London, England, United Kingdom` | match | PASS |
| UK full (`B33 8TH`) | 200 | 446 | `lat` str `'52.4751318'` | match — `B33 8TH, Birmingham, West Midlands, England, United Kingdom` | match | PASS |
| UK outward (`M1`) | 200 | 2 (`[]`) | — | no match | no match | PASS |
| DE full (`10115`, Berlin) | 200 | 435 | `lat` str `'52.5321914'` | match — `10115, Mitte, Berlin, Deutschland` | match | PASS |
| garbage (`country=XX`, `postalcode=NOTAPOSTCODE1`) | 200 | 2 (`[]`) | — | no match | no match | PASS |

**7/7 as expected.** `lat`/`lon` confirmed JSON *strings* in every match, as
the parent design states. `country=XX` + garbage postcode returns `HTTP 200`
with an empty array (`[]`), not an error status — the fetcher's "no match"
path (`-96 GEOCODE_NO_MATCH`) is driven by an **empty array with 200**, not by
HTTP status.

**URL encoding:** both space-containing postcodes (`SW1A 1AA`, `B33 8TH`)
were sent with the space percent-encoded (`%20`) via the manual encoder in
`build_url()`; the script asserts this on every request (`assert "%20" in
url` when the postcode contains a space) — it would have failed loudly, not
silently, had the encoding regressed.

### UA policy

```
PASS  UA='python-requests/2.25.1' -> 403 as expected (policy enforced)
```

Default UA (unmodified `requests` library string, not a custom "bad" UA) gets
a clean `403`. The chosen project UA string
(`esp32-cyd-multiapp/1.0 (github.com/weimanc; dev probe)`) was accepted on
every one of the 7 matrix requests above — it is known-good before any device
code exists.

### HTTP/1.0 compat

```
PASS  status=200 bytes=435 transfer-encoding=None
```

`GET /search?... HTTP/1.0` with an explicit `Host` header returns a normal
`200` with a complete, non-chunked body (`Transfer-Encoding` absent, as
expected for HTTP/1.0). No redirect to a different host was observed (which
would have dodged the cert pin). `openHttps()`'s `useHTTP10(true)` is safe
against this host, **provided the firmware sends `Host` explicitly** —
`HTTPClient` already does this unconditionally, so no firmware change is
implied; this was purely a probe-script gotcha (see above), not a Nominatim
finding.

### Cert chain verify

Strict, offline, single-root verify — exact method of `run/check-datatask-certs`:

```
PASS  ok
```

(`Verify return code: 0 (ok)`, verified against `OPEN_METEO_ROOT_CA`'s PEM
extracted live from `app/src/dataTaskCerts.h`, not a copy.)

Served chain (`-showcerts`, separate connection, subject/issuer only):

```
 0 s:CN=nominatim.openstreetmap.org
   i:C=US, O=Let's Encrypt, CN=YR1
   a:PKEY: RSA, 2048 (bit); sigalg: sha256WithRSAEncryption
   v:NotBefore: Jun  9 06:40:07 2026 GMT; NotAfter: Sep  7 06:40:06 2026 GMT
 1 s:C=US, O=Let's Encrypt, CN=YR1
   i:C=US, O=ISRG, CN=Root YR
   a:PKEY: RSA, 2048 (bit); sigalg: sha256WithRSAEncryption
   v:NotBefore: Sep  3 00:00:00 2025 GMT; NotAfter: Sep  2 23:59:59 2028 GMT
 2 s:C=US, O=ISRG, CN=Root YR
   i:C=US, O=Internet Security Research Group, CN=ISRG Root X1
   a:PKEY: RSA, 4096 (bit); sigalg: sha256WithRSAEncryption
   v:NotBefore: May 13 00:00:00 2026 GMT; NotAfter: Sep  2 23:59:59 2032 GMT
```

Confirms the parent design's claimed chain shape exactly: leaf ← `YR1`
(Let's Encrypt intermediate) ← `ISRG Root YR` ← (cross-signed by) `ISRG Root
X1` — cert index 2's subject is `O=ISRG, CN=Root YR` and its issuer is
`O=Internet Security Research Group, CN=ISRG Root X1`, i.e. the served chain
*is* the cross-sign path, and the strict verify against `OPEN_METEO_ROOT_CA`
(the X1 PEM) succeeds by walking that cross-sign link. The parent design's
MUST-comment risk (if OSM ever drops `Root YR` from the served chain,
verification against X1 alone breaks) is a real, live dependency, evidenced
here — not removed by this probe, just now measured instead of assumed.

### 429 / Retry-After

None observed. All 9 live requests across the single clean run returned 200
or 403 (UA-policy case). No `Retry-After` header seen. (An earlier debugging
session before the script existed made ~2 extra ad-hoc requests plus one
full buggy dry-run of the script while chasing the HTTP/1.0 `Host`-header
bug — none triggered a 429 either; Nominatim's policy targets sustained
unthrottled scraping, not a spaced-out afternoon of manual probing.)

## Conclusions

**(a) "Full postcode" rule — confirmed for NL, UK, and DE.** Full postcodes
match street-level in all three countries tested; truncated forms (NL's
4-digit PC4, UK's outward-only code) return `[]` in both cases tested. The
rule generalizes beyond the NL/UK pair the original provider-decision table
covered — DE was the actual new information this run added.

**(b) Parse-buffer sizing.** Measured max response body: **459 bytes**
(`SW1A 1AA`, `limit=1&addressdetails=0`), well under the design's provisional
`~1 KB StaticJsonDocument`. Per BP-001 (measure, don't guess) this freezes
the figure: **keep the ~1 KB buffer** (do not shrink it to fit the measured
459 B) — ArduinoJson's `StaticJsonDocument` overhead runs well above 1:1
against raw bytes (per-token/string overhead, not just payload bytes), 459 B
of matches is already close to the single-result ceiling (one `address`-free
object with `place_id, licence, osm_type, osm_id, lat, lon, category, type,
place_rank, importance, addresstype, name, display_name, boundingbox[4]`),
and the margin over `~1 KB` buys robustness against a longer `display_name`
(a long UK/DE street+city+county+country string) without a second
measure-and-freeze cycle. The buffer is now evidence-backed, not guessed.

**(c) Cert claim — now evidenced, not asserted.** The parent design's "TLS:
... Verified OK against the exact `OPEN_METEO_ROOT_CA` PEM" line rested on
2026-07-13 ad-hoc probes; this run reproduces that result via the exact
`run/check-datatask-certs` method (see above) with output committed to this
file. QM-2's evidentiary bar is met for the geocode probe's part; the
remaining condition ("provisional until [the roster entry] lands") is
addressed below.

**(d) 429 / rate-limit behaviour.** None observed in any run today. No
evidence either way on `Retry-After` semantics — the editor's Retry wording
should not promise a specific backoff interval until a real 429 is observed
(not manufactured here — deliberately did not attempt a burst probe against
a production geocoding service the way `pr_adsb_probe.py --limit-probe` did
for adsb.fi; Nominatim's policy is stricter and burst-testing it isn't worth
the goodwill cost for a service used once per user action).

## `run/check-datatask-certs` roster edit — option chosen

**Chose the guard (Option A: add the roster row now, gated by a
`PENDING_CERTS` dict that reports a missing `NOMINATIM_ROOT_CA` as a labelled
`PENDING` line — excluded from the pass/fail count — rather than an `ERROR`
that would fail every future `run/check-datatask-certs` invocation until
TASK-320 lands)**, because leaving the roster untouched would silently drop
Nominatim from the standing cert-preflight gate for the entire M-PR-LOCATIONS
window between now and TASK-320, which is exactly the kind of gap
`run/check-datatask-certs` exists to prevent (VE-PRL-12 asks for the roster
entry in *this* task, not a follow-up).

Verified locally:

```
$ ./run/check-datatask-certs
...
PENDING nominatim.openstreetmap.org      (NOMINATIM_ROOT_CA) — NOMINATIM_ROOT_CA not defined yet — lands with TASK-320
...
PASS  all 8 verifiable endpoint(s) verify cleanly against their pinned root CA. (1 PENDING, tracked separately — see comment)
```

(Two unrelated `nl1`/`at1.api.radio-browser.info` `ERROR` rows were also
observed on this run — pre-existing, documented mirror flakiness, see
`MEMORY.md` "TASK-284 station fetch — intermittent"; not touched by or
related to this change, and reproduced identically before and after the
`NOMINATIM_ROOT_CA` edit.) When TASK-320 adds the `NOMINATIM_ROOT_CA` alias
to `dataTaskCerts.h`, the `PENDING` row becomes a real `PASS`/`FAIL` verify
automatically — no further edit to `run/check-datatask-certs` needed, the
`PENDING_CERTS` entry simply stops matching (`certs.get(cert_name)` finds the
alias, `strict_verify()` runs).

## Exit criteria

1. Query matrix re-run (NL full/PC4, UK full×2/outward, DE, garbage) — done,
   7/7 expected. ✅
2. URL encoding of space postcodes verified (asserted in-script, not just
   eyeballed). ✅
3. Response contract (`lat`/`lon` strings, `[]` on no match) confirmed;
   max size measured (459 B) and buffer recommendation frozen (keep ~1 KB). ✅
4. HTTP/1.0 compat confirmed sane (200, non-chunked, no redirect) — with a
   caught-and-documented probe-script bug along the way. ✅
5. UA policy confirmed both ways (default UA 403, project UA accepted). ✅
6. Rate behaviour recorded: no 429/Retry-After observed. ✅
7. Cert chain strict-verified via the `check-datatask-certs` method, output
   committed verbatim above; chain subjects/issuers show the `ISRG Root YR`
   cross-sign. ✅
8. `nominatim.openstreetmap.org` added to `run/check-datatask-certs`
   ENDPOINTS, with a guard so the still-missing `NOMINATIM_ROOT_CA` alias
   reports `PENDING` (informational) instead of failing the gate. ✅
