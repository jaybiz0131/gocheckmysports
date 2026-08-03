#!/usr/bin/env python3
"""
edition.py: The Edition, the composed front page (owner spec 2026-08-03; reconciled
against the approved edition-demo.html per the owner's reconciliation order).

THE CHASSIS RENDERER. Crypto first per the build order; News and Sports extend by
SKINNING (the DESK dict is the whole per-desk surface; anything crypto-specific outside
it is a bug). The desk already exercises judgment (rank, the Brief, the verifier); this
layer RENDERS that judgment. It re-ranks nothing, fetches nothing, and adds no
commercial element (tier doctrine).

DEMO RECONCILIATION (demo wins on composition and proportions; inference only where the
demo is silent): two-font system (serif body/display, Inter furniture), in-flow topbar
with Vol/No and the mode toggles, masthead weight 600 with motto, dateline rules 2px
over 1px, uniform rail sizing, brief band as kicker+stamp head with three columns and
no display headline, down-page left-rule cards, demo color tokens in all three themes,
data-theme semantics on the document element. Every resolved difference is listed in
the build report, not resolved silently.

FIELD-GAP RULINGS (owner, 2026-08-03): sections ship as routes ONLY when real per-story
tags exist; the corpus is uniformly category="news", so v1 renders the sections nav
with only its REAL destinations (Front Page, Back Issues) and no dead links. Kickers
render only real data: the house desk label plus "Updated" when update_of is set.
Reading-mode preference persists via the site's established guarded-localStorage
pattern (ruling accepted).

The demo names 'Newsreader' first in the serif stack without loading it, so Georgia
renders in practice; the stack is kept verbatim so a later self-hosted Newsreader
lights up without a template change.
"""
import datetime
import html as _html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

DESK = {
    "name": "GoCheckMy Sports",
    "motto": "Independent · Scores Are Sourced · Never Betting Advice",
    "folio": ("GoCheckMy Sports is a news desk of Go Check My Brands LLC · "
              "Every source linked · Never betting advice"),
    "place": "Charleston, S.C.",
    "origin": "https://gocheckmysports.com",
    "desk_label": "The Desk",
    "volume": "Vol. I",
    "sections_when_tagged": ["Leagues", "Transfers", "Governance", "Records"],
}


def esc(s):
    return _html.escape(str(s or ""), quote=True)


def _when(d):
    return str(d.get("published_utc") or d.get("date") or "")


def _is_edition(d):
    return (d.get("category") or "").lower() == "daily edition"


def _day_of(d):
    return _when(d)[:10]


CYCLE_HOURS = 30      # the front carries the news CYCLE, not midnight-to-midnight
FRONT_SLOTS = 10      # lead + three rail + six down-page
MAX_BACKFILL_H = 72   # the density floor's reach: a quiet cycle widens its window in
                      # steps until the front fills or the cap is hit (owner direction
                      # 2026-08-03: readers get a full paper, never a scarce one; only
                      # real desk reporting, never padding)


def select(items, day):
    """One edition's inputs: the day's edition item (the Brief) and the ranked stories
    of its news cycle. The window is CYCLE_HOURS back from the edition's own timestamp
    (owner review note, 2026-08-03: a calendar-day window starved a light day to three
    stories while the composition holds ten; an afternoon edition legitimately carries
    the prior evening's reporting). Ranking is the desk's own `rank`; the composition
    renders it, never re-ranks, and never reaches past its own edition's press time."""
    eds = sorted((d for d in items if _is_edition(d) and _day_of(d) == day),
                 key=_when, reverse=True)
    ed = eds[0] if eds else None
    press = _when(ed) if ed else f"{day}T23:59:59Z"
    p = datetime.datetime.fromisoformat(press.replace("Z", "+00:00"))
    hi = press
    hours = CYCLE_HOURS
    while True:
        lo = (p - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stories = [d for d in items if not _is_edition(d) and not d.get("example")
                   and lo <= _when(d) <= hi]
        if len(stories) >= FRONT_SLOTS or hours >= MAX_BACKFILL_H:
            break
        hours += 12
    stories.sort(key=lambda d: (_day_of(d) != day,
                                d.get("rank") if isinstance(d.get("rank"), (int, float))
                                else 999, _when(d)))
    return ed, stories


def edition_days(items):
    return sorted({_day_of(d) for d in items if _is_edition(d)}, reverse=True)


def _clip(text, n):
    """Cut at a word boundary and never on a dangling function word."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:")
    words = cut.split(" ")
    STOP = {"and", "or", "but", "the", "a", "an", "as", "with", "of", "to", "in",
            "on", "at", "for", "its", "his", "her", "their", "even", "while",
            "across", "that"}
    while words and words[-1].lower().rstrip(".,") in STOP:
        words.pop()
    cut = " ".join(words).rstrip(",;:")
    return cut + ("." if not cut.endswith(".") else "")


# Demo tokens verbatim; inference only where the demo is silent (print page-break
# tuning, phone collapse of topbar/dateline, the skip link the site standard requires).
CSS = """
:root{
  --paper:#F7F5F0; --ink:#1A1A1A; --ink-soft:#444444; --ink-faint:#6B6B6B;
  --rule:#C9C4B8; --rule-heavy:#1A1A1A; --accent:#9C4A21; --link:#184454;
  --measure:38rem;
  --serif:'Newsreader', Georgia, 'Times New Roman', serif;
  --sans:Inter,system-ui,sans-serif;
}
[data-theme="dark"]{
  --paper:#141414; --ink:#E8E4DC; --ink-soft:#B8B4AC; --ink-faint:#8A8680;
  --rule:#3A3833; --rule-heavy:#E8E4DC; --accent:#C89A4A; --link:#79B8BE;
}
[data-theme="eink"]{
  --paper:#FFFFFF; --ink:#000000; --ink-soft:#000000; --ink-faint:#333333;
  --rule:#999999; --rule-heavy:#000000; --accent:#000000; --link:#000000;
}
[data-theme="eink"] *{transition:none !important; animation:none !important;
  text-shadow:none !important;}
[data-theme="eink"] body{font-family:Georgia,'Times New Roman',serif;}
*{box-sizing:border-box; margin:0;}
html{scroll-behavior:smooth;}
@media (prefers-reduced-motion: reduce){ html{scroll-behavior:auto;} }
body{background:var(--paper); color:var(--ink); font-family:var(--serif);
  font-size:1.0625rem; line-height:1.55;}
a{color:var(--link); text-decoration:none;}
a:hover{text-decoration:underline;}
a:focus-visible{outline:2px solid var(--accent); outline-offset:2px;}
.ed-skip{position:absolute;left:-9999px}
.ed-skip:focus{left:.5rem;top:.5rem;background:var(--ink);color:var(--paper);
  padding:.4rem .7rem;z-index:9}
.sheet{max-width:76rem; margin:0 auto; padding:0 1.25rem 4rem;}
/* topbar */
.topbar{display:flex; justify-content:space-between; align-items:baseline;
  padding:.55rem 0; border-bottom:1px solid var(--rule);
  font-family:var(--sans); font-size:.72rem;
  letter-spacing:.08em; text-transform:uppercase; color:var(--ink-faint);}
.topbar .modes{display:flex; gap:.9rem;}
.topbar button{background:none; border:none; padding:0; cursor:pointer;
  font:inherit; color:var(--ink-faint); letter-spacing:.08em; text-transform:uppercase;}
.topbar button[aria-pressed="true"]{color:var(--ink); border-bottom:2px solid var(--accent);}
.topbar button:focus-visible{outline:2px solid var(--accent); outline-offset:2px;}
@media(max-width:40rem){.topbar{flex-wrap:wrap;justify-content:center;gap:.4rem .9rem}}
/* masthead */
.masthead{text-align:center; padding:1.6rem 0 .9rem;}
.masthead h1{font-weight:600; font-size:clamp(2.4rem,6vw,4.4rem);
  letter-spacing:.01em; line-height:1;}
.masthead .motto{font-family:var(--sans); font-size:.72rem;
  letter-spacing:.22em; text-transform:uppercase; color:var(--ink-faint);
  margin-top:.55rem;}
.dateline{display:flex; justify-content:space-between; align-items:center;
  border-top:2px solid var(--rule-heavy); border-bottom:1px solid var(--rule-heavy);
  padding:.4rem 0; margin-top:1rem;
  font-family:var(--sans); font-size:.78rem;
  letter-spacing:.06em; text-transform:uppercase;}
@media(max-width:40rem){.dateline{flex-wrap:wrap;gap:.2rem .9rem;justify-content:center}}
.sections{display:flex; gap:1.4rem; flex-wrap:wrap; justify-content:center;
  padding:.55rem 0; border-bottom:1px solid var(--rule);
  font-family:var(--sans); font-size:.78rem; letter-spacing:.1em;
  text-transform:uppercase;}
.sections a{color:var(--ink-soft);}
.sections a[aria-current]{color:var(--accent); font-weight:600;}
/* front grid */
.front{display:grid; gap:0 2.2rem; margin-top:1.6rem; grid-template-columns:1fr;}
@media(min-width:900px){
  .front{grid-template-columns:1.9fr 1fr;}
  .lead{border-right:1px solid var(--rule); padding-right:2.2rem;}
}
.kicker{font-family:var(--sans); font-size:.7rem; font-weight:600;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent);}
.lead h2{font-weight:600; font-size:clamp(1.7rem,3.6vw,2.6rem);
  line-height:1.12; margin:.35rem 0 .5rem; letter-spacing:-.005em;}
.lead h2 a{color:var(--ink);}
.dek{font-size:1.08rem; font-style:italic; color:var(--ink-soft);
  margin-bottom:.9rem; line-height:1.4;}
.byline{font-family:var(--sans); font-size:.72rem;
  letter-spacing:.06em; text-transform:uppercase; color:var(--ink-faint);
  margin-bottom:.9rem;}
.lead .body{column-count:1; column-gap:2rem; column-rule:1px solid var(--rule);}
@media(min-width:640px){ .lead .body{column-count:2;} }
.body p{margin-bottom:.85rem; text-align:justify; hyphens:auto;}
.body p:first-of-type::first-letter{
  float:left; font-size:3.4em; line-height:.82; padding:.04em .08em 0 0; font-weight:600;}
.continued{font-family:var(--sans); font-size:.78rem; letter-spacing:.05em;
  text-transform:uppercase; font-weight:600;}
.continued a{color:var(--accent);}
/* rail */
.rail article{padding:0 0 1.1rem; margin-bottom:1.1rem; border-bottom:1px solid var(--rule);}
.rail article:last-child{border-bottom:none;}
.rail h3{font-weight:600; font-size:1.22rem; line-height:1.2; margin:.3rem 0 .35rem;}
.rail h3 a{color:var(--ink);}
.rail p{font-size:.98rem; color:var(--ink-soft);}
/* the Brief */
.brief{margin-top:2.2rem; border-top:2px solid var(--rule-heavy); padding-top:1.1rem;}
.brief-head{display:flex; align-items:baseline; gap:1rem; margin-bottom:.8rem;}
.brief-head .kicker{color:var(--ink);}
.brief-head .stamp{font-family:var(--sans); font-size:.72rem; color:var(--ink-faint);
  letter-spacing:.05em; text-transform:uppercase;}
.brief-cols{column-count:1; column-gap:2.2rem; column-rule:1px solid var(--rule);
  font-size:1rem;}
@media(min-width:760px){ .brief-cols{column-count:3;} }
.brief-cols p{margin-bottom:.8rem; text-align:justify; hyphens:auto;}
.brief-cites{margin-top:.9rem; padding-top:.6rem; border-top:1px solid var(--rule);
  font-family:var(--sans); font-size:.8rem; color:var(--ink-soft);}
.brief-cites a{margin-right:1.2rem;}
/* down-page */
.downpage{margin-top:2rem; border-top:1px solid var(--rule-heavy); padding-top:1.2rem;
  display:grid; gap:1.4rem 2.2rem; grid-template-columns:1fr;}
@media(min-width:760px){ .downpage{grid-template-columns:repeat(3,1fr);} }
.downpage article{border-left:2px solid var(--rule); padding-left:.9rem;}
.downpage h3{font-weight:600; font-size:1.05rem; line-height:1.25; margin:.25rem 0 .3rem;}
.downpage h3 a{color:var(--ink);}
.downpage p{font-size:.92rem; color:var(--ink-soft); font-style:italic;}
/* back issues + folio */
.backrow{margin-top:2rem;font-family:var(--sans);font-size:.78rem;color:var(--ink-faint);
  letter-spacing:.05em}
.folio{margin-top:2.6rem; border-top:2px solid var(--rule-heavy); padding-top:.7rem;
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:.6rem;
  font-family:var(--sans); font-size:.75rem; color:var(--ink-faint);
  letter-spacing:.05em;}
.folio a{color:var(--ink-soft);}
/* print: the paper edition (demo base; page-break tuning is inference where the
   demo is silent) */
@media print{
  @page{margin:14mm 12mm}
  .topbar,.sections,.backrow{display:none;}
  body{background:#fff; color:#000; font-size:10.5pt;}
  .sheet{max-width:100%; padding:0;}
  .lead .body{column-count:2;}
  .brief-cols{column-count:3;}
  a{color:#000;}
  .front{grid-template-columns:2fr 1fr;}
  .rail article,.downpage article{break-inside:avoid;}
}
"""


JS = """
(function(){
  /* Demo's data-theme semantics + the site's established guarded-localStorage
     persistence (owner ruling accepted, 2026-08-03). Print register is the default;
     a failed read degrades to the default, never to breakage. */
  var KEY='edition-mode';
  var MAP={print:'',night:'dark',eink:'eink'};
  var cur='print';
  try{var s=localStorage.getItem(KEY); if(s in MAP)cur=s;}catch(e){}
  function apply(){
    document.documentElement.setAttribute('data-theme',MAP[cur]);
    var bs=document.querySelectorAll('.modes button[data-mode]');
    for(var i=0;i<bs.length;i++)bs[i].setAttribute('aria-pressed',
      String(bs[i].getAttribute('data-mode')===cur));
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest?e.target.closest('.modes button[data-mode]'):null;
    if(b){cur=b.getAttribute('data-mode');try{localStorage.setItem(KEY,cur)}catch(e2){}apply();}
    var p=e.target.closest?e.target.closest('.modes button[data-print]'):null;
    if(p){window.print();}
  });
  apply();
})();
"""


def _edition_slot(ed):
    t = str(ed.get("title") or "") if ed else ""
    m = re.search(r"(Morning|Afternoon|Midday|Evening)", t, re.I)
    return (m.group(1).title() + " Edition") if m else "The Edition"


def _brief_name(ed):
    t = str(ed.get("title") or "") if ed else ""
    m = re.search(r"The\s+\w+\s+(?:Brief|Wrap|Update)", t, re.I)
    return m.group(0) if m else "The Brief"


def _human_date(day):
    return datetime.date.fromisoformat(day).strftime("%A, %B %-d, %Y")


def _utc_stamp(d):
    m = re.search(r"T(\d{2}):(\d{2})", _when(d))
    if not m:
        return ""
    hh, mm = int(m.group(1)), m.group(2)
    ampm = "AM" if hh < 12 else "PM"
    return f"{(hh % 12) or 12}:{mm} {ampm} UTC"


def _story_url(d):
    return f"/articles/{esc(d.get('slug'))}.html"


def _kicker(desk, d):
    """Real data only (owner ruling): the house desk label, plus Updated when the
    story really is an update. No invented sections, no keyword matching."""
    k = desk["desk_label"]
    if d.get("update_of"):
        k += " · Updated"
    return esc(k)


def render_front(desk, items, day, all_days, canonical_path="/news.html"):
    ed, stories = select(items, day)
    lead = stories[0] if stories else None
    rail = stories[1:4]
    down = stories[4:10]
    slot = _edition_slot(ed)
    issue_no = len(all_days) - all_days.index(day)

    topbar = f"""<div class="topbar">
  <span>{esc(desk["volume"])} · No. {issue_no}</span>
  <nav class="modes" aria-label="Reading modes">
    <button data-mode="print" aria-pressed="true">Print</button>
    <button data-mode="night" aria-pressed="false">Night</button>
    <button data-mode="eink" aria-pressed="false">E-ink</button>
    <button data-print="1">Print or save as PDF</button>
  </nav>
</div>"""

    # Sections nav, v1: only REAL destinations (no dead links, no faked sections; the
    # demo's crypto section list lives in DESK until per-story tags exist).
    head = f"""<header class="masthead">
  <h1>{esc(desk["name"])}</h1>
  <p class="motto">{esc(desk["motto"])}</p>
  <div class="dateline">
    <span>{esc(_human_date(day))}</span>
    <span>{esc(slot)}</span>
    <span>{esc(desk["place"])}</span>
  </div>
  <nav class="sections" aria-label="Sections">
    <a href="/news.html"{' aria-current="page"' if canonical_path == "/news.html" else ""}>Front Page</a>
    <a href="/archive.html">Back Issues</a>
  </nav>
</header>"""

    lead_html = ""
    if lead:
        opening = "".join(f"<p>{p}</p>" for p in (lead.get("body") or [])[:3])
        lead_html = f"""<article class="lead">
  <span class="kicker">{_kicker(desk, lead)}</span>
  <h2><a href="{_story_url(lead)}">{esc(lead.get("title"))}</a></h2>
  <p class="dek">{esc(lead.get("dek"))}</p>
  <p class="byline">By {esc(lead.get("author") or "the desk")} · {esc(_utc_stamp(lead))}</p>
  <div class="body">{opening}</div>
  <p class="continued"><a href="{_story_url(lead)}">Continued &#8594;</a></p>
</article>"""

    rail_html = "".join(f"""<article>
  <span class="kicker">{_kicker(desk, d)}</span>
  <h3><a href="{_story_url(d)}">{esc(d.get("title"))}</a></h3>
  <p>{esc(_clip(d.get("dek"), 220))}</p>
</article>""" for d in rail)

    brief_html = ""
    if ed:
        cites = "".join(
            f'<a href="{esc(s.get("url") or "#")}">{esc(_clip(s.get("title") or s.get("url") or "", 60))}</a>'
            for s in (ed.get("sources") or [])[:8])
        brief_html = f"""<section class="brief" aria-label="{esc(_brief_name(ed))}">
  <div class="brief-head">
    <span class="kicker">{esc(_brief_name(ed))}</span>
    <span class="stamp">The desk's synthesis · {esc(_utc_stamp(ed))}</span>
  </div>
  <div class="brief-cols">{"".join(f"<p>{p}</p>" for p in (ed.get("body") or []))}</div>
  <div class="brief-cites">In this brief: {cites}</div>
</section>"""

    down_html = "".join(f"""<article>
  <h3><a href="{_story_url(d)}">{esc(d.get("title"))}</a></h3>
  <p>{esc(_clip(d.get("dek"), 140))}</p>
</article>""" for d in down)
    down_html = (f'<section class="downpage" aria-label="More from the desk">'
                 f'{down_html}</section>') if down_html else ""

    prev_links = " &middot; ".join(
        f'<a href="/edition/{d}.html">{d}</a>' for d in all_days[:14] if d != day)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(slot)} &middot; {esc(desk["name"])}</title>
<meta name="description" content="The composed daily edition of {esc(desk["name"])}: the desk's ranked reporting and {esc(_brief_name(ed))}, as one front page.">
<link rel="canonical" href="{esc(desk["origin"])}{esc(canonical_path)}">
<style>{CSS}</style>
</head>
<body>
<a class="ed-skip" href="#main">Skip to main content</a>
<div class="sheet">
{topbar}
{head}
<main class="front" id="main">
{lead_html}
<aside class="rail" aria-label="Top stories">{rail_html}</aside>
</main>
{brief_html}
{down_html}
<div class="backrow">Back issues: {prev_links}</div>
<footer class="folio">
  <span>{esc(desk["folio"])}</span>
  <span><a href="/standards.html">Standards &amp; Corrections</a> &middot; <a href="/about.html">About</a> &middot; <a href="/archive.html">Archive</a></span>
</footer>
</div>
<script>{JS}</script>
</body>
</html>"""


def build(items, w, desk=DESK):
    """Render the edition front at the Latest route plus every back issue. Called from
    site_build.build(); touches nothing else. `desk` is the whole skinning surface."""
    days = edition_days(items)
    if not days:
        return 0
    w("news.html", render_front(desk, items, days[0], days, canonical_path="/news.html"))
    for d in days:
        w(f"edition/{d}.html", render_front(desk, items, d, days,
                                            canonical_path=f"/edition/{d}.html"))
    return len(days)
