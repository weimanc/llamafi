#!/usr/bin/env python3
"""M-CEEFAX DS-2 resource-contention soak — persistent Ceefax WS + dataTask fetchers.

Runs the SAME multi-app fetch-cycling plan as test_fetch_stress.py (TASK-248)
concurrently with the cyd2usb_winamp_debug_ceefaxspike build's always-on
persistent Ceefax WebSocket (app/src/ceefaxWsSpike.h), polling `get heap` /
`get stacks` / `get ceefaxSpike` throughout. Purpose: determine whether a
second continuously-open TLS socket reproduces the TASK-285/287/289 class of
heap/TLS starvation already fought through for WebRadio (M-CEEFAX DS-2).

This does NOT run standalone — it's meant to be run twice via run/ceefax-ws-soak
(spike ON) and run/stress (spike OFF, existing script, same fetch plan, no
Ceefax connection) so the two heap-over-time traces can be diffed. This script
reuses test_fetch_stress's get_device_ip/http_log/phases/Stats/report so the
fetch load is identical between the two runs — a real A/B, not two different
tests. It deliberately does NOT use run_serialdbg_tests.Dut: that class's
_verify_debug_firmware() (ADR-042 E1 gate) intentionally rejects any ELF hash
other than the standard cyd2usb_winamp_debug build — correct behaviour for
real regression suites, but this experiment's whole point is to run a
genuinely different scratch build. MiniDut below is a minimal duck-typed
stand-in exposing just what test_fetch_stress's helpers actually need
(.ser, .cmd(), .send()), with no firmware-identity check.

Usage:
    python3 test_ceefax_ws_soak.py --port /dev/ttyUSB0 --minutes 15 [--verbose]
Requires: DUT flashed with cyd2usb_winamp_debug_ceefaxspike, WiFi up.
Exit 0 = soak completed, spike connected at least once, zero hard fetch
failures, heap didn't trend down beyond noise. 1 otherwise (see report).
"""
import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ve_suite_base import make_arg_parser    # noqa: E402
from test_fetch_stress import (              # noqa: E402
    Stats, phases, get_device_ip, http_log, report as fetch_report,
)

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")


class MiniDut:
    """Minimal serial command client — no firmware-identity verification (see
    module docstring for why). Just enough for get_device_ip/http_log/drain/
    Stats.feed and this script's own get-command polling to work unmodified.
    """

    def __init__(self, port: str, baud: int = 115200, timeout: float = 3.0):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.timeout = timeout
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.open()
        self._wait_for_boot()

    def _wait_for_boot(self):
        """Opening the port asserts DTR on most USB-serial adapters, resetting
        the board. Wait for the boot banner, then for WiFi ("IP address:"),
        bounded — simplified from run_serialdbg_tests.Dut._wait_for_ready
        (no portal-recovery/DRD-gap handling; this is a controlled scratch
        run, not an unattended regression suite)."""
        orig_timeout = self.ser.timeout
        self.ser.timeout = 0.5
        deadline = time.monotonic() + 3.0
        boot_seen = False
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "[boot]" in line or "ets Jul" in line:
                boot_seen = True
                break
        if not boot_seen:
            self.ser.timeout = orig_timeout
            self.ser.reset_input_buffer()
            return
        print("  [MiniDut] reboot detected — waiting for WiFi…", flush=True)
        self.ser.timeout = 1.0
        deadline = time.monotonic() + 45.0
        ip_seen = False
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in line:
                ip_seen = True
                break
        self.ser.timeout = orig_timeout
        if not ip_seen:
            raise RuntimeError("DUT WiFi not connected within 45s — check serial output")
        print("  [MiniDut] ready.", flush=True)

    def send(self, cmd: str):
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def read_json(self, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if not line or not line.startswith("{"):
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
        raise TimeoutError(f"no JSON response within {timeout}s")

    def cmd(self, cmd_str: str, timeout: float = 3.0) -> dict:
        # Discard any stale unread line first — the fetch-phase plan fires
        # several dut.send()-only (fire-and-forget) commands between polls
        # (e.g. "set teletextPage 601"), and if those produce their own ack
        # line that's never read, the NEXT cmd()'s read_json() silently
        # grabs that stale JSON instead of the real response (same class of
        # bug get_device_ip() in test_fetch_stress.py already guards against
        # with the same reset_input_buffer() call before "get ip").
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        self.send(cmd_str)
        try:
            return self.read_json(timeout)
        except TimeoutError:
            return {}

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


class HeapSample:
    __slots__ = ("t", "free_int", "lfb_int", "free_dma", "lfb_dma",
                 "spike_connected", "spike_connects", "spike_disconnects", "spike_msgs")


def poll_heap(dut: "MiniDut") -> HeapSample:
    s = HeapSample()
    s.t = time.monotonic()
    r = dut.cmd("get heap", timeout=3.0)
    if isinstance(r, dict):
        s.free_int = r.get("freeInt", 0)
        s.lfb_int  = r.get("lfbInt", 0)
        s.free_dma = r.get("freeDma", 0)
        s.lfb_dma  = r.get("lfbDma", 0)
    else:
        s.free_int = s.lfb_int = s.free_dma = s.lfb_dma = 0
    r2 = dut.cmd("get ceefaxSpike", timeout=3.0)
    if isinstance(r2, dict):
        s.spike_connected = r2.get("connected", False)
        s.spike_connects = r2.get("connects", 0)
        s.spike_disconnects = r2.get("disconnects", 0)
        s.spike_msgs = r2.get("msgs", 0)
    else:
        s.spike_connected = False
        s.spike_connects = s.spike_disconnects = s.spike_msgs = 0
    return s


def heap_report(samples: list[HeapSample], minutes: float) -> bool:
    print("\n" + "=" * 72)
    print(f"CEEFAX WS SOAK — HEAP REPORT — {minutes:.1f} min")
    print("=" * 72)
    if not samples:
        print("no heap samples collected")
        return False
    free_int = [s.free_int for s in samples if s.free_int]
    lfb_int  = [s.lfb_int for s in samples if s.lfb_int]
    print(f"freeInt: first={free_int[0]:>7d}  min={min(free_int):>7d}  "
          f"max={max(free_int):>7d}  last={free_int[-1]:>7d}")
    print(f"lfbInt : first={lfb_int[0]:>7d}  min={min(lfb_int):>7d}  "
          f"max={max(lfb_int):>7d}  last={lfb_int[-1]:>7d}")
    drift = free_int[-1] - free_int[0]
    print(f"freeInt drift (last-first): {drift:+d} bytes over {minutes:.1f} min")

    ever_connected = any(s.spike_connected for s in samples)
    final = samples[-1]
    print(f"\nceefaxSpike: ever_connected={ever_connected}  "
          f"final connected={final.spike_connected}  "
          f"connects={final.spike_connects}  disconnects={final.spike_disconnects}  "
          f"msgs={final.spike_msgs}")

    # A modest downward drift over a short soak is noise; a large monotonic
    # decline is the TASK-285/287/289 heap-leak signature. No fixed byte
    # threshold picked here (see M-CEEFAX DS-2) — report the number, let a
    # human/Architect judge against the baseline (no-spike) run.
    ok = ever_connected and drift > -20000  # generous placeholder gate, see docstring
    print(f"\nVERDICT: {'PASS (see drift above — compare against baseline run)' if ok else 'ATTENTION — see drift/connect status above'}")
    print("=" * 72)
    return ok


def main():
    ap = make_arg_parser([], "M-CEEFAX DS-2 resource-contention soak")
    ap.add_argument("--minutes", type=float, default=15.0)
    ap.add_argument("--heap-interval", type=float, default=10.0,
                     help="seconds between get heap/get ceefaxSpike polls")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    dut = MiniDut(args.port, args.baud)
    try:
        dut.ser.write_timeout = 3.0
    except Exception:
        pass
    st = Stats()
    heap_samples: list[HeapSample] = []

    dut.cmd("set logLevel w"); dut.cmd("set logKeep dataTask")
    dut.cmd("set bgPoll 0")  # same isolation rationale as test_fetch_stress

    ip = get_device_ip(dut)
    mode = f"HTTP /log @ {ip}" if ip else "serial drain (CH340 — may stall)"
    plan = phases()
    print(f"[ceefax-ws-soak] soaking {args.minutes} min, heap poll every "
          f"{args.heap_interval}s, fetch phases via {mode}\n", flush=True)

    t_start = time.monotonic()
    t_end = t_start + args.minutes * 60
    next_heap_poll = t_start
    cyc = 0
    try:
        while time.monotonic() < t_end:
            for label, fire, want_gets, max_wait in plan:
                if time.monotonic() >= next_heap_poll:
                    hs = poll_heap(dut)
                    heap_samples.append(hs)
                    next_heap_poll = time.monotonic() + args.heap_interval
                    print(f"  [heap] t+{hs.t - t_start:5.0f}s freeInt={hs.free_int} "
                          f"lfbInt={hs.lfb_int} spike_connected={hs.spike_connected} "
                          f"disconnects={hs.spike_disconnects} msgs={hs.spike_msgs}",
                          flush=True)

                before = sum(st.codes[label].values())
                if ip:
                    http_log(ip, "?clear=1")
                cmds = fire()
                if args.verbose:
                    print(f"  >> phase {label}: {cmds}", flush=True)
                for cmd in cmds:
                    dut.send(cmd); time.sleep(0.2)
                deadline = min(time.monotonic() + max_wait, t_end)
                fed = 0
                while time.monotonic() < deadline:
                    if ip:
                        txt = http_log(ip, "?n=48")
                        if not txt.startswith("__HTTPERR__"):
                            lines = txt.splitlines()
                            for line in lines[fed:]:
                                st.feed(line)
                            fed = len(lines)
                        time.sleep(1.2)
                    else:
                        from test_fetch_stress import drain
                        drain(dut, 1.5, st)
                    if sum(st.codes[label].values()) - before >= want_gets:
                        break
            cyc += 1
            print(f"  [ceefax-ws-soak] cycle {cyc} done, t+{time.monotonic()-t_start:.0f}s, "
                  f"tls_err={st.tls_errors}", flush=True)
    except KeyboardInterrupt:
        print("\n[ceefax-ws-soak] interrupted — reporting partial results", flush=True)
    except Exception as e:
        print(f"\n[ceefax-ws-soak] error ({e}) — reporting partial results", flush=True)
    finally:
        # final heap sample before closing, if we haven't just taken one
        try:
            heap_samples.append(poll_heap(dut))
        except Exception:
            pass
        dut.close()

    fetch_ok = fetch_report(st, args.minutes)
    heap_ok = heap_report(heap_samples, args.minutes)
    sys.exit(0 if (fetch_ok and heap_ok) else 1)


if __name__ == "__main__":
    main()
