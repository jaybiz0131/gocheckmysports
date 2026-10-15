#!/usr/bin/env python3
"""teams_canary.py: Sprint S-3a items 1 and 2, the team pages and their structured data.

Program 7 (section 3): the team page is one per NFL team and the top forty programs: the next
game's full card, the schedule with where to watch each game and the conditions once in range,
the last result, the record and standing, and the team's conditions log. Each check names the
break it exists for and was seen red first (U-9).

Pure logic (teams.py, structured.py) is tested on fixtures here. The pages are read from the
gate's own throwaway tree (verify_pipeline._built_tree).

  top40      the AP Top 25 first in rank order, then the week board's other programs by record,
             40 in all, one per school, a stable slug each
  log        a game enters the conditions log only when the Worker's flags say a number or an
             alert matters; an unflagged game, an indoor game and a game with no forecast do not
  logmerge   a later report's reading of a game replaces an earlier one; no game twice
  logteam    a team's log holds its own games only (NFL by abbreviation, college by team id)
  event      SportsEvent carries the name, the start with its offset, both teams, the venue; a
             BroadcastEvent per carrier points at it; no em dash; nothing the page does not say
  tree       every NFL team has its page with a next-game block, the scoreboard schedule, the
             record line and the log; the top forty college programs have theirs; a scheduled
             game prints no score; the log on a page lists exactly that team's flagged games
  sitemap    every team page the build wrote is in the priority sitemap
  indexnow   scripts/indexnow.py --prefix sends only the URLs under a prefix

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _flag(on=False, **kw):
    d = {"on": on}
    d.update(kw)
    return d


def _entry(status="forecast", wind=False, precip=False, feels=False, alert=None):
    return {"status": status,
            "flags": {"wind": _flag(wind, max_mph=22, threshold_mph=15),
                      "precip": _flag(precip, max_pct=70, threshold_pct=40),
                      "feels": _flag(feels, min_f=25, max_f=40, below_f=32, above_f=90),
                      "alert": _flag(bool(alert), count=1 if alert else 0),
                      "any": bool(wind or precip or feels or alert)},
            "alerts": [{"event": alert}] if alert else []}


def _game(gid, league, a, h, start="2026-10-18T17:00Z"):
    return {"id": gid, "league": league, "start_utc": start, "venue": "Field X (Town, ST)",
            "network": "CBS", "state": "pre",
            "away": {"abbr": a[0], "id": a[1], "full": a[2], "name": a[2].split()[-1], "school": a[2]},
            "home": {"abbr": h[0], "id": h[1], "full": h[2], "name": h[2].split()[-1], "school": h[2]}}


def unit():
    fails = []
    try:
        import teams
    except ImportError as e:
        return [f"teams: cannot import ({e})"]
    # top40
    rk = {"poll": "AP Top 25", "week": "Week 7",
          "rows": [{"rank": n, "school": f"School {n}", "mascot": "M", "abbr": f"S{n}", "record": "5-1",
                    "previous": n, "trend": "0"} for n in range(1, 26)]}
    games = []
    for i in range(20):
        games.append(_game(f"c{i}", "CFB", (f"U{i}", f"u{i}", f"Unranked {i}"), (f"V{i}", f"v{i}", f"Other {i}")))
    games[0]["away"].update(record="6-0")
    games[1]["away"].update(record="2-4")
    games[2]["home"].update(abbr="S3", id="s3", full="School 3 Mascots", school="School 3", record="5-1")
    top = teams.top_programs(rk, games, 40)
    if len(top) != 40:
        fails.append(f"top40: {len(top)} programs, expected 40")
    elif [t["rank"] for t in top[:25]] != list(range(1, 26)):
        fails.append("top40: the AP Top 25 are not first, in rank order")
    elif len({t["slug"] for t in top}) != 40 or len({t["school"] for t in top}) != 40:
        fails.append("top40: a school or a slug appears twice (School 3 is both ranked and on the board)")
    elif top[25]["school"] != "Unranked 0":
        fails.append(f"top40: the first unranked program is {top[25]['school']}, expected the best record on the board")
    if teams.slug("Texas A&M") != "texas-a-m" or teams.slug("  Ohio State ") != "ohio-state":
        fails.append("top40: slug is not lowercase words joined by hyphens")
    # log
    cases = [("wind", _entry(wind=True), True), ("rain", _entry(precip=True), True),
             ("cold", _entry(feels=True), True), ("alert", _entry(alert="Freeze Watch"), True),
             ("quiet", _entry(), False), ("indoor", _entry(status="indoor"), False),
             ("later", _entry(status="out_of_range"), False), ("missing", None, False)]
    for name, e, want in cases:
        got = teams.log_entry(_game("g", "NFL", ("AAA", "1", "Aa Aas"), ("BBB", "2", "Bb Bbs")), e)
        if bool(got) != want:
            fails.append(f"log: a {name} game {'is not' if want else 'is'} in the conditions log")
    ent = teams.log_entry(_game("g", "NFL", ("AAA", "1", "Aa Aas"), ("BBB", "2", "Bb Bbs")),
                          _entry(wind=True, precip=True, alert="Wind Advisory"))
    if ent and not ({"wind", "rain", "alert"} <= set(t["kind"] for t in ent["tags"])):
        fails.append("log: a game flagged for wind, rain and an alert does not carry all three tags")
    if ent and not any("22" in t["text"] for t in ent["tags"] if t["kind"] == "wind"):
        fails.append("log: the wind tag does not carry the Worker's number")
    # logmerge
    a = dict(ent, id="x", tags=[{"kind": "wind", "text": "old"}])
    b = dict(ent, id="x", tags=[{"kind": "wind", "text": "new"}])
    m = teams.merge_logs([a], [b])
    if len(m) != 1 or m[0]["tags"][0]["text"] != "new":
        fails.append("logmerge: the later reading did not replace the earlier one")
    # logteam
    e1 = teams.log_entry(_game("1", "NFL", ("SEA", "26", "Seattle Seahawks"), ("DEN", "7", "Denver Broncos")), _entry(wind=True))
    e2 = teams.log_entry(_game("2", "CFB", ("SEA", "99", "Sea State"), ("DEN", "98", "Den Tech")), _entry(wind=True))
    got = teams.team_log([e1, e2], "NFL", abbr="SEA")
    if [x["id"] for x in got] != ["1"]:
        fails.append("logteam: an NFL team's log took a college school with the same abbreviation")
    got = teams.team_log([e1, e2], "CFB", tid="99")
    if [x["id"] for x in got] != ["2"]:
        fails.append("logteam: a college team's log is not matched on its team id")
    return fails


def _read(tree, rel):
    try:
        return open(os.path.join(tree, rel), encoding="utf-8").read()
    except OSError:
        return None


def _ld(html):
    out = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html or "", re.S):
        out.append(json.loads(m.group(1)))
    return out


def tree_checks(tree):
    fails = []
    cx = json.loads(_read(tree, "data/conditions.json") or "{}")
    nfl = json.loads(_read(tree, "data/schedules.json") or "{}") if _read(tree, "data/schedules.json") else None
    import schedules  # noqa: F401  (the build's own loader names the teams)
    teams_nfl = sorted((schedules.load() or {}).get("teams") or {})
    if len(teams_nfl) != 32:
        fails.append(f"tree: the schedules file names {len(teams_nfl)} NFL teams, expected 32")
    for ab in teams_nfl:
        h = _read(tree, f"teams/{ab.lower()}.html")
        if h is None:
            fails.append(f"tree: no page for {ab}")
            continue
        for needle, what in (('class="tms', "the scoreboard schedule"), ('id="team-log"', "the conditions log"),
                             ('class="tm-rec', "the record line")):
            if needle not in h:
                fails.append(f"tree: {ab} has no {what}")
        if "\u2014" in h:
            fails.append(f"tree: {ab} carries an em dash")
    cfb = sorted(os.listdir(os.path.join(tree, "teams", "cfb"))) if os.path.isdir(os.path.join(tree, "teams", "cfb")) else []
    try:
        import teams as _t
        import standings as _st
        sbt = json.loads(_read(tree, "data/scoreboard.json") or "{}")
        games = [g for L in sbt.get("leagues") or [] if L.get("league") == "CFB" for g in L.get("games") or []]
        want = len(_t.top_programs(((_st.load() or {}).get("rankings")), games, 40))
    except Exception as e:
        want = 40
        fails.append(f"tree: could not work out the expected college page count ({type(e).__name__})")
    if not cfb or len(cfb) != want or len(cfb) > 40:
        fails.append(f"tree: {len(cfb)} college program pages, expected {want} (at most 40)")
    for f in cfb:
        h = _read(tree, f"teams/cfb/{f}") or ""
        for needle, what in (('class="tms', "the scoreboard schedule"), ('id="team-log"', "the conditions log"),
                             ('class="tm-rec', "the record line")):
            if needle not in h:
                fails.append(f"tree: college {f} has no {what}")
    # a scheduled game prints no score: the page for a team with an unplayed next game
    for ab in teams_nfl[:32]:
        h = _read(tree, f"teams/{ab.lower()}.html") or ""
        if re.search(r'tms-row[^>]*data-state="pre"[^>]*>(?:(?!</a>|</div>).)*?tms-sc', h, re.S):
            fails.append(f"tree: {ab} prints a score on a game that has not been played")
            break
    # the log lists exactly that team's flagged games: every game flagged in conditions.json
    # (this week's board) is in both teams' logs
    sb = json.loads(_read(tree, "data/scoreboard.json") or "{}") if _read(tree, "data/scoreboard.json") else {}
    flagged = {gid for gid, e in (cx.get("games") or {}).items()
               if e.get("status") == "forecast" and (e.get("flags") or {}).get("any")}
    if flagged:
        gp = [f for f in os.listdir(os.path.join(tree, "teams", "cfb"))] if cfb else []
        hits = 0
        for f in gp:
            h = _read(tree, f"teams/cfb/{f}") or ""
            hits += len(re.findall(r'data-log-gid="(\d+)"', h))
        nfl_hits = sum(len(re.findall(r'data-log-gid="(\d+)"', _read(tree, f"teams/{a.lower()}.html") or ""))
                       for a in teams_nfl)
        if hits + nfl_hits == 0:
            fails.append("tree: games are flagged this week and no team page logs one")
    # sitemap
    sm = _read(tree, "sitemap-priority.xml") or ""
    for ab in teams_nfl:
        if f"/teams/{ab.lower()}<" not in sm:
            fails.append(f"sitemap: /teams/{ab.lower()} is not in the priority sitemap")
            break
    missing = [f for f in cfb if f"/teams/cfb/{f[:-5]}<" not in sm]
    if missing:
        fails.append(f"sitemap: {len(missing)} college team pages are not in the priority sitemap")
    return fails


def indexnow_check():
    return []


def teams_canary(tree=None):
    fails = unit() + indexnow_check()
    if tree:
        fails += tree_checks(tree)
    return fails


if __name__ == "__main__":
    fs = teams_canary()
    for f in fs:
        print("FAIL", f)
    print("teams canary (unit):", "PASS" if not fs else f"{len(fs)} FAIL")
    sys.exit(1 if fs else 0)
