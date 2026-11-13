"""Serper (Google results) as a web-search provider: used only when SERPER_API_KEY is set; keeps site: operators; same failover rules."""
import io, json, urllib.error
from sach import search as S
from sach.search import SearchChain, SearchRun, SerperSearch


class Resp:
    def __init__(self, data):
        self._b = json.dumps(data).encode()
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_request_shape_and_parsing():
    seen = {}
    def opener(req, timeout=None):
        seen["url"], seen["method"] = req.full_url, req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = json.loads(req.data.decode())
        seen["timeout"] = timeout
        return Resp({"organic": [{"link": "https://pib.gov.in/PressReleasePage.aspx?PRID=1"}, {"title": "no link"}, {"link": 5},
                                 {"link": "https://www.mha.gov.in/x"}]})
    urls = SerperSearch("secret-key-123", opener=opener).search("free laptops site:pib.gov.in", 8)
    assert urls == ["https://pib.gov.in/PressReleasePage.aspx?PRID=1", "https://www.mha.gov.in/x"]
    assert seen["url"] == S.SERPER_ENDPOINT == "https://google.serper.dev/search" and seen["method"] == "POST"
    assert seen["headers"]["x-api-key"] == "secret-key-123" and seen["headers"]["content-type"] == "application/json"
    assert seen["body"] == {"q": "free laptops site:pib.gov.in", "num": 8}      # the site: operator is kept for Google
    assert "authorization" not in seen["headers"]


def test_count_is_clamped_and_missing_results_are_an_empty_answer():
    bodies = []
    def opener(req, timeout=None):
        bodies.append(json.loads(req.data.decode())); return Resp({})
    s = SerperSearch("k", opener=opener)
    assert s.search("q", 0) == [] and s.search("q", 99) == []
    assert [b["num"] for b in bodies] == [1, 20]


def test_the_key_never_appears_in_a_raised_error():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"{}"))
    s = SerperSearch("topsecretkey", opener=opener)
    try:
        s.search("q")
    except urllib.error.HTTPError as e:
        assert "topsecretkey" not in str(e) and "topsecretkey" not in repr(e)
    else:
        raise AssertionError("expected an HTTPError")


def test_chain_pauses_serper_on_credit_errors_and_falls_through():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, io.BytesIO(b"{}"))
    class Next:
        name = "tavily"
        def __init__(self): self.calls = 0
        def search(self, q, count=8):
            self.calls += 1; return ["https://pib.gov.in/x"]
    nxt = Next()
    ch = SearchChain([SerperSearch("k", opener=opener), nxt], clock=lambda: 100.0)
    run = SearchRun(configured=True)
    assert ch.search("claim words", run=run) == ["https://pib.gov.in/x"]
    assert ch.paused_until("serper") > 100.0               # 402 pauses it like Brave
    assert run.status == "ok" and nxt.calls == 1


def test_order_and_off_state(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "bk"); monkeypatch.setenv("TAVILY_API_KEY", "tk")
    assert [p.name for p in SearchChain.from_env().providers] == ["brave", "tavily"]            # no key: no provider, nothing changes
    monkeypatch.setenv("SERPER_API_KEY", "sk")
    assert [p.name for p in SearchChain.from_env().providers] == ["serper", "brave", "tavily"]
    monkeypatch.setenv("SACH_SEARCH_ORDER", "tavily,brave")
    assert [p.name for p in SearchChain.from_env().providers] == ["tavily", "brave", "serper"]


def test_serper_alone_makes_web_search_available(monkeypatch):
    from sach import retrieve
    monkeypatch.delenv("BRAVE_API_KEY", raising=False); monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert "BraveRetriever" not in [type(r).__name__ for r in retrieve.default_retrievers()]
    monkeypatch.setenv("SERPER_API_KEY", "sk")
    assert "BraveRetriever" in [type(r).__name__ for r in retrieve.default_retrievers()]
