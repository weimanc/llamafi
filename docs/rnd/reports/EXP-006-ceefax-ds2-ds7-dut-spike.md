> Owner: R&D

### EXP-006 — 2026-07-29 — M-CEEFAX DS-2 (resource contention) + DS-7 (reconnect
### characterization) — DUT spike + long-running host observation

**Hypothesis (DS-2)**: a persistent second TLS socket (Ceefax WebSocket) held open
concurrently with `dataTask`/`spotifyTask`'s periodic TLS fetches reproduces the
heap/TLS starvation class already fought through for WebRadio (TASK-285/287/289).

**Hypothesis (DS-7)**: real-world Ceefax relay connection-drop frequency/duration
can inform a concrete `hasError()` sustained-failure threshold (M-CEEFAX DS-7),
rather than picking a number without data.

**Branch**: `rnd/ceefax` (new, isolated worktree — kept separate from the
concurrently-active `rnd/webradio-vis` work in the primary worktree to avoid any
branch/DUT collision; see the branching discussion earlier in this session).

---

#### DS-2 approach

Added a minimal, deliberately non-production spike:
- `app/src/ceefaxWsSpike.h` — a dedicated FreeRTOS task, started unconditionally
  from `setup()` (not gated behind any App's `resume()`/`suspend()` — worst-case
  always-on), holding one `WebSocketsClient` (heap-allocated, not static — see
  below) attempting a real WSS connection + handshake to the live Ceefax relay,
  with a 3s reconnect backoff matching `ceefax_client.py`'s.
- `[env:cyd2usb_winamp_debug_ceefaxspike]` in `platformio.ini` — scoped build env,
  `links2004/WebSockets@^2.7.3` dependency scoped to this env only.
- `app/tools/test_ceefax_ws_soak.py` + `run/ceefax-ws-soak` — soak driver reusing
  `test_fetch_stress.py`'s (TASK-248) exact fetch-cycling plan (teletext/stock/
  weather/crypto) so dataTask load is identical to the existing baseline tool,
  polling `get heap`/`get ceefaxSpike` throughout.

**Real build obstacles hit and fixed** (not just protocol/logic bugs — these are
worth recording since they'll recur for any future WebSocket-on-ESP32 work here):
- PlatformIO's default `lib_ldf_mode = deep+` fails to resolve
  `arduinoWebSockets`' own `#include <WiFi.h>` (confirmed: adding `WiFi` to
  `lib_deps` under `deep+` does NOT fix it; only switching to plain `deep`
  does, scoped to this env).
- Plain `deep` is less automatic than `deep+` about the *main sketch's own*
  transitive framework needs — switching modes broke `main.cpp`'s pre-existing
  `<ESPmDNS.h>` include (from `refreshToken.h`), fixed by adding `ESPmDNS`
  to `lib_deps` explicitly.
- A static-global `WebSocketsClient` overflows `.dram0.bss` even after basing
  the env on `cyd2usb_winamp_debug` (368 bytes over). Fixed with this
  codebase's existing "lazy malloc, once, never freed" convention (heap-allocate
  in `begin()` — see `feedback_dram_bss_static_buffers` memory). Reduced the
  overflow to 48 bytes, still over budget.
- The remaining 48 bytes: switched the spike env to extend **production**
  (`cyd2usb_winamp`) + `-DSERIAL_DEBUG` only (not the full debug env's
  `TOUCH_DEBUG_OVERLAY`/`CORE_DEBUG_LEVEL=1`) — the exact pattern the
  concurrently-running `rnd/webradio-vis` PROP-005 spike (`cyd2usb_winamp_vistap2`)
  already used for the same class of problem. Combined with `-DCORE_DEBUG_LEVEL=0`
  (IDF log verbosity, unrelated to the `SERIAL_DEBUG` get/set surface), this
  cleared the budget with comfortable headroom (38.0% RAM used).
- `run_serialdbg_tests.Dut`'s `_verify_debug_firmware()` (ADR-042 E1 gate)
  correctly rejects any ELF hash other than the standard `cyd2usb_winamp_debug`
  build — appropriate behaviour for real regression suites, wrong tool for a
  scratch build that's deliberately different. Wrote a minimal duck-typed
  `MiniDut` in the soak script instead of weakening that check.
- First soak run's heap readings were all zero — not a device issue (a direct
  raw-serial diagnostic confirmed `get heap` returns real, valid, changing
  values). Root cause: the fetch-phase plan fires several `send()`-only
  (fire-and-forget) commands between polls (e.g. `set teletextPage 601`); their
  ack lines, if any, sit unread in the serial buffer, and the next `get heap`
  silently picks up that stale JSON instead (same bug class
  `test_fetch_stress.py`'s `get_device_ip()` already guards against with
  `reset_input_buffer()` before sending — applied the same fix here).

---

#### DS-2 findings

**The spike's own WebSocket connection never stabilizes** — a separate,
unresolved bug, not the point of this experiment but worth recording: over an
8-minute soak, `connects=3, disconnects≈13+, msgs=3` — it connects a handful of
times, receives roughly one message each time, then drops, cycling on the 3s
reconnect backoff throughout. Root cause not isolated (candidates: cert
verification behaving differently under mbedTLS than under `openssl verify`
despite DS-4's chain-of-trust correction being confirmed correct; a bug in the
minimal handshake/keepalive logic; or the connection churn described below
being partly self-inflicted). Flagged as follow-up, not blocking this finding.

**Real, DUT-confirmed TLS contention — the spike's repeated connection *attempts*
alone measurably degrade unrelated TLS traffic.** Compared two DUT runs on
otherwise-identical firmware (same `cyd2usb_winamp_debug` base):

| | Baseline (no spike) | With `ceefaxWsSpike` running |
|---|---|---|
| Spotify poll failures observed | `http=403` (known external TASK-243 block) once, then one benign `stale connect fd=51 (no current tls error)` | Repeated `rc=-32512 SSL - Memory allocation failed`, **and** one `rc=-9984 X509_CERT_VERIFY_FAILED` — a failure mode never seen in baseline |
| dataTask fetch report | **6 hard failures / 8 min, 1 TLS-layer error line** (`run/stress`, unmodified — see numeric baseline below) | 25 hard failures / 8 min across all 5 fetchers, 11 TLS-layer error lines |

The qualitative shift matters more than the raw count: baseline's Spotify poll
failures are the already-accepted TASK-243 (external 403) and an occasional
benign stale-fd condition; with the spike running, Spotify starts failing with
genuine memory-allocation and certificate-verification errors — the same
*class* of failure already fought through for WebRadio (TASK-285/287/289),
now reproduced by a second continuously-*attempting* TLS client, even one that
never itself reaches a stable connected state. Heap itself did not show a
monotonic leak (`freeInt` oscillated 55-60K ↔ 108-109K across the 8-minute
soak, recovering each time — consistent with normal per-fetch allocate/free
churn, not exhaustion) and no device reboot occurred (confirmed: only the
initial boot marker appears in the full session log). The contention is in
TLS-specific resource (buffer pool / concurrent-session limits), not general
heap.

**Numeric baseline (2026-07-29, same session): done, not just recommended.**
Ran the *existing* `run/stress` tool (unmodified, no Ceefax code at all,
`cyd2usb_winamp_debug`) for the same 8 minutes, same 5-fetcher plan:

| | Baseline (`run/stress`, no Ceefax) | With `ceefaxWsSpike` running |
|---|---|---|
| crypto | 7/7 ok (200×7) | 0/6 ok (`-1`×6) |
| stock/heatmap | 4/7 ok (`-1`×3, 200×4) | 0/3 ok (`-1`×3) |
| stock/quote | 0/1 ok (`-1`×1) | 2/7 ok (`-1`×5, 200×2) |
| teletext | 10/10 ok (200×10) | 0/6 ok (`-120`×1, `-1`×5) |
| weather | 5/7 ok (`-120`×1, `-1`×1, 200×5) | 1/6 ok (`-1`×5, 200×1) |
| TLS-layer error lines | **1** | **11** |
| hard failures (total) | **6** | **25** |

~4× the hard failures, ~11× the TLS-layer error lines, over the identical
fetch-cycling plan and duration. Per-fetcher success rate collapses across
almost every category with the spike running (crypto and teletext go from
100% to 0%; weather from ~71% to ~17%). Sample sizes (`n`) differ slightly
run-to-run (natural variance in how many fetch cycles complete in 8 minutes,
not a controlled trial count) but the shift is large enough that this doesn't
change the conclusion. This closes the "qualitative only" gap — DS-2's
contention finding now has an exact number behind it, not just a table of
error strings.

**Follow-up investigated, found infeasible within current build system —
recorded so it isn't attempted again the same way.** The proposed fix
direction (reduce mbedTLS's per-connection buffer size, mirroring
`PATCH-MEMBUDGET-4`'s I2S DMA-ring reduction) does not transfer as directly as
it sounded. Checked this project's precompiled framework
(`~/.platformio/packages/framework-arduinoespressif32/tools/sdk/esp32/sdkconfig`):
`CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN=16384`, baked into the **precompiled**
`libmbedtls.a` this project links against — a compile-time value, not
reachable via project-level `build_flags` under `framework = arduino`
(PlatformIO's binary-framework mode; changing it needs rebuilding the
framework from source, a much bigger undertaking than this spike). Checked for
a *runtime* alternative — RFC 6066 Max Fragment Length negotiation
(`mbedtls_ssl_conf_max_frag_len()`) — also unavailable:
`MBEDTLS_SSL_MAX_FRAGMENT_LENGTH` support isn't compiled into this framework
build at all (`grep -i fragment` on the sdkconfig: zero matches), and
`WiFiClientSecure`'s `ssl_client.cpp` wrapper doesn't expose any buffer-size
configuration through the Arduino API surface either. **Unlike the I2S case
(a runtime `i2s_config_t.dma_buf_len` struct field, trivially adjustable), the
mbedTLS analog is a compile-time framework constant this project's current
build setup cannot reach without rebuilding the framework from source.** The
DMA-gate mitigation (already DUT-verified) remains the practical ceiling of
what's achievable without that much bigger commitment — a genuine open item
for anyone who wants full connection reliability, not a quick follow-up.

---

#### DS-2 root-cause follow-up (2026-07-29, same session): capacity ceiling, not a race — and a real mitigation

Chased the "spike's own connection never stabilizes" loose end further, since
the user asked directly whether DS-2 is solvable. Findings, in order:

1. **Ruled out cross-app contention as the cause of the spike's own failures.**
   Built a Spotify-disabled diagnostic variant
   (`cyd2usb_winamp_debug_ceefaxspike_noSpotify`, since removed — its question
   is answered) — with `spotifyTask` entirely absent, the spike *still* failed
   to connect 100% of the time over 2 minutes, identical pattern to the
   Spotify-present run. Not a scheduling race between two consumers; the
   spike's connection fails on its own.

2. **Found the real error by bypassing the library's own logging.**
   `WebSocketsClient`'s "connection ... Failed" message swallows the actual
   mbedTLS error. A raw `WiFiClientSecure.connect()` diagnostic (mirroring this
   codebase's own `certSentinel()`/`lastError()` idiom from
   `dataTaskStorage.cpp`) surfaced the real cause:
   `lastError() == -32512 "SSL - Memory allocation failed"` — the *same* error
   Spotify was hitting, occurring even completely alone. This coincided with
   free DMA-capable heap at ~35KB at the moment of the attempt (vs. ~62-105KB
   when other connections succeed earlier in boot) — a capacity ceiling, not a
   timing race: a fresh mbedTLS session needs more contiguous DMA-capable
   memory than is reliably free once the rest of the firmware (display,
   dataTask, spotifyTask) has claimed its share.

3. **A second attempt under this condition crashed the device** — Guru
   Meditation Error (LoadProhibited), not just a failed connection. A stronger,
   more serious finding than "TLS degrades": under the wrong memory
   conditions, a reconnect attempt can crash outright.

4. **Implemented and DUT-verified a mitigation**: gate whether
   `WebSocketsClient::loop()` gets pumped at all on
   `heap_caps_get_free_size(MALLOC_CAP_DMA)` clearing a threshold — an
   established connection keeps being served normally regardless (loop() still
   called), but reconnect attempts simply don't fire while memory is tight,
   since `loop()` is what advances the library's internal reconnect timer.
   Deliberately did **not** try to reimplement the library's own reconnect
   scheduling from outside (disconnect()+beginSslWithCA() on a manual timer) —
   that approach regressed further (attempts stopped even reaching the
   library's internal "connect wss..." log line) and was reverted in favour of
   this much smaller, non-invasive change. **Verified on DUT**: with the gate
   in place, no further crash occurred, and no further failed-connection log
   spam — the device correctly stopped attempting once memory was recognized
   as too tight.

5. **Important nuance the gate does NOT fully resolve**: a single failed
   connection attempt appears to permanently cost a few KB of DMA-capable
   headroom (observed 39968 → 37000 bytes after one failed attempt, not
   recovering for the rest of a 90s observation window) — consistent with
   fragmentation or an incompletely-freed mbedTLS buffer on failure, not a
   one-off. Since the gate's threshold (38000) sits close to steady-state idle
   free-DMA (~40000), the very first attempt can tip the budget just low
   enough that the gate then closes and *stays* closed, i.e. the connection
   may never actually establish in a given session even though nothing is
   crashing anymore. The gate is a correct, verified answer to "stop making it
   worse" — it is not yet a complete answer to "make the connection reliably
   succeed."

6. **Should have checked this project's own memory-budget system before
   empirically probing thresholds on hardware — checked afterward, found real
   prior art.** `app/mem_manifest.yaml` documents `ceiling.DMA = 48000` bytes —
   this project's own code-enforced DMA-capable-heap ceiling, validated by
   `run/check`'s `gen_mem_layout` gate. The empirically-found failure/success
   boundary above (fails ~35-40K, succeeds ~50-62K+) brackets that number
   consistently, not contradicting it — this could have been a starting point
   instead of something rediscovered via repeated flash-and-observe cycles.
   Notably, zero buffers are currently registered with `caps: DMA` in the
   manifest (every entry is `INTERNAL` or `ANY`) — the pool is entirely
   unclaimed by the formal budget system, consistent with
   `M-MEMBUDGET-memory-budget.md`'s own note that WiFi/LWIP/mbedTLS system
   overhead is "no [not freeable]" and out of the manifest's scope. More
   usefully: `EXP-010-membudget-spike.md` already fought this *exact* DMA
   scarcity once, for WebRadio's I2S audio path, measuring `lfbDma` at idle in
   essentially the same ~35-37K range found here. Their fix
   (`PATCH-MEMBUDGET-4`) is the concrete precedent for "reduce the per-consumer
   footprint" (finding 5's remaining gap): they halved the I2S DMA ring buffer
   (`dma_buf_len` 512→256), freeing ~24K of DMA headroom with no audible
   quality loss. mbedTLS has the direct analog —
   `CONFIG_MBEDTLS_SSL_IN_CONTENT_LEN`/`OUT_CONTENT_LEN` (default 16KB each,
   sized for full TLS records Ceefax's small JSON messages don't need) — the
   next concrete step for closing finding 5's gap, not a fresh idea.

---

#### DS-7 findings — complete (full 6h observation window)

`app/tools/ceefax_reconnect_observer.py` ran host-side (background, `--hours 6`)
against the live relay, holding page 100, logging every status transition.
**Full 6.00h window completed. Result: 1 outage total — the initial 7.5s
acquisition wait — and zero disconnects for the remaining ~5h59m52s.** Once
acquired, this connection did not drop even once across the entire session.

**Lean (final for this observation): `hasError()` threshold of "N≥2 consecutive
failed reconnect attempts"** (≈6s of continuous failure, two missed 3s cycles).
Given a full 6-hour session produced zero drops after acquisition, this
threshold has essentially no false-positive risk against *this* session's
behaviour, while still catching a genuine sustained outage within two retry
cycles.

**Real limitation, stated plainly, not glossed over:** this is one long
session, not many independent trials across different times of day / network
conditions — and because zero outages occurred (beyond the initial
acquisition), the observation says nothing about how the relay actually
*behaves* during a real multi-minute outage (does it recover cleanly? does
`initialpage`/carousel state need to be re-established from scratch? how long
do real outages tend to last when they happen?) — only that outages appear to
be rare. The proposed threshold is reasonable given the data available, not
proven against real outage recovery behaviour. If more confidence is wanted
before implementation, re-run the observer across a different time window
(different time of day, different day of week) rather than treating this one
clean session as conclusive.

---

#### Conclusions

1. **DS-2 answered: yes, real contention, DUT-confirmed with an exact number —
   and now understood as a capacity ceiling, not a scheduling race.** A second
   TLS client repeatedly attempting to (re)connect measurably degrades
   Spotify's TLS reliability: ~4× the hard failures, ~11× the TLS-layer error
   lines vs. an unmodified `run/stress` baseline over the identical 8-minute,
   5-fetcher plan, introducing a failure mode (cert-verify failure) absent at
   baseline. The root-cause follow-up traced this to insufficient contiguous
   DMA-capable memory for a fresh mbedTLS session once the rest of the
   firmware has claimed its share — the same "SSL - Memory allocation failed"
   error hits the spike's own connection even with Spotify entirely removed.
   This is the answer M-CEEFAX DS-2 needed before an ADR.
2. **DS-2 is solvable for crash-prevention (DUT-verified); the durable
   connectivity fix is real but currently out of reach without a bigger
   commitment than this spike's scope.** Gating whether the reconnect logic
   gets pumped at all on a free-DMA threshold stopped the crash and the
   failed-attempt log spam on this DUT — a real, working improvement, not just
   a theory. It does not yet guarantee the connection *establishes*: a failed
   attempt costs a few KB of DMA headroom that doesn't recover in-session, so
   the very first attempt can tip the gate closed for the rest of that
   session. The proposed durable fix has a proven precedent in this codebase
   (`EXP-010`/`PATCH-MEMBUDGET-4` reduced WebRadio's I2S DMA ring to free ~24K
   with no quality loss) but the direct mbedTLS analog
   (`CONFIG_MBEDTLS_SSL_IN_CONTENT_LEN`/`OUT_CONTENT_LEN`) turned out to be a
   **compile-time constant baked into this project's precompiled framework
   binary** — not reachable from project-level config the way I2S's
   runtime struct field was, without rebuilding the framework from source.
   Investigated and confirmed infeasible within this spike's scope, not
   abandoned without checking.
3. **The spike's own connection instability is now root-caused, not just
   flagged** — see the follow-up above. Not the same finding as #1's "spike
   causes contention" — it's the mirror image, "the spike is *also a victim*
   of the same tight memory budget," which is arguably the more important
   framing for anyone picking this up: this device's spare capacity for a
   *second* full-size TLS client is marginal at best, independent of exactly
   when it's attempted.
4. **DS-7 complete: drops are rare.** Full 6h session, 1 outage (7.5s initial
   acquisition), zero drops thereafter. `hasError()` threshold: N≥2 consecutive
   failed reconnects. Caveat stated plainly: one long session with zero
   observed outages tells us drops are rare, not how the relay recovers from a
   real one — that remains unverified.
5. **DECISION LOCKED 2026-07-29: accept best-effort connectivity, do not
   pursue the framework rebuild.** Both rebuild paths were scoped (switch the
   whole project to `framework = espidf`; fork-and-custom-build the
   precompiled Arduino framework package) — both real, bounded work, both
   judged disproportionate to a feature that isn't shipped or scheduled. This
   is a deliberate deferral, not an oversight: the crash-prevention mitigation
   (DMA-gated reconnect, DUT-verified) is the actual shipped answer to DS-2.
   If full reliability is ever required, `CONFIG_MBEDTLS_SSL_VARIABLE_
   BUFFER_LENGTH` (not `MAX_CONTENT_LEN` — it shrinks allocated buffers to the
   actual negotiated record size with no protocol-visible change, a more
   targeted lever than what was first proposed) via a rebuilt framework is the
   recorded path — but re-opening that decision needs a concrete reason
   best-effort stops being acceptable, not just revisiting this report.

---

*Feeds: M-CEEFAX DS-2, DS-7 — all resolved and closed as of this report.*
