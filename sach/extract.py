"""Split a forward into atomic checkable claims and tag each with a domain."""
from __future__ import annotations
import re
from .models import Claim

_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+|\s*[|•▪●]\s*")
_BOILER = re.compile(r"forward|share (this|kar)|भेजें|शेयर|ఫార్వర్డ్|షేర్|please|plz|\bgroup\b|जल्दी|త్వరగా|"
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

def extract_claims(forward: str, max_claims: int = 8) -> list[Claim]:
    out, seen = [], set()
    for part in _SPLIT.split(forward or ""):
        s = re.sub(r"\s+", " ", part).strip(" -–—*_~\"'")
        if len(s.split()) < 4 or _BOILER.search(s) and len(s.split()) < 8:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(Claim(text=s, domain=classify_domain(s)))
    return out[:max_claims]
