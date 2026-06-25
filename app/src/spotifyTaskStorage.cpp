// Storage TU for spotifyTask globals + the task body (kept here so the
// header stays light and the task implementation is in one place).
//
// TASK-031a: skeleton only.
// TASK-031b: getCurrentlyPlaying lives here now. Task owns backoff +
// the SpotifyArduino instance. Snapshot is written on every successful
// poll under the spinlock; loop side reads via copySnapshot().

#include "spotifyTask.h"

#include <WiFiClientSecure.h>
#include <freertos/semphr.h>

#include "logSink.h"
#include "logDecode.h"
#include "logHeartbeat.h"
#include "perf.h"

extern WiFiClientSecure client;
extern long             songStartMillis;  // spotifyLogic.h global
extern long             songDuration;     // spotifyLogic.h global

#ifndef SPOTIFY_MARKET
#define SPOTIFY_MARKET ""
#endif

namespace spotifyTask {

QueueHandle_t reqQueue       = nullptr;
Snapshot      g_snapshot     = {};
portMUX_TYPE  g_snapshotMux  = portMUX_INITIALIZER_UNLOCKED;
QueueSnapshot g_queueSnapshot = {};
portMUX_TYPE  g_queueMux      = portMUX_INITIALIZER_UNLOCKED;
TaskHandle_t  g_taskHandle   = nullptr;

static SpotifyArduino *s_spotify = nullptr;

constexpr UBaseType_t kStackBytes  = 10 * 1024;   // mbedtls handshake ~6-8 KB
constexpr UBaseType_t kPriority    = 1;           // above idle, below tcpip
constexpr BaseType_t  kPinnedCpu   = APP_CPU_NUM; // core 1; same as Arduino loop

constexpr uint32_t kPollPeriodMs   = 5000;        // base cadence — backoff multiplies
constexpr uint32_t kBackoffMaxMs   = 60000;       // matches ADR-011

// Task-private state — never accessed from the loop.
static char s_lastTrackUri[200]        = {0};
static char s_lastTrackContextUri[200] = {0};
// TASK-116b: true while ≥1 user action is in-flight. Set by enqueue() for
// non-POLL actions; cleared when xQueueReceive returns pdFALSE (queue empty).
static volatile bool s_actionPending = false;
// TASK-056f: volatile matches s_resetTlsPending pattern — single aligned
// 32-bit store from the loop task (dbg_set "backoff") is atomic on Xtensa.
static volatile unsigned int s_consecutiveFailures = 0;
// TASK-245: last poll HTTP status (set in doPoll). Read by authError() to
// drive the red taskbar error bar. Single aligned 32-bit store, atomic on Xtensa.
static volatile int s_lastHttpStatus = 0;
// TASK-053b: pending TLS reset flag. Set by resetTls() (loop task); read
// and cleared at the top of each taskBody iteration (spotify task). The
// volatile ensures the compiler does not hoist the check out of the loop.
// A single bool write is atomic on ESP32 Xtensa (aligned word store).
static volatile bool s_resetTlsPending = false;

#ifdef SERIAL_DEBUG
// ADR-042 E2: background poll inhibit. 1 = normal, 0 = suspended.
// Set/cleared by dbg_set("bgPoll", ...). Reset to 1 by resetTls() (recovery invariant).
static volatile uint8_t s_bgPollEnabled = 1;
#endif

// TASK-131: TLS yield — dataTask requests Spotify TLS stop so it can
// allocate its own session from the freed heap. s_tlsYieldReq is set
// by tlsYield(); taskBody calls client.stop() then gives the semaphore
// and spins until tlsResume() clears the flag.
static volatile bool     s_tlsYieldReq = false;
static SemaphoreHandle_t s_tlsYieldedSem = nullptr;

// TASK-058: poll timing — read by loop-task getters (aligned 32-bit reads; atomic on Xtensa).
static volatile uint32_t s_lastSuccessfulPollMs = 0;  // millis() of last 200 or 204
static volatile uint32_t s_lastPollFinishedMs   = 0;  // millis() after every doPoll() return

// Queue fetch state (ADR-017 / TASK-020b).
static bool     s_queueRefreshNeeded = true;  // true on startup to prime the panel
static uint32_t s_lastQueueFetchMs   = 0;
constexpr uint32_t kQueueKeepaliveMs = 60000;

// Snapshot writer — runs as the SpotifyArduino getCurrentlyPlaying
// callback on the spotify task's stack. Updates the interpolation
// anchors (atomic int32 globals) and copies track metadata into the
// snapshot buffer under the spinlock.
static void onCurrentlyPlaying(CurrentlyPlaying cp) {
  if (cp.trackUri == NULL) return;

  const bool trackChanged = (strcmp(s_lastTrackUri, cp.trackUri) != 0);
  if (trackChanged) {
    s_queueRefreshNeeded = true;  // new track → queue order may have changed
    strncpy(s_lastTrackUri, cp.trackUri, sizeof(s_lastTrackUri) - 1);
    s_lastTrackUri[sizeof(s_lastTrackUri) - 1] = 0;
    if (cp.contextUri) {
      strncpy(s_lastTrackContextUri, cp.contextUri, sizeof(s_lastTrackContextUri) - 1);
      s_lastTrackContextUri[sizeof(s_lastTrackContextUri) - 1] = 0;
    } else {
      s_lastTrackContextUri[0] = 0;
    }
  }

  // Atomic int32 writes — read by the loop's updateProgressBar.
  if (cp.isPlaying) {
    songStartMillis = millis() - cp.progressMs;
    songDuration    = cp.durationMs;
  } else {
    songStartMillis = 0;
    songDuration    = cp.durationMs;
  }

  portENTER_CRITICAL_SAFE(&g_snapshotMux);
  g_snapshot.seq++;
  g_snapshot.capturedAtMs = millis();
  g_snapshot.valid        = true;
  g_snapshot.isPlaying    = cp.isPlaying;
  g_snapshot.progressMs   = cp.progressMs;
  g_snapshot.durationMs   = cp.durationMs;
  g_snapshot.playingType  = (uint8_t)cp.currentlyPlayingType;
  // TASK-041: clamp lib int → snapshot int8_t. cp.volumePercent is
  // already -1 for "no device" (TASK-039 patch); 0..100 otherwise.
  g_snapshot.volumePercent = (int8_t)cp.volumePercent;
  // chrome-001 final: shuffle + repeat from the same response.
  g_snapshot.shuffleState  = cp.shuffleState;
  g_snapshot.repeatState   = (int8_t)cp.repeatState;
  strncpy(g_snapshot.trackUri,   cp.trackUri                    ? cp.trackUri                    : "", sizeof(g_snapshot.trackUri)   - 1);
  strncpy(g_snapshot.trackName,  cp.trackName                   ? cp.trackName                   : "", sizeof(g_snapshot.trackName)  - 1);
  strncpy(g_snapshot.albumName,  cp.albumName                   ? cp.albumName                   : "", sizeof(g_snapshot.albumName)  - 1);
  strncpy(g_snapshot.contextUri, cp.contextUri                  ? cp.contextUri                  : "", sizeof(g_snapshot.contextUri) - 1);
  if (cp.numArtists > 0 && cp.artists[0].artistName) {
    strncpy(g_snapshot.artistName, cp.artists[0].artistName, sizeof(g_snapshot.artistName) - 1);
  } else {
    g_snapshot.artistName[0] = 0;
  }
  g_snapshot.trackUri  [sizeof(g_snapshot.trackUri)   - 1] = 0;
  g_snapshot.trackName [sizeof(g_snapshot.trackName)  - 1] = 0;
  g_snapshot.albumName [sizeof(g_snapshot.albumName)  - 1] = 0;
  g_snapshot.contextUri[sizeof(g_snapshot.contextUri) - 1] = 0;
  g_snapshot.artistName[sizeof(g_snapshot.artistName) - 1] = 0;
  g_snapshot.deviceActive = (g_snapshot.volumePercent != -1);
  portEXIT_CRITICAL_SAFE(&g_snapshotMux);
}

// Computes the next xQueueReceive timeout from the current backoff
// state. Resets to the base period after a success.
static uint32_t nextWaitMs() {
  unsigned int shift = s_consecutiveFailures > 6 ? 6 : s_consecutiveFailures;
  uint32_t interval = kPollPeriodMs << shift;
  if (interval > kBackoffMaxMs) interval = kBackoffMaxMs;
  return interval;
}

// Called by getQueue() with parsed queue data. Copies into g_queueSnapshot
// under the spinlock. const char* fields are ArduinoJson-owned; must copy.
static void onQueue(QueueData &qd) {
  portENTER_CRITICAL_SAFE(&g_queueMux);
  g_queueSnapshot.count = 0;
  uint8_t n = qd.count < QUEUE_MAX ? qd.count : QUEUE_MAX;
  for (uint8_t i = 0; i < n; i++) {
    strncpy(g_queueSnapshot.items[i].name,   qd.items[i].name       ? qd.items[i].name       : "", sizeof(QueueEntry::name)   - 1);
    strncpy(g_queueSnapshot.items[i].artist, qd.items[i].artistName ? qd.items[i].artistName : "", sizeof(QueueEntry::artist) - 1);
    strncpy(g_queueSnapshot.items[i].uri,    qd.items[i].uri        ? qd.items[i].uri        : "", sizeof(QueueEntry::uri)    - 1);
    g_queueSnapshot.items[i].name  [sizeof(QueueEntry::name)   - 1] = 0;
    g_queueSnapshot.items[i].artist[sizeof(QueueEntry::artist) - 1] = 0;
    g_queueSnapshot.items[i].uri   [sizeof(QueueEntry::uri)    - 1] = 0;
    g_queueSnapshot.items[i].durationMs = (uint32_t)qd.items[i].durationMs;
    g_queueSnapshot.count++;
  }
  g_queueSnapshot.seqno++;
  portEXIT_CRITICAL_SAFE(&g_queueMux);
  LOG_D("spotify.queue", "snapshot updated: count=%u seqno=%lu",
        (unsigned)g_queueSnapshot.count, (unsigned long)g_queueSnapshot.seqno);
}

// Fetches the play queue and updates g_queueSnapshot. Resets the refresh
// flag and keepalive timer regardless of outcome (avoid retry storms).
static void doFetchQueue() {
  if (!s_spotify) return;
  LOG_D("spotify.queue", "GET /v1/me/player/queue");
  unsigned long t0 = millis();
  int status = s_spotify->getQueue(onQueue);
  LOG_D("spotify.queue", "status=%d elapsed=%lums", status, (unsigned long)(millis() - t0));
  s_queueRefreshNeeded = false;
  s_lastQueueFetchMs   = millis();
  if (status < 0) client.stop();  // prevent fd leak: same reason as doPoll
}

// Issues a single poll. Updates backoff + heartbeat counters + (on
// success) the snapshot via the onCurrentlyPlaying callback.
static void doPoll() {
  if (!s_spotify) return;
  LOG_D("spotify.poll", "GET /v1/me/player/currently-playing");
  unsigned long t0 = millis();
  int status = s_spotify->getCurrentlyPlaying(onCurrentlyPlaying, SPOTIFY_MARKET);
  unsigned long elapsed = millis() - t0;
  heartbeat::recordPoll(status == 200 || status == 204, status);
  heartbeat::recordBlock(elapsed);
  s_lastHttpStatus = status;   // TASK-245: feed authError()

  if (status == 200) {
    s_consecutiveFailures = 0;
    s_lastSuccessfulPollMs = millis();
    LOG_D("spotify.poll", "ok %s", httpErr(status));
  } else if (status == 204) {
    s_consecutiveFailures = 0;
    s_lastSuccessfulPollMs = millis();
    songStartMillis = 0;       // 204 no track — disable interpolator
    LOG_D("spotify.poll", "204 no track");
    // TASK-043: 204 means no active device. Reset volumePercent to the -1
    // sentinel and bump seq so updateCurrentlyPlaying's dedup gate fires
    // and the chrome-001 VOLUME slider returns to KEYFRAME_NONE. The 200
    // path's snapshot writer (onCurrentlyPlaying) doesn't run on 204;
    // without this, the slider would be stuck at the last seen volume
    // until the next 200 reanimates a device.
    portENTER_CRITICAL_SAFE(&g_snapshotMux);
    g_snapshot.seq++;
    g_snapshot.capturedAtMs = millis();
    g_snapshot.volumePercent = -1;
    g_snapshot.deviceActive  = false;
    portEXIT_CRITICAL_SAFE(&g_snapshotMux);
  } else {
    s_consecutiveFailures++;
    LOG_W("spotify.poll", "fail http=%s", httpErr(status));
    if (status == -1) {
      char errbuf[80] = {0};
      int rc = client.lastError(errbuf, sizeof(errbuf));
      if (rc < 0) {
        LOG_W("spotify.tls", "after -1: rc=%s errstr='%s'", tlsErr(rc), errbuf);
      } else if (rc > 0) {
        LOG_W("spotify.tls", "after -1: stale connect fd=%d (no current tls error)", rc);
      } else {
        LOG_W("spotify.tls", "after -1: lastError=0 — see [lib] line for cause");
      }
      // Close the stale socket so the next reconnect starts fresh; without
      // this, start_ssl_client() leaks the old fd and errno=11 accumulates.
      client.stop();
    }
  }
  if (s_consecutiveFailures > 0) {
    LOG_D("spotify.poll", "backoff: consecutive=%u next=%lums",
          s_consecutiveFailures, (unsigned long)nextWaitMs());
  }
  s_lastPollFinishedMs = millis();
}

const char *actionName(uint8_t a) {
  switch (a) {
    case ACT_POLL:       return "POLL";
    case ACT_FORCE_POLL: return "FORCE_POLL";
    case ACT_NEXT:       return "NEXT";
    case ACT_PREV:       return "PREV";
    case ACT_PLAY:       return "PLAY";
    case ACT_PAUSE:      return "PAUSE";
    case ACT_SEEK:       return "SEEK";
    case ACT_VOLUME:     return "VOLUME";
    case ACT_SHUFFLE:    return "SHUFFLE";
    case ACT_REPEAT:     return "REPEAT";
    case ACT_PLAY_URI:   return "PLAY_URI";
    default:             return "?";
  }
}

// ---- task body --------------------------------------------------------------

static void taskBody(void *) {
  LOG_I("spotify.task", "task started; pinned core=%d stack=%uB period=%ums",
        (int)kPinnedCpu, (unsigned)kStackBytes, (unsigned)kPollPeriodMs);
  // Cap SO_RCVTIMEO (per-recv) to 15 s and TLS handshake timeout to 30 s.
  // Without these, the default 120 s handshake timeout means a single
  // stalled connect can block for 240 s (two attempts). With 15 s recv
  // and 30 s handshake, worst-case per API call is 75 s (30 s handshake +
  // 15 s recv × 2 attempts); two API calls cap at 150 s — within tlsYield().
  client.setTimeout(15);
  client.setHandshakeTimeout(30);
  // Clear any stale socket left by setup()'s failed auth attempt so the
  // first getCurrentlyPlaying() starts with a clean client.
  client.stop();

  for (;;) {
    // TASK-053b: hard TLS reset requested by loop task (logo tap or serial
    // "reconnect"). Execute here on our own stack so mbedTLS is only ever
    // touched from this task. Clear before the next xQueueReceive so the
    // recovery poll fires immediately at base cadence.
    if (s_resetTlsPending) {
      s_resetTlsPending = false;
      LOG_I("spotify.tls", "hard reset — stopping client");
      client.stop();
    }

    Request req;
    uint32_t waitMs = nextWaitMs();
    BaseType_t got = xQueueReceive(reqQueue, &req, pdMS_TO_TICKS(waitMs));

    if (got == pdFALSE) {
      s_actionPending = false;     // queue drained — no user actions in flight
#ifdef SERIAL_DEBUG
      if (!s_bgPollEnabled) continue;  // bgPoll suspended — skip cadence poll
#endif
      req.action = ACT_POLL;       // self-issue cadence poll
      req.param  = 0;
    } else {
      LOG_D("spotify.task", "dequeued action=%s param=%ld",
            actionName(req.action), (long)req.param);
    }

    // TASK-131: TLS yield — stop Spotify TLS so dataTask can reuse the client
    // for its own fetch (shared-client approach avoids double-TLS-context OOM).
    // Runs after xQueueReceive so any in-flight API call has already completed.
    // Spins (20 ms ticks) until tlsResume() clears the flag; discards the
    // current queued request (the wake-up ACT_POLL) via continue.
    if (s_tlsYieldReq) {
      client.stop();
      LOG_I("spotify.tls", "tls yield — client stopped");
      if (s_tlsYieldedSem) xSemaphoreGive(s_tlsYieldedSem);
      while (s_tlsYieldReq) vTaskDelay(pdMS_TO_TICKS(20));
      LOG_I("spotify.tls", "tls yield — resumed");
      continue;
    }

    switch (req.action) {
      case ACT_POLL:
      case ACT_FORCE_POLL:
        doPoll();
        break;
      case ACT_NEXT:
        LOG_D("spotify.task", "nextTrack");
        s_spotify->nextTrack();
        // Force a fresh poll right after — picks up the new track sooner
        // than the natural cadence would.
        doPoll();
        break;
      case ACT_PREV:
        LOG_D("spotify.task", "previousTrack");
        s_spotify->previousTrack();
        doPoll();
        break;
      case ACT_PLAY:
        LOG_D("spotify.task", "play");
        s_spotify->play();
        doPoll();
        break;
      case ACT_PAUSE:
        LOG_D("spotify.task", "pause");
        s_spotify->pause();
        doPoll();
        break;
      case ACT_SEEK:
        LOG_D("spotify.task", "seek %ld ms", (long)req.param);
        s_spotify->seek((int)req.param);
        // Don't force-poll on seek — the optimistic-UI re-anchor in the
        // touch handler already updated songStartMillis. A poll right
        // after seek often returns the pre-seek progress (Spotify hasn't
        // committed yet) and would visually snap back. Let the natural
        // cadence pick it up.
        break;
      case ACT_VOLUME:
        LOG_D("spotify.task", "setVolume %ld%%", (long)req.param);
        s_spotify->setVolume((int)req.param);
        // ADR-016 §9 — no doPoll() after. Drag-burst guard: drag fires
        // many ACT_VOLUMEs; each doPoll would burst the network and
        // race the optimistic-UI freeze (ADR-016 §10). Next regular
        // poll re-syncs naturally within 5-10 s.
        break;
      case ACT_SHUFFLE:
        LOG_D("spotify.task", "toggleShuffle %s", req.param ? "on" : "off");
        s_spotify->toggleShuffle(req.param != 0);
        doPoll();
        break;
      case ACT_REPEAT:
        LOG_D("spotify.task", "setRepeatMode %ld", (long)req.param);
        s_spotify->setRepeatMode((RepeatOptions)req.param);
        doPoll();
        break;
      case ACT_PLAY_URI: {
        int idx = (int)req.param;
        char uri[64] = {0};
        portENTER_CRITICAL_SAFE(&g_queueMux);
        if (idx >= 0 && idx < (int)g_queueSnapshot.count) {
          strlcpy(uri, g_queueSnapshot.items[idx].uri, sizeof(uri));
        }
        portEXIT_CRITICAL_SAFE(&g_queueMux);
        if (uri[0]) {
          char body[300];
          if (s_lastTrackContextUri[0]) {
            // Playlist/album context: jump to track within context, preserving queue.
            snprintf(body, sizeof(body),
                     "{\"context_uri\":\"%s\",\"offset\":{\"uri\":\"%s\"}}",
                     s_lastTrackContextUri, uri);
          } else {
            // No context (ad-hoc/radio): fall back to single-URI play.
            snprintf(body, sizeof(body), "{\"uris\":[\"%s\"]}", uri);
          }
          LOG_D("spotify.task", "playAdvanced ctx=%s uri=%s",
                s_lastTrackContextUri[0] ? s_lastTrackContextUri : "(none)", uri);
          s_spotify->playAdvanced(body);
          doPoll();
        }
        break;
      }
      default:
        break;
    }

    // Queue fetch — after every poll action, if track changed or keepalive due.
    if (s_queueRefreshNeeded ||
        (millis() - s_lastQueueFetchMs) >= kQueueKeepaliveMs) {
      doFetchQueue();
    }

    // Health: stack hwm of THIS task once a minute.
    static uint32_t stackTickCount = 0;
    if ((++stackTickCount % 12) == 0) {
      uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t);
      LOG_D("spotify.task", "stack_hwm=%uB", (unsigned)hwm);
    }
  }
}

// ---- public API -------------------------------------------------------------

void begin(SpotifyArduino *spotifyObj) {
  if (g_taskHandle != nullptr) {
    LOG_W("spotify.task", "begin() called twice — ignoring");
    return;
  }
  s_spotify = spotifyObj;

  s_tlsYieldedSem = xSemaphoreCreateBinary();
  reqQueue = xQueueCreate(8, sizeof(Request));
  if (reqQueue == nullptr) {
    LOG_E("spotify.task", "xQueueCreate failed — task NOT started");
    return;
  }

  BaseType_t rc = xTaskCreatePinnedToCore(
      &taskBody, "spotifyTask",
      kStackBytes / sizeof(StackType_t),
      nullptr, kPriority, &g_taskHandle, kPinnedCpu);
  if (rc != pdPASS) {
    LOG_E("spotify.task", "xTaskCreatePinnedToCore failed rc=%d", (int)rc);
    g_taskHandle = nullptr;
    return;
  }
  LOG_I("spotify.task", "begin ok — handle=%p", (void *)g_taskHandle);
}

void resetBackoff() {
  s_consecutiveFailures = 0;
}

// TASK-240: stack instrumentation (uxTaskGetStackHighWaterMark returns words).
size_t stackHighWaterBytes() {
  return g_taskHandle ? (size_t)uxTaskGetStackHighWaterMark(g_taskHandle) * sizeof(StackType_t) : 0;
}
size_t stackSizeBytes() { return (size_t)kStackBytes; }

uint32_t lastSuccessfulPollAgeMs() {
  uint32_t t = s_lastSuccessfulPollMs;
  return (t == 0) ? 0 : (uint32_t)(millis() - t);
}

uint32_t nextPollInMs() {
  uint32_t wait = nextWaitMs();
  uint32_t fin  = s_lastPollFinishedMs;
  if (fin == 0) return wait;
  uint32_t elapsed = (uint32_t)(millis() - fin);
  return (elapsed >= wait) ? 0 : wait - elapsed;
}

bool isHealthy() {
  return s_consecutiveFailures < 2;
}

// TASK-245 / ADR-046: true when the poll is in a persistent 403 state —
// authorization refused (e.g. owner-account Premium lapsed, TASK-243). The
// >=2 consecutive-failure guard ignores a one-off 403 so the red bar doesn't
// flash on a transient blip. Self-clears: the next 200/204 resets
// s_consecutiveFailures to 0. Surfaced via SpotifyApp::hasError().
bool authError() {
  return s_lastHttpStatus == 403 && s_consecutiveFailures >= 2;
}

// TASK-245 amendment / ADR-046: true until the *first* successful poll (200/204).
// Drives the amber "connecting" taskbar state at boot, so the bar reads amber
// (working) rather than green (all-good) before we know the connection state.
// Latches false on the first success and stays false (subsequent failures show
// red via authError(), recoveries show green — never amber-connecting again).
bool connecting() {
  return s_lastSuccessfulPollMs == 0;
}

void resetTls() {
  s_consecutiveFailures = 0;
  s_resetTlsPending = true;
#ifdef SERIAL_DEBUG
  s_bgPollEnabled = 1;  // ADR-042: reconnect always restores full operational state
#endif
}

void tlsYield() {
  if (!s_tlsYieldedSem || !reqQueue) return;
  // Drain any orphaned give from a previous timed-out yield (avoids the race
  // where the semaphore is already available from a prior cycle, making the
  // next xSemaphoreTake return immediately before spotifyTask actually stops).
  xSemaphoreTake(s_tlsYieldedSem, 0);
  s_tlsYieldReq = true;
  // Wake the task if it is blocked in xQueueReceive
  Request r{ACT_POLL, 0};
  xQueueSendToFront(reqQueue, &r, 0);
  // Wait for task ack (up to 150 s — covers worst-case 2 API calls × 75 s
  // each = 150 s, with 30 s handshake + 15 s recv × 2 per call).
  xSemaphoreTake(s_tlsYieldedSem, pdMS_TO_TICKS(150000));
}

void tlsResume() {
  s_tlsYieldReq = false;
}

bool enqueue(Action a, int32_t param) {
  if (reqQueue == nullptr) return false;
  Request req = { (uint8_t)a, param };
  if (xQueueSend(reqQueue, &req, 0) == pdTRUE) {
    if (a != ACT_POLL) s_actionPending = true;
    return true;
  }
  // Drop-and-log: full queue means we're either spamming or the task is
  // blocked. Diagnostically visible.
  LOG_W("spotify.task", "queue full — dropped action=%s param=%ld",
        actionName(a), (long)param);
  return false;
}

void copySnapshot(Snapshot *out) {
  if (out == nullptr) return;
  portENTER_CRITICAL_SAFE(&g_snapshotMux);
  *out = g_snapshot;
  portEXIT_CRITICAL_SAFE(&g_snapshotMux);
}

void copyQueueSnapshot(QueueSnapshot *out) {
  if (out == nullptr) return;
  portENTER_CRITICAL_SAFE(&g_queueMux);
  *out = g_queueSnapshot;
  portEXIT_CRITICAL_SAFE(&g_queueMux);
}

bool hasPendingActions() { return s_actionPending; }

#ifdef SERIAL_DEBUG
// TASK-056f — unified owner-dispatch debug accessors (ADR-021 A1).
// Called from loop task only; snapshot copy under spinlock.
bool dbg_get(const char* var, char* buf, int len) {
  if (strcmp(var, "backoff") == 0) {
    snprintf(buf, len,
             "\"var\":\"backoff\",\"consecutiveFailures\":%u,"
             "\"nextPollMs\":%u,\"last\":true",
             (unsigned)s_consecutiveFailures, (unsigned)nextWaitMs());
    return true;
  }
  if (strcmp(var, "heap") == 0) {
    snprintf(buf, len,
             "\"var\":\"heap\",\"freeHeap\":%lu,\"last\":true",
             (unsigned long)ESP.getFreeHeap());
    return true;
  }
  if (strcmp(var, "snapshot") == 0) {
    // Large payload — emit multi-part lines directly; set buf[0]='\0'.
    // cmdGet skips the wrapper print when buf is empty.
    buf[0] = '\0';
    Snapshot snap; copySnapshot(&snap);
    uint32_t ageMs = (uint32_t)(millis() - snap.capturedAtMs);
    // Check if numeric fields + short strings fit in one chunk (< 256 B).
    char chunk0[300];
    int n = snprintf(chunk0, sizeof(chunk0),
      "{\"ok\":true,\"cmd\":\"get\",\"var\":\"snapshot\","
      "\"valid\":%s,\"isPlaying\":%s,\"progressMs\":%ld,"
      "\"durationMs\":%ld,\"volumePct\":%d,"
      "\"shuffle\":%s,\"repeat\":%d,"
      "\"lastPollAgeMs\":%u,\"deviceActive\":%s,",
      snap.valid ? "true" : "false",
      snap.isPlaying ? "true" : "false",
      snap.progressMs, snap.durationMs, (int)snap.volumePercent,
      snap.shuffleState ? "true" : "false", (int)snap.repeatState,
      (unsigned)ageMs, snap.deviceActive ? "true" : "false");
    char part1[800];
    int m = snprintf(part1, sizeof(part1),
      "\"track\":\"%s\",\"artist\":\"%s\",\"currentTrackUri\":\"%s\","
      "\"contextUri\":\"%s\",\"last\":true}",
      snap.trackName, snap.artistName, snap.trackUri, snap.contextUri);
    if (n + m < 798) {
      // Fits in one line — append and emit.
      char line[800];
      snprintf(line, sizeof(line), "%s%s", chunk0, part1);
      Serial.println(line);
    } else {
      // Two-part split.
      // Part 0: numeric fields.
      char p0[350];
      snprintf(p0, sizeof(p0),
        "{\"ok\":true,\"cmd\":\"get\",\"var\":\"snapshot\","
        "\"part\":0,\"last\":false,"
        "\"valid\":%s,\"isPlaying\":%s,\"progressMs\":%ld,"
        "\"durationMs\":%ld,\"volumePct\":%d,"
        "\"shuffle\":%s,\"repeat\":%d,"
        "\"lastPollAgeMs\":%u,\"deviceActive\":%s}",
        snap.valid ? "true" : "false",
        snap.isPlaying ? "true" : "false",
        snap.progressMs, snap.durationMs, (int)snap.volumePercent,
        snap.shuffleState ? "true" : "false", (int)snap.repeatState,
        (unsigned)ageMs, snap.deviceActive ? "true" : "false");
      Serial.println(p0);
      // Part 1: string fields.
      char p1[800];
      snprintf(p1, sizeof(p1),
        "{\"ok\":true,\"cmd\":\"get\",\"var\":\"snapshot\","
        "\"part\":1,\"last\":true,"
        "\"track\":\"%s\",\"artist\":\"%s\",\"currentTrackUri\":\"%s\","
        "\"contextUri\":\"%s\"}",
        snap.trackName, snap.artistName, snap.trackUri, snap.contextUri);
      Serial.println(p1);
    }
    return true;
  }
  if (strcmp(var, "queue") == 0) {
    // TASK-056m: serialize up to 5 QueueSnapshot rows, one JSON line each.
    // Split protocol: each line has "part":N,"last":bool. Reads under spinlock.
    buf[0] = '\0';
    QueueSnapshot qs; copyQueueSnapshot(&qs);
    uint8_t n = qs.count < QUEUE_MAX ? qs.count : QUEUE_MAX;
    if (n == 0) {
      Serial.println("{\"ok\":true,\"cmd\":\"get\",\"var\":\"queue\","
                     "\"count\":0,\"last\":true}");
      return true;
    }
    for (uint8_t i = 0; i < n; ++i) {
      const QueueEntry &e = qs.items[i];
      char row[256];
      snprintf(row, sizeof(row),
        "{\"ok\":true,\"cmd\":\"get\",\"var\":\"queue\","
        "\"part\":%u,\"last\":%s,"
        "\"idx\":%u,\"track\":\"%s\",\"artist\":\"%s\","
        "\"durationMs\":%lu,\"uri\":\"%s\"}",
        (unsigned)i, (i == n - 1) ? "true" : "false",
        (unsigned)i, e.name, e.artist,
        (unsigned long)e.durationMs, e.uri);
      Serial.println(row);
    }
    return true;
  }
  if (strcmp(var, "bgPoll") == 0) {
    snprintf(buf, len,
             "\"var\":\"bgPoll\",\"enabled\":%u,\"last\":true",
             (unsigned)s_bgPollEnabled);
    return true;
  }
  return false;
}

bool dbg_set(const char* var, const char* val) {
  if (strcmp(var, "backoff") == 0) {
    s_consecutiveFailures = (unsigned)atoi(val);
    return true;
  }
  if (strcmp(var, "bgPoll") == 0) {
    s_bgPollEnabled = (atoi(val) != 0) ? 1 : 0;
    return true;
  }
  // TASK-245: inject the last poll HTTP status so VE can synthesise authError()
  // deterministically (set lastHttp 403 + set backoff 2 → true) without relying
  // on a real account 403. Overwritten by the next real poll.
  if (strcmp(var, "lastHttp") == 0) {
    s_lastHttpStatus = atoi(val);
    return true;
  }
  // TASK-245 amendment: inject the last-successful-poll timestamp so VE can drive
  // connecting() deterministically (set lastOkMs 0 → connecting true [boot amber];
  // set lastOkMs 1 → connecting false [connected]). Overwritten by the next real poll.
  if (strcmp(var, "lastOkMs") == 0) {
    s_lastSuccessfulPollMs = (unsigned long)strtoul(val, nullptr, 10);
    return true;
  }
  return false;
}

uint32_t dbg_getFailureCount() {
  return (uint32_t)s_consecutiveFailures;
}
#endif // SERIAL_DEBUG

}  // namespace spotifyTask
