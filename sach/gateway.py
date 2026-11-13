"""Vercel AI Gateway as an AI-judge transport, paid from the owner's free monthly Vercel AI Gateway credit (about $5).

Who calls it: sach/llm.py (GatewayJudge, build_judges) and sach/status.py (usage). Off unless AI_GATEWAY_API_KEY is set: with no key
nothing here runs and the judge chain behaves exactly as before.

Facts (from https://vercel.com/docs/ai-gateway): the endpoint is OpenAI-compatible, POST {BASE}/chat/completions with
`Authorization: Bearer <AI_GATEWAY_API_KEY>`, model ids are `creator/model`. 401 = bad key, 402 = credits (or a budget) used up,
429 = rate limited (may carry Retry-After). The request and response shapes are those of the other OpenAI-compatible judges
(choices[0].message.content), so GatewayJudge reuses OpenAICompatJudge's parsing; only the transport and the failure policy differ.

Spend guard: the credit is finite. A daily call cap (SACH_GATEWAY_MAX_PER_DAY, default 1500, 0 = unlimited) is counted with the shared
counter in sach/store.py on UTC-day keys, the same pattern as sach/vertex.py. Attempts are counted, failed ones are not given back.

Secrets: the key never appears in a log line, an exception message, a repr or the status page. Every error raised from here is a
GatewayError (or TimeoutError) with a generic message built by this module, never the text of an underlying exception. stdlib only."""
from __future__ import annotations
import json, os, urllib.error, urllib.request, time
from . import limits, store

BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_MODELS = "openai/gpt-oss-120b,google/gemini-3.1-flash-lite"
DEFAULT_MAX_PER_DAY = 1500
AUTH_PAUSE_S = 600                # 401/403: the provider is benched this long
MAX_RESPONSE = 2_000_000


class GatewayError(Exception):
    """Generic failure. `code` is the HTTP status when there was one; `headers` carries Retry-After only. The message is always ours."""
    def __init__(self, msg, code=None, headers=None):
        super().__init__(msg)
        self.code, self.headers = code, headers or {}


class GatewayCapReached(GatewayError):
    """The daily call cap is used up: the provider is paused until 00:00 UTC."""


def configured(env=None) -> bool:
    return bool(((env if env is not None else os.environ).get("AI_GATEWAY_API_KEY") or "").strip())

def models() -> list:
    return [m.strip() for m in os.environ.get("SACH_GATEWAY_MODELS", DEFAULT_MODELS).split(",") if m.strip()]


def post(opener, key: str, model: str, body: dict, timeout: float) -> dict:
    """POST one chat completion; -> parsed JSON. Any failure becomes a GatewayError/TimeoutError with a generic message."""
    req = urllib.request.Request(BASE_URL + "/chat/completions", json.dumps(body).encode(), {
        "Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "Sach-check/0.1"}, method="POST")
    code, headers, kind = None, {}, ""
    try:
        with opener(req, timeout=timeout) as r:
            out = json.loads(r.read(MAX_RESPONSE).decode("utf-8", "replace"))
        if not isinstance(out, dict):
            raise ValueError
        return out
    except urllib.error.HTTPError as e:
        code, kind = int(e.code), "http"
        try:
            ra = e.headers.get("retry-after") if e.headers is not None else None
            headers = {"retry-after": ra} if ra else {}
        except Exception:
            headers = {}
    except (TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        kind = "timeout" if isinstance(e, TimeoutError) or isinstance(reason, TimeoutError) else "network"
    except Exception:
        kind = "other"
    if kind == "timeout":
        raise TimeoutError("gateway: request timed out")
    if kind == "http":
        raise GatewayError("gateway: request failed with HTTP %d" % code, code, headers)
    raise GatewayError("gateway: request failed (%s)" % ("network error" if kind == "network" else "unreadable reply"))


# ---------------------------------------------------------------- spend guard
def max_per_day() -> int:
    return limits._env_int("SACH_GATEWAY_MAX_PER_DAY", DEFAULT_MAX_PER_DAY)

def _day_key(now: float) -> str:
    return "gw:d:%d" % int(now // 86400)

def seconds_to_utc_midnight(now: float) -> float:
    return 86400 - (now % 86400)

def reserve_call(st=None, now=None) -> None:
    """Count one call against today's cap. Raises GatewayCapReached when the cap is used up (the attempt is given back, a 'skipped'
    counter is bumped). Never raises anything else: a broken store only makes the cap per-instance."""
    cap = max_per_day()
    if cap <= 0:
        return
    now = time.time() if now is None else now
    try:
        st = st or store.get_store()
    except Exception:
        st = None
    key = _day_key(now)
    n, _ = limits._incr(st, key, 2 * 86400) if st is not None else (limits._mem_incr(key), False)
    if n > cap:
        try:
            if st is not None and getattr(st, "remote", False):
                st.incr(key, -1)
            else:
                limits._mem_incr(key, -1)
            limits._incr(st, "gw:skipped:%d" % int(now // 86400), 2 * 86400) if st is not None else None
        except Exception:
            pass
        raise GatewayCapReached("gateway: daily call cap reached (resumes 00:00 UTC)")

def usage(st=None, now=None) -> dict:
    """For the status page: counts only, never any credential material."""
    now = time.time() if now is None else now
    out = {"calls_today": 0, "max_per_day": max_per_day(), "skipped_over_cap_today": 0}
    try:
        st = st or store.get_store()
        kd, ks = _day_key(now), "gw:skipped:%d" % int(now // 86400)
        c = st.counters([kd, ks]) if getattr(st, "remote", False) else {}
        with limits._mem_lock:
            mem = dict(limits._mem)
        out["calls_today"] = max(int(c.get(kd, 0) or 0), int(mem.get(kd, 0)), 0)
        out["skipped_over_cap_today"] = max(int(c.get(ks, 0) or 0), int(mem.get(ks, 0)), 0)
    except Exception:
        pass
    return out
