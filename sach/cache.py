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

def _poisoned(v: dict) -> bool:
    """An UNVERIFIED live result stored before judge outcomes were recorded (no `timing_ms` in any claim trace) may be a silent
    judge failure that got cached (13 Nov incident). Treat it as a miss so the claim is checked again; decisive verdicts and
    matches carry real evidence and stay valid."""
    if v.get("verdict") != "UNVERIFIED" or v.get("layer") == "match" or v.get("no_claims"):
        return False
    claims = v.get("claims") or []
    return bool(claims) and not any((c.get("trace") or {}).get("timing_ms") for c in claims if isinstance(c, dict))

def lookup(text: str, reply_lang: str | None):
    try:
        v = store.get_store().get(key(text, reply_lang))
        if not (isinstance(v, dict) and v.get("verdict") and "claims" in v):
            return None
        if _poisoned(v):
            return None
        return v
    except Exception:
        return None

def save(text: str, reply_lang: str | None, out: dict) -> None:
    try:
        if storable(out):
            store.get_store().set(key(text, reply_lang), out, ttl_s=ttl_for(out))
    except Exception:
        pass
