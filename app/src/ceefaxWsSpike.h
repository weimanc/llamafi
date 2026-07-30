#pragma once
// ceefaxWsSpike.h — M-CEEFAX DS-2 resource-contention spike.
// rnd/ceefax branch only, never merged to main. Delete alongside the
// cyd2usb_winamp_debug_ceefaxspike platformio.ini env when the experiment
// closes out.
//
// Purpose: hold ONE persistent WSS connection to the live Ceefax relay open
// for the entire session, unconditionally from setup() (not gated behind any
// App's resume()/suspend() — deliberately worse-case: always on, regardless
// of which app is foregrounded), while dataTask's normal fetchers run their
// usual cadence. Observe via `get heap`/`get stacks` (already exist) whether
// a second continuously-open TLS socket reproduces the TASK-285/287/289
// class of heap/TLS starvation already fought through for WebRadio.
//
// Deliberately NOT a full Ceefax client: no page-content parsing, no
// TeletextApp integration, no rendering. DS-2 only cares about connection
// *persistence* and its resource cost, not the protocol payload — the host
// prototype (ceefax_client.py) already proved the protocol/content side.
// The handshake below (service/ttx/pagesearch for page 100, keepalive every
// 5s) is real, matching EXP-005, so the TLS/heap behaviour under test is
// representative of an actual connection, not a synthetic stand-in.

#include <Arduino.h>
#include <WebSocketsClient.h>
#include "dataTaskCerts.h"

namespace ceefaxWsSpike {

// A raw WiFiClientSecure.connect() diagnostic (bypassing WebSocketsClient,
// whose own "connection ... Failed" log swallows the real mbedTLS error)
// found the actual cause of the 100%-repeatable connect failure — confirmed
// even with Spotify entirely disabled, ruling out cross-app contention as
// the cause: `lastError() == -32512 "SSL - Memory allocation failed"`,
// coinciding with free DMA-capable heap dropping to ~35KB right after
// dataTask's own init (vs. ~62-105KB when other connections succeed earlier
// in boot — see EXP-006 follow-up). This is a capacity ceiling, not a
// scheduling race: a fresh mbedTLS session needs more contiguous DMA-capable
// memory than happens to be free at that point in the boot sequence. A
// second raw attempt while memory was this tight also triggered an actual
// crash (Guru Meditation Error / LoadProhibited) on reconnect — a stronger
// finding than "the connection just fails."
//
// Fix: don't attempt a (re)connect at all when there isn't enough headroom
// for it to plausibly succeed — same "check the budget before allocating"
// discipline already used for the WebRadio decoder arena elsewhere in this
// codebase. This governs EVERY (re)connect attempt, not just the first —
// see the gate in _taskBody's loop, not just at startup.
// 45000 was too high — device idle steady-state (no Spotify, nothing fetching)
// sits at ~40KB free DMA and never crosses 45KB at all, so that threshold
// blocked every attempt rather than just unsafe ones. Lowering to bracket the
// actual failure point (~35KB) more tightly while still testing the real
// cliff empirically, not guessing a final number yet.
static constexpr size_t kMinFreeDmaForConnect = 38000;
// 3000 (matching the host client's backoff) turned out too aggressive for
// this manual disconnect()+beginSslWithCA() restart cycle specifically: a
// real TCP+TLS handshake attempt can legitimately take several seconds to
// resolve, and restarting it mid-flight every 3s appears to leave the
// client in a state where it never even reaches its own "connect wss..."
// log line — reset attempts were interrupting themselves. Lengthened to
// give each attempt room to actually resolve (succeed or genuinely fail)
// before intervening again.
static constexpr uint32_t kRetryIntervalMs = 15000;

static const char* const kUrl  = "internal.nathanmediaservices.co.uk";
static const uint16_t    kPort = 443;
static const char* const kPath = "/websockets/ceefax";
static const char* const kChannelId =
    "WyJubXMtY2VlZmF4IiwiaW50ZXJuYWwubmF0aGFubWVkaWFzZXJ2aWNlcy5jby51ayIsIi93ZWJzb2NrZXRzL2NlZWZheCJd";

// Heap-allocated, lazy, never freed — a static-global WebSocketsClient instance
// overflows this debug build's .dram0.bss by 368 bytes at link time (same class
// of issue as the project's existing "lazy malloc once, never freed" rule for
// large static buffers, e.g. WinampDisplay — see project memory
// feedback_dram_bss_static_buffers). Allocated in begin(), lives for the rest
// of the session (this spike is deliberately always-on, never torn down).
static WebSocketsClient* s_ws = nullptr;
static TaskHandle_t      s_task = nullptr;

// Diagnostic counters — plain volatile like spotifyTask's counters
// (appShell-adjacent code already accepts this precedent for Xtensa
// 32-bit-word reads; no torn-read risk at this width).
static volatile bool     s_connected     = false;
static volatile uint32_t s_connectCount  = 0;
static volatile uint32_t s_disconnCount  = 0;
static volatile uint32_t s_msgCount      = 0;
static volatile uint32_t s_bytesTotal    = 0;
static volatile uint32_t s_lastKeepaliveMs = 0;

static void _sendHandshake() {
    char buf[160];
    s_ws->sendTXT(String("service,") + kChannelId);
    s_ws->sendTXT("ttx,true");
    // page 100 = magazine 1, page-in-magazine byte 0x00, subcode wildcard
    // 0x3F7F=16255 — same page_to_magazine_byte() mapping as ceefax_client.py.
    snprintf(buf, sizeof(buf), "pagesearch,0,1,0,16255,true,false,false");
    s_ws->sendTXT(buf);
}

static void _onEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_CONNECTED:
            s_connected = true;
            s_connectCount++;
            Serial.println("[ceefaxSpike] WStype_CONNECTED");
            _sendHandshake();
            break;
        case WStype_DISCONNECTED:
            s_connected = false;
            s_disconnCount++;
            Serial.println("[ceefaxSpike] WStype_DISCONNECTED");
            break;
        case WStype_ERROR:
            Serial.printf("[ceefaxSpike] WStype_ERROR: %.*s\n", (int)length, (const char*)payload);
            break;
        case WStype_TEXT:
            s_msgCount++;
            s_bytesTotal += (uint32_t)length;
            break;
        default:
            break;  // BIN/PING/PONG/FRAGMENT*/ERROR — not needed for this spike
    }
}

static void _taskBody(void*) {
    // Reverted to the original, proven-working flow (begin/onEvent/reconnect-
    // interval set once, library owns its own reconnect state machine) after
    // manually re-driving disconnect()+beginSslWithCA() from outside proved
    // fragile — attempts stopped even reaching the library's own "connect
    // wss..." log line, a worse regression than the bug being fixed. Instead
    // of reimplementing the library's reconnect scheduling, just don't PUMP
    // it (loop() is what advances the internal state machine, including
    // deciding to reconnect) during a low-DMA window — an already-established
    // connection keeps being served normally; only reconnect attempts pause.
    s_ws = new WebSocketsClient();
    s_ws->beginSslWithCA(kUrl, kPort, kPath, CEEFAX_ROOT_CA);
    s_ws->onEvent(_onEvent);
    s_ws->setReconnectInterval(kRetryIntervalMs);

    bool lastGateOk = true;
    for (;;) {
        uint32_t now = millis();
        if (s_connected) {
            s_ws->loop();
        } else {
            size_t freeDma = heap_caps_get_free_size(MALLOC_CAP_DMA);
            bool gateOk = freeDma >= kMinFreeDmaForConnect;
            if (gateOk != lastGateOk) {
                Serial.printf("[ceefaxSpike] reconnect gate %s, freeDma=%u\n",
                              gateOk ? "OPEN" : "CLOSED (low DMA)", (unsigned)freeDma);
                lastGateOk = gateOk;
            }
            if (gateOk) s_ws->loop();
            // else: skip pumping entirely this tick — the library's internal
            // reconnect timer simply doesn't advance while paused, so it
            // picks up exactly where it left off once DMA recovers.
        }
        if (s_connected && (now - s_lastKeepaliveMs >= 5000)) {
            s_ws->sendTXT("keepalive");
            s_lastKeepaliveMs = now;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// Unconditional, one-shot, never torn down (this spike is deliberately
// always-on for the whole session — see file header). No corresponding
// "end()": the point is to observe the worst case, not to model a real
// app's resume()/suspend() lifecycle (that's DS-1/DS-6's concern, already
// resolved on paper — this spike answers DS-2's resource-cost question only).
static void begin() {
    xTaskCreatePinnedToCore(&_taskBody, "ceefaxSpike", 6144, nullptr, 1,
                             &s_task, APP_CPU_NUM);
}

}  // namespace ceefaxWsSpike
