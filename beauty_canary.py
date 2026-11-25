#!/usr/bin/env python3
"""beauty_canary.py: S-DONE point 10, the rules behind what a stranger sees first on the home.

  today first     the home's byte budget draws today's college games before any other day's. It
                  drew by rank alone, so on a Tuesday with two unranked games the open day held no
                  card at all, only "2 more college games. All scores".
  the windows     the row of Sunday kickoff windows under the day tabs says it is Sunday's
                  ("1:00 6, 4:05 and 4:25 3, Night 1" named nothing)
  the wall        a game under way whose kickoff forecast is gone draws one plate, "Under way",
                  not three reading n/a

The band's geometry (the page under the band starts where the band ends; under 720px the band
ends under its controls) is read in a browser by plate_canary.type_widths.

USAGE  python3 beauty_canary.py     exit 1 on any failure; no network
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


def _g(i, lg, a, h, kick, rank=None, state="pre", **kw):
    g = {"league": lg, "id": i, "state": state, "completed": state == "post", "status_short": "", "detail": "",
         "period": 0, "start_utc": kick, "network": "ESPN", "venue": "Stadium", "venue_city": "Town", "venue_state": "OH",
         "away": {"abbr": a, "full": a + " Team", "name": a, "school": a, "score": "0", "id": "a" + i, "rank": None},
         "home": {"abbr": h, "full": h + " Team", "name": h, "school": h, "score": "0", "id": "h" + i, "rank": rank}}
    g.update(kw)
    return g


def beauty_canary():
    import build_manifest as bm
    import site_build as sb
    f = []
    # Tuesday November 24, 2026, 10:00 AM ET. Two unranked college games tonight; forty ranked ones Saturday.
    tue = [_g("t1", "CFB", "KENT", "EMU", "2026-11-25T00:00Z"), _g("t2", "CFB", "M-OH", "WMU", "2026-11-25T00:00Z")]
    sat = [_g(f"s{n}", "CFB", f"A{n}", f"B{n}", "2026-11-28T17:00Z", rank=(n % 25) + 1) for n in range(40)]
    sun = [_g("n1", "NFL", "NO", "CIN", "2026-11-29T18:00Z"), _g("n2", "NFL", "SEA", "SF", "2026-11-29T21:25Z")]
    sbd = {"fetched_at": "2026-11-24T14:55:00Z", "leagues": [{"league": "NFL", "games": sun}, {"league": "CFB", "games": tue + sat}]}
    keep = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.HOME_BUDGET, sb.CX_DATA, sb.GAME_PAGE_IDS)
    try:
        sb._NOW_CACHE = _u("2026-11-24T15:00:00Z")
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.CX_DATA = sbd, None, False, None
        sb.GAME_PAGE_IDS = set()
        sb.MANIFEST = bm.build(sb._build_now(), sbd, None)
        full = sb.render_home([], "")
        if 'data-gid="t1"' not in full or 'data-gid="s39"' not in full:
            return ["beauty: the fixture's home does not draw its games with room for all; the cases prove nothing"]
        # a budget that fits the chrome, the NFL games and about fourteen of the 42 college cards
        sb.HOME_BUDGET = 1
        bare = len(sb.render_home([], "").encode("utf-8"))          # every college card cut
        one = (len(full.encode("utf-8")) - bare) / 42.0
        sb.HOME_BUDGET = int(bare + 14.5 * one)
        cut = sb.render_home([], "")
        drawn = set(re.findall(r'<article class="tk-c[^"]*" data-gid="([^"]+)"', cut))
        if not (10 <= len(drawn) <= 30):
            f.append(f"beauty: the cut fixture draws {len(drawn)} cards; the budget case proves nothing")
        if not {"t1", "t2"} <= drawn:
            f.append(f"beauty: with the budget cutting college games, the home leaves out today's ({sorted({'t1', 't2'} - drawn)}) "
                     f"and draws {len(drawn & {g['id'] for g in sat})} of Saturday's")
        if "more college game" not in cut:
            f.append("beauty: the cut fixture cut nothing")
        # the windows row names its day
        band = re.search(r'(?s)<div class="tk-tabs wb-wins">.*?</div>', cut)
        if not band:
            f.append("beauty: the fixture's home draws no Sunday windows row")
        elif "Sunday" not in re.sub(r"<[^>]+>", " ", band.group(0)):
            f.append("beauty: the Sunday windows row does not say it is Sunday's: "
                     + re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", band.group(0))).strip())
        # the wall: a game under way with its kickoff hour gone
        live = _g("w1", "NFL", "KC", "BUF", "2026-11-24T14:00Z", state="in", status_short="5:53 - 2nd")
        sb.SB_DATA = {"fetched_at": "2026-11-24T14:55:00Z", "leagues": [{"league": "NFL", "games": [live] + sun}]}
        sb.MANIFEST = bm.build(sb._build_now(), sb.SB_DATA, None)
        sb.CX_DATA = {"games": {"w1": {"status": "forecast", "kickoff_hour": {}, "flags": {}, "words": {}}}}
        wall = sb.wall(sb.SB_DATA)
        row = re.search(r'(?s)KC.*?BUF.*?(?=<a class="wl-row"|<div class="wl-row"|</div>\s*</div>)', wall or "")
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row.group(0))) if row else ""
        if not row:
            f.append("beauty: the fixture's wall draws no row for the game under way")
        elif "n/a" in txt or "Under way" not in txt:
            f.append(f"beauty: the wall draws a game under way with no kickoff forecast as {txt.strip()[:120]!r}")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.HOME_BUDGET, sb.CX_DATA, sb.GAME_PAGE_IDS) = keep
    return f


if __name__ == "__main__":
    fs = beauty_canary()
    for x in fs:
        print("::error::" + x)
    print("BEAUTY CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
