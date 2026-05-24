#pragma once
// logSink.h — ESP-IDF log fan-out (ADR-010, TASK-016a).
//
// Installs an esp_log_set_vprintf hook that mirrors every ESP_LOGx line to
// (a) Serial (preserves the original output) and (b) a 12 KB RAM ringbuffer
// of fixed-size line slots. Lines longer than RING_LINE_MAX are truncated with
// a one-time WARN.
//
// Plain `Serial.println` from existing code does NOT pass through here —
// migration is incremental per ADR-010. System tags (mbedtls, ssl_client,
// HTTPClient, lwip, wifi) flow through esp_log and so do hit the ring.

#include <Arduino.h>
#include <esp_log.h>
#include <freertos/FreeRTOS.h>

namespace logsink {

constexpr int RING_LINE_MAX   = 256;   // chars per slot incl. null terminator
constexpr int RING_LINE_COUNT = 48;    // 48 * 256 = 12288 bytes ≈ 12 KB

struct Slot { uint16_t len; char data[RING_LINE_MAX]; };

extern Slot       g_lines[RING_LINE_COUNT];
extern uint16_t   g_head;
extern uint16_t   g_count;
extern bool       g_truncationWarned;
extern portMUX_TYPE g_mux;

inline void ringPush(const char *src, size_t len) {
  if (len == 0) return;
  if (len >= RING_LINE_MAX) len = RING_LINE_MAX - 1;
  portENTER_CRITICAL_SAFE(&g_mux);
  Slot *slot = &g_lines[g_head];
  memcpy(slot->data, src, len);
  slot->data[len] = 0;
  slot->len = (uint16_t)len;
  g_head = (g_head + 1) % RING_LINE_COUNT;
  if (g_count < RING_LINE_COUNT) g_count++;
  portEXIT_CRITICAL_SAFE(&g_mux);
}

inline void ringClear() {
  portENTER_CRITICAL_SAFE(&g_mux);
  g_head = 0;
  g_count = 0;
  portEXIT_CRITICAL_SAFE(&g_mux);
}

// Walks the ring oldest-first, emitting up to `n` most-recent lines via
// `emit(buf, len)`. Each call to emit() receives a single line (may or may
// not end with newline; caller appends one if needed).
template <typename Emit>
inline void ringForEachLast(int n, Emit emit) {
  if (n <= 0) return;
  uint16_t snap_head, snap_count;
  portENTER_CRITICAL_SAFE(&g_mux);
  snap_head = g_head;
  snap_count = g_count;
  portEXIT_CRITICAL_SAFE(&g_mux);
  if (n > snap_count) n = snap_count;
  uint16_t start = (snap_head + RING_LINE_COUNT - n) % RING_LINE_COUNT;
  for (int i = 0; i < n; ++i) {
    uint16_t idx = (start + i) % RING_LINE_COUNT;
    char tmp[RING_LINE_MAX];
    uint16_t len;
    portENTER_CRITICAL_SAFE(&g_mux);
    len = g_lines[idx].len;
    memcpy(tmp, g_lines[idx].data, len);
    tmp[len] = 0;
    portEXIT_CRITICAL_SAFE(&g_mux);
    emit(tmp, (size_t)len);
  }
}

inline int vprintfHook(const char *fmt, va_list args) {
  char line[RING_LINE_MAX];
  int n = vsnprintf(line, sizeof(line), fmt, args);
  if (n < 0) return n;
  bool truncated = (n >= (int)sizeof(line));
  size_t len = truncated ? sizeof(line) - 1 : (size_t)n;

  // Mirror to Serial — preserves what would have appeared without our hook.
  Serial.write((const uint8_t *)line, len);

  ringPush(line, len);

  if (truncated && !g_truncationWarned) {
    g_truncationWarned = true;
    const char msg[] = "[log] WARN: ringbuffer line truncated (cap=256)\n";
    Serial.write((const uint8_t *)msg, sizeof(msg) - 1);
    ringPush(msg, sizeof(msg) - 1);
  }
  return n;
}

// Direct-to-ring logging macros (TASK-018b-bis, 2026-05-07).
// Arduino-ESP32 redefines ESP_LOGx to use its own log_x macros that go
// through printf, NOT esp_log_writev — so our vprintfHook sees almost
// nothing from our own code. These LOG_x macros bypass that mess: format
// once, write to Serial, push to the ring. ADR-010 amendment 4.
inline void logLine(const char *level, const char *tag, const char *fmt, ...)
    __attribute__((format(printf, 3, 4)));

inline void logLine(const char *level, const char *tag, const char *fmt, ...) {
  char buf[RING_LINE_MAX];
  int prefix = snprintf(buf, sizeof(buf), "[%s][%s] ", level, tag);
  if (prefix < 0 || prefix >= (int)sizeof(buf)) return;
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf + prefix, sizeof(buf) - prefix, fmt, ap);
  va_end(ap);
  size_t total = (size_t)prefix + (n < 0 ? 0 : (size_t)n);
  if (total >= sizeof(buf)) total = sizeof(buf) - 1;
  Serial.write((const uint8_t *)buf, total);
  if (total == 0 || buf[total - 1] != '\n') Serial.write((uint8_t)'\n');
  ringPush(buf, total);
}

#define LOG_E(tag, ...) ::logsink::logLine("E", tag, __VA_ARGS__)
#define LOG_W(tag, ...) ::logsink::logLine("W", tag, __VA_ARGS__)
#define LOG_I(tag, ...) ::logsink::logLine("I", tag, __VA_ARGS__)
#define LOG_D(tag, ...) ::logsink::logLine("D", tag, __VA_ARGS__)

inline void begin() {
  esp_log_set_vprintf(&vprintfHook);

  // Defaults per ADR-010 amendment: INFO baseline; DEBUG for active
  // subsystems; WARN for vendored tags whose noise we don't want.
  esp_log_level_set("*",          ESP_LOG_INFO);
  esp_log_level_set("display",    ESP_LOG_DEBUG);
  esp_log_level_set("spotify",    ESP_LOG_DEBUG);
  esp_log_level_set("time",       ESP_LOG_DEBUG);
  esp_log_level_set("HTTPClient", ESP_LOG_WARN);
  esp_log_level_set("WiFiClient", ESP_LOG_WARN);
  esp_log_level_set("ssl_client", ESP_LOG_WARN);
  esp_log_level_set("mbedtls",    ESP_LOG_WARN);

  // esp_log_level_set is exact-tag, not prefix — subtags inherit nothing
  // from their parent. Register each dotted subtag explicitly here. Adding
  // a new ESP_LOGD("foo.bar", ...) site? Add the matching set call below.
  // (ADR-010 amendment 2026-05-07.)
  esp_log_level_set("spotify.poll", ESP_LOG_DEBUG);
  esp_log_level_set("spotify.tls",  ESP_LOG_DEBUG);
  esp_log_level_set("display.skin", ESP_LOG_DEBUG);
  esp_log_level_set("time.ntp",     ESP_LOG_DEBUG);
  esp_log_level_set("time.https",   ESP_LOG_DEBUG);

  ESP_LOGI("log", "log sink up — ring=%d slots × %d B = %d B; build %s %s",
           RING_LINE_COUNT, RING_LINE_MAX, RING_LINE_COUNT * RING_LINE_MAX, __DATE__, __TIME__);
}

}  // namespace logsink
