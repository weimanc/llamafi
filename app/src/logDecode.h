#pragma once
// logDecode.h — decoder helpers for mbedTLS / HTTP error codes
// (ADR-010, TASK-016c).
//
// Use at log call sites to turn opaque numbers into searchable strings:
//
//   ESP_LOGE("spotify.tls", "tls fail rc=%s", tlsErr(rc));
//   ESP_LOGW("spotify",     "poll http=%s",   httpErr(code));
//   LOG_W("dataTask.stock", "fetch err=%s",   stockErr(code));
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

inline const char *httpErr(int code) {
  switch (code) {
    // HTTPClient internal errors (negative codes from http.GET())
    case  -1: return "-1 HTTPC_CONNECTION_REFUSED";
    case  -2: return "-2 HTTPC_SEND_HEADER_FAILED";
    case  -3: return "-3 HTTPC_SEND_PAYLOAD_FAILED";
    case  -4: return "-4 HTTPC_NOT_CONNECTED";
    case  -5: return "-5 HTTPC_CONNECTION_LOST";
    case  -6: return "-6 HTTPC_NO_STREAM";
    case  -7: return "-7 HTTPC_NO_HTTP_SERVER";
    case  -8: return "-8 HTTPC_TOO_LESS_RAM";
    case  -9: return "-9 HTTPC_ENCODING";
    case -10: return "-10 HTTPC_STREAM_WRITE";
    case -11: return "-11 HTTPC_READ_TIMEOUT";
    // Our sentinel: http.begin() returned false (URL/TLS setup failure)
    case -100: return "-100 HTTP_BEGIN_FAILED";
    // HTTP status codes
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

// Stock fetch error decoder. Error code ranges:
//   -1..-11  HTTPClient internal (see httpErr())
//   -91..-95 ArduinoJson DeserializationError (-90 - err.code())
//   -100     http.begin() returned false (URL/TLS setup failure)
//   HTTP 4xx/5xx passed through as-is
inline const char *stockErr(int code) {
  switch (code) {
    case -91: return "-91 JSON_EMPTY_INPUT";
    case -92: return "-92 JSON_INCOMPLETE (stream cut)";
    case -93: return "-93 JSON_INVALID (format changed?)";
    case -94: return "-94 JSON_NO_MEMORY (doc too small)";
    case -95: return "-95 JSON_TOO_DEEP";
    default:  return httpErr(code);
  }
}
