"""PAGEHONESTY: display-only honesty notes on the result page. Offline and deterministic: fake retrievers, fake LLMs, no network.
Every test that checks a condition also checks the neighbouring case, so results that do not meet the condition render as before."""
import json
from datetime import date

import pytest
from test_cache_trace import run, PIB, OFFICIAL, FALSE_TEXT, NoneLLM, CountingRetriever, FakeLLM
from sach import honesty, i18n, linkcheck, match, pipeline, site
from sach.extract import extract_claims
from sach.i18n import UNVERIFIED_PANEL
from sach.models import Claim, UNVERIFIED, TIER_FACTCHECKER
from sach.pipeline import check_forward
from sach.scamsigns import analyze as scam_signs
from sach.site import result_block

LONG = ("Government will give Rs 5000 to every woman. Good morning everyone friends. Click the link now to register. "
        "Pension money for widows is being doubled from next month. Ration card holders get free wheat this winter. "
        "Electricity bills will be zero for farmers in Bihar. Aadhaar will be linked to every bank account by Diwali. "
        "Bank loans for small shops get an interest subsidy this year.")          # 8 distinct sentences, 2 filtered, 6 claims -> 5 checked

class ReportingRetriever(CountingRetriever):
    """A retriever that reports search health, as the real web providers do (search_status 'ok')."""
    def search_with_status(self, q):
        run_ = type("SearchRun", (), {"status": "ok", "providers": ["fake"]})()
        return self.search(q), run_

def run_ok(text=FALSE_TEXT, ev=(PIB,), llm=None, **kw):
    kw.setdefault("log", False); kw.setdefault("use_cache", False)
    return check_forward(text, [ReportingRetriever(list(ev))], llm or FakeLLM(), **kw)

def unverified_out(**kw):
    return run_ok(FALSE_TEXT, ev=(OFFICIAL,), llm=NoneLLM(), **kw)

# ------------------------------------------------------------------ 1. What Sach checked (UNVERIFIED, live, complete)
def test_unverified_live_result_gets_the_panel_with_trace_counts():
    out = unverified_out()
    assert out["verdict"] == UNVERIFIED and out["layer"] == "live" and out["search_status"] == "ok" and not out.get("degraded")
    h = result_block(out)
    assert "What Sach checked" in h and "What UNVERIFIED means" in h and "What to do next" in h
    assert ("Not confirmed or denied by the official sources Sach could read. It does not mean probably true, "
            "and it does not mean probably false.") in h
    assert "Claims checked: 1" in h
    assert "Official pages judged that neither confirmed nor denied the claim: 1" in h     # the one official page, stance none, judged
    assert "PIB pages judged: 0" in h
    assert "PIB covers the Union Government; for a state-level matter ask that state&#x27;s department." in h
    assert "(#linkcheck)" in h                                                                    # the link checker is named

def test_panel_wording_has_no_score_or_percentage():
    h = result_block(unverified_out())
    panel = h[h.index("What Sach checked"):h.index("What Sach checked") + 1500]
    assert "%" not in panel and "confidence" not in panel.lower() and "score" not in panel.lower()

def test_panel_counts_only_answered_official_pages():
    out = unverified_out()
    srcs = out["claims"][0]["trace"]["sources"]
    assert srcs and srcs[0]["judged"]["outcome"] == "answered"
    srcs[0]["judged"]["outcome"] = "timeout"                                  # not judged: must not be counted
    assert "neither confirmed nor denied the claim: 0" in result_block(out)

def test_panel_hindi_and_telugu_use_their_own_text_and_fall_back_to_english():
    out = unverified_out()
    out["language"] = "hi"
    h = result_block(out)
    assert UNVERIFIED_PANEL["hi"]["title"] in h and UNVERIFIED_PANEL["hi"]["next"][:20] in h
    out["language"] = "te"
    assert UNVERIFIED_PANEL["te"]["title"] in result_block(out)
    out["language"] = "mni"                                                    # Manipuri has no table: English, as every other card
    assert "What Sach checked" in result_block(out)

@pytest.mark.parametrize("change", [
    lambda o: o.update(degraded=True),                  # limited mode: incomplete, not this panel
    lambda o: o.update(search_status="down"),           # search was down: incomplete
    lambda o: o.update(search_status="partial"),
    lambda o: o.update(verdict="FALSE"),                # not UNVERIFIED
    lambda o: o.update(layer="match"),
    lambda o: o.update(layer="mixed"),
    lambda o: o["claims"][0].update(reason_code="timed_out"),   # a claim ran out of time: incomplete
])
def test_panel_absent_when_the_check_is_incomplete_or_not_unverified(change):
    out = unverified_out()
    base = result_block(out)
    assert "What Sach checked" in base
    change(out)
    assert "What Sach checked" not in result_block(out)

def test_panel_absent_for_a_clear_verdict_and_for_no_claims():
    out, _ = run(log=False, use_cache=False)                                  # PIB debunk contradicts: FALSE
    assert out["verdict"] != UNVERIFIED and "What Sach checked" not in result_block(out)
    nc, _ = run("Good morning 🙏", ev=(), log=False, use_cache=False)
    assert nc.get("no_claims") and "What Sach checked" not in result_block(nc)

def test_panel_does_not_change_the_verdict():
    out = unverified_out()
    before = (out["verdict"], [c["verdict"] for c in out["claims"]], out["card"])
    result_block(out)
    assert (out["verdict"], [c["verdict"] for c in out["claims"]], out["card"]) == before

# ------------------------------------------------------------------ 2. old matched debunk and 'reviewed' label
def _match_cand(review_date):
    res = {"checks": {"number": True, "entity": True}, "similarity": {"jaccard": 0.9}}
    return match._cand("PIB Fact Check", "https://factcheck.pib.gov.in/", "https://factcheck.pib.gov.in/x", review_date, "Fake",
                       "Government will give Rs 5000 to every woman", "pib_archive", "fuzzy", "Government will give Rs 5000 to every woman", res)

def _matched_out(review_date, monkeypatch):
    cand = _match_cand(review_date)
    monkeypatch.setattr(match, "enabled", lambda: True)
    monkeypatch.setattr(match, "run_match", lambda claims, lang, llm, matcher=None, info=None: [(cand, "")] * len(claims))
    out, _ = run(log=False, use_cache=False)
    assert out["layer"] == "match" and out["claims"][0]["layer"] == "match"
    return out

def test_old_matched_debunk_gets_the_date_notice(monkeypatch):
    out = _matched_out("2020-03-05", monkeypatch)
    h = result_block(out)
    assert ("This is a debunk from Mar 2020. Rumours return: if the forward has new details, do not rely on it alone.") in h
    assert "reviewed 2020-03-05" in h and "accessed 2020-03-05" not in h             # date-only value stays date-only

def test_recent_matched_debunk_has_no_old_notice_but_still_says_reviewed(monkeypatch):
    out = _matched_out(date.today().isoformat(), monkeypatch)
    h = result_block(out)
    assert "This is a debunk from" not in h and "Rumours return" not in h
    assert "reviewed " + date.today().isoformat() in h

def test_old_notice_boundary_is_strictly_older_than_twelve_months():
    today = date(2026, 11, 13)
    def notice(d):
        return honesty.old_debunk_notice({"claims": [{"layer": "match", "match": {"review_date": d}}]}, today=today)
    assert notice("2025-11-13") == ""                 # exactly twelve months: not older than twelve months
    assert "This is a debunk from Nov 2025" in notice("2025-11-12")
    assert notice("2026-01-01") == ""
    assert notice("") == "" and notice("garbage") == ""

def test_live_citations_keep_the_accessed_label():
    out, _ = run(ev=(PIB,), log=False, use_cache=False)
    h = result_block(out)
    assert "accessed " in h and "reviewed " not in h
    assert out["claims"][0]["citations"][0]["date_accessed"] in h
    assert "date_accessed" in out["claims"][0]["citations"][0]              # stored key unchanged

def test_cite_word_only_changes_match_citations():
    assert honesty.cite_word({"layer": "match"}) == "reviewed"
    assert honesty.cite_word({"layer": "live"}) == "accessed" and honesty.cite_word({}) == "accessed"

# ------------------------------------------------------------------ 3. what was not checked
def test_extract_claims_is_identical_with_and_without_the_report():
    texts = [LONG, FALSE_TEXT, "Hello 👍", "Rs 5000 scheme. Share now. Good morning all friends.", "x " * 300, "",
             "Same sentence repeated here. Same sentence repeated here. Another different claim for the list."]
    for t in texts:
        plain = extract_claims(t, max_claims=5)
        rep = {}
        with_rep = extract_claims(t, max_claims=5, report=rep)
        assert [(c.text, c.domain) for c in plain] == [(c.text, c.domain) for c in with_rep]
        assert rep["sentences"] >= len(with_rep)
        assert len(rep["skipped"]) == rep["sentences"] - len(with_rep)

BANK = "Bank loans for small shops get an interest subsidy this year."

def test_report_lists_filtered_and_capped_sentences_in_order():
    rep = {}
    got = extract_claims(LONG, max_claims=5, report=rep)
    assert len(got) == 5 and rep["sentences"] == 8
    assert rep["skipped"] == ["Good morning everyone friends.", "Click the link now to register.", BANK]   # 2 filtered, 1 capped

def test_pipeline_verdicts_and_claims_are_unchanged_by_the_report(monkeypatch):
    with_report = run_ok(LONG, ev=(PIB,))
    orig = pipeline.extract_claims
    monkeypatch.setattr(pipeline, "extract_claims", lambda t, max_claims=8, report=None: orig(t, max_claims=max_claims))
    without = run_ok(LONG, ev=(PIB,))
    assert "extraction" in with_report and "extraction" not in without
    strip = lambda o: [(c["claim"]["text"], c["verdict"], c["reason_code"], c["citations"]) for c in o["claims"]]
    assert strip(with_report) == strip(without) and with_report["verdict"] == without["verdict"]
    assert with_report["card"] == without["card"] and with_report["trace"] == without["trace"]

def test_pipeline_records_checked_and_skipped_counts():
    out = run_ok(LONG, ev=(PIB,))
    ex = out["extraction"]
    assert ex == {"sentences": 8, "checked": 5, "skipped": ["Good morning everyone friends.", "Click the link now to register.", BANK]}

def test_skipped_sentence_is_truncated_to_120_characters():
    long_short = "Share this " + "y" * 150                                       # three words, over 120 characters: filtered as too short
    out, _ = run(FALSE_TEXT + " " + long_short, ev=(PIB,), llm=NoneLLM(), log=False, use_cache=False)
    skipped = out["extraction"]["skipped"]
    assert len(skipped) == 2 and skipped[1].endswith("...") and len(skipped[1]) == 120

def test_extraction_block_renders_only_when_something_was_not_checked():
    h = result_block(run_ok(LONG, ev=(PIB,)))
    assert "Checked 5 of 8 sentences" in h and "Not checked:" in h and "Good morning everyone friends." in h
    assert '<details class="extract"' in h and "and " not in h.split("Not checked:")[1].split("</details>")[0]   # all 3 skipped listed
    more = run_ok(LONG + " Ayushman cards now cover Rs 10 lakh per family. Gas cylinder prices are cut by half today.", ev=(PIB,))
    mh = result_block(more)
    assert "Checked 5 of 10 sentences" in mh and "and 2 more" in mh                     # 10 - 5 checked - 3 listed
    plain, _ = run("Government will give Rs 5000 to every woman.", ev=(PIB,), log=False, use_cache=False)
    assert plain["extraction"] == {"sentences": 1, "checked": 1, "skipped": []}
    assert '<details class="extract"' not in result_block(plain)
    fwd, _ = run(FALSE_TEXT, ev=(PIB,), log=False, use_cache=False)               # 'Please forward...' is skipped: shown
    assert "Checked 1 of 2 sentences" in result_block(fwd)

def test_cached_result_without_the_key_renders_as_before():
    out, _ = run(LONG, ev=(PIB,), log=False, use_cache=False)
    out.pop("extraction")
    assert '<details class="extract"' not in result_block(out) and "Not checked" not in result_block(out)

def test_skipped_text_is_escaped():
    h = honesty.extraction_html({"extraction": {"sentences": 6, "checked": 5, "skipped": ["<script>alert(1)</script> call now today"]}})
    assert "<script>" not in h and "&lt;script&gt;" in h

def test_extraction_html_ignores_bad_shapes():
    for bad in (None, "x", {}, {"sentences": "5", "checked": 2}, {"sentences": 2, "checked": 2, "skipped": []}):
        assert honesty.extraction_html({"extraction": bad} if bad is not None else {}) == ""

# ------------------------------------------------------------------ 4. scam-shaped no-claim
SCAM = "🎉🎉 Congratulations!!! 👉 http://bit.ly/prize123"

def _nc(text, signs=True):
    out, _ = run(text, ev=(), llm=NoneLLM(), log=False, use_cache=False)
    assert out["no_claims"] and out["verdict"] == UNVERIFIED
    if signs:
        out["warning_signs"] = scam_signs(text)
    return out

def test_scam_shaped_no_claim_leads_with_the_warning():
    out = _nc(SCAM)
    assert out["warning_signs"], "the fixture text must fire a scam sign"
    h = result_block(out)
    assert "No checkable fact here, but this looks like a scam pattern. Do not click links or share personal details." in h
    assert "Scam warning" in h and 'stamp big UNVERIFIED">No claim' not in h
    assert h.index("No checkable fact here") < h.index('class="signs"')           # above the signs
    assert out["verdict"] == UNVERIFIED and out["no_claims"] is True             # semantics unchanged

def test_no_claim_without_signs_is_exactly_as_before():
    out = _nc("Good morning 🙏", signs=False)
    h = result_block(out)
    assert '<div class="stamp big UNVERIFIED">No claim</div>' in h
    assert "looks like a scam pattern" not in h and "Scam warning" not in h

# ------------------------------------------------------------------ 5. visible truncation (page script)
NODE_PASTE = r"""
const vm = require('vm');
const JS = process.argv[1], raw = process.argv[2];
const input = JSON.parse(raw);
const els = {};
const mk = (tag) => ({ tag, id: '', className: '', value: '', maxLength: input.maxLength, textContent: '', hidden: false,
  dataset: {}, disabled: false, listeners: {},
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
  insertAdjacentElement(pos, el) { els.trunc = el; }, setAttribute() {}, focus() {}, scrollIntoView() {}, requestSubmit() {},
  classList: { add() {}, remove() {} } });
const ta = mk('textarea'); ta.value = input.value; ta.id = 'text';
const pb = mk('button'); pb.id = 'paste';
const cnt = mk('span'); cnt.id = 'count';
const byId = { '#text': ta, '#count': cnt, '#paste': pb };
const ctx = {
  document: { documentElement: { dataset: {} }, createElement: mk, querySelectorAll: () => [], addEventListener() {},
    querySelector: (s) => (s === '#trunc' ? (els.trunc || null) : (byId[s] || null)) },
  navigator: { clipboard: { readText: () => Promise.resolve(input.clip) } },
  console };
ctx.window = ctx; ctx.addEventListener = () => {};
vm.createContext(ctx);
vm.runInContext(JS, ctx);
(async () => {
  await pb.listeners.click[0]();
  const note = els.trunc || null;
  process.stdout.write(JSON.stringify({ length: ta.value.length, note: note ? note.textContent : null, hidden: note ? note.hidden : null }));
})();
"""

def _run_paste_button(value, clip, maxlen=4000):
    import json, shutil, subprocess, pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", NODE_PASTE, site.JS, json.dumps({"value": value, "clip": clip, "maxLength": maxlen})],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)

NOTE = "Only the first 4,000 characters will be checked."

def test_home_script_shows_the_truncation_note_on_paste_and_on_the_paste_button_path():
    h = site.home().decode()
    js = site.JS
    assert NOTE in js
    assert "addEventListener('paste'" in js and "e.inputType" in js
    assert 'maxlength="4000"' in h and "'trunc'" in js                              # the note element is created once, on demand
    assert js.count("readText") == 1                                                 # no new clipboard read: only the existing click handler
    # the paste button path, run for real under node with a mocked DOM
    over = _run_paste_button("", "x" * 4001)
    assert over["length"] == 4000 and over["note"] == NOTE and over["hidden"] is False
    exact = _run_paste_button("", "x" * 4000)
    assert exact["length"] == 4000 and (exact["note"] is None or exact["hidden"] is True)
    short = _run_paste_button("", "hello")
    assert short["length"] == 5 and (short["note"] is None or short["hidden"] is True)

def test_truncation_note_is_not_in_a_result_page():
    out, _ = run(log=False, use_cache=False)
    assert "Only the first 4,000" not in result_block(out)

# ------------------------------------------------------------------ 6. honesty and tone fixes
def test_no_human_written_claims_remain_in_the_code():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for rel in ("sach/site.py", "sach/i18n.py"):
        assert "human-written" not in (root / rel).read_text(encoding="utf-8")
    assert "AI-written and not yet reviewed by native speakers" in site.home().decode()
    assert "human-written" not in i18n.__doc__

def test_joke_tip_quip_is_not_on_result_pages(monkeypatch):
    monkeypatch.setattr(site, "tip_config", lambda: {"upi": "supporter@okbank"})
    out, _ = run(log=False, use_cache=False)
    assert out["verdict"] == "FALSE" and site.TIP_QUIPS["FALSE"] not in result_block(out)
    assert "softtip" not in result_block(out)

def test_cached_line_is_reworded_and_keeps_ist_date():
    out, _ = run(log=False, use_cache=False)
    out["cached"] = True
    out["first_checked_at"] = "2026-11-10T06:00:00+00:00"
    h = result_block(out)
    from sach import timefmt
    assert f"This result was checked before and is shown again; it was checked on {timefmt.fmt_ist('2026-11-10T06:00:00+00:00')}." in h
    assert "First checked on" not in h and "stored result" not in h

def test_link_panel_gets_the_reply_language():
    text = "Claim that the scheme pays Rs 5000 today. Visit http://bit.ly/xyz1 now to register."
    out, _ = run(text, ev=(OFFICIAL,), llm=NoneLLM(), log=False, use_cache=False)
    out["language"] = "hi"
    h = result_block(out, text=text)
    assert linkcheck.panel_html(text, "hi") in h
    if linkcheck.panel_html(text, "hi") != linkcheck.panel_html(text, "en"):
        assert linkcheck.panel_html(text, "en") not in h

def test_link_panel_english_result_unchanged():
    text = "Claim that the scheme pays Rs 5000 today. Visit http://bit.ly/xyz1 now to register."
    out, _ = run(text, ev=(OFFICIAL,), llm=NoneLLM(), log=False, use_cache=False)
    assert linkcheck.panel_html(text, "en") in result_block(out, text=text)

def test_panel_strings_have_every_key_in_each_language():
    for lang in ("hi", "te"):
        for key in UNVERIFIED_PANEL["en"]:
            assert key in UNVERIFIED_PANEL[lang]

# ------------------------------------------------------------------ 7. no-claim page: link panel language and the scam stamp
def test_no_claim_page_link_panel_gets_the_reply_language():
    text = "Good morning 🙏 Visit http://bit.ly/xyz1 now to register."
    out, _ = run(text, ev=(), llm=NoneLLM(), log=False, use_cache=False)
    assert out["no_claims"]
    out["language"] = "hi"
    h = result_block(out, text=text)
    assert linkcheck.panel_html(text, "hi") in h
    if linkcheck.panel_html(text, "hi") != linkcheck.panel_html(text, "en"):
        assert linkcheck.panel_html(text, "en") not in h
    out_en = dict(out, language="en")
    assert linkcheck.panel_html(text, "en") in result_block(out_en, text=text)

def test_scam_stamp_has_its_own_neutral_class_and_no_verdict_token():
    import re
    out = _nc(SCAM)
    h = result_block(out)
    stamp = re.search(r'<div class="([^"]*)">Scam warning</div>', h)
    assert stamp, "the scam stamp is rendered"
    tokens = stamp.group(1).split()
    assert "scamwarn" in tokens
    assert not set(tokens) & {"TRUE", "FALSE", "MISLEADING", "UNVERIFIED"}
    assert ".stamp.scamwarn{" in site.CSS
    rule = re.search(r"\.stamp\.scamwarn\{([^}]*)\}", site.CSS).group(1)
    assert "var(--ink)" in rule and "var(--mis)" not in rule                  # DEF-3: neutral ink, not the MISLEADING colour
    assert "MISLEADING" not in h.split('class="stamp')[1].split("</div>")[0]


# ------------------------------------------------------------------ DEF-3 / DEF-4 / UNVERIFIED wording
import re as _re

def _css_vars(block):
    return dict(_re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", block))

def _lum(hexc):
    rgb = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)

def _theme_vars():
    light = _css_vars(_re.search(r":root\{([^}]*)\}", site.CSS).group(1))
    dark = _css_vars(_re.search(r":root\[data-theme=dark\]\{([^}]*)\}", site.CSS).group(1))
    media = _css_vars(_re.search(r"@media\(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{([^}]*)\}", site.CSS).group(1))
    return {"light": light, "dark": dark, "media-dark": media}

def test_scam_stamp_is_neutral_ink_with_at_least_4_5_to_1_in_both_themes():
    rule = _re.search(r"\.stamp\.scamwarn\{([^}]*)\}", site.CSS).group(1)
    assert "var(--ink)" in rule and "3px solid var(--ink)" in rule and "opacity:1" in rule
    for verdict_var in ("--false", "--true", "--mis", "--unv"):
        assert f"var({verdict_var})" not in rule
    assert not _re.search(r"#[0-9a-fA-F]{6}", rule)
    for name, v in _theme_vars().items():
        for bg in ("paper", "card"):
            ratio = _ratio(v["ink"], v[bg])
            assert ratio >= 4.5, (name, bg, round(ratio, 2))

def test_scam_stamp_comment_in_honesty_matches_the_style():
    src = open(honesty.__file__, encoding="utf-8").read()
    line = next(l for l in src.splitlines() if "SCAM_STAMP =" in l)
    assert "never a verdict colour" not in line                       # the old claim was false: the class used var(--mis)
    assert "neutral" in line and "ink colour" in line

def test_unverified_panel_says_probably_only_in_the_negated_sentence():
    negated = {"en": "It does not mean probably true, and it does not mean probably false.",
               "hi": "इसका मतलब यह नहीं कि यह शायद सच है, और यह भी नहीं कि यह शायद झूठ है।",
               "te": "ఇది బహుశా నిజం అని కాదు, బహుశా అబద్ధం అని కూడా కాదు."}
    forbidden = {"en": ["probably", "likely"], "hi": ["शायद"], "te": ["బహుశా"]}
    for lang in ("en", "hi", "te"):
        assert negated[lang] in UNVERIFIED_PANEL[lang]["meaning"]
        for key, text in UNVERIFIED_PANEL[lang].items():
            if key == "meaning":
                text = text.replace(negated[lang], "")
            low = text.lower()
            for word in forbidden[lang] + (["likely"] if lang != "en" else []):
                assert word not in low, (lang, key, word)
    out = unverified_out()
    for lang in ("en", "hi", "te"):
        out["language"] = lang
        panel = honesty.unverified_panel(out)
        assert panel
        visible = _re.sub(r"<[^>]+>", " ", panel)
        assert visible.lower().count("probably") == (2 if lang == "en" else 0)
        assert visible.lower().count("likely") == 0

def test_no_claim_link_panel_summary_is_localised_in_hindi_and_telugu():
    text = "Good morning 🙏 Visit http://bit.ly/xyz1 now to register."
    en = linkcheck.panel_html(text, "en")
    assert "1 found" in en                                              # English output unchanged
    for lang in ("hi", "te"):
        h = linkcheck.panel_html(text, lang)
        assert h and "found" not in h.split("</summary>")[0]
        assert "{n}" in linkcheck.TEXT[lang]["found"]
        assert linkcheck.t("found", lang, n=1) != "1 found"
    out, _ = run(text, ev=(), llm=NoneLLM(), log=False, use_cache=False)
    out["language"] = "te"
    assert linkcheck.t("found", "te", n=1) in result_block(out, text=text)
