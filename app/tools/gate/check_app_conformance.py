#!/usr/bin/env python3
"""check_app_conformance.py — the app conformance matrix, rows A5 and A6.

M-TESTARCH §2.3: a conformance matrix is
    (domain enumerated from a generated source of truth)
  x (contract rows taken from NEW-APP-CHECKLIST.md)
  -> one cell per (app, row), generated, never hand-written per app.

The domain is `app_ids_gen.APP_ORDER` — GENERATED from appRegistry.h's X-macro.
The app list is never typed here; that is the durable fix for "the app list order
was hardcoded in the test suite" (§2.4 item 2).

Rows implemented (the two T0-static ones — no device, no build):

  A5  TLS bracket    NEW-APP-CHECKLIST item 2 / BP-031.
                     Every HTTPS session-open site attributable to an app must
                     sit inside a tlsYield()/tlsResume() bracket, either in its
                     own enclosing function or in EVERY caller of it.
  A6  debug surface  NEW-APP-CHECKLIST item 3.
                     The app object must be observable from the serial console:
                     >= 1 `get` key that statically resolves to the app INSTANCE
                     (g_<Name>App), via its own dbgGet() in cmdGet.cpp's delegation
                     chain, or via a cmdGet.cpp branch that calls the instance.

Both rows are asserted STATICALLY over app/src — grep/parse only, tier T0.

Exceptions live in docs/verification/app_conformance_exceptions.md, keyed on
(row, subject), each with an owning TASK and an ISO date. A stale row there is
itself a failure (same bargain as the C6 ledger). Nothing is exempted wholesale:
there is no file, directory or wildcard exemption, by design.

Exit status: 0 unless --strict (see STRICT_DEFAULT / the header of the ledger).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "app" / "src"
TOOLS = Path(__file__).resolve().parent.parent  # app/tools/ — TASK-481 moved this file into gate/
LEDGER = REPO / "docs" / "verification" / "app_conformance_exceptions.md"
CMDGET = SRC / "debug" / "serialConsole" / "cmdGet.cpp"  # body moved here, TASK-471

sys.path.insert(0, str(TOOLS))
from app_ids_gen import APP_ORDER  # noqa: E402  (generated; never typed here)

# Warn-only on landing. See the "advisory vs blocking" note in the ledger:
# A5's unexcepted-failure count is 0, A6's is not, and a gate that lands red
# cannot be blocking without blocking the tree. Promote by flipping this once
# A6's outstanding cells are closed or excepted.
STRICT_DEFAULT = False

ROWS = ("A5", "A6")

# ── ledger ────────────────────────────────────────────────────────────────────

_LEDGER_ROW = re.compile(
    r"^\|\s*`(A\d)`\s*\|\s*`([^`]+)`\s*\|(.*?)\|\s*(TASK-\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*$"
)


def load_ledger() -> tuple[dict[tuple[str, str], dict], list[str]]:
    """(row, subject) -> {why, owner, since}. Errors are returned, never raised."""
    out: dict[tuple[str, str], dict] = {}
    errs: list[str] = []
    if not LEDGER.exists():
        return out, [f"ledger missing: {LEDGER.relative_to(REPO)}"]
    in_ledger = False
    for i, line in enumerate(LEDGER.read_text().splitlines(), 1):
        s = line.rstrip()
        if s.startswith("#"):
            # Only the `## Ledger` section carries rows. The document's other
            # tables also start `| \`A5\` |` (the subject-key legend), and
            # parsing those made the legend look like two malformed rows.
            in_ledger = s.strip().lower().startswith("## ledger")
            continue
        if not in_ledger or not s.startswith("|") or s.startswith("|---") \
                or "| `A" not in s:
            continue
        m = _LEDGER_ROW.match(s)
        if not m:
            errs.append(f"{LEDGER.name}:{i}: unparsable ledger row (needs "
                        "| `row` | `subject` | why | TASK-nnn | YYYY-MM-DD |)")
            continue
        row, subj, why, owner, since = m.groups()
        if row not in ROWS:
            errs.append(f"{LEDGER.name}:{i}: unknown row '{row}'")
            continue
        key = (row, subj)
        if key in out:
            errs.append(f"{LEDGER.name}:{i}: duplicate row for {row}/{subj}")
        out[key] = {"why": why.strip(), "owner": owner, "since": since, "line": i}
    return out, errs


# ── C/C++ source helpers ──────────────────────────────────────────────────────

def sources() -> dict[str, str]:
    out = {}
    for p in sorted(SRC.rglob("*")):
        if p.suffix in (".h", ".cpp"):
            out[str(p.relative_to(REPO)).replace(os.sep, "/")] = p.read_text(errors="replace")
    return out


def strip_comments(text: str) -> str:
    """Blank // and /* */ comments, preserving offsets (so line numbers hold).

    String literals are KEPT — the key names this gate reads live inside them
    (`strcmp(var, "wrStation")`). Only braces *inside* a literal are blanked,
    because every debug printf in this codebase emits JSON and `"{\\"ok\\":true`
    would otherwise desynchronise brace matching for the rest of the file.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if text[k] != "\n":
                    out[k] = " "
            i = j
        elif text[i] in "\"'":
            q = text[i]
            j = i + 1
            while j < n and text[j] != q:
                j += 2 if text[j] == "\\" else 1
            for k in range(i, min(j + 1, n)):
                if text[k] in "{}":
                    out[k] = " "
            i = min(j + 1, n)
        else:
            i += 1
    return "".join(out)


_FUNC = re.compile(
    r"(?:^|\n)[ \t]*(?:template\s*<[^>]*>\s*)?"
    r"(?:(?:static|inline|virtual|constexpr|extern|IRAM_ATTR)\s+)*"
    r"[A-Za-z_][\w:<>,\s\*&]*?\b(\w+)\s*\(([^;{)]*)\)\s*(?:const\s*)?(?:noexcept\s*)?"
    r"(?:override\s*)?\{"
)

_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "else", "do", "sizeof"}


def functions(clean: str) -> list[tuple[str, int, int]]:
    """[(name, start_of_body, end_of_body)] — body spans include the braces."""
    out = []
    for m in _FUNC.finditer(clean):
        name = m.group(1)
        if name in _KEYWORDS:
            continue
        brace = clean.index("{", m.end() - 1)
        depth, j = 0, brace
        while j < len(clean):
            if clean[j] == "{":
                depth += 1
            elif clean[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((name, brace, j))
    return out


def lineno(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


# ── A5: TLS bracket ───────────────────────────────────────────────────────────

# A session-open site: the point at which this code opens its own TLS session.
# `WiFiClientSecure x;` is ADR-029's per-fetch stack session; connecttohost() is
# the audio library's own TLS/TCP connect.
# `extern WiFiClientSecure client;` is a DECLARATION, not a session — the
# definition it refers to is a site in its own right and is counted there.
_TLS_SITE = re.compile(r"(?<!extern )\bWiFiClientSecure\s+(\w+)\s*;"
                       r"|\b(?:->|\.)connecttohost\s*\(")

_YIELD = re.compile(r"\btls(?:Try)?Yield\s*\(")
_RESUME = re.compile(r"\btlsResume\s*\(")
# TASK-458 (M-CODEQUAL C2): a TlsYieldGuard local is an RAII bracket — its
# destructor calls tlsResume() on every exit path by construction (early
# return, fall-through, exception), so a guard declared before the session
# site needs no manual per-path resume scan. Matches both the default ctor
# (`TlsYieldGuard tlsGuard;`) and the bounded-timeout ctor
# (`TlsYieldGuard g(2000);`). Functions that still use the manual
# tlsYield()/tlsResume() pair (e.g. fetchPlaneRadar()) are unaffected — this
# is checked in ADDITION to, not instead of, the existing _brackets scan.
_GUARD = re.compile(r"\bTlsYieldGuard\s+\w+\s*[;(]")

# FetchType tags -> the app that owns the fetch, derived by matching the tag
# against APP_ORDER (uppercased) rather than a typed table.
_FETCH_TAG = re.compile(r"\bDATA_FETCH_([A-Z0-9_]+)\b")


def app_for_token(tok: str) -> str | None:
    t = tok.upper().replace("_", "")
    for app in APP_ORDER:
        if t.startswith(app.upper()):
            return app
    return None


def owning_app_file(srcs: dict[str, str]) -> dict[str, str]:
    """app -> the file that DEFINES class <Name>App."""
    out = {}
    for app in APP_ORDER:
        pat = re.compile(r"\b(?:class|struct)\s+" + app + r"App\b[^;]*\{")
        for rel, text in srcs.items():
            if pat.search(text):
                out[app] = rel
                break
    return out


class A5:
    """Every HTTPS session-open site, its bracket verdict, and its app."""

    def __init__(self, srcs: dict[str, str]):
        self.srcs = srcs
        self.clean = {rel: strip_comments(t) for rel, t in srcs.items()}
        self.funcs = {rel: functions(c) for rel, c in self.clean.items()}
        self.by_app_file = {v: k for k, v in owning_app_file(srcs).items()}
        self.sites: list[dict] = []
        self._scan()

    def _enclosing(self, rel: str, off: int):
        best = None
        for name, s, e in self.funcs[rel]:
            if s <= off <= e and (best is None or s > best[1]):
                best = (name, s, e)
        return best

    def _brackets(self, rel: str, fn, off: int) -> bool:
        """A yield before the session, and a resume on EVERY exit after it.

        "a tlsResume() appears somewhere later in the function" is not the
        contract and is not enough: BP-031 says *every exit path*, and the
        early-return paths in `dataTaskStorage.cpp` are exactly where that has
        been got wrong before. So the region from the yield to the end of the
        function is cut at each `return`, and each piece must carry its own
        resume. (Verified by N2 in test_check_app_conformance.py: deleting only
        `fetchWeather()`'s final resume leaves its early-path resume in place,
        and a "somewhere later" test passes that mutation.)
        """
        name, s, e = fn
        body = self.clean[rel]
        # TASK-458: an RAII TlsYieldGuard declared before this session site
        # brackets it unconditionally — the destructor fires on every exit
        # path (early return, fall-through), which is exactly what the
        # manual scan below exists to verify for the old pattern. See
        # test_check_app_conformance.py's case_a5_guard_* for the mutation
        # coverage (both "guard present -> PASS" and, on a still-manual
        # function, "guard absent, manual resume missing -> still FAILS").
        if _GUARD.search(body[s:off]):
            return True
        ys = [m.end() for m in _YIELD.finditer(body, s, off)]
        if not ys:
            return False
        y = ys[-1]

        # brace depth relative to the function body, per offset in [s, e]
        depth = {}
        d = 0
        for i in range(s, e + 1):
            if body[i] == "{":
                d += 1
            depth[i] = d
            if body[i] == "}":
                d -= 1
                depth[i] = d

        resumes = [(m.start(), depth[m.start()]) for m in _RESUME.finditer(body, y, e)]
        exits = [(y + m.start(), depth[y + m.start()])
                 for m in re.finditer(r"\breturn\b", body[y:e])]
        # ... and the fall-through end. `depth[e]` is 0 (post-decrement of the
        # closing brace); the exit itself happens INSIDE the body, at depth 1.
        exits.append((e, 1))

        for ex, de in exits:
            covered = False
            for (r, dr) in resumes:
                if r >= ex or dr > de:
                    continue
                # the resume must still be in a block that encloses this exit:
                # depth never drops below the resume's own between the two.
                if min(depth[i] for i in range(r, ex)) >= dr:
                    covered = True
                    break
            if not covered:
                return False
        return True

    def _callers_bracket(self, rel: str, fname: str, seen: set) -> bool | None:
        """True/False if every call site brackets; None if there are no call sites."""
        key = (rel, fname)
        if key in seen:
            return None
        seen.add(key)
        found = False
        for crel, cclean in self.clean.items():
            for m in re.finditer(r"\b" + re.escape(fname) + r"\s*\(", cclean):
                fn = self._enclosing(crel, m.start())
                if fn is None or fn[0] == fname:
                    continue
                found = True
                if self._brackets(crel, fn, m.start()):
                    continue
                up = self._callers_bracket(crel, fn[0], seen)
                if not up:
                    return False
        return True if found else None

    def _scan(self):
        for rel, clean in self.clean.items():
            for m in _TLS_SITE.finditer(clean):
                fn = self._enclosing(rel, m.start())
                ln = lineno(clean, m.start())
                site = {"file": rel, "line": ln, "fn": fn[0] if fn else "<file scope>",
                        "id": f"{rel}:{fn[0] if fn else 'file-scope'}"}
                if fn is None:
                    site["ok"], site["how"] = False, "file-scope session, no function to bracket"
                elif self._brackets(rel, fn, m.start()):
                    site["ok"], site["how"] = True, f"bracketed in {fn[0]}()"
                else:
                    up = self._callers_bracket(rel, fn[0], set())
                    site["ok"] = bool(up)
                    site["how"] = (f"bracketed by every caller of {fn[0]}()" if up
                                   else (f"{fn[0]}() has no caller in app/src" if up is None
                                         else f"unbracketed in {fn[0]}() and >=1 caller"))
                site["app"] = self._attribute(rel, fn)
                self.sites.append(site)

    def _attribute(self, rel: str, fn) -> str | None:
        if rel in self.by_app_file:
            return self.by_app_file[rel]
        if fn is None:
            return None
        name, s, e = fn
        for tag in _FETCH_TAG.findall(self.clean[rel][s:e]):
            app = app_for_token(tag)
            if app:
                return app
        # fall back to the function's own name (fetchTeletextPage -> Teletext)
        for app in APP_ORDER:
            if app.lower() in name.lower():
                return app
        return None


# ── A6: debug surface ─────────────────────────────────────────────────────────

_DBGGET_DEF = re.compile(
    r"\bbool\s+(?:(\w+)::)?dbgGet\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?\{")
_STRCMP_KEY = re.compile(r'strcmp\(\s*\w+\s*,\s*"([A-Za-z0-9_]+)"')
_CMDGET_KEY = re.compile(r'strn?cmp\(\s*args\s*,\s*"([A-Za-z0-9_]+)"')


def a6_scan(srcs: dict[str, str]) -> dict[str, dict]:
    """app -> {ok, how, keys}. Reuses gen_get_keys.py's two static sources."""
    clean = {rel: strip_comments(t) for rel, t in srcs.items()}
    cmdget_rel = str(CMDGET.relative_to(REPO)).replace(os.sep, "/")
    cg = clean[cmdget_rel]
    owner = owning_app_file(srcs)

    # M1 — cmdGet.cpp delegates to a shim that forwards to g_<Name>App.dbgGet().
    shims = {}   # shim name -> app
    for rel, c in clean.items():
        for m in re.finditer(r"\b(\w+)\s*\([^)]*\)\s*\{[^}]*\bg_(\w+)App\s*\.\s*dbgGet\s*\(", c):
            app = m.group(2)
            if app in APP_ORDER:
                shims[m.group(1)] = app

    out = {}
    for app in APP_ORDER:
        keys: list[str] = []
        how = None
        # M1: own dbgGet(), reached through a shim cmdGet.cpp actually calls.
        # The definition is either in-class in the owning file (`bool
        # dbgGet(...) {`) or out-of-line, anywhere, qualified with the app's
        # own class (`bool XApp::dbgGet(...) {` — M-SRCLAYOUT Stage E moves
        # method bodies out of the header into a companion .cpp).
        owner_rel = owner.get(app)
        for rel, text in clean.items():
            for m in _DBGGET_DEF.finditer(text):
                qualifier = m.group(1)
                if qualifier is None:
                    if rel != owner_rel:
                        continue
                elif qualifier != app + "App":
                    continue
                brace = text.index("{", m.end() - 1)
                depth, j = 0, brace
                while j < len(text):
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                body_keys = _STRCMP_KEY.findall(text[brace:j])
                called = any(re.search(r"\b" + re.escape(sh) + r"\s*\(", cg)
                             for sh, a in shims.items() if a == app)
                if body_keys and called:
                    keys += body_keys
                    how = f"own dbgGet() in {rel}, reached via cmdGet.cpp's delegation chain"
        # M2: a cmdGet.cpp branch body that calls the app INSTANCE directly.
        if not keys:
            direct = []
            for m in _CMDGET_KEY.finditer(cg):
                # branch body = from the key match to the next `return;`
                end = cg.find("return", m.end())
                seg = cg[m.start():end if end > 0 else m.end() + 400]
                if re.search(r"\bg_" + app + r"App\b", seg):
                    direct.append(m.group(1))
            if direct:
                keys += direct
                how = "cmdGet.cpp branch(es) calling g_%sApp directly" % app
        out[app] = {"ok": bool(keys), "keys": sorted(set(keys)),
                    "how": how or "no `get` key resolves to g_%sApp" % app}
    return out


# ── evaluate ──────────────────────────────────────────────────────────────────

def evaluate(srcs: dict[str, str], ledger: dict, ledger_errors=()):
    """The whole verdict, as data. Kept free of I/O so the negative tests
    (BP-068, test_check_app_conformance.py) can mutate `srcs`/`ledger` in
    memory and assert the checker actually fails."""
    used: set[tuple[str, str]] = set()
    failures: list[str] = list(ledger_errors)

    # ── A5 ────────────────────────────────────────────────────────────────────
    a5 = A5(srcs)
    a5_cells: dict[str, str] = {}
    a5_detail: dict[str, list[str]] = {a: [] for a in APP_ORDER}
    unattributed = []
    for s in a5.sites:
        tag = f"{s['file']}:{s['line']}"
        if s["app"] is None:
            key = ("A5", s["id"])
            if key in ledger:
                used.add(key)
                continue
            unattributed.append(
                f"A5/<unattributed> {tag} in {s['fn']}() — HTTPS session site "
                f"attributable to no registered app "
                f"[bracket: {'ok' if s['ok'] else 'NOT PROVEN'} — {s['how']}]")
            continue
        a5_detail[s["app"]].append(f"{tag} {'ok' if s['ok'] else 'BAD'}: {s['how']}")
        if not s["ok"]:
            key = ("A5", s["id"])
            if key in ledger:
                used.add(key)
                a5_detail[s["app"]][-1] += f"  [excepted {ledger[key]['owner']}]"
            else:
                failures.append(f"A5/{s['app']}: {tag} in {s['fn']}() — {s['how']}")
    for app in APP_ORDER:
        sites = [s for s in a5.sites if s["app"] == app]
        if not sites:
            a5_cells[app] = "n/a"
        elif all(s["ok"] or ("A5", s["id"]) in ledger for s in sites):
            a5_cells[app] = "PASS" if all(s["ok"] for s in sites) else "EXCEPT"
        else:
            a5_cells[app] = "FAIL"
    failures += unattributed

    # ── A6 ────────────────────────────────────────────────────────────────────
    a6 = a6_scan(srcs)
    a6_cells = {}
    for app in APP_ORDER:
        if a6[app]["ok"]:
            a6_cells[app] = "PASS"
        elif ("A6", app) in ledger:
            used.add(("A6", app))
            a6_cells[app] = "EXCEPT"
        else:
            a6_cells[app] = "FAIL"
            failures.append(f"A6/{app}: {a6[app]['how']} (NEW-APP-CHECKLIST item 3)")

    # ── stale ledger rows are themselves a failure ────────────────────────────
    for key, row in sorted(ledger.items()):
        if key not in used:
            failures.append(f"stale exception {key[0]}/{key[1]} "
                            f"({row['owner']}, {row['since']}) — the finding it "
                            f"suppresses no longer exists; delete this row "
                            f"({LEDGER.name}:{row['line']})")

    return {"a5": a5, "a5_cells": a5_cells, "a6": a6, "a6_cells": a6_cells,
            "failures": failures, "used": used}


# ── report ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verbose", action="store_true",
                    help="list every A5 HTTPS site and its bracket evidence")
    args = ap.parse_args()
    strict = STRICT_DEFAULT or args.strict

    srcs = sources()
    ledger, lerrs = load_ledger()
    r = evaluate(srcs, ledger, lerrs)
    a5, a5_cells, a6, a6_cells = r["a5"], r["a5_cells"], r["a6"], r["a6_cells"]
    failures = r["failures"]

    if not args.quiet:
        print(f"check_app_conformance: {len(APP_ORDER)} apps x {len(ROWS)} rows "
              f"(A5 TLS bracket, A6 debug surface) — {len(a5.sites)} HTTPS site(s), "
              f"{len(ledger)} exception(s) on the ledger")
        print(f"  {'app':<12} {'A5':<8} {'A6':<8} A6 evidence")
        for app in APP_ORDER:
            ev = (",".join(a6[app]["keys"][:3]) + ("…" if len(a6[app]["keys"]) > 3 else "")
                  ) if a6[app]["keys"] else a6[app]["how"]
            print(f"  {app:<12} {a5_cells[app]:<8} {a6_cells[app]:<8} {ev}")
        if args.verbose:
            print("  A5 sites:")
            for s in sorted(a5.sites, key=lambda x: (x["file"], x["line"])):
                print(f"    {'ok ' if s['ok'] else 'BAD'} {s['app'] or '<none>':<12} "
                      f"{s['file']}:{s['line']} {s['fn']}() — {s['how']}")
    for f in failures:
        print(f"  {'FAIL' if strict else 'WARN'} {f}")

    n = len(failures)
    if n == 0:
        print("check_app_conformance: OK — A5/A6 conform for every registered app")
        return 0
    print(f"check_app_conformance: {n} finding(s)"
          + ("" if strict else " (warn-only — see docs/verification/"
                              "app_conformance_exceptions.md)"))
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
