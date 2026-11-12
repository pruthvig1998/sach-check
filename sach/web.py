"""Single-container web surface (stdlib only). Run: python -m sach.web"""
from __future__ import annotations
import html, json, os, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from .llm import get_llm
from .pipeline import check_forward
from .scamsigns import analyze as scam_signs
from .retrieve import default_retrievers
from . import razorpay_pay as rzp
from . import telegram_bot as tg
from . import ocr
from . import pwa, share
from . import siteurl
from .legal import PAGES as LEGAL_PAGES, legal_page
from .site import MAX_CHARS, REPLY_LANGS, UPI_APPS, home, ledger_page, pay_page, result_block, tip_amount, tip_config, tip_qr_png, tip_qr_svg, upi_link

RATE_LIMIT, RATE_WINDOW = 8, 60          # best-effort per-IP checks per minute (serverless instances don't share state)
_hits: dict = {}
_hits_lock = threading.Lock()

TIP_ORDER_LIMIT, TIP_VERIFY_LIMIT = 6, 20      # tips have their own buckets so tipping never eats a person's fact-check allowance

def rate_limited(ip: str, kind: str = "check", limit: int = RATE_LIMIT) -> bool:
    now, key = time.time(), f"{kind}:{ip}"
    with _hits_lock:
        q = [t for t in _hits.get(key, []) if now - t < RATE_WINDOW]
        limited = len(q) >= limit
        if not limited:
            q.append(now)
        _hits[key] = q
        if len(_hits) > 2000:            # bound memory
            _hits.clear()
    return limited

class Handler(BaseHTTPRequestHandler):
    retrievers = None
    llm = None

    def log_message(self, *a):           # keep serverless logs quiet
        pass

    def _send(self, body: bytes, code=200, ctype="text/html; charset=utf-8", cache=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", cache or ("no-store" if code != 200 or self.command == "POST" else "public, max-age=60"))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(), code, "application/json; charset=utf-8")

    def _redirect_home_tip(self):
        self.send_response(302)
        self.send_header("Location", "/#tip")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        siteurl.bind(self)                                 # the request's Host header, for canonical links and report text
        try:
            return self._get()
        finally:
            siteurl.unbind()

    def _robots(self):
        site = siteurl.site_url(self)
        body = ("User-agent: *\nAllow: /\nDisallow: /?api=\nDisallow: /?go=\nDisallow: /?view=pay\nDisallow: /?view=tipqr\nDisallow: /?r=\n"
                f"Sitemap: {site}/sitemap.xml\n")
        self._send(body.encode(), ctype="text/plain; charset=utf-8")

    def _sitemap(self):
        site = siteurl.site_url(self)
        paths = ["/", "/impact", "/?view=ledger"] + [f"/?view={slug}" for slug in LEGAL_PAGES]
        urls = "".join(f"<url><loc>{html.escape(site + p)}</loc></url>" for p in paths)
        body = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
        self._send(body.encode(), ctype="application/xml; charset=utf-8")

    def _get(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        view = qs.get("view", [""])[0]
        if qs.get("go", [""])[0] == "tip":                 # tip buttons: the UPI address lives only in this redirect, never in page HTML
            cfg = tip_config()
            if not cfg:
                return self._send(b"not found", 404, "text/plain")
            if not cfg.get("merchant"):                      # NPCI OC-76A: link payments to a personal UPI ID are always rejected
                return self._redirect_home_tip()
            self.send_response(302)
            app = qs.get("app", ["upi"])[0].lower()
            app = app if app in UPI_APPS else "upi"          # unknown app name: generic scheme, never an error
            self.send_header("Location", upi_link(cfg, tip_amount(qs.get("amt", [""])[0]), "Sach tip", app=app, alt=qs.get("alt", [""])[0] == "1"))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if view == "pay":                                    # choose your UPI app (avoids iOS picking WhatsApp for you)
            cfg = tip_config()
            if not cfg:
                return self._send(b"not found", 404, "text/plain")
            if not cfg.get("merchant"):
                return self._redirect_home_tip()
            raw_amt = qs.get("amt", [""])[0]
            amt = tip_amount(raw_amt)
            return self._send(pay_page(amt, bad_amount=bool(raw_amt.strip()) and amt is None, alt=qs.get("alt", [""])[0] == "1"))
        if view == "tipqr":                                  # QR drawn on the server (pay-any-amount link)
            cfg = tip_config()
            as_png = qs.get("fmt", [""])[0] == "png"
            amt = tip_amount(qs.get("amt", [""])[0])
            want_alt = qs.get("alt", [""])[0] == "1"
            if want_alt and not (cfg or {}).get("alt_vpa"):
                return self._send(b"not found", 404, "text/plain")      # no second address configured
            svg = (tip_qr_png(cfg, amt, alt=want_alt) if as_png else tip_qr_svg(cfg, amt, alt=want_alt)) if cfg else None
            if not svg:
                return self._send(b"not found", 404, "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if as_png else "image/svg+xml")
            self.send_header("Content-Length", str(len(svg)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex")
            self.end_headers()
            return self.wfile.write(svg)
        if "r" in qs and not view and u.path in ("", "/", "/api/index"):      # a shared result link
            return self._shared(qs["r"][0])
        if pwa.serve(self, u.path, qs):                      # manifest, icons, service worker, WhatsApp share target
            return
        if view == "robots" or u.path == "/robots.txt":
            return self._robots()
        if view == "sitemap" or u.path == "/sitemap.xml":
            return self._sitemap()
        if view in LEGAL_PAGES:                              # terms / privacy / refund / contact
            return self._send(legal_page(view))
        if view == "impact" or u.path == "/impact":          # live impact page (+ JSON); query form survives Vercel's rewrite
            from . import impact
            if qs.get("format", [""])[0] == "json":
                body = json.dumps(impact.impact_data(), ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                return self.wfile.write(body)
            return self._send(impact.impact_page())
        if view == "ledger" or u.path == "/ledger":      # query form survives Vercel's rewrite; path form works locally
            self._send(ledger_page())
        elif view == "health" or u.path == "/healthz":
            self._send(b"ok", ctype="text/plain")
        else:
            # plain "/" (or the Vercel entry path) is the real home page; any other path or an unknown ?view= still shows home, but is not indexed
            self._send(home(noindex=bool(view) or u.path not in ("", "/", "/api/index")))

    def _shared(self, rid: str):
        """GET /?r=<id>: the stored result, or a friendly 'expired' page. The id is validated and never echoed back."""
        rec = share.load_share(rid)
        if rec is None:
            return self._send(home(error=share.EXPIRED, noindex=True), 404)
        res = dict(rec["result"]); res["cached"] = False
        res["warning_signs"] = scam_signs(rec["text"])
        block = share.shared_header(rec) + result_block(res, link=share.permalink(rid, siteurl.site_url(self)))
        self._send(home(result=block, noindex=True), cache="no-store")

    def _share_post(self):
        """POST /?via=share (installed app, share sheet): text shares are prefilled and checked after a countdown; an image is read
        with OCR and the text is shown for REVIEW (no auto-run). The image is never stored or logged."""
        def page(code=200, **kw):
            return self._send(home(noindex=True, **kw), code)
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n > share.MAX_TOTAL:
            return page(413, error="That image is too big. Please try a smaller screenshot.")
        try:
            fields, images = share.parse_multipart(self.headers.get("Content-Type"), self.rfile.read(n) if n > 0 else b"")
        except share.ShareError as e:
            return page(e.status, error=e.message)
        except Exception:
            return page(400, error="That share didn't look right. Please try again.")
        shared = pwa.share_text({k: [v] for k, v in fields.items()}, MAX_CHARS)
        if not images:
            return page(prefill=shared, autorun=bool(shared))
        mime, raw = images[0]
        if rate_limited(self._client_ip(), "ocr", ocr.OCR_LIMIT):
            return page(429, prefill=shared, error="Too many images too quickly. Please wait a minute.")
        try:
            if Handler.retrievers is None:
                Handler.retrievers, Handler.llm = default_retrievers(), get_llm()
            text = ocr.transcribe(getattr(Handler.llm, "judges", None), raw, mime, MAX_CHARS)
        except ocr.OcrError as e:
            return page(e.status if e.status in (422, 503) else 400, prefill=shared, error=e.message)
        except Exception:
            return page(503, prefill=shared, error=ocr.UNAVAILABLE)
        return page(prefill=(shared + "\n\n" + text if shared else text)[:MAX_CHARS], notice=share.OCR_REVIEW)

    def _client_ip(self):
        return (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()

    def _read_json(self, limit=4096):
        try:
            n = min(int(self.headers.get("Content-Length", 0)), limit)
            body = json.loads(self.rfile.read(n).decode("utf-8", "replace") or "{}")
            return body if isinstance(body, dict) else {}
        except Exception:
            return {}

    def _webhook(self):
        """Razorpay -> us. Verified with the RAW body, answered 2xx so Razorpay stops retrying, logs one non-personal line."""
        if not rzp.webhook_secret():
            return self._json({"error": "webhook not configured"}, 503)
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0 or n > rzp.MAX_WEBHOOK_BYTES:
            return self._json({"error": "bad size"}, 400)
        raw = self.rfile.read(n)
        if not rzp.verify_webhook(raw, self.headers.get("X-Razorpay-Signature")):
            return self._json({"error": "bad signature"}, 400)
        ev = rzp.summarize_event(raw)
        print(f"razorpay-webhook event={ev['event']} payment={ev['payment_id']} order={ev['order_id']} rupees={ev['rupees']}", flush=True)
        return self._json({"ok": True, "event": ev["event"]})

    def _tg_webhook(self):
        """Telegram -> us (?api=tg-webhook): secret header checked in telegram_bot.webhook_http; always 200 once accepted."""
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        def deps():
            if Handler.retrievers is None:
                Handler.retrievers, Handler.llm = default_retrievers(), get_llm()
            return Handler.retrievers, Handler.llm
        code, obj = tg.webhook_http(self.headers, n, self.rfile.read, deps)
        return self._json(obj, code)

    def _gateway_api(self, api: str):
        """Razorpay tip checkout: ?api=rzp-order creates an order, ?api=rzp-verify checks the payment signature."""
        if api == "rzp-webhook":
            return self._webhook()
        body = self._read_json()
        if api == "rzp-order":
            if rate_limited(self._client_ip(), "tip-order", TIP_ORDER_LIMIT):
                return self._json({"error": "Too many attempts. Please wait a minute."}, 429)
            try:
                return self._json(rzp.create_order(body.get("amount")))
            except rzp.GatewayError as e:
                return self._json({"error": e.message}, e.status)
        if rate_limited(self._client_ip(), "tip-verify", TIP_VERIFY_LIMIT):
            return self._json({"verified": False, "error": "Too many attempts. Please wait a minute."}, 429)
        ok = rzp.verify_signature(body.get("razorpay_order_id"), body.get("razorpay_payment_id"), body.get("razorpay_signature"))
        if not ok:
            return self._json({"verified": False, "error": "We couldn't verify that payment."}, 400)
        return self._json({"verified": True})

    def _ocr(self):
        """Screenshot -> text for the person to review. The image and the text are never logged, stored or checked here."""
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n > ocr.MAX_BODY:
            return self._json({"error": "That image is too big. Please try a smaller screenshot."}, 413)
        try:
            raw, mime = ocr.parse_request(self.rfile.read(n) if n > 0 else b"")
            if rate_limited(self._client_ip(), "ocr", ocr.OCR_LIMIT):
                return self._json({"error": "Too many images too quickly. Please wait a minute."}, 429)
            if Handler.retrievers is None:
                Handler.retrievers, Handler.llm = default_retrievers(), get_llm()
            text = ocr.transcribe(getattr(Handler.llm, "judges", None), raw, mime, MAX_CHARS)
        except ocr.OcrError as e:
            return self._json({"error": e.message}, e.status)
        except Exception:
            return self._json({"error": ocr.UNAVAILABLE}, 503)
        return self._json({"text": text, "chars": len(text)})

    def do_POST(self):
        siteurl.bind(self)
        try:
            return self._post()
        finally:
            siteurl.unbind()

    def _post(self):
        api = parse_qs(urlparse(self.path).query).get("api", [""])[0]
        if api == "tg-webhook":
            return self._tg_webhook()
        if api == "ocr":
            return self._ocr()
        if parse_qs(urlparse(self.path).query).get("via", [""])[0] == "share" and "multipart/form-data" in (self.headers.get("Content-Type") or ""):
            return self._share_post()
        if api in ("rzp-order", "rzp-verify", "rzp-webhook"):
            return self._gateway_api(api)
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
        res = dict(res); res["warning_signs"] = scam_signs(text)   # advice only: from THIS request's text, never cached or stored
        if want_json:
            return self._json(res)
        rid = share.ensure_share(text, None if lang_choice == "auto" else lang_choice, res, MAX_CHARS)
        link = share.permalink(rid, siteurl.site_url(self)) if rid else None
        self._send(home(result=result_block(res, chosen=lang_choice != "auto", link=link), prefill=text, reply=lang_choice))

def main():
    Handler.retrievers, Handler.llm = default_retrievers(), get_llm()
    port = int(os.environ.get("PORT", 8080))
    print(f"Sach on :{port} (llm={'on' if Handler.llm else 'off'})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

if __name__ == "__main__":
    main()
