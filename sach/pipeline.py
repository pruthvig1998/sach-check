from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from . import ledger
from .card import render_card
from .extract import extract_claims
from .lang import detect_language
from .models import ClaimVerdict
from .stance import judge
from .verdict import decide, aggregate

def check_forward(text: str, retrievers, llm=None, log=True) -> dict:
    lang = detect_language(text)
    results: list[ClaimVerdict] = []
    for claim in extract_claims(text):
        evidence = []
        for r in retrievers:
            evidence += r.search(claim.text)
        evidence = evidence[:8]
        with ThreadPoolExecutor(max_workers=8) as ex:     # LLM calls are slow; judge sources in parallel
            for e, st in zip(evidence, ex.map(lambda e: judge(claim.text, e, llm), evidence)):
                e.stance = st
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
