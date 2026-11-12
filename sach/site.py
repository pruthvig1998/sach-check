"""Sach website: editorial 'corrections desk' design. Server-rendered, no framework, tiny inline JS."""
from __future__ import annotations
import html, json, os
from urllib.parse import quote
from . import ledger, pwa
from .i18n import LABEL, text_lang
from .lang import SUPPORTED, NAMES, NATIVE, RTL, INDIAN_LANGS, html_lang
from .report import report_html, card_data_script
from .ocr import OCR_BLOCK
from .scamsigns import CSS as SIGNS_CSS, signs_html
from .siteurl import site_url        # noqa: F401  (re-exported: the one place that knows the site's public address)
from .voice import VOICE_JS, VOICE_CSS, voice_controls, progress_panel, listen_buttons

REPO = "https://github.com/pruthvig1998/sach-check"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CHARS = 4000
REPLY_LANGS = ("auto",) + SUPPORTED      # "auto" (match the forward) or any language code in lang.SUPPORTED
N_INDIAN = len(INDIAN_LANGS)          # "English and N Indian languages" in the hero and meta lines: always computed, never typed

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
    ("Can fact-checkers like BOOM or Newschecker decide a verdict?", "No. They are shown as secondary evidence and clearly labelled “not official”. Only PIB or an official source can make a claim false or true."),
    ("Which languages work?", f"English and {N_INDIAN} Indian languages: " + ", ".join(NAMES[c] for c in INDIAN_LANGS) + ", plus Hinglish and Tinglish (Telugu in English letters). The verdict card is written in the language of the forward, or in the language you pick under “Reply in”, with the English meaning beside it. The wording in every language except English is AI-written and still awaiting native-speaker review. The full list is in the Languages section above."),
    ("What happens to what I paste?", "Only the individual claims (not the whole message, and nothing about you) are added to the public ledger, with their verdicts and sources."),
    ("A verdict looks wrong. What do I do?", "Use the “Report a wrong verdict” link under any result. It opens a pre-filled issue on GitHub so we can look at the exact sources used."),
]

FONTS = ("https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,700;0,9..144,900;1,9..144,500"
         "&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500"
         "&family=Noto+Sans+Devanagari:wght@400;600&family=Noto+Sans+Telugu:wght@400;600"
         # Other Indian scripts and Urdu. Google Fonts serves each as unicode-range subsets, so a browser downloads a face only when a
         # character of that script is on the page: nothing extra is fetched for English, Hindi or Telugu pages.
         "&family=Noto+Sans+Bengali:wght@400;600&family=Noto+Sans+Gurmukhi:wght@400;600&family=Noto+Sans+Gujarati:wght@400;600"
         "&family=Noto+Sans+Oriya:wght@400;600&family=Noto+Sans+Tamil:wght@400;600&family=Noto+Sans+Kannada:wght@400;600"
         "&family=Noto+Sans+Malayalam:wght@400;600&family=Noto+Sans+Meetei+Mayek:wght@400;600&family=Noto+Nastaliq+Urdu:wght@400;600&family=Noto+Sans+Arabic:wght@400;600"
         "&display=swap")

CSS = """
:root{--paper:#f2ebdb;--paper2:#e9e0cb;--card:#fffdf6;--field:#fff;--ink:#17140f;--mute:#5d564a;--rule:#17140f;--dot:rgba(23,20,15,.06);
--false:#c2321f;--true:#1f7a45;--mis:#c9780a;--unv:#6b6558;--wa:#dcf8c6;--wa-ink:#17140f;
--serif:'Fraunces','Noto Serif Devanagari','Noto Sans Bengali','Noto Sans Gurmukhi','Noto Sans Gujarati','Noto Sans Oriya','Noto Sans Tamil','Noto Sans Kannada','Noto Sans Malayalam','Noto Sans Meetei Mayek','Noto Sans Arabic',Georgia,serif;--sans:'Instrument Sans','Noto Sans Devanagari','Noto Sans Telugu','Noto Sans Bengali','Noto Sans Gurmukhi','Noto Sans Gujarati','Noto Sans Oriya','Noto Sans Tamil','Noto Sans Kannada','Noto Sans Malayalam','Noto Sans Meetei Mayek','Noto Sans Arabic',sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace}
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
details.trace{margin-top:22px;border:1px solid color-mix(in srgb,var(--ink) 25%,transparent);border-radius:4px;padding:12px 14px;background:var(--card)}
details.trace summary{font-size:16px}.trace .tc{margin:14px 0 0;padding-top:12px;border-top:1px solid color-mix(in srgb,var(--ink) 25%,transparent);overflow-wrap:anywhere}
.trace ul{list-style:none;margin:8px 0;padding:0}.trace li{margin:0 0 10px;font-size:14px;overflow-wrap:anywhere;word-break:break-word}
.trace .st{font-family:var(--mono);font-size:11px;font-weight:500;padding:1px 6px;border-radius:3px;border:1px solid var(--mute);color:var(--mute);margin-right:6px;white-space:nowrap}
.trace .st.CONFIRMS{border-color:var(--true);color:var(--true)}.trace .st.CONTRADICTS{border-color:var(--false);color:var(--false)}.trace .st.PARTLY{border-color:var(--mis);color:var(--mis)}
.trace p{margin:6px 0;font-size:14px;max-width:none}.trace .rule{font-weight:600}
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
@media(max-width:420px){.nav nav{flex-wrap:wrap;white-space:normal;row-gap:2px;justify-content:flex-start}}
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
.tipcard[data-amt]{cursor:pointer}.tipcard.on{background:var(--paper2);box-shadow:4px 4px 0 var(--rule)}.tipcard:focus-visible{outline:3px solid var(--mis);outline-offset:2px}
.tipcard.other{grid-column:1/-1;cursor:default}.tipcard.other:hover{transform:none;box-shadow:none}
.logonote{font-size:12px;color:var(--mute);margin-top:18px}
dialog{border:2px solid var(--rule);border-radius:6px;background:var(--card);color:var(--ink);width:min(92vw,460px);padding:22px 22px 18px;box-shadow:8px 8px 0 var(--rule)}
dialog::backdrop{background:rgba(20,16,10,.55)}
dialog form.x{position:absolute;top:6px;right:8px;margin:0}dialog form.x button{font:inherit;font-size:22px;background:none;border:0;color:var(--ink);cursor:pointer;padding:6px 10px}
dialog img{display:block;background:#fff;padding:8px;border:2px solid var(--rule);border-radius:4px;margin:10px 0}
.linklike{font:inherit;background:none;border:0;padding:0;color:inherit;text-decoration:underline;cursor:pointer}
@media print{.tipcard,#upiqr,dialog{display:none}}
@media print{header.nav,footer,.chips,.row,#busy{display:none}body{background:#fff;color:#000}}
"""
CSS += SIGNS_CSS
# ---- Indian-language scripts, Urdu (right-to-left) and the "Reply in" selector (LANG work package) ----
CSS += """
#lang{min-height:44px;max-width:100%;min-width:0;flex:1 1 14em}
.bubble[dir=rtl]{text-align:right}.bubble[dir=rtl] small{text-align:left}
[lang=ur]{font-family:'Instrument Sans','Noto Nastaliq Urdu','Noto Sans Arabic',sans-serif;line-height:2.1}     /* Latin (PIB, URLs) in the site font, Urdu in Nastaliq */
[lang=ml],[lang=kn],[lang=ta],[lang=or],[lang=te],[lang=bn],[lang=as],[lang=pa],[lang=gu],[lang=mni]{line-height:1.75}
.langlist{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,140px),1fr));gap:8px 12px}
.langlist li{border:1.5px solid var(--rule);background:var(--card);padding:8px 12px;border-radius:3px;display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline;min-width:0}
.langlist b{font-weight:600;font-size:18px}.langlist span{font-size:13px;color:var(--mute)}
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
window.sachBindResult=()=>{const cp=$('#copy');if(cp)cp.addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#cardtext').innerText);cp.textContent='Copied ✓'}catch(e){const r=document.createRange();r.selectNodeContents($('#cardtext'));getSelection().removeAllRanges();getSelection().addRange(r);cp.textContent='Selected — press Ctrl/Cmd+C'}});
const c2=$('#copy2');if(c2)c2.addEventListener('click',async()=>{const t=$('#cardtext').innerText+'\\n\\n—— English ——\\n'+$('#cardtext_en').innerText;try{await navigator.clipboard.writeText(t);c2.textContent='Copied ✓'}catch(e){c2.textContent='Select & copy manually'}});
/* #dl: see the 'Shareable verdict image' block below (before result_block) */
};window.sachBindResult();
let alt=false;const qsAlt=()=>alt?'&alt=1':'';
$$('.altswap').forEach(b=>b.addEventListener('click',()=>{alt=!alt;
$$('.qrimg').forEach(i=>{i.src='/?view=tipqr&fmt=png'+qsAlt()});$$('.dlpng').forEach(a=>{a.href='/?view=tipqr&fmt=png'+qsAlt()});
$$('.qrlabel').forEach(l=>{l.textContent=alt?'Code B':'Code A'});$$('.altswap').forEach(x=>{x.textContent=alt?'Back to code A':'Code not working? Try code B'});
const ap=$('#dlgapps');if(ap)ap.href=ap.href.replace(/&alt=1/,'')+qsAlt()}));
const want=$('#want'),dlg=$('#paydlg');
const setAmt=a=>{if(want)want.textContent=a?('₹'+a):'any amount';$$('.tipcard[data-amt]').forEach(c=>c.classList.toggle('on',String(c.dataset.amt)===String(a)))};
let curAmt=30;const openPay=a=>{curAmt=a;const ra=$('#rzpamt');if(ra)ra.textContent='₹'+a;const rm=$('#rzpmsg');if(rm)rm.textContent='';setAmt(a);if(!dlg)return;$('#dlgamt').textContent='₹'+a;$('#dlgamt2').textContent='₹'+a;const ap2=$('#dlgapps');if(ap2)ap2.href='/?view=pay&amt='+a+qsAlt();
if(typeof dlg.showModal==='function'){if(!dlg.open)dlg.showModal()}else{$('#upiqr').scrollIntoView({behavior:'smooth',block:'center'})}};
$$('.tipcard[data-amt]').forEach(c=>{const go=()=>openPay(c.dataset.amt);c.addEventListener('click',go);c.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}})});
const fw=$('#fw'),fwgo=$('#fwgo');
if(fw&&fwgo){const fwa=()=>(parseInt(fw.value,10)||1)*10;fw.addEventListener('change',()=>{const a=fwa();$('#fwamt').textContent='₹'+a;fwgo.textContent='Chip in ₹'+a;setAmt(a)});fwgo.addEventListener('click',()=>openPay(fwa()))}
const oa=$('#oa'),oago=$('#oago'),oaerr=$('#oaerr');
if(oa&&oago){const val=()=>{const v=parseInt(oa.value,10);return v>=1&&v<=10000?v:null};oa.addEventListener('input',()=>{oaerr.textContent='';setAmt(val())});
const go=()=>{const v=val();if(!v){oaerr.textContent='Enter a whole number from 1 to 10,000.';oa.focus();return}openPay(v)};oago.addEventListener('click',go);oa.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();go()}})}
const rgo=$('#rzpgo'),rmsg=$('#rzpmsg');
if(rgo){const say=t=>{if(rmsg)rmsg.textContent=t};
const loadRzp=()=>window.Razorpay?Promise.resolve():new Promise((ok,no)=>{const s=document.createElement('script');s.src='https://checkout.razorpay.com/v1/checkout.js';s.onload=ok;s.onerror=()=>no(new Error('load'));document.head.appendChild(s)});
const post=(api,b)=>fetch('/?api='+api,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>r.json().then(j=>({ok:r.ok,j})));
rgo.addEventListener('click',async()=>{rgo.disabled=true;say('Opening secure checkout…');
try{await loadRzp();const o=await post('rzp-order',{amount:curAmt});if(!o.ok)throw new Error(o.j.error||'Could not start checkout.');
const k=o.j;const back=()=>{if(dlg&&typeof dlg.showModal==='function'&&!dlg.open)dlg.showModal()};const rz=new window.Razorpay({key:k.key_id,amount:k.amount,currency:k.currency,order_id:k.order_id,name:'Sach',description:'Tip for the corrections desk',theme:{color:'#17140f'},
handler:async resp=>{back();say('Confirming…');const v=await post('rzp-verify',resp);say(v.ok&&v.j.verified?'Thank you! Your tip went through. 🙏':'Paid, but we could not confirm it here. Your bank will show the status.');rgo.disabled=false},
modal:{ondismiss:()=>{back();say('No problem. Nothing was charged.');rgo.disabled=false}}});
rz.on('payment.failed',r=>{back();say('Payment failed: '+((r.error&&r.error.description)||'please try again')+'.');rgo.disabled=false});if(dlg&&dlg.open)dlg.close();rz.open();}
catch(e){say(e.message==='load'?'Could not load checkout. Check your connection, or scan the code instead.':e.message);rgo.disabled=false}})}
if(dlg)dlg.addEventListener('click',e=>{if(e.target===dlg)dlg.close()});
const r=$('#result');if(r)r.scrollIntoView({behavior:'smooth',block:'start'});
let fv='ALL';const apply=()=>{const q=($('#q')?.value||'').toLowerCase();let n=0;$$('tbody tr[data-v]').forEach(tr=>{const ok=(fv==='ALL'||tr.dataset.v===fv)&&tr.innerText.toLowerCase().includes(q);tr.style.display=ok?'':'none';if(ok)n++});const s=$('#shown');if(s)s.textContent=n+' shown';const e=$('#empty');if(e)e.style.display=n?'none':''};
$$('.filters button').forEach(b=>b.addEventListener('click',()=>{$$('.filters button').forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');fv=b.dataset.v;apply()}));
const q=$('#q');if(q){q.addEventListener('input',apply);apply()}
"""

esc = html.escape
LANG_NAME = dict(NATIVE)      # the name of each language in its own script (shown in the result's 'reply language' line)

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

def tip_qr_png(cfg: dict, amount: int | None = None, alt: bool = False) -> bytes | None:
    """The same QR as a PNG, so a phone can save it to the gallery and scan it from there inside the UPI app."""
    try:
        import io, segno
        buf = io.BytesIO()
        segno.make(upi_link(cfg, amount, "Sach tip", alt=alt), error="m").save(buf, kind="png", scale=8, border=4)
        return buf.getvalue()
    except Exception:
        return None

def tip_qr_svg(cfg: dict, amount: int | None = None, alt: bool = False) -> bytes | None:
    """A QR (generic upi:// so every UPI scanner reads it), drawn on the server so the address never appears in the page's HTML."""
    try:
        import io, segno
        buf = io.BytesIO()
        segno.make(upi_link(cfg, amount, "Sach tip", alt=alt), error="m").save(buf, kind="svg", scale=5, border=2, xmldecl=False, svgns=True)
        return buf.getvalue()
    except Exception:
        return None

def tip_config():
    """Returns {'vpa','name'} when SACH_UPI_ID is a valid UPI address, else None (tip jar hidden)."""
    vpa = (os.environ.get("SACH_UPI_ID") or "").strip()
    if not _VPA.match(vpa):
        return None
    name = _re.sub(r"[^A-Za-z0-9 .&'-]", "", os.environ.get("SACH_UPI_NAME") or "Sach")[:40].strip() or "Sach"
    cfg = {"vpa": vpa, "name": name,
           # NPCI OC-76A: payer apps must reject link ("intent") payments to a PERSONAL UPI ID, so app buttons only make sense
           # when the operator marks the address as a merchant UPI ID.
           "merchant": (os.environ.get("SACH_UPI_MERCHANT") or "").strip().lower() in ("1", "true", "yes")}
    alt = (os.environ.get("SACH_UPI_ID_ALT") or "").strip()          # optional second UPI address for the SAME bank account
    if _VPA.match(alt) and alt.lower() != vpa.lower():
        cfg["alt_vpa"] = alt
    return cfg

def upi_link(cfg: dict, amount: int | None = None, note: str = "Sach tip", app: str = "upi", alt: bool = False) -> str:
    base = UPI_APPS.get(app, UPI_APPS["upi"])[1]                     # unknown app name -> the generic scheme, never an error
    vpa = cfg["alt_vpa"] if (alt and cfg.get("alt_vpa")) else cfg["vpa"]      # alt requested but not configured -> the main address
    q = f"pa={_q(vpa, safe='@.-_')}&pn={_q(cfg['name'])}&cu=INR&tn={_q(note)}"
    return base + "?" + q + (f"&am={int(amount)}" if amount else "")


EVAL_PATH = os.path.join(ROOT, "data", "eval_summary.json")      # tests point this at a temp file
EVAL_DOC = f"{REPO}/blob/main/docs/evaluation.md"


def eval_summary() -> dict:
    try:
        with open(EVAL_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def eval_display(ev: dict | None = None) -> dict | None:
    """What the home page may show about the evaluation, read from data/eval_summary.json at request time (never typed in).
    None means "Evaluation pending": the file is missing, marks itself degraded, or is the older format (no commit/date, or
    missing counts). Otherwise {n, correct, overclaims, abstained, commit (short hash), date}."""
    ev = eval_summary() if ev is None else ev
    if not isinstance(ev, dict) or not ev or ev.get("degraded") or str(ev.get("mode", "")).lower() in ("fallback", "degraded"):
        return None
    n, correct, of = _int(ev.get("n")), _int(ev.get("correct")), _int(ev.get("overclaimed_false"))
    commit, date = ev.get("commit"), ev.get("date")
    if not n or correct is None or of is None or not isinstance(commit, str) or not commit.strip() or not isinstance(date, str) or not date.strip():
        return None
    ot = _int(ev.get("overclaimed_true"))
    return {"n": n, "correct": correct, "overclaims": of + (ot or 0), "overclaimed_false": of, "overclaimed_true": ot,
            "abstained": _int(ev.get("abstained")), "commit": commit.strip()[:7], "date": date.strip()[:10]}


def eval_stats_html(d: dict | None) -> str:
    """The number cards plus the 'measured on' line, or the 'Evaluation pending' box. Every value is escaped."""
    if not d:
        return (f'<div class="honest" style="margin-bottom:22px" role="status"><b>Evaluation pending.</b> The last full evaluation run is out of date or incomplete, '
                f'so no numbers are shown here rather than old ones. <a href="{esc(EVAL_DOC)}" rel="noopener">What we measure and how →</a></div>')
    cards = (f'<div class="card"><div class="num" style="color:var(--ink)">{d["n"]}</div><p>claims in the evaluation set</p></div>'
             f'<div class="card"><div class="num g">{d["correct"]}/{d["n"]}</div><p>judged exactly right</p></div>'
             f'<div class="card"><div class="num{"" if d["overclaims"] else " g"}">{d["overclaims"]}</div><p>overclaims: said TRUE or FALSE without proof, the failure we refuse to ship</p></div>')
    if d["abstained"] is not None:
        cards += f'<div class="card"><div class="num" style="color:var(--ink)">{d["abstained"]}</div><p>times it said “unverified” instead of guessing</p></div>'
    return (f'<div class="grid4" style="margin-bottom:12px">{cards}</div>'
            f'<p class="note evmeta" style="margin:0 0 22px">Measured on commit <code>{esc(d["commit"])}</code>, {esc(d["date"])}. '
            f'<a href="{esc(EVAL_DOC)}" rel="noopener">Full table with every claim and failure →</a></p>')


DESC = f"Paste a WhatsApp forward. Sach checks it against PIB and official sources and returns a cited verdict in English and {N_INDIAN} Indian languages."
OG_DESC = f"Got a forward? Get the receipts. PIB-first fact-checking in English and {N_INDIAN} Indian languages."
OG_ALT = "Sach: a red S mark beside four tilted verdict stamps for true, false, misleading and unverified."
ROBOTS_INDEX, ROBOTS_NOINDEX = "index,follow", "noindex,follow"


def layout(body: str, title="Sach — cited verdicts for viral forwards", path: str = "/", noindex: bool = False) -> bytes:
    """`path` is the page's canonical path (never personal query params); `noindex` is for result and prefill pages."""
    cfg = tip_config()
    tip_link = ' · <a href="/#tip">Tip jar ☕</a>' if cfg else ""
    base = site_url()
    canon = esc(base + path, quote=True)
    img = esc(base + "/?view=ogimage", quote=True)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{DESC}">
<meta name="robots" content="{ROBOTS_NOINDEX if noindex else ROBOTS_INDEX}"><link rel="canonical" href="{canon}">
<meta property="og:title" content="Sach — cited verdicts for viral forwards"><meta property="og:description" content="{OG_DESC}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Sach"><meta property="og:locale" content="en_IN"><meta property="og:url" content="{canon}">
<meta property="og:image" content="{img}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="{esc(OG_ALT)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Sach — cited verdicts for viral forwards"><meta name="twitter:description" content="{OG_DESC}"><meta name="twitter:image" content="{img}"><meta name="twitter:image:alt" content="{esc(OG_ALT)}">
<meta name="theme-color" content="#f2ebdb"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23c2321f'/%3E%3Ctext x='32' y='45' font-size='40' text-anchor='middle' fill='white' font-family='serif' font-weight='900'%3ES%3C/text%3E%3C/svg%3E">
<link rel="icon" type="image/png" href="/?view=icon&amp;size=192">
{pwa.HEAD}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet"><style>{CSS}{VOICE_CSS}</style>
<script defer src="https://cdn.vercel-insights.com/v1/script.js"></script></head><body>
<a class="skip" href="#main">Skip to content</a>
<header class="nav"><div class="wrap"><a class="logo" href="/" title="Sach (Hindi सच) and nijam (Telugu నిజం) both mean “truth”">Sach<small><span class="sc">सच · నిజం · </span>truth</small></a>
<nav aria-label="Main"><a href="/#check">Check</a><a class="opt" href="/#how">How it works</a><a class="opt" href="/#rules">Rules</a><a class="opt" href="/#faq">FAQ</a>
<a href="/?view=ledger">Ledger</a><a class="opt" href="/?view=impact">Impact</a><a class="opt" href="{REPO}" rel="noopener">GitHub</a></nav><button id="theme" type="button" aria-label="Toggle dark mode" title="Toggle dark mode">◐</button></div></header>
<main id="main">{body}</main>
<footer><div class="wrap"><div><b>Sach</b> · open source (MIT) · built for the Bharat Agentic-AI Hackathon.<br>Sach is not a government service. It cites official sources; it does not speak for them.</div>
<div>Sources: PIB · *.gov.in / *.nic.in · WHO · fact-checkers (labelled secondary)<br><a href="{REPO}" rel="noopener">Source code</a> · <a href="/?view=ledger">Public ledger</a> · <a href="/?view=impact">Impact</a> · <a href="/#api">API</a>{tip_link}<br><a href="/?view=terms">Terms</a> · <a href="/?view=privacy">Privacy</a> · <a href="/?view=refund">Refunds</a> · <a href="/?view=contact">Contact</a></div></div></footer>
<script>{JS}</script><script>{VOICE_JS}</script>{pwa.SCRIPT}</body></html>""".encode()


def stamp(v: str, cls="") -> str:
    return f'<span class="stamp {cls} {v}">{LABEL["en"][v]}</span>'


_STANCE_WORD = {"confirms": "CONFIRMS", "contradicts": "CONTRADICTS", "mixed": "PARTLY", "none": "NEITHER"}
_TIER_WORD = {"pib_debunk": "PIB fact-check", "official": "official source", "factchecker": "fact-checker (not official)"}


def trace_block(res: dict) -> str:
    """Expandable 'how this verdict was reached' section. Plain <details>, so it works without JavaScript."""
    t = res.get("trace") or {}
    parts = [f'<p>Claims found in the message: <b>{esc(str(t.get("claims_extracted", len(res.get("claims", [])))))}</b></p>']
    for c in res.get("claims", []):
        ct = c.get("trace") or {}
        h = f'<div class="tc"><p><b>{esc(c["claim"]["text"])}</b></p>'
        if ct.get("searched_as") and ct["searched_as"] != c["claim"]["text"]:
            h += f'<p class="note">Searched as: {esc(ct["searched_as"])}</p>'
        srcs = ct.get("sources") or []
        if srcs:
            items = ""
            for x in srcs:
                w = _STANCE_WORD.get(x.get("stance"), "NEITHER")
                when = esc(str(x.get("fetched_at", ""))[:16].replace("T", " "))
                title = f' · {esc(x["title"])}' if x.get("title") else ""
                items += (f'<li><span class="st {w}">{w}</span><a href="{esc(x.get("url", ""))}" rel="noopener">{esc(x.get("source", ""))}</a>'
                          f'<br><span class="note">{esc(_TIER_WORD.get(x.get("tier"), str(x.get("tier", ""))))} · fetched {when} UTC{title}</span></li>')
            h += f'<p class="note">Sources judged for this claim:</p><ul>{items}</ul>'
        else:
            h += '<p class="note">No sources were found for this claim.</p>'
        if ct.get("rule_text"):
            h += f'<p class="rule">{esc(ct["rule_text"])}</p>'
        parts.append(h + "</div>")
    if t.get("overall_rule"):
        parts.append(f'<div class="tc"><p class="note">Overall result</p><p class="rule">{esc(t["overall_rule"])}</p></div>')
    return f'<details class="trace"><summary>How this verdict was reached</summary>{"".join(parts)}</details>'


# ======== Report-to-PIB + shareable verdict image: CSS and JS (package F) ========
CSS += """
details.report{margin-top:20px;border:2px solid var(--rule);border-radius:4px;background:var(--card);padding:0 14px}
details.report summary{display:block;min-height:44px;padding:12px 0;font-size:17px}
details.report .rpt-scope{display:block;font-weight:400;font-size:14px;color:var(--mute);margin-top:2px}
details.report .rpt-text{font-size:14px;line-height:1.45;min-height:230px;margin:6px 0 4px}
details.report .rpt-row .btn,#img-share,#dl{min-height:44px;display:inline-flex;align-items:center;justify-content:center;text-align:center}
#img-share[hidden]{display:none}.result>div{min-width:0}details.report p.note{margin:8px 0}details.report{padding-bottom:6px}
@media print{details.report{display:none}}
"""
# ======== SITE POLISH (phone layout): header rows, action grid, stacked tables, page-title h1. Later rules win over the ones above. ========
CSS += """
/* header: the brand and the theme toggle share row 1; the links are row 2 and scroll sideways on a phone (never a third row) */
.nav .wrap{align-items:center}.logo{order:1;line-height:1.2}.nav nav{order:2}#theme{order:3;flex:none}
h1.h2{font-size:clamp(28px,4vw,44px);line-height:1.55;letter-spacing:-.02em;margin:0 0 6px}
/* result actions: WhatsApp first and solid, the rest outlined; two equal columns on a phone */
.actions .btn{min-height:44px;display:inline-flex;align-items:center;justify-content:center;text-align:center;line-height:1.2}
.actions .listen-note:empty{display:none}
@media(max-width:560px){
.nav .wrap{gap:0 10px;padding-top:3px;padding-bottom:3px;min-height:0}.logo{flex:1 1 0;min-width:0;height:36px;display:flex;align-items:center;font-size:22px;line-height:1;white-space:nowrap;overflow:hidden}
#theme{order:2;width:36px;height:36px;margin-left:auto;display:inline-flex;align-items:center;justify-content:center;padding:0}
.nav nav{order:3;flex:0 0 100%;width:100%;margin:0;gap:2px;font-size:14px;flex-wrap:nowrap;white-space:nowrap;justify-content:flex-start;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.nav nav::-webkit-scrollbar{display:none}
.nav nav a{flex:none;display:inline-flex;align-items:center;min-height:32px;padding:0 9px 0 0;margin-right:5px;border-bottom:0}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.actions .btn{padding:8px 4px;font-size:14px;width:100%;letter-spacing:-.01em}.actions .listen-note{grid-column:1/-1;margin:0}
/* claims table: each row becomes a card (claim, then verdict, then sources); the real <table> stays for desktop and screen readers (roles are set in the markup) */
table.stack,table.stack tbody,table.stack tr,table.stack td{display:block;width:100%}
table.stack thead{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
table.stack tr{background:var(--card);border:1.5px solid var(--rule);border-radius:4px;padding:10px 12px;margin:0 0 10px}
table.stack td{border:0;padding:3px 0;font-size:15px}
table.stack td::before{content:attr(data-label);display:block;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin-bottom:1px}
table.stack td:first-child::before{display:none}table.stack td:first-child{font-size:16px;font-weight:500;padding-bottom:6px}
table.stack td[data-label=Verdict]{display:flex;align-items:center;gap:8px;padding:2px 0 6px}table.stack td[data-label=Verdict]::before{margin:0}
table.stack td.note{padding-top:0}
.result .bubble{max-width:none}
}
"""
JS += r"""
/* ---- Report to PIB: copy button (ids prefixed rpt-) ---- */
window.sachBindReport=function(){const b=document.querySelector('#rpt-copy'),t=document.querySelector('#rpt-text');if(!b||!t)return;
t.addEventListener('focus',()=>t.select());
b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(t.value);b.textContent='Copied ✓'}catch(e){t.focus();t.select();b.textContent='Selected — press Ctrl/Cmd+C'}})};window.sachBindReport();
/* ---- Shareable verdict image: 1080x1350 canvas, real verdict data from #sach-card-data ---- */
window.sachBindCard=function(){
const dl=document.querySelector('#dl'),de=document.querySelector('#sach-card-data'),sh=document.querySelector('#img-share');
if(!dl||!de)return;let D;try{D=JSON.parse(de.textContent)}catch(e){return}
const W=1080,H=1350,P=84,FB={FALSE:'#c2321f',TRUE:'#1f7a45',MISLEADING:'#c9780a',UNVERIFIED:'#6b6558'};
const SCR=['Noto Sans Devanagari','Noto Sans Telugu','Noto Sans Bengali','Noto Sans Gurmukhi','Noto Sans Gujarati','Noto Sans Oriya','Noto Sans Tamil','Noto Sans Kannada','Noto Sans Malayalam','Noto Sans Meetei Mayek','Noto Sans Arabic'],SCRQ=SCR.map(f=>"'"+f+"'").join(',');
const SANS="'Instrument Sans',"+SCRQ+",sans-serif",SERIF="'Fraunces',"+SCRQ+",Georgia,serif",MONO="'IBM Plex Mono',ui-monospace,monospace";
const isR=t=>/[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]/.test(t||'');
const cv=(n,f)=>{try{return getComputedStyle(document.documentElement).getPropertyValue(n).trim()||f}catch(e){return f}};
const gr=s=>window.Intl&&Intl.Segmenter?Array.from(new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(s),x=>x.segment):Array.from(s);
const clip=(t,n)=>{t=(t||'').replace(/\s+/g,' ').trim();if(t.length<=n)return t;const i=t.lastIndexOf(' ',n-1);return t.slice(0,i>n/2?i:n-1).trim()+'…'};
function wrap(x,t,w){const out=[];let ln='';for(const wd of (t||'').split(/\s+/).filter(Boolean)){const tr=ln?ln+' '+wd:wd;if(x.measureText(tr).width<=w){ln=tr;continue}
if(ln){out.push(ln);ln=''}if(x.measureText(wd).width<=w){ln=wd;continue}let pc='';for(const g of gr(wd)){if(pc&&x.measureText(pc+g).width>w){out.push(pc);pc=g}else pc+=g}ln=pc}
if(ln)out.push(ln);return out}
function fit(x,t,w,max){let L=wrap(x,t,w);if(L.length<=max)return L;L=L.slice(0,max);let l=L[max-1];
while(l&&x.measureText(l+'…').width>w){const i=l.lastIndexOf(' ');l=i>0?l.slice(0,i):gr(l).slice(0,-1).join('')}L[max-1]=(l||'')+'…';return L}
const fonts=async()=>{const all=D.word+D.why+D.claim+D.source;try{await Promise.race([Promise.all([document.fonts.load("900 100px Fraunces",D.word_en),document.fonts.load("400 40px 'Instrument Sans'",all),document.fonts.load("600 40px 'Instrument Sans'",all),
...SCR.map(f=>document.fonts.load("600 40px '"+f+"'",all)),document.fonts.load("500 30px 'IBM Plex Mono'",'Sach')]),new Promise(r=>setTimeout(r,2500))])}catch(e){}};
async function render(){await fonts();const c=document.createElement('canvas');c.width=W;c.height=H;const x=c.getContext('2d'),col=cv('--'+({MISLEADING:'mis',UNVERIFIED:'unv'}[D.verdict]||D.verdict.toLowerCase()),FB[D.verdict]||'#6b6558');
const paper=cv('--paper','#f2ebdb'),ink=cv('--ink','#17140f'),mute=cv('--mute','#5d564a'),card=cv('--card','#fffdf6'),MW=W-2*P;x.textBaseline='alphabetic';
x.fillStyle=paper;x.fillRect(0,0,W,H);x.fillStyle=col;x.fillRect(0,0,W,30);
x.fillStyle=ink;x.font='900 64px '+SERIF;x.fillText('Sach',P,142);x.font='500 26px '+MONO;x.fillStyle=mute;x.textAlign='right';x.fillText('VERDICT CARD',W-P,138);x.textAlign='left';
let size=170,L;const bw=MW-70;for(;size>=60;size-=6){x.font='900 '+size+'px '+SERIF;L=wrap(x,D.word,bw);if(L.length<=2&&D.word.split(/\s+/).every(w=>x.measureText(w).width<=bw))break}
const lh=size*1.12,bh=L.length*lh+56,by=230;x.save();x.translate(W/2,by+bh/2);x.rotate(-0.045);x.strokeStyle=col;x.lineWidth=12;x.beginPath();x.roundRect?x.roundRect(-MW/2+10,-bh/2,MW-20,bh,22):x.rect(-MW/2+10,-bh/2,MW-20,bh);x.stroke();
x.fillStyle=col;x.textAlign='center';x.font='900 '+size+'px '+SERIF;L.forEach((l,i)=>x.fillText(l,0,-bh/2+28+size*0.9+i*lh));x.restore();x.textAlign='left';
let y=by+bh+(L.length>1?66:86);if(D.lang!=='en'&&D.word_en){x.fillStyle=col;x.font='500 40px '+MONO;x.textAlign='center';x.fillText('In English: '+D.word_en,W/2,y);x.textAlign='left';y+=L.length>1?80:96}
const put=(t,x0,w,yy)=>{if(isR(t)){x.direction='rtl';x.textAlign='right';x.fillText(t,x0+w,yy);x.direction='ltr';x.textAlign='left'}else x.fillText(t,x0,yy)};
x.fillStyle=ink;x.font='600 46px '+SANS;fit(x,D.why,MW,L.length>1?2:3).forEach(l=>{put(l,P,MW,y);y+=64});y+=L.length>1?34:44;
x.fillStyle=card;x.font='400 38px '+SANS;const ml=Math.max(2,Math.min(6,Math.floor((H-190-y-(D.source?86:0)-92)/54))),cl=fit(x,'“'+clip(D.claim,240)+'”',MW-48,ml),ch=cl.length*54+92;x.fillRect(P,y,MW,ch);x.fillStyle=col;x.fillRect(P,y,10,ch);
x.fillStyle=mute;x.font='500 24px '+MONO;x.fillText('THE CLAIM',P+36,y+44);x.fillStyle=ink;x.font='400 38px '+SANS;cl.forEach((l,i)=>put(l,P+36,MW-72,y+98+i*54));y+=ch+(ml>2?46:40);
if(D.source){x.fillStyle=mute;x.font='400 32px '+SANS;fit(x,'Source: '+D.source+(D.date?' · '+D.date:''),MW,ml>2?2:1).forEach(l=>{x.fillText(l,P,y);y+=46})}
x.fillStyle=ink;x.fillRect(P,H-190,MW,3);x.font='700 46px '+SANS;x.fillText('Checked with Sach',P,H-120);x.fillStyle=mute;x.font='500 32px '+MONO;fit(x,location.origin,MW,1).forEach(l=>x.fillText(l,P,H-68));
return new Promise((ok,no)=>c.toBlob(b=>b?ok(b):no(new Error('blob')),'image/png'))}
let pre=null;const get=()=>pre||(pre=render().catch(e=>{pre=null;throw e}));const name='sach-'+D.verdict.toLowerCase()+'.png';
const save=b=>{const a=document.createElement('a'),u=URL.createObjectURL(b);a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),4000)};
dl.addEventListener('click',async()=>{try{save(await get())}catch(e){dl.textContent='Could not draw the image'}});
const th=document.querySelector('#theme');if(th)th.addEventListener('click',()=>{pre=null});
try{if(sh&&navigator.share&&navigator.canShare&&navigator.canShare({files:[new File([new Blob()],name,{type:'image/png'})]})){sh.hidden=false;get().catch(()=>{});
sh.addEventListener('click',async()=>{try{const b=await get();await navigator.share({files:[new File([b],name,{type:'image/png'})],title:'Sach verdict',text:'Checked with Sach '+location.origin})}catch(e){if(e&&e.name!=='AbortError')try{save(await get())}catch(_){}}})}}catch(e){}
};window.sachBindCard();
/* a swapped-in result (fetch-based check) needs its buttons bound again */
document.addEventListener('sach:result',()=>{window.sachBindReport();window.sachBindCard()});
"""


def card_attrs(code: str) -> str:
    """lang (and dir="rtl" for Urdu) for the verdict-card bubble. The lang is the language the card text is really written in: a Manipuri
    reply is the English card until a native speaker supplies Meitei wording (see i18n.ENGLISH_ONLY), so it is marked lang="en"."""
    real = text_lang(code)
    return f' lang="{html_lang(real)}"' + (' dir="rtl"' if real in RTL else "")


def result_block(res: dict, chosen: bool = False) -> str:
    v = res["verdict"]
    if res.get("no_claims"):
        return (f'<div class="result" id="result"><div><div class="stamp big UNVERIFIED">No claim</div></div>'
                f'<div><p class="kicker">Nothing to check</p><div class="bubble"{card_attrs(res.get("language", "en"))}><span id="cardtext">{esc(res["card"])}</span></div>'
                f'<p class="note" style="margin-top:14px">Greetings, links, emoji and bare numbers are not factual claims. Paste the sentence that makes the claim.</p>'
                f'{signs_html(res.get("warning_signs"), res.get("language", "en"))}</div></div>')
    rows = ""
    for c in res["claims"]:
        fmt = lambda x: (f'<div class="cite"><a href="{esc(x["url"])}" rel="noopener">{esc(x["source"])}</a> '
                         f'<span>· {esc(x["tier"].replace("_"," "))} · accessed {esc(x["date_accessed"])}</span></div>')
        cs = c["citations"]
        cites = "".join(fmt(x) for x in cs[:3]) or '<span class="note">No source found</span>'
        if len(cs) > 3:
            cites += f'<details><summary class="note">+{len(cs) - 3} more sources</summary>{"".join(fmt(x) for x in cs[3:])}</details>'
        rows += (f'<tr role="row"><td role="cell" data-label="Claim">{esc(c["claim"]["text"])}<br><span class="note">{esc(c["claim"]["domain"])} · {esc(c["reason_code"].replace("_"," "))}</span></td>'
                 f'<td role="cell" data-label="Verdict"><span class="tag {c["verdict"]}">{c["verdict"]}</span></td><td role="cell" data-label="Citations">{cites}</td></tr>')
    card = esc(res["card"])
    softtip = ""
    if tip_config() and v in TIP_QUIPS:
        softtip = f'<p class="softtip note">{esc(TIP_QUIPS[v])} <a href="/#tip">Chip in for the corrections desk ☕</a> (optional; never affects a verdict).</p>'
    notice = ""
    if res.get("degraded"):
        notice = ('<div class="honest" style="margin-top:18px" role="status"><b>Limited mode.</b> Our AI checker is unavailable or at capacity right now, '
                  'so Sach only reports a verdict when a PIB debunk clearly matches. Most results will say “unverified”; try again later for a fuller check.</div>')
    if res.get("search_status") in ("down", "partial"):
        notice += ('<div class="honest" style="margin-top:18px" role="status"><b>Web search was unavailable.</b> Live web search was unavailable for this check, '
                   'so Sach could only use its built-in list of PIB debunks. An UNVERIFIED result may change later.</div>')
    english = ""
    if res.get("card_en"):
        said = "".join(f'<li><span class="note">{esc(c["claim"]["text"])}</span><br><b>{esc(c["english"])}</b></li>' for c in res["claims"] if c.get("english"))
        english = (f'<div class="honest" style="margin-top:22px;border-left-color:var(--true)" id="english"><b>What this means in English</b>'
                   f'<div class="bubble" style="margin:10px 0;background:var(--paper)"><span id="cardtext_en">{esc(res["card_en"])}</span></div>'
                   + (f'<p class="note" style="margin:8px 0 4px">We understood the forward as:</p><ul style="padding-left:18px;margin:0">{said}</ul>' if said else
                      ('<p class="note" style="margin:8px 0 0">English rendering of the claim itself was not available for this check.</p>' if res.get('input_language', 'en') != 'en' else ''))
                   + '<div class="row"><button class="btn ghost" id="copy2" type="button">Copy both languages</button></div></div>')
    cachednote = ""
    if res.get("cached"):
        first = str(res.get("first_checked_at") or res.get("checked_at") or "")[:10]
        cachednote = f'<p class="note" role="status" style="margin:0 0 10px">First checked on {esc(first)}. This is a stored result for a repeated message.</p>'
    tr = trace_block(res)
    wa = "https://wa.me/?text=" + quote(res["card"])
    issue = (f"{REPO}/issues/new?title=" + quote(f"Wrong verdict? {v}") + "&body=" +
             quote("Claim(s):\n" + "\n".join("- " + c["claim"]["text"] for c in res["claims"]) + f"\n\nSach said: {v}\nWhat is wrong:\n"))
    return f"""<div class="result" id="result"><div><div class="stamp big {v}">{LABEL['en'][v]}</div></div>
<div><p class="kicker">Forward this card back to the group · reply language: {esc(LANG_NAME.get(res['language'], res['language'].upper()))}{' (your choice)' if chosen else ' (matched to the forward)'}</p>
{cachednote}<div class="bubble"{card_attrs(res.get('language', 'en'))}><span id="cardtext">{card}</span><small dir="ltr">Sach ✓✓</small></div>
<div class="row actions" role="group" aria-label="Share this verdict"><a class="btn wa" href="{esc(wa)}" rel="noopener">Share on WhatsApp</a><button class="btn ghost" id="copy" type="button">Copy card</button>
<button class="btn ghost" id="dl" type="button">Download image</button><button class="btn ghost" id="img-share" type="button" hidden>Share image</button>{listen_buttons(res.get('language', 'en'), bool(res.get('card_en')))}</div>
{signs_html(res.get("warning_signs"), res.get("language", "en"))}{report_html(res)}{card_data_script(res)}{notice}{english}{softtip}<h3 style="font-family:var(--serif);margin:26px 0 6px">Claims checked</h3>
<div style="overflow-x:auto"><table class="stack" role="table"><thead role="rowgroup"><tr role="row"><th role="columnheader">Claim</th><th role="columnheader">Verdict</th><th role="columnheader">Citations</th></tr></thead><tbody role="rowgroup">{rows}</tbody></table></div>
{tr}<p class="note" style="margin-top:14px">Checked {esc(res['checked_at'][:16].replace('T',' '))} UTC. <a href="{esc(issue)}" rel="noopener">Report a wrong verdict</a></p></div></div>"""


def lang_options(reply: str = "auto") -> str:
    """The "Reply in" <select> options: Auto and English first, then the Indian languages by number of speakers (each as "native name · English
    name"), then Tinglish. Every code in REPLY_LANGS appears exactly once."""
    def opt(v, label):
        return f'<option value="{v}"{" selected" if v == reply else ""}>{esc(label)}</option>'
    def group(title, codes):
        return f'<optgroup label="{esc(title)}">' + "".join(opt(c, f"{NATIVE[c]} · {NAMES[c]}") for c in codes) + "</optgroup>"
    return (opt("auto", "Auto (match the forward)") + opt("en", "English") + group("Indian languages", INDIAN_LANGS)
            + f'<optgroup label="Written in English letters">{opt("tl", "Tinglish · Telugu in English letters")}</optgroup>')


def home(result: str = "", prefill: str = "", error: str = "", reply: str = "auto", noindex: bool = False) -> bytes:
    chips = "".join(f'<button type="button" class="chip" data-text="{esc(e["text"])}"><b class="{e["verdict"]}">{e["verdict"]}</b>{esc(e["title"])} · {e["lang"]}</button>' for e in EXAMPLES)
    opts = lang_options(reply)
    ev = eval_display()                      # None = "Evaluation pending" (old format, degraded or missing file)
    stats = eval_stats_html(ev)
    cfg = tip_config()
    faq_items = list(FAQ) + ([("Do tips change what Sach says?", "Never. Verdicts come only from PIB and official sources and the rules above. Tips are optional, go straight from your UPI app to the person who runs Sach, and Sach never sees who paid or how much. Your UPI app will show you who you are paying before you confirm, as it does for every UPI payment.")] if cfg else [])
    faq = "".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in faq_items)
    tip_section = ""
    if cfg:
        cards = "".join(f'<div class="tipcard" data-amt="{amt}" role="button" tabindex="0"><div class="amt">₹{amt}</div><b>{esc(t)}</b><span class="d">{esc(d)}</span></div>'
                        for amt, t, d in TIP_TIERS)
        altnote = ('<p class="note" style="margin:8px 0"><b class="qrlabel">Code A</b> &middot; <button type="button" class="altswap linklike">Code not working? Try code B</button>'
                   ' <span>(same bank account, a different UPI address)</span></p>') if cfg.get("alt_vpa") else ""
        if cfg.get("merchant"):
            appnote = '<p class="note" style="margin:8px 0 0">Prefer a button? <a href="/?view=pay" rel="nofollow">Open my UPI app</a> with the amount filled in.</p>'
            dlgnote = (f'<p style="margin:12px 0 0"><a class="btn ghost" id="dlgapps" href="/?view=pay&amp;amt={3 * PER_FORWARD}" rel="nofollow" '
                       f'style="text-decoration:none">Open my UPI app</a></p>')
        else:
            appnote = ('<p class="note" style="margin:8px 0 0">Why no “open my app” button? UPI rules (NPCI) don\'t let a payment app start a payment '
                       'to a personal UPI ID from a website link, so scanning the code is the way to pay.</p>')
            dlgnote = ('<p class="note" style="margin:12px 0 0"><b>Easiest:</b> show this code on another screen (a laptop, or a friend\'s phone) '
                       'and scan it with your UPI app\'s scanner.</p>')
        from .razorpay_pay import public_key_id
        gw = public_key_id() is not None
        gwbtn = ('<div id="rzpbox" style="margin:0 0 12px"><button class="btn" type="button" id="rzpgo">Pay <span id="rzpamt">₹30</span> by UPI or card</button>'
                 '<p id="rzpmsg" class="note" role="status" style="margin:6px 0 0"></p>'
                 '<p class="note" style="margin:4px 0 0">Secure checkout by Razorpay, which can see who paid (<a href="/?view=privacy" rel="nofollow">privacy</a> · <a href="/?view=refund" rel="nofollow">refunds</a>). Prefer to stay anonymous? Scan the code below.</p></div>') if gw else ""
        opts_fw = "".join(f'<option value="{n}"{" selected" if n == 3 else ""}>{n}</option>' for n in (1, 3, 5, 10, 20))
        tip_section = f'''<section id="tip"><div class="wrap"><p class="kicker">Nobody asked, but…</p><h2>{esc(tip_headline())} ☕</h2>
<p class="sub">Sach has no ads, no paywall and no “forward this to 10 groups or bad luck”. If a verdict saved you an awkward family-group moment, a small tip keeps the corrections coming. <b>Tips never change a verdict.</b></p>
<div class="tipmeter card"><label for="fw">You were about to forward</label><select id="fw" aria-label="Forwards we stopped">{opts_fw}</select><span>messages. At ₹{PER_FORWARD} a forward that's <b id="fwamt">₹{3 * PER_FORWARD}</b></span><button class="btn" type="button" id="fwgo">Chip in ₹{3 * PER_FORWARD}</button></div>
<p class="note" style="margin:0 0 8px">Pick a suggestion (or type your own), then scan the code below and enter that amount in your UPI app.</p>
<div class="tipgrid">{cards}<div class="tipcard other"><div class="amt" style="font-size:24px">Other amount</div><span class="d">Any amount from ₹1 to ₹10,000</span>
<div class="otheramt"><label for="oa"><b>Amount</b> (₹)</label><input id="oa" type="number" inputmode="numeric" min="1" max="10000" step="1" placeholder="e.g. 75"><button class="btn" type="button" id="oago">Continue</button></div><div id="oaerr" class="note" role="alert" style="color:var(--false);min-height:1.3em"></div></div></div>
<div class="tipbox"><img id="upiqr" class="qrimg" src="/?view=tipqr&amp;fmt=png" width="190" height="190" alt="UPI QR code for tips">
<div><p style="margin:0 0 8px"><b>Scan this code</b> with Google Pay, PhonePe, Paytm or BHIM and enter <b id="want">₹{3 * PER_FORWARD}</b> when asked.</p>
<p style="margin:0 0 8px"><b>On a computer:</b> scan it with the UPI app on your phone.<br><b>On a phone:</b> save the image (tap Download, or press and hold it), then open your UPI app, choose <i>Scan QR</i> and pick the image from your gallery.</p>
<div class="row"><a class="btn dlpng" href="/?view=tipqr&amp;fmt=png" download="sach-tip-qr.png" style="text-decoration:none">Download QR image</a></div>{altnote}
<p class="note" style="margin:10px 0 0">Your UPI app shows who you're paying before you confirm; that's UPI's own safety check. Tips are optional and go straight from your app to the person who runs Sach. Sach never sees who paid or how much.</p>
{appnote}</div></div>
<dialog id="paydlg" aria-labelledby="paytitle"><form method="dialog" class="x"><button aria-label="Close">✕</button></form>
<p class="kicker">Chip in for the corrections desk ☕</p>
<h3 id="paytitle" style="font-family:var(--serif);font-size:36px;margin:4px 0 6px">Pay <span id="dlgamt">₹{3 * PER_FORWARD}</span></h3>
{gwbtn}
<img class="qrimg" src="/?view=tipqr&amp;fmt=png" width="190" height="190" alt="UPI QR code for tips">{altnote}
<p style="margin:0 0 8px"><b>Scan this code</b> with Google Pay, PhonePe, Paytm or BHIM and enter <b id="dlgamt2">₹{3 * PER_FORWARD}</b> when asked.</p>
<p class="note" style="margin:0 0 10px"><b>On a phone:</b> tap Download, then in your UPI app choose <i>Scan QR</i> and pick the image from your gallery.</p>
<div class="row"><a class="btn dlpng" href="/?view=tipqr&amp;fmt=png" download="sach-tip-qr.png" style="text-decoration:none">Download QR image</a>
</div>
{dlgnote}</dialog>
</div></section>'''
    body = f"""<div class="wrap"><div class="hero"><div>
<p class="kicker">A corrections desk for your family group</p>
<h1>Got a forward? Get the <em>receipts.</em></h1>
<p class="lede">Paste a WhatsApp message. Sach splits it into claims, checks each against PIB and official sources, and hands back a verdict card you can forward straight into the group, with the link.</p>
<p class="scripts">English and {N_INDIAN} Indian languages · हिन्दी · বাংলা · తెలుగు · தமிழ் · मराठी · <a href="#languages">see all</a></p>
<p class="note" style="margin-top:6px"><b>Sach</b> (सच, Hindi) and <b>nijam</b> (నిజం, Telugu) both mean <b>“truth”</b>.</p>
<div class="row"><a class="btn" href="#check">Check a forward</a><a class="btn ghost" href="#how">How it works</a></div></div>
<div class="stampbox" aria-hidden="true">{stamp('FALSE')}{stamp('TRUE')}{stamp('MISLEADING')}{stamp('UNVERIFIED')}</div></div></div>

<section id="check"><div class="wrap"><h2>Check a forward</h2><p class="sub">Paste the whole message or a single claim. We reply in the language it was written in, or in any language you choose below. Checks usually take 10 to 30 seconds because we read the sources live.</p>
<div class="checker" id="checker"><form id="form" method="post" action="/#result"><label for="text" class="kicker">The forward</label>
<textarea id="text" name="text" placeholder="Paste the message here…" required maxlength="{MAX_CHARS}">{esc(prefill)}</textarea>{voice_controls()}
{OCR_BLOCK}
<div class="chips" role="group" aria-label="Try an example"><span class="note" style="align-self:center">Try:</span>{chips}</div>
<div class="row"><label for="lang" class="note" style="margin-right:-4px">Reply in</label><select id="lang" name="lang">{opts}</select>
<button class="btn" id="go" type="submit">Check it</button><button class="btn ghost" id="paste" type="button">Paste</button><button class="btn ghost" id="clear" type="button">Clear</button>
<span id="count" aria-live="off"></span></div>
<p class="note" style="margin:10px 0 0">Tip: press Ctrl/Cmd + Enter to check. Only the individual claims (never your name) go to the public ledger.</p>
<div id="busy" role="status"><i></i>Reading PIB and official pages… this usually takes 10 to 30 seconds.</div>{progress_panel()}</form>
<div id="results">{f'<p role="alert" style="color:var(--false);font-weight:600;margin-top:14px">{esc(error)}</p>' if error else ''}{result}</div></div></div></section>
{pwa.HOME_HTML}

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
<div class="tier"><span class="t">3 · SECONDARY</span><div><b>BOOM, Vishvas News, Newschecker, Factly and other IFCN-verified fact-checkers.</b> Shown as “fact-checker (not official)”. They can support a note, never a verdict.</div></div></div></section>

<section id="evidence"><div class="wrap"><h2>Does it actually work?</h2><p class="sub">We tested it on real PIB debunks, real government announcements, and invented claims that should be left unverified. The misses are published too.</p>
{stats}<div class="honest"><b>Read this before trusting the numbers</b><ul>
<li>It is a small set{f" ({ev['n']} claims)" if ev else ""}. Treat any number as indicative, not as a guarantee.</li>
<li>When the AI checker is unavailable the site says so (“Limited mode”) and reports only clear PIB debunks.</li>
<li>Many FALSE items are paraphrases of PIB debunk titles, so recall there is optimistic.</li>
<li>Results move by a claim or two between runs, because live search returns different pages.</li>
<li>Hindi and Telugu verdict wording is human-written but still awaiting native-speaker review.</li></ul>
<p class="note" style="margin:10px 0 0"><a href="{EVAL_DOC}" rel="noopener">Full table with every claim and failure →</a></p></div></div></section>

{tip_section}<section id="languages"><div class="wrap"><h2>Languages</h2><p class="sub">English and {N_INDIAN} Indian languages, plus Tinglish. Paste a forward in any of them; pick “Reply in” to get the card in another. The wording is AI-written and awaiting native-speaker review.</p>
<ul class="langlist">{"".join(f'<li lang="{html_lang(c)}"><b>{esc(NATIVE[c])}</b> <span>{esc(NAMES[c])}</span></li>' for c in SUPPORTED if c != "en")}</ul></div></section>
<section id="faq"><div class="wrap"><h2>Questions</h2><p class="sub">Short, honest answers.</p>{faq}</div></section>

<section id="api"><div class="wrap"><h2>Use it from code</h2><p class="sub">The same checker is available as JSON. Be kind: each call reads live sources and usually takes 10 to 30 seconds.</p>
<pre class="code">curl -s -X POST "{esc(site_url())}/?format=json" \\
  --data-urlencode "text=Government is giving Rs 1000 under Corona Sahayata Yojana" \\
  --data-urlencode "lang=te"      # optional reply language: auto (default) or one of {", ".join(SUPPORTED)}

→ {{"verdict":"FALSE","language":"en","card":"…","claims":[{{"verdict":"FALSE","citations":[{{"url":"https://pib.gov.in/…"}}]}}]}}</pre>
<div class="row"><a class="btn ghost" href="/?view=ledger">Open the public ledger →</a><a class="btn ghost" href="{REPO}" rel="noopener">Source on GitHub →</a></div></div></section>"""
    return layout(body, path="/", noindex=bool(result or prefill or error or noindex))


def pay_page(amount: int | None = None, bad_amount: bool = False, alt: bool = False) -> bytes:
    """Pick-your-UPI-app page. Every button is a server redirect, so the UPI address is not in this page's HTML."""
    cfg_ = tip_config() or {}
    alt = bool(alt and cfg_.get("alt_vpa"))                           # ignored unless a second address is configured
    amt_q = f"&amp;amt={amount}" if amount else ""
    alt_q = "&amp;alt=1" if alt else ""
    switch = ""
    if cfg_.get("alt_vpa"):
        other = f'/?view=pay{amt_q}{"" if alt else "&amp;alt=1"}'
        switch = (f'<p class="note">Paying the {"second" if alt else "first"} address. Link not working? <a href="{other}" rel="nofollow">'
                  f'Try the {"first" if alt else "other"} address</a> (same bank account).</p>')
    shown = f"₹{amount}" if amount else "any amount"
    buttons = "".join(f'<a class="appbtn" href="/?go=tip{amt_q}&amp;app={k}{alt_q}" rel="nofollow"><span class="ico">{app_icon(k)}</span>'
                      f'<span class="txt"><b>{esc(name)}</b><span>{esc(hint)}</span></span></a>' for k, (name, _scheme, hint) in UPI_APPS.items())
    err = ('<p role="alert" style="color:var(--false);font-weight:600;margin:0 0 10px">Please enter a whole number of rupees from 1 to 10,000. '
           'You can also pick an app now and type the amount there.</p>') if bad_amount else ""
    body = f"""<div class="wrap"><div class="paywrap"><p class="kicker">Chip in for the corrections desk ☕</p>
<h1 style="font-size:clamp(34px,8vw,54px);margin:6px 0 10px">Pay {esc(shown)}</h1>
{err}<p role="note" style="background:var(--paper2);border-left:6px solid var(--mis);padding:12px 16px;margin:0 0 16px">If your app shows an error, go back and <b>scan the QR code</b> instead.</p>
<p class="sub" style="margin-bottom:14px">Pick the app you use. Your phone may ask “open another application?”; say yes. The amount is filled in and <b>you confirm the payment inside that app</b>.</p>
{buttons}
{switch}{amount_form(amount, compact=True)}
<p class="note">iPhone tip: if you choose “Any other UPI app”, iOS decides which app opens and it may not be the one you wanted (for example WhatsApp). Choosing your app above avoids that. App not installed? Use the QR below or go back.</p>
<h2 style="font-size:24px;margin:26px 0 8px">On a computer?</h2>
<div class="tipbox"><img id="upiqr" src="/?view=tipqr{amt_q}{alt_q}" width="170" height="170" alt="UPI QR code for tips">
<p class="note" style="margin:0;max-width:22em">Scan this with any UPI app{f" (it already has {esc(shown)} filled in)" if amount else " and enter any amount"}. Tips are optional and never change a verdict.</p></div>
<p style="margin-top:24px"><a class="btn ghost" href="/#tip" style="text-decoration:none">← Back to the tip jar</a></p>
<p class="logonote">App names and logos belong to their owners (Google LLC, PayTM Mobile Solutions, NPCI, PhonePe) and are shown only to help you recognise the app. Sach is not affiliated with them. The icons are the apps own App Store icons; the "other app" icon is a generic glyph.</p></div></div>"""
    return layout(body, "Chip in — Sach", path="/?view=pay", noindex=True)


def ledger_page() -> bytes:
    rows = ""
    data = list(reversed(ledger.load()))
    for r in data:
        cites = "".join(f'<div class="cite"><a href="{esc(c["url"])}" rel="noopener">{esc(c["source"])}</a> <span>· {esc(c["tier"].replace("_"," "))} · {esc(c["date_accessed"])}</span></div>'
                        for c in r["citations"]) or '<span class="note">none found</span>'
        rows += (f'<tr role="row" data-v="{esc(r["verdict"])}"><td role="cell" data-label="Claim">{esc(r["claim"])}</td><td role="cell" data-label="Verdict"><span class="tag {esc(r["verdict"])}">{esc(r["verdict"])}</span></td>'
                 f'<td role="cell" data-label="Citations">{cites}</td><td role="cell" data-label="Checked" class="note">{esc(r["checked_at"][:10])}</td></tr>')
    if not rows:
        rows = '<tr data-v="NONE"><td colspan="4" class="note">No claims checked yet.</td></tr>'
    btns = "".join(f'<button type="button" data-v="{v}" aria-pressed="{"true" if v=="ALL" else "false"}">{v.title() if v!="ALL" else "All"}</button>'
                   for v in ("ALL", "FALSE", "TRUE", "MISLEADING", "UNVERIFIED"))
    body = f"""<div class="wrap"><section style="border:0"><p class="kicker">Public record</p><h1 class="h2">Evidence ledger</h1>
<p class="sub">{len(data)} checked claims. Each row lists the sources we actually fetched, with the date we accessed them. On this free deployment the live part of the ledger resets when the server restarts; the repository holds the permanent record.</p>
<div class="filters" role="group" aria-label="Filter by verdict">{btns}<input id="q" type="search" placeholder="Search claims or sources…" aria-label="Search the ledger"><span class="note" id="shown"></span></div>
<div style="overflow-x:auto"><table class="stack" role="table"><thead role="rowgroup"><tr role="row"><th role="columnheader">Claim</th><th role="columnheader">Verdict</th><th role="columnheader">Citations</th><th role="columnheader">Checked</th></tr></thead><tbody role="rowgroup">{rows}<tr id="empty" style="display:none"><td colspan="4" class="note">No claims match your filter.</td></tr></tbody></table></div></section></div>"""
    return layout(body, "Evidence ledger — Sach", path="/?view=ledger")
