"""Serve the review site and run the three arms live on Fireworks.

    python3 web/server.py [--port 8765]

Binds to localhost and serves only web/ and data/images/, so .env and the answer key stay private. The Fireworks key
stays on this server: the browser never sees it. Responses are cached on disk by harness/client.py, so repeating a case is free.
"""
import argparse, json, mimetypes, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
# The saved GLM arm (runs/glm_harness_wiki_low) ran with low reasoning, so live calls do too.
os.environ.setdefault("GLM_REASONING", "low")
from harness import config
from harness.api import analyze

PUBLIC = {"/web/": os.path.join(REPO, "web"), "/data/images/": os.path.join(REPO, "data", "images")}
# web/ also holds these, which only make sense on disk.
HIDDEN = {"server.py", "build_data.py", "build_compare.py", "README.md"}
ARMS = ("kimi_alone", "kimi_harness_wiki", "glm_harness_wiki")
SPLITS = ("test_context", "test")
MAX_BODY = 4096

_cases = {}
_lock = threading.Lock()

def load_case(split, case_id):
    with _lock:
        if split not in _cases:
            _cases[split] = {c["case_id"]: c for c in (json.loads(l) for l in open(os.path.join(REPO, "data", split + ".jsonl")) if l.strip())}
    return _cases[split].get(case_id)

def has_key():
    if os.environ.get("FIREWORKS_API_KEY"):
        return True
    path = os.path.join(REPO, ".env")
    return os.path.exists(path) and any(l.startswith("FIREWORKS_API_KEY=") and l.split("=", 1)[1].strip() for l in open(path))

def static_path(url_path):
    """The file for a public URL, or None. Refuses anything that resolves outside the public folders."""
    for prefix, folder in PUBLIC.items():
        if url_path.startswith(prefix):
            rel = url_path[len(prefix):] or "index.html"
            full = os.path.realpath(os.path.join(folder, rel))
            inside = full.startswith(os.path.realpath(folder) + os.sep)
            if inside and os.path.isfile(full) and os.path.basename(full) not in HIDDEN and not os.path.basename(full).startswith("."):
                return full
    return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/web"):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        if path == "/api/status":
            self.send_json(200, {"live": has_key(), "arms": {a: config.ROWS[a]["model"] for a in ARMS}})
            return
        full = static_path(path)
        if not full:
            self.send_error(404)
            return
        body = open(full, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path != "/api/analyze":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            self.send_json(400, {"error": "bad request"})
            return
        try:
            req = json.loads(self.rfile.read(length))
        except ValueError:
            self.send_json(400, {"error": "bad request"})
            return
        split, case_id, arm = req.get("split"), req.get("case_id"), req.get("arm")
        if split not in SPLITS or arm not in ARMS:
            self.send_json(400, {"error": "unknown split or arm"})
            return
        case = load_case(split, case_id)
        if not case:
            self.send_json(404, {"error": "unknown case"})
            return
        if not has_key():
            self.send_json(503, {"error": "No Fireworks key on the server. Add FIREWORKS_API_KEY to .env and try again."})
            return
        t0 = time.time()
        result = analyze(case, row=arm)
        result["wall_ms"] = int((time.time() - t0) * 1000)
        self.send_json(200, result)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Review site: http://127.0.0.1:{a.port}/web/  live Fireworks calls: {'on' if has_key() else 'off, no key'}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
