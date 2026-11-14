"""L0: the cache is also keyed by the extracted claims, so wrapper text (greetings, 'forwarded', emoji) does not cause a second paid check.
It must never merge different claims (different figure, negation, language) and never show one user's skipped sentences to another."""
import json
import pytest
from test_cache_trace import run, FALSE_TEXT, _fresh_store      # noqa: F401  (autouse fixture re-exported)
from sach import cache

WRAPPED = "Good morning! 🌹🌹 Forwarded many times\nGovernment will give Rs 5000 to every woman.\nShare with all your groups 🙏 जय हिंद"


def test_wrapper_text_reuses_the_checked_answer_without_a_new_search():
    first, r1 = run(FALSE_TEXT)
    assert not first.get("cached") and r1.calls == 1
    second, r2 = run(WRAPPED)
    assert second["cached"] and second["cache_kind"] == "claims" and r2.calls == 0
    assert second["verdict"] == first["verdict"] and second["trace"]["layer"] == "CACHE"


def test_a_different_figure_or_a_negation_is_a_different_claim():
    run(FALSE_TEXT)
    other, r = run("Government will give Rs 6000 to every woman.")
    assert not other.get("cached") and r.calls == 1
    neg, r2 = run("Government will not give Rs 5000 to every woman.")
    assert not neg.get("cached") and r2.calls == 1


def test_reply_language_keeps_separate_answers():
    run(FALSE_TEXT, reply_lang="hi")
    en, r = run(WRAPPED, reply_lang="en")
    assert not en.get("cached") and r.calls == 1


def test_other_users_skipped_sentences_are_not_shown():
    run("Government will give Rs 5000 to every woman. Please forward secret-phrase-alpha to all groups!")
    second, _ = run(WRAPPED)
    assert second["cached"] and second["cache_kind"] == "claims"
    assert "alpha" not in json.dumps(second.get("extraction") or {}) and "alpha" not in json.dumps(second["card"])


def test_switch_off(monkeypatch):
    monkeypatch.setenv("SACH_CLAIM_CACHE", "0")
    run(FALSE_TEXT)
    out, r = run(WRAPPED)
    assert not out.get("cached") and r.calls == 1


def test_claim_key_ignores_light_punctuation_and_case_only():
    k = cache.claim_key
    assert k(["Government will give Rs 5000 to every woman."], None) == k(["government will give rs 5000 to every woman"], None)
    assert k(["Government will give Rs 5000 to every woman"], None) != k(["Government will give Rs 5001 to every woman"], None)
    assert k([], None) is None and k(["", "  "], None) is None
