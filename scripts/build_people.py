"""Build data/people.json from the researched people map (sach-people.csv, 19 Nov 2026).

  python3 scripts/build_people.py path/to/sach-people.csv

What goes in (read by sach/news.py, social signal only; never evidence, never a verdict):
  own       "platform:handle" -> person, for public figures' own accounts on X, Instagram and Facebook (the platforms the social search
            covers). Shown as "the person's own account" only when the claim names that person.
  impostor  "platform:handle" -> person, for accounts a fact-checker, a news organisation, a government page or a court named as fake.
Only strong evidence counts: a verified badge, or a verified_from page on a government site, a fact-checker, a listed news organisation,
a court record, or the person's own website. About a third of the sheet cites fan sites, aggregators or Wikipedia; those rows stay out.
Also out: inactive accounts, accounts of people who have died (a post there is not the person speaking), and rows without a usable URL."""
from __future__ import annotations
import csv, json, os, re, sys
from collections import defaultdict
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SACH_NEWS_SOURCES"] = "0"      # judge evidence against the hand-written outlet list only, as build_news_sources.py does
from sach.fetch import is_official, is_factchecker, _under      # noqa: E402
from sach import news                                              # noqa: E402

OUT = os.path.join(ROOT, "data", "people.json")
PLATFORM = {"x": ("x.com", "twitter.com"), "instagram": ("instagram.com",), "facebook": ("facebook.com",)}
FACT_CHECKERS = ("altnews.in", "boomlive.in", "vishvasnews.com", "newschecker.in", "factly.in", "newsmobile.in", "factcrescendo.com")
COURTS = ("indiankanoon.org", "sci.gov.in", "ecourts.gov.in")
_HANDLE = re.compile(r"[a-z0-9_.]{2,50}")


def host(u: str) -> str:
    h = (urlparse((u or "").strip()).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def key(r: dict) -> str:
    """'x:handle' from the row's URL, or '' when the URL is not a profile on a covered platform."""
    plat = r["platform"].strip().lower()
    if plat not in PLATFORM or not any(_under(host(r["url"]), d) for d in PLATFORM[plat]):
        return ""
    seg = [s for s in urlparse(r["url"].strip()).path.split("/") if s]
    h = seg[0].lower().lstrip("@") if seg else ""
    ok = _HANDLE.fullmatch(h) and h not in news._SKIP and h not in ("profile.php", "pages", "people", "groups", "watch")
    return f"{plat}:{h}" if ok else ""


def strong(r: dict, own_sites: set) -> bool:
    if r["verified_badge"].strip().lower() == "yes" and r["account_type"] == "official":
        return True
    m = re.search(r"https?://\S+", r["verified_from"])
    if not m:
        return False
    src = m.group(0).rstrip(").,;'\"")
    h = host(src)
    return bool(h) and (is_official(src) or is_factchecker(src) or bool(news.group_of(src)) or any(_under(h, d) for d in FACT_CHECKERS + COURTS)
                        or any(_under(h, d) for d in own_sites))


def build(rows: list) -> dict:
    sites = defaultdict(set)
    for r in rows:
        if r["account_type"] == "official" and r["platform"].strip().lower() == "website" and host(r["url"]):
            sites[r["person"].strip()].add(host(r["url"]))
    own, fake = {}, {}
    for r in rows:
        k, person = key(r), r["person"].strip()
        if not k or not person or not strong(r, sites[person]):
            continue
        if r["account_type"] == "impostor":
            # a handle that is just the person's name may have been taken over by the real person since the report (Alia Bhatt, 2014 -> 2020)
            if k.split(":", 1)[1].replace("_", "").replace(".", "") != re.sub(r"[^a-z0-9]", "", person.lower()):
                fake.setdefault(k, person)
        elif r["account_type"] == "official" and r["active"].strip().lower() != "no" and not r["deceased_date"].strip():
            own.setdefault(k, person)
    for k in set(own) & set(fake):          # named both ways: trust neither
        del own[k], fake[k]
    return {"source": "sach-people.csv (researched 19 Nov 2026); strong-evidence rows only",
            "own": dict(sorted(own.items())), "impostor": dict(sorted(fake.items()))}


if __name__ == "__main__":
    with open(sys.argv[1], newline="", encoding="utf-8") as f:
        data = build(list(csv.DictReader(f)))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
        f.write("\n")
    print(f"{len(data['own'])} own accounts, {len(data['impostor'])} impostor accounts -> {OUT}")
