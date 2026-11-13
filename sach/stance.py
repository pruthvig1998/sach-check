"""Decide whether one fetched page contradicts / confirms / partially supports a claim.

Heuristic mode is deliberately conservative: it only returns a non-'none' stance when
the page overlaps strongly with the claim; everything else stays 'none' -> UNVERIFIED.
With ANTHROPIC_API_KEY set, an LLM judges stance (see llm.py)."""
from __future__ import annotations
import re
from .pib import DEBUNK_MARKERS
from .lang import to_ascii_digits
from .langwords import DEBUNK_RE, NEGATION_RE

_STOP = set("the a an and or of to in on for is are was were be been this that it with as by at from will has have "
            "not no all your you we they their our new get free than there".split())

_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ures", "ure", "ions", "ion", "edly", "ies", "ied", "ed", "es", "s", "e")

def _stem(w: str) -> str:
    """Light English stemmer, applied identically to claim and page: closure/close/closed -> clos, ordered/order -> order.
    Strips one common suffix, then keeps at most 5 letters (reduce~reduction)."""
    if not (w.isascii() and w.isalpha()) or len(w) <= 3:
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    return w[:5]

# Same-meaning words that official pages and forwards phrase differently. Only used to decide whether two texts are about the same
# thing (relevance thresholds); it never decides a stance, and the number, quote, denial, direction and injection checks are untouched.
_SYN = {}
for _canon, _words in {
    "payment": "payments payment transactions transaction transfers transfer",
    "levy": "levy levied levying levies charged charging imposed imposing impose",
    "above": "above over exceeding exceeds exceed beyond",
    "rs": "rs rupee rupees inr",
    "raise": "hike hiked hikes raise raised raises increase increased increases",
    "ban": "ban banned bans banning prohibited prohibit prohibits",
}.items():
    for _w in _words.split():
        _SYN[_w] = _canon

# Word characters: \w plus every Indic block (Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam: their vowel signs are
# not \w), Meitei Mayek, and the Arabic-script marks (Urdu letters are already \w).
_WORD = r"[\w\u0900-\u0D7F\uABC0-\uABFF\u064B-\u065F\u0670\u06D6-\u06ED]+"

def tokens(text: str) -> set[str]:
    text = re.sub(r"(?<=\d),(?=\d)", "", to_ascii_digits(text).lower())   # native digits -> 0-9; 2,000 == 2000 (and Indian 1,20,579) before splitting into words
    text = re.sub(r"\b(?:more|greater|higher) than\b|\bin excess of\b", "above", text)   # translations say "more than", PIB says "over"
    ws = [_SYN.get(w, w) for w in re.findall(_WORD, text)]
    ws = [w for w in ws if w not in _STOP and len(w) > 1]
    return {_stem(w) for w in ws}

def numbers(text: str) -> set[str]:
    """Numbers with thousands separators removed, so 19,800 == 19800 and Indian 1,20,579 == 120579."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", to_ascii_digits(text))}      # 2000 == ২০০০ == २००० == ٢٠٠٠

def overlap(claim: str, page: str) -> float:
    c = tokens(claim)
    return len(c & tokens(page)) / len(c) if c else 0.0

_STRICT_DEBUNK = re.compile(r"\b(fake|false|misleading|baseless|fabricated|hoax|busts?|no such|not true)\b|"
                            r"फर्जी|फ़र्ज़ी|झूठ|भ्रामक|నకిలీ|అబద్ధ|తప్పుడు|" + DEBUNK_RE, re.I)       # + the other supported languages (NOT NATIVE-REVIEWED, langwords.py)
_NEGATION = re.compile(r"\b(no|not|never|nahi|nahin|none|without|cannot|won't|isn't|aren't)\b|नहीं|नही|न |లేదు|కాదు|లేవు|" + NEGATION_RE, re.I)

_GENERIC = set("""government govt central union state cabinet approved approve approves approval announced announces announce declared declare
declaring declares will give gives giving every all new scheme schemes yojana minister ministry department national india indian day days month months
year years per under has have been being said says message forward people public citizens everyone everybody rs rupees crore lakh thousand
total amount new launched launch issued issue order circular notice notification
today tomorrow yesterday now soon next immediately urgent shortly tonight week weeks""".split())
_GENERIC = {_stem(w) for w in _GENERIC}   # tokens() returns stems, so compare in stemmed form

def distinctive(text: str) -> set:
    """Content words that actually identify the subject (not generic government vocabulary, not numbers)."""
    return {w for w in tokens(text) if w not in _GENERIC and not w.isdigit() and not re.fullmatch(r"[\d,\.]+\w{0,2}", w)}

def subject_coverage(claim: str, evidence_text: str) -> float:
    """Share of the claim's distinctive words that appear in the supporting text. 'mango' must be in the evidence for a mango claim."""
    d = distinctive(claim)
    return 1.0 if not d else len(d & tokens(evidence_text)) / len(d)

# Text aimed at the judge model rather than at a human reader. A forward or a page that contains it is never allowed to drive a
# decisive stance: it can only make Sach abstain. (A blocklist: it catches the common phrasings, not every paraphrase. The hard
# defences are the verbatim-quote, number and subject checks plus the official-host rule; this only closes the loud cases.)
_INJECTION = re.compile(
    r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(instructions?|prompts?|sources?|rules?|evidence)\b|"
    r"\b(ai|llm|automated|bot)[- ]?(reviewers?|checkers?|judges?|graders?|assistants?|models?)\b|"
    r"\b(note|message|notice|instruction|attention)s?\s+(to|for)\s+(the\s+)?(ai|llm|model|assistant|automated|bot|reviewers?|checkers?|judges?)\b|"
    r"\b(system|developer)\s*(message|prompt|override|instruction)s?\b|\bsystem\s*:|\byou are now\b|"
    r"\b(mark|label|rate|output|answer|reply|respond|return|say|write)\s+(this\s+)?(page\s+|message\s+|claim\s+|forward\s+)?(as\s+)?(true|false|confirms?|contradicts?|verified)\b|"
    r"\bverdict\s*:\s*(true|false|confirms?|contradicts?)\b|\b(confirms|contradicts|partial|neither)\s*\|", re.I)

def has_injection(*texts: str) -> bool:
    return any(_INJECTION.search(t or "") for t in texts)

# Direction words: a claim that says 'increased' is not supported by, or refuted by, a quote that only says 'reduce'.
_UP = ("increas", "rais", "hike", "extend", "higher", "doubl", "boost", "expand")
_DOWN = ("reduc", "cut", "lower", "decreas", "lessen", "slash", "trim", "shrink", "drop")

def _direction(text: str) -> set:
    ws = re.findall(r"[a-z]+", (text or "").lower())
    return {d for d, stems in (("up", _UP), ("down", _DOWN)) if any(w.startswith(x) for w in ws for x in stems)}

def direction_conflict(claim: str, evidence: str) -> bool:
    c, e = _direction(claim), _direction(evidence)
    return bool(c) and bool(e) and not (c & e)

# Words that restrict or relocate a claim. A swap of any of them changes what is true, so the quote must contain each one.
_QUALIFIERS = {_stem(w) for w in """only women woman men man girls boys farmers students seniors children widows minors every everyone free double triple half
except unless mandatory compulsory daily monthly weekly annual yearly minimum maximum""".split()} | {
    _stem(m) for m in """january february march april june july august september october november december
kharif rabi monsoon summer winter""".split()}

def critical_words(claim: str) -> set:
    """Qualifier words, plus proper nouns / names (capitalised words inside the sentence: places, seasons, schemes)."""
    toks = tokens(claim)
    caps = {_stem(w.lower()) for w in re.findall(r"(?<=[A-Za-z0-9,] )[A-Z][a-z]{2,}", claim)}   # also after an acronym: 'PM Kisan'
    return (toks & _QUALIFIERS) | (caps - _GENERIC)     # generic officialese ('Union', 'Cabinet') may be dropped in a short quote

_META = re.compile(r"\b(fake|false|hoax|rumou?rs?|misinformation|fact[- ]?check\w*|scam|fraud\w*|misleading)\b", re.I)

def heuristic_stance(claim: str, title: str, text: str, tier: str) -> str:
    """Conservative. FALSE-grade stance needs a strict debunk word IN THE TITLE and the claim to match the title.
    Negated claims are never judged heuristically (they could be the opposite of what the page debunks)."""
    if _NEGATION.search(claim):
        return "none"
    if has_injection(claim, title, text):    # instructions aimed at the judge: never a decisive stance
        return "none"
    if _META.search(claim):      # a claim ABOUT fake news ("send suspected fake news to ...") matches every debunk-themed title
        return "none"
    page = f"{title} {text}"
    if overlap(claim, page) < 0.5 or subject_coverage(claim, f"{title} {text}") < 0.7:
        return "none"
    cn = numbers(claim)
    if cn and not cn <= numbers(page):
        return "mixed" if tier == "official" and not _STRICT_DEBUNK.search(title) else "none"
    if tier == "pib_debunk" and _STRICT_DEBUNK.search(title) and subject_coverage(claim, title) >= 0.6 and overlap(claim, title) >= 0.4:
        return "contradicts"
    return "confirms" if overlap(claim, page) >= 0.8 and tier == "official" and not _STRICT_DEBUNK.search(page) else "none"

_DENIAL = re.compile(r"\b(fake|false|fictitious|fabricated|forged|fraudulent|scam|hoax|baseless|misleading|misinformation|"
                      r"no such|not true|not been issued|has not issued|denies|denied|clarif\w+|no proposal|not giving|"
                      r"does not exist|incorrect)\b|फर्जी|झूठ|भ्रामक|నకిలీ|అబద్ధ|తప్పుడు|" + DEBUNK_RE, re.I)

# A debunk page quotes the rumour in order to refute it. Such a page, or a quote that only REPORTS a claim, can never confirm it.
_PAGE_DEBUNK = re.compile(r"\b(is|are|was|were) (completely |totally |entirely )?(fake|false|fictitious|fabricated|baseless|misleading|a hoax)\b|"
                          r"\bfictitious\b|\bbusts? (the )?fake|\bno such (scheme|proposal|order|notification|provision|plan|decision|circular)\b|"
                          r"\bnot been issued\b|\bfake news\b|\bmisinformation\b|\bclarif(y|ies|ication)\b", re.I)
_REPORTED = re.compile(r"\b(media report|news report|reports? (said|claim|suggest)|rumou?rs?|viral|circulating|speculat\w+|purported|so-called|alleg\w+|"
                       r"hoax|fake|fictitious|fabricated|baseless)\b", re.I)

def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'\u201c\u201d\u2018\u2019.\u2026]", "", t or "")).strip().lower()

# Stance-scope checks (added with STANCEHARDEN). Each one only ever turns a stance into 'none'; none of them can create a stance.
_NEG_QUOTE = re.compile(r"\b(not approved|has not|have not|never|cancell?ed|withdrawn|rejected|denied|no longer|not applicable|yet to)\b", re.I)
_DENY_WORD = re.compile(r"\b(fake|false|misleading|baseless|hoax|fabricated|no such|not true|rumou?rs?)\b|फर्जी|झूठ|भ्रामक|నకిలీ|అబద్ధ|తప్పుడు", re.I)
_APPROVAL = re.compile(r"\b(approved|approves|sanctioned|notified|announced|launched|is real|is genuine|has been released)\b|मंजूरी|मंजूर|स्वीकृत", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?\u0964])\s+|\n")
_RESTRICT = re.compile(r"\b(only|except|provided that|subject to|limited to|restricted to|excluding|barring|other than|who (?:is an?|are))\b", re.I)

def _contradiction_scope_ok(claim: str, title: str, quote: str) -> bool:
    """A denial must deny THIS claim: same figures, same scheme names, not negated, not in the same sentence as an approval."""
    cn, qn = numbers(claim), numbers(quote)
    if cn and qn and not cn <= qn:
        return False                                  # 'Rs 2000 is fake' cannot refute 'Rs 5000'; neither can a 2019 denial refute a 2024 claim
    if not critical_words(claim) <= tokens(f"{title} {quote}"):
        return False                                  # 'Ayushman scheme ... is fake' cannot refute 'PM Kisan ...'
    for sent in _SENTENCE_END.split(quote or ""):
        for m in _DENY_WORD.finditer(sent):
            if _NEGATION.search(" ".join(sent[:m.start()].split()[-4:])):
                return False                          # 'is not fake', 'never false', 'no longer misleading'
            if _APPROVAL.search(sent):
                return False                          # 'approved ... no such thing': a sentence that both denies and approves
            if cn and not numbers(sent) <= cn:
                return False                          # 'Reports of Rs 2000 ... are misleading; the Rs 5000 scheme is real' (figures in the denial)
            if _denial_names_another_subject(sent, claim, title):
                return False                          # 'The Ayushman scheme ... is fake' names a subject the claim (and title) do not
    return True

_NAME_STOP = _GENERIC | {_stem(w) for w in "fact check unit pib news claim message".split()}

def _denial_names_another_subject(sentence: str, claim: str, title: str) -> bool:
    """Capitalised names inside a denial sentence (mid-sentence, as critical_words reads them) that the claim and title do not contain."""
    names = {_stem(w.lower()) for w in re.findall(r"(?<=[A-Za-z0-9,] )[A-Z][a-z]{2,}", sentence)}
    return bool(names - _NAME_STOP - tokens(claim) - tokens(title))

def _unmatched_restriction(claim: str, quote: str) -> bool:
    """True when the quote limits the claim ('only', 'who is a ...') and the claim does not contain the same limit."""
    cl = " ".join((claim or "").lower().split())
    for m in _RESTRICT.finditer(quote or ""):
        phrase = " ".join(m.group(1).lower().split())
        if not re.search(r"\b" + re.escape(phrase) + r"\b", cl):
            return True
    return False

def validate_stance(label: str, quote: str, claim: str, title: str, text: str) -> str:
    """Accept an LLM stance only if it is backed by a verbatim quote from the page that relates to the claim.
    - quote must appear verbatim in the page (kills hallucinated evidence)
    - quote must overlap the claim (kills 'related topic' calls)
    - CONFIRMS: quote must contain every number in the claim
    - CONTRADICTS: the page must itself be a debunk/denial (a page describing a real scheme can never refute)
    Anything failing a check becomes 'none' -> UNVERIFIED."""
    if label == "none":
        return "none"
    page = _norm(f"{title} {text}")
    # Models often shorten a long sentence with "..." / "…". Every piece must still appear word for word on the page
    # (each at least 12 characters), so nothing that is not on the page can be quoted.
    parts = [_norm(x) for x in re.split(r"\.{3,}|\u2026", quote or "")]
    parts = [x for x in parts if x]
    if not parts or any(len(x) < 12 or x not in page for x in parts):
        return "none"
    q = " ".join(parts)
    if has_injection(claim, title, text, quote):
        return "none"          # the forward or the page tries to instruct the judge: abstain rather than trust it
    if direction_conflict(claim, f"{title} {quote}"):
        return "none"          # 'increased' vs a page that says 'reduce' (and the reverse): neither confirms nor refutes
    if label == "contradicts" and (_NEGATION.search(claim) or _META.search(claim)):
        return "none"          # a negated claim, or one that merely reports a rumour/debunk, can agree with a debunk page: never FALSE
    if label == "contradicts" and not _contradiction_scope_ok(claim, title, quote):
        return "none"          # the denial is about other figures / another scheme / is itself negated or mixed with an approval
    if label in ("confirms", "mixed") and _NEG_QUOTE.search(quote) and not (_NEGATION.search(claim) or _NEG_QUOTE.search(claim)):
        return "none"          # 'has not approved that ... Rs 5000' is the opposite of a confirmation of a positive claim
    if label == "confirms" and _unmatched_restriction(claim, quote):
        return "none"          # 'every woman who is a cricketer' does not confirm 'every woman'
    # A denial ("This is fake; no such proposal exists.") gets its subject from the page title, so for CONTRADICTS the title
    # and quote together must relate to the claim. Confirmations / partial matches must be matched by the quote itself.
    if overlap(claim, f"{title} {quote}" if label == "contradicts" else quote) < 0.4:
        return "none"
    if label in ("confirms", "mixed") and not _META.search(claim) and (
            _DENIAL.search(title) or _PAGE_DEBUNK.search(f"{title} {text}") or _REPORTED.search(quote)):
        return "none"          # the page is a debunk, or the quote merely reports the rumour: it cannot back the claim
    if label == "confirms" and not numbers(claim) <= numbers(quote):
        return "none"
    if label == "confirms" and not critical_words(claim) <= tokens(quote):
        return "none"          # a swapped place/season/month/eligibility word ('Mumbai' for 'Delhi-NCR', 'only women') is not confirmed
    if label in ("confirms", "mixed") and subject_coverage(claim, quote) < 0.7:
        return "none"          # the quote must contain the claim's subject words (a Handloom Day page cannot back a Mango Day claim)
    if label == "contradicts" and subject_coverage(claim, f"{title} {quote}") < 0.6:
        return "none"
    if label == "mixed" and (overlap(claim, quote) < 0.6 or not numbers(claim) or not numbers(quote)):
        return "none"      # 'partial' drives MISLEADING: needs a strongly related quote with numbers on both sides
    if label == "contradicts" and not _DENIAL.search(f"{title} {quote}"):
        return "none"
    return label

def degraded_stance(claim: str, title: str, text: str, tier: str) -> str:
    """Safe fallback when no LLM is available: only a clear PIB debunk can contradict. Never TRUE, never MISLEADING."""
    st = heuristic_stance(claim, title, text, tier)
    return st if (st == "contradicts" and tier == "pib_debunk") else "none"

def judge(claim: str, ev, llm=None) -> str:
    if llm is not None:
        try:
            try:
                s = llm.stance(claim, ev.title, ev.text, tier=ev.tier)
            except TypeError:        # judges that do not take a tier (e.g. test fakes)
                s = llm.stance(claim, ev.title, ev.text)
            if s in ("contradicts", "confirms", "mixed", "none"):
                return s
        except Exception:
            pass  # bad key / network / rate limit: fall back to the conservative heuristic
    return degraded_stance(claim, ev.title, ev.text, ev.tier)
