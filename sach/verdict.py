"""Hard verdict rules. Pure functions: no network, no randomness."""
from __future__ import annotations
from datetime import datetime
from .fetch import http_host_of
from .models import *

def _has_citation(evidence: Evidence) -> bool:
    if not http_host_of(evidence.url):
        return False
    try:
        datetime.fromisoformat(evidence.fetched_at)
    except (TypeError, ValueError):
        return False
    return True

def decide(claim: Claim, evidence: list[Evidence]) -> ClaimVerdict:
    fetched = [e for e in evidence if _has_citation(e)]
    auth = [e for e in fetched if e.tier in AUTHORITATIVE]
    contra = [e for e in auth if e.stance == "contradicts"]
    conf = [e for e in auth if e.stance == "confirms"]
    mixed = [e for e in auth if e.stance == "mixed"]
    fc = [e for e in fetched if e.tier == TIER_FACTCHECKER]

    def cites(*groups):
        seen, out = set(), []
        for g in groups:
            for e in g:
                if e.url not in seen:
                    seen.add(e.url); out.append(e.cite())
        return out

    if contra and conf:   # authoritative sources disagree -> never guess
        return ClaimVerdict(claim, UNVERIFIED, "conflicting_official_sources", cites(contra, conf))
    if conf and mixed:    # one official source confirms, another disagrees on the details -> do not guess
        return ClaimVerdict(claim, UNVERIFIED, "conflicting_official_sources", cites(conf, mixed))
    if contra:
        return ClaimVerdict(claim, FALSE, "official_contradiction", cites(contra, fc))
    if mixed:
        return ClaimVerdict(claim, MISLEADING, "core_fact_distorted", cites(mixed, conf, fc))
    if conf:
        return ClaimVerdict(claim, TRUE, "official_confirmation", cites(conf, fc))
    # No authoritative evidence. Fact-checkers are labelled secondary and can never produce FALSE/TRUE.
    return ClaimVerdict(claim, UNVERIFIED, "factchecker_only" if fc else "no_evidence", cites(fc))

def aggregate(verdicts: list[ClaimVerdict]) -> str:
    vs = [v.verdict for v in verdicts]
    if not vs:
        return UNVERIFIED
    if FALSE in vs:
        return FALSE
    if MISLEADING in vs:
        return MISLEADING
    if all(v == TRUE for v in vs):
        return TRUE
    return UNVERIFIED
