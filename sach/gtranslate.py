"""Google Cloud Translation (Basic, v2) as the FIRST-choice translator for non-English claims; the LLM translator is the fallback.

Who calls it: sach/match.py (run_match) and sach/pipeline.py (_check_claim) through `translate_claim`, and sach/pipeline.py
(check_forward) through `refine_language`; sach/status.py reads `usage`. Off unless GOOGLE_TRANSLATE_API_KEY is set: with no key every
function here returns "nothing" and the pipeline behaves exactly as before.

API facts, read from Google's own pages on 2026-11-13:
- Reference: https://docs.cloud.google.com/translate/docs/reference/rest/v2/translate
  `POST https://translation.googleapis.com/language/translate/v2`; `q` (string or array, up to 128 strings), `target`, optional
  `source` (omitted = auto-detect), `format` (`html` is the DEFAULT, `text` for plain text). Response
  `{"data": {"translations": [{"translatedText", "detectedSourceLanguage"}]}}`; `detectedSourceLanguage` is present only when
  `source` was not sent. The reference page lists q/target as parameters; the how-to page
  (https://docs.cloud.google.com/translate/docs/basic/translating-text) shows the same fields as a JSON request body, which is what we send.
- API key: https://docs.cloud.google.com/docs/authentication/api-keys-use says to send it in the `x-goog-api-key` HTTP header and
  warns that the `?key=` query parameter puts the key in the URL. We use the header only, so the key is never in a URL.
- Languages: https://docs.cloud.google.com/translate/docs/languages lists hi, bn, mr, te, ta, gu, ur, kn, or, ml, pa, as, ne, gom
  (Konkani), mni-Mtei (Meitei/Manipuri), mai (Maithili) in the NMT table, which is what Basic uses.
- Price: https://cloud.google.com/translate/pricing (read 2026-11-13): NMT text translation and language detection, first 500,000
  characters per month free ("applied as $10 credit every month"), then $20.00 per 1,000,000 characters. Basic's maximum request size is
  100K bytes (https://docs.cloud.google.com/translate/quotas); we send at most 1,000 characters.
NOT confirmed from the docs: that `format: "text"` output never contains HTML entities (the docs do not say), so the result is
html-unescaped defensively; and the exact HTTP status for an exhausted trial (assumed 403 or 429, both handled).

Why there is a spend guard: the owner's Google Cloud trial credit is finite and abuse must not burn it. Cache hits cost nothing and are
not counted. A daily character budget (SACH_TRANSLATE_MAX_CHARS_PER_DAY, default 150000, 0 = unlimited) and a per-minute budget
(SACH_TRANSLATE_MAX_CHARS_PER_MIN, default 20000, 0 = unlimited) are counted with `store.incr` on UTC-day / minute keys, the same pattern as
sach/limits.py, and fail open to an in-memory counter if the store errors. When a budget is gone, or Google answered 403/429
(trial over, quota), Google is skipped silently (a counter, not an error) and the LLM translator runs exactly as before.

Latin-script text (English, Hinglish, Tinglish) never goes to Google: its detector would say en or te and mangle romanised text, which the
LLM handles. Never raises; the key never appears in a log line, exception, URL or return value.
stdlib only."""
from __future__ import annotations
import hashlib, html, json, os, time
from collections import Counter
from urllib.request import Request, urlopen
from . import limits, store
from .lang import script_counts

ENDPOINT = "https://translation.googleapis.com/language/translate/v2"
TIMEOUT_S = 4
MAX_CHARS = 1000
MAX_BYTES = 200_000
CACHE_TTL_S = 7 * 86400
DEFAULT_MAX_CHARS_PER_DAY = 150_000
DEFAULT_MAX_CHARS_PER_MIN = 20_000
PAUSE_S = 300                      # after a 403/429 (trial over, quota) do not try again for this long

# Sach code -> Google code. Hindi and Bengali are deliberately NOT forced: our detector falls back to them when the shared script is
# ambiguous (Devanagari: Hindi/Marathi/Konkani/Nepali; Bengali script: Bengali/Assamese), so Google detects. Tinglish/English: not used.
GOOGLE_CODES = {"te": "te", "ta": "ta", "gu": "gu", "ur": "ur", "kn": "kn", "or": "or", "ml": "ml", "pa": "pa", "as": "as",
                "mr": "mr", "ne": "ne", "kok": "gom", "mni": "mni-Mtei"}

_paused_until = 0.0

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default

def key() -> str:
    return os.environ.get("GOOGLE_TRANSLATE_API_KEY", "").strip()

def enabled() -> bool:
    return bool(key())

def max_per_day() -> int:
    return _env_int("SACH_TRANSLATE_MAX_CHARS_PER_DAY", DEFAULT_MAX_CHARS_PER_DAY)

def max_per_min() -> int:
    return _env_int("SACH_TRANSLATE_MAX_CHARS_PER_MIN", DEFAULT_MAX_CHARS_PER_MIN)

def google_code(lang) -> str | None:
    return GOOGLE_CODES.get(lang or "")

def reset() -> None:
    global _paused_until
    _paused_until = 0.0

def is_latin_script(text: str) -> bool:
    """True unless letters in an Indian script or Perso-Arabic outnumber ASCII/Latin letters."""
    indian = sum(script_counts(text or "").values())
    latin = sum(1 for ch in (text or "") if ch.isascii() and ch.isalpha())
    return indian == 0 or latin >= indian

# ---------------------------------------------------------------- the raw API call
def translate(text: str, source: str | None = None, opener=urlopen) -> dict | None:
    """-> {"text": english, "detected": google_code_or_None}, or None on any problem. `source` is a GOOGLE code (None = auto-detect).
    Does no caching and no budgeting: translate_claim does both."""
    global _paused_until
    try:
        k = key()
        if not k or not isinstance(text, str):
            return None
        q = text.strip()[:MAX_CHARS]
        if not q or is_latin_script(q):
            return None
        body = {"q": [q], "target": "en", "format": "text"}
        if source:
            body["source"] = source
        req = Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": k})
        with opener(req, timeout=TIMEOUT_S) as r:
            status = getattr(r, "status", 200)
            if status in (403, 429):
                _paused_until = time.time() + PAUSE_S
                return None
            if status != 200:
                return None
            data = json.loads(r.read(MAX_BYTES).decode("utf-8", "replace"))
        tr = data["data"]["translations"][0]
        out = html.unescape(str(tr["translatedText"])).strip()
        if not out:
            return None
        det = tr.get("detectedSourceLanguage")
        return {"text": out, "detected": str(det).strip() if det else None}
    except Exception as e:
        try:
            if getattr(e, "code", None) in (403, 429):     # urllib raises HTTPError for non-2xx
                _paused_until = time.time() + PAUSE_S
        except Exception:
            pass
        return None                       # no message kept: urllib errors can carry request details

# ---------------------------------------------------------------- cache + spend guard
def _cache_key(text: str, lang) -> str:
    return "gt:" + hashlib.sha256(("%s\x00%s" % (text, lang or "")).encode("utf-8")).hexdigest()

def _windows(now: float):
    return ("gt:m:%d" % int(now // 60), 120), ("gt:d:%d" % int(now // 86400), 2 * 86400)

def _reserve(n: int, st, now: float) -> bool:
    """Reserve n characters in the minute and day budgets. False (and nothing kept) when either is exhausted."""
    pm, pd = max_per_min(), max_per_day()
    (km, ttm), (kd, ttd) = _windows(now)
    taken = []
    for k, ttl, cap in ((km, ttm, pm), (kd, ttd, pd)):
        if cap <= 0:
            continue
        cnt, _ = limits._incr(st, k, ttl, n)
        taken.append(k)
        if cnt > cap:
            for t in taken:
                _give_back(st, t, n)
            return False
    return True

def _give_back(st, k: str, n: int) -> None:
    try:
        if getattr(st, "remote", False):
            st.incr(k, -n)
        else:
            limits._mem_incr(k, -n)
    except Exception:
        pass

def _note(st, name: str, now: float) -> None:
    try:
        limits._incr(st, "gt:%s:%d" % (name, int(now // 86400)), 2 * 86400)
    except Exception:
        pass

def translate_claim(text: str, lang: str, llm=None, opener=urlopen, st=None, now=None) -> dict:
    """The one translation entry point for a non-English claim. -> {"text", "translator": "google"|"llm"|"none", "detected": code|None}.
    Google first (cache, then budget, then the API); on anything but a Google answer the LLM runs exactly as it did before. Never raises
    (an LLM exception becomes translator "none" with empty text)."""
    res = None
    try:
        res = _google(text, lang, opener, st, now)
    except Exception:
        res = None
    if res:
        return {"text": res["text"], "translator": "google", "detected": res.get("detected")}
    if llm is not None and hasattr(llm, "translate"):
        try:
            t = (llm.translate(text) or "").strip()
        except Exception:
            t = ""
        if t:
            return {"text": t, "translator": "llm", "detected": None}
    return {"text": "", "translator": "none", "detected": None}

def _google(text: str, lang, opener, st, now):
    if not enabled() or not isinstance(text, str) or not text.strip():
        return None
    q = text.strip()[:MAX_CHARS]
    if is_latin_script(q) or lang in (None, "en", "tl"):
        return None
    now = time.time() if now is None else now
    try:
        st = st or store.get_store()
    except Exception:
        st = None
    ck = _cache_key(q, lang)
    try:
        hit = st.get(ck) if st is not None else None
        if isinstance(hit, dict) and hit.get("t"):
            return {"text": str(hit["t"]), "detected": hit.get("d")}        # a repeat costs nothing and is not counted
    except Exception:
        pass
    if now < _paused_until:
        return None
    try:
        reserved = _reserve(len(q), st, now) if st is not None else True
    except Exception:
        reserved = True                                                      # a broken counter never blocks translation
    if not reserved:
        if st is not None:
            _note(st, "skipped", now)                                        # a counter, not an error
        return None
    r = translate(q, google_code(lang), opener)
    if not r:
        if st is not None:
            (km, _), (kd, _) = _windows(now)
            for k, cap in ((km, max_per_min()), (kd, max_per_day())):
                if cap > 0:
                    _give_back(st, k, len(q))                                # a failed call is not billed: give the characters back
        return None
    try:
        st.set(ck, {"t": r["text"], "d": r["detected"]}, CACHE_TTL_S)
    except Exception:
        pass
    return r

def usage(st=None, now=None) -> dict:
    """For the status page. Reads only; never any key material."""
    now = time.time() if now is None else now
    out = {"configured": enabled(), "chars_today": 0, "max_chars_per_day": max_per_day(), "skipped_over_budget_today": 0}
    try:
        st = st or store.get_store()
        kd = _windows(now)[1][0]
        ks = "gt:skipped:%d" % int(now // 86400)
        c = st.counters([kd, ks]) if getattr(st, "remote", False) else {}
        with limits._mem_lock:
            mem = dict(limits._mem)
        out["chars_today"] = max(int(c.get(kd, 0) or 0), int(mem.get(kd, 0)), 0)
        out["skipped_over_budget_today"] = max(int(c.get(ks, 0) or 0), int(mem.get(ks, 0)), 0)
    except Exception:
        pass
    return out

# ---------------------------------------------------------------- conservative language refinement
def _script_share(text: str, name: str) -> bool:
    c = script_counts(text or "")
    return bool(c) and max(c, key=c.get) == name and c[name] > 5

def refine_language(ours: str, detected, text: str) -> str:
    """Only two upgrades, only when the script agrees: Devanagari text our detector left as Hindi, and Google says Marathi, Nepali or
    Konkani; Bengali-script text our detector left as Bengali, and Google says Assamese. Anything else returns `ours` unchanged."""
    try:
        d = str(detected or "").strip().lower()
        if ours == "hi" and d in ("mr", "ne", "gom") and _script_share(text, "deva"):
            return "kok" if d == "gom" else d
        if ours == "bn" and d == "as" and _script_share(text, "bn"):
            return "as"
    except Exception:
        pass
    return ours

def consensus_detected(infos) -> str | None:
    """The most common Google-detected language over a forward's claims (None when no claim has one)."""
    c = Counter(i.get("detected") for i in infos if i and i.get("detected"))
    return c.most_common(1)[0][0] if c else None
