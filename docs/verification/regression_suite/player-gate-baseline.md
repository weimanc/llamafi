# M-TESTBASE phase-1 player gate — pre-declared pass set

> Owner: @VE (the pass set) / @Developer (the driver, `run/player-gate`)
> Source of truth for the gate's verdict. Machine-read by `run/player-gate`.
> Design: [M-TESTBASE §4 P3 / §6](../../architecture/designs/M-TESTBASE-phase1-player-gate.md)
> Registered ids: [`test_plan.md`](../test_plan.md) — `T_PLR_01`–`26`, `T_PMT_00`–`04`

---

## 1. What the gate is

One ordered execution of **two legs at the same commit** (VE's wording, adopted at
M-TESTBASE §4 P3):

| Leg | Env flashed | Cells |
|---|---|---|
| **A** | `cyd2usb_winamp_debug` | `T_PLR_01`–`24`,`26` + M3/M4a/M5 + the **S→W** and **W→L** transition cells |
| **B** | `cyd2usb_player` | `test_fbrowser_player.py`, `test_playorder_player.py`, the **L→S** cell and the M2 cells |

**The gate FAILS if any cell in either leg regresses against the pass set below.**

M3 (capability mask) is `T_PLR_17`/`18`/`19`; M4a (`playOrder`) is `T_PLR_20`–`24`/`26`; M5
(bound `PlaylistSource`) is asserted inside the `get player` vector that every `T_PMT_0x` cell
reads — all of them already inside leg A's id list, which is why the leg is a list and not a
concatenation of suites.

### Condition (a) — each leg carries a genuinely cross-mode cell

M-TESTBASE §4: *"each leg must contain at least one genuinely cross-mode cell — one asserting on
mode X after arriving from mode Y — otherwise it is two per-mode suites concatenated and the
objective is lost."*

`run/player-gate` **enforces this at run time**, not by convention: it refuses to run a leg whose
id list contains none of `T_PMT_01`–`04` and exits 2. The cross-mode cells are:

| Leg | Cross-mode cell | Arrives from → asserts on |
|---|---|---|
| A | `T_PMT_01` | Spotify → **WebRadio** (`srcKind=StationList`, `caps=1`) |
| A | `T_PMT_02` | WebRadio → **Player** (`srcKind=LocalPlaylist`, `caps=15`) |
| B | `T_PMT_03` | Player → **Spotify** (`srcKind=SpotifyQueue`, arena not stranded) |
| B | `T_PMT_04` | real playback in Player → **after leaving Player**: `acquires>0`, `active==0` |

`T_PMT_00` is the binding cell, not a cross-mode cell: if it fails, `T_PMT_01`–`04` are
meaningless (M-TESTBASE §8.3), so it is pre-declared in **both** legs.

---

## 2. The pass set

Machine-read. **Columns are positional**: `leg | id | expected | note`. `expected` is `PASS` or
`SKIP`; any other value in that column makes the row invisible to the parser (deliberate — an
un-adjudicated row must not silently weaken the gate).

`SKIP` is a *declared* skip: the cell reports SKIP for a documented reason and an observed FAIL
there is still a regression. An observed PASS where `SKIP` was declared is an improvement, reported
and not failed — re-declare the row when it holds.

| leg | id | expected | note |
|---|---|---|---|
| A | T_PLR_01 | PASS | taskbar tap cycles the player mode |
| A | T_PLR_02 | *(retired 2026-09-05, TASK-603 — no reboot in the body; re-enters as a new id under TASK-615)* | — |
| A | T_PLR_03 | *(retired UNOBSERVABLE 2026-09-05, TASK-603 — unrepresentable at every taskbar offset; TASK-614 owns the record)* | — |
| A | T_PLR_04 | PASS | get/set playerMode round-trips all three |
| A | T_PLR_05 | PASS | tap from another app restores, not cycles |
| A | T_PLR_06 | PASS | eject is per-mode |
| A | T_PLR_07 | PASS | logo tap still resets TLS |
| A | T_PLR_08 | PASS | >=100-track M3U loads |
| A | T_PLR_09 | SKIP | declared SKIP on leg A — local playback cannot start with Spotify's TLS working set resident (TASK-425/431); test_plan.md records the flip trigger |
| A | T_PLR_10 | PASS | relative paths resolve |
| A | T_PLR_11 | PASS | malformed M3U degrades |
| A | T_PLR_12 | PASS | index memory bounded and freed (within-run deltas only) |
| A | T_PLR_13 | PASS | browser paging never stalls audio — browsing half only on leg A |
| A | T_PLR_14 | PASS | navigation taps survive the busy gate |
| A | T_PLR_15 | PASS | busy indicator reflects real work |
| A | T_PLR_16 | PASS | deep/edge browser paths |
| A | T_PLR_17 | PASS | capability mask, shipped mode 1 (runner numbering; spec swap unresolved) |
| A | T_PLR_18 | PASS | capability mask, shipped mode 2 (runner numbering) |
| A | T_PLR_19 | PASS | Player advertises all four capabilities |
| A | T_PLR_20 | PASS | shuffle bag visits each track once |
| A | T_PLR_21 | PASS | four end-of-list shuffle x repeat cells |
| A | T_PLR_22 | PASS | reshuffle does not re-open on the last track |
| A | T_PLR_23 | PASS | prev replays history |
| A | T_PLR_24 | PASS | tap-to-play moves the bag cursor, no reshuffle |
| A | T_PLR_26 | PASS | shuffle/repeat persist across reboot |
| A | T_PMT_00 | PASS | binding — the surface named by `get playerBind` performs `playerCycle` |
| A | T_PMT_01 | PASS | **cross-mode** S->W |
| A | T_PMT_02 | PASS | **cross-mode** W->L |
| B | T_PMT_00 | PASS | binding, re-asserted on the leg-B build |
| B | T_PMT_03 | PASS | **cross-mode** L->S |
| B | T_PMT_04 | PASS | **cross-mode** M2/X052 arena acquire+release across a real playback |
| B | T_PLR_13_playback | PASS | `test_fbrowser_player.py` — 200-entry walk during real playback (whole script = one cell) |
| B | T_PLR_25_playback | PASS | `test_playorder_player.py` — auto-advance end to end (whole script = one cell) |

`T_PLR_25` is **not** in leg A: its only meaningful form needs a real decode, which is
`T_PLR_25_playback` on leg B. `T_PLR_27`–`41` are reserved/blocked (`test_plan.md` §
`T_PLR_27`–`41`) and are deliberately absent — a blocked id in a pass set is a permanent red.

### Divergence from this baseline, 2026-08-31 — `T_PMT_04`

**The `B | T_PMT_04 | PASS` row above is left exactly as recorded**: this document is a dated
baseline, and rewriting a past measurement destroys the only thing a baseline is for. Read it as
"what leg B measured on the baseline date", not as current state.

A leg-B re-run on 2026-08-31 (`NO_WIFI=1 DUT_ENV=cyd2usb_player ./run/test-targeted
T_PLR_25,T_PMT_04,T_PLR_14`) scored **`T_PLR_25` PASS, `T_PLR_14` PASS, `T_PMT_04` FAIL**. The
failure is not the playback-start flake described below — playback started normally and the playlist
loaded 5 rows. It fails `acquires did not move during REAL playback: 1 -> 1` because the arena is
already held at baseline (`acquires=1 releases=0 active=1 hwm=23216`). Tracked as **TASK-553**;
`test_plan.md`'s `T_PMT_04` row carries the detail. Anyone re-running this gate should expect that
one red until TASK-553 resolves, and should not read it as a regression introduced by whatever they
are testing.

### Known flake, declared

`T_PMT_04` failed 1 of 5 consecutive fresh-boot runs on `cyd2usb_player` (2026-08-17): playback
never started (`curRow` stayed `-1` for all three attempts), so `acquires` never left 0. The arena
numbers are identical on every run that started — it is a **playback-start** flake, not an arena
flake. It is declared `PASS` here deliberately: the gate must go red on it, and the reader must
consult this note. When `docs/verification/flaky.yaml` lands (TASK-520) this note moves there.

---

## 3. Re-declaring the pass set

The pass set is *pre-declared*, i.e. written before the run whose verdict it decides. To move it:

```sh
RECORD=1 ./run/player-gate            # writes <out>/observed.md — the table as measured
```

Paste the rows into §2 **with an adjudication in the note column**. A row moved from `PASS` to
`SKIP`, or removed, is a lowering of the gate and needs @VE's sign-off; a row moved from `SKIP` to
`PASS` is a raise and does not.

Recording and gating in the same run is not possible by construction — `RECORD=1` writes the
observed table but the verdict is still computed against the committed §2.
