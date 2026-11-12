"""Installable app: manifest, icons, share target, service worker, install prompt, private history."""
import json, re, struct, zlib, threading
import urllib.parse as up
import pytest
from sach import pwa, site
from sach.site import MAX_CHARS
from test_sach import server, _raw_get, _post      # noqa: F401  (fixtures and helpers from the existing suite)


def get(base, path):
    code, hdr, body = _raw_get(base, path)
    return code, hdr, body


def png_info(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        assert zlib.crc32(tag + body) & 0xFFFFFFFF == struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        chunks[tag] = body
        pos += 12 + n
    w, h, depth, ctype = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    raw = zlib.decompress(chunks[b"IDAT"])
    assert len(raw) == h * (1 + w * 4) and depth == 8 and ctype == 6
    return w, h, raw


# ------------------------------------------------------------------ manifest

def test_manifest_fields_and_content_type(server):
    code, hdr, body = get(server, "/?view=manifest")
    assert code == 200 and hdr["Content-Type"].startswith("application/manifest+json")
    m = json.loads(body)
    assert m["name"] == "Sach: check a forward" and m["short_name"] == "Sach" and m["lang"] == "en"
    assert m["start_url"] == "/" and m["scope"] == "/" and m["display"] == "standalone"
    assert m["theme_color"] == m["background_color"] == "#f2ebdb" and m["description"] and m["categories"]
    assert "#f2ebdb" in site.layout("x").decode()            # same colour as the page's theme-color meta


def test_manifest_icons_point_at_working_routes(server):
    m = json.loads(get(server, "/?view=manifest")[2])
    purposes = {(i["sizes"], i["purpose"]) for i in m["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("192x192", "maskable"), ("512x512", "maskable")} <= purposes
    for i in m["icons"]:
        code, hdr, body = get(server, i["src"])
        assert code == 200 and hdr["Content-Type"] == "image/png" and i["type"] == "image/png"
        assert png_info(body)[:2] == (int(i["sizes"].split("x")[0]),) * 2


def test_manifest_share_target_shape(server):
    st = json.loads(get(server, "/?view=manifest")[2])["share_target"]
    assert st == {"action": "/", "method": "GET", "params": {"title": "title", "text": "text", "url": "url"}}


# ------------------------------------------------------------------ icons

@pytest.mark.parametrize("size", [180, 192, 512])
def test_icon_sizes_are_valid_pngs_with_cache_header(server, size):
    code, hdr, body = get(server, f"/?view=icon&size={size}")
    w, h, raw = png_info(body)
    assert code == 200 and (w, h) == (size, size) and hdr["Cache-Control"] == "public, max-age=86400"
    # brand red somewhere, white somewhere (the S), and a red-dominant centre-left pixel pattern
    px = {raw[1 + y * (1 + w * 4) + 4 * x + 0:1 + y * (1 + w * 4) + 4 * x + 3] for y in range(0, h, 7) for x in range(0, w, 7)}
    assert bytes((0xC2, 0x32, 0x1F)) in px and bytes((255, 255, 255)) in px


@pytest.mark.parametrize("bad", ["", "0", "100", "256", "1024", "abc", "-192", "192.0", "192;"])
def test_other_icon_sizes_are_404(server, bad):
    assert get(server, f"/?view=icon&size={up.quote(bad)}")[0] == 404
    assert get(server, "/?view=icon")[0] == 404


def test_maskable_differs_from_plain_and_is_full_bleed(server):
    plain, mask = get(server, "/?view=icon&size=192")[2], get(server, "/?view=icon&size=192&maskable=1")[2]
    assert plain != mask
    w, _, raw = png_info(mask)
    assert raw[1 + 3] == 255                                   # top-left pixel is opaque: no rounded transparent corner
    _, _, rraw = png_info(plain)
    assert rraw[1 + 3] == 0                                    # plain icon has transparent rounded corners


# ------------------------------------------------------------------ service worker

def test_service_worker_headers(server):
    code, hdr, body = get(server, "/?view=sw")
    assert code == 200 and hdr["Content-Type"].startswith("application/javascript")
    assert hdr["Service-Worker-Allowed"] == "/" and hdr["Cache-Control"] == "no-cache"
    assert body.decode() == pwa.SW_JS


def test_service_worker_source_has_offline_text_and_versioned_caches():
    s = pwa.SW_JS
    assert "Sach needs the internet to check a forward against official sources" in s and "Your text is still here" in s
    assert "const VERSION" in s and "caches.delete" in s and "skipWaiting" in s


def _sw_code():
    """The worker source without comments and without the offline page's HTML literal."""
    src = re.sub(r"/\*.*?\*/", "", pwa.SW_JS, flags=re.S)
    return "\n".join(l.split(" // ")[0] for l in src.splitlines() if not l.strip().startswith("//") and "const OFFLINE" not in l and not l.lstrip().startswith("'"))


@pytest.mark.parametrize("needle", ["api=", "view=pay", "tipqr", "go=tip", "text=", "title=", "url=", "view=ledger", "view=sw"])
def test_service_worker_code_never_names_a_forbidden_url(needle):
    """The only URLs the worker can cache are built from the narrow matchers; none of these patterns appears in its code at all."""
    assert needle not in _sw_code()


def test_service_worker_cache_rules_are_narrow():
    s = pwa.SW_JS
    assert "if (req.method !== 'GET') return;" in s                         # POSTs untouched
    assert "u.pathname === '/' && u.search === ''" in s                      # only the plain home page
    assert "v !== 'manifest' && v !== 'icon'" in s                           # only manifest and icons
    assert "no-store|private" in s                                           # honours no-store responses
    puts = re.findall(r"cache\.(put|add)\(([^)]*)\)", s)
    assert puts and all(arg.split(",")[0] in ("'/'", "req") for _, arg in puts)     # only '/' and static requests are written
    for forbidden in ("api=", "view=pay", "view=tipqr", "go=tip"):
        assert not re.search(r"(cache\.\w+|isStatic|isPlainHome)[^\n]*" + re.escape(forbidden), s)


def test_service_worker_plain_home_vs_static_matcher_logic():
    """Mirror the JS matchers in Python to pin the intended behaviour table."""
    def static(qs):
        p = up.parse_qs(qs, keep_blank_values=True)
        v = p.get("view", [None])[0]
        return v in ("manifest", "icon") and all(k == "view" or (v == "icon" and k in ("size", "maskable")) for k in p)
    assert static("view=manifest") and static("view=icon&size=192&maskable=1")
    for q in ("view=pay", "view=tipqr&fmt=png", "api=rzp-order", "go=tip", "text=hi", "view=manifest&text=x", "view=sw", "view=ledger"):
        assert not static(q)


# ------------------------------------------------------------------ layout

def test_layout_links_manifest_apple_tags_and_registration(server):
    for path in ("/", "/?view=ledger", "/?view=privacy"):
        h = get(server, path)[2].decode()
        for needle in ('<link rel="manifest" href="/?view=manifest">', 'rel="apple-touch-icon" href="/?view=icon&amp;size=180"',
                       'name="apple-mobile-web-app-capable" content="yes"', 'name="mobile-web-app-capable"',
                       'name="apple-mobile-web-app-status-bar-style"', 'name="apple-mobile-web-app-title" content="Sach"',
                       "navigator.serviceWorker.register('/?view=sw'", "'serviceWorker' in navigator", "location.protocol==='https:'",
                       "location.hostname==='localhost'"):
            assert needle in h, (path, needle)


def test_no_external_scripts_added_by_pwa():
    assert "src=" not in pwa.SCRIPT and "http://" not in pwa.JS and "https://" not in pwa.JS
    assert "importScripts" not in pwa.SW_JS and "https://" not in pwa.SW_JS


# ------------------------------------------------------------------ share target

class _Boom:
    name = "boom"
    def retrieve(self, *a, **k):
        raise AssertionError("pipeline must not run for a shared link")
    __call__ = retrieve
    def search(self, *a, **k):
        raise AssertionError("pipeline must not run for a shared link")


def textarea(html):
    m = re.search(r'<textarea[^>]*id="text"[^>]*>(.*?)</textarea>', html, re.S)
    assert m, "textarea missing"
    return m.group(1)


def test_share_target_prefills_without_checking_and_is_no_store(server, monkeypatch):
    import sach.web as W
    monkeypatch.setattr(W.Handler, "retrievers", [_Boom()])
    monkeypatch.setattr(W, "check_forward", lambda *a, **k: (_ for _ in ()).throw(AssertionError("check ran")))
    code, hdr, body = get(server, "/?text=" + up.quote("Govt gives Rs 1000 to all\nForward now!"))
    h = body.decode()
    assert code == 200 and hdr["Cache-Control"] == "no-store" and hdr["Content-Type"].startswith("text/html")
    assert textarea(h) == "Govt gives Rs 1000 to all\nForward now!"
    assert "Claims checked" not in h


def test_share_target_joins_title_text_url_and_dedupes(server):
    q = up.urlencode({"title": "Big news", "text": "Rs 1000 for all", "url": "https://example.com/x"})
    assert textarea(get(server, "/?" + q)[2].decode()) == "Big news\nRs 1000 for all\nhttps://example.com/x"
    q = up.urlencode({"text": "Rs 1000 for all https://example.com/x", "url": "https://example.com/x", "title": "Rs 1000 for all https://example.com/x"})
    assert textarea(get(server, "/?" + q)[2].decode()) == "Rs 1000 for all https://example.com/x"
    assert textarea(get(server, "/?url=" + up.quote("https://example.com/y"))[2].decode()) == "https://example.com/y"


def test_share_target_caps_length_and_strips_control_chars(server):
    h = get(server, "/?text=" + up.quote("a" * (MAX_CHARS + 500)))[2].decode()
    assert len(textarea(h)) == MAX_CHARS
    t = "ok\x00\x07text\x1b[31m‮evil\x7f end"
    v = textarea(get(server, "/?text=" + up.quote(t))[2].decode())
    assert v == "oktext[31mevil end" and not re.search(r"[\x00-\x08\x1b\x7f‮]", v)


def test_share_target_hostile_text_cannot_break_out(server):
    evil = '</textarea><script>alert(1)</script><img src=x onerror=alert(2)>"\''
    for key in ("text", "title", "url"):
        h = get(server, f"/?{key}=" + up.quote(evil))[2].decode()
        assert "<script>alert(1)" not in h and "<img src=x" not in h and "&lt;/textarea&gt;&lt;script&gt;alert(1)" in textarea(h)


def test_share_params_do_not_override_existing_views(server):
    for path, marker in (("/?view=ledger&text=hello", "Search the ledger"), ("/?view=privacy&text=hello", "Privacy policy"),
                         ("/?view=manifest&text=hello", '"short_name"')):
        code, hdr, body = get(server, path)
        assert code == 200 and marker in body.decode()
        assert textarea_missing_or_empty(body.decode())              # shared text was ignored: the view kept its meaning
    code, hdr, body = get(server, "/?go=tip&text=hello")
    assert b"hello" not in body and "no-store" in hdr["Cache-Control"]    # tip route (404 or redirect) wins; never a prefilled home page


def textarea_missing_or_empty(h):
    m = re.search(r'<textarea[^>]*id="text"[^>]*>(.*?)</textarea>', h, re.S)
    return m is None or m.group(1) == ""


def test_plain_home_and_empty_share_params_unchanged(server):
    for path in ("/", "/?text=", "/?text=%20%20&title=&url=", "/?t=1", "/?lang=hi"):
        code, hdr, body = get(server, path)
        assert code == 200 and textarea_missing_or_empty(body.decode()) and "no-store" not in hdr["Cache-Control"]


def test_share_text_unit():
    assert pwa.share_text({}, 100) == ""
    assert pwa.share_text({"text": ["  hi  "]}, 100) == "hi"
    assert pwa.share_text({"text": ["x" * 50]}, 10) == "x" * 10
    assert pwa.share_text({"text": ["a\r\nb\rc"]}, 100) == "a\nb\nc"


# ------------------------------------------------------------------ history and install

def test_home_has_history_panel_and_install_bar(server):
    h = get(server, "/")[2].decode()
    for needle in ('<details class="mychecks" id="mychecks" hidden>', "My checks", 'id="mychecks-clear"', "Clear history",
                   "Saved only on this device, in your browser. Sach's servers never see this list.", 'id="pwa-install"', 'hidden><span id="pwa-msg">'):
        assert needle in h, needle
    assert h.count('class="chip"') == 5


def test_history_script_never_uses_innerhtml_and_uses_textcontent():
    js = pwa.JS
    assert "innerHTML" not in js and "outerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js
    assert "cl.textContent=h.claim" in js and "tag.textContent=h.verdict" in js and "ta.value=h.claim" in js
    assert "slice(0,139)" in js and "MAX=20" in js and "sach-history-v1" in js
    assert "confirm('Clear all saved checks on this device?')" in js


def test_every_storage_call_is_inside_try_catch():
    js = pwa.JS
    for m in re.finditer(r"localStorage\.", js):
        before = js[:m.start()]
        assert before.rfind("try{") > before.rfind("catch(e){") or before.rfind("try{") > before.rfind("}catch"), js[max(0, m.start() - 80):m.start() + 40]
    assert js.count("try{") >= js.count("localStorage.")
    assert "sessionStorage" not in js and "indexedDB" not in js


def test_install_prompt_is_feature_detected_and_never_when_standalone():
    js = pwa.JS
    assert "display-mode: standalone" in js and "navigator.standalone===true" in js
    assert "beforeinstallprompt" in js and "e.preventDefault();deferred=e" in js and "if(standalone)return;" in js
    assert "To install: tap Share, then Add to Home Screen." in js
    assert "if(shown||dismissed())return;" in js                      # at most once per visit, and not after dismissal
    assert "sach-install-dismissed" in js and "iPad|iPhone|iPod" in js and "if(!bar)return;" in js


def test_history_hostile_claim_is_inert_in_page_html(server):
    """Claim text is only ever rendered client-side with textContent; the server page contains no history data at all."""
    code, h = _post(server, "<img src=x onerror=alert(1)> Government will give Rs 5000 to every woman.")
    assert code == 200 and "<img src=x" not in h and "sach-history" in h and 'id="mychecks"' in h


def test_privacy_page_mentions_on_device_history(server):
    h = get(server, "/?view=privacy")[2].decode()
    assert "On your device only" in h and "My checks" in h and "service worker" in h


def test_icon_rendering_is_deterministic_and_cached():
    assert pwa.icon_png(192) is pwa.icon_png(192)
    assert pwa.icon_png(192, True) != pwa.icon_png(192, False)


# ------------------------------------------------------------------ service worker behaviour (executed in Node with a mocked Cache API)
import shutil, subprocess, pathlib

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_service_worker_behaviour_in_node():
    harness = pathlib.Path(__file__).with_name("sw_harness.js")
    r = subprocess.run(["node", str(harness)], input=pwa.SW_JS, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "SW_OK" in r.stdout, r.stdout + r.stderr
