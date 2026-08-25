# Design — M-VENDORING: a policy for vendored upstream code

> Owner: Architect
> Status: proposed
> As-built: 2026-08-16
> Tracked-as: TASK-486
> Extends: [ADR-060](../decisions/ADR-060.md) D2b

> **⚠ SKELETON — A STARTING POINT, NOT A DESIGN.**
> This document exists so the problem has a home, an owner and a record of what is already known.
> It deliberately reaches **no conclusions**. Every "Known" item below was measured or read during
> the 2026-08-16 architecture pass; every "Open" item is genuinely unanswered. A thorough design
> revisit should expect to **restructure this document**, not merely fill it in — and should feel
> free to discard framing that turns out to be wrong. Per BP-DOC-3 (candidate): an admitted gap
> beats an invented contract.

---

## Known

`app/lib/` holds five vendored trees, each managed differently:

| Tree | Patch record | Notes |
|---|---|---|
| `ESP32-audioI2S` | `LOCAL_PATCHES.md` — **created 2026-08-15 (TASK-449)** | Carried patches since `f36152b` (TASK-261) with **no record at all**. Pinned v2.3.0; **must not** go to v3.x (~704 KB at boot → instant crash, EXP-008/009, BP-042). Contains `mb_arena`, which is ours. |
| `SD` | `LOCAL_PATCHES.md` | PATCH-SD-1 — SDHC typing via OCR CCS. **A platform bump silently drops it** and a 32 GB card then fails to mount. |
| `SpotifyArduino` | `LOCAL_PATCHES.md` | — |
| `WiFiClientSecure` | none found | vendored; reason not recorded here |
| `SpotifyDiyThingUpstream` | none | a **copy of a separate git repo** (`Spotify-Diy-Thing/`), which is itself an independent upstream project |

- **The platform is pinned**: `espressif32@6.9.0` (Arduino-ESP32 2.0.17). CLAUDE.md records both why
  (the WiFi/`Network.h` split above 6.9.x) and what a bump costs (PATCH-SD-1).
- **Divergence is one-way and undated.** Nothing records which upstream commit each tree was taken
  from, or whether upstream has since fixed anything vendored around.
- **`SpotifyDiyThingUpstream` is the odd one**: two copies of the same files exist
  (`app/lib/…` and `Spotify-Diy-Thing/SpotifyDiyThing/`), the second belonging to a separate project
  that CLAUDE.md says must not be cross-referenced. Which is authoritative is clear in practice (the
  build uses `app/lib/`) and stated nowhere.

## Open

- **OQ1 — what is the upgrade procedure?** Today it is "re-copy and re-apply per LOCAL_PATCHES.md"
  for one tree and unwritten for the rest.
- **OQ2 — should each tree record its upstream ref?** A commit SHA or release tag per tree would make
  divergence measurable instead of folkloric.
- **OQ3 — should `LOCAL_PATCHES.md` be gated?** A check that every patched file is listed would have
  prevented the ESP32-audioI2S gap. Candidate for `run/check-docs`.
- **OQ4 — is `WiFiClientSecure` still needed?** Vendored with no recorded reason. Possibly dead.
- **OQ5 — should `mb_arena` leave the fork?** ADR-060 D2b TASK-476; blocked on whether a PlatformIO
  `lib/` dir can include from `src/`.

## Do not lose

The failure mode is silent and delayed: a bump that compiles cleanly and breaks a 32 GB SD card
weeks later. Any policy has to be checkable at bump time, not discoverable at failure time.
