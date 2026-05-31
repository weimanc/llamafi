#pragma once
// logDecode.h — decoder helpers for mbedTLS / HTTP error codes
// (ADR-010, TASK-016c).
//
// Use at log call sites to turn opaque numbers into searchable strings:
//
//   ESP_LOGE("spotify.tls", "tls fail rc=%s", tlsErr(rc));
//   ESP_LOGW("spotify",     "poll http=%s",   httpErr(code));
//
// Returned pointers are either static literals (for known codes) or a
// static per-thread fallback buffer (for unknown codes). Not reentrant
// across consecutive calls within a single log line — snprintf into a
// local if you need both decoded in one printf.

#include <Arduino.h>

inline const char *tlsErr(int rc) {
  switch (rc) {
    // Codes seen on this DUT (Arduino-ESP32 ssl_client + mbedtls 2.x).
    case  0x0050: return "0x0050 NET_CONN_RESET";
    case  0x004C: return "0x004C NET_RECV_FAILED";
    case -76:     return "-76 (0x4C) NET_RECV_FAILED";
    case -80:     return "-80 (0x50) NET_CONN_RESET";
    case -9984:   return "-9984 (-0x2700) X509_CERT_VERIFY_FAILED";
    case -29312:  return "-29312 (-0x7280) SSL_CONN_EOF";
    case -29184:  return "-29184 (-0x7200) SSL_FATAL_ALERT_MESSAGE";
    case -30592:  return "-30592 (-0x7780) SSL_PEER_CLOSE_NOTIFY";
    case -32256:  return "-32256 (-0x7E00) SSL_HANDSHAKE_FAILURE";
    default: {
      static char buf[32];
      snprintf(buf, sizeof(buf), "%d (0x%04X) ?", rc, (unsigned)(rc & 0xFFFF));
      return buf;
    }
  }
}

// ArduinoJson DeserializationError mapped to -90 - err.code() (stock fetches).
// Enum order: Ok=0 EmptyInput=1 IncompleteInput=2 InvalidInput=3 NoMemory=4 TooDeep=5
inline const char *stockJsonErr(int code) {
  switch (code) {
    case -91: return "-91 JSON_EMPTY_INPUT";
    case -92: return "-92 JSON_INCOMPLETE (stream cut)";
    case -93: return "-93 JSON_INVALID (format changed?)";
    case -94: return "-94 JSON_NO_MEMORY (doc too small)";
    case -95: return "-95 JSON_TOO_DEEP";
    default: {
      static char buf[24];
      snprintf(buf, sizeof(buf), "%d JSON_?", code);
      return buf;
    }
  }
}

inline const char *httpErr(int code) {
  switch (code) {
    case 200: return "200 OK";
    case 204: return "204 No Content";
    case 301: return "301 Moved";
    case 302: return "302 Found";
    case 304: return "304 Not Modified";
    case 400: return "400 Bad Request";
    case 401: return "401 Unauthorized";
    case 403: return "403 Forbidden";
    case 404: return "404 Not Found";
    case 429: return "429 Too Many Requests";
    case 500: return "500 Server Error";
    case 502: return "502 Bad Gateway";
    case 503: return "503 Service Unavailable";
    case 504: return "504 Gateway Timeout";
    default: {
      static char buf[24];
      snprintf(buf, sizeof(buf), "HTTP %d", code);
      return buf;
    }
  }
}
