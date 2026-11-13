"""Regressions for the evidence used by live verdicts. All source and model calls are stubbed."""
from datetime import datetime, timezone
from email.message import Message
import io
import json
from urllib.error import HTTPError

import pytest

from sach import cache, fetch, llm, pib, share, store
from sach.models import Claim, Evidence, FALSE, TIER_FACTCHECKER, TIER_OFFICIAL, TIER_PIB, UNVERIFIED
from sach.retrieve import BraveRetriever
from sach.verdict import decide

CLAIM = Claim("Government will give Rs 5000 to every woman")
DEBUNK = f"Fake: {CLAIM.text}"
TS = "2026-11-12T10:00:00+00:00"
PIB_URL = "https://pib.gov.in/PressReleasePage.aspx?PRID=42"
OFFICIAL_URL = "https://finmin.gov.in/notice"
PIB_HTML = f"<h2>{DEBUNK}</h2><div id='PdfDiv'>The claim is fake.</div>"


@pytest.mark.parametrize("stance", ["confirms", "contradicts", "mixed"])
@pytest.mark.parametrize("url,fetched_at", [("", TS), (" ", TS), ("https://", TS), (OFFICIAL_URL, ""), (OFFICIAL_URL, "unknown")])
def test_unusable_citation_cannot_decide_a_verdict(stance, url, fetched_at):
    evidence = Evidence("Ministry of Finance", url, TIER_OFFICIAL, fetched_at, stance=stance)
    verdict = decide(CLAIM, [evidence])
    assert verdict.verdict == UNVERIFIED
    assert verdict.reason_code == "no_evidence"
    assert verdict.citations == []


def test_unfetched_evidence_cannot_override_a_fetched_citation():
    confirmation = Evidence("Ministry of Finance", OFFICIAL_URL, TIER_OFFICIAL, "", stance="confirms")
    debunk = Evidence("PIB", PIB_URL, TIER_PIB, TS, stance="contradicts")
    verdict = decide(CLAIM, [confirmation, debunk])
    assert verdict.verdict == FALSE
    assert verdict.citations == [debunk.cite()]


class _Page(io.BytesIO):
    status = 200

    def __init__(self, url, body):
        super().__init__(body.encode())
        self.headers = Message()
        self.url = url

    def geturl(self):
        return self.url


@pytest.fixture
def pages(monkeypatch):
    def install(routes):
        requested = []

        def open_page(req, timeout):
            requested.append(req.full_url)
            response = routes[req.full_url]
            if isinstance(response, Exception):
                raise response
            return _Page(*response)

        monkeypatch.setattr(fetch.urllib.request, "urlopen", open_page)
        monkeypatch.setattr(fetch.time, "sleep", lambda _: None)
        return requested

    return install


@pytest.mark.parametrize("requested,destination,expected_tier", [
    (PIB_URL, "https://pib.gov.in.example.test/?PRID=42", None),
    (PIB_URL, "https://fakepib.gov.in.example.test/?PRID=42", None),
    (OFFICIAL_URL, "https://www.indiatoday.in/fact-check/notice", TIER_FACTCHECKER),
    (OFFICIAL_URL, "https://www.indiatoday.in/india/notice", None),
    (OFFICIAL_URL, "https://www.finmin.gov.in/notice", TIER_OFFICIAL),
    (PIB_URL, "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=42", TIER_PIB),
    ("https://boomlive.in/notice", OFFICIAL_URL, None),
])
def test_brave_revalidates_source_tier_and_cites_the_final_url(pages, requested, destination, expected_tier):
    calls = pages({requested: (destination, PIB_HTML)})
    initial_tier = TIER_FACTCHECKER if requested.startswith("https://boomlive.in/") else TIER_OFFICIAL
    retriever = BraveRetriever(key="fixture")
    first = retriever._evidence(requested, initial_tier)
    cached = retriever._evidence(requested, initial_tier)
    assert calls == [requested]
    assert first == cached
    if expected_tier is None:
        assert first is None
    else:
        assert first.tier == expected_tier
        assert first.cite()["url"] == destination


def test_legacy_page_cache_requires_a_refetch(pages):
    path = fetch._cache_path(OFFICIAL_URL)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"url": OFFICIAL_URL, "status": 200, "body": PIB_HTML,
                   "fetched_at": datetime.now(timezone.utc).isoformat()}, f)
    destination = "https://untrusted.example/notice"
    calls = pages({OFFICIAL_URL: (destination, "fresh body")})
    assert BraveRetriever(key="fixture")._evidence(OFFICIAL_URL, TIER_OFFICIAL) is None
    assert calls == [OFFICIAL_URL]
    updated = fetch.fetch(OFFICIAL_URL)
    assert updated["url"] == OFFICIAL_URL and updated["final_url"] == destination
    assert updated["body"] == "fresh body" and calls == [OFFICIAL_URL]


def test_unsuccessful_redirect_cannot_supply_evidence(pages):
    destination = "https://www.finmin.gov.in/notice"
    pages({OFFICIAL_URL: HTTPError(destination, 404, "missing", None, None)})
    assert BraveRetriever(key="fixture")._evidence(OFFICIAL_URL, TIER_OFFICIAL) is None
    assert fetch.fetch(OFFICIAL_URL)["final_url"] == destination


def test_pib_release_and_feed_require_a_pib_destination(pages):
    feed_url = pib.RSS_URL.format(mod=6, lang=1, reg=3)
    destination = "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=42"
    feed_body = "<item><title>Example</title><link>/?PRID=42</link></item>"
    pages({PIB_URL: (destination, PIB_HTML), feed_url: ("https://untrusted.example/feed", feed_body)})
    release = pib.get_release(42)
    assert release["url"] == destination and release["title"] == DEBUNK
    assert pib.rss_index() == []


def test_pib_rejects_a_non_pib_release_even_on_another_official_host(pages):
    pages({PIB_URL: (OFFICIAL_URL, PIB_HTML)})
    assert pib.get_release(42) is None


def test_single_model_cannot_confirm_itself(monkeypatch):
    judge = llm.GeminiJudge(key="fixture", model="solo")
    calls = []

    def reply(model, *_):
        calls.append(model)
        return f"CONTRADICTS | {DEBUNK}"

    monkeypatch.setattr(judge, "_raw", reply)
    assert judge.stance(CLAIM.text, DEBUNK, "", tier=TIER_OFFICIAL) == "none"
    assert calls == ["solo"]
    assert judge.stance(CLAIM.text, DEBUNK, "", tier=TIER_PIB) == "contradicts"
    assert calls == ["solo", "solo"]


def test_gemini_key_failover_has_secret_free_names(monkeypatch):
    keys = ["test-first-sentinel-a19x", "test-second-sentinel-z82w"]
    judges = [llm.GeminiJudge(key=key, model="fixture-model") for key in keys]
    calls = []

    def reply(judge, *_):
        calls.append(judge.key)
        if judge is judges[0]:
            raise HTTPError("https://example.test", 401, "denied", None, None)
        return "translated sentence"

    monkeypatch.setattr(llm.GeminiJudge, "_raw", reply)
    failover = llm.FailoverJudge(judges)
    assert failover.translate("original sentence") == "translated sentence"
    assert calls == keys
    assert failover.describe() == [("gemini", "cooling down"), ("gemini", "ready")]


@pytest.mark.parametrize("layer", ["live", "mixed"])
def test_legacy_live_verdicts_are_rechecked_and_existing_share_is_readable(layer):
    key = cache.key(CLAIM.text, None)
    rid = share.share_id(key)
    historical = {"verdict": FALSE, "claims": [{}], "layer": layer}
    st = store.get_store()
    st.set(key, historical)
    st.set("share:" + rid, {"key": key, "text": CLAIM.text, "result": historical})
    assert cache.lookup(CLAIM.text, None) is None
    assert share.load_share(rid)["result"] == historical

    current = {"verdict": UNVERIFIED, "claims": [{"trace": {"timing_ms": {"judge": 1}}}], "layer": "live"}
    cache.save(CLAIM.text, None, current)
    assert cache.lookup(CLAIM.text, None) == current
    assert share.share_id(cache.key(CLAIM.text, None)) == rid


def test_match_only_cache_entries_keep_their_published_attribution():
    result = {"verdict": FALSE, "claims": [{"reason_code": "matched_fact_check"}], "layer": "match"}
    store.get_store().set(cache.key(CLAIM.text, None), result)
    assert cache.lookup(CLAIM.text, None) == result
