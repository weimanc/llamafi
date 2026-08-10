#pragma once
// localPlayerApp.h — AppId::LocalPlayer placeholder (TASK-413/414).
//
// TASK-413 wires the player slot's third mode into the shell (enum, taskbar
// cycle, taskbar assertion, debug surface); TASK-414 wires its eject stub —
// see ADR-059 D6/D7 and docs/architecture/designs/M-WINAMP-PLAYER-local-playback.md.
// The real file browser / M3U playback UI lands in TASK-415+. Until then
// this is a minimal App so AppId::LocalPlayer is reachable (mode cycle,
// get/set playerMode, reboot-restore, eject stub) without crashing or
// leaving the canvas in a stale state.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "gen/shell_layout.h"
#include "logSink.h"
#include "winamp/winampDisplay.h"

extern TFT_eSPI tft;
extern WinampDisplay winampDisplay;

class LocalPlayerApp : public App {
public:
    void init()    override { _paint(); }
    void resume()  override { _paint(); }
    void suspend() override {}
    void tick()    override {}
    bool handleInput(TouchPhase phase, int x, int y) override {
        // TASK-414 / ADR-059 D6: eject means "load media from this source"
        // in every player mode; here that's "open the file browser". The
        // real modal browser lands in TASK-416 — until then this is a wired
        // stub (logs + consumes the tap) so the affordance exists and T_PLR_06
        // has something to observe, rather than eject silently doing nothing
        // in Player mode.
        if (phase == TouchPhase::Release && winampDisplay.hitTestEject(x, y)) {
            LOG_I("localplayer", "eject tap → open file browser (stub, TASK-416)");
            return true;
        }
        return false;
    }

private:
    void _paint() {
        tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString("Player", TASKBAR_X / 2, 120, 4);
    }
};
