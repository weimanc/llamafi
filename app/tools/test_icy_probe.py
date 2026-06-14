#!/usr/bin/env python3
"""ICY metadata probe — WebRadio POC (TASK-200).

Connects to a live MP3 stream with 'Icy-MetaData: 1', reads 64 KB of stream
data, and parses the inline ICY metadata block to extract StreamTitle.

Purpose: confirm ICY metadata format before writing the ESP32-side parser.

Test stations (tried in order, first that responds is used):
  1. BBC Radio 2 (UK public broadcaster — highly reliable, 128 kbps MP3)
  2. NPO Radio 2 (NL public broadcaster — alternative)
  3. FunX (NL, radio-browser.info top-voted NL station)

Protocol:
  1. Raw TCP socket to host:port
  2. HTTP/1.0 GET with 'Icy-MetaData: 1' header
  3. Parse response headers — look for 'icy-metaint'
  4. Read that many bytes (audio), then 1 byte (meta-length × 16 = block size)
  5. Read the block, find 'StreamTitle=' and extract the value

Output: ICY headers, metaint value, raw metadata block, parsed StreamTitle.

Usage:
  python3 tools/test_icy_probe.py
  python3 tools/test_icy_probe.py --url http://stream.example.com:8000/stream

Exit 0 = StreamTitle successfully parsed. Exit 1 = failure.
"""
import argparse
import socket
import sys
import urllib.parse

# Test stations tried in order. BBC Radio 2 is extremely reliable and has ICY
# metadata enabled. The NL stations are from radio-browser.info top-voted NL
# MP3 results (TASK-200 probe output).
TEST_STATIONS = [
    ("BBC Radio 2", "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_two"),
    ("NPO Radio 2", "http://icecast.omroep.nl/radio2-bb-mp3"),
    ("FunX", "http://icecast.omroep.nl/funx-bb-mp3"),
]

READ_BYTES = 64 * 1024   # 64 KB of stream data to read
CONNECT_TIMEOUT = 10     # seconds
READ_TIMEOUT = 15        # seconds


def _info(label, detail=""):
    print(f"  [INFO] {label}" + (f": {detail}" if detail else ""))


def _ok(label, detail=""):
    print(f"  [PASS] {label}" + (f": {detail}" if detail else ""))


def _fail(label, detail=""):
    print(f"  [FAIL] {label}" + (f": {detail}" if detail else ""), file=sys.stderr)


def parse_url(url):
    """Return (host, port, path) from an HTTP URL."""
    p = urllib.parse.urlparse(url)
    host = p.hostname
    port = p.port or 80
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return host, port, path


def probe_icy(url, station_name=""):
    """Connect to url with ICY-MetaData: 1, parse StreamTitle.

    Returns True on success, False on failure.
    """
    print(f"\n  Station : {station_name or url}")
    print(f"  URL     : {url}")

    try:
        host, port, path = parse_url(url)
    except Exception as e:
        _fail("URL parse", str(e))
        return False

    # Build the raw HTTP/1.0 request with ICY headers.
    request = (
        f"GET {path} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Icy-MetaData: 1\r\n"
        f"User-Agent: Mozilla/5.0 (X11; Linux x86_64) esp_spotify/probe\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode()

    try:
        sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
    except OSError as e:
        _fail("connect", f"{host}:{port} — {e}")
        return False

    sock.settimeout(READ_TIMEOUT)

    try:
        sock.sendall(request)

        # Read the HTTP response headers (terminated by \r\n\r\n).
        header_buf = b""
        while b"\r\n\r\n" not in header_buf:
            chunk = sock.recv(4096)
            if not chunk:
                _fail("headers", "connection closed before header terminator")
                return False
            header_buf += chunk
            if len(header_buf) > 65536:
                _fail("headers", "header buffer overflow (>64 KB)")
                return False

        # Split headers from any body bytes that arrived with the header block.
        header_end = header_buf.index(b"\r\n\r\n")
        raw_headers = header_buf[:header_end].decode(errors="replace")
        body_start = header_buf[header_end + 4:]

        # Parse response line and headers.
        lines = raw_headers.split("\r\n")
        status_line = lines[0]
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()

        print(f"  Status  : {status_line}")

        # Print all ICY headers.
        icy_headers = {k: v for k, v in headers.items() if k.startswith("icy-")}
        if icy_headers:
            print("  ICY headers:")
            for k, v in icy_headers.items():
                print(f"    {k}: {v}")
        else:
            _info("no icy-* headers found — server may not support ICY metadata")

        # Find metaint.
        metaint_str = headers.get("icy-metaint", "")
        if not metaint_str:
            _fail("icy-metaint", "header not present — server does not send inline metadata")
            return False

        try:
            metaint = int(metaint_str)
        except ValueError:
            _fail("icy-metaint", f"non-integer value: {metaint_str!r}")
            return False

        _ok("icy-metaint", str(metaint))

        # We need to read <metaint> bytes of audio before the first meta block.
        # body_start may already contain some bytes.
        audio_buf = body_start
        while len(audio_buf) < metaint:
            remaining = metaint - len(audio_buf)
            chunk = sock.recv(min(remaining, 4096))
            if not chunk:
                _fail("audio read", f"connection closed after {len(audio_buf)} bytes (need {metaint})")
                return False
            audio_buf += chunk

        _info("audio bytes read", f"{metaint} bytes (one metaint block)")

        # The byte immediately after the audio block is the meta-length byte.
        # meta-length * 16 = byte count of metadata block (zero-padded).
        # audio_buf may have overrun into meta territory if body_start was large.
        meta_len_byte = audio_buf[metaint:metaint + 1]
        extra_after = audio_buf[metaint + 1:]

        if not meta_len_byte:
            # Need to read the length byte.
            meta_len_byte = sock.recv(1)

        if not meta_len_byte:
            _fail("meta-length byte", "connection closed")
            return False

        meta_length = meta_len_byte[0] * 16
        _info("meta-length byte", f"{meta_len_byte[0]} → {meta_length} bytes to read")

        if meta_length == 0:
            _info("metadata block", "empty (length=0) — no StreamTitle in this block")
            _info("hint", "station may update metadata only on track change; try again later")
            return False

        # Read the full metadata block.
        meta_buf = extra_after[:meta_length]
        while len(meta_buf) < meta_length:
            remaining = meta_length - len(meta_buf)
            chunk = sock.recv(min(remaining, 4096))
            if not chunk:
                _fail("metadata read", f"connection closed after {len(meta_buf)}/{meta_length} bytes")
                return False
            meta_buf += chunk

        meta_block = meta_buf[:meta_length]
        meta_text = meta_block.rstrip(b"\x00").decode(errors="replace")
        print(f"  Raw meta: {meta_text!r}")

        # Parse StreamTitle='...' (and optionally StreamUrl='...').
        # Format: StreamTitle='value';StreamUrl='value';
        stream_title = None
        stream_url = None

        import re
        m = re.search(r"StreamTitle='([^']*)'", meta_text)
        if m:
            stream_title = m.group(1)
        m2 = re.search(r"StreamUrl='([^']*)'", meta_text)
        if m2:
            stream_url = m2.group(1)

        if stream_title is not None:
            _ok("StreamTitle", repr(stream_title))
            if stream_url:
                _info("StreamUrl", repr(stream_url))
            return True
        else:
            _fail("StreamTitle", f"not found in metadata block: {meta_text!r}")
            return False

    except socket.timeout:
        _fail("read timeout", f"{READ_TIMEOUT}s")
        return False
    except OSError as e:
        _fail("socket error", str(e))
        return False
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        help="Override test station URL (default: try BBC Radio 2, NPO Radio 2, FunX in order)",
    )
    args = parser.parse_args()

    print("ICY metadata probe — WebRadio POC (TASK-200)")

    if args.url:
        stations = [("custom", args.url)]
    else:
        stations = TEST_STATIONS

    for name, url in stations:
        print(f"\n{'─' * 60}")
        ok = probe_icy(url, station_name=name)
        if ok:
            print()
            print("PASS — ICY StreamTitle successfully parsed")
            sys.exit(0)
        else:
            print(f"  Trying next station...")

    print()
    print("FAIL — no station returned a parseable StreamTitle")
    sys.exit(1)


if __name__ == "__main__":
    main()
