#!/usr/bin/env python3
"""Long single-station WebRadio soak — TASK-393 recurrence watch, v2.

Plays ONE real station (injected via `set wrUrl <resolved-url>`, NOT played
from the full station list) for an extended duration. Single-station is
deliberate: with a real multi-station list, `wrAutoSkip`'s default-ON
behavior means a repeatedly-failing station gets skipped rather than stuck
— which would silently defeat the entire point of this soak (v1 did exactly
this: auto-skip wandered across the real 30-station list and produced a
confusing mix of titles from different stations with no way to tell which
station was actually playing, because nothing was watching `wrIdx`). With
one station in the list, `_stationCount==1` so the auto-skip-to-next branch
in `_onPlaybackFailed()` never applies — TASK-276's terminal-retry is the
ONLY recovery path, exactly the mechanism this soak exists to stress.

v1 also only ever did periodic `get` polling, discarding (via
`reset_input_buffer()`) every unsolicited log line the DUT emits between
polls — throwing away exactly the event stream (`play idx=`, `terminal
retry`, `connecttohost failed`, `stream dead`, `ICY:`, heartbeats) that
would show precisely what happened and when. v2 uses a continuous
reader-thread architecture (matching test_adr045_gate.py) instead: one
thread owns the serial port, tees every raw line (host-timestamped) to a
full log file, and parses known patterns into a structured, real-time
timeline. `get` polling is now a light, low-frequency cross-check
(wrState/wrIdx/wrIcy), not the primary data source.

Primary anomaly signal is now the ACTUAL TASK-390/393 symptom, not a proxy:
the heartbeat's `last_render_age_ms` field, parsed directly off every
`[I][hb]` line. If it climbs by ~the same amount as `uptime` (i.e., zero
repaints) across several consecutive heartbeats, that IS the render-freeze
signature — the same thing established by hand-reading heartbeats earlier
this session. A secondary, mechanism-level signal watches the parsed event
log for a connect-failure/stream-dead event with no observed recovery
(fresh `play idx=` or `terminal retry` line) within WR_TERMINAL_RETRY_MS +
slack.

Either firing captures a full `get` snapshot (wrState/wrIcy/wrIdx/wrSkip/
heap/stacks) immediately and writes an anomaly report; the soak keeps
running afterward (a later recovery, or the run ending still stuck, both
get captured too).

Runs against whatever debug build (SERIAL_DEBUG) is currently flashed —
does not flash anything itself. **Flash `cyd2usb_winamp_debug_noSpotify`
first** (`-DDISABLE_SPOTIFY`, `app/platformio.ini`) — Spotify's background
polling is a continuous competing TLS user that reliably starved the
station-fetch's heap-contiguity guard on a fresh boot this session, and the
runtime `set bgPoll 0` workaround (still sent, belt-and-braces) did NOT
reliably prevent that recurring in practice. This does mean the soak tests
the WebRadio-only mechanism in isolation, not the exact environment of the
one real historical sighting (which had Spotify's TLS churn concurrently
active — TASK-390's own investigation plan flags that as an unconfirmed
contributing hypothesis). Treat this as a first, faster pass that narrows
the mechanism question; a Spotify-present run (regular `cyd2usb_winamp_debug`
build) is a distinct follow-up, not a substitute, if this comes back clean.

Reviewed by an independent agent (VE-style, see TASK-397 in tasks.md) before
first real use — two blocking findings fixed: the render-freeze detector
was gated on `last_render_age_ms` alone, which climbs identically during
completely normal quiet PLAYING (WebRadio's own repaint sites are all
targeted blits after initial connect, not full-chrome repaints) and would
have false-positived within minutes of every run; and `wrAutoSkip` was never
forced on, silently risking a soak where the terminal-retry mechanism under
test was itself disabled by a stale persisted setting.

Usage:
    python3 test_webradio_long_soak.py --port /dev/ttyUSB0 --hours 4
        [--station-name "SLAM! DANCE CLASSICS"] [--report-out PATH] [--raw-log PATH]
Exit 0 always (observational, not a pass/fail gate) unless the DUT never
becomes ready or no station can be resolved.
"""
import re
import sys
import json
import time
import atexit
import queue
import signal
import argparse
import threading
import serial
from pathlib import Path

from app_ids_gen import APP_SLOT

TOOLS_DIR = Path(__file__).resolve().parent
REPORT_DIR = TOOLS_DIR / "rnd_logs"

# WRPlayState (webRadioApp.h): 0 STOPPED,1 CONNECTING,2 PLAYING,
# 3 ERROR_WIFI,4 ERROR_STALL,5 ERROR_UNREACHABLE,6 ERROR_BLOCKED
RETRYABLE_ERROR_STATES = {3, 4, 5}
WR_TERMINAL_RETRY_MS = 30000   # webRadioApp.h:69 -- keep in sync if that constant moves
STUCK_SLACK_S = 20.0           # margin over WR_TERMINAL_RETRY_MS before flagging (mechanism signal)
RENDER_STUCK_HEARTBEATS = 3    # consecutive zero-repaint heartbeats before flagging (render signal)
HEARTBEAT_PERIOD_S = 30        # logHeartbeat.h PERIOD_MS
RENDER_AGE_SLACK_MS = 3000     # tolerance on "delta == heartbeat period" (jitter, missed lines)
# Second VE review finding 2: total silence (loopTask wedged -- this project
# has hit that failure class repeatedly: TASK-285/288/295) is a DIFFERENT
# failure mode than a render freeze, and previously had no detector at all --
# a DUT that died at hour 1 of a 4h soak would have produced a "complete, 0
# anomalies" report, the worst possible outcome for an unattended run. ~3x
# the heartbeat period of zero serial lines (not just zero heartbeats --
# any line at all) is the signal.
DUT_SILENCE_THRESHOLD_S = HEARTBEAT_PERIOD_S * 3

# DUT log-line signatures -- see webRadioApp.h for the LOG_I/LOG_W call sites.
RE_HEARTBEAT = re.compile(
    r"\[hb\].*heap=(\d+)k.*uptime=(\d+):(\d+):(\d+).*last_render_age_ms=(\d+)")
# Second VE review finding 1: real radio-browser.info names routinely
# contain spaces (this soak's own default target, "SLAM! DANCE CLASSICS",
# is one) -- \S+ silently dropped the whole line from the event timeline
# whenever a name had a space in it. Non-greedy .*? instead.
RE_PLAY = re.compile(r"\[webradio\] play idx=(\d+) name=(.*?) url=(\S+)")
# VE review finding 3: Audio.cpp logs "SSL has been established" for https
# stations, "Connection has been established" for http -- the SSL variant
# was missing, silently thinning the event timeline for https-only stations.
RE_CONNECT_OK = re.compile(r"(?:SSL|Connection) has been established in (\d+) ms")
RE_CONNECT_FAIL = re.compile(r"connecttohost failed idx=(\d+)")
RE_STREAM_DEAD = re.compile(r"stream dead \(isRunning=(\d+) for (\d+)ms, bufStalled for (\d+)ms\)")
RE_STALL_RETRY = re.compile(r"stall idx=(\d+) — retrying once")
RE_AUTO_SKIP = re.compile(r"auto-skip (\d+)/(\d+) from idx=(\d+)")
RE_AUTO_SKIP_EXHAUSTED = re.compile(r"auto-skip exhausted")
RE_TERMINAL_RETRY = re.compile(r"terminal retry — re-arming scan idx=(\d+)")
RE_ICY = re.compile(r"\[webradio\] ICY: (.*)")
RE_REDIRECT = re.compile(r"redirect to new host \"([^\"]*)\"")
# ROM bootloader banner date is a fixed constant baked into the chip's boot
# ROM, not the actual calendar date -- literal match, copied from the
# already-validated pattern in test_adr045_gate.py, not reinvented.
RE_BOOT = re.compile(r"ets Jun  8 2016|rst:0x")


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def log(msg):
    print(f"[{_ts()}] {msg}", flush=True)


class SerialDut:
    """Continuous-reader serial DUT, matching test_adr045_gate.py's
    architecture -- one thread owns RX, tees every line to a raw log,
    parses known WebRadio event patterns into a structured timeline, and
    feeds JSON replies to cmd() via a queue. reset_input_buffer() is never
    called -- nothing between polls is ever silently discarded."""

    def __init__(self, port, raw_log_path, baud=115200):
        self.port, self.baud = port, baud
        self.ser = serial.Serial(port, baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False
        self.raw_log = open(raw_log_path, "a", buffering=1)
        self.replies = queue.Queue()
        self.events = []          # (host_ts, kind, dict) -- the structured timeline
        self.heartbeats = []      # (host_ts, heap_k, uptime_s, render_age_ms)
        self.boot_marks = []
        self.last_line_ts = time.time()  # any line at all, not just parsed ones --
                                          # second VE review finding 2's silence watchdog
        self.lock = threading.Lock()
        self._alive = True
        self._rx = threading.Thread(target=self._reader, daemon=True)
        self._rx.start()

    def _emit(self, kind, **fields):
        with self.lock:
            self.events.append((time.time(), kind, fields))

    def _reader(self):
        while self._alive:
            try:
                raw = self.ser.readline()
            except (serial.SerialException, OSError):
                time.sleep(0.2)
                continue
            if not raw:
                continue
            ts = time.time()
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            self.last_line_ts = ts
            self.raw_log.write(f"{ts:.3f}|{line}\n")

            m = RE_HEARTBEAT.search(line)
            if m:
                heap_k = int(m.group(1))
                uptime_s = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4))
                render_age_ms = int(m.group(5))
                with self.lock:
                    self.heartbeats.append((ts, heap_k, uptime_s, render_age_ms))
                continue
            m = RE_PLAY.search(line)
            if m:
                self._emit("play", idx=int(m.group(1)), name=m.group(2), url=m.group(3))
                continue
            if RE_CONNECT_OK.search(line):
                self._emit("connect_ok")
                continue
            m = RE_CONNECT_FAIL.search(line)
            if m:
                self._emit("connect_fail", idx=int(m.group(1)))
                continue
            m = RE_STREAM_DEAD.search(line)
            if m:
                self._emit("stream_dead", isRunning=int(m.group(1)),
                            runningForMs=int(m.group(2)), stalledForMs=int(m.group(3)))
                continue
            m = RE_STALL_RETRY.search(line)
            if m:
                self._emit("stall_retry", idx=int(m.group(1)))
                continue
            m = RE_AUTO_SKIP.search(line)
            if m:
                self._emit("auto_skip", tried=int(m.group(1)), count=int(m.group(2)),
                            fromIdx=int(m.group(3)))
                continue
            if RE_AUTO_SKIP_EXHAUSTED.search(line):
                self._emit("auto_skip_exhausted")
                continue
            m = RE_TERMINAL_RETRY.search(line)
            if m:
                self._emit("terminal_retry", idx=int(m.group(1)))
                continue
            m = RE_ICY.search(line)
            if m:
                self._emit("icy_title", title=m.group(1))
                continue
            m = RE_REDIRECT.search(line)
            if m:
                self._emit("redirect", to=m.group(1))
                continue
            if RE_BOOT.search(line):
                with self.lock:
                    self.boot_marks.append(ts)
                self._emit("boot_marker")
                continue

            if line.startswith("{"):
                try:
                    r = json.loads(line)
                    if isinstance(r, dict) and r.get("last", True):
                        self.replies.put((ts, r))
                except (json.JSONDecodeError, ValueError):
                    pass

    def cmd(self, s, timeout=3.0):
        while not self.replies.empty():
            try:
                self.replies.get_nowait()
            except queue.Empty:
                break
        self.ser.write((s + "\n").encode())
        self.ser.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                _, r = self.replies.get(timeout=0.2)
                return r
            except queue.Empty:
                continue
        return {}

    def boot_wait(self, timeout=45):
        for _ in range(40):
            if self.cmd("get appId", 2.0).get("name"):
                return True
            time.sleep(1.0)
        return False

    def recent_events(self, since_ts, kinds=None):
        with self.lock:
            evs = list(self.events)
        return [(ts, k, f) for ts, k, f in evs
                if ts >= since_ts and (kinds is None or k in kinds)]

    def recent_heartbeats(self, since_ts):
        with self.lock:
            return [h for h in self.heartbeats if h[0] >= since_ts]


def resolve_station_url(dut, name_hint):
    """One-shot: fetch the real station list, resolve name_hint to its
    actual url_resolved, so it can be injected as a fixed single station
    via `set wrUrl` -- guarantees wrIdx never drifts (see module docstring)."""
    cnt = dut.cmd("get wrCount", timeout=3.0).get("count", 0) or 0
    if cnt <= 0:
        return None, None, None
    stations = []
    for i in range(cnt):
        r = dut.cmd(f"get wrStation{i}", timeout=3.0)
        if "name" in r:
            stations.append((i, r["name"], r.get("url")))
    if not stations:
        return None, None, None
    if name_hint:
        for i, name, url in stations:
            if name_hint.lower() in name.lower():
                return i, name, url
        # Second VE review finding 4: this used to silently fall back to
        # idx 0 with just a WARN -- an unattended run could soak a
        # completely different station than intended (defeating the whole
        # point of pinning to TASK-393's exact repro target) with nobody
        # noticing until long after. The station list DID load successfully
        # here (this isn't a fetch failure the caller's retry loop should
        # keep hammering) -- fail loudly and immediately instead, matching
        # the wrAutoSkip-mismatch precedent elsewhere in this tool.
        available = ", ".join(repr(n) for _, n, _ in stations)
        log(f"FAIL: no station matched {name_hint!r} among {len(stations)} loaded. "
            f"Available: {available}")
        sys.exit(1)
    return stations[0]


def snapshot(dut):
    return {
        "ts": _ts(),
        "wrState": dut.cmd("get wrState", timeout=3.0),
        "wrIcy": dut.cmd("get wrIcy", timeout=3.0),
        "wrIdx": dut.cmd("get wrIdx", timeout=3.0),
        "wrSkip": dut.cmd("get wrSkip", timeout=3.0),
        "heap": dut.cmd("get heap", timeout=3.0),
        "stacks": dut.cmd("get stacks", timeout=3.0),
    }


def write_report(report_out, data):
    """Never let a report-write hiccup kill an otherwise-healthy multi-hour
    soak -- log and continue instead of raising."""
    try:
        Path(report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(report_out, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except OSError as e:
        log(f"WARN: report write to {report_out} failed: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--station-name", default="SLAM! DANCE CLASSICS",
                     help="substring to match against loaded station names "
                          "(default matches TASK-393's own live repro station "
                          "exactly; VE review finding 6 -- the old bare 'SLAM' "
                          "default could match any SLAM-family station, not "
                          "necessarily the one TASK-393 actually reproduced on)")
    ap.add_argument("--report-out", default=None,
                     help="path for the anomaly/final report JSON "
                          "(default: app/tools/rnd_logs/webradio_long_soak_<stamp>.json)")
    ap.add_argument("--raw-log", default=None,
                     help="path for the full raw serial log, every line, host-timestamped "
                          "(default: app/tools/rnd_logs/webradio_long_soak_<stamp>_raw.log)")
    ap.add_argument("--spotify-present", action="store_true",
                     help="skip the 'set bgPoll 0' belt-and-braces disable, leaving Spotify's "
                          "background polling active as a concurrent TLS user -- for testing "
                          "the concurrent-TLS-contention hypothesis both TASK-397 VE reviews "
                          "carried forward as unconfirmed (the one condition present in the "
                          "original human sighting that the noSpotify-build runs don't cover). "
                          "Requires the regular cyd2usb_winamp_debug build flashed (Spotify "
                          "enabled), not the noSpotify variant -- this tool does not flash "
                          "anything itself. TASK-243's Premium lapse means bgPoll will just be "
                          "continuous 403 retries rather than real playback polling; that's fine "
                          "for this purpose -- the TLS churn from repeated failed-auth attempts "
                          "is the same contention this hypothesis is about, not successful "
                          "Spotify playback.")
    args = ap.parse_args()

    # VE review finding 4: Python does NOT run atexit handlers on a bare
    # SIGTERM by default (only on normal interpreter exit / SIGINT). This
    # project has already hit a live incident where an external kill of a
    # predecessor tool bypassed its cleanup and reset the DUT (closing the
    # serial port drops DTR via the OS's hangup-on-close). Funnel SIGTERM
    # through sys.exit() so it takes the same path as normal completion and
    # DOES trigger the atexit-registered cleanup below. Defense-in-depth
    # only -- the actual project rule is still "never externally kill a
    # soak mid-flight"; this just makes an accidental kill less bad.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    stamp = time.strftime("%Y%m%dT%H%M%S")
    report_out = args.report_out or str(REPORT_DIR / f"webradio_long_soak_{stamp}.json")
    raw_log_path = args.raw_log or str(REPORT_DIR / f"webradio_long_soak_{stamp}_raw.log")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    log(f"connecting {args.port} … (raw log -> {raw_log_path})")
    dut = SerialDut(args.port, raw_log_path)
    if not dut.boot_wait():
        log("FAIL: shell did not become ready (WiFi up? debug build?)")
        sys.exit(1)

    # Belt-and-braces: `set bgPoll 0` in case this is running against a
    # regular cyd2usb_winamp_debug build rather than the recommended
    # cyd2usb_winamp_debug_noSpotify (see module docstring) -- Spotify's
    # background polling is a continuous competing TLS user that reliably
    # starved the WebRadio station-fetch's heap-contiguity guard (-101,
    # dataTaskStorage.cpp:1575) on a fresh boot this session, and bgPoll=0
    # alone did NOT reliably prevent that recurring (still hit -101 with it
    # set, in a later run) -- the noSpotify build is the real fix; this is
    # just defense-in-depth. VE review finding 5: verify, don't fire-and-forget.
    # (Second-pass review: this handler actually compiles in unconditionally
    # on the noSpotify build too -- DISABLE_SPOTIFY only guards the
    # spotifyTask::begin() call itself, not the dbgSet handler -- so this
    # WARN path shouldn't trigger in practice either way. Kept as a WARN
    # rather than fatal regardless, since it's genuinely non-essential now.)
    if args.spotify_present:
        log("--spotify-present: leaving bgPoll ON — Spotify's background polling stays active "
            "as a concurrent TLS user (testing the concurrent-TLS-contention hypothesis, not "
            "isolating the WebRadio-only mechanism)")
    else:
        log("set bgPoll 0 (belt-and-braces; primary isolation is the noSpotify build)")
        bgpoll_reply = dut.cmd("set bgPoll 0", timeout=2.0)
        if not bgpoll_reply.get("ok"):
            log(f"WARN: 'set bgPoll 0' did not confirm ok=true (got {bgpoll_reply!r}) — "
                f"expected on a noSpotify build (handler may not be compiled in); "
                f"continuing")

    orig_autoskip = None  # populated below, before we force it to 1; _cleanup
                          # reads this by closure at call time, not definition time

    def _cleanup():
        try:
            dut.cmd("set bgPoll 1", timeout=2.0)
            # Second VE review finding 5: wrAutoSkip was forced ON and never
            # restored -- harmless (RAM-only, no settingsSave) but stays
            # forced for the rest of that boot session, which matters if a
            # T237/T_WR_ERR_*-style test runs against the same live session
            # right after this soak exits.
            if orig_autoskip is not None:
                dut.cmd(f"set wrAutoSkip {orig_autoskip}", timeout=2.0)
            dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
        except Exception:
            pass
    atexit.register(_cleanup)

    log(f"entering WebRadio (switchApp {APP_SLOT['WebRadio']}) + resolving station list …")
    dut.cmd(f"switchApp {APP_SLOT['WebRadio']}", timeout=3.0)
    idx = name = url = None
    RETRY_BACKOFF_S = [5.0, 10.0]
    attempts = len(RETRY_BACKOFF_S) + 1
    for attempt in range(1, attempts + 1):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            r = dut.cmd("get wrCount", timeout=3.0)
            cnt = r.get("count", 0) or 0
            if cnt > 0:
                idx, name, url = resolve_station_url(dut, args.station_name)
                break
            if r.get("pending") == 0 and cnt == 0:
                break
            time.sleep(2.0)
        if url:
            break
        lh = dut.cmd("get wrLastHttp", timeout=3.0)
        if attempt > len(RETRY_BACKOFF_S):
            break
        backoff = RETRY_BACKOFF_S[attempt - 1]
        log(f"WARN: station fetch attempt {attempt}/{attempts} failed "
            f"(http={lh.get('http')} ok={lh.get('ok')} jsonErr={lh.get('jsonErr')!r}) — "
            f"waiting {backoff:.0f}s then re-triggering via leave/re-enter")
        time.sleep(backoff)
        dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
        time.sleep(1.0)
        dut.cmd(f"switchApp {APP_SLOT['WebRadio']}", timeout=3.0)
    if not url:
        log(f"FAIL: could not resolve a station URL after {attempts} attempts")
        sys.exit(1)

    log(f"resolved {name!r} (idx={idx}) -> {url}")

    # VE review finding 2 (blocking): the terminal-retry re-arm's OWN gate
    # condition (webRadioApp.h:623) requires g_settings.webRadioAutoSkip ==
    # true -- with _stationCount==1 the "skip to next station" branch never
    # applies, but the retry-recovery mechanism this whole soak exists to
    # stress is unconditionally disabled if autoSkip is false. It's a
    # persisted setting a prior debug session could have left off (T237/
    # T_WR_ERR_* tests flip it deliberately). test_adr045_gate.py sets this
    # explicitly before its trials; that line was dropped translating to
    # this tool. Force it on and verify, don't assume the default holds.
    orig_autoskip = dut.cmd("get wrSkip", timeout=3.0).get("autoSkip")
    dut.cmd("set wrAutoSkip 1", timeout=2.0)
    skip_check = dut.cmd("get wrSkip", timeout=3.0)
    if skip_check.get("autoSkip") != 1:
        log(f"FAIL: wrAutoSkip did not confirm ON after 'set wrAutoSkip 1' "
            f"(got {skip_check!r}) -- the terminal-retry mechanism under test "
            f"would never fire; aborting rather than running a meaningless soak")
        sys.exit(1)
    log("confirmed wrAutoSkip=1 (terminal-retry re-arm is live)")

    log(f"injecting as single station: set wrUrl {url}")
    wrurl_reply = dut.cmd(f"set wrUrl {url}", timeout=3.0)  # _stationCount -> 1
    if not wrurl_reply.get("ok"):
        log(f"WARN: 'set wrUrl' reply did not confirm ok=true (got {wrurl_reply!r}) — "
            f"continuing, but the injected station may not have taken")

    start = time.monotonic()
    start_wall = time.time()
    start_iso = _ts()
    end = start + args.hours * 3600

    anomaly_count = 0
    stuck_since = None            # mechanism-signal (event-log-based) stuck timer
    flagged_mechanism = False
    render_stuck_run = 0          # consecutive zero-repaint heartbeats
    flagged_render = False
    flagged_silence = False       # DUT-silence watchdog (second VE review finding 2)
    last_seen_event_ts = start_wall
    last_hb_seen_ts = start_wall
    last_render_age = None
    last_uptime = None
    poll_n = 0
    all_anomalies = []

    def elapsed():
        return round(time.monotonic() - start, 1)

    def full_report(status):
        return {"start": start_iso, "station": name, "idx": idx, "url": url,
                "status": status, "elapsed_s": elapsed(),
                "anomalies": all_anomalies, "raw_log": raw_log_path}

    log(f"soaking {name!r} for {args.hours:.1f}h — watching heartbeats + event log "
        f"(raw log: {raw_log_path})")

    last_checkpoint = time.monotonic()
    while time.monotonic() < end:
        time.sleep(2.0)  # cheap idle tick; all real signal comes from the reader thread

        # --- watchdog: total DUT silence (loopTask wedged, USB/serial dropped, etc.) ---
        # Distinct from the render-freeze signal: that one requires heartbeats to
        # keep arriving (frozen render, alive loopTask); this one catches the DUT
        # not talking to us AT ALL, the failure mode with no detector before.
        silent_for = time.time() - dut.last_line_ts
        if silent_for > DUT_SILENCE_THRESHOLD_S:
            if not flagged_silence:
                flagged_silence = True
                anomaly_count += 1
                log(f"  *** ANOMALY (DUT silence): no serial output at all for "
                    f"{silent_for:.0f}s (threshold {DUT_SILENCE_THRESHOLD_S:.0f}s) — "
                    f"loopTask wedged? USB/serial dropped? ***")
                all_anomalies.append({"ts": _ts(), "elapsed_s": elapsed(),
                                       "kind": "dut_silent", "silent_for_s": round(silent_for, 1)})
                write_report(report_out, full_report("anomaly-in-progress"))
        elif flagged_silence:
            flagged_silence = False
            log(f"  DUT silence resolved after {silent_for:.0f}s — lines arriving again")

        # --- primary signal: heartbeat render-age (the actual TASK-390/393 symptom) ---
        for hb_ts, heap_k, uptime_s, render_age_ms in dut.recent_heartbeats(last_hb_seen_ts):
            last_hb_seen_ts = hb_ts + 0.001
            if last_render_age is not None:
                d_render = render_age_ms - last_render_age
                d_uptime = uptime_s - last_uptime
                zero_repaint = (d_uptime > 0 and
                                 abs(d_render - d_uptime * 1000) <= RENDER_AGE_SLACK_MS)
                if zero_repaint:
                    render_stuck_run += 1
                else:
                    render_stuck_run = 0
                    flagged_render = False
                log(f"  hb: uptime={uptime_s}s heap={heap_k}k render_age={render_age_ms}ms "
                    f"{'(no repaint)' if zero_repaint else ''}")
                # VE review finding 1 (blocking): last_render_age_ms climbs in
                # lockstep with uptime during NORMAL steady PLAYING too, not
                # just while parked in an error state -- WebRadioApp's own
                # _dirty sites (marquee/buffer-bar/time-digits) are all
                # targeted blits, not repaintChrome(), once initial connect
                # settles. Zero-repaint alone is not the TASK-390/393
                # signature; gate on the DUT actually being in a retryable
                # error state, confirmed at the moment of the trip, or every
                # healthy run false-positives within ~2-3 minutes.
                if render_stuck_run >= RENDER_STUCK_HEARTBEATS and not flagged_render:
                    st_now = dut.cmd("get wrState", timeout=3.0).get("state")
                    if st_now in RETRYABLE_ERROR_STATES:
                        flagged_render = True
                        anomaly_count += 1
                        snap = snapshot(dut)
                        log(f"  *** ANOMALY (render-freeze signal): last_render_age_ms "
                            f"tracking uptime for {render_stuck_run} consecutive heartbeats "
                            f"(~{render_stuck_run * HEARTBEAT_PERIOD_S}s, zero repaints), "
                            f"state={st_now} ***")
                        all_anomalies.append({"ts": _ts(), "elapsed_s": elapsed(),
                                               "kind": "render_freeze",
                                               "consecutive_heartbeats": render_stuck_run,
                                               "render_age_ms": render_age_ms,
                                               "uptime_s": uptime_s, "state": st_now,
                                               "snapshot": snap})
                        write_report(report_out, full_report("anomaly-in-progress"))
                    # else: healthy quiet PLAYING/STOPPED with no repaints --
                    # expected, not an anomaly. Deliberately NOT latching
                    # flagged_render here: keep re-checking state on every
                    # subsequent heartbeat while zero_repaint persists, so a
                    # LATER transition into a stuck error state (without an
                    # intervening repaint in between) still gets caught. One
                    # extra `get wrState` per 30s heartbeat while quiet is
                    # negligible cost.
            last_render_age = render_age_ms
            last_uptime = uptime_s

        # --- secondary signal: event-log mechanism check (connect-fail/stream-dead
        #     with no observed recovery within WR_TERMINAL_RETRY_MS + slack) ---
        new_events = dut.recent_events(last_seen_event_ts)
        if new_events:
            last_seen_event_ts = new_events[-1][0] + 0.001
        for ts, kind, fields in new_events:
            if kind in ("connect_fail", "stream_dead", "auto_skip_exhausted"):
                if stuck_since is None:
                    stuck_since = ts
                    flagged_mechanism = False
                log(f"  event: {kind} {fields}")
            elif kind in ("play", "terminal_retry", "connect_ok", "stall_retry", "auto_skip"):
                stuck_since = None
                flagged_mechanism = False
                if kind == "play":
                    log(f"  event: {kind} {fields}")
            elif kind == "icy_title":
                log(f"  title: {fields['title']!r}")
            elif kind == "boot_marker":
                log("  *** DUT BOOT MARKER SEEN -- unexpected reset mid-soak ***")
                anomaly_count += 1
                all_anomalies.append({"ts": _ts(), "elapsed_s": elapsed(), "kind": "reboot"})
                write_report(report_out, full_report("anomaly-in-progress"))

        if stuck_since is not None and not flagged_mechanism:
            stuck_s = time.time() - stuck_since
            if stuck_s > (WR_TERMINAL_RETRY_MS / 1000.0 + STUCK_SLACK_S):
                flagged_mechanism = True
                anomaly_count += 1
                snap = snapshot(dut)
                log(f"  *** ANOMALY (mechanism signal): no recovery event for {stuck_s:.0f}s "
                    f"after a connect-fail/stream-dead (TASK-393 signature) ***")
                all_anomalies.append({"ts": _ts(), "elapsed_s": elapsed(),
                                       "kind": "mechanism_stuck", "stuck_s": round(stuck_s, 1),
                                       "snapshot": snap})
                write_report(report_out, full_report("anomaly-in-progress"))

        if time.monotonic() - last_checkpoint >= 300:  # 5 min
            last_checkpoint = time.monotonic()
            poll_n += 1
            st = dut.cmd("get wrState", timeout=3.0)
            idx_now = dut.cmd("get wrIdx", timeout=3.0)
            log(f"  alive: elapsed={elapsed():.0f}s state={st.get('state')} "
                f"idx={idx_now.get('idx')} anomalies={anomaly_count}")
            write_report(report_out, full_report("running"))

    final_status = "complete-dut-silent" if flagged_silence else "complete"
    log(f"soak complete: {elapsed():.0f}s elapsed, {anomaly_count} anomaly(ies), "
        f"status={final_status}")
    write_report(report_out, full_report(final_status))
    log(f"report written -> {report_out}")
    log(f"raw log -> {raw_log_path}")


if __name__ == "__main__":
    main()
