# ADR-010 — Multi-role review

> Date: 2026-05-07
> Reviewers: @VE, @Developer, @QM, @PM
> Outcome: ADR-010 amended (see "Architect responses" + the amendment block at the end of ADR-010 itself). TASK-016 split per @PM.

---

## @VE — testability

1. **Ringbuffer + `/log`.** Need explicit test points. Suggest:
   - **T036** unit (host or DUT): inject 200 log lines of varying length; assert `/log?n=80` returns the last 80 in order; assert wrap doesn't tear lines (every line null-terminated, no truncation in the middle of a UTF-8 sequence).
   - **T037** unit: `/log?clear=1` empties the buffer; subsequent `/log` returns 0 lines.
2. **Secret redactor.** Pure unit, host-runnable if `redact()` is in a header without Arduino deps. **T038**: `redact("AQ…verylong…IY") == "AQ…IY (len=131)"`; `redact("")` returns a non-empty marker; `redact(nullptr)` is safe.
3. **Decoder macros.** Pure unit. **T039**: golden table — every code in the decoder set returns the documented string; an unknown code returns the raw hex/integer (no silent loss).
4. **Heartbeat cadence.** **T040** DUT integration: monitor for 5 minutes, assert ≥9 lines tagged `hb` arrive at 30 ± 5 s spacing, all parse as `key=value` pairs.
5. **Migration policy enforcement.** "Incremental with carve-outs" is opt-in by review only. Recommend a `tools/audit_log_hygiene.sh` script that greps for banned patterns (`Bearer `, `client_secret=`, `Serial.print*` of variables named `*token*` / `*secret*` / `*refresh*`). Tier 1 must include this script — otherwise the secret-hygiene guarantee survives one careless commit.
6. **`/log` exposure.** ADR says "no auth, LAN-only, document it." Tighten: require the listener bind to `WiFi.localIP()` explicitly, not `0.0.0.0`. Untestable today, but documented invariant.

## @Developer — implementability

1. **`esp_log_set_vprintf` is process-wide.** Confirmed: system tags (`wifi`, `mbedtls`, `HTTPClient`, `ssl_client`, `esp_https_ota`) flow through the hook. They obey `esp_log_level_set` per-tag — so the WARN-floor for vendored tags is enforceable.
2. **Spinlock choice.** ADR says `portMUX_TYPE`. ESP-IDF logging can fire from ISRs (rare but real). Use `portENTER_CRITICAL_SAFE` / `portEXIT_CRITICAL_SAFE` for both — works in task and ISR context. Cost: identical in non-ISR, free safety.
3. **Web server lifetime.** Existing server is WiFiManager's portal + the `refreshToken.h` page. Both shut down once setup is complete. **The `/log` endpoint needs a permanent post-connect server**, not the portal-mode one. ADR should call this out as a tier-1 deliverable, otherwise `/log` is only available before the device finishes onboarding — useless.
4. **Heartbeat plumbing.** Super-loop tick (per ADR's "lean") fits the existing single-task structure. `millis()` gate, no FreeRTOS task. ~3 lines.
5. **SRAM budget.** 12 KB `.bss` ringbuffer is comfortable; current free heap on cyd2usb_winamp is ~250 KB. Watch for the line cap (256 chars): JSON URLs from Spotify can exceed it — truncation with "…" is the right call, but log a one-time WARN if it ever happens.

## @QM — lessons-learned crosswalk

1. **LL-002 / LL-003** (secrets in serial logs). Tier 1 commits the redactor *and removes the `configFile.h` JSON dump* in the same change. ADR says this. Recommend the commit message lead with the security-fix framing so it's grep-able for an audit.
2. **LL-010** (multi-role protocol skipped). This review is the corrective step — but ADR-010 reached `accepted` *before* it. Going forward, **no ADR transitions to `accepted` without a `@VE` testability pass and a `@Developer` implementability pass**. Candidate for promotion to `best_practices.md`. Flagging for human approval.
3. **LL-011** (dev-facing infra not in PM tracker). The `/log` endpoint is dev infra; ensure a `feature_inventory` entry for `log-001` lands with the first implementation commit, not later.
4. **New risk: DEBUG default ships to users.** ADR ships `display`, `spotify`, `time` at DEBUG. Fine for active development; but at M3/M5 close, lift to INFO. Track as a calendar reminder, not a forgotten knob. Add to TASK-016 follow-ups.
5. **New risk: `/log` is unauthenticated on the LAN.** Acceptable per ADR; QM agrees so long as the device's IP is dev-environment-only. The moment this firmware ships beyond a dev unit, revisit.

## @PM — scheduling / scope

1. **Split TASK-016.** Currently one bucket; should be four sub-tasks because (b) is independently shippable and security-relevant:
   - **TASK-016b** — secret redactor + remove `configFile.h` JSON dump. **Highest priority**, ships independently.
   - **TASK-016a** — `esp_log` hook + ringbuffer + `/log` endpoint + permanent post-connect server.
   - **TASK-016c** — TLS / HTTP decoder macros.
   - **TASK-016d** — heartbeat tick.
2. **M-LOG must not block M3 verify.** This review confirms M3 (TASK-015) is independent of M-LOG. Continue M3 DUT verification on the current logging surface.
3. **Estimate.** Architect ballpark: 016b ≈ 1 hour. 016a ≈ 3–4 hours (ringbuffer + endpoint + server lifetime fix). 016c ≈ 1 hour. 016d ≈ 30 min. Tier 1 total ≈ half a day.
4. **Audit script (per @VE).** Add as TASK-016e, shipped with or before 016b. ~30 min.

---

## Architect responses

| Concern | Response |
|---|---|
| @VE 1–4 | Test points T036–T040 accepted. VE owns the test_plan entries. |
| @VE 5 | Audit script accepted as TASK-016e. Required for tier 1. |
| @VE 6 | Bind to `WiFi.localIP()` is now an ADR invariant. |
| @Dev 2 | Spinlock changed to `portENTER_CRITICAL_SAFE` in ADR amendment. |
| @Dev 3 | Permanent post-connect HTTP server added to tier 1 deliverables. |
| @Dev 5 | One-time WARN on line truncation accepted. |
| @QM 2 | Promotion candidate flagged: "ADRs require @VE+@Developer review before accepted." Awaiting human approval. |
| @QM 4 | Level-lift follow-up tracked at end of TASK-016. |
| @PM 1 | TASK-016 split into 016a/b/c/d/e. 016b ships first. |
| @PM 3 | Estimates recorded in tasks.md. |

No material change to ADR-010 decisions 1–9; amendments are corrections (spinlock kind, `WiFi.localIP()` bind, permanent server, line-truncation WARN, audit script). Tier-1 scope unchanged.
