# Publishing to the public remote — the checklist

> Owner: **@PM** · Written 2026-09-26 · Governs every push of this repo to `public`
> (`git@github.com:weimanc/llamafi.git`). Until this file existed the procedure lived only in one
> agent's memory note; a procedure that is not in the repo is one a fresh session cannot follow.

**Scope.** `master` is local-only by default (CLAUDE.md: work on master directly, never push without
approval). The public repo carries **both** `main` (GitHub's default) and `master`, pushed together.
Anything in a pushed commit — tree **or message** — is public for good: history rewrites after the
fact do not un-publish it.

**This file names no secret.** The home SSID is read from the gitignored config at sweep time (§2).
Never paste a real SSID, coordinate or token into this file, a board row, a commit message or a log.

---

## 0. Approval

- [ ] The human has said, in this session, to push. Approval for one push is not approval for the next.
- [ ] Nothing is pushed by an agent on its own initiative, including "just to sync".

## 1. Know the range

```sh
git fetch public
git rev-list --count public/master..master      # commits to publish
git rev-list --count master..public/master      # must be 0; if not, stop — the remote moved
git diff --stat public/master master | tail -1
```

- [ ] Remote is not ahead of local. Record the count and file totals in the push note (§8).
- [ ] Working tree clean (`git status --short` empty).

## 2. Privacy and secrets sweep — of added lines AND commit messages

The recurring leak vector is a raw DUT capture (`get wifiSaved`, `get wifi`, heartbeat `ssid=`, a
scan list) pasted into a doc, a board row or a commit message. Sweep the whole range, not only the tip.

```sh
R=public/master..master
# SSIDs are derived from the gitignored device config, never typed here.
SSIDS=$(python3 - <<'PY'
import json, glob
out = set()
for f in glob.glob('app/data/wifi_*.json'):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    rows = d.get('networks', [d]) if isinstance(d, dict) else d
    for r in rows:
        if isinstance(r, dict) and r.get('ssid'):
            out.add(r['ssid'])
print('|'.join(sorted(out)))
PY
)
[ -n "$SSIDS" ] || { echo "NO SSID PATTERN — sweep would be blind, stop"; exit 1; }
# Match the base name too: the AP was renamed once, and logs carry both spellings.
git log -p --no-color -U0 $R | grep -E '^\+' | grep -cE "$SSIDS"      # added lines
git log --format='%h %B' $R | grep -cE "$SSIDS"                        # commit messages
```

| # | Check | Expect |
|---|---|---|
| S1 | Home SSID (every spelling) in added lines **and** commit messages | 0 |
| S2 | Tokens: `clientSecret`/`refreshToken` with a value, `Bearer <x>`, `AKIA…`, `ghp_…`, `BEGIN … PRIVATE KEY` | 0 |
| S3 | Precise home coordinates. The public Amsterdam compile default is fine; a city-precision value is fine; anything with 4+ decimals near the real home is not | 0 |
| S4 | Postcodes or street addresses outside the documented provider-capability matrix in `geocode_probe.py` | 0 |
| S5 | Tracked secret-bearing files: `git ls-files \| grep -E 'wifi_creds\|spotify_diy_config\|authBlob\|\.env'` shows only `*.example` | only examples |
| S6 | Absolute home paths `/home/<user>` in added lines | review each; redact if avoidable |
| S7 | Device MACs, RFC1918 addresses | low sensitivity — note, redact if convenient |
| S8 | **Binary files** added in the range (`git diff --numstat public/master master \| awk '$1=="-"'`) — sweep is text-only, so list and eyeball them | reviewed |

- [ ] S1–S5 are zero, or every hit is explained in the push note as a false positive (say why).
- [ ] The sweep output is kept in the scratchpad, **not** committed — it contains the patterns' hits.

**A regex hit is a lead, not a verdict.** The 2026-08-02 sweep's `52.37x`/`4.92x` hit was a PlaneRadar
`dst` distance field. Read the line before deciding either way.

### If S1–S5 find something

- **Unpushed (the normal case): rewrite the local history.** Back up first
  (`git branch backup/pre-publish-$(date +%F) master`), then redact with `git filter-repo` or an
  interactive rebase — replace the value with `<home-ssid>` (or the coordinate with city precision),
  in **both** the tree and the commit message. A redaction commit on top leaves it in public history.
- **Already pushed: tree-only redaction on top** is all that is left, and it is a disclosure that
  already happened — say so; do not present it as fixed.
- After any rewrite, **re-run the whole sweep**, then re-run §3: hashes changed, so anything that
  cites a landing hash on a board row now points at nothing.
  Check with `~/proj/esp/venv/bin/python app/tools/gate/check_board_currency.py`.

## 3. Gates

```sh
./run/check                                   # 11 gates; exit 0 required
./run/check-docs
~/proj/esp/venv/bin/python app/tools/gate/check_board_currency.py    # SEPARATE gate — not inside check-docs
```

- [ ] `run/check` exits 0 (11/11).
- [ ] `run/check-docs` and `check_board_currency` both pass.
- [ ] A red gate that **fails only because no board is attached** is an environment finding, not a
      pass: re-run with the DUT on the bench, or file the non-hermetic test. Do not push over it
      unexplained. (2026-09-26: `test_serial_classify.py` hard-codes a by-id device path and fails
      with the board unplugged.)

## 4. Licence

- [ ] Vendored trees keep their upstream licence files (`app/lib/SD`, `app/lib/WiFiClientSecure`,
      `LOCAL_PATCHES.md` alongside).
- [ ] **Open since the first publish: a licence scan (ScanCode or FOSSA) against committed files was
      never run.** A human decision — record "run" or "deferred, by <who>, <date>" in the push note.

## 5. Public-facing accuracy

- [ ] `README.md` still describes what the firmware does (it drifted before: Teletext's "country-
      selectable" claim survived the M-CEEFAX cut).
- [ ] Nothing in the range publishes a claim the board contradicts (`check_board_currency` covers
      the mechanical part; read the diff of `README.md` and `docs/project/roadmap.md` yourself).

## 6. Push — both branches, together

```sh
git push public master:master master:main
```

- [ ] Never `--force`. If the push is rejected, the remote moved: stop and re-do §1.
- [ ] Not pushed: `rnd/*` branches. R&D work stays local unless the human says otherwise.

## 7. After the push

- [ ] `git fetch public && git rev-parse public/master public/main master` — all three equal.
- [ ] Spot-check the pushed repo in a browser: `README.md` renders, no file you did not expect.

## 8. Record it

Add one line here in the log below **in the same commit series as the next work**, not as an
afterthought — date, tip hash, range size, sweep outcome, licence-scan status.

| Date | Tip | Range | Sweep | Licence scan |
|---|---|---|---|---|
| 2026-07-18 | `69eb581` | 430 commits | 3 doc sites redacted (coords), SSID → `<home-ssid>` in 4 files, tree-only | not run |
| 2026-08-02 | `50197f4`, `e943dac` | +137, then README fix | clean | not run |
| 2026-08-07 | `8a499a1` | +62 | SSID leak found **pre-push** (`e824e14`), fixed by rebase | not run |

---

## Why the checklist is shaped this way

- **The SSID is the recurring failure** (leaked 2026-07-18, caught pre-push 2026-08-07, found in 17
  commits and 7 messages on 2026-09-26). Each time the source was a raw DUT capture. §2 therefore
  derives the pattern from the device config instead of trusting a list someone maintains, and refuses
  to run blind.
- **Messages are swept as well as trees.** A tree redaction does not touch a commit message.
- **Rewrite before, disclose after.** Pre-push is the only time redaction actually works.
- **A green gate that could not run is not green** (§3) — the same rule the test harness applies to
  its own verdicts.
