"""SHAREFIX: the shared text, the image data and the result page describe the claim that DRIVES the overall verdict (never claims[0]),
and an incomplete check (degraded, or web search down or partial) never reads as 'no official source found'. Offline: no network, no LLM."""
import json
from types import SimpleNamespace
from urllib.parse import unquote
import pytest
from test_sach import server, _post   # noqa: F401  (fixture and helper from the existing suite)
from sach import match, share, site
from sach.card import render_card
from sach.i18n import EMOJI, INCOMPLETE_ESC_NOTE, INCOMPLETE_NOTICE, LABEL, WHY, incomplete, tr
from sach.report import card_data, card_data_script, driver_claim

SITE = "https://s.example"
PIB = "https://pib.gov.in/PressReleasePage.aspx?PRID=1618590&x=1#a"
FC = "https://altnews.in/story"
REVIEW = "https://www.boomlive.in/fake-vaccine"
LINK = "https://s.example/?r=0123456789ab"
NO_SOURCE = "no official source"
INC_EN = "Sach could not finish checking this"


def cite(url, source="PIB (Press Information Bureau)", tier="pib_debunk", date="2026-11-10"):
    return {"source": source, "url": url, "tier": tier, "date_accessed": date, "fetched_at": "2026-11-10T08:00:00+00:00"}


def live(text, verdict, url=None, source="PIB (Press Information Bureau)", tier="pib_debunk"):
    cites = [cite(url, source, tier)] if url else []
    return {"claim": {"text": text, "domain": "scheme"}, "verdict": verdict, "english": "", "reason_code": "official_contradiction",
            "citations": cites, "trace": {}, "layer": "live"}


def matched(text, verdict, rating="False", checker="BOOM"):
    return {"claim": {"text": text, "domain": "health"}, "verdict": verdict, "english": "", "reason_code": "factchecker", "citations": [],
            "trace": {}, "layer": "match", "match": {"checker": checker, "review_url": REVIEW, "review_date": "2026-11-01", "rating_text": rating}}


def res(claims, verdict, card=None, lang="en", **kw):
    """A result shaped like pipeline.check_forward output. The card is the live card of the driver's citations unless given."""
    if card is None:
        drv = next((c for c in claims if c["verdict"] == verdict), claims[0])
        card = render_card(verdict, lang, drv.get("citations") or [])
    r = {"language": lang, "input_language": lang, "verdict": verdict, "layer": "live", "card": card, "claims": claims,
         "checked_at": "2026-11-12T09:30:00+00:00", "degraded": False, "search_status": "ok", "trace": {"layer": "LIVE", "claims_extracted": len(claims),
         "overall_rule": "x"}}
    r.update(kw)
    return r


def first_line(t):
    return t.split("\n", 1)[0]


# ---------------------------------------------------------------- the driver claim

@pytest.mark.parametrize("verdicts, verdict, driver", [
    (["UNVERIFIED", "FALSE"], "FALSE", 1),
    (["FALSE", "UNVERIFIED"], "FALSE", 0),
    (["TRUE", "FALSE"], "FALSE", 1),
    (["MISLEADING", "UNVERIFIED"], "MISLEADING", 0),
    (["UNVERIFIED", "MISLEADING"], "MISLEADING", 1),
    (["TRUE", "TRUE"], "TRUE", 0),
    (["UNVERIFIED", "UNVERIFIED"], "UNVERIFIED", 0),
    (["TRUE", "UNVERIFIED"], "UNVERIFIED", 1),
])
def test_driver_claim_is_the_claim_behind_the_overall_verdict(verdicts, verdict, driver):
    claims = [live(f"claim {i}", v) for i, v in enumerate(verdicts)]
    r = res(claims, verdict)
    assert share.driver_claim(r) is claims[driver]
    assert driver_claim(r) is claims[driver]


def test_driver_claim_none_without_claims():
    assert share.driver_claim({"verdict": "UNVERIFIED", "claims": []}) is None


# ---------------------------------------------------------------- shared WhatsApp text: two and more claims

def test_unverified_then_false_matched_puts_false_and_its_review_next_to_each_other():
    r = res([live("Cow urine cures every disease", "UNVERIFIED"), matched("Fake vaccine news", "FALSE")], "FALSE",
            card="❌ Checked by BOOM\nFalse.")
    t = share.build_share_text(r, SITE)
    assert t.startswith("❌ Checked by BOOM\nFalse.")
    assert "❌ False by BOOM: “Fake vaccine news”" in t
    assert "❔ UNVERIFIED: “Cow urine cures every disease”" in t
    assert f"Full evidence: {REVIEW}" in t
    assert "Claim checked" not in t and "PIB" not in t


def test_reverse_order_keeps_the_driver_and_its_link():
    r = res([matched("Fake vaccine news", "FALSE"), live("Cow urine cures every disease", "UNVERIFIED")], "FALSE",
            card="❌ Checked by BOOM\nFalse.")
    t = share.build_share_text(r, SITE)
    assert f"Full evidence: {REVIEW}" in t
    assert "❌ False by BOOM: “Fake vaccine news”" in t and "❔ UNVERIFIED: “Cow urine cures every disease”" in t


def test_wrong_claim_is_never_cited_for_a_false_card():
    """The reported bug: first claim UNVERIFIED with an authoritative-looking link, second claim FALSE with the PIB debunk."""
    r = res([live("Claim A is unverified", "UNVERIFIED", url=FC, source="Alt News", tier="factchecker"),
             live("Claim B is false", "FALSE", url=PIB)], "FALSE")
    t = share.build_share_text(r, SITE)
    assert t.count(PIB) == 1 and FC not in t                                   # the only link is the FALSE claim's own source
    assert "❌ FALSE: “Claim B is false”" in t and "❔ UNVERIFIED: “Claim A is unverified”" in t
    assert t.count("FALSE") == 2 and t.count("UNVERIFIED") == 1                 # headline word + the FALSE line; one UNVERIFIED line


@pytest.mark.parametrize("claims, verdict, driver_text, driver_word", [
    ([live("first true", "TRUE", url=PIB), live("second false", "FALSE", url=FC, source="Alt News", tier="factchecker")], "FALSE", "second false", "FALSE"),
    ([live("first misleading", "MISLEADING", url=PIB), live("second unverified", "UNVERIFIED")], "MISLEADING", "first misleading", "MISLEADING"),
    ([live("first true", "TRUE", url=PIB), live("second true", "TRUE", url=FC, source="Alt News", tier="factchecker")], "TRUE", "first true", "TRUE"),
])
def test_two_claim_orders_name_the_driver_once(claims, verdict, driver_text, driver_word):
    r = res(claims, verdict)
    t = share.build_share_text(r, SITE)
    assert first_line(t) == first_line(r["card"]) and first_line(t).startswith(EMOJI[verdict])
    driver_line = next(l for l in t.split("\n") if driver_text in l)
    assert driver_line.startswith(f"{EMOJI[driver_word]} {driver_word}: ")
    cited = share.driver_claim(r)["citations"][0]["url"]
    assert t.count(cited) == 1                                                  # the driver's own source, shown once (card or evidence line)


def test_mixed_match_and_live_names_each_claim_with_its_own_result():
    r = res([matched("Fake vaccine news", "FALSE"), live("Cow urine cures", "UNVERIFIED")], "FALSE", card="❌ Checked by BOOM\nFalse.")
    lines = share.build_share_text(r, SITE).split("\n")
    assert "❌ False by BOOM: “Fake vaccine news”" in lines
    assert "❔ UNVERIFIED: “Cow urine cures”" in lines
    assert f"Full evidence: {REVIEW}" in lines


@pytest.mark.parametrize("n, extra", [(3, None), (4, "+1 more on the page"), (6, "+3 more on the page")])
def test_many_claims_list_at_most_three_and_say_how_many_more(n, extra):
    claims = [live(f"claim number {i}", "UNVERIFIED") for i in range(n - 1)] + [live("the false one", "FALSE", url=PIB)]
    r = res(claims, "FALSE")
    t = share.build_share_text(r, SITE)
    claim_lines = [l for l in t.split("\n") if ": “" in l and l[:2] in ("❔ ", "❌ ", "✅ ", "⚠️")]
    assert len(claim_lines) == min(n, 3)
    assert "❌ FALSE: “the false one”" in claim_lines                  # the driver is always among the listed claims
    if extra:
        assert extra in t.split("\n")
    else:
        assert "more on the page" not in t
    assert len(t) <= share.SHARE_MAX


def test_each_claim_line_is_cut_to_80_characters():
    long = "word " * 60
    r = res([live(long, "UNVERIFIED"), live("the false one", "FALSE", url=PIB)], "FALSE")
    line = next(l for l in share.build_share_text(r, SITE).split("\n") if l.startswith("❔ "))
    quoted = line.split(": “", 1)[1].rstrip("”")
    assert len(quoted) <= 80 and quoted.endswith("…")


def test_single_claim_still_quotes_the_claim_as_before():
    r = res([live("Only one claim", "FALSE", url=PIB)], "FALSE")
    t = share.build_share_text(r, SITE)
    assert "Claim checked: “Only one claim”" in t and "Claim 1" not in t


# ---------------------------------------------------------------- single-claim output is byte-for-byte unchanged

OLD = {  # expectations stored from the output BEFORE this change (same fixtures as below)
    "false_live": ("X FALSE\nPIB says this claim is false.\nSource: PIB - https://pib.gov.in/PressReleasePage.aspx?PRID=1618590&x=1#a\n\n"
                   "Claim checked: “Government will give Rs 5000 to every woman. Forward to all groups!”\n\n"
                   "Got a forward you're unsure about? Check it free on Sach: https://s.example",
                   "X FALSE\nPIB says this claim is false.\nSource: PIB - https://pib.gov.in/PressReleasePage.aspx?PRID=1618590&x=1#a\n\n"
                   "Claim checked: “Government will give Rs 5000 to every woman. Forward to all groups!”\n\n"
                   "Full evidence: https://s.example/?r=0123456789ab\n\n"
                   "Got a forward you're unsure about? Check it free on Sach: https://s.example"),
    "unv_live": ("? UNVERIFIED\nWe found no official source that confirms or denies this. Do not treat it as fact.\n\n"
                 "Claim checked: “Cow urine cures every disease”\n\n"
                 "Got a forward you're unsure about? Check it free on Sach: https://s.example",
                 "? UNVERIFIED\nWe found no official source that confirms or denies this. Do not treat it as fact.\n\n"
                 "Claim checked: “Cow urine cures every disease”\n\n"
                 "Full evidence: https://s.example/?r=0123456789ab\n\n"
                 "Got a forward you're unsure about? Check it free on Sach: https://s.example"),
    "true_hi": ("T सच\nFinance Ministry ने इसकी पुष्टि की है।\nस्रोत: Ministry of Finance - https://finmin.gov.in/notice.pdf\n\n"
                "जाँचा गया दावा: “सरकार ने नई योजना शुरू की है”\n\n"
                "कोई फ़ॉरवर्ड समझ नहीं आ रहा? Sach पर मुफ़्त में जाँचें: https://s.example",
                "T सच\nFinance Ministry ने इसकी पुष्टि की है।\nस्रोत: Ministry of Finance - https://finmin.gov.in/notice.pdf\n\n"
                "जाँचा गया दावा: “सरकार ने नई योजना शुरू की है”\n\n"
                "पूरा प्रमाण: https://s.example/?r=0123456789ab\n\n"
                "कोई फ़ॉरवर्ड समझ नहीं आ रहा? Sach पर मुफ़्त में जाँचें: https://s.example"),
    "misl_fc": ("M MISLEADING\nPart is real (Alt News), numbers distorted.\nSource: Fact-checker (not official) - Alt News - https://altnews.in/story\n\n"
                "Claim checked: “Train fares doubled”\n\n"
                "Got a forward you're unsure about? Check it free on Sach: https://s.example",
                "M MISLEADING\nPart is real (Alt News), numbers distorted.\nSource: Fact-checker (not official) - Alt News - https://altnews.in/story\n\n"
                "Claim checked: “Train fares doubled”\n\n"
                "Full evidence: https://s.example/?r=0123456789ab\n\n"
                "Got a forward you're unsure about? Check it free on Sach: https://s.example"),
    "match_single": ("F Checked by BOOM\nFalse.\n\nClaim checked: “Fake vaccine news”\n\n"
                     "Got a forward you're unsure about? Check it free on Sach: https://s.example",
                     "F Checked by BOOM\nFalse.\n\nClaim checked: “Fake vaccine news”\n\n"
                     "Full evidence: https://s.example/?r=0123456789ab\n\n"
                     "Got a forward you're unsure about? Check it free on Sach: https://s.example"),
}
OLD_CARD_DATA = {
    "false_live": {"claim": "Government will give Rs 5000 to every woman. Forward to all groups!", "date": "2026-11-10", "lang": "en",
                   "source": "PIB (Press Information Bureau)", "verdict": "FALSE", "why": "PIB says this claim is false.", "word": "FALSE", "word_en": "FALSE"},
    "unv_live": {"claim": "Cow urine cures every disease", "date": "", "lang": "en", "source": "", "verdict": "UNVERIFIED",
                 "why": "We found no official source that confirms or denies this. Do not treat it as fact.", "word": "UNVERIFIED", "word_en": "UNVERIFIED"},
    "match_single": {"claim": "Fake vaccine news", "date": "2026-11-01", "lang": "en",
                     "match": {"checker": "BOOM", "rating_text": "False", "review_date": "2026-11-01", "review_url": "https://www.boomlive.in/x"},
                     "source": "BOOM fact-check", "verdict": "FALSE",
                     "why": 'Checked by BOOM on 2026-11-01: rated "False". Sach did not run its own check.', "word": "False", "word_en": "False"},
}


def single_fixtures():
    fx = {
        "false_live": res([live("Government will give Rs 5000 to every woman. Forward to all groups!", "FALSE", url=PIB)], "FALSE",
                          card="X FALSE\nPIB says this claim is false.\nSource: PIB - " + PIB),
        "unv_live": res([live("Cow urine cures every disease", "UNVERIFIED")], "UNVERIFIED",
                        card="? UNVERIFIED\nWe found no official source that confirms or denies this. Do not treat it as fact."),
        "true_hi": res([live("सरकार ने नई योजना शुरू की है", "TRUE", url="https://finmin.gov.in/notice.pdf", source="Ministry of Finance",
                             tier="official")], "TRUE", lang="hi",
                       card="T सच\nFinance Ministry ने इसकी पुष्टि की है।\nस्रोत: Ministry of Finance - https://finmin.gov.in/notice.pdf"),
        "misl_fc": res([live("Train fares doubled", "MISLEADING", url=FC, source="Alt News", tier="factchecker")], "MISLEADING",
                       card="M MISLEADING\nPart is real (Alt News), numbers distorted.\nSource: Fact-checker (not official) - Alt News - https://altnews.in/story"),
        "match_single": res([matched("Fake vaccine news", "FALSE")], "FALSE", card="F Checked by BOOM\nFalse."),
    }
    fx["match_single"]["claims"][0]["match"]["review_url"] = "https://www.boomlive.in/x"      # as in the stored expectation
    return fx


@pytest.mark.parametrize("name", sorted(OLD))
def test_single_claim_share_text_is_exactly_as_before(name):
    r = single_fixtures()[name]
    plain, link = OLD[name]
    assert share.build_share_text(r, SITE) == plain
    assert share.build_share_text(r, SITE, LINK) == link


@pytest.mark.parametrize("name", sorted(OLD_CARD_DATA))
def test_single_claim_image_data_is_exactly_as_before(name):
    assert card_data(single_fixtures()[name]) == OLD_CARD_DATA[name]


# ---------------------------------------------------------------- every text and image: one headline verdict, claim matches its source

@pytest.mark.parametrize("claims, verdict", [
    ([live("Claim A", "UNVERIFIED"), live("Claim B", "FALSE", url=PIB)], "FALSE"),
    ([matched("Claim A", "FALSE"), live("Claim B", "UNVERIFIED")], "FALSE"),
    ([live("Claim A", "TRUE", url=FC, source="Alt News", tier="factchecker"), live("Claim B", "FALSE", url=PIB)], "FALSE"),
])
def test_shared_text_and_image_agree_on_the_driver(claims, verdict):
    r = res(claims, verdict)
    drv = share.driver_claim(r)
    t = share.build_share_text(r, SITE)
    assert first_line(t).startswith(EMOJI[verdict] + " " + verdict)           # one headline, the overall word
    cd = card_data(r)
    assert cd["verdict"] == verdict and cd["claim"] == drv["claim"]["text"]
    if drv.get("layer") == "match":
        assert cd["match"]["review_url"] == REVIEW
    else:
        assert cd["source"] == drv["citations"][0]["source"]
    assert drv["claim"]["text"] in t and f"{EMOJI[drv['verdict']]} " in t
    script = card_data_script(r)
    assert drv["claim"]["text"] in script


def test_image_word_is_the_driver_not_another_checkers_rating():
    """A live FALSE claim next to a matched TRUE rating: the image names FALSE and the live claim, never the checker's TRUE."""
    r = res([live("Live false claim", "FALSE", url=PIB), matched("Matched true claim", "TRUE", rating="True")], "FALSE")
    cd = card_data(r)
    assert cd["word"] == "FALSE" and cd["claim"] == "Live false claim" and "match" not in cd


def test_image_for_matched_driver_names_the_checker():
    r = res([live("Live unverified", "UNVERIFIED"), matched("Matched false claim", "FALSE")], "FALSE")
    cd = card_data(r)
    assert cd["match"]["checker"] == "BOOM" and cd["claim"] == "Matched false claim" and cd["word"] == "False"


# ---------------------------------------------------------------- no HTML injection through claim text

def test_claim_text_cannot_inject_markup_into_share_or_image_data():
    evil = '</script><img src=x onerror=alert(1)> “quoted” & 100%'
    r = res([live("harmless", "UNVERIFIED"), live(evil, "FALSE", url=PIB)], "FALSE")
    btns, data = share.result_share_html(r, SITE)
    assert "<img" not in btns and "%3Cimg" in btns                           # the wa.me href is percent-encoded
    assert data.count("</script>") == 1 and "<img" not in data and "\\u003c" in data
    script = card_data_script(r)
    assert script.count("</script>") == 1 and "<img" not in script and "\\u003c" in script


# ---------------------------------------------------------------- incomplete checks: wording, placement, button, tipline

INCOMPLETE_CASES = [
    {"degraded": True, "search_status": "ok"},
    {"degraded": False, "search_status": "down"},
    {"degraded": False, "search_status": "partial"},
    {"degraded": True, "search_status": "down"},
]


def unverified_escalated(**kw):
    claims = [live("Cow urine cures every disease", "UNVERIFIED")]
    return res(claims, "UNVERIFIED", card=render_card("UNVERIFIED", "en", []),
               trace={"layer": "ESCALATED", "claims_extracted": 1, "overall_rule": "x", "degraded": False}, **kw)


@pytest.mark.parametrize("flags", INCOMPLETE_CASES)
def test_incomplete_page_shows_notice_above_card_and_no_found_nothing_wording(flags):
    r = unverified_escalated(**flags)
    assert incomplete(r)
    page = site.result_block(r, chosen=False, link=None, text="forward", lang_choice="auto")
    notice = tr(INCOMPLETE_NOTICE, "en")
    assert notice in page
    assert page.index(notice) < page.index('id="cardtext"')                  # above the card and its buttons
    assert page.index(notice) < page.index('id="shareWa"')
    assert NO_SOURCE not in page.lower()
    assert "We found no official source" not in page
    assert "Sach could not finish checking this. This is not a finding that nothing exists." in page   # the card's why-line
    assert r["verdict"] == "UNVERIFIED"


@pytest.mark.parametrize("flags", INCOMPLETE_CASES)
def test_incomplete_share_text_and_tipline_text_say_could_not_finish(flags):
    r = unverified_escalated(**flags)
    t = share.build_share_text(r, SITE)
    assert INC_EN in t and "no official source" not in t.lower()
    assert first_line(t).startswith("❔ UNVERIFIED")                          # the verdict is still UNVERIFIED
    btns, _ = share.result_share_html(r, SITE)
    assert 'class="btn ghost" id="shareWa"' in btns                          # quieter than the 'try again later' hint
    tip = unquote(match.escalation_lines(r, SITE))
    assert "Sach could not finish checking this" in tip and "no official source was found" not in tip
    for o in match.escalation_options(match.escalation_claim(r), SITE, True):
        assert "Sach could not finish checking this" in unquote(o["url"]) and "no official source" not in unquote(o["url"])


@pytest.mark.parametrize("flags", INCOMPLETE_CASES)
def test_incomplete_sharing_has_no_sticky_bar_and_quiet_flag(flags):
    _, data = share.result_share_html(unverified_escalated(**flags), SITE)
    assert '"quiet": true' in data


def test_incomplete_escalation_panel_note_is_not_found_nothing():
    page = site.result_block(unverified_escalated(degraded=True), chosen=False, link=None, text="f", lang_choice="auto")
    assert tr(INCOMPLETE_ESC_NOTE, "en") in page and "We found no official source for this." not in page


def test_complete_checks_keep_the_found_nothing_wording_and_no_notice():
    r = unverified_escalated()
    assert not incomplete(r)
    page = site.result_block(r, chosen=False, link=None, text="f", lang_choice="auto")
    assert "We found no official source that confirms or denies this." in page
    assert "Sach could not finish checking" not in page
    assert 'class="btn wa" id="shareWa"' in page
    assert "We found no official source that confirms or denies this." in share.build_share_text(r, SITE)
    assert "found no official source for it" in unquote(match.escalation_lines(r, SITE))
    _, data = share.result_share_html(r, SITE)
    assert '"quiet"' not in data


def test_complete_multi_claim_text_has_no_incomplete_wording():
    r = res([live("Cow urine cures", "UNVERIFIED"), live("the false one", "FALSE", url=PIB)], "FALSE")
    t = share.build_share_text(r, SITE)
    assert INC_EN not in t


def test_incomplete_verdict_word_stays_unverified_and_image_says_could_not_finish():
    r = unverified_escalated(degraded=True)
    cd = card_data(r)
    assert cd["verdict"] == "UNVERIFIED" and cd["word"] == "UNVERIFIED"
    assert cd["why"] == "Sach could not finish checking this. This is not a finding that nothing exists."


@pytest.mark.parametrize("lang, fragment", [("hi", "जाँच पूरी नहीं कर सका"), ("te", "పూర్తి చేయలేకపోయింది")])
def test_incomplete_wording_in_hindi_and_telugu(lang, fragment):
    r = unverified_escalated(degraded=True, language=lang, input_language=lang)
    r["card"] = render_card("UNVERIFIED", lang, [])
    assert fragment in share.build_share_text(r, SITE)
    assert fragment in site.result_block(r, chosen=False, link=None, text="f", lang_choice=lang)
    assert fragment in card_data(r)["why"]


def test_incomplete_notice_falls_back_to_english_for_unlisted_language():
    assert tr(INCOMPLETE_NOTICE, "mr") is INCOMPLETE_NOTICE["en"]
    assert tr(INCOMPLETE_NOTICE, "mni") is INCOMPLETE_NOTICE["en"]
    r = unverified_escalated(degraded=True, language="mr", input_language="mr")
    r["card"] = render_card("UNVERIFIED", "mr", [])
    page = site.result_block(r, chosen=False, link=None, text="f", lang_choice="mr")
    assert tr(INCOMPLETE_NOTICE, "en") in page


# ---------------------------------------------------------------- verdict-aware incompleteness (defect 1)

DECISIVE_INCOMPLETE = [
    {"degraded": True, "search_status": "ok"},
    {"degraded": False, "search_status": "down"},
    {"degraded": False, "search_status": "partial"},
    {"degraded": True, "search_status": "partial"},
]


@pytest.mark.parametrize("flags", DECISIVE_INCOMPLETE)
@pytest.mark.parametrize("verdict, text", [("FALSE", "Government will give Rs 5000 to every woman."), ("TRUE", "Vaccine is safe.")])
def test_decisive_verdict_with_incomplete_search_is_not_incomplete(flags, verdict, text):
    base = [live(text, verdict, url=PIB)]
    r = res(base, verdict, **flags)
    done = res(base, verdict)
    assert not incomplete(r)
    assert share.build_share_text(r, SITE) == share.build_share_text(done, SITE)
    assert share.result_share_html(r, SITE) == share.result_share_html(done, SITE)
    assert "could not finish" not in share.build_share_text(r, SITE).lower()
    page = site.result_block(r, chosen=False, link=None, text="forward", lang_choice="auto")
    assert INC_EN not in page and tr(INCOMPLETE_NOTICE, "en") not in page
    assert 'class="btn wa" id="shareWa"' in page
    assert '"quiet"' not in share.result_share_html(r, SITE)[1]


def test_decisive_false_with_partial_search_keeps_its_card_wording():
    r = res([live("Govt gives 5000", "FALSE", url=PIB)], "FALSE", search_status="partial")
    assert r["card"].split("\n")[1] == "PIB (Press Information Bureau) says this claim is false."
    assert "could not finish" not in card_data(r)["why"]


def test_unverified_with_incomplete_search_still_incomplete_wording():
    r = unverified_escalated(search_status="partial")
    assert incomplete(r)


# ---------------------------------------------------------------- Telegram reply: sources of the driver only (defect 2)

def tg(r):
    from sach.telegram_bot import format_reply
    return format_reply(r)


def test_telegram_more_sources_never_list_an_unverified_claims_link():
    other = "https://altnews.in/fact-of-cow-urine"
    r = res([live("Cow urine cures every disease", "UNVERIFIED", url=other, source="AltNews"), matched("the false one", "FALSE")], "FALSE")
    text = tg(r)
    assert other not in text and "altnews" not in text.lower()
    assert REVIEW in text                                              # the matched driver's own review link


def test_telegram_driver_pib_source_is_listed_and_other_claims_link_is_not():
    other = "https://altnews.in/fact-of-cow-urine"
    r = res([live("Cow urine cures every disease", "UNVERIFIED", url=other, source="AltNews"),
             live("Govt gives 5000", "FALSE", url=PIB)], "FALSE")
    text = tg(r)
    assert PIB in text and other not in text


def test_telegram_multi_claim_lines_name_each_claim_with_its_own_word():
    r = res([live("Cow urine cures every disease", "UNVERIFIED"), matched("the false one", "FALSE")], "FALSE")
    text = tg(r)
    assert "❔ UNVERIFIED: “Cow urine cures every disease”" in text
    assert "❌ False by BOOM: “the false one”" in text


def test_telegram_single_claim_has_no_per_claim_lines():
    r = res([live("Govt gives 5000", "FALSE", url=PIB)], "FALSE")
    assert "❌ FALSE: “" not in tg(r)


# ---------------------------------------------------------------- JSON API: card and card_en are verdict-aware (defect 3)

def test_json_api_incomplete_unverified_card_says_could_not_finish(server, monkeypatch):
    import sach.web as W
    raw = unverified_escalated(degraded=True)
    raw["card_en"] = render_card("UNVERIFIED", "en", [])
    monkeypatch.setattr(W, "check_forward", lambda *a, **k: dict(raw))
    code, body = _post(server, "Cow urine cures every disease", "/?format=json")
    d = json.loads(body)
    assert code == 200 and d["verdict"] == "UNVERIFIED"
    assert INC_EN in d["card"] and NO_SOURCE not in d["card"].lower()
    assert INC_EN in d["card_en"] and NO_SOURCE not in d["card_en"].lower()
    assert set(raw) <= set(d)                                          # no key removed


def test_json_api_complete_checks_are_byte_identical(server, monkeypatch):
    import sach.web as W
    raw = unverified_escalated()
    raw["card_en"] = render_card("UNVERIFIED", "en", [])
    monkeypatch.setattr(W, "check_forward", lambda *a, **k: dict(raw))
    code, body = _post(server, "Cow urine cures every disease", "/?format=json")
    d = json.loads(body)
    assert d["card"] == raw["card"] and d["card_en"] == raw["card_en"]
    assert NO_SOURCE in d["card"].lower()


# ---------------------------------------------------------------- matched verdict pairing (defect 4)

def cv(layer, verdict, match=None):
    return SimpleNamespace(layer=layer, verdict=verdict, match=match or {})


VISHVAS = {"checker": "Vishvas News", "rating_text": "True", "review_url": "https://vishvasnews.com/x"}


def test_top_match_does_not_pair_a_live_false_with_a_matched_true():
    assert match.top_match([cv("live", "FALSE"), cv("match", "TRUE", VISHVAS)], "FALSE") == {}


def test_top_match_returns_the_driver_match_for_the_overall_verdict():
    boom = {"checker": "BOOM", "rating_text": "False"}
    assert match.top_match([cv("live", "UNVERIFIED"), cv("match", "FALSE", boom)], "FALSE") == boom
    assert match.top_match([cv("match", "FALSE", boom), cv("match", "TRUE", VISHVAS)], "FALSE") == boom
    assert match.top_match([cv("match", "TRUE", VISHVAS), cv("live", "FALSE")], "FALSE") == {}


# ---------------------------------------------------------------- ClaimReview picks the driver (defect 5)

def test_claimreview_uses_the_claim_behind_the_overall_verdict():
    from sach import claimreview
    r = {"verdict": "FALSE", "claims": [live("Cow urine cures every disease", "UNVERIFIED", url=FC, source="AltNews"),
                                        live("Govt gives 5000", "FALSE", url=PIB)],
         "language": "en", "checked_at": "2026-11-12T09:30:00+00:00"}
    out = claimreview.result_review(r, LINK, SITE)
    assert out and out["claimReviewed"] == "Govt gives 5000"
    assert out["itemReviewed"] and FC not in json.dumps(out)


# ---------------------------------------------------------------- source-less cards (defect 6)

@pytest.mark.parametrize("lang, verdict, phrase", [
    ("en", "FALSE", "This claim is false."),
    ("hi", "FALSE", "यह दावा झूठ है।"),
    ("te", "FALSE", "ఈ దావా అబద్ధం."),
    ("en", "TRUE", "This claim is confirmed."),
    ("hi", "TRUE", "इस दावे की पुष्टि हुई है।"),
    ("te", "TRUE", "ఈ దావా ధృవీకరించబడింది."),
])
def test_card_without_citations_drops_the_source_phrase(lang, verdict, phrase):
    card = render_card(verdict, lang, [])
    lines = card.split("\n")
    assert len(lines) == 2 and lines[1] == phrase
    assert "says" not in card and "()" not in card and "  " not in card and not lines[1].startswith(" ")


@pytest.mark.parametrize("lang", ["en", "hi", "te"])
def test_misleading_card_without_citations_has_no_empty_brackets(lang):
    card = render_card("MISLEADING", lang, [])
    assert "()" not in card and "( )" not in card and "{src}" not in card
    assert card.split("\n")[1].strip()


def test_card_with_citations_is_unchanged():
    c = render_card("FALSE", "en", [cite(PIB)])
    assert c == "❌ FALSE\nPIB (Press Information Bureau) says this claim is false.\nSource: PIB (Press Information Bureau) - " + PIB
