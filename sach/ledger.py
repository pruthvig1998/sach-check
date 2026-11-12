from __future__ import annotations
import json, os, threading
from datetime import datetime, timezone
_lock = threading.Lock()

def path():
    return os.environ.get("SACH_LEDGER", "data/ledger.json")

def load() -> list:
    p = path()
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []

def append(entry: dict) -> None:
    with _lock:
        rows = load()
        rows.append(entry)
        os.makedirs(os.path.dirname(path()) or ".", exist_ok=True)
        json.dump(rows, open(path(), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
