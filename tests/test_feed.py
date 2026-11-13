"""FEED work package: ClaimReview feed + JSON-LD on shared results, and the trending-forwards section. Offline and deterministic."""
import ast, http.client, json, pathlib, re, threading
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
import urllib.parse as up
import pytest
import sach.web as W
from sach import claimreview as CR, ledger, store, trending as T
from sach.models import Evidence, TIER_PIB
from sach.pipeline import check_forward
from test_sach import FakeRetriever, TS

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = "https://sach.example"
NOW = datetime.now(timezone.utc)


def iso(days=0):
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


def row(claim="Govt will give Rs 5000 to every woman.", verdict="FALSE", days=0, lang="en", cites=True, **kw):
    r = {"claim": claim, "domain": "news", "verdict": verdict, "reason_code": "official_contradiction", "language": lang,
         "checked_at": iso(days), "citations": [{"source": "PIB", "url": "https://pib.gov.in/x?id=1", "tier": "pib_debunk", "date_accessed": "2026-11-12"}] if cites else []}
    r.update(kw)
    return r


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SACH_SITE_URL", SITE)
    store.reset()
    yield
    store.reset()


def rows_are(monkeypatch, rows):
    monkeypatch.setattr(ledger, "load", lambda: list(rows))


# ------------------------------------------------------------------ ClaimReview builder
def test_builder_required_and_recommended_properties(monkeypatch):
    rows_are(monkeypatch, [row()])
    g = CR.feed()
    assert g["@context"] == "https://schema.org"
    o = g["@graph"][0]
    assert o["@type"] == "ClaimReview"
    assert o["claimReviewed"] == "Govt will give Rs 5000 to every woman."
    assert o["url"].startswith(SITE + "/")
    assert o["author"] == {"@type": "Organization", "name": "Sach", "url": SITE}
    assert o["datePublished"] and o["inLanguage"] == "en-IN"
    assert o["reviewRating"] == {"@type": "Rating", "ratingValue": 1, "bestRating": 5, "worstRating": 1, "alternateName": "False"}
    assert o["citation"][0]["url"] == "https://pib.gov.in/x?id=1"
    json.dumps(g)


def test_no_invented_claimant_or_dates(monkeypatch):
    rows_are(monkeypatch, [row()])
    ir = CR.feed()["@graph"][0]["itemReviewed"]
    assert ir == {"@type": "Claim"}


@pytest.mark.parametrize("v,val,name", [("FALSE", 1, "False"), ("MISLEADING", 3, "Misleading"), ("TRUE", 5, "True")])
def test_rating_mapping(monkeypatch, v, val, name):
    rows_are(monkeypatch, [row(verdict=v)])
    r = CR.feed()["@graph"][0]["reviewRating"]
    assert (r["ratingValue"], r["alternateName"]) == (val, name)
    assert r["worstRating"] >= 1 and r["bestRating"] > r["worstRating"]


def test_language_bcp47(monkeypatch):
    rows_are(monkeypatch, [row(lang="hi"), row("other claim", lang="tl")])
    tags = {o["claimReviewed"]: o["inLanguage"] for o in CR.feed()["@graph"]}
    assert tags["Govt will give Rs 5000 to every woman."] == "hi-IN" and tags["other claim"] == "te-Latn"


def test_only_live_decisive_cited_rows(monkeypatch):
    rows_are(monkeypatch, [row("a"), row("b", verdict="UNVERIFIED"), row("c", layer="match"), row("d", cites=False),
                           row("e", attribution="BOOM"), row("f", match={"checker": "X"}), row("g", layer="live")])
    assert sorted(o["claimReviewed"] for o in CR.feed()["@graph"]) == ["a", "g"]


def test_limit_and_newest_first(monkeypatch):
    rows_are(monkeypatch, [row("old", days=3), row("new", days=0), row("mid", days=1)])
    assert [o["claimReviewed"] for o in CR.feed(limit=2)["@graph"]] == ["new", "mid"]


def test_ledger_anchor_url_when_no_share(monkeypatch):
    r = row()
    rows_are(monkeypatch, [r])
    assert CR.feed()["@graph"][0]["url"] == f"{SITE}/?view=ledger#{CR.row_id(r)}"


def test_share_permalink_used_when_one_exists(monkeypatch):
    from sach import cache, share
    rows_are(monkeypatch, [row("Govt will give Rs 5000 to every woman.")])
    k = cache.key("Govt will give Rs 5000 to every woman.", None)
    store.get_store().set("share:" + share.share_id(k), {"key": k, "text": "x", "result": {"verdict": "FALSE", "claims": []}})
    assert CR.feed()["@graph"][0]["url"] == f"{SITE}/?r={share.share_id(k)}"


def test_ledger_page_rows_carry_the_anchor_id(monkeypatch):
    from sach import site
    r = row()
    rows_are(monkeypatch, [r])
    assert f'id="{CR.row_id(r)}"' in site.ledger_page().decode()


# ------------------------------------------------------------------ routes
@pytest.fixture
def srv():
    W._hits.clear()
    PIB = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
                   "Fake claim: government will give Rs 5000 to every woman", "Fake message claims government will give Rs 5000 to every woman")

    class LLM:
        failures = 0
        judges = []
        def stance(self, claim, title, text, tier=None):
            return "contradicts" if tier == TIER_PIB else "none"
    W.Handler.retrievers, W.Handler.llm = [FakeRetriever([PIB])], LLM()
    s = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{s.server_address[1]}"
    s.shutdown()
    W.Handler.llm = None


def req(base, method, path, body=None, headers=None):
    host, port = base.split(":")
    c = http.client.HTTPConnection(host, int(port))
    c.request(method, path, body, headers or {})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace")


def test_claimreview_routes_content_type(srv, monkeypatch):
    rows_are(monkeypatch, [row()])
    for p in ("/?view=claimreview", "/claimreview.json"):
        st, h, body = req(srv, "GET", p)
        assert st == 200 and h["Content-Type"].startswith("application/json")
        assert json.loads(body)["@graph"][0]["@type"] == "ClaimReview"


def test_vercel_rewrite_before_catch_all():
    src = [r["source"] for r in json.loads((ROOT / "vercel.json").read_text())["rewrites"]]
    assert "/claimreview.json" in src and src.index("/claimreview.json") < src.index("/(.*)")


def test_trending_json_route(srv, monkeypatch):
    rows_are(monkeypatch, [row(), row(days=1)])
    st, h, body = req(srv, "GET", "/?view=trending&format=json")
    d = json.loads(body)
    assert st == 200 and h["Content-Type"].startswith("application/json")
    assert d["window_days"] == T.WINDOW_DAYS and d["items"][0]["count"] == 2


# ------------------------------------------------------------------ JSON-LD on shared pages
def _shared(srv, text="Government will give Rs 5000 to every woman. Please forward to all groups!"):
    st, _, body = req(srv, "POST", "/", up.urlencode({"text": text}), {"Content-Type": "application/x-www-form-urlencoded"})
    rid = re.search(r"/\?r=([0-9a-f]{12})", body).group(1)
    return req(srv, "GET", "/?r=" + rid)[2], rid


def test_json_ld_on_shared_live_result(srv):
    body, rid = _shared(srv)
    m = re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)
    assert len(m) == 1
    o = json.loads(m[0])
    assert o["@context"] == "https://schema.org" and o["@type"] == "ClaimReview"
    assert o["url"].endswith("/?r=" + rid) and o["reviewRating"]["alternateName"] == "False"


def _res(verdict="FALSE", **kw):
    r = {"verdict": verdict, "language": "en", "checked_at": iso(), "claims": [{"verdict": verdict, "claim": {"text": "c </script><!-- x"},
         "citations": [{"url": "https://pib.gov.in/a", "source": "PIB"}]}]}
    r.update(kw)
    return r


def test_json_ld_escaped_and_conditions():
    s = CR.json_ld_for_result(_res(), SITE + "/?r=abcdef012345")
    inner = s[len('<script type="application/ld+json">'):-len("</script>")]
    assert "</script" not in inner and "<!--" not in inner and "<" not in inner
    assert json.loads(inner)["claimReviewed"] == "c </script><!-- x"
    assert CR.json_ld_for_result(_res("UNVERIFIED"), "u") == ""
    assert CR.json_ld_for_result(_res(layer="match"), "u") == ""
    assert CR.json_ld_for_result(_res(attribution="BOOM"), "u") == ""
    r = _res(); r["claims"][0]["layer"] = "match"
    assert CR.json_ld_for_result(r, "u") == ""
    r = _res(); r["claims"][0]["citations"] = []
    assert CR.json_ld_for_result(r, "u") == ""


def test_no_json_ld_on_home_or_unverified_page(srv):
    assert "ld+json" not in req(srv, "GET", "/")[2]


# ------------------------------------------------------------------ trending
def test_grouping_normalisation_counts_and_latest(monkeypatch):
    rows_are(monkeypatch, [row("Govt will give  Rs 5000 to EVERY woman!!", verdict="FALSE", days=2),
                           row("govt will give rs 5000 to every woman", verdict="MISLEADING", days=1, lang="hi"),
                           row("Something else", verdict="TRUE", days=0)])
    items = T.top()
    assert items[0]["count"] == 2 and items[0]["verdict"] == "MISLEADING"
    assert items[0]["languages"] == ["en", "hi"] and items[0]["citation"]["url"] == "https://pib.gov.in/x?id=1"
    assert items[1]["count"] == 1


def test_window_is_seven_days(monkeypatch):
    rows_are(monkeypatch, [row("inside", days=6), row("outside", days=8), row("bad date", checked_at="nonsense")])
    assert [i["claim"] for i in T.top()] == ["inside"]


def test_personal_data_hidden(monkeypatch):
    rows_are(monkeypatch, [row("Call 9876543210 to claim"), row("mail me at a.b@x.com now"), row("My Aadhaar 1234 5678 9012"),
                           row("Pay Rs 500 only"), row("फोन ९८७६५४३२१० पर")])
    assert [i["claim"] for i in T.top()] == ["Pay Rs 500 only"]


def test_matched_row_shows_checked_by(monkeypatch):
    rows_are(monkeypatch, [row("m claim", layer="match", attribution="BOOM")])
    i = T.top()[0]
    assert i["checked_by"] == "BOOM"
    h = T.section_html()
    assert "Checked by BOOM" in h and 'class="stamp' not in h.split("<ol>")[1]


def test_empty_state_and_limit(monkeypatch):
    rows_are(monkeypatch, [])
    assert "Nothing trending yet this week" in T.section_html()
    rows_are(monkeypatch, [row(f"claim number {c}") for c in "abcdefgh"])
    assert len(T.top(5)) == 5 and T.section_html(5).count("<li>") == 5


def test_escaping(monkeypatch):
    rows_are(monkeypatch, [row('<img src=x onerror=alert(1)> "q"')])
    h = T.section_html()
    assert "<img" not in h and "&lt;img" in h


def test_section_in_home_and_impact(monkeypatch):
    from sach import impact, site
    rows_are(monkeypatch, [row()])
    for page in (site.home(), impact.impact_page()):
        t = page.decode()
        assert "What India is checking this week" in t and "Checked 1 time" in t


def test_trending_module_has_no_hand_typed_statistics():
    tree = ast.parse((ROOT / "sach" / "trending.py").read_text(encoding="utf-8"))
    allowed = {0, 1, 5, 7, 8, 10, 25}
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
           and not isinstance(n.value, bool) and n.value not in allowed]
    assert not bad
