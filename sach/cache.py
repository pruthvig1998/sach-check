"""Verdict cache for repeated forwards. Keyed by normalised text + reply language. Used by pipeline.check_forward."""
from __future__ import annotations
import hashlib, os, re, unicodedata
from .extract import clean_text
from . import store

TTL_DECISIVE_S = int(os.environ.get("SACH_CACHE_TTL_DECISIVE_S", 7 * 24 * 3600))   # TRUE / FALSE / MISLEADING
TTL_UNVERIFIED_S = int(os.environ.get("SACH_CACHE_TTL_UNVERIFIED_S", 6 * 3600))    # an official source may appear later
_VERDICT_POLICY = 1  # requires final source URLs, fetched citations and independent model confirmation

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

def claim_cache_enabled() -> bool:
    """L0: also key the cache by the extracted claims, so a forward that differs only by greetings, 'forwarded' lines or emoji reuses the
    same checked answer. Switch off with SACH_CLAIM_CACHE=0."""
    return os.environ.get("SACH_CLAIM_CACHE", "1") != "0"

def _claim_norm(t: str) -> str:
    return re.sub(r"[\s.।॥]+$", "", normalise(t))          # only a trailing full stop is ignored: '?' and '!' change what is being said

def claim_key(claim_texts, reply_lang: str | None, input_lang: str | None = None) -> str | None:
    """Cache key for the set of checked claims (their order kept, a trailing full stop ignored). The INPUT language is part of the key: search and
    translation run in it, and the card follows it when no reply language is chosen. None when there is nothing to key on."""
    parts = [_claim_norm(c) for c in claim_texts if c and c.strip()]
    if not parts:
        return None
    rl = reply_lang if reply_lang else "auto"
    return "cacheC:" + hashlib.sha256(("\x1f".join(parts) + "\x00" + rl + "\x00" + (input_lang or "")).encode("utf-8")).hexdigest()

def _input_lang(text: str) -> str:
    """The same first-pass language the pipeline uses for the lookup (before refinement), so a stored claim key is reachable by the next lookup."""
    from .lang import detect_language
    return detect_language(text)

def lookup(text: str, reply_lang: str | None):
    return lookup_key(key(text, reply_lang))

def lookup_by_claims(claim_texts, reply_lang: str | None, input_lang: str | None = None):
    k = claim_key(claim_texts, reply_lang, input_lang) if claim_cache_enabled() else None
    return lookup_key(k) if k else None

def lookup_key(k: str):
    try:
        v = store.get_store().get(k)
        if not (isinstance(v, dict) and v.get("verdict") and "claims" in v):
            return None
        if v.get("layer") != "match" and v.get("_verdict_policy") != _VERDICT_POLICY:
            return None
        if _poisoned(v):
            return None
        return {k: value for k, value in v.items() if k != "_verdict_policy"}
    except Exception:
        return None

def save(text: str, reply_lang: str | None, out: dict) -> None:
    try:
        if storable(out):
            value, ttl = {**out, "_verdict_policy": _VERDICT_POLICY}, ttl_for(out)
            store.get_store().set(key(text, reply_lang), value, ttl_s=ttl)
            ck = claim_key([(c.get("claim") or {}).get("text", "") for c in out.get("claims", []) if isinstance(c, dict)], reply_lang,
                           _input_lang(text)) if claim_cache_enabled() else None
            if ck:
                store.get_store().set(ck, value, ttl_s=ttl)
    except Exception:
        pass
