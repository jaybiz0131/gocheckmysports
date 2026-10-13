#!/usr/bin/env python3
"""build_manifest.py: one truth for the counts and stamps a build prints (Sprint S-1, item 0).

Until 12 October 2026 every page that printed "N games today" or "Updated 8:15 PM ET"
computed it for itself: the band, the Scores page, the tab strip, the fantasy hub and the
browser script each held their own rule for "today", and on the morning of 12 October the
home said "12 games today" while Where to Watch marked Monday night's scheduled game Final.

The manifest is written ONCE per build, from the build clock, the scoreboard feed and the
schedule file. Every page that prints a count or a stamp reads it. No page counts a card.

  built_utc / built_et    the build clock, with its zone ("Oct 12, 8:15 PM EDT")
  stamp                   the label pages print, "Oct 12, 8:15 PM ET"
  date                    the ET date the page is for. "Today" and "tonight" mean this.
  week                    the NFL week number, by the rule that the week rolls at
                          6:00 AM ET on Tuesday (week_start / week_for below)
  slate.date              counts for that date: total, final, scheduled, in_progress, by league,
                          and the next day's label and total when the date is empty
  slate.week              counts for the week

Pure functions, standard library only, so a test can feed a fixture clock.
"""

import datetime
import json
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

ROLL_WEEKDAY = 1      # Tuesday; Monday is 0
ROLL_HOUR = 6         # 6:00 AM ET


def _utc(iso):
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def week_start(now):
    """The most recent Tuesday 6:00 AM ET at or before `now`, as an ET datetime."""
    et = now.astimezone(ET)
    start = et.replace(hour=ROLL_HOUR, minute=0, second=0, microsecond=0)
    start -= datetime.timedelta(days=(et.weekday() - ROLL_WEEKDAY) % 7)
    if start > et:
        start -= datetime.timedelta(days=7)
    return start


def week_for(now, weeks):
    """The NFL week number for `now`, from the schedule file's weeks, or None.

    A week is the seven days from the Tuesday 6:00 AM ET that precedes its first kickoff.
    The week whose span holds `now` wins. When no span holds it (the file is a week
    behind), the first week that starts after `now` is the next one, and the last week
    stands after the final game."""
    spans = []
    for w in weeks or []:
        ks = [_utc(g.get("kickoff_utc") or g.get("start_utc")) for g in (w.get("games") or [])]
        ks = [k for k in ks if k]
        if not ks or w.get("week") in (None, ""):
            continue
        s = week_start(min(ks))
        spans.append((s, s + datetime.timedelta(days=7), w.get("week")))
    spans.sort(key=lambda t: t[0])
    for s, e, wk in spans:
        if s <= now < e:
            return wk
    for s, e, wk in spans:
        if s > now:
            return wk
    return spans[-1][2] if spans else None


def _label(dt):
    return dt.astimezone(ET).strftime("%b %-d, %-I:%M %p")


def _count(games, today):
    c = {"total": 0, "final": 0, "scheduled": 0, "in_progress": 0}
    for g in games:
        c["total"] += 1
        st = g.get("state")
        if st == "post":
            c["final"] += 1
        elif st == "in":
            c["in_progress"] += 1
        else:
            c["scheduled"] += 1
    return c


def build(now, sb_data=None, w2w=None):
    """The manifest for a build at `now` (an aware datetime)."""
    now = now.astimezone(UTC)
    today = now.astimezone(ET).date()
    games = []
    for L in (sb_data or {}).get("leagues") or []:
        for g in L.get("games") or []:
            k = _utc(g.get("start_utc"))
            if k:
                games.append((L.get("league") or g.get("league") or "", g, k.astimezone(ET).date(), k))
    wk = week_for(now, (w2w or {}).get("weeks"))
    ws = week_start(now)
    we = ws + datetime.timedelta(days=7)

    def pack(rows):
        gs = [g for _lg, g, _d, _k in rows]
        out = _count(gs, today)
        by = {}
        for lg, g, _d, _k in rows:
            by.setdefault(lg, []).append(g)
        out["by_league"] = {lg: _count(v, today) for lg, v in by.items()}
        return out

    dated = [r for r in games if r[2] == today]
    slate_date = pack(dated)
    later = sorted({d for _lg, _g, d, _k in games if d > today})
    if later:
        d0 = later[0]
        slate_date["next_label"] = ("tomorrow" if (d0 - today).days == 1 else d0.strftime("%A"))
        nxt = [r for r in games if r[2] == d0]
        slate_date["next_total"] = len(nxt)
        slate_date["next_by_league"] = {lg: len([1 for r in nxt if r[0] == lg])
                                        for lg in {r[0] for r in nxt}}
    else:
        slate_date["next_label"], slate_date["next_total"], slate_date["next_by_league"] = "", 0, {}
    in_week = [r for r in games if ws <= r[3] < we]
    week_slate = pack(in_week)
    # the day tabs and the Sunday windows of the week board read these
    import carriage
    days = {}
    for lg, g, d, k in sorted(in_week, key=lambda r: r[3]):
        days.setdefault(d, []).append((lg, g, k))
    week_slate["days"] = [
        {"date": d.isoformat(), "label": d.strftime("%a"),
         "by_league": {lg: len([1 for x in rows if x[0] == lg]) for lg in {x[0] for x in rows}}}
        for d, rows in sorted(days.items())]
    wins = {}
    for lg, g, d, k in in_week:
        if lg == "NFL" and d.weekday() == 6:
            key = carriage.window_key(k, "NFL")
            wins[key] = wins.get(key, 0) + 1
    week_slate["sunday_windows"] = wins
    return {
        "built_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "built_et": now.astimezone(ET).strftime("%Y-%m-%d %-I:%M %p %Z"),
        "stamp": _label(now) + " ET",
        "clock": now.astimezone(ET).strftime("%-I:%M %p") + " ET",
        "date": today.isoformat(),
        "week": wk,
        "week_start_et": ws.strftime("%Y-%m-%d %H:%M %Z"),
        "data_utc": (sb_data or {}).get("fetched_at") or "",
        "data_stamp": (_label(_utc((sb_data or {}).get("fetched_at"))) + " ET")
                      if _utc((sb_data or {}).get("fetched_at")) else "",
        "slate": {"date": slate_date, "week": week_slate},
    }


def _leagues(league):
    if league is None:
        return None
    return [league] if isinstance(league, str) else list(league)


def count_line(m, league=None):
    """The one sentence every page prints for the day's count. `league` is None for all
    leagues, one league's name, or a list of names (the board counts NFL and CFB)."""
    d = m["slate"]["date"]
    lgs = _leagues(league)
    if lgs is None:
        n, nxt_n, lab = d["total"], d["next_total"], d["next_label"]
    else:
        n = sum((d["by_league"].get(l) or {}).get("total", 0) for l in lgs)
        nxt_n = sum((d.get("next_by_league") or {}).get(l, 0) for l in lgs)
        lab = d["next_label"]
    if n:
        return f"{n} game{'' if n == 1 else 's'} today"
    if nxt_n:
        return f"No games today \u00b7 {nxt_n} {'game' if nxt_n == 1 else 'games'} {lab}"
    return "No games scheduled"


def dump(m, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, sort_keys=True)
