#pragma once

// Time bootstrap fallback when NTP (UDP/123) is blocked.
// Connects to a TLS host with cert validation disabled, parses the Date:
// header from the response, sets system clock via settimeofday().
//
// Insecure TLS is acceptable here: we only trust the Date header to within a
// few seconds, and the subsequent real Spotify requests do full cert
// validation against the now-correct clock.

#include <WiFiClient.h>
#include <sys/time.h>
#include <time.h>

// Last-resort: parse compile time __DATE__ "Mmm dd yyyy" + __TIME__ "HH:MM:SS"
// into a UTC time_t. Off by however long since the build (drift ~build-age).
// Acceptable for cert notBefore checks; useless for anything signature-bound.
inline time_t buildEpoch() {
  static const char *months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  const char *d = __DATE__;
  const char *t = __TIME__;
  struct tm tm;
  memset(&tm, 0, sizeof(tm));
  for (int i = 0; i < 12; i++) {
    if (memcmp(d, months + i * 3, 3) == 0) { tm.tm_mon = i; break; }
  }
  tm.tm_mday = atoi(d + 4);
  tm.tm_year = atoi(d + 7) - 1900;
  tm.tm_hour = atoi(t);
  tm.tm_min  = atoi(t + 3);
  tm.tm_sec  = atoi(t + 6);
  char *prevTz = getenv("TZ");
  String saved = prevTz ? String(prevTz) : String();
  setenv("TZ", "UTC0", 1);
  tzset();
  time_t r = mktime(&tm);
  if (saved.length()) setenv("TZ", saved.c_str(), 1); else unsetenv("TZ");
  tzset();
  return r;
}

// Plain HTTP. TLS isn't viable while clock is unset (some stacks reject
// handshake on bad clock), and carriers that block NTP often pass HTTP/80.
// 301/302 redirects still carry a Date header — that's all we need.
inline bool fetchHttpsDate(const char *host, time_t &out) {
  WiFiClient client;
  client.setTimeout(5);
  if (!client.connect(host, 80)) {
    Serial.printf("[time] HTTP-Date connect failed: %s\n", host);
    return false;
  }
  size_t sent = client.printf("HEAD / HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n", host);
  client.flush();
  Serial.printf("[time] connected, sent=%u bytes, waiting for response\n", (unsigned)sent);

  unsigned long deadline = millis() + 5000;
  while ((client.connected() || client.available()) && millis() < deadline) {
    String line = client.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;
    Serial.printf("[time] hdr: %s\n", line.c_str());
    if (line.length() > 5 && (line.startsWith("Date:") || line.startsWith("date:"))) {
      String dstr = line.substring(5);
      dstr.trim();
      struct tm tm;
      memset(&tm, 0, sizeof(tm));
      if (strptime(dstr.c_str(), "%a, %d %b %Y %H:%M:%S GMT", &tm) == nullptr) {
        Serial.printf("[time] HTTPS-Date parse failed: '%s'\n", dstr.c_str());
        client.stop();
        return false;
      }
      // mktime interprets struct tm as local; force UTC for this call.
      char *prevTz = getenv("TZ");
      String saved = prevTz ? String(prevTz) : String();
      setenv("TZ", "UTC0", 1);
      tzset();
      time_t t = mktime(&tm);
      if (saved.length()) setenv("TZ", saved.c_str(), 1); else unsetenv("TZ");
      tzset();
      client.stop();
      if (t < 1700000000L) return false;
      out = t;
      return true;
    }
  }
  client.stop();
  Serial.println("[time] HTTPS-Date: no Date header before timeout");
  return false;
}
