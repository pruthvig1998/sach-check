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

    def to_dict(self):
        return {"claim": asdict(self.claim), "verdict": self.verdict, "english": self.english,
                "reason_code": self.reason_code, "citations": self.citations}
