"""Single-container web surface (stdlib only). Run: python -m sach.web"""
from __future__ import annotations
import json, os, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from .llm import get_llm
from .pipeline import check_forward
from .retrieve import default_retrievers
from .site import MAX_CHARS, REPLY_LANGS, home, ledger_page, result_block

RATE_LIMIT, RATE_WINDOW = 8, 60          # best-effort per-IP checks per minute (serverless instances don't share state)
_hits: dict = {}
_hits_lock = threading.Lock()

def rate_limited(ip: str) -> bool:
    now = time.time()
    with _hits_lock:
        q = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
        limited = len(q) >= RATE_LIMIT
        if not limited:
            q.append(now)
        _hits[ip] = q
        if len(_hits) > 2000:            # bound memory
            _hits.clear()
    return limited

class Handler(BaseHTTPRequestHandler):
    retrievers = None
    llm = None

    def log_message(self, *a):           # keep serverless logs quiet
        pass

    def _send(self, body: bytes, code=200, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store" if code != 200 or self.command == "POST" else "public, max-age=60")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(), code, "application/json; charset=utf-8")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        view = parse_qs(u.query).get("view", [""])[0]
        if view == "ledger" or u.path == "/ledger":      # query form survives Vercel's rewrite; path form works locally
            self._send(ledger_page())
        elif view == "health" or u.path == "/healthz":
            self._send(b"ok", ctype="text/plain")
        else:
            self._send(home())

    def _client_ip(self):
        return (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()

    def do_POST(self):
        # single POST route: accept any path (Vercel rewrites hide the original one)
        text, lang_choice = "", "auto"
        want_json = "json" in (parse_qs(urlparse(self.path).query).get("format", [""])[0]) or \
                    "application/json" in (self.headers.get("Accept") or "")
        fail = (lambda code, msg: self._json({"error": msg}, code)) if want_json else \
               (lambda code, msg: self._send(home(prefill=text, error=msg, reply=lang_choice), code))
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        raw = self.rfile.read(min(n, MAX_CHARS * 8)).decode("utf-8", "replace")
        if "application/json" in (self.headers.get("Content-Type") or ""):
            try:
                body = json.loads(raw)
                text, lang_choice = str(body.get("text", "")), str(body.get("lang") or "")
            except Exception:
                text = ""
        else:
            form = parse_qs(raw)
            text, lang_choice = form.get("text", [""])[0], form.get("lang", [""])[0]
        lang_choice = (lang_choice or parse_qs(urlparse(self.path).query).get("lang", [""])[0] or "auto").strip().lower()
        if lang_choice not in REPLY_LANGS:
            lang_choice = "auto"                      # unknown value: match the forward, never error
        text = text.strip()
        if not text:
            return fail(400, "Please paste a message to check.")
        if len(text) > MAX_CHARS:
            return fail(413, f"That message is too long. Please keep it under {MAX_CHARS} characters, or paste the key claim.")
        if rate_limited(self._client_ip()):
            return fail(429, "You're checking quickly. Please wait a minute and try again.")
        if Handler.retrievers is None:
            Handler.retrievers, Handler.llm = default_retrievers(), get_llm()   # lazy: serverless has no main()
        try:
            res = check_forward(text, Handler.retrievers, Handler.llm, reply_lang=None if lang_choice == "auto" else lang_choice)
        except Exception:
            return fail(500, "Something went wrong while checking. Nothing was recorded. Please try again.")
        if want_json:
            return self._json(res)
        self._send(home(result=result_block(res, chosen=lang_choice != "auto"), prefill=text, reply=lang_choice))

def main():
    Handler.retrievers, Handler.llm = default_retrievers(), get_llm()
    port = int(os.environ.get("PORT", 8080))
    print(f"Sach on :{port} (llm={'on' if Handler.llm else 'off'})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

if __name__ == "__main__":
    main()
