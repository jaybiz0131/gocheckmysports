#!/usr/bin/env python3
"""
site_build.py: build the public GoCheckMySports site from committed content.

Reproducible + lossless (the GoCheckMyPet lesson D2: everything the page needs is emitted
here from the templates, so rebuilding never strips the footer, disclaimer, or schema). Reads
site/content/*.json (one file per published item; _-prefixed files are ignored) and renders a
static deploy folder site/publish/: home, archive, one page per article, plus the static
editorial pages (about / how we work / standards) and a 404. No third-party dependency; no em
dashes; the no-betting-advice disclaimer baked into every article and the footer.

CONTENT FLOW
  A story is published only after a human approves it (publish.py, Stage 6). Promote approved
  payloads into committed site content with --ingest, then rebuild:

    python3 site_build.py --ingest      # out/published/*.json -> site/content/*.json, then build
    python3 site_build.py               # build site/publish/ from committed content

USAGE
  python3 site_build.py [--ingest]
"""

import datetime
import json
import os
import re
import sys
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
CONTENT = os.path.join(SITE, "content")
ASSETS = os.path.join(SITE, "assets")
PUBLISH = os.path.join(SITE, "publish")
PUBLISHED = os.path.join(HERE, "out", "published")

# Brand: GoCheckMySports is a daily sports news desk in the GoCheckMy family
# (gocheckmysports.com), tied to the family hub through the "A GoCheckMy site" footer link.
# One identity everywhere: the desk and the site share the name.
NAME = "GoCheckMySports"
SLOGAN = "The score is a fact. The story gets checked."   # the brand tagline
DESK_LINE = "The daily sports desk that checks the story before it runs."   # secondary descriptor
FAMILY = "GoCheckMySports"                     # family/domain tie: gocheckmysports.com
FAMILY_HUB = "https://gocheckmy.com/"          # the GoCheckMy family hub (canonical footer link)
ORIGIN = "https://gocheckmysports.com"         # canonical origin for canonical/og:url/sitemap
OG_IMAGE = ORIGIN + "/og-image.png"            # 1200x630 social card, committed at site/assets/og-image.png
CF_ANALYTICS_TOKEN = ""  # Cloudflare Web Analytics site token for gocheckmysports.com; empty renders no beacon
DESC = ("GoCheckMySports is an independent daily sports news desk built with one intention: "
        "get the stories right and keep the facts honest. Scores are facts; stories get "
        "checked against their sources before they run. Never betting advice.")
FAMILY_DESC = ("GoCheckMySports is sports, checked: a daily news desk that verifies every "
               "story against official league data and on-record sources before it runs. "
               "The score is a fact. The story gets checked. Never betting advice.")
NFA = ("GoCheckMySports reports events. It never advises bets. Nothing here is betting or "
       "gambling advice.")
YEAR = "2026"
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

NAV = [("Home", "/index.html"), ("Latest", "/news.html"),
       ("Archive", "/archive.html"), ("About", "/about.html")]


# ---- helpers -----------------------------------------------------------------

def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "story"


def fmt_date(iso):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso or ""))
    if not m:
        return str(iso or "")
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{MONTHS[mo]} {d}, {y}"


def _parse_utc(item):
    """datetime for a story's publish moment: published_utc when stamped (new stories),
    else midnight of its date (legacy stories carry a date only)."""
    from datetime import datetime, timezone
    for fmt, val in (("%Y-%m-%dT%H:%M:%SZ", item.get("published_utc") or ""),
                     ("%Y-%m-%d", item.get("date") or "")):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fmt_when(item):
    """Dateline with the publish time when we have one: 'July 12, 2026 · 07:41 UTC'.
    Games end late and news breaks around the clock; a reader needs to know 2 hours old vs 20."""
    base = esc(fmt_date(item.get("date")))
    if item.get("published_utc"):
        dt = _parse_utc(item)
        if dt:
            return f"{base} &middot; {dt.strftime('%H:%M')} UTC"
    return base


def _rfc822(item):
    dt = _parse_utc(item)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000") if dt else ""


# Source attribution: outlet names read better (and more honestly) than raw feed URLs.
OUTLETS = {
    "espn.com": "ESPN", "bbc.co.uk": "BBC Sport", "bbc.com": "BBC Sport",
    "cbssports.com": "CBS Sports", "theguardian.com": "The Guardian",
    "sports.yahoo.com": "Yahoo Sports",
    "statsapi.mlb.com": "MLB StatsAPI (official)",
    "api-web.nhle.com": "NHL API (official)",
    "site.api.espn.com": "ESPN Scoreboard",
    "thesportsdb.com": "TheSportsDB",
}


def source_label(src):
    """'ESPN: veteran shortstop traded at the deadline' instead of a raw URL
    with utm cruft. A real title (anything that isn't just the URL) is kept as-is."""
    from urllib.parse import urlparse
    url = src.get("url") or ""
    title = (src.get("title") or "").strip()
    if title and title != url:
        return title
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    outlet = OUTLETS.get(host, host)
    slug = [s for s in p.path.split("/") if s]
    hint = re.sub(r"[-_]+", " ", re.sub(r"\.\w+$", "", slug[-1])) if slug else ""
    hint = re.sub(r"\b\d{5,}\b", "", hint).strip()
    if len(hint) > 80:
        hint = hint[:80].rsplit(" ", 1)[0] + "..."
    if hint and not hint.isdigit():
        return f"{outlet}: {hint}"
    return outlet


# Topic tags: deterministic keyword rules over the story text, computed at build time so
# every story (old and new) gets them without touching the pipeline. Order = priority;
# a story keeps at most 3.
TAG_RULES = [
    ("injuries", r"\b(injur\w*|acl|mcl|achilles|hamstring|concussion\w*|surgery|"
                 r"injured (?:list|reserve)|day-to-day|week-to-week|out for the season|"
                 r"questionable|doubtful|sidelined)\b"),
    ("transactions", r"\b(trade[sd]?|traded|signing\w*|signed|waive[sd]?|waiver\w*|"
                     r"free agen\w*|contract\w*|extension\w*|transfer\w*|draft\w*|"
                     r"released|option\w* (?:exercised|declined)|call[- ]up)\b"),
    ("nfl", r"\b(nfl|super bowl|quarterback\w*|touchdown\w*|training camp)\b"),
    ("nba", r"\b(nba|wnba|finals mvp|triple-double)\b"),
    ("mlb", r"\b(mlb|world series|no-hitter|home run\w*|inning\w*|pitcher\w*)\b"),
    ("nhl", r"\b(nhl|stanley cup|hat trick|power play|goalie\w*|goaltender\w*)\b"),
    ("soccer", r"\b(premier league|champions league|la liga|serie a|bundesliga|mls|"
               r"fifa|uefa|world cup|soccer)\b"),
    ("college", r"\b(ncaa|college football|college basketball|march madness|"
                r"heisman|bowl game\w*|nil deal\w*)\b"),
    ("scores-results", r"\b(final score\w*|won|beat\w*|defeat\w*|shutout|overtime|"
                       r"walk-off|clinch\w*|elimination|playoff\w*|postseason)\b"),
]
_TAG_RES = [(tag, re.compile(pat, re.I)) for tag, pat in TAG_RULES]


def tags_for(item):
    body = item.get("body") or []
    text = " ".join([item.get("title") or "", item.get("dek") or "",
                     item.get("key_fact") or ""] +
                    [p if isinstance(p, str) else "" for p in body])
    return [tag for tag, rx in _TAG_RES if rx.search(text)][:3]


def related_stories(item, items, n=3):
    """Stories sharing a topic tag, newest first. Turns a one-story visit into a session."""
    mine = set(tags_for(item))
    if not mine:
        return []
    scored = []
    for other in items:
        if other is item or other.get("example") or other.get("slug") == item.get("slug"):
            continue
        shared = len(mine & set(tags_for(other)))
        if shared:
            scored.append((shared, other.get("date", ""), other))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [o for _, _, o in scored[:n]]


def render_feed(items):
    """RSS 2.0 feed of the published stories. The desk consumes RSS; now it emits it."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
           "<channel>",
           f"<title>{esc(NAME)} &#8212; {esc(FAMILY)}</title>",
           f"<link>{ORIGIN}/news.html</link>",
           f"<description>{esc(DESC)}</description>",
           "<language>en-us</language>",
           f'<atom:link href="{ORIGIN}/feed.xml" rel="self" type="application/rss+xml"/>']
    for it in [i for i in items if not i.get("example")][:30]:
        url = f"{ORIGIN}/articles/{it['slug']}.html"
        pd = _rfc822(it)
        cats = "".join(f"<category>{esc(t)}</category>" for t in tags_for(it))
        out += ["<item>",
                f"<title>{esc(it.get('title') or '')}</title>",
                f"<link>{url}</link>",
                f'<guid isPermaLink="true">{url}</guid>',
                (f"<pubDate>{pd}</pubDate>" if pd else ""),
                f"<description>{esc(it.get('dek') or '')}</description>",
                cats,
                "</item>"]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(x for x in out if x)


def destyle(text):
    """House style: no em/en dashes in site copy (model drafts sometimes use them)."""
    return (str(text or "").replace(" \u2014 ", ", ").replace("\u2014", ", ")
            .replace(" \u2013 ", ", ").replace("\u2013", "-"))


def load_content():
    items = []
    if os.path.isdir(CONTENT):
        for fn in sorted(os.listdir(CONTENT)):
            if fn.startswith("_") or not fn.endswith(".json"):
                continue
            c = json.load(open(os.path.join(CONTENT, fn), encoding="utf-8"))
            c.setdefault("slug", slugify(c.get("title", "")))
            items.append(c)
    # newest first by date then id
    # newest date first; within a date, the editor's rank (1 = lead); unranked (intro,
    # example) after the day's ranked stories
    items.sort(key=lambda c: (c.get("date", ""), -(c.get("rank") or 999), c.get("id", "")),
               reverse=True)
    return items


# ---- shared chrome -----------------------------------------------------------

def masthead(active, dateline, brand="site"):
    """One identity everywhere: GoCheckMySports is both the site and the desk. The brand
    parameter is kept for the shared call sites; every page renders the same masthead."""
    nav = "".join(
        f'<a href="{esc(href)}"{" class=active" if label == active else ""}>{esc(label)}</a>'
        for label, href in NAV)
    fam = f'<a class="mh-family" href="{FAMILY_HUB}">A GoCheckMy site</a>'
    brand_row = f"""<a class="mh-brand" href="/index.html" style="margin-top:8px">
    <img class="mh-mark" src="/assets/logo.svg" alt="">
    <span class="mh-word">{esc(NAME)}</span>
    <span class="mh-slogan">{esc(SLOGAN)}</span>
  </a>"""
    return f"""<div class="top-rule"></div>
<header class="masthead"><div class="wrap">
  <div class="mh-top">
    {fam}
    <span class="mh-dateline">{esc(dateline)} &middot; Independent &middot; No hype</span>
  </div>
  {brand_row}
</div></header>
<nav class="mh-nav"><div class="wrap">{nav}</div></nav>"""


def newsletter():
    return f"""<section class="news"><div class="wrap">
  <h2>Get the brief</h2>
  <p>The day's real sports news, fact-checked against official league data, with the honest
     take. No hot takes dressed as facts, no rumor mills. One email, on a cadence we can
     actually keep.</p>
  <form name="newsletter" method="POST" data-netlify="true" netlify-honeypot="company" action="/thanks.html">
    <input type="hidden" name="form-name" value="newsletter">
    <input class="hp" type="text" name="company" tabindex="-1" autocomplete="off" aria-hidden="true">
    <input type="email" name="email" placeholder="you@email.com" required aria-label="Email address">
    <button type="submit">Subscribe</button>
  </form>
  <p class="fine">Emails are stored by Netlify Forms and used only to send the newsletter.
     Unsubscribe anytime. See our <a href="/privacy.html">privacy policy</a>. Never betting advice.</p>
</div></section>"""


def trust_block():
    return f"""<section class="trust"><div class="wrap">
  <div class="sec-head"><h2>The desk's promise</h2><span class="bar"></span></div>
  <p class="trust-line">We aggregate stories from official league data and established
  outlets, audit every one for credibility, and surface only what genuinely matters, with
  the rumor and the hype stripped out. Sources are linked on every story, and nothing here
  is ever betting advice.</p>
</div></section>"""


def footer(brand="site"):
    """One identity everywhere; the brand parameter is kept for the shared call sites."""
    links = "".join(f'<a href="{esc(h)}">{esc(l)}</a>' for l, h in
                    [("About", "/about.html"), ("How we work", "/method.html"),
                     ("Standards & corrections", "/standards.html"), ("Archive", "/archive.html"),
                     ("Privacy", "/privacy.html"), ("Terms", "/terms.html"),
                     ("Contact", "mailto:desk@gocheckmysports.com"),
                     ("RSS", "/feed.xml")])
    who = f"{esc(NAME)}"
    note = ("GoCheckMySports is an independent daily sports news desk, built with one "
            "intention: get the stories right and keep the facts honest. The score is a "
            "fact; the story gets checked. Sources are linked on every story.")
    return f"""<footer class="site"><div class="wrap">
  <div class="frow">
    <div class="fbrand">{who}</div>
    <div class="flinks">{links}</div>
  </div>
  <p class="fnote"><b>{esc(NFA)}</b> {note}
    &copy; {YEAR} {who} &middot; <a href="{FAMILY_HUB}">A GoCheckMy site</a>.</p>
</div></footer>"""


_ASSET_VER = {}


def _fingerprint_assets(html):
    """Version every /assets/ URL with a content hash (site.css?v=ab12cd34ef). netlify.toml
    caches assets in the browser for 7 days; without this, a changed stylesheet leaves
    returning visitors on week-old CSS. The HTML itself always revalidates, so a new hash
    reaches every browser on the next page load."""
    import hashlib

    def ver(path):
        if path not in _ASSET_VER:
            f = os.path.join(HERE, "site", path.lstrip("/"))
            try:
                _ASSET_VER[path] = hashlib.md5(open(f, "rb").read()).hexdigest()[:10]
            except OSError:
                _ASSET_VER[path] = "0"
        return _ASSET_VER[path]

    return re.sub(r'((?:src|href)=")(/assets/[^"?#]+)(")',
                  lambda m: f'{m.group(1)}{m.group(2)}?v={ver(m.group(2))}{m.group(3)}', html)


# The motion layer's shared guard: reduced-motion strips every video to its poster and
# freezes the micro-details; otherwise videos play only while on screen and story cards
# fade up once. Inline (one request), transform/opacity only, no layout shift.
MOTION_JS = (
    '<script>(function(){var rm=matchMedia("(prefers-reduced-motion: reduce)").matches;'
    'var vids=[].slice.call(document.querySelectorAll(".motion-video"));'
    'if(rm){vids.forEach(function(v){v.parentNode.removeChild(v)});return;}'
    'document.documentElement.classList.add("mjs");'
    'if("IntersectionObserver" in window){'
    'var vo=new IntersectionObserver(function(es){es.forEach(function(e){var v=e.target;'
    'if(e.isIntersecting&&e.intersectionRatio>=.12){if(v.paused&&!v.dataset.userPaused)v.play().catch(function(){})}'
    'else if(!v.paused)v.pause()})},{threshold:.12});'
    '[].slice.call(document.querySelectorAll(".hero-pause")).forEach(function(b){'
    'var v=b.parentNode.querySelector(".motion-video");if(!v)return;b.hidden=false;'
    'var setP=function(p){if(p){v.dataset.userPaused="1";v.pause();'
    'b.setAttribute("aria-pressed","true");'
    'b.setAttribute("aria-label","Play background animation");b.innerHTML="&#9654;"}'
    'else{delete v.dataset.userPaused;v.play().catch(function(){});'
    'b.setAttribute("aria-pressed","false");'
    'b.setAttribute("aria-label","Pause background animation");b.innerHTML="&#10074;&#10074;"}'
    'try{sessionStorage.setItem("heroPaused",p?"1":"0")}catch(e){}};'
    'try{if(sessionStorage.getItem("heroPaused")==="1")setP(true)}catch(e){}'
    'b.addEventListener("click",function(){setP(!v.paused)})});'
    'vids.forEach(function(v){if(!v.classList.contains("motion-lazy"))vo.observe(v)});'
    'var lz=vids.filter(function(v){return v.classList.contains("motion-lazy")});'
    'if(lz.length){var arm=function(){lz.forEach(function(v){vo.observe(v)});'
    'removeEventListener("scroll",arm)};addEventListener("scroll",arm,{passive:true})}'
    'var ro=new IntersectionObserver(function(es){es.forEach(function(e){'
    'if(e.isIntersecting){e.target.classList.add("in");ro.unobserve(e.target)}})},'
    '{rootMargin:"0px 0px -5% 0px"});'
    '[].slice.call(document.querySelectorAll(".reveal")).forEach(function(el){ro.observe(el)})}'
    'else{[].slice.call(document.querySelectorAll(".reveal")).forEach(function(el){el.classList.add("in")})}'
    '})()</script>')


def shell(title, desc, active, body, dateline, body_class="", path="/", noindex=False,
          brand="site", og_type="website", schema_extra=""):
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=Mrs+Saint+Delafield&display=swap" rel="stylesheet">')
    url = ORIGIN + path
    site_name = NAME
    # Home only: the hero band's poster is the LCP element (the video is preload="none"
    # by design), so hint the browser to fetch it first.
    lcp = ('<link rel="preload" as="image" href="/assets/hero/hero-poster.webp" '
           'fetchpriority="high">\n' if path == "/" else "")
    robots = '<meta name="robots" content="noindex">\n' if noindex else f'<link rel="canonical" href="{esc(url)}">\n'
    robots = lcp + robots
    beacon = ""
    if CF_ANALYTICS_TOKEN:
        beacon = ('\n<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
                  f'data-cf-beacon=\'{{"token": "{CF_ANALYTICS_TOKEN}"}}\'></script>')
    # accessibility: id the page's first <main> landmark as the skip-link target, and emit
    # the skip-link ONLY when such a target exists (list pages built from bare <section>s
    # get no dangling link). The .skip-link CSS lives in site.css.
    skip = ""
    if re.search(r'<main(\s|>)', body):
        body = re.sub(r'<main(\s|>)', r'<main id="main"\1', body, count=1)
        skip = '<a class="skip-link" href="#main">Skip to main content</a>\n'
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{robots}<link rel="alternate" type="application/rss+xml" title="{esc(NAME)} feed" href="/feed.xml">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{esc(og_type)}">{schema_extra}
<meta property="og:url" content="{esc(url)}">
<meta property="og:site_name" content="{esc(site_name)}">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{OG_IMAGE}">
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{fonts}
<link rel="stylesheet" href="/assets/site.css">
</head>
<body class="{esc(body_class)}">
{skip}{masthead(active, dateline, brand)}
{body}
{footer(brand)}{beacon}
{MOTION_JS}
</body>
</html>"""
    return _fingerprint_assets(page)


# ---- article ----------------------------------------------------------------

def render_body(body):
    out = []
    for b in body or []:
        if isinstance(b, dict) and "h2" in b:
            out.append(f"<h2>{esc(b['h2'])}</h2>")
        else:
            out.append(f"<p>{esc(b)}</p>")
    return "\n".join(out)


def verdict_badge(verdict):
    if verdict == "VERIFIED":
        return '<span class="badge verified">Verified</span>'
    if verdict in ("NEEDS-HUMAN-REVIEW", "REVIEW"):
        return '<span class="badge review">Editor reviewed</span>'
    return ""


def sig_block():
    """The desk's closing mark: an HONEST machine attestation. No anchor persona, no human
    editor implied (compliance monitor class 4): the badge states exactly what happened,
    which is that the story passed the automated editorial review described on the method
    page."""
    return """<div class="sigrow">
  <div class="sig">
    <span class="sig-script">GoCheckMySports</span>
    <span class="sig-cap">The GoCheckMySports Desk &middot; automated newsroom</span>
    <span class="sig-attest">Passed our <a href="/method.html">automated editorial review</a>:
      ranked, source-checked, and verified by the desk's independent review pass.</span>
  </div>
  <div class="stamp" aria-label="Automated editorial review stamp">
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle cx="60" cy="60" r="56" fill="none" stroke="currentColor" stroke-width="2"/>
      <circle cx="60" cy="60" r="47" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="3 4"/>
      <defs><path id="stamparc" d="M60,60 m-51,0 a51,51 0 1,1 102,0 a51,51 0 1,1 -102,0"/></defs>
      <text font-size="9.4" letter-spacing="2.2" fill="currentColor"
        font-family="IBM Plex Mono,monospace" font-weight="600">
        <textPath href="#stamparc" startOffset="2%">AUTOMATED REVIEW</textPath>
        <textPath href="#stamparc" startOffset="55%">SOURCE CHECKED</textPath>
      </text>
    </svg>
  </div>
</div>"""


def share_row(url, title):
    """Share buttons for growing the audience: LinkedIn and X get the story with one click,
    copy-link covers everything else. Plain links, no tracking scripts."""
    u, t = quote(url, safe=""), quote(title, safe="")
    return f"""<div class="sharerow">
  <span class="share-lab">Share this story</span>
  <a class="share-btn" href="https://www.linkedin.com/sharing/share-offsite/?url={u}"
     target="_blank" rel="noopener">LinkedIn</a>
  <a class="share-btn" href="https://twitter.com/intent/tweet?text={t}&amp;url={u}"
     target="_blank" rel="noopener">X</a>
  <button class="share-btn" type="button" data-url="{esc(url)}">Copy link</button>
</div>
<script>
(function(){{
  var b=document.querySelector('.sharerow button');if(!b)return;
  b.addEventListener('click',function(){{
    var u=b.getAttribute('data-url');
    function ok(){{b.textContent='Copied';setTimeout(function(){{b.textContent='Copy link';}},1600);}}
    function fb(){{var t=document.createElement('textarea');t.value=u;t.style.position='fixed';t.style.opacity='0';
      document.body.appendChild(t);t.select();try{{document.execCommand('copy');ok();}}catch(e){{}}
      document.body.removeChild(t);}}
    if(navigator.clipboard&&window.isSecureContext){{navigator.clipboard.writeText(u).then(ok,fb);}}else{{fb();}}
  }});
}})();
</script>"""


def render_article(item, all_items=None):
    dateline = fmt_date(item.get("date"))
    badge = verdict_badge(item.get("verdict"))
    tag = f'<span class="tag">{esc(item.get("category","news"))}</span>' if item.get("category") else ""
    topic_chips = "".join(f'<span class="tag topic">{esc(t)}</span>' for t in tags_for(item))
    ribbon = ""
    if item.get("example"):
        ribbon = ('<div class="callout"><b>Example, not a real story.</b> This page shows the '
                  'format GoCheckMySports publishes in. The content is illustrative only.</div>')
    if item.get("update_of"):
        prev = next((i for i in (all_items or []) if i.get("slug") == item["update_of"]), None)
        prev_title = prev.get("title") if prev else "our earlier story"
        ribbon += (f'<div class="callout"><b>Update.</b> This story develops our earlier '
                   f'reporting: <a href="/articles/{esc(item["update_of"])}.html">'
                   f'{esc(prev_title)}</a>.</div>')
    key = ""
    if item.get("key_fact"):
        key = (f'<div class="keyfact"><span class="lab">The key fact</span>'
               f'<p>{esc(item["key_fact"])}</p></div>')
    bottom = ""
    if (item.get("bottom_line") or "").strip():
        bottom = (f'<div class="bottomline"><span class="lab">The Bottom Line</span>'
                  f'<p>{esc(item["bottom_line"])}</p></div>')
    take = ""
    if (item.get("human_take") or "").strip():
        take = (f'<div class="take"><span class="lab">The take</span>'
                f'<p>{esc(item["human_take"])}</p></div>')
    srcs = item.get("sources") or []
    src_html = ""
    if srcs:
        lis = "".join(
            f'<li><a href="{esc(s.get("url",""))}" rel="nofollow">{esc(source_label(s))}</a></li>'
            for s in srcs)
        src_html = f'<div class="sources"><h4>Sources</h4><ol>{lis}</ol></div>'
    rel_html = ""
    for rel in related_stories(item, all_items or []):
        rel_html += (f'<li><a href="/articles/{esc(rel["slug"])}.html">{esc(rel.get("title"))}</a>'
                     f'<span class="mut"> &middot; {fmt_when(rel)}</span></li>')
    if rel_html:
        rel_html = f'<div class="related"><h4>Related stories</h4><ul>{rel_html}</ul></div>'
    author = esc(item.get("author", "The GoCheckMySports Desk"))
    body = f"""<main class="wrap narrow">
  <article class="article">
    <div class="ey">{badge}{tag}{topic_chips}<span class="dateline">{fmt_when(item)}</span></div>
    <h1>{esc(item.get("title"))}</h1>
    {f'<p class="dek">{esc(item["dek"])}</p>' if item.get("dek") else ""}
    <div class="byline">By {author}</div>
    {ribbon}
    <div class="prose">{render_body(item.get("body"))}</div>
    {key}
    {take}
    {bottom}
    <p class="signoff">{esc(SLOGAN)}</p>
    {sig_block()}
    {share_row(ORIGIN + f"/articles/{item['slug']}.html", item.get("title") or "")}
    {src_html}
    {rel_html}
    <p class="nfa">{esc(NFA)}</p>
  </article>
</main>"""
    title = f'{item.get("title")} - {NAME}'
    desc = item.get("dek") or (item.get("body", [""])[0] if item.get("body") else DESC)
    url = f"{ORIGIN}/articles/{item['slug']}.html"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "NewsArticle", "headline": item.get("title"),
         "description": item.get("dek") or "", "url": url, "mainEntityOfPage": url,
         "image": OG_IMAGE,
         "datePublished": item.get("published_utc") or item.get("date"),
         "dateModified": item.get("published_utc") or item.get("date"),
         "author": {"@type": "Organization", "name": NAME, "url": ORIGIN + "/news.html"},
         "publisher": {"@type": "Organization", "name": FAMILY, "url": ORIGIN + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Latest", "item": ORIGIN + "/news.html"},
            {"@type": "ListItem", "position": 2, "name": item.get("title"), "item": url}]}
    ]}, ensure_ascii=False)
    return shell(title, desc if isinstance(desc, str) else DESC, "Latest", body, dateline.upper(),
                 path=f"/articles/{item['slug']}.html", noindex=bool(item.get("example")),
                 og_type="article",
                 schema_extra=f'\n<script type="application/ld+json">{schema}</script>')


# ---- cards / index / archive -------------------------------------------------

def card(item):
    badge = verdict_badge(item.get("verdict"))
    tag = f'<span class="tag">{esc(item.get("category","news"))}</span>' if item.get("category") else ""
    tag += "".join(f'<span class="tag topic">{esc(t)}</span>' for t in tags_for(item)[:2])
    href = f'/articles/{esc(item["slug"])}.html'
    summ = item.get("dek") or (item.get("body", [""])[0] if item.get("body") else "")
    if isinstance(summ, dict):
        summ = summ.get("h2", "")
    nsrc = len(item.get("sources") or [])
    return f"""<article class="card reveal">
  <div class="row">{badge}{tag}</div>
  <h3><a href="{href}">{esc(item.get("title"))}</a></h3>
  <p class="summary">{esc(summ[:180])}</p>
  <div class="foot"><span class="dateline">{fmt_when(item)}</span>
    <span class="src">{nsrc} source{"s" if nsrc != 1 else ""}</span></div>
</article>"""


def desk_strip():
    # Desk strip: the desk line beneath the masthead, text only (the chassis this repo was
    # cloned from put an anchor-portrait video here; sports runs a single brand, no mascot).
    return f"""<section class="desk"><div class="wrap">
  <div class="desk-copy">
    <span class="kicker">From the desk</span>
    <p>{esc(DESK_LINE)}</p>
  </div>
</div></section>"""


def _blink_when(item):
    """Edition timestamp with a clock-style blinking colon (CSS animates .tick-colon)."""
    t = fmt_when(item)
    if ":" in t:
        head, rest = t.split(":", 1)
        return f'{head}<span class="tick-colon">:</span>{rest}'
    return t


def _is_wrap(item):
    return str(item.get("id", "")).startswith("wrap-")


# ---- daypart stacking (owner directive 2026-07-20) --------------------------------
# The front page re-stacks like a broadcast rundown. The build clock decides stacking
# and badge decay ONLY; datelines stay content-derived (the house rule is untouched).
# SITE_BUILD_NOW pins the clock for deterministic replays and the canary.

BREAKING_HOURS = 3
_DAYPART_WRAP = {"morning": "wrap-am-", "midday": "wrap-md-", "evening": "wrap-pm-"}
_NOW_CACHE = None


def _build_now():
    global _NOW_CACHE
    if _NOW_CACHE is None:
        env = os.environ.get("SITE_BUILD_NOW", "")
        try:
            _NOW_CACHE = datetime.datetime.fromisoformat(env.replace("Z", "+00:00"))
        except ValueError:
            _NOW_CACHE = datetime.datetime.now(datetime.timezone.utc)
    return _NOW_CACHE


def _daypart(now):
    return "morning" if now.hour < 14 else "midday" if now.hour < 20 else "evening"


def _fresh_hours(item, now):
    try:
        ts = (item.get("published_utc") or "").replace("Z", "+00:00")
        return (now - datetime.datetime.fromisoformat(ts)).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return 1e9


def home_stack(items, now=None):
    """One deterministic rule for the hero lead and The Bottom Line anchor, shared by
    render_home and bottom_line_card so the front page and /news never disagree.
      1. A story under BREAKING_HOURS old takes the lead with the Breaking badge (a
         breaking publish triggers its own build; the next slot or refresh build
         retires the badge).
      2. The Bottom Line anchors today's edition matching the build daypart.
      3. Otherwise the editor's rank of the newest date leads (unchanged behavior).
      4. No matching edition -> the newest edition, exactly as before. Cron drift's
         worst case is the status quo; nothing ever renders empty."""
    now = now or _build_now()
    stories = [i for i in (items or []) if not i.get("example") and not _is_wrap(i)]
    breaking = False
    if stories:
        freshest = min(stories, key=lambda i: _fresh_hours(i, now))
        if _fresh_hours(freshest, now) <= BREAKING_HOURS:
            breaking = True
            stories = [freshest] + [s for s in stories if s is not freshest]
    wraps = [i for i in (items or [])
             if _is_wrap(i) and i.get("bottom_line") and not i.get("example")]
    prefix = _DAYPART_WRAP[_daypart(now)]
    today = now.strftime("%Y-%m-%d")
    anchor = next((w for w in wraps
                   if str(w.get("id", "")).startswith(prefix) and w.get("date") == today),
                  None)
    if anchor is None:
        anchor = wraps[0] if wraps else None
    return stories, breaking, anchor


# ---- the live layer (owner directive 2026-07-20) ----------------------------------

SCORES_PATH = os.path.join(HERE, "site", "data", "scores.json")
_CLIENT_FEEDS = {
    "MLB": "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=team,linescore",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
}

SCORES_JS = (
    '<script>(function(){var s=document.getElementById("scores-strip");'
    'if(!s||!window.fetch)return;var urls=[];'
    'try{urls=JSON.parse(s.getAttribute("data-feeds")||"[]")}catch(e){return}'
    'var last=0;'
    'function apply(eid,as,hs,det,state){'
    'var g=s.querySelector(\'[data-eid="\'+eid+\'"]\');'
    'if(!g||as==null||hs==null||state==="pre")return;'
    'var rows=g.querySelectorAll(".sb-row"),st=g.querySelector(".sb-status");'
    'if(rows.length<2)return;'
    'rows[0].querySelector(".sb-score").textContent=as;'
    'rows[1].querySelector(".sb-score").textContent=hs;'
    'if(det&&st)st.textContent=det;'
    'g.classList.toggle("live",state==="in");'
    'if(state==="post"){var a=+as,h=+hs;'
    'rows[0].classList.toggle("win",a>h);rows[1].classList.toggle("win",h>a)}}'
    'function refresh(){var n=Date.now();if(n-last<120000)return;last=n;'
    'urls.forEach(function(u){fetch(u).then(function(r){return r.json()})'
    '.then(function(d){if(d&&d.events){d.events.forEach(function(ev){'
    'var c=(ev.competitions||[{}])[0],sides={};'
    '(c.competitors||[]).forEach(function(x){sides[x.homeAway]=x});'
    'var st=(ev.status||{}).type||{};'
    'apply(String(ev.id),(sides.away||{}).score,(sides.home||{}).score,'
    'st.state==="post"?"Final":(st.state==="in"?(st.shortDetail||"Live"):null),st.state)})}'
    'else if(d&&d.dates){d.dates.forEach(function(day){(day.games||[]).forEach(function(g){'
    'var t=g.teams||{},ls=g.linescore||{},ab=(g.status||{}).abstractGameState,'
    'state=ab==="Live"?"in":ab==="Final"?"post":"pre",'
    'det=state==="post"?"Final":state==="in"?((ls.isTopInning?"Top ":"Bot ")+'
    '(ls.currentInning||"")):null;'
    'apply(String(g.gamePk),(t.away||{}).score,(t.home||{}).score,det,state)})})}'
    '}).catch(function(){})})}'
    'refresh();document.addEventListener("visibilitychange",function(){'
    'if(document.visibilityState==="visible")refresh()})})()</script>')


def scores_strip():
    """The live layer, scoreboard edition (owner call 2026-07-21: game cards, not a
    stock-style ticker). Baked from site/data/scores.json (scores_pulse.py; fail-open).
    League data, not news: it never passes the editorial pipeline and says so. Empty or
    missing snapshot = no bar, no dead chrome. One client fetch on load (CORS verified
    on both feeds) updates the cards in place; baked values stand on any failure.
    Nothing self-moves, so WCAG 2.2.2 never triggers; the rail is keyboard-scrollable."""
    try:
        snap = json.load(open(SCORES_PATH, encoding="utf-8"))
    except Exception:
        return ""
    leagues = [l for l in snap.get("leagues", []) if l.get("games")]
    if not leagues:
        return ""
    cards, feeds = [], []
    many = len(leagues) > 1
    for l in leagues:
        feed = _CLIENT_FEEDS.get(l.get("league", ""))
        if feed:
            feeds.append(feed)
        if many:
            cards.append(f'<span class="sb-league">{esc(l.get("league", ""))}</span>')
        for g in l["games"]:
            aw, hm = esc(g.get("away", "")), esc(g.get("home", ""))
            a_s, h_s = g.get("away_score"), g.get("home_score")
            state = g.get("state", "pre")
            pre = state == "pre" or a_s is None or h_s is None
            a_txt = "" if pre else str(a_s)
            h_txt = "" if pre else str(h_s)
            a_win = h_win = ""
            if state == "post" and not pre:
                a_win = " win" if a_s > h_s else ""
                h_win = " win" if h_s > a_s else ""
            live_cls = " live" if state == "in" else ""
            cards.append(
                f'<span class="sb-game{live_cls}" data-eid="{esc(str(g.get("eid", "")))}">'
                f'<span class="sb-row{a_win}"><span class="sb-team">{aw}</span>'
                f'<span class="sb-score">{a_txt}</span></span>'
                f'<span class="sb-row{h_win}"><span class="sb-team">{hm}</span>'
                f'<span class="sb-score">{h_txt}</span></span>'
                f'<span class="sb-status">{esc(str(g.get("detail", "")))}</span></span>')
    stamp = esc((snap.get("generated_utc") or "")[11:16])
    return (f'<section class="scorebar" aria-label="Today\'s scores">'
            f'<div class="wrap"><span class="sb-lab">Scores</span>'
            f'<div class="sb-rail" tabindex="0" role="group" '
            f'aria-label="Scores, scroll horizontally" id="scores-strip" '
            f"data-feeds='{json.dumps(feeds)}'>"
            f'{"".join(cards)}</div>'
            f'<span class="sb-note">League data, not news &middot; as of {stamp} UTC'
            f'</span></div></section>') + SCORES_JS


def bottom_line_card(items):
    """THE BOTTOM LINE (owner directive 2026-07-15): the desk's signature element, the
    newest edition's 3-5 sentence read, refreshed every slot (and by breaking runs).
    Rendered as the compact card that rides beside the lead story (owner directive
    2026-07-17: lead first, Bottom Line to its right, same arrangement as the front
    page), reusing the home hero's card styling."""
    _, _, ed = home_stack(items)  # daypart anchor; falls back to newest edition
    if ed is None:
        return ""
    name = esc((ed.get("title") or "").split(":")[0].strip() or "The Daily Edition")
    return (f'<a class="hero-bl news-bl" href="/articles/{esc(ed["slug"])}.html">'
            f'<span class="hero-kick"><span class="kicker">The Bottom Line</span></span>'
            f'<span class="hero-bl-src">{name} &middot; {_blink_when(ed)}</span>'
            f'<span class="hero-bl-read">{esc(ed["bottom_line"])}</span>'
            f'<span class="hero-bl-more">Read the full edition &rarr;</span></a>')


def render_bottom_line_history(items, dateline):
    """/bottom-line.html: the browsable history of the daily reads, one entry per
    edition, newest first. Each edition's read is preserved with its edition forever."""
    wraps = [i for i in items if _is_wrap(i) and i.get("bottom_line") and not i.get("example")]
    rows = []
    for ed in wraps:
        name = esc((ed.get("title") or "").split(":")[0].strip())
        rows.append(f"""<div class="bl-hist">
      <div class="bl-head"><span class="bl-label">{name}</span>
        <span class="dateline">{fmt_when(ed)}</span></div>
      <p class="bl-read">{esc(ed["bottom_line"])}</p>
      <p style="margin:6px 0 0"><a href="/articles/{esc(ed['slug'])}.html">The full edition &rarr;</a></p>
    </div>""")
    body = f"""<main class="wrap narrow"><section class="page">
  <span class="kicker">The Bottom Line</span>
  <h1>The daily reads</h1>
  <p class="lede">Three times a day the desk closes its edition with The Bottom Line: what
     happened, why it mattered, and what the calendar says comes next. Synthesis of the
     desk's verified reporting, never a prediction and never advice. Every read is kept.</p>
  {"".join(rows) if rows else '<p class="lede">The first edition lands soon.</p>'}
  <p class="nfa">{esc(NFA)}</p>
</section></main>"""
    return shell(f"The Bottom Line - {NAME}", "The desk's daily reads: what happened, why it "
                 "mattered, and what comes next. Synthesis, never advice.",
                 "The Bottom Line", body, dateline, path="/bottom-line.html")


def render_news(items, dateline):
    live = [i for i in items if not i.get("example")]
    bl = bottom_line_card(live)
    live = [i for i in live if not _is_wrap(i)]  # editions speak through the Bottom Line card
    if live:
        lead = live[0]
        rest = live[1:]
        badge = verdict_badge(lead.get("verdict"))
        lead_tags = tags_for(lead)
        tag = (f'<span class="tag topic">{esc(lead_tags[0])}</span>' if lead_tags
               else f'<span class="tag">{esc(lead.get("category", "news"))}</span>')
        lead_inner = f"""<span class="kicker">Lead story</span> {tag}
    <h1><a href="/articles/{esc(lead["slug"])}.html" style="color:inherit">{esc(lead.get("title"))}</a></h1>
    {f'<p class="dek">{esc(lead["dek"])}</p>' if lead.get("dek") else ""}
    <div class="meta">{badge}<span class="dateline">{fmt_when(lead)}</span>
      <a href="/articles/{esc(lead["slug"])}.html">Read the story &rarr;</a></div>"""
        # Lead first, The Bottom Line beside it (front-page arrangement); without an
        # edition the lead simply spans the row.
        lead_html = (f"""<section class="lead"><div class="wrap"><div class="news-grid">
    <div class="news-lead">{lead_inner}</div>
    {bl}
  </div></div></section>""" if bl else f"""<section class="lead"><div class="wrap">
    {lead_inner}
  </div></section>""")
        grid = ""
        if rest:
            grid = (f'<section class="sec"><div class="wrap"><div class="sec-head" id="latest">'
                    f'<h2>More from the desk</h2><span class="bar"></span></div>'
                    f'<div class="grid">{"".join(card(i) for i in rest)}</div></div></section>')
    else:
        lead_html = f"""<section class="lead"><div class="wrap">
    <span class="kicker">The desk is live</span>
    <h1>Honest sports news, on a cadence we can keep.</h1>
    <p class="dek">{esc(DESK_LINE)} The first published brief lands here. In the meantime, read how
       the desk works and why you can trust the byline.</p>
    <div class="meta"><a href="/method.html">How we work &rarr;</a>
      <a href="/about.html">Why this exists &rarr;</a></div>
  </div></section>"""
        grid = ('<section class="sec"><div class="wrap"><div class="empty">'
                '<span class="k">No brief published yet</span>'
                '<p style="margin:.6em 0 0">Every story here will have been ranked by an AI editor, '
                'checked against its sources by an independent AI verifier, and approved by a human. '
                'That gate is the whole point, so we would rather publish nothing than publish junk.</p>'
                '</div></div></section>')
    # news first: lead story (Bottom Line beside it), then the rest of the day's stories;
    # the promise strip and the newsletter read as the footer beats, never above the
    # journalism; the desk strip is secondary chrome; the news itself is the main landmark
    body = (desk_strip() + '<main class="news-main">' + lead_html + grid
            + trust_block() + newsletter() + '</main>')
    return shell(f"Latest news - {NAME}", DESC, "Latest", body, dateline, path="/news.html")


def render_home(items, dateline):
    """The GoCheckMySports front door, built for the RETURNING reader: today's headlines,
    the editions, and the storylines the desk is tracking. The brand pitch lives below the
    information, not above it."""
    live = [i for i in (items or []) if not i.get("example") and not _is_wrap(i)]

    # The front page (owner directive 2026-07-16): a network-style hero mosaic. Several
    # lead stories visible at once with explicit hierarchy (the editor's rank orders them),
    # editions in their own strip below. No carousel: every ranked story is on screen.
    # Daypart re-stack (2026-07-20): home_stack may promote a breaking story to the lead
    # and picks the edition that anchors The Bottom Line square.
    stories, breaking, bl_anchor = home_stack(items)

    def _hero_tag(item):
        tags = tags_for(item)
        return f'<span class="tag topic">{esc(tags[0])}</span>' if tags else ""

    desk_html = ""
    if stories:
        lead = stories[0]
        dek_html = f'<p class="hero-dek">{esc(lead["dek"])}</p>' if lead.get("dek") else ""
        # The desk set: an ambient video loop behind the lead card. It is scenery for
        # WHATEVER story leads, never an illustration of it (no caption, no linkage), and
        # the scrim guarantees the headline always beats the motion. Reduced-motion
        # readers get the poster still only (script below removes the video pre-load).
        hero_video = (
            '<video class="hero-video motion-video" autoplay muted loop playsinline preload="none" '
            'poster="/assets/hero/hero-poster.jpg" aria-hidden="true" tabindex="-1">'
            '<source src="/assets/hero/hero-loop.webm" type="video/webm">'
            '<source src="/assets/hero/hero-loop.mp4" type="video/mp4"></video>'
            '<span class="hero-scrim" aria-hidden="true"></span>'
            '<button class="hero-pause" type="button" hidden aria-pressed="false" '
            'aria-label="Pause background animation">&#10074;&#10074;</button>')
        lead_mark = ('<span class="badge breaking">Breaking</span>' if breaking
                     else _hero_tag(lead))
        lead_html = (f'<a class="hero-lead" href="/articles/{esc(lead["slug"])}.html">'
                     f'<span class="hero-kick"><span class="kicker">Lead story</span>{lead_mark}</span>'
                     f'<h3>{esc(lead.get("title"))}</h3>{dek_html}'
                     f'<span class="hl-meta">{verdict_badge(lead.get("verdict"))}'
                     f'<span class="dateline">{fmt_when(lead)}</span></span></a>')
        # The Bottom Line rides shotgun: the day's summary as the hero square beside the
        # lead, replacing the standalone band lower on the page.
        bl_card = ""
        if bl_anchor is not None:
            ed = bl_anchor
            ed_name = esc((ed.get("title") or "").split(":")[0].strip() or "The Daily Edition")
            bl_card = (f'<a class="hero-bl" href="/articles/{esc(ed["slug"])}.html">'
                       f'<span class="hero-kick"><span class="kicker">The Bottom Line</span></span>'
                       f'<span class="hero-bl-src">{ed_name} &middot; {_blink_when(ed)}</span>'
                       f'<span class="hero-bl-read">{esc(ed["bottom_line"])}</span>'
                       f'<span class="hero-bl-more">Read the full edition &rarr;</span></a>')
        more = "".join(
            f'<a class="hero-item" href="/articles/{esc(i["slug"])}.html">'
            f'<span class="hero-num">{n:02d}</span><span class="hero-body">'
            f'<span class="hero-kick">{_hero_tag(i)}</span>'
            f'<span class="hl-title">{esc(i.get("title"))}</span>'
            f'<span class="dateline">{fmt_when(i)}</span></span></a>'
            for n, i in enumerate(stories[1:6], start=2))
        more += ('<a class="hero-item more" href="/news.html">'
                 '<span class="hero-body"><span class="hl-title">All stories &rarr;</span></span></a>')
        desk_html = f"""<div class="sec-head"><h2>Today at the desk</h2><span class="bar"></span></div>
  <div class="hero-band">{hero_video}<div class="hero-band-inner">
    <div class="hero-grid">{lead_html}{bl_card}</div>
    <div class="hero-more-lab">More from the desk</div>
    <div class="hero-more">{more}</div>
  </div></div>"""

    # The Editions: the desk's daily synthesis as its own strip, one card per slot
    # (morning / midday / evening), newest first, never older than the current news cycle.
    wraps = [i for i in items if _is_wrap(i) and not i.get("example")]
    ed_cards, seen_slots = [], set()
    if wraps:
        recent = sorted({w.get("date", "") for w in wraps}, reverse=True)[:2]
        for w in wraps:
            if len(ed_cards) >= 3:
                break
            if (w.get("date") or "") not in recent:
                continue
            title = w.get("title") or ""
            kick, _, hook = title.partition(":")
            if not hook:
                kick, hook = "The Daily Edition", title
            if kick in seen_slots:
                continue
            seen_slots.add(kick)
            fact = w.get("key_fact") or w.get("dek") or ""
            dot = '<span class="live-dot"></span>' if not ed_cards else ''
            ed_cards.append(
                f'<a class="edition-card reveal" href="/articles/{esc(w["slug"])}.html">'
                f'<span class="ed-kick">{esc(kick)}{dot}</span>'
                f'<span class="ed-title">{esc(hook.strip())}</span>'
                f'<span class="ed-fact">{esc(fact)}</span>'
                f'<span class="dateline">{_blink_when(w)}</span></a>')
    editions_html = ""
    if ed_cards:
        editions_html = (f'<div class="sec-head" style="margin-top:26px"><h2>The Editions</h2>'
                         f'<span class="bar"></span></div>'
                         f'<p class="pc-note" style="margin:0 0 10px">The desk\'s daily synthesis: '
                         f'morning, midday, and evening reads over everything published.</p>'
                         f'<div class="edition-strip">{"".join(ed_cards)}</div>')

    # Tracking: the narratives watchlist, each chip linking to its latest published chapter.
    track_html = ""
    chips = []
    try:
        watch = json.load(open(os.path.join(HERE, "config.json"),
                               encoding="utf-8")).get("narratives", {}).get("watchlist", [])
    except Exception:
        watch = []
    for n in watch:
        kws = n.get("keywords") or []
        if not kws:
            continue
        rx = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b", re.I)
        hit = next((i for i in live if rx.search(" ".join(
            [i.get("title") or "", i.get("dek") or "", i.get("key_fact") or ""] +
            [p for p in (i.get("body") or []) if isinstance(p, str)]))), None)
        if hit:
            chips.append(f'<a class="chip" href="/articles/{esc(hit["slug"])}.html">'
                         f'{esc(n.get("name", ""))}</a>')
    if chips:
        track_html = (f'<div class="tracking"><span class="lab">Tracking</span>{"".join(chips)}'
                      f'<span class="mut">the storylines the desk is following</span></div>')

    # The Bottom Line lives in the hero square beside the lead (owner call 2026-07-16);
    # the standalone band below is retired on home. /bottom-line.html keeps the history.
    # The live layer rides above the fold, before the editorial page begins.
    body = scores_strip() + f"""<main class="wrap"><section class="page">
  {desk_html}
  {editions_html}
  {track_html}
  <p class="lede home-lede" style="margin-top:22px">Built with one intention: get the stories
     right and keep the facts honest. The score is a fact; the story gets checked. Real sports
     news verified against official league data and on-record sources, with the rumor and the
     hype stripped out. No hot takes dressed as facts, no paid promotion, and never betting
     advice. Everything here is free, and every source is linked.</p>
</section></main>""" + newsletter()
    return shell(f"{FAMILY} - Sports, checked.", FAMILY_DESC, "Home", body, dateline, path="/")


def render_archive(items, dateline):
    live = [i for i in items if not i.get("example")]
    if live:
        # group by day, newest first (items are already sorted): a researcher scans by date
        days = []
        for i in live:
            if not days or days[-1][0] != i.get("date"):
                days.append((i.get("date"), []))
            days[-1][1].append(i)
        inner = "".join(
            f'<div class="sec-head" style="margin-top:22px"><h2>{esc(fmt_date(d))}</h2>'
            f'<span class="bar"></span></div><div class="grid">'
            + "".join(card(i) for i in group) + "</div>"
            for d, group in days)
    else:
        inner = ('<div class="empty"><span class="k">Archive is empty</span>'
                 '<p style="margin:.6em 0 0">No stories have been approved and published yet.</p></div>')
    body = f"""<main class="wrap"><section class="sec">
    <div class="sec-head"><h2>Archive</h2><span class="bar"></span></div>
    {inner}
  </section></main>"""
    return shell(f"Archive - {NAME}", "Every published GoCheckMySports story.", "Archive", body,
                 dateline, path="/archive.html")


# ---- static editorial pages --------------------------------------------------

def render_method(items, dateline):
    example = next((i for i in items if i.get("example")), None)
    ex_html = ""
    if example:
        ex_html = (f'<h2>What a finished story looks like</h2>'
                   f'<p>Here is the format, using an illustrative example (not a real story):</p>'
                   f'<div style="margin:18px 0">{card(example)}</div>'
                   f'<p><a href="/articles/{esc(example["slug"])}.html">Open the example story &rarr;</a></p>')
    body = f"""<main class="wrap narrow"><section class="page">
  <span class="kicker">Method</span>
  <h1>How a story gets to you</h1>
  <p class="lede">Automation removes the grind. It does not remove the judgment. Here is exactly
     what happens between a raw feed and a published story, and where the human sits.</p>

  <h2>1. Aggregate the day</h2>
  <p>On a schedule, the desk pulls sports news from many sources at once: official league data
     first (league APIs, official schedules and results, on-record club statements), then
     established outlets. The same event reported by ten outlets is collapsed into one story so
     nothing is double-counted, and a deterministic first pass flags the obvious hype and
     promotion tells before any AI sees it.</p>

  <h2>2. An AI managing editor ranks and strips the hype</h2>
  <p>An AI editor ranks the real news by genuine sporting significance, and strips the junk:
     unsourced rumor dressed as reporting, betting-pick content, affiliate listicles, and
     press releases dressed as news. It shows its work, listing why each story made the cut and
     why others were cut, so the human can audit the call.</p>

  <h2>3. A separate AI verifies the editor</h2>
  <p>A second, independent AI, with an adversarial prompt, audits those picks before anything is
     drafted. It fetches each cited source and checks whether the source actually says what the
     story claims. It flags anything single-source, unconfirmed, or implausible, and stamps each
     story VERIFIED, needs-human-review, or rejected. The builder never verifies its own work, so
     the editor and the verifier are deliberately two different passes. When they disagree, that
     disagreement is surfaced to the human as a signal.</p>

  <h2>4. The gate: the verifier's verdict, with a human editor-in-chief above it</h2>
  <p>A story publishes only when the independent verifier stamps it VERIFIED against its
     sources. Anything the verifier flags for review waits in the queue for the human
     editor-in-chief, who reads it, overrides the machine where judgment differs, kills
     stories, and decides what runs. Anything rejected never publishes. The human also owns
     everything the machine may not touch: the takes and analysis (the AI never writes an
     opinion in a human's voice), the corrections, and the standing rules every story is
     held to. The gate is the verification, and the human can overrule it in either
     direction at any time.</p>

  <div class="callout"><b>Why two AIs, not one.</b> A single model asked to both rank and
    self-check tends to rubber-stamp its own work. An independent pass, told to find what is wrong,
    catches what the first pass missed. It is the same discipline a real newsroom uses: the reporter
    does not fact-check their own copy.</div>

  {ex_html}

  <h2>What we will not do</h2>
  <ul>
    <li>We will not publish anything unverified. If a stage fails, we publish nothing.</li>
    <li>We will not advise bets. We report events and explain what they may mean, never what
        to wager on.</li>
    <li>We will not report an injury from anything but an official report or an on-record
        statement. Speculation about an athlete's body is not news.</li>
    <li>We will not run paid coverage as news. Sponsored items are the thing we are built to
        strip out.</li>
    <li>We will not let the machine speak in a human voice. Takes, analysis, and corrections
        are human work, always.</li>
  </ul>
  <p class="nfa">{esc(NFA)}</p>
</section></main>"""
    return shell(f"How we work - {NAME}", "How GoCheckMySports ranks, verifies, and approves every story.",
                 "How we work", body, dateline, path="/method.html")


def render_about(dateline):
    body = f"""<main class="wrap narrow"><section class="page">
  <span class="kicker">About</span>
  <h1>Why GoCheckMySports exists</h1>
  <p class="lede">Sports media is drowning in hot takes, rumor mills, and betting-pick content.
     The scarce thing is a desk that checks the story. That is the entire product.</p>

  <p>Too much sports "news" is noise wearing a press badge: trade rumors sourced to nobody,
     aggregation of aggregation until the original quote is unrecognizable, injury speculation
     with nothing behind it, and picks columns that are gambling ads in disguise. It is
     exhausting, and it is how readers get misled.</p>

  <p>GoCheckMySports is built on one idea: the score is a fact, and the story gets checked. We
     report what actually happened, verify every claim against official league data and
     on-record sources before it runs, and never tell you what to bet on. Injuries are reported
     only from official reports and on-record statements, never from speculation.</p>

  <h2>The machine does the grind. A human owns the judgment.</h2>
  <p>An AI newsroom does the reading, the triage, the fact-checking, and the first draft, every day,
     without getting tired. But the machine is the staff, not the editor. A story runs only when an
     independent verification pass confirms it against its sources; anything flagged waits for the
     human editor-in-chief, who oversees the desk, overrides the machine where judgment differs, and
     owns every take: no opinion ever goes out in a human voice unless a human wrote it. If that
     standard ever slips, we drop the cadence before we drop the standard.</p>

  <h2>Our bias</h2>
  <p>We are biased toward the reader and against the rumor mill. We weight official league data
     and on-record sources most, we link every source, and we would rather publish nothing on a
     given day than publish something we cannot stand behind.</p>

  <h2>What we are not</h2>
  <p>We are not a sportsbook, a tout service, or a picks column, and nothing here is betting or
     gambling advice. We report what happened and, carefully, what it may mean. What you do with
     that is yours.</p>

  <h2>Contact the desk</h2>
  <p>Tips, corrections, and questions: <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a>.</p>
  <p>Sponsorship inquiries: <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a>.
     Sponsorship never buys coverage; see <a href="/method.html">how we work</a>.</p>

  <div class="callout"><b>Read next:</b> <a href="/method.html">How a story gets to you</a>, the
    step-by-step of how we rank, verify, and approve. Or <a href="/standards.html">our standards and
    corrections policy</a>.</div>
  <p class="nfa">{esc(NFA)}</p>
</section></main>"""
    return shell(f"About - {NAME}", "Why GoCheckMySports exists: an honest daily sports news desk "
                 "that checks every story against its sources.",
                 "About", body, dateline, path="/about.html")


def render_standards(dateline):
    body = f"""<main class="wrap narrow"><section class="page">
  <span class="kicker">Standards</span>
  <h1>Standards and corrections</h1>
  <p class="lede">What you can hold us to.</p>

  <h2>Sourcing</h2>
  <p>Every story links its sources. We weight official league data and primary sources (league
     APIs, official schedules and results, on-record statements from clubs, leagues, and
     athletes) most heavily. A claim carried by a single low-credibility source is marked as
     unverified or is not published. Injuries are reported only from official injury reports or
     on-record statements, never from speculation.</p>

  <h2>Verification</h2>
  <p>Before a story is drafted, an independent verification pass checks each claim against its cited
     source. Stories that cannot be verified are either marked clearly for the reader or held back.
     We would rather be slow than wrong.</p>

  <h2>The gate</h2>
  <p>A story publishes only when an independent verification pass confirms it against its
     sources: VERIFIED runs, flagged-for-review waits for the human editor-in-chief, rejected
     never runs. The human editor oversees the desk, can overrule any machine call in either
     direction, and owns every opinion or analysis in the byline. The AI never writes a
     "take" in a human's voice.</p>

  <h2>Never betting advice</h2>
  <p>We report events and explain what they may mean. We never advise bets, picks, or wagers of
     any kind. Nothing on this site is betting, gambling, financial, or legal advice.</p>

  <h2>Corrections</h2>
  <p>When we get something wrong, we fix it and say so on the story. If you spot an error, tell us and
     we will check it against the source. A correction is a feature of an honest desk, not a failure.</p>

  <h2>AI disclosure</h2>
  <p>Stories on this site are assembled with AI assistance and fact-checked by a separate,
     independent AI verification pass; only stories that pass publish, under a human
     editor-in-chief who oversees the desk, reviews anything flagged, and can overrule any
     call. Takes and corrections are always human. We think transparency about that process
     is part of being trustworthy, which is why this page exists.</p>
  <p class="nfa">{esc(NFA)}</p>
</section></main>"""
    return shell(f"Standards - {NAME}", "GoCheckMySports standards, verification, and corrections policy.",
                 "Standards", body, dateline, path="/standards.html")


def render_privacy(dateline):
    body = f"""<main class="wrap narrow"><section class="page">
  <span class="kicker">Privacy</span>
  <h1>Privacy policy</h1>
  <p class="lede">What this site actually collects, which is very little, and where the little
     goes. No accounts, no ads, no cookies set by us.</p>

  <h2>The newsletter</h2>
  <p>If you sign up for the daily brief, the email address you submit is stored by Netlify Forms,
     the form service of our hosting provider. We use it only to send the newsletter. We do not
     sell your email address, and we do not share it with anyone else. Every issue includes an
     unsubscribe option, and unsubscribing removes you from the list.</p>

  <h2>Analytics</h2>
  <p>We measure traffic with Cloudflare Web Analytics. It is a cookieless beacon: it counts page
     views and referrers in aggregate and does not build profiles or track you across other
     sites. Cloudflare processes those requests under its own privacy policy.</p>

  <h2>Hosting and server logs</h2>
  <p>The site is served by Netlify. Like any web host, Netlify's infrastructure sees standard
     request data (your IP address and browser user agent) and keeps its own server logs under
     its own privacy policy. We do not receive or store that data ourselves.</p>

  <h2>Fonts</h2>
  <p>Pages load their typefaces from Google Fonts (fonts.googleapis.com and fonts.gstatic.com),
     so your browser makes a request to Google when a page loads. Google processes font requests
     under its own privacy policy.</p>

  <h2>Links out</h2>
  <p>Every story links its sources. Once you leave this site, the site you land on operates
     under its own privacy policy.</p>

  <h2>Contact</h2>
  <p>Questions about this policy, your data, or the newsletter, including unsubscribe requests:
     <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a>. A human reads it.</p>

  <h2>Changes</h2>
  <p>This policy changes only when the site's behavior changes, and the date below moves when it
     does. Last updated July 19, 2026.</p>
</section></main>"""
    return shell(f"Privacy - {NAME}",
                 "What GoCheckMySports collects and where it goes: newsletter emails via Netlify Forms, "
                 "cookieless Cloudflare analytics, and nothing else.",
                 "Privacy", body, dateline, path="/privacy.html")


def render_terms(dateline):
    body = f"""<main class="wrap narrow"><section class="page">
  <span class="kicker">Terms</span>
  <h1>Terms of use</h1>

  <h2>Never betting advice</h2>
  <p>GoCheckMySports publishes sports news and plain-language analysis for education and
     information only. Nothing on this site is betting, gambling, financial, or legal advice,
     and nothing here is a recommendation to place any wager. GoCheckMySports reports events;
     it never advises bets. If gambling is a problem for you or someone you know, help is
     available at 1-800-GAMBLER in the United States.</p>

  <h2>Informational purposes only</h2>
  <p>Stories and commentary are assembled from public third-party sources (official league
     data, public APIs, news outlets). Data can be delayed, revised, or wrong at the source.
     Scores and schedules can change on official review. Verify anything that matters against
     primary sources before you act on it.</p>

  <h2>No warranty</h2>
  <p>The site and its data are provided "as is" and "as available," without warranties of any
     kind, express or implied, to the maximum extent permitted by law. We do not warrant that the
     site is accurate, complete, current, or uninterrupted.</p>

  <h2>Limitation of liability</h2>
  <p>To the fullest extent permitted by law, GoCheckMySports and its operators are not liable for
     any loss or damage arising from your use of this site or reliance on its content, including
     wagering losses and indirect, incidental, or consequential damages.</p>

  <h2>Governing law</h2>
  <p>These terms are governed by the laws of the State of South Carolina, without regard to
     conflict-of-law rules. If you do not agree with these terms, please do not use the site.</p>

  <p class="nfa">Last updated July 19, 2026.</p>
</section></main>"""
    return shell(f"Terms of Use - {NAME}",
                 "What GoCheckMySports is and is not: sports news for education and information, "
                 "never betting advice, with no warranty.",
                 "Terms", body, dateline, path="/terms.html")


def render_404(dateline):
    body = """<main class="wrap narrow"><section class="page" style="text-align:center;padding-top:60px">
  <span class="kicker">404</span>
  <h1>That page moved on.</h1>
  <p class="lede" style="margin-left:auto;margin-right:auto">The story you were looking for is not
     here. Try the <a href="/index.html">front page</a> or the <a href="/archive.html">archive</a>.</p>
</section></main>"""
    return shell(f"Not found - {NAME}", "Page not found.", None, body, dateline,
                 path="/404.html", noindex=True)


def render_thanks(dateline):
    body = """<main class="wrap narrow"><section class="page" style="text-align:center;padding-top:60px">
  <span class="kicker">Subscribed</span>
  <h1>You are on the list.</h1>
  <p class="lede" style="margin-left:auto;margin-right:auto">Thanks for subscribing to the brief.
     We will not sell your email, and you can unsubscribe anytime. Back to the
     <a href="/index.html">front page</a>.</p>
</section></main>"""
    return shell(f"Subscribed - {NAME}", "Thanks for subscribing.", None, body, dateline,
                 path="/thanks.html", noindex=True)


# ---- ingest approved payloads -----------------------------------------------

def ingest():
    """Promote approved payloads (out/published/*.json from publish.py) into committed content."""
    if not os.path.isdir(PUBLISHED):
        print("ingest: no out/published/ (nothing approved yet); building from committed content only.")
        return 0
    # date/time from the run, not a wall clock, so builds stay reproducible
    date, published_utc = "undated", ""
    try:
        published_utc = json.load(open(os.path.join(HERE, "out", "items.json"),
                                       encoding="utf-8"))["_meta"]["generated"]
        date = published_utc[:10]
    except Exception:
        pass
    os.makedirs(CONTENT, exist_ok=True)
    # editor rank (1 = lead) so the day's page keeps the desk's editorial order
    rank_map = {}
    try:
        ranked = json.load(open(os.path.join(HERE, "out", "editor.json"), encoding="utf-8"))["ranked"]
        rank_map = {r["id"]: i + 1 for i, r in enumerate(ranked)}
    except Exception:
        pass
    n = 0
    for fn in sorted(os.listdir(PUBLISHED)):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(PUBLISHED, fn), encoding="utf-8"))
        payload = rec.get("payload", {})
        art = payload.get("article", {})
        title = art.get("title") or "Untitled"
        slug = slugify(title)
        body = art.get("body", "")
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()] or [body]
        srcs = [{"title": u, "url": u} for u in art.get("sources", [])]
        title = destyle(title)
        # the writer model sometimes slips a process note about the review status into the
        # copy ("Note: flagged for human review."); the article is the finished story only,
        # so any such sentence is stripped from every published field at the door
        note = re.compile(r"(?:Note:\s*)?[^.!?]*(?:flagged for|pending)\s+human\s+review[^.!?]*[.!?]?\s*"
                          r"|[^.!?]*human review before publication[^.!?]*[.!?]?\s*", re.I)
        def scrub(text):
            return note.sub("", destyle(text)).strip()
        paras = [scrub(p) for p in paras]
        paras = [p for p in paras if p]
        item = {
            "id": rec.get("id"), "slug": slug, "kind": "brief",
            "title": title, "dek": scrub((payload.get("script", {}) or {}).get("summary", "")),
            "date": date, "published_utc": published_utc,
            "category": "news", "verdict": rec.get("verdict"),
            "rank": rank_map.get(rec.get("id")),
            "author": "The GoCheckMySports Desk",
            "key_fact": scrub((payload.get("script", {}) or {}).get("key_fact", "")),
            "bottom_line": scrub(art.get("bottom_line", "")),
            "human_take": destyle(art.get("human_take", "")), "body": paras, "sources": srcs,
        }
        out = os.path.join(CONTENT, f"{date}-{slug}.json")
        json.dump(item, open(out, "w", encoding="utf-8"), indent=2)
        print(f"  ingested {rec.get('id')} -> {os.path.relpath(out)}")
        n += 1
    print(f"ingest: promoted {n} approved item(s) into site content.")
    return n


# ---- build -------------------------------------------------------------------

def _copytree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target, exist_ok=True)
        for f in files:
            data = open(os.path.join(root, f), "rb").read()
            open(os.path.join(target, f), "wb").write(data)


def build():
    items = load_content()
    # dateline reflects the newest content (or a neutral standing line), never a wall clock
    newest = next((i.get("date") for i in items if not i.get("example") and i.get("date")), None)
    dateline = fmt_date(newest).upper() if newest else "AN HONEST SPORTS NEWS DESK"

    import shutil
    if os.path.isdir(PUBLISH):
        shutil.rmtree(PUBLISH)
    os.makedirs(os.path.join(PUBLISH, "articles"), exist_ok=True)
    _copytree(ASSETS, os.path.join(PUBLISH, "assets"))
    # The live layer's snapshot ships too, under the default revalidating headers (it
    # must NOT live under /assets/*, which Netlify caches for a week).
    if os.path.exists(SCORES_PATH):
        os.makedirs(os.path.join(PUBLISH, "data"), exist_ok=True)
        open(os.path.join(PUBLISH, "data", "scores.json"), "wb").write(
            open(SCORES_PATH, "rb").read())

    def w(rel, html):
        path = os.path.join(PUBLISH, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(html)

    w("index.html", render_home(items, dateline))
    w("news.html", render_news(items, dateline))
    w("archive.html", render_archive(items, dateline))
    w("method.html", render_method(items, dateline))
    w("about.html", render_about(dateline))
    w("standards.html", render_standards(dateline))
    w("privacy.html", render_privacy(dateline))
    w("terms.html", render_terms(dateline))
    w("404.html", render_404(dateline))
    w("thanks.html", render_thanks(dateline))
    for it in items:
        w(os.path.join("articles", f"{it['slug']}.html"), render_article(it, all_items=items))
    w("bottom-line.html", render_bottom_line_history(items, dateline))
    w("feed.xml", render_feed(items))

    # the iOS home-screen icon lives at the site root (family convention)
    ati_src = os.path.join(ASSETS, "apple-touch-icon.png")
    if os.path.exists(ati_src):
        open(os.path.join(PUBLISH, "apple-touch-icon.png"), "wb").write(open(ati_src, "rb").read())
    # the social card lives at the site root (family convention: /og-image.png)
    og_src = os.path.join(ASSETS, "og-image.png")
    if os.path.exists(og_src):
        open(os.path.join(PUBLISH, "og-image.png"), "wb").write(open(og_src, "rb").read())

    # sitemap (indexable pages only; 404/thanks are noindex), robots, netlify 404 redirect
    locs = ["/", "/news.html",
            "/archive.html", "/bottom-line.html", "/method.html", "/about.html", "/standards.html",
            "/privacy.html", "/terms.html"]
    locs += [f"/articles/{it['slug']}.html" for it in items if not it.get("example")]
    urls = "\n".join(f"  <url><loc>{ORIGIN}{esc(p)}</loc></url>" for p in locs)
    w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "\n</urlset>\n")
    w("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap.xml\n")
    w("_redirects", "/*  /404.html  404\n")
    n_live = sum(1 for i in items if not i.get("example"))
    print(f"site: built {PUBLISH} - {n_live} published stor{'y' if n_live == 1 else 'ies'} "
          f"+ {len(items) - n_live} example, plus home/archive/method/about/standards/404.")
    return 0


def main():
    if "--ingest" in sys.argv:
        ingest()
    build()


if __name__ == "__main__":
    main()
