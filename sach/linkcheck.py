"""LINKCHECK: check a link, phone number, UPI ID or app before you trust it.

Who calls this: sach/web.py (GET /?view=link, POST /?api=linkcheck, POST /?api=linkexpand) and sach/site.py (the home-page card,
the compact "Links and numbers in this message" panel under a fact-check result, CSS and JS).
Nothing existing serves the purpose: sach/scamsigns.py flags patterns in a whole forward, but does not say, per item, whether an
address is official, imitates an official one, or simply cannot be vouched for.
Data read: data/official_brands.json (verified official domains and numbers, each with an evidence URL). Data written: only a small
cache of RDAP registration dates (sach/store.py, 7 days, keyed by registrable domain; never the pasted text).

What it claims, and what it never claims
  * OFFICIAL: the host is on Sach's verified official list (sach.fetch.is_official or data/official_brands.json).
  * LOOKALIKE: a concrete, explainable rule fired (listed in docs/link-checker.md). Never a guess.
  * SUSPICIOUS_PATTERN: a recognisable scam pattern (shortener, .apk, odd domain ending with money or government words, ...).
  * UNKNOWN: everything else. Sach never says an address is safe: it says it cannot vouch for it and how to verify.
No AI/LLM calls. No fetching of user-supplied pages: lookups use the HOSTNAME only (RDAP registration data, optional Google Safe
Browsing), and the one guarded exception is shortener redirect expansion (expand_short_link), which only ever contacts hosts on the
shortener list.

UPI handles: NPCI's public pages (https://www.npci.org.in/product/upi/all-members and the BHIM UPI guidelines of June 2026,
https://www.npci.org.in/uploads/BHIM_UPI_Guidelines_2026_012a0b1bce.pdf) were checked on 2026-11-13. They list live members and
describe a UPI ID as "name@handle", but publish no handle-to-bank table that could be read there. So Sach shows a handle exactly as
written and says that it does not map handles to banks (KNOWN_HANDLES is empty on purpose; add an entry only with an NPCI/bank
evidence URL, see docs/link-checker.md).

Safe Browsing: Lookup API v4 threatMatches:find, https://developers.google.com/safe-browsing/v4/lookup-api (checked 2026-11-13).
Google's overview (https://developers.google.com/safe-browsing) says the Safe Browsing API is for non-commercial use only.
"""
from __future__ import annotations
import concurrent.futures, html, http.client, ipaddress, json, os, re, socket, ssl, time, unicodedata
import urllib.error, urllib.request
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urljoin, urlsplit

from . import scamsigns, store, timefmt
from .fetch import EXTRA_OFFICIAL, OFFICIAL_HOSTS, OFFICIAL_SUFFIXES, OFFICIAL_ZONES, is_official
from .i18n import tr
from .lang import to_ascii_digits
from .siteurl import site_url

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "official_brands.json")
MAX_INPUT = 4000
MAX_ITEMS = 20
MAX_RAW = 120
PANEL_MAX = 5
RDAP_BUDGET = 5                 # at most this many hostnames get online lookups per request
RDAP_TIMEOUT = 3.0
RDAP_TTL = 7 * 24 * 3600
YOUNG_DAYS, RECENT_DAYS = 30, 180

OFFICIAL, LOOKALIKE, PATTERN, UNKNOWN = "OFFICIAL", "LOOKALIKE", "SUSPICIOUS_PATTERN", "UNKNOWN"
CSS_CLASS = {OFFICIAL: "lc-official", LOOKALIKE: "lc-lookalike", PATTERN: "lc-pattern", UNKNOWN: "lc-unknown"}
GLYPH = {OFFICIAL: "✓", LOOKALIKE: "✕", PATTERN: "!", UNKNOWN: "?"}      # shape as well as colour
RANK = {LOOKALIKE: 0, PATTERN: 1, UNKNOWN: 2, OFFICIAL: 3}

# ---------------------------------------------------------------------------------------------------------------- text
# NOT NATIVE-REVIEWED (hi, te): short strings awaiting a native-speaker pass. English is the fallback for every other language.
TEXT = {
    "en": {
        OFFICIAL: "On the verified official list", LOOKALIKE: "Imitates {brand}", PATTERN: "Looks like a scam pattern",
        UNKNOWN: "Not on the official list: Sach cannot vouch for it",
        "what_to_do": "What to do", "real_address": "The real address is", "warn": "Warn my group on WhatsApp",
        "expand": "Show where this short link goes", "title": "Check a link, number or UPI ID",
        "check": "Check", "checking": "Checking…", "placeholder": "Paste a link, phone number, UPI ID, app name or the whole message",
        "intro": "Sach tells you whether an address is on its verified official list, imitates one, or is something it cannot vouch for. It only says what it can prove, and how to check the rest.",
        "none": "No link, phone number, UPI ID or app was found in that text.",
        "panel": "Links and numbers in this message", "panel_hint": "Paste the message in the link checker for the full check.",
        "high": "high risk", "more": "and {n} more", "empty": "Please paste something to check.",
        "found": "{n} found", "expanding": "Looking up where it goes…", "expand_fail": "Could not find out where this link goes. Treat it with caution.",
        "goes_to": "This short link goes to",
    },
    "hi": {
        OFFICIAL: "सत्यापित आधिकारिक सूची में है", LOOKALIKE: "{brand} की नकल करता है", PATTERN: "ठगी के पैटर्न जैसा दिखता है",
        UNKNOWN: "आधिकारिक सूची में नहीं है: Sach इसकी गारंटी नहीं दे सकता",
        "what_to_do": "क्या करें", "real_address": "असली पता है", "warn": "WhatsApp पर अपने ग्रुप को चेताएँ",
        "expand": "दिखाएँ कि यह छोटा लिंक कहाँ जाता है", "title": "लिंक, नंबर या UPI ID जाँचें",
        "check": "जाँचें", "checking": "जाँच रहे हैं…", "placeholder": "लिंक, फ़ोन नंबर, UPI ID, ऐप का नाम या पूरा संदेश यहाँ चिपकाएँ",
        "panel": "इस संदेश में लिंक और नंबर",
    },
    "te": {
        OFFICIAL: "ధృవీకరించిన అధికారిక జాబితాలో ఉంది", LOOKALIKE: "{brand}ను అనుకరిస్తోంది", PATTERN: "మోసం పద్ధతిలా కనిపిస్తోంది",
        UNKNOWN: "అధికారిక జాబితాలో లేదు: Sach హామీ ఇవ్వలేదు",
        "what_to_do": "ఏం చేయాలి", "real_address": "అసలు అడ్రస్", "warn": "WhatsApp లో మీ గ్రూప్‌ను హెచ్చరించండి",
        "expand": "ఈ చిన్న లింక్ ఎక్కడికి వెళ్తుందో చూపించు", "title": "లింక్, నంబర్ లేదా UPI ID తనిఖీ చేయండి",
        "check": "తనిఖీ", "checking": "తనిఖీ చేస్తున్నాం…", "placeholder": "లింక్, ఫోన్ నంబర్, UPI ID, యాప్ పేరు లేదా మొత్తం సందేశాన్ని ఇక్కడ పేస్ట్ చేయండి",
        "panel": "ఈ సందేశంలో లింక్‌లు, నంబర్లు",
    },
}


def t(key: str, lang: str = "en", **kw) -> str:
    s = tr(TEXT, lang).get(key) or TEXT["en"][key]
    return s.format(**kw) if kw else s


def ui_strings(lang: str = "en") -> dict:
    return {k: t(k, lang) for k in ("what_to_do", "real_address", "warn", "expand", "none", "expanding", "expand_fail", "goes_to", "checking", "check", "empty")}


HOW_TO_CHECK = [
    "Type the official address yourself in your browser, or use the app from the Google Play Store or Apple App Store. Do not tap the link.",
    "Official government sites end in .gov.in or .nic.in. Banks' official sites end in .bank.in, or are long-standing addresses listed on RBI's site (rbi.org.in).",
    "Never enter an OTP, PIN, card details or a password after tapping a link in a message.",
]
ACT_REPORT = "Report it: call 1930 for financial fraud, or use cybercrime.gov.in. Report suspicious messages and calls at sancharsaathi.gov.in (Chakshu)."
UPI_RULES = [
    "You never need to enter your UPI PIN, or accept a collect request, to RECEIVE money. A PIN is only for paying.",
    "Do not pay a \"processing fee\" or \"send Rs 1 to verify\" to get money or a prize.",
    "Before you pay anyone, check that the name your own UPI app shows matches who you expect.",
]

# ------------------------------------------------------------------------------------------------------------ data load
_DATA: dict | None = None


def load_data(path: str | None = None) -> dict:
    global _DATA
    if path is None and _DATA is not None:
        return _DATA
    try:
        with open(path or DATA_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {"brands": [], "phones": [], "reporting": []}
    if path is None:
        _DATA = d
    return d


_MULTI_SUFFIX = {"co.in", "org.in", "net.in", "gov.in", "nic.in", "ac.in", "edu.in", "res.in", "firm.in", "gen.in", "ind.in", "bank.in",
                 "co.uk", "org.uk", "com.au", "co.za", "com.br", "co.nz"}


def registrable(host: str) -> str:
    labels = [x for x in host.split(".") if x]
    if len(labels) >= 3 and ".".join(labels[-2:]) in _MULTI_SUFFIX:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _under(h: str, d: str) -> bool:
    return h == d or h.endswith("." + d)


_FETCH_NAMES = {"pib.gov.in": "PIB", "factcheck.pib.gov.in": "PIB Fact Check", "icmr.gov.in": "ICMR", "rbi.org.in": "RBI", "mygov.in": "MyGov",
                "npci.org.in": "NPCI", "sansad.in": "Parliament of India", "nta.ac.in": "NTA", "irctc.co.in": "IRCTC", "epfindia.gov.in": "EPFO",
                "licindia.in": "LIC", "sbi.co.in": "SBI", "onlinesbi.sbi": "SBI", "aiims.edu": "AIIMS", "pfrda.org.in": "PFRDA",
                "aicte-india.org": "AICTE", "rbiretaildirect.org.in": "RBI Retail Direct", "ugc.ac.in": "UGC", "jansuraksha.in": "Jan Suraksha"}


class _Index:
    """Brands, their official domains and the official labels, built once from the data file and sach/fetch.py."""

    def __init__(self, data: dict):
        self.brands: list[dict] = []
        self.by_domain: dict[str, dict] = {}
        self.body: dict[str, str] = {}                         # domain -> the exact company or body when it differs from the brand name
        for b in data.get("brands", []):
            doms = [d["d"].lower() for d in b.get("domains", []) if d.get("d")]
            if not doms:
                continue
            rec = {"brand": b["brand"], "short": b.get("short") or b["brand"], "tokens": [x.lower() for x in b.get("tokens", [])], "domains": doms,
                   "primary": doms[0], "kind": b.get("kind", "")}
            self.brands.append(rec)
            for d in doms:
                self.by_domain[d] = rec
            for dd in b.get("domains", []):
                if dd.get("body"):
                    self.body[dd["d"].lower()] = dd["body"]
        # bodies already on sach/fetch.py's list that are not in the brand file: they still count as official and as comparison targets
        for d in tuple(OFFICIAL_HOSTS) + tuple(EXTRA_OFFICIAL):
            if d not in self.by_domain:
                label = registrable(d).split(".")[0]
                rec = {"brand": _FETCH_NAMES.get(d, d), "short": _FETCH_NAMES.get(d, d), "tokens": [label] if len(label) >= 3 else [], "domains": [d], "primary": d, "kind": "government"}
                self.brands.append(rec)
                self.by_domain[d] = rec
        self.labels: dict[str, tuple[str, str]] = {}          # official registrable label -> (brand short name, official domain)
        for d, rec in self.by_domain.items():
            if registrable(d) == d:                            # skip e.g. pay.google.com: the label "google" is not Google Pay's
                self.labels.setdefault(d.split(".")[0], (rec["short"], d))

    def brand_for_host(self, host: str):
        return self.match_host(host)[0]

    def match_host(self, host: str):
        """(brand record, the official domain it matched) for an exact host or true subdomain, else (None, None)."""
        for d, rec in self.by_domain.items():
            if _under(host, d):
                return rec, d
        return None, None


_IDX: _Index | None = None


def index() -> _Index:
    global _IDX
    if _IDX is None:
        _IDX = _Index(load_data())
    return _IDX


def official_domains() -> list[str]:
    """Every domain in the verified brand data (the fetch.py suffixes and zones are covered by is_official itself)."""
    return sorted(index().by_domain)


# ------------------------------------------------------------------------------------------------------------- items
@dataclass
class Item:
    kind: str            # url | upi | phone | app
    raw: str             # as written (after removing hidden characters and un-defanging), at most MAX_RAW characters
    value: str           # normalised: URL as pasted, lower-case UPI ID, +91XXXXXXXXXX / 1800... / short code, app text
    pos: int
    flags: tuple = ()

    def to_dict(self) -> dict:
        return {"kind": self.kind, "raw": self.raw, "value": self.value, "pos": self.pos}


# hidden characters: zero-width, bidi controls, soft hyphen, BOM, word joiner, invisible operators
_HIDDEN = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿­͏᠎]")
_OBF = [
    (re.compile(r"\bhxxp(s?)(?=\s*(?:://|\[:\]|\[://\]))", re.I), r"http\1"),
    (re.compile(r"\bhttp(s?)\[:\]//", re.I), r"http\1://"),
    (re.compile(r"\[\s*://\s*\]|\(\s*://\s*\)", re.I), "://"),
    (re.compile(r"\[\s*\.\s*\]|\(\s*\.\s*\)|\{\s*\.\s*\}|\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}", re.I), "."),
    (re.compile(r"(?<=[A-Za-z0-9-]) ?\(\s*dot\s*\) ?(?=[A-Za-z0-9-])", re.I), "."),
    (re.compile(r"\[\s*@\s*\]|\(\s*at\s*\)|\[\s*at\s*\]", re.I), "@"),
]
SHORTENERS = ("bit.ly", "bitly.com", "tinyurl.com", "t.co", "cutt.ly", "rb.gy", "is.gd", "goo.gl", "ow.ly", "shorturl.at", "tiny.cc", "t.ly",
              "v.gd", "buff.ly", "rebrand.ly", "s.id", "lnkd.in", "bit.do")
_SHORT_ALT = "|".join(re.escape(x) for x in sorted(SHORTENERS, key=len, reverse=True))
_TLDS = tuple(dict.fromkeys(scamsigns._TLDS + ("net", "edu", "int", "ai", "pro", "name", "mobi", "cloud", "tech", "space", "pics", "wiki", "company",
                                               "cyou", "rest", "bond", "help", "support", "services", "loan", "finance", "money", "xyz", "in")))
_TLD_ALT = "|".join(sorted(_TLDS, key=len, reverse=True))
_END = "<>\"'`\\s।‘’“”"          # a URL stops at whitespace, quotes, angle brackets and the Hindi danda
_URL_RE = re.compile(
    rf"(?P<js>(?<!\w)(?:javascript|vbscript|data):[^{_END}]{{1,200}})"
    rf"|(?P<full>https?://[^{_END}]{{1,300}})"
    rf"|(?P<www>(?<![\w@./-])www\.[^{_END}]{{1,300}})"
    rf"|(?P<short>(?<![\w@./:-])(?:{_SHORT_ALT})/[A-Za-z0-9_-]{{1,60}}[^{_END}]{{0,100}})"
    rf"|(?P<bare>(?<![\w@./:-])(?:[^\W_][\w-]{{0,62}}\.){{1,6}}(?:{_TLD_ALT}|xn--[a-z0-9-]{{2,59}})(?![\w-])(?:[/:?#][^{_END}]{{0,200}})?)",
    re.I)
_UPI_RE = re.compile(r"(?<![\w.%+-])[A-Za-z0-9][A-Za-z0-9._-]{1,48}@[A-Za-z][A-Za-z0-9]{1,24}(?![\w@-]|\.[A-Za-z0-9])")
_EMAIL_RE = re.compile(r"(?<![\w.%+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9][A-Za-z0-9-]{0,62}(?:\.[A-Za-z0-9-]{1,63}){1,5}")
_MOBILE_RE = re.compile(r"(?<![\d+])(?:(?:\+|00)?91[\s-]{0,2}|0)?([6-9](?:[\s-]?\d){9})(?![\s-]?\d)")
_TOLL_RE = re.compile(r"(?<!\d)(1800|1860)((?:[\s-]?\d){6,7})(?![\s-]?\d)")
_SHORT_CTX = re.compile(r"\b(?:call|dial|helpline|help line|sms|toll[- ]?free)\b[^\d\n]{0,25}?(?<!\d)(\d{3,5})(?!\d)(?!\s*(?:rs\b|rupee|₹|%|lakh|crore|people|persons))", re.I)
_APK_FILE = re.compile(r"(?<![\w/.-])[\w][\w .-]{0,60}?\.apk\b", re.I)
_APK_WORDS = re.compile(r"\b(?:apk|app download|download (?:the |this |our )?app|install (?:the |this |our )?app)\b", re.I)
_TRAIL = ".,;:!?)]}>'\"।’”*"


def _clean_text(text) -> str:
    if not isinstance(text, str):
        return ""
    s = text[:MAX_INPUT]
    s = _HIDDEN.sub("", s)
    s = unicodedata.normalize("NFKC", s)
    s = to_ascii_digits(s)
    for rx, rep in _OBF:
        s = rx.sub(rep, s)
    return s


def _spans_overlap(a: tuple, taken: list) -> bool:
    return any(a[0] < e and s < a[1] for s, e in taken)


def extract_items(text) -> list[Item]:
    """Links, UPI IDs, phone numbers and app mentions in `text`, de-duplicated, in order of appearance. Linear time: every
    quantifier is bounded and the text is cut at MAX_INPUT characters."""
    s = _clean_text(text)
    if not s.strip():
        return []
    found: list[Item] = []
    taken: list = []
    seen: set = set()

    def add(kind, raw, value, start, end, flags=()):
        key = (kind, value.lower() if kind in ("url", "upi", "app") else value)
        if key in seen:
            return
        seen.add(key)
        found.append(Item(kind, raw[:MAX_RAW], value, start, tuple(flags)))
        taken.append((start, end))

    for m in _URL_RE.finditer(s):
        raw = m.group(0).rstrip(_TRAIL)
        if m.group("bare") and _is_filename_like(raw):
            continue
        if len(raw) < 4:
            continue
        add("url", raw, raw, m.start(), m.start() + len(raw))
    emails = [(m.start(), m.end()) for m in _EMAIL_RE.finditer(s)]
    taken.extend(emails)
    for m in _UPI_RE.finditer(s):
        span = (m.start(), m.end())
        if _spans_overlap(span, [x for x in taken if x not in emails]):
            continue
        if _spans_overlap(span, emails):
            continue
        add("upi", m.group(0), m.group(0).lower(), m.start(), m.end())
    for m in _TOLL_RE.finditer(s):
        span = (m.start(), m.end())
        if _spans_overlap(span, taken):
            continue
        digits = re.sub(r"\D", "", m.group(0))
        add("phone", m.group(0).strip(), digits, m.start(), m.end())
    for m in _MOBILE_RE.finditer(s):
        span = (m.start(1), m.end(1))
        if _spans_overlap(span, taken):
            continue
        digits = re.sub(r"\D", "", m.group(1))
        add("phone", m.group(0).strip(), "+91" + digits, m.start(), m.end())
    for m in _SHORT_CTX.finditer(s):
        span = (m.start(1), m.end(1))
        if _spans_overlap(span, taken):
            continue
        add("phone", m.group(1), m.group(1), m.start(1), m.end(1), ("short",))
    for m in _APK_FILE.finditer(s):
        span = (m.start(), m.end())
        if _spans_overlap(span, taken):
            continue
        name = " ".join(m.group(0).split())
        add("app", name, name.lower(), m.start(), m.end(), ("apk",))
    if not any(i.kind == "app" for i in found):
        for w in _APK_WORDS.finditer(s):
            if not _spans_overlap((w.start(), w.end()), taken):          # an "apk" inside a link is already judged as that link
                add("app", w.group(0), w.group(0).lower(), w.start(), w.end(), ("words",))
                break
    found.sort(key=lambda i: i.pos)
    return found


_FILE_EXT = {"jpg", "png", "pdf", "txt", "doc", "docx", "xls", "xlsx", "zip", "mp4", "mp3", "gif", "py", "js", "html", "css", "json", "csv", "exe", "heic", "webp"}


def _is_filename_like(raw: str) -> bool:
    host = re.split(r"[/:?#]", raw, maxsplit=1)[0]
    return host.rsplit(".", 1)[-1].lower() in _FILE_EXT


# --------------------------------------------------------------------------------------------------------- URL parsing
@dataclass
class Parsed:
    raw: str
    scheme: str = ""
    userinfo: str = ""
    host: str = ""          # unicode, lower-case, no trailing dot
    ascii_host: str = ""    # IDNA (punycode) form
    port: str = ""
    path: str = ""
    is_ip: bool = False
    code_url: bool = False  # javascript:, data: ...
    ok: bool = True


_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_HOSTCHARS = re.compile(r"^[^\s/\\?#@<>\"'`]+$")


def _to_ascii_host(h: str) -> str:
    if h.isascii():
        return h.lower()
    try:
        return h.encode("idna").decode("ascii").lower()
    except Exception:
        return h.lower() if h.isascii() else ""


def _to_unicode_host(h: str) -> str:
    try:
        return h.encode("ascii").decode("idna").lower() if "xn--" in h else h.lower()
    except Exception:
        return h.lower()


def parse_url(value: str) -> Parsed:
    raw = (value or "").strip()
    p = Parsed(raw=raw)
    if re.match(r"^(?:javascript|vbscript|data):", raw, re.I):
        p.code_url = True
        p.scheme = raw.split(":", 1)[0].lower()
        return p
    m = re.match(r"^([a-z][a-z0-9+.-]{1,10})://(.*)$", raw, re.I | re.S)
    if m:
        p.scheme, rest = m.group(1).lower(), m.group(2)
    else:
        rest = raw
    auth = re.split(r"[/\\?#]", rest, maxsplit=1)
    authority = auth[0]
    p.path = rest[len(authority):][:300]
    if "@" in authority:
        p.userinfo, authority = authority.rsplit("@", 1)
    if authority.startswith("["):                    # IPv6 literal
        end = authority.find("]")
        host, tail = (authority[1:end], authority[end + 1:]) if end > 0 else ("", "")
        p.is_ip = bool(host)
    else:
        host, _, port = authority.partition(":")
        tail = ":" + port if port else ""
        host = unquote(host)
    if tail.startswith(":"):
        p.port = tail[1:]
        if not p.port.isdigit():
            p.ok = False
    host = host.strip(".").lower()
    if not host or len(host) > 253 or not _HOSTCHARS.match(host):
        p.ok = False
        return p
    p.is_ip = p.is_ip or bool(_IPV4.match(host)) or bool(re.match(r"^(?:0x[0-9a-f]+|\d{8,12})$", host))
    p.host = _to_unicode_host(host)
    p.ascii_host = _to_ascii_host(host) if not p.is_ip else host
    if not p.ascii_host:
        p.ok = False
    return p


# --------------------------------------------------------------------------------------------------- confusables / rules
_CONFUSABLES = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w", "ӏ": "l", "ɡ": "g", "ո": "n", "ս": "u", "ɩ": "i", "ɑ": "a", "ꞵ": "b",
    # Greek
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "γ": "y", "ϲ": "c", "η": "n", "ω": "w",
    # Armenian / Latin lookalikes
    "ı": "i", "ȷ": "j", "ɢ": "g", "ʀ": "r", "ɴ": "n", "ᴅ": "d", "ᴏ": "o", "ᴘ": "p", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ᴢ": "z",
}
_CONF_TABLE = {ord(k): v for k, v in _CONFUSABLES.items()}
_SCAM_WORDS = ("kyc", "update", "verify", "verification", "login", "claim", "register", "registration", "offer", "offers", "bonus", "refund",
               "reward", "rewards", "lucky", "gift", "prize", "cashback", "free", "yojana", "helpline", "support", "customer", "care", "apply",
               "status", "link")
_SCAM_SUBSTR = tuple(w for w in _SCAM_WORDS if len(w) >= 5)


def _mixed_script(label: str) -> bool:
    scripts = set()
    for ch in label:
        if ch.isalpha():
            try:
                scripts.add(unicodedata.name(ch).split(" ", 1)[0])
            except ValueError:
                scripts.add("?")
    return len(scripts) > 1


def _skeleton_variants(label: str) -> set:
    """Look-alike-folded forms of a label: confusable letters mapped, then rn->m, vv->w, 0->o, 5->s, 1->l (and 1->i)."""
    base = unicodedata.normalize("NFKC", label).lower().translate(_CONF_TABLE)
    base = base.replace("rn", "m").replace("vv", "w").replace("0", "o").replace("5", "s")
    return {base.replace("1", "l"), base.replace("1", "i")}


def _edit_distance(a: str, b: str, limit: int) -> int:
    """Levenshtein distance, giving up (returning limit + 1) once it must exceed `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _is_subsequence_insert(short: str, long_: str) -> bool:
    """True when long_ is `short` with exactly one extra character."""
    if len(long_) != len(short) + 1:
        return False
    i = 0
    for ch in long_:
        if i < len(short) and ch == short[i]:
            i += 1
    return i == len(short)


def _parts(label: str) -> list[str]:
    return [p for p in re.split(r"[-_.]+|\d+", label) if p]


def _token_hit(label: str, token: str) -> bool:
    """Does `label` carry the brand `token`? Short tokens (under 4 letters) must be a whole hyphen/digit-separated word; longer ones may
    also start the label or be a whole word; hyphenated tokens (pm-kisan) match as a word sequence or run together."""
    parts = _parts(label)
    tparts = _parts(token)
    n = len(tparts)
    if n > 1 and any(parts[i:i + n] == tparts for i in range(len(parts) - n + 1)):
        return True
    flat = "".join(tparts)
    if flat in parts:
        return True
    return len(flat) >= 4 and (label.replace("-", "").startswith(flat) or (len(flat) >= 6 and flat in label.replace("-", "")))


def _scam_word_in(label: str, exclude: str = "") -> str | None:
    parts = _parts(label)
    flat = label.replace("-", "")
    for w in _SCAM_WORDS:
        if w in parts and w != exclude:
            return w
    for w in _SCAM_SUBSTR:
        if w in flat and w != exclude:
            return w
    return None


@dataclass
class Finding:
    kind: str
    value: str
    verdict: str
    brand: str | None = None
    reasons: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    facts: list = field(default_factory=list)
    official_alternative: str | None = None
    rules: list = field(default_factory=list)
    host: str = ""
    shortener: bool = False
    raw: str = ""
    lang: str = "en"

    @property
    def label(self) -> str:
        return t(self.verdict, self.lang, brand=self.brand or "an official address") if self.verdict == LOOKALIKE else t(self.verdict, self.lang)

    def to_dict(self, site: str | None = None) -> dict:
        d = {"kind": self.kind, "value": self.value, "verdict": self.verdict, "label": self.label, "class": CSS_CLASS[self.verdict],
             "reasons": list(self.reasons), "actions": list(self.actions)}
        if self.raw:
            d["raw"] = self.raw
        if self.facts:
            d["facts"] = list(self.facts)
        if self.brand:
            d["brand"] = self.brand
        if self.official_alternative:
            d["official_alternative"] = self.official_alternative
        if self.rules:
            d["rules"] = list(self.rules)
        if self.shortener:
            d["shortener"] = True
        w = warn_whatsapp(self, site)
        if w:
            d["warn_whatsapp"] = w
        return d


def _defang(s: str) -> str:
    return s.replace(".", "[.]")


def warn_text(f: Finding, site: str | None = None) -> str | None:
    """The WhatsApp warning for a LOOKALIKE or SUSPICIOUS result. No personal data: only the address and what Sach found."""
    if f.verdict not in (LOOKALIKE, PATTERN):
        return None
    site = site or site_url()
    what = _defang(f.host or f.value)[:80]
    if f.verdict == LOOKALIKE:
        alt = f" The real address is {f.official_alternative}." if f.official_alternative else ""
        return f"Warning: this link ({what}) imitates {f.brand or 'an official address'}.{alt} Checked on Sach {site}"
    return f"Warning: this {'link' if f.kind == 'url' else 'message'} ({what}) matches a scam pattern. Do not tap it or enter any OTP or PIN. Checked on Sach {site}"


def warn_whatsapp(f: Finding, site: str | None = None) -> str | None:
    txt = warn_text(f, site)
    return ("https://wa.me/?text=" + quote(txt, safe="")) if txt else None


# -------------------------------------------------------------------------------------------------------- analysis: URL
ODD_TLDS = scamsigns._ODD_TLD | {"live", "vip", "cc", "club", "app", "icu", "cyou", "rest", "bond", "life", "today", "digital", "xyz"}
# ODD_TLDS reuses scamsigns' list and adds a few more registry endings that are cheap and heavily used for throwaway scam pages
_YOUNG_NOTE = "This address was registered only {n} day{s} ago. Official sites are rarely brand new."
_RECENT_NOTE = "This address was registered {n} days ago, which is fairly recent."


def is_shortener(host: str) -> bool:
    return any(_under(host, d) for d in SHORTENERS)


def _brand_from_text(text: str):
    """First brand whose official domain appears (as a dotted label sequence) in `text`."""
    tl = text.lower()
    for d, rec in index().by_domain.items():
        if re.search(r"(?<![a-z0-9-])" + re.escape(d) + r"(?![a-z0-9-])", tl):
            return rec, d
    for zone in ("gov.in", "nic.in", "bank.in"):
        m = re.search(r"(?<![a-z0-9-])([a-z0-9-]{2,40}\." + re.escape(zone) + r")(?![a-z0-9-])", tl)
        if m:
            return {"brand": m.group(1), "short": m.group(1), "primary": m.group(1)}, m.group(1)
    return None, None


def _lookalike_rules(p: Parsed, host: str, ascii_host: str) -> list[tuple]:
    """Concrete evidence that `host` imitates an official address: [(rule_id, brand_rec, reason_text)]."""
    idx = index()
    hits: list[tuple] = []
    reg = registrable(host)
    reg_label = reg.split(".")[0]
    # (i) official domain used as a prefix / subdomain of something else
    for d, rec in idx.by_domain.items():
        pat = r"(?:^|[.-])" + re.escape(d) + r"(?:[.-]|$)"
        m = re.search(pat, host)
        if m and not _under(host, d) and not _cc_tail(host, m.end()):
            hits.append(("official_prefix", rec, f"The address starts with {d}, but the site it really goes to is {reg}. Only the last part of the name before the first \"/\" counts."))
            break
    else:
        for zone in ("gov.in", "nic.in", "bank.in"):
            m = re.search(r"(?:^|\.)([a-z0-9-]{2,40}\." + re.escape(zone) + r")(?:\.|$)", host)
            if m and not host.endswith("." + zone) and host != zone:
                hits.append(("official_prefix", {"brand": "an official body", "short": "an official body", "primary": None}, f"The address starts with {m.group(1)}, but the site it really goes to is {reg}. Only the last part of the name before the first \"/\" counts."))
                break
    # (ii) brand token + scam word in a non-official host
    label_all = host[: len(host) - len(reg)].rstrip(".")                # sub-domain part, may be empty
    labels_to_scan = [reg_label] + [x for x in label_all.split(".") if x]
    done_ii = False
    for rec in idx.brands:
        for lab in labels_to_scan:
            for tok in rec["tokens"]:
                if _token_hit(lab, tok):
                    w = _scam_word_in(lab, exclude=tok.replace("-", ""))
                    if w:
                        hits.append(("brand_plus_scam_word", rec, f"The name contains \"{tok}\" together with the word \"{w}\", but the address is not on {rec['short']}'s verified list."))
                        done_ii = True
                        break
            if done_ii:
                break
        if done_ii:
            break
    # (iii) typo-squat / homoglyph / hyphens-and-digits variant of an official label
    if reg_label and reg not in idx.by_domain:
        raw_label = reg_label
        stripped = re.sub(r"[-\d]", "", raw_label)
        variants = _skeleton_variants(raw_label)
        for off_label, (short, off_dom) in idx.labels.items():
            if raw_label == off_label or reg == off_dom:
                continue
            if not _eligible(off_label):
                continue
            if any(v == off_label for v in variants) and raw_label != off_label:
                if mixed_or_confusable(raw_label):
                    hits.append(("typosquat_lookalike_chars", {"brand": short, "short": short, "primary": off_dom}, f"The name uses look-alike characters to copy {off_dom}."))
                else:
                    hits.append(("typosquat_lookalike_chars", {"brand": short, "short": short, "primary": off_dom}, f"The name is {off_dom} with look-alike letters swapped in (for example \"rn\" for \"m\" or a zero for an o)."))
                break
            if stripped == off_label and stripped != raw_label:
                hits.append(("typosquat_hyphen_digit", {"brand": short, "short": short, "primary": off_dom}, f"The name is {off_dom.split('.')[0]} with extra hyphens or digits added."))
                break
            if True:
                limit = 2 if len(off_label) >= 8 else 1
                if len(off_label) == 5:                                  # 5-letter labels: only an added or dropped letter, not a swapped one
                    near = _is_subsequence_insert(off_label, raw_label) or _is_subsequence_insert(raw_label, off_label)
                else:
                    near = _edit_distance(raw_label, off_label, limit) <= limit or any(_edit_distance(v, off_label, limit) <= limit for v in variants)
                if near and raw_label != off_label and len(raw_label) >= 5:
                    hits.append(("typosquat_edit_distance", {"brand": short, "short": short, "primary": off_dom}, f"The name is a small misspelling of {off_dom}."))
                    break
    # (iv) user-info trick, punycode that spells a brand word
    if p.userinfo:
        rec, d = _brand_from_text(unquote(p.userinfo))
        if rec is not None or "." in p.userinfo:
            hits.append(("userinfo_trick", rec or {"brand": "a well-known address", "short": "a well-known address", "primary": None},
                         f"The part before the @ sign ({p.userinfo[:40]}) is only decoration. The link really goes to {host}."))
    if "xn--" in ascii_host and host != ascii_host:
        for rec in idx.brands:
            for tok in rec["tokens"]:
                if len(tok) >= 3 and any(_token_hit(v, tok) for v in _skeleton_variants(reg_label)):
                    hits.append(("punycode_brand", rec, f"The address is written with special characters that spell \"{tok}\"."))
                    break
            else:
                continue
            break
    return hits


EDIT_5 = {"paytm", "irctc", "uidai"}        # 5-letter official names eligible for look-alike rules (others, like "kotak" or "umang", are ordinary words or names)


def _eligible(off_label: str) -> bool:
    return len(off_label) >= 6 or off_label in EDIT_5


def _cc_tail(host: str, end: int) -> bool:
    """amazon.com.au is Amazon's own Australian site: a bare two-letter country ending after an official domain is not the prefix trick."""
    return bool(re.match(r"^\.[a-z]{2}$", host[end - 1:] if end and host[end - 1:end] == "." else ""))


def mixed_or_confusable(label: str) -> bool:
    return _mixed_script(label) or any(ch in _CONFUSABLES for ch in label.lower())


def _money_context(context: str) -> bool:
    return bool(context) and bool(scamsigns._MONEY_GOV.search(context[:MAX_INPUT]))


def _age_notes(age: int | None) -> tuple[list, bool, bool]:
    """(notes, is_young, is_recent) for a domain age in days; no age means no information: no note at all."""
    if age is None:
        return [], False, False
    if age < YOUNG_DAYS:
        return [_YOUNG_NOTE.format(n=max(age, 0), s="" if age == 1 else "s")], True, True
    if age < RECENT_DAYS:
        return [_RECENT_NOTE.format(n=age)], False, True
    return [], False, False


def analyze_domain(url_or_host: str, context: str = "", *, age_days: int | None = None, threats=None, lang: str = "en") -> Finding:
    """Classify one link or hostname. `context` is the text around it (money/government words make a shortener, odd ending or young
    domain a SUSPICIOUS_PATTERN). `age_days` and `threats` come from the optional online lookups; None means no information."""
    p = parse_url(url_or_host)
    f = Finding("url", p.raw[:300], UNKNOWN, raw=p.raw[:MAX_RAW], lang=lang)
    if p.code_url:
        f.verdict = PATTERN
        f.rules.append("code_url")
        f.reasons.append("This is not a web address. It is a piece of code that would run on your phone if tapped.")
        f.actions = ["Do not tap it.", ACT_REPORT]
        return f
    if not p.ok or not p.host:
        f.reasons.append("Sach could not read this as a web address.")
        f.actions = list(HOW_TO_CHECK)
        return f
    host, ascii_host = p.host, p.ascii_host
    f.host = host
    f.shortener = is_shortener(ascii_host)
    is_apk = bool(re.search(r"\.apk(?:$|[?#])", p.path, re.I))
    money = _money_context(context or p.raw)
    notes, young, recent = _age_notes(age_days)
    if p.scheme == "http":
        f.facts.append("This link does not use HTTPS, so anything typed into it is not encrypted.")
    elif p.scheme == "https":
        f.facts.append("It uses HTTPS. That only means the connection is encrypted; it says nothing about who runs the site.")
    if age_days is not None:
        f.facts.append(f"Domain registered about {age_days} days ago (public registration record).")

    rec, rec_dom = (None, None) if p.is_ip else index().match_host(ascii_host)
    official_host = (not p.is_ip) and (rec is not None or is_official("https://" + ascii_host))
    if official_host and not p.userinfo and not is_apk:
        f.verdict = OFFICIAL
        body = (index().body.get(rec_dom) or rec["brand"]) if rec else _zone_body(ascii_host)
        f.brand = body
        f.reasons.append(f"This address belongs to {body}." if rec else f"This address ends in a registry-restricted ending: {body}.")
        f.reasons.append("Being on the list only vouches for the address. It does not vouch for a message that sent it to you.")
        f.actions = ["Still prefer typing the address yourself, or using the official app, instead of tapping links in messages.",
                     "Never share an OTP or PIN, even on an official site, unless you started the action yourself."]
        return f

    hits: list[tuple] = []
    if official_host and (p.userinfo or is_apk):
        pass                                                              # handled below as a pattern, not as a lookalike
    elif p.is_ip:
        pass
    else:
        hits = _lookalike_rules(p, host, ascii_host)
    if hits:
        f.verdict = LOOKALIKE
        rec0 = hits[0][1]
        f.brand = rec0.get("short") or rec0.get("brand")
        f.official_alternative = rec0.get("primary")
        for rid, _r, why in hits:
            f.rules.append(rid)
            f.reasons.append(why)
        f.reasons.append("Sach flags this only because of the evidence above. It is not a judgement about who runs the site.")
        f.actions = ["Do not tap the link or enter any details on it."]
        if f.official_alternative:
            f.actions.append(f"If you need {f.brand}, type the real address yourself: {f.official_alternative}")
        f.actions += ["Never enter an OTP, PIN, card details or a password after tapping a link in a message.", ACT_REPORT]
    else:
        odd_tld = ascii_host.rsplit(".", 1)[-1] in ODD_TLDS
        pattern: list[str] = []
        if p.is_ip:
            pattern.append("The link goes to a bare number address (an IP address), not a website name. Banks and government sites do not do this.")
            f.rules.append("ip_host")
        if is_apk:
            pattern.append("The link downloads an app file (.apk). " + ("Its address is on the official list, but Sach flags every link to an app file. " if official_host else "") +
                           "Real government and bank apps are installed from the Google Play Store or Apple App Store, never from a link in a message.")
            f.rules.append("apk_link")
        if p.userinfo and official_host:
            pattern.append("The link has a user@ part in front of the address, which is unusual for a real link.")
            f.rules.append("userinfo")
        if any(_mixed_script(lb) for lb in host.split(".")):
            pattern.append("The address mixes letters from different alphabets, a trick used to copy another address.")
            f.rules.append("mixed_script")
        if f.shortener and money:
            pattern.append("A short link hides where it goes, and the message talks about money or government benefits.")
            f.rules.append("shortener_money")
        if odd_tld and money:
            pattern.append(f"The address ends in .{ascii_host.rsplit('.', 1)[-1]}, an ending cheap and common in scam pages, and the message talks about money or government benefits.")
            f.rules.append("odd_tld_money")
        if young and (money or odd_tld or f.shortener):
            pattern.append("The address is brand new and sits beside money, government or short-link signs.")
            f.rules.append("young_domain")
        if threats:
            pattern.append("Google Safe Browsing lists this address as dangerous (" + ", ".join(sorted({str(x).replace('_', ' ').lower() for x in threats}))[:120] + ").")
            f.rules.append("safebrowsing")
        if pattern:
            f.verdict = PATTERN
            f.reasons += pattern
            f.actions = ["Do not tap the link or enter any details on it.", "Never enter an OTP, PIN, card details or a password after tapping a link in a message.", ACT_REPORT]
        else:
            f.verdict = UNKNOWN
            f.reasons.append("This address is not on Sach's verified official list, so Sach cannot vouch for it. That is not the same as saying it is bad.")
            if f.shortener:
                f.reasons.append("It is a short link, which hides the real destination.")
            f.actions = list(HOW_TO_CHECK)
    if notes and f.verdict != OFFICIAL:
        f.reasons += notes
    return f


def _zone_body(host: str) -> str:
    if host.endswith(".gov.in") or host == "gov.in":
        return "an Indian government address (.gov.in)"
    if host.endswith(".nic.in"):
        return "an Indian government address (.nic.in)"
    if any(host.endswith("." + z) for z in OFFICIAL_ZONES):
        return "a bank regulated by RBI (.bank.in)"
    if host.endswith("who.int"):
        return "the World Health Organization"
    return "a body on Sach's official list (docs/sources.md)"


# ------------------------------------------------------------------------------------------------ analysis: UPI, phone, app
KNOWN_HANDLES: dict = {}        # handle -> {"name": ..., "evidence": url}. Empty on purpose: see the module docstring.


def analyze_upi(vpa: str, signs: set | None = None, lang: str = "en") -> Finding:
    vpa = (vpa or "").strip().lower()
    f = Finding("upi", vpa, UNKNOWN, raw=vpa[:MAX_RAW], lang=lang)
    m = re.match(r"^([a-z0-9][a-z0-9._-]{1,48})@([a-z][a-z0-9]{1,24})$", vpa)
    if not m:
        f.reasons.append("This does not look like a valid UPI ID (it should be name@handle).")
        f.actions = list(UPI_RULES)
        return f
    name, handle = m.groups()
    known = KNOWN_HANDLES.get(handle)
    if known:
        f.facts.append(f"The handle \"{handle}\" belongs to {known['name']} (source: {known['evidence']}).")
    else:
        f.facts.append(f"The part after @ (\"{handle}\") is the bank or app that issued the ID. Sach does not map handles to banks, so it cannot say which one this is.")
    f.reasons.append("A UPI ID alone does not prove who owns it. The registered name shows in your own UPI app before you pay.")
    f.reasons.append("Sach cannot vouch for who owns this ID.")
    rec = None
    for b in index().brands:
        if any(_token_hit(name, tk) for tk in b["tokens"]) and _scam_word_in(name, exclude=""):
            rec = b
            break
    if rec:
        f.verdict = PATTERN
        f.rules.append("upi_official_name")
        f.reasons.append(f"The ID uses the name of {rec['short']} with a support-style word. Banks and government bodies do not collect money at personal-looking UPI IDs.")
    if signs and "upi_trap" in signs:
        f.verdict = PATTERN
        f.rules.append("upi_trap")
        f.reasons.append("The message around it matches the \"pay or approve a payment to receive money\" trick.")
    f.actions = list(UPI_RULES) + [ACT_REPORT]
    return f


def _norm_phone(v: str) -> str:
    return re.sub(r"\D", "", v or "")[-10:] if (v or "").startswith("+91") else re.sub(r"\D", "", v or "")


def official_numbers() -> dict:
    out = {}
    for p in load_data().get("phones", []):
        key = _norm_phone(p["number"]) if p["number"].startswith("+") else re.sub(r"\D", "", p["number"])
        out[key] = p
    return out


def analyze_phone(value: str, lang: str = "en") -> Finding:
    f = Finding("phone", value, UNKNOWN, raw=value[:MAX_RAW], lang=lang)
    key = _norm_phone(value) if value.startswith("+") else re.sub(r"\D", "", value)
    off = official_numbers().get(key)
    if off:
        f.verdict = OFFICIAL
        f.brand = off["what"]
        f.reasons.append(f"Official: {off['what']}.")
        f.reasons.append(f"Source: {off['evidence']} (checked {off.get('checked', '')}).")
        f.actions = ["Take the number from the official site yourself rather than from a message, and never share an OTP or PIN on a call."]
        return f
    digits = re.sub(r"\D", "", value)
    if value.startswith("+91") or (len(digits) == 10 and digits[0] in "6789"):
        f.reasons.append("This is a valid-looking Indian mobile number.")
    elif digits[:4] in ("1800", "1860"):
        f.reasons.append("This is a toll-free style number. Scammers also use these, and Sach cannot check who holds it.")
    else:
        f.reasons.append("This is a short number that Sach does not recognise.")
    f.reasons.append("Sach cannot verify who owns a phone number.")
    f.actions = ["Do not call back or share an OTP, PIN or card details with someone who contacted you first.",
                 "For a fake KYC, refund or prize call: report it on 1930 (financial fraud), cybercrime.gov.in, or Chakshu at sancharsaathi.gov.in.",
                 "To find a bank's or office's real number, use its official site or the back of your card, not a number from a message."]
    return f


def analyze_app(it: Item, lang: str = "en") -> Finding:
    f = Finding("app", it.value, PATTERN if "apk" in it.flags else UNKNOWN, raw=it.raw, lang=lang)
    if "apk" in it.flags:
        f.rules.append("apk_file")
        f.reasons.append("An .apk file is an app installed outside the Play Store. Real government and bank apps come from the Google Play Store or Apple App Store, never from a link or a file in a message.")
    elif "words" in it.flags:
        f.reasons.append("The message asks you to install an app. Sach cannot see which app, and cannot vouch for an app named in a message.")
    else:
        f.reasons.append("Sach cannot vouch for an app from its name alone.")
    f.actions = ["Install apps only from the Google Play Store or Apple App Store, and check the publisher's name against the bank's or ministry's official site.",
                 "Do not give an app permission to read your SMS or control your screen.", ACT_REPORT]
    return f


# ----------------------------------------------------------------------------------------- RDAP (domain age), optional
RDAP_BOOT = "https://data.iana.org/rdap/dns.json"
_RDAP_FALLBACK = {"in": "https://rdap.nixiregistry.in/rdap/", "com": "https://rdap.verisign.com/com/v1/", "net": "https://rdap.verisign.com/net/v1/"}
UA = "Sach-linkcheck/1.0 (+https://github.com/pruthvig1998/sach-check; hostname lookup only)"


def network_enabled() -> bool:
    return not os.environ.get("SACH_LINKCHECK_NO_NETWORK")


def _get_json(url: str, opener, timeout: float = RDAP_TIMEOUT, method: str = "GET", body: bytes | None = None):
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": UA, "Accept": "application/json, application/rdap+json",
                                                                          **({"Content-Type": "application/json"} if body else {})})
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read(1_000_000).decode("utf-8", "replace"))


def _default_opener():
    return urllib.request.build_opener()           # no cookie handler: nothing is ever stored or sent back


def parse_bootstrap(doc) -> dict:
    """IANA bootstrap {"services": [[["com","net"], ["https://rdap.../"]], ...]} -> {tld: base_url}."""
    out = {}
    for svc in (doc or {}).get("services", []) if isinstance(doc, dict) else []:
        try:
            tlds, urls = svc[0], svc[1]
            https = [u for u in urls if isinstance(u, str) and u.startswith("https://")]
            if not https:
                continue
            base = https[0] if https[0].endswith("/") else https[0] + "/"
            for tld in tlds:
                out[str(tld).lower()] = base
        except Exception:
            continue
    return out


def rdap_base(tld: str, opener) -> str | None:
    st = store.get_store()
    boot = None
    try:
        boot = st.get("lc:rdapboot")
    except Exception:
        boot = None
    if not isinstance(boot, dict) or not boot:
        try:
            boot = parse_bootstrap(_get_json(RDAP_BOOT, opener))
        except Exception:
            boot = {}
        if boot:
            try:
                st.set("lc:rdapboot", boot, RDAP_TTL)
            except Exception:
                pass
    return boot.get(tld) or _RDAP_FALLBACK.get(tld)


def parse_registration(doc) -> str | None:
    """The `registration` event date from an RDAP domain object, as an ISO string, or None."""
    for ev in (doc or {}).get("events", []) if isinstance(doc, dict) else []:
        if isinstance(ev, dict) and str(ev.get("eventAction", "")).lower() == "registration" and ev.get("eventDate"):
            return str(ev["eventDate"])
    return None


def _parse_dt(s: str):
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def domain_age_days(host: str, opener=None, now=None) -> int | None:
    """Days since the domain was registered, from RDAP (hostname lookup only). Any failure returns None: no information, never "old"."""
    from datetime import datetime, timezone
    try:
        reg = registrable((host or "").lower().strip("."))
        if not reg or "." not in reg or not re.match(r"^[a-z0-9.-]+$", reg) or _IPV4.match(reg):
            return None
        if opener is None:
            if not network_enabled():
                return None
            opener = _default_opener()
        st = store.get_store()
        key = "lc:rdap:" + reg
        cached = st.get(key)
        if isinstance(cached, dict) and "reg" in cached:
            iso = cached["reg"]
        else:
            base = rdap_base(reg.rsplit(".", 1)[-1], opener)
            if not base:
                return None
            iso = None
            try:
                iso = parse_registration(_get_json(base + "domain/" + quote(reg, safe=""), opener))
            except Exception:
                iso = None
            st.set(key, {"reg": iso}, RDAP_TTL if iso else 3600)
        dt = _parse_dt(iso) if iso else None
        if not dt:
            return None
        n = now or datetime.now(timezone.utc)
        return max(0, (n - dt).days)
    except Exception:
        return None


# --------------------------------------------------------------------------------------- Safe Browsing (optional)
SB_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"


def safebrowsing_request(host: str) -> dict:
    return {"client": {"clientId": "sach", "clientVersion": "1.0"},
            "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                           "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": "http://" + host + "/"}]}}


def safebrowsing_matches(host: str, key: str | None = None, opener=None) -> list | None:
    """Threat types Google lists for the HOSTNAME, [] when none, None when there is no key or anything failed. Never prints the key."""
    key = key if key is not None else os.environ.get("GOOGLE_SAFEBROWSING_API_KEY", "")
    if not key or not host:
        return None
    try:
        if opener is None:
            if not network_enabled():
                return None
            opener = _default_opener()
        doc = _get_json(SB_URL + "?key=" + quote(key, safe=""), opener, 3.0, "POST", json.dumps(safebrowsing_request(host)).encode())
        return [m.get("threatType", "UNKNOWN") for m in doc.get("matches", []) if isinstance(m, dict)] if isinstance(doc, dict) else None
    except Exception:
        return None


# ----------------------------------------------------------------------------------------------- guarded redirect lookup
EXPAND_TIMEOUT = 3.0
MAX_REDIRECTS = 3
_BLOCKED_NETS = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "2001::/32", "2002::/16", "100.64.0.0/10", "198.18.0.0/15", "192.0.0.0/24")]


def ip_is_public(ip: str) -> bool:
    """True only for a globally routable unicast address. Blocks loopback, private, link-local (incl. 169.254.169.254), CGNAT,
    multicast, reserved and unspecified ranges, and IPv6 forms that embed an IPv4 address (mapped, NAT64, 6to4, Teredo)."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if a.version == 6:
        if a.ipv4_mapped is not None:
            return ip_is_public(str(a.ipv4_mapped))
        for net in _BLOCKED_NETS:
            if a.version == net.version and a in net:
                return False
        if a.sixtofour is not None:
            return False
    for net in _BLOCKED_NETS:
        if a.version == net.version and a in net:
            return False
    return bool(a.is_global) and not (a.is_multicast or a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        raw = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _real_connect(host, port, ip, tls, timeout):
    return (_PinnedHTTPS if tls else _PinnedHTTP)(host, port, ip, timeout)


def _blocked(reason: str) -> dict:
    return {"ok": False, "final_url": None, "reason": reason}


def expand_short_link(url: str, *, resolver=socket.getaddrinfo, connect=_real_connect, timeout: float = EXPAND_TIMEOUT,
                      clock=time.monotonic, max_redirects: int = MAX_REDIRECTS) -> dict:
    """Where does a short link point? Only contacts hosts on the SHORTENERS list; follows a redirect only to another listed
    shortener; never reads a body; no cookies. Every hop: http/https only, no credentials, port 80/443, every resolved address must be
    public and we connect to the address we checked (so DNS rebinding cannot swap it afterwards). Returns {ok, final_url, hops, reason}."""
    deadline = clock() + timeout
    cur = (url or "").strip()
    hops = 0
    while True:
        try:
            sp = urlsplit(cur)
            port = sp.port
        except ValueError:
            return _blocked("unreadable address")
        scheme = sp.scheme.lower()
        host = (sp.hostname or "").lower().strip(".")
        if scheme not in ("http", "https") or not host:
            return _blocked("only http and https addresses")
        if sp.username is not None or sp.password is not None or "@" in sp.netloc:
            return _blocked("addresses with credentials are refused")
        if port not in (None, 80, 443):
            return _blocked("unusual port")
        if not is_shortener(host):
            return _blocked("not a known short-link service") if hops == 0 else {"ok": True, "final_url": cur, "hops": hops, "reason": "contacted_shorteners_only"}
        port = port or (443 if scheme == "https" else 80)
        if clock() >= deadline:
            return _blocked("timed out")
        try:
            infos = resolver(host, port, 0, socket.SOCK_STREAM)
            ips = [i[4][0] for i in infos]
        except Exception:
            return _blocked("could not resolve")
        if not ips or not all(ip_is_public(ip) for ip in ips):
            return _blocked("address is not a public internet address")
        ip = ips[0]                                              # connect to exactly the address that was checked
        path = (sp.path or "/") + ("?" + sp.query if sp.query else "")
        resp = None
        for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
            remaining = deadline - clock()
            if remaining <= 0:
                return _blocked("timed out")
            conn = None
            try:
                conn = connect(host, port, ip, scheme == "https", remaining)
                conn.request(method, path, headers={"User-Agent": UA, "Accept": "*/*", "Connection": "close", **extra})
                resp = conn.getresponse()
                status = resp.status
                loc = resp.getheader("Location")
            except Exception:
                resp = None
                status = 0
                loc = None
            finally:
                try:
                    if conn is not None:
                        conn.close()                              # the body is never read
                except Exception:
                    pass
            if status in (301, 302, 303, 307, 308) and loc:
                break
            if method == "HEAD" and status in (400, 403, 404, 405, 501, 0):
                continue
            break
        if not (resp is not None and status in (301, 302, 303, 307, 308) and loc):
            if status == 0:
                return _blocked("no answer")
            return {"ok": True, "final_url": cur, "hops": hops, "reason": "not_a_redirect"}
        hops += 1
        nxt = urljoin(cur, loc.strip())
        if hops > max_redirects:
            return _blocked("too many redirects")
        cur = nxt
        if not re.match(r"^https?://", cur, re.I):
            return _blocked("redirects to something other than a web address")


def expand_and_analyze(url: str, context: str = "", lang: str = "en", **kw) -> dict:
    res = expand_short_link(url, **kw)
    out = {"ok": bool(res.get("ok")), "reason": res.get("reason", "")}
    if res.get("ok") and res.get("final_url"):
        fu = res["final_url"]
        sp = urlsplit(fu)
        shown = (sp.scheme + "://" + (sp.netloc.rsplit("@", 1)[-1]) + sp.path)[:120] if sp.scheme else fu[:120]
        out["final"] = shown
        out["finding"] = analyze_domain(fu.split("#", 1)[0].split("?", 1)[0], context, lang=lang).to_dict()      # tracking query strings are not shown
    return out


# ------------------------------------------------------------------------------------------------------------ top level
def analyze_item(it: Item, context: str, signs: set, *, age=None, threats=None, lang: str = "en") -> Finding:
    if it.kind == "url":
        f = analyze_domain(it.value, context, age_days=age, threats=threats, lang=lang)
    elif it.kind == "upi":
        f = analyze_upi(it.value, signs, lang)
    elif it.kind == "phone":
        f = analyze_phone(it.value, lang)
    else:
        f = analyze_app(it, lang)
    f.raw = it.raw
    return f


def _lookups(hosts: list, opener=None, sb_opener=None) -> dict:
    """{host: (age_days|None, threats|None)} for at most RDAP_BUDGET hostnames, in parallel, within a hard wall-clock budget."""
    out: dict = {h: (None, None) for h in hosts}
    if not hosts or (opener is None and sb_opener is None and not network_enabled()):
        return out
    hosts = hosts[:RDAP_BUDGET]

    def work(h):
        return domain_age_days(h, opener), safebrowsing_matches(h, opener=sb_opener)

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts))
    futs = {ex.submit(work, h): h for h in hosts}
    try:
        done, _ = concurrent.futures.wait(futs, timeout=RDAP_TIMEOUT * 2)
        for fu in done:
            try:
                out[futs[fu]] = fu.result()
            except Exception:
                pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out


def check_text(text, *, online: bool = True, opener=None, sb_opener=None, lang: str = "en", site: str | None = None) -> dict:
    """The whole engine: text -> {items: [...], summary: {...}, ui: {...}}. Deterministic rules plus optional hostname-only lookups."""
    raw_text = text if isinstance(text, str) else ""
    truncated = len(raw_text) > MAX_INPUT
    clean = raw_text[:MAX_INPUT]
    items = extract_items(clean)
    if not items:
        stripped = " ".join(clean.split())
        if 2 <= len(stripped) <= 60 and not re.search(r"https?:|@|\d{6,}", stripped):
            items = [Item("app", stripped[:MAX_RAW], stripped.lower(), 0, ("name",))]
    total = len(items)
    items = items[:MAX_ITEMS]
    ctx = _clean_text(clean)
    try:
        signs = {s["id"] for s in scamsigns.analyze(clean)}
    except Exception:
        signs = set()
    lookups: dict = {}
    if online:
        hosts = []
        for it in items:
            if it.kind == "url":
                p = parse_url(it.value)
                if p.ok and p.host and not p.is_ip and not p.code_url and not is_official("https://" + p.ascii_host):
                    if p.ascii_host not in hosts:
                        hosts.append(p.ascii_host)
        lookups = _lookups(hosts, opener, sb_opener)
    findings = []
    for it in items:
        age = threats = None
        if it.kind == "url":
            p = parse_url(it.value)
            age, threats = lookups.get(p.ascii_host, (None, None))
        f = analyze_item(it, ctx, signs, age=age, threats=threats, lang=lang)
        if it.kind == "app" and "name" in it.flags:
            f.reasons.insert(0, "Sach could not find a link, number or UPI ID, so it treated the text as an app name.")
        findings.append(f)
    return {"items": [f.to_dict(site) for f in findings], "summary": summarize(findings, total, truncated, lang), "ui": ui_strings(lang)}


def summarize(findings: list, total: int | None = None, truncated: bool = False, lang: str = "en") -> dict:
    c = {v: 0 for v in (OFFICIAL, LOOKALIKE, PATTERN, UNKNOWN)}
    for f in findings:
        c[f.verdict] += 1
    total = len(findings) if total is None else total
    bits = []
    if c[LOOKALIKE]:
        bits.append(f"{c[LOOKALIKE]} imitate{'s' if c[LOOKALIKE] == 1 else ''} an official address")
    if c[PATTERN]:
        bits.append(f"{c[PATTERN]} look{'s' if c[PATTERN] == 1 else ''} like a scam pattern")
    if c[UNKNOWN]:
        bits.append(f"{c[UNKNOWN]} Sach cannot vouch for")
    if c[OFFICIAL]:
        bits.append(f"{c[OFFICIAL]} on the verified official list")
    text = (f"{total} item{'s' if total != 1 else ''} found: " + ", ".join(bits) + ".") if total else t("none", lang)
    if total > len(findings):
        text += f" Only the first {len(findings)} are shown."
    if truncated:
        text += f" Only the first {MAX_INPUT} characters were read."
    return {"total": total, "shown": len(findings), "official": c[OFFICIAL], "lookalike": c[LOOKALIKE], "pattern": c[PATTERN], "unknown": c[UNKNOWN],
            "high_risk": c[LOOKALIKE] + c[PATTERN], "truncated": truncated, "text": text}


# ---------------------------------------------------------------------------------------------------------- HTML (no-JS)
esc = html.escape


def card_html(d: dict, lang: str = "en", ui: dict | None = None) -> str:
    ui = ui or ui_strings(lang)
    cls = esc(d["class"], quote=True)
    glyph = GLYPH.get(d.get("verdict"), "?")
    reasons = "".join(f"<li>{esc(r)}</li>" for r in d.get("reasons", []))
    facts = "".join(f"<li>{esc(r)}</li>" for r in d.get("facts", []))
    acts = "".join(f"<li>{esc(a)}</li>" for a in d.get("actions", []))
    alt = ""
    if d.get("official_alternative"):
        alt = f'<p class="lc-real"><b>{esc(ui["real_address"])}:</b> <code>{esc(d["official_alternative"])}</code></p>'
    warn = ""
    if d.get("warn_whatsapp"):
        warn = f'<a class="btn ghost lc-warn" href="{esc(d["warn_whatsapp"], quote=True)}" rel="noopener">{esc(ui["warn"])}</a>'
    return (f'<article class="lc-card {cls}"><div class="lc-head"><span class="lc-badge"><span aria-hidden="true">{glyph}</span> {esc(d["label"])}</span>'
            f'<span class="lc-kind">{esc(d["kind"])}</span></div><p class="lc-val"><code>{esc(d.get("raw") or d["value"])}</code></p>'
            f'<ul class="lc-why">{reasons}{facts}</ul>{alt}<p class="lc-todo"><b>{esc(ui["what_to_do"])}</b></p><ul>{acts}</ul>{warn}</article>')


def results_html(res: dict, lang: str = "en") -> str:
    ui = res.get("ui") or ui_strings(lang)
    s = res["summary"]
    if not res["items"]:
        return f'<div class="lc-results" id="lc-out" role="status"><p class="lc-sum">{esc(s["text"])}</p></div>'
    cards = "".join(card_html(d, lang, ui) for d in res["items"])
    return f'<div class="lc-results" id="lc-out" role="status"><p class="lc-sum">{esc(s["text"])}</p>{cards}</div>'


def panel_html(text, lang: str = "en") -> str:
    """The compact panel under a fact-check result: up to PANEL_MAX items, offline rules only (no lookups), a collapsed <details>.
    It never touches the verdict, the cache or the ledger."""
    try:
        if not isinstance(text, str) or not text.strip():
            return ""
        items = [i for i in extract_items(text) if i.kind != "app" or "apk" in i.flags]
        if not items:
            return ""
        ctx = _clean_text(text)
        signs = {s["id"] for s in scamsigns.analyze(text)}
        fs = [analyze_item(i, ctx, signs, lang=lang) for i in items[:MAX_ITEMS]]
    except Exception:
        return ""
    fs.sort(key=lambda f: RANK[f.verdict])
    risky = sum(1 for f in fs if f.verdict in (LOOKALIKE, PATTERN))
    head = f'{t("found", lang, n=len(fs))}' + (f" · {risky} {t('high', lang)}" if risky else "")
    shown = fs[:PANEL_MAX]
    rows = "".join(f'<li class="lc-mini {CSS_CLASS[f.verdict]}"><span class="lc-badge"><span aria-hidden="true">{GLYPH[f.verdict]}</span> {esc(f.label)}</span> '
                   f'<code>{esc(f.raw or f.value)}</code>' + (f'<span class="lc-miniwhy">{esc(f.reasons[0])}</span>' if f.reasons else "") +
                   (f'<span class="lc-miniwhy"><b>{esc(t("real_address", lang))}:</b> {esc(f.official_alternative)}</span>' if f.official_alternative else "") + "</li>" for f in shown)
    more = f'<p class="note">{esc(t("more", lang, n=len(fs) - PANEL_MAX))}</p>' if len(fs) > PANEL_MAX else ""
    return (f'<details class="lc-panel" id="lc-panel"><summary>{esc(t("panel", lang))}: {esc(head)}</summary><ul class="lc-list">{rows}</ul>{more}'
            f'<p class="note">{esc(t("panel_hint", lang))} <a href="#linkcheck">#linkcheck</a></p></details>')


def section_html(lang: str = "en", prefill: str = "", result: str = "") -> str:
    """The home-page card. Works without JavaScript (GET /?view=link&q=...); with JavaScript the text is POSTed and never put in the URL."""
    return (f'<section id="linkcheck"><div class="wrap"><h2>{esc(t("title", lang))}</h2><p class="sub">{esc(t("intro", lang))}</p>'
            f'<div class="checker lc-box"><form id="lcform" method="get" action="/#linkcheck"><input type="hidden" name="view" value="link">'
            f'<label for="lc-text" class="kicker">{esc(t("title", lang))}</label>'
            f'<textarea id="lc-text" name="q" rows="3" maxlength="{MAX_INPUT}" autocomplete="off" placeholder="{esc(t("placeholder", lang), quote=True)}">{esc(prefill)}</textarea>'
            f'<div class="row"><button class="btn" id="lc-go" type="submit">{esc(t("check", lang))}</button></div></form>'
            f'<div id="lc-results" aria-live="polite">{result}</div></div></div></section>')


def view_page_result(q: str, lang: str = "en", **kw) -> tuple[str, str]:
    q = (q or "")[:MAX_INPUT]
    if not q.strip():
        return "", q
    return results_html(check_text(q, lang=lang, **kw), lang), q


CSS = """
.lc-box{margin-top:6px}
#lc-text{min-height:96px}
.lc-results{margin-top:18px;display:grid;gap:14px}
.lc-sum{font-weight:600;margin:0}
.lc-card{background:var(--card);border:2px solid var(--rule);border-left-width:10px;border-radius:4px;padding:12px 14px;overflow-wrap:anywhere}
.lc-card.lc-official{border-left-color:var(--true)}.lc-card.lc-lookalike{border-left-color:var(--false)}.lc-card.lc-pattern{border-left-color:var(--mis)}.lc-card.lc-unknown{border-left-color:var(--unv)}
.lc-head{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;justify-content:space-between}
.lc-badge{font-weight:700;font-size:15px;line-height:1.3;display:inline-flex;gap:6px;align-items:baseline}.lc-badge>span{font-family:var(--mono);display:inline-grid;place-items:center;min-width:1.5em;height:1.5em;border:2px solid currentColor;border-radius:50%;font-size:13px}
.lc-official .lc-badge,.lc-mini.lc-official .lc-badge{color:var(--true)}.lc-lookalike .lc-badge{color:var(--false)}.lc-pattern .lc-badge{color:var(--mis)}.lc-unknown .lc-badge{color:var(--unv)}
.lc-lookalike .lc-badge>span{border-radius:3px}.lc-pattern .lc-badge>span{border-radius:0;transform:rotate(45deg)}.lc-pattern .lc-badge>span{transform:none;border-radius:0}
.lc-kind{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
.lc-val{margin:8px 0 4px}.lc-val code,.lc-mini code,.lc-real code{font-family:var(--mono);font-size:14px;overflow-wrap:anywhere;word-break:break-all}
.lc-card ul{margin:4px 0 6px;padding-left:20px}.lc-card li{margin:3px 0;font-size:15px;line-height:1.45}
.lc-todo{margin:8px 0 0}.lc-real{margin:6px 0;font-size:16px}
.lc-card .btn,.lc-box .btn{min-height:44px;margin-top:6px}
.lc-expand-out{margin-top:8px;font-size:14px}
.lc-panel{margin-top:16px;border:1px solid color-mix(in srgb,var(--ink) 25%,transparent);border-radius:4px;padding:8px 14px;background:var(--card)}
.lc-panel summary{min-height:44px;display:flex;align-items:center;font-size:15px;font-weight:600}
.lc-list{list-style:none;margin:0;padding:0}.lc-mini{padding:8px 0;border-top:1px solid color-mix(in srgb,var(--ink) 20%,transparent);overflow-wrap:anywhere}
.lc-miniwhy{display:block;font-size:14px;line-height:1.4;margin-top:2px}
@media(max-width:560px){.lc-card{padding:10px 12px}.lc-box.checker{padding:16px}}
"""

JS = r"""
(()=>{'use strict';
const f=document.getElementById('lcform');if(!f||!window.fetch||!window.AbortController)return;
const ta=document.getElementById('lc-text'),box=document.getElementById('lc-results'),go=document.getElementById('lc-go');
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const post=(api,b)=>fetch('/?api='+api,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(b),credentials:'omit'}).then(r=>r.json().then(j=>({ok:r.ok,j})));
const GL={OFFICIAL:'✓',LOOKALIKE:'✕',SUSPICIOUS_PATTERN:'!',UNKNOWN:'?'};
function card(d,ui){
  const a=el('article','lc-card '+String(d.class||'').replace(/[^a-z-]/g,''));
  const h=el('div','lc-head'),b=el('span','lc-badge');b.append(el('span',null,GL[d.verdict]||'?'));b.append(' '+d.label);h.append(b,el('span','lc-kind',d.kind));a.append(h);
  const v=el('p','lc-val'),c=el('code',null,d.raw||d.value);v.append(c);a.append(v);
  const ul=el('ul','lc-why');(d.reasons||[]).concat(d.facts||[]).forEach(r=>ul.append(el('li',null,r)));a.append(ul);
  if(d.official_alternative){const p=el('p','lc-real'),bb=el('b',null,ui.real_address+':');p.append(bb,' ');p.append(el('code',null,d.official_alternative));a.append(p)}
  const td=el('p','lc-todo');td.append(el('b',null,ui.what_to_do));a.append(td);
  const al=el('ul');(d.actions||[]).forEach(r=>al.append(el('li',null,r)));a.append(al);
  if(d.warn_whatsapp&&d.warn_whatsapp.indexOf('https://wa.me/?text=')===0){const w=el('a','btn ghost lc-warn',ui.warn);w.href=d.warn_whatsapp;w.rel='noopener';a.append(w)}
  if(d.shortener&&d.kind==='url'){const x=el('button','btn ghost lc-expand',ui.expand);x.type='button';const out=el('p','lc-expand-out');out.setAttribute('role','status');
    x.addEventListener('click',async()=>{x.disabled=true;out.textContent=ui.expanding;
      try{const r=await post('linkexpand',{url:d.value});if(r.ok&&r.j.ok&&r.j.finding){out.textContent='';out.append(ui.goes_to+': ');out.append(el('code',null,r.j.final||''));out.append(card(r.j.finding,ui))}else{out.textContent=ui.expand_fail}}
      catch(e){out.textContent=ui.expand_fail}x.disabled=false});a.append(x,out)}
  return a}
function render(j){const ui=j.ui||{what_to_do:'What to do',real_address:'The real address is',warn:'Warn my group on WhatsApp',expand:'Show where this short link goes'};
  const w=el('div','lc-results');w.setAttribute('role','status');w.append(el('p','lc-sum',(j.summary&&j.summary.text)||''));(j.items||[]).forEach(d=>w.append(card(d,ui)));box.replaceChildren(w)}
f.addEventListener('submit',async e=>{const text=ta.value;if(!text.trim())return;e.preventDefault();const label=go.textContent;go.disabled=true;go.textContent='…';
  try{const r=await post('linkcheck',{text,lang:document.documentElement.lang||'en'});if(r.ok)render(r.j);else{box.replaceChildren(el('p','lc-sum',(r.j&&r.j.error)||'Something went wrong.'))}}
  catch(err){f.submit();return}
  go.disabled=false;go.textContent=label;const first=box.querySelector('.lc-sum');if(first){first.setAttribute('tabindex','-1');first.focus({preventScroll:true});first.scrollIntoView({block:'nearest'})}});
})();
"""
