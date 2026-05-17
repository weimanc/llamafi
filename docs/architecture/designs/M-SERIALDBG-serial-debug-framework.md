# Design — M-SERIALDBG Serial Debug Command Framework

> Owner: Developer
> Status: planned (2026-05-17)
> ADR: [ADR-021](../decisions/ADR-021.md)
> Deps: M5 (hit-test path), M-LOG (structured serial), M-CONN (reconnect baseline)

---

## Overview

Expands `handleSerialCommands()` in `SpotifyDiyThing.ino` from a single `reconnect`
command to a table-driven debug interface. Two build modes:

- **`cyd2usb_winamp`** — production; only `reconnect` compiled in.
- **`cyd2usb_winamp_debug`** — test rig; full command surface, `SERIAL_DEBUG` defined.

All responses are JSON lines (`\n`-terminated). Host scripts use `json.loads(line)`.

---

## Feature 1 — `platformio.ini` debug env + git hash injection

### 1a — New PlatformIO env

Add to `Spotify-Diy-Thing/platformio.ini`:

```ini
[env:cyd2usb_winamp_debug]
extends         = env:cyd2usb_winamp
extra_scripts   = pre:scripts/inject_git_hash.py
build_flags     =
    ${env:cyd2usb_winamp.build_flags}
    -DSERIAL_DEBUG
```

### 1b — Git hash pre-script

New file: `Spotify-Diy-Thing/scripts/inject_git_hash.py`

```python
import subprocess
Import("env")
try:
    rev = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        stderr=subprocess.DEVNULL
    ).decode().strip()
    dirty = subprocess.call(["git", "diff", "--quiet"],
                            stderr=subprocess.DEVNULL)
    tag = rev + ("+" if dirty else "")
except Exception:
    tag = "unknown"
env.Append(CPPFLAGS=[f'-DGIT_REV=\'"{tag}"\' '])
```

`GIT_REV` is then available as a `const char*`-compatible string literal in all
translation units. In production `cyd2usb_winamp` builds `GIT_REV` is not defined
(not needed — no `info` command). Guard any use outside the debug env:

```cpp
#ifdef GIT_REV
  // use GIT_REV
#else
  // "unknown"
#endif
```

### 1c — Boot version line

In `setup()`, immediately after `Serial.begin(115200)` and before `logsink::begin()`:

```cpp
{
  const esp_app_desc_t *d = esp_app_get_description();
  char elf[9];
  snprintf(elf, sizeof(elf), "%02x%02x%02x%02x",
           d->app_elf_sha256[0], d->app_elf_sha256[1],
           d->app_elf_sha256[2], d->app_elf_sha256[3]);
  Serial.printf("[boot] git=%s elf=%s build=%s %s\n",
  #ifdef GIT_REV
      GIT_REV,
  #else
      "n/a",
  #endif
      elf, __DATE__, __TIME__);
}
```

`esp_app_get_description()` is in `<esp_app_desc.h>` (included transitively via
Arduino ESP32 / esp-idf; no explicit include needed in practice, but add
`#include <esp_app_desc.h>` if the compiler complains).

`app_elf_sha256` is a SHA256 of the firmware ELF computed by the ESP-IDF linker step
and baked into the binary at `firmware.bin+0x20+144`. First 4 bytes printed as 8 hex
chars is sufficient for a sanity check; not a security hash.

Expected boot output:
```
[boot] git=4c7710e elf=d22e2bd6 build=May 17 2026 14:22:01
```

Host-side flash verification:
```sh
# before flash: extract expected elf prefix from the build artefact
python3 -c "
import struct
d = open('.pio/build/cyd2usb_winamp_debug/firmware.bin','rb').read()
print(d[0x20+144:0x20+148].hex())
"
# after flash: grep boot line from serial
pio device monitor -e cyd2usb_winamp_debug -p /dev/ttyUSB0 | grep '\[boot\]' | head -1
```

---

## Feature 2 — Table-driven command dispatcher

### Replacement for `handleSerialCommands()` in `SpotifyDiyThing.ino`

```cpp
// ── serial command dispatcher ─────────────────────────────────────
// Non-debug commands (reconnect) are always compiled in.
// SERIAL_DEBUG commands are ifdef-gated below.

static void cmdReconnect(const char *) {
  spotifyTask::resetTls();
  spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
  Serial.println("{\"ok\":true,\"cmd\":\"reconnect\"}");
}

#ifdef SERIAL_DEBUG
static void cmdTap(const char *args);
static void cmdDrag(const char *args);
static void cmdGet(const char *args);
static void cmdSet(const char *args);
static void cmdInfo(const char *);
static void cmdHelp(const char *);
#endif

typedef void (*cmd_fn)(const char *args);
struct SerialCmd { const char *name; cmd_fn fn; };
static const SerialCmd kCmds[] = {
  { "reconnect", cmdReconnect },
#ifdef SERIAL_DEBUG
  { "tap",       cmdTap  },
  { "drag",      cmdDrag },
  { "get",       cmdGet  },
  { "set",       cmdSet  },
  { "info",      cmdInfo },
  { "help",      cmdHelp },
#endif
};
static constexpr int kNumCmds = sizeof(kCmds) / sizeof(kCmds[0]);

static void handleSerialCommands() {
  static char buf[64];
  static int  len = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      buf[len] = '\0';
      if (len > 0) {
        // split "name args" at first space
        char *sp = strchr(buf, ' ');
        const char *args = sp ? sp + 1 : "";
        if (sp) *sp = '\0';
        bool handled = false;
        for (int i = 0; i < kNumCmds; ++i) {
          if (strcmp(buf, kCmds[i].name) == 0) {
            kCmds[i].fn(args);
            handled = true;
            break;
          }
        }
        if (!handled) {
          Serial.printf("{\"ok\":false,\"error\":\"unknown command\",\"cmd\":\"%s\"}\n", buf);
        }
      }
      len = 0;
    } else if (len < (int)sizeof(buf) - 1) {
      buf[len++] = c;
    } else {
      // buffer full — WARN and reset; next newline will be misaligned
      Serial.println("{\"ok\":false,\"error\":\"line too long\"}");
      len = 0;
    }
  }
}
```

The `reconnect` handler now emits a JSON confirmation line instead of the previous
plain-text `[reconnect] TLS reset + force poll`. A `conn-001` test suite must be
created and its expected output updated to JSON format before TASK-SERIALDBG-j merges.
Also audit any tmux/grep scripts that match the old `[reconnect]` prefix.

---

## Feature 3 — Touch injection commands (`tap`, `drag`)

Touch injection goes through the `SpotifyDisplay` base class as virtual methods
(ADR-021 AC-2 resolution — avoids `static_cast` coupling the serial handler to a
concrete type). Add to `spotifyDisplay.h` / `SpotifyDisplay`:

```cpp
// spotifyDisplay.h — inside class SpotifyDisplay
#ifdef SERIAL_DEBUG
// Virtual injection points for serial debug touch simulation.
// Default implementations are no-ops so non-WinampDisplay backends compile
// without change. WinampDisplay overrides both.
// Must be called from the loop task only.
virtual void injectTouch(int sx, int sy) {}
virtual void injectRelease() {}
#endif
```

`WinampDisplay` overrides both. `cmdTap` / `cmdDrag` call through the base pointer —
no cast required:

```cpp
// In cmdTap / cmdDrag:
spotifyDisplay->injectTouch(x, y);   // virtual dispatch → WinampDisplay impl
spotifyDisplay->injectRelease();
```

`injectTouch` is identical to the `ts.touched()` branch in `tick()`, but skips the
`ts.touched()` / `ts.getPointScaled()` calls. It does NOT reset
`touchScreenCoolDownTime` — synthetic inputs must not block physical input after a
test. Test scripts must call `set cooldown 0` before each `tap` command to ensure a
clean gate state.

**Cooldown gate for T079:** `injectTouch` must support an optional cooldown-aware mode.
When the mode is active, if `millis() <= touchScreenCoolDownTime` the touch is skipped
and `lastTouchResult` is set to `{region:"NONE", skipped:true}`. The `cmdTap` JSON
response then includes `"skipped":true`. Without this, T079 is untestable — serial
taps always bypass the gate, so rapid injection never exercises it.

**Volume drag suppression:** The drag-end branch in `checkForInput()` fires whenever
`dragState == D_VOLUME_DRAG && !ts.touched()`. Since `ts.touched()` is always false
between synthetic steps (no physical finger), the drag-end path would commit after
every single `injectTouch` call. A `bool s_injectingDrag` flag (set by `cmdDrag`
before the first sample, cleared by `injectRelease`) must be checked in the
`!ts.touched()` branch to suppress premature commit during injection. Developer must
design and implement this flag in TASK-SERIALDBG-d.

`injectRelease` explicitly transitions `D_VOLUME_DRAG → D_IDLE` and issues the
final `ACT_VOLUME` commit, then clears `s_injectingDrag`.

### `cmdTap` implementation

```cpp
static void cmdTap(const char *args) {
  int x, y;
  if (sscanf(args, "%d %d", &x, &y) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"tap\",\"error\":\"bad args — tap <x> <y>\"}");
    return;
  }
  // spotifyDisplay is the global SpotifyDisplay* in SpotifyDiyThing.ino;
  // cast to WinampDisplay* (safe — cyd2usb_winamp_debug only builds WinampDisplay).
  WinampDisplay *wd = static_cast<WinampDisplay*>(spotifyDisplay);
  wd->injectTouch(x, y);
  wd->injectRelease();
  // Response: which region was hit, emitted inside injectTouch via a
  // last-hit-result field set before returning. See §3a below.
}
```

### `cmdDrag` implementation

**Use queue-drain pattern — do NOT use `delay()` in the loop task** (R&D / Developer
review finding). A blocking `delay(10) × steps` starves the display tick, heartbeat,
and log server for the full drag duration. Instead, `cmdDrag` fills a small injection
ring buffer and returns immediately. A `drainInjectionQueue()` call at the top of
`loop()` (before `handleSerialCommands()`) pops one sample per iteration, delivering
samples at natural loop cadence (~10–20 ms) without blocking.

```cpp
// In SpotifyDiyThing.ino (SERIAL_DEBUG only):
struct InjectionStep { int sx, sy; bool release; };
static InjectionStep s_injectQueue[64];  // max 64 steps per drag
static int s_injectHead = 0, s_injectTail = 0;
static bool s_dragPending = false;  // drag-end JSON not yet emitted
static int s_pendingDragX1, s_pendingDragY1, s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps;

static void drainInjectionQueue() {
  if (s_injectHead == s_injectTail) return;
  InjectionStep &step = s_injectQueue[s_injectHead % 64];
  WinampDisplay *wd = static_cast<WinampDisplay*>(spotifyDisplay);
  if (step.release) {
    wd->injectRelease();
    s_dragPending = false;
    Serial.printf("{\"ok\":true,\"cmd\":\"drag\",\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                  s_pendingDragX1, s_pendingDragY1,
                  s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps);
  } else {
    wd->injectTouch(step.sx, step.sy);
  }
  ++s_injectHead;
}

static void cmdDrag(const char *args) {
  int x1, y1, x2, y2, steps;
  if (sscanf(args, "%d %d %d %d %d", &x1, &y1, &x2, &y2, &steps) != 5
      || steps < 1 || steps > 62) {
    Serial.println("{\"ok\":false,\"cmd\":\"drag\",\"error\":\"bad args — drag <x1> <y1> <x2> <y2> <steps=1..62>\"}");
    return;
  }
  // Fill queue (steps+1 move samples + 1 release)
  s_injectHead = s_injectTail = 0;
  for (int i = 0; i <= steps; ++i) {
    s_injectQueue[s_injectTail++ % 64] = {
      x1 + (x2 - x1) * i / steps,
      y1 + (y2 - y1) * i / steps,
      false
    };
  }
  s_injectQueue[s_injectTail++ % 64] = { 0, 0, true };  // release sentinel
  s_pendingDragX1 = x1; s_pendingDragY1 = y1;
  s_pendingDragX2 = x2; s_pendingDragY2 = y2;
  s_pendingDragSteps = steps;
  s_dragPending = true;
  // JSON response emitted by drainInjectionQueue() when release step processes
}
```

Call `drainInjectionQueue()` once per `loop()` iteration, before `handleSerialCommands()`.

**Minimum steps for debounce coverage:** `VOLUME_DRAG_DEBOUNCE_MS = 300 ms`. At loop
cadence ~15 ms/step, spanning ≥ 2 debounce windows requires ≥ `2 × 300 / 15 = 40`
steps. T082 uses `steps=60` for margin.

### 3a — Hit-result reporting from `injectTouch`

Add a private field to `WinampDisplay`:

```cpp
// Last synthetic touch result — set by injectTouch, read by cmdTap's JSON emit.
struct TouchResult {
  const char *region;  // "TRANSPORT","POSBAR","VOLUME","SHUFFLE","REPEAT","VIS","LOGO","DEADZONE","NONE"
  int         transportPressed;  // 0-4 for TRANSPORT; -1 otherwise
  const char *action;  // "PREV","PLAY","PAUSE","STOP","NEXT","SEEK","VOLUME","SHUFFLE","REPEAT","VIS","TLS_RESET","FORCE_POLL","NONE"
  long        seekMs;  // for POSBAR hits; 0 otherwise
  long        volumePct; // for VOLUME hits; -1 otherwise
  bool        skipped;   // true if cooldown-aware mode blocked this tap
} lastTouchResult = { "NONE", -1, "NONE", 0, -1, false };
```

Region includes `DEADZONE` (taps that land outside all named zones — these dispatch
`ACT_FORCE_POLL` in `checkForInput`). `skipped=true` when the cooldown-aware mode
blocked the tap (needed for T079).

`injectTouch` sets `lastTouchResult` before returning; `cmdTap` reads it and emits
region-specific fields:

```
{"ok":true,"cmd":"tap","x":72,"y":97,"hit":"TRANSPORT","pressed":1,"action":"PLAY","skipped":false}
{"ok":true,"cmd":"tap","x":162,"y":77,"hit":"POSBAR","seekMs":105000,"action":"SEEK","skipped":false}
{"ok":true,"cmd":"tap","x":163,"y":63,"hit":"VOLUME","volumePct":50,"action":"VOLUME","skipped":false}
{"ok":true,"cmd":"tap","x":162,"y":85,"hit":"DEADZONE","action":"FORCE_POLL","skipped":false}
{"ok":true,"cmd":"tap","x":0,"y":0,"hit":"NONE","action":"NONE","skipped":false}
{"ok":true,"cmd":"tap","x":141,"y":97,"hit":"NONE","action":"NONE","skipped":true}
```

### Canonical screen coordinates for test scripts

`originX = (320 - 275) / 2 = 22`, `originY = 0` (set in `displaySetup`).

| Region | Centre x | Centre y | Notes |
|--------|----------|----------|-------|
| PREV   | 22+16+11 = **49** | 0+88+9 = **97** | width 23 px |
| PLAY   | 22+16+23+11 = **72** | **97** | |
| PAUSE  | 22+16+46+11 = **95** | **97** | |
| STOP   | 22+16+69+11 = **118** | **97** | |
| NEXT   | 22+16+92+11 = **141** | **97** | width 22 px |
| POSBAR left  | 22+16 = **38** | 0+72+5 = **77** | seeks ≈ 0 ms |
| POSBAR right | 22+16+247 = **285** | **77** | seeks ≈ duration |
| POSBAR mid   | 22+16+124 = **162** | **77** | seeks ≈ duration/2 |
| VOLUME left  | 22+107 = **129** | 0+57+6 = **63** | 0% |
| VOLUME right | 22+107+67 = **196** | **63** | 100% |
| VOLUME mid   | 22+107+34 = **163** | **63** | ~50% (use for zero-delta drag T078) |
| SHUFFLE      | 22+164+23 = **209** | 0+89+7 = **96** | centre of 47×15 |
| REPEAT       | 22+210+14 = **246** | **96** | centre of 28×15 |
| VIS          | 22+24+38 = **84** | 0+43+8 = **51** | 76×16 rect |
| LOGO         | 22+243+16 = **281** | 0+84+16 = **100** | 32×32 |

Dead zones (expect `hit=DEADZONE` or `hit=NONE` — no transport/posbar/volume action):

| Sample point | x | y | Reason |
|---|---|---|---|
| 1 px left of POSBAR | **37** | 77 | POSBAR starts at x=38; x=37 is outside |
| 1 px above POSBAR | 162 | **71** | POSBAR y=72..81; y=71 is above |
| Posbar–transport gap | 162 | **85** | y=83..87 dead zone (posbar ends y=82, transport starts y=88) |
| 1 px below transport | 162 | **107** | transport ends y=106 (88+18); y=107 is below |

Note: do not use `x=22, y=77` as "1 px left of POSBAR" — that is 16 px left, not 1 px.
Do not use `x=48, y=96` as a dead zone — x=48 at y=96 is inside the PREV button rect.

---

## Feature 4 — `get` / `set` commands

### Readable variables (`get <var>`)

| `<var>` | Source | Notes |
|---------|--------|-------|
| `snapshot` | `spotifyTask::copySnapshot()` | full Snapshot struct |
| `backoff` | `spotifyTask::dbg_getFailureCount()` | requires debug accessor §4a |
| `heap` | `ESP.getFreeHeap()` | |
| `cooldown` | `wd->dbg_getTouchCooldownRemainingMs()` | requires debug accessor §4b |

`cmdGet("snapshot")` response — split protocol when serialised JSON exceeds 256 bytes:
- Each chunk is a complete JSON object on one line.
- Intermediate chunks carry `"part":N` (0-based) and `"last":false`.
- The final chunk carries `"last":true` (and no `"part"` field, or `"part":N` for clarity).
- Host script accumulates lines until `"last":true`, then merges fields.
- Field name `"part"` chosen specifically to avoid collision with `Snapshot.seq`.

Single-line (short track/artist — fits in 256 bytes):
```
{"ok":true,"cmd":"get","var":"snapshot","last":true,"valid":true,"isPlaying":true,"progressMs":42000,"durationMs":210000,"volumePct":65,"shuffle":false,"repeat":2,"track":"Song","artist":"Artist"}
```

Split (long track/artist):
```
{"ok":true,"cmd":"get","var":"snapshot","part":0,"last":false,"valid":true,"isPlaying":true,"progressMs":42000,"durationMs":210000,"volumePct":65,"shuffle":false,"repeat":2}
{"ok":true,"cmd":"get","var":"snapshot","part":1,"last":true,"track":"Very Long Track Name That Would Overflow","artist":"Very Long Artist Name"}
```

Host-side accumulator (Python):
```python
def get_snapshot(ser):
    chunks = {}
    while True:
        r = json.loads(ser.readline())
        chunks.update(r)
        if r.get("last"):
            return chunks
```

`cmdGet("backoff")`:
```
{"ok":true,"cmd":"get","var":"backoff","consecutiveFailures":0,"nextPollMs":5000}
```

### Writable variables (`set <var> <val>`)

| `<var>` | Effect | Use in tests |
|---------|--------|-------------|
| `backoff` | `spotifyTask::dbg_setFailureCount(n)` | T079: force failure state |
| `cooldown` | `wd->dbg_resetTouchCooldown()` | T079: clear cooldown between rapid taps |

`set` response:
```
{"ok":true,"cmd":"set","var":"backoff","val":5}
{"ok":false,"cmd":"set","var":"foo","error":"unknown variable"}
```

### 4a — `spotifyTask` debug accessors

Add to `SpotifyDiyThing/SpotifyDiyThing/spotifyTask.h` inside the `spotifyTask`
namespace, guarded:

```cpp
#ifdef SERIAL_DEBUG
// dbg_* accessors: loop-task only. Cross-task access for set is a write
// race — same tolerance as existing resetBackoff() (single aligned 32-bit
// store, atomic on Xtensa). Declare s_consecutiveFailures as volatile to
// match the s_resetTlsPending pattern. Issue set/get between polls only.
void dbg_setFailureCount(unsigned int n);
unsigned int dbg_getFailureCount();
unsigned int dbg_getNextWaitMs();  // expose nextWaitMs() for get backoff response
#endif
```

Implement in `spotifyTaskStorage.cpp`. Also change `s_consecutiveFailures`
declaration from `static unsigned int` to `static volatile unsigned int` to match
the `s_resetTlsPending` pattern:

```cpp
#ifdef SERIAL_DEBUG
void spotifyTask::dbg_setFailureCount(unsigned int n) {
  s_consecutiveFailures = n;
}
unsigned int spotifyTask::dbg_getFailureCount() {
  return s_consecutiveFailures;
}
unsigned int spotifyTask::dbg_getNextWaitMs() {
  return (unsigned int)nextWaitMs();
}
#endif
```

### 4b — `WinampDisplay` debug accessors

Add to `winampDisplay.h` inside the class, guarded:

```cpp
#ifdef SERIAL_DEBUG
uint32_t dbg_getTouchCooldownRemainingMs() const {
  unsigned long now = millis();
  return (touchScreenCoolDownTime > now) ? (uint32_t)(touchScreenCoolDownTime - now) : 0;
}
void dbg_resetTouchCooldown() {
  touchScreenCoolDownTime = 0;
}
// dragState accessor — needed for T078 teardown verification
const char *dbg_getDragStateName() const {
  return (dragState == D_VOLUME_DRAG) ? "D_VOLUME_DRAG" : "D_IDLE";
}
// optimistic volume hold — needed for T082/T075 scriptable verification
uint32_t dbg_getOptimisticVolumeRemainingMs() const {
  unsigned long now = millis();
  return (optimisticVolumeUntilMs > now) ? (uint32_t)(optimisticVolumeUntilMs - now) : 0;
}
// songDuration mirror — guards hitTestPosbar's songDuration <= 0 branch (T085)
long dbg_getSongDuration() const { return songDuration; }
#endif
```

---

## Feature 5 — `info` command

Combines boot version, heap, snapshot summary, and backoff into one JSON line:

```cpp
static void cmdInfo(const char *) {
  Snapshot snap;
  spotifyTask::copySnapshot(&snap);
  const esp_app_desc_t *d = esp_app_get_description();
  char elf[9];
  snprintf(elf, sizeof(elf), "%02x%02x%02x%02x",
           d->app_elf_sha256[0], d->app_elf_sha256[1],
           d->app_elf_sha256[2], d->app_elf_sha256[3]);
  Serial.printf(
    "{\"ok\":true,\"cmd\":\"info\","
    "\"git\":\"%s\",\"elf\":\"%s\",\"build\":\"%s %s\","
    "\"heap\":%lu,\"isPlaying\":%s,\"progressMs\":%ld,"
    "\"durationMs\":%ld,\"volumePct\":%d,"
    "\"shuffle\":%s,\"repeat\":%d,\"consecutiveFailures\":%u}\n",
#ifdef GIT_REV
    GIT_REV,
#else
    "n/a",
#endif
    elf, __DATE__, __TIME__,
    (unsigned long)ESP.getFreeHeap(),
    snap.isPlaying ? "true" : "false",
    snap.progressMs,
    snap.durationMs,
    (int)snap.volumePercent,
    snap.shuffleState ? "true" : "false",
    (int)snap.repeatState,
    spotifyTask::dbg_getFailureCount());
}
```

Expected output:
```
{"ok":true,"cmd":"info","git":"4c7710e","elf":"d22e2bd6","build":"May 17 2026 14:22:01","heap":183412,"isPlaying":true,"progressMs":42000,"durationMs":210000,"volumePct":65,"shuffle":false,"repeat":2,"consecutiveFailures":0}
```

---

## Feature 6 — `help` command

**Must emit a single JSON line** (ADR-021 invariant — one complete JSON object per `\n`).
Iterate `kCmds[]` to build the response — the table is the single source of truth.
The `SerialCmd` struct must retain the `help` field per ADR-021 Decision 1 (the design
previously dropped it — now restored):

```cpp
struct SerialCmd { const char *name; cmd_fn fn; const char *help; const char *args; };
static const SerialCmd kCmds[] = {
  { "reconnect", cmdReconnect, "TLS reset + force poll",            ""                              },
#ifdef SERIAL_DEBUG
  { "tap",       cmdTap,       "inject touch point",                "<x> <y>"                       },
  { "drag",      cmdDrag,      "inject touch drag (queue-drain)",   "<x1> <y1> <x2> <y2> <steps>"  },
  { "get",       cmdGet,       "read internal state",               "<snapshot|backoff|heap|cooldown>" },
  { "set",       cmdSet,       "write debug state",                 "<backoff|cooldown> <val>"      },
  { "info",      cmdInfo,      "git+elf+build+snapshot summary",    ""                              },
  { "help",      cmdHelp,      "list commands",                     ""                              },
#endif
};

static void cmdHelp(const char *) {
  // Single JSON line — iterate table, build inline. Stay under 512 bytes.
  Serial.print("{\"ok\":true,\"cmd\":\"help\",\"commands\":[");
  for (int i = 0; i < kNumCmds; ++i) {
    if (i > 0) Serial.print(",");
    Serial.printf("{\"name\":\"%s\",\"args\":\"%s\",\"desc\":\"%s\"}",
                  kCmds[i].name, kCmds[i].args, kCmds[i].help);
  }
  Serial.println("]}");
}
```

---

## Open design issues (must resolve before TASK-SERIALDBG-d)

| Ref | Issue | Resolution |
|-----|-------|------------|
| AC-2 (Arch) | `static_cast<WinampDisplay*>` couples serial handler to concrete type | **Resolved (2026-05-17):** virtual `injectTouch`/`injectRelease` on `SpotifyDisplay` base — see Feature 3. |
| AC-4 (Arch) | Boot line unconditional — contradicts ADR-021 Decision 4 | **Resolved (2026-05-17):** boot line is unconditional, carved out in ADR-021 alongside `reconnect` as production-safe passive diagnostic. |
| AC-5 (Arch) | `get snapshot` split protocol unspecified | **Resolved (2026-05-17):** `"part":N` + `"last":true` convention — see Feature 4 `get snapshot` section. |
| QM-F2 | `serialdbg-001` not in `feature_inventory.yaml` | PM/Developer registers before implementation starts. |
| QM-F5 | `reconnect` format change has no test coverage; "T-CONN" doesn't exist | Create `conn-001` suite before TASK-SERIALDBG-j merges. |

## Sub-tasks

PM note: allocate a numeric task block (e.g. TASK-056a–k) consistent with the
existing TASK-NNN scheme. The free-text IDs below are placeholders for the design doc;
use the numeric IDs in `tasks.md`.

| Design ID | Description | File(s) |
|-----------|-------------|---------|
| SERIALDBG-a | `platformio.ini` debug env + `scripts/inject_git_hash.py` | `platformio.ini`, `scripts/` |
| SERIALDBG-b | Boot version line (`[boot] git=... elf=... build=...`) | `SpotifyDiyThing.ino` |
| SERIALDBG-c | Table-driven dispatcher (with 4-field `SerialCmd` struct); replace `handleSerialCommands()`; add `drainInjectionQueue()` call in `loop()` | `SpotifyDiyThing.ino` |
| SERIALDBG-d | `WinampDisplay::injectTouch()` (cooldown-aware mode + `s_injectingDrag` flag) + `injectRelease()` + `lastTouchResult` (7-field struct with DEADZONE) | `winampDisplay.h` |
| SERIALDBG-e | `cmdTap`, `cmdDrag` (queue-drain — no `delay()`); injection ring buffer; per-sample `LOG_D("serial", "inject sample %d/%d sx=%d sy=%d", ...)` trace in `drainInjectionQueue()` for T096 observability | `SpotifyDiyThing.ino` |
| SERIALDBG-f | `spotifyTask::dbg_setFailureCount/getFailureCount/getNextWaitMs`; `s_consecutiveFailures` → `volatile` | `spotifyTask.h`, `spotifyTaskStorage.cpp` |
| SERIALDBG-g | `WinampDisplay` debug accessors: `dbg_getTouchCooldownRemainingMs`, `dbg_resetTouchCooldown`, `dbg_getDragStateName`, `dbg_getOptimisticVolumeRemainingMs`, `dbg_getSongDuration` | `winampDisplay.h` |
| SERIALDBG-h | `cmdGet`, `cmdSet` (with multi-line split protocol once AC-5 resolved) | `SpotifyDiyThing.ino` |
| SERIALDBG-i | `cmdInfo` (full fields incl. `volumePct`, `durationMs`, `shuffle`, `repeat`), `cmdHelp` (single JSON line, iterates table) | `SpotifyDiyThing.ino` |
| SERIALDBG-j | Update `reconnect` to JSON response; create `conn-001` test suite first | `SpotifyDiyThing.ino`, `test_plan.md` |
| SERIALDBG-k | VE: execute T076–T085, T089 on `cyd2usb_winamp_debug` DUT | test rig |
| SERIALDBG-l | (added for sync-001) Extend `get snapshot` response with `lastPollAgeMs`, `currentTrackUri`, `deviceActive`. Snapshot struct gains the three fields; spotifyTask::onCurrentlyPlaying populates them; multi-part split protocol from SERIALDBG-h carries the larger payload. | `spotifyTask.h`, `spotifyTaskStorage.cpp`, `SpotifyDiyThing.ino` |
| SERIALDBG-m | (added for sync-001) New `get queue` command — read-only access to QueueSnapshot rows (≤ 5 entries × `{track, artist, durationMs, uri}`). Reads `g_queueMux`-protected snapshot already populated by playlist-001/002. Split protocol required (5 rows × ~80 B exceeds 256 B single-line). | `SpotifyDiyThing.ino`, `spotifyTask.h` |

Recommended order: a → b → c+j → d → e → f → g → h → i → k.
c and j must be coordinated: conn-001 test suite must exist before j merges.

---

## Exit criteria

- `cyd2usb_winamp` builds clean with no `SERIAL_DEBUG` symbols present; flash size
  does not regress vs. pre-SERIALDBG baseline.
- `cyd2usb_winamp_debug` builds clean; `GIT_REV` present in binary (grep ELF or
  check `info` output).
- Boot line `[boot] git=<hash> elf=<8hex> build=<date> <time>` appears within 1 s of
  serial monitor attach.
- `elf` prefix in boot line matches first 4 bytes of `app_elf_sha256` extracted from
  `firmware.bin+0x20+144`.
- `tap 72 97` → `{"ok":true,...,"hit":"TRANSPORT","action":"PLAY"}` + Spotify plays.
- `drag 129 63 196 63 8` → ≥1 `drawVolume` log lines + `drag-end commit` + Spotify
  volume updated.
- `get snapshot` → valid JSON with all Snapshot fields.
- `set backoff 5` → `dbg_getFailureCount()` returns 5; `get backoff` confirms.
- `info` → JSON with `git`, `elf`, `build`, `heap`, `isPlaying`,
  `consecutiveFailures`.
- `help` → valid JSON listing all commands.
- T076–T082 in test plan executable against `cyd2usb_winamp_debug` build.
