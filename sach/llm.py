"""LLM stance judges with automatic failover. No judge is trusted alone: decisive stances are validated against the page
(verbatim quote, numbers, subject words) and need a second opinion; any failure falls back to stance.degraded_stance().

Order of preference (each only if its key is set): Gemini keys (free tier, rotate through several) -> Groq -> OpenRouter ->
Mistral -> Anthropic. When one is rate-limited or down, the next answers; a quota-exhausted key is skipped for COOLDOWN_S."""
from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from .stance import validate_stance, heuristic_stance

PROMPT = ("You judge ONE source page against ONE claim from a viral forward. Reply on ONE line as:  LABEL | quote\n"
          "where LABEL is exactly one of the words below and quote is a sentence COPIED VERBATIM from the page (max 30 words) that justifies it. For NEITHER write no quote.\n"
          "CONTRADICTS - the page directly refutes this specific claim.\n"
          "CONFIRMS - the page directly states this specific claim is true.\n"
          "PARTIAL - the core fact is real but the claim's numbers, dates or framing differ from the page.\n"
          "NEITHER - anything else: unrelated, only loosely related, or unsure.\n"
          "A page that merely mentions fake news in general, or a DIFFERENT claim, scheme or number, is NEITHER. A page describing a real scheme does not contradict a claim about something else. When unsure, NEITHER.")
TRANSLATE_PROMPT = ("Translate the user's claim into plain English. The claim may be in Telugu, Hindi, or Telugu/Hindi written in English letters (Tinglish/Hinglish). "
                    "Be faithful and literal: keep every number, amount, date, name and scheme name exactly. Do not add, explain or soften anything. Output only the English sentence.")
_MAP = {"CONTRADICTS": "contradicts", "CONFIRMS": "confirms", "PARTIAL": "mixed", "NEITHER": "none"}

COOLDOWN_S = 300      # a key that returned 429/401/403 is skipped this long instead of being hammered on every source

def parse_label(raw: str) -> str:
    w = (raw or "").strip().upper().replace("*", "").split()
    return _MAP.get(w[0].strip(".,:;") if w else "", "none")

def parse_reply(raw: str):
    """'CONTRADICTS | quote...' -> (stance, quote)."""
    label, _, quote = (raw or "").partition("|")
    return parse_label(label), quote.strip()

def _user(claim, title, text):
    return f"CLAIM: {claim}\n\nPAGE TITLE: {title}\nPAGE TEXT: {text[:6000]}"

DEFAULT_GEMINI_MODELS = "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.8-flash,gemini-flash-latest"


class _Judge:
    """Shared behaviour. Subclasses implement _raw(model, system, user, max_tokens) -> text."""
    name = "judge"
    models: list
    exhausted_until = 0.0
    failures = 0

    def available(self) -> bool:
        return time.time() >= self.exhausted_until

    def _note_failure(self, err):
        code = getattr(err, "code", None)
        if code in (429, 401, 403):               # quota / auth: skip this judge for a while (timeouts and 503s do not trigger it)
            self.exhausted_until = time.time() + COOLDOWN_S

    def _label(self, model, claim, title, text):
        st, q = parse_reply(self._raw(model, PROMPT, _user(claim, title, text), 200))
        return validate_stance(st, q, claim, title, text)

    def stance(self, claim, title, text, tier=""):
        """First opinion from the first model that answers. Any decisive stance (not 'none') must be confirmed by a
        DIFFERENT model. If no second model can answer, the deterministic title/number heuristic is the second opinion
        (so a clear PIB debunk survives a flaky free tier, but a lone LLM guess does not). Disagreement -> 'none'."""
        first, used, last = None, None, None
        for m in self.models:
            try:
                first, used = self._label(m, claim, title, text), m
                break
            except Exception as e:      # 404/429/503/timeout/odd payload: try the next model
                last = e
                self._note_failure(e)
                if not self.available():
                    break               # quota gone: the other models of this key share it
        if first is None:
            self.failures += 1
            raise last or RuntimeError(f"{self.name}: no model answered")
        if first == "none":
            return "none"
        for m in [m for m in self.models if m != used] or [used]:
            try:
                return first if self._label(m, claim, title, text) == first else "none"
            except Exception:
                continue
        return first if heuristic_stance(claim, title, text, tier) == first else "none"

    def translate(self, text):
        last = None
        for m in self.models:
            try:
                return self._raw(m, TRANSLATE_PROMPT, text[:1000], 200).strip()
            except Exception as e:
                last = e
                self._note_failure(e)
                if not self.available():
                    break
        raise last or RuntimeError(f"{self.name}: translation failed")


class GeminiJudge(_Judge):
    """Google AI Studio free tier. Skips models that are retired (404), overloaded (503) or rate-limited (429)."""
    def __init__(self, key=None, model=None, timeout=45):
        self.key = key or os.environ["GEMINI_API_KEY"].split(",")[0].strip()
        self.models = [m.strip() for m in (model or os.environ.get("SACH_GEMINI_MODEL", DEFAULT_GEMINI_MODELS)).split(",") if m.strip()]
        self.timeout = timeout
        self.name = "gemini" + (f"-{self.key[-4:]}" if self.key else "")

    def _post(self, model, body):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(url, json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "x-goog-api-key": self.key})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def _raw(self, model, system, user, max_tokens):
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}}
        return self._post(model, body)["candidates"][0]["content"]["parts"][0]["text"]


class OpenAICompatJudge(_Judge):
    """Any OpenAI-compatible chat endpoint: Groq, OpenRouter, Mistral (free tiers / free models)."""
    def __init__(self, name, base_url, key, models, timeout=45):
        self.name, self.base_url, self.key, self.timeout = name, base_url.rstrip("/"), key, timeout
        self.models = [m.strip() for m in models.split(",") if m.strip()]

    def _post(self, model, body):
        req = urllib.request.Request(f"{self.base_url}/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}", "User-Agent": "Sach-check/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def _raw(self, model, system, user, max_tokens):
        body = {"model": model, "temperature": 0, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        return self._post(model, body)["choices"][0]["message"]["content"]


class ClaudeJudge:
    """Optional last resort (paid). Single model: relies on validate_stance and the deterministic check, no second model."""
    name = "claude"
    exhausted_until = 0.0
    failures = 0

    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("SACH_MODEL", "claude-sonnet-5-5")

    def available(self):
        return time.time() >= self.exhausted_until

    def stance(self, claim, title, text, tier=""):
        try:
            r = self.client.messages.create(model=self.model, max_tokens=200, system=PROMPT,
                                            messages=[{"role": "user", "content": _user(claim, title, text)}])
            st, q = parse_reply(r.content[0].text)
            st = validate_stance(st, q, claim, title, text)
            return st if st == "none" or heuristic_stance(claim, title, text, tier) == st else "none"
        except Exception as e:
            self.failures += 1
            self.exhausted_until = time.time() + COOLDOWN_S
            raise

    def translate(self, text):
        r = self.client.messages.create(model=self.model, max_tokens=200, system=TRANSLATE_PROMPT, messages=[{"role": "user", "content": text[:1000]}])
        return r.content[0].text.strip()


class FailoverJudge:
    """Tries judges in order. A judge that raised (all its models failed) is skipped; one in cooldown is skipped without a call.
    Raises only when every judge failed, which makes stance.judge() use the safe rules-only fallback ('Limited mode')."""
    def __init__(self, judges):
        self.judges = list(judges)
        self.failures = 0           # requests where NO judge could answer (what the site reports as Limited mode)

    @property
    def models(self):
        return [m for j in self.judges for m in getattr(j, "models", [])]

    def _run(self, method, *args, **kw):
        last = None
        pool = [j for j in self.judges if j.available()] or []
        for j in pool:
            try:
                return getattr(j, method)(*args, **kw)
            except TypeError:
                if method == "stance" and "tier" in kw:
                    try:
                        return j.stance(*args)
                    except Exception as e:
                        last = e
                else:
                    raise
            except Exception as e:
                last = e
        self.failures += 1
        raise last or RuntimeError("no LLM judge available (all rate-limited or down)")

    def stance(self, claim, title, text, tier=""):
        return self._run("stance", claim, title, text, tier=tier)

    def translate(self, text):
        return self._run("translate", text)

    def describe(self):
        return [(j.name, "ready" if j.available() else "cooling down") for j in self.judges]


def _env_list(*names):
    out = []
    for n in names:
        out += [k.strip() for k in os.environ.get(n, "").split(",") if k.strip()]
    return out

PROVIDERS = (   # name, env key, base url, default models (override with SACH_<NAME>_MODELS; verify with scripts/check_llm.py)
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b"),
    ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free,google/gemma-3-27b-it:free"),
    ("mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1", "mistral-small-latest"),
)

def build_judges():
    judges = []
    for key in dict.fromkeys(_env_list("GEMINI_API_KEY", "GEMINI_API_KEYS", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3")):
        judges.append(GeminiJudge(key=key))
    for name, env, base, models in PROVIDERS:
        for key in _env_list(env):
            judges.append(OpenAICompatJudge(name, base, key, os.environ.get(f"SACH_{name.upper()}_MODELS", models)))
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            judges.append(ClaudeJudge())
        except Exception:
            pass
    return judges

def get_llm():
    judges = build_judges()
    return FailoverJudge(judges) if judges else None
