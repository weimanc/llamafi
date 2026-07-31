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
