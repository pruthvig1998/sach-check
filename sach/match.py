"""The instant MATCH layer and the human-escalation block.

Cascade: verdict cache -> MATCH (a professional fact-checker's or PIB's EXISTING published verdict) -> live check (sach/pipeline.py).
Who calls this: sach/pipeline.py (`run_match`, `build_match_trace`, card/overall helpers), sach/site.py (`match_panel`, `escalation_html`,
`CSS`), sach/report.py (`card_data`), sach/share.py and sach/telegram_bot.py (`escalation_lines`), sach/ledger.py rows (`ledger_fields`),
scripts/run_eval.py (layer table). Nothing existing serves the purpose: pipeline went straight from cache to live retrieval.
Reads: data/seed_debunks.json + data/pib_index.jsonl (via sach.index, local, no network) and, when GOOGLE_FACTCHECK_API_KEY is set,
the Google Fact Check Tools `claims:search` client in sach/factcheck_api.py (4 s timeout; any failure = no match). Writes nothing.

Principles (tested in tests/test_match.py):
 * Attribution is never stripped: a matched verdict is THEIR verdict. Every surface carries checker, review date and review URL.
 * Sach's own verdict rules are untouched. A match never goes through verdict.decide(); its `verdict` is only the mapped category of the
   checker's rating (FALSE / MISLEADING / TRUE, never UNVERIFIED) and the result has layer "match" and a separate `match` object.
 * A wrong match is an overclaim, so matching is conservative; when in doubt the claim falls through to the live layer.

Human tiplines (escalation on UNVERIFIED results). Each number was verified on the outlet's OWN official website on 2026-11-13 (plain
curl, honest User-Agent):
  * PIB Fact Check  +91 87997 11259   https://factcheck.pib.gov.in/ (constants live in sach/report.py)
  * BOOM            +91 77009 06588   https://www.boomlive.in/  (WhatsApp links api.whatsapp.com/send?phone=917700906588 in the site header/footer)
  * Vishvas News    +91 95992 99372   https://www.vishvasnews.com/contact-us/  ("Vishvas News Whatsapp Tipline (+91 9599299372)")
  * Newschecker     +91 99994 99044   https://newschecker.in/  (header link https://wa.me/919999499044)
  DROPPED: Factly +91 92470 52470. factly.in answers automated requests with a Cloudflare challenge (HTTP 403), which we do not bypass, and the
  number could not be confirmed from Factly's own site, WhatsApp channel or IFCN profile (the IFCN page is script-rendered). Add it back only
  after someone confirms it by hand on factly.in.
  NOT INCLUDED: Alt News (its IFCN signatory status expired).
Vishvas News also lists 92052 70923 as a general contact number on the same page; that is not the tipline and is not used.
"""
from __future__ import annotations
import html, os, re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timezone
from urllib.parse import quote
from . import index as pib_index
from . import pibposts
from .fetch import is_factchecker, host_of
from .i18n import EMOJI, INCOMPLETE_ESC_NOTE, incomplete, text_lang, tr
from .models import Claim, ClaimVerdict, FALSE, MISLEADING, TRUE, TIER_PIB, TIER_FACTCHECKER
from .report import PIB_WHATSAPP_DIGITS, PIB_WHATSAPP_DISPLAY, PIB_PORTAL, _clean, _clip
from .stance import (_NEGATION, _META, _GENERIC, _STOP, _stem, critical_words, direction_conflict, distinctive, has_injection,
                     numbers, subject_coverage, tokens)

# ------------------------------------------------------------------------------------------------ thresholds (all in one place)
COVERAGE_MIN = 0.75          # two-way: share of each side's distinctive words found in the other
JACCARD_MIN = 0.67           # extra guard: one swapped word in a short claim (Delhi -> Mumbai) gives 0.6 and fails
MIN_DISTINCTIVE = 2          # each side needs at least two distinctive words, or "similar" means nothing
API_TIMEOUT_S = 4.0          # Fact Check Tools call
TRANSLATE_TIMEOUT_S = 10.0   # only for non-English forwards
DEFAULT_MAX_AGE_YEARS = 5.0  # third-party reviews older than this are not used (PIB is exempt)

PIB_NAME = "PIB Fact Check"
PIB_X_NAME = "PIB Fact Check (on X)"        # a debunk PIB published as a post on X (data/pib_posts.jsonl), never a pib.gov.in release
PIB_NAMES = (PIB_NAME, PIB_X_NAME)
POST_MIN_JACCARD = 0.9    # a post's claim is short and specific, so the wording must be (near) identical on top of every check_pair rule
PIB_HOSTS = ("pib.gov.in", "factcheck.pib.gov.in")

def enabled() -> bool:
    return os.environ.get("SACH_NO_MATCH") != "1"

def max_age_years() -> float:
    try:
        return float(os.environ.get("SACH_MATCH_MAX_AGE_YEARS", DEFAULT_MAX_AGE_YEARS))
    except ValueError:
        return DEFAULT_MAX_AGE_YEARS

# ------------------------------------------------------------------------------------------------ rating text -> category
# Explicit table, compared after lower-casing and stripping punctuation. Anything not listed means NO match (never a guess).
RATING_MAP = {
    # FALSE
    "false": FALSE, "fake": FALSE, "fabricated": FALSE, "hoax": FALSE, "incorrect": FALSE, "untrue": FALSE, "not true": FALSE,
    "baseless": FALSE, "fake news": FALSE, "false claim": FALSE, "fake claim": FALSE, "totally false": FALSE, "completely false": FALSE,
    "fabricated content": FALSE, "pants on fire": FALSE, "wrong": FALSE, "false news": FALSE, "no evidence": None,
    # MISLEADING (partly right, stripped of context, or not a literal factual claim)
    "misleading": MISLEADING, "partly false": MISLEADING, "partially false": MISLEADING, "mostly false": MISLEADING,
    "half true": MISLEADING, "partly true": MISLEADING, "partially true": MISLEADING, "missing context": MISLEADING,
    "out of context": MISLEADING, "false context": MISLEADING, "misleading content": MISLEADING, "satire": MISLEADING,
    "satirical": MISLEADING, "altered": MISLEADING, "manipulated": MISLEADING, "edited": MISLEADING, "doctored": MISLEADING,
    "misattributed": MISLEADING, "old video": MISLEADING, "old image": MISLEADING,
    # TRUE
    "true": TRUE, "correct": TRUE, "accurate": TRUE, "factual": TRUE, "true claim": TRUE, "mostly true": None,
}
RATING_MAP = {k: v for k, v in RATING_MAP.items() if v}      # None entries above are documentation: they stay unmapped

def map_rating(text: str) -> str | None:
    t = re.sub(r"[^a-z ]+", " ", str(text or "").lower())
    return RATING_MAP.get(re.sub(r"\s+", " ", t).strip())

# ------------------------------------------------------------------------------------------------ same-claim test
_NUMWORDS = set("""one two three four five six seven eight nine ten eleven twelve fifteen twenty thirty forty fifty hundred thousand lakh lakhs
crore crores million billion double triple half zero""".split())
_NOISE = {_stem(w) for w in "claim fact check viral breaking video image photo post message news forward whatsapp watch alert".split()}

def _numwords(t: str) -> set:
    return {w for w in re.findall(r"[a-z]+", t.lower()) if w in _NUMWORDS}

def _proper(t: str) -> set:
    """Capitalised words anywhere (names, places, schemes, ALL-CAPS acronyms), as stems."""
    return {_stem(w.lower()) for w in re.findall(r"\b[A-Z][A-Za-z]{2,}\b", t)} - _GENERIC - _NOISE - {_stem(w) for w in _STOP}

def check_pair(claim: str, reviewed: str, page_text: str = "") -> dict:
    """Every check that must hold for `reviewed` (the claim a fact-checker reviewed) to be the same claim as `claim`. Pure, English-first.
    Returns {"ok": bool, "checks": {name: bool}, "similarity": {...numbers}}."""
    dc, dr = distinctive(claim), distinctive(reviewed)
    cov_c = subject_coverage(claim, reviewed) if dc else 0.0          # claim's distinctive words found in the reviewed claim
    cov_r = subject_coverage(reviewed, claim) if dr else 0.0          # and the reverse
    jac = len(dc & dr) / len(dc | dr) if (dc | dr) else 0.0
    tc, tr_ = tokens(claim), tokens(reviewed)
    checks = {
        "enough_subject_words": len(dc) >= MIN_DISTINCTIVE and len(dr) >= MIN_DISTINCTIVE,
        "coverage_claim_in_reviewed": cov_c >= COVERAGE_MIN,
        "coverage_reviewed_in_claim": cov_r >= COVERAGE_MIN,
        "subject_overlap": jac >= JACCARD_MIN,
        # Equal number sets. A PIB headline usually carries no numbers ("No reduction in retirement age"): then every number in the
        # claim must appear in the PIB release text itself, so "to 50" matches a debunk of "to 50" but "to 58" does not.
        "numbers_equal": numbers(claim) == numbers(reviewed) or (not numbers(reviewed) and bool(page_text)
                                                                 and bool(numbers(claim)) and numbers(claim) <= numbers(page_text)),
        "number_words_equal": _numwords(claim) == _numwords(reviewed),
        "no_direction_conflict": not direction_conflict(claim, reviewed),
        "negation_agrees": bool(_NEGATION.search(claim)) == bool(_NEGATION.search(reviewed)),
        "qualifiers_agree": critical_words(claim) <= tr_ and critical_words(reviewed) <= tc,
        "names_places_agree": _proper(claim) <= tr_ and _proper(reviewed) <= tc,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "similarity": {"coverage_claim_in_reviewed": round(cov_c, 3), "coverage_reviewed_in_claim": round(cov_r, 3), "jaccard": round(jac, 3)}}

# ------------------------------------------------------------------------------------------------ PIB archive (local)
_PIB_TAIL = re.compile(r"[,;:\-–—]?\s*PIB[\s’']*s?\s*Fact[\s-]?Check\b.*$", re.I)
_PIB_HEAD = re.compile(r"^\s*(clarification\s+(regarding|on|about)|claim\s+(in|on|that)\s+(a\s+)?(viral\s+)?(video|message|post|image)?\s*(that|about|regarding)?|"
                       r"(misleading|fake|false)\s+(whatsapp\s+|viral\s+|social media\s+)?(message|post|video|news|claim)?\s*(pertaining to|regarding|about|on|that)?)\s*", re.I)
_PIB_TAIL2 = re.compile(r"\s+(is|are|was|were)\s+(completely\s+|totally\s+)?(fake|false|misleading|fabricated|baseless)\s*$", re.I)
_PIB_WORDS = re.compile(r"\b(fake|fictitious|false|fabricated|misleading|baseless|in social media|on social media|whatsapp|viral)\b", re.I)
_PIB_LEAD_NO = re.compile(r"^\s*no\s+", re.I)
_STRICT = re.compile(r"\b(fake|false|misleading|baseless|fabricated|hoax|busts?|no such|not true|fictitious)\b", re.I)
_MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}

def pib_claim_from_title(title: str) -> str:
    """The claim a PIB debunk headline refutes, with the debunk framing removed. 'No reduction in retirement age..., PIB Fact Check busts
    fake news' -> 'reduction in retirement age...': a leading 'No' is the denial, not part of the claim."""
    t = _PIB_TAIL.sub("", str(title or "")).strip(" ,;:-")
    t = _PIB_HEAD.sub("", t)
    t = _PIB_TAIL2.sub("", t)
    t = _PIB_LEAD_NO.sub("", t)
    t = _PIB_WORDS.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" ,;:-")

def _pib_date(posted_on: str) -> str:
    m = re.match(r"\s*(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\s+(\d{4})", str(posted_on or ""))
    if not m or m.group(2).upper() not in _MONTHS:
        return ""
    try:
        return date(int(m.group(3)), _MONTHS[m.group(2).upper()], int(m.group(1))).isoformat()
    except ValueError:
        return ""

def load_pib_records() -> list[dict]:
    """Debunk records from the local PIB index (+ seed titles that the index dates). Only records with a strict debunk word in the title,
    a PIB URL and a release date: a record without a date cannot be attributed properly, so it is not used."""
    rows, seen = [], set()
    for r in pib_index.load():
        if not r.get("debunk"):
            continue
        title, prid = str(r.get("title") or ""), str(r.get("prid") or "")
        d = _pib_date(r.get("posted_on", ""))
        if prid in seen or not d or not _STRICT.search(title) or not prid.isdigit():
            continue
        seen.add(prid)
        rows.append({"title": title, "review_date": d, "url": f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}", "prid": prid,
                     "text": str(r.get("excerpt") or "")})
    for r in pibposts.load():                  # PIB Fact Check posts on X (separate file; every record validated by sach.pibposts.valid)
        rows.append({"title": r["claim"], "claim": r["claim"], "review_date": r["date"], "url": r["url"], "prid": "", "post_id": r["id"],
                     "kind": "post", "verdict": r["verdict"], "text": ""})      # no page_text: numbers must match exactly
    return rows

# ------------------------------------------------------------------------------------------------ candidates
def _is_pib_url(url: str) -> bool:
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in PIB_HOSTS)

def _parse_day(s: str):
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None

def _fresh(review_date: str, today: date, is_pib: bool) -> bool:
    d = _parse_day(review_date)
    if d is None or d > today:
        return False
    return is_pib or (today - d).days <= max_age_years() * 365.25

def _pib_candidates(claim_texts: list[str], records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        post = r.get("kind") == "post"
        reviewed = r["claim"] if post else pib_claim_from_title(r["title"])       # a post's claim is already PIB's own wording
        best = None
        for ct in claim_texts:
            res = check_pair(ct, reviewed, r.get("text", ""))
            if post and res["similarity"]["jaccard"] < POST_MIN_JACCARD:
                continue                    # tighter than check_pair for posts: one different word ("tablets", "PM") must fall through to the live layer
            if res["ok"] and (best is None or res["similarity"]["jaccard"] > best[1]["similarity"]["jaccard"]):
                best = (ct, res)
        if best:
            if post:
                out.append(_cand(PIB_X_NAME, "https://x.com/PIBFactCheck", r["url"], r["review_date"],
                                 "Misleading" if r["verdict"] == "MISLEADING" else "Fake", r["title"], "pib_x_post", best[0], reviewed, best[1]))
                continue
            rating = "Misleading" if re.search(r"\bmisleading\b", r["title"], re.I) else "Fake"
            out.append(_cand(PIB_NAME, "https://factcheck.pib.gov.in/", r["url"], r["review_date"], rating, r["title"], "pib_archive",
                             best[0], reviewed, best[1]))
    return out

def _cand(checker, checker_url, review_url, review_date, rating, reviewed_claim, source, matched_on, matched_text, res) -> dict:
    return {"checker": checker, "checker_url": checker_url, "review_url": review_url, "review_date": review_date, "rating_text": rating,
            "reviewed_claim": reviewed_claim, "source": source, "similarity": res["similarity"]["jaccard"],
            "category": map_rating(rating), "_checks": res["checks"], "_sim": res["similarity"], "_matched_on": matched_on, "_matched_text": matched_text}

def _api_candidates(claim_texts: list[str], reviews: list[dict], today: date) -> list[dict]:
    out, seen = [], set()
    for rv in reviews:
        url = rv.get("url", "")
        pib = _is_pib_url(url)
        if not url.startswith("https://") or url in seen or not (pib or is_factchecker(url)):
            continue                                                    # unverified publisher: never used
        category = map_rating(rv.get("rating"))
        if category is None or not _fresh(rv.get("review_date", ""), today, pib):
            continue                                                    # unmapped rating, or too old / undated
        reviewed = _clean(rv.get("reviewed_claim") or rv.get("title") or "")
        if not reviewed:
            continue
        best = None
        for ct in claim_texts:
            res = check_pair(ct, reviewed)
            if res["ok"] and (best is None or res["similarity"]["jaccard"] > best[1]["similarity"]["jaccard"]):
                best = (ct, res)
        if not best:
            continue
        seen.add(url)
        site = host_of(url)
        name = PIB_NAME if pib else (_clean(rv.get("publisher")) or site)
        curl = "https://factcheck.pib.gov.in/" if pib else f"https://{host_of(rv.get('site') or '') or site}/"
        out.append(_cand(name, curl, url, rv["review_date"], _clean(rv.get("rating")), reviewed, "factcheck_tools", best[0], reviewed, best[1]))
    return out

def pick_best(cands: list[dict]) -> dict | None:
    """Prefer PIB, then the most recent review, then the closest wording."""
    if not cands:
        return None
    return sorted(cands, key=lambda c: (c["checker"] not in PIB_NAMES, _neg_day(c["review_date"]), -c["similarity"]))[0]

def _neg_day(s: str) -> int:
    d = _parse_day(s)
    return -(d.toordinal()) if d else 0

# ------------------------------------------------------------------------------------------------ the matcher
class Matcher:
    """`pib_records`: list from load_pib_records() (None = load lazily from the local index). `fc`: object with
    claim_reviews(query, language) (None = built from GOOGLE_FACTCHECK_API_KEY on first use; no key = API step skipped)."""
    def __init__(self, pib_records=None, fc=None, today: date | None = None):
        self._pib, self._fc, self._today = pib_records, fc, today

    def _records(self):
        if self._pib is None:
            self._pib = load_pib_records()
        return self._pib

    def _client(self):
        if self._fc is None:
            if not os.environ.get("GOOGLE_FACTCHECK_API_KEY"):
                return None
            from .factcheck_api import FactCheckToolsRetriever
            self._fc = FactCheckToolsRetriever(timeout=API_TIMEOUT_S)
        return self._fc

    def match(self, original: str, english: str = "") -> dict | None:
        """-> match dict (with private `_checks` evidence keys) or None. Never raises."""
        try:
            return self._match(original, english)
        except Exception:
            return None

    def _match(self, original: str, english: str):
        if has_injection(original, english) or _META.search(f"{original} {english}"):
            return None                       # instructions aimed at a judge, or a claim ABOUT fake news: never matched
        texts = [t for t in dict.fromkeys([english, original]) if t and t.strip()]
        today = self._today or datetime.now(timezone.utc).date()
        if english or original.isascii():
            hit = pick_best(_pib_candidates(texts, self._records()))
            if hit:
                return hit
        fc = self._client()
        if fc is None:
            return None
        queries = [(q, "en" if q == english and english != original else None) for q in texts]
        with ThreadPoolExecutor(max_workers=len(queries)) as ex:
            futs = [ex.submit(fc.claim_reviews, q, lang) for q, lang in queries]
            done, _ = wait(futs, timeout=API_TIMEOUT_S + 0.5)
        reviews = []
        for f in futs:
            if f in done:
                try:
                    reviews += f.result() or []
                except Exception:
                    pass
        return pick_best(_api_candidates(texts, reviews, today))

_default: Matcher | None = None

def default_matcher() -> Matcher:
    global _default
    if _default is None:
        _default = Matcher()
    return _default

def run_match(claims: list[Claim], lang: str, llm, matcher: Matcher | None = None, info: list | None = None) -> list[tuple]:
    """-> [(match dict or None, english text)] per claim, in order. Claims run in parallel; whatever has not finished by the deadline
    is simply not matched (it goes to the live layer). Never raises. `info` (optional, one dict per claim) is filled with
    {"translator", "detected"} so the pipeline can show who translated and refine the language."""
    m = matcher or default_matcher()
    n = len(claims)
    out = [(None, "")] * n

    def one(c: Claim, i: int = -1):
        english = ""
        if lang != "en":
            from . import gtranslate               # Google Translate first (when keyed), the LLM as the automatic fallback
            tr = gtranslate.translate_claim(c.text, lang, llm)
            english = tr["text"]
            if info is not None and 0 <= i < len(info):
                info[i].update(translator=tr["translator"], detected=tr["detected"])
        if english == c.text:
            english = ""
        return m.match(c.text, english), english

    ex = ThreadPoolExecutor(max_workers=max(1, min(3, n)))
    try:
        futs = [ex.submit(one, c, i) for i, c in enumerate(claims)]
        wait(futs, timeout=API_TIMEOUT_S + 1.0 + (TRANSLATE_TIMEOUT_S if lang != "en" and llm is not None else 0))
        for i, f in enumerate(futs):
            if f.done():
                try:
                    out[i] = f.result()
                except Exception:
                    pass
    finally:
        ex.shutdown(wait=False)
    return out

# ------------------------------------------------------------------------------------------------ building the result pieces
def public_match(c: dict) -> dict:
    """The match object that goes into results, the cache, the ledger and the API: no private evidence keys."""
    return {k: v for k, v in c.items() if not k.startswith("_")}

def verdict_from_match(claim: Claim, c: dict, english: str, now_iso: str, translator: str = "") -> ClaimVerdict:
    pib = c["checker"] in PIB_NAMES
    cite = {"source": c["checker"], "url": c["review_url"], "tier": TIER_PIB if pib else TIER_FACTCHECKER,
            "date_accessed": c["review_date"], "fetched_at": now_iso}
    cites = ", ".join(k for k, v in c["_checks"].items() if v)
    trace = {"layer": "MATCH", "searched_as": english or claim.text,
             "sources": [{"source": c["checker"], "url": c["review_url"], "tier": cite["tier"], "fetched_at": now_iso,
                          "title": c["reviewed_claim"], "stance": "none"}],
             "rule": "matched_fact_check", "rule_text": "", "match": public_match(c),
             "match_checks": c["_checks"], "match_similarity": c["_sim"], "matched_on": c["_matched_on"], "matched_text": c["_matched_text"],
             "match_note": f"Checks passed: {cites}."}
    from .models import RULE_TEXT
    trace["rule_text"] = RULE_TEXT["matched_fact_check"]
    if translator:
        trace["translator"] = translator
    return ClaimVerdict(claim, c["category"], "matched_fact_check", [cite], english=english, trace=trace, layer="match", match=public_match(c))

def fmt_date(iso: str) -> str:
    d = _parse_day(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}" if d else str(iso)

# i18n: NOT NATIVE-REVIEWED (hi, te). Languages without an entry fall back to English through tr().
HEAD = {"en": "Already fact-checked by {checker}",
        "hi": "{checker} पहले ही इसकी जाँच कर चुका है",                      # NOT NATIVE-REVIEWED
        "te": "{checker} దీనిని ఇప్పటికే తనిఖీ చేసింది"}                      # NOT NATIVE-REVIEWED
LINE = {"en": 'Checked by {checker} on {date}: rated "{rating}"',
        "hi": '{checker} ने {date} को जाँचा: रेटिंग "{rating}"',                # NOT NATIVE-REVIEWED
        "te": '{checker} {date} న తనిఖీ చేసింది: రేటింగ్ "{rating}"'}          # NOT NATIVE-REVIEWED
NOTE = {"en": "This is their published fact-check, matched to your message. Sach did not run its own check.",
        "hi": "यह उनकी प्रकाशित फ़ैक्ट-चेक है, जो आपके संदेश से मिलाई गई है। Sach ने अपनी जाँच नहीं चलाई।",      # NOT NATIVE-REVIEWED
        "te": "ఇది వారి ప్రచురించిన ఫ్యాక్ట్-చెక్, మీ సందేశానికి సరిపోల్చబడింది. Sach తన సొంత తనిఖీ చేయలేదు."}   # NOT NATIVE-REVIEWED
REVIEW_LBL = {"en": "Their review", "hi": "उनकी समीक्षा", "te": "వారి సమీక్ష"}                              # NOT NATIVE-REVIEWED
CLAIM_LBL = {"en": "Claim", "hi": "दावा", "te": "ప్రకటన"}                                                  # NOT NATIVE-REVIEWED
PART_HEAD = {"en": "Part of this message was already fact-checked by others",
             "hi": "इस संदेश के एक हिस्से की जाँच पहले ही दूसरों ने की है",                                  # NOT NATIVE-REVIEWED
             "te": "ఈ సందేశంలో కొంత భాగాన్ని ఇతరులు ఇప్పటికే తనిఖీ చేశారు"}                                 # NOT NATIVE-REVIEWED
REST_HEAD = {"en": "Sach's own check of the rest:", "hi": "बाकी हिस्से की Sach की अपनी जाँच:", "te": "మిగిలిన భాగానికి Sach సొంత తనిఖీ:"}   # NOT NATIVE-REVIEWED

def _block(v: ClaimVerdict, lang: str, with_claim: bool) -> list[str]:
    m = v.match
    lines = []
    if with_claim:
        lines.append(f'{tr(CLAIM_LBL, lang)}: "{_clip(_clean(v.claim.text), 140)}"')
    lines.append(tr(LINE, lang).format(checker=m["checker"], date=fmt_date(m["review_date"]), rating=m["rating_text"]))
    lines.append(f"{tr(REVIEW_LBL, lang)}: {m['review_url']}")
    return lines

def render_match_card(results: list[ClaimVerdict], overall: str, lang: str, live_card: str = "") -> str:
    """Forwardable card for a result with at least one matched claim. Names the checker, date and review link for every matched
    claim; Sach's own verdict wording is never used for them. `live_card` is the normal card for the unmatched claims (mixed result)."""
    matched = [v for v in results if v.layer == "match"]
    mixed = len(matched) < len(results)
    if not mixed and len(matched) == 1:
        v = matched[0]
        lines = [f"{EMOJI[v.verdict]} {tr(HEAD, lang).format(checker=v.match['checker'])}"] + _block(v, lang, False) + [tr(NOTE, lang)]
        return "\n".join(lines)
    head = tr(PART_HEAD, lang) if mixed else tr(HEAD, lang).format(checker=", ".join(dict.fromkeys(v.match["checker"] for v in matched)))
    lines = [f"{EMOJI[overall]} {head}"]
    for v in matched:
        lines += [""] + _block(v, lang, True)
    lines += ["", tr(NOTE, lang)]
    if mixed and live_card:
        lines += ["", tr(REST_HEAD, lang), live_card]
    return "\n".join(lines)

def overall_match_rule(results: list[ClaimVerdict], overall: str) -> str:
    matched = [v for v in results if v.layer == "match"]
    who = ", ".join(dict.fromkeys(f"{v.match['checker']} ({v.match['rating_text']})" for v in matched))
    if len(matched) == len(results):
        return f"Every claim matched a published fact-check ({who}). Sach did not run its own check; the overall result follows their ratings."
    return (f"{len(matched)} of {len(results)} claims matched a published fact-check ({who}); Sach checked the rest itself. "
            f"The overall result combines both, worst case first.")

def top_match(results: list[ClaimVerdict], overall: str) -> dict:
    """Attribution for the overall verdict: the match of the DRIVER claim (the first claim whose verdict is the overall one, else the
    first claim, as report.driver_index). {} when that driver claim is not a matched claim: never another claim's rating."""
    if not results:
        return {}
    driver = next((v for v in results if v.verdict == overall), results[0])
    return driver.match if driver.layer == "match" and driver.match else {}

def ledger_fields(v: ClaimVerdict) -> dict:
    if v.layer != "match":
        return {"layer": "live"}
    m = v.match
    return {"layer": "match", "match": {k: m[k] for k in ("checker", "checker_url", "review_url", "review_date", "rating_text", "reviewed_claim", "source", "similarity") if k in m}}

# ------------------------------------------------------------------------------------------------ human escalation
TIPLINES = (
    ("BOOM", "+91 77009 06588", "917700906588", "https://www.boomlive.in/"),
    ("Vishvas News", "+91 95992 99372", "919599299372", "https://www.vishvasnews.com/contact-us/"),
    ("Newschecker", "+91 99994 99044", "919999499044", "https://newschecker.in/"),
)
ESC_HEAD = {"en": "Ask a human fact-checker", "hi": "किसी फ़ैक्ट-चेकर से पूछें", "te": "ఫ్యాక్ట్-చెకర్‌ను అడగండి"}     # NOT NATIVE-REVIEWED
ESC_NOTE = {"en": "We found no official source for this. Tap a name to open WhatsApp with your question filled in, then send it yourself. Sach sends nothing.",
            "hi": "हमें इसके लिए कोई सरकारी स्रोत नहीं मिला। किसी नाम पर टैप करें, WhatsApp आपके सवाल के साथ खुलेगा; भेजना आपको खुद है। Sach कुछ नहीं भेजता।",   # NOT NATIVE-REVIEWED
            "te": "దీనికి అధికారిక ఆధారం దొరకలేదు. ఒక పేరును నొక్కితే WhatsApp మీ ప్రశ్నతో తెరుచుకుంటుంది; మీరే పంపండి. Sach ఏమీ పంపదు."}   # NOT NATIVE-REVIEWED

def escalation_text(claim: str, site: str, incomplete: bool = False) -> str:
    head = f"Please fact-check this message: {_clip(_clean(claim), 600).rstrip(' .!?')}."
    if incomplete:            # the check did not finish: never say that no official source was found
        return f"{head} Checked on Sach ({site}). Sach could not finish checking this."
    return f"{head} Checked on Sach ({site}) and no official source was found."

def escalation_options(claim: str, site: str, incomplete: bool = False) -> list[dict]:
    """PIB Fact Check first, then each verified independent tipline. Plain wa.me links with the question prefilled; Sach sends nothing."""
    body = quote(escalation_text(claim, site, incomplete), safe="")
    opts = [{"name": PIB_NAME, "number": PIB_WHATSAPP_DISPLAY, "url": f"https://wa.me/{PIB_WHATSAPP_DIGITS}?text={body}", "source": PIB_PORTAL}]
    for name, display, digits, src in TIPLINES:
        opts.append({"name": name, "number": display, "url": f"https://wa.me/{digits}?text={body}", "source": src})
    return opts

def escalation_claim(res: dict) -> str:
    cs = [c["claim"]["text"] for c in (res.get("claims") or []) if c.get("verdict") == "UNVERIFIED" and c.get("layer", "live") != "match"]
    return " ".join(cs) or " ".join(c["claim"]["text"] for c in (res.get("claims") or []))

def escalated(res: dict) -> bool:
    return (res.get("trace") or {}).get("layer") == "ESCALATED" and res.get("verdict") == "UNVERIFIED" and not res.get("no_claims")

def escalation_html(res: dict, site: str) -> str:
    if not escalated(res):
        return ""
    lang = res.get("language", "en")
    e = html.escape
    inc = incomplete(res)
    items = "".join(f'<li><a class="btn ghost esc-btn" href="{e(o["url"])}" target="_blank" rel="noopener">'
                    f'<b>{e(o["name"])}</b><span>{e(o["number"])}</span></a></li>'
                    for o in escalation_options(escalation_claim(res), site, inc))
    note = tr(INCOMPLETE_ESC_NOTE, text_lang(lang)) if inc else tr(ESC_NOTE, lang)
    return (f'<section class="escalate" id="escalate" aria-labelledby="esc-h"><h3 id="esc-h">{e(tr(ESC_HEAD, lang))}</h3>'
            f'<p class="note">{e(note)}</p><ul class="esc-list">{items}</ul></section>')

def escalation_lines(res: dict, site: str) -> str:
    """Plain text for Telegram: name, number and the prefilled WhatsApp link."""
    if not escalated(res):
        return ""
    lang = res.get("language", "en")
    rows = [f"- {o['name']} ({o['number']}): {o['url']}"
            for o in escalation_options(escalation_claim(res), site, incomplete(res))]
    return tr(ESC_HEAD, lang) + ":\n" + "\n".join(rows)

# ------------------------------------------------------------------------------------------------ result page pieces
RUN_LIVE = {"en": "Run Sach's own check anyway", "hi": "फिर भी Sach की अपनी जाँच चलाएँ", "te": "అయినా Sach సొంత తనిఖీ చేయండి"}   # NOT NATIVE-REVIEWED
CSS = """
.matchbox{margin:18px 0 0;border:2px solid var(--rule);border-left:8px solid var(--ink);border-radius:4px;background:var(--card);padding:12px 14px}
.matchbox h3{font-family:var(--serif);margin:0 0 6px;font-size:20px;line-height:1.3}.matchbox p{margin:6px 0}.matchbox .by{font-weight:700}
.matchbox blockquote{margin:6px 0;padding:0 0 0 10px;border-left:3px solid var(--rule)}.matchbox .runlive{margin:12px 0 0}
.matchbox .runlive .btn{min-height:44px;display:inline-flex;align-items:center}
.stampby{margin:8px 0 0;font-size:14px;font-weight:700;max-width:260px}
.escalate{margin:20px 0 0;border:2px solid var(--rule);border-radius:4px;background:var(--card);padding:12px 14px}
.escalate h3{font-family:var(--serif);margin:0 0 4px;font-size:20px}
.esc-list{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:8px}.esc-btn{width:100%;min-height:48px;display:flex!important;justify-content:space-between;align-items:center;gap:10px;text-align:left;padding:8px 12px;box-sizing:border-box}
.esc-btn span{font-family:var(--mono);font-size:14px;white-space:nowrap}
@media(min-width:700px){.esc-list{grid-template-columns:1fr 1fr}}
"""

def matched_claims(res: dict) -> list[dict]:
    return [c for c in (res.get("claims") or []) if c.get("layer") == "match" and c.get("match")]

def match_panel(res: dict, text: str = "", lang_choice: str = "auto") -> str:
    """HTML box naming the checker for every matched claim, with the reviewed claim and the review link, and the 'run Sach's own check
    anyway' button (a plain POST form: works without JavaScript)."""
    ms = matched_claims(res)
    if not ms:
        return ""
    e, lang = html.escape, res.get("language", "en")
    parts = []
    for c in ms:
        m = c["match"]
        parts.append(f'<p class="by">{e(tr(LINE, lang).format(checker=m["checker"], date=fmt_date(m["review_date"]), rating=m["rating_text"]))}</p>'
                     f'<p class="note">What they checked:</p><blockquote>{e(m["reviewed_claim"])}</blockquote>'
                     f'<p><a href="{e(m["review_url"])}" rel="noopener">{e(tr(REVIEW_LBL, lang))}: {e(m["checker"])}</a></p>')
    btn = ""
    if text:
        btn = (f'<form class="runlive" method="post" action="/#result"><input type="hidden" name="text" value="{e(text)}">'
               f'<input type="hidden" name="lang" value="{e(lang_choice)}"><input type="hidden" name="force_live" value="1">'
               f'<button class="btn ghost" type="submit">{e(tr(RUN_LIVE, lang))}</button></form>')
    return (f'<div class="matchbox" id="matchbox" role="note"><h3>{e(tr(PART_HEAD if len(ms) < len(res["claims"]) else {"en": "A published fact-check matches this", "hi": "प्रकाशित फ़ैक्ट-चेक इससे मेल खाती है", "te": "ప్రచురించిన ఫ్యాక్ట్-చెక్ దీనికి సరిపోతుంది"}, lang))}</h3>'
            f'{"".join(parts)}<p class="note">{e(tr(NOTE, lang))}</p>{btn}</div>')
