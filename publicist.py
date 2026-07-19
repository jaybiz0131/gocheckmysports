#!/usr/bin/env python3
"""
The Publicist: DRAFT-ONLY mode (owner directive 2026-07-14, supersedes the 2026-07-11
full-auto posting doctrine).

The automation no longer posts to LinkedIn at all. On each run it drafts the lead story's
post, runs the SAME deterministic gates, and files the surviving draft into
linkedin-queue/ (one markdown file per draft, committed by the workflow). Jack posts
manually twice a week with his own framing on top; the automation's job is making that a
90-second task. The LinkedIn API path is kept intact but dormant behind --post (a
deliberate flag no workflow passes), so re-arming later is a one-word change.

  - Only fires when at least one story published TODAY; dedupe via linkedin-posted.json
    (now recording queued drafts) so the same story is never queued twice.
  - Gate failure means NO draft filed (a bad post never even reaches the queue).
  - PAUSE-LINKEDIN file at repo root silences the whole thing.
  - Fail-open for the workflow: problems print ::warning:: and exit 0.

USAGE
  python3 publicist.py             # draft, gate, file into linkedin-queue/
  python3 publicist.py --dry-run   # draft + gate report only, files nothing
  python3 publicist.py --post      # legacy direct posting (dormant; needs LinkedIn secrets)
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys
import urllib.request

import llm

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "linkedin-posted.json")
ORIGIN = "https://gocheckmysports.com"
API_VERSION = "202506"

BANNED = [
    r"—", r"–", r"\bguaranteed?\b", r"\bact now\b", r"\bdon'?t miss\b", r"\bhuge\b",
    r"\bmassive\b", r"\bgame.?changer\b", r"\bto the moon\b", r"\bbullish\b", r"\bbearish\b",
    r"\b(you|time to|should) (buy|sell)\b", r"\bexcited to\b", r"\bproud to\b",
    r"\bthoughts\?", r"price target", r"[\U0001F300-\U0001FAFF☀-➿]",
]
ALLOWED_TAGS = {"#sports", "#nfl", "#nba", "#mlb", "#nhl", "#sportsbusiness"}


def todays_lead():
    today = datetime.date.today().isoformat()
    items = []
    for p in glob.glob(os.path.join(HERE, "site", "content", "*.json")):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("date") == today and not d.get("example") and d.get("slug"):
            items.append(d)
    if not items:
        return None
    items.sort(key=lambda d: d.get("rank") or 99)
    return items[0]


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"posted": []}


def run_gates(post, url):
    rep, ok = [], True

    def check(cond, name, detail=""):
        nonlocal ok
        rep.append(f"{'PASS' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))
        if not cond:
            ok = False

    check(len(post) <= 1200, "length <= 1200", str(len(post)))
    check(url in post, "article link present")
    for pat in BANNED:
        check(not re.search(pat, post, re.I), f"banned pattern absent [{pat[:24]}]")
    check("not betting advice" in post.lower(), "not-betting-advice line present")
    check("gocheckmysports" in post.lower(), "site or desk attribution present")
    tags = re.findall(r"#\w+", post)
    check(len(tags) <= 2, "max 2 hashtags", str(tags))
    check(all(t.lower() in ALLOWED_TAGS for t in tags), "hashtags from allowed set", str(tags))
    return ok, rep


def li_escape(text):
    """LinkedIn's commentary field treats these as Little Text Format controls."""
    for ch in "\\|{}@[]()<>*_~":
        text = text.replace(ch, "\\" + ch)
    return text


def post_to_linkedin(post):
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    urn = os.environ.get("LINKEDIN_PERSON_URN", "").strip()
    if not (token and urn):
        print("::warning::publicist: LinkedIn secrets not set; skipping the post "
              "(the site published fine)")
        return None
    body = {
        "author": urn,
        "commentary": li_escape(post),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                          "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    req = urllib.request.Request(
        "https://api.linkedin.com/rest/posts",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "LinkedIn-Version": API_VERSION,
                 "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.headers.get("x-restli-id") or "posted"
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf-8", "ignore")
        if e.code == 401:
            print("::warning::publicist: LinkedIn token expired or invalid (401). "
                  "Re-run linkedin_auth.py to renew; posting resumes automatically.")
        else:
            print(f"::warning::publicist: LinkedIn API {e.code}: {detail}")
        return None


def file_draft(post, lead, url, rep):
    """The review queue: one markdown file per gated draft. Jack opens it, adds his own
    framing line, pastes to LinkedIn. 90 seconds."""
    qdir = os.path.join(HERE, "linkedin-queue")
    os.makedirs(qdir, exist_ok=True)
    today = datetime.date.today().isoformat()
    path = os.path.join(qdir, f"{today}-{lead['slug'][:60]}.md")
    open(path, "w", encoding="utf-8").write(
        f"# LinkedIn draft: {lead.get('title','')}\n\n"
        f"Story: {url}\n\n"
        f"YOUR FRAMING (add 1-2 lines of your own take above the draft before posting):\n\n"
        f"> _______________________________________________\n\n"
        f"---- READY-TO-PASTE DRAFT (passed all {len(rep)} gates) ----\n\n"
        f"{post}\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--post", action="store_true",
                    help="legacy direct posting (dormant; no workflow passes this)")
    args = ap.parse_args()

    if os.path.exists(os.path.join(HERE, "PAUSE-LINKEDIN")):
        print("publicist: PAUSE-LINKEDIN present; not posting.")
        return 0

    lead = todays_lead()
    if not lead:
        print("publicist: nothing published today; no post.")
        return 0

    state = load_state()
    today = datetime.date.today().isoformat()
    if any(p["date"] == today for p in state["posted"]):
        print("publicist: already posted today; done.")
        return 0
    if any(p["slug"] == lead["slug"] for p in state["posted"]):
        print("publicist: lead story already posted previously; skipping.")
        return 0

    url = f"{ORIGIN}/articles/{lead['slug']}.html"
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    client = llm.Client(cfg, mode="live")
    system = open(os.path.join(HERE, "prompts", "publicist.md"), encoding="utf-8").read()
    user = json.dumps({"headline": lead.get("title"), "summary": lead.get("dek"),
                       "key_fact": lead.get("key_fact"), "link": url}, ensure_ascii=False)
    try:
        draft = client.call_json("publicist", system, "Write today's post for this story:\n" + user)
    except Exception as e:
        print(f"::warning::publicist: drafting failed ({e}); no post today.")
        return 0

    post = (draft.get("post") or "").strip()
    ok, rep = run_gates(post, url)
    print("---- drafted post ----\n" + post + "\n---- gates ----")
    print("\n".join(rep))
    if not ok:
        print("::warning::publicist: gates failed; NOT posting today.")
        return 0
    if args.dry_run:
        print("publicist: DRY RUN, gates passed, filing nothing.")
        return 0

    if args.post:  # legacy full-auto path, dormant by directive 2026-07-14
        post_id = post_to_linkedin(post)
        if post_id:
            state["posted"].append({"date": today, "slug": lead["slug"], "post_id": post_id})
            json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
            print(f"publicist: POSTED ({post_id}) and recorded.")
        return 0

    path = file_draft(post, lead, url, rep)
    state["posted"].append({"date": today, "slug": lead["slug"], "post_id": "queued"})
    json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
    print(f"publicist: DRAFT QUEUED -> {os.path.relpath(path)} (nothing posted; "
          f"add your framing and paste to LinkedIn)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
