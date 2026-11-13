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
    """Verdict bucket: correct | abstained | overclaim_false | overclaim_true | wrong_other | error.
    An ERROR (the check raised, or returned no verdict) is always 'error': a failure, never correct, abstained or a wrong verdict.
    The bucket is about the verdict only. clean() decides whether a correct or abstained verdict also counts
    (it does not when the claim had a judge, search or check problem)."""
    if r.get("status") == "error":
        return "error"
    got, label = r["got"], r["label"]
    if got in ("ERROR", None):
        return "error"
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
    """{lang: {n, correct, abstained, overclaimed_false, overclaimed_true, wrong_other}}; only languages present.
    n counts every claim, ERRORs included; an ERROR is in none of the other buckets."""
    out = {}
    for r in res:
        d = out.setdefault(r["lang"], {"n": 0, "correct": 0, "abstained": 0, "overclaimed_false": 0, "overclaimed_true": 0, "wrong_other": 0})
        d["n"] += 1
        o = outcome(r)
        if o == "error":
            continue
        if o in ("correct", "abstained"):
            if clean(r):
                d[o] += 1
        elif o == "overclaim_false":
            d["overclaimed_false"] += 1
        elif o == "overclaim_true":
            d["overclaimed_true"] += 1
        else:
            d["wrong_other"] += 1
    return out


def by_layer(res):
    """Count completed outcomes by layer."""
    out = {}
    for r in res:
        d = out.setdefault(r.get("layer", "live"), {"n": 0, "correct": 0, "abstained": 0, "overclaimed": 0})
        o = outcome(r)
        d["n"] += 1
        d["correct"] += is_correct(r)
        d["abstained"] += is_abstained(r)
        d["overclaimed"] += o in ("overclaim_false", "overclaim_true")
    return out


def summarize(res):
    o = [outcome(r) for r in res]
    return {"n": len(res), "correct": sum(is_correct(r) for r in res), "overclaimed_false": o.count("overclaim_false"),
            "overclaimed_true": o.count("overclaim_true"), "abstained": sum(is_abstained(r) for r in res),
            "abstained_wrong": sum(x in ("overclaim_false", "overclaim_true", "wrong_other") for x in o)}
    # 'abstained_wrong' keeps its old name and meaning: overclaims + other wrong verdicts. ERRORs are not in it (outcome 'error').
    # Overclaims and wrong verdicts count whatever the claim's status (a degraded claim can still be wrong).
    # 'correct' and 'abstained' count only clean claims (see clean()).
    # The report's 'Wrong verdicts other than overclaims' line uses measures()['wrong_not_overclaim'] instead, which is the same count.


LAYER_ORDER = ("match", "mixed", "live", "error")
FAIL_SEARCH = ("down", "partial", "off")     # search lost, partial or switched off for a claim: the run is not a full run


def clean(r):
    """False when the claim had a judge problem, a search failure (or search off), or a check error status."""
    return not (r.get("status") == "degraded" or r.get("degraded") or r.get("search_status") in FAIL_SEARCH)


def is_correct(r):
    return outcome(r) == "correct" and clean(r)


def is_abstained(r):
    return outcome(r) == "abstained" and clean(r)


def system_failure(r):
    """An ERROR, or a claim that is not clean. Counted in the failure measures; never counted as correct or abstained."""
    return outcome(r) == "error" or not clean(r)


def percentile(sorted_vals, p):
    """Nearest-rank percentile of an ascending list: the value at rank ceil(p/100 * N). None for an empty list."""
    if not sorted_vals:
        return None
    k = math.ceil(p * len(sorted_vals) / 100)
    return sorted_vals[max(1, k) - 1]


def _lat_stats(ms):
    """Seconds: n, p50, p90, p95, max, mean (all None when there is no timing)."""
    s = sorted(ms)
    if not s:
        return {"n": 0, "p50_s": None, "p90_s": None, "p95_s": None, "max_s": None, "mean_s": None}
    return {"n": len(s), "p50_s": round(percentile(s, 50) / 1000, 3), "p90_s": round(percentile(s, 90) / 1000, 3),
            "p95_s": round(percentile(s, 95) / 1000, 3), "max_s": round(s[-1] / 1000, 3), "mean_s": round(sum(s) / len(s) / 1000, 3)}


def _layers_in(res):
    found = {r.get("layer", "live") for r in res}
    return [x for x in LAYER_ORDER if x in found] + sorted(x for x in found if x not in LAYER_ORDER)


def latency(res):
    """{all, untimed, by_layer} with the timing stats in seconds. Claims without an 'ms' (old checkpoints) are counted as untimed."""
    timed = [r for r in res if isinstance(r.get("ms"), (int, float))]
    return {"all": _lat_stats([r["ms"] for r in timed]), "untimed": len(res) - len(timed),
            "by_layer": {ly: _lat_stats([r["ms"] for r in timed if r.get("layer", "live") == ly]) for ly in _layers_in(timed)}}


def measures(res, failed=0):
    """The separate measures, with their denominators. Used by the report and by data/eval_summary.json ('measures')."""
    n = len(res)
    o = [outcome(r) for r in res]
    decisive = [r for r in res if r["label"] in ("TRUE", "FALSE")]
    deg = [r for r in res if r.get("degraded")]
    srch = [r for r in res if r.get("search_status") in FAIL_SEARCH]
    errs = [r for r in res if outcome(r) == "error"]
    anyf = [r for r in res if system_failure(r)]
    s = summarize(res)
    return {"n": n,
            "accuracy": {"correct": s["correct"], "n": n},
            "abstention": {"abstained_on_decisive": sum(is_abstained(r) and r["label"] in ("TRUE", "FALSE") for r in res),
                           "decisive_n": len(decisive)},
            "overclaim": {"false": s["overclaimed_false"], "true": s["overclaimed_true"], "n": n},
            "wrong_not_overclaim": {"count": o.count("wrong_other"), "n": n},
            "failures": {"claims_with_any_failure": len(anyf), "judge_problems_degraded": len(deg), "search_failures": len(srch),
                         "errors": len(errs), "llm_source_failures": failed},
            "latency": latency(res)}


def _pct(a, b):
    return f"{a * 100 / b:.1f}%" if b else "n/a"


def _claim_list(rs):
    return "\n".join(f"  - {_esc(r['claim'])} (label {r['label']}, got {r.get('got', '-')})" for r in rs) or "  - none"


def measures_section(res, failed=0):
    m = measures(res, failed)
    n, a, ab, of, ot = m["n"], m["accuracy"], m["abstention"], m["overclaim"], m["overclaim"]
    wr, f = m["wrong_not_overclaim"], m["failures"]
    deg = [r for r in res if r.get("degraded")]
    srch = [r for r in res if r.get("search_status") in FAIL_SEARCH]
    errs = [r for r in res if outcome(r) == "error"]
    anyf = [r for r in res if system_failure(r)]
    L = ["", "## Measures, separately", "",
         "Each measure has its own denominator. Read them separately; none is a score for the others.", "",
         "| Measure | Count | Denominator | Share |", "|---|---|---|---|",
         f"| Accuracy (exact match) | {a['correct']} | {n} claims | {_pct(a['correct'], n)} |",
         f"| Abstention rate (UNVERIFIED where the label is TRUE or FALSE) | {ab['abstained_on_decisive']} | {ab['decisive_n']} decisive-label claims | {_pct(ab['abstained_on_decisive'], ab['decisive_n'])} |",
         f"| Overclaim: FALSE (said FALSE, label was not) | {of['false']} | {n} claims | {_pct(of['false'], n)} |",
         f"| Overclaim: TRUE (said TRUE, label was not) | {ot['true']} | {n} claims | {_pct(ot['true'], n)} |",
         f"| Wrong but not an overclaim (e.g. MISLEADING; ERRORs excluded) | {wr['count']} | {n} claims | {_pct(wr['count'], n)} |",
         f"| Claims with any failure (see below) | {f['claims_with_any_failure']} | {n} claims | {_pct(f['claims_with_any_failure'], n)} |", "",
         "Accuracy counts abstentions (UNVERIFIED) and ERRORs as misses: an UNVERIFIED answer to a TRUE or FALSE claim is not an exact match, even though it is safe.", "",
         "### Failures", "",
         f"- Judge problem (a judge timed out or failed; the claim is degraded): **{len(deg)}**", _claim_list(deg), "",
         f"- Search failure (web search down or partial): **{len(srch)}**", _claim_list(srch), "",
         f"- ERROR (checking the claim raised an exception; counted as a failure, never as correct or abstained): **{len(errs)}**", _claim_list(errs), "",
         f"- Source judgements where the LLM failed (quota or outage), from the checkpoint: **{failed}**", "",
         f"Claims with at least one of the first three kinds of failure: **{len(anyf)}** of {n}. A claim can have more than one kind, so the three counts can add up to more than this."]
    return L


def latency_section(res):
    lat = latency(res)
    def row(name, s):
        cells = [s["n"]] + [("-" if s[k] is None else f"{s[k]:.2f}") for k in ("p50_s", "p90_s", "p95_s", "max_s", "mean_s")]
        return f"| {name} | " + " | ".join(str(c) for c in cells) + " |"
    L = ["", "## Latency (wall time per claim, seconds)", "",
         "Nearest-rank percentiles. Each claim's time covers its whole check, including search and judge calls. With `--workers` above 1, claims share the provider, so times include that load.", "",
         "| Group | Timed claims | p50 | p90 | p95 | max | mean |", "|---|---|---|---|---|---|---|",
         row("All claims", lat["all"])]
    L += [row(f"Layer: {ly}", s) for ly, s in lat["by_layer"].items()]
    L += ["", f"Claims without timing: **{lat['untimed']}** (checkpoints written before timing was recorded)."]
    return L


def why_tags(r):
    """Why a non-exact-match claim is in the failed table. A claim can carry several tags; they are joined with commas by the caller."""
    o = outcome(r)
    tags = []
    if r.get("degraded"):
        tags.append("judge problem")
    if r.get("search_status") in FAIL_SEARCH:
        tags.append("search failure")
    if o == "error":
        tags.append("error")
    if o == "wrong_other":
        tags.append("wrong verdict")
    if o in ("overclaim_false", "overclaim_true"):
        tags.append("overclaim")
    if o == "abstained":
        tags.append("abstained")
    return tags


def failed_table(res):
    nonexact = [r for r in res if r.get("got") != r["label"]]
    bad = [r for r in res if r.get("got") != r["label"] or system_failure(r)]     # an exact match with a failure is listed too
    extra = len(bad) - len(nonexact)
    L = ["", "## Failed, abstained and wrong cases", "",
         f"Every claim whose result is not an exact match: {len(nonexact)} of {len(res)}. Nothing is left out of this table.", ""]
    if extra:
        L += [f"{extra} exact match(es) are also listed because their check had a judge, search or check failure, so the result is not clean.", ""]
    L += ["| Claim | Lang | Label | Sach | Layer | Reason codes | Result | Why | ms | Error |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in bad:
        tag = {"correct": "exact match, check had a failure", "abstained": "miss (abstained)", "overclaim_false": "OVERCLAIM (FALSE)",
               "overclaim_true": "OVERCLAIM (TRUE)", "wrong_other": "WRONG", "error": "ERROR"}[outcome(r)]
        ms = r.get("ms")
        why = ", ".join(why_tags(r)) or "-"
        L.append(f"| {_esc(r['claim'])} | {r['lang']} | {r['label']} | {r['got'] or '-'} | {r.get('layer', 'live')} | "
                 f"{_esc(', '.join(r.get('reasons') or []) or '-')} | {tag} | {why} | {'-' if ms is None else ms} | {_esc(r.get('error') or '-')} |")
    if not bad:
        L.append("| none | | | | | | | | | |")
    return L


NOT_MEASURED = [
    "Real-user outcomes: this measures Sach's verdicts against labelled claims. It does not measure whether people who receive a forward are helped, or what they do after a check.",
    "The eval set was written by the builders, not collected from real forwards. Claims are cleaner than real forwards (no typos, mixed scripts, emoji or long chains).",
    "Seeded vs unseeded: seeded rows can be found in Sach's own index, so their retrieval is partly circular. The split is shown, but it is not a clean test of retrieval.",
    "Non-English claims were written by the builders (by an AI model for most), and no native speaker has reviewed them.",
    "Single run: one run, no repeats. Live search results and model output vary, so a difference of a claim or two is noise.",
    "Provider variability: which LLM and search provider answered, and any fallback, changes results and latency. Latency also depends on provider load and on `--workers`.",
]


def metrics(rows):
    """Artifact metrics as numerator/denominator pairs. Rates use every attempted row; the decisive denominator counts TRUE/FALSE labels.
    'abstention' is every clean UNVERIFIED answer (controls included); 'abstained_on_decisive' is the missed-abstention rate."""
    scores = summarize(rows)
    n = scores["n"]
    failures = sum(system_failure(row) for row in rows)
    unverified = sum(clean(row) and row.get("got") == "UNVERIFIED" for row in rows)
    decisive = sum(row["label"] in ("TRUE", "FALSE") for row in rows)
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


def _error_row(category, error=None):
    """A check that produced no verdict. It is a failure: never correct, abstained or a wrong verdict.
    'error' is the exception class name only. No exception message text is stored or printed anywhere."""
    return {"got": None, "status": "error", "error_category": category, "error_categories": [category],
            "abstention_category": None, "reasons": [], "evidence_ids": [],
            "source_availability": {"search": "unknown", "observed_source_records": 0, "cited": 0, "page_availability": "unknown"},
            "layer": "error", "degraded": False, "search_status": None, "error": error}


def capture_result(res, llm, offline=False):
    got = res["verdict"]
    if got not in LABELS:
        return _error_row("invalid_result")
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
    if search in FAIL_SEARCH:
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
        "degraded": "judge_degraded" in errors,          # judge problem only (the run's degraded_claims counter)
        "search_status": search,
        "error": None,
    }


# ---------- running ----------
# Exception text is never stored or printed: a failed check keeps only the exception class name (see _error_row).


def run(rows, ret, llm, ckpt, log=False, out=print, workers=1, check=None, offline=False):
    """Check every row not already in the checkpoint; update + persist the checkpoint after each claim.
    Workers persist outcomes in completion order and return them in dataset order."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    ckpt["no_llm"] = bool(ckpt.get("no_llm")) or llm is None
    base = ckpt.get("llm_failures", 0)
    start_fail = getattr(llm, "failures", 0)
    lock = threading.Lock()
    n = len(rows)
    check = check if check is not None else check_forward

    def one(i, r):
        started_at = utc_now()
        start = time.monotonic()
        try:
            result = capture_result(check(r["claim"], ret, llm, log=log), llm, offline=offline)
        except Exception as exc:                    # one broken claim must not abort the run: it is recorded as an error row (a failure)
            category = "check_timeout" if isinstance(exc, TimeoutError) else "check_exception"
            result = _error_row(category, error=type(exc).__name__)
        latency = round((time.monotonic() - start) * 1000, 3)    # wall time of this claim's check, measured in this thread
        result.update(started_at=started_at, latency_ms=latency, ms=latency)
        with lock:                                  # one writer at a time: the checkpoint file and the counters
            ckpt["results"][r["claim"]] = result
            ckpt["llm_failures"] = base + max(0, getattr(llm, "failures", 0) - start_fail)
            categories = result.get("error_categories", ())
            if any(category.startswith("search_") for category in categories):
                ckpt["search_failures"] = ckpt.get("search_failures", 0) + 1       # web search lost (or off) for this claim
            if "judge_degraded" in categories:
                ckpt["degraded_claims"] = ckpt.get("degraded_claims", 0) + 1       # a judge timed out / failed (its UNVERIFIED is not a real abstention)
            if not offline:
                save_checkpoint(ckpt)               # offline fixture runs never touch the checkpoint file
            out(f"[{i}/{n}] {r['label']:10} -> {result['got'] or result['error_category']}")

    todo = []
    for i, r in enumerate(rows, 1):
        prev = ckpt["results"].get(r["claim"])
        if prev is not None and prev.get("status") != "error" and prev.get("got") != "ERROR":   # an error is retried on resume; a finished claim is not
            out(f"[{i}/{n}] {r['label']:10} -> (resumed) {prev['got'] or prev.get('error_category')}")
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
            "layer": row.get("layer") if row.get("layer") in ("live", "match", "mixed") else None,
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
          f"- **Overclaimed FALSE (the unforgivable failure): {s['overclaimed_false']}**",
          f"- **Overclaimed TRUE (also an overclaim): {s['overclaimed_true']}**",
          f"- Wrong verdicts other than overclaims (e.g. MISLEADING where a TRUE/FALSE label stands; ERRORs excluded): {measures(res, failed)['wrong_not_overclaim']['count']}",
          f"- System failures (ERROR, judge problem or search failure; see Measures): {measures(res, failed)['failures']['claims_with_any_failure']}/{n}",
          f"- Latency in ms (p50/p95, {m['latency_ms']['n']} samples): {m['latency_ms']['p50']}/{m['latency_ms']['p95']}"]
    for l in ("FALSE", "TRUE"):
        g = [r for r in res if r["label"] == l]
        L.append(f"- Label {l}: {sum(is_correct(r) for r in g)}/{len(g)} correct; {sum(is_abstained(r) for r in g)} abstained as UNVERIFIED")
    g = [r for r in res if r["label"] == "UNVERIFIED"]          # the controls: UNVERIFIED is the expected answer, so they are not "correct" or "abstained"
    L.append(f"- Label UNVERIFIED (controls): {sum(is_correct(r) for r in g)}/{len(g)} answered UNVERIFIED as expected")
    for tag, flag in (("Seeded (the source's PRID is in data/seed_debunks.json or data/pib_index.jsonl; retrieval is partly circular)", True),
                      ("Unseeded (retrieval had to find the page itself)", False)):
        g = [r for r in res if r["seeded"] == flag and r["label"] != "UNVERIFIED"]
        if g:
            L.append(f"- {tag}: {sum(is_correct(r) for r in g)}/{len(g)} correct")
    L += measures_section(res, failed)
    L += latency_section(res)
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
        sf = sum(system_failure(r) for r in res if r["lang"] == lg)
        L.append(f"| {lg} | {d['n']} | {d['correct']} | {d['abstained']} | {d['overclaimed_false']} | {d['overclaimed_true']} | {sf} |")
    k_unv = sum(r["label"] == "UNVERIFIED" for r in res)
    L += ["", "Abstained = Sach said UNVERIFIED where the label was not UNVERIFIED (safe but a miss).", "",
          f"The site card's 'abstained' figure counts every such UNVERIFIED answer across all labels; the abstention rate in Measures counts only "
          f"TRUE/FALSE-labelled claims. The {k_unv} UNVERIFIED-labelled controls are correct when Sach says UNVERIFIED, so they are in neither count.", "",
          "## Every claim", "", "| Claim | Lang | Label | Sach | Result |", "|---|---|---|---|---|"]
    for r in res:
        o = outcome(r)
        tag = {"correct": "ok", "abstained": "miss (abstained)", "overclaim_false": "OVERCLAIM (FALSE)",
               "overclaim_true": "OVERCLAIM (TRUE)", "wrong_other": "WRONG", "error": "ERROR"}[o]
        if o in ("correct", "abstained") and not clean(r):
            tag = "system failure (not counted as " + ("correct" if o == "correct" else "abstained") + ")"
        L.append(f"| {_esc(r['claim'])} | {r['lang']} | {r['label']} | {r['got'] or '-'} | {tag} |")
    L += failed_table(res)
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
    L += ["", "## What this run did not measure", ""] + [f"- {x}" for x in NOT_MEASURED]
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


def summary_payload(res, meta, eval_hash, judges, failed=0):
    """data/eval_summary.json: the old keys (same meaning), 'measures', and the run-status keys the website checks.
    Written only for a clean, complete, non-degraded full run, so the status keys are fixed to that case."""
    return {**summarize(res), "commit": meta["commit"], "dirty": meta["dirty"], "date": meta["date"], "by_lang": by_lang(res),
            "eval_set_hash": eval_hash, "retrievers": meta["retrievers"], "judges": judges, "measures": measures(res, failed),
            "schema_version": SCHEMA_VERSION, "mode": "live", "complete": True, "partial": False, "degraded": False,
            "no_match": False, "system_failures": sum(system_failure(r) for r in res)}


# ---------- main ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--resume", action="store_true", help="skip claims already checkpointed for matching code, config and dataset")
    ap.add_argument("--only-lang", default="", help="comma list, e.g. hi,te (partial run)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N rows (partial run)")
    ap.add_argument("--no-match", action="store_true", help="switch the MATCH layer off (SACH_NO_MATCH=1) to measure the live layer alone; never replaces the headline files")
    ap.add_argument("--dry-run", action="store_true", help="validate and print the plan; no network calls")
    ap.add_argument("--offline", action="store_true", help="check local synthetic fixtures without keys or network")
    ap.add_argument("--workers", type=int, default=1, help="check this many claims at once (default 1 = sequential; higher is faster; stays inside provider limits at 3)")
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
    run_args = {"check": check_fixture, "offline": True} if a.offline else {}
    res = run(sel, ret, llm, ckpt, log=config["ledger_logging"], workers=a.workers, **run_args)
    failed = ckpt.get("llm_failures", 0)
    sfailed = ckpt.get("search_failures", 0)
    dclaims = ckpt.get("degraded_claims", 0)
    errs = sum(outcome(r) == "error" for r in res)                   # claims whose check raised or returned no verdict
    failures = sum(system_failure(r) for r in res)                   # errors plus claims that are not clean (judge, search)
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
    if errs:
        mode = (mode if (ckpt["no_llm"] or failed or sfailed or dclaims) else "FALLBACK") + f"; checking raised an error on {errs} claims (recorded as ERROR, counted as failures)"
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
        write_json(SUMMARY, summary_payload(res, meta, eval_hash(rows), judges, failed))     # read by the website
    target.write_text(report, encoding="utf-8")
    print("\n".join(report.split("\n")[:14]))
    print(f"\nwrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}"
          + ("  (headline files NOT touched)" if partial or degraded or no_match_run else ""))
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
