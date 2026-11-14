"""L1: PIB Fact Check's public Telegram channel as a source of debunk posts for the match layer. Offline: a small fabricated page, no network."""
import importlib.util, json, pathlib
import pytest
from sach import match, pibposts

_spec = importlib.util.spec_from_file_location("ingest_pib_telegram", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "ingest_pib_telegram.py")
ing = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ing)

PAGE = '''<div class="tgme_widget_message_wrap" data-post="PIB_FactCheck/2024"><div class="tgme_widget_message_text js-message_text" dir="auto">
🚨 FAKE ₹1,000 NOTE ALERT!<br/><br/>Several social media posts claim that a new ₹1,000 note has been issued.<br/><br/>#PIBFactCheck<br/><br/>❌ This claim is fake.<br/>✅ The RBI has made no announcement regarding the issuance of a new ₹1,000 note.</div>
<a class="tgme_widget_message_date"><time datetime="2026-10-27T09:00:00+00:00">x</time></a></div>
<div class="tgme_widget_message_wrap" data-post="PIB_FactCheck/2025"><div class="tgme_widget_message_text js-message_text">Let Truth Shine, Not Fake News. Pause. Verify. Then Click. #PIBFactCheck</div>
<a class="tgme_widget_message_date"><time datetime="2026-10-28T09:00:00+00:00">x</time></a></div>'''
GOOD = ("🚨 FAKE ₹1,000 NOTE ALERT!\n\nSeveral social media posts claim that a new ₹1,000 note has been issued.\n\n#PIBFactCheck\n\n"
        "❌ This claim is fake.\n✅ The RBI has made no announcement regarding the issuance of a new ₹1,000 note.")


def test_parse_reads_ids_text_and_ist_dates():
    posts = ing.parse(PAGE)
    assert [p["id"] for p in posts] == ["2024", "2025"] and posts[0]["date_iso"] == "2026-10-27"
    assert "Several social media posts claim" in posts[0]["text"] and "<" not in posts[0]["text"]


def test_a_real_debunk_is_accepted_and_awareness_posts_are_not():
    posts = ing.parse(PAGE)
    rec, why = pibposts.judge_telegram(posts[0]["id"], posts[0]["text"], posts[0]["date_iso"])
    assert rec and rec["source"] == "telegram" and rec["url"] == "https://t.me/PIB_FactCheck/2024" and rec["verdict"] == "FALSE" and pibposts.valid(rec)
    assert pibposts.judge_telegram(posts[1]["id"], posts[1]["text"], posts[1]["date_iso"])[0] is None      # general awareness post


@pytest.mark.parametrize("text,date,pid", [
    ("Several posts claim a new note has been issued by the central bank today.\n#PIBFactCheck", "2026-10-27", "5"),                          # no fake/false marker
    ("Several posts claim a new note has been issued by the central bank.\n#PIBFactCheck This claim is true and genuine.", "2026-10-27", "5"),  # confirms
    ("सोशल मीडिया पर प्रधानमंत्री से संबंधित दावे के साथ एक वीडियो प्रसारित किया जा रहा है।\n#PIBFactCheck ❌ यह दावा फर्जी है।", "2026-10-13", "6"),  # video, vague
    ("A viral video claims many things about the scheme.\n#PIBFactCheck This claim is fake.", "2026-10-27", "5"),                            # video
    ("Short claim here.\n#PIBFactCheck This is fake.", "2026-10-27", "5"),                                                                    # too short
    (GOOD, "2099-01-01", "5"), (GOOD, "not-a-date", "5"), (GOOD, "2026-10-27", "abc"), (GOOD.replace("#PIBFactCheck", ""), "2026-10-27", "5"),
])
def test_rejections(text, date, pid):
    assert pibposts.judge_telegram(pid, text, date)[0] is None


def test_valid_requires_the_matching_telegram_url():
    rec = pibposts.judge_telegram("2024", GOOD, "2026-10-27")[0]
    assert pibposts.valid(rec)
    assert not pibposts.valid({**rec, "id": "2025"})
    assert not pibposts.valid({**rec, "url": "https://x.com/PIBFactCheck/status/139140199296724583"})
    assert not pibposts.valid({**rec, "url": "https://t.me/someone_else/2024"})


def test_the_match_layer_labels_a_telegram_debunk_and_requires_near_identical_wording(tmp_path, monkeypatch):
    rec = {**pibposts.judge_telegram("2024", GOOD, "2026-10-27")[0], "fetched": "2026-11-14"}
    f = tmp_path / "posts.jsonl"; f.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(pibposts, "POSTS_PATH", str(f))
    rows = [r for r in match.load_pib_records() if r.get("post_id") == "2024"]
    assert rows and rows[0]["source"] == "telegram"
    hit = match._pib_candidates(["Several social media posts claim that a new 1,000 note has been issued."], rows)
    assert hit and hit[0]["checker"] == match.PIB_TG_NAME == "PIB Fact Check (on Telegram)" and hit[0]["source"] == "pib_tg_post"
    assert match.PIB_TG_NAME in match.PIB_NAMES
    assert not match._pib_candidates(["Several social media posts claim that a new 2,000 note has been issued."], rows)     # one figure differs
