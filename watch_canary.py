#!/usr/bin/env python3
"""watch_canary.py: Sprint S-1 item 1, Where to Watch rebuilt (12 October 2026).

Each check names the break it exists for and was seen red first (U-9).

  kickoff-network   every game of the week prints a kickoff and a network from the feed
  streams           the streams printed are the carriage rows' and nothing else
  thirty-days       a row past thirty days prints verify, on the thirtieth day it does not
  grouping          by day, then by window: early, 1:00, 4:05 and 4:25, night
  score             no score before the game, the final after
  fbs               the college feed is read a day at a time and a refused day is skipped
  file              data/carriage.json: every row has a source, a date and a status

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime as _d
import json
import os
import re

from truth_canary import read, visible


def _fixture(sb):
    ET = sb._ET

    def u(et):
        return _d.datetime.fromisoformat(et).replace(tzinfo=ET).astimezone(_d.timezone.utc)

    def g(lg, a, h, kick, st, nets, sa=None, sh=None, i=None):
        k = u(kick)
        return {"league": lg, "away": a, "home": h, "id": i or a + h,
                "kickoff_utc": k.strftime("%Y-%m-%dT%H:%MZ"),
                "carriers": [{"name": n, "market": "National", "type": "TV"} for n in nets],
                "state": st, "completed": st == "post",
                "status": "Final" if st == "post" else "",
                "away_score": sa, "home_score": sh}
    nfl = [g("NFL", "DEN", "SEA", "2026-10-15T20:15", "pre", ["Prime Video"]),
           g("NFL", "LON", "PAR", "2026-10-18T09:30", "pre", ["NFL Net"]),
           g("NFL", "CHI", "GB", "2026-10-18T13:00", "pre", ["FOX"]),
           g("NFL", "LV", "NE", "2026-10-18T13:00", "pre", ["CBS"]),
           g("NFL", "ARI", "LAR", "2026-10-18T16:05", "pre", ["FOX"]),
           g("NFL", "LAC", "KC", "2026-10-18T16:25", "pre", ["CBS"]),
           g("NFL", "DAL", "PHI", "2026-10-18T20:20", "pre", ["NBC", "Peacock"]),
           g("NFL", "BUF", "MIA", "2026-10-19T20:15", "pre", ["ESPN", "ABC"]),
           g("NFL", "MIN", "DET", "2026-10-11T13:00", "post", ["FOX"], "24", "16")]
    cfb = [g("CFB", "ALA", "TEN", "2026-10-17T12:00", "pre", ["ESPN"]),
           g("CFB", "OSU", "IU", "2026-10-17T15:30", "pre", ["ABC"]),
           g("CFB", "LSU", "UGA", "2026-10-17T19:30", "pre", ["CBS"])]
    week = {"season": 2026, "week": 6, "games": nfl, "cfb_games": cfb}
    doc = {"schema": 1, "stale_days": 30,
           "regional_maps": {"label": "Regional maps", "url": "https://maps.example/nfl"},
           "rows": [
        {"id": "cbs-pp", "service": "Paramount+", "leagues": ["NFL", "CFB"],
         "match": {"networks": ["CBS"], "days": ["*"], "windows": ["*"]},
         "status": "ok", "verified": "2026-10-12"},
        {"id": "nbc-pk", "service": "Peacock", "leagues": ["NFL"],
         "match": {"networks": ["NBC"], "days": ["*"], "windows": ["*"]},
         "status": "ok", "verified": "2026-10-12"},
        {"id": "yt", "service": "YouTube TV", "leagues": ["NFL"],
         "match": {"networks": ["CBS", "FOX", "NBC"], "days": ["*"], "windows": ["*"]},
         "status": "ok", "verified": "2026-10-12"},
        {"id": "sling", "service": "Sling TV", "label": "Sling TV (select markets)",
         "leagues": ["NFL"], "match": {"networks": ["FOX"], "days": ["Sun"],
                                       "windows": ["1:00", "4:05-4:25"]},
         "status": "ok", "verified": "2026-10-12"},
        {"id": "fubo", "service": "Fubo", "leagues": ["NFL"],
         "match": {"networks": ["FOX"], "days": ["*"], "windows": ["*"]},
         "status": "verify", "verified": "2026-10-12"}]}
    return u, week, doc


def watch_canary():
    import build_manifest as bm
    import carriage
    import site_build as sb
    fails = []
    u, week, doc = _fixture(sb)
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.MANIFEST, sb._carriage.load, sb.WX_DATA)

    def page(now_iso):
        sb._NOW_CACHE = u(now_iso)
        sb.MANIFEST = bm.build(sb._build_now(), None, None)
        return sb.render_where_to_watch(week, [week], "", current=True)

    try:
        sb.SB_DATA, sb.W2W_DATA, sb.WX_DATA = None, {"weeks": [week]}, None
        sb._carriage.load = lambda: doc
        html = page("2026-10-13T09:00")
        rows = {m.group(1): m.group(2) for m in re.finditer(
            r'<div class="w2w-row" data-gid="([^"]*)">(.*?)</div>', html, re.S)}

        # every game of the week has a kickoff and a network from the fixture
        want_net = {g["id"]: g["carriers"][0]["name"]
                    for g in week["games"] + week["cfb_games"]}
        if len(rows) != len(want_net):
            fails.append(f"watch: the page prints {len(rows)} games, the fixture has {len(want_net)}")
        for gid, net in want_net.items():
            row = rows.get(gid, "")
            txt = re.sub(r"<[^>]+>", " ", row)
            if not re.search(r"\b\d{1,2}:\d\d [AP]M ET\b", txt):
                fails.append(f"watch: game {gid} has no kickoff in ET")
            if sb.network_name(net) not in txt:
                fails.append(f"watch: game {gid} does not print its network {net!r}")

        # the streams follow the carriage rows
        def chips(gid):
            if gid not in rows:
                return None
            seg = rows[gid].split('class="w2w-streams">', 1)[1].split('<span class="w2w-res"')[0]
            return re.findall(r'<span class="w2w-str-c[^"]*"[^>]*>([^<]*)</span>', seg)
        exp = {"CHIGB": ["YouTube TV", "Sling TV (select markets)", "verify"],
               "LVNE": ["Paramount+", "YouTube TV"],
               "ARILAR": ["YouTube TV", "Sling TV (select markets)", "verify"],
               "DALPHI": ["YouTube TV"],      # Peacock is already a network chip: the feed lists it
               "LONPAR": [],
               "DENSEA": [],
               "LSUUGA": ["Paramount+"]}
        for gid, want in exp.items():
            got = chips(gid)
            if got != want:
                fails.append(f"watch: streams for {gid} read {got}, the carriage rows give {want}")
        if "Peacock" not in re.sub(r"<[^>]+>", " ", rows.get("DALPHI", "")):
            fails.append("watch: the Sunday night game does not print Peacock, which the feed lists")
        # Sling is Sunday 1:00 and the late windows only: the London game carries none
        if "Sling" in rows.get("LONPAR", ""):
            fails.append("watch: Sling printed on the early window it does not match")
        # change a row and the page changes: the streams are not typed into the template
        doc["rows"][0]["service"] = "Paramount Plus Changed"
        changed = page("2026-10-13T09:00")
        if "Paramount Plus Changed" not in changed:
            fails.append("watch: editing a carriage row did not change the page")
        doc["rows"][0]["service"] = "Paramount+"

        # a row past thirty days prints verify; on the thirtieth day it does not
        d30 = page("2026-11-11T09:00")        # verified 2026-10-12, so 30 days old
        d31 = page("2026-11-12T09:00")
        if "Paramount+" not in d30:
            fails.append("watch: a row exactly 30 days old already prints verify")
        if "Paramount+" in d31 or "YouTube TV" in d31:
            fails.append("watch: a row 31 days old still prints its service")
        if "verify" not in visible(d31):
            fails.append("watch: a row 31 days old does not print verify")

        # grouping by day, then by window, in kickoff order
        html = page("2026-10-13T09:00")
        d = read(html)
        heads = re.findall(r'<h2 class="w2w-dh">([^<]*)</h2>', html)
        want_heads = ["Sunday, Oct 11", "Thursday, Oct 15", "Saturday, Oct 17", "Sunday, Oct 18",
                      "Monday, Oct 19"]
        if heads != want_heads:
            fails.append(f"watch: the days read {heads}, expected {want_heads}")
        sun = html[html.index("Sunday, Oct 18"):html.index("Monday, Oct 19")]
        wins = re.findall(r'data-window="([^"]*)"', sun)
        if wins != ["early", "1:00", "4:05-4:25", "night"]:
            fails.append(f"watch: Sunday's windows read {wins}, not early, 1:00, 4:05-4:25, night")
        grp = {}
        for m in re.finditer(r'data-window="([^"]*)">(.*?)(?=<div class="w2w-wg"|</section>)', sun, re.S):
            grp[m.group(1)] = re.findall(r'data-gid="([^"]*)"', m.group(2))
        if grp != {"early": ["LONPAR"], "1:00": ["CHIGB", "LVNE"],
                   "4:05-4:25": ["ARILAR", "LACKC"], "night": ["DALPHI"]}:
            fails.append(f"watch: Sunday's games sit in {grp}")
        sat = html[html.index("Saturday, Oct 17"):html.index("Sunday, Oct 18")]
        if re.findall(r'data-window="([^"]*)"', sat) != ["early", "afternoon", "night"]:
            fails.append("watch: Saturday's college games are not grouped early, afternoon, night")

        # no score before the game; the final after
        for gid in ("CHIGB", "DENSEA", "ALATEN"):
            if re.search(r"\b\d+-\d+\b", re.sub(r"<[^>]+>", " ", rows.get(gid, ""))):
                fails.append(f"watch: {gid} prints a score before kickoff")
        if "Final 24-16" not in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rows.get("MINDET", ""))):
            fails.append("watch: the finished game does not print Final 24-16")
    except Exception as e:
        fails.append(f"watch: the fixture page raised {type(e).__name__}: {e}")
    finally:
        sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.MANIFEST, sb._carriage.load, sb.WX_DATA = was

    # the college feed: one day at a time, a refused day skipped
    try:
        import where_to_watch as w
        calls = []

        def fake(url):
            calls.append(url)
            day = re.search(r"dates=(\d{8})", url).group(1)
            if day == "20261016":
                raise OSError("refused")
            ev = {"id": "c" + day, "date": f"{day[:4]}-{day[4:6]}-{day[6:]}T16:00Z",
                  "status": {"type": {"state": "pre", "completed": False}},
                  "competitions": [{"competitors": [
                      {"homeAway": "home", "team": {"abbreviation": "H", "id": "1"}},
                      {"homeAway": "away", "team": {"abbreviation": "A", "id": "2"}}],
                      "geoBroadcasts": [{"media": {"shortName": "ESPN"}, "market": {"type": "National"}}]}]}
            return {"events": [ev, ev]}
        was_get = w._get
        w._get = fake
        try:
            got = w._cfb_week({"games": [{"kickoff_utc": "2026-10-18T17:00Z"}]})
        finally:
            w._get = was_get
        if len(calls) != 7 or "groups=80" not in calls[0] or "-" in re.search(r"dates=(\S+)", calls[0]).group(1):
            fails.append(f"watch: the college feed was asked {len(calls)} times, not once a day for 7 days: {calls[:2]}")
        if len(got) != 6 or any(g["league"] != "CFB" for g in got):
            fails.append(f"watch: the college week holds {len(got)} games, expected 6 (7 days, one refused, "
                         f"a doubled event counted once)")
    except Exception as e:
        fails.append(f"watch: the college feed check raised {type(e).__name__}: {e}")

    # the carriage file itself
    try:
        real = json.load(open(carriage.PATH, encoding="utf-8"))
        ids = set()
        for r in real["rows"]:
            tag = f"carriage row {r.get('id')!r}"
            if r["id"] in ids:
                fails.append(f"watch: duplicate {tag}")
            ids.add(r["id"])
            if not str(r.get("source") or "").startswith("https://"):
                fails.append(f"watch: {tag} has no https source")
            try:
                _d.date.fromisoformat(r.get("verified") or "")
            except ValueError:
                fails.append(f"watch: {tag} has no verified date")
            if r.get("status") not in ("ok", "verify"):
                fails.append(f"watch: {tag} has status {r.get('status')!r}")
            if r.get("status") == "ok" and len(r.get("says") or "") < 20:
                fails.append(f"watch: {tag} is ok but records nothing the page said")
            if r.get("status") == "verify" and not r.get("note"):
                fails.append(f"watch: {tag} is verify with no note saying why")
            if "—" in json.dumps(r, ensure_ascii=False):
                fails.append(f"watch: {tag} has an em dash")
        if not real.get("regional_maps", {}).get("url"):
            fails.append("watch: the carriage file has no regional maps link")
    except Exception as e:
        fails.append(f"watch: data/carriage.json did not load: {type(e).__name__}: {e}")
    return fails


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    fs = watch_canary()
    for f in fs:
        print("::error::" + f)
    print("WATCH CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
