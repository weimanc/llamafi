#pragma once
// localPlayerApp.h — AppId::LocalPlayer placeholder (TASK-413).
//
// TASK-413 only wires the player slot's third mode into the shell (enum,
// taskbar cycle, taskbar assertion, debug surface) — see ADR-059 D6/D7 and
// docs/architecture/designs/M-WINAMP-PLAYER-local-playback.md. The real file
// browser / M3U playback UI lands in TASK-415+. Until then this is a minimal
// App so AppId::LocalPlayer is reachable (mode cycle, get/set playerMode,
// reboot-restore) without crashing or leaving the canvas in a stale state.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "gen/shell_layout.h"

extern TFT_eSPI tft;

class LocalPlayerApp : public App {
public:
    void init()    override { _paint(); }
    void resume()  override { _paint(); }
    void suspend() override {}
    void tick()    override {}
    bool handleInput(TouchPhase phase, int x, int y) override {
        (void)phase; (void)x; (void)y;
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
