"""Privacy-safe popularity counters: how often is the same claim asked, and which layer answered?

Why: the scale plan (docs/plans/architecture-for-scale.md) depends on how much traffic repeats. These counters measure that with real traffic.

What is stored (all through the existing store, all with an expiry of 40 days):
  d:<UTC day>:total                  requests that day
  d:<UTC day>:layer:<name>           requests answered by cache_exact | cache_claims | match | live | mixed | no_claims
  d:<UTC day>:distinct               claim fingerprints seen for the first time that day
  d:<UTC day>:ge2 | ge5 | ge50 | ge500 | ge5000   how many claim fingerprints reached that many asks that day (each counted once)
  d:<UTC day>:reqs_ge2 | reqs_ge5 ...            requests that were the Nth or later ask of a claim (the share a one-time check could have served)
  pop:<UTC day>:<fingerprint>        that claim's ask count for the day
The fingerprint is the first 16 hex characters of a SHA-256 of the canonical claim text(s). NO claim text, NO IP address, NO user or session id and NO
time of day is stored here. The counters never raise: a store failure means a request is not counted, never that it fails.
Switch off with SACH_POPULARITY=0."""
from __future__ import annotations
import hashlib, os, time
from . import store

TTL_S = 40 * 24 * 3600
THRESHOLDS = (2, 5, 50, 500, 5000)
LAYERS = ("cache_exact", "cache_claims", "match", "live", "mixed", "no_claims")
FREE_LAYERS = ("cache_exact", "cache_claims", "match", "no_claims")      # answered without a paid check


def enabled() -> bool:
    return os.environ.get("SACH_POPULARITY", "1") != "0"


def day(now: float | None = None) -> str:
    return time.strftime("%Y%m%d", time.gmtime(time.time() if now is None else now))


def fingerprint(claim_texts) -> str:
    """16 hex characters from the canonical claim text(s); '' when there is nothing to fingerprint. One-way: the text cannot be read back."""
    from .cache import _claim_norm
    parts = [_claim_norm(c) for c in (claim_texts or []) if c and str(c).strip()]
    if not parts:
        return ""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def layer_of(out: dict, cached: bool) -> str:
    if out.get("no_claims"):
        return "no_claims"
    if cached:
        return "cache_claims" if out.get("cache_kind") == "claims" else "cache_exact"
    lay = str(out.get("layer") or "live")
    return lay if lay in LAYERS else "live"


def _bump(s, name: str, by: int = 1) -> int:
    n = s.incr(name, by)
    if n == by:                                  # first write of this counter: give it its expiry
        s.expire(name, TTL_S)
    return n


def record(out: dict, cached: bool = False, now: float | None = None, st=None) -> None:
    """Count one answered request. Never raises."""
    try:
        if not enabled():
            return
        s = st or store.get_store()
        d = day(now)
        _bump(s, f"d:{d}:total")
        _bump(s, f"d:{d}:layer:{layer_of(out, cached)}")
        texts = [(c.get("claim") or {}).get("text", "") for c in (out.get("claims") or [])[:8] if isinstance(c, dict)]
        fp = fingerprint(texts)
        if not fp:
            return
        n = _bump(s, f"pop:{d}:{fp}")
        if n == 1:
            _bump(s, f"d:{d}:distinct")
        for t in THRESHOLDS:
            if n == t:
                _bump(s, f"d:{d}:ge{t}")        # this claim reached t asks today: counted once per claim
            if n >= t:
                _bump(s, f"d:{d}:reqs_ge{t}")   # this request was the t-th or a later ask of its claim
    except Exception:
        pass


def summary(st=None, now: float | None = None) -> dict:
    """Aggregates for the status page: no fingerprints, no text. `repeat_share` is the share of today's requests that repeated a claim already asked
    that day; `answered_without_paid_check` is the share answered by the cache, the match layer or the no-claims reply."""
    try:
        s = st or store.get_store()
        d = day(now)
        names = [f"d:{d}:total", f"d:{d}:distinct"] + [f"d:{d}:layer:{x}" for x in LAYERS] + \
                [f"d:{d}:ge{t}" for t in THRESHOLDS] + [f"d:{d}:reqs_ge{t}" for t in THRESHOLDS]
        c = s.counters(names)
        total, distinct = c[f"d:{d}:total"], c[f"d:{d}:distinct"]
        layers = {x: c[f"d:{d}:layer:{x}"] for x in LAYERS}
        free = sum(layers[x] for x in FREE_LAYERS)
        return {"day_utc": d, "requests": total, "distinct_claims": distinct, "by_layer": layers,
                "repeat_share": round(1 - distinct / total, 4) if total else None,
                "answered_without_paid_check": round(free / total, 4) if total else None,
                "claims_asked_at_least": {str(t): c[f"d:{d}:ge{t}"] for t in THRESHOLDS},
                "requests_that_were_repeats_at_least": {str(t): c[f"d:{d}:reqs_ge{t}"] for t in THRESHOLDS},
                "note": "Counts per UTC day from anonymous one-way fingerprints of the checked claims. No text, no IP address and no user identity is stored. "
                        "Our own tests and repeats are included, so early numbers overstate repetition."}
    except Exception:
        return {"day_utc": day(now), "requests": 0, "note": "counters unavailable"}
