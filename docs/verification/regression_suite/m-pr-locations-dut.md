# M-PR-LOCATIONS DUT VE Suite

> Owner: Verification Engineer
> Milestone: M-PR-LOCATIONS (TASK-324, parent design doc verification sketch)
> Status: **closed 2026-07-16 — T_PRL_01a/02/03/04/05/06/09/10 PASS; T_PRL_01b/07/11 explicitly deferred (not gaps — see notes); T_PRL_08 partially provable by design (see notes)**
> DUT: ESP32-2432S028R CYD2USB, firmware `cyd2usb_winamp_debug`
> Design: `docs/architecture/designs/M-PR-LOCATIONS-location-presets.md` §Verification sketch

---

## VE design notes (read before running)

- **This suite spans five prior tasks' close-out smokes plus one new run.**
  T_PRL_01a/04/06/10 were already DUT-proven at TASK-319/320/321/322's own
  close-out (each landed with an "intermediate DUT smoke PASS" gate) — this
  suite cites that evidence rather than re-running identical assertions
  (LL-102 guard: cited *by name*, not silently absorbed). T_PRL_02/03/05/08/09
  are new — `app/tools/prloc_ve_smoke.py`, run 2026-07-16, 22/22 PASS.
- **`g_shellBusy` silently drops a second interactive tap while a fetch is
  pending — by design, not a bug, but a testability trap.** First attempt at
  T_PRL_09 (rapid double-switch) used two back-to-back `tap` injections on
  the radar strip; it always landed on the *first* tapped slot, never the
  second. Root cause: slot-0's tap sets `hasPendingAsync()`=true (a fetch is
  now in flight), `cmdTap` sets `g_shellBusy=true` after dispatching it, and
  `cmdTap`'s very first check silently drops (`skipped:true`) any tap that
  arrives while `g_shellBusy` is set — the second tap never reaches
  `PlaneRadarApp::handleInput()` at all. This is correct product behaviour
  (the shell won't let interactive touch race a fetch) but it means the
  epoch-race leg has to go through `set prloc active <i>` (main.cpp's serial
  path, which calls `_setActiveLoc()` directly with no `g_shellBusy` gate)
  to actually exercise back-to-back switches. Fixed in the committed test;
  flagging here so a future VE session doesn't rediscover it the same way.
- **T_PRL_08's seq-mismatch leg cannot be manufactured via the current debug
  surface.** `debugInjectGeocode()` deliberately self-stamps the injected
  result's `seq` to whatever is currently pending (VE-PRL-2's own design —
  "carries whatever seq the consumer's pending request has, so it passes the
  identity check"). That means a genuinely *stale* seq can only arrive from a
  real overlapping network fetch, not from the stub hook. The suite instead
  proves the half that IS DUT-provable: cancel mid-lookup leaves clean state
  (SourceFork, nothing persisted), and a late REAL Nominatim result that
  lands afterward (confirmed via non-consuming `get geocode` peek) does not
  touch the slot. The seq-mismatch discard itself
  (`if (r.seq != _prGeoSeq) return;` in `_tickPrLookup()`) is a code-review
  finding — the same one-line identity-guard shape already DUT-proven for
  the analogous `StockChartResult` (TASK-300), not independently
  re-provable live without a seq-injection hook that doesn't exist.
- **T_PRL_07's destructive leg was not run.** The non-destructive half
  (settings survive a firmware `run/flash`/`run/flash-debug` reflash) is
  implicitly proven — every task in this milestone reflashed the DUT
  multiple times across TASK-319 through TASK-324 and `get prloc` came back
  correct every time. The *destructive* half (`run/flash-fs` wipes
  `cal.json`+`settings.json` — documented, expected behaviour, but a real
  wipe of the DUT's live configuration) needs explicit human go-ahead before
  running; not run in this session.
- **T_PRL_11 (geocode during Spotify-active) is blocked by TASK-243**
  (external: owner-account Premium lapsed), same disposition M-PLANERADAR's
  own exit-criterion-4 soak used. `spotifyAuthError:true`/
  `spotifyConnecting:true` were visible throughout this session's `get
  activeError` output — Spotify is retrying its 403 poll, not holding a live
  playback TLS session, so the specific tlsYield-under-real-playback
  interleaving this test wants cannot be exercised until that clears.
  Re-run once TASK-243 clears.
- **T_PRL_01b (live [NETWORK] smoke) was already exercised** at TASK-320's
  own close-out (`prloc_smoke.py` Phase B: live NL postcode 2513AA →
  52.0795/4.3132, seq-matched) and again incidentally by T_PRL_08's real
  fetch in this session (same result). Cited rather than re-run — Nominatim
  is a 1 req/s policy-limited free service; the space-postcode-encoding leg
  specifically (a UK postcode) is the one gap in that coverage, left for a
  dedicated pass if wanted.
- **Every slot this suite's script touched was restored to its exact
  pre-test contents and the original active index** (`Z0` assertion in the
  script) — the DUT's real, in-use location presets (AMS/HH/CAM/WFD at run
  time) were not permanently altered.

---

## Test inventory

| ID        | Description                                                              | Method | Result |
|-----------|---------------------------------------------------------------------------|--------|--------|
| T_PRL_01a | Stubbed editor round-trip (gate) — label→country→postcode→pending→confirm→save | serial | **PASS 2026-07-15** — cited from `prloc_editor_smoke.py`, TASK-321 close-out, 14/14 |
| T_PRL_01b | Live [NETWORK] smoke incl. real Nominatim fetch                          | serial | **PASS (cited)** — TASK-320 close-out (`prloc_smoke.py` Phase B) + incidental re-confirmation in T_PRL_08 this session. Space-postcode-encoding leg specifically not separately re-run. |
| T_PRL_02  | Strip tap switches location (active index, state reset, epoch bump)      | serial | **PASS 2026-07-16** — active index updated, `prLastAction=STRIP_LOC_<i>`, `connecting` resets true then settles false |
| T_PRL_03  | Geocode failure paths (-96 not-found; -97 already covered at TASK-321)   | serial | **PASS 2026-07-16** — -96 stub → LookupError → Cancel → slot untouched (companion to the -97 leg in `prloc_editor_smoke.py`) |
| T_PRL_04  | Migration — pre-upgrade settings.json (no prLocs) → slot 0 seeded        | serial | **PASS (cited)** — TASK-319 close-out (`prloc_smoke.py` Phase A) |
| T_PRL_05  | Same-slot tap no-op; delete-active-slot falls back to slot 0             | serial | **PASS 2026-07-16** — no-op confirmed via stable `connecting:false`; delete-active fallback confirmed (`active`→0, mirror→slot 0 coords) |
| T_PRL_06  | Manual lat/lon entry range validation                                    | serial | **PASS (cited)** — TASK-322 close-out (`prloc_manual_smoke.py`, 13/13) |
| T_PRL_07  | Persistence layers (reflash vs flash-fs wipe)                            | —      | **PARTIAL** — reflash-survival implicit (many reflashes this milestone, always correct); flash-fs-wipe leg **not run** (destructive, needs explicit human go-ahead) |
| T_PRL_08  | Late result after cancel                                                 | serial | **PARTIAL (code-verified for the seq-mismatch half)** — cancel-mid-lookup clean-state + late-real-result-inert both DUT-confirmed; genuine seq mismatch not manufacturable via the debug surface (see notes) |
| T_PRL_09  | Switch discards in-flight old-location fetch (epoch)                     | serial | **PASS 2026-07-16** — back-to-back `set prloc active` settles cleanly on the final slot, no crash, fetch completes correctly after the race |
| T_PRL_10  | Slot-0 delete refusal                                                    | serial | **PASS (cited)** — `prloc_editor_smoke.py` G1, TASK-321 close-out |
| T_PRL_11  | Geocode during Spotify-active (tlsYield coexistence)                     | —      | **BLOCKED** — TASK-243 external (Spotify Premium lapsed); re-run once cleared |

---

## Preconditions (common)

- `./run/flash-debug` complete, firmware `cyd2usb_winamp_debug`.
- Device on WiFi. Spotify session need not be authenticated/playing for any
  leg in this suite except T_PRL_11 (blocked regardless, see above).
- `app/tools/prloc_ve_smoke.py` requires all 4 `prLocs` slots to already be
  filled (uses whichever labels are live on the DUT, restores them exactly
  afterward) — run it against a device that already has 4 named locations
  configured, not a freshly-migrated/empty one.

---

## Notes

- Nominatim (OpenStreetMap) is a free, policy-limited (1 req/s) public
  service — T_PRL_01b/08's live legs are inherently network- and
  rate-policy-dependent; this run saw one real fetch (The Hague, NL
  2513AA) complete correctly in the background after its triggering lookup
  had already been cancelled in the UI.
- All three scripts referenced here (`prloc_smoke.py`, `prloc_editor_smoke.py`,
  `prloc_manual_smoke.py`, `prloc_ve_smoke.py`) are independent, standalone,
  and safe to re-run — each captures the DUT's pre-test state and restores
  it before exiting.
