"""SHARE work package: shareable result links, the WhatsApp message, paste-and-check, share-target launches, image share, how-to helper.
All offline: fake LLM, fake retriever, fake OCR judge."""
import http.client, json, re, threading, time, urllib.parse as up
import pytest
from http.server import ThreadingHTTPServer
import sach.web as W
from sach import cache, share, site, store, pwa
from sach.lang import SUPPORTED
from sach.models import *
from sach.pipeline import check_forward
from sach.site import result_block, home, layout, site_url
from test_sach import FakeRetriever, TS

FWD = "Government will give Rs 5000 to every woman. Please forward to all groups!"
PIB = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
               "Fake claim: government will give Rs 5000 to every woman", "Fake message claims government will give Rs 5000 to every woman")
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64


class FakeLLM:
    failures = 0
    judges = []
    def stance(self, claim, title, text, tier=None):
        return "contradicts" if tier == TIER_PIB else "none"


class FakeJudge:
    name, models, exhausted_until = "fake", ["m"], 0.0
    def __init__(self, reply="Rs 1000 for every woman, forward now"):
        self.reply, self.calls = reply, 0
    def available(self): return True
    def transcribe_image(self, b, mime):
        self.calls += 1
        return self.reply


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch):
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR", "SACH_SITE_URL"):
        monkeypatch.delenv(k, raising=False)
    store.reset()
    yield
    store.reset()


@pytest.fixture
def srv():
    W._hits.clear()
    llm = FakeLLM()
    W.Handler.retrievers, W.Handler.llm = [FakeRetriever([PIB])], llm
    s = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}", llm
    s.shutdown()
    W.Handler.llm = None


def req(base, method, path, body=None, headers=None):
    host, port = base.replace("http://", "").split(":")
    c = http.client.HTTPConnection(host, int(port))
    c.request(method, path, body, headers or {})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace")


def post_text(base, text, path="/"):
    return req(base, "POST", path, up.urlencode({"text": text}), {"Content-Type": "application/x-www-form-urlencoded"})


def multipart(parts, boundary="XbOuNdX"):
    out = b""
    for name, value, fname, ctype in parts:
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"".encode()
        if fname:
            out += f"; filename=\"{fname}\"".encode()
        out += b"\r\n" + (f"Content-Type: {ctype}\r\n".encode() if ctype else b"") + b"\r\n" + (value if isinstance(value, bytes) else value.encode()) + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def textarea(h):
    from html import unescape
    return unescape(re.search(r'<textarea id="text"[^>]*>(.*?)</textarea>', h, re.S).group(1))


def share_id_in(h):
    m = re.search(r"/\?r=([0-9a-f]{12})", up.unquote(h))
    return m.group(1) if m else None


def result(text=FWD, **kw):
    return check_forward(text, [FakeRetriever([PIB])], FakeLLM(), **kw)


# ---------------------------------------------------------------- share id and the permalink page
def test_share_id_is_first_12_hex_of_the_cache_key_and_stored_for_storable_results():
    res = result()
    rid = share.ensure_share(FWD, None, res)
    assert rid == cache.key(FWD, None)[len("cache:"):][:12] and share.valid_id(rid)
    rec = store.get_store().get("share:" + rid)
    assert rec["key"] == cache.key(FWD, None) and rec["text"] == FWD and rec["result"]["verdict"] == "FALSE"


@pytest.mark.parametrize("mut", [{"degraded": True}, {"search_status": "down"}, {"no_claims": True}])
def test_non_storable_results_get_no_share_id(mut):
    res = dict(result(), **mut)
    assert share.ensure_share(FWD, None, res) is None
    assert store.get_store().get("share:" + cache.key(FWD, None)[len("cache:"):][:12]) is None


def test_timed_out_result_gets_no_share_id():
    res = result()
    res = dict(res, claims=[dict(res["claims"][0], reason_code="timed_out")])
    assert share.ensure_share(FWD, None, res) is None


def test_share_ttl_matches_the_cache_entry(monkeypatch):
    seen = {}
    st = store.get_store()
    orig = st.set
    monkeypatch.setattr(st, "set", lambda k, v, ttl_s=None: (seen.__setitem__(k, ttl_s), orig(k, v, ttl_s=ttl_s)))
    share.ensure_share(FWD, None, result())
    seen = {k: v for k, v in seen.items() if k.startswith("share:")}
    assert seen and 7 * 24 * 3600 - 120 <= list(seen.values())[0] <= 7 * 24 * 3600
    seen.clear()
    unv = dict(result(), verdict="UNVERIFIED")
    share.ensure_share("something else entirely about nothing", None, unv)
    assert [v for k, v in seen.items() if k.startswith("share:")][0] <= 6 * 3600


def test_collision_with_a_different_key_gives_no_link_and_load_verifies_the_key():
    res = result()
    rid = cache.key(FWD, None)[len("cache:"):][:12]
    store.get_store().set("share:" + rid, {"key": "cache:" + "f" * 64, "text": "other", "result": res}, ttl_s=60)
    assert share.ensure_share(FWD, None, res) is None
    assert share.load_share(rid) is None                      # the stored key does not belong to this id


@pytest.mark.parametrize("bad", ["", "ABCDEF123456", "abcdef12345", "abcdef1234567", "../etc/pass", "abcdef12345g", "<script>", None, "abcdef12345 "])
def test_valid_id_is_strict(bad):
    assert not share.valid_id(bad)
    assert share.load_share(bad) is None


def test_check_posts_a_permalink_and_r_renders_it(srv):
    base, _ = srv
    code, hdr, h = post_text(base, FWD)
    rid = share_id_in(h)
    assert code == 200 and rid
    code, hdr, p = req(base, "GET", f"/?r={rid}")
    assert code == 200 and hdr["Cache-Control"] == "no-store"
    assert "Someone shared this Sach check with you" in p and "Government will give Rs 5000 to every woman" in p
    assert "First checked on " in p and "Check your own forward" in p and "How this verdict was reached" in p
    assert 'content="noindex,follow"' in p and 'class="stamp big FALSE"' in p
    assert textarea(p) == ""                                    # the checker below is empty


def test_permalink_page_escapes_the_stored_forward(srv):
    base, _ = srv
    evil = '</blockquote><script>alert(1)</script> Government will give Rs 5000 to every woman'
    rid = share.ensure_share(evil, None, result(evil))
    p = req(base, "GET", f"/?r={rid}")[2]
    assert "<script>alert(1)" not in p and "&lt;script&gt;alert(1)" in p


def test_expired_or_missing_id_gives_the_friendly_page(srv):
    base, _ = srv
    code, hdr, p = req(base, "GET", "/?r=0123456789ab")
    assert code == 404 and hdr["Cache-Control"] == "no-store" and "This shared result has expired. Paste the forward to check it again." in p


@pytest.mark.parametrize("hostile", ["<script>alert(7)</script>", '"><img src=x onerror=alert(8)>', "zzzzzzzzzzzz", "../../etc/passwd", "a" * 5000])
def test_hostile_ids_are_rejected_and_not_reflected(srv, hostile):
    base, _ = srv
    code, hdr, p = req(base, "GET", "/?r=" + up.quote(hostile))
    assert code == 404 and "expired" in p
    assert hostile not in p and "alert(7)" not in p and "onerror=alert(8)" not in p


def test_expired_record_is_a_miss(srv, monkeypatch):
    base, _ = srv
    rid = share.ensure_share(FWD, None, result())
    real = time.time
    monkeypatch.setattr("sach.store._now", lambda: real() + 8 * 24 * 3600)
    assert req(base, "GET", f"/?r={rid}")[0] == 404


def test_limited_mode_result_has_no_link_and_message_omits_it(srv):
    base, llm = srv
    W.Handler.llm = None
    code, _, h = post_text(base, FWD)
    assert code == 200 and share_id_in(h) is None and "Full evidence: " + site_url() not in up.unquote(h)


def test_robots_disallows_shared_links(srv):
    assert "Disallow: /?r=" in req(srv[0], "GET", "/robots.txt")[2]


# ---------------------------------------------------------------- the WhatsApp message
def mk_res(lang="en", claim="Government will give Rs 5000 to every woman"):
    res = result()
    res = dict(res, language=lang)
    res["claims"] = [dict(res["claims"][0], claim={"text": claim, "domain": "scheme"})]
    return res


def test_share_text_has_card_claim_permalink_and_cta():
    res = mk_res()
    t = share.build_share_text(res, "https://sach.example", "https://sach.example/?r=0123456789ab")
    assert t.startswith(res["card"])
    assert "Claim checked: “Government will give Rs 5000 to every woman”" in t
    assert "Full evidence: https://sach.example/?r=0123456789ab" in t
    assert t.endswith("Got a forward you're unsure about? Check it free on Sach: https://sach.example")
    assert len(t) < 900


def test_share_text_uses_citation_link_when_no_permalink_and_does_not_duplicate_it():
    res = mk_res()
    assert "https://pib.gov.in/PressReleasePage.aspx?PRID=1" in res["card"]
    t = share.build_share_text(res, "https://s.example")
    assert t.count("https://pib.gov.in/PressReleasePage.aspx?PRID=1") == 1
    res2 = dict(res, card="❌ FALSE\nsomething")                      # card without a link: main citation link is added
    assert "Full evidence: https://pib.gov.in/PressReleasePage.aspx?PRID=1" in share.build_share_text(res2, "https://s.example")


def test_share_text_truncates_claim_and_stays_under_cap_without_cutting_urls():
    long = "word " * 120
    res = mk_res(claim=long)
    link = "https://sach.example/?r=0123456789ab"
    t = share.build_share_text(res, "https://sach.example", link)
    claim_line = [l for l in t.split("\n") if l.startswith("Claim checked:")][0]
    assert len(claim_line) <= len("Claim checked: “”") + 140 and "…" in claim_line
    assert len(t) <= share.SHARE_MAX and link in t and "https://sach.example" in t.split("\n")[-1]
    for u in re.findall(r"https?://\S+", t):
        assert u.rstrip(".,”") in (link, "https://sach.example", "https://pib.gov.in/PressReleasePage.aspx?PRID=1")


def test_share_text_drops_the_claim_before_it_would_cut_anything():
    res = mk_res(claim="x" * 400)
    res["card"] = res["card"] + "\n" + ("y " * 300)
    t = share.build_share_text(res, "https://sach.example", "https://sach.example/?r=0123456789ab")
    assert "Claim checked" not in t and "Full evidence: https://sach.example/?r=0123456789ab" in t


def test_share_text_cta_in_hindi_and_telugu_and_english_elsewhere():
    for lang, frag in (("hi", "Sach पर मुफ़्त में जाँचें"), ("te", "Sach లో ఉచితంగా")):
        assert frag in share.build_share_text(mk_res(lang), "https://s.example")
    for lang in ("bn", "ta", "mni", "ur"):
        assert "Check it free on Sach: https://s.example" in share.build_share_text(mk_res(lang), "https://s.example")


def test_wa_url_round_trips_hostile_text():
    evil = '“</a><script>alert(1)</script>” & 100% sure ?x=1#frag \n"quoted" 😀'
    res = mk_res(claim=evil)
    t = share.build_share_text(res, "https://s.example")
    u = share.wa_url(t)
    assert u.startswith("https://wa.me/?text=") and not re.search(r"[<>\"' \n&#]", u[len("https://wa.me/?text="):])
    assert up.unquote(u.split("text=", 1)[1]) == t


# ---------------------------------------------------------------- result markup
def test_result_markup_wa_first_more_ways_sticky_bar_invite():
    res = dict(result(), warning_signs=[])
    b = result_block(res, link="https://s.example/?r=0123456789ab")
    acts = b[b.index('<div class="row actions"'):]
    acts = acts[:acts.index("</div>") + 6]
    assert acts.index('class="btn wa"') < acts.index('id="more-share"') < acts.index('id="copy"')
    assert "Share on WhatsApp" in acts and "More ways to share" in acts and "hidden" in acts[acts.index('id="more-share"'):][:80]
    m = re.search(r'id="shareWa" href="([^"]+)"', b)
    from html import unescape
    msg = up.unquote(unescape(m.group(1)).split("text=", 1)[1])
    assert "Full evidence: https://s.example/?r=0123456789ab" in msg
    assert "wa.me/?text=" in b and f"free%2C%20in%20{len([c for c in SUPPORTED if c != 'tl'])}%20languages" in b
    data = json.loads(re.search(r'id="sach-share-data">(.*?)</script>', b, re.S).group(1))
    assert data["text"] == msg                                                   # copy and Web Share use the same text
    assert "Tell your family about Sach" in b
    page = layout(b).decode()
    assert 'id="sharebar"' in page and 'Share verdict on WhatsApp' in page and "IntersectionObserver" in page
    assert "safe-area-inset-bottom" in page and "prefers-reduced-motion" in page
    assert page.count("Tell your family about Sach") >= 2                         # footer and below the result


def test_invite_text_computes_language_count_from_supported():
    n = len([c for c in SUPPORTED if c != "tl"])
    t = share.invite_text("https://s.example")
    assert n == 16 and f"free, in {n} languages: https://s.example" in t
    assert t.startswith("Got a WhatsApp forward you're unsure about? Sach checks it against PIB and official sources")


def test_site_url_is_used_not_hard_coded(monkeypatch):
    monkeypatch.setenv("SACH_SITE_URL", "https://example.org")
    b = result_block(dict(result(), warning_signs=[]))
    assert "example.org" in up.unquote(b)


# ---------------------------------------------------------------- inbound: paste and check, countdown, helper
def test_paste_and_check_markup_and_script_reads_clipboard_only_in_a_click():
    h = home().decode()
    assert 'id="pastego"' in h and "Paste and check" in h and 'id="pastemsg" role="status" aria-live="polite"' in h
    assert "Long-press in the box and tap Paste, then press Check." in share.JS
    js = share.JS
    assert js.count("readText()") == 1
    handler = js.index("pg.addEventListener('click'")
    assert js.index("readText()") > handler and js.count("readText") == 2           # one feature test + one call, both inside the handler
    assert "requestSubmit" in js and "Your clipboard is empty" in js
    # no other script reads the clipboard outside a click handler
    assert "readText" not in site.JS.split("const pb=$('#paste')")[0] and "readText" not in layout("x").decode().split("<main")[0]


def test_via_share_get_renders_prefill_and_countdown_but_plain_text_does_not(srv):
    base, _ = srv
    code, hdr, h = req(base, "GET", "/?via=share&text=" + up.quote("Rs 1000 for all"))
    assert code == 200 and hdr["Cache-Control"] == "no-store" and 'content="noindex,follow"' in h
    assert textarea(h) == "Rs 1000 for all" and 'id="autorun"' in h and "Checking this forward in" in h and 'id="autorun-cancel"' in h
    code, hdr, h = req(base, "GET", "/?text=" + up.quote("Rs 1000 for all"))
    assert textarea(h) == "Rs 1000 for all" and 'id="autorun"' not in h and "Checking this forward in" not in h.split("<script")[0]
    h = req(base, "GET", "/?via=share")[2]
    assert 'id="autorun"' not in h                                                   # nothing shared: nothing to count down


def test_countdown_script_cancel_and_typing_stop_it():
    assert "autorun-cancel" in share.JS and "ta.addEventListener('input',stop)" in share.JS and "n=3" in share.JS


def test_helper_has_every_route_and_guards_storage():
    h = home().decode()
    for needle in ('id="howto" open', "How to check a WhatsApp forward", "long-press the message → tap Share (↗) → choose Sach",
                   "Install Sach once (one tap)", 'id="howto-install"', "Copy → come back here → tap Paste and check",
                   "Add Sach to your Home Screen: tap Share → Add to Home Screen.", "In WhatsApp Web, copy the message, then click Paste and check."):
        assert needle in h, needle
    js = share.JS
    for call in ("localStorage.getItem('sach-howto-closed')", "localStorage.removeItem", "localStorage.setItem('sach-howto-closed','1')"):
        i = js.index(call)
        assert "try{" in js[max(0, i - 120):i], call
    assert "display-mode: standalone" in js and "getInstalledRelatedApps" in js and "beforeinstallprompt" in js


# ---------------------------------------------------------------- manifest and share-target POST
def test_manifest_share_target_is_post_multipart_with_files(srv):
    st = json.loads(req(srv[0], "GET", "/?view=manifest")[2])["share_target"]
    assert st["action"] == "/?via=share" and st["method"] == "POST" and st["enctype"] == "multipart/form-data"
    assert st["params"]["files"] == [{"name": "files", "accept": share.SHARE_ACCEPT}]


def test_post_multipart_text_share_prefills_with_countdown_no_store_noindex(srv):
    base, _ = srv
    body, hd = multipart([("title", "Big news", None, None), ("text", "Rs 1000 for all", None, None), ("url", "", None, None)])
    code, hdr, h = req(base, "POST", "/?via=share", body, hd)
    assert code == 200 and hdr["Cache-Control"] == "no-store" and 'content="noindex,follow"' in h
    assert textarea(h) == "Big news\nRs 1000 for all" and 'id="autorun"' in h and "Please check this text" not in h


@pytest.mark.parametrize("data,mime", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")])
def test_post_image_share_runs_ocr_and_shows_text_for_review_without_autorun(srv, data, mime):
    base, llm = srv
    j = FakeJudge("Rs 1000 for every woman <b>x</b>")
    llm.judges = [j]
    body, hd = multipart([("files", data, "shot.bin", mime)])
    code, hdr, h = req(base, "POST", "/?via=share", body, hd)
    assert code == 200 and j.calls == 1 and hdr["Cache-Control"] == "no-store"
    assert textarea(h) == "Rs 1000 for every woman <b>x</b>" and "&lt;b&gt;x&lt;/b&gt;" in h
    assert "Please check this text before you press Check." in h and 'id="autorun"' not in h and "Claims checked" not in h


def test_image_type_is_decided_by_magic_bytes_not_declared_type(srv):
    base, llm = srv
    llm.judges = [FakeJudge()]
    body, hd = multipart([("files", b"<html>not an image</html>" + b"0" * 50, "x.jpg", "image/jpeg")])
    code, _, h = req(base, "POST", "/?via=share", body, hd)
    assert code == 400 and "JPEG, PNG or WebP" in h and llm.judges[0].calls == 0


def test_image_over_5mb_and_body_over_6mb_are_rejected(srv):
    base, llm = srv
    llm.judges = [FakeJudge()]
    body, hd = multipart([("files", JPEG + b"0" * 5_000_100, "x.jpg", "image/jpeg")])
    assert req(base, "POST", "/?via=share", body, hd)[0] == 413
    import socket                                               # declare a 7 MB body: the server must refuse before reading it
    sk = socket.create_connection(base.replace("http://", "").split(":")[0:1] + [int(base.rsplit(":", 1)[1])])
    sk.sendall(b"POST /?via=share HTTP/1.1\r\nHost: x\r\nContent-Type: multipart/form-data; boundary=b\r\nContent-Length: 7000000\r\n\r\n")
    assert b" 413 " in sk.recv(200).split(b"\r\n")[0] + b" "
    sk.close()
    assert llm.judges[0].calls == 0


def test_parse_multipart_limits_and_garbage():
    with pytest.raises(share.ShareError):
        share.parse_multipart("multipart/form-data", b"x")                         # no boundary
    with pytest.raises(share.ShareError):
        share.parse_multipart("text/plain", b"x")
    many = multipart([(f"f{i}", "v", None, None) for i in range(share.MAX_PARTS + 2)])
    with pytest.raises(share.ShareError):
        share.parse_multipart(many[1]["Content-Type"], many[0])
    body, hd = multipart([("text", "a" * 20000, None, None)])
    f, imgs = share.parse_multipart(hd["Content-Type"], body)
    assert len(f["text"]) == share.MAX_FIELD and imgs == []


def test_ocr_unavailable_gives_the_friendly_message_and_stores_nothing(srv, tmp_path, monkeypatch):
    base, llm = srv
    llm.judges = []                                                                   # no judge: OCR unavailable
    body, hd = multipart([("files", PNG, "s.png", "image/png")])
    code, _, h = req(base, "POST", "/?via=share", body, hd)
    from sach import ocr
    assert code == 503 and ocr.UNAVAILABLE in h and textarea(h) == ""
    assert not list(tmp_path.rglob("*.png")) and share.sniff_mime(PNG) == "image/png"
    # nothing image-related in the store
    st = store.get_store()
    assert st.get("share:" + "0" * 12) is None


def test_image_share_shares_the_ocr_rate_limit_bucket(srv):
    from sach import ocr
    base, llm = srv
    llm.judges = [FakeJudge()]
    body, hd = multipart([("files", JPEG, "s.jpg", "image/jpeg")])
    codes = [req(base, "POST", "/?via=share", body, hd)[0] for _ in range(ocr.OCR_LIMIT + 1)]
    assert codes[:ocr.OCR_LIMIT] == [200] * ocr.OCR_LIMIT and codes[-1] == 429


def test_nothing_image_related_is_logged_or_stored(srv, capsys, monkeypatch):
    base, llm = srv
    llm.judges = [FakeJudge("secret screenshot words")]
    sets = []
    st = store.get_store()
    monkeypatch.setattr(st, "set", lambda *a, **k: sets.append(a))
    body, hd = multipart([("files", JPEG, "s.jpg", "image/jpeg")])
    req(base, "POST", "/?via=share", body, hd)
    out = capsys.readouterr()
    assert sets == [] and "secret screenshot words" not in out.out + out.err


def test_service_worker_does_not_intercept_posts_or_share_urls():
    sw = pwa.SW_JS
    assert "if (req.method !== 'GET') return;" in sw
    assert "isPlainHome = u => u.pathname === '/' && u.search === ''" in sw         # /?via=share and /?r= are never cached
    assert "share" not in sw.split("self.addEventListener('fetch'")[1].replace("share-target", "")


def test_privacy_page_mentions_share_links_and_image_shares(srv):
    p = req(srv[0], "GET", "/?view=privacy")[2]
    assert "A share link shows the checked message and Sach&#x27;s result" in p or "A share link shows the checked message and Sach's result" in p
    assert "7 days for TRUE/FALSE/MISLEADING, 6 hours for UNVERIFIED" in p and "not indexed by search engines" in p
    assert "share an image into Sach" in p and "not stored" in p


# ---------------------------------------------------------------- the skipped sentences never reach the public share record
def test_share_record_never_stores_the_skipped_sentences_and_the_permalink_does_not_show_them(srv):
    from test_cache_trace import run as run_check
    from test_pagehonesty import LONG
    out, _ = run_check(LONG, log=False)
    assert out["extraction"]["skipped"]                                  # the private result does hold them (it may stay in the cache)
    rid = share.ensure_share(LONG, None, out)
    assert rid
    assert share.load_share(rid)["result"]["extraction"] == {"sentences": 8, "checked": 5}     # counts only (DEF-2)
    assert "extraction" in store.get_store().get("share:" + rid)["result"]
    assert "skipped" not in store.get_store().get("share:" + rid)["result"]["extraction"]
    base, _ = srv
    p = req(base, "GET", f"/?r={rid}")[2]
    assert "Not checked" not in p and "Checked 5 of 8 sentences" in p                       # the counts line, not the list (DEF-2)


# ---------------------------------------------------------------- DEF-2: the share record keeps counts only, and the permalink says what was not checked
def test_share_record_stores_only_the_two_extraction_counts(srv):
    from test_cache_trace import run as run_check
    from test_pagehonesty import LONG
    out, _ = run_check(LONG, log=False)
    rid = share.ensure_share(LONG, None, out)
    assert rid
    assert share.load_share(rid)["result"]["extraction"] == {"sentences": 8, "checked": 5}
    stored = store.get_store().get("share:" + rid)["result"]["extraction"]
    assert set(stored) == {"sentences", "checked"} and all(type(v) is int for v in stored.values())

def test_permalink_says_checked_m_of_n_and_lists_no_skipped_sentence(srv):
    import html as _html
    from test_cache_trace import run as run_check
    from test_pagehonesty import LONG
    base, _ = srv
    out, _ = run_check(LONG, log=False)
    skipped = ["Good morning everyone friends.", "Click the link now to register.",
               "Bank loans for small shops get an interest subsidy this year."]
    rid = share.ensure_share(LONG, None, out)
    p = req(base, "GET", f"/?r={rid}")[2]
    assert "Checked 5 of 8 sentences" in p
    assert "are not checked" in p                                        # the explanation of short and call-to-action sentences
    outside_forward = re.sub(r'<blockquote class="fwd">.*?</blockquote>', "", p, flags=re.S)
    for s in skipped:
        assert s not in outside_forward and _html.escape(s) not in outside_forward
    assert "Not checked" not in p

def test_permalink_has_no_counts_line_when_all_sentences_were_checked_or_key_absent(srv):
    from test_cache_trace import run as run_check
    base, _ = srv
    one = "Government will give Rs 5000 to every woman."
    out, _ = run_check(one, log=False)
    rid = share.ensure_share(one, None, out)
    assert rid and share.load_share(rid)["result"]["extraction"] == {"sentences": 1, "checked": 1}
    assert "sentences</summary>" not in req(base, "GET", f"/?r={rid}")[2]
    from test_pagehonesty import LONG
    out2, _ = run_check(LONG, log=False)
    out2.pop("extraction")
    rid2 = share.ensure_share(LONG, None, out2)
    assert rid2 and "sentences</summary>" not in req(base, "GET", f"/?r={rid2}")[2]
