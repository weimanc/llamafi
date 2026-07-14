# VE Panel Review — M-PR-LOCATIONS (PlaneRadar location presets + geocode lookup)

> Reviewer: Verification Engineer · Date: 2026-07-13 · Reviewed at design doc revision
> "Q1–Q7 resolved by human same day" (`M-PR-LOCATIONS-location-presets.md`)
> Scope: testability review per the inter-agent protocol (VE challenges Developer/Architect
> on testability before implementation finalised). Design doc not yet implemented —
> `git status` confirms `planeRadarApp.h`'s only uncommitted diff is unrelated palette work
> (TASK-312 icon-draft colour matching); no M-PR-LOCATIONS code exists yet.
> **Verdict: PASS-with-actions** — 2 blockers, 4 majors, 6 minors. None require re-architecting
> the feature; all are closeable within the design doc before TASK breakdown.

---

## Code-claim verification

Verified true in tree:

- `handleInput` returns `false` for `x >= PR_STRIP_X` today (`planeRadarApp.h:207-212`) —
  strip is display-only, matches the doc's "supersedes phase0-preview-ui.md" claim.
- Strip geometry constants exist exactly where cited: `PR_STRIP_ROW_RANGE_Y=5`,
  `_COUNT_Y=43`, `_AGE_Y=193`, `_ERR_Y=213` (`planeRadarApp.h:113-116`); `"N^"` bezel marker
  draw call at `planeRadarApp.h:481` (confirmed literal `tft.drawString("N^", PR_STRIP_LABEL_X, 120, 1)`).
- `dbgGet`/`dbgSet` on `PlaneRadarApp` (`planeRadarApp.h:225-311`) confirm the existing
  TASK-276 injection pattern: `prInjectAircraft` sets `_injected=true`, and `tick()`
  (`:181`) gates the real poll behind `if (!_injected)` — this is the concrete mechanism
  the design doc gestures at for `set geocode` ("Injection must follow the TASK-276
  lesson") but does not itself specify with the same precision (see VE-PRL-2).
- `settingsStorage.cpp` migration pattern for `planeRadar` block (`:252-261`) uses
  per-field `containsKey()` checks with `|` defaults — the proposed `prLocs` migration
  (seed slot 0 from `prLat/prLon` when the key is absent) is a straightforward extension
  of an existing, working pattern. No concern with the migration mechanism itself.
- `dataTaskCerts.h` has no `NOMINATIM_ROOT_CA` symbol yet, and `run/check-datatask-certs`'s
  `ENDPOINTS` list (line ~35) does not include `nominatim.openstreetmap.org` — confirms
  the doc's "add to run/test step-0 preflight roster" is a real, currently-missing action
  item, not already done (VE-PRL-12).
- `M-CERT-ERRCODE-cert-error-sentinel.md` — confirmed **Status: draft**, dated 2026-07-13
  (same day as this design), "no ADR needed" but not landed. This design's error-path
  testability (T_PRL_03) leans on `-120 CERT_VERIFY_FAILED` from that companion doc
  (VE-PRL-11).
- Settings sub-view text entry (`KeyboardWidget`, `appsSection.h:191` stock-ticker flow)
  has **no** documented serial-injection shortcut for typing. Checked
  `test_plan.md` T232/T233/T246/T247 (the closest existing precedent, Stock ticker
  keyboard editor) — all still **Status: planned**, and T233's step is literally
  "type `"TSLA"`" with no described mechanism (no per-key tap sequence, no `set kbText`-
  style hook). This gap is inherited wholesale by M-PR-LOCATIONS' three keyboard-driven
  editor fields (label, country, postcode) — see VE-PRL-1.
- `dataTask.h` confirms the shared-queue architecture (`enqueue*()` / `poll*()` pairs per
  fetch type, `dbgQueueState()` for queue-full/wedge diagnosis) — geocode's
  `enqueueGeocode`/`pollGeocode` slot into this same shape. Relevant to VE-PRL-5/6/7.
- `PR_POLL_MS` comment confirms PlaneRadar's own periodic poll is "foreground-only"
  (`planeRadarApp.h:105`) — so PlaneRadar's *own* fetch cannot race the geocode fetch
  while the user is in Settings (PlaneRadar app is suspended). The real concurrency risk
  is spotifyTask's independent, always-running TLS session (tlsYield/tlsResume), not
  PlaneRadar itself — narrows VE-PRL-7's scope accordingly.

---

## Findings

### VE-PRL-1 (blocker) — No serial-injection primitive exists for KeyboardWidget text entry; T_PRL_01/04(setup)/06 are not executable as specified

The design's editor flow requires **three** separate keyboard-driven text entries per
slot-create (label, country, postcode) or two (label, lat/lon ×2 digits) for the manual
path. The doc's own verification section proposes `set prloc` / `set geocode` shortcuts
for *state*, but says nothing about driving the *keyboard UI* itself — and the only
existing precedent for keyboard-driven Settings entry (Stock ticker editor, T232/233/246/
247) is itself unresolved: those tests are still `planned` with no documented typing
mechanism. Per-key tap sequences against `KeyboardWidget`'s on-screen key layout are
possible in principle but were never built for Stock's ticker editor either — this design
doesn't invent a new solution, it just inherits the same open gap, now three text fields
deep instead of one.

Without this, T_PRL_01 ("create slot via geocode... save") and T_PRL_06 ("manual lat/lon
entry round-trip") cannot be driven by any documented harness technique. `set prloc <i>
<label> <lat> <lon>` (proposed) bypasses the editor entirely and is fine for *state*
setup/teardown, but the design explicitly wants T_PRL_01/06 to exercise the **editor UI**
(that's the whole point of those two tests — the shortcut commands exist precisely so
other tests don't have to).

**Severity:** blocker.
**Resolution:** Add a debug-only `set kbText <value>` hook: when `KeyboardWidget` is the
active modal, this hook injects the full string into its buffer and fires the OK/commit
action in one shot (mirrors `set geocode`'s "stub the next result" shape — same category
of debug-only bypass, not a new pattern). File as a shared serialdbg primitive (benefits
Stock ticker T233/T246 too, not just this feature) rather than a PlaneRadar-only hack.

---

### VE-PRL-2 (blocker) — `set geocode` stub isolation is named but not designed; TASK-276 lesson is cited, not applied

The doc states: *"Injection must follow the TASK-276 lesson: injected state is
cleared/consumed on first poll, and tests isolate against concurrent real fetches
(autoSkip-style isolation)."* This describes the **goal**, not a **mechanism**. Compare
to the existing, working TASK-276 implementation this doc is citing:
`PlaneRadarApp::dbgSet("prInjectAircraft", ...)` sets `_injected = true`, and every real
fetch call site in `tick()`/`resume()`/`handleInput()` is gated `if (!_injected)`
(`planeRadarApp.h:163,177,221,339`) — injection **structurally pre-empts** the real path,
not just "clears on first poll."

For `set geocode`, no equivalent gating is specified:

- Is `enqueueGeocode()` itself suppressed while a stub is armed (structural pre-emption,
  matching `_injected`), or does `set geocode` just pre-load the result slot that
  `pollGeocode()` reads, leaving a real in-flight request free to also complete and
  overwrite it (or vice versa — race, whichever completes/gets-polled second wins)?
- `dataTask`'s `enqueueGeocode`/`pollGeocode` presumably share one result slot per the
  existing `enqueue*`/`poll*` pattern (`dataTask.h`). If a test issues `set geocode ...`
  while the editor's own live "Lookup" flow already has a real `enqueueGeocode()` in
  flight (e.g., harness fires the stub mid-spinner to short-circuit a slow test), the
  slot gets written twice and whichever `pollGeocode()` call lands first wins
  nondeterministically — exactly the class of bug TASK-276 was filed to fix in WebRadio.

**Severity:** blocker (the doc itself flags this as a required property — it should not
ship as a to-be-discovered implementation detail).
**Resolution:** Mirror `_injected` exactly: add a `bool s_geocodeStubbed` (or equivalent)
that (a) `set geocode` sets, (b) the editor's `enqueueGeocode()` call site checks and
skips the real HTTP enqueue when set, (c) `pollGeocode()` clears it after the stub is
consumed exactly once. Document this in the design doc's Verification section with the
same precision as `prInjectAircraft`'s comment block, not a one-line lesson citation.

---

### VE-PRL-3 (major) — T_PRL_01 conflates live-network risk with the actually-novel logic under test; repeats the T_PR_05 SKIP pattern

T_PRL_01 is specced as one test: live Nominatim lookup → save → reboot → persists,
`[NETWORK]`-tagged. This bundles three independent concerns into one pass/fail: (a) does
Nominatim answer and does the TLS chain verify (network- and OSM-availability-dependent,
plus the doc's own noted cross-sign fragility risk), (b) does the on-device JSON→
`GeocodeResult` parse work, (c) does the editor's save/persist/reboot-survival logic
work. `m-planeradar-dut.md` already documents exactly this failure shape for T_PR_05
(SKIP 2026-07-11, 20/20 rapid-fire attempts never hit adsb.fi's rate limit) — and the
design doc itself invokes that history to justify keeping `[NETWORK]` tests to "the
single genuine end-to-end case." T_PRL_01 as specced *is* that end-to-end case, but it's
also load-bearing for (b) and (c), which are the parts new code actually risks getting
wrong — Nominatim's uptime/rate-limiting is not.

**Severity:** major.
**Resolution:** Split into:
- **T_PRL_01a** (non-network, primary regression gate): `set geocode <lat> <lon>
  <display>` stub → drive editor via `set kbText` (VE-PRL-1) → Save → reboot → `get
  prloc` confirms slot persists with stubbed values. This is what actually gates CI/
  pre-merge.
- **T_PRL_01b** (`[NETWORK]`, smoke only): live Nominatim lookup for one known-good
  postcode → assert via `get prloc`'s "last geocode result" fields that `ok=true` and
  `lat`/`lon` are non-zero and plausible (bounding box check, not exact match). Does
  **not** re-verify save/persist/reboot — 01a already owns that.

---

### VE-PRL-4 (major) — No test distinguishes reflash-preserves-SPIFFS vs `flash-fs`-wipe; T_PRL_04 only covers the pre-upgrade-JSON migration path

T_PRL_04 tests "pre-upgrade settings.json (no `prLocs` key) → slot 0 seeded." That is one
of at least three distinct persistence scenarios this feature needs covered, per
project memory (`run/flash-fs wipes cal.json+settings.json`) and `CLAUDE.md`'s SPIFFS
section:

1. **Migration** (T_PRL_04, covered): old `settings.json` present, lacks `prLocs` key →
   seeded from `prLat`/`prLon`.
2. **Ordinary reflash** (missing): `./run/flash-debug` / `./run/flash` reflash firmware
   only, SPIFFS partition untouched — `prLocs[]` with multiple populated slots must
   survive byte-for-byte, including a non-zero `prActiveLoc`.
3. **`flash-fs` destructive wipe** (missing): full SPIFFS format — `settings.json` itself
   is gone, not just missing a key. Boot must fall through to `applyDefaults()`'s
   compile-time seed (slot 0 = "HOME" / `prLat`/`prLon` defaults), not crash or read
   garbage. This is a different code path from migration (no file at all vs. a file
   missing one key) and is worth a distinct assertion given `flash-fs`'s known
   destructive footprint on this project (settings/cal wipe already bit prior features).

**Severity:** major.
**Resolution:** Add T_PRL_07 (ordinary reflash preserves `prLocs`) and T_PRL_08
(`flash-fs` wipe → clean-default seed, not corruption) — see Proposed test additions.

---

### VE-PRL-5 (major) — Stale in-flight geocode result delivered to a UI state that has moved on (cancel mid-lookup, or editor now on a different slot)

The design specifies Retry/Cancel appear "on result" (after `pollGeocode()` returns) but
doesn't say what's allowed **during** the spinner (fetch in flight) or what happens to a
late-arriving result if the user backs out of the editor, or cancels and starts editing
a *different* slot, before `pollGeocode()` next returns true. Given `dataTask`'s
established one-result-slot-per-fetch-type shape (`dataTask.h`), a `pollGeocode()` call
made from "now editing slot 2" context has no documented way to distinguish "this result
is for the lookup I just started" from "this is a stale result for the slot-1 lookup I
abandoned two screens ago." This is the same bug class (stale async result rendered into
a UI that has since changed context) that this project has hit before in other
dataTask-backed apps (e.g. the `_pendingFetch`/`_injected` gating machinery throughout
`planeRadarApp.h` exists specifically to prevent it for the render path).

**Severity:** major.
**Resolution:** Either (a) block Cancel during the spinner (fetch in flight is
uncancellable, editor stays on the spinner until `pollGeocode()` returns, purely a UX
simplification), or (b) tag the enqueue with a generation/slot id and have the editor
discard a `pollGeocode()` result whose tag doesn't match current context. Whichever is
chosen, add it to the design doc explicitly and cover with T_PRL_10.

---

### VE-PRL-6 (major) — Strip tap during pending fetch: stale in-flight `PlaneRadarResult` for the old location can land after the switch

`handleTouch`'s new strip-tap behaviour is specced as: switch `prActiveLoc` → write
through `prLat/prLon` → `saveSettings()` → full repaint → **immediate**
`enqueuePlaneRadar()` at the new centre. But if a tap lands while the *previous*
location's fetch is still `_pendingFetch == true` (the existing member, `planeRadarApp.h:
315`), the design doesn't say whether that stale request is superseded/discarded or
left to complete. `dataTask`'s `enqueuePlaneRadar()` "snapshots params under a spinlock"
(per TASK-303's resolution note) — nothing indicates a second `enqueuePlaneRadar()` call
cancels the first; if the old-location fetch resolves *after* the new one is enqueued,
`tick()`'s `pollPlaneRadar()` (`:183`, ungated on which coordinates the result is *for*)
will render whichever result comes back last, which could be the stale, wrong-location
one landing after the correct one — a location-switch flicker/wrong-render bug directly
in the lineage of TASK-308/309's "stale-scale runway overlay" fixes this same file
already needed once.

**Severity:** major.
**Resolution:** Either debounce/guard `handleTouch`'s strip case behind `!_pendingFetch`
(same-slot tap already has a `slot == prActiveLoc` guard per the design — extend the
guard to "no switch while a fetch for the current slot is outstanding," accepting a tap
being a no-op for ~10s worst case), or tag `enqueuePlaneRadar` results the same way
VE-PRL-5 proposes for geocode. Cover with T_PRL_11.

---

### VE-PRL-7 (minor) — tlsYield/tlsResume cross-task contention not covered by any T_PRL test despite this project's history in exactly this area

`PR_POLL_MS` is foreground-only, so PlaneRadar's own poll can't race the new geocode
fetch (PlaneRadar is suspended while the user is in Settings). But `spotifyTask` runs
independently of foreground app and has repeatedly (5 documented fix layers per project
memory: TASK-285/286/287/289/295) collided with `dataTask`'s TLS usage via
`tlsYield()`/`tlsResume()`. The design does cite "`tlsYield()` before handshake per
BP-031" for the geocode fetcher — the convention is followed on paper — but no T_PRL
test actually exercises "trigger a geocode lookup while Spotify is actively playing,"
which is exactly the condition under which every prior tlsYield bug in this codebase
surfaced.

**Severity:** minor (mechanism is designed correctly; this is a regression-coverage gap,
not a design flaw).
**Resolution:** Add T_PRL_09 — geocode lookup with an active Spotify session, asserting
no stall/crash and normal Spotify polling cadence continues (`get backoff` /
`consecutiveFailures` unchanged) through the geocode fetch.

---

### VE-PRL-8 (minor) — Label uniqueness undefined; no test either way

Nothing in the storage layer or editor flow validates that two slots can't share a
label (e.g. two slots both "HOME"). This isn't a functional bug — strip taps and
`set prloc active <i>` switch by index, not label — but it's a support/UX footgun the
design doesn't resolve, and the sketch doesn't test the current (presumably permissive)
behavior either way.

**Severity:** minor.
**Resolution:** Either explicitly decide "duplicates allowed, cosmetic only" in the
design doc, or add uniqueness validation to the editor's Save step. Add T_PRL_12 to pin
down whichever is chosen.

---

### VE-PRL-9 (minor) — On-device URL-encoding of a space-containing postcode is only verified on the host, not the DUT

The "Host-side left shift" phase-0 probe plan explicitly covers "space and `+` handling
in `postalcode=`" — but only as a **host-side** Python probe. The actual on-device
`enqueueGeocode()` → URL-building code path (hand-rolled `snprintf`-style string
assembly is the norm elsewhere in this codebase) is a separate implementation that could
diverge from the probe script's encoding logic. No T_PRL test drives a UK-style
space-containing postcode (`SW1A 1AA`) through the real device and inspects the request
URL.

**Severity:** minor.
**Resolution:** Add T_PRL_13 — geocode a space-containing postcode, inspect the actual
outgoing URL via the same `LOG_D` mechanism T_PRL_02 already uses ("assert via `get
dataq` / LOG_D URL") to confirm the space is encoded, not passed literally or dropped.

---

### VE-PRL-10 (minor) — Delete-slot-0 no-op invariant is stated but not in the T_PRL sketch

Design states slot 0 "is not deletable (always-defined invariant)." T_PRL_05 covers
delete-active-falls-back-to-slot-0 but not the case of attempting to delete slot 0
itself (Delete action available/disabled? silently no-op if reachable?).

**Severity:** minor.
**Resolution:** Add explicit slot-0-delete-attempt coverage — T_PRL_14.

---

### VE-PRL-11 (minor) — M-CERT-ERRCODE dependency is itself still draft/unimplemented; sequencing risk for T_PRL_03

T_PRL_03 (geocode failure paths) and the design's `-120 CERT_VERIFY_FAILED` error
surfacing both depend on `M-CERT-ERRCODE-cert-error-sentinel.md`, confirmed **Status:
draft**, same date as this doc, not yet an accepted/implemented design. If M-CERT-ERRCODE
lands after M-PR-LOCATIONS' fetcher code, `-120` won't exist yet and cert-failure paths
will surface as whatever `dataTaskStorage.cpp` did before that sentinel (likely a raw
negative HTTPClient code) — T_PRL_03's failure-path assertions need to know which world
they're testing in.

**Severity:** minor (sequencing note, not a design defect).
**Resolution:** PM/Architect confirm M-CERT-ERRCODE lands before or alongside the
geocode fetcher task; if not guaranteed, T_PRL_03 should assert "some non-zero error
code, decoded name TBD" rather than hardcoding `-120`.

---

### VE-PRL-12 (minor) — Nominatim not yet in `run/check-datatask-certs`'s `ENDPOINTS` roster

Confirmed by direct inspection: `nominatim.openstreetmap.org` / `NOMINATIM_ROOT_CA` are
absent from `run/check-datatask-certs`'s `ENDPOINTS` list. The design doc's "Nominatim
host added to the run/test step-0 cert preflight roster" is presently just a sentence,
not a landed action.

**Severity:** minor (concrete, mechanical, low-risk to close).
**Resolution:** Add the `(nominatim.openstreetmap.org, NOMINATIM_ROOT_CA)` tuple to
`ENDPOINTS` as part of the same task that adds `NOMINATIM_ROOT_CA` to `dataTaskCerts.h`
— not a separate follow-up, so it can't slip the way golden-hash staleness slipped in
the M-APP-REGISTRY precedent.

---

## Verdict summary

| # | Finding | Severity |
|---|---|---|
| VE-PRL-1 | No serial text-injection primitive for KeyboardWidget | blocker |
| VE-PRL-2 | `set geocode` isolation named, not designed (TASK-276 lesson unapplied) | blocker |
| VE-PRL-3 | T_PRL_01 conflates network flake with novel logic — T_PR_05 pattern repeat | major |
| VE-PRL-4 | Reflash-preserves vs `flash-fs`-wipe persistence untested | major |
| VE-PRL-5 | Stale geocode result vs. moved-on editor context | major |
| VE-PRL-6 | Stale in-flight PlaneRadarResult after strip-tap location switch | major |
| VE-PRL-7 | No test for geocode fetch concurrent with active Spotify session | minor |
| VE-PRL-8 | Label uniqueness undefined, untested | minor |
| VE-PRL-9 | On-device URL-encoding of space-postcode unverified (host-only probe) | minor |
| VE-PRL-10 | Delete-slot-0 no-op invariant untested | minor |
| VE-PRL-11 | M-CERT-ERRCODE dependency still draft — T_PRL_03 sequencing risk | minor |
| VE-PRL-12 | Nominatim missing from cert preflight roster (mechanical) | minor |

**Verdict: PASS-with-actions.** The overall design — settings shape, write-through-mirror
persistence strategy, `PrLocation[4]` sizing, Lookup|Manual editor fork, and the intent to
reuse the TASK-276 injection pattern — is sound and consistent with this project's
established conventions. Both blockers are closeable by extending patterns that already
exist in the tree (VE-PRL-1 generalizes a gap the Stock ticker editor already has;
VE-PRL-2 asks only that `set geocode` be built with the same rigor `prInjectAircraft`
already demonstrates). Recommend resolving VE-PRL-1/2 in the design doc text before
TASK breakdown; majors (3-6) should be folded into the T_PRL sketch before implementation
starts so tests aren't retrofitted after the fact; minors can be tracked as implementation
notes.

---

## Proposed test additions (T_PRL_07..14, plus T_PRL_01 split)

- **T_PRL_01a** — non-network editor round-trip via `set geocode` stub + `set kbText` +
  reboot persistence. Replaces T_PRL_01 as the primary gate (VE-PRL-3).
- **T_PRL_01b** `[NETWORK]` — live Nominatim smoke only (`ok=true`, plausible lat/lon via
  `get prloc`'s last-geocode fields); does not re-check persistence (VE-PRL-3).
- **T_PRL_07** — ordinary reflash (`run/flash-debug`, SPIFFS untouched) preserves
  populated `prLocs[]` + non-zero `prActiveLoc` (VE-PRL-4).
- **T_PRL_08** — `run/flash-fs` full wipe → boot re-seeds clean compile-time default
  (slot 0 "HOME"), no corruption/crash reading a missing `settings.json` (VE-PRL-4).
- **T_PRL_09** — geocode lookup triggered while Spotify session is actively polling;
  assert no stall, `consecutiveFailures` unaffected (VE-PRL-7).
- **T_PRL_10** — cancel (or back-out) mid-lookup, then start editing a different slot;
  assert the first slot's late-arriving stub/real result does not corrupt the second
  slot's in-progress edit (VE-PRL-5).
- **T_PRL_11** — strip tap to switch location while the previous location's fetch is
  still `_pendingFetch`; assert the disc never renders the stale (old-location) result
  after the switch (VE-PRL-6).
- **T_PRL_12** — save two slots with an identical label; assert documented behavior
  (allowed-cosmetic-only, or rejected — whichever the design settles on) (VE-PRL-8).
- **T_PRL_13** — geocode a space-containing UK postcode on-device; inspect the real
  outgoing request URL via `LOG_D`/`get dataq` for correct encoding (VE-PRL-9).
- **T_PRL_14** — attempt to delete slot 0 from the editor; assert no-op / action
  unavailable, `prLocs[0]` unchanged (VE-PRL-10).

**Prerequisite infrastructure** (blocks the above, not itself a T_PRL test):
`set kbText <value>` debug hook for `KeyboardWidget` injection (VE-PRL-1), and the
`set geocode` structural-pre-emption fix mirroring `_injected` (VE-PRL-2).
