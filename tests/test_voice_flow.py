"""Voice input, read-aloud and the fetch-based check flow: markup, progressive enhancement, string coverage and the pure speech helpers."""
import json
import re
import shutil
import subprocess
import urllib.request as _ur

import pytest

from sach import site, voice
from sach.i18n import LABEL
from tests.test_sach import _post, server  # noqa: F401  (server is a fixture)


def _card_result(lang="hi", card_en=True):
    claim = {"text": "Retirement age is cut", "domain": "scheme", "english": "Retirement age is cut"}
    cit = {"url": "https://pib.gov.in/x", "source": "PIB (Press Information Bureau)", "tier": "pib_debunk", "date_accessed": "2026-01-01"}
    res = {"verdict": "FALSE", "language": lang, "card": "❌ झूठ\nयह दावा झूठ है।\nस्रोत: PIB - https://pib.gov.in/x",
           "claims": [{"claim": claim, "verdict": "FALSE", "citations": [cit], "reason_code": "pib_debunk", "english": "x"}],
           "checked_at": "2026-01-01T00:00:00", "trace": {}}
    if card_en:
        res["card_en"] = "FALSE. This claim is false."
    return res


# ---- markup / progressive enhancement ----
def test_home_has_voice_hooks_and_new_script(server):
    h = _ur.urlopen(server + "/").read().decode()
    for needle in ('id="voicebox"', 'id="speak"', 'id="vlang"', 'id="vstatus"', 'role="status"', 'id="sprog"', 'id="pg-cancel"',
                   'id="results"', 'id="flowstatus"', "SpeechRecognition", "speechSynthesis", "AbortController", "DOMParser"):
        assert needle in h, needle
    # the speak box and progress panel are hidden by default, so with no JavaScript nothing new shows
    assert re.search(r'<div id="voicebox"[^>]*\bhidden\b', h) and re.search(r'<div id="sprog"[^>]*\bhidden\b', h)
    assert h.count("<script>") == 4 and "<script src" not in h   # app, voice, install/history and screenshot-upload scripts
    # the plain form is untouched: same method, action and field names
    assert '<form id="form" method="post" action="/#result">' in h and 'name="text"' in h and 'name="lang"' in h


def test_listen_buttons_on_result_card_hidden_until_script_runs():
    page = site.home(result=site.result_block(_card_result("hi"), chosen=True), prefill="x", reply="hi").decode()
    assert page.count('data-listen="card"') == 1 and 'data-listen="en"' in page and 'data-lang="hi"' in page
    assert all("hidden" in m for m in re.findall(r'<button class="btn ghost listen"[^>]*>', page))
    english = site.result_block(_card_result("en", card_en=False))
    assert 'data-listen="en"' not in english            # nothing to read in a second language
    assert 'data-listen="card"' in english


def test_normal_post_still_returns_full_page_with_result(server):
    st, body = _post(server, "Government will give Rs 5000 to every woman")
    assert st == 200 and 'id="result"' in body and '<div id="results">' in body and 'id="cardtext"' in body
    assert body.index('<div id="results">') < body.index('id="result"')       # result lives inside the swap container
    st, body = _post(server, "")
    assert st == 400 and 'role="alert"' in body and '<div id="results">' in body


def test_swap_container_wraps_errors_too():
    page = site.home(error="You're checking quickly <b>").decode()
    assert '<div id="results"><p role="alert"' in page and "&lt;b&gt;" in page


# ---- JS source hygiene ----
def test_voice_js_never_assigns_innerhtml_or_evals():
    js = voice.VOICE_JS
    assert not re.search(r"inner\s*HTML|outer\s*HTML|insertAdjacentHTML|document\.write|\beval\(|new Function", js)
    for ext in ("http://", "https://"):
        assert ext not in js.replace("__", "")           # no external scripts, CDNs or endpoints
    assert "</script" not in js.lower()


def test_voice_js_is_valid_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed, so the JS syntax check is skipped")
    r = subprocess.run([node, "--check", "-"], input=voice.VOICE_JS, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---- Hindi / Telugu strings ----
def test_every_hindi_and_telugu_string_is_present_and_marked():
    src = open(voice.__file__, encoding="utf-8").read()
    assert "NOT NATIVE-REVIEWED" in src
    assert src.index("NOT NATIVE-REVIEWED") < src.index("STRINGS = {")
    assert set(voice.STRINGS["hi"]) == set(voice.STRINGS["en"]) == set(voice.STRINGS["te"])
    for lang in ("hi", "te"):
        for k, v in voice.STRINGS[lang].items():
            assert v.strip(), (lang, k)
            assert json.dumps(v, ensure_ascii=False)[1:-1] in voice.VOICE_JS, (lang, k)
            assert v in src, (lang, k)
            assert v != voice.STRINGS["en"][k] or k == "x"
        assert re.search(r"[ऀ-ॿ]" if lang == "hi" else r"[ఀ-౿]", " ".join(voice.STRINGS[lang].values()))


def test_spec_wording_is_exact():
    en = voice.STRINGS["en"]
    assert en["typical"] == "Most checks take 10 to 30 seconds. A repeat of a message Sach has seen is instant."
    assert en["still"] == "Still working. Sach stops at about 50 seconds and says UNVERIFIED rather than guessing."
    assert en["voice_te"] == "This phone has no Telugu voice installed"
    for s in ("Splitting your message into claims", "Searching PIB and official sources", "Reading what each source actually says", "Applying the verdict rules"):
        assert s in en.values()
    assert en["result_ready"] == "Result ready"


def test_card_language_map():
    assert voice.CARD_BCP47 == {"en": "en-IN", "hi": "hi-IN", "te": "te-IN", "tl": "en-IN"}
    assert {v for v, _ in voice.SPEAK_LANGS} == {"en-IN", "hi-IN", "te-IN"}
    assert set(LABEL) >= set(voice.CARD_BCP47)


# ---- pure speech helpers (run in node when available) ----
NODE = shutil.which("node")


def _run(expr: str):
    prog = voice.SPEECH_JS + "\nconsole.log(JSON.stringify(" + expr + "))"
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node is not installed; the JS speech helpers cannot be executed here")
def test_speech_text_strips_urls_and_symbols():
    card = "❌ FALSE\nPIB says this is false. ✓✓\nSource: PIB (Press Information Bureau) - https://pib.gov.in/PressReleasePage.aspx?PRID=1&x=2 *bold* #tag"
    out = _run("buildSpeech(%s,[],'Sources')" % json.dumps(card))
    assert "http" not in out and "pib.gov.in" not in out and "PRID" not in out
    assert not re.search(r"[❌✓*#]", out)
    assert out.startswith("FALSE.") and "PIB says this is false." in out and "Source: PIB (Press Information Bureau)" in out


@pytest.mark.skipif(not NODE, reason="node is not installed; the JS speech helpers cannot be executed here")
def test_speech_text_keeps_indic_scripts_and_appends_missing_sources_once():
    hi = "❌ झूठ\nयह दावा झूठ है।"
    out = _run("buildSpeech(%s,['PIB','PIB','Ministry of Finance','www.example.com'],'स्रोत')" % json.dumps(hi))
    assert "झूठ" in out and "यह दावा झूठ है।" in out
    assert out.endswith("स्रोत: PIB, Ministry of Finance.") and out.count("PIB") == 1 and "example" not in out
    te = _run("speechClean(%s)" % json.dumps("✅ నిజం\nఇది నిజం. https://x.gov.in/a"))
    assert te.startswith("నిజం.") and "gov.in" not in te
    # a source already named in the card is not repeated
    dup = _run("buildSpeech('FALSE. PIB says so.',['PIB'],'Sources')")
    assert dup == "FALSE. PIB says so."


@pytest.mark.skipif(not NODE, reason="node is not installed; the JS speech helpers cannot be executed here")
def test_chunking_and_voice_picking():
    chunks = _run("chunkSpeech(%s,60)" % json.dumps("One short sentence. " * 8 + "x" * 150))
    assert len(chunks) > 3 and all(len(c) <= 60 for c in chunks)
    voices = "[{lang:'en_US',name:'a'},{lang:'hi_IN',name:'b'},{lang:'te-IN',name:'c'},{lang:'en-IN',name:'d'}]"
    assert _run("pickVoice(%s,'te-IN').name" % voices) == "c"
    assert _run("pickVoice(%s,'hi-IN').name" % voices) == "b"          # Android style hi_IN matches hi-IN
    assert _run("pickVoice(%s,'en-IN').name" % voices) == "d"
    assert _run("pickVoice([{lang:'en-US',name:'x'}],'te-IN')") is None  # no Telugu voice: never fall back to another language
