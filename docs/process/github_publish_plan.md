# GitHub Publish Plan

> Status: DRAFT  
> Started: 2026-06-07

Plan for publishing this project to a public GitHub repository. Covers license
compliance, attribution obligations, and pre-publish checklist.

---

## 1. External Code Inventory

### 1.1 `app/lib/SpotifyArduino/` — MIT ✅

Vendored fork of [witnessmenow/spotify-api-arduino](https://github.com/witnessmenow/spotify-api-arduino).  
Copyright (c) 2021 Brian Lough.

Checked in under `app/lib/` with local patches documented in
`app/lib/SpotifyArduino/LOCAL_PATCHES.md`. MIT allows patching and redistribution;
original copyright headers in the source files must remain intact.

**Action:** None — already clean. Verify original copyright headers are present
in `src/SpotifyArduino.h` and `src/SpotifyArduino.cpp` before publishing.

---

### 1.2 `Spotify-Diy-Thing/` — MIT ✅ (gitignored)

Upstream: [witnessmenow/Spotify-Diy-Thing](https://github.com/witnessmenow/Spotify-Diy-Thing).  
Copyright (c) 2023 Brian Lough.

Contains `CYD28_TouchscreenR.h/.cpp` — derivative of Paul Stoffregen's
XPT2046_Touchscreen (MIT with "development funding notice" clause: notice must
be preserved in copies).

**Gitignore status:** Excluded by `Spotify-Diy-Thing/` in `.gitignore`. Not
committed; no action needed.

---

### 1.3 `cspot/` — GPL-3.0 (gitignored, unused)

Upstream: [feelfreelinux/cspot](https://github.com/feelfreelinux/cspot).  
GPL-3.0. Strong copyleft — any linked derivative must also be GPL-3.0.

`cspot/` was explored as an alternative Spotify Connect backend but is not used
in the firmware. It is gitignored and not linked by any `app/` code.

**Action:** `rm -rf cspot/` — delete the local directory. No git history to
rewrite; it was never committed.

---

### 1.4 PlatformIO `lib_deps` — fetched at build time, not committed ✅

| Library | License | Source |
|---|---|---|
| `bblanchon/ArduinoJson` | MIT | PlatformIO registry |
| `bodmer/TFT_eSPI` | MIT | PlatformIO registry |
| `wnatth3/WiFiManager` | MIT | PlatformIO registry |
| `khoih-prog/ESP_DoubleResetDetector` | MIT | PlatformIO registry |
| `witnessmenow/Seeed_Arduino_NFC` | MIT | GitHub |
| `bitbank2/JPEGDEC` | Apache 2.0 | PlatformIO registry |

Not committed to the repository. No redistribution concern.

---

### 1.5 `resource/ASCII_Aquarium/ASCII_Aquarium_CYD.ino` — No license ⚠️

**Source:** [POWER-PILL/ASCII-Aquarium](https://github.com/POWER-PILL/ASCII-Aquarium)

The upstream GitHub repository has no LICENSE file. Under default copyright law
this means "all rights reserved" — redistribution is not permitted without
explicit author permission.

The file has no copyright header. It is reference material (not compiled into
firmware) but it IS committed to this repo (the `.gitignore` has
`!resource/ASCII_Aquarium/` as an exception).

**Options:**
1. Open an issue on [POWER-PILL/ASCII-Aquarium](https://github.com/POWER-PILL/ASCII-Aquarium)
   asking the author to add a permissive license.
2. Remove the file from git tracking (`git rm resource/ASCII_Aquarium/ASCII_Aquarium_CYD.ino`)
   and add `resource/ASCII_Aquarium/` to `.gitignore`. Keep a local copy for
   reference.

**Resolution:** Removed from git tracking (2026-06-07). File remains locally for
reference. Upstream repo is the canonical source:
<https://github.com/POWER-PILL/ASCII-Aquarium>

---

### 1.6 `resource/5in1/` — No license, unknown author ⚠️ (gitignored)

**Source:**  
- YouTube video: <https://youtu.be/qM6bYuTQb-I>  
- Original download (Google Drive, from video description):
  <https://drive.google.com/file/d/1nhd1BqWAPwRSzaGkiKleLYczm-PIw6yb/view?usp=sharing>

Code shared via YouTube/Google Drive without an explicit license. The author has
not stated redistribution terms.

**Gitignore status:** Covered by `resource/*` in `.gitignore`. Not committed.
No action required for the publish itself, but note the source above for
attribution if this code is ever incorporated.

---

### 1.7 `app/skins/base-2.91.wsz` + `app/skins/base-2.91/` — Proprietary ❌

**Source:** Winamp 2.91 default ("base") skin. Original artwork by Nullsoft.  
Archived (not licensed) at: <https://skins.webamp.org>

This is the most significant blocker. The base skin shipped with Winamp is
Nullsoft/AOL proprietary artwork. The 2023 Winamp classic source release covered
only the C++ player code, not the bitmap assets. The Winamp Skin Museum
(skins.webamp.org) archives skins for cultural preservation but does not grant
redistribution rights — the museum maintainer (captbaritone/webamp) explicitly
acknowledges Winamp assets remain Nullsoft property.

Both the `.wsz` archive and the extracted `base-2.91/` folder are committed to
git.

**Resolution: Option A — gitignore and document**

Remove from git tracking; add to `.gitignore`. Add a one-line note to the README
instructing users to download the skin themselves and place it at
`app/skins/base-2.91.wsz`. The `run/bake-skin` workflow is unchanged — it just
requires the file to be present before running.

```
# .gitignore additions
app/skins/base-2.91.wsz
app/skins/base-2.91/
```

Alternative options (not chosen):
- **Option B:** Find a community skin with explicit free license and adapt the
  bake tooling to it (non-trivial — layout must match bake tool expectations).
- **Option C:** Design custom replacement bitmaps (clean, but significant art
  effort).

**Action required before publish.**

---

### 1.8 `resource/web-api/` — Spotify developer docs ✅ (low risk)

Local snapshot of Spotify Web API reference material. Sources documented in
`resource/web-api/INDEX.md`. Includes:

- `official-open-api.yaml` — Spotify's publicly published OpenAPI spec
- `sonallux-fixed-open-api.yml` — community-maintained spec from
  [sonallux/spotify-web-api](https://github.com/sonallux/spotify-web-api) (MIT)
- Changelog markdown files scraped from `developer.spotify.com`

Publishing Spotify's own developer documentation in a public repo is a gray area
under their ToS, but it is widely tolerated in the developer community (they
publish the spec publicly for developer use). Low real-world risk.

**Action:** None blocking, but optionally add a note to `INDEX.md` clarifying
these are snapshots for offline reference.

---

## 2. Pre-Publish Checklist

| # | Item | Status |
|---|---|---|
| 1 | Remove / gitignore `app/skins/base-2.91.wsz` + `app/skins/base-2.91/` | ✅ Done (2026-06-07) |
| 2 | Update README with skin download instructions | ❌ TODO |
| 3 | Resolve `resource/ASCII_Aquarium/ASCII_Aquarium_CYD.ino` (remove or get license) | ✅ Done (2026-06-07) — removed from git; upstream: https://github.com/POWER-PILL/ASCII-Aquarium |
| 4 | Delete local `cspot/` directory | ✅ Done (2026-06-07) |
| 5 | Verify MIT copyright headers intact in `app/lib/SpotifyArduino/src/` | ✅ Done (2026-06-07) — headers present in both `.h` and `.cpp` |
| 6 | Add top-level `LICENSE` file declaring project's own license | ✅ Done (2026-06-07) — MIT |
| 7 | Review `.gitignore` — confirm `wifi_creds.h`, `spotify_diy_config.json` excluded | ✅ Done (2026-06-07) — explicit guards added |
| 8 | Scrub git history for any accidentally committed secrets | ✅ Done (2026-06-07) — no secret files in history; tool files use variable names only |
| 9 | Run a license scanner (e.g. ScanCode Toolkit) on committed files | ❌ TODO |
| 10 | Fix `app/data` broken symlink — points to gitignored `Spotify-Diy-Thing/data/`; new users get a broken symlink on clone. Replace with a real directory or a setup script. | ✅ Done (2026-06-08) — `get_refresh_token.py` detects broken symlink, removes it, creates real dir |

---

## 3. Recommended License Scanners

| Tool | Best for |
|---|---|
| [ScanCode Toolkit](https://github.com/nexB/scancode-toolkit) | Deep local scan; finds license text buried in source files |
| [FOSSA](https://fossa.com) | Full dependency + SPDX report; free tier; GitHub CI integration |
| [OSS Review Toolkit (ORT)](https://github.com/oss-review-toolkit/ort) | End-to-end: dependency resolution → license analysis → policy |
| [Licensee](https://github.com/licensee/licensee) | Quick per-file SPDX detection; what GitHub uses internally |
| [Snyk](https://snyk.io) | License + vulnerability combined; free tier |
| [TLDR Legal](https://tldrlegal.com) | Human-readable license summaries (reference, not scanner) |

---

## 4. Choosing a License for This Project

The project's own code is currently unlicensed (no top-level `LICENSE` file).
Constraints from dependencies:

- SpotifyArduino (MIT) — compatible with anything
- All PlatformIO deps (MIT/Apache 2.0) — compatible with anything
- `cspot` (GPL-3.0) — **not linked**, so no copyleft obligation

**Recommended:** MIT. Simple, permissive, compatible with all current deps,
appropriate for a hobbyist hardware project.

If `cspot` were ever linked or distributed together, the project would need to be
GPL-3.0 or GPL-3.0-compatible.
