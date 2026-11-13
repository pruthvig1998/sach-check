"""Grounded search as a LAST RESORT for site:-restricted queries: only when every other provider failed or is paused (for example out of
credits). It must never run when another provider answered (even with an empty list), so it can never shadow Brave or Tavily and never
costs the PIB-first guarantee. Its answer is filtered to the query's own site(s)."""
import urllib.error
import pytest
from sach import search as S
from sach.search import SearchChain, SearchRun

PIB = "https://pib.gov.in/PressReleasePage.aspx?PRID=1618314"
MHA = "https://www.mha.gov.in/notice"
Q_PIB = "free laptops students site:pib.gov.in"
Q_FC = "free laptops students (site:factly.in OR site:boomlive.in)"
Q_POOL = "free laptops students " + " OR ".join("site:" + s for s in S.OFFICIAL_POOL_SITES)
Q_INURL = "free laptops students inurl:laptop site:pib.gov.in"


def http(code):
    return urllib.error.HTTPError("https://x.example/", code, "x", {}, None)


class P:
    """A provider with a script: a list of URLs, or an Exception to raise."""
    def __init__(self, name, result, restricted_result=None):
        self.name, self.result, self.restricted_result = name, result, restricted_result
        self.calls, self.restricted_calls = [], []
        self.fallthrough_empty = name == "grounded"
        self.auth_pause_s = 600.0

    def search(self, query, count=8, restricted=False):
        (self.restricted_calls if restricted else self.calls).append(query)
        out = self.restricted_result if (restricted and self.restricted_result is not None) else self.result
        if isinstance(out, Exception):
            raise out
        return list(out)


def chain(*providers):
    return SearchChain(list(providers), clock=lambda: 1000.0)


def run_search(ch, q):
    run = SearchRun(configured=True)
    return ch.search(q, run=run), run


def test_last_resort_answers_a_pib_query_when_brave_and_tavily_are_out_of_credits():
    g, b, t = P("grounded", []), P("brave", http(402)), P("tavily", http(432))
    g.restricted_result = [PIB, MHA, "https://news.example.com/x"]
    urls, run = run_search(chain(g, b, t), Q_PIB)
    assert urls == [PIB]                                   # filtered to pib.gov.in only
    assert run.status == "ok" and "grounded" in run.provider
    assert g.calls == [] and g.restricted_calls == [Q_PIB]  # asked once, as the last resort


def test_last_resort_filters_to_the_query_site_and_an_empty_filter_is_not_an_answer():
    g = P("grounded", []); g.restricted_result = [MHA, "https://news.example.com/x"]
    urls, run = run_search(chain(g, P("brave", http(402)), P("tavily", http(432))), Q_PIB)
    assert urls == [] and run.status == "down"             # nothing on pib.gov.in: still honestly down, never an off-site URL


def test_it_never_shadows_a_provider_that_answered():
    g, b = P("grounded", []), P("brave", [PIB])
    g.restricted_result = [MHA]
    urls, _ = run_search(chain(g, b), Q_PIB)
    assert urls == [PIB] and g.restricted_calls == []      # brave answered: grounded is never asked


def test_it_does_not_run_when_providers_merely_returned_nothing():
    g, b, t = P("grounded", []), P("brave", []), P("tavily", [])
    g.restricted_result = [PIB]
    urls, run = run_search(chain(g, b, t), Q_PIB)
    assert urls == [] and g.restricted_calls == []         # an empty answer is not a failure: no last resort


def test_it_runs_when_a_provider_is_paused_not_only_when_it_raises():
    g, b = P("grounded", []), P("brave", http(402))
    g.restricted_result = [PIB]
    ch = chain(g, b)
    run_search(ch, Q_PIB)                                  # first call: brave raises 402 and gets paused (grounded answers as the last resort)
    g.restricted_calls.clear()
    urls, run = run_search(ch, Q_PIB)                      # second call: brave is paused (skipped), still a failed provider
    assert urls == [PIB] and g.restricted_calls == [Q_PIB]


def test_fact_checker_queries_use_the_last_resort_too_filtered_to_their_sites():
    g = P("grounded", []); g.restricted_result = ["https://factly.in/a", MHA, "https://www.boomlive.in/fact-check/b"]
    urls, _ = run_search(chain(g, P("brave", http(402)), P("tavily", http(432))), Q_FC)
    assert urls == ["https://factly.in/a", "https://www.boomlive.in/fact-check/b"]


def test_inurl_queries_are_never_sent_to_the_last_resort():
    g = P("grounded", []); g.restricted_result = [PIB]
    urls, run = run_search(chain(g, P("brave", http(402)), P("tavily", http(432))), Q_INURL)
    assert urls == [] and g.restricted_calls == []


def test_unrestricted_and_pool_queries_keep_their_normal_path():
    g = P("grounded", [MHA])
    urls, _ = run_search(chain(g, P("brave", http(402))), "free laptops students")
    assert urls == [MHA] and g.restricted_calls == []      # unrestricted: grounded answers normally
    g2 = P("grounded", [MHA])
    urls2, _ = run_search(chain(g2, P("brave", http(402))), Q_POOL)
    assert urls2 == [MHA] and g2.restricted_calls == []    # pool query: grounded answers normally


def test_a_failing_last_resort_is_just_down_and_pauses_on_credit_errors():
    g = P("grounded", []); g.restricted_result = http(403)
    ch = chain(g, P("brave", http(402)), P("tavily", http(432)))
    urls, run = run_search(ch, Q_PIB)
    assert urls == [] and run.status == "down"
    assert ch.paused_until("grounded") > 1000.0            # 403 pauses grounded like any provider


def test_the_real_grounded_provider_refuses_restricted_calls_without_a_site_and_inurl_queries(monkeypatch):
    class Boom:
        def __getattr__(self, name):
            raise AssertionError("must not call Google")
    g = S.GroundedSearch.__new__(S.GroundedSearch)
    assert g.search("plain words without a site", restricted=True) == []
    assert g.search(Q_INURL, restricted=True) == []
    assert g.search("plain words site:pib.gov.in", 8, restricted=False) == []   # the normal path still refuses restricted queries
