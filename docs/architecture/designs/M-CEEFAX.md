# Design — M-CEEFAX: NMS Ceefax Live Teletext

> Owner: Architect
> Status: **accepted, scheduled 2026-07-30** — see ADR-057. DS-6, DS-2, DS-7
>   all resolved. DS-2 (EXP-006): real TLS contention, root-caused to a
>   DMA-memory capacity ceiling; crash-prevention mitigation DUT-verified;
>   decision locked 2026-07-29 to accept best-effort connectivity, framework
>   rebuild explicitly not pursued — see DS-2. DS-7: full 6h observation
>   complete, 1 outage (initial acquisition), zero drops thereafter.
>   Implementation tracked as TASK-370 through TASK-374.
> Date: 2026-07-29 (design) / 2026-07-30 (scheduled)
> Feeds: ADR-057
> Feeds from: EXP-005, EXP-006

---

## Context / pain points

`nmsceefax.co.uk` is an enthusiast-run, "up-to-date" revival of the BBC's Ceefax
teletext service — real UK news/sport/weather pages, rendered and served the way
1990s teletext actually worked. It was suggested as a second teletext source
alongside the shipped NOS Teletekst app (M-TELETEXT). Unlike the SVT (Sweden) path
identified as the *recommended* second entry in M-TELETEXT DS-6, Ceefax was
unexplored before this spike.

A full protocol reverse-engineering + host prototype was completed (EXP-005). Headline
result: **the display pipeline is 100% reusable, the transport is 0% reusable.**
Ceefax is not a second row in the `teletextCountry` enum the way SVT would be — it is
a live WebSocket broadcast relay, not a page-addressed HTTP fetch, and needs its own
persistent-connection architecture. This doc lays out what adopting it would actually
require, so PM/Architect can decide whether it's worth scheduling against the
`teletextCountry` multi-country path already reserved in M-TELETEXT.

**This is not a build plan.** No firmware code has been written or scheduled. The
prototype lives entirely in `app/tools/` (host-side Python) and is meant to settle the
design questions below before anyone writes C++.

---

## What's proven (EXP-005 + host prototype)

- `app/tools/ceefax_client.py` — background-threaded WebSocket client implementing
  the reverse-engineered protocol (handshake, page-search, keepalive, live row/header
  assembly into a 25×40 grid).
- `app/tools/preview_teletext.py --source ceefax` — **not a separate tool.** Ceefax is
  a second source behind the existing NOS preview, sharing the render pipeline
  (`build_cell_grid`, colour palette, mosaic tables — untouched), the `Keypad` widget,
  the right-strip renderer, and the row-tap link scanner (`scan_links`/`find_row_link`,
  zero changes needed). Only fetch/nav are source-specific: a `navigate()` dispatcher
  picks synchronous NOS `load()` vs. non-blocking `CeefaxClient.goto()` +
  per-frame-poll, and `ceefax_extract_nav()` stands in for NOS's `extract_nav()` where
  there's no `pn=`/`ftl=` metadata to parse (see DS-3).
- End-to-end screenshot: BBC/Ceefax mosaic masthead, magazine index, working strip
  (prev/next via page±1, history back, subpage correctly dimmed), and a fastext bar
  with real parsed labels/colours (inert — see DS-3) — all pixel-correct, rendered
  through the NOS pipeline against live Ceefax data.

This validates the central design bet: **reuse at the render layer, not the fetch
layer.**

---

## Canvas geometry

Unchanged from M-TELETEXT — same 275×240 app canvas, same 6×8 px cell grid (40×25),
same 45 px taskbar strip. A `CeefaxApp` would slot into the same
`gen/teletext_layout.h`-style geometry, or share it outright if the two apps end up
sibling variants of one `TeletextApp` rather than two separate classes (see DS-6).

---

## Design space

### DS-1: Transport architecture

**Option A — Persistent WebSocket owned by a dedicated pump task (lean)**

Model on `WebRadioApp`'s `wrEnsurePumpTask()`/`wrTeardownPumpTask()`
(`app/src/webRadioApp.h`): a `xTaskCreatePinnedToCore` task started in `resume()`,
torn down in `suspend()`, owning one persistent `WiFiClientSecure` + WebSocket
connection for as long as the app is foregrounded. The task holds the 25×40 grid
(spinlock-guarded, same pattern as `TeletextState`) and the app's `tick()` just reads
the latest snapshot — no enqueue/poll round-trip needed since the task *is* the live
data source.

**Option B — Force it into `dataTask`'s poll pattern**: doesn't fit. `dataTask`
allocates a fresh `WiFiClientSecure`+`HTTPClient` per request and frees it — cheap
because nothing persists. A WebSocket has to stay open for page acquisition (5-20 s
carousel wait, per EXP-005 Finding 4) and to keep receiving live updates afterward.
Bolting persistent-connection lifecycle onto a task designed around request/response
would fight the existing abstraction at every step.

**Option C — Poll a proxy that maintains the WebSocket server-side**: would require
standing up and operating a small always-on relay (e.g. a home server holding the
Ceefax WS connection and re-exposing it as a NOS-shaped HTTP endpoint) — turns a
firmware design question into an infrastructure-ownership one. Noted as a way to make
the ESP32 side trivially reuse the existing `dataTask` + NOS parser wholesale, but out
of scope unless someone wants to run and maintain that proxy.

**Lean: Option A.** Matches an existing, DUT-proven pattern in this codebase rather
than inventing a new one. Needs a new library dependency — `links2004/WebSockets` is
the standard Arduino choice with WSS support via `WiFiClientSecure` (not currently in
`platformio.ini`).

---

### DS-2: Resource contention with existing fetchers — RESOLVED 2026-07-29 (DUT-confirmed)

**The real risk, not a formality — and now confirmed on hardware, not just
theorized.** A persistent second TLS socket held open concurrently with
`dataTask`'s periodic short-lived TLS fetches (weather/crypto/stock/NOS
teletext) is the same failure class already fought through in the WebRadio
TLS/heap incidents (TASK-285 boot-time WDT crash, TASK-287 `tlsYield`
concurrent-caller race, TASK-289 fetch/playback heap race — see project memory
`project_tlsyield_starvation`).

**DUT spike result (EXP-006):** a minimal always-on WebSocket task
(`app/src/ceefaxWsSpike.h`, `rnd/ceefax` branch) attempting a real connection
to the live Ceefax relay was run concurrently with `dataTask`'s normal
multi-app fetch cycling. Compared against a no-spike baseline on identical
firmware: Spotify's TLS layer, which at baseline only shows the already-known
TASK-243 403 (external, unrelated) and an occasional benign stale-fd
condition, starts failing with genuine `SSL - Memory allocation failed` and
(once) `X509_CERT_VERIFY_FAILED` when the spike runs — a failure mode absent
at baseline. Heap itself didn't show a monotonic leak (oscillated and
recovered across the soak, consistent with ordinary fetch churn) and no
device reboot occurred — the contention is in TLS-specific resource limits
(buffer pool / concurrent-session ceiling), not general heap exhaustion.
**Notably, this reproduced even though the spike's own connection never
reached a stable connected state** — the repeated connection *attempts*
(TLS handshake setup/teardown on a 3s retry cycle) were enough on their own.

**Numeric confirmation (same day):** a side-by-side run of the unmodified
`run/stress` tool (no Ceefax code at all) over the identical 8-minute,
5-fetcher plan gives an exact comparison, not just error-string matching:
**6 hard failures / 1 TLS-error line at baseline vs. 25 hard failures / 11
TLS-error lines with the spike running** — roughly 4× and 11× respectively.
Per-fetcher success collapses across nearly every category (crypto and
teletext: 100%→0%; weather: ~71%→~17%).

See EXP-006 for the full methodology, real build obstacles hit (PlatformIO
LDF quirks, DRAM budget, the ADR-042 ELF-verification gate), and data.

**Lean: confirmed — a persistent Ceefax connection is a real, DUT-verified
resource-contention risk, not a hypothetical one.** Any production
implementation needs this designed around from the start (matching WebRadio's
own hard-won lesson), not treated as a hardening pass after the fact.

**Root-cause follow-up (same day): it's a capacity ceiling, not a scheduling
race — and it cuts both ways.** Chased the "spike's own connection never
stabilizes" loose end (user asked directly whether DS-2 is solvable). With
Spotify entirely disabled, the spike *still* failed to connect 100% of the
time — ruling out cross-app contention as the cause of its own failures. A
raw-TLS diagnostic (bypassing `WebSocketsClient`'s own error-swallowing log)
found the real error: `lastError() == -32512 "SSL - Memory allocation
failed"` — the *same* error Spotify hits, occurring even completely alone,
coinciding with free DMA-capable heap around ~35KB at the attempt (vs.
~62-105KB when other connections succeed earlier in boot). A second attempt
under this condition **crashed the device** (Guru Meditation Error,
LoadProhibited) — a more serious finding than "TLS degrades."

**Mitigation implemented and DUT-verified**: gate whether
`WebSocketsClient::loop()` gets pumped at all on a free-DMA threshold — an
established connection is served normally regardless, but reconnect attempts
simply don't fire while memory is tight (matches the "check the budget before
allocating" discipline already used for the WebRadio decoder arena elsewhere
in this codebase). Verified on DUT: no further crash, no further failed-
attempt spam. **This is not a complete fix**: a failed attempt appears to
permanently cost a few KB of DMA headroom that doesn't recover in-session
(observed 39968→37000 bytes after one failure), and since the gate's
threshold sits close to steady-state idle free-DMA, the very first attempt
can tip it closed for the rest of a session — the connection may simply never
establish, even though nothing crashes anymore. **Answer to "is DS-2
solvable": yes for the crash/degradation (verified), not yet for reliable
connection establishment** — the durable fix likely also needs to reduce the
memory footprint required per attempt, not just decide more carefully when to
try. See EXP-006's root-cause follow-up section for full detail.

**This project already has a formal DMA budget, and already solved this exact
class of problem once** — checked *after* the empirical probing above, not
before (should have been the first move). `app/mem_manifest.yaml` documents
`ceiling.DMA = 48000` bytes, validated by `run/check`'s `gen_mem_layout` gate;
the empirically-found failure/success boundary (fails ~35-40K, succeeds
~50-62K+) brackets that number consistently. Zero buffers are currently
registered `caps: DMA` in the manifest — this pool is entirely outside the
formal budget system today, consistent with `M-MEMBUDGET-memory-budget.md`'s
own note that WiFi/LWIP/mbedTLS overhead is untracked/unfreeable.
`EXP-010-membudget-spike.md` already fought this exact DMA scarcity for
WebRadio's I2S path (measured `lfbDma` at idle in essentially the same
~35-37K range) and fixed it with `PATCH-MEMBUDGET-4` — halving the I2S DMA
ring (`dma_buf_len` 512→256) freed ~24K with no audible quality loss.

**mbedTLS's direct analog turned out to be blocked, not just unattempted —
investigated, not assumed.** `CONFIG_MBEDTLS_SSL_IN_CONTENT_LEN`/
`OUT_CONTENT_LEN` (default 16KB each) looked like the obvious next step, but
unlike I2S's `dma_buf_len` (a plain runtime struct field), these are
**compile-time values baked into this project's precompiled
`framework = arduino` binary** — confirmed via the shipped sdkconfig
(`CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN=16384`), not overridable via project
`build_flags`. Checked for a runtime alternative too (RFC 6066 Max Fragment
Length negotiation) — also unavailable, that support isn't compiled into this
framework build at all, and `WiFiClientSecure`'s Arduino wrapper exposes no
buffer-size configuration either. Closing this gap needs rebuilding the
framework from source — a materially bigger commitment than this spike's
scope, not a quick follow-up.

Both follow-ups from the prior draft are now resolved (numeric baseline: done,
see above; footprint reduction: investigated and found infeasible without a
framework rebuild, not silently dropped).

**DECISION LOCKED 2026-07-29: accept best-effort connectivity. The framework
rebuild is explicitly NOT being pursued.** The crash-prevention mitigation
(DMA-gated reconnect, DUT-verified) is the shipped answer to DS-2 — a Ceefax
connection may not always establish in a given session, but it will not crash
the device or degrade other apps' TLS reliability once the mitigation is in
place. Both framework-rebuild paths considered (switch to `framework =
espidf` for the whole project; fork-and-custom-build the precompiled
`framework-arduinoespressif32` package) were judged disproportionate to a
feature that isn't shipped or scheduled — real, bounded work, but not worth
doing speculatively. If full connection reliability is ever required later,
the path is recorded (`CONFIG_MBEDTLS_SSL_VARIABLE_BUFFER_LENGTH` via a
rebuilt framework — see EXP-006), but it is a deliberately deferred decision,
not an oversight, and should not be re-litigated without a concrete reason
best-effort connectivity stops being acceptable.

---

### DS-3: Navigation model (no `pn=`/`ftl=` metadata)

NOS conveniently pre-parses `pn=p_/n_/ns/ps` (prev/next/subpage) and `ftl=` (fastext
targets) into response metadata. Ceefax's wire protocol has neither.

**Row-tap inline links (M-TELETEXT DS-2) — implemented, ports unmodified.** Page-index
rows embed plain visible `NNN` 3-digit refs exactly like NOS (confirmed in the
prototype screenshot: 101, 152, 340, 480, 660, 528, etc. all tappable). `preview_
teletext.py`'s `scan_links()`/`find_row_link()` needed zero code changes when pointed
at a Ceefax-sourced grid — proven, not just argued.

**Prev/next page — implemented as page number ± 1.** No `pn=` metadata, but the
page-numbering convention (100-899, magazine = first digit) is dense enough that ±1
is a reasonable stand-in for the real teletext remote's prev/next behaviour. Loses
the "skip missing pages" smartness NOS's real metadata provides.
`ceefax_extract_nav()` in `preview_teletext.py` implements this.

**Fastext colour bar — implemented, real targets included.** Row 24 carries the same
colour-coded label segments as NOS (confirmed:
`'\x01Headlines \x02Sport \x03RegionalTV \x06A-Z Index'`, same 0x01-0x07 FG-colour
scheme), so `ceefax_extract_nav()` parses real labels and colours with the same
segment logic NOS's `extract_nav()` already uses. Real *targets* aren't in that row
(unlike NOS's index rows, row 24 carries no digit refs — an earlier draft of this doc
floated "drive it from row-tap targets on the bottom row" as a fallback; that doesn't
work, there's nothing there to scan) — they're broadcast separately as packet 27
(FLOF links), which `ceefax_client.decode_flof_packet()` now decodes: six
Hamming-**8/4** nibbles per link (simpler than the Hamming-24/18 triplet coding an
earlier draft of this doc assumed X/26/X/28 enhancement packets use — X/27/0 doesn't
use that scheme). **Verified against live traffic**: page 100 → `{0: 101, 1: 300,
2: 600, 3: 199}`, all four buttons resolve to plausible section-index pages and
navigate correctly end-to-end in the prototype. Not every page carries FLOF links —
`ceefax_extract_nav()` leaves a button's target `None` (inert, existing nav code
already handles this) when packet 27 hasn't supplied one, which is the *correct*
behaviour (real teletext decoders do the same), not a fallback state.

---

### DS-4: TLS root CA — corrected 2026-07-29 (initial finding was wrong)

**Original finding (wrong):** `internal.nathanmediaservices.co.uk` chains leaf →
`Let's Encrypt YE2` → `ISRG Root YE` → **ISRG Root X2**, and the last hop's subject
being "ISRG Root X2" was read as "self-signed root, needs a brand-new pinned cert."
That was a mistake — the actual served chain has one more cert: the "ISRG Root X2"
certificate presented here is itself signed **by ISRG Root X1**, i.e. this is the
commonly-served *cross-signed* X2, not the self-signed X2 root.

**Corrected, verified empirically:** `openssl verify -CAfile <the existing
OPEN_METEO_ROOT_CA PEM> -untrusted <server's YE2+RootYE+cross-signed-X2>
<leaf>` → `OK`. The chain verifies against the **X1 root already pinned** in
`dataTaskCerts.h` — no new certificate is needed. This is the exact same shape
already documented for `NOMINATIM_ROOT_CA` in that file (`leaf <- YR1 <- ISRG Root
YR <-(cross-signed by)- ISRG Root X1`) — Ceefax's relay just has a different
Let's Encrypt intermediate generation (YE vs. YR) hitting the identical pattern.

**Lean:** alias, don't add a new cert — `#define CEEFAX_ROOT_CA OPEN_METEO_ROOT_CA`,
same as `RADIO_BROWSER_ROOT_CA`/`NOMINATIM_ROOT_CA`. Carries the same caveat those
two already carry: this depends on `nathanmediaservices.co.uk` continuing to serve
the cross-signed intermediate. If it's ever dropped (typical once X2's self-signed
form has broad store coverage), verification against X1 alone breaks — remediation
is a two-root bundle (`COINGECKO_ROOT_CA` pattern), not a replacement cert. `./run/
check-datatask-certs`-style monitoring would catch that regression the same way it
already does for the other aliased fetchers.

---

### DS-5: Page addressing

**Confirmed compatible with the existing 3-digit convention** — no UI change needed.
`page NNN (100-899) → magazine = NNN // 100, page_byte = int(f"{NNN % 100:02d}", 16)`
(BCD-style nibble packing: tens digit → high nibble, units → low nibble). Verified
against live `pageExists` carousel traffic (page 131 → magazine 1, byte 0x31).
`TeletextApp`'s numpad/settings-preset entry model transfers directly; only the
page→magazine/byte conversion is new (a few lines, see `ceefax_client.py:
page_to_magazine_byte()`).

---

### DS-6: One app or two? (`TeletextApp` variant vs. new `CeefaxApp`) — RESOLVED 2026-07-29

**Option A — `CeefaxApp` as a sibling class**, sharing only the render-layer helpers
(colour palette, mosaic tables, control-code switch — currently inline in
`teletextApp.h::_drawGrid()`) via a small extracted shared header. Cleanest separation
given how different the fetch/state lifecycle is (persistent pump task vs. dataTask
poll), but duplicates the strip/numpad/fastext UI shell unless that's also extracted.

**Option B — one `TeletextApp` with a `teletextCountry`-style source switch**, where
NOS and Ceefax are two `TeletextSource` backends behind a common interface
(`ready()`, `grid()`, `navigate(page)`), matching the reserved-but-unimplemented
`teletextCountry` settings field's original intent (M-TELETEXT DS-6).

**Lean: Option B.** Three independent reasons, any one of which would be enough on its
own:

1. **Taskbar slots are already the scarce resource, not code complexity.**
   M-TELETEXT's own context section notes the shell was at 9 apps with the taskbar
   already scrolling to fit them before Teletext became the 10th. A separate
   `CeefaxApp` is an 11th slot for a page-for-page identical *experience* (same grid,
   same strip, same numpad) with a different backend — that's the taskbar-scarcity
   problem M-TELETEXT already flagged, made worse for no user-facing benefit. Folding
   Ceefax into `TeletextApp` via `teletextCountry` costs zero additional slots.

2. **The host prototype proved the shared surface is real, not aspirational.**
   `preview_teletext.py --source ceefax` runs `build_cell_grid`, the mosaic/colour
   tables, `Keypad`, the strip renderer, and `scan_links`/`find_row_link` completely
   unmodified against Ceefax data (verified with screenshots, not just argued). Option
   A doesn't avoid building the shared-backend abstraction this implies — it still
   needs the render/UI code factored out to share it across two classes instead of
   one. It adds a second class wrapper around the same abstraction for no functional
   gain, only extra indirection.

3. **The settings field already committed to this shape.** `teletextCountry` was
   reserved in M-TELETEXT DS-6 specifically so a second teletext source would be a
   *source*, not a new app. Ceefax is the first real test of that intent; Option B is
   the field's original design working as planned, Option A quietly abandons it.

**The lifecycle-mismatch concern is real but not a blocker.** NOS's backend is a
stateless poll (`resume()`/`suspend()` no-ops beyond triggering/not-triggering the next
`dataTask` fetch); Ceefax's backend needs to start/stop its own pump task
(`wrEnsurePumpTask()`/`wrTeardownPumpTask()`-shaped, see DS-1) on `resume()`/
`suspend()`. That's an ordinary strategy-pattern seam — `TeletextSource::onResume()`/
`onSuspend()` meaning "no-op" for one implementation and "start/stop a FreeRTOS task"
for the other isn't awkward, it's exactly what the interface is for.

**What genuinely is new risk, not validated by the host prototype:** the prototype
picks its source once at process start (`--source` CLI flag) and never switches at
runtime. Firmware's `teletextCountry` is a live Settings toggle — if the user changes
it while `TeletextApp` is backgrounded, the *next* `resume()` must start the newly
selected backend and guarantee the previous one's pump task/WebSocket is fully torn
down first, not just superseded. This follows the existing pull-on-resume pattern
(ADR-043 — settings are read fresh in `resume()`) but needs the pump-task start/stop
wired into that path explicitly; nothing in this spike exercised it, because the host
tool never needed to.

---

### DS-7: Taskbar status flags (`isConnecting()` / `hasError()`) — not addressed until now

**Gap, caught by review, not by this spike.** Every `App` implements
`isConnecting()` (amber active-slot bar) and `hasError()` (red, sticky, highest
precedence — ADR-046) against a tri-state contract: error > busy > idle.
`TeletextApp`'s existing NOS mapping is `isConnecting() { return !_st.ready; }` (a
one-time "before first page ever loaded" gate) and `hasError() { return _ttErr; }`
(set on a failed fetch, cleared on the next success). Nothing in this doc or the host
prototype considered what these should mean for a Ceefax backend, and the two
questions are not the same shape as NOS's.

**`isConnecting()` — lean: diverge from NOS's one-time gate, make it per-navigation.**
NOS's fetch is near-instant after the first load, so nobody would notice if the amber
bar only ever fired once at boot. Ceefax's page-acquisition wait (3-20s+, EXP-005
finding 4) is long and visible on *every* navigation, not just the first — and the
taskbar amber indicator is exactly the mechanism that stays useful while the app
isn't foregrounded (the in-canvas "Waiting for page N..." message the prototype added
only helps if you're looking at the screen). Lean: `isConnecting()` returns
`!backend.acquired()` continuously — true from every `goto()`/`navigate()` call until
the next successful acquisition, not just before the first one ever. This is a
deliberate divergence from the NOS mapping, not an oversight; document it as such so
a future reader doesn't "fix" it back to matching NOS.

**`hasError()` — lean: needs a sustained-failure latch, not a raw reconnect pass-through
(open sub-question on the exact threshold).** `ceefax_client.py`'s reconnect loop
treats a dropped WebSocket as routine — 3s backoff, retry indefinitely — which is
correct behaviour for the connection itself but is exactly the kind of locally-computed,
non-sticky signal that caused taskbar flap before: ADR-046 Amendment 2 already had to
add sticky-latch treatment once for the Spotify auth-error case, and the still-open
Spotify `isHealthy()` gap (`docs/project/tasks.md`, un-numbered P3 item, 2026-07-2x) is
the same class of bug — a real degraded/error signal that exists internally but either
isn't wired to `hasError()` or is wired without latching, so it flaps red-then-green on
ordinary transient recovery instead of reflecting a genuine sustained failure.
Reconnecting every 3s and succeeding a moment later is normal operation, not an error —
`hasError()` must not fire on every blip. What plausibly **should** latch red:
a certificate/handshake failure (won't self-heal by retrying, matches ADR-046's own
definition verbatim), or N consecutive failed reconnect attempts / a connection-down
duration past some multiple of the backoff interval (genuinely sustained, not
transient).

**Update 2026-07-29 (EXP-006, complete):** a long-running host-side observer
(`app/tools/ceefax_reconnect_observer.py`, `--hours 6`) characterized real drop
frequency/duration against the live relay. **Result: 1 outage in the full 6h
session — the initial 7.5s acquisition — zero disconnects for the remaining
~5h59m52s.** Lean: **N≥2 consecutive failed reconnect attempts** (≈6s of
continuous failure) as the `hasError()` threshold — no false-positive risk
against this session's behaviour, while still catching a genuine outage within
two retry cycles.

**Real limitation, not glossed over:** one long session with zero observed
outages tells us drops are rare; it says nothing about how the relay actually
*recovers* from a real one (clean reacquisition? state reset needed?
duration?), since none occurred to observe. The threshold is reasonable given
available data, not proven against real outage-recovery behaviour. More
confidence (different time of day / day of week) would need another
observation run, not a re-read of this one.

---

## Lean / decision

DS-6, DS-2, and DS-7 are all resolved, and DS-2's implementation-level decision
is locked. DS-6: one `TeletextApp`, pluggable `TeletextSource` backend
(Option B). DS-2 (EXP-006, DUT-confirmed, numerically measured — ~4-11× worse
than baseline): a persistent Ceefax connection is real, measurable
TLS-resource contention, root-caused to a DMA capacity ceiling. A
crash-prevention mitigation is DUT-verified; full connection reliability would
need a framework rebuild (two paths scoped, both investigated), and **the
decision is locked to accept best-effort connectivity instead of pursuing
that rebuild** — deliberate, not deferred by default. DS-7 (EXP-006, full 6h
observation): drops are rare (1 outage — initial acquisition — in 6 hours),
`hasError()` threshold set at N≥2 consecutive failures.

**Scheduled 2026-07-30 — ADR-057 accepted, implementation tracked as TASK-370
through TASK-374** (`docs/project/tasks.md`, `## Open — M-CEEFAX`). This
design doc's job is done; ADR-057 is now the authoritative decision record,
and further changes to the architecture/leans described here should go
through an ADR amendment, not an edit to this file.

---

## Open questions

1. ~~DS-2 resource contention~~ — **resolved** (EXP-006, DUT-confirmed real
   contention, root-caused to a DMA capacity ceiling, numerically measured).
   Both follow-ups closed: numeric `run/stress` baseline done; mbedTLS
   footprint reduction investigated and found to need a framework rebuild.
   **Decision locked**: accept best-effort connectivity, do not pursue the
   rebuild.
2. ~~DS-7 `hasError()` sustained-failure threshold~~ — **resolved** (EXP-006:
   full 6h observation, 1 outage — initial acquisition — zero drops thereafter;
   threshold N≥2 consecutive failed reconnects). Caveat: says drops are rare,
   not how the relay recovers from a real one, since none occurred to observe.

**Waived 2026-07-29** (not pursued, not resolved): whether `nmsceefax.co.uk`'s relay
is a service the project wants a firmware dependency on long-term (single enthusiast
operator, no SLA). Accepted as an out-of-scope operational risk rather than an
engineering question — recorded here so a future reader knows it was considered and
consciously set aside, not missed.

---

## Exit criteria (if scheduled)

- DS-6 lean (Option B, above) confirmed in an ADR alongside DS-2's outcome.
- ~~DS-2's confirmed contention (EXP-006) has a mitigation~~ — **done**: the
  DMA-gated reconnect mitigation is DUT-verified (stops the crash and
  failed-attempt churn). Full connection reliability would need a framework
  rebuild — investigated, scoped, and **explicitly declined**: the decision is
  locked to accept best-effort connectivity as a documented limitation, not an
  open gap. An ADR for this milestone should record that decision, not
  re-open the investigation.
- `preview_teletext.py --source ceefax` (this spike's prototype, now merged into the
  existing tool — see "What's proven") gets a settings-driven start page, closing the
  remaining gap with the NOS source's coverage, before firmware work starts. (Fastext
  packet-27 decode is already done — see DS-3.)
- `CEEFAX_ROOT_CA` alias added to `dataTaskCerts.h` (`= OPEN_METEO_ROOT_CA`, per DS-4 —
  no new cert needed, confirmed by verification, not just chain-reading).
- `isConnecting()`/`hasError()` implemented per DS-7's lean, with a concrete
  sustained-failure threshold for `hasError()` decided (not left as "some N").
- `run/check` (5-gate) passes clean once firmware lands.
