"""Speed safeguards: retrievers run in parallel, Brave fetches pages in parallel, a timed-out model is skipped briefly."""
import socket, time
import pytest
from sach import llm as LL
from sach.models import Evidence, TIER_PIB
from sach.pipeline import check_forward
from sach.retrieve import BraveRetriever

DEBUNK = Evidence("PIB Fact Check", "https://pib.gov.in/PressReleasePage.aspx?PRID=1618314", TIER_PIB, "2026-11-12T00:00:00+00:00",
                  "Claim that Government is giving Rs 1000 to everyone under Corona Sahayata Yojana is fake",
                  "PIB Fact Check: This claim is fake. No such scheme is being run by the Government.")

class _Slow:
    def __init__(self, delay, ev=None, log=None, name=""):
        self.delay, self.ev, self.log, self.name = delay, ev or [], log, name
    def search(self, q):
        time.sleep(self.delay)
        if self.log is not None: self.log.append(self.name)
        return list(self.ev)

def test_retrievers_run_in_parallel_and_keep_priority_order(monkeypatch):
    monkeypatch.setenv("SACH_NO_CACHE", "1")
    pib, web = _Slow(0.6, [DEBUNK], name="pib"), _Slow(0.6, [], name="web")
    t = time.monotonic()
    out = check_forward("Government is giving Rs 1000 to everyone under Corona Sahayata Yojana", [pib, web], None, log=False)
    took = time.monotonic() - t
    assert took < 1.1, took                                     # sequential would be at least 1.2 s
    assert out["verdict"] == "FALSE"                            # the PIB debunk still drives the verdict (limited mode)

def test_a_hung_retriever_does_not_lose_the_fast_one(monkeypatch):
    monkeypatch.setenv("SACH_NO_CACHE", "1")
    import sach.pipeline as P
    monkeypatch.setattr(P, "RETRIEVE_DEADLINE_S", 0.5)
    out = check_forward("Government is giving Rs 1000 to everyone under Corona Sahayata Yojana",
                        [_Slow(0.0, [DEBUNK]), _Slow(5.0, [])], None, log=False)
    assert out["verdict"] == "FALSE"

def test_brave_fetches_pages_in_parallel_and_keeps_search_order(monkeypatch):
    b = BraveRetriever(key="k")
    urls = [f"https://pib.gov.in/PressReleasePage.aspx?PRID={i}" for i in (11, 22, 33, 44)]
    monkeypatch.setattr(b, "_urls", lambda q, check, limit, count=10: urls if "pib.gov.in" in q else [])
    def slow_evidence(u, tier):
        time.sleep(0.3)
        return Evidence("PIB", u, tier, "2026-11-12T00:00:00+00:00", "t", "x")
    monkeypatch.setattr(b, "_evidence", slow_evidence)
    t = time.monotonic()
    out = b.search("some claim about a scheme")
    assert time.monotonic() - t < 1.0                           # 4 pages x 0.3 s serially would be 1.2 s
    assert [e.url for e in out][:4] == urls

class _TimeoutJudge(LL._Judge):
    name = "fake"
    def __init__(self):
        self.models, self.calls = ["slow-model", "fast-model"], []
    def _raw(self, model, system, user, max_tokens):
        self.calls.append(model)
        if model == "slow-model":
            raise socket.timeout("timed out")
        return "NEITHER | -"

def test_a_timed_out_model_is_skipped_on_the_next_call_but_the_key_stays_usable():
    j = _TimeoutJudge()
    assert j.stance("claim text here", "title", "page") == "none"
    assert j.calls == ["slow-model", "fast-model"] and j.available()
    j.calls.clear()
    j.stance("claim text here", "title", "page")
    assert j.calls == ["fast-model"]                            # the slow model is skipped for a while

def test_judge_timeouts_are_shorter_than_the_judging_window():
    import sach.pipeline as P
    assert LL.GeminiJudge(key="k").timeout < P.JUDGE_DEADLINE_S
    assert LL.OpenAICompatJudge("groq", "https://x", "k", "m").timeout < P.JUDGE_DEADLINE_S
