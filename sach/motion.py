"""Motion layer: GSAP animations and Lenis smooth scrolling, added on top of the plain pages.

Progressive only. Every page is complete and usable without this file's scripts: nothing is hidden in the HTML or CSS, and no animation
starts below 35 % opacity, so text stays readable even if a script fails or stalls. When the visitor asked for reduced motion, has data saver
on, or the device reports 2 GB of memory or less (many family phones in India), the libraries are not even downloaded. Lenis is used on
pointer devices only; phones keep their native scrolling.

Libraries: GSAP 3.12.5 with ScrollTrigger, and Lenis 1.1.13, pinned and served from Sach's own domain (sach/assets/motion, route /?view=lib).
Switch off with SACH_MOTION=0."""
from __future__ import annotations
import os

# Served from Sach's own domain: the home page makes no third-party request apart from Vercel's own analytics (tests/test_sach.py), so a
# visitor's address never reaches a script CDN. Copied from the public CDNs on 18 Nov 2026. Licences: sach/assets/motion/README.md (GSAP is
# free to use under GreenSock's standard licence but is NOT open source and NOT covered by Sach's MIT licence; Lenis is MIT, notice prepended).
_DIR = os.path.join(os.path.dirname(__file__), "assets", "motion")
FILES = {
    "gsap-3.12.5": ("gsap-3.12.5.min.js", "28033e449a31ebcc396e5be8b13b63152bf03094288fb5867034321927bce087"),
    "scrolltrigger-3.12.5": ("ScrollTrigger-3.12.5.min.js", "ad33c2df9ada8a663c2147357828f980d0b7ca731ef33eb3c6e4f327c3b2cda5"),
    "lenis-1.1.13": ("lenis-1.1.13.min.js", "cb2ee233ae90880f3244b97f7b1242e620578695c817928496e364e0b4f2b436"),
}
GSAP, SCROLL_TRIGGER, LENIS = (f"/?view=lib&f={k}" for k in FILES)


def lib(name: str) -> bytes | None:
    """The library file for /?view=lib&f=<name>, or None for an unknown name (never a path from the request)."""
    entry = FILES.get(name or "")
    if not entry:
        return None
    try:
        with open(os.path.join(_DIR, entry[0]), "rb") as f:
            return f.read()
    except OSError:
        return None


def enabled() -> bool:
    return os.environ.get("SACH_MOTION", "1") != "0"


# Runs in <head>. Decides whether motion will run at all; only then are the three libraries requested (in order, without blocking the page).
# If they have not started within 2.5 s (slow network), the class is removed and the page simply stays as it is.
HEAD_JS = """(function(){try{var d=document.documentElement,n=navigator,c=n.connection||{};
if(matchMedia('(prefers-reduced-motion: reduce)').matches||c.saveData||(n.deviceMemory&&n.deviceMemory<=2))return;
d.classList.add('motion');setTimeout(function(){if(!window.__sachMotion)d.classList.remove('motion')},2500);
var srcs=[%s];srcs.forEach(function(u,i){var s=document.createElement('script');s.src=u;s.async=false;
s.onerror=function(){d.classList.remove('motion')};if(i===srcs.length-1)s.onload=function(){window.__sachLibs=1;if(window.__sachRun)window.__sachRun()};
document.head.appendChild(s)})}catch(e){}})();""" % ",".join(f"'{u}'" for u in (GSAP, SCROLL_TRIGGER, LENIS))

CSS = """
html.motion .stampbox .stamp{animation:none}
.lenis.lenis-smooth{scroll-behavior:auto!important}.lenis.lenis-smooth [data-lenis-prevent]{overscroll-behavior:contain}
.lenis.lenis-stopped{overflow:hidden}
@media print{html.motion *{opacity:1!important;transform:none!important}}
"""

INIT_JS = r"""
(function(){var ran=false;
function run(){
  var d=document.documentElement;
  if(!d.classList.contains('motion')||!window.gsap){d.classList.remove('motion');return}
  window.__sachMotion=true;
  // Nothing ever starts fully invisible: if an animation stalls, every word stays readable.
  var FLOOR=.35;
  var g=window.gsap,ST=window.ScrollTrigger;if(ST)g.registerPlugin(ST);
  // Real time, not frame count: on a slow phone or a busy tab a late frame jumps ahead instead of making the animation crawl.
  g.ticker.lagSmoothing(0);
  // A plain timer (not an animation frame) finishes any animation that is still running after this long, so content can never stay hidden.
  var finish=function(tw,ms){setTimeout(function(){if(tw.progress()<1)tw.progress(1)},ms)};
  try{
    // Smooth scrolling for mouse and trackpad only: phones keep native scrolling, which is what their owners expect.
    if(window.Lenis&&matchMedia('(pointer:fine)').matches){
      var lenis=new Lenis({duration:1.1,smoothWheel:true});
      if(ST){lenis.on('scroll',ST.update);g.ticker.add(function(t){lenis.raf(t*1000)})}
      else{(function raf(t){lenis.raf(t);requestAnimationFrame(raf)})(0)}
      document.addEventListener('click',function(e){
        if(e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;   // new tab, new window, download: the browser's own
        var a=e.target.closest&&e.target.closest('a[href^="#"],a[href^="/#"]');if(!a||a.target||a.hasAttribute('download'))return;
        if(a.getAttribute('href').charAt(0)==='/'&&(location.pathname!=='/'||location.search))return;   // a link to the home page from another page
        var id=a.getAttribute('href').replace(/^\/?/,'');var el=id.length>1&&document.querySelector(id);if(!el)return;
        e.preventDefault();lenis.scrollTo(el,{offset:-80});history.replaceState(null,'',id);
        // Move keyboard focus to the target, as the browser does for an ordinary in-page link (the skip link, screen readers).
        if(!el.hasAttribute('tabindex'))el.setAttribute('tabindex','-1');el.focus({preventScroll:true})});
      window.__sachLenis=lenis;
    }
    // Hero: headline, lede and buttons rise in; the four verdict stamps land one after another, as if stamped. Only when the libraries arrived
    // quickly: on a slow connection the hero has long been on screen, and replaying it would be a flash and a jump.
    if(performance.now()<1500){
      var tl=g.timeline({defaults:{ease:'power3.out'}});
      tl.fromTo('.hero h1',{y:28,opacity:FLOOR},{y:0,opacity:1,duration:.8})
        .fromTo('.hero .lede',{y:18,opacity:FLOOR},{y:0,opacity:1,duration:.6},'-=.45')
        .fromTo('.hero .row',{y:14,opacity:FLOOR},{y:0,opacity:1,duration:.5},'-=.35')
        .fromTo('.stampbox .stamp',{scale:1.9,opacity:FLOOR},{scale:1,opacity:1,duration:.42,ease:'back.out(2.2)',stagger:.16,clearProps:'scale'},'-=.6');
      finish(tl,2000);
    }
    // Sections: the heading and its cards rise in once, when they reach the screen. Sections already on screen are left alone.
    if(ST){
      g.utils.toArray('main section').forEach(function(sec){
        if(sec.getBoundingClientRect().top<innerHeight*.85)return;
        var parts=sec.querySelectorAll(':scope > .wrap > h2, :scope > .wrap > .sub, .card, .checker');
        if(!parts.length)return;
        var tw=g.from(parts,{y:24,opacity:FLOOR,duration:.6,ease:'power2.out',stagger:.06,paused:true});
        ST.create({trigger:sec,start:'top 85%',once:true,onEnter:function(){tw.play();finish(tw,1500)}});
      });
      // The stamps drift slightly as the hero scrolls away.
      g.to('.stampbox',{yPercent:-12,ease:'none',scrollTrigger:{trigger:'.hero',start:'top top',end:'bottom top',scrub:true}});
    }
    // A verdict arriving: the stamp lands and the card slides in, instead of appearing all at once.
    var res=document.getElementById('results');
    if(res&&window.MutationObserver){new MutationObserver(function(){
      var r=res.querySelector('.result');if(!r||r.dataset.animated)return;r.dataset.animated='1';
      var st=r.querySelector('.stamp');
      if(st)finish(g.fromTo(st,{scale:2.2,opacity:FLOOR},{scale:1,opacity:1,duration:.45,ease:'back.out(2)',clearProps:'scale,opacity'}),1200);
      finish(g.from(r.querySelectorAll('.bubble, table, section, details'),{y:18,opacity:FLOOR,duration:.5,stagger:.05,delay:.2,ease:'power2.out'}),1500);
      if(window.__sachLenis)window.__sachLenis.resize();
    }).observe(res,{childList:true,subtree:true})}
  }catch(e){d.classList.remove('motion');try{g.set('.hero h1, .hero .lede, .hero .row, main section *',{clearProps:'opacity,transform'})}catch(_){}}
}
window.__sachRun=function(){
  if(ran||!window.__sachLibs)return;
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',window.__sachRun);return}
  ran=true;run();
};
window.__sachRun();
})();
"""


def head() -> str:
    """The early check and the CSS, for <head>. The libraries are requested by the check itself, and only when motion will run."""
    return f"<script>{HEAD_JS}</script><style>{CSS}</style>" if enabled() else ""


def body_end() -> str:
    """The setup script, placed at the end of <body>."""
    return f"<script>{INIT_JS}</script>" if enabled() else ""
