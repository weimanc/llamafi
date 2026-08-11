#pragma once
// asciiFold.h — UTF-8 → renderable-ASCII transliteration (TASK-415, ADR-059
// design OQ1).
//
// Everything that reaches a PLEDIT row is UTF-8: M3U `#EXTINF` text and ID3
// tags off the SD card, Spotify's API JSON, radio-browser station names. The
// row renderer draws TFT_eSPI Font 1 (GLCD), whose glyphs above 0x7F are box-
// drawing/symbol characters, not Latin letters — so a raw UTF-8 byte pair for
// "é" renders as two unrelated symbols, and a 3-byte sequence as three. The
// Spotify path has had this latent bug since it shipped; M3U makes it acute,
// because a local library is full of accented artist names.
//
// Policy (one pass, no allocation):
//   - ASCII 0x20..0x7E passes through untouched.
//   - Latin-1 Supplement and Latin Extended-A fold to their unaccented base
//     letter(s): "é"→"e", "Æ"→"AE", "ß"→"ss", "ł"→"l".
//   - Typographic punctuation substitutes to its ASCII equivalent: curly
//     quotes→' and ", en/em dash→-, ellipsis→"...", NBSP→space.
//   - Anything else (CJK, emoji, symbols, malformed/truncated UTF-8) becomes
//     '?' — one '?' per codepoint, and one per stray byte, so a mangled string
//     still shows the right shape rather than collapsing to nothing.
//   - Control characters (incl. embedded CR/LF/TAB) become spaces, so a row
//     can never smuggle a line break into the renderer.
//
// Truncation is length-safe in codepoints, not bytes: the output is never cut
// mid-substitution, so "…" either lands whole or not at all.

#include <stddef.h>
#include <stdint.h>

namespace textfold {

// Latin-1 Supplement, U+00C0..U+00FF (index = cp - 0xC0).
static const char kLatin1[64][3] = {
    "A", "A", "A", "A", "A", "A", "AE", "C",   // C0-C7
    "E", "E", "E", "E", "I", "I", "I",  "I",   // C8-CF
    "D", "N", "O", "O", "O", "O", "O",  "x",   // D0-D7 (D7 = multiplication sign)
    "O", "U", "U", "U", "U", "Y", "TH", "ss",  // D8-DF
    "a", "a", "a", "a", "a", "a", "ae", "c",   // E0-E7
    "e", "e", "e", "e", "i", "i", "i",  "i",   // E8-EF
    "d", "n", "o", "o", "o", "o", "o",  "/",   // F0-F7 (F7 = division sign)
    "o", "u", "u", "u", "u", "y", "th", "y",   // F8-FF
};

// Latin Extended-A, U+0100..U+017F (index = cp - 0x100).
static const char kLatinA[128][3] = {
    "A", "a", "A", "a", "A", "a", "C", "c", "C", "c", "C", "c", "C", "c", "D", "d",   // 100-10F
    "D", "d", "E", "e", "E", "e", "E", "e", "E", "e", "E", "e", "G", "g", "G", "g",   // 110-11F
    "G", "g", "G", "g", "H", "h", "H", "h", "I", "i", "I", "i", "I", "i", "I", "i",   // 120-12F
    "I", "i", "IJ", "ij", "J", "j", "K", "k", "k", "L", "l", "L", "l", "L", "l", "L", // 130-13F
    "l", "L", "l", "N", "n", "N", "n", "N", "n", "n", "N", "n", "O", "o", "O", "o",   // 140-14F
    "O", "o", "OE", "oe", "R", "r", "R", "r", "R", "r", "S", "s", "S", "s", "S", "s", // 150-15F
    "S", "s", "T", "t", "T", "t", "T", "t", "U", "u", "U", "u", "U", "u", "U", "u",   // 160-16F
    "U", "u", "U", "u", "W", "w", "Y", "y", "Y", "Z", "z", "Z", "z", "Z", "z", "s",   // 170-17F
};

// Substitution for a single decoded NON-ASCII codepoint. Returns a
// NUL-terminated string of 1..3 ASCII characters — never "", so column counts
// stay predictable. ASCII is handled by the caller without a table lookup.
static inline const char* foldCodepoint(uint32_t cp) {
    if (cp < 0x20 || cp == 0x7F) return " ";          // controls → space
    if (cp >= 0xC0 && cp <= 0xFF) return kLatin1[cp - 0xC0];
    if (cp >= 0x100 && cp <= 0x17F) return kLatinA[cp - 0x100];
    switch (cp) {
        case 0x00A0: return " ";      // NBSP
        case 0x00AB: return "\"";     // «
        case 0x00BB: return "\"";     // »
        case 0x2010: case 0x2011:
        case 0x2012: case 0x2013:
        case 0x2014: case 0x2015: return "-";
        case 0x2018: case 0x2019:
        case 0x201A: case 0x201B: return "'";
        case 0x201C: case 0x201D:
        case 0x201E: case 0x201F: return "\"";
        case 0x2022: return "*";      // bullet
        case 0x2026: return "...";
        case 0x2032: return "'";
        case 0x2033: return "\"";
        case 0x20AC: return "EUR";
        case 0x2122: return "TM";
        default: return "?";
    }
}

// Transliterate `in` into `out` (always NUL-terminated when outSize > 0).
// Returns the number of characters written, excluding the terminator.
// `in` may be NULL. Never writes a partial substitution: if the replacement
// for a codepoint does not fit, the copy stops before it.
static inline size_t foldUtf8(const char* in, char* out, size_t outSize) {
    if (!out || outSize == 0) return 0;
    size_t w = 0;
    out[0] = '\0';
    if (!in) return 0;

    const uint8_t* p = (const uint8_t*)in;
    while (*p) {
        // Plain ASCII: the overwhelmingly common case, no table lookup.
        if (*p >= 0x20 && *p < 0x7F) {
            if (w + 2 > outSize) break;
            out[w++] = (char)*p++;
            out[w] = '\0';
            continue;
        }

        uint32_t cp = 0xFFFD;           // U+FFFD → '?' via foldCodepoint()
        const uint8_t b0 = *p;
        int need = -1;                  // continuation bytes expected
        if (b0 < 0x80)                { cp = b0;         need = 0; }
        else if ((b0 & 0xE0) == 0xC0) { cp = b0 & 0x1F;  need = 1; }
        else if ((b0 & 0xF0) == 0xE0) { cp = b0 & 0x0F;  need = 2; }
        else if ((b0 & 0xF8) == 0xF0) { cp = b0 & 0x07;  need = 3; }
        p++;                            // the lead byte is always consumed
        for (int i = 0; i < need; i++) {
            if ((*p & 0xC0) != 0x80) {  // truncated / malformed sequence:
                cp = 0xFFFD;            // do NOT consume the offending byte —
                break;                  // it may itself start a valid one
            }
            cp = (cp << 6) | (uint32_t)(*p & 0x3F);
            p++;
        }

        const char* sub = foldCodepoint(cp);
        size_t n = 0;
        while (sub[n]) n++;
        if (w + n + 1 > outSize) break;   // would not fit whole — stop here
        for (size_t i = 0; i < n; i++) out[w++] = sub[i];
        out[w] = '\0';
    }
    return w;
}

}  // namespace textfold
