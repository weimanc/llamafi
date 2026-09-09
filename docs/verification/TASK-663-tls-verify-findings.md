# TASK-663 — the radio-browser `-120`: what the host can prove, and what only the board can

> Owner: **@Architect** + **@Developer** · Dated **2026-09-08** · Session: the TASK-671 credit run
> Source finding: [phase-2 session review §B.4](reviews/M-TESTQUAL-phase2-session-review.md)
> Method: the board's exact verifier (mbedTLS **2.28.7**, the version Arduino-ESP32 2.0.17 ships)
> built from source on the host and run against the same chain and the same pinned root.

## 1. The claim under test

§B.4: *"the station fetch fails on a cert chain, not on dead mirrors … `openssl` builds that path;
the board's mbedTLS does not."* The chain as served is
`leaf CN=*.radio-browser.info ← YR2 (pathlen:0) ← ISRG Root YR, cross-signed by ISRG Root X1`,
all `sha256WithRSAEncryption`, X1 being the pinned root (`RADIO_BROWSER_ROOT_CA`, fingerprint
`96:BC:EC:06:…:DF:08:C6`, the genuine self-signed X1).

## 2. What was measured

| # | test | result |
|---|---|---|
| 1 | `cert_app` (mbedTLS 2.28.7) offline: the served 3-cert chain vs X1 alone | **ok** |
| 2 | `ssl_client2` (mbedTLS 2.28.7) live TLS 1.2 handshake to `de1.` and `all.`, X1 only, `auth_mode=required` | **handshake ok, peer verified**, ciphersuite ECDHE-RSA-CHACHA20; 3 of 4 attempts; 1 reset by peer |
| 3 | leaf SAN | `*.api.radio-browser.info`, `*.radio-browser.info` — the two-label hostnames are covered |
| 4 | DNS | `all.` and `de1.` both resolve to **one** address, 91.98.4.78 — no backend roulette |
| 5 | the board's `-120` mapping (`dataTaskStorage.cpp:221`) | substituted **only** when `lastError() == -0x2700` — faithful, not a bucket |
| 6 | the board's clock in the failing boot | `[time] synced epoch=1788770424` before the first failure; and `CONFIG_MBEDTLS_HAVE_TIME_DATE` is **not set** — the board's mbedTLS does not check validity dates at all |
| 7 | the board's `-9984` census across all 8 session boots, by endpoint | `accounts.spotify.com` **7–17 per boot, every boot with network**; `dataTask.webradio` 1–9; `dataTask.stock` 5 in one boot (the TASK-344 cert-break injector's test); Yahoo 15×200 in another |
| 8 | what `accounts.spotify.com` serves today | `leaf ← Certainly Intermediate R1 ← Starfield Root Certificate Authority - G2`; the firmware pins **DigiCert Global Root G2** (`SpotifyArduinoCert.h`) |
| 9 | `i.scdn.co` vs its pin | same rot; `api.spotify.com` still chains to DigiCert G2 and **passes** |
| 10 | mirror behaviour toward a burst of handshakes from one host | 2 of 3 `openssl` connects and 1 of 4 mbedTLS connects **reset before ServerHello**; the next connect served the full chain |

## 3. What follows

**3.1 The §B.4 theory is refuted.** The board's own mbedTLS version, with the board's own anchor,
builds and verifies this chain — offline and on the wire. Whatever rejects it on the board is not
"mbedTLS cannot build a cross-signed path". The host preflight's `Verification: OK` was correct;
what it says about the *board* is nothing, and its header now says so.

**3.2 The largest `-9984` population is a rotted Spotify pin, and it is new.** Spotify moved
`accounts.spotify.com` and `i.scdn.co` to its own CA (Certainly, under Starfield Root G2).
`SpotifyArduinoCert.h` pins DigiCert Global Root G2 for both, so **every token refresh fails at
TLS** — `"Refreshing Access Tokens"` is followed by `-9984` in every boot on record. Nothing checked
these pins; `run/check-datatask-certs` now does, and reads **FAIL** on both. Filed **TASK-675**
(P1). Note the interaction with TASK-243: a device that cannot refresh its token cannot tell a
lapsed-Premium 403 from a stale-token 401 by device evidence alone; the host `spotify_state.py`
check stays the arbiter, but the refresh path is broken regardless.

**3.3 The radio-browser `-0x2700` is a device-side discrepancy with no host reproduction.** Same
mbedTLS version, same anchor, same chain: host passes, board fails 100 % (72/72 across boots).
The remaining differences are all on the board — hardware SHA-256 and RSA paths
(`MBEDTLS_SHA256_ALT`, `MBEDTLS_MPI_EXP_MOD_ALT`, `MBEDTLS_MPI_MUL_MPI_ALT`), the board's heap at the
moment of the two RSA-4096 verifies this chain needs (Yahoo's needs none — DigiCert G2 is 2048-bit
— and Yahoo passes on the same board), and whatever the board actually received. The failing
handshakes took 161–639 ms, consistent with an early structural rejection and with a failed
big-number operation; not consistent with a completed verify. **This document does not pick
between them.** Two theories were already asserted on this symptom from one data point each
(TASK-284 "rate limiting", §B.4 "cross-sign"); a third from the host would be the same mistake.

**3.4 The instrument that ends the guessing costs one flash.** `-0x2700` carries a flags word that
names the reason (`NOT_TRUSTED` / `BAD_KEY` / `CN_MISMATCH` / bad signature), and the vendored
`ssl_client.cpp` never printed it on the handshake-failure path. **PATCH-TLS-2** (this session,
`app/lib/WiFiClientSecure/LOCAL_PATCHES.md`) logs `[tls-verify] flags=0x… <text>` at `[E]` on
exactly that path. The next boot that reproduces the failure answers §3.3 in one line: `0x08
NOT_TRUSTED` says the board never saw a path to X1 (what it received, or a failed RSA-4096 op
collapsing into "signature bad" — mbedTLS's `x509_crt_check_signature` returns -1 for *any* pk
error, alloc included); anything else names itself. Flashing the debug env ends a TASK-557
observation window; that is the human's call, and the reason this is filed rather than done.

**3.5 The mirrors do reset handshakes, and that is a separate, real, smaller thing.** Measured on
the host (row 10). It is the plausible face of TASK-284's "comes and goes", it is not a cert result,
and the preflight now labels it as a reset and retries once, paced, instead of reporting a
sandboxed network.

## 4. What changed in the tree (host-only, no flash)

* `run/check-datatask-certs`: endpoints **derived** from `kRadioBrowserMirrors[]` (never `nl1`/`at1`
  again, always `all.`/`de1.`); Spotify's three hosts added against `SpotifyArduinoCert.h`;
  `-verify_hostname`; NXDOMAIN named as such; reset named as such with one paced retry; the
  header's "replicates the exact verification ESP32 performs" corrected to what it can see.
  `app/tools/test_cert_preflight.py` still passes.
* `app/lib/WiFiClientSecure/src/ssl_client.cpp`: PATCH-TLS-2, compiled, **not flashed**.
* This document; TASK-663 and TASK-675 rows.

## 5. Reproducing the host oracle

```sh
curl -sL -o m.tgz https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/v2.28.7.tar.gz && tar xzf m.tgz
make -C mbedtls-2.28.7 -j8 lib && make -C mbedtls-2.28.7/programs ssl/ssl_client2 x509/cert_app
# X1 = RADIO_BROWSER_ROOT_CA parsed out of app/src/dataTaskCerts.h
mbedtls-2.28.7/programs/x509/cert_app mode=file filename=chain.pem ca_file=x1.pem
mbedtls-2.28.7/programs/ssl/ssl_client2 server_name=de1.api.radio-browser.info server_port=443 \
    ca_file=x1.pem auth_mode=required crt_file=none key_file=none min_version=tls12 max_version=tls12
```

## 6. Session record — the TASK-557 window ended on purpose, 2026-09-09

`./run/monitor-read` before the flash: **uptime 39:38:34**, build `Sep 7 2026-19:3x` (the debug
env flashed after session B), `disc=121` flat. Ended by the human's instruction to flash the debug
env for (a) the first transcript recording (TASK-671) and (b) PATCH-TLS-2's flags line. This is the
datum TASK-557 loses (dut_workflow §5a): a 39 h 38 m application-uptime window on the
`-DBOD_WATCH` build with no reset.

**TASK-675 deprioritised** the same day: the human has lost Spotify access, wants the feature kept,
cannot test it now. The two Spotify FAILs in `run/check-datatask-certs` are expected until it lands.

## 7. PATCH-TLS-2 answered on the first boot, 2026-09-09

```
[E][ssl_client.cpp:292] start_ssl_client(): [tls-verify] flags=0x00000008 The certificate is not correctly signed by the trusted CA
[I][dataTask.webradio] GET mirror=all.api.radio-browser.info code=-120 elapsed=359ms
[E][ssl_client.cpp:292] start_ssl_client(): [tls-verify] flags=0x00000008 The certificate is not correctly signed by the trusted CA
[I][dataTask.webradio] GET mirror=de1.api.radio-browser.info code=-120 elapsed=290ms
```

**`BADCERT_NOT_TRUSTED`, and only that**, on both mirrors, every time. Not `CN_MISMATCH`, not
`BAD_KEY`, not a bad-signature-md/pk flag. mbedTLS sets 0x08 when it finds **no parent that
verifies** for the top of the chain it holds: either the cross-signed `Root YR` never reached the
board (the chain it received ends at `YR2`, whose issuer is not X1), or it did and the RSA-4096
signature check against X1 returned non-zero — and `x509_crt_check_signature` folds *any* pk
error, including an allocation failure, into "not signed by this parent". The flag cannot tell
those two apart; the next instrument can, and it is another six lines in the same place: on this
flag, walk `mbedtls_ssl_get_peer_cert()->next` and log the chain length and each subject/issuer.
A 2-cert chain says "the server sent a different chain to this client"; a 3-cert chain says the
board's RSA-4096 verify of the cross cert failed. **No X1-anchored fetch of the two-cert shape
(Weather via `api.open-meteo.com`) ran in this session's logs**, so the cheap discriminator —
"does a chain needing one X1 RSA-4096 verify pass on the board while this one, needing two,
fails" — is still owed: `./run/test-targeted --scope Weather` on the debug env.

The boot-time Spotify token refresh printed the same 0x08 at t=10.7 s — expected, that pin is
rotted (§3.2, TASK-675 deferred).
