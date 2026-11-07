"""Classic-era page lookup for places Forever cards do not cover.

Facts are the text of a Warcraft Wiki page whose title ends in "(Classic)".
That is the pre-Cataclysm article, not the retail page. The caller must say
the text may differ in World of Warcraft: Forever. A failed read leaves the
place unknown. Nothing here is a retail or Cataclysm source.
"""

import time

import requests

API = "https://warcraft.wiki.gg/api.php"
TTL_SECONDS = 6 * 3600
_cache = {}

# Names only. The page text is fetched. Dungeons outrank zones when both match.
PLACES = (
    ("deadmines", "Deadmines (Classic)", 2),
    ("the deadmines", "Deadmines (Classic)", 2),
    ("wailing caverns", "Wailing Caverns (Classic)", 2),
    ("shadowfang keep", "Shadowfang Keep (Classic)", 2),
    ("shadowfang", "Shadowfang Keep (Classic)", 2),
    ("sfk", "Shadowfang Keep (Classic)", 2),
    ("the stockade", "The Stockade (Classic)", 2),
    ("stockade", "The Stockade (Classic)", 2),
    ("gnomeregan", "Gnomeregan (Classic)", 2),
    ("razorfen kraul", "Razorfen Kraul (Classic)", 2),
    ("razorfen downs", "Razorfen Downs (Classic)", 2),
    ("scarlet monastery", "Scarlet Monastery (Classic)", 2),
    ("uldaman", "Uldaman (Classic)", 2),
    ("zul'farrak", "Zul'Farrak (Classic)", 2),
    ("zulfarrak", "Zul'Farrak (Classic)", 2),
    ("maraudon", "Maraudon (Classic)", 2),
    ("sunken temple", "Temple of Atal'Hakkar (Classic)", 2),
    ("blackrock depths", "Blackrock Depths (Classic)", 2),
    ("blackrock spire", "Blackrock Spire (Classic)", 2),
    ("stratholme", "Stratholme (Classic)", 2),
    ("scholomance", "Scholomance (Classic)", 2),
    ("dire maul", "Dire Maul (Classic)", 2),
    ("ragefire chasm", "Ragefire Chasm (Classic)", 2),
    ("blackfathom deeps", "Blackfathom Deeps (Classic)", 2),
    ("westfall", "Westfall (Classic)", 1),
    ("elwynn", "Elwynn Forest (Classic)", 1),
    ("elwynn forest", "Elwynn Forest (Classic)", 1),
    ("redridge", "Redridge Mountains (Classic)", 1),
    ("duskwood", "Duskwood (Classic)", 1),
    ("stranglethorn", "Stranglethorn Vale (Classic)", 1),
    ("swamp of sorrows", "Swamp of Sorrows (Classic)", 1),
    ("blasted lands", "Blasted Lands (Classic)", 1),
    ("burning steppes", "Burning Steppes (Classic)", 1),
    ("searing gorge", "Searing Gorge (Classic)", 1),
    ("badlands", "Badlands (Classic)", 1),
    ("loch modan", "Loch Modan (Classic)", 1),
    ("wetlands", "Wetlands (Classic)", 1),
    ("arathi", "Arathi Highlands (Classic)", 1),
    ("hillsbrad", "Hillsbrad Foothills (Classic)", 1),
    ("alterac", "Alterac Mountains (Classic)", 1),
    ("silverpine", "Silverpine Forest (Classic)", 1),
    ("tirisfal", "Tirisfal Glades (Classic)", 1),
    ("western plaguelands", "Western Plaguelands (Classic)", 1),
    ("eastern plaguelands", "Eastern Plaguelands (Classic)", 1),
    ("hinterlands", "The Hinterlands (Classic)", 1),
    ("dun morogh", "Dun Morogh (Classic)", 1),
    ("durotar", "Durotar (Classic)", 1),
    ("the barrens", "The Barrens (Classic)", 1),
    ("barrens", "The Barrens (Classic)", 1),
    ("mulgore", "Mulgore (Classic)", 1),
    ("stonetalon", "Stonetalon Mountains (Classic)", 1),
    ("desolace", "Desolace (Classic)", 1),
    ("feralas", "Feralas (Classic)", 1),
    ("thousand needles", "Thousand Needles (Classic)", 1),
    ("tanaris", "Tanaris (Classic)", 1),
    ("un'goro", "Un'Goro Crater (Classic)", 1),
    ("ungoro", "Un'Goro Crater (Classic)", 1),
    ("silithus", "Silithus (Classic)", 1),
    ("felwood", "Felwood (Classic)", 1),
    ("winterspring", "Winterspring (Classic)", 1),
    ("azshara", "Azshara (Classic)", 1),
    ("ashenvale", "Ashenvale (Classic)", 1),
    ("darkshore", "Darkshore (Classic)", 1),
    ("teldrassil", "Teldrassil (Classic)", 1),
    ("moonglade", "Moonglade (Classic)", 1),
    ("dustwallow", "Dustwallow Marsh (Classic)", 1),
    ("stormwind", "Stormwind City (Classic)", 1),
    ("orgrimmar", "Orgrimmar (Classic)", 1),
    ("thunder bluff", "Thunder Bluff (Classic)", 1),
    ("undercity", "Undercity (Classic)", 1),
    ("ironforge", "Ironforge (Classic)", 1),
    ("darnassus", "Darnassus (Classic)", 1),
)


def _compact(text):
    return " ".join(str(text or "").lower().split())


def match_place(speech):
    """Longest specific alias in the utterance. Dungeons beat zones."""

    text = _compact(speech)
    if not text:
        return None
    best = None
    best_key = None
    for alias, title, priority in PLACES:
        needle = _compact(alias)
        if needle and needle in text:
            key = (priority, len(needle))
            if best_key is None or key > best_key:
                best = {"alias": alias, "title": title, "priority": priority}
                best_key = key
    return best


def page_url(title):
    return "https://warcraft.wiki.gg/wiki/" + title.replace(" ", "_")


def clear_cache():
    _cache.clear()


def fetch_page(title, http_get=None, now=None):
    """Load one Classic page. http_get(url, params) is injectable for tests."""

    moment = time.monotonic() if now is None else now
    cached = _cache.get(title)
    if cached and moment - cached[0] < TTL_SECONDS:
        return cached[1]
    getter = http_get or _http_get
    try:
        payload = getter(API, {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": "1",
            "exchars": "3500",
            "format": "json",
        })
    except Exception as exc:
        print(f"[Lull] Classic page failed: {type(exc).__name__}")
        return None
    pages = {}
    if isinstance(payload, dict):
        pages = (payload.get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), None) if isinstance(pages, dict) else None
    if not isinstance(page, dict) or "missing" in page:
        print("[Lull] Classic page missing.")
        return None
    extract = " ".join(str(page.get("extract") or "").split())
    if not extract:
        print("[Lull] Classic page had no text.")
        return None
    result = {
        "name": title.replace(" (Classic)", ""),
        "title": title,
        "extract": extract[:3500],
        "url": page_url(title),
        "label": "Classic-era Warcraft Wiki. This may differ in World of Warcraft: Forever.",
    }
    _cache[title] = (moment, result)
    return result


def _http_get(url, params):
    response = requests.get(
        url,
        params=params,
        timeout=8,
        headers={"User-Agent": "ProductionCenterLull/1.0"},
    )
    response.raise_for_status()
    return response.json()
