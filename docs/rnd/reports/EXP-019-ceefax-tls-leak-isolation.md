### EXP-019 — [2026-07-30] — Ceefax TLS DMA-leak isolation (PROP-008 Option C)

> Owner: R&D

**Hypothesis**: The ~42.6 KB DMA-capable-heap loss per failed Ceefax reconnect
(characterised in PROP-008's DMA-recovery test as a permanent, deterministic,
session-lifetime leak) is caused by the mbedTLS SSL I/O buffers
(`in_buf`/`out_buf`, `CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN=16384` each) never
being freed because the teardown cleanup (`stop_ssl_socket()`) is skipped —
the Links2004/arduinoWebSockets `#864` mechanism ("`WStype_DISCONNECTED` never
fires when the remote goes unresponsive mid-session → the cleanup that frees
the buffers never runs"), as reframed by the parallel upstream-research pass
(commit `3cb1cd0`).

**Approach**:
1. Static trace of the teardown/free paths. **Note the file that actually
   matters**: this project *vendors its own* `app/lib/WiFiClientSecure/`
   (where `PATCH-001`/`PATCH-003` live) — PlatformIO compiles that, **not**
   the framework copy under `~/.platformio/packages/...`. (First instrumentation
   pass wrongly edited the framework copy; probes never appeared because that
   TU isn't linked — `strings firmware.elf | grep LEAKPROBE` = 0 was the tell.)
   - `start_ssl_client()` (vendored) has **no** free-on-error: every handshake
     error/timeout path is a bare `return handle_error(ret)` / `return -1`
     after `mbedtls_ssl_setup()` has already allocated the buffers.
   - The only path that frees them is `stop_ssl_socket()` (→ `mbedtls_ssl_free`),
     reached via `~WiFiClientSecure()`/`stop()`, i.e. only on a real teardown
     or the next attempt's `delete _client.ssl`.
2. Instrumented the **vendored** `ssl_client.cpp` with `ets_printf` probes
   (bypasses `CORE_DEBUG_LEVEL`, which suppresses Arduino `log_e` in this
   build) at: `ssl_setup OK`, `handshake ERROR`, `handshake TIMEOUT`,
   `handshake SUCCESS`, and `stop_ssl_socket CALLED` — each with
   `heap_caps_get_free_size(MALLOC_CAP_DMA)`. Verified present in the ELF
   (5 strings) before trusting a run. Drove `switchApp 8/0` over serial across
   visits, captured probes + `ceefax` DIAG/gate + `WStype` + `get heap`.

**Outcome** (instrumented, 2-visit run):
- **`stop_ssl_socket` is called constantly** — cleanup is *not* skipped. This
  directly contradicts the "cleanup never runs" mechanism, at least under the
  instrumented timing.
- **TLS handshakes SUCCEED repeatedly** (`handshake SUCCESS` many times) then
  get torn down within the same reconnect attempt — the failure is *post-TLS*
  (WebSocket-upgrade layer), not a TLS handshake failure. Rapid
  connect→handshake-success→`stop_ssl_socket` churn.
- **`freeDma` oscillates violently**: 66240 → 6152 → 74856 → 19048 → 33504 →
  74856. It hit **6152** once — that transient low (not a permanent leak) is
  the real crash exposure the original Guru Meditation hit.
- **End state is variable**: visit 1 ended depressed (`freeDma=33504`), visit 2
  recovered (`freeDma=74856`). Not a deterministic plateau.
- Contrast: the earlier **uninstrumented** DMA-recovery runs (PROP-008)
  showed a *stuck* plateau (~34052) with no `WStype_DISCONNECTED` and no
  recovery. That regime is real but **metastable** (gate latches closed after
  a heap dip, so no further churn fires to trigger the recovering cleanup),
  **not** a hard unfreed allocation.

**Two confounds prevent a clean verdict**:
1. **Observer effect** — the probes are blocking `ets_printf` UART writes
   inserted into the hot connect path (~9 per cycle); they materially change
   timing and plausibly change whether disconnects get detected / cleanup
   fires. So the instrumented "cleanup runs / memory recovers" regime cannot
   be assumed equal to the uninstrumented behaviour.
2. **Network variability** — the instrumented session had TLS handshakes
   *succeeding* (relay reachable/responsive); the earlier clean sessions had
   them *failing* (`hasError` latched, no `WStype_CONNECTED`). Different
   regimes, same day — consistent with this project's WiFi/relay-variance
   history.

**Conclusion**: **Inconclusive on the exact free-path mechanism, but it
invalidates the earlier confident model.** The "permanent, deterministic
~42.6 KB session-lifetime leak that never returns" (as written into PROP-008 /
ADR-057 / TASK-374) is **not robust** — it is one metastable, network-dependent
regime among several. In other regimes `stop_ssl_socket` runs freely and DMA
oscillates and recovers. The consistent, robust facts are narrower: (a) each
connect attempt transiently allocates ~16–47 KB of DMA-capable heap; (b) under
churn `freeDma` can dip dangerously low (6152 observed) — the actual crash
risk, which the DMA gate exists to bound; (c) whether a session ends depressed
or recovered is variable and network-dependent, not a fixed cost.

**Recommendation**: **Continue exploring — but escalate direction first.** The
fix is *not* the obvious "add a `stop()`/cleanup call" (cleanup already runs).
Two non-intrusive next steps, neither taken this session:
- Re-measure with **out-of-band** instrumentation (a heap-low-water counter
  updated in the connect path and read via `get heap`/a status var — *no*
  blocking prints in the hot path) to get observer-effect-free dynamics, ideally
  across several sessions to average out network variance.
- Check Links2004/arduinoWebSockets for a release newer than the pinned
  `2.7.3` that addresses `#864`/`#373`; a library bump may be cheaper than any
  local patch, and sidesteps the whole detection-gap question.

**Follow-up (2026-07-31) — lead (a) [library bump] CLOSED, dead end.** Checked
upstream: the PlatformIO registry's latest `links2004/WebSockets` is **2.7.3 —
exactly what we already run** (GitHub's latest *release* is only 2.7.2; 2.7.3 is
the registry high-water mark). **#864 "Disconnection detection issue" is still
OPEN** — no fix in any release. Master has 10 unreleased commits since 2.7.2;
only `#980` "Fixing reconnect failure after pong Timeout" is adjacent, but it's
a pong-timeout reconnect fix, not our post-TLS WS-upgrade churn, and cherry-
picking an unreleased master commit is riskier than a release bump. **There is
nothing newer to bump to and the relevant bug is unfixed upstream.** Remaining
live options are therefore lead (b) [out-of-band re-measurement] or Option A
[accept] — the latter now more defensible since EXP-019 reframed the cost as
variable/metastable/gate-bounded with no crash, not a hard permanent leak.

## Lead (b) — out-of-band measurement (2026-07-31) — RESOLVES the leak question: there is no leak

Instrumented the **vendored** `ssl_client.cpp` with *inline counters only* (no
UART in the hot path → no observer effect): `g_leak_setup` (mbedTLS `ssl_setup`
succeeded = I/O buffers allocated), `g_leak_stop` (`stop_ssl_socket` entered =
buffers freed), handshake ok/err/tmo, and a `freeDma` low-water. Exposed via a
new out-of-band `get ceefaxLeak` command; drove 3 Teletext visits snapshotting
counters + `get heap` before/after each (all reads on `loopTask`, never touching
the pump task's connect path). Caveat: counters are global to *all* TLS
(Spotify/dataTask share `ssl_client.cpp`) — per-visit deltas and the
`outstanding` trend are the signal, not absolute counts.

**Result — no leak, definitively:**
- **`outstanding` (`setup − stop`) is persistently ≤ 0** (−1, −4, −4, −1), never
  climbs. `stop_ssl_socket` runs as often as or *more* than `ssl_setup` — every
  allocated SSL context is freed (stop ≥ setup is the healthy state; `stop()`
  also fires on connects that never reached `setup`). No accumulation.
- **`freeDma` at rest (Spotify, Ceefax torn down) RECOVERS every visit** —
  33796 / 34020 / 35156, all **≥ the 30908 baseline** (trending up). Memory comes
  back when you leave Ceefax.

**This reconciles the whole arc.** The earlier uninstrumented "stuck at 34052
forever / permanent ~42.6 KB / not window-bounded" (`7cc06b1`) was the
**metastable artifact** — the gate latches closed after a heap dip so no further
churn fires the recovering cleanup, making a momentary working level look
permanent. Clean out-of-band, it plainly recovers. **So Option A's original
"degradation bounded to the active-Ceefax window" framing is essentially correct
after all** — the TASK-374 review's "definitively false" was itself wrong,
based on the metastable run.

**Actual Spotify-degradation mechanism, captured live** (full-log run):
```
[ceefax] attempt#1 DMA before(free=66284 largest=21492) after(free=19252 largest=12276)
[ceefax] reconnect gate CLOSED (low DMA) freeDma=19768 lfbDma=12276
[spotify.tls] after -1: rc=-32512 'SSL - Memory allocation failed'
```
Ceefax's connect churn transiently starves DMA-capable heap; Spotify's
**un-gated** TLS poll then can't allocate its ~16 KB buffers → `SSL -32512`.
Transient contention, not a leak; Spotify recovers on its next poll.

**Residual real risk — intermittent low-DMA crash (not a leak).** One run
rebooted mid-visit-3 after `freeDma`/`lfb` dipped to 16256/8180 (counters reset,
~10 s unresponsive); a second full-logged run at the same depth did **not**
crash (Spotify just took `-32512`). So the deep transient dips can occasionally
crash rather than degrade gracefully — the same crash-under-low-DMA class the
DMA gate exists to bound (PROP-008 soak 1: 1 crash; soak 2: 0). Gate mitigates,
doesn't fully eliminate.

**Conclusion (updated)**: **Validated — no memory leak.** The "leak" framing is
retired. Real residue: (1) transient DMA contention while on Ceefax makes
Spotify's poll fail (`-32512`) intermittently, bounded to that window and
self-recovering; (2) at the deepest dips it can occasionally crash instead of
degrade. `TASK-375`'s "recover the leak / add `stop()`" premise is **moot**
(no leak; `stop` already runs).

**Recommendation (updated)**: **Option A (accept)**, with the intermittent crash
as the only non-cosmetic caveat. Any further hardening is **gate-tuning** (raise
`kMinLargestFreeBlockForConnect` / lower `kMaxConsecutiveAttempts` to keep `lfb`
above Spotify's ~16 KB need during churn), *not* a leak fix. Instrumentation
reverted; prod reflashed; tree clean.

## Functional verification (2026-07-31) — Ceefax does NOT connect on the DUT; this reverses the Option-A acceptance

All the above characterised the *coexistence cost* of Ceefax. It never verified
Ceefax actually **works** on the device — and a direct functional test (prompted
by the human: "I've never seen Ceefax working on the DUT") shows **it doesn't.**

- **Never connects.** Two patient DUT observations (fresh boot; and a settled
  90 s-after-boot switch): `ceefaxStatus.connected` stayed **false** the entire
  time, only `WStype_DISCONNECTED` ever logged, never `WStype_CONNECTED`, and no
  page was ever acquired. In the settled run all 5 reconnect attempts fired with
  **ample memory** (freeDma 62–65 K, `lfbDma`=49140 ≫ the 20 K floor) and each
  DIAG before/after barely moved (~3 K) — i.e. the attempts fail **early**
  (before `ssl_setup` allocates the big TLS buffers: a TCP/handshake/WS-upgrade
  or library-throttle failure, **not** memory), then hit `kMaxConsecutiveAttempts`
  and log "giving up … this session" — no retry until the app is re-entered.
- **Crashes under contention.** The fresh-boot run (Ceefax + Spotify token-
  refresh poll + a WebRadio station fetch all doing TLS at once) **crashed the
  device in ~18 s**: `Guru Meditation Error: Core 1 panic'ed (LoadProhibited)` →
  `rst:0xc (SW_CPU_RESET)` — at freeDma≈65 K (a null-deref, not OOM; same class
  as PROP-008 soak-1's `start_ssl_client`/`strlen` crash).
- **The relay is fine — the device is the problem.** From the host, the exact
  endpoint (`wss://internal.nathanmediaservices.co.uk/websockets/ceefax`) DNS-
  resolves, TLS-verifies (`Verify return code: 0 (ok)`), and completes the
  WebSocket upgrade: `HTTP/1.1 101 Switching Protocols` with a valid
  `Sec-WebSocket-Accept`. So this is a **firmware/integration failure against a
  working relay**, not an upstream outage.

**This reverses the Option-A acceptance.** A feature that never connects to a
working relay and can crash the device within seconds of use is **broken**, not
a "documented limitation." The leak analysis above stands (there is no leak),
but it was answering the wrong question — the milestone cannot be closed/accepted
until Ceefax actually connects on this board.

**Leading hypothesis for the no-connect** (unconfirmed): double reconnect
throttle. Our pump calls `_ws->loop()` once per `kRetryIntervalMs` (15 s), and
`WebSocketsClient::loop()` *also* early-returns if `(millis()-_lastConnectionFail)
< _reconnectInterval` (also 15 s). Out of phase, most of our "attempts" may be
loop() calls the library skips → few/no real connects happen, yet each burns one
of the 5-attempt budget → "gives up" having barely tried. The always-on spike
(`ceefaxWsSpike.h`, which DID connect for 6 h in EXP-006) pumps `loop()` every
tick with no such gating, which is consistent with this. Needs confirmation.

**Branch**: master (per this project's work-on-master convention; RnD-branch
discipline in `rnd.md` is overridden here — instrumentation was scratch,
reverted, never committed).

**Notes**:
- Reconciles with `3cb1cd0`: the upstream `#864` match is still the best
  *candidate*, but this pass's direct observation (cleanup *does* run under
  instrumentation) means the "detection-gap → cleanup-skipped → leak" chain is
  **not** cleanly confirmed and may be wrong in the fast (uninstrumented) path.
  Treat it as a hypothesis, not a settled root cause.
- All instrumentation reverted; both edited files (framework + vendored
  `ssl_client.cpp`) restored; prod firmware reflashed; `git status` clean.
- Scratch harnesses: `dma_recovery.py`, `capture_leak.py`, `capture_leak2.py`
  (session scratchpad, uncommitted).
