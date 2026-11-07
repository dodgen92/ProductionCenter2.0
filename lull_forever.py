"""Checked notes for World of Warcraft: Forever.

Wowhead's /forever/ pages are the public database for that Blizzard ruleset
(launched 4 November 2026, level cap 60). Direct downloads from this
environment get HTTP 403, so a card only includes lines taken from public
page text already retrieved. Missing fields stay empty. Gemini does not fill
them.
"""

SILVERPINE_URL = "https://www.wowhead.com/forever/zone=130/silverpine-forest"
SFK_GUIDE_URL = (
    "https://www.wowhead.com/forever/guide/"
    "shadowfang-keep-dungeon-overview-location-rewards"
)
SFK_JOURNAL_URL = "https://www.wowhead.com/forever/dungeon-journal/shadowfang-keep"

EDITION = "forever"

# NPC rows marked Rare on the Forever Silverpine zone page, status Unchanged.
_SILVERPINE_RARES = (
    {
        "name": "Dalaran Spellscribe",
        "detail": "Level 21 rare humanoid. The Forever zone page marks this row Unchanged.",
        "source": SILVERPINE_URL,
    },
    {
        "name": "Gorefang",
        "detail": "Level 13 rare beast. The Forever zone page marks this row Unchanged.",
        "source": SILVERPINE_URL,
    },
    {
        "name": "Krethis Shadowspinner",
        "detail": "Level 15 rare beast. The Forever zone page marks this row Unchanged.",
        "source": SILVERPINE_URL,
    },
    {
        "name": "Old Vicejaw",
        "detail": "Level 14 rare beast. The Forever zone page marks this row Unchanged.",
        "source": SILVERPINE_URL,
    },
)

CARDS = (
    {
        "id": "silverpine-forest",
        "edition": EDITION,
        "name": "Silverpine Forest",
        "priority": 1,
        "aliases": ("silverpine forest", "silverpine"),
        "sources": (SILVERPINE_URL, SFK_GUIDE_URL),
        "danger": (
            "Wowhead lists Silverpine Forest on Forever as a level 10-20 Horde zone "
            "(zone id 130, added in patch 1.60.1).",
            "Shadowfang Keep is in this forest. The Forever dungeon guide puts the "
            "portal just north of Pyrewood Village and recommends levels 22-30.",
        ),
        "rares": _SILVERPINE_RARES,
        "drops": (),
        "lore": (
            "On the Forever database, Silverpine Forest is Horde territory listed at "
            "levels 10-20. The Forever Shadowfang Keep guide places that dungeon here, "
            "north of Pyrewood, and tells the keep's story: during the Third War, "
            "Archmage Arugal summoned worgen to fight the Scourge, the worgen turned "
            "on Dalaran and took Baron Silverlaine's keep above Pyrewood, and Arugal "
            "stayed there with Fenrus and the ghost of Silverlaine."
        ),
        "development": None,
    },
    {
        "id": "shadowfang-keep",
        "edition": EDITION,
        "name": "Shadowfang Keep",
        "priority": 2,
        "aliases": ("shadowfang keep", "shadowfang", "sfk"),
        "sources": (SFK_GUIDE_URL, SFK_JOURNAL_URL),
        "danger": (
            "The Forever dungeon journal lists Shadowfang Keep at level 22-30. "
            "The Forever guide calls the recommended range 22-30 and says Horde "
            "reach it from The Sepulcher, south along the road, then west.",
            "The same guide describes Rethilgore as a low-health fight. Soul Drain "
            "is called minor. Pull the two surrounding mobs first, then polymorph "
            "or burn the remaining Bleak Worg before focusing him.",
        ),
        "rares": (),
        "drops": (),
        "lore": (
            "The Forever Shadowfang Keep guide says that during the Third War the "
            "Kirin Tor fought the Scourge, slain wizards of Dalaran rose again, and "
            "Archmage Arugal summoned worgen against his peers' advice. The worgen "
            "killed Scourge and then the wizards, took Baron Silverlaine's keep above "
            "Pyrewood, and Arugal, guilty and mad, kept them as his children. He is "
            "said to remain in Shadowfang Keep with his pet Fenrus, haunted by "
            "Silverlaine's ghost."
        ),
        "development": None,
    },
)


def _compact(text):
    return " ".join(str(text or "").lower().split())


def lookup_place(speech, edition=None):
    """Return the best Forever card whose alias appears in the utterance.

    A dungeon alias outranks a zone alias when both match. Another edition
    never receives these cards. No card means the place is unknown.
    """

    edition = (edition or EDITION).strip().lower()
    text = _compact(speech)
    if not text:
        return None
    best = None
    best_key = None
    for card in CARDS:
        if card["edition"] != edition:
            continue
        for alias in card["aliases"]:
            needle = _compact(alias)
            if not needle or needle not in text:
                continue
            key = (card.get("priority", 0), len(needle))
            if best_key is None or key > best_key:
                best = card
                best_key = key
    return best
