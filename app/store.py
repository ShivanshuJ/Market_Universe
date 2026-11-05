"""SQLite storage: API response cache (so a retry never re-spends credits), runs, steps and events."""
import json
import pathlib
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache(
  key TEXT PRIMARY KEY, path TEXT, response TEXT, credits REAL, created REAL);
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, request TEXT, params TEXT, status TEXT,
  created REAL, updated REAL, result TEXT, credits REAL DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS steps(
  run_id TEXT, name TEXT, status TEXT, output TEXT, error TEXT, started REAL, finished REAL,
  PRIMARY KEY(run_id, name));
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts REAL, kind TEXT, data TEXT);
"""


class Store:
    def __init__(self, path):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def _x(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def _all(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    # ---- cache
    def cache_get(self, key):
        rows = self._all("SELECT response FROM cache WHERE key=?", (key,))
        return json.loads(rows[0]["response"]) if rows else None

    def cache_put(self, key, path, response, credits):
        self._x("INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?)",
                (key, path, json.dumps(response), credits, time.time()))

    # ---- runs
    def create_run(self, run_id, request, params):
        now = time.time()
        self._x("INSERT INTO runs(id,request,params,status,created,updated) VALUES(?,?,?,?,?,?)",
                (run_id, request, json.dumps(params), "queued", now, now))

    def get_run(self, run_id):
        rows = self._all("SELECT * FROM runs WHERE id=?", (run_id,))
        if not rows:
            return None
        r = dict(rows[0])
        r["params"] = json.loads(r["params"] or "{}")
        r["result"] = json.loads(r["result"]) if r["result"] else None
        return r

    def update_run(self, run_id, **kw):
        if "result" in kw and kw["result"] is not None:
            kw["result"] = json.dumps(kw["result"])
        if "params" in kw:
            kw["params"] = json.dumps(kw["params"])
        kw["updated"] = time.time()
        cols = ", ".join(k + "=?" for k in kw)
        self._x("UPDATE runs SET " + cols + " WHERE id=?", (*kw.values(), run_id))

    def add_credits(self, run_id, amount):
        if run_id and amount:
            self._x("UPDATE runs SET credits=COALESCE(credits,0)+? WHERE id=?", (amount, run_id))

    def list_runs(self, limit=20):
        rows = self._all("SELECT id,request,status,created,credits FROM runs ORDER BY created DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ---- steps
    def step_get(self, run_id, name):
        rows = self._all("SELECT * FROM steps WHERE run_id=? AND name=?", (run_id, name))
        if not rows:
            return None
        r = dict(rows[0])
        r["output"] = json.loads(r["output"]) if r["output"] else None
        return r

    def step_put(self, run_id, name, status, output=None, error=None, started=None):
        self._x("INSERT OR REPLACE INTO steps VALUES(?,?,?,?,?,?,?)",
                (run_id, name, status, json.dumps(output) if output is not None else None, error,
                 started or time.time(), time.time()))

    def steps(self, run_id):
        rows = self._all("SELECT name,status,error,started,finished FROM steps WHERE run_id=? ORDER BY started", (run_id,))
        return [dict(r) for r in rows]

    # ---- events (the UI streams these)
    def add_event(self, run_id, kind, data):
        self._x("INSERT INTO events(run_id,ts,kind,data) VALUES(?,?,?,?)",
                (run_id, time.time(), kind, json.dumps(data)))

    def events_after(self, run_id, last_id):
        rows = self._all("SELECT id,ts,kind,data FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, last_id))
        return [{"id": r["id"], "ts": r["ts"], "kind": r["kind"], "data": json.loads(r["data"])} for r in rows]
