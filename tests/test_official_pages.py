"""L2: 'official pages that mention related things' under a complete UNVERIFIED result. Show-only: never a verdict word, never for a decisive
verdict, never from a fact-checker, always with the 'not a verdict' note."""
import html as _html
import pytest
from test_cache_trace import CountingRetriever, FakeLLM, NoneLLM          # noqa: F401
from sach import honesty, site, store
from sach.models import Evidence, TIER_FACTCHECKER, TIER_OFFICIAL, TIER_PIB
from sach.pipeline import check_forward

TS = "2026-11-14T00:00:00+00:00"
CLAIM = "Government will give Rs 5000 to every woman under PM Mahila Yojana."
RELATED = Evidence("Ministry of Women and Child Development", "https://wcd.gov.in/schemes/mahila", TIER_OFFICIAL, TS, "Mahila schemes overview",
                   "The ministry runs several schemes for women. Mahila welfare schemes provide training and loans to women. A Rs 5000 payment to every woman under PM Mahila Yojana has not been mentioned in this document. Other pages list helplines.")
UNRELATED = Evidence("Ministry of Mines", "https://mines.gov.in/x", TIER_OFFICIAL, TS, "Mining lease rules", "Rules for the grant of mining leases and royalty rates.")
FC = Evidence("BOOM", "https://boomlive.in/fact-check/x", TIER_FACTCHECKER, TS, "Fact check about Mahila Yojana", "Rs 5000 to every woman under PM Mahila Yojana: a fact check of the viral message.")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR", "SACH_SHOW_PAGES"):
        monkeypatch.delenv(k, raising=False)
    store.reset(); yield


def _run(ev, text=CLAIM):
    res = check_forward(text, [CountingRetriever(list(ev))], NoneLLM(), log=False)
    return {**res, "search_status": "ok"}            # the fake retriever reports no status; a configured search reports "ok" on a complete check


def test_related_official_page_is_shown_with_the_note_and_no_verdict_words():
    res = _run([RELATED, UNRELATED, FC])
    assert res["verdict"] == "UNVERIFIED"
    panel = honesty.official_pages_html(res)
    assert "wcd.gov.in/schemes/mahila" in panel and "Rs 5000" in panel
    assert "This is not a verdict" in panel and "Read them yourself" in panel
    assert "mines.gov.in" not in panel and "boomlive" not in panel          # unrelated page and fact-checker are not shown
    low = _html.unescape(panel).lower()
    assert not any(w in low for w in ("confirms", "confirmed", "is true", "is false", "contradicts", "debunk"))


def test_it_is_part_of_the_result_page_only_for_unverified():
    res = _run([RELATED])
    assert "official-pages" in site.result_block(res)
    decisive = check_forward(CLAIM, [CountingRetriever([Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1",
                              TIER_PIB, TS, "Fake claim: Rs 5000 to every woman under PM Mahila Yojana", "Fake claim that government will give Rs 5000 to every woman under PM Mahila Yojana")])], FakeLLM(), log=False)
    assert decisive["verdict"] == "FALSE" and honesty.official_pages_html(decisive) == ""


def test_nothing_related_means_no_panel_and_the_switch_turns_it_off(monkeypatch):
    assert honesty.official_pages_html(_run([UNRELATED])) == ""
    monkeypatch.setenv("SACH_SHOW_PAGES", "0")
    assert honesty.official_pages_html(_run([RELATED])) == ""


def test_snippets_are_short_html_escaped_and_translated():
    bad = Evidence("Ministry X", "https://x.gov.in/p", TIER_OFFICIAL, TS, "Page", "<script>alert(1)</script> Rs 5000 to every woman under PM Mahila Yojana is not described. " + "word " * 200)
    res = _run([bad])
    for s in res["claims"][0]["trace"]["sources"]:
        assert len(s.get("snippet", "")) <= 260
    panel = honesty.official_pages_html(res)
    assert "<script>" not in panel
    for lang, needle in (("hi", "यह नतीजा नहीं है"), ("te", "ఇది తీర్పు కాదు"), ("en", "not a verdict")):
        assert needle in honesty.official_pages_html({**res, "language": lang})


def test_limited_checks_do_not_show_it():
    res = {**_run([RELATED]), "degraded": True}
    assert honesty.official_pages_html(res) == ""


# ---- L5: official places to report a scam, under the warning signs
def test_scam_box_points_to_the_official_reporting_pages_in_en_hi_te():
    from sach import scamsigns
    signs = [{"id": "asks_secret", "severity": "high"}]
    for lang, needle in (("en", "helpline 1930"), ("hi", "हेल्पलाइन 1930"), ("te", "హెల్ప్‌లైన్ 1930")):
        box = scamsigns.signs_html(signs, lang)
        assert needle in box and "https://cybercrime.gov.in/" in box and "https://sancharsaathi.gov.in/" in box
    assert scamsigns.signs_html([], "en") == ""                       # no signs, no box, no references
    box_en = scamsigns.signs_html(signs, "en").lower()
    assert "safe" not in box_en.replace("unsafe", "")                  # the box never says a message is safe


def test_snippets_drop_pib_dateline_skip_links_and_unrendered_pages():
    from sach.models import _snippet
    claim = "Taxpayers receive SMS asking them to submit a refund request."
    pib = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/x", TIER_PIB, TS, "Beware of fake refund SMS",
                   "PIB Backgrounder PRESS RELEASE Posted On: 08 MAY 2019 3:09PM by PIB Chennai It has been brought to the notice of the department that certain emails and SMS are being received by taxpayers asking them to submit a refund request.")
    s = _snippet(claim, pib)
    assert s.startswith("It has been brought to the notice") and "Posted On" not in s and "PRESS RELEASE" not in s
    sbi = Evidence("State Bank of India", "https://onlinesbi.sbi.bank.in/", TIER_OFFICIAL, TS, "SBI", "Skip to main content SBI never asks for confidential information such as PIN and OTP from customers.")
    assert _snippet("SBI asks for PIN and OTP", sbi).startswith("SBI never asks")
    broken = Evidence("PIB", "https://pib.gov.in/y", TIER_PIB, TS, "Factsheet", "Factsheet Details | PIB JavaScript must be enabled in order for you to use the Site in standard view.")
    assert _snippet("factsheet details", broken) == ""


def test_the_same_page_under_two_urls_is_listed_once_and_skip_links_are_removed_everywhere():
    from sach.models import _snippet
    sbi = Evidence("State Bank of India", "https://onlinesbi.sbi.bank.in/", TIER_OFFICIAL, TS, "SBI", "State Bank of India Skip to main content SBI never asks for confidential information such as PIN and OTP.")
    assert "Skip to main content" not in _snippet("SBI asks for PIN and OTP", sbi)
    twin_a = Evidence("Ministry X", "https://x.gov.in/a?PRID=1", TIER_OFFICIAL, TS, "Rs 5000 to every woman", "Rs 5000 to every woman under PM Mahila Yojana is not described in this notice about welfare schemes.")
    twin_b = Evidence("Ministry X", "https://x.gov.in/b?PRID=1&lang=2", TIER_OFFICIAL, TS, "Rs 5000 to every woman", "Rs 5000 to every woman under PM Mahila Yojana is not described in this notice about welfare schemes.")
    panel = honesty.official_pages_html(_run([twin_a, twin_b]))
    assert panel.count("<li") == 1
