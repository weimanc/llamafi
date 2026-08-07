# LOCAL_PATCHES — vendored `SD` library

Verbatim copy of `framework-arduinoespressif32` (3.20017.241212, Arduino 2.0.17)
`libraries/SD`, vendored into `app/lib/` so it takes LDF precedence over the bundled
copy — the same pattern already used for `WiFiClientSecure`.

Re-vendoring after a platform bump: re-copy the upstream directory and re-apply
PATCH-SD-1 below. Do not bump `platform = espressif32` past 6.9.x without checking it
(see `CLAUDE.md`).

---

## PATCH-SD-1 — trust the CSD over the OCR when typing the card (TASK-408)

**File:** `src/sd_diskio.cpp` · **Added:** 2026-08-07

### Symptom

A 30 GB (nominal 32 GB) SDHC card fails to mount with
`f_mount failed: (13) There is no valid FAT volume`, while a 2 GB SDSC card in the same
slot mounts normally.

### Cause

`ff_sd_initialize()` types the card **solely** from OCR bit 30 (CCS) after ACMD41.
On this board that bit reads 0 for the SDHC card, so it is typed `CARD_SD`
(byte-addressed) rather than `CARD_SDHC` (block-addressed). Every read then issues
`sector << 9` as a byte address to a card that expects a block number.

The failure is deliberately hard to spot, because the one sector that still works is the
one you would check first: **address 0 is identical under both addressing modes**, so the
MBR at sector 0 reads back perfectly — valid `0x55AA` signature, partition type `0x0C`
(FAT32 LBA), start LBA 63. Sector 63 then reads deterministic garbage, and FatFs
concludes there is no filesystem.

Init completes with **no warnings at `CORE_DEBUG_LEVEL=2`** — every `log_w` +
`goto unknown_card` path is skipped, so the card looks correctly enumerated.

### Evidence

The same init already contradicts itself. `sdGetSectorsCount()` reads the CSD and takes
the `(csd[0] >> 6) == 0x01` branch — **CSD structure v2.0, defined only for SDHC/SDXC** —
returning a correct 60 733 440 sectors (29 655 MB). A byte-addressed `CARD_SD` cannot be
larger than 2 GB, so the OCR-derived type and the CSD-derived capacity cannot both be
right. DUT-confirmed deterministic: 5 consecutive cold inits, byte-identical results.

### Fix

Added `sdCsdSaysHighCapacity()` and, after the OCR type decision, promote
`CARD_SD` → `CARD_SDHC` when the CSD reports structure v2. Placed **before** the
`SET_BLOCKLEN` block — CMD16 is meaningless on a block-addressed card. The correction
logs at warn level rather than being silent.

Narrow by construction: it only ever promotes `CARD_SD` → `CARD_SDHC`, and only on the
CSD's own evidence, so a genuine SDSC card (CSD v1) is untouched — the 2 GB card that
already worked follows exactly the same path as before.
