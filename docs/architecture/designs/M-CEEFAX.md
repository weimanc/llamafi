# Design — M-CEEFAX: NMS Ceefax Live Teletext (proposal)

> Owner: Architect
> Status: proposal — pre-ADR, host-prototype only, no DUT/firmware work done
> Date: 2026-07-29
> Feeds: none yet (would need a new ADR if scheduled)
> Feeds from: EXP-005

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

### DS-2: Resource contention with existing fetchers

**The real risk, not a formality.** A persistent second TLS socket held open
concurrently with `dataTask`'s periodic short-lived TLS fetches (weather/crypto/stock/
NOS teletext, whichever else is active) is the same failure class already fought
through in the WebRadio TLS/heap incidents (TASK-285 boot-time WDT crash, TASK-287
`tlsYield` concurrent-caller race, TASK-289 fetch/playback heap race — see project
memory `project_tlsyield_starvation`). WebRadio earned its continuous-connection
architecture the hard way, across several DUT-crash cycles. Ceefax would be a *second*
continuously-open TLS socket class on top of that, not a replacement for it — the two
could in principle be foregrounded at overlapping times (Ceefax app active while
WebRadio plays in the background, if that's ever a supported combination) and would
then be competing for the same finite TLS buffer / heap headroom that `dataTask`
already budgets tightly for.

**Lean (not a resolved question — flagged for whoever picks this up):** validate
concurrent persistent-WS + `dataTask` heap/TLS behavior on actual DUT hardware *before*
committing to the architecture, not as a hardening pass afterward. This is exactly the
order-of-operations mistake that cost multiple TASK-2xx cycles on WebRadio.

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

### DS-4: TLS root CA

**Confirmed** (`openssl s_client`, 2026-07-29): `internal.nathanmediaservices.co.uk`
chains through Let's Encrypt's ECDSA hierarchy — leaf → `Let's Encrypt YE2`
(intermediate) → `ISRG Root YE` (cross-signed intermediate) → **ISRG Root X2**
(self-signed root).

This is **not** the ISRG Root X1 already bundled in `dataTaskCerts.h` for other
fetchers — X1 is RSA, X2 is ECDSA, and embedding one does not cover the other. A new
`TELETEXT_CEEFAX_ROOT_CA` (ISRG Root X2 PEM) would need adding before first DUT
connect attempt, following the existing `dataTaskCerts.h` convention (see its
multi-root-bundle precedent for CoinGecko/radio-browser).

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
transient). **The exact threshold isn't picked here** — this needs either a DUT
observation of real-world reconnect failure patterns, or an explicit Architect call,
before implementation; flagging the shape of the answer, not the number.

---

## Lean / decision

DS-6 resolved above (Option B — one `TeletextApp`, pluggable `TeletextSource`
backend). No ADR yet: this repo's convention (see M-TELETEXT/ADR-044) is to write the
ADR once the design is truly ready to schedule, and DS-2 (resource-contention DUT soak
test) still gates that — it's not resolvable on host, and getting it wrong is exactly
the class of mistake that cost several TASK-2xx cycles on WebRadio. Recommend: run the
DS-2 soak test, then write the ADR covering both decisions together.

---

## Open questions

1. DS-2 resource contention — needs a DUT soak test (persistent WS + concurrent
   `dataTask` fetch), not resolvable on host. Now the only *engineering* blocker on
   an ADR (DS-6 resolved above).
2. DS-7 `hasError()` sustained-failure threshold — needs either real-world DUT
   reconnect-failure observation or an explicit Architect call; the shape of the
   answer is proposed above, the exact number isn't.

**Waived 2026-07-29** (not pursued, not resolved): whether `nmsceefax.co.uk`'s relay
is a service the project wants a firmware dependency on long-term (single enthusiast
operator, no SLA). Accepted as an out-of-scope operational risk rather than an
engineering question — recorded here so a future reader knows it was considered and
consciously set aside, not missed.

---

## Exit criteria (if scheduled)

- DS-6 lean (Option B, above) confirmed in an ADR alongside DS-2's outcome.
- DUT soak test proves persistent Ceefax WS + concurrent `dataTask` fetch does not
  reproduce the TASK-285/287/289 class of heap/TLS starvation.
- `preview_teletext.py --source ceefax` (this spike's prototype, now merged into the
  existing tool — see "What's proven") gets a settings-driven start page, closing the
  remaining gap with the NOS source's coverage, before firmware work starts. (Fastext
  packet-27 decode is already done — see DS-3.)
- `TELETEXT_CEEFAX_ROOT_CA` added to `dataTaskCerts.h`.
- `isConnecting()`/`hasError()` implemented per DS-7's lean, with a concrete
  sustained-failure threshold for `hasError()` decided (not left as "some N").
- `run/check` (5-gate) passes clean once firmware lands.
