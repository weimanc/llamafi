# Lessons Learned

> Owner: Quality Manager

Populated during retrospectives. Entries reviewed w/ human for promotion to `best_practices.md`. No promotion without explicit human sign-off.

## Retrospective — 2026-04-28 — ADR-006 direction change + M0 close + M1 spike + time-001 fix

Triggering work: re-scope of the Winamp UI architecture (ADR-006), creation and partial run of the M1 API capability spike, and the time-001 NTP fix that unblocked TLS on the DUT. Below: what went well, what didn't, individual lessons. All entries `open` until human sign-off promotes any to `best_practices.md`.

### What went well (no LL needed, recorded for balance)

- **Plan-first caught a costly redirection cheaply.** The original M1 ADRs prescribed a portable `core/` + `platform/` leaves layout with a PC-mirror build target. Asking the user "stay close to baseline?" *before* writing any code surfaced ADR-006 in one short exchange, superseding three ADRs (001/004/005) without rework.
- **Vendoring + tiny patch worked.** One 3-line `getBearerToken()` getter added to the vendored `SpotifyArduino`, documented in `LOCAL_PATCHES.md`, was sufficient to enable raw `audio-features` / `audio-analysis` GETs without forking semantics.
- **time-001 fix was definitive.** The DUT run produced a clear verdict: the TLS-layer error was 100% clock-related; the residual failure is purely credentials. No ambiguity; no further diagnostic loops needed.
- **Build-verify before flash.** Both env compiles caught no errors but the discipline ensured the DUT trip was strictly a verification step, not iterative debugging.

---

### LL-001 — 2026-04-28 — Diagnose ESP32 TLS failures by checking the clock first

**Context**: First DUT run of the M1 spike returned `ssl_client.cpp:37 _handle_error 0x0050` and `Status Code: -2` on every refresh attempt. Initial hypothesis tree included cert-trust, library bug, network flakiness, and only after host-side cert chain inspection did the system-clock theory surface.

**Observation**: ~30 minutes of diagnostic time + one user round-trip spent ruling out cert and network issues before naming the right cause. The fix itself (3 lines: `configTime()` + bounded wait) took five minutes to write.

**Root cause**: ESP32 has no RTC and the firmware never called `configTime()`. mbedTLS rejects certs whose `notBefore` is in the future and surfaces the failure as a generic send error rather than a cert-validation error code, which misleads the diagnostic order.

**Suggested improvement**: For any ESP32 / RTC-less Arduino target that does TLS, the very first diagnostic question on a TLS failure (especially first-after-boot) should be "is `time(nullptr)` past a sane epoch?" The fix is a one-liner template; ranking it ahead of cert trust saves time.

**Status**: open

---

### LL-002 — 2026-04-28 — Rotate leaked credentials immediately, do not defer

**Context**: TASK-006 was opened on the day of bring-up (TASK-001) when the refresh token was first pasted into a chat transcript. It sat as a backlog item for the rest of the session. Today's DUT run revealed Spotify's leak scanner had auto-revoked the token: `invalid_grant — Refresh token revoked`. The blocker now sits on user account access, which itself is currently impaired.

**Observation**: The leak window between exposure and revocation was the entire session. Had the rotation been done at TASK-001 close, M1 would not be blocked today. The deferral cost a milestone of progress.

**Root cause**: TASK-006 was treated as housekeeping rather than incident response. Rotation was framed as "do this before going public" rather than "do this *now* because the secret is in the wild."

**Suggested improvement**: Treat any credential exposure as a P0 incident-response item, not a queueable task. Specifically: a leaked OAuth refresh token requires (a) dashboard secret rotation and (b) re-issuing the refresh token, both before any further work. Don't pair it with other DUT work as "convenient batch" — block on it.

**Status**: open

---

### LL-003 — 2026-04-28 — Disable library-level secret debug output before flashing

**Context**: The vendored `SpotifyArduino` had `SPOTIFY_DEBUG` enabled, which causes the library to `Serial.print()` the full refresh-token-grant POST body — including refresh token AND client secret — on every auth attempt. With the auth path looping at 5 s, the leaked credentials were re-exposed to anyone watching the serial log on every retry, including in tmux capture buffers.

**Observation**: Even after we knew the credentials were leaked, the firmware kept loudly re-leaking them in cleartext on serial. Multiple capture-pane outputs in this session contain them.

**Root cause**: We accepted the upstream library's debug-default without auditing its log surface for sensitive output before the first flash.

**Suggested improvement**: When vendoring a library with auth handling, audit its debug logging before first flash. Specifically check for any `Serial.print` of client_secret, refresh_token, access_token, or auth bodies. If present, either disable the debug flag or redact the offending lines. Add to `LOCAL_PATCHES.md` if patched.

**Status**: open

---

### LL-004 — 2026-04-28 — Surface human-dependent prerequisites earlier in planning

**Context**: When TASK-006 (rotation) was queued for the next DUT trip, no one asked "do you currently have working Spotify dashboard access?" When the DUT was actually present and rotation was the next step, the user revealed they were having Spotify account/password issues, blocking the work mid-flight.

**Observation**: A 15-second up-front check would have re-ordered the session — we'd have done time-001 first (no account access required), then queued rotation for whenever it became viable. Instead, time-001 happened anyway but only after a stalled rotation attempt.

**Root cause**: Plans surfaced *technical* prerequisites (DUT, build env, library vendoring) but missed *human* prerequisites (account access, dashboard permissions, physical hardware presence).

**Suggested improvement**: For tasks that depend on humans clicking external dashboards, paying for services, or accessing personal accounts, add a pre-flight question to the plan or the AskUserQuestion call: "is access to X working right now?" Treat it on equal footing with technical preconditions.

**Status**: open

---

### LL-005 — 2026-04-28 — Populate `cross_feature_matrix.yaml` from feature creation, not retrospectively

**Context**: The matrix was untracked and empty until the time-001 fix. The api-001 ↔ poll-001 interaction (`X002`, spike reads `lastTrackUri`) was a known coupling at api-001 creation time but only got recorded when X001 forced the file to exist.

**Observation**: AGENTS.md / `developer.md` says: "Two+ features share state, have dependency, or could conflict, record immediately. Call interactions out explicitly — no mental notes." This was violated for ~2 hours by carrying api-001 ↔ poll-001 as a mental note.

**Root cause**: Habit. The first matrix entry feels heavyweight when the file is empty; subsequent entries are easy. Inertia.

**Suggested improvement**: When introducing the *first* feature with any cross-feature link, promote `cross_feature_matrix.yaml` from untracked to tracked in the same commit, and add the entry. Don't wait for a "second" interaction to justify the file.

**Status**: open

---

### LL-006 — 2026-04-28 — `#ifdef NFC_ENABLED` vs `#define NFC_ENABLED 0`

**Context**: Disabling NFC for TASK-004 required commenting out the `#define`, not setting it to 0, because the codebase uses `#ifdef` (which is true for any value). A comment was added at the define explaining this.

**Observation**: This worked but only because the developer noticed the gotcha mid-edit. A user instruction "set NFC_ENABLED 0" would have silently failed if executed literally.

**Root cause**: Mixing `#ifdef` for presence-check with a value-bearing macro `#define X 1` is a known C-preprocessor footgun. The codebase shipped with this pattern; we inherited it.

**Suggested improvement**: When encountering `#ifdef X` with `#define X 1`, flag the inconsistency. Either standardise on `#if X` (value-aware) or strip the value (`#define X` with no payload). For now, leave the comment block at the define so the next reader doesn't repeat the trap.

**Status**: open

---

### LL-007 — 2026-04-28 — `pio run` vendored copy: strip nested `.git` before staging

**Context**: When vendoring `SpotifyArduino` from `.pio/libdeps/cyd2usb/SpotifyArduino` to `lib/SpotifyArduino`, the upstream's `.git/` directory came along. `git add lib/` then warned about an embedded repository and would have left it as a submodule-ish reference rather than vendoring the contents. Caught and fixed by removing the nested `.git` and re-staging.

**Observation**: A second's friction; but the alternative outcome — committing a submodule pointer to upstream — would have left the patches floating outside git.

**Root cause**: PlatformIO clones lib_deps from git when given a URL; the cache retains the upstream `.git/`.

**Suggested improvement**: When vendoring out of `.pio/libdeps/`, always: `cp -r src dst && rm -rf dst/.git` before `git add`. Add to a project-level "how to vendor" note if vendoring becomes a recurring pattern.

**Status**: open

---

### LL-008 — 2026-04-29 — `WiFiClientSecure` reuse breaks non-GET on Arduino-ESP32

**Context**: TASK-007 spike run. Library makes a `getCurrentlyPlaying` GET successfully, then any subsequent `nextTrack` (POST) or `pause` (PUT) on the same client object fails at `client->println()` with mbedTLS `0x0050 (NET_CONN_RESET)`. GETs still succeed indefinitely; non-GETs fail consistently.

**Observation**: A whole class of API calls — every control endpoint the Winamp UI needs — is broken on the current stack despite the library's API surface looking complete. `audio-features` / `audio-analysis` (both GET, made via raw `makeGetRequest`) DID reach Spotify and return authoritative HTTP responses, confirming the issue is specifically non-GET on the shared client, not GETs in general.

**Root cause** (hypothesised, to be confirmed during TASK-009): Arduino-ESP32 2.0.17 `WiFiClientSecure` does not always reset its TLS context cleanly across `stop() → connect()` cycles. The library's `makeRequestWithBody` path (PUT/POST) calls `client->flush()` then `client->connect()` then writes headers — the write fails because the prior TLS context isn't fully torn down. The GET path happens to work, possibly because of how its specific timing or buffer state aligns. This is a documented class of bug in the ESP32 Arduino TLS stack.

**Suggested improvement**: For any Arduino-ESP32 firmware doing both GETs and POST/PUTs to the same TLS host, do **not** share a single long-lived `WiFiClientSecure` across request types. Either allocate a fresh client per request (heap fragmentation risk to manage), or — better — use `HTTPClient` which manages connection lifecycle internally. Spike-style harnesses should test at least one GET and one non-GET before declaring a library "works."

**Status**: open

---

### LL-009 — 2026-04-29 — Spotify deprecated `audio-features` / `audio-analysis` for new Developer apps

**Context**: TASK-007 spike run. Both `GET /v1/audio-features/{id}` and `GET /v1/audio-analysis/{id}` return HTTP 403 for the dev account's app `db2ff394...` (created during TASK-001 in 2026-04-26). ADR-002 had architected the entire VU-meter feature around `audio-analysis` data, with `audio-features` as a fallback — both gates closed.

**Observation**: An architecture decision (ADR-002) that looked solid at design time was based on an API capability Spotify has since revoked for new app registrations. The deprecation was announced in late 2024 (Spotify Web API change-log) and our app, registered post-deprecation, has never had access. The architecture review missed the policy/access dimension entirely.

**Root cause**: Architecture review treated Spotify's API as a given technical surface, not a policy surface that the API provider can constrain by app age, by approval status, or by quota tier. We did not check the API change-log against our app's registration date, or test the endpoints during architecture (they would have returned 403 then, too).

**Suggested improvement**: For any architecture decision that depends on a third-party API endpoint, the architect should — as part of the decision — verify the endpoint actually returns data for the app in question, not just that it exists in the documentation. Where the provider distinguishes app tiers (Spotify Extended Quota Mode, Twitter elevated access, etc.), record which tier the project assumes and what happens if that tier becomes unavailable.

**Status**: open

---

## Retrospective — 2026-05-07 — Multi-day session, M4 close + M2 tier 1 + dev-001 back-fill

Triggering work: M4 polish (TASK-011), M2 skin bake tool tier 1 (TASK-012), and back-filled tracking for the cellular/captive-portal dev infra (TASK-013, dev-001) shipped during the 2026-05-05/06 field-debug session.

### What went well

- **Bake tool delivered on first attempt with working preview.** Pillow + ImageMagick fallback handled all three Winamp BMPs; output compiled clean; preview composite matched layout on visual check.
- **DNS override + HTTPS-Date stack designed iteratively against real failures.** Each shim was pulled out only when a specific upstream condition (DNS block, NTP block, captive-portal MAC gating) was confirmed by a separate experiment. No speculative infrastructure.
- **MAC-spoof workaround for Marriott captive portal was diagnosed correctly.** TLS error -9984 with a now-correct clock pointed at portal interception; pre-auth via NetworkManager `cloned-mac-address` resolved it without firmware changes. Captured as procedure (memory file), not committed code.

### LL-010 — 2026-05-07 — Multi-role inter-agent protocol skipped under "single-voice" execution

**Context**: M4 close (TASK-011) and M2 tier 1 (TASK-012) both shipped without an Architect consult, VE testability challenge, or QM prompt. The 2026-05-05/06 dev-infra work shipped without *any* PM tracking — no task entry, no feature_inventory entry, no test plan. All caught by a 2026-05-07 self-audit, then back-filled.

**Observation**: When one operator plays every role, the inter-agent protocol from `AGENTS.md` (Developer→VE notification, Developer→Architect consult, PM→QM prompt, etc.) collapses into one internal voice. The mechanical conventions (commit messages with feature IDs, ADR consultation before scope decisions) survived; the structured hand-offs did not. Result: ~50% of the documented protocol followed, with the gaps clustered in cross-role notifications.

**Root cause**: Direct-invoke model (`@PM`, `@Architect`, `@VE`) is a discipline, not a tool. Without an explicit "switch hat" prompt at boundaries (feature implemented → notify VE, scope decision → consult Architect, milestone partial-complete → prompt QM), the operator stays in whichever role started the work and skips the cross-role steps.

**Suggested improvement**: For Developer-initiated work, add a checklist gate before commit: (a) Architect consulted on any scope-defining decision not covered by an existing ADR? (b) VE notified with a test entry (even if `planned-deferred`)? (c) `feature_inventory.yaml` updated? (d) PM informed via `tasks.md` entry? Failing any of these is fine — but should be a deliberate "skip with reason," not an oversight. Same gate applies in reverse for tasks PM tracks but no one implements.

**Status**: open

### LL-011 — 2026-05-07 — Dev-environment infra still belongs in PM tracker

**Context**: The 2026-05-05/06 cellular + captive-portal mitigation work (~300 lines of code, three new modules, one helper script) shipped with no `tasks.md` entry, no feature_inventory entry, no test plan. Rationale at the time: "this is dev-environment infra, not roadmap-bearing." Caught and back-filled as TASK-013 / dev-001 a day later.

**Observation**: The "not on the roadmap" framing led to "not tracked at all," but the work is in tree, has cross_features (`wifi-001`, `time-001`), and will need maintenance the moment a future user hits a different hostile-network condition. Treating it as untracked left the PM and VE with no signal that this surface area exists.

**Root cause**: PM tracking conflated with milestone tracking. The roadmap is milestone-level; `tasks.md` is broader and should cover any work that produces durable artefacts.

**Suggested improvement**: Any commit that introduces a new file under `Spotify-Diy-Thing/SpotifyDiyThing/` or `tools/` gets a `tasks.md` entry, regardless of whether it advances a milestone. If it doesn't fit any milestone, it goes in a "Dev infra" section.

**Status**: open

### LL-012 — 2026-05-08 — `WiFiClientSecure::lastError()` is a misleading name

**Context**: TASK-018 follow-up, debugging `HTTP -1` from the vendored Spotify lib. We added `client.lastError(buf, sizeof(buf))` to surface the underlying mbedtls code on `-1` returns.

**Observation**: Every `-1` reported `rc=49 (0x0031)`. mbedtls_strerror printed "UNKNOWN ERROR CODE (0031)". Spent two reflash cycles theorising about exotic socket errnos before realising 49 was the lwip socket fd from the *previous successful* `start_ssl_client` call. Arduino-ESP32 stores `_lastError = ret` where `ret` is the start_ssl_client return value — positive socket fd on success, negative on mbedtls error. The function name implies "last error" but the value is "last result", retained even when the previous call succeeded.

**Root cause**: API name doesn't match semantics. Doc string for `lastError()` doesn't clarify; we trusted the name.

**Suggested improvement**: For sticky-state APIs whose names suggest a single semantic, confirm by reading the source before building diagnostic chains on top. Treat any positive return from `lastError()` as "stale success state, not a current error." Comment the discriminator at every call site.

**Status**: open — fix already in `spotifyLogic.h` (rc>0 prints as "stale connect fd"). Promotion candidate.

### LL-013 — 2026-05-08 — Same numeric error code can mask multiple root causes

**Context**: ADR-007 patched the `WiFiClientSecure` reuse bug — fixed mbedtls `0x0050 NET_CONN_RESET` on the *first* write of a stale TLS session. Spike harness retest (one week later) still produced `0x0050` on every PUT/POST. Knee-jerk: "ADR-007 didn't actually fix it." Reality: three independent lib bugs (trailing-CRLF health check; `Content-Type: application/json` with `Content-Length: 0`; strict `204`-only status check) all produced `0x0050` at the same `send_ssl_data():382` log line. Different root causes, same numeric symptom.

**Observation**: When a fix doesn't move the needle, "the fix didn't work" is the easy hypothesis. "The same error number is masking a different bug" is the harder, more often correct one. ADR-007 *was* working; the next bug in the chain just wore the same uniform.

**Root cause**: TLS-level errors are a small enumeration; many distinct code paths funnel through the same layer and report the same code. mbedtls 0x0050 means "peer reset" — that can happen at any write, for any reason that prompts the peer to close.

**Suggested improvement**: Treat numeric error codes as the *symptom*, never the *cause*. Cross-check with: where in the request stream did the failure happen (first write vs last write — different cause); did the server send a response before the close (means a different protocol-level reject); does the lib's request shape match what the server documents and accepts (spec cross-check)? Don't accept "the fix didn't work" until each of those is checked.

**Status**: open — caught and patched (LOCAL_PATCHES.md #4–6). Promotion candidate.

### LL-014 — 2026-05-08 — Don't blame the network without a positive test

**Context**: After the ADR-007 retest failed all 15 spike rows on Marriott guest WiFi, my first hypothesis was "captive portal blocks non-GET HTTPS methods". User pushed back: AP-level method filtering of HTTPS is implausible without TLS MITM, and we had no MITM evidence (cert validation was passing on GETs). The "method filtering" hypothesis required a mechanism inconsistent with other observed facts.

**Observation**: A flaky network is a tempting target. Hard to falsify (every retry is a new chance to see the same flake). Easy to write up as "network was bad, network was bad again." Real diagnosis is more demanding — it requires a chain of mechanism, not a chain of correlations.

**Root cause**: Cognitive cheap shortcut. Network blame is the embedded equivalent of "have you tried turning it off and on again."

**Suggested improvement**: Before blaming the network for a *consistent* failure mode (sporadic ones really often are network), require either (a) a positive test that excludes the firmware/lib (e.g. curl from host succeeds where DUT fails), or (b) a mechanism explanation consistent with every other observed fact. If neither is available, treat "it's the network" as a hypothesis on equal footing with "it's the lib", not the default.

**Status**: open — directly applicable to TASK-019 / future M-IO investigations. Promotion candidate.

### LL-016 — 2026-05-09 — "Swap X" is under-specified when a feature has multiple layers

**Context**: M-CHROME tier 1 mono/stereo indicator. User said "mono and stereo needs to be swapped." I changed it. User said "swapped again." I changed it back differently. User said "both unlit." I added a default + snapshot-seq refresh. User said "stereo lit, mono dim. just swap stereo and mono please." Final fix: swap two `blitSprite` call positions. **Four reflash cycles to land a one-line change.**

**Observation**: the visible state of a sprite-based indicator is the composition of *three* layers: (a) where the labelled pixels live in the source BMP atlas (UV mapping), (b) the runtime state assignment (which sprite is "lit" given the current data), (c) the on-screen position (where each sprite gets blitted). "Swap" is ambiguous across all three. I picked the wrong layer twice, lost ~5 minutes of DUT-iteration churn each time, and burned the user's patience.

**Root cause** (multi-stage):
1. **First round, didn't even look at the asset.** Picked layer (a) on intuition before examining the BMP. Should have extracted + zoomed the bitmap *first* — the visual ground truth was 30 seconds away.
2. **Conflated bugs.** "Both unlit, swapped again" is two reports. I treated it as "fix the swap, the unlit will resolve when polls land." I should have decoupled them — the unlit was a separate timing bug (snapshot.valid=false at boot before any poll).
3. **Defaulted to canonical-Winamp layout instead of asking.** Even after the atlas was correct, on-screen position is a UX preference. The canonical Winamp main window has stereo-left, mono-right. The user's preference is the opposite. That's not wrong; that's a choice. I shouldn't have argued with the visual layout via implementation — should have just asked.
4. **Test cycle is expensive when the request is ambiguous.** Each guess cost: edit → bake → build → flash → wait for WiFi + first poll → user observes. ~30–60 seconds. With ambiguity, that's a terrible feedback loop. **Asking one clarifying question costs five seconds.**

**Suggested improvement**: when a user request maps onto a sprite-based feature, default-question is *"do you mean the source atlas, the data → sprite mapping, or the on-screen position?"* Ask before changing. Cheaper than guessing. Also: for any request involving an asset, look at the asset before changing code. The thirty-second image-extract path beats the five-minute reflash-and-test path every single time.

**Status**: open — promotion candidate. Same family as LL-014 (don't blame the network without a positive test): "diagnose before guessing" generalises.

### LL-015 — 2026-05-08 — Optimistic-UI mutations must outlive the same loop iteration

**Context**: M5 implementation. Touch handler set `songStartMillis = 0` to freeze the M4 interpolator on pause-touch and set `requestDueTime = 0` to force-poll. Both inside the same `checkForInput()` call. Bar continued ticking visibly post-pause anyway.

**Observation**: Loop order is `checkForInput()` → `updateCurrentlyPlaying()` → `updateProgressBar()`. The `requestDueTime = 0` triggered an immediate GET in the *same* loop iteration; the GET raced Spotify's pause-commit, re-anchored `songStartMillis` from `is_playing=true`, and `updateProgressBar` at the end of the same iteration resumed ticking. The optimistic mutation got steamrolled before the very next render.

**Root cause**: "Optimistic UI" only works if the optimistic state survives long enough for the user to see it. In a single-task super-loop, "long enough" is at least one render — i.e., the optimistic state must NOT be invalidated by something else later in the same iteration.

**Suggested improvement**: When applying an optimistic mutation, check the loop's downstream code paths for anything that can rewrite the same state in the same iteration. If a force-action (force-poll, force-redraw) is part of the same handler, delay it past the next render or guard the optimistic state against the rewrite explicitly. Tier-1 fix here: defer the re-poll by ~1500 ms instead of firing immediately. Tier-2 (deferred): a `local-state-authoritative-until` window that suppresses poll re-anchoring during the optimistic phase.

**Status**: open — partial fix shipped (deferred re-poll). Promotion candidate.

*Second concrete instance (2026-05-10, TASK-045)*: drag-to-set volume slider exhibits the same risk shape on continuous-touch input rather than single tap. Solved here with a tier-2-style mechanism: `WinampDisplay::optimisticVolumeUntilMs` is set to `now + 2000` on every drag sample, and `spotifyLogic.h::updateCurrentlyPlaying` skips the snap-driven `drawVolume` dedup gate when `millis() < getOptimisticVolumeUntil()`. The optimistic state is now authoritative for a bounded window across loop iterations, regardless of how many polls land in between. ADR-016 §10 captures the decision; the abstraction (`getOptimisticVolumeUntil()` virtual on the display interface) is reusable for any future per-element optimistic-write surface (e.g., scrub-to-seek's progress bar). Promotes the LL-015 suggestion's tier-2 idea into delivered code.

### LL-017 — 2026-05-09 — A library that produces output is more dangerous than one that errors

**Context**: TASK-042. User reported BALANCE.BMP composite was wrong on screen ("thin 2-pixel strip surrounded by cyan"). Four prior rounds of investigation had me adjusting crop coordinates, transparency keys, and on-screen positions — none of which were the actual bug. The bug was that Pillow 11.3.0 silently mis-decodes BI_RLE8 streams that use the delta opcode (`00 02 dx dy`) — ~56 % of pixels in BALANCE.BMP came out at the wrong x coordinates, but `Image.open(...).load()` returned successfully and an `Image` object containing garbage was used downstream as if it were correct.

**Observation**: ImageMagick fails with an explicit error on the same file (`unable to runlength decode`). That's a clean failure — caught instantly, easy to route around. PIL's behaviour is the opposite: success-with-wrong-output. The `try/except (ValueError, OSError)` fallback to magick existed in the bake tool, but never fired because PIL never raised. Every bake produced byte-identical (and consistently wrong) output, so the existing T025 determinism check happily kept passing on garbage.

**Root cause**: my mental model of the decoder was binary — "PIL decodes, or raises." A third state ("PIL decodes wrong, silently") wasn't on my failure-mode list. Once it was, the right action was to *not trust the library* — own the decode in our own 30 LOC, byte-validate against a third-party reference (ffmpeg), and only then trust the output.

**Suggested improvement**:
- For any third-party data-pipeline library handling formats with corner cases (rare opcodes, exotic chroma subsampling, weird metadata), produce a **second independent decode** for the file class actually in use, and assert byte-equality at integration time. If the library disagrees with the second source, treat the library as suspect — don't reach for "must be a config flag we missed" reflexively.
- For binary inputs whose pixels we ship in flash, prefer to **own the decoder for the format subset we depend on**. The maintenance cost of 30 LOC of opcode-walking is much lower than the cost of debugging a silent-corruption bug in production firmware.
- When a fix changes only crop coordinates / placement values without explaining the new pixel data, that's a signal the bug is upstream of the placement layer. Re-check the data extraction before adjusting placement.

Sister rule to LL-014 (don't blame network without a positive test) and LL-016 (look at the asset before changing code). Theme: **diagnose at the actual data, don't accept what a layer above says without independent confirmation.**

**Status**: open — promotion candidate. Process implication: when introducing a library dependency on a data-pipeline path, the ADR for that decision should call out *"how do we know the library produced correct output, not just non-error output?"* — that question wasn't asked in ADR-008 and the silent-corruption bug landed undetected.

### LL-018 — 2026-05-10 — Spec-vs-server divergence is structural, not exceptional (LL-013 v2)

**Context**: TASK-041 (M-CHROME tier 2 dynamic VOLUME) shipped end-to-end at commits b8f37d3..8075176, faithful to ADR-014 Amendment 1. T070a/T070b verification on the DUT (2026-05-10) found `Snapshot.volumePercent` stays at the `-1` sentinel on every successful 200 OK poll, regardless of which Spotify Connect device is active or what its volume is.

The lib parser is correct. The bug is upstream: `/me/player/currently-playing` does **not** include the `device` field at all, even though the OpenAPI spec (`resource/web-api/official-open-api.yaml:4701, 4967-4985`) declares the response shape as `CurrentlyPlayingContextObject` which has `device` as a top-level property. The server returns a subset; the spec describes the union. `device` is only actually returned by `/me/player`.

**Observation**: This is the **second concrete instance** of the same pattern that drove LL-013. First instance (M1 spike, 2026-05-08): the spec said player-control endpoints return 204, server actually returns 200, and the lib's strict `return statusCode == 204` flagged every successful call as failure. Second instance (here): the spec said `/me/player/currently-playing` returns the full `CurrentlyPlayingContextObject`, server returns a subset.

**Root cause**: The Spotify OpenAPI spec models multiple endpoints with the same response schema reference (`CurrentlyPlayingContextObject`) for documentation convenience. The server actually returns *different* shapes for those endpoints. The spec is a description of the *union* of fields any of those endpoints might surface — not a contract any single endpoint guarantees. Treating the spec as a contract for one specific endpoint is the trap.

**Suggested improvement**:

1. **Pre-merge wire capture for any lib-filter patch.** Any ADR or LOCAL_PATCH that depends on a documented field being present in a specific endpoint's response must include a `curl` dump showing the field is *actually* in that endpoint's response, captured against the project's own credentials. 30 seconds of work per patch; would have caught both LL-013 instances at design time.
2. **Treat the OpenAPI spec as an over-approximation, not a contract.** When designing an endpoint consumer, ask "what does the server return for *this specific endpoint*?" and verify, rather than "what does the spec say the response shape is?".
3. **Promote LL-013 + LL-009 to best-practice rules.** Two concrete instances of LL-013, plus the same family as LL-009 (verify endpoint access for the project's actual app, not just the documented API surface). Three data points across the project. Strong promotion case — these aren't isolated mistakes, they're a recurring class.

Sister rule to LL-013 / LL-009 / LL-014 (don't blame the network without a positive test). Theme: **the wire is the source of truth; documentation is one input among many.**

**Status**: open — strong promotion candidate. Process implication: ADR-015 establishes the precedent of including wire capture inline in the ADR's evidence section; subsequent ADRs touching API filters should follow the same pattern.

*Verification evidence (2026-05-10)*: ADR-015's URL change verified end-to-end on the DUT. T073 (host-side wire-comparison) caught the bug class directly in ~3 seconds without needing a flash cycle — exactly the discipline this LL prescribes. T070a / T070b PASS on first attempt against the new endpoint. The 30-second wire-capture step at design time would have prevented this entire investigation cycle.

---

### LL-019 — 2026-05-16 — Implementation specs written before R&D measurements produce high error rates

**Context**: TASK-050a/b/c (M-VIS) were written on 2026-05-16 as detailed implementation specs before any pixel-accurate R&D measurements were taken. R&D reports (M-VIS-spectrum-analysis.md, M-VIS-waveform-analysis.md) landed the same day after the specs were already in tasks.md. The Architect's comparison found 5 wrong values in TASK-050b alone (bar count 38→19, bar width 2px→3px+1px gap, colour method threshold→row-lookup, decay constant 0.008f→0.0625f, peak dot size 1px→3px) and 3 wrong values in TASK-050c (colour TFT_GREEN→white, render method single-pixel→vertical-fill, midline y=49→y=50). None of the wrong values were individually implausible — they were all reasonable from first principles. The aggregate was wrong enough to produce a visibly incorrect result on DUT.

**Observation**: Specs written from memory, analogies, or first principles before measurement are unreliable for pixel-level behaviour. In this case "38 bars" came from halving a round-number estimate; "green/yellow/red threshold colouring" from a generic spectrum convention; "drawPixel per column" from a minimal interpretation of the oscilloscope spec. Each looked reasonable alone. The actual Winamp behaviour (19 bars, absolute-row colour table, vertical fill between samples) was only discoverable by measuring the real renderer. No gate existed to prevent the spec from being treated as authoritative.

**Root cause**: The spec was written in the same session as the R&D was ordered, with the implicit assumption that the spec could be drafted from knowledge and corrected after. The tasks.md format does not distinguish "measured" from "estimated" values, and nothing flagged the spec as provisional while R&D was in flight.

**Suggested improvement**:
1. When a design spec depends on pixel-accurate measurements (vis geometry, colour values, animation rates), mark it explicitly as `[PROVISIONAL — awaiting R&D]` until the R&D report is available. Do not write specific numbers until they are measured.
2. Implementation gates: Developer should not start a task whose spec carries a `[PROVISIONAL]` tag. The R&D measurement must arrive and be incorporated by the Architect before coding begins.
3. This applies especially to any spec derived from observing a third-party renderer (Winamp, Media Player, etc.) — "it looks like X" without frame-by-frame analysis is always provisional.

Sister rule to LL-016 ("look at the asset before changing code") and LL-017 ("a library that produces output is more dangerous than one that errors"). Theme: **measure the ground truth before writing implementation numbers.**

**Status**: open — promotion candidate. First instance on this project; preventive catch (no implementation had started when caught). Strong promotion case for projects with any asset-measurement-dependent feature work.

---

### LL-020 — 2026-05-16 — Derived values in R&D reports must be independently verified before spec adoption

**Context**: M-VIS spectrum colours. The R&D report `M-VIS-spectrum-analysis.md` correctly measured 16 RGB888 pixel values from video frames. It then provided a computed RGB565 column — the values that went into the design doc and the code. All 16 RGB565 values were wrong: the conversion formula was misapplied (e.g. row 0 RGB888=(239,49,16) → correct RGB565=0xE982; report said 0xE903, which decodes to (239,32,24)). The design doc propagated all 16 wrong values verbatim. The code matched the spec correctly. Error caught on DUT visual inspection after flash; fix was a 4-line Python one-liner.

**Observation**: The R&D report contained two kinds of data in the same table: *measured* values (RGB888 — correct, derived from video frames) and *computed* values (RGB565 — wrong, derived by formula from the measured values). Nothing in the table distinguished them. The design doc consumed the RGB565 column as measurement output, not as a derived step that could have its own error. The pipeline was: measure → compute → spec → code — with no verification gate between compute and spec.

**Root cause**: Format-conversion steps inside R&D reports are treated as reporting of facts, not as computations that can contain errors. No convention exists requiring derived values to include the formula used or a verification command. Because both columns were in the same table under the same "measured" framing, the computed column inherited the credibility of the measured column.

**Suggested improvement**:
1. R&D reports must distinguish *measured* values (from direct observation) from *derived* values (computed from measurements). Label columns accordingly.
2. Any derived value that goes into a spec must include the derivation formula or a one-line verification command in the report. For RGB888→RGB565: `python3 -c "r,g,b=239,49,16; print(hex((r>>3<<11)|(g>>2<<5)|b>>3))"`. This makes the derivation auditable in 30 seconds.
3. The Architect adopting derived values into a design doc should run the verification before including the value. If no verification command is provided, flag the R&D report and request one before the spec is finalised.

Sister rule to LL-019 (mark provisional specs before R&D is complete) and LL-017 (a library that produces output is more dangerous than one that errors). Theme: **computed values can silently be wrong; always verify derivations independently.**

**Status**: adopted → BP-001 (2026-05-16)

---

### LL-021 — 2026-05-17 — Bake pipeline parameters lost on rebake (wave_atlas)

**Context**: `wave_atlas` rebaked today to fix a frozen-frames bug (30 identical lead-in frames in source video). A `--frame-start 30` flag was added to `bake_wave.py` and the atlas regenerated. Only `--dc-offset 3` was passed; `--boost 2.0 --spatial-smooth 3 --error-diffusion` were silently omitted. The regression was caught by the user ("did you undo the AE effects?") and corrected immediately, but a full reflash cycle was wasted.

**Observation**: The canonical bake invocation existed only in the `feat(wave): M-WAVE-ATLAS bake pipeline and host preview` commit message body. Nobody consults git log before running a tool. The tool's own `--help` lists flags but gives no indication which combination was used to produce the committed output.

**Root cause**: No machine-readable record of the exact bake invocation is committed alongside the generated artifacts. The artifact (`wave_atlas.c`) is reproducible in principle but the reproduction recipe lives only in narrative prose (commit message), which is not consulted at tool-invocation time.

**Suggested improvement**: For every bake tool that produces committed generated artifacts, commit a companion shell script or Makefile target (e.g. `tools/bake_wave.sh`) containing the exact invocation. The script is the canonical recipe; the commit message may reference it but is not the source of truth. When flags change, the script is updated in the same commit as the regenerated artifact.

**Status**: adopted → BP-002 (2026-05-17)

---

## Retrospective — 2026-05-22 — TASK-021/TASK-066/TASK-067 — tap-to-play queue-clear bug lifecycle

Triggering work: TASK-066 (fix `ACT_PLAY_URI` context_uri wire-up) + TASK-067 (T115/T116 DUT verification). The bug was first observed at TASK-021 close-out (2026-05-16) and re-surfaced by the user on 2026-05-22 (6 days later). Both the fix (5 lines in `spotifyTaskStorage.cpp`) and the DUT regression suite (T115 PASS, T116 PASS) landed on the same day.

### What went well

- **Fix was minimal and targeted.** The `s_lastTrackContextUri` infrastructure was already in place — the bug was a single missing wire in `ACT_PLAY_URI`. Once identified, the fix was 5 lines with no refactoring required.
- **Both symptoms resolved by one change.** Queue-cleared and 5-identical-rows were two manifestations of the same root cause; the single fix resolved both without hunting for a second bug.
- **T116 made fully self-contained.** Adding `_play_adhoc_uri()` to the harness meant T116 required no manual Spotify state setup — the test drives its own precondition via the host API. All future re-runs are automated.
- **Bug was well-documented at deferral time.** The TASK-021 notes and M-LIST-v3 design doc recorded the DUT observation, both symptoms, and both resolution options accurately. The diagnosis cost was low when the bug was revisited.

---

### LL-022 — 2026-05-22 — Known bug deferred as prose caveat without a blocking task

**Context**: TASK-021 (tap-to-play) was marked `done` on 2026-05-16 with a documented caveat: "`playAdvanced` replaces context; queue-aware skip deferred to M-LIST-v3." The fix required — wiring `s_lastTrackContextUri` into `ACT_PLAY_URI` — was already identified in the notes. No separate bug task was filed. M-LIST-v3 was marked "planned" with no scheduled start. The user re-reported the bug on 2026-05-22.

**Observation**: A known, identified, 5-line fix lived unresolved for 6 days because the deferral path ("M-LIST-v3, TASK-051a–f") was not backed by a concrete task with an owner and priority. The bug returned to the user rather than being resolved proactively.

**Root cause**: Closing a task as `done` with a known functional regression in the notes, deferred to a future milestone that has no scheduled work, effectively orphans the bug. There is no mechanism in the current process to surface deferred-bug notes as actionable items.

**Suggested improvement**: When a task is closed with a documented functional regression ("caveat"), a separate bug task must be filed at close time with status `planned` (not buried in the deferred milestone). The bug task should reference the parent task but stand alone in the tracker. Tasks with known un-fixed regressions should not be marked `done`; use `done-with-known-issue(TASK-NNN)` or equivalent, or hold `done` until the bug task is also closed.

**Status**: adopted → BP-003 (2026-05-22)

---

### LL-023 — 2026-05-22 — `injectTouch()` diverged from physical touch path — new actions not mirrored

**Context**: `injectTouch()` (`winampDisplay.h`) is the serial-debug touch injection path used by the VE harness. It was introduced in TASK-056d and mirrors the physical `checkForInput()` touch handler. When TASK-021 added the PLEDIT row-tap branch to `checkForInput()`, the same branch was not added to `injectTouch()`. As a result, any serial `tap X Y` command into the PLEDIT area silently fell through to DEADZONE and dispatched `ACT_FORCE_POLL` instead of `ACT_PLAY_URI`. T115's first run exposed this: `'hit': 'DEADZONE'` for coordinates that should have hit PLEDIT.

**Observation**: The physical touch path and `injectTouch()` are now structurally coupled — any new touch action added to one must be added to the other — but there is no enforcement or checklist for this. The divergence was invisible until a test was actually written and run.

**Root cause**: The `injectTouch()` pattern was introduced to mirror the physical path, but the mirroring requirement was never made explicit in code comments, docs, or a review checklist. New touch-path additions are made in `checkForInput()` without consulting `injectTouch()`.

**Suggested improvement**: Add a co-location comment in `winampDisplay.h` at the top of both `checkForInput()` and `injectTouch()` stating: *"These two methods must be kept in sync. Any new touch-action branch added to one must be mirrored in the other."* Additionally: add to the Developer pre-commit checklist (LL-010 / BP) the item: *"If touching the physical touch path: mirror the change in `injectTouch()`."*

**Status**: adopted → BP-004 (2026-05-22)

---

### LL-024 — 2026-05-22 — "VE: no test suite written" prose notes are not actionable without a task

**Context**: The `feature_inventory.yaml` entry for `playlist-001` carried `test_ids: []` and the note *"VE: no test suite written — action from 2026-05-15 audit."* No VE task was filed for TASK-021 at close-out time. The test gap persisted for 7 days. When T115/T116 were eventually written, the `injectTouch()` gap (LL-023) was also discovered — meaning the test infrastructure itself was defective during that window, so even if tests had been written earlier they could not have run correctly without the `injectTouch()` fix.

**Observation**: Audit findings that identify test gaps ("action from audit") recorded only in prose — in a feature YAML note, not as a VE task in `tasks.md` — have no owner, no deadline, and no mechanism to surface as work. They age silently.

**Root cause**: The team convention is to file tasks for implementation work but to record VE actions as prose annotations. VE actions are treated as lower-priority follow-ups rather than first-class tasks. The `test_ids: []` field visually signals a gap but does not create pressure to fill it.

**Suggested improvement**: Any `test_ids: []` entry in `feature_inventory.yaml` for an `implemented` feature must have a corresponding VE task in `tasks.md` with status at least `planned`. The feature should not reach `done` in the roadmap with `test_ids: []`. PM is responsible for filing the VE task at feature close. VE task must reference the feature ID so it is traceable.

**Status**: adopted → BP-005 (2026-05-22)

---

### LL-025 — 2026-05-23 — Two related gaps: single-state visual sign-off, and PM paraphrase vs. exact-quote for visual bugs

**Context**: TASK-051e (scrollbar thumb blit) was closed on a human eyeball at `scrollOffset = 0`. TASK-077 was filed the same day. The bug was actually an X-axis offset (`thumb_x = rightX + 1`, 4px too far left); the PM agent paraphrased "needs to move a bit to the right" as "Y position wrong" — an axis flip that caused the QM audit to verify the Y formula (correct) rather than immediately fixing the X offset (trivial).

**Observation A — single-state sign-off**: A visual check at one boundary state passes trivially for almost any formula. The actual defect (`+ 1` off in X) would not have been caught even with a correct Y-formula audit because they are orthogonal. The "thumb visible at correct position" sign-off at offset=0 is not a VE gate for any parameter-dependent renderer.

**Observation B — symptom transcription**: The PM agent paraphrased the user's spatial description ("needs to move a bit to the right") into a technical coordinate frame ("incorrect Y position"). Right/left → X axis; up/down → Y axis. The paraphrase introduced an axis error that misdirected the QM audit.

**Root cause A**: No explicit VE exit criterion in TASK-051e. T120 existed but was not linked as a gate. Closure accepted at the easiest single state.

**Root cause B**: PM filed the Symptom field from inference ("this seems like a position problem") rather than quoting the user verbatim. The verbatim quote would have immediately identified the axis.

**Suggested improvement A**: For any renderer whose output is a function of a runtime parameter, the VE gate must cover zero, max, and one intermediate value. Task notes must name the test ID explicitly. "Visually correct at rest" is not a regression guard.

**Suggested improvement B**: PM's Symptom field for visual/UI bugs must include the user's exact quoted wording alongside any technical translation. Quote first, interpret second. If the interpretation changes after clarification, update both fields.

**Status**: open

---

### LL-026 — 2026-05-23 — Reference image available, pixel positions still guessed; human forced to iterate

**Context**: `resource/winamp_reference_cropped.png` was provided at project start and used by R&D during TASK-075 (scroll arrows + thumb sprite identification). Despite this, the thumb's horizontal inset within the scrollbar track was implemented as `rightX + 1` with no derivation — a guess. The value was wrong. TASK-077 was filed (itself misfiled as a Y bug) and required 5+ flash-and-observe cycles with human pixel-level feedback to land on the correct value (`+4`). The reference image was available throughout and could have answered the question directly.

**Observation**: R&D measured *what* the thumb sprite was (BMP x=52, y=54, 9×17) but not *where* it should sit within the 19px scrollbar track on screen. The horizontal inset is visible in the reference image: the thumb occupies the inner portion of the track strip. A one-time measurement at TASK-075 or TASK-051e time would have produced the constant. Instead, the implementation shipped with a magic `+ 1` and the user paid for the error in session time.

**Root cause**: R&D task scope was "identify the sprite" (extract coordinates from BMP), not "specify all rendering parameters" (inset, centering, transparency handling). The gap between "sprite found" and "sprite correctly placed" was not identified as a work item. No one asked: "what is the correct X position relative to the track tile?"

**Suggested improvement**: For every sprite blit introduced by a TASK, the implementation spec must include ALL rendering parameters: X offset, Y offset, transparency key, and — for positioned elements — derivation from a reference image measurement. "Sprite found at BMP (x,y,w,h)" is not a complete spec. If a reference image exists, the spec writer must consult it. If a parameter is truly ambiguous, mark it `[VISUAL CALIBRATION NEEDED]` so it is not silently guessed.

**Structural fix (user direction)**: When a reference image is used as the basis for any rendered element, a paired VE/audit item is required to validate the rendered output against that image. "Reference image consumed → visual validation test" is a mandatory pair, not optional. The test does not need pixel-perfect automation; a manual overlay or side-by-side screenshot comparison is sufficient. Without this gate, an element can ship visually wrong and only human frustration eventually surfaces the error.

**User feedback (direct)**: *"I've had 4 agent sessions getting the slider sprite drawn. It's been an uphill battle. The reference image was given at the start. R&D examined it. And yet I still had to iterate a bunch more times, including using my human feedback on pixel differences — while you have all the resources to make the validation."*

**Status**: open

---

## Best-practice candidates (for human sign-off)

Per AGENTS.md, QM does not self-promote. Below are LL items that look durable enough to become best-practice rules:

- **LL-001** → "ESP32 TLS first-diagnostic = check the clock before anything else." Universally applicable on RTC-less boards.
- **LL-002** → "Credential leak = P0 incident, rotate before next task." Universal.
- **LL-003** → "Audit vendored library debug-log surface for secret output before first flash." Universal for any auth-handling library.
- **LL-005** → "Promote and populate `cross_feature_matrix.yaml` on the first cross-feature link, not the second." Process rule, applies to Developer.
- **LL-008** → "On Arduino-ESP32, do not share a single `WiFiClientSecure` across GET and non-GET requests." Library/integration rule, applies to Developer.
- **LL-009** → "Architecture decisions that depend on third-party API endpoints must verify endpoint access for the project's actual app, not just the documented API surface." Process rule, applies to Architect.
- **LL-010** → "Pre-commit checklist for cross-role hand-offs (Architect / VE / PM / inventory). Skips allowed but must be deliberate." Process rule, applies to Developer.
- **LL-011** → "Any new file under sketch/tools dirs gets a tasks.md entry, even if it doesn't advance a milestone." Process rule, applies to PM (and to Developer at commit time).
- **LL-012** → "Read the source for any sticky-state API named `lastError`, `lastResult`, `state`, etc. before building diagnostic chains on its return value." Library rule, applies to Developer.
- **LL-013** → "When a fix doesn't change a numeric error code, distinguish 'fix failed' from 'next bug in the chain shares the symptom'. Trace request bytes; cross-check spec." Process rule, applies to Developer + Architect.
- **LL-014** → "Network blame for a *consistent* failure mode requires a positive test (curl from host) or a mechanism consistent with other facts. Default-network-blame is banned." Process rule, applies to Developer.
- **LL-015** → "Optimistic-UI mutations must survive the same loop iteration. Audit the downstream code path before shipping; defer force-actions or guard optimistic state explicitly." Architecture rule, applies to Developer.
- **LL-016** → "Look at the asset before changing code; ask which layer (atlas / data-mapping / on-screen position) when 'swap' is ambiguous." Process rule, applies to Developer.
- **LL-017** → "A library that produces output is more dangerous than one that errors. For data-pipeline libraries on the file classes we actually depend on, validate output against a second independent decoder; don't trust no-exception as success." Process rule, applies to Developer + Architect.
- **LL-018** → "Treat the OpenAPI spec as an over-approximation, not a contract. Any lib-filter patch that depends on a documented field must include a wire-capture proof that the field is actually returned by the specific endpoint being patched." Process rule, applies to Developer + Architect. Two concrete instances (LL-013 was the first). Strongest promotion case in the candidate set.
- **LL-019** → "Implementation specs that depend on pixel-accurate asset measurements must be marked `[PROVISIONAL — awaiting R&D]` and blocked from implementation until R&D validates the numbers. First-principles estimates produce high error rates on pixel-level behaviour." Process rule, applies to Developer (implementation gate) and Architect (provisional tagging). First instance on this project; preventive catch.
- **LL-020** → "R&D reports must distinguish measured values from derived/computed values. Any derived value entering a spec must include its derivation formula or a one-line verification command. Architect verifies before adopting." Process rule, applies to R&D Engineer (labelling + formula) and Architect (verification gate). Concrete incident: 16/16 RGB565 values wrong in M-VIS spec; 30-second Python check would have caught it.
- **LL-021** → "Bake pipeline parameters must be recorded in a committed, executable form (shell script or Makefile target), not only in a commit message. Commit messages are not consulted before re-running tools." Process rule, applies to Developer + R&D Engineer. Concrete incident: wave_atlas rebaked with only `--dc-offset 3`; `--boost 2.0 --spatial-smooth 3 --error-diffusion` lost because the canonical invocation only existed in the git commit body. → **BP-002**
- **LL-022** → adopted → **BP-003** (2026-05-22)
- **LL-023** → adopted → **BP-004** (2026-05-22)
- **LL-024** → adopted → **BP-005** (2026-05-22)
- **LL-025** → "Visual sign-off for range-dependent renderers must cover zero, max, and one intermediate value. 'Correct at rest' is not a VE gate." Strong promotion case: same failure mode as LL-024 (test gap at closure) but from the opposite direction — test existed, exit criterion link was missing.
- **LL-027** → "Write `.gitignore` before first `git add` on any new build-tool project directory. For PlatformIO: `.pio/` excluded by default. Build outputs are predictable; exclude them proactively." Process rule, applies to Developer.
- **LL-028** → "Spec steps that name a specific file for a code change must either be verified against the actual codebase or marked `[FILE TBD — confirm at implementation]`. Plausible-but-unverified file paths in specs are silent latent risks for agent hand-offs." Process rule, applies to Architect + PM (spec writers).
- **LL-026** → "Reference image used → paired visual validation item required. Any element rendered from a reference image must have a VE/audit item that validates the rendered output against that image. No reference image consumed without a closing verification step." Strong promotion case: directly addresses a recurring human frustration; cost of the check is low (side-by-side screenshot); cost of skipping is 4+ wasted sessions. Applies to Developer (spec completeness) + VE (validation item creation).
- **LL-029** → "Structural refactors must include a grep-for-old-paths step on moved files, plus a tool-script smoke-test gate (e.g. `python3 -c 'import coords'`) before close. A file move that does not update internal path strings is an incomplete migration. BP candidate — applicable to any project with host-side Python/shell tooling."
- **LL-032** → adopted → **BP-010** (2026-05-25)
- **LL-033** → adopted → **BP-011** (2026-05-25)
- **LL-034** → adopted → **BP-012** (2026-05-25)

---

### LL-027 — 2026-05-24 — `.gitignore` must exist before first `git add` on a new directory

**Context**: M-RESTRUCTURE TASK-083 created `app/` as a new PlatformIO project directory. `git add app/` was run before `app/.gitignore` was written. PlatformIO's `.pio/libdeps/` contains git repos (Seeed_Arduino_NFC), which git staged as embedded repositories with a warning.

**Observation**: The embedded git repos were caught before commit and removed with `git rm --cached`. Recovery required manual intervention. The `.gitignore` was then written and the directory re-staged correctly. Had the commit landed with `.pio/` included, reverting would have required `git rm -r --cached app/.pio/` and a corrective commit.

**Root cause**: The `.gitignore` was created reactively (after seeing the staging warning) rather than proactively (before `git add`). For any directory that runs a build tool, the build tool's output directories are predictable in advance.

**Suggested improvement**: When creating a new build-tool project directory, write `.gitignore` as part of the skeleton step — before any `git add`. For PlatformIO: `.pio/` is always excluded. For any tool that fetches or generates files, audit what it produces and exclude it. Rule: `.gitignore` before `git add`, not after.

**Status**: open

---

### LL-028 — 2026-05-24 — Implementation specs that name a specific file must be verified against actual code structure

**Context**: TASK-083 step 5 stated "one-line canvas rect change in `app/src/main.cpp` shell: `originX` 22 → 0." The actual location of the `originX` assignment is `app/src/winamp/winampDisplay.h:49` (`displaySetup()`), not `main.cpp`. The spec was written before the file structure existed — a reasonable planning shortcut — but the named file was wrong.

**Observation**: No rework resulted (grep immediately found the correct location), but a spec naming the wrong file is a latent risk for agent hand-offs where the receiving agent may not re-verify the file attribution and may either fail to find the symbol or make a change in the wrong place.

**Root cause**: The spec was authored at planning time without being able to verify against the actual implementation. The guess (`main.cpp`, which is the shell entry point) was plausible but wrong.

**Suggested improvement**: If a spec step names a specific file for a change, it must either (a) be verified against the actual codebase before the task is assigned, or (b) be marked `[FILE TBD — confirm at implementation]` so the implementer knows to locate it rather than trust the attribution. Plausible-but-unverified file paths in specs are silent landmines.

**Status**: open

---

### LL-029 — 2026-05-24 — Structural refactors must include a tool-script path audit as a mandatory gate

**Context**: M-RESTRUCTURE (TASK-083) moved the project's tool scripts and generated artifacts from `Spotify-Diy-Thing/tools/` and `Spotify-Diy-Thing/SpotifyDiyThing/gen/` to `app/tools/` and `app/gen/`. The migration was mechanically correct for source files and the build system. However, the tool scripts themselves contain hardcoded path strings referencing their *own* outputs and sibling inputs. These strings were not updated.

Discovered 2026-05-24 during a T102 re-run: the test harness imports `coords.py`, which — at the time — had a stale `pathlib.Path` pointing to `../SpotifyDiyThing/gen/skin_layout.h` (line 9) instead of `../gen/skin_layout.h`. The import crashed immediately, blocking T102.

Further investigation found six additional functional (runtime-breaking) stale paths across four scripts:
- `app/tools/preview_vis.py:65` — `pathlib.Path(__file__).parent / "../SpotifyDiyThing/gen/skin_layout.h"`
- `app/tools/bake_wave.sh:19` — `-o "$SCRIPT_DIR/../SpotifyDiyThing/gen"`
- `app/tools/preview_vis.py:340` — argparse `default="SpotifyDiyThing/gen/skin_preview_animated.gif"`
- `app/tools/preview_wave.py:128-129` — argparse `default` and `help` referencing `SpotifyDiyThing/gen/skin_preview_wave.gif`
- `app/tools/bake_skin.py:773` — `parse_shell_layout(path="SpotifyDiyThing/gen/shell_layout.h")` default arg

Plus docstring/help text staleness in `bake_skin.py:8-9`, `bake_vis.py:7-8`, `bake_wave.py:6-7`, `preview_vis.py:20-22,26-27,32,37-38`.

Note: `coords.py` itself had already been fixed (line 9 now reads `"../gen/skin_layout.h"`) before this retrospective was written, likely as part of TASK-083 step 2. The other files were not fixed in the same pass.

**Observation**: The TASK-083 restructure checklist (step 2) explicitly listed updating `CLAUDE.md` path references but did not include a step to audit and update path strings *inside* the tool scripts being moved. The tool scripts were treated as opaque files to be relocated, not as code containing embedded path assumptions that become wrong when the file's working-context changes.

The `check_build.sh` gate (BP-008) caught compile errors but has no visibility into Python or shell script path correctness. No tool-script smoke test exists that would catch a broken import at restructure time. The first consumer (T102) surfaced the breakage.

**Root cause**: The TASK-083 restructure scope definition treated "move files" as sufficient. Path strings inside scripts are a form of structural coupling between a script and its directory context — equivalent to a `#include` path in C. A file move that does not update internal path strings is an incomplete migration. The checklist had no explicit "grep moved scripts for old path strings" step.

**Suggested improvement**:
1. Any task that moves a file or directory must include an explicit sub-step: grep the moved files for hardcoded path strings referencing the old location. The grep can be one command: `grep -rn "OldPath" movedDir/`.
2. For PlatformIO / tool-script projects, the restructure checklist should include: "run each tool script with `--help` or a dry-run invocation from its new location and confirm no `FileNotFoundError` on import."
3. Path strings in tool scripts should be derived from `pathlib.Path(__file__).parent` (relative to the script file), not from the caller's working directory. A script that uses `"SpotifyDiyThing/gen/..."` as a literal string instead of `Path(__file__).parent / "../gen/..."` is fragile to any invocation from a non-standard cwd.
4. The restructure gate (`check_build.sh`) should be complemented by a `tools/smoke_test.sh` that imports each Python module (e.g. `python3 -c "import coords"`) and runs each shell script with `--help` or `--dry-run`. Absence of this gate is what allowed the stale paths to survive TASK-083.

**Status**: open — six functional stale paths remain unresolved in `app/tools/`. A fix task should be filed (see recommendations in this retrospective).

---

### LL-030 — 2026-05-24 — "Build passes" and "DUT verified" are not the same done criterion

**Context**: TASK-087 was closed with status `done (2026-05-24 — check_build.sh 3/3 pass; DUT flash + smoke test pending)`. The same pattern appeared in TASK-042 and TASK-009: the parenthetical "(DUT ... pending)" is treated as a note rather than a blocking exit criterion. Same pattern: task is marked done when the build is clean, DUT verification left as follow-up.

**Observation**: The "DUT smoke test pending" parenthetical is structurally a known gap dressed as a footnote. Any subsequent reader of the task list sees `done` and moves on. When VE or PM picks up the task later, the pending DUT item is invisible in the status. TASK-087's BUG-1 defect was also missed because the DUT run that would have surfaced it (Clock canvas touch enqueuing Spotify actions) hadn't happened yet.

**Root cause**: The project has no `pending-dut` intermediate status and no enforcement that VE sign-off is required before `done` when a task's own notes include a DUT gate. The build gate (`check_build.sh`) is a hard automated gate; DUT verification is informal. The distinction allows "done" to mean different things in different tasks.

**Suggested improvement**:
1. Add `pending-dut` as a recognised task status between `in-progress` and `done`. A task with a DUT exit criterion goes to `pending-dut` after `check_build.sh` passes; VE updates it to `done` after the DUT run.
2. Any task that lists a "DUT smoke test" in its notes must have that smoke test in its exit criterion, not as a parenthetical.
3. PM should reject `done` status on any task whose notes contain "DUT ... pending" without a VE sign-off comment.

**Status**: open — pattern not yet addressed in process docs. Promote to BP if human approves.

---

### LL-031 — 2026-05-24 — Tests must be updated when a feature adds new hit-zones

**Context**: T088 (DEADZONE positive cases) was written before the taskbar strip existed. When TASK-087 added the 45px taskbar at x≥275, three of T088's test coordinates — corner-TR (319,0), corner-BR (319,239), and 1px-right-chrome (276,58) — moved from genuine dead zones into valid taskbar slots. T088 continued to expect `hit=DEADZONE` for these coords. When run against the new firmware, T088's TASKBAR hits triggered `switchApp()`, contaminating `currentAppId` for T134–T140 (cascade: 5 tests failed, 2 of which were spurious cascades from the corrupted state).

**Observation**: The failure chain — T088 poisons app state → T134–T140 fail with `hit=CLOCK` — was not obviously connected to the new feature. The root cause (stale T088 coordinates now in the taskbar strip) required inspection of the test's coordinate values against the new layout constants. The contamination was silent: T088 itself would have passed its own assertions if we'd only updated the expected values, but the side effect (switchApp) persisted into subsequent tests.

**Root cause**: No checklist item requires updating existing tests when a new feature adds or changes hit-zones. The implicit assumption is that new features add new tests; existing tests are assumed stable. This fails when a new feature claims screen area that existing tests probe as dead zone.

**Suggested improvement**:
1. Any task that adds, moves, or resizes a hit-zone must include a sub-step: "grep `run_serialdbg_tests.py` for coordinates that fall inside the new zone's bounds and update or retire those cases."
2. `T088` specifically should be treated as a live inventory of dead zones, not a static set of coordinates. When a new hit-zone is added to the firmware, T088's coordinate list must be audited and the dead-zone coords that are now inside the new zone must be removed or reclassified.
3. The fix pattern is `_restore_spotify()` (or analogous state-restore helpers) as teardown in any test that may switch the active app as a side effect. Tests that exercise taskbar coords should always restore state before returning.

**Status**: open — sub-step not yet added to task template. Promote to BP if human approves.

---

## Retrospective — 2026-05-25 — TASK-090 — App Interface ABC + AppShell refactor

Triggering work: TASK-090 complete — App ABC (`init/resume/suspend/tick/handleInput`), SpotifyApp + ClockApp classes, `appHandleInput()` gesture loop, B1–B4 fixed structurally, T_BI_01–T_BI_04 VE tests implemented and passing. Production build flashed. Three agent sessions (090a–090g, handoff, 090h VE close).

### What went well (no LL needed, recorded for balance)

- **B1–B4 fixed structurally.** All four TASK-087 post-mortem bugs were consequences of a missing `App` lifecycle interface. The Architect correctly diagnosed this and designed the App ABC to make the bugs impossible rather than patching each symptom. No new bugs introduced; confirmed by the full DUT regression suite.
- **Design doc had executable test sequences.** `app-interface.md §Verification impact` named specific `dbgGet` keys, exact serial commands, and observable assertions for T_BI_01–T_BI_04. VE implemented all four tests directly from the spec without clarification. Correct order: Architect names the observable, VE implements it.
- **Handoff note was precise and actionable.** The `pm(TASK-090): handoff note` commit had a numbered TODO block with exact shell commands. The 090h session executed the full sequence without re-reading conversation history.
- **check_build.sh 3/3 on a 618-line winampDisplay.h refactor.** The build gate caught nothing new — the refactor was structurally clean before hitting the DUT.

---

### LL-032 — 2026-05-25 — VE-written tests must be entered in test_plan.md in the same session

**Context**: TASK-090h: VE implemented T_BI_01–T_BI_04 in `run_serialdbg_tests.py`. All four pass on DUT. `test_plan.md` was not updated; no T_BI entries exist there. Additionally, `app-interface-001` was not registered in `feature_inventory.yaml` despite being the named feature for TASK-090.

**Observation**: The passing test functions exist in the harness. But from an audit perspective, `test_plan.md` is the canonical test registry and `feature_inventory.yaml` is the canonical feature registry. Both are missing entries. A future QM audit will find `app-interface-001` absent from the inventory and T_BI tests with no plan entries, breaking traceability from test to feature.

This is the reverse of LL-024 (VE actions not filed as tasks): here the tests *were* written, but not registered in the canonical artifacts.

**Root cause**: VE task scope was treated as "write the Python functions and confirm they pass." Updating `test_plan.md` and `feature_inventory.yaml` are follow-on steps that belong to the same session but are easy to drop when the DUT is the target and docs feel like overhead.

**Suggested improvement**: A VE task is not complete until:
1. Test functions written and passing.
2. Entries added to `test_plan.md` (feature ID, objective, steps, status per test ID).
3. `test_ids` list in `feature_inventory.yaml` populated for the covered feature.

This extends BP-005: the VE task itself is not `done` until the `test_ids` list is populated. VE owns both the harness code and the inventory/plan updates in the same session.

**Status**: adopted → BP-010 (2026-05-25)

---

### LL-033 — 2026-05-25 — Handoff notes with numbered TODO blocks are reliable inter-session mechanisms

**Context**: TASK-090 spanned three sessions. The 090a–090g session ended with a port disconnect mid-run; T148 status was UNKNOWN. The PM agent wrote a dedicated commit (`pm(TASK-090): handoff note`) containing: current regression status with raw counts and interpretation, a numbered NEXT AGENT TODO block with exact shell commands and expected outcomes, and what hadn't been done and why.

**Observation**: The 090h session executed from the handoff without reading conversation history. All four handoff steps completed in order without ambiguity. The port disconnect was characterised precisely ("T148 was the only failure, now fixed — port disconnected mid-run") which let the next agent interpret the 26/27 count correctly rather than treating it as a regression.

**Root cause**: N/A — positive pattern. Recorded because the format is not documented and should be replicable.

**Suggested improvement**: When a DUT session ends with unfinished verification (port disconnect, hardware issue, test not yet written), write a PM handoff commit before closing:
- Status per numbered sub-task.
- Current regression count with interpretation (which test failed and why, if known).
- NEXT AGENT TODO block: numbered, exact shell commands, expected output.
- Any context the receiving agent needs to interpret partial results.

Format: `pm(TASK-NNN): handoff note — [one-line status]`. Separate commit from the implementation commit.

**Status**: adopted → BP-011 (2026-05-25)

---

### LL-034 — 2026-05-25 — Pre-existing intermittent failures dilute regression signal in the test suite

**Context**: The regression suite has four known intermittent failures: T084, T087, T091, T092 (reconnect race, TLS reset log-line timing). On each full run 1–2 fire. The headline count varies across runs: 26/27, 27/27, 30/31, 29/31.

When T148 was fixed by TASK-090, the first clean run still showed 26/27 — T087 had fired. A reader could not tell from the count whether a new regression was present or a known flake had fired. The agent had to cross-reference which test failed to confirm T148 was actually fixed.

**Observation**: Four intermittent tests in a 31-test suite means P(all-green) ≈ 66% even with zero new regressions. "Not all green" is the expected baseline, not a signal. The suite has lost its ability to say "something new broke."

**Root cause**: No mechanism to distinguish "known intermittent, tolerated" from "new failure, investigate." Every failure looks identical in the results table.

**Suggested improvement**:
1. Tag known-intermittent tests in `run_serialdbg_tests.py` with a comment block: `# KNOWN INTERMITTENT: <reason> <date first observed>`.
2. Optionally add a `[FLAKE]` result category (separate from PASS/FAIL/SKIP) when a known-intermittent test fails. Summary shows "30 passed, 0 failed, 1 flaked" — unambiguous signal.
3. For T084/T091/T092 (reconnect timing): consider `--retry 2` logic for this class so a single timing miss doesn't count as a failure.

Flag to PM to track this as a sub-task under tooling-001 or a standalone task.

**Status**: adopted → BP-012 (2026-05-25)

---

### LL-035 — 2026-05-25 — TFT shared hardware state leaks between apps in multi-app shell

**Context**: M-MULTIAPP step 2 (TASK-087/TASK-090) introduced `ClockApp` alongside `WinampDisplay`, both drawing to a single `TFT_eSPI` singleton. `TFT_eSPI` maintains ~6 process-global state fields: `textdatum`, `textfont`, `textsize`, `textcolor`, `swapBytes`, `cursor_x/y`. ADR-026 defined layering rules (no `appShell.h` in `WinampDisplay`, taskbar hit-testing in shell only) but said nothing about TFT hardware state.

**Observation**: After a Clock→Spotify app switch, PLEDIT playlist rows rendered 2–3 characters off the left edge of the content area and ~2 px above the expected baseline. Bug was triggered by a user-reported visual regression; root-caused by code audit. `ClockApp::drawTime()` and `drawDate()` called `tft.setTextDatum(MC_DATUM)` and returned without resetting to `TL_DATUM`. `drawPlaylist()` called `tft.drawString()` with `MC_DATUM` still active, shifting every row's text left by `textWidth/2`.

**Root cause**: ADR-026 addressed *structural* isolation (dependency direction, hit-testing ownership) but left TFT hardware state as an implicit shared resource with no ownership contract. No convention existed: neither "producer resets after use" nor "consumer asserts at entry."

**Suggested improvement**:
1. **Producer rule**: any function that calls `tft.set*(non-default)` must reset that field to its default before returning. Concrete default: `textdatum` → `TL_DATUM`, `swapBytes` saved/restored (screenLog.h already does this correctly).
2. **Consumer rule**: any rendering function that cares about a specific TFT state field must assert that state at function entry — don't inherit. Both rules together give defense-in-depth; producer-only is insufficient because callers can forget; consumer-only is correct but relies on every new function knowing the contract.
3. Capture this as a binding architectural invariant (ADR-027) so new app authors have a named rule to follow.
4. Code-review checklist item: any `tft.set*()` call that sets a non-default value must have a matching reset in the same scope.

**Status**: open

---

## Retrospective — 2026-05-25 — M-MULTIAPP complete: Matrix, Life, Weather, Crypto apps

Triggering work: TASK-093 (MatrixApp), TASK-094 (LifeApp), TASK-095 (WeatherApp + CryptoApp + dataTask + ADR-029), TASK-096 (canvas full-height fix). All 6 `g_apps[]` slots now filled and DUT-verified.

### What went well (no LL needed, recorded for balance)

- **App ABC paid off immediately.** MatrixApp, LifeApp, WeatherApp, CryptoApp each landed as a clean subclass with no structural friction. TASK-090's design investment was justified by four successive apps that needed no shell rework.
- **`dataTask` pattern required no new architecture.** Mirroring `spotifyTask`'s queue + spinlock pattern let Weather + Crypto HTTP work land without a blocking design review. One pattern, two consumers, no surprises.
- **ADR-029 TLS root CA strategy written upfront.** ISRG Root X1 + GTS Root R4 PEMs were hardcoded before implementation started. No TLS debugging during app work — the ca-cert lesson (LL-001) was applied preventively.
- **Canvas bug caught and fixed same session.** TASK-096 top-half-black regression was identified by user visual inspection and fixed same commit cycle. No deferred regression.
- **Prior audit actions largely resolved.** `app-interface-001` registered in feature_inventory.yaml; T_BI_01–T_BI_04 added to test_plan.md; TASK-091 tagged known-intermittent tests (BP-012). All three RED findings from the TASK-090 audit were closed.

---

### LL-036 — 2026-05-25 — Feature inventory registration recurred as a miss for all 4 new app classes

**Context**: TASK-093/094/095 implemented MatrixApp, LifeApp, WeatherApp, CryptoApp. None of the four features (`matrix-001`, `gol-001`, `weather-001`, `crypto-001`) were registered in `feature_inventory.yaml`. This is a direct recurrence of LL-032 (app-interface-001 missing from inventory, TASK-090) which was adopted as BP-010 in the same session.

**Observation**: BP-010 covers the VE side ("VE task not done until test_ids populated"), but there is no corresponding enforceable rule on the Developer side for the feature entry itself. BP-010 assumes the entry exists; it does not require the Developer to create it. The gap was invisible until this audit — tasks.md entries exist, code is in tree, DUT-verified, but from an audit perspective all four features are unregistered.

**Root cause**: BP-010 was adopted to close the loop after feature implementation; the open loop is that implementation can be completed and committed without a feature_inventory.yaml entry ever being written. The Developer checklist (LL-010) lists inventory update as item (c), but that checklist has no enforcement mechanism.

**Suggested improvement**: Developer's `done` criterion for any task tagged `feature: <id> (new)` must include a `feature_inventory.yaml` entry with `status: implemented`, `git_ref`, `files`, and at minimum `test_ids: []`. This is not optional housekeeping — it is the registration act that makes the feature exist to PM, VE, and QM. A task that ships code without this entry is `in_progress`, not `done`.

**Status**: open — promotion candidate alongside LL-032/BP-010. Together they close both ends: Developer registers at implementation (this LL), VE populates test_ids at test-time (BP-010).

---

### LL-037 — 2026-05-25 — Canvas sub-region inherited from prior design era and not updated when app became standalone

**Context**: WeatherApp and CryptoApp were initially implemented (TASK-095) rendering into `y:116..239` — the bottom half of the 275×240 app canvas. This sub-region originated in an earlier design where these apps were conceived as sharing the canvas with Winamp chrome above. Under the App ABC (TASK-090), each app owns the full 275×240 canvas exclusively. The sub-region constraint was not removed from the implementation when the design shifted. TASK-096 was filed and fixed the same session; the user observed the top half black on DUT.

**Observation**: The implementation was correct relative to an older design assumption that was never explicitly invalidated. Nothing in the task spec or code review surfaced the stale constraint. The bug was only visible on DUT with the screen active.

**Root cause**: Design constraints written for one architecture epoch (shared canvas) survived into a new epoch (standalone apps) because there was no gate asking: "given this app now owns the full canvas, is its coordinate origin still appropriate?" The canvas bounds are a precondition that changed when the App ABC landed, but the implementation was written without re-checking that precondition.

**Suggested improvement**: When an app class moves from a "shared display" context to a "standalone full-canvas" context, the implementation spec must explicitly state the expected canvas dimensions (`x: 0..274, y: 0..239`) as a precondition, not an assumption. VE exit criteria for any new App subclass must include: "app fills the full 275×240 app canvas; no unexplained blank regions at any edge." A `fillRect(0,0,275,240,color)` in `init()`/`resume()` is a useful smoke test of the full extent.

Sister rule to LL-025 (visual sign-off must cover the full range, not a single state). Here the "range" is the spatial extent of the canvas; "correct at the bottom half" is not a full-canvas sign-off.

**Status**: open — promotion candidate.

---

## Retrospective — 2026-05-25 — PLEDIT empty rows (getQueue malloc regression)

Triggering work: user bug report — PLEDIT shows chrome but no track rows during active playback. Root-caused to `malloc(65536)` silently failing on fragmented heap; `onQueue` never called; snapshot stays at `count=0`. Fixed by replacing the bodyBuf approach with a streaming `BlockingChunkedStream` that reads directly from the TLS socket. Two lessons extracted.

### What went well

- **Log-driven diagnosis.** `LOG_D("spotify.queue", "status=200 elapsed=490ms")` without a following `snapshot updated` line uniquely identified the silent return path — no SERIAL_DEBUG build needed.
- **Root cause found before fixing.** Full analysis of three plausible hypotheses (malloc failure, JSON parse error, `onQueue` not called) narrowed to one before any code was changed.

---

### LL-038 — 2026-05-25 — Large heap malloc on ESP32 fails silently when the heap is fragmented

**Context**: `getQueue()` in `SpotifyArduino.cpp` allocated a 65 536-byte `bodyBuf` to accumulate the raw Spotify queue response before passing it to `deserializeJson`. The allocation was introduced by the TASK-065 dechunker fix (2026-05-20) and passed T114 at the time. After M-MULTIAPP added five new App subclasses plus `dataTask` (TASK-087–095), heap fragmentation increased enough that `malloc(65536)` started returning `NULL`. The failure path (`!bodyBuf`) returned `statusCode` (200) immediately, calling neither `onQueue` nor any error log — PLEDIT showed 0 rows every keepalive cycle.

**Observation**: `malloc` returning `NULL` is a contract violation that the caller must handle explicitly. The code did handle it, but silently: it closed the connection and returned the HTTP status code unchanged. From the outside, the call looked successful (status=200, elapsed=490ms). Without a `LOG_W` or `LOG_E` on the failure path, the symptom was indistinguishable from "parse succeeded but Spotify returned 0 tracks."

**Root cause**: Two compounding factors: (1) the fix chose a large heap buffer when a streaming parse would have required only ~10 KB (the filtered doc); (2) the silent failure path made the condition unobservable without source-level knowledge of the code. Neither was caught because T114 passed on less-fragmented firmware — the test verified correct behaviour, but not behaviour under resource pressure.

**Suggested improvement**:
- On ESP32, treat any `malloc` of ≥ 16 KB as a risk point. Prefer streaming/incremental approaches that allocate only the output (filtered result), not the full raw input. `deserializeJson(doc, stream, Filter)` costs ~10 KB vs 65 KB + 10 KB.
- Any `malloc` failure path that returns silently must emit at least a `LOG_W` with `heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT)`, so failures are observable in production logs without a debug build.
- When a fix introduces a heap allocation to solve a correctness bug, file a follow-up note asking: "does this allocation still fit after the next feature wave?" The answer may change as subsystems grow.

**Status**: open — promotion candidate.

### LL-039 — 2026-05-25 — T114 not re-run after M-MULTIAPP; resource-sensitive tests need a re-run trigger

**Context**: T114 was written for TASK-065 and asserts `getQueue() count >= 1` after one keepalive cycle. It passed on 2026-05-21 against firmware `ab3864e`. M-MULTIAPP (TASK-087–095) added five App subclasses and `dataTask`, increasing heap fragmentation. The TASK-065 dechunker fix started failing under the new firmware, producing the same symptom T114 was designed to catch. T114 was never re-run against the multiapp build; the regression was only discovered via a user bug report.

**Observation**: T114 would have caught the regression immediately — its assertion (`count >= 1`) fails when `onQueue` is not called. The test was correct; it was not triggered. No regression schedule existed for "re-run these tests when heap usage or subsystem count increases."

**Root cause**: T114's precondition names a specific firmware commit (`≥ ab3864e`), not a firmware *capability* class. When new subsystems landed, no mechanism asked: "which existing tests are sensitive to system-resource changes and should be re-verified?" The gap is scheduling, not test design.

**Suggested improvement**:
- Tests that exercise resource-constrained paths (heap allocation, stack depth, timing jitter) should be annotated `[RESOURCE-SENSITIVE]` analogously to `[FLAKE]`. A new milestone or significant feature addition (any new FreeRTOS task, large static allocation, or app subclass) should trigger a re-run of all `[RESOURCE-SENSITIVE]` tests as part of the merge checklist.
- T114 specifically: update its precondition from a commit hash to a firmware capability description, and add it to the resource-sensitive re-run list for any future App or task addition.

**Status**: open — promotion candidate. Closely related to LL-034 (VE test gap on App ABC) — the pattern of "test written, not re-run after subsequent changes" is recurring.

---

## Retrospective — 2026-05-29 — StockApp -99 NET ERR: host API test and VE stress test both failed to surface root cause

Triggering incident: user observed "NET ERR -99" on screen while manually cycling range tabs in StockApp chart view. Two existing tools were expected to catch this class of issue and did not. Three lessons extracted.

### What went wrong

- **`test_yahoo_finance_api.py` checked the wrong budget** — used `CHART_BUDGET_B = 8192` for chart fetches, but the firmware uses `DynamicJsonDocument(16384)`. A payload that the test passed could still fail in firmware.
- **The budget model was wrong even if the constant were correct** — the test compares raw HTTP payload bytes against the `DynamicJsonDocument` capacity. ArduinoJson's capacity must accommodate the parsed tree, not just the raw JSON. `http.getString()` also allocates a separate heap `String` before parsing. Neither of these was modelled.
- **T186 stress test took three iterations to work**, and still didn't trigger the failure — queue depth=4 silently drops most taps; "32 taps fired" produced only 4 actual fetches, all D1/D5. Mo1 and Ytd were never exercised under pressure.

---

### LL-040 — 2026-05-29 — Host API test used wrong budget constant and wrong capacity model

**Context**: `test_yahoo_finance_api.py` T_SF_06 checks that chart payloads fit the "DUT budget" of 8192 bytes. The firmware's `fetchStockChart()` uses `DynamicJsonDocument(16384)` — 2× the constant in the test. Additionally, the test measures raw HTTP response bytes, not the ArduinoJson capacity requirement (which is larger than raw JSON due to the parsed-tree representation) nor the peak heap pressure (which includes the `http.getString()` String allocation stacked on top of the document).

**Observation**: The test passed for all ranges including Ytd, giving false confidence. On DUT, the same request may fail because the heap can't satisfy both the `String` and the `DynamicJsonDocument` allocation concurrently, or because ArduinoJson runs out of capacity parsing a complex document.

**Root cause**: The budget constant was written during an earlier design pass and not updated when the firmware was changed to use 16384. The conceptual model ("does the payload fit?") is correct but the operationalisation is wrong — payload bytes ≠ ArduinoJson capacity ≠ peak heap pressure.

**Suggested improvement**:
- `CHART_BUDGET_B` in the test must match `DynamicJsonDocument(N)` in firmware exactly. Owner: Developer updates the constant whenever the firmware doc size changes; host test must cross-reference the firmware value (comment citing the source line).
- The payload size check should apply a safety factor (≥ 1.5×) to approximate ArduinoJson tree overhead. A comment should explain why.
- Eliminate the intermediate `String` in firmware: replace `deserializeJson(doc, http.getString())` with `deserializeJson(doc, http.getStream())`. This removes the double-allocation (no `String` heap cost) and makes the host budget check more accurate.

**Resolution (2026-05-30)**: The ADR-034 `getStream()` fix (already landed) plus a JSON filter (`StaticJsonDocument<128>` filter + `StaticJsonDocument<2048>` doc) made raw payload bytes entirely irrelevant for chart fetches — only the non-null `close[]` point count matters. `CHART_BUDGET_B=16384` removed; replaced with `CHART_MAX_POINTS=110` mirroring `chartPoints[110]` in `StockAppState` and the `if (r.len >= 110) break` cap in firmware. T_SF_06 now counts non-null `close[]` entries and asserts `<= 110`. `QUOTE_BUDGET_B=8192` retained — quote fetch has no filter so raw bytes vs `DynamicJsonDocument(8192)` remains correct. Committed `50ce839`.

**Status**: adopted → BP-015 (2026-05-30).

---

### LL-041 — 2026-05-29 — ESP32 stress test assumed "taps fired = fetches executed"; queue depth not accounted for

**Context**: T186 fires 32 taps (8 rounds × 4 tabs) to stress-test rapid range switching. The dataTask queue depth is 4. After the first 4 enqueues, all subsequent taps are silently dropped (`LOG_W "queue full — dropped"`). The 30s drain window captured only 4 chart fetches — all D1 or D5. Mo1 and Ytd (the ranges most likely to exhaust heap) were never executed.

**Observation**: The test reported PASS because `fetchFailed` was not set for the 4 fetches that did run. The stress condition the test was designed to create (heap pressure from back-to-back fetches of large ranges) was never actually reached.

**Root cause**: The test was designed from the tap side ("fire N taps") rather than from the fetch side ("confirm N fetches actually executed"). The queue-depth limit is a firmware constant that the VE should consult when designing throughput stress tests. No assertion on the number of actual fetches was made.

**Suggested improvement**:
- Stress tests targeting a queue-backed task must assert on *completed* fetch count (e.g. `lastChartFetch` counter advancing), not on *commands fired*. A stress test that can't verify its own load level has unknown coverage.
- VE should read the firmware's `xQueueCreate(depth, ...)` call when designing queue-driven tests. If queue depth < intended rounds, either reduce round rate to let the queue drain between rounds, or accept that only `depth` concurrent fetches will run and size ROUNDS accordingly.
- For coverage of all ranges under pressure: send one tap per range, wait for the fetch counter to advance, repeat — rather than firing a burst that floods the queue.

**Resolution (2026-05-30)**: Added `fetchOkCount` monotonic counter to `StockAppState` (incremented on every successful chart parse in `stockTickChart()`; exposed via `get`/`set` serial commands). Replaced `_wait_chart_enqueue()` (enqueue proxy via `lastChartFetch`) with `_wait_chart_complete(before)` which polls `fetchOkCount` until it advances past a pre-tap snapshot — proven HTTP+parse completion, independent of queue depth. T186, T187, T188 all updated: snapshot → tap → assert count advanced. Blind 35 s sleep eliminated. Constraint is now structurally enforced by the counter, not by the test author's knowledge of queue depth. Committed `6c3c70f`.

**Status**: adopted → BP-013 (2026-05-30).

---

### LL-042 — 2026-05-29 — VE stress test took three implementation iterations due to serial port contention assumptions

**Context**: T186 was written three times before it ran correctly. Iteration 1 polled `fetchFailed` inside the tap loop — the DUT was too busy to answer serial queries in 3s. Iteration 2 used a background `threading.Thread` to collect log lines while `cmd()` ran concurrently — the thread consumed JSON ACKs from the serial stream, causing the same timeout. Iteration 3 separated the test into three serial phases (setup with generous timeouts / fire-and-forget taps / stream-read drain) and worked.

**Observation**: The serial port is not a concurrent resource. Any test design that reads from `dut.ser` on two threads simultaneously will produce intermittent ACK loss. This is a structural constraint of the harness, not a timing issue that can be fixed with longer timeouts.

**Root cause**: The harness's `Dut.cmd()` and `Dut.read_json()` assume exclusive ownership of the serial stream. When a background thread also reads from `dut.ser`, ACKs intended for `cmd()` are silently consumed. The constraint was not documented.

**Suggested improvement**:
- Add a note to the `Dut` class header: "Serial stream is not thread-safe. Never read `dut.ser` from a background thread concurrently with `cmd()`/`read_json()`."
- For tests that need to both send commands and collect asynchronous log lines: use the fire-and-forget + drain-phase pattern (send → don't wait for ACK → read stream directly → flush → query state). Do not use threads.
- DUT queries inside hot-firing tap loops should be avoided entirely; always post-check after a drain window.

**Resolution (2026-05-30)**: `Dut.__init__` now captures `_owner_thread = threading.current_thread()`. `_assert_owner()` is called at the top of `send()`, `read_json()`, and `drain_log_lines()` — any cross-thread access raises `RuntimeError` immediately with a LL-042 reference rather than silently consuming ACKs. The constraint is now machine-enforced at the call site, not reliant on documentation. Committed `6c3c70f`.

**Status**: adopted → BP-014 (2026-05-30).

### LL-043 — 2026-05-30 — VE agent spent first 10 minutes diagnosing a wrong DUT state claim before running any tests

**Context**: TASK-112 VE rerun. PM handoff stated "DUT is running a May 30 2026-06:39:34 debug build (aquarium agent flashed it)." The prior session was the aquarium CRAB-FIX-011–014 agent, which would have flashed the production target (`cyd2usb_winamp`) for visual verification — the debug target was never relevant to that work. The build timestamp in the heartbeat matched, which looked like confirmation.

**Observation**: The DUT had production firmware (`cyd2usb_winamp`, no `SERIAL_DEBUG`). The VE agent's first test run failed with `set cooldown 0 failed: {'ok': False, 'error': 'unknown command', 'cmd': 'set'}`. Diagnosing this required tracing through firmware source to distinguish `unknown command` (command not in `kCmds[]` at all — implies no `SERIAL_DEBUG`) from `unknown var` (command found, variable not found — implies debug firmware running but variable not registered). The agent correctly identified the root cause and reflashed the debug build, but consumed ~10 minutes and multiple tool calls before the first real test ran. The user notes this is a recurring pattern — prior agents have hit the same wall.

**Root cause**: Two compounding factors:
1. **Stale DUT state in handoff**: The prior agent (aquarium) flashed production firmware for its own testing, left the DUT in that state, and the PM handoff did not verify the build type — it inherited the claim from context. Build timestamps match between production and debug builds (same source, same date), so the heartbeat `build=May 30 2026-06:39:34` gave false confidence.
2. **No explicit SERIAL_DEBUG probe at harness startup**: `run_serialdbg_tests.py` connects, waits for DUT ready, then runs tests. It never explicitly checks that debug-only commands are available. The smoke check (T169) exercises `set cooldown 0` but the failure message is ambiguous to an agent without firmware-source context.

**Suggested improvement**:
1. **Harness-level preflight**: Add a `_verify_debug_firmware()` step to `Dut._wait_for_ready()` or as the first step in `main()`. Send `get heap` and check the response. If `ok: false, error: "unknown command"` → raise `RuntimeError("Production firmware detected — SERIAL_DEBUG not active. Reflash cyd2usb_winamp_debug before running tests.")`. This makes the diagnostic self-contained in ≤1s with zero firmware-source knowledge required.
2. **PM handoff: always state the flash command used**: The PM handoff should record the exact `pio run -e <ENV>` command the prior agent ran, not just the build timestamp. `cyd2usb_winamp` (production) vs `cyd2usb_winamp_debug` is the critical distinction.
3. **Agent briefings: treat DUT state as unverified**: Any briefing note that says "DUT is running X" should be treated as a *claim to verify*, not a *fact*. The first VE step should be preflight verification regardless of what the context says.

**Resolution (2026-05-30)**: `Dut._verify_debug_firmware()` added to `run_serialdbg_tests.py` — called at end of `__init__` after `_wait_for_ready()`. Sends `get heap`; raises `RuntimeError` with exact reflash commands if `unknown command` is returned. BP-017 adopted; PM handoff guidance added to the BP.

**Status**: adopted → BP-017 (2026-05-30)

---

### LL-044 — 2026-05-31 — Mechanism written but only exercised in debug path — never fires in production

**Context**: Touch UX design review (ADR-035 / M-TOUCH-UX). `touchScreenCoolDownTime` in `winampDisplay.h` is set by three handlers (VIS: 300 ms, Shuffle: 250 ms, Repeat: 250 ms) with correct, intentional durations. The variable had been in the codebase through multiple shipping milestones.

**Observation**: The variable is only checked inside `#ifdef SERIAL_DEBUG injectTouch()`. In every production build the check never executes. Users reported VIS cycling was too easy to skip past — the 200 ms shell cooldown (not the intended 300 ms) was the only gate. The bug was undetected because SERIAL_DEBUG tests ran the intended path; no test exercised the production path specifically.

**Root cause**: The guard (`if (millis() <= touchScreenCoolDownTime)`) was placed in the debug-injection path rather than in the production hot-path (`handleWinampInput()` Phase 2). Because the mechanism worked correctly under `injectTouch()`, it was never flagged as incomplete.

**Suggested improvement**: When adding a new timing gate or rate-limiter, verify the check lives in the path that production code actually executes — not only in a test-injection shim. A single comment at the write site (`touchScreenCoolDownTime = millis() + 300; // checked at Phase 2 top`) is cheaper than rediscovering the gap later.

**Status**: open

---

### LL-045 — 2026-05-31 — ADR and design doc drifted after VE-driven design change

**Context**: Touch UX design review round 2 (ADR-035 / M-TOUCH-UX). VE-CH2 changed the SpotifyApp signal chain: the original `wasLastInputAsync()` direct return was replaced by `_actionDispatched && spotifyTask::hasPendingActions()`. M-TOUCH-UX.md was updated in the same pass. ADR-035 Decision 4 was not.

**Observation**: Developer review (DEV-01) caught the divergence: M-TOUCH-UX described the new chain; ADR-035 still described the old one. A reviewer reading only the ADR would have implemented the wrong chain.

**Root cause**: The design revision was made in M-TOUCH-UX (the detail doc) while the ADR (the decision record) was treated as already-settled and not revisited. Two docs for the same decision with no enforced sync point.

**Suggested improvement**: After any design revision driven by a review finding, update both the ADR and the design doc in the same edit pass before closing the finding. Treat "update ADR" as a mandatory step of resolving a decision-level finding — not an optional follow-up. A checklist item on the review template would enforce this.

**Status**: open — second incident recorded under LL-046 (same root cause; code change during VE run). Escalate to BP.

---

## Retrospective — 2026-05-31 — TASK-114–118 (M-TOUCH-UX: hitbox + debounce + busy indicator)

Triggering work: full M-TOUCH-UX milestone — hitbox.h primitive (TASK-114), shell busy indicator infrastructure (TASK-115), SpotifyApp + StockApp integration (TASK-116), SERIAL_DEBUG deliverables (TASK-117), VE execution (TASK-118). Six commits across five phases. TASK-118 partially closed; two items (T-CDWN-02 re-run, T-BUSY-04 manual) remain open.

### What went well (no LL needed, recorded for balance)

- **Phase-gated delivery worked.** Each of the five implementation phases had an independent exit criterion (build, flash, smoke). No phase produced a regression that blocked the next. The amber indicator came up correctly on the first DUT flash.
- **Design review round paid off.** VE + Developer pre-implementation challenges (DEV-01..05, VE-CH1..CH3) caught five specification gaps before any code was written — `mutable` keyword, thread-safety for `_actionPending`, timer-reset guard on Move events, file list, and ADR sync. Five changes cheaper than five bugs.
- **VE automated 7 of 9 exit criteria.** T-BUSY-01/01b/02/03/05 and T-CDWN-01/03 all executed by the harness without manual observation. Only T-BUSY-04 (auto-clear with network-blocked DUT) is genuinely manual by design.
- **Simplification caught under test, not after shipping.** The `_actionDispatched` / `wasLastInputAsync()` chain (4 files, mutable flag, two-hop signal) was simplified to a direct `spotifyTask::hasPendingActions()` query during TASK-118 — before the task closed. The simpler code is in the tree; the complex design stayed on paper.
- **Harness fix was harness-only.** T076/T079/T081 failures were correctly diagnosed as a harness gap (no poll-for-idle between taps), not a firmware defect. The gate itself (shellBusy blocks sequential canvas taps) was correct and intentional.

---

### LL-046 — 2026-05-31 — Sequential-tap tests need poll-for-idle when a busy gate exists on the tap path

**Context**: TASK-118 VE execution. T076 (hit-zone boundary sweep, 8 taps) and T081 (transport suite, 5 taps) ran sequential `cmd tap` calls with only `set_cooldown_zero()` between them. After TASK-117 wired `g_shellBusy` into `cmdTap` (correct — T-CDWN-02 requires it), any transport tap that enqueues a Spotify action sets `g_shellBusy=true`. The next tap in the sweep arrived while busy was still true and was returned as `skipped:true, hit:CANVAS` — a test failure for the wrong reason.

**Observation**: T076/T079/T081 were written for a world where `cmdTap` had no busy gate. The gate was a new constraint added by TASK-117. No one checked whether existing tests remained valid under the new gate. The harness fix (`_poll_shell_busy(False)` before each tap) was mechanical and correct, but the gap between "gate added" and "existing tests audited" was never closed.

**Root cause**: Existing tests are not systematically re-evaluated when a new tap-path gate is introduced. The gate is an implicit precondition for every `cmd tap` call; existing tests inherited an undocumented precondition mismatch.

**Suggested improvement**: When a new gate is added to the `cmdTap` path (busy gate, cooldown gate, app-state guard), treat it as a breaking change for existing sequential-tap tests. The Developer or VE adding the gate must grep `run_serialdbg_tests.py` for bare `dut.cmd("tap ...")` calls that do not precede the tap with an idle-wait, and add `_poll_shell_busy(dut, False)` (or equivalent) where needed. This is a subset of BP-004 (mirror physical-touch path in inject path) applied to the harness level.

**Status**: open — promotion candidate.

---

### LL-047 — 2026-05-31 — Intermediate dispatch flag was unnecessary; terminal signal was directly observable

**Context**: TASK-116 implemented `SpotifyApp::hasPendingAsync()` as `_actionDispatched && spotifyTask::hasPendingActions()`. `_actionDispatched` was a `mutable bool` in SpotifyApp, set when `wasLastInputAsync()` reported an async dispatch, cleared when the queue drained. `WinampDisplay._lastInputWasAsync` was a per-call bool set at all async dispatch sites. The design required: two new state variables across two classes, `wasLastInputAsync()` checked after both Press and Release delegate calls, `mutable` qualifier on the flag, and `suspend()` to reset it.

During TASK-118 VE, the Developer recognised that `spotifyTask::hasPendingActions()` is the authoritative, self-clearing signal: the queue is non-empty exactly when a user action is in flight. The `_actionDispatched` gate added no information — it only filtered "was there ever a dispatch since the last reset," which is always true when the queue is non-empty and false when it is empty (the same condition the queue reports directly). The entire two-hop chain was replaced with one line.

**Observation**: The design introduced an intermediate tracking variable because the design assumed WinampDisplay's per-call async signal was the only available hook into "did an async dispatch happen." The queue-level signal was already present and directly observable, but was not considered as the primary signal during the review.

**Root cause**: Design reviews focused on "how does the shell know a tap dispatched async work" (signal path up from WinampDisplay) rather than "what is the authoritative source of truth for async work in flight" (spotifyTask queue). The authoritative signal was always one call away. The per-call `_lastInputWasAsync` approach was designed for a world where the queue might have other callers; in practice the queue is exclusively user-initiated, making the queue depth a direct proxy for "user tap in flight."

**Suggested improvement**: Before designing a signal chain to propagate state from a component (WinampDisplay) up through layers (SpotifyApp → shell), ask: "is the terminal state already queryable at the point of consumption?" If `hasPendingActions()` on the task is observable at SpotifyApp scope, prefer `return spotifyTask::hasPendingActions()` over any intermediate flag. The intermediate flag earns its keep only when: (a) the terminal signal is not accessible from the consumer, or (b) the consumer needs "was async dispatched at all" independently of whether it has drained. Neither applied here.

**Status**: open.

---

### LL-045 recurrence note — 2026-05-31 — Code change during VE run left both ADR and design doc stale

**Context**: LL-045 (filed today, same session) describes ADR/design doc drift after a VE-driven design change. This is a second incident of the same root cause: the `_actionDispatched` simplification made during TASK-118 was a code change, not a design-review finding, but it had the same outcome — both ADR-035 and M-TOUCH-UX.md described the old chain after the code was live. The fix was made same-session (afe35b6) but only after the retro surfaced the gap.

**Observation**: LL-045 was filed as an open lesson with a suggested improvement ("update ADR in the same edit pass as the design doc"). That improvement was not applied here because the code change happened during a test run, not a formal review pass. The suggested improvement is correct but only covers review-driven changes; it does not cover implementation-driven simplifications.

**Root cause addition to LL-045**: Doc drift is not limited to review rounds. Any code change that contradicts a named design decision (ADR or design doc) — including simplifications discovered during implementation — must trigger a doc sync before the commit that makes the change. The rule is: "code and doc always agree at commit boundary."

**Suggested improvement (extension to LL-045)**: The sync rule must apply to implementation-driven changes as well as review-driven changes. Add to the Developer checklist (LL-010): "if this commit changes an interaction described in an ADR or design doc, update the doc in the same commit." The git diff is the enforcement point — if an ADR is named in the commit context but not in the diff, that is a flag.

**Status**: escalate to BP together with LL-045. Two incidents of the same root cause, two days apart, same codebase.

---

## Entry Format

```
### LL-001 — [YYYY-MM-DD] — [Topic]
**Context**: What was happening at the time
**Observation**: What went wrong or what worked well
**Root cause**: Underlying reason
**Suggested improvement**: Actionable change
**Status**: open | reviewed | adopted | dismissed
```