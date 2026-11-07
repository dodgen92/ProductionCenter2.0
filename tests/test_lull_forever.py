"""Forever card lookup. No network."""

import lull
import lull_classic
import lull_forever


def test_sfk_outranks_silverpine_and_other_editions_miss():
    """Saying SFK via Silverpine uses the dungeon card. Retail has no card."""

    zone = lull_forever.lookup_place("Headed to Silverpine Forest", "forever")
    assert zone["id"] == "silverpine-forest"
    dungeon = lull_forever.lookup_place("headed SFK via Silverpine", "forever")
    assert dungeon["id"] == "shadowfang-keep"
    assert lull_forever.lookup_place("Headed to Silverpine Forest", "retail") is None
    assert lull_forever.lookup_place("moonbrook", "forever") is None


def test_fakenews_stays_out_of_the_lore_and_drops():
    """The joke label is not mixed into lore, and missing loot is not invented."""

    import lull

    card = lull_forever.lookup_place("sfk", "forever")
    message = lull.render_guide(
        lull.notes_from_forever(card),
        "By the Light, I am still walking.",
        "(FAKENEWS) A producer renamed the keep after a sandwich.",
        [],
    )
    lore = message.index("**📖 LORE**")
    dev = message.index("**🛠️ DEVELOPMENT**")
    assert "Archmage Arugal" in message[lore:dev]
    assert "(FAKENEWS)" not in message[:dev]
    assert "(FAKENEWS)" in message[dev:]
    assert "No three verified drops were named in the source text." in message
    assert "Soul Drain" in message


def test_fetch_page_failure_is_not_a_fact():
    """A network error becomes no page, not a made-up extract."""

    def boom(url, params):
        raise OSError("offline")

    lull_classic.clear_cache()
    assert lull_classic.fetch_page("Westfall (Classic)", http_get=boom) is None
    lull_classic.clear_cache()
    """These starter cards have no verified marquee loot rows."""

    for card in lull_forever.CARDS:
        assert card["edition"] == "forever"
        assert len(card["drops"]) == 0
        assert card["sources"]
