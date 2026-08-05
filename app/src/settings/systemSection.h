#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>
#include "settingsSection.h"
#include "settingsWidgets.h"
#include "../logSink.h"

extern TFT_eSPI tft;

// ============================================================================
// SystemSection — Settings section for device-wide system controls
// (TASK-400, docs/architecture/designs/M-SYS-REBOOT.md).
//
// v1 scope: a single "Reboot device" row behind a Danger-styled confirm
// screen. The design doc's OQ4 explicitly descopes more rows (heap/
// diagnostics readout, firmware version, factory reset) for now — this
// section makes room for a future System category, not for exactly one
// row forever.
//
// Confirm-frame idiom (message + 2-across sButtonBar) mirrors appsSection.h's
// ManualConfirm/LookupError screens — no new confirm-screen code invented,
// per the design's Lean/decision.
// ============================================================================

enum class SystemView : uint8_t { List, Confirm };

class SystemSection : public SettingsSection {
public:
    // ---- SettingsSection contract -------------------------------------------

    const char* title() const override { return "System"; }

    void enter() override {
        _view = SystemView::List;
        repaint();
    }

    SectionResult tick() override { return SectionResult::Continue; }

    void repaint() override {
        drawHeader();
        clearContent();
        if (_view == SystemView::List) _repaintList();
        else                           _repaintConfirm();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return SectionResult::Continue;

        if (isBackTap(x, y)) {
            // Confirm screen's back-tap mirrors its own Cancel button
            // (appsSection.h _handlePrLocBack precedent) — never a
            // coincidental restart via the header zone.
            if (_view == SystemView::Confirm) {
                _view = SystemView::List;
                repaint();
                return SectionResult::Continue;
            }
            return SectionResult::GoBack;
        }

        if (_view == SystemView::List) _handleListTap(y);
        else                           _handleConfirmTap(x, y);
        return SectionResult::Continue;
    }

private:
    SystemView _view = SystemView::List;

    // Confirm-screen buttons: lazy heap-allocated on first reach, never freed
    // — an embedded SButton[2] (32B) tips the debug build's .dram0.bss over
    // budget at link time (measured: overflow by exactly 32B), same "lazy
    // malloc once, never freed" rule the project already uses for static
    // buffers elsewhere (project memory feedback_dram_bss_static_buffers;
    // TeletextApp's _nosSource() / webRadioApp's wrPumpConnectUrlBuf() are
    // the precedent this mirrors).
    SButton* _confirmBtnsPtr = nullptr;
    SButton* _confirmBtns() {
        if (!_confirmBtnsPtr) _confirmBtnsPtr = new SButton[2];
        return _confirmBtnsPtr;
    }

    // ---- List view -------------------------------------------------------

    void _repaintList() {
        drawChevronRow(S_CONTENT_Y, "Reboot device");
    }

    void _handleListTap(int y) {
        int row = tapToRow(y);
        if (row == 0) {
            _view = SystemView::Confirm;
            clearContent();
            _repaintConfirm();
        }
    }

    // ---- Confirm view ------------------------------------------------------
    // OQ2 (design doc): exact wording is placeholder, not gated.

    void _repaintConfirm() {
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL, S_BG);
        tft.drawString("Reboot now?", S_CANVAS_W / 2, 70, 2);
        tft.setTextColor(S_VALUE_OFF, S_BG);
        tft.drawString("Playback and any unsaved", S_CANVAS_W / 2, 96, 2);
        tft.drawString("activity will restart.",   S_CANVAS_W / 2, 114, 2);
        tft.setTextDatum(TL_DATUM);

        // NOTE: field assignment, not aggregate brace-init — SButton has
        // default member initializers, so it's not an aggregate under this
        // toolchain's -std=gnu++11 (see settingsWidgets.h's own note / LL-112).
        SButton* btns = _confirmBtns();
        btns[0].label = "Cancel";
        btns[0].style = SBtnStyle::Neutral;
        btns[1].label = "Reboot";
        btns[1].style = SBtnStyle::Danger;
        sButtonBar(btns, 2);
        btns[0].draw();
        btns[1].draw();
    }

    void _handleConfirmTap(int x, int y) {
        SButton* btns = _confirmBtns();
        if (btns[0].hit(x, y)) {
            // Cancel — back to the System section, no restart, no side effects.
            btns[0].flash();
            _view = SystemView::List;
            repaint();
            return;
        }
        if (btns[1].hit(x, y)) {
            btns[1].flash();
            // VE-1-1: stable-prefix log line, emitted immediately before the
            // restart itself, so a harness reconnecting after the reset can
            // tell "confirmed via this UI path" apart from a coincidental
            // crash/TWDT reset landing at the same moment — mirrors
            // cmdReboot's own ack (main.cpp:4022-4026). Grep-stable text:
            // "[settings] system-reboot confirmed".
            LOG_I("settings", "system-reboot confirmed");
            Serial.flush();
            delay(50);
            ESP.restart();
        }
    }
};
