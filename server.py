#!/usr/bin/env python3
"""
LoL wiki reference wrapper - local static server.

Serves the static web app for local browsing (GitHub Pages hosts the same
app publicly).

Usage: python server.py [--port 8000] [--host 0.0.0.0]
"""

import argparse
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_FILE = ROOT / "data" / "skins.json"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/data/"):
            self._static(DATA_FILE)
            return
        self._static(WEB_DIR / parsed.path.lstrip("/"))

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        self._static(WEB_DIR / parsed.path.lstrip("/"), head=True)

    # ------------------------------------------------------------------
    def _send_headers(self, code=200, ctype="text/html", length=None, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _static(self, path: Path, head=False):
        path = path.resolve()
        if path != DATA_FILE:
            try:
                path.relative_to(WEB_DIR)
            except ValueError:
                self._send_headers(404, "text/plain")
                if not head:
                    self.wfile.write(b"not found")
                return
        if path.is_dir():
            path = path / "index.html"
        if not path.is_file():
            self._send_headers(404, "text/plain")
            if not head:
                self.wfile.write(b"not found")
            return
        ct = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self._send_headers(200, ct, len(data))
        if not head:
            self.wfile.write(data)

    # ------------------------------------------------------------------
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        out = socket.gethostbyname_ex(socket.gethostname())[2]
        ips.update(out)
    except Exception:  # noqa: BLE001
        pass
    return sorted(ips)


def tailscale_ip():
    try:
        import subprocess

        r = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0:
            return r.stdout.strip().splitlines()[0]
    except Exception:  # noqa: BLE001
        pass
    return None


def main():
    ap = argparse.ArgumentParser(description="LoL wiki reference wrapper")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("LoL reference wrapper running:")
    print(f"  local   : http://localhost:{args.port}")
    for ip in lan_ips():
        if ip != "127.0.0.1":
            print(f"  network : http://{ip}:{args.port}")
    ts = tailscale_ip()
    if ts:
        print(f"  tailscale: http://{ts}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()