"""Privacy-safe popularity counters. The properties that matter: no claim text, IP or identity is ever stored; counts and thresholds are right;
a failing store never breaks a request; the switch turns it off."""
import json, os
import pytest
from sach import cache, ledger, popularity, store
from test_cache_trace import run, FALSE_TEXT, _fresh_store        # noqa: F401

import calendar
DAY = float(calendar.timegm((2026, 11, 14, 0, 0, 0)))          # 14 Nov 2026 00:00 UTC
OUT = {"layer": "live", "verdict": "UNVERIFIED", "claims": [{"claim": {"text": "Government will give Rs 5000 to every woman."}}]}


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.delenv("SACH_POPULARITY", raising=False)


def _all_store_content(st):
    """Every key and value the file store holds, as one string, to prove what was (not) stored."""
    blob = []
    for root, _, files in os.walk(st.dir):
        for f in files:
            blob.append(f); blob.append(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read())
    return "\n".join(blob)


def test_nothing_that_identifies_a_person_or_a_message_is_stored():
    st = store.get_store()
    secret_claim = "Rahul Sharma of 22 MG Road, phone 9876543210, will get Rs 5000 from the scheme."
    for _ in range(3):
        popularity.record({"layer": "live", "verdict": "UNVERIFIED", "claims": [{"claim": {"text": secret_claim}}], "ip": "203.0.113.7", "user": "u1"}, False, now=DAY, st=st)
    content = _all_store_content(st)
    for needle in ("Rahul", "9876543210", "MG Road", "5000", "203.0.113.7", "u1", "scheme"):
        assert needle not in content, needle
    fp = popularity.fingerprint([secret_claim])
    assert len(fp) == 16 and fp in content and f"pop:20261114:{fp}" in content.replace("sach:", "").replace("c:", "")


def test_counts_layers_distinct_claims_and_thresholds():
    st = store.get_store()
    other = {"layer": "match", "verdict": "FALSE", "claims": [{"claim": {"text": "A different claim about a different scheme entirely."}}]}
    for _ in range(5):
        popularity.record(OUT, False, now=DAY, st=st)
    popularity.record(OUT, True, now=DAY, st=st)                            # a cached repeat of the same claim
    popularity.record(other, False, now=DAY, st=st)
    s = popularity.summary(st, now=DAY)
    assert s["requests"] == 7 and s["distinct_claims"] == 2
    assert s["by_layer"]["live"] == 5 and s["by_layer"]["cache_exact"] == 1 and s["by_layer"]["match"] == 1
    assert s["claims_asked_at_least"] == {"2": 1, "5": 1, "50": 0, "500": 0, "5000": 0}      # one claim reached 6 asks, the other reached 1
    assert s["requests_that_were_repeats_at_least"]["2"] == 5 and s["requests_that_were_repeats_at_least"]["5"] == 2
    assert s["repeat_share"] == round(1 - 2 / 7, 4) and s["answered_without_paid_check"] == round(2 / 7, 4)


def test_the_day_rolls_over_at_utc_midnight():
    st = store.get_store()
    popularity.record(OUT, False, now=DAY + 86399, st=st); popularity.record(OUT, False, now=DAY + 86400, st=st)
    assert popularity.summary(st, now=DAY)["requests"] == 1 and popularity.summary(st, now=DAY + 86400)["requests"] == 1
    assert popularity.summary(st, now=DAY)["distinct_claims"] == 1 and popularity.summary(st, now=DAY + 86400)["distinct_claims"] == 1   # new day, new count


def test_wrapper_variants_share_one_fingerprint_and_different_claims_do_not():
    f = popularity.fingerprint
    assert f(["Government will give Rs 5000 to every woman."]) == f(["government will give rs 5000 to every woman"])
    assert f(["Government will give Rs 5000 to every woman."]) != f(["Government will give Rs 5001 to every woman."])
    assert f([]) == "" and f(["", "  "]) == ""


def test_a_failing_store_never_breaks_anything():
    class Broken:
        def incr(self, *a, **k): raise RuntimeError("down")
        def expire(self, *a, **k): raise RuntimeError("down")
        def counters(self, *a, **k): raise RuntimeError("down")
    popularity.record(OUT, False, now=DAY, st=Broken())                       # does not raise
    assert popularity.summary(Broken(), now=DAY)["requests"] == 0


def test_the_switch_turns_it_off(monkeypatch):
    monkeypatch.setenv("SACH_POPULARITY", "0")
    st = store.get_store(); popularity.record(OUT, False, now=DAY, st=st)
    assert popularity.summary(st, now=DAY)["requests"] == 0


def test_every_real_path_is_counted_through_the_ledger_choke_point():
    first, _ = run(FALSE_TEXT)                                                # a live check
    second, _ = run(FALSE_TEXT)                                               # served from the exact cache
    third, _ = run("Good morning all 🌹\nGovernment will give Rs 5000 to every woman.\nShare with all your groups 🙏")   # same claims, different wrapper
    s = popularity.summary()
    assert s["requests"] == 3 and s["by_layer"]["cache_exact"] == 1 and s["by_layer"]["cache_claims"] == 1 and s["by_layer"]["live"] == 1
    assert s["distinct_claims"] == 1 and s["claims_asked_at_least"]["2"] == 1
    assert s["answered_without_paid_check"] == round(2 / 3, 4)


def test_the_status_data_and_the_privacy_page_describe_it():
    from sach import status, legal
    d = status.status_data(None, None)
    assert "reuse" in d and "No text, no IP address and no user identity" in d["reuse"]["note"]
    page = legal.privacy_page() if hasattr(legal, "privacy_page") else ""
    html = page.decode() if isinstance(page, bytes) else str(page)
    assert (not html) or "anonymous one-way fingerprint" in html
