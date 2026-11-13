"""Admission control: who may start a LIVE check right now, shared across serverless instances through the store.

Why: every live check spends free-tier AI calls and search credits. Cache hits and matches cost nothing, so they are always
served. A live check is admitted only while a global per-minute and per-day budget has room (SACH_MAX_LIVE_PER_MIN /
SACH_MAX_LIVE_PER_DAY, 0 = no limit). When the budget is gone Sach says so honestly (`busy_result`) instead of attempting a check
that would hit provider limits and come back as a vague "Limited mode".

Counting uses `store.incr` on fixed-window keys (minute and UTC day). Fixed windows allow a short burst at a boundary (up to
twice the limit across two adjacent minutes); that is fine for protecting quotas and keeps it to one Redis command per window.

Failure policy: a store that errors (its `incr` returns 0) never blocks anybody. Per-IP limits fall back to the in-memory
limiter of this instance; the global budget falls back to a per-instance in-memory counter, so a broken store can only make the
limits looser, never close the site. Raw IP addresses are never stored: only a short hash inside a key that expires.
stdlib only; imports no network code."""
from __future__ import annotations
import hashlib, os, threading, time
from . import cache, store
from .lang import SUPPORTED

PER_IP_PER_MIN = 8                       # same as web.RATE_LIMIT
DEFAULT_MAX_LIVE_PER_MIN = 6             # sized in docs/scaling.md ("where each limit bites")
DEFAULT_MAX_LIVE_PER_DAY = 100

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default

def max_per_min() -> int:
    return _env_int("SACH_MAX_LIVE_PER_MIN", DEFAULT_MAX_LIVE_PER_MIN)

def max_per_day() -> int:
    return _env_int("SACH_MAX_LIVE_PER_DAY", DEFAULT_MAX_LIVE_PER_DAY)

# ---------------------------------------------------------------- in-memory fallback (per instance)
_mem: dict = {}
_mem_lock = threading.Lock()

def _mem_incr(key: str, by: int = 1) -> int:
    with _mem_lock:
        if len(_mem) > 500:
            _mem.clear()
        _mem[key] = _mem.get(key, 0) + by
        return _mem[key]

def reset_memory() -> None:
    with _mem_lock:
        _mem.clear()

def _incr(st, key: str, ttl: int, by: int = 1) -> tuple[int, bool]:
    """-> (count, from_store). Falls back to this instance's memory when the store cannot answer."""
    try:
        n = st.incr(key, by) if getattr(st, "remote", False) else 0
    except Exception:
        n = 0
    if isinstance(n, int) and n > 0:
        if n == by and by > 0:
            try:
                st.expire(key, ttl)
            except Exception:
                pass
        return n, True
    return _mem_incr(key, by), False

# ---------------------------------------------------------------- per-IP
def ip_limited(ip: str, fallback, kind: str = "check", limit: int = PER_IP_PER_MIN, st=None, now=None) -> bool:
    """True if this IP is over its per-minute allowance. `fallback(ip, kind, limit)` is the in-memory limiter (web.rate_limited):
    used alone when there is no remote store, and whenever the store fails (fail open to the old behaviour)."""
    st = st or store.get_store()
    if not getattr(st, "remote", False):
        return fallback(ip, kind, limit)
    minute = int((now if now is not None else time.time()) // 60)
    key = "rl:%s:%s:%d" % (kind, hashlib.sha256((ip or "?").encode()).hexdigest()[:16], minute)
    try:
        n = st.incr(key)
    except Exception:
        n = 0
    if not (isinstance(n, int) and n > 0):
        return fallback(ip, kind, limit)
    if n == 1:
        try:
            st.expire(key, 120)
        except Exception:
            pass
    return n > limit

# ---------------------------------------------------------------- global live budget
class Admission:
    """kind: 'free' (cache or match: costs nothing), 'live' (a slot was reserved) or 'busy' (budget gone, do not run live)."""
    def __init__(self, kind: str, reason: str = "", retry_after: int = 0, keys=()):
        self.kind, self.reason, self.retry_after, self.keys = kind, reason, retry_after, tuple(keys)
    @property
    def busy(self) -> bool:
        return self.kind == "busy"

_free_probes: list = []

def register_free_probe(fn) -> None:
    """fn(text, reply_lang) -> truthy when this text would be answered without a live check (e.g. a match against known debunks).
    Called before a slot is reserved; any exception counts as 'not free'."""
    if fn not in _free_probes:
        _free_probes.append(fn)

def _is_free(text: str, rl) -> bool:
    if cache.enabled() and cache.lookup(text, rl) is not None:
        return True
    for fn in list(_free_probes):
        try:
            if fn(text, rl):
                return True
        except Exception:
            continue
    return False

def _windows(now: float):
    m, d = int(now // 60), int(now // 86400)
    return ("lv:m:%d" % m, 60 - int(now % 60)), ("lv:d:%d" % d, 86400 - int(now % 86400))

def admit(text: str, reply_lang=None, st=None, now=None) -> Admission:
    """Decide whether a check of `text` may run. Never raises."""
    try:
        rl = reply_lang if reply_lang in SUPPORTED else None
        if _is_free(text, rl):
            return Admission("free")
        pm, pd = max_per_min(), max_per_day()
        if pm <= 0 and pd <= 0:
            return Admission("live")
        st = st or store.get_store()
        now = time.time() if now is None else now
        (km, wait_m), (kd, wait_d) = _windows(now)
        nm = _incr(st, km, 120)[0] if pm > 0 else 0
        nd = _incr(st, kd, 2 * 86400)[0] if pd > 0 else 0
        if pm > 0 and nm > pm:
            _give_back(st, km if pm > 0 else None, kd if pd > 0 else None)
            _count_busy(st, now)
            return Admission("busy", "minute", max(wait_m, 5))
        if pd > 0 and nd > pd:
            _give_back(st, km if pm > 0 else None, kd)
            _count_busy(st, now)
            return Admission("busy", "day", min(wait_d, 3600))
        return Admission("live", keys=[k for k, on in ((km, pm > 0), (kd, pd > 0)) if on])
    except Exception:
        return Admission("live")                     # never block a check because the limiter itself broke

def _decr(st, key: str) -> None:
    try:
        if getattr(st, "remote", False):
            st.incr(key, -1)
        else:
            _mem_incr(key, -1)
    except Exception:
        pass

def _give_back(st, *keys) -> None:
    """A refused request must not use up budget: return the slots it reserved."""
    for k in keys:
        if k:
            _decr(st, k)

def _count_busy(st, now):
    try:
        _incr(st, "lv:busy:%d" % int(now // 86400), 2 * 86400)
    except Exception:
        pass

def refund(adm: Admission, res=None, st=None) -> None:
    """Give the slot back when the pipeline answered without a live check after all (a cache or match hit that appeared in
    between). `res` is the pipeline result; a refund happens only for results marked cached / matched."""
    try:
        if adm is None or adm.kind != "live" or not isinstance(res, dict):
            return
        if not (res.get("cached") or res.get("matched")):
            return
        st = st or store.get_store()
        _give_back(st, *adm.keys)
    except Exception:
        pass

def usage(st=None, now=None) -> dict:
    """Budget used this minute and today, as far as the store (or this instance's memory) knows. Reads only."""
    st, now = st or store.get_store(), time.time() if now is None else now
    (km, _), (kd, _) = _windows(now)
    kb = "lv:busy:%d" % int(now // 86400)
    try:
        c = st.counters([km, kd, kb]) if getattr(st, "remote", False) else {}
    except Exception:
        c = {}
    with _mem_lock:
        mem = dict(_mem)
    pick = lambda k: max(int(c.get(k, 0) or 0), int(mem.get(k, 0)))
    return {"minute_used": pick(km), "minute_max": max_per_min(), "day_used": pick(kd), "day_max": max_per_day(),
            "busy_today": pick(kb), "shared_store": bool(getattr(st, "remote", False))}

# ---------------------------------------------------------------- the honest "busy" answer (never a verdict)
BUSY_TITLE = "Sach is very busy right now"
PIB_PORTAL = "https://factcheck.pib.gov.in/"
PIB_WHATSAPP = "https://wa.me/918799711259"

def busy_message(reason: str = "minute") -> str:
    when = "in a few minutes" if reason != "day" else "in a few hours (our free daily capacity is used up)"
    return ("Sach is very busy right now, so we have not checked this message and we are not giving a verdict. "
            f"Please try again {when}. Messages Sach has already checked are still answered instantly. "
            "To check something now, you can send it to PIB Fact Check yourself.")

def busy_result(reason: str = "minute", retry_after: int = 60) -> dict:
    """JSON body for the API. There is deliberately NO 'verdict' key: nothing was checked."""
    return {"busy": True, "checked": False, "reason": reason, "retry_after_s": int(retry_after), "title": BUSY_TITLE,
            "message": busy_message(reason),
            "links": {"pib_fact_check_portal": PIB_PORTAL, "pib_fact_check_whatsapp": PIB_WHATSAPP}}

def busy_block(reason: str = "minute") -> str:
    from .site import esc
    return ('<div class="honest" style="margin-top:18px" role="status" id="busy-notice"><b>%s.</b> %s '
            '<a href="%s" rel="noopener">PIB Fact Check portal</a> &middot; <a href="%s" rel="noopener">PIB Fact Check on WhatsApp (+91 87997 11259)</a></div>'
            % (esc(BUSY_TITLE), esc(busy_message(reason)), PIB_PORTAL, PIB_WHATSAPP))

def busy_text(reason: str = "minute") -> str:
    """Plain text for the Telegram bot."""
    return f"{BUSY_TITLE}.\n{busy_message(reason)}\nPIB Fact Check: {PIB_PORTAL} or WhatsApp +91 87997 11259 ({PIB_WHATSAPP})"
