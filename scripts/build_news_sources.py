"""Build data/news_sources.json from the researched sources map (sach-sources.csv, 19 Nov 2026).

  python3 scripts/build_news_sources.py path/to/sach-sources.csv

What goes in (read by sach/news.py):
  domains  news websites (group B, not fact-checkers) -> owner. Adds outlets to the news tier, which never decides a verdict.
  by_lang  language code -> news websites that publish in it (in sheet order), used to add that language's outlets to the news query.
  handles  X / Instagram / Facebook / Threads handles of groups A and B -> account name. Used only to name established accounts in the
           social-signal count, which is never evidence.
What stays out: group C (influencers and celebrities: a watch-list, never a source), rows marked inactive, rows whose verified_from has no
URL or with a doubt noted by the researcher ("recheck", "inferred", only cited by others), government and fact-checker websites (they already have their own tiers), and platform or hosting domains.
Owner names: when a CSV owner already owns a domain in news.NEWS_GROUPS, the existing label is used, so one company is still counted once.
The hand-written NEWS_GROUPS and KNOWN_HANDLES in sach/news.py always win over this file."""
from __future__ import annotations
import csv, json, os, re, sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SACH_NEWS_SOURCES"] = "0"      # compare against the hand-written lists only, or a rebuild would drop every entry it made before
from sach.fetch import is_official, is_factchecker, _under          # noqa: E402
from sach import news                                                  # noqa: E402

OUT = os.path.join(ROOT, "data", "news_sources.json")
SOCIAL = {"x": ("x.com", "twitter.com"), "instagram": ("instagram.com",), "facebook": ("facebook.com",), "threads": ("threads.net", "threads.com")}
# Shared platforms and hosting: a page on these says nothing about who published it.
NOT_OWNED = ("youtube.com", "google.com", "blogspot.com", "wordpress.com", "medium.com", "substack.com", "wixsite.com", "github.io",
             "dailyhunt.in", "sharechat.com", "jio.com", "zee5.com", "hotstar.com", "sonyliv.com", "apple.com")
_HANDLE = re.compile(r"[a-z0-9_.]{2,50}")
LANG = {"Hindi": "hi", "Telugu": "te", "Bengali": "bn", "Assamese": "as", "Manipuri (Meitei)": "mni", "Marathi": "mr", "Konkani": "kok",
        "Nepali": "ne", "Tamil": "ta", "Gujarati": "gu", "Punjabi": "pa", "Odia": "or", "Kannada": "kn", "Malayalam": "ml", "Urdu": "ur"}
# One company under several names in the CSV, or under a different name than sach/news.py uses: counted once. (pattern, label)
ALIASES = ((r"\bTV9\b", "TV9 Network"), (r"Times Group|Bennett", "Times of India"), (r"\bETV\b|Eenadu|Ramoji", "Eenadu"),
           (r"Jagran", "Dainik Jagran"), (r"Republic", "Republic Media Network"), (r"Asianet", "Asianet News Network"))


def owner_of(raw: str, label: dict) -> str:
    raw = raw.strip()
    return label.get(raw) or next((g for p, g in ALIASES if re.search(p, raw)), raw)


def host(u: str) -> str:
    h = (urlparse(u.strip()).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def handle(u: str) -> str:
    seg = [s for s in urlparse(u.strip()).path.split("/") if s]
    h = seg[0].lower().lstrip("@") if seg else ""
    return h if _HANDLE.fullmatch(h) and h not in news._SKIP and h not in ("profile.php", "pages", "people") else ""


_DOUBT = re.compile(r"recheck|inferred|\bcite[sd]?\b", re.I)      # the researcher's own doubt: kept in the sheet, left out here


def usable(r: dict) -> bool:
    return (r["group"] in ("A", "B") and r["active"].strip().lower() != "no" and bool(re.search(r"https?://", r["verified_from"]))
            and not _DOUBT.search(r.get("notes", "")))


def build(rows: list) -> dict:
    rows = [r for r in rows if usable(r)]
    # CSV owner -> the label sach/news.py already uses for one of that owner's websites
    label = {}
    for r in rows:
        if r["platform"] == "website":
            g = news.group_of(r["url"])
            if g:
                label.setdefault(r["owner"].strip(), g)
    domains = {}
    for r in rows:
        if r["group"] != "B" or r["platform"] != "website" or r["category"] == "fact-checker":
            continue
        h = host(r["url"])
        u = "https://" + h + "/"
        if not h or "." not in h or news.group_of(u) or is_official(u) or is_factchecker(u) or any(_under(h, d) for d in NOT_OWNED):
            continue
        domains.setdefault(h, owner_of(r["owner"], label))
    by_lang = {}
    for r in rows:
        h = host(r["url"])
        if r["group"] == "B" and r["platform"] == "website" and r["category"] != "fact-checker" and (h in domains or news.group_of("https://" + h + "/")):
            for name in re.split(r"[;,/|]", r["language"]):
                code = LANG.get(name.strip())
                if code and not any(_under(h, d) or _under(d, h) for d in by_lang.setdefault(code, [])):     # site:etv.co.in covers ts.etv.co.in
                    by_lang[code].append(h)
    handles = {}
    for r in rows:
        dom = SOCIAL.get(r["platform"])
        if not dom or not any(_under(host(r["url"]), d) for d in dom):
            continue
        h = handle(r["url"])
        if h and h not in news.KNOWN_HANDLES:
            handles.setdefault(h, r["name"].strip())
    return {"source": "sach-sources.csv (researched 19 Nov 2026; every row verified from an official site, badge or government directory)",
            "domains": dict(sorted(domains.items())), "by_lang": dict(sorted(by_lang.items())), "handles": dict(sorted(handles.items()))}


if __name__ == "__main__":
    with open(sys.argv[1], newline="", encoding="utf-8") as f:
        data = build(list(csv.DictReader(f)))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
        f.write("\n")
    print(f"{len(data['domains'])} news domains, {len(data['handles'])} handles -> {OUT}")
