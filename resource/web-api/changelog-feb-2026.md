# Web API Changelog — February 2026

> Source: https://developer.spotify.com/documentation/web-api/references/changes/february-2026
> Fetched: 2026-04-30

## Overview

Spotify's February 2026 update restructures API endpoints and removes numerous fields across content types. The changelog details endpoint removals, field deprecations, and behavioral changes applicable across all responses.

## Removed Endpoints

**Catalog & Discovery:**
- `POST /users/{user_id}/playlists` (Create Playlist for user) → use `POST /me/playlists`
- `GET /artists/{id}/top-tracks` (Get Artist's Top Tracks)
- `GET /markets` (Get Available Markets)
- `GET /browse/new-releases` (Get New Releases)
- `GET /albums` (Get Several Albums)
- `GET /artists` (Get Several Artists)
- `GET /audiobooks` (Get Several Audiobooks)
- `GET /browse/categories` (Get Several Browse Categories)
- `GET /chapters` (Get Several Chapters)
- `GET /episodes` (Get Several Episodes)
- `GET /shows` (Get Several Shows)
- `GET /tracks` (Get Several Tracks)
- `GET /browse/categories/{id}` (Get Single Browse Category)
- `GET /users/{id}/playlists` (Get User's Playlists)
- `GET /users/{id}` (Get User's Profile)

**Library Management (Consolidated):**
- `DELETE /me/albums` → use `DELETE /me/library`
- `DELETE /me/audiobooks` → use `DELETE /me/library`
- `DELETE /me/episodes` → use `DELETE /me/library`
- `DELETE /me/shows` → use `DELETE /me/library`
- `DELETE /me/tracks` → use `DELETE /me/library`
- `PUT /me/albums` → use `PUT /me/library`
- `PUT /me/audiobooks` → use `PUT /me/library`
- `PUT /me/episodes` → use `PUT /me/library`
- `PUT /me/shows` → use `PUT /me/library`
- `PUT /me/tracks` → use `PUT /me/library`

**Following/Saved Items Checks (Consolidated):**
- `GET /me/following/contains` → use `GET /me/library/contains`
- `GET /playlists/{id}/followers/contains` → use `GET /me/library/contains`
- `GET /me/albums/contains` → use `GET /me/library/contains`
- `GET /me/audiobooks/contains` → use `GET /me/library/contains`
- `GET /me/episodes/contains` → use `GET /me/library/contains`
- `GET /me/shows/contains` → use `GET /me/library/contains`
- `GET /me/tracks/contains` → use `GET /me/library/contains`

**Following Actions (Consolidated):**
- `PUT /me/following` (Follow Artists or Users) → use `PUT /me/library`
- `PUT /playlists/{id}/followers` (Follow Playlist) → use `PUT /me/library`
- `DELETE /me/following` (Unfollow Artists or Users) → use `DELETE /me/library`
- `DELETE /playlists/{id}/followers` (Unfollow Playlist) → use `DELETE /me/library`

**Playlist Items (Endpoint Restructuring):**
- `POST /playlists/{id}/tracks` → use `POST /playlists/{id}/items`
- `GET /playlists/{id}/tracks` → use `GET /playlists/{id}/items`
- `DELETE /playlists/{id}/tracks` → use `DELETE /playlists/{id}/items`
- `PUT /playlists/{playlist_id}/tracks` → use `PUT /playlists/{id}/items`

## Added Endpoints

- `DELETE /me/library` (Remove from Library)
- `PUT /me/library` (Save to Library)
- `GET /me/library/contains` (Check User's Saved Items)
- `POST /playlists/{id}/items` (Add Items to Playlist)
- `GET /playlists/{id}/items` (Get Playlist Items)
- `DELETE /playlists/{id}/items` (Remove Playlist Items)
- `PUT /playlists/{id}/items` (Update Playlist Items)

## Changed Endpoints

**Search for Item** (`GET /search`): The "maximum value for the `limit` parameter has been reduced from 50 to 10, and the default value has been changed from 20 to 5."

## Removed Fields

**Album:**
- `album_group`
- `available_markets`
- `external_ids` *(reverted in March 2026)*
- `label`
- `popularity`

**Artist:**
- `followers`
- `popularity`

**Audiobook:**
- `available_markets`
- `publisher`

**Chapter:**
- `available_markets`

**Show:**
- `available_markets`
- `publisher`

**Track:**
- `available_markets`
- `external_ids` *(reverted in March 2026)*
- `linked_from`
- `popularity`

**User:**
- `country`
- `email`
- `explicit_content`
- `followers`
- `product`

## Field Renamings

**Playlist:**
- `tracks` → `items`
- `tracks.tracks` → `items.items`
- `tracks.tracks.track` → `items.items.item`

Note: Playlists now return items only for user-owned playlists; other playlists provide metadata without contents.

## Available Endpoints

All player, personalization, search, and user profile endpoints remain operational with field changes applied.
