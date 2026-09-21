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
import glob
import json
from zoneinfo import ZoneInfo
import os
import re
import sys
from urllib.parse import quote

import boundary

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
SLOGAN = "Sports, checked."   # the brand tagline
DESK_LINE = "The daily sports desk that checks the story before it runs."   # secondary descriptor
FAMILY = "GoCheckMySports"                     # family/domain tie: gocheckmysports.com
FAMILY_HUB = "https://gocheckmy.com/"          # the GoCheckMy family hub (canonical footer link)
ORIGIN = "https://gocheckmysports.com"         # canonical origin for canonical/og:url/sitemap

# RETIRED URLS keep working (ported from the news chassis 2026-08-25). When the desk
# publishes the same development more than once and the duplicates are merged, the
# surviving story takes the reporting and the retired slugs 301 to it via _redirects.
# Never delete a published URL outright: someone linked it, and a 404 punishes the
# reader for our filing error. The retired story's content JSON is deleted (so no page
# renders and the redirect actually fires: Netlify does not shadow existing files) and
# its slug maps here. Populated 2026-08-25 from the family duplicate audit, every
# cluster adversarially verified before this map was written.
RETIRED_ARTICLES = {
    # owner report 2026-08-28: one event told repeatedly across consecutive days
    "mlb-proposes-compressing-free-agency-window-to-2-3-weeks-union-calls-it-a-player-rights-elimination":
        "mlb-proposes-restricted-free-agency-window-and-month-long-transaction-freeze",
    "mlb-proposes-transaction-reforms-to-reduce-roster-churn-in-cba-talks":
        "mlb-proposes-restricted-free-agency-window-and-month-long-transaction-freeze",
    # family desk audit 2026-08-31: pre-fix same-event retellings (all published before
    # the 2026-08-30 merge port landed), each verified against the cluster inventory
    "red-sox-activate-anthony-story-from-il-for-yankees-series-finale":
        "red-sox-activate-anthony-and-story-from-injured-list-for-stretch-run",
    "study-finds-chronic-traumatic-encephalopathy-in-vast-majority-of-deceased-nfl-players-studied":
        "bmj-study-documents-high-cte-prevalence-among-deceased-nfl-players",
    "scheffler-wins-fedex-st-jude-championship-by-eight-shots-to-open-playoffs":
        "scheffler-dominates-fedex-st-jude-championship-with-eight-shot-victory",
    "nfl-owners-unanimously-approve-9-612-billion-sale-of-seahawks-to-khosla-family":
        "nfl-owners-unanimously-approve-9-612-billion-seahawks-sale-to-khosla-family",
    "sky-fever-matchup-draws-3-31m-viewers-wnba-s-largest-regular-season-audience-in-29-years":
        "fever-sky-game-draws-3-31-million-viewers-wnba-s-most-watched-regular-season-game-since-1997",
    "111-consecutive-games-zero-errors-wilson-breaks-mlb-shortstop-record":
        "111-games-zero-errors-wilson-sets-mlb-record-at-shortstop",
    "49ers-receiver-pearsall-undergoes-knee-surgery-eyes-2027-return":
        "49ers-wr-ricky-pearsall-undergoes-knee-surgery-targets-nine-month-recovery",
    "49ers-wr-pearsall-has-knee-surgery-targets-9-month-recovery":
        "49ers-wr-ricky-pearsall-undergoes-knee-surgery-targets-nine-month-recovery",
    "bengals-shemar-stewart-hyperextended-knee-on-day-1-of-training-camp":
        "bengals-shemar-stewart-carted-off-day-1-with-hyperextended-knee",
    "bezos-led-consortium-acquires-38-stake-in-liverpool-fc-from-fenway-sports-group":
        "consortium-led-by-bhatia-including-bezos-and-saverin-acquires-38-of-liverpool-fc",
    "blue-jackets-sign-sillinger-to-three-year-extension":
        "blue-jackets-sillinger-avoid-arbitration-with-three-year-13-875m-deal",
    "boston-celtics-agree-to-three-year-15-million-extension-with-forward-jordan-walsh":
        "celtics-extend-walsh-to-3-year-15m-deal",
    "caldwell-pope-signs-with-76ers-after-grizzlies-buyout":
        "caldwell-pope-joins-76ers-on-3-9-million-deal-after-grizzlies-buyout",
    "cara-gardner-morey-exits-vancouver-goldeneyes-gm-role-to-coach":
        "vancouver-goldeneyes-gm-cara-gardner-morey-steps-down-to-coach",
    "celtics-sign-forward-jordan-walsh-to-three-year-15m-extension-through-2029-30":
        "celtics-extend-walsh-to-3-year-15m-deal",
    "eagles-linemen-ojomo-johnson-fight-at-camp":
        "eagles-linemen-ojomo-and-johnson-scuffle-during-final-preseason-practice",
    "england-drops-carse-from-pakistan-test-squad-as-investigation-begins":
        "england-removes-carse-from-pakistan-test-squad-following-handcuffs-incident",
    "ex-qb-hasselbeck-joins-study-seeking-first-living-cte-diagnosis":
        "ex-qb-matt-hasselbeck-part-of-quest-for-living-diagnosis-of-cte",
    "fifa-adviser-cordeiro-resigns-over-infantino-private-equity-plan":
        "fifa-adviser-resigns-coo-accuses-infantino-of-deceiving-staff-on-private-equity-plan",
    "fifa-defends-infantino-against-concerted-effort-to-oust-him":
        "fifa-alleges-concerted-effort-to-undermine-infantino-amid-reelection-year-pressure",
    "fifa-issues-statement-alleging-concerted-effort-to-undermine-infantino-after-severance-claim":
        "fifa-alleges-concerted-effort-to-undermine-infantino-amid-reelection-year-pressure",
    "former-fifa-council-member-isha-johansen-calls-on-gianni-infantino-to-step-down":
        "former-fifa-council-member-isha-johansen-calls-on-infantino-to-step-down",
    "former-fifa-council-member-johansen-calls-for-infantino-s-resignation":
        "former-fifa-council-member-isha-johansen-calls-on-infantino-to-step-down",
    "former-fifa-council-member-johansen-calls-for-infantino-to-step-down":
        "former-fifa-council-member-isha-johansen-calls-on-infantino-to-step-down",
    "jordan-fa-president-accuses-fifa-of-blackmail-over-infantino-support":
        "jordan-fa-president-accuses-fifa-infantino-of-blackmail-over-world-cup-money",
    "jordan-walsh-agrees-to-3-year-15m-extension-with-celtics":
        "celtics-extend-walsh-to-3-year-15m-deal",
    "joseph-parker-cleared-to-compete-as-provisional-suspension-lifted-final-sanction-pending":
        "joseph-parker-cleared-to-compete-after-cocaine-test-final-sanction-pending",
    "joseph-parker-cleared-to-fight-after-cocaine-test":
        "joseph-parker-cleared-to-compete-after-cocaine-test-final-sanction-pending",
    "liv-golf-vendors-report-unpaid-invoices-as-saudi-pif-funding-ends-this-month":
        "liv-golf-vendors-report-unpaid-invoices-as-saudi-funding-ends",
    "mahomes-cleared-for-full-camp-participation-reid-urges-caution-on-week-1-readiness":
        "chiefs-patrick-mahomes-fully-cleared-for-training-camp-participation",
    "mercury-acquire-five-time-all-star-plum-sparks-signal-formal-rebuild-after-contention-failure":
        "kelsey-plum-traded-to-mercury-sparks-signal-reset-after-failed-contention-push",
    "mosquera-marlins-prospect-suspended-80-games-for-positive-boldenone-test":
        "marlins-mosquera-suspended-80-games-for-failed-drug-test",
    "nfl-confirms-super-bowl-lxii-in-atlanta-for-february-13-2028-locking-17-game-schedule-through-2027":
        "nfl-confirms-super-bowl-lxii-in-atlanta-for-february-13-2028-locks-17-game-schedule-through-2027",
    "noah-lyles-wins-us-100m-championship-with-world-leading-9-79-seconds":
        "lyles-wins-us-100m-championship-with-world-leading-9-79-seconds",
    "ohio-state-jpmorganchase-reach-lucrative-jersey-patch-deal":
        "ohio-state-signs-record-17m-jersey-patch-deal-with-jpmorganchase",
    "ohio-state-signs-17m-annual-jersey-patch-deal-with-jpmorganchase":
        "ohio-state-signs-record-17m-jersey-patch-deal-with-jpmorganchase",
    "ohio-state-signs-record-17m-annual-jersey-patch-deal-with-jpmorganchase":
        "ohio-state-signs-record-17m-jersey-patch-deal-with-jpmorganchase",
    "ole-miss-sues-two-former-players-for-breach-of-revenue-sharing-contracts-after-lsu-transfers":
        "ole-miss-sues-two-former-players-for-revenue-sharing-contract-breach",
    "oregon-state-women-s-basketball-players-file-for-union-representation-under-state-law":
        "oregon-state-women-s-basketball-players-file-union-petition-with-state-labor-board",
    "panthers-te-mitchell-evans-carted-off-during-training-camp-with-ankle-injury":
        "panthers-te-mitchell-evans-carted-off-at-training-camp-practice",
    "panthers-tepper-invests-another-500m-into-stadium-renovation":
        "panthers-owner-tepper-commits-additional-500-million-to-stadium-renovation-project",
    "prosecutors-allege-witness-tampering-in-rozier-betting-case":
        "federal-prosecutors-seek-incarceration-of-rozier-co-defendant-for-witness-tampering",
    "ravens-madubuike-practices-for-first-time-in-10-months-cleared-from-pup-list":
        "ravens-madubuike-practices-for-first-time-in-10-months-after-neck-injury",
    "reusser-wins-tour-de-france-femmes-stage-four-time-trial-takes-yellow-jersey":
        "reusser-wins-stage-four-time-trial-takes-yellow-jersey-at-tour-de-france-femmes",
    "robinson-and-gibbs-hold-out-from-training-camp-in-contract-standoff":
        "star-rbs-robinson-gibbs-appear-to-be-hold-ins-while-seeking-deals",
    "running-backs-robinson-gibbs-hold-out-from-training-camp-while-seeking-new-contracts":
        "star-rbs-robinson-gibbs-appear-to-be-hold-ins-while-seeking-deals",
    "saints-bryan-bresee-feared-to-have-torn-acl-on-first-day-of-camp":
        "sources-saints-bryan-bresee-feared-to-have-torn-acl",
    "sec-commissioner-sankey-conference-focused-on-federal-legislation-not-ncaa-breakaway":
        "sec-commissioner-sankey-conference-focused-on-federal-nil-legislation-not-ncaa-breakaway",
    "sparks-trade-five-time-all-star-kelsey-plum-to-phoenix-mercury":
        "kelsey-plum-traded-to-mercury-sparks-signal-reset-after-failed-contention-push",
    "uefa-concacaf-afc-accuse-fifa-of-breach-of-trust-deception-over-world-cup-plan":
        "three-major-soccer-confederations-formally-accuse-fifa-chief-of-deception",
    "uefa-concacaf-afc-accuse-fifa-of-breach-of-trust-over-world-cup-privatization-plan":
        "three-major-soccer-confederations-formally-accuse-fifa-chief-of-deception",
    "uefa-concacaf-and-afc-formally-accuse-infantino-of-deception":
        "three-major-soccer-confederations-formally-accuse-fifa-chief-of-deception",
    "uefa-votes-unanimous-boycott-of-fifa-competitions-over-private-equity-world-cup-plan":
        "uefa-concacaf-afc-unite-against-infantino-world-cup-private-equity-plan",
    "wnba-faces-eligibility-test-after-cunningham-s-transgender-comments-spark-political-attention":
        "wnba-faces-transgender-eligibility-row-after-cunningham-comments",
}

SHORT_NAME = "GoCheckMySports"                # home-screen label (manifest)
THEME_COLOR = "#1F5E3F"                       # browser chrome + manifest
OG_IMAGE = ORIGIN + "/og-image.png"            # 1200x630 social card, generated at build time
CF_ANALYTICS_TOKEN = "3939eb7cf8fc454e82fe1bd1829472cb"  # Cloudflare Web Analytics site token for gocheckmysports.com; empty renders no beacon
DESC = ("GoCheckMySports is an independent daily sports news desk built with one intention: "
        "get the stories right and keep the facts honest. Scores are facts; stories get "
        "checked against their sources before they run. Never betting advice.")
FAMILY_DESC = ("Independent sports news checked against the record before it publishes, with live scores and the sourcing behind every story. No betting picks.")
# C-L5: the one guard line. It appears in the footer and nowhere above the fold.
NFA = "No betting advice."
YEAR = "2026"
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

# NAV IS HAND-MAINTAINED AND SECTIONS IS NOT, which is how a lane can exist and be
# unreachable: the news desk shipped an /archive nobody could click for weeks. College
# Football joins here the same day it joins SECTIONS, and it sits next to NFL because
# that is how a reader thinks about football season.
# THE RAIL IS A CALENDAR, NOT AN ALPHABET (2026-09-04). Ordered by what is in season now,
# so the lanes that matter this week are visible before a reader scrolls. Revisit the order
# when the seasons turn; the list is the only place it is expressed.
NAV = [("Home", "/index.html"), ("Latest", "/news.html"),
       ("The Record", "/keepers.html"),
       ("Scores", "/scores.html"),
       ("Standings", "/standings/nfl.html"),
       ("Where to watch", "/where-to-watch.html"),
       ("Fantasy", "/fantasy/inactives.html"),
       ("NFL", "/sections/nfl.html"),
       ("College Football", "/sections/college-football.html"),
       ("MLB", "/sections/mlb.html"),
       ("Soccer", "/sections/soccer.html"),
       ("WNBA", "/sections/wnba.html"),
       ("Tennis", "/sections/tennis.html"),
       ("NBA", "/sections/nba.html"),
       ("College Basketball", "/sections/college-basketball.html"),
       ("NHL", "/sections/nhl.html"),
       ("More Sports", "/sections/more-sports.html"),
       ("Scores section", "/sections/scores.html"),
       ("Injuries", "/sections/injuries.html"),
       ("Transactions", "/sections/transactions.html"),
       ("Archive", "/archive.html"), ("About", "/about.html")]

# S-1: .mh-nav rendered thirteen items and overflowed at 1440, cutting the last two and
# scrolling "THE RECORD" to "ECORD" on section pages. Nine now, in the audit's order,
# with the product first. NAV above stays the full union: it is what the unreachable-lane
# guard reads, and a lane that moved into More is still a lane that must be reachable.
# N-1 amends S-1: Home is the first item; the wordmark stays a home link too.
NAV_PRIMARY = ["Home", "Scores", "Fantasy", "Where to watch", "The Record", "The Edition",
               "NFL", "College Football", "MLB"]
NAV_MORE = ["Standings", "Soccer", "WNBA", "Tennis", "NBA", "College Basketball",
            "NHL", "More Sports", "Archive", "About"]


# ---- helpers -----------------------------------------------------------------

def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "story"


_ET = ZoneInfo("America/New_York")


def _utc_dt(iso):
    """Parse a UTC stamp in any shape the data files use. None when it is not one."""
    import datetime as _dt
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(iso or "", fmt).replace(tzinfo=_dt.timezone.utc)
        except Exception:
            continue
    return None


def fmt_short_date(iso):
    """'Sep 11' - the meta form (G-7). Prose keeps fmt_date's 'September 11, 2026'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{MONTHS[int(m.group(2))][:3]} {int(m.group(3))}" if m else str(iso or "")


def clamp_words(text, limit, tail="\u2026"):
    """Cut at a word boundary, never mid-word (S-14, G-11).

    A bare slice produced 'The offensive er' and 'Denver Br' on section and coverage
    cards. If a sentence ends inside the limit we stop there instead, which reads as
    written rather than as cut."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    head = t[:limit]
    stop = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if stop >= limit * 0.6:
        return head[:stop + 1]
    cut = head.rsplit(" ", 1)[0].rstrip(",;:-\u2014 ")
    return (cut or head.rstrip()) + tail


_SENT_END = re.compile(r"(?<=[.!?])\s+")


def clamp_sentences(text, limit, tail="\u2026"):
    """UX-11 (S-9, C-6): a dek ends at a sentence, never an ellipsis.

    Takes as many whole sentences as fit. If not even the first one fits, the first
    sentence runs long rather than being cut, because authored text is not truncated;
    a first sentence more than half again the limit is the one case that still falls
    back to a word cut, since a dek that swallows its card is its own defect."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    parts = [x for x in _SENT_END.split(t) if x]
    out = ""
    for p in parts:
        nxt = (out + " " + p).strip() if out else p
        if len(nxt) > limit:
            break
        out = nxt
    if out:
        return out
    first = parts[0] if parts else t
    if len(first) <= limit * 1.5 and re.search(r"[.!?][\"\u2019\u201d)]*$", first):
        return first
    return clamp_words(t, limit, tail)


def _et_clock(dt):
    """An aware datetime to '6:45 PM ET'. Reader-facing times are Eastern (G-7)."""
    return dt.astimezone(_ET).strftime("%-I:%M %p ET") if dt else ""


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
    """Dateline with the publish time: 'July 12, 2026 · 3:41 AM ET'.

    H-5: ONE CONVERSION, THEN BOTH HALVES. This used to take the date from item["date"]
    and the time from the UTC timestamp converted to Eastern, so the two halves were in
    different zones. Every story published between 8 PM and midnight Eastern showed the
    wrong day: the US Open story read "September 16, 2026 · 9:28 PM ET" for a timestamp
    of 01:28Z on the 16th, which is 9:28 PM ET on the FIFTEENTH, and that byline sat on
    an Edition published the evening of the 16th. It was on the desk cards, the Record
    lists and the Edition bylines alike, because they all call this function.

    The timestamp is converted once and the date and the time are both read off that
    one value. item["date"] is the fallback only when there is no timestamp to convert,
    where there is no better answer and no contradiction to create."""
    dt = _parse_utc(item) if item.get("published_utc") else None
    if dt:
        et = dt.astimezone(_ET)
        return f"{MONTHS[et.month]} {et.day}, {et.year} · {_et_clock(dt)}"
    return esc(fmt_date(item.get("date")))


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
    # The NFL pattern knew five words, none of them the ones a season run-up is
    # written in: cutdowns, waivers, the practice squad, the 53-man limit, IR.
    # CLUB NAMES, BECAUSE THAT IS HOW A STORY NAMES A TEAM (2026-09-04). "Vikings suspend
    # Gerald Alexander", "Packers career rushing leader Ahman Green" and "Jets CB Stiggers
    # hospitalized" all filed as nothing, because the pattern knew the sport's vocabulary
    # and not its teams. UNAMBIGUOUS NAMES ONLY, the same rule the college lane already
    # applies to schools: Cardinals, Giants, Panthers, Rangers, Kings and Jets are each
    # two teams in two sports on this desk, so they stay out and their stories are caught
    # by the vocabulary terms above.
    # SHARED SEASON VOCABULARY IS NOT A LEAGUE (2026-09-04). "training camp", "preseason",
    # "waivers", "injured reserve" and "depth chart" are used by every league on this desk,
    # and while they sat here they pulled other sports onto the NFL front: "Lakers open
    # preseason against Suns" tagged nfl, "Yankees open training camp" tagged nfl,
    # "Canadiens place defenseman on waivers" tagged nfl. Three of the five put nfl AHEAD
    # of the correct league. Same doctrine as the month names and the recurring actors: a
    # token every sport uses cannot identify one sport.
    #
    # Nothing is lost by removing them. "waivers" is already owned by transactions and
    # "injured reserve" by injuries, so those stories keep their type tag; and the club
    # names added earlier today carry the league, measured at 0 NFL orphans across 46
    # headlines that name an NFL team. What stays here is NFL-only vocabulary: no other
    # league has a 53-man limit, a practice squad, a franchise tag or a PUP list.
    ("nfl", r"\b(nfl|super bowl|quarterback\w*|touchdown\w*|"
            r"roster cutdown\w*|cutdown\w*|53-man|practice squad|"
            r"pup list|franchise tag|"
            r"snap count\w*|packers|vikings|seahawks|buccaneers|bengals|browns|"
            r"steelers|ravens|texans|colts|jaguars|titans|broncos|chiefs|chargers|"
            r"cowboys|commanders|bears|lions|falcons|saints|49ers|dolphins|"
            r"patriots|bills|eagles)\b"),
    # WNBA IS NOT THE NBA (owner audit 2026-08-29): the nba pattern matches "wnba"
    # outright, so every WNBA story filed under nba. Its own rule, ahead of it.
    # City-qualified where the nickname is an ordinary word. Bare "sky" is Sky Sports and
    # tagged two Premier League stories as WNBA; "storm" is weather and tagged a rain
    # delay. Fever, Liberty, Aces, Lynx, Mercury, Sparks, Mystics and Valkyries are safe
    # on their own.
    ("wnba", r"\b(wnba|fever|liberty|aces|lynx|mercury|sparks|mystics|valkyries|"
             r"atlanta dream|chicago sky|seattle storm|dallas wings|toronto tempo|"
             r"connecticut sun)\b"),
    # Club names, unambiguous only. Heat, Thunder, Jazz, Magic and Kings are ordinary
    # words or a second team; Warriors, Lakers and the rest are not.
    ("nba", r"\b(nba|wnba|finals mvp|triple-double|warriors|lakers|celtics|knicks|nets|"
            r"bucks|nuggets|suns|mavericks|\bmavs\b|clippers|grizzlies|pelicans|spurs|"
            r"timberwolves|trail blazers|raptors|hornets|pistons|pacers|cavaliers|"
            r"\bcavs\b|wizards|76ers|sixers|bulls)\b"),
    # "Athletics" is omitted on purpose: it is Oakland's club AND this desk's track lane.
    # Giants, Cardinals and Rangers are each two teams in two sports.
    ("mlb", r"\b(mlb|world series|no-hitter|home run\w*|inning\w*|pitcher\w*|yankees|"
            r"\bmets\b|dodgers|red sox|\bcubs\b|astros|braves|phillies|padres|mariners|"
            r"brewers|guardians|orioles|twins|detroit tigers|angels|\breds\b|rockies|marlins|"
            r"pirates|royals|white sox|blue jays|diamondbacks|\bdbacks\b|"
            # league structure, unambiguous, and it covers a Detroit story now that bare
            # "tigers" is gone (LSU, Auburn and Clemson are Tigers long before Detroit is)
            r"american league|national league|al east|al central|al west|"
            r"nl east|nl central|nl west|world series)\b"),
    ("nhl", r"\b(nhl|stanley cup|hat trick|power play|goalie\w*|goaltender\w*|canadiens|"
            r"maple leafs|oilers|flames|canucks|senators|sabres|bruins|blackhawks|"
            r"penguins|capitals|lightning|predators|\bblues\b|ducks|sharks|coyotes|"
            r"golden knights|kraken|islanders|devils|flyers|red wings|avalanche|"
            r"blue jackets)\b"),
    # Club names for the same reason. "Liverpool agrees to £120m deal for Barcola" and
    # "Chelsea fined £10m" carried no tag at all. Rangers is omitted deliberately: it is
    # a Glasgow club, a baseball club and a hockey club.
    ("soccer", r"\b(premier league|champions league|la liga|serie a|bundesliga|mls|"
               r"fifa|uefa|world cup|soccer|liverpool|chelsea|arsenal|tottenham|"
               r"manchester united|man utd|manchester city|real madrid|barcelona|"
               r"atletico madrid|bayern munich|juventus|ac milan|inter milan|"
               r"borussia dortmund|paris saint-germain|\bpsg\b|west ham|everton|"
               r"newcastle united|aston villa|derby county|celtic|ajax|benfica|"
               r"english fa|national team)\b"),
    # TENNIS HAD NO RULE AT ALL (2026-09-04). Not a weak rule: no entry, so every tennis
    # story tagged to nothing, which meant no section, no related-stories links and no
    # way in except Latest and the archive. Measured on the corpus: 23 tennis stories,
    # zero tags between them, during a slam the desk's own event calendar was tracking.
    # "grand slam" is deliberately NOT here: on a desk that covers MLB it is a home run
    # four times out of five. Nor is "tiebreak": the first cut of this rule carried it and
    # promptly filed "Blue Jays Defeat Guardians, Secure Tiebreaker and Narrow Wild Card
    # Gap" as tennis. Same trap as the month names, one line after warning about it. "us open" IS here and is the known collision, with golf's
    # championship; this desk writes the tennis one without periods and golf's June major
    # has never appeared in the corpus, but a golf rule would need to claim it back.
    ("tennis", r"\b(tennis|us open|flushing meadows|wimbledon|roland garros|"
               r"french open|australian open|atp|wta|straight sets|"
               r"alcaraz|sabalenka|djokovic|swiatek|sinner|gauff|zverev|medvedev|"
               r"auger-aliassime|rybakina|pegula|navarro|kyrgios|nadal|federer|"
               r"raducanu|tiafoe|fritz|shelton|tsitsipas|musetti|draper|jabeur|"
               r"azarenka|vondrousova|krejcikova|muchova|badosa|ostapenko)\b"),
    # SEASON VOCABULARY (owner directive 2026-08-29). The old pattern knew "ncaa",
    # "college football" and "heisman" and little else, so opening weekend, every
    # conference, the playoff, the portal and every school name were invisible to
    # it. A desk covering the season has to recognise how the sport is written.
    # SPLIT BY SPORT, WITH AN UMBRELLA THAT STAYS (2026-09-04). One college tag meant a
    # basketball story reached the College Football front: "Duke opens as No. 2 in
    # preseason college basketball poll" filed there and nowhere else. But a clean two-way
    # split does not fit what this desk actually publishes. Measured on the live corpus:
    # of 29 college stories, 15 are football-specific, ONE is basketball-specific, and 13
    # carry no sport signal at all because they are governance, athletic directors, NIL,
    # eligibility and conference politics.
    #
    # So the sport-specific vocabulary splits and the shared vocabulary keeps its own tag.
    # A conference, a school name or the transfer portal does not name a sport, which is
    # the same rule the NFL vocabulary just had to learn. The SECTION decides where the
    # umbrella lands: College Football consumes college-football AND college, College
    # Basketball consumes only its own, so a basketball story stops reaching the football
    # front while governance keeps the home it already had.
    ("college-football", r"\b(college football|heisman|bowl game\w*|"
                         r"college football playoff|\bcfp\b|\bfbs\b|\bfcs\b|"
                         r"bowl subdivision|signing day|gridiron)\b"),
    ("college-basketball", r"\b(college basketball|march madness|final four|"
                           r"ncaa tournament|selection sunday|\bthe big dance\b)\b"),
    ("college", r"\b(ncaa|nil\b|transfer portal|"
                r"big ten|big 12|big twelve|pac-?12|big east|mountain west|"
                r"conference usa|sun belt|power (?:four|five)|group of five|"
                r"redshirt|recruiting class|five-star|four-star|"
                r"ohio state|notre dame|clemson|\blsu\b|auburn|florida state|"
                r"penn state|\bucla\b|\busc\b|ole miss|texas a&m|"
                r"student-?athlete\w*)\b|\b(?:SEC|ACC)\b"),
    # SPORTS THE DESK COVERS AND COULD NOT FILE (2026-09-04). 27 live stories carried no
    # tag at all, so they reached no section and no related-stories link: golf, cycling,
    # athletics, combat sports and cricket had no rule of any kind, exactly as tennis had
    # none. Player surnames are deliberately sparse here; the events and governing bodies
    # are what a story about these sports actually names.
    ("golf", r"\b(golf|pga tour|liv golf|lpga|dp world tour|ryder cup|solheim cup|"
             r"masters tournament|birdie\w*|bogey\w*|caddie\w*|tee time|"
             r"the open championship)\b"),
    ("cycling", r"\b(cycling|cyclist\w*|tour de france|vuelta|giro d'italia|giro|"
                r"peloton|velodrome|\buci\b|time trial|general classification|"
                r"volta a portugal)\b"),
    # "Athletics" alone is the name of a baseball club, so the tag is keyed on the events
    # and the governing body instead. Distances carry a unit so "800m" cannot match a
    # transfer fee.
    ("athletics", r"\b(track and field|world athletics|diamond league|commonwealth games|"
                  r"\d{3,4}m (?:final|heat|race|title)|hurdles|heptathlon|decathlon|"
                  r"steeplechase|shot put|pole vault|long jump|triple jump)\b"),
    ("combat sports", r"\b(boxing|boxer\w*|\bufc\b|\bmma\b|\bwbo\b|\bwbc\b|\bwba\b|"
                      r"\bibf\b|bellator|\bpfl\b|knockout|heavyweight|middleweight|"
                      r"welterweight|featherweight|bantamweight|title fight|undisputed "
                      r"champion|title defence|title defense)\b"),
    # "bowler" is OUT: it matched "Pro Bowler" and filed a Jamal Adams signing as cricket.
    # "innings" is out too, because the MLB rule owns it. Cricket has enough vocabulary
    # that is only ever cricket, so the ambiguous batting and bowling words earn nothing.
    ("cricket", r"\b(cricket\w*|\bt20\b|\bt10\b|\bodi\b|wicket\w*|\bipl\b|"
                r"county championship|test series|test squad|test coach|run-scorer|"
                r"the ashes)\b"),
    ("scores-results", r"\b(final score\w*|won|beat\w*|defeat\w*|shutout|overtime|"
                       r"walk-off|clinch\w*|elimination|playoff\w*|postseason)\b"),
]
_TAG_RES = [(tag, re.compile(pat, re.I)) for tag, pat in TAG_RULES]

# The tags that name a SPORT rather than a story type. tags_for guarantees one of these a
# slot when the story scored for any of them; see the reservation in tags_for.
LEAGUE_TAGS = frozenset({"nfl", "college", "college-football", "college-basketball", "nba", "wnba", "mlb", "nhl", "soccer", "tennis",
                         "golf", "cycling", "athletics", "combat sports", "cricket"})


# What a story is ABOUT lives in its headline; the body merely mentions things (owner
# audit 2026-08-29). Scoring one flat bag of title-plus-body let incidental mentions
# outvote the subject, and the tags went visibly wrong: obituaries of King Harald and
# Tim Curry filed under "technology", Mladic and Kusama under "health", a WNBA injury
# under "soccer", an NHL trade request under "nfl". A body hit still counts, it just
# cannot outrank the headline: title, dek and key_fact carry the weight, and a tag that
# appears ONLY in the body has to clear a real threshold before it labels the story.
_HEAD_WEIGHT = 6
_BODY_MIN = 2


# TAGS ARE PURE AND THEY ARE COMPUTED O(n^2) (2026-09-04). related_stories asks for the
# tags of every candidate against every item, so a 483-story corpus makes ~233,000
# tags_for calls in one build. At 3.5ms each that is fourteen minutes, and the build has
# to finish inside Netlify's limit. The function is a pure read of fields that do not
# change during a build, so it is memoised on the story's own id. This was found by the
# build blowing past ten minutes right after the tag rules were widened: the quadratic
# call pattern was always here, the longer patterns only made each call expensive enough
# to notice.
_TAGS_CACHE = {}


def tags_for(item):
    # SLUG, NOT ID. "id" is a per-run sequence number and it repeats: c001 appears 13
    # times in the sports corpus, so keying on it served one story's tags to twelve
    # others. Measured before it shipped: 231 of 483 stories got the wrong tags. A
    # shallow key is not an identity, which is the rule this desk keeps relearning.
    _ck = item.get("slug")
    if _ck is not None:
        _hit = _TAGS_CACHE.get(_ck)
        if _hit is not None:
            return _hit
    _res = _tags_for_uncached(item)
    if _ck is not None:
        _TAGS_CACHE[_ck] = _res
    return _res


def _tags_for_uncached(item):
    body = item.get("body") or []
    head = " ".join([item.get("title") or "", item.get("dek") or "",
                     item.get("key_fact") or ""])
    body_text = " ".join(p if isinstance(p, str) else "" for p in body)
    scored = []
    for i, (tag, rx) in enumerate(_TAG_RES):
        h = len(rx.findall(head))
        b = len(rx.findall(body_text))
        if not h and b < _BODY_MIN:
            continue          # a single passing mention is not what the story is about
        # A HEADLINE HIT ALWAYS OUTRANKS BODY VOLUME. Capping the body's contribution
        # below one headline hit is the whole point: an obituary whose body mentions the
        # hospital nine times is still an obituary, and before this cap it filed as health.
        score = h * _HEAD_WEIGHT + min(b, _HEAD_WEIGHT - 1)
        if score:
            scored.append((score, i, tag))
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = [t[2] for t in scored[:3]]
    # ONE SLOT IS RESERVED FOR THE LEAGUE (2026-09-04). Only three tags are kept and ties
    # break by list position, and the two type rules (injuries, transactions) sit at
    # positions 0 and 1. "Canadiens place defenseman on waivers" came back
    # ['transactions', 'nfl', 'nhl'] with the real league THIRD, and one more type rule
    # (fantasy, scores, anything) would have pushed NHL off the list and orphaned the
    # story from every section page. The cap is fine; letting a story type outrank the
    # sport it happened in is not. So if a league scored at all, it is guaranteed a slot,
    # taking the place of the weakest non-league tag.
    if not any(t in LEAGUE_TAGS for t in top):
        best = next((t[2] for t in scored if t[2] in LEAGUE_TAGS), None)
        if best is not None:
            top = (top[:2] if len(top) >= 3 else top) + [best]
    return top[:3]


def related_stories(item, items, n=6):
    # 6, not 3 (2026-08-25). Search Console showed the internal link graph inverted:
    # boilerplate pages carried 100+ internal links each while articles carried 13 or
    # fewer, and 207 of 369 sitemap articles were still uncrawled. This module is the
    # desk's only article-to-article link source and it already reaches 96% of stories,
    # so widening it from 3 to 6 is the cheapest available doubling of the links that
    # actually point at content rather than at the masthead.
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
           f"<title>{esc(NAME)}</title>",
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


def tracking_match(story, rx):
    """True when a story is genuinely ABOUT a tracked storyline, not merely mentioning
    it (2026-07-27: the Severe weather chip landed on a Tour de France story whose dek
    mentioned a wildfire once). A title hit qualifies alone; otherwise two or more hits
    across title+key_fact. THE DEK DOES NOT QUALIFY (2026-08-25): it is where
    comparative asides live, and two of them hijacked the Iran chip onto a Panama Canal
    story whose dek compared canal traffic to the Strait of Hormuz. A storyline the
    story is ABOUT shows up in the title or in key_fact, the central claim.
    Module level so the canary can pin the regression."""
    title = story.get("title") or ""
    if rx.search(title):
        return True
    text = " ".join([title, story.get("key_fact") or ""])
    return len(rx.findall(text)) >= 2


# ---- coverage hubs (consolidation program 2026-09-01) ------------------------
# Search Console keeps declining to crawl the article long tail: a new domain gets a
# small crawl budget and commodity sports news decays fast, so most chapter URLs are
# never worth a crawl on their own. The evergreen layer Search Console DOES reward is
# one stable URL per storyline, so every watchlist narrative with enough published
# chapters gets a /coverage/ hub that accumulates them, newest first. Reader-facing
# label for the layer: "Full coverage".

HUB_MIN_STORIES = 3


def _watchlist():
    try:
        return json.load(open(os.path.join(HERE, "config.json"),
                              encoding="utf-8")).get("narratives", {}).get("watchlist", [])
    except Exception:
        return []


def narrative_rx(narrative):
    kws = narrative.get("keywords") or []
    if not kws:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b", re.I)


def narrative_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def coverage_hubs(items):
    """The storylines that have earned a hub: HUB_MIN_STORIES or more published stories
    genuinely ABOUT the narrative (tracking_match, the same bar the Tracking chips use),
    newest first. Superseded and example stories are excluded, and so are the wraps,
    for the same reason the chips exclude them: an edition mentions every storyline of
    its day without being about any of them."""
    hubs = []
    for n in _watchlist():
        rx = narrative_rx(n)
        if rx is None:
            continue
        stories = [i for i in items
                   if not i.get("example") and not i.get("superseded_by")
                   and not _is_wrap(i) and tracking_match(i, rx)]
        if len(stories) < HUB_MIN_STORIES:
            continue
        stories.sort(key=lambda i: i.get("published_utc") or i.get("date") or "",
                     reverse=True)
        name = n.get("name") or ""
        hubs.append({"name": name, "slug": narrative_slug(name), "rx": rx,
                     "stories": stories})
    return hubs


def destyle(text):
    """House style: no em/en dashes in site copy (model drafts sometimes use them).

    ENTITIES COUNT. This handled the literal characters only, and the gap was not
    theoretical: three em dashes shipped on a sister site written as &mdash;, including one
    in an H2, and a lint that counted literal characters reported zero. A dash a reader sees
    is a dash whatever it is spelled as in the source, so the numeric and named entity forms
    are normalised here too, before the literal pass runs on whatever they decode to.

        NEVER PUNCTUATE TWICE, AND NEVER REWRITE A QUOTATION (owner audit 2026-08-25).
    The old pass replaced every em dash with ", " unconditionally, so a dash that
    already followed punctuation produced the published string "government. , and",
    and a dash INSIDE a verbatim quotation was silently repunctuated, which changes
    what a named person is quoted as saying. House style still bans the desk's own
    dashes; a source's own words inside quotation marks are left exactly as spoken.
    """
    import re as _re
    s = str(text or "")
    for ent in ("&mdash;", "&#8212;", "&#x2014;", "&#X2014;"):
        s = s.replace(ent, "\u2014")
    for ent in ("&ndash;", "&#8211;", "&#x2013;", "&#X2013;"):
        s = s.replace(ent, "\u2013")

    def _clean(seg):
        # en dash between digits is a numeric range and stays a hyphen
        seg = _re.sub(r"(?<=\d)\s*\u2013\s*(?=\d)", "-", seg)
        seg = seg.replace("\u2013", "-")
        # an em dash following punctuation needs no comma of its own
        seg = _re.sub(r"(?<=[.,;:!?])\s*\u2014\s*", " ", seg)
        # ...nor does one immediately before punctuation or at the end
        seg = _re.sub(r"\s*\u2014\s*(?=[.,;:!?])", "", seg)
        seg = _re.sub(r"\s*\u2014\s*$", "", seg)
        seg = _re.sub(r"\s*\u2014\s*", ", ", seg)
        return _re.sub(r",\s*,", ",", seg)

    # S-15, owner ruling 2026-09-15: house style beats the quotation exemption. The
    # 2026-08-25 audit had carved quoted speech out of this pass so a source's own words
    # were never repunctuated; Jack has now ruled no em dashes anywhere, quotes
    # included, which is what the September audit asked for. The exemption is gone.
    #
    # THE OTHER HALF OF THAT RULING STANDS. "Never punctuate twice" is a separate rule
    # and _clean still enforces it: a dash already following punctuation does not get a
    # comma of its own, which is what produced the published string "government. , and".
    return _clean(s)


_DESTYLE_SKIP = {"url", "href", "link", "slug", "id", "image", "src", "canonical",
                 "published_utc", "date", "event_utc"}


def _destyle_item(obj):
    """S-15: house style over every text field of an item, however deep.

    A fixed list of keys was not enough. The last em dash in the built output sat in
    boundary.fixed - a nested dict - and enumerating fields would only hold until the
    next nested one appeared. This walks the item instead and rewrites every string,
    skipping the keys that are identifiers rather than prose: a dash inside a URL or a
    slug is structure, not punctuation."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _DESTYLE_SKIP:
                continue
            if isinstance(v, str):
                obj[k] = destyle(v)
            else:
                _destyle_item(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = destyle(v)
            else:
                _destyle_item(v)


# ---- UX-15 (S-13): one headline style, sentence case -----------------------------
# Older stories came in Title Case and newer ones in sentence case, so the homepage
# carried both. Title Case is converted at load, once, so every surface that shows a
# headline shows the same style: the card, the H1, the browser tab, the Edition, the
# archive. Slugs are built from the original and never move.
#
# The hard part is knowing which capitals are the style and which are the subject.
# A fixed word list would be wrong by the second week of a season, so the desk reads
# its own corpus: a word that appears capitalised in the middle of body sentences,
# and rarely lower-case there, is a name. "Lions", "Ballmer", "Rasmussen" survive;
# "Teams", "Deals", "Deadline", "Expected" do not.

_SC_KEEP = {
    "NFL", "NBA", "MLB", "NHL", "MLS", "NCAA", "WNBA", "PGA", "LPGA", "UFC", "F1",
    "ACC", "SEC", "PAC", "AFC", "NFC", "AL", "NL", "CFP", "CBA", "MVP", "OT", "TD",
    "QB", "RB", "WR", "TE", "DE", "DT", "LB", "CB", "SS", "FS", "OL", "DL", "PK",
    "ESPN", "CBS", "NBC", "ABC", "TNT", "TBS", "FOX", "BBC", "AP", "PFF", "PFT",
    "US", "USA", "UK", "EU", "TV", "AI", "CEO", "GM", "IR", "PUP", "ACL", "MCL",
    "UCL", "PCL", "TJ", "IL", "DFA", "DH", "ERA", "RBI", "OPS", "WAR", "EPA",
    "NFLPA", "NBPA", "MLBPA", "NHLPA", "IOC", "FIFA", "UEFA", "USMNT", "USWNT",
    "II", "III", "IV", "JR", "SR", "OKC", "LA", "NY", "SF", "DC", "KC", "TB",
}

_SC_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019]*")
_SC_VOCAB = None


def _sc_looks_title(t):
    """A vocabulary-free shape test, used only while the vocabulary is being built."""
    w = [x for x in _SC_WORD.findall(t)[1:] if len(x) > 3]
    if len(w) < 4:
        return False
    return sum(1 for x in w if x[0].isupper()) / len(w) >= 0.75


def _sc_vocab(items):
    """The corpus's own usage. Counted only mid-sentence, because the first word of a
    sentence is capitalised by grammar and says nothing about the word.

    The first cut of this asked "is this word a name?" and lower-cased everything it
    could not prove, which turned Fredd Young into fredd young and Bo Nix into bo Nix.
    A desk that never invents a number does not guess at a name either, so the question
    is inverted: a word is lower-cased only where the desk's own sentences use it
    lower-case at least as often as capitalised. A word the corpus has never written in
    lower case keeps the case it arrived in. Pairs are counted too: Ohio State and US
    Open are capitalised together often enough that neither half is a common word."""
    global _SC_VOCAB
    if _SC_VOCAB is not None:
        return _SC_VOCAB
    cap, low, pair = {}, {}, {}
    for it in items:
        paras = [str(b) for b in (it.get("body") or [])]
        if it.get("dek"):
            paras.append(str(it["dek"]))
        # A headline the desk already wrote in house style is the best evidence there
        # is about which words the house lower-cases; Title Case ones say nothing.
        t = it.get("title") or ""
        if t and not _sc_looks_title(t):
            paras.append(t)
        for para in paras:
            for sent in re.split(r"(?<=[.!?])\s+", para):
                ws = _SC_WORD.findall(sent)[1:]
                for n, w in enumerate(ws):
                    k = w.lower()
                    if w[0].isupper():
                        cap[k] = cap.get(k, 0) + 1
                        if n + 1 < len(ws) and ws[n + 1][:1].isupper():
                            bk = (k, ws[n + 1].lower())
                            pair[bk] = pair.get(bk, 0) + 1
                    else:
                        low[k] = low.get(k, 0) + 1
    _SC_VOCAB = (cap, low, {k for k, n in pair.items() if n >= 3})
    return _SC_VOCAB


_SC_EN = None
_SC_ROSTER = None


def _sc_english():
    """The common-noun and verb list, shipped with the desk rather than read from the
    build machine, so a headline casts the same here as it does on the deploy. It is
    the system word list with every capitalised entry dropped, which is what makes it
    usable: it holds "clinic", "premiere" and "overwhelm" and does not hold "Ohio",
    "September" or "Clippers"."""
    global _SC_EN
    if _SC_EN is None:
        _SC_EN = set()
        path = os.path.join(HERE, "site", "data", "common_words.txt.gz")
        if os.path.exists(path):
            import gzip
            with gzip.open(path, "rt", encoding="utf-8") as f:
                _SC_EN = {l.strip() for l in f if l.strip()}
    return _SC_EN


def _sc_roster():
    """Every word of every name on the player index. A surname that is also an English
    word (Moss, Young, Bowers) is a name first on a sports desk, and the index is the
    league's own spelling of it rather than anything the desk inferred."""
    global _SC_ROSTER
    if _SC_ROSTER is None:
        _SC_ROSTER = set()
        try:
            d = json.load(open(os.path.join(HERE, "site", "data", "players.json"),
                              encoding="utf-8"))
            for pl in (d.get("players") or []):
                for w in _SC_WORD.findall(str(pl.get("name") or "")):
                    if len(w) > 1:
                        _SC_ROSTER.add(w.lower())
        except Exception:
            pass
    return _SC_ROSTER


def _sc_name(k, v):
    """A name, by any of the three things the desk actually knows: the league's player
    index, the site's own abbreviations, or its own writing. The last is a ratio, not a
    majority: Cup is written capitalised three hundred times and lower-case three, and
    Sports and Series are split down the middle, which is why World Cup holds together
    and Championship Series does not."""
    cap, low, _ = v
    if k.upper() in _SC_KEEP or k in _sc_roster():
        return True
    return cap.get(k, 0) >= 3 and low.get(k, 0) * 10 <= cap.get(k, 0)


_SC_SUFFIX = (("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"), ("ies", "y"),
              ("es", ""), ("s", ""), ("ly", ""))


def _sc_common(k, v):
    """A word the house writes in lower case: either the desk's own sentences say so,
    or it is an ordinary English word. Inflections are settled by their stem, because
    no list carries every "criticizes" and "intensifies"."""
    cap, low, _ = v
    if low.get(k, 0) >= 3 and low.get(k, 0) >= cap.get(k, 0):
        return True
    en = _sc_english()
    if k in en:
        return True
    for suf, add in _SC_SUFFIX:
        if k.endswith(suf) and len(k) - len(suf) >= 3:
            stem = k[:-len(suf)] + add
            if stem in en or (low.get(stem, 0) >= 3 and low.get(stem, 0) >= cap.get(stem, 0)):
                return True
    return False


def _sc_is_title_case(t, v):
    """Title Case capitalises the ordinary words, so only ordinary words are evidence.
    Names, acronyms and the first word are capitalised in both styles and are ignored:
    counting them read "Former All-Pro LB Fredd Young dies at 64", which is already in
    house style, as Title Case."""
    toks = [x for x in _SC_WORD.findall(t)]
    ev = [x for x in toks[1:]
          if len(x) > 3 and x.upper() not in _SC_KEEP and not x.isupper()
          and _sc_common(x.lower(), v)]
    if len(ev) < 2:
        return False
    return sum(1 for x in ev if x[0].isupper()) / len(ev) >= 0.6


def _sc_token(tok, first, prev, nxt, v):
    """One word, hyphen parts handled separately so "Eight-Year" becomes "eight-year"
    while "All-Pro" keeps the name it carries."""
    _, _, pairs = v
    out, parts = [], tok.split("-")
    for n, part in enumerate(parts):
        m = _SC_WORD.match(part)
        if not m:
            out.append(part)
            continue
        word = m.group(0)
        rest = part[len(word):]
        k = word.lower()
        # A pair only holds a common word up when the other half is a name: Ohio
        # State and US Open survive, College Sports and Championship Series do not.
        bound = False
        if n == 0:
            if (prev, k) in pairs and _sc_name(prev, v):
                bound = True
            if (k, nxt) in pairs and _sc_name(nxt, v):
                bound = True
        keep = (
            (first and n == 0)
            or word.upper() in _SC_KEEP
            or word.isupper()
            or (len(word) > 1 and any(c.isupper() for c in word[1:]))
            or any(c.isdigit() for c in part)
            or len(word) == 1
            or bound
            or _sc_name(k, v)
            or not _sc_common(k, v)
        )
        out.append((word if keep else word.lower()) + rest)
    return "-".join(out)


def sentence_case(title, v):
    """Title Case in, sentence case out. Anything already in sentence case is returned
    untouched, so the rule never re-cases the desk's own writing."""
    if not title or not _sc_is_title_case(title, v):
        return title
    toks = re.split(r"(\s+)", title)
    words = [i for i, t in enumerate(toks) if t.strip()]
    low = {}
    for i in words:
        m = _SC_WORD.match(toks[i].split("-")[0])
        low[i] = m.group(0).lower() if m else ""
    out, first = list(toks), True
    for j, i in enumerate(words):
        prev = low[words[j - 1]] if j else ""
        nxt = low[words[j + 1]] if j + 1 < len(words) else ""
        out[i] = _sc_token(toks[i], first, prev, nxt, v)
        first = bool(re.search(r"[.!?:]$", toks[i].strip()))
    return "".join(out)


def load_content():
    items = []
    if os.path.isdir(CONTENT):
        for fn in sorted(os.listdir(CONTENT)):
            if fn.startswith("_") or not fn.endswith(".json"):
                continue
            c = json.load(open(os.path.join(CONTENT, fn), encoding="utf-8"))
            c.setdefault("slug", slugify(c.get("title", "")))
            # S-15: house style applies to every text field of every item, whatever
            # path it arrived by. destyle ran only in the brief loader, so stories
            # already committed under CONTENT kept their dashes - the four the audit
            # found were all in this set. Normalising at load covers both.
            _destyle_item(c)
            # Derived, not stored, so stories published before the flag existed are
            # labelled too. Editions are excluded: a daily wrap cites the day's stories and
            # is not a single-outlet claim.
            if "developing" not in c:
                c["developing"] = ((not _is_wrap(c)) and len(c.get("sources") or []) < 2
                                   and not c.get("also_reported_by"))
            items.append(c)
    # newest first by date then id
    # newest date first; within a date, the editor's rank (1 = lead); unranked (intro,
    # example) after the day's ranked stories
    items.sort(key=lambda c: (c.get("date", ""), -(c.get("rank") or 999), c.get("id", "")),
               reverse=True)
    # A SUPERSEDE POINTER WITH NO TARGET RETIRES A STORY BEHIND NOTHING. Both desks carry
    # one: the successor was held by story_shape_problems or folded into another file
    # after the pointer had already been written, so the reader lost the story and got no
    # replacement, and the article page offered a link to a 404. Fail-open at load: the
    # story is live until something real supersedes it.
    _live = {c.get("slug") for c in items if c.get("slug")}
    for c in items:
        s = c.get("superseded_by")
        if s and s not in _live:
            print(f"::warning::load_content: {(c.get('slug') or '?')[:60]} is marked "
                  f"superseded by {s[:60]!r}, which is not published; keeping it live")
            c.pop("superseded_by", None)
        k = c.get("continued_by")
        if k and k not in _live:
            c.pop("continued_by", None)

    # UX-15 (S-13): one headline style, applied once, here, so that every surface that
    # shows a headline shows the same one: the card, the H1, the browser tab, the
    # Edition, the archive, the feed. Slugs were set above from the original title and
    # do not move, because a URL never changes.
    v = _sc_vocab(items)
    n = 0
    for c in items:
        t = c.get("title")
        if t:
            u = sentence_case(t, v)
            if u != t:
                c["title"] = u
                n += 1
    if n:
        print(f"house style: {n} headline(s) cast to sentence case")
    return items


# ---- shared chrome -----------------------------------------------------------

def masthead(active, dateline, brand="site"):
    """One identity everywhere: GoCheckMySports is both the site and the desk. The brand
    parameter is kept for the shared call sites; every page renders the same masthead."""
    # THE RAIL IS LANES, NOTHING ELSE (2026-09-04). Home, Latest, Archive and About are not
    # sections; carrying them in the rail spent scroll width on navigation a reader already
    # has in the wordmark and the footer, and pushed real lanes off the visible edge on a
    # phone. Home is the wordmark, Latest sits beside it, and Archive and About moved into
    # the footer in the same change: /archive was orphaned once already (owner audit
    # 2026-08-29) by being linked from exactly one place, so it never leaves here without
    # arriving somewhere else first.
    # WHERE TO WATCH LEAVES THE RAIL WITH ITS PAGE. where_to_watch withdraws the page
    # when its feed has been unreachable for six days, and a nav entry pointing at a
    # page that was withdrawn is a 404 in the most prominent place on the site.
    _hidden = set()
    if not W2W_LIVE:
        _hidden.add("Where to watch")
    if not IA_BOARD:
        _hidden.add("Fantasy")
    _href = dict(NAV)
    if EDITION_HREF:
        _href["The Edition"] = EDITION_HREF
    nav = "".join(
        f'<a href="{esc(_href[label])}"'
        f'{" class=active" if label == active else ""}>{esc(label)}</a>'
        for label in NAV_PRIMARY
        if label in _href and label not in _hidden)
    _more = [l for l in NAV_MORE if l in _href and l not in _hidden]
    if _more:
        _open = " open" if active in _more else ""
        nav += (f'<details class="mh-more"{_open}><summary>More</summary>'
                f'<div class="mh-more-sheet">'
                + "".join(f'<a href="{esc(_href[l])}"'
                          f'{" class=active" if l == active else ""}>{esc(l)}</a>'
                          for l in _more)
                + '</div></details>')
    fam = f''
    # wordmark: "GoCheckMy" in the shared ink color, the site name ("Sports"/"News")
    # in the site color and italic (owner directive 2026-07-24)
    _base = "GoCheckMy"
    _site = NAME[len(_base):] if NAME.startswith(_base) else ""
    _wordmark = (f'<span class="mh-word-base">{esc(_base)}</span>'
                 f'<span class="mh-word-site">{esc(_site)}</span>') if _site else esc(NAME)
    brand_row = f"""<a class="mh-brand" href="/index.html" style="margin-top:8px">
    <img class="mh-mark" src="/assets/logo.svg" alt="">
    <span class="mh-word">{_wordmark}</span>
    <span class="mh-slogan">{esc(SLOGAN)}</span>
  </a>"""
    return f"""<div class="top-rule"></div>
<header class="masthead"><div class="wrap">
<script>document.addEventListener("DOMContentLoaded",function(){{var e=document.querySelector("[data-live-date]");
if(e){{e.textContent=new Date().toLocaleDateString("en-US",{{month:"long",day:"numeric",year:"numeric"}}).toUpperCase();}}}});</script>
  <div class="mh-top">
    {fam}
    <span class="mh-dateline"><span data-live-date>{esc(dateline)}</span></span>
  </div>
  {brand_row}
</div></header>
<nav class="mh-nav"><div class="wrap" id="lane-rail">{nav}</div></nav>
<script>(function(){{var r=document.getElementById("lane-rail");if(!r)return;
var a=r.querySelector("a.active");if(!a)return;
/* A reader who lands on /sections/nhl.html must see where they are. The active chip can
   sit past the fold of a rail this long, so bring it into view on load without moving
   the page itself. */
var want=a.offsetLeft-(r.clientWidth-a.offsetWidth)/2;
r.scrollLeft=Math.max(0,Math.min(want,r.scrollWidth-r.clientWidth));}})();</script>"""


def newsletter():
    """NO EMAIL CAPTURE (family law, reaffirmed by directive v2 2026-09-12).

    The desk collected addresses through Netlify Forms for a newsletter that was
    never launched, which means it held personal data it had no use for and no
    schedule to justify. The markup is gone rather than hidden: a form that is
    display:none still posts if a crawler or a script reaches it.

    Returns empty so every historical call site is a no-op. If a newsletter is
    ever deliberately approved, rebuild this from the approval, not from here.
    """
    return ""


def trust_block():
    return f"""<section class="trust"><div class="wrap">
  <div class="sec-head"><h2>The desk's promise</h2><span class="bar"></span></div>
  <p class="trust-line">We aggregate stories from official league data and established
  outlets, audit every one for credibility, and surface only what genuinely matters, with
  the rumor and the hype stripped out. Sources are linked on every story, and nothing here
  is ever betting advice.</p>
</div></section>"""


def footer(brand="site", fantasy=False):
    """One identity everywhere; the brand parameter is kept for the shared call sites.

    C-L5: the guard line lives here and only here. Fantasy pages add a second line."""
    links = "".join(f'<a href="{esc(h)}">{esc(l)}</a>' for l, h in
                    # About and Archive live in the masthead nav; repeating them here gave
                    # every page two links to each and helped invert the link graph. The
                    # footer keeps what the nav does not carry.
                    [("Archive", "/archive.html"), ("About", "/about.html"),
                     ("How we work", "/method.html"),
                     ("Standards & corrections", "/standards.html"),
                     ("Privacy", "/privacy.html"), ("Terms", "/terms.html"),
                     ("Contact", "mailto:desk@gocheckmysports.com"),
                     ("RSS", "/feed.xml")])
    who = f"{esc(NAME)}"
    # C-L5 / item 4: one guard line, in one place, muted. The paragraph that used to sit
    # here is the About page's job (C-L9); the footer links there.
    note = ""
    return f"""<footer class="site"><div class="wrap">
  <div class="frow">
    <div class="fbrand">{who}</div>
    <div class="flinks">{links}</div>
  </div>
  <p class="fnote">{esc(NFA)}{" Official reports only." if fantasy else ""}
    {who} · <a href="{FAMILY_HUB}">A GoCheckMy site</a>.<br>&copy; {YEAR} Go Check My Brands LLC</p>
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

    # V-7: FONTS ARE EXEMPT, and they have to be. A woff2 is requested twice over: once
    # by the preload in the HTML, which this function versions, and once by the
    # @font-face url() inside site.css, which it does not. Two different URLs for the
    # same bytes is two downloads, measured on the phone build: seven font requests for
    # five files. The preload then preloads something the page never asks for, which is
    # the opposite of what a preload is for.
    #
    # Cache-busting for fonts rides on the filename instead. They are subset artifacts
    # that change only when the subsetting changes, and a changed subset ships under a
    # new name.
    # R-4: the hero posters join the fonts in the exemption, and for the same reason.
    # The preload in the HTML was versioned and the background url() in site.css was
    # not, so the phone requested hero-poster-phone.webp twice: once with the hash and
    # once without. Two URLs for the same bytes is two downloads.
    return re.sub(r'((?:src|href)=")(/assets/(?!fonts/)(?!hero/)[^"?#]+)(")',
                  lambda m: f'{m.group(1)}{m.group(2)}?v={ver(m.group(2))}{m.group(3)}', html)


# The motion layer's shared guard: reduced-motion strips every video to its poster and
# freezes the micro-details; otherwise videos play only while on screen and story cards
# fade up once. Inline (one request), transform/opacity only, no layout shift.
ATMOS_MOTION_JS = """<script>(function(){
  /* A-16: five moves and no more.
     (1) the live dot pulses, only while a game is live - CSS.
     (2) the lead number counts up once on first paint.
     (3) sparklines draw on, staggered in reading order, once.
     (4) the band's slow zoom - CSS, desktop only, already shipped.
     (5) card lift on hover - CSS, pointer devices only.
     prefers-reduced-motion:reduce stops all five and the loop. */
  try{
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    /* (2) COUNT-UP: REMOVED (C-13). It animated from zero to the value over 600ms,
       so for 600ms the page showed a price that was not the price: screenshots on two
       consecutive days caught the Bitcoin tile at $11,953.88 and $13,908.07 on its way
       to eighty thousand. A number that is not the number, even for a frame, is a
       fabricated number on the front page, and no amount of polish buys that. The
       figure is set at once; the tile's wash settles instead, which is move (1). */

    /* (3) DRAW-ON. The stroke is measured, dashed to its own length and the offset
       animated to zero. The element keeps its size throughout, so again no shift. */
    var lines = document.querySelectorAll('.tile-series polyline, .cb-leadchart polyline');
    [].forEach.call(lines, function(ln, i){
      var len;
      try { len = ln.getTotalLength(); } catch(e) { return; }
      if (!len) return;
      ln.style.strokeDasharray = len + ' ' + len;
      ln.style.strokeDashoffset = len;
      setTimeout(function(){
        ln.style.transition = 'stroke-dashoffset 900ms ease-out';
        ln.style.strokeDashoffset = '0';
      }, 60 * i);
    });
  }catch(e){}
})();</script>
"""


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
    '}'
    # UX-18 (S-15): the reveal-on-scroll fade is gone. It held content back from the
    # reader for the length of an observer callback, left blanks in print and in reader
    # mode, and was never one of the five moves. Nothing replaces it: a card that is on
    # the page is on the page.
    '})()</script>')


def shell(title, desc, active, body, dateline, body_class="", path="/", noindex=False,
          brand="site", og_type="website", schema_extra="", og_image=None,
          canonical_path=None):
    # R-4: the preconnects to Google are gone with the fonts they were for. A
    # preconnect to a host the page never contacts costs a DNS lookup and a TLS
    # handshake for nothing, on the critical path, which is the opposite of the point.
    fonts = (
             # V-7: THE FONTS ARE OURS NOW. Five woff2 files in site/assets/fonts,
             # 59.9 KB together, served from this origin. Google Fonts cost two DNS
             # lookups, two TLS handshakes and a stylesheet round trip BEFORE the first
             # font byte moved, all of it on the LCP path, and it was the slowest thing
             # on the page that we controlled.
             #
             # Preload the two faces that block first paint: the serif the masthead and
             # every headline use, and the sans the body uses. The mono and the italic
             # are wanted below the fold and load on their own.
             '<link rel="preload" as="font" type="font/woff2" crossorigin '
             'href="/assets/fonts/newsreader-roman.woff2">'
             '<link rel="preload" as="font" type="font/woff2" crossorigin '
             'href="/assets/fonts/inter.woff2">')
    # ONE URL PER PAGE (2026-08-17). Netlify's Pretty URLs serve every page at both
    # /articles/foo and /articles/foo.html, and rewrite internal links to the
    # extensionless form. Emitting a .html canonical meant Google crawled the linked
    # (extensionless) URL, read a canonical pointing somewhere else, and filed it as
    # "Alternate page with proper canonical tag" for every story. The same mismatch made
    # og:url disagree with the URL people actually share. Both are fixed by naming the
    # form the site actually serves and links. If Pretty URLs is ever disabled, this must
    # revert with it, or every canonical will point at a 404.
    # CANONICAL MAY POINT ELSEWHERE (crawl audit 2026-08-25): a composite page whose
    # unique content already lives on its own URL should name that URL rather than
    # compete with it. Everything else keeps the self-referential canonical.
    _cp = canonical_path or path
    url = ORIGIN + (_cp[:-5] if _cp.endswith(".html") else _cp)
    site_name = NAME
    # S-25: the band's backdrop poster IS the LCP element by design (addendum item 2),
    # so it is preloaded at high priority. The loop is injected after the load event by
    # script and is never preloaded. 1280 wide, not the addendum's 1600: that is the
    # widest source in the repo and upscaling adds bytes without detail (owner call,
    # 2026-09-15). 80KB against the 120KB ceiling.
    # V-7: THE PHONE NEVER FETCHES THE FULL POSTER. The poster is a CSS background,
    # not an <img>, so <picture> and imagesrcset do not apply: with imagesizes the
    # browser still resolves a 390 CSS-pixel viewport at 2x to 780 and takes the large
    # file. A media-gated preload is the tool that actually works here, and it pairs
    # with the matching media query on the background in site.css, so exactly one of
    # the two is ever requested.
    lcp = (('<link rel="preload" as="image" media="(max-width:720px)" '
            'href="/assets/hero/hero-poster-phone.webp" fetchpriority="high">\n'
            '<link rel="preload" as="image" media="(min-width:721px)" '
            'href="/assets/hero/hero-poster.webp" fetchpriority="high">\n')
           if path == "/" else "")
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
<meta property="og:image" content="{og_image or OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:image:alt" content="{esc(NAME)} share card">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{og_image or OG_IMAGE}">
<meta name="twitter:image:alt" content="{esc(NAME)} share card">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta property="og:locale" content="en_US">
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="{THEME_COLOR}">
{fonts}
<link rel="stylesheet" href="/assets/site.css">
</head>
<body class="{esc(body_class)}">
<div class="ground" aria-hidden="true"></div>
{skip}{masthead(active, dateline, brand)}
{body}
{footer(brand, fantasy=str(path or "").startswith("/fantasy"))}{beacon}
{tab_bar(path)}
{MOTION_JS}{ATMOS_MOTION_JS}{SW_REGISTER}{FORMAT_JS if 'fmt-btn' in body else ''}{PLAYER_SEARCH_JS if 'pc-q' in body else ''}
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


def _independent_outlets(item):
    """The distinct outlets that carried this story: its cited sources plus the
    corroboration the aggregator recorded. Two of these is what "Verified" claims."""
    outs = []
    for src in (item.get("sources") or []):
        nm = (src.get("title") or src.get("name") or "") if isinstance(src, dict) else ""
        nm = (nm or "").strip().lower()
        if nm and nm not in outs:
            outs.append(nm)
    for a in (item.get("also_reported_by") or []):
        nm = ((a.get("outlet") or "") if isinstance(a, dict) else "").strip().lower()
        if nm and nm not in outs:
            outs.append(nm)
    return outs


def status_badge(item):
    """UX-2 (S-2): ONE STATUS PER STORY, AND ONLY ONE.

    Cards carried "Verified" and "Developing, single source" side by side, and
    "Verified" beside "Reported \u00b7 ESPN", because two badge systems rendered on the
    same card: verdict_badge for the verifier's verdict and _receipt_status for the
    sourcing. A reader cannot tell from that whether the desk stands behind the story,
    and the badge vocabulary is the site's promise: it cannot argue with itself.

    The vocabulary, in order of precedence:
      Developing            an event still in motion
      Verified              the verifier cleared it AND two or more outlets carried it
      Reported \u00b7 Outlet     one named outlet
      (nothing)             no named outlet to stand behind

    A story the verifier did not clear is never "Verified" however many outlets carried
    it; corroboration is not the desk's own check.
    """
    if item is None:
        return ""
    if item.get("developing"):
        return ('<span class="badge developing" title="An event still in motion. The '
                'desk publishes it as developing rather than settled.">Developing</span>')
    outs = _independent_outlets(item)
    if item.get("verdict") == "VERIFIED" and len(outs) >= 2:
        return '<span class="badge verified">Verified</span>'
    if item.get("verdict") in ("NEEDS-HUMAN-REVIEW", "REVIEW"):
        return '<span class="badge review">Editor reviewed</span>'
    if outs:
        named = _bd_outlet((item.get("sources") or [{}])[0]) or outs[0].title()
        return f'<span class="badge dat">Reported \u00b7 {esc(named)}</span>'
    return ""


def verdict_badge(verdict, item=None):
    """The verdict, plus a developing flag when the story rests on a single outlet.

    Ported from the crypto desk 2026-08-17. The two labels say different things and both
    matter: "Verified" means the verifier checked the claims against the sources that
    existed, "Developing" means only one outlet has carried it yet. Showing only the first
    is the part that oversells, and an audit flagged reading "VERIFIED" directly above "no
    independent outlet had corroborated it" as a contradiction the reader has to reconcile.
    A story with corroboration is NOT developing whatever its citation count: the badge
    discloses resting on one outlet's word, not a thin sources list."""
    # UX-2: this used to emit the verdict AND a developing flag, which is how a card
    # ended up carrying two statuses that disagreed. It is now one call into
    # status_badge, which decides. The signature stays so the nine call sites do not
    # each have to change shape; where no item is available the verdict alone is used.
    if item is None:
        if verdict == "VERIFIED":
            return '<span class="badge verified">Verified</span>'
        if verdict in ("NEEDS-HUMAN-REVIEW", "REVIEW"):
            return '<span class="badge review">Editor reviewed</span>'
        return ""
    return status_badge(item)


def sig_block():
    """The desk's closing mark: an HONEST machine attestation. No anchor persona, no human
    editor implied: the mark states what was DONE to the story, never how the desk is built.
    Owner's call, 2026-07-30: the process is competitive advantage, so the caption no longer
    says "automated newsroom" and the attestation no longer points at a pipeline walkthrough.
    Signature reads Chuck Wando, the desk's byline.

    Anything added here must describe the story, not the machinery. What keeps a named
    byline honest is the standards page and the sources linked on the story itself."""
    return """<div class="sigrow">
  <div class="sig">
    <span class="sig-script">Chuck Wando</span>
    <span class="sig-cap">The GoCheckMySports Desk</span>
    <span class="sig-attest"><a href="/method.html" rel="nofollow">How we work</a></span>
  </div>
  <div class="stamp" role="img" aria-label="Sources verified, on the record stamp">
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle cx="60" cy="60" r="56" fill="none" stroke="currentColor" stroke-width="2"/>
      <!-- Stamp J (owner's pick, 2026-07-30): a solid accent disc fills the ring and the
           GoCheckMy check is knocked out of it, so the mark IS the seal rather than a small
           device sitting inside one. The knockout uses --card so it inverts with the theme;
           a hardcoded white would vanish into the dark-mode disc. This replaces the dashed
           inner ring, which the disc now occupies. -->
      <circle cx="60" cy="60" r="45" fill="currentColor"/>
      <defs><path id="stamparc" d="M60,60 m-51,0 a51,51 0 1,1 102,0 a51,51 0 1,1 -102,0"/></defs>
      <text font-size="9.4" letter-spacing="2.2" fill="currentColor"
        font-family="IBM Plex Mono,monospace" font-weight="600">
        <textPath href="#stamparc" startOffset="2%">SOURCES VERIFIED</textPath>
        <textPath href="#stamparc" startOffset="55%">ON THE RECORD</textPath>
      </text>
      <path d="M27 62 L49 85 L93 32" fill="none" stroke="var(--card)" stroke-width="11"
        stroke-linecap="round" stroke-linejoin="round"/>
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


def render_article(item, all_items=None, hubs=None):
    dateline = fmt_date(item.get("date"))
    badge = verdict_badge(item.get("verdict"), item)
    tag = f'<span class="tag">{esc(item.get("category","news"))}</span>' if item.get("category") else ""
    topic_chips = "".join(f'<span class="tag topic">{esc(t)}</span>' for t in display_tags(item))
    ribbon = ""
    if item.get("example"):
        ribbon = ('<div class="callout"><b>Example, not a real story.</b> This page shows the '
                  'format GoCheckMySports publishes in. The content is illustrative only.</div>')
    if item.get("superseded_by"):
        newer = next((i for i in (all_items or [])
                      if i.get("slug") == item["superseded_by"]), None)
        newer_title = newer.get("title") if newer else "the newest version"
        ribbon += (f'<div class="callout"><b>This story has been updated.</b> Read the '
                   f'latest version: <a href="/articles/{esc(item["superseded_by"])}.html">'
                   f'{esc(newer_title)}</a>.</div>')
    if item.get("continued_by") and not item.get("superseded_by"):
        later = next((i for i in (all_items or [])
                      if i.get("slug") == item["continued_by"]), None)
        later_title = later.get("title") if later else "our later story"
        ribbon += (f'<div class="callout"><b>There is a later development.</b> This story '
                   f'stands; the storyline continued in: '
                   f'<a href="/articles/{esc(item["continued_by"])}.html">'
                   f'{esc(later_title)}</a>.</div>')
    if item.get("update_of"):
        prev = next((i for i in (all_items or []) if i.get("slug") == item["update_of"]), None)
        prev_title = prev.get("title") if prev else "our earlier story"
        ribbon += (f'<div class="callout"><b>Update.</b> This story develops our earlier '
                   f'reporting: <a href="/articles/{esc(item["update_of"])}.html">'
                   f'{esc(prev_title)}</a>.</div>')
    # THE BOUNDARY PANEL sits ABOVE the prose, unlike every other panel on the page, because
    # it answers the only question a reader of a security advisory has before they will read
    # anything else: am I affected. Values are the vendor's own words, copied through the
    # pipeline by assignment (writer._carry_boundary) and never restated in prose, so there
    # is no sentence here that can come back inverted. See boundary.py.
    bnd = ""
    brows = boundary.rows(item.get("boundary") or {})
    if brows:
        lis = ""
        for label, value in brows:
            _is_url = str(value).strip().lower().startswith(("http://", "https://", "/"))
            cell = (f'<a href="{esc(value)}" rel="nofollow noopener">{esc(value)}</a>'
                    if label == "Advisory" and _is_url else esc(value))
            lis += f'<div class="brow"><dt>{esc(label)}</dt><dd>{cell}</dd></div>'
        bnd = (f'<section class="boundary" aria-labelledby="bnd-h">'
               f'<h2 id="bnd-h">Who this affects</h2>'
               f'<p class="mut">Quoted from the advisory linked below. The desk does not '
               f'restate it.</p><dl>{lis}</dl></section>')
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
        # SINGLE-SOURCE DISCLOSURE (owner directive 2026-07-31): when only one outlet has
        # carried a development, say so plainly beside the sourcing. This is a factual note
        # about THIS story, not process talk: a reader deserves to know a claim rests on one
        # outlet, and stating it is a credibility signal rather than an admission.
        note = ""
        import common as _cmn
        if _cmn.distinct_publishers([s.get("url", "") for s in srcs]) <= 1:
            note = (f'<p class="single-source"><b>Single-source report.</b> As published, '
                    f'only {esc(source_label(srcs[0]))} had reported this development. '
                    f'No independent outlet had corroborated it.</p>')
        also = item.get("also_reported_by") or []
        if also:
            names = ", ".join(esc(a.get("outlet", "")) for a in also[:4] if a.get("outlet"))
            note += (f'<p class="also-reported"><b>Also reported by</b> {names}. '
                     f'Independent coverage of the same development, found by search; '
                     f'not this story\'s sources.</p>')
        src_html = f'<div class="sources"><h2>Sources</h2><ol>{lis}</ol>{note}</div>'
    # Full coverage: a chapter of a hub-worthy storyline points the reader (and the
    # crawler) at the storyline's stable /coverage/ URL, above the related-stories
    # module. Two at most; a story is rarely honestly ABOUT more than two storylines.
    cov_html = ""
    if not item.get("example") and not item.get("superseded_by") and not _is_wrap(item):
        mine = [h for h in (hubs or []) if tracking_match(item, h["rx"])][:2]
        if mine:
            cov_html = ('<div class="tracking"><span class="lab">Full coverage</span>'
                        + "".join(f'<a class="chip" href="/coverage/{esc(h["slug"])}.html">'
                                  f'{esc(h["name"])}</a>' for h in mine)
                        + '</div>')
    rel_html = ""
    for rel in related_stories(item, all_items or []):
        rel_html += (f'<li><a href="/articles/{esc(rel["slug"])}.html">{esc(rel.get("title"))}</a>'
                     f'<span class="mut"> · {fmt_when(rel)}</span></li>')
    if rel_html:
        rel_html = f'<div class="related"><h2>Related stories</h2><ul>{rel_html}</ul></div>'
    # NO PER-STORY CHECK TRAIL. This used to render a "How this story was checked" block on
    # every article, naming the desk's automated verifier, its independent approver, and how
    # many cited pages were fetched live. That is the process, published once per story, and
    # it is removed for the same reason the method-page walkthrough was (owner's call,
    # 2026-07-30). The corrections path survives in the footer's standards link, which is
    # what that block's "Report an error" was for.
    trail = ""
    author = esc(item.get("author", "The GoCheckMySports Desk"))
    body = f"""<main class="wrap narrow">
  <article class="article">
    <div class="ey">{badge}{'<span class="badge update">Update</span>' if item.get("update_of") else ''}{tag}{topic_chips}<span class="dateline">{fmt_when(item)}</span></div>
    <h1>{esc(item.get("title"))}</h1>
    {f'<p class="dek">{esc(item["dek"])}</p>' if item.get("dek") else ""}
    <div class="byline">By {author}</div>
    {ribbon}
    {bnd}
    <div class="prose">{render_body(item.get("body"))}</div>
    {key}
    {take}
    {bottom}
    <p class="signoff">{esc(SLOGAN)}</p>
    {sig_block()}
    {share_row(ORIGIN + f"/articles/{item['slug']}", item.get("title") or "")}
    {trail}
    {src_html}
    {cov_html}
    {rel_html}
    <p class="nfa">{esc(NFA)}</p>
  </article>
</main>"""
    title = f'{item.get("title")} - {NAME}'
    desc = item.get("dek") or (item.get("body", [""])[0] if item.get("body") else DESC)
    url = f"{ORIGIN}/articles/{item['slug']}.html"
    # Per-article share card, written earlier in build() by _render_og_card. Checked on
    # disk rather than assumed, because that render is fail-open: if it was skipped the
    # article falls back to the site-wide card instead of pointing at a 404.
    card_out = os.path.join(PUBLISH, "og", f"{item['slug']}.png")
    og_image = f"{ORIGIN}/og/{item['slug']}.png" if os.path.exists(card_out) else OG_IMAGE
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "NewsArticle", "headline": item.get("title"),
         "description": item.get("dek") or "", "url": url, "mainEntityOfPage": url,
         "image": og_image,
         "datePublished": item.get("published_utc") or item.get("date"),
         "dateModified": item.get("published_utc") or item.get("date"),
         "author": {"@type": "Organization", "name": NAME, "url": ORIGIN + "/news.html"},
         # ONE PUBLISHER IDENTITY (crawl audit 2026-08-25): the article names the same
         # @id the homepage Organization block defines, so a crawler resolves both to
         # one entity instead of reading a fresh Organization on every page.
         "publisher": {"@id": ORIGIN + "/#publisher"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Latest", "item": ORIGIN + "/news.html"},
            {"@type": "ListItem", "position": 2, "name": item.get("title"), "item": url}]}
    ]}, ensure_ascii=False)
    return shell(title, desc if isinstance(desc, str) else DESC, "Latest", body, dateline.upper(),
                 path=f"/articles/{item['slug']}.html", noindex=bool(item.get("example")),
                 og_type="article", og_image=og_image,
                 schema_extra=f'\n<script type="application/ld+json">{schema}</script>')


# ---- cards / index / archive -------------------------------------------------

def _ends_sentence(t):
    return bool(re.search(r"[.!?][\"\u2019\u201d)]*$", (t or "").strip()))


def dek_for(item, limit):
    """UX-11: the card's line, ending at a sentence. The desk writes four fields that
    can serve as one, and a brief's dek is sometimes a single 400-character sentence
    that no limit can end cleanly; rather than cut it, the card takes the first of the
    four that does end at a sentence inside the limit. Only when none does is a cut
    made, which is the case the audit's ellipsis rule cannot avoid."""
    cands = [item.get("dek"), item.get("key_fact"), item.get("bottom_line")]
    body = item.get("body") or []
    if body:
        b = body[0]
        cands.append(b.get("h2") if isinstance(b, dict) else b)
    for c in cands:
        if not c:
            continue
        t = clamp_sentences(str(c), limit)
        if _ends_sentence(t):
            return t
    for c in cands:
        if c:
            return clamp_sentences(str(c), limit)
    return ""


def card(item, drop=()):
    """UX-15 (S-14). `drop` is the tag a page already is. On /sections/nfl every card
    carried an "nfl" chip, which tells the reader where they already are and spends the
    two chips a card has on nothing; the chips go to the tags that add something."""
    badge = verdict_badge(item.get("verdict"), item)
    skip = {str(d).lower() for d in (drop or ())}
    cat = item.get("category")
    tag = (f'<span class="tag">{esc(cat)}</span>'
           if cat and str(cat).lower() not in skip else "")
    topics = [t for t in display_tags(item) if str(t).lower() not in skip]
    tag += "".join(f'<span class="tag topic">{esc(t)}</span>' for t in topics[:2])
    href = f'/articles/{esc(item["slug"])}.html'
    summ = dek_for(item, 180)
    nsrc = len(item.get("sources") or [])
    return f"""<article class="card">
  <div class="row">{badge}{tag}</div>
  <h3><a href="{href}">{esc(item.get("title"))}</a></h3>
  <p class="summary">{esc(summ)}</p>
  <div class="foot"><span class="dateline">{fmt_when(item)}</span>
    <span class="src">{nsrc} source{"s" if nsrc != 1 else ""}</span></div>
</article>"""


def desk_strip():
    # Desk strip: the desk line beneath the masthead, text only (the chassis this repo was
    # cloned from put an anchor-portrait video here; sports runs a single brand, no mascot).
    return f"""<section class="desk" aria-label="About this desk"><div class="wrap">
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


# UX-5 (S-5): WHAT LEADS THE HOMEPAGE.
#
# On an NFL Thursday with a game that night the page led with Formula 1's 2027
# calendar. It was the newest verified story, and newest-verified was the whole rule.
#
# lead value = league weight for today x recency x verification, and verification is
# the FLOOR rather than a term: a story the verifier did not clear cannot lead however
# big it is. The league weight comes from the calendar, because what a reader came for
# on a Thursday in September is not what they came for on a Tuesday in March.
LEAGUE_WEIGHT = {
    # league: (base, {ET weekday: weight}); Monday is 0, Sunday is 6.
    "NFL":    (1.6, {3: 4.0, 6: 4.5, 0: 3.5}),      # Thu, Sun, Mon in season
    "CFB":    (1.2, {5: 3.5, 4: 1.6}),              # Saturday, and Thursday night games
    "MLB":    (1.3, {}),                            # lifted in the pennant race below
    "NBA":    (1.2, {}),
    "NHL":    (1.1, {}),
    "WNBA":   (1.0, {}),
    "Soccer": (1.0, {}),
}


_DAY_SLATE = None


def _day_slate(now=None):
    """E-1: what is actually being played today, per league, from the board.

    Returns {league: (games, started)} or {} when the board did not answer, which is
    the signal to fall back on the table alone.

    Today is the board's own day in Eastern, which is the day the reader is having.
    """
    global _DAY_SLATE
    if _DAY_SLATE is not None:
        return _DAY_SLATE
    now = now or _build_now()
    today = now.astimezone(_ET).date()
    out = {}
    for lg in ((SB_DATA or {}).get("leagues") or []):
        key = (lg.get("league") or "").upper()
        gs = lg.get("games") or []
        if not key or not gs:
            continue
        n = started = 0
        for g in gs:
            k = _utc_dt(g.get("start_utc") or "")
            if not k:
                continue
            # THE BOARD IS NOT A DAY. Each league's endpoint answers with its own
            # window: on a Monday morning the NFL board carries the whole week (one
            # game on the 17th, fourteen on the 20th, one tonight), the college board
            # carries NEXT weekend, and the NBA board carries a game in October.
            # Counting what the board returned would have made Saturday's college
            # slate the story on a Monday, which is worse than the calendar this is
            # replacing.
            #
            # A game counts when it is today in Eastern, or when it finished recently
            # enough to still be today's news: last night's baseball is what a desk
            # writes about this morning, and the board will not call it today.
            if k.astimezone(_ET).date() == today:
                n += 1
                if g.get("state") in ("in", "post"):
                    started += 1
            elif (g.get("state") == "post"
                  and 0 <= (now - k).total_seconds() / 3600 <= RECENT_FINAL_HOURS):
                n += 1
                started += 1
        if n:
            out[key] = (n, started)
    _DAY_SLATE = out
    return out


def _league_weight(league, now=None):
    """Today's weight for a league.

    E-1: THE DAY IS MEASURED, NOT LOOKED UP. The weekday table below is a calendar kept
    by hand: it gives the NFL 4.5 on a Sunday in June, when there is no NFL, and holds
    college football at 3.5 every Saturday including the ones in March. This desk has
    already learned three times that a hand-kept list is stale in both directions, and
    the correction each time was to measure the thing instead.

    The board is the measurement, and it is already on disk. A league with fifteen games
    today is having its day whatever the calendar thinks; a league with none is not,
    however good its Sunday usually is.

    The table is still the prior, because "how much does a sports reader care about this
    league at all" is a judgement and not a count, and a league with two games can still
    be the wrong lead. What the slate does is stop the calendar asserting a day that is
    not happening, and let one that is happening through.

    The lift saturates at eight games: a fifteen-game Sunday is not twice the day a
    seven-game one is, and without a ceiling the biggest slate would always lead no
    matter what was on it.

    When the board is unavailable the table stands alone, unchanged, which is the same
    fail-safe every other surface here keeps.
    """
    now = now or _build_now()
    et = now.astimezone(_ET)
    key = (league or "").upper() if league else ""
    base, byday = LEAGUE_WEIGHT.get(key, (1.0, {}))
    w = byday.get(et.weekday(), base)
    if key == "MLB" and et.month in (9, 10):
        w = max(w, 2.6)

    slate = _day_slate(now)
    if slate:
        n, started = slate.get(key, (0, 0))
        if n == 0:
            # The calendar claimed this league's day and nothing is being played. The
            # prior is cut to the base rather than to zero: a league can be the story
            # on a day it does not play, and often is.
            w = min(w, base)
        else:
            lift = 1.0 + (min(n, 8) / 8.0) * 1.6
            w = max(w, base * lift)
            if started:
                # A game that has kicked off produces news; a slate still hours away
                # has produced none yet.
                w *= 1.12
    return w


_TEAM_VOCAB = None


def _team_vocab():
    """A-5: the teams each league actually has, for checking a tag against a story.

    Nicknames are not usable here (half the NFL's are ordinary English), so the NFL
    vocabulary is full names from the schedule file and the college one is school
    names from the colour table. A name shorter than five characters is left out: "UCF"
    and "Duke" are fine as evidence and "Navy" and "Rice" are not, and the cost of
    dropping a few is a check that never fires wrongly.
    """
    global _TEAM_VOCAB
    if _TEAM_VOCAB is not None:
        return _TEAM_VOCAB
    v = {"NFL": set(), "CFB": set()}
    for _a, t in ((TEAM_DATA or {}).get("teams") or {}).items():
        n = (t.get("name") or "").strip()
        if len(n) >= 5:
            v["NFL"].add(n)
    try:
        tc = json.load(open(os.path.join(HERE, "site", "data", "team-colors.json"),
                            encoding="utf-8"))
        for _a, t in (tc.get("college-football") or {}).items():
            n = (t.get("name") or "").strip()
            if len(n) >= 5:
                v["CFB"].add(n)
    except Exception:
        pass
    # A school that is also an NFL city name is evidence for neither.
    both = v["CFB"] & {n.rsplit(" ", 1)[0] for n in v["NFL"]}
    v["CFB"] -= both
    _TEAM_VOCAB = v
    return v


def _league_from_teams(item):
    """The league the story's own teams belong to, or "" when they do not agree.

    A story tagged both nfl and college, naming Vanderbilt and NC State, led the desk
    grid as NFL on an NFL Sunday. The teams in the headline are the better evidence
    than either tag, and where they are unambiguous they win.
    """
    v = _team_vocab()
    # FAIL CLOSED. The college list is only safe once the NFL list has been subtracted
    # from it: without the schedule file loaded there is no NFL vocabulary, "Buffalo"
    # stays in the college set, and a Bills story would read as college football. No
    # NFL names, no check.
    if not v["NFL"]:
        return ""
    claim = " ".join([item.get("title") or "", item.get("dek") or ""])
    # A SINGLE ONE-WORD NAME IS NOT EVIDENCE. The college vocabulary has 639 schools in
    # it and some are ordinary words and ordinary first names: a romance-scam story
    # about a fake 49ers player was filed as COLLEGE FOOTBALL because its dek named a
    # suspect "Taylor Chan" and there is a Taylor University. That is the fourth time
    # this desk has been bitten by a matcher that one shared token can satisfy, after
    # RECURRING_ACTORS, the date-stamp trap and the supersede floor, and the rule each
    # time is the same: the floor comes from the structure, never from a list kept by
    # hand.
    #
    # The structure here is the name itself. "Ohio State", "Texas A&M" and "NC State"
    # cannot be anything else; "Taylor", "Buffalo" and "Miami" can be almost anything.
    # So a multi-word name stands on its own, and a one-word name needs a second name
    # from the same league to corroborate it.
    hits = {}
    for lg, names in v.items():
        found = [n for n in names if re.search(r"\b" + re.escape(n) + r"\b", claim)]
        if not found:
            continue
        if any(" " in n for n in found) or len(set(found)) >= 2:
            hits[lg] = len(found)
    live = list(hits)
    return live[0] if len(live) == 1 else ""


def display_tags(item):
    """A-5: the tags a card SHOWS, with a league tag the story's own teams contradict
    removed. The desk tagged a Vanderbilt at NC State recap both nfl and college, and
    the grid printed the nfl chip on an NFL Sunday. The teams in the headline are the
    better evidence, and where they are unambiguous the chip that disagrees comes off.
    Nothing is added: a story with no evidence keeps exactly the tags it had."""
    tags = list(tags_for(item))
    lg = _league_from_teams(item)
    if not lg:
        return tags
    wrong = {k.lower() for k in LEAGUE_WEIGHT} - {lg.lower()}
    kept = [t for t in tags if t.lower() not in wrong] or tags
    # and where the story already carries the right league, it leads: a card that has
    # just lost its "nfl" chip should say "college", not fall back to a generic tag.
    right = [t for t in kept if t.lower() in (lg.lower(), "college")]
    return (right + [t for t in kept if t not in right]) if right else kept


# E-1: THE DESK'S TAGS AND THE WEIGHT TABLE'S KEYS WERE NEVER CONNECTED. The desk
# writes "college"; the scoreboard, and therefore the weight table, says "CFB". So a
# correctly tagged college story could not resolve to a league at all, the scan fell
# through to whatever other league tag happened to be on it, and a Senate bill about
# college sports, tagged college and nhl, read as ICE HOCKEY and was weighted as such.
#
# Only aliases belong here. This is a spelling table, not a judgement about what a story
# is about: that question is A-5's, and the teams a story names still outrank every tag.
TAG_LEAGUE = {
    "college": "CFB", "ncaaf": "CFB", "college-football": "CFB", "cfb": "CFB",
    "football": "NFL", "baseball": "MLB", "basketball": "NBA", "hockey": "NHL",
    "ncaa": "CFB", "wnba": "WNBA", "soccer": "Soccer", "futbol": "Soccer",
}


def _story_league(item):
    """The league a story belongs to, from its own field or its tags."""
    lg = (item.get("league") or "").upper()
    if lg:
        return lg
    # A-5: the teams the story names outrank a tag that disagrees with them.
    byteam = _league_from_teams(item)
    tags = [t.upper() for t in tags_for(item)]
    if byteam and byteam not in tags[:1]:
        return byteam
    for t in tags:
        # tags arrive upper-cased from the line above; the alias table is keyed in the
        # spelling the desk writes. Lower-casing the lookup, not the table, keeps the
        # table readable as the desk's own vocabulary.
        t = TAG_LEAGUE.get(t.lower(), t)
        if t in LEAGUE_WEIGHT:
            return t
    return ""


def lead_value(item, now=None):
    """UX-5. Zero for anything the verifier did not clear: that is the floor."""
    if item.get("verdict") != "VERIFIED":
        return 0.0
    now = now or _build_now()
    hours = _fresh_hours(item, now)
    if hours is None:
        return 0.0
    # Recency decays by half every twelve hours, so a good story from this morning
    # still beats a better one from two days ago, and nothing from last week leads.
    recency = 0.5 ** (max(hours, 0.0) / 12.0)
    return _league_weight(_story_league(item), now) * recency


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
    stories = [i for i in (items or []) if not i.get("example") and not _is_wrap(i)
               and not i.get("superseded_by")]
    breaking = False
    if stories:
        freshest = min(stories, key=lambda i: _fresh_hours(i, now))
        # BREAKING requires the EVENT to be fresh, not just the publish (owner
        # directive 2026-07-27: a Friday ruling posted Monday is never Breaking).
        # event_utc is stamped at ingest from the story's wire timestamp; a story
        # without one can never carry the label.
        def _event_fresh(story):
            try:
                ev = datetime.datetime.fromisoformat(
                    (story.get("event_utc") or "").replace("Z", "+00:00"))
                return (now - ev).total_seconds() <= 12 * 3600
            except Exception:
                return False
        if _fresh_hours(freshest, now) <= BREAKING_HOURS and _event_fresh(freshest):
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
    # EDITIONS STALENESS (owner directive 2026-07-27): an edition older than 24 hours
    # is never featured; the module collapses instead of presenting old synthesis as
    # current. The /bottom-line archive keeps every edition.
    if anchor is not None and _fresh_hours(anchor, now) > 24:
        anchor = None
    return stories, breaking, anchor


# ---- the live layer (owner directive 2026-07-20) ----------------------------------

SCORES_PATH = os.path.join(HERE, "site", "data", "scores.json")
# WHICH LEAGUES THE BROWSER MAY REFRESH IN PLACE. Must stay in step with
# scores_pulse.LEAGUES, but it is deliberately NOT the same list: SCORES_JS understands
# exactly two payload shapes, ESPN's events[].competitions[].competitors and MLB's
# dates[].games[]. Tennis is neither. ESPN hangs a tournament's matches off
# events[].groupings[], so a tennis feed here would match no card, and worse, retire()
# would then strip the live styling from every tennis card on the rail because none of
# them appeared in the "seen" set. Baked values are correct and update every run; a
# tennis card simply does not self-refresh between builds. UFC is out for the same
# reason: a fight card is one event holding many bouts, so events[].competitions[0] is
# only ever the first fight.
_CLIENT_FEEDS = {
    "MLB": "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=team,linescore",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "CFB": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "CBB": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
    "WCBB": "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard",
    "WNBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "EPL": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
    "La Liga": "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard",
    "Serie A": "https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard",
    "Bundesliga": "https://site.api.espn.com/apis/site/v2/sports/soccer/ger.1/scoreboard",
    "UCL": "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard",
    "MLS": "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
}

# H-7 (2026-09-16): THE SCORES STRIP IS DELETED, with SCORES_JS and SCORES_AGE_JS.
#
# It was the homepage's fallback when the scoreboard snapshot aged past six hours: the
# band withdrew and this rendered instead, captioned "League data, not news · as of
# ...". Two things were wrong with that. The caption is a sentence about the site, which
# C-L1 removes. And a reader who meets one component at 8 AM and a different one at
# 8 PM learns nothing from the swap; they cannot even tell that what they are looking
# at is old.
#
# L-4 is the opposite rule and it is the one that holds: stale data renders, with its
# own stamp and a stale mark. scoreboard.load() now returns the snapshot with
# stale: true instead of None, the band renders it, and the stamp says
# "Updated 7:57 AM ET · stale". The live poll (L-3) then updates it in place the moment
# the source answers, which is the thing the strip could never do.
#
# Removed here rather than left unreferenced: about 200 lines of generator and two
# inline scripts that no page called any more.

_BL_GUARD_SCRIPT = (
    '<script>(function(){var b=document.querySelector("[data-bl-published]");'
    'if(!b)return;var t=Date.parse(b.getAttribute("data-bl-published"));'
    'if(isNaN(t)||Date.now()-t<=864e5)return;'
    'b.setAttribute("href","/bottom-line.html");'
    'var s=b.querySelector(".hero-bl-src");if(s)s.textContent="The daily reads";'
    'var r=b.querySelector(".hero-bl-read");if(r)r.textContent='
    '"The next edition is on the way. Catch up on the archive of the desk\u2019s daily reads.";'
    'var m=b.querySelector(".hero-bl-more");if(m)m.innerHTML="The Bottom Line archive &rarr;";'
    '})();</script>')


def _bl_fresh_label(ed, name):
    """Honest label when the band shows a previous day's edition."""
    ed_date = (ed.get("published_utc") or "")[:10]
    build_date = _build_now().date().isoformat()
    if ed_date and ed_date < build_date:
        import datetime as _dt
        days = (_dt.date.fromisoformat(build_date) - _dt.date.fromisoformat(ed_date)).days
        return ("Yesterday's " + name) if days == 1 else (name + " · " + esc(fmt_date(ed_date)))
    return name


def bottom_line_card(items):
    """THE BOTTOM LINE (owner directive 2026-07-15): the desk's signature element, the
    newest edition's 3-5 sentence read, refreshed every slot (and by breaking runs).
    Rendered as the compact card that rides beside the lead story (owner directive
    2026-07-17: lead first, Bottom Line to its right, same arrangement as the front
    page), reusing the home hero's card styling."""
    _, _, ed = home_stack(items)  # daypart anchor; falls back to newest edition
    if ed is None:
        return ""
    name = _bl_fresh_label(ed, esc((ed.get("title") or "").split(":")[0].strip()
                                   or "The Daily Edition"))
    return (f'<a class="hero-bl news-bl" data-bl-published="{esc(ed.get("published_utc") or "")}" '
            f'href="/articles/{esc(ed["slug"])}.html">'
            f'<span class="hero-kick"><span class="kicker">The Bottom Line</span></span>'
            f'<span class="hero-bl-src">{name} · {_blink_when(ed)}</span>'
            f'<span class="hero-bl-read">{esc(ed["bottom_line"])}</span>'
            f'<span class="hero-bl-more">Read the full edition &rarr;</span></a>'
            + _BL_GUARD_SCRIPT)


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
  <p class="lede">Once a day the desk closes its edition with The Bottom Line: what
     happened, why it mattered, and what the calendar says comes next. Synthesis of the
     desk's verified reporting, never a prediction and never advice. Every read is kept.</p>
  {"".join(rows) if rows else '<p class="lede">The first edition lands soon.</p>'}
  <p class="nfa">{esc(NFA)}</p>
</section></main>"""
    return shell(f"The Bottom Line - {NAME}", "The desk's daily reads: what happened, why it "
                 "mattered, and what comes next. Synthesis, never advice.",
                 "The Bottom Line", body, dateline, path="/bottom-line.html")


def render_news(items, dateline):
    # superseded chapters live on only through their own page's forward pointer; the
    # news list and archive show one entry per story, exactly like the homepage
    live = [i for i in items if not i.get("example") and not i.get("superseded_by")]
    bl = bottom_line_card(live)
    live = [i for i in live if not _is_wrap(i)]  # editions speak through the Bottom Line card
    if live:
        lead = live[0]
        rest = live[1:]
        badge = verdict_badge(lead.get("verdict"), lead)
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
                '<p style="margin:.6em 0 0">Every story here will have been ranked for significance, '
                'checked against its sources by an independent verification pass, and held if it '
                'fails that check. '
                'That gate is the whole point, so we would rather publish nothing than publish junk.</p>'
                '</div></div></section>')
    # news first: lead story (Bottom Line beside it), then the rest of the day's stories;
    # the promise strip and the newsletter read as the footer beats, never above the
    # journalism; the desk strip is secondary chrome; the news itself is the main landmark
    body = (desk_strip() + '<main class="news-main">' + lead_html + grid
            + trust_block() + '</main>')
    return shell(f"Latest news - {NAME}", DESC, "Latest", body, dateline, path="/news.html")



def home_schema():
    """Organization + WebSite for the homepage.

    Article pages have carried NewsArticle and BreadcrumbList since launch and /news now
    carries CollectionPage, but the HOMEPAGE, the page a crawler reaches first and the one
    that should establish who publishes everything else, emitted no structured data at all
    (crawl audit 2026-08-25). The publisher block here is the same identity the article
    schema names, so the two agree."""
    org = {"@type": "NewsMediaOrganization", "@id": ORIGIN + "/#publisher",
           "name": FAMILY, "url": ORIGIN + "/",
           "logo": {"@type": "ImageObject", "url": ORIGIN + "/og-image.png"},
           "description": FAMILY_DESC}
    site = {"@type": "WebSite", "@id": ORIGIN + "/#website", "url": ORIGIN + "/",
            "name": FAMILY, "publisher": {"@id": ORIGIN + "/#publisher"}}
    return ('<script type="application/ld+json">'
            + json.dumps({"@context": "https://schema.org", "@graph": [org, site]},
                         ensure_ascii=False) + "</script>")

# EVERGREEN PICKS (newsroom work order 2026-09-12). The homepage linked the newest
# stories and the editions; nothing linked the desk's best work, so an article's only
# inbound link was a related-stories slot on a page nobody crawls either. This is the
# curated set: 25 articles linked directly from the front door with their own headlines as
# anchor text.
#
# "Best" is scored from what the desk already records rather than invented, because this
# desk has no quality score and making one up is how a ranking starts lying. Four signals,
# all of them proxies for SEARCH SHELF-LIFE, which is the thing the work order actually
# asks for:
#   - sources: a story checked against four sources outlives one checked against one
#   - depth: body length, which separates a real piece from a two-paragraph recap
#   - lineage: a story other stories update is a running subject, not a result
#   - subject: contracts, lawsuits, broadcast rights and governance keep being searched;
#     a final score is searched on the night and never again
# A pure recap is demoted hard, which is the whole point: those are the pages that decay.
_EVERGREEN_SUBJECT = re.compile(
    r"\b(contract|extension|trade|lawsuit|sue[sd]?|court|ruling|settle\w*|fine[sd]?|"
    r"suspend\w*|ban\w*|broadcast\w*|media rights|streaming|tv deal|sold|sale|"
    r"acquire\w*|ownership|stake|commissioner|governance|eligibility|policy|rule change|"
    r"how to watch|schedule|expansion|realign\w*|salary cap|revenue)\b", re.I)


def evergreen_picks(items, n=25):
    live = [i for i in items
            if not i.get("example") and not i.get("superseded_by") and not _is_wrap(i)]
    scored = []
    for it in live:
        body = it.get("body") or []
        words = sum(len(str(b).split()) for b in body)
        srcs = len(it.get("sources") or [])
        blob = " ".join([it.get("title") or "", it.get("dek") or "", it.get("key_fact") or ""])
        tags = set(tags_for(it))
        score = 0.0
        score += min(srcs, 5) * 2.0                      # corroboration, capped
        score += min(words / 250.0, 4.0)                 # depth, capped
        if it.get("continued_by") or it.get("update_of"):
            score += 3.0                                 # a running subject
        if _EVERGREEN_SUBJECT.search(blob):
            score += 4.0                                 # searched for months
        if tags == {"scores-results"} or (
                "scores-results" in tags and words < 200):
            score -= 6.0                                 # a result, searched for a night
        scored.append((score, it.get("published_utc") or "", it))
    scored.sort(key=lambda t: (-t[0], t[1]), reverse=False)
    # One per subject line, so the module does not spend six of its slots on one saga.
    picked, seen = [], set()
    for _sc, _when, it in scored:
        key = frozenset(w for w in _subject_words(it.get("title") or "") if w)
        if any(len(key & k) >= 2 for k in seen):
            continue
        seen.add(key)
        picked.append(it)
        if len(picked) >= n:
            break
    return picked


def _bd_outlet(src):
    """Just the outlet: "Reuters", not "Reuters: the whole headline". source_label is
    built for a citation list under an article and returns the article title; a card
    footer needs the masthead name and nothing else."""
    from urllib.parse import urlparse
    url = (src.get("url") if isinstance(src, dict) else src) or ""
    if not isinstance(url, str) or not url.startswith("http"):
        name = (src.get("name") or src.get("outlet") or "") if isinstance(src, dict) else ""
        return name.strip()
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host in OUTLETS:
        return OUTLETS[host]
    bare = host.removesuffix(".com").removesuffix(".org").removesuffix(".io")
    return bare.rsplit(".", 1)[-1].replace("-", " ").title() if bare else ""


# ---- S1: the receipts ledger --------------------------------------------------
# Artboard 4 module 3. The lead story's checkable figures, each with the source the
# story attributes it to and a status badge.
#
# WHERE THE ROWS COME FROM, and what stops this being decoration. Content files carry
# no per-claim source mapping: `sources` is a story-level list and `verification` is a
# story-level verdict. So a naive ledger would print every figure against every source
# and imply an attribution nobody made.
#
# What makes it real is that this desk attributes inline. Measured across 460 live
# stories: 415 carry an inline "per X" or "according to X", 224 carry two or more
# checkable figures, and 207 carry both. When the outlet named beside a figure matches
# one of the story's cited sources, that IS a claim-to-source link the story itself
# asserted, and the ledger reports it rather than inventing one.
#
# A story that does not clear that bar gets no ledger. Per S1: "a story without
# checkable figures does not get a ledger."

# Money, large counts, percentages, scorelines, and measured quantities.
_FIG_RX = re.compile(
    r"(\$[\d,.]+(?:\s?(?:million|billion|trillion|m|bn))?"
    r"|\b\d{1,3}(?:,\d{3})+\b"
    r"|\b\d+(?:\.\d+)?\s?(?:%|percent)"
    r"|\b\d+-\d+\b"
    r"|\b\d+(?:\.\d+)?[ -]?(?:yards|points|games|weeks|days|years|seasons)\b)", re.I)

# A figure the desk worked out rather than quoted. Narrow on purpose: these are the
# phrases that state a derivation in the sentence itself, so the Calculated badge is
# never a guess about provenance.
_DERIVED_RX = re.compile(
    r"\b(average|averages|averaging|per year|annually|per game|combined|in total|"
    r"altogether|works out to|amounts to|equivalent to|effectively|a rate of)\b", re.I)

_ATTR_RX = re.compile(r"\b(?:per|according to|reported by|told|via|cited by)\s+"
                      r"([A-Z][A-Za-z.'&\-]*(?:\s+[A-Z][A-Za-z.'&\-]*){0,3})")


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _receipt_rows(item, cap=4):
    """One row per checkable figure, with the source the story attributes it to."""
    srcs = [s for s in (item.get("sources") or []) if isinstance(s, dict)]
    if not srcs:
        return []
    names = {(s.get("title") or "").strip(): s for s in srcs if s.get("title")}
    blob = [item.get("key_fact") or ""] + [str(b) for b in (item.get("body") or [])[:5]]
    rows, seen = [], set()
    carry = None                       # the last outlet named, for a following sentence
    for sent in _sentences(" ".join(blob)):
        a = _ATTR_RX.search(sent)
        if a:
            cand = a.group(1).strip(" .,")
            # Only accept an outlet the story actually cites. "per a source" and
            # "according to head coach Dan Campbell" are not sources in this sense.
            for nm in names:
                if nm.lower() in cand.lower() or cand.lower() in nm.lower():
                    carry = nm
                    break
        figs = _FIG_RX.findall(sent)
        if not figs:
            continue
        fig = figs[0]
        key = fig.lower().replace(",", "")
        if key in seen:
            continue
        seen.add(key)
        derived = bool(_DERIVED_RX.search(sent))
        # Punch item 9 / the standing law: a receipt is a quotation of the story, so it
        # is never cut. A sentence too long to show is SKIPPED and the next candidate
        # takes its place; an ellipsis in a receipt reads as the desk trailing off in the
        # middle of the evidence.
        if len(sent) > 128:
            continue
        claim = sent
        src_name = carry or (srcs[0].get("title") or "")
        rows.append({
            "claim": claim,
            "source": ("Derived in the story from figures above" if derived
                       else src_name),
            "derived": derived,
            "url": (names.get(src_name) or srcs[0]).get("url") or "",
        })
        if len(rows) >= cap:
            break
    return rows


def _breaking_badge(item, hours=BREAKING_HOURS):
    """S-16. BREAKING expires. The audit found the badge on a story published the
    previous day; it had been rendered unconditionally by the photo band that S-2
    retired, so for a while no card carried it at all.

    The badge is bounded twice, and both bounds already existed for choosing the lead:
    the story must be under BREAKING_HOURS old (3, inside the audit's 6), and its EVENT
    must be within 12 hours (owner directive 2026-07-27: a Friday ruling posted Monday
    is never Breaking). After that the card shows its verdict badge alone."""
    if not item:
        return ""
    now = _build_now()
    if _fresh_hours(item, now) > hours:
        return ""
    try:
        ev = datetime.datetime.fromisoformat(
            (item.get("event_utc") or "").replace("Z", "+00:00"))
    except Exception:
        return ""
    if (now - ev).total_seconds() > 12 * 3600:
        return ""
    return '<span class="badge breaking">Breaking</span>'


def receipts_ledger(item, max_rows=2):
    """S-4 / punch item 9: the receipts STRIP, two rows, each one line, nothing cut.

    This was a four-row table in three columns, which squeezed the claim to 246px - about
    31 characters - so every real claim wrapped and was then cut mid-sentence
    ("membership valid...", "tournament, with..."). The claims are EXTRACTED from the
    story, so they cannot be authored shorter and must not be truncated.

    The board settles the shape: two rows, a plain label with a hairline over them, and
    claims that WRAP to two lines complete rather than being cut to one. Selection is the
    only lever the data allows, so it takes the two most compact claims. The live claims
    run 77 to 127 characters against about 51 that fit one line at this width, so one
    line per row is not achievable from extracted sentences without cutting them, and
    cutting them is the thing this fixes.
    """
    rows = _receipt_rows(item)
    if not rows:
        return ""
    verified = (item.get("verdict") or "").upper() == "VERIFIED"
    # Two rows, and the two most compact ones, because a receipt is a fact and the
    # shortest statement of it is the best one on a card. The claims are EXTRACTED from
    # the story, not authored here, so they are never rewritten and never cut - they
    # wrap, exactly as they do on the board.
    shown = sorted(rows, key=lambda r: len(" ".join(str(r["claim"]).split())))[:max_rows]
    head = (f'<div class="sp-strip-head"><span class="bd-label">Sources</span>'
            f'<span class="bd-src">{len(rows)} of {len(rows)} '
            f'{"verified" if verified else "reported"}</span></div>')
    out = [f'<div class="sp-ledger sp-strip">', head]
    for r in shown:
        badge = ('<span class="bd-badge calc">Calculated</span>' if r["derived"]
                 else ('<span class="bd-badge ok">Verified</span>' if verified
                       else '<span class="bd-badge dat">Reported</span>'))
        src = esc(r["source"])
        if r["url"] and not r["derived"]:
            src = f'<a href="{esc(r["url"])}" rel="nofollow">{src}</a>'
        out.append(f'<div class="sp-strip-row"><span class="sp-claim">'
                   f'{esc(" ".join(str(r["claim"]).split()))}</span>'
                   f'<span class="bd-src">{src}</span>{badge}</div>')
    out.append("</div>")
    return "".join(out)


def fig_money(v):
    """UX-18 (S-19). One format for a money figure in a chip. The desk was printing the
    figures as each story happened to write them, so one chip read "$81 million ·
    $13.5M": two spellings of the same unit, side by side, which makes a reader check
    whether they are the same kind of number. The value is never changed, only its
    spelling, and a figure that carries a decimal keeps it."""
    def trim(x):
        t = f"{x:.1f}"
        return t[:-2] if t.endswith(".0") else t
    a = abs(v)
    if a >= 1e12:
        return f"${trim(v / 1e12)}T"
    if a >= 1e9:
        return f"${trim(v / 1e9)}B"
    if a >= 1e6:
        return f"${trim(v / 1e6)}M"
    if a >= 1e3:
        return f"${trim(v / 1e3)}K"
    return f"${v:,.0f}"


def _usd(fig):
    """Parse "$18.75 million" to a number, or None when it is not money."""
    m = re.match(r"\$([\d,.]+)\s*(million|billion|trillion|m|bn)?$", fig.strip(), re.I)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "trillion": 1e12}
    return v * mult.get((m.group(2) or "").lower(), 1)


def receipts_chart(item):
    """Artboard 4 module 3, right column: the two largest comparable money figures in
    the ledger, as two bars. Two figures of the same unit are the only pair that can
    honestly share an axis, so a story without them gets no chart rather than a chart
    comparing yards to dollars."""
    rows = _receipt_rows(item, cap=8)
    vals = []
    for r in rows:
        for f in _FIG_RX.findall(r["claim"]):
            v = _usd(f)
            if v:
                vals.append((v, f, r["claim"]))
                break
    uniq, seen = [], set()
    for v, f, c in sorted(vals, key=lambda t: -t[0]):
        if v in seen:
            continue
        seen.add(v)
        uniq.append((v, f, c))
    if len(uniq) < 2:
        return ""
    (v1, f1, c1), (v2, f2, c2) = uniq[0], uniq[1]
    W, BH = 300, 14
    w1 = W - 60
    w2 = max(6, round(w1 * (v2 / v1)))

    def lab(c):
        return (c.split(":")[0] if ":" in c[:40] else c.split(",")[0])[:38]
    return (
        '<div class="bd-card sp-chart"><span class="bd-eyebrow">The receipts, charted</span>'
        f'<div class="bd-h3" style="font-size:18px">{esc(lab(c1))}</div>'
        f'<svg width="{W}" height="86" viewBox="0 0 {W} 86" role="img" '
        f'aria-label="{esc(f1)} against {esc(f2)}." style="max-width:100%">'
        f'<rect x="0" y="10" width="{w1}" height="{BH}" rx="4" fill="var(--rule)"></rect>'
        f'<text x="{w1 + 8}" y="{10 + BH - 2}" font-family="var(--mono)" font-size="11.5" '
        f'fill="var(--muted)">{esc(f1)}</text>'
        f'<rect x="0" y="48" width="{w2}" height="{BH}" rx="4" fill="var(--rule)" '
        f'opacity="0.55"></rect>'
        f'<text x="{w2 + 8}" y="{48 + BH - 2}" font-family="var(--mono)" font-size="11.5" '
        f'fill="var(--muted)">{esc(f2)}</text></svg>'
        f'<p class="bd-src">Both figures as the story reports them, drawn to the same '
        f'scale.</p></div>')


# ---- S2: Where to Watch -------------------------------------------------------
# Artboard 4 module 4. The week's windows and the carrier that shows each game, from
# where_to_watch.py. See that module for why it reads the feed itself rather than
# scores.json, and for the fail-safe rules. Nothing here is typed in: a game the
# league has not announced a carrier for says so.
#
# The ZIP lookup is deliberately absent. The order says ship static first, and an
# input that does nothing is the control rule 5 forbids.

def _w2w_slug(week):
    return f"nfl-{week.get('season') or ''}-week-{week.get('week') or ''}"


def _w2w_wx(g, wx):
    """S-B5 detail on the schedule row: the reading, or nothing. Credited to the
    family's own weather product, as the item asks."""
    if not wx:
        return ""
    w = (wx.get("games") or {}).get(g.get("id") or "")
    if not w:
        return ""
    if w.get("indoors"):
        return '<span class="bd-src w2w-wx">indoors</span>'
    bits = []
    if w.get("temp_f") is not None:
        bits.append(f'{w["temp_f"]}F')
    if w.get("wind_mph") is not None:
        bits.append(f'wind {w["wind_mph"]} mph{" (flagged)" if w.get("windy") else ""}')
    if w.get("precip_pct") is not None:
        bits.append(f'{w["precip_pct"]}% precip')
    if not bits:
        return ""
    return f'<span class="bd-src w2w-wx">{esc(", ".join(bits))}</span>'


def _w2w_carriers(g):
    if not g.get("carriers"):
        # item 31: the sentence explaining why goes; the column says what it knows.
        return '<span class="w2w-car">TBA</span>'
    out = []
    for c in g["carriers"]:
        tag = "" if c.get("market") == "National" else '<span class="w2w-loc">Local</span>'
        out.append(f'<span class="w2w-car">{esc(c.get("name") or "")}{tag}</span>')
    return "".join(out)


def _w2w_stamp(data):
    """The real as-of time, in the page's own words. When the fetch failed and the
    committed file is being served, this shows THAT file's time, not now: a data
    surface is current or visibly stale, never quietly either."""
    import datetime as _dt
    raw = (data or {}).get("fetched_at") or ""
    try:
        t = _dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except Exception:
        return ""
    age = (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds() / 3600
    return f'<p class="bd-src">Updated {esc(_et_clock(t))}</p>'


def _w2w_split(week):
    """Upcoming windows first, then anything the feed says is finished. Read from the
    feed's `completed`, never from the clock: a build at 03:00 UTC cannot tell whether
    Thursday's game finished, was postponed, or is in a weather delay."""
    # D-14: `completed` alone is not enough. It is the right signal on a FRESH file -
    # a build at 03:00 UTC cannot tell whether Thursday's game finished, was postponed
    # or is in a weather delay - but where_to_watch keeps its committed file when the
    # fetch fails, and on a stale file yesterday's game is still completed:false and
    # therefore still "upcoming". That is how the rail card offered Monday night's game
    # on Tuesday. A kickoff that has already passed is not a NEXT window, whatever the
    # flag says; the grace period keeps a game actually in progress on the card.
    import datetime as _dt
    _grace = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=4)

    def _still_ahead(g):
        k = _utc_dt(g.get("kickoff_utc") or g.get("start_utc") or "")
        return True if k is None else k > _grace

    up, done = [], []
    for wname, games in _w2w_windows(week):
        pending = [g for g in games if not g.get("completed") and _still_ahead(g)]
        played = [g for g in games
                  if g.get("completed") or not _still_ahead(g)]
        if pending:
            up.append((wname, pending))
        if played:
            done.append((wname, played))
    return up, done


def _w2w_windows(week):
    """Games grouped by window, windows in kickoff order. A window the feed shows that
    is not one of the named slots (a Wednesday opener, an international game) keeps its
    own day name rather than being forced into a slot it does not belong to."""
    order, groups = [], {}
    for g in week.get("games") or []:
        w = g.get("window") or g.get("day_et") or "Other"
        if w not in groups:
            groups[w] = []
            order.append(w)
        groups[w].append(g)
    return [(w, groups[w]) for w in order]


def render_where_to_watch(week, weeks, dateline, current=False):
    slug = _w2w_slug(week)
    url = "/where-to-watch.html" if current else f"/where-to-watch/{slug}.html"
    up, done = _w2w_split(week)
    rows = []
    for wname, games in up:
        rows.append(f'<div class="w2w-win"><span class="bd-label">{esc(wname)}</span>'
                    f'<span class="bd-stamp">{esc(games[0].get("day_et") or "")}</span></div>')
        for g in games:
            rows.append(
                f'<div class="w2w-row"><span class="w2w-game">{esc(g.get("away") or "")} at '
                f'{esc(g.get("home") or "")}</span>'
                f'<span class="bd-src">{esc(g.get("kickoff_et") or "")}</span>'
                f'<span class="w2w-cars">{_w2w_carriers(g)}{_w2w_wx(g, WX_DATA)}</span></div>')
    if done:
        # item 30: the finished games sit at the bottom under one plain noun. "per the
        # league feed" is process (C-L3) and "Already played" is a sentence about the
        # section rather than its name.
        rows.append('<div class="w2w-win w2w-done">'
                    '<span class="bd-label">Final</span></div>')
        for wname, games in done:
            for g in games:
                sc = ""
                if g.get("away_score") is not None and g.get("home_score") is not None:
                    sc = (f'{esc(str(g.get("away_score")))}-'
                          f'{esc(str(g.get("home_score")))}')
                rows.append(
                    f'<div class="w2w-row w2w-played"><span class="w2w-game">'
                    f'{esc(g.get("away") or "")} at {esc(g.get("home") or "")}</span>'
                    f'<span class="bd-src">{esc(g.get("day_et") or "")}</span>'
                    f'<span class="w2w-cars"><span class="bd-src">'
                    f'{esc(g.get("status") or "Final")}{" " + sc if sc else ""}</span>'
                    f'</span></div>')
    others = "".join(
        f'<a class="bd-more" href="/where-to-watch/{_w2w_slug(w)}.html">Week {w.get("week")}</a>'
        for w in weeks if w.get("week") != week.get("week"))
    n = len(week.get("games") or [])
    body = f"""<main class="wrap"><section class="page">
  <h1 class="lx-h1" style="margin-bottom:6px">NFL Week {esc(str(week.get("week") or ""))}</h1>
  {_w2w_stamp(W2W_DATA)}
  <div class="w2w">{"".join(rows)}</div>
  <div class="lx-actions">{others}</div>
  <p class="bd-src" style="margin-top:14px">Weather: National Weather Service.
     Schedule and channels: ESPN.</p>
</section></main>"""
    return shell(f"NFL Week {week.get('week')}: where to watch every game - {NAME}",
                 f"Every NFL Week {week.get('week')} game by kickoff window, with the "
                 f"channel or stream that carries it.",
                 "Where to watch", body, dateline, path=url)


def nfl_week(w2w=None):
    """F-2: the NFL week, computed from the SCHEDULE file, never from the calendar.

    A week runs from the Tuesday after the last game of the previous week through the
    Monday night game. The schedule gives the kickoffs, so the rule is simply: the
    current week is the first one whose last kickoff has not yet passed. Every surface
    that names a week reads this one function, so the band, the hub, the inactives
    board, the game pages and the player pages cannot disagree.

    Returns (week_number, last_kickoff_utc) or (None, None) when the file has no weeks.
    """
    data = w2w if w2w is not None else W2W_DATA
    weeks = (data or {}).get("weeks") or []
    if not weeks:
        return (None, None)
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    for w in weeks:
        ks = [_utc_dt(g.get("kickoff_utc") or "") for g in (w.get("games") or [])]
        ks = [k for k in ks if k]
        if not ks:
            continue
        last = max(ks)
        # a Monday night game runs about four hours; the week turns after it ends
        if now < last + _dt.timedelta(hours=4):
            return (w.get("week"), last)
    last_w = weeks[-1]
    ks = [_utc_dt(g.get("kickoff_utc") or "") for g in (last_w.get("games") or [])]
    return (last_w.get("week"), max([k for k in ks if k], default=None))


def fantasy_asof(label, when_iso, source=""):
    """C-L1 and item 41: one stamp, "Updated Sep 14, 8:00 PM ET".

    F-1 asked for the week, the label and the source on every fantasy surface. The copy
    pass overrules that and wins where they differ: the week is in the heading (N-7), and
    the label and the source are the kind of chrome C-L1 removes. `label` and `source`
    are kept in the signature so the call sites do not all have to change at once."""
    dt = _utc_dt(when_iso or "")
    if not dt:
        return ""
    when = f'{fmt_short_date(dt.astimezone(_ET).strftime("%Y-%m-%d"))}, {_et_clock(dt)}'
    return f'<p class="fx-asof">Updated {esc(when)}</p>'


def _also_today(pool, n=3):
    """N-4: the lead card without a receipts ledger was a headline, a dek and a
    byline stretched down a 1,130px rail - two thirds of it empty. On a day whose
    top story carries no checkable figures the ledger's place is taken by the next
    three desk headlines and their times, so the card fills the row on its own
    content and the row's height is the lead's, never the rail's."""
    rows = []
    for i in (pool or []):
        if len(rows) >= n:
            break
        if not i.get("slug") or not _claim(i["slug"]):
            continue
        # A headline is never clamped (C-9, and the standing law that authored text is
        # not truncated); it wraps. The stamp is the time only: every item on this list
        # carries the same dateline as the lead beside it, so repeating the date three
        # times is the chrome C-L1 removes.
        _dt = _parse_utc(i)
        _when = _et_clock(_dt) if _dt else fmt_when(i)
        rows.append(f'<a class="sp-also-r" href="/articles/{esc(i["slug"])}.html">'
                    f'<span class="sp-also-h">{esc(i.get("title") or "")}</span>'
                    f'<span class="bd-src">{esc(_when)}</span></a>')
    if not rows:
        return ""
    return (f'<div class="sp-also"><span class="bd-label">Also today</span>'
            f'{"".join(rows)}</div>')


def where_to_watch_card(data):
    """Homepage module 4, left. The next window or two, not the whole week."""
    if not data or not (data.get("weeks") or []):
        return ""
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    # D-14: the next window comes from the SCHEDULE, so pick the first week that
    # actually has one. Picking the first week with an uncompleted game and stopping
    # there is what stranded the card on a stale file: week 1 looked unfinished, had no
    # window still ahead, and the card fell to nothing rather than to week 2.
    upcoming = []
    week = None
    for w in data["weeks"]:
        up, _played = _w2w_split(w)
        if up:
            # N-4: one window on the rail card, not two. The rail clamps to the lead
            # card; the whole week is one click away on /where-to-watch.
            week, upcoming = w, up[:1]
            break
    if not upcoming:
        return ""
    rows = []
    for wname, games in upcoming:
        rows.append(f'<div class="w2w-win"><span class="bd-label">{esc(wname)}</span>'
                    f'<span class="bd-stamp">{esc(games[0].get("day_et") or "")}</span></div>')
        for g in games[:3]:     # N-4: the rail card is a sample, not the window
            rows.append(
                f'<div class="w2w-row"><span class="w2w-game">{esc(g.get("away") or "")} at '
                f'{esc(g.get("home") or "")}</span>'
                f'<span class="bd-src">{esc(g.get("kickoff_et") or "")}</span>'
                f'<span class="w2w-cars">{_w2w_carriers(g)}</span></div>')
    return (f'<div class="bd-card" style="gap:12px;padding:20px 22px 18px">'
            f'<div class="bd-sec" style="border:none;padding:0"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Where to watch</span>'
            f'<span class="bd-h2" style="font-size:20px">NFL Week '
            f'{esc(str(week.get("week") or ""))}</span></div>'
            f'<a class="bd-more" href="/where-to-watch.html">All games</a></div>'
            f'<div class="w2w">{"".join(rows)}</div>'
            '</div>')


# ---- S6: the news hub ---------------------------------------------------------
# /news.html was a flat dump of every live story. It is now the Record tier, then
# one section per storyline, then a month archive, with a paginated page per
# storyline behind it.
#
# ONE TAXONOMY. The storylines here are RECORD_LANES: the same lanes, the same
# names, the same tag rules the Record uses. There is no second Tracking-only
# classification to drift out of sync with the first.
#
# REACHABILITY, which is the whole point of the rebuild. Every live story is
# reachable at a click depth of three or less from the front page:
#   home -> /news -> /news/<lane> -> /news/<lane>/page/N   (a lane's stories)
#   home -> /news -> /news/archive/YYYY-MM                 (anything unclaimed)
# and no page renders with fewer than NEWS_MIN_STORIES entries.
NEWS_PER_SECTION = 6      # stories shown inline per storyline on the hub
NEWS_PER_PAGE = 24        # stories per paginated storyline page
NEWS_MIN_STORIES = 5      # a lane below this is not given a page (no thin pages)
NEWS_RECENT_DAYS = 60     # a lane whose newest story is older than this is "past"


# THE NEWS HUB CARRIES MORE LANES THAN THE RECORD, and the reason is what each surface
# is for. The Record is what stays true after the news moves on, so its lanes are the
# business-of-sports ones: rulings, discipline, rights. The news hub has to reach EVERY
# live story, and 382 of 410 are game coverage the Record lanes correctly ignore. A
# transactions wire or a Tuesday result is not something that "holds up after the news
# cycle moves on", so it does not belong in the Record, and a hub that cannot reach it
# has failed at the one job the rebuild exists for.
#
# These are the desk's OWN TAGS, not a new classification: transactions 163, injuries
# 94, nfl 120, soccer 66, mlb 65, scores-results 129. Every lane below clears the
# five-story floor on live content; WNBA (1) and NHL (2) do not and are deliberately
# absent, so their stories reach readers through the month archive instead of through a
# lane too thin to earn a page.
NEWS_EXTRA_LANES = [
    ("transactions", "Transactions", ("transactions",), False),
    ("injuries", "Injuries", ("injuries",), False),
    ("nfl", "NFL", ("nfl",), False),
    ("soccer", "Soccer", ("soccer",), False),
    ("results", "Results", ("scores-results",), False),
    ("mlb", "MLB", ("mlb",), False),
    ("nba", "NBA", ("nba",), False),
    ("college", "College", ("college", "college-football", "college-basketball"), False),
    ("other-sports", "Other sports",
     ("combat sports", "golf", "cycling", "cricket", "athletics"), False),
    ("tennis", "Tennis", ("tennis",), False),
]
# Which lanes match on tags rather than phrases.
NEWS_TAG_LANES = {slug for slug, _n, _t, _h in NEWS_EXTRA_LANES}


def _news_lane_index(items):
    """Every live story bucketed into its lane, newest first. First lane in
    RECORD_LANES order claims a story, so nothing is double counted."""
    live = [i for i in (items or [])
            if not i.get("example") and not _is_wrap(i) and not i.get("superseded_by")]
    live.sort(key=lambda i: i.get("published_utc") or "", reverse=True)
    claimed, lanes = set(), []
    for slug, name, tags, _home in RECORD_LANES + NEWS_EXTRA_LANES:
        tag_lane = slug in NEWS_TAG_LANES
        rx = None if tag_lane else _record_lane_rx(tags)
        want = set(tags) if tag_lane else None
        got = []
        for i in live:
            if i.get("slug") in claimed:
                continue
            hit = bool(want & set(tags_for(i))) if tag_lane else _record_lane_match(rx, i)
            if hit:
                got.append(i)
                claimed.add(i.get("slug"))
        lanes.append({"slug": slug, "name": name, "items": got})
    rest = [i for i in live if i.get("slug") not in claimed]
    # Newest first: the hub is ordered by which storyline moved most recently.
    lanes.sort(key=lambda L: (L["items"][0].get("published_utc") or "") if L["items"] else "",
               reverse=True)
    return lanes, rest, live


def _news_row(i):
    tags = tags_for(i)
    return (f'<div class="nh-row"><a class="nh-t" href="/articles/{esc(i["slug"])}.html">'
            f'{esc(i.get("title") or "")}</a>'
            f'<span class="nh-m">{verdict_badge(i.get("verdict"), i)}'
            f'<span class="bd-stamp">{esc(fmt_when(i))}</span>'
            + (f'<span class="bd-stamp">{esc(tags[0])}</span>' if tags else "")
            + '</span></div>')


def _news_month_archive(live):
    """Month buckets, newest first. Every story has a month, so this is the floor
    under reachability: a story its lane never showed is still one click from here."""
    by = {}
    for i in live:
        m = (i.get("published_utc") or "")[:7]
        if len(m) == 7:
            by.setdefault(m, []).append(i)
    return dict(sorted(by.items(), reverse=True))


def _news_month_label(m):
    """"September 2026" from "2026-09". fmt_date returns a full day stamp, and
    slicing three characters off it produced "September 1, 2"."""
    import datetime as _dt
    try:
        return _dt.date(int(m[:4]), int(m[5:7]), 1).strftime("%B %Y")
    except Exception:
        return m


def _news_jsonld(url, name, desc, rows, crumbs):
    """CollectionPage + ItemList + BreadcrumbList, as specified."""
    items = [{"@type": "ListItem", "position": n,
              "url": f"{ORIGIN}/articles/{i['slug']}.html",
              "name": (i.get("title") or "")[:110]}
             for n, i in enumerate(rows[:30], start=1)]
    crumb = [{"@type": "ListItem", "position": n, "name": nm,
              "item": f"{ORIGIN}{href}"} for n, (nm, href) in enumerate(crumbs, start=1)]
    # shell() injects schema_extra into the head verbatim, so it carries its own
    # script tag; returning bare JSON put nothing on the page at all.
    return '\n<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage",
        "url": f"{ORIGIN}{url}", "name": name, "description": desc,
        "isPartOf": {"@type": "WebSite", "name": FAMILY, "url": ORIGIN},
        "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": crumb},
        "mainEntity": {"@type": "ItemList", "numberOfItems": len(rows),
                       "itemListElement": items},
    }, separators=(",", ":")) + "</script>"


def _news_section(lane, past=False):
    rows = lane["items"]
    if not rows:
        return ""
    shown = rows[:NEWS_PER_SECTION]
    more = ""
    if len(rows) >= NEWS_MIN_STORIES and len(rows) > len(shown):
        more = (f'<a class="bd-more" href="/news/{esc(lane["slug"])}.html">'
                f'All {len(rows)}</a>')
    # C-L6: the count is short. The date is the day, not the full dateline.
    _nd = _utc_dt((rows[0].get("published_utc") or rows[0].get("date") or "")) if rows else None
    newest_short = fmt_short_date(_nd.astimezone(_ET).strftime("%Y-%m-%d")) if _nd else ""
    return (f'<section class="bd-mod" id="{esc(lane["slug"])}">'
            f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(lane["name"])}</span>'
            f'<span class="bd-stamp">{len(rows)} stories'
            f'{" · " + esc(newest_short) if newest_short and not past else ""}</span>'
            f'</div>{more}</div>'
            f'<div class="nh-rows">{"".join(_news_row(i) for i in shown)}</div></section>')


def render_news_hub(items, dateline, pulse=None):
    """/news.html (C4)."""
    lanes, rest, live = _news_lane_index(items)
    import datetime as _dt
    cutoff = (_build_now() - _dt.timedelta(days=NEWS_RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    current = [L for L in lanes if L["items"] and (L["items"][0].get("published_utc") or "") >= cutoff]
    past = [L for L in lanes if L["items"] and L not in current]

    # Jump chips, in the same order the sections render.
    jump = "".join(
        f'<a class="nh-chip" href="#{esc(L["slug"])}">{esc(L["name"])}'
        f'<span class="nh-chip-n">{len(L["items"])}</span></a>' for L in current)

    # S-18: /news opened with the entire Record block before a single story. On the
    # news desk the Record is a pointer, not the page.
    rec = ('<p class="lx-dek" style="margin-top:10px">'
           '<a href="/keepers.html">The Record &rarr;</a></p>')
    months = _news_month_archive(live)
    marc = "".join(
        f'<a class="nh-mo" href="/news/archive/{esc(m)}.html">'
        f'<span class="nh-mo-m">{esc(_news_month_label(m))}</span>'
        f'<span class="bd-stamp">{len(v)} stories</span></a>'
        for m, v in months.items())
    arch = (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Archive</span>'
            f'<h2 class="bd-h2">Every story by month</h2></div>'
            f'<a class="bd-more" href="/archive.html">Full archive</a></div>'
            f'<div class="nh-months">{marc}</div></section>') if marc else ""

    past_html = ""
    if past:
        past_html = (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                     f'<span class="bd-eyebrow">Past storylines</span>'
                     f'<h2 class="bd-h2">Quiet for {NEWS_RECENT_DAYS} days or more</h2>'
                     f'</div></div>'
                     + "".join(_news_section(L, past=True) for L in past) + '</section>')

    body = f"""<main class="wrap"><section class="page">
  <h1 class="lx-h1" style="margin-bottom:6px">The news desk</h1>
  {rec}
  <div class="bd-sec" style="margin-top:26px"><div class="bd-sec-l">
    <h2 class="bd-h2">Storylines</h2></div></div>
  <nav class="nh-jump" aria-label="Jump to a storyline">{jump}</nav>
  {"".join(_news_section(L) for L in current)}
  {past_html}
  {arch}
</section></main>"""
    return shell(f"Sports news by storyline - {NAME}",
                 "Every checked story on the desk, grouped by the storyline it belongs to: "
                 "lawsuits and rulings, discipline, media rights and more.",
                 "News desk", body, dateline, path="/news.html",
                 schema_extra=_news_jsonld("/news.html", "The news desk",
                                           "Checked sports stories by storyline", live,
                                           [("Home", "/"), ("News desk", "/news.html")]))


def render_news_lane(lane, page, pages, dateline):
    """/news/<slug>.html and /news/<slug>/page/N.html."""
    rows = lane["items"][(page - 1) * NEWS_PER_PAGE: page * NEWS_PER_PAGE]
    base = f"/news/{lane['slug']}.html"
    nav = []
    if page > 1:
        prev = base if page == 2 else f"/news/{lane['slug']}/page/{page-1}.html"
        nav.append(f'<a class="bd-more" href="{esc(prev)}">&larr; Newer</a>')
    if page < pages:
        nav.append(f'<a class="bd-more" href="/news/{esc(lane["slug"])}/page/{page+1}.html">'
                   f'Older &rarr;</a>')
    url = base if page == 1 else f"/news/{lane['slug']}/page/{page}.html"
    title = f"{lane['name']} - crypto news by storyline"
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/news.html">News desk</a> / {esc(lane["name"])}</p>
  <h1 class="lx-h1" style="margin-bottom:6px">{esc(lane["name"])}</h1>
  <p class="lx-dek">{len(lane["items"])} stories{_page_note(page, pages)}</p>
  <div class="nh-rows">{"".join(_news_row(i) for i in rows)}</div>
  <div class="lx-actions">{"".join(nav)}</div>
</section></main>"""
    return shell(f"{title} - {NAME}",
                 f"Every checked story the desk has published on {lane['name'].lower()}.",
                 "News desk", body, dateline, path=url,
                 schema_extra=_news_jsonld(url, lane["name"],
                                           f"Sports stories on {lane['name'].lower()}", rows,
                                           [("Home", "/"), ("News desk", "/news.html"),
                                            (lane["name"], base)]),
                 noindex=False)


def render_news_month(month, rows, dateline):
    """/news/archive/YYYY-MM.html."""
    url = f"/news/archive/{month}.html"
    label = _news_month_label(month)
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/news.html">News desk</a> / Archive / {esc(label)}</p>
  <h1 class="lx-h1" style="margin-bottom:6px">{esc(label)}</h1>
  <p class="lx-dek">{len(rows)} stories</p>
  <div class="nh-rows">{"".join(_news_row(i) for i in rows)}</div>
</section></main>"""
    return shell(f"Sports news, {label} - {NAME}",
                 f"Every checked story the desk published in {label}.",
                 "News desk", body, dateline, path=url,
                 schema_extra=_news_jsonld(url, label, f"Sports stories from {label}", rows,
                                           [("Home", "/"), ("News desk", "/news.html"),
                                            (label, url)]))


# ---- S-F: phone shell, install, share ------------------------------------------
# A sticky bottom tab bar on phones, a manifest that installs properly, and a service
# worker that caches THE SHELL ONLY.
#
# WHAT THE WORKER MUST NEVER CACHE, and why it is worth being explicit in code rather
# than in a comment on a policy page: scores, inactives, weather and the board are the
# whole product, and a stale score served from a cache is worse than no score. The
# worker matches the stylesheet, the fonts and the icons, and nothing else. It never
# touches /site/data, never an HTML page, and never anything that could carry a
# person's own state, because there is no per-person state on this site to carry.

TAB_BAR = [
    # N-1: HOME IS FIRST, and it is named Home. The first tab was labelled Scores and
    # pointed at /index.html, so the tab bar had no way back to the front page and the
    # scoreboard's own page was not reachable from it at all.
    ("Home", "/index.html",
     "M3 9l7-6 7 6v8H3z"),                                    # a roof over a door
    ("Scores", "/scores.html",
     "M3 13h3l2-5 3 9 2.5-6 1.5 2h4"),                       # a scoreline
    ("Fantasy", "/fantasy/inactives.html",
     "M4 6h10M4 10h7M4 14h10M17 7v7M17 16.5v.5"),            # a list with a flag
    ("Watch", "/where-to-watch.html",
     "M3 5h14v9H3zM7 17h6"),                                  # a screen
    ("Record", "/keepers.html",
     "M5 3h8l3 3v11H5zM8 8h5M8 11h5"),                        # a filed document
    ("More", "/archive.html",
     "M4 6h12M4 10h12M4 14h12"),                              # a menu
]


def tab_bar(active_path=""):
    """The phone tab bar. Hidden above the phone breakpoint in CSS rather than built
    twice. A tab whose page is not being built this run is dropped, so the bar never
    offers a destination that does not exist."""
    out = []
    for label, href, d in TAB_BAR:
        if label == "Fantasy" and not IA_BOARD:
            continue
        if label == "Watch" and not W2W_LIVE:
            continue
        on = " on" if href == active_path else ""
        out.append(
            f'<a class="tb-item{on}" href="{esc(href)}">'
            f'<svg viewBox="0 0 20 20" aria-hidden="true" width="20" height="20">'
            f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"></path></svg>'
            f'<span>{esc(label)}</span></a>')
    if len(out) < 2:
        return ""
    return (f'<nav class="tabbar" aria-label="Sections">{"".join(out)}</nav>')


SERVICE_WORKER = """/* GoCheckMySports service worker: the shell, and nothing else.
   Scores, inactives, weather and the Record are the product. A stale score served
   from a cache is worse than no score, so this caches the stylesheet, the fonts and
   the icons, and never an HTML page, never /site/data, never anything else. */
const SHELL = 'gcms-shell-%(v)s';
const ASSETS = %(assets)s;
self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin) return;
  /* Only the shell. Anything that is or could become data goes to the network. */
  if (!ASSETS.includes(u.pathname)) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
"""

SW_REGISTER = ("<script>if('serviceWorker' in navigator){window.addEventListener('load',"
               "function(){navigator.serviceWorker.register('/sw.js').catch(function(){});"
               "});}</script>")


# ---- S-A: the Scoreboard band, and S-B1 designations on the cards --------------
# Artboard: sports-v3-desktop / sports-v3-phone. The band is the product: a reader
# opening the site on a Sunday should see every live score with its network without
# scrolling or clicking.
#
# EVERYTHING HERE OMITS RATHER THAN GUESSES. A game with no network shows no chip. A
# sport whose length is not fixed draws no progress bar, because a bar that is 50% of
# nothing is a fabricated number. A team with no colour in team-colors.json gets the
# neutral bar the omission table specifies.

SB_TAB_ORDER = ["NFL", "MLB", "CFB", "Soccer", "NBA", "NHL", "WNBA"]


# ---- CFB-1: the school in full, the poll rank, and an order that follows the day ----
# Three complaints, one shape. A college card reading "UGA at ARK" asks the reader to
# know a hundred and thirty abbreviations, where the NFL's thirty-two are read faster
# than the names. The poll rank is the single most useful fact about a college game and
# the band did not carry it anywhere. And MLB sat above college football on a Saturday
# in September because SB_TAB_ORDER is a constant, while the marquee beside it, which
# does read the calendar weighting, had already led with a college game: the band
# disagreed with itself.
#
# WHERE A RANK COMES FROM. The game's own feed first (curatedRank, the rank at that
# kickoff), then the committed AP Top 25. The second source is what makes the band
# carry ranks on the build after a poll refresh instead of waiting for the next
# scoreboard fetch. Both are ESPN and the join is abbreviation to abbreviation inside
# one sport, so "MIA" here is the Hurricanes and cannot become the Marlins. No match,
# no rank: the omission table, not a guess.
# Two different questions, and they must not share a set. What a card CALLS a team is
# every league's business; whether a team has a POLL RANK is college football's alone.
# These were one constant once, and widening it so the NFL could print "Buffalo" also
# opened the rank lookup to the NFL: the AP index is keyed on abbreviation, so the
# Dolphins took Miami's rank, the Texans took Houston's and the Rangers took Texas's.
# That is exactly the collision the note above says cannot happen, and it cannot only
# while the lookup is fenced to one sport.
FULL_NAME_LEAGUES = {"NFL", "MLB", "CFB", "Soccer", "NBA", "NHL", "WNBA"}
RANKED_LEAGUES = {"CFB"}     # the only league here that has a poll worth printing
AP_TOP = 25
_AP_INDEX = {"key": None, "map": {}}


def _ap_rank_index():
    """{ABBR: rank} for the committed AP Top 25, memoised on the poll it came from.
    Empty when the poll has not been fetched, which reads the same as every team being
    unranked: nothing is printed."""
    rk = ((ST_DATA or {}).get("rankings") or {})
    key = f"{(ST_DATA or {}).get('fetched_at') or ''}|{rk.get('week') or ''}"
    if _AP_INDEX["key"] == key:
        return _AP_INDEX["map"]
    out = {}
    for r in (rk.get("rows") or []):
        ab, n = (r.get("abbr") or "").strip().upper(), r.get("rank")
        if ab and isinstance(n, int) and 1 <= n <= AP_TOP:
            out[ab] = n
    _AP_INDEX.update(key=key, map=out)
    return out


def _team_rank(g, t):
    """This team's poll rank for this game, or None. Only college football has a poll
    the band prints, so no other league is looked up at all."""
    if (g.get("league") or "") not in RANKED_LEAGUES:
        return None
    n = t.get("rank")
    if isinstance(n, int) and 1 <= n <= AP_TOP:
        return n
    return _ap_rank_index().get((t.get("abbr") or "").strip().upper())


def _team_label(g, t):
    """What a card calls this team. Shows full team names (city/school) for all leagues.
    For example: "Georgia" instead of "UGA", "Buffalo" instead of "BUF"."""
    if (g.get("league") or "") in FULL_NAME_LEAGUES:
        return (t.get("school") or t.get("name") or t.get("abbr") or "").strip()
    return (t.get("abbr") or "").strip()


def _team_mascot(g, t):
    """The mascot, when it says something the card has not already said.

    CFB-2: WHICH MIAMI. The label is the place, and the place is not the team: "Miami"
    is the Hurricanes on a Saturday and the Dolphins on a Sunday, and the board printed
    both the same. The mascot is what tells them apart, so it rides under the name.

    Suppressed when it would only repeat what is above it. The feed's mascot for a
    college side is the real one ("Scarlet Knights"), but the older field it falls back
    to is the school again, and a card reading "Rutgers / Rutgers" is noise. The first
    word is compared too, so "Western Kentucky" does not pick up "Western KY".
    """
    m = (t.get("mascot") or t.get("name") or "").strip()
    if not m:
        return ""
    label = _team_label(g, t).strip()
    if m.lower() == label.lower():
        return ""
    first = lambda s: (s.split() or [""])[0].lower()
    if label and first(m) == first(label):
        return ""
    return m


def _rank_html(g, t, cls="tk-rk"):
    """The rank badge, or nothing. Kept as its own element outside any node the live
    poll rewrites, so a score update cannot take the rank off the card."""
    n = _team_rank(g, t)
    return f'<span class="{cls}">{n}</span>' if n else ""


def _game_rank(g):
    """The better of a game's two poll ranks, for ordering: 26 when neither side is
    ranked, so every ranked game sorts above every unranked one and a top-five game
    sorts above a 24 against a 25."""
    ns = [n for n in (_team_rank(g, g.get("away") or {}),
                      _team_rank(g, g.get("home") or {})) if n]
    return min(ns) if ns else AP_TOP + 1


def _day_league_order(now=None):
    """Today's league order, heaviest first, by the same calendar weighting the lead
    story (UX-5) and the marquee already use. Ties keep SB_TAB_ORDER's own order, so a
    day whose leagues carry no weighting of their own looks exactly as it did before
    this rule existed."""
    return sorted(SB_TAB_ORDER,
                  key=lambda n: (-_league_weight(n, now), SB_TAB_ORDER.index(n)))


def _league_rank(league, now=None):
    """A league's place in today's order. 99 for a league the board does not tab."""
    order = _day_league_order(now)
    return order.index(league) if league in order else 99


def _sb_sort_key(g, now=None):
    """The band's running order: state first (live, then a recent final, then upcoming,
    then old finals), then today's league weighting, then the poll rank, then kickoff.

    The rank sits BELOW the league and ABOVE the clock on purpose. It must not lift a
    ranked college game over a live NFL game, which is what putting it first would do;
    within college football it must put the top-ten game above the noon fixture that
    happens to kick first, which is what putting it below the clock would prevent.
    """
    return (_sb_state_rank(g, now), _league_rank(g.get("league") or "", now),
            _live_urgency(g) if g.get("state") == "in" else (0, ""),
            _game_rank(g), g.get("start_utc") or "")


def _sb_sort_key_in_league(g, now=None):
    """The same order inside one league's panel, where the league term is a constant
    and only the poll rank and the clock can separate two games."""
    return (_sb_state_rank(g, now),
            _live_urgency(g) if g.get("state") == "in" else (0, ""),
            _game_rank(g), g.get("start_utc") or "")


def _sb_team_row(t, lose=False, big=False, started=True, kick=""):
    # S-19: the board's own feed carries no colour, so it comes from the scoreboard,
    # matched on team id. No match, no bar: a neutral rule rather than a wrong colour.
    col = _nfl_color(t.get("id"))
    bar = (f'<span class="tc" style="background:{esc(col)}"></span>' if col
           else '<span class="tc tc-none"></span>')
    rec = f' · {esc(t.get("record"))}' if t.get("record") else ""
    nm = (f'<span class="abbr{" big" if big else ""}">{esc(t.get("abbr") or "")}</span>'
          f'<span class="tname">{esc(t.get("name") or "")}{rec}</span>')
    if big:
        nm = (f'<span class="sb-stack"><span class="abbr big">{esc(t.get("abbr") or "")}'
              f'</span><span class="tname">{esc(t.get("name") or "")}{rec}</span></span>')
    sc = t.get("score")
    sc = "" if sc in (None, "") or not started else str(sc)
    # S-9: before kickoff the score column is not empty, it carries the time, in mono,
    # in the place the score will occupy. Passed on one row only so it prints once.
    if not started and kick:
        return (f'<div class="team">{bar}{nm}</div>'
                f'<span class="score kick{" big" if big else ""}">{esc(kick)}</span>')
    return (f'<div class="team">{bar}{nm}</div>'
            f'<span class="score{" lose" if lose else ""}'
            f'{" big" if big else ""}">{esc(sc)}</span>')


def _sb_zone(text):
    """G-7/S-11: the feed hands back status_short pre-formatted with the offset name
    of the day - "9/18 - 7:30 PM EDT" in summer, EST in winter. House style is one
    label, ET, all year. Done at render because the string arrives already built."""
    return re.sub(r"\b(EDT|EST)\b", "ET", str(text or ""))


def _sb_today_status(g):
    """S-9: "9/14 - 7:30 PM ET" loses its date prefix when the game is today, because
    then the band is today's and the date says nothing. It KEEPS the date when the band
    has fallen through to a later day, which it does whenever today has no games - and
    on that day the date is the most useful thing on the card."""
    txt = _sb_zone(g.get("status_short"))
    d = _utc_dt(g.get("start_utc") or "")
    if d and d.astimezone(_ET).date() == _build_now().astimezone(_ET).date():
        txt = re.sub(r"^\s*\d{1,2}/\d{1,2}\s*-\s*", "", txt)
    return txt


def _sb_status(g):
    st = g.get("state")
    if st == "in":
        per = _sb_today_status(g)
        return f'<span class="live"><span class="dot"></span>{esc(per)}</span>'
    if st == "post":
        return ('<span class="fin"><svg width="11" height="11" viewBox="0 0 11 11" '
                'aria-hidden="true"><path d="M2 5.8L4.3 8 9 3" fill="none" '
                'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
                'stroke-linejoin="round"></path></svg>Final</span>')
    return f'<span class="soon">{esc(_sb_today_status(g))}</span>'


def _sb_losers(g):
    """Which side to mute. Only at final, and only when the scores differ: muting a
    leader mid-game would call a result that has not happened."""
    if g.get("state") != "post":
        return (False, False)
    try:
        a, h = int(g["away"].get("score")), int(g["home"].get("score"))
    except Exception:
        return (False, False)
    return (a < h, h < a)


def _sb_fantasy_strip(g, ia_index):
    """S-B1/S-8. Designations for this game's two teams, from the inactives snapshot.
    Once a list has been seen the strip says so and links the board; before that it
    gives the posting time rather than implying a clean bill of health.

    NFL ONLY, AND THE ID IS NOT AN IDENTITY (S-8). Inactives are an NFL gameday
    concept. The strip was rendering on every league because the index keyed on the
    bare team id, and ESPN's ids are scoped per league: MLB Chicago is id 4, NHL
    Montreal is id 10, NBA Miami is 14, against NFL Denver 7 and Tennessee 10. So a
    hockey card collected a football team's count and printed it as fact - the audit
    caught "INACTIVES CHW 7 · CLE 7" on baseball. The league gate is the instruction;
    keying the index by (league, id) is what stops the collision coming back through
    some other surface."""
    if (g.get("league") or "") != "NFL":
        return ""
    bits, when = [], ""
    for side in ("away", "home"):
        tid = (g.get(side) or {}).get("id") or ""
        ab = (g.get(side) or {}).get("abbr") or ""
        # H-1: the list has to belong to THIS game, not merely to this team.
        t = _ia_for_game(g, ia_index or {}, side)
        if not t:
            continue
        bits.append(f'{esc(ab)} {t["count"]}')
    if bits:
        return (f'<a class="sb-fan" href="/fantasy/inactives.html">'
                f'<span class="sb-fan-k">Inactives</span>'
                f'{esc(" · ".join(bits))}</a>')
    # Not posted yet. The league posts about ninety minutes before kickoff; say when
    # rather than nothing, and only for a game that has not started.
    if g.get("state") == "pre":
        dt = _utc_dt(g.get("start_utc") or "")
        if dt:
            import datetime as _dt
            when = _et_clock(dt - _dt.timedelta(minutes=90))
            if when:
                return (f'<span class="sb-fan sb-fan-pend">'
                        f'<span class="sb-fan-k">Inactives</span>post {esc(when)}</span>')
    return ""


def _wx_for(g, wx):
    """This game's kickoff weather, keyed the way kickoff_weather writes it."""
    if not wx:
        return None
    games = wx.get("games") or {}
    for k in (g.get("id") or "", f'{(g.get("away") or {}).get("abbr","")}@'
                                 f'{(g.get("home") or {}).get("abbr","")}'):
        if k and k in games:
            return games[k]
    return None


def _wx_chip(g, wx):
    """S-B5. A flag only above the threshold, and "indoors" where the roof says so.
    A game with no reading shows nothing: the omission table's rule, and the reason
    the feed's own weather is not read at all (no sustained wind, transposed fields)."""
    w = _wx_for(g, wx)
    if not w:
        return ""
    if w.get("indoors"):
        return '<span class="wx wx-in">indoors</span>'
    if w.get("windy"):
        return (f'<span class="wx wx-wind">wind {esc(str(w.get("wind_mph")))} mph</span>')
    return ""


def _game_href(g):
    """A game page where one is built, else the scores page. Game pages are NFL only
    for now: they need a box score and an inactives list, and only the NFL surfaces
    both on this desk today."""
    return (f'/games/{g.get("id")}.html' if g.get("league") == "NFL" and g.get("id")
            else "/scores.html")


def _mq_vars(g):
    """A-8: the marquee's diagonal wash reads the same two team colours as A-7."""
    a = (g.get("away") or {}).get("color") or ""
    b = (g.get("home") or {}).get("color") or ""
    return f' style="--a:{esc(a)};--b:{esc(b)}"' if a and b else ""


# ---- V-1 / SC-1..SC-9: the Ticket card ----------------------------------------
# From ScoreboardC.dc.html (canvas row thirteen). The stub carries the matchup in the
# two team colors, a perforation, then a spec list, the story line and two buttons.
#
# ONLY THE LINES THAT EXIST RENDER (SC-1). Every value below comes from a file the desk
# already holds: the scoreboard feed, kickoff-weather.json, the inactives board and the
# designations report. A fact the desk does not hold is omitted, never guessed and never
# filled: that is the same law as "a module with no data is omitted".

_TK_INK = "#EBE9E3"
_TK_UP, _TK_DOWN, _TK_TIE = "#3DDC84", "#FF7A6B", "#F0C674"
_TK_MID = " \u00b7 "     # the separator, kept out of f-string expressions


def _tk_colors(g):
    """The two team colors for the stub gradient, from the feed's own values."""
    def one(side, fallback):
        c = ((g.get(side) or {}).get("color") or "").strip()
        return c if re.fullmatch(r"#[0-9a-fA-F]{6}", c or "") else fallback
    return one("away", "#2A2D35"), one("home", "#1B1E25")


def _tk_score(side):
    try:
        return int(side.get("score"))
    except (TypeError, ValueError):
        return None


def _tk_sc9(g):
    """SC-9: who is winning, in color. Returns (away_color, home_color).

    Live and final only. A pre-game card carries no color on the teams, which is what
    makes the two states read apart at a glance without reading a word."""
    if g.get("state") not in ("in", "post"):
        return "", ""
    a, h = _tk_score(g.get("away") or {}), _tk_score(g.get("home") or {})
    if a is None or h is None:
        return "", ""
    if a == h:
        return _TK_TIE, _TK_TIE
    return (_TK_UP, _TK_DOWN) if a > h else (_TK_DOWN, _TK_UP)


_VENUE_FIX = None


def _venue_name(g):
    """H-11: the feed's venue name, with a correction only where the feed is wrong.

    The feed is the source. venue_corrections.json is the single exception and it is
    kept honest mechanically: every entry records the feed's name at the time it was
    entered, and the canary asserts that name is still what the feed says. The day the
    source corrects its record, the canary fails naming the entry and the entry goes.
    A correction that stops being a correction cannot sit there quietly.
    """
    global _VENUE_FIX
    name = (g.get("venue") or "").strip()
    if not name:
        return ""
    if _VENUE_FIX is None:
        _VENUE_FIX = {}
        try:
            with open(os.path.join(HERE, "site", "data", "venue_corrections.json"),
                      encoding="utf-8") as fh:
                _VENUE_FIX = (json.load(fh) or {}).get("corrections") or {}
        except Exception:
            _VENUE_FIX = {}
    # Keyed by the HOME TEAM the feed names: the scoreboard record carries no venue id,
    # and a bare name is not a key (two clubs can share a stadium name's words). The
    # entry must also still name the string the feed is actually carrying, so a
    # correction cannot outlive the error it corrects.
    key = f'{g.get("league") or ""}:{(g.get("home") or {}).get("abbr") or ""}'
    fix = _VENUE_FIX.get(key) or {}
    if fix.get("feed_name") == name and fix.get("name"):
        return fix["name"]
    return name


def _tk_venue(g, wx):
    """Venue, with the weather when the game is outdoors. WX is keyed by game id."""
    w = ((wx or {}).get("games") or {}).get(str(g.get("id"))) or {}
    # H-11: the name is the feed's. kickoff-weather.json's `venue` comes from our own
    # venues.json, which had "Reliant Stadium" for a stadium renamed NRG in 2014, and
    # the card printed it as fact. The weather itself stays: it is keyed to the venue's
    # coordinates and the stadium did not move, so the temperature is true even when we
    # have no name to put in front of it.
    venue = _venue_name(g)
    if not venue and not w:
        return ""
    if w.get("indoors") or g.get("venue_indoor"):
        # UX-13: with the name withheld the line showed only its attribute, "roof",
        # which reads as a field with its label missing. The value is the fact.
        return f"{venue} \u00b7 roof" if venue else "Indoors"
    bits = [venue] if venue else []
    if isinstance(w.get("temp_f"), (int, float)):
        bits.append(f"{int(w['temp_f'])}\u00b0F at kickoff")
    if isinstance(w.get("wind_mph"), (int, float)) and w["wind_mph"] >= 8:
        bits.append(f"wind {int(w['wind_mph'])} mph")
    if isinstance(w.get("precip_pct"), (int, float)) and w["precip_pct"] >= 40:
        bits.append(f"{int(w['precip_pct'])}% rain")
    return " \u00b7 ".join(bits) if bits else ""


_TK_DESIG = {}


def _tk_desig_index(desig):
    """NFL designation counts per team nickname, built once.

    The designations report names a team in full ("Arizona Cardinals"); the scoreboard
    names it by nickname and abbreviation. Matching on the nickname is safe HERE and only
    here: the report is NFL-only and no two NFL nicknames collide. It is not a general
    key, and nothing outside this function may use it that way.
    """
    if _TK_DESIG:
        return _TK_DESIG
    for status, players in ((desig or {}).get("groups") or {}).items():
        for p in players or []:
            nick = (p.get("team") or "").split()[-1].lower()
            if nick:
                _TK_DESIG.setdefault(nick, {}).setdefault(status.lower(), 0)
                _TK_DESIG[nick][status.lower()] += 1
    return _TK_DESIG


def _tk_avail(g, ia_index, desig):
    """SC-1: the availability line in the league's own words.

    NFL says designations and inactives, MLB says probables, NBA and NHL say injury
    report. A league whose vocabulary the desk does not hold gets no line at all.
    """
    league = g.get("league")
    if league != "NFL":
        return []          # MLB probables and NBA/NHL reports are not held yet (W-5)
    idx = _tk_desig_index(desig)
    rows = []
    parts = []
    for side in ("away", "home"):
        t = g.get(side) or {}
        # A NAMELESS TEAM MUST NOT TAKE THE BUILD. "".split() is [], and [-1] on it
        # raises, so one feed row with an empty name would stop every page rather than
        # cost one line on one card. Found by a canary fixture, not by a reader, and
        # only because the fixture was lazier about names than the feed has been.
        _nm = (t.get("name") or "").split()
        counts = idx.get(_nm[-1].lower()) if _nm else None
        if not counts:
            continue
        bits = [f"{n} {k}" for k, n in
                sorted(counts.items(), key=lambda kv: ("out", "doubtful",
                                                       "questionable").index(kv[0])
                       if kv[0] in ("out", "doubtful", "questionable") else 9)]
        if bits:
            parts.append(f"{esc(t.get('abbr') or '')} " + " \u00b7 ".join(bits))
    if parts:
        rows.append(("Designations", " \u00b7 ".join(parts)))
    if g.get("state") == "pre":
        both = all(_ia_for_game(g, ia_index, s) for s in ("away", "home"))
        dt = _utc_dt(g.get("start_utc") or "")
        if both:
            rows.append(("Inactives", "posted"))
        elif dt:
            # UX-13: "post about 11:30 AM ET" on a card for Sunday told a Thursday
            # reader the wrong thing. Beyond a day out the line carries its day.
            import datetime as _d
            _at = dt - _d.timedelta(minutes=90)
            _far = (dt - _build_now()).total_seconds() > 24 * 3600
            _when = (f'{_at.astimezone(_ET).strftime("%a")} {_et_clock(_at)}'
                     if _far else _et_clock(_at))
            rows.append(("Inactives", f"post about {_when}"))
    else:
        n = sum(1 for s in ("away", "home") if _ia_for_game(g, ia_index, s))
        if n:
            rows.append(("Inactives", "posted"))
    return rows


_TK_NICKS = {}


def _tk_lead_team(league, title):
    """The team nickname the headline opens with, lowercased, or "".

    Only the first six words: a headline's subject is at its front, and scanning the
    whole line would make every mention a subject, which is the thing this guards.
    """
    if not league:
        return ""
    if league not in _TK_NICKS:
        pool = set()
        for L in ((SB_DATA or {}).get("leagues") or []):
            if L.get("league") != league:
                continue
            for gg in (L.get("games") or []):
                for side in ("away", "home"):
                    nm = ((gg.get(side) or {}).get("name") or "").strip().lower()
                    if nm:
                        pool.add(nm)
        _TK_NICKS[league] = pool
    pool = _TK_NICKS.get(league) or set()
    if not pool:
        return ""
    for w in re.findall(r"[A-Za-z0-9'&.-]+", title)[:6]:
        if w.lower() in pool:
            return w.lower()
    return ""


_TK_FULLNAME = {}


def _tk_full_name(league, team_id):
    """The team's full name for a league and team id, or "".

    NFL only, from the inactives board, which names every team it has seen in full and
    carries the same ids the scoreboard uses. Keyed on (league, id): the pair is the
    identity, the id alone is not (ids repeat across leagues).
    """
    if league != "NFL" or not team_id:
        return ""
    if not _TK_FULLNAME:
        for t in ((IA_BOARD or {}).get("teams") or []):
            if t.get("id") and t.get("team"):
                _TK_FULLNAME[("NFL", str(t["id"]))] = t["team"]
    return _TK_FULLNAME.get((league, str(team_id)), "")


def _tk_story(g, items):
    """SC-7: the newest desk story naming either team, inside three days before the
    game, or the recap once it is final. No match, no line: there is never a filler.

    The Wire (W-5, Sprint I) replaces this pool; the rule it is matched by does not
    change, so this is the same function with a wider source later.

    THE MATCH KNOWS THE LEAGUE. "Giants" is San Francisco in a story tagged MLB and New
    York in one tagged NFL, and a nickname alone would hand a Yankees headline to the
    Jets. A story qualifies only when its tags carry this game's league.
    """
    league = (g.get("league") or "").upper()
    # A NICKNAME IS A SHALLOW KEY. The first cut matched the feed's team name against
    # the story's title, dek and key fact, and handed the Lions-Bills card a story about
    # television ratings: its key fact contained the word "bills". Half the NFL's
    # nicknames are ordinary English (Bills, Giants, Saints, Chiefs, Rams, Bears,
    # Titans, Commanders, Texans, Packers, Eagles, Cardinals, Falcons, Panthers), so a
    # bare nickname will keep finding stories that are not about the team.
    #
    # The full name is the identity, and the inactives board holds it per team id for
    # the NFL. Where it is known the match requires it. Where it is not, the nickname
    # must appear in the HEADLINE, which is a claim about what the story is about,
    # never in a key fact, which is a detail inside one. Case-sensitive either way.
    full, nicks = [], []
    for side in ("away", "home"):
        t = g.get(side) or {}
        nick = (t.get("name") or "").strip()
        fn = _tk_full_name(league, t.get("id"))
        if fn:
            full.append(fn)
        elif len(nick) > 2:
            nicks.append(nick)
    if not (full or nicks) or not items:
        return ""
    kick = _utc_dt(g.get("start_utc") or "")
    if not kick:
        return ""
    import datetime as _d
    lo = kick - _d.timedelta(days=3)
    best = None
    for it in items:
        tags = [t.upper() for t in tags_for(it)] + [(it.get("league") or "").upper()]
        if league and league not in tags:
            continue
        title = it.get("title") or ""
        body = " ".join([title, it.get("dek") or ""])
        hit = any(re.search(r"\b" + re.escape(n) + r"\b", body) for n in full) or \
              any(re.search(r"\b" + re.escape(n) + r"\b", title) for n in nicks)
        if not hit:
            continue
        # NAMING A TEAM IS NOT BEING ABOUT IT. "Dodgers clinch playoff berth ... ties
        # Braves record" names the Braves and belongs on no Atlanta card. When the
        # headline opens with a different team in the same league, that team is the
        # subject and this is not the game's story.
        subj = _tk_lead_team(league, title)
        if subj and subj not in {n.lower() for n in nicks} | {
                f.split()[-1].lower() for f in full}:
            continue
        when = _parse_utc(it)
        if not when or when < lo:
            continue
        if g.get("state") != "post" and when > kick:
            continue
        if best is None or (_parse_utc(best) or when) < when:
            best = it
    if not best:
        return ""
    return (f'<div class="tk-stry">{verdict_badge(best.get("verdict"), best)}'
            f'<a href="/articles/{esc(best["slug"])}.html">'
            f'{esc(best.get("title") or "")}</a></div>')


def _tk_leaders(g):
    """Punch item 12: three leaders on a live or final card, from the fantasy points the
    desk already computes for every started game.

    The marquee's live state was the stub, a story line and two buttons, with a couple
    of hundred pixels under it and "Game page" alone at the bottom. That is the product
    missing from the product: a reader watching a live game wants the names.

    Nothing at all when the box score has no players yet, which is every game before
    kickoff. There is no placeholder."""
    if g.get("state") not in ("in", "post"):
        return []
    pts = (LIVE_POINTS or {}).get(g.get("id")) or \
          (LIVE_POINTS or {}).get(str(g.get("id"))) or {}
    if not pts:
        # C-2: THE DESK COMPUTES POINTS FOR THE NFL AND NOWHERE ELSE, so a live
        # baseball, hockey or basketball card named nobody at all: the block was absent
        # rather than empty, which reads as "nothing happened". The feed carries its own
        # leaders for most of them, stated as the feed states them, and they are used
        # only where the desk has nothing of its own. Measured on tonight's board: 30 of
        # 46 started games have them.
        return [(f'{L["name"]} {L["cat"]}'.strip(), (L["line"] or "")[:34])
                for L in (g.get("leaders") or [])[:3]]
    # fantasy_points.leaders is the desk's own ranking, and it is the one the live
    # board and the game page already use. Reimplementing the sort here would be a
    # second definition of "leader" that could disagree with the page it links to.
    import fantasy_points as _fp
    rows = []
    for p in _fp.leaders(pts, n=3):
        line = "; ".join(p.get("line") or [])
        rows.append((f'{p.get("name", "")} {p.get("ppr", 0):.1f}', line[:34]))
    return rows


def _tk_winprob(g):
    """C-3: the win probability, as one model last stated it, on a live game only.

    THE DESK PUBLISHES NO FORECAST OF ITS OWN, and this is not one. It is the same shape
    as the line: a number a named company produced, carried as a fact about what that
    company said. Nothing here is modelled or derived, and the model is named on the row
    exactly as the provider is named beside a spread.

    Never on a final. The track ends when the game does, so the last reading of a
    finished game is 100% or 0% for every game ever played, which restates the result as
    a percentage and tells a reader nothing they cannot see in the score.

    Never a bare "51%" either: a probability with no side attached is the one number on
    a card that can be read exactly backwards.
    """
    if g.get("state") != "in":
        return ""
    v = (LIVE_WP or {}).get(str(g.get("id")))
    if v is None:
        return ""
    home = (g.get("home") or {}).get("abbr") or "Home"
    away = (g.get("away") or {}).get("abbr") or "Away"
    # The side with the better of the two is the one named, because "BUF 68%" is read
    # correctly by everyone and "32%" beside two team names is read correctly by nobody.
    ab, pct = (home, v) if v >= 0.5 else (away, 1.0 - v)
    n = int(round(pct * 100))
    return (f'<div class="tk-wp" data-lens-only="lines">'
            f'<span class="wp-bar" aria-hidden="true">'
            f'<i style="width:{n}%"></i></span>'
            f'<span class="wp-v">{esc(ab)} {n}% to win</span>'
            f'<span class="wp-src" data-wp-model="ESPN">ESPN\'s model</span></div>')


def _tk_linescore(g):
    """C-2: how the score happened, not just what it is.

    The card said 41-31 and nothing about the four quarters that produced it, which is
    the difference between a result and a game. The feed carries the periods for every
    league that has them, in its own display form, and the desk does not name them: it
    numbers them in the order they were played and lets the league's own count say
    whether that is a quarter, an inning or a period.

    Only where BOTH sides have periods and the counts agree. A half-filled linescore is
    a table with a hole in it, and the total is what the card already says.
    """
    if g.get("state") not in ("in", "post"):
        return ""
    a, h = g.get("away") or {}, g.get("home") or {}
    pa, ph = a.get("periods") or [], h.get("periods") or []
    if not pa or len(pa) != len(ph):
        return ""
    n = len(pa)
    head = "".join(f"<th>{i + 1}</th>" for i in range(n))

    def row(t, ps):
        sc = _tk_score(t)
        cells = "".join(f"<td>{esc(x)}</td>" for x in ps)
        tot = f'<td class="ls-t">{sc if sc is not None else ""}</td>'
        return (f'<tr><th scope="row">{esc(t.get("abbr") or "")}</th>'
                f'{cells}{tot}</tr>')

    return ('<div class="tk-ls"><table class="ls">'
            f'<thead><tr><th><span class="sr-only">Team</span></th>{head}'
            '<th class="ls-t">T</th></tr></thead>'
            f'<tbody>{row(a, pa)}{row(h, ph)}</tbody></table></div>')


_TK_CLOCK = re.compile(r"^\s*0*:?0*0?\s*$|^\s*0:00\s*$")


def _tk_state(g):
    """H-2: what state this game is in, in the feed's own words.

    The cards read the feed's `detail`, which is a CLOCK. Baseball has no clock, so
    every MLB card printed "0:00": folded finals said it in the status slot and the
    live marquee said "Live \u00b7 MLB \u00b7 0:00", on all five live games. The same
    holds for tennis and golf, and in this snapshot `detail` is "0:00" for every league
    including football, because only a game actually in play populates it.

    `status_short` is the feed's own human string and it is always right: "Final",
    "Final/13", "Top 6th", "Bot 1st". It leads. The clock is appended only when it is a
    real running clock, which is what makes "3rd Quarter 5:21" possible without letting
    a zero through."""
    short = (g.get("status_short") or "").strip()
    detail = (g.get("detail") or "").strip()
    clock_is_real = detail and not _TK_CLOCK.match(detail) and detail != "0:00"
    if short and clock_is_real and detail not in short:
        return f"{short} \u00b7 {detail}"
    if short:
        return short
    return detail if clock_is_real else ""


def _tk_kicker(g):
    """The stub's top line: league, week and day, or the live state."""
    league = esc(g.get("league") or "")
    if g.get("state") == "in":
        det = esc(_tk_state(g) or "Live")
        return f'<span class="tk-k live"><span class="dot"></span>Live \u00b7 {league} \u00b7 {det}</span>'
    if g.get("state") == "post":
        return f'<span class="tk-k">{league} \u00b7 Final</span>'
    bits = [league]
    if league == "NFL":
        wk, _ = nfl_week()
        if wk:
            bits.append(f"Week {wk}")
    dt = _utc_dt(g.get("start_utc") or "")
    if dt:
        bits.append(dt.astimezone(_ET).strftime("%A"))
    line = _TK_MID.join(bits)
    return f'<span class="tk-k">{esc(line)}</span>'


def _tk_line(g):
    """B-2 and the 20 September law: the line, as a fact, with the provider named.

    The number and its attribution are built together and returned together, so there
    is no path through this function that prints a spread nobody set. odds_gate checks
    the rendered page for exactly that.

    No pick, no advice, no link to a book: what the card says is what one company was
    offering, and who was offering it.
    """
    ln, opened = _tk_logged(g)
    prov = ln.get("provider")
    if not prov:
        return ""
    bits = []
    if ln.get("detail"):
        bits.append(esc(str(ln["detail"])))
    if ln.get("total") is not None:
        bits.append(f'O/U {esc(str(ln["total"]))}')
    ml = [f'{side.upper()} {esc(str(ln[key]))}'
          for side, key in (("away", "ml_away"), ("home", "ml_home")) if ln.get(key)]
    if not bits:
        return ""
    return (f'<div class="tk-line" data-lens-only="lines" '
            f'data-line-spread="{esc(str(ln.get("spread", "")))}">'
            f'<span class="tk-line-v">{" &middot; ".join(bits)}</span>'
            + (f'<span class="tk-line-ml">{" &middot; ".join(ml)}</span>' if ml else "")
            + opened
            + f'<span class="tk-line-src" data-line-provider="{esc(prov)}">'
              f'{esc(prov)} via ESPN</span></div>')


def _tk_countdown(g):
    """B-2: the stub is never empty before kickoff. The countdown is written by the
    client from the kickoff the card already carries, because a countdown baked at
    build time is wrong the moment it is served."""
    if g.get("state") != "pre" or not g.get("start_utc"):
        return ""
    return ('<span class="tk-count-dn" data-lens-only="watch" data-countdown '
            f'data-kick="{esc(g.get("start_utc") or "")}"></span>')


def _tk_disc(g, t, side):
    """B-2: the two-letter disc, in the team's own colour, at the head of a row.

    Without logos the card needs one piece of instant recognition, and on the board it
    is this: the abbreviation in a filled circle in the team's colour, drawn from the
    colour the card already carries, so it costs no licence and works for every club in
    every league.

    Aria-hidden because the row already names the team: a screen reader hearing "CAR,
    Carolina" twice is the disc being read as content when it is recognition.
    """
    col = _tk_colors(g)[0 if side == "away" else 1]
    ab = (t.get("abbr") or "")[:3]
    if not ab:
        return ""
    return (f'<span class="tk-disc" style="--d:{col}" aria-hidden="true">'
            f'{esc(ab)}</span>')


_TK_FAV = re.compile(r"^([A-Z&.\-]{2,5})\s*([+-]\d+(?:\.\d+)?)$")


def _tk_logged(g):
    """C-1 and the law's second clause: the line now, and the line at open beside it.

    Returns (line, opened_markup). The line is the feed's when the feed has one and the
    logged reading when it does not, which is every game that has kicked off: ESPN drops
    the odds object at kickoff, so on the Sunday night slate 0 of 61 finals and 0 of 6
    live games carried one. Without the log there is no line on any card after kickoff
    and no cover ruling on any final, ever.

    The open line prints only when it MOVED. "Opened KC -6" beside "KC -6" is the same
    fact twice, and a card that says everything twice is a card nobody reads.
    """
    feed = g.get("line") or {}
    try:
        import lines as _lnmod
        rec = _lnmod.for_game(LINES_DATA, g.get("id"))
    except Exception:
        rec = None
    if not rec:
        return (feed, "")
    now = dict(rec.get("now") or {})
    now["provider"] = rec.get("provider") or feed.get("provider") or ""
    use = feed if feed.get("provider") else now
    op = rec.get("open") or {}
    moved = int(rec.get("moves") or 0) and op.get("detail") and \
        op.get("detail") != (use.get("detail") or now.get("detail"))
    if not moved:
        return (use, "")
    return (use, f'<span class="tk-line-open">Opened {esc(str(op["detail"]))}</span>')


def _tk_marks(g, t, side):
    """B-2: possession and timeouts, for the side that has them.

    All three of these were already in the situation object the down-and-distance line
    came from, and none of them were being read. A live football card without the ball
    is a card that cannot tell you who is driving.

    Timeouts print at zero. "No timeouts" is the single most consequential fact in a
    two-minute drill, and treating it as an absence prints nothing at the moment the
    reader most wants it.
    """
    if g.get("state") != "in":
        return ""
    out = ""
    tid = str(t.get("id") or "")
    if tid and str(g.get("possession") or "") == tid:
        out += '<span class="tk-poss" title="Has the ball" aria-label="Has the ball">' \
               '&#9679;</span>'
    n = g.get("to_away") if side == "away" else g.get("to_home")
    if isinstance(n, int) and 0 <= n <= 3:
        pips = "".join(f'<i class="{"on" if i < n else "off"}"></i>' for i in range(3))
        out += (f'<span class="tk-to" aria-label="{n} timeout'
                f'{"" if n == 1 else "s"} left">{pips}</span>')
    return out


def _tk_redzone(g, t):
    """The tint goes on the chip of the team INSIDE the twenty, which is the team with
    the ball. The feed's isRedZone says a game is in one; it does not say whose."""
    if g.get("state") != "in" or not g.get("red_zone"):
        return ""
    tid = str(t.get("id") or "")
    return " rz" if tid and str(g.get("possession") or "") == tid else ""


def _ruling_text(g):
    """The cover and total ruling as plain text, for the share card. The same function
    decides it as decides the page, and the markup is stripped rather than the logic
    being written twice: two implementations of "did the favourite cover" is two answers
    waiting to disagree on the one artefact a reader cannot check.
    """
    h = _tk_ruling(g)
    if not h:
        return ""
    import re as _re
    body = h.split('<span class="tk-ruling-src"')[0]
    return _re.sub(r"<[^>]+>", "", body).replace("&middot;", "\u00b7").strip()


def _tk_ruling(g):
    """The law of 20 September, the last clause: on finals, whether the favourite
    covered and whether the total went over.

    A ruling, not a verdict on anyone's bet: it is arithmetic on two numbers the card
    already prints, and it is only ever stated about the line one named provider set.
    No line, no provider, no ruling. A tie on either number is a push and says so.

    The FAVOURITE comes from the feed's own detail string ("KC -6.5"), never from the
    sign of the spread field, because the sign's frame of reference is the feed's and a
    silent flip would print the wrong team as the one that covered.
    """
    if g.get("state") != "post":
        return ""
    ln, _ = _tk_logged(g)
    if not ln.get("provider"):
        return ""
    a, h = g.get("away") or {}, g.get("home") or {}
    sa, sh = _tk_score(a), _tk_score(h)
    if sa is None or sh is None:
        return ""
    bits = []
    m = _TK_FAV.match(str(ln.get("detail") or "").strip())
    if m:
        fav_ab, num = m.group(1), float(m.group(2))
        by = abs(num)
        if fav_ab == (h.get("abbr") or ""):
            margin = sh - sa
        elif fav_ab == (a.get("abbr") or ""):
            margin = sa - sh
        else:
            margin = None
        if margin is not None and num < 0:
            bits.append(f"{fav_ab} covered" if margin > by else
                        (f"{fav_ab} did not cover" if margin < by else
                         f"{fav_ab} pushed"))
    if ln.get("total") is not None:
        try:
            tot = float(ln["total"])
        except (TypeError, ValueError):
            tot = None
        if tot is not None:
            pts = sa + sh
            bits.append(f"Over {_fmt_line_num(tot)}" if pts > tot else
                        (f"Under {_fmt_line_num(tot)}" if pts < tot else
                         f"Pushed {_fmt_line_num(tot)}"))
    if not bits:
        return ""
    return (f'<div class="tk-ruling" data-lens-only="lines">{esc(_TK_MID.join(bits))}'
            f'<span class="tk-ruling-src" data-ruling-provider="{esc(ln.get("provider") or "")}">'
            f'vs {esc(ln.get("provider") or "")} via ESPN</span></div>')


def _fmt_line_num(v):
    """46.5 stays 46.5; 47.0 becomes 47. A trailing zero on a total reads as a
    precision the line does not have."""
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _tk_trec(t):
    """B-2: A RECORD BELONGS TO THE TEAM, not to a line under both of them.

    The card joined them into one line, "Steelers 1-0 \u00b7 Patriots 0-1", which reads
    as a sentence about the game rather than a fact about each side, and once the rows
    stacked it sat under the pair naming them again in the order they already appear in.
    The record rides with its team, in mono, and the joined line stays on the layouts
    that still run the names inline (see .tk-rec[data-role=rec] in the stylesheet).
    """
    r = (t or {}).get("record") or ""
    return f'<span class="tk-trec">{esc(r)}</span>' if r else ""


def _tk_matchup(g, big=40):
    """The 40px matchup, with SC-9 colour on live and final."""
    # CFB-1: two school names do not fit the 40px a three-letter code was sized for.
    # The TYPE steps down rather than the names being cut, because a truncated school
    # is the abbreviation problem again with an ellipsis on the end.
    _full = (g.get("league") or "") in FULL_NAME_LEAGUES
    _fcls = " tk-num-full" if _full else ""
    if _full:
        big = 24
    ca, ch = _tk_sc9(g)
    a, h = g.get("away") or {}, g.get("home") or {}
    sa, sh = _tk_score(a), _tk_score(h)
    started = g.get("state") in ("in", "post")
    # UX-1: THE SCORE COLOURS NEEDED A SURFACE OF THEIR OWN. SC-9's green and red sat
    # straight on the team wash, so a green score on a red wash and a red score on a
    # blue one were the two worst pairings on the card. Each team now sits in a smoke
    # chip: a dark translucent fill that gives both colours the same ground whatever
    # the wash behind it, with the leader carrying a bar in its own green and its text
    # at 800, the trailer at 500, and a tie carrying no bar at all.
    #
    # Pre-game keeps the inline matchup in plain white: there is no leader before
    # kickoff, and a chip with nothing to say is a box around a fact.
    #
    # L-3: each half stays addressable so a poll rewrites the score and the colour in
    # place without touching the rest of the card.
    if not started:
        def plain(t, which):
            # CFB-1: the rank sits OUTSIDE the polled node. The live poll rewrites
            # [data-side] by textContent, so a badge inside it would be wiped by the
            # first score that arrived. data-label tells the poll what to print back.
            # B-2: ONE ELEMENT PER TEAM. The disc, the rank and the name were three
            # siblings, so stacking the rows put the disc on a line of its own.
            return (f'<span class="tk-side">{_tk_disc(g, t, which)}'
                    f'{_rank_html(g, t)}'
                    f'<span data-side="{which}" data-abbr="{esc(t.get("abbr") or "")}" '
                    f'data-label="{esc(_team_label(g, t))}" '
                    f'style="color:#FFFFFF">{esc(_team_label(g, t))}</span>'
                    f'{_tk_trec(t)}</span>')
        return (f'<span class="tk-num{_fcls}" style="font-size:{big}px">'
                f'{plain(a, "away")} <span class="tk-at">at</span> '
                f'{plain(h, "home")}</span>')

    tie = ca == ch
    def chip(t, sc, col, which):
        lead = (col == _TK_UP) and not tie
        cls = "tk-chip-score" + (" lead" if lead else "") + _tk_redzone(g, t)
        bar = (f'<i style="background:{col}"></i>' if lead else "")
        return (f'<span class="{cls}" style="color:{col};'
                f'font-weight:{800 if lead else 500}">{bar}{_tk_disc(g, t, which)}{_rank_html(g, t)}'
                f'<span data-side="{which}" data-abbr="{esc(t.get("abbr") or "")}" '
                f'data-label="{esc(_team_label(g, t))}">'
                f'<span class="tk-nm">{esc(_team_label(g, t))}</span>'
                f'<span class="tk-sc">{sc if sc is not None else ""}</span>'
                f'</span>{_tk_trec(t)}{_tk_marks(g, t, which)}</span>')
    return (f'<span class="tk-num tk-num-chips{_fcls}" style="font-size:{big}px">'
            f'{chip(a, sa, ca, "away")}{chip(h, sh, ch, "home")}</span>')


def _edition_label(ed):
    """UX-9 (S-7): the Edition card names the edition it links to.

    It said "Read tonight's Edition" at 8 AM, over an edition published the previous
    evening. The card names the edition by its date, and says "tonight's" only once
    that evening's edition has actually published: the word is a claim about what is
    behind the link, not a time of day.
    """
    when = _parse_utc(ed) if ed else None
    if not when:
        return "Read the Edition"
    et = when.astimezone(_ET)
    today = _build_now().astimezone(_ET).date()
    if et.date() == today:
        return "Read tonight\u2019s Edition"
    return f'The Edition \u00b7 {MONTHS[et.month]} {et.day}'


def _unused(pool, n):
    """UX-11: the first n stories not already on this page, claiming as it goes."""
    out = []
    for i in (pool or []):
        if len(out) >= n:
            break
        if _claim(i.get("slug")):
            out.append(i)
    return out


_PAGE_USED = set()


def _page_reset():
    """UX-11: a new page starts with nothing claimed."""
    _PAGE_USED.clear()


def _claim(slug):
    """UX-11 (S-9): one appearance per story per page.

    The homepage linked 29 distinct stories 47 times: one four times, another three,
    thirteen twice. A story in "From the desk" and again in the Record's read-further
    list is the same page telling the reader twice, and it costs the slot a second
    story would have had.

    Blocks claim in render order, so the earliest and most prominent placement keeps
    the story and later blocks skip it. Returns False when the story is already on the
    page.
    """
    if not slug:
        return True
    if slug in _PAGE_USED:
        return False
    _PAGE_USED.add(slug)
    return True


def _storyline_open(entry, now=None):
    """UX-10: is this storyline inside its window today?

    A storyline with no window is evergreen and always open. A window is [MM-DD, MM-DD]
    and may wrap the new year, which is why this compares month-day rather than dates.
    """
    w = (entry or {}).get("window")
    if not w or len(w) != 2:
        return True
    today = (now or _build_now()).astimezone(_ET).strftime("%m-%d")
    start, end = w[0], w[1]
    if start <= end:
        return start <= today <= end
    return today >= start or today <= end      # a window that crosses the new year


def _day_time(g):
    """UX-9: "Thu 8:15 PM ET". The site's one time format, from the game's own
    timestamp rather than from whatever string the feed happened to send."""
    dt = _utc_dt(g.get("start_utc") or g.get("kickoff_utc") or "")
    if not dt:
        return ""
    return f'{dt.astimezone(_ET).strftime("%a")} {_et_clock(dt)}'


def _tk_rec_html(g):
    """The two lines, as markup. The second is omitted when there is nothing to say."""
    recs, when = _tk_records(g)
    out = f'<div class="tk-rec" data-role="rec">{esc(recs)}</div>'
    if when:
        out += f'<div class="tk-rec tk-when" data-role="when">{esc(when)}</div>'
    return out


def _tk_records(g):
    """UX-3 (S-3): TWO LINES. Records on the first, day and time on the second.

    H-9 put the whole line on one row and gave it white-space:nowrap with an ellipsis
    to stop it wrapping before "ET". That stopped the wrap by cutting the time off
    instead: "Steelers 1-0 \u00b7 Patriots 0-1 \u00b7 Sun 1:00 PM..." on /scores at 1440.
    A time is never truncated anywhere on this site, and the fix for a line that is too
    long is a second line, not an ellipsis.

    Note for the next reader: the audit's test, grepping site/publish for "PM..." or
    "AM...", cannot see this. The ellipsis was drawn by CSS text-overflow and never
    existed in the HTML. The real test measures the rendered element.
    """
    bits = []
    for s in ("away", "home"):
        t = g.get(s) or {}
        if t.get("name") and t.get("record"):
            bits.append(f"{t['name']} {t['record']}")
    if g.get("state") == "in":
        when = g.get("situation") or ""
    elif g.get("state") == "post":
        when = ""
    else:
        dt = _utc_dt(g.get("start_utc") or "")
        if dt:
            # H-9: the board's line is "Lions 1-0 \u00b7 Bills 1-0 \u00b7 Thu 8:15 PM
            # ET": the weekday and the time, as one part, with no day of month. Mine
            # carried "Thu 17 Sep" and the clock as two parts, which wrapped before
            # "ET" on the marquee at 1440 and again on phone. The date is on the card
            # above it and on the page; the reader needs the day and the hour.
            when = f'{dt.astimezone(_ET).strftime("%a")} {_et_clock(dt)}'
    return (_TK_MID.join(b for b in bits if b), when)


def _tk_card(g, ia_index, wx=None, desig=None, items=None, buttons=True):
    """SC-1: the full Ticket card. Three states; only the lines that exist render."""
    a_col, b_col = _tk_colors(g)
    state = g.get("state")
    net = (f'<span class="tk-chip" data-lens-only="watch">{esc(g.get("network"))}'
           f'</span>' if g.get("network") else "")
    # B-3: the spec grid holds two different KINDS of fact, and the lenses separate
    # them: where and in what weather is a watching fact, who is out is a fantasy one.
    # They render as two grids rather than one so a lens can take either without the
    # other, and with no lens chosen they sit one above the other exactly as before.
    venue = _tk_venue(g, wx)
    watch_rows = [("Venue", venue)] if (venue and state == "pre") else []
    fan_rows = _tk_avail(g, ia_index, desig)

    def _grid(rr, lens):
        if not rr:
            return ""
        return (f'<div class="tk-spec" data-lens-only="{lens}">' + "".join(
            f'<span class="sk">{esc(k)}</span><span class="sv">{esc(v)}</span>'
            for k, v in rr) + '</div>')

    spec = _grid(watch_rows, "watch") + _grid(fan_rows, "fantasy")
    leaders = _tk_leaders(g)
    lead_html = ""
    if leaders:
        lead_html = '<div class="tk-l3" data-lens-only="fantasy">' + "".join(
            f'<div><b>{esc(n)}</b>{esc(d)}</div>' for n, d in leaders) + '</div>'
    ls_html = _tk_winprob(g) + _tk_linescore(g)
    story = _tk_story(g, items or [])
    btns = ""
    if buttons:
        gp = f'/games/{esc(str(g.get("id")))}.html'
        # H-8: a button that does not go where it says is filler. "Box score" pointed
        # at /scores.html, which is the board the reader just came from. It links to
        # this game's leaders block when the desk holds one, and when it does not the
        # button is absent rather than pointing somewhere plausible.
        if state in ("in", "post"):
            has_box = bool((LIVE_POINTS or {}).get(g.get("id"))
                           or (LIVE_POINTS or {}).get(str(g.get("id"))))
            second = (f'<a class="tk-btn ghost" href="{gp}#box">Box score</a>'
                      if has_box else "")
        else:
            second = ('<a class="tk-btn ghost" href="/where-to-watch.html">'
                      'Where to watch</a>')
        # B-2: the whole card is the link; the two controls become quiet links beside
        # it. "Where to watch" is the network chip, so the second control is dropped
        # where a network is already shown on the card.
        btns = (f'<div class="tk-btns"><a class="tk-btn" href="{gp}">Game page</a>'
                f'{second}</div>'
                f'<a class="tk-card-a" href="{gp}" tabindex="-1" aria-hidden="true"></a>')
    wide = " wide" if state in ("in", "post") else ""
    # A-2: the card carries what the recount needs, so the counts and the "Next" line
    # are read off the board rather than baked into the header.
    _kd = _utc_dt(g.get("start_utc") or "")
    return (f'<article class="tk-c{wide}" data-gid="{esc(str(g.get("id")))}" '
            f'data-league="{esc(g.get("league") or "")}" data-state="{esc(state or "")}" '
            f'data-kick="{esc(g.get("start_utc") or "")}" '
            f'data-kick-et="{esc(_et_clock(_kd) if _kd else "")}" '
            f'data-away="{esc((g.get("away") or {}).get("abbr") or "")}" '
            f'data-home="{esc((g.get("home") or {}).get("abbr") or "")}" '
            f'style="--a:{a_col};--b:{b_col}">'
            f'<div class="tk-stub" style="--a:{a_col};--b:{b_col}">'
            f'<div class="tk-stub-top"><span data-role="kicker">{_tk_kicker(g)}</span>'
            f'{net}</div>'
            f'<div class="tk-mu" data-role="mu">{_tk_matchup(g)}</div>'
            f'{_tk_rec_html(g)}'
            f'{_tk_countdown(g)}'
            f'{_tk_line(g)}'
            f'{_tk_ruling(g)}'
            f'</div><div class="tk-perf"></div>'
            f'<div class="tk-body">{spec}{ls_html}{lead_html}{story}{btns}'
            f'</div></article>')


def _tk_fold(g, ia_index, desig=None):
    """SC-2: the same card folded. A 6px bar per row, the teams, the score or time, the
    status line, the network, and one fact line. Clicking it opens the full card in
    place; with no script it is a link to the game page, which is the same information.
    """
    a_col, b_col = _tk_colors(g)
    ca, ch = _tk_sc9(g)
    state = g.get("state")
    started = state in ("in", "post")
    def row(side, col):
        t = g.get(side) or {}
        sc = _tk_score(t)
        # UX-1: the same chip at row scale, with the leader's bar and weight.
        _tie = ca == ch
        _lead = (col == _TK_UP) and not _tie
        _cls = "s sc" + (" lead" if _lead else (" trail" if col and not _tie else ""))
        _bar = f'<i style="background:{col}"></i>' if _lead else ""
        val = (f'<span class="{_cls}" data-side="{side}" style="color:{col}">'
               f'{_bar}{sc}</span>'
               if started and sc is not None
               else f'<span class="s" data-side="{side}"></span>')
        # UX-1 adjustment: on a folded row the abbreviation is WHITE. Coloured, it sat
        # bare on the team wash with no chip under it, and PHI in red on the Phillies'
        # red was the case that proved it. The chip carries the colour and the bar; the
        # abbreviation carries the name.
        # data-abbr carried the side name here ("away"/"home") rather than the
        # abbreviation, which is what the other two chip sites put in it. Anything
        # reading data-abbr across the band therefore saw 34 "away" and 34 "home"
        # before it saw a single team. The side has its own attribute.
        # CFB-1: the bold slot carries whatever this league calls the team, and the
        # poll rank rides in front of it. data-abbr keeps the ABBREVIATION whatever is
        # printed, because the team pin and the live poll both match on it.
        _full = (g.get("league") or "") in FULL_NAME_LEAGUES
        _bcls = ' class="full"' if _full else ""
        ab = (f'<b{_bcls} data-side="{side}" '
              f'data-abbr="{esc(t.get("abbr") or "")}">'
              f'{_rank_html(g, t)}{esc(_team_label(g, t))}</b>')
        # CFB-2: the grey line is the mascot and the record, which is what makes one
        # "Miami" the Hurricanes and the other the Dolphins. The mascot drops out on its
        # own where it would only repeat the bold slot, and then the record stands alone.
        _tail = " ".join(x for x in (esc(_team_mascot(g, t)),
                                     esc(t.get("record") or "")) if x)
        return (f'<div class="t"><i style="background:{_tk_colors(g)[0 if side == "away" else 1]}"></i>'
                f'{ab}<span>{_tail}</span></div>{val}')
    when = ""
    if not started:
        dt = _utc_dt(g.get("start_utc") or "")
        if dt:
            when = f'{dt.astimezone(_ET).strftime("%a")} {_et_clock(dt)}'
    status = esc(_tk_state(g)) if started else esc(when)
    net = (f'<span class="tk-chip sm">{esc(g.get("network"))}</span>'
           if g.get("network") else "")
    facts = _tk_avail(g, ia_index, desig)
    fact = f'<div class="x">{esc(facts[0][0])} {esc(facts[0][1])}</div>' if facts else ""
    wide = " wide" if started else ""
    return (f'<a class="tk-fold{wide}" data-gid="{esc(str(g.get("id")))}" '
            f'data-league="{esc(g.get("league") or "")}" '
            f'data-state="{esc(state or "")}" style="--a:{a_col};--b:{b_col}" '
            f'href="/games/{esc(str(g.get("id")))}.html">'
            f'{row("away", ca)}{row("home", ch)}'
            f'<div class="st"><span data-role="status">{status}</span>{net}</div>'
            f'{fact}</a>')


LENSES = (("all", "All", "every fact the card holds"),
          ("lines", "Lines", "the spread, the total and where it opened"),
          ("fantasy", "Fantasy", "who is out, and who is scoring"),
          ("watch", "Watch", "the network, the venue and the countdown"))


def lens_control():
    """B-3: THE LENS. Four ways to read the same board.

    A tab chooses which GAMES are on the board. A lens chooses which FACTS each card
    shows, which is a different question and was not being asked: the card carried the
    line, the inactives, the leaders, the network and the venue all at once, so every
    reader paid for every other reader's interest.

    Called Lines and not Bets. The desk shows a line as a fact and makes no bet, the
    Standards page calls the section Lines, and a control named for an activity the desk
    does not do would be the one word on the page that contradicts the doctrine.

    No script, no lens: the control ships hidden and the hiding is done by CSS keyed on
    an attribute only the script sets, so a reader without JavaScript sees the whole
    card and no dead buttons. That is also what a crawler sees.
    """
    bs = "".join(
        f'<button type="button" class="lens-b{" on" if k == "all" else ""}" '
        f'data-lens="{k}" aria-pressed="{"true" if k == "all" else "false"}" '
        f'title="{esc(why)}">{esc(label)}</button>'
        for k, label, why in LENSES)
    return ('<div class="lens" role="group" hidden '
            'aria-label="Choose which facts each card shows">'
            f'<span class="lens-k">Show</span>{bs}</div>')


def _tk_tabs(games, active="all", href="/scores.html"):
    """SC-4: the league switcher. Each tab carries its count today or its next date.

    A league with nothing today shows its next slate rather than a zero, because a zero
    reads as "this league is off" when the truth is "not until Saturday". Tabs are real
    links to /scores#nfl so they work with no script at all.
    """
    import datetime as _d
    today = _build_now().astimezone(_ET).date()
    by_league = {}
    for g in games:
        by_league.setdefault(g.get("league"), []).append(g)
    out = []
    n_today = sum(1 for g in games
                  if (_utc_dt(g.get("start_utc") or "") or _d.datetime.max.replace(
                      tzinfo=_d.timezone.utc)).astimezone(_ET).date() == today)
    n_live = sum(1 for g in games if g.get("state") == "in")
    sub_all = f"{n_today} today" if n_today else "next up"
    if n_live:
        sub_all = f"{n_live} live"
    out.append((["", " on"][active == "all"], "All", sub_all, "all"))
    # CFB-1: the tab strip is the band's order, so the tabs and the cards under them
    # cannot disagree about which league leads today.
    for name in _day_league_order():
        gs = by_league.get(name)
        if not gs:
            continue
        mine_today = [g for g in gs
                      if (_utc_dt(g.get("start_utc") or "") or _d.datetime.max.replace(
                          tzinfo=_d.timezone.utc)).astimezone(_ET).date() == today]
        live = sum(1 for g in gs if g.get("state") == "in")
        if live:
            sub = f"{live} live"
        elif mine_today:
            # M-21: A TAB THAT HOLDS A FINAL SAYS SO. "1 today" over a board of one
            # finished game tells a reader there is something to come. The count line
            # below carries the full sentence with the next kickoff.
            _fin_t = [x for x in mine_today if x.get("state") == "post"]
            sub = (f"{len(_fin_t)} final" if len(_fin_t) == len(mine_today)
                   else f"{len(mine_today)} today")
        elif [x for x in gs if _is_recent_final(x)]:
            # A final from last night is still the thing this tab holds, even though it
            # is not today's. "NFL Sun" over the Bills result is the front page telling
            # a reader to come back in three days.
            _rf = [x for x in gs if _is_recent_final(x)]
            sub = f"{len(_rf)} final"
        else:
            nxt = sorted((_utc_dt(g.get("start_utc") or "") for g in gs
                          if _utc_dt(g.get("start_utc") or "")), key=lambda d: d)
            nxt = [d for d in nxt if d.astimezone(_ET).date() > today]
            if nxt:
                d0 = nxt[0].astimezone(_ET)
                sub = (d0.strftime("%a") if (d0.date() - today).days < 7
                       else d0.strftime("%b %-d"))
            else:
                # H-6: A LEAGUE WITH A PANEL ALWAYS HAS A TAB. This used to skip a
                # league whose games were all in the past, so at 7:57 AM the MLB panel
                # existed with fifteen finals and no tab could reach it. A board the
                # reader cannot open is worse than no board.
                done = sum(1 for g in gs if g.get("state") == "post")
                sub = f"{done} final" if done else f"{len(gs)} games"
        slug = name.lower().replace(" ", "-")
        out.append((" on" if active == slug else "", name, sub, slug))
    return ('<div class="tk-tabs">' + "".join(
        f'<a class="tk-tab{on}" data-league="{esc(label)}" href="{href}#{slug}">{esc(label)}'
        f'<small>{esc(sub)}</small></a>'
        for on, label, sub, slug in out) + '</div>')


def _sb_card(g, ia_index, marquee=False, wx=None):
    lose_a, lose_h = _sb_losers(g)
    _started = g.get("state") in ("in", "post")
    prog = g.get("progress")
    bar = (f'<div class="prog" style="width:{prog*100:.0f}%"></div>'
           if isinstance(prog, (int, float)) else "")
    net = f'<span class="net">{esc(g.get("network"))}</span>' if g.get("network") else ""
    fan = _sb_fantasy_strip(g, ia_index)
    if marquee:
        # S-7. Three states, and every line in them is a reading or it is absent.
        #
        # The audit's pre-game kicker is "TONIGHT · NFL · WEEK 1". The feed carries no
        # week number and no venue name - both come back None - so the kicker says the
        # day and the league and stops. A week number invented at build time to match a
        # mock is exactly the fabricated figure this desk does not print.
        import datetime as _dt
        state = g.get("state")
        sit = (f'<span>{esc(g.get("situation"))}</span>' if g.get("situation") else "")
        foot = (f'<a class="sb-link" href="{esc(_game_href(g))}">'
                f'{"Game page" if g.get("league") == "NFL" else "All scores"}</a>')
        if state == "pre":
            dt = _utc_dt(g.get("start_utc") or "")
            when = _et_clock(dt) if dt else ""
            today = dt and dt.astimezone(_ET).date() == _build_now().astimezone(_ET).date()
            kick = " · ".join(x for x in (("Tonight" if today else "Next up"),
                                          g.get("league")) if x)
            facts = []
            wxf = _wx_for(g, wx)
            if wxf:
                facts.append(esc(wxf))
            elif g.get("venue_indoor"):
                facts.append("Indoors, no weather factor")
            if fan:
                facts.append(fan)
            lines = "".join(f'<span class="sb-mq-fact">{f}</span>' for f in facts)
            w2w = ('<a class="sb-link" href="/where-to-watch.html">Where to watch</a>'
                   if W2W_LIVE else "")
            return (f'<div class="sb-marquee sb-mq-pre"{_mq_vars(g)}>'
                    f'<div class="sb-mq-top"><span class="kicker">{esc(kick)}</span>'
                    f'<span class="st-r">{_wx_chip(g, wx)}{net}</span></div>'
                    f'<div class="sb-mq-grid">'
                    f'{_sb_team_row(g["away"], False, big=True, started=False)}'
                    f'{_sb_team_row(g["home"], False, big=True, started=False)}</div>'
                    + (f'<div class="sb-mq-kick">{esc(when)}</div>' if when else "")
                    + (f'<div class="sb-mq-facts">{lines}</div>' if lines else "")
                    + f'<div class="sb-mq-foot">{foot}{w2w}</div>{bar}</div>')
        if state == "post":
            foot += ('<a class="sb-link" href="' + esc(_game_href(g)) + '">Box leaders</a>'
                     if g.get("league") == "NFL" else "")
        return (f'<div class="sb-marquee"{_mq_vars(g)}>'
                f'<div class="sb-mq-top">{_sb_status(g)}<span class="st-r">'
                f'{_wx_chip(g, wx)}{net}</span></div>'
                f'<div class="sb-mq-grid">'
                f'{_sb_team_row(g["away"], lose_a, big=True, started=_started)}'
                f'{_sb_team_row(g["home"], lose_h, big=True, started=_started)}</div>'
                f'<div class="sb-mq-meta">{sit}{fan}</div>'
                f'<div class="sb-mq-foot">{foot}</div>{bar}</div>')
    # S-9: pre-game, the kickoff time sits in the score column of the first row.
    _kick = ""
    if not _started:
        _d = _utc_dt(g.get("start_utc") or "")
        _kick = _et_clock(_d).replace(" ET", "") if _d else ""
    # A-7: the wash needs both team colours as custom properties. Same table the 5px
    # team bars already read, so a card can never disagree with its own bars.
    _ca = (g.get("away") or {}).get("color") or ""
    _cb = (g.get("home") or {}).get("color") or ""
    _vars = (f' style="--a:{esc(_ca)};--b:{esc(_cb)}"' if _ca and _cb else "")
    return (f'<div class="game"{_vars}>'
            f'{_sb_team_row(g["away"], lose_a, started=_started, kick=_kick)}'
            f'{_sb_team_row(g["home"], lose_h, started=_started)}'
            f'<div class="st">{_sb_status(g)}<span class="st-r">'
            f'{_wx_chip(g, wx)}{net}</span></div>'
            f'{f"<div class=sb-fanrow>{fan}</div>" if fan else ""}{bar}</div>')


MARQUEE_HOLD_NOON = 12        # a marquee final holds until noon ET the next day
MARQUEE_IMMINENT_MIN = 90     # and an upcoming marquee game holds from 90 minutes out
RECENT_FINAL_HOURS = 18       # "a final from last night" as the band counts it


IMMINENT_MIN = 60             # B-1: "upcoming inside sixty minutes"
DELAYED_WORDS = ("postpon", "delay", "suspend", "canc")


def _is_delayed(g):
    """A game the league has stopped. B-1 puts these at the end of the bucket they came
    from, with the word on the card, rather than mixed in among games that are on."""
    blob = " ".join([str(g.get("status_short") or ""), str(g.get("detail") or ""),
                     str(g.get("status") or "")]).lower()
    return any(w in blob for w in DELAYED_WORDS)


def _is_recent_final(g, now=None):
    """B-1 made _sb_state_rank return a tuple (bucket, delayed), and two places were
    still comparing it to an integer, so "is this a recent final" was silently always
    false and a tab holding last night's result went back to reading "next Sat". The
    question gets its own function rather than a comparison against a rank whose shape
    can change again."""
    return _sb_state_rank(g, now)[0] == 2


def _sb_state_rank(g, now=None):
    """B-1, THE ORDERING LAW, and the only function that decides it.

    Live, then anything kicking off inside the hour, then today's finals, then the rest
    of upcoming, then older finals. A delayed or postponed game sits at the end of the
    bucket it came from.

    The sixty-minute step is what M-21 was missing. M-21 put every recent final above
    every upcoming game, which is right at nine on a Sunday morning and wrong at 12:55:
    a game kicking off in five minutes belongs above one that finished last night. The
    two rules are the same rule with the clock added.
    """
    now = now or _build_now()
    st = g.get("state")
    late = 1 if _is_delayed(g) else 0
    if st == "in":
        return (0, late)
    k = _utc_dt(g.get("start_utc") or "")
    if st == "pre":
        mins = ((k - now).total_seconds() / 60) if k else 1e9
        return (1, late) if 0 <= mins <= IMMINENT_MIN else (3, late)
    if st == "post":
        if k and (now - k).total_seconds() / 3600 <= RECENT_FINAL_HOURS:
            return (2, late)
        return (4, late)
    return (3, late)


def _live_urgency(g):
    """B-1: live games lead by urgency, the closest game adjusted by how little time is
    left. A three-point game in the fourth is more urgent than a three-point game in the
    first, and a blowout is not urgent at any hour.

    Returns a sort key, so smaller is more urgent. A game whose feed carries no clock
    falls back to its margin alone rather than being guessed at.
    """
    try:
        margin = abs(int((g.get("away") or {}).get("score"))
                     - int((g.get("home") or {}).get("score")))
    except (TypeError, ValueError):
        return (99, g.get("start_utc") or "")
    # The period the feed reports, as a fraction of a normal game: later is more urgent.
    per = g.get("period")
    try:
        per = int(per)
    except (TypeError, ValueError):
        per = 0
    total = {"NFL": 4, "CFB": 4, "NBA": 4, "NHL": 3, "MLB": 9, "WNBA": 4}.get(
        (g.get("league") or "").upper(), 4)
    left = max(0.0, (total - per) / float(total)) if per else 1.0
    # A one-score game in the last period scores near zero; a rout early scores high.
    # The second term breaks a tie between equal margins toward the game with less
    # time left: a 7-7 first quarter and a 7-7 fourth both score zero on margin, and
    # the fourth is the one a reader wants first.
    return (round(margin * (0.4 + left), 2), round(left, 3),
            g.get("start_utc") or "")


def _marquee_league(games, now=None):
    """The league that leads today, by the same calendar weighting the lead story uses
    (UX-5). On a Thursday in September that is the NFL; on a Saturday, college
    football; in a week with neither, whatever is playing."""
    ls = {g.get("league") for g in games if g.get("league")}
    if not ls:
        return None
    now = now or _build_now()
    return max(sorted(ls), key=lambda l: _league_weight(l, now))


def _mins_to_kick(g, now):
    k = _utc_dt(g.get("start_utc") or "")
    return (k - now).total_seconds() / 60 if k else None


def _final_holds(g, now):
    """M-21: a marquee-league final holds the marquee until noon ET the day after the
    game. The Bills beat the Lions at 11:20 PM and by 9 the next morning the front page
    had replaced them with a 3 PM soccer fixture, which is not what a reader opens a
    sports site for on a Friday."""
    k = _utc_dt(g.get("start_utc") or "")
    if not k:
        return False
    import datetime as _d
    et = k.astimezone(_ET)
    deadline = (et + _d.timedelta(days=1)).replace(hour=MARQUEE_HOLD_NOON, minute=0,
                                                   second=0, microsecond=0)
    return now.astimezone(_ET) < deadline


def _sb_marquee_pick(games, now=None):
    """The marquee picks itself, and nothing about it is an editor's choice.

    THE ORDER, AND WHY EACH STEP IS THERE.

    A marquee-league game inside ninety minutes of kickoff comes first (M-20). The poll
    rewrites values in place and never moves a card, so the marquee is whatever the last
    BUILD chose. On 17 Sep the last build before kickoff was the 8:06 PM inactives
    snapshot, which had DET at BUF as upcoming and three live games elsewhere, so it put
    a 0-0 Mets game in the marquee eight minutes before the Bills kicked off and the
    only NFL game of the night ran its whole first hour as a row.

    Then a marquee-league game that is live. Then a marquee-league final, until noon ET
    the next day (M-21), which is the case that put the biggest result of the week off
    the front page by breakfast.

    Only then does everything else get a turn: live by league and closeness, upcoming by
    LEAGUE FIRST and kickoff second (M-20; it was kickoff first, which is how a 3 PM
    soccer fixture outranked the night's NFL game), and finals last.
    """
    now = now or _build_now()
    # CFB-1: the marquee already picked its LEAGUE by the calendar weighting; its
    # tie-breaks used the fixed tab order, so the two halves of one decision read two
    # different tables. Both read the day now.
    order = {n: i for i, n in enumerate(_day_league_order(now))}
    ml = _marquee_league(games, now)
    mine = [g for g in games if g.get("league") == ml]

    imminent = [g for g in mine if g.get("state") == "pre"
                and (_mins_to_kick(g, now) or 1e9) <= MARQUEE_IMMINENT_MIN
                and (_mins_to_kick(g, now) or -1) > -1e9]
    if imminent:
        return sorted(imminent, key=lambda g: g.get("start_utc") or "")[0]

    def closeness(g):
        try:
            d = abs(int(g["away"]["score"]) - int(g["home"]["score"]))
        except Exception:
            d = 99
        return (order.get(g["league"], 99), d)

    ml_live = [g for g in mine if g.get("state") == "in"]
    if ml_live:
        return sorted(ml_live, key=closeness)[0]

    # A FINAL IS JUDGED BY THE MARQUEE LEAGUE AT ITS OWN KICKOFF, not today's. Friday
    # lifts MLB for the pennant race (2.60) above an out-of-window NFL (1.60), so asking
    # "is this today's marquee league?" on Friday morning said no about a Thursday night
    # NFL game and the hold never fired. At kickoff on Thursday the NFL was 4.00, which
    # is the weight that made it the marquee in the first place.
    ml_final = [g for g in games
                if g.get("state") == "post" and _final_holds(g, now)
                and g.get("league") == _marquee_league(
                    games, _utc_dt(g.get("start_utc") or "") or now)]
    if ml_final:
        return sorted(ml_final, key=lambda g: g.get("start_utc") or "", reverse=True)[0]

    live = [g for g in games if g.get("state") == "in"]
    if live:
        # SC-3b (R-3): LEAGUE ORDER FIRST, CLOSENESS SECOND. A one-point WNBA game must
        # not take the marquee from the only NFL game of the night.
        return sorted(live, key=closeness)[0]
    up = [g for g in games if g.get("state") == "pre" and g.get("start_utc")]
    if up:
        # M-20: league first, kickoff second. The other way round put CHE at BRE at 3 PM
        # above the night's NFL game.
        return sorted(up, key=lambda g: (order.get(g["league"], 99), g["start_utc"]))[0]
    fin = [g for g in games if g.get("state") == "post"]
    return sorted(fin, key=lambda g: order.get(g["league"], 99))[0] if fin else None


def _ia_index(board):
    """Inactive counts by team id, for the card strips."""
    if not board:
        return {}
    # (league, id): a bare id is not an identity across leagues - see _sb_fantasy_strip.
    # The inactives feed is NFL, so that is the league these ids belong to.
    return {("NFL", str(t.get("id"))): t for t in board.get("teams") or [] if t.get("id")}


def _ia_for_game(g, ia_index, side):
    """H-1: the inactives list for ONE SIDE OF ONE GAME, or None.

    A LIST BELONGS TO A GAME, and the day file does not say so. It is keyed by team id
    and merges the last eight days (N-7), so on Wednesday of Week 2 it still holds the
    lists captured at Week 1's games. Asking it "does this team have a list?" answered
    yes for all 32 teams, and every Week 2 card read "Inactives: posted" three days
    before a single Week 2 list existed. The fantasy rail on the same page said "Week 2,
    nothing posted for this week yet", which was the true sentence.

    A list counts for a game only when it was FIRST SEEN inside that game's window:
    from three hours before kickoff to the end of that day, Eastern. Teams post about
    ninety minutes out, so three hours is generous on the early side and the day end
    closes it without needing to know when the game finished.
    """
    kick = _utc_dt(g.get("start_utc") or "")
    tid = str((g.get(side) or {}).get("id") or "")
    if not kick or not tid:
        return None
    import datetime as _d
    opens = kick - _d.timedelta(hours=3)
    day_end = kick.astimezone(_ET).replace(hour=23, minute=59, second=59) \
                  .astimezone(_d.timezone.utc)

    # THE WEEK'S BOARD CANNOT ANSWER THIS QUESTION, AND ASKING IT WAS THE BUG.
    #
    # board() merges eight days (N-7) and keeps a player's FIRST sighting, which is
    # right for a page that lists the week and wrong for a page about one game. Two
    # things follow from it. A team's merged first_seen is the MINIMUM across the
    # week, so any team that had a list in Week 1 is stamped with Week 1 forever and
    # this window rejects it for every later game. And a player inactive in both weeks
    # keeps his Week 1 stamp, so he is missing from Week 2's list entirely: on 17 Sep
    # Buffalo's merged entry was seven players dated 13 Sep plus one dated tonight,
    # and tonight's actual list was seven.
    #
    # So this reads the DAY FILE for the game's own Eastern date, which is the capture
    # the poller made at this game's list going up, with each player's real stamp. The
    # merged board stays the source for the week's page, where it is correct.
    day = kick.astimezone(_ET).strftime("%Y-%m-%d")
    try:
        import inactives as _iam
        snap = _iam.load_snapshot(day)
    except Exception:
        snap = None
    t = ((snap or {}).get("teams") or {}).get(tid) if snap else None
    if t:
        players = [p for p in (t.get("players") or {}).values()
                   if p.get("first_seen")
                   and opens <= _utc_dt(p["first_seen"]) <= day_end]
        if players:
            players.sort(key=lambda p: (p.get("first_seen") or "", p.get("name") or ""))
            firsts = [p["first_seen"] for p in players]
            return {"team": t.get("team"), "id": t.get("id"), "players": players,
                    "count": len(players), "first_seen": min(firsts),
                    "last_added": max(firsts),
                    "incomplete": bool(t.get("unresolved")),
                    "reconciled_at": t.get("reconciled_at")}

    # Fall back to the merged board, with the same window, for a game whose day file
    # is missing. A team stamped from an earlier week still fails it, which is the
    # behaviour H-1 asked for in the first place.
    t = ia_index.get(("NFL", tid))
    if not t:
        return None
    seen = _utc_dt(t.get("first_seen") or "")
    return t if seen and opens <= seen <= day_end else None


SB_LIVE_JS = """
<script>(function(){
  /* L-2/L-3/L-4: the live poll.

     The page is rendered from the last committed snapshot and is complete without this
     script; crawlers and a reader with JS off see a finished board. This only rewrites
     values that are already on the page, in place. It never adds or removes a card.

     THE SOURCE IS THE PUBLIC SCOREBOARD FEED, the same one the build reads. L-1 swaps
     the URL for the Worker's /live/scores.json route and nothing else here changes:
     the reshape below is the site's own shape either way.

     Cadence (L-2): 60s while any game on this page is live, 10 minutes otherwise, and
     only while the tab is visible. Freshness (L-4): three consecutive misses mark the
     band stale beside its stamp and drop the live dot, rather than leaving a wrong
     score looking current. */
  var CARDS = document.querySelectorAll('[data-gid]');
  if (!CARDS.length) return;
  var PATHS = {NFL:'football/nfl', MLB:'baseball/mlb', CFB:'football/college-football',
               NBA:'basketball/nba', NHL:'hockey/nhl', WNBA:'basketball/wnba'};
  var BASE = 'https://site.api.espn.com/apis/site/v2/sports/';
  var UP = '#3DDC84', DOWN = '#FF7A6B', TIE = '#F0C674';
  var FAST = 60000, SLOW = 600000, MISS = 0, timer = null;

  var leagues = {};
  [].forEach.call(CARDS, function(c){
    var l = c.getAttribute('data-league'); if (PATHS[l]) leagues[l] = 1;
  });
  leagues = Object.keys(leagues);
  if (!leagues.length) return;

  function byId(gid){ return document.querySelectorAll('[data-gid="' + gid + '"]'); }

  function colours(a, h){
    if (a === null || h === null) return [null, null];
    if (a === h) return [TIE, TIE];
    return a > h ? [UP, DOWN] : [DOWN, UP];
  }

  function num(v){ var n = parseInt(v, 10); return isNaN(n) ? null : n; }

  /* A-4: A BAKED LIVE STATE EXPIRES. The page is built from a snapshot, and between
     builds that snapshot ages: on Sunday morning the 8:00 PM Saturday build still
     painted six MLB games as live in the first inning, and on a hidden tab the poll
     does not run at all (L-2), so a phone resuming from the background showed
     Saturday's first quarter as "Live" until the reader looked at it.

     If the build is older than STALE_BUILD_MS, every card baked live is marked as of
     the build's own time, with no live dot, until the poll answers for it. This removes
     a claim; it never invents one. The poll clears the mark the moment it has a real
     state for that card. */
  var STALE_BUILD_MS = 3 * 3600 * 1000;
  var BAND = document.querySelector('[data-built]');
  var BUILT = BAND ? Date.parse(BAND.getAttribute('data-built') || '') : NaN;
  var BUILD_STALE = isFinite(BUILT) && (Date.now() - BUILT) >= STALE_BUILD_MS;
  (function expireBakedLive(){
    var band = BAND;
    if (!band || !BUILD_STALE) return;
    var asof = band.getAttribute('data-built-et') || '';
    [].forEach.call(CARDS, function(c){
      if (c.getAttribute('data-state') !== 'in') return;
      c.setAttribute('data-baked-stale', '1');
      var k = c.querySelector('[data-role="kicker"]');
      if (k) k.textContent = (c.getAttribute('data-league') || '')
                             + (asof ? ' \u00b7 as of ' + asof : '');
      var w = c.querySelector('[data-role="when"]');
      if (w && asof) w.textContent = 'as of ' + asof;
    });
  })();
  setTimeout(recount, 0);   /* A-2: correct the baked counts even before the first poll */

  /* B-2: THE COUNTDOWN. Written by the client, never baked: a countdown rendered at
     build time is wrong the moment it is served, and on this desk a build can be hours
     old. It ticks once a minute, which is the resolution it shows, and it stops the
     moment the game is no longer upcoming so a started game never reads "kicks in". */
  function countdowns(){
    var now = Date.now();
    document.querySelectorAll('[data-countdown]').forEach(function(el){
      var card = el.closest('[data-gid]');
      if (card && card.getAttribute('data-state') !== 'pre') { el.textContent = ''; return; }
      var k = Date.parse(el.getAttribute('data-kick') || '');
      if (!isFinite(k)) { el.textContent = ''; return; }
      var mins = Math.round((k - now) / 60000);
      if (mins < 0) { el.textContent = ''; return; }
      if (mins < 60) { el.textContent = 'kicks in ' + mins + 'm'; return; }
      var h = Math.floor(mins / 60), m = mins % 60;
      el.textContent = h < 24
        ? 'kicks in ' + h + 'h ' + (m < 10 ? '0' : '') + m + 'm'
        : '';
    });
  }
  countdowns();
  setInterval(countdowns, 60000);

  function paint(gid, s){
    [].forEach.call(byId(gid), function(card){
      var started = s.state === 'in' || s.state === 'post';
      var c = colours(started ? s.away : null, started ? s.home : null);
      card.setAttribute('data-state', s.state);
      card.removeAttribute('data-baked-stale');   /* A-4: the poll has answered */
      card.classList.toggle('wide', started);
      ['away','home'].forEach(function(side, i){
        var sc = side === 'away' ? s.away : s.home;
        /* the full card's stub: abbreviation and score live in one span */
        var big = card.querySelector('.tk-mu [data-side="' + side + '"]');
        if (big) {
          /* CFB-1: data-label is what this league calls the team ("Georgia"), and
             data-abbr stays the abbreviation the pin and this poll match on. Without
             the label the first poll rewrote every college name back to its initials. */
          var ab = big.getAttribute('data-label') || big.getAttribute('data-abbr') || '';
          /* B-2: the score is its own node now so it can be set at 64px against a name
             at 15px. textContent on the parent would delete both children, which is
             how the first cut of this silently erased every score it painted. */
          var nm = big.querySelector('.tk-nm'), scn = big.querySelector('.tk-sc');
          if (nm) {
            nm.textContent = ab;
            if (scn) scn.textContent = started && sc !== null ? sc : '';
          } else {
            big.textContent = started && sc !== null ? ab + ' ' + sc : ab;
          }
          big.style.color = c[i] || '#FFFFFF';
        }
        /* the folded card: score and abbreviation are separate */
        var cell = card.querySelector('.s[data-side="' + side + '"]');
        if (cell) {
          cell.textContent = started && sc !== null ? sc : '';
          cell.className = started && sc !== null ? 's sc' : 's';
          cell.style.color = c[i] || '';
        }
        var abb = card.querySelector('b[data-side="' + side + '"]');
        if (abb) abb.style.color = c[i] || '';
      });
      var st = card.querySelector('[data-role="status"]');
      if (st && started) st.textContent = s.status;
      var k = card.querySelector('[data-role="kicker"] .tk-k');
      if (k) {
        if (s.state === 'in') {
          k.className = 'tk-k live';
          k.innerHTML = '<span class="dot"></span>Live · ' +
                        (card.getAttribute('data-league') || '') + ' · ' +
                        esc(s.status);
        } else if (s.state === 'post') {
          k.className = 'tk-k';
          k.textContent = (card.getAttribute('data-league') || '') + ' · Final';
        }
      }
      /* UX-3: the situation belongs on the second line, beside where the kickoff
         time was, not on the records line. */
      var when = card.querySelector('[data-role="when"]');
      if (when) {
        /* A-4: A FINAL HAS NO SITUATION. The poll wrote the situation on a live game
           and never took it back, so ten Saturday finals sat under their final scores
           reading "3rd & 4 at MSU 31" all Sunday morning. A card that leaves the live
           state drops the line with it. */
        if (s.state === 'in' && s.situation) when.textContent = s.situation;
        else if (s.state === 'post') when.textContent = s.short || 'Final';
        else if (s.state === 'pre' && s.kick) when.textContent = s.kick;
      }
    });
    /* A-3: the strip moves with the cards. Same game, same source, same paint. */
    [].forEach.call(document.querySelectorAll('.msb-g[data-gid="' + gid + '"]'),
      function(it){
        it.setAttribute('data-state', s.state);
        var started = s.state === 'in' || s.state === 'post';
        ['away', 'home'].forEach(function(side){
          var el = it.querySelector('.msb-s[data-side="' + side + '"]');
          if (!el) return;
          var v = side === 'away' ? s.away : s.home;
          el.textContent = (started && v !== null && v !== undefined) ? String(v) : '';
        });
        var a = s.away, h = s.home, tie = (a === h);
        ['away', 'home'].forEach(function(side){
          var el = it.querySelector('.msb-s[data-side="' + side + '"]');
          if (!el) return;
          var mine = side === 'away' ? a : h, other = side === 'away' ? h : a;
          var lead = (mine !== null && other !== null && !tie && mine > other);
          el.classList.toggle('msb-lead', !!lead);
        });
        var st = it.querySelector('[data-role="msb-status"]');
        if (st) st.textContent = started ? (s.status || '') : (st.textContent || '');
      });
    recount();        /* A-2: the header, the tabs and "Next" follow the cards */
  }

  /* A-2: THE COUNTS COME FROM THE CARDS, NEVER FROM THE BUILD. "49 games today · 16
     live now" was baked at 8:00 PM Saturday and survived a poll that had just turned
     every one of those games into a final, so the header claimed sixteen live games
     above a board showing none. The tab counts and the "Next" line had the same
     problem. They are recomputed from the cards' CURRENT state after every paint.

     "Next" is the first card whose state is pre, by kickoff. It named LSU at Ole Miss,
     a game that had already started at build time: a game that has kicked off is never
     the next one. */
  /* THE SLATE, not the page. The band renders a marquee and six cards per panel, so
     counting the DOM said "NFL 7 today" on a sixteen-game Sunday. The feed carries
     every game in every league the page shows, so the counts are computed from that
     and seeded from the cards only until the first answer arrives. */
  var SLATE = {};
  [].forEach.call(document.querySelectorAll('.tk-c[data-gid]'), function(c){
    var gid = c.getAttribute('data-gid');
    if (gid && !SLATE[gid]) SLATE[gid] = {
      lg: c.getAttribute('data-league') || '', state: c.getAttribute('data-state'),
      kick: c.getAttribute('data-kick') || '', ket: c.getAttribute('data-kick-et') || '',
      a: c.getAttribute('data-away') || '', h: c.getAttribute('data-home') || '',
      /* a live state the poll has not confirmed counts as live only while the build
         it came from is recent; past that it is A-4's expired state */
      baked: BUILD_STALE ? 1 : 0};
  });

  function etTime(iso){
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleTimeString('en-US', {
        timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit'}) + ' ET';
    } catch (e) { return ''; }
  }

  function recount(){
    var byLeague = {}, live = 0, today = 0, upcoming = [];
    Object.keys(SLATE).forEach(function(gid){
      var g = SLATE[gid], lg = g.lg, st = g.state;
      byLeague[lg] = byLeague[lg] || {live:0, total:0, fin:0};
      byLeague[lg].total++;
      today++;
      /* a baked live state that the poll has not confirmed is not counted as live */
      if (st === 'in' && !g.baked) { live++; byLeague[lg].live++; }
      if (st === 'post') byLeague[lg].fin++;
      if (st === 'pre') upcoming.push({k:g.kick, t:g.ket || etTime(g.kick),
                                       a:g.a, h:g.h});
    });
    var head = document.querySelector('.sb-count');
    if (head) {
      /* "0 live now" is said out loud rather than dropped: on a Sunday morning it
         tells the reader nothing has started, which is the thing they came to learn. */
      head.textContent = today + ' game' + (today === 1 ? '' : 's') + ' today'
                       + ' \u00b7 ' + live + ' live now';
    }
    [].forEach.call(document.querySelectorAll('.tk-tab'), function(tab){
      var lg = tab.getAttribute('data-league'), sm = tab.querySelector('small');
      if (!sm || !lg) return;
      var b = byLeague[Object.keys(byLeague).filter(function(k){
        return k.toLowerCase() === lg.toLowerCase(); })[0]];
      if (!b) return;
      if (b.live) sm.textContent = b.live + ' live';
      else if (b.fin === b.total && b.total) sm.textContent = b.fin + ' final';
      else if (b.total) sm.textContent = b.total + ' today';
    });
    var nx = document.querySelector('.sb-next');
    if (nx) {
      upcoming.sort(function(x, y){ return x.k < y.k ? -1 : x.k > y.k ? 1 : 0; });
      var n = upcoming[0];
      nx.textContent = n ? ('Next: ' + n.a + ' at ' + n.h + (n.t ? ' ' + n.t : '')) : '';
      nx.hidden = !n;
    }
  }

  function esc(t){ var d = document.createElement('div'); d.textContent = t || '';
                   return d.innerHTML; }

  function stamp(when, stale){
    var el = document.querySelector('.sb-head .sb-stamp, .sb-countwrap .sb-stamp');
    if (el) {
      /* L-3: THE STAMP IS THE SOURCE'S OWN TIME, NEVER THE BROWSER'S. The public feed
         carries no response time, so until the Worker route does (L-1) the stamp stays
         the one the build wrote and only the stale mark moves. Writing the browser's
         clock here would be the page asserting a freshness the source never claimed,
         which is the same class of error as a fabricated number. */
      var base = (el.getAttribute('data-base') || el.textContent || '')
                 .replace(/ · stale$/, '');
      if (!el.getAttribute('data-base')) el.setAttribute('data-base', base);
      var d = when ? new Date(when) : null;
      if (d && !isNaN(d)) {
        base = 'Updated ' + d.toLocaleTimeString('en-US', {timeZone:'America/New_York',
                 hour:'numeric', minute:'2-digit'}) + ' ET';
        el.setAttribute('data-base', base);
      }
      /* D-1, found at checkpoint 4: at 9:16 PM the stamp read "Updated 8:00 PM ET"
         while the scores under it were seconds old, because this function rewrites the
         numbers and leaves the stamp at the build's time. One page, two ages, and the
         older one is the one in words.

         The rule above still holds and is not being relaxed: we do not know when the
         SOURCE last updated, so we do not say. But we do know, exactly, when this page
         last asked and got an answer, and that is a different claim: "updated" is about
         the feed, "checked" is about us. Saying the second is honest, and it is the fact
         the reader actually wants when the board is moving. */
      var seen = '';
      if (!stale && when !== undefined) {
        seen = ' · checked ' + new Date().toLocaleTimeString('en-US',
                 {timeZone:'America/New_York', hour:'numeric', minute:'2-digit'});
      }
      el.textContent = base + seen + (stale ? ' · stale' : '');
    }
    document.querySelectorAll('.tk-k.live .dot').forEach(function(d){
      d.style.visibility = stale ? 'hidden' : '';
    });
  }

  function leagueOf(json){
    var l = (((json || {}).leagues || [])[0] || {}).abbreviation || '';
    if (l === 'NCAAF') l = 'CFB';
    return l;
  }

  function reshape(json){
    var out = [], when = null;
    ((json && json.events) || []).forEach(function(ev){
      var comp = (ev.competitions || [])[0]; if (!comp) return;
      var cs = comp.competitors || [];
      var home = null, away = null;
      cs.forEach(function(x){ if (x.homeAway === 'home') home = x; else away = x; });
      var st = ((comp.status || {}).type) || {};
      out.push({id: String(ev.id),
                state: st.state || '',
                status: st.shortDetail || st.detail || st.description || '',
                short: st.shortDetail || st.description || 'Final',
                kick: ev.date || '',
                away: away ? num(away.score) : null,
                home: home ? num(home.score) : null,
                aabbr: (away && away.team && away.team.abbreviation) || '',
                habbr: (home && home.team && home.team.abbreviation) || '',
                situation: (comp.situation || {}).downDistanceText || ''});
    });
    /* NOT A TIME. json.day.date is the scoreboard's CALENDAR DAY, "2026-09-20", and
       passing it to stamp() rendered it as one: new Date() reads it as UTC midnight,
       which in Eastern is 8:00 PM the day before, so the live band read "Updated 8:00
       PM ET" all Sunday afternoon. The rule stamp() already states is the right one
       and was not being followed: the public feed carries no response time, so the
       build's stamp stands and only the stale mark moves. */
    return {games: out, when: null};
  }

  function tick(){
    var wanted = leagues.map(function(l){
      return fetch(BASE + PATHS[l] + '/scoreboard', {cache:'no-store'})
             .then(function(r){ return r.ok ? r.json() : null; })
             .catch(function(){ return null; });
    });
    Promise.all(wanted).then(function(all){
      var got = 0, live = 0;
      all.forEach(function(j){
        if (!j) return;
        got++;
        var r = reshape(j);
        r.games.forEach(function(s){
          /* A-2: EVERY game the feed names enters the slate, whether or not the band
             renders a card for it. The counts are about the day, not about the six
             cards that fit. */
          var prev = SLATE[s.id] || {};
          SLATE[s.id] = {lg: prev.lg || leagueOf(j) || '', state: s.state,
                         kick: s.kick || prev.kick || '', ket: prev.ket || '',
                         a: s.aabbr || prev.a || '', h: s.habbr || prev.h || '',
                         baked: 0};
          if (!byId(s.id).length) return;
          paint(s.id, s);
          if (s.state === 'in') live++;
        });
      });
      if (!got) {
        /* L-4: a miss changes nothing on the page. Three in a row says so. */
        if (++MISS >= 3) stamp(null, true);
      } else {
        MISS = 0;
        stamp(null, false);
      }
      schedule(live > 0);
    });
  }

  function schedule(fast){
    clearTimeout(timer);
    timer = setTimeout(function(){ if (!document.hidden) tick(); else schedule(fast); },
                       fast ? FAST : SLOW);
  }

  /* Poll on load only if something on the page could change. */
  var anyLive = false, anyPre = false;
  [].forEach.call(CARDS, function(c){
    var s = c.getAttribute('data-state');
    if (s === 'in') anyLive = true;
    if (s === 'pre') anyPre = true;
  });
  if (!anyLive && !anyPre) return;
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) tick();
  });
  if (!document.hidden) tick(); else schedule(anyLive);
})();</script>
"""

SB_TABS_JS = """
<script>(function(){
  /* SC-4: the tabs switch the band. Every league's panel is already in the page, so
     this only moves the `hidden` attribute and the `on` class; nothing is fetched and
     nothing is laid out from scratch.

     WITHOUT THIS SCRIPT THE TABS STILL WORK: each one is a real link to that league's
     section on /scores, and the browser follows it. This turns the same link into an
     in-place switch when it can, and gets out of the way when it cannot. */
  var tabs = document.querySelectorAll('.tk-tabs .tk-tab');
  var panels = document.querySelectorAll('.tk-panel');
  if (!tabs.length || !panels.length) return;
  var KEY = 'gcm.league';
  function slugOf(a){ var h = a.getAttribute('href') || ''; var i = h.indexOf('#');
    return i < 0 ? 'all' : h.slice(i + 1); }
  function show(slug){
    var found = false;
    panels.forEach(function(p){
      var mine = p.getAttribute('data-league') === slug;
      if (mine) found = true;
      p.hidden = !mine;
    });
    if (!found) return false;
    tabs.forEach(function(t){
      t.classList.toggle('on', slugOf(t) === slug);
    });
    /* H-6: the count in the band header describes the panel on screen, not the whole
       slate. Each panel carries its own; this moves it up. */
    var panel = document.querySelector('.tk-panel[data-league="' + slug + '"]');
    var count = panel && panel.querySelector('.tk-count');
    var head = document.querySelector('.sb-count');
    if (count && head) head.textContent = count.textContent;
    try { localStorage.setItem(KEY, slug); } catch (e) {}
    return true;
  }
  tabs.forEach(function(t){
    t.addEventListener('click', function(ev){
      var slug = slugOf(t);
      /* Only take over the click when this page can actually show that league. On a
         league the band is not carrying, the link does its job and goes to /scores. */
      if (show(slug)) {
        ev.preventDefault();
        if (history.replaceState) history.replaceState(null, '', '#' + slug);
      }
    });
  });
  var want = (location.hash || '').slice(1);
  if (!want) { try { want = localStorage.getItem(KEY) || ''; } catch (e) {} }
  if (want) show(want);

  /* H-3 (SC-2): a fold opens the full card in place, by click or tap. The card is
     already in the page beside it, so this only moves the hidden attribute. Without
     this script the fold is still a link to the game page, which is where the reader
     was going anyway. */
  document.querySelectorAll('.tk-pair').forEach(function(pair){
    var fold = pair.querySelector('.tk-fold');
    var open = pair.querySelector('.tk-open');
    if (!fold || !open) return;
    fold.setAttribute('role', 'button');
    fold.setAttribute('aria-expanded', 'false');
    function set(on){
      fold.hidden = on;
      open.hidden = !on;
      fold.setAttribute('aria-expanded', on ? 'true' : 'false');
    }
    fold.addEventListener('click', function(ev){
      /* A modifier or a middle click is a reader asking for the game page. */
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
      ev.preventDefault();
      set(true);
    });
    var close = open.querySelector('.tk-close');
    if (close) close.addEventListener('click', function(ev){
      ev.preventDefault(); set(false); fold.focus();
    });
  });
})();</script>
"""

SB_HERO_JS = """
<script>(function(){
  /* Hero addendum item 3: the loop may replace the poster on desktop ONLY, and only
     after the load event. It is never requested on a phone, because the request is
     made by this script and this script does not run one below 1024. Reduced motion
     stops both the loop and the poster's zoom. webm only: the mp4 is 1.67MB, over the
     1.5MB ceiling, and every browser that autoplays a muted loop here reads webm. */
  try{
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!window.matchMedia || !window.matchMedia('(min-width:1024px)').matches) return;
    var bg = document.querySelector('.sb-hero .sb-bg');
    if (!bg) return;
    window.addEventListener('load', function(){
      var v = document.createElement('video');
      v.className = 'sb-loop'; v.muted = true; v.autoplay = true; v.loop = true;
      v.playsInline = true; v.setAttribute('aria-hidden','true'); v.tabIndex = -1;
      v.src = '/assets/hero/hero-loop.webm';
      v.addEventListener('playing', function(){ bg.classList.add('has-loop'); });
      bg.appendChild(v);
    });
  }catch(e){}
})();</script>"""


def _sb_ornament(games):
    """A-5: the kickoff timeline. One bar per kickoff window in the day's slate, height
    proportional to the number of games in that window, drawn from site/data and never
    hand-made. A day with no games has no ornament; there is never a fake series."""
    import collections
    today = _build_now().astimezone(_ET).date()
    by_hour = collections.Counter()
    for g in games:
        d = _utc_dt(g.get("start_utc") or "")
        if not d:
            continue
        e = d.astimezone(_ET)
        if e.date() == today:
            by_hour[e.hour] += 1
    if not by_hour:
        return ""
    hours = sorted(by_hour)
    lo, hi = min(hours), max(hours)
    span = max(hi - lo, 1)
    peak = max(by_hour.values())
    W, H = 1200, 170
    bars = []
    for h in hours:
        x = ((h - lo) / span) * (W - 90) + 20
        bh = max(12, (by_hour[h] / peak) * (H - 24))
        bars.append(f'<rect x="{x:.0f}" y="{H-bh:.0f}" width="46" height="{bh:.0f}" '
                    f'rx="3" fill="#3DDC84"></rect>')
    # UX-12: the bars read as a rendering glitch because nothing said what they were.
    # One bar per kickoff window in today's slate, its height the number of games in
    # that window. The title is what a hover shows and what a screen reader reads.
    _legend = (f"Kickoff windows today: {len(hours)} window"
               f"{'' if len(hours) == 1 else 's'}, busiest carries {peak} game"
               f"{'' if peak == 1 else 's'}.")
    return (f'<svg class="sb-orn" viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
            f'role="img" aria-label="{esc(_legend)}">'
            f'<title>{esc(_legend)}</title>{"".join(bars)}</svg>')


def _sb_day_split(games):
    """S-25. How many of these games are actually TODAY, on the reader's clock.

    The band said "62 games today" and linked "All 62 games today". The scoreboard feed
    is not a day, it is a schedule: measured 15 Sep it held 62 games spanning 9 Sep to
    3 Oct, and none of them were today. len(games) was never the day's count, and S-25
    put that number in the hero's promise row where a reader would read it as the
    desk's own tally. Returns (todays_games, next_day_label, next_day_count)."""
    import datetime as _dt
    today = _build_now().astimezone(_ET).date()
    by_day = {}
    for g in games:
        d = _utc_dt(g.get("start_utc") or "")
        if d:
            by_day.setdefault(d.astimezone(_ET).date(), []).append(g)
    todays = by_day.get(today) or []
    nxt = sorted(d for d in by_day if d > today)
    if not nxt:
        return todays, "", 0
    d0 = nxt[0]
    lab = "tomorrow" if (d0 - today).days == 1 else d0.strftime("%A")
    return todays, lab, len(by_day[d0])


# ---- S-L4: the sticky mini-scoreboard --------------------------------------------
# The audit's fourth lead item: when the reader scrolls past the band, a thin strip with
# the live scores stays at the top of the page, the way ESPN and Yahoo keep scores in
# view while you read.
#
# ONLY WHEN THERE IS SOMETHING LIVE. A strip of scheduled games is a strip of zeros, and
# a strip of finals is yesterday's news pinned to the top of today's page. With no game
# in progress the strip is not rendered at all, which is also why it costs nothing on
# the days it would say nothing.
#
# It is fixed rather than sticky because the nav above it is already sticky, and two
# sticky siblings at top:0 land on top of each other. The offset is measured from the
# nav at runtime rather than written as a number here: the nav is 44px today and that
# is not a promise it makes.

MINI_SB_JS = """<script>(function(){
  var strip=document.querySelector('.msb'), band=document.querySelector('.scoreband');
  if(!strip||!band||!('IntersectionObserver' in window)) return;
  var nav=document.querySelector('nav.mh-nav');
  function offset(){
    var h = nav ? Math.round(nav.getBoundingClientRect().height) : 0;
    document.documentElement.style.setProperty('--msb-top', h+'px');
  }
  offset();
  addEventListener('resize', offset, {passive:true});
  /* The strip appears once the band has left the top of the viewport and goes away
     again when it returns. Nothing is delayed by this: the strip is extra, and the
     page is complete without it. */
  new IntersectionObserver(function(es){
    strip.hidden = es[0].isIntersecting;
  }, {rootMargin:'-1px 0px 0px 0px', threshold:0}).observe(band);
})();</script>"""


# ---- S-L3: my teams --------------------------------------------------------------
# The audit's third lead item, and the sports twin of the crypto desk's coin pins: pin
# teams, and their games lead the band while their injuries lead the hub. No account,
# nothing sent, nothing logged; the choice lives in this browser and nowhere else.
#
# WHY THE REORDER IS CLIENT-SIDE. The desk cannot know what a reader has pinned, and
# should not: that is the whole point of a device-only list. So the page ships in its
# normal order, complete and correct for everyone, and the script moves what the reader
# picked to the front. A reader with no pins gets exactly the page that shipped, and a
# reader with no JavaScript gets it too.

LENS_JS = """<script>(function(){
  /* B-3: the lens. Four ways to read the same board.

     WHAT IT DOES NOT DO: it never adds, removes or reorders a card. It sets one
     attribute on the board and the stylesheet does the rest, which means a lens can
     never disagree with the live poll about what is on the page.

     The default is All, and the choice is remembered per device in localStorage the
     same way the team pins are. A stored value that is not one of the four is ignored
     rather than trusted: the attribute goes straight into a CSS selector. */
  var KEY = 'gcm.lens', OK = {all:1, lines:1, fantasy:1, watch:1};
  var groups = document.querySelectorAll('.lens');
  if (!groups.length) return;

  function roots(){
    /* The band and the /scores board are different elements on different pages, so the
       attribute goes on whatever contains the cards, found from the cards themselves. */
    var out = [], seen = [];
    [].forEach.call(document.querySelectorAll('.tk-c'), function(c){
      var r = c.closest('.sb-inner') || c.closest('main') || document.body;
      if (seen.indexOf(r) < 0) { seen.push(r); out.push(r); }
    });
    return out;
  }

  function read(){
    try { var v = localStorage.getItem(KEY); return OK[v] ? v : 'all'; }
    catch (e) { return 'all'; }
  }

  function apply(v, save){
    if (!OK[v]) v = 'all';
    roots().forEach(function(r){ r.setAttribute('data-lens-on', v); });
    [].forEach.call(document.querySelectorAll('.lens-b'), function(b){
      var on = b.getAttribute('data-lens') === v;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (save) { try { localStorage.setItem(KEY, v); } catch (e) {} }
  }

  [].forEach.call(groups, function(gp){
    gp.hidden = false;      /* only now does the control exist for a reader */
    gp.addEventListener('click', function(ev){
      var b = ev.target.closest('.lens-b');
      if (!b) return;
      ev.preventDefault();
      apply(b.getAttribute('data-lens'), true);
    });
  });
  /* THE FIRST APPLY WAITS FOR THE DOCUMENT. This script is attached to the band, and
     on /scores the band is parsed BEFORE the card grid further down the page, so at
     this point querySelectorAll('.tk-c') can be empty, roots() returns nothing and the
     lens is set on no element at all. Clicking a button afterwards worked, which is why
     it read as correct: by then the document had finished. A stored lens would simply
     not have been applied on load, on the one page that is entirely cards. */
  function start(){ apply(read(), false); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();</script>"""


TEAM_PIN_JS = """<script>(function(){
  var KEY='gcms_teams', store=null;
  try{ localStorage.setItem('__t','1'); localStorage.removeItem('__t'); store=localStorage; }
  catch(e){ document.querySelectorAll('[data-tpin]').forEach(function(n){n.hidden=true;}); return; }
  function get(){ try{ return JSON.parse(store.getItem(KEY)||'[]'); }catch(e){ return []; } }
  function set(v){ try{ store.setItem(KEY, JSON.stringify(v.slice(0,12))); }catch(e){} }

  function first(el, parent){          /* move to the front of its own container */
    if(el && parent && el.parentElement===parent) parent.insertBefore(el, parent.firstChild);
  }
  function apply(){
    var picks=get();
    /* C-4: a reorder and an unpin both re-run this, so the marks from the previous run
       are cleared first. Without it an unpinned team kept its highlight until the next
       page load, which is the reader being told their change did not take. */
    document.querySelectorAll('.tk-pinned').forEach(function(n){
      n.classList.remove('tk-pinned'); });
    document.querySelectorAll('.msb-pinned').forEach(function(n){
      n.classList.remove('msb-pinned'); });
    document.querySelectorAll('[data-tpick]').forEach(function(b){
      b.setAttribute('aria-pressed', String(picks.indexOf(b.getAttribute('data-tpick'))>-1));
    });
    if(!picks.length) return;
    /* The band: a game card whose either side is pinned goes to the front of its
       league group, newest pick last so the order the reader picked in is kept. */
    for(var i=picks.length-1;i>=0;i--){
      var ab=picks[i];
      document.querySelectorAll('.tk-c').forEach(function(card){
        var hit=false;
        card.querySelectorAll('[data-abbr]').forEach(function(x){
          if(x.getAttribute('data-abbr')===ab) hit=true;
        });
        if(hit){
          card.classList.add('tk-pinned');
          /* The movable unit is whatever the band lays out: the grid's children are
             tk-pair wrappers, and the marquee is the card itself. Moving the card out
             of its wrapper would take it out of the grid entirely. */
          var unit = card.closest('.tk-pair') || card;
          first(unit, unit.parentElement);
        }
      });
    }
    /* A-3: the strip leads with the reader's teams. */
    for(var m=picks.length-1;m>=0;m--){
      var ab2=picks[m];
      document.querySelectorAll('.msb-g').forEach(function(it){
        if(it.getAttribute('data-away')===ab2 || it.getAttribute('data-home')===ab2){
          it.classList.add('msb-pinned'); first(it, it.parentElement);
        }
      });
    }
    /* The hub: a pinned team's inactives block goes to the front of the grid. */
    var names={};
    document.querySelectorAll('[data-tabbr][data-tname]').forEach(function(n){
      names[n.getAttribute('data-tabbr')]=n.getAttribute('data-tname');
    });
    for(var j=picks.length-1;j>=0;j--){
      var want=names[picks[j]];
      if(!want) continue;
      document.querySelectorAll('.ia-team[data-team]').forEach(function(blk){
        if(blk.getAttribute('data-team')===want){
          blk.classList.add('ia-pinned'); first(blk, blk.parentElement);
        }
      });
    }
  }
  document.addEventListener('click', function(e){
    var b=e.target.closest('[data-tpick]'); if(!b) return;
    e.preventDefault();
    var t=b.getAttribute('data-tpick'), v=get(), i=v.indexOf(t);
    if(i>-1){ v.splice(i,1); } else { v.push(t); }
    set(v); apply(); panel();
  });

  /* C-4: THE PANEL. The reader's teams, in the order the board will use, with the two
     controls that change it. Buttons and not drag: drag needs a pointer, fights a
     scrolling phone, and is invisible to a keyboard and a screen reader. */
  function nextFor(ab){
    /* The best line this board can give about one team, in order of what a reader
       wants: a game in play, then a result from today, then the next kickoff. Read off
       the cards' own attributes, so the panel cannot disagree with the card. */
    var best=null, rank={'in':0, 'post':1, 'pre':2};
    document.querySelectorAll('.tk-c[data-gid]').forEach(function(c){
      var aw=c.getAttribute('data-away'), hm=c.getAttribute('data-home');
      if(aw!==ab && hm!==ab) return;
      var st=c.getAttribute('data-state')||'pre';
      var r=rank[st]; if(r===undefined) r=3;
      if(best===null || r<best.r) best={r:r, c:c, st:st, aw:aw, hm:hm};
    });
    if(!best) return '';
    var other = (best.aw===ab) ? best.hm : best.aw;
    var vs = (best.aw===ab) ? 'at '+other : 'v '+other;
    if(best.st==='pre'){
      var k=best.c.getAttribute('data-kick-et')||'';
      return k ? vs+', '+k : vs;
    }
    /* A score belongs to a side, so it is read from the card's own halves rather than
       assembled from two numbers whose order this function would have to guess. */
    var mine=best.c.querySelector('[data-side="'+(best.aw===ab?'away':'home')+'"]');
    var theirs=best.c.querySelector('[data-side="'+(best.aw===ab?'home':'away')+'"]');
    function num(el){ if(!el) return null; var n=el.querySelector('.tk-sc');
      var t=(n?n.textContent:el.textContent)||''; t=t.replace(/[^0-9-]/g,'');
      return t===''?null:t; }
    var a=num(mine), b=num(theirs);
    if(a===null||b===null) return vs;
    return (best.st==='in'?'live ':'')+a+'-'+b+' '+vs;
  }

  function nameOf(ab){
    var n=document.querySelector('[data-tabbr="'+ab+'"][data-tname]');
    return (n && n.getAttribute('data-tname')) || ab;
  }
  function panel(){
    var secs=document.querySelectorAll('[data-mine]');
    if(!secs.length) return;
    var v=get();
    [].forEach.call(secs, function(sec){
      var ol=sec.querySelector('.mine-l');
      sec.hidden = !v.length;
      if(!v.length){ ol.innerHTML=''; return; }
      ol.innerHTML = v.map(function(ab,i){
        var nm = nameOf(ab);
        /* E-2, THE READER PANEL: the row says what is NEXT for this team, not just
           that it is pinned. A list of names the reader already knows is a list of
           names; the fact they came for is when their team plays and what happened
           last time. Both are on this page already, on the cards, so the panel reads
           them off the board rather than asking anyone for anything. */
        var nx = nextFor(ab);
        /* The first row cannot move up and the last cannot move down. A disabled
           button that says what it would do is clearer than one that silently does
           nothing, and a screen reader announces the state. */
        return '<li class="mine-r" data-ab="'+ab+'">'
             + '<span class="mine-p">'+(i+1)+'</span>'
             + '<span class="mine-nm">'+nm+(nx?'<span class="mine-w">'+nx+'</span>':'')
               +'</span>'
             + '<span class="mine-b">'
             + '<button type="button" class="mine-x" data-act="up" data-ab="'+ab+'"'
             + (i===0?' disabled':'')+' aria-label="Move '+nm+' up">&#9650;</button>'
             + '<button type="button" class="mine-x" data-act="down" data-ab="'+ab+'"'
             + (i===v.length-1?' disabled':'')+' aria-label="Move '+nm+' down">'
             + '&#9660;</button>'
             + '<button type="button" class="mine-x mine-off" data-act="off" '
             + 'data-ab="'+ab+'" aria-label="Unpin '+nm+'">Unpin</button>'
             + '</span></li>';
      }).join('');
    });
  }
  document.addEventListener('click', function(e){
    var b=e.target.closest('.mine-x'); if(!b) return;
    e.preventDefault();
    var act=b.getAttribute('data-act');
    var ab=b.getAttribute('data-ab'), v=get(), i=v.indexOf(ab);
    if(i<0) return;
    if(act==='off'){ v.splice(i,1); }
    else if(act==='up' && i>0){ v.splice(i,1); v.splice(i-1,0,ab); }
    else if(act==='down' && i<v.length-1){ v.splice(i,1); v.splice(i+1,0,ab); }
    else { return; }
    set(v); apply(); panel();
    /* KEEP THE READER'S PLACE. The list is rebuilt from scratch on every change, so
       the button that was just pressed no longer exists and focus falls to the top of
       the document: a keyboard reader loses their position on every single press. The
       same control on the row that moved gets focus back, and where that control has
       just become disabled (a team moved to the top can no longer move up) or the row
       is gone entirely (an unpin), the first control that is still usable takes it. */
    var again = (act === 'off') ? null
      : document.querySelector('.mine-r[data-ab="' + ab + '"] [data-act="' + act + '"]');
    if (!again || again.disabled) {
      again = document.querySelector('.mine-l .mine-x:not([disabled])');
    }
    if (again) again.focus();
  });
  /* THE FIRST PASS WAITS FOR THE DOCUMENT, for the same reason the lens does: this
     script is attached to the band, and on /scores the band is parsed before the card
     grid. apply() only needed storage and survived it; panel() reads the CARDS to say
     what is next for each team, so run early it found none and every row rendered as a
     bare name. The rows looked right, which is how it would have shipped. */
  function boot(){ apply(); panel(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();</script>"""


def team_pin(abbr, name=""):
    """S-L3: pin this team. Device-only, on the same pattern as the crypto desk's coin
    pins, and hidden outright where storage is unavailable rather than offering a
    control that cannot remember anything."""
    if not abbr:
        return ""
    nm = f' data-tabbr="{esc(abbr)}" data-tname="{esc(name)}"' if name else ""
    return (f'<span class="tpinwrap" data-tpin{nm}>'
            f'<button type="button" class="wl-pick tpin" data-tpick="{esc(abbr)}" '
            f'aria-pressed="false">Pin {esc(abbr)}</button></span>')


def pins_panel():
    """C-4: the reader's own teams, in the order they will appear, and reorderable.

    The pins already move a team's card to the front of its group, but the ORDER was
    whatever order they were picked in, and there was no way to change it and nowhere to
    see them together at all. A reader with four teams had no way to say which one leads
    the board on a Sunday.

    Buttons and not drag. Drag is the obvious gesture and it is the one that fails: it
    needs a pointer, it fights a scrolling phone, and it is invisible to a keyboard and
    to a screen reader. Two buttons per row work everywhere and say what they do.

    Rendered empty and filled by the script from storage, because the pins are on the
    device and the build has never heard of them. Hidden until there is something in it.
    """
    return ('<section class="mine" data-mine hidden aria-labelledby="mine-h">'
            '<div class="mine-t"><h3 id="mine-h">My teams</h3>'
            '<span class="mine-n">Your board leads with these, in this order.</span>'
            '</div><ol class="mine-l"></ol></section>')


def _team_pin_index(team_data):
    """Every team's abbreviation paired with its full name, so the script can match a
    pinned abbreviation against the hub's blocks, which are named in full. Rendered
    once per page that needs it, as data rather than as script."""
    rows = sorted((team_data or {}).get("teams", {}).items())
    if not rows:
        return ""
    return ('<span hidden>' + "".join(
        f'<span data-tabbr="{esc(a)}" data-tname="{esc(t.get("name") or "")}"></span>'
        for a, t in rows) + '</span>')


def mini_scoreboard(sb):
    """A-3: the thin strip, with ids so the poll can move it.

    It carried no data-gid, so the poll could not touch it: at 2:23 PM on NFL Sunday
    the strip still showed one soccer match from the build while seventeen games were
    live on the board above it. Every item now carries its game id, league and state,
    and the same paint() that moves a card moves the strip.

    WHAT IT HOLDS. Live games first, then the next kickoffs, so a strip is never empty
    on a morning before the slate starts, which is when a reader most wants to know
    what is coming. The reader's pinned teams are moved to the front on the client
    (S-L3's store), because the desk does not know what they pinned and should not.
    """
    if not sb or not sb.get("leagues"):
        return ""
    games = [g for L in sb["leagues"] for g in L["games"]]
    live = [g for g in games if g.get("state") == "in"]
    nxt = sorted((g for g in games if g.get("state") == "pre" and g.get("start_utc")),
                 key=lambda g: g["start_utc"])
    show = (live + nxt)[:8]
    if not show:
        return ""
    cells = []
    for g in show:
        a, h = g.get("away") or {}, g.get("home") or {}
        ca, ch = _tk_colors(g)
        sa, sh = a.get("score"), h.get("score")
        started = g.get("state") in ("in", "post")

        def side(t, sc, col, lead, which):
            val = "" if (sc is None or not started) else esc(str(sc))
            return (f'<span class="msb-t">{_rank_html(g, t, cls="tk-rk msb-rk")}'
                    f'<b style="color:{col}">{esc(t.get("abbr") or "")}</b>'
                    f'<span class="msb-s{" msb-lead" if lead else ""}" '
                    f'data-side="{which}">{val}</span></span>')
        try:
            ia, ih = int(sa), int(sh)
            tie = ia == ih
        except (TypeError, ValueError):
            ia = ih = None
            tie = True
        _kd = _utc_dt(g.get("start_utc") or "")
        status = (g.get("status_short") or "") if started else (
            _et_clock(_kd) if _kd else "")
        cells.append(
            f'<a class="msb-g" data-gid="{esc(str(g.get("id") or ""))}" '
            f'data-league="{esc(g.get("league") or "")}" '
            f'data-state="{esc(g.get("state") or "")}" '
            f'data-away="{esc(a.get("abbr") or "")}" '
            f'data-home="{esc(h.get("abbr") or "")}" '
            f'href="{esc(_game_href(g))}">'
            + side(a, sa, ca, ia is not None and not tie and ia > ih, "away")
            + side(h, sh, ch, ih is not None and not tie and ih > ia, "home")
            + f'<span class="msb-st" data-role="msb-status">{esc(status)}</span></a>')
    return (f'<div class="msb" role="region" aria-label="Live scores" hidden>'
            f'<div class="msb-in">{"".join(cells)}'
            f'<a class="msb-all" href="/scores.html">All scores</a></div></div>')


def scoreboard_band(sb, board, wx=None):
    """The dark band under the masthead. Returns "" when there is nothing to show, so
    the homepage simply does not carry it rather than carrying an empty shell."""
    if not sb or not sb.get("leagues"):
        return ""
    games = [g for L in sb["leagues"] for g in L["games"]]
    if not games:
        return ""
    ia = _ia_index(board)
    mq = _sb_marquee_pick(games)
    rest = [g for g in games if g is not mq]
    # Live first, then upcoming, then finals: what a reader opened the page for.
    # CFB-1: today's weighting, then the poll rank, then the clock. It was
    # SB_TAB_ORDER's fixed index, which is why MLB sat above college football on a
    # Saturday in September.
    rest.sort(key=_sb_sort_key)
    present = [n for n in _day_league_order() if any(g["league"] == n for g in games)]
    n_live = sum(1 for g in games if g.get("state") == "in")
    _today, _nxt_lab, _nxt_n = _sb_day_split(games)
    if _today:
        count_line = (f"{len(_today)} game{'' if len(_today) == 1 else 's'} today"
                      f" · {n_live} live now")
        foot_link = f"All {len(_today)} game{'' if len(_today) == 1 else 's'}"
    elif _nxt_n:
        count_line = (f"No games today · {_nxt_n} "
                      f"{'game' if _nxt_n == 1 else 'games'} {_nxt_lab}")
        foot_link = "All games"
    else:
        count_line = "No games scheduled"
        foot_link = "All games"
    # SC-4: the tabs carry a count or a next date and switch the whole band.
    tabs = _tk_tabs(games, active="all")
    # SC-4: every league's own marquee and folded set is rendered, and the script shows
    # one at a time. Rendering only the active league would mean a tab could not switch
    # anything without a round trip, and rendering nothing but links would make the tabs
    # a navigation rather than a switcher. The cost is about 8 KB gzipped for a band
    # that then switches instantly and still works with no script at all, because every
    # tab is a real link to that league's section on /scores.
    def _panel(league):
        pool = [g for g in games if league == "all" or g.get("league") == league]
        if not pool:
            return ""
        m = _sb_marquee_pick(pool)
        others = [g for g in pool if g is not m]
        others.sort(key=_sb_sort_key_in_league)
        slug = "all" if league == "all" else league.lower().replace(" ", "-")
        # H-6: the count and the next kickoff belong to the panel, so they follow the
        # tab. They used to sit in the band header and describe the whole slate, so
        # picking NFL left "No games today \u00b7 6 games tomorrow" and "Next: CON at
        # ATL" above a board of NFL games.
        _today_p, _lab_p, _n_p = _sb_day_split(pool)
        _live_p = sum(1 for g in pool if g.get("state") == "in")
        if _today_p:
            _count_p = (f"{len(_today_p)} game{'' if len(_today_p) == 1 else 's'} today"
                        f" \u00b7 {_live_p} live now")
            _foot_p = f"All {len(_today_p)} game{'' if len(_today_p) == 1 else 's'}"
        else:
            # H-6 follow-up: THE COUNT LINE NAMES WHAT THE TAB HOLDS. With the MLB tab
            # reading "15 final" the count line read "No games scheduled", which
            # contradicts the board beside it.
            #
            # The first cut of this fix only caught the case where the pool held
            # nothing but finals, which almost never happens: a pool that holds
            # yesterday's finals usually holds the next fixture too, and then the count
            # read "No games today - 1 game Thursday" over fifteen final scorecards.
            # Finals are named whenever the panel has them, before the no-games line
            # gets a turn.
            _done = sum(1 for g in pool if g.get("state") == "post")
            _nxt_all = sorted((_utc_dt(g.get("start_utc") or "") for g in pool
                               if _utc_dt(g.get("start_utc") or "")))
            _nxt_all = [d for d in _nxt_all if d > _build_now()]
            if _done:
                _count_p = f"{_done} final"
                if _nxt_all:
                    _d0 = _nxt_all[0].astimezone(_ET)
                    _count_p += (f" \u00b7 next {_d0.strftime('%a')} "
                                 f"{_et_clock(_nxt_all[0])}")
            elif _n_p:
                _count_p = (f"No games today \u00b7 {_n_p} "
                            f"{'game' if _n_p == 1 else 'games'} {_lab_p}")
            else:
                _count_p = "No games scheduled"
            _foot_p = "All games"
        _nxt_p = ""
        _pre_p = sorted((g for g in pool if g.get("state") == "pre"),
                        key=lambda g: g.get("start_utc") or "")
        if _pre_p:
            _pg = _pre_p[0]
            _pd = _utc_dt(_pg.get("start_utc") or "")
            if _pd:
                _nxt_p = (f'<span class="sb-next">Next: '
                          f'{esc(_team_label(_pg, _pg.get("away") or {}))} at '
                          f'{esc(_team_label(_pg, _pg.get("home") or {}))} '
                          f'{esc(_et_clock(_pd))}</span>')
        # H-3: each fold carries its own full card beside it, hidden. The panel already
        # holds every game, so opening one is a class swap with nothing fetched and no
        # layout built from scratch. A reader with no script still gets the fold's link
        # to the game page, which is the same information.
        def _pair(gg):
            return (f'<div class="tk-pair" data-gid="{esc(str(gg.get("id")))}">'
                    f'{_tk_fold(gg, ia, desig=IA_DESIG)}'
                    f'<div class="tk-open" hidden>'
                    f'{_tk_card(gg, ia, wx=wx, desig=IA_DESIG, items=ALL_ITEMS)}'
                    f'<button class="tk-close" type="button" aria-label="Close">'
                    f'Close</button></div></div>')
        return (f'<div class="sb-grid tk-panel" data-league="{esc(slug)}"'
                f'{"" if slug == "all" else " hidden"}>'
                f'{_tk_card(m, ia, wx=wx, desig=IA_DESIG, items=ALL_ITEMS) if m else ""}'
                f'<div class="sb-cards">'
                + "".join(_pair(g) for g in others[:6])
                + f'</div><div class="sb-foot tk-foot">'
                  f'<a class="sb-link" href="/scores.html#{esc(slug)}">{esc(_foot_p)}'
                  f' &rarr;</a>{_nxt_p}</div>'
                  f'<span class="tk-count" hidden>{esc(_count_p)}</span>'
                + '</div>')

    panels = "".join(_panel(n) for n in ["all"] + present)
    stamp = _et(sb.get("fetched_at") or "")
    # H-7: the stale mark rides beside the stamp, and the live dot goes with it.
    if sb.get("stale"):
        stamp += " \u00b7 stale"
    # S-25: the next kickoff, from the feed. Absent when nothing is scheduled.
    nxt = ""
    _pre = sorted((g for g in games if g.get("state") == "pre"),
                  key=lambda g: g.get("start_utc") or "")
    if _pre:
        _g = _pre[0]
        _dt = _utc_dt(_g.get("start_utc") or "")
        if _dt:
            nxt = (f'<span class="sb-next">Next: '
                   f'{esc(_team_label(_g, _g.get("away") or {}))} at '
                   f'{esc(_team_label(_g, _g.get("home") or {}))} '
                   f'{esc(_et_clock(_dt))}</span>')
    _orn = _sb_ornament(games)
    return f"""<section class="scoreband sb-hero{'' if _orn else ' no-orn'}" data-built="{_build_now().strftime('%Y-%m-%dT%H:%M:%SZ')}" data-built-et="{_et_clock(_build_now())}" aria-label="The Scoreboard">
  <div class="sb-bg" aria-hidden="true"></div>
  <div class="sb-scrim" aria-hidden="true"></div>
  <div class="wrap sb-inner">
    <div class="sb-promise">
      <div class="sb-promise-l">
        <h2 class="sb-claim">Scoreboard</h2>

      </div>
      <span class="sb-count">{esc(count_line)}</span>
    </div>
    <div class="sb-head">
      <div class="sb-head-l">
        <div class="sb-tabs">{tabs}</div>
        {lens_control()}{_week_link()}</div>
      <span class="sb-stamp">Updated {esc(stamp)}</span>
    </div>
    {panels}
  </div>
  {_orn}
</section>
<div class="sb-fade" aria-hidden="true"></div>""" + mini_scoreboard(sb) + _team_pin_index(TEAM_DATA) + SB_HERO_JS + SB_TABS_JS + SB_LIVE_JS + MINI_SB_JS + TEAM_PIN_JS + LENS_JS


# ---- S-L1: standings and the college football rankings ---------------------------
# The audit's first lead item: the site had no standings anywhere, and standings are one
# of the five things a reader opens a sports site for. They come from the same lane the
# band reads, they are read on their own pages, and they carry a tab on /scores.
#
# THE RULE THIS MODULE IS BUILT AROUND. standings.py writes a league only when its teams
# have played. In September the upstream endpoint answers for the 2026-27 basketball and
# hockey seasons, thirty teams at 0-0, and a full table of zeros looks like a result. So
# there is no "no data yet" table here and no placeholder: a league with nothing to show
# is not on the page, which is the same law the Board tiles follow.

ST_DATA = None            # set at build by standings.load()

# The columns a reader actually reads, per league, in the order they read them. Anything
# the source did not send for a row is blank, never a zero.
ST_COLS = {
    # Points for and against came out: nine stat columns did not fit two tables across
    # at 1440 and the streak was clipped off the right edge of every one of them. The
    # differential carries what PF and PA were there to say.
    "nfl": [("wins", "W"), ("losses", "L"), ("ties", "T"), ("winPercent", "PCT"),
            ("divisionRecord", "DIV"), ("differential", "DIFF"), ("streak", "STRK")],
    "mlb": [("wins", "W"), ("losses", "L"), ("winPercent", "PCT"),
            ("gamesBehind", "GB"), ("streak", "STRK")],
    "nba": [("wins", "W"), ("losses", "L"), ("winPercent", "PCT"),
            ("gamesBehind", "GB"), ("streak", "STRK")],
    "nhl": [("wins", "W"), ("losses", "L"), ("winPercent", "PCT"), ("streak", "STRK")],
}


def _team_page_exists(abbr):
    return bool((TEAM_DATA or {}).get("teams", {}).get(abbr))


def _st_cell(v):
    """A figure the source sent, or nothing. Never a zero standing in for a gap."""
    return esc(str(v)) if v not in (None, "", "-") else ""


def _st_table(key, group):
    cols = ST_COLS.get(key) or ST_COLS["nfl"]
    cols = [(k, lab) for k, lab in cols
            if any(r.get(k) not in (None, "") for r in group["rows"])]
    head = "".join(f'<th scope="col">{esc(lab)}</th>' for _k, lab in cols)
    body = []
    for n, r in enumerate(group["rows"], 1):
        cells = "".join(f'<td>{_st_cell(r.get(k))}</td>' for k, _lab in cols)
        # S-L2: a team in a standings table is a link to that team's page, where one
        # was built. Only NFL has team pages today, so only NFL rows link; a row that
        # linked to a page that does not exist is worse than a row that does not link.
        who = (f'<span class="st-abbr">{esc(r.get("abbr") or "")}</span>'
               f'<span class="st-name">{esc(r.get("team") or "")}</span>')
        if key == "nfl" and r.get("abbr") and _team_page_exists(r["abbr"]):
            who = f'<a href="/teams/{esc(r["abbr"].lower())}.html">{who}</a>'
        body.append(f'<tr><td class="st-pos">{n}</td>'
                    f'<td class="st-team">{who}</td>{cells}</tr>')
    # "American League East" under a heading that already says American League: the
    # conference prefix comes off the display, the way the venue map tidies a name
    # without renaming it. The source's own spelling stays in standings.json.
    label = group["name"]
    conf = group.get("conference") or ""
    if conf and label.startswith(conf + " "):
        label = label[len(conf) + 1:]
    return (f'<div class="st-block"><h3 class="st-h">{esc(label)}</h3>'
            f'<div class="st-wrap"><table class="st-t">'
            f'<thead><tr><th scope="col"><span class="sr-only">Position</span></th>'
            f'<th scope="col">Team</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')


def _st_league_block(lg):
    """One league: its groups, under the conference each sits in when it has one."""
    by_conf = {}
    for g in lg["groups"]:
        by_conf.setdefault(g.get("conference") or "", []).append(g)
    out = []
    for conf, groups in by_conf.items():
        if conf:
            out.append(f'<div class="sec-head" style="margin-top:22px">'
                       f'<h2>{esc(conf)}</h2><span class="bar"></span></div>')
        out.append('<div class="st-grid">'
                   + "".join(_st_table(lg["key"], g) for g in groups) + '</div>')
    return "".join(out)


def _st_stamp(st):
    """One stamp, as the copy law asks, and the season year is not on it: the source
    said 2027 for a table of 2026 results, so the year is not something this page can
    assert. See the note at the top of standings.py."""
    t = _utc_dt(st.get("fetched_at") or "")
    if not t:
        return ""
    mark = " \u00b7 stale" if st.get("stale") else ""
    return f'<span class="sec-n">Updated {_et_clock(t)}{mark}</span>'


# ---- S-L2: team pages ------------------------------------------------------------
# The audit's second lead item, and the missing third of a set: the game page and the
# player page exist, /teams/det did not. Everything on it is furniture the desk already
# owns, joined on the one key that is an identity here: the team's full name. The
# schedules file names a team "Buffalo Bills", the inactives board names it "Buffalo
# Bills", and the standings row names it "Buffalo Bills". Abbreviations collide across
# leagues and nicknames are ordinary English; the full name is neither.

TEAM_DATA = None          # set at build by schedules.load()


def _team_standing(abbr):
    """This team's standings row and the group it sits in, or (None, "")."""
    for lg in ((ST_DATA or {}).get("leagues") or []):
        if lg.get("key") != "nfl":
            continue
        for g in lg["groups"]:
            for n, r in enumerate(g["rows"], 1):
                if r.get("abbr") == abbr:
                    return r, g["name"], n
    return None, "", 0


def _ord(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _team_standing_line(abbr):
    r, group, pos = _team_standing(abbr)
    if not r:
        return ""
    rec = "-".join(x for x in (r.get("wins"), r.get("losses"),
                               r.get("ties") if r.get("ties") not in (None, "0") else None)
                   if x is not None)
    bits = [b for b in (rec, f"{_ord(pos)} in {group}" if group else "",
                        r.get("streak")) if b]
    return " \u00b7 ".join(bits)


def _team_desig(full_name):
    """Every player this team has on the official report, by name, with the injury and
    the status. The same source the game page reads (IA_DESIG.groups), matched on the
    team's FULL NAME, which is what those rows carry."""
    order = {"out": 0, "doubtful": 1, "questionable": 2}
    rows = []
    for _status, players in ((IA_DESIG or {}).get("groups") or {}).items():
        for p in (players or []):
            if (p.get("team") or "").strip() == full_name and p.get("name"):
                rows.append(p)
    rows.sort(key=lambda p: (order.get((p.get("status") or "").lower(), 9),
                             p.get("name") or ""))
    return rows


def _team_stories(full_name, nickname, items, n=6):
    """The desk's stories about this team.

    THE SAME RULE THE GAME PAGE LEARNED. A nickname is a shallow key: half the NFL's
    are ordinary English, and matching "Bills" against a key fact once handed a
    television-ratings story to a Lions-Bills card. The full name is required where the
    desk knows it; a nickname qualifies only in the HEADLINE, which is a claim about
    what a story is about, and never in a body detail. Case-sensitive either way.
    """
    out = []
    for i in (items or []):
        if i.get("example") or _is_wrap(i) or i.get("superseded_by"):
            continue
        title = i.get("title") or ""
        # THE KEY FACT IS NOT THE SUBJECT. The first cut matched the full name anywhere
        # in the story's summary fields, and put a 49ers story on the Titans page: the
        # key fact named the Titans as the opponent Shanahan's team was playing. A team
        # page is a page about a team, so the claim has to be in the headline or the
        # dek, which are what a story says it is about; a detail inside one is not.
        claim = " ".join([title, i.get("dek") or ""])
        if (full_name and full_name in claim) or (nickname and len(nickname) > 2
                                                  and nickname in title):
            out.append(i)
    out.sort(key=lambda i: i.get("published_utc") or "", reverse=True)
    return [i for i in out if _claim(i.get("slug"))][:n]


def _team_row(e, colors):
    """One fixture from this team's side. A score renders only when the game is over:
    a scheduled game has no result, and a 0 standing in for one would be a reading the
    desk never took."""
    dt = _utc_dt(e.get("date") or "")
    when = ""
    if dt:
        et = dt.astimezone(_ET)
        when = f'{et.strftime("%a %-d %b")}'
    if e.get("bye"):
        return (f'<tr class="tm-bye"><td class="tm-wk">{esc(str(e.get("week") or ""))}</td>'
                f'<td class="tm-dt"></td><td class="tm-opp"></td>'
                f'<td class="tm-r"><span class="tm-time">Bye</span></td>'
                f'<td class="tm-n"></td></tr>')
    opp = esc(e.get("opp") or "")
    at = "at" if not e.get("home") else "vs"
    res = ""
    if e.get("result"):
        cls = {"W": "tm-w", "L": "tm-l"}.get(e["result"], "tm-t")
        res = (f'<span class="tm-res {cls}">{esc(e["result"])}</span>'
               f'<span class="tm-sc">{e.get("score")}-{e.get("opp_score")}</span>')
    elif e.get("bye"):
        res = '<span class="tm-time">Bye</span>'
    elif dt and e.get("state") != "post":
        # A kickoff the league has not set is not a kickoff. The feed says so with
        # timeValid, and believing it printed "12:00 AM ET" against Week 18.
        res = (f'<span class="tm-time">{_et_clock(dt)}</span>' if e.get("time_set", True)
               else '<span class="tm-time">Time TBA</span>')
    net = (f'<span class="tm-net">{esc(e["network"])}</span>'
           if e.get("network") and not e.get("result") else "")
    wk = e.get("week")
    return (f'<tr><td class="tm-wk">{esc(str(wk)) if wk else ""}</td>'
            f'<td class="tm-dt">{esc(when)}</td>'
            f'<td class="tm-opp"><span class="tm-at">{at}</span>'
            f'<a href="/teams/{opp.lower()}.html">{opp}</a></td>'
            f'<td class="tm-r">{res}</td><td class="tm-n">{net}</td></tr>')


def render_team_page(tm, items, dateline):
    abbr = tm["abbr"]
    name = tm.get("name") or abbr
    stand = _team_standing_line(abbr)
    evs = sorted(tm.get("events") or [], key=lambda e: e.get("date") or "")
    played = [e for e in evs if e.get("result")]
    # S-L2: the bye is a week of the season. Without it the table reads 5 then 7 and
    # looks like a missing row rather than a week off.
    fixtures = len(evs)          # the bye is a week, not a fixture, and is not counted
    bye = tm.get("bye")
    if bye:
        weeks = [e.get("week") for e in evs]
        if bye not in weeks:
            at = next((n for n, w in enumerate(weeks) if w and w > bye), len(evs))
            evs = evs[:at] + [{"week": bye, "bye": True}] + evs[at:]
    nxt = next((e for e in evs if e.get("state") != "post"), None)

    next_line = ""
    if nxt:
        dt = _utc_dt(nxt.get("date") or "")
        when = f'{dt.astimezone(_ET).strftime("%a %-d %b")} {_et_clock(dt)}' if dt else ""
        next_line = (
            f'<div class="tm-next"><span class="bd-label">Next</span>'
            f'<span class="tm-next-o">{"vs" if nxt.get("home") else "at"} '
            f'{esc(nxt.get("opp_name") or nxt.get("opp") or "")}</span>'
            + (f'<span class="bd-stamp">{esc(when)}</span>' if when else "")
            + (f'<span class="bd-stamp">{esc(nxt["network"])}</span>'
               if nxt.get("network") else "")
            + '</div>')

    desig = _team_desig(name)
    inj = ""
    if desig:
        inj = ('<div class="sec-head" style="margin-top:26px"><h2>Injury report</h2>'
               f'<span class="bar"></span><span class="sec-n">{len(desig)} '
               f'player{"" if len(desig) == 1 else "s"}</span></div>'
               '<div class="gp-dz-rows">'
               + "".join(
                   f'<div class="gp-dz-row"><span class="gp-dz-st s-'
                   f'{esc((p.get("status") or "").lower()[:1] or "x")}">'
                   f'{esc((p.get("status") or "")[:1].upper() or "?")}</span>'
                   f'<span class="gp-dz-n">{esc(p.get("name"))}</span>'
                   f'<span class="gp-dz-p">{esc(p.get("pos") or "")}</span>'
                   f'<span class="gp-dz-i">{esc(_injury_case(p.get("detail") or ""))}</span>'
                   f'</div>'
                   for p in desig)
               + '</div>')

    stories = _team_stories(name, tm.get("nickname") or "", items)
    news = ""
    if stories:
        news = ('<div class="sec-head" style="margin-top:26px"><h2>From the desk</h2>'
                '<span class="bar"></span></div><div class="rs">'
                + "".join(
                    f'<a class="rs-m" href="/articles/{esc(i["slug"])}.html">'
                    f'{esc(i.get("title") or "")}</a>' for i in stories)
                + '</div>')

    body = f"""<main class="wrap"><section class="page">
  <h1 class="sr-only">{esc(name)}: schedule, results, injury report and standing</h1>
  <div class="sec-head"><h2>{esc(name)}</h2><span class="bar"></span>
    {f'<span class="sec-n">{esc(stand)}</span>' if stand else ""}
    {team_pin(abbr, name)}</div>
  {next_line}
  <div class="sec-head" style="margin-top:24px"><h2>Schedule and results</h2>
    <span class="bar"></span>
    <span class="sec-n">{len(played)} played of {fixtures}</span></div>
  <div class="st-wrap"><table class="st-t tm-t">
    <thead><tr><th scope="col">Wk</th><th scope="col">Date</th>
      <th scope="col">Opponent</th><th scope="col">Result</th>
      <th scope="col">TV</th></tr></thead>
    <tbody>{"".join(_team_row(e, None) for e in evs)}</tbody></table></div>
  {inj}{news}
  <nav class="st-nav" aria-label="Related">
    <a class="st-nav-a" href="/standings/nfl.html">NFL standings</a>
    <a class="st-nav-a" href="/fantasy/inactives.html">Inactives</a>
    <a class="st-nav-a" href="/scores.html">Scores</a></nav>
</section></main>""" + TEAM_PIN_JS
    return shell(f"{name}: schedule, results and injury report - {NAME}",
                 f"{name} schedule and results, the official injury report, the "
                 f"standing, and the desk's stories about the team.",
                 "Scores", body, dateline, path=f"/teams/{abbr.lower()}.html")


WEEK_COUNT = 18


def _sched_week(team_data, wk):
    """B-4: one week's fixtures, rebuilt from the 32 team schedules.

    WHY FROM THERE. The scoreboard feed is today and only today: it cannot answer "what
    happened in week 1" or "who plays next Sunday", which is most of what a reader wants
    from a board in September. The team schedules already on file carry every fixture of
    the season with its result, so the week is a regroup of data the desk holds rather
    than a new request to anyone.

    Each game appears twice, once in each team's file, so the id is the identity and the
    two views are merged. A game seen from its home team's side is the one that decides
    who is home, because that is the only side that states it without inference.
    """
    out = {}
    for abbr, t in ((team_data or {}).get("teams") or {}).items():
        for e in t.get("events") or []:
            if e.get("week") != wk or not e.get("id"):
                continue
            gid = str(e["id"])
            home_ab = abbr if e.get("home") else e.get("opp") or ""
            away_ab = (e.get("opp") or "") if e.get("home") else abbr
            g = out.setdefault(gid, {"id": gid, "date": e.get("date"),
                                     "state": e.get("state") or "",
                                     "time_set": e.get("time_set", True),
                                     "network": e.get("network") or "",
                                     "home": home_ab, "away": away_ab,
                                     "home_score": None, "away_score": None})
            if not g.get("network") and e.get("network"):
                g["network"] = e["network"]
            if e.get("score") is not None and e.get("opp_score") is not None:
                if e.get("home"):
                    g["home_score"], g["away_score"] = e["score"], e["opp_score"]
                else:
                    g["away_score"], g["home_score"] = e["score"], e["opp_score"]
    return sorted(out.values(), key=lambda g: (g.get("date") or "", g["away"]))


def _week_row(g, names):
    """One fixture. A result where there is one, a kickoff where there is not, and
    never a zero standing in for a game that has not been played."""
    dt = _utc_dt(g.get("date") or "")
    when = ""
    if dt:
        d = dt.astimezone(_ET)
        # schedules.py carries the feed's own timeValid: week 18 comes back at 05:00Z
        # with the clock unset, and printing it would be a precise time the league has
        # not announced.
        when = (f'{d.strftime("%a %-d %b")} &middot; {_et_clock(dt)}'
                if g.get("time_set", True) else d.strftime("%a %-d %b"))
    hs, as_ = g.get("home_score"), g.get("away_score")
    played = hs is not None and as_ is not None
    def side(ab, sc, won):
        nm = esc(names.get(ab) or ab)
        cls = " wk-w" if won else ""
        val = (f'<span class="wk-sc{cls}">{sc}</span>' if played else "")
        return (f'<span class="wk-t{cls}"><a href="/teams/{esc(ab.lower())}.html">'
                f'{nm}</a></span>{val}')
    aw = side(g["away"], as_, played and as_ > hs)
    hm = side(g["home"], hs, played and hs > as_)
    right = (f'<span class="wk-when">{when}</span>'
             + (f'<span class="wk-net">{esc(g["network"])}</span>'
                if g.get("network") and not played else ""))
    return (f'<li class="wk-r{" wk-done" if played else ""}">'
            f'<span class="wk-sides">{aw}<span class="wk-at">at</span>{hm}</span>'
            f'{right}</li>')


def _week_link():
    """B-4: the board is today. This is the way to every other day of the season, and
    it names the week it goes to rather than saying "schedule", because a reader who
    wants last Sunday's results is looking for a number."""
    wk, _ = nfl_week()
    if not wk:
        return ""
    return (f'<a class="wk-link" href="/nfl/week-{wk}.html">'
            f'NFL week {wk} and the season</a>')


def week_selector(active, week_now=None):
    """The strip of weeks. Eighteen links, the current one marked, and the one being
    read marked differently: "this week" and "the week you are looking at" are two
    different facts and a reader in week 6 in November needs both."""
    bits = []
    for w in range(1, WEEK_COUNT + 1):
        cls = "wk-b"
        if w == active:
            cls += " on"
        if week_now and w == week_now:
            cls += " now"
        bits.append(f'<a class="{cls}" href="/nfl/week-{w}.html" '
                    + (f'aria-current="page" ' if w == active else "")
                    + f'>{w}</a>')
    return ('<nav class="wk-nav" aria-label="NFL week">'
            '<span class="wk-k">Week</span>' + "".join(bits) + '</nav>')


def render_week_page(team_data, wk, dateline, week_now=None):
    games = _sched_week(team_data, wk)
    names = {a: (t.get("short") or t.get("name") or a)
             for a, t in ((team_data or {}).get("teams") or {}).items()}
    played = sum(1 for g in games if g.get("home_score") is not None)
    if not games:
        body = '<p class="wk-none">No fixtures on file for this week.</p>'
        count = ""
    else:
        body = '<ul class="wk-l">' + "".join(_week_row(g, names) for g in games) + '</ul>'
        count = (f'{len(games)} game{"" if len(games) == 1 else "s"}'
                 + (f', {played} played' if played else ''))
    head = (f'<div class="wk-head"><h1>NFL week {wk}</h1>'
            + (f'<span class="wk-c">{esc(count)}</span>' if count else "") + '</div>')
    note = ('<p class="bd-src">Fixtures and results as the league reports them. '
            'Today\'s games are live on the '
            '<a href="/scores.html">scoreboard</a>.</p>')
    return shell(
        f"NFL week {wk} - {NAME}",
        (f"Every NFL game in week {wk}: the fixtures, the kickoff times and the "
         f"results, as the league reports them."),
        "Scores",
        f'<section class="page wrap wk-page">{head}'
        f'{week_selector(wk, week_now)}{body}{note}</section>',
        dateline, path=f"/nfl/week-{wk}.html")


WIRE_HOURS = 48
WIRE_MAX = 120


def _wire_rows(items, now=None):
    """E-2: THE WIRE. Everything this desk did, newest first, with the time it happened.

    A returning reader's question is "what has happened since I last looked", and no
    page answered it. The front page answers "what matters now", the archive answers
    "what exists", and between them the desk's own working day was invisible: a story
    published at 10:42, a list posted at 11:32, a game final at 4:25 and an Edition at
    7:48 were four facts on four different surfaces with nothing putting them in order.

    A LOG, NOT A LIVE BLOG. Every line is something that happened, stamped when it
    happened, linking to the thing itself. Nothing is written for the Wire: if a line is
    here, the fact is somewhere else on this site and this is the index to it in time.

    Built from what is already on disk, so it costs no request and cannot disagree with
    the pages it points at.
    """
    now = now or _build_now()
    cut = now - datetime.timedelta(hours=WIRE_HOURS)
    rows = []

    for it in (items or []):
        if it.get("example") or it.get("superseded_by"):
            continue
        t = _parse_utc(it)
        if not t or t < cut:
            continue
        wrap = _is_wrap(it)
        rows.append({
            "t": t, "kind": "Edition" if wrap else "Story",
            "text": it.get("title") or "",
            "href": (f'/articles/{esc(it.get("slug") or "")}.html'),
            "note": "" if wrap else (_story_league(it) or ""),
        })

    for lg in ((SB_DATA or {}).get("leagues") or []):
        for g in (lg.get("games") or []):
            if g.get("state") != "post":
                continue
            k = _utc_dt(g.get("start_utc") or "")
            if not k or k < cut:
                continue
            a, h = g.get("away") or {}, g.get("home") or {}
            sa, sh = _tk_score(a), _tk_score(h)
            if sa is None or sh is None:
                continue
            # The FINAL is the event, and the desk does not know the minute it ended.
            # The kickoff is what is on file, so that is what is stamped, and the line
            # says "Final" rather than pretending to a time nobody recorded.
            rows.append({
                "t": k, "kind": "Final",
                "text": (f'{a.get("abbr") or ""} {sa}, {h.get("abbr") or ""} {sh}'),
                "href": f'/games/{esc(str(g.get("id")))}.html',
                "note": g.get("league") or "",
            })

    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["t"], reverse=True):
        key = (r["kind"], r["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= WIRE_MAX:
            break
    return out


def _wire_filter(rows):
    """Forty-five of this weekend's fifty-one entries are final scores, so the desk's
    own five stories are buried under them and the page fails the question it exists to
    answer. The filter is the board's lens mechanism and not a second invention: the
    reader has met these buttons already, and a kind that is not on the page today gets
    no button, because a control that filters nothing is noise.
    """
    # The plural is written out, not built by adding an s: the first cut produced a
    # button reading "Storys" on the finished page.
    kinds = [(k, pl) for k, pl in (("Story", "Stories"), ("Final", "Finals"),
                                   ("Edition", "Editions"))
             if any(r["kind"] == k for r in rows)]
    if len(kinds) < 2:
        return ""
    bs = "".join(
        f'<button type="button" class="lens-b" data-wire="{k.lower()}" '
        f'aria-pressed="false">{esc(pl)}</button>' for k, pl in kinds)
    return ('<div class="lens wr-f" role="group" hidden '
            'aria-label="Filter the wire by what happened">'
            '<span class="lens-k">Show</span>'
            '<button type="button" class="lens-b on" data-wire="all" '
            'aria-pressed="true">All</button>' + bs + '</div>')


WIRE_JS = """<script>(function(){
  var g = document.querySelector('.wr-f');
  if (!g) return;
  g.hidden = false;
  function apply(v){
    document.querySelectorAll('.wr-r').forEach(function(r){
      r.hidden = (v !== 'all' && r.getAttribute('data-kind') !== v);
    });
    /* A day heading with nothing under it is a date that did not happen. */
    document.querySelectorAll('.wr-l').forEach(function(l){
      var any = l.querySelector('.wr-r:not([hidden])');
      l.hidden = !any;
      var h = l.previousElementSibling;
      if (h && h.classList.contains('wr-d')) h.hidden = !any;
    });
    g.querySelectorAll('.lens-b').forEach(function(b){
      var on = b.getAttribute('data-wire') === v;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  g.addEventListener('click', function(e){
    var b = e.target.closest('.lens-b');
    if (!b) return;
    e.preventDefault();
    apply(b.getAttribute('data-wire'));
  });
})();</script>"""


def render_wire(items, dateline, now=None):
    now = now or _build_now()
    rows = _wire_rows(items, now)
    if not rows:
        return None
    body, day = [], None
    for r in rows:
        et = r["t"].astimezone(_ET)
        d = et.strftime("%A %-d %B")
        if d != day:
            if day is not None:
                body.append("</ol>")
            body.append(f'<h2 class="wr-d">{esc(d)}</h2><ol class="wr-l">')
            day = d
        note = (f'<span class="wr-n">{esc(r["note"])}</span>' if r["note"] else "")
        body.append(
            f'<li class="wr-r" data-kind="{esc(r["kind"].lower())}">'
            f'<span class="wr-t">{esc(_et_clock(r["t"]))}</span>'
            f'<span class="wr-k wr-k-{esc(r["kind"].lower())}">{esc(r["kind"])}</span>'
            f'<a class="wr-x" href="{r["href"]}">{esc(r["text"])}</a>{note}</li>')
    body.append("</ol>")
    return shell(
        f"The Wire - {NAME}",
        "Everything this desk published and every game that finished, newest first, "
        "with the time it happened.",
        "News",
        '<section class="page wrap wr-page">'
        '<div class="wr-head"><h1>The Wire</h1>'
        f'<span class="wr-c">{len(rows)} entries, last {WIRE_HOURS} hours</span></div>'
        '<p class="bd-src">Nothing is written for this page. Every line is something '
        'that happened, stamped when it happened, linking to the thing itself.</p>'
        + _wire_filter(rows) + "".join(body) + '</section>' + WIRE_JS,
        dateline, path="/wire.html")


def render_standings_page(st, lg, dateline):
    name = lg["league"]
    body = f"""<main class="wrap"><section class="page">
  <h1 class="sr-only">{esc(name)} standings</h1>
  <div class="sec-head"><h2>{esc(name)} standings</h2><span class="bar"></span>
    {_st_stamp(st)}</div>
  {_st_league_block(lg)}
  {_st_nav(st, lg["key"])}
</section></main>"""
    return shell(f"{name} standings - {NAME}",
                 f"{name} standings by division and conference, from the league feed.",
                 "Scores", body, dateline, path=f'/standings/{lg["key"]}.html')


def _st_rank_rows(rk):
    rows = []
    for r in rk["rows"]:
        prev, cur = r.get("previous"), r.get("rank")
        move = ""
        try:
            d = int(prev) - int(cur)
            if int(prev) == 0:
                move = '<span class="st-new">new</span>'
            elif d > 0:
                move = f'<span class="st-up">&#9650; {d}</span>'
            elif d < 0:
                move = f'<span class="st-dn">&#9660; {abs(d)}</span>'
        except (TypeError, ValueError):
            move = ""
        fpv = r.get("first_place")
        fp = (f'<span class="st-fp">{esc(str(fpv))} first-place '
              f'vote{"" if fpv == 1 else "s"}</span>' if fpv else "")
        who = " ".join(x for x in (r.get("school"), r.get("mascot")) if x)
        rows.append(
            f'<tr><td class="st-pos">{esc(str(cur))}</td>'
            f'<td class="st-team"><span class="st-name">{esc(who)}</span>{fp}</td>'
            f'<td>{esc(r.get("record") or "")}</td><td class="st-mv">{move}</td></tr>')
    return "".join(rows)


def render_rankings_page(st, dateline):
    rk = st.get("rankings")
    if not rk:
        return None
    body = f"""<main class="wrap"><section class="page">
  <h1 class="sr-only">College football rankings</h1>
  <div class="sec-head"><h2>{esc(rk["poll"])}</h2><span class="bar"></span>
    <span class="sec-n">{esc(rk.get("week") or "")}</span></div>
  <div class="st-wrap"><table class="st-t st-rank">
    <thead><tr><th scope="col"><span class="sr-only">Rank</span></th>
      <th scope="col">Team</th><th scope="col">Record</th>
      <th scope="col">Since last poll</th></tr></thead>
    <tbody>{_st_rank_rows(rk)}</tbody></table></div>
  {_st_nav(st, "college-football")}
</section></main>"""
    return shell(f"College football rankings - {NAME}",
                 f"{rk['poll']}, {rk.get('week') or ''}: every ranked team with its "
                 f"record and its movement since the last poll.",
                 "Scores", body, dateline, path="/standings/college-football.html")


def _st_nav(st, here):
    """The other tables, from wherever the reader is. A league with nothing to show is
    not listed, so this row never offers an empty page."""
    links = [(lg["key"], lg["league"]) for lg in (st.get("leagues") or [])]
    if st.get("rankings"):
        links.append(("college-football", "College football"))
    if len(links) < 2:
        return ""
    return ('<nav class="st-nav" aria-label="Other standings">'
            + "".join(
                (f'<span class="st-nav-a on">{esc(lab)}</span>' if k == here
                 else f'<a class="st-nav-a" href="/standings/{esc(k)}.html">'
                      f'{esc(lab)}</a>')
                for k, lab in links)
            + '</nav>')


def standings_strip(st):
    """S-L1 on /scores: the tab that takes a reader to the tables. The page is the
    day's games; the standings are the season, and they get a door, not a copy."""
    links = [(lg["key"], lg["league"]) for lg in (st.get("leagues") or [])]
    if st.get("rankings"):
        links.append(("college-football", "College football"))
    if not links:
        return ""
    return (f'<section class="bd-mod st-strip">'
            f'<div class="sec-head"><h2>Standings</h2><span class="bar"></span>'
            f'{_st_stamp(st)}</div>'
            + '<nav class="st-nav" aria-label="Standings">'
            + "".join(f'<a class="st-nav-a" href="/standings/{esc(k)}.html">'
                      f'{esc(lab)}</a>' for k, lab in links)
            + '</nav></section>')


def render_scores_page(sb, board, dateline, wx=None):
    """/scores: every game, grouped by league, with a Yesterday, Today, Tomorrow strip.
    The strip links only days we actually hold data for."""
    if not sb or not sb.get("leagues"):
        return None
    ia = _ia_index(board)
    secs = []
    for L in sb["leagues"]:
        games = L["games"]
        if not games:
            continue
        games = sorted(games, key=_sb_sort_key_in_league)
        # SC-5: every game as a full Ticket card, three across, grouped by league with
        # a sticky league row. Live first, then upcoming, then final, which is the order
        # the reader opened the page for.
        n_live = sum(1 for g in games if g.get("state") == "in")
        count = f'{len(games)} game{"" if len(games) == 1 else "s"}'
        if n_live:
            count += f' \u00b7 {n_live} live'
        secs.append(
            f'<section class="bd-mod" id="{esc(L["league"].lower())}">'
            f'<div class="tk-lg"><span>{esc(L["league"])}</span><i></i>'
            f'<span class="tk-lg-n">{esc(count)}</span></div>'
            f'<div class="tk-g3">'
            + "".join(_tk_card(g, ia, wx=wx, desig=IA_DESIG, items=ALL_ITEMS)
                      for g in games) + '</div></section>')
    n_live = sum(1 for L in sb["leagues"] for g in L["games"] if g.get("state") == "in")
    _all = [g for L in sb["leagues"] for g in L["games"]]
    _today, _nxt_lab, _nxt_n = _sb_day_split(_all)
    if _today:
        count_line = (f"{len(_today)} game{'' if len(_today) == 1 else 's'} today"
                      f" · {n_live} live now")
    elif _nxt_n:
        count_line = (f"No games today · {_nxt_n} "
                      f"{'game' if _nxt_n == 1 else 'games'} {_nxt_lab}")
    else:
        count_line = "No games scheduled"
    # Revised G-2: an inner page carrying the same product opens with the SAME band at
    # reduced height, then continues light. That amends S-10's "run the page inside the
    # band"; the addendum wins, and it is the better read - a page-length dark surface
    # is the thing the audit took off /pulse.
    # A-14: the inner band carries the same photo, scrim, glass cards and ornament as
    # the homepage band, at about 60 percent of its height. It was a header strip with
    # nothing in it but the promise line - the photo showed and nothing else did.
    #
    # The promise line itself goes with it: copy item 5 took "Every score. No odds. No
    # noise." off the homepage band as an H1 and C-L2 bans a promise in a heading. It
    # survived here because item 5 named the homepage. The page's name is its heading.
    # Live first, then the next kickoffs in time order. The homepage band groups by
    # league because it carries the league tabs; this one has no tabs, and grouping by
    # league here put five Sunday NFL games under a header reading "6 games tomorrow"
    # while the five games that are actually tomorrow sat below the fold.
    _band_games = sorted(_all, key=_sb_sort_key)
    # Six cards, two rows of three. The homepage band carries a marquee and eight;
    # six without the marquee is the 60 percent A-14 asks for, and it is measured
    # from the content rather than pinned to a pixel height the slate would break.
    # A-14: this band is 60 percent of the homepage's. The Ticket rebuild added the
    # tabs and taller folded cards and pushed it to 84, which is not a reduced band,
    # it is a second homepage above the board the reader came for. Three folds, not six:
    # every game is a full card a few hundred pixels below.
    _band_cards = "".join(_tk_fold(g, ia, desig=IA_DESIG) for g in _band_games[:3])
    _orn = _sb_ornament(_all)
    band = f"""<section class="scoreband sb-hero sb-hero-inner{'' if _orn else ' no-orn'}" data-built="{_build_now().strftime('%Y-%m-%dT%H:%M:%SZ')}" data-built-et="{_et_clock(_build_now())}" aria-label="Scores">
  <div class="sb-bg" aria-hidden="true"></div>
  <div class="sb-scrim" aria-hidden="true"></div>
  <div class="wrap sb-inner">
    <div class="sb-promise">
      <div class="sb-promise-l">
        <h1 class="sb-claim">Scores</h1>
      </div>
      <span class="sb-countwrap">
        <span class="sb-count">{esc(count_line)}</span>
        <span class="sb-stamp">Updated {esc(_et(sb.get("fetched_at") or ""))}</span>
      </span>
    </div>
    {_tk_tabs(_all, active="all")}
    {lens_control()}{_week_link()}
    {pins_panel()}
    <div class="sb-grid sb-grid-inner">
      <div class="sb-cards">{_band_cards}</div>
    </div>
  </div>
  {_orn}
</section>
<div class="sb-fade" aria-hidden="true"></div>""" + mini_scoreboard(sb) + _team_pin_index(TEAM_DATA) + SB_LIVE_JS + MINI_SB_JS + TEAM_PIN_JS + LENS_JS
    body = band + f"""<main class="wrap"><section class="page">
    <div class="scoreband scoreband-page">{"".join(secs)}</div>
    {standings_strip(ST_DATA) if ST_DATA else ""}
</section></main>"""
    return shell(f"Scores - {NAME}",
                 "Every live score across the leagues this desk covers, with the "
                 "network carrying each game and the line as the book reported it.",
                 "Scores", body, dateline, path="/scores.html")


# ---- S-B2: the Sunday Inactives board -----------------------------------------
# The single most important fantasy surface, and it must be correct before it is
# pretty. Data comes from inactives.py, which polls and snapshots; see that module for
# why the board cannot simply query a feed at render time.
#
# THE STAMP IS OURS AND THE PAGE SAYS SO (ruling 1). Never "posted": the league posts
# about ninety minutes before kickoff and we do not observe that moment. We observe our
# own check, so the column is "first seen" and the page explains it once.
#
# NOTHING ASSUMES SEVEN (ruling 2). No feed carries a game-day roster or an active
# count, so no expected count is asserted. The board says "N inactive listed", never
# "the N inactives" and never "all", so a short list cannot read as a complete one.
# Detroit listed five on 13 Sep and the uncapped endpoint confirmed five.

FANTASY_LINE = ("Facts, not advice. Official reports only. We never tell you whom to "
                "start.")
# Copy item 42 removed this from the inactives page: it is a sentence about how the
# desk works, which C-L1 puts on How we work and nowhere else. Kept as the string the
# explainer page can use, unreferenced by any board.
INACTIVES_NOTE = ("Teams post about 90 minutes before kickoff.")


def _et(iso):
    """UTC stamp to ET clock, '6:45 PM ET' (G-7).

    Was a flat UTC-4 with the note 'Eastern is UTC-4 through the regular season'. It is
    not: DST ends November 1, and the season runs to February. Every ET time on the site
    would have read an hour late from November, the inactives posting time included. The
    zone does the arithmetic now, so the switch needs no edit."""
    dt = _utc_dt(iso)
    return dt.astimezone(_ET).strftime("%-I:%M %p ET") if dt else ""


def _league_teams(w2w=None):
    """Every team the schedule mentions across all weeks. Derived, not hand-kept: a
    hand-kept list of 32 goes stale the season a team moves or renames."""
    data = w2w if w2w is not None else W2W_DATA
    out = set()
    for w in (data or {}).get("weeks") or []:
        for g in (w.get("games") or []):
            for side in ("away", "home"):
                v = g.get(side)
                if v:
                    out.add(str(v))
    return out


def nfl_byes(week_no, w2w=None):
    """S-B12: the teams on bye in a week, from the schedule.

    A bye is not a field in the feed; it is the absence of a fixture. The league's 32
    teams minus the teams with a game that week IS the bye list, so it needs no new
    source. Returns [] when the schedule does not hold that week, rather than guessing.
    """
    data = w2w if w2w is not None else W2W_DATA
    weeks = (data or {}).get("weeks") or []
    wk = next((w for w in weeks if w.get("week") == week_no), None)
    if not wk:
        return []
    playing = set()
    for g in (wk.get("games") or []):
        for side in ("away", "home"):
            v = g.get(side)
            if v:
                playing.add(str(v))
    # Only claim a bye list when the week looks complete; a partial schedule would
    # name teams as idle that simply are not in the file yet.
    if len(playing) < 24:
        return []
    league = _league_teams(data)
    return sorted(league - playing) if len(league) >= 30 else []


def _fantasy_tonight_card(sb, board, desig):
    """S-3 / F-1 / N-6. The rail's fantasy card, and every figure on it belongs to the
    week the card names.

    The live card read "Week 2 · This week's designations · 33 out, 7 doubtful, 81
    questionable · as of Sep 14, 8:00 PM ET". Those are WEEK 1's final designations
    under a Week 2 heading, which is the stale board an owner sees. A figure renders
    under the week it belongs to and no other: before this week's first kickoff the
    card says what is coming and when the first report lands, and last week's numbers
    are one tap away under "Week 1, final".
    """
    import datetime as _dt
    wk, _ = nfl_week()
    rows = []
    first, first_game = None, None
    for w in ((W2W_DATA or {}).get("weeks") or []):
        if w.get("week") != wk:
            continue
        for g in (w.get("games") or []):
            k = _utc_dt(g.get("kickoff_utc") or "")
            if k and (first is None or k < first):
                first, first_game = k, g
    before_kickoff = bool(first and _build_now() < first)

    if before_kickoff:
        rows.append('<div class="bd-rec-row"><span class="bd-rec-t">First practice '
                    'report</span><span class="bd-src">Wednesday</span></div>')
        if first_game:
            rows.append(
                f'<div class="bd-rec-row"><span class="bd-rec-t">'
                f'{esc(first.astimezone(_ET).strftime("%A"))}: '
                f'{esc(first_game.get("away") or "")} at '
                f'{esc(first_game.get("home") or "")}</span>'
                f'<span class="bd-src">{esc(_et_clock(first))}</span></div>')
    else:
        ia = _ia_index(board)
        games = [g for L in ((sb or {}).get("leagues") or [])
                 for g in (L.get("games") or []) if g.get("league") == "NFL"]
        for g in games:
            if g.get("state") != "pre":
                continue
            dt = _utc_dt(g.get("start_utc") or "")
            if not dt:
                continue
            aw = (g.get("away") or {}).get("abbr") or ""
            hm = (g.get("home") or {}).get("abbr") or ""
            # N-7c: THE SAME TEST THE PAGE USES. This asked whether the team appears
            # anywhere in the board, which is true for all 31 all week, so the rail told
            # a Friday reader that Sunday's lists were posted. A list counts for a game
            # only inside that game's window.
            both = all(_ia_for_game(g, ia, side) for side in ("away", "home"))
            when = ("lists posted" if both
                    else f"lists post about {_et_clock(dt - _dt.timedelta(minutes=90))}")
            rows.append(f'<div class="bd-rec-row"><span class="bd-rec-t">{esc(aw)} at '
                        f'{esc(hm)}</span><span class="bd-src">{esc(when)}</span></div>')
            if len(rows) >= 2:
                break
        if desig and desig.get("groups"):
            bits = [f"{len(v)} {k.lower()}" for k, v in desig["groups"].items() if v]
            if bits:
                rows.append(f'<div class="bd-rec-row"><span class="bd-rec-t">'
                            f'Week {wk} designations</span>'
                            f'<span class="bd-src">{esc(" · ".join(bits))}</span></div>')

    byes = nfl_byes(wk) if wk else []
    if byes:
        rows.append(f'<div class="bd-rec-row"><span class="bd-rec-t">On bye</span>'
                    f'<span class="bd-src">{esc(", ".join(byes))}</span></div>')
    if not rows:
        return ""
    rows = rows[:2]     # N-4: two facts of the day, the rest on /fantasy
    stamp = "" if before_kickoff else ((board or {}).get("last_change") or "")
    tail = (fantasy_asof("Designations", stamp, "the league injury report") if stamp
            else f'<p class="fx-asof">Week {wk} · nothing posted for this week yet</p>')
    prev = (wk - 1) if isinstance(wk, int) and wk > 1 else wk
    return (f'<div class="bd-card sp-railcard sp-fantasy">'
            f'<div class="bd-cardtop"><span class="bd-eyebrow">'
            f'Fantasy{f", Week {wk}" if wk else ""}</span></div>'
            f'<div class="bd-rec-rows">{"".join(rows)}</div>{tail}'
            f'<a class="bd-more" href="/fantasy/inactives.html">Week {prev}, final</a>'
            f'</div>')


def _inactives_pending(games, posted_ids):
    """Teams playing today whose list we have not seen yet, with the time the league is
    expected to post: kickoff minus ninety minutes. Never a guess about who.

    MATCHED ON TEAM ID, not name. The first cut compared the board's display names
    ("Atlanta Falcons") against the schedule's abbreviations ("ATL"), matched nothing,
    and listed all thirty-two teams as pending directly underneath the nineteen whose
    lists were already on the page.

    Only games that have not kicked off. A live or finished game's list is either
    already seen or never coming, and either way "expected 11:30 AM ET" is wrong on a
    page rendered at 2pm."""
    import datetime as _dt
    out = []
    for g in games or []:
        if (g.get("state") or "") != "pre":
            continue
        for side in ("home", "away"):
            nm = g.get(side) or ""
            tid = g.get(f"{side}_id") or ""
            if not nm or tid in posted_ids or nm in posted_ids:
                continue
            k = g.get("kickoff_utc") or ""
            exp = ""
            try:
                t = _dt.datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(
                    tzinfo=_dt.timezone.utc)
                exp = _et((t - _dt.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            except Exception:
                pass
            out.append({"team": nm, "expected": exp, "kick": g.get("kickoff_et") or ""})
    out.sort(key=lambda x: (x["expected"] or "z", x["team"]))
    return out


def _nfl_color(team_id):
    """A team's colour from the scoreboard feed, by id. "" when the feed has not been
    read this build or the id is not in it."""
    if not team_id or not SB_DATA:
        return ""
    for L in (SB_DATA.get("leagues") or []):
        if L.get("league") != "NFL":
            continue
        for g in (L.get("games") or []):
            for side in ("away", "home"):
                t = g.get(side) or {}
                if str(t.get("id")) == str(team_id):
                    return t.get("color") or ""
    return ""


def _wk_suffix():
    """F-1: nothing renders under "today" or "this week" without the week beside it."""
    wk, _ = nfl_week()
    return f", Week {wk}" if wk else ""


def _ia_hub_count(board):
    """The phrase the hub and the rail both use, from one model."""
    lists, players = _ia_week_totals(board, W2W_DATA)
    if not lists:
        return "no lists posted yet"
    return (f"{lists} list{'' if lists == 1 else 's'}, "
            f"{players} player{'' if players == 1 else 's'}")


def _ia_week_totals(board, w2w):
    """A-5: this week's lists and players, the number N-7c put on the week page.

    The hub said "Week 2 inactives, 319 players", which is every sighting in the
    eight-day board under a heading naming one week. Week 2 had two lists and
    fourteen players. One model, one number, wherever the week is named.
    """
    if not board or not w2w:
        return 0, 0
    _wkno, _ = _ia_week()
    wk = next((w for w in (w2w.get("weeks") or []) if w.get("week") == _wkno), None)
    if not wk:
        return 0, 0
    by_id = {str(t["id"]): t for t in (board.get("teams") or []) if t.get("id")}
    lists = players = 0
    for g in (wk.get("games") or []):
        for k in ("away_id", "home_id"):
            t = by_id.get(str(g.get(k)))
            got = _ia_team_for_game(t, g) if t else None
            if got:
                lists += 1
                players += got["count"]
    return lists, players


def _dg_list_state(team, board, w2w):
    """A-5: has THIS team's list posted for its next fixture?

    The page printed "Out · ACTIVE" on the same row all Sunday morning, because the
    test was whether the team appeared anywhere in the eight-day board, which is true
    for all 31 teams all week. A fantasy owner reading "Out · Active" at 9 AM makes the
    wrong decision, which is the whole cost of a shallow key on this desk.

    Returns (posted, when): posted is the team's list for its next game if it is up,
    otherwise None, and when is the time it is expected.
    """
    if not board or not w2w:
        return None, ""
    _wkno, _ = _ia_week()
    wk = next((w for w in (w2w.get("weeks") or []) if w.get("week") == _wkno), None)
    tm = next((t for t in (board.get("teams") or []) if t.get("team") == team), None)
    if not wk or not tm:
        return None, ""
    for g in (wk.get("games") or []):
        if str(g.get("away_id")) != str(tm.get("id")) and \
           str(g.get("home_id")) != str(tm.get("id")):
            continue
        got = _ia_team_for_game(tm, g)
        return got, _ia_expected(g)
    return None, ""


def _dg_ruling(p, board, w2w, ia_names):
    """The flag, only once the list it depends on exists."""
    posted, when = _dg_list_state(p.get("team"), board, w2w)
    if posted is None:
        # Before the list, the honest line is when it comes, not a guess at the answer.
        return (f'<span class="bd-src dg-wait">{esc(when)}</span>' if when else "")
    if (p.get("team"), p.get("name")) in ia_names:
        return '<span class="bd-badge dat">inactive</span>'
    return '<span class="bd-badge ok">active</span>'


def _ia_week():
    """The week the held lists belong to, and whether it is final.

    ONE RULE, TWO USERS. The heading and the game grouping must name the same week or
    the page groups Week 1's lists under Week 2's fixtures, which is what the first cut
    of N-7 did: a Week 1, final heading over Thursday-of-Week-2 kickoffs.
    """
    wk, _last = nfl_week()
    first = None
    for w in ((W2W_DATA or {}).get("weeks") or []):
        if w.get("week") != wk:
            continue
        ks = [_utc_dt(g.get("kickoff_utc") or "") for g in (w.get("games") or [])]
        ks = [k for k in ks if k]
        first = min(ks) if ks else None
    if first and _build_now() < first:
        prev = (wk - 1) if isinstance(wk, int) and wk > 1 else None
        return prev, True
    return wk, False


def _ia_heading(board):
    """N-7: the board names the WEEK its lists belong to, not the day the file carries.

    These lists are captured at games. Until the current week's first kickoff everything
    held is the PREVIOUS week's and it is final, so the heading says that - rather than
    "Today's inactives" over Sunday's lists, or the merged week file's own day, which on
    a Tuesday evening is already tomorrow in UTC."""
    wk, final = _ia_week()
    if final:
        return f"Week {wk}, final" if wk else "Inactives, final"
    return f"Week {wk} inactives" if wk else "Inactives"


def _ia_rows(players, stamp):
    return "".join(
        f'<div class="ia-row"><span class="ia-name">{esc(p.get("name") or "")}</span>'
        f'<span class="ia-pos">{esc(p.get("pos") or "")}</span>'
        f'<span class="bd-src">{esc(p.get("reason") or "")}</span>'
        + (f'<span class="ia-upd">updated {esc(_et(p.get("first_seen") or ""))}</span>'
           if p.get("first_seen") and p["first_seen"] != stamp else "")
        + '</div>'
        for p in players)


def _inactives_team_card(t):
    # N-7b: a team's card shows each list under the day it belongs to. A player inactive
    # on the 13th and again on the 17th is two listings and appears under both, which is
    # what the board holds now; with one list there is no heading and the card is the
    # card it always was.
    by_day = t.get("by_day") or []
    if len(by_day) > 1:
        rows = "".join(
            f'<div class="ia-day"><span class="ia-day-h">'
            f'{esc(fmt_short_date(d["day"]))}</span>'
            f'<span class="ia-day-n">{d["count"]} inactive</span></div>'
            + _ia_rows(d["players"], d.get("first_seen"))
            for d in by_day)
    else:
        rows = _ia_rows(t["players"], t["first_seen"])
    flag = ('<span class="bd-badge dat">list may be incomplete</span>'
            if t.get("incomplete") else "")
    # S-19: the board's own feed carries no colour, so it comes from the scoreboard,
    # matched on team id. No match, no bar: a neutral rule rather than a wrong colour.
    col = _nfl_color(t.get("id"))
    bar = (f'<span class="tc" style="background:{esc(col)}"></span>' if col
           else '<span class="tc tc-none"></span>')
    return (f'<div class="bd-card ia-team" data-team="{esc(t["team"])}">'
            f'<div class="bd-cardtop">{bar}<span class="bd-eyebrow">{esc(t["team"])}</span>'
            + (f'<span class="bd-stamp">{len(by_day)} lists, {t["count"]} '
               f'listings</span>' if len(by_day) > 1 else
               f'<span class="bd-stamp">{t["count"]} inactive</span>')
            + f'<span class="bd-stamp">posted {esc(_et(t["first_seen"]))}</span>'
            f'{flag}</div>'
            f'<div class="ia-rows">{rows}</div></div>')


def _ia_tonight_block():
    """S-19. On a day whose lists are not the board's day - a Monday showing Sunday -
    tonight's game still matters, so it gets its own block with the time its lists are
    expected. Nothing scheduled, no block."""
    if not SB_DATA:
        return ""
    import datetime as _dt
    today = _build_now().astimezone(_ET).date()
    for L in (SB_DATA.get("leagues") or []):
        if L.get("league") != "NFL":
            continue
        for g in sorted((L.get("games") or []), key=lambda x: x.get("start_utc") or ""):
            if g.get("state") != "pre":
                continue
            d = _utc_dt(g.get("start_utc") or "")
            if not d or d.astimezone(_ET).date() != today:
                continue
            aw = (g.get("away") or {}).get("abbr") or ""
            hm = (g.get("home") or {}).get("abbr") or ""
            when = _et_clock(d - _dt.timedelta(minutes=90))
            return (f'<div class="bd-card ia-tonight"><span class="bd-eyebrow">Tonight'
                    f'</span><span class="ia-tonight-g">{esc(aw)} at {esc(hm)}</span>'
                    f'<span class="bd-src">lists post about {esc(when)}</span></div>')
    return ""


def _ia_week_switch(board, games):
    """A link to the earlier lists, only when there are some."""
    if not _ia_earlier(board, games):
        return ""
    _wkno, _ = _ia_week()
    return ('<nav class="st-nav" aria-label="Weeks">'
            f'<span class="st-nav-a on">Week {_wkno}</span>'
            '<a class="st-nav-a" href="/fantasy/inactives/week-earlier.html">'
            'Earlier</a></nav>')


def _ia_week_summary(board, games):
    """N-7c: the header counts THIS WEEK'S LISTS, and says when the rest post.

    It read "207 players, 31 teams", which is every sighting the board holds across the
    whole eight-day window, under a heading that says Week 2. Week 2 had two lists and
    fourteen players.
    """
    by_id = {str(t["id"]): t for t in board.get("teams") or [] if t.get("id")}
    lists, players, waiting = 0, 0, []
    for g in games or []:
        for k in ("away_id", "home_id"):
            t = by_id.get(str(g.get(k)))
            got = _ia_team_for_game(t, g) if t else None
            if got:
                lists += 1
                players += got["count"]
            else:
                waiting.append(g)
    bits = [f"{lists} list{'' if lists == 1 else 's'} posted, "
            f"{players} player{'' if players == 1 else 's'}"] if lists else []
    # D-2, found at checkpoint 4: at 9:20 PM on Sunday this line still read "Sunday's
    # lists post about 6:50 PM ET", beside its own count of 29 lists already posted. It
    # forecast from the earliest game still without a list, whether or not that game had
    # long since kicked off, so the forecast outlived the thing it forecast. Checkpoint 3
    # found the same shape on the 4:05 and 4:25 cards.
    #
    # A forecast is only a forecast while it is in the future. Games still waiting are
    # split by that line and nothing else: the ones whose posting time has not arrived
    # get the forecast, and the ones whose time has passed are reported as what the desk
    # actually knows, which is that it is holding no list for them. "Not posted" would be
    # a claim about the team; "no list" is a claim about this desk, and only the second
    # one is ours to make.
    if waiting:
        import datetime as _d
        _now = _build_now()
        ahead, passed = [], []
        for g in waiting:
            k = _utc_dt(g.get("kickoff_utc") or "")
            (ahead if (k and (k - _d.timedelta(minutes=90)) > _now) else passed).append(g)
        if ahead:
            nxt = min(ahead, key=lambda g: g.get("kickoff_utc") or "")
            k = _utc_dt(nxt.get("kickoff_utc") or "")
            at = k - _d.timedelta(minutes=90)
            day = k.astimezone(_ET).strftime("%A")
            bits.append(f"{day}'s lists post about {_et_clock(at)}")
        if passed:
            # COUNTED IN TEAMS, because that is what this list holds: a game appends once
            # for each side still missing, and a game where one team has posted and the
            # other has not is exactly the case a count of games would hide.
            n = len(passed)
            bits.append(f"no list yet for {n} team{'' if n == 1 else 's'}")
    if not bits:
        bits = ["no lists yet"]
    return "; ".join(bits)


def _ia_expected(g):
    """When this game's list is expected: about ninety minutes before kickoff, on the
    game's own day. The same phrasing the game cards use."""
    k = _utc_dt(g.get("kickoff_utc") or g.get("start_utc") or "")
    if not k:
        return "posting time not set"
    import datetime as _d
    at = (k - _d.timedelta(minutes=90)).astimezone(_ET)
    far = (k - _build_now()).total_seconds() > 24 * 3600
    return (f'posts about {at.strftime("%a")} {_et_clock(k - _d.timedelta(minutes=90))}'
            if far else f'posts about {_et_clock(k - _d.timedelta(minutes=90))}')


def _ia_window(g):
    """H-1's window for a scheduled game: from three hours before kickoff to the end of
    that Eastern day. The same window the game page uses, so the two pages cannot
    disagree about which list belongs to which fixture."""
    import datetime as _d
    k = _utc_dt(g.get("kickoff_utc") or g.get("start_utc") or "")
    if not k:
        return None, None
    end = k.astimezone(_ET).replace(hour=23, minute=59, second=59) \
           .astimezone(_d.timezone.utc)
    return k - _d.timedelta(hours=3), end


def _ia_team_for_game(t, g):
    """N-7c: A LISTING BELONGS TO A GAME. The board holds every sighting of the week
    (N-7b), and a team's card under a fixture must hold that fixture's list and no
    other. On Friday morning Detroit's section under DET at BUF carried its 13
    September list as well, which is Week 1's game sitting under Week 2's.

    Returns None when this team has no list for this game, so the team goes to the
    pending column with the time its list is expected rather than showing an old one.
    """
    opens, end = _ia_window(g)
    if not opens:
        return None
    ps = [p for p in (t.get("players") or [])
          if p.get("first_seen") and opens <= _utc_dt(p["first_seen"]) <= end]
    if not ps:
        return None
    firsts = [p["first_seen"] for p in ps]
    return {**t, "players": ps, "count": len(ps),
            "first_seen": max(firsts), "first_sighting": min(firsts),
            # one list, so the card renders without day headings
            "by_day": [{"day": ps[0].get("day") or "", "players": ps,
                        "count": len(ps), "first_seen": min(firsts)}]}


IA_RUNTIME_H = 4        # an NFL game is ~3h10m; past that a kickoff is history
# Most severe first, which is also most useful first: a player ruled out is a lineup
# change, a questionable one is a thing to watch.
IA_SEV = ("Out", "Doubtful", "Questionable")


def _ia_full_name(abbr):
    """The team's full name from its abbreviation, which is the key the designations
    report is written in. The schedules file carries both, so the join is a lookup
    rather than a guess; an abbreviation it does not carry returns "" and the card
    simply shows no report."""
    t = ((TEAM_DATA or {}).get("teams") or {}).get((abbr or "").strip().upper())
    return (t or {}).get("name") or ""


def _ia_desig_rows(abbr, n=6):
    """(rows html, counts html) for a team's official injury report.

    N-9: WHAT THE PAGE HOLDS BEFORE THE LIST POSTS. An inactive list posts about 90
    minutes before kickoff, so for most of the week every fixture on this page was two
    cards saying "posts about 1:00 PM ET" and nothing else, on the surface a fantasy
    owner opens precisely to decide a lineup. The official designations are known days
    earlier and are the best answer available until the list lands, so they fill the
    card and the list replaces them when it posts.

    Ruled out first. The desk's own report is the source, so a player it does not carry
    is not invented, and a team with an empty report shows the stamp alone.
    """
    rows = _team_desig(_ia_full_name(abbr))
    if not rows:
        return "", ""
    counts = {s: 0 for s in IA_SEV}
    for p in rows:
        s = (p.get("status") or "").strip().title()
        if s in counts:
            counts[s] += 1
    cn = " · ".join(f"{v} {k.lower()}" for k, v in counts.items() if v)
    shown = rows[:n]
    body = "".join(
        f'<div class="gp-dz-row">'
        f'<span class="gp-dz-st s-{esc((p.get("status") or "x").lower()[:1])}">'
        f'{esc((p.get("status") or "?")[:1].upper())}</span>'
        f'<span class="gp-dz-n">{esc(p.get("name") or "")}</span>'
        f'<span class="gp-dz-p">{esc(p.get("pos") or "")}</span>'
        f'<span class="gp-dz-i">{esc(_injury_case(p.get("detail") or ""))}</span>'
        f'</div>' for p in shown)
    if len(rows) > len(shown):
        body += (f'<div class="ia-dz-more">and {len(rows) - len(shown)} more on '
                 f'<a href="/fantasy/injuries.html">the injury report</a></div>')
    return body, cn


def _ia_phase(g, now=None):
    """(phase, when) for a fixture: 0 in progress, 1 still to come, 2 finished.

    N-8: AN INACTIVE LIST IS ONLY NEWS BEFORE KICKOFF. The page ordered fixtures the way
    the schedule file happens to list them, which is chronological, so on a Friday the
    reader opened to Thursday night's final and had to scroll past it to reach the lists
    that still decide a lineup. Finished games keep their section and go to the bottom.

    The feed's own state leads, because it knows about a delay the clock does not. When
    the file carries no state the kickoff decides, with one game's runtime allowed.
    """
    now = now or _build_now()
    k = _utc_dt(g.get("kickoff_utc") or "")
    st = (g.get("state") or "").strip()
    if st == "post" or g.get("completed"):
        ph = 2
    elif st == "in":
        ph = 0
    elif not k:
        ph = 1                                   # unplaceable: treat as ahead, never buried
    elif k > now:
        ph = 1
    else:
        ph = 0 if (now - k).total_seconds() < IA_RUNTIME_H * 3600 else 2
    return ph, k


def _ia_game_key(g, now=None):
    """Sort fixtures for a reader standing in the present: what is on now, then what is
    next, then what is over. Finished games run newest first, so the game that just
    ended sits above last Thursday's."""
    ph, k = _ia_phase(g, now)
    ts = k.timestamp() if k else 0.0
    return (ph, -ts if ph == 2 else ts)


def _ia_by_game(board, games):
    """N-7: the week's lists grouped by the game they belong to, with its kickoff.

    A flat grid of 31 team cards is a list of teams; a reader looking at inactives is
    looking at a game. Teams are matched to a game on ID, never on name: the schedule
    writes abbreviations and the board writes display names, and a shallow key is not
    an identity.

    A team the schedule does not place (a bye, or a game the file does not carry) is
    not dropped. It goes under its own heading at the end, because a list the desk
    holds and does not show is worse than an ugly grouping.
    """
    by_id = {}
    for t in board["teams"]:
        if t.get("id"):
            by_id[str(t["id"])] = t
    used, groups = set(), []
    _cur_win = object()     # a sentinel: the first fixture always writes its heading
    # N-8: kickoff order, present first. Windows come out grouped because the fixtures
    # inside one share a kickoff, so sorting the games sorts the windows with them.
    for g in sorted(games, key=_ia_game_key):
        # N-7c: this fixture's list, not the team's week. A side with no list for this
        # game shows when its list is expected, in the same section, rather than being
        # given an older one or dropped out of the page.
        cards = []
        for _k in ("away_id", "home_id"):
            _t = by_id.get(str(g.get(_k)))
            _got = _ia_team_for_game(_t, g) if _t else None
            if _got:
                used.add(str(_got["id"]))
                cards.append(_inactives_team_card(_got))
            else:
                _abbr = g.get("away") if _k == "away_id" else g.get("home")
                # N-9: the list has not posted, so the card carries the official
                # designations until it does rather than standing empty.
                _dz, _cn = _ia_desig_rows(_abbr)
                _col = _nfl_color(g.get(_k))
                _bar = (f'<span class="tc" style="background:{esc(_col)}"></span>'
                        if _col else '<span class="tc tc-none"></span>')
                cards.append(
                    f'<div class="bd-card ia-team ia-await">'
                    f'<div class="bd-cardtop">{_bar}'
                    f'<span class="bd-eyebrow">{esc(_abbr or "")}</span>'
                    + (f'<span class="bd-stamp">{esc(_cn)}</span>' if _cn else "")
                    + f'<span class="bd-stamp">{esc(_ia_expected(g))}</span>'
                    f'</div>'
                    + (f'<div class="gp-dz-rows ia-dz">{_dz}</div>' if _dz else "")
                    + '</div>')
        head = (f'{esc(g.get("away") or "")} at {esc(g.get("home") or "")}')
        when = " \u00b7 ".join(x for x in (g.get("day_et"), g.get("kickoff_et")) if x)
        _ph, _ = _ia_phase(g)
        _win = g.get("window") or ""
        if _win != _cur_win:
            _cur_win = _win
            groups.append(
                f'<h2 class="ia-win{" past" if _ph == 2 else ""}">{esc(_win)}'
                + ('<span class="ia-win-n">played</span>' if _ph == 2 else "")
                + '</h2>')
        # N-8: EVERY SECTION FOLDS, AND A FINISHED ONE ARRIVES FOLDED. <details> because
        # the open/shut state belongs to the element, not to a script: with JS off the
        # page is still readable and every section still opens.
        _open = "" if _ph == 2 else " open"
        _mark = ('<span class="ia-st done">Final</span>' if _ph == 2
                 else '<span class="ia-st live">Live</span>' if _ph == 0 else "")
        groups.append(
            f'<details class="ia-game" data-phase="{_ph}" '
            f'data-window="{esc(g.get("window") or "")}"{_open}>'
            f'<summary class="ia-gh">'
            f'<span class="ia-gh-t">{head}</span>{_mark}'
            f'<span class="ia-kick">{esc(when)}</span>'
            # N-9: wind and cold decide a fantasy lineup as surely as a designation
            # does, and the desk already takes the reading for the schedule page.
            + (_w2w_wx(g, WX_DATA) if _ph != 2 else "")
            + '</summary>'
            f'<div class="ia-grid">' + "".join(cards) + '</div></details>')
    # THE WEEK'S PAGE IS THE WEEK'S GAMES. Teams whose lists belong to an earlier week
    # are not shown here at all: they live under their own week. A flat remainder of 29
    # teams carrying Week 1's lists under a Week 2 heading is the defect N-7c names.
    return "".join(groups)


def _ia_earlier(board, games):
    """Every sighting that does not belong to one of this week's fixtures. The schedule
    file carries the weeks AHEAD, so an earlier week's games cannot be paired against
    it; those lists are shown by team under the day they went up, which is what the
    board holds and all it can honestly say."""
    windows = [w for w in (_ia_window(g) for g in games or []) if w[0]]
    out = []
    for t in board.get("teams") or []:
        keep = []
        for pl in (t.get("players") or []):
            fs = _utc_dt(pl.get("first_seen") or "")
            if not fs:
                continue
            if any(a <= fs <= b for a, b in windows):
                continue
            keep.append(pl)
        if not keep:
            continue
        firsts = [p["first_seen"] for p in keep]
        days = {}
        for pl in keep:
            days.setdefault(pl.get("day") or "", []).append(pl)
        out.append({**t, "players": keep, "count": len(keep),
                    "first_seen": max(firsts), "first_sighting": min(firsts),
                    "by_day": [{"day": d, "players": v, "count": len(v),
                                "first_seen": min(x["first_seen"] for x in v)}
                               for d, v in sorted(days.items(), reverse=True)]})
    out.sort(key=lambda t: (t["first_seen"] or "", t["team"]), reverse=True)
    return out


def render_inactives_earlier(board, w2w, dateline):
    """N-7c: the lists from before this week, on their own page. The CURRENT week keeps
    /fantasy/inactives and that URL never changes; this is where the earlier ones live
    so they are neither lost nor sitting under the wrong week's heading."""
    if not board or not board.get("teams"):
        return None
    _wks = (w2w or {}).get("weeks") or []
    _wkno, _ = _ia_week()
    _week = next((w for w in _wks if w.get("week") == _wkno), None)
    teams = _ia_earlier(board, (_week or {}).get("games") or [])
    if not teams:
        return None
    n = sum(t["count"] for t in teams)
    body = f"""<main class="wrap"><section class="page">
  <h1 class="lx-h1" style="margin-bottom:6px">Earlier inactives</h1>
  <p class="lx-dek">{n} listing{"" if n == 1 else "s"} across
     {len(teams)} team{"" if len(teams) == 1 else "s"}, before Week {_wkno}</p>
  <nav class="st-nav" aria-label="Weeks">
    <a class="st-nav-a" href="/fantasy/inactives.html">Week {_wkno}</a>
    <span class="st-nav-a on">Earlier</span></nav>
  <div class="ia-grid" style="margin-top:18px">
    {"".join(_inactives_team_card(t) for t in teams)}
  </div>
</section></main>"""
    return shell(f"Earlier NFL inactives - {NAME}",
                 "The inactive lists from before this week, by team, each under the day "
                 "it went up.",
                 "Fantasy", body, dateline, path="/fantasy/inactives/week-earlier.html")


IA_FOLD_JS = """<script>(function(){
  /* N-8/N-9: on a phone the page opens to the next fixture alone and the rest wait
     behind their headings. Once each card carries an injury report the whole week
     expanded is fifteen phone screens, and the next window alone is eight; one fixture
     is four, and it is the one a reader at kickoff is looking at. It stays open rather
     than folding everything so the first thing on the page is an answer, and so the
     fold is visibly a fold. Desktop keeps every upcoming fixture open: the two-column
     grid has the room and folding there would cost a reader clicks for nothing. A
     browser with no matchMedia, or JS off, gets the markup's own state, which is
     readable either way. */
  try{
    if(!window.matchMedia || !matchMedia('(max-width:700px)').matches) return;
    var seen=false;
    document.querySelectorAll('details.ia-game').forEach(function(d){
      if(d.getAttribute('data-phase')==='2'){ d.open=false; return; }
      d.open=!seen; seen=true;
    });
  }catch(e){}
})();</script>"""


def render_inactives(board, w2w, dateline):
    """/fantasy/inactives. Returns None when nothing is held, so the page and its nav
    entry withdraw together rather than showing an empty table."""
    if not board or not board.get("teams"):
        return None
    posted = {t["team"] for t in board["teams"]}
    # N-7: the whole NFL week, and THE WEEK THESE LISTS BELONG TO. weeks[:1] was the
    # same defect copy item 30 found on /where-to-watch, and taking the current week
    # instead is the opposite error: before Week 2 kicks off everything held is Week 1,
    # and grouping it under Week 2's fixtures puts Sunday's lists under Thursday night.
    _wks = (w2w or {}).get("weeks") or []
    _wkno, _ = _ia_week()
    _week = next((w for w in _wks if w.get("week") == _wkno), None)
    games = (_week or {}).get("games") or []
    # S-B12's who-plays-when strip is about the week AHEAD, not the week these final
    # lists came from: a reader on this page before Thursday wants to know when the
    # next lists post. It names its own week so the two cannot be read as one.
    _ahead_no, _ = nfl_week()
    _ahead = next((w for w in _wks if w.get("week") == _ahead_no), None)
    _ahead_games = (_ahead or {}).get("games") or []
    # Match on the team names the schedule uses, which are abbreviations; the board
    # holds full display names. Only teams we can match are shown as pending, so a
    # name we cannot resolve is left out rather than asserted as unposted.
    pending = _inactives_pending(
        games, {a for t in board["teams"] for a in (t["team"], str(t.get("id") or ""))})
    cards = _ia_by_game(board, games)
    pend = ""
    if pending:
        pend = ('<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                '<span class="bd-eyebrow">Not seen yet</span>'
                '<h2 class="bd-h2" style="font-size:20px">Lists we have not seen</h2>'
                '</div></div><div class="ia-pending">'
                + "".join(f'<div class="ia-pend"><span class="ia-name">{esc(p["team"])}</span>'
                          f'<span class="bd-src">expected {esc(p["expected"])}</span></div>'
                          for p in pending)
                + '</div></section>')
    body = f"""<main class="wrap"><section class="page">
    <h1 class="lx-h1" style="margin-bottom:6px">{esc(_ia_heading(board))}</h1>
  <p class="lx-dek">{esc(_ia_week_summary(board, games))}</p>
  {_ia_week_switch(board, games)}
  {fantasy_asof("First seen", (board or {}).get("last_change") or
                (board or {}).get("last_poll") or "", "the league injury feed")}
  {_ia_tonight_block()}
  {_sb12_who_plays_when(_ahead_games)}
  {cards}
  {pend}
</section></main>""" + _team_pin_index(TEAM_DATA) + TEAM_PIN_JS + IA_FOLD_JS
    return shell(f"Today's NFL inactives - {NAME}",
                 "Every team's inactive list for today's games, with the time our check "
                 "first saw each one. Facts, not advice.",
                 "Fantasy", body, dateline, path="/fantasy/inactives.html",
                 og_image=f"{ORIGIN}/share/inactives.png")


# ---- S-B3, S-B7, S-B8: live points, the hub, and game pages --------------------
# Points are computed from the official box score at each refresh and carry the format
# toggle client-side. The toggle is remembered on the device in localStorage and
# nothing else: no account, no cookie sent anywhere, nothing logged.

# item 38: "Computed from the official box score at each refresh" is process (C-L3).
# The caveat a reader needs is what remains.
FANTASY_FOOT = "Your league's scoring may differ."
TWO_PT_NOTE = "Two-point conversions are not included live."

FORMAT_JS = """<script>(function(){
  var KEY='gcms_fmt', fmts=['ppr','half','standard'];
  function get(){try{var v=localStorage.getItem(KEY);return fmts.indexOf(v)>-1?v:'ppr'}
    catch(e){return 'ppr'}}
  function apply(f){
    document.querySelectorAll('[data-fmt]').forEach(function(el){
      el.hidden = el.getAttribute('data-fmt')!==f;});
    document.querySelectorAll('.fmt-btn').forEach(function(b){
      b.setAttribute('aria-pressed', String(b.getAttribute('data-set')===f));});
    document.querySelectorAll('[data-pts]').forEach(function(el){
      var v=el.getAttribute('data-'+f); if(v!==null) el.textContent=v;});
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest('.fmt-btn'); if(!b) return;
    var f=b.getAttribute('data-set');
    try{localStorage.setItem(KEY,f)}catch(err){}
    apply(f);
  });
  apply(get());
})();</script>"""


def _fmt_toggle():
    return ('<div class="fmt" role="group" aria-label="Scoring format">'
            + "".join(f'<button type="button" class="fmt-btn" data-set="{k}" '
                      f'aria-pressed="{"true" if k == "ppr" else "false"}">{lab}</button>'
                      for k, lab in (("ppr", "PPR"), ("half", "Half"),
                                     ("standard", "Standard")))
            + '</div>')


def _leader_rows(rows, rank_from=1):
    out = []
    for n, p in enumerate(rows, start=rank_from):
        out.append(
            f'<div class="fp-row"><span class="fp-n">{n}</span>'
            f'<span class="fp-name">{esc(p.get("name") or "")}</span>'
            f'<span class="ia-pos">{esc(p.get("pos") or "")}</span>'
            f'<span class="bd-src">{esc(p.get("team") or "")}</span>'
            f'<span class="bd-src fp-line">{esc("; ".join(p.get("line") or []))}</span>'
            f'<span class="fp-pts" data-pts data-ppr="{p.get("ppr", 0)}" '
            f'data-half="{p.get("half", 0)}" data-standard="{p.get("standard", 0)}">'
            f'{p.get("ppr", 0)}</span></div>')
    return "".join(out)


def _leaders_module(points, title, n=8, expand=True, anchor=""):
    if not points:
        return ""
    import fantasy_points as _fp
    top = _fp.leaders(points, n)
    if not top:
        return ""
    rest = [p for p in sorted(points.values(), key=lambda x: -x.get("ppr", 0))][n:]
    more = ""
    if expand and rest:
        more = (f'<details class="fp-more"><summary>Every player in this game '
                f'({len(rest)} more)</summary><div class="fp-rows">'
                f'{_leader_rows(rest, n + 1)}</div></details>')
    return (f'<section class="bd-mod"{f" id={anchor}" if anchor else ""}>'
            f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(title)}</span></div>{_fmt_toggle()}</div>'
            f'<div class="fp-rows">{_leader_rows(top)}</div>{more}'
            f'<p class="bd-src">{esc(FANTASY_FOOT)} {esc(TWO_PT_NOTE)}</p></section>')


def _game_wx_block(g, wx):
    w = _wx_for(g, wx)
    if not w:
        return ""
    if w.get("indoors"):
        return ('<div class="bd-card" style="padding:14px 16px"><span class="bd-label">'
                # H-11: the game's own name, corrected, not the weather file's, which
                # takes it from venues.json and was still saying Reliant.
                'Kickoff weather</span><p class="bd-read">Indoors at '
                f'{esc(_venue_name(g) or w.get("venue") or "the venue")}.</p></div>')
    bits = []
    if w.get("temp_f") is not None:
        bits.append(f'{w["temp_f"]}F')
    if w.get("wind_mph") is not None:
        bits.append(f'wind {w["wind_mph"]} mph {esc(w.get("wind_dir") or "")}'.strip())
    if w.get("precip_pct") is not None:
        bits.append(f'{w["precip_pct"]}% chance of precipitation')
    if w.get("summary"):
        bits.append(str(w["summary"]).lower())
    return ('<div class="bd-card" style="padding:14px 16px"><span class="bd-label">'
            'Kickoff weather</span>'
            f'<p class="bd-read">{esc(", ".join(bits))}.</p>'
            '<p class="bd-src">National Weather Service, via GoCheckMyWeather.</p></div>')


def _gp_designations(g, desig):
    """UX-4 (S-4): WHO, not how many.

    The page showed "DET 4 questionable \u00b7 BUF 1 out" to a reader who opened it to
    find out which players. The report carries the name, the position and the injury
    for every listed player, and the page has been throwing that away to print a count.

    Grouped by team, ordered Out, Doubtful, Questionable, because that is the order a
    reader cares about. A status the feed carries that this desk does not name renders
    as the feed's own word rather than being dropped.
    """
    if (g.get("league") or "") != "NFL":
        return ""
    idx = {}
    for status, players in ((desig or {}).get("groups") or {}).items():
        for pl in players or []:
            nick = (pl.get("team") or "").split()[-1].lower()
            if nick:
                idx.setdefault(nick, []).append(pl)
    rank = {"out": 0, "doubtful": 1, "questionable": 2}
    cols = []
    for side in ("away", "home"):
        t = g.get(side) or {}
        rows = idx.get((t.get("name") or "").split()[-1].lower()) or []
        if not rows:
            continue
        rows = sorted(rows, key=lambda p: (rank.get((p.get("status") or "").lower(), 9),
                                           p.get("name") or ""))
        items_html = "".join(
            f'<div class="gp-dz-row"><span class="gp-dz-st s-'
            f'{esc((p.get("status") or "").lower()[:1] or "x")}">'
            f'{esc((p.get("status") or "")[:1].upper() or "?")}</span>'
            f'<span class="gp-dz-n">{esc(p.get("name") or "")}</span>'
            f'<span class="gp-dz-p">{esc(p.get("pos") or "")}</span>'
            f'<span class="gp-dz-i">{esc(_injury_case(p.get("detail") or ""))}</span>'
            f'<span class="gp-dz-f">{esc(p.get("status") or "")}</span></div>'
            for p in rows)
        cols.append(f'<div class="gp-dz-team"><div class="bd-label">'
                    f'{esc(t.get("abbr") or "")} \u00b7 {len(rows)} listed</div>'
                    f'{items_html}</div>')
    if not cols:
        return ""
    return (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Designations</span></div>'
            f'<a class="bd-more" href="/fantasy/injuries.html">All</a></div>'
            f'<div class="gp-dz">{"".join(cols)}</div></section>')


def _injury_case(text):
    """S-17: the feed writes "knee - mcl"; a reader reads "Knee (MCL)"."""
    t = (text or "").strip()
    if not t:
        return ""
    parts = [x.strip() for x in t.replace(" - ", "|").replace(" / ", "|").split("|") if x.strip()]
    # Uppercase the abbreviations a report actually uses, not every short word: the
    # first cut keyed on length and turned "hip" into "HIP".
    ABBR = {"acl", "mcl", "pcl", "lcl", "ucl", "mri", "cte", "ir", "pup", "nfi",
            "acj", "ac", "it", "tbi", "nfl"}
    def cap(w):
        return w.upper() if w.lower() in ABBR else w[:1].upper() + w[1:]
    parts = [" ".join(cap(w) for w in p.split()) for p in parts]
    return parts[0] if len(parts) == 1 else f"{parts[0]} ({', '.join(parts[1:])})"


def render_game_page(g, points, board, wx, items, dateline):
    """S-B8. The game header, the fantasy strip and inactives, leaders, weather, and
    the desk's recent stories for both teams."""
    ia = _ia_index(board)
    away, home = g.get("away") or {}, g.get("home") or {}
    inact = []
    for key in ("away", "home"):
        side = g.get(key) or {}
        # H-1: this game's list, not this team's most recent one. The page was listing
        # Week 1's inactives under a Week 2 fixture, with the names.
        t = _ia_for_game(g, ia, key)
        if not t:
            continue
        names = ", ".join(f'{p.get("name")} ({p.get("pos")})' for p in t["players"])
        inact.append(f'<div class="gp-ia"><span class="bd-label">{esc(side.get("abbr"))}'
                     f' inactive</span><span class="bd-read">{esc(names)}</span></div>')
    inact_block = ""
    if inact:
        inact_block = (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                       f'<span class="bd-eyebrow">Inactives</span></div>'
                       f'<a class="bd-more" href="/fantasy/inactives.html">All lists</a>'
                       f'</div>{"".join(inact)}</section>')
    # UX-4: ONLY STORIES ABOUT THESE TWO TEAMS. This matched a nickname against the
    # title or the key fact, case-insensitively, which is how a Cowboys-Giants
    # viewership story reached the Lions-Bills page. It is the same shallow key the
    # card story line had, and it takes the same rule: the full team name where the
    # desk knows it, the nickname in the HEADLINE only otherwise, and never a headline
    # whose subject is a different team in the same league.
    live_items = [i for i in (items or [])
                  if not i.get("example") and not _is_wrap(i)][:120]
    league = (g.get("league") or "").upper()
    full, nicks = [], []
    for _side in ("away", "home"):
        _t = g.get(_side) or {}
        _fn = _tk_full_name(league, _t.get("id"))
        if _fn:
            full.append(_fn)
        elif len(_t.get("name") or "") > 2:
            nicks.append(_t["name"])
    rel = []
    for i in live_items:
        tags = [t.upper() for t in tags_for(i)] + [(i.get("league") or "").upper()]
        if league and league not in tags:
            continue
        title = i.get("title") or ""
        body = title + " " + (i.get("dek") or "")
        if not (any(re.search(r"\b" + re.escape(n) + r"\b", body) for n in full)
                or any(re.search(r"\b" + re.escape(n) + r"\b", title) for n in nicks)):
            continue
        subj = _tk_lead_team(league, title)
        if subj and subj not in {n.lower() for n in nicks} | {
                f.split()[-1].lower() for f in full}:
            continue
        rel.append(i)
        if len(rel) == 4:
            break
    rel_block = ""
    if rel:
        rel_block = ('<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                     '<span class="bd-eyebrow">From the desk</span></div></div>'
                     '<div class="nh-rows">'
                     + "".join(_news_row(i) for i in rel) + '</div></section>')
    _pre = g.get("state") == "pre"
    # H-4 (SC-9): the header is the Ticket card, with its team-colour stub and the
    # leader/trailer colours on live and final. It was the old dark marquee card, which
    # is the one surface SC-9 names that was still on the previous design. The
    # availability line under it follows H-1: a list counts for this game only when it
    # was first seen inside this game's window.
    # UX-4: the page carries a stamp that MOVES WITH THE POLL, as the band's does. It
    # read "Updated Sep 16, 7:57 AM ET" on game day, which is the build time, not the
    # data's.
    head = (f'<div class="scoreband scoreband-page gp-head">'
            f'{_tk_card(g, ia, wx=wx, desig=IA_DESIG, items=items, buttons=False)}'
            f'<div class="sb-head"><div class="sb-head-l"></div>'
            f'<span class="sb-stamp">Updated '
            f'{esc(_et((SB_DATA or {}).get("fetched_at") or ""))}</span></div></div>'
            + SB_LIVE_JS)

    # The inactives block says WHEN a list is expected rather than being absent, so a
    # reader before kickoff learns something instead of nothing (S-20).
    if not inact and _pre:
        import datetime as _dt
        _d = _utc_dt(g.get("start_utc") or "")
        if _d:
            _post = _et_clock(_d - _dt.timedelta(minutes=90))
            inact_block = (
                f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                f'<span class="bd-eyebrow">Inactives</span></div>'
                f'<a class="bd-more" href="/fantasy/inactives.html">All lists</a></div>'
                # C-L1: a stamp, not an explanation of how the league works.
                f'<p class="bd-read">Post about {esc(_post)}</p></section>')

    # Designations for both teams, from this week's report.
    # UX-4: the per-player designations. The block that used to be here compared the
    # game's team NICKNAMES ("Lions") against the report's full names ("Detroit Lions")
    # and so never matched a single player: _rows was always empty and the section never
    # rendered, which is why the page showed only the counts in the header. Another
    # shallow key, silently returning nothing rather than the wrong thing.
    _desig = _gp_designations(g, IA_DESIG)

    # Where to watch, when the feed has this game.
    _w2w = ""
    if W2W_LIVE and g.get("network"):
        _w2w = (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                f'<span class="bd-eyebrow">Where to watch</span></div>'
                f'<a class="bd-more" href="/where-to-watch.html">All games</a></div>'
                f'<p class="bd-read">{esc(g.get("network"))} carries this game.</p>'
                f'</section>')
    body = f"""<main class="wrap"><section class="page">
    <h1 class="lx-h1" style="margin-bottom:6px">{esc(away.get("name") or "")} at
     {esc(home.get("name") or "")}</h1>
  {head}
  {_game_wx_block(g, wx)}
  {inact_block}
  {_desig}
  {_w2w}
  {"" if _pre else _leaders_module(points, "Fantasy leaders", anchor="box")}
  {rel_block}
  {fantasy_asof("Designations", (IA_DESIG or {}).get("last_poll") or "",
                "the league injury report")}
</section></main>"""
    return shell(f'{away.get("abbr")} at {home.get("abbr")} - {NAME}',
                 f'{away.get("name")} at {home.get("name")}: score, inactives, fantasy '
                 f'leaders and kickoff weather. Facts, not advice.',
                 "Scores", body, dateline, path=f'/games/{g.get("id")}.html',
                 og_image=f'{ORIGIN}/share/games/{g.get("id")}.png')


def render_fantasy_live(all_points, dateline):
    """S-B3's all-games board."""
    merged = {}
    for pts in all_points.values():
        merged.update(pts)
    if not merged:
        return None
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/index.html">Home</a> / Fantasy / Live points</p>
  <h1 class="lx-h1" style="margin-bottom:6px">Live fantasy points</h1>
  <p class="lx-dek">Every player with a stat line this week, across every game.</p>
  {fantasy_asof("Points", _build_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "the official box score")}
  {_leaders_module(merged, f"Week {nfl_week()[0]} leaders", n=25, expand=False)}
</section></main>"""
    return shell(f"Live fantasy points - {NAME}",
                 "Live fantasy points in PPR, half-PPR and standard, computed from the "
                 "official box score. No projections, ever.",
                 "Fantasy", body, dateline, path="/fantasy/live.html")


# ---- S-B12: byes and the schedule ---------------------------------------------
# All of it from the schedule file the band already reads. A week with no byes has no
# byes card; a week the file does not carry has no windows block. Nothing is invented
# and nothing is drawn empty.

# The windows a reader has to be told about, because they are not Sunday afternoon.
_ODD_WINDOW = re.compile(r"thursday|saturday|monday|sunday night", re.I)


def _sb12_week(wk):
    for w in ((W2W_DATA or {}).get("weeks") or []):
        if w.get("week") == wk:
            return w
    return None


def _sb12_byes_card():
    """S-B12: this week's byes and next week's, on the days it matters (Tue-Sat).

    The NFL has no byes until week five or so, so for most of September this returns
    nothing at all, which is the right answer rather than a card reading "none".
    """
    wk, _ = nfl_week()
    if not wk:
        return ""
    dow = _build_now().astimezone(_ET).weekday()      # Mon 0 .. Sun 6
    if dow not in (1, 2, 3, 4, 5):                    # Tuesday to Saturday
        return ""
    rows = []
    for label, n in ((f"Week {wk}", wk), (f"Week {wk + 1}", wk + 1)):
        teams = nfl_byes(n)
        if teams:
            rows.append(f'<div class="bd-rec-row"><span class="bd-rec-t">{esc(label)}'
                        f'</span><span class="bd-src">{esc(", ".join(teams))}</span></div>')
    if not rows:
        return ""
    return (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">On bye</span></div></div>'
            f'<div class="bd-rec-rows">{"".join(rows)}</div></section>')


def _sb12_windows():
    """S-B12: the week's games by window, with the kickoff in ET and the network, and
    the unusual windows flagged. Sunday afternoon is not flagged; it is the default."""
    wk, _ = nfl_week()
    week = _sb12_week(wk)
    if not week:
        return ""
    by_win = {}
    for g in (week.get("games") or []):
        by_win.setdefault(g.get("window") or "", []).append(g)
    if not by_win:
        return ""
    def _key(w):
        gs = by_win[w]
        ks = [_utc_dt(g.get("kickoff_utc") or "") for g in gs]
        ks = [k for k in ks if k]
        return min(ks) if ks else _build_now()
    out = []
    for win in sorted(by_win, key=_key):
        gs = sorted(by_win[win], key=lambda g: g.get("kickoff_utc") or "")
        odd = bool(_ODD_WINDOW.search(win))
        # The 9:30 AM ET international window is unusual and does not name itself.
        if not odd:
            odd = any((g.get("kickoff_et") or "").startswith("9:30 AM") for g in gs)
        flag = '<span class="fw-odd">unusual window</span>' if odd else ""
        rows = "".join(
            f'<div class="w2w-row"><span class="w2w-game">{esc(g.get("away") or "")} at '
            f'{esc(g.get("home") or "")}</span>'
            f'<span class="bd-src">{esc(g.get("kickoff_et") or "")}</span>'
            f'<span class="w2w-cars">{_w2w_carriers(g)}</span></div>' for g in gs)
        out.append(f'<div class="fw-win"><div class="fw-wh">'
                   f'<span class="bd-label">{esc(win)}</span>{flag}'
                   f'<span class="bd-src">{esc(gs[0].get("day_et") or "")}</span></div>'
                   f'<div class="w2w">{rows}</div></div>')
    return (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Week {wk} windows</span></div>'
            f'<a class="bd-more" href="/where-to-watch.html">All games</a></div>'
            f'{"".join(out)}</section>')


def _sb12_who_plays_when(games):
    """S-B12: the who-plays-when strip for the inactives board. One row per window with
    the teams in it, so a reader scanning lists knows which games they belong to."""
    if not games:
        return ""
    by_win = {}
    for g in games:
        by_win.setdefault(g.get("window") or "", []).append(g)
    # N-8: the strip is a menu for the sections below it, so it runs in the same order:
    # the window that is next at the top, the ones already played at the foot. A window
    # takes the standing of its own games, which is what min() over the fixture key is.
    def _key(w):
        return min(_ia_game_key(g) for g in by_win[w])
    rows = []
    for win in sorted(by_win, key=_key):
        gs = by_win[win]
        _past = _key(win)[0] == 2
        teams = " \u00b7 ".join(f'{g.get("away") or ""} at {g.get("home") or ""}'
                                for g in gs[:8])
        more = f" and {len(gs) - 8} more" if len(gs) > 8 else ""
        rows.append(f'<div class="wpw-row{" past" if _past else ""}">'
                    f'<span class="bd-label">{esc(win)}</span>'
                    + ('<span class="wpw-done">played</span>' if _past else "")
                    + f'<span class="bd-src">{esc(teams + more)}</span></div>')
    wk, _ = nfl_week()
    head = (f'<div class="wpw-h"><span class="bd-eyebrow">Week {wk}, who plays when'
            f'</span><a class="bd-more" href="/where-to-watch.html">All games</a></div>'
            if wk else "")
    return f'{head}<div class="wpw">{"".join(rows)}</div>'


def render_fantasy_hub(board, desig, all_points, wx, sb, dateline):
    """S-B7. The hub: the official answer, then the surfaces that give it."""
    blocks = []
    if board:
        top = board["teams"][:6]
        cards = "".join(
            f'<a class="bd-card" href="/fantasy/inactives.html" '
            f'style="text-decoration:none"><span class="bd-label">{esc(t["team"])}</span>'
            f'<span class="bd-read">{t["count"]} inactive</span>'
            f'<span class="bd-stamp">posted {esc(_et(t["first_seen"]))}</span></a>'
            for t in top)
        blocks.append(("inactives",
            f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(_ia_heading(board))}</span>'
            f'<span class="bd-stamp">{_ia_hub_count(board)}</span></div>'
            f'<a class="bd-more" href="/fantasy/inactives.html">All teams</a>'
            f'</div><div class="bd-cards4">{cards}</div></section>'))
    if desig:
        counts = " · ".join(f'{k} {len(v)}' for k, v in desig["groups"].items() if v)
        blocks.append(("designations",
            f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Designations{_wk_suffix()}</span>'
            f'<span class="bd-stamp">{counts}</span></div>'
            f'<a class="bd-more" href="/fantasy/injuries.html">All</a>'
            f'</div></section>'))
    merged = {}
    for pts in (all_points or {}).values():
        merged.update(pts)
    if merged:
        blocks.append(("live", _leaders_module(merged, "Live points", n=8, expand=False)
                      .replace('</section>',
                               '<a class="bd-more" href="/fantasy/live.html">'
                               'The full board</a></section>')))
    if not blocks:
        return None
    # S-E: the day's marquee games, as "Where to watch tonight". The network already
    # rides every Scoreboard card; this is the same data on the surface a fantasy
    # reader is already on.
    watch = ""
    if sb:
        games = [g for L in sb["leagues"] for g in L["games"]
                 if g.get("state") in ("pre", "in")]
        games.sort(key=lambda g: (_league_rank(g.get("league") or ""),
                                  _game_rank(g), g.get("start_utc") or ""))
        rows = "".join(
            f'<div class="w2w-row"><span class="w2w-game">'
            f'{esc(_team_label(g, g.get("away") or {}))} at '
            f'{esc(_team_label(g, g.get("home") or {}))}</span>'
            # UX-9: ONE TIME FORMAT. This printed the feed's own string, "9/17 - 8:15
            # PM EDT": a numeric date and a zone name that changes twice a year, on the
            # one surface that disagreed with every other. Day then time, always ET.
            f'<span class="bd-src">{esc(_day_time(g))}</span>'
            f'<span class="w2w-cars">'
            + (f'<span class="w2w-car">{esc(g.get("network"))}</span>'
               if g.get("network") else '<span class="bd-src">not announced</span>')
            + '</span></div>' for g in games[:6])
        if rows:
            watch = (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                     f'<span class="bd-eyebrow">Tonight</span></div>'
                     f'<a class="bd-more" href="/where-to-watch.html">All games</a>'
                     f'</div><div class="w2w">{rows}</div></section>')

      # S-B15: the hub is day-aware. The player check stays at the top; under it the
    # blocks are ORDERED by the day, leading with the one that day is about.
    #
    # The order is over the blocks the desk actually holds. Tuesday's "week in numbers"
    # (S-B13), Wednesday's practice reports (S-B9), the depth-chart changes (S-B10) and
    # the roster moves (S-B11) are not built yet, so those days lead with the next
    # block in their own list rather than with an empty frame: a module with no data is
    # omitted, and that rule outranks the running order.
    named = dict(blocks)
    named["windows"] = _sb12_windows()
    named["byes"] = _sb12_byes_card()
    named["tonight"] = watch
    DAY_ORDER = {
        1: ["byes", "inactives", "designations", "windows", "tonight"],      # Tue
        2: ["designations", "inactives", "byes", "windows", "tonight"],      # Wed
        3: ["tonight", "inactives", "designations", "windows", "byes"],      # Thu
        4: ["designations", "windows", "inactives", "byes", "tonight"],      # Fri
        5: ["windows", "designations", "inactives", "byes", "tonight"],      # Sat
        6: ["inactives", "live", "designations", "tonight", "windows"],      # Sun
        0: ["live", "inactives", "designations", "tonight", "windows"],      # Mon
    }
    _dow = _build_now().astimezone(_ET).weekday()
    _order = DAY_ORDER.get(_dow, ["inactives", "designations", "windows", "tonight"])
    _seen, _out = set(), []
    for key in _order + sorted(named):          # anything unlisted still renders, last
        if key in _seen:
            continue
        _seen.add(key)
        if named.get(key):
            _out.append(named[key])

    body = f"""<main class="wrap"><section class="page">
  <h1 class="lx-h1" style="margin-bottom:6px">Fantasy</h1>
  {player_check_block()}
  {"".join(_out)}
</section></main>"""
    return shell(f"Fantasy facts - {NAME}",
                 "Official inactives, designations and live points. Facts, not advice: "
                 "we never tell you whom to start.",
                 "Fantasy", body, dateline, path="/fantasy/index.html")


# ---- S-B6: the player check, and player status pages ---------------------------
# A client-side search over the daily index. The search runs in the browser against a
# small JSON payload; no query is sent anywhere and nothing is logged, which is the
# same rule the crypto watchlist follows.

PLAYER_SEARCH_JS = """<script>(function(){
  var box=document.getElementById('pc-q'), out=document.getElementById('pc-out');
  if(!box||!out) return;
  var data=null, url=box.getAttribute('data-src');
  function load(){ if(data) return Promise.resolve(data);
    return fetch(url).then(function(r){return r.json()}).then(function(j){
      data=j.players||[]; return data; }); }
  function card(p){
    var st = p.designation ? p.designation : (p.inactive_seen ? 'Inactive' : 'No designation');
    var cls = p.inactive_seen ? 'dat' : (p.designation ? 'dat' : 'ok');
    var n = p.next || {};
    var when = n.day ? (n.day+' '+(n.kickoff_et||'')) : '';
    var opp = n.opponent ? ((n.home?'vs ':'at ')+n.opponent) : '';
    return '<a class="bd-card pc-card" href="/players/'+p.slug+'.html">'
      +'<span class="bd-cardtop"><span class="bd-eyebrow">'+p.team+' '+p.pos+'</span>'
      +'<span class="bd-badge '+cls+'">'+st+'</span></span>'
      +'<span class="bd-rec-hl" style="font-size:22px">'+p.name+'</span>'
      +(p.detail?'<span class="bd-src">'+p.detail+'</span>':'')
      +(opp?'<span class="bd-read">Next: '+opp+(when?' · '+when:'')
        +(n.network?' · '+n.network:'')+'</span>':'')
      +'</a>';
  }
  function run(){
    var q=(box.value||'').trim().toLowerCase();
    if(q.length<2){ out.innerHTML=''; return; }
    load().then(function(ps){
      var hits=ps.filter(function(p){return p.name.toLowerCase().indexOf(q)>-1;}).slice(0,8);
      out.innerHTML = hits.length ? hits.map(card).join('')
        : '<p class="bd-src">No player by that name.</p>';
    }).catch(function(){ out.innerHTML='<p class="bd-src">Could not load. Try the '
      +'boards below.</p>'; });
  }
  var t; box.addEventListener('input',function(){clearTimeout(t);t=setTimeout(run,140);});
})();</script>"""


def player_check_block():
    return ('<section class="bd-mod pc"><div class="bd-sec"><div class="bd-sec-l">'
            '<h2 class="bd-h2">Player check</h2></div></div>'
            '<label class="sr-only" for="pc-q">Search a player by name</label>'
            '<div class="pc-field">'
            '<svg class="pc-ico" width="17" height="17" viewBox="0 0 17 17" '
            'aria-hidden="true"><circle cx="7.2" cy="7.2" r="5.2" fill="none" '
            'stroke="currentColor" stroke-width="1.7"></circle>'
            '<path d="M11.2 11.2L15.2 15.2" stroke="currentColor" stroke-width="1.7" '
            'stroke-linecap="round"></path></svg>'
            '<input id="pc-q" class="pc-q" type="search" autocomplete="off" '
            'placeholder="Player name" data-src="/data/players.json">'
            '<button type="button" class="pc-go" data-pc-go>Check</button></div>'
            '<div id="pc-out" class="pc-out" aria-live="polite"></div>'
            '</section>')


_KICK_RX = re.compile(r"^(\d{1,2}):(\d{2})\s*(AM|PM)", re.I)


def _ia_post_phrase(n):
    """UX-18 (S-17). When this game's inactives post. The player record carries the
    kickoff as the reader sees it ("Sun 20 Sep", "4:25 PM ET"), so the line is built
    from those and not from a clock the record does not hold. "About" is not hedging:
    teams post about 90 minutes out, and a derived time is not presented as an
    announced one. If the subtraction would cross back over midnight the day is left
    off rather than guessed at."""
    m = _KICK_RX.match((n or {}).get("kickoff_et") or "")
    if not m:
        return ""
    h, mi = int(m.group(1)) % 12, int(m.group(2))
    if m.group(3).upper() == "PM":
        h += 12
    mins = h * 60 + mi - 90
    day = ((n.get("day") or "").split() or [""])[0]
    if mins < 0:
        mins += 24 * 60
        day = ""
    h2, m2 = divmod(mins, 60)
    ampm = "AM" if h2 < 12 else "PM"
    h12 = h2 % 12 or 12
    when = f"{h12}:{m2:02d} {ampm} ET"
    return f"Inactives post about {day} {when}.".replace("  ", " ")


def _player_answer(p, n):
    """UX-18 (S-17). The page asks one question in its H1 and used to answer it three
    times: a badge, a sentence, and the first row of the season table. One line answers
    it now, in the order a reader needs it: the status, what it is, and when the list
    that settles it posts. The badge is gone; it said the same word twice."""
    if p.get("inactive_seen"):
        seen = _utc_dt(p.get("inactive_seen") or "")
        bits = ["Inactive."]
        g = p.get("inactive_game") or (n or {}).get("opponent") or ""
        if g:
            bits[0] = f"Inactive {'vs ' if (n or {}).get('home') else 'at '}{g}."
        if seen:
            e = seen.astimezone(_ET)
            today = _build_now().astimezone(_ET).date()
            day = ("today" if e.date() == today
                   else "yesterday" if e.date() == today - datetime.timedelta(days=1)
                   else e.strftime("%A"))
            bits.append(f"Posted {day}, {_et_clock(seen)}.")
        return " ".join(bits)
    if p.get("designation"):
        bits = [f'{p["designation"].strip().rstrip(".")}.']
        inj = _injury_case(p.get("detail") or "")
        if inj:
            bits.append(f"{inj}.")
        post = _ia_post_phrase(n)
        if post:
            bits.append(post)
        return " ".join(bits)
    return "No designation on the official report."


def render_player_page(p, board, dateline):
    """/players/<slug>. Titled to the question people actually type."""
    n = p.get("next") or {}
    answer = _player_answer(p, n)
    nxt = ""
    if n.get("opponent"):
        when = " ".join(x for x in (n.get("day"), n.get("kickoff_et")) if x)
        nxt = (f'<p class="bd-read">Next game: '
               f'{"vs " if n.get("home") else "at "}{esc(n["opponent"])}'
               + (f' · {esc(when)}' if when else "")
               + (f' · {esc(n["network"])}' if n.get("network") else "") + '</p>')
    hist = ""
    rows = [d for d in (p.get("designations") or []) if d.get("status")]
    # UX-18 (S-17): "This season" with one row that repeats the answer line is the
    # third place the page answered its own question. A log needs something to log.
    if len(rows) == 1 and (rows[0].get("status") or "").strip().lower() == \
            (p.get("designation") or "").strip().lower():
        rows = []
    if rows:
        hist = ('<div class="bd-card pl-desig"><span class="bd-label">'
                'This season</span><div class="pl-rows">'
                + "".join(
                    f'<div class="pl-row"><span class="pl-d">'
                    f'{esc(fmt_short_date(d.get("date") or ""))}</span>'
                    f'<span class="pl-s">{esc(d.get("status") or "")}</span>'
                    f'<span class="bd-src">{esc(d.get("detail") or "")}</span></div>'
                    for d in rows[:8])
                + '</div></div>')
    body = f"""<main class="wrap narrow"><section class="page">
  <p class="bd-stamp"><a href="/fantasy/index.html">Fantasy</a> / {esc(p.get("name"))}</p>
  <h1 class="lx-h1" style="margin-bottom:6px">Is {esc(p.get("name"))} playing this week?
     Official status</h1>
  <div class="bd-cardtop" style="margin-bottom:8px">
    <span class="bd-eyebrow">{esc(p.get("team"))} {esc(p.get("pos"))}</span></div>
  <p class="lx-dek pl-answer">{esc(answer)}</p>
  {nxt}{hist}
  <p class="bd-src"><a href="/fantasy/inactives.html">Inactives</a> ·
     <a href="/fantasy/injuries.html">Designations</a></p>
  {fantasy_asof("Status", p.get("inactive_seen") or "", "the league injury report")}
</section></main>"""
    return shell(f'Is {p.get("name")} playing this week? Official status - {NAME}',
                 f'The official status for {p.get("name")}, {p.get("team")} '
                 f'{p.get("pos")}: designation, inactive list and next game. '
                 f'Facts, not advice.',
                 "Fantasy", body, dateline, path=f'/players/{p.get("slug")}.html')


# ---- S-B4: this week's designations --------------------------------------------
# Built from the SAME poll as the Inactives board, so the two pages can never disagree
# about a player. Grouped Out, Doubtful, Questionable, in that order, because that is
# the order the official report uses and the order of how much it settles.
#
# Injured Reserve, PUP and suspensions are roster states rather than game-week
# designations and appear on neither page.

def render_designations(desig, board, dateline):
    if not desig:
        return None
    ia_names = set()
    for t in (board or {}).get("teams") or []:
        for p in t.get("players") or []:
            ia_names.add((t.get("team"), p.get("name")))
    secs = []
    for status in ("Out", "Doubtful", "Questionable"):
        rows = desig["groups"].get(status) or []
        if not rows:
            continue
        cards = []
        for p in rows:
            # S-B1's rule, applied here too: a player carrying a designation who is NOT
            # on a posted inactive list is active. Saying so is the single most useful
            # thing this page does on a Sunday.
            ruled = _dg_ruling(p, board, W2W_DATA, ia_names)
            cards.append(
                f'<div class="dg-row"><span class="dg-name">{esc(p.get("name") or "")}</span>'
                f'<span class="ia-pos">{esc(p.get("pos") or "")}</span>'
                f'<span class="bd-src">{esc(p.get("team") or "")}</span>'
                f'<span class="bd-src">{esc(p.get("detail") or "")}</span>{ruled}</div>')
        secs.append(
            f'<section class="bd-mod" id="{esc(status.lower())}">'
            f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(status)}</span>'
            f'<span class="bd-stamp">{len(rows)} players</span></div></div>'
            f'<div class="dg-rows">{"".join(cards)}</div></section>')
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/index.html">Home</a> / Fantasy / Designations</p>
  <h1 class="lx-h1" style="margin-bottom:6px">Designations{_wk_suffix()}</h1>
  <p class="lx-dek">{desig["total"]} players</p>
  {fantasy_asof("Designations", desig.get("last_poll") or "", "the league injury report")}
  <p class="bd-src">Out, Doubtful and Questionable as the official report lists them.
     A player who is questionable and not on a posted inactive list is shown as active.
     Read on our own schedule; see the <a href="/fantasy/inactives.html">inactives
     board</a> for today's posted lists.</p>
  {"".join(secs)}
</section></main>"""
    return shell(f"NFL injury designations this week - {NAME}",
                 "Every player listed Out, Doubtful or Questionable on the official "
                 "report, with what it is and whether they have been ruled out today.",
                 "Fantasy", body, dateline, path="/fantasy/injuries.html")


# ---- S3: living tables --------------------------------------------------------
# "Evergreen pages built as tables that update when a ruling or filing posts. Each
# carries a source per row and an updated stamp."
#
# EVERY ROW IS A STORY THIS DESK PUBLISHED. That is the whole design. A media-rights
# table typed in from general knowledge would be longer and would also be this desk
# asserting deals it never reported and cannot stand behind. Each row here links the
# story, names the outlets that story cited, and carries that story's own date, so the
# table updates exactly when the desk publishes, which is what "living" means here.
#
# ONLY ONE OF THE TWO TABLES SHIPS. The order asks for media rights and for cap math
# (dead money). Measured across the whole live corpus: media rights has 5 reported
# deals, cap math has 1. A one-row table is not a table, and the alternative is to
# fill it from memory. So cap math is reported as having no inventory, the same
# finding as its Record lane, and it ships the day the desk has covered it.
LIVING_TABLES = [
    {
        "slug": "media-rights",
        "lane": "media-rights",
        "title": "Media rights, by property",
        "h1": "Sports media rights, every deal this desk has reported",
        "dek": "Who carries what, what changed, and the filing or announcement behind "
               "each row.",
        "desc": "A living table of sports media rights deals: property, what changed, "
                "when it was reported, and the source behind every row.",
        "col": "Property",
        "rx": (r"media rights|broadcast deal|tv deal|rights deal|streaming deal|"
               r"rights package|broadcast rights|tv contract|media deal|rights fee|"
               r"carriage"),
        "min_rows": 5,
    },
]


def _table_rows(spec, items):
    rx = re.compile(spec["rx"], re.I)
    live = [i for i in (items or [])
            if not i.get("example") and not _is_wrap(i) and not i.get("superseded_by")]
    got = []
    for i in live:
        t = i.get("title") or ""
        n = len(rx.findall(t)) + len(rx.findall(i.get("key_fact") or "")) \
            + len(rx.findall(i.get("dek") or ""))
        if rx.search(t) or n >= 2:
            got.append(i)
    got.sort(key=lambda i: i.get("published_utc") or "", reverse=True)
    return got


def _table_property(item):
    """The league or property a row is about, from the tags the desk already applies.
    Falls back to the first proper noun in the headline rather than inventing one."""
    lg = {"nfl": "NFL", "mlb": "MLB", "nba": "NBA", "wnba": "WNBA", "nhl": "NHL",
          "soccer": "Soccer", "tennis": "Tennis", "golf": "Golf",
          "college-football": "College football", "college": "College",
          "combat sports": "Combat sports", "cycling": "Cycling"}
    for t in tags_for(item):
        if t in lg:
            return lg[t]
    _NOT_A_PROPERTY = {"nbc", "cbs", "fox", "abc", "espn", "tnt", "amazon", "netflix",
                       "peacock", "paramount", "apple", "disney", "comcast", "warner",
                       "prime", "ion", "victory+", "youtube", "max", "turner",
                       "scores-results", "transactions", "injuries", "markets"}
    for t in tags_for(item):
        if t and t.lower() not in _NOT_A_PROPERTY:
            return t.replace("-", " ").title()
    m = re.match(r"([A-Z][A-Za-z0-9'&.-]*)", item.get("title") or "")
    if m and m.group(1).lower() not in _NOT_A_PROPERTY:
        return m.group(1)
    return "Not stated"


def render_living_table(spec, items, dateline):
    rows = _table_rows(spec, items)
    if len(rows) < spec["min_rows"]:
        return None
    trs = []
    for i in rows:
        outlets = []
        for s in (i.get("sources") or []):
            nm = _bd_outlet(s)
            if nm and nm not in outlets:
                outlets.append(nm)
        what = clamp_sentences((i.get("key_fact") or i.get("dek") or "").strip(), 260)
        trs.append(
            f'<tr><td class="lt-prop">{esc(_table_property(i))}</td>'
            f'<td class="lt-what"><a href="/articles/{esc(i["slug"])}.html">'
            f'{esc(i.get("title") or "")}</a>'
            + (f'<span class="bd-src">{esc(what)}</span>' if what else "") + '</td>'
            f'<td class="lt-when"><span class="bd-stamp">{esc(fmt_date(i.get("date") or ""))}'
            f'</span></td>'
            f'<td class="lt-src"><span class="bd-src">'
            f'{esc(", ".join(outlets[:3]) or "linked on the story")}</span></td></tr>')
    updated = fmt_date(rows[0].get("date") or "")
    url = f'/keepers/{spec["slug"]}.html'
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/keepers.html">The Record</a> / {esc(spec["title"])}</p>
  <h1 class="lx-h1" style="margin-bottom:6px">{esc(spec["h1"])}</h1>
  <p class="lx-dek">{esc(spec["dek"])}</p>
  <div class="bd-cardtop"><span class="bd-badge dat">Living table</span>
    <span class="bd-stamp">{len(rows)} rows, updated {esc(updated)}</span></div>
  <div class="lt-wrap"><table class="lt">
    <thead><tr><th>{esc(spec["col"])}</th><th>What changed</th><th>Reported</th>
      <th>Source</th></tr></thead>
    <tbody>{"".join(trs)}</tbody></table></div>
  <p class="bd-src" style="margin-top:14px">Stories this desk published. Not a survey
     of every deal in the market.</p>
</section></main>"""
    return url, shell(f'{spec["title"]} - {NAME}', spec["desc"], "The Record", body,
                      dateline, path=url)


# ---- S-C: Record lane cards v3, Contracts and Fantasy facts --------------------
# The lane card drops the cadence bars it used to carry. A bar chart of how often the
# desk published is a fact about the desk, not about the story, and the space is better
# spent on what the story established. It now carries the story's Bottom Line pull, the
# receipts line, and the read link, with a status chip ONLY when the metadata actually
# has one and a chart ONLY when the story carries numbers.

_MONEY_RX = re.compile(r"\$\s?[\d,.]+\s?(?:million|billion|bn|m)?\b", re.I)
# Narrow on purpose. "deal" alone catches a trade and a broadcast agreement; paired
# with a dollar figure and a contract verb it catches a contract.
_CONTRACT_RX = re.compile(r"\b(signs?|signed|signing|extension|extends?|re-signs?|"
                          r"guaranteed|year deal|[0-9]-year|contract)\b", re.I)
# A figure that came from a league or union document rather than a reporter.
_FILED_RX = re.compile(r"\b(league (?:document|filing|source)|union|NFLPA|NBPA|MLBPA|"
                       r"cap sheet|filing|filed with|official (?:document|release)|"
                       r"transaction wire)\b", re.I)


def _contracts_lane(items):
    out = []
    for i in items:
        tags = {t.lower() for t in tags_for(i)}
        if "transactions" not in tags:
            continue
        blob = " ".join([i.get("title") or "", i.get("key_fact") or ""])
        if _MONEY_RX.search(blob) and _CONTRACT_RX.search(blob):
            out.append(i)
    return out


_ANON_RX = re.compile(
    r"\b(anonymous(?:ly)? (?:source|sourced|estimate)|"
    r"(?:a |two |multiple |league |team )?sources? (?:told|say|said|indicate|"
    r"with knowledge|familiar)|per sources|according to sources|"
    r"people familiar (?:with|who)|someone familiar|"
    r"who (?:was |were )?(?:not authori[sz]ed|granted anonymity)|"
    r"spoke on condition of anonymity|unnamed source)\b", re.I)


def _official_report(item):
    """UX-14 (S-12). The Fantasy facts lane is official reports only: the league's
    injury report, a team's own statement, a filing. A story that rests on unnamed
    sourcing may be true and may run everywhere else on the site; it does not set a
    fantasy expectation, so it never features here. On 16 Sep the lane led with an
    anonymous-source estimate of a three-to-four-week absence, which is exactly the
    shape the doctrine excludes."""
    blob = " ".join([item.get("title") or "", item.get("dek") or "",
                     item.get("key_fact") or ""]
                    + [str(b) for b in (item.get("body") or [])[:3]])
    return not _ANON_RX.search(blob)


def _fantasy_facts_lane(items):
    return [i for i in items
            if "injuries" in {t.lower() for t in tags_for(i)} and _official_report(i)]


def _receipt_status(item):
    """Filed when the figure comes from a league or union document; Reported with the
    outlet named when it does not. Never guessed: with no outlet to name and no filing
    language, the row carries neither chip."""
    blob = " ".join([item.get("key_fact") or "", item.get("dek") or ""]
                    + [str(b) for b in (item.get("body") or [])[:2]])
    if _FILED_RX.search(blob):
        return '<span class="bd-badge ok">Filed</span>'
    outlets = []
    for s in (item.get("sources") or []):
        nm = _bd_outlet(s)
        if nm and nm not in outlets:
            outlets.append(nm)
    # UX-2: the sourcing badge is gone from here. status_badge owns the one status a
    # card shows, and "Reported \u00b7 Outlet" is one of its three words. "Filed" above
    # stays: it is a fact about a document, not a claim about the desk's confidence.
    return ""


def _lane_figures(item):
    """S-17. The lane's money figures as a chip.

    This drew a two-bar chart comparing "$45M" against "$30 million", which invited a
    reading it could not support: the bars looked like a part-to-whole when the two
    figures are a total and a guarantee. The figures themselves were never the problem,
    so they stay, as text, in the order they were found."""
    figs, seen = [], set()
    blob = " ".join([item.get("title") or "", item.get("key_fact") or ""])
    for f in _MONEY_RX.findall(blob):
        txt = f.strip()
        v = _usd(txt if txt.startswith("$") else "$" + txt)
        if v and v not in seen:
            seen.add(v)
            figs.append((v, txt))
    if len(figs) < 2:
        return ""
    figs.sort(key=lambda t: -t[0])
    return (f'<span class="bd-chip lane-figs">'
            f'{esc(" · ".join(fig_money(v) for v, _f in figs[:3]))}</span>')


SPORTS_ACCENT = "#1F5E3F"
LANE_COLORS = {"Lawsuits and rulings": "#4B5563"}


def lane_card_v3(item, lane_name, stamp=None):
    """S-C. The v3 lane card. `stamp` lets a lane show its count and newest date in
    place of the piece's own dateline (S-17)."""
    pull = clamp_sentences(
        (item.get("bottom_line") or item.get("key_fact") or item.get("dek") or "").strip(), 300)
    chip = _receipt_status(item)
    # A status chip only when the metadata has one. verdict_badge is the desk's own
    # and is present on every checked story; the receipt chip is not.
    status = verdict_badge(item.get("verdict"), item) if item.get("verdict") else ""
    outlets = []
    for s in (item.get("sources") or []):
        nm = _bd_outlet(s)
        if nm and nm not in outlets:
            outlets.append(nm)
    receipts = (f'<p class="bd-src">Source: {esc(", ".join(outlets[:3]))}</p>'
                if outlets else "")
    # A-13: a 3px left rule in the lane colour, with the eyebrow in the same colour.
    # The style tile is the reference where the board names only two lanes (V-15):
    # ".card.lane { border-left:3px solid #1F5E3F }" is the default and "Sports rule
    # #1F5E3F - Sports accent, lanes, links" confirms it, so lanes take the Sports
    # accent and lawsuits is the single exception at #4B5563. Nothing invented.
    _lc = LANE_COLORS.get(lane_name, SPORTS_ACCENT)
    return (f'<div class="bd-card lane-v3" style="--lane:{_lc}">'
            f'<div class="bd-cardtop"><span class="bd-eyebrow" style="color:{_lc}">'
            f'{esc(lane_name)}</span>'
            f'{status}{chip}<span class="bd-stamp">'
            f'{stamp if stamp else esc(fmt_when(item))}</span></div>'
            f'<a class="bd-rec-hl" href="/articles/{esc(item["slug"])}.html">'
            f'{esc(item.get("title") or "")}</a>'
            + (f'<p class="bd-read" style="font-size:15px">{esc(pull)}</p>' if pull else "")
            + _lane_figures(item)
            + receipts
            + f'<a class="bd-more" href="/articles/{esc(item["slug"])}.html">'
              f'Read the story</a></div>')


def extra_lanes(items, board, claimed=None, strip=False):
    """S-17. The Contracts and Fantasy facts lane SECTIONS, with no wrapper of their
    own. They used to render their own bd-mod with a second copy of the Record's
    header, which is what printed the Record twice on the homepage. record_sections
    owns the block and the header now; this returns lanes to go inside it."""
    # ONE STORY, ONE PLACE ON THE PAGE (R2). These two lanes matched against the whole
    # live corpus while the main lanes claimed from it separately, so a story could be
    # claimed by Contracts AND by Fantasy facts AND still be the homepage lead: measured
    # 15 Sep, the Pacheco surgery piece rendered three times on one screen. The lanes
    # above have first claim, these two take what is left, and the second of them does
    # not repeat the first.
    taken = set(claimed or ())
    live = [i for i in (items or [])
            if not i.get("example") and not _is_wrap(i) and not i.get("superseded_by")
            and i.get("slug") not in taken]
    live.sort(key=lambda i: i.get("published_utc") or "", reverse=True)
    out = []
    for name, rows, href in (
            ("Contracts", _contracts_lane(live), None),
            ("Fantasy facts", _fantasy_facts_lane(live), "/fantasy/index.html")):
        rows = [i for i in rows if i.get("slug") not in taken]
        if len(rows) < RECORD_LANE_MIN:
            continue
        taken.update(i.get("slug") for i in rows[:4])
        # UX-11: the lane takes the first story not already on this page. A lane
        # featuring a story the desk grid or Also today already ran is the same page
        # telling the reader twice, and it costs the lane the story below it.
        rows = [r for r in rows if _claim(r.get("slug"))]
        if not rows:
            continue
        # UX-18 (S-16): on the homepage these two lanes wear the strip like the rest of
        # the Record. They were the pair the old details collapse was hiding, and with
        # the collapse gone they were 1,636px of a phone homepage on their own.
        if strip:
            feat, more_rows = rows[0], rows[1:3]
            out.append(
                f'<section class="bd-rec-lane rs">'
                # No count on these two: the main lanes count an inventory of picks
                # and these match the whole live corpus, so "105 stories" beside "12
                # stories" would put two different units in one row of numbers.
                f'<a class="rs-n" href="{esc(href or "/keepers.html")}">{esc(name)}</a>'
                f'<a class="rs-f" href="/articles/{esc(feat["slug"])}.html">'
                f'{esc(feat.get("title") or "")}</a>'
                + "".join(f'<a class="rs-m" href="/articles/{esc(i["slug"])}.html">'
                          f'{esc(i.get("title") or "")}</a>' for i in more_rows)
                + '</section>')
            continue
        feat = rows[0]
        more = "".join(
            f'<div class="bd-rec-row">'
            f'<a class="bd-rec-t" href="/articles/{esc(i["slug"])}.html">'
            f'{esc(i.get("title") or "")}</a>'
            f'<span class="bd-src">{esc(fmt_when(i))}</span></div>' for i in rows[1:4])
        extra = ""
        if name == "Fantasy facts" and board:
            extra = (f'<div class="bd-rec-row"><a class="bd-rec-t" '
                     f'href="/fantasy/inactives.html">This week\'s inactives, '
                     f'{_ia_hub_count(board)}</a>'
                     f'<span class="bd-src">Living board</span></div>')
        right = (f'<div class="bd-card bd-rec-more">'
                 f'<span class="bd-label">More</span>'
                 f'<div class="bd-rec-rows">{extra}{more}</div>'
                 + (f'<a class="bd-more" href="{href}">The fantasy hub</a>' if href else "")
                 + '</div>')
        out.append(f'<section class="bd-rec-lane" id="{slugify(name)}">'
                   f'{lane_card_v3(feat, name)}{right}</section>')
    return "".join(out)


# ---- S5: The Record -----------------------------------------------------------
# Addendum of 2026-09-13, ported from the crypto desk. What this desk has published
# that stays true after the news moves on, grouped into lanes, each lane led by its
# strongest piece. It replaces "Stories worth keeping", which was a list of bare links
# saying nothing about what any of them was. The name changes everywhere; /keepers
# stays the URL, per family standing law.
#
# LANE MATCHING ON THIS DESK IS BY PHRASE, NOT BY TAG, and the difference is not a
# style choice. The crypto desk tags stories `regulation`, `stablecoins`, `etfs-funds`,
# so its lanes are those tags and the inventory falls out. This desk tags by league and
# event type: transactions 163, scores-results 129, nfl 120, injuries 94. Not one tag
# names a business-of-sports lane, so the lanes here are phrase matchers over the story
# text.
#
# THE PHRASES ARE ALL MULTI-WORD, and that was measured rather than assumed. A first cut
# used single words and filed "SMU Defeats FSU in a Game Played Without Stadium Lights"
# under Stadium deals and "Judge Reinstated: Yankees Captain Returns After 3-Month IL"
# under Discipline. That is the failure this chassis has now relearned six times: a
# matcher satisfied by one shared token needs a floor. Multi-word phrases are the floor
# here, plus the tag-chip rule the desk already uses: a TITLE hit qualifies alone,
# otherwise two hits across title, key_fact and dek.
RECORD_LANES = [
    ("lawsuits-and-rulings", "Lawsuits and rulings",
     ("lawsuit", "antitrust", "class action", "federal judge", "criminal probe",
      "court ruling", "files suit", "settlement with", "grievance", "arbitrator",
      "subpoena", "indicted", "appeals court", "legal action", "prosecutors",
      "federal court", "injunction"), True),
    ("discipline", "Discipline",
     ("suspended for", "suspension", "fined ", "banned for", "violation",
      "disciplinary", "performance-enhancing", "ineligible", "expelled"), True),
    ("media-rights", "Media rights",
     ("media rights", "broadcast deal", "tv deal", "rights deal", "streaming deal",
      "rights package", "broadcast rights", "tv contract", "media deal",
      "regional sports network", "rights fee", "broadcast partner"), True),
    ("ownership", "Ownership",
     ("controlling stake", "minority stake", "investor group", "sale of the",
      "ownership group", "acquires the", "chapter 11", "new owner", "ownership stake",
      "takes over the", "purchase of the"), False),
    ("cap-math", "Cap math",
     ("salary cap", "cap space", "dead money", "luxury tax", "cap hit", "franchise tag",
      "cap penalty", "second apron", "cap charge", "cap casualty", "cap room"), False),
    ("stadium-deals", "Stadium deals",
     ("stadium deal", "naming rights", "new stadium", "stadium funding", "arena deal",
      "new arena", "ballpark deal", "stadium plan", "publicly funded", "stadium project",
      "stadium financing"), False),
    ("expansion", "Expansion",
     ("expansion team", "expansion franchise", "relocation", "expansion fee",
      "expansion bid", "relocate to", "expansion draft"), False),
]

# A lane needs this many pieces to render at all: one featured plus the three
# read-further rows the shape calls for. Below it the lane is omitted, per addendum
# item 5, rather than shown half empty.
RECORD_LANE_MIN = 4

# Slugs whose pages are standing explainers rather than dated reporting. Used only for
# the one-word type line on a read-further row.
_RECORD_EXPLAINER_SLUGS = set()   # this desk has no standing explainer pages yet


def _page_note(page, pages):
    """C-L6: counts are short. " \u00b7 page 2 of 3", or nothing on a single page."""
    return f" \u00b7 page {page} of {pages}" if pages > 1 else ""


def _record_type(item, hub_slugs):
    """Retained for the Record page's own grouping; it no longer labels a card.

    Copy item 24 removed "Checked story" and "Running story" from under every
    read-further headline: the row is the headline and its date. The words were
    shipping 707 times across the site, which is what the first copy pass missed by
    grepping a narrower set of chrome classes than the law actually covers."""
    if (item.get("slug") or "") in _RECORD_EXPLAINER_SLUGS:
        return "Explainer"
    if (item.get("slug") or "") in hub_slugs:
        return "Living table"
    if item.get("continued_by") or item.get("update_of"):
        return "Running story"
    return "Checked story"


def _record_lane_rx(kws):
    return re.compile(r"(?:" + "|".join(re.escape(k) for k in kws) + r")", re.I)


def _record_lane_match(rx, item):
    """The desk's own tag-chip rule, applied to lanes: a title hit qualifies alone,
    otherwise two hits across title, key_fact and dek. Never the body."""
    t = item.get("title") or ""
    if rx.search(t):
        return True
    n = len(rx.findall(t)) + len(rx.findall(item.get("key_fact") or "")) \
        + len(rx.findall(item.get("dek") or ""))
    return n >= 2


def _record_inventory(items):
    """Every evergreen pick bucketed by lane. One piece lands in one lane only: the
    first lane in RECORD_LANES order that claims it."""
    # THE POOL IS EVERY LIVE STORY, not evergreen_picks. evergreen_picks collapses to
    # one story per subject line, which is right for a homepage list and wrong here:
    # a lane IS a subject line, so that filter left five chapters of one lawsuit as a
    # single pick and starved every lane below the floor (measured: 2, 3, 2, 2, 0, 0,
    # 0 against 11, 8, 4, 3 from the full corpus). The lane match is itself the
    # evergreen filter on this desk. A court ruling or a rights deal stays true; a
    # Tuesday box score never matches a lane in the first place.
    pool = [i for i in (items or [])
            if not i.get("example") and not _is_wrap(i) and not i.get("superseded_by")]
    pool.sort(key=lambda i: i.get("published_utc") or "", reverse=True)
    picks = pool
    claimed, by_lane = set(), {}
    for slug, name, kws, _home in RECORD_LANES:
        rx = _record_lane_rx(kws)
        lane = []
        for it in picks:
            key = it.get("slug")
            if key in claimed:
                continue
            if _record_lane_match(rx, it):
                lane.append(it)
                claimed.add(key)
        by_lane[slug] = lane
    return by_lane, picks


def _record_bars(lane_items, w=440, h=54, months=6):
    """The lane's own publishing cadence: pieces per month over the last six months.
    This is the "small data element built from the lane's own content" the addendum
    asks for, and it is the one such element this desk can build without inventing a
    status model it does not have. A lane with nothing to count draws nothing."""
    import datetime as _dt
    now = _build_now()
    buckets, labels = [], []
    for k in range(months - 1, -1, -1):
        y, m = now.year, now.month - k
        while m <= 0:
            m += 12
            y -= 1
        buckets.append(sum(1 for i in lane_items
                           if (i.get("published_utc") or "")[:7] == f"{y:04d}-{m:02d}"))
        labels.append(_dt.date(y, m, 1).strftime("%b"))
    if not any(buckets):
        return ""
    peak = max(buckets) or 1
    bw, gap = 46, 12
    base, top = h - 16, 6
    parts = []
    for i, (n, lab) in enumerate(zip(buckets, labels)):
        x = i * (bw + gap)
        bh = max(2, round((n / peak) * (base - top)))
        parts.append(f'<rect x="{x}" y="{base - bh}" width="{bw}" height="{bh}" rx="2" '
                     f'fill="var(--rule)" opacity="{0.35 + 0.65 * (n / peak):.2f}"></rect>')
        parts.append(f'<text x="{x + bw / 2:.0f}" y="{h - 4}" font-family="var(--mono)" '
                     f'font-size="10.5" fill="var(--muted)" text-anchor="middle">{lab}</text>')
    total = (bw + gap) * len(buckets) - gap
    aria = ", ".join(f"{l} {n}" for l, n in zip(labels, buckets))
    return (f'<svg class="bd-chart" width="{total}" height="{h}" viewBox="0 0 {total} {h}" '
            f'role="img" aria-label="Pieces published in this lane by month: {esc(aria)}.">'
            f'{"".join(parts)}</svg>')


def _record_strip(slug, name, lane_items, hub_slugs):
    """UX-18 (S-16). The homepage Record as a strip: the lane's name, its feature, and
    two more. The full lane cards live on /keepers, which is the page for them.

    The five full cards ran 1,858px at 1440 and 4,004px on a phone, where they were
    82% of the homepage: the Record was not a section of the front page, it was the
    back half of it. The existing mitigation hid four lanes inside a details a script
    closed, which trades height for a page whose shape depends on JavaScript. A strip
    needs no script and shows every lane at once."""
    if len(lane_items) < RECORD_LANE_MIN:
        return ""
    picked = [i for i in lane_items if _claim(i.get("slug"))][:3]
    if not picked:
        return ""
    feat, rest = picked[0], picked[1:]
    rows = "".join(
        f'<a class="rs-m" href="/articles/{esc(i["slug"])}.html">'
        f'{esc(i.get("title") or "")}</a>' for i in rest)
    return (f'<section class="bd-rec-lane rs" aria-labelledby="rs-{esc(slug)}">'
            f'<a class="rs-n" id="rs-{esc(slug)}" href="/keepers.html#{esc(slug)}">'
            f'{esc(name)}</a>'
            f'<span class="rs-c">{len(lane_items)} stor'
            f'{"y" if len(lane_items) == 1 else "ies"}</span>'
            f'<a class="rs-f" href="/articles/{esc(feat["slug"])}.html">'
            f'{esc(feat.get("title") or "")}</a>{rows}</section>')


def _record_lane(slug, name, lane_items, hub_slugs, page=False, tables=None):
    """One lane: the featured piece on the left, three more on the right."""
    if len(lane_items) < RECORD_LANE_MIN:
        return ""
    feat = lane_items[0]
    rest = lane_items[1:4]
    newest = max((i.get("published_utc") or "") for i in lane_items)[:10]
    # was "1 pieces in the Record"; the count carries no noun now, so it cannot disagree
    status = f"{len(lane_items)} stor{'y' if len(lane_items) == 1 else 'ies'}"
    srcs = []
    for i in lane_items[:6]:
        for s in (i.get("sources") or []):
            lab = _bd_outlet(s)
            if lab and lab not in srcs:
                srcs.append(lab)
    receipts = (f'Source: {esc(", ".join(srcs[:4]))}' if srcs
                else "Receipts: every source linked on the piece")
    # S-17: every lane uses the v3 card. Three used the v2 feature card and two used
    # v3, which is what made one Record look like two.
    left = lane_card_v3(feat, name, stamp=status)
    rows = "".join(
        f'<div class="bd-rec-row"><a class="bd-rec-t" href="/articles/{esc(i["slug"])}.html">'
        f'{esc(i.get("title") or "")}</a>'
        f'<span class="bd-src">{esc(fmt_date(i.get("date")))}</span></div>'
        for i in rest)
    all_href = f"#{esc(slug)}" if page else f"/keepers.html#{esc(slug)}"
    # S3: a lane with a living table leads its read-further list with it. The table is
    # the standing version of everything below it, so it goes first and is labelled as
    # what it is.
    _lt = next((t for t in LIVING_TABLES if t.get("lane") == slug), None)
    if _lt and _lt["slug"] in (tables or set()):
        rows = (f'<div class="bd-rec-row">'
                f'<a class="bd-rec-t" href="/keepers/{esc(_lt["slug"])}.html">'
                f'{esc(_lt["title"])}</a>'
                f'<span class="bd-src">Living table</span></div>') + rows
    right = ""
    if rows:
        right = (f'<div class="bd-card bd-rec-more">'
                 f'<span class="bd-label">More</span>'
                 f'<div class="bd-rec-rows">{rows}</div>'
                 f'<a class="bd-more" href="{all_href}">All {esc(name.lower())}</a></div>')
    return f'<section class="bd-rec-lane" id="{esc(slug)}">{left}{right}</section>'


def _live_tables(items):
    """Which living tables have the rows to render. Same question render_living_table
    asks, so the Record's link and the page itself can never disagree."""
    return {t["slug"] for t in LIVING_TABLES
            if len(_table_rows(t, items)) >= t["min_rows"]}


def record_sections(items, home=True, board=None):
    """The Record: ONE header and one block, five lanes on the homepage in the audit's
    order (Lawsuits and rulings, Discipline, Media rights, Contracts, Fantasy facts),
    every lane on /keepers.html. S-17."""
    by_lane, _picks = _record_inventory(items)
    hub_slugs = {h.get("slug") for h in coverage_hubs(items) if isinstance(h, dict)}
    lanes = "".join(
        (_record_strip(slug, name, by_lane.get(slug) or [], hub_slugs) if home
         else _record_lane(slug, name, by_lane.get(slug) or [], hub_slugs, page=True,
                           tables=_live_tables(items)))
        for slug, name, _tags, on_home in RECORD_LANES
        if (on_home or not home))
    _claimed = {i.get("slug") for v in by_lane.values() for i in v}
    if home and HOME_LEAD_SLUG:
        _claimed.add(HOME_LEAD_SLUG)
    lanes += extra_lanes(items, board, claimed=_claimed, strip=home)
    if not lanes.strip():
        return ""
    head = (f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<h2 class="bd-h2">The Record</h2></div>'
            + (f'<a class="bd-more" href="/keepers.html">All</a>' if home else "")
            + '</div>')
    # S-24's details collapse is gone with the cards it was hiding: the strip is short
    # enough to show every lane, and the page no longer needs a script to have a shape.
    wrap = f'<div class="rs-grid">{lanes}</div>' if home else lanes
    return f'<section class="bd-mod" aria-labelledby="bd-rec">{head}{wrap}</section>'


def record_full_index(items, shown=12):
    """Addendum item 4. The remaining evergreen titles as plain links in three columns,
    so the internal-link count the priority sitemap relies on survives the change from a
    wall of links to a set of lane sections. This replaces the wall, it does not delete
    the links."""
    picks = evergreen_picks(items, n=40)
    rest = picks[shown:]
    if len(rest) < 6:
        return ""
    links = "".join(f'<a href="/articles/{esc(i["slug"])}.html">{esc(i.get("title") or "")}</a>'
                    for i in rest)
    return (f'<section class="bd-mod bd-rec-index">'
            f'<div class="bd-cardtop"><span class="bd-label">More</span>'
            f'<a class="bd-more" href="/keepers.html">All</a></div>'
            f'<div class="bd-rec-cols">{links}</div></section>')


def render_keepers(items, dateline):
    """/keepers.html: every lane, same shape as the homepage sections."""
    body = f"""<main class="wrap"><section class="page">
  <h1 class="sr-only">The Record</h1>
  {record_sections(items, home=False)}
  {record_full_index(items, shown=0)}
</section></main>"""
    return shell(f"The Record - {NAME}",
                 "The desk's standing work, by lane: what each piece establishes and the "
                 "receipts behind it.", "", body, dateline, path="/keepers.html")




def render_home(items, dateline):
    """The GoCheckMySports front door, built for the RETURNING reader: today's headlines,
    the editions, and the storylines the desk is tracking. The brand pitch lives below the
    information, not above it."""
    live = [i for i in (items or []) if not i.get("example") and not _is_wrap(i)]

    # UX-11: one appearance per story per page, and blocks claim in render order, so
    # this has to be the FIRST thing the page does. The first cut reset halfway down,
    # after the desk grid had already claimed, which wiped its claims and let the same
    # story render again below.
    #
    # The band's league panels are excluded deliberately: they are alternate views of
    # the same slot and only one is ever on screen, so a story on the NFL card and the
    # MLB card is not the page saying it twice.
    _page_reset()

    # The front page (owner directive 2026-07-16): a network-style hero mosaic. Several
    # lead stories visible at once with explicit hierarchy (the editor's rank orders them),
    # editions in their own strip below. No carousel: every ranked story is on screen.
    # Daypart re-stack (2026-07-20): home_stack may promote a breaking story to the lead
    # and picks the edition that anchors The Bottom Line square.
    stories, breaking, bl_anchor = home_stack(items)

    # S1 TAKES THE TOP STORY, so the hero mosaic must not print it again. The ledger
    # decides: a lead with checkable figures becomes the receipts card above, and the
    # mosaic starts one story down. Without a ledger there is no lead row and the
    # mosaic leads as it always did.
    # UX-5: the lead is the highest lead value among the top of the editor's rank, not
    # simply the first. The rest of the stack keeps the editor's order.
    _pool = stories[:12]
    _best = max(_pool, key=lambda i: lead_value(i), default=None) if _pool else None
    if _best is not None and lead_value(_best) > 0 and _best is not stories[0]:
        stories = [_best] + [x for x in stories if x is not _best]
    _s1_lead = stories[0] if stories else None
    _s1_ledger = receipts_ledger(_s1_lead) if _s1_lead else ""
    global HOME_LEAD_SLUG
    HOME_LEAD_SLUG = (_s1_lead or {}).get("slug") if _s1_lead else None
    hero_pool = stories[1:] if _s1_lead else stories

    def _hero_tag(item):
        # A-5: the grid's league chip, with a tag the story's own teams contradict
        # removed. This printed "nfl" on a Vanderbilt at NC State recap, on NFL Sunday.
        tags = display_tags(item)
        return f'<span class="tag topic">{esc(tags[0])}</span>' if tags else ""

    desk_html = ""
    if hero_pool:
        stories = hero_pool
        lead = stories[0]
        # S-2: the dark .hero-band is gone - the photo band over hero-poster.webp, the
        # second "Lead story" badge under the one in the lead row above it, and the
        # numbered 02-06 cards. It was the homepage's second hero, arguing with the
        # first. Its stories come here, to the light grid (S-6).
        #
        # D-13: the Bottom Line card is off the homepage. Sprint A rehomed it here
        # rather than delete it, and on the live page it became the first item under
        # "From the desk" at nine lines - which is not the S-6 shape (six light cards,
        # no summary text) and reads as the Edition leading the homepage. The Edition
        # keeps its nav entry, /bottom-line.html keeps the history, and the Edition's
        # homepage presence is one card in this grid, in the same shape as the rest.
        ed_card = ""
        if bl_anchor is not None:
            ed = bl_anchor
            ed_card = (f'<a class="bd-card sp-deskcard sp-deskcard-ed" '
                       f'href="/articles/{esc(ed["slug"])}.html">'
                       f'<span class="bd-cardtop"><span class="bd-eyebrow">'
                       f'The Evening Edition</span></span>'
                       f'<span class="sp-deskcard-h">{esc(_edition_label(ed))}</span>'
                       f'<span class="dateline">{fmt_when(ed)}</span></a>')
        # S-6: six light cards, three across. League label, the desk's badge, the
        # headline clamped at a word boundary, the time in ET. No summary text, so
        # equal heights come from the clamp and not from stretching a short card.
        cards = "".join(
            f'<a class="bd-card sp-deskcard" href="/articles/{esc(i["slug"])}.html">'
            f'<span class="bd-cardtop">{_hero_tag(i)}'
            f'{verdict_badge(i.get("verdict"), i)}</span>'
            f'<span class="sp-deskcard-h">{esc(clamp_words(i.get("title") or "", 96))}</span>'
            f'<span class="dateline">{fmt_when(i)}</span></a>'
            for i in _unused(stories, 6))
        cards = ed_card + cards
        desk_html = (f'<div class="bd-sec"><div class="bd-sec-l">'
                     f'<h2 class="bd-h2">From the desk</h2></div>'
                     f'<a class="bd-more" href="/news.html">All stories</a></div>'
                     f'<div class="sp-deskgrid">{cards}</div>')

    # The Editions: the desk's daily synthesis as its own strip, one card per slot
    # (morning / midday / evening), newest first, never older than the current news cycle.
    # EDITIONS STALENESS (owner directive 2026-07-27, same rule as the featured band):
    # a card older than 24 hours never renders and the strip collapses entirely when
    # nothing fresh exists; the live-dot only ever sits on a fresh card. A July 23
    # brief wearing a live-dot on July 27 slipped through this module.
    _now = _build_now()
    wraps = [i for i in items if _is_wrap(i) and not i.get("example")
             and _fresh_hours(i, _now) <= 24]
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
                f'<a class="edition-card" href="/articles/{esc(w["slug"])}.html">'
                f'<span class="ed-kick">{esc(kick)}{dot}</span>'
                f'<span class="ed-title">{esc(hook.strip())}</span>'
                f'<span class="ed-fact">{esc(fact)}</span>'
                f'<span class="dateline">{_blink_when(w)}</span></a>')
    # Artboard 4 module 3, right rail: the Edition as one card rather than the strip.
    # Built from the newest fresh edition, which is the same source the strip used.
    _edition_card_html = ""
    _fresh_ed = next((x for x in wraps), None)
    if _fresh_ed:
        _kick, _, _hook = (_fresh_ed.get("title") or "").partition(":")
        _edition_card_html = (
            f'<div class="bd-card" style="gap:10px;padding:20px 22px 18px">'
            f'<span class="bd-eyebrow">The Evening Edition</span>'
            f'<div class="bd-h3" style="font-size:20px">'
            f'{esc((_hook or _kick).strip())}</div>'
            f'<p class="bd-read">One read a day over everything the desk published, with '
            f'the scores that settled and the stories that were checked.</p>'
            f'<div class="bd-cta">'
            f'<a class="bd-btn" href="/articles/{esc(_fresh_ed["slug"])}.html">'
            f'{esc(_edition_label(_fresh_ed))}</a>'
            f'<a class="bd-more" href="/bottom-line.html">Past editions</a></div></div>')

    editions_html = ""
    if ed_cards:
        editions_html = (f'<div class="sec-head" style="margin-top:26px"><h2>The Editions</h2>'
                         f'<span class="bar"></span></div>'
                         f'<p class="pc-note" style="margin:0 0 10px">The desk\'s daily synthesis: '
                         f'one evening read over everything published that day.</p>'
                         f'<div class="edition-strip">{"".join(ed_cards)}</div>')

    # Tracking: the narratives watchlist, each chip linking to its latest published chapter.
    # HUB FIRST (consolidation 2026-09-01): a storyline that has earned a /coverage/ hub
    # sends its chip there instead, the stable URL, and the hub shows the newest chapter
    # first anyway. Storylines without a hub keep the newest-chapter behavior unchanged.
    track_html = ""
    chips = []
    _chip_slugs_used = set()
    watch = _watchlist()
    _hub_by_name = {h["name"]: h for h in coverage_hubs(items)}
    _tracking_match = tracking_match
    for n in watch:
        rx = narrative_rx(n)
        if rx is None:
            continue
        # UX-10: the window is checked ONCE, at the top, for both chip sources. The
        # first cut checked it only on the story-matched branch, so a storyline with a
        # coverage hub kept its chip past its window: NFL training camp, NBA free agency
        # and World Cup aftermath all still rendered in Week 2 while MLB trade deadline,
        # which has no hub, correctly disappeared.
        if not _storyline_open(n):
            print(f"tracking: chip {n.get('name')!r} is outside its window; not offered")
            continue
        hub = _hub_by_name.get(n.get("name", ""))
        if hub:
            chips.append(f'<a class="chip" href="/coverage/{esc(hub["slug"])}.html">'
                         f'{esc(n.get("name", ""))}</a>')
            continue
        cands = [i for i in live if not i.get("superseded_by") and _tracking_match(i, rx)]
        cands.sort(key=lambda i: i.get("published_utc") or "", reverse=True)
        hit = cands[0] if cands else None
        # ONE ARTICLE, ONE CHIP (2026-08-25): two labels on one story reads as a wiring
        # error ("NFL training camp" and "NBA free agency" both landed on one Lions
        # injury story). First storyline to claim an article keeps it; a later chip
        # resolving to the same slug is dropped, and a dropped chip is honest where a
        # mislabeled one is not.
        if hit and hit.get("slug") in _chip_slugs_used:
            print(f"tracking: chip {n.get('name')!r} skipped; its newest match "
                  f"{hit.get('slug')!r} already carries another chip")
            hit = None
        if hit:
            _chip_slugs_used.add(hit.get("slug"))
            # BUILD GATE (owner directive 2026-07-27): a chip whose target does not
            # carry its storyline fails the build rather than shipping a mislink.
            if not _tracking_match(hit, rx) or hit.get("superseded_by"):
                raise SystemExit(f"tracking chip mismatch: {n.get('name')} -> {hit.get('slug')}")
            chips.append(f'<a class="chip" href="/articles/{esc(hit["slug"])}.html">'
                         f'{esc(n.get("name", ""))}</a>')
    if chips:
        # copy item 18: "Storylines", six chips, "All". The tagline under the chips
        # ("the storylines the desk is following") survived the first copy pass and
        # shipped on the live homepage; it is a section describing itself (C-L1).
        track_html = (f'<div class="tracking"><span class="lab">Storylines</span>'
                      f'{"".join(chips[:6])}'
                      f'<a class="chip chip-all" href="/news.html">All</a>'
                      f'<i class="tracking-br"></i></div>')

    # S1, Artboard 4 module 3: the lead story with its receipts ledger, and beside it
    # the charted receipts and the Edition. The ledger is only rendered for a story
    # that actually carries checkable figures with an attribution the story made; see
    # receipts_ledger. Without one the lead keeps its normal shape and the row shows
    # the Edition alone, rather than an empty ledger frame.
    lead_row = ""
    global ALL_ITEMS
    ALL_ITEMS = items
    _lead, _ledger = _s1_lead, _s1_ledger
    # D-5: the row renders whenever there is a lead story. It used to require a receipts
    # ledger too, so on a day whose top story carried none the lead card AND the whole
    # rail vanished - Where to Watch, Fantasy tonight and the storylines with it - and
    # the Bottom Line paragraph led the homepage instead. A fantasy card cannot depend on
    # whether an unrelated story happens to have receipts.
    if _lead:
        _lt = tags_for(_lead)
        # S-4: no body paragraph on the homepage - that was the source of the lead
        # card's ~400px of body text. The DEK is authored by the writer, so it is not cut
        # either (punch item 9, and the standing law): it renders whole and the card
        # takes the height it needs. The row is align-items:stretch, so the rail follows.
        _dek = " ".join((_lead.get("dek") or "").split())
        _left = (f'<div class="bd-card sp-lead">'
                 f'<div class="bd-cardtop"><span class="bd-eyebrow">Lead story</span>'
                 f'{f"<span class=bd-stamp>{esc(_lt[0])}</span>" if _lt else ""}'
                 f'{_breaking_badge(_lead)}'
                 f'{verdict_badge(_lead.get("verdict"), _lead)}</div>'
                 f'<a class="sp-lead-h" href="/articles/{esc(_lead["slug"])}.html">'
                 f'{esc(_lead.get("title") or "")}</a>'
                 + (f'<p class="sp-lead-dek">{esc(_dek)}</p>' if _dek else "")
                 + (_ledger or _also_today(stories))
                 + f'<div class="bd-brief-foot"><span class="bd-by">Chuck Wando</span>'
                   f'<a class="bd-more" href="/articles/{esc(_lead["slug"])}.html">'
                   f'Read the story</a></div></div>')
        # S-3: the rail rendered <div class="sp-rail"></div> whenever the receipts
        # chart and the edition card both came back empty - a blank third of the page
        # beside the lead. It carries the three cards the audit specifies now, and a
        # rail with nothing in it collapses the row to one column rather than shipping
        # an empty one.
        # M-9 (H-14): the Where to Watch card is off the homepage. Its button is on
        # every game card and its page is in the nav, so the rail was carrying a third
        # copy of the same fixtures and a game appeared three times above the fold.
        _rail_cards = [c for c in (_fantasy_tonight_card(SB_DATA, IA_BOARD, IA_DESIG),
                                   track_html) if c]
        if _rail_cards:
            # N-4: the rail sits in a box whose own content height is zero (the rail
            # inside it is absolutely placed), so the grid row is sized by the lead
            # card alone. The rail stretches to that height and clips; it never
            # stretches the lead. On phone the row is one column and the box goes back
            # to normal flow.
            lead_row = (f'<section class="sp-leadrow">{_left}'
                        f'<div class="sp-railbox">'
                        f'<div class="sp-rail">{"".join(_rail_cards)}</div></div></section>')
            track_html = ""     # the rail is carrying the storylines now
        else:
            lead_row = f'<section class="sp-leadrow sp-leadrow-1col">{_left}</section>'


    # S-3: .sp-w2wrow is retired. Where to watch and the storylines both moved up into
    # the lead rail, and a row that renders neither is a row with nothing to render.
    w2w_row = ""

    # The Bottom Line lives in the hero square beside the lead (owner call 2026-07-16);
    # the standalone band below is retired on home. /bottom-line.html keeps the history.
    # The live layer rides above the fold, before the editorial page begins.
    # S-A: the band is the product and it sits directly under the masthead. The old
    # ticker strip stays available for pages that are not the front door.
    # H-7: no fallback. The band renders the last snapshot, marked stale when it is,
    # and renders nothing at all when there is no snapshot to render. The old strip and
    # its copy are deleted: "League data, not news" was a sentence about the site, and
    # a reader meeting a different component at 8 AM than at 8 PM learns nothing from
    # the swap.
    _band = scoreboard_band(SB_DATA, IA_BOARD, WX_DATA)
    body = _band + f"""<main class="wrap"><section class="page">
  {lead_row}
  {desk_html}
  {w2w_row}
  {track_html}
  {record_sections(items, home=True, board=IA_BOARD)}
</section></main>"""
    return shell(f"{FAMILY} - Sports, checked.", FAMILY_DESC, "Home", body, dateline, path="/", schema_extra=home_schema())


def render_archive(items, dateline):
    live = [i for i in items if not i.get("example") and not i.get("superseded_by")]
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
    # Full coverage: the hub layer, listed compactly ahead of the day-by-day listing so
    # a researcher chasing one storyline never has to walk the whole archive for it.
    hubs = coverage_hubs(items)
    hub_html = ""
    if hubs:
        hub_html = ('<div class="sec-head"><h2>Full coverage</h2><span class="bar"></span></div>'
                    '<div class="tracking">'
                    + "".join(f'<a class="chip" href="/coverage/{esc(h["slug"])}.html">'
                              f'{esc(h["name"])}</a>' for h in hubs)
                    + '</div>')
    body = f"""<main class="wrap"><h1 class="sr-only">GoCheckMySports archive</h1><section class="sec">
    {hub_html}
    <div class="sec-head"{' style="margin-top:22px"' if hub_html else ''}><h2>Archive</h2><span class="bar"></span></div>
    {inner}
  </section></main>"""
    return shell(f"Archive - {NAME}", "Every published GoCheckMySports story.", "Archive", body,
                 dateline, path="/archive.html")


# ---- section hubs ------------------------------------------------------------

# THE DESK'S LANES (owner decision 2026-08-25). Search Console showed 105 pages indexed,
# zero clicks ever, and impressions scattered across unrelated topics: Google had no idea
# what this site is about. The fix is a topical identity, and the honest version of that
# is the lanes the desk ALREADY OWNS, measured across 325 published stories, not the lanes
# it might wish it covered. Sports lanes are league-shaped because that is how sports
# readers navigate; these four carry 25%, 23%, 11% and 12% of published stories.
#
# Deliberately additive and reversible: this changes how the existing corpus is ORGANISED,
# not what the desk publishes. Narrowing the editorial mix is a bigger bet that should
# follow evidence these hubs help, and unlike a hub, a narrowed archive cannot be undone.
# (slug, page title, nav label, tags, blurb)
SECTIONS = [
    ("nfl", "NFL", "NFL", ("nfl",),
     "Roster moves, injury reports and league business, sourced to official reports and "
     "on-record statements."),
    ("soccer", "Soccer", "Soccer", ("soccer",),
     "Transfers, results and governance across the major competitions."),
    ("mlb", "MLB", "MLB", ("mlb",),
     "Trades, injuries and results, checked against official league data."),
    ("nba", "NBA", "NBA", ("nba",),
     "Signings, trades and results from the NBA and WNBA."),
    # COLLEGE FOOTBALL HAS ITS OWN LANE (owner directive 2026-08-29). The desk carried a
    # college TAG but no section, so the sport with the largest audience in the American
    # calendar had nowhere to live on the site while its season opened. The lane covers
    # the year-round story too, not just Saturdays: eligibility rulings, the transfer
    # portal, NIL and conference realignment are where this sport's real news happens.
    # College Football consumes the umbrella too, so governance, athletic directors, NIL
    # and conference politics keep the home they already had. College Basketball consumes
    # only its own tag, which is what stops a basketball story reaching the football front.
    ("college-football", "College Football", "College Football",
     ("college-football", "college"),
     "Games, eligibility rulings, the transfer portal, NIL and conference realignment, "
     "sourced to official statements and the record."),
    ("college-basketball", "College Basketball", "College Basketball",
     ("college-basketball",),
     "The tournament, the polls and the portal, sourced to official brackets and "
     "on-record statements."),
    ("tennis", "Tennis", "Tennis", ("tennis",),
     "Slam draws, tour results, injuries and the business of the sport, sourced to "
     "official draws and on-record statements."),
    ("wnba", "WNBA", "WNBA", ("wnba",),
     "Signings, trades, injuries and results across the league."),
    ("nhl", "NHL", "NHL", ("nhl",),
     "Trades, injuries and results, checked against official league data."),
    # ONE LANE FOR THE SPORTS THAT CANNOT FILL ONE EACH. Golf, cycling, cricket, combat
    # sports and athletics are each too thin for a nav slot and each strongly seasonal, so
    # separately they would produce empty fronts out of season. Together they are a real
    # section with year-round coverage.
    ("more-sports", "More Sports", "More Sports",
     ("combat sports", "golf", "cycling", "cricket", "athletics"),
     "Boxing and MMA, golf, cycling, cricket and athletics."),
    # THE SECOND AXIS (2026-09-04). These are story TYPES, not sports, and they are what
    # guarantees no story is unreachable: 20 of the 24 stories that reached no lane are a
    # result, an injury or a signing in a sport with no section of its own. They are real
    # pages for that reason, and they are deliberately NOT in the lane rail, because two
    # global rails on a phone is the clutter the rail work just removed. They surface as a
    # compact row on the homepage and on every section front instead.
    ("scores", "Scores &amp; Results", "Scores", ("scores-results",),
     "Final scores and what they settled, checked against official league data."),
    ("injuries", "Injuries", "Injuries", ("injuries",),
     "Who is hurt, how long for, and what the club has actually confirmed."),
    ("transactions", "Transactions", "Transactions", ("transactions",),
     "Signings, trades, extensions and waivers across every league the desk covers."),
]

# The second axis, kept out of the lane rail but present in NAV so the unreachable-section
# guard still sees them. masthead() filters both this and NAV_UTILITY.
NAV_CROSSCUT = frozenset({"Scores section", "Injuries", "Transactions"})


# A LANE THE READER CANNOT CLICK DOES NOT EXIST (owner audit 2026-08-29). SECTIONS and
# NAV are separate hand-maintained lists, which is exactly how the news desk shipped an
# archive page nothing linked to. This fails the import rather than the deploy, so the
# mismatch is caught the moment someone adds a lane and forgets the nav.
# Not lanes. Present in NAV so the unreachable-section guard still sees the whole map,
# but filtered out of the rail; they render in the masthead and the footer instead.
# Set at build once where_to_watch has reported. False keeps its nav entry off.
W2W_LIVE = False
W2W_DATA = None      # set at build by where_to_watch.load()
HOME_LEAD_SLUG = None  # set at build: the homepage lead, so the Record cannot repeat it
EDITION_HREF = None  # set at build: the newest dated edition (S-1 nav)
IA_BOARD = None      # set at build by inactives.board()
IA_DESIG = None      # set at build by inactives.designations()
SB_DATA = None       # set at build by scoreboard.load()
LINES_DATA = None    # set at build by lines.log(): the line at open per game
WX_DATA = None       # set at build by kickoff_weather.load()
LIVE_POINTS = {}     # set at build: fantasy points per game id, for live/final cards
LIVE_WP = {}         # set at build: ESPN's win probability, LIVE games only (C-3)
ALL_ITEMS = []       # set at build: the published story pool the card story line draws
                     # from (SC-7). The Wire replaces this source in Sprint I; the
                     # matching rule does not change.

NAV_UTILITY = frozenset({"Latest", "Sources"})   # N-1: Home is a nav item now

_nav_hrefs = {h for _l, h in NAV}
_unreachable = [slug for slug, *_rest in SECTIONS
                if f"/sections/{slug}.html" not in _nav_hrefs]
if _unreachable:
    raise SystemExit("site_build: section(s) missing from NAV and therefore unreachable: "
                     + ", ".join(_unreachable))


def section_items(items, tags):
    """Live stories in a lane, newest first. A story can appear in more than one lane;
    that is honest, a court ruling about a wildfire evacuation belongs in both."""
    want = set(tags)
    return [i for i in items
            if not i.get("example") and not i.get("superseded_by") and not _is_wrap(i)
            and want & set(tags_for(i))]


def crosscut_row(items, active=None):
    """The second axis, as a compact row rather than a second global rail.

    Every story on this desk is a result, an injury, a signing or none of those, and that
    cut runs ACROSS the leagues rather than beside them. It is what guarantees the desk has
    no unreachable stories: 20 of the 24 that reached no lane are a result, an injury or a
    signing in a sport with no section of its own.

    It is a row and not a rail on purpose. A second sticky rail is two rows of chrome above
    the news on a phone, which is exactly the clutter the lane rail was cleaned up to avoid.
    This renders inline, once, under the section head, and carries its own counts so a
    reader can see there is something behind each link before spending a tap.
    """
    out = []
    for slug, title, nav_label, tags, _blurb in SECTIONS:
        if nav_label not in NAV_CROSSCUT:
            continue
        n = len(section_items(items, tags))
        if not n:
            continue
        cls = " class=\"xc-on\"" if nav_label == active else ""
        out.append(f'<a href="/sections/{slug}.html"{cls}>{esc(nav_label)}'
                   f'<span class="xc-n">{n}</span></a>')
    if not out:
        return ""
    return ('<nav class="xcut" aria-label="Across every league">'
            + "".join(out) + '</nav>')


def render_section(slug, title, nav_label, tags, blurb, items, dateline):
    live = section_items(items, tags)
    drop = set(tags or ()) | {slug, nav_label, title}
    if live:
        inner = ('<div class="grid">'
                 + "".join(card(i, drop) for i in live[:60]) + "</div>")
        if len(live) > 60:
            inner += (f'<p class="fine">Showing the 60 most recent of {len(live)} stories in '
                      f'this section. <a href="/archive.html">The full archive</a> has the rest.</p>')
    else:
        inner = ('<div class="empty"><span class="k">Nothing here yet</span>'
                 '<p style="margin:.6em 0 0">No published stories carry this section yet.</p></div>')
    plain = title.replace("&amp;", "and")
    body = f"""<main class="wrap"><h1 class="sr-only">{esc(plain)}</h1><section class="sec">
    <div class="sec-head"><h2>{title}</h2><span class="bar"></span>
      <span class="sec-n">{len(live)} {"story" if len(live) == 1 else "stories"}</span></div>
    {crosscut_row(items, nav_label)}
    {inner}
  </section></main>"""
    # nav_label, not the page title: shell() marks the nav item whose label matches,
    # so passing "Disasters and Weather" left the reader with no active-state anywhere
    return shell(f"{plain} - {NAME}", blurb, nav_label, body, dateline,
                 path=f"/sections/{slug}.html")


def _name_mid_sentence(name):
    # "League discipline" reads as "league discipline" inside a sentence; a name led by
    # an acronym ("NFL training camp") or carrying a proper noun ("World Cup aftermath")
    # keeps its caps
    first = (name.split() or [""])[0]
    if name[:1].isupper() and not first.isupper() and not any(c.isupper() for c in name[1:]):
        return name[0].lower() + name[1:]
    return name


def render_coverage_hub(hub, dateline):
    """One /coverage/ page per hub-worthy storyline: every published chapter, newest
    first, on a stable URL. This is the evergreen page the aging sitemap consolidates
    crawl attention into; the section pages organize by league, this layer organizes by
    storyline."""
    name = hub["name"]
    # The description still goes to the tab and to search; the page itself carries the
    # name and the count, the same law the section pages follow.
    intro = (f"Every story the desk has published on {_name_mid_sentence(name)}, "
             f"newest first.")
    n = len(hub["stories"])
    inner = '<div class="grid">' + "".join(card(i) for i in hub["stories"]) + "</div>"
    body = f"""<main class="wrap"><h1 class="sr-only">{esc(name)}</h1><section class="sec">
    <div class="sec-head"><h2>{esc(name)}</h2><span class="bar"></span>
      <span class="sec-n">{n} {"story" if n == 1 else "stories"}</span></div>
    {inner}
  </section></main>"""
    return shell(f"{name}: full coverage - {NAME}", intro, "Full coverage", body, dateline,
                 path=f"/coverage/{hub['slug']}.html")


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
  <h1>How we work</h1>
  <p class="lede">The standards this desk holds itself to, and the things it does not do.</p>

  <h2>What we aim for</h2>
  <ul>
    <li><b>Sources you can check.</b> Stories link the material they draw on, and official
        data such as league results, schedules and on-record club statements carries more
        weight here than anyone's account of it.</li>
    <li><b>A second look before publication.</b> Stories are checked against the sources they
        cite, by a pass separate from the one that assembled them. Work that does not hold up
        is held back or dropped rather than smoothed over.</li>
    <li><b>Reports stay reports.</b> An unconfirmed signing, trade or injury is labelled as a
        report and attributed to whoever reported it.</li>
    <li><b>One event, one story.</b> The same news carried by many outlets is treated as one
        story, so a loud story does not look like ten of them.</li>
    <li><b>Human oversight.</b> A human editor-in-chief oversees the desk, can hold or remove
        anything, and owns the opinion and analysis published here.</li>
  </ul>

  {ex_html}

  <h2>What we do not do</h2>
  <ul>
    <li>Work that does not hold up is held back rather than published.</li>
    <li>We do not advise bets. We report events and explain what they may mean, never what
        to wager on.</li>
    <li>We do not report an injury from anything but an official report or an on-record
        statement. Speculation about an athlete's body is not news.</li>
    <li>We do not run paid coverage as news. Sponsored items are the thing we are built to
        strip out.</li>
    <li>We do not put an opinion in a voice that did not hold it. Takes, analysis, and
        corrections are human work, always.</li>
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

  <h2>How a story gets published</h2>
  <p>A story runs only when an independent verification pass confirms it against its sources, and
     every source is linked so you can check the work yourself. A human editor-in-chief oversees the
     desk, can hold or remove anything, and owns every take: no opinion ever goes out in a human
     voice unless a human wrote it. If that standard ever slips, we drop the cadence before we drop
     the standard.</p>

  <h2>Our bias</h2>
  <p>We are biased toward the reader and against the rumor mill. We weight official league data
     and on-record sources most, we link every source, and we would rather publish nothing on a
     given day than publish something we cannot stand behind.</p>

  <h2>What we are not</h2>
  <p>We are not a sportsbook, a tout service, or a picks column, and nothing here is betting or
     gambling advice. We report what happened and, carefully, what it may mean. What you do with
     that is yours.</p>

  <h2>Contact the desk</h2>
  <p class="operator">This website is operated by Go Check My Brands LLC, a South Carolina limited liability company. Contact: hello@gocheckmysports.com.</p>
  <p>Tips, corrections, and questions: <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a>.</p>
  <p>Sponsorship inquiries: <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a>.
     Sponsorship never buys coverage; see <a href="/method.html">how we work</a>.</p>

  <div class="callout"><b>Read next:</b> <a href="/method.html">How we work</a>, the
    the standards every story has to clear. Or <a href="/standards.html">our standards and
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
  <p>Stories link the sources they draw on. We give more weight to official data such as
     league results, schedules and on-record club statements than to commentary about them,
     and a claim resting on a single weak source is labelled as unconfirmed or left out.</p>

  <h2>Verification</h2>
  <p>Stories are checked against the sources they cite by a pass separate from the one that
     assembled them. Work that does not hold up is labelled clearly for the reader or held
     back. We would rather be slow than wrong.</p>

  <h2>Lines</h2>
  <p>Where a game carries a betting line, this desk shows it as it was reported: the
     spread, the total and the moneyline as one provider published them, with that
     provider named beside the number. A line is a fact about what a company was
     offering at a moment, and it is shown for the same reason a kickoff time or a
     weather reading is shown.</p>
  <p>The desk does not make picks, does not advise anyone to bet, does not publish
     forecasts or win probabilities of its own, and carries no link to a sportsbook. A
     line that arrives without a provider is not published at all, because an
     unattributed number would read as this desk's estimate, and this desk does not
     estimate.</p>
  <p>Two things follow from a line being a reading at a moment. When a line moves, the
     card shows where it opened beside where it is now, both from the same provider, and
     the opening figure is whatever was published the first time this desk saw the game:
     the feed does not keep it, so the desk logs it. And once a game is final, the card
     states whether the favourite covered and whether the total went over. That is
     arithmetic on the score and on that provider's number, attributed to them, and it
     is not a judgement on anyone's wager.</p>
  <h2>Models</h2>
  <p>A live game may carry a win probability. It is one model's reading, the model is
     named on the row, and it is shown for the same reason and under the same rule as a
     line: it is a fact about what that model said at that moment, not a forecast this
     desk makes. The desk builds no model, tunes none, and averages none together.</p>
  <p>It appears only while a game is in play. When a game ends, the model's last reading
     is a hundred per cent for the team that won, which restates the result as a
     percentage, so the desk does not show it. And it always names the side it refers
     to, because a bare percentage beside two team names is the one number on a page
     that can be read exactly backwards.</p>

  <h2>Oversight</h2>
  <p>A human editor-in-chief oversees the desk, can hold or remove anything, and owns the
     opinion and analysis published here.</p>

  <h2>Never betting advice</h2>
  <p>We report events and explain what they may mean. We never advise bets, picks, or wagers of
     any kind. Nothing on this site is betting, gambling, financial, or legal advice.</p>

  <h2>Corrections</h2>
  <p>When we get something wrong, we fix it and say so on the story. If you spot an error, email
     <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a> and we will check it
     against the source. Corrections are made promptly and noted on the story itself. A correction
     is a feature of an honest desk, not a failure.</p>

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

  <p class="operator">This website is operated by Go Check My Brands LLC, a South Carolina limited liability company. Contact: hello@gocheckmysports.com.</p>

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
  <p>Typefaces are served from this site. Your browser makes no request to Google, or to any
     other font host, when a page loads.</p>

  <h2>Links out</h2>
  <p>Stories link their sources. Once you leave this site, the site you land on operates
     under its own privacy policy.</p>

  <h2>Contact and data requests</h2>
  <p>Questions about this policy, your data, or the newsletter, including unsubscribe requests:
     <a href="mailto:desk@gocheckmysports.com">desk@gocheckmysports.com</a>. A human reads it.
     If you want to know what we hold about you (for subscribers, that is your email address)
     or want it deleted, email the same address and we will handle it promptly.</p>

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

  <p class="operator">This website is operated by Go Check My Brands LLC, a South Carolina limited liability company. Contact: hello@gocheckmysports.com.</p>

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
     primary sources before you act on it. When we get something wrong, we correct it and note
     the correction on the story; our <a href="/standards.html">standards and corrections
     policy</a> explains how to report an error.</p>

  <h2>Links to other sites</h2>
  <p>Every story links its sources, and those links lead to sites we do not control. We are not
     responsible for the content, accuracy, availability, or policies of any external site.
     A link is a citation, not an endorsement.</p>

  <h2>Our content and yours</h2>
  <p>The original text on this site (our stories, daily editions, and page copy) is
     &copy; {YEAR} Go Check My Brands LLC. You may quote it with attribution and a link. Headlines,
     reporting, and data from the outlets and leagues we cite remain the property of their
     owners; we summarize in our own words and link to the original rather than reproduce it.</p>

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
     We do not sell your email, and you can unsubscribe anytime. Back to the
     <a href="/index.html">front page</a>.</p>
</section></main>"""
    return shell(f"Subscribed - {NAME}", "Thanks for subscribing.", None, body, dateline,
                 path="/thanks.html", noindex=True)



# ---- publish-door helpers ----------------------------------------------------

OUTLET_NAMES = {
    "espn.com": "ESPN",
    "bbc.co.uk": "BBC Sport", "bbc.com": "BBC Sport",
    "cbssports.com": "CBS Sports",
    "theguardian.com": "Guardian Sport",
    "sports.yahoo.com": "Yahoo Sports", "yahoo.com": "Yahoo Sports",
    "mlb.com": "MLB.com",
    "nhl.com": "NHL.com",
    "thesportsdb.com": "TheSportsDB",
}


def outlet_name(url):
    """Display name for a cited URL (the writer hands ingest bare URLs; a Sources list
    of raw URLs is unreadable and hides the outlet). Falls back to the domain."""
    from urllib.parse import urlparse
    host = (urlparse(url).netloc or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for dom, name in OUTLET_NAMES.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host or url


def story_shape_problems(item):
    """Deterministic publish-door belt: a malformed story is held with a named reason,
    never silently published. Soft gaps (key_fact, bottom_line) only warn: a thin but
    sound story still ships."""
    hold, warn = [], []
    for k in ("title", "dek"):
        if not str(item.get(k) or "").strip():
            hold.append(f"empty {k}")
    if item.get("title") == "Untitled":
        hold.append("placeholder title")
    if not [x for x in (item.get("body") or []) if str(x).strip()]:
        hold.append("empty body")
    if not item.get("sources"):
        hold.append("no sources")
    import re as _re
    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", str(item.get("date") or "")):
        hold.append(f"malformed date {item.get('date')!r}")
    if not _re.match(r"^[a-z0-9-]{8,}$", str(item.get("slug") or "")):
        hold.append(f"malformed slug {item.get('slug')!r}")
    for k in ("key_fact", "bottom_line"):
        if not str(item.get(k) or "").strip():
            warn.append(f"empty {k}")
    return hold, warn


def _title_words(t):
    import re as _re
    # crude singular merge: "strike"/"strikes" and "test"/"tests" must count as the
    # same word (2026-07-22: a same-day Iran rewrite scored 0.625 against its twin
    # because plural variants split the overlap)
    return {w[:-1] if w.endswith("s") and not w.endswith("ss") else w
            for w in _re.findall(r"[a-z]{4,}", (t or "").lower())}


# Words that carry no subject. Two titles sharing only these share nothing: "trade"
# paired a Toronto Tempo signing with a Yankees reliever, "game" and "wnba" paired a
# spectator ban with an ejection, "after" paired a WNBA fine with an unrelated press
# comment. All three retired a correct story. Month, weekday and slot names are here
# for the same reason: titles on this desk carry a "(September 2)" date suffix, so
# "september" was the ONLY shared word holding up the Clippers/Daktronics supersede,
# the flagship case this patch exists to stop. A date stamp is not a subject.
GENERIC_TITLE_WORDS = frozenset("""
about after against amid among announce announced announces before being between
called case cases change changes claim claims comment comments could deal deals
decision decisions during first following found from group groups have holds into
issue issues just latest league leave leaves major make makes month months more
most move moves near need needs never next official officials only open opens
order orders over part people plan plans police president press report reported
reports return returns rules ruling said says second sets several since some
start starts state states still take takes team teams that their them then there
these they third this those three time times told took total under until update
updates used using week weeks what when where which while will with without
work works would year years game games season seasons player players coach
coaches trade trades sign signs signed win wins loss losses
january february march april june july august september october november december
monday tuesday wednesday thursday friday saturday sunday
morning afternoon evening night today tonight tomorrow yesterday weekend daily
""".split())


def _subject_words(t):
    """Title words that actually name a subject."""
    return _title_words(t) - GENERIC_TITLE_WORDS


# A word this desk uses all season names a recurring actor, not a story. Computed from
# the corpus so it stays current without anyone maintaining it: a subject word carried by
# 2% or more of published titles (and by at least 4 of them, so a young corpus does not
# flag its whole vocabulary) cannot on its own establish that two stories are one event.
RECURRING_MIN_SHARE = 0.02
RECURRING_MIN_COUNT = 4
_RECURRING_CACHE = {}


def _recurring_subjects(content_dir):
    hit = _RECURRING_CACHE.get(content_dir)
    if hit is not None:
        return hit
    counts, n = {}, 0
    for fn in sorted(os.listdir(content_dir)) if os.path.isdir(content_dir or "") else []:
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        try:
            d = json.load(open(os.path.join(content_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        if d.get("example") or str(d.get("id") or "").startswith("wrap-"):
            continue
        t = d.get("title") or ""
        if not t:
            continue
        n += 1
        for w in _subject_words(t):
            counts[w] = counts.get(w, 0) + 1
    out = frozenset(w for w, k in counts.items()
                    if k >= RECURRING_MIN_COUNT and n and k / n >= RECURRING_MIN_SHARE)
    _RECURRING_CACHE[content_dir] = out
    return out


def supersede_ok(old_title, new_title, old=None, new=None, content_dir=None):
    """True when the new story may RETIRE the old one from every listing page.

    Retirement is the strong claim: it makes the old page unreachable except by its
    direct URL, forever. It is right for a replacement (one event, told better) and
    wrong for a follow-up. So it needs evidence, and the failure mode is deliberately
    benign: a pair that fails this still publishes and still cross-links as a lineage,
    it just leaves both chapters reachable. Two live cross-linked pages is a small cost.
    A correct story nobody can reach is the failure a reader actually notices.

    Two ways to clear it, and BOTH require shared subject matter, which is the part the
    old code had no notion of:
      - the titles overlap on subject words by a third or more, or
      - dedupe agrees the two are one event AND they share at least one subject word.
    The second conjunct is what stops the Clippers case: dedupe called that pair one
    event, and the titles share literally nothing."""
    a, b = _subject_words(old_title), _subject_words(new_title)
    if not a or not b:
        return False
    shared = a & b
    if not shared:
        return False
    if len(shared) / min(len(a), len(b)) >= 0.34:
        return True
    if old is not None and new is not None:
        # THE DEDUPE BRANCH NEEDS A REAL SUBJECT, NOT A REGULAR CAST MEMBER. dedupe called
        # the Clippers and Daktronics stories one event; it will do the same for two
        # unrelated FIFA rulings or two unrelated Trump stories, because on this chassis
        # same_event is grep-class too. So the shared word that carries this branch has to
        # be one that actually distinguishes the pair. If every word they share is one the
        # desk prints all season, the pair links as a lineage instead of one deleting the
        # other, and both stay reachable.
        if not (shared - _recurring_subjects(content_dir or CONTENT)):
            return False
        try:
            import dedupe
            return bool(dedupe.same_event(old_title, old.get("key_fact", ""),
                                          new_title, new.get("key_fact", "")))
        except Exception:
            return False
    return False


def find_superseded(title, declared_title, content_dir, hours=96, item=None):
    """(slug, relation) for an existing story this new one follows, or (None, None).
    relation is "supersede" (retire the old page) or "chain" (keep both, cross-linked).

    Two detectors: the editor's explicit declaration (exact title match from its shelf:
    catches the same event under a rewritten angle) and a deterministic word-overlap
    backstop (>=70% of meaningful title words: catches near-identical republication that
    slips past every model). A declaration that does not clear supersede_ok is not
    discarded, it is DOWNGRADED to a chain: the editor saw a connection, and the honest
    rendering of a connection the desk cannot verify is a link, not a deletion.
    Editions and examples are never superseded."""
    import datetime as _dt
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)).isoformat()
    nw = _title_words(title)
    best = None
    for fn in sorted(os.listdir(content_dir)) if os.path.isdir(content_dir) else []:
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        try:
            d = json.load(open(os.path.join(content_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        if d.get("example") or "brief" in (d.get("kind") or "") and d.get("id", "").startswith("wrap-"):
            continue
        if d.get("id", "").startswith("wrap-") or d.get("category") == "daily edition":
            continue
        if (d.get("published_utc") or "") < cutoff or d.get("superseded_by"):
            continue
        t = d.get("title") or ""
        if declared_title and t.strip() == declared_title.strip():
            if supersede_ok(t, title, d, item, content_dir):
                return d.get("slug"), "supersede"
            print(f"::warning::supersede: the editor declared this story an update of "
                  f"{(d.get('slug') or '')[:60]!r}, but the two share no subject; "
                  f"linking them as a lineage instead of retiring the earlier story")
            return d.get("slug"), "chain"
        tw = _title_words(t)
        if nw and tw:
            overlap = len(nw & tw) / min(len(nw), len(tw))
            # same-day rewording is almost always the same event; a cross-day match
            # must clear the stricter bar (day N of a running story is a genuinely
            # different chapter and belongs to the editor's declared-update path)
            import datetime as _dt
            same_day = (d.get("published_utc") or "")[:10] ==                 _dt.datetime.now(_dt.timezone.utc).date().isoformat()
            if overlap >= (0.5 if same_day else 0.7):
                best = d.get("slug")
    return (best, "supersede") if best else (None, None)


def mark_continued(content_dir, old_slug, new_slug):
    """Point the earlier chapter forward WITHOUT retiring it. The counterpart to
    mark_superseded for a lineage: both stories stay on every listing page, and a reader
    who lands on the earlier one is told where the storyline went next."""
    for fn in os.listdir(content_dir):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(content_dir, fn)
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("slug") == old_slug:
            d["continued_by"] = new_slug
            json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
            return True
    return False


def mark_superseded(content_dir, old_slug, new_slug):
    """Rewrite the superseded story's JSON so the homepage retires it and its page
    points forward. Content files are pipeline-owned; this is the one sanctioned
    mutation (the update chain)."""
    for fn in os.listdir(content_dir):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(content_dir, fn)
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if d.get("slug") == old_slug:
            d["superseded_by"] = new_slug
            json.dump(d, open(path, "w", encoding="utf-8"), indent=2)
            return True
    return False


# ---- ingest approved payloads -----------------------------------------------


# ---- one event, one URL (ported from the crypto desk, root-cause fix 2026-08-30) ----
#
# WHY THE DUPLICATES KEPT COMING BACK despite every guard added in August: all of those
# guards block a retelling that adds NOTHING, and a real newsroom's second telling almost
# always adds SOMETHING: a fuller figure, one more source, the afternoon's extra detail.
# On this desk such a story passed every gate BY DESIGN and minted a second URL for the
# same event. The crypto desk has had the missing piece since mid-August, which is exactly
# why its duplicate rate collapsed while this desk kept accumulating them: a same-event
# retelling MERGES INTO THE EXISTING URL instead of becoming a new page. This is that
# piece, ported with every scar it earned there:
#   - same_event alone is a candidate filter, never the verdict: it once paired a Kalshi
#     lawsuit with a Tether earnings report, and later a BankChain alliance with a Roman
#     Storm retrial. Merging also requires _same_storyline, real content overlap on a
#     shared subject.
#   - a better-sourced retelling REPLACES the prose (leaving the thinner telling standing
#     is how an overstatement outlives its own correction); an equal-or-weaker retelling
#     only contributes its sources.
#   - on an upgrade the citations REPLACE rather than union: the displaced sources were
#     verified against text that no longer exists on the page.

_STORY_STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with",
               "from", "as", "at", "its", "it", "that", "this", "after", "over", "amid",
               "says", "said", "new", "first", "report", "reports",
               # A DATE IS NOT A SUBJECT (2026-08-30). On the general-news corpus the
               # ported storyline test merged "Yayoi Kusama dies at 97" into "King
               # Harald V dies at 89": their ONLY shared capitalized token was
               # "August", from the datelines in both key facts, and with a shared
               # "name" in hand the 0.22 overlap floor was reachable on "dies"/"died"
               # alone. Months, weekdays and the day's other furniture words carry no
               # subject identity, and neither do the verbs of dying, which every
               # obituary shares by construction.
               "january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december",
               "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
               "sunday", "today", "yesterday", "tomorrow", "week", "month", "year",
               "dies", "died", "dead", "death", "age", "aged", "his", "her", "their",
               "officials", "authorities", "federal", "state", "u.s", "u.s.", "us",
               # league acronyms are beats, not events: "MLB" was the only shared name
               # between a Cardinals game story and a Tommy John obituary
               "mlb", "nfl", "nba", "nhl", "wnba", "ncaa"}


def _content_words(*texts):
    out = set()
    for t in texts:
        out |= {w for w in re.findall(r"[a-z][a-z0-9.]{2,}", (t or "").lower())
                if w not in _STORY_STOP}
    return out


def _proper_nouns(*texts):
    out = set()
    for t in texts:
        out |= {w.lower() for w in re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}", t or "")
                if w.lower() not in _STORY_STOP}
    return out


def _same_storyline(a, b, names_floor=0.22):
    """True when two stories visibly share a subject, by their own words."""
    at, bt = a.get("title") or "", b.get("title") or ""
    ak, bk = a.get("key_fact") or "", b.get("key_fact") or ""
    aw, bw = _content_words(at, ak), _content_words(bt, bk)
    if not aw or not bw:
        return False
    overlap = len(aw & bw) / min(len(aw), len(bw))
    shared_names = _proper_nouns(at, ak) & _proper_nouns(bt, bk)
    return overlap >= 0.55 or (bool(shared_names) and overlap >= names_floor)


def _parse_utc_item(item):
    from datetime import datetime, timezone
    for fmt, val in (("%Y-%m-%dT%H:%M:%SZ", item.get("published_utc") or ""),
                     ("%Y-%m-%d", item.get("date") or "")):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# 36 hours, wider than crypto's 24: this desk's leak table runs on consecutive-day
# retellings (Kassebaum, TikTok, the South Korea exercises, Bald Range, all one day
# apart), and a morning retelling of last evening's story is the same event here.
# Beyond 36h a second story is follow-up territory and belongs to the update chain.
DEDUPE_WINDOW_H = 36


def same_event_on_disk(item, window_h=DEDUPE_WINDOW_H, content=None):
    """(path, story) of an already-published story covering this same event, or
    (None, None). Runs at ingest, the moment content actually enters the site, so it
    also catches anything that reached site/content without passing autopilot."""
    import glob as _glob
    import dedupe
    when = _parse_utc_item(item)
    if not when:
        return None, None
    for path in sorted(_glob.glob(os.path.join(content or CONTENT, "*.json"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            other = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if other.get("example"):
            continue
        if str(other.get("id") or "").startswith("wrap-") or \
                other.get("category") == "daily edition":
            continue
        if other.get("slug") == item.get("slug"):
            # skip-self ONLY for the item's own dated file (re-ingest). The same slug
            # in a DIFFERENT dated file is the strongest duplicate signal there is:
            # article URLs carry no date, so both files collide at one address and
            # whichever globs last silently wins the page (three live pairs on the
            # news desk shipped through exactly this bypass, 2026-08-31 audit).
            if os.path.basename(path) == f"{item.get('date')}-{item.get('slug')}.json":
                continue
            return path, other, "merge"
        other_when = _parse_utc_item(other)
        if not other_when or abs((when - other_when).total_seconds()) > window_h * 3600:
            continue
        if not dedupe.same_event(other.get("title", ""), other.get("key_fact", ""),
                                 item.get("title", ""), item.get("key_fact", "")):
            continue
        if not _same_storyline(item, other, 0.22):
            continue
        # THREE TIERS AND AN ESCAPE, measured on this desk's own leaked pairs
        # (2026-08-30). fwd = what the newcomer adds over the published story;
        # rev = what the published story says that the newcomer does NOT cover.
        #   fwd < NOVELTY_MIN: the newcomer adds nothing -> merge, published prose
        #     stands, its sources join. (the Kassebaum second obit: fwd 0)
        #   rev < NOVELTY_MIN: the published story is fully covered by the newcomer,
        #     a superset retelling -> merge, the newcomer's prose replaces. (the
        #     Venezuela and TikTok pairs: rev 0. This is the tier every August guard
        #     lacked: equal sources, added facts, same event, and it minted a URL.)
        #   more sources: a corroborated reframing replaces even when rev > 0,
        #     because the overstated claims it corrects are exactly the ones it does
        #     not repeat. (crypto's Solana-halt correction class)
        #   both add things the other lacks -> two genuine developments of one
        #     storyline -> NOT merged; the caller chains update_of instead, so the
        #     pair renders as a lineage rather than as two orphan pages. (the
        #     mail-ballot rulings: rev 2)
        _sig_item = dedupe._claim_signature(item) - dedupe._OUTLETS
        _sig_other = dedupe._claim_signature(other) - dedupe._OUTLETS
        fwd = len(_sig_item - dedupe._covered_signature(other))
        rev = len(_sig_other - dedupe._covered_signature(item))
        # NO SIGNATURE, NO VERDICT (dedupe's own 2026-08-21 rule, which this code
        # bypassed on its first test): an empty claim signature makes its novelty count
        # zero VACUOUSLY, and the second mail-ballot ruling, whose distinctive tokens
        # are all stopworded away, read as "adds nothing" and would have merged into a
        # different ruling. A tier only speaks when its signature actually exists.
        # A RETELLING KEEPS THE HEADLINE'S SUBJECT; A REACTION SHIFTS IT (2026-08-30).
        # "Trump announces an EU trade investigation" fully covers "EU fines Google",
        # so the coverage tiers read the reaction as a superset retelling and would
        # have replaced the fine story with the reaction. Every one of the 73 verified
        # August leaks was a near-same-headline pair (overlap 0.45 to 1.0), so merge
        # additionally requires the headlines to agree; a pair that shares the event
        # but not the headline is a lineage and chains instead.
        _hov = dedupe._headline_overlap(item.get("title") or "", other.get("title") or "")
        _mode = "merge" if _hov >= 0.45 else "chain"
        if _sig_item and fwd < dedupe.NOVELTY_MIN:
            return path, other, _mode
        if _sig_other and rev < dedupe.NOVELTY_MIN:
            return path, other, _mode
        if len(item.get("sources") or []) > len(other.get("sources") or []):
            return path, other, _mode
        return path, other, "chain"
    return None, None, None


def merge_into_existing(path, prior, incoming):
    """Fold a same-event retelling into the story already published, keeping its URL."""
    import dedupe as _dd
    _rev = len(_dd._claim_signature(prior)
               - _dd._covered_signature(incoming) - _dd._OUTLETS)
    # the newcomer's words win when it out-sources the original OR fully covers it
    # (a superset retelling); a thinner echo only contributes its sources
    upgraded = (len(incoming.get("sources") or []) > len(prior.get("sources") or [])
                or (_rev < _dd.NOVELTY_MIN
                    and len(json.dumps(incoming.get("body") or ""))
                    > len(json.dumps(prior.get("body") or ""))))
    if upgraded:
        old_title = prior.get("title", "")
        for f in ("title", "dek", "key_fact", "body", "bottom_line", "boundary",
                  "standfirst", "lead", "verdict"):
            if f in incoming:
                prior[f] = incoming[f]
        prior["consolidated"] = (
            "This story was updated in place with a better-sourced account of the same "
            f"event, carrying {len(incoming.get('sources') or [])} sources against the "
            f"original {len(prior.get('sources') or [])}. The earlier version was "
            f"headlined \u201c{old_title}\u201d. The URL and publication time are "
            "unchanged.")
        prior["superseded_sources"] = prior.get("sources") or []
        prior["sources"] = incoming.get("sources") or []
    else:
        seen = {(s.get("url") or "").strip() for s in (prior.get("sources") or [])}
        for src in (incoming.get("sources") or []):
            u = (src.get("url") or "").strip()
            if u and u not in seen:
                prior.setdefault("sources", []).append(src)
                seen.add(u)
    prior["updated_utc"] = incoming.get("published_utc") or prior.get("published_utc")
    prior.setdefault("merged_from", []).append({
        "id": incoming.get("id"), "title": incoming.get("title"),
        "published_utc": incoming.get("published_utc")})
    json.dump(prior, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


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
    rank_map, updates_map = {}, {}
    try:
        ranked = json.load(open(os.path.join(HERE, "out", "editor.json"), encoding="utf-8"))["ranked"]
        rank_map = {r["id"]: i + 1 for i, r in enumerate(ranked)}
        updates_map = {r["id"]: r["updates"] for r in ranked if r.get("updates")}
    except Exception:
        pass
    # the wire timestamp of the story's cluster: the closest thing the desk holds to
    # WHEN THE EVENT HAPPENED; the Breaking label gate depends on it
    event_map = {}
    try:
        event_map = {c["id"]: c.get("timestamp") or "" for c in json.load(
            open(os.path.join(HERE, "out", "items.json"), encoding="utf-8"))["clusters"]}
    except Exception:
        pass
    # verification inputs for the per-story trail (same run, already on disk)
    verifier_reasons, source_checks = {}, {}
    try:
        verifier_reasons = {v["id"]: v for v in json.load(
            open(os.path.join(HERE, "out", "verifier.json"), encoding="utf-8"))["verdicts"]}
    except Exception:
        pass
    try:
        source_checks = json.load(open(os.path.join(HERE, "out", "source_texts.json"),
                                       encoding="utf-8"))
    except Exception:
        pass
    n, merged = 0, 0
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
        srcs = [{"title": outlet_name(u), "url": u} for u in art.get("sources", [])]
        title = destyle(title)
        # the writer model sometimes slips a process note about the review status into the
        # copy ("Note: flagged for human review."); the article is the finished story only,
        # so any such sentence is stripped from every published field at the door
        # THE READER GETS THE NEWS, NEVER THE NEWSROOM'S NOTES (quality audit
        # 2026-08-30: on the crypto desk roughly half the sampled stories narrated
        # their own research gaps in the body, "Decrypt does not specify...",
        # "remains unreported in available coverage", and the sports desk shipped a
        # literal empty clause, "Awful Announcing reports that ." left behind by a
        # sentence repair). Both classes are process residue, mechanical to detect,
        # and cutting a whole sentence cannot invent anything.
        note = re.compile(r"(?:Note:\s*)?[^.!?]*(?:flagged for|pending)\s+human\s+review[^.!?]*[.!?]?\s*"
                          r"|[^.!?]*human review before publication[^.!?]*[.!?]?\s*"
                          r"|[^.!?]*(?:do(?:es)? not (?:specify|state|say|disclose|name)"
                          r"|not (?:specified|disclosed|named|stated) in"
                          r"|remains? unreported|unavailable in (?:the )?available"
                          r"|available (?:coverage|reporting) does not"
                          r"|could not be independently)[^.!?]*[.!?]?\s*", re.I)
        dangling = re.compile(r"[^.!?]*\b(?:reports?|said|says|stated|writes?|notes?)"
                              r"\s+that\s*[.!?](?=\s|$)", re.I)
        def scrub(text):
            return dangling.sub("", note.sub("", destyle(text))).strip()
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
        checks = source_checks.get(rec.get("id")) or []
        live = sum(1 for c in checks
                   if c.get("http_status") == 200 and (c.get("source_text") or "").strip())
        if event_map.get(rec.get("id")):
            item["event_utc"] = event_map[rec.get("id")]
        item["verification"] = {
            "verdict": rec.get("verdict"),
            "checked_utc": published_utc,
            "sources_cited": len(srcs),
            "sources_live_checked": live,
        }
        old_slug, relation = find_superseded(
            title, updates_map.get(rec.get("id")), CONTENT, item=item)
        if old_slug and old_slug != slug:
            item["update_of"] = old_slug
        else:
            relation = None
        # WHO ELSE REPORTED THIS (owner directive 2026-08-01). Recorded as coverage that
        # exists, never as this story's sources: Google News links are redirects, so they
        # never enter the sources list. Fail-soft and bounded to the handful of stories
        # that actually publish.
        try:
            import corroborate
            also = corroborate.also_reported_by(
                title, (srcs[0].get("title") if srcs else "") or "")
            if also:
                item["also_reported_by"] = [{"outlet": o, "headline": h} for o, h in also]
        except Exception as e:
            print(f"::warning::corroboration lookup failed for {rec.get('id')}: {e}")
        hold, warn = story_shape_problems(item)
        if hold:
            print(f"::warning::ingest: story {rec.get('id')} HELD, not published: "
                  + "; ".join(hold))
            continue
        if warn:
            print(f"::warning::ingest: story {rec.get('id')} shipped with gaps: "
                  + "; ".join(warn))
        # The boundary block passes through UNSCRUBBED and UNDESTYLED, alone among the
        # fields here. Every other value is the desk's own prose and gets house style; these
        # four are the vendor's words, checked character-for-character against the advisory
        # upstream (boundary.check_against_sources) and labeled on the page as quoted. Running
        # destyle over a quotation would edit a version range the desk promised not to touch,
        # for a house-style rule that has never applied to quoted material anyway.
        if boundary.is_complete(art.get("boundary")):
            item["boundary"] = {f: str(art["boundary"][f]) for f in boundary.FIELDS}
        # ONE EVENT, ONE URL: a same-event retelling folds into the published story
        # instead of minting a second address (see the port block above for why the
        # August guards could never do this job).
        prior_path, prior, mode = same_event_on_disk(item)
        if prior_path and mode == "merge":
            merge_into_existing(prior_path, prior, item)
            print(f"  MERGED {rec.get('id')} into {os.path.basename(prior_path)} "
                  f"(same event within {DEDUPE_WINDOW_H}h; no second story created)")
            merged += 1
            continue
        if prior_path and mode == "chain" and not item.get("update_of"):
            # two genuine developments of one storyline: publish, but as a LINEAGE.
            # The editor is supposed to declare this and usually does not (measured:
            # most same-storyline follow-ups shipped with no update_of at all), so
            # ingest declares it deterministically from what is actually on disk.
            item["update_of"] = prior.get("slug")
            relation = "chain"
            print(f"  CHAINED {rec.get('id')} as update of {prior.get('slug')[:56]} "
                  f"(same storyline, distinct development)")
        out = os.path.join(CONTENT, f"{date}-{slug}.json")
        json.dump(item, open(out, "w", encoding="utf-8"), indent=2)
        if item.get("update_of"):
            # RETIREMENT IS FOR A REPLACEMENT, NOT A FOLLOW-UP. This branch used to call
            # mark_superseded for every update_of, the chain above included, whose own
            # comment asks for "a LINEAGE rather than two orphan pages". A lineage with
            # its first chapter deleted is not a lineage. The strong claim now needs the
            # strong evidence; everything else links and both chapters stay reachable.
            if relation == "supersede":
                mark_superseded(CONTENT, item["update_of"], slug)
                print(f"  ingested {rec.get('id')} as UPDATE of {item['update_of']} "
                      f"-> {os.path.relpath(out)}")
            else:
                mark_continued(CONTENT, item["update_of"], slug)
                print(f"  ingested {rec.get('id')} as a LATER CHAPTER of "
                      f"{item['update_of']} (both stay live) "
                      f"-> {os.path.relpath(out)}")
        else:
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


def _render_og_card(item):
    """Render this article's OG card into PUBLISH/og/<slug>.png at build time. FAIL-OPEN:
    any problem (Pillow missing, font issue, bad headline) is swallowed so the card simply
    does not exist and the article falls back to the site-wide og-image. A card is a
    nice-to-have; it must never break the site build."""
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(HERE, "scripts"))
        import og_render
        cat = (item.get("category") or "").strip().lower()
        kicker = ("Sports News" if cat in ("", "news")
                  else "Daily Edition" if cat == "daily edition" else item["category"].title())
        og_render.render_card(item.get("title", ""), kicker,
                              os.path.join(PUBLISH, "og", f"{item['slug']}.png"))
        return True
    except Exception as e:
        print(f"::warning::og card skipped for {item.get('slug','?')}: {e}")
        return False


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
    # R-4: the PIL faces are for share_cards and og_render, which draw text into PNGs
    # at build time. No page requests them, and at 728 KB they are the largest thing in
    # assets. They stay in the repo, where the renderers read them; they do not ship.
    for _stale in glob.glob(os.path.join(PUBLISH, "assets", "fonts", "*.ttf")):
        try:
            os.remove(_stale)
        except OSError:
            pass
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

    # computed once and shared: the home chips, the article Full coverage links, the
    # /coverage/ pages themselves and the priority sitemap all read the same set
    site_hubs = coverage_hubs(items)

    # S2: refresh the schedule, then decide whether Where to Watch exists at all this
    # build. This runs BEFORE any page renders, because the nav entry on every page
    # depends on the answer. A failed fetch falls back to the committed file and only
    # withdraws the page once that file is six days old.
    global W2W_LIVE, W2W_DATA
    _w2w = None
    try:
        import where_to_watch as _w2wmod
        _w2wmod.refresh()
        _w2w = _w2wmod.load()
    except Exception as _e:
        print(f"where_to_watch: unavailable ({type(_e).__name__}); page and nav withheld")
    W2W_LIVE = bool(_w2w and (_w2w.get("weeks") or []))
    # S-B5: kickoff weather from NWS. It reads the schedule file, so it runs after
    # where_to_watch.refresh() writes it and BEFORE the schedule pages render: the
    # first ordering had the pages asking an empty WX_DATA for a reading.
    global WX_DATA
    WX_DATA = None
    try:
        import kickoff_weather as _wxmod
        _wxmod.refresh()
        WX_DATA = _wxmod.load()
    except Exception as _e:
        print(f"kickoff_weather: unavailable ({type(_e).__name__}); weather withheld")

    W2W_DATA = _w2w if W2W_LIVE else None
    if W2W_LIVE:
        _wks = _w2w["weeks"]
        # item 30: the page opened with Week 1 - sixteen finished games - because it
        # took the first week in the file. It opens with the week that still has a
        # window ahead, the same rule the rail card uses (D-14).
        _cur = next((w for w in _wks if _w2w_split(w)[0]), _wks[-1])
        w("where-to-watch.html", render_where_to_watch(_cur, _wks, dateline, current=True))
        for _wk in _wks:
            w(f"where-to-watch/{_w2w_slug(_wk)}.html",
              render_where_to_watch(_wk, _wks, dateline))
        print(f"where to watch: {len(_wks)} week(s), "
              f"{sum(len(x.get('games') or []) for x in _wks)} games, "
              f"as of {_w2w.get('fetched_at')}")

    # S-A: the Scoreboard band's own data. scores_pulse.py is frozen and writes a
    # ticker's worth of each game; the band needs networks, records, period and
    # situation, so this reads the public scoreboards itself.
    global SB_DATA, LINES_DATA
    SB_DATA = None
    try:
        import scoreboard as _sbmod
        _sbmod.refresh()
        SB_DATA = _sbmod.load()
    except Exception as _e:
        print(f"scoreboard: unavailable ({type(_e).__name__}); band withheld")

    # C-1: log the line while the game is still scheduled, because the feed drops its
    # odds object at kickoff and a line nobody logged before then is gone for good.
    # This runs on every build, which is why the Worker's build hooks matter to it: the
    # open line is only as early as the first build that saw the game.
    LINES_DATA = None
    try:
        import lines as _lnmod
        LINES_DATA = _lnmod.log([g for L in (SB_DATA or {}).get("leagues") or []
                                 for g in L.get("games") or []])
    except Exception as _e:
        print(f"lines: unavailable ({type(_e).__name__}); open lines withheld")

    # S-L1: the standings and the college football rankings. A league whose season has
    # not started writes nothing, so a failure here costs the standings pages and
    # nothing else on the site.
    global ST_DATA
    ST_DATA = None
    try:
        import standings as _stmod
        _stmod.refresh()
        ST_DATA = _stmod.load()
    except Exception as _e:
        print(f"standings: unavailable ({type(_e).__name__}); tables withheld")

    # S-L2: a team's own season, for the team pages. Cached for six hours, so a build
    # that runs four times an hour costs one fetch. It reads its team list from the
    # standings file, so a failure there simply means no team pages this build.
    global TEAM_DATA
    TEAM_DATA = None
    try:
        import schedules as _schmod
        _schmod.refresh()
        TEAM_DATA = _schmod.load()
    except Exception as _e:
        print(f"schedules: unavailable ({type(_e).__name__}); team pages withheld")

    # S-B2: poll the injury feed and snapshot before rendering, so a build that lands
    # inside a posting window captures it. The board renders from the snapshot, never
    # from a live read; see inactives.py.
    # S-1: the nav's Edition entry points at the newest dated issue. Resolved before
    # any page renders, because the masthead is on every one of them.
    global EDITION_HREF
    EDITION_HREF = None
    try:
        import edition as _ed_nav
        _days = _ed_nav.edition_days(items)
        if _days:
            EDITION_HREF = _ed_nav._latest_edition_path(_days)
    except Exception as _e:
        print(f"nav: Edition link unavailable ({type(_e).__name__}); item withheld")

    global IA_BOARD
    IA_BOARD = None
    try:
        import inactives as _ia
        _ia.poll()
        IA_BOARD = _ia.board()
    except Exception as _e:
        print(f"inactives: unavailable ({type(_e).__name__}); board withheld")
    global IA_DESIG
    IA_DESIG = None
    try:
        import inactives as _ia2
        IA_DESIG = _ia2.designations()
    except Exception:
        pass
    if IA_DESIG:
        _dg = render_designations(IA_DESIG, IA_BOARD, dateline)
        if _dg:
            w("fantasy/injuries.html", _dg)
            print(f"designations: {IA_DESIG['total']} players")
    # The default share card, drawn from the same system as the rest (art direction
    # pass). Written to /assets so OG_IMAGE keeps pointing at one path.
    try:
        import share_cards as _sc0
        _sc0.og_card(os.path.join(PUBLISH, "assets", "og-image.png"))
    except Exception as _e:
        print(f"share cards: default OG not drawn ({type(_e).__name__}); "
              f"the committed image stands")

    if IA_BOARD:
        try:
            import share_cards as _sc2
            _sc2.inactives_card(IA_BOARD,
                                os.path.join(PUBLISH, "share", "inactives.png"))
        except Exception:
            pass
        _ia_html = render_inactives(IA_BOARD, W2W_DATA, dateline)
        if _ia_html:
            w("fantasy/inactives.html", _ia_html)
            # N-7c: the earlier week's lists, where they are neither lost nor filed
            # under this week's heading.
            _ia_earlier_html = render_inactives_earlier(IA_BOARD, W2W_DATA, dateline)
            if _ia_earlier_html:
                w("fantasy/inactives/week-earlier.html", _ia_earlier_html)
            print(f"inactives board: {IA_BOARD['total']} players, "
                  f"{len(IA_BOARD['teams'])} teams")

    # S-B3/S-B8: points per game, then the game pages, the live board and the hub.
    # Only games that have started have a players block, so only those are fetched.
    #
    # PUNCH ITEM 12: this block now runs BEFORE the homepage. It used to run three
    # lines after it, so the band's live marquee had nothing to show but its buttons no
    # matter what the box score held.
    global LIVE_POINTS, LIVE_WP
    _all_points = {}
    _all_wp = {}
    _nfl = []
    if SB_DATA:
        import fantasy_points as _fpm
        _nfl = [g for L in SB_DATA["leagues"] if L["league"] == "NFL"
                for g in L["games"]]
        for _g in _nfl:
            if _g.get("state") in ("in", "post"):
                # C-3: one fetch, two readings. The win-probability track has been in
                # this response since the points feature shipped and was thrown away
                # every build.
                _pts, _wp = _fpm.for_game_full(_g["id"])
                if _pts:
                    _all_points[_g["id"]] = _pts
                # ONLY WHILE THE GAME IS LIVE. The track ends when the game does, so a
                # final's last reading is 1.0 or 0.0 for every game ever played: it
                # restates the result as a percentage and says nothing.
                if _wp is not None and _g.get("state") == "in":
                    _all_wp[str(_g["id"])] = _wp
    LIVE_POINTS = _all_points
    LIVE_WP = _all_wp
    w("index.html", render_home(items, dateline))
    if SB_DATA:
        _cards = 0
        for _g in _nfl:
            # S-F: the card is drawn from the same game record the page renders, so
            # the number in a group chat and the number on the page cannot disagree.
            try:
                import share_cards as _sc
                # S-F: the card is drawn from the same record the page renders, so
                # the ruling is computed once, here, and handed over rather than
                # re-derived inside the drawing code where it could drift from the page.
                _g = dict(_g, line=(_tk_logged(_g)[0] or {}),
                          ruling=_ruling_text(_g))
                _sc.game_card(_g, os.path.join(PUBLISH, "share", "games",
                                               f'{_g["id"]}.png'))
                _cards += 1
            except Exception as _e:
                pass
            w(f'games/{_g["id"]}.html',
              render_game_page(_g, _all_points.get(_g["id"]), IA_BOARD, WX_DATA,
                               items, dateline))
        print(f"share cards: {_cards} game card(s)")
        print(f"game pages: {len(_nfl)}, {len(_all_points)} with a box score")
        _fl = render_fantasy_live(_all_points, dateline)
        if _fl:
            w("fantasy/live.html", _fl)
    # S-D: one dated record a day of what each feed carried, so the day-14 report has
    # a series to read. Instrumentation only; it never fails a build.
    try:
        import source_trial as _st
        _st.record()
    except Exception as _e:
        print(f"source_trial: skipped ({type(_e).__name__})")

    # S-B6: the daily index, then a page for every player the facts say is worth one.
    try:
        import player_index as _pix
        _pix.build()
        _IDX = _pix.load()
    except Exception as _e:
        print(f"player_index: unavailable ({type(_e).__name__}); check withheld")
        _IDX = None
    if _IDX:
        # The search payload is served from /data so the worker never caches it.
        os.makedirs(os.path.join(PUBLISH, "data"), exist_ok=True)
        with open(os.path.join(PUBLISH, "data", "players.json"), "w",
                  encoding="utf-8") as _pf:
            json.dump({"players": [{k: v for k, v in p.items()
                                    if k in ("name", "slug", "team", "pos",
                                             "designation", "detail",
                                             "inactive_seen", "next")}
                                   for p in _IDX["players"]]}, _pf,
                      separators=(",", ":"))
        _stat_names = {p.get("name") for pts in _all_points.values()
                       for p in pts.values() if p.get("name")}
        _pages = _pix.page_set(_IDX, _stat_names)
        for _p in _pages:
            w(f'players/{_p["slug"]}.html', render_player_page(_p, IA_BOARD, dateline))
        print(f"player pages: {len(_pages)} of {len(_IDX['players'])} indexed "
              f"({len(_stat_names)} with a stat line)")

    _hub = render_fantasy_hub(IA_BOARD, IA_DESIG, _all_points, WX_DATA, SB_DATA, dateline)
    if _hub:
        w("fantasy/index.html", _hub)
        print("fantasy hub: built")

    if SB_DATA:
        _sc = render_scores_page(SB_DATA, IA_BOARD, dateline, WX_DATA)
        if _sc:
            w("scores.html", _sc)
            print(f"scores page: {sum(len(L['games']) for L in SB_DATA['leagues'])} games")

    # E-2: the Wire, the desk's own day in order. Written before the week pages so a
    # failure here costs one page and nothing after it.
    _wire = render_wire(items, dateline)
    if _wire:
        w("wire.html", _wire)
        print(f"wire: {len(_wire_rows(items))} entr(ies)")

    # B-4: one page per NFL week, from the team schedules already on file. A week that
    # has no fixtures on file writes nothing rather than an empty page.
    if TEAM_DATA:
        _wk_now, _ = nfl_week()
        _wk_n = _wk_g = 0
        for _w in range(1, WEEK_COUNT + 1):
            _gs = _sched_week(TEAM_DATA, _w)
            if not _gs:
                continue
            w(f"nfl/week-{_w}.html", render_week_page(TEAM_DATA, _w, dateline, _wk_now))
            _wk_n += 1
            _wk_g += len(_gs)
        print(f"weeks: {_wk_n} page(s), {_wk_g} fixture(s)"
              + (f", this week is {_wk_now}" if _wk_now else ""))

    # S-L1: one page per league that has a table, plus the rankings.
    if ST_DATA:
        _st_n = 0
        for _lg in (ST_DATA.get("leagues") or []):
            w(f'standings/{_lg["key"]}.html', render_standings_page(ST_DATA, _lg, dateline))
            _st_n += sum(len(g["rows"]) for g in _lg["groups"])
        _rk = render_rankings_page(ST_DATA, dateline)
        if _rk:
            w("standings/college-football.html", _rk)
        print(f"standings: {len(ST_DATA.get('leagues') or [])} league page(s), "
              f"{_st_n} team(s)"
              + (", rankings" if _rk else "")
              + (f"; not started: {', '.join(ST_DATA['not_started'])}"
                 if ST_DATA.get("not_started") else ""))

    # S-L2: one page per team. Each page claims its own stories, so _page_reset runs
    # per page and a story can lead one team's page and another's.
    if TEAM_DATA and (TEAM_DATA.get("teams") or {}):
        _tm_n = 0
        for _abbr, _tm in sorted((TEAM_DATA.get("teams") or {}).items()):
            _page_reset()
            w(f"teams/{_abbr.lower()}.html", render_team_page(_tm, items, dateline))
            _tm_n += 1
        print(f"team pages: {_tm_n}")

    w("keepers.html", render_keepers(items, dateline))
    # S3: the living tables, one page each, in the Record lane they belong to.
    _lt_urls = []
    for _spec in LIVING_TABLES:
        _got = render_living_table(_spec, items, dateline)
        if _got:
            _u, _html = _got
            w(_u.lstrip("/"), _html)
            _lt_urls.append(_u)
            print(f"living table: {_u}")
        else:
            print(f"living table: {_spec['slug']} withheld, fewer than "
                  f"{_spec['min_rows']} reported rows")
    w("news.html", render_news_hub(items, dateline))
    # S6: a page per storyline, paginated, plus a page per month. These are what make
    # every live story reachable within three clicks of the front page.
    _nh_lanes, _nh_rest, _nh_live = _news_lane_index(items)
    _nh_urls = []
    for _L in _nh_lanes:
        if len(_L["items"]) < NEWS_MIN_STORIES:
            continue
        _pages = max(1, -(-len(_L["items"]) // NEWS_PER_PAGE))
        for _pg in range(1, _pages + 1):
            _rel = (f'news/{_L["slug"]}.html' if _pg == 1
                    else f'news/{_L["slug"]}/page/{_pg}.html')
            w(_rel, render_news_lane(_L, _pg, _pages, dateline))
            _nh_urls.append("/" + _rel)
    for _m, _rows in _news_month_archive(_nh_live).items():
        w(f"news/archive/{_m}.html", render_news_month(_m, _rows, dateline))
    print(f"news hub: {len(_nh_lanes)} storyline(s), {len(_nh_urls)} storyline page(s)")
    w("archive.html", render_archive(items, dateline))
    for _slug, _title, _nav, _tags, _blurb in SECTIONS:
        w(f"sections/{_slug}.html",
          render_section(_slug, _title, _nav, _tags, _blurb, items, dateline))
    for _hub in site_hubs:
        w(f"coverage/{_hub['slug']}.html", render_coverage_hub(_hub, dateline))
    w("method.html", render_method(items, dateline))
    w("about.html", render_about(dateline))
    w("standards.html", render_standards(dateline))
    w("privacy.html", render_privacy(dateline))
    w("terms.html", render_terms(dateline))
    w("404.html", render_404(dateline))
    w("thanks.html", render_thanks(dateline))
    for it in items:
        _render_og_card(it)  # build-time per-article share card (fail-open) -> PUBLISH/og/
        w(os.path.join("articles", f"{it['slug']}.html"),
          render_article(it, all_items=items, hubs=site_hubs))
    w("bottom-line.html", render_bottom_line_history(items, dateline))
    w("feed.xml", render_feed(items))

    # The site card and the home-screen icon are GENERATED here, not copied from assets.
    # They used to be copied, and all three desks shipped the same committed file: News and
    # Sports were serving the Crypto card, so the one surface a stranger sees carried the
    # wrong brand. Generating removes the class of bug rather than the instance.
    # Fail-open, and fall back to the committed asset, because a missing og:image is worse
    # than a stale one.
    _share_generated = False
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(HERE, "scripts"))
        import og_render
        og_render.render_site_card(os.path.join(PUBLISH, "og-image.png"))
        og_render.render_icon(os.path.join(PUBLISH, "apple-touch-icon.png"), 180)
        _share_generated = True
    except Exception as e:
        print(f"::warning::share surfaces not generated, falling back to committed: {e}")
    if not _share_generated:
        for _name in ("apple-touch-icon.png", "og-image.png"):
            _src = os.path.join(ASSETS, _name)
            if os.path.exists(_src):
                open(os.path.join(PUBLISH, _name), "wb").write(open(_src, "rb").read())
    # A web app manifest, so saving to a home screen picks up the desk's own name and colour
    # instead of the page title and a browser default.
    with open(os.path.join(PUBLISH, "site.webmanifest"), "w", encoding="utf-8") as _mf:
        # FAMILY, not NAME. NAME is the byline persona on this desk (Crypto Cronkite), and
        # a home-screen label is a brand surface: the wordmark is the hero there too.
        json.dump({"name": FAMILY, "short_name": SHORT_NAME, "start_url": "/",
                   "display": "standalone", "background_color": "#FBFAF6",
                   "theme_color": THEME_COLOR,
                   # S-F: an install wants 192 and 512, plus a maskable icon so
                   # Android does not letterbox the mark inside its own shape. Drawn at
                   # size rather than upscaled: the only icon in the repo was 180px and
                   # a 512 scaled from it is visibly soft.
                   "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192",
                              "type": "image/png"},
                             {"src": "/assets/icon-512.png", "sizes": "512x512",
                              "type": "image/png"},
                             {"src": "/assets/icon-maskable-512.png", "sizes": "512x512",
                              "type": "image/png", "purpose": "maskable"},
                             {"src": "/apple-touch-icon.png", "sizes": "180x180",
                              "type": "image/png"}]}, _mf, ensure_ascii=False, indent=1)

    # S-F: the shell worker. The asset list is built from what actually shipped, and
    # the cache name carries the build stamp so a new build retires the old cache
    # rather than serving last week's stylesheet.
    _sw_assets = ["/assets/site.css", "/assets/icon-192.png", "/assets/icon-512.png",
                  "/assets/favicon.svg", "/apple-touch-icon.png"]
    for _f in sorted(os.listdir(os.path.join(PUBLISH, "assets", "fonts"))
                     if os.path.isdir(os.path.join(PUBLISH, "assets", "fonts")) else []):
        if _f.endswith((".woff2", ".woff")):
            _sw_assets.append(f"/assets/fonts/{_f}")
    _sw_assets = [a for a in _sw_assets
                  if os.path.exists(os.path.join(PUBLISH, a.lstrip("/")))]
    with open(os.path.join(PUBLISH, "sw.js"), "w", encoding="utf-8") as _swf:
        _swf.write(SERVICE_WORKER % {
            "v": _build_now().strftime("%Y%m%d%H%M"),
            "assets": json.dumps(_sw_assets)})
    print(f"service worker: {len(_sw_assets)} shell asset(s), no data cached")

    # sitemap (indexable pages only; 404/thanks are noindex), robots, netlify 404 redirect
    # P-2: THE FRONT DOORS WERE NOT IN THE SITEMAP. This list was written once and never
    # grew with the site: /scores, the four fantasy hubs, the Record and Where to watch
    # were all missing, which is to say the two pages a sports reader actually lands on
    # were not in the crawl path at all. Everything a reader can reach from the nav
    # belongs here.
    locs = ["/", "/news.html", "/scores.html", "/wire.html",
            "/fantasy/index.html", "/fantasy/inactives.html", "/fantasy/injuries.html",
            "/fantasy/live.html", "/fantasy/inactives/week-earlier.html"] + \
           [f"/sections/{sl}.html" for sl, _t, _n, _g, _b in SECTIONS] + [
            "/archive.html", "/bottom-line.html", "/method.html", "/about.html", "/standards.html",
            "/privacy.html", "/terms.html"]
    # only the ones that were actually written this build
    locs = [u for u in locs if os.path.exists(os.path.join(PUBLISH, u.lstrip("/")))]
    # SPLIT SITEMAP (2026-08-25). Search Console showed 207 of 369 submitted articles
    # still uncrawled: a new domain gets a small crawl budget and a single flat sitemap
    # spends it uniformly, so a story from six weeks ago competes with this morning's.
    # A sitemapindex points at two children, and the priority file is small enough to be
    # crawled whole. For a news desk RECENCY is the honest priority signal: the desk has
    # no quality score, and inventing one to rank its own work would be a worse lie than
    # a flat sitemap. Everything stays listed; only the ordering of attention changes.
    arts = [it for it in items if not it.get("example")]
    arts_sorted = sorted(arts, key=lambda i: i.get("published_utc") or i.get("date") or "",
                         reverse=True)
    PRIORITY_N = 30

    def _clean(p):
        return ORIGIN + (p[:-5] if p.endswith(".html") else p)

    def _urlset(paths):
        body = "\n".join(f"  <url><loc>{esc(_clean(p))}</loc></url>" for p in paths)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + body + "\n</urlset>\n")

    # SITEMAP AGING (consolidation 2026-09-01). The split bought the newest stories a
    # crawled-whole priority file; Search Console still declined the long tail behind it.
    # So the sitemap now stops advertising what a crawler will not spend budget on:
    # superseded stories leave both tiers (their replacements are already listed), and a
    # story older than 60 days on the build clock leaves the sitemap entirely. Aged-out
    # pages stay live, linked and redirect-protected; they are just no longer offered
    # for crawl. The /coverage/ hubs ride the priority tier because they are the
    # evergreen layer the aging tail consolidates into.
    _smap_now = _build_now()

    def _age_days(it):
        try:
            when = datetime.datetime.fromisoformat(
                (it.get("published_utc") or it.get("date") or "").replace("Z", "+00:00"))
        except ValueError:
            return 0.0        # an unparseable date stays advertised (fail-open)
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        return (_smap_now - when).total_seconds() / 86400.0

    n_superseded = sum(1 for i in arts_sorted if i.get("superseded_by"))
    eligible = [i for i in arts_sorted if not i.get("superseded_by")]
    # THE PRIORITY TIER IS THE BEST WORK, NOT THE NEWEST (work order 2026-09-12). It was
    # the N most recent stories, which means every new article entered the crawled-whole
    # tier and pushed a better one out, and a desk publishing several a day churned the
    # set faster than Google could read it. Search Console shows the result: 295 articles
    # queued and uncrawled while the priority file kept changing underneath the crawler.
    #
    # It is now the same evergreen ranking the homepage links, so the two agree: a story
    # in the priority sitemap is a story the front door also points at. Recency still has
    # a home in news-sitemap.xml, which is the file built for it.
    _ev = {i.get("slug") for i in evergreen_picks(eligible, PRIORITY_N)}
    prio_arts = [i for i in eligible if i.get("slug") in _ev]
    tail = [i for i in eligible if i.get("slug") not in _ev]
    archive_arts = [i for i in tail if _age_days(i) <= 60]
    n_aged_out = len(tail) - len(archive_arts)

    # priority: the hub pages a reader starts from, the coverage hubs, the newest N stories
    hub_paths = [f"/coverage/{h['slug']}.html" for h in site_hubs]
    # S5/S6: the Record, the storyline hubs and Where to Watch are the desk's own topic
    # pages and the crawl path to every story, so they ride the priority tier. Month
    # archives ride the archive tier with the aged stories they index. Storyline page 2
    # onward is reachable from page 1 and needs no entry of its own.
    _s6_lanes, _s6_rest, _s6_live = _news_lane_index(items)
    topic_locs = ["/keepers.html"]
    topic_locs += [f"/news/{L['slug']}.html" for L in _s6_lanes
                   if len(L["items"]) >= NEWS_MIN_STORIES]
    # S-L1: the standings pages are topic pages and a crawl path in their own right,
    # and only the ones that actually built are listed, so a league whose season has
    # not started never puts a 404 in the sitemap.
    if ST_DATA:
        topic_locs += [f'/standings/{lg["key"]}.html'
                       for lg in (ST_DATA.get("leagues") or [])]
        if ST_DATA.get("rankings"):
            topic_locs.append("/standings/college-football.html")
    if TEAM_DATA:
        topic_locs += [f"/teams/{a.lower()}.html"
                       for a in sorted((TEAM_DATA.get("teams") or {}))]
        # B-4: the eighteen week pages, listed the same way and for the same reason
        # P-2 exists. A page written by the build and named in no sitemap is a page the
        # desk has decided nobody will find. Only the weeks actually written are listed.
        topic_locs += [f"/nfl/week-{_w}.html" for _w in range(1, WEEK_COUNT + 1)
                       if _sched_week(TEAM_DATA, _w)]
    if W2W_LIVE and W2W_DATA:
        topic_locs.append("/where-to-watch.html")
        topic_locs += [f"/where-to-watch/{_w2w_slug(_wk)}.html"
                       for _wk in (W2W_DATA.get("weeks") or [])]
    prio = locs + topic_locs + hub_paths + [f"/articles/{i['slug']}.html" for i in prio_arts]
    # P-2: player, game and Edition pages are real pages a reader can land on and were
    # in no tier at all. They ride the archive tier rather than the priority one, which
    # is kept small on purpose so a new domain's crawl budget reads it whole.
    # The Edition pages are written LAST (they must win the /news.html route), so at
    # this point their directory is empty: the build wipes publish on every run. Asking
    # the filesystem gave nothing. The Edition is asked what days it will write instead.
    _extra = []
    try:
        import edition as _ed_sm
        _extra += [f"/edition/{_d}.html" for _d in _ed_sm.edition_days(items)]
    except Exception as _e:
        print(f"::warning::sitemap: edition days unavailable ({type(_e).__name__})")
    # the living tables, which write to /keepers/<slug>.html earlier in the build
    _extra += list(_lt_urls)
    for _sub in ("players", "games"):
        _dir = os.path.join(PUBLISH, _sub)
        if os.path.isdir(_dir):
            _extra += [f"/{_sub}/{_f}" for _f in sorted(os.listdir(_dir))
                       if _f.endswith(".html")]
    archive = _extra + [f"/news/archive/{m}.html" for m in _news_month_archive(_s6_live)] \
        + [f"/articles/{i['slug']}.html" for i in archive_arts]
    w("sitemap-priority.xml", _urlset(prio))
    w("sitemap-archive.xml", _urlset(archive))
    print(f"sitemap: priority {len(prio)} ({len(hub_paths)} hubs), "
          f"archive {len(archive)}, aged out {n_aged_out}, "
          f"superseded excluded {n_superseded}")
    w("sitemap.xml",
      '<?xml version="1.0" encoding="UTF-8"?>\n'
      '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
      f'  <sitemap><loc>{ORIGIN}/sitemap-priority.xml</loc></sitemap>\n'
      f'  <sitemap><loc>{ORIGIN}/sitemap-archive.xml</loc></sitemap>\n'
      f'  <sitemap><loc>{ORIGIN}/news-sitemap.xml</loc></sitemap>\n'
      '</sitemapindex>\n')

    # GOOGLE NEWS SITEMAP (2026-07-31): a standard sitemap tells crawlers a page exists;
    # this tells Google News a page is FRESH NEWS worth crawling now, and it is the entry
    # requirement for News/Discover surfacing. Spec: articles from the last 48 hours only,
    # nothing static, max 1000 URLs, W3C publication_date. An empty news sitemap is valid
    # and correct on a quiet day, so this never fabricates freshness.
    _news_now = _build_now()
    news_rows = []
    for it in items:
        if it.get("example") or it.get("superseded_by"):
            continue
        try:
            when = datetime.datetime.fromisoformat(
                (it.get("published_utc") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        if (_news_now - when).total_seconds() > 48 * 3600:
            continue
        news_rows.append(
            f"  <url>\n"
            f"    <loc>{ORIGIN}/articles/{esc(it['slug'])}</loc>\n"
            f"    <news:news>\n"
            f"      <news:publication>\n"
            f"        <news:name>{esc(NAME)}</news:name>\n"
            f"        <news:language>en</news:language>\n"
            f"      </news:publication>\n"
            f"      <news:publication_date>{esc(when.strftime('%Y-%m-%dT%H:%M:%SZ'))}"
            f"</news:publication_date>\n"
            f"      <news:title>{esc(it.get('title') or '')}</news:title>\n"
            f"    </news:news>\n"
            f"  </url>")
    news_rows = news_rows[:1000]
    w("news-sitemap.xml",
      '<?xml version="1.0" encoding="UTF-8"?>\n'
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
      '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
      + ("\n".join(news_rows) + "\n" if news_rows else "") + "</urlset>\n")

    w("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap.xml\n"
                    f"Sitemap: {ORIGIN}/news-sitemap.xml\n")
    # /rss.xml is the address readers and aggregators try first; the desk publishes at
    # /feed.xml, so alias rather than leave a 404 (2026-08-13 audit). Retired duplicate
    # slugs 301 to their surviving story, ahead of the catch-all (Netlify takes the
    # first match).
    # A REDIRECT TO A 404 IS WORSE THAN NO REDIRECT (owner audit 2026-08-29, ported from
    # the crypto desk where it shipped: a survivor slug transcribed from a truncated
    # console listing left a 301 pointing at nothing for a day). Every survivor must
    # actually render, and this fails the build loudly if one does not.
    _rendered = {i.get("slug") for i in items if i.get("slug")}
    _dangling = sorted(v for v in set(RETIRED_ARTICLES.values()) if v not in _rendered)
    if _dangling:
        for v in _dangling:
            print(f"::error::RETIRED_ARTICLES points at a survivor that does not exist: "
                  f"{v} (the retired URLs mapped to it would 301 into a 404)")
        raise SystemExit(f"site: {len(_dangling)} dangling redirect target(s); fix "
                         f"RETIRED_ARTICLES before shipping")
    redirects = "".join(f"/articles/{old}.html  /articles/{new}.html  301\n"
                        f"/articles/{old}  /articles/{new}  301\n"
                        for old, new in sorted(RETIRED_ARTICLES.items()))
    # ONE URL PER PAGE, ENFORCED AT THE EDGE (2026-09-12). The canonical, the sitemap and
    # the internal links all name the extensionless form and have since 2026-08-17, but
    # the .html file still answers 200, so both URLs are live and Google files every
    # article's .html twin under "Alternate page with proper canonical tag". That status
    # is Google consolidating correctly rather than an error, but it is 108 URLs of crawl
    # budget spent re-confirming duplicates on a site whose real articles are not being
    # crawled at all. A 301 removes the duplicate instead of explaining it.
    #
    # Scoped to the two directories that have twins. If Netlify does not honour a suffix
    # splat the rules simply never match, which is why this is safe to try: the failure
    # mode is the status quo. Placed BEFORE the catch-all 404 so it wins.
    canonical_301 = ("/articles/*.html  /articles/:splat  301!\n"
                     "/sections/*.html  /sections/:splat  301!\n")
    w("_redirects", "/rss.xml  /feed.xml  301\n" + redirects + canonical_301
                    + "/*  /404.html  404\n")
    # THE EDITION (owner spec 2026-08-03, chassis extension per the approved crypto
    # build): the composed front replaces the Latest tab at its own URL; back issues
    # under /edition/. Written LAST so the composed front wins the /news.html route.
    import edition as _edition
    n_ed = _edition.build(items, w, shell=shell)
    if n_ed:
        print(f"site: The Edition composed for {n_ed} day(s) -> news.html + /edition/")

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
