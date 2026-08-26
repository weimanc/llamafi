#!/usr/bin/env python3
"""gen_playlist_fixtures.py — build the T_PLR_08..12 M3U fixtures (TASK-415).

The SD write path is a known open defect (TASK-424), so these cannot be written
from the device: generate them here, then copy the tree onto the card from a
host card reader.

    python3 app/tools/gen_playlist_fixtures.py
    # then, with the card mounted on the host:
    cp -r app/tools/fixtures/sd/playlists /run/media/<you>/<card>/
    cp app/tools/fixtures/sd/mp3/rel.m3u  /run/media/<you>/<card>/mp3/

Track names are the ones already on this card's /mp3 (TASK-410's fixtures).
Nothing here writes to the card itself.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "app" / "tools" / "fixtures" / "sd"

# A slice of what /mp3 actually holds — `sdls /mp3`, 2026-08-11.
TRACKS = [
    ("01 - Tomorrow Comes Today.mp3", "Gorillaz", "Tomorrow Comes Today", 192),
    ("02 - Clint Eastwood.mp3",       "Gorillaz", "Clint Eastwood",       341),
    ("03 - 19-2000.mp3",              "Gorillaz", "19-2000",              208),
    ("04 - Rock The House.mp3",       "Gorillaz", "Rock The House",       249),
    ("05 - Feel Good Inc.mp3",        "Gorillaz", "Feel Good Inc",        222),
    ("06 - DARE.mp3",                 "Gorillaz", "DARE",                 246),
    ("07 - Dirty Harry.mp3",          "Gorillaz", "Dirty Harry",          231),
    ("08 - Kids With Guns.mp3",       "Gorillaz", "Kids With Guns",       225),
    ("09 - El Manana.mp3",            "Gorillaz", "El Manana",            232),
    ("10 - Stylo.mp3",                "Gorillaz", "Stylo",                270),
    ("5 - Clocks - Coldplay.mp3",     "Coldplay", "Clocks",               307),
    ("8 - Yellow - Coldplay.mp3",     "Coldplay", "Yellow",               266),
]


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  {path.relative_to(REPO)}  ({len(data)} B)")


def gate100() -> bytes:
    """T_PLR_08/09/12 — 120 entries, absolute paths, every one real.

    Longer than the 12 distinct files on the card, so it cycles: the gate is
    "does a >=100-entry index load and scroll", not "are they distinct".
    """
    out = ["#EXTM3U"]
    for i in range(120):
        name, artist, title, dur = TRACKS[i % len(TRACKS)]
        out.append(f"#EXTINF:{dur},{artist} - {title} ({i + 1:03d})")
        out.append(f"/mp3/{name}")
    return ("\n".join(out) + "\n").encode("utf-8")


def rel_same_dir() -> bytes:
    """T_PLR_10 — lives in /mp3, refers to its own directory with no leading path."""
    out = ["#EXTM3U"]
    for name, artist, title, dur in TRACKS[:4]:
        out.append(f"#EXTINF:{dur},{artist} - {title}")
        out.append(name)          # bare relative
    for name, artist, title, dur in TRACKS[4:6]:
        out.append(f"#EXTINF:{dur},{artist} - {title}")
        out.append(f"./{name}")   # explicit ./
    return ("\n".join(out) + "\n").encode("utf-8")


def rel_parent() -> bytes:
    """T_PLR_10 — lives in /playlists, climbs out with ../mp3/."""
    out = ["#EXTM3U"]
    for name, artist, title, dur in TRACKS[:3]:
        out.append(f"#EXTINF:{dur},{artist} - {title}")
        out.append(f"../mp3/{name}")
    return ("\n".join(out) + "\n").encode("utf-8")


def utf8() -> bytes:
    """OQ1 — accented / typographic / CJK text through the ASCII fold.

    Every path is real, so a row that renders wrong is a fold bug and not a
    missing file.
    """
    rows = [
        ("Björk", "Jóga"),
        ("Sigur Rós", "Sæglópur"),
        ("Antonín Dvořák", "Symphony No. 9"),
        ("Motörhead", "Ace of Spades"),
        ("Mötley Crüe", "Dr. Feelgood"),
        ("Beyoncé", "Don’t Hurt Yourself"),          # U+2019
        ("Anonymous", "“Quoted” — dashed…"),          # U+201C/201D, U+2014, U+2026
        ("坂本龍一", "Merry Christmas Mr. Lawrence"),  # CJK -> ????
        ("Café Tacvba", "Déjà Vu ½ × ¾"),
    ]
    out = ["#EXTM3U"]
    for i, (artist, title) in enumerate(rows):
        name = TRACKS[i % len(TRACKS)][0]
        out.append(f"#EXTINF:{180 + i},{artist} - {title}")
        out.append(f"/mp3/{name}")
    return ("\n".join(out) + "\n").encode("utf-8")


def malformed() -> bytes:
    """T_PLR_11 — every degradation mode in one file, in a known order.

    Expected: 8 entries load (rows 0..7 below), the file never crashes the
    parser, and row 6 renders the "(unreadable)" placeholder only if its record
    has no path line — it has one, so it renders the basename instead. The
    trailing #EXTINF with no path contributes NO entry, which is the real
    truncation case.
    """
    crlf = "\r\n"
    parts = []
    parts.append("﻿#EXTM3U")                       # 0: UTF-8 BOM on line 1
    parts.append("# a plain comment, not a directive")
    parts.append("")                                     # blank line
    parts.append(f"#EXTINF:192,Gorillaz - Tomorrow Comes Today")
    parts.append("/mp3/01 - Tomorrow Comes Today.mp3")   # entry 0: normal
    parts.append("/mp3/02 - Clint Eastwood.mp3")         # entry 1: no #EXTINF at all
    parts.append("#EXTINF:-1,Unknown duration")
    parts.append("/mp3/03 - 19-2000.mp3")                # entry 2: duration -1 -> 0
    parts.append("#EXTINF:not-a-number,Junk duration")
    parts.append("/mp3/04 - Rock The House.mp3")         # entry 3: unparsable duration -> 0
    parts.append("#EXTINF:222")                          # no comma, so no title
    parts.append("/mp3/05 - Feel Good Inc.mp3")          # entry 4: falls back to basename
    parts.append("#EXTGRP:something we ignore")
    parts.append("#EXTINF:246,Gorillaz - DARE")
    parts.append("#EXTVLCOPT:no-video")                  # directive BETWEEN extinf and path
    parts.append("/mp3/06 - DARE.mp3")                   # entry 5
    parts.append("#EXTINF:231,Missing File")
    parts.append("/mp3/this-file-does-not-exist.mp3")    # entry 6: indexes fine, play fails
    parts.append("   /mp3/07 - Dirty Harry.mp3   ")      # entry 7: leading/trailing spaces
    body = crlf.join(parts) + crlf                       # CRLF line endings throughout
    body += "#EXTINF:999,Truncated - no path line follows"   # no trailing newline
    return body.encode("utf-8")


def empty() -> bytes:
    """T_PLR_11 — a header and nothing else. Loads, count 0, no crash."""
    return b"#EXTM3U\n"


def gate20() -> bytes:
    """T_PLR_20-24 (TASK-418) — 20 entries, absolute paths. The play-order
    engine tests (shuffle bag / end-of-list cells / prev-history / tap-to-play
    cursor) all run through the debug surface (`advance`/`set plCursor`),
    never decoding audio, so the 20 entries do not need 20 distinct files —
    entry ids are per-RECORD (position in the M3U), not per-file, so cycling
    through the same 12 real tracks still yields 20 distinct ids. Only
    T_PLR_25 (the one real-playback case) needs actual short audio, and it
    reuses gate100/real files rather than this fixture.
    """
    out = ["#EXTM3U"]
    for i in range(20):
        name, artist, title, dur = TRACKS[i % len(TRACKS)]
        out.append(f"#EXTINF:{dur},{artist} - {title} ({i + 1:02d})")
        out.append(f"/mp3/{name}")
    return ("\n".join(out) + "\n").encode("utf-8")


def main() -> None:
    print("writing playlist fixtures:")
    write(OUT / "playlists" / "gate100.m3u", gate100())
    write(OUT / "playlists" / "gate20.m3u", gate20())
    write(OUT / "playlists" / "relpar.m3u", rel_parent())
    write(OUT / "playlists" / "utf8.m3u", utf8())
    write(OUT / "playlists" / "bad.m3u", malformed())
    write(OUT / "playlists" / "empty.m3u", empty())
    write(OUT / "mp3" / "rel.m3u", rel_same_dir())
    print("\ncopy onto the card (host card reader — the device write path is TASK-424):")
    print("  cp -r app/tools/fixtures/sd/playlists <CARD>/")
    print("  cp    app/tools/fixtures/sd/mp3/rel.m3u <CARD>/mp3/")
    print("\nor push a single fixture over serial (TASK-415/424 short-burst path):")
    print("  python3 app/tools/sd_put.py app/tools/fixtures/sd/playlists/gate20.m3u /playlists/gate20.m3u")


if __name__ == "__main__":
    main()
