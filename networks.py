#!/usr/bin/env python3
"""networks.py: the one table that turns a feed's network code into the name a reader knows
(S-60 part 3, 21 November 2026).

The feed prints codes: "ERADM" on two cards and the homepage printed "ABCverify". A code with a
mapping prints its name. A code with none prints the feed's own display name, and when that is a
bare code (one all-capital token that no table knows) the card says "Check local listings" and the
code goes to the console log once, so the next mapping is a one-line edit here.

"verify" is the carriage table's internal flag for a row the desk has not confirmed. It is never
reader copy: it is stripped from any network string here, and the chips that carried it are gone.
"""

import re

# Feed code or display string (exact, case-insensitive) to the name readers know.
TABLE = {
    "ABC": "ABC", "CBS": "CBS", "NBC": "NBC", "FOX": "Fox", "FS1": "FS1",
    "ESPN": "ESPN", "ESPN2": "ESPN2", "ESPNU": "ESPNU", "ESPN+": "ESPN+",
    "ESPN UNLMTD": "ESPN Unlimited", "ESPN UNLIMITED": "ESPN Unlimited",
    "SEC NETWORK": "SEC Network", "SECN": "SEC Network", "SECN+": "SECN+",
    "ACC NETWORK": "ACC Network", "ACCN": "ACC Network", "ACCNX": "ACC Network Extra",
    "BTN": "BTN", "CBSSN": "CBSSN", "TNT": "TNT", "TRUTV": "truTV",
    "PEACOCK": "Peacock", "CW": "CW", "USA": "USA Network", "USA NET": "USA Network",
    "USA NETWORK": "USA Network", "NFL NETWORK": "NFL Network", "NFLN": "NFL Network",
    "PRIME VIDEO": "Prime Video", "AMAZON PRIME VIDEO": "Prime Video",
    "NBC SPORTS BO": "NBC Sports Boston", "TBS": "TBS", "FS2": "FS2", "ESPNEWS": "ESPNews",
    "NETFLIX": "Netflix", "YOUTUBE": "YouTube", "APPLE TV+": "Apple TV+",
}
BARE = "Check local listings"
_LOGGED = set()


def clean(raw):
    """The network string with the internal 'verify' flag removed wherever it leaked in."""
    return re.sub(r"(?i)\s*verify\s*$", "", (raw or "").strip()).strip()


def is_bare_code(s):
    """One all-capital token the table does not know, like ERADM: not a name a reader knows."""
    s = (s or "").strip()
    return bool(re.fullmatch(r"[A-Z0-9]{3,8}", s)) and s.upper() not in TABLE


def label(raw):
    """(text, bare): the name to print and whether the feed gave a bare unmapped code."""
    s = clean(raw)
    if not s:
        return "", False
    hit = TABLE.get(s.upper())
    if hit:
        return hit, False
    if is_bare_code(s):
        if s not in _LOGGED:
            _LOGGED.add(s)
            print(f"networks: unmapped network code {s!r}; the card prints {BARE!r}")
        return BARE, True
    return s, False
