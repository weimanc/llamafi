#pragma once
// teletextApp.h — live teletext reader (M-TELETEXT ADR-044).
// Self-contained per D0/SF.11 (M-SRCLAYOUT Stage E / TASK-471). Method
// bodies live in teletextApp.cpp.
//
// NOS Teletekst (page-addressed HTTP poll via dataTask), behind a
// TeletextSource strategy seam. A second source (NMS Ceefax, a persistent
// WebSocket relay) was implemented under ADR-057 then CUT (ADR-058: its
// persistent TLS/WS connection alone exceeded this hardware's DMA budget —
// it connected but dropped ~90ms later, before a page could render). The
// seam and the render layer (_drawGrid/_drawStrip/_drawBar/_handle*) are kept
// intact so a future second source could slot in without touching rendering.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "gen/teletext_layout.h"
#include "logSink.h"

#include "display/tft.h"

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
    void onResume(uint16_t /*page*/) override;
    void onSuspend() override {}
    void navigate(uint16_t page, uint8_t sub) override;
    bool poll(dataTask::TeletextState* out) override;

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

class TeletextApp : public App {
public:
    void init() override;
    void resume() override;

    // Shared by init() and resume(). NOS Teletekst is the only backend — the
    // NMS Ceefax second source was cut (ADR-058: not viable within this
    // hardware's DMA budget). The TeletextSource seam is kept for a possible
    // future backend.
    void _activateSource();

    void suspend() override { _active()->onSuspend(); }

    // TASK-245/246 (ADR-046): delegate to the active backend.
    bool isConnecting() const override { return _active()->isConnecting(); }
    bool hasError() const override { return _active()->hasError(); }

    void tick() override;

    bool hasPendingAsync() const override { return _active()->hasPendingAsync(); }

    // TASK-518 (P4): in-flight = the active backend's _pendingFetch — set by
    // navigate() (a user page request) and by poll()'s cadence re-fetch, and
    // cleared in poll() the moment dataTask::pollTeletext() delivers, on the
    // parse-failure path as well as the success path (teletextApp.h:139, ahead
    // of the result.ready branch). Transient and self-clearing, so
    // hasPendingAsync() is already the right answer; stated explicitly because
    // this app's isConnecting() is one of the traps.
    //
    // isConnecting() NOT reusable: NosTeletextSource::isConnecting() is
    // !_ready, a never-had-data latch set once on the first page that renders
    // and never re-armed. A Teletext sitting on a rendered page with no fetch
    // outstanding is idle, and !_ready would call it busy forever if the very
    // first fetch ever failed.
    bool hasInFlightOp() const override { return _active()->hasPendingAsync(); }

    bool handleInput(TouchPhase phase, int x, int y) override;

    // ── Serial debug accessors ────────────────────────────────────────────────
    bool dbgGet(const char* var, char* buf, int len) const;
    bool dbgSet(const char* var, const char* val);

#ifdef SERIAL_DEBUG
    // TASK-635 (M-HARNESS2 R14): `get armed` predicate + `set injclear`
    // clear — read/clear the existing _injectedContent flag, no new state.
    bool dbgArmedInjectedContent() const  { return _injectedContent; }
    void dbgClearInjectedContent()        { _injectedContent = false; }
#endif

private:
    // NOS backend lazy heap-allocated on first entry, never freed — embedding
    // the polymorphic source overflows the debug build's .dram0.bss at link
    // time, same "lazy malloc once, never freed" rule the project uses for
    // large static buffers (e.g. WinampDisplay — see project memory
    // feedback_dram_bss_static_buffers).
    NosTeletextSource* _nos = nullptr;

    NosTeletextSource* _nosSource() {
        if (!_nos) _nos = new NosTeletextSource();
        return _nos;
    }
    // Only one backend remains (Ceefax cut, ADR-058). Kept as _active() (rather
    // than inlining _nosSource() everywhere) so the TeletextSource seam stays
    // intact for a possible future second source.
    TeletextSource* _active() const {
        return const_cast<TeletextApp*>(this)->_nosSource();
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
    void _navigate(uint16_t page, uint8_t sub = 0);
    void _goBack();

    // ── Input handlers ───────────────────────────────────────────────────────
    bool _handleStrip(int y);
    bool _handleBar(int x);
    bool _handleGrid(int x, int y);

    // ── Numpad overlay ────────────────────────────────────────────────────────
    // Layout: 3×4 grid of 74×39 px buttons starting at (9, 35).
    // Row 0: 1 2 3  Row 1: 4 5 6  Row 2: 7 8 9  Row 3: DEL 0 GO
    static constexpr int kNpBtnW = 74, kNpBtnH = 39, kNpBtnGap = 1;
    static constexpr int kNpX0   = 9,  kNpY0   = 35, kNpRowH   = 40;

    void _drawNumpad();
    bool _handleNumpad(int x, int y);
    void _numpadGo();

    // ── Renderer ──────────────────────────────────────────────────────────────
    void _draw();
    void _drawGrid();
    void _drawStrip();
    void _drawBar();

    // ── Arrow glyph helpers (fillTriangle) ───────────────────────────────────
    void _drawTriUp(int cx, int tip_y, int h, uint16_t col);
    void _drawTriDown(int cx, int tip_y, int h, uint16_t col);
    void _drawTriLeft(int cx, int cy, int h, uint16_t col);
    void _drawTriRight(int cx, int cy, int h, uint16_t col);
};
