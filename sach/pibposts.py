"""Verified debunks that PIB Fact Check published as posts on X (data/pib_posts.jsonl), for the MATCH layer.

Why: most of PIB Fact Check's well-known debunks (free laptop scheme, free recharge, fake RBI/bank messages, fake notices) exist ONLY as posts,
never as pib.gov.in press releases, so the press-release index (data/pib_index.jsonl) cannot see them.

Who calls this: sach/match.py (`load_pib_records` appends `load()` output) and scripts/add_pib_posts.py (ingest: `extract_claim`,
`judge`, `to_ist_date`). Pure stdlib, no network here; the only network call is in the ingest script (fxtwitter reader, polite).

Record (one JSON object per line):
  id        status id (string of digits)
  url       canonical public URL https://x.com/PIBFactCheck/status/<id>  (what we cite and link; never the fxtwitter URL)
  date      the post date as an IST calendar date (ISO)
  text      the post text, verbatim, minus a trailing link/tracking only
  claim     what the post says is circulating, in PIB's own words (framing like "A WhatsApp message is circulating claiming" removed)
  verdict   "FALSE" (post says fake/false/not announced/baseless) or "MISLEADING" (post says misleading and nothing stronger)
  fetched   ISO date the post was fetched
  kind      "post"   (never a pib.gov.in press release)
Nothing here is ever typed by hand: scripts/add_pib_posts.py writes every record from a fetched post.
"""
from __future__ import annotations
import json, os, re, unicodedata
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_PATH = os.path.join(ROOT, "data", "pib_posts.jsonl")
AUTHOR = "PIBFactCheck"
URL_RE = re.compile(r"^https://x\.com/PIBFactCheck/status/(\d{15,20})$")
TG_CHANNEL = "PIB_FactCheck"                                    # PIB Fact Check's public Telegram channel
TG_URL_RE = re.compile(r"^https://t\.me/PIB_FactCheck/(\d{1,9})$")
IST = timezone(timedelta(hours=5, minutes=30), "IST")
VERDICTS = ("FALSE", "MISLEADING")

_cache: dict = {"key": None, "rows": []}

# ------------------------------------------------------------------------------------------------ judging a fetched post
_HASHTAG = re.compile(r"#PIBFactCheck\b", re.I)
_STRONG = re.compile(r"\b(fake|false|falsely|not\s+announced|baseless|fabricated|fraudulent)\b", re.I)
_MISLEAD = re.compile(r"\bmisleading\b", re.I)
_CONFIRMS_TRUE = re.compile(r"\b(claim|message|news|post|document|letter)\s+is\s+(true|genuine|authentic|correct|real)\b|"
                            r"\b(partly|partially|half)\s+(true|false|correct)\b|\bmostly\s+(true|false)\b|\bgenuine\b|\bis\s+authentic\b|"
                            r"\b(is|are)\s+(indeed\s+)?true\b|✅\s*(this\s+)?(claim\s+is\s+)?(true|genuine|correct)\b", re.I)
_MEDIA_ONLY = re.compile(r"\b(video|image|photo|photograph|clip|picture|screenshot|reel)\b", re.I)
_VERDICT_TAGS = re.compile(r"#(?:fake|false|misleading|fraud|scam)\w*\s*", re.I)
_QUESTION_LEAD = re.compile(r"^(?:did|have)\s+you\s+(?:also\s+)?(?:receive[d]?|come\s+across|seen|got)\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,3}?"
                            r"(?:forward|message|sms|email|e-mail|voicemail|text)\b\s*(?:,\s*allegedly\s+from\s+[^,]+,)?\s*"
                            r"(?:(?:claiming|stating|saying)(?:\s+that)?\s+)?", re.I)
_SOURCE_LEAD = re.compile(r"^(?:an?\s+|the\s+)?(?:\w+\s+){0,3}?(?:message|post|forward|video|sms|email|news\s+(?:report|article)|report|article|tweet)\s+"
                          r"(?:with\s+a\s+link\s+)?(?:(?:is|are)\s+)?"
                          r"(?:claims?|claiming|stating|states|says|saying)\s+(?:that\s+)?", re.I)
_CIRCULATING = re.compile(r"\s*,?\s*\b(?:(?:is|are|was|were)\s+)?(?:(?:being|been|has\s+been|have\s+been)\s+)?"
                          r"(?:circulat(?:ed|ing|es?)|going\s+around|doing\s+the\s+rounds|going\s+viral|shared|forwarded|spreading)\b"
                          r"(?:\s+(?:on|in|across|via|through)\s+(?:whatsapp|social\s+media|messaging\s+platforms|the\s+internet|online)"
                          r"(?:\s+and\s+(?:other\s+)?(?:social\s+media|messaging\s+platforms|platforms))?)?\s*,?"
                          r"(?=\s*(?:$|[.,]|(?:with|claim\w*|stating|saying|that)\b))", re.I)
_PUNCT_ONLY = "\ufe0f\u200d"
_MAX_CLAIM_CHARS = 420


def to_ist_date(created_at: str = "", timestamp=None) -> str:
    """ISO date of the post in IST. `timestamp` (unix seconds) wins; otherwise parse 'Mon Apr 27 11:12:03 +0000 2026'. '' if unparseable."""
    try:
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            return datetime.fromtimestamp(float(timestamp), timezone.utc).astimezone(IST).date().isoformat()
        dt = datetime.strptime(str(created_at).strip(), "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(IST).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return ""


def strip_trailing_links(text: str) -> str:
    """Only trailing t.co / pic.x.com / tracking links come off the post text; the wording itself is never edited."""
    t = str(text or "").rstrip()
    while True:
        n = re.sub(r"(?:\s+|^)(?:https?://\S+|pic\.(?:x|twitter)\.com/\S+)\s*$", "", t)
        if n == t:
            return t.strip()
        t = n.rstrip()


def _plain(s: str) -> str:
    """Drop links, verdict hashtags (#fake), emoji/symbols; keep the word of any other hashtag or @mention (without the sign) so the
    sentence still reads whole ('advisory by @UNICEF' -> 'advisory by UNICEF'). Letters (incl. Indic), digits and punctuation stay."""
    s = re.sub(r"https?://\S+|pic\.(?:x|twitter)\.com/\S+", " ", s)
    s = _VERDICT_TAGS.sub("", s)
    s = re.sub(r"[@#](?=\w)", "", s)
    s = s.translate({0x2049: "?", 0x2753: "?", 0x2754: "?", 0x203C: "!", 0x2757: "!", 0x2755: "!"})
    s = "".join(" " if unicodedata.category(c).startswith("S") or c in _PUNCT_ONLY else c for c in s)
    s = re.sub(r"[₹]", "", s)
    return re.sub(r"[ \t]+", " ", s)


def _is_header(sent: str) -> bool:
    """A short exclamation ('Scam Alert!', 'Beware of False Claims!', 'Do not fall for fake videos!') is a banner, not the claim."""
    t = sent.strip()
    return t.endswith("!") and len(re.findall(r"\w+", t)) <= 7


def extract_claim(text: str) -> str:
    """The claim a PIB post says is circulating: the text BEFORE the '#PIBFactCheck' marker, cleaned of emoji/links, with banners
    ('Scam Alert!'), a short rhetorical headline ('Free laptops for students?'), and the circulation framing ('A WhatsApp message is
    circulating claiming that', 'Did you receive a forward claiming that') removed. PIB's own words, nothing added.
    Returns '' when nothing concrete is left."""
    m = _HASHTAG.search(text or "")
    head = (text or "")[:m.start()] if m else ""
    paras = [re.sub(r"\s+", " ", p).strip(" -–—:•*") for p in re.split(r"\n\s*\n", _plain(head))]
    paras = [re.sub(r"^(?:claim\s*\d*\s*:\s*|[?!.,;:]+\s*)", "", p, flags=re.I) for p in paras if p]
    paras = [p for p in paras if p]
    if len(paras) > 1 and len(re.findall(r"\w+", paras[0])) <= 5 and paras[0].rstrip().endswith(("?", "!")):
        paras = paras[1:]                                     # short headline question / banner above the real sentence
    out = []
    for p in paras:
        sents = [x for x in re.split(r"(?<=[.!?])\s+", p) if x.strip()]
        sents = [x for x in sents if not _is_header(x)] or sents
        if sents:
            sents[0] = _QUESTION_LEAD.sub("", sents[0], count=1)
            sents[0] = _CIRCULATING.sub(" ", sents[0], count=1)
            sents[0] = _SOURCE_LEAD.sub("", sents[0].strip(), count=1)
        out.append(" ".join(sents))
    claim = re.sub(r"\s+", " ", " ".join(out)).strip(" -–—:,")
    claim = re.sub(r"\s+([,.?!])", r"\1", claim).rstrip("?").strip()
    if len(claim) > _MAX_CLAIM_CHARS:
        cut = claim[:_MAX_CLAIM_CHARS]
        claim = cut[:cut.rfind(" ")].rstrip(",;:-") if " " in cut else cut
    return claim


FAMILY_MAX = 3


def family_key(claim: str) -> str:
    """Normalised claim with every number masked: the 30 'Mudra loan approval letter' posts differ only in amounts and are one family."""
    t = re.sub(r"\d[\d,]*(?:\.\d+)?", "#", str(claim).lower())
    return re.sub(r"[^\w#]+", " ", t).strip()


_VERDICTISH = re.compile(r"\b(fake|false|falsely|fraud\w*|scam\w*|beware|fabricated|misleading|NOT|propaganda\s+alert)\b", re.I)
_BAD_START = re.compile(r"^(?:to|asking|urging|with|and|or|but|of|for|by|on|in|at)\b", re.I)


def _nums(t: str) -> set:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}


def garbled(claim: str, text: str) -> str:
    """'' when the extracted claim reads whole, else why not. A fragment, a claim that still carries PIB's verdict wording, a multi-claim
    thread, or a claim that lost a number present in the post's claim paragraph is dropped (quality over count)."""
    if not claim or not claim[0].isalpha() or _BAD_START.match(claim):
        return "extracted claim is a fragment"
    if _VERDICTISH.search(claim):
        return "extracted claim carries verdict wording (not a clean claim)"
    if re.search(r"point-by-point|claim\s*\d", claim, re.I):
        return "post makes several claims point by point"
    if re.search(r"\s[,.;:]|\b(\w+) \1\b|'\s+\w+\s+is\b", claim):
        return "extracted claim has a gap or stutter"
    m = _HASHTAG.search(text or "")
    before = _plain((text or "")[:m.start()]) if m else ""
    if _nums(before) - _nums(claim):
        return "extracted claim lost a number from the post"
    return ""


def judge(tweet: dict) -> tuple[dict | None, str]:
    """-> (record fields, '') for an acceptable debunk post, or (None, reason). `tweet` is fxtwitter's `tweet` object.
    Accept only: author exactly PIBFactCheck; #PIBFactCheck plus FAKE/FALSE/MISLEADING/'not announced'/'baseless'; not a reply to or quote of
    someone else's post; not a TRUE/partly-true confirmation; a concrete text claim (not video/image only)."""
    if not isinstance(tweet, dict):
        return None, "no tweet object"
    author = (tweet.get("author") or {}).get("screen_name")
    if author != AUTHOR:
        return None, f"author is {author!r}, not {AUTHOR!r}"
    tid = str(tweet.get("id") or "")
    if not re.fullmatch(r"\d{15,20}", tid):
        return None, "bad status id"
    if tweet.get("replying_to") or tweet.get("replying_to_status"):
        return None, "is a reply (not a stand-alone debunk)"
    q = tweet.get("quote")
    if q and (q.get("author") or {}).get("screen_name") != AUTHOR:
        return None, "quotes someone else's post (ambiguous whose claim is judged)"
    if tweet.get("reposted_by") or tweet.get("is_repost"):
        return None, "is a repost"
    raw = str(tweet.get("text") or "")
    text = strip_trailing_links(raw)
    if not _HASHTAG.search(text):
        return None, "no #PIBFactCheck marker"
    strong, mislead = bool(_STRONG.search(text)), bool(_MISLEAD.search(text))
    if not (strong or mislead):
        return None, "no debunk marker (FAKE/FALSE/MISLEADING/not announced/baseless)"
    if _CONFIRMS_TRUE.search(text):
        return None, "ambiguous or confirms the claim (true / partly true / genuine)"
    claim = extract_claim(text)
    if _MEDIA_ONLY.search(claim):
        return None, "claim is about a video/image, not a text claim"
    why = garbled(claim, text)
    if why:
        return None, why
    words = re.findall(r"[A-Za-zऀ-෿0-9]+", claim)
    if len(words) < 6:
        return None, f"no concrete text claim (extracted {len(words)} words)"
    d = to_ist_date(tweet.get("created_at", ""), tweet.get("created_timestamp"))
    if not d:
        return None, "post date unreadable"
    if date.fromisoformat(d) > datetime.now(IST).date():
        return None, "post date is in the future"
    return {"id": tid, "url": f"https://x.com/{AUTHOR}/status/{tid}", "date": d, "text": text, "claim": claim,
            "verdict": "FALSE" if strong else "MISLEADING", "kind": "post"}, ""


_MEDIA_ONLY_INDIC = re.compile(r"वीडियो|फोटो|तस्वीर|क्लिप|वायरल\s+वीडियो|వీడియో|ఫోటో|చిత్రం|ভিডিও|ছবি|வீடியோ|புகைப்படம்|વિડિઓ|ફોટો")   # Hindi, Telugu, Bengali, Tamil, Gujarati


def judge_telegram(post_id, text: str, date_iso: str) -> tuple[dict | None, str]:
    """The same acceptance rules as `judge`, for a post on PIB Fact Check's own Telegram channel (https://t.me/PIB_FactCheck/<id>).
    -> (record fields incl. source='telegram', '') or (None, reason). Pure: the caller fetched and parsed the page."""
    pid = str(post_id or "")
    if not re.fullmatch(r"\d{1,9}", pid):
        return None, "bad Telegram post id"
    t = strip_trailing_links(str(text or ""))
    if not _HASHTAG.search(t):
        return None, "no #PIBFactCheck marker"
    strong, mislead = bool(_STRONG.search(t)), bool(_MISLEAD.search(t))
    if not (strong or mislead):
        return None, "no debunk marker (FAKE/FALSE/MISLEADING/not announced/baseless)"
    if _CONFIRMS_TRUE.search(t):
        return None, "ambiguous or confirms the claim (true / partly true / genuine)"
    claim = extract_claim(t)
    if _MEDIA_ONLY.search(claim) or _MEDIA_ONLY_INDIC.search(claim):
        return None, "claim is about a video/image, not a text claim"
    why = garbled(claim, t)
    if why:
        return None, why
    if len(re.findall(r"[A-Za-z\u0900-\u0dff0-9]+", claim)) < 6:
        return None, "no concrete text claim"
    try:
        d = date.fromisoformat(str(date_iso))
    except ValueError:
        return None, "post date unreadable"
    if d > datetime.now(IST).date():
        return None, "post date is in the future"
    return {"id": pid, "url": f"https://t.me/{TG_CHANNEL}/{pid}", "date": d.isoformat(), "text": t, "claim": claim,
            "verdict": "FALSE" if strong else "MISLEADING", "kind": "post", "source": "telegram"}, ""


# ------------------------------------------------------------------------------------------------ loading
def valid(r: dict) -> bool:
    """A stored record is usable only with every field in shape: canonical x.com URL whose id equals `id`, a date, a claim, a verdict."""
    try:
        m = (TG_URL_RE if r.get("source") == "telegram" else URL_RE).match(str(r.get("url") or ""))
        return bool(m and m.group(1) == str(r.get("id")) and r.get("kind") == "post" and r.get("verdict") in VERDICTS
                    and str(r.get("claim") or "").strip() and str(r.get("text") or "").strip()
                    and date.fromisoformat(str(r.get("date"))))
    except (ValueError, TypeError):
        return False


def load(path: str | None = None) -> list[dict]:
    """Valid, de-duplicated post records. A missing file, corrupt line or malformed record is skipped, never fatal."""
    path = path or POSTS_PATH
    if not os.path.exists(path):
        return []
    key = (path, os.path.getmtime(path))
    if _cache["key"] != key:
        rows, seen = [], set()
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and valid(r) and r["id"] not in seen:
                seen.add(r["id"])
                rows.append(r)
        _cache.update(key=key, rows=rows)
    return _cache["rows"]
