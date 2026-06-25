#!/usr/bin/env python3
"""Multi-app fetch stress / soak — TASK-248.

Exercises EVERY dataTask fetcher repeatedly and unattended, then prints a report:
per-fetcher latency (min/median/p95/max), HTTP outcome histogram, failure counts,
and a global TLS-error tally. Purpose: take the human out of the manual debug loop
when chasing fetch reliability / latency. Pairs with `run/stress` (flash debug →
soak → restore prod).

It drives fetches via the debug triggers and parses the shared fetch-result log
shape emitted by dataTaskStorage.cpp:
    [D][dataTask.<app>] ... <code> elapsed=<ms>ms
plus failures: 'http.begin failed', 'JSON err', 'JSON parse error', 'http <code>'
and TLS-layer noise: 'ssl_client', 'SSL - Memory', 'after -1', mbedtls alerts.

Forceable fetchers (hammered): stock quote / chart / heatmap, teletext.
Weather/Crypto have no debug trigger — sampled by switching (interval-bound), so
their sample count is lower; that is expected, not a failure.

Usage:
    python3 test_fetch_stress.py --port /dev/ttyUSB0 --minutes 10 [--verbose]
Requires: DUT flashed with cyd2usb_winamp_debug, WiFi up. No Spotify session needed.
Exit 0 = soak completed with zero TLS errors and zero hard failures; 1 otherwise.

Known limitation: the CH340 USB-serial bridge on this board can stall under the
heavy bidirectional traffic of a long soak; the run then degrades to a partial
report (caught) — re-run if a fetcher shows 0 samples. stock/quote (8 sequential
TLS handshakes) + teletext sample most reliably; weather/crypto/heatmap each
fetch fine individually (verified) but sample less consistently in a continuous
soak. See TASK-248.
"""
import re
import sys
import time
import pathlib
import statistics
from collections import defaultdict, Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run_serialdbg_tests import Dut          # noqa: E402
from ve_suite_base import make_arg_parser    # noqa: E402

RE_GET  = re.compile(r"\[dataTask\.(\w+)\].*?(-?\d+) elapsed=(\d+)ms")
RE_BEGINFAIL = re.compile(r"\[dataTask\.(\w+)\].*http\.begin failed")
RE_JSONERR   = re.compile(r"\[dataTask\.(\w+)\].*JSON (?:err|parse error)")
RE_HTTPW     = re.compile(r"\[dataTask\.(\w+)\].*\bhttp (-?\d+)\b")
RE_TLS  = re.compile(r"ssl_client|SSL - Memory|MbedTLS|mbedtls|alloc.*fail|after -1", re.I)


def _label(app: str, line: str) -> str:
    """Derive a fetcher label (app + sub-view) from the log line."""
    if app == "stock":
        if "quote" in line:   return "stock/quote"
        if "heatmap" in line: return "stock/heatmap"
        if "chart" in line:   return "stock/chart"
        return "stock/?"
    return app


VERBOSE = False

class Stats:
    def __init__(self):
        self.codes = defaultdict(Counter)   # label -> {code: n}
        self.ms    = defaultdict(list)      # label -> [elapsed_ms]
        self.begin_fail = Counter()         # label -> n
        self.json_err   = Counter()         # label -> n
        self.tls_errors = 0
        self.tls_samples = []

    def feed(self, line: str):
        if RE_TLS.search(line):
            self.tls_errors += 1
            self.tls_samples.append(line.strip()[:120])
        m = RE_GET.search(line)
        if m:
            app, code, ms = m.group(1), int(m.group(2)), int(m.group(3))
            label = _label(app, line)
            self.codes[label][code] += 1
            self.ms[label].append(ms)
            if VERBOSE:
                print(f"      parsed GET {label} code={code} {ms}ms", flush=True)
            return
        if VERBOSE and "dataTask" in line:
            print(f"      raw: {line}", flush=True)
        m = RE_BEGINFAIL.search(line)
        if m:
            self.begin_fail[_label(m.group(1), line)] += 1
            return
        m = RE_JSONERR.search(line)
        if m:
            self.json_err[_label(m.group(1), line)] += 1


def drain(dut: Dut, secs: float, st: Stats):
    orig = dut.ser.timeout
    dut.ser.timeout = 0.4
    end = time.monotonic() + secs
    while time.monotonic() < end:
        raw = dut.ser.readline()
        if not raw:
            continue
        st.feed(raw.decode("utf-8", "replace").rstrip())
    dut.ser.timeout = orig


# Fetches are enqueued by the ACTIVE app's tick(), and the single dataTask serialises
# (and is starved by a 403 Spotify, TASK-244). So drive ONE fetch at a time and wait
# for its result before moving on — re-triggering faster just saturates the queue and
# starves the other fetchers. A phase is: (label, setup+trigger cmds, want_label,
# expected_gets, max_wait_s). Stock phases bounce through Spotify (app 0) so switchApp 7
# re-runs the launch view with the freshly-set stockMode (resume re-applies on change).
# Weather/Crypto have no debug trigger: switching re-fetches on their 60 s interval, so
# they sample when a cycle has elapsed ≥60 s since their last fetch (lower cadence — OK,
# they are single fast GETs, low TLS risk).
# NB: no "switchApp 0" bounce — activating Spotify hands the shared TLS to the 403
# poll (~14 s) right before the fetch we want, starving it. Each stock phase is
# entered FRESH from a non-stock app so triggerFetch/triggerHeatmap set the subview
# cleanly (the quote tick only runs in List, heatmap tick only in Heatmap).
_TT_PAGES = [101, 601, 702, 801]
def phases():
    tt = {"i": 0}
    def teletext():
        p = _TT_PAGES[tt["i"] % len(_TT_PAGES)]; tt["i"] += 1
        return ["switchApp 9", f"set teletextPage {p}"]
    # max_wait is generous: after each fetch the 403 Spotify resumes and runs an
    # overdue poll (~10–15 s) before the next fetcher gets a TLS window, so a fetch
    # can legitimately take that long to land. want_gets breaks early when it does.
    return [
        ("teletext",      teletext,                                                  1, 25),
        ("stock/quote",   lambda: ["set stockMode 0", "switchApp 7",
                                    "set triggerFetch 1"],                           8, 40),
        ("weather",       lambda: ["switchApp 2"],                                   1, 30),
        ("stock/heatmap", lambda: ["switchApp 7", "set triggerHeatmap 1"],           1, 30),
        ("crypto",        lambda: ["switchApp 3"],                                   1, 35),
    ]


def pct(vals, p):
    if not vals: return 0
    s = sorted(vals); k = min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))
    return s[k]


def report(st: Stats, minutes: float) -> bool:
    print("\n" + "=" * 72)
    print(f"FETCH STRESS REPORT — {minutes:.1f} min soak")
    print("=" * 72)
    labels = sorted(set(list(st.codes) + list(st.begin_fail) + list(st.json_err)))
    hard_fail = 0
    print(f"{'fetcher':14s} {'n':>4s} {'ok':>4s} {'min':>6s} {'med':>6s} {'p95':>6s} {'max':>6s}  outcomes")
    for lab in labels:
        ms = st.ms[lab]
        codes = st.codes[lab]
        n = sum(codes.values())
        ok = codes.get(200, 0) + codes.get(204, 0)
        nonok = n - ok + st.begin_fail[lab] + st.json_err[lab]
        hard_fail += nonok
        outs = ", ".join(f"{c}×{cnt}" for c, cnt in sorted(codes.items()))
        extra = []
        if st.begin_fail[lab]: extra.append(f"begin-fail×{st.begin_fail[lab]}")
        if st.json_err[lab]:   extra.append(f"json-err×{st.json_err[lab]}")
        if extra: outs += " | " + ", ".join(extra)
        print(f"{lab:14s} {n:>4d} {ok:>4d} "
              f"{min(ms) if ms else 0:>6d} {int(statistics.median(ms)) if ms else 0:>6d} "
              f"{pct(ms,95):>6d} {max(ms) if ms else 0:>6d}  {outs}")
    print("-" * 72)
    print(f"TLS-layer error lines: {st.tls_errors}")
    for s in st.tls_samples[:8]:
        print(f"    {s}")
    print(f"hard failures (non-2xx + begin-fail + json-err): {hard_fail}")
    ok = (st.tls_errors == 0 and hard_fail == 0)
    print(f"\nVERDICT: {'PASS — clean soak' if ok else 'ATTENTION — see counts above'}")
    print("=" * 72)
    return ok


def main():
    ap = make_arg_parser([], "Multi-app fetch stress / soak (TASK-248)")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    global VERBOSE
    VERBOSE = args.verbose

    dut = Dut(args.port, args.baud)
    try:
        dut.ser.write_timeout = 3.0   # don't block forever if the CH340 stalls
    except Exception:
        pass
    st = Stats()
    plan = phases()
    print(f"[stress] soaking {args.minutes} min over {len(plan)} fetch phases…", flush=True)
    t_start = time.monotonic()
    t_end = t_start + args.minutes * 60
    cyc = 0
    try:
        while time.monotonic() < t_end:
            for label, fire, want_gets, max_wait in plan:
                before = sum(st.codes[label].values())
                cmds = fire()
                if VERBOSE:
                    print(f"  >> phase {label}: {cmds}", flush=True)
                for cmd in cmds:
                    dut.send(cmd); time.sleep(0.2)
                deadline = min(time.monotonic() + max_wait, t_end)
                while time.monotonic() < deadline:
                    drain(dut, 1.5, st)
                    if sum(st.codes[label].values()) - before >= want_gets:
                        break   # this fetch's result(s) landed — next phase
            cyc += 1
            print(f"  [stress] cycle {cyc} done, t+{time.monotonic()-t_start:.0f}s, "
                  f"tls_err={st.tls_errors}", flush=True)
    except KeyboardInterrupt:
        print("\n[stress] interrupted — reporting partial results", flush=True)
    except Exception as e:
        # CH340 serial can stall under heavy soak traffic and surface as a read/write
        # error — degrade gracefully (report what we have) rather than hang.
        print(f"\n[stress] serial error ({e}) — reporting partial results", flush=True)
    finally:
        dut.close()
    ok = report(st, args.minutes)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
