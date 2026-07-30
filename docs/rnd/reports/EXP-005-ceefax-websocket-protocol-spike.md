> Owner: R&D

### EXP-005 — 2026-07-29 — NMS Ceefax Live WebSocket Protocol Spike

**Hypothesis**: `nmsceefax.co.uk` (an enthusiast-run "up-to-date" revival of the BBC's
Ceefax teletext service) exposes the page content via some HTTP endpoint similar to
NOS Teletekst (`teletekst-data.nos.nl/page/{N}`, see M-TELETEXT), making it addable to
the `teletextCountry` enum as a second entry.

**Approach**: Host-side source analysis of the site's JS viewer bundle
(`teletext-viewer/tv.js`, `teletext-resources/teletext.js`), live protocol probing with
a throwaway Python WebSocket client (`websocket-client`, installed into the project venv
for this spike only), and a full prototype: `app/tools/ceefax_client.py` (new — the
WebSocket transport/state layer) plus a `--source ceefax` mode added directly to the
existing `app/tools/preview_teletext.py` (not a separate tool — see M-CEEFAX DS-6,
"one app, pluggable source"), which renders live pages through the **unmodified**
NOS render pipeline (`preview_teletext.build_cell_grid`) and reuses its strip/keypad
UI, with `ceefax_extract_nav()` supplying page±1 nav and real (but currently
non-interactive) fastext-bar labels in place of NOS's `pn=`/`ftl=` metadata.

---

#### Finding 1 — Hypothesis rejected: no REST endpoint, it's a live broadcast relay

`nmsceefax.co.uk` serves a JS teletext *set emulator* (canvas renderer, remote-control
UI, full ETS 300 706 Level 1/2.5/3 decode including Hamming 8/4 and 24/18, DRCS, POP,
MOT/TOP tables — `teletext.js` is ~15 KB of parity/Hamming tables and packet decoders).
It talks to a backend over a **persistent WebSocket**, not a page-addressed HTTP GET.
There is no cacheable "fetch page N" URL to reverse-engineer; the server relays a real
off-air-style teletext broadcast carousel and the client acquires a "slot" on a
specific page and waits for it to cycle round on air.

Endpoint (decoded from the site's default channel ID — base64 of a 3-element JSON
array `["service-name", host, path]`, found in `settings.js`):

```
wss://internal.nathanmediaservices.co.uk/websockets/ceefax
```

`settings.js` ships three more preset channel IDs pointing at *other* operators
running the same client/relay software against their own teletext sources
(`webfax.thetvroom.com`, `zxnet.co.uk` — "Webfax 1/2", "Teefax"). Not explored further;
noted in case a future spike wants a second Ceefax-protocol source.

#### Finding 2 — Outbound wire format is NOT what it looks like in the source

`tv.js` calls `websocket.send(["service", channelID])` etc. — this reads like it should
be JSON, but `WebSocket.send()` only accepts string/Blob/ArrayBuffer types; passing a
plain JS array coerces via `Array.prototype.toString()`, which **comma-joins the
elements with no brackets or quotes**. Sending real JSON here gets the connection
closed immediately (verified: JSON-encoded `["service", ...]` → close code 1000 within
milliseconds). The actual outbound frames are:

```
service,<base64 channel id>
ttx,true
pagesearch,<slot>,<magazine>,<page>,<subcode>,<pagesearch>,<pagehold>,<enhancement>
keepalive                          (every 5s — connection stays open without it in
                                     testing, but the reference client always sends it)
```

Inbound frames, by contrast, genuinely are JSON arrays (`["cmd", ...args]`) — verified
against `header`, `row`, `initialpage`, `pageExists`, `clock`, `secondTick`,
`channelSettings`, `apiver`.

#### Finding 3 — Row/header text bytes are byte-identical to NOS's decoded scheme

`atob(base64) & 0x7F` per byte reproduces exactly the control-code scheme
`teletextApp.h`/`preview_teletext.py` already implement for NOS (0x01–0x07 FG colour,
0x10–0x17 mosaic, 0x1C/0x1D BG, 0x20–0x7E printable ASCII). Real off-air UK teletext is
7-bit odd-parity — masking the parity bit is the only "decode" step needed for basic
Level 1 display content; no Hamming decode is needed for row text (only for packet
*addressing* and Level 2.5 enhancement packets, which this spike did not need).

**Verified empirically**, not just by source-reading: `preview_teletext.build_cell_grid()`,
called unmodified on a Ceefax-sourced content string, renders a pixel-correct page
(BBC/Ceefax mosaic logo, magazine index, fastext colour bar) — see prototype output.

#### Finding 4 — It's a live carousel, not a poll/fetch

Requesting a page (`pagesearch`) does not return that page's content directly (except
a short cosmetic title snapshot via `initialpage`, ~20 bytes, not the full grid). The
server begins forwarding `header`/`row` frames for the requested page only once the
real broadcast carousel cycles round to it — observed 5–20 s in a 35 s capture window
of magazine 1 traffic (~50 other pages cycling past first). After acquisition, the
server continues pushing `header`/`row` updates every re-airing (roughly every 6–8 s
observed for page 100), and — notably — **content can change between re-airings**: a
rotating headline strip on page 100 alternated "Cricket" / "Formula 1" copy across
successive captures of the same page, live. This is a genuinely different UX from
NOS's single-shot poll: no single instant is "page ready", the grid is a continuously
live surface.

The server appears to filter `row` frames server-side to the caller's acquired
slot/page — no `row` frames for other magazine-1 pages were observed, only `header` +
`pageExists` carousel announcements for those. Re-requesting a different page (new
`pagesearch` on slot 0) starts the acquisition wait over.

#### Finding 5 — Page addressing maps cleanly onto the existing 3-digit convention

`page` NNN (100–899) → `magazine = NNN // 100`, `page_byte = int(f"{NNN % 100:02d}", 16)`
(tens digit → high nibble, units digit → low nibble; e.g. page 131 → magazine 1, byte
0x31 = 49 decimal — confirmed against live `pageExists` events naming page 131 as
`[..., 1, 49]`). This is the same BCD-style packing real teletext hardware uses, and it
composes cleanly with the existing 3-digit page-number UI (`TeletextApp`'s numpad,
settings presets) — no UI redesign needed for entry.

#### Finding 6 — No `pn=`/`ftl=` equivalent; row-tap links + real fastext both work

NOS's response conveniently includes pre-parsed `pn=p_/n_/ns/ps` (prev/next/subpage)
and `ftl=` (fastext target pages) metadata lines. Ceefax's wire protocol has neither.

**Inline row-tap link scanning works unmodified**: page-index rows embed plain `NNN`
page references as visible text (confirmed in the prototype screenshot — 101, 152,
144, 302, 340, 360, 480, 660, 459, 143, 555, 695, 528 all visible as tappable 3-digit
refs), so `TeletextApp`'s existing DS-2 row-tap mechanism (M-TELETEXT) ports directly
— `scan_links()`/`find_row_link()` in `preview_teletext.py` needed zero changes.

**Fastext button bar — real targets now decoded (packet 27 / FLOF).** Row 24 carries
the same colour-coded label segments as NOS (confirmed —
`'\x01Headlines \x02Sport \x03RegionalTV \x06A-Z Index'`, same 0x01-0x07 FG-colour
scheme), giving labels/colours for free via the same segment logic `extract_nav()`
uses for NOS. The actual link *targets* are broadcast separately as packet 27
(`rownum == 27` in the same `"row"` wire message shape as ordinary content rows —
not a distinct message type). An initial read of `teletext.js` assumed this needed
Hamming-24/18 triplet decode (the scheme X/26 and X/28 enhancement packets use); it
doesn't — X/27/0 (FLOF) is simpler, six Hamming-**8/4** nibbles per link (one byte
each, not a 3-byte triplet). Ported `hamming_8_4_decode()` (table extracted
programmatically from `teletext.js`, not hand-transcribed — 256 entries is too easy
to mistranscribe) plus the link-field layout from `tv.js`'s `linkbuttonhandler()` into
`ceefax_client.decode_flof_packet()`. **Verified against live traffic**: page 100
decoded real link targets `{0: 101, 1: 300, 2: 600, 3: 199}` (Headlines→101,
Sport→300, RegionalTV→600, A-Z Index→199) — all plausible BBC Ceefax section-index
pages, and the fastext bar now renders with working targets end-to-end, no longer an
inert placeholder.

One correctness note: the reference JS has a real operator-precedence bug in its
"is this link unset" check (`linksubcodeandmags & 0x3F7F == 0x3F7F` parses in JS as
`linksubcodeandmags & (0x3F7F==0x3F7F)` = `linksubcodeandmags & 1`, not the evidently
intended `(linksubcodeandmags & 0x3F7F) == 0x3F7F`). `decode_flof_packet()` implements
the intended check, not the buggy one — flagged in case anyone cross-references
against the live site's own behaviour and finds a discrepancy on genuinely-unset links.

#### Finding 7 — No new TLS root needed (corrected 2026-07-29 — original finding was wrong)

`internal.nathanmediaservices.co.uk` chains leaf → `Let's Encrypt YE2` → `ISRG Root
YE` → a cert whose subject is "ISRG Root X2". The original write-up of this finding
read that last hop as "self-signed X2 root, needs a brand-new pinned cert" — wrong:
the cert actually served here is signed **by ISRG Root X1** (the commonly-served
cross-signed form of X2, not the self-signed X2 root). Verified with `openssl
verify -CAfile <the OPEN_METEO_ROOT_CA PEM already in dataTaskCerts.h> -untrusted
<server's intermediates> <leaf>` → `OK`. No new cert is needed — same pattern
`dataTaskCerts.h` already documents for `NOMINATIM_ROOT_CA` (a different Let's
Encrypt intermediate generation, identical cross-sign-to-X1 shape). Same caveat
those aliases carry: depends on the server continuing to serve the cross-signed
intermediate; if dropped, needs a two-root bundle, not a new single cert.

#### Finding 8 — Transport architecture doesn't fit `dataTask`'s poll pattern

`dataTask` (used by NOS Teletekst and every other fetcher app) is built around
stack-allocating a `WiFiClientSecure`+`HTTPClient` per request and freeing it
immediately after — a single-shot GET pattern, cheap because the connection doesn't
persist. Ceefax needs a **persistent** WebSocket connection for as long as the app is
foregrounded, which is architecturally closer to `WebRadioApp`'s dedicated pump task
(`wrEnsurePumpTask()`/`wrTeardownPumpTask()` in `webRadioApp.h`, `xTaskCreatePinnedToCore`
on `resume()`, torn down on `suspend()`) than to any of the `dataTask::FETCH_*` fetchers.
No existing WebSocket client library is vendored in `platformio.ini`; one
(`links2004/WebSockets` is the common Arduino choice, supports WSS via
`WiFiClientSecure`) would be a new dependency.

---

#### Conclusions

1. **Hypothesis rejected** — Ceefax is not a config-only addition to the
   `teletextCountry` enum the way SVT (EXP-004 finding) might be; the wire protocol,
   transport model, and page-acquisition semantics are all different from NOS.

2. **Rendering is fully reusable, unmodified** — the highest-value finding. Every
   piece of `teletextApp.h`'s cell-drawing logic (colour palette, control-code state
   machine, mosaic bit layout) and its host-side twin in `preview_teletext.py` applies
   to Ceefax content byte-for-byte. Confirmed by running Ceefax-sourced grids through
   `build_cell_grid()` unmodified and rendering a correct page (see prototype).

3. **Transport is not reusable** — needs a new WebSocket dependency, a new persistent
   background task (WebRadio's pump-task pattern is the closer architectural fit than
   dataTask), a new TLS root, and a live/carousel-aware state model instead of a
   poll-and-cache one.

4. **Navigation UX mostly transfers, and fastext is fully real now** — 3-digit page
   numbering and row-tap inline links (DS-2) port directly. Prev/next-page uses a
   page±1 fallback (Ceefax supplies no `pn=`). Fastext-by-colour needed new logic
   (no `ftl=` metadata) but is no longer a placeholder: packet 27 (FLOF) is decoded
   end-to-end and produces working targets, verified against live traffic (Finding 6).

5. **Resource risk is real, not hypothetical** — a second always-on TLS socket
   alongside `dataTask`'s periodic fetches is the same class of heap/TLS-buffer
   contention already fought through in the WebRadio tlsYield-starvation incidents
   (TASK-285/287/289). Any implementation needs the same care from day one, not as a
   follow-up hardening pass.

---

#### Recommended follow-on (if adopted)

- Packet 27 (FLOF) decode is done on host (`ceefax_client.decode_flof_packet()`).
  Porting it to firmware is arithmetic-only (no floats, no dynamic allocation beyond
  a fixed 6-entry table) — should be a direct C++ translation, not a re-design.
- Confirm live heap/TLS behavior of a persistent `WiFiClientSecure` WebSocket
  concurrent with `dataTask` fetches on actual ESP32 hardware before committing to the
  architecture — this is exactly the failure class TASK-285/287/289 already found once.
- Evaluate `links2004/WebSockets` library footprint (flash + heap) against the existing
  `-DDRAM .dram0.bss` headroom constraints noted for other static-buffer apps.

---

*Feeds: M-CEEFAX*
