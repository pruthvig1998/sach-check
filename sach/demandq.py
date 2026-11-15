"""Demand queue: claims many people asked while the live budget was used up, worked through by how many asked.

Privacy (owner decision, 14 Nov 2026): once a claim has been asked MIN_ASKS times while Sach could not check it, the extracted claim sentence(s)
(not the full forward, no IP, no identity, no time of day) are kept for 30 days so a later run can check them. Counting before that point is by the
anonymous fingerprint only. Switch off with SACH_DEMAND_QUEUE=0. Nothing here can change a verdict: queued claims go through the normal pipeline."""
from __future__ import annotations
import os, re, time
from . import store

TTL_S = 30 * 24 * 3600
MAX_CLAIMS_KEPT = 3
MAX_CLAIM_CHARS = 500
LIST = "dq:list"
_NUMBER = re.compile(r"\+?\d[\d\s\-]{5,}\d")
_HANDLE = re.compile(r"\S+@\S+")


def _scrub(t: str) -> str:
    """Phone numbers and UPI or email handles in a claim are replaced before storage: the queue needs the claim, not the contact."""
    return _HANDLE.sub("[id]", _NUMBER.sub("[number]", t.strip()))[:MAX_CLAIM_CHARS]


def enabled() -> bool:
    return os.environ.get("SACH_DEMAND_QUEUE", "1") != "0"


def min_asks() -> int:
    try:
        return max(2, int(os.environ.get("SACH_QUEUE_MIN_ASKS", "5")))
    except ValueError:
        return 5


def note(text: str, st=None) -> None:
    """Count one unserved ask of this text's claims; queue the claims when they reach min_asks. Never raises."""
    try:
        if not enabled():
            return
        from .limits import _claims_and_lang
        from .popularity import fingerprint
        texts, lang = _claims_and_lang(text)
        fp = fingerprint(texts)
        if not fp:
            return
        s = st or store.get_store()
        n = s.incr("dq:n:" + fp)
        if not (isinstance(n, int) and n > 0):
            return
        if n in (1, min_asks()):
            s.expire("dq:n:" + fp, TTL_S)
        if n == min_asks():
            kept = [_scrub(t) for t in texts[:MAX_CLAIMS_KEPT] if t and t.strip()]
            s.set("dq:c:" + fp, {"claims": kept, "lang": lang, "queued_at": int(time.time())}, ttl_s=TTL_S)
            s.push(LIST, fp, cap=500)
            s.incr("dq:queued")
    except Exception:
        pass


def pending(st=None, limit: int = 20) -> list:
    """Queued claims not yet checked, most asked first: [{fp, asks, claims, lang}]."""
    s = st or store.get_store()
    out = []
    for fp in dict.fromkeys(s.items(LIST)):
        try:
            c = s.get("dq:c:" + fp)
            if not isinstance(c, dict) or s.get("dq:done:" + fp):
                continue
            n = (s.counters(["dq:n:" + fp]) or {}).get("dq:n:" + fp, 0)
            out.append({"fp": fp, "asks": int(n or 0), "claims": c.get("claims") or [], "lang": c.get("lang")})
        except Exception:
            continue
    out.sort(key=lambda r: -r["asks"])
    return out[:limit]


def mark_done(fp: str, st=None) -> None:
    try:
        s = st or store.get_store()
        s.set("dq:done:" + fp, 1, ttl_s=TTL_S)
        s.incr("dq:finished")
    except Exception:
        pass


def size(st=None) -> int:
    """Waiting claims, from two counters (no per-claim reads, so the status page stays cheap)."""
    try:
        c = (st or store.get_store()).counters(["dq:queued", "dq:finished"]) or {}
        return max(0, int(c.get("dq:queued", 0) or 0) - int(c.get("dq:finished", 0) or 0))
    except Exception:
        return 0


def work(check, max_checks: int = 5, st=None, dry_run: bool = True, reserve_share: float = 0.5) -> list:
    """Check queued claims, most asked first. `check(text)` runs the normal pipeline. Uses the same live budget as visitors and stops when
    the day's used share passes `reserve_share` of the cap (visitors keep the rest), or on the first busy answer. Returns what it did."""
    from . import limits
    s = st or store.get_store()
    done = []
    for row in pending(s, limit=max_checks):
        text = "\n".join(row["claims"])
        if dry_run:
            done.append({"fp": row["fp"], "asks": row["asks"], "action": "would_check"})
            continue
        cap, used = limits.max_per_day(), limits.usage(s)["day_used"]
        if cap > 0 and used >= cap * reserve_share:
            done.append({"fp": row["fp"], "action": "stopped_reserve"})
            break
        adm = limits.admit(text, st=s)
        if adm.busy:
            done.append({"fp": row["fp"], "action": "stopped_busy", "reason": adm.reason})
            break
        if adm.kind != "live":                              # answered from the cache or a match: finished only if that answer is decisive
            from . import cache
            hit = cache.lookup_by_claims(row["claims"], None, row.get("lang")) or cache.lookup(text, None)
            if hit and hit.get("verdict") != "UNVERIFIED":
                mark_done(row["fp"], s)
                done.append({"fp": row["fp"], "action": "already_answered", "verdict": hit.get("verdict")})
            else:
                done.append({"fp": row["fp"], "action": "skipped_cached_unverified"})
            continue
        try:
            res = check(text)
        except Exception:
            limits.release(adm, st=s)
            limits._give_back(s, *adm.keys)                 # a failed check must not use up budget
            done.append({"fp": row["fp"], "action": "error"})
            continue
        limits.release(adm, st=s)
        limits.refund(adm, res, st=s)
        from . import cache
        if not cache.storable(res or {}):                   # timed out or degraded: nothing was stored, so the claim stays queued
            done.append({"fp": row["fp"], "action": "not_stored_kept_queued"})
            continue
        mark_done(row["fp"], s)
        done.append({"fp": row["fp"], "asks": row["asks"], "action": "checked", "verdict": (res or {}).get("verdict")})
    return done
