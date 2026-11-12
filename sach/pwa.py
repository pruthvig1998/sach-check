"""Sach as an app (stdlib only): web app manifest, PNG icons, WhatsApp share target, service worker,
install prompt and private on-device history ("My checks").

Called from sach/web.py (`pwa.serve`, one block in do_GET) and sach/site.py (`layout` and `home` append HEAD, SCRIPT, HOME_HTML).
Nothing here talks to the pipeline, the ledger or any third party. The history lives only in the visitor's localStorage.
Do not import sach.site at module level: site.py imports this module.
"""
from __future__ import annotations
import json, math, re, struct, zlib
from functools import lru_cache

THEME = "#f2ebdb"            # same as <meta name="theme-color"> in site.layout
BRAND = (0xC2, 0x32, 0x1F)   # the red in the layout's inline favicon
ICON_SIZES = (180, 192, 512)  # the only sizes served; anything else is a 404

# ---------------------------------------------------------------- manifest

def manifest() -> dict:
    icon = lambda s, m=False: {"src": f"/?view=icon&size={s}" + ("&maskable=1" if m else ""), "sizes": f"{s}x{s}",
                               "type": "image/png", "purpose": "maskable" if m else "any"}
    return {
        "id": "/", "name": "Sach: check a forward", "short_name": "Sach",
        "description": "Paste or share a WhatsApp forward. Sach checks it against PIB and official sources and gives a cited verdict in English, Hindi or Telugu.",
        "start_url": "/", "scope": "/", "display": "standalone", "lang": "en",
        "background_color": THEME, "theme_color": THEME,
        "categories": ["news", "utilities", "education"],
        "icons": [icon(192), icon(512), icon(192, True), icon(512, True)],
        "share_target": {"action": "/", "method": "GET", "params": {"title": "title", "text": "text", "url": "url"}},
    }

# ---------------------------------------------------------------- icons (pure Python raster: rounded square + a geometric "S")

_R, _W = 0.20, 0.14           # S-units: radius of each bowl's centre line, stroke width
_SWEEP = math.radians(235)
_ARCS = ((0.0, -_R, math.radians(90)), (0.0, _R, math.radians(-90)))   # (cx, cy, start angle): upper bowl, lower bowl; the second is the first turned 180 degrees

def _arc_dist(x: float, y: float, cx: float, cy: float, a0: float) -> float:
    dx, dy = x - cx, y - cy
    if (math.atan2(dy, dx) - a0) % (2 * math.pi) <= _SWEEP:
        return abs(math.hypot(dx, dy) - _R)
    best = 9.0
    for a in (a0, a0 + _SWEEP):                       # round caps: distance to the nearer end of the arc
        best = min(best, math.hypot(x - (cx + _R * math.cos(a)), y - (cy + _R * math.sin(a))))
    return best

def _s_distance(u: float, v: float) -> float:
    return min(_arc_dist(u, v, *a) for a in _ARCS) - _W / 2    # negative inside the stroke

def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

@lru_cache(maxsize=16)
def icon_png(size: int, maskable: bool = False) -> bytes:
    """RGBA PNG. Regular icons have rounded transparent corners. Maskable (and the 180 px Apple icon, which iOS masks itself)
    are full-bleed with the S kept inside the central safe zone."""
    full_bleed = maskable or size == 180
    k = 0.58 if maskable else 0.68                    # S height is about 0.94 * k of the icon
    half, radius = size / 2, size * 12 / 64
    rows = bytearray()
    for j in range(size):
        py = j + 0.5
        v = (py / size - 0.5) / k
        row = bytearray(b"\x00")
        for i in range(size):
            px = i + 0.5
            a = 255
            if not full_bleed:
                qx, qy = abs(px - half) - (half - radius), abs(py - half) - (half - radius)
                if qx > -1 and qy > -1:
                    d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius
                    a = int(255 * min(1.0, max(0.0, 0.5 - d)))
            cov = 0.0
            u = (px / size - 0.5) / k
            if -0.45 < u < 0.45 and -0.62 < v < 0.62:
                cov = min(1.0, max(0.0, 0.5 - _s_distance(u, v) * k * size))
            row += bytes((round(BRAND[0] + (255 - BRAND[0]) * cov), round(BRAND[1] + (255 - BRAND[1]) * cov),
                          round(BRAND[2] + (255 - BRAND[2]) * cov), a))
        rows += row
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _chunk(b"IEND", b"")

# ---------------------------------------------------------------- share target

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f‎‏‪-‮⁦-⁩]")   # keeps \n and \t, drops the rest incl. bidi controls

def _clean(s: str) -> str:
    return _CTRL.sub("", s.replace("\r\n", "\n").replace("\r", "\n")).strip()

def share_text(qs: dict, limit: int) -> str:
    """Join the shared title/text/url into one prefill string. Never checks anything. '' when nothing usable was shared."""
    get = lambda k: _clean(qs.get(k, [""])[0][:limit * 2])
    title, text, url = get("title"), get("text"), get("url")
    parts = []
    for p in (title, text, url):
        if p and not any(p in q for q in parts):      # WhatsApp often repeats the url inside text, or the title as the text
            parts = [q for q in parts if q not in p] + [p]
    return "\n".join(parts)[:limit].strip()

_SHARE_PATHS = ("", "/", "/api/index")

# ---------------------------------------------------------------- HTTP

def _out(h, body: bytes, ctype: str, cache: str, extra: dict | None = None, code: int = 200):
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("X-Content-Type-Options", "nosniff")
    h.send_header("Referrer-Policy", "no-referrer")
    h.send_header("Cache-Control", cache)
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)

def serve(h, path: str, qs: dict) -> bool:
    """Handle ?view=manifest|icon|sw and the share target. True when a response was written."""
    view = qs.get("view", [""])[0]
    if view == "manifest":
        _out(h, json.dumps(manifest(), ensure_ascii=False).encode(), "application/manifest+json; charset=utf-8", "public, max-age=3600")
        return True
    if view == "icon":
        size = qs.get("size", [""])[0]
        if size not in {str(s) for s in ICON_SIZES}:
            _out(h, b"not found", "text/plain", "no-store", code=404)
        else:
            _out(h, icon_png(int(size), qs.get("maskable", [""])[0] == "1"), "image/png", "public, max-age=86400")
        return True
    if view == "sw":
        _out(h, SW_JS.encode(), "application/javascript; charset=utf-8", "no-cache", {"Service-Worker-Allowed": "/"})
        return True
    if not view and qs.get("go", [""])[0] != "tip" and path in _SHARE_PATHS and any(qs.get(k, [""])[0].strip() for k in ("title", "text", "url")):
        from .site import MAX_CHARS, home                  # lazy: site imports this module
        pre = share_text(qs, MAX_CHARS)
        if pre:
            _out(h, home(prefill=pre), "text/html; charset=utf-8", "no-store")   # personal text: never cacheable by browser, CDN or service worker
            return True
    return False

# ---------------------------------------------------------------- service worker
# Cache rules, in one place: only (a) the plain home page "/" with no query string, as an offline fallback,
# and (b) the manifest and icons are ever stored. Everything else goes straight to the network, untouched.

SW_JS = r"""/* Sach service worker. Caches only the public shell. Never caches POSTs, ?api=, pay/tip pages, share-target URLs or results. */
const VERSION = 'v1';
const SHELL = 'sach-shell-' + VERSION;      // the plain home page
const STATIC = 'sach-static-' + VERSION;    // manifest and icons
const OFFLINE = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>Offline - Sach</title><style>body{font:18px/1.5 system-ui,sans-serif;margin:0;padding:32px 20px;background:#f2ebdb;color:#17140f}' +
  'main{max-width:30em;margin:0 auto}h1{font-size:28px}button{font:inherit;font-weight:600;min-height:44px;padding:8px 22px;margin-top:8px}' +
  '@media(prefers-color-scheme:dark){body{background:#15130f;color:#f1eadb}}</style></head><body><main><h1>You\'re offline</h1>' +
  '<p>You\'re offline. Sach needs the internet to check a forward against official sources. Your text is still here: try again when you\'re back online.</p>' +
  '<button type="button" onclick="location.reload()">Try again</button></main></body></html>';

const offlinePage = () => new Response(OFFLINE, {status: 503, headers: {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'}});

// Only the plain home page ("/" and nothing in the query string) and the manifest/icon URLs may be cached.
const isPlainHome = u => u.pathname === '/' && u.search === '';
const isStatic = u => {
  if (u.pathname !== '/') return false;
  const p = u.searchParams, v = p.get('view');
  if (v !== 'manifest' && v !== 'icon') return false;
  return [...p.keys()].every(k => k === 'view' || (v === 'icon' && (k === 'size' || k === 'maskable')));
};
const cacheable = r => r.ok && !r.redirected && r.type === 'basic' && !/no-store|private/i.test(r.headers.get('Cache-Control') || '');

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.add('/')).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k.startsWith('sach-') && k !== SHELL && k !== STATIC).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function homeFirst(req) {                 // network first; on a slow or dead connection fall back to the saved plain home page
  const cache = await caches.open(SHELL);
  const net = fetch(req).then(r => { if (cacheable(r)) cache.put('/', r.clone()); return r; });
  net.catch(() => {});
  const saved = await cache.match('/');
  if (!saved) return net.catch(offlinePage);
  return Promise.race([net, new Promise(ok => setTimeout(() => ok(saved), 5000))]).catch(() => saved);
}

async function staticFirst(req) {               // icons and manifest: cache first
  const cache = await caches.open(STATIC);
  const hit = await cache.match(req);
  if (hit) return hit;
  const r = await fetch(req);
  if (cacheable(r)) cache.put(req, r.clone());
  return r;
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;             // never touch POSTs (checks, tips)
  const u = new URL(req.url);
  if (u.origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    e.respondWith(isPlainHome(u) ? homeFirst(req) : fetch(req).catch(offlinePage));   // other pages are never stored
  } else if (isStatic(u)) {
    e.respondWith(staticFirst(req));
  }                                              // anything else (?api=, ?view=pay, ?view=tipqr, ?go=tip, ...) is not intercepted
});
"""

# ---------------------------------------------------------------- page pieces (appended by site.layout / site.home)

HEAD = """<link rel="manifest" href="/?view=manifest"><link rel="apple-touch-icon" href="/?view=icon&amp;size=180">
<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="apple-mobile-web-app-title" content="Sach">
<style>""" + """
/* --- pwa.py: install bar and My checks */
.pwa-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:14px 0 0;padding:10px 14px;background:var(--card);border:1.5px solid var(--ink);border-radius:4px;font-size:15px}
.pwa-bar[hidden],.mychecks[hidden]{display:none}
.mychecks summary .note{margin-left:6px}
.pwa-bar span{flex:1 1 200px}.pwa-bar .btn{min-height:44px;padding:8px 18px;font-size:16px}.pwa-bar .x{min-width:44px;padding:8px 10px}
details.mychecks{margin:18px 0 0;border:1.5px solid var(--ink);border-radius:4px;background:var(--card);padding:0 14px}
details.mychecks summary{min-height:44px;display:flex;align-items:center;font-size:17px}
.mychecks ul{list-style:none;margin:0;padding:0}
.mychecks li{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;align-items:start;padding:10px 0;border-top:1px solid color-mix(in srgb,var(--ink) 25%,transparent)}
.mychecks li .tag{margin-top:3px}.mychecks .claim{overflow-wrap:anywhere;font-size:16px}
.mychecks .meta{grid-column:2;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;font-size:13px;color:var(--mute)}
.mychecks .btn{min-height:44px;padding:8px 16px;font-size:15px}
.mychecks .foot{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:12px 0 14px;border-top:1px solid color-mix(in srgb,var(--ink) 25%,transparent)}
.mychecks .foot p{margin:0;flex:1 1 220px}
</style>"""

HOME_HTML = """<div class="wrap">
<div class="pwa-bar" id="pwa-install" role="region" aria-label="Install Sach" hidden><span id="pwa-msg"></span><button type="button" class="btn" id="pwa-go" hidden>Install Sach</button><button type="button" class="btn ghost x" id="pwa-x" aria-label="Dismiss">&#10005;</button></div>
<details class="mychecks" id="mychecks" hidden><summary>My checks <span id="mychecks-n" class="note"></span></summary>
<ul id="mychecks-list"></ul>
<div class="foot"><p class="note">Saved only on this device, in your browser. Sach's servers never see this list.</p><button type="button" class="btn ghost" id="mychecks-clear">Clear history</button></div></details>
</div>"""

# One script: service worker registration, install prompt, share-target scroll, private history. Every storage call is wrapped in try/catch.
JS = r"""
(function(){
'use strict';
var $=function(i){return document.getElementById(i)};
/* service worker (https or localhost only; failures are silent) */
try{if('serviceWorker' in navigator&&(location.protocol==='https:'||location.hostname==='localhost'||location.hostname==='127.0.0.1')){
window.addEventListener('load',function(){try{navigator.serviceWorker.register('/?view=sw',{scope:'/'}).catch(function(){})}catch(e){}})}}catch(e){}
/* shared text arrived from WhatsApp: scroll to the checker, never submit, then drop the personal text from the address bar */
try{var sp=new URLSearchParams(location.search);if(!$('result')&&(sp.has('text')||sp.has('title')||sp.has('url'))){
var ck=$('checker');if(ck)ck.scrollIntoView({block:'center'});history.replaceState(null,'','/#check')}}catch(e){}
/* install prompt */
(function(){var bar=$('pwa-install');if(!bar)return;var msg=$('pwa-msg'),go=$('pwa-go'),x=$('pwa-x'),deferred=null,shown=false,DKEY='sach-install-dismissed';
var standalone=false;try{standalone=(window.matchMedia&&matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true}catch(e){}
if(standalone)return;
var dismissed=function(){try{var t=parseInt(localStorage.getItem(DKEY)||'0',10);return t>0&&Date.now()-t<30*864e5}catch(e){return false}};
var show=function(text,canInstall){if(shown||dismissed())return;shown=true;msg.textContent=text;go.hidden=!canInstall;bar.hidden=false};
x.addEventListener('click',function(){bar.hidden=true;try{localStorage.setItem(DKEY,String(Date.now()))}catch(e){}});
window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferred=e;show('Install Sach on your phone to open it like an app.',true)});
window.addEventListener('appinstalled',function(){bar.hidden=true;deferred=null});
go.addEventListener('click',function(){if(!deferred)return;var d=deferred;deferred=null;bar.hidden=true;try{d.prompt();if(d.userChoice)d.userChoice.then(function(){},function(){})}catch(e){}});
try{var ua=navigator.userAgent||'',ios=/iPad|iPhone|iPod/.test(ua)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
if(ios&&!/CriOS|FxiOS|EdgiOS/.test(ua))show('To install: tap Share, then Add to Home Screen.',false)}catch(e){}
})();
/* My checks: the last 20 checks, kept only in this browser */
var KEY='sach-history-v1',MAX=20,V={TRUE:1,FALSE:1,MISLEADING:1,UNVERIFIED:1};
var load=function(){try{var a=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(a)?a.filter(function(h){return h&&typeof h.claim==='string'&&V[h.verdict]}).slice(0,MAX):[]}catch(e){return[]}};
var save=function(a){try{localStorage.setItem(KEY,JSON.stringify(a.slice(0,MAX)))}catch(e){}};
var readResult=function(){var res=$('result');if(!res)return null;var v='',claim='',lang='';
try{var el=$('sach-card-data');if(el){var d=JSON.parse(el.textContent||'{}'),c=d.claims&&d.claims[0];v=String(d.verdict||'');lang=String(d.language||d.lang||'');
claim=c?(typeof c==='string'?c:String(c.text||(c.claim&&c.claim.text)||'')):String(d.claim||'')}}catch(e){}
if(!V[v]){var st=res.querySelector('.stamp.big');if(st)for(var k in V)if(st.classList.contains(k))v=k}
if(!claim){var td=res.querySelector('tbody tr td');if(td&&td.firstChild)claim=td.firstChild.textContent||''}
claim=claim.replace(/\s+/g,' ').trim();if(!claim||!V[v])return null;
if(claim.length>140)claim=claim.slice(0,139)+'…';
if(!lang){var lg=$('lang');lang=lg&&lg.value!=='auto'?lg.value:''}
return{ts:Date.now(),verdict:v,claim:claim,lang:lang.slice(0,8)}};
var record=function(){var r=readResult();if(!r)return;var a=load().filter(function(h){return h.claim!==r.claim});a.unshift(r);save(a)};
var render=function(){var panel=$('mychecks'),list=$('mychecks-list');if(!panel||!list)return;var a=load();
if(!a.length){panel.hidden=true;return}
panel.hidden=false;$('mychecks-n').textContent='('+a.length+')';list.textContent='';
a.forEach(function(h){var li=document.createElement('li'),tag=document.createElement('span'),cl=document.createElement('div'),meta=document.createElement('div'),dt=document.createElement('span'),b=document.createElement('button');
tag.className='tag '+h.verdict;tag.textContent=h.verdict;cl.className='claim';cl.textContent=h.claim;meta.className='meta';
try{dt.textContent=new Date(h.ts).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'})}catch(e){}
b.type='button';b.className='btn ghost';b.textContent='Check again';
b.addEventListener('click',function(){var ta=$('text');if(!ta)return;ta.value=h.claim;ta.dispatchEvent(new Event('input'));var ck=$('checker');if(ck)ck.scrollIntoView({behavior:'smooth',block:'center'});ta.focus()});
meta.appendChild(dt);meta.appendChild(b);li.appendChild(tag);li.appendChild(cl);li.appendChild(meta);list.appendChild(li)})};
var clr=$('mychecks-clear');if(clr)clr.addEventListener('click',function(){if(confirm('Clear all saved checks on this device?')){try{localStorage.removeItem(KEY)}catch(e){}render()}});
try{record()}catch(e){}
try{render()}catch(e){}
})();
"""

SCRIPT = "<script>" + JS + "</script>"
