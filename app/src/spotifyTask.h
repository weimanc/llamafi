#pragma once
// spotifyTask.h — async Spotify HTTP on a dedicated FreeRTOS task
// (ADR-012, TASK-031). Tier-1 scope (TASK-031a): scaffolding only —
// task body is a stub that dequeues + logs, no API calls yet.
// TASK-031b lifts the poll into the task; TASK-031c lifts touch
// actions; TASK-031d removes the deferred-repoll guard.
//
// Goal: Arduino loop task never blocks on HTTP. Today's data
// (perf-001 heartbeat field `slow=display.input:4189ms`) shows the
// touch handler firing synchronous Spotify calls inline. After the
// full migration the same field should drop below 100 ms.

#include <Arduino.h>
#include <SpotifyArduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

namespace spotifyTask {

enum Action : uint8_t {
  ACT_POLL = 0,         // task self-issues on queue-empty timeout
  ACT_FORCE_POLL,       // loop requests an immediate poll (e.g. post-touch)
  ACT_NEXT,
  ACT_PREV,
  ACT_PLAY,
  ACT_PAUSE,
  ACT_SEEK,             // param = position in ms
  ACT_VOLUME,           // param = volume percent 0..100 (ADR-016 §9)
  ACT_SHUFFLE,          // param = 0 (off) | 1 (on)
  ACT_REPEAT,           // param = RepeatOptions enum: 0=track, 1=context, 2=off
  ACT_PLAY_URI,         // param = row index into g_queueSnapshot.items[]
};

struct Request {
  uint8_t action;
  int32_t param;
};

// Snapshot of the most recent successful poll. Written by the task,
// read by the loop. All accesses bracketed by snapshotMux. seq bumps
// on every successful write; loop compares to its last-rendered seq
// to detect "anything new".
struct Snapshot {
  uint32_t seq;
  uint32_t capturedAtMs;
  bool     valid;
  bool     isPlaying;
  long     progressMs;
  long     durationMs;
  // Currently-playing type from SpotifyPlayingType enum: 0=track,
  // 1=episode, 2=other. Used by chrome-001 to drive mono/stereo.
  uint8_t  playingType;
  // device.volume_percent from the same poll (TASK-041, ADR-014 A1.4).
  // -1 if no active device or field missing; 0..100 otherwise. Default
  // -1 so any pre-first-poll read sees the sentinel rather than a
  // valid 0% (snapshot.valid gates this in practice — defensive).
  int8_t   volumePercent = -1;
  // Shuffle / repeat from the same poll (chrome-001 final / LOCAL_PATCHES
  // patch #9). repeatState matches RepeatOptions enum: 0=track, 1=context,
  // 2=off — see SpotifyArduino.h. Cached locally as int8_t to avoid
  // dragging the lib header into spotifyTask.h.
  bool     shuffleState  = false;
  int8_t   repeatState   = 2;  // repeat_off
  char     trackUri[200];
  char     trackName[128];
  char     artistName[128];
  char     albumName[128];
  // TASK-066: context_uri from /me/player (playlist or album URI, empty for ad-hoc).
  char     contextUri[200];
  // TASK-056l (SERIALDBG-l): true when volumePercent != -1 (active device).
  bool     deviceActive = false;
};

// Queue snapshot (ADR-017 / TASK-020b). Written by spotifyTask on each
// successful getQueue(); read by winampDisplay to render the playlist strip.
// [0] = currently_playing, [1..QUEUE_MAX-1] = next-up queue items.
#define QUEUE_MAX SPOTIFY_QUEUE_MAX_ITEMS

struct QueueEntry {
  char     name[48];
  char     artist[32];
  char     uri[64];
  uint32_t durationMs;  // TASK-047b
};

struct QueueSnapshot {
  QueueEntry items[QUEUE_MAX];
  uint8_t    count;   // valid items (0 = nothing/unknown)
  uint32_t   seqno;   // bumped on every write; display detects changes
};

extern QueueHandle_t reqQueue;
extern Snapshot      g_snapshot;
extern portMUX_TYPE  g_snapshotMux;
extern QueueSnapshot g_queueSnapshot;
extern portMUX_TYPE  g_queueMux;
extern TaskHandle_t  g_taskHandle;

// Lifecycle. Call after spotifyRefreshToken() has primed the lib.
void begin(SpotifyArduino *spotifyObj);

// Loop posts requests; non-blocking (xQueueSend with timeout 0).
// Returns false if the queue was full — drop and emit a WARN.
bool enqueue(Action a, int32_t param = 0);

// Snapshot read (under spinlock). Caller supplies an out struct.
void copySnapshot(Snapshot *out);
void copyQueueSnapshot(QueueSnapshot *out);

// TASK-052: reset exponential backoff counter so the next timer-triggered
// poll fires at the base cadence. Safe to call from the loop task — the
// write is a single aligned 32-bit store (atomic on ESP32 Xtensa).
void resetBackoff();

// TASK-116b: returns true while a user-initiated action is in flight.
// Set when enqueue() accepts a non-POLL action; cleared when the queue
// drains (xQueueReceive returns pdFALSE). Prevents amber indicator from
// flashing between consecutive queued actions.
bool hasPendingActions();

// TASK-058: poll timing getters — safe to call from the loop task.
// lastSuccessfulPollAgeMs: millis since last 200 or 204; 0 before first poll.
// nextPollInMs: estimated ms until next cadence poll (clamped to 0 when overdue).
uint32_t lastSuccessfulPollAgeMs();
uint32_t nextPollInMs();

// TASK-053b: returns true when the connection is considered healthy
// (fewer than 2 consecutive poll failures). Safe to call from any task.
bool isHealthy();

// TASK-245 / ADR-046: returns true when the poll is in a persistent 403 state
// (authorization refused — e.g. owner-account Premium lapsed). Drives the red
// taskbar active-bar error signal via SpotifyApp::hasError(). Self-clears on
// the next successful (200/204) poll. Safe to call from the loop task.
bool authError();

// TASK-245 amendment / ADR-046: true until the first successful poll — drives the
// amber "connecting" taskbar state at boot. Latches false on first 200/204.
bool connecting();

// TASK-053b: schedule a hard TLS reset. Sets a pending flag; the spotify
// task detects it at the top of its next iteration and calls client.stop()
// on its own stack (avoids cross-task mbedTLS races). Also zeroes the
// backoff counter so the recovery poll fires immediately.
void resetTls();

// TASK-264 (Q3-a): notify the task that WebRadio is now the active player.
// active == true: drops TLS connection (via s_resetTlsPending) and idles
//   until cleared — reclaims the ~50 K TLS working set for the WebRadio arena.
// active == false: resumes normal poll/reconnect on the next iteration.
// Non-blocking — safe to call from the Arduino loop task.
void setWebRadioActive(bool active);

// TASK-240: stack instrumentation — minimum free stack ever (watermark) + size.
size_t stackHighWaterBytes();
size_t stackSizeBytes();

// TASK-131: stop Spotify TLS so a dataTask fetch can allocate its own
// session from the freed heap (~40 k released). Blocks until the spotify
// task acks (up to 5 s). Must be followed by tlsResume(); the task spins
// (20 ms ticks) holding the yield until that call.
// Used by every HTTPS fetch in dataTask (heatmap, crypto, stock quote/chart).
void tlsYield();
void tlsResume();

// TASK-299: lock-free snapshot of the yield handshake for get dataq —
// outstanding tlsYield() callers and whether the task has acked the stop.
// A dataq read showing wrPhase=0 with yieldCount>0 and tlsStopped=false for
// tens of seconds means the station fetch is parked waiting for the ack.
uint8_t tlsYieldCount();
bool    tlsStoppedFlag();
// Loop-position marker: -1 not started, 0 queue-wait, 1 yield-spin,
// 2 wr-idle, 3 dispatching (doPoll / API call / token refresh).
int8_t   taskActivity();
uint32_t taskActivityMs();

#ifdef SERIAL_DEBUG
// TASK-056f (serialdbg-001 / ADR-021 A1) — unified owner-dispatch accessors.
// Loop-task only (no cross-task safety for snapshot reads outside spinlock).
// dbg_get: serialize state for var into buf (JSON key-value fragment, no
//   outer braces). Multi-part payloads emitted via Serial.printf directly;
//   buf set to '\0'. Returns false if var unknown.
//   Vars: "snapshot", "backoff", "heap", "queue".
// dbg_set: write a debug var. Returns false if var unknown or val invalid.
//   Vars: "backoff" (sets consecutiveFailures; aligned 32-bit store on Xtensa).
// dbg_getFailureCount: thin getter for cmdInfo (avoids parsing dbg_get output).
bool dbg_get(const char* var, char* buf, int len);
bool dbg_set(const char* var, const char* val);
uint32_t dbg_getFailureCount();
#endif

}  // namespace spotifyTask
