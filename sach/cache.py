"""Verdict cache for repeated forwards. Keyed by normalised text + reply language. Used by pipeline.check_forward."""
from __future__ import annotations
import hashlib, os, re, unicodedata
from .extract import clean_text
from . import store

TTL_DECISIVE_S = int(os.environ.get("SACH_CACHE_TTL_DECISIVE_S", 7 * 24 * 3600))   # TRUE / FALSE / MISLEADING
TTL_UNVERIFIED_S = int(os.environ.get("SACH_CACHE_TTL_UNVERIFIED_S", 6 * 3600))    # an official source may appear later

def enabled(use_cache: bool = True, log: bool = True) -> bool:
    return bool(use_cache) and bool(log) and os.environ.get("SACH_NO_CACHE") != "1"

def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", clean_text(text)).casefold()
    return re.sub(r"\s+", " ", t).strip()

def key(text: str, reply_lang: str | None) -> str:
    rl = reply_lang if reply_lang else "auto"
    return "cache:" + hashlib.sha256((normalise(text) + "\x00" + rl).encode("utf-8")).hexdigest()

def storable(out: dict) -> bool:
    if out.get("degraded") or out.get("no_claims") or out.get("search_status") in ("down", "partial"):   # an outage must not be cached as an answer
        return False
    return not any(c.get("reason_code") == "timed_out" for c in out.get("claims", []))

def ttl_for(out: dict) -> int:
    return TTL_UNVERIFIED_S if out.get("verdict") == "UNVERIFIED" else TTL_DECISIVE_S

def lookup(text: str, reply_lang: str | None):
    try:
        v = store.get_store().get(key(text, reply_lang))
        return v if isinstance(v, dict) and v.get("verdict") and "claims" in v else None
    except Exception:
        return None

def save(text: str, reply_lang: str | None, out: dict) -> None:
    try:
        if storable(out):
            store.get_store().set(key(text, reply_lang), out, ttl_s=ttl_for(out))
    except Exception:
        pass
