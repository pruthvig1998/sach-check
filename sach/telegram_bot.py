"""Telegram bot front door for Sach (stdlib only, $0: Telegram's Bot API is free).

Who calls it: sach/web.py (POST /?api=tg-webhook) and scripts/set_telegram_webhook.py.
Env: TELEGRAM_BOT_TOKEN (from @BotFather), TELEGRAM_WEBHOOK_SECRET (random string you choose; Telegram echoes it in the
X-Telegram-Bot-Api-Secret-Token header). Optional TELEGRAM_BOT_USERNAME (without @) so "@yourbot" mentions work in groups.

Slow checks are done INLINE (sendChatAction, run pipeline, sendMessage, then HTTP 200): on Vercel the function is frozen
once the response is sent, so a background thread is not safe. update_ids are remembered so Telegram's retries are no-ops.
The bot token lives only in the request URL path inside TelegramClient and is never logged, printed or put in an exception.
"""
from __future__ import annotations
import hmac, json, os, re, threading, time
from urllib.request import Request, urlopen
from . import store as _store
from . import pipeline as _pipeline
from .site import MAX_CHARS, REPLY_LANGS
from .lang import NAMES, SUPPORTED

API = "https://api.telegram.org"
MAX_UPDATE_BYTES = 256 * 1024
TG_LIMIT = 4096
CHUNK = 4000                                   # a little under Telegram's 4096 limit
CHECKS_PER_MIN, WINDOW_S = 6, 60
LANG_TTL_S, SEEN_TTL_S = 365 * 24 * 3600, 3600
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_TOKEN = re.compile(r"^\d{5,16}:[A-Za-z0-9_-]{35,}$")
_SECRET = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
LANG_NAMES = dict(NAMES)
LANG_CODES = ", ".join(f"{c} {NAMES[c].split(' (')[0]}" for c in SUPPORTED)      # "en English, hi Hindi, bn Bengali, ..."

def check_forward(*a, **k):                    # indirection so tests can swap it; pipeline.py itself is untouched
    return _pipeline.check_forward(*a, **k)

# ---------------------------------------------------------------- config / redaction
def config():
    """(token, secret) when both are set and well-formed, else None."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    secret = (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if _TOKEN.match(token) and _SECRET.match(secret):
        return token, secret
    return None

def enabled() -> bool:
    return config() is not None

def redact(text, *secrets) -> str:
    s = str(text)
    for x in secrets:
        if x:
            s = s.replace(x, "[redacted]")
    s = re.sub(r"/bot\d+:[A-Za-z0-9_-]+", "/bot[redacted]", s)
    return re.sub(r"\b\d{5,16}:[A-Za-z0-9_-]{35,}\b", "[redacted]", s)

def verify_secret(header_value) -> bool:
    cfg = config()
    if not cfg or not isinstance(header_value, str):
        return False
    return hmac.compare_digest(header_value.encode("utf-8", "replace"), cfg[1].encode())

# ---------------------------------------------------------------- Bot API client
class TelegramClient:
    """POST JSON to https://api.telegram.org/bot<token>/<method>. Returns the `result` (or True) or None on any error.
    The URL (which holds the token) is never put in a message, log or exception. `last_error` is redacted."""
    def __init__(self, token: str, opener=None):
        self._token, self._open, self.last_error = token, opener or urlopen, ""

    def call(self, method: str, payload: dict | None = None):
        self.last_error = ""
        try:
            req = Request(f"{API}/bot{self._token}/{method}", data=json.dumps(payload or {}).encode(), method="POST",
                          headers={"Content-Type": "application/json", "User-Agent": "sach-check"})
            with self._open(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            detail = ""
            try:                                    # HTTPError carries Telegram's JSON error body
                body = json.loads(e.read().decode("utf-8", "replace"))
                detail = f" {body.get('error_code', '')} {body.get('description', '')}".rstrip()
            except Exception:
                pass
            self.last_error = redact(f"{type(e).__name__}{detail}", self._token)
            return None
        if not isinstance(data, dict) or not data.get("ok"):
            self.last_error = redact(f"telegram error {data.get('error_code', '') if isinstance(data, dict) else ''}", self._token)
            return None
        res = data.get("result")
        return True if res is None else res

    def send_message(self, chat_id, text, **extra):
        return self.call("sendMessage", {"chat_id": chat_id, "text": text, **extra})
    def send_chat_action(self, chat_id, action="typing"):
        return self.call("sendChatAction", {"chat_id": chat_id, "action": action})
    def set_webhook(self, url, secret, **extra):
        return self.call("setWebhook", {"url": url, "secret_token": secret, **extra})
    def delete_webhook(self, drop_pending_updates=False):
        return self.call("deleteWebhook", {"drop_pending_updates": bool(drop_pending_updates)})
    def get_webhook_info(self):
        return self.call("getWebhookInfo", {})

def client_from_env(opener=None):
    cfg = config()
    return TelegramClient(cfg[0], opener) if cfg else None

# ---------------------------------------------------------------- texts
WELCOME = (
    "Namaste! I am Sach, a free fact-checker for forwarded messages.\n\n"
    "How to use me: forward or paste a message here. I look for official sources (PIB, government sites, WHO) and reply "
    "with a verdict and links: TRUE, FALSE, MISLEADING or UNVERIFIED.\n\n"
    "UNVERIFIED does not mean false. It means I could not find a clear official answer.\n"
    "Sach is not a government service. Please do not send private data such as OTPs, bank details or Aadhaar numbers.\n\n"
    "Reply language: /lang auto (match the message), or /lang with a code: " + LANG_CODES + ".\n\n"
    "हिंदी: कोई भी फ़ॉरवर्ड यहाँ भेजें, मैं स्रोत के साथ जाँच बताऊँगा। भाषा बदलने के लिए /lang hi\n"
    "తెలుగు: ఏదైనా ఫార్వర్డ్ ఇక్కడ పంపండి, నేను ఆధారాలతో తనిఖీ చేస్తాను. భాష మార్చడానికి /lang te")
NOT_TEXT = "I can only read text for now. Please paste or forward the message as text."
TOO_LONG = f"That message is too long. Please keep it under {MAX_CHARS} characters, or send just the key claim."
SLOW_DOWN = "You are checking quickly. Please wait a minute and try again."
APOLOGY = "Sorry, something went wrong while checking. Nothing was recorded. Please try again in a minute."
EMPTY_CHECK = "Send me the message to check, or reply to it with /check."

# ---------------------------------------------------------------- helpers
_hits: dict = {}
_hits_lock = threading.Lock()

def _rate(chat_id) -> str:
    """'ok' | 'warn' (first refusal in the window: say slow down) | 'quiet' (already warned)."""
    now = time.time()
    with _hits_lock:
        st = _hits.get(chat_id) or {"t": [], "warned": 0.0}
        st["t"] = [t for t in st["t"] if now - t < WINDOW_S]
        if len(st["t"]) < CHECKS_PER_MIN:
            st["t"].append(now); st["warned"] = 0.0; res = "ok"
        elif now - st["warned"] >= WINDOW_S:
            st["warned"] = now; res = "warn"
        else:
            res = "quiet"
        _hits[chat_id] = st
        if len(_hits) > 5000:
            _hits.clear()
    return res

def split_message(text: str, limit: int = CHUNK) -> list:
    """Split at line boundaries (then spaces) so no URL is cut; every piece is <= limit and non-empty."""
    out, cur = [], ""
    def flush():
        nonlocal cur
        if cur.strip():
            out.append(cur.rstrip("\n"))
        cur = ""
    for line in text.split("\n"):
        while len(line) > limit:                       # one huge line: break on a space, hard cut only as a last resort
            cut = line.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            flush(); out.append(line[:cut]); line = line[cut:].lstrip(" ")
        if len(cur) + len(line) + 1 > limit:
            flush()
        cur += line + "\n"
    flush()
    return out or [text[:limit] or "."]

def format_reply(res: dict) -> str:
    card = str(res.get("card") or "").strip()
    parts = [card]
    if res.get("card_en") and res.get("language") != "en":
        parts.append("In English:\n" + str(res["card_en"]).strip())
    seen = set(re.findall(r"https?://\S+", "\n".join(parts)))
    more = []
    for c in res.get("claims") or []:
        for x in (c.get("citations") or [])[:3]:
            u = str(x.get("url") or "")
            if u.startswith(("http://", "https://")) and u not in seen and len(more) < 4:
                seen.add(u); more.append(f"- {x.get('source', 'Source')}: {u}")
    if more:
        parts.append("More sources:\n" + "\n".join(more))
    if res.get("degraded"):
        parts.append("Note: my AI checker is busy, so I only report a verdict when an official debunk clearly matches.")
    return "\n\n".join(p for p in parts if p)

def _lang_get(chat_id):
    try:
        v = _store.get_store().get(f"tg:lang:{chat_id}")
        return v if v in REPLY_LANGS and v != "auto" else None
    except Exception:
        return None

def _lang_set(chat_id, lang) -> bool:
    try:
        _store.get_store().set(f"tg:lang:{chat_id}", lang, LANG_TTL_S)
        return _store.get_store().get(f"tg:lang:{chat_id}") == lang
    except Exception:
        return False

def _seen_before(update_id) -> bool:
    if not isinstance(update_id, int):
        return False
    try:
        st, key = _store.get_store(), f"tg:seen:{update_id}"
        if st.get(key):
            return True
        st.set(key, 1, SEEN_TTL_S)
    except Exception:
        pass
    return False

def _bot_id():
    cfg = config()
    return int(cfg[0].split(":")[0]) if cfg else None

def _addressed(msg: dict, text: str, bot_id, username: str) -> bool:
    """Group chats: only a reply to one of the bot's messages, or an @mention of it."""
    rf = (msg.get("reply_to_message") or {}).get("from") or {}
    if bot_id is not None and rf.get("id") == bot_id:
        return True
    for e in (msg.get("entities") or msg.get("caption_entities") or []):
        if e.get("type") == "text_mention" and bot_id is not None and (e.get("user") or {}).get("id") == bot_id:
            return True
        if e.get("type") == "mention" and username:
            seg = text[e.get("offset", 0): e.get("offset", 0) + e.get("length", 0)]
            if seg.lower() == "@" + username.lower():
                return True
    return False

def _parse_command(text: str):
    """('check', 'rest of line') for '/check@Bot rest'; (None, text) when it is not a command."""
    m = re.match(r"^/(\w+)(?:@(\w+))?(?:\s+(.*))?$", text, re.S)
    return (m.group(1).lower(), (m.group(3) or "").strip(), m.group(2)) if m else (None, text, None)

# ---------------------------------------------------------------- the handler
def handle_update(update: dict, retrievers, llm, send=None, bot_id=None, username=None) -> dict:
    """Pure-ish: `send(method, payload)` does the I/O. Never raises; always returns {'ok': True, ...}."""
    chat_id = None
    try:
        if not isinstance(update, dict):
            return {"ok": True, "ignored": "bad update"}
        if "message" not in update:
            return {"ok": True, "ignored": "edit" if "edited_message" in update else "type"}
        msg = update["message"]
        if not isinstance(msg, dict) or not isinstance(msg.get("chat"), dict):
            return {"ok": True, "ignored": "bad message"}
        chat_id = msg["chat"].get("id")
        if (msg.get("from") or {}).get("is_bot") or chat_id is None:
            return {"ok": True, "ignored": "bot"}
        if send is None:
            c = client_from_env()
            if c is None:
                return {"ok": True, "ignored": "not configured"}
            send = c.call
        bot_id = bot_id if bot_id is not None else _bot_id()
        username = (username if username is not None else os.environ.get("TELEGRAM_BOT_USERNAME", "")).strip().lstrip("@")
        private = msg["chat"].get("type") == "private"
        text = msg.get("text") if isinstance(msg.get("text"), str) else (msg.get("caption") if isinstance(msg.get("caption"), str) else "")
        text = text.strip()
        cmd, rest, target = _parse_command(text) if text else (None, "", None)
        if cmd and target and username and target.lower() != username.lower():
            return {"ok": True, "ignored": "other bot"}
        if not private and cmd not in ("check", "start", "help", "lang") and not _addressed(msg, text, bot_id, username):
            return {"ok": True, "ignored": "group"}
        if _seen_before(update.get("update_id")):
            return {"ok": True, "ignored": "duplicate"}

        def say(t, **extra):
            opts = {"link_preview_options": {"is_disabled": True}, **extra}      # plain text, no parse_mode, no previews
            if not private and msg.get("message_id") is not None:
                opts["reply_parameters"] = {"message_id": msg["message_id"], "allow_sending_without_reply": True}
            for piece in split_message(t):
                send("sendMessage", {"chat_id": chat_id, "text": piece, **opts})

        if cmd in ("start", "help"):
            say(WELCOME); return {"ok": True, "action": "help"}
        if cmd == "lang":
            arg = rest.split()[0].lower() if rest.split() else ""
            if arg not in REPLY_LANGS:
                cur = _lang_get(chat_id)
                say("Choose the reply language, for example /lang en or /lang auto (match the message).\n"
                    f"Codes: {LANG_CODES}.\n"
                    f"Now: {LANG_NAMES.get(cur, 'auto (matches the message)')}.")
                return {"ok": True, "action": "lang-usage"}
            saved = _lang_set(chat_id, arg)
            name = "auto (matches the message)" if arg == "auto" else LANG_NAMES[arg]
            say(f"Reply language: {name}." + ("" if saved else " (I could not remember this choice, so I will match each message for now.)"))
            return {"ok": True, "action": "lang", "lang": arg}
        if cmd is not None and cmd != "check":
            if private:
                say(WELCOME)
            return {"ok": True, "action": "help"}
        # a check: '/check text', '/check' replying to a message, or any plain text
        claim = rest if cmd == "check" else text
        if username and cmd is None:
            claim = re.sub(r"(?i)@" + re.escape(username) + r"\b", "", claim).strip()
        if cmd == "check" and not claim:
            rt = msg.get("reply_to_message") or {}
            claim = (rt.get("text") or rt.get("caption") or "").strip() if isinstance(rt, dict) else ""
        if not claim:
            say(EMPTY_CHECK if cmd == "check" else NOT_TEXT); return {"ok": True, "action": "no-text"}
        if len(claim) > MAX_CHARS:
            say(TOO_LONG); return {"ok": True, "action": "too-long"}
        r = _rate(chat_id)
        if r != "ok":
            if r == "warn":
                say(SLOW_DOWN)
            return {"ok": True, "action": "rate-limited"}
        send("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        lang = _lang_get(chat_id)
        res = check_forward(claim, retrievers, llm, reply_lang=lang)
        say(format_reply(res))
        return {"ok": True, "action": "checked", "verdict": res.get("verdict")}
    except Exception as e:                                     # never reach the HTTP layer; Telegram would retry forever
        print(f"telegram-bot error={type(e).__name__}", flush=True)
        try:
            if chat_id is not None and send is not None:
                send("sendMessage", {"chat_id": chat_id, "text": APOLOGY})
        except Exception:
            pass
        return {"ok": True, "error": True}

# ---------------------------------------------------------------- HTTP glue (called from sach/web.py)
def webhook_http(headers, raw_len: int, read_body, get_deps, send=None):
    """-> (status, json-able). `read_body(n)` returns bytes; `get_deps()` returns (retrievers, llm) lazily."""
    if not enabled():
        return 503, {"error": "telegram bot not configured"}
    if not verify_secret(headers.get(SECRET_HEADER)):
        return 403, {"error": "forbidden"}
    if raw_len <= 0 or raw_len > MAX_UPDATE_BYTES:
        return 413, {"error": "bad size"}
    try:
        update = json.loads(read_body(raw_len).decode("utf-8", "replace"))
    except Exception:
        return 400, {"error": "bad json"}
    try:
        retrievers, llm = get_deps()
    except Exception:
        retrievers, llm = [], None
    handle_update(update, retrievers, llm, send=send)
    return 200, {"ok": True}
