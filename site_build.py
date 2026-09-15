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
SLOGAN = "The score is a fact. The story gets checked."   # the brand tagline
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
NFA = ("GoCheckMySports reports events. It never advises bets. Nothing here is betting or "
       "gambling advice.")
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
NAV_PRIMARY = ["Scores", "Fantasy", "Where to watch", "The Record", "The Edition",
               "NFL", "College Football", "MLB"]
NAV_MORE = ["Soccer", "WNBA", "Tennis", "NBA", "College Basketball", "NHL",
            "More Sports", "Archive", "About"]


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
    """Dateline with the publish time when we have one: 'July 12, 2026 · 3:41 AM ET'.
    Games end late and news breaks around the clock; a reader needs to know 2 hours old vs 20."""
    base = esc(fmt_date(item.get("date")))
    if item.get("published_utc"):
        dt = _parse_utc(item)
        if dt:
            return f"{base} · {_et_clock(dt)}"
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
    fam = f'<a class="mh-family" href="{FAMILY_HUB}">A GoCheckMy site</a>'
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
    <span class="mh-dateline"><span data-live-date>{esc(dateline)}</span> · Independent · No hype</span>
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


def footer(brand="site"):
    """One identity everywhere; the brand parameter is kept for the shared call sites."""
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
    note = ("GoCheckMySports is an independent daily sports news desk, built with one "
            "intention: get the stories right and keep the facts honest. The score is a "
            "fact; the story gets checked. Sources are linked on every story.")
    return f"""<footer class="site"><div class="wrap">
  <div class="frow">
    <div class="fbrand">{who}</div>
    <div class="flinks">{links}</div>
  </div>
  <p class="fnote"><b>{esc(NFA)}</b> {note}
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
          brand="site", og_type="website", schema_extra="", og_image=None,
          canonical_path=None):
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=Mrs+Saint+Delafield&display=swap" rel="stylesheet">')
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
{skip}{masthead(active, dateline, brand)}
{body}
{footer(brand)}{beacon}
{tab_bar(path)}
{MOTION_JS}{SW_REGISTER}{FORMAT_JS if 'fmt-btn' in body else ''}{PLAYER_SEARCH_JS if 'pc-q' in body else ''}
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


def verdict_badge(verdict, item=None):
    """The verdict, plus a developing flag when the story rests on a single outlet.

    Ported from the crypto desk 2026-08-17. The two labels say different things and both
    matter: "Verified" means the verifier checked the claims against the sources that
    existed, "Developing" means only one outlet has carried it yet. Showing only the first
    is the part that oversells, and an audit flagged reading "VERIFIED" directly above "no
    independent outlet had corroborated it" as a contradiction the reader has to reconcile.
    A story with corroboration is NOT developing whatever its citation count: the badge
    discloses resting on one outlet's word, not a thin sources list."""
    out = ""
    if verdict == "VERIFIED":
        out = '<span class="badge verified">Verified</span>'
    elif verdict in ("NEEDS-HUMAN-REVIEW", "REVIEW"):
        out = '<span class="badge review">Editor reviewed</span>'
    if item is not None and item.get("developing"):
        out += ('<span class="badge developing" title="Only one outlet has carried this so '
                'far. The desk publishes it as developing rather than corroborated.">'
                'Developing, single source</span>')
    return out


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
    <span class="sig-attest">Ranked, source-checked, and verified by the desk's
      <a href="/method.html" rel="nofollow">independent review pass</a>.</span>
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
    topic_chips = "".join(f'<span class="tag topic">{esc(t)}</span>' for t in tags_for(item))
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

def card(item):
    badge = verdict_badge(item.get("verdict"), item)
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
  <p class="summary">{esc(clamp_words(summ, 180))}</p>
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

SCORES_AGE_JS = (
    # DATA-AGE TRIPWIRE (owner directive 2026-07-28; teeth 2026-08-31): the strip's
    # "as of" line is a promise. The client refresh (on load, on tab return, and on a
    # 2-minute interval) rewrites it to the real refresh time, but ONLY when a feed
    # actually matched a baked card (SCORES_JS gates the event on that now); if the
    # committed snapshot is older than 3 hours AND no such refresh has landed, the
    # widget says so itself AND the strip goes sb-frozen so its 'live' cards lose the
    # green live styling instead of impersonating games in progress.
    '<script>(function(){var n=document.getElementById("sb-note");if(!n)return;'
    'var s=document.getElementById("scores-strip");'
    'function two(x){return(x<10?"0":"")+x}'
    'function mark(d,live){var t=d.toLocaleTimeString("en-US",{timeZone:"America/New_York",'
    'hour:"numeric",minute:"2-digit"})+" ET";'
    'n.textContent="League data, not news \u00b7 as of "+t+(live?"":"");}'
    'var g=Date.parse(n.getAttribute("data-generated")||"");'
    'function stale(){n.textContent="League data, not news \u00b7 last update may be "+'
    '"delayed; scores below may not be current";n.classList.add("sb-stale");'
    'if(s)s.classList.add("sb-frozen")}'
    'if(!isNaN(g)&&Date.now()-g>108e5)stale();'
    'window.addEventListener("gcm:scores-refreshed",function(){mark(new Date(),1);'
    'n.classList.remove("sb-stale");if(s)s.classList.remove("sb-frozen")});'
    '})();</script>')


# The client refresh (2026-08-31 rebuild after the frozen-'Bot 6' audit):
#   - fetches ride a yesterday..today date range (StatsAPI startDate/endDate, ESPN
#     dates=) so a game baked before midnight can still resolve to its Final; the
#     bare URLs return only today's slate, which could never match yesterday's cards;
#   - the gcm:scores-refreshed event fires ONLY when a feed matched at least one
#     baked card; a parseable feed matching nothing is staleness, not freshness;
#   - orphan retirement: a baked live card whose eid the league's own feed no longer
#     carries can never resolve, so it loses the live class and says so;
#   - a real 2-minute interval polls alongside load and tab-return (the 120000ms
#     check in refresh() is the shared throttle).
SCORES_JS = (
    '<script>(function(){var s=document.getElementById("scores-strip");'
    'if(!s||!window.fetch)return;var feeds=[];'
    'try{feeds=JSON.parse(s.getAttribute("data-feeds")||"[]")}catch(e){return}'
    'var last=0;'
    'function two(x){return(x<10?"0":"")+x}'
    'function iso(d){return d.getUTCFullYear()+"-"+two(d.getUTCMonth()+1)+"-"+two(d.getUTCDate())}'
    'function apply(eid,as,hs,det,state){'
    'var g=s.querySelector(\'[data-eid="\'+eid+\'"]\');'
    'if(!g)return 0;'
    'if(as==null||hs==null||state==="pre")return 1;'
    'var rows=g.querySelectorAll(".sb-row"),st=g.querySelector(".sb-status");'
    'if(rows.length<2)return 1;'
    'rows[0].querySelector(".sb-score").textContent=as;'
    'rows[1].querySelector(".sb-score").textContent=hs;'
    'if(det&&st)st.textContent=det;'
    'g.classList.toggle("live",state==="in");'
    'if(state==="post"){var a=+as,h=+hs;'
    'rows[0].classList.toggle("win",a>h);rows[1].classList.toggle("win",h>a)}'
    'return 1}'
    'function retire(lg,seen){'
    's.querySelectorAll(\'.sb-game.live[data-lg="\'+lg+\'"]\').forEach(function(g){'
    'if(seen[g.getAttribute("data-eid")])return;'
    'g.classList.remove("live");'
    'var st=g.querySelector(".sb-status");'
    'if(st)st.textContent="Updated earlier"})}'
    'function refresh(){var n=Date.now();if(n-last<120000)return;last=n;'
    'var today=new Date(),yest=new Date(n-864e5);'
    'var ok=function(){try{window.dispatchEvent(new Event("gcm:scores-refreshed"))}catch(e){}};'
    'feeds.forEach(function(f){var lg=f[0],u=f[1];'
    'u+=u.indexOf("statsapi")>-1?"&startDate="+iso(yest)+"&endDate="+iso(today):'
    '(u.indexOf("?")>-1?"&":"?")+"dates="+iso(yest).replace(/-/g,"")+"-"+iso(today).replace(/-/g,"");'
    'fetch(u).then(function(r){return r.json()})'
    '.then(function(d){var seen={},got=0;'
    'if(d&&d.events){d.events.forEach(function(ev){'
    'var c=(ev.competitions||[{}])[0],sides={};'
    '(c.competitors||[]).forEach(function(x){sides[x.homeAway]=x});'
    'var st=(ev.status||{}).type||{};'
    'seen[String(ev.id)]=1;'
    'got+=apply(String(ev.id),(sides.away||{}).score,(sides.home||{}).score,'
    'st.state==="post"?"Final":(st.state==="in"?(st.shortDetail||"Live"):null),st.state)})}'
    'else if(d&&d.dates){d.dates.forEach(function(day){(day.games||[]).forEach(function(g){'
    'var t=g.teams||{},ls=g.linescore||{},ab=(g.status||{}).abstractGameState,'
    'state=ab==="Live"?"in":ab==="Final"?"post":"pre",'
    'det=state==="post"?"Final":state==="in"?((ls.isTopInning?"Top ":"Bot ")+'
    '(ls.currentInning||"")):null;'
    'seen[String(g.gamePk)]=1;'
    'got+=apply(String(g.gamePk),(t.away||{}).score,(t.home||{}).score,det,state)})})}'
    'else return;'
    'retire(lg,seen);'
    'if(got)ok()'
    '}).catch(function(){})})}'
    'refresh();document.addEventListener("visibilitychange",function(){'
    'if(document.visibilityState==="visible")refresh()});'
    'setInterval(refresh,120000)})()</script>')


def scores_strip():
    """The live layer, scoreboard edition (owner call 2026-07-21: game cards, not a
    stock-style ticker). Baked from site/data/scores.json (scores_pulse.py; fail-open).
    League data, not news: it never passes the editorial pipeline and says so. Empty or
    missing snapshot = no bar, no dead chrome. Client fetches (load, tab return,
    2-minute interval; CORS verified on both feeds) update the cards in place; baked
    values stand on any failure.
    Nothing self-moves, so WCAG 2.2.2 never triggers; the rail is keyboard-scrollable."""
    try:
        snap = json.load(open(SCORES_PATH, encoding="utf-8"))
    except Exception:
        return ""
    leagues = [l for l in snap.get("leagues", []) if l.get("games")]
    if not leagues:
        return ""
    # BUILD-TIME FAIL-CLOSED GUARD (2026-08-31; the Bottom Line guard's rule applied
    # to the strip: a stalled pipeline can never showcase an old inning as current).
    # scores_pulse.py runs before every build, so a stale snapshot here means the
    # fetch just failed and every 'in' state is a frozen inning, not a live game
    # ('Bot 6' stood on the live page 13 hours after the game ended). Past the
    # snapshot's own stale_after_utc hint (generated_utc + 3h when absent) live
    # cards demote to plain 'as of' cards; past 24h the strip does not render.
    now = _build_now()
    gen_raw = snap.get("generated_utc") or ""
    try:
        gen = datetime.datetime.fromisoformat(gen_raw.replace("Z", "+00:00"))
    except ValueError:
        gen = None
    if gen is None or (now - gen).total_seconds() > 24 * 3600:
        return ""
    try:
        stale_after = datetime.datetime.fromisoformat(
            (snap.get("stale_after_utc") or "").replace("Z", "+00:00"))
    except ValueError:
        stale_after = gen + datetime.timedelta(hours=3)
    demote_live = now > stale_after
    stamp = esc(_et(gen_raw))          # G-7: reader-facing clock is Eastern
    cards, feeds = [], []
    for l in leagues:
        feed = _CLIENT_FEEDS.get(l.get("league", ""))
        if feed:
            # [league, url] pairs: the client needs to know WHICH league a feed
            # covers so it only retires orphaned live cards from that league
            feeds.append([l.get("league", ""), feed])
        # ALWAYS label the league (2026-08-17). This was conditional on more than one
        # league having games, so in a month where only MLB is playing the strip rendered
        # as bare abbreviations and a start time ("TB DET 6:40 PM ET") with nothing saying
        # what sport it is. The label costs one chip and is the difference between a
        # scoreboard and a row of letters for anyone who is not already a fan.
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
            detail = str(g.get("detail", ""))
            if state == "in" and demote_live:
                # a frozen inning is not a live game: the card keeps its last scores
                # but loses the live treatment and says when they were taken
                live_cls = ""
                detail = f"as of {_et(gen_raw)}"
            cards.append(
                f'<span class="sb-game{live_cls}" data-eid="{esc(str(g.get("eid", "")))}" '
                f'data-lg="{esc(l.get("league", ""))}">'
                f'<span class="sb-row{a_win}"><span class="sb-team">{aw}</span>'
                f'<span class="sb-score">{a_txt}</span></span>'
                f'<span class="sb-row{h_win}"><span class="sb-team">{hm}</span>'
                f'<span class="sb-score">{h_txt}</span></span>'
                f'<span class="sb-status">{esc(detail)}</span></span>')
    # a snapshot from a previous day says so: bare 'as of 01:45 UTC' read as
    # this-morning when the bake was 13 hours old (2026-08-31)
    gen_date, build_date = gen_raw[:10], now.date().isoformat()
    note_when = (f"{esc(fmt_date(gen_date))}, {stamp}" if gen_date != build_date
                 else stamp)
    return (f'<section class="scorebar" aria-label="Today\'s scores">'
            f'<div class="wrap"><span class="sb-lab">Scores</span>'
            f'<div class="sb-rail" tabindex="0" role="group" '
            f'aria-label="Scores, scroll horizontally" id="scores-strip" '
            f"data-feeds='{json.dumps(feeds)}'>"
            f'{"".join(cards)}</div>'
            f'<span class="sb-note" id="sb-note" '
            f'data-generated="{esc(snap.get("generated_utc") or "")}">'
            f'League data, not news · as of {note_when}'
            f'</span></div></section>') + SCORES_JS + SCORES_AGE_JS


# STALENESS GUARD (owner directive 2026-07-22: the Bottom Line is a powerful piece or
# it is not on the page). Build time: an edition from a previous day is labeled
# honestly. View time: the band carries its timestamp and the reader's browser retires
# it into an archive pointer past 20 hours, so a stalled pipeline can never showcase
# an old read as current.
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
        claim = sent if len(sent) <= 128 else sent[:125].rsplit(" ", 1)[0] + "..."
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


def receipts_ledger(item):
    """The bordered ledger. Returns "" when the story has nothing checkable."""
    rows = _receipt_rows(item)
    if len(rows) < 2:
        return ""
    verified = (item.get("verdict") or "").upper() == "VERIFIED"
    out = ['<div class="sp-ledger">',
           '<div class="sp-row3 sp-head"><span class="bd-label">The receipts</span>'
           '<span class="bd-label">Source</span><span class="bd-label">Status</span></div>']
    for n, r in enumerate(rows):
        last = ' style="border-bottom:none"' if n == len(rows) - 1 else ""
        badge = ('<span class="bd-badge calc">Calculated</span>' if r["derived"]
                 else ('<span class="bd-badge ok">Verified</span>' if verified
                       else '<span class="bd-badge dat">Reported</span>'))
        src = esc(r["source"])
        if r["url"] and not r["derived"]:
            src = f'<a href="{esc(r["url"])}" rel="nofollow">{src}</a>'
        out.append(f'<div class="sp-row3"{last}><span class="sp-claim">{esc(r["claim"])}</span>'
                   f'<span class="bd-src">{src}</span>{badge}</div>')
    out.append("</div>")
    return "".join(out)


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
        return '<span class="bd-src">Not yet announced by the league</span>'
    out = []
    for c in g["carriers"]:
        tag = "" if c.get("market") == "National" else '<span class="w2w-loc">Local</span>'
        strm = '<span class="w2w-str">Streaming</span>' if c.get("type") == "Streaming" else ""
        out.append(f'<span class="w2w-car">{esc(c.get("name") or "")}{tag}{strm}</span>')
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
    when = f'{_et_clock(t)}, {t.astimezone(_ET).strftime("%a %-d %b")}'
    tail = ", not refreshed since" if age > 24 else ""
    return (f'<p class="bd-src">Channels as listed by the league, as of {esc(when)}'
            f'{tail}.</p>')


def _w2w_split(week):
    """Upcoming windows first, then anything the feed says is finished. Read from the
    feed's `completed`, never from the clock: a build at 03:00 UTC cannot tell whether
    Thursday's game finished, was postponed, or is in a weather delay."""
    up, done = [], []
    for wname, games in _w2w_windows(week):
        pending = [g for g in games if not g.get("completed")]
        played = [g for g in games if g.get("completed")]
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
        rows.append('<div class="w2w-win w2w-done"><span class="bd-label">Already played'
                    '</span><span class="bd-stamp">final, per the league feed</span></div>')
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
  <p class="bd-stamp"><a href="/index.html">Home</a> / Where to watch</p>
  <h1 class="lx-h1" style="margin-bottom:6px">NFL Week {esc(str(week.get("week") or ""))},
     every window and the channel that carries it</h1>
  <p class="lx-dek">{n} games, grouped by kickoff window. Carriers as the league has
     announced them.</p>
  {_w2w_stamp(W2W_DATA)}
  <div class="w2w">{"".join(rows)}</div>
  <div class="lx-actions">{others}</div>
  <p class="bd-src" style="margin-top:14px">Weather from the National Weather Service
     via GoCheckMyWeather, for the hour of kickoff. Source: ESPN NFL scoreboard, read at build.
     National and local carriage as the feed reports it; a game with no carrier listed
     has not been announced yet.</p>
</section></main>"""
    return shell(f"NFL Week {week.get('week')}: where to watch every game - {NAME}",
                 f"Every NFL Week {week.get('week')} game by kickoff window, with the "
                 f"channel or stream that carries it.",
                 "Where to watch", body, dateline, path=url)


def where_to_watch_card(data):
    """Homepage module 4, left. The next window or two, not the whole week."""
    if not data or not (data.get("weeks") or []):
        return ""
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    week = None
    for w in data["weeks"]:
        if any(not g.get("completed") for g in w.get("games") or []):
            week = w
            break
    week = week or data["weeks"][-1]
    # Only windows with a game still to play, and never a finished one.
    upcoming, _played = _w2w_split(week)
    upcoming = upcoming[:2]
    if not upcoming:
        return ""
    rows = []
    for wname, games in upcoming:
        rows.append(f'<div class="w2w-win"><span class="bd-label">{esc(wname)}</span>'
                    f'<span class="bd-stamp">{esc(games[0].get("day_et") or "")}</span></div>')
        for g in games[:4]:
            rows.append(
                f'<div class="w2w-row"><span class="w2w-game">{esc(g.get("away") or "")} at '
                f'{esc(g.get("home") or "")}</span>'
                f'<span class="bd-src">{esc(g.get("kickoff_et") or "")}</span>'
                f'<span class="w2w-cars">{_w2w_carriers(g)}</span></div>')
    return (f'<div class="bd-card" style="gap:12px;padding:20px 22px 18px">'
            f'<div class="bd-sec" style="border:none;padding:0"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Where to watch</span>'
            f'<span class="bd-h2" style="font-size:20px">NFL Week '
            f'{esc(str(week.get("week") or ""))}, every window and the channel that '
            f'carries it</span></div>'
            f'<a class="bd-more" href="/where-to-watch.html">All windows</a></div>'
            f'<div class="w2w">{"".join(rows)}</div>'
            f'<p class="bd-src">Carriage as the league has announced it. Regional games '
            f'vary by market.</p></div>')


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
                f'All {len(rows)} in {esc(lane["name"].lower())}</a>')
    newest = fmt_when(rows[0]) if rows else ""
    return (f'<section class="bd-mod" id="{esc(lane["slug"])}">'
            f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(lane["name"])}</span>'
            f'<span class="bd-stamp">{len(rows)} stories'
            f'{", newest " + esc(newest) if newest and not past else ""}</span>'
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

    rec = record_sections(items, home=True)
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
  <p class="lx-dek">{len(live)} checked stories, grouped by the storyline they belong to.
     Every source linked, every figure checkable.</p>
  {rec}
  <div class="bd-sec" style="margin-top:26px"><div class="bd-sec-l">
    <span class="bd-eyebrow">Storylines</span>
    <h2 class="bd-h2">What the desk is following</h2></div></div>
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
  <p class="lx-dek">{len(lane["items"])} checked stories in this storyline.
     {f"Page {page} of {pages}." if pages > 1 else ""}</p>
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
  <p class="lx-dek">{len(rows)} checked stories published this month.</p>
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
    ("Scores", "/index.html",
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


def _sb_team_row(t, lose=False, big=False, started=True, kick=""):
    col = t.get("color") or ""
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
                'stroke-linejoin="round"></path></svg>FINAL · checked</span>')
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
    bits = []
    for side in ("away", "home"):
        tid = (g.get(side) or {}).get("id") or ""
        ab = (g.get(side) or {}).get("abbr") or ""
        t = (ia_index or {}).get(("NFL", str(tid)))
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
            return (f'<div class="sb-marquee sb-mq-pre">'
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
        return (f'<div class="sb-marquee">'
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
    return (f'<div class="game">'
            f'{_sb_team_row(g["away"], lose_a, started=_started, kick=_kick)}'
            f'{_sb_team_row(g["home"], lose_h, started=_started)}'
            f'<div class="st">{_sb_status(g)}<span class="st-r">'
            f'{_wx_chip(g, wx)}{net}</span></div>'
            f'{f"<div class=sb-fanrow>{fan}</div>" if fan else ""}{bar}</div>')


def _sb_marquee_pick(games):
    """The marquee picks itself: the closest live score in the largest-audience league,
    else the next kickoff. No editor touches it."""
    order = {n: i for i, n in enumerate(SB_TAB_ORDER)}
    live = [g for g in games if g.get("state") == "in"]
    if live:
        def closeness(g):
            try:
                d = abs(int(g["away"]["score"]) - int(g["home"]["score"]))
            except Exception:
                d = 99
            return (order.get(g["league"], 99), d)
        return sorted(live, key=closeness)[0]
    up = [g for g in games if g.get("state") == "pre" and g.get("start_utc")]
    if up:
        return sorted(up, key=lambda g: (g["start_utc"], order.get(g["league"], 99)))[0]
    fin = [g for g in games if g.get("state") == "post"]
    return sorted(fin, key=lambda g: order.get(g["league"], 99))[0] if fin else None


def _ia_index(board):
    """Inactive counts by team id, for the card strips."""
    if not board:
        return {}
    # (league, id): a bare id is not an identity across leagues - see _sb_fantasy_strip.
    # The inactives feed is NFL, so that is the league these ids belong to.
    return {("NFL", str(t.get("id"))): t for t in board.get("teams") or [] if t.get("id")}


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
    rank = {"in": 0, "pre": 1, "post": 2}
    rest.sort(key=lambda g: (rank.get(g.get("state"), 9),
                             SB_TAB_ORDER.index(g["league"])
                             if g["league"] in SB_TAB_ORDER else 99,
                             g.get("start_utc") or ""))
    present = [n for n in SB_TAB_ORDER if any(g["league"] == n for g in games)]
    n_live = sum(1 for g in games if g.get("state") == "in")
    _today, _nxt_lab, _nxt_n = _sb_day_split(games)
    if _today:
        count_line = (f"{len(_today)} game{'' if len(_today) == 1 else 's'} today"
                      f" · {n_live} live now")
        foot_link = f"All {len(_today)} game{'' if len(_today) == 1 else 's'} today"
    elif _nxt_n:
        count_line = (f"No games today · {_nxt_n} "
                      f"{'game' if _nxt_n == 1 else 'games'} {_nxt_lab}")
        foot_link = "The full scoreboard"
    else:
        count_line = "No games scheduled"
        foot_link = "The full scoreboard"
    tabs = "".join(
        f'<a class="tab{" on" if i == 0 else ""}" '
        f'href="/scores.html{"" if i == 0 else "#" + esc(n.lower())}">{esc(n)}</a>'
        for i, n in enumerate(["All live"] + present))
    cards = "".join(_sb_card(g, ia, wx=wx) for g in rest[:8])
    stamp = _et(sb.get("fetched_at") or "")
    # S-25: the next kickoff, from the feed. Absent when nothing is scheduled.
    nxt = ""
    _pre = sorted((g for g in games if g.get("state") == "pre"),
                  key=lambda g: g.get("start_utc") or "")
    if _pre:
        _g = _pre[0]
        _dt = _utc_dt(_g.get("start_utc") or "")
        if _dt:
            nxt = (f'<span class="sb-next">Next: '
                   f'{esc((_g.get("away") or {}).get("abbr") or "")} at '
                   f'{esc((_g.get("home") or {}).get("abbr") or "")} '
                   f'{esc(_et_clock(_dt))}</span>')
    return f"""<section class="scoreband sb-hero" aria-label="The Scoreboard">
  <div class="sb-bg" aria-hidden="true"></div>
  <div class="sb-scrim" aria-hidden="true"></div>
  <div class="wrap sb-inner">
    <div class="sb-promise">
      <div class="sb-promise-l">
        <h2 class="sb-claim">Every score. No odds. No noise.</h2>
        <p class="sb-proof">Finals checked against the league feeds. Inactives within
          five minutes of posting. Every source linked.</p>
      </div>
      <span class="sb-count">{esc(count_line)}</span>
    </div>
    <div class="sb-head">
      <div class="sb-head-l"><span class="sb-lab">The Scoreboard</span>
        <div class="sb-tabs">{tabs}</div></div>
      <span class="sb-stamp">Updated {esc(stamp)} · refreshes every 15 minutes
        · finals checked against league feeds</span>
    </div>
    <div class="sb-grid">
      {_sb_card(mq, ia, marquee=True, wx=wx) if mq else ""}
      <div class="sb-cards">{cards}</div>
    </div>
    <div class="sb-foot"><a class="sb-link" href="/scores.html">{esc(foot_link)}
      &rarr;</a>{nxt}</div>
  </div>
</section>""" + SB_HERO_JS


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
        rank = {"in": 0, "pre": 1, "post": 2}
        games = sorted(games, key=lambda g: (rank.get(g.get("state"), 9),
                                             g.get("start_utc") or ""))
        secs.append(
            f'<section class="bd-mod" id="{esc(L["league"].lower())}">'
            f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(L["league"])}</span>'
            f'<span class="bd-stamp">{len(games)} games</span></div></div>'
            f'<div class="sb-cards sb-cards-light">'
            + "".join(_sb_card(g, ia, wx=wx) for g in games) + '</div></section>')
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/index.html">Home</a> / Scores</p>
  <h1 class="lx-h1" style="margin-bottom:6px">Every score. No odds. No noise.</h1>
  <p class="lx-dek">Updated {esc(_et(sb.get("fetched_at") or ""))}. Finals are checked
     against the league feeds.</p>
  <div class="scoreband scoreband-page">{"".join(secs)}</div>
</section></main>"""
    return shell(f"Scores - {NAME}",
                 "Every live score across the leagues this desk covers, with the "
                 "network carrying each game. No odds, ever.",
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
INACTIVES_NOTE = ("Times are when our check first saw each player's inactive flag, "
                  "checked every five minutes. Teams post about 90 minutes before "
                  "kickoff.")


def _et(iso):
    """UTC stamp to ET clock, '6:45 PM ET' (G-7).

    Was a flat UTC-4 with the note 'Eastern is UTC-4 through the regular season'. It is
    not: DST ends November 1, and the season runs to February. Every ET time on the site
    would have read an hour late from November, the inactives posting time included. The
    zone does the arithmetic now, so the switch needs no edit."""
    dt = _utc_dt(iso)
    return dt.astimezone(_ET).strftime("%-I:%M %p ET") if dt else ""


def _fantasy_tonight_card(sb, board, desig):
    """S-3. The lead rail's fantasy card: tonight's NFL games and when their lists
    post, this week's designation counts, and the way to the board.

    Every line is a reading or it is absent. No game tonight, no line about games; no
    designations held, no counts. If none of it holds, the card does not render and the
    rail closes around it rather than showing a frame with nothing in it."""
    rows = []
    games = [g for L in ((sb or {}).get("leagues") or []) for g in (L.get("games") or [])
             if g.get("league") == "NFL"]
    ia = _ia_index(board)
    for g in games:
        if g.get("state") != "pre":
            continue
        dt = _utc_dt(g.get("start_utc") or "")
        if not dt:
            continue
        import datetime as _dt
        aw = (g.get("away") or {}).get("abbr") or ""
        hm = (g.get("home") or {}).get("abbr") or ""
        posted = [t for t in (aw, hm)
                  if ia.get(("NFL", str((g.get("away") if t == aw else g.get("home")) or {}
                                        ).get("id")))]
        when = (f'lists posted' if len(posted) == 2
                else f'lists post about {_et_clock(dt - _dt.timedelta(minutes=90))}')
        rows.append(f'<div class="bd-rec-row"><span class="bd-rec-t">{esc(aw)} at '
                    f'{esc(hm)}</span><span class="bd-src">{esc(when)}</span></div>')
        if len(rows) >= 2:
            break
    if desig and desig.get("groups"):
        bits = [f'{len(v)} {k.lower()}' for k, v in desig["groups"].items() if v]
        if bits:
            rows.append(f'<div class="bd-rec-row"><span class="bd-rec-t">'
                        f'This week\u2019s designations</span>'
                        f'<span class="bd-src">{esc(" · ".join(bits))}</span></div>')
    if not rows:
        return ""
    return (f'<div class="bd-card sp-railcard">'
            f'<div class="bd-cardtop"><span class="bd-eyebrow">Fantasy, tonight</span>'
            f'</div><div class="bd-rec-rows">{"".join(rows)}</div>'
            f'<a class="bd-more" href="/fantasy/inactives.html">The inactives board</a>'
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


def _inactives_team_card(t):
    rows = "".join(
        f'<div class="ia-row"><span class="ia-name">{esc(p.get("name") or "")}</span>'
        f'<span class="ia-pos">{esc(p.get("pos") or "")}</span>'
        f'<span class="bd-src">{esc(p.get("reason") or "")}</span>'
        + (f'<span class="ia-upd">updated {esc(_et(p.get("first_seen") or ""))}</span>'
           if p.get("first_seen") and p["first_seen"] != t["first_seen"] else "")
        + '</div>'
        for p in t["players"])
    flag = ('<span class="bd-badge dat">list may be incomplete</span>'
            if t.get("incomplete") else "")
    return (f'<div class="bd-card ia-team">'
            f'<div class="bd-cardtop"><span class="bd-eyebrow">{esc(t["team"])}</span>'
            f'<span class="bd-stamp">{t["count"]} inactive listed</span>'
            f'<span class="bd-stamp">first seen {esc(_et(t["first_seen"]))}</span>'
            f'{flag}</div>'
            f'<div class="ia-rows">{rows}</div></div>')


def render_inactives(board, w2w, dateline):
    """/fantasy/inactives. Returns None when nothing is held, so the page and its nav
    entry withdraw together rather than showing an empty table."""
    if not board or not board.get("teams"):
        return None
    posted = {t["team"] for t in board["teams"]}
    games = []
    for wk in ((w2w or {}).get("weeks") or [])[:1]:
        games = wk.get("games") or []
    # Match on the team names the schedule uses, which are abbreviations; the board
    # holds full display names. Only teams we can match are shown as pending, so a
    # name we cannot resolve is left out rather than asserted as unposted.
    pending = _inactives_pending(
        games, {a for t in board["teams"] for a in (t["team"], str(t.get("id") or ""))})
    cards = "".join(_inactives_team_card(t) for t in board["teams"])
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
  <p class="bd-stamp"><a href="/index.html">Home</a> / Fantasy / Inactives</p>
  <h1 class="lx-h1" style="margin-bottom:6px">Today's inactives</h1>
  <p class="lx-dek">{board["total"]} players listed inactive across
     {len(board["teams"])} teams.</p>
  <p class="bd-src">{esc(INACTIVES_NOTE)}</p>
  <p class="bd-src"><strong>{esc(FANTASY_LINE)}</strong></p>
  <div class="ia-grid">{cards}</div>
  {pend}
  <p class="bd-src" style="margin-top:14px">Last updated
     {esc(_et(board.get("last_change") or ""))}. Source: the league injury feed, read on
     our own schedule and kept as a dated record.</p>
</section></main>"""
    return shell(f"Today's NFL inactives - {NAME}",
                 "Every team's inactive list for today's games, with the time our check "
                 "first saw each one. Facts, not advice.",
                 "Fantasy", body, dateline, path="/fantasy/inactives.html",
                 og_image=f"{ORIGIN}/share/inactives.png")


# ---- S-B3, S-B7, S-B8: live points, the hub, and game pages --------------------
# Points are computed from the official box score at each refresh and carry the format
# toggle client-side. The toggle is remembered on the device in localStorage and
# nothing else: no account, no cookie sent anywhere, nothing logged.

FANTASY_FOOT = ("Computed from the official box score at each refresh. Your league's "
                "scoring may differ.")
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


def _leaders_module(points, title, n=8, expand=True):
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
    return (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">{esc(title)}</span></div>{_fmt_toggle()}</div>'
            f'<div class="fp-rows">{_leader_rows(top)}</div>{more}'
            f'<p class="bd-src">{esc(FANTASY_FOOT)} {esc(TWO_PT_NOTE)}</p></section>')


def _game_wx_block(g, wx):
    w = _wx_for(g, wx)
    if not w:
        return ""
    if w.get("indoors"):
        return ('<div class="bd-card" style="padding:14px 16px"><span class="bd-label">'
                'Kickoff weather</span><p class="bd-read">Indoors at '
                f'{esc(w.get("venue") or "the venue")}.</p></div>')
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


def render_game_page(g, points, board, wx, items, dateline):
    """S-B8. The game header, the fantasy strip and inactives, leaders, weather, and
    the desk's recent stories for both teams."""
    ia = _ia_index(board)
    away, home = g.get("away") or {}, g.get("home") or {}
    inact = []
    for side in (away, home):
        t = ia.get(("NFL", str(side.get("id"))))   # game pages are NFL only
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
    # The desk's own recent coverage of both teams, by tag.
    import re as _re
    names = [n for n in ((away.get("name") or ""), (home.get("name") or "")) if n]
    rx = _re.compile("|".join(_re.escape(n) for n in names), _re.I) if names else None
    live_items = [i for i in (items or [])
                  if not i.get("example") and not _is_wrap(i)][:120]
    rel = []
    if rx:
        for i in live_items:
            if rx.search(i.get("title") or "") or rx.search(i.get("key_fact") or ""):
                rel.append(i)
            if len(rel) == 4:
                break
    rel_block = ""
    if rel:
        rel_block = ('<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                     '<span class="bd-eyebrow">From the desk</span></div></div>'
                     '<div class="nh-rows">'
                     + "".join(_news_row(i) for i in rel) + '</div></section>')
    head = (f'<div class="scoreband scoreband-page gp-head">'
            f'<div class="sb-cards">{_sb_card(g, ia, wx=wx)}</div></div>')
    body = f"""<main class="wrap"><section class="page">
  <p class="bd-stamp"><a href="/scores.html">Scores</a> /
     {esc(away.get("abbr") or "")} at {esc(home.get("abbr") or "")}</p>
  <h1 class="lx-h1" style="margin-bottom:6px">{esc(away.get("name") or "")} at
     {esc(home.get("name") or "")}</h1>
  {head}
  {_game_wx_block(g, wx)}
  {inact_block}
  {_leaders_module(points, "Fantasy leaders")}
  {rel_block}
  <p class="bd-src"><strong>{esc(FANTASY_LINE)}</strong></p>
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
  <p class="lx-dek">Every player with a stat line today, across every game.</p>
  <p class="bd-src"><strong>{esc(FANTASY_LINE)}</strong></p>
  {_leaders_module(merged, "Today's leaders", n=25, expand=False)}
</section></main>"""
    return shell(f"Live fantasy points - {NAME}",
                 "Live fantasy points in PPR, half-PPR and standard, computed from the "
                 "official box score. No projections, ever.",
                 "Fantasy", body, dateline, path="/fantasy/live.html")


def render_fantasy_hub(board, desig, all_points, wx, sb, dateline):
    """S-B7. The hub: the official answer, then the surfaces that give it."""
    blocks = []
    if board:
        top = board["teams"][:6]
        cards = "".join(
            f'<a class="bd-card" href="/fantasy/inactives.html" '
            f'style="text-decoration:none"><span class="bd-label">{esc(t["team"])}</span>'
            f'<span class="bd-read">{t["count"]} inactive listed</span>'
            f'<span class="bd-stamp">first seen {esc(_et(t["first_seen"]))}</span></a>'
            for t in top)
        blocks.append(
            f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">Today\'s inactives</span>'
            f'<span class="bd-stamp">{board["total"]} players</span></div>'
            f'<a class="bd-more" href="/fantasy/inactives.html">The full board</a>'
            f'</div><div class="bd-cards4">{cards}</div></section>')
    if desig:
        counts = " · ".join(f'{k} {len(v)}' for k, v in desig["groups"].items() if v)
        blocks.append(
            f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">This week\'s designations</span>'
            f'<span class="bd-stamp">{counts}</span></div>'
            f'<a class="bd-more" href="/fantasy/injuries.html">All designations</a>'
            f'</div></section>')
    merged = {}
    for pts in (all_points or {}).values():
        merged.update(pts)
    if merged:
        blocks.append(_leaders_module(merged, "Live points", n=8, expand=False)
                      .replace('</section>',
                               '<a class="bd-more" href="/fantasy/live.html">'
                               'The full board</a></section>'))
    if not blocks:
        return None
    # S-E: the day's marquee games, as "Where to watch tonight". The network already
    # rides every Scoreboard card; this is the same data on the surface a fantasy
    # reader is already on.
    watch = ""
    if sb:
        games = [g for L in sb["leagues"] for g in L["games"]
                 if g.get("state") in ("pre", "in")]
        games.sort(key=lambda g: (SB_TAB_ORDER.index(g["league"])
                                  if g["league"] in SB_TAB_ORDER else 99,
                                  g.get("start_utc") or ""))
        rows = "".join(
            f'<div class="w2w-row"><span class="w2w-game">'
            f'{esc((g.get("away") or {}).get("abbr",""))} at '
            f'{esc((g.get("home") or {}).get("abbr",""))}</span>'
            f'<span class="bd-src">{esc(g.get("status_short") or "")}</span>'
            f'<span class="w2w-cars">'
            + (f'<span class="w2w-car">{esc(g.get("network"))}</span>'
               if g.get("network") else '<span class="bd-src">not announced</span>')
            + '</span></div>' for g in games[:6])
        if rows:
            watch = (f'<section class="bd-mod"><div class="bd-sec"><div class="bd-sec-l">'
                     f'<span class="bd-eyebrow">Where to watch tonight</span></div>'
                     f'<a class="bd-more" href="/where-to-watch.html">Every window</a>'
                     f'</div><div class="w2w">{rows}</div></section>')

    body = f"""<main class="wrap"><section class="page">
  <h1 class="lx-h1" style="margin-bottom:6px">Is he playing? Here's the official
     answer.</h1>
  <p class="bd-src"><strong>{esc(FANTASY_LINE)}</strong></p>
  {player_check_block()}
  {"".join(blocks)}
  {watch}
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
        : '<p class="bd-src">No player by that name in today\\u2019s index.</p>';
    }).catch(function(){ out.innerHTML='<p class="bd-src">The index could not be '
      +'loaded. Try the boards below.</p>'; });
  }
  var t; box.addEventListener('input',function(){clearTimeout(t);t=setTimeout(run,140);});
})();</script>"""


def player_check_block():
    return ('<section class="bd-mod pc"><div class="bd-sec"><div class="bd-sec-l">'
            '<span class="bd-eyebrow">Player check</span>'
            '<h2 class="bd-h2">Is he playing?</h2></div></div>'
            '<label class="sr-only" for="pc-q">Search a player by name</label>'
            '<input id="pc-q" class="pc-q" type="search" autocomplete="off" '
            'placeholder="Type a player\'s name" data-src="/data/players.json">'
            '<div id="pc-out" class="pc-out" aria-live="polite"></div>'
            '<p class="bd-src">Searched on your device against today\'s index. '
            'Nothing you type is sent anywhere.</p></section>')


def render_player_page(p, board, dateline):
    """/players/<slug>. Titled to the question people actually type."""
    n = p.get("next") or {}
    inactive = bool(p.get("inactive_seen"))
    if inactive:
        answer = "Ruled out. On today's posted inactive list."
        badge = '<span class="bd-badge dat">Inactive</span>'
    elif p.get("designation"):
        answer = (f'Listed {p["designation"].lower()} on the official report'
                  + (f', {p["detail"].lower()}' if p.get("detail") else "") + ".")
        badge = f'<span class="bd-badge dat">{esc(p["designation"])}</span>'
    else:
        answer = "No designation on the official report."
        badge = '<span class="bd-badge ok">No designation</span>'
    nxt = ""
    if n.get("opponent"):
        when = " ".join(x for x in (n.get("day"), n.get("kickoff_et")) if x)
        nxt = (f'<p class="bd-read">Next game: '
               f'{"vs " if n.get("home") else "at "}{esc(n["opponent"])}'
               + (f' · {esc(when)}' if when else "")
               + (f' · {esc(n["network"])}' if n.get("network") else "") + '</p>')
    hist = ""
    if p.get("inactive_seen"):
        hist = (f'<p class="bd-src">First seen on the inactive list at '
                f'{esc(_et(p["inactive_seen"]))}.</p>')
    body = f"""<main class="wrap narrow"><section class="page">
  <p class="bd-stamp"><a href="/fantasy/index.html">Fantasy</a> / {esc(p.get("name"))}</p>
  <h1 class="lx-h1" style="margin-bottom:6px">Is {esc(p.get("name"))} playing this week?
     Official status</h1>
  <div class="bd-cardtop" style="margin-bottom:8px">
    <span class="bd-eyebrow">{esc(p.get("team"))} {esc(p.get("pos"))}</span>{badge}</div>
  <p class="lx-dek">{esc(answer)}</p>
  {nxt}{hist}
  <p class="bd-src">Status as the official report lists it, read on our own schedule.
     See the <a href="/fantasy/inactives.html">inactives board</a> for today's posted
     lists and <a href="/fantasy/injuries.html">this week's designations</a> for the
     full report.</p>
  <p class="bd-src"><strong>{esc(FANTASY_LINE)}</strong></p>
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
            ruled = ""
            if (p.get("team"), p.get("name")) in ia_names:
                ruled = '<span class="bd-badge dat">inactive</span>'
            elif board and any(t.get("team") == p.get("team")
                               for t in board.get("teams") or []):
                ruled = '<span class="bd-badge ok">active</span>'
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
  <h1 class="lx-h1" style="margin-bottom:6px">This week's designations</h1>
  <p class="lx-dek">{desig["total"]} players carry an official designation right now.</p>
  <p class="bd-src">Out, Doubtful and Questionable as the official report lists them.
     A player who is questionable and not on a posted inactive list is shown as active.
     Read on our own schedule; see the <a href="/fantasy/inactives.html">inactives
     board</a> for today's posted lists.</p>
  <p class="bd-src"><strong>{esc(FANTASY_LINE)}</strong></p>
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
        what = (i.get("key_fact") or i.get("dek") or "").strip()
        if len(what) > 260:
            what = what[:255].rsplit(" ", 1)[0] + "..."
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
  <p class="bd-src" style="margin-top:14px">Every row is a story this desk published
     and checked. The table updates when the next one posts; it is not a survey of
     every deal in the market.</p>
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


def _fantasy_facts_lane(items):
    return [i for i in items if "injuries" in {t.lower() for t in tags_for(i)}]


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
    if outlets:
        return f'<span class="bd-badge dat">Reported · {esc(outlets[0])}</span>'
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
            f'{esc(" · ".join(f for _v, f in figs[:3]))}</span>')


def lane_card_v3(item, lane_name, stamp=None):
    """S-C. The v3 lane card. `stamp` lets a lane show its count and newest date in
    place of the piece's own dateline (S-17)."""
    pull = (item.get("bottom_line") or item.get("key_fact") or item.get("dek") or "").strip()
    if len(pull) > 300:
        pull = pull[:295].rsplit(" ", 1)[0] + "..."
    chip = _receipt_status(item)
    # A status chip only when the metadata has one. verdict_badge is the desk's own
    # and is present on every checked story; the receipt chip is not.
    status = verdict_badge(item.get("verdict"), item) if item.get("verdict") else ""
    outlets = []
    for s in (item.get("sources") or []):
        nm = _bd_outlet(s)
        if nm and nm not in outlets:
            outlets.append(nm)
    receipts = (f'<p class="bd-src">Receipts: {esc(", ".join(outlets[:3]))}</p>'
                if outlets else "")
    return (f'<div class="bd-card lane-v3">'
            f'<div class="bd-cardtop"><span class="bd-eyebrow">{esc(lane_name)}</span>'
            f'{status}{chip}<span class="bd-stamp">'
            f'{stamp if stamp else esc(fmt_when(item))}</span></div>'
            f'<a class="bd-rec-hl" href="/articles/{esc(item["slug"])}.html">'
            f'{esc(item.get("title") or "")}</a>'
            + (f'<p class="bd-read" style="font-size:15px">{esc(pull)}</p>' if pull else "")
            + _lane_figures(item)
            + receipts
            + f'<a class="bd-more" href="/articles/{esc(item["slug"])}.html">'
              f'Read the piece</a></div>')


def extra_lanes(items, board, claimed=None):
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
                     f'{board["total"]} players listed</a>'
                     f'<span class="bd-src">Living board</span></div>')
        right = (f'<div class="bd-card bd-rec-more">'
                 f'<span class="bd-label">Read further in {esc(name.lower())}</span>'
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


def _record_type(item, hub_slugs):
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


def _record_lane(slug, name, lane_items, hub_slugs, page=False, tables=None):
    """One lane: the featured piece on the left, three more on the right."""
    if len(lane_items) < RECORD_LANE_MIN:
        return ""
    feat = lane_items[0]
    rest = lane_items[1:4]
    newest = max((i.get("published_utc") or "") for i in lane_items)[:10]
    # was "1 pieces in the Record"; the count carries no noun now, so it cannot disagree
    status = (f"{len(lane_items)} in the Record · newest {esc(fmt_short_date(newest))}"
              if newest else f"{len(lane_items)} in the Record")
    srcs = []
    for i in lane_items[:6]:
        for s in (i.get("sources") or []):
            lab = _bd_outlet(s)
            if lab and lab not in srcs:
                srcs.append(lab)
    receipts = (f'Receipts: {esc(", ".join(srcs[:4]))}' if srcs
                else "Receipts: every source linked on the piece")
    # S-17: every lane uses the v3 card. Three used the v2 feature card and two used
    # v3, which is what made one Record look like two.
    left = lane_card_v3(feat, name, stamp=status)
    rows = "".join(
        f'<div class="bd-rec-row"><a class="bd-rec-t" href="/articles/{esc(i["slug"])}.html">'
        f'{esc(i.get("title") or "")}</a>'
        f'<span class="bd-src">{esc(_record_type(i, hub_slugs))}</span></div>'
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
                 f'<span class="bd-label">Read further in {esc(name.lower())}</span>'
                 f'<div class="bd-rec-rows">{rows}</div>'
                 f'<a class="bd-more" href="{all_href}">All {esc(name.lower())}</a></div>')
    return f'<section class="bd-rec-lane" id="{esc(slug)}">{left}{right}</section>'


def _live_tables(items):
    """Which living tables have the rows to render. Same question render_living_table
    asks, so the Record's link and the page itself can never disagree."""
    return {t["slug"] for t in LIVING_TABLES
            if len(_table_rows(t, items)) >= t["min_rows"]}


REC_MORE_JS = """
<script>(function(){
  /* S-24. The Record ships expanded so the page is complete without JavaScript; this
     collapses it on a phone, where five lanes are a third of the homepage. Desktop is
     untouched and the summary is hidden there by CSS. */
  try{
    if (window.matchMedia && window.matchMedia('(max-width:640px)').matches){
      document.querySelectorAll('details.rec-more').forEach(function(d){ d.open = false; });
    }
  }catch(e){}
})();</script>"""


def record_sections(items, home=True, board=None):
    """The Record: ONE header and one block, five lanes on the homepage in the audit's
    order (Lawsuits and rulings, Discipline, Media rights, Contracts, Fantasy facts),
    every lane on /keepers.html. S-17."""
    by_lane, _picks = _record_inventory(items)
    hub_slugs = {h.get("slug") for h in coverage_hubs(items) if isinstance(h, dict)}
    lanes = "".join(
        _record_lane(slug, name, by_lane.get(slug) or [], hub_slugs, page=not home,
                     tables=_live_tables(items))
        for slug, name, _tags, on_home in RECORD_LANES
        if (on_home or not home))
    _claimed = {i.get("slug") for v in by_lane.values() for i in v}
    if home and HOME_LEAD_SLUG:
        _claimed.add(HOME_LEAD_SLUG)
    lanes += extra_lanes(items, board, claimed=_claimed)
    if not lanes.strip():
        return ""
    head = (f'<div class="bd-sec"><div class="bd-sec-l">'
            f'<span class="bd-eyebrow">The Record</span>'
            f'<h2 class="bd-h2">What stays true after the news moves on</h2></div>'
            + (f'<a class="bd-more" href="/keepers.html">The full Record</a>' if home else "")
            + '</div>')
    # S-24: five lane sections are 4,970px on a phone, over a third of the homepage.
    # The first lane stays; the rest go inside a details the phone closes. It ships
    # OPEN, so a reader without JavaScript sees every lane exactly as before - the
    # script only closes it where the height is the problem.
    parts = re.findall(r'<section class="bd-rec-lane".*?</section>', lanes, re.S)
    if home and len(parts) > 1:
        rest = "".join(parts[1:])
        lanes = (parts[0]
                 + f'<details class="rec-more" open><summary>Show all '
                   f'{len(parts)} lanes</summary>{rest}</details>')
    return (f'<section class="bd-mod" aria-labelledby="bd-rec">{head}{lanes}</section>'
            + (REC_MORE_JS if home else ""))


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
            f'<div class="bd-cardtop"><span class="bd-label">The Record, full index</span>'
            f'<a class="bd-more" href="/keepers.html">Open the Record</a></div>'
            f'<div class="bd-rec-cols">{links}</div></section>')


def render_keepers(items, dateline):
    """/keepers.html: every lane, same shape as the homepage sections."""
    body = f"""<main class="wrap"><section class="page">
  <h1 class="sr-only">The Record: what stays true after the news moves on</h1>
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
    _s1_lead = stories[0] if stories else None
    _s1_ledger = receipts_ledger(_s1_lead) if _s1_lead else ""
    global HOME_LEAD_SLUG
    HOME_LEAD_SLUG = (_s1_lead or {}).get("slug") if (_s1_lead and _s1_ledger) else None
    hero_pool = stories[1:] if (_s1_lead and _s1_ledger) else stories

    def _hero_tag(item):
        tags = tags_for(item)
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
        # The Bottom Line card is NOT part of what the audit retired. It was put in the
        # hero square by owner call on 2026-07-16 and the standalone band below was
        # retired in the same move, so removing the square without rehoming it would
        # delete the element rather than relocate it. It leads this section as a light
        # card; /bottom-line.html still keeps the history.
        bl_card = ""
        if bl_anchor is not None:
            ed = bl_anchor
            ed_name = esc((ed.get("title") or "").split(":")[0].strip() or "The Daily Edition")
            bl_card = (f'<a class="bd-card sp-bl" '
                       f'data-bl-published="{esc(ed.get("published_utc") or "")}" '
                       f'href="/articles/{esc(ed["slug"])}.html">'
                       f'<span class="bd-cardtop"><span class="bd-eyebrow">'
                       f'The Bottom Line</span>'
                       f'<span class="bd-stamp">{_bl_fresh_label(ed, ed_name)} · '
                       f'{_blink_when(ed)}</span></span>'
                       f'<span class="sp-bl-read">{esc(ed["bottom_line"])}</span>'
                       f'<span class="bd-more">Read the full edition &rarr;</span></a>'
                       + _BL_GUARD_SCRIPT)
        # S-6: six light cards, three across. League label, the desk's badge, the
        # headline clamped at a word boundary, the time in ET. No summary text, so
        # equal heights come from the clamp and not from stretching a short card.
        cards = "".join(
            f'<a class="bd-card sp-deskcard" href="/articles/{esc(i["slug"])}.html">'
            f'<span class="bd-cardtop">{_hero_tag(i)}'
            f'{verdict_badge(i.get("verdict"), i)}</span>'
            f'<span class="sp-deskcard-h">{esc(clamp_words(i.get("title") or "", 96))}</span>'
            f'<span class="dateline">{fmt_when(i)}</span></a>'
            for i in stories[:6])
        desk_html = (f'<div class="bd-sec"><div class="bd-sec-l">'
                     f'<span class="bd-eyebrow">The desk</span>'
                     f'<h2 class="bd-h2">From the desk</h2></div>'
                     f'<a class="bd-more" href="/news.html">All stories &rarr;</a></div>'
                     f'{bl_card}<div class="sp-deskgrid">{cards}</div>')

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
                f'<a class="edition-card reveal" href="/articles/{esc(w["slug"])}.html">'
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
            f'Read tonight\'s Edition</a>'
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
        track_html = (f'<div class="tracking"><span class="lab">Tracking</span>{"".join(chips)}'
                      f'<span class="mut">the storylines the desk is following</span></div>')

    # S1, Artboard 4 module 3: the lead story with its receipts ledger, and beside it
    # the charted receipts and the Edition. The ledger is only rendered for a story
    # that actually carries checkable figures with an attribution the story made; see
    # receipts_ledger. Without one the lead keeps its normal shape and the row shows
    # the Edition alone, rather than an empty ledger frame.
    lead_row = ""
    _lead, _ledger = _s1_lead, _s1_ledger
    if _lead and _ledger:
        _lt = tags_for(_lead)
        # S-4: no body paragraph on the homepage. It was the source of the lead card's
        # ~400px of body text and of the headline that stopped mid-sentence at "The...".
        _dek = clamp_words((_lead.get("dek") or "").strip(), 190)
        _left = (f'<div class="bd-card sp-lead">'
                 f'<div class="bd-cardtop"><span class="bd-eyebrow">Lead story</span>'
                 f'{f"<span class=bd-stamp>{esc(_lt[0])}</span>" if _lt else ""}'
                 f'{_breaking_badge(_lead)}'
                 f'{verdict_badge(_lead.get("verdict"), _lead)}</div>'
                 f'<a class="sp-lead-h" href="/articles/{esc(_lead["slug"])}.html">'
                 f'{esc(_lead.get("title") or "")}</a>'
                 + (f'<p class="sp-lead-dek">{esc(_dek)}</p>' if _dek else "")
                 + _ledger
                 + f'<div class="bd-brief-foot"><span class="bd-by">Chuck Wando, '
                   f'The GoCheckMySports desk. Every figure links to the source the '
                   f'story cites.</span>'
                   f'<a class="bd-more" href="/articles/{esc(_lead["slug"])}.html">'
                   f'Read the full breakdown</a></div></div>')
        # S-3: the rail rendered <div class="sp-rail"></div> whenever the receipts
        # chart and the edition card both came back empty - a blank third of the page
        # beside the lead. It carries the three cards the audit specifies now, and a
        # rail with nothing in it collapses the row to one column rather than shipping
        # an empty one.
        _rail_cards = [c for c in (where_to_watch_card(W2W_DATA),
                                   _fantasy_tonight_card(SB_DATA, IA_BOARD, IA_DESIG),
                                   track_html) if c]
        if _rail_cards:
            lead_row = (f'<section class="sp-leadrow">{_left}'
                        f'<div class="sp-rail">{"".join(_rail_cards)}</div></section>')
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
    _band = scoreboard_band(SB_DATA, IA_BOARD, WX_DATA) or scores_strip()
    body = _band + f"""<main class="wrap"><h1 class="sr-only">GoCheckMySports: every score, checked</h1><section class="page">
  {lead_row}
  {desk_html}
  {editions_html}
  {w2w_row}
  {track_html}
  {record_sections(items, home=True, board=IA_BOARD)}
  {record_full_index(items)}
  <p class="lede home-lede" style="margin-top:22px">Built with one intention: get the stories
     right and keep the facts honest. The score is a fact; the story gets checked. Real sports
     news verified against official league data and on-record sources, with the rumor and the
     hype stripped out. No hot takes dressed as facts, no paid promotion, and never betting
     advice. Everything here is free, and every source is linked.</p>
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
WX_DATA = None       # set at build by kickoff_weather.load()

NAV_UTILITY = frozenset({"Home", "Latest", "The Edition", "Archive", "About", "Sources"})

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
            '<span class="xc-lab">Across every league</span>' + "".join(out) + '</nav>')


def render_section(slug, title, nav_label, tags, blurb, items, dateline):
    live = section_items(items, tags)
    if live:
        inner = '<div class="grid">' + "".join(card(i) for i in live[:60]) + "</div>"
        if len(live) > 60:
            inner += (f'<p class="fine">Showing the 60 most recent of {len(live)} stories in '
                      f'this section. <a href="/archive.html">The full archive</a> has the rest.</p>')
    else:
        inner = ('<div class="empty"><span class="k">Nothing here yet</span>'
                 '<p style="margin:.6em 0 0">No published stories carry this section yet.</p></div>')
    plain = title.replace("&amp;", "and")
    body = f"""<main class="wrap"><h1 class="sr-only">{esc(plain)}</h1><section class="sec">
    <div class="sec-head"><h2>{title}</h2><span class="bar"></span></div>
    <p class="lede" style="margin:0 0 14px">{blurb}</p>
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
    intro = (f"Every story the desk has published on {_name_mid_sentence(name)}, "
             f"newest first. This page updates with each new development.")
    inner = '<div class="grid">' + "".join(card(i) for i in hub["stories"]) + "</div>"
    body = f"""<main class="wrap"><h1 class="sr-only">{esc(name)}</h1><section class="sec">
    <div class="sec-head"><h2>{esc(name)}</h2><span class="bar"></span></div>
    <p class="lede" style="margin:0 0 14px">{esc(intro)}</p>
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
  <p>Pages load their typefaces from Google Fonts (fonts.googleapis.com and fonts.gstatic.com),
     so your browser makes a request to Google when a page loads. Google processes font requests
     under its own privacy policy.</p>

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
        w("where-to-watch.html", render_where_to_watch(_wks[0], _wks, dateline, current=True))
        for _wk in _wks:
            w(f"where-to-watch/{_w2w_slug(_wk)}.html",
              render_where_to_watch(_wk, _wks, dateline))
        print(f"where to watch: {len(_wks)} week(s), "
              f"{sum(len(x.get('games') or []) for x in _wks)} games, "
              f"as of {_w2w.get('fetched_at')}")

    # S-A: the Scoreboard band's own data. scores_pulse.py is frozen and writes a
    # ticker's worth of each game; the band needs networks, records, period and
    # situation, so this reads the public scoreboards itself.
    global SB_DATA
    SB_DATA = None
    try:
        import scoreboard as _sbmod
        _sbmod.refresh()
        SB_DATA = _sbmod.load()
    except Exception as _e:
        print(f"scoreboard: unavailable ({type(_e).__name__}); band withheld")

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
            print(f"inactives board: {IA_BOARD['total']} players, "
                  f"{len(IA_BOARD['teams'])} teams")

    w("index.html", render_home(items, dateline))
    # S-B3/S-B8: points per game, then the game pages, the live board and the hub.
    # Only games that have started have a players block, so only those are fetched.
    _all_points = {}
    if SB_DATA:
        import fantasy_points as _fpm
        _nfl = [g for L in SB_DATA["leagues"] if L["league"] == "NFL"
                for g in L["games"]]
        for _g in _nfl:
            if _g.get("state") in ("in", "post"):
                _pts = _fpm.for_game(_g["id"])
                if _pts:
                    _all_points[_g["id"]] = _pts
        _cards = 0
        for _g in _nfl:
            # S-F: the card is drawn from the same game record the page renders, so
            # the number in a group chat and the number on the page cannot disagree.
            try:
                import share_cards as _sc
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
    locs = ["/", "/news.html"] + [f"/sections/{sl}.html" for sl, _t, _n, _g, _b in SECTIONS] + [
            "/archive.html", "/bottom-line.html", "/method.html", "/about.html", "/standards.html",
            "/privacy.html", "/terms.html"]
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
    if W2W_LIVE and W2W_DATA:
        topic_locs.append("/where-to-watch.html")
        topic_locs += [f"/where-to-watch/{_w2w_slug(_wk)}.html"
                       for _wk in (W2W_DATA.get("weeks") or [])]
    prio = locs + topic_locs + hub_paths + [f"/articles/{i['slug']}.html" for i in prio_arts]
    archive = [f"/news/archive/{m}.html" for m in _news_month_archive(_s6_live)] \
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
