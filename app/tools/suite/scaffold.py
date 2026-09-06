#!/usr/bin/env python3
"""suite/scaffold.py — scaffold a new test's RECORD. TASK-630 / Dev D4.

WHAT THIS IS FOR. Every test written from now on carries declarations: a class
with a written reason (R35), a scope, an effect, and — once TASK-641/642 land —
a claim class and a falsifier. Dev review §2.3 priced the alternative: *"if the
declarations must be typed by hand, they will be typed badly"*, at roughly 45
minutes a test. Half a day of scaffolding turns that into five minutes.

THE LINE THIS TOOL DOES NOT CROSS. A scaffold that fills in the fields needing
judgement is how a declaration becomes theatre (QM §4). So the split is explicit
and it is mechanical, not a matter of taste:

  GENERATED — everything DERIVABLE from the tree, and nothing else:
    * the family module the body belongs in         (_meta's module/scope map)
    * `scope` and HOW it was seeded                 (_meta.seed_scope)
    * `cls`'s SEED                                  (_meta.seed_cls)
    * `effect`                                      (_meta.seed_effect, run over
                                                     the emitted body — so the
                                                     value is the one the gate
                                                     will derive, not a guess)
    * the registry line, in the literal shape `gate/check_player_binding.py`
      regexes (a wrapped or reformatted entry reds `run/check`)
    * the `test_plan.md` entry, so C6's binding check is satisfied the moment
      the body is registered rather than at the next `run/check`
    * an id-collision check against the live registry AND `retired_test_ids.md`
    * a body skeleton that already satisfies the five host gates a new test
      trips first: a reachable `fail()` (R34), typed reads (R18), the restore
      manager for a mutating body (R17), no `skip()` standing in for an unmet
      premise (R28), no import-time board access (R48)

  REFUSED — deliberately, and with a placeholder the GATE REJECTS:
    * `cls_reason`, when a gating class is asked for. `check_test_meta.py`
      demands ≥ 80 characters of argument about why THIS test's failure means
      the ids after it cannot be trusted. The scaffold emits a stub that is
      shorter than that on purpose, so a scaffolded gating test CANNOT ship
      until a person writes the sentence. That refusal is the mechanical check
      behind the declaration (Phase 1 standing condition 2).
    * `scope_reason` / `effect_reason`, when an override is asked for. Both are
      one-word tags whose only job is to separate a considered placement from a
      typo; a generated one separates nothing. The tool REFUSES to emit the
      override at all unless the author supplies the word on the command line.
    * the oracle. The body asserts a placeholder and says so.
    * `claim_class` and `falsifier` (R1/R9). These fields DO NOT EXIST in the
      record yet — TASK-641 and TASK-642 are blocked behind Phase 5 — and
      inventing their spelling here would be a second definition of a record
      that has one owner.

No DUT, no serial port, no build, no network. Prints to stdout and edits
nothing: the family modules are up to 3 500 lines and are read by four
source-level gates, and a tool that rewrites them in place would be a fifth
thing that can silently corrupt them.

    ./run/new-test <scope> <ID>
    ./run/new-test LocalPlayer T_PLR_40 --cls CORE --title "queue survives eject"
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from suite.serialdbg import _meta                              # noqa: E402

#: `<scope> -> family module basename`, DERIVED from _meta's own map so a new
#: family module is picked up without editing a table here.
def family_for(scope: str) -> str:
    """The module a body for `scope` belongs in. -> basename without `.py`.

    Derived by inverting `_meta._module_scope_map()`; anything with no module of
    its own is the catch-all, which is what `_meta.CATCH_ALL_SCOPE` already
    means. Never a typed table: a table here would be a second definition of the
    family layout and would rot the first time a family is split (LL-114).
    """
    for base, mapped in sorted(_meta._module_scope_map().items()):
        if mapped == scope and os.path.exists(
                os.path.join(HERE, "serialdbg", f"{base}.py")):
            return base
    return _meta.CATCH_ALL_SCOPE


def registered_ids() -> set:
    """Every id the suite can dispatch today, plus every retired one.

    Both halves matter: reusing a LIVE id gives one id two bodies (R46 P1, the
    `T_PLR_25` shape TASK-603 had to adjudicate), and reusing a RETIRED one
    silently re-attaches the retirement ledger's row to a different test.
    """
    ids: set = set()
    try:
        import suite.serialdbg as _suite
        # `build_all_meta()` is the superset: 198 records against
        # `build_all_tests()`'s 195, because the HEALTH family keeps its own
        # registry (§4.5) and `T_DH_01..03` appear only here. Reading the meta
        # registry rather than unioning two test registries also means a family
        # added later is seen without editing this line.
        ids |= set(_suite.build_all_meta())
    except Exception:                                          # pragma: no cover
        pass
    path = os.path.join(ROOT, "docs/verification/retired_test_ids.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.strip().startswith("|"):
                    cell = line.strip().strip("|").split("|")[0].strip("`* ")
                    if re.fullmatch(r"T[A-Z0-9_]*\d+", cell):
                        ids.add(cell)
    return ids


_ID_RE = re.compile(r"^T(?:_[A-Z0-9]+)*_?\d+$")


def func_name(test_id: str) -> str:
    """`T_PLR_40` -> `t_plr_40`; `T097` -> `t097`. The suite's own convention,
    and the one `gate/check_player_binding.py` matches against the registry."""
    return test_id.lower()


# ── the emitted body ─────────────────────────────────────────────────────────
#
# Written as a template rather than assembled from fragments so that what a
# reader sees here is exactly what the author gets. Every line of it is load
# bearing against a gate; the comments say which, because a skeleton whose
# shape is unexplained gets "simplified" into a gate failure by the third
# author who copies it.

_READ_ONLY_BODY = '''\
{decorator}def {fn}(dut: Dut):
    """{title}

    {plan_ref}
    """
    # TASK-630 scaffold. R18 (TASK-596): a typed accessor, never `.get(k, dflt)`
    # — a defaulted read turns a device that never answered into a green cell.
    # NoAnswer -> UNMET and BadField -> FAIL are raised for you by lib/dut.py;
    # do not catch them here.
    observed = dut.get_int("{read_key}")

    # AUTHOR: replace this with the real oracle. It is deliberately a
    # placeholder that CANNOT pass: a scaffold that emitted a passing assertion
    # would ship a test whose green cell means nothing.
    if observed != observed:
        fail("{tid}", f"SCAFFOLD: no oracle written yet (observed={{observed}})")
        return
    fail("{tid}", "SCAFFOLD: this test has no oracle — write one or delete "
                  "the id (docs/process/test_id_retirement.md)")
'''

_MUTATING_BODY = '''\
{decorator}def {fn}(dut: Dut):
    """{title}

    {plan_ref}
    """
    # TASK-630 scaffold. R17 (TASK-602): every mutation is made inside the
    # restore manager, which restores on EVERY exit path including the
    # exception one. A `finally:` that restores is NOT equivalent — the gate
    # scores the USE OF THE MANAGER, because four hand-written `finally` blocks
    # were already leaking state at the time it landed.
    with dut.saved("{read_key}", set_to=1):
        observed = dut.get_int("{read_key}")

        # AUTHOR: replace this with the real oracle — see the read-only note.
        if observed != observed:
            fail("{tid}", f"SCAFFOLD: no oracle written yet (observed={{observed}})")
            return
        fail("{tid}", "SCAFFOLD: this test has no oracle — write one or delete the "
                      "id (docs/process/test_id_retirement.md)")
'''

_PLAN_ENTRY = '''\
### {tid} — [{feature}] {title}

- **Type**: integration (DUT)
- **Feature(s)**: {feature}
- **Objective**: AUTHOR — one sentence, stating what is asserted and against what.
- **Preconditions**: AUTHOR — what must hold before the body runs.
- **Steps**:
  1. AUTHOR.
- **Expected result**: AUTHOR — the observable, and what a failure looks like.
- **Harness**: `run/test-targeted {tid}`. Owner: VE.
- **Status**: written ({today}).
'''


class Refusal(SystemExit):
    """A field the author must supply was not supplied.

    Its own type so the negative suite can assert the tool REFUSED rather than
    merely printed something unhelpful.
    """


def build(test_id: str, scope: str, cls: str = None, effect: str = None,
          title: str = None, scope_reason: str = None,
          effect_reason: str = None, read_key: str = "heap",
          today: str = None, known_ids: set = None) -> dict:
    """-> {'record':…, 'body':…, 'registry':…, 'plan':…, 'notes':[…]}.

    Pure: no file is written and nothing is imported from the DUT layer.
    """
    today = today or datetime.date.today().isoformat()
    if not _ID_RE.match(test_id):
        raise Refusal(f"{test_id!r} is not a test id (expected e.g. T_PLR_40 or "
                      f"T240).")
    if scope not in _meta.SCOPES:
        raise Refusal(f"scope {scope!r} is not in the enum. Scope names are "
                      f"CASE-SENSITIVE: {', '.join(sorted(_meta.SCOPES))}")
    ids = registered_ids() if known_ids is None else set(known_ids)
    if test_id in ids:
        raise Refusal(f"{test_id} already binds to a body or a retirement row. "
                      f"One id, one body (R46 P1).")

    module = family_for(scope)
    seed_scope, how = _meta.seed_scope(test_id, module)
    seed_cls = _meta.seed_cls(seed_scope if seed_scope == scope else scope)

    notes = []
    decl = []
    # ── scope. Generated when the seed already produces it (EC-D2: "zero
    # hand-typed scope values"); an override needs the author's one-word tag and
    # the tool refuses to invent one.
    if seed_scope == scope:
        notes.append(f"scope={scope} — SEEDED from the {how} "
                     f"({module}.py); not declared, per EC-D2.")
    else:
        if not scope_reason:
            raise Refusal(
                f"scope {scope!r} does not match the seed {seed_scope!r} that "
                f"{module}.py + the id prefix produce, so it must be DECLARED — "
                f"and a declaration carries a one-word reason. Pass "
                f"--scope-reason <word>. (A generated reason separates nothing "
                f"from a typo, which is the only thing the field is for.)")
        decl.append(f'scope="{scope}", scope_reason="{scope_reason}"')
        notes.append(f"scope={scope} — DECLARED over the {how} seed "
                     f"{seed_scope!r}, reason {scope_reason!r}.")

    # ── cls. The seed is generated. A GATING class is refused: the sentence is
    # the whole content of the declaration (R35) and the placeholder below is
    # short on purpose so check_test_meta rejects it.
    cls = cls or seed_cls
    if cls not in _meta.CLASSES:
        raise Refusal(f"cls {cls!r} is not one of {', '.join(_meta.CLASSES)}")
    gating = cls in ("RIG", "HEALTH", "CORE")
    if cls != seed_cls or gating:
        stub = "TODO(author): why a failure here means the rest cannot be trusted"
        decl.append(f'cls="{cls}", cls_reason="{stub}"')
        if gating:
            notes.append(
                f"cls={cls} — GATING, and its reason is REFUSED by this tool. "
                f"check_test_meta.py requires >= 80 characters saying why this "
                f"test's failure means the ids after it cannot be trusted; the "
                f"stub emitted is {len(stub)} characters and WILL red run/check "
                f"until you replace it. If you cannot write the sentence, the "
                f"id is FEATURE and that is the finding.")
        else:
            notes.append(f"cls={cls} — declared over the seed {seed_cls!r}.")
    else:
        notes.append(f"cls={cls} — SEEDED from scope {scope!r}; not declared.")

    # ── effect. Derived from the emitted body itself, below, so the value
    # reported is the one the gate will derive rather than a claim about it.
    if effect is not None:
        if effect not in _meta.EFFECTS:
            raise Refusal(f"effect {effect!r} is not one of "
                          f"{', '.join(_meta.EFFECTS)}")
        if not effect_reason:
            raise Refusal(
                f"an effect override needs --effect-reason <word>; the seed is "
                f"read from the body's own commands and overriding it silently "
                f"is how a mutating body gets admitted to a descent (EC-S1).")
        decl.append(f'effect="{effect}", effect_reason="{effect_reason}"')

    mutating = (effect or "") in ("mutating", "resetting")
    template = _MUTATING_BODY if mutating else _READ_ONLY_BODY
    decorator = f"@meta({', '.join(decl)})\n" if decl else ""
    fn = func_name(test_id)
    body = template.format(
        decorator=decorator, fn=fn, tid=test_id, read_key=read_key,
        title=(title or f"AUTHOR — one line naming what {test_id} asserts"),
        plan_ref=f"Plan: docs/verification/test_plan.md `### {test_id}`.")

    if effect is None:
        # The honest value: run the real seeder over the real emitted text.
        derived = _seed_effect_of_source(body, fn)
        notes.append(f"effect={derived} — SEEDED from the emitted body's own "
                     f"commands; re-derived on every run, never stored.")
        if derived == _meta.DEFAULT_EFFECT and ".cmd(" not in body:
            # Not a scaffold defect, and worth stating rather than hiding:
            # `_meta.seed_effect` reads `.cmd(...)` / `.send(...)` STRING
            # LITERALS, and the R18 typed accessors (`dut.get_int`, `dut.saved`)
            # are not literals. A body written the way TASK-596 asks therefore
            # seeds to the conservative `mutating` even when it only reads. That
            # is safe (nothing is admitted to a descent by omission) but it is
            # not accurate, and an author who expects `read-only` here should
            # know why they did not get it.
            notes.append(
                "effect NOTE: the seeder matches `.cmd(\"…\")` literals, which "
                "a typed-accessor body has none of — so a read-only body seeds "
                "conservatively to `mutating`. Override it with --effect "
                "read-only --effect-reason <word> if that is wrong.")

    return {
        "id": test_id, "scope": scope, "cls": cls, "module": module,
        "body": body,
        "registry": f'    "{test_id}": {fn},',
        "plan": _PLAN_ENTRY.format(tid=test_id, title=(title or "AUTHOR — title"),
                                   feature=f"{scope.lower()}-001", today=today),
        "notes": notes,
    }


def _seed_effect_of_source(source: str, fn_name: str) -> str:
    """`_meta.seed_effect` over emitted TEXT rather than a live function.

    The seeder walks `inspect.getsource`, so the text has to become a function
    object first. Compiled in an isolated namespace with the two names the
    skeleton references stubbed out — importing the suite to get real ones would
    make a scaffold depend on a live registry it is trying to add to.
    """
    import types
    ns: dict = {"Dut": object, "fail": lambda *a, **k: None,
                "meta": lambda **k: (lambda f: f)}
    mod = types.ModuleType("_scaffold_probe")
    mod.__dict__.update(ns)
    mod.__file__ = "<scaffold>"
    try:
        code = compile(source, "<scaffold>", "exec")
        exec(code, mod.__dict__)                       # noqa: S102 — our own text
        return _meta.seed_effect(mod.__dict__[fn_name])
    except Exception:
        # A seeder that cannot read the body must say so, not guess `read-only`.
        return _meta.DEFAULT_EFFECT


def render(out: dict) -> str:
    lines = [
        f"── {out['id']}  scope={out['scope']}  cls={out['cls']}  "
        f"-> app/tools/suite/serialdbg/{out['module']}.py ──",
        "",
        "GENERATED — derived from the tree; do not hand-edit these values:",
    ]
    for n in out["notes"]:
        lines.append(f"  · {n}")
    lines += [
        "",
        "1. the body — paste into "
        f"app/tools/suite/serialdbg/{out['module']}.py",
        "",
        out["body"],
        f"2. the registry entry — paste into {out['module']}.py's TESTS dict "
        f"(this literal shape is regexed by gate/check_player_binding.py):",
        "",
        out["registry"],
        "",
        "3. the plan entry — paste into docs/verification/test_plan.md "
        "(C6 binds every registered id to one):",
        "",
        out["plan"],
        "REFUSED — this tool will not write these for you:",
        "  · the oracle. The body fails unconditionally until you write one.",
        "  · a gating `cls_reason`. The stub is under check_test_meta.py's "
        "80-character floor and reds run/check until replaced.",
        "  · `claim_class` / `falsifier` (R1/R9) — those fields do not exist in "
        "the record yet (TASK-641/642, Phase 5). Inventing their spelling here "
        "would be a second definition of a record that has one owner.",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="run/new-test",
        description="scaffold a new test's record (TASK-630 / Dev D4)")
    ap.add_argument("scope", help=f"one of: {', '.join(sorted(_meta.SCOPES))} "
                                  f"(CASE-SENSITIVE)")
    ap.add_argument("test_id")
    ap.add_argument("--cls", default=None, choices=list(_meta.CLASSES))
    ap.add_argument("--effect", default=None, choices=list(_meta.EFFECTS))
    ap.add_argument("--title", default=None)
    ap.add_argument("--scope-reason", default=None,
                    help="one word; required only when the scope overrides its seed")
    ap.add_argument("--effect-reason", default=None,
                    help="one word; required only when --effect overrides the seed")
    ap.add_argument("--read-key", default="heap",
                    help="the `get` key the skeleton reads (default: heap)")
    a = ap.parse_args(argv)
    out = build(a.test_id, a.scope, cls=a.cls, effect=a.effect, title=a.title,
                scope_reason=a.scope_reason, effect_reason=a.effect_reason,
                read_key=a.read_key)
    print(render(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
