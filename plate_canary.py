#!/usr/bin/env python3
"""plate_canary.py: S-5.6, no plate label is clipped at any width.

Jack's one-look correction of October 20, 2026: a plate label that overflows its plate at any width is
clipped. The week board's venue plate ("Roof usually closed" first) ran past its plate on the team
page at 768. This canary reads every plate the strip, the game pages and the team pages draw, in a
browser with the shipped fonts loaded, at 390, 768 and 1440 (scripts/plate-fit.mjs; a plate is any
displayed element on the plate color, so a plate the next change draws is read too). Three checks,
each seen red first (U-9):

  built     every plate on the gate's own build (the home, Scores, every game page, every team page) fits
            its box at all three widths
  longest   the longest label the data and the ruled lines can print is drawn by the REAL renderers (the
            team page's schedule row, the strip card, the game page's conditions block) in each place a
            plate sits, at the three widths and in a narrow box too, and fits
  same      every plate that FIT on main is drawn as main drew it (type size, plate box), at 21 widths, 14 on
            the sheet's grid and 7 off it; main is the stylesheet in fixtures/plate-base and the old markup
  blind     the same labels with the fit taken away (nowrap, a fixed size, a narrow box) MUST be reported
            clipped; a sweep that finds nothing there is blind and the canary fails on it

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import glob
import html as _html
import json
import os
import re
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WIDTHS = [320, 360, 390, 414, 600, 700, 768, 820, 900, 1024, 1100, 1280, 1440, 1920]
OFFGRID = [340, 500, 650, 860, 980, 1200, 1600]     # widths no breakpoint of the sheet was written for
ALL_WIDTHS = sorted(set(WIDTHS) | set(OFFGRID))
# main's stylesheet as it stood when S-5.6 began (69f3b8d): what a plate that already fit must still be drawn by.
# A later item that changes a plate on purpose updates this file on purpose.
BASE_CSS = os.path.join("fixtures", "plate-base", "site.css")
PLATE = "rgb(20, 26, 23)"    # --sbc-plate (#141A17), the color every plate of the look is on
SWEEP_TIMEOUT = 600
# S-5.6 round 4: stream labels the carriage rows can print on the strip card's chip row; the longest one that
# arrived with the data (the ESPN app's own name) clipped on the team pages at 320 and 340.
STREAM_LABELS = ["ESPN app (ESPN Unlimited)", "Peacock", "Fox One (Fox Sports app)"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def sweep(tree, pages, widths=WIDTHS, dump=None):
    """scripts/plate-fit.mjs over the pages. Returns (findings, summary, problems)."""
    node = shutil.which("node")
    if not node:
        return [], None, ["plate fit: node is not installed, so no plate was read in a browser"]
    tmp = tempfile.mkdtemp(prefix="plate-fit-")
    try:
        cfgp = os.path.join(tmp, "config.json")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"pages": pages, "widths": widths, "plate": PLATE, "dump": dump}, f)
        try:
            r = subprocess.run([node, os.path.join(HERE, "scripts", "plate-fit.mjs"), tree, cfgp],
                               capture_output=True, text=True, timeout=SWEEP_TIMEOUT)
        except subprocess.TimeoutExpired:
            return [], None, ["plate fit: the browser sweep timed out"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    found, summary, problems = [], None, []
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if "fail" in o:
            problems.append("plate fit: " + o["fail"])
        elif "summary" in o:
            summary = o["summary"]
        elif o.get("kind") == "clipped":
            found.append(o)
        else:
            problems.append("plate fit: " + json.dumps(o))
    if summary is None and not problems:
        problems.append("plate fit: the browser sweep wrote no summary" + (": " + r.stderr[-200:] if r.stderr else ""))
    return found, summary, problems


def _describe(found):
    """Failure strings, one per plate kind and width, never a count alone."""
    grp = {}
    for o in found:
        grp.setdefault((o["el"], o["width"], o["why"].split(" ")[0]), []).append(o)
    out = []
    for (el, w, kind), v in sorted(grp.items()):
        pg = sorted({x["page"] for x in v})
        where = ", ".join(pg[:3]) + (f" and {len(pg) - 3} more" if len(pg) > 3 else "")
        out.append(f"plate fit: {where} at {w}: {el} \"{v[0]['text']}\" is clipped ({v[0]['why']}, "
                   f"plate {v[0]['w']}px, type {v[0]['size']})")
    return out


def built_pages(out):
    """The pages that draw the strip, the game plates and the team plates."""
    pg = ["index.html", "scores.html"]
    pg += sorted(os.path.relpath(p, out) for p in glob.glob(os.path.join(out, "games", "*.html")))
    pg += sorted(os.path.relpath(p, out) for p in glob.glob(os.path.join(out, "teams", "**", "*.html"), recursive=True))
    return [p for p in pg if os.path.exists(os.path.join(out, p))]


def label_candidates(out, root=None):
    """Every label a one-line plate can print: the ruled lines, the data's own lines, and each label
    already drawn on the built pages. Returns a dict label -> where it came from."""
    root = root or HERE
    import conditions as cx
    c = {cx.ROOF_USUAL: "ruled line", "Dome · No weather": "ruled line",
         "Outside NWS coverage": "ruled line"}
    for v in cx.ROOF_LINES.values():
        c[v] = "ruled line"
    for d in DAYS:
        c[f"Conditions from {d}"] = "ruled line, longest weekday"
    try:
        data = json.load(open(os.path.join(root, "site", "data", "conditions.json"), encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    for e in (data.get("games") or {}).values():
        line = (e.get("words") or {}).get("line")
        if line:
            c.setdefault(line, "data")
    for p in built_pages(out):
        h = open(os.path.join(out, p), encoding="utf-8").read()
        for m in re.findall(r'<p class="sbc-one"[^>]*>([^<]*)</p>', h):
            c.setdefault(_html.unescape(m), "built " + p)
        for m in re.findall(r'<span class="tms-pl tms-one"[^>]*>([^<]*)</span>', h):
            c.setdefault(_html.unescape(m), "built " + p)
    return c


def _shell(out):
    """The head and the foot of a built team page: a fixture is a real page with a main of our own."""
    h = open(os.path.join(out, "teams", "atl.html"), encoding="utf-8").read()
    m = re.search(r"<main\b[^>]*>", h)
    e = h.rfind("</main>")
    if not m or e < 0:
        return None
    return h[:m.end()], h[e:]


def fixtures(out, labels, blind):
    """(pages, problems): fixture pages drawn by the real renderers. blind=True takes the fit away."""
    import site_build as sb
    sh = _shell(out)
    if not sh:
        return {}, ["plate fit: the built team page has no main to build a fixture in"]
    head, foot = sh
    ent = {}
    real = sb.cx_entry
    sb.cx_entry = lambda g: ent.get(str((g or {}).get("id")))
    try:
        rows, strips, games = [], [], []
        for i, lab in enumerate(labels):
            gid = f"fx{i}"
            ent[gid] = {"status": "roofed", "words": {"line": lab}}
            rows.append({"week": i + 1, "date": "2026-11-01T18:00:00Z", "home": True, "opp": "ATL",
                         "opp_full": "Atlanta Falcons", "state": "pre", "time_set": True, "net": "CBS",
                         "id": gid, "page": False})
            wx, _ = sb.sbc_weather({"id": gid}, ent[gid])
            strips.append(wx)
        team = sb._tms_board(rows)
        no_fit = ' style="white-space:nowrap;overflow-wrap:normal;font-size:18px"'
        if blind:
            team = team.replace('class="tms-pl tms-one"', 'class="tms-pl tms-one"' + no_fit)
            strips = [s.replace('<p class="sbc-one">', '<p class="sbc-one"' + no_fit + ">") for s in strips]
        body = ""
        # the team row sits in the page grid at every width; a box would only invent a layout
        body += f'<div class="fx-box">{team}</div>'
        for w in ("", "max-width:330px", "max-width:240px"):
            if blind and not w:
                continue
            st = f' style="{w}"' if w else ""
            body += "".join(f'<div class="fx-box"{st}><article class="tk-c sbc">{s}</article></div>' for s in strips)
            body += "".join(f'<div class="fx-box"{st}><section class="sbc sbg"><div class="sbg-cx">{s}</div></section></div>'
                            for s in strips)
        if not blind:
            # the strip card's chip row on a team page: the real card and the real stream chip, in the page grid
            for i, sl in enumerate(STREAM_LABELS):
                g = {"id": f"fxs{i}", "league": "cfb", "state": "pre", "start_utc": "2026-11-01T18:00:00Z",
                     "network": "SEC Network", "home": {"abbr": "AUB", "name": "Auburn"},
                     "away": {"abbr": "MIZ", "name": "Missouri"}}
                chip = sb._svc_tag(sl, "", "tk-chip tk-stream", ' data-lens-only="watch"')
                body += f'<div class="fx-box">{sb.sbc_card(g, {}, ticket=True, stream=chip)}</div>'
        if blind:
            # the team row's own wxs column is narrow, and the label is told not to wrap
            body = body.replace('<span class="tms-wxs">', '<span class="tms-wxs" style="width:140px">')
        return {"fixture.html": head + body + foot}, []
    finally:
        sb.cx_entry = real


def base_tree(out, pages, root=None):
    """A copy of the built pages drawn as main drew them: main's stylesheet (BASE_CSS) and main's two markup
    details (the line score's columns, no --w on a number plate). Same data, so any difference is the change."""
    root = root or HERE
    base = tempfile.mkdtemp(prefix="plate-base-")
    os.mkdir(os.path.join(base, "assets"))
    for n in os.listdir(os.path.join(out, "assets")):
        if n != "site.css":
            os.symlink(os.path.join(out, "assets", n), os.path.join(base, "assets", n))
    shutil.copy(os.path.join(root, BASE_CSS), os.path.join(base, "assets", "site.css"))
    cols = re.compile(r"minmax\(min-content,1fr\) repeat\((\d+),minmax\(22px,var\(--sbc-q\)\)\) var\(--sbc-t\)")
    for pg in pages:
        h = open(os.path.join(out, pg), encoding="utf-8").read()
        h = cols.sub(r"minmax(0,1fr) repeat(\1,var(--sbc-q)) var(--sbc-t)", h)
        h = re.sub(r'(<span class="sbg-big") style="--w:[0-9.]+"', r"\1", h)
        dst = os.path.join(base, pg)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(h)
    return base


def unchanged(new, old):
    """Failure strings for every plate that FIT on main (and sits in a group with no clipped plate on main) whose
    size, plate box or type differs from main's. new and old are the sweeps' dumps."""
    ix = {(r["page"], r["width"]): r["all"] for r in old}
    fails, grp = [], {}
    seen = 0
    for r in new:
        b = ix.get((r["page"], r["width"]))
        if b is None:
            fails.append(f"plate same: {r['page']} at {r['width']} was read on the branch and not on main")
            continue
        seen += 1
        if len(b) != len(r["all"]):
            fails.append(f"plate same: {r['page']} at {r['width']} draws {len(r['all'])} plates, main {len(b)}")
            continue
        badg = {x["g"] for x in b if x["bad"] and x["g"] >= 0}
        for ob, nw in zip(b, r["all"]):
            if ob["bad"] or ob["g"] in badg:
                continue
            if abs(ob["fs"] - nw["fs"]) > 0.01 or abs(ob["w"] - nw["w"]) > 0.5 or abs(ob["h"] - nw["h"]) > 0.5:
                grp.setdefault((nw["el"], r["width"]), []).append((r["page"], ob, nw))
    if not seen:
        fails.append("plate same: no page was read on both sides, so nothing was compared")
    for (el, w), v in sorted(grp.items()):
        pg = sorted({x[0] for x in v})
        o, n = v[0][1], v[0][2]
        fails.append(f"plate same: {', '.join(pg[:3])}{' and %d more' % (len(pg) - 3) if len(pg) > 3 else ''} at {w}: {el} "
                     f"fit on main ({o['fs']}px type, {o['w']}x{o['h']}) and is drawn {n['fs']}px, {n['w']}x{n['h']} "
                     f"({len(v)} plates)")
    return fails, seen


def plate_canary(out, root=None):
    fails = []
    if not out or not os.path.isdir(out):
        return ["plate fit: the gate's build wrote no tree, so no plate was checked"]
    pages = built_pages(out)
    if "index.html" not in pages or not any(p.startswith("games/") for p in pages) \
            or not any(p.startswith("teams/") for p in pages):
        fails.append("plate fit: the build has no home, game page or team page, so the check proves nothing")
    # built: the gate's own tree
    dumpd = tempfile.mkdtemp(prefix="plate-dump-")
    newd = os.path.join(dumpd, "new.json")
    found, summ, probs = sweep(out, pages, ALL_WIDTHS, newd)
    fails += probs + _describe(found)
    if summ is not None:
        if not summ.get("plates"):
            fails.append("plate fit: no plate was measured on the built pages")
        print(f"plate fit: {summ.get('pages', 0)} pages at {summ.get('widths')}, {summ.get('plates', 0)} plates read, "
              f"{summ.get('findings', 0)} clipped, {summ.get('seconds', 0)} s in the browser")
    # same: a plate that fit on main is drawn exactly as main drew it, at every width
    base = None
    try:
        base = base_tree(out, pages, root)
        oldd = os.path.join(dumpd, "old.json")
        _f, _s, probs2 = sweep(base, pages, ALL_WIDTHS, oldd)
        fails += [x for x in probs2 if "findings" not in x]
        try:
            nw, od = json.load(open(newd)), json.load(open(oldd))
        except (OSError, ValueError):
            nw, od = [], []
            fails.append("plate same: the sweeps wrote no records to compare")
        if nw:
            f2, seen = unchanged(nw, od)
            fails += f2
            print(f"plate same: {seen} page-widths compared with main's stylesheet and markup on the same data, "
                  f"{len(f2)} plate kinds drawn differently where they fit")
    finally:
        shutil.rmtree(dumpd, ignore_errors=True)
        if base:
            shutil.rmtree(base, ignore_errors=True)
    # longest: the real renderers, every label, every place a plate sits
    cands = label_candidates(out, root)
    labels = sorted(cands, key=lambda s: (-len(s), s))
    longest = labels[0]
    tmp = tempfile.mkdtemp(prefix="plate-fx-")
    try:
        os.symlink(os.path.join(out, "assets"), os.path.join(tmp, "assets"))
        for blind in (False, True):
            pgs, probs = fixtures(out, labels, blind)
            fails += probs
            for name, h in pgs.items():
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                    f.write(h)
            if probs:
                continue
            found, summ, probs = sweep(tmp, ["fixture.html"])
            if blind:
                # the same labels with the fit taken away must be caught, on both kinds of plate
                kinds = {o["el"].split(".")[1] if "." in o["el"] else o["el"] for o in found}
                if probs and not found:
                    fails += probs
                for want in ("tms-one", "sbc-one"):
                    if not any(want in o["el"] for o in found):
                        fails.append(f"plate fit: a {want} plate whose label is wider than its plate was NOT reported "
                                     f"clipped, so the check is blind")
                widths = {o["width"] for o in found}
                if widths != set(WIDTHS):
                    fails.append(f"plate fit: the clipped fixture was caught at {sorted(widths)}, not at {WIDTHS}")
            else:
                fails += [x for x in probs if "findings" not in x]
                fails += [f"{x} (fixture: longest label \"{longest}\" and {len(labels) - 1} others)"
                          for x in _describe(found)]
                if summ is not None:
                    if summ.get("plates", 0) < len(labels) * 3:
                        fails.append("plate fit: the label fixture drew fewer plates than labels, so it proves nothing")
                    print(f"plate fit: {len(labels)} labels, longest \"{longest}\" ({len(longest)} characters, "
                          f"{cands[longest]}), {summ.get('plates', 0)} fixture plates at {WIDTHS}, "
                          f"{summ.get('findings', 0)} clipped")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    f = plate_canary(sys.argv[1] if len(sys.argv) > 1 else None)
    for x in f:
        print("FAIL", x)
    print("plate canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
