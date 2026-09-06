#!/usr/bin/env python3
"""lib/replay.py — record a DUT session, replay it against the real bodies.

TASK-628 / M-HARNESS2 R10 / DEV review §4.

WHAT THIS IS. Three things and nothing else:

  * a **recording transport** that sits under `Dut.ser` and writes down every
    command and the lines that answered it,
  * a **keyed store** — `(command, nth) -> lines` — that can drive a real `Dut`
    with no serial port anywhere in the process,
  * a **virtual clock**, so the suite's ~250 fixed sleeps cost nothing.

WHAT THIS IS NOT. It is **not** the mutation driver. Selecting which field to
mutate from R9's declared falsifier, running the control arm, and ratcheting the
recorded set are TASK-641/642/643, which are blocked behind this row. The
interface those rows get is stated in "THE INTERFACE LEFT TO 641/642/643" below
and is the only part of this module they should need.

── WHY A BYTE-LEVEL RECORDER AND NOT A `Dut.cmd` WRAPPER ─────────────────────

The DEV review costed this as "a recording wrapper on `Dut.cmd` — ~50 lines",
and noted in the same breath that `send()`/`read_json()` are called directly by
the suite and that `drain_log_lines` reads unsolicited lines with no command at
all, so a second unkeyed channel would be needed. Both problems disappear at the
transport. `lib/dut.py` has exactly **one** write choke point (`send` ->
`ser.write`) and exactly **one** read choke point (`ser.readline`) — `cmd`,
`cmd_drain`, `read_json`, `read_json_multi`, `read_reply`, `get_int/str/bool/
float/val`, `set_val`, `wait_shell_cooldown_clear`, `drain_log_lines` and the
`saved`/`injected` managers all funnel through them. Recording there covers
every one of those paths with no per-method wrapper, no list of methods to keep
in sync, and no separate unkeyed channel: unsolicited log lines are simply the
lines that arrive after a command and before the next one.

It also means the REAL `Dut` runs in replay. That is the lesson of
`spike/task584_residue_verdicts.py` and it is the whole reason the replay says
anything: `read_reply`'s correlation, the `NoAnswer`/`BadField` split and the
typed accessors all execute their production code. A fake `Dut` would prove the
fake agrees with itself.

── THE KEYED STORE, AND WHY POSITIONAL IS WRONG ──────────────────────────────

DEV §4.1's amendment, which this module is built to: these bodies **branch on
earlier replies**. `_switch_to`, `_wait_chart_complete`, `_tb_set_offset` and
`_stock_ok_count` all decide what to send next from what came back. Mutate a
reply and the body legitimately takes a different path — that is the point of
mutation — and a positional transcript then hands reply #7 to command #7 when
the body is now asking a different question. The reply is *plausible* and
*wrong*, and the run is silently meaningless.

So the key is `(command string, nth occurrence of that command)`. A body that
takes the same path gets exactly what it recorded; a body that branches
elsewhere either finds the command it now needs (because some other path
recorded it) or does not — and "does not" is a **transcript miss**, which is
never a verdict.

── A TRANSCRIPT MISS IS INCONCLUSIVE, NEVER A CONFIRMATION ───────────────────

This is the failure the whole M-HARNESS2 programme exists to stop, one layer up,
and DEV §4.1 point 2 says so explicitly: if a miss is recorded as a FAIL, the
mutation job reports an id as falsifiable when what actually happened is that
the recording was incomplete, and the acceptance number is manufactured.

Three mechanisms enforce it here, not one comment:

  1. `Status.INCONCLUSIVE` is a member of a closed enum on every `ReplayResult`,
     orthogonal to the body's verdict. There is no way to obtain a result
     without one.
  2. `confirmations()` is the ONLY sanctioned way to count, and it refuses to
     count a row whose status is not `OK`. `ReplayResult.is_confirmation` is a
     property, not a convention.
  3. `TranscriptMiss` derives from **`BaseException`**, not `Exception`. Test
     bodies and their helpers contain bare `except Exception:` arms; if a miss
     were an `Exception`, a body could swallow it and then `pass_()` itself on a
     reply it never received. That would be the manufactured-confirmation defect
     reintroduced inside the tool built to detect it.

── STALENESS ─────────────────────────────────────────────────────────────────

A recording is only valid against the firmware it was taken from (DEV §4.3's
"transcripts rot"). Every transcript is stamped with the ELF id `lib/dut.py`
already reads in `_verify_debug_firmware` (`firmware.bin[176:180]`), and
`replay_test` refuses to interpret a body run against a transcript whose stamp
does not match the currently built firmware. Refuses — `INCONCLUSIVE` with a
re-record instruction, never a FAIL. A stale transcript turning the job red for
a reason unrelated to the tests is how a gate becomes noise, and noise on a gate
is how C3 got where it is.

The "I cannot tell" case is loud too: no built `firmware.bin` in the tree means
the expected ELF is unknown, and that is `INCONCLUSIVE(elf-unknown)`, not a
silent assumption of freshness. `REPLAY_ELF=<hex>` names it explicitly;
`elf_check=False` waives it and STAMPS the waiver on the result, so a waived run
can never be read back as a checked one.

── THE VIRTUAL CLOCK ─────────────────────────────────────────────────────────

253 `time.sleep` calls, ~100 s of pure sleeping per pass, and the mutation job
runs at least two passes per id. A replay that honours real time is a replay
nobody runs. `virtual_time()` patches `time.sleep`/`time.monotonic` on the
stdlib module, so every `import time` in `lib/` and in the suite sees it.

The honesty problem — "do not let a test that genuinely depends on elapsed time
silently pass" — is answered by a second pass rather than by hope. A replay can
only honestly speak about verdicts that the TRANSCRIPT determines. So
`replay_test` runs the body twice by default: once with sleeps advancing the
clock by exactly what was asked (`dilation=1.0`) and once with sleeps advancing
it by nothing (`dilation=0.0`). If the verdict differs, the body's verdict
depends on host elapsed time that the transcript does not encode, and the id is
reported `INCONCLUSIVE(time-dependent)` — not passed, not failed. Cost: one more
pass with no I/O in it.

Idle reads always advance the clock by `IDLE_STEP` regardless of dilation. They
have to: `while time.monotonic() < deadline` is the shape of every read loop in
`dut.py`, and a clock frozen at 0 would hang them rather than time them out.

── THE INTERFACE LEFT TO 641/642/643 ─────────────────────────────────────────

    Transcript.load(path) / .save(path)      the store, ELF-stamped
    Transcript.keys()                        every (cmd, nth) it holds
    Transcript.mutate(pred, fn) -> Transcript   a COPY with fields rewritten
    replay_test(tid, body, transcript, ...) -> ReplayResult
    ReplayResult.is_confirmation             False for every INCONCLUSIVE
    confirmations(results)                   the only sanctioned count

TASK-641 generates the read-key set and the author's claim class; TASK-642 turns
that into a named falsifier field; TASK-643 is the driver: for each id it calls
`replay_test` three times — baseline (expect PASS), `mutate` the falsifier's key
(expect FAIL), `mutate` a key the test reads but should not depend on (expect
PASS, R10a's control arm) — and **voids the id entirely if any arm is not `OK`**.
This module deliberately does not decide which key is which; that is a claim
about the test's vocabulary and it belongs with the falsifier declaration.

── TASK-631: THE LAST 20 EXCHANGES ON A FAIL ─────────────────────────────────

`FailRing` is the same recorder in a second mode: a `deque(maxlen=20)` instead
of a full transcript, installed on a REAL run, snapshotted into the artifact
when a blocking verdict is recorded. See `FailRing` and `results.py`'s
`set_exchange_provider`.
"""

from __future__ import annotations

import collections
import contextlib
import copy
import enum
import json
import os
import pathlib
import re
import threading
import time as _time_mod

#: Bumped when the on-disk transcript layout changes meaning. A transcript at an
#: unknown version is INCONCLUSIVE for exactly the reason a stale one is.
TRANSCRIPT_SCHEMA = 1

#: Virtual seconds an idle read costs. Small enough that a 3 s window still
#: takes many reads (so a body polling a device model sees several samples),
#: large enough that a 30 s timeout does not need 3000 iterations.
IDLE_STEP = 0.01

#: The maximum exchanges a FailRing carries (TASK-631: "the last 20").
RING_LEN = 20


# ── errors ───────────────────────────────────────────────────────────────────

class ReplayError(Exception):
    """Base for the engine's own refusals (not for a body's verdict)."""


class StaleTranscript(ReplayError):
    """The transcript was recorded against different firmware.

    Its own class because its handling differs from every other refusal: the
    action is `re-record`, not `fix the test`, and reporting it as a FAIL is the
    documented way this job turns into noise (DEV §4.3).
    """


class TranscriptMiss(BaseException):
    """The body asked something the recording does not answer.

    **`BaseException` on purpose.** Bodies and helpers in the suite contain bare
    `except Exception:` arms. A miss that a body can catch is a miss that a body
    can turn into a `pass_()` on a reply it never received — a manufactured
    confirmation, inside the mechanism built to detect manufactured
    confirmations (DEV §4.1 point 2). Nothing in the suite catches
    `BaseException`, so this reaches `replay_test` intact.
    """

    def __init__(self, cmd: str, nth: int, recorded: int, tid: str = ""):
        self.cmd, self.nth, self.recorded, self.tid = cmd, nth, recorded, tid
        if recorded:
            detail = (f"recorded {recorded} time(s), this replay asked for "
                      f"#{nth + 1} — the body took a path the recording does "
                      f"not cover")
        else:
            detail = ("never recorded at all — the body branched somewhere the "
                      "recording never went")
        super().__init__(f"no recorded reply for {cmd!r} #{nth}: {detail}")


# ── outcome vocabulary ───────────────────────────────────────────────────────

class Status(enum.Enum):
    """Did this replay produce a result that may be counted?

    Closed, two-valued, and carried on every `ReplayResult`. A caller cannot
    obtain a result without one, which is the whole point: `INCONCLUSIVE` is a
    value in the data, not a note in a log line.
    """

    OK = "OK"
    INCONCLUSIVE = "INCONCLUSIVE"


class Reason(enum.Enum):
    """Why a replay was INCONCLUSIVE. `NONE` iff status is OK."""

    NONE = "-"
    #: the body asked for something the recording does not have
    TRANSCRIPT_MISS = "transcript-miss"
    #: recorded against different firmware — re-record, do not debug
    STALE_TRANSCRIPT = "stale-transcript"
    #: no built firmware.bin to compare against; freshness is unknown
    ELF_UNKNOWN = "elf-unknown"
    #: the verdict changed when sleeps stopped advancing the clock
    TIME_DEPENDENT = "time-dependent"
    #: nothing was ever recorded for this id
    NO_TRANSCRIPT = "no-transcript"
    #: the body blocks on input(); not replayable at all (T093, T095)
    INTERACTIVE = "interactive"
    #: the body wrote no verdict, or the engine itself broke
    NO_VERDICT = "no-verdict"
    ENGINE_ERROR = "engine-error"


class ReplayResult:
    """One replay of one id. Immutable in practice; compared by nothing."""

    __slots__ = ("tid", "status", "reason", "detail", "verdict", "record",
                 "used", "recorded", "slept_s", "wall_s", "elf_checked",
                 "time_probe", "tail_miss")

    #: What the dilation-0 arm was able to say. `agreed` — the verdict does not
    #: move when sleeps stop advancing the clock. `flipped` — it does, and the
    #: row is INCONCLUSIVE(time-dependent). `undecided` — that arm hit a miss of
    #: its own, because the body's COMMAND SEQUENCE depends on elapsed time (a
    #: poll loop's iteration count does, and that is ubiquitous and harmless);
    #: no evidence either way, and it is recorded as no evidence rather than
    #: quietly read as agreement. `off` — not probed.
    time_probe: str

    def __init__(self, tid, status, reason=Reason.NONE, detail="", verdict=None,
                 record="", used=0, recorded=0, slept_s=0.0, wall_s=0.0,
                 elf_checked=True, time_probe="off", tail_miss=False):
        self.time_probe = time_probe
        self.tail_miss = tail_miss
        self.tid, self.status, self.reason, self.detail = (
            tid, status, reason, detail)
        self.verdict, self.record = verdict, record
        self.used, self.recorded = used, recorded
        self.slept_s, self.wall_s = slept_s, wall_s
        self.elf_checked = elf_checked

    @property
    def is_confirmation(self) -> bool:
        """May this row be counted as evidence about the test?

        A property and not a convention. The only `True` is a replay that ran to
        a verdict on a transcript whose freshness was CHECKED — a waived ELF
        check is not a confirmation either, because "we did not look" and "we
        looked and it matched" must not read the same downstream.
        """
        return self.status is Status.OK and self.elf_checked

    def __repr__(self):
        v = getattr(self.verdict, "value", self.verdict)
        tail = f" [{self.reason.value}]" if self.status is Status.INCONCLUSIVE else ""
        return f"<{self.tid} {self.status.value} verdict={v}{tail}>"

    def line(self) -> str:
        v = getattr(self.verdict, "value", self.verdict) or "-"
        if self.status is Status.INCONCLUSIVE:
            return (f"  {self.tid:12s} INCONCLUSIVE  {self.reason.value:18s} "
                    f"{self.detail}")
        w = "" if self.elf_checked else "  (ELF CHECK WAIVED — not a confirmation)"
        t = "  tail-miss(teardown not recorded)" if self.tail_miss else ""
        return (f"  {self.tid:12s} OK            verdict={v:9s} "
                f"{self.used}/{self.recorded} exchanges{w}{t}")


def confirmations(results) -> int:
    """The ONLY sanctioned count over a set of `ReplayResult`s.

    Exists so that no caller ever writes `len(results)` and calls it an
    acceptance number. An INCONCLUSIVE row is not a smaller confirmation; it is
    not a confirmation.
    """
    return sum(1 for r in results if r.is_confirmation)


def summarize(results) -> str:
    ok = confirmations(results)
    inc = [r for r in results if not r.is_confirmation]
    by = collections.Counter(
        r.reason.value if r.status is Status.INCONCLUSIVE else "elf-waived"
        for r in inc)
    out = [f"{ok} confirmed, {len(inc)} INCONCLUSIVE of {len(results)}"]
    for k, n in sorted(by.items()):
        out.append(f"    {n:3d}  {k}")
    return "\n".join(out)


# ── the virtual clock ────────────────────────────────────────────────────────

class VirtualClock:
    """A monotonic counter that `sleep` advances instead of waiting.

    `dilation` scales explicit sleeps only — 1.0 is faithful, 0.0 is the probe
    arm (see the module docstring). Idle reads advance the clock unconditionally
    through `tick()`, because every read loop in `dut.py` is bounded by
    `time.monotonic()` and a frozen clock hangs rather than times out.
    """

    def __init__(self, t0: float = 1000.0, dilation: float = 1.0):
        self.t = float(t0)
        self.dilation = float(dilation)
        self.slept_s = 0.0
        self.sleeps = 0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, d) -> None:
        d = max(0.0, float(d))
        self.sleeps += 1
        self.slept_s += d
        self.t += d * self.dilation

    def tick(self, d: float = IDLE_STEP) -> None:
        self.t += d


@contextlib.contextmanager
def virtual_time(clock: VirtualClock):
    """Patch `time.sleep`/`time.monotonic` for the duration.

    Module-level patching, as `spike/task584_residue_verdicts.py` does, because
    the suite and `lib/dut.py` both do `import time` and hold no reference this
    could be injected into. `time.time()` is deliberately NOT patched: nothing in
    the replayed paths uses wall-clock time for anything but a log stamp, and a
    patched wall clock would make timestamps in a recording lie.
    """
    real_sleep, real_mono = _time_mod.sleep, _time_mod.monotonic
    _time_mod.sleep, _time_mod.monotonic = clock.sleep, clock.monotonic
    try:
        yield clock
    finally:
        _time_mod.sleep, _time_mod.monotonic = real_sleep, real_mono


# ── redaction (TASK-631) ─────────────────────────────────────────────────────

#: Reply keys whose VALUE never enters a transcript or a fail-ring. Defensive:
#: measured zero hits across the current corpus and the current `cmdGet.cpp`
#: surface (the firmware already prints `pwlen`, not the password). It is here
#: because the cost of the rule is a regex and the cost of its absence is a
#: credential in a JSON file somebody attaches to a task.
_SECRET_KEY_RE = re.compile(
    r"(?i)(pass|passwd|password|pwd|psk|secret|token|refresh|bearer|"
    r"clientid|client_id|apikey|api_key|credential)")

#: Command PREFIXES whose arguments are replaced wholesale.
_SECRET_CMD_RE = re.compile(
    r"(?i)^(set|setcfg|wifi)\s+\S*(pass|pw|psk|secret|token|key)\S*\s+")


def redact_cmd(cmd: str) -> str:
    m = _SECRET_CMD_RE.match(cmd or "")
    return (m.group(0) + "<redacted>") if m else cmd


def redact_line(line: str) -> str:
    """Redact secret-looking fields in a JSON reply line; pass others through."""
    s = (line or "").strip()
    if not s.startswith("{"):
        return line
    try:
        obj = json.loads(s)
    except (ValueError, json.JSONDecodeError):
        return line
    if not isinstance(obj, dict):
        return line
    hit = False
    for k in list(obj):
        if _SECRET_KEY_RE.search(str(k)):
            obj[k], hit = "<redacted>", True
    return json.dumps(obj) if hit else line


# ── the store ────────────────────────────────────────────────────────────────

class Transcript:
    """`(command, nth) -> [reply line, ...]` for one test id, ELF-stamped.

    `preamble` holds lines that arrived before the first command — the boot
    chatter and anything a previous test left on the wire. It is replayed
    first-come, unkeyed, which is the second channel DEV §4.1 point 1 asks for.
    """

    def __init__(self, tid: str, elf=None, build_env=None, recorded_at=None,
                 gen=None):
        self.tid = tid
        self.elf = elf
        self.build_env = build_env
        self.recorded_at = recorded_at
        self.gen = gen
        self.preamble: list = []
        #: (cmd, nth) -> [line, ...]. Ordered by insertion, which is record order.
        self.exchanges: dict = {}

    # -- building -----------------------------------------------------------

    def add(self, cmd: str, lines: list) -> tuple:
        nth = sum(1 for (c, _n) in self.exchanges if c == cmd)
        key = (cmd, nth)
        self.exchanges[key] = list(lines)
        return key

    def keys(self) -> list:
        return list(self.exchanges)

    def count_of(self, cmd: str) -> int:
        return sum(1 for (c, _n) in self.exchanges if c == cmd)

    def get(self, cmd: str, nth: int) -> list:
        """-> the recorded lines, or raise `TranscriptMiss`."""
        try:
            return self.exchanges[(cmd, nth)]
        except KeyError:
            raise TranscriptMiss(cmd, nth, self.count_of(cmd), self.tid) from None

    # -- mutation (the primitive TASK-643 drives; NOT the driver) -----------

    def mutate(self, pred, fn) -> "Transcript":
        """A COPY with every JSON reply line matching `pred` rewritten by `fn`.

        `pred(cmd, nth, obj) -> bool`; `fn(obj) -> obj` mutates a decoded reply
        dict in place or returns a new one. A copy and never in place, because a
        driver that mutates its baseline has no baseline — and the control arm
        (R10a) needs both from the same recording.

        This is a store operation. Choosing WHICH key to mutate is a claim about
        the test's vocabulary and belongs to TASK-641/642's falsifier
        declaration, not here.
        """
        out = Transcript(self.tid, self.elf, self.build_env, self.recorded_at,
                         self.gen)
        out.preamble = list(self.preamble)
        n = 0
        for (cmd, nth), lines in self.exchanges.items():
            new = []
            for ln in lines:
                s = (ln or "").strip()
                if s.startswith("{"):
                    try:
                        obj = json.loads(s)
                    except (ValueError, json.JSONDecodeError):
                        new.append(ln)
                        continue
                    if isinstance(obj, dict) and pred(cmd, nth, obj):
                        obj = fn(copy.deepcopy(obj)) or obj
                        n += 1
                        new.append(json.dumps(obj))
                        continue
                new.append(ln)
            out.exchanges[(cmd, nth)] = new
        out.mutations = n                                  # noqa: B010 (info)
        return out

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema": TRANSCRIPT_SCHEMA,
            "id": self.tid,
            "elf": self.elf,
            "build_env": self.build_env,
            "recorded_at": self.recorded_at,
            "generation": self.gen,
            "preamble": self.preamble,
            "exchanges": [{"cmd": c, "nth": n, "lines": v}
                          for (c, n), v in self.exchanges.items()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        got = d.get("schema")
        if got != TRANSCRIPT_SCHEMA:
            raise StaleTranscript(
                f"transcript schema {got!r}, this engine knows "
                f"{TRANSCRIPT_SCHEMA} — re-record; guessing at a layout is how "
                f"a replay answers a question it did not understand")
        t = cls(d.get("id"), d.get("elf"), d.get("build_env"),
                d.get("recorded_at"), d.get("generation"))
        t.preamble = list(d.get("preamble") or [])
        for e in d.get("exchanges") or []:
            t.exchanges[(e["cmd"], int(e["nth"]))] = list(e.get("lines") or [])
        return t

    def save(self, path) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".part")
        tmp.write_text(json.dumps(self.to_dict(), indent=1) + "\n")
        tmp.replace(p)
        return p

    @classmethod
    def load(cls, path) -> "Transcript":
        return cls.from_dict(json.loads(pathlib.Path(path).read_text()))


# ── the ELF stamp ────────────────────────────────────────────────────────────

def current_elf_expected(build_env=None):
    """The ELF id of the firmware currently BUILT in the tree, or None.

    The same four bytes `lib/dut.py:_verify_debug_firmware` compares against the
    board — one source, not a second reading of the same fact (LL-114).
    `REPLAY_ELF` overrides for a host with no build directory.
    """
    env_elf = os.environ.get("REPLAY_ELF")
    if env_elf:
        return env_elf.strip().lower()
    env = build_env or os.environ.get("DUT_ENV") or "cyd2usb_winamp_debug"
    fw = (pathlib.Path(__file__).resolve().parents[1] / ".pio" / "build" / env
          / "firmware.bin")
    if not fw.exists():
        return None
    try:
        return fw.read_bytes()[176:180].hex()
    except OSError:
        return None


# ── the transports ───────────────────────────────────────────────────────────

class RecordingSerial:
    """Wraps a live `Dut.ser`, writing each command and its replies down.

    Transparent: everything it does not define is delegated, so it composes over
    `_TeeSerial` (and would compose over a raw `serial.Serial`) without knowing
    anything about either.
    """

    def __init__(self, inner, tid: str = "", redact: bool = True):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_redact", redact)
        object.__setattr__(self, "transcript", Transcript(tid))
        object.__setattr__(self, "_cur", None)     # (cmd, [lines]) or None

    # -- the two choke points ----------------------------------------------

    def write(self, b):
        self._flush_exchange()
        cmd = b.decode(errors="replace").strip()
        if self._redact:
            cmd = redact_cmd(cmd)
        object.__setattr__(self, "_cur", (cmd, []))
        return self._inner.write(b)

    def readline(self):
        raw = self._inner.readline()
        line = raw.decode(errors="replace").strip()
        if line:                        # idle reads carry nothing; see IDLE_STEP
            if self._redact:
                line = redact_line(line)
            if self._cur is None:
                self.transcript.preamble.append(line)
            else:
                self._cur[1].append(line)
        return raw

    # -- lifecycle ----------------------------------------------------------

    def _flush_exchange(self):
        if self._cur is not None:
            self.transcript.add(self._cur[0], self._cur[1])
            object.__setattr__(self, "_cur", None)

    def finish(self) -> Transcript:
        self._flush_exchange()
        return self.transcript

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_inner"), name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


class StubTransport:
    """Drives a real `Dut` from a `Transcript`. No port, no device, no bytes.

    A byte-level stand-in with `write`/`flush`/`readline`, exactly the surface
    `lib/dut.py` uses — so `cmd`, `read_reply`, the accessors, the correlation
    loop and the `NoAnswer`/`BadField` split all run production code.
    """

    def __init__(self, transcript: Transcript, clock: VirtualClock):
        self.t = transcript
        self.clock = clock
        self.out = collections.deque(str(x) for x in transcript.preamble)
        self.seen: dict = collections.Counter()
        self.used = 0

    def write(self, b):
        cmd = b.decode(errors="replace").strip()
        nth = self.seen[cmd]
        self.seen[cmd] += 1
        lines = self.t.get(cmd, nth)          # raises TranscriptMiss
        self.used += 1
        self.out.extend(str(x) for x in lines)
        return len(b)

    def flush(self):
        pass

    def readline(self):
        if self.out:
            return (self.out.popleft() + "\n").encode()
        # A quiet line. Advance the clock so the caller's deadline is reachable
        # instead of spinning: every read loop in dut.py is monotonic-bounded.
        self.clock.tick()
        return b""

    # `Dut` reads no other attribute off `ser` on the replayed paths; anything
    # it might add later should fail loudly rather than silently return a Mock.
    def close(self):
        pass


def make_replay_dut(transcript: Transcript, clock: VirtualClock):
    """A REAL `lib.dut.Dut` with a `StubTransport` under it.

    `object.__new__` and not `Dut(...)`: the constructor opens a port, waits for
    a boot and verifies firmware. Bypassing it is the point — the precedent is
    `spike/task584_residue_verdicts.py:make_dut`, and what matters is that every
    METHOD is the production one.
    """
    from .dut import Dut
    d = object.__new__(Dut)
    d.ser = StubTransport(transcript, clock)
    d._owner_thread = threading.current_thread()
    d.port = "replay"
    d.elf = transcript.elf
    d.elf_expected = transcript.elf
    d.build_env = transcript.build_env
    d._last_phase = None
    return d


# ── the replay ───────────────────────────────────────────────────────────────

def _run_once(tid, body, transcript, dilation):
    """One pass. -> (verdict, record, used, clock, miss|None, error|None)."""
    from . import results as R
    clock = VirtualClock(dilation=dilation)
    saved_results = dict(R.RESULTS), dict(R.VERDICTS)
    R.RESULTS.clear()
    dut = make_replay_dut(transcript, clock)
    miss = err = None
    try:
        with virtual_time(clock):
            try:
                body(dut)
            except TranscriptMiss as e:      # BaseException — see its docstring
                miss = e
            except Exception as e:           # noqa: BLE001 — a body's own crash
                err = e
        verdict, record = R.VERDICTS.get(tid), R.RESULTS.get(tid, "")
    finally:
        R.RESULTS.clear()
        for k, v in saved_results[0].items():
            R.RESULTS.set_typed(k, saved_results[1][k], v)
    return verdict, record, dut.ser.used, clock, miss, err


def replay_test(tid: str, body, transcript: Transcript, *,
                elf_check: bool = True, expected_elf=None,
                probe_time: bool = True,
                strict_tail: bool = False) -> ReplayResult:
    """Run `body` against `transcript` with no device. -> `ReplayResult`.

    `body` is a suite body taking one `dut` argument — obtained by the CALLER
    from `build_all_tests()`. This module never imports a suite (M-TOOLING §3).

    Ordering of the refusals is deliberate: freshness first (a stale transcript
    makes every later signal meaningless), then the miss, then the body's own
    crash, then the time probe. The first refusal wins and names itself.
    """
    from . import results as R                                   # noqa: F401

    n_rec = len(transcript.exchanges)
    if n_rec == 0 and not transcript.preamble:
        return ReplayResult(tid, Status.INCONCLUSIVE, Reason.NO_TRANSCRIPT,
                            "nothing was recorded for this id", recorded=0)

    checked = True
    if elf_check:
        want = expected_elf if expected_elf is not None else current_elf_expected(
            transcript.build_env)
        if want is None:
            return ReplayResult(
                tid, Status.INCONCLUSIVE, Reason.ELF_UNKNOWN,
                "no built firmware.bin to compare the transcript's stamp "
                "against (build the debug env, or set REPLAY_ELF) — freshness "
                "unknown is not freshness", recorded=n_rec)
        if (transcript.elf or "").lower() != str(want).lower():
            return ReplayResult(
                tid, Status.INCONCLUSIVE, Reason.STALE_TRANSCRIPT,
                f"recorded against elf {transcript.elf!r}, tree builds "
                f"{want!r} — RE-RECORD this transcript. A stale transcript is "
                f"not a failing test.", recorded=n_rec)
    else:
        checked = False

    t_wall = _time_mod.monotonic()
    verdict, record, used, clock, miss, err = _run_once(
        tid, body, transcript, 1.0)
    wall = round(_time_mod.monotonic() - t_wall, 4)

    # A MISS BEFORE THE VERDICT VOIDS THE ROW; A MISS AFTER IT DOES NOT.
    #
    # This distinction is not in DEV §4 and the engine does not work without it.
    # Measured on the real `T_MA_03`: the FAIL branch calls `_restore_spotify`
    # and the UNMET branch calls it too, so the command TAIL after a verdict is
    # different on every path — a transcript recorded from a healthy board can
    # essentially never cover it. Voiding on a tail miss would make every
    # falsification INCONCLUSIVE and the whole mechanism would report nothing.
    #
    # It is not the hole DEV §4.1 point 2 warns about, and the difference is
    # exactly where the verdict came from. A miss BEFORE the verdict means the
    # body never asserted anything and any verdict would be manufactured — void.
    # A miss AFTER means `fail()`/`pass_()` was already called, on replies that
    # WERE recorded; what is missing is teardown, which asserts nothing. The row
    # is flagged (`tail_miss`) and printed, so a stricter driver can demand full
    # coverage with `strict_tail=True` rather than having the choice made here.
    tail_only = miss is not None and verdict is not None and not strict_tail
    if miss is not None and not tail_only:
        return ReplayResult(tid, Status.INCONCLUSIVE, Reason.TRANSCRIPT_MISS,
                            str(miss), used=used, recorded=n_rec,
                            slept_s=clock.slept_s, wall_s=wall,
                            elf_checked=checked)
    if err is not None and not tail_only:
        # The body raised. That is data about the body, not about the engine —
        # but it is not a verdict either, and a driver must not count it.
        return ReplayResult(tid, Status.INCONCLUSIVE, Reason.ENGINE_ERROR,
                            f"{type(err).__name__}: {err}", used=used,
                            recorded=n_rec, slept_s=clock.slept_s, wall_s=wall,
                            elf_checked=checked)
    if verdict is None:
        return ReplayResult(tid, Status.INCONCLUSIVE, Reason.NO_VERDICT,
                            "the body recorded no verdict for its own id",
                            used=used, recorded=n_rec, slept_s=clock.slept_s,
                            wall_s=wall, elf_checked=checked)

    probe = "off"
    if probe_time:
        v2, _r2, _u2, _c2, miss2, err2 = _run_once(tid, body, transcript, 0.0)
        if miss2 is not None or err2 is not None or v2 is None:
            probe = "undecided"
        elif v2 is not verdict:
            return ReplayResult(
                tid, Status.INCONCLUSIVE, Reason.TIME_DEPENDENT,
                f"verdict {getattr(verdict, 'value', verdict)} with sleeps "
                f"advancing the clock, {getattr(v2, 'value', v2)} without — "
                f"this id's verdict rests on host elapsed time the transcript "
                f"does not encode", used=used, recorded=n_rec,
                slept_s=clock.slept_s, wall_s=wall, elf_checked=checked,
                time_probe="flipped")
        else:
            probe = "agreed"

    return ReplayResult(tid, Status.OK, Reason.NONE, "", verdict=verdict,
                        record=record, used=used, recorded=n_rec,
                        slept_s=clock.slept_s, wall_s=wall, elf_checked=checked,
                        time_probe=probe, tail_miss=tail_only)


# ── recording on a live run ──────────────────────────────────────────────────

@contextlib.contextmanager
def recording(dut, tid: str = "", redact: bool = True):
    """Record one id's session off a live `Dut`. Yields the `RecordingSerial`.

    Restores the original transport on the way out even if the body raised, so a
    failed recording cannot leave the session wrapped for the next test.
    """
    inner = dut.ser
    rec = RecordingSerial(inner, tid, redact=redact)
    dut.ser = rec
    try:
        yield rec
    finally:
        rec.finish()
        dut.ser = inner
    stamp = getattr(dut, "elf", None) or getattr(dut, "elf_expected", None)
    rec.transcript.elf = stamp
    rec.transcript.build_env = getattr(dut, "build_env", None)
    rec.transcript.gen = dut.gen_tag() if hasattr(dut, "gen_tag") else None
    rec.transcript.recorded_at = _time_mod.strftime(
        "%Y-%m-%dT%H:%M:%SZ", _time_mod.gmtime())


# ── TASK-631: the last 20 exchanges behind a FAIL ────────────────────────────

class FailRing:
    """The recorder in ring mode: the last `RING_LEN` exchanges, session-wide.

    WHY A RING AND NOT A TRANSCRIPT. A full recording of a `run/test` pass is
    tens of thousands of exchanges held in RAM for the whole run, and 195 of them
    written into an artifact that triage reads twenty lines of. The ring holds a
    bounded 20; the append is O(1) and the eviction is free.

    WHY SESSION-WIDE AND NOT PER-ID. A body that issued fewer than 20 commands
    would otherwise pad its context with nothing, when the most useful lines are
    exactly the ones from the test BEFORE it — the arming test, in every
    state-residue finding this programme has. Each entry carries the id it
    happened under, so a cross-boundary read is visible rather than implied.

    COST ON A GREEN RUN. One `deque.append` of a small tuple per command, and
    NOTHING else: `snapshot()` is called only from `results.set_typed` for a
    blocking verdict, so a run with no FAIL and no UNMET never builds a single
    context payload. Measured in `lib/test_replay.py`.
    """

    def __init__(self, maxlen: int = RING_LEN, redact: bool = True):
        self.buf = collections.deque(maxlen=maxlen)
        self.redact = redact
        self.tid = ""
        self._cur = None
        self._n = 0

    # -- the transport wrapper ---------------------------------------------

    def wrap(self, dut):
        """Install on a live `Dut`. -> the ring, for `set_exchange_provider`."""
        ring = self

        class _RingSerial(RecordingSerial):
            def write(self, b):
                ring._start(b.decode(errors="replace").strip())
                return object.__getattribute__(self, "_inner").write(b)

            def readline(self):
                raw = object.__getattribute__(self, "_inner").readline()
                line = raw.decode(errors="replace").strip()
                if line:
                    ring._line(line)
                return raw

        dut.ser = _RingSerial(dut.ser, redact=False)
        return self

    def _start(self, cmd):
        self._commit()
        if self.redact:
            cmd = redact_cmd(cmd)
        self._n += 1
        self._cur = {"seq": self._n, "id": self.tid, "cmd": cmd, "replies": []}

    def _line(self, line):
        if self._cur is None:
            return
        if self.redact:
            line = redact_line(line)
        # Two lines is the whole reply for every command in the corpus except
        # the multi-part `get queue`; cap so one drain cannot evict the ring.
        if len(self._cur["replies"]) < 4:
            self._cur["replies"].append(line[:400])

    def _commit(self):
        if self._cur is not None:
            self.buf.append(self._cur)
            self._cur = None

    # -- the provider -------------------------------------------------------

    def begin(self, tid: str):
        """Called by the runner as each id is dispatched."""
        self._commit()
        self.tid = tid

    def snapshot(self, tid: str) -> list:
        """`results`' exchange provider. -> the last `RING_LEN` exchanges."""
        self._commit()
        return list(self.buf)
