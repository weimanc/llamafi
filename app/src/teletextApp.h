#pragma once
// teletextApp.h — live teletext reader (M-TELETEXT ADR-044, M-CEEFAX ADR-057).
// Single-header App class. Slots into appRegistry.h at index 9.
//
// Two TeletextSource backends behind one app (ADR-057 item 1/DS-6): NOS
// Teletekst (page-addressed HTTP poll via dataTask) and NMS Ceefax (a
// persistent WebSocket relay of a real UK broadcast carousel, pump-task
// owned). The render layer below (_drawGrid/_drawStrip/_drawBar/_handle*) is
// 100% shared and untouched by which backend is active — proven on the host
// prototype (preview_teletext.py --source ceefax, EXP-005) before any of this
// was written.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include <freertos/semphr.h>
#include <esp_heap_caps.h>
#include "appShell.h"
#include "dataTask.h"
#include "dataTaskCerts.h"
#include "settingsStorage.h"
#include "gen/teletext_layout.h"
#include "logSink.h"
#include "spotifyTask.h"

extern TFT_eSPI tft;

// ── RGB565 teletext colour palette ────────────────────────────────────────────
static const uint16_t kTTColors[8] = {
    0x0000,  // 0 black
    0xF800,  // 1 red
    0x07E0,  // 2 green
    0xFFE0,  // 3 yellow
    0x001F,  // 4 blue
    0xF81F,  // 5 magenta
    0x07FF,  // 6 cyan
    0xFFFF,  // 7 white
};

// ── Mosaic sub-rects within a CHAR_W×CHAR_H (6×8) cell ──────────────────────
// Bit order: 0=top-left, 1=top-right, 2=mid-left, 3=mid-right, 4=bot-left, 5=bot-right
static const int8_t kMosaicRect[6][4] = {  // { dx, dy, w, h }
    { 0, 0, 3, 3 },  // bit 0 top-left
    { 3, 0, 3, 3 },  // bit 1 top-right
    { 0, 3, 3, 3 },  // bit 2 mid-left
    { 3, 3, 3, 3 },  // bit 3 mid-right
    { 0, 6, 3, 2 },  // bit 4 bot-left
    { 3, 6, 3, 2 },  // bit 5 bot-right
};

// ── Fast-text bar colours (red/green/yellow/cyan) ────────────────────────────
static const uint16_t kFtlBarColors[4] = { 0xF800, 0x07E0, 0xFFE0, 0x07FF };

// ── ISO-8859-1 extended → nearest ASCII printable ────────────────────────────
// Font1 (GLCD) only covers 0x20..0x7E. Characters 0x80..0xFF are mapped to
// their base ASCII letter so the cell background is always drawn and text is
// readable (ë→e, ü→u, etc.) rather than showing stale pixels.
static const uint8_t kLatin1Ascii[128] PROGMEM = {
    // 0x80..0x9F  C1 controls
    ' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',
    ' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',
    // 0xA0..0xAF
    ' ','!','c','L','$','Y','|','p','"','c','a','"','~','-','R','-',
    // 0xB0..0xBF
    'o','+','2','3','\'','u','P','*',',','1','o','"','?','?','?','?',
    // 0xC0..0xCF  À Á Â Ã Ä Å Æ Ç È É Ê Ë Ì Í Î Ï
    'A','A','A','A','A','A','A','C','E','E','E','E','I','I','I','I',
    // 0xD0..0xDF  Ð Ñ Ò Ó Ô Õ Ö × Ø Ù Ú Û Ü Ý Þ ß
    'D','N','O','O','O','O','O','x','O','U','U','U','U','Y','P','B',
    // 0xE0..0xEF  à á â ã ä å æ ç è é ê ë ì í î ï
    'a','a','a','a','a','a','a','c','e','e','e','e','i','i','i','i',
    // 0xF0..0xFF  ð ñ ò ó ô õ ö ÷ ø ù ú û ü ý þ ÿ
    'd','n','o','o','o','o','o','/','o','u','u','u','u','y','p','y',
};

// ── Strip UI colours ─────────────────────────────────────────────────────────
static const uint16_t kStripBg      = 0x1082;  // dark grey ≈ (28,28,28)
static const uint16_t kStripActive  = 0xDEFB;  // light grey ≈ (220,220,220)
static const uint16_t kStripDim     = 0x2104;  // dim grey ≈ (70,70,70) — same as taskbar bg
static const uint16_t kStripBack    = 0x07FF;  // cyan for back zone when history non-empty
static const uint16_t kStripPageNum = 0xA514;  // mid-grey for page number text

// ── Preset start pages ───────────────────────────────────────────────────────
static const uint16_t kPagePresets[] = { 101, 601, 702, 800 };
static const uint8_t  kPollPresets[] = { 30, 60, 120 };

// ── TeletextSource (ADR-057 item 1) ─────────────────────────────────────────
// Ordinary strategy-pattern seam: NOS is a stateless dataTask poll, Ceefax
// owns a persistent pump task. onResume()/onSuspend() mean "no-op" for one
// and "start/stop a FreeRTOS task" for the other — that asymmetry is exactly
// what the interface is for (M-CEEFAX design doc DS-6).
class TeletextSource {
public:
    virtual ~TeletextSource() = default;
    // (Re)activate this backend, requesting `page` as the start page.
    virtual void onResume(uint16_t page) = 0;
    virtual void onSuspend() = 0;
    virtual void navigate(uint16_t page, uint8_t sub) = 0;
    // Writes a fresh grid (page/cells/ftlTargets/ftlLabels/ready) into *out
    // when new content arrived since the last call. Nav metadata
    // (prevPage/nextPage/subpage*) is left untouched here — NOS fills it
    // itself from server metadata; Ceefax has none (DS-3), see
    // usesPageAdjacentNav(). Returns true iff *out was written.
    virtual bool poll(dataTask::TeletextState* out) = 0;
    // True for backends with no pn= metadata (DS-3): caller synthesizes
    // prevPage/nextPage as page±1 and leaves subpage nav permanently absent.
    virtual bool usesPageAdjacentNav() const { return false; }
    virtual bool isConnecting() const = 0;
    virtual bool hasError() const = 0;
    virtual bool hasPendingAsync() const = 0;
};

// ── NOS Teletekst backend — unmodified behaviour, moved off TeletextApp ────
// (TASK-370: "existing NOS behaviour must be provably unchanged" — this is
// the exact tick()/isConnecting()/hasError() logic the old single-class
// TeletextApp had, just relocated so it can sit behind the interface above.)
class NosTeletextSource : public TeletextSource {
public:
    void onResume(uint16_t /*page*/) override {
        _pollSecs     = g_settings.teletextPollSecs;
        _lastFetch    = _forceNow();  // force immediate fetch
        _pendingFetch = false;
        _ttErr        = false;
    }

    void onSuspend() override {}

    void navigate(uint16_t page, uint8_t sub) override {
        _lastFetch    = _forceNow();
        _pendingFetch = true;
        dataTask::enqueueTeletextPage(page, sub);
    }

    bool poll(dataTask::TeletextState* out) override {
        unsigned long now = millis();
        if (!_pendingFetch && (now - _lastFetch >= (unsigned long)_pollSecs * 1000UL)) {
            dataTask::enqueueTeletextPage(out->page);
            _lastFetch    = now;
            _pendingFetch = true;
        }

        dataTask::TeletextState result;
        if (dataTask::pollTeletext(&result)) {
            _pendingFetch = false;
            if (result.ready) {
                *out   = result;
                _ttErr = false;   // TASK-246: success clears red
                _ready = true;
                return true;
            }
            _ttErr = true;        // TASK-246: fetch returned but page not parsed → red
        }
        return false;
    }

    // TASK-245 / ADR-046: amber "connecting" bar until the first page renders.
    bool isConnecting() const override { return !_ready; }
    // TASK-246: red bar when the last page fetch failed (cleared on next success).
    bool hasError() const override { return _ttErr; }
    bool hasPendingAsync() const override { return _pendingFetch; }

    // ── Debug-surface parity (BP-036) — see TeletextApp::dbgSet ─────────────
    void debugForceImmediateFetch() { _lastFetch = _forceNow(); }
    void debugClearPending()        { _pendingFetch = false; }

private:
    uint8_t       _pollSecs     = 60;
    unsigned long _lastFetch    = 0;
    bool          _pendingFetch = false;
    bool          _ttErr        = false;
    bool          _ready        = false;

    // Returns a _lastFetch sentinel that makes the elapsed check immediately
    // true regardless of millis() value (handles early-boot case where
    // millis() < pollSecs*1000 and a plain 0 would not trigger the condition).
    unsigned long _forceNow() const {
        return millis() - (unsigned long)_pollSecs * 1000UL;
    }
};

// ── Ceefax backend (M-CEEFAX / ADR-057) ─────────────────────────────────────
// Dedicated pump task, mirroring webRadioApp.h's wrEnsurePumpTask()/
// wrTeardownPumpTask() ack-based teardown (item 2). Only this task ever
// touches the WebSocketsClient — navigate()/onResume()/onSuspend(), called
// from loopTask, only touch the spinlock-guarded fields below; the pump task
// owns _ws exclusively and deletes it itself at teardown, so no cross-task
// synchronization is needed on the client object itself.
class CeefaxTeletextSource : public TeletextSource {
public:
    void onResume(uint16_t page) override {
        _resetForPage(page);
        // Arm the sustained-failure timer from activation, not from the
        // first WStype_DISCONNECTED — DUT-observed (TASK-372): on a bad
        // network day the very first connect attempt can fail silently
        // (DMA-gate closed the whole session, or a raw connect() failure
        // the library doesn't surface as an event at all), so waiting for
        // a disconnect event to ever fire would mean hasError() never
        // latches even after arbitrarily long total failure — the class of
        // bug ADR-057 item 7 explicitly calls out avoiding.
        _disconnectedSinceMs = millis();
        _ensurePumpTask();
    }

    void onSuspend() override {
        _teardownPumpTask();
    }

    void navigate(uint16_t page, uint8_t /*sub*/) override {
        _resetForPage(page);
    }

    bool poll(dataTask::TeletextState* out) override {
        bool wasDirty = false;
        portENTER_CRITICAL_SAFE(&_mux);
        if (_dirty) {
            out->page = _reqPage;
            out->ready = _acquired;
            memcpy(out->cells, _cells, sizeof(out->cells));
            memcpy(out->ftlTargets, _ftlTargets, sizeof(out->ftlTargets));
            _dirty = false;
            wasDirty = true;
        }
        portEXIT_CRITICAL_SAFE(&_mux);
        if (wasDirty) _deriveFtlLabels(out);
        return wasDirty;
    }

    // DS-3: no pn= metadata — caller synthesizes page±1.
    bool usesPageAdjacentNav() const override { return true; }

    // DS-7: fires on every navigation, not just first-ever load — the
    // acquisition wait (3-20s+) is long and visible on every page change.
    // Deliberate divergence from NOS's one-time gate; do not "fix" this to
    // match NOS.
    bool isConnecting() const override {
        bool acquired;
        portENTER_CRITICAL_SAFE(&_mux);
        acquired = _acquired;
        portEXIT_CRITICAL_SAFE(&_mux);
        return !acquired;
    }

    // DS-7: sustained-failure latch, not a raw reconnect pass-through.
    // Ordinary 3s/15s-backoff reconnects are not errors; only a connection
    // that has stayed down across at least 2 retry cycles latches red
    // (EXP-006: N≥2 consecutive failed reconnect attempts). Self-clears the
    // instant a reconnect succeeds — matches SpotifyApp/WebRadioApp's
    // sticky/self-clearing hasError() contract (ADR-046 Amendment 2).
    bool hasError() const override {
        bool connected;
        unsigned long since;
        portENTER_CRITICAL_SAFE(&_mux);
        connected = _connected;
        since     = _disconnectedSinceMs;
        portEXIT_CRITICAL_SAFE(&_mux);
        if (connected || since == 0) return false;
        return (millis() - since) >= (2 * kRetryIntervalMs);
    }

    bool hasPendingAsync() const override { return isConnecting(); }

    // ── Debug surface (BP-036) ───────────────────────────────────────────────
    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "ceefaxStatus") == 0) {
            bool connected, acquired; unsigned long since;
            portENTER_CRITICAL_SAFE(&_mux);
            connected = _connected; acquired = _acquired; since = _disconnectedSinceMs;
            portEXIT_CRITICAL_SAFE(&_mux);
            snprintf(buf, len,
                     "\"var\":\"ceefaxStatus\",\"connected\":%s,\"acquired\":%s,"
                     "\"downMs\":%lu,\"hasError\":%s,\"last\":true",
                     connected ? "true" : "false", acquired ? "true" : "false",
                     since ? (unsigned long)(millis() - since) : 0UL,
                     hasError() ? "true" : "false");
            return true;
        }
        return false;
    }

private:
    // TASK-370 (ADR-057 items 2/6): pump-task transport + cert alias.
    static constexpr const char* kHost = "internal.nathanmediaservices.co.uk";
    static constexpr uint16_t kPort = 443;
    static constexpr const char* kPath = "/websockets/ceefax";
    static constexpr const char* kChannelId =
        "WyJubXMtY2VlZmF4IiwiaW50ZXJuYWwubmF0aGFubWVkaWFzZXJ2aWNlcy5jby51ayIsIi93ZWJzb2NrZXRzL2NlZWZheCJd";

    // TASK-370 (ADR-057 item 3): DMA-gated reconnect thresholds. The
    // free-bytes threshold was originally ceefaxWsSpike.h/EXP-006's value
    // (38000), but that spike's narrow build (production base + this
    // feature only) has both less DMA-capable fragmentation AND a higher
    // idle baseline (~40-45K) than the real production build (TFT_eSPI,
    // WiFi, MEMBUDGET_PHASE1's arena, etc. all compete for the same pool).
    // DUT-confirmed on THIS build (TASK-370 gate soak): a raw free-byte
    // count above the spike's threshold is NOT sufficient on its own —
    // start_ssl_client() crashed (Guru Meditation / LoadProhibited in
    // strlen(), same failure class as EXP-006) at freeDma=66288, because
    // the free bytes weren't one contiguous block. mbedTLS needs a
    // contiguous allocation (CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN=16384 per
    // handshake buffer), so the gate also checks
    // heap_caps_get_largest_free_block() — the same fragmentation-aware
    // pattern webRadioApp.h already uses (mb_arena / EXP-010).
    // PROP-008 follow-up isolation (2026-07-30): this build's baseline idle
    // freeDma sits at ~36-37K regardless of whether Spotify is running —
    // below the original 38000, meaning the gate almost never opened at
    // all in practice. Lowered to 30000 (comfortably under that idle
    // reading, still requiring genuine headroom) so real attempts can
    // actually fire; kMinLargestFreeBlockForConnect (the fragmentation
    // check that stopped the crash) and kMaxConsecutiveAttempts (the
    // attempt cap that stopped it recurring) are UNCHANGED — this change
    // only affects how often an attempt gets a chance to run, not what
    // happens once it does. *** Re-soak (crash + connectivity + Spotify
    // coexistence) before trusting — do not assume safe from reasoning
    // alone, per feedback memory persistent-conn-dma-gate-pattern. ***
    static constexpr size_t   kMinFreeDmaForConnect         = 30000;
    static constexpr size_t   kMinLargestFreeBlockForConnect = 20000;
    static constexpr uint32_t kRetryIntervalMs      = 15000;

    // TASK-374: hard cap on consecutive connect attempts per activation.
    // DUT-confirmed the crash above can still recur even above
    // kMinLargestFreeBlockForConnect (seen once at lfbDma=27636, higher than
    // a prior clean 5-minute run at 21492) — the free-block size isn't a
    // fully reliable predictor, this looks like WiFiClientSecure/mbedTLS
    // internal state on repeated connect() calls against the same
    // WebSocketsClient object, not purely a memory-size question, and
    // fully root-causing it is out of scope for this milestone (ADR-057
    // already declines a framework rebuild). Since a crash is a harder
    // requirement than "best-effort connectivity" (ADR-057 accepts flaky
    // connects, not device resets), bound the exposure instead of retrying
    // forever: after this many consecutive failed attempts with no
    // WStype_CONNECTED in between, stop calling loop() in the disconnected
    // branch for the rest of this activation. hasError() still latches
    // (downMs keeps climbing) so the taskbar correctly shows the sustained
    // failure; onResume() resets the counter, so leaving and re-entering
    // Ceefax (or a reboot) gets a fresh budget.
    static constexpr uint8_t kMaxConsecutiveAttempts = 5;

    static constexpr UBaseType_t kStackWords = (8 * 1024) / sizeof(StackType_t);
    // *** DUT-VERIFY (TASK-370 gate): sized as a starting point, not assumed
    // from WebRadio's pump-task precedent — this task's stack additionally
    // holds a StaticJsonDocument for inbound frame parsing. ***

    mutable portMUX_TYPE _mux = portMUX_INITIALIZER_UNLOCKED;
    uint16_t _reqPage     = 100;
    bool     _acquired    = false;
    bool     _dirty       = false;
    bool     _sendPending = false;
    uint8_t  _cells[25][40];
    uint16_t _ftlTargets[4] = {};
    bool     _connected   = false;
    unsigned long _disconnectedSinceMs = 0;

    WebSocketsClient* _ws      = nullptr;
    TaskHandle_t      _task    = nullptr;
    SemaphoreHandle_t _ackSem  = nullptr;
    volatile bool     _stopReq = false;
    unsigned long     _lastKeepaliveMs = 0;
    unsigned long     _lastAttemptMs   = 0;  // TASK-374: throttles reconnect attempts to once/kRetryIntervalMs
    uint8_t           _consecutiveAttempts = 0;  // TASK-374: kMaxConsecutiveAttempts cap

    void _resetForPage(uint16_t page) {
        portENTER_CRITICAL_SAFE(&_mux);
        _reqPage  = page;
        _acquired = false;
        _dirty    = false;
        memset(_cells, 0x20, sizeof(_cells));
        memset(_ftlTargets, 0, sizeof(_ftlTargets));
        _sendPending = true;
        portEXIT_CRITICAL_SAFE(&_mux);
    }

    // Idempotent — safe to call on every onResume() (mirrors wrEnsurePumpTask()).
    void _ensurePumpTask() {
        if (_task) return;
        if (!_ackSem) _ackSem = xSemaphoreCreateBinary();
        _stopReq = false;
        BaseType_t rc = xTaskCreatePinnedToCore(&_trampoline, "ceefaxPump", kStackWords,
                                                 this, 1, &_task, APP_CPU_NUM);
        if (rc != pdPASS) {
            LOG_E("ceefax", "xTaskCreatePinnedToCore failed rc=%d", (int)rc);
            _task = nullptr;
        }
    }

    // Enforced teardown [mirrors wrTeardownPumpTask()]: signal stop, wait
    // (bounded) for the pump's ack. The pump itself owns disconnecting and
    // freeing _ws before it acks — best-effort on timeout, matches this
    // codebase's "never crash, degrade" philosophy elsewhere in WebRadio.
    void _teardownPumpTask() {
        if (!_task) return;
        _stopReq = true;
        if (xSemaphoreTake(_ackSem, pdMS_TO_TICKS(5000)) != pdTRUE)
            LOG_E("ceefax", "pump teardown ack timeout — pump may be stuck in loop()");
        _task = nullptr;
    }

    static void _trampoline(void* arg) {
        static_cast<CeefaxTeletextSource*>(arg)->_taskBody();
    }

    void _sendHandshake() {
        _ws->sendTXT(String("service,") + kChannelId);
        _ws->sendTXT("ttx,true");
    }

    void _sendPageSearch(uint16_t page) {
        uint16_t magazine = page / 100;
        uint16_t suffix   = page % 100;
        uint8_t  pageByte = (uint8_t)(((suffix / 10) << 4) | (suffix % 10));  // BCD
        char buf[64];
        snprintf(buf, sizeof(buf), "pagesearch,0,%u,%u,16255,true,false,false",
                 (unsigned)magazine, (unsigned)pageByte);
        _ws->sendTXT(buf);
    }

    static int8_t _b64Val(char c) {
        if (c >= 'A' && c <= 'Z') return (int8_t)(c - 'A');
        if (c >= 'a' && c <= 'z') return (int8_t)(c - 'a' + 26);
        if (c >= '0' && c <= '9') return (int8_t)(c - '0' + 52);
        if (c == '+') return 62;
        if (c == '/') return 63;
        return -1;
    }

    static size_t _b64Decode(const char* in, uint8_t* out, size_t outCap) {
        size_t o = 0; int val = 0, bits = -8;
        for (const char* p = in; *p && *p != '='; p++) {
            int8_t c = _b64Val(*p);
            if (c < 0) continue;
            val = (val << 6) + c;
            bits += 6;
            if (bits >= 0) {
                if (o < outCap) out[o++] = (uint8_t)((val >> bits) & 0xFF);
                bits -= 8;
            }
        }
        return o;
    }

    // Hamming 8/4 inverse table (packet 27 / FLOF only — X/26, X/28 use
    // Hamming 24/18, not needed here). Table extracted programmatically from
    // teletext.js's hamming_8_4_inverse during EXP-005; transcribed verbatim
    // from ceefax_client.py, not hand-derived. 0xff = decode error.
    static uint8_t _hamming84(uint8_t b) {
        static const uint8_t kInverse[256] PROGMEM = {
            0x01,0xff,0x01,0x01,0xff,0x00,0x01,0xff, 0xff,0x02,0x01,0xff,0x0a,0xff,0xff,0x07,
            0xff,0x00,0x01,0xff,0x00,0x00,0xff,0x00, 0x06,0xff,0xff,0x0b,0xff,0x00,0x03,0xff,
            0xff,0x0c,0x01,0xff,0x04,0xff,0xff,0x07, 0x06,0xff,0xff,0x07,0xff,0x07,0x07,0x07,
            0x06,0xff,0xff,0x05,0xff,0x00,0x0d,0xff, 0x06,0x06,0x06,0xff,0x06,0xff,0xff,0x07,
            0xff,0x02,0x01,0xff,0x04,0xff,0xff,0x09, 0x02,0x02,0xff,0x02,0xff,0x02,0x03,0xff,
            0x08,0xff,0xff,0x05,0xff,0x00,0x03,0xff, 0xff,0x02,0x03,0xff,0x03,0xff,0x03,0x03,
            0x04,0xff,0xff,0x05,0x04,0x04,0x04,0xff, 0xff,0x02,0x0f,0xff,0x04,0xff,0xff,0x07,
            0xff,0x05,0x05,0x05,0x04,0xff,0xff,0x05, 0x06,0xff,0xff,0x05,0xff,0x0e,0x03,0xff,
            0xff,0x0c,0x01,0xff,0x0a,0xff,0xff,0x09, 0x0a,0xff,0xff,0x0b,0x0a,0x0a,0x0a,0xff,
            0x08,0xff,0xff,0x0b,0xff,0x00,0x0d,0xff, 0xff,0x0b,0x0b,0x0b,0x0a,0xff,0xff,0x0b,
            0x0c,0x0c,0xff,0x0c,0xff,0x0c,0x0d,0xff, 0xff,0x0c,0x0f,0xff,0x0a,0xff,0xff,0x07,
            0xff,0x0c,0x0d,0xff,0x0d,0xff,0x0d,0x0d, 0x06,0xff,0xff,0x0b,0xff,0x0e,0x0d,0xff,
            0x08,0xff,0xff,0x09,0xff,0x09,0x09,0x09, 0xff,0x02,0x0f,0xff,0x0a,0xff,0xff,0x09,
            0x08,0x08,0x08,0xff,0x08,0xff,0xff,0x09, 0x08,0xff,0xff,0x0b,0xff,0x0e,0x03,0xff,
            0xff,0x0c,0x0f,0xff,0x04,0xff,0xff,0x09, 0x0f,0xff,0x0f,0x0f,0xff,0x0e,0x0f,0xff,
            0x08,0xff,0xff,0x05,0xff,0x0e,0x0d,0xff, 0xff,0x0e,0x0f,0xff,0x0e,0x0e,0xff,0x0e,
        };
        return pgm_read_byte(&kInverse[b]);
    }

    // X/27 designation 0 (FLOF): 6 links (colour buttons 0-3 = red/green/
    // yellow/cyan; indices 4/5 not decoded, matching this milestone's scope).
    // Returns true iff this is a designation-0 packet; targets[i]=0 means
    // that colour has no link on this page (real teletext decoders leave the
    // button inert in that case — not a gap to close).
    static bool _decodeFlofPacket(const uint8_t* raw, size_t rawLen,
                                   uint8_t packetMagazine, uint16_t targets[4]) {
        if (rawLen < 38) return false;
        if (_hamming84(raw[0]) != 0) return false;
        for (int i = 0; i < 4; i++) {
            int base = 6 * i + 1;
            uint8_t l1 = _hamming84(raw[base + 0]) & 0xF;
            uint8_t l2 = _hamming84(raw[base + 1]) & 0xF;
            uint8_t l3 = _hamming84(raw[base + 2]) & 0xF;
            uint8_t l4 = _hamming84(raw[base + 3]) & 0xF;
            uint8_t l5 = _hamming84(raw[base + 4]) & 0xF;
            uint8_t l6 = _hamming84(raw[base + 5]) & 0xF;
            uint8_t  pageByte    = (uint8_t)(l2 * 0x10 + l1);
            uint16_t subcodeMags = (uint16_t)(l3 | (l4 << 4) | (l5 << 8) | (l6 << 12));

            if (pageByte == 0xFF && (subcodeMags & 0x3F7F) == 0x3F7F) { targets[i] = 0; continue; }

            uint16_t m1 = (subcodeMags & 0x0080) >> 7;
            uint16_t m2 = (subcodeMags & 0x4000) >> 14;
            uint16_t m3 = (subcodeMags & 0x8000) >> 15;
            uint8_t magazine = packetMagazine ^ (uint8_t)((m3 << 2) | (m2 << 1) | m1);
            if (magazine == 0) magazine = 8;

            uint8_t tens = (pageByte >> 4) & 0xF, units = pageByte & 0xF;
            if (tens > 9 || units > 9) { targets[i] = 0; continue; }
            uint16_t pageNum = (uint16_t)(magazine * 100 + tens * 10 + units);
            targets[i] = (pageNum >= 100 && pageNum <= 899) ? pageNum : 0;
        }
        return true;
    }

    // Row-24 fastext label text — same colour-segment scan as NOS's own
    // extraction (dataTaskStorage.cpp fetchTeletext()), byte-identical
    // control-code scheme confirmed by EXP-005. Kept as a local copy rather
    // than a shared helper so the NOS fetch path is untouched (TASK-370
    // no-regression requirement).
    static void _deriveFtlLabels(dataTask::TeletextState* out) {
        static const uint8_t kFtlColors[4] = { 1, 2, 3, 6 };  // red, green, yellow, cyan
        uint8_t row24[40];
        memcpy(row24, out->cells[24], 40);
        for (int i = 0; i < 4; i++) {
            char lbl[12] = {}; int llen = 0; uint8_t curFg = 7;
            for (int ci = 0; ci < 40; ci++) {
                uint8_t c = row24[ci];
                if (c >= 0x01 && c <= 0x07) { curFg = c; continue; }
                if (c >= 0x10 && c <= 0x17) { curFg = c & 0x07; continue; }
                if (c < 0x20) continue;
                if (curFg == kFtlColors[i] && llen < 11) lbl[llen++] = (char)c;
            }
            while (llen > 0 && lbl[llen - 1] == ' ') llen--;
            lbl[llen] = '\0';
            strlcpy(out->ftlLabels[i], lbl, sizeof(out->ftlLabels[i]));
        }
    }

    // Runs entirely on the pump task (called synchronously from ws->loop()).
    void _onMessage(uint8_t* payload, size_t length) {
        StaticJsonDocument<384> doc;
        if (deserializeJson(doc, (const char*)payload, length)) return;
        JsonArray arr = doc.as<JsonArray>();
        if (arr.isNull() || arr.size() < 2) return;
        const char* cmd = arr[0].as<const char*>();
        if (!cmd) return;

        if (strcmp(cmd, "header") == 0 && arr.size() >= 4) {
            const char* b64 = arr[2].as<const char*>();
            bool pagematched = arr[3].as<bool>();
            if (!b64 || !pagematched) return;
            uint8_t raw[40];
            if (_b64Decode(b64, raw, sizeof(raw)) < 40) return;
            portENTER_CRITICAL_SAFE(&_mux);
            _acquired = true;
            for (int i = 0; i < 32; i++) _cells[0][8 + i] = raw[8 + i] & 0x7F;
            _dirty = true;
            portEXIT_CRITICAL_SAFE(&_mux);
        } else if (strcmp(cmd, "row") == 0 && arr.size() >= 5) {
            bool acquired;
            portENTER_CRITICAL_SAFE(&_mux);
            acquired = _acquired;
            portEXIT_CRITICAL_SAFE(&_mux);
            if (!acquired) return;
            uint8_t magazine  = (uint8_t)arr[2].as<int>();
            int     rownum    = arr[3].as<int>();
            const char* b64   = arr[4].as<const char*>();
            if (!b64) return;
            uint8_t raw[40];
            if (_b64Decode(b64, raw, sizeof(raw)) < 40) return;
            if (rownum >= 1 && rownum <= 24) {
                portENTER_CRITICAL_SAFE(&_mux);
                memcpy(_cells[rownum], raw, 40);
                _dirty = true;
                portEXIT_CRITICAL_SAFE(&_mux);
            } else if (rownum == 27) {
                uint16_t targets[4] = { 0, 0, 0, 0 };
                if (_decodeFlofPacket(raw, sizeof(raw), magazine, targets)) {
                    portENTER_CRITICAL_SAFE(&_mux);
                    memcpy(_ftlTargets, targets, sizeof(_ftlTargets));
                    _dirty = true;
                    portEXIT_CRITICAL_SAFE(&_mux);
                }
            }
            // rownum 26/28 (X26/X28 enhancement, Hamming 24/18) — out of
            // scope, DS-3.
        }
        // "initialpage"/"pageExists"/"clock"/"secondTick"/"channelSettings"/
        // "apiver" — cosmetic, not needed to render a page.
    }

    void _onEvent(WStype_t type, uint8_t* payload, size_t length) {
        switch (type) {
            case WStype_CONNECTED:
                portENTER_CRITICAL_SAFE(&_mux);
                _connected = true;
                _disconnectedSinceMs = 0;
                _sendPending = true;  // (re)send pagesearch for the current requested page
                portEXIT_CRITICAL_SAFE(&_mux);
                _consecutiveAttempts = 0;  // TASK-374: a real connect resets the attempt budget
                LOG_I("ceefax", "WStype_CONNECTED");
                _sendHandshake();
                break;
            case WStype_DISCONNECTED:
                portENTER_CRITICAL_SAFE(&_mux);
                _connected = false;
                if (_disconnectedSinceMs == 0) _disconnectedSinceMs = millis();
                portEXIT_CRITICAL_SAFE(&_mux);
                LOG_I("ceefax", "WStype_DISCONNECTED");
                break;
            case WStype_ERROR:
                LOG_W("ceefax", "WStype_ERROR: %.*s", (int)length, (const char*)payload);
                break;
            case WStype_TEXT:
                _onMessage(payload, length);
                break;
            default:
                break;  // BIN/PING/PONG/FRAGMENT* — not needed
        }
    }

    void _taskBody() {
        _ws = new WebSocketsClient();
        _ws->onEvent([this](WStype_t t, uint8_t* p, size_t l) { _onEvent(t, p, l); });
        _ws->beginSslWithCA(kHost, kPort, kPath, CEEFAX_ROOT_CA);
        _ws->setReconnectInterval(kRetryIntervalMs);
        _lastAttemptMs = millis() - kRetryIntervalMs;  // attempt immediately on first tick
        _consecutiveAttempts = 0;

        bool lastGateOk = true;
        for (;;) {
            if (_stopReq) {
                _ws->disconnect();
                delete _ws;
                _ws = nullptr;
                xSemaphoreGive(_ackSem);
                vTaskDelete(NULL);
            }

            bool connectedSnapshot;
            portENTER_CRITICAL_SAFE(&_mux);
            connectedSnapshot = _connected;
            portEXIT_CRITICAL_SAFE(&_mux);

            unsigned long now = millis();

            if (connectedSnapshot) {
                _ws->loop();
            } else {
                // TASK-370 (ADR-057 item 3): gate reconnect attempts on free
                // DMA-capable heap AND largest contiguous block — an
                // established connection is served normally regardless,
                // only reconnect attempts pause. See kMinLargestFreeBlock-
                // ForConnect's comment above: raw free bytes alone let a
                // real crash through in this build (fragmentation).
                size_t freeDma = heap_caps_get_free_size(MALLOC_CAP_DMA);
                size_t lfbDma  = heap_caps_get_largest_free_block(MALLOC_CAP_DMA);
                bool gateOk = freeDma >= kMinFreeDmaForConnect
                           && lfbDma  >= kMinLargestFreeBlockForConnect;
                if (gateOk != lastGateOk) {
                    LOG_I("ceefax", "reconnect gate %s freeDma=%u lfbDma=%u",
                          gateOk ? "OPEN" : "CLOSED (low DMA)",
                          (unsigned)freeDma, (unsigned)lfbDma);
                    lastGateOk = gateOk;
                }
                // TASK-374 (M-CEEFAX close-out gate): the DMA gate alone
                // stops the crash but NOT cross-app TLS degradation —
                // DUT-confirmed (8-min coexistence soak): pumping loop()
                // every 20ms tick raced Spotify's independent poller
                // constantly, and it went 0/8 successful with genuine
                // SSL -32512 "Memory allocation failed" for the whole
                // session. This project already has a protocol for exactly
                // this class of conflict (architecture.md "TLS coexistence"
                // — every dataTask HTTPS fetch brackets itself with
                // tlsYield()/tlsResume()), but wrapping *every* 20ms tick
                // with it would mean Spotify is yielded continuously for as
                // long as the gate stays open (worse than the race). Fix:
                // only ever call loop() at all in this disconnected branch
                // once per kRetryIntervalMs, under the yield bracket — same
                // "just don't pump it" precedent as the gate itself
                // (ceefaxWsSpike.h: skipping loop() entirely simply pauses
                // the library's internal reconnect timer, it doesn't lose
                // track of time), so every real attempt this task ever makes
                // happens inside tlsYield()/tlsResume(), none unwrapped.
                if (gateOk && _consecutiveAttempts < kMaxConsecutiveAttempts
                           && now - _lastAttemptMs >= kRetryIntervalMs) {
                    _lastAttemptMs = now;
                    _consecutiveAttempts++;
                    spotifyTask::tlsYield();
                    _ws->loop();
                    spotifyTask::tlsResume();
                    if (_consecutiveAttempts == kMaxConsecutiveAttempts) {
                        LOG_W("ceefax", "giving up after %u consecutive attempts this session",
                              (unsigned)kMaxConsecutiveAttempts);
                    }
                }
            }

            uint16_t pageSnapshot; bool sendNow;
            portENTER_CRITICAL_SAFE(&_mux);
            sendNow = _connected && _sendPending;
            pageSnapshot = _reqPage;
            if (sendNow) _sendPending = false;
            portEXIT_CRITICAL_SAFE(&_mux);
            if (sendNow) _sendPageSearch(pageSnapshot);

            if (connectedSnapshot && now - _lastKeepaliveMs >= 5000) {
                _ws->sendTXT("keepalive");
                _lastKeepaliveMs = now;
            }

            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
};

class TeletextApp : public App {
public:
    void init() override {
        memset(&_st, 0, sizeof(_st));
        _histDepth = 0;
        _lastTapMs = 0;
        _lastAction[0] = '\0';
        _activeCountry = 0xFF;  // unset — _activateSource() below always runs before first use
        // TASK-373 bug caught on DUT (persistence round-trip test): appShell
        // calls init() XOR resume() on a given app's first-ever entry per
        // session (never both — see main.cpp switchApp()), so backend
        // activation can't live in resume() alone or a fresh boot's very
        // first Teletext visit silently stays on NOS regardless of the
        // persisted teletextCountry. Shared with resume() below.
        _activateSource();
    }

    void resume() override {
        _activateSource();
        _draw();
    }

    // Shared by init() and resume() — see init()'s comment on why both need it.
    void _activateSource() {
        uint8_t wantCountry = (g_settings.teletextCountry == 1) ? 1 : 0;
        if (_activeCountry != 0xFF && wantCountry != _activeCountry) {
            // M-CEEFAX DS-6 "what's genuinely new risk": a live source
            // switch must fully tear down the previous backend's connection
            // before the new one starts, and stale nav-metadata/content from
            // the old backend must not linger on screen.
            _activeOf(_activeCountry)->onSuspend();
            memset(&_st, 0, sizeof(_st));
        }
        _activeCountry = wantCountry;
        _st.page   = g_settings.teletextPage;
        _injectedContent = false;
        _numpadActive = false;
        _numpadCount  = 0;
        _active()->onResume(_st.page);
    }

    void suspend() override { _active()->onSuspend(); }

    // TASK-245/246 (ADR-046), DS-7: delegate to the active backend — NOS and
    // Ceefax intentionally use different isConnecting()/hasError() semantics
    // (see CeefaxTeletextSource's comments), not a bug to unify.
    bool isConnecting() const override { return _active()->isConnecting(); }
    bool hasError() const override { return _active()->hasError(); }

    void tick() override {
        if (_active()->poll(&_st)) {
            if (_active()->usesPageAdjacentNav()) {
                _st.prevPage    = (_st.page > 100) ? _st.page - 1 : 0;
                _st.nextPage    = (_st.page < 899) ? _st.page + 1 : 0;
                _st.subpageNext = _st.subpagePrev = 0;
                _st.subpageNextSub = _st.subpagePrevSub = 0;
            }
            _draw();
        }
    }

    bool hasPendingAsync() const override { return _active()->hasPendingAsync(); }

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return false;

        // 300 ms debounce
        unsigned long now = millis();
        if (now - _lastTapMs < 300) {
            strlcpy(_lastAction, "DEBOUNCE", sizeof(_lastAction));
            return false;
        }
        _lastTapMs = now;

        // Strip is always live (back, nav) even when numpad is active
        if (x >= TTXT_STRIP_X && x < TTXT_STRIP_X + TTXT_STRIP_W && y < TTXT_BAR_Y0) {
            return _handleStrip(y);
        }

        if (_numpadActive) {
            if (y >= TTXT_BAR_Y0 && y <= TTXT_BAR_Y1) {
                // Fast-text tap while numpad open: dismiss numpad, navigate
                _numpadActive = false; _numpadCount = 0;
                return _handleBar(x);
            }
            return _handleNumpad(x, y);
        }

        if (y >= TTXT_BAR_Y0 && y <= TTXT_BAR_Y1) {
            return _handleBar(x);
        }
        if (y < TTXT_BAR_Y0) {
            return _handleGrid(x, y);
        }
        strlcpy(_lastAction, "NONE", sizeof(_lastAction));
        return false;
    }

    // ── Serial debug accessors ────────────────────────────────────────────────
    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "teletextReady") == 0) {
            snprintf(buf, len, "\"var\":\"teletextReady\",\"ready\":%s,\"last\":true",
                     _st.ready ? "true" : "false");
            return true;
        }
        if (strcmp(var, "teletextPage") == 0) {
            snprintf(buf, len, "\"var\":\"teletextPage\",\"page\":%u,\"last\":true",
                     (unsigned)_st.page);
            return true;
        }
        if (strcmp(var, "teletextPollSecs") == 0) {
            snprintf(buf, len, "\"var\":\"teletextPollSecs\",\"pollSecs\":%u,\"last\":true",
                     (unsigned)g_settings.teletextPollSecs);
            return true;
        }
        if (strcmp(var, "teletextHttpCode") == 0) {
            snprintf(buf, len, "\"var\":\"teletextHttpCode\",\"val\":%d,\"last\":true",
                     dataTask::lastTeletextHttpCode());
            return true;
        }
        if (strcmp(var, "teletextLastAction") == 0) {
            snprintf(buf, len, "\"var\":\"teletextLastAction\",\"val\":\"%s\",\"last\":true",
                     _lastAction);
            return true;
        }
        if (strcmp(var, "teletextHasSubpages") == 0) {
            bool has = (_st.subpageNext || _st.subpagePrev);
            snprintf(buf, len, "\"var\":\"teletextHasSubpages\",\"val\":%s,\"last\":true",
                     has ? "true" : "false");
            return true;
        }
        if (strcmp(var, "teletextSubpage") == 0) {
            snprintf(buf, len,
                     "\"var\":\"teletextSubpage\","
                     "\"next\":%u,\"nextSub\":%u,\"prev\":%u,\"prevSub\":%u,\"last\":true",
                     (unsigned)_st.subpageNext, (unsigned)_st.subpageNextSub,
                     (unsigned)_st.subpagePrev, (unsigned)_st.subpagePrevSub);
            return true;
        }
        // TASK-373: which backend is active (0=NOS/1=Ceefax), mirrors the
        // Settings toggle so a serial harness can confirm the switch landed.
        if (strcmp(var, "teletextBackend") == 0) {
            snprintf(buf, len, "\"var\":\"teletextBackend\",\"val\":\"%s\",\"last\":true",
                     (_activeCountry == 1) ? "ceefax" : "nos");
            return true;
        }
        if (_ceefax && _ceefax->dbgGet(var, buf, len)) return true;
        return false;
    }

    bool dbgSet(const char* var, const char* val) {
        if (strcmp(var, "teletextPage") == 0) {
            int pg = atoi(val);
            if (pg >= 100 && pg <= 899) {
                _st.page = (uint16_t)pg;
                g_settings.teletextPage = _st.page;
                _nosSource()->debugForceImmediateFetch();
            }
            return true;
        }
        if (strcmp(var, "triggerTeletextFetch") == 0 && strcmp(val, "1") == 0) {
            _nosSource()->debugForceImmediateFetch();
            _nosSource()->debugClearPending();  // allow tick() to enqueue even if prior fetch pending
            return true;
        }
        if (strcmp(var, "teletextSubpageNext") == 0) {
            // Format: "617-2" sets subpageNext=617 subpageNextSub=2; "0" clears.
            int pg = atoi(val);
            const char* dash = strchr(val, '-');
            uint8_t sub = (dash && dash[1]) ? (uint8_t)atoi(dash + 1) : 0;
            _st.subpageNext    = (pg >= 100 && pg <= 899) ? (uint16_t)pg : 0;
            _st.subpageNextSub = _st.subpageNext ? sub : 0;
            _drawStrip();
            return true;
        }
        if (strcmp(var, "teletextSubpagePrev") == 0) {
            int pg = atoi(val);
            const char* dash = strchr(val, '-');
            uint8_t sub = (dash && dash[1]) ? (uint8_t)atoi(dash + 1) : 0;
            _st.subpagePrev    = (pg >= 100 && pg <= 899) ? (uint16_t)pg : 0;
            _st.subpagePrevSub = _st.subpagePrev ? sub : 0;
            _drawStrip();
            return true;
        }
        if (strcmp(var, "teletextPageContent") == 0) {
            // Inject synthetic page content from hex-encoded 2000-char string.
            // Encoding: contiguous hex pairs, e.g. "204e4f53..."
            // 2000 hex chars = 1000 bytes = 25×40 grid.
            int vlen = strlen(val);
            if (vlen == 2000) {
                for (int r = 0; r < 25; r++) {
                    for (int ci = 0; ci < 40; ci++) {
                        int idx = (r * 40 + ci) * 2;
                        char hi = val[idx], lo = val[idx+1];
                        auto hexv = [](char c) -> uint8_t {
                            if (c >= '0' && c <= '9') return c - '0';
                            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                            return 0;
                        };
                        _st.cells[r][ci] = (uint8_t)((hexv(hi) << 4) | hexv(lo));
                    }
                }
                _st.ready = true;
                _injectedContent = true;
                _draw();
            }
            return true;
        }
        return false;
    }

private:
    // Both backends lazy heap-allocated, never freed — embedding either
    // (each polymorphic, and CeefaxTeletextSource's 25×40 cell grid alone is
    // 1000 bytes) overflows this debug build's .dram0.bss at link time, same
    // class of issue as the project's existing "lazy malloc once, never
    // freed" rule for large static buffers (e.g. WinampDisplay,
    // ceefaxWsSpike's WebSocketsClient — see project memory
    // feedback_dram_bss_static_buffers). In practice _nos is allocated on
    // the app's very first entry regardless of backend (init()/resume()
    // always need SOME source); _ceefax only the first time teletextCountry
    // actually selects Ceefax.
    NosTeletextSource*    _nos     = nullptr;
    CeefaxTeletextSource* _ceefax  = nullptr;
    // Which backend is live (0xFF = unset, before the first resume()) — a
    // 1-byte country code instead of a stored TeletextSource* pointer;
    // _active()/_activeOf() resolve it to the (lazily-allocated) object on
    // every call. Every extra stored pointer here costs the same 4 bytes the
    // debug build's .dram0.bss budget is already fighting for (see the
    // lazy-allocation comment above), so this app deliberately trades a
    // pointer dereference for that byte.
    uint8_t _activeCountry = 0xFF;

    NosTeletextSource* _nosSource() {
        if (!_nos) _nos = new NosTeletextSource();
        return _nos;
    }
    CeefaxTeletextSource* _ceefaxSource() {
        if (!_ceefax) _ceefax = new CeefaxTeletextSource();
        return _ceefax;
    }
    TeletextSource* _activeOf(uint8_t country) {
        return (country == 1) ? (TeletextSource*)_ceefaxSource() : (TeletextSource*)_nosSource();
    }
    TeletextSource* _active() const {
        return const_cast<TeletextApp*>(this)->_activeOf(_activeCountry == 0xFF ? 0 : _activeCountry);
    }

    dataTask::TeletextState _st      = {};
    uint16_t _history[10]= {};
    uint8_t  _histDepth  = 0;
    unsigned long _lastTapMs  = 0;
    bool     _injectedContent = false;
    char     _lastAction[16]  = {};
    bool     _numpadActive    = false;
    uint8_t  _numpadDigits[3] = {};
    uint8_t  _numpadCount     = 0;

    // ── Navigation helpers ────────────────────────────────────────────────────
    void _navigate(uint16_t page, uint8_t sub = 0) {
        if (!page || page < 100 || page > 899) return;
        if (_histDepth < 10) _history[_histDepth++] = _st.page;
        _st.page = page;
        _active()->navigate(page, sub);
    }

    void _goBack() {
        if (_histDepth == 0) return;
        _st.page = _history[--_histDepth];
        _active()->navigate(_st.page, 0);
    }

    // ── Input handlers ───────────────────────────────────────────────────────
    bool _handleStrip(int y) {
        if (y >= TTXT_STRIP_SUBUP_Y0 && y <= TTXT_STRIP_SUBUP_Y1) {
            strlcpy(_lastAction, "STRIP_SUBUP", sizeof(_lastAction));
            if (_st.subpagePrev) _navigate(_st.subpagePrev, _st.subpagePrevSub);
            return true;
        }
        if (y >= TTXT_STRIP_PAGE_Y0 && y <= TTXT_STRIP_PAGE_Y1) {
            strlcpy(_lastAction, "STRIP_PAGE", sizeof(_lastAction));
            _numpadActive = !_numpadActive;
            _numpadCount  = 0;
            if (_numpadActive) _drawNumpad(); else _draw();
            return true;
        }
        if (y >= TTXT_STRIP_BACK_Y0 && y <= TTXT_STRIP_BACK_Y1) {
            strlcpy(_lastAction, "STRIP_BACK", sizeof(_lastAction));
            if (_numpadActive) {
                _numpadActive = false; _numpadCount = 0; _draw();
            } else if (_histDepth > 0) {
                _goBack();
            }
            return true;
        }
        if (y >= TTXT_STRIP_PREV_Y0 && y <= TTXT_STRIP_PREV_Y1) {
            strlcpy(_lastAction, "STRIP_PREV", sizeof(_lastAction));
            if (_st.prevPage) _navigate(_st.prevPage);
            return true;
        }
        if (y >= TTXT_STRIP_NEXT_Y0 && y <= TTXT_STRIP_NEXT_Y1) {
            strlcpy(_lastAction, "STRIP_NEXT", sizeof(_lastAction));
            if (_st.nextPage) _navigate(_st.nextPage);
            return true;
        }
        if (y >= TTXT_STRIP_SUBDN_Y0 && y <= TTXT_STRIP_SUBDN_Y1) {
            strlcpy(_lastAction, "STRIP_SUBDN", sizeof(_lastAction));
            if (_st.subpageNext) _navigate(_st.subpageNext, _st.subpageNextSub);
            return true;
        }
        strlcpy(_lastAction, "NONE", sizeof(_lastAction));
        return false;
    }

    bool _handleBar(int x) {
        int btn = x / TTXT_FTL_BTN_W;
        if (btn < 0) btn = 0;
        if (btn > 3) btn = 3;
        char act[16]; snprintf(act, sizeof(act), "BAR_FTL%d", btn);
        strlcpy(_lastAction, act, sizeof(_lastAction));
        if (_st.ftlTargets[btn]) _navigate(_st.ftlTargets[btn]);
        return true;
    }

    bool _handleGrid(int x, int y) {
        int row = y / TTXT_CHAR_H;
        int tap_col = x / TTXT_CHAR_W;
        if (row < 0 || row >= 25) { strlcpy(_lastAction, "NONE", sizeof(_lastAction)); return false; }

        // Scan row for isolated 3-digit page ref within ±3 cols of tap point
        const uint8_t* rowData = _st.cells[row];
        uint16_t found = 0;
        for (int ci = 0; ci <= 37; ci++) {
            uint8_t c0 = rowData[ci], c1 = rowData[ci+1], c2 = rowData[ci+2];
            if (c0 >= '1' && c0 <= '8' && c1 >= '0' && c1 <= '9' && c2 >= '0' && c2 <= '9') {
                uint16_t pg = (c0-'0')*100 + (c1-'0')*10 + (c2-'0');
                if (pg >= 100 && pg <= 899) {
                    int ref_col = ci + 1;  // centre of 3-digit ref
                    if (abs(ref_col - tap_col) <= 3) { found = pg; break; }
                }
            }
        }
        if (found) {
            strlcpy(_lastAction, "GRID_LINK", sizeof(_lastAction));
            _navigate(found);
            return true;
        }
        strlcpy(_lastAction, "GRID_NONE", sizeof(_lastAction));
        return false;
    }

    // ── Numpad overlay ────────────────────────────────────────────────────────
    // Layout: 3×4 grid of 74×39 px buttons starting at (9, 35).
    // Row 0: 1 2 3  Row 1: 4 5 6  Row 2: 7 8 9  Row 3: DEL 0 GO
    static constexpr int kNpBtnW = 74, kNpBtnH = 39, kNpBtnGap = 1;
    static constexpr int kNpX0   = 9,  kNpY0   = 35, kNpRowH   = 40;

    void _drawNumpad() {
        tft.fillRect(0, 0, TTXT_GRID_W, TTXT_BAR_Y0, 0x1082);

        // Input display — three digit slots
        static const uint16_t kEntered = 0xFFE0;  // yellow
        static const uint16_t kEmpty   = 0x7BEF;  // light grey
        int sy = 17;
        for (int i = 0; i < 3; i++) {
            int sx = 60 + i * 40;
            if (i < (int)_numpadCount) {
                char ch[2] = { (char)('0' + _numpadDigits[i]), '\0' };
                tft.setTextColor(kEntered, 0x1082);
                tft.setTextDatum(MC_DATUM);
                tft.drawString(ch, sx, sy, 4);
            } else {
                tft.drawFastHLine(sx - 8, sy + 12, 16, kEmpty);
            }
        }

        // Buttons
        static const char* const kLabels[12] = {
            "1","2","3","4","5","6","7","8","9","DEL","0","GO"
        };
        bool canGo = (_numpadCount == 3);
        for (int i = 0; i < 12; i++) {
            int col = i % 3, row = i / 3;
            int bx = kNpX0 + col * (kNpBtnW + kNpBtnGap);
            int by = kNpY0 + row * kNpRowH;
            uint16_t bg;
            if      (i == 9)  bg = 0x8000;                        // DEL: dark red
            else if (i == 11) bg = canGo ? 0x07E0 : 0x0320;       // GO: bright/dim green
            else              bg = 0x3186;                          // digit: dark grey
            tft.fillRoundRect(bx, by, kNpBtnW, kNpBtnH, 3, bg);
            tft.setTextColor(0xFFFF, bg);
            tft.setTextDatum(MC_DATUM);
            tft.drawString(kLabels[i], bx + kNpBtnW / 2, by + kNpBtnH / 2, 2);
        }
        _drawStrip();
    }

    bool _handleNumpad(int x, int y) {
        if (y >= TTXT_BAR_Y0) { strlcpy(_lastAction, "NONE", sizeof(_lastAction)); return false; }
        int col = (x - kNpX0) / (kNpBtnW + kNpBtnGap);
        int row = (y - kNpY0) / kNpRowH;
        if (col < 0 || col > 2 || row < 0 || row > 3 || x >= kNpX0 + 3 * (kNpBtnW + kNpBtnGap)) {
            // Tap outside grid — dismiss
            _numpadActive = false; _numpadCount = 0;
            _draw();
            strlcpy(_lastAction, "NUMPAD_DISMISS", sizeof(_lastAction));
            return true;
        }
        static const int8_t kMap[12] = { 1,2,3, 4,5,6, 7,8,9, -1,0,-2 };
        int8_t val = kMap[row * 3 + col];
        if (val == -1) {  // DEL
            if (_numpadCount > 0) _numpadCount--;
            _drawNumpad();
            strlcpy(_lastAction, "NUMPAD_DEL", sizeof(_lastAction));
        } else if (val == -2) {  // GO
            strlcpy(_lastAction, "NUMPAD_GO", sizeof(_lastAction));
            _numpadGo();
        } else {
            if (_numpadCount < 3) {
                _numpadDigits[_numpadCount++] = (uint8_t)val;
                _drawNumpad();
                char act[16]; snprintf(act, sizeof(act), "NUMPAD_%d", (int)val);
                strlcpy(_lastAction, act, sizeof(_lastAction));
                if (_numpadCount == 3) _numpadGo();
            }
        }
        return true;
    }

    void _numpadGo() {
        if (_numpadCount < 3) return;
        uint16_t pg = (uint16_t)_numpadDigits[0] * 100
                    + (uint16_t)_numpadDigits[1] * 10
                    + (uint16_t)_numpadDigits[2];
        _numpadActive = false;
        _numpadCount  = 0;
        if (pg >= 100 && pg <= 899) {
            _navigate(pg);
        } else {
            _draw();  // invalid page — just dismiss numpad
        }
    }

    // ── Renderer ──────────────────────────────────────────────────────────────
    void _draw() {
        _drawGrid();
        _drawStrip();
        _drawBar();
    }

    void _drawGrid() {
        tft.setTextFont(1);
        tft.setTextDatum(TL_DATUM);
        for (int ri = 0; ri < 25; ri++) {
            uint8_t fg = 7, bg = 0;
            bool gfxMode = false;
            for (int ci = 0; ci < 40; ci++) {
                uint8_t c = _st.cells[ri][ci];
                int px = ci * TTXT_CHAR_W;
                int py = ri * TTXT_CHAR_H;

                // Process control codes (consume; render as background cell)
                if (c >= 0x01 && c <= 0x07) { fg = c; gfxMode = false;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c == 0x10) { fg = 0; gfxMode = true;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c >= 0x11 && c <= 0x17) { fg = c & 0x07; gfxMode = true;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c == 0x1C) { bg = 0;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c == 0x1D) { bg = fg;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c < 0x20) {
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }

                if (gfxMode) {
                    // Mosaic: extract 6-bit pattern (bit5 always 1 to stay printable)
                    uint8_t pat = (c & 0x1F) | ((c & 0x40) >> 1);
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]);
                    for (int b = 0; b < 6; b++) {
                        if (pat & (1 << b)) {
                            tft.fillRect(px + kMosaicRect[b][0], py + kMosaicRect[b][1],
                                         kMosaicRect[b][2], kMosaicRect[b][3], kTTColors[fg]);
                        }
                    }
                } else {
                    // Text mode: Font1 covers 0x20..0x7E; map extended Latin-1 to ASCII base
                    uint8_t ch = (c <= 0x7E) ? c
                                             : (uint8_t)pgm_read_byte(&kLatin1Ascii[c - 0x80]);
                    tft.drawChar(px, py, (char)ch, kTTColors[fg], kTTColors[bg], 1);
                }
            }
        }
    }

    void _drawStrip() {
        tft.fillRect(TTXT_STRIP_X, 0, TTXT_STRIP_W, TTXT_GRID_H, kStripBg);

        int cx = TTXT_STRIP_X + TTXT_STRIP_W / 2;

        // Zone 0 — subpage ▲ (y=0..33)
        {
            uint16_t col = (_st.subpagePrev) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_SUBUP_Y0 + TTXT_STRIP_SUBUP_Y1) / 2;
            _drawTriUp(cx, mid - 4, 8, col);
        }
        // Zone 1 — page number (y=34..66)
        {
            int mid = (TTXT_STRIP_PAGE_Y0 + TTXT_STRIP_PAGE_Y1) / 2;
            char pbuf[4]; snprintf(pbuf, sizeof(pbuf), "%u", (unsigned)_st.page);
            tft.setTextFont(1);
            tft.setTextColor(kStripPageNum, kStripBg);
            tft.setTextDatum(MC_DATUM);
            tft.drawString(pbuf, cx, mid, 1);
            tft.setTextDatum(TL_DATUM);
        }
        // Zone 2 — ◄◄ back (y=67..99)
        {
            uint16_t col = (_histDepth > 0) ? kStripBack : kStripDim;
            int mid = (TTXT_STRIP_BACK_Y0 + TTXT_STRIP_BACK_Y1) / 2;
            _drawTriLeft(cx - 2, mid, 6, col);
            _drawTriLeft(cx + 3, mid, 6, col);
        }
        // Zone 3 — ◄ prev page (y=100..132)
        {
            uint16_t col = (_st.prevPage) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_PREV_Y0 + TTXT_STRIP_PREV_Y1) / 2;
            _drawTriLeft(cx, mid, 8, col);
        }
        // Zone 4 — ► next page (y=133..165)
        {
            uint16_t col = (_st.nextPage) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_NEXT_Y0 + TTXT_STRIP_NEXT_Y1) / 2;
            _drawTriRight(cx, mid, 8, col);
        }
        // Zone 5 — subpage ▼ (y=166..199)
        {
            uint16_t col = (_st.subpageNext) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_SUBDN_Y0 + TTXT_STRIP_SUBDN_Y1) / 2;
            _drawTriDown(cx, mid + 4, 8, col);
        }
    }

    void _drawBar() {
        for (int i = 0; i < 4; i++) {
            int x0 = i * TTXT_FTL_BTN_W;
            tft.fillRect(x0, TTXT_BAR_Y0, TTXT_FTL_BTN_W, TTXT_BAR_H, kFtlBarColors[i]);
            if (_st.ftlLabels[i][0]) {
                tft.setTextFont(1);
                tft.setTextColor(TFT_BLACK, kFtlBarColors[i]);
                tft.setTextDatum(MC_DATUM);
                tft.drawString(_st.ftlLabels[i], x0 + TTXT_FTL_BTN_W / 2,
                               TTXT_BAR_Y0 + TTXT_BAR_H / 2, 1);
                tft.setTextDatum(TL_DATUM);
            }
        }
        // Fill the 3-pixel gap at x=272..274 not reached by any button (4*68=272)
        tft.fillRect(4 * TTXT_FTL_BTN_W, TTXT_BAR_Y0,
                     TTXT_STRIP_X + TTXT_STRIP_W - 4 * TTXT_FTL_BTN_W, TTXT_BAR_H, 0x0000);
    }

    // ── Arrow glyph helpers (fillTriangle) ───────────────────────────────────
    void _drawTriUp(int cx, int tip_y, int h, uint16_t col) {
        int base_y = tip_y + h;
        int half_w = h / 2;
        tft.fillTriangle(cx, tip_y, cx - half_w, base_y, cx + half_w, base_y, col);
    }
    void _drawTriDown(int cx, int tip_y, int h, uint16_t col) {
        int base_y = tip_y - h;
        int half_w = h / 2;
        tft.fillTriangle(cx, tip_y, cx - half_w, base_y, cx + half_w, base_y, col);
    }
    void _drawTriLeft(int cx, int cy, int h, uint16_t col) {
        int half_w = h / 2;
        tft.fillTriangle(cx - half_w, cy, cx + half_w, cy - half_w, cx + half_w, cy + half_w, col);
    }
    void _drawTriRight(int cx, int cy, int h, uint16_t col) {
        int half_w = h / 2;
        tft.fillTriangle(cx + half_w, cy, cx - half_w, cy - half_w, cx - half_w, cy + half_w, col);
    }
};
