# WiFiClientSecure — local patches

Vendored copy of the Arduino-ESP32 `WiFiClientSecure` library (framework
`espressif32@6.9.0` / Arduino-ESP32 2.0.17). Patches are marked inline with a
`PATCH-…` comment at the site. Re-apply all of them after any platform bump —
same rule as `app/lib/SD/LOCAL_PATCHES.md`.

Numbering note: the existing `PATCH-003` marker in `ssl_client.cpp` predates the
`PATCH-<lib>-<n>` convention used by `app/lib/SD`, and it is unrelated to the
`PATCH-003` in `docs/architecture/designs/M-MULTIAPP/upstream-patches.md` (which
tracks patches to the `Spotify-Diy-Thing/` upstream, a different tree). New
patches to this library use the `PATCH-TLS-<n>` form.

---

## PATCH-TLS-1 — `stop()` must release its socket with `lwip_close()` (TASK-424)

**File**: `src/WiFiClientSecure.cpp`, `WiFiClientSecure::stop()`.

**Upstream defect** (present verbatim in the framework copy — the vendored file
was byte-identical here before this patch, so this is not a local divergence).

`sslclient->socket` is an **lwIP socket number**. Every other socket call in this
library is namespace-consistent with that: `start_ssl_client()` allocates with
`lwip_socket()`, its error paths and stale-socket guard release with
`lwip_close()`, and so does `stop_ssl_socket()`. `stop()` alone used the plain
`close()` — the **VFS** close, a different namespace.

The two namespaces overlap at the bottom. `LWIP_SOCKET_OFFSET` is
`FD_SETSIZE - CONFIG_LWIP_MAX_SOCKETS`, and `FD_SETSIZE` is `MEMP_NUM_NETCONN`,
so the offset is **0**: lwIP hands out socket 0 first. VFS descriptors also start
at 0, and this firmware leaves fd 0 free, so the *first file it opens* is VFS
fd 0 — measured directly, an SD file opened on a clean boot reports `fd:0`.

So `stop()` on lwIP socket 0 executes `close(0)` against the VFS, closing an
unrelated open file. That lands in `vfs_fat_close()`, which `f_close()`es the
file and `memset`s its `FIL` to zero. For a write in flight that means:

* `obj.fs == NULL` → `validate()` returns `FR_INVALID_OBJECT` → `f_write()`
  returns 0 with **no** `sd_diskio` error — TASK-424's "accepted but not
  delivered" silent truncation; and
* if the freed slot is re-opened underneath the same pointer, the next
  `f_write()` faults in `validate()` (`ff.c:3465`) with `EXCVADDR=0x00000001` —
  TASK-424's panic.

**Fix**: `lwip_close(sslclient->socket)`, matching the rest of the library.

**Evidence** (DUT, 2026-09-01, `cyd2usb_winamp_debug`): the `sdfilwatch` probe
(`app/src/debug/serialConsole/cmdSd.cpp`) caught the FIL going all-zero mid-write
with `fdCheck:-1 fd:0 errno:9 (EBADF)`; a temporary `-Wl,--wrap=close` shim
named the caller as `WiFiClientSecure::stop()` in this file,
running on `spotifyTask`. Full record in TASK-424.

**Not the cause, checked and ruled out**: `ssl_init()` leaving `socket` at 0
through its `memset`. Both constructors assign `socket` immediately afterwards
(`-1`, or the passed socket), so the context is never left at 0 by that path — a
patch there was tried first and changed nothing on the DUT.

---

## PATCH-003 — close the stale socket before creating a new one

**File**: `src/ssl_client.cpp`, `start_ssl_client()`.

Pre-existing patch, marked inline. Without it an internal library retry calls
`start_ssl_client()` again and `lwip_socket()` overwrites `sslclient->socket`
without closing the old fd. After ~8 leaked fds the 16-slot lwIP socket table is
exhausted and every subsequent `lwip_socket()` fails with `EAGAIN`/`errno=11`.
