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

## 1. The four execution contexts

Measured from the source, not assumed:

| Context | Core | Prio | Stack | Created at |
|---|---|---|---|---|
| `loopTask` (Arduino) | 1 (`APP_CPU`) | 1 | 20 480 B (`-DARDUINO_LOOP_STACK_SIZE`) | framework |
| `spotifyTask` | 1 (`APP_CPU_NUM`) | 1 | 10 240 B | `spotifyTaskStorage.cpp:591` |
| `dataTask` | 1 (`APP_CPU_NUM`) | 1 | 11 264 B (14 336 debug) | `dataTaskStorage.cpp:1682` |
| `wrAudio` pump | 1 (`APP_CPU_NUM`) | **2** | 8 192 B | `audio/audioEngine.h:649` |

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

### 1.1 The fact that reframes everything

**All four contexts are pinned to core 1.** There is **no true parallelism between them** — they are
time-sliced on one CPU. Core 0 (`PRO_CPU`) runs the WiFi/lwIP stack, so parallelism exists between
the app and the network stack, but not among these four.

Consequences that follow directly, and that a reader assuming SMP would get wrong:

- Every race between these four is a **preemption race**, not a simultaneous-access race. A
  non-atomic read that is never preempted mid-sequence is safe *by scheduling*, which is why some of
  this code has survived without locks.
- **The pump task at priority 2 preempts all three others**, at any instruction. That is the single
  most dangerous edge in the system, and the reason for R4 below.
- The three priority-1 tasks round-robin. A priority-1 task that blocks without yielding starves the
  other two — the TASK-285/288 watchdog family.

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
> - **G5 — NEW, and blocking. §1 enumerates four execution contexts; there are six.** The omitted
>   `arduino_events` context runs application code at **priority 19 on core 1 in every build**, which
>   falsifies §1.1's "single most dangerous edge" and puts R5's "nothing else is permitted" outside
>   its own quantifier. Full mechanism-level derivation in §1's correction. **TASK-473's G2 must not
>   execute before this closes** — an assert set written against a four-context model bakes the
>   omission into runtime checks, which is the one operation that makes a framing error expensive to
>   undo. Filed as **TASK-541**.

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
