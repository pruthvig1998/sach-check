#!/usr/bin/env python3
"""Freeze the live impact numbers into evidence/impact-<date>.json.

    python scripts/snapshot_impact.py                      # fetch from production
    python scripts/snapshot_impact.py --url http://127.0.0.1:8080
    python scripts/snapshot_impact.py --from-local         # compute in-process, no network

The file holds the payload exactly as the server returned it plus a `snapshot` block with where/when it was
fetched, the git commit, and a sha256 of the canonical payload JSON. Machine-generated: never edit by hand.
It will not overwrite an existing snapshot without --force."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, sys, urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_URL = "https://sach-check-lilac.vercel.app"
UA = "Sach-check-snapshot/0.1 (open-source fact-check; evidence snapshot script)"
TIMEOUT = 30
EXPECTED_KEYS = ("generated_at", "counting_since", "storage", "checks_total", "checks_served_fresh", "cache_hits",
                 "verdicts", "languages", "ledger", "evaluation", "sources_policy", "how")
OPENER = urllib.request.urlopen          # replaced in tests


def canonical(payload) -> bytes:
    """The exact bytes the sha256 is taken over. Verify with the recipe in evidence/README.md."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_of(payload) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def validate(payload) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload is not a JSON object")
    missing = [k for k in EXPECTED_KEYS if k not in payload]
    if missing:
        raise ValueError("payload is missing keys: " + ", ".join(missing))


def fetch_payload(base: str) -> tuple[dict, str]:
    url = base.rstrip("/") + "/?view=impact&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with OPENER(req, timeout=TIMEOUT) as r:
        status = getattr(r, "status", 200)
        raw = r.read().decode("utf-8")
    if status != 200:
        raise ValueError("server answered HTTP %s" % status)
    try:
        payload = json.loads(raw)
    except ValueError as e:
        raise ValueError("server did not return valid JSON (%s)" % e)
    return payload, url


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip() or None
    except Exception:
        return None


def build_snapshot(payload: dict, fetched_from: str) -> dict:
    return {"snapshot": {"fetched_from": fetched_from,
                         "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "git_commit": git_commit(),
                         "sha256": sha256_of(payload)},
            "payload": payload}


def main(argv=None, out_dir: pathlib.Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=DEFAULT_URL, help="base URL of the deployed site (default: %(default)s)")
    ap.add_argument("--date", help="YYYY-MM-DD for the file name (default: today, UTC)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing snapshot")
    ap.add_argument("--from-local", action="store_true", help="compute the payload in-process instead of fetching it")
    ap.add_argument("--out-dir", help="directory to write to (default: evidence/)")
    a = ap.parse_args(argv)
    date = a.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        print("error: --date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    d = pathlib.Path(a.out_dir) if a.out_dir else (out_dir or ROOT / "evidence")
    target = d / ("impact-%s.json" % date)
    if target.exists() and not a.force:
        print("error: %s already exists; snapshots are frozen. Use --force to replace it." % target, file=sys.stderr)
        return 1
    try:
        if a.from_local:
            from sach.impact import impact_data
            payload, src = json.loads(json.dumps(impact_data(), ensure_ascii=False)), "local (in-process impact_data())"
        else:
            payload, src = fetch_payload(a.url)
        validate(payload)
    except Exception as e:
        print("error: %s; nothing written" % e, file=sys.stderr)
        return 1
    snap = build_snapshot(payload, src)
    d.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    p = payload
    print("wrote %s" % target)
    print("  from %s at %s" % (src, snap["snapshot"]["fetched_at"]))
    print("  storage=%s counting_since=%s checks=%s cache_hits=%s ledger_rows=%s" % (
        p.get("storage"), p.get("counting_since"), p.get("checks_total"), p.get("cache_hits"), (p.get("ledger") or {}).get("rows")))
    print("  git_commit=%s" % snap["snapshot"]["git_commit"])
    print("  sha256=%s" % snap["snapshot"]["sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
