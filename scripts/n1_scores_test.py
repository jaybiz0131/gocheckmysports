#!/usr/bin/env python3
"""N-1 (November 21, 2026): a card never draws an old reading as current (class B, the scores feed).

Read live at 3:43 PM ET on Saturday November 21: the reading of 20:43:10 UTC (commit d852ed8, kept byte for byte as
fixtures/n1/scoreboard-2026-11-21T2043Z.json) carried LSU at Tennessee as "pre", "11/21 - 3:30 PM EST", thirteen
minutes after its kickoff, so the Scoreboard drew a kickoff card for a game in play; and BYU at Kansas as "2OT" with the
detail "0:00", so its card printed no clock and no final while the page aged.

The rules, in the standing house wording (a reading past its window is shown with its age, never lit as current):
  - a game whose kickoff has passed with no live state reads "No update since <time> ET, waiting for the feed", with no
    score and no kickoff time, never as upcoming;
  - a game in overtime with no running clock prints the time of its reading: "2OT as of 3:43 PM ET"; a running clock
    or a final prints as the feed sends it.
  - a raw network code the desk cannot name (ERADM) is omitted, never printed.

  python3 scripts/n1_scores_test.py      # exit 1 on any failure; no network, no model call
"""
import copy
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
UTC = dt.timezone.utc


def guarded(fails, msg, fn):
    try:
        ok = bool(fn())
    except Exception as e:                                   # noqa: BLE001
        ok, msg = False, f"{msg} [{type(e).__name__}: {str(e)[:120]}]"
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


def game(sb, gid):
    for L in sb["leagues"]:
        for g in L["games"]:
            if str(g["id"]) == gid:
                return g
    return None


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or ""))


def unit():
    fails = []
    print("N-1 scores: an old reading is never drawn as current")
    import scoreboard
    import site_build as sb
    raw = json.load(open(os.path.join(HERE, "fixtures", "n1", "scoreboard-2026-11-21T2043Z.json"), encoding="utf-8"))
    guarded(fails, "the premise: LSU at TENN is 'pre' 13 minutes after kickoff, BYU at KU is 2OT with a 0:00 clock",
            lambda: game(raw, "401856754")["state"] == "pre" and game(raw, "401856866")["status_short"] == "2OT"
            and game(raw, "401856866")["detail"] == "0:00")
    now = dt.datetime(2026, 11, 21, 20, 47, tzinfo=UTC)          # the build after the 20:43 reading
    d = scoreboard.honest(copy.deepcopy(raw), now)
    lsu, byu = game(d, "401856754"), game(d, "401856866")
    guarded(fails, "LSU at TENN reads 'No update since 3:43 PM ET, waiting for the feed'",
            lambda: lsu["status_short"] == "No update since 3:43 PM ET, waiting for the feed")
    guarded(fails, "and is not upcoming: no 'pre' state, no score printed for either side",
            lambda: lsu["state"] != "pre" and lsu["away"]["score"] == "" and lsu["home"]["score"] == "")
    guarded(fails, "BYU at KU prints its reading's time: '2OT as of 3:43 PM ET'", lambda: byu["status_short"] == "2OT as of 3:43 PM ET")
    guarded(fails, "a final is untouched", lambda: game(d, "401858531")["status_short"] == game(raw, "401858531")["status_short"])
    guarded(fails, "a running clock is untouched (UCLA at MICH '14:03 - 1st')",
            lambda: game(d, "401858528")["status_short"] == game(raw, "401858528")["status_short"])
    guarded(fails, "a game whose kickoff is still ahead stays upcoming",
            lambda: all(g["state"] == "pre" for L in d["leagues"] for g in L["games"]
                        if g.get("start_utc") and scoreboard._kick(g) and scoreboard._kick(g) > now
                        and game(raw, str(g["id"]))["state"] == "pre"))
    early = scoreboard.honest(copy.deepcopy(raw), dt.datetime(2026, 11, 21, 20, 29, tzinfo=UTC))
    guarded(fails, "before its kickoff LSU at TENN is still upcoming", lambda: game(early, "401856754")["state"] == "pre")
    # the card a reader sees on /scores
    sb.SB_DATA = d
    card = text(sb._tk_card(lsu, {}))
    guarded(fails, "the /scores card says 'No update since 3:43 PM ET, waiting for the feed' and not the kickoff '3:30'",
            lambda: "No update since 3:43 PM ET, waiting for the feed" in card and "3:30" not in card)
    # S-61: THE CHIP ROW TOO. The card's kicker said "No update since" while its chip row drew the game as live: the
    # score chips (tk-chip-score) with an empty score slot and, where the reading carried one, the possession dot.
    # A past-kickoff game with no live state is drawn stale in the chip row: no score chip, no live dot, the stale style
    # and the "No update since" time.
    lsu_dot = copy.deepcopy(lsu)
    lsu_dot["possession"] = str((lsu_dot.get("home") or {}).get("id") or "")
    raw_card = sb._tk_card(lsu_dot, {})
    mu = re.search(r'<div class="tk-mu" data-role="mu">(.*?)</div>', raw_card, re.S)
    mu = mu.group(1) if mu else ""
    guarded(fails, "the chip row of a past-kickoff game draws no score chip", lambda: mu and "tk-chip-score" not in mu)
    guarded(fails, "the chip row of a past-kickoff game draws no live dot (no possession mark, no live dot)",
            lambda: "tk-poss" not in raw_card and "&#9679;" not in raw_card and 'class="dot"' not in raw_card)
    guarded(fails, "the chip row is drawn in the stale style with the 'No update since' time",
            lambda: "tk-stale" in mu and "No update since 3:43 PM ET" in text(mu))
    guarded(fails, "the band's status for that game is not live (no live dot)",
            lambda: 'class="dot"' not in sb._sb_status(lsu) and "No update since 3:43 PM ET" in text(sb._sb_status(lsu)))
    guarded(fails, "a game really in play keeps its score chips and its live dot",
            lambda: "tk-chip-score" in sb._tk_card(game(d, "401858528"), {})
            and 'class="dot"' in sb._sb_status(game(d, "401858528")))
    card2 = text(sb._tk_card(byu, {}))
    guarded(fails, "the BYU card prints '2OT as of 3:43 PM ET'", lambda: "2OT as of 3:43 PM ET" in card2)
    guarded(fails, "ERADM is omitted, a known network is named",
            lambda: sb.network_name("ERADM") == "" and sb.network_name("ESPN Unlmtd") == "ESPN Unlimited"
            and sb.network_name("ABC") == "ABC")
    guarded(fails, "no card prints the raw code ERADM", lambda: "ERADM" not in text(sb._tk_card(game(d, "401858528"), {})))
    return fails


def main():
    fails = unit()
    print(f"\nN-1 scores: {'PASS' if not fails else 'FAIL'} ({len(fails)} failure(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
