# Audit Log

> Owner: Quality Manager

All audits: scope, findings, actions, status.

### Audit — 2026-05-09 — TASK-042 process-skip retrospective (silent BMP-decoder corruption)

**Triggered by**: user (`@AGENTS.md how much of the process was skipped`)

**Areas checked**:
- [x] Was the fix scoped through PM (tasks.md entry before edits)?
- [x] Was the bake-tool dependency change reviewed against the existing ADR?
- [x] Were VE regression tests added before close?
- [x] Were lessons-learned + audit-log entries written before commit?
- [x] Was the multi-role review pre-implement step (LL-010) honoured?

**Findings**:

1. **TASK-042 was edited and run on disk before any tracking artefact was created.** The bake_skin.py change to add a manual BI_RLE8 decoder was made directly, the bake re-ran, the user confirmed visually — all before a TASK-### was opened, before ADR-008 was reviewed, and before VE was given a chance to challenge the testability of the fix. The team-review workflow described in `AGENTS.md` was bypassed entirely. Same shape as the issue captured in LL-016 (mono/stereo swap done solo without looking at the asset first); different surface (tooling, not chrome) but same root cause: solo-agent fast path skipped team checks.

2. **ADR-008 decision #8 was factually wrong from the day it was written, and not detected for two days.** It said: "Pillow's BI_RLE8 BMP decoder fails on Winamp's `TEXT.BMP` (raises `ValueError`). Tool falls back to `magick`." The "raises" framing implicitly modelled PIL as binary-success-or-error. Decision #8 didn't ask the question "how do we know PIL's output is *correct*, not just non-erroring?" — and so the silent-corruption mode for BALANCE.BMP shipped undetected through the M-CHROME tier 2 work. ADR-008 Amendment 1 corrects this; LL-017 captures the general principle.

3. **The existing T025 determinism check kept passing on garbage.** Byte-identical bake-to-bake is a necessary condition for correctness, but not sufficient. The PIL-broken decode was deterministically wrong: every bake produced the same wrong bytes, golden hash matched, and the test gate stayed green. Determinism without a separate ground-truth check is just stable-corruption. T071 + T072 (added 2026-05-09) plug the gap by validating against a second decoder (ffmpeg) and asserting positive content (green pixels in the balance bar).

4. **Magick fallback was load-bearing in name only.** ADR-008 listed magick as a hard dep on the bake step. For BALANCE.BMP, magick rejected the file outright with `unable to runlength decode`. The fallback never triggered because PIL never raised. So neither path actually decoded the file correctly until the manual decoder went in. The dependency was paying for the wrong failure mode.

5. **Build artefacts — green** on the fix. `python3 tools/bake_skin.py -i ../skins/base-2.91.wsz -o ../SpotifyDiyThing/gen` runs clean; per-element `gen/composite/balance_bar_frame0.png` now contains the canonical Winamp green slider track (rows y=3-7), confirmed via per-row pixel summary against ffmpeg's decode (byte-identical).

6. **Stale `gen/golden.sha256`.** SKIN_MAIN_BG[] bytes changed (correct content now). T025 will fail until VE regenerates the golden. Not regenerated yet — pending visual sign-off from user that the new bake is correct (open `gen/skin_preview.png` + `gen/composite/balance_bar_frame0.png`).

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Open TASK-042 in tasks.md | PM | this commit |
| Amend ADR-008 (decision #8 superseded) | Architect | this commit |
| Add T071 (manual decoder vs ffmpeg) + T072 (positive-content green-pixel assertion) to test_plan.md | VE | this commit |
| Mark T028 superseded (magick-fallback test no longer load-bearing) | VE | this commit |
| Regenerate `SpotifyDiyThing/gen/golden.sha256` after user visual sign-off | VE | this commit |
| Add LL-017 to lessons_learned.md | QM | this commit |
| Promote LL-017 once a second project sees the same class of bug | human | candidate, deferred |
| Future ADRs touching data-pipeline libs MUST answer "how do we know the library produced *correct* output?" | Architect | discipline rule |

**Resolution**: closed (2026-05-10). User visually confirmed the new bake (green balance bar visible in `gen/composite/balance_bar_frame0.png`). `gen/golden.sha256` regenerated; `sha256sum -c golden.sha256` passes both files. Determinism re-verified by a second bake → identical hashes. Process artefacts committed: PM (TASK-042 in tasks.md), Architect (ADR-008 Amendment 1), VE (T028 superseded; T071 + T072 added; golden regen), QM (LL-017 + this audit row). Future ADRs touching data-pipeline libs are expected to answer the *"how do we know the library produced correct output?"* question — discipline rule, no specific ticket.

---

### Audit — 2026-04-28 — Session-end self-audit (ADR-006 + M0 close + M1 spike + time-001)

**Triggered by**: human ("do retrospective, what went well, what could be done better")

**Areas checked**:
- [x] Feature inventory completeness (features in code not in inventory)
- [x] Test coverage per feature (implemented features with no test_ids)
- [x] Cross-feature test coverage (interactions with no test_coverage)
- [x] Documentation currency (docs lagging behind code)
- [x] Secret-hygiene posture
- [x] Build artefacts in sync with source (both PlatformIO envs)

**Findings**:

1. **Inventory completeness — minor gap.** All in-tree features have entries: `deploy-001`, `auth-001`, `cfg-001`, `wifi-001`, `poll-001`, `disp-001`, `touch-001`, `nfc-001`, `time-001`, `api-001`. Spike code (`spikeMode.h`, `spikeRawHttp.h`) is registered under `api-001`. No orphaned feature folders or files.

2. **Test coverage — substantial gap on baseline features.** Of nine baseline features (`deploy-001` through `nfc-001`), **zero have test_ids**. Test plan only covers `api-001` (T001-T018) and `time-001` (T019, T020). VE backlog: at minimum a smoke test per baseline feature. Acceptable for a project that came in with a working firmware (verification was implicit "it works on the dev unit") but should be flagged.

3. **Cross-feature test coverage — adequate for what's recorded.** Two interactions (`X001`, `X002`) both have `test_coverage` populated (T020 and T016/T017/T018 respectively). No matrix entries lack test linkage.

4. **Documentation currency — green.** Architecture (ADR-006), inventory, matrix, tasks, roadmap, test plan all updated this session. ADR-003 was promoted from proposed to accepted; ADR-002 trimmed. ADRs 001/004/005 marked superseded.

5. **Secret hygiene — yellow.**
   - `.gitignore` correctly excludes `data/spotify_diy_config.json`. Verified with `git check-ignore`.
   - `data/spotify_diy_config.example.json` template committed.
   - **However**: leaked refresh-token-and-secret pair was carried forward through this entire session in `data/spotify_diy_config.json` and dumped to serial logs on every TLS retry due to `SPOTIFY_DEBUG` being on in the vendored library. Spotify auto-revoked. Rotation (TASK-006) deferred pending user account access. See `lessons_learned.md` LL-002 and LL-003.

6. **Build artefacts in sync — green.** `cyd2usb` and `cyd2usb_spike` envs both build clean post-`time-001`. Flash usage 86.9% on `cyd2usb_spike`; comfortable headroom for now, must re-verify after M3 (skin atlas).

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Add baseline-feature smoke tests to `test_plan.md` (Finding 2) | VE | not yet ticketed; flag PM at next planning |
| Disable `SPOTIFY_DEBUG` or redact secret-bearing log lines in vendored lib | Developer | fold into TASK-006 procedure (run after rotation) |
| Resume TASK-006 rotation when user account access restored | Developer | TASK-006 already exists, status `pending` |
| Human review of LL-001..LL-007; promote candidates to `best_practices.md` | QM ↔ human | tracked in `lessons_learned.md` Best-practice candidates section |

**Resolution**: open — actions remain pending. Audit re-runs on next milestone close (M1 exit when TASK-006 + spike run complete).

---

### Audit — 2026-05-07 — Process self-audit triggered by user "@PM how much of the process was followed"

**Triggered by**: human (direct-invoke `@PM`)

**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage (matrix)
- [x] Documentation currency
- [x] Inter-agent protocol adherence (per AGENTS.md)
- [x] Build artefacts in sync

**Findings**:

1. **Feature inventory — yellow.** Three new features shipped without inventory entries: `poll-002` (M4, Spotify-Diy-Thing@f84b112), `m2-001` (M2 tier 1, @a9682be), `dev-001` (network shims, @bf5d5ca). Back-filled this session.

2. **Test coverage — yellow.** New features had zero test entries before this audit. Back-filled T021–T031 across three new suites (poll-002, m2-001, dev-001). Most entries are `passing` or `planned-deferred`; deterministic regression for the bake tool (T025 byte-identical re-bake) is `planned` — needs a checked-in golden hash.

3. **Cross-feature matrix — green.** No new cross-feature interactions beyond the existing `poll-001 ↔ disp-001` link, which `poll-002` and `disp-001` extend rather than introduce. Matrix unchanged.

4. **Documentation currency — yellow → green after this audit.**
   - ADR for the bake tool's implementation choices was missing — back-filled as ADR-008.
   - Roadmap M2 status updated (in_progress, tier 1 done) and M4 (done) on 2026-05-07.
   - Tasks file: TASK-011 moved to Completed; TASK-012, TASK-013 added.

5. **Inter-agent protocol — red.** Substantial gaps caught by the user's `@PM` query, captured as LL-010 and LL-011:
   - No Architect consult before bake-tool implementation (ADR-003 deferred items decided without ADR).
   - No VE testability challenge before either M4 or M2 tier 1 finalized.
   - No QM prompt after TASK-011 (M4) closed.
   - Dev-001 (cellular/captive-portal infra) shipped with no PM tracking at all.
   - Best-practices file (`docs/quality/best_practices.md`) not consulted this session.

6. **Build artefacts — green.** `cyd2usb` env builds clean post-M4 and post-M2 tier 1. Album art temporarily disabled via `DISABLE_ALBUM_ART` define in `.ino` — orthogonal i.scdn.co fetch hang, tracked separately (no task ID yet — VE follow-up to register).

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Commit checked-in golden hash for bake tool output (T025) | VE | not yet ticketed; flag PM at next planning |
| Register the album-art fetch hang as a task | PM | not yet ticketed |
| Pre-commit checklist for cross-role hand-offs (LL-010) | human review | LL candidate, awaiting promotion |
| Tasks-file entry rule for any new sketch/tools file (LL-011) | human review | LL candidate, awaiting promotion |
| Read `best_practices.md` at session start as standing practice | Developer | discipline change, no ticket |

**Resolution**: open — back-fill complete (this commit), follow-up actions remain pending.

---

### Audit — 2026-05-08 — Process self-audit (TASK-009 close, M-LOG/2, M-IO, M5)

**Triggered by**: human (`@docs/agents/AGENTS.md how much of the process did we skip?`)

**Scope**: everything between the 2026-05-07 audit and now — TASK-016 a/b/c/d/e/f (M-LOG tier 1), TASK-018 (M-LOG2), TASK-019 tier 1 (M-IO, ADR-011), TASK-009 close-out (3 lib patches beyond ADR-007), M5 (touch-002) close, skin source swap.

**Process scorecard (per AGENTS.md inter-agent protocol)**:

| Protocol rule | Followed? | Notes |
|---|---|---|
| Developer notifies VE when feature `implemented` | ✗ | Six features shipped (log-001, log-002, io-001, touch-002, plus the api-002 lib patches and the bake-tool tier 3 sprites earlier) without explicit VE handoff. VE got pulled in once via the ADR-010 mini-review; that's it. |
| VE challenges Developer on testability before finalised | partial | ADR-010 review did this — caught the build-time `CORE_DEBUG_LEVEL` gate retroactively, not before. Every other ship cycle skipped this entirely. |
| Architect reviews R&D proposals before PM schedules | n/a | No R&D this session. |
| Developer consults Architect before cross-component changes | ✗ | The TASK-009 close-out (3 lib patches in the request-construction path) and M5 (touch-002 reaching into spotifyLogic's `songStartMillis` for optimistic-UI freeze) were both cross-component. Neither paused for an Architect ping. |
| VE challenges Architect on testability of interfaces | ✗ | ADR-011 (M-IO tier 1) shipped with "mini multi-role review folded into the ADR itself for speed". Self-conducted. T046–T049 were named but never written into `test_plan.md`. |
| PM prompts QM after every feature/milestone close | ✗ | M5 was closed (commit `b37b66a`) with no QM prompt. This audit is the manual user catch. |
| QM brings best-practice candidates to human | partial | LL-010 was flagged for promotion; never resolved. Multiple new LL candidates surfaced this session and weren't captured (see Findings 4 below). |

**Findings**:

1. **Feature inventory — red.** Four shipped features missing from `feature_inventory.yaml`: `log-001` (M-LOG tier 1), `log-002` (on-screen overlay), `io-001` (M-IO tier 1), `touch-002` (M5). All four were referenced by ADRs, tasks, and commit messages — but never registered. Same class of skip as LL-005/LL-011 (cross-feature matrix, dev-infra not tracked).

2. **Test plan — red.** Three planned test suites never landed:
   - T036–T040 (M-LOG tier 1) — named in `ADR-010-review.md`, never written.
   - T046–T049 (M-IO tier 1) — named in ADR-011, never written.
   - T0xx (M5 / touch-002) — never named, never written.
   The visual confirmations during this session were ad-hoc DUT eyeball checks recorded in commit messages — not in the test plan, not regression-able.

3. **ADR review gating — red.** The very thing LL-010 was raised for. ADR-010 reached `accepted` ahead of multi-role review and was amended *four times* retroactively as findings emerged from implementation (build-time level gate, exact-tag matching, log_e/log_w bypass, ESP_LOGx blast radius). ADR-011 took a "mini multi-role review folded into the ADR itself for speed" shortcut and shipped without a real VE/Developer pass. ADR-007 was assumed to fully fix non-GET TLS — turned out three more structural lib bugs were stacked on the same numeric error (covered by the new LL-013 below).

4. **Lessons captured — red.** At least four LL-worthy findings from this session went uncaptured before this audit:
   - "WiFiClientSecure::lastError() returns last *result* not last *error* — sticky stale success fd." (`fd=49` mistaken for an error code, sent us down a dead-end "rc=49 unknown" path for two reflashes.)
   - "Arduino-ESP32 redefines ESP_LOGx to its own log_x macros that bypass esp_log_writev." (Caused the screenlog overlay to render an empty ringbuffer for several reflash cycles before being diagnosed.)
   - "Same numeric error code can mask multiple independent root causes." (mbedtls 0x0050 NET_CONN_RESET appeared in three distinct lib bugs; ADR-007 was assumed to fix all instances of it.)
   - "When the SDK spec says 204 No Content but the server returns 200, the server wins." (Lib's `return statusCode == 204` made every successful PUT/POST look like a failure.)

5. **Network-blame antipattern.** When the spike harness retest failed all 15 rows, my first hypothesis was "Marriott captive portal blocks non-GET methods over HTTPS". User pushed back. AP-level method filtering of HTTPS is implausible without TLS MITM, and we had no MITM evidence — the hypothesis was lazy. The actual cause was three structural lib bugs (caught by spec cross-check and request-byte tracing). LL-014 below.

6. **Build artefacts — green.** Both `cyd2usb` and `cyd2usb_winamp` and `cyd2usb_winamp_screenlog` and `cyd2usb_spike` envs build clean. Flash 88.8 % / 97.8 % / 97.8 % / 90.4 % respectively.

7. **Heartbeat / observability — green.** TASK-016d's `block_max_ms` field is now in every heartbeat; the `/log` endpoint exists (HTTP-test deferred until a non-AP-isolated network); on-screen overlay populated and DUT-verified.

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Register `log-001`, `log-002`, `io-001`, `touch-002` in `feature_inventory.yaml` | Developer | this commit |
| Write T036–T040 (M-LOG), T046–T049 (M-IO), T050+ (M5) into `test_plan.md` | VE | this commit |
| Add LL-012 / LL-013 / LL-014 / LL-015 to `lessons_learned.md` | QM | this commit |
| Promote LL-010 (multi-role review pre-`accepted`) — already a candidate; user-decision pending | human | already pending |
| Re-run multi-role review on ADR-011 properly (currently "self-conducted") | Architect ↔ VE | not yet ticketed |
| Fold TASK-009 close-out lib patches back into ADR-007 as amendments (or ADR-007-review.md) | Architect | not yet ticketed |
| Prompt QM at the next milestone close (any of M6, M7) — habit fix | PM | discipline |

**Resolution**: open — back-fill ships in this commit; ADR-011 review and ADR-007 amendment remain pending.

---

## Entry Format

```
### Audit — [YYYY-MM-DD] — [Scope]
**Triggered by**: human | PM | self
**Areas checked**:
- [ ] Feature inventory completeness (features in code not in inventory)
- [ ] Test coverage per feature (implemented features with no test_ids)
- [ ] Cross-feature test coverage (interactions with no test_coverage)
- [ ] Documentation currency (docs lagging behind code)

**Findings**: (specific gaps — named by feature ID, file path, or responsible agent)

**Actions assigned**: (owner and action per finding)

**Resolution**: (completed actions and outcome — filled in after closure)
```