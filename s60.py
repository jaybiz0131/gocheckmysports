#!/usr/bin/env python3
"""s60.py: the scoreboard's three states and the honest card lines (S-60, 21 November 2026).

At 3:43 PM ET on a 58-game Saturday nobody could find what was on. The Scores page is now Live,
Upcoming and Final, and every card says only what the feed said. Pure functions; the build and the
canary hand them a clock.

  phase()          live | upcoming | final | stale for one game at `now`
  stale            kickoff more than STALE_MIN ago and the feed still says it has not started. It
                   counts in Live (a reader looking for what is on wants it) and says why it is quiet.
  live_label()     "5:53 2nd", "Halftime", "End 3rd", "OT", "2OT 4:12"
  final_label()    "Final", "Final/2OT", with the time the desk first saw it final when it has one
  order_*()        Live by least time remaining, then rank, then kickoff; Upcoming by kickoff;
                   Final by the time seen final, newest first
  default_tab()    Live while any game is on, else Upcoming while any is to come, else Final
  weather_absent() why a card has no conditions, never the word "missing"
"""

import datetime
import re
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
STALE_MIN = 10
FAR_HOURS = 48
TABS = ("live", "upcoming", "final")
# (periods in regulation, minutes in one) for the leagues whose clocks the feed runs
PERIODS = {"NFL": (4, 15), "CFB": (4, 15), "NBA": (4, 12), "WNBA": (4, 10), "NHL": (3, 20)}
_ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
BIG = 10 ** 6


def utc(iso):
    try:
        d = datetime.datetime.fromisoformat(str(iso or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)


def et_clock(dt):
    return dt.astimezone(ET).strftime("%-I:%M %p") + " ET"


def is_stale(g, now):
    if g.get("state") != "pre":
        return False
    k = utc(g.get("start_utc"))
    return bool(k) and (now - k) > datetime.timedelta(minutes=STALE_MIN)


def phase(g, now):
    st = g.get("state")
    if st == "in":
        return "live"
    if st == "post":
        return "final"
    return "stale" if is_stale(g, now) else "upcoming"


def tab_of(g, now):
    """The state tab a game sits under: a stale game is listed with Live."""
    p = phase(g, now)
    return "live" if p == "stale" else p


def _clock(g):
    """M:SS the feed is running, or None. The feed's detail is "0:00" until a game is on."""
    for s in ((g.get("detail") or "").strip(), (g.get("status_short") or "").strip()):
        m = re.search(r"\b(\d{1,2}:\d{2})\b", s)
        if m and m.group(1) != "0:00":
            return m.group(1)
    return None


def _period(g):
    try:
        return int(g.get("period"))
    except (TypeError, ValueError):
        return 0


def _ot_word(g):
    """"OT", "2OT" from the feed's own word, else from the period count; None when not overtime."""
    s = (g.get("status_short") or "").upper()
    m = re.search(r"\b(\d?)OT\b", s)
    reg = PERIODS.get(g.get("league") or "", (4, 15))[0]
    if m:
        return (m.group(1) + "OT") if m.group(1) not in ("", "1") else "OT"
    if _period(g) > reg and g.get("state") in ("in", "post"):
        n = _period(g) - reg
        return "OT" if n == 1 else f"{n}OT"
    return None


def live_label(g):
    s = (g.get("status_short") or "").strip()
    low = s.lower()
    if "half" in low:
        return "Halftime"
    m = re.match(r"(?i)^end\s+(?:of\s+)?(?:the\s+)?(\d)(?:st|nd|rd|th)?\b", s)
    if m:
        return f"End {_ORD.get(int(m.group(1)), m.group(1) + 'th')}"
    ot = _ot_word(g)
    clk = _clock(g)
    if ot:
        return f"{ot} {clk}" if clk else ot
    m = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\S+)$", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    if clk and _period(g) in _ORD:
        return f"{clk} {_ORD[_period(g)]}"
    return s or "In progress"


def final_label(g):
    s = (g.get("status_short") or "").strip()
    ot = _ot_word(g)
    word = f"Final/{ot}" if ot else "Final"
    if s.lower().startswith("final/") and not ot:
        word = s
    seen = utc(g.get("final_seen_utc"))
    return f"{word} as of {et_clock(seen)}" if seen else word


def stale_line(fetched_iso):
    t = utc(fetched_iso)
    since = et_clock(t) if t else "the last read"
    return f"No update since {since}, waiting for the feed"


def remaining(g):
    """Seconds of regulation left by the clock the feed gave, BIG when it gave none."""
    n, ln = PERIODS.get(g.get("league") or "", (0, 0))
    if not n:
        return BIG
    s = (g.get("status_short") or "").lower()
    p = _period(g)
    if "half" in s:
        return (n - n // 2) * ln * 60
    if re.match(r"^end\b", s) and p:
        return max(0, n - p) * ln * 60
    clk = _clock(g)
    if not p or not clk:
        return BIG
    mm, ss = clk.split(":")
    return max(0, n - p) * ln * 60 + int(mm) * 60 + int(ss)


def order_live(games, now, rank=lambda g: 99):
    """Least time remaining first, then the better poll rank, then kickoff. Stale games trail."""
    return sorted(games, key=lambda g: (1 if is_stale(g, now) else 0, remaining(g), rank(g),
                                        g.get("start_utc") or ""))


def order_upcoming(games, now, rank=lambda g: 99):
    return sorted(games, key=lambda g: (g.get("start_utc") or "", rank(g)))


def order_final(games, now, rank=lambda g: 99):
    """Newest final first by the time the desk saw it final; a final with no such time sorts by
    kickoff, after those that have one."""
    return sorted(games, key=lambda g: (g.get("final_seen_utc") or "", g.get("start_utc") or ""),
                  reverse=True)


ORDER = {"live": order_live, "upcoming": order_upcoming, "final": order_final}


def default_tab(games, now):
    c = {t: 0 for t in TABS}
    for g in games:
        c[tab_of(g, now)] += 1
    if c["live"]:
        return "live"
    return "upcoming" if c["upcoming"] else "final"


def counts(games, now):
    c = {t: 0 for t in TABS}
    for g in games:
        c[tab_of(g, now)] += 1
    return c


def card_line(g, now, fetched_iso=""):
    """(text, css class) for the state word of one card."""
    p = phase(g, now)
    if p == "live":
        return live_label(g), "st-live"
    if p == "final":
        return final_label(g), "st-final"
    if p == "stale":
        return stale_line(fetched_iso), "st-stale"
    k = utc(g.get("start_utc"))
    return (et_clock(k) if k else ""), "st-up"


def weather_absent(g, e, now):
    """(text, css class) for a card with no kickoff conditions. Never the word "missing"."""
    if g.get("venue_indoor") or (e or {}).get("status") in ("indoor", "roofed"):
        return "Indoor", ""
    k = utc(g.get("start_utc"))
    if k and (k - now) > datetime.timedelta(hours=FAR_HOURS):
        return "Conditions at kickoff", ""
    return "Conditions unavailable", "st-stale"


def stamp_finals(payload, prev, fetched_iso):
    """final_seen_utc on every final: carried from the last snapshot for a game that was already
    final there. A game first read as final now gets this read's time; a game the last snapshot
    already held as final with no stamp stays unstamped (the desk did not see it finish)."""
    seen, was_post = {}, set()
    for L in (prev or {}).get("leagues") or []:
        for g in L.get("games") or []:
            key = (L.get("league"), str(g.get("id")))
            if g.get("state") == "post":
                was_post.add(key)
            if g.get("final_seen_utc"):
                seen[key] = g["final_seen_utc"]
    for L in payload.get("leagues") or []:
        for g in L.get("games") or []:
            key = (L.get("league"), str(g.get("id")))
            if g.get("state") != "post":
                g.pop("final_seen_utc", None)
            elif key in seen:
                g["final_seen_utc"] = seen[key]
            elif key in was_post:
                g.pop("final_seen_utc", None)
            else:
                g["final_seen_utc"] = fetched_iso
    return payload


def cadence_line(day_weekday, every_min, weekend=(5, 6)):
    """", refreshed every N minutes" on a day the schedule runs every N, else nothing."""
    return f", refreshed every {every_min} minutes" if day_weekday in weekend and every_min else ""
