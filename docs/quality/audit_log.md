# Audit Log

> Owner: Quality Manager

All audits: scope, findings, actions, status.

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