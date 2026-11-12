"""The public address of this Sach site, in one place.

Who calls this: sach/site.py (`layout`: canonical, og:url, og:image), sach/web.py (robots.txt, sitemap.xml, and it binds the
request's Host header for the duration of a request), sach/report.py (the "Checked with Sach (...)" line), scripts/*.py (defaults).
Nothing existing serves the purpose: the address used to be typed into four places. Reads the environment and a Host header only;
writes nothing. stdlib only, imports nothing that touches the network (sach/report.py imports it).

Order: SACH_SITE_URL (validated) -> the request's own Host header (validated, https) -> DEFAULT_SITE_URL.
"""
from __future__ import annotations
import os, re, threading

DEFAULT_SITE_URL = "https://sach-check-lilac.vercel.app"     # the one place the old address lives; override with SACH_SITE_URL

_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*(?::[0-9]{1,5})?$")
_ORIGIN = re.compile(r"^https://(?P<host>[^/?#@\s]+)/*$")
_local = threading.local()


def valid_host(host) -> str | None:
    """A lower-cased hostname[:port] if it is plausible, else None. Never returns anything that could carry markup or a path."""
    if not isinstance(host, str):
        return None
    h = host.strip().lower()
    if not _HOST.match(h):
        return None
    port = h.partition(":")[2]
    if port and not 1 <= int(port) <= 65535:
        return None
    return h


def env_site_url() -> str | None:
    """SACH_SITE_URL as a clean origin (https, host[:port], no path/query/fragment, no trailing slash), or None if unset or invalid."""
    raw = (os.environ.get("SACH_SITE_URL") or "").strip()
    m = _ORIGIN.match(raw)
    host = valid_host(m.group("host")) if m else None
    return f"https://{host}" if host else None


def bind(handler) -> None:
    """Remember this request's Host header for the current thread, so code without a handler (report text, layout) can use it."""
    try:
        _local.host = valid_host(handler.headers.get("Host"))
    except Exception:
        _local.host = None


def unbind() -> None:
    _local.host = None


def site_url(handler=None) -> str:
    """The site's public origin, no trailing slash: SACH_SITE_URL, else https://<Host of this request>, else the default."""
    env = env_site_url()
    if env:
        return env
    host = None
    if handler is not None:
        try:
            host = valid_host(handler.headers.get("Host"))
        except Exception:
            host = None
    if host is None:
        host = getattr(_local, "host", None)
    return f"https://{host}" if host else DEFAULT_SITE_URL
