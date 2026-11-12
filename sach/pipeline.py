from __future__ import annotations
import os, time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout, wait
from . import ledger
from .card import render_card
from .extract import clean_text, extract_claims
from .i18n import LABEL, NOCLAIM, NOCLAIM_LABEL
from .lang import detect_language
from .models import Claim, ClaimVerdict, UNVERIFIED
from .stance import judge
from .verdict import decide, aggregate

# Hard wall-clock caps. Socket timeouts are per-read, and a trickling server can hang a thread forever.
RETRIEVE_DEADLINE_S = 30
JUDGE_DEADLINE_S = 30
BUDGET_S = float(os.environ.get("SACH_BUDGET_S", 48))   # whole check must finish inside Vercel's 60 s limit
MAX_CLAIMS = 5
PARALLEL_CLAIMS = 3

def _run_with_deadline(fn, secs, default):
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(fn).result(timeout=secs)
    except (_Timeout, Exception):
        return default
    finally:
        ex.shutdown(wait=False)      # abandon a hung thread instead of blocking on it

def _check_claim(claim: Claim, lang: str, retrievers, llm, deadline: float) -> ClaimVerdict:
    left = lambda cap: max(0.3, min(cap, deadline - time.monotonic()))
    q = claim.text                                      # text used for searching + judging
    if lang != "en" and llm is not None and hasattr(llm, "translate"):
        q = _run_with_deadline(lambda: llm.translate(claim.text), left(15), "") or claim.text   # PIB pages are mostly English
    evidence = []
    for r in retrievers:
        evidence += _run_with_deadline(lambda r=r: r.search(q), left(RETRIEVE_DEADLINE_S), [])
    evidence = evidence[:8]
    ex = ThreadPoolExecutor(max_workers=8)              # LLM calls are slow; judge sources in parallel
    futs = [ex.submit(judge, q, e, llm) for e in evidence]
    wait(futs, timeout=left(JUDGE_DEADLINE_S))
    for e, f in zip(evidence, futs):
        try:
            e.stance = f.result(timeout=0) if f.done() else "none"
        except Exception:
            e.stance = "none"                           # hung/failed judge call -> no stance -> UNVERIFIED, never a guess
    ex.shutdown(wait=False)
    v = decide(claim, evidence)
    v.english = q if q != claim.text else ""
    return v

def check_forward(text: str, retrievers, llm=None, log=True, reply_lang: str | None = None) -> dict:
    """reply_lang: 'en' | 'hi' | 'te' | 'tl' to force the reply language; None/'auto' matches the forward.
    The INPUT language always drives translation and search; only the reply changes."""
    text = clean_text(text)
    lang = detect_language(text)                                   # input language
    out_lang = reply_lang if reply_lang in LABEL else lang          # reply language
    claims = extract_claims(text, max_claims=MAX_CLAIMS)
    if not claims:        # greeting, emoji, bare URL, numbers: nothing checkable. Say so instead of implying a search failed.
        out = {"language": out_lang, "input_language": lang, "verdict": "UNVERIFIED", "no_claims": True, "claims": [],
               "checked_at": ledger.now(), "card": f"{NOCLAIM_LABEL[out_lang]}\n{NOCLAIM[out_lang]}"}
        if out_lang != "en":
            out["card_en"] = f"{NOCLAIM_LABEL['en']}\n{NOCLAIM['en']}"
        return out
    fails_before = getattr(llm, "failures", 0)
    deadline = time.monotonic() + BUDGET_S
    ex = ThreadPoolExecutor(max_workers=PARALLEL_CLAIMS)
    futs = [ex.submit(_check_claim, c, lang, retrievers, llm, deadline) for c in claims]
    results: list[ClaimVerdict] = []
    for c, f in zip(claims, futs):
        try:
            results.append(f.result(timeout=max(0.3, deadline - time.monotonic() + 3)))
        except Exception:
            results.append(ClaimVerdict(c, UNVERIFIED, "timed_out", []))   # ran out of time: say so, never guess
    ex.shutdown(wait=False)
    overall = aggregate(results)
    # card cites the evidence behind the verdict that drove the overall result
    driver = next((v for v in results if v.verdict == overall), None)
    cites = driver.citations if driver else []
    out = {"language": out_lang, "input_language": lang, "verdict": overall, "card": render_card(overall, out_lang, cites),
           "claims": [v.to_dict() for v in results], "checked_at": ledger.now()}
    if out_lang != "en":
        out["card_en"] = render_card(overall, "en", cites)       # same verdict and citations, in English
    out["degraded"] = llm is None or getattr(llm, "failures", 0) > fails_before   # AI judge missing/at capacity: clear PIB debunks only
    if log:
        for v in results:
            if v.reason_code == "timed_out":
                continue                                # don't pollute the public ledger with unfinished checks
            ledger.append({"claim": v.claim.text, "domain": v.claim.domain, "verdict": v.verdict,
                           "reason_code": v.reason_code, "citations": v.citations,
                           "language": lang, "checked_at": out["checked_at"]})
    return out
