"""Sach website: editorial 'corrections desk' design. Server-rendered, no framework, tiny inline JS."""
from __future__ import annotations
import html, json, os
from urllib.parse import quote
from . import ledger
from .i18n import LABEL

REPO = "https://github.com/pruthvig1998/sach-check"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CHARS = 4000
REPLY_LANGS = ("auto", "en", "hi", "te", "tl")

# Verified forwards (each checked against the live pipeline before being listed here).
EXAMPLES = [
    {"verdict": "FALSE", "lang": "EN", "title": "Fake scheme",
     "text": "Government is giving Rs 1000 to everyone under Corona Sahayata Yojana. Click the link to register. Please forward to all groups!"},
    {"verdict": "TRUE", "lang": "EN", "title": "Real announcement",
     "text": "The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore."},
    {"verdict": "MISLEADING", "lang": "EN", "title": "Right scheme, wrong date",
     "text": "The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021 to March 2030."},
    {"verdict": "FALSE", "lang": "TINGLISH", "title": "Tinglish forward",
     "text": "Central sarkaru employees retirement age ni 50 years ki taggistundi ani message vachindi"},
    {"verdict": "FALSE", "lang": "HI", "title": "हिन्दी फ़ॉरवर्ड",
     "text": "सरकार कोरोना सहायता योजना के तहत सभी को 1000 रुपये दे रही है। जल्दी रजिस्टर करें, सबको शेयर करें।"},
]

FAQ = [
    ("Is Sach an official government service?", "No. Sach is an independent open-source project. It cites official sources such as PIB and ministry sites, and shows you the link, but it does not speak for the government."),
    ("Why does it so often say “unverified”?", "Because guessing is worse. If we cannot find an official source that confirms or denies a claim, we say so plainly. “Unverified” is a respectable answer; wrongly calling something false is the one failure we refuse to ship."),
    ("What is the difference between false and misleading?", "False means an official source directly contradicts the claim. Misleading means the core fact is real, but the forward gets the numbers, dates or framing wrong, for example the right scheme with the wrong amount."),
    ("Can fact-checkers like Alt News or BOOM decide a verdict?", "No. They are shown as secondary evidence and clearly labelled “not official”. Only PIB or an official source can make a claim false or true."),
    ("Which languages work?", "English, Hindi, Telugu, Hinglish and Tinglish (Telugu in English letters). The verdict card is written in the language of the forward; Tinglish gets a Tinglish card. Hindi and Telugu wording is human-written but still awaiting native-speaker review."),
    ("What happens to what I paste?", "Only the individual claims (not the whole message, and nothing about you) are added to the public ledger, with their verdicts and sources."),
    ("A verdict looks wrong. What do I do?", "Use the “Report a wrong verdict” link under any result. It opens a pre-filled issue on GitHub so we can look at the exact sources used."),
]

FONTS = ("https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,700;0,9..144,900;1,9..144,500"
         "&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500"
         "&family=Noto+Sans+Devanagari:wght@400;600&family=Noto+Sans+Telugu:wght@400;600&display=swap")

CSS = """
:root{--paper:#f2ebdb;--paper2:#e9e0cb;--card:#fffdf6;--field:#fff;--ink:#17140f;--mute:#5d564a;--rule:#17140f;--dot:rgba(23,20,15,.06);
--false:#c2321f;--true:#1f7a45;--mis:#c9780a;--unv:#6b6558;--wa:#dcf8c6;--wa-ink:#17140f;
--serif:'Fraunces','Noto Serif Devanagari',Georgia,serif;--sans:'Instrument Sans','Noto Sans Devanagari','Noto Sans Telugu',sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#15130f;--paper2:#201d17;--card:#1b1914;--field:#12100d;--ink:#f1eadb;--mute:#a79f8d;--rule:#f1eadb;--dot:rgba(241,234,219,.06);
--false:#ef6a55;--true:#4fbf80;--mis:#e8a23b;--unv:#9a9383;--wa:#1f4d32;--wa-ink:#eaf6ea}}
:root[data-theme=dark]{--paper:#15130f;--paper2:#201d17;--card:#1b1914;--field:#12100d;--ink:#f1eadb;--mute:#a79f8d;--rule:#f1eadb;--dot:rgba(241,234,219,.06);
--false:#ef6a55;--true:#4fbf80;--mis:#e8a23b;--unv:#9a9383;--wa:#1f4d32;--wa-ink:#eaf6ea}
*{box-sizing:border-box}html{scroll-behavior:smooth}
html,body{overflow-x:clip}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:17px;line-height:1.55;
background-image:radial-gradient(var(--dot) 1px,transparent 1px);background-size:5px 5px}
a{color:inherit}.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
.skip{position:absolute;left:-999px}.skip:focus{left:10px;top:10px;background:#fff;color:#000;padding:8px;z-index:99}
header.nav{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--paper) 94%,transparent);backdrop-filter:blur(6px);border-bottom:2px solid var(--rule)}
.nav .wrap{display:flex;align-items:center;flex-wrap:wrap;gap:6px 22px;min-height:58px;padding-top:6px;padding-bottom:6px}
.logo{font-family:var(--serif);font-weight:900;font-size:26px;text-decoration:none;letter-spacing:-.02em}
.logo small{font-weight:500;font-size:14px;margin-left:8px;color:var(--mute)}
.nav nav{margin-left:auto;display:flex;gap:18px;font-size:15px;font-weight:500;align-items:center}
.nav nav a{text-decoration:none;border-bottom:2px solid transparent}.nav nav a:hover{border-color:var(--ink)}
#theme{font:inherit;background:transparent;border:1.5px solid var(--ink);color:var(--ink);border-radius:99px;width:34px;height:34px;cursor:pointer}

.hero{padding:56px 0 34px;display:grid;grid-template-columns:1.25fr .75fr;gap:30px;align-items:center}
@media(max-width:860px){.hero{grid-template-columns:1fr}}
.kicker{font-family:var(--mono);font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}
h1{font-family:var(--serif);font-weight:900;font-size:clamp(40px,7vw,84px);line-height:.98;letter-spacing:-.035em;margin:12px 0 18px}
h1 em{font-style:italic;font-weight:500;color:var(--false)}
.lede{font-size:20px;max-width:34em}.scripts{font-family:var(--serif);font-size:20px;margin-top:14px;color:var(--mute)}
.stampbox{display:grid;grid-template-columns:1fr;gap:38px;align-content:center;padding:14px 6px}
.stampbox .stamp:nth-child(odd){justify-self:start}.stampbox .stamp:nth-child(even){justify-self:end}
.stamp{font-family:var(--serif);font-weight:900;text-transform:uppercase;letter-spacing:.06em;border:6px solid currentColor;
border-radius:10px;padding:8px 22px;transform:rotate(-8deg);position:relative;display:inline-block;opacity:.92;white-space:nowrap}
.stamp::after{content:"";position:absolute;inset:-6px;border:2px solid currentColor;border-radius:14px;opacity:.5}
.stamp.big{font-size:clamp(34px,6vw,54px)}.stamp.sm{font-size:20px;border-width:3px;padding:3px 12px;transform:rotate(-4deg)}
.stamp.FALSE{color:var(--false)}.stamp.TRUE{color:var(--true)}.stamp.MISLEADING{color:var(--mis)}.stamp.UNVERIFIED{color:var(--unv)}
.stampbox .stamp{font-size:clamp(22px,4vw,30px);padding:6px 16px;border-width:4px;animation:drop .7s both}
.stampbox .stamp:nth-child(1){transform:rotate(-8deg);animation-delay:.2s}.stampbox .stamp:nth-child(2){transform:rotate(6deg);animation-delay:.45s}
.stampbox .stamp:nth-child(3){transform:rotate(4deg);animation-delay:.7s}.stampbox .stamp:nth-child(4){transform:rotate(-5deg);animation-delay:.95s}
@keyframes drop{from{opacity:0;scale:2.2}to{opacity:.92;scale:1}}
@media(prefers-reduced-motion:reduce){.stamp{animation:none!important}html{scroll-behavior:auto}}
section{padding:46px 0;border-top:2px solid var(--rule)}
h2{font-family:var(--serif);font-weight:900;font-size:clamp(28px,4vw,44px);letter-spacing:-.02em;margin:0 0 6px}
.sub{color:var(--mute);max-width:42em;margin:0 0 26px}
.checker{background:var(--card);border:2px solid var(--rule);box-shadow:8px 8px 0 var(--rule);padding:24px;border-radius:4px}
select{font:inherit;font-size:16px;padding:10px 12px;border:2px solid var(--rule);background:var(--field);color:var(--ink);border-radius:3px}
textarea,input[type=search]{width:100%;font:inherit;font-size:18px;padding:14px;border:2px solid var(--rule);background:var(--field);color:var(--ink);border-radius:3px}
textarea{min-height:170px;resize:vertical}input[type=search]{font-size:16px;padding:9px 12px;max-width:340px}
textarea:focus,input:focus,button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid var(--mis);outline-offset:2px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:14px}
.btn{font:inherit;font-weight:600;font-size:17px;background:var(--ink);color:var(--paper);border:2px solid var(--ink);padding:11px 24px;border-radius:3px;cursor:pointer;text-decoration:none;display:inline-block}
.btn:hover{background:var(--false);border-color:var(--false);color:#fff}.btn.ghost{background:transparent;color:var(--ink)}.btn.ghost:hover{background:var(--ink);color:var(--paper)}
.btn[disabled]{opacity:.6;cursor:wait}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px}
.chip{font:inherit;font-size:14px;border:1.5px dashed var(--ink);background:transparent;color:var(--ink);padding:6px 12px;border-radius:99px;cursor:pointer}
.chip:hover{background:var(--paper2)}.chip b{font-family:var(--mono);font-size:11px;margin-right:6px;padding:1px 6px;border-radius:3px;color:#fff}
.chip b.FALSE,.tag.FALSE{background:#b3281a}.chip b.TRUE,.tag.TRUE{background:#17703c}.chip b.MISLEADING,.tag.MISLEADING{background:#a86207}.chip b.UNVERIFIED,.tag.UNVERIFIED{background:#5b5649}
.note{font-size:14px;color:var(--mute)}#count{font-family:var(--mono);font-size:12px;color:var(--mute);margin-left:auto}
#busy{display:none;margin-top:16px;font-family:var(--mono);font-size:14px}
#busy.on{display:block}#busy i{display:inline-block;width:10px;height:10px;background:var(--false);border-radius:50%;margin-right:8px;animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.25;transform:scale(.7)}}
.result{margin-top:30px;display:grid;grid-template-columns:auto 1fr;gap:26px;align-items:start;scroll-margin-top:80px}
@media(max-width:760px){.result{grid-template-columns:1fr}}
.bubble{background:var(--wa);color:var(--wa-ink);border-radius:10px 10px 10px 0;padding:14px 16px;font-size:17px;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 0 rgba(0,0,0,.25);max-width:520px}
.bubble small{display:block;text-align:right;opacity:.6;font-size:11px;margin-top:6px}
table{width:100%;border-collapse:collapse;font-size:15px}th{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;text-align:left;color:var(--mute)}
td,th{padding:9px 10px 9px 0;border-bottom:1px solid color-mix(in srgb,var(--ink) 25%,transparent);vertical-align:top}
.tag{font-family:var(--mono);font-size:12px;font-weight:500;padding:2px 8px;border-radius:3px;color:#fff;white-space:nowrap}
.cite{font-family:var(--mono);font-size:13px;word-break:break-all}.cite span{color:var(--mute)}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
@media(max-width:900px){.grid4{grid-template-columns:1fr 1fr}}@media(max-width:600px){.grid4{grid-template-columns:1fr}}
.card{background:var(--card);border:2px solid var(--rule);padding:18px;border-radius:4px}
.card h3{font-family:var(--serif);font-size:21px;margin:8px 0 6px}.card p{margin:0;font-size:15px}
.num{font-family:var(--serif);font-weight:900;font-size:44px;line-height:1;color:var(--false)}.num.g{color:var(--true)}
.step .n{font-family:var(--mono);font-size:13px;color:var(--mute)}
.tier{display:flex;gap:16px;align-items:baseline;padding:14px 0;border-bottom:1px solid color-mix(in srgb,var(--ink) 25%,transparent)}
.tier .t{font-family:var(--mono);font-size:12px;min-width:104px;padding:3px 8px;text-align:center;border:1.5px solid var(--ink);border-radius:3px}
.honest{background:var(--paper2);border-left:6px solid var(--mis);padding:16px 20px;border-radius:2px}
.honest ul{margin:8px 0 0;padding-left:20px}.honest li{margin:4px 0;font-size:15px}
details{border-bottom:1px solid color-mix(in srgb,var(--ink) 25%,transparent);padding:14px 0}summary{cursor:pointer;font-weight:600;font-size:18px}details p{margin:10px 0 0;max-width:46em}
pre.code{background:var(--field);border:1.5px solid var(--rule);padding:14px;overflow-x:auto;font-family:var(--mono);font-size:13px;border-radius:3px}
footer{border-top:2px solid var(--rule);padding:30px 0 50px;font-size:14px;color:var(--mute)}
footer .wrap{display:flex;flex-wrap:wrap;gap:12px 28px;justify-content:space-between}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px;align-items:center}.filters button{font:inherit;font-size:14px;padding:5px 14px;border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:99px;cursor:pointer}
.filters button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
@media(max-width:860px){.hero{grid-template-columns:1fr;padding:34px 0 10px}.stampbox{gap:22px;padding:6px}.stampbox .stamp{font-size:clamp(18px,5vw,26px);padding:4px 12px;border-width:3px}h1{font-size:clamp(40px,11vw,64px)}}
@media(max-width:560px){.nav .wrap{gap:0 12px;padding-top:4px;padding-bottom:4px;min-height:0}.logo{font-size:22px}.logo small{font-size:12px}.nav nav{gap:4px 8px;font-size:12.5px;width:100%;margin-left:0;justify-content:space-between;white-space:nowrap}#theme{width:28px;height:28px;flex:none}.wrap{padding:0 16px}}
#tip .tipgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}
@media(max-width:900px){#tip .tipgrid{grid-template-columns:1fr 1fr}}
.tipcard{display:block;text-decoration:none;background:var(--card);border:2px solid var(--rule);border-radius:4px;padding:14px;transition:transform .12s}
.tipcard:hover{transform:rotate(-1.2deg) translateY(-2px);box-shadow:4px 4px 0 var(--rule)}
.tipcard .amt{font-family:var(--serif);font-weight:900;font-size:34px;line-height:1;color:var(--false)}
.tipcard b{display:block;margin-top:6px}.tipcard span.d{font-size:13px;color:var(--mute)}
.tipbox{display:flex;flex-wrap:wrap;gap:22px;align-items:center}#upiqr{background:#fff;padding:8px;border:2px solid var(--rule);border-radius:4px;width:170px;height:170px;display:block}
.tipmeter{margin:18px 0;display:flex;flex-wrap:wrap;gap:12px 18px;align-items:center}.tipmeter select{max-width:100%}.tipmeter b#fwamt{font-family:var(--serif);font-size:26px;color:var(--false)}.softtip{margin-top:12px;font-size:14px}.softtip a{font-weight:600}
.appbtn{display:flex;flex-direction:column;gap:2px;text-decoration:none;background:var(--card);border:2px solid var(--rule);border-radius:4px;padding:14px 16px;margin:10px 0;transition:transform .12s}
.appbtn:hover,.appbtn:focus-visible{transform:translateX(4px);box-shadow:4px 4px 0 var(--rule)}.appbtn b{font-family:var(--serif);font-size:22px;color:var(--ink)}.appbtn .txt>span{font-size:13px;color:var(--mute)}
.paywrap{max-width:560px;margin:0 auto;padding:30px 0 50px}
.appbtn{flex-direction:row!important;align-items:center;gap:14px!important}.appbtn .ico{flex:none;width:50px;height:50px;display:grid;place-items:center;background:var(--paper2);border-radius:12px;color:var(--ink)}
.appbtn .txt{display:flex;flex-direction:column;gap:2px}.appimg{display:block;width:50px;height:50px;border-radius:12px}
.otheramt{display:flex;flex-wrap:wrap;gap:10px 12px;align-items:center;margin:14px 0}.otheramt input[type=number]{width:9em;font:inherit;font-size:18px;padding:9px 12px;border:2px solid var(--rule);background:var(--field);color:var(--ink);border-radius:3px}
.tipcard.other{grid-column:1/-1;cursor:default}.tipcard.other:hover{transform:none;box-shadow:none}
.logonote{font-size:12px;color:var(--mute);margin-top:18px}
@media print{.tipcard,#upiqr{display:none}}
@media print{header.nav,footer,.chips,.row,#busy{display:none}body{background:#fff;color:#000}}
"""

JS = """
const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
const root=document.documentElement;try{const t=localStorage.getItem('sach-theme');if(t)root.dataset.theme=t}catch(e){}
const th=$('#theme');if(th)th.addEventListener('click',()=>{const dark=getComputedStyle(root).getPropertyValue('--paper').trim()==='#15130f';const n=dark?'light':'dark';root.dataset.theme=n;try{localStorage.setItem('sach-theme',n)}catch(e){}});
const ta=$('#text'),cnt=$('#count');
const upd=()=>{if(ta&&cnt)cnt.textContent=ta.value.length+' / '+ta.maxLength};if(ta){ta.addEventListener('input',upd);upd();
ta.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();$('#form').requestSubmit()}})}
$$('.chip').forEach(c=>c.addEventListener('click',()=>{ta.value=c.dataset.text;upd();ta.focus();$('#checker').scrollIntoView({behavior:'smooth',block:'center'})}));
const pb=$('#paste');if(pb)pb.addEventListener('click',async()=>{try{ta.value=(await navigator.clipboard.readText()).slice(0,ta.maxLength);upd();ta.focus()}catch(e){pb.textContent='Paste with Ctrl/Cmd+V'}});
const lg=$('#lang');if(lg){try{const v=localStorage.getItem('sach-lang');if(v&&!document.querySelector('#result')&&lg.value==='auto')lg.value=v}catch(e){}lg.addEventListener('change',()=>{try{localStorage.setItem('sach-lang',lg.value)}catch(e){}})}
const clr=$('#clear');if(clr)clr.addEventListener('click',()=>{ta.value='';upd();ta.focus()});
const f=$('#form');if(f)f.addEventListener('submit',e=>{if(!ta.value.trim()){e.preventDefault();ta.focus();return}$('#busy').classList.add('on');$('#go').disabled=true;$('#go').textContent='Checking…'});
window.addEventListener('pageshow',()=>{const g=$('#go');if(g){g.disabled=false;g.textContent='Check it';$('#busy').classList.remove('on')}});
const cp=$('#copy');if(cp)cp.addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#cardtext').innerText);cp.textContent='Copied ✓'}catch(e){const r=document.createRange();r.selectNodeContents($('#cardtext'));getSelection().removeAllRanges();getSelection().addRange(r);cp.textContent='Selected — press Ctrl/Cmd+C'}});
const c2=$('#copy2');if(c2)c2.addEventListener('click',async()=>{const t=$('#cardtext').innerText+'\\n\\n—— English ——\\n'+$('#cardtext_en').innerText;try{await navigator.clipboard.writeText(t);c2.textContent='Copied ✓'}catch(e){c2.textContent='Select & copy manually'}});
const dl=$('#dl');if(dl)dl.addEventListener('click',()=>{const lines=$('#cardtext').innerText.split('\\n'),W=900,pad=40,lh=44;
const c=document.createElement('canvas');c.width=W;c.height=pad*2+lines.length*lh+60;const x=c.getContext('2d');x.fillStyle='#dcf8c6';x.fillRect(0,0,W,c.height);
x.fillStyle='#17140f';x.font='600 30px sans-serif';let y=pad+30;lines.forEach(l=>{x.fillText(l.slice(0,70),pad,y);y+=lh});x.font='20px monospace';x.fillStyle='#555';x.fillText('Sach · checked '+new Date().toISOString().slice(0,10),pad,c.height-24);
const a=document.createElement('a');a.download='sach-verdict.png';a.href=c.toDataURL('image/png');a.click()});
const fw=$('#fw');if(fw){const go=$('#fwgo'),amt=$('#fwamt');const upd2=()=>{const n=parseInt(fw.value,10)||1,a=n*10;amt.textContent='₹'+a;go.href='/?view=pay&amt='+a;go.textContent='Chip in ₹'+a};fw.addEventListener('change',upd2);upd2()}
const r=$('#result');if(r)r.scrollIntoView({behavior:'smooth',block:'start'});
let fv='ALL';const apply=()=>{const q=($('#q')?.value||'').toLowerCase();let n=0;$$('tbody tr[data-v]').forEach(tr=>{const ok=(fv==='ALL'||tr.dataset.v===fv)&&tr.innerText.toLowerCase().includes(q);tr.style.display=ok?'':'none';if(ok)n++});const s=$('#shown');if(s)s.textContent=n+' shown';const e=$('#empty');if(e)e.style.display=n?'none':''};
$$('.filters button').forEach(b=>b.addEventListener('click',()=>{$$('.filters button').forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');fv=b.dataset.v;apply()}));
const q=$('#q');if(q){q.addEventListener('input',apply);apply()}
"""

esc = html.escape
LANG_NAME = {'en': 'English', 'hi': 'हिन्दी', 'te': 'తెలుగు', 'tl': 'Tinglish'}

# ---- Tip jar (UPI). Off unless SACH_UPI_ID is set in the environment; the ID is never stored in the repository. ----
import re as _re
from urllib.parse import quote as _q
_VPA = _re.compile(r"^[A-Za-z0-9._-]{2,64}@[A-Za-z]{2,32}$")
TIP_TIERS = [(20, "A cutting chai", "powers one forward through the desk"), (50, "Samosa for the fact-checker", "debunking is hungry work"),
             (100, "Bust ten forwards", "a whole family group's worth"), (500, "Sponsor a family-group intervention", "funds the desk for a week")]
TIP_HEADLINES = ["Fact-checking is free. Chai is not.", "Be the “Verified” in your family group.", "This desk runs on free tiers and strong chai.",
                 "WhatsApp University has no refund policy. We do the homework.", "Every tip is one fewer “Forwarded many times”.",
                 "Your uncle's forwards can't be fixed. This desk can be funded."]
TIP_QUIPS = {"FALSE": "Fake caught. Your family group thanks you.", "TRUE": "A real one! Celebrate with a samosa for the desk 🥟",
             "MISLEADING": "Half-truths are twice the work. Chai helps."}
PER_FORWARD = 10      # the "forwards saved" picker: ₹10 a forward

# Each UPI app's own link scheme. The generic upi:// scheme is claimed by many apps; on iPhone iOS then picks one at random
# (e.g. WhatsApp). App-specific schemes let the payer choose. Built on the server so the UPI address stays out of the HTML.
UPI_APPS = {"gpay": ("Google Pay", "gpay://upi/pay", "opens Google Pay"),
            "phonepe": ("PhonePe", "phonepe://pay", "opens PhonePe"),
            "paytm": ("Paytm", "paytmmp://pay", "opens Paytm"),
            "bhim": ("BHIM", "bhim://upi/pay", "opens BHIM"),
            "upi": ("Any other UPI app", "upi://pay", "your phone decides which app opens")}

# Logos: the apps' own App Store icons (96px), stored in sach/assets/app_icons with a NOTICE (third-party trademarks, not MIT).
# Embedded as data URIs so the chooser makes no third-party requests. If a file is missing the tile falls back to a generic glyph.
import base64 as _b64
_ICON_DIR = os.path.join(ROOT, "sach", "assets", "app_icons")

def _load_app_icons() -> dict:
    out = {}
    for key in ("gpay", "phonepe", "paytm", "bhim"):
        try:
            with open(os.path.join(_ICON_DIR, key + ".jpg"), "rb") as f:
                out[key] = _b64.b64encode(f.read()).decode()
        except OSError:
            pass
    return out

_APP_IMGS = _load_app_icons()

def app_icon(app: str) -> str:
    if app in _APP_IMGS:
        return f'<img class="appimg" src="data:image/jpeg;base64,{_APP_IMGS[app]}" width="50" height="50" alt="" decoding="async">'
    return ('<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" focusable="false">'
            '<rect x="7" y="2.5" width="10" height="19" rx="2.2"/><path d="M11 18.5h2"/></svg>')

def amount_form(value: int | None = None, compact: bool = False) -> str:
    """Custom amount box (GET form -> the app chooser). The server validates 1..10000 again, whatever the browser allows."""
    v = f' value="{value}"' if value else ""
    return (f'<form class="otheramt{" compact" if compact else ""}" method="get" action="/"><input type="hidden" name="view" value="pay">'
            f'<label for="oa{"2" if compact else ""}"><b>{"Change amount" if compact else "Amount"}</b> (₹)</label>'
            f'<input id="oa{"2" if compact else ""}" name="amt" type="number" inputmode="numeric" min="1" max="10000" step="1" placeholder="e.g. 75"{v} required>'
            f'<button class="btn" type="submit">Continue</button></form>')

def tip_headline() -> str:
    import datetime
    return TIP_HEADLINES[datetime.date.today().toordinal() % len(TIP_HEADLINES)]       # one per day: stable within a visit

def tip_amount(raw) -> int | None:
    """A tip amount from a query string: a whole number of rupees, 1..10000. Anything else means 'any amount'."""
    raw = (raw or "").strip()
    return int(raw) if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 10000 else None      # ASCII digits only (not "٥٠")

def tip_qr_svg(cfg: dict, amount: int | None = None) -> bytes | None:
    """A QR (generic upi:// so every UPI scanner reads it), drawn on the server so the address never appears in the page's HTML."""
    try:
        import io, segno
        buf = io.BytesIO()
        segno.make(upi_link(cfg, amount, "Sach tip"), error="m").save(buf, kind="svg", scale=5, border=2, xmldecl=False, svgns=True)
        return buf.getvalue()
    except Exception:
        return None

def tip_config():
    """Returns {'vpa','name'} when SACH_UPI_ID is a valid UPI address, else None (tip jar hidden)."""
    vpa = (os.environ.get("SACH_UPI_ID") or "").strip()
    if not _VPA.match(vpa):
        return None
    name = _re.sub(r"[^A-Za-z0-9 .&'-]", "", os.environ.get("SACH_UPI_NAME") or "Sach")[:40].strip() or "Sach"
    return {"vpa": vpa, "name": name}

def upi_link(cfg: dict, amount: int | None = None, note: str = "Sach tip", app: str = "upi") -> str:
    base = UPI_APPS.get(app, UPI_APPS["upi"])[1]                     # unknown app name -> the generic scheme, never an error
    q = f"pa={_q(cfg['vpa'], safe='@.-_')}&pn={_q(cfg['name'])}&cu=INR&tn={_q(note)}"
    return base + "?" + q + (f"&am={int(amount)}" if amount else "")


def eval_summary() -> dict:
    try:
        return json.load(open(os.path.join(ROOT, "data", "eval_summary.json"), encoding="utf-8"))
    except Exception:
        return {}


def layout(body: str, title="Sach — cited verdicts for viral forwards") -> bytes:
    cfg = tip_config()
    tip_link = ' · <a href="/#tip">Tip jar ☕</a>' if cfg else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="Paste a WhatsApp forward. Sach checks it against PIB and official sources and returns a cited verdict in English, Hindi or Telugu.">
<meta property="og:title" content="Sach — cited verdicts for viral forwards"><meta property="og:description" content="Got a forward? Get the receipts. PIB-first fact-checking in English, Hindi and Telugu.">
<meta name="theme-color" content="#f2ebdb"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23c2321f'/%3E%3Ctext x='32' y='45' font-size='40' text-anchor='middle' fill='white' font-family='serif' font-weight='900'%3ES%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet"><style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a>
<header class="nav"><div class="wrap"><a class="logo" href="/" title="Sach (Hindi सच) and nijam (Telugu నిజం) both mean “truth”">Sach<small><span class="sc">सच · నిజం · </span>truth</small></a>
<nav aria-label="Main"><a href="/#check">Check</a><a class="opt" href="/#how">How it works</a><a class="opt" href="/#rules">Rules</a><a class="opt" href="/#faq">FAQ</a>
<a href="/?view=ledger">Ledger</a><a class="opt" href="{REPO}" rel="noopener">GitHub</a><button id="theme" type="button" aria-label="Toggle dark mode" title="Toggle dark mode">◐</button></nav></div></header>
<main id="main">{body}</main>
<footer><div class="wrap"><div><b>Sach</b> · open source (MIT) · built for the Bharat Agentic-AI Hackathon.<br>Sach is not a government service. It cites official sources; it does not speak for them.</div>
<div>Sources: PIB · *.gov.in / *.nic.in · WHO · fact-checkers (labelled secondary)<br><a href="{REPO}" rel="noopener">Source code</a> · <a href="/?view=ledger">Public ledger</a> · <a href="/#api">API</a>{tip_link}</div></div></footer>
<script>{JS}</script></body></html>""".encode()


def stamp(v: str, cls="") -> str:
    return f'<span class="stamp {cls} {v}">{LABEL["en"][v]}</span>'


def result_block(res: dict, chosen: bool = False) -> str:
    v = res["verdict"]
    if res.get("no_claims"):
        return (f'<div class="result" id="result"><div><div class="stamp big UNVERIFIED">No claim</div></div>'
                f'<div><p class="kicker">Nothing to check</p><div class="bubble"><span id="cardtext">{esc(res["card"])}</span></div>'
                f'<p class="note" style="margin-top:14px">Greetings, links, emoji and bare numbers are not factual claims. Paste the sentence that makes the claim.</p></div></div>')
    rows = ""
    for c in res["claims"]:
        fmt = lambda x: (f'<div class="cite"><a href="{esc(x["url"])}" rel="noopener">{esc(x["source"])}</a> '
                         f'<span>· {esc(x["tier"].replace("_"," "))} · accessed {esc(x["date_accessed"])}</span></div>')
        cs = c["citations"]
        cites = "".join(fmt(x) for x in cs[:3]) or '<span class="note">No source found</span>'
        if len(cs) > 3:
            cites += f'<details><summary class="note">+{len(cs) - 3} more sources</summary>{"".join(fmt(x) for x in cs[3:])}</details>'
        rows += (f'<tr><td>{esc(c["claim"]["text"])}<br><span class="note">{esc(c["claim"]["domain"])} · {esc(c["reason_code"].replace("_"," "))}</span></td>'
                 f'<td><span class="tag {c["verdict"]}">{c["verdict"]}</span></td><td>{cites}</td></tr>')
    card = esc(res["card"])
    softtip = ""
    if tip_config() and v in TIP_QUIPS:
        softtip = f'<p class="softtip note">{esc(TIP_QUIPS[v])} <a href="/#tip">Chip in for the corrections desk ☕</a> (optional; never affects a verdict).</p>'
    notice = ""
    if res.get("degraded"):
        notice = ('<div class="honest" style="margin-top:18px" role="status"><b>Limited mode.</b> Our AI checker is unavailable or at capacity right now, '
                  'so Sach only reports a verdict when a PIB debunk clearly matches. Most results will say “unverified”; try again later for a fuller check.</div>')
    english = ""
    if res.get("card_en"):
        said = "".join(f'<li><span class="note">{esc(c["claim"]["text"])}</span><br><b>{esc(c["english"])}</b></li>' for c in res["claims"] if c.get("english"))
        english = (f'<div class="honest" style="margin-top:22px;border-left-color:var(--true)" id="english"><b>What this means in English</b>'
                   f'<div class="bubble" style="margin:10px 0;background:var(--paper)"><span id="cardtext_en">{esc(res["card_en"])}</span></div>'
                   + (f'<p class="note" style="margin:8px 0 4px">We understood the forward as:</p><ul style="padding-left:18px;margin:0">{said}</ul>' if said else
                      ('<p class="note" style="margin:8px 0 0">English rendering of the claim itself was not available for this check.</p>' if res.get('input_language', 'en') != 'en' else ''))
                   + '<div class="row"><button class="btn ghost" id="copy2" type="button">Copy both languages</button></div></div>')
    wa = "https://wa.me/?text=" + quote(res["card"])
    issue = (f"{REPO}/issues/new?title=" + quote(f"Wrong verdict? {v}") + "&body=" +
             quote("Claim(s):\n" + "\n".join("- " + c["claim"]["text"] for c in res["claims"]) + f"\n\nSach said: {v}\nWhat is wrong:\n"))
    return f"""<div class="result" id="result"><div><div class="stamp big {v}">{LABEL['en'][v]}</div></div>
<div><p class="kicker">Forward this card back to the group · reply language: {esc(LANG_NAME.get(res['language'], res['language'].upper()))}{' (your choice)' if chosen else ' (matched to the forward)'}</p>
<div class="bubble"><span id="cardtext">{card}</span><small>Sach ✓✓</small></div>
<div class="row"><button class="btn ghost" id="copy" type="button">Copy card</button><a class="btn" href="{esc(wa)}" rel="noopener">Share on WhatsApp</a>
<button class="btn ghost" id="dl" type="button">Download image</button></div>
{notice}{english}{softtip}<h3 style="font-family:var(--serif);margin:26px 0 6px">Claims checked</h3>
<div style="overflow-x:auto"><table><thead><tr><th>Claim</th><th>Verdict</th><th>Citations</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="note" style="margin-top:14px">Checked {esc(res['checked_at'][:16].replace('T',' '))} UTC. <a href="{esc(issue)}" rel="noopener">Report a wrong verdict</a></p></div></div>"""


def home(result: str = "", prefill: str = "", error: str = "", reply: str = "auto") -> bytes:
    chips = "".join(f'<button type="button" class="chip" data-text="{esc(e["text"])}"><b class="{e["verdict"]}">{e["verdict"]}</b>{esc(e["title"])} · {e["lang"]}</button>' for e in EXAMPLES)
    opts = "".join(f'<option value="{v}"{" selected" if v == reply else ""}>{esc(t)}</option>' for v, t in
                   (("auto", "Auto (match the forward)"), ("en", "English"), ("hi", "हिन्दी"), ("te", "తెలుగు"), ("tl", "Tinglish")))
    ev = eval_summary()
    stats = ""
    if ev:
        stats = f"""<div class="grid4" style="margin-bottom:22px">
<div class="card"><div class="num g">{ev['correct']}/{ev['n']}</div><p>claims judged exactly right</p></div>
<div class="card"><div class="num g">{ev['overclaimed_false']}</div><p>overclaimed FALSE: the failure we refuse to ship</p></div>
<div class="card"><div class="num g">{ev['abstained_wrong']}</div><p>wrong TRUE or FALSE verdicts</p></div>
<div class="card"><div class="num" style="color:var(--ink)">{ev['abstained']}</div><p>times it said “unverified” instead of guessing</p></div></div>"""
    cfg = tip_config()
    faq_items = list(FAQ) + ([("Do tips change what Sach says?", "Never. Verdicts come only from PIB and official sources and the rules above. Tips are optional, go straight from your UPI app to the person who runs Sach, and Sach never sees who paid or how much. Your UPI app will show you who you are paying before you confirm, as it does for every UPI payment.")] if cfg else [])
    faq = "".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in faq_items)
    tip_section = ""
    if cfg:
        cards = "".join(f'<a class="tipcard" href="/?view=pay&amp;amt={amt}" rel="nofollow"><div class="amt">₹{amt}</div><b>{esc(t)}</b><span class="d">{esc(d)}</span></a>'
                        for amt, t, d in TIP_TIERS)
        opts_fw = "".join(f'<option value="{n}"{" selected" if n == 3 else ""}>{n}</option>' for n in (1, 3, 5, 10, 20))
        tip_section = f'''<section id="tip"><div class="wrap"><p class="kicker">Nobody asked, but…</p><h2>{esc(tip_headline())} ☕</h2>
<p class="sub">Sach has no ads, no paywall and no “forward this to 10 groups or bad luck”. If a verdict saved you an awkward family-group moment, a small tip keeps the corrections coming. <b>Tips never change a verdict.</b></p>
<div class="tipmeter card"><label for="fw">You were about to forward</label><select id="fw" aria-label="Forwards we stopped">{opts_fw}</select><span>messages. At ₹{PER_FORWARD} a forward that's <b id="fwamt">₹{3 * PER_FORWARD}</b></span>
<a class="btn" id="fwgo" href="/?view=pay&amp;amt={3 * PER_FORWARD}" rel="nofollow" style="text-decoration:none">Chip in ₹{3 * PER_FORWARD}</a></div>
<div class="tipgrid">{cards}<div class="tipcard other"><div class="amt" style="font-size:24px">Other amount</div><span class="d">Any amount from ₹1 to ₹10,000</span>{amount_form()}</div></div>
<div class="tipbox"><img id="upiqr" src="/?view=tipqr" width="170" height="170" alt="UPI QR code for tips">
<div><p style="margin:0 0 8px"><b>On a phone:</b> tap an amount, then pick your UPI app (Google Pay, PhonePe, Paytm…). It opens with the amount filled in and you confirm there.<br><b>On a computer:</b> scan the QR code with any UPI app and enter any amount.</p>
<div class="row"><a class="btn" href="/?view=pay" rel="nofollow" style="text-decoration:none">Pay any amount</a></div>
<p class="note" style="margin:10px 0 0">Your UPI app shows who you're paying before you confirm; that's UPI's own safety check. Tips are optional and go straight from your app to the person who runs Sach. Sach never sees who paid or how much.</p></div></div></div></section>'''
    body = f"""<div class="wrap"><div class="hero"><div>
<p class="kicker">A corrections desk for your family group</p>
<h1>Got a forward? Get the <em>receipts.</em></h1>
<p class="lede">Paste a WhatsApp message. Sach splits it into claims, checks each against PIB and official sources, and hands back a verdict card you can forward straight into the group, with the link.</p>
<p class="scripts">English · हिन्दी · తెలుగు · Hinglish · Tinglish</p>
<p class="note" style="margin-top:6px"><b>Sach</b> (सच, Hindi) and <b>nijam</b> (నిజం, Telugu) both mean <b>“truth”</b>.</p>
<div class="row"><a class="btn" href="#check">Check a forward</a><a class="btn ghost" href="#how">How it works</a></div></div>
<div class="stampbox" aria-hidden="true">{stamp('FALSE')}{stamp('TRUE')}{stamp('MISLEADING')}{stamp('UNVERIFIED')}</div></div></div>

<section id="check"><div class="wrap"><h2>Check a forward</h2><p class="sub">Paste the whole message or a single claim. We reply in the language it was written in, or in any language you choose below. Checks usually take 10 to 30 seconds because we read the sources live.</p>
<div class="checker" id="checker"><form id="form" method="post" action="/#result"><label for="text" class="kicker">The forward</label>
<textarea id="text" name="text" placeholder="Paste the message here…" required maxlength="{MAX_CHARS}">{esc(prefill)}</textarea>
<div class="chips" role="group" aria-label="Try an example"><span class="note" style="align-self:center">Try:</span>{chips}</div>
<div class="row"><label for="lang" class="note" style="margin-right:-4px">Reply in:</label><select id="lang" name="lang" aria-label="Reply language">{opts}</select>
<button class="btn" id="go" type="submit">Check it</button><button class="btn ghost" id="paste" type="button">Paste</button><button class="btn ghost" id="clear" type="button">Clear</button>
<span id="count" aria-live="off"></span></div>
<p class="note" style="margin:10px 0 0">Tip: press Ctrl/Cmd + Enter to check. Only the individual claims (never your name) go to the public ledger.</p>
<div id="busy" role="status"><i></i>Reading PIB and official pages… this usually takes 10 to 30 seconds.</div></form>
{f'<p role="alert" style="color:var(--false);font-weight:600;margin-top:14px">{esc(error)}</p>' if error else ''}{result}</div></div></section>

<section id="how"><div class="wrap"><h2>How it works</h2><p class="sub">Four steps, all visible. Nothing is invented: a citation appears only if we actually fetched that page.</p>
<div class="grid4">
<div class="card step"><span class="n">01</span><h3>Split</h3><p>The forward is broken into atomic, checkable claims and tagged: scheme or money, health, news, other.</p></div>
<div class="card step"><span class="n">02</span><h3>Search</h3><p>PIB first, then official domains (*.gov.in, *.nic.in, WHO), then fact-checkers as secondary evidence.</p></div>
<div class="card step"><span class="n">03</span><h3>Judge</h3><p>Each source is judged confirms, contradicts or neither, and must quote the exact sentence it relies on.</p></div>
<div class="card step"><span class="n">04</span><h3>Reply</h3><p>A short card: verdict first, one line of why, the citation link, in the forward’s own language.</p></div></div></div></section>

<section id="rules"><div class="wrap"><h2>The verdict rules</h2><p class="sub">These are hard rules in code, covered by tests. They do not bend for a good guess.</p>
<div class="grid4">
<div class="card">{stamp('FALSE','sm')}<h3>False</h3><p>Only when PIB or an official source directly contradicts the claim.</p></div>
<div class="card">{stamp('TRUE','sm')}<h3>True</h3><p>Only when an official source directly confirms it, with the same numbers.</p></div>
<div class="card">{stamp('MISLEADING','sm')}<h3>Misleading</h3><p>The core fact is real, but the numbers, dates or framing in the forward are distorted.</p></div>
<div class="card">{stamp('UNVERIFIED','sm')}<h3>Unverified</h3><p>Everything else. No evidence is never “false”. Fact-checkers alone never decide a verdict.</p></div></div></div></section>

<section id="sources"><div class="wrap"><h2>Where the evidence comes from</h2><p class="sub">In this order, and always labelled.</p>
<div class="tier"><span class="t">1 · PIB</span><div><b>PIB Fact Check and press releases.</b> Has this exact claim already been debunked or announced? We search PIB first, using a growing local index of PIB debunks and announcements plus live search, and re-read every page before citing it.</div></div>
<div class="tier"><span class="t">2 · OFFICIAL</span><div><b>Ministry and department sites,</b> scheme guideline pages, WHO and ICMR for health, plus the Reserve Bank of India, MyGov, NPCI and Parliament (sansad.in). Any *.gov.in, *.nic.in or who.int page counts.</div></div>
<div class="tier"><span class="t">3 · SECONDARY</span><div><b>Alt News, BOOM, Vishvas News.</b> Shown as “fact-checker (not official)”. They can support a note, never a verdict.</div></div></div></section>

<section id="evidence"><div class="wrap"><h2>Does it actually work?</h2><p class="sub">We tested it on real PIB debunks, real government announcements, and invented claims that should be left unverified. The misses are published too.</p>
{stats}<div class="honest"><b>Read this before trusting the numbers</b><ul>
<li>It is a small set ({ev.get('n','?')} claims), and two labels were corrected after we looked at the evidence. Treat it as indicative.</li>
<li>These numbers were measured before our latest safety hardening. A fresh run is waiting for the free AI quota to reset; when the AI checker is unavailable the site says so (“Limited mode”) and reports only clear PIB debunks.</li>
<li>Many FALSE items are paraphrases of PIB debunk titles, so recall there is optimistic.</li>
<li>Results move by a claim or two between runs, because live search returns different pages.</li>
<li>Hindi and Telugu verdict wording is human-written but still awaiting native-speaker review.</li></ul>
<p class="note" style="margin:10px 0 0"><a href="{REPO}/blob/main/docs/evaluation.md" rel="noopener">Full table with every claim and failure →</a></p></div></div></section>

{tip_section}<section id="faq"><div class="wrap"><h2>Questions</h2><p class="sub">Short, honest answers.</p>{faq}</div></section>

<section id="api"><div class="wrap"><h2>Use it from code</h2><p class="sub">The same checker is available as JSON. Be kind: each call reads live sources and usually takes 10 to 30 seconds.</p>
<pre class="code">curl -s -X POST "https://sach-check-lilac.vercel.app/?format=json" \\
  --data-urlencode "text=Government is giving Rs 1000 under Corona Sahayata Yojana" \\
  --data-urlencode "lang=te"      # optional reply language: auto (default), en, hi, te, tl

→ {{"verdict":"FALSE","language":"en","card":"…","claims":[{{"verdict":"FALSE","citations":[{{"url":"https://pib.gov.in/…"}}]}}]}}</pre>
<div class="row"><a class="btn ghost" href="/?view=ledger">Open the public ledger →</a><a class="btn ghost" href="{REPO}" rel="noopener">Source on GitHub →</a></div></div></section>"""
    return layout(body)


def pay_page(amount: int | None = None, bad_amount: bool = False) -> bytes:
    """Pick-your-UPI-app page. Every button is a server redirect, so the UPI address is not in this page's HTML."""
    amt_q = f"&amp;amt={amount}" if amount else ""
    shown = f"₹{amount}" if amount else "any amount"
    buttons = "".join(f'<a class="appbtn" href="/?go=tip{amt_q}&amp;app={k}" rel="nofollow"><span class="ico">{app_icon(k)}</span>'
                      f'<span class="txt"><b>{esc(name)}</b><span>{esc(hint)}</span></span></a>' for k, (name, _scheme, hint) in UPI_APPS.items())
    err = ('<p role="alert" style="color:var(--false);font-weight:600;margin:0 0 10px">Please enter a whole number of rupees from 1 to 10,000. '
           'You can also pick an app now and type the amount there.</p>') if bad_amount else ""
    body = f"""<div class="wrap"><div class="paywrap"><p class="kicker">Chip in for the corrections desk ☕</p>
<h1 style="font-size:clamp(34px,8vw,54px);margin:6px 0 10px">Pay {esc(shown)}</h1>
{err}<p class="sub" style="margin-bottom:14px">Pick the app you use. Your phone may ask “open another application?”; say yes. The amount is filled in and <b>you confirm the payment inside that app</b>.</p>
{buttons}
{amount_form(amount, compact=True)}
<p class="note">iPhone tip: if you choose “Any other UPI app”, iOS decides which app opens and it may not be the one you wanted (for example WhatsApp). Choosing your app above avoids that. App not installed? Use the QR below or go back.</p>
<h2 style="font-size:24px;margin:26px 0 8px">On a computer?</h2>
<div class="tipbox"><img id="upiqr" src="/?view=tipqr{amt_q}" width="170" height="170" alt="UPI QR code for tips">
<p class="note" style="margin:0;max-width:22em">Scan this with any UPI app{f" (it already has {esc(shown)} filled in)" if amount else " and enter any amount"}. Tips are optional and never change a verdict.</p></div>
<p style="margin-top:24px"><a class="btn ghost" href="/#tip" style="text-decoration:none">← Back to the tip jar</a></p>
<p class="logonote">App names and logos belong to their owners (Google LLC, PayTM Mobile Solutions, NPCI, PhonePe) and are shown only to help you recognise the app. Sach is not affiliated with them. The icons are the apps own App Store icons; the "other app" icon is a generic glyph.</p></div></div>"""
    return layout(body, "Chip in — Sach")


def ledger_page() -> bytes:
    rows = ""
    data = list(reversed(ledger.load()))
    for r in data:
        cites = "".join(f'<div class="cite"><a href="{esc(c["url"])}" rel="noopener">{esc(c["source"])}</a> <span>· {esc(c["tier"].replace("_"," "))} · {esc(c["date_accessed"])}</span></div>'
                        for c in r["citations"]) or '<span class="note">none found</span>'
        rows += (f'<tr data-v="{esc(r["verdict"])}"><td>{esc(r["claim"])}</td><td><span class="tag {esc(r["verdict"])}">{esc(r["verdict"])}</span></td>'
                 f'<td>{cites}</td><td class="note">{esc(r["checked_at"][:10])}</td></tr>')
    if not rows:
        rows = '<tr data-v="NONE"><td colspan="4" class="note">No claims checked yet.</td></tr>'
    btns = "".join(f'<button type="button" data-v="{v}" aria-pressed="{"true" if v=="ALL" else "false"}">{v.title() if v!="ALL" else "All"}</button>'
                   for v in ("ALL", "FALSE", "TRUE", "MISLEADING", "UNVERIFIED"))
    body = f"""<div class="wrap"><section style="border:0"><p class="kicker">Public record</p><h2>Evidence ledger</h2>
<p class="sub">{len(data)} checked claims. Each row lists the sources we actually fetched, with the date we accessed them. On this free deployment the live part of the ledger resets when the server restarts; the repository holds the permanent record.</p>
<div class="filters" role="group" aria-label="Filter by verdict">{btns}<input id="q" type="search" placeholder="Search claims or sources…" aria-label="Search the ledger"><span class="note" id="shown"></span></div>
<div style="overflow-x:auto"><table><thead><tr><th>Claim</th><th>Verdict</th><th>Citations</th><th>Checked</th></tr></thead><tbody>{rows}<tr id="empty" style="display:none"><td colspan="4" class="note">No claims match your filter.</td></tr></tbody></table></div></section></div>"""
    return layout(body, "Evidence ledger — Sach")
