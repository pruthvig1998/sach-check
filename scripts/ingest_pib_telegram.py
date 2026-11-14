"""Read PIB Fact Check's PUBLIC Telegram channel (https://t.me/s/PIB_FactCheck, the page Telegram serves to anyone) and append the debunk posts that
pass sach.pibposts.judge_telegram to data/pib_posts.jsonl. Polite: one request every two seconds, an honest User-Agent, a few pages at a time.
Nothing is typed by hand; every record is parsed from a fetched post and judged by the same rules as the X posts.
Usage: python scripts/ingest_pib_telegram.py [--pages 3] [--dry-run]"""
import argparse, html, json, os, pathlib, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
from sach import pibposts

URL = "https://t.me/s/" + pibposts.TG_CHANNEL
UA = "SachFactCheckBot/1.0 (+https://sachcheck.in; reads one public channel, 1 request every 2 seconds)"
IST = timezone(timedelta(hours=5, minutes=30))
_POST = re.compile(r'data-post="' + pibposts.TG_CHANNEL + r'/(\d+)"')

def parse(page: str) -> list[dict]:
    """-> [{id, text, date_iso}] from one page of the Telegram web preview. Posts with no text or date are skipped."""
    out, marks = [], list(_POST.finditer(page))
    for i, m in enumerate(marks):
        block = page[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(page)]
        t = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        d = re.search(r'<time[^>]*datetime="([^"]+)"', block)
        if not (t and d):
            continue
        body = re.sub(r"<br\s*/?>", "\n", t.group(1))
        body = html.unescape(re.sub(r"<[^>]+>", " ", body))
        body = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in body.split("\n")).strip()
        try:
            day = datetime.fromisoformat(d.group(1)).astimezone(IST).date().isoformat()
        except ValueError:
            continue
        out.append({"id": m.group(1), "text": body, "date_iso": day,
                    "forwarded": "tgme_widget_message_forwarded_from" in block, "reply": "tgme_widget_message_reply" in block})
    return out

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2, help="pages of ~20 posts, newest first (max 20)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-file", default="", help="parse a saved copy of a channel page instead of fetching (one page only)")
    a = ap.parse_args()
    have = {str(r["id"]) for r in pibposts.load()}
    claims_have = {" ".join(r["claim"].lower().split()) for r in pibposts.load()}
    new, seen, url = [], 0, URL
    pages = max(1, min(a.pages, 20))
    for page_no in range(pages):
        try:
            posts = parse(open(a.from_file, encoding="utf-8", errors="replace").read() if a.from_file else fetch(url)); seen += len(posts)
        except Exception as e:                           # a reset or a block: stop politely, keep what was read, never retry in a loop
            print("stopped after a fetch error:", type(e).__name__); break
        if not posts:
            break
        for p in posts:
            rec, why = pibposts.judge_telegram(p["id"], p["text"], p["date_iso"], p.get("forwarded", False), p.get("reply", False))
            if rec is None or rec["id"] in have:
                continue
            if " ".join(rec["claim"].lower().split()) in claims_have:
                continue                                  # the same debunk is already stored (for example from X)
            rec["fetched"] = datetime.now(IST).date().isoformat()
            new.append(rec); have.add(rec["id"]); claims_have.add(" ".join(rec["claim"].lower().split()))
        if a.from_file:
            break
        url = URL + "?before=" + str(min(int(p["id"]) for p in posts))
        if page_no < pages - 1:
            time.sleep(2.0)
    print(f"read {seen} posts; {len(new)} new debunk records accepted")
    for r in new:
        print("  +", r["date"], r["verdict"], r["claim"][:90])
    if new and not a.dry_run:
        with open(pibposts.POSTS_PATH, "a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("appended to", pibposts.POSTS_PATH)

if __name__ == "__main__":
    main()
