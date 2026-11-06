"""Crustdata client: auth headers, timeouts, 429 retry using x-ratelimit-reset, error classes,
response cache (a retry or resume never re-spends credits) and a credit budget guard."""
import collections
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request

from . import fixtures

BASE = "https://api.crustdata.com"
VERSION = "2025-11-01"


class CrustdataError(Exception):
    def __init__(self, status, body):
        super().__init__("Crustdata HTTP %s: %s" % (status, str(body)[:300]))
        self.status, self.body = status, body


class OutOfCredits(CrustdataError):
    """402: retrying will not help."""


# In-memory ring buffer of recent API calls, shown in the UI's call log. Holds no keys and no response bodies.
LOG = collections.deque(maxlen=400)
_LOG_LOCK = threading.Lock()
_LOG_SEQ = [0]


def _brief(path, body):
    """A short human description of what a call asks for."""
    b = body or {}
    if "search" in b and isinstance(b["search"], dict):
        return (b["search"].get("query") or "")[:70]
    if "crustdata_company_ids" in b:
        return "%d compan%s" % (len(b["crustdata_company_ids"]), "y" if len(b["crustdata_company_ids"]) == 1 else "ies")
    if "query" in b:
        return str(b["query"])[:70]
    f = b.get("filters")
    if isinstance(f, dict):
        conds = f.get("conditions") or [f]
        return ", ".join("%s %s %s" % (str(c.get("field", "")).split(".")[-1], c.get("type", ""), str(c.get("value", ""))[:20]) for c in conds[:2])
    return ""


def log_call(path, body, source, credits=0.0, ms=0, status="ok"):
    with _LOG_LOCK:
        _LOG_SEQ[0] += 1
        LOG.append({"id": _LOG_SEQ[0], "ts": time.strftime("%H:%M:%S"), "path": path, "what": _brief(path, body), "source": source,
                    "credits": round(credits, 2), "ms": int(ms), "status": status})


def log_since(after=0):
    with _LOG_LOCK:
        return [e for e in LOG if e["id"] > after]


class BudgetExceeded(Exception):
    """Our own guard: the run spent its credit budget."""


class Client:
    def __init__(self, key, store, run_id=None, budget=None, offline=False, on_warn=None):
        self.key, self.store, self.run_id = key, store, run_id
        self.budget, self.offline = budget, offline
        self.spent = 0.0
        self.calls = 0
        self.cache_hits = 0
        self.on_warn = on_warn or (lambda m: None)

    def remaining_budget(self):
        return None if self.budget is None else self.budget - self.spent

    def call(self, path, body, method="POST", use_cache=True):
        ck = hashlib.sha256((method + path + json.dumps(body, sort_keys=True)).encode()).hexdigest()
        if use_cache:
            hit = self.store.cache_get(ck)
            if hit is not None:
                self.cache_hits += 1
                log_call(path, body, "cache")
                return hit
        if self.offline:
            return fixtures.answer(path, body)
        if self.budget is not None and self.spent >= self.budget:
            raise BudgetExceeded("credit budget of %s reached (spent %.2f)" % (self.budget, self.spent))
        if not self.key:
            raise CrustdataError(401, "CRUSTDATA_KEY is not set")
        t0 = time.time()
        try:
            data, credits = self._http(path, body, method)
        except Exception as e:  # noqa: BLE001
            log_call(path, body, "live", 0.0, (time.time() - t0) * 1000, "error %s" % getattr(e, "status", "") if hasattr(e, "status") else "error")
            raise
        log_call(path, body, "live", credits, (time.time() - t0) * 1000)
        self.calls += 1
        self.spent += credits
        self.store.add_credits(self.run_id, credits)
        if use_cache:
            self.store.cache_put(ck, path, data, credits)
        return data

    def _http(self, path, body, method):
        headers = {"authorization": "Bearer " + self.key, "content-type": "application/json",
                   "x-api-version": VERSION, "user-agent": "orgchart-xray/0.1"}
        last = None
        for attempt in range(6):
            req = urllib.request.Request(BASE + path, method=method, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None)
            try:
                r = urllib.request.urlopen(req, timeout=90)
                credits = float(r.headers.get("X-Credits-Used", 0) or 0)
                return json.loads(r.read().decode("utf-8")), credits
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")
                if e.code == 429:
                    wait = min(float(e.headers.get("x-ratelimit-reset", 5) or 5) + 0.5, 65)
                    self.on_warn("rate limited (429): waiting %.0fs then retrying" % wait)
                    time.sleep(wait)
                    last = e
                    continue
                if e.code == 402:
                    raise OutOfCredits(402, text)
                if e.code >= 500:
                    self.on_warn("server error %s: retrying" % e.code)
                    time.sleep(2 ** attempt)
                    last = e
                    continue
                raise CrustdataError(e.code, text)  # 400/401/403/404: do not retry
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.on_warn("network problem (%s): retrying" % e)
                time.sleep(2 ** attempt)
                last = e
        raise CrustdataError(0, "gave up after retries: %s" % last)
