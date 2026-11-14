"""The no-LLM layers (L0 claim-keyed cache, L2 official-pages panel, L5 references) are display and reuse layers. For the same claims they must
never change a verdict, its rule, or which claims were checked. This test runs each scenario with the layers on and off and compares."""
import pytest
from test_cache_trace import CountingRetriever, FakeLLM, NoneLLM, PIB, OFFICIAL, FALSE_TEXT      # noqa: F401
from sach import store
from sach.models import Evidence, TIER_OFFICIAL
from sach.pipeline import check_forward

TS = "2026-11-14T00:00:00+00:00"
CONFIRM = Evidence("Ministry of Finance", "https://finmin.gov.in/budget", TIER_OFFICIAL, TS, "Union Budget", "The Union Cabinet has approved Rs 5000 crore for the scheme.")
SCENARIOS = [
    ("debunk", FALSE_TEXT, [PIB], FakeLLM),
    ("unverified", "Government will give Rs 7000 to every farmer under the new yojana.", [OFFICIAL], NoneLLM),
    ("no evidence", "Government will give Rs 8000 to every student under a new scheme.", [], NoneLLM),
]
WRAPPERS = ["{t}", "Good morning 🌹\nForwarded many times\n{t}\nShare with all your groups 🙏", "{t}\n\nplease forward to everyone"]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR", "SACH_CLAIM_CACHE", "SACH_SHOW_PAGES"):
        monkeypatch.delenv(k, raising=False)
    store.reset(); yield


def _essence(res):
    return {"verdict": res["verdict"], "layer": res.get("layer"), "claims": [(c["claim"]["text"], c["verdict"], c["reason_code"]) for c in res["claims"]]}


@pytest.mark.parametrize("name,text,ev,llm", SCENARIOS)
def test_layers_on_or_off_give_the_same_verdicts(monkeypatch, name, text, ev, llm):
    monkeypatch.setenv("SACH_CLAIM_CACHE", "0"); monkeypatch.setenv("SACH_SHOW_PAGES", "0")
    off = [_essence(check_forward(w.format(t=text), [CountingRetriever(list(ev))], llm(), log=True)) for w in WRAPPERS]
    store.reset()
    monkeypatch.delenv("SACH_CLAIM_CACHE"); monkeypatch.delenv("SACH_SHOW_PAGES")
    on = [_essence(check_forward(w.format(t=text), [CountingRetriever(list(ev))], llm(), log=True)) for w in WRAPPERS]
    assert on == off
    assert len({repr(x["claims"]) for x in on}) == 1                     # every wrapper variant checked the same claim and got the same answer


def test_a_cached_answer_is_never_served_for_a_different_claim():
    seen = {}
    for text in ("Government will give Rs 5000 to every woman.", "Government will give Rs 5001 to every woman.", "Government will not give Rs 5000 to every woman.",
                 "Government will give Rs 5000 to every man."):
        res = check_forward(text, [CountingRetriever([OFFICIAL])], NoneLLM(), log=True)
        assert not res.get("cached"), text                               # four different claims, four fresh checks
        seen[text] = res["claims"][0]["claim"]["text"]
    assert len(set(seen.values())) == 4
