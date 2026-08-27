# Design — M-CONCURRENCY: the task-ownership contract

> Owner: Architect
> Status: accepted
> As-built: 2026-08-26
> Date: 2026-08-16
> Reviewed: 2026-08-26 (@Architect, independent — see §8; accepted **with corrections**, and
> with one blocking defect in §1 that TASK-541 must close before TASK-473's G2 executes)
> Feeds: a future ADR; promotes to `docs/architecture/interfaces/IFC-002`
> Tracked-as: TASK-473
> Registers: no new feature id — this documents existing behaviour.
> Mined from: the 24 `shared_state` / `resource_contention` / `conflict` entries in
> `cross_feature_matrix.yaml`, plus the TASK-287/289/293/295/299/404/430 bug lineage.

> **CORRECTED — @Architect independent review, 2026-08-26 (R6). "24 entries" is wrong, and was
> wrong on the day it was written.** Counted mechanically at this document's own add-commit
> (`ce0bbe2`) with `git show ce0bbe2:docs/project/cross_feature_matrix.yaml | grep -oP
> 'interaction_type:\s*\K\w+' | sort | uniq -c`: **23 `shared_state` + 2 `resource_contention` +
> 5 `conflict` = 30**, out of 64 `X` ids. Today the same command gives **25 + 2 + 5 = 32** of 65.
> The document cites 19 distinct `X` ids in §2/§3, so "24" is neither the filtered population nor
> the cited set. The provenance claim survives — the mining is real and the ownership table's
> citations all resolve (all 17 checked individually against the file) — only the number is false.

**Why this document exists.** Almost every hard bug in this project has been a concurrency-contract
violation, found on hardware: TASK-287 (concurrent `tlsYield` callers), 289 (fetch/playback heap
race, bidirectional), 293 (resume-then-yield deadlock), 295 (65 s connect vs 15 s TWDT), 299
(resume-then-yield 20 ms hole), 404 (NVS/SPIFFS `esp_wifi_connect` collision), 430 (150 s yield
ceiling blocking a row tap). The rules that would have prevented them **do exist** — as comments,
as best practices, and as 24 empirical entries in the cross-feature matrix — but nowhere as one
statement of who owns what.

This document is the normative version of what that matrix records descriptively. The matrix says
*"these two features turned out to share state."* This says *"this context owns this data; it
crosses by this mechanism; that call is illegal from there."*

---

## 1. The six execution contexts (corrected 2026-08-26, TASK-541)

> **TASK-541 as-built.** The table below is the closed version of what §1's two review
> corrections (below) established. Re-derived independently of both the original authoring pass
> and the 2026-08-26 review — every citation in this table was re-checked against source for this
> closure, not copied from the review. All of the review's citations and numbers were confirmed
> exact except where noted; no third context was found. See §1.1 for the corrected conclusion and
> the end of this document for the full as-built note.

Measured from the source, not assumed — four contexts the project's own code creates, plus two the
Arduino/ESP-IDF framework creates on the project's behalf into which the project registers a
callback (a `xTaskCreatePinnedToCore` grep of `app/src` structurally cannot find the latter two —
see §8 R1):

| Context | Core | Prio | Stack | Created at |
|---|---|---|---|---|
| `loopTask` (Arduino) | 1 (`APP_CPU`) | 1 | 20 480 B (`-DARDUINO_LOOP_STACK_SIZE`) | framework |
| `spotifyTask` | 1 (`APP_CPU_NUM`) | 1 | 10 240 B | `spotifyTaskStorage.cpp:591` |
| `dataTask` | 1 (`APP_CPU_NUM`) | 1 | 14 336 B (11 264 B iff `WEBRADIO_ONLY`) | `dataTaskStorage.cpp:1693` |
| `wrAudio` pump | 1 (`APP_CPU_NUM`) | **2** | 8 192 B | `audio/audioEngine.cpp:410` |
| `arduino_events` (framework) | 1 | **19** | 4 096 B | framework — see derivation below |
| WiFi driver task (`wifi`) | **0** | **23** | n/a (closed-source lib) | framework — see derivation below |

**`arduino_events`, re-derived at the mechanism.** `WiFi.onEvent(onEvent)`
(`app/src/wifiDiag.cpp:85`, called unconditionally from `app/src/boot/boot.cpp:276` — the
surrounding `#ifdef SERIAL_DEBUG` in `app/src/wifiDiag.h` opens at line 63, *after* this API)
registers into the Arduino event queue. `WiFiGeneric.cpp:578` in the pinned framework  <!-- check-docs: ignore-line -->
(`framework-arduinoespressif32` 3.20017, i.e. the `espressif32@6.9.0` this project pins — confirmed
against the installed package's `package.json`) creates the consumer:
`xTaskCreateUniversal(_arduino_event_task, "arduino_events", 4096, NULL, ESP_TASKD_EVENT_PRIO - 1,
&_arduino_event_task_handle, ARDUINO_EVENT_RUNNING_CORE)`. Resolving the priority macro chain in the
same SDK checkout (`framework-arduinoespressif32/tools/sdk/esp32/include/`, the package tree that
actually pairs with the `sdkconfig` line numbers below — the newer
`framework-arduinoespressif32-libs` package installed alongside it does **not** match these line
numbers and is not what this pinned platform version resolves to):
`esp_system/include/esp_task.h:35` gives `ESP_TASK_PRIO_MAX = configMAX_PRIORITIES`;  <!-- check-docs: ignore-line -->
`freertos/include/esp_additions/freertos/FreeRTOSConfig.h:81` gives `configMAX_PRIORITIES = 25`;  <!-- check-docs: ignore-line -->
`esp_system/include/esp_task.h:54` gives `ESP_TASKD_EVENT_PRIO = ESP_TASK_PRIO_MAX - 5 = 20` →  <!-- check-docs: ignore-line -->
task priority `20 - 1 = 19`. `ARDUINO_EVENT_RUNNING_CORE` resolves
(`cores/esp32/esp32-hal.h:69`) to `CONFIG_ARDUINO_EVENT_RUNNING_CORE`, which  <!-- check-docs: ignore-line -->
`framework-arduinoespressif32/tools/sdk/esp32/sdkconfig:225` sets to `1` → **core 1**. Every number  <!-- check-docs: ignore-line -->
and every citation the review gave for this row is exact; re-derivation changed nothing.

**The core-0 one, re-derived — one number confirmed from source, one not independently
greppable.** `promiscCb` is registered via `esp_wifi_set_promiscuous_rx_cb`
(`app/src/wifiDiag.cpp:233`) and therefore runs on the WiFi driver task. Its core pin is a
source-verifiable `sdkconfig` fact: `framework-arduinoespressif32/tools/sdk/esp32/sdkconfig:1033`  <!-- check-docs: ignore-line -->
sets `CONFIG_ESP32_WIFI_TASK_PINNED_TO_CORE_0=y` → **core 0**, confirmed. Its **priority (23)** is
not: the WiFi driver task is created inside the closed-source WiFi library
(`libnet80211.a`/`libcore.a`, shipped as prebuilt binaries in this SDK) — no header in the checked
-out framework exposes a `WIFI_TASK_PRIORITY` or equivalent macro, and no `sdkconfig` option governs
it (grepped `esp_wifi/include/*.h` for `Priority`/`PRIO`: no hit). 23 is this project's transcription
of the value ESP-IDF's own published performance guide documents for the WiFi task on the IDF
release this Arduino core wraps (v4.4-family) — carried forward here, not independently re-derived
from a grep, because the value is compiled into a binary this checkout does not source-expose. This
is flagged rather than silently asserted as re-verified: if a future pass gets access to a
disassembly or an upstream IDF source tree with the wifi component in source form, re-check this one
number specifically.

> **RESOLVED — TASK-541, 2026-08-26.** Both findings below are folded into the table at the top of
> this section (stack figure fixed, citations updated to their post-TASK-471 locations). Left in
> place as the review record; the table above is the citable version.

> **CORRECTED — @Architect independent review, 2026-08-26 (R1, R2). Every core/priority/stack
> value in this table is right except one, which is inverted; two of the four `Created at`
> citations have drifted; and the table is not the whole population.**
>
> **The inverted value.** `dataTask`'s "11 264 B (14 336 debug)" reads the `#ifdef` backwards.
> `dataTaskStorage.cpp:109-115` gates on **`WEBRADIO_ONLY`**, not `SERIAL_DEBUG`: 11 KB *iff*
> `WEBRADIO_ONLY`, **14 KB otherwise**. `app/platformio.ini` defines `-DWEBRADIO_ONLY` in exactly
> one env (`[env:cyd2usb_webradio]`, line 133). So **production (`cyd2usb_winamp`) and every debug
> env get 14 336 B**; 11 264 B is the *webradio-only* build — the single env this table's figure
> would least likely describe. Checked at `ce0bbe2` too: the `#ifdef` was identical on the day this
> was written, so this is an authoring error, not drift. It propagated verbatim into IFC-002 §1 and
> was then "independently verified" by @VE for `T_CC_05` (`test_plan.md:37`) — a figure checked
> three times and wrong all three, because nobody read the *condition*, only the constant (BP-067).
>
> **Drifted citations.** `spotifyTaskStorage.cpp:591` is still exact. `dataTaskStorage.cpp:1682` →
> **`:1693`**. `audio/audioEngine.h:649` → **`audio/audioEngine.cpp:410`** — the file was split by  <!-- check-docs: ignore-line -->
> TASK-471 (M-SRCLAYOUT Stage E, `d81f04b`), so the citation names a location that no longer holds a
> task creation at all. `-DARDUINO_LOOP_STACK_SIZE=20480` is `app/platformio.ini:67`, unchanged.
> `T_CC_05` exists to catch exactly this drift and has never been run.

> **RESOLVED — TASK-541, 2026-08-26.** The six-context table above supersedes the four-context one
> this blockquote was attached to; §1.1 below is rewritten to match. Left in place as the review
> record — see the top of §1 for the re-derivation (all citations and numbers here were confirmed
> exact against source except the WiFi task's priority, which is not independently greppable; see
> the note there).

> **CORRECTED — @Architect independent review, 2026-08-26 (R1). "The four execution contexts" is
> the framing defect in this document. There are six, and the two it omits are the two that break
> its central claims.** This is a *blocking* correction: §1.1's "single most dangerous edge" and
> R5's "nothing else is permitted" are both stated over an incomplete population.
>
> | Omitted context | Core | Prio | Builds | App code that runs there |
> |---|---|---|---|---|
> | `arduino_events` | 1 | **19** | **all** | `wifiDiag::onEvent` (`wifiDiag.cpp:38`) |
> | WiFi task (`wifi`) | **0** | 23 | debug only | `wifiDiag::promiscCb` (`wifiDiag.cpp:198`) |
>
> **`arduino_events`, verified at the mechanism.** `WiFi.onEvent(onEvent)` (`wifiDiag.cpp:85`,
> called unconditionally from `boot/boot.cpp:276` — the surrounding `#ifdef SERIAL_DEBUG` in
> `wifiDiag.h` opens at line 63, *after* this API) registers into the Arduino event queue.
> `WiFiGeneric.cpp:578` in the pinned framework (`framework-arduinoespressif32` 3.20017, i.e. the  <!-- check-docs: ignore-line -->
> `espressif32@6.9.0` this project pins) creates that consumer as
> `xTaskCreateUniversal(_arduino_event_task, "arduino_events", 4096, NULL, ESP_TASKD_EVENT_PRIO - 1,
> …, ARDUINO_EVENT_RUNNING_CORE)`. In the same SDK, `esp_task.h:54` gives  <!-- check-docs: ignore-line -->
> `ESP_TASKD_EVENT_PRIO = ESP_TASK_PRIO_MAX - 5`, `esp_task.h:35` gives  <!-- check-docs: ignore-line -->
> `ESP_TASK_PRIO_MAX = configMAX_PRIORITIES`, and `FreeRTOSConfig.h:81` gives  <!-- check-docs: ignore-line -->
> `configMAX_PRIORITIES = 25` → **priority 19**. `sdkconfig:225` gives
> `CONFIG_ARDUINO_EVENT_RUNNING_CORE=1` → **core 1**. Both halves read from the shipped SDK, not
> inferred from the default.
>
> **What that invalidates.** §1.1 says the priority-2 pump task "preempts all three others… the
> single most dangerous edge in the system". A priority-19 context on the same core preempts **all
> four**, in every build, at any instruction — including mid-`portENTER_CRITICAL_SAFE`-adjacent
> sequences the pump task cannot interrupt. It writes `discCount` / `lastDiscReason` / `lastDiscMs`
> / `lastGotIpMs` (read by `logHeartbeat.h:105` and `debug/serialConsole/cmdGet.cpp:83-87` on loopTask), mutates three
> non-`volatile` file statics (`s_winStartMs`, `s_winLines`, `s_suppressed`), and calls
> `Serial.print` — a resource loopTask also owns. The code *knows*: `wifiDiag.cpp:64-65` carries a
> "(VE-8: the handler runs on the WiFi event task; interleaved printf tears lines)" note. The
> contract did not.
>
> **The core-0 one is narrower but sharper.** `promiscCb` is registered via
> `esp_wifi_set_promiscuous_rx_cb` (`wifiDiag.cpp:233`) and therefore runs on the WiFi driver task,
> which `sdkconfig:1033` pins with `CONFIG_ESP32_WIFI_TASK_PINNED_TO_CORE_0=y`. It performs
> read-modify-write on seven fields of `beaconStats` while `debug/serialConsole/cmdGet.cpp:137-144` reads all seven on
> loopTask, unlocked — a genuinely **simultaneous** access, and a torn multi-field snapshot by
> construction. It is `#ifdef SERIAL_DEBUG` only, which bounds the blast radius but not the
> framing error: §1.1's "core 0 runs the WiFi/lwIP stack" is no longer the whole truth, because
> this project now puts *its own* code there.

### 1.1 The fact that reframes everything (corrected 2026-08-26, TASK-541)

**Five of the six contexts are pinned to core 1; one is not.** `loopTask`, `spotifyTask`,
`dataTask`, the `wrAudio` pump and `arduino_events` are all on core 1 and are time-sliced on one
CPU — there is **no true parallelism among these five**. The WiFi driver task is the exception:
`sdkconfig` pins it to **core 0**, so it runs genuinely in parallel with all five of the others, not
merely interleaved with them. Core 0 otherwise runs the WiFi/lwIP stack, which is why the original
"core 0 runs the WiFi/lwIP stack" framing was reasonable in 2026-08-16 — this project's own code
(`promiscCb`, debug builds only) now runs there too, which is exactly what the four-context count
missed.

Consequences that follow, corrected for six contexts, and split into the two kinds of danger the
original single "most dangerous edge" sentence conflated:

- **Among the five core-1 contexts, every race is a preemption race, not a simultaneous-access
  race.** A non-atomic sequence that is never preempted mid-sequence is safe *by scheduling*, which
  is why some of this code has survived without locks — this part of the original claim still
  holds, just over five contexts instead of four.
- **The most dangerous *preemption* edge is no longer the pump task.** `arduino_events` runs at
  priority **19** — strictly above the pump task's 2 — on core 1, **in every build, not just
  debug**, and it preempts all four other core-1 contexts (including the pump task itself) at any
  instruction. It is the edge R4's motivating example (the pump task) understated: a context this
  document did not know about can interrupt a `configASSERT`-guarded callback, a `portMUX`-adjacent
  sequence, or a `Serial.print` mid-line, and does so on production hardware today, not just in a
  debug build. `wifiDiag.cpp:64-65` already carries a code comment acknowledging the tearing risk
  ("the handler runs on the WiFi event task; interleaved printf tears lines") — the contract simply
  never counted the task that comment is about.
- **The most dangerous *race*, full stop, is not a preemption race at all.** `promiscCb` on the WiFi
  driver task (core 0, debug builds only) performs an **unlocked read-modify-write across seven
  fields of `beaconStats`** while `debug/serialConsole/cmdGet.cpp:137-144` reads all seven on `loopTask` — a genuinely
  simultaneous access on two different physical cores, with no scheduling relationship between the
  writer and the reader at all. Nothing about task priority makes this safe, because priority only
  orders contexts that share a core; a lock (or `portMUX`, matching the pattern `dataTask` already
  uses for its own cross-core-shaped result slots) is the only fix. This is narrower in blast radius
  than the `arduino_events` edge — seven debug-only stats fields feeding one `get` command, not
  four other contexts' worth of state — but it is the one edge in this entire document for which
  "safe by scheduling" is not merely unproven, it is categorically inapplicable. Ranking a single
  "most dangerous edge" across both categories is a category error; the honest statement is two
  edges, ranked within their own kind: **`arduino_events` is the worst preemption edge (production,
  all builds, priority above everything on its core); the WiFi driver task's `promiscCb` is the
  worst race of any kind (true concurrency, unlocked, debug builds only).**
- The three priority-1 tasks (`loopTask`, `spotifyTask`, `dataTask`) round-robin among themselves,
  as before — `arduino_events` at 19 preempts all three of them too, but does not change how they
  relate to each other. A priority-1 task that blocks without yielding still starves the other two
  — the TASK-285/288 watchdog family, unchanged by this correction.

> **Matrix correction.** `cross_feature_matrix.yaml` X015 states *"dataTask fetch functions … run on
> Core 0"*. That is **wrong**: `dataTaskStorage.cpp:117` pins to `APP_CPU_NUM` (core 1), and
> `git log -S'PRO_CPU_NUM'` shows it was never otherwise. The entry's *conclusion* (spinlock-published
> results) is right; its stated reason is not. Flagged to Developer — the matrix is the artifact of
> record and should not carry a false hardware claim.

> **CORRECTED — @Architect independent review, 2026-08-26 (R4). This gap is closed; §5 G4 goes with
> it.** TASK-491 landed the fix (`e2f70db`) and TASK-500 (2026-08-23) finished it — including a
> stray second "Core 0" in the same entry that TASK-491's original fix had missed. Verified at the
> text, not at the board (BP-067 — a closed row is not evidence the file changed):
> `cross_feature_matrix.yaml:238-257` today reads "same-core preemption race, not a cross-core one",
> cites `dataTaskStorage.cpp:117` and IFC-002 directly, and carries no "Core 0" claim anywhere.
>
> **A caution this document earned, though.** TASK-500's rewrite quotes IFC-002's "there is no true
> parallelism between them" and applies it *"for the whole system"*. R1 above shows that
> generalisation is false in debug builds. The over-broad phrasing originated here, in §1.1, and has
> already propagated one hop into the artifact of record.

## 2. Ownership table

Who owns each shared resource, and how other contexts reach it.

| Resource | Owner | Crossing mechanism | Evidence |
|---|---|---|---|
| `TFT_eSPI tft` / all rendering | **loopTask, exclusively** | none — no other context may draw | X005 |
| SPIFFS (`settings.json`, config) | loopTask | none | X011 |
| SD / FATFS volume | loopTask **and** pump task | FATFS VFS per-volume serialisation; an open `File` costs ~4.4 KB | **X052** |
| The one `Audio` object (1 DAC, 1 arena, 1 InBuff) | audio engine | `s_wrAudioMutex`; request/result posting | **X050**, X048 |
| Spotify TLS session (~40 KB) | `spotifyTask` | ref-counted `tlsYield()` / `tlsResume()` | **X010**, X028 |
| `dataTask` queue + result slots | `dataTask` | `portMUX` spinlock + seq/epoch identity | X007, X015, **X027** |
| `vu::` level / spectrum statics | pump task (**writer**) | single-writer, loopTask reads | X043, X044, X045 |
| WiFi radio | shared, unarbitrated | **none — see §5 G1** | X014 |
| `prLat`/`prLon` | write-through mirror of `prLocs[active]` | single writer path | X026, X035 |
| `playOrder[]` vs `viewOrder[]` | disjoint owners | never cross-written | X062 |
| App error state (`hasError()`) | the app instance | sticky member, shell only reads | X019 |

## 3. The rules

Each rule states the invariant, its evidence, and what breaks without it.

**R1 — At most one TLS session may be *establishing* at a time.**
`spotifyTask` holds a persistent `WiFiClientSecure` (~40 KB) between polls; a new handshake needs
~50–70 KB contiguous. Any other context opening TLS must first `tlsYield()` and must `tlsResume()`
on **every** exit path. *(X010, X028; TASK-222 is the case where a reviewer certified conformance
that did not exist.)* → M-CODEQUAL C2 replaces the manual discipline with a scope guard.

**R2 — Only `loopTask` touches the display.**
No other context may call `tft.*`, directly or transitively. The pump task's visualisation data
crosses as *numbers* (R5), never as draw calls. *(X005)*

**R3 — Only `loopTask` touches the playlist model, the file browser, settings, and SD *except* the
pump task's own open audio file.**
Two contexts on one FATFS volume is already the maximum; a third is a redesign. *(X052)*

**R4 — A callback that fires on the pump task may only set a flag.**
`audio_eof_mp3`, `audio_info`, `audio_showstreamtitle` and `audio_process_extern` all run **on the
pump task, at priority 2, with the engine mutex held**. Opening the next track from inside one
self-deadlocks. The flag is drained on `loopTask`'s next tick. *(X063; enforced by
`configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle)` per ADR-059 D12.)*

> **CORRECTED — @Architect independent review, 2026-08-26 (R3, R5). Two errors, and the second is
> the one §4's whole conclusion rests on.**
>
> **(a) `audio_process_extern` does not belong in this list — and this was already ruled, ten days
> ago, in this document's own interface.** It runs a rectified peak scan and a 19-band Goertzel on
> the pump task every decoded block (`audio/audioEngine.cpp:102-137`, read in full — the Goertzel
> loop is `s0 = mono + coeff*s1 - s2` over `vu::SPEC_BAND_COUNT`), writing `vu::lLevelRef()` /
> `rLevelRef()` and `vu::updateSpectrumBar()`. That is R5 mechanism 2, correct by construction, not
> a flag. @VE raised this as MAJOR on 2026-08-16; IFC-002 v2 split it into **I4a/I4b** and
> `test_plan.md:35` **discarded `T_CC_03`** because "the claim was false". **None of that came back
> here.** See R9 in §8 — this is a back-propagation failure, not a fresh finding.
>
> **(b) The assert does not enforce this rule.** Read `audio/audioEngine.cpp:63-80`: the *only*
> `configASSERT` in `app/src` (grep `configASSERT` — one hit) sits inside **`aeDrainEof()`**, the
> loopTask-side **drainer**, and asserts that the *drainer* is on loopTask. Not one of the four
> callbacks carries a check. Nothing prevents `audio_eof_mp3` from calling `connecttoFS()` — the
> exact self-deadlock X063 describes. What the assert actually enforces is *"this function runs only
> on loopTask"*, which is an **R2/R3-family** invariant, not R4's *"this callback may only set a
> flag"*. The verified fact (an assert exists, at ADR-059 D12) is real; the inference (therefore R4
> is enforced) does not follow, and §4's table and its "Only R4 is actually enforced" conclusion are
> built on it.

**R5 — Data crosses contexts by exactly one of four mechanisms.** Nothing else is permitted:

| # | Mechanism | Use | Example |
|---|---|---|---|
| 1 | `portMUX` spinlock + copy into caller storage | bulk results | `dataTask` result slots |
| 2 | Single-writer scalar statics | high-rate telemetry | `vu::lLevelRef()` |
| 3 | Mutex-guarded singleton | one hardware resource | `s_wrAudioMutex` |
| 4 | Post-a-request / poll-a-result | anything that would block | `wrPumpConnect` |

> **CORRECTED — @Architect independent review, 2026-08-26 (R7). "Nothing else is permitted" is
> stated over the wrong population, and mechanism 2's own flagship example does not satisfy
> mechanism 2.**
>
> **Population.** R5 enumerates crossings among the four contexts of §1. §1's correction shows there
> are six. `wifiDiag::onEvent` crosses from `arduino_events` to loopTask by writing four `volatile`
> counters plus three plain non-`volatile` statics, and by sharing `Serial` — none of which is M1,
> M2 as written, M3 or M4. `promiscCb` crosses from **core 0** by unlocked read-modify-write on a
> seven-field struct. Neither is a violation anyone committed knowingly; both are outside the set
> the rule quantifies over. A rule that says "nothing else" must first say "among whom".
>
> **Mechanism 2 has two writers.** M2 is defined as "exactly one writing context". Grep
> `lLevelRef()|rLevelRef()` across `app/src`: the pump task writes them at
> `audio/audioEngine.cpp:114-115`, and **loopTask writes them too** at `winamp/vuMeter.h:495-499` —
> `if (realAudio) { if (!playing) { lLvl = 0.0f; rLvl = 0.0f; } }`. The two writers are intended to
> be mode-exclusive, and the reachability of an overlap window (pump still feeding while `playing`
> has gone false, e.g. during teardown) is **untested** — that inference is *not* established here,
> and this correction does not claim a live race. What is established is narrower and still
> load-bearing: **the contract's named example of "exactly one writing context" has two**, so M2 as
> written does not describe the code it cites, and any assert built from M2's wording would fire.

> **RE-DERIVED — TASK-541, 2026-08-26. R5 does not hold as written; it is restated below rather than
> patched.** The population correction above (R7) says R5's mechanisms were enumerated over four
> contexts and the rule's "nothing else is permitted" needs to say "among whom" first. Working that
> through against the six-context table in §1: the two framework contexts do not merely fall outside
> R5's stated scope, they cross by two mechanisms neither M1-M4 nor any sensible fifth mechanism
> should bless as-is.
>
> - **`arduino_events` → `loopTask`.** Four `volatile uint32_t`/`uint8_t` counters
>   (`discCount`, `lastDiscReason`, `lastDiscMs`, `lastGotIpMs`) plus three plain non-`volatile`
>   statics (`s_winStartMs`, `s_winLines`, `s_suppressed`) written on `arduino_events`, read on
>   `loopTask` with no lock, no sequence number, and — for the three non-`volatile` statics — no
>   compiler guarantee the write is even visible promptly to the reader. `Serial` itself is also
>   shared, unarbitrated, between the two. This is not M2 (M2 requires exactly one writer *and* is
>   silent on whether the reader can observe a torn group of fields — here the four counters are
>   read together as a struct-like group at `debug/serialConsole/cmdGet.cpp:83-87` and `logHeartbeat.h:105`, so a
>   snapshot spanning a disconnect-then-reconnect transition can pair a new `lastDiscMs` with a
>   stale `lastDiscReason`). It is closest in shape to M2 but weaker: M2's contract implicitly
>   assumes a single scalar read in isolation (`vu::lLevelRef()` is read alone), not a multi-field
>   group read as one logical unit.
> - **WiFi driver task → `loopTask` (`promiscCb`/`beaconStats`).** Unlocked read-modify-write on
>   seven fields, read unlocked on a different core. This fits none of M1-M4 and cannot be waved
>   into any of them without changing the code: M1 needs a `portMUX` around both sides (this project
>   already has the pattern — `dataTask`'s own result slots), M2 needs exactly one writer (there is
>   one writer here, but M2 was never meant to cover cross-*core* access — nothing in a scalar-static
>   write is safe against a genuinely simultaneous writer on another core), M3/M4 don't apply to a
>   passive stats struct.
>
> **Disposition: R5 is restated, not merely re-scoped.** "Nothing else is permitted" still holds as
> the *design intent* — this document has never sanctioned inventing new ad hoc crossing shapes —
> but the two framework-context crossings are undocumented violations of that intent, not omissions
> in the rule's wording. Restated: **R5 governs every crossing among all six contexts in §1, not
> four. Data crosses by exactly one of the four mechanisms below; a crossing that does not fit one
> of them is a gap to close (bring the code into M1-M4), not a fifth mechanism to add.** Concretely,
> two gaps exist today and are new §5 items: `promiscCb`/`beaconStats` needs the M1 treatment
> (`portMUX`, mirroring `dataTask`'s own pattern for exactly this shape) — **G6**; and
> `wifiDiag::onEvent`'s four-counter group needs either a documented "torn snapshot is acceptable
> here because X" argument or a sequence-stamped M1-style publish — **G7**. Filed as **TASK-544**
> (implementation is out of scope for a docs-only task; TASK-541 only establishes that the gap
> exists and why).

**R6 — Every cross-context result carries identity.**
A monotonic `seq` (geocode) or `epoch` (PlaneRadar) echoed in the result, so a late reply to a
superseded request is discarded rather than applied. Staleness is not detectable by content. *(X027)*

> **CORRECTED — @Architect independent review, 2026-08-26 (R9). False as a universal — and this was
> a @VE **BLOCKER** ten days ago that never reached this file.** IFC-002 I5 was restated on
> 2026-08-16 to the conditional form ("*where a stale reply could apply against changed consumer
> state*") after @VE showed IFC-001's own message table records "none (single consumer)" for five of
> nine result types. Real set: **three of nine** — `stockChart` (symbol echo), `planeRadar` (epoch),
> `geocode` (seq). `test_plan.md:36` **discarded `T_CC_04`** on the same grounds. Read IFC-002 I5
> for the current rule; the sentence above is superseded, not merely imprecise.

**R7 — A mirror has exactly one writer path.**
`prLat`/`prLon` mirror `prLocs[prActiveLoc]`; consumers read only the mirror, and every writer of the
source updates it. Two mirrors now exist (`home-location-001` added one) — see §5 G3. *(X026, X035)*

> **CORRECTED — @Architect independent review, 2026-08-26 (R8). R7 does not hold for `prLat`/`prLon`
> *individually* today, so G3's question — "does it hold for the pair?" — is asking past the actual
> defect.** A designated single writer exists: `SettingsStorage::prSlotWritten()`
> (`settingsStorage.cpp:672-685`), whose own header comment claims to be "THE single implementation
> of the matrix — every prLocs slot writer calls this". Grepping every assignment to `prLat`
> contradicts the comment: **`PlaneRadarApp::_setActiveLoc()` writes the active mirror inline**
> (`apps/planeRadarApp.cpp:145-146`) and never calls the helper, and the load path writes it a third
> time (`settingsStorage.cpp:451-452`).
>
> The inline write is *defensible* — `_setActiveLoc()` changes which slot is active, and
> `prSlotWritten(slot)` gates on `slot == g_settings.prActiveLoc`, which is still the **old** slot at
> that point, so calling the helper there would silently no-op. That is exactly the finding: the
> helper's contract cannot express "the active slot changed", so a second writer path is *forced*,
> and the comment asserting there is only one is false. R7 should be restated as "one designated
> writer **per kind of mutation**", and `prSlotWritten()` should grow the missing case — otherwise
> G2's proposed assert has nothing well-defined to assert.

**R8 — A priority-1 task must not block without feeding the watchdog.**
Long blocking calls on `loopTask`, `spotifyTask` or `dataTask` starve the other two and trip the TWDT.
*(TASK-285, 288, 295.)* Bounded variants exist for exactly this reason — `tlsTryYield(timeoutMs)`
against `tlsYield()`'s 150 s ceiling *(TASK-430)*.

**R9 — Acquire is a latch, not a refcount, for `mb_arena`; release is idempotent.**
Multiple releases along different exit paths are the intended shape. *(M-CODEQUAL C2.)*

## 4. What enforces this today

| Rule | Enforcement | Strength |
|---|---|---|
| R4 | `configASSERT` on the loopTask handle | **runtime, strong** |
| R1 | comments + BP-031 | weak — TASK-222 proved it fails |
| R2, R3 | convention only | **none** |
| R5 | convention only | **none** |
| R6 | per-call-site code | medium |
| R8 | TWDT (detects, does not prevent) | post-hoc |

Only R4 is actually enforced. That asymmetry is the finding: the rule that got an assert is the one
that stopped recurring.

> **CORRECTED — @Architect independent review, 2026-08-26 (R3, R5). Both rows that carry a verdict
> are wrong, and the conclusion inverts.**
>
> **R4's row.** Per §3's correction (b), the one `configASSERT` in the firmware guards
> `aeDrainEof()`, the loopTask-side drainer — not the four callbacks. **R4 has no enforcement.** The
> "runtime, strong" assert is real, but it enforces an R2/R3-shaped rule (*this function runs only on
> loopTask*) that §4 does not have a row for. So the honest table is: **one rule of the R2/R3 family
> is enforced at exactly one call site; R4 is convention.**
>
> **R1's row.** "comments + BP-031, weak" is now stale in this document's favour. **TASK-458**
> (`15d3c55`) landed `spotifyTask::TlsYieldGuard` (`spotifyTask.h:206-245`) and **TASK-459**
> (`5225208`) migrated the audio engine's `s_aeSpotifyYielded` bool onto it; **TASK-495** (`1df8b33`)
> fixed the `fetchCrypto` divergence that blocked them. Counted today: **9 guard sites** — 8 in
> `dataTaskStorage.cpp` and the transferable static `s_aeTlsGuard` in `audio/audioEngine.cpp`. For
> those, R1 *is* guaranteed by construction. IFC-002's I1 row ("Not guaranteed by construction after
> TASK-458: that task is OPEN") is correspondingly out of date.
>
> **What survived the migration is the real R1 finding.** Two hand-paired sites remain:
> `dataTaskStorage.cpp:1335`/`:1440` (`fetchPlaneRadar`, one straight-line function, no early return
> between them — verified by scanning every `return` in 1327-1441: there are none, so this one is
> safe though unguarded), and — materially — **`WebRadioApp::_spotifyYielded`**
> (`apps/webRadioApp.h:339`): **one acquire** (`apps/webRadioApp.cpp:1362`) against **five releases spread
> over four functions** (`:250`, `:262`, `:1278`, `:1340`, `:1394`), held across ticks and across the
> CONNECTING state. That is the *same shape* TASK-459 retired — its commit message describes
> `s_aeSpotifyYielded` as "three release sites in three functions, none performing the acquire" — and
> it is strictly larger. It was not migrated, and no row tracks it. Filed as **TASK-542**.

## 5. Known gaps

- **G1 — the WiFi radio has no arbitration.** X014 records that `WiFi.scanNetworks()` during a live
  TLS session can disrupt it; TASK-436 found the converse (auto-reconnect's `esp_wifi_connect()` loop
  makes `esp_wifi_scan_start()` fail outright), and TASK-404 a third (NVS and SPIFFS connect attempts
  colliding). Three bugs, one missing arbiter. **This is the largest unclosed gap in the contract.**
- **G2 — R2/R3/R5 are unenforced.** A debug-build assert on the owning task handle, mirroring R4,
  would convert three conventions into checks for a few bytes.
- **G3 — two write-through mirrors now exist** (`prLat/prLon`, and home-location's lat/lon onto
  slot 0). R7 holds for each individually; whether it holds for the pair is untested. *(X035)*
- **G4 — X015 carries a false core assignment** (§1.1).

> **CORRECTED — @Architect independent review, 2026-08-26. Re-stated gap list.**
>
> - **G1 stands, but "three bugs" overstates it.** Verified each of the three separately. TASK-436
>   and TASK-404 are **closed with landed point fixes**, visible in source:
>   `settings/wifiSection.h:707` (`WiFi.setAutoReconnect(false)` before the scan, re-armed at `:639`
>   and on `leave()`) and the NVS→SPIFFS disconnect/settle interlock. **X014 was never an observed
>   bug** — read `cross_feature_matrix.yaml:209-220`: it rates the risk "a single missed poll rather
>   than a session breakdown — acceptable", and says outright "Not yet tested on DUT". So the true
>   shape is *two fixed collisions plus one untested hypothesis, each patched at its own call site,
>   with no invariant tying them together* — which still argues for an arbiter (OQ1's lean is right)
>   but not from the strength of "three bugs". Grepped for one: no `wifiArbiter`/`radioLock`/
>   equivalent exists anywhere in `app/src` or `docs/architecture`.
> - **G2 stands, and is cheaper than stated — but its premise is wrong.** G2 proposes an assert
>   "mirroring R4". Per §3(b) there is no R4 assert to mirror; the existing `aeDrainEof()` assert is
>   *already* the R2/R3 handle-comparison shape, so G2 is "apply the mechanism we already have to
>   more sites", not "invent one". G2's list is also **missing R4 itself**, which §4 wrongly credits
>   as enforced. Independently re-verified the precondition: grepping `tft\.` across
>   `spotifyTaskStorage.cpp`, `dataTaskStorage.cpp` and `audio/audioEngine.cpp` gives **zero** hits,
>   as does `SPIFFS|saveSettings|loadSettings` — I2/I3 hold today at the direct-call level, so an
>   assert would ship green. @VE's caveat still applies: it must walk one level of call-graph
>   closure to be worth anything.
> - **G3 is asking the wrong question.** See R7's correction: R7 fails for `prLat`/`prLon`
>   *individually* (three writer sites, one designated helper), so "does it hold for the pair" is
>   downstream of a defect in the singular case.
> - **~~G4~~ — CLOSED.** TASK-491 (`e2f70db`) + TASK-500 (2026-08-23). Verified in the matrix text,
>   not from the board. Drop this row.
> - **~~G5~~ — CLOSED, TASK-541 (this pass).** §1 now enumerates six contexts; §1.1 and R5 are
>   restated against them. **TASK-473's G2 is unblocked** — see TASK-473's own row for what that
>   unblocking means concretely.

- **G6 — NEW, TASK-541. `promiscCb`'s write to `beaconStats` is unlocked against a cross-core
  reader.** The one crossing in this document that is a true simultaneous access, not a preemption
  race (§1.1, R5's re-derivation). Needs the M1 (`portMUX`) treatment `dataTask` already uses for
  the same shape. Debug builds only, so bounded blast radius, but it is the only edge in the whole
  contract for which "safe by scheduling" cannot apply even in principle. Filed as **TASK-544**.
- **G7 — NEW, TASK-541. `wifiDiag::onEvent`'s four-counter/three-static group crossing to `loopTask`
  has no identity and no lock**, and is read as a logical group (`debug/serialConsole/cmdGet.cpp:83-87`,
  `logHeartbeat.h:105`), so a snapshot can pair fields from different disconnect/reconnect events.
  Needs either a documented "torn read is acceptable because X" argument or a sequence-stamped
  publish. Filed alongside G6 as **TASK-544**.

## 6. Verification

The contract is only worth writing if violations become detectable:

| id | Must be true | Method |
|---|---|---|
| `T_CC_01` | No context but `loopTask` calls `tft.*` | host — call-graph grep from each task body |
| `T_CC_02` | Every `tlsYield()` has a matching resume on all paths | host — after M-CODEQUAL C2, guaranteed by construction |
| `T_CC_03` | Pump-task callbacks set flags only | review + the R4 assert |
| `T_CC_04` | Cross-context results carry identity | review of every `poll*()` |
| `T_CC_05` | Task core/priority/stack matches §1 | host — grep the create calls; catches drift like G4 |

> **CORRECTED — @Architect independent review, 2026-08-26 (R9, R10). Two of these five were formally
> discarded by @VE on 2026-08-18 and this table never learned.** `docs/verification/test_plan.md:33-37`
> — VE's file, and the one that owns test ids — carries the dispositions:
>
> | id | VE ruling (`test_plan.md`) | this table |
> |---|---|---|
> | `T_CC_01` | **KEEP**, scoped to the three non-loopTask TUs + one level of call-graph closure | as written, minus the scoping |
> | `T_CC_02` | **KEEP but BLOCKED** on TASK-495 → TASK-458 | claims "guaranteed by construction" |
> | `T_CC_03` | **DISCARD — the claim was false** | listed unchanged |
> | `T_CC_04` | **DISCARD — the claim was false** | listed unchanged |
> | `T_CC_05` | **KEEP unchanged** | correct |
>
> `T_CC_02`'s blocker has since cleared — TASK-495 (`1df8b33`), TASK-458 (`15d3c55`) and TASK-459
> (`5225208`) have all landed — but "guaranteed by construction" is *still* not true, because of the
> two un-migrated sites in §4's correction; the guard makes it true for 9 of 11. `T_CC_05` is the
> one row worth running immediately: it would have caught the inverted `dataTask` stack figure and
> both drifted line citations in §1, and it has never been executed.
>
> The five ids also sit in `docs/verification/id_binding_exceptions.md:79-83` as **undeclared**,
> attributed to TASK-473. Whoever executes TASK-473 owns clearing that exception, not just the code.

## 7. Open questions

- **OQ1** — should the WiFi radio get an explicit arbiter (G1), or is documenting the three known
  collisions enough? Lean: arbiter. Three separate bugs is a pattern, not coincidence.
- **OQ2** — is the all-on-core-1 pinning deliberate or inherited? It makes reasoning easier but
  forfeits the second core entirely. If deliberate, it belongs in an ADR as a decision; if inherited,
  it is a load-bearing accident.
- **OQ3** — should R2/R3/R5 get debug-build asserts (G2)? Cost is a handle comparison; the R4
  precedent says the enforced rule is the one that stops recurring.

## 8. Independent review — @Architect, 2026-08-26 (BP-066)

**Scope.** Full independent (non-author) review, ten days after authoring. Every technical claim
re-derived from current source, from the pinned framework SDK, and from the tree at this document's
own add-commit (`ce0bbe2`) where the question was "was it ever true". Corrections to specific claims
are embedded as blockquotes at the claim (front matter, §1, §1.1, §3 R4/R5/R6/R7, §4, §5, §6); the
findings below are the ones with no single claim to attach to.

### R1 — the framing defect: §1 counts four contexts and there are six

The full derivation is in §1's second correction. Stated as a framing finding rather than a fact
correction: this document's own opening line for §1 is *"Measured from the source, not assumed"*,
and the measurement it took was of `xTaskCreatePinnedToCore` **call sites in `app/src`** — which
finds exactly the three tasks this project creates, plus `loopTask` by inspection. The contexts it
missed are the ones **the framework creates on the project's behalf** and into which the project
then registers a callback: `WiFi.onEvent()` and `esp_wifi_set_promiscuous_rx_cb()`. That is the
author's blind spot, and it is structural, not careless: *a grep for task creation cannot find a
context you did not create.* The correct measurement is a grep for **callback registration**, which
is what R5 (a rule about data crossing contexts) should have driven and did not.

The consequence is not hypothetical. §1.1 names "the pump task at priority 2 preempts all three
others" as *the single most dangerous edge in the system*, and that sentence is the load-bearing
premise for R4, R5 and the whole "safe by scheduling, not by construction" argument that IFC-002
restates. A priority-19 context, in every build, on the same core, preempting all four, is a
strictly more dangerous edge and is unmentioned in either document.

**Blocking, for one specific reason.** TASK-473's G2 sub-item proposes writing runtime asserts from
this model. Asserts encode a taxonomy into the binary; adding them against a four-context model is
the concurrency equivalent of M-TOOLING's directory-move problem — cheap now, expensive to unwind.
Filed as **TASK-541**, which must close first.

### R2 — the `dataTask` stack figure was wrong when written, and three checks passed it

`11 264 B (14 336 debug)` reads the `#ifdef` backwards; the gate is `WEBRADIO_ONLY`, not
`SERIAL_DEBUG` (§1). What makes this worth a holistic finding rather than a typo correction is its
audit trail: it was written here on 2026-08-16, copied verbatim into **IFC-002 §1** the same day,
and then `test_plan.md:37` recorded that @VE *"independently verified every figure — pinning,
priorities 1/1/2, stacks 10240/11264/8192/20480"*. Three passes over one number, and all three
read the **constant** and not the **condition** two lines above it. This is BP-067's exact failure
shape applied to a documentation figure rather than a review finding, and it is the strongest
argument in this review for `T_CC_05` being run as a script rather than re-read by a person.

### R3 — R4 is the one rule the document says is enforced, and it is not

Detail in §3(b) and §4. The finding in one line: **the assert is on the drainer, not the callback.**
`grep -rn configASSERT app/src` returns exactly one hit, inside `aeDrainEof()`. §4's closing
sentence — *"Only R4 is actually enforced. That asymmetry is the finding: the rule that got an
assert is the one that stopped recurring"* — is the document's most-quoted conclusion, is repeated
almost verbatim in IFC-002's enforcement table, and inverts the truth: what got the assert is an
R2/R3-shaped *task-identity* check at one call site, and R4's actual content (a callback may only
set a flag) has no check anywhere.

The underlying observation still survives, and is arguably strengthened: **the enforced thing is the
thing that stopped recurring, and the enforced thing is a handle comparison** — which is precisely
the mechanism G2 wants to spread to I2/I3. The document reached the right recommendation from a
mis-labelled premise.

### R4 — one gap is already closed and one is mis-framed

G4 closed via TASK-491 (`e2f70db`) and TASK-500 (2026-08-23) — verified in the matrix text, not from
the board rows (§1.1's correction). G3 asks whether R7 holds "for the pair" of mirrors when R7 does
not hold for the singular case (§3 R7's correction: `prSlotWritten()` claims in its own comment to be
"THE single implementation" and two other sites write the same mirror, one of them necessarily,
because the helper cannot express "the active slot changed").

### R5 — three of the corrections here are ten days old and were never back-propagated

This is the process finding, and it is the one to act on. On 2026-08-16 @VE reviewed **IFC-002** and
raised one BLOCKER and two MAJORs — all three against claims that **originate in this document**:

| @VE finding, 2026-08-16 | Landed in IFC-002 | Landed in `test_plan.md` | Landed here |
|---|---|---|---|
| I5 was a universal; real set is 3 of 9 (**BLOCKER**) | yes, v2 | yes — `T_CC_04` discarded | **no** — §3 R6 unchanged |
| I4 false about `audio_process_extern` (MAJOR) | yes — split I4a/I4b | yes — `T_CC_03` discarded | **no** — §3 R4 unchanged |
| I1 not "guaranteed by construction" (MAJOR) | yes | yes — `T_CC_02` blocked | **no** — §3 R1 unchanged |

Three artifacts were corrected and the fourth — the design document that *is* the source of all
three claims, and that §7 of IFC-002 points back to for "rationale, bug lineage and the mining" —
was left carrying the original false text. For ten days, `M-CONCURRENCY` §3 and `IFC-002` said
opposite things about the same two invariants, and a reader arriving through TASK-473's row (which
links the design doc first) would have read the wrong one.

**Why it happened is visible in the paper trail.** `ESCALATIONS-2026-08-16.md:118-135` records the
VE round being integrated at ~03:30 into commits `55913fd`/`bd7282d`, and the very next section
records the pass being cut off mid-verification at the usage checkpoint. The review was applied to
the *contract* because the contract was what VE reviewed. Nothing in the process says a correction
to an IFC must propagate back to the design doc that defines it — BP-065 covers code→doc, BP-066
covers review→doc, and neither covers doc→doc.

**This also refutes a claim in a sibling review.** M-TOOLING §8 R1 (2026-08-26) lists
"M-CONCURRENCY" among documents that "all have" review markers, from a grep of
`docs/architecture/designs/`. Re-run word-boundary today: `grep -Ew "CORRECTED|@VE|@Architect|@Developer|@QM"`
over this file returned **zero** before this pass. The review existed; it landed on the interface and
the test plan, not on the design doc. M-TOOLING's finding was right about the pattern and wrong about
this instance — corrected in place there.

> **Resolved, TASK-543, 2026-08-27.** The content gap this finding describes was already closed by
> this same review pass (the R4/R6/R1 blockquote corrections embedded in §3, above). What remained
> open was the process gap — nothing said a correction to an IFC must propagate back to its design
> doc — and that's now [BP-072](../../quality/best_practices.md#bp-072). Registered as decay mode D6
> in M-DOCLIFE (mechanically undetectable, same class as D5 — a heuristic check was considered and
> explicitly declined, see M-DOCLIFE-check-docs-spec.md §6).

### R6 — R1's discipline is now partly mechanised, and the residue is concentrated in one file

§4's correction has the numbers: TASK-458/459/495 landed `TlsYieldGuard`, 9 sites are guarded, and
the remainder is `fetchPlaneRadar`'s straight-line pair (verified safe: no `return` between
`:1335` and `:1440`) plus `WebRadioApp::_spotifyYielded` — 1 acquire, 5 releases, 4 functions, held
across ticks. The last is the largest instance of the exact pattern TASK-459 was created to retire,
it is in the app most likely to gain new exit paths, and nothing tracks it. **TASK-542.**

### R7 — status of the rules after re-measurement

| | Verdict |
|---|---|
| **R1** | **Holds; enforcement claim stale in the document's favour.** 9 of 11 sites now construction-guaranteed; the residue is TASK-542. |
| **R2** | **Holds, and re-verified.** Zero `tft.` hits in the three non-loopTask TUs. Unenforced, as stated. |
| **R3** | **Holds.** Zero SPIFFS/settings hits in those TUs; the pump task's SD use is confined to its own `File`. |
| **R4** | **Rule holds; both the example list and the enforcement claim are false** (§3). @VE ruled the example list false on 2026-08-16. |
| **R5** | **Holds for its four mechanisms; fails on completeness and on its own M2 example** (§3, R1). |
| **R6** | **False as written** — @VE BLOCKER, superseded by IFC-002 I5's conditional form. |
| **R7** | **Fails in the singular case** (three writer sites, one designated helper). |
| **R8** | **Holds unchanged.** `tlsTryYield(ms)` exists (`spotifyTask.h:193`) and the guard's timeout ctor encodes its contract (`:211`). |
| **R9** | **Holds unchanged.** `mb_arena_acquire()` is idempotent; the latch shape is as described. |

The §1 table's *values* also hold in full apart from the one inverted figure: pinning `APP_CPU_NUM`
at three sites, priorities 1/1/2, stacks 10240 / 8192 / 20480 and `-DARDUINO_LOOP_STACK_SIZE=20480`
were each re-read from source. The central claim of §1.1 — **all four named contexts share core 1,
so every race among them is a preemption race** — is true and is the most valuable thing in the
document. It is the *scope* of that claim, not the claim, that this review breaks.

### R8 — the open questions, answered where they can be

- **OQ1 (WiFi arbiter) — still open; lean still correct, argument needs restating.** "Three separate
  bugs is a pattern" is the wrong support (§5: two fixed bugs and one untested hypothesis). The
  better support is structural and is now stronger than when asked: with R1's correction, the WiFi
  radio is touched from **five** contexts — loopTask (`wifiSection.h`, `boot.cpp`, `cmdSet.cpp`),
  `arduino_events` (`wifiDiag::onEvent` observing), loopTask's supervisor (`superviseTick()`), the
  driver's own auto-reconnect loop, and, in debug builds, promiscuous mode on core 0. Nothing
  serialises them; the three point fixes are three different local disciplines. That is an arbiter's
  case without needing a bug count.
- **OQ2 (deliberate or inherited pinning?) — answerable now: inherited, then made load-bearing.**
  `spotifyTaskStorage.cpp:41` comments its choice as *"core 1; same as Arduino loop"* — i.e. it
  followed `loopTask`, which is on core 1 because `sdkconfig:220` says `CONFIG_ARDUINO_RUNNING_CORE=1`.
  `dataTaskStorage.cpp:117` and `audio/audioEngine.cpp:412` state `APP_CPU_NUM` with no rationale at
  all. So: **inherited from the framework default, never decided.** It has since become load-bearing
  — X015's correction (TASK-500) now reasons *from* it, and `audio/audioEngine.h:265` documents a
  branch as safe because "both pinned to `APP_CPU_NUM`". OQ2's own phrasing ("if inherited, it is a
  load-bearing accident") is therefore the answer, and it should graduate to an ADR **recording**
  the pinning rather than deciding it — the decision was made by a `sdkconfig` default in 2016.
- **OQ3 (asserts for R2/R3/R5) — yes, and the precondition is already green.** Both TUs greps come
  back clean (§5 G2), so the asserts ship without a fix-first phase. Two conditions: they must walk
  one level of call-graph closure (@VE), and they must not be written until TASK-541 fixes the
  context model. R5 in particular cannot be asserted as written — its M2 clause has two writers
  (§3 R5's correction).

### As-built / disposition (BP-065)

**Status `proposed` → `accepted`, with corrections, not as written.** The framing survives attack
where it matters: the ownership table is accurate (all 17 `X` citations resolve and say what is
claimed), R2/R3/R8/R9 hold unchanged, the four crossing mechanisms are a real and useful taxonomy,
and §1.1's preemption-race insight is correct for the contexts it names and is the reason this
document was worth writing. Leaving it at `proposed` after a review has run would be the worse error
— TASK-473 is live P2 work governed by it, and BP-066 makes an unreviewed document formally
uncitable, which is the state it has been in for ten days while being cited.

**Six claims in it are false and are struck at the point of use**: the "24 entries" provenance count
(front matter), the `dataTask` stack figure (§1), the four-context enumeration (§1), R4's example
list and its enforcement claim (§3, §4), R6's universal (§3), and R7's single-writer claim for
`prLat`/`prLon` (§3). Two of the six were already ruled false by @VE on 2026-08-16 and never
back-propagated. G4 is closed. **Anyone citing this document must cite the corrected figures.**

**One blocking defect.** §1's context model is incomplete in a way that falsifies §1.1's headline
edge and R5's quantifier (R1). **TASK-473's G2 must not execute until TASK-541 closes.** G1 and G3
are unaffected and may proceed, G3 with its scope corrected to the singular case.

**Filed from this review:** **TASK-541** (six contexts, blocks G2), **TASK-542**
(`WebRadioApp::_spotifyYielded` → `TlsYieldGuard`), **TASK-543** (doc→doc back-propagation gap,
process — for QM).

**Reviewer hit-rate, this pass (BP-066 requires tracking it):** 10 findings raised, all 10 verified
against source before filing; none withdrawn. Against the review brief's four suggested lines of
attack: *re-verify §1 against current source* — **confirmed**, one inverted value and two drifted
citations; *has anything landed that already closes G1/G2/G3* — **confirmed**, G4 closed outright
and R1's enforcement partly mechanised by TASK-458/459/495; *is there a defect in the framing
itself* — **confirmed**, R1; *is TASK-473 well-scoped* — **confirmed mis-scoped**, G2's premise is
wrong, G3 asks past the defect, G4 is done. The findings **not** on the brief, and the ones this
review would defend as new, are **R1** (the six contexts — the only blocking one), **R3** (the
assert guards the drainer, not the callback), **R5** (three @VE corrections never reached this file,
and M-TOOLING's own review recorded the opposite), **R2** (the stack figure, wrong through three
checks), and **R6** (`_spotifyYielded`). Ten of ten holding on a first-ever review of a ten-day-old
document is, per BP-066's own note, a signal about authoring pace rather than about review quality —
the second such reading in two days, on documents from the same one-day batch.

## 9. As-built — TASK-541 (2026-08-26, BP-065)

**Closes the blocking defect §8 R1 found.** §1's table now lists six execution contexts, not four:
`arduino_events` (priority 19, core 1, all builds) and the WiFi driver task (priority 23, core 0,
debug builds only) are added, each with independently re-derived — not copied from the review —
priority, core and citations. Every number and citation the review gave checked out exactly against
source, with one exception: the WiFi driver task's priority (23) lives inside a closed-source,
prebuilt library this checkout does not expose in source form, so it could be re-confirmed as
internally consistent (no `sdkconfig` option or header macro contradicts it) but not independently
re-derived from a grep the way every other figure in this document was — flagged in §1, not silently
asserted as re-verified.

**§1.1 is rewritten**, not patched. The old "pump task preempts all three others, the single most
dangerous edge" conflated two different kinds of danger once six contexts are counted: a preemption
edge (same-core, ordered by priority) and a true-concurrency edge (cross-core, unordered by any
priority). Restated as two rankings: `arduino_events` is now the worst *preemption* edge (priority
19, all builds, preempts four other contexts at any instruction — worse than the pump task's
priority 2 on every axis); the WiFi driver task's `promiscCb`/`beaconStats` access is the worst
*race* of any kind, because it is the one edge in the document for which "safe by scheduling" is not
merely unproven but inapplicable — it runs on a different physical core from its reader with no
ordering relationship at all.

**R5 is restated, not re-scoped.** Read against six contexts, R5's "nothing else is permitted" isn't
just missing a population statement — the two framework-context crossings genuinely don't fit any of
M1-M4, and blessing a fifth ad hoc mechanism would defeat the rule's purpose. Restated: R5 governs
all six contexts; a crossing that doesn't fit M1-M4 is a gap to close, not grounds for a new
mechanism. Two such gaps exist today, filed as new §5 items **G6** (`promiscCb` needs the M1/`portMUX`
treatment `dataTask` already uses) and **G7** (`wifiDiag::onEvent`'s counter group needs identity or
an explicit torn-read justification) — both tracked as **TASK-544**, implementation out of scope
here.

**IFC-002 propagated.** Its execution-context table, the "all four pinned to core 1" claim, the
"Known gaps" line and the version header are all corrected in the same commit — it previously
restated M-CONCURRENCY's pre-correction four-context model verbatim, inverted stack figure included.

**TASK-473's G2 is unblocked.** See TASK-473's own row in `tasks-architecture.md` for the disposition
— summarized: G2 was never asking for a new mechanism, only for the R2/R3 handle-comparison assert
(the one `aeDrainEof()` already uses) to be applied at more call sites; that is unaffected by the
context count. What *was* blocked was writing that assert set from a four-context mental model. With
six contexts named, G2 may proceed on its original I2/I3 scope; it should not be extended to assert
anything about `arduino_events` or the WiFi driver task specifically, since neither of those two
gaps (G6, G7) has a fix yet to assert against — asserting the *presence* of the gap is not the same
as closing it.

**Not found: a seventh context.** Re-checked the same mechanism the review used (framework-created
tasks with an app-registered callback) against every `*.onEvent(`, `esp_*_register*_cb`,
`esp_*_set_*_cb` and `xTaskCreate*` call in `app/src` and the pinned framework's `WiFi*.cpp`. No
third framework-owned context with app code running in it was found. This is not a proof of
completeness — a callback mechanism this pass didn't grep for could still exist — but no candidate
surfaced.

## 10. As-built — TASK-473 (G1/G2/G3) and TASK-542 (2026-08-26, BP-065)

**G1 — WiFi radio arbiter, scoped to the one gap that had no point fix.** Re-verified all three
citations before designing anything (per this task's own instruction): TASK-436 and TASK-404 are
closed, landed point fixes (`settings/wifiSection.h:707`/`:639`, boot.cpp's NVS→SPIFFS interlock);
X014 was never an observed bug (`cross_feature_matrix.yaml`: "not yet tested on DUT"). Grepping every
radio-mutating call site found exactly one that never got the `setAutoReconnect(false)`-before-scan
treatment the other three independently converged on: `set wifiScan` (`debug/serialConsole/
cmdSet.cpp`), a debug-only async-scan hook. A full new arbiter module was considered and rejected as
over-scoped for the one live gap — instead, the existing convention (silence auto-reconnect for the
duration of the radio op) was applied at this site, with the release moved to `get wifiScan`'s
completion branch (`cmdGet.cpp`) since the scan is async and the set-side call cannot know when it's
actually done. `WIFI_SCAN_RUNNING` is the only state left un-re-armed; every terminal state
(`WIFI_SCAN_FAILED` or a result count) re-arms.

**G2 — the aeDrainEof()-shaped assert, applied as what VE's disposition actually specified.** The
M-CONCURRENCY §5 text proposing a runtime "handle-comparison assert" was superseded by
`test_plan.md`'s VE disposition for `T_CC_01` (2026-08-16): "KEEP as an **automatable host test**...
closer in kind to `T_CQ_03`'s grep than to a checklist" — there is no live call site inside
`spotifyTaskStorage.cpp`/`dataTaskStorage.cpp`/`audio/audioEngine.cpp` to attach a runtime assert to
(that's the point — zero hits today), so the assert takes the form VE actually specified: a
documented, re-runnable grep, scoped to the three non-loopTask TUs plus one level of call-graph
closure into every project header they `#include`. Executed: zero `tft.` and zero
`SPIFFS|saveSettings|loadSettings` hits at both levels. `T_CC_01` and `T_CC_05` (never previously
executed) both PASS; `T_CC_02` is now unblocked and PASS by construction for 10 of 11 sites plus one
manually-verified straight-line pair, following TASK-542 below. Full results and the exact grep
commands are in `test_plan.md`'s `T_CC_*` table. The five `T_CC_0[1-5]` ids are cleared off
`id_binding_exceptions.md` (49 → 44 rows) — declared, not merely executed informally.

**G3 — `prSlotWritten()` grew the missing mutation case.** Per R7's correction: the helper's own
contract ("THE single implementation") couldn't express "the active slot changed" (its
`slot == prActiveLoc` test needs the new slot to already be current, which it isn't yet at the
moment of a switch), forcing every switch call site to duplicate the mirror-copy inline. Added
`SettingsStorage::prActiveLocChanged(slot)` as the matrix's second, explicit half — never touches
the home mirror, does not persist, same shape as `prSlotWritten()`. Routed all three prior inline
writers through it: `PlaneRadarApp::_setActiveLoc()`, `appsSection.h`'s `_prDeleteSlot()` fallback,
and `cmdSet.cpp`'s `set prloc active` Settings-side branch. Pure behavioral substitution — same
net writes, same order, verified by reading each site before and after.

**TASK-542 — `WebRadioApp::_spotifyYielded` → `_tlsGuard` (`TlsYieldGuard`).** Mirrors TASK-459's
`s_aeSpotifyYielded` migration exactly: the bare `bool` became a `TlsYieldGuard` member
(default `TlsYieldGuard::none()`), acquired once in `_play()` (`TlsYieldGuard()` — unconditional
yield, matching the old unconditional `tlsYield()` call) and released via move-assignment to
`TlsYieldGuard::none()` at every prior release site, reproducing the old `if (flag) { tlsResume();
flag=false; }` exactly (move-assignment's own `if (ok_) tlsResume();`). **Correction to this
document's own count, checked against source before editing**: §8 R6 and this task's filing both say
"4 functions" — actual count is **3** (`tick()`, two release branches; `_stopAudio()`, one; `_play()`,
the acquire plus two release branches) — 1 acquire, 5 releases, 3 functions. Not re-litigated further
since the count doesn't change the fix, only the doc's own arithmetic.

**Verified**: `run/check` 11/11 (all 6 firmware envs, `golden.sha256`, tool smoke, app-registry +
mem_layout staleness, check-docs including the cleared `T_CC_*` ledger rows). No DUT verification
specific to G1/G2/G3/TASK-542 beyond `run/check`'s build-time conformance gates — these are host-
verifiable-by-construction changes (grep-checked invariants, a compile-time guard-type swap, a pure
refactor of an existing settings-mirror path with identical net writes), not new runtime behavior
needing a DUT repro. `set wifiScan`/`get wifiScan` and `set prloc active` were not separately
DUT-driven this pass — flagged, not a claimed pass, if a future session wants that coverage.
