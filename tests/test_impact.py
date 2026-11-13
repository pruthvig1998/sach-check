"""Impact page, JSON, snapshot script. Offline and deterministic: no network, no real LLM."""
import ast, importlib.util, json, pathlib, re
import pytest
import urllib.request as _ur
from test_sach import server, FakeRetriever, TS          # noqa: F401  (server is a fixture)
from sach import impact, ledger, store, fetch, site
from sach.models import Evidence, TIER_PIB, TIER_OFFICIAL
from sach.pipeline import check_forward

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIB = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
               "Fake claim: government will give Rs 5000 to every woman", "Fake message claims government will give Rs 5000 to every woman")
OFF = Evidence("Ministry of Finance", "https://finmin.gov.in/x", TIER_OFFICIAL, TS, "PM Kisan", "PM Kisan gives farmers Rs 6000 per year")

class LLM:
    failures = 0
    def __init__(self, mode=None): self.mode = mode
    def stance(self, claim, title, text, tier=None):
        return self.mode or ("contradicts" if tier == TIER_PIB else "none")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR"):
        monkeypatch.delenv(k, raising=False)
    store.reset()
    yield
    store.reset()


def chk(text, ev=(PIB,), llm=None):
    return check_forward(text, [FakeRetriever(list(ev))], llm or LLM())


FALSE_T = "Government will give Rs 5000 to every woman. Please forward to all groups!"
TRUE_T = "PM Kisan gives farmers Rs 6000 per year."
UNV_T = "The new moon landing scheme will start next month."
TE_T = "ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది, వెంటనే షేర్ చేయండి."
HI_T = "सरकार हर महिला को 7000 रुपये देगी, जल्दी शेयर करें।"


def scenario():
    outs = [chk(FALSE_T),
            chk(TRUE_T, ev=(OFF,), llm=LLM("confirms")),
            chk(UNV_T, ev=()),
            chk(FALSE_T),                  # cache hit
            chk(HI_T), chk(TE_T),
            chk("Good morning 🙏")]        # nothing checkable
    return outs


# ---------------------------------------------------------------- zero state
def test_empty_state_renders_honestly():
    d = impact.impact_data()
    assert d["checks_total"] == 0 and d["counting_since"] is None
    assert d["verdicts"]["denominator"] == 0 and d["verdicts"]["FALSE"]["pct"] is None
    assert d["cache_hit_pct"] is None
    page = impact.impact_page().decode()
    assert "not available" in page.lower() and "No checks counted yet" in page
    assert "NaN" not in page and "None" not in page and "ZeroDivision" not in page
    assert "Counting since not available" in page
    json.dumps(d)


# ---------------------------------------------------------------- numbers match independent computation
def test_numbers_match_ledger_and_counters():
    outs = scenario()
    assert [o["verdict"] for o in outs[:3]] == ["FALSE", "TRUE", "UNVERIFIED"] and outs[3].get("cached")
    d = impact.impact_data()
    s = store.get_store()
    c = s.counters(["checks_total", "cache_hits", "no_claims", "verdict:TRUE", "verdict:FALSE", "verdict:UNVERIFIED",
                    "verdict:MISLEADING", "lang:en", "lang:hi", "lang:te", "lang:tl"])
    assert d["checks_total"] == c["checks_total"] == len(outs)
    assert d["cache_hits"] == c["cache_hits"] == 1
    assert d["checks_served_fresh"] == len(outs) - 1
    assert d["no_claims"] == 1
    # independent tallies from the results returned to callers
    exp_v = {}
    for o in outs:
        if not o.get("no_claims"):
            exp_v[o["verdict"]] = exp_v.get(o["verdict"], 0) + 1
    den = sum(exp_v.values())
    assert d["verdicts"]["denominator"] == den
    tot = 0.0
    for v in ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED"):
        assert d["verdicts"][v]["count"] == exp_v.get(v, 0)
        assert d["verdicts"][v]["pct"] == round(exp_v.get(v, 0) * 100 / den, 1)
        tot += d["verdicts"][v]["pct"]
    assert abs(tot - 100) < 0.5
    exp_l = {}
    for o in outs:
        exp_l[o["input_language"]] = exp_l.get(o["input_language"], 0) + 1
    assert exp_l.get("hi") == 1 and exp_l.get("te") == 1
    for k in ("en", "hi", "te", "tl"):
        assert d["languages"][k]["count"] == exp_l.get(k, 0)
    assert d["languages"]["denominator"] == sum(exp_l.get(k, 0) for k in ("en", "hi", "te", "tl"))
    # ledger
    rows = ledger.load()
    assert d["ledger"]["rows"] == len(rows)
    for v in ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED"):
        assert d["ledger"]["by_verdict"][v] == sum(1 for r in rows if r["verdict"] == v)
    falses = sorted((r for r in rows if r["verdict"] == "FALSE"), key=lambda r: r["checked_at"], reverse=True)
    rec = d["ledger"]["recent_false"]
    assert len(rec) == min(5, len(falses))
    assert [r["date"] for r in rec] == [r["checked_at"].split("T")[0] for r in falses[:len(rec)]]
    assert all(r["citation_url"].startswith("http") for r in rec if r["citation_url"])
    assert d["counting_since"] == s.get("first_event_at") and d["counting_since"]
    assert d["cache_hit_pct"] == round(100 / len(outs), 1)


def test_evaluation_headline_from_file_and_missing_fields():
    ev = json.load(open(ROOT / "data" / "eval_summary.json", encoding="utf-8"))
    d = impact.impact_data()["evaluation"]
    # The checked-in 26/31 summary is legacy and lacks a measured TRUE-overclaim
    # count. Both pages suppress it rather than interpreting that count as zero.
    assert d["available"] is False and d["n"] is None and d["correct_pct"] is None
    page = impact.impact_page().decode()
    assert "Not available" in page and "26/31" not in page


def test_benchmark_eligibility_is_shared_between_home_and_impact(monkeypatch):
    full = {"n": 10, "correct": 7, "overclaimed_false": 1, "overclaimed_true": 1, "abstained": 1,
            "commit": "abc123456", "date": "2026-11-13", "by_lang": {"en": {"n": 10}}}
    for status in ({}, {"mode": "live", "complete": True, "partial": False, "degraded": False,
                    "no_match": False, "system_failures": 0}):
        summary = dict(full, **status)
        assert site.eval_display(summary) is not None
        monkeypatch.setattr(impact, "_eval_file", lambda summary=summary: (summary, None))
        assert impact._evaluation()["available"] is True
    invalid = (
        {k: v for k, v in full.items() if k != "overclaimed_true"},
        dict(full, overclaimed_true=None), dict(full, correct=-1), dict(full, n=0),
        dict(full, correct=11), dict(full, abstained=11), dict(full, mode="offline_fixture"),
        dict(full, run_mode="offline_fixture"), dict(full, correct=8),
        dict(full, mode="fallback"), dict(full, partial=True), dict(full, complete=False),
        dict(full, degraded=True), dict(full, no_match=True), dict(full, system_failures=1),
        dict(full, system_failures="unknown"),
    )
    for summary in invalid:
        assert site.eval_display(summary) is None, summary
        monkeypatch.setattr(impact, "_eval_file", lambda summary=summary: (summary, None))
        ev = impact._evaluation()
        assert ev["available"] is False and ev["n"] is None and ev["correct_pct"] is None, summary


def test_usage_labels_and_repeat_traffic_caveat():
    d = impact.impact_data()
    assert "answered without the verdict cache" in d["how"]["checks_served_fresh"]
    assert "people or demonstrated outcomes" in impact.impact_page().decode()


def test_limited_mode_copy_covers_partial_source_judging():
    res = check_forward(FALSE_T, [FakeRetriever([PIB])], None)
    html = site.result_block(res)
    assert "Part of Sach’s AI check was unavailable or at capacity" in html
    assert "some source comparisons may be missing" in html
    assert "unverified” as uncertainty, not as proof a claim is false" in html


def test_evaluation_file_missing(monkeypatch):
    monkeypatch.setattr(impact, "_eval_file", lambda: ({}, "data/eval_summary.json does not exist in this deployment"))
    d = impact.impact_data()["evaluation"]
    assert d["available"] is False and d["n"] is None and d["correct_pct"] is None
    assert "does not exist" in impact.impact_page().decode()


def test_sources_policy_derived_from_fetch():
    sp = impact.impact_data()["sources_policy"]
    assert sp["official_suffixes"] == len(fetch.OFFICIAL_SUFFIXES)
    assert sp["official_extra_domains"] == len(fetch.EXTRA_OFFICIAL)
    assert sp["factchecker_hosts"] == len(fetch.FACTCHECKER_HOSTS)
    assert sp["factchecker_sites_with_path_rules"] == len(fetch.FACTCHECKER_PATHS)


# ---------------------------------------------------------------- honesty about storage
class RemoteFake(store.FileStore):
    remote = True


def test_storage_temporary_then_persistent(monkeypatch, tmp_path):
    d = impact.impact_data()
    assert d["storage"] == "temporary"
    page = impact.impact_page().decode()
    assert "temporary" in page and "they reset when the server restarts" in page
    fake = RemoteFake(str(tmp_path / "remote"))
    monkeypatch.setattr(store, "get_store", lambda: fake)
    d = impact.impact_data()
    assert d["storage"] == "persistent"
    page = impact.impact_page().decode()
    assert "<b>persistent</b>" in page and "they reset when the server restarts" not in page


# ---------------------------------------------------------------- routes, escaping, nav
def test_routes_json_and_html(server):
    scenario()
    for path in ("/?view=impact", "/impact"):
        r = _ur.urlopen(server + path)
        h = r.read().decode()
        assert r.status == 200 and "Impact" in h and "How each number is computed" in h and "Read this first" in h
        assert 'href="/?view=impact"' in h                                  # nav and footer
        assert h.count('href="/?view=impact"') >= 2
    r = _ur.urlopen(server + "/?view=impact&format=json")
    assert r.headers["Content-Type"].startswith("application/json") and r.headers["Cache-Control"] == "no-store"
    got = json.loads(r.read())
    want = impact.impact_data()
    for k in ("checks_total", "cache_hits", "storage", "verdicts", "languages", "ledger", "evaluation", "sources_policy", "how", "counting_since"):
        assert got[k] == want[k]
    h = _ur.urlopen(server + "/").read().decode()
    assert 'class="opt" href="/?view=impact"' in h                         # hidden on phones in the header, always in the footer
    assert "Impact</a> · <a" in h


def test_hostile_claim_is_escaped():
    ledger.append({"claim": "<script>alert(1)</script>", "domain": "news", "verdict": "FALSE", "reason_code": "x",
                   "citations": [{"source": "<b>x</b>", "url": "javascript:alert(1)", "tier": "official", "date_accessed": "2099-01-01"}],
                   "language": "en", "checked_at": "2099-01-01T00:00:00+00:00"})
    page = impact.impact_page().decode()
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "javascript:alert" not in page and "&lt;b&gt;x&lt;/b&gt;" not in page    # bad scheme: no link, source not shown as link


def test_vercel_json():
    v = json.load(open(ROOT / "vercel.json"))
    srcs = [r["source"] for r in v["rewrites"]]
    assert "/(.*)" in srcs and "/impact" in srcs and srcs.index("/impact") < srcs.index("/(.*)")
    assert {"source": "/(.*)", "destination": "/api/index"} in v["rewrites"]
    assert {"source": "/impact", "destination": "/api/index?view=impact"} in v["rewrites"]
    assert v["functions"]["api/index.py"]["maxDuration"] == 60


def test_page_is_mobile_safe_markup():
    page = impact.impact_page().decode()
    assert 'name="viewport"' in page
    scenario()
    page = impact.impact_page().decode()
    assert 'role="img" aria-label="' in page and "<h1" in page and "<h2" in page


# ---------------------------------------------------------------- snapshot script
def load_script():
    spec = importlib.util.spec_from_file_location("snapshot_impact", ROOT / "scripts" / "snapshot_impact.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_snapshot_from_local(tmp_path, capsys):
    scenario()
    m = load_script()
    assert m.main(["--from-local", "--date", "2026-11-14", "--out-dir", str(tmp_path)]) == 0
    f = tmp_path / "impact-2026-11-14.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    assert set(d) == {"snapshot", "payload"}
    assert {"fetched_from", "fetched_at", "git_commit", "sha256"} <= set(d["snapshot"])
    assert m.sha256_of(d["payload"]) == d["snapshot"]["sha256"]
    import hashlib
    canon = json.dumps(d["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert hashlib.sha256(canon).hexdigest() == d["snapshot"]["sha256"]
    for k in m.EXPECTED_KEYS:
        assert k in d["payload"]
    assert d["payload"]["checks_total"] == 7
    assert "sha256=" in capsys.readouterr().out
    # refuses overwrite
    before = f.read_text(encoding="utf-8")
    assert m.main(["--from-local", "--date", "2026-11-14", "--out-dir", str(tmp_path)]) == 1
    assert f.read_text(encoding="utf-8") == before
    assert m.main(["--from-local", "--date", "2026-11-14", "--out-dir", str(tmp_path), "--force"]) == 0


class _Resp:
    def __init__(self, body, status=200): self.body, self.status = body, status
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_snapshot_fetch_with_fake_opener(tmp_path, monkeypatch):
    m = load_script()
    payload = impact.impact_data()
    seen = {}
    def opener(req, timeout=None):
        seen["url"], seen["ua"], seen["timeout"] = req.full_url, req.get_header("User-agent"), timeout
        return _Resp(json.dumps(payload).encode())
    monkeypatch.setattr(m, "OPENER", opener)
    assert m.main(["--url", "https://example.test/", "--date", "2026-11-14", "--out-dir", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "impact-2026-11-14.json").read_text(encoding="utf-8"))
    assert d["snapshot"]["fetched_from"] == "https://example.test/?view=impact&format=json"
    assert d["payload"] == payload
    assert seen["timeout"] == 30 and "Sach" in seen["ua"] and seen["url"].endswith("?view=impact&format=json")


@pytest.mark.parametrize("body", [b"not json {", b'{"hello": 1}', b"[1,2]"])
def test_snapshot_rejects_bad_payload(tmp_path, monkeypatch, body, capsys):
    m = load_script()
    monkeypatch.setattr(m, "OPENER", lambda req, timeout=None: _Resp(body))
    assert m.main(["--url", "https://example.test", "--date", "2026-11-14", "--out-dir", str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []
    assert "nothing written" in capsys.readouterr().err


# ---------------------------------------------------------------- guard: no hand-typed statistics
ALLOWED_NUMBERS = {0, 1, 100, 5}      # 5 = RECENT, the number of recent FALSE rows listed (a layout size, not a statistic)

def test_no_hand_typed_numbers_in_impact_module():
    tree = ast.parse((ROOT / "sach" / "impact.py").read_text(encoding="utf-8"))
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            if n.value not in ALLOWED_NUMBERS:
                bad.append((n.lineno, n.value))
    assert not bad, "numeric literals in sach/impact.py (compute, do not type): %s" % bad
    # and none inside the HTML/CSS text of the page except layout CSS
    src = (ROOT / "sach" / "impact.py").read_text(encoding="utf-8")
    assert not re.search(r"\b\d{2,}\s*(checks|claims|forwards)\b", src)
