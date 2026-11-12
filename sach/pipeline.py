from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
from . import ledger
from .card import render_card
from .extract import extract_claims
from .lang import detect_language
from .models import ClaimVerdict
from .stance import judge
from .verdict import decide, aggregate

RETRIEVE_DEADLINE_S = 70   # hard wall-clock caps: socket timeouts are per-read and a trickling server can hang a thread forever
JUDGE_DEADLINE_S = 50

def _run_with_deadline(fn, secs, default):
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(fn).result(timeout=secs)
    except (_Timeout, Exception):
        return default
    finally:
        ex.shutdown(wait=False)      # abandon a hung thread instead of blocking on it

def check_forward(text: str, retrievers, llm=None, log=True) -> dict:
    lang = detect_language(text)
    results: list[ClaimVerdict] = []
    for claim in extract_claims(text):
        evidence = []
        for r in retrievers:
            evidence += _run_with_deadline(lambda r=r: r.search(claim.text), RETRIEVE_DEADLINE_S, [])
        evidence = evidence[:8]
        ex = ThreadPoolExecutor(max_workers=8)            # LLM calls are slow; judge sources in parallel
        futs = [ex.submit(judge, claim.text, e, llm) for e in evidence]
        for e, f in zip(evidence, futs):
            try:
                e.stance = f.result(timeout=JUDGE_DEADLINE_S)
            except Exception:
                e.stance = "none"                      # hung/failed judge call -> no stance -> UNVERIFIED, never a guess
        ex.shutdown(wait=False)
        results.append(decide(claim, evidence))
    overall = aggregate(results)
    # card cites the evidence behind the verdict that drove the overall result
    driver = next((v for v in results if v.verdict == overall), None)
    cites = driver.citations if driver else []
    out = {"language": lang, "verdict": overall, "card": render_card(overall, lang, cites),
           "claims": [v.to_dict() for v in results], "checked_at": ledger.now()}
    if log:
        for v in results:
            ledger.append({"claim": v.claim.text, "domain": v.claim.domain, "verdict": v.verdict,
                           "reason_code": v.reason_code, "citations": v.citations,
                           "language": lang, "checked_at": out["checked_at"]})
    return out
