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
    def __init__(self, kind: str, reason: str = "", retry_after: int = 0, keys=(), flight: str = "", flight_mem: bool = False):
        self.kind, self.reason, self.retry_after, self.keys, self.flight = kind, reason, retry_after, tuple(keys), flight
        self.flight_mem = flight_mem               # the flight place was taken in this instance's memory, so it is given back there
    @property
    def busy(self) -> bool:
        return self.kind == "busy"

_free_probes: list = []

def register_free_probe(fn) -> None:
    """fn(text, reply_lang) -> truthy when this text would be answered without a live check (e.g. a match against known debunks).
    Called before a slot is reserved; any exception counts as 'not free'."""
    if fn not in _free_probes:
        _free_probes.append(fn)

def _claims_and_lang(text: str):
    """The checked claims and input language the pipeline would derive from this text (same functions, same limit), for the claim-keyed cache and the flight key."""
    from .extract import clean_text, extract_claims
    from .lang import detect_language
    from .pipeline import MAX_CLAIMS
    t = clean_text(text)
    return [c.text for c in extract_claims(t, max_claims=MAX_CLAIMS)], detect_language(t)

def _is_free(text: str, rl) -> bool:
    if cache.enabled() and cache.lookup(text, rl) is not None:
        return True
    if cache.enabled():
        try:
            texts, lang = _claims_and_lang(text)
            if texts and cache.lookup_by_claims(texts, rl, lang) is not None:
                return True                      # the same claims under different wrapper text: answered from the cache, so no live slot
        except Exception:
            pass
    for fn in list(_free_probes):
        try:
            if fn(text, rl):
                return True
        except Exception:
            continue
    return False

# ---------------------------------------------------------------- single-flight: one live check per new claim at a time
FLIGHT_TTL_S = 90                                  # a crashed leader frees the claim after this
_sleep = time.sleep                                # replaced in tests

def flight_enabled() -> bool:
    return os.environ.get("SACH_SINGLE_FLIGHT", "1") != "0"

def flight_wait_s() -> int:
    return min(25, max(0, _env_int("SACH_FLIGHT_WAIT_S", 10)))

def _flight_key(text: str, rl) -> str:
    try:
        texts, lang = _claims_and_lang(text)
        k = cache.claim_key(texts, rl, lang) if texts else None
    except Exception:
        k = None
    return "sf:" + (k or cache.key(text, rl))

def _await_answer(text: str, rl, st, fk: str):
    """Another request is already checking this claim. Wait a few seconds for its stored answer; if it appears this request is free, otherwise it is
    told plainly that the claim is being checked (no second paid check, no verdict). Always gives its own place back."""
    deadline = time.time() + flight_wait_s()
    while time.time() < deadline:
        _sleep(2.5)
        if _is_free(text, rl):
            return Admission("free")
    return Admission("busy", "flight", 20)

def release(adm, st=None) -> None:
    """The leader of a flight is done (answered, failed or refunded): the next ask of this claim may start a check."""
    try:
        if adm is not None and getattr(adm, "flight", ""):
            _release_flight(st or store.get_store(), adm.flight, bool(getattr(adm, "flight_mem", False)))
    except Exception:
        pass

def _release_flight(st, key: str, mem: bool) -> None:
    """Give a flight place back on the backend it was taken from, and never leave a negative counter behind (an expired key would otherwise
    go to -1 with no expiry and lock the claim, or let two checks run at once)."""
    if mem or not getattr(st, "remote", False):
        with _mem_lock:
            if _mem.get(key, 0) > 0:
                _mem[key] -= 1
        return
    try:
        n = st.incr(key, -1)
        if isinstance(n, int) and n < 0:
            st.incr(key, -n)                          # the key had already expired: put it back to zero
            st.expire(key, 1)
    except Exception:
        pass

def _windows(now: float):
    m, d = int(now // 60), int(now // 86400)
    return ("lv:m:%d" % m, 60 - int(now % 60)), ("lv:d:%d" % d, 86400 - int(now % 86400))

def admit(text: str, reply_lang=None, st=None, now=None, force_live: bool = False) -> Admission:
    """Decide whether a check of `text` may run. Never raises. `force_live` (the visitor asked for Sach's own check anyway) is never free:
    it needs a budget slot like any live check and does not wait on another request."""
    flight, fmem = "", False
    try:
        rl = reply_lang if reply_lang in SUPPORTED else None
        if not force_live and _is_free(text, rl):
            return Admission("free")
        pm, pd = max_per_min(), max_per_day()
        if pm <= 0 and pd <= 0:
            return Admission("live")                             # no budget configured: the limiter does nothing, not even touch the store
        st = st or store.get_store()
        if flight_enabled() and not force_live:
            fk = _flight_key(text, rl)
            n, from_store = _incr(st, fk, FLIGHT_TTL_S)
            if n > 1:
                _release_flight(st, fk, not from_store)          # a follower holds no place while it waits
                return _await_answer(text, rl, st, fk)           # someone is already checking this exact claim
            flight, fmem = fk, not from_store
        now = time.time() if now is None else now
        (km, wait_m), (kd, wait_d) = _windows(now)
        nm = _incr(st, km, 120)[0] if pm > 0 else 0
        nd = _incr(st, kd, 2 * 86400)[0] if pd > 0 else 0
        if pm > 0 and nm > pm:
            _give_back(st, km if pm > 0 else None, kd if pd > 0 else None)
            _release_flight(st, flight, fmem) if flight else None
            _count_busy(st, now)
            return Admission("busy", "minute", max(wait_m, 5))
        if pd > 0 and nd > pd:
            _give_back(st, km if pm > 0 else None, kd)
            _release_flight(st, flight, fmem) if flight else None
            _count_busy(st, now)
            return Admission("busy", "day", min(wait_d, 3600))
        return Admission("live", keys=[k for k, on in ((km, pm > 0), (kd, pd > 0)) if on], flight=flight, flight_mem=fmem)
    except Exception:
        return Admission("live", flight=flight, flight_mem=fmem)          # never block a check because the limiter itself broke

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
        if not (res.get("cached") or res.get("matched") or res.get("layer") == "match"):   # repeats and published fact-checks cost no AI/search
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

FLIGHT_TITLE = "This message is being checked right now"

def busy_title(reason: str = "minute") -> str:
    return FLIGHT_TITLE if reason == "flight" else BUSY_TITLE

def related_pages(text: str, n: int = 3) -> list:
    """Up to n PIB releases from the LOCAL indexes that mention things related to the claim (title and link only; no network, no AI). Show-only: a
    reference for the reader, never a verdict. Same word-coverage gates as retrieval."""
    try:
        from . import index as pib_index, pibfts
        texts, _ = _claims_and_lang(text)
        hits = []
        for t in texts[:2]:
            hits += list(pib_index.search(t, top_n=n))
            if pibfts.enabled():
                hits += pibfts.search(t, top_n=n)
        out, seen = [], set()
        for h in sorted(hits, key=lambda h: -h.get("score", 0)):
            prid = str(h.get("prid") or "")
            if prid.isdigit() and prid not in seen:
                seen.add(prid)
                out.append({"title": " ".join(str(h.get("title") or "").split())[:160], "url": f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}"})
        return out[:n]
    except Exception:
        return []

def busy_message(reason: str = "minute") -> str:
    if reason == "flight":
        return ("Someone asked about this same message a moment ago, so Sach is already checking it and we do not give a second, duplicate check. "
                "Please try again in about 20 seconds: the answer should then be ready. We have not given a verdict yet.")
    when = "in a few minutes" if reason != "day" else "in a few hours (our free daily capacity is used up)"
    return ("Sach is very busy right now, so we have not checked this message and we are not giving a verdict. "
            f"Please try again {when}. Messages Sach has already checked are still answered instantly. "
            "To check something now, you can send it to PIB Fact Check yourself.")

def busy_result(reason: str = "minute", retry_after: int = 60, text: str = "") -> dict:
    """JSON body for the API. There is deliberately NO 'verdict' key: nothing was checked."""
    out = {"busy": True, "checked": False, "reason": reason, "retry_after_s": int(retry_after), "title": busy_title(reason),
           "message": busy_message(reason),
           "links": {"pib_fact_check_portal": PIB_PORTAL, "pib_fact_check_whatsapp": PIB_WHATSAPP}}
    rel = related_pages(text) if text and reason != "flight" else []
    if rel:
        out["related_official_pages"] = rel
        out["related_note"] = "These PIB releases mention things related to your message. This is not a verdict."
    return out

def busy_block(reason: str = "minute", text: str = "") -> str:
    from .site import esc
    rel = related_pages(text) if text and reason != "flight" else []
    related = ""
    if rel:
        related = ('<p style="margin:10px 0 4px"><b>Official pages that mention related things (not a verdict):</b></p><ul style="margin:0;padding-left:18px">'
                   + "".join(f'<li><a href="{esc(r["url"])}" rel="noopener" target="_blank">{esc(r["title"])}</a></li>' for r in rel) + "</ul>")
    return ('<div class="honest" style="margin-top:18px" role="status" id="busy-notice"><b>%s.</b> %s '
            '<a href="%s" rel="noopener">PIB Fact Check portal</a> &middot; <a href="%s" rel="noopener">PIB Fact Check on WhatsApp (+91 87997 11259)</a>%s</div>'
            % (esc(busy_title(reason)), esc(busy_message(reason)), PIB_PORTAL, PIB_WHATSAPP, related))

def busy_text(reason: str = "minute", text: str = "") -> str:
    """Plain text for the Telegram bot. With `text`, up to three related PIB pages from the local indexes are listed (titles and links, never a
    verdict), the same as on the website. A 'being checked right now' reply lists no pages."""
    rel = related_pages(text) if text and reason != "flight" else []
    pages = "".join(f"\n- {p['title']}: {p['url']}" for p in rel)
    return (f"{busy_title(reason)}.\n{busy_message(reason)}" + (f"\nOfficial pages that may be related (not a verdict):{pages}" if pages else "")
            + f"\nPIB Fact Check: {PIB_PORTAL} or WhatsApp +91 87997 11259 ({PIB_WHATSAPP})")[:4000]      # Telegram's limit is 4096
