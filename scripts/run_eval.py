"""Score Sach over data/eval_set.json and write docs/evaluation.md (failures included).

Usage:
  python scripts/run_eval.py --dry-run            # validate the set, print the plan; no network, no LLM calls
  python scripts/run_eval.py                      # full run (needs LLM keys in .env; spends free-tier quota)
  python scripts/run_eval.py --resume             # continue with matching code, configuration and dataset
  python scripts/run_eval.py --offline            # key-free synthetic fixture check; writes a separate JSON artifact
  python scripts/run_eval.py --only-lang hi,te    # partial run -> docs/evaluation-partial-run.md only
  python scripts/run_eval.py --limit 5            # partial run

Only a full, non-degraded run may replace docs/evaluation.md and data/eval_summary.json.
See docs/evaluation-method.md."""
import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from importlib import metadata
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SACH_LEDGER", "data/eval_ledger.json")
os.environ["SACH_NO_CACHE"] = "1"    # the evaluation must never read or write the verdict cache (set before importing sach)
from sach import gateway, gtranslate, match, pipeline, vertex  # noqa: E402
from sach.excerpt import EXCERPT_CHARS        # noqa: E402
from sach.pipeline import check_forward      # noqa: E402
from sach.retrieve import default_retrievers  # noqa: E402
from sach.llm import LLM_MAX_CONCURRENT, get_llm  # noqa: E402
from sach.models import Evidence, RULE_TEXT, TIER_OFFICIAL, TIER_PIB  # noqa: E402
from sach.stance import heuristic_stance  # noqa: E402

EVAL_SET = ROOT / "data" / "eval_set.json"
RETRIEVAL_INPUTS = ("data/seed_debunks.json", "data/pib_index.jsonl", "data/pib_posts.jsonl")
SUMMARY = ROOT / "data" / "eval_summary.json"
DOCS = ROOT / "docs"
CHECKPOINT = ROOT / "cache" / "eval_progress.json"
SCHEMA_VERSION = 1
JUDGE_NAMES = {"vertex", "gemini", "groq", "gateway", "openrouter", "mistral", "cloudflare", "claude"}
MODEL_ID = re.compile(r"@?[a-zA-Z0-9][a-zA-Z0-9._/-]{0,126}(?::[a-zA-Z0-9._-]+)?\Z")
LABELS = ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED")
LANGS = ("en", "hi", "te", "hinglish", "tinglish",
         "bn", "mr", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as", "kok", "ne", "mni")   # forwards in 13 more Indian languages
FIELDS = ("claim", "label", "source", "lang", "seeded", "verified_on", "note")


# ---------- data ----------
def load_rows(path=None):
    with open(path or EVAL_SET, encoding="utf-8") as handle:
        return json.load(handle)


def validate_rows(rows):
    """Return a list of problems (empty if the set is well formed)."""
    errs, seen = [], set()
    for i, r in enumerate(rows):
        for f in FIELDS:
            if f not in r:
                errs.append(f"row {i}: missing {f}")
        if r.get("label") not in LABELS:
            errs.append(f"row {i}: bad label {r.get('label')!r}")
        if r.get("lang") not in LANGS:
            errs.append(f"row {i}: bad lang {r.get('lang')!r}")
        if not isinstance(r.get("seeded"), bool):
            errs.append(f"row {i}: seeded must be true/false")
        key = " ".join(str(r.get("claim", "")).lower().split())
        if key in seen:
            errs.append(f"row {i}: duplicate claim")
        seen.add(key)
    return errs


def fingerprint(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def eval_hash(rows):
    return fingerprint(rows)[:16]


def code_hash():
    """Hash actual runner/package contents, dependency manifests and local retrieval inputs."""
    paths = ["scripts/run_eval.py", "requirements.txt", "requirements-dev.txt", *RETRIEVAL_INPUTS]
    paths += [p.relative_to(ROOT).as_posix() for p in (ROOT / "sach").rglob("*.py")]
    files = {}
    for name in sorted(paths):
        path = ROOT / name
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return fingerprint(files)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_configuration(retrievers, llm, offline, workers):
    """Export typed settings, provider labels and model identifiers safe to disclose."""
    dependencies = {}
    for name in ("beautifulsoup4", "soupsieve", "anthropic"):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = None
    judges = getattr(llm, "judges", ()) or ([llm] if llm is not None else [])
    names = [getattr(judge, "name", "").split("-", 1)[0] for judge in judges]
    judge_names = [name if name in JUDGE_NAMES else ("fixture" if offline else "other") for name in names]
    models = [getattr(judge, "models", None) or [getattr(judge, "model", None)] for judge in judges]
    secrets = {
        value.strip() for key, setting in os.environ.items()
        if any(marker in key for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))
        for value in setting.split(",") if len(value.strip()) >= 4
    }
    model_ids = [
        [model if MODEL_ID.fullmatch(model) and not re.match(r"^(?:AIza|sk[-_]|gsk_|gh[pousr]_)", model)
         and not any(secret in model for secret in secrets) else "[redacted]"
         for model in items if isinstance(model, str)]
        for items in models
    ]
    config = {
        "python": ".".join(str(n) for n in sys.version_info[:3]),
        "dependencies": dependencies,
        "match_enabled": not offline and match.enabled(),
        "max_match_age_years": match.max_age_years(),
        "verdict_cache_enabled": False,
        "workers": workers,
        "ledger_logging": not offline and bool(os.environ.get("SACH_SEED_LEDGER")),
        "budget_seconds": pipeline.BUDGET_S,
        "judge_concurrency": LLM_MAX_CONCURRENT,
        "excerpt_chars": EXCERPT_CHARS,
        "retrievers": [type(r).__name__ for r in retrievers],
        "search_providers": [
            provider.name for r in retrievers for provider in getattr(getattr(r, "chain", None), "providers", ())
            if provider.name in ("brave", "tavily")
        ],
        "judges": judge_names,
        "judge_models": model_ids,
        "translate_enabled": not offline and gtranslate.enabled(),
        "translate_max_per_day": gtranslate.max_per_day(),
        "translate_max_per_min": gtranslate.max_per_min(),
        "gateway_max_per_day": gateway.max_per_day(),
        "vertex_max_per_day": vertex.max_per_day(),
    }
    return config, fingerprint({"config": config, "models": models})


def lang_counts(rows):
    out = {}
    for r in rows:
        out[r["lang"]] = out.get(r["lang"], 0) + 1
    return out


def git_info():
    """(commit hash or 'unknown', dirty flag). Dirty = uncommitted changes to tracked or untracked files."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip() or "unknown"
        st = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip()
        return commit, bool(st)
    except Exception:
        return "unknown", True


# ---------- scoring ----------
def outcome(r):
    """Classify a completed verdict or a system failure."""
    if r.get("status") in ("error", "degraded"):
        return "system_failure"
    got, label = r["got"], r["label"]
    if got == label:
        return "correct"
    if got == "UNVERIFIED":
        return "abstained"
    if got == "FALSE":
        return "overclaim_false"
    if got == "TRUE":
        return "overclaim_true"
    return "wrong_other"       # e.g. MISLEADING where the label was TRUE/FALSE/UNVERIFIED


def by_lang(res):
    """{lang: {n, correct, abstained, overclaimed_false, overclaimed_true, wrong_other}}; only languages present."""
    out = {}
    for r in res:
        d = out.setdefault(r["lang"], {"n": 0, "correct": 0, "abstained": 0, "overclaimed_false": 0, "overclaimed_true": 0, "wrong_other": 0})
        d["n"] += 1
        o = outcome(r)
        key = {"overclaim_false": "overclaimed_false", "overclaim_true": "overclaimed_true"}.get(o, o)
        d[key] = d.get(key, 0) + 1
        if o == "system_failure" and r["got"] in ("TRUE", "FALSE") and r["got"] != r["label"]:
            d["overclaimed_" + r["got"].lower()] += 1
    return out


def by_layer(res):
    """Count completed outcomes by layer."""
    out = {}
    for r in res:
        if outcome(r) == "system_failure":
            continue
        d = out.setdefault(r.get("layer", "live"), {"n": 0, "correct": 0, "abstained": 0, "overclaimed": 0})
        o = outcome(r)
        d["n"] += 1
        d["correct"] += o == "correct"
        d["abstained"] += o == "abstained"
        d["overclaimed"] += o in ("overclaim_false", "overclaim_true")
    return out


def summarize(res):
    o = [outcome(r) for r in res]
    overclaimed_false = sum(r["got"] == "FALSE" and r["label"] != "FALSE" for r in res)
    overclaimed_true = sum(r["got"] == "TRUE" and r["label"] != "TRUE" for r in res)
    return {"n": len(res), "correct": o.count("correct"), "overclaimed_false": overclaimed_false,
            "overclaimed_true": overclaimed_true, "abstained": o.count("abstained"),
            "abstained_wrong": overclaimed_false + overclaimed_true + o.count("wrong_other")}


def metrics(rows):
    """Rates use attempted rows, except missed abstention, which needs a decisive expected label."""
    scores = summarize(rows)
    n = scores["n"]
    failures = sum(outcome(row) == "system_failure" for row in rows)
    unverified = sum(outcome(row) != "system_failure" and row["got"] == "UNVERIFIED" for row in rows)
    decisive = sum(row["label"] != "UNVERIFIED" for row in rows)
    durations = sorted(row["latency_ms"] for row in rows if "latency_ms" in row)

    def rate(numerator, denominator=n):
        return {"numerator": numerator, "denominator": denominator}

    return {
        "accuracy": rate(scores["correct"]),
        "abstention": rate(unverified),
        "abstained_on_decisive": rate(scores["abstained"], decisive),
        "overclaimed_false": rate(scores["overclaimed_false"]),
        "overclaimed_true": rate(scores["overclaimed_true"]),
        "system_failure": rate(failures),
        "latency_ms": {
            "n": len(durations),
            "p50": durations[math.ceil(len(durations) * 0.50) - 1] if durations else None,
            "p95": durations[math.ceil(len(durations) * 0.95) - 1] if durations else None,
        },
    }


# ---------- checkpoint ----------
def new_checkpoint(key):
    return {"key": key, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}


def load_checkpoint(key):
    """Reuse only results with matching schema, code, config and dataset fingerprints."""
    try:
        with CHECKPOINT.open(encoding="utf-8") as handle:
            c = json.load(handle)
        if isinstance(c, dict) and c.get("key") == key and isinstance(c.get("results"), dict):
            return c
    except (OSError, ValueError):
        pass
    return new_checkpoint(key)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        tmp = pathlib.Path(handle.name)
        try:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def save_checkpoint(c):
    write_json(CHECKPOINT, c)


def evidence_id(url):
    """Canonical PIB identifiers or hashes, keeping arbitrary URL tokens out of exports."""
    if not isinstance(url, str) or not url:
        return None
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host == "pib.gov.in" or host.endswith(".pib.gov.in"):
            for key, values in parse_qs(parts.query).items():
                if key.lower() == "prid" and re.fullmatch(r"[0-9]{1,12}", values[0]):
                    return "pib:" + values[0]
    except ValueError:
        pass
    return "url-sha256:" + hashlib.sha256(url.split("#", 1)[0].encode("utf-8")).hexdigest()


def capture_result(res, llm, offline=False):
    got = res["verdict"]
    if got not in LABELS:
        return {"got": None, "status": "error", "error_category": "invalid_result"}
    layer = res.get("layer", "live")
    claims = res["claims"]
    reasons = [v["reason_code"] for v in claims if v["reason_code"] in RULE_TEXT]
    cited = [evidence_id(c["url"]) for v in claims for c in v["citations"]]
    sources = [evidence_id(e["url"]) for v in claims for e in v.get("trace", {}).get("sources", ())]
    search = res.get("search_status")
    if search not in ("ok", "partial", "down", "off"):
        search = "unknown"
    if layer == "match" or res.get("no_claims"):
        search = "not_applicable"
    elif offline:
        search = "offline_fixture"
    errors = []
    if "timed_out" in reasons:
        errors.append("check_timeout")
    if search in ("partial", "down", "off"):
        errors.append("search_" + search)
    if llm is None and layer != "match":
        errors.append("judge_unavailable")
    elif res.get("degraded") or res.get("judge_problems"):
        errors.append("judge_degraded")
    source_ids = list(dict.fromkeys(e for e in sources + cited if e))
    return {
        "got": got,
        "status": "degraded" if errors else "completed",
        "error_category": errors[0] if errors else None,
        "error_categories": errors,
        "abstention_category": (
            "no_checkable_claim" if res.get("no_claims")
            else next((r for r in reasons if r in ("no_evidence", "factchecker_only", "conflicting_official_sources")),
                      "unverified")
        ) if got == "UNVERIFIED" and not errors else None,
        "reasons": reasons,
        "evidence_ids": source_ids,
        "source_availability": {
            "search": search,
            "observed_source_records": len(source_ids),
            "cited": len(set(cited) - {None}),
            "page_availability": "unknown",
        },
        "layer": layer if layer in ("live", "match", "mixed") else None,
    }


# ---------- running ----------
def run(rows, ret, llm, ckpt, log=False, out=print, workers=1, persist=None, check=None, offline=False):
    """Check every row not already in the checkpoint; update + persist the checkpoint after each claim.
    Workers persist outcomes in completion order and return them in dataset order."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    ckpt["no_llm"] = bool(ckpt.get("no_llm")) or llm is None
    base = ckpt.get("llm_failures", 0)
    start_fail = getattr(llm, "failures", 0)
    lock = threading.Lock()
    n = len(rows)
    persist = persist if persist is not None else save_checkpoint
    check = check if check is not None else check_forward

    def one(i, r):
        started_at = utc_now()
        start = time.monotonic()
        try:
            result = capture_result(check(r["claim"], ret, llm, log=log), llm, offline=offline)
        except Exception as exc:
            category = "check_timeout" if isinstance(exc, TimeoutError) else "check_exception"
            result = {"got": None, "status": "error", "error_category": category}
        result.update(started_at=started_at, latency_ms=round((time.monotonic() - start) * 1000, 3))
        with lock:                                  # one writer at a time: the checkpoint file and the counters
            ckpt["results"][r["claim"]] = result
            ckpt["llm_failures"] = base + max(0, getattr(llm, "failures", 0) - start_fail)
            categories = result.get("error_categories", ())
            if any(category.startswith("search_") for category in categories):
                ckpt["search_failures"] = ckpt.get("search_failures", 0) + 1
            if "judge_degraded" in categories:
                ckpt["degraded_claims"] = ckpt.get("degraded_claims", 0) + 1
            persist(ckpt)
            out(f"[{i}/{n}] {r['label']:10} -> {result['got'] or result['error_category']}")

    todo = []
    for i, r in enumerate(rows, 1):
        if r["claim"] in ckpt["results"]:
            old = ckpt["results"][r["claim"]]
            out(f"[{i}/{n}] {r['label']:10} -> (resumed) {old['got'] or old.get('error_category')}")
        else:
            todo.append((i, r))
    if max(1, int(workers or 1)) == 1:
        for i, r in todo:
            one(i, r)
    else:
        with ThreadPoolExecutor(max_workers=int(workers)) as ex:
            for f in [ex.submit(one, i, r) for i, r in todo]:
                f.result()                          # checkpoint/output failures still fail the run
    return [{**r, **ckpt["results"][r["claim"]]} for r in rows if r["claim"] in ckpt["results"]]


# ---------- offline fixtures and artifacts ----------
OFFLINE_FIXTURES = (
    ("fixture-library-grant", "The Marigold library grant gives every resident 900 tokens.", "FALSE",
     TIER_PIB, "Fake: The Marigold library grant gives every resident 900 tokens."),
    ("fixture-library-opening", "The Juniper library opens on 12 May.", "TRUE",
     TIER_OFFICIAL, "The Juniper library opens on 12 May."),
    ("fixture-library-bonus", "The Lavender library gives readers a 500 token bonus.", "UNVERIFIED", None, ""),
)


def offline_rows():
    return [{
        "fixture_id": case_id, "claim": claim, "label": label,
        "source": f"https://fixtures.invalid/{case_id}" if tier else "",
        "lang": "en", "seeded": False, "verified_on": None, "note": "",
    } for case_id, claim, label, tier, _ in OFFLINE_FIXTURES]


class FixtureRetriever:
    def search(self, claim):
        for case_id, text, _, tier, title in OFFLINE_FIXTURES:
            if tier and claim.rstrip(".") == text.rstrip("."):
                return [Evidence("Offline fixture", f"https://fixtures.invalid/{case_id}", tier,
                                 "2000-01-01T00:00:00+00:00", title, title)]
        return []


class FixtureJudge:
    name = "fixture"

    def stance(self, claim, title, text, tier=""):
        return heuristic_stance(claim, title, text, tier)


def check_fixture(claim, retrievers, llm, log=False):
    return check_forward(claim, retrievers, llm, log=log, force_live=True)


def provenance(row):
    if row.get("fixture_id"):
        return "synthetic_fixture"
    if row["label"] == "UNVERIFIED":
        return "synthetic_control"
    if row.get("translated_from"):
        return "translated_claim"
    return "curated_claim"


def build_artifact(rows, key, config, dirty, partial, degraded, expected_rows):
    offline = key["mode"] == "offline_fixture"
    groups = {}
    entries = []
    for row in rows:
        origin = provenance(row)
        groups.setdefault(origin, []).append(row)
        translated_from = row.get("translated_from")
        availability = row.get("source_availability", {
            "search": "unknown", "observed_source_records": None, "cited": None, "page_availability": "unknown",
        })
        entries.append({
            "fixture_id": row.get("fixture_id") or fingerprint(row["claim"]),
            "provenance": origin,
            "translated_from_id": fingerprint(translated_from) if translated_from else None,
            "expected_source_id": evidence_id(row.get("source")) if origin != "synthetic_control" else None,
            "verified_on": row.get("verified_on"),
            "seeded": row["seeded"],
            "language": row["lang"],
            "expected_label": row["label"],
            "prediction": row["got"],
            "abstained": row["status"] == "completed" and row["got"] == "UNVERIFIED",
            "overclaim": row["got"] if row["got"] in ("TRUE", "FALSE") and row["got"] != row["label"] else None,
            "status": row["status"],
            "outcome": outcome(row),
            "abstention_category": row.get("abstention_category"),
            "error_category": row.get("error_category"),
            "error_categories": row.get("error_categories") or ([row["error_category"]] if row.get("error_category") else []),
            "reason_codes": row.get("reasons", []),
            "source_availability": availability,
            "evidence_ids": row.get("evidence_ids", []),
            "layer": row.get("layer"),
            "started_at": row["started_at"],
            "latency_ms": row["latency_ms"],
            "code_hash": key["code_hash"],
            "config_hash": key["config_hash"],
        })
    return {
        **key,
        "dataset": "offline_pipeline_fixtures" if offline else "data/eval_set.json",
        "generated_at": utc_now(),
        "dirty": dirty,
        "partial": bool(partial),
        "degraded": degraded,
        "complete": not partial and len(entries) == expected_rows,
        "expected_rows": expected_rows,
        "config": config,
        "metrics": metrics(rows),
        "metrics_by_provenance": {origin: metrics(group) for origin, group in groups.items()},
        "rows": entries,
    }


# ---------- report ----------
def _esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def history_files(docs=None):
    h = (docs or DOCS) / "evaluation-history"
    return sorted(p.name for p in h.glob("evaluation-*-superseded.md")) if h.is_dir() else []


def build_report(res, meta, degraded, partial, failed, docs=None):
    s = summarize(res); n = s["n"]
    m = metrics(res)
    bl = by_lang(res)
    title = "# Evaluation" + (" (partial run)" if partial else "") + (" (fallback mode)" if degraded else "")
    L = [title, ""]
    if partial:
        L += [f"> **This was a partial run ({partial}); it is not a measurement of the full set.** It is saved to `docs/evaluation-partial-run.md` and does not replace `docs/evaluation.md` or `data/eval_summary.json`.", ""]
    if degraded:
        L += ["> **This run was degraded; it does not measure the full system.** It is saved separately and does not replace `docs/evaluation.md`.", ""]
    L += [f"Measured on commit `{meta['commit']}`" + (" (working tree had uncommitted changes)" if meta["dirty"] else " (clean tree)") + f", {meta['date']} (UTC).", "",
          f"Mode: {meta['mode']}; retrieval: {', '.join(meta['retrievers'])}; judges: {', '.join(meta['judges']) or 'none'}.", "",
          f"- Claims: **{n}** (see limitations)", f"- Exact-match accuracy: **{s['correct']}/{n}**",
          f"- **Overclaimed FALSE: {s['overclaimed_false']}/{n}**",
          f"- **Overclaimed TRUE: {s['overclaimed_true']}/{n}**",
          f"- Abstention: {m['abstention']['numerator']}/{n}",
          f"- System failures: {m['system_failure']['numerator']}/{n}",
          f"- Latency in ms (p50/p95, {m['latency_ms']['n']} samples): {m['latency_ms']['p50']}/{m['latency_ms']['p95']}",
          f"- Wrong verdicts other than overclaims (e.g. MISLEADING where a TRUE/FALSE label stands): {s['abstained_wrong'] - s['overclaimed_false'] - s['overclaimed_true']}"]
    for l in ("FALSE", "TRUE", "UNVERIFIED"):
        g = [r for r in res if r["label"] == l]
        L.append(f"- Label {l}: {sum(outcome(r) == 'correct' for r in g)}/{len(g)} correct; {metrics(g)['abstention']['numerator']} abstained as UNVERIFIED")
    for tag, flag in (("Seeded (the source's PRID is in data/seed_debunks.json or data/pib_index.jsonl; retrieval is partly circular)", True),
                      ("Unseeded (retrieval had to find the page itself)", False)):
        g = [r for r in res if r["seeded"] == flag and r["label"] != "UNVERIFIED"]
        if g:
            L.append(f"- {tag}: {sum(outcome(r) == 'correct' for r in g)}/{len(g)} correct")
    bl_ = by_layer(res)
    L += ["", "## Which layer answered", "", "Completed checks by layer.", "",
          "| Layer | Claims | Exact match | Abstained | Overclaims |", "|---|---|---|---|---|"]
    for ly in [x for x in ("match", "mixed", "live") if x in bl_] + [x for x in bl_ if x not in ("match", "mixed", "live")]:
        d = bl_[ly]
        L.append(f"| {ly} | {d['n']} | {d['correct']} | {d['abstained']} | {d['overclaimed']} |")
    L += ["", ("The match layer was OFF for this run (`--no-match`): every row above went through the live layer alone." if meta.get("no_match") else
               "`match` rows were answered by an existing PIB or fact-checker verdict, not by Sach's own check. Eval claims are often paraphrases of "
               "published PIB debunks, so match accuracy on this set is circular; run with `--no-match` to measure the live layer alone."), ""]
    L += ["", "## By language", "", "| Language | n | Exact match | Abstained | Overclaimed FALSE | Overclaimed TRUE | System failures |",
          "|---|---|---|---|---|---|---|"]
    for lg in [x for x in LANGS if x in bl] + [x for x in bl if x not in LANGS]:
        d = bl[lg]
        L.append(f"| {lg} | {d['n']} | {d['correct']} | {d['abstained']} | {d['overclaimed_false']} | {d['overclaimed_true']} | {d.get('system_failure', 0)} |")
    L += ["", "Abstained = Sach said UNVERIFIED where the label was not UNVERIFIED (safe but a miss).", "",
          "## Every claim", "", "| Claim | Lang | Label | Sach | Result |", "|---|---|---|---|---|"]
    for r in res:
        o = outcome(r)
        tag = {"correct": "ok", "abstained": "miss (abstained)", "overclaim_false": "OVERCLAIM (FALSE)",
               "overclaim_true": "OVERCLAIM (TRUE)", "wrong_other": "WRONG", "system_failure": "SYSTEM FAILURE"}[o]
        L.append(f"| {_esc(r['claim'])} | {r['lang']} | {r['label']} | {r['got'] or '—'} | {tag} |")
    L += ["", "## Limitations (read before citing these numbers)",
          f"- The set is small ({n} claims here). Every non-control row was checked by fetching the cited official page and reading it; rows are not bulk-scraped. PIB has no listing page for debunks and its RSS feed returns only the latest 20 items, so a real 100+ set needs more manual work or a crawl. Rows added in the v2 revision carry the fetch date in `verified_on`; the original 31 rows were verified in the original build and were not re-fetched.",
          "- The Hindi, Telugu, Hinglish and Tinglish rows were written by an AI model and have not been reviewed by a native speaker. Real forwards are messier. Treat per-language numbers as a smoke test, not a measurement of how Sach does on real forwards in that language.",
          "- Per-language groups are tiny (a handful of rows each), so one claim moves a percentage a lot.",
          "- Rows marked `seeded` have their PIB page in the hand-seeded list or the harvested index, so retrieval for them is partly circular and their accuracy is optimistic. Many FALSE claims paraphrase PIB debunk titles for the same reason.",
          "- Relabel disclosure: the first control (\"free laptops to all students\") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.",
          "- Relabel disclosure 2: the RPF 4,208 Constable / 452 SI claim was first labelled FALSE (from PIB debunk 2009349), but that debunk was about a fake notice on one website; a genuine PIB release (PRID 2246142) lists those same vacancy numbers. Sach said TRUE; relabelled TRUE after inspecting the evidence. Two labels were changed after seeing results, so treat headline accuracy as indicative only.",
          "- Retrieval varies run to run (live search results change), so single-run numbers move by a claim or two. The evaluation runs with the verdict cache switched off (`SACH_NO_CACHE=1`).",
          "- Official-domain rule is *.gov.in / *.nic.in / who.int (plus a few listed hosts), so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.",
          "- There are no true MISLEADING rows: PIB items tagged \"misleading\" are labelled FALSE, so a MISLEADING verdict on them counts as a wrong verdict here."]
    if failed:
        L.append(f"- The LLM failed on {failed} source judgements during this run (quota/outage); those fell back to the safe PIB-debunk-only check.")
    hist = history_files(docs)
    L += ["", "## Previous runs", ""]
    L += [f"- [{h}](evaluation-history/{h})" for h in hist] or ["- None archived yet."]
    return "\n".join(L) + "\n"


def archive_previous(commit, docs=None):
    """Move the current docs/evaluation.md into docs/evaluation-history/ with a superseded banner. Returns the new path or None."""
    docs = docs or DOCS
    cur = docs / "evaluation.md"
    if not cur.exists():
        return None
    text = cur.read_text(encoding="utf-8")
    m = re.search(r"Measured on commit `[^`]*`[^\n]*?(\d{4}-\d{2}-\d{2})", text)
    tag = m.group(1) if m else "v1"
    hist = docs / "evaluation-history"
    hist.mkdir(parents=True, exist_ok=True)
    dest, k = hist / f"evaluation-{tag}-superseded.md", 2
    while dest.exists():
        dest = hist / f"evaluation-{tag}-{k}-superseded.md"; k += 1
    banner = f"> **Superseded** by the run measured on commit `{commit}`. Kept for the record; the current report is `docs/evaluation.md`.\n\n"
    dest.write_text(banner + text, encoding="utf-8")
    cur.unlink()
    return dest


# ---------- main ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--resume", action="store_true", help="skip claims already checkpointed for matching code, config and dataset")
    ap.add_argument("--only-lang", default="", help="comma list, e.g. hi,te (partial run)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N rows (partial run)")
    ap.add_argument("--no-match", action="store_true", help="switch the MATCH layer off (SACH_NO_MATCH=1) to measure the live layer alone; never replaces the headline files")
    ap.add_argument("--dry-run", action="store_true", help="validate and print the plan; no network calls")
    ap.add_argument("--offline", action="store_true", help="check local synthetic fixtures without keys or network")
    ap.add_argument("--workers", type=int, default=1, help="check this many claims at once (default 1 = sequential; 5 is about 4-5x faster and stays inside the AI-call and search limits)")
    a = ap.parse_args(argv)
    if a.workers < 1 or a.limit < 0:
        ap.error("--workers must be positive and --limit must be nonnegative")
    if a.offline and (a.resume or a.no_match or a.only_lang or a.limit):
        ap.error("--offline always runs its full fixture set with matching disabled")
    if a.no_match:
        with patch.dict(os.environ, {"SACH_NO_MATCH": "1"}):
            return run_evaluation(a)
    return run_evaluation(a)


def run_evaluation(a):
    rows = offline_rows() if a.offline else load_rows()
    errs = validate_rows(rows)
    if errs:
        print("eval set is invalid:\n  " + "\n  ".join(errs)); return 2
    langs = [x.strip() for x in a.only_lang.split(",") if x.strip()]
    bad = [x for x in langs if x not in LANGS]
    if bad:
        print(f"unknown language(s): {bad}; choose from {LANGS}"); return 2
    sel = [r for r in rows if not langs or r["lang"] in langs]
    if a.limit:
        sel = sel[:a.limit]
    partial = ", ".join(([f"languages {','.join(langs)}"] if langs else []) + ([f"first {a.limit} rows"] if a.limit else []))
    no_match = not match.enabled()
    no_match_run = no_match and not partial
    commit, dirty = git_info()
    artifact_path = ROOT / "cache" / ("evaluation-offline-fixture.json" if a.offline else "evaluation-live.json")
    if a.dry_run:
        lab = {}
        for r in sel:
            lab[r["label"]] = lab.get(r["label"], 0) + 1
        print(f"DRY RUN: no network or LLM calls. Eval set {len(rows)} rows (hash {eval_hash(rows)}); would check {len(sel)}.")
        print("by language:", dict(sorted(lang_counts(sel).items())))
        print("by label:   ", dict(sorted(lab.items())))
        if a.offline:
            print(f"commit {commit}; offline fixture artifact: {artifact_path}")
        else:
            print(f"commit {commit}{' (dirty)' if dirty else ''}; live artifact: {artifact_path}")
            print(f"resume checkpoint: {CHECKPOINT} ({'will be used if compatible' if a.resume else 'ignored; a fresh run overwrites it'})")
        return 0
    ret, llm = ([FixtureRetriever()], FixtureJudge()) if a.offline else (default_retrievers(), get_llm())
    config, config_hash = run_configuration(ret, llm, a.offline, a.workers)
    key = {
        "schema_version": SCHEMA_VERSION,
        "mode": "offline_fixture" if a.offline else "live",
        "commit": commit,
        "eval_hash": fingerprint(rows),
        "code_hash": code_hash(),
        "config_hash": config_hash,
    }
    ckpt = load_checkpoint(key) if a.resume else new_checkpoint(key)
    run_args = {"persist": lambda _: None, "check": check_fixture, "offline": True} if a.offline else {}
    res = run(sel, ret, llm, ckpt, log=config["ledger_logging"], workers=a.workers, **run_args)
    failed = ckpt.get("llm_failures", 0)
    sfailed = ckpt.get("search_failures", 0)
    dclaims = ckpt.get("degraded_claims", 0)
    failures = sum(outcome(r) == "system_failure" for r in res)
    degraded = ckpt["no_llm"] or failed > 0 or sfailed > 0 or dclaims > 0 or failures > 0
    artifact = build_artifact(res, key, config, dirty, partial, degraded, len(rows))
    write_json(artifact_path, artifact)
    print(f"wrote {artifact_path.relative_to(ROOT)}")
    if a.offline:
        correct = artifact["metrics"]["accuracy"]["numerator"]
        print(f"Offline synthetic fixture check: {correct}/{len(sel)} passed.")
        return 0 if correct == len(sel) and not degraded else 1
    if ckpt["no_llm"]:
        mode = "FALLBACK (no LLM key): clear PIB debunks only, never TRUE or MISLEADING"
    elif failed:
        mode = f"FALLBACK: the LLM failed on {failed} source judgements (quota/outage), so those sources fell back to the safe PIB-debunk-only check"
    else:
        mode = "LLM stance (with second-opinion consensus where more than one judge is configured)"
    if sfailed:
        mode = (mode if (ckpt["no_llm"] or failed) else "FALLBACK") + f"; web search failed for {sfailed} claims (disabled, out of credits or outage)"
    if dclaims:
        mode = (mode if (ckpt["no_llm"] or failed or sfailed) else "FALLBACK") + f"; an AI judge timed out or failed on {dclaims} claims (judge_problems), so their UNVERIFIED is not a real abstention"
    if failures:
        mode += f"; {failures} rows had a system failure"
    judges = config["judges"]
    meta = {"commit": commit, "dirty": dirty, "date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(), "mode": mode,
            "retrievers": config["retrievers"], "judges": judges, "no_match": no_match}
    report = build_report(res, meta, degraded, partial, failed)
    if partial:
        target = DOCS / "evaluation-partial-run.md"
    elif no_match_run:
        target = DOCS / "evaluation-no-match-run.md"     # live layer alone: a different measurement, never the headline
    elif degraded or not artifact["complete"]:
        target = DOCS / "evaluation-fallback-run.md"
    else:
        archive_previous(commit)
        report = build_report(res, meta, degraded, partial, failed)    # rebuilt so "Previous runs" lists the file just archived
        target = DOCS / "evaluation.md"
        write_json(SUMMARY, {
            **summarize(res), "commit": commit, "dirty": dirty, "date": meta["date"], "by_lang": by_lang(res),
            "eval_set_hash": eval_hash(rows), "retrievers": meta["retrievers"], "judges": judges,
            "schema_version": SCHEMA_VERSION, "mode": "live", "complete": True, "partial": False,
            "degraded": False, "no_match": False, "system_failures": 0,
        })
    target.write_text(report, encoding="utf-8")
    print("\n".join(report.split("\n")[:14]))
    print(f"\nwrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}"
          + ("  (headline files NOT touched)" if partial or degraded or no_match_run else ""))
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
