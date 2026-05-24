#pragma once
// logServer.h — permanent post-connect HTTP server for the /log endpoint
// (ADR-010 / TASK-016a).
//
// Stands up a WebServer bound explicitly to WiFi.localIP() (LAN-only
// invariant per ADR-010). The WiFiManager portal server and the
// refreshToken.h server both run on port 80 during onboarding and are
// torn down once setup completes — start this only after both are gone.
//
//   GET /log           — last 80 lines, plain text
//   GET /log?n=N       — last N lines (capped at ring size)
//   GET /log?clear=1   — empty the ring; returns "ok\n"
//
// No authentication — same threat model as the existing serial monitor.

#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>

#include "logSink.h"

namespace logsink {

inline WebServer *&serverInstance() {
  static WebServer *s = nullptr;
  return s;
}

inline void handleLog(WebServer &s) {
  if (s.hasArg("clear")) {
    ringClear();
    s.send(200, "text/plain", "ok\n");
    return;
  }
  int n = 80;
  if (s.hasArg("n")) {
    int v = s.arg("n").toInt();
    if (v > 0) n = v;
  }
  s.sendHeader("Cache-Control", "no-store");
  s.setContentLength(CONTENT_LENGTH_UNKNOWN);
  s.send(200, "text/plain", "");
  ringForEachLast(n, [&s](const char *buf, size_t len) {
    s.sendContent(buf);
    if (len == 0 || buf[len - 1] != '\n') s.sendContent("\n");
  });
  s.sendContent("");  // close chunked stream
}

inline void serverBegin() {
  if (serverInstance() != nullptr) return;
  IPAddress ip = WiFi.localIP();
  WebServer *s = new WebServer(ip, 80);
  s->on("/log", [s]() { handleLog(*s); });
  s->onNotFound([s]() {
    s->send(404, "text/plain", "not found — try /log\n");
  });
  s->begin();
  serverInstance() = s;
  ESP_LOGI("log", "server listening on http://%s/log", ip.toString().c_str());
}

inline void serverLoop() {
  WebServer *s = serverInstance();
  if (s) s->handleClient();
}

}  // namespace logsink
