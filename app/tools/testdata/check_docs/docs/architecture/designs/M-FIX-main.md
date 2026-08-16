# Fixture — the main scanned document

> Status: proposed
> Date: 2026-08-16

Frozen input for `T_DOC_01`–`T_DOC_09`. Every line below exists to exercise one
branch of `check_docs.py`. Do not "tidy" this file: the golden output at
`app/tools/testdata/check_docs/golden.txt` pins its exact failure list, and a
cosmetic edit here is a test failure there.

## C1 — positional citations

Resolving, plain: app/src/main.cpp:5 — the file has 10 lines.
Resolving, range within bounds: app/src/main.cpp:1-9

Broken, missing file: app/src/ghost.cpp:1
Broken, line overrun: app/src/main.cpp:999

Range checked on the HIGHER bound — this must FAIL even though the lower bound
resolves: app/src/main.cpp:1-999

Recursive `docs/` resolution — a sibling doc cited by bare basename. This is a
CORRECT citation and must PASS; a flat root list wrongly calls it broken:
M-FIX-nested.md:3

### Inline-backtick anti-regression case — load-bearing

The citation below is broken AND written in backticks, which is the normal
citation form in this corpus. It MUST appear in the failure list.

If anyone ever reintroduces inline-backtick suppression, this citation becomes
invisible, C1's count drops, and `T_DOC_03`'s golden comparison fails — which is
the entire point of putting it here. See the [O-rev] measurement: inline
suppression hides 96 % of the corpus (604 citations -> 21) while still reporting
PASS.

Broken citation in backticks: `app/src/ghost.cpp:7`

### Suppression that MUST work

Fenced blocks are not scanned, so nothing in this block counts:

```
app/src/ghost.cpp:42
See also app/src/ghost.cpp:44 and app/src/nowhere.py:100
```

This prose line names a coordinate that must not be gated: app/src/ghost.cpp:43 <!-- check-docs: ignore-line -->

## C2 — identifier existence

Resolving: TASK-100, ADR-001, IFC-001, X001.

Archive-only resolution — TASK-900 lives ONLY in the exempt `tasks-archive.md`.
It MUST resolve: exemptions scope scanning, never resolution. A resolver that
skips exempt files scores 1261 false failures on the live corpus.

Broken: TASK-999, ADR-999, IFC-999, X099.

## C3 — build-environment names

Resolving: cyd2usb_winamp.
Broken: cyd2usb_bogus.

Out of scope entirely — `cyd` and `trinity` are the sibling project's envs and
must NOT be flagged by C3, which gates the prefixed form only. (This paragraph
deliberately avoids writing that prefix as a bare literal: it would be counted
as a reference and inflate the fixture's C3 total.)

## C5 — relative .md links

Good: [nested](M-FIX-nested.md)
Good, with anchor: [adr](../decisions/ADR-001.md#some-heading)
Good, URL-encoded: [spaced](../../links/target%20with%20space.md)
External, ignored: [site](https://example.invalid/x.md)
Broken: [missing](M-FIX-missing.md)
