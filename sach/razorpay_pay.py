"""Razorpay Standard Checkout for the tip jar (stdlib only: no SDK, so nothing extra to install on Vercel).

Flow: browser asks us for an order -> we create it at Razorpay with the SECRET key (server side only) ->
browser opens Razorpay's checkout with the public key id + order id -> on success the browser sends us the three
values Razorpay returns -> we verify the HMAC-SHA256 signature before calling anything "paid".

Env vars: RAZORPAY_KEY_ID (public, safe for the browser) and RAZORPAY_KEY_SECRET (never leaves the server).
Both unset => gateway is off and the tip jar stays QR-only.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, os, re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ORDERS_URL = "https://api.razorpay.com/v1/orders"
MIN_RUPEES, MAX_RUPEES = 1, 10000                       # same bounds as the QR tip amounts; Razorpay's own minimum is 100 paise
_KEY_ID = re.compile(r"^rzp_(test|live)_[A-Za-z0-9]{8,40}$")
_ID = re.compile(r"^[A-Za-z0-9_]{6,64}$")               # order_/pay_ ids
_SIG = re.compile(r"^[0-9a-f]{64}$")                    # hex SHA-256

class GatewayError(Exception):
    """status is the HTTP code we should answer with (400 bad input, 401 bad keys, 500/502 upstream)."""
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message

def gateway_config() -> dict | None:
    """{'key_id','secret','mode'} when both keys are set and look right, else None."""
    key_id = (os.environ.get("RAZORPAY_KEY_ID") or "").strip()
    secret = (os.environ.get("RAZORPAY_KEY_SECRET") or "").strip()
    m = _KEY_ID.match(key_id)
    if not m or len(secret) < 8:
        return None
    return {"key_id": key_id, "secret": secret, "mode": m.group(1)}

def public_key_id() -> str | None:
    cfg = gateway_config()
    return cfg["key_id"] if cfg else None

def rupees_to_paise(rupees) -> int:
    if isinstance(rupees, bool) or not isinstance(rupees, (int, str)):
        raise GatewayError(400, "Enter a whole number of rupees from 1 to 10,000.")
    s = str(rupees).strip()
    if not (s.isascii() and s.isdigit()) or not (MIN_RUPEES <= int(s) <= MAX_RUPEES):
        raise GatewayError(400, "Enter a whole number of rupees from 1 to 10,000.")
    return int(s) * 100

def create_order(rupees, receipt: str = "sach-tip", _open=urlopen) -> dict:
    """POST /v1/orders. Returns {order_id, amount (paise), currency, key_id}; never returns the secret."""
    cfg = gateway_config()
    if not cfg:
        raise GatewayError(503, "Card and UPI checkout isn't switched on.")
    paise = rupees_to_paise(rupees)
    body = json.dumps({"amount": paise, "currency": "INR", "receipt": re.sub(r"[^A-Za-z0-9_-]", "", receipt)[:40] or "sach-tip"}).encode()
    auth = base64.b64encode(f"{cfg['key_id']}:{cfg['secret']}".encode()).decode()
    req = Request(ORDERS_URL, data=body, method="POST",
                  headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}", "User-Agent": "sach-check"})
    try:
        with _open(req, timeout=15) as r:
            data = json.loads(r.read().decode())
    except HTTPError as e:
        raise GatewayError(401 if e.code == 401 else 502, "Razorpay rejected our keys." if e.code == 401 else "Razorpay couldn't create the order. Please try again.")
    except (URLError, TimeoutError, ValueError, OSError):
        raise GatewayError(502, "Couldn't reach Razorpay. Please try again.")
    oid = data.get("id") if isinstance(data, dict) else None
    if not isinstance(oid, str) or not _ID.match(oid):
        raise GatewayError(502, "Razorpay gave an unexpected answer. Please try again.")
    return {"order_id": oid, "amount": paise, "currency": "INR", "key_id": cfg["key_id"]}

def verify_signature(order_id, payment_id, signature) -> bool:
    """HMAC-SHA256(order_id + '|' + payment_id, KEY_SECRET) compared in constant time. False on anything odd."""
    cfg = gateway_config()
    if not cfg or not all(isinstance(x, str) for x in (order_id, payment_id, signature)):
        return False
    if not (_ID.match(order_id) and _ID.match(payment_id) and _SIG.match(signature.lower())):
        return False
    want = hmac.new(cfg["secret"].encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, signature.lower())


# ---- webhooks: Razorpay calls us (server to server) when a payment is captured/failed/refunded, even if the payer closed the tab
WEBHOOK_EVENTS = ("payment.captured", "payment.failed", "order.paid", "refund.processed")
MAX_WEBHOOK_BYTES = 64 * 1024

def webhook_secret() -> str | None:
    """RAZORPAY_WEBHOOK_SECRET: a secret YOU choose, entered both in Razorpay's webhook settings and in the environment."""
    sec = (os.environ.get("RAZORPAY_WEBHOOK_SECRET") or "").strip()
    return sec if len(sec) >= 8 else None

def verify_webhook(raw: bytes, signature) -> bool:
    """X-Razorpay-Signature = hex HMAC-SHA256 of the RAW request body with the webhook secret."""
    sec = webhook_secret()
    if not sec or not isinstance(raw, (bytes, bytearray)) or not isinstance(signature, str) or not _SIG.match(signature.strip().lower()):
        return False
    want = hmac.new(sec.encode(), bytes(raw), hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, signature.strip().lower())

def summarize_event(raw: bytes) -> dict:
    """The few non-personal fields worth logging for the operator: event name, payment/order id, amount in rupees."""
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
        ev = d.get("event") if isinstance(d, dict) else None
        pay = (((d.get("payload") or {}).get("payment") or {}).get("entity") or {}) if isinstance(d, dict) else {}
        pid, oid, amt = pay.get("id"), pay.get("order_id"), pay.get("amount")
        return {"event": ev if ev in WEBHOOK_EVENTS else "other",
                "payment_id": pid if isinstance(pid, str) and _ID.match(pid) else None,
                "order_id": oid if isinstance(oid, str) and _ID.match(oid) else None,
                "rupees": round(amt / 100, 2) if isinstance(amt, (int, float)) and not isinstance(amt, bool) and 0 < amt <= 100000000 else None}
    except Exception:
        return {"event": "other", "payment_id": None, "order_id": None, "rupees": None}
