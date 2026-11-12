from __future__ import annotations
import json, os, threading
from datetime import datetime, timezone
from . import store
_lock = threading.Lock()

def path():
    return os.environ.get("SACH_LEDGER", "data/ledger.json")

_SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ledger_seed.json")

COUNTERS = ("checks_total", "cache_hits", "no_claims", "verdict:TRUE", "verdict:FALSE", "verdict:MISLEADING", "verdict:UNVERIFIED",
            "lang:en", "lang:hi", "lang:te", "lang:tl")

def _row_key(r):
    return (r.get("claim"), r.get("checked_at")) if isinstance(r, dict) else None

def load() -> list:
    """Starter ledger + live file rows + shared-store rows (only present with a remote store), without duplicates."""
    p = path()
    try:
        live = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    except Exception:
        live = []
    seed = json.load(open(_SEED, encoding="utf-8")) if os.path.exists(_SEED) else []
    out, seen = [], set()
    for r in seed + live + store.get_store().items("ledger"):
        k = _row_key(r)
        if k is None or k in seen:
            continue
        seen.add(k); out.append(r)
    return out

def append(entry: dict) -> None:
    # The file is the ledger of record. A remote store (Vercel: disk is temporary and per-instance) gets the row too;
    # the local FileStore does not, because that would only duplicate the file.
    with _lock:
        try:
            p = path()
            rows = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
            rows.append(entry)
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            json.dump(rows, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass                                   # read-only disk: the shared store below may still keep it
    s = store.get_store()
    if s.remote:
        s.push("ledger", entry, cap=500)

def record_check(out: dict, cached: bool = False) -> None:
    """Count one completed check (call only when logging is on). Never raises."""
    try:
        s = store.get_store()
        s.incr("checks_total")
        if cached:
            s.incr("cache_hits")
        if out.get("no_claims"):
            s.incr("no_claims")
        else:
            s.incr("verdict:" + str(out.get("verdict")))
        s.incr("lang:" + str(out.get("input_language", "en")))
        if s.get("first_event_at") is None:
            s.set("first_event_at", now())
    except Exception:
        pass

def stats() -> dict:
    s = store.get_store()
    c = s.counters(COUNTERS)
    c["first_event_at"] = s.get("first_event_at")
    c["ledger_rows"] = len(load())
    return c

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
