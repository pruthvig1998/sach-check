from __future__ import annotations
from dataclasses import dataclass, field, asdict

TIER_PIB = "pib_debunk"
TIER_OFFICIAL = "official"
TIER_FACTCHECKER = "factchecker"
AUTHORITATIVE = (TIER_PIB, TIER_OFFICIAL)

TRUE, FALSE, MISLEADING, UNVERIFIED = "TRUE", "FALSE", "MISLEADING", "UNVERIFIED"

@dataclass
class Evidence:
    source_name: str
    url: str
    tier: str            # TIER_*
    fetched_at: str      # ISO timestamp of the real fetch
    title: str = ""
    text: str = ""
    stance: str = "none"  # contradicts | confirms | mixed | none

    def cite(self) -> dict:
        return {"source": self.source_name, "url": self.url, "tier": self.tier,
                "date_accessed": self.fetched_at[:10], "fetched_at": self.fetched_at}

@dataclass
class Claim:
    text: str
    domain: str = "other"   # scheme | health | news | other

@dataclass
class ClaimVerdict:
    claim: Claim
    verdict: str
    reason_code: str
    citations: list = field(default_factory=list)
    english: str = ""        # English rendering of a non-English claim (what we actually searched for)
    trace: dict = field(default_factory=dict)   # audit trail: what was searched, every source judged, which rule fired
    layer: str = "live"      # "match" = a fact-checker's or PIB's existing published verdict (sach/match.py), not Sach's own check
    match: dict = field(default_factory=dict)   # attribution of a matched verdict: checker, review_url, review_date, rating_text, ...
    detected: str | None = None                 # language Google detected (not in to_dict())

    def to_dict(self):
        d = {"claim": asdict(self.claim), "verdict": self.verdict, "english": self.english,
             "reason_code": self.reason_code, "citations": self.citations, "trace": self.trace, "layer": self.layer}
        if self.match:
            d["match"] = self.match
        return d

# One plain sentence per reason code that verdict.decide() can return (plus timed_out, set by the pipeline).
RULE_TEXT = {
    "official_contradiction": "An official source contradicts this claim, so the rule gives FALSE.",
    "official_confirmation": "An official source confirms this claim, so the rule gives TRUE.",
    "core_fact_distorted": "An official source says part of this is right but the details are different, so the rule gives MISLEADING.",
    "conflicting_official_sources": "Official sources disagree with each other, so we do not guess and the rule gives UNVERIFIED.",
    "factchecker_only": "Only fact-checkers were found. They are not official, so the rule gives UNVERIFIED.",
    "no_evidence": "No official source was found that confirms or denies this, so the rule gives UNVERIFIED.",
    "matched_fact_check": "A fact-checker's own published review matches this claim, so Sach shows their verdict with their name and did not run its own check.",
    "timed_out": "The check ran out of time before it finished, so the result is UNVERIFIED.",
}

def build_trace(searched_as: str, evidence: list, reason_code: str, translator: str | None = None) -> dict:
    t = {"searched_as": searched_as,
         "sources": [{"source": e.source_name, "url": e.url, "tier": e.tier, "fetched_at": e.fetched_at,
                      "title": e.title, "stance": e.stance} for e in evidence[:8]],
         "rule": reason_code, "rule_text": RULE_TEXT.get(reason_code, "")}
    if translator:
        t["translator"] = translator          # "google" | "llm" | "none": who produced the English used for searching
    return t

def overall_rule(verdicts: list) -> str:
    """Plain sentence for whichever branch of verdict.aggregate() decides the overall verdict."""
    vs = [v.verdict for v in verdicts]
    if not vs:
        return "No claims were checked, so the overall result is UNVERIFIED."
    if FALSE in vs:
        return "At least one claim is FALSE, so the overall result is FALSE."
    if MISLEADING in vs:
        return "No claim is FALSE and at least one is MISLEADING, so the overall result is MISLEADING."
    if all(v == TRUE for v in vs):
        return "Every claim is TRUE, so the overall result is TRUE."
    return "Not every claim could be confirmed, so the overall result is UNVERIFIED."
