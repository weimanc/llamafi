# Spotify Web API — local snapshot

> Fetched: 2026-04-30
> Upstream: https://developer.spotify.com/documentation/web-api

Snapshot of Spotify Web API reference material relevant to this project. The OpenAPI specs are the authoritative machine-readable source; the markdown changelog files capture key policy notes that the OpenAPI doesn't fully convey.

---

## Files

| File | Source | Notes |
|------|--------|-------|
| `official-open-api.yaml` | https://developer.spotify.com/reference/web-api/open-api-schema.yaml | Official OpenAPI 3.0.3 spec, 7523 lines, 70 endpoint paths. |
| `sonallux-fixed-open-api.yml` | https://github.com/sonallux/spotify-web-api `fixed-spotify-open-api.yml` | Community-maintained spec with bugs fixed (mostly schema correctness). Use this for code-gen if generating clients. |
| `player-endpoints.yaml` | extracted slice of `official-open-api.yaml` (lines 3484–4080) | All `/me/player*` paths in one file for quick reference. The endpoints this project actually drives. |
| `changelog-feb-2026.md` | https://developer.spotify.com/documentation/web-api/references/changes/february-2026 | Endpoints removed, fields removed, library API consolidated under `/me/library`. |
| `changelog-feb-2026-migration-guide.md` | https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide | Development Mode vs Extended Quota Mode tier policy, per-endpoint migration patterns. |
| `changelog-mar-2026.md` | https://developer.spotify.com/documentation/web-api/references/changes/march-2026 | Reverts: `external_ids` for Album and Track restored. |

---

## Project-relevant findings (cross-ref `docs/quality/lessons_learned.md`)

### Why the M1 spike got HTTP 403 on `audio-features` / `audio-analysis` (LL-009)

Both endpoints are explicitly **`deprecated: true`** in the official spec and tagged with `x-spotify-policy-list: MachineLearning`. Quote from `official-open-api.yaml` lines 2902 onward:

```yaml
/audio-features:
    get:
      deprecated: true
      tags:
        - Tracks
      operationId: get-several-audio-features
      x-spotify-policy-list:
        - $ref: '#/components/x-spotify-policy/policies/MachineLearning'
```

Same for `/audio-features/{id}` (line 2936) and `/audio-analysis/{id}` (line 2970).

The MachineLearning policy is the gate. Apps in **Development Mode** (which is what our `db2ff394...` app is, per the Feb 2026 tier split) cannot call these endpoints — they return 403. Apps in **Extended Quota Mode** retain access. Extended Quota Mode requires manual approval from Spotify; uncertain timeline.

This invalidates ADR-002 ("VU meter sourced from Spotify `audio-analysis`, beat-synchronised") for our project tier. Tracked as TASK-010.

### Why most non-GET requests fail at TLS-send (LL-008)

Not a Spotify issue. The Spotify endpoints we drive are all present in the spec (`/me/player/play`, `/me/player/pause`, `/me/player/next`, `/me/player/previous`, `/me/player/seek`, `/me/player/volume`, `/me/player/shuffle`, `/me/player/repeat`). Listed in `player-endpoints.yaml`. The failure is in `WiFiClientSecure` reuse on Arduino-ESP32 2.0.17. Tracked as TASK-009.

### Development Mode app limits we may hit

From `changelog-feb-2026-migration-guide.md`:

- **App owner must have an active Spotify Premium subscription.** "If the owner's Premium subscription lapses, the app will stop working." Important for hosting strategy if multiple users.
- **1 Client ID per developer**, **5 users per app** for Dev Mode. Existing apps grandfathered. We have 1 Client ID and (presumably) 1 user, so we're fine.

### Field changes that may bite the existing firmware

The `SpotifyArduino` library parses many fields. February 2026 removed several. Track-level **fields the lib reads that may now be missing or have changed**:

- `popularity` — **removed** (Track). Lib may parse it; will get 0 / null.
- `available_markets` — **removed** (Track). Lib uses it via `?market=...` param on requests; the fallback path is unaffected, but if the lib reads `available_markets` from response payloads it's gone.
- `external_ids` — removed Feb 2026, **reverted Mar 2026**. Currently available again.
- `linked_from` — **removed** (Track). Track relinking field; library may use it for region-restricted track follow-through.

These are silent breakage candidates: the library may behave fine but log JSON-parse warnings or compute incorrect derived values.

---

## Endpoints this project uses (current and planned)

From `player-endpoints.yaml`:

| Path | Method | Used by | Status this project |
|------|--------|---------|---------------------|
| `/me/player/currently-playing` | GET | `poll-001` | Working (verified 2026-04-29) |
| `/me/player` | GET | (planned, may help with device targeting) | Not used yet |
| `/me/player/devices` | GET | (potentially TASK-009 — for device-transfer fallback) | Not used yet |
| `/me/player/play` | PUT | M5 / api-001 spike `p` | **Failing** (TASK-009 TLS reuse) |
| `/me/player/pause` | PUT | M5 / api-001 spike `P` | **Failing** (TASK-009) |
| `/me/player/next` | POST | M5 / api-001 spike `>` | **Failing** (TASK-009) |
| `/me/player/previous` | POST | M5 / api-001 spike `<` | **Failing** (TASK-009) |
| `/me/player/seek` | PUT | M5 / api-001 spike `s` `S` | **Failing** (TASK-009) |
| `/me/player/volume` | PUT | M5 / api-001 spike `+` `-` `v` | **Failing** (TASK-009) |
| `/me/player/shuffle` | PUT | M5 / api-001 spike `h` `H` | **Failing** (TASK-009) |
| `/me/player/repeat` | PUT | M5 / api-001 spike `r` `R` `o` | **Failing** (TASK-009) |
| `/audio-features/{id}` | GET | M6 / api-001 spike `f` | **403 Forbidden** (deprecated, TASK-010) |
| `/audio-analysis/{id}` | GET | M6 / api-001 spike `a` `A` | **403 Forbidden** (deprecated, TASK-010) |
| `/me/player/queue` | GET | (potential future — show next-up) | Not used yet |

---

## Refresh procedure

When Spotify ships a new changelog or this snapshot ages out:

```sh
cd resource/web-api
curl -sSL -o official-open-api.yaml https://developer.spotify.com/reference/web-api/open-api-schema.yaml
curl -sSL -o sonallux-fixed-open-api.yml https://raw.githubusercontent.com/sonallux/spotify-web-api/main/fixed-spotify-open-api.yml
# Then re-fetch any changelog/migration markdown pages that have changed.
# Update player-endpoints.yaml by re-extracting `/me/player*` from the official spec.
```
