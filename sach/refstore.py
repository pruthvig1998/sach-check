"""Reference store: dated facts copied from official documents (data/reference.json, built by scripts/build_reference.py).

Answers everyday questions such as "When is Diwali?" from the Government's own holiday list, with the source, at no search or AI cost.
It never produces TRUE or FALSE: a question gets an ANSWER card, a statement gets a small "official dates" panel beside its normal result.
Switch off with SACH_REFSTORE=0."""
from __future__ import annotations
import json, os, re
from datetime import date

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "reference.json")
_DATA = None

# Names people actually type, per fact id. Latin aliases match on word boundaries; other scripts match as substrings. NOT NATIVE-REVIEWED.
ALIASES = {
    "republic_day": ("republic day", "गणतंत्र दिवस", "గణతంత్ర దినోత్సవం"),
    "holi": ("holi", "होली", "హోలీ"),
    "id_ul_fitr": ("id-ul-fitr", "eid-ul-fitr", "eid ul fitr", "idul fitr", "ramzan eid", "ramadan eid", "ईद-उल-फितर", "रमज़ान ईद", "రంజాన్"),
    "ram_navami": ("ram navami", "rama navami", "sri rama navami", "राम नवमी", "శ్రీరామ నవమి", "రామ నవమి"),
    "mahavir_jayanti": ("mahavir jayanti", "महावीर जयंती"),
    "good_friday": ("good friday", "गुड फ्राइडे", "గుడ్ ఫ్రైడే"),
    "buddha_purnima": ("buddha purnima", "budh purnima", "बुद्ध पूर्णिमा", "బుద్ధ పూర్ణిమ"),
    "bakrid": ("bakrid", "bakri eid", "eid-ul-adha", "eid ul adha", "id-ul-zuha", "eid al adha", "बकरीद", "బక్రీద్"),
    "muharram": ("muharram", "मुहर्रम", "మొహర్రం"),
    "independence_day": ("independence day", "स्वतंत्रता दिवस", "స్వాతంత్ర్య దినోత్సవం"),
    "id_e_milad": ("id-e-milad", "eid-e-milad", "milad-un-nabi", "milad un nabi", "ईद-ए-मिलाद", "మిలాద్"),
    "janmashtami": ("janmashtami", "krishna janmashtami", "gokulashtami", "जन्माष्टमी", "కృష్ణాష్టమి", "జన్మాష్టమి"),
    "gandhi_jayanti": ("gandhi jayanti", "गांधी जयंती", "గాంధీ జయంతి"),
    "dussehra": ("dussehra", "dasara", "dussera", "vijayadashami", "vijaya dashami", "दशहरा", "विजयादशमी", "దసరా", "విజయదశమి"),
    "diwali": ("diwali", "deepavali", "dipawali", "deepawali", "दिवाली", "दीवाली", "दीपावली", "దీపావళి"),
    "guru_nanak_jayanti": ("guru nanak jayanti", "guru nanak's birthday", "gurpurab", "गुरु नानक जयंती"),
    "christmas": ("christmas", "xmas", "क्रिसमस", "క్రిస్మస్"),
    "new_year": ("new year's day", "new years day"),
    "makar_sankranti": ("makar sankranti", "sankranti", "sankranthi", "मकर संक्रांति", "సంక్రాంతి"),
    "pongal": ("pongal", "பொங்கல்"),
    "basant_panchami": ("basant panchami", "vasant panchami", "बसंत पंचमी"),
    "maha_shivratri": ("maha shivratri", "mahashivratri", "shivaratri", "shivratri", "महाशिवरात्रि", "శివరాత్రి"),
    "shivaji_jayanti": ("shivaji jayanti", "शिवाजी जयंती"),
    "holika_dahan": ("holika dahan", "होलिका दहन"),
    "ugadi": ("ugadi", "yugadi", "gudi padwa", "gudi padava", "cheti chand", "उगादी", "गुड़ी पड़वा", "ఉగాది"),
    "easter": ("easter",),
    "vaisakhi": ("vaisakhi", "baisakhi", "vishu", "tamil new year", "बैसाखी"),
    "bohag_bihu": ("bohag bihu", "bahag bihu", "poila boishakh", "pohela boishakh"),
    "rath_yatra": ("rath yatra", "ratha yatra", "रथ यात्रा"),
    "onam": ("onam", "ഓണം"),
    "raksha_bandhan": ("raksha bandhan", "rakhi", "रक्षाबंधन", "राखी", "రాఖీ", "రక్షాబంధన్"),
    "ganesh_chaturthi": ("ganesh chaturthi", "vinayaka chaturthi", "vinayaka chavithi", "vinayak chaturthi", "गणेश चतुर्थी", "వినాయక చవితి"),
    "valmiki_jayanti": ("valmiki jayanti", "वाल्मीकि जयंती"),
    "karva_chauth": ("karva chauth", "karwa chauth", "करवा चौथ"),
    "naraka_chaturdasi": ("naraka chaturdasi", "naraka chaturdashi", "narak chaturdashi", "నరక చతుర్దశి"),
    "govardhan_puja": ("govardhan puja", "गोवर्धन पूजा"),
    "bhai_duj": ("bhai duj", "bhai dooj", "bhaiya dooj", "भाई दूज"),
    "chhath": ("chhath", "chhath puja", "छठ"),
    "christmas_eve": ("christmas eve",),
}
_QUESTION = re.compile(r"[?？؟]|^\s*(when|what|which|is|are|was|did|does|do|will|who|where|how|kab|kya|kaun)\b|\b(date|kab hai|kab h)\b|"
                       r"कब|क्या|कौन|किस दिन|तारीख|ఎప్పుడు|ఏ రోజు|ఎవరు|తేదీ", re.I)


def enabled() -> bool:
    return os.environ.get("SACH_REFSTORE", "1") != "0"


def _data() -> dict:
    global _DATA
    if _DATA is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _DATA = json.load(f)
        except Exception:
            _DATA = {"sources": {}, "holidays": []}
    return _DATA


def is_question(text: str) -> bool:
    return bool(_QUESTION.search(text or ""))


def _ids(text: str) -> list:
    t = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    hits = []
    for fid, names in ALIASES.items():
        for n in names:
            if (re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", t) if n.isascii() else n in t):
                hits.append((t.find(n), -len(n), fid))
                break
    hits.sort()
    out = [fid for _, _, fid in hits]
    if "christmas_eve" in out and "christmas" in out:
        out.remove("christmas")                          # "christmas eve" also contains "christmas": keep the longer name
    return out


def lookup(text: str, today: date | None = None) -> list:
    """Official dated facts for the festivals or holidays named in `text`. With a year in the text only that year; otherwise this year and next.
    Each fact: {id, name, kind, date, weekday, source, url, note?}. Empty when the store is off or knows nothing."""
    if not enabled():
        return []
    ids = _ids(text)
    if not ids:
        return []
    today = today or date.today()
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", text or "")} or {today.year, today.year + 1}
    d = _data()
    out = []
    for fid in ids[:3]:
        for f in d["holidays"]:
            if f["id"] == fid and int(f["date"][:4]) in years:
                src = d["sources"].get(f["source"], {})
                y, m, dd = (int(x) for x in f["date"].split("-"))
                out.append({**f, "weekday": date(y, m, dd).strftime("%A"), "source": src.get("name", ""), "url": src.get("url", "")})
    return out


def answerable(text: str) -> bool:
    """True when `text` is a short question the store can answer by itself (so no live check is needed)."""
    t = (text or "").strip()
    return bool(t) and len(t.split()) <= 25 and "\n" not in t and (is_question(t) or len(t.split()) <= 5) and bool(lookup(t))


def fmt_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    dt = date(y, m, d)
    return f"{dt.strftime('%A')}, {d} {dt.strftime('%B')} {y}"


try:                                                     # a question the store answers costs nothing, so it never needs a live-check slot
    from . import limits as _limits
    _limits.register_free_probe(lambda text, rl: answerable(text))
except Exception:
    pass
