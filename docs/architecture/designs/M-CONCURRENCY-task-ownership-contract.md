# Design — M-CONCURRENCY: the task-ownership contract

> Owner: Architect
> Status: **proposed** — 2026-08-16
> Date: 2026-08-16
> Feeds: a future ADR; promotes to `docs/architecture/interfaces/IFC-002`
> Tracked-as: TASK-473
> Registers: no new feature id — this documents existing behaviour.
> Mined from: the 24 `shared_state` / `resource_contention` / `conflict` entries in
> `cross_feature_matrix.yaml`, plus the TASK-287/289/293/295/299/404/430 bug lineage.

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

**R5 — Data crosses contexts by exactly one of four mechanisms.** Nothing else is permitted:

| # | Mechanism | Use | Example |
|---|---|---|---|
| 1 | `portMUX` spinlock + copy into caller storage | bulk results | `dataTask` result slots |
| 2 | Single-writer scalar statics | high-rate telemetry | `vu::lLevelRef()` |
| 3 | Mutex-guarded singleton | one hardware resource | `s_wrAudioMutex` |
| 4 | Post-a-request / poll-a-result | anything that would block | `wrPumpConnect` |

**R6 — Every cross-context result carries identity.**
A monotonic `seq` (geocode) or `epoch` (PlaneRadar) echoed in the result, so a late reply to a
superseded request is discarded rather than applied. Staleness is not detectable by content. *(X027)*

**R7 — A mirror has exactly one writer path.**
`prLat`/`prLon` mirror `prLocs[prActiveLoc]`; consumers read only the mirror, and every writer of the
source updates it. Two mirrors now exist (`home-location-001` added one) — see §5 G3. *(X026, X035)*

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

## 6. Verification

The contract is only worth writing if violations become detectable:

| id | Must be true | Method |
|---|---|---|
| `T_CC_01` | No context but `loopTask` calls `tft.*` | host — call-graph grep from each task body |
| `T_CC_02` | Every `tlsYield()` has a matching resume on all paths | host — after M-CODEQUAL C2, guaranteed by construction |
| `T_CC_03` | Pump-task callbacks set flags only | review + the R4 assert |
| `T_CC_04` | Cross-context results carry identity | review of every `poll*()` |
| `T_CC_05` | Task core/priority/stack matches §1 | host — grep the create calls; catches drift like G4 |

## 7. Open questions

- **OQ1** — should the WiFi radio get an explicit arbiter (G1), or is documenting the three known
  collisions enough? Lean: arbiter. Three separate bugs is a pattern, not coincidence.
- **OQ2** — is the all-on-core-1 pinning deliberate or inherited? It makes reasoning easier but
  forfeits the second core entirely. If deliberate, it belongs in an ADR as a decision; if inherited,
  it is a load-bearing accident.
- **OQ3** — should R2/R3/R5 get debug-build asserts (G2)? Cost is a handle comparison; the R4
  precedent says the enforced rule is the one that stops recurring.
