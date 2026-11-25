#!/usr/bin/env python3
"""current_canary.py: S-DONE point 7, the fantasy surfaces show the current NFL week by date.

The fixture is Wednesday, November 25, 2026, 9:00 AM ET: Week 12 by date (the week rolled Tuesday
at 6:00 AM), its first game that night. The desk holds what it held on production that morning:
last week's inactive lists (Washington, Monday night), a box score from last Monday's game, this
week's designations, and a schedule file that has dropped Week 11.

  the week        the inactives board is headed by the week the calendar says, never "Week 11,
                  final"; with no Week 12 list posted it says so and says when the first is due
  no old lists    the hub draws no team card from last week under this week's heading, and never
                  the words "no lists posted yet" over posted lists
  points          "Points this week" is this week's games only; last week's box score is not this
                  week's points. The points page always exists (its URL does not come and go) and
                  says when the first game is, with nothing to show
  stamps          each surface carries the time of its own data: the designations theirs, the
                  points the reading's, a player page the report's; never the build's clock
  the carrier     the hub and a player page print the network's name, not the feed's code

USAGE  python3 current_canary.py     exit 1 on any failure; no network, no model call
"""

import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
UTC = datetime.timezone.utc


def _u(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def _fixture():
    def wg(i, a, aid, h, hid, kick, win):
        return {"id": i, "away": a, "home": h, "away_id": aid, "home_id": hid, "kickoff_utc": kick,
                "kickoff_et": "", "day_et": "", "window": win, "state": "pre", "completed": False, "status": "",
                "carriers": [{"name": "Netflix", "market": "National", "type": "TV"}]}
    w2w = {"fetched_at": "2026-11-25T13:55:00Z", "weeks": [
        {"season": 2026, "week": 12, "games": [
            wg("5001", "GB", "9", "LAR", "14", "2026-11-26T01:00Z", "Wednesday"),
            wg("5002", "CHI", "3", "DET", "8", "2026-11-26T18:00Z", "Thursday night")]},
        {"season": 2026, "week": 13, "games": [
            wg("6001", "NYJ", "20", "MIA", "15", "2026-12-06T18:00Z", "Sunday afternoon, 1:00 ET")]}]}

    def sg(i, a, h, kick, st, net, sa="0", sh="0"):
        return {"league": "NFL", "id": i, "state": st, "completed": st == "post", "status_short": "Final" if st == "post" else "",
                "detail": "", "period": 4 if st == "post" else 0, "start_utc": kick, "network": net,
                "away": {"abbr": a, "full": a, "name": a, "score": sa, "id": a}, "home": {"abbr": h, "full": h, "name": h, "score": sh, "id": h}}
    sbd = {"fetched_at": "2026-11-25T13:55:00Z", "leagues": [{"league": "NFL", "games": [
        sg("4001", "CIN", "WSH", "2026-11-24T01:15Z", "post", "ESPN", "20", "22"),
        sg("5001", "GB", "LAR", "2026-11-26T01:00Z", "pre", "CBSSN")]}]}
    was = {"name": "Athan Kaliakmanis", "pos": "QB", "reason": "Coach's Decision", "first_seen": "2026-11-24T00:00:42Z",
           "day": "2026-11-23", "player_id": "1"}
    board = {"day": "2026-11-24", "first_poll": "2026-11-24T00:00:42Z", "last_poll": "2026-11-24T01:05:50Z",
             "last_change": "2026-11-24T00:00:42Z", "total": 1, "teams": [
                 {"team": "Washington Commanders", "id": "28", "players": [was], "count": 1,
                  "first_seen": "2026-11-24T00:00:42Z", "first_sighting": "2026-11-24T00:00:42Z",
                  "last_added": "2026-11-24T00:00:42Z", "incomplete": False, "reconciled_at": None,
                  "by_day": [{"day": "2026-11-23", "players": [was], "count": 1, "first_seen": "2026-11-24T00:00:42Z"}]}]}
    desig = {"groups": {"Out": [{"name": "A"}], "Doubtful": [], "Questionable": [{"name": "B"}, {"name": "C"}]},
             "total": 3, "last_poll": "2026-11-25T09:20:00Z"}
    pts = {"4001": {"p1": {"name": "Dak Prescott", "pos": "QB", "team": "DAL", "ppr": 35.9, "half": 35.9, "standard": 35.9,
                           "line": ["325 pass yds, 4 TD"]}}}
    return w2w, sbd, board, desig, pts


def _text(html):
    html = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html or "")
    m = re.search(r"(?is)<main\b.*?</main>", html)
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", m.group(0) if m else html)))


def current_canary():
    import build_manifest as bm
    import site_build as sb
    f = []
    w2w, sbd, board, desig, pts = _fixture()
    keep = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.IA_DESIG)
    try:
        sb._NOW_CACHE = _u("2026-11-25T14:00:00Z")          # Wednesday 9:00 AM ET
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.IA_BOARD, sb.IA_DESIG = sbd, w2w, True, board, desig
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        if sb.nfl_week()[0] != 12:
            return [f"current: the fixture's week by date is {sb.nfl_week()[0]}, not 12; the cases prove nothing"]
        # the week
        if sb._ia_week() != (12, False):
            f.append(f"current: the inactives board's week is {sb._ia_week()}, not Week 12 by date")
        if sb._ia_heading(board) != "Week 12 inactives":
            f.append(f"current: the board is headed {sb._ia_heading(board)!r} on the Wednesday of Week 12")
        hub = _text(sb.render_fantasy_hub(board, desig, pts, None, sbd, ""))
        ina = _text(sb.render_inactives(board, w2w, "") or "")
        # no old lists under this week's heading
        if "Washington Commanders" in hub:
            f.append("current: the hub draws Washington's Week 11 list under this week's heading")
        if "final" in hub.lower() or "final" in ina.lower()[:200]:
            f.append("current: a fantasy surface is headed by last week ('final') on the Wednesday of Week 12")
        for name, t in (("the hub", hub), ("the inactives board", ina)):
            if "Week 12 inactives" not in t:
                f.append(f"current: {name} does not name Week 12's inactives")
            if "Wednesday's lists post about 6:30 PM ET" not in t:
                f.append(f"current: {name} does not say when Week 12's first lists are due (Wednesday, about 6:30 PM ET)")
        # points
        if "Points this week" in hub or "Dak Prescott" in hub:
            f.append("current: the hub prints last Monday's box score as 'Points this week'")
        live = sb.render_fantasy_live(pts, "")
        lt = _text(live or "")
        if not live:
            f.append("current: the points page is not written when no game of the week has been played; its URL must not come and go")
        elif "Dak Prescott" in lt or "Week 12" not in lt or "8:00 PM ET" not in lt:
            f.append(f"current: with no Week 12 game played the points page reads {lt[:160]!r}")
        this = {"5001": {"p9": {"name": "Jordan Love", "pos": "QB", "team": "GB", "ppr": 21.4, "half": 21.4,
                                "standard": 21.4, "line": ["250 pass yds, 2 TD"]}}}
        hub2 = _text(sb.render_fantasy_hub(board, desig, dict(pts, **this), None, sbd, ""))
        if "Points this week" not in hub2 or "Jordan Love" not in hub2 or "Dak Prescott" in hub2:
            f.append("current: with a Week 12 box score the hub's points are not that game's alone")
        elif "Updated Nov 25, 8:55 AM ET" not in hub2:
            f.append("current: the hub's points carry no stamp of their own reading (Nov 25, 8:55 AM ET)")
        lt2 = _text(sb.render_fantasy_live(dict(pts, **this), "") or "")
        if "Jordan Love" not in lt2 or "Dak Prescott" in lt2 or "Updated Nov 25, 8:55 AM ET" not in lt2:
            f.append("current: the points page is not Week 12's players under the reading's own time")
        # stamps
        if "Updated Nov 25, 4:20 AM ET" not in hub:
            f.append("current: the hub's designations carry no stamp of their own (the report read at 4:20 AM ET)")
        player = {"name": "A.J. Brown", "slug": "a-j-brown", "team": "NE", "pos": "WR", "designation": "Doubtful",
                  "detail": "Hamstring", "inactive_seen": "", "designations": [],
                  "next": {"opponent": "LAC", "home": False, "day": "Sun, Nov 29", "kickoff_et": "4:05 PM ET", "network": "CBSSN"}}
        pt = _text(sb.render_player_page(player, board, ""))
        if "Updated Nov 25, 4:20 AM ET" not in pt:
            f.append("current: a player page with a designation and no inactive listing carries no stamp")
        # the carrier
        if "CBSSN" in pt or "CBS Sports Network" not in pt:
            f.append("current: a player page prints the feed's code for the carrier")
        if "CBSSN" in hub or "CBS Sports Network" not in hub:
            f.append("current: the hub's Tonight block prints the feed's code for the carrier")
        # Jack's ruling of November 24, 2026: a story lane with no new item in 14 days comes off the
        # navigation and the home, and its hub prints one line with the date of its last item
        f += _lanes(sb)
    finally:
        sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.IA_DESIG = keep
    return f


def _lanes(sb):
    """The stale-lane rule on the committed corpus at the fixture's clock (Wednesday November 25, 2026;
    the desk's last story and last Edition are of October 12, the Record's last piece of October 8)
    and on planted clocks."""
    f = []
    now = sb._build_now()
    keep = (sb.LANE_QUIET, sb.EDITION_HREF)
    try:
        items = sb.load_content()
        quiet = sb.lanes_quiet(items, now)
        for lane, day in (("record", "2026-10-08"), ("storylines", "2026-10-12"), ("edition", "2026-10-12")):
            t = quiet.get(lane)
            if lane not in quiet:
                f.append(f"lanes: {lane} is read as live on November 25; its last item is of {day}")
            elif not t or t.astimezone(sb._ET).strftime("%Y-%m-%d") != day:
                f.append(f"lanes: {lane}'s last item is read as {t}, not {day}")
        early = sb.lanes_quiet(items, _u("2026-10-20T14:00:00Z"))
        if any(k in early for k in ("record", "storylines", "edition")):
            f.append(f"lanes: eight days after the last story the lanes are read as quiet ({sorted(early)}); the window is 14 days")
        if sb.lane_line(_u("2026-10-12T23:43:00Z")) != "Nothing new since October 12, 2026.":
            f.append(f"lanes: the line reads {sb.lane_line(_u('2026-10-12T23:43:00Z'))!r}")
        sb.EDITION_HREF = "/archive.html"
        sb.LANE_QUIET = quiet
        foot = sb.footer()
        for label in ("Storylines", "The Record", "The Edition"):
            if f">{label}</a>" in foot:
                f.append(f"lanes: the footer still links {label}, a lane with nothing new in 14 days")
        for label in ("Archive", "About", "How we work"):
            if f">{label}</a>" not in foot:
                f.append(f"lanes: the footer lost {label}, which is not a story lane")
        rec = _text(sb.render_keepers(items, ""))
        if "Nothing new since October 8, 2026." not in rec:
            f.append("lanes: the Record's page does not say 'Nothing new since October 8, 2026.'")
        news = _text(sb.render_news_hub(items, ""))
        if "Nothing new since October 12, 2026." not in news:
            f.append("lanes: the Storylines page does not say 'Nothing new since October 12, 2026.'")
        sb.LANE_QUIET = {}
        foot = sb.footer()
        if not all(f">{label}</a>" in foot for label in ("Storylines", "The Record", "The Edition")):
            f.append("lanes: with every lane live the footer does not link all three")
        if "Nothing new since" in _text(sb.render_news_hub(items, "")):
            f.append("lanes: a live Storylines page prints the quiet line")
        # the Wire: off the home when it has had nothing in 14 days, and its page says since when
        sb.LANE_QUIET = {"wire": _u("2026-02-08T03:30:00Z")}
        if sb.home_lead(items, now).strip():
            f.append("lanes: the home still carries the Wire's lead with the Wire quiet since February 8")
        if "Nothing new since February 7, 2026." not in _text(sb.render_wire(items, "", now) or ""):
            f.append("lanes: the Wire's page does not say when it last had something (February 7, 2026, ET)")
    finally:
        sb.LANE_QUIET, sb.EDITION_HREF = keep
    return f


if __name__ == "__main__":
    fs = current_canary()
    for x in fs:
        print("::error::" + x)
    print("CURRENT CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
