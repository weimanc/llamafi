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

---

## PATCH-SD-2 — a failed `f_mount()` leaves the volume registered, so unregistering frees memory FatFs still points at (TASK-408)

**File:** `src/sd_diskio.cpp` · **Added:** 2026-08-08

### Symptom

With **no card in the slot**, a sequence of failed mounts panics — either

```
assert failed: vQueueDelete queue.c:2131 (pxQueue)
  vQueueDelete <- ff_del_syncobj <- f_mount <- sdcard_mount <- SDFS::begin
```

or a bare `LoadStoreError` in the same path. Reproducible in two commands: `sdmbr`
(which mounts at `/sdraw` to force `disk_initialize()`) followed by any `SD.begin()`.

### Cause — use-after-free of the FATFS object

`f_mount(fs, drv, 1)` registers the volume **before** it attempts the forced mount:

```c
    if (fs) { fs->fs_type = 0; fs->sobj = 0; ff_cre_syncobj(vol, &fs->sobj); }
    FatFs[vol] = fs;                    /* <-- registered here */
    if (opt == 0) return FR_OK;
    res = mount_volume(&path, &fs, 0);  /* <-- only now can it fail */
```

So a **failed** `f_mount` still leaves `FatFs[vol]` pointing at the FATFS and a live sync
object attached to it. `sdcard_mount()`'s failure path then calls
`esp_vfs_fat_unregister_path()`, which frees the `vfs_fat_ctx_t` the FATFS is *embedded
in* — without detaching it. `FatFs[vol]` is now dangling into freed heap, and the sync
object is leaked.

The next mount's `f_mount()` dereferences that stale pointer to tear down what it believes
is the currently-mounted volume — `ff_del_syncobj(cfs->sobj)` — and asserts on a NULL
handle, or faults on garbage.

### Why it looked benign upstream, and why the first fix attempt failed

The stock library only ever mounts `/sd`, so each failed attempt frees and immediately
reallocates a context of identical size, usually at the same address. `FatFs[vol]` then
happens to point at the *new* context and the stale `sobj` field is plausible enough to
survive. **DUT-isolated: six consecutive failed `SD.begin()` calls with no card do not
crash** (heap delta 0, device alive). Introduce a second path with a different context
size — `sdmbr`'s `/sdraw` — and the addresses diverge, so the dangling pointer resolves to
genuinely foreign memory and it panics.

An initial fix that only cleared the stale `card->base_path` (to stop `sdcard_uninit()`
double-unregistering) was **DUT-tested and did not fix it** — that is a real but separate
hygiene bug, not this crash. Kept, because it is still correct.

### Fix

`f_mount(NULL, drv, 0)` — FatFs's own detach, which deletes the sync object and clears the
slot — before `esp_vfs_fat_unregister_path()` on **every** failure path. Plus the
`base_path` clearing above, and the missing unregister on the `f_mkfs` allocation-failure
path, which leaked a registration outright.

Verified on the DUT with no card: three `sdmbr` → `SD.begin()` pairs plus `sdprobe`,
`sdls` and `sdcycle`, zero resets, heap delta 0–36 B, device responsive throughout.

Hardens the stock `SDFS::begin()` failure path, not just the probe — which matters for
`T_SD_10` / LocalPlayer degraded entry, where a missing card is a normal user state.
