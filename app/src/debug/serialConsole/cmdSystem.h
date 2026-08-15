#pragma once
// debug/serialConsole/cmdSystem.h — reboot / advance / help.
// Moved verbatim out of main.cpp (M-SRCLAYOUT). SERIAL_DEBUG-only:
// included from inside main.cpp's `#ifdef SERIAL_DEBUG` block, so this
// file is never reached in a production build.

static void cmdReboot(const char *) {
  prepareForReboot();   // TASK-429/451, see the helper
  Serial.println("{\"ok\":true,\"cmd\":\"reboot\"}");
  Serial.flush();
  delay(50);
  ESP.restart();
}

// TASK-418 / ADR-059 D12: steps the play-order engine WITHOUT decoding audio
// — reads the LocalPlayer instance directly, same "reachable without the
// mode being on screen" contract as `get plCount`/`get plOrder` above, since
// this is what makes T_PLR_20-24 runnable in seconds instead of hours of
// real playback.
static void cmdAdvance(const char *args) {
  const bool next = (strcmp(args, "prev") != 0);   // anything but "prev" == next
  if (strcmp(args, "next") != 0 && strcmp(args, "prev") != 0) {
    Serial.println("{\"ok\":false,\"cmd\":\"advance\",\"error\":\"usage: advance <next|prev>\"}");
    return;
  }
  bool moved = false, reshuffled = false;
  uint16_t row = 0;
  g_LocalPlayerApp.dbgAdvance(next, &moved, &row, &reshuffled);
  Serial.printf("{\"ok\":true,\"cmd\":\"advance\",\"dir\":\"%s\",\"moved\":%s,"
                "\"row\":%u,\"reshuffled\":%s}\n",
                next ? "next" : "prev", moved ? "true" : "false",
                (unsigned)row, reshuffled ? "true" : "false");
}

static void cmdHelp(const char *) {
  // Single JSON line — iterate kCmds[]; table is the single source of truth.
  Serial.print("{\"ok\":true,\"cmd\":\"help\",\"commands\":[");
  for (int i = 0; i < kNumCmds; ++i) {
    if (i > 0) Serial.print(",");
    Serial.printf("{\"name\":\"%s\",\"args\":\"%s\",\"desc\":\"%s\"}",
                  kCmds[i].name, kCmds[i].args, kCmds[i].help);
  }
  Serial.println("]}");
}

