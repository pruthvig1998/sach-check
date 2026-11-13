"""Tiny key-value storage for the cache, counters and ledger rows.

Two backends: FileStore (default, JSON files) and UpstashStore (Upstash Redis REST API, used when a REST URL and
token are in the environment). Any storage failure is swallowed: reads behave as a miss, writes are dropped.
A fact-check must never fail because storage did."""
from __future__ import annotations
import hashlib, json, os, tempfile, threading, time
import urllib.request

PREFIX = "sach:"
_lock = threading.RLock()

def _now() -> float:
    return time.time()

class FileStore:
    remote = False

    def __init__(self, directory: str):
        self.dir = directory

    def _file(self, kind: str, key: str) -> str:
        return os.path.join(self.dir, kind + "_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")

    def _read(self, path: str, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write(self, path: str, data) -> None:
        try:
            os.makedirs(self.dir, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, path)
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        except Exception:
            pass

    def get(self, key: str):
        try:
            with _lock:
                rec = self._read(self._file("kv", key), None)
            if not isinstance(rec, dict) or "v" not in rec:
                return None
            if rec.get("exp") is not None and rec["exp"] <= _now():
                return None
            return rec["v"]
        except Exception:
            return None

    def set(self, key: str, value, ttl_s=None) -> None:
        try:
            with _lock:
                self._write(self._file("kv", key), {"v": value, "exp": (_now() + ttl_s) if ttl_s else None})
        except Exception:
            pass

    def incr(self, name: str, by: int = 1) -> int:
        try:
            with _lock:
                p = os.path.join(self.dir, "counters.json")
                c = self._read(p, {})
                if not isinstance(c, dict):
                    c = {}
                c[name] = int(c.get(name, 0)) + by
                self._write(p, c)
                return c[name]
        except Exception:
            return 0

    def expire(self, name: str, ttl_s: int) -> None:
        """Counters in the local file never expire (only used in development / single instance); nothing to do."""

    def counters(self, names) -> dict:
        try:
            with _lock:
                c = self._read(os.path.join(self.dir, "counters.json"), {})
            if not isinstance(c, dict):
                c = {}
            return {n: int(c.get(n, 0)) for n in names}
        except Exception:
            return {n: 0 for n in names}

    def push(self, list_name: str, value, cap: int = 500) -> None:
        try:
            with _lock:
                p = self._file("list", list_name)
                rows = self._read(p, [])
                if not isinstance(rows, list):
                    rows = []
                rows.append(value)
                self._write(p, rows[-cap:])
        except Exception:
            pass

    def items(self, list_name: str) -> list:
        try:
            with _lock:
                rows = self._read(self._file("list", list_name), [])
            return rows if isinstance(rows, list) else []
        except Exception:
            return []


class UpstashStore:
    remote = True

    def __init__(self, url: str, token: str, opener=None):
        self.url = url.rstrip("/")
        self.token = token
        self.opener = opener or urllib.request.urlopen

    def _cmd(self, *cmd):
        """Run one Redis command. Returns the 'result' field, or None on any failure."""
        try:
            req = urllib.request.Request(self.url, data=json.dumps(list(cmd)).encode("utf-8"), method="POST",
                                         headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
            with self.opener(req, timeout=2) as r:
                if getattr(r, "status", 200) != 200:
                    return None
                body = json.loads(r.read().decode("utf-8"))
            return body.get("result") if isinstance(body, dict) else None
        except Exception:
            return None

    def get(self, key: str):
        raw = self._cmd("GET", PREFIX + key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value, ttl_s=None) -> None:
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except Exception:
            return
        if ttl_s:
            self._cmd("SET", PREFIX + key, payload, "EX", int(ttl_s))
        else:
            self._cmd("SET", PREFIX + key, payload)

    def incr(self, name: str, by: int = 1) -> int:
        r = self._cmd("INCRBY", PREFIX + "c:" + name, int(by))
        return r if isinstance(r, int) else 0

    def expire(self, name: str, ttl_s: int) -> None:
        """Let a counter (e.g. a per-minute rate-limit key) delete itself, so they do not pile up in the free 250 MB database."""
        self._cmd("EXPIRE", PREFIX + "c:" + name, int(ttl_s))

    def counters(self, names) -> dict:
        names = list(names)
        if not names:
            return {}
        r = self._cmd("MGET", *[PREFIX + "c:" + n for n in names])
        out = {}
        for i, n in enumerate(names):
            try:
                out[n] = int(r[i] or 0)
            except Exception:
                out[n] = 0
        return out

    def push(self, list_name: str, value, cap: int = 500) -> None:
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except Exception:
            return
        k = PREFIX + "l:" + list_name
        if self._cmd("RPUSH", k, payload) is not None:
            self._cmd("LTRIM", k, -int(cap), -1)

    def items(self, list_name: str) -> list:
        r = self._cmd("LRANGE", PREFIX + "l:" + list_name, 0, -1)
        out = []
        for raw in r if isinstance(r, list) else []:
            try:
                out.append(json.loads(raw))
            except Exception:
                pass
        return out


_inst = None
_inst_key = None

def _env_config():
    e = os.environ
    url = e.get("UPSTASH_REDIS_REST_URL") or e.get("KV_REST_API_URL") or ""
    tok = e.get("UPSTASH_REDIS_REST_TOKEN") or e.get("KV_REST_API_TOKEN") or ""
    if url and tok:
        return ("upstash", url, tok)
    d = e.get("SACH_STORE_DIR") or os.path.join(os.path.dirname(os.path.abspath(e.get("SACH_LEDGER", "data/ledger.json"))), "store")
    return ("file", d)

def get_store():
    """Process-wide store; rebuilt whenever the relevant environment variables change."""
    global _inst, _inst_key
    key = _env_config()
    if _inst is None or key != _inst_key:
        _inst = UpstashStore(key[1], key[2]) if key[0] == "upstash" else FileStore(key[1])
        _inst_key = key
    return _inst

def reset() -> None:
    global _inst, _inst_key
    _inst = _inst_key = None
