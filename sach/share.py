"""Sharing in both directions: Sach -> WhatsApp (share text, permalink, invite, sticky bar) and WhatsApp -> Sach (paste and check,
share-target auto-check, image share, how-to helper).

Who calls this: sach/site.py (result_block, home, layout import the HTML/CSS/JS pieces), sach/web.py (permalink route `/?r=<id>`,
the share-target POST, and `ensure_share` after a check), sach/pwa.py (manifest share_target values).
Nothing existing serves the purpose: result_block used to send only the card text. Reads/writes the key-value store under
`share:<id>` (the original forward text and the result of a storable check, same expiry as the cache entry). Never reads or stores
an image. Does not import sach.site at module level (site imports this module).
"""
from __future__ import annotations
import email.policy, html, json, re, time
from email.parser import BytesParser
from urllib.parse import quote
from . import timefmt
from . import cache, store
from .i18n import EMOJI, incomplete, tr, text_lang
from .lang import SUPPORTED
from .report import _clean, _clip, display_card, driver_claim, driver_index
from .models import AUTHORITATIVE

esc = html.escape
ID_RE = re.compile(r"[0-9a-f]{12}")
SHARE_MAX = 900                                   # characters in the WhatsApp message
N_LANGS = len([c for c in SUPPORTED if c != "tl"])   # English + the Indian languages (Tinglish is a spelling style, not counted)

EXPIRED = "This shared result has expired. Paste the forward to check it again."

# Card-language strings for the share message. NOT NATIVE-REVIEWED (hi, te). Other languages fall back to English through tr().
CTA = {"en": "Got a forward you're unsure about? Check it free on Sach: {url}",
       "hi": "कोई फ़ॉरवर्ड समझ नहीं आ रहा? Sach पर मुफ़्त में जाँचें: {url}",                # NOT NATIVE-REVIEWED
       "te": "ఏదైనా ఫార్వర్డ్ మీద సందేహం ఉందా? Sach లో ఉచితంగా తనిఖీ చేయండి: {url}"}          # NOT NATIVE-REVIEWED
CLAIM_LBL = {"en": "Claim checked:", "hi": "जाँचा गया दावा:", "te": "తనిఖీ చేసిన ప్రకటన:"}   # NOT NATIVE-REVIEWED
EVIDENCE_LBL = {"en": "Full evidence:", "hi": "पूरा प्रमाण:", "te": "పూర్తి ఆధారాలు:"}      # NOT NATIVE-REVIEWED


# ---------------------------------------------------------------- shareable result link

def valid_id(rid) -> bool:
    return isinstance(rid, str) and ID_RE.fullmatch(rid) is not None


def share_id(cache_key: str) -> str:
    """First 12 hex characters of the cache key's digest."""
    return cache_key.rsplit(":", 1)[-1][:12]


def permalink(rid: str, site: str) -> str:
    return f"{site}/?r={rid}"


def _age_s(out: dict) -> float:
    try:
        import datetime
        t = datetime.datetime.fromisoformat(str(out.get("first_checked_at") or out.get("checked_at")).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return max(0.0, time.time() - t.timestamp())
    except Exception:
        return 0.0


def ensure_share(text: str, reply_lang, out: dict, max_chars: int = 4000):
    """Store (or confirm) the public record for a storable result and return its id, else None (no link for limited-mode,
    search-down or timed-out results, or when caching is off). On an id collision with a different key, no link is offered."""
    try:
        if not cache.enabled() or not cache.storable(out) or not out.get("claims"):
            return None
        k = cache.key(text, reply_lang)
        rid = share_id(k)
        st = store.get_store()
        cur = st.get("share:" + rid)
        if isinstance(cur, dict):
            return rid if cur.get("key") == k else None
        ttl = max(60, int(cache.ttl_for(out) - _age_s(out)))              # same expiry as the cache entry, not longer
        keep = {x: v for x, v in out.items() if x not in ("warning_signs", "cached", "served_at", "extraction")}   # extraction = the user's skipped sentences: private
        ex = out.get("extraction")
        if isinstance(ex, dict) and isinstance(ex.get("sentences"), int) and isinstance(ex.get("checked"), int):
            keep["extraction"] = {"sentences": ex["sentences"], "checked": ex["checked"]}   # counts only: the permalink says 'Checked M of N', never the sentence text
        st.set("share:" + rid, {"key": k, "text": str(text).strip()[:max_chars], "result": keep}, ttl_s=ttl)
        return rid
    except Exception:
        return None


def load_share(rid):
    """The stored record for a valid id, or None (invalid id, missing, expired, or a record that does not match its id)."""
    if not valid_id(rid):
        return None
    try:
        rec = store.get_store().get("share:" + rid)
        if (isinstance(rec, dict) and isinstance(rec.get("key"), str) and share_id(rec["key"]) == rid and isinstance(rec.get("text"), str)
                and isinstance(rec.get("result"), dict) and rec["result"].get("verdict") and "claims" in rec["result"]):
            return rec
    except Exception:
        pass
    return None


def shared_header(rec: dict) -> str:
    res = rec["result"]
    first = esc(timefmt.fmt_ist(res.get("first_checked_at") or res.get("checked_at") or ""))
    return (f'<div class="shared" id="sharedhdr" role="note"><p class="kicker">Someone shared this Sach check with you</p>'
            f'<p class="note" style="margin:6px 0 4px">The forward that was checked:</p><blockquote class="fwd">{esc(rec["text"])}</blockquote>'
            f'<p class="note" style="margin:6px 0 12px">First checked on {first}.</p>'
            f'<a class="btn" id="checkown" href="#checker">Check your own forward</a></div>')


# ---------------------------------------------------------------- the WhatsApp message

def _claim_link(res: dict, c: dict):
    """The link for ONE claim (the driver): its official-first citation, else (for a matched claim in a multi-claim forward) its
    match review link. Single-claim results keep the citation-only rule, so their text is unchanged."""
    cites = [x for x in (c.get("citations") or []) if x.get("url")]
    lead = ([x for x in cites if x.get("tier") in AUTHORITATIVE] or cites or [None])[0]
    if lead:
        return str(lead["url"])
    m = c.get("match") if c.get("layer") == "match" else None
    if m and len(res.get("claims") or []) > 1 and m.get("review_url"):
        return str(m["review_url"])
    return None


def _lead_url(res: dict):
    c = driver_claim(res)
    return _claim_link(res, c) if c else None


def _claim_lines(res: dict, lang: str) -> list:
    """Multi-claim forwards: one compact line per claim (at most three, the driver always among them) with that claim's own result
    word, so no claim is attributed to another. A matched claim names its fact-checker. Claim text is cut to 80 characters."""
    claims = res.get("claims") or []
    d = driver_index(res)
    keep = [0, 1, 2] if d < 3 else [0, 1, d]
    keep = [i for i in keep if i < len(claims)]
    out = []
    for i in keep:
        c = claims[i]
        v = str(c.get("verdict", ""))
        m = c.get("match") if c.get("layer") == "match" and c.get("match") else None
        word = f'{m.get("rating_text", "")} by {m.get("checker", "")}' if m else v
        txt = _clip(_clean((c.get("claim") or {}).get("text", "")), 80)
        out.append(f'{EMOJI.get(v, "")} {word}: “{txt}”')
    if len(claims) > len(keep):
        out.append(f"+{len(claims) - len(keep)} more on the page")
    return out


def build_share_text(res: dict, site: str, link=None) -> str:
    """Verdict card, the claim that drives the verdict (quoted, max 140 chars), 'Full evidence: <link>' for that claim, and a call to
    action. A forward with several claims lists each claim with its own result instead of quoting one. Under SHARE_MAX characters when
    possible: the claim is shortened first, then dropped. A URL is never cut."""
    lang = text_lang(res.get("language", "en"))
    card = display_card(res).strip()
    drv = driver_claim(res)
    multi = len(res.get("claims") or []) > 1
    claim = _clean(drv["claim"]["text"]) if drv and drv.get("claim") else ""
    lines = _claim_lines(res, lang) if multi else []
    ev = link or (_claim_link(res, drv) if drv else None)
    cta = tr(CTA, lang).format(url=site)

    def compose(limit: int) -> str:
        parts = [card]
        if lines:
            parts.append("\n".join(lines))
        if limit and claim and not multi:
            parts.append(f'{tr(CLAIM_LBL, lang)} “{_clip(claim, limit)}”')
        if ev and ev not in card:                                  # the card already carries its citation link
            parts.append(f"{tr(EVIDENCE_LBL, lang)} {ev}")
        parts.append(cta)
        return "\n\n".join(parts)

    t = compose(140)
    for limit in (100, 60, 0):
        if len(t) <= SHARE_MAX:
            break
        t = compose(limit)
    return t


def wa_url(text: str) -> str:
    return "https://wa.me/?text=" + quote(text, safe="")


def invite_text(site: str) -> str:
    return (f"Got a WhatsApp forward you're unsure about? Sach checks it against PIB and official sources, free, "
            f"in {N_LANGS} languages: {site}")


def invite_link(site: str, cls: str = "invite") -> str:
    return (f'<a class="{cls}" href="{esc(wa_url(invite_text(site)))}" rel="noopener">Tell your family about Sach</a>')


def _json_script(el_id: str, obj) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    for ch, rep in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        s = s.replace(ch, rep)
    return f'<script type="application/json" id="{el_id}">{s}</script>'


def result_share_html(res: dict, site: str, link=None) -> tuple[str, str]:
    """(buttons that go first in the actions group, JSON data element for the scripts)."""
    text = build_share_text(res, site, link)
    quiet = incomplete(res)            # an incomplete check: the share button is quieter than the 'try again later' hint, and no sticky bar
    btns = (f'<a class="btn {"ghost" if quiet else "wa"}" id="shareWa" href="{esc(wa_url(text))}" rel="noopener">Share on WhatsApp</a>'
            f'<button class="btn ghost" id="more-share" type="button" hidden>More ways to share</button>')
    data = {"text": text, "link": link or ""}
    if quiet:
        data["quiet"] = True
    return btns, _json_script("sach-share-data", data)


# ---------------------------------------------------------------- WhatsApp -> Sach: share target (POST, text and image)
# Manifest share_target, confirmed in Chrome's "Receive shared data with the Web Share Target API"
# (developer.chrome.com/docs/capabilities/web-apis/web-share-target): one entry may combine title/text/url with files when
# method is "POST" and enctype is "multipart/form-data" (params.files = [{name, accept}]); GET cannot carry files; a manifest has
# one share_target; the app must be installed. With no service worker fetch handler for POST the browser posts to the server.
SHARE_ACTION = "/?via=share"
SHARE_FILE_FIELD = "files"
SHARE_ACCEPT = ["image/jpeg", "image/png", "image/webp", ".jpg", ".jpeg", ".png", ".webp"]

MAX_TOTAL = 6_000_000
MAX_IMAGE = 5_000_000
MAX_PARTS = 12
MAX_FIELD = 8_000
OCR_REVIEW = "Please check this text before you press Check."


class ShareError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def sniff_mime(raw: bytes):
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def parse_multipart(content_type: str, body: bytes) -> tuple[dict, list]:
    """Strict multipart/form-data parse with email.parser. Returns ({field: text}, [image bytes]).
    Raises ShareError. Image type is decided by magic bytes, never by the declared type or file name."""
    ct = str(content_type or "")[:300]
    if len(body) > MAX_TOTAL:
        raise ShareError(413, "That share is too big. Please try a smaller screenshot.")
    if not ct.lower().startswith("multipart/form-data") or "boundary=" not in ct.lower():
        raise ShareError(400, "That share didn't look right. Please try again.")
    msg = BytesParser(policy=email.policy.HTTP).parsebytes(b"Content-Type: " + ct.encode("latin-1", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    if not msg.is_multipart():
        raise ShareError(400, "That share didn't look right. Please try again.")
    fields: dict = {}
    images: list = []
    for i, part in enumerate(msg.iter_parts()):
        if i >= MAX_PARTS:
            raise ShareError(400, "That share had too many parts.")
        if part.get_content_disposition() != "form-data":
            continue
        name = str(part.get_param("name", header="content-disposition") or "")[:40]
        data = part.get_payload(decode=True) or b""
        if part.get_filename() is not None or name == SHARE_FILE_FIELD:
            if not data:
                continue
            if len(data) > MAX_IMAGE:
                raise ShareError(413, "That image is too big. Please try a smaller screenshot.")
            mime = sniff_mime(data)
            if mime is None:
                raise ShareError(400, "Please share a JPEG, PNG or WebP image.")
            images.append((mime, data))
        elif name in ("title", "text", "url") and name not in fields:
            fields[name] = data[:MAX_FIELD * 4].decode("utf-8", "replace")[:MAX_FIELD]
    return fields, images


# ---------------------------------------------------------------- page pieces

PASTE_HTML = ('<button class="btn pastego" id="pastego" type="button">Paste and check</button>'
              '<p class="note pastemsg" id="pastemsg" role="status" aria-live="polite"></p>')

AUTORUN_HTML = ('<div class="autorun" id="autorun" role="status" aria-live="polite"><span>Checking this forward in <b id="autorun-n">3</b>…</span> '
                '<button class="btn ghost" id="autorun-cancel" type="button">Cancel</button></div>')


def review_notice() -> str:
    return f'<p class="note reviewnote" id="reviewnote" role="status" aria-live="polite"><b>{esc(OCR_REVIEW)}</b></p>'


HOWTO_HTML = """<details class="howto" id="howto" open><summary>How to check a WhatsApp forward</summary>
<div class="howroute" data-route="android-installed"><b>Android, Sach installed</b><p>In WhatsApp, long-press the message → tap Share (↗) → choose Sach.</p></div>
<div class="howroute" data-route="android"><b>Android</b><p>Install Sach once (one tap), then you can share any forward straight from WhatsApp.</p>
<p><button class="btn" id="howto-install" type="button" hidden>Install Sach</button></p>
<p class="note">Or: long-press the message → Copy → come back here → tap Paste and check.</p></div>
<div class="howroute" data-route="ios"><b>iPhone</b><p>In WhatsApp, long-press the message → Copy → come back here → tap Paste and check.</p>
<p class="note">Add Sach to your Home Screen: tap Share → Add to Home Screen.</p></div>
<div class="howroute" data-route="desktop"><b>Computer</b><p>In WhatsApp Web, copy the message, then click Paste and check.</p></div></details>"""

BAR_HTML = ('<div class="sharebar" id="sharebar" role="region" aria-label="Share this verdict" hidden>'
            '<a class="btn wa" id="sharebar-wa" href="#">Share verdict on WhatsApp</a>'
            '<button class="btn ghost" id="sharebar-x" type="button" aria-label="Dismiss">&#10005;</button></div>')

CSS = """
.actions .btn.wa{flex:1 1 100%;background:#0f7a3a;border-color:#0f7a3a;color:#fff;font-size:18px;min-height:52px}
.actions .btn.wa:hover,.sharebar .btn.wa:hover{background:#0b6130;border-color:#0b6130;color:#fff}
.sharebar .btn.wa{background:#0f7a3a;border-color:#0f7a3a;color:#fff}
.btn.wa-invite{background:#0f7a3a;border-color:#0f7a3a;color:#fff}.btn.wa-invite:hover{background:#0b6130;border-color:#0b6130;color:#fff}
.actions #more-share{flex:1 1 100%}
@media(max-width:560px){.actions .btn.wa,.actions #more-share{grid-column:1/-1}}
.invite{display:inline-flex;align-items:center;min-height:44px;font-weight:600}
.invitebox{margin:12px 0 0}
.pastego{display:flex;width:100%;min-height:52px;font-size:18px;align-items:center;justify-content:center;margin:8px 0 4px}
.pastego[hidden]{display:none}.pastemsg{min-height:1.3em;margin:4px 0 8px}
.autorun{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin:10px 0 0;padding:10px 14px;border:2px dashed var(--rule);border-radius:4px;background:var(--paper2);font-weight:600}
.autorun .btn{min-height:44px;padding:8px 18px}.autorun[hidden]{display:none}
.reviewnote{margin:8px 0 0}
details.howto{margin:16px 0 0;border:1.5px solid var(--ink);border-radius:4px;background:var(--card);padding:0 14px}
details.howto summary{min-height:44px;display:flex;align-items:center;font-size:17px}
.howroute{padding:8px 0;border-top:1px solid color-mix(in srgb,var(--ink) 25%,transparent)}.howroute[hidden]{display:none}
.howroute p{margin:4px 0;font-size:16px;max-width:none}.howroute .btn{min-height:44px}
.shared{margin:0 0 22px;padding:16px 18px;background:var(--paper2);border-left:6px solid var(--true);border-radius:2px;scroll-margin-top:80px}
blockquote.fwd{margin:0;padding:8px 12px;border-left:4px solid var(--rule);background:var(--card);white-space:pre-wrap;overflow-wrap:anywhere;max-height:14em;overflow:auto}
.shared .btn{min-height:48px;display:inline-flex;align-items:center}
.sharebar[hidden]{display:none!important}
@media(min-width:761px){.sharebar{left:auto!important;right:24px!important;bottom:24px!important;border:2px solid var(--rule)!important;border-radius:6px;box-shadow:6px 6px 0 var(--rule);width:auto}}
@media(min-width:0px){
.sharebar{display:flex;gap:8px;align-items:center;position:fixed;left:0;right:0;bottom:0;z-index:30;padding:8px 12px calc(8px + env(safe-area-inset-bottom));background:var(--card);border-top:2px solid var(--rule);animation:sbup .2s ease-out}
.sharebar .btn.wa{flex:1;min-height:48px;display:inline-flex;align-items:center;justify-content:center}
.sharebar .btn.ghost{min-width:44px;min-height:48px;padding:8px 10px}
html.has-sharebar footer{padding-bottom:calc(96px + env(safe-area-inset-bottom))}}
@keyframes sbup{from{transform:translateY(100%)}to{transform:none}}
@media(prefers-reduced-motion:reduce){.sharebar{animation:none!important}}
@media print{.sharebar,.pastego,.autorun,details.howto{display:none!important}}
"""

JS = r"""
(function(){
'use strict';
var $=function(s){return document.querySelector(s)};
var say=function(el,m){if(el)el.textContent=m};
/* ---- Sach -> WhatsApp: runs at load and again after a swapped-in result ---- */
var io=null,dismissed=false;
window.sachBindShare=function(){
  var wa=$('#shareWa'),bar=$('#sharebar'),more=$('#more-share'),d=$('#sach-share-data'),data=null,root=document.documentElement;
  if(io){io.disconnect();io=null}
  if(bar){bar.hidden=true;root.classList.remove('has-sharebar')}
  try{data=d?JSON.parse(d.textContent):null}catch(e){data=null}
  window.sachShareText=data?function(){return data.text}:null;
  if(more&&data&&navigator.share){more.hidden=false;
    more.addEventListener('click',function(){try{var p=navigator.share({title:'Sach verdict',text:data.text});if(p&&p.catch)p.catch(function(){})}catch(e){}})}
  if(wa&&bar&&data&&!data.quiet&&'IntersectionObserver' in window){var bw=$('#sharebar-wa');if(bw)bw.href=wa.href;dismissed=false;
    io=new IntersectionObserver(function(es){var e=es[es.length-1],show=!e.isIntersecting&&!dismissed;
      bar.hidden=!show;root.classList.toggle('has-sharebar',show)});io.observe(wa)}
};
var bx=$('#sharebar-x');if(bx)bx.addEventListener('click',function(){dismissed=true;var b=$('#sharebar');if(b)b.hidden=true;document.documentElement.classList.remove('has-sharebar')});
window.sachBindShare();document.addEventListener('sach:result',window.sachBindShare);
var sh=$('#sharedhdr');if(sh){var fix=function(){if(scrollY>0)sh.scrollIntoView({block:'start'})};window.addEventListener('load',function(){setTimeout(fix,400)});if(document.fonts&&document.fonts.ready)document.fonts.ready.then(function(){setTimeout(fix,100)})}
var co=$('#checkown');if(co)co.addEventListener('click',function(e){e.preventDefault();var c=$('#checker'),t=$('#text');if(c)c.scrollIntoView({block:'start'});if(t)t.focus()});
/* ---- WhatsApp -> Sach: Paste and check (clipboard is read only inside this click handler) ---- */
var pg=$('#pastego'),pm=$('#pastemsg'),ta=$('#text'),form=$('#form');
if(pg&&ta&&form){
  var sync=function(){pg.hidden=!!ta.value.trim()};ta.addEventListener('input',sync);sync();
  var manual=function(m){say(pm,m);ta.focus()};
  pg.addEventListener('click',function(){
    say(pm,'');
    if(!navigator.clipboard||!navigator.clipboard.readText){manual('Long-press in the box and tap Paste, then press Check.');return}
    navigator.clipboard.readText().then(function(t){
      t=(t||'').trim();
      if(!t){manual('Your clipboard is empty. Copy the message in WhatsApp first, then come back and tap Paste and check.');return}
      ta.value=t.slice(0,ta.maxLength>0?ta.maxLength:4000);ta.dispatchEvent(new Event('input',{bubbles:true}));
      if(form.requestSubmit)form.requestSubmit();else form.submit()
    },function(){manual('Long-press in the box and tap Paste, then press Check.')})
  });
}
/* ---- share-target launch: visible 3-second countdown, then check; Cancel (or typing) stops it ---- */
var ar=$('#autorun');
if(ar&&ta&&form){var n=3,num=$('#autorun-n'),tm=null,stop=function(){if(tm){clearInterval(tm);tm=null}ar.hidden=true};
  tm=setInterval(function(){n--;if(n<=0){stop();if(ta.value.trim()){if(form.requestSubmit)form.requestSubmit();else form.submit()}}else if(num)num.textContent=n},1000);
  var cn=$('#autorun-cancel');if(cn)cn.addEventListener('click',function(){stop();ta.focus()});
  ta.addEventListener('input',stop);
}
/* ---- how-to helper: show the route for this device; remember "closed" ---- */
var hw=$('#howto');
if(hw){
  try{if(localStorage.getItem('sach-howto-closed')==='1')hw.open=false}catch(e){}
  hw.addEventListener('toggle',function(){try{if(hw.open)localStorage.removeItem('sach-howto-closed');else localStorage.setItem('sach-howto-closed','1')}catch(e){}});
  var ua=navigator.userAgent||'',standalone=false;
  try{standalone=(window.matchMedia&&matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true}catch(e){}
  var isIos=/iPad|iPhone|iPod/.test(ua)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1),isAnd=/Android/i.test(ua),mobile=/Mobi|Android|iPhone|iPad/i.test(ua);
  var show=function(keep){var rs=hw.querySelectorAll('.howroute');for(var i=0;i<rs.length;i++)rs[i].hidden=keep.indexOf(rs[i].getAttribute('data-route'))<0};
  var pick=function(inst){if(isIos)show(['ios']);else if(isAnd)show([inst?'android-installed':'android']);else if(!mobile)show(['desktop']);else show(['android','ios','desktop'])};
  pick(standalone);
  if(isAnd&&!standalone&&navigator.getInstalledRelatedApps){try{navigator.getInstalledRelatedApps().then(function(a){if(a&&a.length)pick(true)},function(){})}catch(e){}}
  if(!isIos&&!isAnd&&mobile===false&&!/Windows|Macintosh|Linux|CrOS/.test(ua))show(['android','ios','desktop']);
  var ib=$('#howto-install'),def=null;
  window.addEventListener('beforeinstallprompt',function(e){def=e;if(ib)ib.hidden=false});
  window.addEventListener('appinstalled',function(){if(ib)ib.hidden=true;def=null});
  if(ib)ib.addEventListener('click',function(){if(!def)return;var d=def;def=null;ib.hidden=true;try{d.prompt()}catch(e){}});
}
})();
"""
