#!/usr/bin/env python3
"""test_check_screendump_instrument.py — the negative suite for TASK-589's gate.

BP-068: a gate nobody has seen fail is not a gate. This one exists because its
subject already rotted once IN SILENCE for three months while a check ran over
the file on every commit and reported it as fine, so "it passes today" is worth
nothing here on its own.

Each arm builds a shadow `app/tools` — every entry SYMLINKED, except the one
file under mutation, which is a real copy — and requires the checker to report
the mutation. The mutations are not invented: `M1` is verbatim the defect that
took the instrument down (`A-1`), and `M6`/`M7` are the two halves of TASK-340's
transform, whose loss would make `--colorprobe` green on a board with a
degraded MISO read.

One control arm runs the checker over an UNMUTATED shadow tree and requires it
to be silent, so a checker that simply always fails cannot pass this suite.

    python3 app/tools/gate/test_check_screendump_instrument.py
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent.parent

sys.path.insert(0, str(HERE))
import check_screendump_instrument as gate  # noqa: E402

results: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def shadow(tmp: pathlib.Path, mutate: dict[str, str]) -> pathlib.Path:
    """A shadow app/tools: symlinks throughout, real copies of `mutate` keys.

    Kept at `<tmp>/app/tools` with `<tmp>/app/gen` symlinked alongside, because
    `preview_common` (which `clock_delta_smoke` imports) reads `app/gen/*.h`
    relative to the tools directory's parent — LL-114's rule that host tools
    parse the generated headers rather than mirroring them.
    """
    app = tmp / "app"
    app.mkdir()
    (app / "gen").symlink_to(ROOT / "app" / "gen")
    out = app / "tools"
    out.mkdir()
    for entry in TOOLS.iterdir():
        if entry.name == "__pycache__":
            continue
        (out / entry.name).symlink_to(entry)
    for rel, text in mutate.items():
        dst = out / rel
        if dst.is_symlink():
            dst.unlink()
        else:                       # a file inside a symlinked package dir
            real = dst
            pkg = dst.parent
            if pkg.is_symlink():
                src = pkg.resolve()
                pkg.unlink()
                shutil.copytree(src, pkg, ignore=shutil.ignore_patterns("__pycache__"))
            real.unlink(missing_ok=True)
        dst.write_text(text)
    return out


def src(rel: str) -> str:
    return (TOOLS / rel).read_text()


def run_arm(name: str, mutate: dict[str, str], want: str,
            expect_silence: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="task589-gate-") as td:
        tools = shadow(pathlib.Path(td), mutate)
        found = gate._run_child(tools)
    if expect_silence:
        report(name, not found, f"{len(found)} finding(s): {found[:2]}")
        return
    hit = [f for f in found if f.startswith(want)]
    report(name, bool(hit),
           (hit[0][:150] if hit else f"NOT CAUGHT — findings were {found}"))


def main() -> int:
    sd = src("screendump.py")

    # ── the control ──────────────────────────────────────────────────────────
    run_arm("N0 unmutated shadow tree is silent", {}, "", expect_silence=True)

    # ── M1 — the real defect, verbatim (WP-A A-1) ────────────────────────────
    run_arm(
        "N1 A-1 itself: the deleted _PORTAL_INDICATORS import is caught",
        {"screendump.py": sd.replace(
            "from lib.dut import Dut, _DUT_WIFI_WAIT_S, _is_ip_line",
            "from lib.dut import Dut, _DUT_WIFI_WAIT_S, _PORTAL_INDICATORS")},
        "A screendump")

    # ── M2 — a dependant alone. check_import_safety files this as "skipped". ─
    run_arm(
        "N2 a dependant that stops importing is caught",
        {"clock_delta_smoke.py": src("clock_delta_smoke.py").replace(
            "from screendump import DutLite, dump_with_retry, autodetect_port",
            "from screendump import DutLite, dump_with_retry, no_such_symbol")},
        "A clock_delta_smoke")

    # ── M3 — bands reassembled at the wrong offset. Imports fine; every
    #        capture is scrambled, and a render signature over it is stable
    #        nonsense.
    run_arm(
        "N3 a band written to the wrong row is caught",
        {"screendump.py": sd.replace(
            "        canvas[ry:ry + rows, :] = band",
            "        canvas[ry:ry + rows, :] = band[::-1]")},
        "B1")

    # ── M4 — the retry removed. The corrupted band stays ZERO, which is a
    #        black rectangle: it reads as content, not as a gap.
    run_arm(
        "N4 a corrupted band left unhealed is caught",
        {"screendump.py": sd.replace(
            "def dump_with_retry(dut, x, y, w, h, max_retries=4):\n"
            "    canvas, failed = _dump_region(dut, x, y, w, h)",
            "def dump_with_retry(dut, x, y, w, h, max_retries=4):\n"
            "    canvas, failed = _dump_region(dut, x, y, w, h)\n"
            "    return canvas")},
        "B3")

    # ── M5 — a channel swap. Invisible on a grey UI, fatal to ADR-064.
    run_arm(
        "N5 an R/B channel swap is caught",
        {"screendump.py": sd.replace(
            "    return np.stack([r, g, b], axis=-1).astype(np.uint8)",
            "    return np.stack([b, g, r], axis=-1).astype(np.uint8)")},
        "C rgb565_to_rgb888")

    # ── M6/M7 — the two halves of TASK-340's transform. An oracle that
    #        accepts either inversion is green on a degraded read.
    run_arm(
        "N6 --colorprobe accepting an unswapped fill probe is caught",
        {"screendump.py": sd.replace(
            '        want = _byteswap16(exp) if kind == "fill" else exp',
            "        want = exp")},
        "D")
    run_arm(
        "N7 --colorprobe accepting a byte-swapped push probe is caught",
        {"screendump.py": sd.replace(
            '        want = _byteswap16(exp) if kind == "fill" else exp',
            "        want = _byteswap16(exp)")},
        "D")
    run_arm(
        "N8 the wrong end-to-end swatch ground truth is caught",
        {"screendump.py": sd.replace("COLORPROBE_SWATCH_VALUE = 0xF0F0",
                                     "COLORPROBE_SWATCH_VALUE = 0x0F0F")},
        "D COLORPROBE_SWATCH_VALUE")

    # ── E — the wrapper arm, over a shadow run/ tree. ────────────────────────
    with tempfile.TemporaryDirectory(prefix="task589-wrap-") as td:
        fake = pathlib.Path(td)
        (fake / "run").mkdir()
        (fake / "run" / "screendump").write_text(
            '#!/usr/bin/env bash\n"$VENV_PY" "$PIO_DIR/tools/screendump.py"\n')
        f = gate.check_wrapper(fake)
        report("N9 a wrapper that drops \"$@\" is caught",
               any(x.startswith("E run/screendump does not forward") for x in f),
               str(f))
        (fake / "run" / "screendump").write_text(
            '#!/usr/bin/env bash\necho "$@"\n')
        f = gate.check_wrapper(fake)
        report("N10 a wrapper that no longer calls screendump.py is caught",
               any("no longer invokes" in x for x in f), str(f))

    # ── the checker's own liveness: a tree with no instrument in it at all
    #     must FAIL loudly, not pass vacuously.
    with tempfile.TemporaryDirectory(prefix="task589-empty-") as td:
        found = gate._run_child(pathlib.Path(td) / "app" / "tools")
        report("N11 a tree with no screendump.py fails, not passes vacuously",
               bool(found), str(found)[:150])

    npass = sum(1 for _, ok, _ in results if ok)
    print(f"\n== TASK-589 gate negative suite: {npass}/{len(results)} PASS ==")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
