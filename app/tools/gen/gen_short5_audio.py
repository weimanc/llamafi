#!/usr/bin/env python3
"""gen_short5_audio.py — build the T_PLR_25/T_PMT_04 real-audio fixture (TASK-418).

T_PLR_25 is the ONE test in the play-order suite that drives real playback
(audio_eof_mp3() -> _stepOrder() -> _startPlayback()), so unlike every other
fixture in this directory it can't be satisfied with dummy bytes — the ESP32's
MP3 decoder has to actually decode these. Needs `ffmpeg` (sine-wave test-tone
synthesis + MP3 encode) on the host; not part of gen_playlist_fixtures.py
because that file's shape is pure-Python bytes-in, and this one shells out.

    python3 app/tools/gen/gen_short5_audio.py
    python3 app/tools/sd_put.py --tree app/tools/fixtures/sd   # needs debug firmware + monitor down

KNOWN BLOCKER (TASK-424, SD write path panics/silently corrupts in FatFs):
pushing these 5 files (~245 KB total) over `sd_put.py`'s short-burst path has
twice (2026-08-27) triggered TASK-424's corrupted-FIL signature on every
`sdput` call made immediately afterward in the same debug session — see that
task's record in tasks-winamp-player.md for the reproduction detail. Until
TASK-424 lands, expect this fixture to need re-pushing (and T_PLR_25 to stay
failing/blocked) even though the files generated here are fine on the host.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "app" / "tools" / "fixtures" / "sd"

# (filename, frequency Hz) — distinct tones, ~3s each, so a human spot-check
# (or a future assertion on audio content) can tell them apart.
TONES = [
    ("tone1.mp3", 440),
    ("tone2.mp3", 494),
    ("tone3.mp3", 523),
    ("tone4.mp3", 587),
    ("tone5.mp3", 659),
]


def make_tone(dest: Path, freq: int, duration: float = 3.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={duration}",
         "-ar", "44100", "-ac", "2", "-b:a", "128k", str(dest)],
        check=True,
    )


def short5_m3u() -> bytes:
    out = ["#EXTM3U"]
    for name, freq in TONES:
        out.append(f"#EXTINF:3,Test Tone ({freq}Hz)")
        out.append(f"../mp3/short5/{name}")
    return ("\n".join(out) + "\n").encode("utf-8")


def main() -> int:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("ERROR: ffmpeg not found on PATH — required to synthesize the tones", file=sys.stderr)
        return 1

    print("writing short5 audio fixture:")
    for name, freq in TONES:
        dest = OUT / "mp3" / "short5" / name
        make_tone(dest, freq)
        print(f"  {dest}  ({dest.stat().st_size} B, {freq} Hz)")
    m3u_path = OUT / "playlists" / "short5.m3u"
    m3u_path.parent.mkdir(parents=True, exist_ok=True)
    m3u_path.write_bytes(short5_m3u())
    print(f"  {m3u_path}  ({m3u_path.stat().st_size} B)")
    print("\npush over serial (TASK-415/424 short-burst path; needs debug firmware, monitor down):")
    print("  python3 app/tools/sd_put.py --tree app/tools/fixtures/sd")
    print("\nSee this file's docstring for TASK-424's known interaction with this push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
