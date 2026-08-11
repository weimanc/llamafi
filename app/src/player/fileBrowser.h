#pragma once
// fileBrowser.h — TASK-416: modal SD directory browser for LocalPlayerApp,
// entered via eject (design §4/§6, ADR-059 D6).
//
// Reuse, not rebuild: built on settings/settingsWidgets.h's SPickerList,
// generalised in this same task off its CountryEntry-specific shape to a
// row-accessor callback pair (DEV-3) — the scrollbar, drag handling, offset
// clamping, highlight and CP-1 full-phase-takeover contract are the expensive
// parts, and none of them care about the item type. This header is the
// browser's OWN client of that generalised widget; the country picker
// (settings/appsSection.h's `_countryRowText`/`_countryRowMatches`) is the
// other.
//
// Directory walk: SD.open(dir) + File::openNextFile(), one directory level at
// a time, paged at ≤FB_BATCH entries per tick() call so loopTask never stalls
// the audio pump — see FB_BATCH's comment for the TASK-408 measurement this is
// tuned from. Directories first, then .mp3/.m3u files, natural FAT order — no
// sort buffer (design §4): a single walk pass buckets each entry into the
// _dirs[]/_files[] array it belongs to as it is encountered, so within each
// bucket the on-disk order is preserved with no comparison sort at all. The
// two buckets ARE held in RAM (heap, alloc()/free() like m3u::PlaylistIndex —
// re-seeking via openNextFile() from the top on every scroll/repaint would be
// hundreds of FAT lookups per second against the audio pump, the exact thing
// batching exists to prevent), which is a paging cache, not the sort buffer
// the design explicitly rules out.
//
// Concurrency (design §9 / NEW-APP-CHECKLIST items 1+4): pending() backs the
// host's hasPendingAsync() while a page walk is in flight, and isBackZone()
// backs isNavigationTap() so the shell's busy gate does not swallow a tap on
// the browser's own back/up zone while a page is still loading — the TASK-384
// defect class, confirmed on real hardware there, not just the harness.

#include <Arduino.h>
#include <SD.h>
#include <string.h>

#include "logSink.h"
#include "player/m3u.h"
#include "settings/settingsWidgets.h"
#include "touchPhase.h"

extern bool sdReady();   // main.cpp — the boot mount's outcome (TASK-408/427)

namespace player {

class FileBrowser {
public:
    // LocalPlayerApp implements this — kept as a raw interface (not a
    // callback pair) because both actions need more than an (idx, ctx) shape:
    // a resolved path and a decision about what kind of file it is.
    struct Delegate {
        virtual void fbPlayFile(const char* path)     = 0;   // tap on an .mp3
        virtual void fbLoadPlaylist(const char* path) = 0;   // tap on an .m3u
        virtual ~Delegate() = default;
    };

    // Sizing note (found on the DUT, T_PLR_06, 2026-08-11): the naive
    // FB_NAME_LEN=40/FB_MAX_FILES=224 first cut truncated real filenames —
    // this card's /mp3 has "14 - Clint Eastwood (Ed Case & Sweetie Irie
    // Refix).mp3", 56 characters — and a truncated STORED name breaks path
    // reconstruction (opens the wrong/nonexistent file), which is worse than
    // capping the entry COUNT (the m3u.h PL_MAX_ENTRIES/_truncated precedent:
    // degrade by dropping trailing entries, never by corrupting a kept one).
    // So NAME_LEN went up, not down, and MAX_FILES/MAX_DIRS came down to
    // compensate: same DUT run measured a real `alloc FAILED (11 520 B) —
    // free=50 700` after a Spotify+WebRadio leg fragmented the heap (WebRadio's
    // own ~40 KB working set, released on suspend() but not necessarily
    // returned as one contiguous block — the M-HEAP-FRAGMENTATION class of
    // risk this project already tracks elsewhere, not new to this task). This
    // sizing does not eliminate that risk — nothing short of not allocating
    // does — it only keeps the ask as small as correctness allows. alloc()
    // failure degrades cleanly (hasError(), no crash) exactly like
    // m3u::PlaylistIndex::alloc() failing does.
    //
    // Cut further (T_PLR_13 on cyd2usb_player, 2026-08-11): 48/160 (13 312 B)
    // still failed WHILE A TRACK WAS PLAYING — the Helix arena's own 24 576 B
    // contiguous grab plus the Audio object leaves less, and more fragmented,
    // headroom than the browsing-only case T_PLR_06 first found this on. This
    // card's real content (53 files in /mp3, 11 entries at root) is nowhere
    // near either of these caps, so the smaller numbers cost nothing today —
    // they only reduce, not eliminate, the alloc-under-fragmentation risk.
    // Cut a third time (T_PLR_13 on cyd2usb_player WHILE A TRACK PLAYS,
    // 2026-08-11): 24/96 (7 680 B) still failed with the arena held AND the
    // Audio object AND its pump task all resident — `free=46020` total but
    // no single ~7.7 KB contiguous run. This is the concurrent-use case the
    // design's own §4/§9 name explicitly (browsing while playing), so it is
    // the realistic floor, not a synthetic worst case. Coming down further
    // trades away real capability (this card's /mp3 has 53 files; 48 would
    // already truncate it) for a fragmentation risk that array-shrinking
    // alone cannot fully close — see the note above this block.
    static const uint16_t FB_MAX_DIRS  = 16;
    static const uint16_t FB_MAX_FILES = 64;
    static const size_t   FB_NAME_LEN  = 64;    // basename only; matches PlRow::text's 64

    // TASK-408's T_SD_07 measured 26.4 ms/entry walking a 200-file directory
    // (openNextFile() stats every entry to resolve isDirectory() — there is no
    // cheaper walk to ask for). 4 entries/tick is ~106 ms worst case, under
    // the ~160 ms the 6 400 B InBuff can absorb at 320 kbps before an audible
    // underrun (design §4's 2026-08-08 revision — the original "≤32/tick" in
    // the task text is superseded by this correction; do not raise it back).
    static const uint8_t FB_BATCH = 4;

    void bind(Delegate* d) { _delegate = d; }

    bool alloc() {
        if (_dirs) return true;
        _dirs  = (FBEntry*)malloc(sizeof(FBEntry) * FB_MAX_DIRS);
        _files = (FBEntry*)malloc(sizeof(FBEntry) * FB_MAX_FILES);
        if (!_dirs || !_files) {
            LOG_W("filebrowser", "alloc FAILED (%u B) — free=%u",
                  (unsigned)bytes(), (unsigned)ESP.getFreeHeap());
            free();
            return false;
        }
        return true;
    }

    void free() {
        _closeDir();
        if (_dirs)  { ::free(_dirs);  _dirs  = nullptr; }
        if (_files) { ::free(_files); _files = nullptr; }
        _picker.hide();
        _state = State::Idle;
        _dir[0] = '\0';
        _dirCount = _fileCount = 0;
    }

    static size_t bytes() { return sizeof(FBEntry) * ((size_t)FB_MAX_DIRS + FB_MAX_FILES); }

    bool allocated() const { return _dirs != nullptr; }
    bool active()    const { return _picker.active(); }
    bool pending()   const { return _state == State::Walking; }
    bool isBackZone(int x, int y) const { return _picker.isBackZone(x, y); }
    const char* dir() const { return _dir; }

    // Opens (or re-opens, for descend/ascend) `dir` as the current listing.
    bool open(const char* dir) {
        if (!_dirs && !alloc()) return false;
        if (!sdReady()) { LOG_W("filebrowser", "no SD card mounted"); return false; }
        _closeDir();
        char norm[m3u::PL_PATH_MAX];
        strlcpy(norm, (dir && dir[0]) ? dir : "/", sizeof(norm));
        // SD.open()'s FILE_READ path is a stat, and the ESP-IDF FATFS VFS
        // fails that stat on a path ending in '/' — "does not exist, no
        // permits for creation" — even though the SAME directory lists fine
        // via openNextFile() once opened without it. Caught on the DUT
        // (T_PLR_16, 2026-08-11): a directory-tap descend builds its target
        // WITH a trailing slash (so _dir is always ready as a path-concat
        // prefix — see below), and passing that straight to SD.open() broke
        // every second-level descend. Strip it for the open() call only; the
        // root "/" itself must not become an empty string.
        {
            size_t nn = strlen(norm);
            if (nn > 1 && norm[nn - 1] == '/') norm[nn - 1] = '\0';
        }
        _dh = SD.open(norm, FILE_READ);
        if (!_dh || !_dh.isDirectory()) {
            if (_dh) _dh.close();
            LOG_W("filebrowser", "open failed: %s", norm);
            return false;
        }
        strlcpy(_dir, norm, sizeof(_dir));
        // Trailing slash kept so every path build below is a plain concat —
        // the same idiom m3u::PlaylistIndex::_deriveDir() uses.
        size_t n = strlen(_dir);
        if (n == 0 || _dir[n - 1] != '/') {
            if (n + 1 < sizeof(_dir)) { _dir[n] = '/'; _dir[n + 1] = '\0'; }
        }
        _dirCount = 0;
        _fileCount = 0;
        _state = State::Walking;
        // count=0 — tick() grows it via updateCount() as entries are found,
        // so the first screen paints from the first batch rather than
        // waiting for the whole directory (design §4 point 2).
        _picker.show(0, _dir, nullptr, _sRowText, nullptr, _sOnSelect, _sOnCancel, this);
        LOG_I("filebrowser", "browsing %s", _dir);
        return true;
    }

    void handleInput(TouchPhase phase, int x, int y) { _picker.handleInput(phase, x, y); }

    // Call from the host's tick(). Continues the paged walk, ≤FB_BATCH
    // openNextFile() calls per invocation.
    void tick() {
        if (_state != State::Walking) return;
        for (uint8_t i = 0; i < FB_BATCH; i++) {
            File e = _dh.openNextFile();
            if (!e) { _finish(); break; }
            _classify(e);
            e.close();
        }
        if (_state == State::Walking) _picker.updateCount((int16_t)(_dirCount + _fileCount));
    }

#ifdef SERIAL_DEBUG
    // ── Debug surface (ADR-059 D12: shipped with the feature) ──────────────
    // Drives the browser from the harness without a physical tap — T_PLR_13-16
    // need to open big/nested/empty directories and select rows deterministically.
    bool dbgSelect(int16_t idx) {
        if (!_picker.active()) return false;
        _onSelect(idx);
        return true;
    }
    bool dbgCancel() {
        if (!_picker.active()) return false;
        _onCancel();
        return true;
    }
    void dbgReport() const {
        Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"fbState\","
                      "\"active\":%s,\"pending\":%s,\"dir\":\"%s\","
                      "\"dirCount\":%u,\"fileCount\":%u,\"last\":true}\n",
                      active() ? "true" : "false", pending() ? "true" : "false",
                      _dir, (unsigned)_dirCount, (unsigned)_fileCount);
    }
#endif

private:
    enum class State : uint8_t { Idle, Walking, Done };
    struct FBEntry { char name[FB_NAME_LEN]; };

    void _finish() {
        _closeDir();
        _state = State::Done;
        _picker.updateCount((int16_t)(_dirCount + _fileCount));
        LOG_I("filebrowser", "%s: %u dirs, %u files", _dir,
              (unsigned)_dirCount, (unsigned)_fileCount);
    }

    void _closeDir() { if (_dh) _dh.close(); }

    static bool _hasExt(const char* name, const char* ext) {
        const size_t nl = strlen(name), el = strlen(ext);
        return nl >= el && strcasecmp(name + nl - el, ext) == 0;
    }

    // One walk pass, bucketed by type — see header comment for why this is
    // "no sort buffer" and not a contradiction of it.
    void _classify(File& e) {
        const char* nm = e.name();   // basename (FS.h VFSFileImpl::name())
        if (!nm || !nm[0]) return;
        if (nm[0] == '.' && (nm[1] == '\0' || (nm[1] == '.' && nm[2] == '\0'))) return;  // . / ..
        if (e.isDirectory()) {
            if (_dirCount < FB_MAX_DIRS) strlcpy(_dirs[_dirCount++].name, nm, FB_NAME_LEN);
        } else if (_hasExt(nm, ".mp3") || _hasExt(nm, ".m3u")) {
            if (_fileCount < FB_MAX_FILES) strlcpy(_files[_fileCount++].name, nm, FB_NAME_LEN);
        }
        // Anything else — non-audio files — is silently filtered (T_PLR_16).
    }

    void _onSelect(int16_t idx) {
        if (idx < 0) return;
        if (idx < (int16_t)_dirCount) {
            char next[m3u::PL_PATH_MAX];
            snprintf(next, sizeof(next), "%s%s/", _dir, _dirs[idx].name);
            open(next);
            return;
        }
        const int16_t fi = idx - (int16_t)_dirCount;
        if (fi < 0 || fi >= (int16_t)_fileCount) return;
        char path[m3u::PL_PATH_MAX];
        snprintf(path, sizeof(path), "%s%s", _dir, _files[fi].name);
        if (!_delegate) return;
        if (_hasExt(_files[fi].name, ".m3u")) _delegate->fbLoadPlaylist(path);
        else                                  _delegate->fbPlayFile(path);
    }

    // The picker's own back-zone (SPickerList::isBackZone / its "< back"
    // header tap) is the browser's single back/up affordance: ascend one
    // level, or — at root — close (the picker is already hidden by the time
    // this fires; SPickerList::_cancel() hides before invoking onCancel).
    void _onCancel() {
        if (strcmp(_dir, "/") == 0) { _state = State::Done; return; }
        char parent[m3u::PL_PATH_MAX];
        strlcpy(parent, _dir, sizeof(parent));
        size_t n = strlen(parent);
        if (n && parent[n - 1] == '/') parent[--n] = '\0';   // drop trailing slash
        char* slash = strrchr(parent, '/');
        if (slash) *(slash + 1) = '\0'; else strlcpy(parent, "/", sizeof(parent));
        open(parent);
    }

    static void _sRowText(int16_t idx, char* left, size_t leftSize,
                           char* right, size_t rightSize, void* ctx) {
        static_cast<FileBrowser*>(ctx)->_rowText(idx, left, leftSize, right, rightSize);
    }
    static void _sOnSelect(int16_t idx, void* ctx) { static_cast<FileBrowser*>(ctx)->_onSelect(idx); }
    static void _sOnCancel(void* ctx)               { static_cast<FileBrowser*>(ctx)->_onCancel(); }

    void _rowText(int16_t idx, char* left, size_t leftSize, char* right, size_t rightSize) {
        left[0] = '\0'; right[0] = '\0';
        if (idx < 0) return;
        if (idx < (int16_t)_dirCount) {
            strlcpy(left, _dirs[idx].name, leftSize);
            strlcpy(right, ">", rightSize);   // drawChevronRow's idiom — deeper navigation
            return;
        }
        const int16_t fi = idx - (int16_t)_dirCount;
        if (fi < 0 || fi >= (int16_t)_fileCount) return;
        strlcpy(left, _files[fi].name, leftSize);
    }

    Delegate*   _delegate = nullptr;
    SPickerList _picker;
    File        _dh;
    FBEntry*    _dirs  = nullptr;
    FBEntry*    _files = nullptr;
    uint16_t    _dirCount  = 0;
    uint16_t    _fileCount = 0;
    State       _state = State::Idle;
    char        _dir[m3u::PL_PATH_MAX] = {0};
};

}  // namespace player
