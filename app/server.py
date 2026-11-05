"""Tiny dependency-free web server: static UI, JSON API and a server-sent-events stream of run steps.
Run:  python -m app.server   then open http://localhost:8000"""
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import export
from .compare import compare
from .config import ROOT, settings
from .pipeline import execute, new_run
from .store import Store

STORE = None
ACTIVE = set()
ACTIVE_LOCK = threading.Lock()
WEB = ROOT / "web"


def start_run_thread(run_id):
    with ACTIVE_LOCK:
        if run_id in ACTIVE:
            return False
        ACTIVE.add(run_id)

    def work():
        try:
            execute(STORE, run_id)
        finally:
            with ACTIVE_LOCK:
                ACTIVE.discard(run_id)
    threading.Thread(target=work, daemon=True).start()
    return True


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _text(self, text, ctype, filename=None):
        b = text.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", ctype + "; charset=utf-8")
        if filename:
            self.send_header("content-disposition", 'attachment; filename="%s"' % filename)
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        if path == "/api/companies":  # latest finished run per company
            seen = {}
            for r in STORE.list_runs(200):
                if r["status"] != "done":
                    continue
                run = STORE.get_run(r["id"])
                res = run["result"]
                cid = res["company"]["id"]
                if cid not in seen:
                    seen[cid] = {"run_id": r["id"], "company_id": cid, "name": res["company"]["name"],
                                 "external": res["analysis"]["counts"]["external"], "window": res["window"]["start"],
                                 "has_exits": bool(res["analysis"].get("exits")), "created": r["created"]}
            return self._json(list(seen.values()))
        if path == "/api/compare":
            ids = [i for i in (q.get("ids") or [""])[0].split(",") if i]
            runs = [STORE.get_run(i) for i in ids]
            if len(runs) < 2 or any(not r or not r["result"] for r in runs):
                return self._json({"error": "give at least two finished run ids"}, 400)
            return self._json(compare([r["result"] for r in runs]))
        if path.startswith("/api/export/"):
            run = STORE.get_run(path.rsplit("/", 1)[1])
            if not run or not run["result"]:
                return self._json({"error": "no finished result for that run"}, 404)
            fmt = (q.get("format") or ["md"])[0]
            res = run["result"]
            name = res["company"]["name"].lower().replace(" ", "-")
            if fmt == "html":
                return self._text(export.render_html(res), "text/html")
            if fmt == "email":
                return self._text(export.email_draft(res), "text/plain")
            return self._text(export.render_markdown(res), "text/markdown", "%s-competitor-read.md" % name)
        if path == "/api/config":
            s = settings()
            return self._json({"offline": s["offline"], "has_crustdata_key": bool(s["crustdata_key"]),
                               "has_model_key": bool(s["anthropic_key"]), "budget": s["budget"]})
        if path == "/api/runs":
            return self._json(STORE.list_runs())
        if path == "/api/last":
            for r in STORE.list_runs(50):
                if r["status"] == "done":
                    return self._json({"id": r["id"], **STORE.get_run(r["id"])})
            return self._json({"error": "no finished runs yet"}, 404)
        if path.startswith("/api/run/"):
            run = STORE.get_run(path.rsplit("/", 1)[1])
            if not run:
                return self._json({"error": "unknown run"}, 404)
            run["steps"] = STORE.steps(run["id"])
            return self._json(run)
        if path.startswith("/api/stream/"):
            return self._stream(path.rsplit("/", 1)[1])
        f = WEB / ("index.html" if path in ("/", "") else path.lstrip("/"))
        if f.is_file() and WEB in f.resolve().parents:
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("content-type", mimetypes.guess_type(str(f))[0] or "application/octet-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/run":
            b = self._body()
            req = (b.get("request") or "").strip()
            if not req:
                return self._json({"error": "request is empty"}, 400)
            run_id = new_run(STORE, req, company=(b.get("company") or "").strip() or None,
                             offline=True if b.get("offline") else None)
            start_run_thread(run_id)
            return self._json({"run_id": run_id})
        if path.startswith("/api/resume/"):
            run_id = path.rsplit("/", 1)[1]
            if not STORE.get_run(run_id):
                return self._json({"error": "unknown run"}, 404)
            return self._json({"run_id": run_id, "started": start_run_thread(run_id)})
        self._json({"error": "not found"}, 404)

    def _stream(self, run_id):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "close")
        self.end_headers()
        last, idle = 0, 0
        try:
            while True:
                evs = STORE.events_after(run_id, last)
                for ev in evs:
                    self.wfile.write(("data: %s\n\n" % json.dumps(ev)).encode())
                    last = ev["id"]
                self.wfile.flush()
                run = STORE.get_run(run_id)
                with ACTIVE_LOCK:
                    active = run_id in ACTIVE
                if not evs and run and run["status"] in ("done", "failed", "needs_input") and not active:
                    idle += 1
                    if idle > 2:
                        self.wfile.write(b"event: end\ndata: {}\n\n")
                        self.wfile.flush()
                        return
                else:
                    idle = 0
                time.sleep(0.3)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def main():
    global STORE
    s = settings()
    STORE = Store(s["db"])
    srv = ThreadingHTTPServer(("0.0.0.0", s["port"]), H)
    print("X-Ray running at http://localhost:%d  (offline=%s)" % (s["port"], s["offline"]))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
