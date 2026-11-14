"""Hindi and Telugu language-review fixes (directive 10): incomplete-check notices, escalation question, vocabulary, labels.
Strings are pinned verbatim; none of this changes a verdict, a threshold or retrieval."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from sach import i18n, match, models, scamsigns, site, telegram_bot, voice
from sach.pipeline import check_forward
from test_search import CLAIM, Judge, StatusRetriever      # noqa: F401


def _unverified(lang, **extra):
    res = check_forward(CLAIM, [StatusRetriever(answered=0)], Judge(), log=False)     # search down, so a limited UNVERIFIED result
    res = dict(res, language=lang, **extra)
    return res


def test_search_down_notice_is_localised_and_has_no_heading_leftover():
    for lang, needle in (("en", "Web search was unavailable for this check, so Sach could only use its built-in list of published PIB fact-checks."),
                         ("hi", "इस जाँच के लिए वेब खोज उपलब्ध नहीं थी"),
                         ("te", "ఈ తనిఖీకి వెబ్ శోధన అందుబాటులో లేదు")):
        assert needle in site.result_block(_unverified(lang))


def test_degraded_notice_is_localised_and_no_longer_tells_users_to_check_cited_sources():
    assert "Check the cited sources" not in i18n.DEGRADED_NOTICE["en"]
    assert "it is not proof the claim is false" in i18n.DEGRADED_NOTICE["en"]
    for lang, needle in (("en", "Limited check."), ("hi", "सीमित जाँच।"), ("te", "పరిమిత తనిఖీ.")):
        assert needle in site.result_block(_unverified(lang, degraded=True))


def test_timed_out_rule_text_in_hindi_and_telugu_only_for_that_rule():
    ct = {"rule": "timed_out", "rule_text": models.RULE_TEXT["timed_out"]}
    assert models.localized_rule_text(ct, "en") == models.RULE_TEXT["timed_out"]
    assert models.localized_rule_text(ct, "hi") == "जाँच पूरी होने से पहले समय खत्म हो गया, इसलिए नतीजा पुष्टि नहीं हुई है।"
    assert models.localized_rule_text(ct, "te") == "తనిఖీ పూర్తి కాకముందే సమయం అయిపోయింది, కాబట్టి ఫలితం ధృవీకరించబడలేదు."
    other = {"rule": "no_evidence", "rule_text": models.RULE_TEXT["no_evidence"]}
    assert models.localized_rule_text(other, "hi") == models.RULE_TEXT["no_evidence"]       # other rules stay English


def test_escalation_question_is_localised_and_the_incomplete_variant_stays_honest():
    en = match.escalation_text("Free laptops for all.", "https://sach.example")
    assert en == "Please fact-check this message: Free laptops for all. I checked it on Sach (https://sach.example), but Sach found no official source for it."
    hi = match.escalation_text("Free laptops for all.", "https://sach.example", lang="hi")
    assert hi.startswith("कृपया इस संदेश की जाँच करें: Free laptops for all.") and "Sach (https://sach.example)" in hi and "आधिकारिक स्रोत" in hi
    te = match.escalation_text("Free laptops for all.", "https://sach.example", lang="te")
    assert te.startswith("దయచేసి ఈ సందేశాన్ని తనిఖీ చేయండి: Free laptops for all.") and "అధికారిక మూలం" in te
    inc = match.escalation_text("Free laptops for all.", "https://sach.example", incomplete=True, lang="hi")
    assert "could not finish checking" in inc and "no official source" not in inc
    assert match.escalation_text("x", "s", lang="mr") == match.escalation_text("x", "s")      # no table for the language: English


def test_escalation_note_hindi_and_telugu_replaced():
    assert match.ESC_NOTE["hi"].startswith("हमें इसके लिए कोई आधिकारिक स्रोत नहीं मिला।") and "सरकारी" not in match.ESC_NOTE["hi"]
    assert match.ESC_NOTE["te"].startswith("దీనికి అధికారిక మూలం దొరకలేదు.")


def test_official_vocabulary_is_standardised_in_hindi_and_telugu():
    assert i18n.WHY["hi"]["UNVERIFIED"] == "हमें इसकी पुष्टि या इसका खंडन करने वाला कोई आधिकारिक स्रोत नहीं मिला। इसे सच न मानें।"
    assert i18n.WHY["te"]["UNVERIFIED"] == "దీనిని ధృవీకరించే లేదా ఖండించే అధికారిక మూలం మాకు దొరకలేదు. దీన్ని నిజమని నమ్మవద్దు."
    assert i18n.LABEL["te"]["UNVERIFIED"] == "ధృవీకరించబడలేదు"
    assert i18n.LABEL["hi"]["UNVERIFIED"] == "पुष्टि नहीं हुई"             # untouched
    assert "सरकारी" not in i18n.FC_NOTE["hi"] and "आधिकारिक" in i18n.FC_NOTE["hi"]
    hi_panel = i18n.UNVERIFIED_PANEL["hi"]
    assert "सरकारी" not in hi_panel["official"] and "सरकारी" not in hi_panel["meaning"]


def test_progress_message_uses_the_native_unverified_word():
    assert "UNVERIFIED" not in voice.STRINGS["hi"]["still"] and "पुष्टि नहीं हुई" in voice.STRINGS["hi"]["still"]
    assert "UNVERIFIED" not in voice.STRINGS["te"]["still"] and "ధృవీకరించబడలేదు" in voice.STRINGS["te"]["still"]


def test_scam_box_advice_names_the_official_site_in_hindi_and_telugu():
    hi, te = scamsigns.UI["hi"], scamsigns.UI["te"]
    assert hi["intro"] == "ये ठगों के आम तरीके हैं। इनसे तथ्यों का सच तय नहीं होता, और ये ऊपर दिए गए नतीजे को नहीं बदलते।"
    assert hi["advice"] == "OTP या PIN किसी को न बताएँ। अनजाने लिंक पर क्लिक न करें। आधिकारिक वेबसाइट का पता खुद टाइप करके जाँचें।"
    assert te["advice"] == "OTP లేదా PIN ఎవరికీ చెప్పకండి. తెలియని లింక్‌లను క్లిక్ చేయకండి. అధికారిక వెబ్‌సైట్ అడ్రస్‌ను మీరే టైప్ చేసి సరిచూడండి."


def test_telegram_welcome_is_gender_neutral_and_the_degraded_note_is_localised():
    assert "बताऊँगा" not in telegram_bot.WELCOME and "यहाँ कोई भी फ़ॉरवर्ड भेजें, स्रोत के साथ जाँच मिलेगी।" in telegram_bot.WELCOME
    assert set(i18n.TG_DEGRADED_NOTE) == {"en", "hi", "te"}
    assert i18n.TG_DEGRADED_NOTE["en"].startswith("Note: part of my AI check was unavailable")


def test_no_em_dash_in_the_new_strings():
    tables = [i18n.DEGRADED_NOTICE, i18n.SEARCH_DOWN_NOTICE, i18n.TG_DEGRADED_NOTE, match.ESC_NOTE, match.ESC_QUESTION, models.RULE_TEXT_TIMED_OUT]
    for t in tables:
        for v in t.values():
            assert "—" not in v
