> Owner: R&D

### EXP-023 — 2026-08-27 — M-TESTARCH OQ-A: T1 host-shim spike (rung 1 of PROP-010)

**Hypothesis**: Per PROP-010 rung 1 — a ~200–300 line host shim
(`arduino_shim/` + `fs_shim/`) lets `m3u.h`, and by extension
`settingsStorage.h`, `asciiFold.h`, `textFit.h`, `timeFmt.h`, compile and
link on the host with zero behaviour in the shim itself. If true, T1 is a
real tier today, not contingent on D0.

**Approach**: Cut `rnd/testarch-oq-spikes` from `master`. Before touching
any shim code, re-verified the sandbox toolchain rather than trusting the
coordinator's report of it:

```
$ which gcc g++ pio
/usr/bin/gcc
(no g++, no pio on PATH)
$ echo 'int main(){return 0;}' > /tmp/t.cpp && gcc /tmp/t.cpp -o /tmp/t.out
gcc: fatal error: cannot execute 'cc1plus': posix_spawnp: Permission denied
compilation terminated.
$ python3 -c "import platformio"
ModuleNotFoundError: No module named 'platformio'
```
Confirmed once, as instructed — no compiler, no PlatformIO. This blocks the
actual measurement step (compile + link) of this spike; everything below is
static analysis and best-effort shim authoring, not a pass/fail result.

Re-verified PROP-010's own include-level claims by reading the files
directly rather than trusting the doc:
- `app/src/util/mathUtil.h`/`.cpp`: `<cmath> <cstring> <cstdint>` only. No
  Arduino dependency — confirms the zero-shim-baseline claim.
- `app/src/util/asciiFold.h`: `<stddef.h> <stdint.h>` only. Confirms.
- `app/src/util/textFit.h`: `<string.h>` only. Confirms.
- `app/src/util/timeFmt.h`: `#include <Arduino.h>` **and**
  `"../settingsStorage.h"` — needs the shim, as PROP-010's own step-3
  grouping (not step-1) already implies.
- `app/src/settingsStorage.h`: `#include <Arduino.h>` only (for basic types
  the file itself doesn't visibly need beyond what plain C++ already gives
  it, but the include is real and unconditional).
- `app/src/player/m3u.h`: `#include <Arduino.h> <SD.h> <stdlib.h>
  <string.h> <strings.h>`, plus `"logSink.h"` and `"util/asciiFold.h"`.

Wrote, but could not compile:
- `app/test/host/arduino_shim/Arduino.h` — `String` (thin `std::string`
  wrapper), `millis()`, `random()`, `Serial` (stdio-backed), `ESP` (stub
  `getFreeHeap()`), `min`/`max` templates, `F()` passthrough,
  `strlcpy`/`strlcat` (BSD extensions Arduino-ESP32/newlib provide that
  glibc doesn't).
- `app/test/host/fs_shim/SD.h` — `File`/`SD` over plain `stdio` `FILE*`,
  scoped to exactly what `m3u.h`'s `LineReader`/`PlaylistIndex` call:
  default-construct, `SD.open()→File`, `operator bool`, `seek()`,
  `read(buf,len)→int`, `close()`. Path-sandboxed under `HOST_SD_ROOT`
  (default `./sdcard`) so a host run can't touch the real filesystem.
- `app/test/host/main.cpp` — bare runner, two sections: Section A calls
  the zero-shim files directly (`buildMathLUT`, `lut_sin`/`lut_cos`,
  `hsvToRgb`/`565`, `foldUtf8`, `textFit`); Section B `#include`s
  `settingsStorage.h`, `timeFmt.h`, `player/m3u.h` and exercises
  `m3u::PlaylistIndex` against a fixture file
  (`app/test/host/fixtures/test.m3u`).
- `app/test/host/fixtures/test.m3u` — small fixture with an accented
  artist name (exercises `asciiFold`), a missing-`#EXTINF` record, and a
  duration field.

**Unanticipated finding (the actual rung-1 signal)**: `m3u.h` pulls in
`"logSink.h"` (`app/src/logSink.h`) for its `LOG_W`/`LOG_I` macros. That
real header is not Arduino-core — it `#include`s `<esp_log.h>` and
`<freertos/FreeRTOS.h>` to run a 12 KB ring buffer plus an
`esp_log_set_vprintf` hook. That is outside the "String, millis(), Serial,
min/max, F()" shim surface PROP-010's plan describes, and `logSink.h`
itself is a sixth file not in M-TESTARCH's five-file list
(`mathUtil`/`asciiFold`/`textFit`/`settingsStorage`/`timeFmt`). Worked
around it by writing `app/test/host/arduino_shim/logSink.h` — a stub that
shadows the real header via include-path ordering (`arduino_shim` searched
before `app/src`) and keeps only the four `LOG_x` macro call shapes,
dropping the ring-buffer/esp_log behaviour entirely. Whether this still
counts as "T1 stays scoped to the five named files" is a judgement call —
it's one small additional stub header, not a slice of `app/src` — but it is
genuinely unanticipated scope PROP-010's kill gate should be read against.

**Outcome**: Nothing was compiled, linked, or run. Every claim above about
what each header `#include`s is a direct reading of the source, not
inference from the design doc — that part is solid. Whether the shim as
written actually satisfies the compiler (type mismatches, missing overloads,
`File`/`String` API gaps not caught by inspection) is genuinely unknown.

**Conclusion**: **Inconclusive — blocked by sandbox environment (no C++
toolchain, no PlatformIO).** The zero-shim-baseline claim (step 1) is
independently re-confirmed by source inspection and is very likely correct
once compiled. The shim spike itself (steps 2–3) cannot be scored
pass/fail — the shim exists as a documented, best-effort artifact, not a
tested one. The one real technical finding — `logSink.h` drags in ESP-IDF
headers, not just Arduino ones — should inform whoever re-runs this: it's
either an acceptable one-file stub (as done here) or, if a reviewer decides
that's out of the "five files" scope, a rung-1 kill-gate trigger under
PROP-010's own criterion ("shim would have to grow to cover code the doc
didn't anticipate").

**Recommendation**: **Continue exploring, in an environment with a working
C++ compiler.** Do not treat this branch's shim as validated. Next session
with a toolchain should: (1) compile Section A alone first (should be
trivial, near-zero risk per the source reading above); (2) compile Section
B and fix whatever the shim gets wrong on first pass — expect `String`/
`File` API gaps, since neither was tested against a real compiler; (3)
re-render a verdict on the `logSink.h` stub against the actual kill gate
language once real pass/fail is available, not before.

**Branch**: `rnd/testarch-oq-spikes`

**Notes**:
- Intended (untested) build command, left as a comment at the top of
  `app/test/host/main.cpp`:
  `g++ -std=gnu++17 -Wall -Wextra -I app/test/host/arduino_shim -I
  app/test/host/fs_shim -I app/src app/test/host/main.cpp
  app/src/util/mathUtil.cpp -o /tmp/host_test`, then
  `HOST_SD_ROOT=app/test/host/fixtures /tmp/host_test`.
- Every new file under `app/test/host/` carries an explicit
  UNCOMPILED/UNVERIFIED header comment — do not let staleness of that
  warning become the way this gets mistaken for tested code later.
- Toolchain failure evidence for the record: `gcc`'s `cc1plus` exists on
  disk but fails `posix_spawnp: Permission denied` even outside Claude
  Code's own sandbox restrictions — this reads as an OS/environment-level
  restriction, not something fixable by retrying the invocation. `pio` is
  absent from `PATH` and `platformio` is not importable by the active
  `python3`. Re-verified once per the coordinator's instruction not to
  spend more than one attempt on this.
