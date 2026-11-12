"""Live impact page. Nothing here is typed in: every figure is computed from the ledger, the counters and
data/eval_summary.json at request time, and each one carries a plain-English 'how' line.

If a source is unavailable the figure is None in the data and "not available" on the page, never a placeholder."""
from __future__ import annotations
import json, os
from . import fetch, ledger, store
from .lang import NAMES, SUPPORTED
from .site import ROOT, esc, layout

VERDICTS = ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED")
LANGS = SUPPORTED          # every language Sach detects (lang.SUPPORTED); counters for ones never seen simply read zero
LANG_NAME = NAMES
RECENT = 5            # how many recent FALSE verdicts to list
NA = "not available"


def pct(part, whole):
    """Percentage rounded to one decimal, or None when the denominator is zero (never a division error)."""
    if not whole:
        return None
    return round(part * 100 / whole, 1)


def _eval_file() -> tuple[dict, str | None]:
    p = os.path.join(ROOT, "data", "eval_summary.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return (d, None) if isinstance(d, dict) else ({}, "data/eval_summary.json is not a JSON object")
    except FileNotFoundError:
        return {}, "data/eval_summary.json does not exist in this deployment"
    except Exception as e:
        return {}, "data/eval_summary.json could not be read (%s)" % type(e).__name__


def _evaluation() -> dict:
    d, err = _eval_file()
    keys = ("n", "correct", "overclaimed_false", "overclaimed_true", "abstained", "commit", "date")
    ev = {"available": bool(d), "error": err}
    for k in keys:
        ev[k] = d.get(k)
    ev["by_lang"] = d.get("by_lang")
    ev["correct_pct"] = pct(d["correct"], d["n"]) if isinstance(d.get("correct"), int) and isinstance(d.get("n"), int) else None
    ev["missing_fields"] = [k for k in keys if k not in d] + ([] if "by_lang" in d else ["by_lang"]) if d else []
    ev["how"] = ("Read from data/eval_summary.json, which scripts/run_eval.py writes after a full run of the "
                 "evaluation set. Percent correct = correct / n.")
    return ev


def _recent_false(rows: list) -> list:
    idx = [(str(r.get("checked_at") or ""), i) for i, r in enumerate(rows) if r.get("verdict") == "FALSE"]
    out = []
    for _, i in sorted(idx, reverse=True)[:RECENT]:
        r = rows[i]
        cites = r.get("citations") or []
        c = cites[0] if cites and isinstance(cites[0], dict) else {}
        url = str(c.get("url") or "")
        out.append({"claim": str(r.get("claim") or ""), "date": str(r.get("checked_at") or "").split("T")[0],
                    "citation_url": url if url.lower().startswith(("http://", "https://")) else None,
                    "citation_source": str(c.get("source") or "") or None})
    return out


def _sources_policy() -> dict:
    return {
        "official_suffixes": len(fetch.OFFICIAL_SUFFIXES),
        "official_hosts": len(fetch.OFFICIAL_HOSTS),
        "official_zones": len(fetch.OFFICIAL_ZONES),
        "official_extra_domains": len(fetch.EXTRA_OFFICIAL),
        "factchecker_hosts": len(fetch.FACTCHECKER_HOSTS),
        "factchecker_sites_with_path_rules": len(fetch.FACTCHECKER_PATHS),
        "how": "Counted from the lists in sach/fetch.py (OFFICIAL_SUFFIXES, OFFICIAL_HOSTS, OFFICIAL_ZONES, "
               "EXTRA_OFFICIAL, FACTCHECKER_HOSTS, FACTCHECKER_PATHS). Fact-checkers are secondary: they are "
               "labelled and can never produce TRUE or FALSE on their own.",
    }


def impact_data() -> dict:
    st = ledger.stats()
    rows = [r for r in ledger.load() if isinstance(r, dict)]
    persistent = bool(getattr(store.get_store(), "remote", False))
    total, hits, noc = st.get("checks_total", 0), st.get("cache_hits", 0), st.get("no_claims", 0)
    vsum = sum(st.get("verdict:" + v, 0) for v in VERDICTS)
    lsum = sum(st.get("lang:" + k, 0) for k in LANGS)
    by_v = {v: sum(1 for r in rows if r.get("verdict") == v) for v in VERDICTS}
    return {
        "generated_at": ledger.now(),
        "counting_since": st.get("first_event_at"),
        "storage": "persistent" if persistent else "temporary",
        "storage_note": ("Counters live in a shared remote store and survive server restarts. If that store cannot be "
                         "reached, counters read as zero." if persistent else
                         "Counters live in files on this server and reset when it restarts."),
        "checks_total": total,
        "checks_served_fresh": max(total - hits, 0),
        "cache_hits": hits,
        "cache_hit_pct": pct(hits, total),
        "no_claims": noc,
        "verdicts": {"denominator": vsum,
                     **{v: {"count": st.get("verdict:" + v, 0), "pct": pct(st.get("verdict:" + v, 0), vsum)} for v in VERDICTS}},
        "languages": {"denominator": lsum,
                      **{k: {"count": st.get("lang:" + k, 0), "pct": pct(st.get("lang:" + k, 0), lsum)} for k in LANGS}},
        "ledger": {"rows": len(rows), "by_verdict": by_v, "recent_false": _recent_false(rows)},
        "evaluation": _evaluation(),
        "sources_policy": _sources_policy(),
        "how": {
            "checks_total": "Counter checks_total: incremented once for every completed check, including cache hits.",
            "checks_served_fresh": "checks_total minus cache_hits: checks that ran the full pipeline.",
            "cache_hits": "Counter cache_hits: incremented when an identical forward was answered from the verdict cache.",
            "no_claims": "Counter no_claims: forwards with nothing checkable (greetings, emoji, bare links). They are not in the verdict breakdown.",
            "verdicts": "Counters verdict:TRUE, verdict:FALSE, verdict:MISLEADING, verdict:UNVERIFIED (overall verdict of each check). "
                        "Each share = that count / the sum of the four, and the denominator is shown.",
            "languages": "Counters lang:<code> for every supported language code, e.g. lang:en, lang:hi, lang:bn (language of the forward as detected). Each share = count / the sum of those counters.",
            "ledger": "Rows returned by ledger.load(): the bundled starter ledger plus rows recorded by this server. "
                      "One row per claim (a forward can hold several claims), so this is not the same number as checks.",
            "recent_false": "The latest rows in that ledger whose verdict is FALSE, newest first, with the first citation on each.",
            "counting_since": "Counter first_event_at: the time of the first check this store ever counted.",
        },
    }


# ------------------------------------------------------------------ page
IMPACT_CSS = """
.imp-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:14px;margin:0 0 24px}
.imp-stats .card{min-width:0}.imp-stats .num{font-size:clamp(30px,9vw,44px);color:var(--ink);overflow-wrap:anywhere}
.imp-stats .card p{margin-top:6px}.imp-stats .num.na{font-size:22px;color:var(--mute)}
.imp-bar{display:flex;height:30px;border:2px solid var(--rule);border-radius:4px;overflow:hidden;background:var(--paper2);margin:10px 0}
.imp-bar i{display:block;height:100%;min-width:0}
.imp-bar .TRUE{background:var(--true)}.imp-bar .FALSE{background:var(--false)}.imp-bar .MISLEADING{background:var(--mis)}.imp-bar .UNVERIFIED{background:var(--unv)}
.imp-legend{list-style:none;margin:8px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:6px 16px;font-size:15px}
.imp-legend li{display:flex;gap:8px;align-items:baseline}
.imp-legend .sw{flex:none;width:12px;height:12px;border-radius:2px;border:1px solid var(--rule);transform:translateY(1px)}
.imp-legend .TRUE{background:var(--true)}.imp-legend .FALSE{background:var(--false)}.imp-legend .MISLEADING{background:var(--mis)}.imp-legend .UNVERIFIED{background:var(--unv)}
.imp-honest{margin:0 0 28px}.imp-honest p{margin:6px 0}
.imp-how{padding-left:20px}.imp-how li{margin:8px 0;overflow-wrap:anywhere}
.imp-recent{list-style:none;margin:0;padding:0}.imp-recent li{padding:12px 0;border-bottom:1px solid color-mix(in srgb,var(--ink) 25%,transparent);overflow-wrap:anywhere}
.imp-recent .note{display:block;margin-top:2px}
.imp-sec h2{font-size:clamp(24px,6vw,34px)}.imp-sec h3{font-family:var(--serif);font-size:20px;margin:18px 0 4px}
"""


def _n(v):
    return NA if v is None else esc(str(v))


def _pct(v):
    return NA if v is None else "%s%%" % v


def _stat(num, label, na=False):
    return '<div class="card"><div class="num%s">%s</div><p>%s</p></div>' % (" na" if na else "", num, esc(label))


def _share_block(title: str, order, labels, group: dict, denom_what: str) -> str:
    d = group["denominator"]
    if not d:
        return '<h3>%s</h3><p class="note">Not available: no checks have been counted yet, so there is nothing to divide.</p>' % esc(title)
    segs = "".join('<i class="%s" style="width:%s%%"></i>' % (k, group[k]["pct"]) for k in order if group[k]["count"])
    text = ", ".join("%s %s (%s of %s)" % (labels.get(k, k), group[k]["pct"], group[k]["count"], d) for k in order)
    legend = "".join('<li><span class="sw %s" aria-hidden="true"></span><span><b>%s</b>: %s, %s%%</span></li>'
                     % (k, esc(labels.get(k, k)), group[k]["count"], group[k]["pct"]) for k in order)
    return ('<h3>%s</h3><div class="imp-bar" role="img" aria-label="%s">%s</div><ul class="imp-legend">%s</ul>'
            '<p class="note">Shares are out of %s (%s).</p>') % (esc(title), esc(text), segs, legend, d, esc(denom_what))


def impact_page() -> bytes:
    d = impact_data()
    persistent = d["storage"] == "persistent"
    since = d["counting_since"]
    ev = d["evaluation"]
    v, lg, lgr = d["verdicts"], d["languages"], d["ledger"]
    if d["checks_total"]:
        stats = "".join((
            _stat(esc(str(d["checks_total"])), "checks counted"),
            _stat(esc(str(d["checks_served_fresh"])), "ran the full pipeline"),
            _stat(esc(str(d["cache_hits"])), "answered from the cache (%s of all checks)" % _pct(d["cache_hit_pct"])),
            _stat(esc(str(d["no_claims"])), "had nothing checkable"),
        ))
    else:
        stats = _stat(NA, "No checks counted yet, so there is nothing to show.", na=True)
    honest = ('<div class="honest imp-honest" id="honesty"><h2 style="font-size:22px">Read this first</h2>'
              '<p><b>Counting since %s.</b> This server\'s counters are <b>%s</b>%s.</p>'
              '<p>Numbers are computed from the ledger and counters on every page load; nothing here is typed in. %s</p></div>') % (
        esc(since) if since else "not available (no check has been counted yet)",
        "persistent" if persistent else "temporary",
        "" if persistent else ": they reset when the server restarts",
        esc(d["storage_note"]))
    vblock = _share_block("Verdicts", VERDICTS, {}, v, "the sum of the four verdict counters")
    lblock = _share_block("Languages of the forwards", LANGS, LANG_NAME, lg, "the sum of the language counters")
    if ev["available"]:
        miss = ev["missing_fields"]
        facts = [("Claims in the evaluation set", ev["n"]), ("Judged exactly right", ev["correct"]),
                 ("Percent right", _pct(ev["correct_pct"])),
                 ("Overclaimed FALSE", ev["overclaimed_false"]), ("Overclaimed TRUE", ev["overclaimed_true"]),
                 ("Said unverified instead of guessing", ev["abstained"]),
                 ("Run on commit", ev["commit"]), ("Run date", ev["date"])]
        li = "".join("<li>%s: <b>%s</b></li>" % (esc(k), _n(x)) for k, x in facts)
        evb = "<ul>%s</ul>" % li
        if ev["by_lang"]:
            evb += '<p class="note">By language: %s</p>' % esc(json.dumps(ev["by_lang"], ensure_ascii=False))
        if miss:
            evb += '<p class="note">Not in this evaluation file (older format): %s. Shown as not available.</p>' % esc(", ".join(miss))
    else:
        evb = '<p class="note">Not available: %s.</p>' % esc(ev["error"] or "no evaluation summary")
    evb += '<p class="note">%s</p>' % esc(ev["how"])
    recent = ""
    for r in lgr["recent_false"]:
        cite = ('<a href="%s" rel="noopener">%s</a>' % (esc(r["citation_url"]), esc(r["citation_source"] or r["citation_url"]))
                if r["citation_url"] else "no citation recorded")
        recent += '<li>%s<span class="note">%s · %s</span></li>' % (esc(r["claim"]), esc(r["date"] or NA), cite)
    recent = '<ul class="imp-recent">%s</ul>' % recent if recent else '<p class="note">Not available: the ledger has no FALSE verdicts yet.</p>'
    bv = lgr["by_verdict"]
    ledger_line = "%s claim rows in the public ledger: %s." % (lgr["rows"], ", ".join("%s %s" % (bv[k], k) for k in VERDICTS))
    sp = d["sources_policy"]
    sp_line = ("Source rules in sach/fetch.py: %s official suffixes, %s official hosts, %s official zones, %s more official domains; "
               "%s fact-checker sites and %s more with path rules (secondary, labelled).") % (
        sp["official_suffixes"], sp["official_hosts"], sp["official_zones"], sp["official_extra_domains"],
        sp["factchecker_hosts"], sp["factchecker_sites_with_path_rules"])
    how = "".join("<li><b>%s</b>: %s</li>" % (esc(k.replace("_", " ")), esc(t)) for k, t in d["how"].items())
    how += "<li><b>sources policy</b>: %s</li><li><b>evaluation</b>: %s</li>" % (esc(sp["how"]), esc(ev["how"]))
    body = ('<div class="wrap imp-sec"><section style="border:0"><p class="kicker">Live numbers</p><h1 style="font-size:clamp(34px,9vw,64px)">Impact</h1>'
            '<p class="sub">What Sach has done, counted by the server itself. Generated %s UTC.</p>%s'
            '<h2>Checks</h2><div class="imp-stats">%s</div>%s%s'
            '<h2 style="margin-top:34px">Evaluation</h2>%s'
            '<h2 style="margin-top:34px">Public ledger</h2><p>%s</p><h3>Latest FALSE verdicts</h3>%s<p class="note">%s <a href="/?view=ledger">Open the full ledger</a>.</p>'
            '<h2 style="margin-top:34px">How each number is computed</h2><ul class="imp-how">%s</ul>'
            '<p class="note"><a href="/?view=impact&amp;format=json">The same data as JSON</a></p></section></div>') % (
        esc(d["generated_at"].replace("T", " ")), honest, stats, vblock, lblock, evb, esc(ledger_line), recent, esc(sp_line), how)
    return layout(body, "Impact — Sach", path="/impact").replace(b"</style>", ("\n" + IMPACT_CSS).encode() + b"</style>", 1)
