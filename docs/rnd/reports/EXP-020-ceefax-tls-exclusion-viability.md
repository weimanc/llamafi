### EXP-020 — [2026-07-31] — Ceefax TLS-exclusion viability (ADR-058 Option A) — noSpotify isolation

> Owner: R&D

**Status**: PARTIAL — executed 2026-07-31. Precondition cleared and the key
transport result landed (Ceefax **connects** for the first time), but the clean
near-1-way isolation was blocked by the CH340 `ttyUSB0↔1` flap wedging the board
mid-capture. See **Results** at the bottom. Server-frugal throughout (~a dozen
relay connects total).

---

**Question this answers**

ADR-058 asks whether M-CEEFAX is viable given three concurrent TLS consumers
(Spotify poll, WebRadio/dataTask, Ceefax) cannot fit a single ~77 KB
DMA-capable heap, and proposes **Option A** (pause the *other* consumers while
the user is on the Ceefax source). Before building A's dynamic
`tlsYield`/`tlsResume`-for-`dataTask` machinery, this experiment cheaply tests
**whether A's premise even holds** — i.e. does giving Ceefax the DMA pool
(mostly) to itself actually let it connect + acquire + render without crashing
or starving other TLS? It uses the already-existing `-DDISABLE_SPOTIFY` build as
a *static* stand-in for the exclusion, so no new firmware machinery is needed to
get the answer.

**Hypothesis**

The blocker is DMA-pool capacity, not a Ceefax bug (the connect-path crash is
already fixed — uninitialized `_client_cert`, commit 44b5fb0). So:
- With Ceefax given the pool (near-1-way), it will connect + acquire + render a
  page, crash-free, no `errno=11` → Option A's premise holds.
- If it fails even near-1-way, the pool is too small for *even Ceefax alone* →
  Option A cannot save it → ADR-058 **B** (framework/mbedTLS-buffer rebuild) or
  **D** (cut) is the real fork, and A's machinery should NOT be built.

**Prior data that shapes the design** (EXP-006 / EXP-019 isolation): with
Spotify fully disabled, `freeDma` still sat at **~36–37 KB** the whole time —
TFT_eSPI + WiFi + the MEMBUDGET arena + WebRadio/dataTask compete for the same
pool. So **`-DDISABLE_SPOTIFY` alone = a 2-way case (Ceefax + WebRadio)**, not
1-way. A true near-1-way test additionally requires WebRadio *idle*.

---

**Precondition (must verify first — otherwise the runs are meaningless)**

The device-side outbound-TLS throttle re-triggered by the 2026-07-31 session's
heavy testing must have cleared. Verify cheaply, one burst each:
1. Host still reaches the relay: `curl -s -o /dev/null -w "%{http_code}\n"
   --max-time 12 -H "Connection: Upgrade" -H "Upgrade: websocket"
   -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=="
   https://internal.nathanmediaservices.co.uk/websockets/ceefax` → expect `101`.
2. Device connect is NOT throttled: a single Ceefax attempt's DIAG line should
   show `attempt#1 DMA before(free≈58K…) after(free≈3–11K…)` — i.e. it allocates
   the ~55 KB mbedTLS pair (TCP+TLS succeeded). If instead `before`/`after`
   barely move (~3 KB, largest block unchanged), the device is still throttled →
   **stop, wait, do not proceed** (running now proves nothing and re-arms the
   limit).

---

**Approach / protocol**

Build (already compiles with the crash fix): `cyd2usb_winamp_debug_noSpotify`
(`app/platformio.ini:163`, `-DDISABLE_SPOTIFY`). Flash it, then use the harness
on the stable by-id symlink with `--no-reset` (see TASK-376 rig notes — the
CH340 flaps ttyUSB0↔1 and DTR/RTS reset drops the CYD into download mode):

```
~/.platformio/penv/bin/pio run -d app -e cyd2usb_winamp_debug_noSpotify -t upload \
  --upload-port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
sleep 6
python3 app/tools/ceefax_connect_check.py \
  --port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 --no-reset --secs 200
```

- **Run 1 — near-1-way (Ceefax gets the pool):** WebRadio **idle** (do not start
  a station). Switch to Teletext/Ceefax. This is the cleanest test of A's premise.
- **Run 2 — 2-way (Ceefax + WebRadio):** WebRadio **playing a station**. Same
  harness. Tests whether pausing only Spotify (the easy half of A) suffices, or
  whether `dataTask`/WebRadio must yield too.
- **Run 3 (optional contrast) — full 3-way:** the normal `cyd2usb_winamp_debug`
  (Spotify enabled) — the currently-failing baseline, for a clean before/after.

Metrics per run (from the harness + DIAG): `ever_connected`, `ever_acquired`,
`crashed`, `errno=11` occurrences, `freeDma` floor, time-to-acquire, pump-task
stack HWM (right-sizes the precautionary 16 KB stack while we're here).

---

**Pass/fail → ADR-058 decision mapping**

| Run 1 (near-1-way) | Run 2 (2-way) | Reading | Action |
|---|---|---|---|
| **FAIL** (no connect/acquire, or crash/`errno=11`) | — | Pool too small for even Ceefax alone | **Do NOT build Option A.** Escalate ADR-058 **B vs D** to human. Architect lean: **D (cut)**. |
| **PASS** | **FAIL** | Ceefax works alone but can't coexist with WebRadio | Option A must yield **both** Spotify *and* `dataTask`/WebRadio; the WebRadio-audio UX policy (ADR-058 A-subtlety 1) becomes **mandatory** — @PM call. |
| **PASS** | **PASS** | Pausing background TLS during Ceefax foreground is sufficient | **Green light for A.** Build the dynamic `tlsYield`-for-`dataTask` exclusion, hold it for the foreground session + a post-boot connect delay; then TASK-374 coexistence soak = Gate 2. |

Also, in ALL cases, Run 1/2 double as the first real check of **Gate 1** (does
the integrated build connect + acquire + render a page at all — never yet
observed). A total failure to connect+acquire even near-1-way, with the
Precondition confirming the device is NOT throttled, would itself be a
significant (and different) finding — debug the pagesearch/parse path, not the
transport.

---

**Deliverables**
- Record the runs' data in this report (promote Status PLANNED → DONE).
- Update **ADR-058** with the outcome and which fork (A / B / D) it selects.
- Hand to @PM (viability + WebRadio-audio policy if A) and @VE (does TASK-374's
  soak need a WebRadio-playing-while-on-Ceefax case for Gate 2?).

**Server discipline**: each run = one connection burst; space runs; abort the
moment the Precondition check shows the device is throttled. This experiment is
explicitly designed to answer the viability question with the *fewest* relay
connections, not a soak.

---

**Results — 2026-07-31 (PARTIAL)**

Executed against `cyd2usb_winamp_debug_noSpotify` (crash fix + servicing fix in,
commit 44b5fb0).

*Precondition — CLEARED.* Host still gets `HTTP/1.1 101` in 0.05 s. Device is no
longer throttled: `attempt#1 DMA before(free≈69412 largest≈49140) after(free≈
23088)` — it allocates the full ~46 KB mbedTLS pair (TCP+TLS succeeds), not the
~3 KB fast-fail seen while throttled. So the earlier block was indeed the
transient device-side rate-limit; it eased on its own.

*Headline win — Ceefax CONNECTS.* For the **first time in the whole M-CEEFAX
effort**, `WStype_CONNECTED` fires on the integrated build. This **validates the
servicing-window fix (TASK-376 bugs 1+2) end-to-end** — the 101 upgrade is now
read before the header timeout. Also **crash-free and no `errno=11`** across
these runs, confirming the uninitialized-`_client_cert` crash fix and the
`kServicingWindowMs < reconnectInterval` storm fence hold under real connects.

*Blocker to Gate 1 — the session drops within ~3 s, before a page is acquired.*
After `WStype_CONNECTED`, the connection tears down within ~3 s (`freeDma`
recovers to ~69 K = TLS buffers freed) and re-attempts ~every 15 s; `acquired`
never goes true. The Ceefax carousel needs 5–20 s+ to deliver a requested page,
so a 3 s session never survives long enough to render. **Gate 1 (render a page)
is NOT met** — but for a *session-lifetime* reason, not the capacity/crash
reasons this experiment set out to test.

*Why "Run 1 = WebRadio idle" wasn't truly 1-way.* Even with no station selected
(`get wrStation` → count 0), `dataTask` **auto-fetches the WebRadio station list
on boot** (`radio-browser.info`, paging offset 0/30, ~18 s of TLS), cycling
`freeDma` 6 K↔68 K and starving Ceefax's connect during that window. So
`-DDISABLE_SPOTIFY` + nominal-idle is still a **2-way** case at boot, not 1-way.
A genuine near-1-way test needs `dataTask` actually quiet.

*Root-cause lean for the ≤3 s drop — contention, not a protocol/session bug
(server-free code comparison).* The old spike `ceefaxWsSpike.h` (commit 56e96e8)
stayed connected **6 h**. Diffing its connected-state handling against
`CeefaxTeletextSource`: the `loop()`-every-tick-while-connected and the 5 s
`keepalive` are **identical**; the handshake (`service,<id>` / `ttx,true` /
`pagesearch`) is identical; both rely on the library's auto-PONG. The spike ran
in a **narrow** build (spike-only, no other TLS); the integrated build has
WebRadio/dataTask doing concurrent TLS. Since the connected-path code is the
same as the 6 h-stable spike, the most likely cause of the drop is **cross-app
TLS contention knocking over Ceefax's established session** — i.e. the exact
thing Option A removes — **not** a regression in the port. (Not *proven*: the
clean isolation that would confirm it — `dataTask` truly quiet, watch whether
the session then survives — was blocked by the CH340 flap this session.)

**Verdict against the decision table:** Run 1 could not be cleanly run
(near-1-way unreachable without quieting `dataTask`), so the A/B/D capacity fork
is **not yet decided**. What *is* established:
- Gate 1 is *close* — transport + servicing + crash are handled; the only thing
  between here and a rendered page is keeping the session alive long enough,
  which looks like contention.
- Option A's premise is **supported** (spike-code-identical + narrow-build-stable
  ⇒ contention is the differentiator), but **unconfirmed** pending a real 1-way.

**Recommended next step (pick one):**
1. **Cheapest confirmation:** a throwaway test build that stubs/deletes the
   WebRadio boot station-fetch (and keep WebRadio not-playing) → true ~1-way.
   If Ceefax then *stays connected and acquires a page*, contention is confirmed
   and Option A is validated to build. If it *still* drops in ~3 s with a quiet
   `dataTask`, there IS a session bug to chase (revisit keepalive/relay-close).
2. **Or go straight to Option A:** implement the `tlsYield`/`tlsResume`-for-
   `dataTask` exclusion held across the Ceefax foreground session (+ a post-boot
   connect delay so it never starts into the boot-fetch storm), then re-run this
   harness — a passing connect+acquire *is* Gate 1 and most of Gate 2.

Either path is server-frugal (one connect burst per check). The CH340 flap is
the practical tax — reset via esptool when the board wedges; use the by-id
symlink + `--no-reset`.
