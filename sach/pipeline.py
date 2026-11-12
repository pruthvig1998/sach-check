from __future__ import annotations
import os, time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout, wait
from . import ledger
from .card import render_card
from .extract import clean_text, extract_claims
from .i18n import NOCLAIM, NOCLAIM_LABEL, tr
from .lang import SUPPORTED, detect_language
from . import cache
from .models import Claim, ClaimVerdict, UNVERIFIED, build_trace, overall_rule
from .retrieve import canonical_key
from .search import combine_status, DOWN
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

def _search_one(r, q):
    """-> (evidence, SearchRun or None). Retrievers that can report web-search health expose search_with_status; the
    status object is created per call, so parallel claims never share one."""
    fn = getattr(r, "search_with_status", None)
    return fn(q) if fn else (r.search(q), None)

def _check_claim(claim: Claim, lang: str, retrievers, llm, deadline: float) -> ClaimVerdict:
    left = lambda cap: max(0.3, min(cap, deadline - time.monotonic()))
    q = claim.text                                      # text used for searching + judging
    if lang != "en" and llm is not None and hasattr(llm, "translate"):
        q = _run_with_deadline(lambda: llm.translate(claim.text), left(15), "") or claim.text   # PIB pages are mostly English
    evidence = []
    rex = ThreadPoolExecutor(max_workers=max(1, len(retrievers)))      # PIB and web search in parallel, not one after the other
    rfuts = [rex.submit(_search_one, r, q) for r in retrievers]
    wait(rfuts, timeout=left(RETRIEVE_DEADLINE_S))
    sstat, sprov = [], []
    for r, f in zip(retrievers, rfuts):                 # keep the retrievers' priority order (PIB first)
        reports = hasattr(r, "search_with_status")
        try:
            ev, run = f.result(timeout=0)               # not done yet -> TimeoutError
            evidence += ev
            if run is not None:
                sstat.append(run.status); sprov += run.providers
        except Exception:
            if reports:
                sstat.append(DOWN)                      # a hung or crashed web search is a lost search, said out loud
    rex.shutdown(wait=False)
    seen, uniq = set(), []
    for e in evidence:                                  # the same PIB release often arrives under several URLs
        k = canonical_key(e.url)
        if k not in seen:
            seen.add(k); uniq.append(e)
    evidence = uniq[:8]
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
    v.trace = build_trace(q, evidence, v.reason_code)      # every judged source, cited or not
    v.search_status, v.search_provider = combine_status(sstat), ",".join(dict.fromkeys(sprov))   # not in to_dict(): read by check_forward
    return v

def check_forward(text: str, retrievers, llm=None, log=True, reply_lang: str | None = None,
                  use_cache: bool = True) -> dict:
    """reply_lang: any code in lang.SUPPORTED to force the reply language; None/'auto' matches the forward.
    The INPUT language always drives translation and search; only the reply changes."""
    text = clean_text(text)
    rl = reply_lang if reply_lang in SUPPORTED else None
    use = cache.enabled(use_cache, log)
    if use:
        hit = cache.lookup(text, rl)
        if hit is not None:
            out = dict(hit)
            out["first_checked_at"] = hit.get("first_checked_at") or hit.get("checked_at")
            out["cached"], out["served_at"] = True, ledger.now()
            ledger.record_check(out, cached=True)
            return out
    lang = detect_language(text)                                   # input language
    out_lang = reply_lang if reply_lang in SUPPORTED else lang          # reply language
    claims = extract_claims(text, max_claims=MAX_CLAIMS)
    if not claims:        # greeting, emoji, bare URL, numbers: nothing checkable. Say so instead of implying a search failed.
        out = {"language": out_lang, "input_language": lang, "verdict": "UNVERIFIED", "no_claims": True, "claims": [],
               "checked_at": ledger.now(), "card": f"{tr(NOCLAIM_LABEL, out_lang)}\n{tr(NOCLAIM, out_lang)}"}
        if out_lang != "en":
            out["card_en"] = f"{NOCLAIM_LABEL['en']}\n{NOCLAIM['en']}"
        out["trace"] = {"claims_extracted": 0, "overall_rule": overall_rule([]), "degraded": False}
        out["search_status"], out["search_provider"] = "ok", ""      # nothing was searched, so nothing failed
        if log:
            ledger.record_check(out, cached=False)
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
            results.append(ClaimVerdict(c, UNVERIFIED, "timed_out", [], trace=build_trace(c.text, [], "timed_out")))   # ran out of time: say so, never guess
    ex.shutdown(wait=False)
    overall = aggregate(results)
    # card cites the evidence behind the verdict that drove the overall result
    driver = next((v for v in results if v.verdict == overall), None)
    cites = driver.citations if driver else []
    out = {"language": out_lang, "input_language": lang, "verdict": overall, "card": render_card(overall, out_lang, cites),
           "claims": [v.to_dict() for v in results], "checked_at": ledger.now()}
    if out_lang != "en":
        out["card_en"] = render_card(overall, "en", cites)       # same verdict and citations, in English
    out["search_status"] = combine_status([getattr(v, "search_status", None) for v in results])   # ok | partial | down | off
    out["search_provider"] = ",".join(dict.fromkeys(p for v in results for p in getattr(v, "search_provider", "").split(",") if p))
    out["degraded"] = llm is None or getattr(llm, "failures", 0) > fails_before   # AI judge missing/at capacity: clear PIB debunks only
    out["trace"] = {"claims_extracted": len(claims), "overall_rule": overall_rule(results), "degraded": out["degraded"]}
    if log:
        for v in results:
            if v.reason_code == "timed_out":
                continue                                # don't pollute the public ledger with unfinished checks
            ledger.append({"claim": v.claim.text, "domain": v.claim.domain, "verdict": v.verdict,
                           "reason_code": v.reason_code, "citations": v.citations,
                           "language": lang, "checked_at": out["checked_at"]})
        ledger.record_check(out, cached=False)
        if use:
            cache.save(text, rl, out)
    return out
