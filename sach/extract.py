"""Split a forward into atomic checkable claims and tag each with a domain."""
from __future__ import annotations
import re
from .models import Claim

_INVISIBLE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")

def clean_text(t: str) -> str:
    """Strip control, zero-width and bidi-override characters (they break matching and can spoof display)."""
    return _INVISIBLE.sub("", t or "")

# Sentence ends: . ! ? and the Devanagari/Bengali/Odia danda । and double danda ॥, the Urdu full stop ۔ and question mark ؟, the Meitei cheikhei ꯫
_SPLIT = re.compile(r"(?<=[.!?।॥۔؟\uabeb])\s+|\n+|\s*[|•▪●]\s*")
_BOILER = re.compile(r"forward|share (this|kar|with (?:all|your|every|everyone))|भेजें|शेयर|ఫార్వర్డ్|షేర్|please|plz|\bgroup\b|जल्दी|త్వరగా|"
                     r"good (morning|night|evening|afternoon)|blessed|have a (nice|great|good|happy)|namaste|सुप्रभात|शुभ|శుభోదయం|శుభ|"
                     r"\bclick\b|\blink\b|\bregister\b|\bhurry\b|\bapply now\b|\bvisit\b|\bdownload\b|\bsubscribe\b|\bwhatsapp\b|क्लिक|लिंक|रजिस्टर|క్లిక్|లింక్|నమోదు|"
                     # NOT NATIVE-REVIEWED: share / forward / click / link in the other supported scripts (the same call-to-action filter as above)
                     r"শেয়ার|ফরওয়ার্ড|ক্লিক|লিংক|शेअर|फॉरवर्ड|ஷேர்|ஃபார்வர்டு|கிளிக்|லிங்க்|"
                     r"શેર કરો|ફોરવર્ડ|ક્લિક|લિંક|ਸ਼ੇਅਰ|ਫਾਰਵਰਡ|ਕਲਿੱਕ|ਲਿੰਕ|ଶେୟାର|ଫରୱାର୍ଡ|କ୍ଲିକ୍|ଲିଙ୍କ|"
                     r"ಶೇರ್|ಫಾರ್ವರ್ಡ್|ಕ್ಲಿಕ್|ಲಿಂಕ್|ഷെയർ|ഫോർവേഡ്|ക്ലിക്ക്|ലിങ്ക്|شیئر|فارورڈ|کلک|لنک|"
                     r"^[\W\d_]*$", re.I)
_DOMAINS = {
    "scheme": r"yojana|scheme|subsid|pension|ration|aadhaar|aadhar|pm[- ]?kisan|ayushman|rupees|₹|rs\.?\s?\d|lakh|crore|"
              r"bank|loan|gst|tax|योजना|पेंशन|राशन|आधार|रुपये|₹|పథకం|పింఛను|రేషన్|ఆధార్|రూపాయ",
    "health": r"cancer|covid|vaccine|virus|cure|diabetes|doctor|hospital|medicine|drink|immun|"
              r"कैंसर|टीका|वैक्सीन|इलाज|दवा|बीमारी|క్యాన్సర్|టీకా|వ్యాక్సిన్|చికిత్స|ఆసుపత్రి|మందు",
    "news": r"arrest|killed|attack|election|bandh|curfew|announce|banned|ban |govt|government|minister|"
            r"सरकार|मंत्री|प्रतिबंध|चुनाव|ప్రభుత్వం|మంత్రి|నిషేధ|ఎన్నికల",
}

def classify_domain(text: str) -> str:
    for d, pat in _DOMAINS.items():
        if re.search(pat, text, re.I):
            return d
    return "other"

# Abbreviation dots that must not end a sentence: Rs. and friends, plus the rupee abbreviation in Telugu, Hindi/Marathi, Tamil, Gujarati,
# Kannada and Malayalam. Left out on purpose (not sure enough, or too ambiguous): Bengali "টা." (also the common classifier -টা), Odia, Punjabi.
_ABBR = re.compile(r"(\b(?:Rs|Re|Dr|Mr|Mrs|Ms|Shri|Smt|No|Nos|approx|vs|etc|St|Govt|Min)|రూ|రు|रु|रू|ரூ|રૂ|ರೂ|രൂ)\.", re.I)
_DOT = "\u2024"   # one-dot leader: stands in for the full stop of an abbreviation while we split sentences

def extract_claims(forward: str, max_claims: int = 8, report: dict | None = None) -> list[Claim]:
    """report: optional dict. When given it receives {'sentences': N, 'skipped': [...]} (N = distinct sentences seen, skipped = those
    not returned, in document order). The returned claims are the same with or without it."""
    out, order, seen = [], [], set()
    protected = _ABBR.sub(lambda m: m.group(1) + _DOT, clean_text(forward))
    for part in _SPLIT.split(protected):
        part = part.replace(_DOT, ".")
        s = re.sub(r"\s+", " ", part).strip(" -–—*_~\"'")
        if len(s.split()) < 4 or _BOILER.search(s) and len(s.split()) < 9:
            if report is not None and s and s.lower() not in seen:
                seen.add(s.lower()); order.append((s, None))
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        c = Claim(text=s, domain=classify_domain(s))
        out.append(c); order.append((s, c))
    kept = out[:max_claims]
    if report is not None:
        kept_ids = {id(c) for c in kept}
        report["sentences"] = len(order)
        report["skipped"] = [s for s, c in order if c is None or id(c) not in kept_ids]
    return kept
