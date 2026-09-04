# Interface Contracts

One file per interface: `IFC-001.md`, `IFC-002.md`, ...
Owner: Architect. See `../../agents/architect.md` for entry format and rules.

## Index

| IFC | Subject | Status |
|---|---|---|
| 001 | dataTask fetch service | v1 |
| 002 | task ownership + cross-context exchange | v1 |
| 003 | App lifecycle and shell dispatch | v1 |
| 004 | audio engine | **stub** — blocked on TASK-452 |
| 005 | PlaylistSource | **stub** |
| 006 | display / renderer seam | **stub** — blocked on TASK-468 |
| 007 | serial debug console (the DUT test surface) | contracted, unversioned — ADR-065 |
| 008 | test-run result artifact | contracted, not yet built — ADR-066 |

A **stub** reserves the number and records what the contract must cover. It is not implementable.
Contracting an interface before reading it carefully invents obligations, which is worse than an
admitted gap.
