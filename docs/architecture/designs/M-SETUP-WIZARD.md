# Design — M-SETUP-WIZARD: `run/setup` wizard

> Owner: Architect  
> Status: **implemented** (2026-06-11, `463ba0b`; VE-verified same day — feature
> `setup-wizard-001`, T-SETUP-01..10)  
> Milestone: M-SETUP-WIZARD  
> Reality-sync 2026-07-16 (Architect pass): shipped as designed EXCEPT the
> PATCH-003 section below, which is historical — the patch landed, then was
> **retired** when M-SETTINGS WiFi Phase 2 deleted `WifiManagerHandler.h`
> entirely (WiFiManager/DRD left the boot path). The SPIFFS `/wifi_creds.json`
> read now lives in `app/src/main.cpp` (~:2146-2185) and the priority chain
> gained two levels: `wifi_creds.h` → **NVS** → SPIFFS `/wifi_creds.json` →
> **on-device WiFi settings UI** (no captive portal). One post-design fix on
> record: `WiFi.persistent(true)` corrupted NVS on bad SPIFFS creds
> (TASK-167) — the shipped code uses `persistent(false)` on the SPIFFS path.
> OQ-2 resolved by reality: wizard and on-device UI share the file, no
> conflict. See `upstream-patches.md` (PATCH-003 marked retired).  

---

## Problem

First-time setup requires two separate manual steps that are undiscoverable:

1. **WiFi** — user must hand-edit `wifi_creds.h` with `#define` syntax, then reflash firmware. This is a compile-time path from upstream; our project should not promote it as the default.
2. **Spotify** — user must invoke `get_refresh_token.py` directly and remember to `./run/spiffs push` afterward.

No single entry point exists. New users navigate three README sections to get a working device.

---

## Solution

`run/setup` — bare terminal wizard. Writes both credential files to `app/data/`, then offers a single `./run/spiffs push` to upload both to SPIFFS non-destructively.

---

## Credential storage — SPIFFS as primary path

Both credential files live in `app/data/` on the host and in the SPIFFS partition on the device.

| File (host) | SPIFFS path | Content |
|---|---|---|
| `app/data/wifi_creds.json` | `/wifi_creds.json` | `{"ssid": "...", "pass": "..."}` |
| `app/data/spotify_diy_config.json` | `/spotify_diy_config.json` | `{"clientId": "...", "clientSecret": "...", "refreshToken": "..."}` |

Single `./run/spiffs push` uploads both non-destructively. No firmware recompile needed for credential changes.

### WiFi priority chain (after PATCH-003)

```
1. wifi_creds.h compile-time defines   ← upstream dev-shortcut; untouched; highest priority
2. SPIFFS /wifi_creds.json             ← our primary user path (PATCH-003)
3. WiFiManager captive portal          ← fallback
```

The compile-time path stays exactly as upstream wrote it. Our project promotes SPIFFS and does not document `wifi_creds.h` as the recommended user workflow.

---

## PATCH-003 — `WifiManagerHandler.h`

**File:** `Spotify-Diy-Thing/SpotifyDiyThing/WifiManagerHandler.h`  
**Rationale:** Upstream has no runtime credential path. Compile-time `wifi_creds.h` requires a firmware reflash on every credential change and is unsuitable as the default user workflow.

Insert a SPIFFS-read block inside `setupWiFiManager()`, **after** the `#ifdef HARDCODED_WIFI_SSID` block, **before** the `WiFiManager wm;` line:

```cpp
// PATCH-003: Read WiFi credentials from SPIFFS /wifi_creds.json.
// Promoted as the default user path by run/setup; avoids firmware recompile.
// Priority: wifi_creds.h (compile-time) > SPIFFS > WiFiManager portal.
#ifndef HARDCODED_WIFI_SSID
if (!forceConfig) {
    SPIFFS.begin(true);
    if (SPIFFS.exists("/wifi_creds.json")) {
        File f = SPIFFS.open("/wifi_creds.json", "r");
        if (f) {
            StaticJsonDocument<256> doc;
            if (deserializeJson(doc, f) == DeserializationError::Ok) {
                const char* ssid = doc["ssid"] | "";
                const char* pass = doc["pass"] | "";
                if (strlen(ssid) > 0) {
                    WiFi.persistent(true);
                    WiFi.mode(WIFI_STA);
                    WiFi.begin(ssid, pass);
                    Serial.print("[wifi] Connecting from SPIFFS: ");
                    Serial.println(ssid);
                    unsigned long deadline = millis() + 30000;
                    while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
                        delay(250);
                        Serial.print(".");
                    }
                    Serial.println();
                    if (WiFi.status() == WL_CONNECTED) {
                        f.close();
                        drd->stop();
                        return;
                    }
                    Serial.println("[wifi] SPIFFS connect failed — falling through to portal.");
                }
            }
            f.close();
        }
    }
}
#endif
```

**Notes:**
- Guarded by `#ifndef HARDCODED_WIFI_SSID` so the compile-time path still takes full priority.
- `SPIFFS.begin(true)` is idempotent if already mounted (called later by `configFile.h`).
- `StaticJsonDocument<256>` fits the schema comfortably; no heap allocation.
- Must be registered in `upstream-patches.md` as PATCH-003 before merging.

---

## `.gitignore` update

Replace named per-file entries with a directory-level rule so any future credential file in `app/data/` is covered automatically:

```gitignore
# app/data/ — runtime credentials and overrides; never commit
app/data/*
!app/data/.gitkeep
```

Remove the existing named entries:
```gitignore
# remove these:
app/data/spotify_diy_config.json
app/data/host_overrides.json
```

Add `app/data/.gitkeep` to keep the directory tracked in git (empty placeholder).

---

## File permissions

`run/setup` calls `os.chmod(path, 0o600)` after writing each file. Standard practice for secret files (mirrors `~/.ssh/id_rsa`, `~/.aws/credentials`). Owner read/write only.

---

## UX flow

```
$ ./run/setup

ESP32 Spotify Display — Setup Wizard

What would you like to configure?
  1. WiFi credentials
  2. Spotify API keys
  3. Both

Choice [1/2/3]: 3
```

Sections run in order: WiFi first, Spotify second. Ctrl-C at any point leaves existing files untouched (write via temp file + `os.replace()`).

---

## WiFi section

```
=== WiFi Credentials ===

SSID: MyNetwork
Password: (hidden)
Confirm:  (hidden)

Writing app/data/wifi_creds.json ... done. (chmod 600)
```

Validation: SSID non-empty ≤ 32 chars; password non-empty ≥ 8 chars, confirmed.  
Existing file: shows current SSID, prompts `Overwrite? [y/N]:`.

---

## Spotify section

```
=== Spotify API Keys ===

Client ID:     (input)
Client Secret: (hidden)

Opening browser for Spotify authorisation...
Waiting for callback on http://127.0.0.1:8888/callback/ ...

✓ Refresh token obtained.
Writing app/data/spotify_diy_config.json ... done. (chmod 600)
```

OAuth implementation: inline reuse of `get_refresh_token.py` logic (no new deps).  
Existing file: shows masked Client ID, prompts `Overwrite? [y/N]:`.

---

## End summary + flash offer

```
=== Done ===

  WiFi:    app/data/wifi_creds.json written
  Spotify: app/data/spotify_diy_config.json written

Upload both to device now? (./run/spiffs push) [Y/n]:
```

Single `./run/spiffs push` uploads `app/data/` into SPIFFS non-destructively.  
If declined: `Remember to run ./run/spiffs push before first boot.`

---

## Implementation

- **Language:** Python 3, shebang `#!/usr/bin/env python3`, placed at `run/setup`
- **Modules:** `getpass`, `http.server`, `threading`, `urllib`, `json`, `pathlib`, `os`, `sys`, `subprocess` — all stdlib, no venv required
- **Flash call:** `subprocess.run(["./run/spiffs", "push"])`, stdout/stderr inherited
- **Atomicity:** write `<file>.tmp` → `os.replace()` on success
- **Paths:** all derived from `REPO_ROOT = Path(__file__).parent.parent`

---

## Relationship to `get_refresh_token.py`

Stays as a standalone tool for scripted/headless re-auth. `run/setup` inlines the same OAuth logic rather than shelling out (avoids venv activation complexity in a subprocess).

---

## Docs to update

| File | Change |
|---|---|
| `README.md` | Replace steps 4 + 7 with single `./run/setup` step; move manual paths to a collapsible note |
| `docs/process/project_run_scripts.md` | Add `run/setup` row |
| `CLAUDE.md` | Add `./run/setup` to run/ scripts list |
| `docs/process/dut_workflow.md` | New §1 "First-time setup" pointing to `run/setup` before §0 port resolution |
| `docs/architecture/designs/M-MULTIAPP/upstream-patches.md` | Register PATCH-003 |
| `.gitignore` | Replace named `app/data/` entries with `app/data/*` + `!app/data/.gitkeep` |

---

## Exit criteria

| # | Criterion |
|---|-----------|
| E1 | WiFi section writes valid `wifi_creds.json`; PATCH-003 firmware reads it and connects |
| E2 | Spotify section completes OAuth and writes valid `spotify_diy_config.json` |
| E3 | Single `./run/spiffs push` offer at end uploads both files non-destructively (cal.json/settings.json preserved) |
| E4 | Overwrite guard prompts when existing files present |
| E5 | Ctrl-C at any point leaves existing files untouched |
| E6 | `wifi_creds.h` compile-time path still works (PATCH-003 is `#ifndef`-guarded) |
| E7 | All six docs updated |

---

## Open questions

| # | Question |
|---|----------|
| OQ-1 | Should `run/setup` absorb `get_refresh_token.py` eventually? Current answer: keep both. |
| OQ-2 | When M-SETTINGS WiFi Phase 2 ships (on-device WiFi selection), SPIFFS `/wifi_creds.json` becomes writable from the device too. `run/setup` and the on-device flow will share the same file — no conflict, but worth noting. |
