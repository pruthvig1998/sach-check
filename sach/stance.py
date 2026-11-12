"""Decide whether one fetched page contradicts / confirms / partially supports a claim.

Heuristic mode is deliberately conservative: it only returns a non-'none' stance when
the page overlaps strongly with the claim; everything else stays 'none' -> UNVERIFIED.
With ANTHROPIC_API_KEY set, an LLM judges stance (see llm.py)."""
from __future__ import annotations
import re
from .pib import DEBUNK_MARKERS

_STOP = set("the a an and or of to in on for is are was were be been this that it with as by at from will has have "
            "not no all your you we they their our new get free".split())

def tokens(text: str) -> set[str]:
    ws = [w for w in re.findall(r"[\w\u0900-\u097F\u0C00-\u0C7F]+", text.lower()) if w not in _STOP and len(w) > 1]
    return {w[:5] if w.isascii() and w.isalpha() and len(w) > 5 else w for w in ws}  # crude stem: reduce~reduction

def numbers(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,]*(?:\.\d+)?", text))

def overlap(claim: str, page: str) -> float:
    c = tokens(claim)
    return len(c & tokens(page)) / len(c) if c else 0.0

_STRICT_DEBUNK = re.compile(r"\b(fake|false|misleading|baseless|fabricated|hoax|busts?|no such|not true)\b|"
                            r"फर्जी|फ़र्ज़ी|झूठ|भ्रामक|నకిలీ|అబద్ధ|తప్పుడు", re.I)
_NEGATION = re.compile(r"\b(no|not|never|nahi|nahin|none|without|cannot|won't|isn't|aren't)\b|नहीं|नही|न |లేదు|కాదు|లేవు", re.I)

def heuristic_stance(claim: str, title: str, text: str, tier: str) -> str:
    """Conservative. FALSE-grade stance needs a strict debunk word IN THE TITLE and the claim to match the title.
    Negated claims are never judged heuristically (they could be the opposite of what the page debunks)."""
    if _NEGATION.search(claim):
        return "none"
    page = f"{title} {text}"
    if overlap(claim, page) < 0.6:
        return "none"
    cn = numbers(claim)
    if cn and not cn <= numbers(page):
        return "mixed" if tier == "official" and not _STRICT_DEBUNK.search(title) else "none"
    if tier == "pib_debunk" and _STRICT_DEBUNK.search(title) and overlap(claim, title) >= 0.6:
        return "contradicts"
    return "confirms" if overlap(claim, page) >= 0.8 and tier == "official" and not _STRICT_DEBUNK.search(page) else "none"

_DENIAL = re.compile(r"\b(fake|false|fictitious|fabricated|forged|fraudulent|scam|hoax|baseless|misleading|misinformation|"
                      r"no such|not true|not been issued|has not issued|denies|denied|clarif\w+|no proposal|not giving|"
                      r"does not exist|incorrect)\b|फर्जी|झूठ|भ्रामक|నకిలీ|అబద్ధ|తప్పుడు", re.I)

def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'\u201c\u201d\u2018\u2019.\u2026]", "", t or "")).strip().lower()

def validate_stance(label: str, quote: str, claim: str, title: str, text: str) -> str:
    """Accept an LLM stance only if it is backed by a verbatim quote from the page that relates to the claim.
    - quote must appear verbatim in the page (kills hallucinated evidence)
    - quote must overlap the claim (kills 'related topic' calls)
    - CONFIRMS: quote must contain every number in the claim
    - CONTRADICTS: the page must itself be a debunk/denial (a page describing a real scheme can never refute)
    Anything failing a check becomes 'none' -> UNVERIFIED."""
    if label == "none":
        return "none"
    q, page = _norm(quote), _norm(f"{title} {text}")
    if len(q) < 12 or q not in page:
        return "none"
    if overlap(claim, quote) < 0.4:
        return "none"
    if label == "confirms" and not numbers(claim) <= numbers(quote):
        return "none"
    if label == "mixed" and (overlap(claim, quote) < 0.6 or not numbers(claim) or not numbers(quote)):
        return "none"      # 'partial' drives MISLEADING: needs a strongly related quote with numbers on both sides
    if label == "contradicts" and not _DENIAL.search(f"{title} {quote}"):
        return "none"
    return label

def judge(claim: str, ev, llm=None) -> str:
    if llm is not None:
        try:
            s = llm.stance(claim, ev.title, ev.text)
            if s in ("contradicts", "confirms", "mixed", "none"):
                return s
        except Exception:
            pass  # bad key / network / rate limit: fall back to the conservative heuristic
    return heuristic_stance(claim, ev.title, ev.text, ev.tier)
