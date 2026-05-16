# Design — M7 Open Questions

> Owner: Architect / PM
> Status: resolved (2026-05-16)
> Deps: M6 and all prior milestones

All four open questions from `architecture.md` are resolved below. Each either references an ADR or is closed with written rationale.

---

## 1. TLS root CA strategy (pin vs trust-store)

**Closed by ADR-019** (2026-05-16).

Keep the two hardcoded DigiCert Global Root CA G2 PEM strings in
`lib/SpotifyArduino/src/SpotifyArduinoCert.h`. Both `spotify_server_cert`
(used for `api.spotify.com` + `accounts.spotify.com`) and
`spotify_image_server_cert` (album art CDN) resolve to this root, which
expires 2038-01-15. No firmware change required.

Maintenance trigger: if Spotify rotates to a new root CA, update the PEM
in the vendored cert file and reflash.

---

## 2. Seek-bar drag visual treatment

**Resolved here** — no ADR warranted (implementation pattern, not direction change).

**Decision: snap to finger position immediately during drag; freeze interpolation
until touch release; fire the seek API call on release.**

Rationale: this is the only treatment that gives the user honest real-time
feedback about where they are setting the position. Freezing the interpolated
bar mid-drag and firing only on release (the ADR-004 debounce decision) is
already settled. The visual question is whether the bar follows the finger
during drag or stays frozen at the pre-drag position — it must follow the
finger (Option A), otherwise the user has no drag feedback at all.

Implementation:

- In `touchScreen.h` hit-test for the posbar region, track `isDragging` +
  `dragPositionMs` (computed from finger X mapped onto `[0, durationMs]`).
- While dragging: `spotifyDisplay::setSeekBarPosition(dragPositionMs)` instead
  of the interpolated value; do not advance interpolation.
- On touch release: enqueue `ACT_SEEK` with `dragPositionMs`; clear `isDragging`
  and resume interpolation from the seek point.
- The optimistic position anchor (`songStartMillis`) is updated to reflect
  the seek so interpolation picks up from the right place before the poll
  reconciles.

---

## 3. Speculative one-shot poll after intent

**Closed by ADR-020** (2026-05-16).

Implement a 750 ms deferred poll after `ACT_NEXT` and `ACT_PREV` only.
Cuts track-change reconciliation latency from up to 5 s to ~1–1.5 s.
No speculative poll for play/pause/volume/shuffle/repeat (optimistic UI
sufficient) or seek (position interpolation sufficient).

---

## 4. `audio-analysis` SPIFFS-mirror vs RAM-only

**Already closed by ADR-009** (2026-05-07, supersedes ADR-002).

M6 shipped with a synthetic VU envelope (ADR-009 option e) — no
`audio-analysis` fetch occurs. This question is moot unless Extended Quota
Mode is granted in the future, at which point it becomes a new open question
scoped to the audio-analysis integration milestone.

---

## Implementation tracking

| Item | Disposition | Where |
|---|---|---|
| TLS root CA | Keep current — no impl | ADR-019 |
| Seek-drag visual | Snap to finger, fire on release | Above §2 — impl in `touchScreen.h` |
| Speculative poll | Implement for next/prev | ADR-020 — sub-task under M7 or M-PERF |
| audio-analysis cache | Already closed (synthetic VU) | ADR-009 |

Seek-drag and speculative poll are the two remaining implementation items.
Both are small (~20–40 LOC each). Seek-drag is DUT-testable only; speculative
poll can be logic-reviewed on-host.
