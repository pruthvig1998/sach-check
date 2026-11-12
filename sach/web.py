"""Single-container web surface (stdlib only). Run: python -m sach.web"""
from __future__ import annotations
import html, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from . import ledger
from .llm import get_llm
from .pipeline import check_forward
from .retrieve import default_retrievers

CSS = ("body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;line-height:1.5}"
       "textarea{width:100%;min-height:10rem;font-size:1rem}pre.card{background:#f4f4f4;padding:1rem;border-radius:8px;"
       "white-space:pre-wrap;font-size:1.05rem}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;"
       "padding:.4rem;text-align:left;vertical-align:top}.TRUE{color:#0a7d2c}.FALSE{color:#b00020}.MISLEADING{color:#a15c00}"
       ".UNVERIFIED{color:#555}button{font-size:1rem;padding:.5rem 1rem}")

def page(body: str) -> bytes:
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Sach</title><style>{CSS}</style><h1>Sach <small>सच · నిజం</small></h1>"
            f"<nav><a href='/'>Check a forward</a> · <a href='/?view=ledger'>Evidence ledger</a></nav>{body}").encode()

def form(prefill="") -> str:
    return ("<form method=post action=/><p>Paste a forward (English, हिन्दी, తెలుగు or Hinglish):</p>"
            f"<textarea name=text>{html.escape(prefill)}</textarea><p><button>Check</button></p></form>")

def result_html(res: dict) -> str:
    rows = "".join(f"<tr><td>{html.escape(c['claim']['text'])}</td><td class={c['verdict']}>{c['verdict']}</td>"
                   f"<td>{len(c['citations'])} citation(s)</td></tr>" for c in res["claims"])
    return (f"<h2 class={res['verdict']}>{res['verdict']}</h2><p>Copy and forward this card:</p>"
            f"<pre class=card>{html.escape(res['card'])}</pre><h3>Claims checked</h3><table>{rows}</table>")

def ledger_html() -> str:
    rows = ""
    for r in reversed(ledger.load()):
        cites = "<br>".join(f"<a href='{html.escape(c['url'])}' rel=noopener>{html.escape(c['source'])}</a> "
                            f"({c['tier']}, accessed {c['date_accessed']})" for c in r["citations"]) or "none found"
        rows += (f"<tr><td>{html.escape(r['claim'])}</td><td class={r['verdict']}>{r['verdict']}</td>"
                 f"<td>{cites}</td><td>{r['checked_at'][:10]}</td></tr>")
    return f"<h2>Public evidence ledger</h2><table><tr><th>Claim<th>Verdict<th>Citations<th>Checked</tr>{rows}</table>"

class Handler(BaseHTTPRequestHandler):
    retrievers = None
    llm = None

    def _send(self, body: bytes, code=200, ctype="text/html; charset=utf-8"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        view = parse_qs(u.query).get("view", [""])[0]
        if view == "ledger" or u.path == "/ledger":      # query form survives Vercel's rewrite; path form works locally
            self._send(page(ledger_html()))
        elif view == "health" or u.path == "/healthz":
            self._send(b"ok", ctype="text/plain")
        else:
            self._send(page(form()))

    def do_POST(self):
        # single POST route: accept any path (Vercel rewrites hide the original one)
        n = min(int(self.headers.get("Content-Length", 0)), 20000)
        text = parse_qs(self.rfile.read(n).decode("utf-8", "replace")).get("text", [""])[0].strip()
        if not text:
            return self._send(page(form() + "<p>Please paste some text.</p>"), 400)
        if Handler.retrievers is None:
            Handler.retrievers, Handler.llm = default_retrievers(), get_llm()   # lazy: serverless has no main()
        res = check_forward(text, Handler.retrievers, Handler.llm)
        self._send(page(result_html(res) + form(text)))

def main():
    Handler.retrievers, Handler.llm = default_retrievers(), get_llm()
    port = int(os.environ.get("PORT", 8080))
    print(f"Sach on :{port} (llm={'on' if Handler.llm else 'off'})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

if __name__ == "__main__":
    main()
