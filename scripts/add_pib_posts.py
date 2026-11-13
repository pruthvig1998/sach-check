#!/usr/bin/env python3
"""Add verified PIB Fact Check posts on X to data/pib_posts.jsonl.

  python scripts/add_pib_posts.py 2048690628415148453 https://x.com/PIBFactCheck/status/2047... --file ids.txt

Every record comes from a FETCHED post; nothing is typed by hand. Each status id is fetched from the fxtwitter reader
(https://api.fxtwitter.com/PIBFactCheck/status/<id>, a third-party service that mirrors public X posts, no login, no evasion) and
accepted only if sach.pibposts.judge() says so: author exactly PIBFactCheck, #PIBFactCheck plus FAKE/FALSE/MISLEADING/"not announced"/
"baseless", not a reply/quote/repost, not a TRUE or partly-true confirmation, a concrete text claim. Everything else is skipped with the
reason printed. The record's `url` is always the canonical https://x.com/PIBFactCheck/status/<id>, which is what Sach cites and links.

Polite: honest User-Agent, >= 1.1 s between requests, one request per id, no retries storm. Stdlib only. Needs network; tests use a fake opener.
"""
from __future__ import annotations
import argparse, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sach import pibposts

USER_AGENT = "Sach-factcheck-research (contact via sachcheck.in)"
API = "https://api.fxtwitter.com/PIBFactCheck/status/{id}"
MIN_GAP_S = 1.1
_ID = re.compile(r"(?:^|/status(?:es)?/)(\d{15,20})(?:\D|$)")


def parse_id(arg: str) -> str | None:
    """A bare status id, or an x.com/twitter.com URL ... /PIBFactCheck/status/<id>. Anything else (other accounts) -> None."""
    a = str(arg).strip()
    if re.fullmatch(r"\d{15,20}", a):
        return a
    m = re.match(r"https?://(?:www\.)?(?:x|twitter)\.com/PIBFactCheck/status(?:es)?/(\d{15,20})(?:[/?#]|$)", a)
    return m.group(1) if m else None


def urlopen_default(req, timeout=25):
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_tweet(status_id: str, opener=urlopen_default) -> tuple[dict | None, str]:
    """-> (tweet object, '') or (None, reason). Never raises."""
    req = urllib.request.Request(API.format(id=status_id), headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with opener(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                      # network, HTTP 404 (deleted), bad JSON: the id is simply skipped
        return None, f"fetch failed: {type(e).__name__} {str(e)[:60]}"
    if not isinstance(data, dict) or data.get("code") != 200 or not isinstance(data.get("tweet"), dict):
        return None, f"unexpected response (code {data.get('code') if isinstance(data, dict) else '?'})"
    if str(data["tweet"].get("id")) != status_id:
        return None, "returned a different status id"
    return data["tweet"], ""


def existing_ids(path: str) -> set:
    out = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                out.add(str(json.loads(line).get("id")))
            except ValueError:
                continue
    return out


def ingest(ids: list[str], path: str = pibposts.POSTS_PATH, opener=urlopen_default, sleep=time.sleep, now=None, log=print) -> dict:
    """Fetch, judge and append. -> {"accepted": [records], "rejected": [(id, reason)], "skipped": [ids already present]}."""
    have = existing_ids(path)
    families: dict = {}
    for r in pibposts.load(path):
        families.setdefault(pibposts.family_key(r["claim"]), []).append(r)
    out = {"accepted": [], "rejected": [], "skipped": []}
    first = True
    for sid in sorted(dict.fromkeys(ids), key=int):          # oldest first: the earliest posts are the family representatives
        if sid in have:
            out["skipped"].append(sid)
            continue
        if not first:
            sleep(MIN_GAP_S)
        first = False
        tweet, why = fetch_tweet(sid, opener)
        rec = None
        if tweet is not None:
            rec, why = pibposts.judge(tweet)
        if rec is None:
            out["rejected"].append((sid, why))
            log(f"SKIP {sid}: {why}")
            continue
        fam = pibposts.family_key(rec["claim"])
        nums = pibposts._nums(rec["claim"])
        kept = [(r["claim"]) for r in families.get(fam, [])]
        if len(kept) >= pibposts.FAMILY_MAX or any(pibposts._nums(k) == nums for k in kept):
            out["rejected"].append((sid, "near-duplicate of claims already kept (family cap or same numbers)"))
            log(f"SKIP {sid}: near-duplicate of claims already kept")
            continue
        families.setdefault(fam, []).append(rec)
        rec["fetched"] = (now or datetime.now(timezone.utc)).date().isoformat()
        rec = {k: rec[k] for k in ("id", "url", "date", "text", "claim", "verdict", "fetched", "kind")}
        out["accepted"].append(rec)
        have.add(sid)
        log(f"OK   {sid} {rec['date']} {rec['verdict']}: {rec['claim'][:90]}")
    if out["accepted"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for r in out["accepted"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="*", help="status ids or https://x.com/PIBFactCheck/status/<id> URLs")
    ap.add_argument("--file", help="text file with one id or URL per line (# comments allowed)")
    ap.add_argument("--out", default=pibposts.POSTS_PATH)
    a = ap.parse_args(argv)
    raw = list(a.ids)
    if a.file:
        raw += [l.split("#")[0].strip() for l in open(a.file, encoding="utf-8") if l.split("#")[0].strip()]
    ids = []
    for r in raw:
        i = parse_id(r)
        if i:
            ids.append(i)
        else:
            print(f"SKIP {r!r}: not a PIBFactCheck status id/URL")
    res = ingest(ids, a.out)
    print(f"accepted {len(res['accepted'])}, rejected {len(res['rejected'])}, already present {len(res['skipped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
