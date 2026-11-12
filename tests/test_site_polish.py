"""Site polish: configurable site address, SEO and share tags, robots/sitemap, preview image, phone layout markup, evaluation numbers."""
import http.client, json, pathlib, re, struct, zlib
import pytest
from sach import pwa, report, siteurl, site
from sach.scamsigns import signs_html
from test_sach import server, _raw_get, _post      # noqa: F401  (fixtures and helpers from the existing suite)

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = "https://sach.example.org"
FWD = ("Government is giving Rs 1000 to everyone under Corona Sahayata Yojana. Share your OTP. "
       "Click the link to register: http://pm-yojana-gov.xyz/claim. Forward to 10 groups or bad luck. bit.ly/abc")


class H:
    """The one thing site_url reads from a handler."""
    def __init__(self, host=None):
        self.headers = {} if host is None else {"Host": host}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("SACH_SITE_URL", raising=False)
    siteurl.unbind()
    yield
    siteurl.unbind()


def meta(html_, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"', html_)
    return m.group(1) if m else None


def canonical(html_):
    m = re.search(r'<link rel="canonical" href="([^"]*)"', html_)
    return m.group(1) if m else None


# ------------------------------------------------------------------ site_url

def test_default_when_nothing_is_set():
    assert siteurl.site_url() == siteurl.DEFAULT_SITE_URL == "https://sach-check-lilac.vercel.app"
    assert siteurl.site_url(H()) == siteurl.DEFAULT_SITE_URL           # a handler without a Host header


@pytest.mark.parametrize("raw,want", [(EXAMPLE, EXAMPLE), (EXAMPLE + "/", EXAMPLE), (EXAMPLE + "///", EXAMPLE), ("  " + EXAMPLE + " ", EXAMPLE),
                                      ("https://Sach.Example.ORG", EXAMPLE), ("https://example.org:8443", "https://example.org:8443")])
def test_env_var_wins_and_is_cleaned(monkeypatch, raw, want):
    monkeypatch.setenv("SACH_SITE_URL", raw)
    assert siteurl.site_url() == want
    assert siteurl.site_url(H("other.example")) == want                 # beats the Host header


@pytest.mark.parametrize("bad", ["http://sach.example.org", "ftp://sach.example.org", "sach.example.org", "https://", "https:///", EXAMPLE + "/path",
                                 EXAMPLE + "?q=1", EXAMPLE + "#frag", "https://user@sach.example.org", "https://sach example.org", "javascript:alert(1)",
                                 'https://a"><script>alert(1)</script>.com', "https://-bad.example", "https://a..b", "https://x.com:99999", "https://" + "a" * 300 + ".com"])
def test_bad_env_values_are_ignored(monkeypatch, bad):
    monkeypatch.setenv("SACH_SITE_URL", bad)
    assert siteurl.env_site_url() is None
    assert siteurl.site_url() == siteurl.DEFAULT_SITE_URL
    assert siteurl.site_url(H("good.example.com")) == "https://good.example.com"       # falls through to the Host header


def test_host_header_fallback_is_https_and_lowercased():
    assert siteurl.site_url(H("Sach.Example.com")) == "https://sach.example.com"
    assert siteurl.site_url(H("sach.example.com:8080")) == "https://sach.example.com:8080"


@pytest.mark.parametrize("host", ['evil.com/<script>alert(1)</script>', 'a"b.com', "x y.com", "", "-a.com", "a..b.com", "a.com:99999", "a.com:", "<b>.com",
                                  "a.com\r\nX: y", "a.com, b.com", "a.com@b.com", "a" * 300 + ".com", "exämple.com", "a.com/"])
def test_hostile_host_values_are_never_reflected(host):
    assert siteurl.site_url(H(host)) == siteurl.DEFAULT_SITE_URL


def test_bound_host_is_used_by_code_without_a_handler():
    siteurl.bind(H("bound.example.com"))
    assert siteurl.site_url() == "https://bound.example.com"
    siteurl.unbind()
    assert siteurl.site_url() == siteurl.DEFAULT_SITE_URL


def test_no_hard_coded_old_address_outside_the_single_default():
    hits = []
    for base in ("sach", "scripts", "api"):
        for p in (ROOT / base).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits += [(str(p.relative_to(ROOT)), i + 1) for i, line in enumerate(text.splitlines()) if "sach-check-lilac" in line]
    assert [h[0] for h in hits] == ["sach/siteurl.py"] and len(hits) == 1, hits


def test_report_text_uses_the_configured_address(monkeypatch):
    res = {"verdict": "FALSE", "checked_at": "2026-11-12T10:00:00+00:00", "claims": [{"claim": {"text": "x is true"}, "verdict": "FALSE", "citations": []}]}
    assert f"({siteurl.DEFAULT_SITE_URL})" in report.build_report(res)["body"]
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    assert f"({EXAMPLE})" in report.build_report(res)["body"]


def test_scripts_default_to_site_url(monkeypatch):
    import importlib.util
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    for name in ("snapshot_impact", "set_telegram_webhook"):
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.DEFAULT_URL == EXAMPLE


# ------------------------------------------------------------------ canonical, Open Graph, Twitter, robots meta

def test_head_tags_use_site_url_and_absolute_urls(monkeypatch):
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    h = site.layout("<h1>x</h1>").decode()
    assert canonical(h) == EXAMPLE + "/" and meta(h, "property", "og:url") == EXAMPLE + "/"
    img = EXAMPLE + "/?view=ogimage"
    assert meta(h, "property", "og:image") == img and meta(h, "name", "twitter:image") == img
    assert meta(h, "property", "og:type") == "website" and meta(h, "property", "og:site_name") == "Sach" and meta(h, "property", "og:locale") == "en_IN"
    assert meta(h, "property", "og:image:width") == "1200" and meta(h, "property", "og:image:height") == "630" and meta(h, "property", "og:image:alt")
    assert meta(h, "name", "twitter:card") == "summary_large_image" and meta(h, "name", "twitter:title") and meta(h, "name", "twitter:description")
    assert meta(h, "name", "robots") == "index,follow"
    assert '<link rel="icon" type="image/png" href="/?view=icon&amp;size=192">' in h and "data:image/svg+xml" in h
    assert "sach-check-lilac" not in h


def test_layout_page_paths_and_noindex(monkeypatch):
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    h = site.layout("x", path="/?view=ledger", noindex=True).decode()
    assert canonical(h) == EXAMPLE + "/?view=ledger" and meta(h, "name", "robots") == "noindex,follow"


def test_hostile_host_cannot_inject_into_canonical_over_http(server):
    host, port = server.replace("http://", "").split(":")
    c = http.client.HTTPConnection(host, int(port))
    c.putrequest("GET", "/", skip_host=True)
    c.putheader("Host", 'evil.com"><script>alert(1)</script>')
    c.endheaders()
    body = c.getresponse().read().decode()
    assert "<script>alert(1)</script>" not in body and "evil.com" not in body
    assert canonical(body) == siteurl.DEFAULT_SITE_URL + "/"


def test_real_host_header_becomes_the_canonical_host(server):
    host, port = server.replace("http://", "").split(":")
    c = http.client.HTTPConnection(host, int(port))
    c.putrequest("GET", "/?view=ledger", skip_host=True)
    c.putheader("Host", "sach.example.com")
    c.endheaders()
    body = c.getresponse().read().decode()
    assert canonical(body) == "https://sach.example.com/?view=ledger" and meta(body, "property", "og:image") == "https://sach.example.com/?view=ogimage"


def get(server, path):
    code, hdr, body = _raw_get(server, path)
    return code, hdr, body.decode("utf-8", "replace") if "text" in hdr.get("Content-Type", "") or "xml" in hdr.get("Content-Type", "") else body


def test_each_page_has_its_canonical_path_and_robots(server, monkeypatch):
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    for path, want_canon in (("/", "/"), ("/?view=ledger", "/?view=ledger"), ("/impact", "/impact"), ("/?view=impact", "/impact"),
                             ("/?view=terms", "/?view=terms"), ("/?view=privacy", "/?view=privacy"), ("/?view=refund", "/?view=refund"),
                             ("/?view=contact", "/?view=contact")):
        code, _, h = get(server, path)
        assert code == 200 and canonical(h) == EXAMPLE + want_canon, path
        assert meta(h, "name", "robots") == "index,follow", path
        assert h.count("<h1") == 1, path


def test_result_prefill_and_unknown_pages_are_noindex_and_never_carry_personal_params(server, monkeypatch):
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    code, h = _post(server, FWD)
    assert code == 200 and meta(h, "name", "robots") == "noindex,follow" and canonical(h) == EXAMPLE + "/" and h.count("<h1") == 1
    code, _, h = get(server, "/?text=Government+gives+Rs+5000+secret123")           # WhatsApp share-target prefill
    assert code == 200 and meta(h, "name", "robots") == "noindex,follow"
    assert "text=" not in canonical(h) and "secret123" not in canonical(h) and "secret123" not in meta(h, "property", "og:url")
    for path in ("/?view=nonsense", "/nothing-here"):
        code, _, h = get(server, path)
        assert code == 200 and 'id="check"' in h and meta(h, "name", "robots") == "noindex,follow" and canonical(h) == EXAMPLE + "/", path
    code, h = _post(server, "")                                                         # error page
    assert code == 400 and meta(h, "name", "robots") == "noindex,follow"
    for path in ("/?utm_source=x", "/?view="):                                           # the real home page, tracking params or not
        code, _, h = get(server, path)
        assert meta(h, "name", "robots") == "index,follow", path


def test_every_page_has_exactly_one_h1(server, monkeypatch):
    monkeypatch.setenv("SACH_UPI_ID", "supporter@okbank")
    monkeypatch.setenv("SACH_UPI_MERCHANT", "1")
    for path in ("/", "/?view=ledger", "/impact", "/?view=terms", "/?view=privacy", "/?view=refund", "/?view=contact", "/?view=pay", "/?view=pay&amt=50"):
        code, _, h = get(server, path)
        assert code == 200 and h.count("<h1") == 1, path
    code, h = _post(server, "Government will give Rs 5000 to every woman.")
    assert h.count("<h1") == 1


# ------------------------------------------------------------------ robots.txt and sitemap.xml

@pytest.mark.parametrize("path", ["/?view=robots", "/robots.txt"])
def test_robots_txt(server, monkeypatch, path):
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    code, hdr, body = get(server, path)
    assert code == 200 and hdr["Content-Type"].startswith("text/plain")
    assert "User-agent: *" in body and "Allow: /" in body and f"Sitemap: {EXAMPLE}/sitemap.xml" in body
    assert "Disallow: /?api=" in body and "Disallow: /?view=pay" in body and "Disallow: /?view=tipqr" in body


@pytest.mark.parametrize("path", ["/?view=sitemap", "/sitemap.xml"])
def test_sitemap_xml(server, monkeypatch, path):
    monkeypatch.setenv("SACH_SITE_URL", EXAMPLE)
    code, hdr, body = get(server, path)
    assert code == 200 and hdr["Content-Type"].startswith("application/xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", body)
    assert locs == [EXAMPLE + p for p in ("/", "/impact", "/?view=ledger", "/?view=terms", "/?view=privacy", "/?view=refund", "/?view=contact")]
    assert body.startswith('<?xml version="1.0" encoding="UTF-8"?>') and 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in body
    assert "view=pay" not in body and "text=" not in body


def test_robots_and_sitemap_use_the_request_host_without_env(server):
    host, port = server.replace("http://", "").split(":")
    c = http.client.HTTPConnection(host, int(port))
    c.putrequest("GET", "/robots.txt", skip_host=True)
    c.putheader("Host", "sach.example.com")
    c.endheaders()
    assert "Sitemap: https://sach.example.com/sitemap.xml" in c.getresponse().read().decode()


def test_vercel_rewrites_for_robots_and_sitemap_come_before_the_catch_all():
    rw = json.loads((ROOT / "vercel.json").read_text())["rewrites"]
    src = [r["source"] for r in rw]
    assert src.index("/robots.txt") < src.index("/(.*)") and src.index("/sitemap.xml") < src.index("/(.*)") and src[-1] == "/(.*)"
    dest = {r["source"]: r["destination"] for r in rw}
    assert dest["/robots.txt"] == "/api/index?view=robots" and dest["/sitemap.xml"] == "/api/index?view=sitemap"
    assert dest["/impact"] == "/api/index?view=impact" and dest["/(.*)"] == "/api/index"          # the existing rewrites are unchanged


# ------------------------------------------------------------------ preview image

def test_og_image_is_a_valid_1200x630_png_served_with_long_cache(server):
    code, hdr, body = _raw_get(server, "/?view=ogimage")
    assert code == 200 and hdr["Content-Type"] == "image/png" and "max-age=2592000" in hdr["Cache-Control"]
    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(body):
        n, tag = struct.unpack(">I4s", body[pos:pos + 8])
        data = body[pos + 8:pos + 8 + n]
        assert zlib.crc32(tag + data) & 0xFFFFFFFF == struct.unpack(">I", body[pos + 8 + n:pos + 12 + n])[0]
        chunks[tag] = data
        pos += 12 + n
    w, h, depth, ctype = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (w, h, depth, ctype) == (1200, 630, 8, 2)
    raw = zlib.decompress(chunks[b"IDAT"])
    assert len(raw) == h * (1 + w * 3)
    px = lambda x, y: tuple(raw[y * (1 + w * 3) + 1 + x * 3: y * (1 + w * 3) + 4 + x * 3])
    assert px(5, 5) == (0xF2, 0xEB, 0xDB)              # paper background
    assert px(150, 200) == (0xC2, 0x32, 0x1F)          # the red mark on the left
    assert pwa.og_png() is pwa.og_png()                # built once


# ------------------------------------------------------------------ result markup on a phone

def test_result_has_action_grid_summary_details_and_labelled_table(server):
    code, h = _post(server, FWD)
    assert code == 200
    acts = h[h.index('<div class="row actions"'):]
    acts = acts[:acts.index("</div>") + 6]
    assert 'role="group"' in acts and acts.index("Share on WhatsApp") < acts.index("Copy card") < acts.index("Download image")
    assert 'class="btn wa"' in acts and 'class="btn ghost" id="copy"' in acts and 'id="img-share"' in acts and "hidden" in acts
    signs = h[h.index('<section class="signs"'):]
    signs = signs[:signs.index("</section>")]
    assert re.search(r'<p class="sg-sum">\d+ warning signs: [^<]+</p>', signs)
    assert signs.count("<li>") >= 3 and signs.index("sg-all") > signs.index("<ul>")
    first_ul = signs[signs.index("<ul>"):signs.index("</ul>")]
    assert first_ul.count("<li>") == 2                                    # two signs open, the rest inside <details>
    assert re.search(r'<details class="sg-all"><summary>Show all \d+ signs</summary>', signs)
    for label in ("Claim", "Verdict", "Citations"):
        assert f'data-label="{label}"' in h
    assert '<table class="stack" role="table">' in h and "<thead" in h and "<th" in h           # the real table stays
    assert "@media(max-width:560px)" in h and "attr(data-label)" in h


def test_one_sign_has_no_details_and_singular_summary():
    h = signs_html([{"id": "asks_secret", "severity": "high", "title": "t", "why": "w", "evidence": "share OTP"}], "en")
    assert "1 warning sign: asks for OTP or PIN" in h and "<details" not in h and h.count("<li>") == 1


def test_signs_summary_is_localised_and_escaped():
    hi = signs_html([{"id": "asks_secret", "severity": "high", "evidence": "x"}, {"id": "forward_chain", "severity": "medium", "evidence": "y"}], "hi")
    assert "2 चेतावनी संकेत:" in hi and "sg-sum" in hi and "<details" not in hi
    evil = signs_html([{"id": "nope", "severity": "high", "title": "<img src=x onerror=alert(1)>", "why": "<b>", "evidence": "<script>"}] * 3, "en")
    assert "<img" not in evil and "<script>" not in evil and "&lt;img" in evil and "&lt;script&gt;" in evil


def test_hostile_text_is_still_escaped_in_the_result(server):
    code, h = _post(server, "<script>alert(1)</script> Government will give Rs 5000 to every woman. Share your OTP <img src=x onerror=alert(2)>")
    assert code == 200 and "<script>alert(1)</script>" not in h and "<img src=x" not in h and "&lt;script&gt;alert(1)&lt;/script&gt;" in h


# ------------------------------------------------------------------ evaluation numbers on the home page

def write_eval(tmp_path, monkeypatch, d):
    p = tmp_path / "eval_summary.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(site, "EVAL_PATH", str(p))


NEW = {"n": 77, "correct": 61, "overclaimed_false": 0, "overclaimed_true": 1, "abstained": 12, "abstained_wrong": 1,
       "commit": "abcdef1234567890", "dirty": False, "date": "2026-11-20T08:30:00Z", "by_lang": {}}


def test_home_shows_numbers_from_the_file(tmp_path, monkeypatch):
    write_eval(tmp_path, monkeypatch, NEW)
    h = site.home().decode()
    assert ">77<" in h and ">61/77<" in h and ">1<" in h and ">12<" in h              # n, correct/n, overclaims (0 FALSE + 1 TRUE), abstained
    assert "<code>abcdef1</code>" in h and "abcdef12" not in h and "2026-11-20" in h and "08:30" not in h
    assert "docs/evaluation.md" in h and "Evaluation pending" not in h and "26/31" not in h
    write_eval(tmp_path, monkeypatch, dict(NEW, n=90, correct=70, commit="1234567"))      # changes with the file
    h = site.home().decode()
    assert ">90<" in h and ">70/90<" in h and "<code>1234567</code>" in h and ">77<" not in h


def test_home_says_pending_for_old_format_degraded_or_missing_file(tmp_path, monkeypatch):
    old = {"n": 31, "correct": 26, "overclaimed_false": 0, "abstained": 5, "abstained_wrong": 0}
    for d in (old, dict(NEW, degraded=True), dict(NEW, mode="fallback"), {k: v for k, v in NEW.items() if k != "commit"},
              {k: v for k, v in NEW.items() if k != "date"}, dict(NEW, n=0), dict(NEW, correct="61"), {}, []):
        write_eval(tmp_path, monkeypatch, d)
        h = site.home().decode()
        assert "Evaluation pending" in h and "docs/evaluation.md" in h, d
        assert "26/31" not in h and "61/77" not in h and "<code>" not in h, d
    monkeypatch.setattr(site, "EVAL_PATH", str(tmp_path / "missing.json"))
    assert "Evaluation pending" in site.home().decode()
    (tmp_path / "bad.json").write_text("{not json")
    monkeypatch.setattr(site, "EVAL_PATH", str(tmp_path / "bad.json"))
    assert "Evaluation pending" in site.home().decode()


def test_no_evaluation_number_is_hard_coded_in_site_source():
    src = (ROOT / "sach" / "site.py").read_text(encoding="utf-8")
    assert "26/31" not in src and "ev['correct']" not in src


def test_evaluation_values_are_escaped(tmp_path, monkeypatch):
    write_eval(tmp_path, monkeypatch, dict(NEW, commit="<b>x</b>zzzz", date="<i>2026</i>"))
    h = site.home().decode()
    assert "<b>x</b>" not in h and "&lt;b&gt;x" in h
