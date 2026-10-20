#!/usr/bin/env python3
"""structured.py: SportsEvent and BroadcastEvent for the game and team pages (Sprint S-3a item 2).

Pure builders over the game record the page already renders, so the markup cannot say what the
page does not: the names are the page's names, the start is the page's kickoff with its offset, the
carriers are the where-to-watch block's. Schema.org's BroadcastEvent is a live broadcast of an
event on a BroadcastService, so there is one per carrier and none when the page names none.
No dash characters in any string (the house rule), and nothing here calls out.
"""

import datetime
import re
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SPORT = {"NFL": "American football", "CFB": "American football"}
LEAGUE = {"NFL": "National Football League", "CFB": "NCAA Division I FBS football"}


def _clean(s):
    return re.sub(r"\s*[–—]\s*", ", ", str(s or "")).strip()


def iso_et(utc):
    """An ISO start time with its Eastern offset, or '' when the time is not known."""
    try:
        d = datetime.datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
    except ValueError:
        return ""
    return d.astimezone(ET).isoformat(timespec="seconds")


def team_node(side, league):
    name = _clean(side.get("full") or side.get("name") or side.get("abbr"))
    return {"@type": "SportsTeam", "name": name, "sport": SPORT.get(league, "American football")}


def game_graph(g, origin, carriers=(), venue_city="", page_path=None, venue_region="", description="",
               image=""):
    """The @graph for one game page: the SportsEvent, then a BroadcastEvent per carrier.

    S-5.2: the address is the city and state the page prints beside the venue, and the
    description and image are the page's own meta description and og:image, so the event carries
    what Google's Event documentation requires and recommends without saying anything the page
    does not (measure_canary.SPORTS_EVENT_REQUIRED lists them with the source)."""
    league = g.get("league") or "NFL"
    away, home = g.get("away") or {}, g.get("home") or {}
    an = _clean(away.get("full") or away.get("name"))
    hn = _clean(home.get("full") or home.get("name"))
    path = page_path or f'/games/{g.get("id")}.html'
    url = origin + path
    ev_id = url + "#event"
    start = iso_et(g.get("start_utc"))
    venue = _clean(re.sub(r"\s*\(.*\)\s*$", "", g.get("venue") or ""))
    place = {"@type": "Place", "name": venue or "Venue to be announced"}
    if venue_city:
        place["address"] = {"@type": "PostalAddress", "addressLocality": _clean(venue_city)}
        if venue_region:
            place["address"]["addressRegion"] = _clean(venue_region)
    ev = {"@type": "SportsEvent", "@id": ev_id, "name": f"{an} at {hn}", "url": url,
          "sport": SPORT.get(league, "American football"), "startDate": start,
          "eventStatus": "https://schema.org/EventScheduled",
          "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
          "location": place, "awayTeam": team_node(away, league), "homeTeam": team_node(home, league),
          "competitor": [team_node(away, league), team_node(home, league)],
          # schema.org's superEvent takes an Event, and a league is an organization: the league is
          # the organizer (a SportsOrganization), which the schema accepts on an Event.
          "organizer": {"@type": "SportsOrganization", "name": LEAGUE.get(league, league),
                        "sport": SPORT.get(league, "American football")}}
    if description:
        ev["description"] = _clean(description)
    if image:
        ev["image"] = [image]
    graph = [ev]
    seen = set()
    for c in carriers or []:
        c = _clean(c)
        if not c or c.lower() in seen:
            continue
        seen.add(c.lower())
        graph.append({"@type": "BroadcastEvent", "name": f"{an} at {hn} on {c}", "isLiveBroadcast": True,
                      "startDate": start, "broadcastOfEvent": {"@id": ev_id},
                      "publishedOn": {"@type": "BroadcastService", "name": c}})
    return {"@context": "https://schema.org", "@graph": graph}


def team_graph(team, league, origin, path, next_game=None, carriers=()):
    """A SportsTeam for a team page, pointing at its next game's event when one is known.

    S-5.2: one event, one page. The next game is its game page's SportsEvent, named here by its
    @id through Organization.event and not restated: a copy on the team page has no page of its
    own to stay true to (on the October 20 build four NFL team pages restated a next game whose
    game page was never built, with no carrier and a URL that answered 404), and it would state a
    venue address the team page does not print. The caller passes next_game only when its game
    page is built. `carriers` is kept for callers and no longer used."""
    name = _clean(team.get("name") or team.get("school"))
    node = {"@type": "SportsTeam", "@id": origin + path + "#team", "name": name, "url": origin + path,
            "sport": SPORT.get(league, "American football"),
            "memberOf": {"@type": "SportsOrganization", "name": LEAGUE.get(league, league)}}
    if next_game and next_game.get("id"):
        node["event"] = {"@id": f'{origin}/games/{next_game.get("id")}.html#event'}
    return {"@context": "https://schema.org", "@graph": [node]}
