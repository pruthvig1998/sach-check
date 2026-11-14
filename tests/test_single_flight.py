"""Phase 1 of the scale design: one live check per new claim at a time (single-flight), claim-cache hits never use a live slot, and a busy reply that
is useful (related PIB pages from the local index, demand recorded) without ever giving a verdict. Offline: fake store, no network."""
import json
import pytest
from test_scale import FakeStore
from test_cache_trace import run, FALSE_TEXT, PIB, _fresh_store          # noqa: F401
from sach import cache, limits, popularity, store
from sach.pipeline import check_forward

WRAPPED = "Good morning all 🌹\nForwarded many times\nGovernment will give Rs 5000 to every woman.\nShare with all your groups 🙏"


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setenv("SACH_MAX_LIVE_PER_MIN", "50"); monkeypatch.setenv("SACH_MAX_LIVE_PER_DAY", "500")
    monkeypatch.delenv("SACH_SINGLE_FLIGHT", raising=False); monkeypatch.setenv("SACH_FLIGHT_WAIT_S", "5")
    monkeypatch.setattr(limits, "_sleep", lambda s: None)
    limits.reset_memory()


def test_the_first_ask_leads_and_a_second_ask_of_the_same_claim_waits_for_its_answer(monkeypatch):
    st = FakeStore()
    leader = limits.admit(FALSE_TEXT, st=st)
    assert leader.kind == "live" and leader.flight.startswith("sf:")
    polls = {"n": 0}
    real = limits._is_free
    def free_after_two_polls(text, rl):
        polls["n"] += 1
        return polls["n"] > 3 and True                       # the leader's answer lands in the cache during the wait (first calls are the entry checks)
    monkeypatch.setattr(limits, "_is_free", free_after_two_polls)
    follower = limits.admit(FALSE_TEXT, st=st)
    assert follower.kind == "free" and follower.flight == ""
    assert st.c[leader.flight] == 1                          # the follower gave its own place back


def test_a_follower_is_told_the_claim_is_being_checked_and_gets_no_verdict(monkeypatch):
    st = FakeStore()
    limits.admit(FALSE_TEXT, st=st)
    monkeypatch.setattr(limits, "_is_free", lambda t, r: False)
    follower = limits.admit(FALSE_TEXT, st=st)
    assert follower.busy and follower.reason == "flight" and follower.retry_after == 20
    body = limits.busy_result("flight", 20, FALSE_TEXT)
    assert "verdict" not in body and body["title"] == "This message is being checked right now" and "second, duplicate check" in body["message"]
    assert "related_official_pages" not in body              # nothing is shown for a claim that is already being checked


def test_the_lock_is_released_and_the_next_ask_leads_again():
    st = FakeStore()
    a = limits.admit(FALSE_TEXT, st=st)
    limits.release(a, st=st)
    b = limits.admit(FALSE_TEXT, st=st)
    assert b.kind == "live" and b.flight == a.flight


def test_wrapper_variants_and_different_claims(monkeypatch):
    st = FakeStore()
    a = limits.admit(FALSE_TEXT, st=st)
    b = limits.admit("Government will give Rs 9999 to every farmer under a brand new yojana.", st=st)     # a different claim: its own flight
    assert a.kind == "live" and b.kind == "live" and a.flight != b.flight
    assert limits._flight_key(FALSE_TEXT, None) == limits._flight_key(WRAPPED, None)       # the same claims under a different wrapper share one flight
    assert limits._flight_key(FALSE_TEXT, None) != limits._flight_key(FALSE_TEXT, "hi")     # a different reply language is its own flight


def test_a_claim_cache_hit_is_free_and_uses_no_live_slot():
    first, _ = run(FALSE_TEXT)                                # stores the answer under the exact key and the claim key
    st = FakeStore()
    adm = limits.admit(WRAPPED, st=st)                        # same claims, different wrapper text
    assert adm.kind == "free" and st.incr_calls == 0 and not any(k.startswith("lv:") for k in st.c)


def test_the_budget_still_applies_and_returns_the_flight_when_refused(monkeypatch):
    monkeypatch.setenv("SACH_MAX_LIVE_PER_MIN", "1")
    st = FakeStore()
    one = limits.admit(FALSE_TEXT, st=st)
    two = limits.admit("Government will give Rs 8000 to every student under a new scheme.", st=st)
    assert one.kind == "live" and two.busy and two.reason == "minute"
    assert st.c.get(limits._flight_key("Government will give Rs 8000 to every student under a new scheme.", None), 0) == 0   # a refused ask holds no flight


def test_the_switch_and_a_broken_store_never_block_anyone(monkeypatch):
    monkeypatch.setenv("SACH_SINGLE_FLIGHT", "0")
    st = FakeStore()
    assert limits.admit(FALSE_TEXT, st=st).flight == "" and limits.admit(FALSE_TEXT, st=st).kind == "live"      # two asks, no waiting
    monkeypatch.delenv("SACH_SINGLE_FLIGHT")
    assert limits.admit(FALSE_TEXT, st=FakeStore(broken=True)).kind == "live"


def test_the_busy_page_lists_related_pib_pages_records_demand_and_has_no_verdict(monkeypatch, tmp_path):
    from sach import index as pib_index
    idx = tmp_path / "idx.jsonl"
    idx.write_text(json.dumps({"prid": "2260621", "title": "Cabinet approves scheme for coal and lignite gasification projects", "excerpt": "The Union Cabinet approved coal and lignite gasification projects with an outlay of Rs 37,500 crore."}) + "\n", encoding="utf-8")
    monkeypatch.setattr(pib_index, "INDEX_PATH", str(idx)); pib_index._cache.update(key=None, rows=[])
    text = "The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore."
    block = limits.busy_block("day", text)
    assert "PRID=2260621" in block and "not a verdict" in block and "coal and lignite" in block
    body = limits.busy_result("day", 600, text)
    assert "verdict" not in body and body["related_official_pages"][0]["url"].endswith("PRID=2260621")
    st = store.get_store()
    popularity.record_unchecked(text, "day", st=st)
    s = popularity.summary(st)
    assert s["unchecked_requests"] == 1 and s["distinct_claims"] == 1
    assert "coal" not in json.dumps(s)                        # still no claim text anywhere
