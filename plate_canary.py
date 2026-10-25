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
WIDTHS = [390, 768, 1440]
PLATE = "rgb(20, 26, 23)"    # --sbc-plate (#141A17), the color every plate of the look is on
SWEEP_TIMEOUT = 600
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def sweep(tree, pages, widths=WIDTHS):
    """scripts/plate-fit.mjs over the pages. Returns (findings, summary, problems)."""
    node = shutil.which("node")
    if not node:
        return [], None, ["plate fit: node is not installed, so no plate was read in a browser"]
    tmp = tempfile.mkdtemp(prefix="plate-fit-")
    try:
        cfgp = os.path.join(tmp, "config.json")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"pages": pages, "widths": widths, "plate": PLATE}, f)
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
        for w in ("", "max-width:420px", "max-width:150px"):
            if blind and not w:
                continue
            st = f' style="{w}"' if w else ""
            body += f'<div class="fx-box"{st}>{team}</div>'
        for w in ("", "max-width:330px", "max-width:150px"):
            if blind and not w:
                continue
            st = f' style="{w}"' if w else ""
            body += "".join(f'<div class="fx-box"{st}><article class="tk-c sbc">{s}</article></div>' for s in strips)
            body += "".join(f'<div class="fx-box"{st}><section class="sbc sbg"><div class="sbg-cx">{s}</div></section></div>'
                            for s in strips)
        if blind:
            # the team row's own wxs column is narrow, and the label is told not to wrap
            body = body.replace('<span class="tms-wxs">', '<span class="tms-wxs" style="width:140px">')
        return {"fixture.html": head + body + foot}, []
    finally:
        sb.cx_entry = real


def plate_canary(out, root=None):
    fails = []
    if not out or not os.path.isdir(out):
        return ["plate fit: the gate's build wrote no tree, so no plate was checked"]
    pages = built_pages(out)
    if "index.html" not in pages or not any(p.startswith("games/") for p in pages) \
            or not any(p.startswith("teams/") for p in pages):
        fails.append("plate fit: the build has no home, game page or team page, so the check proves nothing")
    # built: the gate's own tree
    found, summ, probs = sweep(out, pages)
    fails += probs + _describe(found)
    if summ is not None:
        if not summ.get("plates"):
            fails.append("plate fit: no plate was measured on the built pages")
        print(f"plate fit: {summ.get('pages', 0)} pages at {summ.get('widths')}, {summ.get('plates', 0)} plates read, "
              f"{summ.get('findings', 0)} clipped, {summ.get('seconds', 0)} s in the browser")
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
