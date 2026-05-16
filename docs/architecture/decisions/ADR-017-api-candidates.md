# M-LIST — Spotify API Candidate Analysis

> Companion to ADR-017. Documents all three data-source candidates evaluated for the M-LIST playlist panel.
> Decision: **Tier 1 (queue endpoint) chosen first.** Tiers 2 and 3 deferred.

---

## Candidate 1 — `GET /me/player/queue` ✅ CHOSEN (Tier 1)

**Endpoint:** `GET /v1/me/player/queue`

**Scopes required:** `user-read-currently-playing`, `user-read-playback-state`

**Scope gap:** current token has `user-read-playback-state user-modify-playback-state`.  
`user-read-currently-playing` may need to be added — verify at DUT time (Spotify sometimes accepts `user-read-playback-state` as a superset for queue; if 403, regenerate token).

**Response shape:**
```json
{
  "currently_playing": {
    "name": "Track Name",
    "uri": "spotify:track:<id>",
    "artists": [{ "name": "Artist Name" }],
    "duration_ms": 210000,
    "type": "track"
  },
  "queue": [
    { "name": "...", "uri": "spotify:track:...", "artists": [{"name":"..."}] },
    ...
  ]
}
```

`queue[]` contains up to 20 items. Items can be `TrackObject` or `EpisodeObject` — filter on `type == "track"` to skip podcast episodes.

**Fields used:** `name`, `artists[0].name`, `uri` per item. Everything else ignored.

**Parse strategy:** ArduinoJson streaming filter doc — extract only the above three fields for the first 7 items. Bounds heap allocation.

**Poll cadence:** On track-change detection + 60 s keepalive (see ADR-017 §5).

**Strengths:**
- Reflects the **actual playback order** including manually-queued overrides. User may have queued tracks that override the source playlist — the queue endpoint shows those; a playlist-items fetch would not.
- Single HTTP call — no chaining.
- No pagination.
- Response is small if filtered; even unfiltered is manageable (20 track objects ≈ 5-10 KB JSON).

**Weaknesses:**
- Does not tell the user *where* in the source playlist they are (no playlist position/index).
- Queue can be empty (user playing a single track, no context) — must gracefully handle `queue: []`.
- Episodes in queue return `type: "episode"` — need to filter or display differently.

**Breaking changes (Feb/Mar 2026):** None. Queue endpoint schema unchanged.

---

## Candidate 2 — Currently-Playing Context → Playlist Items (Tier 2, deferred)

**Endpoints:**
1. `GET /v1/me/player/currently-playing` — already polled; extract `context.uri` (the source playlist/album/artist URI)
2. `GET /v1/playlists/{playlist_id}/items?fields=items(item(name,uri,duration_ms),added_at)&limit=20&offset=<current_position>` — fetch a page of items centred on the current track position

**Scopes required:** `user-read-currently-playing`, `playlist-read-private`

**Why deferred:**
- Requires two sequential HTTP calls per update cycle.
- Playlist position (`offset`) is not directly in the currently-playing response — must be inferred by matching `item.uri` against the fetched page, which can fail if the track appears multiple times in the playlist.
- `context` can be `null` (playing from a search result, ad, or no context) — fallback to Candidate 1 or show nothing.
- The fetched list shows the *static* playlist order; it will be wrong whenever the user has manually queued tracks that override it.
- Feb 2026 field rename: `tracks.tracks.track` → `items.items.item`. Must use the new field path; `fields=` filter must reference the new names.

**Strengths over Candidate 1:**
- Shows position within the full playlist — user sees "track 5 of 42".
- Allows backwards scrolling (previous tracks).
- Richer context: playlist name, added-by, added-at.

**When to revisit:** After Tier 1 ships and user wants a "full playlist browser" experience rather than a simple "up next" strip.

**Response shape (with fields filter):**
```json
{
  "items": [
    {
      "item": {
        "name": "Track Name",
        "uri": "spotify:track:<id>",
        "duration_ms": 210000
      },
      "added_at": "2024-01-15T12:00:00Z"
    }
  ],
  "next": "https://api.spotify.com/v1/playlists/.../items?offset=20&limit=20",
  "total": 42
}
```

---

## Candidate 3 — Playlist Browser: `GET /me/playlists` (Tier 3, out of scope)

**Endpoints:**
1. `GET /v1/me/playlists?limit=20` — user's playlists (paginated)
2. `GET /v1/playlists/{id}/items` — items in a selected playlist

**Scopes required:** `playlist-read-private`

**Why out of scope:**
- Requires a selection UI — user taps a playlist from a list, then sees its tracks. No design exists for this interaction.
- 7 rows at Font 2 is insufficient for a playlist browser; would need a scrolling gesture model that doesn't exist yet in the touch layer.
- Two-call chain with pagination on both legs.
- Only returns playlists **owned by the user or collaborative** — playlists followed from other users return metadata but `items` field is `null` (Spotify restriction).
- No clear trigger for when to update (which playlist is "active" isn't exposed by this endpoint).

**Response shape (playlists list):**
```json
{
  "items": [
    {
      "name": "My Playlist",
      "id": "37i9dQ...",
      "uri": "spotify:playlist:37i9dQ...",
      "tracks": { "total": 42 }
    }
  ],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

**When to revisit:** If M-LIST evolves into a full playlist-management screen. Requires a new UX design and touch interaction model well beyond what the current 7-row strip can support.

---

## Comparison Table

| Property | Candidate 1 — Queue | Candidate 2 — Playlist Items | Candidate 3 — Playlist Browser |
|---|---|---|---|
| HTTP calls per update | 1 | 2 (sequential) | 2+ (paginated) |
| Reflects manual queue overrides | **Yes** | No | No |
| Shows position in source playlist | No | **Yes** | Yes |
| Handles null context | Yes (queue always exists) | No (must fallback) | No |
| Scope gap | Possibly `user-read-currently-playing` | `playlist-read-private` | `playlist-read-private` |
| Dev complexity | Low | Medium | High |
| Suitable for 7-row strip | **Yes** | Yes | No (needs scroll UI) |
| Breaking changes (Feb 2026) | None | Field rename: `track`→`item` | Field rename: `track`→`item` |
| Decision | **Tier 1 — implement** | Tier 2 — deferred | Tier 3 — out of scope |

---

## Notes on Feb 2026 Breaking Changes

Spotify renamed playlist track fields in Feb 2026 (affects Candidates 2 and 3 only):

| Old field path | New field path |
|---|---|
| `PlaylistTrackObject.track` | `PlaylistTrackObject.item` |
| `PlaylistObject.tracks` | `PlaylistObject.items` |
| `GET .../items` response `tracks` | `GET .../items` response `items` |

The `SpotifyArduino` library's `getPlaylistTracks` implementation (if it exists) likely uses the old field names. Must patch before use. Not relevant for Tier 1 (queue endpoint unaffected).
