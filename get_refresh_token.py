#!/usr/bin/env python3
"""
Fetch a Spotify refresh token and write app/data/spotify_diy_config.json.

Prereqs in the Spotify Developer Dashboard for your app:
  Redirect URIs -> add exactly:  http://127.0.0.1:8888/callback/
  Save.

Usage:
  ./get_refresh_token.py <CLIENT_ID> <CLIENT_SECRET>
  # or
  SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... ./get_refresh_token.py
"""
import base64
import http.server
import json
import os
import pathlib
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_URI = "http://127.0.0.1:8888/callback/"
SCOPE = "user-read-playback-state user-modify-playback-state"
PORT = 8888

# Config file lives at app/data/ relative to this script's directory.
REPO_ROOT = pathlib.Path(__file__).parent.resolve()
DATA_DIR = REPO_ROOT / "app" / "data"
CONFIG_FILE = DATA_DIR / "spotify_diy_config.json"

received = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback/":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        received.update({k: v[0] for k, v in qs.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        if "code" in received:
            self.wfile.write(b"Got the code. You can close this tab.")
        else:
            self.wfile.write(f"Error: {received}".encode())


def ensure_data_dir():
    """Create app/data/ as a real directory, replacing a broken symlink if present."""
    if DATA_DIR.is_symlink() and not DATA_DIR.exists():
        DATA_DIR.unlink()
        DATA_DIR.mkdir(parents=True)
    elif not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)


def write_config(client_id, client_secret, refresh_token):
    ensure_data_dir()
    config = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "refreshToken": refresh_token,
    }
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")
    print(f"\nConfig written to {CONFIG_FILE.relative_to(REPO_ROOT)}")
    print("Next step:  ./run/spiffs push spotify_diy_config.json")


def main():
    if len(sys.argv) >= 3:
        client_id, client_secret = sys.argv[1], sys.argv[2]
    else:
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        sys.exit("usage: ./get_refresh_token.py <CLIENT_ID> <CLIENT_SECRET>")

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    })

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("Opening browser for Spotify auth...")
    print("If it doesn't open, visit:\n ", auth_url, "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    while "code" not in received and "error" not in received:
        pass
    server.shutdown()

    if "error" in received:
        sys.exit(f"auth failed: {received['error']}")

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": received["code"],
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as r:
        tok = json.loads(r.read())

    write_config(client_id, client_secret, tok["refresh_token"])


if __name__ == "__main__":
    main()
