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
#include <esp_task_wdt.h>
#include "dataTask.h"   // TASK-697: dbgRingPush — the yield-handshake half of `get dataRing`

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
// TASK-245: last poll HTTP status (set in doPoll). Single aligned 32-bit store,
// atomic on Xtensa.
static volatile int s_lastHttpStatus = 0;
// TASK-245: sticky auth-error (403) latch — set on a 403 poll, cleared on a
// 200/204. Read by authError(). Held through transient -1 blips; touch-immune
// (not coupled to s_consecutiveFailures). See doPoll() / dbg_set("lastHttp").
static volatile bool s_authErrorLatched = false;
// TASK-366 / ADR-046: sticky non-auth-degraded latch — set once
// s_consecutiveFailures reaches isHealthy()'s own >=2 threshold on a non-403
// failure (network blip, timeout, DNS), cleared only on a real 200/204.
// Deliberately NOT a raw read of s_consecutiveFailures/isHealthy(): that
// counter is zeroed by resetBackoff() on every touch (ADR-046 Amendment 2's
// exact flap lesson for s_authErrorLatched applies here too), so a sticky
// latch mirroring s_authErrorLatched's pattern is required to avoid the same
// red<->green flap on tap. Read by degraded(), OR'd into SpotifyApp::hasError().
static volatile bool s_degradedLatched = false;
// TASK-053b: pending TLS reset flag. Set by resetTls() (loop task); read
// and cleared at the top of each taskBody iteration (spotify task). The
// volatile ensures the compiler does not hoist the check out of the loop.
// A single bool write is atomic on ESP32 Xtensa (aligned word store).
static volatile bool s_resetTlsPending = false;
// TASK-264 (Q3-a): set by setWebRadioActive(); suppresses TLS reconnect
// while WebRadio holds the arena.
static volatile bool s_webRadioActive = false;

#ifdef SERIAL_DEBUG
// ADR-042 E2: background poll inhibit. 1 = normal, 0 = suspended.
// Set/cleared by dbg_set("bgPoll", ...). Reset to 1 by resetTls() (recovery invariant).
static volatile uint8_t s_bgPollEnabled = 1;

// TASK-430: test-only wedge injection. This IS a new 4-byte static
// (SERIAL_DEBUG-only, so it does not exist in the production .bss at all).
// Debug .bss headroom is near zero (see CLAUDE.md) — 4 bytes was checked
// against dram0_0_seg before landing this. Arms a one-shot simulated "stuck mid-HTTP-call"
// window: the task honours it AFTER its next dequeue but BEFORE the
// yield-ack checkpoint that follows, so an in-flight tlsYield()/
// tlsTryYield() request queued during the window goes un-acked until the
// window elapses — reproducing the real bug's shape (a task that will not
// check the yield flag again until its blocking network call returns)
// without an actual wedged HTTP call. `set spotifyWedge <ms>` arms it.
static volatile uint32_t s_dbgWedgeMs = 0;
#endif

// TASK-131: TLS yield — dataTask requests Spotify TLS stop so it can
// allocate its own session from the freed heap. taskBody calls client.stop()
// then gives the semaphore and spins until every requester has resumed.
// TASK-287: reference-counted, not a single flag — WebRadioApp::_play() and
// a dataTask fetcher (e.g. the WebRadio station-list fetch) can both want
// TLS yielded at once (they fire close together on WebRadio entry). A plain
// bool let the first resume() clear the flag out from under a still-waiting
// second requester, which then polled uselessly until another full yield
// cycle happened to occur (functional stall, observed hanging 60s+ in DUT
// testing). s_tlsYieldReqCount/s_tlsStopped/s_tlsYieldMux are guarded
// together so concurrent tlsYield()/tlsResume() callers see a consistent
// view: only the request that actually stops TLS waits on the semaphore;
// late arrivals while already-stopped return immediately; only the last
// tlsResume() (count back to 0) lets spotifyTask resume.
static volatile uint8_t  s_tlsYieldReqCount = 0;  // # of outstanding tlsYield() callers

// TASK-299: loop-position marker for get dataq — where is spotifyTask right
// now? -1=not started, 0=blocked in xQueueReceive, 1=yield-spin (acked, holding
// while callers run), 2=wr-idle bounce, 3=dispatching an action (doPoll/API
// call, incl. token refresh). Written only by spotifyTask; read lock-free.
static volatile int8_t   s_dbgActivity   = -1;
static volatile uint32_t s_dbgActivityMs = 0;
static inline void dbgAct(int8_t a) { s_dbgActivity = a; s_dbgActivityMs = millis(); }
static volatile bool     s_tlsStopped       = false;  // true once spotifyTask has ack'd for the current batch
static SemaphoreHandle_t s_tlsYieldedSem = nullptr;
static portMUX_TYPE       s_tlsYieldMux = portMUX_INITIALIZER_UNLOCKED;

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
  // TASK-244: a 403 auth-error (owner-account Premium lapse, TASK-243) will not
  // recover by fast-retrying — it takes hours — and hammering it every 5–20 s
  // keeps the spotify task holding the shared TLS, starving every dataTask
  // fetcher (weather/crypto/stock/teletext) behind tlsYield() (the visible
  // "stuck on amber" symptom). Jump straight to the max backoff so Spotify idles
  // between polls and the dataTask gets prompt yield windows; recovery is still
  // detected within one max-backoff interval once the account is fixed. Also
  // immune to resetBackoff() (touch zeroes s_consecutiveFailures, but the 403
  // latch holds), so a tap can't restart the fast-poll storm.
  if (s_authErrorLatched) return kBackoffMaxMs;
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
  // TASK-245: latch the auth-error (403) state. Sticky — set on a 403, held
  // through transient -1/timeout blips (which are NOT auth refusals), cleared
  // only on a real success below. Keying authError() on this latch rather than
  // the instantaneous status avoids the red bar flapping when failed polls
  // alternate 403 / -1, and decouples it from s_consecutiveFailures (which a
  // touch zeroes via resetBackoff()).
  if (status == 403) s_authErrorLatched = true;

  if (status == 200) {
    s_consecutiveFailures = 0;
    s_lastSuccessfulPollMs = millis();
    s_authErrorLatched = false;
    s_degradedLatched = false;
    LOG_D("spotify.poll", "ok %s", httpErr(status));
  } else if (status == 204) {
    s_consecutiveFailures = 0;
    s_lastSuccessfulPollMs = millis();
    s_authErrorLatched = false;
    s_degradedLatched = false;
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
    // TASK-366: >=2 mirrors isHealthy()'s own threshold. 403s are excluded
    // here in spirit (a 403 that trips this would already be red via
    // authError()) but not worth a branch to special-case — OR'd together
    // in hasError(), a redundant true changes nothing observable.
    if (s_consecutiveFailures >= 2) s_degradedLatched = true;
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

    // TASK-289: service TLS-yield requests BEFORE the WebRadio idle trap
    // below — that continue-loop never reaches the post-dequeue yield check,
    // so a tlsYield() raised while WebRadio is active (and no other yield is
    // outstanding) would go un-acked for its full 150 s ceiling, parking the
    // caller's task (observed: deferred wrUrl play froze loopTask — fetch
    // resumed count→0, this task fell into wr-idle, play's fresh yield
    // starved). Identical semantics to the post-dequeue block; worst-case
    // ack latency from wr-idle is one 500 ms sleep.
    if (s_tlsYieldReqCount > 0) {
      client.stop();
      LOG_I("spotify.tls", "tls yield — client stopped");
      dbgAct(1);
#ifdef SERIAL_DEBUG
      dataTask::dbgRingPush(dataTask::RING_TLS_STOP_ACK, (int16_t)s_tlsYieldReqCount);
#endif
      if (s_tlsYieldedSem) xSemaphoreGive(s_tlsYieldedSem);
      while (s_tlsYieldReqCount > 0) {
        vTaskDelay(pdMS_TO_TICKS(20));
        // TASK-299: re-ack fresh waiters. A tlsResume() followed within one
        // 20 ms tick by another caller's tlsYield() (count 1→0→1 — exactly
        // what back-to-back queued dataTask fetches produce) is invisible to
        // this loop: the new waiter got no give (ours was consumed by the
        // previous cycle) and parked for its full 150 s ceiling, serializing
        // every queued fetch behind it (T_WR_TLS_01 false-FAILs; cascades).
        // count>0 with s_tlsStopped still false means an un-acked waiter;
        // the binary semaphore absorbs duplicate gives, so this is safe to
        // repeat each tick until the waiter takes it.
        if (s_tlsYieldReqCount > 0 && !s_tlsStopped && s_tlsYieldedSem)
          xSemaphoreGive(s_tlsYieldedSem);
      }
      LOG_I("spotify.tls", "tls yield — resumed");
      continue;
    }

    // TASK-264 (Q3-a): keep TLS stopped while WebRadio holds the arena.
    // client.stop() is idempotent; 500 ms idle prevents tight-looping.
    if (s_webRadioActive) {
      client.stop();
      dbgAct(2);
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    Request req;
    uint32_t waitMs = nextWaitMs();
    dbgAct(0);
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

#ifdef SERIAL_DEBUG
    // TASK-430: fire the armed wedge here — after this dequeue, before the
    // yield-ack checkpoint below — so any tlsYield()/tlsTryYield() request
    // that lands while we're "busy" goes un-acked until the window elapses,
    // same as a real stuck-mid-HTTP-call task would. Feeds the TWDT in
    // slices, same shape as tlsYield()'s own wait, so it cannot crash the
    // device on its own.
    if (s_dbgWedgeMs > 0) {
      uint32_t wedge = s_dbgWedgeMs;
      s_dbgWedgeMs = 0;
      LOG_W("spotify.tls", "debug wedge armed — simulating %ums unresponsive HTTP call",
            (unsigned)wedge);
      for (uint32_t waited = 0; waited < wedge; waited += 100) {
        vTaskDelay(pdMS_TO_TICKS(100));
        esp_task_wdt_reset();
      }
      LOG_W("spotify.tls", "debug wedge released");
    }
#endif

    // TASK-131: TLS yield — stop Spotify TLS so dataTask can reuse the client
    // for its own fetch (shared-client approach avoids double-TLS-context OOM).
    // Runs after xQueueReceive so any in-flight API call has already completed.
    // TASK-287: spins until every outstanding requester has called
    // tlsResume() (count back to 0), not just a single flag — see the
    // s_tlsYieldReqCount comment above. Discards the current queued request
    // (the wake-up ACT_POLL) via continue.
    if (s_tlsYieldReqCount > 0) {
      client.stop();
      LOG_I("spotify.tls", "tls yield — client stopped");
      dbgAct(1);
#ifdef SERIAL_DEBUG
      dataTask::dbgRingPush(dataTask::RING_TLS_STOP_ACK, (int16_t)s_tlsYieldReqCount);
#endif
      if (s_tlsYieldedSem) xSemaphoreGive(s_tlsYieldedSem);
      while (s_tlsYieldReqCount > 0) {
        vTaskDelay(pdMS_TO_TICKS(20));
        // TASK-299: re-ack fresh waiters — see the identical top-of-loop
        // block for the count 1→0→1 race this closes.
        if (s_tlsYieldReqCount > 0 && !s_tlsStopped && s_tlsYieldedSem)
          xSemaphoreGive(s_tlsYieldedSem);
      }
      LOG_I("spotify.tls", "tls yield — resumed");
      continue;
    }

    dbgAct(3);
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

void begin(SpotifyArduino *spotifyObj, bool startIdle) {
  if (g_taskHandle != nullptr) {
    LOG_W("spotify.task", "begin() called twice — ignoring");
    return;
  }
  s_spotify = spotifyObj;

  // TASK-363 (M-SPOTIFY-BOOT-GATE, ADR-054 decision 1): seed the idle flag
  // *before* the task is created, so the task's very first top-of-loop
  // check already sees the correct state — closes Finding 1's boot race,
  // where s_webRadioActive was only set later via setWebRadioActive() from
  // the boot-time switchApp(WebRadio) call, too late to prevent the first
  // self-issued ACT_POLL from firing a TLS connect ~5s after begin().
  s_webRadioActive = startIdle;

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
  LOG_I("spotify.task", "begin ok — handle=%p startIdle=%d", (void *)g_taskHandle, (int)startIdle);
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

// TASK-245 / ADR-046: true while in a 403 auth-error state (e.g. owner-account
// Premium lapsed, TASK-243). Reads the sticky s_authErrorLatched, NOT the
// instantaneous status or s_consecutiveFailures:
//   (a) one 403 is enough — it's a definitive auth refusal, not a transient
//       blip (~13 s to red vs ~31 s for the old >=2-consecutive rule).
//   (b) held through transient -1/timeout polls (which alternate with 403s on
//       a wedged session) — keying on the live status would flap red↔green.
//   (c) touch-immune — resetBackoff() (every touch) zeroes s_consecutiveFailures
//       but not this latch.
// Cleared only on a real success (200/204) in doPoll(). Via SpotifyApp::hasError().
bool authError() {
  return s_authErrorLatched;
}

// TASK-366 / ADR-046: true while in a sticky non-auth-degraded state (>=2
// consecutive non-403 poll failures — network/timeout/DNS, not auth refusal).
// OR'd with authError() into SpotifyApp::hasError() so the taskbar goes red
// on either kind of persistent failure. See s_degradedLatched for why this
// is a dedicated latch rather than a raw isHealthy() read.
bool degraded() {
  return s_degradedLatched;
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

// TASK-264 (Q3-a): signal the task that WebRadio is now the active player.
// When active, kicks an immediate client.stop() via s_resetTlsPending and then
// suppresses all TLS reconnects until cleared. Non-blocking.
void setWebRadioActive(bool active) {
  s_webRadioActive = active;
  if (active) s_resetTlsPending = true;
}

bool tlsYield() {
  if (!s_tlsYieldedSem || !reqQueue) return true;

  // TASK-287: only the requester that actually flips TLS from running to
  // stopped needs to wait — a concurrent second caller (count already >0,
  // s_tlsStopped already true) can return immediately, TLS is already
  // yielded for it too.
  bool needWait;
  portENTER_CRITICAL(&s_tlsYieldMux);
  needWait = !s_tlsStopped;
  s_tlsYieldReqCount++;
  portEXIT_CRITICAL(&s_tlsYieldMux);
  if (!needWait) return true;

#ifdef SERIAL_DEBUG
  dataTask::dbgRingPush(dataTask::RING_YIELD_REQ, (int16_t)s_tlsYieldReqCount);
#endif

  // Drain any orphaned give from a previous timed-out yield (avoids the race
  // where the semaphore is already available from a prior cycle, making the
  // next xSemaphoreTake return immediately before spotifyTask actually stops).
  xSemaphoreTake(s_tlsYieldedSem, 0);
  // Wake the task if it is blocked in xQueueReceive
  Request r{ACT_POLL, 0};
  xQueueSendToFront(reqQueue, &r, 0);
  // Wait for task ack (up to 150 s — covers worst-case 2 API calls × 75 s
  // each = 150 s, with 30 s handshake + 15 s recv × 2 per call).
  // TASK-286: polled in short slices rather than one blocking 150 s take —
  // a caller on loopTask (e.g. WebRadioApp::_play()) would otherwise never
  // feed the TWDT while spotifyTask is stuck mid-API-call (observed with
  // TASK-243's stalled token refresh), tripping the watchdog and hard-
  // crashing the device well before the 150 s ceiling (TASK-285).
  constexpr uint32_t kSliceMs = 200;
  constexpr uint32_t kTotalMs = 150000;
  for (uint32_t waited = 0; waited < kTotalMs; waited += kSliceMs) {
    if (xSemaphoreTake(s_tlsYieldedSem, pdMS_TO_TICKS(kSliceMs)) == pdTRUE) {
      s_tlsStopped = true;
#ifdef SERIAL_DEBUG
      dataTask::dbgRingPush(dataTask::RING_YIELD_ACK, (int16_t)s_tlsYieldReqCount);
#endif
      return true;
    }
    // TASK-287: a concurrent tlsYield() call already consumed the one give()
    // spotifyTask issues per stop event and set s_tlsStopped — stop waiting
    // on a token that will never come again this cycle.
    if (s_tlsStopped) {
#ifdef SERIAL_DEBUG
      dataTask::dbgRingPush(dataTask::RING_YIELD_ACK, (int16_t)s_tlsYieldReqCount);
#endif
      return true;
    }
    esp_task_wdt_reset();
  }
  // TASK-700: the 150 s ceiling elapsed with no ack. Previously this path
  // left s_tlsYieldReqCount incremented forever, relying on TlsYieldGuard's
  // destructor to unconditionally call tlsResume() and rebalance it — that
  // assumption is gone now that ok_ reflects this function's real return
  // value (a failed guard's destructor no longer calls tlsResume() at all).
  // Roll back the same way tlsTryYield() does below, with the same race
  // check: the ack can still land in the gap between the last semaphore
  // check above and here, in which case this caller legitimately holds the
  // yield and must be treated as a success (no rollback, return true).
  portENTER_CRITICAL(&s_tlsYieldMux);
  bool ackedAtTheWire = s_tlsStopped;
  if (!ackedAtTheWire && s_tlsYieldReqCount > 0) s_tlsYieldReqCount--;
  uint8_t countAfter = s_tlsYieldReqCount;
  portEXIT_CRITICAL(&s_tlsYieldMux);
  if (!ackedAtTheWire) {
    LOG_W("spotify.tls", "tls yield timed out after 150000ms — ref count rolled back, no yield granted");
  }
#ifdef SERIAL_DEBUG
  dataTask::dbgRingPush(ackedAtTheWire ? dataTask::RING_YIELD_ACK : dataTask::RING_YIELD_TIMEOUT,
                         (int16_t)countAfter);
#endif
  return ackedAtTheWire;
}

// TASK-430: bounded non-blocking sibling of tlsYield() above — same
// ref-counted handshake, but gives up after timeoutMs instead of riding the
// full 150 s ceiling. Mirrors tlsYield()'s increment/wake/slice-wait shape;
// only the exit paths differ (see spotifyTask.h for the contract).
bool tlsTryYield(uint32_t timeoutMs) {
  // DISABLE_SPOTIFY builds (cyd2usb_player — TASK-431's shipping home for
  // Player mode) never call begin(), so these stay null and there is no TLS
  // session to yield. tlsYield() null-guards to a silent no-op success (the
  // caller proceeds, tlsResume() below no-ops too since it only touches the
  // plain s_tlsYieldReqCount/s_tlsStopped ints, no pointer deref). Returning
  // false here instead would make aeConnectFile() fail EVERY call on the one
  // variant local playback is supposed to work on — caught by TASK-430's own
  // gate before it shipped.
  if (!s_tlsYieldedSem || !reqQueue) return true;

  bool needWait;
  portENTER_CRITICAL(&s_tlsYieldMux);
  needWait = !s_tlsStopped;
  s_tlsYieldReqCount++;
  portEXIT_CRITICAL(&s_tlsYieldMux);
  if (!needWait) return true;

#ifdef SERIAL_DEBUG
  dataTask::dbgRingPush(dataTask::RING_YIELD_REQ, (int16_t)s_tlsYieldReqCount);
#endif

  // Same orphaned-give drain as tlsYield() — see its comment.
  xSemaphoreTake(s_tlsYieldedSem, 0);
  Request r{ACT_POLL, 0};
  xQueueSendToFront(reqQueue, &r, 0);

  constexpr uint32_t kSliceMs = 100;
  uint32_t waited = 0;
  while (waited < timeoutMs) {
    uint32_t slice = (timeoutMs - waited < kSliceMs) ? (timeoutMs - waited) : kSliceMs;
    if (xSemaphoreTake(s_tlsYieldedSem, pdMS_TO_TICKS(slice)) == pdTRUE) {
      s_tlsStopped = true;
#ifdef SERIAL_DEBUG
      dataTask::dbgRingPush(dataTask::RING_YIELD_ACK, (int16_t)s_tlsYieldReqCount);
#endif
      return true;
    }
    if (s_tlsStopped) {  // TASK-287: concurrent caller already got the ack
#ifdef SERIAL_DEBUG
      dataTask::dbgRingPush(dataTask::RING_YIELD_ACK, (int16_t)s_tlsYieldReqCount);
#endif
      return true;
    }
    esp_task_wdt_reset();
    waited += slice;
  }

  // Timed out. Roll back our own increment so a caller that gives up leaves
  // no trace — unless the task acked in the gap between the last check above
  // and here, in which case this caller now legitimately holds the yield and
  // must be treated as a success (its ref count stays, and it owes a
  // tlsResume() like any other successful caller).
  portENTER_CRITICAL(&s_tlsYieldMux);
  bool ackedAtTheWire = s_tlsStopped;
  if (!ackedAtTheWire && s_tlsYieldReqCount > 0) s_tlsYieldReqCount--;
  uint8_t countAfter = s_tlsYieldReqCount;
  portEXIT_CRITICAL(&s_tlsYieldMux);
  if (!ackedAtTheWire) {
    LOG_W("spotify.tls", "tls try-yield timed out after %ums — ref count rolled back, no yield granted",
          (unsigned)timeoutMs);
  }
#ifdef SERIAL_DEBUG
  dataTask::dbgRingPush(ackedAtTheWire ? dataTask::RING_YIELD_ACK : dataTask::RING_YIELD_TIMEOUT,
                         (int16_t)countAfter);
#endif
  return ackedAtTheWire;
}

uint8_t tlsYieldCount()  { return s_tlsYieldReqCount; }
bool    tlsStoppedFlag() { return s_tlsStopped; }
int8_t  taskActivity()   { return s_dbgActivity; }
uint32_t taskActivityMs() { return s_dbgActivityMs; }

void tlsResume() {
  // TASK-287: only the LAST outstanding requester (count back to 0) actually
  // lets spotifyTask resume — an earlier resume() must not clear the yield
  // out from under a still-waiting concurrent caller.
  portENTER_CRITICAL(&s_tlsYieldMux);
  if (s_tlsYieldReqCount > 0) s_tlsYieldReqCount--;
  if (s_tlsYieldReqCount == 0) s_tlsStopped = false;
  uint8_t countAfter = s_tlsYieldReqCount;
  portEXIT_CRITICAL(&s_tlsYieldMux);
#ifdef SERIAL_DEBUG
  dataTask::dbgRingPush(dataTask::RING_TLS_RESUME, (int16_t)countAfter);
#endif
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
    // TASK-366: mirror doPoll()'s latch rule so VE can drive the degraded
    // taskbar red state without a real network failure ("set backoff 2").
    // Sticky, same as the real path — does not clear on a lower value here;
    // use `set lastHttp 200` (below) to simulate the recovery that clears it.
    if (s_consecutiveFailures >= 2) s_degradedLatched = true;
    return true;
  }
  if (strcmp(var, "bgPoll") == 0) {
    s_bgPollEnabled = (atoi(val) != 0) ? 1 : 0;
    return true;
  }
#ifdef SERIAL_DEBUG
  // TASK-430: `set spotifyWedge <ms>` arms the one-shot simulated-stuck-task
  // wedge (see s_dbgWedgeMs above) for the spotify task's next dequeue.
  if (strcmp(var, "spotifyWedge") == 0) {
    s_dbgWedgeMs = (uint32_t)strtoul(val, nullptr, 10);
    return true;
  }
#endif
  // TASK-245: inject a poll HTTP status so VE can drive authError()
  // deterministically without a real account 403. Applies the same latch rule
  // as a real poll (403 → set, 200/204 → clear), so `set lastHttp 403` → red,
  // `set lastHttp 200` → clear. Overwritten by the next real poll.
  if (strcmp(var, "lastHttp") == 0) {
    int s = atoi(val);
    s_lastHttpStatus = s;
    if (s == 403) s_authErrorLatched = true;
    else if (s == 200 || s == 204) {
      s_authErrorLatched = false;
      s_degradedLatched = false;  // TASK-366: same success clears both latches
    }
    return true;
  }
  // TASK-245 amendment: inject the last-successful-poll timestamp so VE can drive
  // connecting() deterministically (set lastOkMs 0 → connecting true [boot amber];
  // set lastOkMs 1 → connecting false [connected]). Overwritten by the next real poll.
  if (strcmp(var, "lastOkMs") == 0) {
    s_lastSuccessfulPollMs = (unsigned long)strtoul(val, nullptr, 10);
    return true;
  }
  // TASK-411 — seed the queue snapshot with N synthetic entries and bump the
  // seqno, exactly as storeQueueSnapshot() does for a real poll. `set queue N`,
  // 0 <= N <= QUEUE_MAX; N=0 is the empty-list state.
  //
  // Why this exists: PLEDIT rows come only from this snapshot, so every test
  // that asserts on a *row* — T_PLE_01 states 2-5, T_PLE_02/03/06, T155-T160 —
  // was unrunnable whenever the account could not poll. TASK-243 (owner Premium
  // lapsed) has held that state across multiple sessions with no owner-side fix,
  // and `wait_for_queue()` simply skips those tests rather than failing them,
  // so the gap was silent. Injection also buys something a live account cannot:
  // the SAME rows on two different builds, which is what a before/after pixel
  // diff needs to mean anything, and a deterministic over-long title instead of
  // whatever happens to be playing.
  //
  // Content is a pure function of the index, so two builds seeded with the same
  // N render identical pixels:
  //   - odd rows carry a deliberately over-long artist AND title, so a single
  //     capture exercises both the truncated and the untruncated row layout;
  //   - durations sweep past 9:59 (i >= 15), so the duration column is captured
  //     at both 4- and 5-character widths, which is what moves the truncation
  //     budget for the row text.
  // Overwritten by the next successful real poll, same as any other injected
  // state here.
  if (strcmp(var, "queue") == 0) {
    int n = val && *val ? atoi(val) : 0;
    if (n < 0) n = 0;
    if (n > QUEUE_MAX) n = QUEUE_MAX;
    portENTER_CRITICAL_SAFE(&g_queueMux);
    for (int i = 0; i < n; i++) {
      QueueEntry &e = g_queueSnapshot.items[i];
      if (i & 1) {
        snprintf(e.name,   sizeof(e.name),   "A Very Long Track Title That Must Truncate %02d", i);
        snprintf(e.artist, sizeof(e.artist), "An Extremely Long Artist %02d", i);
      } else {
        snprintf(e.name,   sizeof(e.name),   "Track %02d", i);
        snprintf(e.artist, sizeof(e.artist), "Artist %02d", i);
      }
      snprintf(e.uri, sizeof(e.uri), "spotify:track:inj%02d", i);
      e.durationMs = (uint32_t)(61 + i * 37) * 1000UL;   // 1:01 .. 12:44
    }
    g_queueSnapshot.count = (uint8_t)n;
    g_queueSnapshot.seqno++;
    portEXIT_CRITICAL_SAFE(&g_queueMux);
    Serial.printf("[D][spotify.queue] injected count=%u seqno=%lu\n",
                  (unsigned)n, (unsigned long)g_queueSnapshot.seqno);
    return true;
  }
  return false;
}

uint32_t dbg_getFailureCount() {
  return (uint32_t)s_consecutiveFailures;
}
#endif // SERIAL_DEBUG

#ifdef SERIAL_DEBUG
// TASK-635: `get armed` predicates. bgPoll is armed when OFF — the real path
// only ever sets it back to 1 (reconnect, ADR-042), so off is always injected.
bool dbgArmedWedge() { return s_dbgWedgeMs > 0; }
bool dbgBgPollOff() { return s_bgPollEnabled == 0; }
#endif

}  // namespace spotifyTask
