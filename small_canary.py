#!/usr/bin/env python3
"""small_canary.py: Sprint S-1 item 4, the small truths (12 October 2026).

Each check names the break it exists for and was seen red first (U-9).

  fantasy-link   the Fantasy link in the header and on the phone bar points at /fantasy/index
  points-stamp   the points block on the Fantasy hub carries the manifest's stamp
  whole-stats    a player line renders whole or not at all, never cut mid-stat
  not-a-score    an odds value in the score field never renders as a score
  overtime       a period past regulation prints only when the game went to overtime
  player-search  the search's data source is the file the site serves, and it has players

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""
import datetime as _d
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def small_canary():
    import build_manifest as bm
    import fantasy_points as fp
    import site_build as sb
    from truth_canary import _fixture
    fails = []
    u, sbd, w2w, _ = _fixture(sb)
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
           sb.LIVE_POINTS, sb.IA_DESIG)
    try:
        sb._NOW_CACHE = u("2026-10-11T09:00")
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE = sbd, w2w, True
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)

        # fantasy-link
        page = sb.render_scores_page(sbd, {}, "")
        head = re.findall(r'<a href="([^"]*)">Fantasy</a>', page)
        bar = [h for h, inner in re.findall(r'<a class="tb-item[^"]*" href="([^"]*)">(.*?)</a>', page, re.S)
               if inner.endswith("<span>Fantasy</span>")]
        if head != ["/fantasy/index.html"]:
            fails.append(f"small: the header Fantasy link points at {head}, not /fantasy/index")
        if bar != ["/fantasy/index.html"]:
            fails.append(f"small: the phone bar Fantasy link points at {bar}, not /fantasy/index")

        # points-stamp
        pts = {"g1": {"p1": {"name": "A Player", "team": "KC", "pos": "QB", "ppr": 30.0,
                             "half": 30.0, "standard": 30.0, "line": ["x"]}}}
        hub = sb.render_fantasy_hub(None, {"groups": {"Out": ["a"]}, "last_poll": "2026-10-11T12:00:00Z"},
                                    pts, None, sbd, "")
        m = sb.MANIFEST
        block = hub[hub.index("Points this week"):] if hub and "Points this week" in hub else ""
        want = f"Updated {m['data_stamp'] or m['stamp']}".replace(" ET", " ET")
        stamp = re.search(r'class="fx-asof">([^<]*)<', block)
        if not block:
            fails.append("small: the Fantasy hub has no points block")
        elif not stamp or not stamp.group(1).startswith("Updated "):
            fails.append("small: the points block carries no stamp")
        elif stamp.group(1) != want.replace("Updated ", "Updated ") and \
                stamp.group(1).split(", ", 1)[-1] != want.split(", ", 1)[-1]:
            fails.append(f"small: the points block stamp reads {stamp.group(1)!r}, the manifest says {want!r}")

        # whole-stats
        if sb._fit_stats(["12 att", "79 yds", "1 td"], limit=14, sep=", ") != "12 att, 79 yds":
            fails.append("small: _fit_stats cut or dropped whole stats that fit")
        if sb._fit_stats(["12 att", "79 yds", "1 td"], limit=12, sep=", ") != "12 att":
            fails.append("small: _fit_stats printed a stat that does not fit")
        if sb._fit_stats(["a very long first stat that cannot fit"], limit=10) != "":
            fails.append("small: _fit_stats printed a first stat that does not fit, cut")
        parts = ["26/38 passing", "327 passing yds", "4 passing td", "1 int"]
        game = {"league": "NFL", "id": "XG", "state": "post", "start_utc": "2026-10-11T17:00:00Z",
                "away": {"abbr": "AAA", "score": "31", "name": "A", "full": "A"},
                "home": {"abbr": "BBB", "score": "24", "name": "B", "full": "B"}}
        sb.LIVE_POINTS = {"XG": {"p": {"name": "Q Back", "team": "AAA", "pos": "QB", "ppr": 25.0,
                                       "half": 25.0, "standard": 25.0, "line": parts}}}
        rows = sb._tk_leaders(game)
        got = rows[0][1] if rows else None
        okset = ["; ".join(parts[:k]) for k in range(0, len(parts) + 1)]
        if got not in okset:
            fails.append(f"small: the leader line reads {got!r}, which is cut mid-stat")
        if got == "; ".join(parts):
            fails.append("small: the fixture line fits whole, so it proves nothing about the cut")
        feed = dict(game, id="FG", leaders=[{"cat": "PASS", "name": "Q Back", "team": "1",
                                            "line": "26/38, 327 YDS, 4 TD, 1 INT, 2 SACKS, 3 FUM"}])
        sb.LIVE_POINTS = {}
        frow = sb._tk_leaders(feed)
        fl = frow[0][1] if frow else ""
        if not "26/38, 327 YDS, 4 TD, 1 INT, 2 SACKS, 3 FUM".startswith(fl) or \
                (fl and not "26/38, 327 YDS, 4 TD, 1 INT, 2 SACKS, 3 FUM".split(fl)[1].startswith(", ")
                 and fl != "26/38, 327 YDS, 4 TD, 1 INT, 2 SACKS, 3 FUM"):
            fails.append(f"small: the feed's leader line reads {fl!r}, cut mid-stat")

        # not-a-score
        for state in ("pre", "in", "post"):
            g = {"league": "NHL", "id": "H" + state, "state": state,
                 "start_utc": "2026-10-11T23:00:00Z", "status_short": "",
                 "away": {"abbr": "BOS", "score": "-218", "name": "B", "full": "B"},
                 "home": {"abbr": "NYR", "score": "+180", "name": "N", "full": "N"}}
            html = sb._tk_card(g, sb._ia_index({"teams": []})) + sb._tk_fold(g, sb._ia_index({"teams": []}))
            if "-218" in re.sub(r"<[^>]+>", " ", html) or "+180" in re.sub(r"<[^>]+>", " ", html):
                fails.append(f"small: an odds value in the score field printed on a {state} NHL card")
        if sb._tk_score({"score": "3"}) != 3 or sb._tk_score({"score": "0"}) != 0:
            fails.append("small: a real score no longer renders")

        # overtime
        def cols(league, per, short):
            g = {"league": league, "id": "L", "state": "post", "status_short": short,
                 "away": {"abbr": "AAA", "score": "10", "periods": per},
                 "home": {"abbr": "BBB", "score": "7", "periods": per}}
            return re.findall(r"<th>([^<]*)</th>", sb._tk_linescore(g).split("<tbody>")[0])
        for league, per, short, want_cols in (
                ("NFL", ["7", "3", "0", "0", "0"], "Final", ["1", "2", "3", "4"]),
                ("NFL", ["7", "3", "0", "0", "0"], "Final/OT", ["1", "2", "3", "4", "OT"]),
                ("CFB", ["7", "3", "0", "0"], "Final", ["1", "2", "3", "4"]),
                ("NHL", ["1", "0", "2", "0"], "Final", ["1", "2", "3"]),
                ("NHL", ["1", "0", "2", "0"], "Final/OT", ["1", "2", "3", "OT"])):
            got_c = cols(league, per, short)
            if got_c != want_cols:
                fails.append(f"small: a {league} linescore {short!r} with {len(per)} periods has "
                             f"columns {got_c}, expected {want_cols}")

        # player-search
        pc = sb.player_check_block()
        src = re.search(r'data-src="([^"]*)"', pc)
        if not src:
            fails.append("small: the player search has no data source")
        else:
            f = os.path.join(HERE, "site", src.group(1).lstrip("/"))
            try:
                data = json.load(open(f, encoding="utf-8"))
                if not [p for p in data.get("players") or [] if p.get("name")]:
                    fails.append("small: the player search's data file holds no players, so it cannot show results")
            except (OSError, ValueError) as e:
                fails.append(f"small: the player search's data source {src.group(1)} is not served ({e})")
        if "data-pc-go" not in pc or 'id="pc-out"' not in pc:
            fails.append("small: the player search has no button or no results area")
    except Exception as e:
        import traceback
        fails.append(f"small: the fixture raised {type(e).__name__}: {e} ({traceback.format_exc().splitlines()[-3].strip()})")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
         sb.LIVE_POINTS, sb.IA_DESIG) = was
    return fails


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    fs = small_canary()
    for f in fs:
        print("::error::" + f)
    print("SMALL CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
