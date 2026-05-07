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