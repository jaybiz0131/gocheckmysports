#!/usr/bin/env python3
"""
kill_streak.py: the kill ledger and its alarm (owner ruling 2026-08-03, N=3).

THE CHASSIS COPY. Identical in gocheckmycrypto, gocheckmynews and gocheckmysports.

WHY THIS EXISTS
  The Coldcard case: the desk broke the story on July 31, and over the next three days
  intake kept carrying the escalation, the editor kept ranking it, the writer kept
  drafting it, and the approver killed THIRTEEN consecutive drafts on accuracy while the
  story grew from $38M to nearly $89M and led every competitor. Each kill was logged
  individually and correctly; nothing counted them. FOMC died the same way, three kills
  in two days, promised to readers in the Week Ahead. The gate ran and caught; the
  pattern went unwatched.

WHAT IT DOES
  Reads editorial-log.json, groups rejected drafts into DEVELOPMENTS using the dedup
  guard's own matcher (dedupe.same_event, the same grain the publish guard uses), and
  treats a development's streak as broken only when a published story matches it after
  the last kill. Two consumers:

    kill_history(title)  -> the prior kills for a matching unbroken development, reasons
                            VERBATIM. The writer prepends these to the next draft's
                            prompt, so attempt N+1 knows exactly why attempts 1..N died
                            (the wraprescue pattern, applied at story level).
    main()               -> reports streaks; at N >= 3 files ONE deduplicated DIGEST
                            issue covering every live streak, each kill quoted verbatim
                            so a human can judge legitimate-versus-theater. '7.3K vs
                            7,300' is the calibration case study, in the template.

  Advisory for the run, loud for a human: never blocks anything.
"""
import glob
import json
import os
import sys

import common
import dedupe

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "editorial-log.json")
CONTENT = os.path.join(HERE, "site", "content")
STREAK_N = 3          # owner ruling 2026-08-03: three consecutive kills open the flag
RECENT_DAYS = 10      # a kill older than this is history, not a live streak


def _entries():
    try:
        return json.load(open(LOG, encoding="utf-8"))
    except Exception:
        return []


def _published(since_date=""):
    out = []
    for p in glob.glob(os.path.join(CONTENT, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("example") or str(d.get("id") or "").startswith("wrap-"):
            continue
        if str(d.get("date") or "") >= since_date:
            out.append((str(d.get("date") or ""), str(d.get("title") or "")))
    return out


# A REFUSAL IS NOT A KILL (family audit 2026-09-02). When the writer was handed a
# story with no usable brief it wrote its refusal AS the draft ("STORY REJECTED: Research
# Brief Required", "STORY CANNOT BE DRAFTED: No brief supplied for ..."), the approver
# killed that, and the ledger recorded a kill under the refusal's title. The streak
# alarm then rang on developments named "STORY REJECTED: Research Brief Required" (6x on
# the sports desk), and the spend breaker parked real stories behind them. The writer
# no longer emits these (writer.validate drops them as sourcing failures); the ledger
# reader ignores any that are still in the log.
REFUSAL_RE = None


def is_refusal_title(title):
    global REFUSAL_RE
    if REFUSAL_RE is None:
        import re
        REFUSAL_RE = re.compile(
            # "CANNOT PUBLISH: No Source Text Available" reached PUBLISH on the news desk
            # 2026-08-15 and was still live three weeks later, on news.html with its own
            # article page, because this pattern knew "cannot draft" but not "cannot
            # publish". The brief says to extend this the moment a new refusal phrasing
            # appears rather than let it ledger; the same phrasing also has to be caught
            # before it becomes a story, which is writer._is_refusal calling this.
            r"^\s*(?:held\s*:|(?:story\s+(?:rejected|held|cannot\s+be\s+drafted|not\s+drafted|"
            r"withheld)|cannot\s+(?:draft|publish|be\s+published)|no\s+(?:research\s+)?brief|"
            r"no\s+source\s+text|draft\s+(?:refused|withheld)|"
            r"unable\s+to\s+draft|insufficient\s+(?:brief|source))\b)", re.I)
    return bool(REFUSAL_RE.search(str(title or "")))


def _recent_kills():
    import datetime
    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()
    kills = []
    for e in _entries():
        d = str(e.get("date") or "")
        if d < cutoff:
            continue
        for r in e.get("rejected") or []:
            if r.get("headline") and not is_refusal_title(r["headline"]):
                kills.append({"date": d, "headline": r["headline"],
                              "category": r.get("category", "?"),
                              "reasons": [str(x) for x in (r.get("reasons") or [])]})
    return kills


def _group(kills):
    """Kills bucketed into developments by the publish guard's own matcher."""
    groups = []
    for k in kills:
        for g in groups:
            if dedupe.same_event(g[0]["headline"], "", k["headline"], ""):
                g.append(k)
                break
        else:
            groups.append([k])
    return groups


def _last_publish(group, published):
    """The date the desk last published this development, or '' if it never did."""
    dates = [date for date, title in published
             if dedupe.same_event(group[0]["headline"], "", title, "")]
    return max(dates) if dates else ""


def _live_run(group, published):
    """The kills SINCE the desk last published this development, oldest first.

    A streak means 'the desk keeps killing this and never runs it'. The old rule only
    broke a streak when a publish was dated at or after the LAST kill, so a single
    later kill resurrected the entire history: the Treasury GENIUS development showed
    twelve kills while a correct story about it had been live since 2026-08-17, and
    most of those kills were the desk re-drafting the story it had already published
    (fixed upstream by the researcher's rehash guard). A publish settles everything
    before it; only what the desk killed afterwards is evidence of abandonment.
    """
    cut = _last_publish(group, published)
    return sorted([k for k in group if not cut or k["date"] > cut],
                  key=lambda k: k["date"])


def _unbroken(group, published):
    """Kept for callers that want the old boolean: is anything still unresolved?"""
    return bool(_live_run(group, published))


def streaks(n=STREAK_N):
    kills = _recent_kills()
    if not kills:
        return []
    pub = _published(since_date=min(k["date"] for k in kills))
    out = []
    for g in _group(kills):
        run = _live_run(g, pub)          # only kills since the last publish count
        if len(run) >= n:
            out.append(run)
    return out


def kill_history(title):
    """Prior unbroken kills matching this title's development, oldest first."""
    kills = _recent_kills()
    if not kills:
        return []
    pub = _published(since_date=min(k["date"] for k in kills))
    for g in _group(kills):
        if dedupe.same_event(g[0]["headline"], "", title, ""):
            return _live_run(g, pub)     # kills since the last publish, never older
    return []


SPEND_BREAKER_N = 5   # consecutive kills on one development before the desk stops paying
                      # to draft it again and hands the call to a human
SPEND_BREAKER_SAME = 3  # fewer are needed when the SAME objection keeps landing


def _reason_key(k):
    """A coarse fingerprint of WHY a draft died, so 'the same objection again' can be
    recognised across attempts without demanding identical wording."""
    import re
    blob = " ".join(k.get("reasons") or []).lower()
    blob = re.sub(r"[^a-z ]", " ", blob)
    words = [w for w in blob.split() if len(w) > 4]
    return frozenset(words[:40])


def stop_drafting(title, n=SPEND_BREAKER_N, same_n=SPEND_BREAKER_SAME):
    """Should the desk stop drafting this development and hand it to a human?

    THE CIRCUIT BREAKER (2026-08-17 handoff, redesigned against the evidence). The
    handoff proposed breaking when attempt N+1 dies on the SAME objection as attempt N,
    on the reasoning that repeating an argument the desk keeps losing cannot help. The
    log does not support that premise: the ETF-inflow development died eleven times and
    the objections were all DIFFERENT, an unsignalled attribution, then a paraphrase
    that moved 'performance' to 'inflow', then a 'mid-April' the brief never said, then
    an omitted bear case. The writer fixes each point and surfaces a new one.

    So the primary rule is count, not repetition: after N consecutive kills the desk is
    empirically not converging, whatever the reasons say, and further drafting spends
    research, writing and approval budget to publish nothing. The same-objection case
    still exists and breaks sooner, because that one really is arguing in a circle.

    Returns (True, reason) or (False, ""). Advisory: it stops DRAFTING, never publishing,
    and the digest carries the development to a human who can decide whether the gate is
    right (drop it) or the brief is wrong (fix the inputs)."""
    hist = kill_history(title)
    if len(hist) >= same_n:
        a, b = _reason_key(hist[-1]), _reason_key(hist[-2])
        if a and b and len(a & b) / max(1, min(len(a), len(b))) >= 0.6:
            return True, (f"{len(hist)} consecutive kills and the last two land on "
                          f"substantially the same objection; this is a circle, not an edit")
    if len(hist) >= n:
        return True, (f"{len(hist)} consecutive kills with no publish; the desk is not "
                      f"converging on this development and further drafts spend without "
                      f"changing the outcome")
    return False, ""


def _flag_digest(groups):
    """ONE digest issue for all live streaks (25 on first run; one issue per
    development would flood the tracker and bury the signal). Deduplicated by title;
    close it after triage and the next breach refiles with current state."""
    import urllib.request
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    title = f"Kill streaks: {len(groups)} developments the desk is abandoning"
    if not tok or not repo:
        print(f"kill_streak: no GH token; digest reported in log only")
        return
    hdrs = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues?state=open&labels=pipeline",
            headers=hdrs)
        if any(i["title"].startswith("Kill streaks:")
               for i in json.load(urllib.request.urlopen(req))):
            print("kill-streak digest already open; not duplicating")
            return
        # GitHub rejects an issue body over 65536 chars, and on 2026-08-04 the crypto
        # desk's 24 streaks quoted out to 75182: the digest silently failed to file
        # while its siblings' shorter ones went through. The alarm must never be the
        # thing that breaks. Sections are added while they fit, and the tail is named
        # rather than dropped in silence.
        LIMIT = 60000
        sections, used, dropped = [], 0, 0
        for g in sorted(groups, key=lambda g: -len(g)):
            block = [f"\n### {len(g)}x: {g[-1]['headline'][:90]} "
                     f"({g[0]['date']}..{g[-1]['date']})"]
            for k in g:
                block.append(f"- **{k['date']}** [{k['category']}] {k['headline'][:90]}")
                for r in k["reasons"][:2]:
                    block.append(f"  - {r[:300]}")
            size = sum(len(x) + 1 for x in block)
            if used + size > LIMIT:
                dropped += 1
                continue
            sections.extend(block)
            used += size
        if dropped:
            sections.append(f"\n_{dropped} further streak(s) omitted to fit GitHub's "
                            f"issue-body limit; the run log lists every one._")
        stopped = [g for g in groups if stop_drafting(g[-1]["headline"])[0]]
        body = (
            (f"**{len(stopped)} of these are no longer being drafted** (the spend "
             f"breaker: repeated paid attempts that published nothing). Each needs a "
             f"human call: is the gate right and the story should be dropped, or is the "
             f"brief wrong and the inputs need fixing?\n\n" if stopped else "") +
            "Developments with three or more consecutive approver kills and no publish "
            "breaking the streak (the Coldcard pattern: 13 kills over three days while "
            "the story tripled and led every competitor).\n\nEach kill is quoted so a "
            "human can judge legitimate-versus-theater. The calibration case study is "
            "'7.3K BTC vs 7,300 BTC': a kill over notation identity is theater; a kill "
            "over a smuggled or contradicted fact is the gate working.\n"
            + "\n".join(sections) +
            "\n\nThe next draft of each development automatically carries its prior "
            "objections verbatim in the writer prompt. Close after triage; the next "
            "breach refiles with current state.")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues",
            data=json.dumps({"title": title, "body": body,
                             "labels": ["pipeline"]}).encode(),
            headers=hdrs, method="POST")
        urllib.request.urlopen(req)
        print(f"kill-streak digest opened: {title}")
    except Exception as e:
        detail = ""
        try:
            detail = f" {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        except Exception:
            pass
        print(f"kill_streak: could not file digest ({e.__class__.__name__}{detail})")


def main():
    hits = streaks()
    if not hits:
        print("kill_streak: no unbroken kill streaks at threshold "
              f"{STREAK_N} in the last {RECENT_DAYS} days.")
        return 0
    # ADVISORY, SO A WARNING (family audit 2026-09-02): this check "never blocks
    # anything" by its own charter, yet it annotated every run with one ::error:: per
    # live streak, six to ten red lines on green runs, and the owner read every run as
    # failed. The digest issue below is the alarm; the annotation is the pointer to it.
    for g in hits:
        common.gh("warning",
                  f"kill_streak: '{g[-1]['headline'][:70]}' killed {len(g)}x "
                  f"consecutively ({g[0]['date']}..{g[-1]['date']}) with no publish; "
                  f"the desk is abandoning a development it owns.")
    _flag_digest(hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
