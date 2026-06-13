> Owner: R&D

### EXP-004 — 2026-06-13 — Multi-country Teletext API Wire Format Spike

**Hypothesis**: Other active European teletext services (ORF/AT, ARD/DE, SVT/SE,
RAI/IT, YLE/FI) expose the same wire format as NOS Teletekst — `<pre>` block,
25×40 chars, ISO-8859-1, control codes 0x01–0x17 — and can be added to the
`teletextCountry` enum as config-only changes.

**Approach**: Host-side HTTP fetch + source analysis for each candidate. No DUT
required. NOS format already confirmed in the M-TELETEXT PoC.

---

#### Findings

| Service | URL probed | Format | Size | Classification |
|---------|-----------|--------|------|----------------|
| NOS (NL) | `teletekst-data.nos.nl/page/101` | `<pre>` 25×40, ISO-8859-1, ctrl codes 0x01–0x17 | ~1.1 KB | ✓ native |
| ORF (AT) | `teletext.orf.at/channel/orf1/page/100/1` | Vue.js SPA shell — no content without JS | n/a | ✗ blocked |
| ARD (DE) | `ard-text.de/index.php?page=100` | HTML `div.ardtext_classic`, CSS color classes, UTF-8; CDN blocks direct fetch | unknown | ✗ scrape |
| SVT (SE) | `texttv.nu/api/get/100?includePlainTextContent=1` | JSON; `content_plain` key ~1–2 KB, ~23 rows, UTF-8; 25–30 KB total response | 25–30 KB | ~ JSON |
| RAI (IT) | `servizitelevideo.rai.it/televideo/pub/pagina.jsp?p=100` | PNG images (720×456 px) only; JSP wraps `<img>` | n/a | ✗ hard no |
| YLE (FI) | `yle.fi/tekstitv?P=100` (web) / `external.api.yle.fi/v1/teletext/pages/100.json` (API) | Web: `<pre>` present but 150–200 KB page; API: JSON `text` type (compact) but needs `app_id`+`app_key` | 150–200 KB (web) | ~ gated |

---

#### Finding 1 — NOS format is unique among the five candidates

None of the five services delivers a drop-in `<pre>` block at ~1 KB with the
same 0x01–0x17 control-code scheme. NOS is the only service usable with the
native parser on an ESP32 without modification.

#### Finding 2 — SVT (SE) is the best viable second entry

The `texttv.nu` API (unofficial but stable, used by multiple open-source apps)
provides `content_plain` — a single UTF-8 string with embedded newlines, roughly
23 rows at ~40 chars wide. Payload for that field alone is ~1–2 KB, comparable
to NOS. The total JSON response is 25–30 KB, requiring stream-parsing or a
targeted field extraction (`ArduinoJson` filter doc) to avoid large buffer
allocation on the ESP32.

SVT content uses UTF-8 with no 0x01–0x17 control codes; colours are in the
JSON `content` (HTML) field, which can be ignored when rendering plain text.
The rendered output would be monochrome text only — no colour teletext — but
functional as a news/sports reader.

No authentication required. An `app=` query param is expected by convention
(set to `esp32-teletext` or similar).

#### Finding 3 — ORF and ARD require a server-side proxy

ORF's Vue.js SPA requires a JavaScript engine to render; the underlying XHR
data endpoint was not found via static analysis. ARD's `div.ardtext_classic`
grid is accessible via HTML scraping (BeautifulSoup-style) but the CDN blocks
non-browser requests. Both could be normalised to the NOS `<pre>` format by a
home-server proxy (e.g. a small FastAPI endpoint), but this is out of scope for
on-device firmware.

#### Finding 4 — RAI is incompatible

RAI Televideo delivers all content as rasterized PNG images (720×456 px). There
is no text path. Adding RAI would require OCR — not viable on ESP32.

#### Finding 5 — YLE is feasible via API key registration

YLE's JSON API (`external.api.yle.fi/v1/teletext/pages/{N}.json`) offers a
`text` content type that delivers compact plain text comparable in size to NOS.
It requires a free developer key from `developer.yle.fi`. The web page wrapper
is 150–200 KB and unusable on-device. If a key is obtained, YLE could be
added via a dedicated JSON fetch path (simpler than SVT since the structure
is more regular).

---

#### Conclusions

1. **Hypothesis rejected** — no other tested service matches the NOS wire format
   directly. The `teletextCountry` enum cannot be expanded as a config-only change.

2. **SVT (SE) recommended as first extension** — requires a JSON fetch path
   (stream-parse `content_plain` from `texttv.nu` response), no auth, ~1–2 KB
   usable payload. Colour output not available; plain text rendering acceptable.

3. **YLE (FI) as second extension** — requires API key registration; JSON path
   similar to SVT. Defer until key is available.

4. **ORF / ARD** — blocked on-device; viable only via a LAN proxy. Not
   recommended for on-device MVP.

5. **RAI** — hard no.

---

#### Recommended follow-on (if SVT adopted)

- Add `FETCH_TELETEXT_PAGE_SVT` fetch type to `dataTask`, or parameterise the
  existing `FETCH_TELETEXT_PAGE` with a country selector.
- Use `ArduinoJson` filter doc to extract only `content_plain` from the 25–30 KB
  response, avoiding a full JSON buffer in SRAM.
- Validate on DUT that the filtered extraction fits within the existing HTTP read
  buffer budget (currently sized for ~1.5 KB NOS responses — needs adjustment).
- Plain-text render only; no colour attributes. Document this limitation in
  Settings UI ("SVT: text only").

---

*Feeds: M-TELETEXT DS-6, OQ4*
