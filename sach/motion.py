"""Motion layer: GSAP animations and Lenis smooth scrolling, added on top of the plain pages.

Progressive only. Every page is complete and usable without this file's scripts: nothing is hidden in the HTML or CSS, and no animation
starts below 35 % opacity, so text stays readable even if a script fails or stalls. It does nothing at all when the visitor asked for reduced motion, has data saver on, or the device reports 2 GB of
memory or less (many family phones in India). Lenis is used on pointer devices only; phones keep their native scrolling.

Libraries (pinned, served from Sach's own domain with `defer`): GSAP 3.12.5 with ScrollTrigger, and Lenis 1.1.13.
Switch off with SACH_MOTION=0."""
from __future__ import annotations
import os

# Served from Sach's own domain (sach/assets/motion, route /?view=lib): the home page makes no third-party request apart from Vercel's own
# analytics (tests/test_sach.py), so a visitor's address never reaches a script CDN. Copied unchanged from the public CDNs on 18 Nov 2026;
# SHA-256 below. GSAP: GreenSock standard licence (bundling in your own site allowed); Lenis: MIT.
_DIR = os.path.join(os.path.dirname(__file__), "assets", "motion")
FILES = {
    "gsap-3.12.5": ("gsap-3.12.5.min.js", "28033e449a31ebcc396e5be8b13b63152bf03094288fb5867034321927bce087"),
    "scrolltrigger-3.12.5": ("ScrollTrigger-3.12.5.min.js", "ad33c2df9ada8a663c2147357828f980d0b7ca731ef33eb3c6e4f327c3b2cda5"),
    "lenis-1.1.13": ("lenis-1.1.13.min.js", "b2958f142f832f0d5e547cdef77e6fadfce16bea60982fc8bbf50395a2439df8"),
}
GSAP, SCROLL_TRIGGER, LENIS = (f"/?view=lib&amp;f={k}" for k in FILES)


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


# Decides before first paint whether motion will run (and turns off the stamps' CSS drop so GSAP can play it instead). If the libraries have not
# started within 2.5 s (blocked CDN, slow network), the class is removed and the page shows as it always did. Nothing is hidden in CSS: the
# animations start from 35 % opacity at the lowest, so a stalled animation can never leave text unreadable.
HEAD_JS = """(function(){try{var d=document.documentElement,n=navigator,c=n.connection||{};
if(matchMedia('(prefers-reduced-motion: reduce)').matches||c.saveData||(n.deviceMemory&&n.deviceMemory<=2))return;
d.classList.add('motion');setTimeout(function(){if(!window.__sachMotion)d.classList.remove('motion')},2500)}catch(e){}})();"""

CSS = """
html.motion .stampbox .stamp{animation:none}
.lenis.lenis-smooth{scroll-behavior:auto!important}.lenis.lenis-smooth [data-lenis-prevent]{overscroll-behavior:contain}
.lenis.lenis-stopped{overflow:hidden}
"""

INIT_JS = r"""
document.addEventListener('DOMContentLoaded',function(){
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
  var show=function(sel){g.set(sel,{opacity:1})};
  try{
    // Smooth scrolling for mouse and trackpad only: phones keep native scrolling, which is what their owners expect.
    if(window.Lenis&&matchMedia('(pointer:fine)').matches){
      var lenis=new Lenis({duration:1.1,smoothWheel:true});
      if(ST){lenis.on('scroll',ST.update);g.ticker.add(function(t){lenis.raf(t*1000)})}
      else{(function raf(t){lenis.raf(t);requestAnimationFrame(raf)})(0)}
      document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href^="#"],a[href^="/#"]');if(!a)return;
        if(a.getAttribute('href').charAt(0)==='/'&&location.pathname!=='/')return;
        var id=a.getAttribute('href').replace(/^\/?/,'');var el=id.length>1&&document.querySelector(id);if(!el)return;
        e.preventDefault();lenis.scrollTo(el,{offset:-80});history.replaceState(null,'',id)});
      window.__sachLenis=lenis;
    }
    // Hero: headline, lede and buttons rise in; the four verdict stamps land one after another, as if stamped.
    var tl=g.timeline({defaults:{ease:'power3.out'}});
    tl.fromTo('.hero h1',{y:28,opacity:FLOOR},{y:0,opacity:1,duration:.8})
      .fromTo('.hero .lede',{y:18,opacity:FLOOR},{y:0,opacity:1,duration:.6},'-=.45')
      .fromTo('.hero .row',{y:14,opacity:FLOOR},{y:0,opacity:1,duration:.5},'-=.35')
      .fromTo('.stampbox .stamp',{scale:1.9,opacity:FLOOR},{scale:1,opacity:1,duration:.42,ease:'back.out(2.2)',stagger:.16,clearProps:'scale'},'-=.6');
    finish(tl,2000);
    // Sections: the heading and its cards rise in once, when they reach the screen.
    if(ST){
      g.utils.toArray('main section').forEach(function(sec){
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
      if(st)g.fromTo(st,{scale:2.2,opacity:FLOOR},{scale:1,opacity:1,duration:.45,ease:'back.out(2)',clearProps:'scale,opacity'});
      finish(g.from(r.querySelectorAll('.bubble, table, section, details'),{y:18,opacity:FLOOR,duration:.5,stagger:.05,delay:.2,ease:'power2.out'}),1500);
      if(window.__sachLenis)window.__sachLenis.resize();
    }).observe(res,{childList:true,subtree:true})}
  }catch(e){show('.hero h1, .hero .lede, .hero .row');d.classList.remove('motion')}
});
"""


def head() -> str:
    """Tags for <head>: the early check, the CSS and the three libraries (deferred, so they never block the page)."""
    if not enabled():
        return ""
    return (f"<script>{HEAD_JS}</script><style>{CSS}</style>"
            f'<script defer src="{GSAP}"></script><script defer src="{SCROLL_TRIGGER}"></script><script defer src="{LENIS}"></script>')


def body_end() -> str:
    """The setup script, placed at the end of <body>."""
    return f"<script>{INIT_JS}</script>" if enabled() else ""
