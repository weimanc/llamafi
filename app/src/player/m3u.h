#pragma once
// m3u.h — extended-M3U parse + the playlist RAM index (TASK-415, ADR-059 D3).
//
// A playlist must survive being large without a proportional RAM cost, so the
// entries are NOT held in RAM as text. What is held is one immutable index over
// the file plus two permutations of it:
//
//   entries[]   {uint32 offset, uint16 durSec, uint16 flags}   8 B, load-order,
//               subscripts are STABLE ENTRY IDS. Written only by load().
//   viewOrder[] uint16 — what PLEDIT renders and (TASK-421) SAVE writes.
//   playOrder[] uint16 — what playback advances through (TASK-418's shuffle bag).
//
// The split is the whole point: a shuffle expressed as positions into a mutable
// array is invalidated by any reorder, and a shuffle that permutes the index in
// place writes shuffled order back to the card on save. With the split, shuffle
// can only ever touch playOrder, so it provably cannot affect what is shown or
// saved. TASK-415 ships the read-only half — the permutations are built as the
// identity and nothing mutates them yet.
//
// `offset` addresses the START OF THE RECORD, i.e. the `#EXTINF:` line when the
// entry has one and the path line otherwise. Pointing it at the path line would
// make the artist/title unreachable without rescanning from the top of the file.
//
// Row text is composed on demand from the card (a ≤PL_TEXT_CACHE-row cache
// absorbs repaints), never stored per entry — 256 rows of text would be ~24 KB.
//
// Memory: 256 × 8 + 2 × 256 × 2 + 8 × 68 = 3 616 B, all heap, acquired on app
// resume and freed on suspend (mem_manifest.yaml: player_index, player_rowcache).
// The 16-entry staging arena the design budgets is NOT allocated here — nothing
// can stage an entry until TASK-420 adds edit mode.

#include <Arduino.h>
#include <SD.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>   // strncasecmp

#include "logSink.h"
#include "util/asciiFold.h"

namespace m3u {

// ── Sizing ──────────────────────────────────────────────────────────────────
static const uint16_t PL_MAX_ENTRIES = 256;   // ADR-059 D3's budgeted ceiling
static const uint8_t  PL_TEXT_CACHE  = 8;     // ≈ one PLEDIT screen of rows
static const size_t   PL_TEXT_LEN    = 64;    // matches PlRow::text
static const size_t   PL_LINE_MAX    = 160;   // longest line kept whole; longer truncates
static const size_t   PL_PATH_MAX    = 96;    // playlist path / resolved track path

enum PlFlags : uint16_t {
    PLF_EXTINF = 1 << 0,   // record opens with an #EXTINF: line
    PLF_ABS    = 1 << 1,   // path line is '/'-rooted (no directory resolution)
    PLF_STAGED = 1 << 2,   // TASK-420: path lives in the staging arena, not the file
};

struct PlEntry {           // 8 B — see header comment
    uint32_t offset;
    uint16_t durSec;
    uint16_t flags;
};

// Rendered for a record whose path line cannot be read (truncated file, junk).
// A file-scope array, not a static constexpr member: under -std=gnu++11 an
// odr-used static constexpr pointer member needs an out-of-line definition,
// which a header-only class cannot have.
static const char PL_PLACEHOLDER[] = "(unreadable)";

// ── Buffered line reader ────────────────────────────────────────────────────
// File::read() is unbuffered — a byte-at-a-time parse of a 100-track playlist
// is thousands of VFS round trips. This reads in PL_READ_CHUNK blocks and
// hands back whole lines with the file offset each one started at, which is
// exactly what the index needs to store.
class LineReader {
public:
    static const size_t PL_READ_CHUNK = 256;

    // `startOffset` must be a line boundary (0, or an offset this reader
    // previously reported).
    void begin(File* f, uint32_t startOffset) {
        _f = f; _base = startOffset; _len = 0; _idx = 0; _eof = false;
        if (_f) _f->seek(startOffset);
    }

    // Reads one line into `out` (NUL-terminated, CR/LF stripped, truncated to
    // outSize). `lineOffset` receives the byte offset the line started at.
    // Returns false only at end of file with nothing read.
    bool next(char* out, size_t outSize, uint32_t* lineOffset) {
        if (!_f) return false;
        size_t w = 0;
        if (outSize) out[0] = '\0';
        const uint32_t start = _base + _idx;
        bool any = false;
        for (;;) {
            if (_idx >= _len && !_fill()) break;     // EOF
            const char c = (char)_buf[_idx++];
            any = true;
            if (c == '\n') break;
            if (c == '\r') continue;                 // CRLF and lone-CR tolerant
            if (w + 1 < outSize) out[w++] = c;       // overflow silently dropped
        }
        if (outSize) out[w] = '\0';
        if (lineOffset) *lineOffset = start;
        return any;
    }

private:
    bool _fill() {
        if (_eof) return false;
        _base += _len;
        _idx = 0;
        const int n = _f->read(_buf, PL_READ_CHUNK);
        _len = (n > 0) ? (size_t)n : 0;
        if (_len == 0) { _eof = true; return false; }
        return true;
    }

    File*    _f = nullptr;
    uint8_t  _buf[PL_READ_CHUNK];
    size_t   _len = 0, _idx = 0;
    uint32_t _base = 0;
    bool     _eof = true;
};

// ── The index ───────────────────────────────────────────────────────────────
class PlaylistIndex {
public:
    // Heap acquire/release. alloc() is idempotent; free() is safe to call on an
    // un-allocated index (suspend() runs unconditionally).
    bool alloc() {
        if (_entries) return true;
        _entries = (PlEntry*)malloc(sizeof(PlEntry) * PL_MAX_ENTRIES);
        _view    = (uint16_t*)malloc(sizeof(uint16_t) * PL_MAX_ENTRIES);
        _play    = (uint16_t*)malloc(sizeof(uint16_t) * PL_MAX_ENTRIES);
        _cache   = (CacheRow*)malloc(sizeof(CacheRow) * PL_TEXT_CACHE);
        if (!_entries || !_view || !_play || !_cache) {
            LOG_W("m3u", "index alloc FAILED (%u B) — free=%u",
                  (unsigned)bytes(), (unsigned)ESP.getFreeHeap());
            free();
            return false;
        }
        _reset();
        return true;
    }

    void free() {
        _closeFile();
        if (_entries) { ::free(_entries); _entries = nullptr; }
        if (_view)    { ::free(_view);    _view    = nullptr; }
        if (_play)    { ::free(_play);    _play    = nullptr; }
        if (_cache)   { ::free(_cache);   _cache   = nullptr; }
        _reset();
    }

    bool allocated() const { return _entries != nullptr; }

    static size_t bytes() {
        return sizeof(PlEntry) * PL_MAX_ENTRIES
             + sizeof(uint16_t) * PL_MAX_ENTRIES * 2
             + sizeof(CacheRow) * PL_TEXT_CACHE;
    }

    // ── Load ────────────────────────────────────────────────────────────────
    // One pass. Builds entries[] and the identity permutations; leaves the file
    // OPEN for on-demand row reads (the mount's max_files budget is 2: this
    // handle plus the audio decoder's — see main.cpp's kSdMaxFiles).
    //
    // Degrades rather than failing: a truncated file, a missing #EXTINF, a BOM,
    // CRLF or junk comment lines all load what they can (T_PLR_11). Only a file
    // that cannot be opened at all is a hard failure.
    bool load(const char* path) {
        if (!allocated() || !path || !*path) return false;
        const unsigned long t0 = millis();
        _closeFile();
        _reset();
        strlcpy(_path, path, sizeof(_path));
        // The playlist's OWN path gets the same treatment as the track paths
        // inside it — the VFS does not resolve "." or ".." for either, and
        // _deriveDir() below must not derive a directory containing a ".."
        // segment or every relative track in the file inherits it.
        _normalize(_path);
        _deriveDir();

        _f = SD.open(_path, FILE_READ);
        _lastReadMs = millis();
        if (!_f) {
            LOG_W("m3u", "open failed: %s", _path);
            _err = true;
            return false;
        }

        LineReader lr;
        lr.begin(&_f, 0);
        char line[PL_LINE_MAX];
        uint32_t off = 0;
        bool     first = true;
        bool     havePending = false;     // an #EXTINF: is waiting for its path
        uint32_t pendingOff = 0;
        uint16_t pendingDur = 0;

        while (lr.next(line, sizeof(line), &off)) {
            char* s = line;
            if (first) {                                  // strip UTF-8 BOM
                first = false;
                if ((uint8_t)s[0] == 0xEF && (uint8_t)s[1] == 0xBB && (uint8_t)s[2] == 0xBF)
                    s += 3;
            }
            while (*s == ' ' || *s == '\t') s++;
            if (*s == '\0') continue;                     // blank line

            if (*s == '#') {
                if (strncasecmp(s, "#EXTINF:", 8) == 0) {
                    // A second #EXTINF before any path line replaces the first —
                    // the last directive before the path is the one that describes it.
                    havePending = true;
                    pendingOff  = off;
                    const long d = strtol(s + 8, nullptr, 10);
                    pendingDur  = (d > 0 && d < 65535) ? (uint16_t)d : 0;
                }
                continue;                                 // #EXTM3U and all other directives
            }

            if (_count >= PL_MAX_ENTRIES) {
                _truncated = true;
                break;
            }
            PlEntry& e = _entries[_count];
            e.offset = havePending ? pendingOff : off;
            e.durSec = havePending ? pendingDur : 0;
            e.flags  = (uint16_t)((havePending ? PLF_EXTINF : 0) | (*s == '/' ? PLF_ABS : 0));
            _view[_count] = _count;                       // identity until TASK-420 reorders
            _play[_count] = _count;                       // identity until TASK-418 shuffles
            _totalSec += e.durSec;
            _count++;
            havePending = false;
            pendingDur  = 0;
        }

        _loadMs = millis() - t0;
        LOG_I("m3u", "loaded %s: %u entries%s in %lums (total %lus)",
              _path, (unsigned)_count, _truncated ? " (TRUNCATED)" : "",
              (unsigned long)_loadMs, (unsigned long)_totalSec);
        if (_count == 0) LOG_W("m3u", "no playable entries in %s", _path);
        return true;
    }

    // ── Read-side accessors (all take VIEW indices) ─────────────────────────
    uint16_t count()    const { return _count; }
    uint32_t totalSec() const { return _totalSec; }
    uint32_t loadMs()   const { return _loadMs; }
    bool     truncated()const { return _truncated; }
    bool     error()    const { return _err; }
    const char* path()  const { return _path; }
    const char* dir()   const { return _dir; }

    uint16_t idAt(uint16_t viewIdx) const {
        return (viewIdx < _count) ? _view[viewIdx] : 0;
    }
    uint16_t durationAt(uint16_t viewIdx) const {
        return (viewIdx < _count) ? _entries[_view[viewIdx]].durSec : 0;
    }
    // playOrder position -> view-order row.
    uint16_t playRowAt(uint16_t playIdx) const {
        if (playIdx >= _count) return 0;
        const int16_t r = viewRowOfId(_play[playIdx]);
        return (r >= 0) ? (uint16_t)r : 0;
    }

    // ── TASK-418 / ADR-059 D9 — the shuffle bag ─────────────────────────────
    // playOrder[] is a Fisher-Yates permutation of the CURRENT view ids
    // (§2: shuffle never touches viewOrder, so this provably cannot affect
    // what PLEDIT shows or what SAVE writes). Rebuilt from _view fresh every
    // call rather than permuting whatever _play last held, so a shuffle
    // toggled on after an edit (TASK-420+) always reflects the live list —
    // there is no stale membership to repair.
    //
    // `avoidId` is the guard against the reshuffle-on-wrap annoyance (design
    // §8): a track that just finished must not immediately re-open the next
    // cycle. Pass an id outside the entries[] domain (e.g. 0xFFFF) to skip
    // the guard, which toggle-ON does — nothing has "just finished" yet.
    void shuffleReset(uint16_t avoidId) {
        if (!_play || !_view || _count == 0) return;
        for (uint16_t i = 0; i < _count; i++) _play[i] = _view[i];
        // Fisher-Yates, standard backward walk: for i from count-1 down to 1,
        // swap _play[i] with _play[random(0..i)].
        for (uint16_t i = _count - 1; i > 0; i--) {
            const uint16_t j = (uint16_t)random(0, i + 1);
            const uint16_t tmp = _play[i]; _play[i] = _play[j]; _play[j] = tmp;
        }
        if (_count > 1 && _play[0] == avoidId) {
            const uint16_t j = (uint16_t)random(1, _count);
            const uint16_t tmp = _play[0]; _play[0] = _play[j]; _play[j] = tmp;
        }
    }

    // Raw playOrder dump (ids), for `get plOrder` (ADR-059 D12) and for
    // T_PLR_20-24's collision/history checks.
    const uint16_t* playOrder() const { return _play; }
    // M-TESTBASE P2 / X062: viewOrder had NO accessor at all — _view was private
    // with only idAtView()/viewRowOfId(), so "what PLEDIT renders and what SAVE
    // writes" could not be observed even in principle. NOTE the standing caveat:
    // _view is identity until TASK-420 lands a reorder mutator, so today this
    // reads as 0..n-1 by construction. Exposing it now is what lets T_PLR_30
    // become writable the moment TASK-424/420 unblock it.
    const uint16_t* viewOrder() const { return _view; }
    uint16_t idAtPlayPos(uint16_t pos) const { return (pos < _count) ? _play[pos] : 0; }
    // Linear scan is fine at PL_MAX_ENTRIES=256 (same trade-off playRowAt/
    // viewRowOfId already make) — tap-to-play and prev/next are user-paced,
    // not a per-frame hot path.
    int16_t playPosOfId(uint16_t id) const {
        for (uint16_t i = 0; i < _count; i++) if (_play[i] == id) return (int16_t)i;
        return -1;
    }
    int16_t viewRowOfId(uint16_t id) const {
        for (uint16_t i = 0; i < _count; i++) if (_view[i] == id) return (int16_t)i;
        return -1;
    }
    uint16_t idAtView(uint16_t viewIdx) const { return (viewIdx < _count) ? _view[viewIdx] : 0; }

    // Display text for a row, ASCII-folded (design OQ1) and cached. Never
    // fails visibly: an unreadable record renders the placeholder so a bad row
    // is distinguishable from an empty list.
    void rowText(uint16_t viewIdx, char* out, size_t outSize) {
        if (outSize == 0) return;
        out[0] = '\0';
        if (viewIdx >= _count) { strlcpy(out, PL_PLACEHOLDER, outSize); return; }
        const uint16_t id = _view[viewIdx];

        for (uint8_t i = 0; i < PL_TEXT_CACHE; i++) {
            if (_cache[i].valid && _cache[i].id == id) { strlcpy(out, _cache[i].text, outSize); return; }
        }

        char text[PL_TEXT_LEN];
        if (!_composeText(id, text, sizeof(text))) strlcpy(text, PL_PLACEHOLDER, sizeof(text));

        CacheRow& c = _cache[_cacheNext];
        _cacheNext = (uint8_t)((_cacheNext + 1) % PL_TEXT_CACHE);
        c.valid = true;
        c.id    = id;
        strlcpy(c.text, text, sizeof(c.text));
        strlcpy(out, text, outSize);
    }

    // Playable path for a row, resolved against the playlist's directory when
    // relative (T_PLR_10). Returns false if the record can't be read.
    bool pathAt(uint16_t viewIdx, char* out, size_t outSize) {
        if (viewIdx >= _count || outSize == 0) return false;
        char raw[PL_PATH_MAX];
        if (!_readRecord(_view[viewIdx], nullptr, 0, raw, sizeof(raw))) return false;
        return _resolve(raw, out, outSize);
    }

    // Release the open playlist File once nothing has read a row for `idleMs`.
    // Call from the app's tick().
    //
    // Holding the handle open is what makes scrolling affordable — a velocity
    // scroll repaints ~30 times a second and each repaint reads up to 8 rows,
    // so re-opening per read would be hundreds of FAT directory lookups per
    // second, on loopTask, against the audio pump. But an open file is NOT
    // free: newlib gives every `FILE*` a stdio buffer sized from the VFS's
    // st_blksize, which FATFS reports as 4 096 — measured at ~4.4 KB of heap
    // per open handle, more than the entire index. Paying that while the user
    // stares at a static list would put the mode 8 KB over the 5.2 KB the
    // design budgets (T_PLR_12), for nothing.
    //
    // So: open lazily on the first read, keep it open across a burst of reads,
    // drop it when the burst ends. reopen is transparent — every read path
    // goes through _ensureOpen().
    void closeIfIdle(uint32_t idleMs) {
        if (!_f || _lastReadMs == 0) return;
        if (millis() - _lastReadMs < idleMs) return;
        _f.close();
        _lastReadMs = 0;
    }

    bool fileOpen() const { return (bool)_f; }

    // Row text changed underneath us (a mutation, TASK-420) — drop the cache.
    void invalidateText() {
        if (!_cache) return;
        for (uint8_t i = 0; i < PL_TEXT_CACHE; i++) _cache[i].valid = false;
        _cacheNext = 0;
    }

private:
    struct CacheRow { uint16_t id; bool valid; char text[PL_TEXT_LEN]; };  // 68 B

    void _reset() {
        _count = 0; _totalSec = 0; _loadMs = 0;
        _truncated = false; _err = false;
        _cacheNext = 0;
        _path[0] = '\0'; _dir[0] = '\0';
        if (_cache) for (uint8_t i = 0; i < PL_TEXT_CACHE; i++) _cache[i].valid = false;
    }

    void _closeFile() { if (_f) _f.close(); _lastReadMs = 0; }

    // Re-open the playlist after closeIfIdle() dropped it. A load() that failed
    // to open in the first place left _path set but _err true; retrying here is
    // deliberate — a card re-seated between reads should recover rather than
    // leave the list permanently blank.
    bool _ensureOpen() {
        if (_f) return true;
        if (!_path[0]) return false;
        _f = SD.open(_path, FILE_READ);
        return (bool)_f;
    }

    // Directory of _path, with trailing slash ("/mp3/"). Root stays "/".
    void _deriveDir() {
        strlcpy(_dir, _path, sizeof(_dir));
        char* slash = strrchr(_dir, '/');
        if (!slash) { strlcpy(_dir, "/", sizeof(_dir)); return; }
        slash[1] = '\0';                       // keep the slash itself
    }

    bool _resolve(const char* raw, char* out, size_t outSize) {
        if (!raw || !*raw) return false;
        if (raw[0] == '/') strlcpy(out, raw, outSize);
        else               snprintf(out, outSize, "%s%s", _dir, raw);
        _normalize(out);
        return out[0] != '\0';
    }

    // Collapse "." and ".." segments in place.
    //
    // The first cut of this deliberately did NOT collapse, on the reasoning that
    // FatFs would do it and a second path parser is a second thing to get wrong.
    // That was measured false on the DUT (T_PLR_10, 2026-08-11): the ESP-IDF
    // FATFS VFS passes the path through untouched and
    // `/playlists/../mp3/x.mp3` fails to open, while `/mp3/x.mp3` opens fine.
    // A playlist one directory up from its media is an ordinary layout, so the
    // collapse has to happen here.
    //
    // ".." at the root is dropped rather than escaping ("/../x" -> "/x"), the
    // same clamp every real path resolver applies.
    static void _normalize(char* p) {
        if (!p || p[0] != '/') return;
        char*       w = p;            // write cursor, AT the leading '/'
        const char* r = p + 1;        // read cursor
        while (*r) {
            const char* seg = r;
            while (*r && *r != '/') r++;
            const size_t len = (size_t)(r - seg);
            if (*r == '/') r++;
            if (len == 0) continue;                       // "//"
            if (len == 1 && seg[0] == '.') continue;      // "/./"
            if (len == 2 && seg[0] == '.' && seg[1] == '.') {
                if (w > p) {                              // pop the last segment
                    w--;                                  // onto its last character
                    while (w > p && *w != '/') w--;       // back to its leading '/'
                }
                continue;                                 // ".." at root is dropped
            }
            // The separator is written BEFORE the segment, never after it. The
            // append-then-trim shape is the obvious one and is wrong: writing
            // the trailing '/' lands exactly on the string's NUL terminator on
            // the final segment, which the read cursor is still sitting on, so
            // the loop reads on into whatever follows in memory and emits a path
            // with heap garbage glued to the end. Caught by T_PLR_11 on the DUT
            // ("/mp3/02 - Clint Eastwood.mp3/<garbage>") — and only sometimes,
            // since it depends on the next byte being non-zero.
            *w++ = '/';
            memmove(w, seg, len);     // w <= seg always: never clobbers unread input
            w += len;
        }
        if (w == p) *w++ = '/';       // everything collapsed away -> "/"
        *w = '\0';
    }

    // Reads a record: optionally its display text (from #EXTINF, else the file
    // basename) and optionally its raw path line. Either output may be NULL.
    bool _readRecord(uint16_t id, char* textOut, size_t textSize,
                     char* pathOut, size_t pathSize) {
        if (id >= _count || !_ensureOpen()) return false;
        _lastReadMs = millis();
        LineReader lr;
        lr.begin(&_f, _entries[id].offset);
        char line[PL_LINE_MAX];
        uint32_t off = 0;
        char extinf[PL_LINE_MAX];
        extinf[0] = '\0';

        // At most a handful of lines: the #EXTINF (if any), then any stray
        // directives, then the path. Bounded so a malformed file can't spin.
        for (int guard = 0; guard < 8; guard++) {
            if (!lr.next(line, sizeof(line), &off)) break;
            char* s = line;
            while (*s == ' ' || *s == '\t') s++;
            if (*s == '\0') continue;
            if (*s == '#') {
                if (strncasecmp(s, "#EXTINF:", 8) == 0) {
                    const char* comma = strchr(s + 8, ',');
                    strlcpy(extinf, comma ? comma + 1 : "", sizeof(extinf));
                }
                continue;
            }
            // Path line — the record ends here. Trailing whitespace must go:
            // FAT will not open "/mp3/x.mp3   ", and a hand-edited playlist
            // picks up stray spaces easily. (Leading whitespace was already
            // skipped above; this is the other half of the same trim.)
            {
                char* end = s + strlen(s);
                while (end > s && (end[-1] == ' ' || end[-1] == '\t')) *--end = '\0';
            }
            if (pathOut && pathSize) strlcpy(pathOut, s, pathSize);
            if (textOut && textSize) {
                if (extinf[0]) {
                    textfold::foldUtf8(extinf, textOut, textSize);
                } else {
                    _basename(s, textOut, textSize);
                }
                if (textOut[0] == '\0') return false;
            }
            return true;
        }
        return false;   // truncated record — no path line
    }

    bool _composeText(uint16_t id, char* out, size_t outSize) {
        return _readRecord(id, out, outSize, nullptr, 0);
    }

    // "/mp3/01 - Song.mp3" -> "01 - Song", ASCII-folded.
    void _basename(const char* p, char* out, size_t outSize) {
        const char* slash = strrchr(p, '/');
        const char* base  = slash ? slash + 1 : p;
        char tmp[PL_PATH_MAX];
        strlcpy(tmp, base, sizeof(tmp));
        char* dot = strrchr(tmp, '.');
        if (dot && dot != tmp) *dot = '\0';
        textfold::foldUtf8(tmp, out, outSize);
    }

    PlEntry*  _entries = nullptr;
    uint16_t* _view    = nullptr;
    uint16_t* _play    = nullptr;
    CacheRow* _cache   = nullptr;
    uint8_t   _cacheNext = 0;

    File      _f;
    char      _path[PL_PATH_MAX] = {0};
    char      _dir[PL_PATH_MAX]  = {0};
    uint16_t  _count = 0;
    uint32_t  _totalSec = 0;
    uint32_t  _loadMs = 0;
    bool      _truncated = false;
    bool      _err = false;
    uint32_t  _lastReadMs = 0;   // 0 = no handle held; see closeIfIdle()
};

}  // namespace m3u
