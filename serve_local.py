"""Serve the paper book locally with editing enabled (no GitHub, no PIN).

    python serve_local.py            -> http://127.0.0.1:8765

The page detects localhost and saves edits through POST /api/save, which writes
data/portfolio.json in place. Commit and push whenever you are happy with it.
"""
import json, os, sys, webbrowser, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "data", "portfolio.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/book"):
            body = open(BOOK, "rb").read() if os.path.exists(BOOK) else b'{"version":1,"trades":[],"watchlist":[],"theses":{},"valuations":{}}'
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body); return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/save":
            self.send_response(404); self.end_headers(); return
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            assert isinstance(data, dict) and "trades" in data
        except Exception as exc:
            self.send_response(400); self.end_headers(); self.wfile.write(str(exc).encode()); return
        tmp = BOOK + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2); f.write("\n")
        os.replace(tmp, BOOK)
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"ok":true}')

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = "http://127.0.0.1:%d/" % PORT
    print("Serene Paper Book (local, editing on):", url)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
