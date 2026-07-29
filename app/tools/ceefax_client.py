"""ceefax_client.py — minimal client for NMS Ceefax's live teletext relay.

R&D spike (EXP-005, 2026-07-29) reverse-engineered this from
https://nmsceefax.co.uk 's teletext-viewer/tv.js. It is NOT a REST API like
NOS Teletekst (see preview_teletext.py) — it is a persistent WebSocket relay
of a real off-air UK teletext broadcast carousel.

Endpoint (decoded from the site's default channel ID, base64 of a 3-element
JSON array ["nms-ceefax", host, path]):

    wss://internal.nathanmediaservices.co.uk/websockets/ceefax

Wire protocol
--------------
Outbound frames are **comma-joined values**, i.e. what JavaScript's
`WebSocket.send(anArray)` actually transmits (`Array.prototype.toString`,
NOT `JSON.stringify` — sending a JSON-encoded array here gets the socket
closed immediately with code 1000). Frames used by this client:

    "service,<base64 channel id>"
    "ttx,true"
    "pagesearch,<slot>,<magazine>,<page>,<subcode>,<pagesearch>,<pagehold>,<enhancement>"
    "keepalive"                      (send every ~5s; server appears to expect
                                       this — the reference client does)

Inbound frames ARE JSON arrays: `["cmd", ...args]`. Relevant commands:

    ["apiver", N]
    ["header", slot, base64(40B), pagematched, controlcodes, magazine, subcode, page]
    ["row", slot, magazine, rownum(1-24), base64(40B)]
    ["initialpage", slot, magazine, page, subcode, base64(~20B)]   -- cached
        title snapshot, sent once right after a matching pagesearch; cosmetic,
        not needed once "header"/"row" start arriving.
    ["pageExists", slot, magazine, page]   -- carousel announcements for OTHER
        pages currently on air in the same magazine; ignore.
    ["clock", ...], ["secondTick"], ["channelSettings", {...}]  -- cosmetic.

Row/header text bytes are 7-bit odd-parity teletext characters. Masking each
byte with `& 0x7F` reproduces exactly the same byte stream NOS Teletekst's
`<pre>` block delivers pre-decoded server-side — same control-code scheme
(0x01-0x07 FG colour, 0x10-0x17 mosaic, 0x1C/0x1D BG, 0x20-0x7E printable).
That means `preview_teletext.build_cell_grid()` (and the identical C++ logic
in `app/src/teletextApp.h::_drawGrid()`) render Ceefax content UNMODIFIED —
confirmed by this module reusing that exact function.

Page addressing: page NNN (100-899) -> magazine = NNN // 100 (0 means 8),
page-in-magazine byte = int(f"{NNN % 100:02d}", 16) (tens digit -> high
nibble, units digit -> low nibble — BCD-style, not straight binary).
Confirmed against live 'pageExists' events during the spike (page 131 ->
magazine 1, byte 0x31 = 49 decimal, matches observed traffic).

Live carousel, not poll/fetch
------------------------------
Unlike a NOS-style single-shot GET, there is no "page ready" response you
fetch on demand. You request a page (a "slot" acquisition) and then wait for
the real broadcast carousel to cycle round to it — observed 5-20s depending
on magazine position — after which the server begins forwarding "header"/
"row" frames for exactly that page as they're transmitted, and continues
forwarding updates every time it re-airs for as long as the slot stays
acquired. Treat the grid as a live, continuously-updating surface, not a
cached snapshot — there is no single instant at which the page is "done".

Fastext targets (packet 27 / FLOF)
------------------------------------
Real fastext link targets are NOT in any JSON field — they're broadcast as
packet 27 (rownum 27, same "row" message shape as ordinary content rows,
just routed differently: see `decode_flof_packet()`) and are Hamming-8/4
coded (NOT the Hamming-24/18 triplet coding X/26 and X/28 enhancement
packets use — this decode is simpler, one nibble per `hamming_8_4_decode`
call). Ported from `teletext.js`/`tv.js`'s `linkbuttonhandler()` /
packet-27 case, both cached from https://nmsceefax.co.uk during EXP-005;
the Hamming 8/4 inverse table below was extracted programmatically from
that source, not hand-transcribed.

X/27 designation 0 (FLOF) carries 6 links (indices 0-3 = red/green/yellow/
cyan fastext buttons — the only ones this module decodes; index 4 is
unused by the reference client's own UI, index 5 is a non-colour "index"
link, both skipped here). Each link is 6 raw bytes (36 total after the 1
designation byte): 2 nibbles pack a BCD page-in-magazine byte (same
encoding `page_to_magazine_byte()` produces), 4 nibbles pack a 16-bit
subcode-and-relative-magazine field. The target magazine is the packet's
own broadcast magazine XORed with a 3-bit relative offset extracted from
that field — pages can fastext-link across magazines, not just within one.

NOTE: the reference JS has a real operator-precedence bug in its "is this
link unset" check (`x & 0x3F7F == 0x3F7F` parses as `x & (0x3F7F==0x3F7F)`
= `x & 1` in JS, not the intended `(x & 0x3F7F) == 0x3F7F`). This module
implements the evidently-intended check, not the buggy one.
"""
from __future__ import annotations

import base64
import json
import threading
import time

import websocket  # pip install websocket-client

DEFAULT_URL = "wss://internal.nathanmediaservices.co.uk/websockets/ceefax"
DEFAULT_CHANNEL_ID = (
    "WyJubXMtY2VlZmF4IiwiaW50ZXJuYWwubmF0aGFubWVkaWFzZXJ2aWNlcy5jby51ayIsIi93ZWJzb2NrZXRzL2NlZWZheCJd"
)
SUBCODE_WILDCARD = 0x3F7F
ROWS, COLS = 25, 40
KEEPALIVE_SECS = 5


def page_to_magazine_byte(page: int) -> tuple[int, int]:
    """NNN (100-899) -> (magazine 1-8, page-in-magazine byte, BCD-style)."""
    if not (100 <= page <= 899):
        raise ValueError(f"page {page} out of range 100-899")
    magazine = page // 100
    suffix = page % 100
    page_byte = int(f"{suffix:02d}", 16)  # tens->high nibble, units->low nibble
    return magazine, page_byte


# ── Hamming 8/4 decode (packet 27 / FLOF only — X/26, X/28 use Hamming 24/18,
#    not implemented here) — table extracted programmatically from
#    teletext.js's `hamming_8_4_inverse`, 256 entries, 0xff = decode error ──
_HAMMING_8_4_INVERSE = [
    0x01, 0xff, 0x01, 0x01, 0xff, 0x00, 0x01, 0xff,
    0xff, 0x02, 0x01, 0xff, 0x0a, 0xff, 0xff, 0x07,
    0xff, 0x00, 0x01, 0xff, 0x00, 0x00, 0xff, 0x00,
    0x06, 0xff, 0xff, 0x0b, 0xff, 0x00, 0x03, 0xff,
    0xff, 0x0c, 0x01, 0xff, 0x04, 0xff, 0xff, 0x07,
    0x06, 0xff, 0xff, 0x07, 0xff, 0x07, 0x07, 0x07,
    0x06, 0xff, 0xff, 0x05, 0xff, 0x00, 0x0d, 0xff,
    0x06, 0x06, 0x06, 0xff, 0x06, 0xff, 0xff, 0x07,
    0xff, 0x02, 0x01, 0xff, 0x04, 0xff, 0xff, 0x09,
    0x02, 0x02, 0xff, 0x02, 0xff, 0x02, 0x03, 0xff,
    0x08, 0xff, 0xff, 0x05, 0xff, 0x00, 0x03, 0xff,
    0xff, 0x02, 0x03, 0xff, 0x03, 0xff, 0x03, 0x03,
    0x04, 0xff, 0xff, 0x05, 0x04, 0x04, 0x04, 0xff,
    0xff, 0x02, 0x0f, 0xff, 0x04, 0xff, 0xff, 0x07,
    0xff, 0x05, 0x05, 0x05, 0x04, 0xff, 0xff, 0x05,
    0x06, 0xff, 0xff, 0x05, 0xff, 0x0e, 0x03, 0xff,
    0xff, 0x0c, 0x01, 0xff, 0x0a, 0xff, 0xff, 0x09,
    0x0a, 0xff, 0xff, 0x0b, 0x0a, 0x0a, 0x0a, 0xff,
    0x08, 0xff, 0xff, 0x0b, 0xff, 0x00, 0x0d, 0xff,
    0xff, 0x0b, 0x0b, 0x0b, 0x0a, 0xff, 0xff, 0x0b,
    0x0c, 0x0c, 0xff, 0x0c, 0xff, 0x0c, 0x0d, 0xff,
    0xff, 0x0c, 0x0f, 0xff, 0x0a, 0xff, 0xff, 0x07,
    0xff, 0x0c, 0x0d, 0xff, 0x0d, 0xff, 0x0d, 0x0d,
    0x06, 0xff, 0xff, 0x0b, 0xff, 0x0e, 0x0d, 0xff,
    0x08, 0xff, 0xff, 0x09, 0xff, 0x09, 0x09, 0x09,
    0xff, 0x02, 0x0f, 0xff, 0x0a, 0xff, 0xff, 0x09,
    0x08, 0x08, 0x08, 0xff, 0x08, 0xff, 0xff, 0x09,
    0x08, 0xff, 0xff, 0x0b, 0xff, 0x0e, 0x03, 0xff,
    0xff, 0x0c, 0x0f, 0xff, 0x04, 0xff, 0xff, 0x09,
    0x0f, 0xff, 0x0f, 0x0f, 0xff, 0x0e, 0x0f, 0xff,
    0x08, 0xff, 0xff, 0x05, 0xff, 0x0e, 0x0d, 0xff,
    0xff, 0x0e, 0x0f, 0xff, 0x0e, 0x0e, 0xff, 0x0e,
]


def hamming_8_4_decode(byte: int) -> int:
    """Returns a 4-bit value (0-0xF), or 0xFF on an uncorrectable error."""
    return _HAMMING_8_4_INVERSE[byte]


# Fastext bar slot -> X/27/0 link index. Matches the reference client's own
# remote-control bindings (remote.js: linkbuttonhandler(0..3) for the colour
# keys) and preview_teletext.py's COLOR_ORDER = [red, green, yellow, cyan].
FLOF_COLOUR_LINK_INDICES = (0, 1, 2, 3)


def decode_flof_packet(packet: bytes, packet_magazine: int) -> dict[int, int] | None:
    """Decode an X/27 packet (40 raw bytes from a rownum==27 'row' message).

    Returns {link_index(0-3): target_page(100-899)} for whichever of the 4
    colour links are set and decode to a plausible page, or None if this
    packet isn't designation 0 (FLOF) — X/27/4 and X/27/5 (POP link tables)
    aren't decoded here, matching M-CEEFAX DS-3's scoped-down MVP.
    """
    if len(packet) < 38:
        return None
    dc = hamming_8_4_decode(packet[0])
    if dc != 0:
        return None

    links: dict[int, int] = {}
    for i in FLOF_COLOUR_LINK_INDICES:
        base = 6 * i + 1
        nibbles = [hamming_8_4_decode(packet[base + k]) & 0xF for k in range(6)]
        l1, l2, l3, l4, l5, l6 = nibbles
        page_byte = l2 * 0x10 + l1
        subcode_mags = l3 | (l4 << 4) | (l5 << 8) | (l6 << 12)

        if page_byte == 0xFF and (subcode_mags & SUBCODE_WILDCARD) == SUBCODE_WILDCARD:
            continue  # unset link (0xFF page, wildcard subcode)

        m1 = (subcode_mags & 0x0080) >> 7
        m2 = (subcode_mags & 0x4000) >> 14
        m3 = (subcode_mags & 0x8000) >> 15
        magazine = packet_magazine ^ ((m3 << 2) | (m2 << 1) | m1)
        if magazine == 0:
            magazine = 8

        tens, units = (page_byte >> 4) & 0xF, page_byte & 0xF
        if tens > 9 or units > 9:
            continue  # not valid BCD digits -> not a real page ref
        page_num = magazine * 100 + tens * 10 + units
        if 100 <= page_num <= 899:
            links[i] = page_num

    return links


class CeefaxClient:
    """Background-threaded WebSocket client mirroring preview_teletext's
    fetch()/parse() surface closely enough to feed the same renderer:
    `.content` is a 1000-char string (25x40, one byte per cell, control
    codes intact) just like NOS's decoded <pre> block.
    """

    def __init__(self, page: int = 100, url: str = DEFAULT_URL,
                 channel_id: str = DEFAULT_CHANNEL_ID):
        self._url = url
        self._channel_id = channel_id
        self._lock = threading.Lock()
        self._content = [0x20] * (ROWS * COLS)  # flat 1000-byte grid, space-filled
        self._dirty = True
        self._connected = False
        self._acquired = False   # True once a pagematched header has landed
        self._flof: dict[int, int] = {}  # link_index(0-3) -> target page, from packet 27
        self._status = "connecting"
        self._page = page
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._stop = False
        self._keepalive_thread: threading.Thread | None = None

    # ── public API ────────────────────────────────────────────────────────
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self._ws:
            self._ws.close()

    def goto(self, page: int):
        """Request a new page: reset the grid and re-issue pagesearch.

        Acquisition (waiting for the broadcast carousel to cycle round to
        this page) takes 3-20s+ depending on magazine position (EXP-005
        finding 4) — NOT instant like a NOS fetch. `self._status` must be
        updated here, not left at the previous page's "acquired" string,
        or callers have no way to distinguish "still waiting" from "hung"
        during that window (this was a real bug: the UI showed a blank grid
        under a stale "acquired page <old>" status for the whole wait).
        """
        with self._lock:
            self._content = [0x20] * (ROWS * COLS)
            self._acquired = False
            self._flof = {}  # stale links from the old page must not linger
            self._page = page
            self._status = f"requesting page {page}..."
            self._dirty = True
        if self._ws and self._connected:
            self._send_pagesearch(page)

    def snapshot(self) -> tuple[str, bool, str, bool, dict[int, int]]:
        """Return (content_1000_chars, dirty, status, acquired, flof) and clear dirty.

        flof: {link_index(0-3): target_page} for fastext colour links decoded
        from the latest packet 27 — see decode_flof_packet(). Empty until a
        packet 27 arrives for the acquired page (some pages don't carry one).
        """
        with self._lock:
            content = "".join(chr(b) for b in self._content)
            dirty = self._dirty
            self._dirty = False
            return content, dirty, self._status, self._acquired, dict(self._flof)

    # ── internals ────────────────────────────────────────────────────────
    def _send_pagesearch(self, page: int):
        magazine, page_byte = page_to_magazine_byte(page)
        self._ws.send(
            f"pagesearch,0,{magazine},{page_byte},{SUBCODE_WILDCARD},true,false,false"
        )

    def _on_open(self, ws):
        self._connected = True
        self._status = "connected, requesting page"
        ws.send(f"service,{self._channel_id}")
        ws.send("ttx,true")
        self._send_pagesearch(self._page)
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()

    def _keepalive_loop(self):
        while not self._stop and self._connected:
            time.sleep(KEEPALIVE_SECS)
            if self._ws and self._connected:
                try:
                    self._ws.send("keepalive")
                except Exception:
                    return

    def _on_message(self, ws, message):
        try:
            m = json.loads(message)
        except Exception:
            return
        cmd = m[0]
        if cmd == "header":
            _slot, b64, pagematched = m[1], m[2], m[3]
            raw = base64.b64decode(b64)
            with self._lock:
                if pagematched:
                    if not self._acquired:
                        self._status = f"acquired page {self._page}"
                    self._acquired = True
                    for i, b in enumerate(raw[8:40]):
                        self._content[0 * COLS + 8 + i] = b & 0x7F
                    self._dirty = True
        elif cmd == "row":
            _slot, magazine, rownum, b64 = m[1], m[2], m[3], m[4]
            if not self._acquired:
                return
            raw = base64.b64decode(b64)
            if 1 <= rownum <= 24:
                with self._lock:
                    for i, b in enumerate(raw[:COLS]):
                        self._content[rownum * COLS + i] = b & 0x7F
                    self._dirty = True
            elif rownum == 27:
                links = decode_flof_packet(raw, magazine)
                if links is not None:
                    with self._lock:
                        self._flof = links
                        self._dirty = True
            # rownum 26/28 (X26/X28 enhancement packets, Hamming 24/18) —
            # not decoded; out of scope (M-CEEFAX DS-3 only covers FLOF).
        # "initialpage", "pageExists", "clock", "secondTick", "channelSettings",
        # "apiver" — cosmetic / not needed to render a page; ignored.

    def _on_error(self, ws, err):
        self._status = f"error: {err}"

    def _on_close(self, ws, code, msg):
        self._connected = False
        self._status = f"closed ({code})"

    def _run(self):
        while not self._stop:
            self._status = "connecting"
            self._ws = websocket.WebSocketApp(
                self._url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws.run_forever(ping_interval=None)
            if self._stop:
                return
            time.sleep(3)  # reconnect backoff


if __name__ == "__main__":
    import sys
    page = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    c = CeefaxClient(page=page)
    c.start()
    try:
        last_status = None
        last_flof = None
        while True:
            content, dirty, status, acquired, flof = c.snapshot()
            if status != last_status:
                print(status)
                last_status = status
            if flof != last_flof:
                print("flof links:", flof)
                last_flof = flof
            if dirty:
                print(f"--- page {page} (acquired={acquired}) ---")
                for r in range(ROWS):
                    row = content[r * COLS:(r + 1) * COLS]
                    print("".join(ch if 0x20 <= ord(ch) < 0x7F else " " for ch in row))
            time.sleep(0.5)
    except KeyboardInterrupt:
        c.stop()
