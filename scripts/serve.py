"""Serve the quiz app with caching disabled, so a rebuilt bank or app is always picked up.

Usage: python3 scripts/serve.py [port]   (default 8765), then open http://localhost:8765
"""
import functools
import http.server
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    handler = functools.partial(NoCacheHandler, directory=str(APP))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Quiz app at http://localhost:{port}  (Ctrl+C to stop)")
        server.serve_forever()


if __name__ == "__main__":
    main()
