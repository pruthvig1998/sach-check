"""No live web: retrievers are replaced by recorded fixtures."""
import pytest
from sach.models import *
from sach.extract import extract_claims
from sach.lang import detect_language
from sach.verdict import decide, aggregate
from sach.stance import heuristic_stance
from sach.pipeline import check_forward
from sach.card import render_card
from sach.i18n import LABEL, WHY
from sach.fetch import is_official, is_factchecker
from sach.pib import parse_rss, parse_release

TS = "2026-11-12T10:00:00+00:00"
C = Claim("Government will give Rs 5000 to every woman under PM Mahila Yojana")

def ev(tier, stance, url="https://pib.gov.in/x", name="PIB"):
    return Evidence(name, url, tier, TS, "t", "txt", stance)

# --- claim extraction
def test_extract_splits_and_drops_boilerplate():
    f = "PM Kisan: farmers get Rs 6000 per year.\nPlease forward to all groups!!\nDrinking hot water cures cancer."
    cs = extract_claims(f)
    assert [c.domain for c in cs] == ["scheme", "health"]
    assert all("forward" not in c.text.lower() for c in cs)

def test_extract_hindi_telugu_split_on_danda():
    assert len(extract_claims("सरकार हर महिला को 5000 रुपये देगी। यह योजना कल बंद हो जाएगी।")) == 2
    assert extract_claims("ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది. ఈ పథకం రేపు ముగుస్తుంది.")[0].domain == "scheme"

# --- verdict rules (the hard ones)
def test_false_requires_official_contradiction():
    assert decide(C, [ev(TIER_PIB, "contradicts")]).verdict == FALSE
    assert decide(C, [ev(TIER_OFFICIAL, "contradicts")]).verdict == FALSE

def test_absence_of_evidence_is_unverified_never_false():
    assert decide(C, []).verdict == UNVERIFIED
    assert decide(C, [ev(TIER_OFFICIAL, "none")]).verdict == UNVERIFIED

def test_factchecker_alone_never_gives_false_or_true():
    for stance in ("contradicts", "confirms", "mixed"):
        v = decide(C, [ev(TIER_FACTCHECKER, stance, "https://www.altnews.in/a", "Alt News")])
        assert v.verdict == UNVERIFIED and v.reason_code == "factchecker_only"
        assert v.citations[0]["tier"] == TIER_FACTCHECKER   # labelled, not dressed up as official

def test_conflicting_official_sources_unverified():
    assert decide(C, [ev(TIER_PIB, "contradicts"), ev(TIER_OFFICIAL, "confirms", "https://a.gov.in")]).verdict == UNVERIFIED

def test_true_and_misleading():
    assert decide(C, [ev(TIER_OFFICIAL, "confirms")]).verdict == TRUE
    assert decide(C, [ev(TIER_OFFICIAL, "mixed")]).verdict == MISLEADING

def test_aggregate_priority():
    mk = lambda v: ClaimVerdict(C, v, "x")
    assert aggregate([mk(TRUE), mk(FALSE)]) == FALSE
    assert aggregate([mk(TRUE), mk(MISLEADING)]) == MISLEADING
    assert aggregate([mk(TRUE), mk(UNVERIFIED)]) == UNVERIFIED
    assert aggregate([mk(TRUE)]) == TRUE
    assert aggregate([]) == UNVERIFIED

# --- citations
@pytest.mark.parametrize("stance,tier", [("contradicts", TIER_PIB), ("confirms", TIER_OFFICIAL), ("mixed", TIER_OFFICIAL)])
def test_every_non_unverified_verdict_has_citation(stance, tier):
    v = decide(C, [ev(tier, stance)])
    assert v.citations and all(c["url"] and c["date_accessed"] and c["source"] for c in v.citations)

def test_unfetched_evidence_is_never_cited():
    e = ev(TIER_PIB, "contradicts"); e.fetched_at = ""
    assert decide(C, [e]).citations == []

# --- stance heuristic is conservative
def test_heuristic_stance():
    claim = "PM Mahila Yojana gives Rs 5000 to every woman"
    assert heuristic_stance(claim, "Fake: PM Mahila Yojana gives Rs 5000 to every woman", "", TIER_PIB) == "contradicts"
    assert heuristic_stance(claim, "Cabinet approves GST rate changes", "unrelated text about trade", TIER_PIB) == "none"
    assert heuristic_stance(claim, "PM Mahila Yojana", "gives Rs 2000 to every woman", TIER_OFFICIAL) == "mixed"

# --- language + cards
@pytest.mark.parametrize("text,lang", [
    ("Government will give free laptops to all students", "en"),
    ("सरकार हर महिला को 5000 रुपये देगी, जल्दी शेयर करें", "hi"),
    ("ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది", "te"),
    ("sarkar sabko free paisa degi yeh yojana kal band ho jayegi jaldi bhejo", "hi")])
def test_language_detection(text, lang):
    assert detect_language(text) == lang

CITE = [{"source": "PIB", "url": "https://pib.gov.in/x", "tier": TIER_PIB, "date_accessed": "2026-11-12", "fetched_at": TS}]

@pytest.mark.parametrize("lang", ["en", "hi", "te"])
@pytest.mark.parametrize("verdict", [TRUE, FALSE, MISLEADING, UNVERIFIED])
def test_card_verdict_first_and_in_language(lang, verdict):
    card = render_card(verdict, lang, CITE)
    first = card.splitlines()[0]
    assert LABEL[lang][verdict] in first
    if verdict != UNVERIFIED:
        assert "https://pib.gov.in/x" in card
    if lang != "en":
        assert not any(w in card for w in ("FALSE", "TRUE", "claim"))

def test_templates_complete_and_short():
    for lang in WHY:
        assert set(WHY[lang]) == {TRUE, FALSE, MISLEADING, UNVERIFIED}
        assert all(len(s) < 160 for s in WHY[lang].values())

class FakeRetriever:
    def __init__(self, ev): self.ev = ev
    def search(self, claim): return [Evidence(e.source_name, e.url, e.tier, e.fetched_at, e.title, e.text) for e in self.ev]

def test_pipeline_reply_language_matches_input_and_logs_ledger():
    from sach import ledger
    pib = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
                   "Fake claim: government will give Rs 5000 to every woman",
                   "Fake message claims government will give Rs 5000 to every woman")
    res = check_forward("सरकार हर महिला को 5000 रुपये देगी, जल्दी शेयर करें।", [FakeRetriever([pib])])
    assert res["language"] == "hi"
    # heuristic stance cannot match Devanagari claim to English page -> stays honest
    assert res["verdict"] == UNVERIFIED
    res2 = check_forward("Government will give Rs 5000 to every woman. Please forward to all groups!", [FakeRetriever([pib])])
    assert res2["verdict"] == FALSE and "https://pib.gov.in/PressReleasePage.aspx?PRID=1" in res2["card"]
    assert len(ledger.load()) >= 2 and all("citations" in r for r in ledger.load())

# --- domains + parsers
def test_domain_classification():
    assert is_official("https://pib.gov.in/x") and is_official("https://www.mohfw.gov.in/a") and is_official("https://www.who.int/b")
    assert not is_official("https://gov.in.evil.com/") and not is_official("https://evilgov.in/")
    assert is_factchecker("https://www.boomlive.in/a") and not is_factchecker("https://boomlive.in.evil.com")

def test_rss_and_release_parsers():
    xml = "<rss><channel><item><title>A</title><link>https://pib.gov.in/PressReleaseIframePage.aspx?PRID=42</link></item></channel></rss>"
    assert parse_rss(xml) == [{"title": "A", "prid": "42"}]
    d = parse_release("<html><h2>Title X</h2><div id='PdfDiv'>Body text</div></html>")
    assert d["title"] == "Title X" and d["body"] == "Body text"

# --- regressions from the Day-1 data checkpoint (live PIB pages)
def test_summary_page_mentioning_misinformation_is_not_a_debunk():
    claim = "PIB Fact Check Unit has issued over 2,900 fact checks."
    title = "Government Counters Misinformation; PIB Fact-Check Unit Issues Over 2,900 Fact Checks"
    assert heuristic_stance(claim, title, "The unit debunked fake news...", TIER_OFFICIAL) != "contradicts"
    assert heuristic_stance(claim, title, "The unit debunked fake news...", TIER_PIB) != "contradicts"

def test_negated_claim_is_not_judged_against_a_debunk_title():
    t = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
    assert heuristic_stance("Government will not reduce retirement age of Central Government employees", t, "", TIER_PIB) == "none"
    assert heuristic_stance("Central Government will reduce retirement age of employees to 50", t, "", TIER_PIB) in ("contradicts", "none")

def test_llm_failure_falls_back_to_heuristic():
    from sach.stance import judge
    class Broken:
        def stance(self, *a): raise RuntimeError("401 invalid api key")
    e = Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: PM Mahila Yojana gives Rs 5000 to every woman", "")
    assert judge("PM Mahila Yojana gives Rs 5000 to every woman", e, Broken()) == "contradicts"
