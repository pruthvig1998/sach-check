"""Point the Telegram bot at Sach (or remove / inspect it). Prints only redacted output; never the token or secret.
Usage: python scripts/set_telegram_webhook.py [--url https://sach-check-lilac.vercel.app] | --info | --delete
Reads TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET from the environment or .env."""
import argparse, json, os, pathlib, sys
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root))
import sach  # noqa: loads .env
from sach import telegram_bot as tg

DEFAULT_URL = "https://sach-check-lilac.vercel.app"

def run(argv=None, client=None, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=DEFAULT_URL, help="public base URL of the deployed site")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--info", action="store_true", help="show getWebhookInfo")
    g.add_argument("--delete", action="store_true", help="remove the webhook (turns the bot off)")
    a = ap.parse_args(argv)
    cfg = tg.config()
    token, secret = cfg if cfg else ((os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(), (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip())
    safe = lambda x: tg.redact(x, token, secret)
    if a.info or a.delete:
        if not tg._TOKEN.match(token):
            out("TELEGRAM_BOT_TOKEN is missing or malformed."); return 2
    elif not cfg:
        out("TELEGRAM_BOT_TOKEN and/or TELEGRAM_WEBHOOK_SECRET is missing or malformed (token 123456:ABC..., secret 16-256 of A-Za-z0-9_-)."); return 2
    c = client or tg.TelegramClient(token)
    if a.info:
        res = c.get_webhook_info()
    elif a.delete:
        res = c.delete_webhook()
    else:
        base = a.url.rstrip("/")
        if not base.startswith("https://"):
            out("--url must start with https://"); return 2
        res = c.set_webhook(f"{base}/?api=tg-webhook", secret, allowed_updates=["message"], drop_pending_updates=True)
    if res is None:
        out(safe(f"Telegram call failed: {c.last_error or 'unknown error'}")); return 1
    out(safe(json.dumps(res, indent=2, ensure_ascii=False)) if a.info else safe("OK" + (": webhook removed" if a.delete else ": webhook set")))
    return 0

if __name__ == "__main__":
    sys.exit(run())
