from __future__ import annotations
import os, time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout, wait
from . import ledger
from .card import render_card
from .extract import clean_text, extract_claims
from .i18n import NOCLAIM, NOCLAIM_LABEL, tr
from .lang import SUPPORTED, detect_language
from . import cache, gtranslate, match as _match
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

class _JudgeError(Exception):
    def __init__(self, kind: str, ms: int):
        super().__init__(kind)
        self.kind, self.ms = kind, ms


def _check_claim(claim: Claim, lang: str, retrievers, llm, deadline: float, english: str = "", tinfo: dict | None = None) -> ClaimVerdict:
    t_start = time.monotonic()
    left = lambda cap: max(0.3, min(cap, deadline - time.monotonic()))
    q = claim.text                                      # text used for searching + judging
    tinfo = tinfo if tinfo is not None else {}
    if english:
        q = english                                     # already translated by the match layer: do not pay for it twice
    elif lang != "en":
        tr = _run_with_deadline(lambda: gtranslate.translate_claim(claim.text, lang, llm), left(15), None)   # Google first, LLM fallback; PIB pages are mostly English
        if tr:
            q = tr["text"] or claim.text
            tinfo.update(translator=tr["translator"], detected=tr["detected"])
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
    t_judge = time.monotonic()
    t_retrieved = t_judge
    ex = ThreadPoolExecutor(max_workers=8)              # LLM calls are slow; judge sources in parallel
    def _judge_timed(e):
        t = time.monotonic()
        try:
            return judge(q, e, llm), int((time.monotonic() - t) * 1000)
        except Exception as exc:                        # judge() already swallows provider errors; anything raised here is a bug: say so
            raise _JudgeError(type(exc).__name__, int((time.monotonic() - t) * 1000))
    futs = [ex.submit(_judge_timed, e) for e in evidence]
    window = left(JUDGE_DEADLINE_S)
    wait(futs, timeout=window)
    problems = 0
    for e, f in zip(evidence, futs):
        try:
            if f.done():
                e.stance, ms = f.result(timeout=0)
                e.judge_note = {"outcome": "answered", "ms": ms}
            else:
                e.stance = "none"                       # still running at the deadline: the AI did not answer in time
                e.judge_note = {"outcome": "timeout", "ms": int(window * 1000)}
                problems += 1
        except _JudgeError as je:
            e.stance = "none"
            e.judge_note = {"outcome": "error:" + je.kind, "ms": je.ms}
            problems += 1
        except Exception as exc:
            e.stance = "none"                           # never a guess: no stance -> UNVERIFIED, but now it is visible and flagged
            e.judge_note = {"outcome": "error:" + type(exc).__name__, "ms": 0}
            problems += 1
    ex.shutdown(wait=False)
    v = decide(claim, evidence)
    v.english = q if q != claim.text else ""
    v.trace = build_trace(q, evidence, v.reason_code, tinfo.get("translator") or "none")      # every judged source, cited or not
    v.detected = tinfo.get("detected")
    v.trace["layer"] = "LIVE"
    v.trace["timing_ms"] = {"retrieve": int((t_retrieved - t_start) * 1000), "judge": int((time.monotonic() - t_judge) * 1000), "judge_window": int(window * 1000)}
    v.judge_problems = problems                         # sources whose AI judge did not answer (timeout or error): read by check_forward
    v.search_status, v.search_provider = combine_status(sstat), ",".join(dict.fromkeys(sprov))   # not in to_dict(): read by check_forward
    return v

def check_forward(text: str, retrievers, llm=None, log=True, reply_lang: str | None = None,
                  use_cache: bool = True, force_live: bool = False, matcher=None) -> dict:
    """reply_lang: any code in lang.SUPPORTED to force the reply language; None/'auto' matches the forward.
    The INPUT language always drives translation and search; only the reply changes."""
    text = clean_text(text)
    rl = reply_lang if reply_lang in SUPPORTED else None
    use = cache.enabled(use_cache, log)
    if use and not force_live:       # "run Sach's own check anyway" must not be answered by a cached match
        hit = cache.lookup(text, rl)
        if hit is not None:
            out = dict(hit)
            out["first_checked_at"] = hit.get("first_checked_at") or hit.get("checked_at")
            out["cached"], out["served_at"] = True, ledger.now()
            ot = dict(hit.get("trace") or {})
            out["trace"] = {**ot, "layer": "CACHE", "original_layer": ot.get("original_layer") if ot.get("layer") == "CACHE" else ot.get("layer", "LIVE")}
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
        out["trace"] = {"layer": "LIVE", "claims_extracted": 0, "overall_rule": overall_rule([]), "degraded": False}
        out["layer"] = "live"
        out["search_status"], out["search_provider"] = "ok", ""      # nothing was searched, so nothing failed
        if log:
            ledger.record_check(out, cached=False)
        return out
    fails_before = getattr(llm, "failures", 0)
    deadline = time.monotonic() + BUDGET_S
    # MATCH layer: an existing published verdict from PIB or a verified fact-checker, attributed. No live retrieval or LLM for these claims.
    matches = [(None, "")] * len(claims)
    tinfos = [{} for _ in claims]           # per claim: which translator ran and what Google detected
    if not force_live and _match.enabled():
        try:
            matches = _match.run_match(claims, lang, llm, matcher, tinfos)
        except Exception:
            matches = [(None, "")] * len(claims)
    now_iso = ledger.now()
    results: list = [None] * len(claims)
    todo = []
    for i, (c, (m, eng)) in enumerate(zip(claims, matches)):
        if m:
            results[i] = _match.verdict_from_match(c, m, eng, now_iso, tinfos[i].get("translator") or ("none" if lang == "en" else ""))
        else:
            todo.append(i)
    ex = ThreadPoolExecutor(max_workers=PARALLEL_CLAIMS)
    futs = {i: ex.submit(_check_claim, claims[i], lang, retrievers, llm, deadline, matches[i][1], tinfos[i]) for i in todo}
    for i, f in futs.items():
        try:
            results[i] = f.result(timeout=max(0.3, deadline - time.monotonic() + 3))
        except Exception:
            c = claims[i]
            results[i] = ClaimVerdict(c, UNVERIFIED, "timed_out", [], trace=build_trace(c.text, [], "timed_out"))   # ran out of time: say so, never guess
    ex.shutdown(wait=False)
    if lang != "en":                      # Google's detector may sharpen an ambiguous Devanagari / Bengali-script guess (only the 'auto' reply language follows)
        newlang = gtranslate.refine_language(lang, gtranslate.consensus_detected(tinfos), text)
        if newlang != lang:
            if out_lang == lang and not (reply_lang in SUPPORTED):
                out_lang = newlang
            lang = newlang
    live = [v for v in results if v.layer != "match"]
    overall = aggregate(results)
    # card cites the evidence behind the verdict that drove the overall result (Sach's own live claims only; matches carry their own attribution)
    pool = live if live else results
    driver = next((v for v in pool if v.verdict == aggregate(pool)), None)
    cites = driver.citations if driver else []
    if len(live) == len(results):
        layer = "live"
        card, card_en = render_card(overall, out_lang, cites), (render_card(overall, "en", cites) if out_lang != "en" else "")
    else:
        layer = "match" if not live else "mixed"
        lcard = lambda lg: render_card(aggregate(live), lg, cites) if live else ""
        card = _match.render_match_card(results, overall, out_lang, lcard(out_lang))
        card_en = _match.render_match_card(results, overall, "en", lcard("en")) if out_lang != "en" else ""
    out = {"language": out_lang, "input_language": lang, "verdict": overall, "layer": layer, "card": card,
           "claims": [v.to_dict() for v in results], "checked_at": now_iso}
    if layer != "live":
        out["match"] = _match.top_match(results, overall)
    if card_en:
        out["card_en"] = card_en                                   # same verdict and citations, in English
    out["search_status"] = combine_status([getattr(v, "search_status", None) for v in live]) if live else "ok"   # ok | partial | down | off
    out["search_provider"] = ",".join(dict.fromkeys(p for v in live for p in getattr(v, "search_provider", "").split(",") if p))
    judge_problems = sum(getattr(v, "judge_problems", 0) for v in live)
    out["degraded"] = bool(live) and (llm is None or getattr(llm, "failures", 0) > fails_before or judge_problems > 0)   # AI judge missing, at capacity, timed out or failed: never "neutral"
    if judge_problems:
        out["judge_problems"] = judge_problems
    tlayer = {"live": "LIVE", "match": "MATCH", "mixed": "MATCH+LIVE"}[layer]
    if layer == "live" and overall == UNVERIFIED and not any(v.reason_code == "timed_out" for v in results):
        tlayer = "ESCALATED"                                       # UNVERIFIED live result: the card offers human fact-checkers
    out["trace"] = {"layer": tlayer, "claims_extracted": len(claims), "degraded": out["degraded"],
                    "overall_rule": overall_rule(results) if layer == "live" else _match.overall_match_rule(results, overall)}
    if log:
        for v in results:
            if v.reason_code == "timed_out":
                continue                                # don't pollute the public ledger with unfinished checks
            ledger.append({"claim": v.claim.text, "domain": v.claim.domain, "verdict": v.verdict,
                           "reason_code": v.reason_code, "citations": v.citations,
                           "language": lang, "checked_at": out["checked_at"], **_match.ledger_fields(v)})
        ledger.record_check(out, cached=False)
        if use and not force_live:       # a forced live run never overwrites the cached match for the same text
            cache.save(text, rl, out)
    return out
