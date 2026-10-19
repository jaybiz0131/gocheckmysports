#!/usr/bin/env python3
"""fbs_canary.py: Sprint S-3b.3, the college slate is every FBS game of the week.

Until 19 October 2026 the scoreboard read college football once, undated, and got ESPN's default
group: 16 games on a Saturday that holds 44 FBS games. The board, the game pages and the top-forty
college programs all take their list from that read, so the board was a third of the slate and
the programs stopped at 35 (S-3a report, section 6). The read now asks for the FBS group (groups=80)
for each day of the board's week, the same feed and the same parameters where_to_watch.py already
uses for college. Each check names the break it exists for and was seen red first (U-9).

  count      the college read holds every FBS game the feed gives for the board's week, once each
             (the fixture's own grouping: 56 distinct ids over seven days, 2 of them also in the
             default slate, 2 more in the default slate from last week)
  ask        each dated college read names groups=80 and limit=300; the NFL read names neither
  days       the days read are the board's week, Tuesday through Monday, by the manifest's rule
  failday    a day that fails is skipped and the rest stand; a failed default read does not lose
             the days; every read failing raises, so the league is skipped as before
  board      the board holds the FBS games of the week once each, in kickoff order, each with a
             game page (BOARD_IDS, _has_game_page), and the manifest's count agrees
  final      a scheduled game never prints Final
  weight     the home stays under 150 KB with the whole FBS week and a full NFL Sunday; under a
             small budget the NFL stays, the best FBS games stay, each day counts what it left
             out from the manifest's totals and links Scores
  top40      the top forty college programs fill to forty from the wider read and do not from the
             old default slate
  inert      the weather helpers that were never fed (WX_DATA is always None) are gone, and the
             Ticket's venue line carries no weather half
  tree       in the built tree no game card id repeats, no scheduled card says Final, and every
             game page a card links is in the tree

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime as _d
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PATH = "football/college-football"
# the board's week for the fixture clock below: Tuesday 20 October to Monday 26 October 2026
DAYS = ["20261020", "20261021", "20261022", "20261023", "20261024", "20261025", "20261026"]
PER_DAY = {"20261020": 3, "20261021": 1, "20261022": 3, "20261023": 5, "20261024": 44,
           "20261025": 0, "20261026": 0}
FBS_WEEK = sum(PER_DAY.values())          # 56, the grouping the fixture states
OVERLAP = 2                               # default-slate games that are also dated Saturday games
STALE = 2                                 # default-slate games from last week, off the board


def _ev(i, day, hhmm, state="pre", away=None, home=None):
    """One feed event on ET day `day` (YYYYMMDD) at `hhmm`, with two distinct schools."""
    from zoneinfo import ZoneInfo
    et = _d.datetime.strptime(day + hhmm, "%Y%m%d%H%M").replace(tzinfo=ZoneInfo("America/New_York"))
    iso = et.astimezone(_d.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    away = away or (f"A{i}", f"a{i}", f"Away School {i}")
    home = home or (f"H{i}", f"h{i}", f"Home School {i}")

    def side(ha, t):
        return {"homeAway": ha, "score": "0", "team": {
            "id": t[1], "abbreviation": t[0], "location": t[2], "name": "Mascots",
            "displayName": t[2] + " Mascots", "shortDisplayName": t[2]}}
    return {"id": str(i), "date": iso,
            "status": {"type": {"state": state, "completed": state == "post",
                                "shortDetail": "Final" if state == "post" else "10/24 - 12:00 PM EDT"}},
            "competitions": [{"competitors": [side("away", away), side("home", home)]}]}


def _fixture():
    """The feed as a function of the url: the FBS group by day, and a default slate."""
    by_day, n = {}, 1000
    for day in DAYS:
        evs = []
        for k in range(PER_DAY[day]):
            n += 1
            evs.append(_ev(n, day, "%02d00" % (12 + (k % 8))))
        by_day[day] = evs
    sat = by_day["20261024"]
    default = [sat[0], sat[1],
               _ev(9001, "20261017", "1200", "post"), _ev(9002, "20261017", "1500", "post")]
    return by_day, default


def _feed(by_day, default, fail_days=(), fail_default=False, asked=None):
    def get(url):
        if asked is not None:
            asked.append(url)
        m = re.search(r"dates=(\d{8})", url)
        if m:
            if m.group(1) in fail_days:
                raise OSError("down")
            if "groups=80" not in url:
                # an undated-group dated read is the default group, which is the thing under test
                return {"events": list(default)}
            return {"events": list(by_day.get(m.group(1), []))}
        if fail_default:
            raise OSError("down")
        return {"events": list(default)}
    return get


def _clock():
    from zoneinfo import ZoneInfo
    return _d.datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("America/New_York"))


def feed_unit():
    import scoreboard as scb
    fails = []
    by_day, default = _fixture()
    was = (scb._get, getattr(scb, "_board_days", None))
    scb._board_days = lambda now=None: list(DAYS)
    try:
        # count
        asked = []
        scb._get = _feed(by_day, default, asked=asked)
        got = scb._league("CFB", PATH, "college-football", {})
        ids = [g["id"] for g in got]
        want = FBS_WEEK + STALE
        if len(ids) != want:
            fails.append(f"count: the college read holds {len(ids)} games, the FBS grouping gives "
                         f"{FBS_WEEK} for the week plus {STALE} left in the default slate = {want}")
        if len(ids) != len(set(ids)):
            fails.append("count: a college game id is read twice")
        # ask
        dated = [u for u in asked if "dates=" in u]
        if len(dated) != len(DAYS) or not all("groups=80" in u and "limit=300" in u for u in dated):
            fails.append(f"ask: the dated college reads are {len(dated)}, each must name groups=80 and "
                         f"limit=300 (got {[u.split('?')[-1] for u in dated][:2]})")
        asked.clear()
        scb._get = _feed(by_day, default, asked=asked)
        scb._week_days = lambda: ["20261022"]
        try:
            scb._league("NFL", "football/nfl", "nfl", {})
        finally:
            del scb._week_days
        if any("groups=" in u or "limit=" in u for u in asked):
            fails.append("ask: the NFL read names a college group or limit")
        # failday
        scb._get = _feed(by_day, default, fail_days=("20261024",))
        left = FBS_WEEK - PER_DAY["20261024"] + STALE + OVERLAP     # Saturday's two stay via the default slate
        try:
            n = len(scb._league("CFB", PATH, "college-football", {}))
        except OSError:
            n = "none (the league raised)"
        if n != left:
            fails.append(f"failday: with Saturday failing the read holds {n} games, expected {left}")
        scb._get = _feed(by_day, default, fail_default=True)
        try:
            n = len(scb._league("CFB", PATH, "college-football", {}))
        except OSError:
            n = "none (the league raised)"
        if n != FBS_WEEK:
            fails.append(f"failday: with the default read failing the days hold {n} games, "
                         f"expected {FBS_WEEK}")
        scb._get = _feed(by_day, default, fail_default=True, fail_days=DAYS)
        try:
            scb._league("CFB", PATH, "college-football", {})
            fails.append("failday: every college read failed and the league did not raise, so a "
                         "total failure would be written as an empty slate")
        except OSError:
            pass
    finally:
        scb._get = was[0]
        if was[1] is None:
            if hasattr(scb, "_board_days"):
                del scb._board_days
        else:
            scb._board_days = was[1]
    # days: the board's week by the manifest's rule, from a clock
    try:
        got = scb._board_days(_clock())
    except Exception as e:
        got = f"{type(e).__name__}: {e}"
    if got != DAYS:
        fails.append(f"days: the board's week for Thursday 22 October is {got}, expected {DAYS}")
    try:
        mon = scb._board_days(_d.datetime(2026, 10, 19, 11, 8, tzinfo=_clock().tzinfo))
        tue = scb._board_days(_d.datetime(2026, 10, 20, 7, 0, tzinfo=_clock().tzinfo))
    except Exception as e:
        mon = tue = f"{type(e).__name__}: {e}"
    if mon != ["20261013", "20261014", "20261015", "20261016", "20261017", "20261018", "20261019"] \
            or tue != DAYS:
        fails.append(f"days: the week rolls Tuesday 6:00 AM ET; Monday 19 October reads {mon}, "
                     f"Tuesday 20 October 7 AM reads {tue}")
    return fails


def _college_games():
    """The scoreboard's CFB games as the fixture feed gives them, through the real reader."""
    import scoreboard as scb
    by_day, default = _fixture()
    was = (scb._get, getattr(scb, "_board_days", None))
    scb._get = _feed(by_day, default)
    scb._board_days = lambda now=None: list(DAYS)
    try:
        return scb._league("CFB", PATH, "college-football", {})
    finally:
        scb._get = was[0]
        if was[1] is None:
            del scb._board_days
        else:
            scb._board_days = was[1]


def board_unit():
    import build_manifest as bm
    import site_build as sb
    import teams
    from truth_canary import read
    fails = []
    games = _college_games()
    # one scheduled game is marked as already final in the feed's own fields, one is not: the first
    # prints Final, no other does
    sbd = {"fetched_at": "2026-10-22T12:00:00Z", "leagues": [{"league": "CFB", "games": games}]}
    w2w = {"fetched_at": "2026-10-22T12:00:00Z",
           "weeks": [{"season": 2026, "week": 7, "games": [], "cfb_games": []}]}
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
           sb.WX_DATA, sb._carriage.load, sb.BOARD_IDS, sb.GAME_PAGE_IDS)
    try:
        sb._NOW_CACHE = _clock().astimezone(_d.timezone.utc)
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb._carriage.load = lambda: {"schema": 1, "stale_days": 30, "rows": []}
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        bg = sb.board_games(sbd)
        sb.BOARD_IDS = {str(g.get("id")) for _k, g in bg if g.get("id")}
        if len(bg) != FBS_WEEK:
            fails.append(f"board: the board holds {len(bg)} college games, the FBS grouping gives {FBS_WEEK}")
        ks = [k for k, _g in bg]
        if ks != sorted(ks):
            fails.append("board: the board's games are not in kickoff order")
        nopage = [g["id"] for _k, g in bg if not sb._has_game_page(g)]
        if nopage:
            fails.append(f"board: {len(nopage)} board games have no game page ({nopage[:3]})")
        if "9001" in sb.BOARD_IDS or "9002" in sb.BOARD_IDS:
            fails.append("board: last week's game is on this week's board")
        band, board = sb.week_board(sbd)
        d = read(band + board)
        if len(d.units) != FBS_WEEK or len(set(d.units)) != len(d.units):
            fails.append(f"board: the page prints {len(d.units)} cards ({len(set(d.units))} distinct), "
                         f"expected {FBS_WEEK} once each")
        n_tab = sum(int(n or 0) for _l, n in re.findall(
            r'class="tk-tab wb-t[^"]*" data-day="([^"]*)"[^>]*>[^<]*(?:<small>(\d+)</small>)?', band + board))
        if n_tab != FBS_WEEK:
            fails.append(f"board: the day tabs count {n_tab} games, the manifest says {FBS_WEEK}")
        # final: every card here is scheduled, so none may say Final
        for m in re.finditer(r'<article[^>]*data-gid="([^"]*)"[^>]*data-state="pre".*?</article>',
                             board, re.S):
            if "Final" in re.sub(r"<[^>]+>", " ", m.group(0)):
                fails.append(f"final: the scheduled game {m.group(1)} prints Final")
                break
        # top40
        top = teams.top_programs(None, games, 40)
        if len(top) != 40:
            fails.append(f"top40: the wider read gives {len(top)} programs, expected 40")
        dflt = {e["id"] for e in _fixture()[1]}
        old = teams.top_programs(None, [g for g in games if g["id"] in dflt], 40)
        if len(old) >= 40:
            fails.append("top40: the old default slate filled forty programs, so this fixture cannot show the fix")
    except Exception as e:
        fails.append(f"board: the board fixture raised {type(e).__name__}: {e}")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
         sb.WX_DATA, sb._carriage.load, sb.BOARD_IDS, sb.GAME_PAGE_IDS) = was
    return fails


def _nfl_games(n=16):
    out = []
    for i in range(n):
        e = _ev(f"n{i}", "20261025", "%02d00" % (13 + i % 7))
        out.append(e)
    return out


def weight_unit():
    """The home stays under 150 KB with the whole FBS week and a full NFL Sunday on the board
    (scorecard line 4). The cut is exercised with a small budget, since the fixture's cards carry
    no conditions plates and run lighter than the real ones: the NFL stays, the best FBS games stay
    (a ranked one with the last kickoff of the week), the rest are counted under their day from the
    manifest's own totals, and Scores is linked."""
    import build_manifest as bm
    import scoreboard as scb
    import site_build as sb
    fails = []
    was_get = (scb._get, getattr(scb, "_board_days", None))
    by_day, default = _fixture()
    # the last kickoff of the week is a ranked game
    last = by_day["20261024"][-1]
    last["competitions"][0]["competitors"][0]["curatedRank"] = {"current": 3}
    scb._get = _feed(by_day, default)
    scb._board_days = lambda now=None: list(DAYS)
    try:
        cfb = scb._league("CFB", PATH, "college-football", {})
    finally:
        scb._get = was_get[0]
        if was_get[1] is None:
            del scb._board_days
        else:
            scb._board_days = was_get[1]
    # NFL games built with the same reader, from the NFL fixture
    scb._get = lambda url: {"events": _nfl_games()}
    scb._week_days = lambda: []
    try:
        nfl = scb._league("NFL", "football/nfl", "nfl", {})
    finally:
        scb._get = was_get[0]
        del scb._week_days
    sbd = {"fetched_at": "2026-10-22T12:00:00Z",
           "leagues": [{"league": "NFL", "games": nfl}, {"league": "CFB", "games": cfb}]}
    w2w = {"fetched_at": "2026-10-22T12:00:00Z",
           "weeks": [{"season": 2026, "week": 7, "cfb_games": [],
                      "games": [{"id": g["id"], "carriers": [], "kickoff_utc": g["start_utc"]} for g in nfl]}]}
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
           sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF, sb.HOME_BUDGET)
    try:
        sb._NOW_CACHE = _clock().astimezone(_d.timezone.utc)
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb._carriage.load = lambda: {"schema": 1, "stale_days": 30, "rows": []}
        sb.CR_REPORTS, sb.EDITION_HREF = [], "/edition/2026-10-21.html"
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        sb.BOARD_IDS = {str(g.get("id")) for _k, g in sb.board_games(sbd) if g.get("id")}
        if not 0 < sb.HOME_BUDGET <= 145000:
            fails.append(f"weight: HOME_BUDGET is {sb.HOME_BUDGET}; the scorecard's 150000 needs a margin under it")
        full = sb.render_home([], "")
        if len(full.encode("utf-8")) > 150000:
            fails.append(f"weight: the home is {len(full.encode('utf-8'))} bytes with the whole FBS week, "
                         f"over the scorecard's 150000")
        # the cut budget sits between the page with no college card and the page with all of them,
        # measured here, because the shipped page carries more than this fixture (pins, team index)
        sb.HOME_BUDGET = 1
        base = len(sb.render_home([], "").encode("utf-8"))
        sb.HOME_BUDGET = 10 ** 7
        whole = len(sb.render_home([], "").encode("utf-8"))
        sb.HOME_BUDGET = (base + whole) // 2
        small = sb.render_home([], "")
        n = len(small.encode("utf-8"))
        if n > sb.HOME_BUDGET:
            fails.append(f"weight: the home is {n} bytes under a {sb.HOME_BUDGET}-byte budget")
        shown_cfb = set(re.findall(r'<article[^>]*data-gid="([^"]*)"[^>]*data-league="CFB"', small))
        shown_nfl = set(re.findall(r'<article[^>]*data-gid="([^"]*)"[^>]*data-league="NFL"', small))
        if len(shown_nfl) != len(nfl):
            fails.append(f"weight: the cut drew {len(shown_nfl)} of {len(nfl)} NFL games; the NFL is never cut")
        if not shown_cfb or len(shown_cfb) >= FBS_WEEK:
            fails.append(f"weight: the cut drew {len(shown_cfb)} of {FBS_WEEK} college games; it must draw "
                         f"some and not all")
        if str(last["id"]) not in shown_cfb:
            fails.append("weight: a ranked game is cut while unranked games stay")
        more = [int(x) for x in re.findall(r'<p class="bd-src wb-more">(\d+) more college game', small)]
        if sum(more) != FBS_WEEK - len(shown_cfb):
            fails.append(f"weight: the days say {sum(more)} more college games, the board holds "
                         f"{FBS_WEEK - len(shown_cfb)} it did not draw")
        wall_more = [int(x) for x in re.findall(r'<p class="wl-src">(\d+) more college game', small)]
        if sum(wall_more) != sum(more):
            fails.append(f"weight: the wall says {sum(wall_more)} more, the cards say {sum(more)}")
        if more and 'href="/scores.html#cfb">All scores</a>' not in small:
            fails.append("weight: the cut line does not link Scores")
        tabs = sum(int(x) for x in re.findall(r'class="tk-tab wb-t" data-day="[^"]*"[^>]*>[^<]*<small>(\d+)</small>', small))
        if tabs != FBS_WEEK + len(nfl):
            fails.append(f"weight: the day tabs count {tabs}, the manifest says {FBS_WEEK + len(nfl)}")
        if sb.HOME_HIDE:
            fails.append("weight: the home's hide list leaked past the render")
    except Exception as e:
        fails.append(f"weight: the fixture raised {type(e).__name__}: {e}")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
         sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF, sb.HOME_BUDGET) = was
    return fails


def inert_unit():
    import site_build as sb
    fails = []
    for name in ("_wx_chip", "_w2w_wx", "_wx_for"):
        if hasattr(sb, name):
            fails.append(f"inert: {name} is still defined; WX_DATA is always None, so it prints nothing")
    g = {"id": "1", "venue": "Field X", "league": "CFB"}
    wx = {"games": {"1": {"temp_f": 61, "wind_mph": 14, "precip_pct": 55}}}
    try:
        got = sb._tk_venue(g, wx) if sb._tk_venue.__code__.co_argcount == 2 else sb._tk_venue(g)
    except Exception as e:
        got = f"{type(e).__name__}: {e}"
    if got != "Field X":
        fails.append(f"inert: the Ticket's venue line is {got!r}; it carries a weather half the "
                     f"Worker's strip already owns")
    return fails


def tree_checks(tree):
    fails = []
    try:
        home = open(os.path.join(tree, "index.html"), encoding="utf-8").read()
    except OSError:
        return ["tree: no home page in the built tree"]
    gids = re.findall(r'<article[^>]*class="tk-c sbc[^"]*"[^>]*data-gid="([^"]*)"', home)
    dup = sorted({x for x in gids if gids.count(x) > 1})
    if dup:
        fails.append(f"tree: game ids printed twice on the home: {dup[:3]}")
    for m in re.finditer(r'<article[^>]*class="tk-c sbc[^"]*"[^>]*data-gid="([^"]*)"[^>]*data-state="pre".*?</article>',
                         home, re.S):
        if "Final" in re.sub(r"<[^>]+>", " ", m.group(0)):
            fails.append(f"tree: the scheduled game {m.group(1)} prints Final on the home")
            break
    for gid in re.findall(r'class="tk-card-a" href="/games/([^"]+)\.html"', home):
        if not os.path.exists(os.path.join(tree, "games", gid + ".html")):
            fails.append(f"tree: the home links /games/{gid}.html and the build wrote no such page")
            break
    return fails


def tree_unit():
    """The tree checks are run on three small trees first: a clean one must pass, and each defect
    they exist for must be named, so a check that reads nothing cannot pass in silence (U-9)."""
    import shutil
    import tempfile
    card = ('<article class="tk-c sbc" data-gid="%s" data-league="CFB" data-state="%s">%s'
            '<a class="tk-card-a" href="/games/%s.html"></a></article>')
    fails = []
    cases = [("clean", [card % ("1", "pre", "12:00 PM", "1"), card % ("2", "post", "Final", "2")], ["1", "2"], 0),
             ("a game id twice", [card % ("1", "pre", "x", "1")] * 2, ["1"], 1),
             ("a scheduled game that says Final", [card % ("1", "pre", "Final", "1")], ["1"], 1),
             ("a link to a page not written", [card % ("1", "pre", "x", "1")], [], 1)]
    for name, cards, pages, want in cases:
        tmp = tempfile.mkdtemp(prefix="fbs-tree-")
        try:
            os.makedirs(os.path.join(tmp, "games"))
            open(os.path.join(tmp, "index.html"), "w", encoding="utf-8").write("<html>" + "".join(cards) + "</html>")
            for p in pages:
                open(os.path.join(tmp, "games", p + ".html"), "w").write("x")
            got = tree_checks(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if len(got) != want:
            fails.append(f"tree: on a tree with {name} the checks returned {len(got)} failure(s), expected {want}")
    return fails


def fbs_canary(tree=None):
    fails = feed_unit() + board_unit() + weight_unit() + inert_unit() + tree_unit()
    if tree:
        fails += tree_checks(tree)
    return fails


if __name__ == "__main__":
    fs = fbs_canary()
    for f in fs:
        print("FAIL", f)
    print("fbs canary (unit):", "PASS" if not fs else f"{len(fs)} FAIL")
    sys.exit(1 if fs else 0)
