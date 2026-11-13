"""Status page: GET /?view=status (and &format=json). Which AI and search providers are configured and ready, how much of the
global live-check budget is used, and what the counters say. Honest about its limits: provider pause state lives in THIS serverless
instance's memory (another instance may differ); budget and counters come from the shared store when Upstash is set.

Never shows keys, key suffixes or IP addresses: a Gemini judge's internal name carries the last 4 characters of its key, so judges
are labelled by position ("gemini #1") here, never by their internal name."""
from __future__ import annotations
import time
from . import timefmt
from . import gtranslate, ledger, limits, store, vertex, gateway

_AI = [("vertex", "GOOGLE_SA_JSON"), ("groq", "GROQ_API_KEY"), ("gateway", "AI_GATEWAY_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("openrouter", "OPENROUTER_API_KEY"), ("mistral", "MISTRAL_API_KEY"),
       ("cloudflare", "CLOUDFLARE_API_TOKEN"), ("claude", "ANTHROPIC_API_KEY")]
_SEARCH = [("brave", "BRAVE_API_KEY"), ("tavily", "TAVILY_API_KEY")]


def _family(name: str) -> str:
    return "gemini" if name.startswith("gemini") else name


def _capped_usage(j, st, now, mod) -> dict:
    try:
        return j.usage(st, now)
    except Exception:
        return {"calls_today": 0, "max_per_day": mod.max_per_day(), "skipped_over_cap_today": 0}

_CAPPED = {"vertex": vertex, "gateway": gateway}      # billed providers: calls today against a daily cap


def ai_providers(llm, now=None, st=None) -> list:
    now = time.time() if now is None else now
    judges = list(getattr(llm, "judges", None) or [])
    rows, seen = [], {}
    for j in judges:
        fam = _family(str(getattr(j, "name", "judge")))
        seen[fam] = seen.get(fam, 0) + 1
        try:
            ready = bool(j.available())
        except Exception:
            ready = False
        try:
            paused = sorted(m for m, t in j._pauses().items() if t > now) if hasattr(j, "_pauses") else []
        except Exception:
            paused = []
        rows.append({"provider": fam if sum(1 for x in judges if _family(str(getattr(x, "name", ""))) == fam) == 1 else f"{fam} #{seen[fam]}",
                     "configured": True, "state": "ready" if ready else "paused",
                     "paused_models": len(paused), "models": len(getattr(j, "models", []) or [1]),
                     "failures_since_start": int(getattr(j, "failures", 0) or 0)})
        if fam in _CAPPED:                       # billed provider: today's calls against the cap (counts only, never the project, account or key)
            rows[-1].update(_capped_usage(j, st, now, _CAPPED[fam]))
    for fam, env in _AI:
        if fam not in seen:
            rows.append({"provider": fam, "configured": False, "state": "off", "paused_models": 0, "models": 0, "failures_since_start": 0})
            if fam in _CAPPED:
                rows[-1].update({"calls_today": 0, "max_per_day": _CAPPED[fam].max_per_day(), "skipped_over_cap_today": 0})
    return rows


def search_providers(retrievers, now=None) -> list:
    now = time.time() if now is None else now
    chain = next((getattr(r, "chain", None) for r in (retrievers or []) if getattr(r, "chain", None) is not None), None)
    rows, have = [], set()
    for p in getattr(chain, "providers", []) or []:
        until = chain.paused_until(p.name)
        have.add(p.name)
        rows.append({"provider": p.name, "configured": True, "state": "paused" if until > now else "ready",
                     "paused_for_s": max(0, int(until - now))})
    for name, env in _SEARCH:
        if name not in have:
            rows.append({"provider": name, "configured": False, "state": "off", "paused_for_s": 0})
    return rows


def status_data(llm=None, retrievers=None, st=None, now=None) -> dict:
    now = time.time() if now is None else now
    st = st or store.get_store()
    try:
        c = ledger.stats()
    except Exception:
        c = {}
    use = limits.usage(st, now)
    total, hits = int(c.get("checks_total", 0) or 0), int(c.get("cache_hits", 0) or 0)
    return {
        "generated_at": ledger.now(),
        "scope_note": ("Provider state (ready / paused, failures) is read from this one server instance's memory and resets when it "
                       "restarts; other instances may differ. Budget and counters come from the shared store when one is configured."),
        "ai_providers": ai_providers(llm, now, st),
        "search_providers": search_providers(retrievers, now),
        "live_budget": {"minute": {"used": use["minute_used"], "max": use["minute_max"]},
                        "day_utc": {"used": use["day_used"], "max": use["day_max"]},
                        "refused_busy_today": use["busy_today"], "shared_store": use["shared_store"],
                        "note": "Fixed windows (the minute, the UTC day). A max of 0 means no limit. Cache and match answers are not counted."},
        "google_translation": gtranslate.usage(st, now),
        "checks": {"total_all_time": total, "cache_hits_all_time": hits, "live_all_time": max(total - hits, 0),
                   "counting_since": c.get("first_event_at"),
                   "note": "All-time counters from the same store as the impact page (cache hits cost nothing). Matches are included in the live figure until they have their own counter."},
        "storage": "persistent" if getattr(st, "remote", False) else "temporary",
    }


def _badge(state):
    from .site import esc
    cls = {"ready": "TRUE", "paused": "MISLEADING", "off": "UNVERIFIED"}.get(state, "UNVERIFIED")
    return '<b class="%s">%s</b>' % (cls, esc(state))


def status_page(d: dict) -> bytes:
    from .site import esc, layout
    def _calls(r):
        if "calls_today" not in r:
            return "-"
        return "%s of %s" % (r["calls_today"], r["max_per_day"]) if r["max_per_day"] else "%s (no cap)" % r["calls_today"]
    ai = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s of %s</td><td>%s</td><td>%s</td></tr>" % (
        esc(r["provider"]), "yes" if r["configured"] else "no", _badge(r["state"]),
        r["paused_models"], r["models"], r["failures_since_start"], esc(_calls(r))) for r in d["ai_providers"])
    se = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        esc(r["provider"]), "yes" if r["configured"] else "no", _badge(r["state"]),
        ("%s s" % r["paused_for_s"]) if r["paused_for_s"] else "-") for r in d["search_providers"])
    b, ck = d["live_budget"], d["checks"]
    lim = lambda x: "no limit" if not x["max"] else "%s of %s" % (x["used"], x["max"])
    g = d["google_translation"]
    gt_used = "%s of %s" % (g["chars_today"], g["max_chars_per_day"]) if g["max_chars_per_day"] else "%s (no limit)" % g["chars_today"]
    body = ('<div class="wrap" style="padding:30px 0"><p class="kicker">Health</p><h1 style="font-size:clamp(32px,8vw,56px)">Status</h1>'
            '<p class="sub">Updated %s. %s</p>'
            '<h2>AI judges</h2><div style="overflow-x:auto"><table><thead><tr><th>Provider</th><th>Configured</th><th>Now</th><th>Models paused</th><th>Failures since start</th><th>Calls today</th></tr></thead><tbody>%s</tbody></table></div>'
            '<h2 style="margin-top:28px">Web search</h2><div style="overflow-x:auto"><table><thead><tr><th>Provider</th><th>Configured</th><th>Now</th><th>Paused for</th></tr></thead><tbody>%s</tbody></table></div>'
            '<h2 style="margin-top:28px">Live-check budget</h2><ul><li>This minute: <b>%s</b></li><li>Today (resets 5:30 am IST): <b>%s</b></li><li>Refused as busy today: <b>%s</b></li></ul><p class="note">%s</p>'
            '<h2 style="margin-top:28px">Google Translation</h2><ul><li>Configured: <b>%s</b></li><li>Characters today (resets 5:30 am IST): <b>%s</b></li><li>Skipped because the budget was used: <b>%s</b></li></ul><p class="note">Optional first-choice translator for non-English forwards; when it is off, over budget or unavailable, the AI translator is used. Repeats come from the cache and are not counted.</p>'
            '<h2 style="margin-top:28px">Checks</h2><ul><li>All time: <b>%s</b> (cache hits <b>%s</b>, everything else <b>%s</b>)</li><li>Counting since: %s</li></ul><p class="note">%s</p>'
            '<p class="note"><a href="/?view=status&amp;format=json">The same data as JSON</a> &middot; <a href="/impact">Impact</a></p></div>') % (
        esc(timefmt.fmt_ist(d["generated_at"])), esc(d["scope_note"]), ai, se, esc(lim(b["minute"])), esc(lim(b["day_utc"])),
        b["refused_busy_today"], esc(b["note"]), "yes" if g["configured"] else "no", esc(gt_used), g["skipped_over_budget_today"], ck["total_all_time"], ck["cache_hits_all_time"], ck["live_all_time"],
        esc(timefmt.fmt_ist(ck["counting_since"]) if ck["counting_since"] else "not available"), esc(ck["note"]))
    return layout(body, "Status — Sach", path="/?view=status", noindex=True)


def serve(handler, llm, retrievers, as_json=False):
    import json
    d = status_data(llm, retrievers)
    if as_json:
        body, ctype = json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8"
    else:
        body, ctype = status_page(d), "text/html; charset=utf-8"
    return handler._send(body, 200, ctype, cache="no-store", extra={"X-Robots-Tag": "noindex, nofollow"})
