#!/usr/bin/env python3
"""teams.py: the logic behind the team pages (Sprint S-3a, Program 7 section 3).

Pure functions over the desk's own files: no network, no model, no build state, so the canary can
test them on fixtures (teams_canary.py). site_build.py renders; this decides.

THE TOP FORTY PROGRAMS. The AP Top 25 first, in rank order, then the rest of the week board's
college programs by record, best first, until there are forty. Ranked is the poll's judgement and
the board is what the reader can see this week; the order between them is the only editorial call
and it is made here, once, in the open. One page per school: a school that is both ranked and on
the board is one program.

THE CONDITIONS LOG. A game enters the log when the Worker's flags say a number or an alert matters
(wind 15 mph and over, a 40 percent chance of precipitation and over, a feel below 32 or above 90,
an alert). The numbers on a log line are the Worker's own. Past games are not in conditions.json
once the week rolls, so conditions_report.py carries each report's flagged games in its "log"; the
build merges every report's log with the live file, the latest reading of a game winning.
"""

import re


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _pct(rec):
    m = re.match(r"\s*(\d+)-(\d+)(?:-(\d+))?", rec or "")
    if not m:
        return -1.0
    w, l, t = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    n = w + l + t
    return (w + t / 2) / n if n else -1.0


def _teams_on_board(cfb_games):
    for g in cfb_games:
        for side in ("away", "home"):
            t = g.get(side) or {}
            if t.get("school") or t.get("full"):
                yield t


def top_programs(rankings, cfb_games, n=40):
    """The n programs that get a page, as dicts: slug, school, mascot, abbr, id, color, rank,
    previous, trend, record, ranked."""
    by_school, by_abbr = {}, {}
    for t in _teams_on_board(cfb_games):
        by_school[t.get("school") or ""] = t
        by_abbr[t.get("abbr") or ""] = t
    out, seen = [], set()

    def add(school, base, **kw):
        sl = slug(school)
        if not sl or sl in seen:
            return
        seen.add(sl)
        d = {"slug": sl, "school": school, "mascot": base.get("mascot") or "", "abbr": base.get("abbr") or "",
             "id": str(base.get("id") or ""), "color": base.get("color") or "",
             "record": base.get("record") or "", "rank": None, "previous": None, "trend": "", "ranked": False}
        d.update({k: v for k, v in kw.items() if v not in (None, "")})
        out.append(d)

    for r in sorted(((rankings or {}).get("rows") or []), key=lambda r: r.get("rank") or 99):
        school = r.get("school") or ""
        base = dict(by_school.get(school) or by_abbr.get(r.get("abbr") or "") or {})
        base.setdefault("abbr", r.get("abbr"))
        base["mascot"] = base.get("mascot") or r.get("mascot")
        add(school, base, rank=r.get("rank"), previous=r.get("previous"), trend=r.get("trend") or "",
            record=r.get("record") or base.get("record"), ranked=True)
    rest = sorted((t for t in by_school.values() if slug(t.get("school")) not in seen),
                  key=lambda t: (-_pct(t.get("record")), t.get("school") or ""))
    for t in rest:
        if len(out) >= n:
            break
        add(t.get("school"), t)
    return out[:n]



# S-5.0: THE REGISTRY (J-9, option (a), ruled October 20, 2026). Under the law that URLs never change, a
# college team page once built is built every week after; the set only grows. data/cfb-teams-built.json
# holds every program whose page has been built: its slug, the identity it was built with (school,
# mascot, abbreviation, ESPN id, color), the Eastern date it was first built and where that is recorded.
# These three functions are the whole of the rule and touch no file; site_build.py reads and writes.

REGISTRY_FIELDS = ("slug", "school", "mascot", "abbr", "id", "color", "since", "source")
_SLUG_OK = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def registry_entries(doc):
    """The well-formed entries of a registry document, in its order. An entry is refused unless its slug
    is the slug of its school and every field it carries is a string (the id may be a number): the published copy is read back
    by the next build, and nothing it holds may name a path the build would not have made."""
    progs = doc.get("programs") if isinstance(doc, dict) else None
    out, seen = [], set()
    for e in progs if isinstance(progs, list) else []:
        if not isinstance(e, dict):
            continue
        if any(not isinstance(e.get(k, ""), (int, str) if k == "id" else str) or isinstance(e.get(k), bool)
               for k in REGISTRY_FIELDS):
            continue
        sl = e.get("slug") or ""
        if not _SLUG_OK.fullmatch(sl) or slug(e.get("school")) != sl or len(sl) > 80 or sl in seen:
            continue
        seen.add(sl)
        out.append({k: str(e.get(k) or "") for k in REGISTRY_FIELDS})
    return out


def registry_union(doc, programs, since="", source=""):
    """The registry with every program added that it does not hold. Nothing is removed and no filled field
    changes; a field the registry holds empty takes the program's value (an id the board names later).
    `programs` are the week's forty or another registry's entries. Kept in slug order."""
    by = {e["slug"]: e for e in registry_entries(doc)}
    for p in programs or []:
        sl = (p or {}).get("slug") or ""
        if not _SLUG_OK.fullmatch(sl) or slug(p.get("school")) != sl:
            continue
        ident = {k: str(p.get(k) or "") for k in ("school", "mascot", "abbr", "id", "color")}
        if sl in by:
            e = by[sl]
            for k, v in ident.items():
                if not e.get(k) and v:
                    e[k] = v
            continue
        by[sl] = {"slug": sl, **ident, "since": str(p.get("since") or since or ""),
                  "source": str(p.get("source") or source or "")}
    out = {k: v for k, v in (doc.items() if isinstance(doc, dict) else []) if k != "programs"}
    out["programs"] = [by[k] for k in sorted(by)]
    return out


def registry_programs(doc, top, cfb_games):
    """Every program that gets a page: the week's forty first, as top_programs made them, then each
    registry program not among them, in slug order. A registry program comes from the same data the forty
    use: the week's board when the board holds it (matched on the ESPN id, else the school), and its
    stored identity when it does not, with no record, since a record the week does not state is stale."""
    out = list(top or [])
    have = {p["slug"] for p in out}
    by_id, by_school = {}, {}
    for t in _teams_on_board(cfb_games or []):
        if t.get("id"):
            by_id[str(t.get("id"))] = t
        by_school[slug(t.get("school") or "")] = t
    for e in registry_entries(doc):
        if e["slug"] in have:
            continue
        b = (by_id.get(e["id"]) if e["id"] else None) or by_school.get(e["slug"]) or {}
        out.append({"slug": e["slug"], "school": e["school"],
                    "mascot": b.get("mascot") or e["mascot"], "abbr": b.get("abbr") or e["abbr"],
                    "id": str(b.get("id") or e["id"] or ""), "color": b.get("color") or e["color"],
                    "record": b.get("record") or "", "rank": None, "previous": None, "trend": "",
                    "ranked": False})
        have.add(e["slug"])
    return out

def _kind_tags(e):
    f = (e or {}).get("flags") or {}
    tags = []
    w = f.get("wind") or {}
    if w.get("on"):
        tags.append({"kind": "wind", "text": f"Wind up to {round(w['max_mph'])} mph"})
    p = f.get("precip") or {}
    if p.get("on"):
        tags.append({"kind": "rain", "text": f"{round(p['max_pct'])} percent chance of rain"})
    fe = f.get("feels") or {}
    if fe.get("on"):
        if isinstance(fe.get("min_f"), (int, float)) and fe["min_f"] < fe.get("below_f", 32):
            tags.append({"kind": "cold", "text": f"Feels as cold as {round(fe['min_f'])} degrees"})
        elif isinstance(fe.get("max_f"), (int, float)) and fe["max_f"] > fe.get("above_f", 90):
            tags.append({"kind": "heat", "text": f"Feels as hot as {round(fe['max_f'])} degrees"})
    for a in ((e or {}).get("alerts") or [])[:2]:
        if a.get("event"):
            tags.append({"kind": "alert", "text": str(a["event"])})
    return tags


def bye_weeks(events):
    """The weeks of the season (1 to 18) a team has no fixture, from its fixtures. The feed's own
    "bye" field is wrong for many teams (Chicago's said 7; the week it did not play was 10)."""
    have = {e.get("week") for e in events or [] if e.get("week")}
    if not have:
        return []
    return [w for w in range(1, 19) if w not in have]


def log_entry(g, e):
    """One log line for a game, or None when the Worker's flags say nothing matters. A game under a
    roof is never logged: the weather outside is not the game's weather (S-3a, 15 October)."""
    if not e or e.get("status") != "forecast" or e.get("roof") in ("retractable", "fixed"):
        return None
    tags = _kind_tags(e)
    if not tags:
        return None
    a, h = g.get("away") or {}, g.get("home") or {}
    return {"id": str(g.get("id")), "league": g.get("league"), "start_utc": g.get("start_utc") or "",
            "away": {"abbr": a.get("abbr"), "id": str(a.get("id") or ""), "name": a.get("full") or a.get("name")},
            "home": {"abbr": h.get("abbr"), "id": str(h.get("id") or ""), "name": h.get("full") or h.get("name")},
            "venue": g.get("venue") or "", "tags": tags}


def merge_logs(*lists):
    """Every list's entries, one per game id, the later list's reading winning."""
    by = {}
    for lst in lists:
        for x in lst or []:
            by[x["id"]] = x
    return sorted(by.values(), key=lambda x: (x.get("start_utc") or "", x["id"]))


def team_log(entries, league, abbr=None, tid=None):
    """This team's own entries. NFL matches on the abbreviation, college on the team id: an
    abbreviation is not an identity across leagues (MIA is the Dolphins and the Hurricanes)."""
    out = []
    for x in entries or []:
        if x.get("league") != league:
            continue
        for side in ("away", "home"):
            t = x.get(side) or {}
            if (abbr and t.get("abbr") == abbr and league == "NFL") or (tid and t.get("id") == str(tid)):
                out.append(x)
                break
    return out
