"""Paladin alert feed: raids, and the voice-line list the widget reads.

The random picker lives in widgets/paladin-sub/paladin.js (pickLine). It is
browser code, so these tests do not run it. Manual check: open
?test=sub&once=1 twice. The parchment under the bubble should not repeat
the same Dono sentence back to back. ?test=1 queues the next alert while
one is still speaking.
"""

import json
import re
from pathlib import Path

import pytest

import Server

ROOT = Path(__file__).resolve().parents[1]
LINES_JS = ROOT / "widgets" / "paladin-sub" / "lines.js"
AUDIO = ROOT / "widgets" / "paladin-sub" / "audio"


@pytest.fixture(autouse=True)
def clean_feed(monkeypatch, tmp_path):
    """Empty the event feed and keep the credits file out of the repo."""

    Server.EVENT_ID = 0
    Server.EVENTS.clear()
    monkeypatch.setattr(Server, "CREDITS_FILE", tmp_path / "stream_credits.json")


@pytest.fixture
def client():
    Server.app.config["TESTING"] = True
    return Server.app.test_client()


def load_lines(path):
    """Read lines.js. Full-line // comments and trailing commas are allowed."""

    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    body = raw.split("=", 1)[1].rsplit(";", 1)[0]
    body = re.sub(r",\s*([\]}])", r"\1", body)
    data = json.loads(body)
    if not isinstance(data, dict):
        raise AssertionError("PALADIN_LINES should be an object")
    return data


def test_voice_lines_match_the_audio_files():
    """Every mp3 in audio/ has one line, and every line points at a real mp3."""

    # Proves: lines.js and the audio folder stay in sync, so a renamed file
    # or a blank sentence fails here instead of silently on stream.

    lines = load_lines(LINES_JS)
    assert set(lines) == {"dono", "follow", "raid"}

    dono = {row["file"] for row in lines["dono"]}
    follow = {row["file"] for row in lines["follow"]}
    raid = [row["file"] for row in lines["raid"]]
    assert dono == {f"Dono{i}.mp3" for i in range(1, 12)}
    assert follow == {f"Follow{i}.mp3" for i in range(1, 6)}
    assert raid == ["Raid1.mp3"]

    listed = []
    for key in ("dono", "follow", "raid"):
        for row in lines[key]:
            assert isinstance(row["text"], str) and row["text"].strip()
            assert (AUDIO / row["file"]).is_file()
            listed.append(row["file"])
    on_disk = {path.name for path in AUDIO.glob("*.mp3")}
    assert set(listed) == on_disk
    assert len(listed) == len(set(listed))


def test_widgets_route_serves_a_paladin_line(client, monkeypatch):
    """GET /widgets/paladin-sub/audio/Raid1.mp3 returns that mp3."""

    # Proves: the browser source can load a voice line from the server.

    monkeypatch.delenv("WIDGETS_DIR", raising=False)
    response = client.get("/widgets/paladin-sub/audio/Raid1.mp3")
    assert response.status_code == 200
    assert response.mimetype.startswith("audio/")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.data[:3] == b"ID3"
    assert len(response.data) > 1000


def test_raid_notification_publishes_the_fields_the_widget_reads(client):
    """An incoming raid shows up on /events as type raid, with user and viewers."""

    # Proves: channel.raid reaches the paladin feed. The widget reads
    # user (or login) and viewers. No Twitch call is made.

    Server.handle_notification(
        "channel.raid",
        {
            "from_broadcaster_user_id": "999",
            "from_broadcaster_user_login": "eve",
            "from_broadcaster_user_name": "Eve",
            "to_broadcaster_user_id": "12345",
            "to_broadcaster_user_login": "tyler",
            "to_broadcaster_user_name": "Tyler",
            "viewers": 20,
        },
    )

    response = client.get("/events?since=0")
    assert response.status_code == 200
    events = response.get_json()["events"]
    assert len(events) == 1
    raid = events[0]
    assert raid["type"] == "raid"
    assert raid["user"] == "Eve"
    assert raid["login"] == "eve"
    assert raid["viewers"] == 20


def test_alert_events_publish_the_fields_the_widget_reads(client):
    """Follow, sub, resub, gift, and cheer keep the field names the paladin uses."""

    # Proves: those subscriptions were already handled. This locks the
    # shape the widget reads (user, amount, months) so a raid change
    # cannot drop one of them.

    Server.handle_notification(
        "channel.follow",
        {"user_name": "Dee", "user_login": "dee"},
    )
    Server.handle_notification(
        "channel.subscribe",
        {"user_name": "Bob", "user_login": "bob", "is_anonymous": False},
    )
    Server.handle_notification(
        "channel.subscription.message",
        {
            "user_name": "Bob",
            "user_login": "bob",
            "cumulative_months": 14,
            "duration_months": 1,
            "is_anonymous": False,
        },
    )
    Server.handle_notification(
        "channel.subscription.gift",
        {"user_name": "Ann", "user_login": "ann", "total": 5, "is_anonymous": False},
    )
    Server.handle_notification(
        "channel.cheer",
        {"user_name": "Cal", "user_login": "cal", "bits": 100, "is_anonymous": False},
    )

    by_type = {event["type"]: event for event in Server.EVENTS}
    assert by_type["follow"]["user"] == "Dee"
    assert by_type["sub"]["user"] == "Bob" and by_type["sub"]["amount"] == 1
    assert by_type["resub"]["months"] == 14 and by_type["resub"]["amount"] == 1
    assert by_type["gift"]["user"] == "Ann" and by_type["gift"]["amount"] == 5
    assert by_type["bits"]["user"] == "Cal" and by_type["bits"]["amount"] == 100

    # The widget polls /events. Same objects should be on the route.
    payload = client.get("/events?since=0").get_json()
    assert {event["type"] for event in payload["events"]} == {
        "follow",
        "sub",
        "resub",
        "gift",
        "bits",
    }
