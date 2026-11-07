"""Forever card lookup. No network."""

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
        card,
        "By the Light, I am still walking.",
        "(FAKENEWS) A producer renamed the keep after a sandwich.",
        [],
    )
    lore = message.index("**📖 LORE**")
    dev = message.index("**🛠️ DEVELOPMENT**")
    assert "Archmage Arugal" in message[lore:dev]
    assert "(FAKENEWS)" not in message[:dev]
    assert "(FAKENEWS)" in message[dev:]
    assert "No three verified drops are on the card" in message
    assert "Soul Drain" in message


def test_cards_do_not_invent_a_third_drop_when_none_are_checked():
    """These starter cards have no verified marquee loot rows."""

    for card in lull_forever.CARDS:
        assert card["edition"] == "forever"
        assert len(card["drops"]) == 0
        assert card["sources"]
