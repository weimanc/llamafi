# February 2026 Web API Dev Mode Changes — Migration Guide

> Source: https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide
> Fetched: 2026-04-30

## Overview

Spotify's February 2026 update introduces significant changes for Development Mode applications. This guide addresses migration requirements for affected developers.

## Affected Applications

**Extended Quota Mode:** "No migration required. Apps in extended quota mode are not affected by any of the changes described in this guide — all existing endpoints, fields, and behaviors remain unchanged."

**Development Mode:** Requires full migration per this guide.

## Timeline

- **February 11, 2026:** New Development Mode apps created with new restrictions
- **March 9, 2026:** Existing Development Mode apps migrated to new restrictions

## Account and App Changes

### Premium Requirement

"All Development Mode apps require the app owner to have an active Spotify Premium subscription. If the owner's Premium subscription lapses, the app will stop working."

### App Limits

| Requirement | Limit |
|---|---|
| Client IDs per developer | 1 |
| Users per app | 5 |

"Existing apps are grandfathered: If you already have multiple Client IDs or more than 5 users, you will retain them."

## Endpoint Modifications

### Library Management Consolidation

**Saving/Following — Before:**
- `PUT /me/tracks`
- `PUT /me/albums`
- `PUT /me/episodes`
- `PUT /me/shows`
- `PUT /me/audiobooks`
- `PUT /me/following`
- `PUT /playlists/{id}/followers`

**After:**
- `PUT /me/library`

**Removing/Unfollowing — Before:**
- `DELETE /me/tracks`
- `DELETE /me/albums`
- `DELETE /me/episodes`
- `DELETE /me/shows`
- `DELETE /me/audiobooks`
- `DELETE /me/following`
- `DELETE /playlists/{id}/followers`

**After:**
- `DELETE /me/library`

**Contains Checks — Before:**
- `GET /me/tracks/contains`
- `GET /me/albums/contains`
- `GET /me/episodes/contains`
- `GET /me/shows/contains`
- `GET /me/audiobooks/contains`
- `GET /me/following/contains`
- `GET /playlists/{id}/followers/contains`

**After:**
- `GET /me/library/contains`

### Playlist Endpoint Renames

| Removed | Replacement |
|---|---|
| `POST /playlists/{id}/tracks` | `POST /playlists/{id}/items` |
| `GET /playlists/{id}/tracks` | `GET /playlists/{id}/items` |
| `DELETE /playlists/{id}/tracks` | `DELETE /playlists/{id}/items` |
| `PUT /playlists/{playlist_id}/tracks` | `PUT /playlists/{id}/items` |

### Batch/Bulk Fetch Endpoints Removed

| Removed | Alternative |
|---|---|
| `GET /tracks` | `GET /tracks/{id}` (individual requests) |
| `GET /albums` | `GET /albums/{id}` |
| `GET /artists` | `GET /artists/{id}` |
| `GET /episodes` | `GET /episodes/{id}` |
| `GET /shows` | `GET /shows/{id}` |
| `GET /audiobooks` | `GET /audiobooks/{id}` |
| `GET /chapters` | `GET /chapters/{id}` |

### Browse and Artist Endpoints Removed

- `GET /browse/new-releases`
- `GET /browse/categories`
- `GET /browse/categories/{id}`
- `GET /artists/{id}/top-tracks`

### Other User Data Endpoints Removed

| Removed | Notes |
|---|---|
| `GET /users/{id}` | Use `GET /me` for current user |
| `GET /users/{id}/playlists` | Use `GET /me/playlists` for current user |
| `POST /users/{user_id}/playlists` | Use `POST /me/playlists` |
| `GET /markets` | No replacement |

### Search Endpoint Changes

| Parameter | Before | After |
|---|---|---|
| `limit` maximum | 50 | 10 |
| `limit` default | 20 | 5 |

## Field Changes

### Removed Fields

**Track:** `available_markets`, `external_ids` *(reverted Mar 2026)*, `linked_from`, `popularity`

**Album:** `album_group`, `available_markets`, `external_ids` *(reverted Mar 2026)*, `label`, `popularity`

**Artist:** `followers`, `popularity`

**User (`GET /me`):** `country`, `email`, `explicit_content`, `followers`, `product`

**Show:** `available_markets`, `publisher`

**Audiobook/Chapter:** `available_markets`, `publisher` (audiobook only)

### Renamed Fields

**Playlist:**
- `tracks` → `items`
- `tracks.tracks` → `items.items`
- `tracks.tracks.track` → `items.items.item`

"Playlist contents (items) are only returned for playlists the user owns or collaborates on."

## Migration Patterns

### Library Save Calls

Before:
```js
await spotify.put('/me/tracks', { ids: ['trackId1', 'trackId2'] });
await spotify.put('/me/albums', { ids: ['albumId1'] });
await spotify.put('/me/following', { ids: ['artistId1'], type: 'artist' });
```

After:
```js
await spotify.put('/me/library', {
  uris: [
    'spotify:track:trackId1',
    'spotify:track:trackId2',
    'spotify:album:albumId1',
    'spotify:artist:artistId1'
  ]
});
```

### Handling Removed Fields

"Consider alternative sorting criteria or remove this feature" when popularity field is no longer available.

### Playlist Field Rename

Before:
```js
const trackCount = playlist.tracks.total;
const firstTrack = playlist.tracks.items[0].track;
```

After:
```js
const trackCount = playlist.items?.total ?? 0;
const firstTrack = playlist.items?.items?.[0]?.item;
if (!playlist.items) {
  console.log('Track details not available for this playlist');
}
```
