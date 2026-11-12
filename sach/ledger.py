from __future__ import annotations
import json, os, threading
from datetime import datetime, timezone
_lock = threading.Lock()

def path():
    return os.environ.get("SACH_LEDGER", "data/ledger.json")

_SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ledger_seed.json")

def load() -> list:
    """Live ledger plus the bundled starter ledger (so a fresh serverless instance isn't empty)."""
    p = path()
    live = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    seed = json.load(open(_SEED, encoding="utf-8")) if os.path.exists(_SEED) else []
    return seed + live

def append(entry: dict) -> None:
    with _lock:
        p = path()
        rows = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
        rows.append(entry)
        os.makedirs(os.path.dirname(path()) or ".", exist_ok=True)
        json.dump(rows, open(path(), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
