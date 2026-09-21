#!/usr/bin/env python3
"""fantasy_points.py: live fantasy points from the official box score (S-B3).

COMPUTED, NEVER PROJECTED. Every number here is arithmetic on a stat line the league
has already published. There is no model, no estimate and no ranking, and there never
will be on this desk.

THE FORMULAS, as the directive states them:
  passing    1 point per 25 yards, 4 per TD, minus 2 per interception
  rushing    1 per 10 yards, 6 per TD
  receiving  1 per 10 yards, 6 per TD, plus 1 / 0.5 / 0 per reception by format
  fumbles    minus 2 per fumble LOST
  kicking    3 per field goal, 1 per extra point

TWO-POINT CONVERSIONS ARE NOT INCLUDED, and the page says so rather than quietly
being wrong. The box score carries no two-point field: zero matches for twoPoint,
2PT or conversion anywhere in the payload. Scoring plays name the conversion in their
text, but they are final-only, so they cannot feed a live number even if parsed.
Ruled 2026-09-14: compute without, footnote it, and reconcile at final if the scoring
plays carry the attempt.

STATS ARE READ BY LABEL, NEVER BY INDEX. The passing array is seven wide during a game
and eight at final, because QBR appears only once the game ends. Positional reads
would silently shift every number after it.
"""

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={id}"
TIMEOUT = 20
FORMATS = ("ppr", "half", "standard")
PER_REC = {"ppr": 1.0, "half": 0.5, "standard": 0.0}


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _num(s):
    """A stat cell to a number. Cells come as "23/33", "5", "1-1" or "-"."""
    t = str(s or "").strip()
    if not t or t == "-":
        return 0.0
    if "/" in t:
        t = t.split("/")[0]
    if "-" in t and not t.startswith("-"):
        t = t.split("-")[0]
    try:
        return float(t)
    except ValueError:
        return 0.0


def _by_label(cat):
    """label -> index, so a shifting array cannot shift the numbers."""
    return {str(l).strip().upper(): i for i, l in enumerate(cat.get("labels") or [])}


def _cell(row, idx, label):
    i = idx.get(label.upper())
    if i is None or i >= len(row.get("stats") or []):
        return 0.0
    return _num(row["stats"][i])


def player_points(summary):
    """Every player in this game with a line, and their points in all three formats."""
    out = {}
    for team in ((summary.get("boxscore") or {}).get("players") or []):
        tm = ((team.get("team") or {}).get("abbreviation") or "")
        for cat in team.get("statistics") or []:
            name = (cat.get("name") or "").lower()
            idx = _by_label(cat)
            for row in cat.get("athletes") or []:
                a = row.get("athlete") or {}
                pid = str(a.get("id") or "")
                if not pid:
                    continue
                p = out.setdefault(pid, {
                    "name": a.get("displayName") or "", "team": tm,
                    "pos": ((a.get("position") or {}).get("abbreviation") or ""),
                    "line": [], "base": 0.0, "rec": 0.0})
                if name == "passing":
                    y, td, i_ = (_cell(row, idx, "YDS"), _cell(row, idx, "TD"),
                                 _cell(row, idx, "INT"))
                    p["base"] += y / 25.0 + td * 4 - i_ * 2
                    if y or td:
                        p["line"].append(f"{y:.0f} pass yds, {td:.0f} TD")
                elif name == "rushing":
                    y, td = _cell(row, idx, "YDS"), _cell(row, idx, "TD")
                    p["base"] += y / 10.0 + td * 6
                    if y or td:
                        p["line"].append(f"{y:.0f} rush yds, {td:.0f} TD")
                elif name == "receiving":
                    y, td = _cell(row, idx, "YDS"), _cell(row, idx, "TD")
                    rec = _cell(row, idx, "REC")
                    p["base"] += y / 10.0 + td * 6
                    p["rec"] += rec
                    if y or rec:
                        p["line"].append(f"{rec:.0f} rec, {y:.0f} yds, {td:.0f} TD")
                elif name == "fumbles":
                    p["base"] -= _cell(row, idx, "LOST") * 2
                elif name == "kicking":
                    fg, xp = _cell(row, idx, "FG"), _cell(row, idx, "XP")
                    p["base"] += fg * 3 + xp
                    if fg or xp:
                        p["line"].append(f"{fg:.0f} FG, {xp:.0f} XP")
    for p in out.values():
        for f in FORMATS:
            p[f] = round(p["base"] + p["rec"] * PER_REC[f], 1)
        p.pop("base", None)
        p.pop("rec", None)
    return out


def for_game(event_id):
    """Points for one game, or None when the box score has no players yet (a game that
    has not kicked off has no `players` block at all)."""
    try:
        s = _get(SUMMARY.format(id=event_id))
    except Exception:
        return None
    pts = player_points(s)
    if not pts:
        return None
    return pts


def win_probability(summary):
    """C-3: the home side's win probability, as ESPN's model last stated it.

    THE DESK PUBLISHES NO FORECAST OF ITS OWN. This is the same rule the 20 September
    law applied to the line: a number one company produced, carried as a fact about what
    that company said, with the company named beside it. Nothing here is modelled,
    smoothed, averaged or extrapolated, and a game with no track gets no number.

    THE TRACK IS ALREADY ON DISK. This endpoint is fetched for every started NFL game to
    compute fantasy points, so the 190-point win-probability track has been downloaded
    and discarded on every build since that feature shipped. C-3 costs no new request.

    Returns a float 0..1 or None. The LAST point is taken, because the track runs
    play by play and the only honest reading of "the win probability" on a card is the
    most recent one the model produced.
    """
    wp = (summary or {}).get("winprobability")
    if not isinstance(wp, list) or not wp:
        return None
    last = wp[-1]
    v = last.get("homeWinPercentage") if isinstance(last, dict) else None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def for_game_full(event_id):
    """Points and the win-probability reading from ONE fetch.

    Kept separate from for_game so the existing caller is untouched. The summary carries
    pickcenter, againstTheSpread and odds, which odds_gate forbids from reaching any
    written file, so nothing but the two extracted values leaves this function.
    """
    try:
        s = _get(SUMMARY.format(id=event_id))
    except Exception:
        return (None, None)
    return (player_points(s) or None, win_probability(s))


def leaders(points, n=8, fmt="ppr"):
    rows = [p for p in (points or {}).values() if p.get(fmt)]
    rows.sort(key=lambda p: -p.get(fmt, 0))
    return rows[:n]


def main():
    if len(sys.argv) < 2:
        print("usage: fantasy_points.py <event-id>")
        return 2
    pts = for_game(sys.argv[1])
    if not pts:
        print("no box score yet for that game")
        return 0
    print(f"{len(pts)} players with a line")
    for p in leaders(pts, 10):
        print(f"  {p['name']:24} {p['team']:4} {p['pos']:3} "
              f"PPR {p['ppr']:5.1f}  half {p['half']:5.1f}  std {p['standard']:5.1f}"
              f"   {'; '.join(p['line'])[:52]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
