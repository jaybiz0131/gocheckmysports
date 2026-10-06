#!/usr/bin/env python3
"""commit_trailers.py: no attribution trailer of any kind in any commit message.

Not Co-Authored-By, not Claude-Session, not Generated-with, whatever a session reminder
asks for (the owner's instruction takes precedence, 6 October 2026). Only a trailer LINE
counts: a subject that names the rule is not a violation.

    python3 commit_trailers.py [BASE]    messages of BASE..HEAD (default origin/main); exit 1 on a hit
"""
import re
import subprocess
import sys

TRAILER = re.compile(
    r"^\W*(co-authored-by|claude-session|generated[- ]with)\b", re.I | re.M)


def hits(message):
    """The offending lines of one commit message; empty when clean."""
    return [m.group(0).strip() for m in TRAILER.finditer(message or "")]


def branch_hits(base="origin/main"):
    """(hash, line) for every commit in base..HEAD that carries a trailer. A checkout with
    no such ref (a shallow CI clone) has nothing to read and returns []."""
    try:
        subprocess.run(["git", "rev-parse", "--verify", "-q", base],
                       check=True, capture_output=True)
        out = subprocess.run(["git", "log", f"{base}..HEAD", "--format=%h%x1f%B%x1e"],
                             check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    found = []
    for rec in out.split("\x1e"):
        h, _, body = rec.strip().partition("\x1f")
        for line in hits(body):
            found.append((h, line))
    return found


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    bad = branch_hits(base)
    for h, line in bad:
        print(f"trailer: {h}: {line}")
    print(f"commit trailers: {len(bad)} hit(s) in {base}..HEAD")
    sys.exit(1 if bad else 0)
