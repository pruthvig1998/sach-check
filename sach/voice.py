"""Voice input, read-aloud and the smoother (fetch-based) check flow for the Sach website.

Everything here is progressive enhancement: the server renders hidden controls, the browser script reveals only the ones the device
can really use, and without JavaScript the page is the plain form POST it always was. Nothing here talks to the server in a new way:
the fetch flow sends the same urlencoded POST the form would send and swaps the results area out of the returned page.
Plain client-side JS only: no external scripts, fonts or services.
"""
import html
import json

from .i18n import text_lang
from .lang import BCP47, NAMES, NATIVE

esc = html.escape

# Short UI strings in English, Hindi and Telugu. The server renders the English text; the script swaps in hi/te from the reply-language choice.
# NOT NATIVE-REVIEWED (every hi and te string below is awaiting a native-speaker pass, like the verdict-card wording)
STRINGS = {
    "en": {
        "speak": "Speak", "stop": "Stop", "vlang_label": "Speak in",
        "privacy": "On many phones and browsers, speech recognition sends your voice to the browser maker's speech service. Sach never records or stores audio. Nothing is checked until you press Check it.",
        "listening": "Listening… tap Stop when you are done.",
        "stopped": "Stopped. Read the text, fix anything, then press Check it.",
        "err_not_allowed": "The microphone is blocked. Allow it in the browser settings, or type instead.",
        "err_no_speech": "No speech heard. Tap Speak and try again.",
        "err_network": "Could not reach the speech service. Check your internet, or type instead.",
        "err_audio": "No microphone found. Check it, or type instead.",
        "err_lang": "This language is not supported for speaking on this phone. Pick another, or type instead.",
        "err_generic": "Speaking did not work this time. You can type the message instead.",
        "listen": "Listen", "listen_stop": "Stop reading", "listen_en": "Listen in English",
        "voice_hi": "This phone has no Hindi voice installed", "voice_te": "This phone has no Telugu voice installed",
        "voice_missing": "This phone has no {lang} voice installed. Use “Listen in English” instead.",
        "voice_try": "No {lang} voice was found on this phone. Sach will still try; if you hear nothing, use “Listen in English”.",
        "src_word": "Sources",
        "progress_title": "Checking your forward", "elapsed": "{n} seconds", "step_of": "Step {n} of 4",
        "stage1": "Splitting your message into claims", "stage2": "Searching PIB and official sources",
        "stage3": "Reading what each source actually says", "stage4": "Applying the verdict rules",
        "general": "These are the steps Sach goes through. This page cannot see which one is running right now.",
        "typical": "Most checks take 10 to 30 seconds. A repeat of a message Sach has seen is instant.",
        "still": "Still working. Sach stops at about 50 seconds and says UNVERIFIED rather than guessing.",
        "cancel": "Cancel", "cancelled": "Check cancelled. Your text is still there.",
        "checking": "Checking…", "result_ready": "Result ready",
    },
    "hi": {
        "speak": "बोलकर लिखें", "stop": "रोकें", "vlang_label": "बोलने की भाषा",
        "privacy": "कई फ़ोन और ब्राउज़र में आपकी आवाज़ ब्राउज़र बनाने वाली कंपनी की सेवा को भेजी जाती है। Sach आवाज़ रिकॉर्ड या सेव नहीं करता। Check it दबाने तक कुछ नहीं जाँचा जाता।",
        "listening": "सुन रहे हैं… पूरा होने पर रोकें दबाएँ।",
        "stopped": "रुक गया। लिखा हुआ पढ़ लें, ठीक कर लें, फिर Check it दबाएँ।",
        "err_not_allowed": "माइक्रोफ़ोन बंद है। ब्राउज़र की सेटिंग में अनुमति दें, या टाइप करें।",
        "err_no_speech": "कोई आवाज़ नहीं सुनाई दी। फिर से कोशिश करें।",
        "err_network": "आवाज़ पहचानने की सेवा से जुड़ नहीं सके। इंटरनेट देखें, या टाइप करें।",
        "err_audio": "माइक्रोफ़ोन नहीं मिला। उसे जाँचें, या टाइप करें।",
        "err_lang": "इस फ़ोन पर यह भाषा नहीं चलती। दूसरी भाषा चुनें, या टाइप करें।",
        "err_generic": "इस बार बोलकर लिखना नहीं चला। आप संदेश टाइप कर सकते हैं।",
        "listen": "सुनें", "listen_stop": "पढ़ना रोकें", "listen_en": "अंग्रेज़ी में सुनें",
        "voice_hi": "इस फ़ोन में हिन्दी आवाज़ नहीं है", "voice_te": "इस फ़ोन में तेलुगु आवाज़ नहीं है",
        "voice_missing": "इस फ़ोन में {lang} आवाज़ नहीं है। इसकी जगह “अंग्रेज़ी में सुनें” दबाएँ।",
        "voice_try": "इस फ़ोन में {lang} आवाज़ नहीं मिली। Sach फिर भी कोशिश करेगा; कुछ न सुनाई दे तो “अंग्रेज़ी में सुनें” दबाएँ।",
        "src_word": "स्रोत",
        "progress_title": "आपका फ़ॉरवर्ड जाँच रहे हैं", "elapsed": "{n} सेकंड", "step_of": "चरण {n} / 4",
        "stage1": "संदेश को अलग-अलग दावों में बाँटना", "stage2": "PIB और सरकारी स्रोतों में खोजना",
        "stage3": "हर स्रोत में असल में क्या लिखा है, यह पढ़ना", "stage4": "फ़ैसले के नियम लगाना",
        "general": "Sach ये चरण पूरे करता है। इस पेज को अभी यह नहीं दिखता कि कौन-सा चल रहा है।",
        "typical": "ज़्यादातर जाँच में 10 से 30 सेकंड लगते हैं। पहले देखा हुआ संदेश तुरंत हो जाता है।",
        "still": "अभी काम चल रहा है। Sach करीब 50 सेकंड में रुक जाता है और अंदाज़ा लगाने की जगह UNVERIFIED कहता है।",
        "cancel": "रद्द करें", "cancelled": "जाँच रद्द की। आपका लिखा हुआ वैसा ही है।",
        "checking": "जाँच रहे हैं…", "result_ready": "नतीजा तैयार है",
    },
    "te": {
        "speak": "మాట్లాడి రాయండి", "stop": "ఆపండి", "vlang_label": "మాట్లాడే భాష",
        "privacy": "చాలా ఫోన్లు, బ్రౌజర్లలో మీ గొంతు బ్రౌజర్ తయారీదారు స్పీచ్ సేవకు వెళ్తుంది. Sach ఆడియోను రికార్డ్ చేయదు, దాచదు. Check it నొక్కే వరకు ఏదీ తనిఖీ కాదు.",
        "listening": "వింటున్నాం… అయిపోయాక ఆపండి నొక్కండి.",
        "stopped": "ఆగింది. రాసినది చదివి, సరిచేసి, Check it నొక్కండి.",
        "err_not_allowed": "మైక్రోఫోన్ అనుమతి లేదు. బ్రౌజర్ సెట్టింగ్స్‌లో అనుమతించండి, లేదా టైప్ చేయండి.",
        "err_no_speech": "మాట వినిపించలేదు. మళ్ళీ ప్రయత్నించండి.",
        "err_network": "స్పీచ్ సేవకు కనెక్ట్ కాలేదు. ఇంటర్నెట్ చూడండి, లేదా టైప్ చేయండి.",
        "err_audio": "మైక్రోఫోన్ కనిపించలేదు. దాన్ని చూడండి, లేదా టైప్ చేయండి.",
        "err_lang": "ఈ ఫోన్‌లో ఈ భాష పనిచేయదు. వేరే భాష ఎంచుకోండి, లేదా టైప్ చేయండి.",
        "err_generic": "ఈసారి మాట్లాడి రాయడం పని చేయలేదు. మీరు సందేశాన్ని టైప్ చేయవచ్చు.",
        "listen": "వినండి", "listen_stop": "చదవడం ఆపండి", "listen_en": "ఇంగ్లీష్‌లో వినండి",
        "voice_hi": "ఈ ఫోన్‌లో హిందీ వాయిస్ లేదు", "voice_te": "ఈ ఫోన్‌లో తెలుగు వాయిస్ లేదు",
        "voice_missing": "ఈ ఫోన్‌లో {lang} వాయిస్ లేదు. బదులుగా “ఇంగ్లీష్‌లో వినండి” నొక్కండి.",
        "voice_try": "ఈ ఫోన్‌లో {lang} వాయిస్ కనిపించలేదు. Sach అయినా ప్రయత్నిస్తుంది; ఏమీ వినిపించకపోతే “ఇంగ్లీష్‌లో వినండి” నొక్కండి.",
        "src_word": "ఆధారాలు",
        "progress_title": "మీ ఫార్వర్డ్‌ను తనిఖీ చేస్తున్నాం", "elapsed": "{n} సెకన్లు", "step_of": "దశ {n} / 4",
        "stage1": "సందేశాన్ని వేర్వేరు వాదనలుగా విడగొట్టడం", "stage2": "PIB, అధికారిక వనరులలో వెతకడం",
        "stage3": "ప్రతి వనరు నిజంగా ఏం చెబుతోందో చదవడం", "stage4": "తీర్పు నియమాలను వర్తింపజేయడం",
        "general": "Sach ఈ దశల గుండా వెళ్తుంది. ఇప్పుడు ఏ దశ నడుస్తోందో ఈ పేజీకి తెలియదు.",
        "typical": "చాలా తనిఖీలకు 10 నుండి 30 సెకన్లు పడుతుంది. ఇంతకు ముందు చూసిన సందేశం వెంటనే వస్తుంది.",
        "still": "ఇంకా పని జరుగుతోంది. Sach సుమారు 50 సెకన్లకు ఆగి, ఊహించకుండా UNVERIFIED అని చెబుతుంది.",
        "cancel": "రద్దు చేయండి", "cancelled": "తనిఖీ రద్దు అయింది. మీ టెక్స్ట్ అలాగే ఉంది.",
        "checking": "తనిఖీ చేస్తున్నాం…", "result_ready": "ఫలితం సిద్ధంగా ఉంది",
    },
}

# Speak-in picker: the languages browsers' speech recognition commonly supports (Chrome/Android). Odia (or-IN) and Assamese (as-IN) are left
# out because support could not be confirmed here; Konkani, Nepali and Manipuri have no common recognition support either. NOT verified on a device.
SPEAK_CODES = ("en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "ml", "pa")
SPEAK_LANGS = tuple((BCP47[c], NATIVE[c]) for c in SPEAK_CODES)
# Read-aloud tag per card language: every language is attempted. Tinglish is Latin letters, so the English voice reads it, not te-IN.
CARD_BCP47 = dict(BCP47, tl="en-IN")
# Languages for which a missing voice does not disable the Listen button (the phone may still do something with the tag).
TRY_LISTEN = ("or", "as", "kok", "ne", "mni")
# reply language -> the speak-in tag to preselect (Tinglish speakers dictate Telugu)
REC_DEFAULT = {c: BCP47[c] for c in (*SPEAK_CODES, "tl")}


def _t(k: str) -> str:
    return esc(STRINGS["en"][k])


def voice_controls() -> str:
    """Speak button, language picker, privacy note and live status. Hidden until the script finds speech recognition."""
    opts = "".join(f'<option value="{v}">{esc(n)}</option>' for v, n in SPEAK_LANGS)
    return (f'<div id="voicebox" class="voicebox" hidden><div class="row" style="margin-top:12px">'
            f'<button type="button" class="btn ghost" id="speak" aria-pressed="false"><span aria-hidden="true">🎤</span> <span id="speaklabel">{_t("speak")}</span></button>'
            f'<label for="vlang" class="note" data-vk="vlang_label">{_t("vlang_label")}</label><select id="vlang">{opts}</select></div>'
            f'<p class="note" id="vprivacy" data-vk="privacy" style="margin:8px 0 0">{_t("privacy")}</p>'
            f'<p class="note vstatus" id="vstatus" role="status" aria-live="polite"></p></div>'
            f'<p id="flowstatus" class="sr" role="status" aria-live="polite"></p>')


def progress_panel() -> str:
    """The honest progress panel shown by the fetch flow: elapsed seconds, general stage text, Cancel. Hidden by default."""
    return (f'<div id="sprog" class="sprog" hidden><p class="pg-head"><i aria-hidden="true"></i><b data-vk="progress_title">{_t("progress_title")}</b> '
            f'<span id="pg-elapsed" class="note"></span></p>'
            f'<p id="pg-stage" class="pg-stage" role="status" aria-live="polite"></p>'
            f'<p class="note" data-vk="general">{_t("general")}</p><p class="note" data-vk="typical">{_t("typical")}</p>'
            f'<p class="note pg-still" id="pg-still" role="status" hidden data-vk="still">{_t("still")}</p>'
            f'<button type="button" class="btn ghost" id="pg-cancel" data-vk="cancel">{_t("cancel")}</button></div>')


def listen_buttons(card_lang: str, has_english: bool) -> str:
    """Listen controls for the result card. Hidden until the script finds speechSynthesis (and a usable voice)."""
    lang = text_lang(card_lang) if card_lang in CARD_BCP47 else "en"      # a Manipuri card is English text: read it with the English voice
    out = (f'<button class="btn ghost listen" type="button" hidden data-listen="card" data-lang="{esc(lang)}" aria-pressed="false">'
           f'<span aria-hidden="true">🔊</span> <span class="ll">{_t("listen")}</span></button>')
    if has_english and lang != "en":
        out += (f'<button class="btn ghost listen" type="button" hidden data-listen="en" data-lang="en" aria-pressed="false">'
                f'<span aria-hidden="true">🔊</span> <span class="ll">{_t("listen_en")}</span></button>')
    return out + '<span class="note listen-note" role="status" aria-live="polite"></span>'


# ---- Pure helpers (no DOM). Kept in their own string so tests can run them in node. ----
SPEECH_JS = r"""
function speechClean(s){
  s=String(s==null?'':s).replace(/\r/g,'').replace(/https?:\/\/\S+/gi,' ').replace(/\bwww\.\S+/gi,' ')
    .replace(/\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:gov\.in|nic\.in|ac\.in|in|com|org|net|int)\b(?:\/\S*)?/gi,' ');
  s=s.split('\n').map(function(l){l=l.trim();return l&&!/[.!?।॥۔؟]$/.test(l)?l+'.':l}).join(' ');
  s=s.replace(/[^\p{L}\p{M}\p{N}\s.,;:!?%₹'’()\/&।॥۔؟،-]/gu,' ');
  s=s.replace(/\s[-–—]+(?=\s*(?:[.,;:!?।॥۔؟،]|$))/g,'');
  return s.replace(/\s*\.(?:\s*\.)+/g,'.').replace(/\s+/g,' ').replace(/\s+([.,;:!?।॥۔؟،])/g,'$1').trim();
}
function buildSpeech(card,sources,srcWord){
  var body=speechClean(card),names=[];
  (sources||[]).forEach(function(n){n=speechClean(n).replace(/[.]+$/,'');if(n&&names.indexOf(n)<0&&body.toLowerCase().indexOf(n.toLowerCase())<0)names.push(n)});
  return names.length?body+' '+srcWord+': '+names.join(', ')+'.':body;
}
function chunkSpeech(text,max){
  max=max||180;var parts=String(text).match(/[^.!?।॥۔؟]+[.!?।॥۔؟]*\s*/g)||[],out=[],cur='';
  parts.forEach(function(p){
    while(p.length>max){var cut=p.lastIndexOf(' ',max);if(cut<1)cut=max;if(cur){out.push(cur);cur=''}out.push(p.slice(0,cut).trim());p=p.slice(cut)}
    if((cur+p).length>max&&cur){out.push(cur.trim());cur=p}else cur+=p;
  });
  if(cur.trim())out.push(cur.trim());return out.filter(Boolean);
}
function pickVoice(voices,bcp){
  var want=String(bcp).toLowerCase().replace('_','-'),pre=want.split('-')[0],list=Array.prototype.slice.call(voices||[]),norm=function(v){return String(v.lang||'').toLowerCase().replace('_','-')};
  var exact=list.filter(function(v){return norm(v)===want})[0];
  return exact||list.filter(function(v){return norm(v).split('-')[0]===pre})[0]||null;
}
"""

VOICE_JS_BODY = r"""
const S=__STRINGS__,CARD=__CARD__,NAMES=__NAMES__,REC=__REC__,TRY=__TRY__;
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const lg=$('#lang'),ta=$('#text'),form=$('#form'),box=$('#results');
const reduced=()=>!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
const uiLang=()=>{const v=lg?lg.value:'auto';return S[v]?v:'en'};
const tr=(k,l,o)=>{let s=(S[l]&&S[l][k])||S.en[k]||'';if(o)for(const x in o)s=s.split('{'+x+'}').join(o[x]);return s};
const t=(k,o)=>tr(k,uiLang(),o);
const say=(el,msg)=>{if(el)el.textContent=msg};

/* ---- 1. Speak the forward (Web Speech recognition) ---- */
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
const vbox=$('#voicebox'),spk=$('#speak'),vl=$('#vlang'),vst=$('#vstatus'),spl=$('#speaklabel');
let rec=null,listening=false,vtouched=false;
const defVlang=()=>REC[lg&&lg.value]||'en-IN';
const spkUi=()=>{if(!spk)return;spk.setAttribute('aria-pressed',listening?'true':'false');spk.classList.toggle('on',listening);say(spl,listening?t('stop'):t('speak'))};
const ERR={'not-allowed':'err_not_allowed','service-not-allowed':'err_not_allowed','no-speech':'err_no_speech','network':'err_network','audio-capture':'err_audio','language-not-supported':'err_lang'};
function startSpeak(){
  let r;try{r=new SR()}catch(e){say(vst,t('err_generic'));return}
  const base=ta.value&&!/\s$/.test(ta.value)?ta.value+' ':ta.value;let gotErr=false;
  r.continuous=true;r.interimResults=true;r.lang=vl.value;
  r.onstart=()=>{listening=true;spkUi();say(vst,t('listening'))};
  r.onresult=e=>{let s='';for(let i=0;i<e.results.length;i++){const x=(e.results[i][0].transcript||'').trim();if(x)s+=(s?' ':'')+x}
    ta.value=(base+s).slice(0,ta.maxLength>0?ta.maxLength:4000);ta.dispatchEvent(new Event('input',{bubbles:true}));try{ta.setSelectionRange(ta.value.length,ta.value.length);ta.scrollTop=ta.scrollHeight}catch(_){}};
  r.onerror=e=>{if(e.error==='aborted')return;gotErr=true;say(vst,t(ERR[e.error]||'err_generic'))};
  r.onend=()=>{listening=false;rec=null;spkUi();if(!gotErr){say(vst,t('stopped'));try{ta.focus()}catch(_){}}};
  rec=r;try{r.start()}catch(e){listening=false;rec=null;spkUi();say(vst,t('err_generic'))}
}
if(SR&&vbox&&spk&&vl&&ta){
  vbox.hidden=false;vl.value=defVlang();
  vl.addEventListener('change',()=>{vtouched=true;if(rec)try{rec.stop()}catch(_){}});
  if(lg)lg.addEventListener('change',()=>{if(!vtouched)vl.value=defVlang()});
  spk.addEventListener('click',()=>{if(listening&&rec){try{rec.stop()}catch(_){}}else startSpeak()});
  window.addEventListener('pagehide',()=>{if(rec)try{rec.abort()}catch(_){}});
}

/* ---- 2. Listen to the verdict (speechSynthesis) ---- */
const SS=window.speechSynthesis&&window.SpeechSynthesisUtterance?window.speechSynthesis:null;
let speakingBtn=null;
const cardLangOf=()=>{const c=$('.listen[data-listen=card]');return c?(c.dataset.lang||'en'):'en'};
const lbl=(b,on)=>{const ll=b.querySelector('.ll');if(!ll)return;const en=b.dataset.listen==='en',l=en?'en':(b.dataset.lang||'en');
  ll.textContent=on?tr('listen_stop',l):(en?tr('listen_en',cardLangOf()):tr('listen',l))};
const stopReading=()=>{if(SS)try{SS.cancel()}catch(_){}if(speakingBtn){const b=speakingBtn;speakingBtn=null;b.setAttribute('aria-pressed','false');lbl(b,false)}};
const voiceMsg=(l,tryit)=>{const own=S[l]&&S[l]['voice_'+l];return own&&!tryit?own:tr(tryit?'voice_try':'voice_missing',l,{lang:NAMES[l]||l})};
function refreshListen(){
  $$('.listen').forEach(b=>{
    if(!SS){b.hidden=true;return}
    b.hidden=false;const lang=b.dataset.lang||'en',note=b.parentNode.querySelector('.listen-note');
    if(b!==speakingBtn)lbl(b,false);
    const voices=SS.getVoices?SS.getVoices():[],need=(lang!=='en'&&lang!=='tl'),tryit=TRY.indexOf(lang)>=0;
    const none=need&&voices.length>0&&!pickVoice(voices,CARD[lang]);          // an empty list means voices have not loaded yet: stay enabled, speak by lang only
    const missing=none&&!tryit;                                               // a language we only attempt (Odia, Assamese, ...) stays enabled
    b.disabled=!!missing;b.setAttribute('aria-disabled',missing?'true':'false');
    if(note&&b.dataset.listen==='card')note.textContent=none?voiceMsg(lang,tryit):'';
  });
}
function bindListen(){
  $$('.listen').forEach(b=>{if(b.dataset.bound)return;b.dataset.bound='1';
    b.addEventListener('click',()=>{
      if(b.disabled)return;
      if(speakingBtn===b){stopReading();return}
      stopReading();
      const en=b.dataset.listen==='en',node=$(en?'#cardtext_en':'#cardtext');if(!node)return;
      const lang=en?'en':(b.dataset.lang||'en'),srcs=$$('#result .cite a').map(a=>a.textContent);
      const text=buildSpeech(node.innerText||node.textContent,srcs,tr('src_word',lang));if(!text)return;
      const bcp=CARD[lang]||'en-IN',voice=pickVoice(SS.getVoices?SS.getVoices():[],bcp),parts=chunkSpeech(text);
      speakingBtn=b;b.setAttribute('aria-pressed','true');lbl(b,true);
      const done=()=>{if(speakingBtn===b){speakingBtn=null;b.setAttribute('aria-pressed','false');refreshListen()}};
      parts.forEach((p,i)=>{const u=new SpeechSynthesisUtterance(p);u.lang=bcp;if(voice)u.voice=voice;u.rate=0.92;
        if(i===parts.length-1){u.onend=done}u.onerror=ev=>{if(ev&&(ev.error==='canceled'||ev.error==='interrupted'))return;done()};SS.speak(u)});
    })});
  refreshListen();
}
if(SS){bindListen();if(SS.addEventListener)SS.addEventListener('voiceschanged',refreshListen);else SS.onvoiceschanged=refreshListen;
  window.addEventListener('pagehide',stopReading);document.addEventListener('visibilitychange',()=>{if(document.hidden)stopReading()})}

/* ---- 3. Smoother check flow (fetch the same POST, honest progress, cancel) ---- */
const sprog=$('#sprog'),pgEl=$('#pg-elapsed'),pgStage=$('#pg-stage'),pgStill=$('#pg-still'),pgCancel=$('#pg-cancel'),flow=$('#flowstatus'),go=$('#go');
const canFetch=!!(window.fetch&&window.FormData&&window.DOMParser&&window.AbortController&&form&&box&&ta&&sprog&&go);
let ctl=null,tick=null,t0=0,inflight=false;
const STAGES=[0,6,14,22];
function paintProgress(){
  const s=Math.floor((Date.now()-t0)/1000);let i=0;STAGES.forEach((v,k)=>{if(s>=v)i=k});
  say(pgEl,t('elapsed',{n:s}));
  const st=t('step_of',{n:i+1})+' · '+t('stage'+(i+1));if(pgStage.textContent!==st)pgStage.textContent=st;
  if(s>=35)pgStill.hidden=false;
}
function showProgress(){t0=Date.now();sprog.hidden=false;pgStill.hidden=true;pgStage.textContent='';paintProgress();tick=setInterval(paintProgress,1000)}
function hideProgress(){if(tick){clearInterval(tick);tick=null}sprog.hidden=true}
function resetForm(){inflight=false;ctl=null;hideProgress();box.hidden=false;go.disabled=false;go.textContent='Check it';const b=$('#busy');if(b)b.classList.remove('on')}
function announce(msg){if(!flow)return;flow.textContent='';setTimeout(()=>{flow.textContent=msg},50)}
function fallback(){hideProgress();inflight=false;const b=$('#busy');if(b)b.classList.add('on');try{HTMLFormElement.prototype.submit.call(form)}catch(_){form.submit()}}
function swapIn(doc){
  const nb=doc.querySelector('#results');if(!nb)throw new Error('shape');
  box.replaceChildren(...Array.from(nb.childNodes).map(n=>document.importNode(n,true)));box.hidden=false;
  const verdict=box.querySelector('.stamp.big'),err=box.querySelector('[role=alert]'),target=verdict||err;
  const dt=(doc.title||'').trim()||document.title;document.title=verdict?verdict.textContent.trim()+' · '+dt:dt;
  if(window.sachBindResult)window.sachBindResult();bindListen();
  document.dispatchEvent(new CustomEvent('sach:result',{detail:{results:box}}));
  if(target){target.setAttribute('tabindex','-1');target.focus({preventScroll:true});
    target.scrollIntoView({behavior:reduced()?'auto':'smooth',block:'start'})}
  announce(verdict?t('result_ready'):(err?err.textContent:t('result_ready')));
}
async function runCheck(){
  inflight=true;ctl=new AbortController();const b=$('#busy');if(b)b.classList.remove('on');
  go.disabled=true;go.textContent=t('checking');box.hidden=true;showProgress();
  try{
    const multi=form.enctype==='multipart/form-data',fd=new FormData(form);
    const r=await fetch(form.action,{method:'POST',body:multi?fd:new URLSearchParams(fd),signal:ctl.signal,credentials:'same-origin',headers:{'Accept':'text/html'}});
    if(![200,400,413,429].includes(r.status)||!/text\/html/i.test(r.headers.get('content-type')||''))throw new Error('status');
    const doc=new DOMParser().parseFromString(await r.text(),'text/html');
    if(r.status===200&&!doc.querySelector('#results #result'))throw new Error('shape');
    swapIn(doc);resetForm();
  }catch(e){
    if(e&&e.name==='AbortError'){resetForm();announce(t('cancelled'));try{ta.focus()}catch(_){}return}
    fallback();
  }
}
if(canFetch){
  form.addEventListener('submit',e=>{
    if(!ta.value.trim())return;                       // empty: the page's own handler refocuses the box
    e.preventDefault();e.stopImmediatePropagation();
    if(rec)try{rec.stop()}catch(_){}
    stopReading();if(!inflight)runCheck();
  },true);
  pgCancel.addEventListener('click',()=>{if(ctl)ctl.abort()});
  window.addEventListener('pageshow',e=>{if(e.persisted||inflight){if(ctl)try{ctl.abort()}catch(_){}resetForm()}});
}

/* ---- labels follow the reply language (English text is the server-rendered default) ---- */
function applyLang(){
  $$('[data-vk]').forEach(el=>{el.textContent=t(el.dataset.vk)});spkUi();refreshListen();
}
if(lg){lg.addEventListener('change',applyLang)}applyLang();
"""

def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


VOICE_JS = ("(()=>{'use strict';" + SPEECH_JS + VOICE_JS_BODY.replace("__STRINGS__", _js(STRINGS)).replace("__CARD__", _js(CARD_BCP47))
            .replace("__NAMES__", _js(NAMES)).replace("__REC__", _js(REC_DEFAULT)).replace("__TRY__", _js(list(TRY_LISTEN))) + "})();")

VOICE_CSS = """
[hidden]{display:none!important}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.voicebox .btn,.sprog .btn,.listen{min-height:44px}.voicebox select{min-height:44px}
.vstatus{min-height:1.4em;margin:6px 0 0}
#speak.on{background:var(--false);border-color:var(--false);color:#fff}
#speak.on span[aria-hidden]{display:inline-block;animation:vpulse 1s infinite}
.listen[disabled]{cursor:not-allowed}.listen-note{flex-basis:100%}
.sprog{margin-top:16px;padding:14px 16px;border:2px dashed var(--rule);border-radius:4px;background:var(--paper2)}
.sprog p{margin:0 0 8px;max-width:none}.pg-head{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;font-family:var(--mono);font-size:15px}
.pg-head i{display:inline-block;width:10px;height:10px;background:var(--false);border-radius:50%;animation:vpulse 1s infinite}
.pg-stage{font-weight:600;font-size:17px}.pg-still{color:var(--ink);font-weight:600}
@keyframes vpulse{50%{opacity:.3;transform:scale(.75)}}
@media(prefers-reduced-motion:reduce){#speak.on span[aria-hidden],.pg-head i{animation:none!important}}
@media print{.voicebox,.sprog,.listen{display:none!important}}
"""
