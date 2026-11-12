"""Telegram bot: everything offline (fake send, fake pipeline, injected opener)."""
import importlib.util, io, json, pathlib, threading, urllib.request as ur, urllib.error as ue
from http.server import ThreadingHTTPServer
import pytest
import sach.telegram_bot as T
import sach.web as W
from sach import store

TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"[:35]
SECRET = "s3cr3t_" + "x" * 20
URL = "https://pib.gov.in/PressReleasePage.aspx?PRID=1"

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    T._hits.clear(); store.reset()

class Sent(list):
    def __call__(self, method, payload):
        self.append((method, payload)); return True
    def texts(self): return [p["text"] for m, p in self if m == "sendMessage"]

def result(card="\U0001F534 FALSE\nNot true.\nSource: PIB - " + URL, lang="en", **kw):
    r = {"verdict": "FALSE", "card": card, "language": lang, "claims": []}
    r.update(kw); return r

@pytest.fixture
def fake_check(monkeypatch):
    calls = []
    def f(text, retrievers, llm, reply_lang=None, **k):
        calls.append((text, reply_lang)); return result()
    monkeypatch.setattr(T, "check_forward", f); return calls

def msg(text="hello there claim", chat=1, ctype="private", uid=1, **kw):
    m = {"message_id": 7, "chat": {"id": chat, "type": ctype}, "from": {"id": 5, "is_bot": False}, "text": text}
    m.update(kw); return {"update_id": uid, "message": m}

def run(update, send=None):
    send = Sent() if send is None else send
    return T.handle_update(update, [], None, send=send), send

# ---- commands
@pytest.mark.parametrize("c", ["/start", "/help", "/start@SachBot"])
def test_start_help(c, fake_check):
    r, s = run(msg(c))
    t = s.texts()[0]
    assert "UNVERIFIED does not mean false" in t and "not a government service" in t and "हिंदी" in t and "తెలుగు" in t and "private data" in t
    assert not fake_check

def test_lang_valid_persists_and_is_used(fake_check):
    r, s = run(msg("/lang hi", uid=1)); assert "Hindi" in s.texts()[0]
    assert store.get_store().get("tg:lang:1") == "hi"
    run(msg("some claim text", uid=2)); assert fake_check[-1][1] == "hi"
    run(msg("/lang auto", uid=3)); run(msg("another claim", uid=4)); assert fake_check[-1][1] is None

def test_lang_invalid_shows_usage(fake_check):
    r, s = run(msg("/lang klingon")); assert "/lang en" in s.texts()[0]
    assert store.get_store().get("tg:lang:1") is None

def test_lang_store_failure_falls_back_to_auto(monkeypatch, fake_check):
    class Bad:
        def get(self, k): raise RuntimeError("down")
        def set(self, *a, **k): raise RuntimeError("down")
    monkeypatch.setattr(store, "get_store", lambda: Bad())
    r, s = run(msg("/lang te")); assert "could not remember" in s.texts()[0]
    r, s = run(msg("a claim here", uid=2)); assert fake_check[-1][1] is None and r["action"] == "checked"

# ---- checks
def test_private_check_sends_card_plain_text_no_parse_mode(fake_check):
    r, s = run(msg("Rs 5000 for every woman"))
    assert r["action"] == "checked" and fake_check == [("Rs 5000 for every woman", None)]
    assert s[0][0] == "sendChatAction" and s[0][1]["action"] == "typing"
    m, p = s[1]; assert m == "sendMessage" and "FALSE" in p["text"] and URL in p["text"]
    assert "parse_mode" not in p and p["link_preview_options"] == {"is_disabled": True}

def test_non_english_adds_english_meaning_and_more_sources(monkeypatch):
    monkeypatch.setattr(T, "check_forward", lambda *a, **k: result("hi card " + URL, "hi", card_en="en card " + URL,
        claims=[{"citations": [{"source": "WHO", "url": "https://who.int/a"}, {"source": "PIB", "url": URL}]}]))
    r, s = run(msg("x claim"))
    t = s.texts()[0]; assert "hi card" in t and "In English:\nen card" in t and "WHO: https://who.int/a" in t
    assert t.count(URL) == 2    # card + english card, not repeated as "more sources"

def test_forwarded_caption_is_checked(fake_check):
    u = msg(); del u["message"]["text"]; u["message"]["caption"] = "forwarded caption claim"
    run(u); assert fake_check[0][0] == "forwarded caption claim"

@pytest.mark.parametrize("key", ["photo", "sticker", "voice"])
def test_non_text_friendly(key, fake_check):
    u = msg(); del u["message"]["text"]; u["message"][key] = {}
    r, s = run(u); assert "only read text" in s.texts()[0] and not fake_check

def test_too_long(fake_check):
    r, s = run(msg("a" * (T.MAX_CHARS + 1))); assert "too long" in s.texts()[0] and not fake_check

def test_long_reply_split_under_limit_and_urls_intact(monkeypatch):
    lines = [f"line {i} https://example.org/{'p' * 150}/{i}" for i in range(80)]
    monkeypatch.setattr(T, "check_forward", lambda *a, **k: result("\n".join(lines)))
    r, s = run(msg("claim text"))
    ts = s.texts(); assert len(ts) > 1 and all(0 < len(t) <= 4096 for t in ts)
    assert "\n".join(ts).split("\n") == lines
    giant = "w " * 5000 + "https://x.org/" + "q" * 300
    pieces = T.split_message(giant); assert all(len(p) <= T.CHUNK for p in pieces) and any("https://x.org/" + "q" * 300 in p for p in pieces)

def test_hostile_text_verbatim_plain(monkeypatch):
    hostile = "<b>bold</b> *x* _y_ [x](http://evil) `code` &amp;"
    seen = []
    monkeypatch.setattr(T, "check_forward", lambda text, *a, **k: seen.append(text) or result(hostile))
    r, s = run(msg("claim " + hostile))
    assert seen[0].endswith(hostile) and s.texts()[0].startswith(hostile)
    assert all("parse_mode" not in p for m, p in s)

# ---- groups / bots
def test_group_ignored_unless_addressed(fake_check):
    r, s = run(msg("random chatter", ctype="group")); assert r["ignored"] == "group" and not s and not fake_check
    r, s = run(msg("/check Rs 5 scheme", ctype="supergroup", uid=2)); assert r["action"] == "checked" and fake_check[-1][0] == "Rs 5 scheme"
    assert [p for m, p in s if m == "sendMessage"][0]["reply_parameters"]["message_id"] == 7

def test_group_reply_to_bot_and_mention(monkeypatch, fake_check):
    u = msg("is this true", ctype="group", uid=3, reply_to_message={"from": {"id": 123456789}})
    assert run(u)[0]["action"] == "checked"
    u = msg("@SachBot is this true", ctype="group", uid=4, entities=[{"type": "mention", "offset": 0, "length": 8}])
    assert run(u)[0]["ignored"] == "group"                    # username unknown: not provably us
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "SachBot")
    r, s = run(u); assert r["action"] == "checked" and fake_check[-1][0] == "is this true"
    assert run(msg("/check@OtherBot x", ctype="group", uid=5))[0]["ignored"] == "other bot"

def test_check_command_replying_to_a_forward(fake_check):
    u = msg("/check", ctype="group", reply_to_message={"text": "forwarded claim body", "from": {"id": 9}})
    run(u); assert fake_check[0][0] == "forwarded claim body"

def test_bot_messages_and_edits_ignored(fake_check):
    u = msg(); u["message"]["from"]["is_bot"] = True
    assert run(u)[0]["ignored"] == "bot"
    e = {"update_id": 9, "edited_message": msg()["message"]}
    r, s = run(e); assert r["ignored"] == "edit" and not s and not fake_check

# ---- limits / idempotency / errors
def test_rate_limit_and_single_warning(fake_check):
    s = Sent()
    for i in range(6): T.handle_update(msg(f"claim {i}", uid=100 + i), [], None, send=s)
    assert len(fake_check) == 6
    for i in range(3): T.handle_update(msg(f"more {i}", uid=200 + i), [], None, send=s)
    assert len(fake_check) == 6 and sum("quickly" in t for t in s.texts()) == 1
    assert run(msg("other chat", chat=2, uid=300))[0]["action"] == "checked"

def test_duplicate_update_id_processed_once(fake_check):
    run(msg(uid=55)); r, s = run(msg(uid=55))
    assert len(fake_check) == 1 and r["ignored"] == "duplicate" and not s

def test_store_failure_still_processes(monkeypatch, fake_check):
    monkeypatch.setattr(store, "get_store", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert run(msg(uid=1))[0]["action"] == "checked"

def test_exceptions_never_escape(monkeypatch, capsys):
    def boom(*a, **k): raise RuntimeError(TOKEN)
    monkeypatch.setattr(T, "check_forward", boom)
    r, s = run(msg("claim"))
    assert r == {"ok": True, "error": True} and "Sorry" in s.texts()[0]
    assert TOKEN not in capsys.readouterr().out
    class Dead(Sent):
        def __call__(self, *a): raise OSError("net")
    assert T.handle_update(msg(uid=9), [], None, send=Dead())["ok"] is True
    assert T.handle_update("garbage", [], None, send=Sent())["ok"] is True
    assert T.handle_update({"message": {"chat": 5}}, [], None, send=Sent())["ok"] is True

# ---- client
class Resp:
    def __init__(self, body): self.b = body
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False

def test_client_builds_url_and_json():
    seen = {}
    def op(req, timeout=None):
        seen.update(url=req.full_url, body=json.loads(req.data), t=timeout, ct=req.get_header("Content-type")); return Resp(b'{"ok":true,"result":{"a":1}}')
    c = T.TelegramClient(TOKEN, op)
    assert c.send_message(5, "hi", link_preview_options={"is_disabled": True}) == {"a": 1}
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage" and seen["t"] == 10
    assert seen["body"] == {"chat_id": 5, "text": "hi", "link_preview_options": {"is_disabled": True}} and seen["ct"] == "application/json"
    c.set_webhook("https://x/?api=tg-webhook", SECRET, allowed_updates=["message"]); assert seen["url"].endswith("/setWebhook") and seen["body"]["secret_token"] == SECRET
    c.send_chat_action(5); assert seen["body"]["action"] == "typing"
    c.delete_webhook(); c.get_webhook_info()

def test_client_failure_returns_none_and_redacts():
    def op(req, timeout=None): raise ue.URLError(f"failed {req.full_url}")
    c = T.TelegramClient(TOKEN, op)
    assert c.call("sendMessage", {}) is None and TOKEN not in c.last_error
    def op2(req, timeout=None): raise ue.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b'{"ok":false,"error_code":401,"description":"Unauthorized"}'))
    c = T.TelegramClient(TOKEN, op2); assert c.call("x") is None and "Unauthorized" in c.last_error and TOKEN not in c.last_error
    c = T.TelegramClient(TOKEN, lambda r, timeout=None: Resp(b'{"ok":false,"error_code":400}')); assert c.call("x") is None

@pytest.mark.parametrize("tok,sec,ok", [(TOKEN, SECRET, True), ("bad", SECRET, False), (TOKEN, "short", False), (TOKEN, "a b" * 8, False), ("", "", False)])
def test_config_validation(monkeypatch, tok, sec, ok):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", tok); monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", sec)
    assert T.enabled() is ok

# ---- HTTP route
@pytest.fixture
def server(monkeypatch):
    W._hits.clear(); W.Handler.retrievers = []; W.Handler.llm = None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()

def hook(base, body, secret=None, path="/?api=tg-webhook"):
    h = {"Content-Type": "application/json"}
    if secret is not None: h[T.SECRET_HEADER] = secret
    try:
        r = ur.urlopen(ur.Request(base + path, body if isinstance(body, bytes) else json.dumps(body).encode(), h)); return r.status, r.read().decode()
    except ue.HTTPError as e:
        return e.code, e.read().decode()

def test_route_503_when_unconfigured(server, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert hook(server, msg(), SECRET)[0] == 503

@pytest.mark.parametrize("sec", [None, "", "wrong", SECRET[:-1], SECRET + "x", SECRET.upper()])
def test_route_403_bad_secret(server, sec):
    code, body = hook(server, msg(), sec)
    assert code == 403 and SECRET not in body and TOKEN not in body

def test_route_200_valid_update_uses_fake_client(server, monkeypatch, fake_check):
    s = Sent()
    monkeypatch.setattr(T, "client_from_env", lambda opener=None: type("C", (), {"call": s})())
    code, body = hook(server, msg("a claim"), SECRET)
    assert code == 200 and json.loads(body) == {"ok": True} and fake_check and s.texts()
    assert hook(server, b"{not json", SECRET)[0] == 400
    assert hook(server, b"x" * (T.MAX_UPDATE_BYTES + 1), SECRET)[0] == 413

def test_route_200_even_when_pipeline_explodes(server, monkeypatch, capsys):
    s = Sent()
    monkeypatch.setattr(T, "client_from_env", lambda opener=None: type("C", (), {"call": s})())
    monkeypatch.setattr(T, "check_forward", lambda *a, **k: 1 / 0)
    code, body = hook(server, msg("claim"), SECRET)
    assert code == 200 and TOKEN not in body and TOKEN not in capsys.readouterr().out and "Sorry" in s.texts()[0]

# ---- script
def load_script():
    p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "set_telegram_webhook.py"
    spec = importlib.util.spec_from_file_location("set_tg", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

class FakeClient(T.TelegramClient):
    def __init__(self, ret): super().__init__(TOKEN); self.ret, self.calls = ret, []
    def call(self, method, payload=None): self.calls.append((method, payload)); return self.ret

def test_script_info_redacts_everything():
    lines = []
    c = FakeClient({"url": f"https://h/?x={TOKEN}&s={SECRET}", "pending_update_count": 0})
    assert load_script().run(["--info"], client=c, out=lines.append) == 0
    o = "\n".join(lines); assert TOKEN not in o and SECRET not in o and "pending_update_count" in o and "[redacted]" in o

def test_script_set_and_delete():
    m, lines = load_script(), []
    c = FakeClient(True)
    assert m.run([], client=c, out=lines.append) == 0
    meth, p = c.calls[0]
    assert meth == "setWebhook" and p == {"url": "https://sach-check-lilac.vercel.app/?api=tg-webhook", "secret_token": SECRET,
                                          "allowed_updates": ["message"], "drop_pending_updates": True}
    assert m.run(["--delete"], client=c, out=lines.append) == 0 and c.calls[1][0] == "deleteWebhook"
    assert SECRET not in "\n".join(lines) and TOKEN not in "\n".join(lines)
    assert m.run(["--url", "http://insecure"], client=c, out=lines.append) == 2

def test_script_failure_and_missing_env(monkeypatch):
    m, lines = load_script(), []
    c = FakeClient(None); c.last_error = f"boom {TOKEN}"
    assert m.run([], client=c, out=lines.append) == 1 and TOKEN not in "\n".join(lines)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert m.run([], client=FakeClient(True), out=lines.append) == 2
